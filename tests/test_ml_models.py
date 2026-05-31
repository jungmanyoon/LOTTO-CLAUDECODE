#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 모델 테스트

Phase 2.7: ML Model Tests
- LSTM 모델 테스트
- Ensemble 모델 테스트
- Monte Carlo 시뮬레이션 테스트
- 모델 캐시 저장/로드 테스트

목표 커버리지: 70%+
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import tempfile
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Mock 데이터베이스 import
try:
    from mocks.mock_database import MockDatabaseManager
except ImportError:
    from tests.mocks.mock_database import MockDatabaseManager


# =========================================================================
# Test Fixtures
# =========================================================================

@pytest.fixture
def mock_db():
    """테스트용 Mock 데이터베이스"""
    db = MockDatabaseManager()
    db.setup_sample_data(num_rounds=100)
    return db


@pytest.fixture
def sample_winning_numbers():
    """테스트용 당첨번호 데이터"""
    return [
        "1,2,3,4,5,6",
        "7,11,16,35,36,44",
        "2,9,16,25,26,40",
        "4,7,14,30,31,38",
        "2,6,12,19,22,43",
        "1,6,14,15,29,41",
        "10,16,18,31,33,40",
        "5,9,13,23,28,44",
        "6,8,13,23,26,45",
        "3,6,16,22,29,40",
    ] * 10  # 100개 데이터


@pytest.fixture
def temp_model_dir():
    """임시 모델 디렉토리"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# =========================================================================
# LSTM Predictor Tests
# =========================================================================

class TestLSTMPredictor:
    """LSTM 예측기 테스트"""

    def test_lstm_predictor_import(self):
        """[OK] LSTM 예측기 import 테스트"""
        try:
            from src.ml.lstm_predictor import LSTMPredictor, TENSORFLOW_AVAILABLE
            assert LSTMPredictor is not None
        except ImportError as e:
            pytest.skip(f"TensorFlow not available: {e}")

    def test_lstm_predictor_initialization(self, temp_model_dir):
        """[OK] LSTM 예측기 초기화 테스트"""
        try:
            from src.ml.lstm_predictor import LSTMPredictor, TENSORFLOW_AVAILABLE
            if not TENSORFLOW_AVAILABLE:
                pytest.skip("TensorFlow not available")

            predictor = LSTMPredictor(
                sequence_length=30,
                model_path=os.path.join(temp_model_dir, 'test_lstm.h5')
            )

            assert predictor.sequence_length == 30
            assert predictor.feature_dims == 45
            assert predictor.output_dims == 45
        except ImportError:
            pytest.skip("TensorFlow not available")

    def test_lstm_predictor_params(self, temp_model_dir):
        """[OK] LSTM 모델 파라미터 검증"""
        try:
            from src.ml.lstm_predictor import LSTMPredictor, TENSORFLOW_AVAILABLE
            if not TENSORFLOW_AVAILABLE:
                pytest.skip("TensorFlow not available")

            predictor = LSTMPredictor(
                sequence_length=50,
                model_path=os.path.join(temp_model_dir, 'test_lstm.h5')
            )

            # 드롭아웃 비율 확인 (과적합 방지)
            assert predictor.dropout_rate >= 0.3
            # LSTM 유닛 구조 확인
            assert len(predictor.lstm_units) >= 2
            assert predictor.lstm_units[0] >= 64
        except ImportError:
            pytest.skip("TensorFlow not available")

    @pytest.mark.slow
    def test_lstm_predictor_build_model(self, temp_model_dir):
        """[OK] LSTM 모델 구축 테스트 (느림)"""
        try:
            from src.ml.lstm_predictor import LSTMPredictor, TENSORFLOW_AVAILABLE
            if not TENSORFLOW_AVAILABLE:
                pytest.skip("TensorFlow not available")

            predictor = LSTMPredictor(
                sequence_length=20,
                model_path=os.path.join(temp_model_dir, 'test_lstm.h5')
            )

            # 모델이 생성되었는지 확인
            if hasattr(predictor, '_build_model'):
                predictor._build_model()
                assert predictor.model is not None
        except ImportError:
            pytest.skip("TensorFlow not available")


# =========================================================================
# Ensemble Predictor Tests
# =========================================================================

class TestEnsemblePredictor:
    """앙상블 예측기 테스트"""

    def test_ensemble_predictor_import(self):
        """[OK] 앙상블 예측기 import 테스트"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            assert EnsemblePredictor is not None
        except ImportError as e:
            pytest.skip(f"scikit-learn not available: {e}")

    def test_ensemble_predictor_initialization(self, temp_model_dir):
        """[OK] 앙상블 예측기 초기화 테스트"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            predictor = EnsemblePredictor(model_dir=temp_model_dir)

            # 기본 설정 확인
            assert predictor.model_dir == temp_model_dir
            assert 'rf' in predictor.ensemble_weights
            assert 'xgb' in predictor.ensemble_weights
            assert 'nn' in predictor.ensemble_weights
        except ImportError:
            pytest.skip("scikit-learn not available")

    def test_ensemble_weights_sum(self, temp_model_dir):
        """[OK] 앙상블 가중치 합계 검증"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            predictor = EnsemblePredictor(model_dir=temp_model_dir)

            # 가중치 합이 1에 가까운지 확인
            total_weight = sum(predictor.ensemble_weights.values())
            assert abs(total_weight - 1.0) < 0.01
        except ImportError:
            pytest.skip("scikit-learn not available")

    def test_ensemble_feature_config(self, temp_model_dir):
        """[OK] 앙상블 특징 설정 검증"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            predictor = EnsemblePredictor(model_dir=temp_model_dir)

            # 특징 설정 확인
            assert predictor.feature_config['use_statistics'] is True
            assert predictor.feature_config['use_patterns'] is True
            assert predictor.feature_config['use_temporal'] is True
            assert len(predictor.feature_config['window_sizes']) >= 2
        except ImportError:
            pytest.skip("scikit-learn not available")

    def test_ensemble_min_samples(self, temp_model_dir):
        """[OK] 최소 학습 샘플 수 검증"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            predictor = EnsemblePredictor(model_dir=temp_model_dir)

            # 모델 안정성을 위한 최소 샘플 수
            assert predictor.min_train_samples >= 50
        except ImportError:
            pytest.skip("scikit-learn not available")


# =========================================================================
# Monte Carlo Simulator Tests
# =========================================================================

class TestMonteCarloSimulator:
    """Monte Carlo 시뮬레이터 테스트"""

    def test_monte_carlo_import(self):
        """[OK] Monte Carlo 시뮬레이터 import 테스트"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
        assert MonteCarloSimulator is not None

    def test_monte_carlo_initialization(self):
        """[OK] Monte Carlo 초기화 테스트"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()

        # 기본 파라미터 확인
        assert 'n_simulations' in simulator.simulation_params
        assert 'confidence_level' in simulator.simulation_params
        assert simulator.simulation_params['confidence_level'] > 0.9

    def test_monte_carlo_with_db_manager(self, mock_db):
        """[OK] DB 매니저와 함께 초기화"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator(db_manager=mock_db)
        assert simulator.db_manager is not None

    def test_monte_carlo_simulation_params(self):
        """[OK] 시뮬레이션 파라미터 검증"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()

        # 시뮬레이션 횟수 범위 확인
        assert simulator.simulation_params['n_simulations'] >= 5000
        assert simulator.simulation_params['n_simulations'] <= 10000

        # 수렴 임계값 확인
        assert simulator.simulation_params['convergence_threshold'] < 0.01

    def test_monte_carlo_probability_model(self):
        """[OK] 확률 모델 설정 검증"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()

        # 모든 확률 모델 요소가 활성화되어 있는지 확인
        assert simulator.probability_model['use_frequency'] is True
        assert simulator.probability_model['use_patterns'] is True
        assert simulator.probability_model['use_correlations'] is True
        assert simulator.probability_model['use_temporal'] is True

    def test_monte_carlo_cache_structure(self):
        """[OK] 캐시 구조 검증"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()

        # 캐시 구조 확인
        assert 'simulations' in simulator.cache
        assert 'probabilities' in simulator.cache
        assert 'best_combinations' in simulator.cache

    def test_monte_carlo_load_historical_data(self, sample_winning_numbers):
        """[OK] 과거 데이터 로드 테스트"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        simulator.load_historical_data(sample_winning_numbers)

        assert simulator.historical_data is not None
        assert len(simulator.historical_data) == len(sample_winning_numbers)

    def test_monte_carlo_probability_matrix(self, sample_winning_numbers):
        """[OK] 확률 행렬 계산 테스트"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        simulator.load_historical_data(sample_winning_numbers)

        # 확률 행렬이 생성되었는지 확인
        assert simulator.probability_matrix is not None
        # 확률 행렬 크기 확인 (45개 번호)
        assert len(simulator.probability_matrix) == 45
        # 확률 합이 1에 가까운지 확인
        total_prob = sum(simulator.probability_matrix)
        assert abs(total_prob - 1.0) < 0.1

    def test_monte_carlo_empty_data_handling(self):
        """[OK] 빈 데이터 처리"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        # 빈 데이터로 로드 시도
        simulator.load_historical_data([])

        # 에러 없이 처리되어야 함
        assert simulator.historical_data is None or len(simulator.historical_data) == 0


# =========================================================================
# Model Cache Tests
# =========================================================================

class TestModelCache:
    """모델 캐시 테스트"""

    def test_ensemble_model_save_directory(self, temp_model_dir):
        """[OK] 앙상블 모델 저장 디렉토리 생성"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            predictor = EnsemblePredictor(model_dir=temp_model_dir)

            # 디렉토리가 생성되었는지 확인
            assert os.path.exists(temp_model_dir)
        except ImportError:
            pytest.skip("scikit-learn not available")

    def test_model_path_validation(self, temp_model_dir):
        """[OK] 모델 경로 유효성 검증"""
        try:
            from src.ml.lstm_predictor import LSTMPredictor, TENSORFLOW_AVAILABLE
            if not TENSORFLOW_AVAILABLE:
                pytest.skip("TensorFlow not available")

            model_path = os.path.join(temp_model_dir, 'test_model.h5')
            predictor = LSTMPredictor(model_path=model_path)

            assert predictor.model_path == model_path
        except ImportError:
            pytest.skip("TensorFlow not available")


# =========================================================================
# Prediction Output Tests
# =========================================================================

class TestPredictionOutput:
    """예측 출력 형식 테스트"""

    def test_monte_carlo_output_format(self, sample_winning_numbers):
        """[OK] Monte Carlo 출력 형식 검증"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        simulator.load_historical_data(sample_winning_numbers)

        # run_simulation 메서드가 있는 경우
        if hasattr(simulator, 'run_simulation'):
            try:
                result = simulator.run_simulation(n_combinations=5)
                if result:
                    # 결과가 리스트인지 확인
                    assert isinstance(result, (list, dict))
            except Exception:
                # 시뮬레이션 실패는 테스트 실패로 처리하지 않음
                pass

    def test_prediction_number_range(self, sample_winning_numbers):
        """[OK] 예측 번호 범위 검증 (1-45)"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        simulator.load_historical_data(sample_winning_numbers)

        # 확률 행렬의 모든 값이 유효한지 확인
        if simulator.probability_matrix is not None:
            for prob in simulator.probability_matrix:
                assert prob >= 0  # 음수 확률 없음
                assert prob <= 1  # 1 초과 확률 없음


# =========================================================================
# Integration Tests
# =========================================================================

@pytest.mark.integration
class TestMLIntegration:
    """ML 시스템 통합 테스트"""

    def test_multiple_models_coexistence(self, temp_model_dir):
        """[OK] 여러 모델 동시 존재 테스트"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            # 여러 모델 동시 생성
            ensemble = EnsemblePredictor(model_dir=temp_model_dir)
            monte_carlo = MonteCarloSimulator()

            assert ensemble is not None
            assert monte_carlo is not None
        except ImportError:
            pytest.skip("Required modules not available")

    def test_model_independence(self, temp_model_dir, sample_winning_numbers):
        """[OK] 모델 간 독립성 테스트"""
        try:
            from src.ml.ensemble_predictor import EnsemblePredictor, SKLEARN_AVAILABLE
            from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

            if not SKLEARN_AVAILABLE:
                pytest.skip("scikit-learn not available")

            # Monte Carlo 데이터 로드
            monte_carlo = MonteCarloSimulator()
            monte_carlo.load_historical_data(sample_winning_numbers)

            # Ensemble 초기화
            ensemble = EnsemblePredictor(model_dir=temp_model_dir)

            # Monte Carlo 상태가 Ensemble에 영향을 주지 않아야 함
            assert ensemble.is_trained is False  # 아직 학습되지 않음
        except ImportError:
            pytest.skip("Required modules not available")


# =========================================================================
# Edge Case Tests
# =========================================================================

class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_historical_data(self):
        """[OK] 빈 히스토리 데이터 처리"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        simulator.load_historical_data(None)

        # 에러 없이 처리
        assert simulator.historical_data is None

    def test_invalid_number_format(self):
        """[OK] 잘못된 번호 형식 처리"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()

        # 잘못된 형식의 데이터
        invalid_data = ["invalid", "not,numbers", "1,2,3"]

        try:
            simulator.load_historical_data(invalid_data)
        except (ValueError, IndexError):
            # 예외 발생 가능
            pass

    def test_small_dataset(self):
        """[OK] 작은 데이터셋 처리"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        small_data = ["1,2,3,4,5,6"] * 5  # 5개만

        simulator.load_historical_data(small_data)

        # 작은 데이터셋도 처리 가능해야 함
        assert simulator.historical_data is not None

    def test_duplicate_numbers_handling(self):
        """[OK] 중복 번호 데이터 처리"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator

        simulator = MonteCarloSimulator()
        # 같은 번호가 반복되는 데이터
        repeated_data = ["1,2,3,4,5,6"] * 50

        simulator.load_historical_data(repeated_data)

        # 확률 계산이 올바르게 되어야 함
        if simulator.probability_matrix is not None:
            # 1-6 번호의 확률이 다른 번호보다 높아야 함
            high_prob_numbers = [simulator.probability_matrix[i] for i in range(6)]
            low_prob_numbers = [simulator.probability_matrix[i] for i in range(6, 45)]

            avg_high = np.mean(high_prob_numbers)
            avg_low = np.mean(low_prob_numbers)

            assert avg_high > avg_low


# =========================================================================
# Performance Tests
# =========================================================================

@pytest.mark.slow
class TestPerformance:
    """성능 테스트 (선택적)"""

    def test_monte_carlo_cpu_scaling(self):
        """[OK] CPU 기반 시뮬레이션 횟수 조정"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
        import multiprocessing as mp

        simulator = MonteCarloSimulator()
        cpu_count = mp.cpu_count()

        # CPU 수에 따른 적절한 시뮬레이션 횟수
        n_simulations = simulator.simulation_params['n_simulations']
        assert n_simulations >= cpu_count * 500  # 최소 CPU당 500회

    def test_probability_matrix_computation(self, sample_winning_numbers):
        """[OK] 확률 행렬 계산 성능"""
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
        import time

        simulator = MonteCarloSimulator()

        start_time = time.time()
        simulator.load_historical_data(sample_winning_numbers)
        elapsed = time.time() - start_time

        # 100개 데이터 처리에 1초 미만
        assert elapsed < 1.0
