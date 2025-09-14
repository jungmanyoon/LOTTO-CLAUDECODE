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
from src.utils.logging_setup import setup_logging

class AutoThresholdOptimizer:
    """자동 임계값 최적화 실행기"""

    def __init__(self):
        self.logger = setup_logging("auto_threshold_optimizer")
        self.optimizer = ThresholdOptimizer()
        self.stats_manager = PerformanceStatsManager()
        self.db_manager = DatabaseManager()

        # 최적화 설정
        self.optimization_config = {
            'n_trials': 30,  # Optuna 시도 횟수
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

    def run_backtesting_with_config(self, config: Dict) -> Dict[str, Any]:
        """특정 설정으로 백테스팅 실행"""
        try:
            self.logger.info(f"백테스팅 시작 - Threshold: {config.get('global_probability_threshold')}")

            # 백테스팅 프레임워크 초기화
            framework = OptimizedBacktestingFramework(
                db_manager=self.db_manager,
                config_path="configs/adaptive_filter_config.yaml"
            )

            # 임시 설정 적용
            framework.config = config

            # 백테스팅 실행 (최근 50회차)
            backtest_range = (1137, 1186)  # 최근 50회차
            results = framework.run_comprehensive_backtest(
                start_round=backtest_range[0],
                end_round=backtest_range[1],
                save_results=False  # 임시 실행이므로 저장하지 않음
            )

            # 성능 메트릭 계산
            performance_metrics = self._calculate_performance_metrics(results, config)

            return performance_metrics

        except Exception as e:
            self.logger.error(f"백테스팅 실행 실패: {e}")
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

            # 전체 평균 매칭 계산
            total_matches = 0
            total_predictions = 0
            ml_included_count = 0
            ml_total_count = 0

            for model_name, model_metrics in model_performances.items():
                avg_matches = model_metrics.get('avg_matches', 0)
                predictions = model_metrics.get('total_predictions', 0)

                total_matches += avg_matches * predictions
                total_predictions += predictions

                # ML 모델 포함률 계산
                if 'ml' in model_name.lower() or 'lstm' in model_name.lower() or 'ensemble' in model_name.lower():
                    ml_total_count += predictions
                    # Filter를 통과한 ML 예측 수 (추정)
                    ml_included_count += model_metrics.get('filter_passed_count', predictions * 0.085)

            avg_matches = total_matches / total_predictions if total_predictions > 0 else 0
            ml_inclusion_rate = ml_included_count / ml_total_count if ml_total_count > 0 else 0

            # 필터링된 조합 수 추출
            filter_stats = backtest_results.get('filter_statistics', {})
            combination_count = filter_stats.get('total_combinations_after_filter', 300000)

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

    def optimize_threshold(self):
        """임계값 최적화 실행"""
        self.logger.info("=" * 60)
        self.logger.info(f"자동 임계값 최적화 시작 - {datetime.now()}")
        self.logger.info("=" * 60)

        try:
            # 현재 최적 성능 조회
            current_best = self.optimizer.get_current_best_params()
            current_score = current_best['score'] if current_best else 0

            self.logger.info(f"현재 최적 점수: {current_score:.3f}")

            # Optuna 최적화 실행
            optimization_results = self.optimizer.optimize(
                backtesting_func=self.run_backtesting_with_config,
                n_trials=self.optimization_config['n_trials'],
                n_jobs=1,  # 단일 프로세스로 실행 (안정성)
                study_name=f"auto_opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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