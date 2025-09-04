#!/usr/bin/env python3
"""
데이터베이스 락 문제 해결 스크립트
WAL 모드 정리 및 데이터베이스 최적화
"""
import sqlite3
import os
import time
import logging
import sys

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

def fix_database_lock(db_path: str):
    """데이터베이스 락 문제 해결"""
    logging.info(f"데이터베이스 락 문제 해결 시작: {db_path}")
    
    # WAL과 SHM 파일 경로
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    
    try:
        # 1. WAL 체크포인트 실행
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        logging.info("WAL 체크포인트 완료")
        
        # 2. 잠시 대기
        time.sleep(1)
        
        # 3. WAL/SHM 파일 삭제 시도
        if os.path.exists(wal_path):
            try:
                os.remove(wal_path)
                logging.info("WAL 파일 삭제 완료")
            except Exception as e:
                logging.warning(f"WAL 파일 삭제 실패: {e}")
                
        if os.path.exists(shm_path):
            try:
                os.remove(shm_path)
                logging.info("SHM 파일 삭제 완료")
            except Exception as e:
                logging.warning(f"SHM 파일 삭제 실패: {e}")
        
        # 4. 데이터베이스 무결성 검사
        conn = sqlite3.connect(db_path, timeout=5.0)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        
        if result[0] == "ok":
            logging.info("데이터베이스 무결성 검사 통과")
        else:
            logging.error(f"데이터베이스 무결성 검사 실패: {result}")
            
        # 5. VACUUM 실행 (선택적)
        logging.info("데이터베이스 최적화 (VACUUM) 실행 중...")
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.execute("VACUUM")
        conn.close()
        logging.info("데이터베이스 최적화 완료")
        
        return True
        
    except Exception as e:
        logging.error(f"데이터베이스 락 해결 실패: {e}")
        return False

def main():
    """메인 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 데이터베이스 경로
    db_path = os.path.join(project_root, "data", "combinations.db")
    
    if not os.path.exists(db_path):
        logging.error(f"데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        return
    
    # 락 문제 해결
    if fix_database_lock(db_path):
        logging.info("데이터베이스 락 문제가 해결되었습니다.")
        
        # 다른 데이터베이스도 정리
        other_dbs = [
            "data/lotto_numbers.db",
            "data/patterns.db"
        ]
        
        for db_name in other_dbs:
            other_db_path = os.path.join(project_root, db_name)
            if os.path.exists(other_db_path):
                logging.info(f"\n{db_name} 정리 중...")
                fix_database_lock(other_db_path)
    else:
        logging.error("데이터베이스 락 문제 해결에 실패했습니다.")

if __name__ == "__main__":
    main()