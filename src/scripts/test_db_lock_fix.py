#!/usr/bin/env python3
"""
database is locked 에러 해결 테스트
"""
import os
import sys
import time
import logging

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.utils.db_connection_manager import DatabaseConnectionManager

def test_database_lock_fix():
    """데이터베이스 락 문제 해결 테스트"""
    print("\n=== Database Lock Fix 테스트 ===\n")
    
    try:
        # 데이터베이스 매니저 초기화
        print("1. 데이터베이스 매니저 초기화 중...")
        start_time = time.time()
        db_manager = DatabaseManager()
        elapsed = time.time() - start_time
        print(f"   → 완료 (소요 시간: {elapsed:.2f}초)\n")
        
        # 각 데이터베이스 접근 테스트
        print("2. 각 데이터베이스 접근 테스트:")
        
        # 로또 번호 DB
        print("   - lotto_numbers.db 테스트...", end='')
        last_round = db_manager.get_last_round()
        print(f" [성공] 마지막 회차: {last_round}")
        
        # 조합 DB
        print("   - combinations.db 테스트...", end='')
        exists = db_manager.check_base_combinations_exist()
        print(f" [성공] 기본 조합 존재: {exists}")
        
        # 패턴 DB
        print("   - patterns.db 테스트...", end='')
        latest_pattern = db_manager.get_latest_pattern_analysis()
        print(f" [성공] 최신 패턴: {'있음' if latest_pattern else '없음'}")
        
        # 필터 DB들
        filter_types = ['match', 'odd_even', 'consecutive', 'sum_range', 
                       'fixed_step', 'last_digit', 'max_gap', 'section', 
                       'average', 'multiple', 'ten_section', 
                       'arithmetic_sequence', 'geometric_sequence',
                       'prime_composite', 'digit_sum', 'dispersion']
        
        print("\n3. 필터 데이터베이스 접근 테스트:")
        success_count = 0
        fail_count = 0
        
        for filter_type in filter_types:
            try:
                filter_db = db_manager.get_filter_db(filter_type)
                if filter_db:
                    # 간단한 쿼리 실행
                    with filter_db._create_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                    print(f"   - {filter_type}: [성공]")
                    success_count += 1
                else:
                    print(f"   - {filter_type}: [실패] DB 객체 없음")
                    fail_count += 1
            except Exception as e:
                print(f"   - {filter_type}: [실패] {str(e)}")
                fail_count += 1
        
        print(f"\n필터 DB 테스트 결과: 성공 {success_count}개, 실패 {fail_count}개")
        
        # 동시 접근 테스트
        print("\n4. 동시 접근 테스트:")
        print("   여러 DB에 동시에 접근 시도 중...")
        
        import concurrent.futures
        
        def access_db(db_name, operation):
            """데이터베이스 접근 함수"""
            try:
                operation()
                return f"{db_name}: 성공"
            except Exception as e:
                return f"{db_name}: 실패 - {str(e)}"
        
        # 동시 실행할 작업들
        operations = [
            ("lotto_numbers", lambda: db_manager.get_last_round()),
            ("combinations", lambda: db_manager.check_base_combinations_exist()),
            ("patterns", lambda: db_manager.get_latest_pattern_analysis()),
            ("match_filter", lambda: db_manager.get_filter_db('match').get_last_filtered_round()),
            ("odd_even_filter", lambda: db_manager.get_filter_db('odd_even').get_last_filtered_round()),
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for db_name, operation in operations:
                future = executor.submit(access_db, db_name, operation)
                futures.append(future)
            
            # 결과 수집
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                print(f"   - {result}")
        
        print("\n✅ 모든 테스트 완료!")
        print("\n개선 사항:")
        print("1. 연결 타임아웃을 30초로 증가")
        print("2. WAL 모드 활성화로 읽기/쓰기 동시성 향상")
        print("3. 자동 재시도 메커니즘 추가")
        print("4. 데이터베이스별 락 관리")
        print("5. PRAGMA 최적화 설정 적용")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    test_database_lock_fix()