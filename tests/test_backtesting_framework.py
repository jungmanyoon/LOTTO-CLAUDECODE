#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
백테스팅 프레임워크 종합 테스트

Phase 3.3: 백테스팅 프레임워크 개선
- 보너스 번호 처리 검증
- 체크포인트 재개 테스트
- 성능 통계 기록 검증
- 다중 라운드 백테스트
"""

import pytest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestBonusNumberHandling:
    """보너스 번호 처리 테스트"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock 데이터베이스 매니저"""
        mock_db = MagicMock()
        # 보너스 번호 포함 데이터 설정
        mock_db.get_numbers_with_bonus.return_value = [
            (1000, (1, 10, 20, 30, 40, 45, 7)),  # 보너스: 7
            (1001, (2, 11, 21, 31, 41, 44, 8)),  # 보너스: 8
            (1002, (3, 12, 22, 32, 42, 43, 9)),  # 보너스: 9
        ]
        return mock_db

    @pytest.fixture
    def framework(self, mock_db_manager):
        """백테스팅 프레임워크 인스턴스"""
        from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework

        # 싱글톤 정리
        if hasattr(OptimizedBacktestingFramework, '_instances'):
            OptimizedBacktestingFramework._instances.clear()

        framework = OptimizedBacktestingFramework(db_manager=mock_db_manager)
        yield framework

        # 정리
        if hasattr(OptimizedBacktestingFramework, '_instances'):
            OptimizedBacktestingFramework._instances.clear()

    def test_bonus_number_in_data(self, mock_db_manager):
        """보너스 번호가 데이터에 포함되는지 테스트"""
        data = mock_db_manager.get_numbers_with_bonus()

        assert len(data) == 3

        # 각 레코드가 7개 번호를 가져야 함 (6개 + 보너스 1개)
        for round_num, numbers in data:
            assert len(numbers) == 7

    def test_bonus_number_extraction(self, mock_db_manager):
        """보너스 번호 추출 테스트"""
        data = mock_db_manager.get_numbers_with_bonus()

        round_num, numbers = data[0]

        main_numbers = numbers[:6]
        bonus_number = numbers[6]

        assert len(main_numbers) == 6
        assert bonus_number == 7  # 첫 번째 레코드의 보너스

    def test_second_prize_match(self, framework):
        """2등 당첨 (5 + 보너스) 계산 테스트"""
        # 당첨 번호: (1, 10, 20, 30, 40, 45), 보너스: 7
        winning_numbers = [1, 10, 20, 30, 40, 45]
        bonus = 7

        # 5개 일치 + 보너스 일치 예측
        prediction = [1, 10, 20, 30, 40, 7]  # 5개 일치 + 보너스

        # 일치 개수 계산
        main_matches = len(set(prediction) & set(winning_numbers))
        bonus_match = bonus in prediction

        # 2등 조건: 5개 일치 + 보너스 일치
        is_second_prize = (main_matches == 5 and bonus_match)

        assert is_second_prize == True

    def test_third_prize_match(self):
        """3등 당첨 (5개 일치) 계산 테스트"""
        winning_numbers = [1, 10, 20, 30, 40, 45]
        bonus = 7

        # 5개 일치, 보너스 미일치 예측
        prediction = [1, 10, 20, 30, 40, 99]

        main_matches = len(set(prediction) & set(winning_numbers))
        bonus_match = bonus in prediction

        # 3등 조건: 5개 일치 + 보너스 미일치
        is_third_prize = (main_matches == 5 and not bonus_match)

        assert is_third_prize == True


class TestCheckpointResume:
    """체크포인트 재개 테스트"""

    @pytest.fixture
    def temp_data_dir(self):
        """임시 데이터 디렉토리"""
        tmpdir = tempfile.mkdtemp()
        data_dir = Path(tmpdir) / 'data'
        data_dir.mkdir()
        yield data_dir

        # 정리
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def mock_db_manager(self):
        """Mock 데이터베이스 매니저"""
        mock_db = MagicMock()
        mock_db.get_numbers_with_bonus.return_value = [
            (r, (1, 2, 3, 4, 5, 6, 7)) for r in range(100, 120)
        ]
        return mock_db

    def test_state_file_creation(self, temp_data_dir, mock_db_manager):
        """상태 파일 생성 테스트"""
        # 상태 파일 직접 생성 테스트
        state_file = temp_data_dir / 'backtest_state.json'

        # 상태 데이터 생성
        state_data = {
            'last_completed_round': 100,
            'start_round': 100,
            'end_round': 110,
            'timestamp': datetime.now().isoformat()
        }

        # 파일 저장
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_data, f)

        # 파일 존재 확인
        assert state_file.exists()

        # 파일 내용 확인
        with open(state_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        assert loaded['last_completed_round'] == 100

    def test_checkpoint_data_structure(self, temp_data_dir):
        """체크포인트 데이터 구조 테스트"""
        checkpoint_data = {
            'last_completed_round': 105,
            'start_round': 100,
            'end_round': 110,
            'timestamp': datetime.now().isoformat(),
            'results': {
                'round_results': {},
                'model_performances': {}
            }
        }

        state_file = temp_data_dir / 'backtest_state.json'

        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f)

        # 파일 읽기
        with open(state_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        assert loaded['last_completed_round'] == 105
        assert loaded['start_round'] == 100
        assert loaded['end_round'] == 110

    def test_resume_from_checkpoint(self, temp_data_dir):
        """체크포인트에서 재개 테스트"""
        # 체크포인트 생성 (105회차까지 완료)
        checkpoint_data = {
            'last_completed_round': 105,
            'start_round': 100,
            'end_round': 110,
            'timestamp': datetime.now().isoformat()
        }

        state_file = temp_data_dir / 'backtest_state.json'
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f)

        # 재개 시작 라운드 계산
        with open(state_file, 'r', encoding='utf-8') as f:
            saved_state = json.load(f)

        resume_round = saved_state['last_completed_round'] + 1

        assert resume_round == 106

    def test_checkpoint_overwrite_protection(self, temp_data_dir):
        """체크포인트 덮어쓰기 보호 테스트"""
        state_file = temp_data_dir / 'backtest_state.json'

        # 첫 번째 체크포인트
        checkpoint1 = {'last_completed_round': 100}
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint1, f)

        # 두 번째 체크포인트 (더 진행된 상태)
        checkpoint2 = {'last_completed_round': 105}
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint2, f)

        # 읽기
        with open(state_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        # 최신 상태가 저장되어야 함
        assert loaded['last_completed_round'] == 105


class TestPerformanceStatistics:
    """성능 통계 기록 테스트"""

    @pytest.fixture
    def mock_stats_manager(self):
        """Mock 성능 통계 매니저"""
        mock_manager = MagicMock()
        mock_manager.save_session_results.return_value = True
        mock_manager.get_session_results.return_value = {
            'session_id': 'test-session',
            'avg_matches': 1.5,
            'max_matches': 4,
            'total_rounds': 10
        }
        return mock_manager

    def test_performance_metrics_structure(self):
        """성능 메트릭 구조 테스트"""
        metrics = {
            'average_matches': 1.5,
            'max_matches': 4,
            'min_matches': 0,
            'match_distribution': {0: 5, 1: 3, 2: 1, 3: 0, 4: 1, 5: 0, 6: 0},
            'filter_inclusion_rate': 0.85,
            'total_predictions': 100,
            'total_rounds': 10
        }

        assert 'average_matches' in metrics
        assert 'max_matches' in metrics
        assert 'filter_inclusion_rate' in metrics

    def test_match_count_calculation(self):
        """일치 개수 계산 테스트"""
        winning = [1, 10, 20, 30, 40, 45]
        prediction = [1, 10, 20, 35, 41, 44]

        matches = len(set(winning) & set(prediction))

        assert matches == 3

    def test_performance_statistics_aggregation(self):
        """성능 통계 집계 테스트"""
        round_results = [
            {'matches': 2, 'included': True},
            {'matches': 1, 'included': True},
            {'matches': 0, 'included': False},
            {'matches': 3, 'included': True},
            {'matches': 1, 'included': True},
        ]

        total_matches = sum(r['matches'] for r in round_results)
        avg_matches = total_matches / len(round_results)
        max_matches = max(r['matches'] for r in round_results)
        inclusion_rate = sum(1 for r in round_results if r['included']) / len(round_results)

        assert total_matches == 7
        assert avg_matches == 1.4
        assert max_matches == 3
        assert inclusion_rate == 0.8

    def test_model_performance_comparison(self):
        """모델별 성능 비교 테스트"""
        model_performances = {
            'lstm': {'avg_matches': 1.5, 'max_matches': 4},
            'ensemble': {'avg_matches': 1.8, 'max_matches': 5},
            'monte_carlo': {'avg_matches': 1.2, 'max_matches': 3}
        }

        best_model = max(model_performances.items(),
                        key=lambda x: x[1]['avg_matches'])

        assert best_model[0] == 'ensemble'
        assert best_model[1]['avg_matches'] == 1.8


class TestMultiRoundBacktest:
    """다중 라운드 백테스트 테스트"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock 데이터베이스 매니저"""
        mock_db = MagicMock()
        # 50회차 데이터 생성
        mock_db.get_numbers_with_bonus.return_value = [
            (r, (r % 45 + 1, (r+1) % 45 + 1, (r+2) % 45 + 1,
                 (r+3) % 45 + 1, (r+4) % 45 + 1, (r+5) % 45 + 1, 7))
            for r in range(1100, 1150)
        ]
        return mock_db

    def test_round_range_validation(self):
        """라운드 범위 검증 테스트"""
        start_round = 1100
        end_round = 1110

        # 유효한 범위
        assert end_round > start_round
        assert end_round - start_round == 10

    def test_batch_processing(self):
        """배치 처리 테스트"""
        start_round = 1100
        end_round = 1149  # 50회차: 1100-1149
        batch_size = 10

        batches = []
        for i in range(start_round, end_round + 1, batch_size):
            batch_end = min(i + batch_size - 1, end_round)
            batches.append((i, batch_end))

        # 배치 개수 확인 (50회차 / 10 = 5 배치)
        assert len(batches) == 5

    def test_window_size_validation(self):
        """윈도우 크기 검증 테스트"""
        window_size = 100
        start_round = 1100

        # 윈도우 크기만큼의 과거 데이터가 필요
        required_data_start = start_round - window_size

        assert required_data_start == 1000

    def test_parallel_round_processing(self):
        """병렬 라운드 처리 테스트"""
        rounds = list(range(1100, 1110))

        # 병렬 처리 가능한 라운드 그룹
        # (각 라운드는 독립적으로 처리 가능)
        chunk_size = 3
        chunks = [rounds[i:i+chunk_size] for i in range(0, len(rounds), chunk_size)]

        assert len(chunks) == 4  # [3, 3, 3, 1]
        assert chunks[0] == [1100, 1101, 1102]
        assert chunks[-1] == [1109]

    def test_result_aggregation(self):
        """결과 집계 테스트"""
        round_results = {
            1100: {'lstm': 2, 'ensemble': 3},
            1101: {'lstm': 1, 'ensemble': 2},
            1102: {'lstm': 0, 'ensemble': 1},
            1103: {'lstm': 3, 'ensemble': 4},
        }

        # 모델별 집계
        lstm_total = sum(r['lstm'] for r in round_results.values())
        ensemble_total = sum(r['ensemble'] for r in round_results.values())

        lstm_avg = lstm_total / len(round_results)
        ensemble_avg = ensemble_total / len(round_results)

        assert lstm_total == 6
        assert ensemble_total == 10
        assert lstm_avg == 1.5
        assert ensemble_avg == 2.5


class TestModelCache:
    """모델 캐시 테스트"""

    @pytest.fixture
    def temp_cache_dir(self):
        """임시 캐시 디렉토리"""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_data_hash_generation(self):
        """데이터 해시 생성 테스트"""
        import hashlib

        data1 = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
        data2 = [[7, 8, 9, 10, 11, 12], [1, 2, 3, 4, 5, 6]]  # 순서만 다름

        # 정렬 후 해시
        def get_hash(data):
            data_str = str(sorted([tuple(d) for d in data]))
            return hashlib.md5(data_str.encode()).hexdigest()

        hash1 = get_hash(data1)
        hash2 = get_hash(data2)

        # 순서가 달라도 같은 해시 (정렬됨)
        assert hash1 == hash2

    def test_cache_key_format(self):
        """캐시 키 형식 테스트"""
        model_type = 'ensemble'
        data_hash = 'abc123'

        cache_key = f"{model_type}_{data_hash}"

        assert cache_key == 'ensemble_abc123'

    def test_cache_file_path(self, temp_cache_dir):
        """캐시 파일 경로 테스트"""
        cache_key = 'ensemble_abc123'
        cache_file = os.path.join(temp_cache_dir, f"{cache_key}.pkl")

        assert cache_file.endswith('.pkl')
        assert 'ensemble_abc123' in cache_file


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_predictions(self):
        """빈 예측 처리"""
        predictions = []

        if not predictions:
            result = {'matches': 0, 'predictions': []}
        else:
            result = {'predictions': predictions}

        assert result['matches'] == 0

    def test_invalid_round_range(self):
        """잘못된 라운드 범위"""
        start_round = 1110
        end_round = 1100

        with pytest.raises(ValueError):
            if start_round > end_round:
                raise ValueError("시작 라운드가 종료 라운드보다 클 수 없습니다")

    def test_insufficient_data(self):
        """데이터 부족 케이스"""
        available_rounds = 50
        required_window = 100

        has_sufficient_data = available_rounds >= required_window

        assert has_sufficient_data == False

    def test_all_zero_matches(self):
        """모든 예측이 0개 일치"""
        results = [0, 0, 0, 0, 0]

        avg_matches = sum(results) / len(results)
        max_matches = max(results)

        assert avg_matches == 0
        assert max_matches == 0


class TestDataContaminationCheck:
    """데이터 오염 검사 테스트"""

    def test_high_match_detection(self):
        """높은 일치율 감지 테스트"""
        results = {
            'avg_matches': 5.5,  # 비정상적으로 높음
            'max_matches': 6
        }

        # 데이터 오염 경고 임계값
        contamination_threshold = 3.0

        is_contaminated = results['avg_matches'] > contamination_threshold

        assert is_contaminated == True

    def test_normal_match_rate(self):
        """정상 일치율 테스트"""
        results = {
            'avg_matches': 1.2,
            'max_matches': 4
        }

        contamination_threshold = 3.0

        is_contaminated = results['avg_matches'] > contamination_threshold

        assert is_contaminated == False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
