#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[NEW] Weekly Cycle Manager - 주간 사이클 기반 무한 학습 관리자

[automation-1 / 미연결 - 의도적] 이 매니저는 UnifiedOptimizer(단일 백그라운드 최적화,
src/optimization/unified_optimizer.py)로 **대체**되었으며, main.py에 의도적으로 연결하지 않는다.
- on_new_round_detected() -> start_continuous_learning() 은 별도 데몬 스레드에서
  ThresholdOptimizer.optimize()를 무한 반복하는데, 이는 UnifiedOptimizer가 이미 수행하는
  백그라운드 최적화와 정확히 중복되어, 동시 실행 시 스레드/DB 경합과 임계값 이중 기록을 유발한다.
- 따라서 SystemStateManager.set_weekly_cycle_manager()는 호출되지 않으며(주입 안 함),
  weekly_cycle_mode/never_stop_learning 설정 플래그는 이 매니저 전용이 아니라
  ThresholdOptimizer의 "무한 최적화" 동작 제어에 쓰이므로 그대로 둔다(False로 내리면 옵티마이저가 멈춤).
- 재활성화하려면 UnifiedOptimizer와의 역할을 통합/택일한 뒤 연결할 것.

새 로또 회차 발표 시 자동으로 1주일 사이클을 시작하고,
사이클 내내 학습을 계속하여 마지막에 최고 성능으로 예측 생성

주요 기능:
- 새 회차 감지 시 사이클 자동 시작
- 1주일 동안 무한 학습 (배치 단위: 25회 trial)
- 사이클 종료 시 최고 성능 파라미터로 예측 생성
- 다음 사이클은 이전 사이클 최고 성능에서 시작
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import yaml


class WeeklyCycleManager:
    """주간 사이클 기반 무한 학습 관리자"""

    def __init__(
        self,
        threshold_optimizer,
        auto_improvement_manager,
        config_path: str = "config.yaml"
    ):
        """
        Args:
            threshold_optimizer: ThresholdOptimizer 인스턴스
            auto_improvement_manager: ImprovedAutoImprovementManager 인스턴스
            config_path: 설정 파일 경로
        """
        self.optimizer = threshold_optimizer
        self.improvement_mgr = auto_improvement_manager
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)

        # 설정 로드
        self._load_config()

        # 사이클 상태
        self.current_cycle = 0
        self.cycle_start_time = None
        self.cycle_start_round = 0
        self.cycle_end_time = None
        self.is_learning = False
        self.learning_thread = None
        self.stop_signal = threading.Event()

        # 사이클 성능 추적
        self.cycle_best_performance = 0.0
        self.cycle_total_trials = 0

        self.logger.info("WeeklyCycleManager 초기화 완료")

    def _load_config(self):
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            opt_config = config.get('optimization', {})
            self.never_stop_learning = opt_config.get('never_stop_learning', False)
            self.weekly_cycle_mode = opt_config.get('weekly_cycle_mode', False)
            self.cycle_duration_hours = opt_config.get('cycle_duration_hours', 168)  # 1주일
            self.trial_batch_size = opt_config.get('trial_batch_size', 25)
            self.batch_interval_seconds = opt_config.get('batch_interval_seconds', 300)  # 5분

            self.logger.info(f"Weekly Cycle 설정 로드:")
            self.logger.info(f"  - never_stop_learning: {self.never_stop_learning}")
            self.logger.info(f"  - weekly_cycle_mode: {self.weekly_cycle_mode}")
            self.logger.info(f"  - cycle_duration: {self.cycle_duration_hours}시간 ({self.cycle_duration_hours / 24:.1f}일)")
            self.logger.info(f"  - trial_batch_size: {self.trial_batch_size}회")
            self.logger.info(f"  - batch_interval: {self.batch_interval_seconds}초 ({self.batch_interval_seconds / 60:.1f}분)")

        except Exception as e:
            self.logger.error(f"설정 로드 실패: {e}")
            # 기본값 설정
            self.never_stop_learning = False
            self.weekly_cycle_mode = False
            self.cycle_duration_hours = 168
            self.trial_batch_size = 25
            self.batch_interval_seconds = 300

    def on_new_round_detected(self, round_num: int, backtesting_func: Callable) -> bool:
        """
        새 회차 감지 시 호출 - 사이클 시작

        Args:
            round_num: 새 회차 번호
            backtesting_func: 백테스팅 함수

        Returns:
            bool: 사이클 시작 성공 여부
        """
        try:
            # 무한 학습 모드가 비활성화되어 있으면 무시
            if not self.never_stop_learning or not self.weekly_cycle_mode:
                self.logger.info("무한 학습 모드 비활성화 - 사이클 시작 건너뜀")
                return False

            # 이전 사이클이 실행 중이면 종료
            if self.is_learning:
                self.logger.warning(f"[WARN] 이전 사이클(#{self.current_cycle}) 실행 중 - 강제 종료")
                self.stop_cycle()

            # 새 사이클 시작
            self.current_cycle = round_num
            self.cycle_start_time = datetime.now()
            self.cycle_start_round = round_num
            self.cycle_end_time = self.cycle_start_time + timedelta(hours=self.cycle_duration_hours)
            self.cycle_total_trials = 0

            # 이전 사이클 최고 성능 상속
            prev_best = self.improvement_mgr.state.get('cycle_best_performance', 0.0)
            self.cycle_best_performance = prev_best

            self.logger.info(f"")
            self.logger.info(f"╔{'═' * 78}╗")
            self.logger.info(f"║ [NEW] 새 사이클 시작: Round #{round_num}                                         ║")
            self.logger.info(f"╠{'═' * 78}╣")
            self.logger.info(f"║   • 시작 시간: {self.cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}                           ║")
            self.logger.info(f"║   • 종료 예정: {self.cycle_end_time.strftime('%Y-%m-%d %H:%M:%S')}                           ║")
            self.logger.info(f"║   • 사이클 기간: {self.cycle_duration_hours}시간 ({self.cycle_duration_hours / 24:.1f}일)                        ║")
            self.logger.info(f"║   • 이전 사이클 최고 성능: {prev_best:.4f}                                   ║")
            self.logger.info(f"║   • 배치 크기: {self.trial_batch_size}회                                              ║")
            self.logger.info(f"║   • 배치 간격: {self.batch_interval_seconds}초 ({self.batch_interval_seconds / 60:.1f}분)                               ║")
            self.logger.info(f"╚{'═' * 78}╝")
            self.logger.info(f"")

            # 상태 저장
            self.improvement_mgr.state['current_cycle'] = self.current_cycle
            self.improvement_mgr.state['cycle_start_time'] = self.cycle_start_time.isoformat()
            self.improvement_mgr.state['cycle_start_round'] = self.cycle_start_round
            self.improvement_mgr.state['cycle_total_trials'] = 0
            self.improvement_mgr.save_state()

            # 백그라운드 학습 스레드 시작
            self.start_continuous_learning(backtesting_func)

            return True

        except Exception as e:
            self.logger.error(f"사이클 시작 실패: {e}")
            return False

    def start_continuous_learning(self, backtesting_func: Callable):
        """
        무한 학습 루프 시작 (백그라운드 스레드)

        Args:
            backtesting_func: 백테스팅 함수
        """
        if self.is_learning:
            self.logger.warning("이미 학습 중입니다")
            return

        self.is_learning = True
        self.stop_signal.clear()

        # 백그라운드 스레드에서 학습 실행
        self.learning_thread = threading.Thread(
            target=self._infinite_learning_loop,
            args=(backtesting_func,),
            daemon=True,
            name=f"WeeklyCycle-{self.current_cycle}"
        )
        self.learning_thread.start()

        self.logger.info(f"[O] 무한 학습 스레드 시작: {self.learning_thread.name}")

    def _infinite_learning_loop(self, backtesting_func: Callable):
        """
        무한 학습 루프 (별도 스레드에서 실행)

        Args:
            backtesting_func: 백테스팅 함수
        """
        batch_count = 0

        self.logger.info(f"")
        self.logger.info(f"{'=' * 80}")
        self.logger.info(f"  [INF]  무한 학습 루프 시작 - 사이클 #{self.current_cycle}")
        self.logger.info(f"{'=' * 80}")
        self.logger.info(f"")

        while not self.stop_signal.is_set():
            try:
                batch_count += 1
                batch_start_time = datetime.now()

                self.logger.info(f"")
                self.logger.info(f"┌{'─' * 78}┐")
                self.logger.info(f"│ [PKG] 배치 #{batch_count} 시작                                                  │")
                self.logger.info(f"├{'─' * 78}┤")
                self.logger.info(f"│   • 시작 시간: {batch_start_time.strftime('%H:%M:%S')}                                            │")
                self.logger.info(f"│   • Trial 수: {self.trial_batch_size}회                                              │")
                self.logger.info(f"│   • 누적 Trials: {self.cycle_total_trials}회                                        │")
                self.logger.info(f"└{'─' * 78}┘")

                # ThresholdOptimizer로 배치 실행
                results = self.optimizer.optimize(
                    backtesting_func=backtesting_func,
                    n_trials=self.trial_batch_size,
                    n_jobs=1
                )

                batch_end_time = datetime.now()
                batch_duration = (batch_end_time - batch_start_time).total_seconds()

                # 결과 처리
                if results and results.get('best_score', 0) > 0:
                    self.cycle_total_trials += self.trial_batch_size

                    # 사이클 최고 성능 업데이트
                    if results['best_score'] > self.cycle_best_performance:
                        improvement = results['best_score'] - self.cycle_best_performance
                        self.cycle_best_performance = results['best_score']

                        self.logger.info(f"")
                        self.logger.info(f"[BEST] 사이클 최고 성능 갱신!")
                        self.logger.info(f"   {self.cycle_best_performance - improvement:.4f} → {self.cycle_best_performance:.4f} (↑{improvement:.4f})")
                        self.logger.info(f"   Threshold: {results['best_params']['threshold']:.2f}")
                        self.logger.info(f"   ML Bypass: {results['best_params']['ml_bypass']}")
                        self.logger.info(f"   ML Weight: {results['best_params']['ml_weight']:.2f}")

                        # 상태 저장
                        self.improvement_mgr.state['cycle_best_performance'] = self.cycle_best_performance
                        self.improvement_mgr.state['cycle_total_trials'] = self.cycle_total_trials
                        self.improvement_mgr.save_state()

                self.logger.info(f"")
                self.logger.info(f"[O] 배치 #{batch_count} 완료 ({batch_duration:.1f}초)")
                self.logger.info(f"   현재 사이클 최고 성능: {self.cycle_best_performance:.4f}")
                self.logger.info(f"   누적 Trials: {self.cycle_total_trials}회")

                # 사이클 종료 시간 확인
                remaining_time = (self.cycle_end_time - datetime.now()).total_seconds()
                if remaining_time <= 0:
                    self.logger.info(f"")
                    self.logger.info(f"[TIME] 사이클 종료 시간 도달 - 학습 중단")
                    break

                # 다음 배치까지 대기 (또는 종료 신호 대기)
                self.logger.info(f"[WAIT] 다음 배치까지 {self.batch_interval_seconds}초 대기...")
                if self.stop_signal.wait(timeout=self.batch_interval_seconds):
                    self.logger.info(f"[STOP] 종료 신호 수신 - 학습 중단")
                    break

            except Exception as e:
                self.logger.error(f"배치 #{batch_count} 실행 중 오류: {e}")
                # 오류 발생 시에도 계속 진행 (1분 대기 후)
                time.sleep(60)

        # 사이클 종료 처리
        self._finalize_cycle()

    def _finalize_cycle(self):
        """사이클 종료 처리"""
        self.is_learning = False

        cycle_duration = (datetime.now() - self.cycle_start_time).total_seconds() / 3600  # 시간 단위

        self.logger.info(f"")
        self.logger.info(f"╔{'═' * 78}╗")
        self.logger.info(f"║ [FINISH] 사이클 #{self.current_cycle} 종료                                            ║")
        self.logger.info(f"╠{'═' * 78}╣")
        self.logger.info(f"║   • 실행 시간: {cycle_duration:.1f}시간                                           ║")
        self.logger.info(f"║   • 총 Trials: {self.cycle_total_trials}회                                       ║")
        self.logger.info(f"║   • 최고 성능: {self.cycle_best_performance:.4f}                                    ║")
        self.logger.info(f"╚{'═' * 78}╝")
        self.logger.info(f"")

        # 사이클 히스토리 저장
        cycle_record = {
            'cycle': self.current_cycle,
            'start_time': self.cycle_start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'duration_hours': cycle_duration,
            'total_trials': self.cycle_total_trials,
            'best_performance': self.cycle_best_performance
        }

        # 구버전 state 파일 호환: 키 부재 시 KeyError 방지 (automation-5, _load_state 병합과 이중 방어)
        self.improvement_mgr.state.setdefault('weekly_cycle_history', []).append(cycle_record)
        self.improvement_mgr.save_state()

        self.logger.info(f"[O] 사이클 히스토리 저장 완료")

    def stop_cycle(self):
        """사이클 강제 종료"""
        if not self.is_learning:
            self.logger.warning("실행 중인 사이클이 없습니다")
            return

        self.logger.info(f"[STOP] 사이클 #{self.current_cycle} 강제 종료 요청")
        self.stop_signal.set()

        # 스레드 종료 대기 (최대 30초)
        if self.learning_thread and self.learning_thread.is_alive():
            self.learning_thread.join(timeout=30)
            if self.learning_thread.is_alive():
                self.logger.warning("[WARN] 학습 스레드가 30초 내에 종료되지 않음")
            else:
                self.logger.info("[O] 학습 스레드 정상 종료")

    def get_cycle_status(self) -> Dict[str, Any]:
        """현재 사이클 상태 반환"""
        if not self.is_learning:
            return {
                'is_active': False,
                'current_cycle': self.current_cycle,
                'message': '실행 중인 사이클 없음'
            }

        remaining_time = (self.cycle_end_time - datetime.now()).total_seconds() / 3600  # 시간
        progress = ((datetime.now() - self.cycle_start_time).total_seconds() /
                   (self.cycle_duration_hours * 3600)) * 100

        return {
            'is_active': True,
            'current_cycle': self.current_cycle,
            'start_time': self.cycle_start_time.isoformat(),
            'end_time': self.cycle_end_time.isoformat(),
            'remaining_hours': remaining_time,
            'progress_percent': progress,
            'total_trials': self.cycle_total_trials,
            'best_performance': self.cycle_best_performance
        }

    def stop_and_generate_predictions(self, prediction_generator_func: Optional[Callable] = None) -> Dict[str, Any]:
        """
        사이클 종료 및 최고 성능 파라미터로 예측 생성

        Args:
            prediction_generator_func: 예측 생성 함수 (선택)

        Returns:
            Dict: 예측 결과
        """
        # 사이클 종료
        self.stop_cycle()

        # 최고 파라미터 적용
        self.logger.info(f"")
        self.logger.info(f"[TARGET] 사이클 최고 성능 파라미터로 예측 생성 시작")
        self.logger.info(f"   사이클 최고 성능: {self.cycle_best_performance:.4f}")

        # ThresholdOptimizer의 최적 파라미터 적용
        apply_success = self.optimizer.apply_best_params(validate=False)

        if not apply_success:
            self.logger.error("[X] 최적 파라미터 적용 실패")
            return {'success': False, 'error': 'apply_params_failed'}

        # 예측 생성 (함수가 제공된 경우)
        predictions = None
        if prediction_generator_func:
            try:
                predictions = prediction_generator_func()
                self.logger.info(f"[O] 예측 생성 완료: {len(predictions) if predictions else 0}개")
            except Exception as e:
                self.logger.error(f"예측 생성 실패: {e}")

        return {
            'success': True,
            'cycle': self.current_cycle,
            'best_performance': self.cycle_best_performance,
            'total_trials': self.cycle_total_trials,
            'predictions': predictions
        }
