#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
필터링 통계 시스템 빠른 테스트
"""

import logging
import os
import sys

# 프로젝트 루트 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # tests 폴더의 상위 디렉토리
sys.path.insert(0, project_root)

from src.core.db_manager import DatabaseManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_filter_statistics():
    """필터링 통계 빠른 테스트"""
    try:
        logging.info("필터링 통계 빠른 테스트 시작")
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 최신 회차 확인
        latest_round = db_manager.get_last_round()
        logging.info(f"최신 회차: {latest_round}")
        
        # 각 필터별 통계 확인 (새로운 get_filtering_statistics 메서드 테스트)
        logging.info("\n=== 각 필터별 통계 확인 ===")
        
        filter_names = ['match', 'odd_even', 'consecutive', 'sum_range', 'fixed_step', 
                       'last_digit', 'max_gap', 'section', 'average', 'multiple', 
                       'ten_section', 'arithmetic_sequence', 'geometric_sequence', 
                       'prime_composite', 'digit_sum', 'dispersion']
        
        total_stats = {}
        
        for filter_name in filter_names:
            filter_db = db_manager.get_filter_db(filter_name)
            if filter_db:
                # get_filtering_statistics 호출
                if hasattr(filter_db, 'get_filtering_statistics'):
                    stats = filter_db.get_filtering_statistics(latest_round)
                    if stats:
                        total = stats.get('total_combinations', 0)
                        excluded = stats.get('excluded_combinations', 0)
                        percent = stats.get('exclude_percent', 0)
                        time = stats.get('filter_time', 0)
                        
                        total_stats[filter_name] = {
                            'total': total,
                            'excluded': excluded,
                            'percent': percent,
                            'time': time
                        }
                        
                        logging.info(f"{filter_name}: 입력 {total:,}개, 제외 {excluded:,}개 ({percent:.2f}%), 시간 {time:.2f}초")
                    else:
                        logging.info(f"{filter_name}: 통계 없음")
                        
                # filter_details 직접 확인
                details = filter_db.get_filter_details(latest_round)
                if details and isinstance(details, dict):
                    initial = details.get('initial_count', 0)
                    excluded = details.get('excluded_count', 0)
                    percent = details.get('exclude_percent', 0)
                    
                    logging.info(f"  -> filter_details: 입력 {initial:,}개, 제외 {excluded:,}개 ({percent:.2f}%)")
        
        # 전체 필터링 프로세스 요약
        logging.info("\n=== 필터링 프로세스 요약 ===")
        
        # 초기 조합 수
        initial_combinations = len(db_manager.combinations_db.get_base_combinations())
        logging.info(f"초기 조합 수: {initial_combinations:,}개")
        
        # 필터별 제외 수 합계 (중복 포함)
        total_excluded_sum = sum(stat['excluded'] for stat in total_stats.values())
        logging.info(f"필터별 제외 수 합계 (중복 포함): {total_excluded_sum:,}개")
        
        # 최종 남은 조합 수
        final_combinations = db_manager.combinations_db.get_filtered_combinations(latest_round)
        if final_combinations:
            final_count = len(final_combinations)
            actual_excluded = initial_combinations - final_count
            actual_percent = (actual_excluded / initial_combinations * 100) if initial_combinations > 0 else 0
            
            logging.info(f"최종 남은 조합: {final_count:,}개")
            logging.info(f"실제 제외된 조합: {actual_excluded:,}개 ({actual_percent:.2f}%)")
        else:
            logging.info("최종 필터링된 조합이 없습니다.")
            
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    test_filter_statistics()