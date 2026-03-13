#!/usr/bin/env python3
"""
데이터베이스 연결 관리자
database is locked 에러를 방지하기 위한 향상된 연결 관리

Phase 3.13: Transaction 관리 개선
- SAVEPOINT 전략 적용
- 롤백 로직 강화
- 트랜잭션 타임아웃 설정
"""
import sqlite3
import time
import logging
from contextlib import contextmanager
from typing import Optional, Generator, Any, Callable
import threading
import os
import random
import uuid
from functools import wraps

class DatabaseConnectionManager:
    """개선된 데이터베이스 연결 관리자"""

    # 클래스 레벨 락 관리
    _locks = {}
    _lock_creation_lock = threading.Lock()
    # WAL 모드 확인 완료된 DB 경로 캐시
    _wal_verified_dbs = set()
    _wal_verified_lock = threading.Lock()
    
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

        FIX: threading.RLock 제거 - SQLite WAL 모드 + busy_timeout이 동시 접근을 처리함
        threading.RLock은 병렬 스레드 수가 많을 때 120초 타임아웃으로 인해 lock 획득 실패를 유발

        Args:
            db_path: 데이터베이스 파일 경로
            timeout: 연결 타임아웃 (초)
            max_retries: 최대 재시도 횟수

        Yields:
            sqlite3.Connection: 데이터베이스 연결 객체
        """
        conn = None
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                # 연결 생성 - WAL 모드가 동시 접근을 내부적으로 처리
                # isolation_level='DEFERRED': BEGIN 시 락 획득
                conn = sqlite3.connect(db_path, timeout=timeout, isolation_level='DEFERRED', check_same_thread=False)

                cursor = conn.cursor()

                # WAL 모드는 DB 파일 수준에서 영구 설정 - 최초 1회만 체크
                abs_path = os.path.abspath(db_path)
                need_wal_check = abs_path not in DatabaseConnectionManager._wal_verified_dbs
                if need_wal_check:
                    cursor.execute('PRAGMA journal_mode')
                    current_mode = cursor.fetchone()[0]
                    if current_mode != 'wal':
                        cursor.execute('PRAGMA journal_mode = WAL')
                    with DatabaseConnectionManager._wal_verified_lock:
                        DatabaseConnectionManager._wal_verified_dbs.add(abs_path)

                # 기본 최적화 설정 (연결당 1회 필요)
                cursor.execute('PRAGMA synchronous = NORMAL')
                cursor.execute('PRAGMA temp_store = MEMORY')
                cursor.execute('PRAGMA cache_size = -64000')  # 64MB
                cursor.execute('PRAGMA busy_timeout = 120000')  # 120초 (SQLite 내장 재시도)
                cursor.execute('PRAGMA locking_mode = NORMAL')
                cursor.execute('PRAGMA foreign_keys = ON')

                # 연결 반환
                yield conn
                break  # 성공시 루프 종료

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
            finally:
                # 연결 정리
                if conn:
                    try:
                        conn.close()
                    except sqlite3.Error as e:
                        logging.debug(f"연결 닫기 실패 (무시): {e}")

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
                        # FIX: DEFERRED 모드에서는 commit 필요
                        conn.commit()
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


class TransactionManager:
    """
    향상된 트랜잭션 관리자 (Phase 3.13)

    Features:
    - SAVEPOINT를 사용한 중첩 트랜잭션 지원
    - 자동 롤백 및 에러 처리
    - 트랜잭션 타임아웃
    - 트랜잭션 상태 추적

    Usage:
        with TransactionManager(conn) as txn:
            cursor.execute(...)
            with txn.savepoint('sp1'):  # 중첩 트랜잭션
                cursor.execute(...)
            # savepoint 자동 해제
        # 트랜잭션 자동 커밋 또는 롤백
    """

    def __init__(self, connection: sqlite3.Connection, timeout: float = 30.0):
        """
        트랜잭션 관리자 초기화

        Args:
            connection: SQLite 연결 객체
            timeout: 트랜잭션 타임아웃 (초)
        """
        self.connection = connection
        self.timeout = timeout
        self.start_time = None
        self.savepoints = []
        self._is_active = False
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> 'TransactionManager':
        """트랜잭션 시작"""
        self.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """트랜잭션 종료 - 예외 발생 시 자동 롤백"""
        if exc_type is not None:
            # 예외 발생 시 롤백
            self.rollback(f"예외 발생: {exc_type.__name__}: {exc_val}")
            return False  # 예외 전파
        else:
            # 정상 종료 시 커밋
            if not self._committed and not self._rolled_back:
                self.commit()
        return False

    def begin(self) -> None:
        """트랜잭션 시작"""
        if self._is_active:
            logging.warning("트랜잭션이 이미 활성화되어 있습니다")
            return

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self._is_active = True
            self.start_time = time.time()
            logging.debug("트랜잭션 시작 (IMMEDIATE 모드)")
        except sqlite3.OperationalError as e:
            if "cannot start a transaction within a transaction" in str(e):
                # 이미 트랜잭션이 진행 중인 경우
                self._is_active = True
                self.start_time = time.time()
                logging.debug("기존 트랜잭션 사용")
            else:
                raise

    def commit(self) -> None:
        """트랜잭션 커밋"""
        if not self._is_active:
            logging.warning("활성 트랜잭션이 없습니다")
            return

        if self._committed or self._rolled_back:
            logging.warning("트랜잭션이 이미 종료되었습니다")
            return

        # 타임아웃 체크
        self._check_timeout()

        # 모든 savepoint 해제
        while self.savepoints:
            sp_name = self.savepoints.pop()
            try:
                self.connection.execute(f"RELEASE SAVEPOINT {sp_name}")
                logging.debug(f"SAVEPOINT 해제: {sp_name}")
            except sqlite3.Error as e:
                logging.debug(f"SAVEPOINT 해제 실패 (무시): {sp_name}, {e}")

        try:
            self.connection.commit()
            self._committed = True
            elapsed = time.time() - self.start_time if self.start_time else 0
            logging.debug(f"트랜잭션 커밋 완료 ({elapsed:.2f}초)")
        except sqlite3.Error as e:
            logging.error(f"트랜잭션 커밋 실패: {e}")
            self.rollback(f"커밋 실패: {e}")
            raise
        finally:
            self._is_active = False

    def rollback(self, reason: str = "수동 롤백") -> None:
        """트랜잭션 롤백"""
        if self._rolled_back:
            logging.debug("트랜잭션이 이미 롤백되었습니다")
            return

        # 모든 savepoint 롤백
        while self.savepoints:
            sp_name = self.savepoints.pop()
            try:
                self.connection.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                self.connection.execute(f"RELEASE SAVEPOINT {sp_name}")
                logging.debug(f"SAVEPOINT 롤백: {sp_name}")
            except sqlite3.Error as e:
                logging.debug(f"SAVEPOINT 롤백 실패 (무시): {sp_name}, {e}")

        try:
            self.connection.rollback()
            self._rolled_back = True
            elapsed = time.time() - self.start_time if self.start_time else 0
            logging.warning(f"트랜잭션 롤백 ({elapsed:.2f}초): {reason}")
        except sqlite3.Error as e:
            logging.error(f"트랜잭션 롤백 실패: {e}")
        finally:
            self._is_active = False

    @contextmanager
    def savepoint(self, name: str = None) -> Generator[str, None, None]:
        """
        SAVEPOINT 생성 (중첩 트랜잭션)

        Args:
            name: SAVEPOINT 이름 (없으면 자동 생성)

        Yields:
            str: SAVEPOINT 이름

        Usage:
            with txn.savepoint('sp1') as sp:
                cursor.execute(...)
                # 예외 발생 시 이 savepoint까지만 롤백
        """
        if not self._is_active:
            raise RuntimeError("활성 트랜잭션이 없습니다")

        # 타임아웃 체크
        self._check_timeout()

        # SAVEPOINT 이름 생성
        sp_name = name or f"sp_{uuid.uuid4().hex[:8]}"

        try:
            self.connection.execute(f"SAVEPOINT {sp_name}")
            self.savepoints.append(sp_name)
            logging.debug(f"SAVEPOINT 생성: {sp_name}")
            yield sp_name

            # 정상 종료 시 RELEASE
            if sp_name in self.savepoints:
                self.savepoints.remove(sp_name)
                self.connection.execute(f"RELEASE SAVEPOINT {sp_name}")
                logging.debug(f"SAVEPOINT 해제: {sp_name}")

        except Exception as e:
            # 예외 발생 시 이 savepoint까지 롤백
            if sp_name in self.savepoints:
                self.savepoints.remove(sp_name)
                try:
                    self.connection.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                    self.connection.execute(f"RELEASE SAVEPOINT {sp_name}")
                    logging.warning(f"SAVEPOINT 롤백: {sp_name}, 원인: {e}")
                except sqlite3.Error as rollback_error:
                    logging.error(f"SAVEPOINT 롤백 실패: {sp_name}, {rollback_error}")
            raise

    def _check_timeout(self) -> None:
        """트랜잭션 타임아웃 체크"""
        if self.start_time and self.timeout:
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout:
                self.rollback(f"타임아웃 ({elapsed:.2f}초 > {self.timeout}초)")
                raise TimeoutError(f"트랜잭션 타임아웃: {elapsed:.2f}초 초과")

    @property
    def is_active(self) -> bool:
        """트랜잭션 활성 상태"""
        return self._is_active and not self._committed and not self._rolled_back

    @property
    def elapsed_time(self) -> float:
        """경과 시간 (초)"""
        if self.start_time:
            return time.time() - self.start_time
        return 0.0


def with_transaction(timeout: float = 30.0):
    """
    트랜잭션 데코레이터

    함수 실행을 트랜잭션으로 감싸고, 예외 발생 시 자동 롤백합니다.

    Args:
        timeout: 트랜잭션 타임아웃 (초)

    Usage:
        @with_transaction(timeout=60.0)
        def save_data(conn, data):
            cursor = conn.cursor()
            cursor.executemany(...)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(connection: sqlite3.Connection, *args, **kwargs) -> Any:
            with TransactionManager(connection, timeout=timeout):
                return func(connection, *args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def transaction_scope(db_path: str, timeout: float = 30.0) -> Generator[tuple, None, None]:
    """
    트랜잭션 스코프 컨텍스트 매니저

    연결과 트랜잭션을 함께 관리합니다.

    Args:
        db_path: 데이터베이스 파일 경로
        timeout: 트랜잭션 타임아웃 (초)

    Yields:
        tuple: (connection, transaction_manager)

    Usage:
        with transaction_scope('test.db') as (conn, txn):
            cursor = conn.cursor()
            cursor.execute(...)
            with txn.savepoint('sp1'):
                cursor.execute(...)
    """
    with DatabaseConnectionManager.get_connection(db_path) as conn:
        with TransactionManager(conn, timeout=timeout) as txn:
            yield conn, txn
