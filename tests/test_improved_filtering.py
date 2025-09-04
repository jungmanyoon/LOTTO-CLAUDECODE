"""개선된 필터링 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager
import random

def test_improved_filtering():
    """개선된 필터링 테스트"""
    
    print("\n" + "="*60)
    print("개선된 필터링 테스트")
    print("="*60)
    
    # 설정 다시 로드
    config_manager = ConfigManager()
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # sum_range 설정 확인
    sum_range_config = config_manager.config['filters']['criteria']['sum_range']
    print(f"\nsum_range 설정:")
    print(f"  min_sum: {sum_range_config['min_sum']}")
    print(f"  max_sum: {sum_range_config['max_sum']}")
    
    # 테스트 1: 랜덤 조합으로 테스트
    print(f"\n[테스트 1] 랜덤 조합 1000개")
    print("-"*50)
    
    random_combinations = []
    for _ in range(1000):
        numbers = sorted(random.sample(range(1, 46), 6))
        combo_str = ','.join(map(str, numbers))
        random_combinations.append(combo_str)
    
    # 주요 필터만 테스트
    test_filters = ['sum_range', 'average', 'consecutive', 'odd_even']
    current = random_combinations.copy()
    
    for filter_name in test_filters:
        if filter_name in filter_manager.filters:
            filter_obj = filter_manager.filters[filter_name]
            before = len(current)
            current = filter_obj.apply(current, 1186)  # 새 회차로 테스트
            after = len(current)
            exclude_rate = (before - after) / before * 100 if before > 0 else 0
            print(f"  {filter_name:15s}: {before:4d} → {after:4d} ({exclude_rate:5.1f}% 제외)")
    
    survival_rate = len(current) / 1000 * 100
    print(f"\n  최종: {len(current)}개 (생존율 {survival_rate:.1f}%)")
    
    # 테스트 2: 실제 조합에서 랜덤 샘플
    print(f"\n[테스트 2] 실제 조합에서 랜덤 10,000개")
    print("-"*50)
    
    # 전체 조합에서 랜덤하게 선택
    all_combinations = db_manager.combinations_db.get_base_combinations()
    
    if len(all_combinations) > 10000:
        # 랜덤하게 10000개 선택
        sample_indices = random.sample(range(len(all_combinations)), 10000)
        sample_combinations = [all_combinations[i] for i in sample_indices]
    else:
        sample_combinations = all_combinations
    
    current = sample_combinations.copy()
    
    for filter_name in test_filters:
        if filter_name in filter_manager.filters:
            filter_obj = filter_manager.filters[filter_name]
            before = len(current)
            current = filter_obj.apply(current, 1186)
            after = len(current)
            exclude_rate = (before - after) / before * 100 if before > 0 else 0
            print(f"  {filter_name:15s}: {before:6d} → {after:6d} ({exclude_rate:5.1f}% 제외)")
    
    survival_rate = len(current) / len(sample_combinations) * 100
    print(f"\n  최종: {len(current):,}개 (생존율 {survival_rate:.1f}%)")
    
    # 814만개 추정
    estimated = int(8145060 * survival_rate / 100)
    print(f"\n[814만개 추정]")
    print(f"  예상 최종 조합: {estimated:,}개")
    
    # 평가
    print(f"\n[평가]")
    if estimated < 50000:
        print("  여전히 너무 적음 (목표: 20-60만개)")
    elif estimated < 200000:
        print("  약간 적음")
    elif estimated < 600000:
        print("  적절한 수준!")
    else:
        print("  너무 많음")

if __name__ == "__main__":
    test_improved_filtering()