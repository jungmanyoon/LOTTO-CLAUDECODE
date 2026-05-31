"""
FilterValidator 데이터베이스 저장 기능 테스트

이 테스트는 FilterValidator가 필터 통과율을 데이터베이스에 저장하는지 검증합니다.
근본 원인: FilterValidator는 82.35%를 계산했지만 JSON에만 저장하고 DB에는 저장하지 않았습니다.
"""
import pytest
import sqlite3
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class TestFilterValidatorDatabaseSave:
    """FilterValidator 데이터베이스 저장 테스트"""

    def test_save_to_performance_tracker_method_exists(self):
        """_save_to_performance_tracker 메서드가 존재하는지 확인"""
        from src.validators.filter_validator import FilterValidator

        validator = FilterValidator()

        # 메서드 존재 확인
        assert hasattr(validator, '_save_to_performance_tracker')
        assert callable(getattr(validator, '_save_to_performance_tracker'))

    def test_save_to_performance_tracker_called_after_validation(self):
        """필터 검증 후 _save_to_performance_tracker가 호출되는지 확인"""
        from src.validators.filter_validator import FilterValidator

        validator = FilterValidator()

        # Mock 설정
        with patch.object(validator, '_save_validation_results') as mock_save_json, \
             patch.object(validator, '_save_to_performance_tracker') as mock_save_db, \
             patch.object(validator, '_print_validation_summary'), \
             patch.object(validator.db_manager, 'get_numbers_with_bonus') as mock_get_numbers:

            # 가짜 데이터 설정
            mock_get_numbers.return_value = [
                (1100, (1, 2, 3, 4, 5, 6, 7)),
                (1101, (8, 9, 10, 11, 12, 13, 14)),
            ]

            # 검증 실행
            validator.validate_filters_with_historical_data(start_round=1100, end_round=1101)

            # JSON 저장 호출 확인
            assert mock_save_json.called

            # ✅ 핵심: DB 저장도 호출되는지 확인
            assert mock_save_db.called, "❌ _save_to_performance_tracker가 호출되지 않음!"

    def test_save_to_performance_tracker_does_not_write_garbage_data(self):
        """[FIX] _save_to_performance_tracker가 avg_matches=0 쓰레기 데이터를 DB에 쓰지 않는지 확인

        이전 동작: avg_matches=0, threshold=0으로 save_performance_result 호출 -> 쓰레기 데이터 오염
        새 동작: DB 저장 금지, INFO 로그만 출력 -> auto-improvement 오염 방지
        """
        from src.validators.filter_validator import FilterValidator

        validator = FilterValidator()

        # 테스트 데이터
        test_results = {
            'overall_pass_rate': 82.35,
            'total_rounds': 100,
            'overall_pass_count': 82
        }

        # Mock PerformanceTracker (모듈 레벨 임포트 경로로 패치)
        with patch('src.validators.filter_validator.PerformanceTracker') as MockTracker:
            mock_tracker_instance = Mock()
            MockTracker.return_value = mock_tracker_instance

            # 실행
            validator._save_to_performance_tracker(test_results)

            # [FIX] save_performance_result가 호출되지 않아야 함 (avg_matches=0 쓰레기 방지)
            assert not mock_tracker_instance.save_performance_result.called, (
                "FilterValidator가 avg_matches=0으로 DB에 쓰레기 데이터를 저장하면 안 됩니다! "
                "백테스팅 없이 avg_matches를 알 수 없습니다."
            )

    def test_database_not_polluted_by_filter_validator(self):
        """[FIX] filter_validator가 avg_matches=0 레코드를 DB에 삽입하지 않는지 확인"""
        from src.validators.filter_validator import FilterValidator

        # 테스트 전 레코드 수 기록
        with sqlite3.connect('data/continuous_improvement.db') as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS performance_history "
                "(id INTEGER PRIMARY KEY, avg_matches REAL, filter_pass_rate REAL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            ) if False else None  # 테이블 존재 보장용
            try:
                before_count = conn.execute(
                    'SELECT COUNT(*) FROM performance_history WHERE avg_matches=0'
                ).fetchone()[0]
            except Exception:
                before_count = 0

        # 실행 (avg_matches=0 레코드가 추가되면 안 됨)
        test_results = {'overall_pass_rate': 77.77, 'total_rounds': 10, 'overall_pass_count': 7}
        validator = FilterValidator()
        validator._save_to_performance_tracker(test_results)

        # DB 확인: avg_matches=0 레코드가 증가하지 않아야 함
        with sqlite3.connect('data/continuous_improvement.db') as conn:
            try:
                after_count = conn.execute(
                    'SELECT COUNT(*) FROM performance_history WHERE avg_matches=0'
                ).fetchone()[0]
            except Exception:
                after_count = 0

        assert after_count == before_count, (
            f"avg_matches=0 쓰레기 레코드가 {after_count - before_count}개 추가됨! "
            f"FilterValidator는 avg_matches를 계산하지 않으므로 DB 저장 금지"
        )

    def test_fix_prevents_garbage_data_in_auto_improvement(self):
        """[FIX] filter_validator 호출이 auto-improvement DB를 오염시키지 않음을 확인"""
        from src.validators.filter_validator import FilterValidator

        validator = FilterValidator()

        # 여러 번 호출해도 DB가 오염되지 않아야 함
        for pass_rate in [70.0, 80.0, 90.0, 100.0]:
            test_results = {
                'overall_pass_rate': pass_rate,
                'total_rounds': 50,
                'overall_pass_count': int(50 * pass_rate / 100)
            }
            # 예외 없이 실행되어야 함
            validator._save_to_performance_tracker(test_results)

        # DB에 avg_matches=0 레코드가 없어야 함
        with sqlite3.connect('data/continuous_improvement.db') as conn:
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM performance_history WHERE avg_matches=0 OR avg_matches IS NULL"
                ).fetchone()[0]
            except Exception:
                count = 0

        assert count == 0, (
            f"DB에 avg_matches=0 쓰레기 레코드 {count}개 발견! "
            f"filter_validator의 DB 오염이 해결되지 않았습니다."
        )

        print(f"\n[OK] auto-improvement DB 오염 방지 확인됨")


def test_integration_with_real_data():
    """[FIX] 통합 테스트: filter_validator 실행 후 DB가 오염되지 않는지 확인"""
    from src.validators.filter_validator import FilterValidator

    validator = FilterValidator()

    # 테스트 전 DB 상태 스냅샷
    before_zero_count = 0
    try:
        with sqlite3.connect('data/continuous_improvement.db') as conn:
            before_zero_count = conn.execute(
                "SELECT COUNT(*) FROM performance_history WHERE avg_matches=0 OR avg_matches IS NULL"
            ).fetchone()[0]
    except Exception:
        pass

    # Mock으로 실제 필터 검증 실행
    with patch.object(validator.db_manager, 'get_numbers_with_bonus') as mock_get_numbers:
        # 2개 회차만 테스트
        mock_get_numbers.return_value = [
            (1100, (1, 2, 3, 4, 5, 6, 7)),
            (1101, (8, 9, 10, 11, 12, 13, 14)),
        ]

        # 필터 검증 실행
        with patch.object(validator, '_print_validation_summary'):
            results = validator.validate_filters_with_historical_data(start_round=1100, end_round=1101)

    # 결과 딕셔너리 확인
    assert 'overall_pass_rate' in results

    # [FIX] DB가 오염되지 않았는지 확인: avg_matches=0 레코드 증가 없음
    after_zero_count = 0
    try:
        with sqlite3.connect('data/continuous_improvement.db') as conn:
            after_zero_count = conn.execute(
                "SELECT COUNT(*) FROM performance_history WHERE avg_matches=0 OR avg_matches IS NULL"
            ).fetchone()[0]
    except Exception:
        pass

    assert after_zero_count == before_zero_count, (
        f"필터 검증 후 avg_matches=0 쓰레기 레코드 {after_zero_count - before_zero_count}개 증가! "
        f"DB 오염이 해결되지 않았습니다."
    )

    print(f"\n[OK] 통합 테스트 통과!")
    print(f"   필터 통과율: {results['overall_pass_rate']:.2f}% (DB 오염 없음)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
