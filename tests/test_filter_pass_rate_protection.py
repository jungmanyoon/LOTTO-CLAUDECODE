#!/usr/bin/env python3
"""
필터 통과율 보호 시스템 테스트

이 테스트는 다음을 검증합니다:
1. PerformanceMetrics에 filter_pass_rate 필드 추가
2. filter_criteria_snapshots 테이블 생성
3. 필터 조건 스냅샷 저장/조회 기능
4. 최고 필터 통과율 조회 기능
5. rollback_to_best_pass_rate() 함수 동작
"""

import pytest
import os
import sqlite3
import yaml
import tempfile
import shutil
from datetime import datetime

# 테스트용 임포트
from src.core.continuous_improvement_engine import (
    PerformanceMetrics,
    PerformanceTracker,
    ContinuousImprovementEngine
)


class TestFilterPassRateProtection:
    """필터 통과율 보호 시스템 테스트"""

    @pytest.fixture
    def temp_db(self):
        """임시 데이터베이스 생성"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_continuous_improvement.db")
        yield db_path
        # 정리
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def tracker(self, temp_db):
        """PerformanceTracker 인스턴스 생성"""
        return PerformanceTracker(db_path=temp_db)

    def test_performance_metrics_has_filter_pass_rate(self):
        """✅ TEST 1: PerformanceMetrics에 filter_pass_rate 필드가 있는지 확인"""
        metrics = PerformanceMetrics(
            avg_matches=1.5,
            best_match=4,
            accuracy_3plus=0.3,
            ml_inclusion_rate=0.15,
            combination_count=300000,
            threshold=1.4,
            ml_bypass_filters=12,
            ml_weight=0.5,
            filter_pass_rate=82.5,  # ✅ 새 필드
            timestamp=datetime.now()
        )

        assert hasattr(metrics, 'filter_pass_rate'), "filter_pass_rate 필드가 없습니다"
        assert metrics.filter_pass_rate == 82.5, "filter_pass_rate 값이 올바르지 않습니다"
        print("[O] TEST 1 통과: PerformanceMetrics.filter_pass_rate 필드 존재")

    def test_database_schema_has_filter_pass_rate_column(self, tracker):
        """✅ TEST 2: performance_history 테이블에 filter_pass_rate 컬럼이 있는지 확인"""
        with sqlite3.connect(tracker.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(performance_history)")
            columns = [row[1] for row in cursor.fetchall()]

            assert 'filter_pass_rate' in columns, "filter_pass_rate 컬럼이 없습니다"
            assert 'is_best_pass_rate' in columns, "is_best_pass_rate 컬럼이 없습니다"

        print("[O] TEST 2 통과: performance_history 테이블에 필드 존재")

    def test_filter_criteria_snapshots_table_exists(self, tracker):
        """✅ TEST 3: filter_criteria_snapshots 테이블이 생성되었는지 확인"""
        with sqlite3.connect(tracker.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='filter_criteria_snapshots'
            """)
            result = cursor.fetchone()

            assert result is not None, "filter_criteria_snapshots 테이블이 없습니다"

        print("[O] TEST 3 통과: filter_criteria_snapshots 테이블 존재")

    def test_save_and_retrieve_performance_with_pass_rate(self, tracker):
        """✅ TEST 4: filter_pass_rate 포함 성능 데이터 저장 및 조회"""
        metrics = PerformanceMetrics(
            avg_matches=1.5,
            best_match=4,
            accuracy_3plus=0.3,
            ml_inclusion_rate=0.15,
            combination_count=300000,
            threshold=1.4,
            ml_bypass_filters=12,
            ml_weight=0.5,
            filter_pass_rate=85.0,
            timestamp=datetime.now()
        )

        # 저장
        record_id = tracker.save_performance_result(metrics, round_number=1183)

        # 조회
        with sqlite3.connect(tracker.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filter_pass_rate, is_best_pass_rate FROM performance_history WHERE id = ?", (record_id,))
            row = cursor.fetchone()

            assert row is not None, "저장된 기록을 찾을 수 없습니다"
            assert row[0] == 85.0, f"filter_pass_rate가 올바르지 않습니다: {row[0]}"
            assert row[1] == 1, "is_best_pass_rate가 True여야 합니다"  # 첫 번째 기록은 best

        print("[O] TEST 4 통과: filter_pass_rate 저장 및 조회 성공")

    def test_best_pass_rate_tracking(self, tracker):
        """✅ TEST 5: 최고 필터 통과율 추적 기능 테스트"""
        # 여러 성능 기록 저장
        records = [
            (1.5, 80.0),  # avg_matches, filter_pass_rate
            (1.6, 85.0),  # ← 최고 통과율
            (1.7, 82.0),
        ]

        for avg_matches, pass_rate in records:
            metrics = PerformanceMetrics(
                avg_matches=avg_matches,
                best_match=4,
                accuracy_3plus=0.3,
                ml_inclusion_rate=0.15,
                combination_count=300000,
                threshold=1.4,
                ml_bypass_filters=12,
                ml_weight=0.5,
                filter_pass_rate=pass_rate,
                timestamp=datetime.now()
            )
            tracker.save_performance_result(metrics)

        # 최고 통과율 조회
        best_pass_rate_perf = tracker.get_best_pass_rate_performance()

        assert best_pass_rate_perf is not None, "최고 통과율 기록을 찾을 수 없습니다"
        assert best_pass_rate_perf.filter_pass_rate == 85.0, f"최고 통과율이 올바르지 않습니다: {best_pass_rate_perf.filter_pass_rate}"
        assert best_pass_rate_perf.avg_matches == 1.6, "최고 통과율 기록의 avg_matches가 올바르지 않습니다"

        print("[O] TEST 5 통과: 최고 필터 통과율 추적 성공")

    def test_filter_criteria_snapshot_save_and_retrieve(self, tracker):
        """✅ TEST 6: 필터 조건 스냅샷 저장 및 조회 테스트"""
        # 성능 기록 저장
        metrics = PerformanceMetrics(
            avg_matches=1.5,
            best_match=4,
            accuracy_3plus=0.3,
            ml_inclusion_rate=0.15,
            combination_count=300000,
            threshold=1.4,
            ml_bypass_filters=12,
            ml_weight=0.5,
            filter_pass_rate=85.0,
            timestamp=datetime.now()
        )
        performance_history_id = tracker.save_performance_result(metrics)

        # 필터 조건 스냅샷 저장
        filter_criteria = {
            'match': {'max_match': 3},
            'multiple': {'global_threshold': 1.5},
            'ten_section': {'max_empty_sections': 2}
        }

        tracker.save_filter_criteria_snapshot(
            performance_history_id=performance_history_id,
            filter_criteria=filter_criteria,
            filter_pass_rate=85.0
        )

        # 스냅샷 조회
        retrieved_criteria = tracker.get_filter_criteria_snapshot(performance_history_id)

        assert retrieved_criteria is not None, "필터 조건 스냅샷을 찾을 수 없습니다"
        assert 'match' in retrieved_criteria, "match 필터가 스냅샷에 없습니다"
        assert retrieved_criteria['match']['max_match'] == 3, "max_match 값이 올바르지 않습니다"
        assert len(retrieved_criteria) == 3, f"필터 개수가 올바르지 않습니다: {len(retrieved_criteria)}"

        print("[O] TEST 6 통과: 필터 조건 스냅샷 저장/조회 성공")

    def test_is_best_pass_rate_flag_update(self, tracker):
        """✅ TEST 7: is_best_pass_rate 플래그 업데이트 테스트"""
        # 첫 번째 기록 (80%)
        metrics1 = PerformanceMetrics(
            avg_matches=1.5, best_match=4, accuracy_3plus=0.3,
            ml_inclusion_rate=0.15, combination_count=300000,
            threshold=1.4, ml_bypass_filters=12, ml_weight=0.5,
            filter_pass_rate=80.0, timestamp=datetime.now()
        )
        id1 = tracker.save_performance_result(metrics1)

        # 두 번째 기록 (85%) - 더 높은 통과율
        metrics2 = PerformanceMetrics(
            avg_matches=1.5, best_match=4, accuracy_3plus=0.3,
            ml_inclusion_rate=0.15, combination_count=300000,
            threshold=1.4, ml_bypass_filters=12, ml_weight=0.5,
            filter_pass_rate=85.0, timestamp=datetime.now()
        )
        id2 = tracker.save_performance_result(metrics2)

        # 플래그 확인
        with sqlite3.connect(tracker.db_path) as conn:
            cursor = conn.cursor()

            # 첫 번째 기록의 플래그는 FALSE여야 함
            cursor.execute("SELECT is_best_pass_rate FROM performance_history WHERE id = ?", (id1,))
            assert cursor.fetchone()[0] == 0, "첫 번째 기록의 is_best_pass_rate가 False여야 합니다"

            # 두 번째 기록의 플래그는 TRUE여야 함
            cursor.execute("SELECT is_best_pass_rate FROM performance_history WHERE id = ?", (id2,))
            assert cursor.fetchone()[0] == 1, "두 번째 기록의 is_best_pass_rate가 True여야 합니다"

        print("[O] TEST 7 통과: is_best_pass_rate 플래그 업데이트 성공")


def main():
    """테스트 실행"""
    print("="*60)
    print("필터 통과율 보호 시스템 테스트 시작")
    print("="*60)

    # pytest 실행
    pytest.main([__file__, '-v', '--tb=short'])

    print("\n" + "="*60)
    print("모든 테스트 완료")
    print("="*60)


if __name__ == "__main__":
    main()
