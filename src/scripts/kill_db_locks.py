#!/usr/bin/env python3
"""
데이터베이스 락을 강제로 해제하는 스크립트
WAL 파일 정리 및 프로세스 종료
"""
import os
import sys
import glob
import psutil
import time

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def find_db_files(base_dir='data'):
    """모든 SQLite 데이터베이스 파일 찾기"""
    db_files = []
    for pattern in ['*.db', '**/*.db']:
        db_files.extend(glob.glob(os.path.join(base_dir, pattern), recursive=True))
    return db_files

def clean_wal_files():
    """WAL 및 SHM 파일 정리"""
    print("\n=== WAL/SHM 파일 정리 ===\n")
    
    db_files = find_db_files()
    cleaned_count = 0
    
    for db_path in db_files:
        # WAL 파일 확인
        wal_path = db_path + '-wal'
        shm_path = db_path + '-shm'
        
        if os.path.exists(wal_path):
            try:
                os.remove(wal_path)
                print(f"[삭제] {wal_path}")
                cleaned_count += 1
            except Exception as e:
                print(f"[실패] {wal_path}: {e}")
        
        if os.path.exists(shm_path):
            try:
                os.remove(shm_path)
                print(f"[삭제] {shm_path}")
                cleaned_count += 1
            except Exception as e:
                print(f"[실패] {shm_path}: {e}")
    
    print(f"\n총 {cleaned_count}개의 WAL/SHM 파일을 정리했습니다.")

def find_locking_processes():
    """데이터베이스 파일을 잠그고 있는 프로세스 찾기"""
    print("\n=== 데이터베이스 파일을 사용 중인 프로세스 찾기 ===\n")
    
    db_files = find_db_files()
    locking_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'open_files']):
        try:
            # 프로세스가 열고 있는 파일 확인
            if proc.info['open_files']:
                for file in proc.info['open_files']:
                    for db_path in db_files:
                        if db_path in file.path:
                            locking_processes.append({
                                'pid': proc.info['pid'],
                                'name': proc.info['name'],
                                'file': file.path
                            })
                            print(f"PID {proc.info['pid']} ({proc.info['name']}) → {file.path}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    return locking_processes

def kill_locking_processes(processes):
    """데이터베이스를 잠그고 있는 프로세스 종료"""
    if not processes:
        print("\n데이터베이스를 잠그고 있는 프로세스가 없습니다.")
        return
    
    print(f"\n{len(processes)}개의 프로세스를 종료하시겠습니까? (y/n): ", end='')
    
    # 자동 실행 모드
    print("y (자동 모드)")
    
    killed_count = 0
    for proc_info in processes:
        try:
            proc = psutil.Process(proc_info['pid'])
            proc.terminate()
            print(f"[종료] PID {proc_info['pid']} ({proc_info['name']})")
            killed_count += 1
        except Exception as e:
            print(f"[실패] PID {proc_info['pid']}: {e}")
    
    if killed_count > 0:
        print(f"\n{killed_count}개의 프로세스를 종료했습니다.")
        print("3초 대기 중...")
        time.sleep(3)

def reset_db_locks():
    """데이터베이스 락 초기화"""
    print("\n=== SQLite 데이터베이스 락 초기화 ===\n")
    
    import sqlite3
    
    db_files = find_db_files()
    reset_count = 0
    
    for db_path in db_files:
        try:
            # 데이터베이스 연결 및 즉시 종료로 락 해제
            conn = sqlite3.connect(db_path, timeout=1.0)
            conn.execute("PRAGMA journal_mode=DELETE")  # WAL 모드 해제
            conn.close()
            
            # 다시 WAL 모드로 설정
            conn = sqlite3.connect(db_path, timeout=1.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
            
            print(f"[초기화] {db_path}")
            reset_count += 1
            
        except Exception as e:
            print(f"[실패] {db_path}: {e}")
    
    print(f"\n{reset_count}개의 데이터베이스를 초기화했습니다.")

def main():
    """메인 함수"""
    print("SQLite 데이터베이스 락 해제 도구")
    print("="*50)
    
    # 1. 프로세스 확인 및 종료
    locking_processes = find_locking_processes()
    if locking_processes:
        kill_locking_processes(locking_processes)
    
    # 2. WAL/SHM 파일 정리
    clean_wal_files()
    
    # 3. 데이터베이스 락 초기화
    reset_db_locks()
    
    print("\n✅ 데이터베이스 락 해제 완료!")
    print("\n이제 프로그램을 다시 실행해보세요.")

if __name__ == "__main__":
    main()