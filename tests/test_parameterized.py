#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파라미터화된 테스트 모음

Phase 3.11: @pytest.mark.parametrize 활용
- 엣지 케이스 조합 테스트
- 경계값 테스트
- 다양한 입력 조합 테스트
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock
from decimal import Decimal

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestCombinationValidation:
    """조합 유효성 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("combination,expected_valid", [
        # 정상 케이스
        ([1, 2, 3, 4, 5, 6], True),
        ([1, 10, 20, 30, 40, 45], True),
        ([40, 41, 42, 43, 44, 45], True),
        # 범위 벗어남
        ([0, 1, 2, 3, 4, 5], False),
        ([1, 2, 3, 4, 5, 46], False),
        ([-1, 2, 3, 4, 5, 6], False),
        # 중복
        ([1, 1, 2, 3, 4, 5], False),
        ([1, 2, 3, 3, 4, 5], False),
        # 길이 오류
        ([1, 2, 3, 4, 5], False),
        ([1, 2, 3, 4, 5, 6, 7], False),
        ([], False),
    ])
    def test_combination_validity(self, combination, expected_valid):
        """조합 유효성 검증"""
        def is_valid_combination(combo):
            if len(combo) != 6:
                return False
            if len(set(combo)) != 6:
                return False
            if not all(1 <= n <= 45 for n in combo):
                return False
            return True

        assert is_valid_combination(combination) == expected_valid


class TestSumRangeValidation:
    """합계 범위 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("combination,min_sum,max_sum,expected", [
        # 정상 범위 내
        ([1, 2, 3, 4, 5, 6], 21, 200, True),  # sum=21
        ([10, 20, 30, 40, 41, 42], 68, 209, True),  # sum=183
        ([40, 41, 42, 43, 44, 45], 100, 300, True),  # sum=255
        # 범위 밖
        ([1, 2, 3, 4, 5, 6], 22, 200, False),  # sum=21, below min
        ([40, 41, 42, 43, 44, 45], 68, 200, False),  # sum=255, above max
        # 경계값
        ([1, 2, 3, 4, 5, 6], 21, 21, True),  # 정확히 경계
        ([40, 41, 42, 43, 44, 45], 255, 255, True),  # 정확히 경계
        ([1, 2, 3, 4, 5, 6], 20, 20, False),  # 경계 밖
    ])
    def test_sum_range_filter(self, combination, min_sum, max_sum, expected):
        """합계 범위 필터 테스트"""
        total = sum(combination)
        result = min_sum <= total <= max_sum
        assert result == expected


class TestConsecutiveNumbers:
    """연속 번호 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("combination,max_consecutive,expected_pass", [
        # 연속 없음
        ([1, 3, 5, 7, 9, 11], 2, True),
        ([2, 8, 15, 22, 30, 40], 2, True),
        # 2연속 허용
        ([1, 2, 10, 20, 30, 40], 2, True),
        ([1, 2, 3, 10, 20, 30], 3, True),
        # 연속 초과
        ([1, 2, 3, 10, 20, 30], 2, False),
        ([1, 2, 3, 4, 10, 20], 3, False),
        ([1, 2, 3, 4, 5, 6], 4, False),  # 6연속
        # 경계 케이스
        ([1, 2, 3, 4, 20, 30], 4, True),  # 정확히 4연속
        ([1, 2, 3, 4, 5, 20], 4, False),  # 5연속
    ])
    def test_consecutive_filter(self, combination, max_consecutive, expected_pass):
        """연속 번호 필터 테스트"""
        def has_too_many_consecutive(combo, max_consec):
            count = 1
            for i in range(1, len(combo)):
                if combo[i] == combo[i-1] + 1:
                    count += 1
                    if count > max_consec:
                        return True
                else:
                    count = 1
            return False

        result = not has_too_many_consecutive(combination, max_consecutive)
        assert result == expected_pass


class TestOddEvenRatio:
    """홀짝 비율 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("combination,expected_pass", [
        # 정상 비율 (1:5 ~ 5:1)
        ([1, 3, 5, 7, 9, 10], True),  # 5:1
        ([2, 4, 6, 8, 10, 11], True),  # 1:5
        ([1, 3, 5, 2, 4, 6], True),  # 3:3
        ([1, 3, 2, 4, 6, 8], True),  # 2:4
        ([1, 3, 5, 7, 2, 4], True),  # 4:2
        # 비정상 비율 (0:6, 6:0)
        ([1, 3, 5, 7, 9, 11], False),  # 6:0 (모두 홀수)
        ([2, 4, 6, 8, 10, 12], False),  # 0:6 (모두 짝수)
    ])
    def test_odd_even_ratio(self, combination, expected_pass):
        """홀짝 비율 필터 테스트"""
        odd_count = sum(1 for n in combination if n % 2 == 1)
        result = 1 <= odd_count <= 5
        assert result == expected_pass


class TestThresholdValues:
    """임계값 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("threshold,expected_valid", [
        # 정상 범위
        (0.5, True),
        (1.0, True),
        (2.0, True),
        (3.0, True),
        (0.3, True),  # 최소값
        # 경계값
        (0.1, True),
        (5.0, True),
        # 비정상 값
        (0.0, False),
        (-0.5, False),
        (-1.0, False),
    ])
    def test_threshold_validation(self, threshold, expected_valid):
        """임계값 유효성 검증"""
        def is_valid_threshold(t):
            return t > 0
        assert is_valid_threshold(threshold) == expected_valid


class TestPerformanceScores:
    """성능 점수 계산 파라미터화 테스트"""

    @pytest.mark.parametrize("avg_matches,expected_normalized", [
        (0.0, 0.0),
        (0.5, 0.25),
        (1.0, 0.5),
        (1.5, 0.75),
        (2.0, 1.0),
        (2.5, 1.0),  # capped at 1.0
        (3.0, 1.0),  # capped at 1.0
    ])
    def test_normalize_score(self, avg_matches, expected_normalized):
        """점수 정규화 테스트"""
        from src.core.performance_metrics import PerformanceMetrics
        result = PerformanceMetrics.normalize_score(avg_matches)
        assert abs(result - expected_normalized) < 0.001


class TestRankCalculation:
    """등수 계산 파라미터화 테스트"""

    @pytest.mark.parametrize("matches,has_bonus,expected_rank", [
        (6, False, 1),  # 1등
        (5, True, 2),   # 2등 (5개 + 보너스)
        (5, False, 3),  # 3등
        (4, False, 4),  # 4등
        (3, False, 5),  # 5등
        (2, False, 0),  # 낙첨
        (1, False, 0),  # 낙첨
        (0, False, 0),  # 낙첨
    ])
    def test_rank_calculation(self, matches, has_bonus, expected_rank):
        """등수 계산 테스트"""
        def calculate_rank(match_count, bonus_match):
            if match_count == 6:
                return 1
            elif match_count == 5 and bonus_match:
                return 2
            elif match_count == 5:
                return 3
            elif match_count == 4:
                return 4
            elif match_count == 3:
                return 5
            return 0

        result = calculate_rank(matches, has_bonus)
        assert result == expected_rank


class TestBatchSizeCalculation:
    """배치 크기 계산 파라미터화 테스트"""

    @pytest.mark.parametrize("total_items,batch_size,expected_batches", [
        (100, 10, 10),
        (100, 30, 4),   # 마지막 배치는 10개
        (100, 100, 1),
        (100, 150, 1),  # batch_size > total
        (0, 10, 0),     # 빈 데이터
        (1, 10, 1),     # 단일 아이템
        (10000, 500, 20),
    ])
    def test_batch_count(self, total_items, batch_size, expected_batches):
        """배치 개수 계산 테스트"""
        import math
        if total_items == 0:
            batches = 0
        else:
            batches = math.ceil(total_items / batch_size)
        assert batches == expected_batches


class TestDecimalPrecision:
    """소수점 정밀도 파라미터화 테스트"""

    @pytest.mark.parametrize("value1,value2,tolerance,expected_equal", [
        (Decimal("0.1") + Decimal("0.2"), Decimal("0.3"), Decimal("0.00000001"), True),
        (Decimal("1.0") / Decimal("3.0") * Decimal("3.0"), Decimal("1.0"), Decimal("0.00000001"), True),
        (Decimal("0.99"), Decimal("1.0"), Decimal("0.001"), False),  # 차이가 0.01
        (Decimal("1.01"), Decimal("1.0"), Decimal("0.001"), False),  # 차이가 0.01
    ])
    def test_decimal_equality(self, value1, value2, tolerance, expected_equal):
        """Decimal 정밀도 테스트"""
        result = abs(value1 - value2) < tolerance
        assert result == expected_equal


class TestNumberDistribution:
    """번호 분포 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("combination,expected_high_low_valid", [
        # 고저 비율 검증 (1-22 vs 23-45)
        ([1, 5, 10, 25, 30, 35], True),   # 3:3
        ([1, 2, 3, 4, 5, 25], True),      # 5:1
        ([25, 30, 35, 40, 42, 45], True), # 0:6 - 극단 but valid
        ([1, 2, 3, 4, 5, 6], True),       # 6:0 - 극단 but valid
    ])
    def test_high_low_distribution(self, combination, expected_high_low_valid):
        """고저 분포 테스트"""
        low_count = sum(1 for n in combination if n <= 22)
        high_count = 6 - low_count
        # 모든 분포 허용 (0:6 ~ 6:0)
        result = 0 <= low_count <= 6
        assert result == expected_high_low_valid


class TestFilterPassRates:
    """필터 통과율 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("passed,total,expected_rate", [
        (100, 1000, 0.1),
        (500, 1000, 0.5),
        (1000, 1000, 1.0),
        (0, 1000, 0.0),
        (1, 10000, 0.0001),
        (333, 1000, 0.333),
    ])
    def test_pass_rate_calculation(self, passed, total, expected_rate):
        """통과율 계산 테스트"""
        rate = passed / total if total > 0 else 0
        assert abs(rate - expected_rate) < 0.001


class TestEdgeCaseCombinations:
    """엣지 케이스 조합 테스트"""

    @pytest.mark.parametrize("numbers,expected_sum", [
        ([1, 2, 3, 4, 5, 6], 21),      # 최소 합계
        ([40, 41, 42, 43, 44, 45], 255),  # 최대 합계
        ([1, 2, 3, 43, 44, 45], 138),  # 양 극단 혼합
        ([22, 23, 24, 25, 26, 27], 147),  # 중간값 연속
    ])
    def test_combination_sums(self, numbers, expected_sum):
        """조합 합계 엣지 케이스"""
        assert sum(numbers) == expected_sum

    @pytest.mark.parametrize("numbers,expected_gap", [
        ([1, 2, 3, 4, 5, 6], 1),       # 최소 갭 (모두 연속)
        ([1, 10, 20, 30, 40, 45], 10), # 큰 갭
        ([1, 45, 2, 44, 3, 43], 40),   # 정렬 후 [1,2,3,43,44,45] -> max gap 40
        ([5, 10, 15, 20, 25, 30], 5),  # 균등 갭
    ])
    def test_max_gap(self, numbers, expected_gap):
        """최대 갭 테스트"""
        sorted_nums = sorted(numbers)
        gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
        max_gap = max(gaps) if gaps else 0
        assert max_gap == expected_gap


class TestRoundValidation:
    """회차 검증 파라미터화 테스트"""

    @pytest.mark.parametrize("round_num,expected_valid", [
        (1, True),
        (100, True),
        (1000, True),
        (1200, True),
        (0, False),
        (-1, False),
        (-100, False),
    ])
    def test_round_number_validity(self, round_num, expected_valid):
        """회차 번호 유효성 테스트"""
        is_valid = round_num > 0
        assert is_valid == expected_valid


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
