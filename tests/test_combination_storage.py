#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조합 저장 통합 테스트

Phase 3.10: 중복 조합 저장 통합
- TEXT vs BLOB 저장 테스트
- 인코딩/디코딩 정확성
- 마이그레이션 검증
- 크기 절약 확인
"""

import pytest
import sys
import struct
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.validators import LottoValidator
from src.scripts.migrate_combination_storage import (
    CombinationStorageMigrator,
    CombinationStorageUnifier
)


class TestCombinationEncoding:
    """조합 인코딩/디코딩 테스트"""

    def test_encode_basic(self):
        """기본 인코딩 테스트"""
        numbers = [1, 2, 3, 4, 5, 6]
        bitmap = LottoValidator.encode_combination(numbers)

        assert bitmap > 0
        assert bitmap < (2 ** 45)  # 45비트 이내

    def test_decode_basic(self):
        """기본 디코딩 테스트"""
        numbers = [1, 2, 3, 4, 5, 6]
        bitmap = LottoValidator.encode_combination(numbers)
        decoded = LottoValidator.decode_combination(bitmap)

        assert decoded == numbers

    @pytest.mark.parametrize("numbers", [
        [1, 2, 3, 4, 5, 6],
        [1, 10, 20, 30, 40, 45],
        [7, 14, 21, 28, 35, 42],
        [1, 2, 3, 43, 44, 45],
        [40, 41, 42, 43, 44, 45],
    ])
    def test_encode_decode_roundtrip(self, numbers):
        """인코딩-디코딩 왕복 테스트"""
        bitmap = LottoValidator.encode_combination(numbers)
        decoded = LottoValidator.decode_combination(bitmap)

        assert decoded == sorted(numbers)

    def test_different_combinations_different_bitmaps(self):
        """다른 조합은 다른 비트맵"""
        combo1 = [1, 2, 3, 4, 5, 6]
        combo2 = [1, 2, 3, 4, 5, 7]

        bitmap1 = LottoValidator.encode_combination(combo1)
        bitmap2 = LottoValidator.encode_combination(combo2)

        assert bitmap1 != bitmap2

    def test_order_independence(self):
        """순서와 무관하게 같은 비트맵"""
        combo1 = [1, 2, 3, 4, 5, 6]
        combo2 = [6, 5, 4, 3, 2, 1]

        bitmap1 = LottoValidator.encode_combination(combo1)
        bitmap2 = LottoValidator.encode_combination(combo2)

        assert bitmap1 == bitmap2


class TestCombinationStorageUnifier:
    """저장 통합 API 테스트"""

    def test_encode_to_blob(self):
        """문자열에서 BLOB 변환"""
        combination = "1,2,3,4,5,6"
        blob = CombinationStorageUnifier.encode_to_blob(combination)

        assert isinstance(blob, bytes)
        assert len(blob) == 8

    def test_decode_from_blob(self):
        """BLOB에서 문자열 변환"""
        combination = "1,2,3,4,5,6"
        blob = CombinationStorageUnifier.encode_to_blob(combination)
        decoded = CombinationStorageUnifier.decode_from_blob(blob)

        assert decoded == combination

    @pytest.mark.parametrize("combination", [
        "1,2,3,4,5,6",
        "1,10,20,30,40,45",
        "7,14,21,28,35,42",
        "40,41,42,43,44,45",
    ])
    def test_roundtrip_various_combinations(self, combination):
        """다양한 조합의 왕복 테스트"""
        blob = CombinationStorageUnifier.encode_to_blob(combination)
        decoded = CombinationStorageUnifier.decode_from_blob(blob)

        assert decoded == combination

    def test_encode_batch(self):
        """배치 인코딩 테스트"""
        combinations = ["1,2,3,4,5,6", "7,8,9,10,11,12", "40,41,42,43,44,45"]
        blobs = CombinationStorageUnifier.encode_batch(combinations)

        assert len(blobs) == 3
        assert all(len(b) == 8 for b in blobs)

    def test_decode_batch(self):
        """배치 디코딩 테스트"""
        combinations = ["1,2,3,4,5,6", "7,8,9,10,11,12", "40,41,42,43,44,45"]
        blobs = CombinationStorageUnifier.encode_batch(combinations)
        decoded = CombinationStorageUnifier.decode_batch(blobs)

        assert decoded == combinations


class TestStorageSizeComparison:
    """저장 크기 비교 테스트"""

    def test_text_size(self):
        """TEXT 저장 크기"""
        combinations = [
            "1,2,3,4,5,6",
            "1,10,20,30,40,45",
            "7,14,21,28,35,42",
        ]

        total_size = sum(len(c.encode('utf-8')) for c in combinations)
        avg_size = total_size / len(combinations)

        # 평균 약 15-20 바이트
        assert 10 < avg_size < 25

    def test_blob_size(self):
        """BLOB 저장 크기"""
        combinations = [
            "1,2,3,4,5,6",
            "1,10,20,30,40,45",
            "7,14,21,28,35,42",
        ]

        blobs = CombinationStorageUnifier.encode_batch(combinations)
        total_size = sum(len(b) for b in blobs)
        avg_size = total_size / len(blobs)

        # 고정 8 바이트
        assert avg_size == 8

    def test_size_savings(self):
        """크기 절약량 확인"""
        # 1000개 조합 테스트
        # 주의: random.seed()는 전역 상태를 고정해 이후 실행되는 다른 테스트
        # (예: 대시보드 예측 seed)까지 결정론이 전파되므로 지역 인스턴스를 쓴다.
        test_combos = []
        import random
        rng = random.Random(42)

        for _ in range(1000):
            nums = sorted(rng.sample(range(1, 46), 6))
            test_combos.append(','.join(map(str, nums)))

        text_size = sum(len(c.encode('utf-8')) for c in test_combos)
        blob_size = len(test_combos) * 8  # 고정 8바이트

        savings_percent = ((text_size - blob_size) / text_size) * 100

        # 최소 40% 절약 예상
        assert savings_percent > 40


class TestCombinationStorageMigrator:
    """마이그레이션 테스트"""

    @pytest.fixture
    def temp_db(self):
        """테스트용 임시 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # TEXT 형식 테이블 생성
        cursor.execute('''
            CREATE TABLE combinations_text (
                id INTEGER PRIMARY KEY,
                combination TEXT NOT NULL,
                score REAL
            )
        ''')

        # 테스트 데이터 삽입
        test_data = [
            (1, "1,2,3,4,5,6", 0.5),
            (2, "7,8,9,10,11,12", 0.6),
            (3, "40,41,42,43,44,45", 0.7),
        ]
        cursor.executemany('INSERT INTO combinations_text VALUES (?, ?, ?)', test_data)
        conn.commit()
        conn.close()

        yield db_path

        # Windows 호환성: 임시 파일 정리는 무시
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_analyze_database(self, temp_db):
        """데이터베이스 분석 테스트"""
        migrator = CombinationStorageMigrator()
        migrator.db_paths = [temp_db]

        analysis = migrator.analyze_storage()

        assert len(analysis['databases']) == 1
        db_info = list(analysis['databases'].values())[0]
        assert len(db_info['text_tables']) >= 1
        assert db_info['text_records'] == 3

    def test_migrate_to_blob(self, temp_db):
        """TEXT -> BLOB 마이그레이션 테스트"""
        migrator = CombinationStorageMigrator()

        result = migrator.migrate_to_blob(temp_db, 'combinations_text')

        assert result['success'] == True
        assert result['records_migrated'] == 3

        # 새 테이블 확인
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM combinations_text_blob")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3

    def test_verify_migration(self, temp_db):
        """마이그레이션 검증 테스트"""
        migrator = CombinationStorageMigrator()

        # 마이그레이션 실행
        migrator.migrate_to_blob(temp_db, 'combinations_text')

        # 직접 검증 (테이블에서 BLOB 데이터 조회 후 디코딩)
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()

        # 원본 데이터 조회
        cursor.execute("SELECT combination FROM combinations_text ORDER BY id")
        original_combos = [row[0] for row in cursor.fetchall()]

        # 마이그레이션된 데이터 조회 및 디코딩
        cursor.execute("SELECT combination_blob FROM combinations_text_blob")
        migrated_rows = cursor.fetchall()

        decoded_combos = []
        for row in migrated_rows:
            blob = row[0]
            bitmap = struct.unpack('<Q', blob)[0]
            numbers = LottoValidator.decode_combination(bitmap)
            decoded_combos.append(','.join(map(str, numbers)))

        conn.close()

        # 정렬 후 비교 (순서가 다를 수 있으므로)
        assert sorted(original_combos) == sorted(decoded_combos)
        assert len(decoded_combos) == 3


class TestBlobStorageIntegrity:
    """BLOB 저장 무결성 테스트"""

    def test_struct_packing(self):
        """구조체 패킹 일관성"""
        numbers = [1, 2, 3, 4, 5, 6]
        bitmap = LottoValidator.encode_combination(numbers)

        # 리틀 엔디안 패킹
        packed = struct.pack('<Q', bitmap)
        unpacked = struct.unpack('<Q', packed)[0]

        assert unpacked == bitmap

    def test_max_bitmap_value(self):
        """최대 비트맵 값 테스트"""
        # 최대값: 40-45번이 모두 1인 경우
        numbers = [40, 41, 42, 43, 44, 45]
        bitmap = LottoValidator.encode_combination(numbers)

        # 8바이트(64비트)로 충분히 저장 가능
        packed = struct.pack('<Q', bitmap)
        assert len(packed) == 8

    def test_blob_uniqueness(self):
        """BLOB 고유성 테스트"""
        combos = [
            [1, 2, 3, 4, 5, 6],
            [1, 2, 3, 4, 5, 7],
            [2, 3, 4, 5, 6, 7],
        ]

        blobs = []
        for combo in combos:
            bitmap = LottoValidator.encode_combination(combo)
            blob = struct.pack('<Q', bitmap)
            blobs.append(blob)

        # 모든 BLOB이 고유해야 함
        assert len(set(blobs)) == len(blobs)


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_min_numbers(self):
        """최소 번호 조합"""
        numbers = [1, 2, 3, 4, 5, 6]
        blob = CombinationStorageUnifier.encode_to_blob(','.join(map(str, numbers)))
        decoded = CombinationStorageUnifier.decode_from_blob(blob)

        assert decoded == "1,2,3,4,5,6"

    def test_max_numbers(self):
        """최대 번호 조합"""
        numbers = [40, 41, 42, 43, 44, 45]
        blob = CombinationStorageUnifier.encode_to_blob(','.join(map(str, numbers)))
        decoded = CombinationStorageUnifier.decode_from_blob(blob)

        assert decoded == "40,41,42,43,44,45"

    def test_spread_numbers(self):
        """넓게 퍼진 번호"""
        numbers = [1, 10, 20, 30, 40, 45]
        blob = CombinationStorageUnifier.encode_to_blob(','.join(map(str, numbers)))
        decoded = CombinationStorageUnifier.decode_from_blob(blob)

        assert decoded == "1,10,20,30,40,45"


class TestDatabaseOperations:
    """데이터베이스 작업 테스트"""

    @pytest.fixture
    def temp_db(self):
        """테스트용 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test_ops.db'
        yield db_path

        # Windows 호환성: 임시 파일 정리
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_blob_insert_select(self, temp_db):
        """BLOB 삽입 및 조회"""
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE test_blob (
                id INTEGER PRIMARY KEY,
                combination_blob BLOB NOT NULL
            )
        ''')

        # 삽입
        combo = "1,2,3,4,5,6"
        blob = CombinationStorageUnifier.encode_to_blob(combo)
        cursor.execute('INSERT INTO test_blob VALUES (?, ?)', (1, blob))
        conn.commit()

        # 조회
        cursor.execute('SELECT combination_blob FROM test_blob WHERE id = 1')
        result = cursor.fetchone()[0]
        decoded = CombinationStorageUnifier.decode_from_blob(result)

        conn.close()

        assert decoded == combo

    def test_blob_index_usage(self, temp_db):
        """BLOB 인덱스 사용 테스트"""
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE test_blob (
                id INTEGER PRIMARY KEY,
                combination_blob BLOB NOT NULL UNIQUE
            )
        ''')
        cursor.execute('CREATE INDEX idx_blob ON test_blob(combination_blob)')

        # 대량 삽입 (전역 random.seed 금지 - 다른 테스트로 결정론 전파 방지)
        import random
        rng = random.Random(42)

        for i in range(1000):
            nums = sorted(rng.sample(range(1, 46), 6))
            combo = ','.join(map(str, nums))
            blob = CombinationStorageUnifier.encode_to_blob(combo)
            try:
                cursor.execute('INSERT INTO test_blob VALUES (?, ?)', (i, blob))
            except sqlite3.IntegrityError:
                pass  # 중복 무시

        conn.commit()

        # 인덱스 사용 확인
        target_combo = "1,2,3,4,5,6"
        target_blob = CombinationStorageUnifier.encode_to_blob(target_combo)

        cursor.execute('''
            EXPLAIN QUERY PLAN
            SELECT id FROM test_blob WHERE combination_blob = ?
        ''', (target_blob,))

        # 전체 계획 가져오기
        plan_rows = cursor.fetchall()
        plan_str = ' '.join(str(row) for row in plan_rows)
        conn.close()

        # 인덱스 또는 UNIQUE 제약조건 사용 확인
        # SQLite는 UNIQUE 제약조건에 자동으로 인덱스를 생성하므로
        # SEARCH 또는 INDEX 또는 USING을 확인
        assert any(keyword in plan_str.upper() for keyword in ['INDEX', 'SEARCH', 'USING'])


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
