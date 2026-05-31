"""
Unit Tests for Unified Performance Metrics System
==================================================
Validates scoring formulas, normalization, and comparison logic.
Prevents future formula drift through comprehensive test coverage.
"""

import unittest
import pytest
from src.core.performance_metrics import (
    PerformanceMetrics,
    ModelPerformance,
    normalize_score,
    calculate_overall_score
)


class TestPerformanceMetricsNormalization(unittest.TestCase):
    """Test score normalization functions"""

    def test_normalize_zero_matches(self):
        """0 matches should normalize to 0.0"""
        result = PerformanceMetrics.normalize_score(0.0)
        self.assertEqual(result, 0.0)

    def test_normalize_target_matches(self):
        """1.0 matches (target) should normalize to 0.5"""
        result = PerformanceMetrics.normalize_score(1.0)
        self.assertEqual(result, 0.5)

    def test_normalize_perfect_matches(self):
        """2.0 matches should normalize to 1.0 (100%)"""
        result = PerformanceMetrics.normalize_score(2.0)
        self.assertEqual(result, 1.0)

    def test_normalize_capped_at_one(self):
        """Scores > 2.0 should be capped at 1.0"""
        result = PerformanceMetrics.normalize_score(3.5)
        self.assertEqual(result, 1.0)

        result = PerformanceMetrics.normalize_score(6.0)
        self.assertEqual(result, 1.0)

    def test_normalize_negative_clamped(self):
        """Negative scores should be clamped to 0.0"""
        result = PerformanceMetrics.normalize_score(-0.5)
        self.assertEqual(result, 0.0)

    def test_normalize_realistic_values(self):
        """Test realistic avg_matches values"""
        # 0.806 avg_matches (old value)
        result = PerformanceMetrics.normalize_score(0.806)
        self.assertAlmostEqual(result, 0.403, places=3)

        # 1.102 avg_matches (new value)
        result = PerformanceMetrics.normalize_score(1.102)
        self.assertAlmostEqual(result, 0.551, places=3)

        # Verify new > old
        self.assertTrue(0.551 > 0.403)

    def test_denormalize_score(self):
        """Test score denormalization"""
        self.assertEqual(PerformanceMetrics.denormalize_score(0.5), 1.0)
        self.assertEqual(PerformanceMetrics.denormalize_score(1.0), 2.0)
        self.assertEqual(PerformanceMetrics.denormalize_score(0.0), 0.0)

    def test_round_trip_normalization(self):
        """Normalize then denormalize should return original (within range)"""
        original = 1.5
        normalized = PerformanceMetrics.normalize_score(original)
        denormalized = PerformanceMetrics.denormalize_score(normalized)
        self.assertAlmostEqual(denormalized, original, places=5)


class TestPerformanceMetricsOverallScore(unittest.TestCase):
    """Test overall score calculation"""

    def test_calculate_overall_default_weights(self):
        """Test weighted average with default weights"""
        # 0.25 * 0.9 + 0.5 * 1.1 + 0.25 * 0.8 = 0.975
        result = PerformanceMetrics.calculate_overall_score(0.9, 1.1, 0.8)
        self.assertAlmostEqual(result, 0.975, places=3)

    def test_calculate_overall_custom_weights(self):
        """Test with custom weights"""
        weights = {'lstm': 0.3, 'ensemble': 0.4, 'monte_carlo': 0.3}
        result = PerformanceMetrics.calculate_overall_score(
            1.0, 1.0, 1.0, weights=weights
        )
        self.assertEqual(result, 1.0)

    def test_calculate_overall_realistic_scenario(self):
        """Test with realistic model performances"""
        # Scenario from bug report
        lstm = 0.9
        ensemble = 1.1
        monte_carlo = 0.8

        result = PerformanceMetrics.calculate_overall_score(lstm, ensemble, monte_carlo)
        self.assertAlmostEqual(result, 0.975, places=2)

    def test_calculate_overall_zero_values(self):
        """Test with zero performances"""
        result = PerformanceMetrics.calculate_overall_score(0.0, 0.0, 0.0)
        self.assertEqual(result, 0.0)

    def test_calculate_overall_returns_raw_scale(self):
        """Verify overall score is in raw 0-6 range, NOT normalized"""
        result = PerformanceMetrics.calculate_overall_score(1.5, 2.0, 1.8)
        # Expected: 1.5*0.25 + 2.0*0.5 + 1.8*0.25 = 1.825
        self.assertAlmostEqual(result, 1.825, places=3)
        # Verify it's NOT normalized (would be 0.9125 if normalized)
        self.assertTrue(result > 1.0)

    def test_convenience_function(self):
        """Test convenience wrapper function"""
        result1 = calculate_overall_score(0.9, 1.1, 0.8)
        result2 = PerformanceMetrics.calculate_overall_score(0.9, 1.1, 0.8)
        self.assertEqual(result1, result2)


class TestPerformanceMetricsComparison(unittest.TestCase):
    """Test performance comparison logic"""

    def test_compare_improved_performance(self):
        """Test detecting improvement"""
        current = PerformanceMetrics.normalize_score(1.102)  # 0.551
        previous = PerformanceMetrics.normalize_score(0.806)  # 0.403

        result = PerformanceMetrics.compare_performance(current, previous)

        self.assertTrue(result['improved'])
        self.assertFalse(result['degraded'])
        self.assertFalse(result['stable'])
        self.assertGreater(result['change_percent'], 0)
        self.assertAlmostEqual(result['change_percent'], 36.72, places=0)

    def test_compare_degraded_performance(self):
        """Test detecting degradation"""
        current = PerformanceMetrics.normalize_score(0.806)  # 0.403
        previous = PerformanceMetrics.normalize_score(1.102)  # 0.551

        result = PerformanceMetrics.compare_performance(current, previous)

        self.assertFalse(result['improved'])
        self.assertTrue(result['degraded'])
        self.assertFalse(result['stable'])
        self.assertLess(result['change_percent'], 0)

    def test_compare_stable_performance(self):
        """Test detecting stable performance (within threshold)"""
        current = 0.500
        previous = 0.505  # Only 1% difference

        result = PerformanceMetrics.compare_performance(
            current, previous, threshold=0.05
        )

        self.assertFalse(result['improved'])
        self.assertFalse(result['degraded'])
        self.assertTrue(result['stable'])

    def test_compare_custom_threshold(self):
        """Test with custom significance threshold"""
        current = 0.510
        previous = 0.500

        # With 5% threshold: not significant
        result1 = PerformanceMetrics.compare_performance(
            current, previous, threshold=0.05
        )
        self.assertTrue(result1['stable'])

        # With 1% threshold: significant
        result2 = PerformanceMetrics.compare_performance(
            current, previous, threshold=0.01
        )
        self.assertTrue(result2['improved'])

    def test_compare_zero_previous(self):
        """Test comparison when previous is zero"""
        result = PerformanceMetrics.compare_performance(0.5, 0.0)
        self.assertTrue(result['improved'])
        # Change percent should be 0 to avoid division by zero
        self.assertEqual(result['change_percent'], 0.0)


class TestPerformanceMetricsContamination(unittest.TestCase):
    """Test data contamination detection"""

    def test_contamination_clean_data(self):
        """Test clean data (< 2.5 avg_matches)"""
        result = PerformanceMetrics.check_contamination(1.5)
        self.assertFalse(result['is_contaminated'])
        self.assertEqual(result['severity'], 'none')

    def test_contamination_warning_level(self):
        """Test warning level (2.5 <= avg_matches < 3.0)"""
        result = PerformanceMetrics.check_contamination(2.7)
        self.assertTrue(result['is_contaminated'])
        self.assertEqual(result['severity'], 'warning')

    def test_contamination_critical_level(self):
        """Test critical level (avg_matches >= 3.0)"""
        result = PerformanceMetrics.check_contamination(3.5)
        self.assertTrue(result['is_contaminated'])
        self.assertEqual(result['severity'], 'critical')

    def test_contamination_boundary_values(self):
        """Test boundary values"""
        # Just below warning
        result = PerformanceMetrics.check_contamination(2.49)
        self.assertFalse(result['is_contaminated'])

        # Exactly at warning threshold
        result = PerformanceMetrics.check_contamination(2.5)
        self.assertTrue(result['is_contaminated'])
        self.assertEqual(result['severity'], 'warning')

        # Exactly at critical threshold
        result = PerformanceMetrics.check_contamination(3.0)
        self.assertTrue(result['is_contaminated'])
        self.assertEqual(result['severity'], 'critical')


class TestPerformanceMetricsCompositeScore(unittest.TestCase):
    """Test composite score calculation (0-100 scale)"""

    def test_composite_score_all_perfect(self):
        """Test with perfect values"""
        # 2.0 avg, 10% accuracy_3plus, 6 best_match = 100%
        result = PerformanceMetrics.calculate_composite_score(
            avg_matches=2.0,
            accuracy_3plus=0.1,
            best_match=6
        )
        self.assertEqual(result, 100.0)

    def test_composite_score_all_zero(self):
        """Test with zero values"""
        result = PerformanceMetrics.calculate_composite_score(
            avg_matches=0.0,
            accuracy_3plus=0.0,
            best_match=0
        )
        self.assertEqual(result, 0.0)

    def test_composite_score_realistic(self):
        """Test with realistic values"""
        # 1.0 avg, 5% accuracy, 4 best_match
        result = PerformanceMetrics.calculate_composite_score(
            avg_matches=1.0,
            accuracy_3plus=0.05,
            best_match=4
        )
        # Expected: (0.5*0.5 + 0.5*0.3 + 0.667*0.2) * 100 = 52.34
        self.assertGreater(result, 50.0)
        self.assertLess(result, 60.0)

    def test_composite_score_capped_at_100(self):
        """Test score is capped at 100"""
        result = PerformanceMetrics.calculate_composite_score(
            avg_matches=5.0,
            accuracy_3plus=0.5,
            best_match=6
        )
        self.assertEqual(result, 100.0)


class TestPerformanceMetricsValidation(unittest.TestCase):
    """Test data validation"""

    def test_validate_complete_data(self):
        """Test validation with complete valid data"""
        data = {
            'avg_matches': 1.2,
            'max_matches': 5,
            'accuracy_3plus': 0.08,
            'total_predictions': 100
        }
        self.assertTrue(PerformanceMetrics.validate_performance_data(data))

    def test_validate_missing_required_field(self):
        """Test validation fails with missing avg_matches"""
        data = {
            'max_matches': 5,
            'accuracy_3plus': 0.08
        }
        self.assertFalse(PerformanceMetrics.validate_performance_data(data))

    def test_validate_out_of_range_avg_matches(self):
        """Test validation fails with out-of-range avg_matches"""
        data = {'avg_matches': 7.0}  # Max is 6
        self.assertFalse(PerformanceMetrics.validate_performance_data(data))

        data = {'avg_matches': -1.0}  # Min is 0
        self.assertFalse(PerformanceMetrics.validate_performance_data(data))

    def test_validate_out_of_range_accuracy(self):
        """Test validation fails with out-of-range accuracy"""
        data = {
            'avg_matches': 1.0,
            'accuracy_3plus': 1.5  # Max is 1.0
        }
        self.assertFalse(PerformanceMetrics.validate_performance_data(data))


class TestModelPerformanceDataClass(unittest.TestCase):
    """Test ModelPerformance dataclass"""

    def test_model_performance_creation(self):
        """Test creating ModelPerformance instance"""
        perf = ModelPerformance(
            avg_matches=1.2,
            max_matches=5,
            accuracy_3plus=0.08,
            total_predictions=100,
            ml_inclusion_rate=0.15
        )
        self.assertEqual(perf.avg_matches, 1.2)
        self.assertEqual(perf.max_matches, 5)

    def test_model_performance_to_dict(self):
        """Test converting to dictionary"""
        perf = ModelPerformance(avg_matches=1.0)
        data = perf.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data['avg_matches'], 1.0)
        self.assertEqual(data['max_matches'], 0)


class TestPerformanceMetricsFormatting(unittest.TestCase):
    """Test report formatting"""

    def test_format_basic_report(self):
        """Test basic report formatting"""
        data = {'avg_matches': 1.2}
        report = PerformanceMetrics.format_performance_report(data)
        self.assertIn('1.200', report)
        self.assertIn('Performance Report', report)

    def test_format_report_with_normalized(self):
        """Test report includes normalized score"""
        data = {'avg_matches': 1.0}
        report = PerformanceMetrics.format_performance_report(data, include_normalized=True)
        self.assertIn('0.500', report)  # 1.0 / 2.0 = 0.5
        self.assertIn('50.0%', report)

    def test_format_report_without_normalized(self):
        """Test report without normalized score"""
        data = {'avg_matches': 1.0}
        report = PerformanceMetrics.format_performance_report(data, include_normalized=False)
        self.assertNotIn('Normalized', report)

    def test_format_report_contamination_warning(self):
        """Test report includes contamination warning"""
        data = {'avg_matches': 3.2}
        report = PerformanceMetrics.format_performance_report(data)
        self.assertIn('CRITICAL', report)


class TestFormulaConsistency(unittest.TestCase):
    """Test that formulas remain consistent across all methods"""

    def test_normalization_formula_consistency(self):
        """Verify normalization formula: score = avg_matches / 2.0"""
        test_values = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]

        for val in test_values:
            result = PerformanceMetrics.normalize_score(val)
            expected = min(1.0, val / 2.0)
            self.assertAlmostEqual(result, expected, places=5,
                                 msg=f"Formula inconsistency for {val}")

    def test_weighted_average_formula_consistency(self):
        """Verify weighted average formula stays consistent"""
        lstm, ensemble, monte_carlo = 1.0, 1.5, 0.8

        # Manual calculation
        expected = lstm * 0.25 + ensemble * 0.5 + monte_carlo * 0.25

        # Function calculation
        result = PerformanceMetrics.calculate_overall_score(lstm, ensemble, monte_carlo)

        self.assertAlmostEqual(result, expected, places=5)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""

    def test_very_small_positive_values(self):
        """Test with very small positive values"""
        result = PerformanceMetrics.normalize_score(0.001)
        self.assertGreater(result, 0.0)
        self.assertLess(result, 0.01)

    def test_maximum_possible_value(self):
        """Test with maximum possible matches (6)"""
        result = PerformanceMetrics.normalize_score(6.0)
        self.assertEqual(result, 1.0)

    def test_float_precision(self):
        """Test floating point precision handling"""
        val = 1.0 / 3.0  # 0.333...
        result = PerformanceMetrics.normalize_score(val)
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.15)
        self.assertLess(result, 0.17)


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test convenience wrapper functions"""

    def test_normalize_score_wrapper(self):
        """Test normalize_score convenience function"""
        result1 = normalize_score(1.0)
        result2 = PerformanceMetrics.normalize_score(1.0)
        assert result1 == result2

    def test_calculate_overall_wrapper(self):
        """Test calculate_overall_score convenience function"""
        result1 = calculate_overall_score(0.9, 1.1, 0.8)
        result2 = PerformanceMetrics.calculate_overall_score(0.9, 1.1, 0.8)
        assert result1 == result2


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
