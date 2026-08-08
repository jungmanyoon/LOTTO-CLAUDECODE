#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""성적표가 항상 '마지막 회차 기준'으로 나오는지 지키는 회귀 테스트.

[왜 이 테스트가 생겼나 - 2026-08-08]
1236회 추첨 직후, 우리 예측 대조(420세트, 최고 4개 일치)는 이미 끝나 DB에 있었는데도
화면 성적표는 1235회에서 멈춰 보였다. 원인은 두 겹이었다.

  1) 수집: 폴링 스크립트가 LottoNumbersDB()를 인자 없이 만들다 TypeError -> except가 삼키고
     "당첨번호만 수집"으로 넘어가, 공식 통계(총 판매량/등수별 당첨자 수)가 저장되지 않았다.
  2) 표시: 성적표가 '공식 통계가 없는 회차'를 통째로 건너뛰어(continue), 최신 회차가 사라졌다.

(1)은 고쳤지만 통계는 당첨번호보다 늦게 들어올 수 있다. 그때도 화면이 지난 회차에 멈춘 것처럼
보이면 안 된다. 그래서 (2)를 "비교 상대가 없으면 '집계 중'으로 표시하되 회차는 유지"로 바꿨고,
이 테스트가 그 규칙을 고정한다.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _make_predictions_db(path: str, rounds: dict) -> None:
    """회차별 (대조 장수, 3개 이상 적중 건수)로 prediction_results 를 채운다."""
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE prediction_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                prediction_id INTEGER,
                actual_numbers TEXT NOT NULL,
                bonus_number INTEGER,
                match_count INTEGER,
                bonus_match BOOLEAN DEFAULT 0,
                rank INTEGER,
                prize_amount INTEGER,
                check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for rnd, (checked, hits) in rounds.items():
            for i in range(checked):
                conn.execute(
                    "INSERT INTO prediction_results (round, actual_numbers, match_count) VALUES (?, ?, ?)",
                    (rnd, '1,2,3,4,5,6', 3 if i < hits else 1),
                )


def _make_lotto_db(path: str, stats: dict) -> None:
    """회차별 (총 판매액, 3개 이상 당첨 건수)로 lotto_statistics 를 채운다."""
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE lotto_statistics (
                round INTEGER PRIMARY KEY,
                first_winners INTEGER DEFAULT 0, first_prize BIGINT DEFAULT 0,
                second_winners INTEGER DEFAULT 0, second_prize BIGINT DEFAULT 0,
                third_winners INTEGER DEFAULT 0, third_prize BIGINT DEFAULT 0,
                fourth_winners INTEGER DEFAULT 0, fourth_prize BIGINT DEFAULT 0,
                fifth_winners INTEGER DEFAULT 0, fifth_prize BIGINT DEFAULT 0,
                total_sales BIGINT DEFAULT 0
            )
        """)
        for rnd, (sales, wins) in stats.items():
            conn.execute(
                "INSERT INTO lotto_statistics (round, fifth_winners, total_sales) VALUES (?, ?, ?)",
                (rnd, wins, sales),
            )


@pytest.fixture
def dashboard(tmp_path):
    """임시 DB만 바라보는 대시보드 인스턴스."""
    from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard

    dash = EnhancedLottoDashboard()
    dash.predictions_db_path = str(tmp_path / "predictions.db")
    dash.lotto_db_path = str(tmp_path / "lotto_numbers.db")
    return dash


@pytest.mark.unit
def test_최신회차_통계가_아직_없어도_성적표에_남는다(dashboard, tmp_path):
    """추첨 직후: 우리 대조는 끝났고 전국 공식 집계만 아직인 상태."""
    _make_predictions_db(str(tmp_path / "predictions.db"),
                         {1235: (400, 12), 1236: (420, 18)})
    _make_lotto_db(str(tmp_path / "lotto_numbers.db"),
                   {1235: (100_000_000_000, 2_400_000)})  # 1236 통계는 아직 없음

    result = dashboard.get_real_buyer_comparison()

    assert result['available'] is True
    # 핵심: 최신 회차가 사라지지 않는다
    assert result['latest_round'] == 1236
    assert result['rounds'][0]['round'] == 1236
    assert result['rounds'][0]['pending'] is True
    # 우리 성적은 그대로 보여준다 (420장 중 18건 = 100장당 4.29개)
    assert result['rounds'][0]['our_per100'] == pytest.approx(4.29, abs=0.01)
    # 비교 상대가 없으므로 상대 수치와 배수는 비운다
    assert result['rounds'][0]['real_per100'] is None
    assert result['rounds'][0]['ratio'] is None
    # 누적/판정은 비교 가능한 회차만 쓴다 (집계 대기 회차를 섞어 왜곡하지 않는다)
    assert result['summary']['rounds'] == 1
    assert result['summary']['pending_rounds'] == [1236]
    assert result['summary']['our_tickets'] == 400


@pytest.mark.unit
def test_통계가_들어오면_정상_비교로_바뀐다(dashboard, tmp_path):
    """공식 집계가 들어온 뒤: 집계 대기 표시가 사라지고 배수가 계산된다."""
    _make_predictions_db(str(tmp_path / "predictions.db"),
                         {1235: (400, 12), 1236: (400, 16)})
    _make_lotto_db(str(tmp_path / "lotto_numbers.db"),
                   {1235: (100_000_000_000, 2_400_000),
                    1236: (100_000_000_000, 2_000_000)})  # 1억 장 중 200만 건 = 100장당 2개

    result = dashboard.get_real_buyer_comparison()

    latest = result['rounds'][0]
    assert latest['round'] == 1236
    assert latest.get('pending', False) is False
    assert latest['real_per100'] == pytest.approx(2.0, abs=0.01)
    assert latest['our_per100'] == pytest.approx(4.0, abs=0.01)
    assert latest['ratio'] == pytest.approx(2.0, abs=0.01)
    assert result['summary']['rounds'] == 2
    assert result['summary']['pending_rounds'] == []


@pytest.mark.unit
def test_대조_기록이_없으면_빈_결과(dashboard, tmp_path):
    """예측 대조가 하나도 없으면 '없음'으로 정직하게 알린다(가짜 값 금지)."""
    _make_predictions_db(str(tmp_path / "predictions.db"), {})
    _make_lotto_db(str(tmp_path / "lotto_numbers.db"), {1235: (100_000_000_000, 2_400_000)})

    result = dashboard.get_real_buyer_comparison()

    assert result['available'] is False
    assert result['rounds'] == []
