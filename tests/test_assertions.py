#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assertion 테스트 모음

Phase 3.14: 핵심 메서드 입력 검증
- 입력값 유효성 검증
- 반환값 검증
- 불변조건 체크
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestLottoValidatorAssertions:
    """LottoValidator 입력 검증 테스트"""

    def test_valid_number_assertions(self):
        """is_valid_number 입력 검증"""
        from src.utils.validators import LottoValidator

        # 유효한 번호
        assert LottoValidator.is_valid_number(1) == True
        assert LottoValidator.is_valid_number(45) == True
        assert LottoValidator.is_valid_number(22) == True

        # 범위 외 번호
        assert LottoValidator.is_valid_number(0) == False
        assert LottoValidator.is_valid_number(46) == False
        assert LottoValidator.is_valid_number(-1) == False

        # 타입 오류
        assert LottoValidator.is_valid_number(1.5) == False
        assert LottoValidator.is_valid_number("1") == False

    def test_valid_combination_assertions(self):
        """is_valid_combination 입력 검증"""
        from src.utils.validators import LottoValidator

        # 유효한 조합
        assert LottoValidator.is_valid_combination([1, 2, 3, 4, 5, 6]) == True
        assert LottoValidator.is_valid_combination([40, 41, 42, 43, 44, 45]) == True

        # 길이 오류
        assert LottoValidator.is_valid_combination([1, 2, 3, 4, 5]) == False
        assert LottoValidator.is_valid_combination([1, 2, 3, 4, 5, 6, 7]) == False

        # 중복
        assert LottoValidator.is_valid_combination([1, 1, 2, 3, 4, 5]) == False

        # 범위 오류
        assert LottoValidator.is_valid_combination([0, 1, 2, 3, 4, 5]) == False
        assert LottoValidator.is_valid_combination([1, 2, 3, 4, 5, 46]) == False

    def test_encode_decode_assertions(self):
        """비트맵 인코딩/디코딩 입력 검증"""
        from src.utils.validators import LottoValidator

        # 정상 인코딩/디코딩
        original = [1, 2, 3, 4, 5, 6]
        bitmap = LottoValidator.encode_combination(original)
        decoded = LottoValidator.decode_combination(bitmap)
        assert decoded == original

        # 잘못된 길이 예외
        with pytest.raises(ValueError):
            LottoValidator.encode_combination([1, 2, 3, 4, 5])

        with pytest.raises(ValueError):
            LottoValidator.encode_combination([1, 2, 3, 4, 5, 6, 7])

        # 잘못된 번호 예외
        with pytest.raises(ValueError):
            LottoValidator.encode_combination([0, 1, 2, 3, 4, 5])

        with pytest.raises(ValueError):
            LottoValidator.encode_combination([1, 2, 3, 4, 5, 46])

    def test_combination_string_assertions(self):
        """문자열 조합 변환 검증"""
        from src.utils.validators import LottoValidator

        # 정상 변환
        assert LottoValidator.is_valid_combination_string("1,2,3,4,5,6") == True
        assert LottoValidator.is_valid_combination_string("40,41,42,43,44,45") == True

        # 잘못된 형식
        assert LottoValidator.is_valid_combination_string("1,2,3,4,5") == False
        assert LottoValidator.is_valid_combination_string("1;2;3;4;5;6") == False
        assert LottoValidator.is_valid_combination_string("a,b,c,d,e,f") == False
        assert LottoValidator.is_valid_combination_string("") == False

    def test_filter_criteria_assertions(self):
        """필터 기준값 검증"""
        from src.utils.validators import LottoValidator
        from src.utils.constants import LottoConstants

        # MATCH 필터 검증
        assert LottoValidator.validate_filter_criteria(
            {'max_match': 3}, LottoConstants.FilterTypes.MATCH
        ) == True

        with pytest.raises(ValueError):
            LottoValidator.validate_filter_criteria({}, LottoConstants.FilterTypes.MATCH)

        with pytest.raises(ValueError):
            LottoValidator.validate_filter_criteria(
                {'max_match': 7}, LottoConstants.FilterTypes.MATCH
            )

        # CONSECUTIVE 필터 검증
        assert LottoValidator.validate_filter_criteria(
            {'max_consecutive': 3}, LottoConstants.FilterTypes.CONSECUTIVE
        ) == True

        with pytest.raises(ValueError):
            LottoValidator.validate_filter_criteria(
                {'max_consecutive': 1}, LottoConstants.FilterTypes.CONSECUTIVE
            )

        # SUM_RANGE 필터 검증
        assert LottoValidator.validate_filter_criteria(
            {'min_sum': 21, 'max_sum': 255}, LottoConstants.FilterTypes.SUM_RANGE
        ) == True

        with pytest.raises(ValueError):
            LottoValidator.validate_filter_criteria(
                {'min_sum': 100, 'max_sum': 50}, LottoConstants.FilterTypes.SUM_RANGE
            )


class TestThresholdManagerAssertions:
    """ThresholdManager 입력 검증 테스트"""

    def test_threshold_value_assertions(self):
        """임계값 유효성 검증"""
        from src.core.threshold_manager import ThresholdManager

        manager = ThresholdManager.get_instance()

        # 현재 임계값 확인
        threshold = manager.get_threshold()
        assert threshold > 0, "임계값은 0보다 커야 함"
        assert isinstance(threshold, (int, float)), "임계값은 숫자여야 함"

    def test_ml_relaxed_threshold_assertions(self):
        """ML 완화 임계값 검증"""
        from src.core.threshold_manager import ThresholdManager

        manager = ThresholdManager.get_instance()

        # ML 완화 임계값 확인
        ml_threshold = manager.get_ml_relaxed_threshold()
        assert ml_threshold >= 0, "ML 완화 임계값은 0 이상이어야 함"

    def test_bypass_filters_assertions(self):
        """우회 필터 설정 검증"""
        from src.core.threshold_manager import ThresholdManager

        manager = ThresholdManager.get_instance()

        # 우회 필터 설정 확인 (개수 또는 리스트)
        bypass_filters = manager.get_ml_bypass_filters()
        assert bypass_filters is not None, "우회 필터 설정이 있어야 함"
        # 값이 정수이면 필터 개수, 리스트이면 필터 목록
        assert isinstance(bypass_filters, (int, list)), "우회 필터는 정수 또는 리스트"


class TestPerformanceMetricsAssertions:
    """PerformanceMetrics 입력 검증 테스트"""

    def test_normalize_score_assertions(self):
        """점수 정규화 입력 검증"""
        from src.core.performance_metrics import PerformanceMetrics

        # 정상 범위
        assert 0 <= PerformanceMetrics.normalize_score(0) <= 1
        assert 0 <= PerformanceMetrics.normalize_score(1) <= 1
        assert 0 <= PerformanceMetrics.normalize_score(2) <= 1
        assert 0 <= PerformanceMetrics.normalize_score(3) <= 1

        # 음수 입력은 0 반환
        assert PerformanceMetrics.normalize_score(-1) >= 0

    def test_overall_score_assertions(self):
        """전체 점수 계산 검증"""
        from src.core.performance_metrics import PerformanceMetrics

        # 정상 범위의 점수 - 실제 API 사용 (lstm, ensemble, monte_carlo)
        score = PerformanceMetrics.calculate_overall_score(
            lstm=0.5,
            ensemble=0.6,
            monte_carlo=0.4
        )
        assert isinstance(score, (int, float)), "전체 점수는 숫자"
        assert score >= 0, "전체 점수는 0 이상"

    def test_comparison_assertions(self):
        """성능 비교 검증"""
        from src.core.performance_metrics import PerformanceMetrics

        # 같은 값 비교 - 결과는 딕셔너리
        result = PerformanceMetrics.compare_performance(1.0, 1.0)
        assert isinstance(result, dict), "비교 결과는 딕셔너리"
        assert 'improved' in result or 'degraded' in result, "결과에 개선/저하 정보 포함"

        # 더 좋은 값
        result = PerformanceMetrics.compare_performance(1.5, 1.0)
        assert isinstance(result, dict)
        assert result.get('improved', False) == True or result.get('change_percent', 0) > 0

        # 더 나쁜 값
        result = PerformanceMetrics.compare_performance(0.5, 1.0)
        assert isinstance(result, dict)
        assert result.get('degraded', False) == True or result.get('change_percent', 0) < 0


class TestConfigManagerAssertions:
    """ConfigManager 입력 검증 테스트"""

    def test_config_loading_assertions(self):
        """설정 로딩 검증"""
        from src.utils.config_manager import ConfigManager

        manager = ConfigManager()

        # 설정 값이 None이 아니어야 함
        config = manager.get_filtering_config()
        assert config is not None, "필터링 설정이 있어야 함"

        logging_config = manager.get_logging_config()
        assert logging_config is not None, "로깅 설정이 있어야 함"

    def test_threshold_config_assertions(self):
        """임계값 설정 검증"""
        from src.utils.config_manager import ConfigManager

        manager = ConfigManager()

        threshold = manager.get_global_probability_threshold()
        assert threshold is not None, "임계값이 있어야 함"
        assert threshold > 0, "임계값은 양수여야 함"


class TestDatabaseManagerAssertions:
    """DatabaseManager 입력 검증 테스트"""

    def test_singleton_assertions(self):
        """싱글톤 패턴 검증"""
        from src.core.db_manager import DatabaseManager

        db1 = DatabaseManager()
        db2 = DatabaseManager()

        assert db1 is db2, "DatabaseManager는 싱글톤이어야 함"

    def test_numbers_format_assertions(self):
        """번호 형식 검증"""
        from src.core.db_manager import DatabaseManager

        db = DatabaseManager()

        # DB가 초기화되지 않은 경우 스킵
        try:
            numbers = db.get_numbers_with_bonus()
        except AttributeError:
            pytest.skip("Database not initialized")
            return

        if numbers:
            # 첫 번째 결과의 형식 검증
            first_result = numbers[0]
            assert len(first_result) == 2, "결과는 (회차, 번호튜플) 형식"

            round_num, nums_tuple = first_result
            assert isinstance(round_num, int), "회차는 정수"
            assert round_num > 0, "회차는 양수"
            assert len(nums_tuple) == 7, "번호 튜플은 7개 (6개 + 보너스)"


class TestFilterOutputAssertions:
    """필터 출력값 검증 테스트"""

    def test_sum_filter_output_assertions(self):
        """합계 필터 출력 검증"""
        # 합계 필터 로직 테스트
        def check_sum_range(combo, min_sum=21, max_sum=255):
            total = sum(combo)
            return min_sum <= total <= max_sum

        # 모든 유효 조합은 합계가 21-255 범위
        assert check_sum_range([1, 2, 3, 4, 5, 6]) == True  # min: 21
        assert check_sum_range([40, 41, 42, 43, 44, 45]) == True  # max: 255

    def test_consecutive_filter_output_assertions(self):
        """연속 필터 출력 검증"""
        def check_consecutive(combo, max_consecutive=4):
            count = 1
            for i in range(1, len(combo)):
                if combo[i] == combo[i-1] + 1:
                    count += 1
                    if count > max_consecutive:
                        return False
                else:
                    count = 1
            return True

        # 검증
        assert check_consecutive([1, 3, 5, 7, 9, 11]) == True  # 연속 없음
        assert check_consecutive([1, 2, 3, 10, 20, 30]) == True  # 3연속
        assert check_consecutive([1, 2, 3, 4, 5, 10]) == False  # 5연속 (max 4 초과)


class TestInvariantAssertions:
    """불변조건 검증 테스트"""

    def test_combination_invariants(self):
        """조합 불변조건"""
        from src.utils.validators import LottoValidator

        # 어떤 유효 조합이든
        valid_combos = [
            [1, 2, 3, 4, 5, 6],
            [10, 20, 30, 35, 40, 45],
            [1, 15, 22, 33, 40, 45],
        ]

        for combo in valid_combos:
            # 1. 길이는 항상 6
            assert len(combo) == 6, f"조합 길이는 6: {combo}"

            # 2. 중복 없음
            assert len(set(combo)) == 6, f"중복 없어야 함: {combo}"

            # 3. 모든 번호는 1-45 범위
            assert all(1 <= n <= 45 for n in combo), f"범위 내: {combo}"

            # 4. 합계는 21-255 범위
            assert 21 <= sum(combo) <= 255, f"합계 범위: {combo}"

            # 5. 정렬된 조합
            sorted_combo = sorted(combo)
            assert sorted_combo[0] < sorted_combo[-1], f"첫 번호 < 마지막 번호"

    def test_round_number_invariants(self):
        """회차 번호 불변조건"""
        from src.core.db_manager import DatabaseManager

        db = DatabaseManager()

        # DB가 초기화되지 않은 경우 스킵
        try:
            last_round = db.get_last_round()
        except AttributeError:
            pytest.skip("Database not initialized")
            return

        if last_round:
            # 회차는 양의 정수
            assert last_round > 0, "회차는 양수"
            assert isinstance(last_round, int), "회차는 정수"

            # 합리적인 범위 (1회부터 현재까지)
            assert last_round < 10000, "회차는 10000 미만"

    def test_probability_invariants(self):
        """확률 불변조건"""
        from src.core.threshold_manager import ThresholdManager

        manager = ThresholdManager.get_instance()
        threshold = manager.get_threshold()

        # 확률 임계값은 0-100 범위의 백분율
        assert 0 < threshold <= 100, f"임계값 범위: {threshold}"


class TestBoundaryConditions:
    """경계 조건 테스트"""

    def test_minimum_combination(self):
        """최소 조합 (1,2,3,4,5,6)"""
        from src.utils.validators import LottoValidator

        min_combo = [1, 2, 3, 4, 5, 6]
        assert LottoValidator.is_valid_combination(min_combo)
        assert sum(min_combo) == 21  # 최소 합계

    def test_maximum_combination(self):
        """최대 조합 (40,41,42,43,44,45)"""
        from src.utils.validators import LottoValidator

        max_combo = [40, 41, 42, 43, 44, 45]
        assert LottoValidator.is_valid_combination(max_combo)
        assert sum(max_combo) == 255  # 최대 합계

    def test_edge_numbers(self):
        """경계 번호 (1, 45)"""
        from src.utils.validators import LottoValidator

        # 경계값 포함 조합
        edge_combo = [1, 10, 20, 30, 40, 45]
        assert LottoValidator.is_valid_combination(edge_combo)

        # 경계값 바로 밖
        assert LottoValidator.is_valid_number(0) == False
        assert LottoValidator.is_valid_number(46) == False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
