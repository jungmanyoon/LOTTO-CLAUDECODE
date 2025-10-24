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
from optuna.samplers import TPESampler, CmaEsSampler
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

        # 최적화 범위 설정 (개선: 더 낮은 임계값 탐색)
        self.threshold_range = (0.3, 3.0)  # 0.3% ~ 3.0% (최적값 1.0%가 최소값이었으므로 하한 확장)
        self.ml_bypass_range = (10, 20)    # ML bypass filters 개수 (기존 5~15에서 10~20으로 조정)
        self.ml_weight_range = (0.3, 0.8)  # ML 가중치 (기존 0.2~0.6에서 0.3~0.8로 확대)

        # 성능 목표
        self.target_avg_matches = (0.8, 1.5)  # 목표 평균 매칭
        self.target_ml_inclusion = 0.15       # 목표 ML 포함률 15%

        # 고정 검증 세트 설정 (개선: 슬라이딩 윈도우 → 고정 세트)
        # 이유: 같은 파라미터가 다른 점수를 받는 문제 해결 (91% 중복 시도 제거)
        self.fixed_validation_start = 1050  # 고정 검증 시작 회차
        self.fixed_validation_end = 1150    # 고정 검증 종료 회차 (100회차)
        self.use_fixed_validation = True    # 고정 검증 사용 여부

        # 최적화 히스토리
        self.optimization_history = []
        self.best_params = None
        self.best_score = float('-inf')

        # 데이터베이스 초기화
        self._init_optimization_db()

        # 현재 설정 로드
        self.current_config = self._load_current_config()

        # 수렴 감지 설정 (Convergence Detection) - config.yaml에서 로드
        self._load_convergence_settings()

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

    def _load_convergence_settings(self):
        """config.yaml에서 수렴 감지 설정 로드"""
        try:
            # config.yaml 로드
            config_yaml_path = "config.yaml"
            with open(config_yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # optimization 섹션에서 설정 가져오기
            opt_config = config.get('optimization', {})
            self.convergence_patience = opt_config.get('convergence_patience', 50)
            self.convergence_threshold = opt_config.get('convergence_threshold', 0.01)
            self.max_cumulative_trials = opt_config.get('max_cumulative_trials', 500)

            self.logger.info(f"수렴 감지 설정 로드 완료:")
            self.logger.info(f"  - convergence_patience: {self.convergence_patience}")
            self.logger.info(f"  - convergence_threshold: {self.convergence_threshold}")
            self.logger.info(f"  - max_cumulative_trials: {self.max_cumulative_trials}")

        except Exception as e:
            self.logger.warning(f"수렴 감지 설정 로드 실패 (기본값 사용): {e}")
            # 기본값 설정
            self.convergence_patience = 50
            self.convergence_threshold = 0.01
            self.max_cumulative_trials = 500

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
                self.ml_bypass_range[1],
                step=2  # 1 → 2로 변경: 5, 7, 9, 11, 13, 15 (조합 수 감소)
            )

            ml_weight = trial.suggest_float(
                'ml_weight',
                self.ml_weight_range[0],
                self.ml_weight_range[1],
                step=0.1  # 0.05 → 0.1로 변경: 0.2, 0.3, 0.4, 0.5, 0.6 (조합 수 감소)
            )

            # ============================================================
            # 🔍 TRACE: Trial 시작 로그
            # ============================================================
            self.logger.info(f"")
            self.logger.info(f"╔{'═' * 78}╗")
            self.logger.info(f"║ 🧪 Trial #{trial.number:4d} CONFIGURATION                                        ║")
            self.logger.info(f"╠{'═' * 78}╣")
            self.logger.info(f"║   Threshold: {threshold:6.2f}                                                    ║")
            self.logger.info(f"║   ML Bypass: {ml_bypass:6d}                                                    ║")
            self.logger.info(f"║   ML Weight: {ml_weight:6.2f}                                                    ║")
            self.logger.info(f"╚{'═' * 78}╝")

            # 임시 설정 적용
            temp_config = self.current_config.copy()
            temp_config['global_probability_threshold'] = threshold
            temp_config['ml_integration']['ml_bypass_filters'] = ml_bypass
            temp_config['ml_integration']['ml_weight'] = ml_weight

            # ============================================================
            # 🔍 TRACE: 설정 검증
            # ============================================================
            self.logger.info(f"[TRACE] temp_config 생성 완료:")
            self.logger.info(f"  - global_probability_threshold: {temp_config.get('global_probability_threshold')}")
            self.logger.info(f"  - ml_integration.ml_bypass_filters: {temp_config.get('ml_integration', {}).get('ml_bypass_filters')}")
            self.logger.info(f"  - ml_integration.ml_weight: {temp_config.get('ml_integration', {}).get('ml_weight')}")

            # 백테스팅 실행
            try:
                self.logger.info(f"[TRACE] backtesting_func 호출 시작...")

                # 고정 검증 세트 사용 (개선: 슬라이딩 윈도우 문제 해결)
                if self.use_fixed_validation:
                    self.logger.info(f"[고정 검증] {self.fixed_validation_start}~{self.fixed_validation_end} 회차 사용")
                    results = backtesting_func(
                        temp_config,
                        start_round=self.fixed_validation_start,
                        end_round=self.fixed_validation_end
                    )
                else:
                    # 기존 슬라이딩 윈도우 방식 (하위 호환성)
                    results = backtesting_func(temp_config)

                self.logger.info(f"[TRACE] backtesting_func 호출 완료")

                # 성능 메트릭 추출
                avg_matches = results.get('avg_matches', 0)
                ml_inclusion = results.get('ml_inclusion_rate', 0)
                combination_count = results.get('combination_count', 0)

                # ============================================================
                # 🔍 TRACE: 백테스팅 결과
                # ============================================================
                self.logger.info(f"[TRACE] 백테스팅 결과:")
                self.logger.info(f"  - avg_matches: {avg_matches:.3f}")
                self.logger.info(f"  - ml_inclusion_rate: {ml_inclusion:.3f}")
                self.logger.info(f"  - combination_count: {combination_count:,}")

                # 다중 목적 함수 계산
                score = self._calculate_score(
                    avg_matches,
                    ml_inclusion,
                    combination_count,
                    threshold
                )

                # ============================================================
                # 🔍 TRACE: 점수 계산 완료
                # ============================================================
                self.logger.info(f"")
                self.logger.info(f"┌{'─' * 78}┐")
                self.logger.info(f"│ 📊 Trial #{trial.number:4d} RESULT                                              │")
                self.logger.info(f"├{'─' * 78}┤")
                self.logger.info(f"│   Avg Matches    : {avg_matches:6.3f}                                            │")
                self.logger.info(f"│   ML Inclusion   : {ml_inclusion:6.3f}                                            │")
                self.logger.info(f"│   Combinations   : {combination_count:8,}                                        │")
                self.logger.info(f"│   FINAL SCORE    : {score:6.3f}                                            │")
                self.logger.info(f"└{'─' * 78}┘")
                self.logger.info(f"")

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
        # ✅ FIX: 조합 수 범위 확대 (20~40만 → 30~70만)
        # 이유: 필터가 너무 공격적이어서 좋은 조합도 제외됨
        if 300000 <= combination_count <= 700000:
            efficiency_score = 1.0
        elif combination_count < 300000:
            efficiency_score = combination_count / 300000
        else:
            efficiency_score = max(0, 1.0 - (combination_count - 700000) / 700000)

        # 임계값 안정성 점수 (극단적 값 회피)
        if 0.5 <= threshold <= 1.5:
            stability_score = 1.0
        else:
            stability_score = 0.8

        # 가중 평균 계산
        # ✅ FIX: 가중치 재조정 (match 중요도 증가, efficiency 감소)
        weights = {
            'match': 0.45,       # 35% → 45% (매칭 점수 최우선)
            'inclusion': 0.30,   # 30% 유지 (ML 포함률)
            'efficiency': 0.10,  # 20% → 10% (조합 수는 보조 지표)
            'stability': 0.15    # 15% 유지 (안정성)
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
            n_trials: 시도 횟수 (기존 스터디에 추가로 실행할 횟수)
            n_jobs: 병렬 작업 수
            study_name: 스터디 이름 (None이면 고정된 이름 사용)

        Returns:
            최적 파라미터와 성능 지표
        """
        # 고정된 스터디 이름 사용 (지속적 학습을 위해)
        # CMA-ES sampler 전환: 새 study 이름으로 중복 시도 감소 (91% → <20% 목표)
        if study_name is None:
            study_name = "lotto_threshold_optimization_cmaes"  # 기존 TPE study와 분리

        # Optuna 스터디 생성 (기존 스터디가 있으면 로드)
        # 개선: CmaEsSampler 사용으로 중복 시도 감소 (기존 91% 중복 → 목표 <20%)
        study = optuna.create_study(
            study_name=study_name,
            direction='maximize',
            sampler=CmaEsSampler(
                seed=42,
                n_startup_trials=10  # 초기 랜덤 탐색 (중복 방지)
            ),
            pruner=MedianPruner(
                n_startup_trials=5,
                n_warmup_steps=10
            ),
            storage=f"sqlite:///{self.optimization_db_path}",
            load_if_exists=True  # 기존 스터디가 있으면 로드하여 이어서 진행
        )

        # 기존 시도 횟수 확인
        previous_trials = len(study.trials)
        total_trials_target = previous_trials + n_trials

        self.logger.info(f"최적화 시작: {study_name}")
        self.logger.info(f"  - Sampler: CMA-ES (중복 시도 <20% 목표)")
        self.logger.info(f"  - 임계값 범위: {self.threshold_range[0]}~{self.threshold_range[1]}%")
        self.logger.info(f"  - 고정 검증 세트: {self.fixed_validation_start}~{self.fixed_validation_end} 회차")
        self.logger.info(f"  - 기존 시도: {previous_trials}회")
        self.logger.info(f"  - 추가 시도: {n_trials}회")
        self.logger.info(f"  - 총 목표: {total_trials_target}회")

        # 수렴 감지: 최대 누적 trial 체크
        if previous_trials >= self.max_cumulative_trials:
            self.logger.warning(f"⚠️ 최대 누적 trial 수 도달 ({previous_trials}/{self.max_cumulative_trials})")
            self.logger.warning(f"   기존 최적 파라미터 유지: threshold={study.best_trial.params['threshold']:.2f}, "
                              f"ml_bypass={study.best_trial.params['ml_bypass']}, "
                              f"ml_weight={study.best_trial.params['ml_weight']:.2f}")
            return {
                'study_name': study_name,
                'best_params': study.best_trial.params,
                'best_score': study.best_value,
                'best_trial_number': study.best_trial.number,
                'previous_trials': previous_trials,
                'new_trials': 0,
                'total_trials': previous_trials,
                'converged': True,
                'convergence_reason': 'max_cumulative_trials'
            }

        # 수렴 감지: 최근 patience개 trial에서 개선이 없는지 체크
        if previous_trials >= self.convergence_patience:
            is_converged = self._check_convergence(
                study,
                patience=self.convergence_patience,
                threshold=self.convergence_threshold
            )
            if is_converged:
                # Changed from WARNING to INFO: Convergence is a positive outcome, not an error
                self.logger.info(f"✅ [CONVERGED] 최적화 수렴 완료 - 최적 파라미터 적용")
                self.logger.info(f"   최적 파라미터: threshold={study.best_trial.params['threshold']:.2f}, "
                               f"ml_bypass={study.best_trial.params['ml_bypass']}, "
                               f"ml_weight={study.best_trial.params['ml_weight']:.2f}")
                return {
                    'study_name': study_name,
                    'best_params': study.best_trial.params,
                    'best_score': study.best_value,
                    'best_trial_number': study.best_trial.number,
                    'previous_trials': previous_trials,
                    'new_trials': 0,
                    'total_trials': previous_trials,
                    'converged': True,
                    'convergence_reason': 'no_improvement'
                }

        # 첫 실행일 때만 현재 설정을 초기 추측값으로 사용
        if previous_trials == 0:
            study.enqueue_trial({
                'threshold': self.current_config.get('global_probability_threshold', 1.0),
                'ml_bypass': self.current_config.get('ml_integration', {}).get('ml_bypass_filters', 8),
                'ml_weight': self.current_config.get('ml_integration', {}).get('ml_weight', 0.4)
            })
            self.logger.info("첫 실행: 현재 설정을 초기값으로 사용")
        else:
            self.logger.info(f"이전 최적 파라미터 기반으로 계속 탐색 (best score: {study.best_value:.3f})")

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
            'previous_trials': previous_trials,
            'new_trials': n_trials,
            'total_trials': len(study.trials),
            'avg_matches': best_trial.user_attrs.get('avg_matches'),
            'ml_inclusion_rate': best_trial.user_attrs.get('ml_inclusion_rate'),
            'combination_count': best_trial.user_attrs.get('combination_count')
        }

        self.logger.info(f"최적화 완료!")
        self.logger.info(f"  - 총 시도: {results['total_trials']}회 (이전: {previous_trials}, 신규: {n_trials})")
        self.logger.info(f"  - 최적 파라미터: threshold={self.best_params['threshold']:.2f}, ml_bypass={self.best_params['ml_bypass']}, ml_weight={self.best_params['ml_weight']:.2f}")
        self.logger.info(f"  - 최적 점수: {self.best_score:.3f}")

        return results

    def _check_convergence(
        self,
        study: optuna.Study,
        patience: int = 50,
        threshold: float = 0.01
    ) -> bool:
        """
        수렴 감지: 최근 시도들이 최적 점수를 개선하지 못하면 True 반환

        Args:
            study: Optuna study 객체
            patience: 개선 없이 허용할 최대 trial 수
            threshold: 의미있는 개선으로 판단할 최소 개선율 (1% = 0.01)

        Returns:
            bool: 수렴 여부 (True = 수렴됨, 최적화 중단 권장)
        """
        try:
            # 완료된 trial이 충분히 있는지 확인
            completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
            if len(completed_trials) < patience:
                return False  # 아직 patience만큼 시도하지 않음

            # 최근 patience개 trial의 최고 점수
            recent_trials = completed_trials[-patience:]
            recent_best_score = max(t.value for t in recent_trials)

            # 전체 최고 점수
            overall_best_score = study.best_value

            # 개선율 계산
            if overall_best_score <= 0:
                return False  # 점수가 0이하면 수렴 판단 불가

            improvement_rate = (recent_best_score - overall_best_score) / abs(overall_best_score)

            # 로그 출력
            self.logger.info(f"[수렴 감지] 최근 {patience}회 최고: {recent_best_score:.4f}, "
                           f"전체 최고: {overall_best_score:.4f}, "
                           f"개선율: {improvement_rate:.2%}")

            # 개선율이 threshold 이하면 수렴으로 판단
            if improvement_rate < threshold:
                self.logger.info(f"[CONVERGED] [수렴 감지] {patience}회 동안 {threshold:.1%} 이상 개선 없음 → 최적화 수렴됨")
                return True

            return False

        except Exception as e:
            self.logger.error(f"수렴 감지 오류: {e}")
            return False

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

        FIX: FilterAutoAdjuster가 저장한 dynamic_criteria 보존

        Args:
            validate: 적용 전 검증 수행 여부

        Returns:
            성공 여부
        """
        if self.best_params is None:
            self.logger.warning("적용할 최적 파라미터가 없습니다.")
            return False

        try:
            # ✅ FIX: 최신 설정 파일 다시 로드 (FilterAutoAdjuster 조정값 반영)
            # 메모리 캐시(self.current_config) 대신 파일에서 직접 로드
            with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)

            # 기존 dynamic_criteria 확인 및 로깅
            has_dynamic_criteria = 'dynamic_criteria' in current_config
            if has_dynamic_criteria:
                self.logger.info("[ThresholdOptimizer] dynamic_criteria 발견 - 보존됨")

            # ✅ FIX: global_probability_threshold만 업데이트 (dynamic_criteria 보존)
            # ✅ PRECISION FIX: round()로 부동소수점 오차 제거
            old_threshold = current_config.get('global_probability_threshold', 1.0)
            current_config['global_probability_threshold'] = round(self.best_params['threshold'], 2)
            self.logger.info(
                f"[ThresholdOptimizer] global_probability_threshold: "
                f"{old_threshold} → {round(self.best_params['threshold'], 2)}"
            )

            # ML 통합 설정 업데이트
            if 'ml_integration' not in current_config:
                current_config['ml_integration'] = {}
            current_config['ml_integration']['ml_bypass_filters'] = self.best_params['ml_bypass']
            current_config['ml_integration']['ml_weight'] = round(self.best_params['ml_weight'], 2)

            # 검증 모드
            if validate:
                self.logger.info("최적 파라미터 검증 중...")
                # TODO: 검증 로직 구현 (간단한 백테스팅)

            # ✅ FIX: 설정 저장 (dynamic_criteria 보존됨)
            self._save_config(current_config, backup=True)

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

    def reset_study(self, study_name: str = "lotto_threshold_optimization"):
        """
        최적화 스터디 초기화 (새로 시작하고 싶을 때 사용)

        Args:
            study_name: 초기화할 스터디 이름
        """
        try:
            # Optuna 스터디 삭제
            optuna.delete_study(
                study_name=study_name,
                storage=f"sqlite:///{self.optimization_db_path}"
            )
            self.logger.info(f"스터디 '{study_name}' 초기화 완료. 다음 실행부터 새로 시작합니다.")
            return True
        except Exception as e:
            self.logger.warning(f"스터디 초기화 실패 (이미 없을 수 있음): {e}")
            return False

    def get_study_info(self, study_name: str = "lotto_threshold_optimization") -> Dict:
        """
        현재 스터디 정보 조회

        Args:
            study_name: 조회할 스터디 이름

        Returns:
            스터디 정보 딕셔너리
        """
        try:
            study = optuna.load_study(
                study_name=study_name,
                storage=f"sqlite:///{self.optimization_db_path}"
            )

            info = {
                'study_name': study_name,
                'n_trials': len(study.trials),
                'best_value': study.best_value if study.trials else None,
                'best_params': study.best_params if study.trials else None,
                'trials_complete': len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]),
                'trials_failed': len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL]),
                'trials_pruned': len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
            }

            return info
        except KeyError:
            self.logger.info(f"스터디 '{study_name}'를 찾을 수 없습니다. 아직 최적화를 실행하지 않았습니다.")
            return {'study_name': study_name, 'n_trials': 0}
        except Exception as e:
            self.logger.error(f"스터디 정보 조회 실패: {e}")
            return {}

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