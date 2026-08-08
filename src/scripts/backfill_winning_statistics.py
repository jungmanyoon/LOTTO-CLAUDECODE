# -*- coding: utf-8 -*-
"""
공식 당첨 통계(등수별 당첨자 수 + 총 판매량)를 누락 회차에 대해 채운다.

[왜 필요한가]
"실제로 로또를 산 사람들은 몇 장당 몇 개나 맞았나"를 계산하려면 회차별 총 판매 게임 수와
등수별 당첨자 수가 필요하다. 이 값이 있어야 우리 예측 성적을 '이론값'이 아니라
'실제 구매자들의 실적'과 직접 비교할 수 있다.

[왜 비어 있었나]
 1) main.py가 DataCollector에 lotto_numbers_db를 넘기지 않아 파싱된 통계가 그냥 버려졌다.
 2) 총 판매액을 구 필드명(totSelAmt)에서 읽고 있었는데 현행 API에는 그 필드가 없다.
둘 다 수정했고, 이 스크립트는 그 이전에 누락된 과거 회차를 소급해서 채운다.

기존 fetch_missing_statistics()는 레거시 HTML 페이지를 파싱하는데 그 경로는 이미
동작하지 않으므로(meta[name=description] 제거됨) 새 API를 쓴다.

사용:
  python src/scripts/backfill_winning_statistics.py            # 누락분 전체
  python src/scripts/backfill_winning_statistics.py --limit 5  # 최근 5개만(테스트)
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import logging
import sqlite3

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('backfill_stats')

API = 'https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.dhlottery.co.kr/lt645/result',
}
DB = os.path.join(ROOT, 'data', 'lotto_numbers.db')


def missing_rounds(limit=None):
    with sqlite3.connect(DB) as conn:
        rows = conn.execute("""
            SELECT round FROM lotto_numbers
            WHERE round NOT IN (
                SELECT round FROM lotto_statistics WHERE total_sales > 0
            )
            ORDER BY round DESC
        """).fetchall()
    out = [r[0] for r in rows]
    return out[:limit] if limit else out


def fetch_all_stats():
    """전체 회차를 한 번에 받아 회차별 통계 dict 로 반환(단건 반복보다 훨씬 가볍다)."""
    resp = requests.get(f'{API}?srchLtEpsd=all', headers=HEADERS, timeout=30)
    resp.raise_for_status()
    out = {}
    for item in (resp.json().get('data') or {}).get('list') or []:
        rnd = item.get('ltEpsd')
        if rnd is None:
            continue
        total_sales = item.get('wholEpsdSumNtslAmt') or item.get('totSelAmt') or 0
        out[int(rnd)] = {
            'first_winners': item.get('rnk1WnNope', 0) or 0,
            'first_prize': item.get('rnk1WnAmt', 0) or 0,
            'second_winners': item.get('rnk2WnNope', 0) or 0,
            'second_prize': item.get('rnk2WnAmt', 0) or 0,
            'third_winners': item.get('rnk3WnNope', 0) or 0,
            'third_prize': item.get('rnk3WnAmt', 0) or 0,
            'fourth_winners': item.get('rnk4WnNope', 0) or 0,
            'fourth_prize': item.get('rnk4WnAmt', 0) or 0,
            'fifth_winners': item.get('rnk5WnNope', 0) or 0,
            'fifth_prize': item.get('rnk5WnAmt', 0) or 0,
            'total_sales': int(total_sales),
        }
    return out


def backfill_missing(limit=None, quiet=False) -> int:
    """누락된 회차의 공식 통계를 채우고, 채운 개수를 돌려준다.

    스크립트 실행(main)과 main.py 사이클 양쪽에서 같은 로직을 쓰기 위해 함수로 분리했다.
    (2026-08-08: 수집 경로가 통계를 빠뜨려도 다음 실행이 스스로 복구하도록 자동 호출 추가)

    Args:
        limit: 최근 N개만 처리(None이면 전체)
        quiet: True면 누락이 없을 때 조용히 넘어간다(정기 실행용)
    """
    todo = missing_rounds(limit)
    if not todo:
        if not quiet:
            log.info("채울 통계가 없습니다(모든 회차 보유).")
        return 0
    log.info(f"통계 누락 {len(todo)}개 회차: {todo[:6]}{' ...' if len(todo) > 6 else ''}")

    t0 = time.time()
    stats = fetch_all_stats()
    log.info(f"API 전체 조회 완료: {len(stats)}개 회차 ({time.time()-t0:.1f}초)")

    from src.core.specialized_databases import LottoNumbersDB
    db = LottoNumbersDB(DB)

    ok = skipped = 0
    for rnd in todo:
        s = stats.get(rnd)
        if not s or not s['total_sales']:
            skipped += 1
            continue
        try:
            if db.insert_statistics(rnd, s):
                ok += 1
                games = s['total_sales'] // 1000
                win3 = (s['first_winners'] + s['second_winners'] + s['third_winners']
                        + s['fourth_winners'] + s['fifth_winners'])
                rate = win3 / games * 100 if games else 0
                log.info(f"  {rnd}회: 판매 {games:,}장 / 3개이상 당첨 {win3:,}건 "
                         f"({rate:.3f}% = 100장당 {rate:.2f}개)")
            else:
                skipped += 1
        except Exception as e:
            log.warning(f"  {rnd}회 저장 실패: {e}")
            skipped += 1

    log.info(f"완료: 저장 {ok}개 / 건너뜀 {skipped}개")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()
    backfill_missing(args.limit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
