#!/usr/bin/env python3
"""
백테스팅 성능 개선 테스트 스크립트
기존 프레임워크와 최적화된 프레임워크의 성능을 비교
"""
import time
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.backtesting.backtesting_framework import BacktestingFramework
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework


def measure_performance(framework_class, db_manager, enable_fractal=False):
    """프레임워크 성능 측정"""
    start_time = time.time()
    
    # 프레임워크 초기화
    if framework_class.__name__ == 'OptimizedBacktestingFramework':
        framework = framework_class(db_manager, enable_fractal=enable_fractal)
    else:
        framework = framework_class(db_manager)
    
    # 백테스팅 실행
    results = framework.run_backtest(
        start_round=1133,
        end_round=1152,  # 20회차만 테스트
        window_size=100
    )
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    return execution_time, results


def main():
    """성능 비교 실행"""
    setup_logging()
    
    logging.info("="*60)
    logging.info("백테스팅 성능 개선 테스트")
    logging.info("="*60)
    
    db_manager = DatabaseManager()
    
    # 1. 기존 프레임워크 테스트
    logging.info("\n1. 기존 백테스팅 프레임워크 테스트...")
    original_time, original_results = measure_performance(
        BacktestingFramework, db_manager
    )
    
    # 2. 최적화된 프레임워크 테스트 (프랙탈 비활성화)
    logging.info("\n2. 최적화된 백테스팅 프레임워크 테스트 (프랙탈 비활성화)...")
    optimized_time, optimized_results = measure_performance(
        OptimizedBacktestingFramework, db_manager, enable_fractal=False
    )
    
    # 3. 성능 비교 결과
    logging.info("\n" + "="*60)
    logging.info("성능 비교 결과")
    logging.info("="*60)
    
    logging.info(f"\n기존 프레임워크:")
    logging.info(f"  - 실행 시간: {original_time:.2f}초")
    logging.info(f"  - 회차당 평균: {original_time/20:.2f}초")
    
    logging.info(f"\n최적화된 프레임워크:")
    logging.info(f"  - 실행 시간: {optimized_time:.2f}초")
    logging.info(f"  - 회차당 평균: {optimized_time/20:.2f}초")
    
    improvement = (original_time - optimized_time) / original_time * 100
    speedup = original_time / optimized_time
    
    logging.info(f"\n성능 개선:")
    logging.info(f"  - 개선율: {improvement:.1f}%")
    logging.info(f"  - 속도 향상: {speedup:.1f}배")
    logging.info(f"  - 절약 시간: {original_time - optimized_time:.2f}초")
    
    # 4. 정확도 비교
    logging.info("\n" + "="*60)
    logging.info("정확도 비교")
    logging.info("="*60)
    
    # 모델별 성능 비교
    models = ['lstm', 'ensemble', 'monte_carlo', 'combined']
    for model in models:
        original_perf = original_results['performance_metrics']['model_performance'].get(model, {})
        optimized_perf = optimized_results['performance_metrics']['model_performance'].get(model, {})
        
        logging.info(f"\n[{model.upper()}]")
        logging.info(f"  기존 - 평균 일치: {original_perf.get('avg_matches', 0):.2f}개")
        logging.info(f"  최적화 - 평균 일치: {optimized_perf.get('avg_matches', 0):.2f}개")
        logging.info(f"  기존 - 3개 이상 일치율: {original_perf.get('accuracy_3plus', 0):.2f}%")
        logging.info(f"  최적화 - 3개 이상 일치율: {optimized_perf.get('accuracy_3plus', 0):.2f}%")
    
    # 5. 최종 권장사항
    logging.info("\n" + "="*60)
    logging.info("최종 권장사항")
    logging.info("="*60)
    
    if improvement > 30:
        logging.info("✅ 최적화가 매우 효과적입니다!")
        logging.info("   - 캐싱 시스템이 잘 작동하고 있습니다")
        logging.info("   - 병렬 처리가 성능을 크게 향상시켰습니다")
    elif improvement > 10:
        logging.info("✅ 최적화가 효과적입니다!")
        logging.info("   - 추가 최적화 여지가 있을 수 있습니다")
    else:
        logging.info("⚠️ 최적화 효과가 제한적입니다")
        logging.info("   - 다른 병목 지점을 찾아야 할 수 있습니다")
    
    logging.info("\n추가 최적화 방안:")
    logging.info("1. GPU 가속 활용 (TensorFlow/PyTorch)")
    logging.info("2. 더 공격적인 캐싱 전략")
    logging.info("3. 데이터베이스 쿼리 최적화")
    logging.info("4. 메모리 사용량 프로파일링")


if __name__ == "__main__":
    main()