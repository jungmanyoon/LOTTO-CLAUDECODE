#!/usr/bin/env python3
"""
데이터베이스 락 문제 해결 스크립트
WAL 모드 활성화 및 최적화
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import logging
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def optimize_database(db_path):
    """데이터베이스 최적화"""
    print(f"\nOptimizing {db_path}...")
    
    try:
        # 직접 연결 (timeout 증가)
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()
        
        # WAL 모드 활성화
        cursor.execute("PRAGMA journal_mode=WAL")
        print(f"  Journal mode: {cursor.fetchone()[0]}")
        
        # 동시성 향상 설정
        cursor.execute("PRAGMA busy_timeout=60000")  # 60초
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA locking_mode=NORMAL")
        
        # WAL 체크포인트 실행
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print("  WAL checkpoint executed")
        
        # 데이터베이스 분석
        cursor.execute("ANALYZE")
        print("  Database analyzed")
        
        # db_meta 테이블이 없으면 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS db_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # storage_mode 설정
        cursor.execute("""
            INSERT OR REPLACE INTO db_meta (key, value)
            VALUES ('storage_mode', 'optimized')
        """)
        
        conn.commit()
        conn.close()
        
        print(f"  [OK] {os.path.basename(db_path)} optimized")
        return True
        
    except Exception as e:
        print(f"  [ERROR] Failed to optimize {db_path}: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("Database Lock Issue Fix")
    print("="*70)
    
    # 모든 데이터베이스 파일 찾기
    db_files = []
    
    # 메인 데이터베이스
    main_dbs = [
        'data/combinations.db',
        'data/lotto_numbers.db',
        'data/patterns.db'
    ]
    
    for db in main_dbs:
        if os.path.exists(db):
            db_files.append(db)
    
    # 필터 데이터베이스
    filters_dir = 'data/filters'
    if os.path.exists(filters_dir):
        for file in os.listdir(filters_dir):
            if file.endswith('.db'):
                db_files.append(os.path.join(filters_dir, file))
    
    print(f"\nFound {len(db_files)} database files")
    
    # 각 데이터베이스 최적화
    success_count = 0
    for db_path in db_files:
        if optimize_database(db_path):
            success_count += 1
        time.sleep(0.5)  # 잠시 대기
    
    print("\n" + "="*70)
    print(f"Result: {success_count}/{len(db_files)} databases optimized")
    
    if success_count == len(db_files):
        print("[SUCCESS] All databases optimized successfully!")
    else:
        print("[WARNING] Some databases failed to optimize")
    
    print("="*70)
    
    return success_count == len(db_files)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)