"""
최적화 진행상황 체크포인트 관리 시스템 (DEPRECATED)

⚠️ DEPRECATION WARNING:
   이 Grid Search 기반 체크포인트 시스템은 더 이상 사용되지 않습니다.
   Optuna TPE 기반 최적화(ThresholdOptimizer.optimize())를 사용하세요.

   Grid Search 방식 (이 파일):
   - 하드코딩된 140개 조합 순차 테스트
   - 지능적 파라미터 탐색 없음
   - 단순 체크포인트 기반 재개

   Optuna 방식 (권장):
   - Bayesian 최적화로 지능적 파라미터 탐색
   - SQLite 기반 persistence (자동 pause/resume)
   - TPE sampler로 이전 trial 학습
   - 누적 학습으로 효율적 최적화

중단된 최적화를 이어서 실행할 수 있도록 진행상황을 저장하고 관리
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import sqlite3

class OptimizationCheckpointManager:
    """
    최적화 진행상황 체크포인트 관리자 (DEPRECATED)

    ⚠️ 이 클래스는 더 이상 사용되지 않습니다.
    대신 Optuna TPE 기반 최적화를 사용하세요:
    - ThresholdOptimizer.optimize() - Bayesian 최적화
    - AutoThresholdOptimizer.optimize_with_optuna() - 고수준 인터페이스
    """

    def __init__(self):
        import warnings
        warnings.warn(
            "OptimizationCheckpointManager는 deprecated입니다. "
            "Optuna TPE 기반 최적화(AutoThresholdOptimizer.optimize_with_optuna)를 사용하세요.",
            DeprecationWarning,
            stacklevel=2
        )
        self.checkpoint_file = "data/optimization_checkpoint.json"
        self.progress_db = "data/optimization_progress.db"
        self.logger = logging.getLogger(__name__)

        # 체크포인트 데이터 구조
        self.checkpoint = {
            'version': '1.0',
            'created_at': None,
            'last_updated': None,
            'last_lottery_round': None,  # 마지막 로또 회차
            'current_optimization': {
                'session_id': None,
                'start_time': None,
                'current_threshold': None,
                'current_ml_bypass': None,
                'current_ml_weight': None,
                'completed_trials': [],
                'pending_trials': [],
                'total_trials_planned': 0,
                'best_score_so_far': 0,
                'best_params_so_far': {}
            },
            'optimization_grid': {
                'thresholds': [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5],
                'ml_bypasses': [5, 8, 11, 12, 15],
                'ml_weights': [0.3, 0.4, 0.5, 0.6]
            },
            'completed_combinations': [],  # 완료된 (threshold, ml_bypass, ml_weight) 조합
            'results_history': []  # 모든 테스트 결과 이력
        }

        # 데이터베이스 초기화
        self._init_progress_db()

        # 체크포인트 로드
        self.load_checkpoint()

    def _init_progress_db(self):
        """진행상황 추적용 데이터베이스 초기화"""
        os.makedirs(os.path.dirname(self.progress_db), exist_ok=True)

        with sqlite3.connect(self.progress_db) as conn:
            cursor = conn.cursor()

            # 최적화 세션 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimization_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    lottery_round INTEGER,
                    start_time TEXT,
                    end_time TEXT,
                    total_trials INTEGER,
                    completed_trials INTEGER,
                    status TEXT DEFAULT 'running',
                    best_score REAL,
                    best_threshold REAL,
                    best_ml_bypass INTEGER,
                    best_ml_weight REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 개별 테스트 결과 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trial_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    trial_number INTEGER,
                    threshold REAL,
                    ml_bypass INTEGER,
                    ml_weight REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    score REAL,
                    execution_time REAL,
                    completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES optimization_sessions (session_id)
                )
            """)

            # 로또 회차 추적 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lottery_round_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_number INTEGER UNIQUE NOT NULL,
                    first_seen_at TEXT,
                    optimization_reset BOOLEAN DEFAULT FALSE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def load_checkpoint(self) -> Dict[str, Any]:
        """체크포인트 파일 로드"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    loaded_checkpoint = json.load(f)

                # 버전 체크 및 마이그레이션
                if loaded_checkpoint.get('version') == self.checkpoint['version']:
                    self.checkpoint = loaded_checkpoint
                    self.logger.info(f"체크포인트 로드 완료. 완료된 조합: {len(self.checkpoint['completed_combinations'])}개")
                else:
                    self.logger.warning("체크포인트 버전 불일치. 새로 시작합니다.")
                    self.save_checkpoint()
            except Exception as e:
                self.logger.error(f"체크포인트 로드 실패: {e}")
                self.save_checkpoint()
        else:
            self.logger.info("새로운 체크포인트 파일 생성")
            self.checkpoint['created_at'] = datetime.now().isoformat()
            self.save_checkpoint()

        return self.checkpoint

    def save_checkpoint(self):
        """체크포인트 저장"""
        try:
            self.checkpoint['last_updated'] = datetime.now().isoformat()

            # 디렉토리 생성
            os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)

            # 파일 저장
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint, f, indent=2, ensure_ascii=False)

            self.logger.info("체크포인트 저장 완료")

        except Exception as e:
            self.logger.error(f"체크포인트 저장 실패: {e}")

    def check_lottery_update(self, current_round: int) -> bool:
        """
        로또 회차 업데이트 확인

        Args:
            current_round: 현재 로또 회차 번호

        Returns:
            bool: 새로운 회차이면 True, 기존 회차면 False
        """
        last_round = self.checkpoint.get('last_lottery_round')

        if last_round is None:
            # 처음 실행
            self.checkpoint['last_lottery_round'] = current_round
            self.save_checkpoint()
            self._track_lottery_round(current_round, reset=True)
            return True

        if current_round > last_round:
            # 새로운 회차 발견
            self.logger.info(f"🎯 새로운 로또 회차 발견: {last_round} → {current_round}")
            self.checkpoint['last_lottery_round'] = current_round

            # 최적화 진행상황 초기화
            self.reset_optimization_progress()
            self._track_lottery_round(current_round, reset=True)
            return True

        return False

    def _track_lottery_round(self, round_number: int, reset: bool = False):
        """로또 회차 추적"""
        with sqlite3.connect(self.progress_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO lottery_round_tracking
                (round_number, first_seen_at, optimization_reset)
                VALUES (?, ?, ?)
            """, (round_number, datetime.now().isoformat(), reset))

            conn.commit()

    def reset_optimization_progress(self):
        """최적화 진행상황 초기화 (새 로또 회차 시작)"""
        self.logger.info("최적화 진행상황 초기화 중...")

        # 기존 세션 종료
        if self.checkpoint['current_optimization']['session_id']:
            self._close_session(self.checkpoint['current_optimization']['session_id'])

        # 체크포인트 초기화
        self.checkpoint['current_optimization'] = {
            'session_id': None,
            'start_time': None,
            'current_threshold': None,
            'current_ml_bypass': None,
            'current_ml_weight': None,
            'completed_trials': [],
            'pending_trials': [],
            'total_trials_planned': 0,
            'best_score_so_far': 0,
            'best_params_so_far': {}
        }
        self.checkpoint['completed_combinations'] = []
        self.checkpoint['results_history'] = []

        self.save_checkpoint()
        self.logger.info("최적화 진행상황 초기화 완료")

    def get_next_combination(self) -> Optional[Tuple[float, int, float]]:
        """
        다음에 테스트할 조합 반환

        Returns:
            (threshold, ml_bypass, ml_weight) 또는 None (모두 완료)
        """
        grid = self.checkpoint['optimization_grid']
        completed = set(map(tuple, self.checkpoint['completed_combinations']))

        # 모든 가능한 조합 생성
        for threshold in grid['thresholds']:
            for ml_bypass in grid['ml_bypasses']:
                for ml_weight in grid['ml_weights']:
                    combination = (threshold, ml_bypass, ml_weight)
                    if combination not in completed:
                        return combination

        return None

    def mark_combination_complete(
        self,
        threshold: float,
        ml_bypass: int,
        ml_weight: float,
        result: Dict[str, Any]
    ):
        """
        조합 테스트 완료 표시

        Args:
            threshold: 테스트한 임계값
            ml_bypass: ML 바이패스 필터 수
            ml_weight: ML 가중치
            result: 테스트 결과
        """
        combination = [threshold, ml_bypass, ml_weight]

        # 완료된 조합 추가
        if combination not in self.checkpoint['completed_combinations']:
            self.checkpoint['completed_combinations'].append(combination)

        # 결과 기록
        result_record = {
            'timestamp': datetime.now().isoformat(),
            'threshold': threshold,
            'ml_bypass': ml_bypass,
            'ml_weight': ml_weight,
            'avg_matches': result.get('avg_matches', 0),
            'ml_inclusion_rate': result.get('ml_inclusion_rate', 0),
            'combination_count': result.get('combination_count', 0),
            'score': result.get('score', 0)
        }
        self.checkpoint['results_history'].append(result_record)

        # 최고 점수 업데이트
        if result.get('score', 0) > self.checkpoint['current_optimization']['best_score_so_far']:
            self.checkpoint['current_optimization']['best_score_so_far'] = result['score']
            self.checkpoint['current_optimization']['best_params_so_far'] = {
                'threshold': threshold,
                'ml_bypass': ml_bypass,
                'ml_weight': ml_weight
            }

        # 데이터베이스에 저장
        self._save_trial_result(
            self.checkpoint['current_optimization']['session_id'],
            len(self.checkpoint['completed_combinations']),
            threshold, ml_bypass, ml_weight, result
        )

        self.save_checkpoint()

        # 진행상황 로깅
        total_combinations = (
            len(self.checkpoint['optimization_grid']['thresholds']) *
            len(self.checkpoint['optimization_grid']['ml_bypasses']) *
            len(self.checkpoint['optimization_grid']['ml_weights'])
        )
        progress = len(self.checkpoint['completed_combinations']) / total_combinations * 100

        self.logger.info(
            f"테스트 {len(self.checkpoint['completed_combinations'])}/{total_combinations} "
            f"({progress:.1f}%): 임계값={threshold}, ML바이패스={ml_bypass}, ML가중치={ml_weight} "
            f"→ 평균매치={result.get('avg_matches', 0):.3f} (점수: {result.get('score', 0):.3f})"
        )

    def _save_trial_result(
        self,
        session_id: str,
        trial_number: int,
        threshold: float,
        ml_bypass: int,
        ml_weight: float,
        result: Dict[str, Any]
    ):
        """테스트 결과를 데이터베이스에 저장"""
        if not session_id:
            return

        with sqlite3.connect(self.progress_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO trial_results
                (session_id, trial_number, threshold, ml_bypass, ml_weight,
                 avg_matches, ml_inclusion_rate, combination_count, score, execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                trial_number,
                threshold,
                ml_bypass,
                ml_weight,
                result.get('avg_matches', 0),
                result.get('ml_inclusion_rate', 0),
                result.get('combination_count', 0),
                result.get('score', 0),
                result.get('execution_time', 0)
            ))

            # 세션 정보 업데이트
            cursor.execute("""
                UPDATE optimization_sessions
                SET completed_trials = ?,
                    best_score = ?,
                    best_threshold = ?,
                    best_ml_bypass = ?,
                    best_ml_weight = ?
                WHERE session_id = ?
            """, (
                trial_number,
                self.checkpoint['current_optimization']['best_score_so_far'],
                self.checkpoint['current_optimization']['best_params_so_far'].get('threshold'),
                self.checkpoint['current_optimization']['best_params_so_far'].get('ml_bypass'),
                self.checkpoint['current_optimization']['best_params_so_far'].get('ml_weight'),
                session_id
            ))

            conn.commit()

    def start_optimization_session(self, lottery_round: int) -> str:
        """
        새 최적화 세션 시작

        Args:
            lottery_round: 현재 로또 회차

        Returns:
            session_id: 세션 ID
        """
        session_id = f"opt_{lottery_round}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.checkpoint['current_optimization']['session_id'] = session_id
        self.checkpoint['current_optimization']['start_time'] = datetime.now().isoformat()

        # 총 계획된 테스트 수 계산
        total_trials = (
            len(self.checkpoint['optimization_grid']['thresholds']) *
            len(self.checkpoint['optimization_grid']['ml_bypasses']) *
            len(self.checkpoint['optimization_grid']['ml_weights'])
        )
        self.checkpoint['current_optimization']['total_trials_planned'] = total_trials

        # 데이터베이스에 세션 생성
        with sqlite3.connect(self.progress_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO optimization_sessions
                (session_id, lottery_round, start_time, total_trials, status)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, lottery_round, datetime.now().isoformat(), total_trials, 'running'))

            conn.commit()

        self.save_checkpoint()
        self.logger.info(f"새 최적화 세션 시작: {session_id} (총 {total_trials}개 테스트 계획)")

        return session_id

    def _close_session(self, session_id: str):
        """세션 종료"""
        if not session_id:
            return

        with sqlite3.connect(self.progress_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE optimization_sessions
                SET end_time = ?, status = ?
                WHERE session_id = ?
            """, (datetime.now().isoformat(), 'completed', session_id))

            conn.commit()

    def get_progress_summary(self) -> Dict[str, Any]:
        """진행상황 요약 반환"""
        total_combinations = (
            len(self.checkpoint['optimization_grid']['thresholds']) *
            len(self.checkpoint['optimization_grid']['ml_bypasses']) *
            len(self.checkpoint['optimization_grid']['ml_weights'])
        )

        completed = len(self.checkpoint['completed_combinations'])
        progress = completed / total_combinations * 100 if total_combinations > 0 else 0

        return {
            'total_combinations': total_combinations,
            'completed_combinations': completed,
            'remaining_combinations': total_combinations - completed,
            'progress_percentage': progress,
            'current_session': self.checkpoint['current_optimization']['session_id'],
            'best_score': self.checkpoint['current_optimization']['best_score_so_far'],
            'best_params': self.checkpoint['current_optimization']['best_params_so_far'],
            'last_lottery_round': self.checkpoint.get('last_lottery_round'),
            'last_updated': self.checkpoint.get('last_updated')
        }

    def should_continue_optimization(self) -> bool:
        """최적화를 계속해야 하는지 확인"""
        # 남은 조합이 있는지 확인
        return self.get_next_combination() is not None

    def get_optimization_report(self) -> str:
        """최적화 진행상황 리포트 생성"""
        summary = self.get_progress_summary()

        report = []
        report.append("\n" + "="*60)
        report.append("📊 최적화 진행상황 리포트")
        report.append("="*60)

        report.append(f"\n✅ 진행률: {summary['completed_combinations']}/{summary['total_combinations']} "
                     f"({summary['progress_percentage']:.1f}%)")
        report.append(f"🎯 현재 로또 회차: {summary['last_lottery_round']}")
        report.append(f"🏃 현재 세션: {summary['current_session']}")

        if summary['best_params']:
            report.append(f"\n🏆 현재까지 최적 파라미터:")
            report.append(f"  • 임계값: {summary['best_params'].get('threshold')}%")
            report.append(f"  • ML 바이패스: {summary['best_params'].get('ml_bypass')}개")
            report.append(f"  • ML 가중치: {summary['best_params'].get('ml_weight')}")
            report.append(f"  • 점수: {summary['best_score']:.3f}")

        # 최근 5개 테스트 결과
        if self.checkpoint['results_history']:
            report.append(f"\n📈 최근 테스트 결과:")
            for result in self.checkpoint['results_history'][-5:]:
                report.append(
                    f"  • T={result['threshold']:.1f}, B={result['ml_bypass']}, "
                    f"W={result['ml_weight']:.2f} → 매치={result['avg_matches']:.3f}, "
                    f"점수={result['score']:.3f}"
                )

        report.append(f"\n⏰ 마지막 업데이트: {summary['last_updated']}")
        report.append("="*60)

        return '\n'.join(report)


# 싱글톤 인스턴스
_checkpoint_manager = None

def get_checkpoint_manager() -> OptimizationCheckpointManager:
    """체크포인트 관리자 싱글톤 인스턴스 반환"""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = OptimizationCheckpointManager()
    return _checkpoint_manager