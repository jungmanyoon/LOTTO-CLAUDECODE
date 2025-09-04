"""강화된 필터 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
import random
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_strong_filters():
    """강화된 필터로 테스트"""
    
    print("\n" + "="*60)
    print("강화된 필터 테스트")
    print("="*60)
    
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # 전체 조합 가져오기
    print("\n전체 조합 로드 중...")
    all_combinations = db_manager.combinations_db.get_base_combinations()
    total_count = len(all_combinations)
    print(f"전체 조합 수: {total_count:,}개")
    
    # 랜덤하게 섞기
    print("\n조합을 랜덤하게 섞는 중...")
    random.shuffle(all_combinations)
    
    # 샘플로 테스트 (50,000개)
    sample_size = min(50000, total_count)
    sample_combinations = all_combinations[:sample_size]
    
    print(f"\n{sample_size:,}개 샘플로 필터링 테스트")
    print("-"*60)
    
    # 필터 적용
    current = sample_combinations.copy()
    total_excluded = 0
    
    # 필터 순서 (효율적인 순서)
    filter_order = [
        'sum_range',    # 합계 범위
        'average',      # 평균값 필터
        'consecutive',  # 연속 번호
        'section',      # 구간
        'dispersion',   # 분산도
        'prime_composite',  # 소수/합성수
        'odd_even',     # 홀짝
        'fixed_step',   # 고정 간격
        'last_digit',   # 끝자리
        'match',        # 일치 번호
        'max_gap',      # 최대 간격
        'multiple',     # 배수
        'ten_section',  # 10구간
        'digit_sum',    # 자릿수 합
    ]
    
    print("\n필터별 제외율:")
    for filter_name in filter_order:
        if filter_name in filter_manager.filters:
            filter_obj = filter_manager.filters[filter_name]
            try:
                before = len(current)
                current = filter_obj.apply(current, 1186)
                after = len(current)
                excluded = before - after
                exclude_rate = excluded / before * 100 if before > 0 else 0
                total_excluded += excluded
                
                if exclude_rate > 0:
                    status = ""
                    if exclude_rate > 50:
                        status = " [강력]"
                    elif exclude_rate > 20:
                        status = " [중간]"
                    elif exclude_rate > 10:
                        status = " [약간]"
                    
                    print(f"  {filter_name:20s}: {before:6,} -> {after:6,} ({exclude_rate:5.1f}% 제외){status}")
                    
            except Exception as e:
                print(f"  {filter_name:20s}: 에러 - {str(e)[:50]}")
    
    survival_rate = len(current) / sample_size * 100
    exclude_rate = 100 - survival_rate
    
    print(f"\n" + "="*60)
    print(f"최종 결과:")
    print(f"  샘플: {sample_size:,}개")
    print(f"  최종: {len(current):,}개")
    print(f"  생존율: {survival_rate:.2f}%")
    print(f"  제외율: {exclude_rate:.2f}%")
    
    # 814만개 추정
    estimated = int(8145060 * survival_rate / 100)
    print(f"\n814만개 추정:")
    print(f"  예상 최종 조합: {estimated:,}개")
    
    # 목표 달성 여부
    print(f"\n평가:")
    if 200000 <= estimated <= 600000:
        print(f"  [성공] 목표 달성! (목표: 20-60만개)")
    elif estimated < 200000:
        print(f"  [경고] 너무 강함 (현재: {estimated:,}개)")
        print(f"         일부 필터를 약화시켜야 합니다.")
    else:
        print(f"  [경고] 아직 약함 (현재: {estimated:,}개)")
        print(f"         필터를 더 강화해야 합니다.")
    
    return estimated

if __name__ == "__main__":
    result = test_strong_filters()
    
    print("\n" + "="*60)
    print("필터 강도 분석")
    print("="*60)
    
    if result < 200000:
        print("너무 강력한 필터:")
        print("  - consecutive를 3으로 늘리기")
        print("  - section을 3으로 늘리기")
        print("  - average 범위 확대")
    elif result > 600000:
        print("추가 강화 필요:")
        print("  - digit_sum 범위 축소")
        print("  - ten_section 제한 강화")
        print("  - arithmetic_sequence 강화")