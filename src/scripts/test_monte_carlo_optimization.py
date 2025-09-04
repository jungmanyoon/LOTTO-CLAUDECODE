#!/usr/bin/env python3
"""
Monte Carlo 시뮬레이터 최적화 테스트
성능 개선 효과 검증 및 벤치마크
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

def test_optimization_effects():
    """최적화 효과 테스트"""
    print("="*70)
    print("Monte Carlo 시뮬레이터 최적화 효과 테스트")
    print("="*70)
    
    # 데이터 로드
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    
    if len(winning_numbers) < 50:
        print(f"❌ 데이터 부족: {len(winning_numbers)}개 (최소 50개 필요)")
        return
    
    print(f"✅ 과거 당첨번호 {len(winning_numbers)}개 로드됨")
    
    # 시뮬레이터 초기화
    simulator = MonteCarloSimulator(db_manager)
    simulator.load_historical_data(winning_numbers)
    
    # 테스트 파라미터
    test_simulations = [1000, 2000, 5000]
    
    print("\n" + "="*70)
    print("📊 성능 벤치마크 (조기 종료 비활성화)")
    print("="*70)
    
    baseline_results = []
    
    for n_sim in test_simulations:
        print(f"\n🔄 {n_sim:,}회 시뮬레이션 테스트...")
        
        # 캐시 초기화
        simulator.clear_cache()
        
        # 벡터화된 최적화 버전 (조기 종료 없음)
        start_time = time.time()
        results = simulator.simulate_combinations(n_sim, enable_early_termination=False)
        elapsed = time.time() - start_time
        rate = n_sim / elapsed
        
        baseline_results.append({
            'simulations': n_sim,
            'elapsed': elapsed,
            'rate': rate,
            'top_score': results[0][1] if results else 0
        })
        
        print(f"  ⏱️  실행 시간: {elapsed:.2f}초")
        print(f"  🚀 처리 속도: {rate:.0f} 시뮬레이션/초")
        print(f"  🎯 최고 점수: {results[0][1]:.2f}")
    
    print("\n" + "="*70)
    print("⚡ 조기 종료 최적화 효과 테스트")
    print("="*70)
    
    early_termination_results = []
    
    for n_sim in test_simulations:
        print(f"\n🔄 {n_sim:,}회 시뮬레이션 (조기 종료 활성화)...")
        
        # 캐시 초기화
        simulator.clear_cache()
        
        # 조기 종료 최적화 버전
        start_time = time.time()
        results = simulator.simulate_combinations(n_sim, enable_early_termination=True)
        elapsed = time.time() - start_time
        
        # 실제 시뮬레이션 횟수 추정 (캐시 통계로)
        cache_stats = simulator.get_cache_stats()
        
        early_termination_results.append({
            'target_simulations': n_sim,
            'elapsed': elapsed,
            'top_score': results[0][1] if results else 0
        })
        
        print(f"  ⏱️  실행 시간: {elapsed:.2f}초")
        print(f"  🎯 최고 점수: {results[0][1]:.2f}")
        
        # 기존 버전과 비교
        baseline = next(r for r in baseline_results if r['simulations'] == n_sim)
        improvement = ((baseline['elapsed'] - elapsed) / baseline['elapsed']) * 100
        
        print(f"  📈 성능 개선: {improvement:.1f}% 단축")
    
    print("\n" + "="*70)
    print("💾 캐싱 효과 테스트")
    print("="*70)
    
    # 동일한 시뮬레이션 반복 실행 (캐싱 효과 확인)
    print("\n🔄 동일한 시뮬레이션 2회 연속 실행 (캐싱 효과 확인)...")
    
    # 첫 번째 실행
    simulator.clear_cache()
    start_time = time.time()
    simulator.simulate_combinations(2000, enable_early_termination=False)
    first_elapsed = time.time() - start_time
    
    # 두 번째 실행 (캐시 사용)
    start_time = time.time()
    simulator.simulate_combinations(2000, enable_early_termination=False)
    second_elapsed = time.time() - start_time
    
    cache_improvement = ((first_elapsed - second_elapsed) / first_elapsed) * 100
    
    print(f"  첫 번째 실행: {first_elapsed:.2f}초")
    print(f"  두 번째 실행: {second_elapsed:.2f}초 (캐시 사용)")
    print(f"  캐싱 효과: {cache_improvement:.1f}% 단축")
    
    # 캐시 통계
    cache_stats = simulator.get_cache_stats()
    print(f"  캐시 크기: {cache_stats['simulation_cache_size']}개")
    print(f"  메모리 사용량: {cache_stats['memory_usage_mb']:.1f}MB")
    
    print("\n" + "="*70)
    print("📋 최적화 효과 종합 요약")
    print("="*70)
    
    # 5000회 기준 개선 효과 계산
    baseline_5k = next(r for r in baseline_results if r['simulations'] == 5000)
    early_5k = next(r for r in early_termination_results if r['target_simulations'] == 5000)
    
    total_improvement = ((baseline_5k['elapsed'] - early_5k['elapsed']) / baseline_5k['elapsed']) * 100
    expected_old_time = 16.4  # 원래 문제에서 제시된 시간
    vs_original = ((expected_old_time - early_5k['elapsed']) / expected_old_time) * 100
    
    print(f"\n🎯 5,000회 시뮬레이션 기준:")
    print(f"  • 기존 예상 시간: {expected_old_time:.1f}초")
    print(f"  • 벡터화 최적화: {baseline_5k['elapsed']:.1f}초")
    print(f"  • 조기 종료 최적화: {early_5k['elapsed']:.1f}초")
    print(f"  • 총 성능 개선: {vs_original:.1f}% 단축")
    print(f"  • 목표 달성: {'✅' if vs_original >= 60 else '❌'} (목표: 60% 이상)")
    
    print(f"\n🔧 적용된 최적화 기법:")
    print(f"  ✅ 벡터화된 NumPy 연산")
    print(f"  ✅ 배치 처리 (500개 단위)")
    print(f"  ✅ 수렴 감지 조기 종료")
    print(f"  ✅ 지능형 캐싱 시스템")
    print(f"  ✅ 메모리 효율적 계산")
    print(f"  ✅ 병렬 처리 오버헤드 제거")
    
    print(f"\n🎊 결과:")
    if vs_original >= 60:
        print(f"  🎉 최적화 목표 달성! {vs_original:.1f}% 성능 개선")
        print(f"  🚀 {expected_old_time:.1f}초 → {early_5k['elapsed']:.1f}초")
    else:
        print(f"  ⚠️  추가 최적화 필요: {vs_original:.1f}% 개선")
    
    return {
        'baseline_results': baseline_results,
        'early_termination_results': early_termination_results,
        'total_improvement_percent': vs_original,
        'target_achieved': vs_original >= 60
    }

def test_specific_optimizations():
    """특정 최적화 기법별 효과 테스트"""
    print("\n" + "="*70)
    print("🔬 개별 최적화 기법 효과 분석")
    print("="*70)
    
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    simulator = MonteCarloSimulator(db_manager)
    simulator.load_historical_data(winning_numbers)
    
    n_test = 2000
    
    # 1. 상관관계 사용 vs 미사용
    print(f"\n🧪 상관관계 사용 효과 테스트:")
    
    # 상관관계 사용
    simulator.probability_model['use_correlations'] = True
    simulator.clear_cache()
    start_time = time.time()
    simulator.simulate_combinations(n_test, enable_early_termination=False)
    corr_time = time.time() - start_time
    
    # 상관관계 미사용 (더 빠른 벡터화 가능)
    simulator.probability_model['use_correlations'] = False
    simulator.clear_cache()
    start_time = time.time()
    simulator.simulate_combinations(n_test, enable_early_termination=False)
    no_corr_time = time.time() - start_time
    
    corr_improvement = ((corr_time - no_corr_time) / corr_time) * 100
    
    print(f"  상관관계 사용: {corr_time:.2f}초")
    print(f"  상관관계 미사용: {no_corr_time:.2f}초")
    print(f"  속도 개선: {corr_improvement:.1f}%")
    
    # 원래 설정으로 복원
    simulator.probability_model['use_correlations'] = True
    
    # 2. 배치 크기 최적화 테스트
    print(f"\n🧪 배치 크기 최적화 테스트:")
    batch_sizes = [100, 500, 1000]
    
    for batch_size in batch_sizes:
        # 원래 배치 크기 저장
        original_method = simulator._simulate_batch_vectorized
        
        # 배치 크기별 테스트 (시뮬레이션 내부에서 배치 크기 고정)
        simulator.clear_cache()
        start_time = time.time()
        
        # 직접 배치 시뮬레이션 호출
        total_batches = n_test // batch_size
        for _ in range(total_batches):
            simulator._simulate_batch_vectorized(batch_size)
        
        batch_time = time.time() - start_time
        rate = n_test / batch_time
        
        print(f"  배치 크기 {batch_size:4d}: {batch_time:.2f}초 ({rate:.0f} sim/s)")
    
    print(f"\n✨ 최적화 분석 완료!")

if __name__ == "__main__":
    try:
        # 기본 최적화 효과 테스트
        results = test_optimization_effects()
        
        # 개별 최적화 기법 테스트
        test_specific_optimizations()
        
        print(f"\n🏁 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()