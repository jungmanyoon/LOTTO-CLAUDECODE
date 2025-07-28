#!/usr/bin/env python3
"""개선된 Match 필터 테스트 스크립트"""

import os
import sys
import logging
from typing import List, Dict, Any

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager
from src.filters.match_filter import MatchFilter
from src.utils.config_manager import ConfigManager

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('test_match_filter.log')
        ]
    )

def test_match_filter_with_timeseries():
    """시계열을 고려한 Match 필터 테스트"""
    
    setup_logging()
    logging.info("=" * 60)
    logging.info("개선된 Match 필터 테스트 시작")
    logging.info("=" * 60)
    
    # 데이터베이스 매니저 초기화
    db_manager = DatabaseManager()
    
    # 설정 로드
    config_manager = ConfigManager()
    match_criteria = config_manager.get_filter_criteria('match')
    logging.info(f"Match 필터 설정: max_match = {match_criteria['max_match']}")
    
    # Match 필터 초기화
    match_filter = MatchFilter(db_manager, match_criteria)
    
    # 테스트할 회차 범위 설정 (최근 10개 회차)
    last_round = db_manager.get_last_round()
    test_rounds = range(max(1, last_round - 9), last_round + 1)
    
    results = []
    
    for round_num in test_rounds:
        logging.info(f"\n--- {round_num}회차 테스트 ---")
        
        # 해당 회차의 당첨번호 가져오기
        round_data = db_manager.get_numbers_by_round(round_num)
        if not round_data:
            logging.warning(f"{round_num}회차 데이터가 없습니다.")
            continue
            
        winning_combination = round_data[1]  # 당첨번호 문자열
        logging.info(f"당첨번호: {winning_combination}")
        
        # 테스트 조합 생성 (당첨번호 포함)
        test_combinations = [
            winning_combination,  # 실제 당첨번호
            "1,2,3,4,5,6",       # 테스트 조합 1
            "7,14,21,28,35,42",  # 테스트 조합 2
            "10,20,30,40,41,42", # 테스트 조합 3
        ]
        
        # 필터 적용
        filtered = match_filter.apply_filter(test_combinations, round_num)
        
        # 결과 분석
        winning_passed = winning_combination in filtered
        pass_rate = len(filtered) / len(test_combinations) * 100
        
        result = {
            'round': round_num,
            'winning_combination': winning_combination,
            'total_tested': len(test_combinations),
            'passed': len(filtered),
            'pass_rate': pass_rate,
            'winning_passed': winning_passed
        }
        results.append(result)
        
        logging.info(f"테스트 조합 수: {len(test_combinations)}")
        logging.info(f"통과한 조합 수: {len(filtered)}")
        logging.info(f"통과율: {pass_rate:.2f}%")
        logging.info(f"당첨번호 통과 여부: {'통과' if winning_passed else '제외됨'}")
    
    # 전체 결과 요약
    logging.info("\n" + "=" * 60)
    logging.info("전체 테스트 결과 요약")
    logging.info("=" * 60)
    
    total_tested = sum(r['total_tested'] for r in results)
    total_passed = sum(r['passed'] for r in results)
    winning_passed_count = sum(1 for r in results if r['winning_passed'])
    
    logging.info(f"테스트한 회차 수: {len(results)}")
    logging.info(f"전체 테스트 조합 수: {total_tested}")
    logging.info(f"전체 통과 조합 수: {total_passed}")
    logging.info(f"전체 통과율: {total_passed/total_tested*100:.2f}%")
    logging.info(f"당첨번호 통과율: {winning_passed_count/len(results)*100:.2f}% ({winning_passed_count}/{len(results)})")
    
    # 문제가 있는 회차 확인
    problem_rounds = [r for r in results if not r['winning_passed']]
    if problem_rounds:
        logging.warning(f"\n당첨번호가 제외된 회차: {[r['round'] for r in problem_rounds]}")
    else:
        logging.info("\n모든 회차에서 당첨번호가 정상적으로 통과했습니다!")
    
    return results

def test_before_method():
    """get_winning_numbers_before 메서드 테스트"""
    
    logging.info("\n" + "=" * 60)
    logging.info("get_winning_numbers_before 메서드 테스트")
    logging.info("=" * 60)
    
    db_manager = DatabaseManager()
    
    # 특정 회차 테스트
    test_round = 1000
    
    # 전체 당첨번호
    all_numbers = db_manager.get_all_winning_numbers()
    logging.info(f"전체 당첨번호 개수: {len(all_numbers)}")
    
    # 특정 회차 이전 당첨번호
    before_numbers = db_manager.get_winning_numbers_before(test_round)
    logging.info(f"{test_round}회차 이전 당첨번호 개수: {len(before_numbers)}")
    
    # 차이 확인
    difference = len(all_numbers) - len(before_numbers)
    logging.info(f"차이: {difference}개")
    
    # 실제 회차 수와 비교
    last_round = db_manager.get_last_round()
    expected_difference = last_round - test_round + 1
    logging.info(f"예상 차이: {expected_difference}개 (마지막 회차: {last_round})")

if __name__ == "__main__":
    # get_winning_numbers_before 메서드 테스트
    test_before_method()
    
    # Match 필터 테스트
    test_match_filter_with_timeseries()