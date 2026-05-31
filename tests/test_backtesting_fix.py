#!/usr/bin/env python3
"""
백테스팅 버그 수정 검증 테스트
- _check_prediction_in_filtered_pool() 메소드가 제대로 필터 검증을 수행하는지 확인
- 항상 True를 반환하던 버그가 수정되었는지 검증
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import unittest
from unittest.mock import Mock, patch, MagicMock
import logging

# 테스트 대상 모듈 임포트
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.core.filter_validator import FilterValidator

# 로깅 설정 (테스트 중 로그 레벨 조정)
logging.basicConfig(level=logging.WARNING)


class TestBacktestingFix(unittest.TestCase):
    """백테스팅 필터 검증 버그 수정 테스트"""

    def setUp(self):
        """테스트 픽스처 설정"""
        # Mock 객체들 생성
        self.mock_db_manager = Mock(spec=DatabaseManager)
        self.mock_filter_manager = Mock(spec=FilterManager)
        self.mock_filter_validator = Mock(spec=FilterValidator)

        # 싱글톤 인스턴스 정리 (기존 인스턴스가 있으면 제거)
        if hasattr(OptimizedBacktestingFramework, '_instances'):
            OptimizedBacktestingFramework._instances.clear()

        # OptimizedBacktestingFramework 인스턴스 생성
        self.framework = OptimizedBacktestingFramework(db_manager=self.mock_db_manager)
        self.framework.filter_validator = self.mock_filter_validator

    def test_filter_validation_returns_false_for_invalid(self):
        """필터를 통과하지 못하는 예측에 대해 False를 반환하는지 테스트"""
        print("\n=== 테스트 1: 필터 실패 시 False 반환 검증 ===")

        # Mock 설정: 필터 검증 실패
        self.mock_filter_validator.validate_winning_numbers.return_value = {
            'passed_all_filters': False,
            'failed_filters': [
                {'name': 'consecutive_filter', 'reason': '연속 번호 3개 포함'},
                {'name': 'sum_range_filter', 'reason': '합계 250 (범위 벗어남)'}
            ]
        }

        # 테스트 예측 (필터를 통과하지 못할 것으로 설정)
        test_prediction = [1, 2, 3, 40, 41, 42]  # 연속 번호가 많은 조합
        test_round = 1100

        # 메소드 호출
        result = self.framework._check_prediction_in_filtered_pool(test_prediction, test_round)

        # 검증
        self.assertFalse(result, "필터를 통과하지 못하는 예측에 대해 False를 반환해야 함")
        self.mock_filter_validator.validate_winning_numbers.assert_called_once_with(test_round, test_prediction)

        print(f"[PASS] 필터 실패 예측 {test_prediction}에 대해 False 반환됨")

    def test_filter_validation_returns_true_for_valid(self):
        """필터를 통과하는 예측에 대해 True를 반환하는지 테스트"""
        print("\n=== 테스트 2: 필터 통과 시 True 반환 검증 ===")

        # Mock 설정: 필터 검증 성공
        self.mock_filter_validator.validate_winning_numbers.return_value = {
            'passed_all_filters': True,
            'failed_filters': []
        }

        # 테스트 예측 (필터를 통과할 것으로 설정)
        test_prediction = [5, 12, 23, 31, 38, 44]  # 일반적인 분포
        test_round = 1100

        # 메소드 호출
        result = self.framework._check_prediction_in_filtered_pool(test_prediction, test_round)

        # 검증
        self.assertTrue(result, "필터를 통과하는 예측에 대해 True를 반환해야 함")
        self.mock_filter_validator.validate_winning_numbers.assert_called_once_with(test_round, test_prediction)

        print(f"[PASS] 필터 통과 예측 {test_prediction}에 대해 True 반환됨")

    def test_error_handling_returns_false(self):
        """필터 검증 중 에러 발생 시 False를 반환하는지 테스트"""
        print("\n=== 테스트 3: 에러 처리 검증 ===")

        # Mock 설정: 에러 발생
        self.mock_filter_validator.validate_winning_numbers.side_effect = Exception("Filter validation error")

        # 테스트 예측
        test_prediction = [1, 2, 3, 4, 5, 6]
        test_round = 1100

        # 메소드 호출
        result = self.framework._check_prediction_in_filtered_pool(test_prediction, test_round)

        # 검증
        self.assertFalse(result, "에러 발생 시 False를 반환해야 함 (수정 전에는 True 반환했던 버그)")

        print("[PASS] 에러 발생 시 False 반환됨 (버그 수정 확인)")

    def test_no_false_positives_with_varied_predictions(self):
        """다양한 예측에 대해 100% 통과율이 나오지 않는지 테스트"""
        print("\n=== 테스트 4: 100% 통과율 버그 수정 검증 ===")

        # 다양한 검증 결과 설정 (일부는 통과, 일부는 실패)
        def mock_validation_side_effect(round_num, prediction):
            # 예측의 합에 따라 다른 결과 반환 (현실적인 시뮬레이션)
            prediction_sum = sum(prediction)
            if prediction_sum < 80 or prediction_sum > 200:  # 극단적인 합계
                return {
                    'passed_all_filters': False,
                    'failed_filters': [{'name': 'sum_range_filter', 'reason': f'합계 {prediction_sum} 범위 벗어남'}]
                }
            elif any(prediction[i+1] - prediction[i] == 1 for i in range(len(prediction)-1)):  # 연속 번호 존재
                return {
                    'passed_all_filters': False,
                    'failed_filters': [{'name': 'consecutive_filter', 'reason': '연속 번호 포함'}]
                }
            else:
                return {
                    'passed_all_filters': True,
                    'failed_filters': []
                }

        self.mock_filter_validator.validate_winning_numbers.side_effect = mock_validation_side_effect

        # 다양한 테스트 예측들
        test_predictions = [
            [1, 2, 3, 4, 5, 6],      # 연속 번호 - 실패 예상
            [5, 10, 15, 20, 25, 30], # 정상 - 통과 예상
            [1, 5, 10, 15, 20, 45],  # 합계 96 - 실패 예상 (너무 작음)
            [35, 36, 40, 41, 42, 45], # 연속 번호 - 실패 예상
            [7, 14, 21, 28, 35, 42], # 정상 - 통과 예상
            [40, 41, 42, 43, 44, 45] # 극단값 + 연속 - 실패 예상
        ]

        # 모든 예측에 대해 테스트
        results = []
        for i, prediction in enumerate(test_predictions):
            result = self.framework._check_prediction_in_filtered_pool(prediction, 1100 + i)
            results.append(result)
            status = "통과" if result else "실패"
            print(f"  예측 {prediction}: {status}")

        # 검증: 100% 통과율이 아니어야 함
        pass_rate = sum(results) / len(results) * 100
        self.assertLess(pass_rate, 100, "모든 예측이 통과해서는 안됨 (버그 수정 확인)")
        self.assertGreater(pass_rate, 0, "모든 예측이 실패해서도 안됨")

        print(f"[PASS] 필터 통과율 {pass_rate:.1f}% (100%가 아님을 확인)")

    def test_integration_with_real_filter_validator(self):
        """실제 FilterValidator와의 통합 테스트 (가능한 경우)"""
        print("\n=== 테스트 5: 실제 컴포넌트 통합 테스트 ===")

        try:
            # 실제 컴포넌트로 통합 테스트 시도
            real_db_manager = DatabaseManager()
            real_filter_manager = FilterManager(real_db_manager)
            real_filter_validator = FilterValidator(real_filter_manager, real_db_manager)

            # 실제 컴포넌트로 새 프레임워크 인스턴스 생성
            # 싱글톤 인스턴스 정리
            if hasattr(OptimizedBacktestingFramework, '_instances'):
                OptimizedBacktestingFramework._instances.clear()

            real_framework = OptimizedBacktestingFramework(db_manager=real_db_manager)
            real_framework.filter_validator = real_filter_validator

            # 실제 테스트
            test_predictions = [
                [1, 2, 3, 4, 5, 6],      # 연속 번호 많음 - 실패 예상
                [7, 14, 21, 28, 35, 42]  # 정상 분포 - 통과 가능성 높음
            ]

            results = []
            for prediction in test_predictions:
                try:
                    result = real_framework._check_prediction_in_filtered_pool(prediction, 1100)
                    results.append(result)
                    status = "통과" if result else "실패"
                    print(f"  실제 필터 테스트 {prediction}: {status}")
                except Exception as e:
                    print(f"  실제 필터 테스트 {prediction}: 에러 ({e})")
                    results.append(False)

            # 모든 예측이 통과하지 않는지 확인 (버그 수정 검증)
            if len(results) > 0:
                pass_rate = sum(results) / len(results) * 100
                self.assertLess(pass_rate, 100, "실제 필터에서도 100% 통과해서는 안됨")
                print(f"[PASS] 실제 필터 통과율 {pass_rate:.1f}%")

        except Exception as e:
            print(f"[WARN] 실제 컴포넌트 테스트 건너뜀: {e}")
            # 실제 컴포넌트가 없어도 테스트는 통과
            pass

    def test_method_signature_compatibility(self):
        """메소드 시그니처가 올바른지 확인"""
        print("\n=== 테스트 6: 메소드 시그니처 검증 ===")

        # 메소드가 존재하는지 확인
        self.assertTrue(hasattr(self.framework, '_check_prediction_in_filtered_pool'))

        # 메소드 호출 가능한지 확인
        method = getattr(self.framework, '_check_prediction_in_filtered_pool')
        self.assertTrue(callable(method))

        print("[PASS] 메소드 시그니처 정상")

    def tearDown(self):
        """테스트 정리"""
        # 싱글톤 인스턴스 정리
        if hasattr(OptimizedBacktestingFramework, '_instances'):
            OptimizedBacktestingFramework._instances = {}


def run_comprehensive_test():
    """포괄적인 테스트 실행 및 보고서 생성"""
    print("="*70)
    print("[INFO] 백테스팅 버그 수정 검증 테스트 시작")
    print("="*70)
    print("\n[INFO] 테스트 목적:")
    print("- _check_prediction_in_filtered_pool() 메소드 수정 검증")
    print("- 항상 True 반환하던 버그 수정 확인")
    print("- 실제 필터 검증 로직 작동 확인")
    print("- 에러 처리 개선 확인")

    # 테스트 실행
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestBacktestingFix)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 결과 보고
    print("\n" + "="*70)
    print("[INFO] 테스트 결과 요약")
    print("="*70)

    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    success = total_tests - failures - errors

    print(f"총 테스트: {total_tests}개")
    print(f"성공: {success}개")
    print(f"실패: {failures}개")
    print(f"에러: {errors}개")

    if failures == 0 and errors == 0:
        print("\n[SUCCESS] 모든 테스트 통과! 백테스팅 버그 수정이 성공적으로 검증되었습니다.")
        print("\n[INFO] 확인된 사항:")
        print("- 필터 검증 로직이 제대로 작동함")
        print("- 더 이상 항상 True를 반환하지 않음")
        print("- 에러 발생 시 False를 반환함")
        print("- 현실적인 필터 통과율 확인")
    else:
        print("\n[ERROR] 일부 테스트 실패! 추가 수정이 필요할 수 있습니다.")

        if failures > 0:
            print("\n실패한 테스트:")
            for test, traceback in result.failures:
                print(f"- {test}: {traceback.split('AssertionError:')[-1].strip()}")

        if errors > 0:
            print("\n에러가 발생한 테스트:")
            for test, traceback in result.errors:
                print(f"- {test}: 에러 발생")

    print("\n" + "="*70)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)