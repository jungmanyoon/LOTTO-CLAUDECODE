# -*- coding: utf-8 -*-
"""추첨 시각 계산 (한국 시간).

로또 6/45는 매주 토요일 20:00에 판매가 마감되고 20:35에 추첨한다. 회차는 매주 1씩 늘어난다.
달력 규칙을 따로 두지 않고, DB에 저장된 마지막 회차의 추첨일에서 주 단위로 다음 회차 시각을 계산한다.

쓰임
  - 추첨 감시(draw_watcher): 다음 회차 추첨 직후부터 당첨번호를 확인한다.
  - 예측 저장 보호(main.py, bulk_predict_once.py, 대시보드 버튼): 판매가 이미 마감된 회차 번호로
    예측을 저장하지 않는다. 새 당첨번호가 DB에 들어오기 전에는 'DB 마지막 회차 + 1'이 이미 추첨이
    끝난 회차를 가리킬 수 있기 때문이다(2026-09-26 1243회: 추첨 뒤 22시대 발행분이 섞였다).
"""

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

KST = timezone(timedelta(hours=9))
SALES_CLOSE = (20, 0)  # 토 20:00 판매 마감
DRAW_TIME = (20, 35)  # 토 20:35 추첨

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_LOTTO_DB = os.path.join(_ROOT, "data", "lotto_numbers.db")


def now_kst() -> datetime:
    return datetime.now(KST)


def parse_draw_date(text) -> date:
    """'2026-09-26', '2026.09.26', '20260926' 모두 허용한다."""
    raw = str(text).strip()[:10].replace(".", "-").replace("/", "-")
    if len(raw) == 8 and raw.isdigit():
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return datetime.strptime(raw, "%Y-%m-%d").date()


def round_day(target_round: int, last_round: int, last_draw_date) -> date:
    """마지막 회차 추첨일에서 주 단위로 target 회차의 추첨일을 계산한다."""
    return parse_draw_date(last_draw_date) + timedelta(days=7 * (int(target_round) - int(last_round)))


def _at(day: date, hour_minute) -> datetime:
    return datetime(day.year, day.month, day.day, hour_minute[0], hour_minute[1], tzinfo=KST)


def sales_close_at(target_round: int, last_round: int, last_draw_date) -> datetime:
    return _at(round_day(target_round, last_round, last_draw_date), SALES_CLOSE)


def draw_at(target_round: int, last_round: int, last_draw_date) -> datetime:
    return _at(round_day(target_round, last_round, last_draw_date), DRAW_TIME)


def latest_round_info(db_path: Optional[str] = None) -> Tuple[Optional[int], Optional[str]]:
    """DB의 마지막 회차와 그 추첨일. 읽을 수 없으면 (None, None)."""
    path = db_path or DEFAULT_LOTTO_DB
    if not os.path.exists(path):
        return None, None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT round, draw_date FROM lotto_numbers ORDER BY round DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None, None
    return int(row[0]), row[1]


def sales_closed_for(target_round: int, db_path: Optional[str] = None,
                     now: Optional[datetime] = None) -> Tuple[bool, Optional[datetime]]:
    """target 회차의 판매가 이미 마감됐는지. 판단할 수 없으면 (False, None)으로 막지 않는다."""
    last_round, last_date = latest_round_info(db_path)
    if last_round is None or not last_date:
        return False, None
    try:
        close = sales_close_at(target_round, last_round, last_date)
    except ValueError:
        return False, None
    return (now or now_kst()) >= close, close
