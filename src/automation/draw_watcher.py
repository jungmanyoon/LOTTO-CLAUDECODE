# -*- coding: utf-8 -*-
"""추첨 감시: 토요일 추첨 직후 당첨번호를 직접 확인해 즉시 반영한다 (HF 서버 대시보드 안에서 동작).

왜 필요한가 (2026-09-27 실측)
  GitHub Actions 예약 실행이 8월 말부터 3~5시간씩 늦게 켜져, 추첨(20:35) 뒤 당첨번호는 22~23시,
  이번 주 결과와 새 예측은 새벽 1시에야 반영됐다. 9/5·9/12에는 GitHub 서버에서 동행복권 접속이
  10회 연속 시간 초과로 실패했다. 수집 자체는 30초면 끝난다. 그래서 항상 켜져 있는 HF 서버가
  시계 역할을 맡는다.

동작
  1) 다음 회차 추첨 5분 뒤(토 20:40)부터 45초마다 동행복권 단건 조회(미게시 응답은 매우 가볍다).
     추첨 뒤 4시간이 지나도 미게시면 10분 간격으로 늦춘다(지연·휴무 대비).
  2) 게시되면 즉시
     a. 서버 DB에 당첨번호와 공식 통계를 저장한다(응답의 회차 번호가 기대 회차와 같을 때만).
        화면은 요청마다 DB를 새로 읽으므로 곧바로 보인다.
     b. GH_DISPATCH_TOKEN 이 있으면 GitHub 주간 작업(재분석·새 예측)을 즉시 호출한다.
        GitHub 서버가 동행복권에 접속하지 못해도 이어서 진행하도록 당첨번호를 함께 넘긴다.
     c. 이번 주 결과 보고: 우리 예측 대조 -> 1등 조합이 당시 풀에 들었는지 기록 -> 로그 보고.
  3) 토큰이 있으면 1시간마다 매시 발행(bulk-predict) 작업도 직접 호출한다. 예약이 밀리고 버려져
     회차당 발행이 400~800장에서 약 200장으로 줄었기 때문이다. 판매 마감~새 당첨번호 반영 사이는 건너뛴다.
  4) 켜질 때 한 번 자가 점검(동행복권 접속, 토큰 읽기 권한)을 해 상태에 남긴다.
  상태는 /api/draw-watch-status 로 확인한다. 토큰 값은 어디에도 노출하지 않는다.

켜는 조건: HF 서버(SPACE_ID 있음) 또는 LOTTO_DRAW_WATCH=1. LOTTO_DRAW_WATCH=0 이면 끈다.
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from src.automation.draw_clock import (
    DEFAULT_LOTTO_DB,
    draw_at,
    latest_round_info,
    now_kst,
    round_day,
    sales_closed_for,
)

DEFAULT_REPO = "jungmanyoon/LOTTO-CLAUDECODE"
REANALYSIS_WORKFLOW = "weekly-predict.yml"
BULK_WORKFLOW = "bulk-predict.yml"
ACTIVE_RUN_STATES = {"queued", "in_progress", "waiting", "requested", "pending"}

log = logging.getLogger("draw_watcher")


# ---------------------------------------------------------------------------
# 동행복권 응답 해석 (DataCollector 와 같은 필드 규칙)
# ---------------------------------------------------------------------------
def parse_draw_item(item: Dict, expected_round: int) -> Dict:
    """단건 조회 응답을 검증해 {round, numbers, bonus, draw_date}로 바꾼다. 이상하면 ValueError."""
    round_field = item.get("ltEpsd")
    if round_field is not None and int(round_field) != int(expected_round):
        raise ValueError(f"응답 회차 {round_field} != 기대 회차 {expected_round}")
    numbers = [item.get(f"tm{i}WnNo") for i in range(1, 7)]
    bonus = item.get("bnsWnNo")
    if any(n is None for n in numbers) or bonus is None:
        raise ValueError("당첨번호 또는 보너스가 비어 있습니다")
    numbers = [int(n) for n in numbers]
    bonus = int(bonus)
    if len(set(numbers)) != 6 or not all(1 <= n <= 45 for n in numbers):
        raise ValueError(f"당첨번호 형식 이상: {numbers}")
    if not 1 <= bonus <= 45 or bonus in numbers:
        raise ValueError(f"보너스 형식 이상: {bonus}")
    date_str = str(item.get("ltRflYmd") or "")
    draw_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 else None
    return {"round": int(expected_round), "numbers": sorted(numbers), "bonus": bonus, "draw_date": draw_date}


def default_probe(round_num: int):
    from src.scripts.poll_and_fetch_result import probe

    return probe(round_num)


# ---------------------------------------------------------------------------
# GitHub 작업 즉시 호출 (예약 실행이 3~5시간씩 늦게 켜지는 문제를 피한다)
# ---------------------------------------------------------------------------
def dispatch_workflow(workflow: str, since: datetime, inputs: Optional[Dict] = None, token: Optional[str] = None,
                      repo: Optional[str] = None, session=None) -> Dict:
    """GitHub 작업을 바로 실행한다. since 이후 이미 대기·실행 중인 같은 작업이 있으면 다시 부르지 않는다."""
    token = token if token is not None else os.environ.get("GH_DISPATCH_TOKEN", "").strip()
    if not token:
        return {"status": "no_token"}
    if session is None:
        import requests as session  # noqa: N813
    repo = repo or os.environ.get("LOTTO_GH_REPO", DEFAULT_REPO)
    base = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    after = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        runs = session.get(f"{base}/runs", headers=headers, params={"per_page": 10, "created": f">={after}"},
                           timeout=20)
        if runs.status_code == 200:
            for run in runs.json().get("workflow_runs", []):
                if run.get("status") in ACTIVE_RUN_STATES:
                    return {"status": "already_running", "run_id": run.get("id"), "run_status": run.get("status")}
        payload = {"ref": "main"}
        if inputs:
            payload["inputs"] = inputs
        resp = session.post(f"{base}/dispatches", headers=headers, json=payload, timeout=20)
    except Exception as exc:  # 네트워크 오류는 상태로 드러내고, 예약 실행이 뒤이어 받는다
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    if resp.status_code == 204:
        return {"status": "dispatched"}
    return {"status": "failed", "http": resp.status_code, "detail": (resp.text or "")[:200]}


def dispatch_reanalysis(draw: Dict, draw_time: datetime, token: Optional[str] = None,
                        repo: Optional[str] = None, session=None) -> Dict:
    """주간 작업(재분석·새 예측)을 즉시 실행하며 당첨번호를 함께 넘긴다."""
    inputs = {
        "round": str(draw["round"]),
        "numbers": ",".join(str(n) for n in draw["numbers"]),
        "bonus": str(draw["bonus"]),
        "draw_date": draw.get("draw_date") or "",
    }
    return dispatch_workflow(REANALYSIS_WORKFLOW, draw_time, inputs, token=token, repo=repo, session=session)


def check_dispatch_access(token: Optional[str] = None, repo: Optional[str] = None, session=None) -> Dict:
    """토큰으로 주간 작업 정보를 읽어 본다(읽기 전용, 실행하지 않음). 배포 직후 토큰이 맞는지 확인용."""
    token = token if token is not None else os.environ.get("GH_DISPATCH_TOKEN", "").strip()
    if not token:
        return {"status": "no_token"}
    if session is None:
        import requests as session  # noqa: N813
    repo = repo or os.environ.get("LOTTO_GH_REPO", DEFAULT_REPO)
    try:
        resp = session.get(
            f"https://api.github.com/repos/{repo}/actions/workflows/{REANALYSIS_WORKFLOW}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            timeout=20,
        )
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok"} if resp.status_code == 200 else {"status": "failed", "http": resp.status_code}


# ---------------------------------------------------------------------------
# 감시기
# ---------------------------------------------------------------------------
class DrawWatcher:
    START_DELAY = timedelta(minutes=5)
    FAST_SECONDS = 45.0
    SLOW_SECONDS = 600.0
    FAST_WINDOW = timedelta(hours=4)
    MAX_IDLE_SLEEP = 300.0
    STATS_RETRY_SECONDS = 300.0
    STATS_RETRY_WINDOW = timedelta(hours=6)
    # [2026-09-27] 매시 발행(bulk-predict)도 예약이 밀리고 버려져 회차당 발행이 400~800장에서 약 200장으로
    # 줄었다(8/6 실측: 하루 48회 요구 중 13.8회만 실행). HF 서버가 1시간마다 직접 호출해 발행량을 되살린다.
    BULK_INTERVAL = timedelta(hours=1)

    def __init__(self, db_path: Optional[str] = None, probe: Optional[Callable] = None,
                 process: Optional[Callable] = None, clock: Optional[Callable] = None,
                 bulk_dispatch: Optional[Callable] = None, access_check: Optional[Callable] = None):
        self.db_path = db_path or DEFAULT_LOTTO_DB
        self._probe = probe or default_probe
        self._process = process or self._process_new_round
        self._clock = clock or now_kst
        self._bulk_dispatch = bulk_dispatch or (lambda since: dispatch_workflow(BULK_WORKFLOW, since))
        self._access_check = access_check or check_dispatch_access
        self._bulk_enabled = os.environ.get("LOTTO_BULK_DISPATCH", "1").strip() != "0"
        self._next_bulk_at = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._errors = 0
        self._stats_pending = None  # (round, 처음 실패 시각, 마지막 시도 시각)
        self._state = {
            "enabled": True,
            "phase": "starting",
            "checks": 0,
            "token_configured": bool(os.environ.get("GH_DISPATCH_TOKEN", "").strip()),
        }

    # ---- 상태 ----
    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def status(self) -> Dict:
        with self._lock:
            return dict(self._state)

    # ---- 한 번의 판단 (테스트 가능하도록 분리) ----
    def step(self) -> float:
        """한 번 확인하고 다음 확인까지 기다릴 초를 돌려준다."""
        now = self._clock()
        last_round, last_date = latest_round_info(self.db_path)
        if last_round is None or not last_date:
            self._set(phase="error", last_error="DB의 마지막 회차 또는 추첨일을 읽지 못했습니다")
            return self.MAX_IDLE_SLEEP
        target = last_round + 1
        draw_time = draw_at(target, last_round, last_date)
        start = draw_time + self.START_DELAY
        self._set(last_round=last_round, target_round=target,
                  draw_at=draw_time.isoformat(timespec="minutes"), poll_start_at=start.isoformat(timespec="minutes"))
        self._retry_statistics(now)
        self._maybe_dispatch_bulk(now, target)
        if now < start:
            self._set(phase="waiting")
            return max(1.0, min((start - now).total_seconds(), self.MAX_IDLE_SLEEP))

        with self._lock:
            self._state["checks"] = self._state.get("checks", 0) + 1
            self._state["last_check"] = now.isoformat(timespec="seconds")
        try:
            item = self._probe(target)
        except Exception as exc:  # 일시 장애는 계속 재시도하되 상태와 로그로 드러낸다
            self._errors += 1
            if self._errors == 1 or self._errors % 10 == 0:
                log.warning("[추첨 감시] %s회 조회 실패 %s회째: %s: %s", target, self._errors, type(exc).__name__, exc)
            self._set(phase="polling", consecutive_errors=self._errors, last_error=f"{type(exc).__name__}: {exc}")
            return self.FAST_SECONDS
        self._errors = 0
        if item is None:
            self._set(phase="polling", consecutive_errors=0)
            return self.FAST_SECONDS if now - draw_time < self.FAST_WINDOW else self.SLOW_SECONDS

        self._set(phase="processing", detected_round=target, detected_at=now.isoformat(timespec="seconds"))
        log.info("[추첨 감시] %s회 당첨번호 게시 확인 (%s)", target, now.strftime("%m-%d %H:%M:%S"))
        result = self._process(target, item, draw_time)
        if result.get("error"):
            # 응답 검증·저장이 실패하면 짧은 간격으로 조르지 않고 평소 간격으로 다시 확인한다
            self._set(phase="error", last_result=result, last_error=result["error"])
            return self.FAST_SECONDS
        self._set(phase="done", last_result=result, last_error=None)
        return 5.0

    def _maybe_dispatch_bulk(self, now: datetime, target: int) -> None:
        """1시간마다 매시 발행 작업을 호출한다. 판매 마감~새 당첨번호 반영 사이에는 부르지 않는다."""
        if not self._bulk_enabled or not self.status().get("token_configured"):
            return
        if self._next_bulk_at is not None and now < self._next_bulk_at:
            return
        self._next_bulk_at = now + self.BULK_INTERVAL
        closed, _ = sales_closed_for(target, self.db_path, now=now)
        stamp = now.isoformat(timespec="minutes")
        if closed:
            self._set(bulk_last={"status": "skipped_sales_closed", "at": stamp})
            return
        result = self._bulk_dispatch(now - self.BULK_INTERVAL)
        with self._lock:
            self._state["bulk_last"] = {**result, "at": stamp}
            if result.get("status") == "dispatched":
                self._state["bulk_dispatched"] = self._state.get("bulk_dispatched", 0) + 1

    def _retry_statistics(self, now: datetime) -> None:
        if not self._stats_pending:
            return
        round_num, first_fail, last_try = self._stats_pending
        if now - first_fail > self.STATS_RETRY_WINDOW:
            self._stats_pending = None
            self._set(stats_pending=None)
            return
        if (now - last_try).total_seconds() < self.STATS_RETRY_SECONDS:
            return
        from src.scripts.poll_and_fetch_result import ensure_statistics

        ok = ensure_statistics(round_num)
        self._stats_pending = None if ok else (round_num, first_fail, now)
        self._set(stats_pending=None if ok else round_num)

    # ---- 게시 확인 뒤 처리 ----
    def _process_new_round(self, target: int, item: Dict, draw_time: datetime) -> Dict:
        from src.automation.weekly_report import (
            inclusion_summary,
            log_cumulative,
            record_pool_inclusion,
            run_weekly_report,
        )
        from src.core.db_manager import DatabaseManager
        from src.data_collector import DataCollector
        from src.scripts.poll_and_fetch_result import ensure_statistics

        out = {"round": target}
        try:
            draw = parse_draw_item(item, target)
        except ValueError as exc:
            log.error("[추첨 감시] %s회 응답 검증 실패: %s", target, exc)
            return {**out, "error": f"응답 검증 실패: {exc}"}
        if not draw["draw_date"]:
            draw["draw_date"] = str(draw_time.date())
        db = DatabaseManager()
        collector = DataCollector(db_manager=db, lotto_numbers_db=db.lotto_db)
        if not db.insert_lotto_numbers_with_bonus(target, draw["numbers"], draw["bonus"], draw["draw_date"]):
            return {**out, "error": "DB 저장 실패"}
        stats = collector._parse_statistics_from_api(item)  # 같은 응답에 등수별 당첨자 수가 함께 온다
        if stats:
            db.lotto_db.insert_statistics(target, stats)
        out["saved"] = draw
        log.info("[추첨 감시] %s회 저장: %s + 보너스 %s", target, draw["numbers"], draw["bonus"])

        out["dispatch"] = dispatch_reanalysis(draw, draw_time)
        log.info("[추첨 감시] GitHub 재분석 호출: %s", out["dispatch"].get("status"))

        stats_ok = ensure_statistics(target)
        out["stats"] = stats_ok
        if not stats_ok:
            now = self._clock()
            self._stats_pending = (target, now, now)
            self._set(stats_pending=target)

        try:
            report = run_weekly_report(db, check_pool=False)
            out["report"] = [r["summary"] for r in report.get("rounds", [])]
        except Exception as exc:  # 대조 실패가 풀 확인을 막지 않되, 숨기지 않는다
            out["report_error"] = f"{type(exc).__name__}: {exc}"
            log.error("[이번 주 결과 보고] %s회 대조 실패: %s", target, out["report_error"])
        try:
            inclusion = record_pool_inclusion(db, target)
            out["inclusion"] = {k: inclusion[k] for k in ("in_pool", "pool_size", "pool_fraction")}
            log.info("[이번 주 결과 보고] %s회 1등 조합이 우리 추천 풀(%s개)에: %s", target,
                     f"{inclusion['pool_size']:,}", "들어 있었음" if inclusion["in_pool"] else "없었음")
            log_cumulative(log, inclusion_summary())
        except Exception as exc:  # 풀 확인 실패가 결과 반영을 막지 않되, 숨기지 않는다
            out["inclusion_error"] = f"{type(exc).__name__}: {exc}"
            log.warning("[이번 주 결과 보고] %s회 풀 포함 확인 실패: %s", target, out["inclusion_error"])
        return out

    def self_check(self) -> None:
        """켜질 때 한 번: 동행복권 접속(이미 발표된 최신 회차 조회)과 GitHub 토큰(읽기 전용)을 확인한다."""
        now = self._clock().isoformat(timespec="seconds")
        last_round, _ = latest_round_info(self.db_path)
        if last_round:
            try:
                item = self._probe(last_round)
                self._set(dhlottery_reachable=item is not None, dhlottery_checked_at=now, dhlottery_error=None)
            except Exception as exc:
                self._set(dhlottery_reachable=False, dhlottery_checked_at=now,
                          dhlottery_error=f"{type(exc).__name__}: {exc}")
        access = self._access_check()
        self._set(github_dispatch=access.get("status"), github_dispatch_http=access.get("http"))
        log.info("[추첨 감시] 자가 점검: 동행복권 %s / GitHub 호출 %s",
                 "접속됨" if self.status().get("dhlottery_reachable") else "접속 안 됨", access.get("status"))

    # ---- 스레드 ----
    def run(self) -> None:
        log.info("[추첨 감시] 시작 (토큰 %s)", "있음" if self.status().get("token_configured") else "없음")
        try:
            self.self_check()
        except Exception as exc:  # 점검 실패가 감시를 막지 않는다
            self._set(self_check_error=f"{type(exc).__name__}: {exc}")
        while not self._stop.is_set():
            try:
                delay = self.step()
            except Exception as exc:  # 감시가 죽지 않게 하되, 오류는 상태와 로그로 남긴다
                log.error("[추첨 감시] 처리 오류: %s: %s", type(exc).__name__, exc)
                self._set(phase="error", last_error=f"{type(exc).__name__}: {exc}")
                delay = 60.0
            self._stop.wait(delay)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, name="draw-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_WATCHER: Optional[DrawWatcher] = None


def watch_enabled() -> bool:
    flag = os.environ.get("LOTTO_DRAW_WATCH", "").strip()
    if flag == "0":
        return False
    return flag == "1" or bool(os.environ.get("SPACE_ID"))


def start_draw_watcher_if_enabled() -> Optional[DrawWatcher]:
    global _WATCHER
    if not watch_enabled():
        return None
    if _WATCHER is None:
        _WATCHER = DrawWatcher()
        _WATCHER.start()
    return _WATCHER


def watcher_status() -> Dict:
    if _WATCHER is None:
        return {"enabled": False}
    return _WATCHER.status()


__all__ = [
    "DrawWatcher",
    "check_dispatch_access",
    "dispatch_reanalysis",
    "dispatch_workflow",
    "parse_draw_item",
    "round_day",
    "start_draw_watcher_if_enabled",
    "watch_enabled",
    "watcher_status",
]
