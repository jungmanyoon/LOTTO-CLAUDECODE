#!/usr/bin/env python3
"""간단한 Match 필터 테스트"""

import os
import sys

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager

def test_winning_numbers_before():
    """get_winning_numbers_before 메서드 테스트"""
    
    print("=" * 60)
    print("get_winning_numbers_before 메서드 테스트")
    print("=" * 60)
    
    db_manager = DatabaseManager()
    
    # 마지막 회차 확인
    last_round = db_manager.get_last_round()
    print(f"마지막 회차: {last_round}")
    
    # 전체 당첨번호
    all_numbers = db_manager.get_all_winning_numbers()
    print(f"\n전체 당첨번호 개수: {len(all_numbers)}")
    
    # 테스트 케이스들
    test_rounds = [100, 500, 1000, 1100, last_round]
    
    for round_num in test_rounds:
        if round_num > last_round:
            continue
            
        # 해당 회차 이전 당첨번호
        before_numbers = db_manager.get_winning_numbers_before(round_num)
        print(f"\n{round_num}회차 이전 당첨번호 개수: {len(before_numbers)}")
        print(f"예상 개수: {round_num - 1}")
        print(f"일치 여부: {'✓' if len(before_numbers) == round_num - 1 else '✗'}")
        
        # 해당 회차의 당첨번호가 포함되어 있는지 확인
        round_data = db_manager.get_numbers_by_round(round_num)
        if round_data:
            current_numbers = round_data[1]
            is_included = current_numbers in before_numbers
            print(f"{round_num}회차 당첨번호({current_numbers}) 포함 여부: {'포함됨 (오류!)' if is_included else '포함 안됨 (정상)'}")

def test_match_filter_simple():
    """Match 필터 간단 테스트"""
    
    print("\n" + "=" * 60)
    print("Match 필터 간단 테스트")
    print("=" * 60)
    
    from src.filters.match_filter import MatchFilter
    from src.utils.config_manager import ConfigManager
    
    db_manager = DatabaseManager()
    config_manager = ConfigManager()
    
    # Match 필터 설정
    match_criteria = config_manager.get_filter_criteria('match')
    print(f"\nMatch 필터 설정: max_match = {match_criteria['max_match']}")
    
    # Match 필터 초기화
    match_filter = MatchFilter(db_manager, match_criteria)
    
    # 특정 회차 테스트 (예: 1000회차)
    test_round = 1000
    round_data = db_manager.get_numbers_by_round(test_round)
    
    if round_data:
        winning_combination = round_data[1]
        print(f"\n{test_round}회차 당첨번호: {winning_combination}")
        
        # 테스트 조합 (당첨번호 포함)
        test_combinations = [winning_combination]
        
        # 필터 적용 - 로깅 비활성화를 위해 직접 호출
        import logging
        logging.disable(logging.CRITICAL)  # 로깅 비활성화
        
        filtered = match_filter.apply_filter(test_combinations, test_round)
        
        logging.disable(logging.NOTSET)  # 로깅 재활성화
        
        print(f"필터 통과 여부: {'통과 (정상)' if winning_combination in filtered else '제외됨 (오류!)'}")
        
        # 이전 회차들과의 일치도 확인
        winning_numbers = match_filter.db_manager.get_winning_numbers_before(test_round)
        print(f"\n{test_round}회차 이전 당첨번호 개수: {len(winning_numbers)}")
        
        # 실제로 몇 개가 일치하는지 확인
        winning_set = set(map(int, winning_combination.split(',')))
        match_counts = []
        
        for prev_nums in winning_numbers[:10]:  # 최근 10개만 확인
            prev_set = set(map(int, prev_nums.split(',')))
            match_count = len(winning_set & prev_set)
            if match_count >= 4:  # 4개 이상 일치하는 경우만 표시
                match_counts.append((prev_nums, match_count))
        
        if match_counts:
            print("\n이전 당첨번호와의 일치도 (4개 이상):")
            for nums, count in match_counts:
                print(f"  {nums} -> {count}개 일치")
        else:
            print("\n이전 당첨번호와 4개 이상 일치하는 경우가 없음")

if __name__ == "__main__":
    # 메서드 테스트
    test_winning_numbers_before()
    
    # Match 필터 테스트
    test_match_filter_simple()