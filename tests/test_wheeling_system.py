"""
휠링 시스템 단위 테스트
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimization.wheeling_system import (
    WheelingSystem,
    WheelType,
    WheelPattern,
    WheelResult,
    GuaranteeLevel
)


class TestWheelingSystemBasic:
    """기본 기능 테스트"""

    def setup_method(self):
        """테스트 셋업"""
        self.ws = WheelingSystem()
        self.test_numbers = [3, 7, 12, 17, 23, 28, 33, 38, 42, 45]

    def test_init(self):
        """초기화 테스트"""
        ws = WheelingSystem()
        assert ws is not None
        assert ws.ticket_price == 1000

    def test_generate_wheel_basic(self):
        """기본 휠 생성 테스트"""
        result = self.ws.generate_wheel(self.test_numbers, guarantee=3)

        assert isinstance(result, WheelResult)
        assert result.wheel_type == WheelType.ABBREVIATED
        assert len(result.generated_combinations) > 0
        assert result.guarantee_level == 3
        assert result.estimated_cost == len(result.generated_combinations) * 1000

    def test_generate_wheel_with_guarantee_4(self):
        """4개 보장 휠 테스트"""
        result = self.ws.generate_wheel(self.test_numbers, guarantee=4)

        assert result.guarantee_level == 4
        # 4개 보장은 더 많은 조합 필요
        assert len(result.generated_combinations) > 0

    def test_generate_full_wheel(self):
        """전체 휠 테스트"""
        small_numbers = [1, 2, 3, 4, 5, 6, 7]
        result = self.ws.generate_wheel(
            small_numbers,
            guarantee=3,
            wheel_type=WheelType.FULL
        )

        # 7C6 = 7개 조합
        assert len(result.generated_combinations) == 7
        assert result.wheel_type == WheelType.FULL

    def test_generate_balanced_wheel(self):
        """균형 휠 테스트"""
        result = self.ws.generate_wheel(
            self.test_numbers,
            guarantee=3,
            wheel_type=WheelType.BALANCED,
            max_combinations=15
        )

        assert result.wheel_type == WheelType.BALANCED
        assert len(result.generated_combinations) <= 15

        # 균형 점수 체크
        assert 'balance_score' in result.coverage_analysis

    def test_generate_key_wheel(self):
        """키 번호 휠 테스트"""
        key_numbers = [7, 17, 33]
        pool_numbers = [3, 12, 23, 28, 38, 42, 45]

        result = self.ws.generate_key_wheel(
            key_numbers, pool_numbers, guarantee=3
        )

        assert result.wheel_type == WheelType.KEY
        assert len(result.generated_combinations) > 0

        # 모든 조합에 키 번호 포함 확인
        for combo in result.generated_combinations:
            assert all(k in combo for k in key_numbers)


class TestWheelingSystemValidation:
    """입력 검증 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_minimum_numbers_required(self):
        """최소 번호 개수 검증"""
        with pytest.raises(ValueError, match="최소 6개 이상"):
            self.ws.generate_wheel([1, 2, 3, 4, 5])

    def test_invalid_guarantee(self):
        """잘못된 보장 수 검증"""
        with pytest.raises(ValueError, match="보장 수는 3-6 범위"):
            self.ws.generate_wheel([1, 2, 3, 4, 5, 6, 7], guarantee=2)

        with pytest.raises(ValueError, match="보장 수는 3-6 범위"):
            self.ws.generate_wheel([1, 2, 3, 4, 5, 6, 7], guarantee=7)

    def test_key_wheel_too_many_keys(self):
        """키 번호 초과 검증"""
        with pytest.raises(ValueError, match="키 번호는 5개 이하"):
            self.ws.generate_key_wheel(
                [1, 2, 3, 4, 5, 6],  # 6개 키 번호
                [7, 8, 9, 10]
            )

    def test_key_wheel_insufficient_numbers(self):
        """키 휠 번호 부족 검증"""
        with pytest.raises(ValueError, match="전체 번호가 6개 이상"):
            self.ws.generate_key_wheel([1], [2, 3])


class TestWheelingSystemCoverage:
    """커버리지 분석 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_coverage_analysis(self):
        """커버리지 분석 테스트"""
        numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = self.ws.generate_wheel(numbers, guarantee=3)

        cov = result.coverage_analysis
        assert 'total_combinations' in cov
        assert 'coverage_ratio' in cov
        assert 'covered_subsets' in cov
        assert 'total_subsets' in cov
        assert 'avg_number_frequency' in cov
        assert 'balance_score' in cov

        assert 0 <= cov['coverage_ratio'] <= 1

    def test_full_wheel_full_coverage(self):
        """전체 휠의 완전 커버리지 확인"""
        numbers = [1, 2, 3, 4, 5, 6, 7]
        result = self.ws.generate_wheel(
            numbers, guarantee=3, wheel_type=WheelType.FULL
        )

        # 전체 휠은 100% 커버리지
        assert result.coverage_analysis['coverage_ratio'] == 1.0


class TestWheelingSystemExpectedReturn:
    """기대 수익 계산 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_expected_return_calculation(self):
        """기대 수익 계산 테스트"""
        numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = self.ws.generate_wheel(numbers, guarantee=3, max_combinations=10)

        expected = self.ws.calculate_expected_return(result)

        assert 'total_cost' in expected
        assert 'total_expected_value' in expected
        assert 'net_expected_value' in expected
        assert 'roi_percent' in expected
        assert 'breakdown' in expected

        assert expected['total_cost'] == len(result.generated_combinations) * 1000

    def test_expected_return_custom_probability(self):
        """커스텀 확률로 기대 수익 계산"""
        numbers = [1, 2, 3, 4, 5, 6, 7]
        result = self.ws.generate_wheel(numbers, guarantee=3, wheel_type=WheelType.FULL)

        custom_prob = {3: 0.02, 4: 0.001, 5: 0.00002, 6: 0.000000015}
        expected = self.ws.calculate_expected_return(result, custom_prob)

        assert expected['total_cost'] > 0
        assert '3개_일치' in expected['breakdown']


class TestWheelingSystemPredictionOptimization:
    """ML 예측 기반 최적화 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_optimize_from_predictions(self):
        """예측 기반 최적화 테스트"""
        predictions = [
            [1, 5, 10, 15, 20, 25],
            [1, 5, 12, 18, 22, 30],
            [1, 5, 10, 17, 25, 35],
            [2, 5, 10, 15, 28, 40],
            [1, 8, 10, 15, 25, 45],
        ]

        result = self.ws.optimize_from_predictions(
            predictions, top_n=5, guarantee=3, max_combinations=20
        )

        assert len(result.generated_combinations) <= 20
        assert result.guarantee_level == 3

    def test_optimize_empty_predictions(self):
        """빈 예측으로 최적화 시도"""
        with pytest.raises(ValueError, match="예측 결과가 없습니다"):
            self.ws.optimize_from_predictions([])


class TestWheelingSystemOutput:
    """출력 포맷 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_format_wheel_output(self):
        """출력 포맷 테스트"""
        numbers = [1, 2, 3, 4, 5, 6, 7]
        result = self.ws.generate_wheel(numbers, guarantee=3, wheel_type=WheelType.FULL)

        output = self.ws.format_wheel_output(result)

        assert "휠링 시스템 결과" in output
        assert "입력 번호" in output
        assert "보장 등급" in output
        assert "커버리지 분석" in output
        assert "기대 수익 분석" in output

    def test_format_without_analysis(self):
        """분석 없이 출력 테스트"""
        numbers = [1, 2, 3, 4, 5, 6, 7]
        result = self.ws.generate_wheel(numbers, guarantee=3, wheel_type=WheelType.FULL)

        output = self.ws.format_wheel_output(result, include_analysis=False)

        assert "휠링 시스템 결과" in output
        assert "커버리지 분석" not in output


class TestWheelPattern:
    """WheelPattern 데이터 클래스 테스트"""

    def test_wheel_pattern_creation(self):
        """WheelPattern 생성 테스트"""
        pattern = WheelPattern(
            name="Test-7-6-3",
            numbers_selected=7,
            numbers_per_combo=6,
            guarantee=3,
            combinations_count=4,
            pattern=[(0,1,2,3,4,5), (0,1,2,3,4,6)]
        )

        assert pattern.name == "Test-7-6-3"
        assert pattern.numbers_selected == 7
        assert pattern.combinations_count == 4
        assert len(pattern.pattern) == 2

    def test_wheel_pattern_str(self):
        """WheelPattern 문자열 표현 테스트"""
        pattern = WheelPattern(
            name="8-6-3",
            numbers_selected=8,
            numbers_per_combo=6,
            guarantee=3,
            combinations_count=6
        )

        str_repr = str(pattern)
        assert "8-6-3" in str_repr
        assert "8개" in str_repr
        assert "6조합" in str_repr


class TestWheelingSystemIntegration:
    """통합 테스트"""

    def setup_method(self):
        self.ws = WheelingSystem()

    def test_real_world_scenario(self):
        """실제 시나리오 테스트"""
        # 사용자가 10개 번호를 선택하고 4등 보장 휠 생성
        my_numbers = [3, 7, 12, 17, 23, 28, 33, 38, 42, 45]
        result = self.ws.generate_wheel(my_numbers, guarantee=3, max_combinations=20)

        # 조합 검증
        for combo in result.generated_combinations:
            assert len(combo) == 6
            assert all(1 <= n <= 45 for n in combo)
            assert all(n in my_numbers for n in combo)

        # 비용 검증
        assert result.estimated_cost <= 20000

    def test_key_number_strategy(self):
        """키 번호 전략 테스트"""
        # 통계적으로 유망한 번호 3개를 키 번호로 설정
        key = [17, 33, 40]  # Hot 번호
        pool = [3, 7, 12, 23, 28, 38, 42, 45]  # Cold/Neutral 번호

        result = self.ws.generate_key_wheel(key, pool, guarantee=3)

        # 모든 조합에 키 번호 포함 확인
        for combo in result.generated_combinations:
            assert 17 in combo
            assert 33 in combo
            assert 40 in combo


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
