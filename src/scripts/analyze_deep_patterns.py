"""
심층 극단 패턴 발굴 (1226회 전수) - 다각도 통계: 조합론/위치/간격/끝자리/구간/마르코프/시계열

사용자 지시(2026-06-01): "데이터분석가/암호해독가/패턴분석가/AI학습 관점으로 더 신중히 깊게.
내가 말한 것 + 기존 것 외에 더 중요한 패턴을 찾아라."

목표: 16필터/극단성점수/mean_reversion이 못 잡는 새 극단 경계를 데이터로 발굴.
각 패턴마다 (1) 역사적 경계(절대/거의 안 나온 값) (2) 제거 효과 추정 (3) 당첨 위험(역사적 위반 수)을
함께 기록. 신중: 다중비교 함정 주의 - 발견은 "후보"일 뿐, 2단계(전문가 적대검증)에서 확정.

분석 렌즈:
  P1 쌍 동시출현(조합론): C(45,2) 함께 나온 빈도. 절대 함께 안 나온 쌍, 최다 쌍, 기대 대비 편차.
  P2 삼중 동시출현: 관측된 삼중 수, 최다 삼중.
  P3 위치별 분포: 정렬 6개의 1st~6th 값 역사적 min/max/분위 -> "최소번호 상한/최대번호 하한" 경계.
  P4 간격(gap): 인접 차이, 최대간격 분포 -> 역사적 최대간격 상한.
  P5 끝자리: 같은 끝자리 최대 개수 분포.
  P6 구간(decade 5분할): 점유 분포, 빈 구간 수 분포 -> 한 구간 몰림/공백 극단.
  P7 합/홀짝/저고/AC: 역사적 min~max 경계.
  P8 마르코프 전이: 직전 회차 출현번호의 다음 회차 재출현률 vs 미출현번호 출현률(carryover 효과).
  P9 첫·끝수 동시: (min,max) 조합 극단.

출력: results/deep_patterns.json + 콘솔 ASCII 요약.
사용법: python src/scripts/analyze_deep_patterns.py
"""
import os
import sys
import json
from itertools import combinations
from collections import Counter, defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np

TOTAL = 8_145_060


def main():
    from src.core.db_manager import DatabaseManager
    db = DatabaseManager()

    main_by_round = {}
    for r, tup in db.get_numbers_with_bonus():
        main_by_round[r] = sorted(int(x) for x in tup[:6])
    rounds = sorted(main_by_round)
    draws = [main_by_round[r] for r in rounds]
    n = len(draws)
    arr = np.array(draws, dtype=np.int16)  # (n,6) 정렬됨

    print("=" * 92)
    print(f"심층 극단 패턴 발굴  |  {rounds[0]}~{rounds[-1]}회 (총 {n}회)")
    print("=" * 92)
    R = {'meta': {'first': rounds[0], 'last': rounds[-1], 'count': n}}

    # ============================================================
    # P1. 쌍 동시출현 (조합론)
    # ============================================================
    pair = np.zeros((46, 46), dtype=np.int32)
    for ns in draws:
        for a, b in combinations(ns, 2):
            pair[a][b] += 1
    pair_counts = [pair[a][b] for a, b in combinations(range(1, 46), 2)]
    pair_counts = np.array(pair_counts)
    total_pairs = len(pair_counts)  # 990
    expected = n * 15 / total_pairs  # 회차당 15쌍
    never_pairs = [(a, b) for a, b in combinations(range(1, 46), 2) if pair[a][b] == 0]
    # 최다/최소 쌍
    pair_list = sorted(((pair[a][b], a, b) for a, b in combinations(range(1, 46), 2)), reverse=True)
    top_pairs = [(int(c), a, b) for c, a, b in pair_list[:8]]
    bot_pairs = [(int(c), a, b) for c, a, b in pair_list[-8:]]
    print("\n[P1] 쌍 동시출현 (조합론)")
    print(f"  쌍 990개, 기대 동시출현 {expected:.1f}회, 실제 최소~최대 {int(pair_counts.min())}~{int(pair_counts.max())}")
    print(f"  한 번도 함께 안 나온 쌍: {len(never_pairs)}개")
    print(f"  최다 동시출현 top3: {top_pairs[:3]}")
    print(f"  최소 동시출현 bot3: {bot_pairs[:3]}")
    R['P1_pairs'] = {
        'expected': round(expected, 1), 'min': int(pair_counts.min()), 'max': int(pair_counts.max()),
        'never_together_count': len(never_pairs), 'never_pairs_sample': never_pairs[:20],
        'top_pairs': top_pairs, 'bottom_pairs': bot_pairs,
        'mean': round(float(pair_counts.mean()), 2), 'std': round(float(pair_counts.std()), 2),
    }

    # ============================================================
    # P2. 삼중 동시출현
    # ============================================================
    triple_cnt = Counter()
    for ns in draws:
        for t in combinations(ns, 3):
            triple_cnt[t] += 1
    total_triples_possible = 14190  # C(45,3)
    observed_triples = len(triple_cnt)
    top_triples = [(int(c), list(t)) for t, c in triple_cnt.most_common(5)]
    repeat_triples = sum(1 for c in triple_cnt.values() if c >= 2)
    print("\n[P2] 삼중 동시출현")
    print(f"  가능 삼중 {total_triples_possible}, 관측된 삼중 {observed_triples}개 "
          f"({observed_triples/total_triples_possible*100:.1f}%)")
    print(f"  2회 이상 반복된 삼중: {repeat_triples}개, 최다 top3: {top_triples[:3]}")
    R['P2_triples'] = {
        'possible': total_triples_possible, 'observed': observed_triples,
        'repeated_2plus': repeat_triples, 'top_triples': top_triples,
    }

    # ============================================================
    # P3. 위치별 분포 (정렬 1st~6th)
    # ============================================================
    print("\n[P3] 위치별 분포 (정렬 후 위치별 번호 경계)")
    pos_stats = {}
    for pos in range(6):
        col = arr[:, pos]
        pos_stats[pos + 1] = {
            'min': int(col.min()), 'max': int(col.max()),
            'mean': round(float(col.mean()), 2),
            'p1': int(np.percentile(col, 1)), 'p99': int(np.percentile(col, 99)),
        }
        print(f"  {pos+1}번째 수: 범위 {int(col.min())}~{int(col.max())}, 평균 {col.mean():.1f}, "
              f"1%~99% [{int(np.percentile(col,1))}~{int(np.percentile(col,99))}]")
    R['P3_position'] = pos_stats
    # 핵심 경계: 최소수(1st)의 최대값, 최대수(6th)의 최소값
    R['P3_position']['min_number_ceiling'] = int(arr[:, 0].max())   # 1st가 넘은 적 없는 상한
    R['P3_position']['max_number_floor'] = int(arr[:, 5].min())     # 6th가 내려간 적 없는 하한
    print(f"  >> 최소수(1st)가 넘은 적 없는 상한: {int(arr[:,0].max())} "
          f"(즉 6개 모두 {int(arr[:,0].max())+1}+ 인 조합은 역사상 0)")
    print(f"  >> 최대수(6th)가 내려간 적 없는 하한: {int(arr[:,5].min())} "
          f"(즉 6개 모두 {int(arr[:,5].min())-1}- 인 조합은 역사상 0)")

    # ============================================================
    # P4. 간격(gap)
    # ============================================================
    gaps = np.diff(arr, axis=1)  # (n,5)
    max_gaps = gaps.max(axis=1)
    min_gaps = gaps.min(axis=1)
    print("\n[P4] 번호 간격(인접 차이)")
    print(f"  최대간격 범위 {int(max_gaps.min())}~{int(max_gaps.max())}, 평균 {max_gaps.mean():.1f}")
    print(f"  최소간격=1(연속) 비율 {(min_gaps==1).mean()*100:.1f}% (연속쌍 있는 회차)")
    print(f"  최대간격 분포(>=20): {int((max_gaps>=20).sum())}회, >=25: {int((max_gaps>=25).sum())}회")
    R['P4_gaps'] = {
        'max_gap_min': int(max_gaps.min()), 'max_gap_max': int(max_gaps.max()),
        'max_gap_mean': round(float(max_gaps.mean()), 2),
        'has_consecutive_pct': round(float((min_gaps == 1).mean() * 100), 1),
        'max_gap_ge20': int((max_gaps >= 20).sum()), 'max_gap_ge25': int((max_gaps >= 25).sum()),
        'max_gap_dist': {str(g): int((max_gaps == g).sum()) for g in range(1, int(max_gaps.max()) + 1)},
    }

    # ============================================================
    # P5. 끝자리
    # ============================================================
    last_digit = arr % 10
    same_last_max = []
    for row in last_digit:
        c = Counter(row.tolist())
        same_last_max.append(max(c.values()))
    same_last_max = np.array(same_last_max)
    print("\n[P5] 끝자리 (같은 끝자리 최대 개수)")
    print(f"  같은끝자리 최대개수 분포: {dict(sorted(Counter(same_last_max.tolist()).items()))}")
    R['P5_last_digit'] = {
        'same_last_max_dist': {str(k): int(v) for k, v in sorted(Counter(same_last_max.tolist()).items())},
        'ge4_count': int((same_last_max >= 4).sum()),
    }

    # ============================================================
    # P6. 구간(decade 5분할: 1-9,10-19,20-29,30-39,40-45)
    # ============================================================
    def decade(x):
        return min((x) // 10, 4)
    occ_dist = Counter()       # 한 구간 최대 점유
    empty_dist = Counter()     # 빈 구간 수
    for ns in draws:
        secs = Counter(decade(x) for x in ns)
        occ_dist[max(secs.values())] += 1
        empty_dist[5 - len(secs)] += 1
    print("\n[P6] 구간(10단위 5분할) 점유")
    print(f"  한 구간 최대점유 분포: {dict(sorted(occ_dist.items()))}")
    print(f"  빈 구간 수 분포: {dict(sorted(empty_dist.items()))}")
    R['P6_decade'] = {
        'max_occupancy_dist': {str(k): v for k, v in sorted(occ_dist.items())},
        'empty_sections_dist': {str(k): v for k, v in sorted(empty_dist.items())},
    }

    # ============================================================
    # P7. 합/홀짝/저고/AC 경계
    # ============================================================
    sums = arr.sum(axis=1)
    odd = (arr % 2 == 1).sum(axis=1)
    low = (arr <= 22).sum(axis=1)
    # AC value
    ac_vals = []
    for ns in draws:
        diffs = set()
        for a, b in combinations(ns, 2):
            diffs.add(b - a)
        ac_vals.append(len(diffs) - 5)
    ac_vals = np.array(ac_vals)
    print("\n[P7] 합/홀짝/저고/AC 역사적 경계")
    print(f"  합계: {int(sums.min())}~{int(sums.max())} (평균 {sums.mean():.0f})")
    print(f"  홀수개수: {int(odd.min())}~{int(odd.max())} 분포 {dict(sorted(Counter(odd.tolist()).items()))}")
    print(f"  저번호(<=22): {int(low.min())}~{int(low.max())} 분포 {dict(sorted(Counter(low.tolist()).items()))}")
    print(f"  AC값: {int(ac_vals.min())}~{int(ac_vals.max())} (낮을수록 단조)")
    R['P7_bounds'] = {
        'sum_min': int(sums.min()), 'sum_max': int(sums.max()), 'sum_mean': round(float(sums.mean()), 1),
        'odd_dist': {str(k): int(v) for k, v in sorted(Counter(odd.tolist()).items())},
        'low_dist': {str(k): int(v) for k, v in sorted(Counter(low.tolist()).items())},
        'ac_min': int(ac_vals.min()), 'ac_max': int(ac_vals.max()),
        'ac_dist': {str(k): int(v) for k, v in sorted(Counter(ac_vals.tolist()).items())},
    }

    # ============================================================
    # P8. 마르코프 전이 (직전 회차 출현번호의 다음 재출현률)
    # ============================================================
    # 직전 회차에 '나온' 번호가 다음 회차에 나올 확률 vs '안 나온' 번호
    carry_hit = 0      # 직전 출현 번호가 다음에도 출현
    carry_total = 0    # 직전 출현 번호 수 (=6*(n-1))
    noshow_hit = 0     # 직전 미출현 번호가 다음에 출현
    noshow_total = 0   # 직전 미출현 번호 수 (=39*(n-1))
    for i in range(1, n):
        prev = set(draws[i - 1])
        cur = set(draws[i])
        for num in range(1, 46):
            if num in prev:
                carry_total += 1
                if num in cur:
                    carry_hit += 1
            else:
                noshow_total += 1
                if num in cur:
                    noshow_hit += 1
    carry_rate = carry_hit / carry_total
    noshow_rate = noshow_hit / noshow_total
    base_rate = 6 / 45
    print("\n[P8] 마르코프 전이 (직전 출현이 다음에 영향 주나)")
    print(f"  직전 '출현' 번호의 다음 재출현률: {carry_rate*100:.2f}% (기대 {base_rate*100:.2f}%)")
    print(f"  직전 '미출현' 번호의 다음 출현률: {noshow_rate*100:.2f}%")
    print(f"  => carryover {'우위' if carry_rate>noshow_rate else '열위/무관'} "
          f"(차이 {(carry_rate-noshow_rate)*100:+.2f}%p)")
    R['P8_markov'] = {
        'carry_rate': round(carry_rate * 100, 3), 'noshow_rate': round(noshow_rate * 100, 3),
        'base_rate': round(base_rate * 100, 3), 'diff_pp': round((carry_rate - noshow_rate) * 100, 3),
    }

    # ============================================================
    # P9. (최소수, 최대수) 극단 동시
    # ============================================================
    print("\n[P9] (최소수,최대수) 범위")
    span = arr[:, 5] - arr[:, 0]
    print(f"  전체범위(최대-최소): {int(span.min())}~{int(span.max())} 평균 {span.mean():.1f}")
    print(f"  범위<=20 (좁게 몰림) 회차: {int((span<=20).sum())} / {n}")
    R['P9_span'] = {
        'min': int(span.min()), 'max': int(span.max()), 'mean': round(float(span.mean()), 1),
        'le20_count': int((span <= 20).sum()), 'le15_count': int((span <= 15).sum()),
    }

    print("\n" + "=" * 92)
    outpath = os.path.join(PROJECT_ROOT, 'results', 'deep_patterns.json')
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: results/deep_patterns.json")


if __name__ == '__main__':
    main()
