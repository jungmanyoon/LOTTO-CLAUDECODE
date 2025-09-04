"""필터링 과정 상세 추적"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
import logging

# 로깅 레벨 상세하게 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def trace_filtering():
    """필터링 과정 추적"""
    
    print("\n" + "="*60)
    print("필터링 과정 상세 추적")
    print("="*60)
    
    # DB 매니저 초기화
    db_manager = DatabaseManager()
    
    # FilterManager 초기화
    filter_manager = FilterManager(db_manager)
    
    # 전체 조합 10개만 샘플로 테스트
    sample_combinations = [
        "1,2,3,4,5,6",      # 연속 번호 (제외될 것)
        "1,2,3,4,5,45",     # 일부 연속
        "1,10,20,30,40,45", # 분산된 번호
        "5,10,15,20,25,30", # 5의 배수
        "2,4,8,16,32,40",   # 기하수열
        "7,14,21,28,35,42", # 7의 배수
        "1,3,5,7,9,11",     # 모두 홀수 (제외될 것)
        "2,4,6,8,10,12",    # 모두 짝수 (제외될 것)
        "10,15,20,25,30,35",# 산술수열
        "3,11,19,27,35,43", # 8씩 증가
    ]
    
    print(f"\n테스트 조합 {len(sample_combinations)}개:")
    for i, comb in enumerate(sample_combinations, 1):
        print(f"  {i:2d}. {comb}")
    
    # 각 필터별로 개별 테스트
    filters_to_test = [
        'average', 'sum_range', 'consecutive', 'odd_even', 
        'prime_composite', 'fixed_step', 'match'
    ]
    
    print("\n" + "="*60)
    print("필터별 개별 테스트")
    print("="*60)
    
    for filter_name in filters_to_test:
        if filter_name not in filter_manager.filters:
            print(f"\n{filter_name} 필터: 활성화되지 않음")
            continue
            
        filter_obj = filter_manager.filters[filter_name]
        
        print(f"\n{filter_name} 필터 테스트:")
        print(f"  설정: {filter_obj.criteria}")
        
        # 필터 적용
        try:
            remaining = filter_obj.apply(sample_combinations.copy(), 1185)
            excluded = len(sample_combinations) - len(remaining)
            
            print(f"  결과: {excluded}개 제외 ({excluded/len(sample_combinations)*100:.1f}%)")
            
            # 제외된 조합 표시
            excluded_combs = set(sample_combinations) - set(remaining)
            if excluded_combs:
                print(f"  제외된 조합:")
                for comb in excluded_combs:
                    idx = sample_combinations.index(comb) + 1
                    print(f"    #{idx}: {comb}")
        except Exception as e:
            print(f"  에러: {str(e)}")
    
    # 전체 필터 순차 적용
    print("\n" + "="*60)
    print("전체 필터 순차 적용")
    print("="*60)
    
    current_combinations = sample_combinations.copy()
    print(f"시작: {len(current_combinations)}개")
    
    for filter_name in filter_manager.filters.keys():
        filter_obj = filter_manager.filters[filter_name]
        before_count = len(current_combinations)
        
        try:
            current_combinations = filter_obj.apply(current_combinations, 1185)
            after_count = len(current_combinations)
            excluded = before_count - after_count
            
            if excluded > 0:
                print(f"{filter_name:20s}: {before_count}개 → {after_count}개 ({excluded}개 제외)")
        except Exception as e:
            print(f"{filter_name:20s}: 에러 - {str(e)}")
    
    print(f"\n최종: {len(current_combinations)}개 남음")
    if current_combinations:
        print("남은 조합:")
        for comb in current_combinations:
            idx = sample_combinations.index(comb) + 1
            print(f"  #{idx}: {comb}")

if __name__ == "__main__":
    trace_filtering()