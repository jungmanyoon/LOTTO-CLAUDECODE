#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
트랜잭션 관리 테스트

Phase 3.13: Transaction 관리 개선
- SAVEPOINT 전략 적용
- 롤백 로직 강화
- 트랜잭션 타임아웃 설정
"""

import pytest
import sys
import os
import time
import tempfile
import sqlite3
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestTransactionManagerBasic:
    """TransactionManager 기본 기능 테스트"""

    def test_transaction_context_manager(self):
        """컨텍스트 매니저 기본 동작 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        # 임시 데이터베이스 생성
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            # TransactionManager 사용
            with TransactionManager(conn) as txn:
                assert txn.is_active
                conn.execute("INSERT INTO test (value) VALUES (?)", ("test1",))

            # 커밋 확인
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()
        finally:
            os.unlink(db_path)

    def test_transaction_auto_rollback_on_exception(self):
        """예외 발생 시 자동 롤백 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            # 예외 발생 시 롤백
            try:
                with TransactionManager(conn) as txn:
                    conn.execute("INSERT INTO test (value) VALUES (?)", ("test1",))
                    raise ValueError("테스트 예외")
            except ValueError:
                pass

            # 롤백 확인
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 0

            conn.close()
        finally:
            os.unlink(db_path)

    def test_transaction_manual_commit(self):
        """수동 커밋 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            txn = TransactionManager(conn)
            txn.begin()
            conn.execute("INSERT INTO test (value) VALUES (?)", ("test1",))
            txn.commit()

            # 커밋 확인
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()
        finally:
            os.unlink(db_path)

    def test_transaction_manual_rollback(self):
        """수동 롤백 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            txn = TransactionManager(conn)
            txn.begin()
            conn.execute("INSERT INTO test (value) VALUES (?)", ("test1",))
            txn.rollback("테스트 롤백")

            # 롤백 확인
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 0

            conn.close()
        finally:
            os.unlink(db_path)


class TestSavepoint:
    """SAVEPOINT 기능 테스트"""

    def test_savepoint_basic(self):
        """SAVEPOINT 기본 동작 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            with TransactionManager(conn) as txn:
                conn.execute("INSERT INTO test (value) VALUES (?)", ("outer",))

                with txn.savepoint('sp1') as sp:
                    conn.execute("INSERT INTO test (value) VALUES (?)", ("inner",))
                    # 정상 종료 - savepoint 해제

            # 둘 다 커밋됨
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 2

            conn.close()
        finally:
            os.unlink(db_path)

    def test_savepoint_rollback_on_exception(self):
        """SAVEPOINT 예외 발생 시 롤백 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            with TransactionManager(conn) as txn:
                conn.execute("INSERT INTO test (value) VALUES (?)", ("outer",))

                try:
                    with txn.savepoint('sp1') as sp:
                        conn.execute("INSERT INTO test (value) VALUES (?)", ("inner",))
                        raise ValueError("SAVEPOINT 내 예외")
                except ValueError:
                    pass  # savepoint 롤백됨

            # outer만 커밋됨
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor.execute("SELECT value FROM test")
            value = cursor.fetchone()[0]
            assert value == "outer"

            conn.close()
        finally:
            os.unlink(db_path)

    def test_nested_savepoints(self):
        """중첩 SAVEPOINT 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            with TransactionManager(conn) as txn:
                conn.execute("INSERT INTO test (value) VALUES (?)", ("level0",))

                with txn.savepoint('sp1') as sp1:
                    conn.execute("INSERT INTO test (value) VALUES (?)", ("level1",))

                    with txn.savepoint('sp2') as sp2:
                        conn.execute("INSERT INTO test (value) VALUES (?)", ("level2",))

            # 모두 커밋됨
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 3

            conn.close()
        finally:
            os.unlink(db_path)


class TestTransactionTimeout:
    """트랜잭션 타임아웃 테스트"""

    def test_timeout_check(self):
        """타임아웃 체크 로직 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.commit()

            # 매우 짧은 타임아웃
            txn = TransactionManager(conn, timeout=0.1)
            txn.begin()

            # 타임아웃 대기
            time.sleep(0.2)

            # 타임아웃 발생 확인
            with pytest.raises(TimeoutError):
                txn._check_timeout()

            conn.close()
        finally:
            os.unlink(db_path)

    def test_elapsed_time(self):
        """경과 시간 계산 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        conn = Mock()
        txn = TransactionManager(conn, timeout=30.0)

        # 시작 전
        assert txn.elapsed_time == 0.0

        # 시작 후
        txn.start_time = time.time() - 5.0  # 5초 전
        elapsed = txn.elapsed_time
        assert 4.9 <= elapsed <= 5.1


class TestTransactionState:
    """트랜잭션 상태 추적 테스트"""

    def test_is_active_property(self):
        """is_active 프로퍼티 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        conn = Mock()
        txn = TransactionManager(conn)

        # 초기 상태
        assert not txn.is_active

        # 시작 후
        txn._is_active = True
        assert txn.is_active

        # 커밋 후
        txn._committed = True
        assert not txn.is_active

    def test_state_after_commit(self):
        """커밋 후 상태 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            txn = TransactionManager(conn)
            txn.begin()
            assert txn._is_active
            assert not txn._committed
            assert not txn._rolled_back

            txn.commit()
            assert not txn._is_active
            assert txn._committed
            assert not txn._rolled_back

            conn.close()
        finally:
            os.unlink(db_path)

    def test_state_after_rollback(self):
        """롤백 후 상태 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            txn = TransactionManager(conn)
            txn.begin()
            txn.rollback()

            assert not txn._is_active
            assert not txn._committed
            assert txn._rolled_back

            conn.close()
        finally:
            os.unlink(db_path)


class TestTransactionDecorator:
    """트랜잭션 데코레이터 테스트"""

    def test_with_transaction_decorator(self):
        """with_transaction 데코레이터 테스트"""
        from src.utils.db_connection_manager import with_transaction

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            @with_transaction(timeout=30.0)
            def insert_data(connection, value):
                connection.execute("INSERT INTO test (value) VALUES (?)", (value,))

            insert_data(conn, "decorated_value")

            # 커밋 확인
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM test")
            result = cursor.fetchone()[0]
            assert result == "decorated_value"

            conn.close()
        finally:
            os.unlink(db_path)

    def test_decorator_rollback_on_exception(self):
        """데코레이터 예외 시 롤백 테스트"""
        from src.utils.db_connection_manager import with_transaction

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

            @with_transaction(timeout=30.0)
            def insert_and_fail(connection, value):
                connection.execute("INSERT INTO test (value) VALUES (?)", (value,))
                raise RuntimeError("테스트 예외")

            with pytest.raises(RuntimeError):
                insert_and_fail(conn, "will_rollback")

            # 롤백 확인
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 0

            conn.close()
        finally:
            os.unlink(db_path)


class TestTransactionScope:
    """transaction_scope 컨텍스트 매니저 테스트"""

    def test_transaction_scope_basic(self):
        """transaction_scope 기본 동작 테스트"""
        from src.utils.db_connection_manager import transaction_scope

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            # 테이블 생성
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()
            conn.close()

            # transaction_scope 사용
            with transaction_scope(db_path) as (conn, txn):
                assert txn.is_active
                conn.execute("INSERT INTO test (value) VALUES (?)", ("scope_test",))

            # 커밋 확인
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM test")
            result = cursor.fetchone()[0]
            assert result == "scope_test"
            conn.close()

        finally:
            os.unlink(db_path)

    def test_transaction_scope_with_savepoint(self):
        """transaction_scope와 savepoint 조합 테스트"""
        from src.utils.db_connection_manager import transaction_scope

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()
            conn.close()

            with transaction_scope(db_path) as (conn, txn):
                conn.execute("INSERT INTO test (value) VALUES (?)", ("outer",))

                with txn.savepoint('sp1'):
                    conn.execute("INSERT INTO test (value) VALUES (?)", ("inner",))

            # 확인
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 2
            conn.close()

        finally:
            os.unlink(db_path)


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_double_commit(self):
        """중복 커밋 시도 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            txn = TransactionManager(conn)
            txn.begin()
            txn.commit()

            # 두 번째 커밋은 무시됨
            txn.commit()  # 경고만 발생

            conn.close()
        finally:
            os.unlink(db_path)

    def test_double_rollback(self):
        """중복 롤백 시도 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            txn = TransactionManager(conn)
            txn.begin()
            txn.rollback("first")

            # 두 번째 롤백은 무시됨
            txn.rollback("second")  # 무시됨

            conn.close()
        finally:
            os.unlink(db_path)

    def test_savepoint_without_active_transaction(self):
        """활성 트랜잭션 없이 savepoint 시도"""
        from src.utils.db_connection_manager import TransactionManager

        conn = Mock()
        txn = TransactionManager(conn)

        with pytest.raises(RuntimeError, match="활성 트랜잭션이 없습니다"):
            with txn.savepoint('sp1'):
                pass

    def test_begin_when_already_active(self):
        """이미 활성 상태에서 begin 시도"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            txn = TransactionManager(conn)
            txn.begin()
            txn.begin()  # 경고만 발생, 에러 아님

            assert txn.is_active
            txn.rollback()
            conn.close()
        finally:
            os.unlink(db_path)


class TestSavepointLogic:
    """SAVEPOINT 로직 상세 테스트"""

    def test_savepoint_name_auto_generation(self):
        """SAVEPOINT 이름 자동 생성 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.commit()

            with TransactionManager(conn) as txn:
                with txn.savepoint() as sp_name:
                    # 자동 생성된 이름 확인
                    assert sp_name.startswith('sp_')
                    assert len(sp_name) == 11  # 'sp_' + 8 hex chars

            conn.close()
        finally:
            os.unlink(db_path)

    def test_savepoint_tracking(self):
        """SAVEPOINT 추적 테스트"""
        from src.utils.db_connection_manager import TransactionManager

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.commit()

            with TransactionManager(conn) as txn:
                assert len(txn.savepoints) == 0

                with txn.savepoint('sp1') as sp1:
                    assert len(txn.savepoints) == 1
                    assert 'sp1' in txn.savepoints

                # savepoint 해제 후
                assert len(txn.savepoints) == 0

            conn.close()
        finally:
            os.unlink(db_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
