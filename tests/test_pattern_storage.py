#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
패턴 저장소 마이그레이션 테스트

Phase 3.7: JSON 패턴 저장 → 컬럼 마이그레이션
- 스키마 분석 테스트
- 컬럼 추가 테스트
- 인덱스 생성 테스트
- 요약 데이터 추출 테스트
- 쿼리 최적화 테스트
"""

import json
import pytest
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scripts.migrate_pattern_storage import (
    PatternStorageMigrator,
    PatternQueryOptimizer
)


class TestPatternStorageMigrator:
    """패턴 저장소 마이그레이터 테스트"""

    @pytest.fixture
    def temp_db(self):
        """테스트용 임시 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test_patterns.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 패턴 분석 테이블 생성 (JSON 컬럼 포함)
        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT NOT NULL,
                odd_even_patterns TEXT NOT NULL,
                consecutive_patterns TEXT NOT NULL,
                sum_range_patterns TEXT,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 테스트 데이터 삽입
        test_data = [
            (1, json.dumps({0: 5.0, 1: 15.0, 2: 30.0, 3: 35.0, 4: 12.0, 5: 2.5, 6: 0.5}),
             json.dumps({'odd': {3: 32.5, 4: 25.0, 2: 20.0}, 'even': {3: 32.5, 2: 25.0, 4: 20.0}}),
             json.dumps({1: 65.0, 2: 25.0, 3: 8.0, 4: 1.5, 5: 0.4, 6: 0.1}),
             json.dumps({"21-60": 2.5, "61-100": 25.0, "101-140": 45.0, "141-180": 25.0, "181-220": 2.5})),
            (2, json.dumps({0: 4.5, 1: 14.5, 2: 31.0, 3: 34.0, 4: 13.0, 5: 2.3, 6: 0.7}),
             json.dumps({'odd': {3: 33.0, 4: 24.0, 2: 21.0}, 'even': {3: 33.0, 2: 24.0, 4: 21.0}}),
             json.dumps({1: 64.0, 2: 26.0, 3: 7.5, 4: 2.0, 5: 0.3, 6: 0.2}),
             json.dumps({"21-60": 3.0, "61-100": 24.0, "101-140": 46.0, "141-180": 24.0, "181-220": 3.0})),
            (3, json.dumps({0: 5.5, 1: 16.0, 2: 29.0, 3: 36.0, 4: 11.0, 5: 2.0, 6: 0.5}),
             json.dumps({'odd': {3: 31.0, 4: 26.0, 2: 19.0}, 'even': {3: 31.0, 2: 26.0, 4: 19.0}}),
             json.dumps({1: 66.0, 2: 24.0, 3: 8.5, 4: 1.0, 5: 0.4, 6: 0.1}),
             json.dumps({"21-60": 2.0, "61-100": 26.0, "101-140": 44.0, "141-180": 26.0, "181-220": 2.0})),
        ]

        cursor.executemany('''
            INSERT INTO pattern_analysis (round, number_match_patterns, odd_even_patterns,
                                         consecutive_patterns, sum_range_patterns)
            VALUES (?, ?, ?, ?, ?)
        ''', test_data)
        conn.commit()
        conn.close()

        yield db_path

        # Windows 호환성: 임시 파일 정리
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_analyze_current_schema(self, temp_db):
        """스키마 분석 테스트"""
        migrator = PatternStorageMigrator(temp_db)
        analysis = migrator.analyze_current_schema()

        assert analysis['db_exists'] == True
        assert analysis['table_exists'] == True
        assert analysis['row_count'] == 3
        assert 'number_match_patterns' in analysis['json_columns']
        assert 'odd_even_patterns' in analysis['json_columns']
        assert 'consecutive_patterns' in analysis['json_columns']

    def test_analyze_missing_summary_columns(self, temp_db):
        """누락된 요약 컬럼 분석 테스트"""
        migrator = PatternStorageMigrator(temp_db)
        analysis = migrator.analyze_current_schema()

        # 요약 컬럼이 아직 없어야 함
        assert 'min_probability' in analysis['missing_summary_columns']
        assert 'max_probability' in analysis['missing_summary_columns']
        assert 'total_pattern_count' in analysis['missing_summary_columns']

    def test_add_summary_columns(self, temp_db):
        """요약 컬럼 추가 테스트"""
        migrator = PatternStorageMigrator(temp_db)
        result = migrator.add_summary_columns()

        assert result['success'] == True
        assert 'min_probability' in result['columns_added']
        assert 'max_probability' in result['columns_added']

        # 컬럼 존재 확인
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(pattern_analysis)")
        columns = {col[1] for col in cursor.fetchall()}
        conn.close()

        assert 'min_probability' in columns
        assert 'max_probability' in columns
        assert 'total_pattern_count' in columns

    def test_add_summary_columns_idempotent(self, temp_db):
        """컬럼 추가 멱등성 테스트 (중복 실행)"""
        migrator = PatternStorageMigrator(temp_db)

        # 첫 번째 실행
        result1 = migrator.add_summary_columns()
        assert result1['success'] == True
        added_count = len(result1['columns_added'])

        # 두 번째 실행 - 이미 존재하는 컬럼은 스킵되어야 함
        result2 = migrator.add_summary_columns()
        assert result2['success'] == True
        assert len(result2['columns_skipped']) == added_count
        assert len(result2['columns_added']) == 0

    def test_create_indexes(self, temp_db):
        """인덱스 생성 테스트"""
        migrator = PatternStorageMigrator(temp_db)

        # 먼저 컬럼 추가
        migrator.add_summary_columns()

        # 인덱스 생성
        result = migrator.create_indexes()

        assert result['success'] == True
        assert len(result['indexes_created']) > 0

        # 인덱스 존재 확인
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='pattern_analysis'
        """)
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert 'idx_pattern_round' in indexes
        assert 'idx_pattern_analyzed_at' in indexes

    def test_create_indexes_idempotent(self, temp_db):
        """인덱스 생성 멱등성 테스트"""
        migrator = PatternStorageMigrator(temp_db)
        migrator.add_summary_columns()

        # 첫 번째 실행
        result1 = migrator.create_indexes()
        assert result1['success'] == True
        created_count = len(result1['indexes_created'])

        # 두 번째 실행
        result2 = migrator.create_indexes()
        assert result2['success'] == True
        assert len(result2['indexes_skipped']) >= created_count


class TestJsonSummaryExtraction:
    """JSON 요약 추출 테스트"""

    def test_extract_summary_simple(self):
        """단순 JSON에서 요약 추출"""
        migrator = PatternStorageMigrator()
        json_data = json.dumps({0: 5.0, 1: 15.0, 2: 30.0, 3: 35.0, 4: 12.0, 5: 2.5, 6: 0.5})

        summary = migrator.extract_summary_from_json(json_data)

        assert summary['min_probability'] == 0.5
        assert summary['max_probability'] == 35.0
        assert summary['pattern_count'] == 7
        assert summary['has_low_prob'] == True  # 0.5 < 1.0

    def test_extract_summary_nested(self):
        """중첩 JSON에서 요약 추출"""
        migrator = PatternStorageMigrator()
        json_data = json.dumps({
            'odd': {3: 32.5, 4: 25.0, 2: 20.0},
            'even': {3: 32.5, 2: 25.0, 4: 20.0}
        })

        summary = migrator.extract_summary_from_json(json_data)

        assert summary['min_probability'] == 20.0
        assert summary['max_probability'] == 32.5
        assert summary['pattern_count'] == 6
        assert summary['has_low_prob'] == False  # 모든 값 >= 1.0

    def test_extract_summary_empty(self):
        """빈 JSON에서 요약 추출"""
        migrator = PatternStorageMigrator()
        summary = migrator.extract_summary_from_json("{}")

        assert summary['min_probability'] is None
        assert summary['max_probability'] is None
        assert summary['pattern_count'] == 0
        assert summary['has_low_prob'] == False

    def test_extract_summary_none(self):
        """None 입력에서 요약 추출"""
        migrator = PatternStorageMigrator()
        summary = migrator.extract_summary_from_json(None)

        assert summary['min_probability'] is None
        assert summary['pattern_count'] == 0

    def test_extract_summary_invalid_json(self):
        """잘못된 JSON에서 요약 추출"""
        migrator = PatternStorageMigrator()
        summary = migrator.extract_summary_from_json("not valid json")

        assert summary['min_probability'] is None
        assert summary['pattern_count'] == 0


class TestPopulateSummaryColumns:
    """요약 컬럼 데이터 채우기 테스트"""

    @pytest.fixture
    def temp_db_with_columns(self):
        """요약 컬럼이 추가된 임시 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test_patterns.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT NOT NULL,
                odd_even_patterns TEXT NOT NULL,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 테스트 데이터 삽입
        test_data = [
            (1, json.dumps({0: 5.0, 1: 15.0, 2: 30.0, 6: 0.5}),
             json.dumps({'odd': {3: 32.5}, 'even': {3: 32.5}})),
            (2, json.dumps({0: 4.5, 1: 14.5, 2: 31.0, 6: 0.3}),
             json.dumps({'odd': {3: 33.0}, 'even': {3: 33.0}})),
        ]

        cursor.executemany('''
            INSERT INTO pattern_analysis (round, number_match_patterns, odd_even_patterns)
            VALUES (?, ?, ?)
        ''', test_data)
        conn.commit()
        conn.close()

        yield db_path

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_populate_summary_columns(self, temp_db_with_columns):
        """요약 컬럼 데이터 채우기"""
        migrator = PatternStorageMigrator(temp_db_with_columns)

        # 컬럼 추가
        migrator.add_summary_columns()

        # 데이터 채우기
        result = migrator.populate_summary_columns()

        assert result['success'] == True
        assert result['rows_updated'] == 2

        # 데이터 확인
        conn = sqlite3.connect(str(temp_db_with_columns))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT round, min_probability, max_probability, total_pattern_count, has_low_prob_patterns
            FROM pattern_analysis
            ORDER BY round
        """)
        rows = cursor.fetchall()
        conn.close()

        # round 1 확인
        assert rows[0][0] == 1  # round
        assert rows[0][1] == 0.5  # min_probability (0.5 from match patterns)
        assert rows[0][4] == 1  # has_low_prob_patterns

        # round 2 확인
        assert rows[1][0] == 2
        assert rows[1][1] == 0.3  # min_probability


class TestFullMigration:
    """전체 마이그레이션 테스트"""

    @pytest.fixture
    def temp_db(self):
        """테스트용 임시 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test_patterns.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT NOT NULL,
                odd_even_patterns TEXT NOT NULL,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        test_data = [
            (1, json.dumps({0: 5.0, 1: 15.0}), json.dumps({'odd': {3: 32.5}})),
            (2, json.dumps({0: 4.5, 6: 0.5}), json.dumps({'even': {3: 33.0}})),
        ]

        cursor.executemany('''
            INSERT INTO pattern_analysis (round, number_match_patterns, odd_even_patterns)
            VALUES (?, ?, ?)
        ''', test_data)
        conn.commit()
        conn.close()

        yield db_path

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_run_full_migration(self, temp_db):
        """전체 마이그레이션 실행"""
        migrator = PatternStorageMigrator(temp_db)
        result = migrator.run_full_migration(dry_run=False)

        assert result['success'] == True
        assert result['dry_run'] == False
        assert result['schema_analysis'] is not None
        assert result['columns_result']['success'] == True
        assert result['indexes_result']['success'] == True
        assert result['populate_result']['success'] == True

    def test_run_dry_run(self, temp_db):
        """Dry run 테스트"""
        migrator = PatternStorageMigrator(temp_db)
        result = migrator.run_full_migration(dry_run=True)

        assert result['success'] == True
        assert result['dry_run'] == True

        # 실제 변경이 없어야 함
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(pattern_analysis)")
        columns = {col[1] for col in cursor.fetchall()}
        conn.close()

        assert 'min_probability' not in columns  # 컬럼이 추가되지 않아야 함


class TestPatternQueryOptimizer:
    """패턴 쿼리 최적화 테스트"""

    @pytest.fixture
    def migrated_db(self):
        """마이그레이션 완료된 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'test_patterns.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT NOT NULL,
                odd_even_patterns TEXT NOT NULL,
                min_probability REAL,
                max_probability REAL,
                total_pattern_count INTEGER DEFAULT 0,
                has_low_prob_patterns INTEGER DEFAULT 0,
                schema_version INTEGER DEFAULT 2,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 인덱스 생성
        cursor.execute("CREATE INDEX idx_pattern_has_low_prob ON pattern_analysis(has_low_prob_patterns)")
        cursor.execute("CREATE INDEX idx_pattern_min_prob ON pattern_analysis(min_probability)")

        # 테스트 데이터
        test_data = [
            (1, json.dumps({0: 5.0}), json.dumps({}), 0.5, 5.0, 2, 1, 2),
            (2, json.dumps({1: 15.0}), json.dumps({}), 1.5, 15.0, 2, 0, 2),
            (3, json.dumps({2: 30.0}), json.dumps({}), 0.3, 30.0, 2, 1, 2),
        ]

        cursor.executemany('''
            INSERT INTO pattern_analysis (round, number_match_patterns, odd_even_patterns,
                                         min_probability, max_probability, total_pattern_count,
                                         has_low_prob_patterns, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', test_data)
        conn.commit()
        conn.close()

        yield db_path

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_get_patterns_with_low_probability(self, migrated_db):
        """낮은 확률 패턴 조회"""
        results = PatternQueryOptimizer.get_patterns_with_low_probability(
            migrated_db, threshold=1.0
        )

        # round 1 (0.5)과 round 3 (0.3)이 해당
        assert len(results) == 2
        rounds = [r[0] for r in results]
        assert 1 in rounds
        assert 3 in rounds
        assert 2 not in rounds  # 1.5 >= 1.0 이므로 제외

    def test_get_pattern_statistics_summary(self, migrated_db):
        """패턴 통계 요약 조회"""
        summary = PatternQueryOptimizer.get_pattern_statistics_summary(migrated_db)

        assert summary['total_rounds'] == 3
        assert summary['rounds_with_low_prob'] == 2
        assert summary['avg_pattern_count'] == 2.0


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_nonexistent_db(self):
        """존재하지 않는 DB"""
        migrator = PatternStorageMigrator(Path('/nonexistent/path.db'))
        analysis = migrator.analyze_current_schema()

        assert analysis['db_exists'] == False
        assert analysis['table_exists'] == False

    def test_empty_table(self):
        """빈 테이블"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'empty.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT
            )
        ''')
        conn.commit()
        conn.close()

        try:
            migrator = PatternStorageMigrator(db_path)
            result = migrator.run_full_migration()

            assert result['success'] == True
            assert result['populate_result']['rows_updated'] == 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_table_without_json_columns(self):
        """JSON 컬럼이 없는 테이블"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'no_json.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                analyzed_at TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

        try:
            migrator = PatternStorageMigrator(db_path)
            analysis = migrator.analyze_current_schema()

            assert analysis['table_exists'] == True
            assert len(analysis['json_columns']) == 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestQueryPerformance:
    """쿼리 성능 테스트"""

    @pytest.fixture
    def large_db(self):
        """대용량 테스트 데이터베이스"""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / 'large_patterns.db'

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE pattern_analysis (
                round INTEGER PRIMARY KEY,
                number_match_patterns TEXT NOT NULL,
                min_probability REAL,
                max_probability REAL,
                total_pattern_count INTEGER DEFAULT 0,
                has_low_prob_patterns INTEGER DEFAULT 0,
                schema_version INTEGER DEFAULT 2,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 1000개 행 삽입 (전역 random.seed 금지 - 다른 테스트로 결정론 전파 방지)
        test_data = []
        import random
        rng = random.Random(42)

        for i in range(1000):
            min_prob = rng.uniform(0.1, 10.0)
            max_prob = rng.uniform(min_prob, 50.0)
            has_low = 1 if min_prob < 1.0 else 0

            test_data.append((
                i + 1,
                json.dumps({j: rng.uniform(0, 50) for j in range(7)}),
                min_prob,
                max_prob,
                7,
                has_low,
                2
            ))

        cursor.executemany('''
            INSERT INTO pattern_analysis (round, number_match_patterns,
                                         min_probability, max_probability,
                                         total_pattern_count, has_low_prob_patterns,
                                         schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', test_data)

        # 인덱스 생성
        cursor.execute("CREATE INDEX idx_has_low ON pattern_analysis(has_low_prob_patterns)")
        cursor.execute("CREATE INDEX idx_min_prob ON pattern_analysis(min_probability)")

        conn.commit()
        conn.close()

        yield db_path

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_query_uses_index(self, large_db):
        """쿼리가 인덱스를 사용하는지 확인"""
        conn = sqlite3.connect(str(large_db))
        cursor = conn.cursor()

        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT round, min_probability
            FROM pattern_analysis
            WHERE has_low_prob_patterns = 1
              AND min_probability < 1.0
        """)

        plan_rows = cursor.fetchall()
        plan_str = ' '.join(str(row) for row in plan_rows)
        conn.close()

        # 인덱스 사용 확인
        assert any(keyword in plan_str.upper() for keyword in ['INDEX', 'SEARCH', 'USING'])

    def test_query_performance_with_index(self, large_db):
        """인덱스를 사용한 쿼리 성능"""
        import time

        conn = sqlite3.connect(str(large_db))
        cursor = conn.cursor()

        # 인덱스 사용 쿼리
        start = time.time()
        cursor.execute("""
            SELECT round, min_probability
            FROM pattern_analysis
            WHERE has_low_prob_patterns = 1
            ORDER BY round DESC
            LIMIT 100
        """)
        results = cursor.fetchall()
        indexed_time = time.time() - start

        conn.close()

        # 인덱스 사용 쿼리는 빠르게 실행되어야 함
        assert indexed_time < 0.1  # 100ms 이내
        assert len(results) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
