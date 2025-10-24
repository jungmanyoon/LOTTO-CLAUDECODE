#!/usr/bin/env python3
"""
지속적인 성능 개선 엔진
- 매 회차마다 자동 백테스팅 및 성능 개선
- 다양한 임계값 테스트 및 최적화
- 실시간 성능 비교 및 자동 적용
- 성능 저하 시 자동 롤백
"""
import os
import json
import sqlite3
import logging
import threading
import time
import schedule
import pytz
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import numpy as np
import yaml
from dataclasses import dataclass
from enum import Enum

# 기존 컴포넌트 임포트
from .performance_stats_manager import PerformanceStatsManager
from .threshold_optimizer import ThresholdOptimizer
from .db_manager import DatabaseManager
from ..backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework

class OptimizationStatus(Enum):
    """최적화 상태"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

@dataclass
class PerformanceMetrics:
    """성능 지표"""
    avg_matches: float
    best_match: int
    accuracy_3plus: float
    ml_inclusion_rate: float
    combination_count: int
    threshold: float
    ml_bypass_filters: int
    ml_weight: float
    filter_pass_rate: float  # ✅ NEW: 필터 통과율 추적 (historical winning numbers 통과율)
    timestamp: datetime
    session_id: int = None

class PerformanceTracker:
    """성능 추적 및 분석 클래스"""

    def __init__(self, db_path: str = "data/continuous_improvement.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()

    def _init_database(self):
        """지속적 개선용 데이터베이스 초기화"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 성능 이력 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_number INTEGER,
                    avg_matches REAL NOT NULL,
                    best_match INTEGER,
                    accuracy_3plus REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    threshold REAL NOT NULL,
                    ml_bypass_filters INTEGER,
                    ml_weight REAL,
                    filter_pass_rate REAL,
                    is_baseline BOOLEAN DEFAULT FALSE,
                    is_best BOOLEAN DEFAULT FALSE,
                    is_best_pass_rate BOOLEAN DEFAULT FALSE,
                    improvement_from_baseline REAL,
                    session_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 최적화 세션 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimization_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_number INTEGER,
                    session_type TEXT, -- 'weekly', 'manual', 'triggered'
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT,
                    tests_count INTEGER DEFAULT 0,
                    improvements_found INTEGER DEFAULT 0,
                    best_threshold REAL,
                    best_ml_bypass INTEGER,
                    best_ml_weight REAL,
                    best_performance REAL,
                    baseline_performance REAL,
                    improvement_rate REAL,
                    applied BOOLEAN DEFAULT FALSE,
                    rollback_reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 파라미터 변경 이력
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS parameter_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    parameter_name TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL,
                    change_reason TEXT,
                    applied_at TEXT,
                    rollback_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES optimization_sessions (id)
                )
            """)

            # ✅ NEW: 필터 조건 스냅샷 테이블 (롤백 지원)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_criteria_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    performance_history_id INTEGER,
                    filter_name TEXT NOT NULL,
                    criteria_json TEXT NOT NULL,
                    filter_pass_rate REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (performance_history_id) REFERENCES performance_history (id)
                )
            """)

            # ✅ 기존 테이블에 filter_pass_rate 컬럼 추가 (마이그레이션)
            try:
                cursor.execute("ALTER TABLE performance_history ADD COLUMN filter_pass_rate REAL")
            except sqlite3.OperationalError:
                pass  # 컬럼이 이미 존재하는 경우 무시

            # ✅ 기존 테이블에 is_best_pass_rate 컬럼 추가 (마이그레이션)
            try:
                cursor.execute("ALTER TABLE performance_history ADD COLUMN is_best_pass_rate BOOLEAN DEFAULT FALSE")
            except sqlite3.OperationalError:
                pass  # 컬럼이 이미 존재하는 경우 무시

            conn.commit()

    def save_performance_result(self, metrics: PerformanceMetrics, round_number: int = None,
                              is_baseline: bool = False) -> int:
        """성능 결과 저장"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 현재 최고 성능 확인
            cursor.execute("""
                SELECT MAX(avg_matches) FROM performance_history
                WHERE round_number = ? OR round_number IS NULL
            """, (round_number,))

            current_best = cursor.fetchone()[0] or 0
            is_best = metrics.avg_matches > current_best

            # ✅ NEW: 현재 최고 필터 통과율 확인
            cursor.execute("""
                SELECT MAX(filter_pass_rate) FROM performance_history
                WHERE round_number = ? OR round_number IS NULL
            """, (round_number,))

            current_best_pass_rate = cursor.fetchone()[0] or 0
            is_best_pass_rate = metrics.filter_pass_rate > current_best_pass_rate

            # 베이스라인 대비 개선율 계산
            improvement_from_baseline = 0.0
            if not is_baseline:
                cursor.execute("""
                    SELECT avg_matches FROM performance_history
                    WHERE is_baseline = TRUE
                    ORDER BY created_at DESC LIMIT 1
                """)
                baseline = cursor.fetchone()
                if baseline and baseline[0] > 0:
                    improvement_from_baseline = (metrics.avg_matches - baseline[0]) / baseline[0]

            # 새로운 최고 성능이면 기존 best 플래그 제거
            if is_best:
                cursor.execute("""
                    UPDATE performance_history SET is_best = FALSE
                    WHERE round_number = ? OR round_number IS NULL
                """, (round_number,))

            # ✅ NEW: 새로운 최고 필터 통과율이면 기존 best_pass_rate 플래그 제거
            if is_best_pass_rate:
                cursor.execute("""
                    UPDATE performance_history SET is_best_pass_rate = FALSE
                    WHERE round_number = ? OR round_number IS NULL
                """, (round_number,))

            # 성능 결과 저장
            cursor.execute("""
                INSERT INTO performance_history
                (round_number, avg_matches, best_match, accuracy_3plus, ml_inclusion_rate,
                 combination_count, threshold, ml_bypass_filters, ml_weight, filter_pass_rate,
                 is_baseline, is_best, is_best_pass_rate, improvement_from_baseline, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                round_number, metrics.avg_matches, metrics.best_match, metrics.accuracy_3plus,
                metrics.ml_inclusion_rate, metrics.combination_count, metrics.threshold,
                metrics.ml_bypass_filters, metrics.ml_weight, metrics.filter_pass_rate,
                is_baseline, is_best, is_best_pass_rate, improvement_from_baseline, metrics.session_id
            ))

            record_id = cursor.lastrowid
            conn.commit()

            self.logger.info(
                f"성능 결과 저장 완료 (ID: {record_id}, 평균 매치: {metrics.avg_matches:.3f}, "
                f"필터 통과율: {metrics.filter_pass_rate:.1f}%)"
            )
            return record_id

    def get_best_performance(self, round_number: int = None) -> Optional[PerformanceMetrics]:
        """최고 성능 기록 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM performance_history
                WHERE is_best = TRUE
            """
            params = []

            if round_number:
                query += " AND round_number = ?"
                params.append(round_number)

            query += " ORDER BY avg_matches DESC LIMIT 1"

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return PerformanceMetrics(
                    avg_matches=row[2],
                    best_match=row[3],
                    accuracy_3plus=row[4],
                    ml_inclusion_rate=row[5],
                    combination_count=row[6],
                    threshold=row[7],
                    ml_bypass_filters=row[8],
                    ml_weight=row[9],
                    filter_pass_rate=row[10] if row[10] is not None else 0.0,  # ✅ NEW
                    timestamp=datetime.fromisoformat(row[16]) if row[16] and isinstance(row[16], str) else datetime.now(),  # ✅ FIXED: handle None
                    session_id=row[15]  # ✅ FIXED: correct index
                )
        return None

    def get_best_pass_rate_performance(self, round_number: int = None) -> Optional[PerformanceMetrics]:
        """✅ NEW: 최고 필터 통과율 기록 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM performance_history
                WHERE is_best_pass_rate = TRUE
            """
            params = []

            if round_number:
                query += " AND round_number = ?"
                params.append(round_number)

            query += " ORDER BY filter_pass_rate DESC LIMIT 1"

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return PerformanceMetrics(
                    avg_matches=row[2],
                    best_match=row[3],
                    accuracy_3plus=row[4],
                    ml_inclusion_rate=row[5],
                    combination_count=row[6],
                    threshold=row[7],
                    ml_bypass_filters=row[8],
                    ml_weight=row[9],
                    filter_pass_rate=row[10] if row[10] is not None else 0.0,
                    timestamp=datetime.fromisoformat(row[16]) if row[16] and isinstance(row[16], str) else datetime.now(),  # ✅ FIXED: handle None
                    session_id=row[15]  # ✅ FIXED: correct index
                )
        return None

    def save_filter_criteria_snapshot(self, performance_history_id: int,
                                     filter_criteria: Dict[str, Dict],
                                     filter_pass_rate: float) -> int:
        """✅ NEW: 필터 조건 스냅샷 저장 (롤백 지원용)"""
        import json

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for filter_name, criteria in filter_criteria.items():
                cursor.execute("""
                    INSERT INTO filter_criteria_snapshots
                    (performance_history_id, filter_name, criteria_json, filter_pass_rate)
                    VALUES (?, ?, ?, ?)
                """, (
                    performance_history_id,
                    filter_name,
                    json.dumps(criteria, ensure_ascii=False),
                    filter_pass_rate
                ))

            conn.commit()
            self.logger.info(
                f"필터 조건 스냅샷 저장 완료 (Performance ID: {performance_history_id}, "
                f"{len(filter_criteria)}개 필터, 통과율: {filter_pass_rate:.1f}%)"
            )
            return performance_history_id

    def get_filter_criteria_snapshot(self, performance_history_id: int) -> Dict[str, Dict]:
        """✅ NEW: 필터 조건 스냅샷 조회 (롤백용)"""
        import json

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT filter_name, criteria_json
                FROM filter_criteria_snapshots
                WHERE performance_history_id = ?
            """, (performance_history_id,))

            filter_criteria = {}
            for row in cursor.fetchall():
                filter_name = row[0]
                criteria_json = row[1]
                filter_criteria[filter_name] = json.loads(criteria_json)

            return filter_criteria

    def get_performance_trends(self, days: int = 30) -> List[Dict]:
        """성능 추이 분석"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    DATE(created_at) as date,
                    AVG(avg_matches) as avg_performance,
                    MAX(avg_matches) as best_performance,
                    COUNT(*) as test_count,
                    AVG(ml_inclusion_rate) as avg_ml_inclusion,
                    AVG(threshold) as avg_threshold
                FROM performance_history
                WHERE created_at >= datetime('now', '-{} days')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """.format(days))

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

class AutoOptimizer:
    """자동 최적화 클래스"""

    def __init__(self, db_manager: DatabaseManager, config_path: str = "configs/adaptive_filter_config.yaml"):
        self.db_manager = db_manager
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)

        # 최적화 범위 설정
        self.threshold_candidates = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
        self.ml_bypass_candidates = list(range(5, 16))  # 5~15
        self.ml_weight_candidates = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]

    def grid_search_optimization(self, baseline_metrics: PerformanceMetrics,
                               max_tests: int = 50) -> Dict[str, Any]:
        """그리드 서치 최적화"""
        self.logger.info(f"그리드 서치 최적화 시작 (최대 {max_tests}회 테스트)")

        best_result = {
            'params': {
                'threshold': baseline_metrics.threshold,
                'ml_bypass': baseline_metrics.ml_bypass_filters,
                'ml_weight': baseline_metrics.ml_weight
            },
            'performance': baseline_metrics.avg_matches,
            'improvement': 0.0
        }

        test_count = 0
        results = []

        # 백테스팅 프레임워크 초기화
        backtesting = OptimizedBacktestingFramework(self.db_manager)

        # 그리드 서치 실행
        for threshold in self.threshold_candidates:
            if test_count >= max_tests:
                break

            for ml_bypass in self.ml_bypass_candidates:
                if test_count >= max_tests:
                    break

                for ml_weight in self.ml_weight_candidates:
                    if test_count >= max_tests:
                        break

                    # 현재 설정과 동일하면 스킵
                    if (threshold == baseline_metrics.threshold and
                        ml_bypass == baseline_metrics.ml_bypass_filters and
                        ml_weight == baseline_metrics.ml_weight):
                        continue

                    try:
                        # 임시 설정 적용
                        temp_config = self._create_temp_config(threshold, ml_bypass, ml_weight)

                        # 백테스팅 프레임워크에 설정 적용
                        self._apply_config_to_framework(backtesting, temp_config)

                        # 백테스팅 실행 (최근 30회차)
                        latest_round = self.db_manager.get_latest_round()
                        start_round = max(1, latest_round - 29)

                        result = backtesting.run_backtest(
                            start_round=start_round,
                            end_round=latest_round
                        )

                        avg_matches = result.get('performance_metrics', {}).get('overall_avg_matches', 0)
                        ml_inclusion = result.get('ml_inclusion_rate', 0)

                        test_result = {
                            'threshold': threshold,
                            'ml_bypass': ml_bypass,
                            'ml_weight': ml_weight,
                            'avg_matches': avg_matches,
                            'ml_inclusion_rate': ml_inclusion,
                            'improvement': avg_matches - baseline_metrics.avg_matches
                        }

                        results.append(test_result)
                        test_count += 1

                        # 더 좋은 결과인지 확인
                        if avg_matches > best_result['performance']:
                            best_result = {
                                'params': {
                                    'threshold': threshold,
                                    'ml_bypass': ml_bypass,
                                    'ml_weight': ml_weight
                                },
                                'performance': avg_matches,
                                'improvement': avg_matches - baseline_metrics.avg_matches
                            }

                        self.logger.info(f"테스트 {test_count}/{max_tests}: "
                                       f"임계값={threshold}, ML바이패스={ml_bypass}, ML가중치={ml_weight} "
                                       f"→ 평균매치={avg_matches:.3f} (개선: {avg_matches - baseline_metrics.avg_matches:+.3f})")

                    except Exception as e:
                        self.logger.error(f"그리드 서치 테스트 실패: {e}")
                        continue

        return {
            'best_result': best_result,
            'total_tests': test_count,
            'all_results': results
        }

    def bayesian_optimization(self, baseline_metrics: PerformanceMetrics,
                            n_trials: int = 30) -> Dict[str, Any]:
        """베이지안 최적화 (기존 ThresholdOptimizer 활용)"""
        self.logger.info(f"베이지안 최적화 시작 ({n_trials}회 시도)")

        optimizer = ThresholdOptimizer(
            config_path=self.config_path,
            stats_db_path="data/performance_stats.db"
        )

        def backtesting_func(config):
            """백테스팅 함수"""
            backtesting = OptimizedBacktestingFramework(self.db_manager)
            latest_round = self.db_manager.get_latest_round()
            start_round = max(1, latest_round - 29)

            # 백테스팅 프레임워크에 설정 적용
            self._apply_config_to_framework(backtesting, config)

            result = backtesting.run_backtest(
                start_round=start_round,
                end_round=latest_round
            )

            return {
                'avg_matches': result.get('performance_metrics', {}).get('overall_avg_matches', 0),
                'ml_inclusion_rate': result.get('ml_inclusion_rate', 0),
                'combination_count': result.get('combination_count', 0)
            }

        # 베이지안 최적화 실행
        results = optimizer.optimize(
            backtesting_func=backtesting_func,
            n_trials=n_trials,
            n_jobs=1
        )

        improvement = results['best_score'] - baseline_metrics.avg_matches

        return {
            'best_params': results['best_params'],
            'best_performance': results['avg_matches'],
            'improvement': improvement,
            'trials_completed': results['n_trials']
        }

    def _create_temp_config(self, threshold: float, ml_bypass: int, ml_weight: float) -> Dict:
        """임시 설정 생성"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"개선 엔진 실패: {e}")
            config = {}

        # 임계값 설정
        config['global_probability_threshold'] = threshold

        # ML 통합 설정
        if 'ml_integration' not in config:
            config['ml_integration'] = {}

        config['ml_integration']['ml_bypass_filters'] = ml_bypass
        config['ml_integration']['ml_weight'] = ml_weight

        return config

    def _apply_config_to_framework(self, framework: 'OptimizedBacktestingFramework', config: Dict):
        """백테스팅 프레임워크에 설정 적용"""
        try:
            # 필터 매니저 설정 적용
            if hasattr(framework, 'filter_manager'):
                # 적응형 필터 임계값 설정
                if hasattr(framework.filter_manager, 'adaptive_filter'):
                    threshold = config.get('global_probability_threshold', 1.0)
                    framework.filter_manager.adaptive_filter.probability_threshold = threshold

                # 통합 필터 매니저인 경우
                elif hasattr(framework.filter_manager, 'set_config'):
                    framework.filter_manager.set_config(config)

            # ML 설정 적용
            ml_config = config.get('ml_integration', {})
            framework.ml_config = {
                'ml_bypass_filters': ml_config.get('ml_bypass_filters', 8),
                'ml_weight': ml_config.get('ml_weight', 0.4),
                'ml_relaxed_threshold': ml_config.get('ml_relaxed_threshold', 0.5)
            }

        except Exception as e:
            self.logger.warning(f"설정 적용 중 오류: {e}")

class ContinuousImprovementEngine:
    """지속적인 성능 개선 엔진"""

    def __init__(self,
                 db_manager: DatabaseManager,
                 config_path: str = "configs/adaptive_filter_config.yaml",
                 improvement_db_path: str = "data/continuous_improvement.db"):

        self.db_manager = db_manager
        self.config_path = config_path
        self.improvement_db_path = improvement_db_path
        self.logger = logging.getLogger(__name__)

        # 컴포넌트 초기화
        self.performance_tracker = PerformanceTracker(improvement_db_path)
        self.auto_optimizer = AutoOptimizer(db_manager, config_path)
        self.stats_manager = PerformanceStatsManager()

        # 상태 관리
        self.status = OptimizationStatus.IDLE
        self.current_session_id = None
        self.is_running = False

        # 설정 로드
        self.config = self._load_config()

        # 스케줄러 설정 (한국 시간 기준)
        self.korea_tz = pytz.timezone('Asia/Seoul')

        # 백그라운드 스레드
        self.scheduler_thread = None
        self.optimization_lock = threading.Lock()

    def _load_config(self) -> Dict:
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"설정 파일 로드 실패: {e}")
            return {}

    def _save_config(self, config: Dict, backup: bool = True):
        """설정 파일 저장"""
        try:
            if backup:
                # 백업 생성
                backup_path = self.config_path.replace(
                    '.yaml',
                    f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml'
                )
                with open(backup_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, allow_unicode=True)

                self.logger.info(f"설정 백업 생성: {backup_path}")

            # 새 설정 저장
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)

            self.config = config
            self.logger.info("설정 파일 업데이트 완료")

        except Exception as e:
            self.logger.error(f"설정 파일 저장 실패: {e}")
            raise

    def start_continuous_improvement(self):
        """지속적 개선 시스템 시작"""
        if self.is_running:
            self.logger.warning("지속적 개선 시스템이 이미 실행 중입니다.")
            return

        self.is_running = True
        self.logger.info("지속적 성능 개선 시스템 시작")

        # 토요일 밤 8시 30분 (로또 추첨 후) 자동 실행 스케줄
        schedule.every().saturday.at("20:30").do(self._weekly_optimization_job)

        # 매일 저녁 9시 새 회차 확인 및 최적화 (토요일 제외)
        schedule.every().day.at("21:00").do(self._check_new_round_and_optimize)

        # 매일 오전 3시 베이스라인 업데이트 검사
        schedule.every().day.at("03:00").do(self._daily_baseline_check)

        # 스케줄러 스레드 시작
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

        self.logger.info("자동 스케줄러 활성화 완료")
        self.logger.info("- 매주 토요일 20:30: 주간 최적화")
        self.logger.info("- 매일 21:00: 새 회차 확인 및 최적화")
        self.logger.info("- 매일 03:00: 베이스라인 점검")

    def stop_continuous_improvement(self):
        """지속적 개선 시스템 중지"""
        self.is_running = False
        schedule.clear()

        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        self.logger.info("지속적 성능 개선 시스템 중지")

    def _run_scheduler(self):
        """스케줄러 실행"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 체크
            except Exception as e:
                self.logger.error(f"스케줄러 오류: {e}")
                time.sleep(300)  # 오류 시 5분 대기

    def _weekly_optimization_job(self):
        """주간 최적화 작업"""
        try:
            self.logger.info("주간 자동 최적화 시작")

            # 새로운 회차 데이터 확인
            latest_round = self.db_manager.get_latest_round()
            if latest_round is None:
                self.logger.warning("최신 회차 정보를 가져올 수 없습니다.")
                return

            # 최적화 실행
            results = self.run_optimization_cycle(
                round_number=latest_round,
                session_type='weekly'
            )

            if results.get('improvement_applied', False):
                self.logger.info(f"주간 최적화 완료: 성능 개선 적용됨 (개선율: {results.get('improvement_rate', 0):.2%})")
            else:
                self.logger.info(f"주간 최적화 완료: 현재 설정 유지 (최고 성능: {results.get('best_performance', 0):.3f})")

        except Exception as e:
            self.logger.error(f"주간 최적화 작업 실패: {e}")

    def _check_new_round_and_optimize(self):
        """새 회차 확인 및 자동 최적화"""
        try:
            # 토요일은 20:30에 실행되므로 스킵
            from datetime import datetime
            if datetime.now().weekday() == 5:  # 토요일 = 5
                return

            self.logger.info("새 회차 확인 및 자동 최적화 시작")

            # 최신 회차 확인
            latest_round = self.db_manager.get_latest_round()

            # 마지막 최적화 세션 확인
            with sqlite3.connect(self.improvement_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT round_number FROM optimization_sessions
                    WHERE status = 'completed'
                    ORDER BY created_at DESC LIMIT 1
                """)
                last_optimized = cursor.fetchone()

            # 새 회차가 있고 아직 최적화하지 않았다면 실행
            # None 체크 추가하여 NoneType 비교 오류 방지
            if (latest_round is not None and
                (not last_optimized or (last_optimized[0] is not None and latest_round > last_optimized[0]))):
                self.logger.info(f"새 회차 {latest_round} 발견, 최적화 시작")

                # 최적화 실행
                results = self.run_optimization_cycle(
                    round_number=latest_round,
                    session_type='daily'
                )

                if results.get('improvement_applied', False):
                    self.logger.info(f"새 회차 최적화 완료: 성능 개선 적용 (개선: {results.get('improvement_rate', 0):.2%})")
                else:
                    self.logger.info(f"새 회차 최적화 완료: 현재 설정 유지 (성능: {results.get('best_performance', 0):.3f})")
            else:
                self.logger.info("새 회차 없음 또는 이미 최적화됨")

        except Exception as e:
            self.logger.error(f"새 회차 확인 및 최적화 실패: {e}")

    def _daily_baseline_check(self):
        """일일 베이스라인 점검"""
        try:
            self.logger.info("일일 베이스라인 점검 시작")

            # 현재 성능 측정
            current_metrics = self._measure_current_performance()
            if current_metrics is None:
                return

            # 베이스라인과 비교
            best_performance = self.performance_tracker.get_best_performance()

            if best_performance is None:
                # 첫 베이스라인 설정
                self.performance_tracker.save_performance_result(
                    current_metrics, is_baseline=True
                )
                self.logger.info("첫 베이스라인 설정 완료")
            else:
                # 성능 저하 확인 (10% 이상 하락)
                performance_ratio = current_metrics.avg_matches / best_performance.avg_matches

                if performance_ratio < 0.9:
                    self.logger.warning(f"성능 저하 감지: {performance_ratio:.1%} (현재: {current_metrics.avg_matches:.3f}, 최고: {best_performance.avg_matches:.3f})")

                    # 긴급 최적화 트리거
                    self.trigger_emergency_optimization()
                else:
                    self.logger.info(f"베이스라인 점검 완료: 성능 유지 ({performance_ratio:.1%})")

        except Exception as e:
            self.logger.error(f"일일 베이스라인 점검 실패: {e}")

    def run_optimization_cycle(self, round_number: int = None,
                             session_type: str = 'manual') -> Dict[str, Any]:
        """최적화 사이클 실행"""
        with self.optimization_lock:
            if self.status == OptimizationStatus.RUNNING:
                self.logger.warning("이미 최적화가 실행 중입니다.")
                return {'status': 'already_running'}

            self.status = OptimizationStatus.RUNNING

            try:
                self.logger.info(f"최적화 사이클 시작 (타입: {session_type})")

                # 세션 시작
                session_id = self._start_optimization_session(round_number, session_type)
                self.current_session_id = session_id

                # 현재 성능 측정 (베이스라인)
                baseline_metrics = self._measure_current_performance()
                if baseline_metrics is None:
                    raise Exception("베이스라인 성능 측정 실패")

                baseline_metrics.session_id = session_id
                self.performance_tracker.save_performance_result(
                    baseline_metrics, round_number, is_baseline=True
                )

                self.logger.info(f"베이스라인 성능: 평균 매치 {baseline_metrics.avg_matches:.3f}")

                # 그리드 서치 최적화
                grid_results = self.auto_optimizer.grid_search_optimization(
                    baseline_metrics, max_tests=25
                )

                # 베이지안 최적화 (그리드 서치에서 개선이 있었을 때만)
                best_improvement = grid_results['best_result']['improvement']

                if best_improvement > 0.01:  # 1% 이상 개선 시
                    self.logger.info("그리드 서치에서 개선 발견, 베이지안 최적화 진행")
                    bayesian_results = self.auto_optimizer.bayesian_optimization(
                        baseline_metrics, n_trials=15
                    )

                    # 더 나은 결과 선택
                    if bayesian_results['improvement'] > best_improvement:
                        best_params = bayesian_results['best_params']
                        best_performance = bayesian_results['best_performance']
                        final_improvement = bayesian_results['improvement']
                        optimization_method = 'bayesian'
                    else:
                        best_params = grid_results['best_result']['params']
                        best_performance = grid_results['best_result']['performance']
                        final_improvement = best_improvement
                        optimization_method = 'grid_search'
                else:
                    best_params = grid_results['best_result']['params']
                    best_performance = grid_results['best_result']['performance']
                    final_improvement = best_improvement
                    optimization_method = 'grid_search'

                # 개선 여부 확인 및 적용
                improvement_applied = False
                rollback_reason = None

                if final_improvement > 0:  # 조금이라도 개선되면 즉시 적용
                    try:
                        self._apply_optimization_results(best_params)
                        improvement_applied = True

                        self.logger.info(f"최적화 결과 적용 완료:")
                        self.logger.info(f"  - 임계값: {best_params['threshold']}")
                        self.logger.info(f"  - ML 바이패스: {best_params.get('ml_bypass', 'N/A')}")
                        self.logger.info(f"  - ML 가중치: {best_params.get('ml_weight', 'N/A')}")
                        self.logger.info(f"  - 성능 개선: {final_improvement:+.3f} ({final_improvement/baseline_metrics.avg_matches:.1%})")

                    except Exception as e:
                        self.logger.error(f"최적화 결과 적용 실패: {e}")
                        rollback_reason = f"적용 실패: {e}"
                        improvement_applied = False
                else:
                    rollback_reason = f"개선 없음: {final_improvement:.3f} <= 0"
                    self.logger.info(f"개선이 없어 현재 설정 유지 ({final_improvement:+.3f})")

                # 세션 완료
                self._complete_optimization_session(
                    session_id, best_params, best_performance,
                    baseline_metrics.avg_matches, final_improvement,
                    improvement_applied, rollback_reason, grid_results['total_tests']
                )

                self.status = OptimizationStatus.COMPLETED

                return {
                    'status': 'completed',
                    'session_id': session_id,
                    'baseline_performance': baseline_metrics.avg_matches,
                    'best_performance': best_performance,
                    'improvement_rate': final_improvement / baseline_metrics.avg_matches if baseline_metrics.avg_matches > 0 else 0,
                    'improvement_applied': improvement_applied,
                    'optimization_method': optimization_method,
                    'tests_completed': grid_results['total_tests'],
                    'best_params': best_params,
                    'rollback_reason': rollback_reason
                }

            except Exception as e:
                self.logger.error(f"최적화 사이클 실행 실패: {e}")
                self.status = OptimizationStatus.FAILED

                if self.current_session_id:
                    self._fail_optimization_session(self.current_session_id, str(e))

                return {
                    'status': 'failed',
                    'error': str(e)
                }

            finally:
                self.current_session_id = None

    def trigger_emergency_optimization(self):
        """긴급 최적화 트리거"""
        self.logger.warning("긴급 최적화 시작: 성능 저하 감지")

        # 백그라운드에서 최적화 실행
        threading.Thread(
            target=lambda: self.run_optimization_cycle(session_type='emergency'),
            daemon=True
        ).start()

    def _measure_current_performance(self) -> Optional[PerformanceMetrics]:
        """현재 설정으로 성능 측정"""
        try:
            # 백테스팅 실행
            backtesting = OptimizedBacktestingFramework(self.db_manager)
            latest_round = self.db_manager.get_latest_round()

            # ✅ FIX: latest_round는 이미 발표된 회차이므로 제외 (데이터 오염 방지)
            # 최신 회차를 학습 데이터로 사용하지 않도록 end_round = latest_round - 1
            end_round = latest_round - 1  # 최신 회차 제외
            start_round = max(1, end_round - 29)  # 30회차 테스트 (end_round 기준)

            if end_round < start_round or start_round < 1:
                self.logger.error(f"백테스팅 범위 오류: start={start_round}, end={end_round}")
                return None

            result = backtesting.run_backtest(
                start_round=start_round,
                end_round=end_round
            )

            # 성능 지표 추출
            performance_metrics = result.get('performance_metrics', {})
            avg_matches = performance_metrics.get('overall_avg_matches', 0)

            # 모델별 최고 성능 찾기
            model_performance = performance_metrics.get('model_performance', {})
            best_match = 0
            accuracy_3plus = 0

            for model_name, model_metrics in model_performance.items():
                best_match = max(best_match, model_metrics.get('best_match', 0))
                accuracy_3plus = max(accuracy_3plus, model_metrics.get('accuracy_3plus', 0))

            # ✅ FIX: overall_filter_pass_rate 추출 (백테스팅 결과에서)
            # performance_metrics 내부에 overall_filter_pass_rate가 있음
            performance_metrics = result.get('performance_metrics', {})
            overall_filter_pass_rate = performance_metrics.get('overall_filter_pass_rate', 0.0)

            return PerformanceMetrics(
                avg_matches=avg_matches,
                best_match=best_match,
                accuracy_3plus=accuracy_3plus,
                ml_inclusion_rate=result.get('ml_inclusion_rate', 0),
                combination_count=result.get('combination_count', 0),
                threshold=self.config.get('global_probability_threshold', 1.0),
                ml_bypass_filters=self.config.get('ml_integration', {}).get('ml_bypass_filters', 8),
                ml_weight=self.config.get('ml_integration', {}).get('ml_weight', 0.4),
                filter_pass_rate=overall_filter_pass_rate,  # ✅ FIX: 전체 필터 통과율 사용
                timestamp=datetime.now()
            )

        except Exception as e:
            self.logger.error(f"현재 성능 측정 실패: {e}")
            return None

    def _apply_optimization_results(self, best_params: Dict):
        """
        최적화 결과 적용

        FIX: FilterAutoAdjuster가 저장한 dynamic_criteria 보존
        """
        # ✅ FIX: 최신 설정 파일 다시 로드 (FilterAutoAdjuster 조정값 반영)
        # 메모리 캐시(self.config) 대신 파일에서 직접 로드
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"설정 파일 로드 실패: {e}")
            current_config = self.config.copy()

        # 기존 dynamic_criteria 확인 및 로깅
        has_dynamic_criteria = 'dynamic_criteria' in current_config
        if has_dynamic_criteria:
            self.logger.info("[ContinuousImprovementEngine] dynamic_criteria 발견 - 보존됨")

        # ✅ FIX: global_probability_threshold만 업데이트 (dynamic_criteria 보존)
        # ✅ PRECISION FIX: round()로 부동소수점 오차 제거
        old_threshold = current_config.get('global_probability_threshold', 1.0)
        current_config['global_probability_threshold'] = round(best_params['threshold'], 2)
        self.logger.info(
            f"[ContinuousImprovementEngine] global_probability_threshold: "
            f"{old_threshold} → {round(best_params['threshold'], 2)}"
        )

        # ML 통합 설정 업데이트
        if 'ml_integration' not in current_config:
            current_config['ml_integration'] = {}

        if 'ml_bypass' in best_params:
            current_config['ml_integration']['ml_bypass_filters'] = best_params['ml_bypass']

        if 'ml_weight' in best_params:
            current_config['ml_integration']['ml_weight'] = round(best_params['ml_weight'], 2)

        # ✅ FIX: 설정 저장 (dynamic_criteria 보존됨)
        self._save_config(current_config, backup=True)

    def _start_optimization_session(self, round_number: int, session_type: str) -> int:
        """최적화 세션 시작"""
        with sqlite3.connect(self.improvement_db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO optimization_sessions
                (round_number, session_type, start_time, status)
                VALUES (?, ?, ?, ?)
            """, (round_number, session_type, datetime.now().isoformat(), 'running'))

            session_id = cursor.lastrowid
            conn.commit()

            return session_id

    def _complete_optimization_session(self, session_id: int, best_params: Dict,
                                     best_performance: float, baseline_performance: float,
                                     improvement_rate: float, applied: bool,
                                     rollback_reason: str, tests_count: int):
        """최적화 세션 완료"""
        with sqlite3.connect(self.improvement_db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE optimization_sessions SET
                    end_time = ?,
                    status = ?,
                    tests_count = ?,
                    improvements_found = ?,
                    best_threshold = ?,
                    best_ml_bypass = ?,
                    best_ml_weight = ?,
                    best_performance = ?,
                    baseline_performance = ?,
                    improvement_rate = ?,
                    applied = ?,
                    rollback_reason = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                tests_count,
                1 if improvement_rate > 0 else 0,
                best_params.get('threshold'),
                best_params.get('ml_bypass'),
                best_params.get('ml_weight'),
                best_performance,
                baseline_performance,
                improvement_rate,
                applied,
                rollback_reason,
                session_id
            ))

            conn.commit()

    def _fail_optimization_session(self, session_id: int, error_message: str):
        """최적화 세션 실패 처리"""
        with sqlite3.connect(self.improvement_db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE optimization_sessions SET
                    end_time = ?,
                    status = ?,
                    rollback_reason = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'failed',
                error_message,
                session_id
            ))

            conn.commit()

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 조회"""
        # 최근 세션 정보
        with sqlite3.connect(self.improvement_db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM optimization_sessions
                ORDER BY created_at DESC LIMIT 1
            """)

            last_session = cursor.fetchone()

        # 성능 추이
        trends = self.performance_tracker.get_performance_trends(days=7)
        best_performance = self.performance_tracker.get_best_performance()

        return {
            'status': self.status.value,
            'is_running': self.is_running,
            'current_session_id': self.current_session_id,
            'last_session': dict(zip([
                'id', 'round_number', 'session_type', 'start_time', 'end_time',
                'status', 'tests_count', 'improvements_found', 'best_threshold',
                'best_ml_bypass', 'best_ml_weight', 'best_performance',
                'baseline_performance', 'improvement_rate', 'applied',
                'rollback_reason', 'created_at'
            ], last_session)) if last_session else None,
            'performance_trends': trends[:5],  # 최근 5일
            'best_performance_ever': {
                'avg_matches': best_performance.avg_matches,
                'threshold': best_performance.threshold,
                'ml_bypass_filters': best_performance.ml_bypass_filters,
                'ml_weight': best_performance.ml_weight,
                'timestamp': best_performance.timestamp.isoformat()
            } if best_performance else None,
            'current_config': {
                'threshold': self.config.get('global_probability_threshold', 1.0),
                'ml_bypass_filters': self.config.get('ml_integration', {}).get('ml_bypass_filters', 8),
                'ml_weight': self.config.get('ml_integration', {}).get('ml_weight', 0.4)
            }
        }

    def manual_optimization(self) -> Dict[str, Any]:
        """수동 최적화 실행"""
        self.logger.info("수동 최적화 시작")
        return self.run_optimization_cycle(session_type='manual')

    def rollback_to_best(self) -> bool:
        """최고 성능 설정으로 롤백"""
        try:
            best_performance = self.performance_tracker.get_best_performance()
            if best_performance is None:
                self.logger.warning("롤백할 최고 성능 기록이 없습니다.")
                return False

            # 최고 성능 파라미터로 설정 업데이트
            best_params = {
                'threshold': best_performance.threshold,
                'ml_bypass': best_performance.ml_bypass_filters,
                'ml_weight': best_performance.ml_weight
            }

            self._apply_optimization_results(best_params)

            self.logger.info(f"최고 성능 설정으로 롤백 완료:")
            self.logger.info(f"  - 평균 매치: {best_performance.avg_matches:.3f}")
            self.logger.info(f"  - 임계값: {best_performance.threshold}")
            self.logger.info(f"  - ML 바이패스: {best_performance.ml_bypass_filters}")
            self.logger.info(f"  - ML 가중치: {best_performance.ml_weight}")

            return True

        except Exception as e:
            self.logger.error(f"최고 성능 설정 롤백 실패: {e}")
            return False

    def rollback_to_best_pass_rate(self) -> bool:
        """✅ NEW: 최고 필터 통과율 설정으로 롤백"""
        try:
            best_pass_rate_perf = self.performance_tracker.get_best_pass_rate_performance()
            if best_pass_rate_perf is None:
                self.logger.warning("롤백할 최고 필터 통과율 기록이 없습니다.")
                return False

            # 1. Threshold/ML 파라미터 롤백
            best_params = {
                'threshold': best_pass_rate_perf.threshold,
                'ml_bypass': best_pass_rate_perf.ml_bypass_filters,
                'ml_weight': best_pass_rate_perf.ml_weight
            }

            self._apply_optimization_results(best_params)

            # 2. 필터 조건 스냅샷 복원
            import sqlite3
            with sqlite3.connect(self.performance_tracker.db_path) as conn:
                cursor = conn.cursor()

                # 최고 통과율 기록의 performance_history ID 찾기
                cursor.execute("""
                    SELECT id FROM performance_history
                    WHERE is_best_pass_rate = TRUE
                    ORDER BY filter_pass_rate DESC LIMIT 1
                """)
                result = cursor.fetchone()

                if result:
                    performance_history_id = result[0]

                    # 필터 조건 스냅샷 복원
                    filter_criteria = self.performance_tracker.get_filter_criteria_snapshot(performance_history_id)

                    if filter_criteria:
                        # adaptive_filter_config.yaml 업데이트
                        import yaml
                        adaptive_config_path = "configs/adaptive_filter_config.yaml"

                        with open(adaptive_config_path, 'r', encoding='utf-8') as f:
                            adaptive_config = yaml.safe_load(f)

                        # dynamic_criteria 복원
                        if 'dynamic_criteria' not in adaptive_config:
                            adaptive_config['dynamic_criteria'] = {}

                        adaptive_config['dynamic_criteria'].update(filter_criteria)

                        # 저장
                        with open(adaptive_config_path, 'w', encoding='utf-8') as f:
                            yaml.dump(adaptive_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

                        self.logger.info(f"✅ 필터 조건 스냅샷 복원 완료 ({len(filter_criteria)}개 필터)")

            self.logger.info(f"최고 필터 통과율 설정으로 롤백 완료:")
            self.logger.info(f"  - 필터 통과율: {best_pass_rate_perf.filter_pass_rate:.2f}%")
            self.logger.info(f"  - 평균 매치: {best_pass_rate_perf.avg_matches:.3f}")
            self.logger.info(f"  - 임계값: {best_pass_rate_perf.threshold}")
            self.logger.info(f"  - ML 바이패스: {best_pass_rate_perf.ml_bypass_filters}")
            self.logger.info(f"  - ML 가중치: {best_pass_rate_perf.ml_weight}")

            return True

        except Exception as e:
            self.logger.error(f"최고 필터 통과율 설정 롤백 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def _apply_config_to_framework(self, framework: 'OptimizedBacktestingFramework', config: Dict):
        """백테스팅 프레임워크에 설정 적용"""
        try:
            # 필터 매니저 설정 적용
            if hasattr(framework, 'filter_manager'):
                # 적응형 필터 임계값 설정
                if hasattr(framework.filter_manager, 'adaptive_filter'):
                    threshold = config.get('global_probability_threshold', 1.0)
                    framework.filter_manager.adaptive_filter.probability_threshold = threshold

                # 통합 필터 매니저인 경우
                elif hasattr(framework.filter_manager, 'set_config'):
                    framework.filter_manager.set_config(config)

            # ML 설정 적용
            ml_config = config.get('ml_integration', {})
            framework.ml_config = {
                'ml_bypass_filters': ml_config.get('ml_bypass_filters', 8),
                'ml_weight': ml_config.get('ml_weight', 0.4),
                'ml_relaxed_threshold': ml_config.get('ml_relaxed_threshold', 0.5)
            }

        except Exception as e:
            self.logger.warning(f"설정 적용 중 오류: {e}")