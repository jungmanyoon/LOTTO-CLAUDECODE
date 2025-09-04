#!/usr/bin/env python3
"""
데이터베이스 최적화 스크립트
모든 SQLite 데이터베이스의 무결성 검사 및 최적화 수행
"""
import os
import sys
import logging
from glob import glob

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.db_connection_manager import DatabaseConnectionManager
from src.core.db_manager import DatabaseManager

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def find_all_databases(base_dir: str = 'data') -> list:
    """모든 SQLite 데이터베이스 파일 찾기"""
    db_files = []
    
    # .db 파일 찾기
    for db_path in glob(os.path.join(base_dir, '**', '*.db'), recursive=True):
        db_files.append(db_path)
    
    return db_files

def optimize_all_databases():
    """모든 데이터베이스 최적화"""
    print("\n=== 데이터베이스 최적화 시작 ===\n")
    
    # 데이터베이스 파일 찾기
    db_files = find_all_databases()
    
    if not db_files:
        print("데이터베이스 파일을 찾을 수 없습니다.")
        return
    
    print(f"총 {len(db_files)}개의 데이터베이스 파일을 발견했습니다.\n")
    
    success_count = 0
    fail_count = 0
    
    for db_path in db_files:
        print(f"\n처리 중: {db_path}")
        
        # 데이터베이스 정보 출력
        info = DatabaseConnectionManager.get_database_info(db_path)
        print(f"  - 파일 크기: {info['file_size']:,} bytes")
        print(f"  - 페이지 수: {info['page_count']:,}")
        print(f"  - 저널 모드: {info['journal_mode']}")
        print(f"  - 테이블: {', '.join(info['tables'])}")
        
        # 무결성 검사
        print("  - 무결성 검사 중...", end='')
        if DatabaseConnectionManager.check_database_integrity(db_path):
            print(" [통과]")
            
            # 최적화 수행
            print("  - 최적화 수행 중...", end='')
            if DatabaseConnectionManager.optimize_database(db_path):
                print(" [완료]")
                
                # 최적화 후 정보
                new_info = DatabaseConnectionManager.get_database_info(db_path)
                size_reduction = info['file_size'] - new_info['file_size']
                if size_reduction > 0:
                    reduction_percent = (size_reduction / info['file_size']) * 100
                    print(f"  - 파일 크기 감소: {size_reduction:,} bytes ({reduction_percent:.1f}%)")
                
                success_count += 1
            else:
                print(" [실패]")
                fail_count += 1
        else:
            print(" [실패]")
            print("  ! 무결성 검사 실패 - 데이터베이스가 손상되었을 수 있습니다.")
            fail_count += 1
    
    # 결과 요약
    print(f"\n\n=== 최적화 완료 ===")
    print(f"성공: {success_count}개")
    print(f"실패: {fail_count}개")
    print(f"총 처리: {len(db_files)}개")

def check_locked_databases():
    """잠긴 데이터베이스 확인"""
    print("\n=== 데이터베이스 잠금 상태 확인 ===\n")
    
    db_files = find_all_databases()
    locked_count = 0
    
    for db_path in db_files:
        try:
            # 간단한 쿼리로 접근 가능 여부 확인
            with DatabaseConnectionManager.get_connection(db_path, timeout=5.0, max_retries=1) as conn:
                conn.execute("SELECT 1")
            print(f"[정상] {db_path}")
        except Exception as e:
            if "database is locked" in str(e):
                print(f"[잠김] {db_path}")
                locked_count += 1
            else:
                print(f"[오류] {db_path}: {str(e)}")
    
    if locked_count > 0:
        print(f"\n잠긴 데이터베이스: {locked_count}개")
        print("프로그램을 종료하고 다시 시도하세요.")
    else:
        print("\n모든 데이터베이스가 정상적으로 접근 가능합니다.")

def main():
    """메인 함수"""
    setup_logging()
    
    # 자동으로 최적화 실행
    check_locked_databases()
    print("\n" + "="*50 + "\n")
    optimize_all_databases()

if __name__ == "__main__":
    main()