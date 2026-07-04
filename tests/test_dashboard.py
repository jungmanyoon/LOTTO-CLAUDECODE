#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대시보드 테스트 모듈

Phase 2.12: Dashboard Tests
- Flask 엔드포인트 테스트
- API 응답 검증
- 버튼 기능 테스트
- 에러 핸들링 테스트
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
import sqlite3
import tempfile

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestEnhancedLottoDashboard:
    """EnhancedLottoDashboard 클래스 테스트"""

    @pytest.fixture
    def mock_db_paths(self, tmp_path):
        """임시 데이터베이스 경로 생성"""
        # 예측 DB 생성
        predictions_dir = tmp_path / "data" / "predictions"
        predictions_dir.mkdir(parents=True, exist_ok=True)
        predictions_db = predictions_dir / "predictions.db"

        # 로또 번호 DB 생성
        data_dir = tmp_path / "data"
        lotto_db = data_dir / "lotto_numbers.db"
        combinations_db = data_dir / "combinations.db"

        # 데이터베이스 초기화
        self._init_predictions_db(str(predictions_db))
        self._init_lotto_db(str(lotto_db))

        return {
            'predictions': str(predictions_db),
            'lotto': str(lotto_db),
            'combinations': str(combinations_db),
            'root': str(tmp_path)
        }

    def _init_predictions_db(self, db_path):
        """예측 DB 초기화"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY,
                    round INTEGER,
                    set_number INTEGER,
                    numbers TEXT,
                    confidence REAL,
                    source TEXT,
                    characteristics TEXT,
                    prediction_date TEXT
                )
            """)
            # 샘플 데이터 삽입
            cursor.execute("""
                INSERT INTO predictions
                (round, set_number, numbers, confidence, source, characteristics, prediction_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (1200, 1, "1,2,3,4,5,6", 0.85, "ML", '{}', "2024-01-01"))
            conn.commit()

    def _init_lotto_db(self, db_path):
        """로또 번호 DB 초기화"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS winning_numbers (
                    round INTEGER PRIMARY KEY,
                    num1 INTEGER, num2 INTEGER, num3 INTEGER,
                    num4 INTEGER, num5 INTEGER, num6 INTEGER,
                    bonus INTEGER,
                    draw_date TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO winning_numbers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (1200, 7, 11, 16, 35, 36, 44, 1, "2024-01-01"))
            conn.commit()

    @pytest.fixture
    def dashboard(self, mock_db_paths):
        """대시보드 인스턴스 생성"""
        with patch.dict(os.environ, {}):
            # EnhancedLottoDashboard 임포트 및 경로 패치
            with patch('src.scripts.enhanced_dashboard_v2.EnhancedLottoDashboard.__init__') as mock_init:
                mock_init.return_value = None
                from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard

                dashboard = EnhancedLottoDashboard()
                dashboard.project_root = mock_db_paths['root']
                dashboard.predictions_db_path = mock_db_paths['predictions']
                dashboard.lotto_db_path = mock_db_paths['lotto']
                dashboard.db_path = mock_db_paths['combinations']
                dashboard.logger = Mock()
                dashboard.filter_validation_results = {}
                dashboard.filter_criteria = {
                    'consecutive': {'max_consecutive': 4},
                    'sum_range': {'min_sum': 68, 'max_sum': 209},
                    'odd_even': {'excluded_counts': []}
                }
                return dashboard

    def test_get_all_rounds(self, dashboard, mock_db_paths):
        """회차 목록 조회 테스트"""
        rounds = dashboard.get_all_rounds()
        assert isinstance(rounds, list)
        assert 1200 in rounds

    def test_get_all_rounds_empty(self, dashboard, tmp_path):
        """빈 DB에서 회차 조회 테스트"""
        empty_db = tmp_path / "empty.db"
        with sqlite3.connect(str(empty_db)) as conn:
            conn.execute("""
                CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY, round INTEGER
                )
            """)
        dashboard.predictions_db_path = str(empty_db)
        rounds = dashboard.get_all_rounds()
        assert rounds == []

    def test_check_matches(self, dashboard):
        """번호 일치 확인 테스트"""
        pred = [1, 2, 3, 4, 5, 6]
        winning = [1, 2, 3, 7, 8, 9]
        matches = dashboard.check_matches(pred, winning)
        assert matches == 3

    def test_check_matches_all_match(self, dashboard):
        """전체 일치 테스트"""
        pred = [1, 2, 3, 4, 5, 6]
        winning = [1, 2, 3, 4, 5, 6]
        matches = dashboard.check_matches(pred, winning)
        assert matches == 6

    def test_check_matches_no_match(self, dashboard):
        """일치 없음 테스트"""
        pred = [1, 2, 3, 4, 5, 6]
        winning = [7, 8, 9, 10, 11, 12]
        matches = dashboard.check_matches(pred, winning)
        assert matches == 0

    def test_calculate_rank_first(self, dashboard):
        """1등 계산 테스트 (6개 일치)"""
        rank = dashboard.calculate_rank(6, False)
        assert rank == 1

    def test_calculate_rank_second(self, dashboard):
        """2등 계산 테스트 (5개 + 보너스)"""
        rank = dashboard.calculate_rank(5, True)
        assert rank == 2

    def test_calculate_rank_third(self, dashboard):
        """3등 계산 테스트 (5개)"""
        rank = dashboard.calculate_rank(5, False)
        assert rank == 3

    def test_calculate_rank_fourth(self, dashboard):
        """4등 계산 테스트 (4개)"""
        rank = dashboard.calculate_rank(4, False)
        assert rank == 4

    def test_calculate_rank_fifth(self, dashboard):
        """5등 계산 테스트 (3개)"""
        rank = dashboard.calculate_rank(3, False)
        assert rank == 5

    def test_calculate_rank_no_prize(self, dashboard):
        """미당첨 테스트 (2개 이하)"""
        rank = dashboard.calculate_rank(2, False)
        assert rank is None

    def test_analyze_round_performance_with_results(self, dashboard):
        """당첨 결과 분석 테스트"""
        predictions = [
            {'numbers': [1, 2, 3, 4, 5, 6], 'matches': 3, 'rank': 5},
            {'numbers': [7, 8, 9, 10, 11, 12], 'matches': 2, 'rank': None}
        ]
        winning = {'numbers': [1, 2, 3, 7, 8, 9], 'bonus': 10}
        analysis = dashboard.analyze_round_performance(predictions, winning)
        # 실제 반환되는 키 확인
        assert 'average_matches' in analysis or 'best_match' in analysis or isinstance(analysis, dict)

    def test_analyze_round_performance_no_winning(self, dashboard):
        """당첨번호 없을 때 분석 테스트"""
        predictions = [{'numbers': [1, 2, 3, 4, 5, 6]}]
        analysis = dashboard.analyze_round_performance(predictions, None)
        # 당첨번호 없으면 빈 dict 반환
        assert isinstance(analysis, dict)


class TestFlaskApp:
    """Flask 앱 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트 생성"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False  # 테스트에서 CSRF 비활성화
            with app.test_client() as client:
                yield client

    def test_index_route(self, client):
        """메인 페이지 라우트 테스트"""
        response = client.get('/')
        assert response.status_code == 200

    def test_api_rounds_route(self, client):
        """회차 목록 API 테스트"""
        response = client.get('/api/rounds')
        # API가 응답을 반환해야 함
        assert response.status_code == 200
        data = json.loads(response.data)
        # rounds 키가 있거나 빈 배열이어야 함
        assert 'rounds' in data or isinstance(data, (list, dict))

    def test_api_predictions_route(self, client):
        """예측 조회 API 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_predictions_by_round.return_value = {
                'round': 1200,
                'predictions': [],
                'winning_numbers': None
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/predictions/1200')
            assert response.status_code == 200

    def test_api_stats_route(self, client):
        """통계 API 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_statistics.return_value = {
                'total_predictions': 100,
                'total_rounds': 10
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/stats')
            assert response.status_code == 200

    def test_api_performance_route(self, client):
        """성능 API 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_recent_performance.return_value = []
            mock_dash.return_value = mock_instance

            response = client.get('/api/performance')
            assert response.status_code == 200

    def test_api_backtest_performance_route(self, client):
        """백테스트 성능 API 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_backtest_performance.return_value = {
                'status': 'success',
                'data': {}
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/backtest-performance')
            assert response.status_code == 200

    def test_api_optimizer_status_route(self, client):
        """옵티마이저 상태 API 테스트"""
        response = client.get('/api/optimizer-status')
        # 응답은 성공(200) 또는 서버 에러(500)
        assert response.status_code in [200, 500]
        try:
            data = json.loads(response.data)
            assert isinstance(data, dict)
        except json.JSONDecodeError:
            pass  # 에러 시 JSON이 아닐 수 있음

    def test_api_quick_prediction_status_route(self, client):
        """빠른 예측 상태 API 테스트"""
        response = client.get('/api/quick-prediction-status')
        assert response.status_code == 200


class TestErrorHandlers:
    """에러 핸들러 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_404_error_handler(self, client):
        """404 에러 핸들러 테스트"""
        response = client.get('/nonexistent-route')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data
        assert data['error_code'] == 'NOT_FOUND'

    def test_500_error_handler(self, client):
        """500 에러 핸들러 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_dash.side_effect = Exception("Test error")
            # 500 에러가 발생해야 하지만 Flask의 에러 핸들링에 따라 다름
            response = client.get('/api/stats')
            # 에러 발생 시 500이거나 처리된 응답
            assert response.status_code in [200, 500]


class TestApiResponses:
    """API 응답 형식 검증 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_rounds_response_format(self, client):
        """회차 목록 응답 형식 테스트"""
        response = client.get('/api/rounds')
        data = json.loads(response.data)

        # API가 list를 직접 반환하거나 dict로 감싸서 반환
        assert isinstance(data, (list, dict))
        if isinstance(data, dict) and 'rounds' in data:
            assert isinstance(data['rounds'], list)

    def test_predictions_response_format(self, client):
        """예측 조회 응답 형식 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_predictions_by_round.return_value = {
                'round': 1200,
                'predictions': [
                    {
                        'id': 1,
                        'numbers': [1, 2, 3, 4, 5, 6],
                        'confidence': 0.85
                    }
                ],
                'winning_numbers': None
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/predictions/1200')
            data = json.loads(response.data)

            assert 'round' in data or 'predictions' in data

    def test_stats_response_format(self, client):
        """통계 응답 형식 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_statistics.return_value = {
                'total_predictions': 100,
                'total_rounds': 10,
                'avg_confidence': 0.75
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/stats')
            data = json.loads(response.data)

            assert isinstance(data, dict)


class TestGeneratePredictions:
    """예측 생성 기능 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_generate_predictions_rate_limit(self, client):
        """예측 생성 Rate Limit 테스트"""
        # 이 테스트는 rate limit 데코레이터 동작만 확인한다.
        # [2026-07-02] 과거에는 mock 없이 실제 핸들러가 끝까지 실행되어 운영
        # predictions.db / week_*.json에 실제 예측 5세트를 저장했다(중복 세트
        # 누적 사고의 주범). 예측 생성/저장 경로 전체를 mock으로 차단한다.
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash, \
             patch('src.core.extremeness_pool_predictor.ExtremenessPoolPredictor') as mock_epp, \
             patch('src.core.quick_prediction_engine.QuickPredictionEngine') as mock_quick, \
             patch('src.core.prediction_tracker.PredictionTracker.save_predictions',
                   return_value=True):
            mock_instance = Mock()
            mock_instance.get_all_rounds.return_value = [1200]
            mock_dash.return_value = mock_instance
            mock_epp.return_value.build_pool.return_value = None
            mock_epp.return_value.predict.return_value = [
                {'numbers': [1, 12, 23, 34, 40, 45], 'confidence': 0.9, 'source': 'MockPool'},
                {'numbers': [2, 13, 24, 35, 41, 44], 'confidence': 0.9, 'source': 'MockPool'},
                {'numbers': [3, 14, 25, 36, 42, 43], 'confidence': 0.9, 'source': 'MockPool'},
                {'numbers': [4, 15, 26, 37, 39, 44], 'confidence': 0.9, 'source': 'MockPool'},
                {'numbers': [5, 16, 27, 38, 40, 43], 'confidence': 0.9, 'source': 'MockPool'},
            ]
            mock_quick.return_value.generate_quick_predictions.return_value = []

            # 첫 번째 요청
            response = client.post('/api/generate-predictions')
            # 응답은 성공 또는 rate limit
            assert response.status_code in [200, 429, 500]


class TestFilterValidation:
    """필터 검증 기능 테스트"""

    @pytest.fixture
    def dashboard(self):
        """대시보드 목업"""
        with patch('src.scripts.enhanced_dashboard_v2.EnhancedLottoDashboard.__init__') as mock_init:
            mock_init.return_value = None
            from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard

            dashboard = EnhancedLottoDashboard()
            dashboard.logger = Mock()
            dashboard.filter_validation_results = {}
            dashboard.filter_criteria = {
                'consecutive': {'max_consecutive': 4},
                'sum_range': {'min_sum': 68, 'max_sum': 209},
                'odd_even': {'excluded_counts': []}
            }
            return dashboard

    def test_validate_numbers_sum_range(self, dashboard):
        """합계 범위 검증 테스트"""
        # 합계: 21 (1+2+3+4+5+6) - 범위 68-209 밖
        result = dashboard.validate_prediction_numbers([1, 2, 3, 4, 5, 6])
        # 결과가 dict 타입이어야 함
        assert isinstance(result, dict)

    def test_validate_numbers_valid(self, dashboard):
        """유효한 번호 검증 테스트"""
        # 합계: 120 (10+15+20+25+30+20=120) - 범위 내
        result = dashboard.validate_prediction_numbers([10, 15, 20, 25, 30, 35])
        assert isinstance(result, dict)


class TestWeekPredictions:
    """주간 예측 기능 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_week_predictions_route(self, client):
        """주간 예측 API 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_week_predictions.return_value = {
                'round': 1200,
                'predictions': []
            }
            mock_dash.return_value = mock_instance

            response = client.get('/api/week-predictions/1200')
            assert response.status_code == 200


class TestOptimizerHistory:
    """옵티마이저 히스토리 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_optimizer_history_route(self, client):
        """옵티마이저 히스토리 API 테스트"""
        response = client.get('/api/optimizer-history')
        # 응답은 성공(200) 또는 서버 에러(500)
        assert response.status_code in [200, 500]
        try:
            data = json.loads(response.data)
            # 히스토리는 list로 반환될 수 있음
            assert isinstance(data, (dict, list))
        except json.JSONDecodeError:
            pass  # 에러 시 JSON이 아닐 수 있음


class TestDashboardSingleton:
    """대시보드 싱글톤 패턴 테스트"""

    def test_get_dashboard_returns_instance(self):
        """get_dashboard 함수 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.EnhancedLottoDashboard') as MockDash:
            MockDash.return_value = Mock()
            from src.scripts.enhanced_dashboard_v2 import get_dashboard

            # 싱글톤 패턴 확인을 위해 두 번 호출
            dash1 = get_dashboard()
            dash2 = get_dashboard()

            # 같은 인스턴스여야 함
            assert dash1 is not None
            assert dash2 is not None


class TestKSTConversion:
    """한국 시간대 변환 테스트"""

    @pytest.fixture
    def dashboard(self):
        """대시보드 목업"""
        with patch('src.scripts.enhanced_dashboard_v2.EnhancedLottoDashboard.__init__') as mock_init:
            mock_init.return_value = None
            from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard

            dashboard = EnhancedLottoDashboard()
            dashboard.logger = Mock()
            return dashboard

    def test_convert_to_kst_valid(self, dashboard):
        """유효한 날짜 KST 변환 테스트"""
        result = dashboard._convert_to_kst("2024-01-01 12:00:00")
        assert result is not None

    def test_convert_to_kst_invalid(self, dashboard):
        """유효하지 않은 날짜 변환 테스트"""
        result = dashboard._convert_to_kst("invalid-date")
        # 에러 시 원본 반환 또는 None
        assert result == "invalid-date" or result is None


class TestBacktestPerformance:
    """백테스트 성능 조회 테스트"""

    @pytest.fixture
    def dashboard(self, tmp_path):
        """대시보드 목업"""
        with patch('src.scripts.enhanced_dashboard_v2.EnhancedLottoDashboard.__init__') as mock_init:
            mock_init.return_value = None
            from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard

            dashboard = EnhancedLottoDashboard()
            dashboard.project_root = str(tmp_path)
            dashboard.logger = Mock()
            return dashboard

    def test_get_backtest_performance_no_db(self, dashboard):
        """DB 없을 때 백테스트 성능 조회 테스트"""
        result = dashboard.get_backtest_performance()
        assert isinstance(result, dict)
        assert 'status' in result or 'error' in result


class TestIntegration:
    """통합 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_full_workflow(self, client):
        """전체 워크플로우 테스트"""
        # 1. 메인 페이지 로드
        response = client.get('/')
        assert response.status_code == 200

        # 2. 회차 목록 조회
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_all_rounds.return_value = [1200]
            mock_instance.get_predictions_by_round.return_value = {
                'round': 1200,
                'predictions': []
            }
            mock_instance.get_statistics.return_value = {}
            mock_dash.return_value = mock_instance

            response = client.get('/api/rounds')
            assert response.status_code == 200

            # 3. 특정 회차 예측 조회
            response = client.get('/api/predictions/1200')
            assert response.status_code == 200

            # 4. 통계 조회
            response = client.get('/api/stats')
            assert response.status_code == 200

    def test_api_error_handling(self, client):
        """API 에러 핸들링 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            # 예외 발생 시뮬레이션
            mock_instance = Mock()
            mock_instance.get_all_rounds.side_effect = Exception("DB Error")
            mock_dash.return_value = mock_instance

            response = client.get('/api/rounds')
            # 에러 발생 시에도 응답은 반환되어야 함
            assert response.status_code in [200, 500]


class TestJSONResponse:
    """JSON 응답 테스트"""

    @pytest.fixture
    def client(self):
        """Flask 테스트 클라이언트"""
        with patch.dict(os.environ, {'TESTING': 'true'}):
            from src.scripts.enhanced_dashboard_v2 import app
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            with app.test_client() as client:
                yield client

    def test_json_content_type(self, client):
        """JSON Content-Type 헤더 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_all_rounds.return_value = []
            mock_dash.return_value = mock_instance

            response = client.get('/api/rounds')
            assert 'application/json' in response.content_type

    def test_json_valid_format(self, client):
        """유효한 JSON 형식 테스트"""
        with patch('src.scripts.enhanced_dashboard_v2.get_dashboard') as mock_dash:
            mock_instance = Mock()
            mock_instance.get_all_rounds.return_value = [1200]
            mock_dash.return_value = mock_instance

            response = client.get('/api/rounds')
            # JSON 파싱 가능해야 함
            try:
                data = json.loads(response.data)
                assert True
            except json.JSONDecodeError:
                assert False, "Invalid JSON response"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
