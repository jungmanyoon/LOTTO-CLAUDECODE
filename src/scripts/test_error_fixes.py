#!/usr/bin/env python3
"""
백테스팅 에러 수정 테스트 스크립트
수정된 OptimizedBacktestingFramework가 에러 없이 작동하는지 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework


def test_error_fixes():
    """에러 수정 테스트"""
    setup_logging()
    
    logging.info("="*60)
    logging.info("백테스팅 에러 수정 테스트 시작")
    logging.info("="*60)
    
    db_manager = DatabaseManager()
    
    # 최적화된 프레임워크로 테스트
    try:
        logging.info("\n1. OptimizedBacktestingFramework 초기화...")
        framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
        logging.info("✅ 초기화 성공")
        
        logging.info("\n2. 백테스팅 실행 (5회차만 테스트)...")
        results = framework.run_backtest(
            start_round=1133,
            end_round=1137,  # 5회차만
            window_size=100
        )
        
        # 결과 분석
        logging.info("\n3. 결과 분석...")
        predictions = results.get('predictions', [])
        error_count = 0
        success_count = 0
        
        for pred in predictions:
            if 'error' in pred:
                error_count += 1
                logging.error(f"  - 회차 {pred['round']}: 에러 발생 - {pred['error']}")
            else:
                success_count += 1
                # 각 모델의 예측 결과 확인
                model_results = pred.get('predictions', {})
                for model_name, model_preds in model_results.items():
                    if model_preds:
                        logging.info(f"  - 회차 {pred['round']} {model_name}: {len(model_preds)}개 예측 생성")
        
        # 성능 지표 확인
        metrics = results.get('performance_metrics', {})
        if metrics:
            logging.info("\n4. 성능 지표:")
            total_rounds = metrics.get('total_rounds', 0)
            logging.info(f"  - 총 테스트 회차: {total_rounds}")
            
            for model_name, model_metrics in metrics.get('model_performance', {}).items():
                logging.info(f"\n  [{model_name.upper()}]")
                logging.info(f"    - 총 예측 수: {model_metrics.get('total_predictions', 0)}")
                logging.info(f"    - 평균 일치: {model_metrics.get('avg_matches', 0):.2f}개")
        
        # 최종 결과
        logging.info("\n" + "="*60)
        logging.info("테스트 결과 요약")
        logging.info("="*60)
        logging.info(f"✅ 성공: {success_count}회차")
        logging.info(f"❌ 실패: {error_count}회차")
        
        if error_count == 0:
            logging.info("\n🎉 모든 에러가 해결되었습니다!")
        else:
            logging.warning(f"\n⚠️ {error_count}개 회차에서 여전히 에러가 발생합니다.")
        
        # 캐시 확인
        cache_dir = "cache/models"
        if os.path.exists(cache_dir):
            cache_files = os.listdir(cache_dir)
            logging.info(f"\n캐시 파일 수: {len(cache_files)}개")
        
        return error_count == 0
        
    except Exception as e:
        logging.error(f"\n테스트 중 예외 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False


def main():
    """메인 실행 함수"""
    success = test_error_fixes()
    
    if success:
        logging.info("\n✅ 에러 수정이 성공적으로 완료되었습니다!")
        logging.info("   main.py를 F5로 실행할 준비가 되었습니다.")
    else:
        logging.error("\n❌ 일부 에러가 여전히 존재합니다.")
        logging.error("   추가 디버깅이 필요합니다.")


if __name__ == "__main__":
    main()