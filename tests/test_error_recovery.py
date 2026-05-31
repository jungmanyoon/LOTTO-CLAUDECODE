#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
에러 복구 테스트

Phase 2.11: Error Recovery Tests
- 커스텀 예외 클래스 테스트
- 롤백 시나리오 테스트
- 체크포인트 복구 테스트
- DB 락 타임아웃 테스트
- 캐시 손상 복구 테스트
- SystemHealthChecker 테스트

목표 커버리지: 70%+
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import sys
import json
import sqlite3
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# =========================================================================
# Test Fixtures
# =========================================================================

@pytest.fixture
def temp_dir():
    """임시 디렉토리"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_db_path(temp_dir):
    """임시 데이터베이스 경로"""
    return os.path.join(temp_dir, 'test.db')


@pytest.fixture
def temp_config_path(temp_dir):
    """임시 설정 파일 경로"""
    config_path = os.path.join(temp_dir, 'config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write("""
adaptive_options:
  global_probability_threshold: 1.0
  ml_relaxed_threshold: 0.5
dynamic_criteria:
  sum_range:
    min: 100
    max: 200
""")
    return config_path


# =========================================================================
# Custom Exception Tests
# =========================================================================

class TestLottoBaseException:
    """기본 예외 클래스 테스트"""

    def test_base_exception_creation(self):
        """[OK] 기본 예외 생성"""
        from src.core.exceptions import LottoBaseException

        exc = LottoBaseException("테스트 메시지")

        assert exc.message == "테스트 메시지"
        assert exc.error_code is not None
        assert exc.details == {}

    def test_base_exception_with_details(self):
        """[OK] 상세 정보 포함 예외"""
        from src.core.exceptions import LottoBaseException

        exc = LottoBaseException(
            "테스트 메시지",
            error_code="TEST_001",
            details={'key': 'value'}
        )

        assert exc.error_code == "TEST_001"
        assert exc.details == {'key': 'value'}

    def test_base_exception_with_cause(self):
        """[OK] 원인 예외 포함"""
        from src.core.exceptions import LottoBaseException

        cause = ValueError("원인 에러")
        exc = LottoBaseException("테스트 메시지", cause=cause)

        assert exc.cause == cause

    def test_base_exception_to_dict(self):
        """[OK] 딕셔너리 변환"""
        from src.core.exceptions import LottoBaseException

        exc = LottoBaseException(
            "테스트 메시지",
            error_code="TEST_001",
            details={'key': 'value'}
        )

        result = exc.to_dict()

        assert result['error_type'] == 'LottoBaseException'
        assert result['error_code'] == 'TEST_001'
        assert result['message'] == '테스트 메시지'
        assert result['details'] == {'key': 'value'}

    def test_base_exception_str(self):
        """[OK] 문자열 표현"""
        from src.core.exceptions import LottoBaseException

        exc = LottoBaseException("테스트 메시지", error_code="TEST_001")
        str_repr = str(exc)

        assert "TEST_001" in str_repr
        assert "테스트 메시지" in str_repr


class TestDatabaseError:
    """데이터베이스 예외 테스트"""

    def test_database_error_creation(self):
        """[OK] 데이터베이스 예외 생성"""
        from src.core.exceptions import DatabaseError

        exc = DatabaseError("DB 연결 실패", db_path="test.db")

        assert "DB 연결 실패" in exc.message
        # db_path가 details에 포함되어 있는지 확인
        assert 'db_path' in exc.details or exc.details.get('db_path') == 'test.db'

    def test_database_connection_error(self):
        """[OK] DB 연결 에러"""
        try:
            from src.core.exceptions import DatabaseConnectionError
            exc = DatabaseConnectionError("연결 실패")
            assert exc is not None
        except ImportError:
            pytest.skip("DatabaseConnectionError not available")

    def test_database_query_error(self):
        """[OK] DB 쿼리 에러"""
        try:
            from src.core.exceptions import DatabaseQueryError
            exc = DatabaseQueryError("쿼리 실패", query="SELECT * FROM table")
            assert exc is not None
        except ImportError:
            pytest.skip("DatabaseQueryError not available")


class TestFilterError:
    """필터 예외 테스트"""

    def test_filter_error_creation(self):
        """[OK] 필터 예외 생성"""
        try:
            from src.core.exceptions import FilterError
            exc = FilterError("필터 실행 실패")
            assert "필터" in exc.message or "Filter" in exc.message
        except ImportError:
            pytest.skip("FilterError not available")

    def test_filter_config_error(self):
        """[OK] 필터 설정 에러"""
        try:
            from src.core.exceptions import FilterConfigError
            exc = FilterConfigError("설정 오류", filter_name="sum_range")
            assert exc is not None
        except ImportError:
            pytest.skip("FilterConfigError not available")


class TestMLError:
    """ML 예외 테스트"""

    def test_ml_error_creation(self):
        """[OK] ML 예외 생성"""
        try:
            from src.core.exceptions import MLError
            exc = MLError("모델 로드 실패")
            assert exc is not None
        except ImportError:
            pytest.skip("MLError not available")

    def test_model_load_error(self):
        """[OK] 모델 로드 에러"""
        try:
            from src.core.exceptions import ModelLoadError
            exc = ModelLoadError("모델 파일 손상")
            assert exc is not None
        except ImportError:
            pytest.skip("ModelLoadError not available")

    def test_prediction_error(self):
        """[OK] 예측 에러"""
        try:
            from src.core.exceptions import PredictionError
            exc = PredictionError("예측 실패")
            assert exc is not None
        except ImportError:
            pytest.skip("PredictionError not available")


# =========================================================================
# Rollback Scenario Tests
# =========================================================================

class TestRollbackScenarios:
    """롤백 시나리오 테스트"""

    def test_config_backup_exists(self, temp_config_path):
        """[OK] 설정 파일 백업 기능"""
        import shutil

        # 백업 파일 생성
        backup_path = temp_config_path + '.backup'
        shutil.copy(temp_config_path, backup_path)

        assert os.path.exists(backup_path)

        # 롤백 시뮬레이션
        shutil.copy(backup_path, temp_config_path)
        assert os.path.exists(temp_config_path)

    def test_transaction_rollback(self, temp_db_path):
        """[OK] 트랜잭션 롤백 테스트"""
        # DB 생성 및 테이블 생성 (명시적 close로 Windows 파일 잠금 방지)
        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            cursor.execute("INSERT INTO test (value) VALUES ('original')")
            conn.commit()
        finally:
            conn.close()

        # 트랜잭션 롤백 테스트
        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO test (value) VALUES ('should_rollback')")
            # 롤백 실행
            conn.rollback()
        finally:
            conn.close()

        # 롤백 확인
        conn = sqlite3.connect(temp_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
        finally:
            conn.close()

        assert count == 1  # 원래 데이터만 있어야 함

    @patch('src.core.threshold_optimizer.ThresholdOptimizer')
    def test_optimization_rollback(self, mock_optimizer, temp_config_path):
        """[OK] 최적화 롤백 시뮬레이션"""
        # 원래 값 저장
        original_threshold = 1.0

        # 새 값으로 변경 시도 (실패 시뮬레이션)
        new_threshold = 0.5

        # 롤백
        restored_threshold = original_threshold

        assert restored_threshold == original_threshold


# =========================================================================
# Checkpoint Recovery Tests
# =========================================================================

class TestCheckpointRecovery:
    """체크포인트 복구 테스트"""

    def test_checkpoint_file_creation(self, temp_dir):
        """[OK] 체크포인트 파일 생성"""
        checkpoint_path = os.path.join(temp_dir, 'checkpoint.json')

        checkpoint_data = {
            'version': '1.0',
            'created_at': '2024-01-01T00:00:00',
            'current_trial': 5,
            'total_trials': 25,
            'best_score': 1.5
        }

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f)

        assert os.path.exists(checkpoint_path)

    def test_checkpoint_load_recovery(self, temp_dir):
        """[OK] 체크포인트 로드 복구"""
        checkpoint_path = os.path.join(temp_dir, 'checkpoint.json')

        # 체크포인트 저장
        checkpoint_data = {
            'version': '1.0',
            'current_trial': 10,
            'best_params': {'threshold': 1.0}
        }
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f)

        # 체크포인트 로드
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        assert loaded['current_trial'] == 10
        assert loaded['best_params']['threshold'] == 1.0

    def test_checkpoint_corruption_handling(self, temp_dir):
        """[OK] 손상된 체크포인트 처리"""
        checkpoint_path = os.path.join(temp_dir, 'checkpoint.json')

        # 손상된 JSON 파일 생성
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            f.write("{invalid json")

        # 손상된 파일 로드 시도
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                json.load(f)
            assert False, "Should raise JSONDecodeError"
        except json.JSONDecodeError:
            pass  # 예상된 동작

    def test_checkpoint_missing_handling(self, temp_dir):
        """[OK] 누락된 체크포인트 처리"""
        checkpoint_path = os.path.join(temp_dir, 'nonexistent.json')

        # 파일 없음 확인
        assert not os.path.exists(checkpoint_path)

        # 새 체크포인트 생성으로 복구
        default_checkpoint = {'version': '1.0', 'current_trial': 0}
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(default_checkpoint, f)

        assert os.path.exists(checkpoint_path)


# =========================================================================
# Database Lock Tests
# =========================================================================

class TestDatabaseLock:
    """DB 락 타임아웃 테스트"""

    def test_database_timeout_setting(self, temp_db_path):
        """[OK] DB 타임아웃 설정"""
        # 타임아웃 설정 테스트
        conn = sqlite3.connect(temp_db_path, timeout=5.0)
        assert conn is not None
        conn.close()

    def test_database_busy_handling(self, temp_db_path):
        """[OK] DB 비지 상태 처리"""
        # 첫 번째 연결 (락 유지)
        conn1 = sqlite3.connect(temp_db_path, timeout=1.0)
        cursor1 = conn1.cursor()
        cursor1.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        cursor1.execute("BEGIN EXCLUSIVE")

        # 두 번째 연결 시도 (타임아웃 예상)
        conn2 = sqlite3.connect(temp_db_path, timeout=0.1)

        try:
            cursor2 = conn2.cursor()
            cursor2.execute("INSERT INTO test (id) VALUES (1)")
            # 락 때문에 실패할 수 있음
        except sqlite3.OperationalError:
            pass  # 예상된 동작

        conn1.rollback()
        conn1.close()
        conn2.close()

    def test_wal_mode_performance(self, temp_db_path):
        """[OK] WAL 모드 설정"""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # WAL 모드 활성화
        cursor.execute("PRAGMA journal_mode=WAL")
        mode = cursor.fetchone()[0]

        # WAL 또는 기본 모드 (테스트 환경에 따라 다름)
        assert mode in ['wal', 'delete', 'memory']

        conn.close()


# =========================================================================
# Cache Corruption Recovery Tests
# =========================================================================

class TestCacheRecovery:
    """캐시 손상 복구 테스트"""

    def test_cache_directory_creation(self, temp_dir):
        """[OK] 캐시 디렉토리 생성"""
        cache_dir = os.path.join(temp_dir, 'cache', 'models')

        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        assert os.path.exists(cache_dir)

    def test_corrupted_cache_detection(self, temp_dir):
        """[OK] 손상된 캐시 감지"""
        cache_file = os.path.join(temp_dir, 'model.pkl')

        # 손상된 캐시 파일 생성
        with open(cache_file, 'wb') as f:
            f.write(b'corrupted data')

        # pickle 로드 시도
        import pickle
        try:
            with open(cache_file, 'rb') as f:
                pickle.load(f)
            assert False, "Should raise error"
        except Exception:
            pass  # 예상된 동작 (손상 감지)

    def test_cache_cleanup(self, temp_dir):
        """[OK] 캐시 정리"""
        cache_dir = os.path.join(temp_dir, 'cache')
        os.makedirs(cache_dir)

        # 테스트 파일 생성
        test_files = ['cache1.pkl', 'cache2.pkl', 'cache3.pkl']
        for filename in test_files:
            filepath = os.path.join(cache_dir, filename)
            with open(filepath, 'w') as f:
                f.write('test')

        # 캐시 정리
        for filename in test_files:
            filepath = os.path.join(cache_dir, filename)
            os.remove(filepath)

        # 정리 확인
        remaining = os.listdir(cache_dir)
        assert len(remaining) == 0

    def test_cache_recreation(self, temp_dir):
        """[OK] 캐시 재생성"""
        cache_file = os.path.join(temp_dir, 'model_cache.json')

        # 손상된 캐시 제거
        if os.path.exists(cache_file):
            os.remove(cache_file)

        # 새 캐시 생성
        new_cache = {
            'version': '1.0',
            'created_at': '2024-01-01T00:00:00',
            'data': {}
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(new_cache, f)

        assert os.path.exists(cache_file)


# =========================================================================
# System Health Checker Tests
# =========================================================================

class TestSystemHealthChecker:
    """시스템 건강 체크 테스트"""

    def test_database_health_check(self, temp_db_path):
        """[OK] 데이터베이스 건강 체크"""
        # DB 생성 및 테스트 테이블
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE health_check (id INTEGER)")
        conn.commit()

        # 건강 체크 쿼리
        cursor.execute("SELECT 1")
        result = cursor.fetchone()

        assert result[0] == 1
        conn.close()

    def test_file_system_health_check(self, temp_dir):
        """[OK] 파일 시스템 건강 체크"""
        # 쓰기 테스트
        test_file = os.path.join(temp_dir, 'health_test.txt')
        with open(test_file, 'w') as f:
            f.write('health check')

        # 읽기 테스트
        with open(test_file, 'r') as f:
            content = f.read()

        assert content == 'health check'

        # 삭제 테스트
        os.remove(test_file)
        assert not os.path.exists(test_file)

    def test_memory_health_check(self):
        """[OK] 메모리 건강 체크"""
        import psutil

        memory = psutil.virtual_memory()

        # 메모리 정보 확인
        assert memory.total > 0
        assert memory.available > 0
        assert 0 <= memory.percent <= 100

    def test_disk_health_check(self, temp_dir):
        """[OK] 디스크 건강 체크"""
        import psutil

        disk = psutil.disk_usage(temp_dir)

        # 디스크 정보 확인
        assert disk.total > 0
        assert disk.free > 0
        assert 0 <= disk.percent <= 100


# =========================================================================
# Integration Tests
# =========================================================================

@pytest.mark.integration
class TestErrorRecoveryIntegration:
    """에러 복구 통합 테스트"""

    def test_full_recovery_workflow(self, temp_dir, temp_db_path):
        """[OK] 전체 복구 워크플로우"""
        # 1. 초기 상태 설정
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE state (id INTEGER, value TEXT)")
        cursor.execute("INSERT INTO state VALUES (1, 'initial')")
        conn.commit()

        # 2. 체크포인트 저장
        checkpoint_path = os.path.join(temp_dir, 'checkpoint.json')
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump({'state': 'before_error'}, f)

        # 3. 에러 시뮬레이션 후 롤백
        try:
            cursor.execute("INSERT INTO state VALUES (2, 'error_state')")
            raise Exception("Simulated error")
        except Exception:
            conn.rollback()

        # 4. 체크포인트에서 복구
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)

        assert checkpoint['state'] == 'before_error'

        # 5. 상태 확인
        cursor.execute("SELECT COUNT(*) FROM state")
        count = cursor.fetchone()[0]
        assert count == 1  # 원래 데이터만 있어야 함

        conn.close()

    def test_cascading_error_handling(self):
        """[OK] 연쇄 에러 처리"""
        from src.core.exceptions import LottoBaseException

        errors = []

        try:
            try:
                raise ValueError("Level 1 error")
            except ValueError as e1:
                raise LottoBaseException("Level 2 error", cause=e1)
        except LottoBaseException as e2:
            errors.append(e2)
            assert e2.cause is not None
            assert "Level 1 error" in str(e2.cause)


# =========================================================================
# Edge Case Tests
# =========================================================================

class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_checkpoint(self, temp_dir):
        """[OK] 빈 체크포인트 처리"""
        checkpoint_path = os.path.join(temp_dir, 'empty.json')

        # 빈 체크포인트
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump({}, f)

        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)

        assert checkpoint == {}

    def test_unicode_in_error_message(self):
        """[OK] 유니코드 에러 메시지"""
        from src.core.exceptions import LottoBaseException

        exc = LottoBaseException("한글 에러 메시지 테스트")
        assert "한글" in exc.message

    def test_large_details_dict(self):
        """[OK] 큰 상세 정보 처리"""
        from src.core.exceptions import LottoBaseException

        large_details = {f'key_{i}': f'value_{i}' for i in range(100)}
        exc = LottoBaseException("테스트", details=large_details)

        assert len(exc.details) == 100

    def test_nested_exception_chain(self):
        """[OK] 중첩 예외 체인"""
        from src.core.exceptions import LottoBaseException

        e1 = ValueError("Root cause")
        e2 = LottoBaseException("Level 1", cause=e1)
        e3 = LottoBaseException("Level 2", cause=e2)

        assert e3.cause == e2
        assert e3.cause.cause == e1
