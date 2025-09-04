"""최종 문제 진단"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import random
from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

def final_diagnosis():
    """최종 문제 진단"""
    
    print("\n" + "="*60)
    print("최종 문제 진단")
    print("="*60)
    
    # DB 매니저와 필터 매니저 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # 1000개 랜덤 조합 생성
    sample_size = 1000
    test_combinations = []
    
    print(f"\n{sample_size}개 랜덤 조합 생성 중...")
    for _ in range(sample_size):
        numbers = sorted(random.sample(range(1, 46), 6))
        combo_str = ','.join(map(str, numbers))
        test_combinations.append(combo_str)
    
    # 순차 적용 시뮬레이션
    print("\n순차 필터 적용 시뮬레이션:")
    print("-"*60)
    
    current = test_combinations.copy()
    print(f"시작: {len(current):,}개")
    
    critical_filters = []
    
    for filter_name in filter_manager.filters.keys():
        filter_obj = filter_manager.filters[filter_name]
        
        try:
            before = len(current)
            current = filter_obj.apply(current, 1185)
            after = len(current)
            excluded = before - after
            
            if excluded > 0:
                exclude_rate = excluded / before * 100
                print(f"{filter_name:20s}: {before:5,} → {after:5,} ({exclude_rate:5.1f}% 제외)")
                
                # 50% 이상 제외하는 필터는 문제
                if exclude_rate > 50:
                    critical_filters.append((filter_name, exclude_rate))
                    print(f"                      ^^^ 과도한 제외! ^^^")
        except Exception as e:
            print(f"{filter_name:20s}: 에러 - {str(e)[:30]}")
    
    final_rate = len(current) / sample_size * 100
    print(f"\n최종: {len(current):,}개 ({final_rate:.2f}% 생존)")
    
    # 진단 결과
    print("\n" + "="*60)
    print("진단 결과:")
    print("="*60)
    
    if final_rate < 10:
        print("\n[문제] 과도한 필터링!")
        print(f"  - {sample_size}개 → {len(current)}개 (생존율 {final_rate:.2f}%)")
        
        if critical_filters:
            print(f"\n[주범 필터] 50% 이상 제외하는 필터:")
            for filter_name, rate in critical_filters:
                print(f"  - {filter_name}: {rate:.1f}% 제외")
        
        print("\n[해결 방안]")
        print("  1. 위 필터들의 파라미터 완화")
        print("  2. 또는 해당 필터 비활성화")
        print("  3. 필터 적용 순서 변경 (약한 필터 먼저)")
    else:
        print(f"\n[정상] 적절한 필터링 수준")
        print(f"  - 생존율: {final_rate:.2f}%")
    
    # 814만개 추정
    estimated_final = int(8145060 * final_rate / 100)
    print(f"\n[814만개 추정]")
    print(f"  - 예상 최종 조합: {estimated_final:,}개")
    
    if estimated_final < 100000:
        print("  - 경고: 너무 적음! 목표는 20-60만개")
    elif estimated_final < 200000:
        print("  - 주의: 약간 적음")
    elif estimated_final < 600000:
        print("  - 양호: 적절한 수준")
    else:
        print("  - 주의: 너무 많음")

if __name__ == "__main__":
    final_diagnosis()