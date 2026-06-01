"""
극단 패턴 데이터 발굴 (1226회 전수 분석) - 사용자 전략: 역사적으로 거의 안 나온 패턴을 찾아 제거

사용자 핵심 아이디어(2026-06-01): "무작위 말고 데이터 기반. 예) 같은 번호가 연속으로 최대
몇 회 나왔는지 1226회 분석 -> '4회 이상 연속 없다'면 직전 3회 연속 번호는 빼고 추첨."
=> 16개 필터가 못 잡는 새 극단 규칙을 데이터로 발굴. 신중하게(성급한 규칙화 금지, 사실 먼저).

분석 항목:
  A. 번호별 연속 출현(consecutive rounds): 같은 번호가 연달아 최대 몇 회 나왔나
  B. 직전 회차 재등장: 지난 회차 6번호 중 이번에 몇 개 다시 나왔나 (0~6 분포)
  C. 직전 2/3회 누적 재등장
  D. 장기 미출현(cold gap): 한 번호가 최대 몇 회 연속 안 나왔나
  E. 보너스 번호: 연속 동일 / 다음회차 본번호 등장 / 빈도 분포 / 본번호 재출현
  F. 날짜: 월별 번호 경향 (표본 적어 참고)

출력: 핵심 통계 콘솔(ASCII) + results/extreme_patterns.json (한글 콘솔 깨짐 대비)

사용법: python src/scripts/analyze_extreme_patterns.py
"""
import os
import sys
import json
from collections import Counter, defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np


def main():
    from src.core.db_manager import DatabaseManager
    db = DatabaseManager()

    # 회차 -> 본번호6 set, 보너스, 날짜
    main_by_round = {}
    bonus_by_round = {}
    for r, tup in db.get_numbers_with_bonus():
        main_by_round[r] = sorted(int(x) for x in tup[:6])
        bonus_by_round[r] = int(tup[6])
    date_by_round = {}
    for r, s, d in db.get_all_numbers():
        date_by_round[r] = d

    rounds = sorted(main_by_round.keys())
    n_rounds = len(rounds)
    idx_of = {r: i for i, r in enumerate(rounds)}
    print("=" * 92)
    print(f"극단 패턴 데이터 발굴  |  분석 회차 {rounds[0]}~{rounds[-1]} (총 {n_rounds}회)")
    print("=" * 92)

    result = {'meta': {'first': rounds[0], 'last': rounds[-1], 'count': n_rounds}}

    # ---------------------------------------------------------------
    # A. 번호별 연속 출현 (연속된 회차에 연달아)
    # ---------------------------------------------------------------
    appear_idx = {n: [] for n in range(1, 46)}
    for i, r in enumerate(rounds):
        for n in main_by_round[r]:
            appear_idx[n].append(i)

    max_streak = {}
    streak_event_counts = Counter()  # k회 연속이 몇 번 발생
    for n, idxs in appear_idx.items():
        best = cur = 0
        prev = None
        run_lengths = []
        for i in idxs:
            if prev is not None and i == prev + 1:
                cur += 1
            else:
                if cur > 0:
                    run_lengths.append(cur)
                cur = 1
            best = max(best, cur)
            prev = i
        if cur > 0:
            run_lengths.append(cur)
        max_streak[n] = best
        for L in run_lengths:
            if L >= 2:
                streak_event_counts[L] += 1

    overall_max_streak = max(max_streak.values())
    streak_dist = dict(sorted(streak_event_counts.items()))
    # 최근 직전 N회 연속 중인 번호(다음 회차 제외 후보) - 최신 회차 기준
    last_i = n_rounds - 1
    currently_on_streak = {}  # streak_len -> [numbers]
    for n, idxs in appear_idx.items():
        # 현재 연속: 최신 회차에 나왔고 직전들도 연속인지 역으로 카운트
        cur = 0
        j = last_i
        idxset = set(idxs)
        while j >= 0 and j in idxset:
            cur += 1
            j -= 1
        if cur >= 1 and last_i in idxset:
            currently_on_streak.setdefault(cur, []).append(n)

    print("\n[A] 번호 연속 출현 (같은 번호가 연달아 몇 회)")
    print(f"  전체 최대 연속: {overall_max_streak}회")
    print(f"  연속 발생 분포(k회연속: 횟수): {streak_dist}")
    print(f"  번호별 최대연속 분포: {dict(sorted(Counter(max_streak.values()).items()))}")
    on3 = currently_on_streak.get(3, [])
    on2 = currently_on_streak.get(2, [])
    print(f"  최신({rounds[-1]})까지 3연속중 번호: {on3} / 2연속중: {on2}")
    result['A_consecutive'] = {
        'overall_max_streak': overall_max_streak,
        'streak_event_counts': streak_dist,
        'max_streak_per_number': {str(k): v for k, v in max_streak.items()},
        'currently_on_streak': {str(k): v for k, v in currently_on_streak.items()},
    }

    # ---------------------------------------------------------------
    # B. 직전 회차 재등장 개수 (0~6)
    # ---------------------------------------------------------------
    reappear = []
    for i in range(1, n_rounds):
        prev = set(main_by_round[rounds[i - 1]])
        cur = set(main_by_round[rounds[i]])
        reappear.append(len(prev & cur))
    reappear = np.array(reappear)
    re_dist = np.bincount(reappear, minlength=7)[:7]
    print("\n[B] 직전 회차 번호 재등장 개수 (지난주 6개 중 이번에 몇 개)")
    print(f"  분포 0~6개: {list(int(x) for x in re_dist)}")
    print(f"  최대 재등장: {int(reappear.max())}개, 평균 {reappear.mean():.2f}개")
    print(f"  4개 이상 재등장 회차 수: {int((reappear >= 4).sum())} / {len(reappear)}")
    result['B_prev_reappear'] = {
        'dist_0_to_6': [int(x) for x in re_dist],
        'max': int(reappear.max()), 'mean': round(float(reappear.mean()), 3),
        'ge4_count': int((reappear >= 4).sum()),
    }

    # ---------------------------------------------------------------
    # C. 직전 2/3회 누적 재등장
    # ---------------------------------------------------------------
    for w in (2, 3):
        cnts = []
        for i in range(w, n_rounds):
            prevu = set()
            for k in range(1, w + 1):
                prevu |= set(main_by_round[rounds[i - k]])
            cur = set(main_by_round[rounds[i]])
            cnts.append(len(prevu & cur))
        cnts = np.array(cnts)
        print(f"\n[C] 직전 {w}회 누적 번호 중 이번 재등장: 평균 {cnts.mean():.2f}, 최대 {int(cnts.max())}, "
              f"분포 {list(int(x) for x in np.bincount(cnts, minlength=7)[:7])}")
        result[f'C_prev{w}_reappear'] = {
            'mean': round(float(cnts.mean()), 3), 'max': int(cnts.max()),
            'dist': [int(x) for x in np.bincount(cnts, minlength=7)[:7]],
        }

    # ---------------------------------------------------------------
    # D. 장기 미출현(cold gap): 한 번호가 최대 몇 회 연속 안 나왔나
    # ---------------------------------------------------------------
    max_gap = {}
    for n, idxs in appear_idx.items():
        gaps = []
        prev = -1
        for i in idxs:
            gaps.append(i - prev - 1)
            prev = i
        gaps.append((n_rounds - 1) - prev)  # 최신까지 미출현
        max_gap[n] = max(gaps) if gaps else 0
    overall_max_gap = max(max_gap.values())
    # 현재 미출현 길이
    cur_cold = {}
    for n, idxs in appear_idx.items():
        last = idxs[-1] if idxs else -1
        cur_cold[n] = (n_rounds - 1) - last
    print("\n[D] 장기 미출현(콜드): 한 번호가 최대 몇 회 연속 안 나왔나")
    print(f"  전체 최대 미출현: {overall_max_gap}회")
    print(f"  현재 가장 오래 미출현 top5: "
          f"{sorted(cur_cold.items(), key=lambda x: -x[1])[:5]}")
    result['D_cold_gap'] = {
        'overall_max_gap': overall_max_gap,
        'max_gap_per_number': {str(k): v for k, v in max_gap.items()},
        'current_cold_top5': sorted(cur_cold.items(), key=lambda x: -x[1])[:5],
    }

    # ---------------------------------------------------------------
    # E. 보너스 번호 패턴
    # ---------------------------------------------------------------
    bonus_vals = [bonus_by_round[r] for r in rounds]
    bonus_freq = np.bincount(np.array(bonus_vals), minlength=46)[1:46]
    # 보너스 연속 동일
    bonus_same_consec = sum(1 for i in range(1, n_rounds)
                            if bonus_by_round[rounds[i]] == bonus_by_round[rounds[i - 1]])
    # 보너스가 다음 회차 본번호로 등장
    bonus_to_next_main = sum(1 for i in range(n_rounds - 1)
                             if bonus_by_round[rounds[i]] in set(main_by_round[rounds[i + 1]]))
    # 보너스가 직전 회차 본번호였나
    bonus_was_prev_main = sum(1 for i in range(1, n_rounds)
                              if bonus_by_round[rounds[i]] in set(main_by_round[rounds[i - 1]]))
    # 보너스가 같은 회차 본번호 합 안에? (정의상 본번호와 다름 - 검증)
    bonus_eq_main_sameround = sum(1 for r in rounds if bonus_by_round[r] in set(main_by_round[r]))
    print("\n[E] 보너스 번호 패턴")
    print(f"  보너스 빈도 최소~최대: {int(bonus_freq.min())}~{int(bonus_freq.max())} "
          f"(균등기대 {n_rounds/45:.1f})")
    print(f"  보너스 연속 동일 횟수: {bonus_same_consec} / {n_rounds-1}")
    print(f"  보너스가 '다음 회차' 본번호로 등장: {bonus_to_next_main} / {n_rounds-1} "
          f"({bonus_to_next_main/(n_rounds-1)*100:.1f}%)")
    print(f"  보너스가 '직전 회차' 본번호였음: {bonus_was_prev_main} / {n_rounds-1}")
    print(f"  보너스==같은회차 본번호(불가해야 정상): {bonus_eq_main_sameround}")
    result['E_bonus'] = {
        'freq_min': int(bonus_freq.min()), 'freq_max': int(bonus_freq.max()),
        'same_consecutive': bonus_same_consec,
        'to_next_main': bonus_to_next_main, 'was_prev_main': bonus_was_prev_main,
        'eq_main_sameround': bonus_eq_main_sameround,
    }

    # ---------------------------------------------------------------
    # F. 날짜(월별) 경향 - 참고용 (표본 적음)
    # ---------------------------------------------------------------
    month_freq = defaultdict(lambda: np.zeros(46, dtype=int))
    month_rounds = Counter()
    for r in rounds:
        d = date_by_round.get(r, '')
        mm = None
        for sep in ('-', '.', '/'):
            parts = d.split(sep)
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                mm = int(parts[1])
                break
        if mm is None:
            continue
        month_rounds[mm] += 1
        for n in main_by_round[r]:
            month_freq[mm][n] += 1
    # 월별 평균 번호값(저/고 경향)
    month_avg = {}
    for mm in sorted(month_freq):
        total = month_freq[mm][1:46].sum()
        if total:
            avg_num = sum(n * month_freq[mm][n] for n in range(1, 46)) / total
            month_avg[mm] = round(float(avg_num), 2)
    print("\n[F] 날짜(월별) 경향 - 참고용")
    print(f"  월별 추첨수: {dict(sorted(month_rounds.items()))}")
    print(f"  월별 평균 당첨번호값(저↔고): {month_avg}")
    result['F_month'] = {'rounds_per_month': dict(sorted(month_rounds.items())),
                         'avg_number_by_month': month_avg}

    print("\n" + "=" * 92)
    outpath = os.path.join(PROJECT_ROOT, 'results', 'extreme_patterns.json')
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: results/extreme_patterns.json")


if __name__ == '__main__':
    main()
