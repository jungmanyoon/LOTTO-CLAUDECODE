"""
AC값(Arithmetic Complexity) 필터 단위 테스트
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.filters.ac_value_filter import ACValueFilter


class TestACValueCalculation:
    """AC값 계산 로직 테스트"""

    def test_ac_value_arithmetic_sequence(self):
        """등차수열은 낮은 AC값을 가져야 함"""
        # 1, 2, 3, 4, 5, 6 -> 차이: {1} -> D=1 -> AC=1-5=-4 (최소 0)
        # 실제로는 차이값이 {1,2,3,4,5}가 됨
        numbers = [1, 2, 3, 4, 5, 6]
        ac = ACValueFilter.calculate_ac_value(numbers)
        # 차이: 1-2=1, 1-3=2, 1-4=3, 1-5=4, 1-6=5, 2-3=1(중복), 2-4=2(중복)...
        # 고유 차이: {1,2,3,4,5} = 5개 -> AC = 5-5 = 0
        assert ac == 0, f"등차수열 1-6의 AC값은 0이어야 함, 실제: {ac}"

    def test_ac_value_step_5(self):
        """5 간격 등차수열 테스트"""
        numbers = [5, 10, 15, 20, 25, 30]
        ac = ACValueFilter.calculate_ac_value(numbers)
        # 차이: {5, 10, 15, 20, 25} = 5개 -> AC = 5-5 = 0
        assert ac == 0, f"5 간격 등차수열의 AC값은 0이어야 함, 실제: {ac}"

    def test_ac_value_high_randomness(self):
        """무작위 패턴은 높은 AC값을 가져야 함"""
        numbers = [3, 17, 25, 31, 38, 44]
        ac = ACValueFilter.calculate_ac_value(numbers)
        # 무작위 패턴은 다양한 차이값을 가짐 -> 높은 AC값
        assert ac >= 7, f"무작위 패턴의 AC값은 7 이상이어야 함, 실제: {ac}"

    def test_ac_value_range(self):
        """AC값은 0-10 범위여야 함"""
        # 다양한 조합 테스트
        test_cases = [
            [1, 2, 3, 4, 5, 6],
            [1, 10, 20, 30, 40, 45],
            [7, 14, 21, 28, 35, 42],
            [2, 11, 19, 28, 37, 45],
        ]

        for numbers in test_cases:
            ac = ACValueFilter.calculate_ac_value(numbers)
            assert 0 <= ac <= 10, f"AC값이 범위를 벗어남: {ac} (조합: {numbers})"

    def test_ac_value_maximum(self):
        """최대 AC값(10) 테스트"""
        # 15개의 모든 차이가 고유한 경우: D=15 -> AC=15-5=10
        # 예: 매우 불규칙한 조합
        numbers = [1, 3, 7, 15, 31, 45]
        ac = ACValueFilter.calculate_ac_value(numbers)
        assert ac <= 10, f"AC값이 최대값 10을 초과함: {ac}"

    def test_ac_value_invalid_input(self):
        """잘못된 입력에 대한 예외 처리"""
        with pytest.raises(ValueError):
            ACValueFilter.calculate_ac_value([1, 2, 3, 4, 5])  # 5개만

        with pytest.raises(ValueError):
            ACValueFilter.calculate_ac_value([1, 2, 3, 4, 5, 6, 7])  # 7개


class TestACValueVectorized:
    """벡터화된 AC값 계산 테스트"""

    def test_vectorized_calculation(self):
        """벡터화 계산이 단일 계산과 동일한 결과를 반환"""
        test_combinations = [
            [1, 2, 3, 4, 5, 6],
            [5, 10, 15, 20, 25, 30],
            [3, 17, 25, 31, 38, 44],
        ]

        # numpy 배열로 변환
        arr = np.array(test_combinations, dtype=np.int8)

        # 벡터화된 계산
        vectorized_results = ACValueFilter.calculate_ac_value_vectorized(arr)

        # 단일 계산과 비교
        for i, numbers in enumerate(test_combinations):
            single_result = ACValueFilter.calculate_ac_value(numbers)
            assert vectorized_results[i] == single_result, \
                f"벡터화 결과가 단일 계산과 다름: {vectorized_results[i]} vs {single_result}"


class TestACValueFilter:
    """AC값 필터 적용 테스트"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock DB Manager"""
        mock = Mock()
        mock.get_all_winning_numbers = Mock(return_value=[
            (3, 17, 25, 31, 38, 44),  # 높은 AC
            (1, 2, 3, 4, 5, 6),       # 낮은 AC
        ])
        return mock

    @pytest.fixture
    def ac_filter(self, mock_db_manager):
        """AC값 필터 인스턴스"""
        return ACValueFilter(mock_db_manager, {'min_ac': 7, 'max_ac': 10})

    def test_filter_initialization(self, ac_filter):
        """필터 초기화 테스트"""
        assert ac_filter._criteria['min_ac'] == 7
        assert ac_filter._criteria['max_ac'] == 10
        assert ac_filter._criteria['use_scoring'] == False

    def test_filter_validation(self, mock_db_manager):
        """기준값 유효성 검증 테스트"""
        # 유효한 기준
        filter1 = ACValueFilter(mock_db_manager, {'min_ac': 0, 'max_ac': 10})
        assert filter1._criteria['min_ac'] == 0

        # 잘못된 범위
        with pytest.raises(ValueError):
            ACValueFilter(mock_db_manager, {'min_ac': 8, 'max_ac': 5})

        # 범위 초과
        with pytest.raises(ValueError):
            ACValueFilter(mock_db_manager, {'min_ac': -1, 'max_ac': 10})

    def test_apply_filter(self, ac_filter):
        """필터 적용 테스트"""
        # 테스트 조합
        combinations = [
            "1,2,3,4,5,6",      # AC=0 (제외됨)
            "5,10,15,20,25,30", # AC=0 (제외됨)
            "3,17,25,31,38,44", # AC>=7 (통과)
        ]

        result = ac_filter.apply(combinations, round_num=1)

        # 낮은 AC값 조합은 제외되어야 함
        assert "1,2,3,4,5,6" not in result
        assert "5,10,15,20,25,30" not in result
        # 높은 AC값 조합은 유지되어야 함
        assert "3,17,25,31,38,44" in result

    def test_get_ac_score(self, ac_filter):
        """점수화 테스트"""
        # 낮은 AC값 -> 낮은 점수
        score_low = ac_filter.get_ac_score([1, 2, 3, 4, 5, 6])
        assert score_low <= 20, f"낮은 AC값의 점수가 너무 높음: {score_low}"

        # 높은 AC값 -> 높은 점수
        score_high = ac_filter.get_ac_score([3, 17, 25, 31, 38, 44])
        assert score_high >= 70, f"높은 AC값의 점수가 너무 낮음: {score_high}"


class TestACValueFilterIntegration:
    """AC값 필터 통합 테스트"""

    @pytest.fixture
    def mock_db_manager(self):
        mock = Mock()
        mock.get_all_winning_numbers = Mock(return_value=[])
        return mock

    def test_process_chunk(self):
        """청크 처리 테스트"""
        combinations = [
            "1,2,3,4,5,6",
            "3,17,25,31,38,44",
            "7,14,21,28,35,42",
        ]

        # min_ac=7로 필터링
        result = ACValueFilter._process_chunk(combinations, min_ac=7, max_ac=10)

        # 등차수열(AC=0)은 제외되어야 함
        assert "1,2,3,4,5,6" not in result
        assert "7,14,21,28,35,42" not in result  # 7의 배수, AC 낮음

    def test_empty_input(self, mock_db_manager):
        """빈 입력 처리 테스트"""
        ac_filter = ACValueFilter(mock_db_manager)
        result = ac_filter.apply([], round_num=1)
        assert result == []

    def test_large_batch(self, mock_db_manager):
        """대량 배치 처리 테스트"""
        import random
        random.seed(42)

        # 1000개의 랜덤 조합 생성
        combinations = []
        for _ in range(1000):
            nums = sorted(random.sample(range(1, 46), 6))
            combinations.append(",".join(map(str, nums)))

        ac_filter = ACValueFilter(mock_db_manager, {'min_ac': 7, 'max_ac': 10})
        result = ac_filter.apply(combinations, round_num=1)

        # 결과가 원본보다 작아야 함 (일부 조합이 제외됨)
        assert len(result) <= len(combinations)
        # 모든 결과가 유효한 형식이어야 함
        for comb in result:
            nums = list(map(int, comb.split(',')))
            assert len(nums) == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
