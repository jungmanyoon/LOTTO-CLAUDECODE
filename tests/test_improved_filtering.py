#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개선된 필터링 시스템 테스트
"""

import logging
import os
import sys
import time

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

def test_improved_filtering():
    """개선된 필터링 시스템 테스트"""
    try:
        logging.info("\n" + "="*60)
        logging.info("개선된 필터링 시스템 테스트 시작")
        logging.info("="*60 + "\n")
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 최신 회차 확인
        latest_round = db_manager.get_last_round()
        logging.info(f"테스트 회차: {latest_round}")
        
        # 필터 매니저 초기화
        filter_manager = FilterManager(db_manager)
        
        # 이전 필터링 상태 확인
        logging.info("\n=== 이전 필터링 상태 확인 ===")
        last_filtered_round = filter_manager.get_last_filtered_round()
        if last_filtered_round:
            logging.info(f"마지막 필터링 회차: {last_filtered_round}")
        else:
            logging.info("이전 필터링 기록 없음")
        
        # 필터링 실행
        logging.info("\n=== 필터링 실행 시작 ===")
        start_time = time.time()
        
        # 강제로 전체 필터링 실행 (테스트 목적)
        success = filter_manager.apply_filters(
            latest_round, 
            update_mode='full', 
            force=True
        )
        
        end_time = time.time()
        
        # 결과 확인
        if success:
            logging.info("\n✅ 필터링 성공!")
            logging.info(f"총 소요 시간: {end_time - start_time:.2f}초")
            
            # 최종 조합 확인
            final_combinations = db_manager.combinations_db.get_filtered_combinations(latest_round)
            if final_combinations:
                logging.info(f"최종 필터링된 조합 수: {len(final_combinations):,}개")
                
                # 샘플 조합 표시
                logging.info("\n=== 샘플 조합 (처음 5개) ===")
                for i, comb in enumerate(final_combinations[:5], 1):
                    logging.info(f"{i}. {comb}")
            else:
                logging.error("최종 필터링된 조합을 가져올 수 없습니다.")
        else:
            logging.error("\n❌ 필터링 실패!")
            
        # 각 필터별 통계 확인
        logging.info("\n=== 필터별 통계 확인 ===")
        filter_names = filter_manager.get_registered_filters()
        
        for filter_name in filter_names:
            filter_db = db_manager.get_filter_db(filter_name)
            if filter_db:
                stats = filter_db.get_filtering_statistics(latest_round)
                if stats and stats['excluded_combinations'] > 0:
                    logging.info(f"{filter_name}: {stats['excluded_combinations']:,}개 제외 ({stats['exclude_percent']:.2f}%)")
                    
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    test_improved_filtering()