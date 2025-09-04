#!/usr/bin/env python3
"""
개선된 main.py - 최적화된 실행 순서
필터 최적화 → ML 학습 → 백테스팅 → 자동 개선 → 예측
"""
import logging
import argparse
import os
import time

# matplotlib 백엔드를 non-interactive로 설정 (tkinter 에러 방지)
import matplotlib
matplotlib.use('Agg')

# TensorFlow oneDNN 경고 억제
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# TensorFlow 로깅 레벨 설정
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # WARNING 이상만 표시

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.meta_data_manager import MetaDataManager
from src.data_collector import DataCollector
from src.core.combination_manager import CombinationManager
from src.core.filter_manager import FilterManager
from src.validators.filter_validator import FilterValidator
from src.optimization.adaptive_filter_optimizer import AdaptiveFilterOptimizer
from src.backtesting.backtesting_framework import BacktestingFramework
from src.ml.auto_ml_optimizer import AutoMLOptimizer
from src.optimization.feedback_loop_system import FeedbackLoopSystem
from src.ml.realtime_learning_system import RealtimeLearningSystem
from src.monitoring.performance_dashboard import PerformanceDashboard
from src.utils.config_manager import ConfigManager

# ML/AI 모듈 임포트
try:
    from src.ml.lstm_predictor import LSTMPredictor
    from src.ml.ensemble_predictor import EnsemblePredictor
    ML_AVAILABLE = True
except ImportError as e:
    ML_AVAILABLE = False
    logging.warning(f"ML 모듈 로드 실패: {e}")

try:
    from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
    from src.probabilistic.bayesian_inference import BayesianFilter
    PROBABILISTIC_AVAILABLE = True
except ImportError as e:
    PROBABILISTIC_AVAILABLE = False
    logging.warning(f"확률론적 모듈 로드 실패: {e}")

def parse_arguments():
    """명령줄 인수 파싱"""
    parser = argparse.ArgumentParser(description='로또 번호 예측 시스템 (개선된 버전)')
    
    # 기본 옵션
    parser.add_argument('--debug', action='store_true', help='디버그 모드 활성화')
    parser.add_argument('--verbose', '-v', action='store_true', help='상세 출력')
    
    # ML/AI 옵션
    parser.add_argument('--skip-ml', action='store_true', help='ML/AI 분석 건너뛰기')
    parser.add_argument('--skip-backtest', action='store_true', help='백테스팅 건너뛰기')
    parser.add_argument('--skip-optimization', action='store_true', help='자동 최적화 건너뛰기')
    parser.add_argument('--predictions', type=int, default=10, help='예측 조합 수 (기본: 10)')
    
    # 새로운 옵션
    parser.add_argument('--feedback-loop', action='store_true', help='피드백 루프 시스템 활성화')
    parser.add_argument('--realtime-learning', action='store_true', help='실시간 학습 활성화')
    parser.add_argument('--monitoring', action='store_true', help='성능 모니터링 대시보드 생성')
    parser.add_argument('--auto-improve', action='store_true', help='자동 개선 모드 (모든 최적화 활성화)')
    
    return parser.parse_args()

def main():
    """개선된 메인 실행 함수"""
    # 명령줄 인수 파싱
    args = parse_arguments()
    
    # 자동 개선 모드
    if args.auto_improve:
        args.feedback_loop = True
        args.realtime_learning = True
        args.monitoring = True
        args.skip_optimization = False
    
    # 로깅 설정
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    try:
        start_time = time.time()
        
        logging.info("="*60)
        logging.info("🎯 로또 번호 예측 시스템 v2.0 (개선된 버전)")
        logging.info("="*60)
        logging.info(f"프로그램 시작 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 메타데이터 매니저 초기화
        meta_manager = MetaDataManager()
        
        # 최신 회차 정보 수집
        logging.info("\n[데이터 수집] 최신 로또 정보 확인 중...")
        data_collector = DataCollector()
        latest_round, latest_date = data_collector.get_latest_round()
        logging.info(f"최신 회차: {latest_round} ({latest_date})")
        
        # 새로운 데이터 수집
        new_rounds = data_collector.collect_new_data(db_manager, latest_round)
        if new_rounds:
            logging.info(f"새로운 회차 {len(new_rounds)}개 수집 완료")
        
        # 성능 모니터링 대시보드 초기화
        dashboard = None
        if args.monitoring:
            logging.info("\n[모니터링] 성능 모니터링 시스템 초기화...")
            dashboard = PerformanceDashboard(db_manager)
        
        # ========== 1단계: 필터 최적화 ==========
        logging.info("\n" + "="*60)
        logging.info("[1단계] 필터 검증 및 최적화")
        logging.info("="*60)
        
        # 필터 검증
        filter_validator = FilterValidator(db_manager)
        validation_results = filter_validator.validate_filters_with_historical_data(
            start_round=max(1, latest_round - 100),
            end_round=latest_round
        )
        
        # 적응형 필터 최적화
        if not args.skip_optimization:
            adaptive_optimizer = AdaptiveFilterOptimizer(db_manager)
            optimization_results = adaptive_optimizer.optimize_filters_adaptive(latest_round)
            
            if optimization_results['optimized']:
                logging.info(f"✅ {len(optimization_results['optimized_filters'])}개 필터 최적화 완료")
        
        # 필터 매니저 초기화
        filter_manager = FilterManager(db_manager)
        
        # ========== 2단계: ML/AI 학습 ==========
        models = {}
        if not args.skip_ml and ML_AVAILABLE:
            logging.info("\n" + "="*60)
            logging.info("[2단계] ML/AI 모델 학습")
            logging.info("="*60)
            
            winning_numbers = db_manager.get_all_winning_numbers()
            
            if winning_numbers and len(winning_numbers) >= 50:
                # LSTM 모델
                try:
                    logging.info("\n[LSTM] 시계열 예측 모델 준비...")
                    lstm_predictor = LSTMPredictor(sequence_length=50)
                    if not lstm_predictor.is_trained:
                        logging.info("  - LSTM 모델 학습 중...")
                        lstm_predictor.train(winning_numbers, epochs=30, batch_size=32)
                    models['lstm'] = lstm_predictor
                except Exception as e:
                    logging.error(f"LSTM 모델 오류: {str(e)}")
                
                # 앙상블 모델
                try:
                    logging.info("\n[Ensemble] 앙상블 모델 준비...")
                    ensemble_predictor = EnsemblePredictor()
                    if not ensemble_predictor.is_trained:
                        logging.info("  - 앙상블 모델 학습 중...")
                        ensemble_predictor.train(winning_numbers, test_size=0.2)
                    models['ensemble'] = ensemble_predictor
                except Exception as e:
                    logging.error(f"앙상블 모델 오류: {str(e)}")
                
                # Monte Carlo
                if PROBABILISTIC_AVAILABLE:
                    try:
                        logging.info("\n[Monte Carlo] 시뮬레이터 준비...")
                        mc_simulator = MonteCarloSimulator(db_manager)
                        models['monte_carlo'] = mc_simulator
                    except Exception as e:
                        logging.error(f"Monte Carlo 오류: {str(e)}")
        
        # ========== 3단계: 백테스팅 ==========
        backtest_results = None
        if not args.skip_backtest and models:
            logging.info("\n" + "="*60)
            logging.info("[3단계] 백테스팅 실행")
            logging.info("="*60)
            
            backtesting_framework = BacktestingFramework(db_manager)
            backtest_results = backtesting_framework.run_backtest(
                start_round=max(1, latest_round - 50),
                end_round=latest_round,
                window_size=100
            )
            
            # 성능 모니터링 업데이트
            if dashboard:
                metrics = backtest_results.get('performance_metrics', {})
                for model_type in ['lstm', 'ensemble', 'monte_carlo']:
                    model_metrics = metrics.get(model_type.upper(), {})
                    avg_matches = model_metrics.get('avg_matches', 0)
                    dashboard.update_metrics('performance', model_type, avg_matches)
        
        # ========== 4단계: 피드백 루프 (자동 개선) ==========
        if args.feedback_loop and backtest_results and models:
            logging.info("\n" + "="*60)
            logging.info("[4단계] 피드백 루프 - 자동 모델 개선")
            logging.info("="*60)
            
            feedback_system = FeedbackLoopSystem(db_manager)
            feedback_results = feedback_system.run_feedback_loop(
                models,
                start_round=max(1, latest_round - 50),
                end_round=latest_round
            )
            
            logging.info(feedback_system.get_optimization_report())
        
        # ========== 5단계: 실시간 학습 ==========
        if args.realtime_learning and models:
            logging.info("\n" + "="*60)
            logging.info("[5단계] 실시간 학습 시스템")
            logging.info("="*60)
            
            realtime_system = RealtimeLearningSystem(db_manager)
            
            # 최신 결과로 모델 업데이트
            if new_rounds:
                for round_data in new_rounds:
                    update_result = realtime_system.update_models_incrementally(
                        models,
                        {'round': round_data[0], 'numbers': [int(n) for n in round_data[1].split(',')]}
                    )
                    logging.info(f"회차 {round_data[0]} 결과로 모델 업데이트 완료")
            
            logging.info(realtime_system.get_learning_report())
        
        # ========== 6단계: 최종 예측 ==========
        logging.info("\n" + "="*60)
        logging.info("[6단계] 최종 예측 번호 생성")
        logging.info("="*60)
        
        final_predictions = []
        
        # ML 모델 예측
        if models:
            for model_type, model in models.items():
                try:
                    if model_type == 'lstm':
                        predictions = model.predict_next_numbers(
                            db_manager.get_all_winning_numbers()[-50:],
                            num_predictions=args.predictions
                        )
                    elif model_type == 'ensemble':
                        predictions = model.predict_next_numbers(
                            db_manager.get_all_winning_numbers(),
                            num_predictions=args.predictions
                        )
                    elif model_type == 'monte_carlo':
                        predictions = model.simulate(n_predictions=args.predictions)
                    
                    for pred in predictions[:5]:  # 상위 5개만
                        final_predictions.append({
                            'numbers': pred.get('numbers', pred),
                            'confidence': pred.get('confidence', 0),
                            'source': model_type.upper()
                        })
                except Exception as e:
                    logging.error(f"{model_type} 예측 오류: {str(e)}")
        
        # 예측 결과 출력
        logging.info("\n" + "◆"*30)
        logging.info("🎯 최종 예측 번호")
        logging.info("◆"*30)
        
        for i, prediction in enumerate(final_predictions[:5], 1):
            numbers_str = ', '.join(f"{num:2d}" for num in prediction['numbers'])
            confidence = prediction.get('confidence', 0)
            source = prediction.get('source', 'Unknown')
            
            logging.info(f"\n📌 추천 {i}세트: [{numbers_str}]")
            logging.info(f"   신뢰도: {confidence:.1%} | 출처: {source}")
        
        # ========== 7단계: 모니터링 대시보드 생성 ==========
        if dashboard:
            logging.info("\n" + "="*60)
            logging.info("[7단계] 성능 모니터링 대시보드 생성")
            logging.info("="*60)
            
            dashboard_path = dashboard.generate_dashboard()
            logging.info(f"대시보드 생성 완료: {dashboard_path}")
            
            # 성능 저하 확인
            degradations = dashboard.check_performance_degradation()
            if degradations:
                logging.warning("성능 저하 감지:")
                for deg in degradations:
                    logging.warning(f"  - {deg}")
        
        # 실행 시간 출력
        total_time = time.time() - start_time
        logging.info(f"\n전체 실행 시간: {total_time:.2f}초 ({total_time/60:.2f}분)")
        logging.info("\n[완료] 모든 작업이 정상적으로 완료되었습니다.")
        logging.info("="*60)
        
    except Exception as e:
        logging.error(f"프로그램 실행 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise
    finally:
        # matplotlib 정리 작업
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except:
            pass

if __name__ == "__main__":
    main()