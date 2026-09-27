# -*- coding: utf-8 -*-
"""추첨 감시 · 이번 주 결과 보고 · 판매 마감 보호 테스트 (2026-09-27).

네트워크와 운영 DB를 쓰지 않는다. 동행복권 조회와 GitHub 호출은 가짜로 바꾼다.
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.automation import draw_clock
from src.automation.draw_clock import KST, draw_at, parse_draw_date, sales_close_at, sales_closed_for
from src.automation.draw_watcher import DrawWatcher, dispatch_reanalysis, parse_draw_item
from src.automation.weekly_report import inclusion_summary, load_inclusion, round_summary, save_inclusion

pytestmark = pytest.mark.unit


def _lotto_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE lotto_numbers (round INTEGER PRIMARY KEY, numbers TEXT, draw_date TEXT, "
                     "created_at TEXT, bonus_number INTEGER)")
        for r, nums, date, bonus in rows:
            conn.execute("INSERT INTO lotto_numbers (round, numbers, draw_date, bonus_number) VALUES (?,?,?,?)",
                         (r, nums, date, bonus))
    return str(path)


ITEM_1243 = {"ltEpsd": 1243, "ltRflYmd": "20260926", "tm1WnNo": 9, "tm2WnNo": 18, "tm3WnNo": 24,
             "tm4WnNo": 38, "tm5WnNo": 43, "tm6WnNo": 44, "bnsWnNo": 35}


# ---------------------------------------------------------------- 시각 계산
def test_parse_draw_date_accepts_common_formats():
    for text in ("2026-09-26", "2026.09.26", "20260926", "2026-09-26 00:00:00"):
        assert str(parse_draw_date(text)) == "2026-09-26"


def test_next_draw_and_sales_close_are_one_week_after_last_draw():
    assert draw_at(1244, 1243, "2026-09-26") == datetime(2026, 10, 3, 20, 35, tzinfo=KST)
    assert sales_close_at(1244, 1243, "2026-09-26") == datetime(2026, 10, 3, 20, 0, tzinfo=KST)


def test_sales_closed_for_uses_db_last_round(tmp_path):
    db = _lotto_db(tmp_path / "l.db", [(1243, "9,18,24,38,43,44", "2026-09-26", 35)])
    before = datetime(2026, 10, 3, 19, 59, tzinfo=KST)
    after = datetime(2026, 10, 3, 20, 0, tzinfo=KST)
    assert sales_closed_for(1244, db, now=before)[0] is False
    assert sales_closed_for(1244, db, now=after)[0] is True
    # DB에 당첨번호가 들어오면 다음 회차는 일주일 뒤라 다시 열린다
    assert sales_closed_for(1243, db, now=datetime(2026, 9, 26, 21, 0, tzinfo=KST))[0] is True


def test_sales_closed_for_never_blocks_when_unknown(tmp_path):
    assert sales_closed_for(10, str(tmp_path / "missing.db")) == (False, None)


# ---------------------------------------------------------------- 응답 검증
def test_parse_draw_item_valid():
    out = parse_draw_item(ITEM_1243, 1243)
    assert out == {"round": 1243, "numbers": [9, 18, 24, 38, 43, 44], "bonus": 35, "draw_date": "2026-09-26"}


@pytest.mark.parametrize("patch, message", [
    ({"ltEpsd": 1242}, "회차"),
    ({"tm6WnNo": 43}, "당첨번호"),
    ({"bnsWnNo": 44}, "보너스"),
    ({"tm1WnNo": None}, "비어"),
    ({"tm1WnNo": 46}, "당첨번호"),
])
def test_parse_draw_item_rejects_bad_responses(patch, message):
    with pytest.raises(ValueError, match=message):
        parse_draw_item({**ITEM_1243, **patch}, 1243)


# ---------------------------------------------------------------- 감시기 판단
class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _watcher(tmp_path, clock, probe, process=None):
    db = _lotto_db(tmp_path / "l.db", [(1243, "9,18,24,38,43,44", "2026-09-26", 35)])
    calls = []

    def _process(target, item, draw_time):
        calls.append((target, item, draw_time))
        return {"round": target}

    watcher = DrawWatcher(db_path=db, probe=probe, process=process or _process, clock=clock,
                          bulk_dispatch=lambda since: {"status": "test"})
    return watcher, calls


def test_watcher_waits_until_five_minutes_after_draw(tmp_path):
    probed = []
    clock = _Clock(datetime(2026, 10, 3, 20, 30, tzinfo=KST))
    watcher, _ = _watcher(tmp_path, clock, lambda r: probed.append(r))
    delay = watcher.step()
    assert probed == [] and watcher.status()["phase"] == "waiting"
    assert 0 < delay <= 300
    assert watcher.status()["target_round"] == 1244


def test_watcher_polls_fast_then_slow(tmp_path):
    clock = _Clock(datetime(2026, 10, 3, 20, 41, tzinfo=KST))
    watcher, _ = _watcher(tmp_path, clock, lambda r: None)
    assert watcher.step() == DrawWatcher.FAST_SECONDS
    assert watcher.status()["phase"] == "polling"
    clock.now = datetime(2026, 10, 4, 1, 0, tzinfo=KST)  # 추첨 뒤 4시간 넘음
    assert watcher.step() == DrawWatcher.SLOW_SECONDS


def test_watcher_keeps_polling_after_errors(tmp_path):
    def broken(_):
        raise ConnectionError("timeout")

    watcher, _ = _watcher(tmp_path, _Clock(datetime(2026, 10, 3, 20, 41, tzinfo=KST)), broken)
    assert watcher.step() == DrawWatcher.FAST_SECONDS
    assert watcher.step() == DrawWatcher.FAST_SECONDS
    status = watcher.status()
    assert status["consecutive_errors"] == 2 and "ConnectionError" in status["last_error"]


def test_watcher_processes_published_round(tmp_path):
    item = {**ITEM_1243, "ltEpsd": 1244}
    watcher, calls = _watcher(tmp_path, _Clock(datetime(2026, 10, 3, 20, 47, tzinfo=KST)), lambda r: item)
    assert watcher.step() == 5.0
    assert calls and calls[0][0] == 1244 and calls[0][2] == datetime(2026, 10, 3, 20, 35, tzinfo=KST)
    assert watcher.status()["phase"] == "done"


def test_watcher_backs_off_when_processing_fails(tmp_path):
    item = {**ITEM_1243, "ltEpsd": 1244}
    watcher, _ = _watcher(tmp_path, _Clock(datetime(2026, 10, 3, 20, 47, tzinfo=KST)), lambda r: item,
                          process=lambda target, it, dt: {"round": target, "error": "응답 검증 실패"})
    assert watcher.step() == DrawWatcher.FAST_SECONDS
    assert watcher.status()["phase"] == "error"


def test_watcher_polls_immediately_when_db_is_behind(tmp_path):
    probed = []
    clock = _Clock(datetime(2026, 10, 20, 9, 0, tzinfo=KST))  # 몇 주 밀린 상태
    watcher, _ = _watcher(tmp_path, clock, lambda r: probed.append(r))
    watcher.step()
    assert probed == [1244]


# ---------------------------------------------------------------- 매시 발행 호출
def _bulk_watcher(tmp_path, clock, monkeypatch, token="t"):
    if token:
        monkeypatch.setenv("GH_DISPATCH_TOKEN", token)
    else:
        monkeypatch.delenv("GH_DISPATCH_TOKEN", raising=False)
    db = _lotto_db(tmp_path / "l.db", [(1243, "9,18,24,38,43,44", "2026-09-26", 35)])
    calls = []

    def fake_bulk(since):
        calls.append(since)
        return {"status": "dispatched"}

    watcher = DrawWatcher(db_path=db, probe=lambda r: None, clock=clock, bulk_dispatch=fake_bulk)
    return watcher, calls


def test_bulk_dispatch_runs_once_per_hour(tmp_path, monkeypatch):
    clock = _Clock(datetime(2026, 9, 28, 10, 0, tzinfo=KST))
    watcher, calls = _bulk_watcher(tmp_path, clock, monkeypatch)
    watcher.step()
    watcher.step()
    assert len(calls) == 1
    clock.now += timedelta(minutes=61)
    watcher.step()
    assert len(calls) == 2 and watcher.status()["bulk_dispatched"] == 2


def test_bulk_dispatch_skips_after_sales_close(tmp_path, monkeypatch):
    clock = _Clock(datetime(2026, 10, 3, 20, 10, tzinfo=KST))  # 1244회 판매 마감 뒤, 당첨번호 반영 전
    watcher, calls = _bulk_watcher(tmp_path, clock, monkeypatch)
    watcher.step()
    assert calls == [] and watcher.status()["bulk_last"]["status"] == "skipped_sales_closed"


def test_bulk_dispatch_needs_token(tmp_path, monkeypatch):
    watcher, calls = _bulk_watcher(tmp_path, _Clock(datetime(2026, 9, 28, 10, 0, tzinfo=KST)), monkeypatch, token="")
    watcher.step()
    assert calls == []


# ---------------------------------------------------------------- GitHub 즉시 호출
class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _Session:
    def __init__(self, runs=None, post_status=204):
        self.runs = runs or []
        self.post_status = post_status
        self.posts = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_headers = headers
        return _Resp(200, {"workflow_runs": self.runs})

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, headers, json))
        return _Resp(self.post_status, text="bad")


DRAW = {"round": 1244, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7, "draw_date": "2026-10-03"}
DRAW_TIME = datetime(2026, 10, 3, 20, 35, tzinfo=KST)


def test_dispatch_without_token_does_nothing(monkeypatch):
    monkeypatch.delenv("GH_DISPATCH_TOKEN", raising=False)
    assert dispatch_reanalysis(DRAW, DRAW_TIME, session=_Session())["status"] == "no_token"


def test_dispatch_sends_numbers_to_weekly_workflow():
    session = _Session()
    out = dispatch_reanalysis(DRAW, DRAW_TIME, token="t", repo="o/r", session=session)
    assert out["status"] == "dispatched"
    url, headers, payload = session.posts[0]
    assert url.endswith("/repos/o/r/actions/workflows/weekly-predict.yml/dispatches")
    assert headers["Authorization"] == "Bearer t"
    assert payload == {"ref": "main", "inputs": {"round": "1244", "numbers": "1,2,3,4,5,6",
                                                 "bonus": "7", "draw_date": "2026-10-03"}}


def test_dispatch_skips_when_a_run_is_already_active():
    session = _Session(runs=[{"id": 9, "status": "in_progress"}])
    out = dispatch_reanalysis(DRAW, DRAW_TIME, token="t", repo="o/r", session=session)
    assert out["status"] == "already_running" and session.posts == []


def test_self_check_reports_reachability_and_token(tmp_path):
    watcher, _ = _watcher(tmp_path, _Clock(datetime(2026, 9, 27, 10, 0, tzinfo=KST)), lambda r: ITEM_1243)
    watcher._access_check = lambda: {"status": "ok"}
    watcher.self_check()
    status = watcher.status()
    assert status["dhlottery_reachable"] is True and status["github_dispatch"] == "ok"

    def broken(_):
        raise ConnectionError("blocked")

    other = tmp_path / "blocked"
    other.mkdir()
    watcher2, _ = _watcher(other, _Clock(datetime(2026, 9, 27, 10, 0, tzinfo=KST)), broken)
    watcher2._access_check = lambda: {"status": "no_token"}
    watcher2.self_check()
    assert watcher2.status()["dhlottery_reachable"] is False
    assert "ConnectionError" in watcher2.status()["dhlottery_error"]


def test_check_dispatch_access_is_read_only():
    from src.automation.draw_watcher import check_dispatch_access

    session = _Session()
    assert check_dispatch_access(token="t", repo="o/r", session=session) == {"status": "ok"}
    assert session.posts == []
    assert check_dispatch_access(token="", repo="o/r", session=session) == {"status": "no_token"}


def test_dispatch_reports_http_failure():
    out = dispatch_reanalysis(DRAW, DRAW_TIME, token="t", repo="o/r", session=_Session(post_status=422))
    assert out["status"] == "failed" and out["http"] == 422


# ---------------------------------------------------------------- 선반영 스크립트
class _FakeDB:
    def __init__(self, last, rows=None):
        self.last = last
        self.rows = rows or {}
        self.inserted = []

    def get_last_round(self):
        return self.last

    def get_numbers_by_round(self, r):
        return (r, self.rows[r], "2026-09-26") if r in self.rows else None

    def insert_lotto_numbers_with_bonus(self, r, numbers, bonus, date):
        self.inserted.append((r, numbers, bonus, date))
        return True


@pytest.fixture
def apply_mod(monkeypatch):
    from src.scripts import apply_dispatched_result as mod
    return mod


def _run_apply(monkeypatch, mod, fake, argv):
    monkeypatch.setattr("src.core.db_manager.DatabaseManager", lambda: fake)
    return mod.main(argv)


def test_apply_inserts_next_round(monkeypatch, apply_mod):
    fake = _FakeDB(1243)
    code = _run_apply(monkeypatch, apply_mod, fake,
                      ["--round", "1244", "--numbers", "6,5,4,3,2,1", "--bonus", "7", "--draw-date", "2026.10.03"])
    assert code == 0 and fake.inserted == [(1244, [1, 2, 3, 4, 5, 6], 7, "2026-10-03")]


ARGS_1244 = ["--round", "1244", "--numbers", "1,2,3,4,5,6", "--bonus", "7"]


def test_apply_checks_existing_round_without_overwriting(monkeypatch, apply_mod):
    same = _FakeDB(1244, {1244: "1,2,3,4,5,6"})
    assert _run_apply(monkeypatch, apply_mod, same, ARGS_1244) == 0
    different = _FakeDB(1244, {1244: "1,2,3,4,5,9"})
    assert _run_apply(monkeypatch, apply_mod, different, ARGS_1244) == 1
    assert same.inserted == [] and different.inserted == []


def test_apply_ignores_gaps_and_empty_input(monkeypatch, apply_mod):
    fake = _FakeDB(1240)
    assert _run_apply(monkeypatch, apply_mod, fake, ARGS_1244) == 0
    assert _run_apply(monkeypatch, apply_mod, fake, ["--round", ""]) == 0
    assert fake.inserted == []


@pytest.mark.parametrize("numbers, bonus", [("1,2,3,4,5", "7"), ("1,1,3,4,5,6", "7"), ("1,2,3,4,5,6", "6")])
def test_apply_rejects_invalid_numbers(monkeypatch, apply_mod, numbers, bonus):
    fake = _FakeDB(1243)
    assert _run_apply(monkeypatch, apply_mod, fake, ["--round", "1244", "--numbers", numbers, "--bonus", bonus]) == 1
    assert fake.inserted == []


# ---------------------------------------------------------------- 결과 보고
def test_inclusion_roundtrip_and_summary(tmp_path):
    path = str(tmp_path / "pool_inclusion.json")
    data = load_inclusion(path)
    data["rounds"]["1242"] = {"in_pool": False, "pool_fraction": 0.184}
    data["rounds"]["1243"] = {"in_pool": True, "pool_fraction": 0.184}
    save_inclusion(data, path)
    summary = inclusion_summary(load_inclusion(path))
    assert summary["weeks"] == 2 and summary["in_pool"] == 1
    assert summary["expected_if_random"] == pytest.approx(0.368)


def test_round_summary_counts_ranks(tmp_path):
    pred = tmp_path / "p.db"
    with sqlite3.connect(pred) as conn:
        conn.execute("CREATE TABLE prediction_results (round INTEGER, match_count INTEGER, bonus_match INTEGER)")
        conn.executemany("INSERT INTO prediction_results VALUES (1243, ?, ?)",
                         [(3, 0), (3, 0), (4, 0), (5, 1), (2, 0), (0, 0)])
    lotto = _lotto_db(tmp_path / "l.db", [(1243, "9,18,24,38,43,44", "2026-09-26", 35)])
    s = round_summary(str(pred), lotto, 1243)
    assert s["tickets"] == 6 and s["hits3"] == 4 and s["best"] == 5
    assert s["ranks"] == {1: 0, 2: 1, 3: 0, 4: 1, 5: 2}
    assert s["winning"] == [9, 18, 24, 38, 43, 44] and s["bonus"] == 35


# ---------------------------------------------------------------- 발행 보호
def test_bulk_predict_skips_after_sales_close(monkeypatch, capsys):
    from src.scripts import bulk_predict_once

    monkeypatch.setattr("src.core.db_manager.DatabaseManager", lambda: _FakeDB(1243))
    close = datetime(2026, 10, 3, 20, 0, tzinfo=KST)
    monkeypatch.setattr("src.automation.draw_clock.sales_closed_for", lambda r, *a, **k: (True, close))

    def must_not_build(*args, **kwargs):
        raise AssertionError("판매 마감 뒤에는 풀을 만들지 않아야 합니다")

    monkeypatch.setattr("src.core.extremeness_pool_predictor.ExtremenessPoolPredictor.build_pool", must_not_build)
    bulk_predict_once.main()
    assert "판매 마감" in capsys.readouterr().out


def test_draw_watch_status_api_reports_next_draw(monkeypatch):
    from src.scripts import enhanced_dashboard_v2 as dash

    monkeypatch.setattr("src.automation.draw_clock.latest_round_info", lambda *a, **k: (1243, "2026-09-26"))
    client = dash.app.test_client()
    data = client.get("/api/draw-watch-status").get_json()
    assert data["target_round"] == 1244 and data["draw_at"].startswith("2026-10-03T20:35")
    assert "token" not in "".join(k for k in data if k != "token_configured")


def test_generate_predictions_refuses_after_sales_close(monkeypatch):
    from src.scripts import enhanced_dashboard_v2 as dash

    close = datetime(2026, 10, 3, 20, 0, tzinfo=KST)
    monkeypatch.setattr("src.automation.draw_clock.sales_closed_for", lambda r, *a, **k: (True, close))
    client = dash.app.test_client()
    dash.app.config["WTF_CSRF_ENABLED"] = False
    resp = client.post("/api/generate-predictions", json={})
    assert resp.status_code in (409, 401, 403)
    if resp.status_code == 409:
        assert "마감" in resp.get_json()["error"]


def test_status_timestamps_are_kst():
    now = draw_clock.now_kst()
    assert now.utcoffset() == timedelta(hours=9)


# ---------------------------------------------------------------- 가벼운 의존성 환경
LIGHT_ENV_PROBE = """
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'schedule', 'watchdog'}:
            raise ModuleNotFoundError('blocked: ' + name)
        return None
sys.meta_path.insert(0, Block())
import src.automation.draw_clock, src.automation.draw_watcher, src.automation.weekly_report
print('auto_scheduler' in ' '.join(sys.modules))
"""


def test_automation_modules_import_without_heavy_packages():
    """매시 발행 작업은 가벼운 패키지만 설치한다. 새 모듈이 schedule/watchdog 없이 불러와져야 한다."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-c", LIGHT_ENV_PROBE], capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr[-800:]
    assert result.stdout.strip() == "False"


def test_package_level_names_still_import_lazily():
    import src.automation as automation

    assert automation.AutomationCoordinator.__name__ == "AutomationCoordinator"
    assert "AutoScheduler" in dir(automation)
    with pytest.raises(AttributeError):
        automation.NotAThing  # noqa: B018
