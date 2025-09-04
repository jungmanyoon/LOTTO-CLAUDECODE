#!/usr/bin/env python3
"""
필터 수정 테스트 스크립트
"""
import logging
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.logger import setup_logging

def test_filter_application():
    """필터 적용 테스트"""
    setup_logging()
    
    logging.info("\n" + "="*60)
    logging.info("필터 적용 테스트")
    logging.info("="*60)
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 조합 개수 확인
        total_count = db_manager.combinations_db.count_all_combinations()
        logging.info(f"전체 조합 개수: {total_count:,}")
        
        # 필터 매니저 초기화
        filter_manager = FilterManager(db_manager)
        
        # 필터 등록 상태 확인
        logging.info(f"\n등록된 필터 수: {len(filter_manager.filters)}")
        for name, filter_obj in filter_manager.filters.items():
            logging.info(f"  - {name}: {filter_obj.__class__.__name__}")
        
        # 간단한 필터 적용 테스트
        logging.info("\n[테스트] 10,000개 조합에 대한 필터 적용 시작...")
        
        # apply_all_filters 호출
        latest_round = db_manager.lotto_db.get_last_round()
        logging.info(f"최신 회차: {latest_round}")
        
        success = filter_manager.apply_filters(latest_round, update_mode='full', force=True)
        
        if success:
            logging.info("\n✅ 필터 적용 성공!")
        else:
            logging.error("\n❌ 필터 적용 실패!")
            
        return success
        
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_filter_application()
    sys.exit(0 if success else 1)