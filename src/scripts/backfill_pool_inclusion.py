# -*- coding: utf-8 -*-
"""지난 회차의 '1등 조합이 당시 추천 풀에 들었나'를 운영 방식 그대로 다시 계산해 기록한다.

회차 r마다 r-1회까지의 당첨번호로 운영 풀(극단성 풀, 현재 K·가중치 설정)을 800만 전수로 만들고,
r회 1등 조합이 그 안에 있었는지 data/predictions/pool_inclusion.json 에 남긴다.
이미 기록된 회차는 건너뛴다(--force 로 다시 계산).

사용: python src/scripts/backfill_pool_inclusion.py --from 1232 --to 1243
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def main(argv=None) -> int:
    from src.automation.weekly_report import (
        INCLUSION_START_ROUND,
        inclusion_summary,
        load_inclusion,
        pool_inclusion,
        save_inclusion,
    )
    from src.core.db_manager import DatabaseManager

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=INCLUSION_START_ROUND)
    ap.add_argument("--to", dest="end", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    db = DatabaseManager()
    end = args.end or int(db.get_last_round())
    data = load_inclusion()
    for round_num in range(args.start, end + 1):
        if str(round_num) in data["rounds"] and not args.force:
            print(f"{round_num}회: 이미 기록됨 - 건너뜀")
            continue
        started = time.time()
        entry = pool_inclusion(db, round_num)
        data["rounds"][str(round_num)] = entry
        save_inclusion(data)
        print(f"{round_num}회: {'풀 안' if entry['in_pool'] else '풀 밖'} "
              f"(풀 {entry['pool_size']:,}개, {time.time() - started:.0f}초)", flush=True)
    s = inclusion_summary(data)
    print(f"누적: {s['weeks']}주 중 {s['in_pool']}주 풀 안 (무작위였다면 약 {s['expected_if_random']:.1f}주)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
