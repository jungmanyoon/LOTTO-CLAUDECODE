#!/usr/bin/env python3
"""
간단한 필터 테스트 - 데이터베이스 없이 직접 테스트
"""
import logging
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import setup_logging
from src.filters.sum_range_filter import SumRangeFilter
from src.filters.odd_even_filter import OddEvenFilter
from src.filters.consecutive_filter import ConsecutiveFilter

def test_filters_directly():
    """필터를 직접 테스트"""
    setup_logging()
    
    logging.info("\n" + "="*60)
    logging.info("필터 직접 테스트 (데이터베이스 없이)")
    logging.info("="*60)
    
    # 테스트용 조합 생성 (다양한 특성을 가진 조합들)
    test_combinations = [
        # 합계가 작은 조합들
        "1,2,3,4,5,6",      # 합: 21
        "1,2,3,4,5,7",      # 합: 22
        "1,2,3,4,5,8",      # 합: 23
        # 합계가 중간인 조합들
        "10,15,20,25,30,35", # 합: 135
        "5,10,15,20,25,30",  # 합: 105
        # 합계가 큰 조합들
        "40,41,42,43,44,45", # 합: 255
        "35,36,37,38,39,40", # 합: 225
        # 연속 번호가 많은 조합들
        "1,2,3,4,5,10",      # 5개 연속
        "20,21,22,23,24,25", # 6개 연속
        "10,11,12,20,21,22", # 3개씩 연속
        # 홀수가 많은 조합들
        "1,3,5,7,9,11",      # 홀수 6개
        "1,3,5,7,9,10",      # 홀수 5개
        # 짝수가 많은 조합들
        "2,4,6,8,10,12",     # 짝수 6개
        "2,4,6,8,10,11",     # 짝수 5개
        # 일반적인 조합들
        "7,14,21,28,35,42",  # 7의 배수
        "5,10,15,20,25,30",  # 5의 배수
        "1,6,11,16,21,26",   # 5씩 차이
        "2,9,16,23,30,37",   # 7씩 차이
        "3,10,17,24,31,38",  # 7씩 차이
        "4,11,18,25,32,39",  # 7씩 차이
    ]
    
    logging.info(f"테스트 조합 생성: {len(test_combinations)}개")
    
    # 조합들의 특성 출력
    for i, combo in enumerate(test_combinations[:5]):
        nums = [int(n) for n in combo.split(',')]
        total_sum = sum(nums)
        odd_count = sum(1 for n in nums if n % 2 == 1)
        even_count = 6 - odd_count
        consecutive_groups = []
        
        # 연속 번호 확인
        for j in range(len(nums)-1):
            if nums[j+1] - nums[j] == 1:
                if not consecutive_groups or nums[j] != consecutive_groups[-1][-1] + 1:
                    consecutive_groups.append([nums[j]])
                consecutive_groups[-1].append(nums[j+1])
        
        max_consecutive = max(len(g) for g in consecutive_groups) if consecutive_groups else 0
        
        logging.info(f"  조합 {i+1}: {combo}")
        logging.info(f"    - 합계: {total_sum}, 홀수: {odd_count}개, 짝수: {even_count}개, 최대 연속: {max_consecutive}개")
    
    logging.info(f"테스트 조합 생성: {len(test_combinations)}개")
    logging.info(f"샘플 조합: {test_combinations[:3]}")
    
    # 각 필터 테스트
    filters_to_test = [
        ("합계 범위 필터", SumRangeFilter, {"min_sum": 100, "max_sum": 180}),
        ("홀짝 필터", OddEvenFilter, {"odd": [2, 3, 4], "even": [2, 3, 4]}),
        ("연속 번호 필터", ConsecutiveFilter, {"max_consecutive": 2})
    ]
    
    for filter_name, filter_class, criteria in filters_to_test:
        logging.info(f"\n[{filter_name} 테스트]")
        logging.info(f"기준: {criteria}")
        
        # 필터 생성 (db_manager 없이)
        filter_obj = filter_class(None, criteria)
        
        # 필터 적용
        filtered = filter_obj.apply(test_combinations.copy(), 1182)
        
        excluded_count = len(test_combinations) - len(filtered)
        exclusion_rate = (excluded_count / len(test_combinations)) * 100
        
        logging.info(f"결과: {len(filtered)}/{len(test_combinations)}개 통과")
        logging.info(f"제외율: {exclusion_rate:.1f}% ({excluded_count}개 제외)")
        
        if excluded_count > 0:
            logging.info("✅ 필터가 정상적으로 작동합니다!")
        else:
            logging.warning("⚠️ 필터가 아무것도 제외하지 않았습니다.")
    
    logging.info("\n" + "="*60)
    logging.info("테스트 완료")
    logging.info("="*60)

if __name__ == "__main__":
    test_filters_directly()