#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개선 사항 테스트 스크립트
"""

import logging
import time
import os
import sys

# 프로젝트 루트 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

# 로깅 설정 (간단한 출력을 위해 INFO 레벨로 설정)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_filter_performance():
    """필터 성능 개선 테스트"""
    try:
        logging.info("=== 필터 성능 개선 테스트 시작 ===")
        
        # 관리자 초기화
        db_manager = DatabaseManager()
        filter_manager = FilterManager(db_manager)
        
        # 테스트용 조합 생성 (1000개 샘플)
        test_combinations = []
        for i in range(1000):
            # 임의의 조합 생성
            nums = []
            start = (i % 40) + 1
            for j in range(6):
                nums.append((start + j * 2) % 45 + 1)
            nums = sorted(set(nums))[:6]  # 중복 제거 후 6개만 선택
            if len(nums) == 6:
                test_combinations.append(','.join(map(str, nums)))
        
        logging.info(f"테스트 조합 수: {len(test_combinations)}개")
        
        # 각 필터별 성능 측정
        filter_performance = {}
        
        # dispersion 필터 테스트
        logging.info("\n--- Dispersion 필터 테스트 ---")
        if 'dispersion' in filter_manager.filters:
            start_time = time.time()
            result = filter_manager.filters['dispersion'].apply(test_combinations.copy(), 1)
            elapsed_time = time.time() - start_time
            filter_performance['dispersion'] = elapsed_time
            logging.info(f"Dispersion 필터: {elapsed_time:.2f}초 (필터링 후: {len(result)}개)")
        
        # match 필터 테스트
        logging.info("\n--- Match 필터 테스트 ---")
        if 'match' in filter_manager.filters:
            start_time = time.time()
            result = filter_manager.filters['match'].apply(test_combinations.copy(), 1)
            elapsed_time = time.time() - start_time
            filter_performance['match'] = elapsed_time
            logging.info(f"Match 필터: {elapsed_time:.2f}초 (필터링 후: {len(result)}개)")
        
        # fixed_step 필터 테스트
        logging.info("\n--- Fixed Step 필터 테스트 ---")
        if 'fixed_step' in filter_manager.filters:
            start_time = time.time()
            result = filter_manager.filters['fixed_step'].apply(test_combinations.copy(), 1)
            elapsed_time = time.time() - start_time
            filter_performance['fixed_step'] = elapsed_time
            logging.info(f"Fixed Step 필터: {elapsed_time:.2f}초 (필터링 후: {len(result)}개)")
        
        # 필터 실행 순서 확인
        logging.info("\n--- 필터 실행 순서 확인 ---")
        ordered_filters = filter_manager._get_optimized_filter_order()
        for i, (filter_name, _) in enumerate(ordered_filters):
            efficiency = filter_manager.filter_efficiency.get(filter_name, 0)
            logging.info(f"{i+1}. {filter_name} (효율성: {efficiency:.2f})")
        
        # 성능 요약
        logging.info("\n=== 성능 개선 결과 요약 ===")
        for filter_name, elapsed_time in filter_performance.items():
            logging.info(f"{filter_name}: {elapsed_time:.4f}초")
        
        logging.info("\n테스트 완료!")
        
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

def test_database_schema():
    """데이터베이스 스키마 확인"""
    try:
        logging.info("\n=== 데이터베이스 스키마 확인 ===")
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # filter_stats 테이블 스키마 확인
        filter_db = db_manager.get_filter_db('match')
        if filter_db:
            # DB 연결 확인
            if hasattr(filter_db, 'conn') and filter_db.conn:
                cursor = filter_db.conn.cursor()
            else:
                logging.error("데이터베이스 연결 실패")
                return
            
            # 테이블 정보 조회
            cursor.execute("PRAGMA table_info(filter_stats)")
            columns = cursor.fetchall()
            
            logging.info("\nfilter_stats 테이블 컬럼:")
            for col in columns:
                logging.info(f"  - {col[1]}: {col[2]}")
        
        logging.info("\n스키마 확인 완료!")
        
    except Exception as e:
        logging.error(f"스키마 확인 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    # 성능 테스트 실행
    test_filter_performance()
    
    # 데이터베이스 스키마 확인
    test_database_schema()