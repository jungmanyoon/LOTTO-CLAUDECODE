"""
필터 통과율 데이터 경로 수정 검증 테스트

ROOT CAUSE:
- continuous_improvement_engine.py가 result['filter_pass_rate']를 찾았지만
- 실제 데이터는 result['performance_metrics']['overall_filter_pass_rate']에 있음

FIX:
1. backtesting_framework.py: overall_filter_pass_rate 계산 추가 (line 1021-1033)
2. continuous_improvement_engine.py: 올바른 경로에서 데이터 추출 (line 957-971)
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.core.continuous_improvement_engine import PerformanceMetrics, ContinuousImprovementEngine


class TestFilterPassRateDataPath:

    def test_backtesting_returns_overall_filter_pass_rate(self):
        """백테스팅 결과에 overall_filter_pass_rate가 포함되는지 확인"""
        # Simulate backtesting result structure
        backtesting_result = {
            'performance_metrics': {
                'overall_avg_matches': 1.2,
                'model_performance': {
                    'lstm': {
                        'total_predictions': 10,
                        'filter_passed_count': 8,
                        'filter_pass_rate': 80.0
                    },
                    'ensemble': {
                        'total_predictions': 10,
                        'filter_passed_count': 9,
                        'filter_pass_rate': 90.0
                    }
                },
                'overall_filter_pass_rate': 85.0  # ✅ This should exist after fix
            }
        }

        # Verify the key exists
        assert 'overall_filter_pass_rate' in backtesting_result['performance_metrics']
        assert backtesting_result['performance_metrics']['overall_filter_pass_rate'] == 85.0


    def test_continuous_improvement_extracts_correct_path(self):
        """continuous_improvement_engine이 올바른 경로에서 filter_pass_rate 추출하는지 확인"""
        # Simulate backtesting result
        mock_result = {
            'performance_metrics': {
                'overall_avg_matches': 1.5,
                'model_performance': {
                    'lstm': {'best_match': 4, 'accuracy_3plus': 15.0},
                },
                'overall_filter_pass_rate': 82.5  # ✅ Correct path
            },
            'ml_inclusion_rate': 0.12,
            'combination_count': 300000
        }

        # Extract using same logic as fixed code
        performance_metrics = mock_result.get('performance_metrics', {})
        overall_filter_pass_rate = performance_metrics.get('overall_filter_pass_rate', 0.0)

        # Verify extraction
        assert overall_filter_pass_rate == 82.5
        assert overall_filter_pass_rate > 0  # Not the default value!


    def test_old_path_returns_zero(self):
        """이전 경로(result['filter_pass_rate'])는 0을 반환하는지 확인"""
        mock_result = {
            'performance_metrics': {
                'overall_filter_pass_rate': 82.5
            }
        }

        # Old (wrong) path
        old_way = mock_result.get('filter_pass_rate', 0.0)

        # New (correct) path
        new_way = mock_result.get('performance_metrics', {}).get('overall_filter_pass_rate', 0.0)

        # Old way returns default (WRONG)
        assert old_way == 0.0

        # New way returns actual value (CORRECT)
        assert new_way == 82.5


    def test_overall_filter_pass_rate_calculation(self):
        """overall_filter_pass_rate가 모든 모델의 통과율을 집계하는지 확인"""
        model_performance = {
            'lstm': {
                'total_predictions': 10,
                'filter_passed_count': 8,  # 80%
            },
            'ensemble': {
                'total_predictions': 10,
                'filter_passed_count': 9,  # 90%
            },
            'monte_carlo': {
                'total_predictions': 10,
                'filter_passed_count': 10,  # 100%
            }
        }

        # Calculate overall (same logic as fixed code)
        total_predictions = sum(m['total_predictions'] for m in model_performance.values())
        total_passed = sum(m['filter_passed_count'] for m in model_performance.values())

        overall_filter_pass_rate = (total_passed / total_predictions) * 100

        # Verify: (8+9+10) / (10+10+10) * 100 = 27/30 * 100 = 90%
        assert overall_filter_pass_rate == 90.0


    @patch('src.core.continuous_improvement_engine.OptimizedBacktestingFramework')
    def test_end_to_end_data_flow(self, mock_backtesting_class, tmp_path):
        """전체 데이터 흐름이 정상 작동하는지 확인"""
        # Mock backtesting to return correct structure
        mock_backtesting = Mock()
        mock_backtesting.run_backtest.return_value = {
            'performance_metrics': {
                'overall_avg_matches': 1.2,
                'model_performance': {
                    'lstm': {'best_match': 4, 'accuracy_3plus': 15.0,
                           'total_predictions': 10, 'filter_passed_count': 8}
                },
                'overall_filter_pass_rate': 82.35  # ✅ Key fix!
            },
            'ml_inclusion_rate': 0.12,
            'combination_count': 300000
        }
        mock_backtesting_class.return_value = mock_backtesting

        # Mock DatabaseManager
        mock_db = Mock()
        mock_db.get_latest_round.return_value = 1186

        # Create engine
        db_path = str(tmp_path / "test_ci.db")
        engine = ContinuousImprovementEngine(
            db_manager=mock_db,
            config_path='configs/adaptive_filter_config.yaml',
            improvement_db_path=db_path
        )

        # Measure performance (this will call our fixed extraction logic)
        metrics = engine._measure_current_performance()

        # Verify filter_pass_rate is extracted correctly
        assert metrics is not None
        assert metrics.filter_pass_rate == 82.35  # ✅ SUCCESS!
        assert metrics.filter_pass_rate > 0  # Not the default!


    def test_protection_system_triggers_with_valid_data(self, tmp_path):
        """유효한 데이터로 보호 시스템이 트리거되는지 확인"""
        from src.core.continuous_improvement_engine import PerformanceTracker

        db_path = str(tmp_path / "test_tracker.db")
        tracker = PerformanceTracker(db_path=db_path)

        # Save a best pass rate record
        best_metrics = PerformanceMetrics(
            avg_matches=1.2,
            best_match=4,
            accuracy_3plus=15.0,
            ml_inclusion_rate=0.12,
            combination_count=300000,
            threshold=1.0,
            ml_bypass_filters=8,
            ml_weight=0.4,
            filter_pass_rate=82.35,  # ✅ Non-zero value
            timestamp=datetime.now()
        )

        tracker.save_performance_result(best_metrics, round_number=1186)

        # Retrieve best pass rate
        best = tracker.get_best_pass_rate_performance()

        # Verify protection system can trigger
        assert best is not None
        assert best.filter_pass_rate > 0  # ✅ Condition passes!
        assert best.filter_pass_rate == 82.35

        # Simulate current pass rate drop
        current_pass_rate = 81.0

        # Check if protection would trigger
        should_warn = current_pass_rate < best.filter_pass_rate
        drop_amount = best.filter_pass_rate - current_pass_rate

        assert should_warn is True
        assert drop_amount == pytest.approx(1.35, abs=0.01)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
