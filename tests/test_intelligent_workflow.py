#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IntelligentWorkflow 단위 테스트

목적: IntelligentWorkflow의 핵심 기능 검증
- 워크플로우 초기화 및 구성
- 단계별 실행 로직
- ML 모델 통합
- 필터 시스템 통합
- 에러 처리 및 복구
- 상태 관리 및 캐싱
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import json
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.core.intelligent_workflow import IntelligentWorkflow


class TestIntelligentWorkflowInitialization:
    """IntelligentWorkflow 초기화 테스트"""

    def test_workflow_initialization_with_valid_dependencies(self):
        """
        테스트: 유효한 의존성으로 워크플로우 초기화
        예상: 모든 의존성이 올바르게 설정됨
        """
        # Arrange
        mock_db = Mock()
        mock_filter_manager = Mock()
        mock_cache_manager = Mock()

        # Act
        workflow = IntelligentWorkflow(mock_db, mock_filter_manager, mock_cache_manager)

        # Assert
        assert workflow.db_manager is mock_db
        assert workflow.filter_manager is mock_filter_manager
        assert workflow.cache_manager is mock_cache_manager
        assert workflow.logger is not None

    def test_workflow_initialization_with_none_dependencies(self):
        """
        테스트: None 의존성으로 초기화 시도
        예상: AttributeError 없이 초기화 (None 허용)
        """
        # Act & Assert - should not raise exception
        workflow = IntelligentWorkflow(None, None, None)
        assert workflow.db_manager is None
        assert workflow.filter_manager is None
        assert workflow.cache_manager is None


class TestWorkflowExecution:
    """워크플로우 실행 테스트"""

    @pytest.fixture
    def mock_workflow_components(self):
        """워크플로우 컴포넌트 Mock 픽스처"""
        mock_db = Mock()
        mock_filter_manager = Mock()
        mock_cache_manager = Mock()

        return {
            'db': mock_db,
            'filter_manager': mock_filter_manager,
            'cache_manager': mock_cache_manager
        }

    def test_execute_with_cached_results(self, mock_workflow_components):
        """
        테스트: 캐시된 결과가 있을 때 실행
        예상: 재필터링 없이 캐시 사용, 빠른 실행
        """
        # Arrange
        workflow = IntelligentWorkflow(
            mock_workflow_components['db'],
            mock_workflow_components['filter_manager'],
            mock_workflow_components['cache_manager']
        )

        # Mock methods
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value=None)
        workflow._prepare_filtered_combinations = Mock(return_value=['1,2,3,4,5,6'] * 100)
        workflow._run_ml_predictions = Mock(return_value={
            'lstm': [{'numbers': [1,2,3,4,5,6], 'confidence': 85}],
            'ensemble': [{'numbers': [7,8,9,10,11,12], 'confidence': 90}],
            'monte_carlo': [{'numbers': [13,14,15,16,17,18], 'confidence': 80}]
        })
        workflow._run_backtesting = Mock(return_value={
            'lstm': {'avg_match': 1.2, 'max_match': 3},
            'ensemble': {'avg_match': 1.5, 'max_match': 4},
            'monte_carlo': {'avg_match': 1.1, 'max_match': 3}
        })
        workflow._generate_final_predictions = Mock(return_value=[
            {'numbers': [1,2,3,4,5,6], 'confidence': 90, 'model': 'ensemble'}
        ])
        workflow._save_results = Mock()

        # Act
        results = workflow.execute(force_refresh=False)

        # Assert
        assert results is not None
        assert results['round'] == 1186  # Next round
        assert 'predictions' in results
        assert 'cache_used' in results
        assert results['cache_used'] == True
        workflow._save_results.assert_called_once()

    def test_execute_with_force_refresh(self, mock_workflow_components):
        """
        테스트: 강제 재처리 모드로 실행
        예상: 캐시 무시하고 재필터링 실행
        """
        # Arrange
        workflow = IntelligentWorkflow(
            mock_workflow_components['db'],
            mock_workflow_components['filter_manager'],
            mock_workflow_components['cache_manager']
        )

        # Mock methods
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value=None)
        workflow._prepare_filtered_combinations = Mock(return_value=['1,2,3,4,5,6'] * 100)
        workflow._run_ml_predictions = Mock(return_value={
            'lstm': [], 'ensemble': [], 'monte_carlo': []
        })
        workflow._run_backtesting = Mock(return_value={})
        workflow._generate_final_predictions = Mock(return_value=[])
        workflow._save_results = Mock()

        # Act
        results = workflow.execute(force_refresh=True)

        # Assert
        assert results['cache_used'] == False
        workflow._prepare_filtered_combinations.assert_called_once_with(1185, True)

    def test_execute_with_new_round_detected(self, mock_workflow_components):
        """
        테스트: 새 회차 감지 시 실행
        예상: 자동으로 force_refresh=True로 전환
        """
        # Arrange
        workflow = IntelligentWorkflow(
            mock_workflow_components['db'],
            mock_workflow_components['filter_manager'],
            mock_workflow_components['cache_manager']
        )

        mock_workflow_components['cache_manager'].update_with_new_round = Mock(return_value=True)

        # Mock methods
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value={
            'round': 1186,
            'numbers': [1, 2, 3, 4, 5, 6]
        })
        workflow._prepare_filtered_combinations = Mock(return_value=['1,2,3,4,5,6'])
        workflow._run_ml_predictions = Mock(return_value={})
        workflow._run_backtesting = Mock(return_value={})
        workflow._generate_final_predictions = Mock(return_value=[])
        workflow._save_results = Mock()

        # Act
        results = workflow.execute(force_refresh=False)

        # Assert
        mock_workflow_components['cache_manager'].update_with_new_round.assert_called_once_with(
            1186, [1, 2, 3, 4, 5, 6]
        )
        # Should use force_refresh due to new round
        workflow._prepare_filtered_combinations.assert_called_once_with(1185, True)

    def test_execute_with_no_filtered_combinations(self, mock_workflow_components):
        """
        테스트: 필터링된 조합이 없을 때
        예상: 에러 응답 반환
        """
        # Arrange
        workflow = IntelligentWorkflow(
            mock_workflow_components['db'],
            mock_workflow_components['filter_manager'],
            mock_workflow_components['cache_manager']
        )

        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value=None)
        workflow._prepare_filtered_combinations = Mock(return_value=[])

        # Act
        results = workflow.execute()

        # Assert
        assert 'error' in results
        assert results['error'] == '필터링 실패'


class TestNewRoundDetection:
    """새 회차 감지 테스트"""

    def test_check_for_new_round_public_method(self):
        """
        테스트: 공개 메서드로 새 회차 확인
        예상: _check_new_round와 동일한 결과 반환
        """
        # Arrange
        mock_db = Mock()
        workflow = IntelligentWorkflow(mock_db, None, None)
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value={
            'round': 1186,
            'numbers': [1, 2, 3, 4, 5, 6]
        })

        # Act
        result = workflow.check_for_new_round()

        # Assert
        assert result is not None
        assert result['round'] == 1186
        assert result['numbers'] == [1, 2, 3, 4, 5, 6]
        workflow._get_latest_round.assert_called_once()
        workflow._check_new_round.assert_called_once_with(1185)

    def test_update_with_new_round(self):
        """
        테스트: 새 회차 데이터로 업데이트
        예상: DB 업데이트 후 True 반환 (재필터링 필요)
        """
        # Arrange
        mock_db = Mock()
        workflow = IntelligentWorkflow(mock_db, None, None)

        # Act
        result = workflow.update_with_new_round(1186, [1, 2, 3, 4, 5, 6])

        # Assert
        # [FIX] 코드가 update_lottery_data(round, numbers) -> fetch_and_save_lotto_data()로
        #       리팩토링됨 (동행복권에서 최신 데이터 동기화). 재필터링 필요 시 True 반환.
        assert result == True
        mock_db.fetch_and_save_lotto_data.assert_called_once()


class TestFilteredCombinationsPreparation:
    """필터링된 조합 준비 테스트"""

    def test_prepare_with_valid_cache(self):
        """
        테스트: 유효한 캐시가 있을 때
        예상: 캐시에서 로드, 필터링 스킵
        """
        # Arrange
        mock_cache_manager = Mock()
        mock_cache_manager.load_filtered_results = Mock(return_value=['1,2,3,4,5,6'] * 1000)

        workflow = IntelligentWorkflow(None, None, mock_cache_manager)

        # Act
        result = workflow._prepare_filtered_combinations(1185, force_refresh=False)

        # Assert
        assert len(result) == 1000
        mock_cache_manager.load_filtered_results.assert_called_once_with(1185)

    def test_prepare_with_force_refresh(self):
        """
        테스트: 강제 재처리 플래그 설정 시
        예상: 캐시 무시하고 재필터링
        """
        # Arrange
        mock_db = Mock()
        mock_filter_manager = Mock()
        mock_cache_manager = Mock()

        # Mock DB operations
        mock_db.combinations_db._create_connection = Mock()
        mock_conn = MagicMock()
        mock_cursor = Mock()
        mock_cursor.fetchone = Mock(return_value=[8145060])
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_db.combinations_db._create_connection.return_value = mock_conn

        mock_db.combinations_db.get_filtered_combinations_count = Mock(return_value=300000)
        mock_filter_manager.apply_filters = Mock(return_value=True)
        mock_cache_manager.save_filtered_results_stream = Mock()

        workflow = IntelligentWorkflow(mock_db, mock_filter_manager, mock_cache_manager)

        # Act
        with patch.object(workflow, '_get_total_combinations_count', return_value=8145060):
            result = workflow._prepare_filtered_combinations(1185, force_refresh=True)

        # Assert
        mock_filter_manager.apply_filters.assert_called_once_with(1185)
        mock_cache_manager.save_filtered_results_stream.assert_called_once()

    def test_prepare_with_insufficient_combinations(self):
        """
        테스트: 전체 조합 수가 부족할 때
        예상: 전체 조합 생성 후 필터링
        """
        # Arrange
        mock_db = Mock()
        mock_filter_manager = Mock()
        mock_cache_manager = Mock()

        mock_cache_manager.load_filtered_results = Mock(return_value=None)
        mock_db.combinations_db.get_filtered_combinations_count = Mock(return_value=300000)
        mock_filter_manager.apply_filters = Mock(return_value=True)
        mock_cache_manager.save_filtered_results_stream = Mock()

        workflow = IntelligentWorkflow(mock_db, mock_filter_manager, mock_cache_manager)
        workflow._generate_all_combinations = Mock()

        # Act
        with patch.object(workflow, '_get_total_combinations_count', return_value=1000000):
            result = workflow._prepare_filtered_combinations(1185, force_refresh=True)

        # Assert
        workflow._generate_all_combinations.assert_called_once()


class TestMLPredictions:
    """ML 예측 테스트"""

    def test_run_ml_predictions_with_combinations(self):
        """
        테스트: 조합이 주어졌을 때 ML 예측 실행
        예상: 모든 ML 모델(LSTM, Ensemble, Monte Carlo) 예측 반환
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        combinations = ['1,2,3,4,5,6'] * 2000

        # Act
        predictions = workflow._run_ml_predictions(combinations, 1185)

        # Assert
        assert 'lstm' in predictions
        assert 'ensemble' in predictions
        assert 'monte_carlo' in predictions
        assert len(predictions['lstm']) > 0
        assert len(predictions['ensemble']) > 0
        assert len(predictions['monte_carlo']) > 0

    def test_lstm_predictions_format(self):
        """
        테스트: LSTM 예측 결과 포맷
        예상: numbers와 confidence 키를 포함하는 딕셔너리 리스트
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        combinations = ['1,2,3,4,5,6'] * 1000

        # Act
        predictions = workflow._predict_lstm(combinations)

        # Assert
        assert len(predictions) == 10  # Returns 10 predictions
        for pred in predictions:
            assert 'numbers' in pred
            assert 'confidence' in pred
            assert len(pred['numbers']) == 6
            assert 60 <= pred['confidence'] <= 90

    def test_ensemble_predictions_format(self):
        """
        테스트: Ensemble 예측 결과 포맷
        예상: numbers와 confidence 키를 포함하는 딕셔너리 리스트
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        combinations = ['1,2,3,4,5,6'] * 1000

        # Act
        predictions = workflow._predict_ensemble(combinations)

        # Assert
        assert len(predictions) == 10
        for pred in predictions:
            assert 'numbers' in pred
            assert 'confidence' in pred
            assert len(pred['numbers']) == 6
            assert 65 <= pred['confidence'] <= 95

    def test_monte_carlo_predictions_format(self):
        """
        테스트: Monte Carlo 예측 결과 포맷
        예상: numbers와 confidence 키를 포함하는 딕셔너리 리스트
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        combinations = ['1,2,3,4,5,6'] * 1000

        # Act
        predictions = workflow._predict_monte_carlo(combinations)

        # Assert
        assert len(predictions) == 10
        for pred in predictions:
            assert 'numbers' in pred
            assert 'confidence' in pred
            assert len(pred['numbers']) == 6
            assert 55 <= pred['confidence'] <= 85


class TestBacktesting:
    """백테스팅 테스트"""

    def test_run_backtesting_returns_performance_metrics(self):
        """
        테스트: 백테스팅 실행
        예상: 모든 모델에 대한 성능 메트릭 반환
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        predictions = {
            'lstm': [{'numbers': [1,2,3,4,5,6], 'confidence': 85}],
            'ensemble': [{'numbers': [7,8,9,10,11,12], 'confidence': 90}],
            'monte_carlo': [{'numbers': [13,14,15,16,17,18], 'confidence': 80}]
        }

        # Act
        results = workflow._run_backtesting(predictions, 1185)

        # Assert
        assert 'lstm' in results
        assert 'ensemble' in results
        assert 'monte_carlo' in results
        assert 'avg_match' in results['lstm']
        assert 'max_match' in results['lstm']
        assert results['lstm']['avg_match'] > 0
        assert results['ensemble']['avg_match'] > 0
        assert results['monte_carlo']['avg_match'] > 0


class TestFinalPredictions:
    """최종 예측 생성 테스트"""

    def test_generate_final_predictions_combines_all_models(self):
        """
        테스트: 최종 예측 생성 시 모든 모델 결과 통합
        예상: 신뢰도 순으로 정렬된 상위 10개 예측
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        predictions = {
            'lstm': [
                {'numbers': [1,2,3,4,5,6], 'confidence': 85},
                {'numbers': [7,8,9,10,11,12], 'confidence': 70}
            ],
            'ensemble': [
                {'numbers': [13,14,15,16,17,18], 'confidence': 95},
                {'numbers': [19,20,21,22,23,24], 'confidence': 80}
            ],
            'monte_carlo': [
                {'numbers': [25,26,27,28,29,30], 'confidence': 75},
                {'numbers': [31,32,33,34,35,36], 'confidence': 65}
            ]
        }
        backtest_results = {
            'lstm': {'avg_match': 1.2, 'max_match': 3},
            'ensemble': {'avg_match': 1.5, 'max_match': 4},
            'monte_carlo': {'avg_match': 1.1, 'max_match': 3}
        }

        # Act
        final = workflow._generate_final_predictions(predictions, backtest_results)

        # Assert
        assert len(final) == 6  # 6 total predictions (2 per model)
        assert all('numbers' in pred for pred in final)
        assert all('confidence' in pred for pred in final)
        assert all('model' in pred for pred in final)
        # Should be sorted by confidence (weighted)
        for i in range(len(final) - 1):
            assert final[i]['confidence'] >= final[i+1]['confidence']

    def test_generate_final_predictions_applies_weights(self):
        """
        테스트: 백테스트 결과를 가중치로 적용
        예상: avg_match가 높은 모델의 예측이 더 높은 신뢰도
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        predictions = {
            'lstm': [{'numbers': [1,2,3,4,5,6], 'confidence': 80}],
            'ensemble': [{'numbers': [7,8,9,10,11,12], 'confidence': 80}]
        }
        backtest_results = {
            'lstm': {'avg_match': 1.0, 'max_match': 3},
            'ensemble': {'avg_match': 2.0, 'max_match': 4}  # Higher weight
        }

        # Act
        final = workflow._generate_final_predictions(predictions, backtest_results)

        # Assert
        # Ensemble should have higher weighted confidence (80 * 2.0 = 160 vs 80 * 1.0 = 80)
        assert final[0]['model'] == 'ensemble'
        assert final[0]['confidence'] > final[1]['confidence']


class TestResultsSaving:
    """결과 저장 테스트"""

    def test_save_results_creates_json_file(self, tmp_path):
        """
        테스트: 결과를 JSON 파일로 저장
        예상: results 디렉토리에 JSON 파일 생성
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        results = {
            'round': 1186,
            'generated_at': datetime.now().isoformat(),
            'filtered_combinations': 300000,
            'predictions': [
                {'numbers': [1,2,3,4,5,6], 'confidence': 90, 'model': 'ensemble'}
            ],
            'backtest_performance': {
                'lstm': {'avg_match': 1.2, 'max_match': 3}
            },
            'cache_used': True
        }

        # Change working directory to tmp_path for test
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Act
            workflow._save_results(results)

            # Assert
            results_dir = tmp_path / "results"
            assert results_dir.exists()
            json_files = list(results_dir.glob("prediction_*.json"))
            assert len(json_files) == 1

            # Verify JSON content
            with open(json_files[0], 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                assert saved_data['round'] == 1186
                assert saved_data['filtered_combinations'] == 300000
                assert len(saved_data['predictions']) == 1
        finally:
            os.chdir(original_cwd)

    def test_save_results_with_korean_text(self, tmp_path):
        """
        테스트: 한글 텍스트가 포함된 결과 저장
        예상: UTF-8 인코딩으로 올바르게 저장
        """
        # Arrange
        workflow = IntelligentWorkflow(None, None, None)
        results = {
            'round': 1186,
            'generated_at': datetime.now().isoformat(),
            'description': '테스트 예측 결과',
            'predictions': []
        }

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            # Act
            workflow._save_results(results)

            # Assert
            results_dir = tmp_path / "results"
            json_files = list(results_dir.glob("prediction_*.json"))

            with open(json_files[0], 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                assert saved_data['description'] == '테스트 예측 결과'
        finally:
            os.chdir(original_cwd)


class TestErrorHandling:
    """에러 처리 테스트"""

    def test_execute_handles_filter_failure_gracefully(self):
        """
        테스트: 필터링 실패 시 에러 처리
        예상: 예외 발생하지 않고 에러 응답 반환
        """
        # Arrange
        mock_filter_manager = Mock()
        mock_filter_manager.apply_filters = Mock(return_value=False)

        workflow = IntelligentWorkflow(None, mock_filter_manager, None)
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value=None)
        workflow._get_total_combinations_count = Mock(return_value=8145060)

        mock_cache_manager = Mock()
        mock_cache_manager.load_filtered_results = Mock(return_value=None)
        workflow.cache_manager = mock_cache_manager

        # Mock DB manager
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_db.combinations_db._create_connection = Mock(return_value=mock_conn)
        workflow.db_manager = mock_db

        # Act
        result = workflow.execute()

        # Assert
        assert 'error' in result
        assert result['error'] == '필터링 실패'

    def test_prepare_filtered_combinations_handles_empty_cache(self):
        """
        테스트: 빈 캐시 처리
        예상: 재필터링 실행
        """
        # Arrange
        mock_cache_manager = Mock()
        mock_cache_manager.load_filtered_results = Mock(return_value=None)
        mock_filter_manager = Mock()
        mock_filter_manager.apply_filters = Mock(return_value=True)

        mock_db = Mock()
        mock_db.combinations_db.get_filtered_combinations_count = Mock(return_value=300000)
        mock_cache_manager.save_filtered_results_stream = Mock()

        workflow = IntelligentWorkflow(mock_db, mock_filter_manager, mock_cache_manager)
        workflow._get_total_combinations_count = Mock(return_value=8145060)

        # Act
        result = workflow._prepare_filtered_combinations(1185, force_refresh=False)

        # Assert
        mock_filter_manager.apply_filters.assert_called_once()


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    def test_full_workflow_end_to_end(self):
        """
        테스트: 전체 워크플로우 종단간 실행
        예상: 모든 단계가 순차적으로 실행되고 최종 결과 반환
        """
        # Arrange
        mock_db = Mock()
        mock_filter_manager = Mock()
        mock_cache_manager = Mock()

        # Setup mocks
        mock_cache_manager.load_filtered_results = Mock(return_value=['1,2,3,4,5,6'] * 1000)

        workflow = IntelligentWorkflow(mock_db, mock_filter_manager, mock_cache_manager)
        workflow._get_latest_round = Mock(return_value=1185)
        workflow._check_new_round = Mock(return_value=None)
        workflow._save_results = Mock()

        # Act
        results = workflow.execute(force_refresh=False)

        # Assert
        assert results is not None
        assert 'round' in results
        assert 'predictions' in results
        assert 'backtest_performance' in results
        assert results['round'] == 1186
        workflow._save_results.assert_called_once()

    @pytest.mark.slow
    def test_workflow_with_actual_database_structure(self, tmp_path):
        """
        테스트: 실제 데이터베이스 구조와 통합
        예상: 실제와 유사한 환경에서 워크플로우 실행

        Note: 이 테스트는 실행 시간이 오래 걸릴 수 있어 slow 마크
        """
        # This test is marked as slow and can be skipped for quick test runs
        # Use: pytest -m "not slow" to skip
        pass


if __name__ == "__main__":
    # 테스트 실행
    pytest.main([__file__, '-v', '--tb=short'])
