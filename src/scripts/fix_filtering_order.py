"""필터링 순서 문제 해결"""
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

def fix_filtering_with_random_sampling():
    """랜덤 샘플링으로 필터링 개선"""
    
    print("\n" + "="*60)
    print("랜덤 샘플링 필터링")
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
    
    # 샘플로 테스트 (100,000개)
    sample_size = min(100000, total_count)
    sample_combinations = all_combinations[:sample_size]
    
    print(f"\n{sample_size:,}개 샘플로 필터링 테스트")
    print("-"*60)
    
    # 필터 적용
    current = sample_combinations.copy()
    
    # 필터 순서 최적화 (효율적인 순서)
    filter_order = [
        'average',      # 평균값 필터 (제외율 낮음)
        'sum_range',    # 합계 범위
        'consecutive',  # 연속 번호
        'odd_even',     # 홀짝
        'match',        # 일치 번호
        'prime_composite',  # 소수/합성수
        'fixed_step',   # 고정 간격
        'last_digit',   # 끝자리
        'max_gap',      # 최대 간격
        'section',      # 구간
        'multiple',     # 배수
        'ten_section',  # 10구간
        'digit_sum',    # 자릿수 합
        'dispersion',   # 분산도
    ]
    
    for filter_name in filter_order:
        if filter_name in filter_manager.filters:
            filter_obj = filter_manager.filters[filter_name]
            try:
                before = len(current)
                current = filter_obj.apply(current, 1186)
                after = len(current)
                exclude_rate = (before - after) / before * 100 if before > 0 else 0
                
                if exclude_rate > 0:
                    print(f"  {filter_name:20s}: {before:6,} → {after:6,} ({exclude_rate:5.1f}% 제외)")
                    
                # 너무 많이 제외되면 경고
                if exclude_rate > 50:
                    print(f"    ⚠️ 과도한 제외! 파라미터 조정 필요")
                    
            except Exception as e:
                print(f"  {filter_name:20s}: 에러 - {str(e)[:50]}")
    
    survival_rate = len(current) / sample_size * 100
    print(f"\n최종 결과:")
    print(f"  샘플: {sample_size:,}개 → {len(current):,}개")
    print(f"  생존율: {survival_rate:.2f}%")
    
    # 814만개 추정
    estimated = int(8145060 * survival_rate / 100)
    print(f"\n814만개 추정:")
    print(f"  예상 최종 조합: {estimated:,}개")
    
    # 목표 달성 여부
    print(f"\n평가:")
    if 200000 <= estimated <= 600000:
        print(f"  ✅ 목표 달성! (목표: 20-60만개)")
    elif estimated < 200000:
        print(f"  ⚠️ 아직 부족 (현재: {estimated:,}개)")
    else:
        print(f"  ⚠️ 너무 많음 (현재: {estimated:,}개)")
    
    return estimated

if __name__ == "__main__":
    result = fix_filtering_with_random_sampling()
    
    if result > 1000000:
        print("\n" + "="*60)
        print("추가 조정 필요")
        print("="*60)
        print("필터를 더 강화해야 합니다:")
        print("  1. consecutive: max_consecutive를 3으로 줄이기")
        print("  2. fixed_step: 더 많은 패턴 제외")
        print("  3. section: 구간당 최대 3개로 제한")