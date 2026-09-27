# -*- coding: utf-8 -*-
"""HF 서버 추첨 감시가 넘긴 당첨번호를 GitHub 주간 작업의 DB에 선반영한다.

[왜 필요한가 - 2026-09-27]
GitHub 서버에서 동행복권 접속이 10회 연속 시간 초과로 실패한 날(9/5, 9/12)이 있었다. 이때 주간 작업은
새 회차 없이 돌아, 이미 추첨이 끝난 회차 번호로 예측을 만들 수 있었다. HF 서버는 동행복권 공식 응답을
검증한 뒤 이 작업을 즉시 호출하면서 당첨번호를 함께 넘기므로, 여기서는 그 값을 확인해 넣기만 한다.

규칙
  - DB 다음 회차(마지막 회차 + 1)일 때만 넣는다. 번호 6개는 1~45의 서로 다른 수, 보너스는 그 밖의 수.
  - 이미 있는 회차면 번호가 같은지만 확인한다(다르면 오류로 드러낸다. 덮어쓰지 않는다).
  - 입력이 비어 있으면(예약 실행) 아무것도 하지 않는다. 공식 통계는 이후 수집 단계가 채운다.

사용: python src/scripts/apply_dispatched_result.py --round 1244 --numbers 1,2,3,4,5,6 --bonus 7 --draw-date 2026-10-03
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="")
    ap.add_argument("--numbers", default="")
    ap.add_argument("--bonus", default="")
    ap.add_argument("--draw-date", default="")
    return ap.parse_args(argv)


def validate(round_text, numbers_text, bonus_text, date_text):
    round_num = int(round_text)
    numbers = sorted(int(x) for x in numbers_text.split(",") if x.strip())
    bonus = int(bonus_text)
    if len(numbers) != 6 or len(set(numbers)) != 6 or not all(1 <= n <= 45 for n in numbers):
        raise ValueError(f"당첨번호 형식 이상: {numbers_text}")
    if not 1 <= bonus <= 45 or bonus in numbers:
        raise ValueError(f"보너스 형식 이상: {bonus_text}")
    draw_date = date_text.strip() or None
    if draw_date:
        from src.automation.draw_clock import parse_draw_date

        draw_date = str(parse_draw_date(draw_date))
    return round_num, numbers, bonus, draw_date


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.round.strip():
        print("[선반영] 넘겨받은 당첨번호 없음(예약 실행) - 건너뜀")
        return 0
    try:
        round_num, numbers, bonus, draw_date = validate(args.round, args.numbers, args.bonus, args.draw_date)
    except (ValueError, TypeError) as exc:
        print(f"[선반영] 입력 검증 실패: {exc}")
        return 1

    from src.core.db_manager import DatabaseManager

    db = DatabaseManager()
    last = int(db.get_last_round() or 0)
    if round_num <= last:
        row = db.get_numbers_by_round(round_num)
        saved = sorted(int(x) for x in str(row[1]).split(",")[:6]) if row else None
        if saved != numbers:
            print(f"[선반영] {round_num}회 DB 번호 {saved} 와 넘겨받은 번호 {numbers} 가 다릅니다 - 확인 필요")
            return 1
        print(f"[선반영] {round_num}회는 이미 DB에 있고 번호가 같습니다 - 건너뜀")
        return 0
    if round_num != last + 1:
        print(f"[선반영] DB 마지막 {last}회와 이어지지 않는 {round_num}회라 넣지 않습니다(수집 단계가 동기화)")
        return 0
    if not db.insert_lotto_numbers_with_bonus(round_num, numbers, bonus, draw_date):
        print(f"[선반영] {round_num}회 DB 저장 실패")
        return 1
    print(f"[선반영] {round_num}회 저장: {numbers} + 보너스 {bonus} ({draw_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
