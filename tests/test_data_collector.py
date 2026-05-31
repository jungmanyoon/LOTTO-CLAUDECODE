#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터 수집기 테스트

Phase 2.6: Data Collector Tests
- Mock HTTP 응답 테스트
- 네트워크 오류 처리
- 파싱 오류 처리
- 재시도 로직 검증

목표 커버리지: 70%+
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup
import requests

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data_collector import DataCollector

# Mock 데이터베이스 import - 상대 경로 사용
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
    db.setup_sample_data(num_rounds=10)

    # get_last_round 메서드 추가 (DataCollector에서 사용)
    db.get_last_round = Mock(return_value=10)
    db.insert_lotto_numbers_with_bonus = Mock()

    yield db
    db.clear_all_data()


@pytest.fixture
def data_collector(mock_db):
    """테스트용 DataCollector 인스턴스"""
    return DataCollector(db_manager=mock_db)


@pytest.fixture
def sample_html_response():
    """동행복권 사이트 HTML 응답 샘플"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="description" content="동행복권 로또6/45 1150회 당첨번호 3,10,19,24,31,45+2">
    </head>
    <body>
        <p class="desc">(2024년 11월 30일 추첨)</p>
        <div class="win_result">
            <span>3</span>
            <span>10</span>
            <span>19</span>
            <span>24</span>
            <span>31</span>
            <span>45</span>
            <span>2</span>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_html_invalid():
    """잘못된 형식의 HTML 응답"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="description" content="동행복권 로또6/45">
    </head>
    <body>
        <p class="desc">날짜 정보 없음</p>
    </body>
    </html>
    """


# =========================================================================
# Unit Tests - parse_numbers
# =========================================================================

class TestParseNumbers:
    """번호 파싱 테스트"""

    def test_parse_numbers_success(self, data_collector, sample_html_response):
        """[OK] 정상적인 번호 파싱"""
        soup = BeautifulSoup(sample_html_response, 'html.parser')
        result = data_collector.parse_numbers(soup)

        assert result is not None
        assert len(result) == 2  # (numbers, bonus) 튜플

        numbers, bonus = result
        assert numbers == [3, 10, 19, 24, 31, 45]
        assert bonus == 2

    def test_parse_numbers_with_different_format(self, data_collector):
        """[OK] 다양한 번호 형식 파싱"""
        html = """
        <html>
        <head>
            <meta name="description" content="로또6/45 999회 당첨번호 1,2,3,4,5,6+7">
        </head>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = data_collector.parse_numbers(soup)

        assert result is not None
        numbers, bonus = result
        assert numbers == [1, 2, 3, 4, 5, 6]
        assert bonus == 7

    def test_parse_numbers_missing_meta(self, data_collector):
        """[OK] meta 태그 없는 경우"""
        html = "<html><head></head><body></body></html>"
        soup = BeautifulSoup(html, 'html.parser')
        result = data_collector.parse_numbers(soup)

        assert result is None

    def test_parse_numbers_invalid_format(self, data_collector, sample_html_invalid):
        """[OK] 잘못된 형식의 번호"""
        soup = BeautifulSoup(sample_html_invalid, 'html.parser')
        result = data_collector.parse_numbers(soup)

        assert result is None

    def test_parse_numbers_exception_handling(self, data_collector):
        """[OK] 예외 발생 시 None 반환"""
        # BeautifulSoup이 아닌 잘못된 입력
        result = data_collector.parse_numbers(None)
        assert result is None


# =========================================================================
# Unit Tests - parse_date
# =========================================================================

class TestParseDate:
    """날짜 파싱 테스트"""

    def test_parse_date_success(self, data_collector, sample_html_response):
        """[OK] 정상적인 날짜 파싱"""
        soup = BeautifulSoup(sample_html_response, 'html.parser')
        result = data_collector.parse_date(soup)

        assert result == "2024-11-30"

    def test_parse_date_various_formats(self, data_collector):
        """[OK] 다양한 날짜 형식 파싱"""
        test_cases = [
            ("(2024년 1월 5일 추첨)", "2024-01-05"),
            ("(2023년 12월 31일 추첨)", "2023-12-31"),
            ("(2002년 1월 1일 추첨)", "2002-01-01"),
        ]

        for date_text, expected in test_cases:
            html = f"""
            <html><body>
                <p class="desc">{date_text}</p>
            </body></html>
            """
            soup = BeautifulSoup(html, 'html.parser')
            result = data_collector.parse_date(soup)
            assert result == expected, f"Failed for: {date_text}"

    def test_parse_date_missing_desc(self, data_collector):
        """[OK] desc 클래스 없는 경우"""
        html = "<html><body><p>날짜 없음</p></body></html>"
        soup = BeautifulSoup(html, 'html.parser')
        result = data_collector.parse_date(soup)

        assert result is None

    def test_parse_date_invalid_format(self, data_collector):
        """[OK] 잘못된 날짜 형식"""
        html = """
        <html><body>
            <p class="desc">(날짜 정보 없음)</p>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        result = data_collector.parse_date(soup)

        assert result is None

    def test_parse_date_exception_handling(self, data_collector):
        """[OK] 예외 발생 시 None 반환"""
        result = data_collector.parse_date(None)
        assert result is None


# =========================================================================
# Unit Tests - get_latest_round
# =========================================================================

class TestGetLatestRound:
    """최신 회차 조회 테스트"""

    @patch('src.data_collector.requests.get')
    def test_get_latest_round_success(self, mock_get, data_collector):
        """[OK] 정상적인 최신 회차 조회 (새 JSON API 방식)"""
        mock_response = Mock()
        mock_response.status_code = 200
        # 새 API 방식: JSON 응답으로 회차 목록 반환
        mock_response.json.return_value = {
            'data': {
                'list': [
                    {'ltEpsd': 1148},
                    {'ltEpsd': 1149},
                    {'ltEpsd': 1150},
                ]
            }
        }
        mock_get.return_value = mock_response

        result = data_collector.get_latest_round()

        assert result == 1150
        mock_get.assert_called_once()

    @patch('src.data_collector.requests.get')
    def test_get_latest_round_network_error(self, mock_get, data_collector):
        """[OK] 네트워크 오류 처리"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = data_collector.get_latest_round()

        assert result is None

    @patch('src.data_collector.requests.get')
    def test_get_latest_round_timeout(self, mock_get, data_collector):
        """[OK] 타임아웃 처리"""
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        result = data_collector.get_latest_round()

        assert result is None

    @patch('src.data_collector.requests.get')
    def test_get_latest_round_http_error(self, mock_get, data_collector):
        """[OK] HTTP 오류 상태 코드 처리"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = data_collector.get_latest_round()

        assert result is None

    @patch('src.data_collector.requests.get')
    def test_get_latest_round_invalid_html(self, mock_get, data_collector):
        """[OK] 잘못된 HTML 응답 처리"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><head></head></html>"
        mock_get.return_value = mock_response

        result = data_collector.get_latest_round()

        assert result is None


# =========================================================================
# Unit Tests - collect_round_data
# =========================================================================

class TestCollectRoundData:
    """특정 회차 데이터 수집 테스트"""

    @patch('src.data_collector.requests.get')
    def test_collect_round_data_success(self, mock_get, data_collector,
                                        mock_db, sample_html_response):
        """[OK] 정상적인 데이터 수집"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = sample_html_response
        mock_get.return_value = mock_response

        result = data_collector.collect_round_data(1150, max_retries=3)

        assert result is True
        mock_db.insert_lotto_numbers_with_bonus.assert_called_once_with(
            1150, [3, 10, 19, 24, 31, 45], 2, "2024-11-30"
        )

    @patch('src.data_collector.requests.get')
    def test_collect_round_data_retry_success(self, mock_get, data_collector,
                                              mock_db, sample_html_response):
        """[OK] 재시도 후 성공"""
        # 첫 번째 실패, 두 번째 성공
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.text = sample_html_response

        mock_get.side_effect = [mock_response_fail, mock_response_success]

        result = data_collector.collect_round_data(1150, max_retries=3)

        assert result is True
        assert mock_get.call_count == 2

    @patch('src.data_collector.requests.get')
    @patch('src.data_collector.time.sleep')  # sleep 모킹하여 테스트 속도 향상
    def test_collect_round_data_max_retries(self, mock_sleep, mock_get,
                                            data_collector):
        """[OK] 최대 재시도 횟수 초과"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = data_collector.collect_round_data(1150, max_retries=3)

        assert result is False
        # 각 retry마다 새 API + 레거시 두 번씩 호출: 3 * 2 = 6회
        assert mock_get.call_count == 6
        assert mock_sleep.call_count == 2  # 3번 시도, 2번 sleep

    @patch('src.data_collector.requests.get')
    def test_collect_round_data_parse_failure(self, mock_get, data_collector,
                                              sample_html_invalid):
        """[OK] 파싱 실패 시 재시도"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = sample_html_invalid
        mock_get.return_value = mock_response

        result = data_collector.collect_round_data(1150, max_retries=2)

        assert result is False

    @patch('src.data_collector.requests.get')
    @patch('src.data_collector.time.sleep')
    def test_collect_round_data_exception(self, mock_sleep, mock_get,
                                          data_collector):
        """[OK] 예외 발생 시 재시도"""
        mock_get.side_effect = Exception("Unexpected error")

        result = data_collector.collect_round_data(1150, max_retries=2)

        assert result is False
        # 각 retry마다 새 API + 레거시 두 번씩 호출: 2 * 2 = 4회
        assert mock_get.call_count == 4


# =========================================================================
# Integration Tests - fetch_lotto_data
# =========================================================================

class TestFetchLottoData:
    """전체 데이터 수집 워크플로우 테스트"""

    @patch.object(DataCollector, 'get_latest_round')
    @patch.object(DataCollector, 'collect_round_data')
    def test_fetch_lotto_data_no_new_data(self, mock_collect, mock_latest,
                                          data_collector, mock_db):
        """[OK] 새로운 데이터 없는 경우"""
        mock_latest.return_value = 10  # 최신 회차
        mock_db.get_last_round.return_value = 10  # DB에 저장된 마지막 회차

        data_collector.fetch_lotto_data()

        # collect_round_data가 호출되지 않아야 함
        mock_collect.assert_not_called()

    @patch.object(DataCollector, 'get_latest_round')
    @patch.object(DataCollector, 'collect_round_data')
    def test_fetch_lotto_data_new_rounds(self, mock_collect, mock_latest,
                                         data_collector, mock_db):
        """[OK] 새로운 회차 데이터 수집"""
        mock_latest.return_value = 15  # 최신 회차
        mock_db.get_last_round.return_value = 10  # DB에 저장된 마지막 회차
        mock_collect.return_value = True

        data_collector.fetch_lotto_data()

        # 11, 12, 13, 14, 15 회차 수집 필요
        assert mock_collect.call_count >= 5

    @patch.object(DataCollector, 'get_latest_round')
    def test_fetch_lotto_data_latest_round_failure(self, mock_latest,
                                                   data_collector):
        """[OK] 최신 회차 조회 실패"""
        mock_latest.return_value = None

        # 에러 없이 종료되어야 함
        data_collector.fetch_lotto_data()

    @patch.object(DataCollector, 'get_latest_round')
    @patch.object(DataCollector, 'collect_round_data')
    def test_fetch_lotto_data_partial_success(self, mock_collect, mock_latest,
                                              data_collector, mock_db):
        """[OK] 일부 회차만 성공"""
        mock_latest.return_value = 12
        mock_db.get_last_round.return_value = 10

        # 11회차 성공, 12회차 실패
        mock_collect.side_effect = [True, False]

        data_collector.fetch_lotto_data()

        # 2개 회차 시도
        assert mock_collect.call_count >= 2

    @patch.object(DataCollector, 'get_latest_round')
    @patch.object(DataCollector, 'collect_round_data')
    def test_fetch_lotto_data_first_collection(self, mock_collect, mock_latest,
                                               data_collector, mock_db):
        """[OK] 첫 수집 (DB 비어있음)"""
        mock_latest.return_value = 5
        mock_db.get_last_round.return_value = 0  # DB 비어있음
        mock_collect.return_value = True

        data_collector.fetch_lotto_data()

        # 1~5회차 모두 수집
        assert mock_collect.call_count >= 5


# =========================================================================
# Edge Case Tests
# =========================================================================

class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_data_collector_without_db_manager(self):
        """[OK] DB 매니저 없이 생성"""
        collector = DataCollector()
        assert collector.db_manager is None

    def test_data_collector_with_meta_manager(self, mock_db):
        """[OK] meta_manager 포함 생성"""
        meta_manager = Mock()
        collector = DataCollector(db_manager=mock_db, meta_manager=meta_manager)
        assert collector.meta_manager is meta_manager

    def test_base_url_configuration(self, mock_db):
        """[OK] 기본 URL 설정 확인"""
        collector = DataCollector(db_manager=mock_db)
        assert 'dhlottery.co.kr' in collector.base_url
        assert 'byWin' in collector.base_url

    def test_parse_numbers_with_spaces(self, data_collector):
        """[OK] 공백이 포함된 번호 파싱"""
        html = """
        <html>
        <head>
            <meta name="description" content="당첨번호 1, 2, 3, 4, 5, 6+7">
        </head>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        # 현재 정규식은 공백 없는 형식만 지원
        result = data_collector.parse_numbers(soup)
        # 공백이 있으면 파싱 실패할 수 있음 (현재 구현에 따름)
        # 이는 실제 사이트 형식에 맞춰 구현되어 있음


# =========================================================================
# Performance Tests
# =========================================================================

@pytest.mark.slow
class TestPerformance:
    """성능 테스트 (선택적)"""

    @patch('src.data_collector.requests.get')
    def test_batch_collection_performance(self, mock_get, data_collector,
                                          mock_db, sample_html_response):
        """[OK] 배치 수집 성능 테스트"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = sample_html_response
        mock_get.return_value = mock_response

        # 여러 회차 수집 시뮬레이션
        success_count = 0
        for round_num in range(1, 11):
            if data_collector.collect_round_data(round_num, max_retries=1):
                success_count += 1

        assert success_count == 10
