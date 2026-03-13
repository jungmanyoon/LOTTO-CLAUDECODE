"""
자동 임계값 최적화 시스템
24시간 주기로 백테스팅을 실행하고 최적 임계값을 자동으로 업데이트
"""
import os
import sys
import time
import logging
import schedule
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import yaml

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.threshold_optimizer import ThresholdOptimizer
from src.core.performance_stats_manager import PerformanceStatsManager
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
from src.core.db_manager import DatabaseManager
from src.core.integrated_filter_manager import IntegratedFilterManager
from src.core.optimization_checkpoint_manager import get_checkpoint_manager
from src.core.threshold_manager import get_threshold_manager
try:
    from src.utils.logging_setup import setup_logging
except ImportError:
    from src.logger import setup_logging

class AutoThresholdOptimizer:
    """자동 임계값 최적화 실행기"""

    def __init__(self):
        # 로거 초기화 (항상 기본 로거 사용)
        import logging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # ThresholdManager 연동 (Single Source of Truth)
        self.threshold_manager = get_threshold_manager()
        self.threshold_manager.load_from_config()  # 설정 파일에서 초기 로드

        self.optimizer = ThresholdOptimizer()
        self.stats_manager = PerformanceStatsManager()
        self.db_manager = DatabaseManager()
        self.checkpoint_manager = get_checkpoint_manager()  # 체크포인트 관리자 추가
        self.config_path = "configs/adaptive_filter_config.yaml"  # 설정 파일 경로

        # 최적화 설정
        self.optimization_config = {
            'n_trials': 25,  # Optuna 시도 횟수 (누적 학습이므로 적당한 횟수로 자주 실행)
            'interval_hours': 24,  # 최적화 주기 (시간)
            'min_improvement': 0.05,  # 최소 개선율 (5%)
            'validation_rounds': 50,  # 검증 라운드 수
            'max_avg_matches': 2.0,  # 데이터 오염 임계값
            'target_ml_inclusion': 0.15  # 목표 ML 포함률
        }

        # 상태 추적
        self.last_optimization_time = None
        self.optimization_count = 0
        self.best_score_history = []

        # Task 7: ml_inclusion_rate 추적 (최근 10 trials)
        self.recent_inclusion_rates = []

        # 외부 종료 플래그 (백그라운드 스레드 종료 감지용)
        self._shutdown_flag = None

        # 현재 설정 로드
        self.current_config = self._load_current_config()

    def _load_current_config(self) -> Dict:
        """현재 설정 파일 로드"""
        try:
            with open("configs/adaptive_filter_config.yaml", 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # yaml.safe_load는 빈 파일에서 None 반환 가능
                return config if config is not None else {}
        except Exception as e:
            self.logger.error(f"설정 파일 로드 실패: {e}")
            return {}

    def set_shutdown_flag(self, flag: dict):
        """외부 종료 플래그 설정 (프레임워크 + 옵티마이저에 전파)"""
        self._shutdown_flag = flag
        # ThresholdOptimizer에도 전파
        if hasattr(self, 'optimizer') and self.optimizer:
            self.optimizer.set_shutdown_flag(flag)

    def run_backtesting_with_config(self, config: Dict, start_round: int = None, end_round: int = None) -> Dict[str, Any]:
        """특정 설정으로 백테스팅 실행 (최적화됨 - 싱글톤 재사용)

        Args:
            config: 설정 딕셔너리
            start_round: 시작 회차 (None이면 기본값 사용 - 최근 50회차)
            end_round: 종료 회차 (None이면 기본값 사용 - 최근 50회차)
        """
        # Windows 백그라운드 스레드 tqdm 호환성: 매 호출 시 sys.stderr 안전화
        import sys
        try:
            sys.stderr.write('')
            sys.stderr.flush()
        except (OSError, ValueError, AttributeError):
            sys.stderr = sys.stdout
        try:
            # ============================================================
            # ThresholdManager를 통한 중앙 파라미터 설정 (Single Source of Truth)
            # ============================================================
            threshold = config.get('global_probability_threshold', 1.0)
            ml_bypass = config.get('ml_integration', {}).get('ml_bypass_filters', 8)
            ml_weight = config.get('ml_integration', {}).get('ml_weight', 0.4)

            # ThresholdManager에 설정 (모든 컴포넌트에 자동 전파)
            self.threshold_manager.set_threshold(threshold, source="optimizer")
            self.threshold_manager.set_ml_bypass_filters(ml_bypass, source="optimizer")
            self.threshold_manager.set_ml_weight(ml_weight, source="optimizer")

            self.logger.info(f"=== 백테스팅 시작 ===")
            self.logger.info(f"  Threshold: {threshold:.2f}% (ThresholdManager 적용)")
            self.logger.info(f"  ML Bypass: {ml_bypass} (ThresholdManager 적용)")
            self.logger.info(f"  ML Weight: {ml_weight:.2f} (ThresholdManager 적용)")

            # ============================================================
            # 🚀 PERFORMANCE FIX: 싱글톤 재사용 (재초기화 제거)
            # ============================================================
            # 기존 싱글톤 인스턴스 재사용 (백테스팅 프레임워크는 한 번만 초기화)
            from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework

            framework = OptimizedBacktestingFramework.get_instance()
            if framework is None:
                # 첫 실행시에만 초기화
                framework = OptimizedBacktestingFramework(
                    db_manager=self.db_manager,
                    enable_fractal=False  # 속도를 위해 프랙탈 분석 비활성화
                )
                self.logger.info("[싱글톤] 백테스팅 프레임워크 첫 초기화")
            else:
                self.logger.info("[싱글톤] 기존 백테스팅 프레임워크 재사용")

            # ============================================================
            # 🔍 CRITICAL: 파라미터만 업데이트 (재초기화 없음)
            # ============================================================
            # update_parameters 메서드로 파라미터만 변경
            framework.update_parameters(
                threshold=threshold,
                ml_bypass=ml_bypass,
                ml_weight=ml_weight
            )

            # 파라미터 업데이트 후 상태 로깅
            self.logger.info(f"[파라미터 업데이트] 완료:")
            self.logger.info(f"  - probability_threshold: {threshold}")
            self.logger.info(f"  - ml_bypass_filters: {ml_bypass}")
            self.logger.info(f"  - ml_weight: {ml_weight}")

            # 백테스팅 실행 (고정 검증 세트 또는 슬라이딩 윈도우)
            if start_round is not None and end_round is not None:
                # 고정 검증 세트 사용 (ThresholdOptimizer에서 전달)
                backtest_range = (start_round, end_round)
                self.logger.info(f"[고정 검증] {backtest_range[0]}~{backtest_range[1]} 회차 사용")
            else:
                # 동적 검증 범위 계산 (hold-out 테스트셋 오염 방지)
                # ThresholdOptimizer._update_validation_range()와 동일한 로직:
                #   훈련  -> 1 ~ (latest - 2*window - 1)
                #   검증  -> (latest - 2*window) ~ (latest - window - 1)  <- 이 범위 사용
                #   테스트 -> (latest - window) ~ (latest - 1)            <- hold-out (미사용)
                try:
                    all_numbers = self.db_manager.get_all_winning_numbers()
                    if all_numbers:
                        latest = max(r for r, _ in all_numbers)
                    else:
                        latest = 1186  # DB 조회 실패 시 보수적 폴백
                except Exception:
                    latest = 1186
                window = 100
                test_set_start = max(1, latest - window)
                validation_end = max(1, test_set_start - 1)
                validation_start = max(1, validation_end - window + 1)
                backtest_range = (validation_start, validation_end)
                self.logger.info(f"[검증 범위] {backtest_range[0]}~{backtest_range[1]} 회차 (hold-out {test_set_start}~{latest-1} 제외)")

            # 종료 플래그 전파: 백테스팅 프레임워크에도 전달
            if self._shutdown_flag:
                framework.set_shutdown_flag(self._shutdown_flag)

            # FIX-01: 백테스트 실행 전 이전 상태 강제 초기화
            # 이유: Optuna Trial마다 독립적인 백테스트 수행이 필요
            framework.clear_state()
            framework.processed_rounds.clear()

            self.logger.info(f"[TRACE] run_backtest() 호출 중... (rounds {backtest_range[0]}-{backtest_range[1]})")
            results = framework.run_backtest(
                start_round=backtest_range[0],
                end_round=backtest_range[1]
            )
            self.logger.info(f"[TRACE] run_backtest() 완료")

            # 성능 메트릭 계산
            performance_metrics = self._calculate_performance_metrics(results, config)

            # 결과 로깅
            self.logger.info(f"=== 백테스팅 결과 ===")
            self.logger.info(f"  Avg Matches: {performance_metrics.get('avg_matches', 0):.3f}")
            self.logger.info(f"  ML Inclusion: {performance_metrics.get('ml_inclusion_rate', 0):.3f}")
            self.logger.info(f"  Combinations: {performance_metrics.get('combination_count', 0):,}")

            return performance_metrics

        except Exception as e:
            self.logger.error(f"백테스팅 실행 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'avg_matches': 0,
                'ml_inclusion_rate': 0,
                'combination_count': 0,
                'error': str(e)
            }

    def _calculate_performance_metrics(self, backtest_results: Dict, config: Dict) -> Dict[str, Any]:
        """백테스팅 결과에서 성능 메트릭 추출"""
        try:
            performance_metrics = backtest_results.get('performance_metrics', {})
            model_performances = performance_metrics.get('model_performance', {})

            # ✅ DEBUG: 실제 백테스팅 결과 구조 로깅
            self.logger.info(f"[METRICS DEBUG] 모델 수: {len(model_performances)}")

            # 전체 평균 매칭 계산
            total_matches = 0
            total_predictions = 0
            ml_included_count = 0
            ml_total_count = 0

            for model_name, model_metrics in model_performances.items():
                avg_matches = model_metrics.get('avg_matches', 0)
                predictions = model_metrics.get('total_predictions', 0)
                filter_passed = model_metrics.get('filter_passed_count', 0)

                total_matches += avg_matches * predictions
                total_predictions += predictions

                # ✅ DEBUG: 각 모델별 상세 로깅
                self.logger.debug(f"[MODEL] {model_name}: avg={avg_matches:.3f}, pred={predictions}, filter_passed={filter_passed}")

                # ML 모델 포함률 계산 (모든 모델 포함)
                # ✅ FIX: 모든 모델의 filter_passed_count 사용 (ML 모델만 아님)
                if 'filter_passed_count' in model_metrics:
                    ml_total_count += predictions
                    ml_included_count += filter_passed
                    pass_rate = (filter_passed / predictions * 100) if predictions > 0 else 0
                    self.logger.debug(f"[FILTER_PASSED] {model_name}: {filter_passed}/{predictions} = {pass_rate:.1f}%")
                else:
                    # filter_passed_count가 없는 경우에만 fallback
                    if 'ml' in model_name.lower() or 'lstm' in model_name.lower() or 'ensemble' in model_name.lower():
                        ml_total_count += predictions
                        estimated_rate = self._get_recent_avg_inclusion_rate()
                        ml_included_count += predictions * estimated_rate
                        self.logger.debug(f"[FALLBACK] {model_name}: {predictions} * {estimated_rate:.3f}")

            avg_matches = total_matches / total_predictions if total_predictions > 0 else 0
            ml_inclusion_rate = ml_included_count / ml_total_count if ml_total_count > 0 else 0

            # ✅ DEBUG: 최종 계산 결과 로깅
            self.logger.info(f"[METRICS RESULT] avg_matches={avg_matches:.4f}, ml_inclusion={ml_inclusion_rate:.4f} ({ml_inclusion_rate*100:.1f}%)")

            # 필터링된 조합 수 추출
            filter_stats = backtest_results.get('filter_statistics', {})
            combination_count = filter_stats.get('total_combinations_after_filter', 300000)

            # Task 7: ml_inclusion_rate 이력 저장 (최근 10개 유지)
            if ml_inclusion_rate > 0:
                self.recent_inclusion_rates.append(ml_inclusion_rate)
                if len(self.recent_inclusion_rates) > 10:
                    self.recent_inclusion_rates.pop(0)

            return {
                'avg_matches': avg_matches,
                'ml_inclusion_rate': ml_inclusion_rate,
                'combination_count': combination_count,
                'total_predictions': total_predictions,
                'threshold': config.get('global_probability_threshold'),
                'ml_bypass': config.get('ml_integration', {}).get('ml_bypass_filters'),
                'ml_weight': config.get('ml_integration', {}).get('ml_weight')
            }

        except Exception as e:
            self.logger.error(f"성능 메트릭 계산 실패: {e}")
            return {
                'avg_matches': 0,
                'ml_inclusion_rate': 0,
                'combination_count': 0
            }

    def _get_recent_avg_inclusion_rate(self) -> float:
        """
        Task 7: 최근 trial들의 평균 ml_inclusion_rate 반환

        Returns:
            float: 최근 평균 (없으면 0.085 - 실제 ML 포함률 기반)

        Note:
            - ML 예측이 필터를 통과하는 비율은 약 8.5% (0.085)
            - 93%는 잘못된 값이었음 (점수 왜곡 원인)
            - 목표: 15% (0.15) 달성
        """
        if self.recent_inclusion_rates:
            avg = sum(self.recent_inclusion_rates) / len(self.recent_inclusion_rates)
            self.logger.debug(f"[Recent avg inclusion] {len(self.recent_inclusion_rates)} trials: {avg:.3f}")
            return avg
        else:
            # ✅ FIX: 실제 ML 포함률 8.5% 사용 (기존 93%는 잘못된 값)
            # 이 값은 ML 예측이 필터를 통과하는 실제 비율
            default_rate = 0.085
            self.logger.debug(f"[Default inclusion] Using default: {default_rate:.3f}")
            return default_rate

    def optimize_with_optuna(self, n_trials: int = 10, infinite_mode: bool = False):
        """
        Optuna TPE sampler를 사용한 지능적 최적화 (중단/재시작 지원)

        Args:
            n_trials: 이번에 실행할 trial 수 (기존 study에 추가)
            infinite_mode: True이면 n_trials 완료 후 계속 반복 (무한 반복)

        Note:
            탐색 공간 (ThresholdOptimizer에서 정의):
            - probability_threshold: 1.0~3.0 (기존 1.8~2.0에서 확대)
            - ml_bypass_filters: 10~20 (기존 15 고정에서 확대)
            - ml_weight: 0.3~0.8 (기존 0.6 고정에서 확대)
        """
        self.logger.info("=" * 60)
        self.logger.info(f"🔬 Optuna TPE 기반 최적화 시작 - {datetime.now()}")
        if infinite_mode:
            self.logger.info(f"⚡ 무한 반복 모드 활성화 - {n_trials}회 trial 후 자동 재시작")
        self.logger.info("=" * 60)

        try:
            # 백테스팅 함수 정의 (고정 검증 세트 지원)
            def backtesting_func(config, start_round=None, end_round=None):
                """백테스팅 실행 및 결과 반환

                Args:
                    config: 설정 딕셔너리
                    start_round: 시작 회차 (ThresholdOptimizer에서 전달)
                    end_round: 종료 회차 (ThresholdOptimizer에서 전달)
                """
                return self.run_backtesting_with_config(config, start_round, end_round)

            # Optuna 최적화 실행 (CMA-ES sampler 사용)
            # study_name 미지정 → ThresholdOptimizer 기본값 "lotto_threshold_v4" 사용
            # (v4 목적함수: ml_inclusion 제거, pool_penalty=0.05, INCLUSION_THRESHOLD=0.99)
            result = self.optimizer.optimize(
                backtesting_func=backtesting_func,
                n_trials=n_trials,
                n_jobs=1,
            )

            # 수렴 감지: result에 converged 플래그 확인
            if result.get('converged', False):
                self.logger.info(f"[CONVERGED] 최적화 수렴 감지: {result.get('convergence_reason', 'unknown')}")
                # 수렴 시 최적 파라미터 적용
                if result.get('best_params'):
                    self._apply_best_params(result['best_params'])
                return {
                    'status': 'converged',
                    'converged': True,
                    'convergence_reason': result.get('convergence_reason'),
                    'best_params': result['best_params'],
                    'best_score': result['best_score'],
                    'total_trials': result['total_trials']
                }

            # 최적 파라미터 적용
            if result.get('best_params'):
                self._apply_best_params(result['best_params'])

            # 무한 모드이면 계속 진행
            if infinite_mode:
                self.logger.info(f"♻️ 무한 반복 모드: {n_trials}회 trial 완료, 다음 사이클 시작...")
                return {
                    'status': 'cycle_completed',
                    'best_params': result['best_params'],
                    'best_score': result['best_score'],  # best_value -> best_score 수정
                    'total_trials': result['total_trials'],
                    'message': f'Completed {n_trials} trials, continuing...'
                }

            return {
                'status': 'completed',
                'best_params': result['best_params'],
                'best_score': result['best_score'],  # best_value -> best_score 수정
                'total_trials': result['total_trials']
            }

        except Exception as e:
            self.logger.error(f"Optuna 최적화 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {'status': 'error', 'error': str(e)}

    def optimize_with_checkpoint(self, infinite_mode: bool = False):
        """
        체크포인트를 사용한 점진적 최적화 (DEPRECATED - Grid Search 방식)

        ⚠️ 이 메서드는 Grid Search 방식이며 deprecated 되었습니다.
        대신 optimize_with_optuna()를 사용하세요.

        Args:
            infinite_mode: True이면 140개 조합 완료 후 자동으로 재시작 (무한 반복)
        """
        self.logger.warning("⚠️ optimize_with_checkpoint()는 Grid Search 방식이며 deprecated 되었습니다.")
        self.logger.warning("   대신 optimize_with_optuna()를 사용하세요.")
        self.logger.info("=" * 60)
        self.logger.info(f"체크포인트 기반 최적화 시작 (Grid Search) - {datetime.now()}")
        if infinite_mode:
            self.logger.info("⚡ 무한 반복 모드 활성화 - 140개 조합 완료 후 자동 재시작")
        self.logger.info("=" * 60)

        try:
            # 현재 로또 회차 확인
            all_numbers = self.db_manager.get_all_winning_numbers()
            if all_numbers:
                # get_all_winning_numbers returns List[Tuple[round_num, numbers]]
                current_round = max(item[0] for item in all_numbers)
            else:
                current_round = 0

            # 로또 회차 업데이트 확인
            if self.checkpoint_manager.check_lottery_update(current_round):
                self.logger.info(f"🔄 로또 회차 {current_round}로 업데이트됨. 최적화 초기화.")
                self.checkpoint_manager.reset_optimization_progress()

            # 세션 시작
            if not self.checkpoint_manager.checkpoint['current_optimization']['session_id']:
                session_id = self.checkpoint_manager.start_optimization_session(current_round)
                self.logger.info(f"새 최적화 세션 시작: {session_id}")

            # 진행상황 리포트
            self.logger.info(self.checkpoint_manager.get_optimization_report())

            # 다음 조합 가져오기
            next_combination = self.checkpoint_manager.get_next_combination()

            if next_combination:
                threshold, ml_bypass, ml_weight = next_combination

                # 설정 생성
                test_config = self.current_config.copy()
                test_config['global_probability_threshold'] = threshold
                test_config['ml_integration']['ml_bypass_filters'] = ml_bypass
                test_config['ml_integration']['ml_weight'] = ml_weight

                # 백테스팅 실행
                self.logger.info(f"테스트 중: 임계값={threshold}, ML바이패스={ml_bypass}, ML가중치={ml_weight}")
                result = self.run_backtesting_with_config(test_config)

                # 점수 계산
                score = self._calculate_optimization_score(result)
                result['score'] = score

                # 결과 저장
                self.checkpoint_manager.mark_combination_complete(threshold, ml_bypass, ml_weight, result)

                # 개선 확인
                if score > 0:
                    improvement = result.get('avg_matches', 0) - 0
                    self.logger.info(f"개선: +{improvement:.3f}")

                return {
                    'status': 'in_progress',
                    'current_combination': next_combination,
                    'result': result,
                    'progress': self.checkpoint_manager.get_progress_summary()
                }
            else:
                self.logger.info("✅ 모든 조합 테스트 완료!")

                # 최적 파라미터 적용
                summary = self.checkpoint_manager.get_progress_summary()
                if summary['best_params']:
                    self._apply_best_params(summary['best_params'])

                # 무한 모드이면 체크포인트 초기화하고 계속 진행
                if infinite_mode:
                    self.logger.info("♻️ 무한 반복 모드: 체크포인트 초기화하고 다음 사이클 시작...")
                    # 최적 파라미터는 유지하되, 테스트 진행상황만 초기화
                    best_params_backup = summary['best_params']
                    best_score_backup = summary['best_score']

                    self.checkpoint_manager.reset_optimization_progress()

                    # 다음 사이클 시작
                    session_id = self.checkpoint_manager.start_optimization_session(current_round)
                    self.logger.info(f"🔄 새 사이클 시작: {session_id}")
                    self.logger.info(f"📊 이전 사이클 최적 파라미터: {best_params_backup} (점수: {best_score_backup:.3f})")

                    # 계속 진행 상태로 반환
                    return {
                        'status': 'cycle_completed',
                        'best_params': best_params_backup,
                        'best_score': best_score_backup,
                        'message': 'Cycle completed, starting new cycle'
                    }

                return {
                    'status': 'completed',
                    'best_params': summary['best_params'],
                    'best_score': summary['best_score']
                }

        except Exception as e:
            self.logger.error(f"체크포인트 최적화 실패: {e}")
            return {'status': 'error', 'error': str(e)}

    def _calculate_optimization_score(self, result: Dict) -> float:
        """최적화 점수 계산"""
        avg_matches = result.get('avg_matches', 0)
        ml_inclusion = result.get('ml_inclusion_rate', 0)
        combination_count = result.get('combination_count', 300000)

        # 평균 매칭 점수
        if 0.8 <= avg_matches <= 1.5:
            match_score = 1.0
        elif avg_matches < 0.8:
            match_score = avg_matches / 0.8
        else:
            match_score = max(0, 2.0 - avg_matches / 1.5)

        # ML 포함률 점수
        inclusion_score = min(1.0, ml_inclusion / 0.15)

        # 조합 수 점수
        if 200000 <= combination_count <= 400000:
            combination_score = 1.0
        elif combination_count < 200000:
            combination_score = combination_count / 200000
        else:
            combination_score = max(0, 1.0 - (combination_count - 400000) / 400000)

        # 가중 평균
        return (match_score * 0.4 + inclusion_score * 0.3 + combination_score * 0.3)

    def _apply_best_params(self, params: Dict):
        """최적 파라미터 적용"""
        try:
            config = self._load_current_config()

            # config가 비어있으면 에러 처리
            if not config:
                self.logger.error("설정 파일이 비어있거나 로드 실패")
                return

            # 필수 키 확인 및 초기화
            if 'ml_integration' not in config:
                config['ml_integration'] = {}

            # ✅ PRECISION FIX: round()로 부동소수점 오차 제거
            config['global_probability_threshold'] = round(params['threshold'], 2)
            config['ml_integration']['ml_bypass_filters'] = params['ml_bypass']
            config['ml_integration']['ml_weight'] = round(params['ml_weight'], 2)

            # 백업 후 저장
            backup_path = f"configs/adaptive_filter_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
            with open(self.config_path, 'r', encoding='utf-8') as f:
                backup_config = yaml.safe_load(f)
            with open(backup_path, 'w', encoding='utf-8') as f:
                yaml.dump(backup_config, f, allow_unicode=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)

            # 로그 출력 시 부동소수점 정리
            formatted_params = {k: round(v, 2) if isinstance(v, float) else v for k, v in params.items()}
            self.logger.info(f"✅ 최적 파라미터 적용: {formatted_params}")

        except Exception as e:
            self.logger.error(f"파라미터 적용 실패: {e}")

    def reset_study(self, study_name: str = None):
        """
        Optuna study 초기화 (새 회차 데이터 감지 시 호출)

        새 로또 번호가 발표되면 기존 학습 데이터가 더 이상 유효하지 않을 수 있으므로
        study를 초기화하고 처음부터 최적화를 시작합니다.

        Args:
            study_name: 초기화할 스터디 이름 (None이면 기본값 사용)
        """
        try:
            if study_name is None:
                study_name = "lotto_threshold_v4"

            # ThresholdOptimizer의 reset_study 호출
            result = self.optimizer.reset_study(study_name=study_name)

            if result:
                self.logger.info(f"🔄 [AutoThresholdOptimizer] Study '{study_name}' 초기화 완료")
                self.logger.info("   → 새 회차 데이터로 처음부터 최적화 시작")

                # 내부 상태도 초기화
                self.best_score_history = []
                self.recent_inclusion_rates = []
                self.optimization_count = 0
            else:
                self.logger.warning(f"[AutoThresholdOptimizer] Study 초기화 실패 (이미 없을 수 있음)")

            return result

        except Exception as e:
            self.logger.error(f"[AutoThresholdOptimizer] Study 초기화 중 오류: {e}")
            return False

    def optimize_threshold(self):
        """임계값 최적화 실행 (기존 방식 유지)"""
        self.logger.info("=" * 60)
        self.logger.info(f"자동 임계값 최적화 시작 - {datetime.now()}")
        self.logger.info("=" * 60)

        try:
            # 현재 최적 성능 조회
            current_best = self.optimizer.get_current_best_params()
            current_score = current_best['score'] if current_best else 0

            self.logger.info(f"현재 최적 점수: {current_score:.3f}")

            # Optuna 최적화 실행 (고정된 study_name으로 누적 학습)
            optimization_results = self.optimizer.optimize(
                backtesting_func=self.run_backtesting_with_config,
                n_trials=self.optimization_config['n_trials'],
                n_jobs=1,  # 단일 프로세스로 실행 (안정성)
                study_name=None  # None이면 기본값 "lotto_threshold_v4" 사용 (누적 학습)
            )

            # 결과 분석
            new_score = optimization_results['best_score']
            improvement = (new_score - current_score) / current_score if current_score > 0 else 1.0

            self.logger.info(f"새로운 최적 점수: {new_score:.3f}")
            self.logger.info(f"개선율: {improvement:.1%}")

            # 개선이 있으면 적용
            if improvement >= self.optimization_config['min_improvement']:
                self.logger.info("충분한 개선 확인 - 새 파라미터 적용")

                # 검증 실행
                if self._validate_new_params(optimization_results):
                    # 최적 파라미터 적용
                    success = self.optimizer.apply_best_params(validate=False)

                    if success:
                        self.logger.info("✅ 새 파라미터 적용 완료")
                        self._send_notification(
                            f"임계값 최적화 완료: {optimization_results['best_params']['threshold']:.1f}%",
                            optimization_results
                        )
                    else:
                        self.logger.error("파라미터 적용 실패")
                else:
                    self.logger.warning("검증 실패 - 기존 파라미터 유지")
            else:
                self.logger.info(f"개선율 미달 ({improvement:.1%} < {self.optimization_config['min_improvement']:.1%})")
                self.logger.info("기존 파라미터 유지")

            # 통계 업데이트
            self.optimization_count += 1
            self.last_optimization_time = datetime.now()
            self.best_score_history.append(new_score)

            # 성능 리포트 생성
            self._generate_performance_report(optimization_results)

        except Exception as e:
            self.logger.error(f"최적화 실행 실패: {e}")
            self._send_notification("임계값 최적화 실패", {'error': str(e)})

    def _validate_new_params(self, optimization_results: Dict) -> bool:
        """새 파라미터 검증"""
        try:
            # 데이터 오염 확인
            avg_matches = optimization_results.get('avg_matches', 0)
            if avg_matches > self.optimization_config['max_avg_matches']:
                self.logger.warning(f"데이터 오염 의심 - 평균 매칭: {avg_matches:.3f}")
                return False

            # ML 포함률 확인
            ml_inclusion = optimization_results.get('ml_inclusion_rate', 0)
            if ml_inclusion < 0.05:  # 최소 5%
                self.logger.warning(f"ML 포함률 너무 낮음: {ml_inclusion:.1%}")
                return False

            # 조합 수 확인
            combination_count = optimization_results.get('combination_count', 0)
            if combination_count < 100000 or combination_count > 600000:
                self.logger.warning(f"비정상적인 조합 수: {combination_count:,}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"검증 실패: {e}")
            return False

    def _generate_performance_report(self, optimization_results: Dict):
        """성능 리포트 생성"""
        try:
            # 최근 성능 이력 조회
            history = self.stats_manager.get_threshold_performance_history(limit=10)

            # 최적 임계값 통계
            optimal_stats = self.stats_manager.get_optimal_threshold_stats()

            report = f"""
╔════════════════════════════════════════════════════════════╗
║                  임계값 최적화 리포트                          ║
╠════════════════════════════════════════════════════════════╣
║ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
║ 총 최적화 횟수: {self.optimization_count}
║
║ [현재 최적 파라미터]
║ - 확률 임계값: {optimization_results['best_params']['threshold']:.1f}%
║ - ML Bypass 필터: {optimization_results['best_params']['ml_bypass']}개
║ - ML 가중치: {optimization_results['best_params']['ml_weight']:.2f}
║
║ [성능 지표]
║ - 최적화 점수: {optimization_results['best_score']:.3f}
║ - 평균 매칭: {optimization_results.get('avg_matches', 0):.3f}
║ - ML 포함률: {optimization_results.get('ml_inclusion_rate', 0):.1%}
║ - 조합 수: {optimization_results.get('combination_count', 0):,}
║
║ [최근 5회 점수 추이]
"""
            for i, score in enumerate(self.best_score_history[-5:], 1):
                report += f"║   {i}. {score:.3f}\n"

            report += """╚════════════════════════════════════════════════════════════╝
"""
            self.logger.info(report)

            # 파일로 저장
            report_path = f"logs/threshold_optimization_{datetime.now().strftime('%Y%m%d')}.txt"
            with open(report_path, 'a', encoding='utf-8') as f:
                f.write(report)

        except Exception as e:
            self.logger.error(f"리포트 생성 실패: {e}")

    def _send_notification(self, title: str, data: Dict):
        """알림 전송 (추후 구현 가능)"""
        # 이메일, 슬랙, 텔레그램 등으로 알림 전송 가능
        self.logger.info(f"📢 알림: {title}")

    def schedule_optimization(self):
        """최적화 스케줄 설정"""
        # 매일 새벽 3시에 실행
        schedule.every().day.at("03:00").do(self.optimize_threshold)

        # 12시간마다 간단한 체크
        schedule.every(12).hours.do(self.check_performance)

        self.logger.info("최적화 스케줄 설정 완료")
        self.logger.info("- 전체 최적화: 매일 03:00")
        self.logger.info("- 성능 체크: 12시간마다")

    def check_performance(self):
        """현재 성능 체크 (간단한 확인)"""
        try:
            # 최근 백테스팅 결과 확인
            recent_stats = self.stats_manager.get_latest_performance(limit=1)

            if recent_stats:
                latest = recent_stats[0]
                self.logger.info(f"최근 성능 - 평균 매칭: {latest.get('avg_matches', 0):.3f}")

                # 성능이 크게 떨어진 경우 즉시 최적화
                if latest.get('avg_matches', 0) < 0.5:
                    self.logger.warning("성능 저하 감지 - 즉시 최적화 실행")
                    self.optimize_threshold()

        except Exception as e:
            self.logger.error(f"성능 체크 실패: {e}")

    def run_continuous(self):
        """연속 실행 모드"""
        self.logger.info("자동 임계값 최적화 시스템 시작")

        # 초기 최적화 실행
        self.optimize_threshold()

        # 스케줄 설정
        self.schedule_optimization()

        # 무한 루프 실행
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 체크

            except KeyboardInterrupt:
                self.logger.info("사용자 중단 요청")
                break
            except Exception as e:
                self.logger.error(f"실행 오류: {e}")
                time.sleep(300)  # 5분 대기 후 재시도

    def run_once(self):
        """단일 실행 모드"""
        self.logger.info("단일 최적화 실행 모드")
        self.optimize_threshold()

        # 결과 요약 출력
        self.logger.info("\n최적화 완료!")
        best_params = self.optimizer.get_current_best_params()
        if best_params:
            self.logger.info(f"최적 임계값: {best_params['threshold']:.1f}%")
            self.logger.info(f"ML Bypass: {best_params['ml_bypass']}개")
            self.logger.info(f"ML 가중치: {best_params['ml_weight']:.2f}")


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='자동 임계값 최적화 시스템')
    parser.add_argument('--mode', choices=['once', 'continuous'], default='once',
                       help='실행 모드 (once: 단일 실행, continuous: 연속 실행)')
    parser.add_argument('--trials', type=int, default=30,
                       help='Optuna 시도 횟수')
    parser.add_argument('--rollback', action='store_true',
                       help='이전 설정으로 롤백')

    args = parser.parse_args()

    # 최적화 실행
    optimizer = AutoThresholdOptimizer()

    if args.rollback:
        # 롤백 실행
        success = optimizer.optimizer.rollback_params()
        if success:
            print("✅ 파라미터 롤백 완료")
        else:
            print("❌ 파라미터 롤백 실패")
    else:
        # 시도 횟수 설정
        optimizer.optimization_config['n_trials'] = args.trials

        # 모드별 실행
        if args.mode == 'once':
            optimizer.run_once()
        else:
            optimizer.run_continuous()


if __name__ == "__main__":
    main()