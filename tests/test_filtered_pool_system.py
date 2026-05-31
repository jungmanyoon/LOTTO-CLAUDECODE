#!/usr/bin/env python3
"""
필터링된 풀 시스템 테스트
개선된 ML 시스템의 통합 테스트
"""
import unittest
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import numpy as np

# 테스트를 위한 경로 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ml.filtered_pool_lstm_predictor import FilteredPoolLSTMPredictor
from src.ml.filtered_pool_ensemble_predictor import FilteredPoolEnsemblePredictor
# Use OptimizedBacktestingFramework (filtered_pool_backtesting_framework was consolidated)
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework as FilteredPoolBacktestingFramework
from src.core.ml_filter_integration_manager import MLFilterIntegrationManager


class TestFilteredPoolLSTMPredictor(unittest.TestCase):
    """필터링된 풀 LSTM 예측기 테스트"""

    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.predictor = FilteredPoolLSTMPredictor(
            sequence_length=10,
            model_path=os.path.join(self.temp_dir, 'test_lstm.h5')
        )

        # 테스트 데이터
        self.historical_combinations = [
            [1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12],
            [13, 14, 15, 16, 17, 18],
            [19, 20, 21, 22, 23, 24],
            [25, 26, 27, 28, 29, 30],
            [31, 32, 33, 34, 35, 36],
            [1, 7, 13, 19, 25, 31],
            [2, 8, 14, 20, 26, 32],
            [3, 9, 15, 21, 27, 33],
            [4, 10, 16, 22, 28, 34],
            [5, 11, 17, 23, 29, 35],
            [6, 12, 18, 24, 30, 36]
        ]

        self.filtered_combinations = [
            [1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12],
            [13, 14, 15, 16, 17, 18],
            [19, 20, 21, 22, 23, 24],
            [25, 26, 27, 28, 29, 30],
            [1, 7, 13, 19, 25, 31],
            [2, 8, 14, 20, 26, 32],
            [3, 9, 15, 21, 27, 33],
            [4, 10, 16, 22, 28, 34],
            [5, 11, 17, 23, 29, 35]
        ]

    def tearDown(self):
        """테스트 정리"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_filtered_pool(self):
        """필터링된 풀 설정 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        self.assertEqual(self.predictor.pool_size, len(self.filtered_combinations))
        self.assertEqual(len(self.predictor.combination_to_idx), len(self.filtered_combinations))
        self.assertEqual(len(self.predictor.idx_to_combination), len(self.filtered_combinations))

    def test_prepare_training_data(self):
        """학습 데이터 준비 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        X, y = self.predictor.prepare_training_data(self.historical_combinations)

        self.assertIsInstance(X, np.ndarray)
        self.assertIsInstance(y, np.ndarray)
        self.assertEqual(len(X), len(y))
        self.assertTrue(len(X) > 0)

    def test_find_similar_combination(self):
        """유사 조합 찾기 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        test_combo = [1, 2, 3, 4, 5, 7]  # 풀에 없는 조합
        similar_idx = self.predictor._find_similar_combination(test_combo)

        self.assertIsInstance(similar_idx, int)
        self.assertTrue(0 <= similar_idx < len(self.filtered_combinations))

    def test_predict_from_filtered_pool_fallback(self):
        """필터링된 풀에서 예측 (폴백 모드) 테스트"""
        # 모델이 훈련되지 않은 상태에서 테스트
        predictions = self.predictor.predict_from_filtered_pool(
            self.historical_combinations,
            self.filtered_combinations,
            num_predictions=3
        )

        self.assertEqual(len(predictions), 3)
        for pred in predictions:
            self.assertIn('numbers', pred)
            self.assertIn('confidence', pred)
            self.assertEqual(len(pred['numbers']), 6)
            self.assertTrue(all(1 <= n <= 45 for n in pred['numbers']))

    @patch('src.ml.filtered_pool_lstm_predictor.TENSORFLOW_AVAILABLE', False)
    def test_no_tensorflow_fallback(self):
        """TensorFlow 없을 때 폴백 테스트"""
        predictor = FilteredPoolLSTMPredictor()
        predictions = predictor.predict_from_filtered_pool(
            self.historical_combinations,
            self.filtered_combinations,
            num_predictions=2
        )

        self.assertEqual(len(predictions), 2)
        for pred in predictions:
            self.assertIn('source', pred)
            self.assertEqual(pred['source'], 'random_from_pool')


class TestFilteredPoolEnsemblePredictor(unittest.TestCase):
    """필터링된 풀 앙상블 예측기 테스트"""

    def setUp(self):
        """테스트 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.predictor = FilteredPoolEnsemblePredictor(model_dir=self.temp_dir)

        # 테스트 데이터
        self.historical_combinations = [
            [1, 12, 23, 34, 45, 6],
            [7, 18, 29, 40, 11, 22],
            [13, 24, 35, 6, 17, 28],
            [19, 30, 41, 2, 13, 24],
            [25, 36, 7, 18, 29, 40],
            [31, 42, 3, 14, 25, 36],
            [1, 17, 33, 9, 25, 41],
            [2, 18, 34, 10, 26, 42],
            [3, 19, 35, 11, 27, 43],
            [4, 20, 36, 12, 28, 44],
            [5, 21, 37, 13, 29, 45],
            [6, 22, 38, 14, 30, 16]
        ]

        self.filtered_combinations = [
            [1, 12, 23, 34, 45, 6],
            [7, 18, 29, 40, 11, 22],
            [13, 24, 35, 6, 17, 28],
            [19, 30, 41, 2, 13, 24],
            [25, 36, 7, 18, 29, 40],
            [1, 17, 33, 9, 25, 41],
            [2, 18, 34, 10, 26, 42],
            [3, 19, 35, 11, 27, 43],
            [4, 20, 36, 12, 28, 44],
            [5, 21, 37, 13, 29, 45]
        ]

    def tearDown(self):
        """테스트 정리"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_filtered_pool(self):
        """필터링된 풀 설정 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        self.assertEqual(self.predictor.pool_size, len(self.filtered_combinations))
        self.assertTrue(len(self.predictor.combination_to_label) > 0)
        self.assertTrue(len(self.predictor.label_to_combination) > 0)

    def test_extract_combination_features(self):
        """조합 특징 추출 테스트"""
        test_combo = [1, 12, 23, 34, 45, 6]
        features = self.predictor.extract_combination_features(test_combo)

        # 필수 특징들이 있는지 확인
        self.assertIn('sum', features)
        self.assertIn('mean', features)
        self.assertIn('odd_ratio', features)
        self.assertIn('consecutive_ratio', features)
        self.assertIn('prime_ratio', features)

        # 값들이 합리적인 범위인지 확인
        self.assertTrue(0 <= features['odd_ratio'] <= 1)
        self.assertTrue(0 <= features['consecutive_ratio'] <= 1)
        self.assertTrue(0 <= features['prime_ratio'] <= 1)

    def test_extract_sequence_features(self):
        """시퀀스 특징 추출 테스트"""
        features = self.predictor.extract_sequence_features(self.historical_combinations, 8)

        self.assertIsInstance(features, dict)
        self.assertTrue(len(features) > 0)

        # 번호별 빈도 특징이 있는지 확인
        freq_features = [k for k in features.keys() if k.startswith('freq_')]
        self.assertTrue(len(freq_features) > 0)

    def test_prepare_training_data(self):
        """학습 데이터 준비 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        X, y = self.predictor.prepare_training_data(self.historical_combinations)

        self.assertIsInstance(X, np.ndarray)
        self.assertIsInstance(y, np.ndarray)
        self.assertEqual(len(X), len(y))
        self.assertTrue(len(X) > 0)

    def test_find_similar_combination_label(self):
        """유사 조합 레이블 찾기 테스트"""
        self.predictor.set_filtered_pool(self.filtered_combinations)

        test_combo = [1, 12, 23, 34, 45, 7]  # 마지막 번호만 다름
        similar_label = self.predictor._find_similar_combination_label(test_combo)

        self.assertIsInstance(similar_label, int)
        self.assertTrue(similar_label in self.predictor.label_to_combination)

    @patch('src.ml.filtered_pool_ensemble_predictor.SKLEARN_AVAILABLE', False)
    def test_no_sklearn_fallback(self):
        """scikit-learn 없을 때 폴백 테스트"""
        predictor = FilteredPoolEnsemblePredictor()
        predictions = predictor.predict_from_filtered_pool(
            self.historical_combinations,
            self.filtered_combinations,
            num_predictions=2
        )

        self.assertEqual(len(predictions), 2)
        for pred in predictions:
            self.assertIn('source', pred)
            self.assertEqual(pred['source'], 'random_from_pool')


class TestMLFilterIntegrationManager(unittest.TestCase):
    """ML-Filter 통합 관리자 테스트"""

    def setUp(self):
        """테스트 설정"""
        # Mock 데이터베이스 관리자
        self.mock_db_manager = Mock()
        self.mock_db_manager.get_all_winning_numbers.return_value = [
            "1,2,3,4,5,6",
            "7,8,9,10,11,12",
            "13,14,15,16,17,18",
            "19,20,21,22,23,24",
            "25,26,27,28,29,30",
            "31,32,33,34,35,36",
            "1,7,13,19,25,31",
            "2,8,14,20,26,32",
            "3,9,15,21,27,33",
            "4,10,16,22,28,34"
        ]

        # Mock 필터 관리자
        self.mock_filter_manager = Mock()
        self.mock_filter_manager.apply_all_filters.return_value = [
            "1,2,3,4,5,6",
            "7,8,9,10,11,12",
            "13,14,15,16,17,18",
            "19,20,21,22,23,24",
            "25,26,27,28,29,30"
        ]

        with patch('src.core.ml_filter_integration_manager.DatabaseManager') as mock_db_class, \
             patch('src.core.ml_filter_integration_manager.FilterManager') as mock_filter_class:

            mock_db_class.return_value = self.mock_db_manager
            mock_filter_class.return_value = self.mock_filter_manager

            self.integration_manager = MLFilterIntegrationManager()

    def test_prepare_historical_data(self):
        """과거 데이터 준비 테스트"""
        historical_data = self.integration_manager._prepare_historical_data()

        self.assertEqual(len(historical_data), 10)
        self.assertTrue(all(len(combo) == 6 for combo in historical_data))
        self.assertTrue(all(all(1 <= n <= 45 for n in combo) for combo in historical_data))

    def test_calculate_quality_score(self):
        """품질 점수 계산 테스트"""
        test_combinations = [
            [1, 2, 3, 4, 5, 6],      # 연속 번호 (낮은 점수)
            [2, 14, 23, 31, 38, 45], # 균형 잡힌 조합 (높은 점수)
            [1, 1, 1, 1, 1, 1],      # 잘못된 조합 (오류 처리)
        ]

        for combo in test_combinations[:2]:  # 유효한 조합만 테스트
            score = self.integration_manager._calculate_quality_score(combo)
            self.assertTrue(0.0 <= score <= 1.0)

    def test_remove_duplicate_predictions(self):
        """중복 예측 제거 테스트"""
        predictions = [
            {'numbers': [1, 2, 3, 4, 5, 6], 'confidence': 0.8},
            {'numbers': [7, 8, 9, 10, 11, 12], 'confidence': 0.7},
            {'numbers': [1, 2, 3, 4, 5, 6], 'confidence': 0.6},  # 중복
            {'numbers': [13, 14, 15, 16, 17, 18], 'confidence': 0.5}
        ]

        unique_predictions = self.integration_manager._remove_duplicate_predictions(predictions)

        self.assertEqual(len(unique_predictions), 3)
        combo_sets = [set(pred['numbers']) for pred in unique_predictions]
        self.assertEqual(len(combo_sets), len(set(tuple(s) for s in combo_sets)))

    def test_generate_data_hash(self):
        """데이터 해시 생성 테스트"""
        historical_data = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
        pool_size = 1000

        hash1 = self.integration_manager._generate_data_hash(historical_data, pool_size)
        hash2 = self.integration_manager._generate_data_hash(historical_data, pool_size)
        hash3 = self.integration_manager._generate_data_hash(historical_data, 2000)

        # 같은 데이터는 같은 해시
        self.assertEqual(hash1, hash2)
        # 다른 데이터는 다른 해시
        self.assertNotEqual(hash1, hash3)

    def test_update_performance_stats(self):
        """성능 통계 업데이트 테스트"""
        initial_total = self.integration_manager.performance_stats['total_predictions']

        self.integration_manager._update_performance_stats(1000, 1.5)

        # 카운터가 증가했는지 확인
        self.assertEqual(
            self.integration_manager.performance_stats['total_predictions'],
            initial_total + 1
        )

        # 다른 통계들이 업데이트되었는지 확인
        self.assertEqual(self.integration_manager.performance_stats['prediction_time'], 1.5)
        self.assertTrue(self.integration_manager.performance_stats['average_pool_size'] > 0)

    def test_get_performance_summary(self):
        """성능 요약 반환 테스트"""
        summary = self.integration_manager.get_performance_summary()

        self.assertIn('performance_stats', summary)
        self.assertIn('cache_status', summary)
        self.assertIn('configuration', summary)

        # 필수 성능 통계 필드 확인
        stats = summary['performance_stats']
        required_fields = ['total_predictions', 'filter_pass_rate', 'average_pool_size']
        for field in required_fields:
            self.assertIn(field, stats)

    def test_clear_cache(self):
        """캐시 정리 테스트"""
        # 캐시에 데이터 추가
        self.integration_manager.filtered_pool_cache['test'] = {'data': 'test'}
        self.integration_manager.model_cache['test'] = {'model': 'test'}

        # 캐시 정리
        self.integration_manager.clear_cache()

        # 캐시가 비었는지 확인
        self.assertEqual(len(self.integration_manager.filtered_pool_cache), 0)
        self.assertEqual(len(self.integration_manager.model_cache), 0)


class TestFilteredPoolBacktestingFramework(unittest.TestCase):
    """필터링된 풀 백테스팅 프레임워크 테스트"""

    def setUp(self):
        """테스트 설정"""
        # Mock 데이터베이스 관리자
        self.mock_db_manager = Mock()
        self.mock_db_manager.get_numbers_with_bonus.return_value = [
            (1, (1, 2, 3, 4, 5, 6, 7)),
            (2, (8, 9, 10, 11, 12, 13, 14)),
            (3, (15, 16, 17, 18, 19, 20, 21)),
            (4, (22, 23, 24, 25, 26, 27, 28)),
            (5, (29, 30, 31, 32, 33, 34, 35))
        ]

        with patch('src.backtesting.optimized_backtesting_framework.DatabaseManager') as mock_db_class:
            mock_db_class.return_value = self.mock_db_manager
            self.framework = FilteredPoolBacktestingFramework()

    def test_calculate_matches(self):
        """매치 계산 테스트"""
        predictions = {
            'test_model': [
                [1, 2, 3, 4, 5, 6],  # 6개 일치
                [1, 2, 3, 4, 5, 7],  # 5개 일치 + 보너스
                [1, 2, 3, 4, 8, 9],  # 4개 일치
                [10, 11, 12, 13, 14, 15]  # 0개 일치
            ]
        }
        actual = [1, 2, 3, 4, 5, 6]
        bonus = 7

        matches = self.framework._calculate_matches(predictions, actual, bonus)

        self.assertIn('test_model', matches)
        model_matches = matches['test_model']

        self.assertEqual(len(model_matches), 4)

        # 각 예측의 매치 결과 확인
        self.assertEqual(model_matches[0]['match_count'], 6)
        self.assertEqual(model_matches[0]['rank'], 1)

        self.assertEqual(model_matches[1]['match_count'], 5)
        self.assertTrue(model_matches[1]['bonus_match'])
        self.assertEqual(model_matches[1]['rank'], 2)

        self.assertEqual(model_matches[2]['match_count'], 4)
        self.assertEqual(model_matches[2]['rank'], 4)

        self.assertEqual(model_matches[3]['match_count'], 0)
        self.assertIsNone(model_matches[3]['rank'])

    def test_calculate_performance_metrics(self):
        """성능 지표 계산 테스트"""
        test_predictions = [
            {
                'round': 1,
                'predictions': {'model1': [[1, 2, 3, 4, 5, 6]]},
                'matches': {
                    'model1': [{'match_count': 3, 'rank': 5}]
                }
            },
            {
                'round': 2,
                'predictions': {'model1': [[7, 8, 9, 10, 11, 12]]},
                'matches': {
                    'model1': [{'match_count': 1, 'rank': None}]
                }
            }
        ]

        metrics = self.framework._calculate_performance_metrics(test_predictions)

        self.assertIn('total_rounds', metrics)
        self.assertIn('model_performance', metrics)
        self.assertEqual(metrics['total_rounds'], 2)

        # 모델 성능 확인
        self.assertIn('model1', metrics['model_performance'])
        model_perf = metrics['model_performance']['model1']

        self.assertEqual(model_perf['total_predictions'], 2)
        self.assertEqual(model_perf['avg_matches'], 2.0)  # (3+1)/2
        self.assertEqual(model_perf['best_match'], 3)


def run_comprehensive_test():
    """포괄적인 테스트 실행"""
    print("="*60)
    print("필터링된 풀 시스템 포괄적 테스트 시작")
    print("="*60)

    # 테스트 스위트 생성
    test_classes = [
        TestFilteredPoolLSTMPredictor,
        TestFilteredPoolEnsemblePredictor,
        TestMLFilterIntegrationManager,
        TestFilteredPoolBacktestingFramework
    ]

    total_tests = 0
    total_failures = 0
    total_errors = 0

    for test_class in test_classes:
        print(f"\n[{test_class.__name__}] 테스트 실행 중...")

        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=1, stream=open(os.devnull, 'w'))
        result = runner.run(suite)

        tests_run = result.testsRun
        failures = len(result.failures)
        errors = len(result.errors)

        total_tests += tests_run
        total_failures += failures
        total_errors += errors

        status = "PASS" if (failures == 0 and errors == 0) else "FAIL"
        print(f"  - 실행: {tests_run}, 실패: {failures}, 오류: {errors} [{status}]")

        # 실패 및 오류 상세 출력
        if failures > 0:
            print("  실패 상세:")
            for test, traceback in result.failures:
                print(f"    * {test}: {traceback.split('AssertionError:')[-1].strip()}")

        if errors > 0:
            print("  오류 상세:")
            for test, traceback in result.errors:
                print(f"    * {test}: {traceback.split('Error:')[-1].strip()}")

    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)
    print(f"총 테스트: {total_tests}")
    print(f"실패: {total_failures}")
    print(f"오류: {total_errors}")
    success_rate = ((total_tests - total_failures - total_errors) / total_tests * 100) if total_tests > 0 else 0
    print(f"성공률: {success_rate:.1f}%")

    if total_failures == 0 and total_errors == 0:
        print("\n[SUCCESS] 모든 테스트가 통과했습니다!")
        return True
    else:
        print(f"\n[FAILURE] {total_failures + total_errors}개의 테스트가 실패했습니다.")
        return False


if __name__ == '__main__':
    # 개별 테스트 클래스 실행 또는 포괄적 테스트 실행
    if len(sys.argv) > 1 and sys.argv[1] == '--comprehensive':
        success = run_comprehensive_test()
        sys.exit(0 if success else 1)
    else:
        # 표준 unittest 실행
        unittest.main()