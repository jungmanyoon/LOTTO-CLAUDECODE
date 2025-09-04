#!/usr/bin/env python3
"""
간단한 Monte Carlo 최적화 테스트
"""
import sys
import os
import time
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
from src.core.db_manager import DatabaseManager

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def simple_performance_test():
    """간단한 성능 테스트"""
    print("="*50)
    print("Monte Carlo 최적화 성능 테스트")
    print("="*50)
    
    # 데이터 로드
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    
    if len(winning_numbers) < 50:
        print(f"데이터 부족: {len(winning_numbers)}개")
        return
    
    print(f"과거 당첨번호 {len(winning_numbers)}개 로드됨")
    
    # 시뮬레이터 초기화
    simulator = MonteCarloSimulator(db_manager)
    simulator.load_historical_data(winning_numbers)
    
    # 기본 성능 테스트
    print("\n1. 기본 시뮬레이션 (조기 종료 없음)")
    simulator.clear_cache()
    start_time = time.time()
    results = simulator.simulate_combinations(2000, enable_early_termination=False)
    baseline_time = time.time() - start_time
    print(f"  - 2000회 시뮬레이션: {baseline_time:.2f}초")
    print(f"  - 처리 속도: {2000/baseline_time:.0f} sim/s")
    
    # 조기 종료 테스트
    print("\n2. 조기 종료 최적화")
    simulator.clear_cache()
    start_time = time.time()
    results = simulator.simulate_combinations(2000, enable_early_termination=True)
    optimized_time = time.time() - start_time
    print(f"  - 최대 2000회 시뮬레이션: {optimized_time:.2f}초")
    
    # 개선 효과
    improvement = ((baseline_time - optimized_time) / baseline_time) * 100
    print(f"\n3. 성능 개선 효과")
    print(f"  - 조기 종료 효과: {improvement:.1f}% 단축")
    
    # 5000회 예상 성능
    projected_5k_baseline = baseline_time * 2.5  # 2000->5000 스케일링
    projected_5k_optimized = optimized_time * 2.5
    vs_original = ((16.4 - projected_5k_optimized) / 16.4) * 100
    
    print(f"\n4. 5000회 시뮬레이션 예상 성능")
    print(f"  - 기존 예상: 16.4초")
    print(f"  - 최적화 예상: {projected_5k_optimized:.1f}초")
    print(f"  - 총 개선 효과: {vs_original:.1f}% 단축")
    
    # 최고 조합 확인
    best = simulator.get_best_combinations(3, min_confidence=0.5)
    print(f"\n5. 최적 조합 상위 3개")
    for i, combo in enumerate(best, 1):
        print(f"  {i}. {combo['numbers']} (점수: {combo['score']:.1f})")
    
    print(f"\n목표 달성: {'YES' if vs_original >= 60 else 'NO'} (60% 이상 목표)")
    
    return {
        'baseline_time': baseline_time,
        'optimized_time': optimized_time,
        'improvement_percent': improvement,
        'projected_5k_improvement': vs_original
    }

if __name__ == "__main__":
    try:
        result = simple_performance_test()
        print("\n테스트 완료!")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()