#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
필터링 통계 시스템 테스트
"""

import logging
import os
import sys

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_filtering_statistics():
    """필터링 통계 테스트"""
    try:
        logging.info("필터링 통계 테스트 시작")
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 최신 회차 확인
        latest_round = db_manager.get_last_round()
        logging.info(f"최신 회차: {latest_round}")
        
        # 필터 매니저 초기화
        filter_manager = FilterManager(db_manager)
        
        # 필터링 실행 전 통계 표시
        logging.info("\n=== 필터링 실행 전 통계 (이전 실행 결과) ===")
        for filter_name in filter_manager.filters.keys():
            filter_db = db_manager.get_filter_db(filter_name)
            if filter_db and hasattr(filter_db, 'get_filtering_statistics'):
                stats = filter_db.get_filtering_statistics(latest_round)
                if stats:
                    excluded = stats.get('excluded_combinations', 0)
                    percent = stats.get('exclude_percent', 0)
                    logging.info(f"{filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")
        
        # 필터링 실행 (강제로 새로 실행)
        logging.info("\n=== 필터링 실행 중 ===")
        success = filter_manager.apply_filters(latest_round, update_mode='full', force=True)
        
        if success:
            logging.info("\n필터링 성공!")
        else:
            logging.error("\n필터링 실패!")
            
        # 필터링 실행 후 통계는 apply_filters 메서드 내에서 자동으로 표시됨
        
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    test_filtering_statistics()