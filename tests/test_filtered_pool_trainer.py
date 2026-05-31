#!/usr/bin/env python3
"""
필터링된 풀 학습기 단위 테스트
"""
import pytest
import numpy as np
import sys
import os
from unittest.mock import Mock, MagicMock, patch

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ml.filtered_pool_trainer import FilteredPoolTrainer


@pytest.fixture
def sample_combinations():
    """테스트용 샘플 조합"""
    return [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
        [13, 14, 15, 16, 17, 18],
        [19, 20, 21, 22, 23, 24],
        [5, 10, 15, 20, 25, 30],  # 완전 일치 조합 (winning_numbers[4])
        [31, 32, 33, 34, 35, 36],
        [37, 38, 39, 40, 41, 42],
        [1, 5, 10, 15, 20, 25],   # 완전 일치 조합 (winning_numbers[0])
        [2, 7, 12, 17, 22, 27],
        [3, 9, 15, 21, 27, 33]
    ]


@pytest.fixture
def sample_winning_numbers():
    """테스트용 샘플 당첨번호"""
    return [
        "1,5,10,15,20,25",
        "2,7,12,17,22,27",
        "3,8,13,18,23,28",
        "4,9,14,19,24,29",
        "5,10,15,20,25,30",
        "6,11,16,21,26,31",
        "7,12,17,22,27,32",
        "8,13,18,23,28,33",
        "9,14,19,24,29,34",
        "10,15,20,25,30,35"
    ]


@pytest.fixture
def trainer():
    """FilteredPoolTrainer 인스턴스"""
    return FilteredPoolTrainer(pool_sample_size=100)


class TestFilteredPoolTrainer:
    """FilteredPoolTrainer 테스트"""

    def test_initialization(self, trainer):
        """초기화 테스트"""
        assert trainer.pool_sample_size == 100
        assert trainer.feature_config['use_statistics'] is True
        assert trainer.feature_config['use_patterns'] is True
        assert trainer.feature_config['use_distributions'] is True
        assert trainer.hybrid_weights['winning_numbers'] == 0.7
        assert trainer.hybrid_weights['filtered_pool'] == 0.3

    def test_extract_pool_features(self, trainer, sample_combinations):
        """특징 추출 테스트"""
        features = trainer.extract_pool_features(sample_combinations)

        # 결과 검증
        assert not features.empty
        assert len(features) == len(sample_combinations)

        # 필수 특징 컬럼 확인
        expected_columns = ['mean', 'std', 'min', 'max', 'range', 'sum',
                          'odd_ratio', 'consecutive_ratio', 'avg_gap']
        for col in expected_columns:
            assert col in features.columns

        # 값 범위 검증
        assert (features['mean'] >= 1).all() and (features['mean'] <= 45).all()
        assert (features['odd_ratio'] >= 0).all() and (features['odd_ratio'] <= 1).all()

    def test_extract_pool_features_empty(self, trainer):
        """빈 조합 리스트 처리 테스트"""
        features = trainer.extract_pool_features([])
        assert features.empty

    def test_extract_pool_features_with_tuples(self, trainer):
        """튜플 입력 처리 테스트"""
        tuple_combinations = [
            (1, 2, 3, 4, 5, 6),
            (7, 8, 9, 10, 11, 12),
            (13, 14, 15, 16, 17, 18)
        ]
        features = trainer.extract_pool_features(tuple_combinations)

        assert not features.empty
        assert len(features) == len(tuple_combinations)

    def test_generate_labels(self, trainer, sample_combinations, sample_winning_numbers):
        """레이블 생성 테스트"""
        labels = trainer.generate_labels(sample_combinations, sample_winning_numbers)

        # 결과 검증
        assert len(labels) == len(sample_combinations)
        assert (labels >= 0).all() and (labels <= 1).all()

        # 완전 일치 조합의 유사도가 높은지 확인
        # sample_combinations[4] = [5,10,15,20,25,30]
        # sample_winning_numbers[4] = "5,10,15,20,25,30"
        # 동일한 조합이므로 유사도가 다른 조합들보다 높아야 함
        # Jaccard 40% + Match 60% weighted score이므로 실제 값은 ~0.28 정도
        assert labels[4] > labels[0]  # 완전 일치가 다른 조합보다 높음
        assert labels[4] == max(labels)  # 가장 높은 유사도

    def test_generate_labels_empty(self, trainer):
        """빈 입력 처리 테스트"""
        labels = trainer.generate_labels([], [])
        assert len(labels) == 0

    def test_fine_tune_model_mock(self, trainer):
        """모델 미세조정 테스트 (모의 객체)"""
        # Mock 객체 생성
        mock_model = Mock()
        mock_model.__class__.__name__ = 'EnsemblePredictor'
        mock_model.is_trained = True
        mock_model.models = {'rf': Mock(), 'xgb': Mock(), 'nn': Mock()}

        mock_db_manager = Mock()
        mock_db_manager.get_all_winning_numbers.return_value = [
            "1,2,3,4,5,6",
            "7,8,9,10,11,12"
        ] * 10  # 20개 당첨번호

        mock_filter_manager = Mock()

        # _sample_filtered_pool을 모의로 대체
        with patch.object(trainer, '_sample_filtered_pool') as mock_sample:
            mock_sample.return_value = [
                (1, 2, 3, 4, 5, 6),
                (7, 8, 9, 10, 11, 12),
                (13, 14, 15, 16, 17, 18)
            ]

            # 미세조정 수행
            result = trainer.fine_tune_model(
                mock_model, mock_db_manager, mock_filter_manager
            )

            # 결과 검증
            assert result is not None
            assert result == mock_model

    def test_train_hybrid_model_mock(self, trainer):
        """하이브리드 학습 테스트 (모의 객체)"""
        # Mock 객체 생성
        mock_model = Mock()
        mock_model.__class__.__name__ = 'EnsemblePredictor'
        mock_model.is_trained = False
        mock_model.train = Mock()

        mock_db_manager = Mock()
        mock_db_manager.get_all_winning_numbers.return_value = [
            f"{i},{i+1},{i+2},{i+3},{i+4},{i+5}"
            for i in range(1, 51)  # 50개 당첨번호
        ]

        mock_filter_manager = Mock()

        # fine_tune_model을 모의로 대체
        with patch.object(trainer, 'fine_tune_model') as mock_fine_tune:
            mock_fine_tune.return_value = mock_model

            # 하이브리드 학습 수행
            result = trainer.train_hybrid_model(
                mock_model, mock_db_manager, mock_filter_manager
            )

            # 결과 검증
            assert result is not None
            mock_model.train.assert_called_once()
            mock_fine_tune.assert_called_once()

    def test_evaluate_pool_coverage(self, trainer, sample_combinations, sample_winning_numbers):
        """풀 커버리지 평가 테스트"""
        # Mock 모델 생성
        mock_model = Mock()
        mock_model.__class__.__name__ = 'EnsemblePredictor'

        # 모의 예측 생성
        mock_predictions = np.random.rand(len(sample_combinations), 45)
        mock_model.predict_probability.return_value = mock_predictions

        # 특징 추출 및 스케일러 학습
        features = trainer.extract_pool_features(sample_combinations)
        trainer.scaler.fit(features)

        # 평가 수행
        metrics = trainer.evaluate_pool_coverage(
            mock_model, sample_combinations, sample_winning_numbers
        )

        # 결과 검증
        assert 'pool_size' in metrics
        assert 'mse' in metrics or 'error' in metrics
        if 'pool_size' in metrics:
            assert metrics['pool_size'] == len(sample_combinations)

    def test_sample_filtered_pool_mock(self, trainer):
        """필터링된 풀 샘플링 테스트"""
        # Mock FilterManager 생성
        mock_filter_manager = Mock()
        mock_combinations = [
            (1, 2, 3, 4, 5, 6),
            (7, 8, 9, 10, 11, 12),
            (13, 14, 15, 16, 17, 18)
        ] * 100  # 300개 조합

        mock_filter_manager.get_filtered_combinations.return_value = mock_combinations

        # 샘플링 수행
        sampled = trainer._sample_filtered_pool(mock_filter_manager, 1000, 50)

        # 결과 검증
        assert len(sampled) == 50
        assert all(isinstance(combo, tuple) for combo in sampled)
        assert all(len(combo) == 6 for combo in sampled)

    def test_sample_filtered_pool_small_pool(self, trainer):
        """작은 풀 샘플링 테스트 (샘플 크기 > 풀 크기)"""
        mock_filter_manager = Mock()
        mock_combinations = [
            (1, 2, 3, 4, 5, 6),
            (7, 8, 9, 10, 11, 12)
        ]

        mock_filter_manager.get_filtered_combinations.return_value = mock_combinations

        # 샘플링 수행 (샘플 크기 > 풀 크기)
        sampled = trainer._sample_filtered_pool(mock_filter_manager, 1000, 50)

        # 전체 풀이 반환되어야 함
        assert len(sampled) == len(mock_combinations)

    def test_save_and_load_trainer_state(self, trainer, tmp_path):
        """학습기 상태 저장/로드 테스트"""
        # 상태 수정
        trainer.pool_sample_size = 5000
        trainer.training_history.append({'test': 'data'})

        # 저장
        filepath = tmp_path / "trainer_state.pkl"
        trainer.save_trainer_state(str(filepath))

        # 새 인스턴스 생성 및 로드
        new_trainer = FilteredPoolTrainer(pool_sample_size=100)
        new_trainer.load_trainer_state(str(filepath))

        # 검증
        assert new_trainer.pool_sample_size == 5000
        assert len(new_trainer.training_history) == 1
        assert new_trainer.training_history[0]['test'] == 'data'

    def test_feature_extraction_statistics(self, trainer):
        """통계적 특징 추출 테스트"""
        combinations = [
            [1, 2, 3, 4, 5, 6],      # 연속 번호
            [1, 10, 20, 30, 40, 45], # 분산된 번호
            [5, 10, 15, 20, 25, 30]  # 등차수열
        ]

        features = trainer.extract_pool_features(combinations)

        # 연속 번호의 경우 consecutive_ratio가 높아야 함
        assert features.loc[0, 'consecutive_ratio'] > 0.8

        # 분산된 번호의 경우 gap이 커야 함
        assert features.loc[1, 'max_gap'] > features.loc[0, 'max_gap']

        # 등차수열의 경우 gap_std가 작아야 함
        assert features.loc[2, 'gap_std'] < 1.0

    def test_label_generation_similarity(self, trainer):
        """유사도 레이블 생성 정확도 테스트"""
        # 완전 일치 조합
        combinations = [
            [1, 2, 3, 4, 5, 6],
            [1, 2, 3, 4, 5, 7],  # 5개 일치
            [1, 2, 3, 4, 8, 9],  # 4개 일치
            [10, 11, 12, 13, 14, 15]  # 0개 일치
        ]

        winning_numbers = ["1,2,3,4,5,6"]

        labels = trainer.generate_labels(combinations, winning_numbers)

        # 유사도 순서 확인
        assert labels[0] > labels[1]  # 6개 일치 > 5개 일치
        assert labels[1] > labels[2]  # 5개 일치 > 4개 일치
        assert labels[2] > labels[3]  # 4개 일치 > 0개 일치

    def test_hybrid_weights_validation(self, trainer):
        """하이브리드 가중치 검증"""
        # 가중치 합이 1.0이어야 함
        total_weight = (trainer.hybrid_weights['winning_numbers'] +
                       trainer.hybrid_weights['filtered_pool'])
        assert abs(total_weight - 1.0) < 1e-6


@pytest.mark.integration
class TestFilteredPoolTrainerIntegration:
    """통합 테스트 (실제 DB 필요)"""

    @pytest.fixture
    def real_db_manager(self):
        """실제 DB 관리자 (통합 테스트용)"""
        try:
            from src.core.db_manager import DatabaseManager
            return DatabaseManager()
        except Exception:
            pytest.skip("DatabaseManager를 초기화할 수 없습니다")

    @pytest.fixture
    def real_filter_manager(self, real_db_manager):
        """실제 필터 관리자 (통합 테스트용)"""
        try:
            from src.core.filter_manager import FilterManager
            return FilterManager(real_db_manager)
        except Exception:
            pytest.skip("FilterManager를 초기화할 수 없습니다")

    def test_full_training_pipeline(self, real_db_manager, real_filter_manager):
        """전체 학습 파이프라인 테스트"""
        # 당첨번호 가져오기
        winning_numbers = real_db_manager.get_all_winning_numbers()

        if len(winning_numbers) < 50:
            pytest.skip("당첨번호 데이터 부족")

        # 앙상블 모델 생성
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor
            ensemble = EnsemblePredictor()
        except Exception:
            pytest.skip("EnsemblePredictor를 초기화할 수 없습니다")

        # 학습기 생성
        trainer = FilteredPoolTrainer(pool_sample_size=100)

        # 하이브리드 학습 수행
        result = trainer.train_hybrid_model(
            ensemble, real_db_manager, real_filter_manager
        )

        # 결과 검증
        assert result is not None
        assert len(trainer.training_history) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
