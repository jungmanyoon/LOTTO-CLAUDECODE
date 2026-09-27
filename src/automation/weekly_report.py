# -*- coding: utf-8 -*-
"""이번 주 결과 보고: 새 당첨번호가 들어오면 재분석보다 먼저 우리 예측을 대조해 보고한다.

순서 (사용자 요청 2026-09-27: "이번 주 결과 보고를 하고 재분석으로 넘어가야")
  1) 우리 발행분 전체를 새 당첨번호와 대조해 저장한다(ResultChecker). 화면 성적표가 이 결과를 읽는다.
  2) 그 회차 1등 조합이 당시 추천 후보 풀(극단성 풀)에 들어 있었는지 확인해 기록한다.
     풀은 예측할 때와 같게 '그 회차 직전까지의 당첨번호'(train_until = 회차 - 1)로 만든다.
     이 시스템이 노리는 것은 1등 조합이 풀 안에 남는 것이므로, 이것이 전략의 1차 성적이다.
     ('3개 이상 맞은 장수'는 어떤 번호를 사도 평균이 한 장당 2.383%로 같아 전략 효과를 재지 못한다.)
  3) 한눈에 보는 보고를 로그에 남긴다.

HF 서버의 추첨 감시(draw_watcher)와 main.py가 같은 함수를 쓴다.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from math import comb
from typing import Dict, List, Optional

TOTAL = comb(45, 6)
P3_PLUS = sum(comb(6, k) * comb(39, 6 - k) for k in range(3, 7)) / TOTAL  # 0.023834...
INCLUSION_START_ROUND = 1232  # 서버 자동 발행 시작 회차(대시보드 성적표 집계 시작과 같음)
MAX_INCLUSION_PER_RUN = 4  # 한 번에 풀을 새로 만드는 회차 수 상한(밀린 회차는 백필 스크립트로)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INCLUSION_PATH = os.path.join(_ROOT, "data", "predictions", "pool_inclusion.json")


# ---------------------------------------------------------------------------
# 1등 조합 풀 포함 기록
# ---------------------------------------------------------------------------
def load_inclusion(path: Optional[str] = None) -> Dict:
    path = path or INCLUSION_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("rounds"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "rounds": {}}


def save_inclusion(data: Dict, path: Optional[str] = None) -> None:
    path = path or INCLUSION_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data["note"] = (
        "회차별로 그 회차 1등 조합이 당시 추천 후보 풀(그 회차 직전까지의 당첨번호로 만든 극단성 풀)에 "
        "들어 있었는지 기록한다. 풀 비율만큼은 무작위로도 들어간다(예: 150만/815만 = 18.4%)."
    )
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def pool_inclusion(db_manager, round_num: int) -> Dict:
    """round_num 1등 조합이 train_until=round_num-1 로 만든 운영 풀에 들어 있었는지."""
    import numpy as np

    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor

    row = db_manager.get_numbers_by_round(round_num)
    if not row:
        raise ValueError(f"{round_num}회 당첨번호가 DB에 없습니다")
    winner = sorted(int(x) for x in str(row[1]).split(",")[:6])
    predictor = ExtremenessPoolPredictor(db_manager)
    size = int(predictor.build_pool(train_until=round_num - 1))
    pool = predictor._pool_combos
    hit = bool(np.any(np.all(pool == np.asarray(winner, dtype=pool.dtype), axis=1)))
    return {
        "round": int(round_num),
        "in_pool": hit,
        "winner": winner,
        "pool_size": size,
        "pool_fraction": size / TOTAL,
        "train_until": int(round_num - 1),
        "target_K": int(predictor.target_K),
        "scoring_method": str(predictor.scoring_method),
        "computed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def record_pool_inclusion(db_manager, round_num: int, path: Optional[str] = None) -> Dict:
    data = load_inclusion(path)
    entry = pool_inclusion(db_manager, round_num)
    data["rounds"][str(round_num)] = entry
    save_inclusion(data, path)
    return entry


def inclusion_summary(data: Optional[Dict] = None) -> Dict:
    data = data if data is not None else load_inclusion()
    entries = [v for v in data.get("rounds", {}).values() if isinstance(v, dict) and "in_pool" in v]
    weeks = len(entries)
    hits = sum(1 for v in entries if v["in_pool"])
    expected = sum(float(v.get("pool_fraction", 0)) for v in entries)
    return {
        "weeks": weeks,
        "in_pool": hits,
        "rate": hits / weeks if weeks else None,
        "expected_if_random": expected,
        "pool_fraction": expected / weeks if weeks else None,
    }


# ---------------------------------------------------------------------------
# 회차 성적 요약
# ---------------------------------------------------------------------------
def round_summary(predictions_db: str, lotto_db: str, round_num: int) -> Dict:
    with sqlite3.connect(predictions_db) as conn:
        rows = conn.execute(
            "SELECT match_count, bonus_match FROM prediction_results WHERE round = ?", (round_num,)
        ).fetchall()
    matches = [int(m or 0) for m, _ in rows]
    ranks = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for m, bonus in rows:
        m = int(m or 0)
        if m == 6:
            ranks[1] += 1
        elif m == 5:
            ranks[2 if bonus else 3] += 1
        elif m == 4:
            ranks[4] += 1
        elif m == 3:
            ranks[5] += 1
    tickets = len(matches)
    hits3 = sum(1 for m in matches if m >= 3)
    out = {
        "round": int(round_num),
        "tickets": tickets,
        "best": max(matches) if matches else None,
        "ranks": ranks,
        "hits3": hits3,
        "per100": round(100 * hits3 / tickets, 2) if tickets else None,
        "random_per100": round(100 * P3_PLUS, 2),
        "winning": None,
        "bonus": None,
        "draw_date": None,
    }
    with sqlite3.connect(lotto_db) as conn:
        win = conn.execute(
            "SELECT numbers, bonus_number, draw_date FROM lotto_numbers WHERE round = ?", (round_num,)
        ).fetchone()
    if win:
        out["winning"] = [int(x) for x in str(win[0]).split(",")[:6]]
        out["bonus"] = win[1]
        out["draw_date"] = win[2]
    return out


def log_cumulative(log, cumulative: Dict) -> None:
    if cumulative.get("weeks"):
        log.info(
            "  누적(%s회부터): %s주 중 %s주 풀 안 (무작위였다면 약 %.1f주)",
            INCLUSION_START_ROUND, cumulative["weeks"], cumulative["in_pool"], cumulative["expected_if_random"],
        )


def _log_report(log, summary: Dict, inclusion: Optional[Dict], cumulative: Dict) -> None:
    r = summary
    ranks = r["ranks"]
    rank_text = " / ".join(f"{k}등 {ranks[k]}장" for k in (1, 2, 3, 4, 5) if ranks[k]) or "당첨 없음"
    log.info("=" * 64)
    log.info(
        "[이번 주 결과 보고] %s회 (%s) 당첨번호 %s + 보너스 %s",
        r["round"], r["draw_date"], " ".join(str(n) for n in (r["winning"] or [])), r["bonus"],
    )
    log.info(
        "  우리 예측 %s장 | 최고 %s개 일치 | %s | 3개 이상 %s장 = 100장당 %s (어떤 번호든 평균 %s)",
        r["tickets"], r["best"], rank_text, r["hits3"], r["per100"], r["random_per100"],
    )
    if inclusion is not None:
        log.info(
            "  1등 조합이 우리 추천 풀(%s개 = 800만 중 %.1f%%)에: %s",
            f"{inclusion['pool_size']:,}", 100 * inclusion["pool_fraction"],
            "들어 있었음" if inclusion["in_pool"] else "없었음",
        )
        log_cumulative(log, cumulative)
    log.info("  전국 구매자 비교는 공식 집계(판매량·당첨자 수)가 들어오면 화면 성적표에 표시됩니다.")
    log.info("=" * 64)


def run_weekly_report(db_manager, check_pool: bool = True, logger=None,
                      inclusion_path: Optional[str] = None) -> Dict:
    """당첨번호가 들어왔지만 아직 대조하지 않은 회차를 대조하고 보고한다. 재분석보다 먼저 호출한다."""
    from src.core.prediction_tracker import PredictionTracker
    from src.core.result_checker import ResultChecker

    log = logger or logging.getLogger(__name__)
    tracker = PredictionTracker()
    last_round = int(db_manager.get_last_round() or 0)
    due = sorted(r for r in tracker.get_unchecked_rounds() if int(r) <= last_round)
    if not due:
        log.info("[이번 주 결과 보고] 새로 대조할 회차가 없습니다 (DB 최신 %s회)", last_round)
        return {"status": "nothing", "rounds": []}

    ResultChecker(db_manager, tracker).check_new_results()

    lotto_db = getattr(db_manager.lotto_db, "db_path", None) or os.path.join(_ROOT, "data", "lotto_numbers.db")
    reports: List[Dict] = []
    pool_budget = MAX_INCLUSION_PER_RUN
    for round_num in due:
        summary = round_summary(str(tracker.db_path), str(lotto_db), round_num)
        if not summary["tickets"]:
            continue
        inclusion = None
        if check_pool and round_num >= INCLUSION_START_ROUND and pool_budget > 0:
            pool_budget -= 1
            try:
                inclusion = record_pool_inclusion(db_manager, round_num, inclusion_path)
            except Exception as exc:  # 풀 확인 실패가 결과 대조를 막지 않되, 숨기지 않는다
                log.warning("[이번 주 결과 보고] %s회 1등 조합 풀 포함 확인 실패: %s: %s",
                            round_num, type(exc).__name__, exc)
        cumulative = inclusion_summary(load_inclusion(inclusion_path))
        _log_report(log, summary, inclusion, cumulative)
        reports.append({"summary": summary, "inclusion": inclusion})
    return {"status": "reported", "rounds": reports}
