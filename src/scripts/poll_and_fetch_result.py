# -*- coding: utf-8 -*-
"""
추첨 직후 당첨번호를 '게시되는 즉시' 수집하는 폴링 스크립트.

[왜 폴링인가 - 2026-08-05 실측 근거]
GitHub Actions의 schedule(cron)은 이 저장소에서 정시에 발사된 적이 674회 중 0회이며,
지연 중앙값 99분(최소 51.9분, 최대 218분)이다. 즉 "몇 시에 실행하라"고 예약해도 그 시각에
켜지지 않는다. 반면 동행복권 게시는 추첨(토 20:35) 후 약 11분(1227회 실측 10분 50초)이면 끝난다.

그래서 발사 시각을 통제하는 대신 **일찍 켜서 게시될 때까지 기다린다**.
 - 미게시 응답은 59바이트/0.06초로 매우 가벼워 45초 간격 폴링의 부하가 사실상 없다.
 - 게시되는 순간 감지 -> 즉시 DB 저장 -> 워크플로우가 커밋/화면반영.
 - 기존(주간 예측에만 의존): 추첨 -> GitHub 반영 145분
   개선(이 스크립트): 게시 감지 즉시 -> 약 1~2분

[종료 코드 / 출력]
 - 항상 exit 0 으로 끝나고, 결과는 GITHUB_OUTPUT 의 updated=true|false 로 알린다.
   (미게시는 '실패'가 아니라 정상적인 '아직 아님'이므로 워크플로우를 빨갛게 만들지 않는다)
 - 단, 네트워크/DB 등 진짜 오류는 exit 1 로 드러낸다. 조용히 성공으로 위장하지 않는다.

사용:
  python src/scripts/poll_and_fetch_result.py [--max-wait 175] [--interval 45] [--once]
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('MPLBACKEND', 'Agg')

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('poll_result')

API_URL = 'https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.dhlottery.co.kr/lt645/result',
}


def _emit(key: str, value: str) -> None:
    """GitHub Actions 스텝 출력에 기록(로컬 실행 시에는 stdout에만 남는다)."""
    print(f"[출력] {key}={value}")
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(f"{key}={value}\n")
        except OSError as e:
            log.warning(f"GITHUB_OUTPUT 기록 실패({e}) - 무시하고 계속")


def _summary(text: str) -> None:
    """잡 요약(Actions 화면 상단)에 기록. 게시 시각 실측 누적용."""
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not path:
        return
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text + '\n')
    except OSError:
        pass


def probe(round_num: int, timeout: int = 15):
    """해당 회차가 게시됐는지 단건 조회. 게시 전이면 None.

    전체 조회(srchLtEpsd=all)는 745KB를 받아오므로 폴링에 부적합하다. 단건은 약 677바이트.
    """
    import requests

    resp = requests.get(f'{API_URL}?srchLtEpsd={round_num}', headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    lst = (resp.json().get('data') or {}).get('list') or []
    if not lst:
        return None
    item = lst[0]
    nums = [item.get(f'tm{i}WnNo') for i in range(1, 7)]
    if any(n is None for n in nums) or item.get('bnsWnNo') is None:
        return None
    return item


def ensure_statistics(round_num: int) -> bool:
    """해당 회차의 공식 통계(총 판매량 + 등수별 당첨자 수)가 저장됐는지 확인하고, 비었으면 채운다.

    [왜 필요한가 - 2026-08-08]
    화면 성적표는 '우리 성적'과 '전국 구매자 성적'을 같은 단위로 비교한다. 후자는 이 통계에서
    나오므로, 통계가 없으면 그 회차는 성적표에서 통째로 빠진다(1236회가 실제로 그랬다).
    수집이 조용히 반쪽만 성공하는 일을 막기 위해 저장 결과를 눈으로 확인하고, 비면 복구한다.

    통계가 당첨번호보다 늦게 게시되는 경우도 있으므로, 실패해도 워크플로우를 죽이지 않고
    경고만 남긴다(주간 예측 실행이 같은 복구를 한 번 더 시도한다).
    """
    import sqlite3

    from src.scripts.backfill_winning_statistics import DB as STATS_DB, fetch_all_stats

    def saved() -> bool:
        with sqlite3.connect(STATS_DB) as conn:
            row = conn.execute(
                "SELECT total_sales FROM lotto_statistics WHERE round = ?", (round_num,)
            ).fetchone()
        return bool(row and row[0])

    if saved():
        log.info(f"{round_num}회 공식 통계 저장 확인 (성적표 반영 가능)")
        return True

    log.warning(f"{round_num}회 공식 통계가 비어 있습니다 - 즉시 재수집합니다")
    try:
        stats = fetch_all_stats().get(round_num)
        if not stats or not stats.get('total_sales'):
            log.warning(f"{round_num}회 통계가 아직 게시되지 않았습니다 - 주간 실행에서 재시도")
            return False
        from src.core.specialized_databases import LottoNumbersDB
        LottoNumbersDB(STATS_DB).insert_statistics(round_num, stats)
    except Exception as e:
        log.warning(f"{round_num}회 통계 재수집 실패({type(e).__name__}: {e}) - 주간 실행에서 재시도")
        return False

    if saved():
        log.info(f"{round_num}회 공식 통계 복구 완료")
        return True
    log.warning(f"{round_num}회 공식 통계 저장이 확인되지 않습니다 - 주간 실행에서 재시도")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-wait', type=int, default=175, help='최대 대기(분). 이 시간까지 기다렸다 미게시면 종료')
    ap.add_argument('--interval', type=int, default=45, help='폴링 간격(초)')
    ap.add_argument('--once', action='store_true', help='한 번만 확인하고 종료(리허설/테스트용)')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager

    db = DatabaseManager()
    last_saved = db.get_last_round()
    if not last_saved:
        log.error("DB에서 마지막 회차를 읽지 못했습니다. DB 상태를 확인하세요.")
        return 1
    target = int(last_saved) + 1
    log.info(f"DB 최종 회차 {last_saved} -> {target}회 게시를 기다립니다 "
             f"(간격 {args.interval}초, 최대 {args.max_wait}분)")

    deadline = time.monotonic() + args.max_wait * 60
    attempts = 0
    consecutive_errors = 0
    started = time.monotonic()

    while True:
        attempts += 1
        try:
            item = probe(target)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            log.warning(f"{attempts}번째 조회 실패({type(e).__name__}: {e}) - 연속 {consecutive_errors}회")
            # 네트워크 일시 장애와 지속 장애를 구분한다. 지속되면 진짜 오류로 드러낸다.
            if consecutive_errors >= 10:
                log.error("조회가 10회 연속 실패했습니다. 네트워크 또는 API 변경을 의심하세요.")
                _emit('updated', 'false')
                _emit('error', 'api_unreachable')
                return 1
            item = None

        if item is not None:
            waited = (time.monotonic() - started) / 60
            log.info(f"{target}회 게시 감지! (대기 {waited:.1f}분, {attempts}번째 조회)")
            break

        if args.once:
            log.info(f"{target}회 아직 미게시 - --once 모드이므로 종료")
            _emit('updated', 'false')
            _emit('reason', 'not_published_yet')
            return 0

        if time.monotonic() >= deadline:
            log.info(f"{args.max_wait}분 동안 {target}회가 게시되지 않았습니다. 다음 예약에서 재시도합니다.")
            _emit('updated', 'false')
            _emit('reason', 'timeout')
            _summary(f"- {target}회: {args.max_wait}분 대기했으나 미게시 (조회 {attempts}회)")
            return 0

        time.sleep(args.interval)

    # 게시 확인됨 -> 실제 수집(밀린 회차가 여러 개일 수 있으므로 전체 동기화 경로를 쓴다)
    from src.data_collector import DataCollector

    # lotto_numbers_db 를 넘겨야 1~5등 당첨자수/판매액 통계도 함께 저장된다.
    # 이 통계가 없으면 화면 성적표에서 그 회차가 통째로 빠진다(비교 상대가 없어서).
    #
    # [2026-08-08 버그 수정] 여기서 LottoNumbersDB() 를 인자 없이 만들다가
    # TypeError(db_path 필수)로 실패했고, except 가 그걸 삼켜 "당첨번호만 수집"으로 넘어갔다.
    # 그 결과 1236회 통계가 비었고 성적표가 1235회에서 멈춰 보였다.
    # DatabaseManager 가 이미 올바른 경로로 만들어 둔 인스턴스를 그대로 쓴다(경로 중복 정의 제거).
    collector = DataCollector(db_manager=db, lotto_numbers_db=db.lotto_db)

    collector.fetch_lotto_data()

    after = db.get_last_round()
    if not after or int(after) < target:
        log.error(f"게시는 확인됐는데 DB 저장이 안 됐습니다 (DB 최종 {after}, 기대 {target}). "
                  f"저장 경로를 확인하세요.")
        _emit('updated', 'false')
        _emit('error', 'save_failed')
        return 1

    # 당첨번호만 들어가고 통계가 빠지면 성적표에서 이 회차가 사라진다. 여기서 확인/복구한다.
    stats_ok = ensure_statistics(int(after))

    nums = db.get_numbers_with_bonus()
    latest = [row for row in nums if int(row[0]) == int(after)]
    detail = ''
    if latest:
        n = latest[0][1]
        detail = f" 당첨번호 {list(n[:6])} + 보너스 {n[6]}"
    log.info(f"수집 완료: DB 최종 회차 {after}.{detail}")

    _emit('updated', 'true')
    _emit('round', str(after))
    _emit('stats', 'true' if stats_ok else 'false')
    waited_min = (time.monotonic() - started) / 60
    _summary(f"- {after}회 수집 완료 (대기 {waited_min:.1f}분 / 조회 {attempts}회).{detail}")
    _summary(f"- 공식 통계(성적표 비교용): {'저장됨' if stats_ok else '미저장 - 주간 실행에서 재시도'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
