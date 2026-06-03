"""
백그라운드 최적화 서비스
메인 프로그램과 독립적으로 실행되는 지속적 최적화 시스템
"""

import os
import sys
import time
import signal
import logging
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.threshold_optimizer import ThresholdOptimizer
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework


class BackgroundOptimizer:
    """백그라운드 최적화 서비스"""

    def __init__(
        self,
        interval_hours: float = 1.0,
        trials_per_run: int = 25,
        log_file: str = "logs/background_optimizer.log"
    ):
        """
        Args:
            interval_hours: 최적화 실행 간격 (시간)
            trials_per_run: 실행당 시도 횟수
            log_file: 로그 파일 경로
        """
        self.interval_hours = interval_hours
        self.trials_per_run = trials_per_run
        self.log_file = log_file
        self.running = False
        self.status_file = "data/optimizer_status.json"

        # 로그 디렉토리 생성
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.status_file), exist_ok=True)

        # 로깅 설정
        self._setup_logging()

        # 최적화기 초기화
        self.optimizer = ThresholdOptimizer()
        self.backtester = OptimizedBacktestingFramework()

        # 시그널 핸들러 등록
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.logger.info("백그라운드 최적화 서비스 초기화 완료")
        self.logger.info(f"  - 실행 간격: {interval_hours}시간")
        self.logger.info(f"  - 실행당 시도: {trials_per_run}회")
        self.logger.info(f"  - 로그 파일: {log_file}")

    def _setup_logging(self):
        """로깅 설정"""
        self.logger = logging.getLogger('BackgroundOptimizer')
        self.logger.setLevel(logging.INFO)

        # 파일 핸들러
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 포맷 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (안전한 종료)"""
        signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        self.logger.info(f"{signal_name} 수신, 안전하게 종료 중...")
        self.running = False

    def _update_status(self, status: Dict):
        """상태 파일 업데이트 (원자적 쓰기 - 병렬 처리 중 파일 손상 방지)"""
        # [N-W19] 수정: open('w') 직접 쓰기 → 임시 파일 후 os.replace()로 원자적 교체
        try:
            tmp_path = self.status_file + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.status_file)
        except Exception as e:
            self.logger.error(f"상태 파일 업데이트 실패: {e}")

    def _get_status(self) -> Dict:
        """현재 상태 조회"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"상태 파일 읽기 실패: {e}")

        return {
            'running': False,
            'last_run': None,
            'next_run': None,
            'total_runs': 0,
            'current_trial': 0,
            'total_trials': 0,
            'best_params': None,
            'best_score': None
        }

    def _check_database_lock(self) -> bool:
        """데이터베이스 잠금 확인"""
        try:
            # 짧은 타임아웃으로 연결 시도
            db_path = "data/threshold_optimization.db"
            if not os.path.exists(db_path):
                return False

            conn = sqlite3.connect(db_path, timeout=1.0)
            conn.execute("SELECT 1")
            conn.close()
            return False  # 잠금 없음
        except sqlite3.OperationalError:
            return True  # 잠금 있음
        except Exception as e:
            self.logger.warning(f"DB 잠금 확인 중 오류: {e}")
            return False

    def _wait_for_database_unlock(self, max_wait_seconds: int = 300):
        """데이터베이스 잠금 해제 대기"""
        start_time = time.time()
        while self._check_database_lock():
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                self.logger.warning(f"DB 잠금 대기 시간 초과 ({max_wait_seconds}초)")
                return False

            if elapsed > 0 and int(elapsed) % 30 == 0:
                self.logger.info(f"DB 잠금 대기 중... ({int(elapsed)}초)")

            time.sleep(5)

        return True

    def _run_optimization(self) -> Optional[Dict]:
        """단일 최적화 실행"""
        try:
            # 데이터베이스 잠금 대기
            if not self._wait_for_database_unlock():
                self.logger.error("DB 잠금으로 인해 최적화 실행 불가")
                return None

            self.logger.info(f"최적화 시작 ({self.trials_per_run} trials)")

            # 백테스팅 함수 정의
            def backtesting_func(config, start_round=None, end_round=None):
                """백테스팅 실행 함수 (ThresholdOptimizer 호환: start_round/end_round 지원)"""
                # start_round/end_round가 없으면 DB에서 자동 계산
                if start_round is None or end_round is None:
                    latest = self.backtester.db_manager.get_latest_round()
                    if end_round is None:
                        end_round = latest
                    if start_round is None:
                        start_round = max(1, latest - 29)

                # config에서 파라미터 추출하여 백테스터에 적용
                adaptive_opts = config.get('adaptive_options', config)
                threshold = adaptive_opts.get('global_probability_threshold')
                ml_bypass = adaptive_opts.get('ml_bypass_threshold')
                ml_weight = adaptive_opts.get('ml_weight')

                if any(v is not None for v in [threshold, ml_bypass, ml_weight]):
                    self.backtester.update_parameters(
                        threshold=threshold,
                        ml_bypass=ml_bypass,
                        ml_weight=ml_weight
                    )

                # 백테스팅 실행
                result = self.backtester.run_backtest(
                    start_round=start_round,
                    end_round=end_round
                )

                # 반환값 표준화 (ThresholdOptimizer가 avg_matches 키 접근)
                perf = result.get('performance_metrics', {})
                return {
                    'avg_matches': perf.get('overall_avg_matches', 0),
                    'ml_inclusion_rate': result.get('ml_inclusion_rate', 0),
                    'combination_count': result.get('combination_count', 0),
                }

            # 최적화 실행
            results = self.optimizer.optimize(
                backtesting_func=backtesting_func,
                n_trials=self.trials_per_run,
                n_jobs=1  # 백그라운드에서는 단일 프로세스로 실행
            )

            self.logger.info(f"최적화 완료!")
            self.logger.info(f"  - 최적 파라미터: {results['best_params']}")
            self.logger.info(f"  - 최적 점수: {results['best_score']:.3f}")
            self.logger.info(f"  - 평균 매칭: {results.get('avg_matches', 'N/A')}")
            self.logger.info(f"  - ML 포함률: {results.get('ml_inclusion_rate', 'N/A')}")

            return results

        except Exception as e:
            self.logger.error(f"최적화 실행 실패: {e}", exc_info=True)
            return None

    def run(self):
        """백그라운드 서비스 실행"""
        self.running = True
        self.logger.info("백그라운드 최적화 서비스 시작")

        status = self._get_status()
        status['running'] = True
        status['start_time'] = datetime.now().isoformat()
        self._update_status(status)

        try:
            while self.running:
                # 상태 업데이트
                status = self._get_status()
                status['next_run'] = (
                    datetime.now() + timedelta(hours=self.interval_hours)
                ).isoformat()
                self._update_status(status)

                # 최적화 실행
                self.logger.info(f"=== 최적화 실행 #{status['total_runs'] + 1} ===")
                results = self._run_optimization()

                if results:
                    # 상태 업데이트
                    status['total_runs'] += 1
                    status['last_run'] = datetime.now().isoformat()
                    status['total_trials'] = results.get('total_trials', 0)
                    status['best_params'] = results.get('best_params')
                    status['best_score'] = results.get('best_score')
                    status['avg_matches'] = results.get('avg_matches')
                    status['ml_inclusion_rate'] = results.get('ml_inclusion_rate')
                    self._update_status(status)

                # 대기
                if self.running:
                    wait_seconds = self.interval_hours * 3600
                    self.logger.info(f"다음 실행까지 {self.interval_hours}시간 대기...")

                    # 인터럽트 가능한 대기
                    for _ in range(int(wait_seconds)):
                        if not self.running:
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("사용자에 의해 중단됨")

        except Exception as e:
            self.logger.error(f"백그라운드 서비스 오류: {e}", exc_info=True)

        finally:
            # 종료 상태 업데이트
            status = self._get_status()
            status['running'] = False
            status['stop_time'] = datetime.now().isoformat()
            self._update_status(status)

            self.logger.info("백그라운드 최적화 서비스 종료")

    def stop(self):
        """서비스 중지"""
        self.logger.info("서비스 중지 요청")
        self.running = False


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='백그라운드 최적화 서비스')
    parser.add_argument(
        '--interval',
        type=float,
        default=1.0,
        help='최적화 실행 간격 (시간, 기본값: 1.0)'
    )
    parser.add_argument(
        '--trials',
        type=int,
        default=25,
        help='실행당 시도 횟수 (기본값: 25)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='logs/background_optimizer.log',
        help='로그 파일 경로'
    )

    args = parser.parse_args()

    # 서비스 시작
    optimizer = BackgroundOptimizer(
        interval_hours=args.interval,
        trials_per_run=args.trials,
        log_file=args.log_file
    )

    optimizer.run()


if __name__ == '__main__':
    main()
