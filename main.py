import logging
import argparse
import os
import time

# TensorFlow oneDNN 경고 억제
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# TensorFlow 로깅 레벨 설정
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # WARNING 이상만 표시

from src.filters.average_filter import AverageFilter
from src.filters.section_filter import SectionFilter
from src.logger import setup_logging
from src.core.db_structure import DatabasePaths
from src.core.db_manager import DatabaseManager
from src.meta_data_manager import MetaDataManager
from src.data_collector import DataCollector
from src.core.combination_manager import CombinationManager
from src.core.filter_manager import FilterManager
from src.core.pattern_manager import PatternManager
from src.filters.match_filter import MatchFilter
from src.filters.odd_even_filter import OddEvenFilter
from src.filters.consecutive_filter import ConsecutiveFilter
from src.filters.sum_range_filter import SumRangeFilter
from src.filters.fixed_step_filter import FixedStepFilter
from src.filters.last_digit_filter import LastDigitFilter
from src.filters.max_gap_filter import MaxGapFilter
from src.filters.multiple_filter import MultipleFilter
from src.utils.constants import LottoConstants
from src.core.specialized_databases import PatternsDB
from src.filters.ten_section_filter import TenSectionFilter  # 신규 추가
from src.filters.arithmetic_sequence_filter import ArithmeticSequenceFilter  # 신규 추가
from src.filters.geometric_sequence_filter import GeometricSequenceFilter  # 신규 추가
from src.utils.config_manager import ConfigManager
from src.utils.db_migrator import DatabaseMigrator  # 신규 추가

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
    logging.warning(f"확률 모듈 로드 실패: {e}")

try:
    from src.advanced.fractal_pattern_analyzer import FractalPatternAnalyzer
    ADVANCED_AVAILABLE = True
except ImportError as e:
    ADVANCED_AVAILABLE = False
    logging.warning(f"고급 분석 모듈 로드 실패: {e}")

try:
    from src.enhanced_dynamic_filter_manager import EnhancedDynamicFilterManager
    DYNAMIC_FILTER_AVAILABLE = True
except ImportError as e:
    DYNAMIC_FILTER_AVAILABLE = False
    logging.warning(f"동적 필터 매니저 로드 실패: {e}")

def parse_args():
    """명령줄 인수 파싱"""
    parser = argparse.ArgumentParser(description='로또 번호 분석 및 필터링 프로그램')
    parser.add_argument('--config', type=str, help='설정 파일 경로')
    parser.add_argument('--optimize', action='store_true', help='최적화된 저장 방식 사용')
    parser.add_argument('--parallel', action='store_true', help='병렬 처리 사용')
    parser.add_argument('--workers', type=int, help='병렬 작업자 수')
    parser.add_argument('--skip-fetch', action='store_true', help='데이터 수집 단계 건너뛰기')
    parser.add_argument('--skip-patterns', action='store_true', help='패턴 분석 단계 건너뛰기')
    parser.add_argument('--full-filter', action='store_true', default=True, help='전체 필터링 수행')
    parser.add_argument('--reset-db', action='store_true', help='데이터베이스 강제 초기화 (개발용)')
    parser.add_argument('--force-no-migration', action='store_true', help='데이터베이스 마이그레이션 건너뛰기 (개발용)')
    parser.add_argument('--ignore-migration-errors', action='store_true', help='마이그레이션 오류를 무시하고 계속 진행합니다 (오류 발생 가능)')
    parser.add_argument('--force', action='store_true', help='모든 오류를 무시하고 강제로 실행 (위험)')
    parser.add_argument('--force-filter', action='store_true', default=True, help='이전 필터링 여부와 상관없이 필터링을 강제 실행합니다')
    
    # ML/AI 관련 옵션
    parser.add_argument('--skip-ml', action='store_true', help='ML/AI 분석 건너뛰기')
    parser.add_argument('--ml-only', action='store_true', help='ML/AI 분석만 수행')
    parser.add_argument('--lstm', action='store_true', default=True, help='LSTM 시계열 예측 사용')
    parser.add_argument('--no-lstm', dest='lstm', action='store_false', help='LSTM 사용 안함')
    parser.add_argument('--ensemble', action='store_true', default=True, help='앙상블 모델 예측 사용')
    parser.add_argument('--no-ensemble', dest='ensemble', action='store_false', help='앙상블 사용 안함')
    parser.add_argument('--monte-carlo', action='store_true', default=True, help='Monte Carlo 시뮬레이션 사용')
    parser.add_argument('--no-monte-carlo', dest='monte_carlo', action='store_false', help='Monte Carlo 사용 안함')
    parser.add_argument('--bayesian', action='store_true', default=True, help='베이지안 추론 사용')
    parser.add_argument('--no-bayesian', dest='bayesian', action='store_false', help='베이지안 사용 안함')
    parser.add_argument('--fractal', action='store_true', default=True, help='프랙탈 패턴 분석 사용')
    parser.add_argument('--no-fractal', dest='fractal', action='store_false', help='프랙탈 사용 안함')
    parser.add_argument('--dynamic-filter', action='store_true', default=True, help='동적 필터 모니터링 사용')
    parser.add_argument('--no-dynamic-filter', dest='dynamic_filter', action='store_false', help='동적 필터 사용 안함')
    parser.add_argument('--predictions', type=int, default=5, help='ML 예측 조합 수')
    
    return parser.parse_args()

def main():
    # 명령줄 인수 파싱
    args = parse_args()
    
    # 설정 로드 및 로깅 설정
    config_path = args.config
    if config_path is None and os.path.exists('config.yaml'):
        config_path = 'config.yaml'
        logging.info(f"설정 파일 경로가 지정되지 않아 기본 경로 '{config_path}'를 사용합니다.")
    
    setup_logging(config_path)
    
    try:
        # 설정 관리자 초기화
        config_manager = ConfigManager(config_path)
        
        logging.info("[초기화] 데이터베이스 및 매니저 초기화 중...")
        meta_manager = MetaDataManager()
        
        # 데이터베이스 초기화/마이그레이션 처리
        should_continue = True  # 계속 진행 여부
        db_initialized = False  # DB 초기화 성공 여부
        
        if args.reset_db:
            # 사용자가 명시적으로 초기화를 요청한 경우
            logging.warning("사용자 요청으로 데이터베이스를 강제 초기화합니다.")
            try:
                db_migrator = DatabaseMigrator(meta_manager)
                reset_result = db_migrator.reset_database()
                
                if not reset_result:
                    logging.error("데이터베이스 초기화 실패")
                    if args.ignore_migration_errors or args.force:
                        logging.warning("데이터베이스 초기화 오류를 무시하고 계속 진행합니다 (ignore-migration-errors 또는 force 옵션 사용)")
                    else:
                        logging.error("프로그램을 정상적으로 실행하려면 다음 문제를 해결해야 합니다:")
                        logging.error("1. 다른 프로그램이 데이터베이스 파일을 사용 중인지 확인하세요.")
                        logging.error("2. 데이터베이스 파일에 대한 쓰기 권한이 있는지 확인하세요.")
                        logging.error("3. 디스크 공간이 충분한지 확인하세요.")
                        logging.error("4. 관리자 권한으로 실행해보세요.")
                        logging.error("오류를 무시하고 계속 진행하려면 --ignore-migration-errors 또는 --force 옵션을 사용하세요.")
                        should_continue = False
                else:
                    db_initialized = True
                
                if should_continue:
                    # 최적화 모드 설정 업데이트
                    storage_mode = "optimized" if args.optimize else "legacy"
                    try:
                        update_result = meta_manager.update_db_info(
                            version=DatabaseMigrator.CURRENT_REQUIRED_VERSION,
                            storage_mode=storage_mode
                        )
                        
                        if not update_result and not (args.ignore_migration_errors or args.force):
                            logging.error("메타데이터 업데이트 실패")
                            should_continue = False
                    except Exception as update_err:
                        logging.error(f"메타데이터 업데이트 중 오류 발생: {str(update_err)}")
                        if not (args.ignore_migration_errors or args.force):
                            should_continue = False
            except Exception as init_err:
                logging.error(f"초기화 과정에서 예외 발생: {str(init_err)}")
                if args.force:
                    logging.warning("force 옵션으로 오류 무시하고 계속 진행합니다.")
                else:
                    should_continue = False
                    
        elif not args.force_no_migration and should_continue:
            # 자동 마이그레이션 수행 (필요한 경우에만)
            try:
                logging.info("데이터베이스 호환성 검사 중...")
                db_migrator = DatabaseMigrator(meta_manager)
                
                # 저장 모드 결정
                target_storage_mode = "optimized" if args.optimize else None
                
                # 필요한 경우 마이그레이션 수행
                success, message = db_migrator.migrate_if_needed(target_storage_mode)
                if success:
                    logging.info(message)
                    db_initialized = True
                else:
                    logging.error(f"마이그레이션 실패: {message}")
                    if args.ignore_migration_errors or args.force:
                        logging.warning("마이그레이션 오류를 무시하고 계속 진행합니다 (ignore-migration-errors 또는 force 옵션 사용)")
                    else:
                        logging.error("데이터베이스 문제를 해결하려면 다음 옵션 중 하나를 사용하세요:")
                        logging.error("1. --reset-db: 데이터베이스를 초기화합니다 (데이터 손실 발생)")
                        logging.error("2. --force-no-migration: 마이그레이션을 건너뜁니다 (호환성 문제 발생 가능)")
                        logging.error("3. --ignore-migration-errors: 마이그레이션 오류를 무시하고 계속 진행합니다 (오류 발생 가능)")
                        logging.error("4. --force: 모든 오류를 무시하고 강제로 실행합니다 (위험)")
                        should_continue = False
            except Exception as migration_err:
                logging.error(f"마이그레이션 과정에서 예외 발생: {str(migration_err)}")
                if args.force:
                    logging.warning("force 옵션으로 오류 무시하고 계속 진행합니다.")
                else:
                    should_continue = False
        else:
            # 마이그레이션 건너뛰기
            logging.info("데이터베이스 마이그레이션을 건너뜁니다.")
            db_initialized = True
                    
        if not should_continue:
            raise Exception("데이터베이스 초기화 또는 마이그레이션 실패")
                    
        try:
            # 데이터베이스 매니저 초기화 (마이그레이션 후에 초기화)
            db_manager = DatabaseManager()
            
            # 저장 모드 설정
            if args.optimize and meta_manager.get_db_storage_mode() != "optimized":
                logging.info("최적화된 데이터 저장 방식으로 설정합니다.")
                try:
                    db_manager.combinations_db.set_storage_mode('optimized')
                    meta_manager.update_db_info(storage_mode="optimized")
                except Exception as mode_err:
                    logging.error(f"저장 모드 설정 실패: {str(mode_err)}")
                    if not (args.ignore_migration_errors or args.force):
                        raise
            
            # 명령줄 인수로 필터링 설정 업데이트
            filtering_config = config_manager.get_filtering_config()
            if args.parallel is not None:
                filtering_config['use_parallel'] = args.parallel
            if args.workers is not None:
                filtering_config['max_workers'] = args.workers
                
        except Exception as db_err:
            logging.error(f"데이터베이스 초기화 중 오류 발생: {str(db_err)}")
            if args.ignore_migration_errors or args.force:
                logging.warning("데이터베이스 오류를 무시하고 계속 시도합니다. 추가 오류가 발생할 수 있습니다.")
            else:
                raise
        
        # 데이터 수집 (선택적 건너뛰기)
        if not args.skip_fetch:
            logging.info("\n[데이터 수집] 로또 당첨 번호 수집 시작...")
            collector = DataCollector(db_manager=db_manager, meta_manager=meta_manager)
            collector.fetch_lotto_data()
        else:
            logging.info("\n[데이터 수집] 건너뛰기")
        
        # 패턴 분석 (선택적 건너뛰기)
        if not args.skip_patterns:
            logging.info("\n[패턴 분석] 데이터 패턴 분석 시작...")
            pattern_manager = PatternManager(db_manager)
            latest_round = db_manager.lotto_db.get_last_round()
            pattern_manager.analyze_patterns(latest_round)
        else:
            logging.info("\n[패턴 분석] 건너뛰기")
            latest_round = db_manager.lotto_db.get_last_round()
        
        # ML/AI 분석 및 예측 (선택적)
        if not args.skip_ml:
            logging.info("\n" + "="*60)
            logging.info("[ML/AI 분석] 인공지능 기반 분석 및 예측 시작...")
            logging.info("="*60)
            
            # 당첨번호 데이터 준비
            winning_numbers = db_manager.get_all_winning_numbers()
            
            if winning_numbers and len(winning_numbers) >= 50:
                # 1. LSTM 시계열 예측
                if args.lstm and ML_AVAILABLE:
                    try:
                        logging.info("\n[LSTM] 시계열 예측 모델 실행...")
                        lstm_predictor = LSTMPredictor(sequence_length=50)
                        
                        # 모델 학습 (필요시)
                        if not lstm_predictor.is_trained:
                            logging.info("  - LSTM 모델 학습 중...")
                            lstm_predictor.train(winning_numbers, epochs=30, batch_size=32)
                        
                        # 예측 수행
                        lstm_predictions = lstm_predictor.predict_next_numbers(
                            winning_numbers[-50:], 
                            num_predictions=args.predictions
                        )
                        
                        logging.info(f"  - LSTM 예측 완료: {len(lstm_predictions)}개 조합")
                        for i, pred in enumerate(lstm_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - LSTM 예측 실패: {str(e)}")
                
                # 2. 앙상블 모델 예측
                if args.ensemble and ML_AVAILABLE:
                    try:
                        logging.info("\n[Ensemble] 앙상블 모델 (RF+XGBoost+NN) 실행...")
                        ensemble_predictor = EnsemblePredictor()
                        
                        # 모델 학습 (필요시)
                        if not ensemble_predictor.is_trained:
                            logging.info("  - 앙상블 모델 학습 중...")
                            evaluation = ensemble_predictor.train(winning_numbers, test_size=0.2)
                            if evaluation:
                                logging.info(f"  - 학습 완료: 정확도 {evaluation.get('ensemble', {}).get('accuracy', 0):.4f}")
                        
                        # 예측 수행
                        ensemble_predictions = ensemble_predictor.predict_next_numbers(
                            winning_numbers,
                            num_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 앙상블 예측 완료: {len(ensemble_predictions)}개 조합")
                        for i, pred in enumerate(ensemble_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - 앙상블 예측 실패: {str(e)}")
                
                # 3. Monte Carlo 시뮬레이션
                if args.monte_carlo and PROBABILISTIC_AVAILABLE:
                    try:
                        logging.info("\n[Monte Carlo] 확률적 시뮬레이션 실행...")
                        mc_simulator = MonteCarloSimulator(db_manager)
                        mc_simulator.load_historical_data(winning_numbers)
                        
                        # 시뮬레이션 실행
                        logging.info("  - 10,000회 시뮬레이션 중...")
                        start_time = time.time()
                        mc_simulator.simulate_combinations(10000)
                        elapsed = time.time() - start_time
                        
                        # 최적 조합 추출
                        mc_predictions = mc_simulator.get_best_combinations(
                            n_combinations=args.predictions,
                            min_confidence=0.6
                        )
                        
                        logging.info(f"  - 시뮬레이션 완료 ({elapsed:.1f}초): {len(mc_predictions)}개 조합")
                        for i, pred in enumerate(mc_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (점수: {pred['score']:.2f}, 신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - Monte Carlo 시뮬레이션 실패: {str(e)}")
                
                # 4. 베이지안 추론
                if args.bayesian and PROBABILISTIC_AVAILABLE:
                    try:
                        logging.info("\n[Bayesian] 베이지안 추론 시스템 실행...")
                        bayesian_filter = BayesianFilter(db_manager)
                        
                        # 사전분포 초기화
                        logging.info("  - 사전분포 초기화 중...")
                        bayesian_filter.initialize_priors(winning_numbers[:-10])
                        
                        # 예측 수행
                        bayesian_predictions = bayesian_filter.predict_next_combination(
                            winning_numbers[-10:],
                            n_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 베이지안 예측 완료: {len(bayesian_predictions)}개 조합")
                        for i, pred in enumerate(bayesian_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (우도: {pred['likelihood']:.6f})")
                        
                        # 신념 시각화 저장
                        bayesian_filter.visualize_beliefs()
                        bayesian_filter.save_beliefs()
                    
                    except Exception as e:
                        logging.error(f"  - 베이지안 추론 실패: {str(e)}")
                
                # 5. 프랙탈 패턴 분석
                if args.fractal and ADVANCED_AVAILABLE:
                    try:
                        logging.info("\n[Fractal] 프랙탈 패턴 분석 실행...")
                        fractal_analyzer = FractalPatternAnalyzer(db_manager)
                        
                        # 시계열 데이터 로드
                        logging.info("  - 시계열 데이터 로드 중...")
                        fractal_analyzer.load_time_series(winning_numbers)
                        
                        # 프랙탈 패턴 탐지
                        logging.info("  - 프랙탈 패턴 분석 중...")
                        patterns = fractal_analyzer.detect_fractal_patterns()
                        
                        # 결과 출력
                        if patterns.get('fractal_dimensions'):
                            logging.info("  - 프랙탈 차원:")
                            for key, dim in list(patterns['fractal_dimensions'].items())[:3]:
                                logging.info(f"    {key}: {dim:.3f}")
                        
                        if patterns.get('chaos_metrics'):
                            logging.info("  - 카오스 메트릭:")
                            for key, value in list(patterns['chaos_metrics'].items())[:3]:
                                logging.info(f"    {key}: {value:.3f}")
                        
                        # 프랙탈 기반 예측
                        fractal_predictions = fractal_analyzer.predict_with_fractals(
                            n_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 프랙탈 예측 완료: {len(fractal_predictions)}개 조합")
                        for i, pred in enumerate(fractal_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                        
                        # 분석 결과 저장
                        fractal_analyzer.visualize_fractal_analysis()
                        fractal_analyzer.save_analysis()
                    
                    except Exception as e:
                        logging.error(f"  - 프랙탈 분석 실패: {str(e)}")
            
            else:
                logging.warning("ML/AI 분석을 위한 충분한 데이터가 없습니다. (최소 50개 필요)")
        
        # ML만 수행 모드
        if args.ml_only:
            logging.info("\n[완료] ML/AI 분석만 수행하고 종료합니다.")
            return
        
        # 필터링 초기화 및 실행
        logging.info("\n" + "="*60)
        logging.info("[조합 필터링] 로또 번호 조합 필터링 시작...")
        logging.info("="*60)
        
        # 동적 필터 매니저 초기화 (사용 가능한 경우)
        enhanced_filter_manager = None
        if args.dynamic_filter and DYNAMIC_FILTER_AVAILABLE:
            try:
                logging.info("\n[동적 필터] 실시간 모니터링 시스템 시작...")
                enhanced_filter_manager = EnhancedDynamicFilterManager(db_manager)
                enhanced_filter_manager.start_monitoring()
                logging.info("  - 실시간 모니터링 활성화됨")
            except Exception as e:
                logging.error(f"  - 동적 필터 초기화 실패: {str(e)}")
        
        # 기본 조합 확인 및 생성
        combination_manager = CombinationManager(db_manager)
        if not db_manager.combinations_db.check_base_combinations_exist():
            logging.info("\n[기본 조합 생성] 시작...")
            combination_manager.generate_base_combinations()
         
        # 필터 매니저 초기화 및 필터 등록 (자동)
        filter_manager = FilterManager(db_manager)
        
        # ML 예측기를 필터에 연결 (사용 가능한 경우)
        if ML_AVAILABLE and 'ensemble_predictor' in locals():
            try:
                ml_filter = filter_manager.filters.get('ml_prediction')
                if ml_filter:
                    ml_filter.set_predictor(ensemble_predictor)
                    logging.info("[ML 필터] 앙상블 예측기가 ML 필터에 연결되었습니다.")
            except Exception as e:
                logging.warning(f"ML 필터 연결 실패: {str(e)}")
        
        # 필터링 모드 결정 및 필터 적용
        update_mode = 'full' if args.full_filter or args.force_filter else 'incremental'
        
        # 기존 필터링 결과 무시하고 강제로 새로 필터링 실행
        logging.info("\n[필터링 강제 실행] 모든 필터를 처음부터 적용합니다...")
        filter_manager.apply_filters(latest_round, 'full', force=True)
        
        # 동적 필터 모니터링 중지 및 보고서 저장
        if enhanced_filter_manager:
            try:
                logging.info("\n[동적 필터] 성능 보고서 생성 중...")
                enhanced_filter_manager.export_performance_report()
                enhanced_filter_manager.stop_monitoring()
                logging.info("  - 성능 보고서가 저장되었습니다.")
            except Exception as e:
                logging.error(f"  - 동적 필터 보고서 생성 실패: {str(e)}")
        
        logging.info("\n[완료] 모든 작업이 정상적으로 완료되었습니다.")
        logging.info("="*60)
        
    except Exception as e:
        logging.error(f"프로그램 실행 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        logging.info("="*60)
        raise

if __name__ == "__main__":
    main()