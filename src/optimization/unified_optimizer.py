#!/usr/bin/env python3
"""
통합 최적화기 (UnifiedOptimizer)
Phase 3: SmartAutoLearning(레이어 1) + BackgroundOptimization(레이어 2) 통합

- 단일 백그라운드 스레드로 Optuna CMA-ES 최적화 + 정기 피드백 루프 수행
- 상태는 OptimizationDB(data/optimization.db)에 저장 (JSON 파일 불필요)
- 종료 플래그(stop_flag)를 AutoThresholdOptimizer → OptimizedBacktestingFramework 체인으로 전파
"""
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from src.core.optimization_db import get_optimization_db

# 피드백 루프 실행 간격 (분) - 구 SmartAutoLearning.min_interval_minutes
_FEEDBACK_INTERVAL_MINUTES = 30

# [log-analysis-5] 한 사이클당 누적 trial 수 (기존 동작과 동일: 0->10->20...).
# 단, optimize()를 이 값만큼 한 번에 호출하지 않고 _TRIALS_PER_SUBBATCH 단위로
# 쪼개어 호출하여, 종료(stop_flag) 확인 빈도를 높인다(30초 join 내 안전 종료 보강).
_TRIALS_PER_CYCLE = 10
# optimize() 1회 호출에 넣는 trial 수. 작을수록 종료 확인이 잦아지지만(안전),
# Optuna study persistence 덕분에 누적 학습 결과는 한 번에 10개 돌린 것과 동일하다.
# (worst-case 미확인 블로킹 = trial 1개의 evaluate() 시간으로 제한)
_TRIALS_PER_SUBBATCH = 2

# [신 아키텍처 2026-05-31] 최적화 엔진 선택:
#   'pool'(기본): PoolOptimizer v6 (극단성 점수 가중치 탐색, 목표 풀 K, 통과율 제약 없음)
#   'threshold' : 구 AutoThresholdOptimizer v5 (global_probability_threshold 탐색) - 폴백용
# 환경변수 LOTTO_OPTIMIZER_MODE 로 전환.
_OPTIMIZER_MODE = os.environ.get('LOTTO_OPTIMIZER_MODE', 'pool')
_POOL_TARGET_K = int(os.environ.get('LOTTO_TARGET_POOL_K', '1500000'))


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
        self._stop_join_done = False  # stop() 멱등성: join 1회만 수행 (이중 종료 호출 대비)

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
        self.logger.info("   - 백테스팅 모니터링 주기: 30분마다 (PoolOptimizer 워커, 비실행 레거시 피드백루프와 무관)")
        self.logger.info("   - 상태 저장: data/optimization.db")
        return self._thread

    def run_optimization_cycle(self, n_trials: int = 10) -> Dict:
        """단일 최적화 사이클 실행 (동기, 테스트 및 수동 호출용)

        [optimization-3] _OPTIMIZER_MODE 분기 추가:
          백그라운드 워커(_worker)와 동일하게 모드를 확인해 일관된 경로를 사용한다.
          - 'pool'(기본): PoolOptimizer v6 (극단성 가중치 탐색, 통과율 제약 없음)
          - 'threshold' : 구 AutoThresholdOptimizer v5 (threshold 탐색) - 폴백용
        (이 메서드는 production 호출처가 없는 수동/테스트용이지만 모드 정합성을 맞춘다.)
        """
        if _OPTIMIZER_MODE == 'pool':
            # _worker_pool과 동일한 pool 평가 경로 재사용
            from src.core.pool_optimizer import PoolOptimizer
            optimizer = PoolOptimizer(self.db_manager, target_K=_POOL_TARGET_K)
            optimizer.set_shutdown_flag(self._stop_flag)
            result = optimizer.optimize(n_trials=n_trials, study_name="pool_optimization_v6")
            # 종료/취소가 아니면 최적 가중치를 저장 (예측 풀 캐시 무효화 트리거)
            if not result.get('cancelled') and not self._stop_flag.get('stop', False):
                optimizer.save_best(result)
            return result

        # ---- 구 v5 경로 (mode='threshold') ----
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
            # pool 워커는 'total_cycles_pool', threshold 워커는 'total_cycles'에 저장하므로
            # 현재 모드에 맞는 키를 읽는다 (optimization-2). 반환 키 이름은 호환 위해 유지.
            'total_cycles': self._opt_db.get_state(
                'total_cycles_pool' if _OPTIMIZER_MODE == 'pool' else 'total_cycles', 0),
            'last_feedback_time': self._opt_db.get_state('last_feedback_time'),
        }

    def stop(self):
        """백그라운드 최적화 중지 (멱등 - 이중 호출 안전)

        main.py의 Phase3 종료와 signal/atexit graceful_shutdown이 모두 stop()을 호출하므로,
        join을 한 번만 수행하여 30초 대기가 중복(최대 60초)되는 것을 방지한다.
        """
        self._stop_flag['stop'] = True
        self._running = False
        if self._stop_join_done:
            self.logger.debug("[UnifiedOptimizer] stop() 재호출 - 이미 종료 처리됨(추가 join 생략)")
            return
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                self.logger.warning("[UnifiedOptimizer] 스레드가 30초 내에 종료되지 않음 (daemon으로 강제 종료)")
            else:
                self.logger.info("[UnifiedOptimizer] 스레드 정상 종료 완료")
        self._stop_join_done = True
        self.logger.info("[UnifiedOptimizer] 최적화 중지")

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _worker(self):
        """
        백그라운드 워커.
        mode='pool'(기본): PoolOptimizer v6 사이클 (극단성 가중치 탐색)
        mode='threshold' : 구 AutoThresholdOptimizer v5 (Optuna CMA-ES, threshold 탐색)
        공통: 30분마다 피드백 루프
        """
        if _OPTIMIZER_MODE == 'pool':
            self._worker_pool()
            return

        # ---- 구 v5 경로 (mode='threshold') ----
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
                    best_params = result.get('best_params') or {}
                    self.logger.info(f"[CONVERGED] [UnifiedOptimizer] 최적화 수렴: {convergence_reason}")
                    self.logger.info(f"   최적 파라미터: threshold={best_params.get('threshold', 'N/A')}, "
                                     f"ml_bypass={best_params.get('ml_bypass', 'N/A')}, "
                                     f"ml_weight={best_params.get('ml_weight', 'N/A')}")
                    self.logger.info(f"   최적 점수: {result.get('best_score', 0):.4f}")
                    self.logger.info(f"   총 누적 trials: {result.get('total_trials', 'N/A')}개")
                    break

                if result.get('status') == 'cycle_completed':
                    cycle_count += 1
                    total_trials = result.get('total_trials', cycle_count * 10)
                    self.logger.info(f"[UnifiedOptimizer] 사이클 #{cycle_count} 완료 (누적 trials: {total_trials}개)")

                    best_params = result.get('best_params') or {}
                    if best_params:
                        self.logger.info(
                            f"[UnifiedOptimizer] 현재 최적: "
                            f"임계값={best_params.get('threshold', 'N/A')}%, "
                            f"ML바이패스={best_params.get('ml_bypass', 'N/A')}, "
                            f"ML가중치={best_params.get('ml_weight', 'N/A')} "
                            f"(점수: {result.get('best_score', 0):.3f})"
                        )
                        # OptimizationDB에 최적 파라미터 저장
                        self._opt_db.set_state('last_best_params', best_params)
                        self._opt_db.set_state('last_best_score', result.get('best_score', 0))
                        self._opt_db.set_state('total_cycles', cycle_count)

                    # 사이클 완료 시 예측 번호 5세트 생성
                    self._generate_predictions_after_cycle(cycle_count)

                elif result.get('status') == 'completed':
                    self.logger.info(f"[UnifiedOptimizer] 최적화 정상 완료 (총 trials: {result.get('total_trials')})")
                    break
                elif result.get('status') == 'error':
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

    def _worker_pool(self):
        """
        [신 v6] PoolOptimizer 백그라운드 워커.
        - 극단성 점수 가중치(feature scale + 페널티)를 Optuna로 탐색
        - 목적: 분리도 AUC + 약한 hold-out lift LCB (통과율 제약 없음)
        - 사이클마다 configs/extremeness_weights.json 갱신 → 예측 풀 캐시 자동 무효화
        - 30분마다 피드백 루프(백테스팅 모니터링)
        """
        try:
            from src.core.pool_optimizer import PoolOptimizer
            optimizer = PoolOptimizer(self.db_manager, target_K=_POOL_TARGET_K)
            # 종료 플래그 전파: optimize() 내부 Optuna 루프가 trial 경계마다 stop을 확인하도록 함
            # (threshold 경로의 set_shutdown_flag와 동일 패턴 - 30초 미종료/강제종료 방지)
            optimizer.set_shutdown_flag(self._stop_flag)
        except Exception as e:
            self.logger.error(f"[UnifiedOptimizer] PoolOptimizer 초기화 실패 - 최적화 비활성(예측은 정상): {e}")
            self._running = False
            return

        self.logger.info("[UnifiedOptimizer] 워커 스레드 시작 (mode=pool / PoolOptimizer v6)")
        self.logger.info(f"   - 목표 풀 크기 K={_POOL_TARGET_K:,} (극단 최대 제거)")
        self.logger.info("   - 목적: 분리도 AUC + 약한 lift LCB (통과율 제약 없음)")
        self.logger.info("   - 누적 학습: 0->10->20... / 상태 data/pool_optimization.db")

        cycle_count = self._opt_db.get_state('total_cycles_pool', 0)
        last_feedback_time: Optional[datetime] = None
        last_fb_str = self._opt_db.get_state('last_feedback_time')
        if last_fb_str:
            try:
                last_feedback_time = datetime.fromisoformat(last_fb_str)
            except (ValueError, TypeError):
                last_feedback_time = None

        while not self._stop_flag.get('stop', False):
            try:
                if self._stop_flag.get('stop', False):
                    break
                # ---- 1. PoolOptimizer 최적화 사이클 (10 trials 누적) ----
                # [log-analysis-5] optimize(n_trials=10)을 한 번에 호출하면, 종료 신호가
                # 사이클 도중에 들어와도 10개 trial이 모두 끝날 때까지(또는 다음 trial 가지치기까지)
                # 워커 루프로 제어가 돌아오지 않아 30초 join을 초과해 daemon 강제종료 경고가 났다.
                # -> trial을 _TRIALS_PER_SUBBATCH(=2) 단위로 쪼개 호출하고, 각 호출 사이에서
                #    stop_flag를 확인한다. Optuna study는 영속(SQLite, load_if_exists)이라
                #    누적 결과는 한 번에 10개 돌린 것과 동일하며, 마지막 호출의 result가
                #    study 전체의 best를 담는다(이후 저장/예측 로직 변경 없음).
                #    worst-case 미확인 블로킹 = sub-batch 1회의 evaluate() 시간으로 축소.
                result = None
                _remaining = _TRIALS_PER_CYCLE
                while _remaining > 0:
                    if self._stop_flag.get('stop', False):
                        break
                    _n = min(_TRIALS_PER_SUBBATCH, _remaining)
                    result = optimizer.optimize(n_trials=_n, study_name="pool_optimization_v6")
                    _remaining -= _n
                    # sub-batch가 종료/취소로 중단된 경우 즉시 사이클 중단
                    if result is None or result.get('cancelled'):
                        break

                # [종료 가드] optimize()가 길게 블로킹되는 동안 stop이 켜졌거나 사이클이
                # 취소(완료 trial 0개)된 경우, 저장/예측/피드백 등 모든 후처리를 생략하고 종료한다.
                # 종료 중 0.000 백테스팅이 DB에 기록되는 문제의 핵심 차단점이다.
                if self._stop_flag.get('stop', False) or result is None or result.get('cancelled'):
                    self.logger.info("[UnifiedOptimizer] 종료/취소 감지 - pool 사이클 후처리 생략")
                    break

                cycle_count += 1
                best_val = result.get('best_value', 0)
                auc = result.get('auc_separation', 0)
                lift = result.get('lift_lcb', 0)
                self.logger.info(
                    f"[UnifiedOptimizer] pool 사이클 #{cycle_count} 완료 "
                    f"(누적 trials: {result.get('n_trials', 'N/A')}, "
                    f"score={best_val:.4f}, AUC={auc:.4f}, lift_lcb={lift:.3f})"
                )

                # 최적 가중치 저장 (예측 풀 캐시 자동 무효화 트리거)
                optimizer.save_best(result)
                self._opt_db.set_state('last_best_params', result.get('best_params'))
                self._opt_db.set_state('last_best_score', best_val)
                self._opt_db.set_state('total_cycles_pool', cycle_count)

                # 예측 생성 직전 종료 재확인
                if self._stop_flag.get('stop', False):
                    break
                # 사이클 완료 시 예측 5세트 생성
                self._generate_predictions_after_cycle(cycle_count)

                # ---- 2. 정기 피드백 루프 (30분마다) ----
                now = datetime.now()
                if (last_feedback_time is None or
                        (now - last_feedback_time).total_seconds() >= _FEEDBACK_INTERVAL_MINUTES * 60):
                    # 피드백(백테스팅) 진입 직전 종료 재확인 - 종료 중 백테스팅 실행/기록 차단
                    if self._stop_flag.get('stop', False):
                        break
                    self._run_feedback_cycle()
                    last_feedback_time = datetime.now()

            except KeyboardInterrupt:
                self.logger.info("[UnifiedOptimizer] 최적화 중단 요청")
                break
            except Exception as e:
                self.logger.error(f"[UnifiedOptimizer] pool 사이클 오류: {e}")
                time.sleep(60)

        self.logger.info("[UnifiedOptimizer] 워커 스레드 종료 (pool)")
        self._running = False

    def _run_feedback_cycle(self):
        """
        피드백 루프 실행 (구 SmartAutoLearning.run_learning() 대체).
        EnhancedFeedbackLoop 없으면 기본 백테스팅으로 대체.
        """
        # [종료 가드 2차 방어] 종료 중이면 피드백(백테스팅) 자체를 시작하지 않는다.
        # 호출자(_worker_pool)의 가드와 별개로 함수 입구에서도 막아 어떤 경로로 들어와도 안전.
        if self._stop_flag.get('stop', False):
            self.logger.info("[UnifiedOptimizer] 종료 중 - 피드백 루프 생략")
            return
        try:
            from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop
            enhanced_feedback = EnhancedFeedbackLoop(db_manager=self.db_manager)
            # 백테스팅 싱글톤에 종료 플래그 전파 (run_backtest 내부 조기중단 + 0.000 저장 차단)
            try:
                from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
                _bt = OptimizedBacktestingFramework.get_instance()
                if _bt:
                    _bt.set_shutdown_flag(self._stop_flag)
            except Exception:
                pass
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

            # run_improvement_cycle 반환에는 'improved'/'improvement_rate' 키가 없고
            # 'total_improvements'(개선 적용 건수)가 존재 → 이 값으로 개선 여부 판정
            _improvements = improvement_result.get('total_improvements', 0) if improvement_result else 0
            if _improvements > 0:
                self.logger.info(f"[UnifiedOptimizer] 피드백 개선 완료: {_improvements}건 적용")
            else:
                self.logger.info("[UnifiedOptimizer] 피드백: 현재 최적 상태 유지")

        except ImportError:
            # EnhancedFeedbackLoop 없으면 기본 백테스팅으로 대체
            try:
                from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
                backtesting = OptimizedBacktestingFramework(self.db_manager)
                # run_backtest 필수 인자: start_round, end_round
                latest = self.db_manager.get_latest_round() if self.db_manager else 0
                _end = latest if latest > 0 else 50
                _start = max(1, _end - 49)
                result = backtesting.run_backtest(start_round=_start, end_round=_end)
                perf = result.get('performance_metrics', {})
                self.logger.info(
                    f"[UnifiedOptimizer] 피드백 백테스팅 완료: "
                    f"평균 매치 {perf.get('overall_avg_matches', 0):.2f}개"
                )
            except Exception as e2:
                self.logger.error(f"[UnifiedOptimizer] 피드백 대체 백테스팅 실패: {e2}")

        except Exception as e:
            self.logger.error(f"[UnifiedOptimizer] 피드백 루프 실패: {e}")

        finally:
            # FIX: 모든 경로(정상/ImportError/Exception)에서 피드백 시간 저장
            # 이전: except 블록의 return으로 저장이 누락되어 재시작 시 즉시 피드백 실행됨
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
