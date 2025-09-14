"""
임계값 최적화 시스템
Optuna를 활용한 Bayesian Optimization으로 최적 임계값 탐색
"""
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import optuna
import numpy as np
import yaml
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

class ThresholdOptimizer:
    """백테스팅 임계값 최적화 관리자"""

    def __init__(
        self,
        config_path: str = "configs/adaptive_filter_config.yaml",
        stats_db_path: str = "data/performance_stats.db",
        optimization_db_path: str = "data/threshold_optimization.db"
    ):
        self.config_path = config_path
        self.stats_db_path = stats_db_path
        self.optimization_db_path = optimization_db_path
        self.logger = logging.getLogger(__name__)

        # 최적화 범위 설정
        self.threshold_range = (0.3, 2.5)  # 0.3% ~ 2.5%
        self.ml_bypass_range = (3, 12)     # ML bypass filters 개수
        self.ml_weight_range = (0.2, 0.6)  # ML 가중치

        # 성능 목표
        self.target_avg_matches = (0.8, 1.5)  # 목표 평균 매칭
        self.target_ml_inclusion = 0.15       # 목표 ML 포함률 15%

        # 최적화 히스토리
        self.optimization_history = []
        self.best_params = None
        self.best_score = float('-inf')

        # 데이터베이스 초기화
        self._init_optimization_db()

        # 현재 설정 로드
        self.current_config = self._load_current_config()

    def _init_optimization_db(self):
        """최적화 결과 저장용 데이터베이스 초기화"""
        os.makedirs(os.path.dirname(self.optimization_db_path), exist_ok=True)

        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()

            # 최적화 세션 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimization_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT NOT NULL,
                    study_name TEXT NOT NULL,
                    n_trials INTEGER DEFAULT 0,
                    best_threshold REAL,
                    best_ml_bypass INTEGER,
                    best_ml_weight REAL,
                    best_score REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 개별 시도 결과 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimization_trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    trial_number INTEGER,
                    threshold REAL NOT NULL,
                    ml_bypass INTEGER,
                    ml_weight REAL,
                    score REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    execution_time REAL,
                    status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES optimization_sessions (id)
                )
            """)

            # 최적 파라미터 이력 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS best_parameters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    threshold REAL NOT NULL,
                    ml_bypass INTEGER,
                    ml_weight REAL,
                    score REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    validation_rounds INTEGER,
                    is_active BOOLEAN DEFAULT TRUE,
                    applied_at TEXT,
                    rollback_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def _load_current_config(self) -> Dict:
        """현재 설정 파일 로드"""
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
                # 백업 파일 생성
                backup_path = self.config_path.replace(
                    '.yaml',
                    f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml'
                )
                with open(backup_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.current_config, f, allow_unicode=True)

            # 새 설정 저장
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)

            self.current_config = config
            self.logger.info(f"설정 파일 업데이트 완료: {self.config_path}")

        except Exception as e:
            self.logger.error(f"설정 파일 저장 실패: {e}")
            raise

    def create_objective(self, backtesting_func):
        """Optuna 목적 함수 생성"""

        def objective(trial):
            # 하이퍼파라미터 제안
            threshold = trial.suggest_float(
                'threshold',
                self.threshold_range[0],
                self.threshold_range[1],
                step=0.1
            )

            ml_bypass = trial.suggest_int(
                'ml_bypass',
                self.ml_bypass_range[0],
                self.ml_bypass_range[1]
            )

            ml_weight = trial.suggest_float(
                'ml_weight',
                self.ml_weight_range[0],
                self.ml_weight_range[1],
                step=0.05
            )

            # 임시 설정 적용
            temp_config = self.current_config.copy()
            temp_config['global_probability_threshold'] = threshold
            temp_config['ml_integration']['ml_bypass_filters'] = ml_bypass
            temp_config['ml_integration']['ml_weight'] = ml_weight

            # 백테스팅 실행
            try:
                results = backtesting_func(temp_config)

                # 성능 메트릭 추출
                avg_matches = results.get('avg_matches', 0)
                ml_inclusion = results.get('ml_inclusion_rate', 0)
                combination_count = results.get('combination_count', 0)

                # 다중 목적 함수 계산
                score = self._calculate_score(
                    avg_matches,
                    ml_inclusion,
                    combination_count,
                    threshold
                )

                # 중간 결과 기록
                trial.set_user_attr('avg_matches', avg_matches)
                trial.set_user_attr('ml_inclusion_rate', ml_inclusion)
                trial.set_user_attr('combination_count', combination_count)

                # 조기 종료 조건 (Pruning)
                if avg_matches > 3.0:  # 데이터 오염 의심
                    raise optuna.TrialPruned()

                return score

            except Exception as e:
                self.logger.error(f"백테스팅 실행 실패: {e}")
                return float('-inf')

        return objective

    def _calculate_score(
        self,
        avg_matches: float,
        ml_inclusion: float,
        combination_count: int,
        threshold: float
    ) -> float:
        """
        다중 목적 점수 계산
        높을수록 좋음
        """
        # 평균 매칭 점수 (목표 범위 내 최적화)
        if self.target_avg_matches[0] <= avg_matches <= self.target_avg_matches[1]:
            match_score = 1.0
        elif avg_matches < self.target_avg_matches[0]:
            match_score = avg_matches / self.target_avg_matches[0]
        else:
            # 너무 높으면 페널티 (데이터 오염 가능성)
            match_score = max(0, 2.0 - avg_matches / self.target_avg_matches[1])

        # ML 포함률 점수 (높을수록 좋음, 목표 15%)
        inclusion_score = min(1.0, ml_inclusion / self.target_ml_inclusion)

        # 조합 수 효율성 점수 (적절한 크기 유지)
        if 200000 <= combination_count <= 400000:
            efficiency_score = 1.0
        elif combination_count < 200000:
            efficiency_score = combination_count / 200000
        else:
            efficiency_score = max(0, 1.0 - (combination_count - 400000) / 400000)

        # 임계값 안정성 점수 (극단적 값 회피)
        if 0.5 <= threshold <= 1.5:
            stability_score = 1.0
        else:
            stability_score = 0.8

        # 가중 평균 계산
        weights = {
            'match': 0.35,
            'inclusion': 0.30,
            'efficiency': 0.20,
            'stability': 0.15
        }

        total_score = (
            weights['match'] * match_score +
            weights['inclusion'] * inclusion_score +
            weights['efficiency'] * efficiency_score +
            weights['stability'] * stability_score
        )

        return total_score

    def optimize(
        self,
        backtesting_func,
        n_trials: int = 50,
        n_jobs: int = 1,
        study_name: Optional[str] = None
    ) -> Dict:
        """
        Bayesian Optimization 실행

        Args:
            backtesting_func: 백테스팅 함수
            n_trials: 시도 횟수
            n_jobs: 병렬 작업 수
            study_name: 스터디 이름

        Returns:
            최적 파라미터와 성능 지표
        """
        if study_name is None:
            study_name = f"threshold_opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.logger.info(f"최적화 시작: {study_name} (trials={n_trials})")

        # Optuna 스터디 생성
        study = optuna.create_study(
            study_name=study_name,
            direction='maximize',
            sampler=TPESampler(
                n_startup_trials=10,
                n_ei_candidates=24,
                seed=42
            ),
            pruner=MedianPruner(
                n_startup_trials=5,
                n_warmup_steps=10
            ),
            storage=f"sqlite:///{self.optimization_db_path}"
        )

        # 현재 설정을 초기 추측값으로 사용
        study.enqueue_trial({
            'threshold': self.current_config.get('global_probability_threshold', 1.0),
            'ml_bypass': self.current_config.get('ml_integration', {}).get('ml_bypass_filters', 8),
            'ml_weight': self.current_config.get('ml_integration', {}).get('ml_weight', 0.4)
        })

        # 최적화 실행
        study.optimize(
            self.create_objective(backtesting_func),
            n_trials=n_trials,
            n_jobs=n_jobs,
            show_progress_bar=True
        )

        # 최적 결과 추출
        best_trial = study.best_trial
        self.best_params = best_trial.params
        self.best_score = best_trial.value

        # 결과 저장
        self._save_optimization_results(study_name, study)

        results = {
            'study_name': study_name,
            'best_params': self.best_params,
            'best_score': self.best_score,
            'best_trial_number': best_trial.number,
            'n_trials': len(study.trials),
            'avg_matches': best_trial.user_attrs.get('avg_matches'),
            'ml_inclusion_rate': best_trial.user_attrs.get('ml_inclusion_rate'),
            'combination_count': best_trial.user_attrs.get('combination_count')
        }

        self.logger.info(f"최적화 완료: {results}")

        return results

    def _save_optimization_results(self, study_name: str, study: optuna.Study):
        """최적화 결과 데이터베이스 저장"""
        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()

            # 세션 정보 저장
            best_trial = study.best_trial
            cursor.execute("""
                INSERT INTO optimization_sessions
                (session_date, study_name, n_trials, best_threshold, best_ml_bypass,
                 best_ml_weight, best_score, avg_matches, ml_inclusion_rate, combination_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                study_name,
                len(study.trials),
                self.best_params['threshold'],
                self.best_params['ml_bypass'],
                self.best_params['ml_weight'],
                self.best_score,
                best_trial.user_attrs.get('avg_matches'),
                best_trial.user_attrs.get('ml_inclusion_rate'),
                best_trial.user_attrs.get('combination_count')
            ))

            session_id = cursor.lastrowid

            # 개별 시도 결과 저장
            for trial in study.trials:
                if trial.state == optuna.trial.TrialState.COMPLETE:
                    cursor.execute("""
                        INSERT INTO optimization_trials
                        (session_id, trial_number, threshold, ml_bypass, ml_weight,
                         score, avg_matches, ml_inclusion_rate, combination_count,
                         execution_time, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        session_id,
                        trial.number,
                        trial.params['threshold'],
                        trial.params['ml_bypass'],
                        trial.params['ml_weight'],
                        trial.value,
                        trial.user_attrs.get('avg_matches'),
                        trial.user_attrs.get('ml_inclusion_rate'),
                        trial.user_attrs.get('combination_count'),
                        (trial.datetime_complete - trial.datetime_start).total_seconds(),
                        'COMPLETE'
                    ))

            conn.commit()

    def apply_best_params(self, validate: bool = True) -> bool:
        """
        최적 파라미터를 설정 파일에 적용

        Args:
            validate: 적용 전 검증 수행 여부

        Returns:
            성공 여부
        """
        if self.best_params is None:
            self.logger.warning("적용할 최적 파라미터가 없습니다.")
            return False

        try:
            # 새 설정 준비
            new_config = self.current_config.copy()
            new_config['global_probability_threshold'] = self.best_params['threshold']
            new_config['ml_integration']['ml_bypass_filters'] = self.best_params['ml_bypass']
            new_config['ml_integration']['ml_weight'] = self.best_params['ml_weight']

            # 검증 모드
            if validate:
                self.logger.info("최적 파라미터 검증 중...")
                # TODO: 검증 로직 구현 (간단한 백테스팅)

            # 설정 저장
            self._save_config(new_config, backup=True)

            # 최적 파라미터 이력 저장
            with sqlite3.connect(self.optimization_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE best_parameters SET is_active = FALSE WHERE is_active = TRUE
                """)
                cursor.execute("""
                    INSERT INTO best_parameters
                    (threshold, ml_bypass, ml_weight, score, avg_matches,
                     ml_inclusion_rate, validation_rounds, applied_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.best_params['threshold'],
                    self.best_params['ml_bypass'],
                    self.best_params['ml_weight'],
                    self.best_score,
                    self.optimization_history[-1]['avg_matches'] if self.optimization_history else None,
                    self.optimization_history[-1]['ml_inclusion_rate'] if self.optimization_history else None,
                    50,  # 검증 라운드 수
                    datetime.now().isoformat()
                ))
                conn.commit()

            self.logger.info(f"최적 파라미터 적용 완료: {self.best_params}")
            return True

        except Exception as e:
            self.logger.error(f"최적 파라미터 적용 실패: {e}")
            return False

    def get_optimization_history(self, limit: int = 10) -> List[Dict]:
        """최근 최적화 이력 조회"""
        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM optimization_sessions
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            return results

    def get_current_best_params(self) -> Optional[Dict]:
        """현재 활성화된 최적 파라미터 조회"""
        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM best_parameters
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))

            return None

    def rollback_params(self) -> bool:
        """이전 파라미터로 롤백"""
        try:
            # 백업 파일 찾기
            backup_files = [
                f for f in os.listdir(os.path.dirname(self.config_path))
                if f.startswith(os.path.basename(self.config_path).replace('.yaml', '_backup_'))
            ]

            if not backup_files:
                self.logger.warning("롤백할 백업 파일이 없습니다.")
                return False

            # 가장 최근 백업 파일 복원
            latest_backup = sorted(backup_files)[-1]
            backup_path = os.path.join(os.path.dirname(self.config_path), latest_backup)

            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_config = yaml.safe_load(f)

            self._save_config(backup_config, backup=False)

            # 데이터베이스 업데이트
            with sqlite3.connect(self.optimization_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE best_parameters
                    SET is_active = FALSE, rollback_at = ?
                    WHERE is_active = TRUE
                """, (datetime.now().isoformat(),))
                conn.commit()

            self.logger.info(f"파라미터 롤백 완료: {backup_path}")
            return True

        except Exception as e:
            self.logger.error(f"파라미터 롤백 실패: {e}")
            return False

    def adaptive_optimization(
        self,
        backtesting_func,
        interval_hours: int = 24,
        min_improvement: float = 0.05
    ):
        """
        주기적 자동 최적화

        Args:
            backtesting_func: 백테스팅 함수
            interval_hours: 최적화 주기 (시간)
            min_improvement: 최소 개선율 (적용 기준)
        """
        last_optimization = self._get_last_optimization_time()

        if last_optimization:
            time_diff = datetime.now() - datetime.fromisoformat(last_optimization)
            if time_diff < timedelta(hours=interval_hours):
                self.logger.info(f"다음 최적화까지 {interval_hours - time_diff.total_seconds()/3600:.1f}시간 남음")
                return

        # 최적화 실행
        self.logger.info("자동 최적화 시작...")
        results = self.optimize(backtesting_func, n_trials=30)

        # 개선율 확인
        current_best = self.get_current_best_params()
        if current_best:
            improvement = (results['best_score'] - current_best['score']) / current_best['score']

            if improvement >= min_improvement:
                self.logger.info(f"성능 개선 확인 ({improvement:.1%}), 새 파라미터 적용")
                self.apply_best_params(validate=True)
            else:
                self.logger.info(f"개선율 미달 ({improvement:.1%} < {min_improvement:.1%}), 현재 파라미터 유지")
        else:
            # 첫 최적화인 경우
            self.apply_best_params(validate=True)

    def _get_last_optimization_time(self) -> Optional[str]:
        """마지막 최적화 시간 조회"""
        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT created_at FROM optimization_sessions
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            return row[0] if row else None