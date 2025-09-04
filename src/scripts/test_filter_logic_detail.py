"""필터링 로직 상세 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

def test_filter_logic():
    """필터링 로직 테스트"""
    
    print("\n" + "="*60)
    print("필터링 로직 상세 테스트")
    print("="*60)
    
    # DB 매니저와 필터 매니저 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # 테스트 조합 (100개)
    test_combinations = []
    for i in range(100):
        # 다양한 패턴의 조합 생성
        if i < 20:
            # 정상적인 조합
            nums = [1+i, 10+i, 20+i, 30+i, 35+i, 40+i]
        elif i < 40:
            # 연속 번호 포함
            nums = [1+i, 2+i, 3+i, 20+i, 30+i, 40+i]
        elif i < 60:
            # 홀수/짝수 편향
            nums = [1+i*2, 3+i*2, 5+i*2, 7+i*2, 9+i*2, 11+i*2] if i % 2 == 0 else [2+i*2, 4+i*2, 6+i*2, 8+i*2, 10+i*2, 12+i*2]
        else:
            # 기타 패턴
            nums = [5+i, 10+i, 15+i, 20+i, 25+i, 30+i]
        
        # 범위 확인 (1-45)
        nums = [min(45, max(1, n)) for n in nums]
        nums = sorted(list(set(nums)))[:6]  # 중복 제거, 정렬, 6개만
        
        if len(nums) == 6:
            combo_str = ','.join(map(str, nums))
            test_combinations.append(combo_str)
    
    print(f"\n테스트 조합 수: {len(test_combinations)}개")
    
    # 각 필터 개별 적용
    print("\n각 필터별 제외 수:")
    print("-"*50)
    
    filter_results = {}
    
    for filter_name, filter_obj in filter_manager.filters.items():
        try:
            # 각 필터를 원본 조합에 개별 적용
            remaining = filter_obj.apply(test_combinations.copy(), 1185)
            excluded = len(test_combinations) - len(remaining)
            filter_results[filter_name] = {
                'excluded': excluded,
                'remaining': len(remaining),
                'rate': excluded / len(test_combinations) * 100
            }
            print(f"{filter_name:20s}: {excluded:3d}개 제외 ({excluded/len(test_combinations)*100:5.1f}%)")
        except Exception as e:
            print(f"{filter_name:20s}: 에러 - {str(e)}")
    
    # 순차 적용 시뮬레이션
    print("\n순차 적용 시뮬레이션:")
    print("-"*50)
    
    current = test_combinations.copy()
    print(f"시작: {len(current)}개")
    
    for filter_name, filter_obj in filter_manager.filters.items():
        try:
            before = len(current)
            current = filter_obj.apply(current, 1185)
            after = len(current)
            
            if before != after:
                print(f"{filter_name:20s}: {before:3d} → {after:3d} ({before-after:3d}개 제외)")
        except Exception as e:
            print(f"{filter_name:20s}: 에러")
    
    print(f"\n최종: {len(current)}개 남음 (생존율 {len(current)/len(test_combinations)*100:.1f}%)")
    
    # 문제 진단
    print("\n" + "="*60)
    print("문제 진단:")
    print("="*60)
    
    if len(current) < len(test_combinations) * 0.1:
        print("⚠ 과도한 필터링 발생!")
        print("  원인: 필터가 순차적으로 적용되어 조합이 급격히 감소")
        print("\n해결 방안:")
        print("  1. 필터 파라미터 완화")
        print("  2. 필터 적용 방식 변경 (AND → OR)")
        print("  3. 중요 필터만 선택적 적용")
    else:
        print("✓ 필터링 수준 적절")

if __name__ == "__main__":
    test_filter_logic()