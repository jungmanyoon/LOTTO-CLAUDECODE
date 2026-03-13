#!/usr/bin/env python3
"""
통합 최적화기 (UnifiedOptimizer)
Phase 3: SmartAutoLearning(레이어 1) + BackgroundOptimization(레이어 2) 통합

- 단일 백그라운드 스레드로 Optuna CMA-ES 최적화 + 정기 피드백 루프 수행
- 상태는 OptimizationDB(data/optimization.db)에 저장 (JSON 파일 불필요)
- 종료 플래그(stop_flag)를 AutoThresholdOptimizer → OptimizedBacktestingFramework 체인으로 전파
"""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from src.core.optimization_db import get_optimization_db

# 피드백 루프 실행 간격 (분) - 구 SmartAutoLearning.min_interval_minutes
_FEEDBACK_INTERVAL_MINUTES = 30


class UnifiedOptimizer:
    """
    통합 최적화기: Optuna CMA-ES 백그라운드 최적화 + 정기 피드백 루프를
    하나의 백그라운드 스레드로 실행하는 단일 진입점.
    """

    def __init__(self, db_manager, config_path: str = 'configs/adaptive_filter_config.yaml'):
        self.db_manager = db_manager
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        self._opt_db = get_optimization_db()

        self._stop_flag: Dict = {'stop': False}
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def start_background(self, stop_flag: Optional[Dict] = None) -> threading.Thread:
        """
        백그라운드 최적화 스레드 시작.
        stop_flag는 외부(main.py)에서 종료 신호를 보낼 때 사용하는 공유 dict.
        """
        if stop_flag is not None:
            self._stop_flag = stop_flag

        self._running = True
        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="UnifiedOptimizer"
        )
        self._thread.start()
        self.logger.info("[UnifiedOptimizer] 백그라운드 최적화 시작")
        self.logger.info("   - Optuna CMA-ES 기반 Bayesian 최적화 (10 trials/cycle)")
        self.logger.info("   - 피드백 루프 주기: 30분마다")
        self.logger.info("   - 상태 저장: data/optimization.db")
        return self._thread

    def run_optimization_cycle(self, n_trials: int = 10) -> Dict:
        """단일 최적화 사이클 실행 (동기, 테스트 및 수동 호출용)"""
        from src.scripts.auto_threshold_optimizer import AutoThresholdOptimizer
        optimizer = AutoThresholdOptimizer()
        optimizer.set_shutdown_flag(self._stop_flag)
        return optimizer.optimize_with_optuna(n_trials=n_trials)

    def get_status(self) -> Dict:
        """현재 상태 반환"""
        return {
            'is_running': self._running,
            'stop_flag': self._stop_flag.get('stop', False),
            'last_best_params': self._opt_db.get_state('last_best_params'),
            'last_best_score': self._opt_db.get_state('last_best_score', 0),
            'total_cycles': self._opt_db.get_state('total_cycles', 0),
            'last_feedback_time': self._opt_db.get_state('last_feedback_time'),
        }

    def stop(self):
        """백그라운드 최적화 중지"""
        self._stop_flag['stop'] = True
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                self.logger.warning("[UnifiedOptimizer] 스레드가 30초 내에 종료되지 않음 (daemon으로 강제 종료)")
            else:
                self.logger.info("[UnifiedOptimizer] 스레드 정상 종료 완료")
        self.logger.info("[UnifiedOptimizer] 최적화 중지")

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _worker(self):
        """
        백그라운드 워커.
        1) Optuna CMA-ES 최적화 사이클 (10 trials)
        2) 30분마다 피드백 루프 (EnhancedFeedbackLoop)
        """
        # AutoThresholdOptimizer 초기화
        try:
            from src.scripts.auto_threshold_optimizer import AutoThresholdOptimizer
            optimizer = AutoThresholdOptimizer()
            optimizer.set_shutdown_flag(self._stop_flag)
        except Exception as e:
            self.logger.error(f"[UnifiedOptimizer] 초기화 실패: {e}")
            self._running = False
            return

        self.logger.info("[UnifiedOptimizer] 워커 스레드 시작")
        self.logger.info("   - 무한 반복 모드 (10 trials per cycle)")
        self.logger.info("   - 누적 학습: 0->10->20->30... (지능적 파라미터 탐색)")
        self.logger.info("   - SQLite 기반 persistence (자동 중단/재시작)")
        self.logger.info("   - 수렴 감지: patience=50, threshold=1%, max_trials=500")

        cycle_count = self._opt_db.get_state('total_cycles', 0)
        converged = False
        last_feedback_time: Optional[datetime] = None

        # 마지막 피드백 시간 복원
        last_fb_str = self._opt_db.get_state('last_feedback_time')
        if last_fb_str:
            try:
                last_feedback_time = datetime.fromisoformat(last_fb_str)
            except (ValueError, TypeError):
                last_feedback_time = None

        while not self._stop_flag.get('stop', False) and not converged:
            try:
                # ---- 1. Optuna 최적화 사이클 ----
                result = optimizer.optimize_with_optuna(n_trials=10, infinite_mode=True)

                # 수렴 감지
                if result.get('converged', False):
                    converged = True
                    convergence_reason = result.get('convergence_reason', 'unknown')
                    self.logger.info(f"[CONVERGED] [UnifiedOptimizer] 최적화 수렴: {convergence_reason}")
                    self.logger.info(f"   최적 파라미터: threshold={result['best_params']['threshold']:.2f}%, "
                                     f"ml_bypass={result['best_params']['ml_bypass']}, "
                                     f"ml_weight={result['best_params']['ml_weight']:.2f}")
                    self.logger.info(f"   최적 점수: {result['best_score']:.4f}")
                    self.logger.info(f"   총 누적 trials: {result['total_trials']}개")
                    break

                if result['status'] == 'cycle_completed':
                    cycle_count += 1
                    total_trials = result.get('total_trials', cycle_count * 10)
                    self.logger.info(f"[UnifiedOptimizer] 사이클 #{cycle_count} 완료 (누적 trials: {total_trials}개)")

                    if result.get('best_params'):
                        self.logger.info(
                            f"[UnifiedOptimizer] 현재 최적: "
                            f"임계값={result['best_params']['threshold']}%, "
                            f"ML바이패스={result['best_params']['ml_bypass']}, "
                            f"ML가중치={result['best_params']['ml_weight']} "
                            f"(점수: {result['best_score']:.3f})"
                        )
                        # OptimizationDB에 최적 파라미터 저장
                        self._opt_db.set_state('last_best_params', result['best_params'])
                        self._opt_db.set_state('last_best_score', result.get('best_score', 0))
                        self._opt_db.set_state('total_cycles', cycle_count)

                    # 사이클 완료 시 예측 번호 5세트 생성
                    self._generate_predictions_after_cycle(cycle_count)

                elif result['status'] == 'completed':
                    self.logger.info(f"[UnifiedOptimizer] 최적화 정상 완료 (총 trials: {result.get('total_trials')})")
                    break
                elif result['status'] == 'error':
                    self.logger.error(f"[UnifiedOptimizer] 최적화 에러: {result.get('error')}")
                    break

                # ---- 2. 정기 피드백 루프 (30분마다) ----
                now = datetime.now()
                if (last_feedback_time is None or
                        (now - last_feedback_time).total_seconds() >= _FEEDBACK_INTERVAL_MINUTES * 60):
                    self._run_feedback_cycle()
                    last_feedback_time = datetime.now()

            except KeyboardInterrupt:
                self.logger.info("[UnifiedOptimizer] 최적화 중단 요청")
                break
            except Exception as e:
                self.logger.error(f"[UnifiedOptimizer] 사이클 오류: {e}")
                time.sleep(60)  # 오류 시 1분 대기 후 재시도

        if converged:
            self.logger.info("[CONVERGED] [UnifiedOptimizer] 수렴으로 종료 (최적 파라미터 적용됨)")
        self.logger.info("[UnifiedOptimizer] 워커 스레드 종료")
        self._running = False

    def _run_feedback_cycle(self):
        """
        피드백 루프 실행 (구 SmartAutoLearning.run_learning() 대체).
        EnhancedFeedbackLoop 없으면 기본 백테스팅으로 대체.
        """
        try:
            from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop
            enhanced_feedback = EnhancedFeedbackLoop(db_manager=self.db_manager)
            latest_round = self.db_manager.get_latest_round()
            if latest_round is None:
                self.logger.warning("[UnifiedOptimizer] 피드백: DB에서 회차 정보 조회 불가")
                return

            start_round = max(1, latest_round - 50)
            self.logger.info(f"[UnifiedOptimizer] 피드백 루프 시작: {start_round}~{latest_round}회차")
            improvement_result = enhanced_feedback.run_improvement_cycle(
                start_round=start_round,
                end_round=latest_round,
                max_iterations=1
            )

            if improvement_result and improvement_result.get('improved', False):
                self.logger.info(
                    f"[UnifiedOptimizer] 피드백 개선 완료: "
                    f"{improvement_result.get('improvement_rate', 0):.2%}"
                )
            else:
                self.logger.info("[UnifiedOptimizer] 피드백: 현재 최적 상태 유지")

        except ImportError:
            # EnhancedFeedbackLoop 없으면 기본 백테스팅으로 대체
            try:
                from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
                backtesting = OptimizedBacktestingFramework(self.db_manager)
                result = backtesting.run_backtest(test_rounds=50)
                self.logger.info(
                    f"[UnifiedOptimizer] 피드백 백테스팅 완료: "
                    f"평균 매치 {result.get('average_matches', 0):.2f}개"
                )
            except Exception as e2:
                self.logger.error(f"[UnifiedOptimizer] 피드백 대체 백테스팅 실패: {e2}")
            return

        except Exception as e:
            self.logger.error(f"[UnifiedOptimizer] 피드백 루프 실패: {e}")
            return

        # 마지막 피드백 시간 저장
        self._opt_db.set_state('last_feedback_time', datetime.now().isoformat())

    def _generate_predictions_after_cycle(self, cycle_count: int):
        """최적화 사이클 완료 후 예측 번호 5세트 생성 (선택적)"""
        try:
            from src.core.db_manager import DatabaseManager
            from src.core.filter_manager import FilterManager
            # generate_final_predictions는 main.py에서 정의되므로 동적 임포트
            import importlib
            import sys
            main_mod = sys.modules.get('__main__')
            if main_mod and hasattr(main_mod, 'generate_final_predictions'):
                _db = DatabaseManager()
                _fm = FilterManager(_db)
                _predictions = main_mod.generate_final_predictions(_db, _fm, num_sets=5)

                print("\n" + "=" * 60)
                print(f"[사이클 #{cycle_count} 완료] 추천 번호 5세트")
                print("=" * 60)
                for i, pred in enumerate(_predictions, 1):
                    nums = ', '.join(f"{n:2d}" for n in pred['numbers'])
                    print(f"  [{i}] {nums}  (신뢰도: {pred.get('confidence', 0):.1%})")
                print("=" * 60 + "\n")
        except Exception as pred_err:
            self.logger.debug(f"[UnifiedOptimizer] 예측 생성 실패 (비치명적): {pred_err}")
