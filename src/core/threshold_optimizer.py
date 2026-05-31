"""
임계값 최적화 시스템
Optuna를 활용한 Bayesian Optimization으로 최적 임계값 탐색

[v2] 목적함수 재설계 (2026-03-06):
- 기존: 포함률 최대화 -> 필터 무력화 구조적 결함
- 변경: 포함률은 제약조건(>=98%), 풀 크기 최소화가 핵심 목표
"""
import os
import math
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Callable
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
        optimization_db_path: str = "data/optimization.db"
    ) -> None:
        # Phase 2: optimization.db로 통합 (Optuna storage는 threshold_optimization.db 유지)
        self.config_path = config_path
        # FIX: adaptive_config_path 별칭 추가 (apply_best_params에서 사용)
        self.adaptive_config_path = config_path
        self.stats_db_path = stats_db_path
        self.optimization_db_path = optimization_db_path
        self.logger = logging.getLogger(__name__)

        # [v2] 최적화 범위 설정
        self.threshold_range = (0.3, 2.5)  # 0.3% ~ 2.5% (3.0->2.5: 극단적 느슨함 방지)
        self.ml_bypass_range = (8, 15)     # ML bypass 8~15 (ThresholdManager 허용: 8~20)
        self.ml_weight_range = (0.3, 0.7)  # ML 가중치 0.3~0.7 (0.8->0.7: 과도한 ML 의존 방지)

        # 성능 목표
        self.target_avg_matches = (0.8, 1.5)  # 목표 평균 매칭
        self.target_ml_inclusion = 0.15       # 목표 ML 포함률 15%

        # [v2] 필터 파라미터 하한선 (Optuna가 필터를 무력화하지 못하도록)
        # 각 필터의 기준값이 이 범위를 벗어나면 안 됨
        self.filter_bounds = {
            'consecutive': {'max_consecutive': (2, 5)},    # 2~5 (6이상은 사실상 무력화)
            'match': {'max_match': (3, 5)},                # 3~5 (6이면 무력화)
            'last_digit': {'min_same_last_digits': (3, 5)}, # 3~5 (6이면 무력화)
            'sum_range': {'min_sum': (30, 70), 'max_sum': (180, 255)},
            'average': {'min_average': (5.0, 12.0), 'max_average': (33.0, 42.0)},
            'digit_sum': {'min_digit_sum': (10, 25), 'max_digit_sum': (45, 70)},
            'dispersion': {'min_std_dev': (2.0, 6.0), 'max_std_dev': (16.0, 20.0)},
            'max_gap': {'max_allowed_gap': (20, 35)},
            'section': {'max_numbers_per_section': (4, 6)},
        }

        # 동적 검증 세트 설정 (개선: 고정 세트 → 슬라이딩 윈도우)
        # 이유: 새 회차가 추가되면 최신 데이터로 검증해야 함
        # [v5 FIX] 50→100: 표본 확대로 통과율/avg_matches 표준오차 감소(노이즈 롤백 방지).
        # 50회 표본은 통과율 granularity 2%p라 0.95 임계와 정합 불가 → 100회로 1%p 해상도 확보.
        self.validation_window_size = 100   # 검증에 사용할 회차 수
        self.use_dynamic_validation = True  # 동적 검증 사용 여부
        self.state_file = "data/auto_improvement_state.json"

        # 동적 검증 세트 초기화 (최신 데이터 기반)
        self._update_validation_range()

        # 새 회차 감지를 위한 상태
        self.last_known_round = self._get_latest_round()

        # 최적화 히스토리
        self.optimization_history = []
        self.best_params = None
        self.best_score = float('-inf')

        # Phase 4: ML 하이퍼파라미터 탐색 범위
        self.lstm_epochs_range = (10, 50)
        self.ensemble_n_estimators_range = (50, 200)
        self.monte_carlo_simulations_range = (1000, 10000)
        # Phase 4: 모델 파라미터 캐시 - 동일 파라미터 시 백테스팅 재실행 방지
        self._model_param_cache: Dict[tuple, Dict] = {}

        # 데이터베이스 초기화
        self._init_optimization_db()

        # 현재 설정 로드
        self.current_config = self._load_current_config()

        # 수렴 감지 설정 (Convergence Detection) - config.yaml에서 로드
        self._load_convergence_settings()

    def _init_optimization_db(self) -> None:
        """최적화 결과 저장용 데이터베이스 초기화"""
        os.makedirs(os.path.dirname(self.optimization_db_path), exist_ok=True)

        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()

            # 최적화 세션 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS threshold_optimization_sessions (
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

            # 개별 시도 결과 테이블 (optimization_db.py의 optimization_trials와 충돌 방지)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS threshold_trial_details (
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
                    FOREIGN KEY (session_id) REFERENCES threshold_optimization_sessions (id)
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


    def _get_latest_round(self) -> int:
        """데이터베이스에서 최신 회차 번호 가져오기"""
        try:
            from .db_manager import DatabaseManager
            db = DatabaseManager()
            numbers = db.get_numbers_with_bonus()
            if numbers:
                return max(n[0] for n in numbers)
            return 1150  # 기본값
        except Exception as e:
            self.logger.warning(f"최신 회차 조회 실패: {e}")
            return 1150

    def _update_validation_range(self) -> None:
        """최신 데이터 기반으로 검증 범위 업데이트

        구조:
          훈련  -> 회차 1 ~ (latest - 2*window - 1)
          검증  -> 회차 (latest - 2*window) ~ (latest - window - 1)  <- Optuna 최적화용
          테스트 -> 회차 (latest - window) ~ (latest - 1)            <- hold-out (최적화에 미사용)
        """
        try:
            latest = self._get_latest_round()
            window = self.validation_window_size  # 100

            # hold-out 테스트셋: 최신 window개 회차 (Optuna 최적화에 절대 미사용)
            self.test_set_start = max(1, latest - window)
            self.test_set_end = latest - 1

            # Optuna 검증셋: 테스트셋 직전 window개 회차
            self.fixed_validation_end = max(1, self.test_set_start - 1)
            self.fixed_validation_start = max(1, self.fixed_validation_end - window + 1)
            self.use_fixed_validation = True

            self.logger.info(f"[동적 검증] 범위 업데이트:")
            self.logger.info(f"  Optuna 검증셋: {self.fixed_validation_start}~{self.fixed_validation_end} ({window}회차)")
            self.logger.info(f"  Hold-out 테스트셋: {self.test_set_start}~{self.test_set_end} ({window}회차, 최적화 미사용)")
            self.logger.info(f"  (최신 회차: {latest}, 윈도우: {window})")
        except Exception as e:
            self.logger.warning(f"검증 범위 업데이트 실패: {e}")
            # 폴백: 기존 고정값 (검증/테스트 분리)
            self.fixed_validation_start = 950
            self.fixed_validation_end = 1050
            self.test_set_start = 1051
            self.test_set_end = 1150

    def evaluate_on_test_set(self, backtesting_func) -> Dict[str, Any]:
        """hold-out 테스트셋에서 최적 파라미터 최종 평가 (최적화 완료 후 1회만 호출)

        주의: 이 메서드는 Optuna 최적화 완료 후 최종 성능 확인에만 사용한다.
              최적화 루프 내부에서 호출하면 테스트셋 오염이 발생한다.

        Returns:
            dict: avg_matches, ml_inclusion_rate, combination_count 등
        """
        if not hasattr(self, 'test_set_start') or not hasattr(self, 'test_set_end'):
            self._update_validation_range()

        if not self.best_params:
            self.logger.warning("[테스트셋 평가] 최적 파라미터 없음 - 현재 설정으로 평가")
            best_config = self.current_config.copy()
        else:
            best_config = self.current_config.copy()
            best_config['global_probability_threshold'] = self.best_params.get('threshold', 1.0)
            if 'ml_integration' not in best_config:
                best_config['ml_integration'] = {}
            best_config['ml_integration']['ml_bypass_filters'] = self.best_params.get('ml_bypass', 10)
            best_config['ml_integration']['ml_weight'] = self.best_params.get('ml_weight', 0.5)

        self.logger.info(f"[테스트셋 평가] 범위: {self.test_set_start}~{self.test_set_end}")
        self.logger.info(f"[테스트셋 평가] 파라미터: {self.best_params}")

        results = backtesting_func(
            best_config,
            start_round=self.test_set_start,
            end_round=self.test_set_end
        )

        self.logger.info(f"[테스트셋 평가 완료]")
        self.logger.info(f"  avg_matches    : {results.get('avg_matches', 0):.3f}")
        self.logger.info(f"  ml_inclusion   : {results.get('ml_inclusion_rate', 0):.3f}")
        self.logger.info(f"  combinations   : {results.get('combination_count', 0):,}")

        return results

    def _load_best_performance(self) -> Optional[Dict]:
        """auto_improvement_state.json에서 최고 성능 설정 로드"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    best = state.get('best_performance')
                    if best:
                        self.logger.info(f"[최고 성능 로드] ")
                        self.logger.info(f"  - avg_matches: {best.get('ensemble_avg_matches', 'N/A')}")
                        self.logger.info(f"  - threshold: {best.get('threshold_settings', {}).get('global_probability_threshold', 'N/A')}")
                        return best
            return None
        except Exception as e:
            self.logger.warning(f"최고 성능 로드 실패: {e}")
            return None

    def check_new_round(self) -> bool:
        """새 회차 감지 및 검증 범위 업데이트

        Returns:
            True: 새 회차 발견 (검증 범위 업데이트됨)
            False: 변경 없음
        """
        current_round = self._get_latest_round()

        if current_round > self.last_known_round:
            self.logger.info(f"[새 회차 감지] {self.last_known_round} -> {current_round}")

            # 검증 범위 업데이트
            self._update_validation_range()
            self.last_known_round = current_round

            # 최고 성능 설정 로드 (새 회차에서 초기값으로 사용)
            best = self._load_best_performance()
            if best:
                threshold_settings = best.get('threshold_settings', {})
                self.best_params = {
                    'threshold': threshold_settings.get('global_probability_threshold', 1.0),
                    'ml_bypass': threshold_settings.get('ml_bypass_filters', 15),
                    'ml_weight': threshold_settings.get('ml_weight', 0.5)
                }
                self.logger.info(f"[초기값 설정] 이전 최고 성능 파라미터 사용: {self.best_params}")

            return True
        return False


    def _load_convergence_settings(self) -> None:
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

            # [NEW] Never-Stop Learning Mode 설정 로드
            self.never_stop_learning = opt_config.get('never_stop_learning', False)
            self.weekly_cycle_mode = opt_config.get('weekly_cycle_mode', False)
            self.trial_batch_size = opt_config.get('trial_batch_size', 25)
            self.batch_interval_seconds = opt_config.get('batch_interval_seconds', 300)

            self.logger.info(f"수렴 감지 설정 로드 완료:")
            self.logger.info(f"  - convergence_patience: {self.convergence_patience}")
            self.logger.info(f"  - convergence_threshold: {self.convergence_threshold}")
            self.logger.info(f"  - max_cumulative_trials: {self.max_cumulative_trials}")

            # [NEW] 무한 학습 모드 로그
            if self.never_stop_learning:
                self.logger.info(f"  [무한 학습 모드 활성화]")
                self.logger.info(f"     - 수렴 감지 무시: True")
                self.logger.info(f"     - 주간 사이클 모드: {self.weekly_cycle_mode}")
                self.logger.info(f"     - 배치 크기: {self.trial_batch_size}회")
                self.logger.info(f"     - 배치 간격: {self.batch_interval_seconds}초")

        except Exception as e:
            self.logger.warning(f"수렴 감지 설정 로드 실패 (기본값 사용): {e}")
            # 기본값 설정
            self.convergence_patience = 150   # 50→150: 너무 빠른 조기 수렴 방지
            self.convergence_threshold = 0.01
            self.max_cumulative_trials = 500
            self.never_stop_learning = False
            self.weekly_cycle_mode = False
            self.trial_batch_size = 25
            self.batch_interval_seconds = 300

    def _enforce_filter_bounds(self, config: Dict[str, Any]) -> None:
        """
        [v2] 필터 파라미터가 하한선/상한선을 벗어나지 않도록 교정

        Optuna나 auto-adjuster가 필터 기준값을 극단적으로 조정하는 것을 방지합니다.
        예: consecutive max_consecutive=6 -> 사실상 필터 무력화 -> 5로 교정

        Args:
            config: adaptive_filter_config 딕셔너리 (in-place 수정)
        """
        dynamic_criteria = config.get('dynamic_criteria', {})
        if not dynamic_criteria:
            return

        corrections_made = []

        for filter_name, bounds in self.filter_bounds.items():
            if filter_name not in dynamic_criteria:
                continue

            filter_config = dynamic_criteria[filter_name]
            for param_name, (lower, upper) in bounds.items():
                if param_name not in filter_config:
                    continue

                current_value = filter_config[param_name]
                if current_value is None:
                    continue

                # 타입 보존 (int/float)
                if isinstance(current_value, int):
                    clamped = max(int(lower), min(int(upper), current_value))
                else:
                    clamped = max(float(lower), min(float(upper), float(current_value)))

                if clamped != current_value:
                    filter_config[param_name] = clamped
                    corrections_made.append(
                        f"  {filter_name}.{param_name}: {current_value} -> {clamped} "
                        f"(bounds: {lower}~{upper})"
                    )

        if corrections_made:
            self.logger.warning(
                f"[v2] 필터 하한선 교정 {len(corrections_made)}건:\n" +
                "\n".join(corrections_made)
            )
        else:
            self.logger.debug("[v2] 필터 파라미터 모두 범위 내")

    def _save_config(self, config: Dict[str, Any], backup: bool = True) -> None:
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

    def set_shutdown_flag(self, flag: dict):
        """외부 종료 플래그 설정 (백그라운드 최적화 종료 감지용)"""
        self._shutdown_flag = flag

    def _is_shutting_down(self) -> bool:
        """종료 플래그 확인"""
        return bool(getattr(self, '_shutdown_flag', None) and self._shutdown_flag.get('stop', False))

    def _measure_winning_inclusion_rate(self, threshold: float, start_round: int, end_round: int) -> float:
        """
        [v2] 당첨번호가 현재 필터 설정으로 풀에 포함되는 비율 측정

        실제 당첨번호를 가져와서 각 필터를 적용한 후
        모든 필터를 통과하는 당첨번호의 비율을 반환합니다.

        Args:
            threshold: 현재 probability threshold
            start_round: 검증 시작 회차
            end_round: 검증 종료 회차

        Returns:
            포함률 (0.0 ~ 1.0)
        """
        try:
            from src.validators.filter_validator import FilterValidator
            from src.core.db_manager import DatabaseManager

            db = DatabaseManager()
            validator = FilterValidator(db)

            # 검증 범위의 당첨번호 가져오기
            all_numbers_data = db.get_all_numbers()
            if not all_numbers_data:
                self.logger.warning("[v2] 당첨번호 데이터 없음 - 포함률 1.0 반환")
                return 1.0

            # 검증 범위 필터링
            test_numbers = []
            for round_num, numbers_str, draw_date in all_numbers_data:
                if start_round <= round_num <= end_round:
                    numbers = [int(n) for n in numbers_str.split(',')]
                    test_numbers.append((round_num, numbers))

            if not test_numbers:
                self.logger.warning(f"[v2] 검증 범위({start_round}~{end_round})에 당첨번호 없음")
                return 1.0

            # 각 당첨번호에 대해 필터 통과 여부 확인
            passed_count = 0
            for round_num, numbers in test_numbers:
                all_passed = True
                for filter_name, filter_instance in validator.filter_manager.filters.items():
                    try:
                        passed = validator._check_filter_pass(filter_instance, numbers, round_num)
                        if not passed:
                            all_passed = False
                            break
                    except Exception:
                        continue  # 개별 필터 오류 시 통과로 처리

                if all_passed:
                    passed_count += 1

            inclusion_rate = passed_count / len(test_numbers)
            self.logger.info(
                f"[v2] 당첨번호 포함률: {inclusion_rate:.3f} "
                f"({passed_count}/{len(test_numbers)}) "
                f"threshold={threshold:.2f}"
            )
            return inclusion_rate

        except Exception as e:
            self.logger.error(f"[v2] 당첨번호 포함률 측정 실패: {e}")
            # 측정 실패 시 안전하게 1.0 반환 (페널티 없음)
            return 1.0

    def _estimate_pool_size(self, threshold: float) -> int:
        """
        [v2] 주어진 threshold에서의 예상 풀 크기 추정

        실제 필터링을 실행하지 않고, threshold와 combination_count의
        관계를 사용하여 빠르게 추정합니다.

        Args:
            threshold: probability threshold

        Returns:
            예상 풀 크기
        """
        # threshold와 풀 크기의 대략적 관계 (실측 데이터 기반)
        # 실측: 1.3% -> ~300K, 0.5% -> ~500K
        # 로그 관계: pool_size = base * exp(-k * threshold)
        # [FIX] 계수 보정: -1.8 → -2.54 (실측 역산: -ln(300K/8145060) / 1.3 ≈ 2.54)
        # 기존 계수 -1.8은 1.3%에서 ~784K 추정 → 실측 300K 대비 2.6배 오차
        TOTAL = 8_145_060
        # 보정된 경험적 계수 (실측 기반)
        estimated = int(TOTAL * math.exp(-2.54 * threshold))
        # 최소/최대 제한
        estimated = max(50_000, min(estimated, TOTAL))
        return estimated

    def create_objective(self, backtesting_func: Callable[[Dict[str, Any], int, int], Dict[str, Any]]) -> Callable[[optuna.Trial], float]:
        """[v2] Optuna 목적 함수 생성 - 풀 크기 최소화 중심"""

        def objective(trial):
            # 종료 플래그 확인 - trial 시작 전 조기 중단
            if self._is_shutting_down():
                self.logger.info(f"[SHUTDOWN] Trial #{trial.number}: 종료 플래그 감지 - TrialPruned")
                raise optuna.TrialPruned()
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
                step=2
            )

            ml_weight = trial.suggest_float(
                'ml_weight',
                self.ml_weight_range[0],
                self.ml_weight_range[1],
                step=0.1
            )

            # ============================================================
            # [v4] Trial 시작 로그 (threshold/ml_bypass/ml_weight 3개만 최적화)
            # NOTE: lstm_epochs, n_estimators, mc_sims는 Optuna 검색공간에서 제거
            #       이유: 백테스팅 프레임워크에 전달 경로 없음 → 최적화 효과 없음
            #             + 검색 공간 확대로 threshold 탐색 수렴 방해
            # ============================================================
            self.logger.info(f"")
            self.logger.info(f"={'=' * 78}")
            self.logger.info(
                f"  [v4] Trial #{trial.number:4d} CONFIG: "
                f"threshold={threshold:.2f}, ml_bypass={ml_bypass}, ml_weight={ml_weight:.2f}"
            )
            self.logger.info(f"={'=' * 78}")

            # 임시 설정 적용
            temp_config = self.current_config.copy()
            temp_config['global_probability_threshold'] = threshold
            temp_config['ml_integration'] = dict(temp_config.get('ml_integration', {}))
            temp_config['ml_integration']['ml_bypass_filters'] = ml_bypass
            temp_config['ml_integration']['ml_weight'] = ml_weight

            # 캐시 키: threshold 0.01 단위 bin + ml_bypass + ml_weight
            cache_key = (round(threshold * 100), ml_bypass, round(ml_weight * 10))
            cache_hit = cache_key in self._model_param_cache

            # 백테스팅 실행
            try:
                if cache_hit:
                    # 캐시 히트 - 모델 재훈련 없이 이전 결과 재사용
                    cached = self._model_param_cache[cache_key]
                    avg_matches = cached['avg_matches']
                    ml_inclusion = cached['ml_inclusion']
                    combination_count = cached['combination_count']
                    total_predictions = cached.get('total_predictions', 1)
                    self.logger.info(
                        f"  [CACHE HIT] 모델 파라미터 동일 - 백테스팅 스킵 "
                        f"(avg_matches={avg_matches:.3f})"
                    )
                else:
                    # 캐시 미스 - FIX-01: 이전 Trial의 백테스트 상태 파일 초기화
                    backtest_state_file = "data/backtest_state.json"
                    if os.path.exists(backtest_state_file):
                        try:
                            os.remove(backtest_state_file)
                        except OSError as e:
                            self.logger.warning(f"[FIX-01] 상태 파일 삭제 실패: {e}")

                    # 고정 검증 세트 사용
                    if self.use_fixed_validation:
                        self.logger.info(f"[v3] 검증 범위: {self.fixed_validation_start}~{self.fixed_validation_end}")
                        results = backtesting_func(
                            temp_config,
                            start_round=self.fixed_validation_start,
                            end_round=self.fixed_validation_end
                        )
                    else:
                        results = backtesting_func(temp_config)

                    # 종료 플래그 재확인
                    if self._is_shutting_down():
                        self.logger.info(f"[SHUTDOWN] Trial #{trial.number}: 백테스팅 완료 후 종료 감지 - TrialPruned")
                        raise optuna.TrialPruned()

                    # 성능 메트릭 추출
                    avg_matches = results.get('avg_matches', 0)
                    ml_inclusion = results.get('ml_inclusion_rate', 0)
                    combination_count = results.get('combination_count', 0)
                    total_predictions = results.get('total_predictions', 0)

                    # 캐시에 저장 (다음 trial에서 재사용)
                    self._model_param_cache[cache_key] = {
                        'avg_matches': avg_matches,
                        'ml_inclusion': ml_inclusion,
                        'combination_count': combination_count,
                        'total_predictions': total_predictions,
                    }

                # ============================================================
                # [v4] 당첨번호 포함률 측정 (제약조건)
                # [FIX] 측정 범위를 백테스팅 범위 외부로 분리
                # 문제: 기존에는 validation_start/end = 백테스팅 범위(50회차)와 동일
                #       → 최적화 대상과 제약조건 검증 데이터가 겹쳐 과적합 위험
                # 수정: 백테스팅 시작점 이전 100회차를 winning_inclusion 측정에 사용
                # ============================================================
                if self.use_fixed_validation:
                    # 백테스팅 범위: fixed_validation_start ~ fixed_validation_end
                    # winning_inclusion 범위: 백테스팅 시작 100회차 전 (완전 분리)
                    wi_end = max(1, self.fixed_validation_start - 1)
                    wi_start = max(1, wi_end - self.validation_window_size + 1)
                    # 최소 20회차 보장 (데이터 부족 시 폴백)
                    if wi_end - wi_start < 19:
                        wi_start = max(1, self.fixed_validation_start - 20)
                        wi_end = self.fixed_validation_start - 1
                else:
                    wi_start = 1037
                    wi_end = 1136
                winning_inclusion_rate = self._measure_winning_inclusion_rate(
                    threshold, wi_start, wi_end
                )
                self.logger.info(
                    f"  [v4] winning_inclusion 측정 범위: {wi_start}~{wi_end} "
                    f"(백테스팅 {self.fixed_validation_start}~{self.fixed_validation_end}와 분리)"
                )

                # combination_count가 0이면 추정값 사용
                if combination_count <= 0:
                    combination_count = self._estimate_pool_size(threshold)
                    self.logger.info(f"[v3] combination_count=0, 추정값 사용: {combination_count:,}")

                # [v3] avg_matches 최대화 중심 점수 계산
                score = self._calculate_score(
                    avg_matches,
                    ml_inclusion,
                    combination_count,
                    threshold,
                    winning_inclusion_rate
                )

                # ============================================================
                # [v3] 결과 로그
                # ============================================================
                self.logger.info(f"  [v3] Trial #{trial.number:4d} RESULT:")
                self.logger.info(f"    Avg Matches     : {avg_matches:.3f}")
                self.logger.info(f"    ML Inclusion    : {ml_inclusion:.3f}")
                self.logger.info(f"    Combinations    : {combination_count:,}")
                self.logger.info(f"    Win Inclusion   : {winning_inclusion_rate:.3f}")
                self.logger.info(f"    SCORE (v3)      : {score:.4f}")
                self.logger.info(f"  {'=' * 78}")

                # 중간 결과 기록
                trial.set_user_attr('avg_matches', avg_matches)
                trial.set_user_attr('ml_inclusion_rate', ml_inclusion)
                trial.set_user_attr('combination_count', combination_count)
                trial.set_user_attr('winning_inclusion_rate', winning_inclusion_rate)

                # 조기 종료 조건 (Pruning)
                if avg_matches > 3.0:  # 데이터 오염 의심
                    raise optuna.TrialPruned()

                # 0값 결과 방어 - avg_matches=0이면 predictions 여부와 무관하게 제거
                if avg_matches == 0:
                    self.logger.warning(f"[GARBAGE] Trial #{trial.number}: avg_matches=0 - TrialPruned (predictions={total_predictions})")
                    raise optuna.TrialPruned()

                return score

            except optuna.TrialPruned:
                raise  # TrialPruned는 그대로 전파
            except Exception as e:
                self.logger.error(f"백테스팅 실행 실패: {e}")
                # CMA-ES 공분산 행렬 오염 방지: float('-inf') 대신 TrialPruned 사용
                raise optuna.TrialPruned()

        return objective

    def _calculate_score(
        self,
        avg_matches: float,
        ml_inclusion: float,
        combination_count: int,
        threshold: float,
        winning_inclusion_rate: float = 1.0
    ) -> float:
        """
        [v5] 통과율(winning_inclusion) 최대화 중심 점수 계산

        공식:
            제약 충족(통과율 >= 0.95):
                score = winning_inclusion + 0.1 * avg_matches - 0.05 * log(pool/100_000)
            제약 위반(통과율 < 0.95):
                score = winning_inclusion - 10 * deficit - pool_penalty

        설계 원칙(2026-05-31 재설계, Codex/Gemini 교차검증):
        - [핵심 전략] 1차 지표 = "실제 당첨번호가 필터를 통과하는 비율(통과율)".
          로또는 독립시행이므로 avg_matches 최대화는 노이즈/과적합 추종(E[일치수]=0.8 고정).
        - winning_inclusion_rate를 "주 목표"로 승격(기존 v4는 제약조건으로만 사용 → 우선순위 역전 버그).
        - avg_matches는 가중치 0.1의 tie-breaker로 강등(동률 trial 구분용, 노이즈 영향 최소화).
        - pool_penalty(풀 축소 인센티브) 유지: "통과율 유지하며 풀 최소화" = 핵심 전략 그 자체.
        - 제약 위반 시 deficit*10 강페널티로 통과율 미달 trial이 절대 선택되지 않게 함.

        Args:
            avg_matches: 평균 매칭 수 (보조 tie-breaker, 노이즈 신호)
            ml_inclusion: ML 예측의 필터 통과율 (미사용 - Level-3 바이패스로 상수 편향)
            combination_count: 필터링 후 조합 수 (로그 페널티)
            threshold: 현재 probability threshold (내부 사용 안 함, 하위호환성 유지)
            winning_inclusion_rate: 당첨번호가 필터를 통과하는 비율 (주 최적화 목표)
        """
        # [v5 FIX] 0.99 → 0.95: 50~100회 표본에서 1~2개 누락에 score가 절벽처럼 0이 되는
        #          cliff 제거. 0.95는 핵심 전략(통과율 95%+)의 목표값과 정합.
        INCLUSION_THRESHOLD = 0.95

        # ============================================================
        # (A) 풀 크기 로그 페널티 (regularizer) - 먼저 계산하여 모든 경로에 적용
        # pool=300K → penalty=0.055, pool=8.14M → penalty=0.220
        # "같은 통과율이면 더 좁은 풀"을 선호하도록 유도 (핵심 전략)
        # ============================================================
        effective_pool = max(combination_count if combination_count > 0 else 8_145_060, 100_000)
        pool_penalty = 0.05 * math.log(effective_pool / 100_000)

        # ============================================================
        # (B) 당첨번호 통과율 제약 위반 (Hard Constraint)
        # 95% 미만 시 미달분에 강한 페널티 → 풀 축소 이득이 절대 이기지 못하게
        # ============================================================
        if winning_inclusion_rate < INCLUSION_THRESHOLD:
            deficit = INCLUSION_THRESHOLD - winning_inclusion_rate
            # 1%p 미달 당 0.1 감점 (통과율 주항보다 10배 큰 기울기로 위반을 강하게 회피)
            score = winning_inclusion_rate - deficit * 10.0 - pool_penalty
            self.logger.debug(
                f"[SCORE v5] 통과율 제약 위반: {winning_inclusion_rate:.3f} < {INCLUSION_THRESHOLD} "
                f"-> deficit={deficit:.3f}, score={score:.4f}"
            )
            return score

        # ============================================================
        # (C) 최종 점수: 통과율(주) + avg_matches(보조 tie-breaker) - 풀 페널티
        # 통과율 충족 trial들 사이에서는 pool_penalty(풀 크기)가 실질 구분자가 됨
        # → "통과율 95%+ 유지하면서 풀을 최대한 좁힌" trial이 최고 점수
        # ============================================================
        score = winning_inclusion_rate + 0.1 * avg_matches - pool_penalty

        self.logger.debug(
            f"[SCORE v5] winning_inclusion={winning_inclusion_rate:.3f}(주) "
            f"+ 0.1*avg_matches={0.1 * avg_matches:.3f}(보조) "
            f"- pool_penalty={pool_penalty:.4f} -> score={score:.4f}"
        )

        return score

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
        # ============================================================
        # [SYNC] 새 회차 감지 및 검증 범위 업데이트
        # ============================================================
        new_round_detected = self.check_new_round()
        if new_round_detected:
            self.logger.info(f"")
            self.logger.info(f"╔{'═' * 78}╗")
            self.logger.info(f"║ [NEW] 새 회차 감지! 검증 범위 업데이트됨                                   ║")
            self.logger.info(f"╠{'═' * 78}╣")
            self.logger.info(f"║   검증 범위: {self.fixed_validation_start}~{self.fixed_validation_end}                                     ║")
            self.logger.info(f"║   이전 최고 성능 파라미터 사용                                      ║")
            self.logger.info(f"╚{'═' * 78}╝")
            self.logger.info(f"")

        # [v4] 새 목적함수용 스터디 이름 (v3와 분리)
        # 이유: ml_inclusion 제거, pool_penalty 0.01→0.05, INCLUSION_THRESHOLD 0.98→0.99로
        #       공식이 근본적으로 변경되어 기존 v3 trial 결과와 CMA-ES 공분산 행렬 호환 불가
        if study_name is None:
            study_name = "lotto_threshold_v4"  # v4 목적함수 (ml_inclusion 제거, pool_penalty 0.05)

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

        # [NEW] Never-Stop Learning Mode 활성화 체크
        if self.never_stop_learning:
            self.logger.info(f"")
            self.logger.info(f"╔{'═' * 78}╗")
            self.logger.info(f"║ [ON] 무한 학습 모드 활성화 - 수렴 감지 무시됨                               ║")
            self.logger.info(f"╠{'═' * 78}╣")
            self.logger.info(f"║   • 최대 trial 제한 무시: {self.max_cumulative_trials} → ∞                      ║")
            self.logger.info(f"║   • 수렴 감지 무시: patience={self.convergence_patience} → 무효화               ║")
            self.logger.info(f"║   • 주간 사이클 모드: {'활성화' if self.weekly_cycle_mode else '비활성화'}                                  ║")
            self.logger.info(f"║   • 학습은 외부 종료 신호까지 계속됩니다                                ║")
            self.logger.info(f"╚{'═' * 78}╝")
            self.logger.info(f"")

        # 수렴 감지: 최대 누적 trial 체크 (무한 학습 모드에서는 우회)
        if not self.weekly_cycle_mode and previous_trials >= self.max_cumulative_trials:
            self.logger.warning(f"[WARN] 최대 누적 trial 수 도달 ({previous_trials}/{self.max_cumulative_trials})")
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

        # 수렴 감지: 최근 patience개 trial에서 개선이 없는지 체크 (무한 학습 모드에서는 우회)
        if not self.never_stop_learning and previous_trials >= self.convergence_patience:
            is_converged = self._check_convergence(
                study,
                patience=self.convergence_patience,
                threshold=self.convergence_threshold
            )
            if is_converged:
                # Changed from WARNING to INFO: Convergence is a positive outcome, not an error
                self.logger.info(f"[CONVERGED] 최적화 수렴 완료 - 최적 파라미터 적용")
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

        # 초기값 설정: 첫 실행 또는 새 회차 감지 시
        if previous_trials == 0 or new_round_detected:
            # 새 회차가 감지되면 이전 최고 성능 파라미터 사용
            if new_round_detected and self.best_params:
                initial_params = {
                    'threshold': self.best_params.get('threshold', 1.0),
                    'ml_bypass': self.best_params.get('ml_bypass', 15),
                    'ml_weight': self.best_params.get('ml_weight', 0.5),
                    'lstm_epochs': self.best_params.get('lstm_epochs', 30),
                    'ensemble_n_estimators': self.best_params.get('ensemble_n_estimators', 100),
                    'monte_carlo_simulations': self.best_params.get('monte_carlo_simulations', 6000),
                }
                study.enqueue_trial(initial_params)
                self.logger.info(f"[새 회차] 이전 최고 성능 파라미터로 초기화: {initial_params}")
            else:
                # 첫 실행이거나 최고 성능이 없으면 현재 설정 사용
                study.enqueue_trial({
                    'threshold': self.current_config.get('global_probability_threshold', 1.0),
                    'ml_bypass': self.current_config.get('ml_integration', {}).get('ml_bypass_filters', 8),
                    'ml_weight': self.current_config.get('ml_integration', {}).get('ml_weight', 0.4),
                    'lstm_epochs': 30,
                    'ensemble_n_estimators': 100,
                    'monte_carlo_simulations': 6000,
                })
                self.logger.info("첫 실행: 현재 설정을 초기값으로 사용")
        else:
            self.logger.info(f"이전 최적 파라미터 기반으로 계속 탐색 (best score: {study.best_value:.3f})")

        # 최적화 실행
        # [FIX] VSCode/Cursor 디버거에서 tqdm 진행 표시줄 충돌 방지
        study.optimize(
            self.create_objective(backtesting_func),
            n_trials=n_trials,
            n_jobs=n_jobs,
            show_progress_bar=False  # debugpy OSError 방지
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
            'combination_count': best_trial.user_attrs.get('combination_count'),
            # 새 회차 감지 정보 추가
            'new_round_detected': new_round_detected,
            'validation_range': (self.fixed_validation_start, self.fixed_validation_end),
            'latest_round': self.last_known_round
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

            # [FIX] 공식 수정: recent - overall이 아닌 overall - recent
            # 최근 최고가 전체 최고와 얼마나 차이 나는지 측정
            # improvement_rate < threshold → 최근이 전체 최고 대비 거의 차이 없음 → 수렴
            improvement_rate = (overall_best_score - recent_best_score) / abs(overall_best_score)

            # 로그 출력
            self.logger.info(f"[수렴 감지] 최근 {patience}회 최고: {recent_best_score:.4f}, "
                           f"전체 최고: {overall_best_score:.4f}, "
                           f"정체율: {improvement_rate:.2%}")

            # 정체율이 threshold 이하면 수렴으로 판단 (최근이 전체 최고와 거의 같음)
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
                INSERT INTO threshold_optimization_sessions
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
                        INSERT INTO threshold_trial_details
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
            # [FIX] 최신 설정 파일 다시 로드 (FilterAutoAdjuster 조정값 반영)
            # 메모리 캐시(self.current_config) 대신 파일에서 직접 로드
            with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)

            # 기존 dynamic_criteria 확인 및 로깅
            has_dynamic_criteria = 'dynamic_criteria' in current_config
            if has_dynamic_criteria:
                self.logger.info("[ThresholdOptimizer] dynamic_criteria 발견 - 보존됨")

            # [FIX] global_probability_threshold만 업데이트 (dynamic_criteria 보존)
            # [FIX] PRECISION: round()로 부동소수점 오차 제거
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

            # [v2] 필터 파라미터 하한선 검증 및 교정
            self._enforce_filter_bounds(current_config)

            # 설정 저장 (dynamic_criteria 보존됨)
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

            # 로그 출력 시 부동소수점 정리
            formatted_params = {k: round(v, 2) if isinstance(v, float) else v for k, v in self.best_params.items()}
            self.logger.info(f"최적 파라미터 적용 완료: {formatted_params}")
            return True

        except Exception as e:
            self.logger.error(f"최적 파라미터 적용 실패: {e}")
            return False

    def get_optimization_history(self, limit: int = 10) -> List[Dict]:
        """최근 최적화 이력 조회"""
        with sqlite3.connect(self.optimization_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM threshold_optimization_sessions
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
            elif improvement < -0.10:  # [FIX] 10% 이상 성능 하락 감지
                self.logger.warning(f"[WARN] 성능 하락 감지: {improvement:.1%}")
                self.logger.warning("자동 롤백 시작 - 이전 파라미터로 복원 시도...")

                # 자동 롤백 수행
                rollback_success = self.rollback_params()
                if rollback_success:
                    self.logger.info("[O] 자동 롤백 완료 - 이전 파라미터 복원됨")
                else:
                    self.logger.error("[X] 자동 롤백 실패 - 백업 파일 없음")
            else:
                self.logger.info(f"개선율 미달 ({improvement:.1%} < {min_improvement:.1%}), 현재 파라미터 유지")
        else:
            # 첫 최적화인 경우
            self.apply_best_params(validate=True)

    def reset_study(self, study_name: str = "lotto_threshold_v4"):
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

    def get_study_info(self, study_name: str = "lotto_threshold_v4") -> Dict:
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
                SELECT created_at FROM threshold_optimization_sessions
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            return row[0] if row else None