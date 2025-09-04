#!/usr/bin/env python3
"""
데이터베이스 연결 관리자
database is locked 에러를 방지하기 위한 향상된 연결 관리
"""
import sqlite3
import time
import logging
from contextlib import contextmanager
from typing import Optional, Generator
import threading
import os
import random

class DatabaseConnectionManager:
    """개선된 데이터베이스 연결 관리자"""
    
    # 클래스 레벨 락 관리
    _locks = {}
    _lock_creation_lock = threading.Lock()
    
    @classmethod
    def get_lock(cls, db_path: str) -> threading.Lock:
        """데이터베이스별 락 획득"""
        with cls._lock_creation_lock:
            if db_path not in cls._locks:
                cls._locks[db_path] = threading.RLock()  # RLock으로 변경
            return cls._locks[db_path]
    
    @staticmethod
    @contextmanager
    def get_connection(db_path: str, timeout: float = 120.0, 
                      max_retries: int = 5) -> Generator[sqlite3.Connection, None, None]:
        """
        안전한 데이터베이스 연결 생성 및 관리
        
        Args:
            db_path: 데이터베이스 파일 경로
            timeout: 연결 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            
        Yields:
            sqlite3.Connection: 데이터베이스 연결 객체
        """
        # 데이터베이스별 락 획득
        db_lock = DatabaseConnectionManager.get_lock(db_path)
        
        conn = None
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # 락 획득 시도
                acquired = db_lock.acquire(timeout=timeout)
                if not acquired:
                    if attempt < max_retries - 1:
                        # 랜덤 백오프
                        wait_time = retry_delay * (attempt + 1) + random.uniform(0, 1)
                        logging.warning(f"데이터베이스 락 대기 중... (시도 {attempt + 1}/{max_retries}, {wait_time:.1f}초 대기)")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise sqlite3.OperationalError("Could not acquire database lock after all retries")
                
                try:
                    # 연결 생성 - isolation_level=None으로 autocommit 모드
                    conn = sqlite3.connect(db_path, timeout=timeout, isolation_level=None, check_same_thread=False)
                    
                    # 한 번만 WAL 설정 확인
                    cursor = conn.cursor()
                    cursor.execute('PRAGMA journal_mode')
                    current_mode = cursor.fetchone()[0]
                    
                    if current_mode != 'wal':
                        # WAL 모드가 아닌 경우만 설정
                        cursor.execute('PRAGMA journal_mode = WAL')
                    
                    # 기본 최적화 설정
                    cursor.execute('PRAGMA synchronous = NORMAL')
                    cursor.execute('PRAGMA temp_store = MEMORY')
                    cursor.execute('PRAGMA cache_size = -64000')  # 64MB
                    cursor.execute('PRAGMA busy_timeout = 120000')  # 120초
                    cursor.execute('PRAGMA locking_mode = NORMAL')
                    
                    # 연결 반환
                    yield conn
                    break  # 성공시 루프 종료
                    
                finally:
                    # 연결 정리
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    # 락 해제
                    try:
                        db_lock.release()
                    except:
                        pass
                    
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1) + random.uniform(0, 2)
                    logging.warning(f"데이터베이스 잠금 발생, 재시도 중... (시도 {attempt + 1}/{max_retries}, {wait_time:.1f}초 대기)")
                    time.sleep(wait_time)
                else:
                    logging.error(f"데이터베이스 연결 실패: {str(e)}")
                    raise
            except Exception as e:
                logging.error(f"예상치 못한 데이터베이스 연결 오류: {str(e)}")
                raise

    @staticmethod
    def execute_with_retry(db_path: str, query: str, params: tuple = None,
                          max_retries: int = 5) -> Optional[list]:
        """
        쿼리 실행 with 자동 재시도
        
        Args:
            db_path: 데이터베이스 파일 경로
            query: 실행할 SQL 쿼리
            params: 쿼리 파라미터
            max_retries: 최대 재시도 횟수
            
        Returns:
            Optional[list]: 쿼리 결과 또는 None
        """
        for attempt in range(max_retries):
            try:
                with DatabaseConnectionManager.get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                    
                    # SELECT 쿼리인 경우 결과 반환
                    if query.strip().upper().startswith('SELECT'):
                        return cursor.fetchall()
                    else:
                        # autocommit 모드이므로 commit 불필요
                        return None
                        
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait_time = 0.5 * (attempt + 1) + random.uniform(0, 1)
                    logging.warning(f"쿼리 실행 중 잠금 발생, 재시도 중... (시도 {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
                    
        return None

    @staticmethod
    def check_database_integrity(db_path: str) -> bool:
        """
        데이터베이스 무결성 검사
        
        Args:
            db_path: 데이터베이스 파일 경로
            
        Returns:
            bool: 무결성 검사 통과 여부
        """
        try:
            with DatabaseConnectionManager.get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                return result and result[0] == "ok"
        except Exception as e:
            logging.error(f"데이터베이스 무결성 검사 실패: {str(e)}")
            return False

    @staticmethod
    def optimize_database(db_path: str) -> bool:
        """
        데이터베이스 최적화 (VACUUM, ANALYZE)
        
        Args:
            db_path: 데이터베이스 파일 경로
            
        Returns:
            bool: 최적화 성공 여부
        """
        try:
            # WAL 체크포인트 실행
            with DatabaseConnectionManager.get_connection(db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("ANALYZE")
            
            logging.info(f"데이터베이스 최적화 완료: {db_path}")
            return True
                    
        except Exception as e:
            logging.error(f"데이터베이스 최적화 실패: {str(e)}")
            return False

    @staticmethod
    def get_storage_mode(db_path: str) -> str:
        """데이터베이스 저장 모드 확인"""
        try:
            with DatabaseConnectionManager.get_connection(db_path) as conn:
                cursor = conn.cursor()
                
                # db_meta 테이블 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_meta'")
                if cursor.fetchone():
                    cursor.execute("SELECT value FROM db_meta WHERE key='storage_mode'")
                    result = cursor.fetchone()
                    if result:
                        return result[0]
                
                # 기본값 반환
                return 'normal'
                
        except Exception as e:
            logging.debug(f"저장 모드 확인 실패: {str(e)}")
            return 'normal'
