"""
Unified Performance Metrics System
====================================
Single source of truth for all performance scoring calculations across the entire system.
Prevents formula drift between modules by providing centralized scoring functions.

Design Decision: Normalized 0-1 Range (Raw Score Internally Stored)
---------------------------------------------------------------------
After analyzing all usage patterns, we standardize on:
- Raw avg_matches stored in database (0-6 range) for data integrity
- Normalized scores (0-1 range) used for comparisons and decisions
- Consistent formula: normalized_score = min(1.0, max(0.0, raw_score / 2.0))
- Target: 1.0 avg_matches (0.5 normalized) for balanced predictions

Rationale:
1. Raw scores preserve true match counts for analysis
2. Normalized scores provide intuitive percentage-like comparisons (50% = 1 match)
3. Division by 2.0 sets realistic target (1 match = 50%, 2 matches = 100%)
4. Prevents threshold confusion (0.8 normalized is clearly 1.6 avg_matches)
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ModelPerformance:
    """
    Standardized model performance data structure.

    Attributes:
        avg_matches: Average number of matches (0-6 scale, raw data)
        max_matches: Maximum matches achieved (0-6 scale)
        accuracy_3plus: Percentage of predictions with 3+ matches (0-1 scale)
        total_predictions: Total number of predictions made
        ml_inclusion_rate: ML prediction filter inclusion rate (0-1 scale)
    """
    avg_matches: float
    max_matches: int = 0
    accuracy_3plus: float = 0.0
    total_predictions: int = 0
    ml_inclusion_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'avg_matches': self.avg_matches,
            'max_matches': self.max_matches,
            'accuracy_3plus': self.accuracy_3plus,
            'total_predictions': self.total_predictions,
            'ml_inclusion_rate': self.ml_inclusion_rate
        }


class PerformanceMetrics:
    """
    Unified performance metrics calculator.
    Single source of truth for all scoring formulas across the system.
    """

    # Performance Constants
    MAX_POSSIBLE_MATCHES = 6  # Lotto has 6 main numbers
    TARGET_AVG_MATCHES = 1.0  # Realistic target for balanced predictions
    NORMALIZATION_DIVISOR = 2.0  # Maps 2 matches to 1.0 (100%)

    # Model Weights for Composite Scoring
    MODEL_WEIGHTS = {
        'lstm': 0.25,
        'ensemble': 0.5,
        'monte_carlo': 0.25
    }

    # Data Contamination Thresholds
    CONTAMINATION_WARNING = 2.5  # Warn if avg_matches > 2.5
    CONTAMINATION_CRITICAL = 3.0  # Critical if avg_matches > 3.0

    @staticmethod
    def normalize_score(avg_matches: float, max_matches: int = MAX_POSSIBLE_MATCHES) -> float:
        """
        Convert raw avg_matches to normalized score (0-1 range).

        Formula: normalized = min(1.0, max(0.0, avg_matches / NORMALIZATION_DIVISOR))

        This creates an intuitive scale where:
        - 0.0 matches → 0.0 score (0%)
        - 1.0 matches → 0.5 score (50%) ← TARGET
        - 2.0 matches → 1.0 score (100%)
        - 3.0+ matches → 1.0 score (capped at 100%, potential contamination)

        Args:
            avg_matches: Average number of matches (0-6 scale)
            max_matches: Maximum possible matches (default: 6)

        Returns:
            Normalized score in [0.0, 1.0] range

        Examples:
            >>> PerformanceMetrics.normalize_score(0.0)
            0.0
            >>> PerformanceMetrics.normalize_score(1.0)
            0.5
            >>> PerformanceMetrics.normalize_score(2.0)
            1.0
            >>> PerformanceMetrics.normalize_score(3.5)
            1.0  # Capped at 1.0
        """
        if avg_matches < 0:
            logger.warning(f"Negative avg_matches detected: {avg_matches}, clamping to 0.0")
            avg_matches = 0.0

        normalized = avg_matches / PerformanceMetrics.NORMALIZATION_DIVISOR
        return min(1.0, max(0.0, normalized))

    @staticmethod
    def denormalize_score(normalized_score: float) -> float:
        """
        Convert normalized score back to raw avg_matches.

        Formula: avg_matches = normalized * NORMALIZATION_DIVISOR

        Args:
            normalized_score: Score in [0.0, 1.0] range

        Returns:
            Raw avg_matches (0-6 scale)

        Examples:
            >>> PerformanceMetrics.denormalize_score(0.5)
            1.0
            >>> PerformanceMetrics.denormalize_score(1.0)
            2.0
        """
        return normalized_score * PerformanceMetrics.NORMALIZATION_DIVISOR

    @staticmethod
    def calculate_overall_score(
        lstm: float,
        ensemble: float,
        monte_carlo: float,
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate weighted overall score from individual model performances.

        This function EXPECTS raw avg_matches (0-6 scale) as inputs and
        returns raw avg_matches as output. Normalization should be done
        separately using normalize_score() if needed.

        Args:
            lstm: LSTM model avg_matches (0-6 scale)
            ensemble: Ensemble model avg_matches (0-6 scale)
            monte_carlo: Monte Carlo model avg_matches (0-6 scale)
            weights: Optional custom weights (default: 0.25, 0.5, 0.25)

        Returns:
            Weighted average of avg_matches (0-6 scale)

        Examples:
            >>> PerformanceMetrics.calculate_overall_score(0.9, 1.1, 0.8)
            1.0  # 0.9*0.25 + 1.1*0.5 + 0.8*0.25 = 1.0
        """
        if weights is None:
            weights = PerformanceMetrics.MODEL_WEIGHTS

        overall = (
            lstm * weights.get('lstm', 0.25) +
            ensemble * weights.get('ensemble', 0.5) +
            monte_carlo * weights.get('monte_carlo', 0.25)
        )

        return overall

    @staticmethod
    def calculate_composite_score(
        avg_matches: float,
        accuracy_3plus: float,
        best_match: int,
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate composite performance score (0-100 scale) for dashboards.

        Used by monitoring dashboards to provide intuitive percentage scores.
        This is different from normalized_score and should NOT be used for
        optimization decisions.

        Args:
            avg_matches: Average matches (0-6 scale)
            accuracy_3plus: 3+ match accuracy (0-1 scale)
            best_match: Best match count (0-6 scale)
            weights: Optional custom weights

        Returns:
            Composite score in [0, 100] range

        Formula:
            score = (
                (avg_matches / 2.0) * 0.5 +       # 50% weight
                (accuracy_3plus / 0.1) * 0.3 +    # 30% weight (10% target)
                (best_match / 6.0) * 0.2           # 20% weight
            ) * 100
        """
        if weights is None:
            weights = {'avg_matches': 0.5, 'accuracy_3plus': 0.3, 'best_match': 0.2}

        # Normalize each component to [0, 1] range
        norm_avg = min(1.0, avg_matches / 2.0)  # 2 matches = 100%
        norm_accuracy = min(1.0, accuracy_3plus / 0.1)  # 10% = 100%
        norm_best = best_match / PerformanceMetrics.MAX_POSSIBLE_MATCHES

        # Calculate weighted composite
        score = (
            norm_avg * weights['avg_matches'] +
            norm_accuracy * weights['accuracy_3plus'] +
            norm_best * weights['best_match']
        ) * 100

        return min(100.0, max(0.0, score))

    @staticmethod
    def check_contamination(avg_matches: float) -> Dict[str, Any]:
        """
        Check for potential data contamination based on avg_matches.

        Data contamination occurs when test data leaks into training,
        causing unrealistically high match rates.

        Args:
            avg_matches: Average matches (0-6 scale)

        Returns:
            Dict with contamination status:
                - is_contaminated: bool
                - severity: str ('none', 'warning', 'critical')
                - message: str (explanation)

        Thresholds:
            - < 2.5: Clean (normal)
            - 2.5-3.0: Warning (suspicious)
            - > 3.0: Critical (likely contaminated)
        """
        if avg_matches >= PerformanceMetrics.CONTAMINATION_CRITICAL:
            return {
                'is_contaminated': True,
                'severity': 'critical',
                'message': f'CRITICAL: avg_matches={avg_matches:.3f} > {PerformanceMetrics.CONTAMINATION_CRITICAL} - Data contamination detected!'
            }
        elif avg_matches >= PerformanceMetrics.CONTAMINATION_WARNING:
            return {
                'is_contaminated': True,
                'severity': 'warning',
                'message': f'WARNING: avg_matches={avg_matches:.3f} > {PerformanceMetrics.CONTAMINATION_WARNING} - Possible data contamination'
            }
        else:
            return {
                'is_contaminated': False,
                'severity': 'none',
                'message': f'Clean: avg_matches={avg_matches:.3f} within normal range'
            }

    @staticmethod
    def compare_performance(
        current: float,
        previous: float,
        threshold: float = 0.05
    ) -> Dict[str, Any]:
        """
        Compare two performance scores and determine if there's improvement.

        IMPORTANT: This function expects NORMALIZED scores (0-1 range).
        Use normalize_score() on raw avg_matches before passing to this function.

        Args:
            current: Current normalized score (0-1 range)
            previous: Previous normalized score (0-1 range)
            threshold: Minimum change to consider significant (default: 0.05 = 5%)

        Returns:
            Dict with comparison results:
                - improved: bool
                - degraded: bool
                - stable: bool
                - change_percent: float
                - change_absolute: float

        Examples:
            >>> current = PerformanceMetrics.normalize_score(1.102)  # 0.551
            >>> previous = PerformanceMetrics.normalize_score(0.806)  # 0.403
            >>> result = PerformanceMetrics.compare_performance(current, previous)
            >>> result['improved']
            True
            >>> result['change_percent']
            36.72  # 36.72% improvement
        """
        change_absolute = current - previous
        change_percent = (change_absolute / previous * 100) if previous > 0 else 0.0

        is_significant = abs(change_absolute) >= threshold

        return {
            'improved': is_significant and change_absolute > 0,
            'degraded': is_significant and change_absolute < 0,
            'stable': not is_significant,
            'change_percent': change_percent,
            'change_absolute': change_absolute,
            'is_significant': is_significant
        }

    @staticmethod
    def validate_performance_data(performance: Dict[str, Any]) -> bool:
        """
        Validate performance data structure and value ranges.

        Args:
            performance: Performance dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = ['avg_matches']

        # Check required fields
        for field in required_fields:
            if field not in performance:
                logger.error(f"Missing required field: {field}")
                return False

        # Validate ranges
        avg_matches = performance.get('avg_matches', -1)
        if not (0 <= avg_matches <= PerformanceMetrics.MAX_POSSIBLE_MATCHES):
            logger.error(f"avg_matches out of range: {avg_matches}")
            return False

        # Validate optional fields if present
        if 'accuracy_3plus' in performance:
            if not (0 <= performance['accuracy_3plus'] <= 1.0):
                logger.error(f"accuracy_3plus out of range: {performance['accuracy_3plus']}")
                return False

        if 'max_matches' in performance:
            if not (0 <= performance['max_matches'] <= PerformanceMetrics.MAX_POSSIBLE_MATCHES):
                logger.error(f"max_matches out of range: {performance['max_matches']}")
                return False

        return True

    @staticmethod
    def format_performance_report(
        performance: Dict[str, Any],
        include_normalized: bool = True
    ) -> str:
        """
        Format performance data as human-readable report.

        Args:
            performance: Performance dictionary
            include_normalized: Include normalized scores (default: True)

        Returns:
            Formatted string report
        """
        avg_matches = performance.get('avg_matches', 0.0)
        lines = [
            "Performance Report",
            "=" * 50,
            f"Average Matches (Raw):  {avg_matches:.3f}"
        ]

        if include_normalized:
            normalized = PerformanceMetrics.normalize_score(avg_matches)
            lines.append(f"Normalized Score:       {normalized:.3f} ({normalized*100:.1f}%)")

        if 'max_matches' in performance:
            lines.append(f"Best Match:             {performance['max_matches']}")

        if 'accuracy_3plus' in performance:
            lines.append(f"3+ Match Accuracy:      {performance['accuracy_3plus']:.1%}")

        if 'total_predictions' in performance:
            lines.append(f"Total Predictions:      {performance['total_predictions']}")

        # Contamination check
        contamination = PerformanceMetrics.check_contamination(avg_matches)
        lines.append(f"\n{contamination['message']}")

        return "\n".join(lines)


# Convenience functions for backward compatibility
def normalize_score(avg_matches: float) -> float:
    """Convenience wrapper for PerformanceMetrics.normalize_score()"""
    return PerformanceMetrics.normalize_score(avg_matches)


def calculate_overall_score(lstm: float, ensemble: float, monte_carlo: float) -> float:
    """Convenience wrapper for PerformanceMetrics.calculate_overall_score()"""
    return PerformanceMetrics.calculate_overall_score(lstm, ensemble, monte_carlo)
