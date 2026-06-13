# -*- coding: utf-8 -*-
"""
로또 당첨번호 시계열 패턴 분석
핵심 질문: 패턴이 시간에 따라 변하는가?
"""

import sqlite3
import numpy as np
from scipy import stats
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

DB_PATH = "data/lotto_numbers.db"

def load_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT round, numbers, draw_date FROM lotto_numbers ORDER BY round")
    rows = cursor.fetchall()
    conn.close()

    rounds, all_numbers, dates, months = [], [], [], []
    for r, nums, d in rows:
        ns = list(map(int, nums.split(',')))
        rounds.append(r)
        all_numbers.append(ns)
        dates.append(d)
        months.append(int(d[5:7]) if d else 0)

    return np.array(rounds), all_numbers, dates, np.array(months)


def sep():
    print("\n" + "="*65)


def analysis1_moving_average_trend(rounds, all_numbers):
    sep()
    print("[분석 1] 번호별 50회 이동평균 출현율 - 추세 분석")
    print("="*65)

    n_rounds = len(rounds)
    appear = np.zeros((45, n_rounds), dtype=float)
    for i, ns in enumerate(all_numbers):
        for n in ns:
            appear[n-1, i] = 1.0

    WINDOW = 50
    RECENT = 200

    trend_slopes = {}
    for num in range(1, 46):
        arr = appear[num-1]
        ma = np.convolve(arr, np.ones(WINDOW)/WINDOW, mode='valid')
        recent_ma = ma[-RECENT:] if len(ma) >= RECENT else ma
        x = np.arange(len(recent_ma))
        slope, intercept, r, p, se = stats.linregress(x, recent_ma)
        overall_rate = arr.mean()
        trend_slopes[num] = (slope, p, recent_ma[-1], overall_rate)

    sorted_asc = sorted(trend_slopes.items(), key=lambda x: x[1][0], reverse=True)

    print("\n[현재 상승 추세 TOP 5] - 최근 200회 이동평균 선형 기울기")
    hdr = "  번호 | 기울기(x1e-4) | p-value | 현재출현율 | 전체평균 | 유의"
    print(hdr)
    print("  " + "-"*60)
    for num, (slope, p, cur, overall) in sorted_asc[:5]:
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(
            f"  {num:>3}번 | {slope*1e4:>13.4f} | {p:>7.4f} | "
            f"{cur:>10.4f} | {overall:>8.4f} | {sig}"
        )

    print("\n[현재 하락 추세 TOP 5]")
    print(hdr)
    print("  " + "-"*60)
    for num, (slope, p, cur, overall) in sorted_asc[-5:][::-1]:
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(
            f"  {num:>3}번 | {slope*1e4:>13.4f} | {p:>7.4f} | "
            f"{cur:>10.4f} | {overall:>8.4f} | {sig}"
        )

    # 추세 전환점 탐지 (이동평균이 최근 100회 이내에 방향 전환한 번호)
    print("\n[추세 전환점 탐지] - 최근 100회 이내 방향 전환 감지")
    print("  번호 | 전환 위치 | 전 기울기 | 후 기울기 | 판정")
    print("  " + "-"*55)
    cp_found = []
    for num in range(1, 46):
        arr = appear[num-1]
        ma = np.convolve(arr, np.ones(WINDOW)/WINDOW, mode='valid')
        if len(ma) < 200:
            continue
        seg1 = ma[-200:-100]
        seg2 = ma[-100:]
        x1 = np.arange(len(seg1))
        x2 = np.arange(len(seg2))
        s1 = stats.linregress(x1, seg1).slope
        s2 = stats.linregress(x2, seg2).slope
        # 방향이 바뀌었는지
        if s1 * s2 < 0:  # 부호 반전 = 전환
            direction = "상승->하락" if s1 > 0 else "하락->상승"
            cp_found.append((num, s1, s2, direction))

    if cp_found:
        for num, s1, s2, d in sorted(cp_found, key=lambda x: abs(x[2]-x[1]), reverse=True)[:10]:
            print(f"  {num:>3}번 | 최근 100회 | {s1*1e4:>9.3f} | {s2*1e4:>9.3f} | {d}")
    else:
        print("  전환점 없음")

    return appear


def analysis2_sum_trend(rounds, all_numbers):
    sep()
    print("[분석 2] 합계의 장기 추세 분석")
    print("="*65)

    sums = np.array([sum(ns) for ns in all_numbers])
    n = len(sums)

    # 100회 이동 평균
    ma100 = np.convolve(sums, np.ones(100)/100, mode='valid')
    ma_first = ma100[:50].mean()
    ma_last = ma100[-50:].mean()

    print(f"\n  전체 합계: 평균={sums.mean():.2f}, 표준편차={sums.std():.2f}")
    print(f"  100회 이동평균 초반(1~150회) 평균: {ma_first:.2f}")
    print(f"  100회 이동평균 후반(최근 50포인트) 평균: {ma_last:.2f}")
    print(f"  변화량: {ma_last - ma_first:+.2f}")

    # 전체 선형 추세
    x = np.arange(n)
    slope, intercept, r, p, se = stats.linregress(x, sums)
    print(f"\n  [전체 선형 추세] 기울기={slope:.4f}/회차, R^2={r**2:.4f}, p={p:.4f}")
    if p < 0.05:
        direction = "증가" if slope > 0 else "감소"
        print(f"  -> 통계적으로 유의한 {direction} 추세 (p<0.05)")
    else:
        print(f"  -> 통계적으로 유의하지 않음 (추세 없음, p={p:.3f})")

    # 구간별(300회 단위) 평균 비교
    print("\n  [300회 단위 구간별 평균 합계]")
    print("  구간       | 회차 범위     | 평균 합계 | 표준편차 | 중앙값")
    print("  " + "-"*58)
    groups = []
    labels = []
    for i in range(0, n, 300):
        seg = sums[i:i+300]
        r_start = rounds[i]
        r_end = rounds[min(i+len(seg)-1, n-1)]
        lbl = f"구간{i//300+1}({r_start}~{r_end})"
        print(f"  {lbl:<18} | {seg.mean():>9.2f} | {seg.std():>8.2f} | {np.median(seg):>6.1f}")
        groups.append(seg)
        labels.append(lbl)

    # Kruskal-Wallis 검정
    stat, p_kw = stats.kruskal(*groups)
    print(f"\n  [Kruskal-Wallis 검정] H={stat:.4f}, p={p_kw:.4f}")
    if p_kw < 0.05:
        print(f"  -> 구간 간 합계 분포가 통계적으로 유의하게 다름 (p<0.05)")
        # 사후 검정: 1구간 vs 마지막 구간
        stat2, p2 = stats.mannwhitneyu(groups[0], groups[-1], alternative='two-sided')
        print(f"  -> 1구간 vs 마지막구간 Mann-Whitney U: p={p2:.4f}")
    else:
        print(f"  -> 구간 간 합계 분포에 유의한 차이 없음")

    return sums


def analysis3_distribution_change(rounds, all_numbers):
    sep()
    print("[분석 3] 번호 분포의 구간별 변화 (200회씩 6구간)")
    print("="*65)

    n = len(all_numbers)
    seg_size = 200

    print("\n  구간       | 저번호(1-15) | 중번호(16-30) | 고번호(31-45)")
    print("  " + "-"*58)

    low_ratios, mid_ratios, high_ratios = [], [], []
    seg_labels = []

    for i in range(0, min(n, seg_size * 6), seg_size):
        seg = all_numbers[i:i+seg_size]
        if len(seg) < 50:
            continue
        nums_flat = [x for ns in seg for x in ns]
        total = len(nums_flat)
        low = sum(1 for x in nums_flat if x <= 15) / total
        mid = sum(1 for x in nums_flat if 16 <= x <= 30) / total
        high = sum(1 for x in nums_flat if x >= 31) / total
        r_start = rounds[i]
        r_end = rounds[min(i+len(seg)-1, n-1)]
        lbl = f"{r_start}~{r_end}회"
        print(f"  {lbl:<12} | {low:>12.4f} | {mid:>13.4f} | {high:>13.4f}")
        low_ratios.append(low)
        mid_ratios.append(mid)
        high_ratios.append(high)
        seg_labels.append(lbl)

    # 추세 검정
    print("\n  [구간별 저번호 비율 선형 추세]")
    if len(low_ratios) >= 3:
        x = np.arange(len(low_ratios))
        sl, ic, r, p, _ = stats.linregress(x, low_ratios)
        sig = "유의 *" if p < 0.05 else "비유의"
        print(f"    기울기={sl:.5f}/구간, p={p:.4f} -> {sig}")

    print("  [구간별 고번호 비율 선형 추세]")
    if len(high_ratios) >= 3:
        x = np.arange(len(high_ratios))
        sl, ic, r, p, _ = stats.linregress(x, high_ratios)
        sig = "유의 *" if p < 0.05 else "비유의"
        print(f"    기울기={sl:.5f}/구간, p={p:.4f} -> {sig}")

    # ANOVA (저번호 각 구간 raw 값으로)
    seg_low_raw = []
    for i in range(0, min(n, seg_size * 6), seg_size):
        seg = all_numbers[i:i+seg_size]
        if len(seg) < 50:
            continue
        seg_low_raw.append([sum(1 for x in ns if x <= 15) for ns in seg])

    if len(seg_low_raw) >= 3:
        stat, p_kw = stats.kruskal(*seg_low_raw)
        print(f"\n  [저번호 개수 Kruskal-Wallis] H={stat:.3f}, p={p_kw:.4f}")
        if p_kw < 0.05:
            print("  -> 구간별 저번호 출현 개수가 유의하게 다름")
        else:
            print("  -> 구간별 저번호 출현 개수에 유의한 차이 없음")


def analysis4_recent200_unique(rounds, all_numbers):
    sep()
    print("[분석 4] 최근 200회차의 독특한 패턴 발굴")
    print("="*65)

    n = len(all_numbers)
    recent = all_numbers[-200:]
    past = all_numbers[:-200]

    def get_features(data):
        sums = [sum(ns) for ns in data]
        odd_counts = [sum(1 for x in ns if x % 2 == 1) for ns in data]
        low_counts = [sum(1 for x in ns if x <= 15) for ns in data]
        high_counts = [sum(1 for x in ns if x >= 31) for ns in data]
        max_gaps = [max(sorted(ns)[i+1]-sorted(ns)[i] for i in range(5)) for ns in data]
        consec = [sum(1 for i in range(5) if sorted(ns)[i+1]-sorted(ns)[i]==1) for ns in data]
        return {
            "합계": sums,
            "홀수개수": odd_counts,
            "저번호(1-15)개수": low_counts,
            "고번호(31-45)개수": high_counts,
            "최대간격": max_gaps,
            "연속쌍수": consec,
        }

    rf = get_features(recent)
    pf = get_features(past)

    print(f"\n  비교: 과거({len(past)}회) vs 최근({len(recent)}회)")
    print(f"\n  특성              | 과거 평균 | 최근 평균 | 차이    | p-value | 유의")
    print("  " + "-"*65)
    for feat in rf:
        r_arr = np.array(rf[feat], dtype=float)
        p_arr = np.array(pf[feat], dtype=float)
        stat, p = stats.mannwhitneyu(p_arr, r_arr, alternative='two-sided')
        diff = r_arr.mean() - p_arr.mean()
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(
            f"  {feat:<18} | {p_arr.mean():>9.3f} | {r_arr.mean():>9.3f} | "
            f"{diff:>+7.3f} | {p:>7.4f} | {sig}"
        )

    # 번호별 출현 빈도 변화
    print("\n  [번호별 출현빈도 변화 - 최근 200회 vs 전체 기대빈도]")
    print("  (최근200회 출현횟수 - 기대횟수) 상위/하위 5번호")
    expected_per200 = 200 * 6 / 45  # 각 번호 기대 출현횟수
    recent_flat = [x for ns in recent for x in ns]
    from collections import Counter
    cnt = Counter(recent_flat)
    deviations = {num: cnt.get(num, 0) - expected_per200 for num in range(1, 46)}
    sorted_dev = sorted(deviations.items(), key=lambda x: x[1], reverse=True)
    print("  과잉출현: ", [(n, f"{v:+.1f}") for n, v in sorted_dev[:5]])
    print("  과소출현: ", [(n, f"{v:+.1f}") for n, v in sorted_dev[-5:][::-1]])


def analysis5_seasonality(rounds, all_numbers, months):
    sep()
    print("[분석 5] 계절성/주기성 탐지")
    print("="*65)

    n = len(all_numbers)

    # 월별 각 번호 출현빈도
    print("\n  [월별 번호 출현율 차이 검정] - 유의한 번호 (p<0.05)")
    print("  번호 | chi2    | p-value | 과잉 월 | 과소 월")
    print("  " + "-"*52)
    significant_nums = []
    for num in range(1, 46):
        monthly_counts = defaultdict(int)
        monthly_totals = defaultdict(int)
        for i, (ns, m) in enumerate(zip(all_numbers, months)):
            monthly_totals[m] += 1
            if num in ns:
                monthly_counts[m] += 1
        # chi-square 검정
        obs = np.array([monthly_counts[m] for m in range(1, 13)])
        total_appear = obs.sum()
        total_rounds = sum(monthly_totals[m] for m in range(1, 13))
        exp = np.array([monthly_totals[m] * total_appear / total_rounds for m in range(1, 13)])
        # 0 방지
        mask = exp > 0
        chi2 = ((obs[mask] - exp[mask])**2 / exp[mask]).sum()
        df = mask.sum() - 1
        p = 1 - stats.chi2.cdf(chi2, df)
        if p < 0.10:
            rates = {m: monthly_counts[m]/monthly_totals[m] if monthly_totals[m]>0 else 0
                     for m in range(1, 13)}
            top_month = max(rates, key=rates.get)
            bot_month = min(rates, key=rates.get)
            significant_nums.append((num, chi2, p, top_month, bot_month))

    if significant_nums:
        for num, chi2, p, top_m, bot_m in sorted(significant_nums, key=lambda x: x[2])[:10]:
            sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "+"))
            print(f"  {num:>3}번 | {chi2:>7.3f} | {p:>7.4f} | {top_m:>5}월 | {bot_m:>5}월 {sig}")
    else:
        print("  유의한 월별 패턴 없음 (모든 번호 p>=0.10)")

    # 짝수/홀수 회차 비교
    print("\n  [짝수 회차 vs 홀수 회차 패턴 비교]")
    even_rounds = [all_numbers[i] for i in range(n) if rounds[i] % 2 == 0]
    odd_rounds  = [all_numbers[i] for i in range(n) if rounds[i] % 2 == 1]

    feats = {
        "합계": lambda ns: sum(ns),
        "홀수개수": lambda ns: sum(1 for x in ns if x % 2 == 1),
        "저번호비율": lambda ns: sum(1 for x in ns if x <= 15) / 6,
    }
    print(f"  특성       | 홀수회차평균 | 짝수회차평균 | p-value")
    print("  " + "-"*46)
    for fname, fn in feats.items():
        ev = np.array([fn(ns) for ns in even_rounds])
        od = np.array([fn(ns) for ns in odd_rounds])
        _, p = stats.mannwhitneyu(od, ev, alternative='two-sided')
        sig = "*" if p < 0.05 else "ns"
        print(f"  {fname:<10} | {od.mean():>12.4f} | {ev.mean():>12.4f} | {p:>7.4f} {sig}")

    # 자기상관 분석 (합계의 주기성)
    print("\n  [합계 자기상관 - 유의한 주기 탐색]")
    sums = np.array([sum(ns) for ns in all_numbers], dtype=float)
    sums_z = (sums - sums.mean()) / sums.std()
    max_lag = 52
    sig_lags = []
    # 95% 신뢰 구간
    ci = 1.96 / np.sqrt(n)
    for lag in range(1, max_lag+1):
        acf = np.corrcoef(sums_z[:-lag], sums_z[lag:])[0, 1]
        if abs(acf) > ci:
            sig_lags.append((lag, acf))
    if sig_lags:
        print(f"  유의 자기상관 (95% CI={ci:.4f}) 라그:")
        for lag, acf in sig_lags[:10]:
            print(f"    lag={lag:>3}회 | ACF={acf:.4f}")
    else:
        print(f"  유의한 자기상관 없음 (95% CI 기준={ci:.4f})")


def analysis6_changepoint(rounds, all_numbers, appear):
    sep()
    print("[분석 6] 변화점(Change Point) 심층 분석")
    print("="*65)

    n = len(all_numbers)
    sums = np.array([sum(ns) for ns in all_numbers], dtype=float)

    # CUSUM 기반 전체 변화점 탐지 (합계 기준)
    # 이동 평균 기울기 변화로 주요 구조 변화 탐지
    print("\n  [합계 기준 CUSUM 변화점 분석]")
    mu = sums.mean()
    cusum_pos = np.zeros(n)
    cusum_neg = np.zeros(n)
    k = sums.std() * 0.5  # allowance
    for i in range(1, n):
        cusum_pos[i] = max(0, cusum_pos[i-1] + (sums[i] - mu) - k)
        cusum_neg[i] = max(0, cusum_neg[i-1] - (sums[i] - mu) - k)

    # 변화점: CUSUM이 임계값(4*sigma) 초과 후 리셋되는 지점
    threshold = 4 * sums.std()
    change_points = []
    for i in range(1, n):
        if cusum_pos[i] > threshold or cusum_neg[i] > threshold:
            change_points.append((rounds[i], cusum_pos[i], cusum_neg[i]))

    if change_points:
        # 연속 그룹 중 첫 번째만 취함
        cp_rounds = [change_points[0]]
        for cp in change_points[1:]:
            if cp[0] - cp_rounds[-1][0] > 50:
                cp_rounds.append(cp)
        print(f"  주요 변화점 회차 (CUSUM 임계={threshold:.1f}):")
        for r, cp, cn in cp_rounds[:8]:
            direction = "상승편향" if cp > cn else "하락편향"
            print(f"    회차 {r:>5} | CUSUM+={cp:>8.2f} | CUSUM-={cn:>8.2f} | {direction}")
    else:
        print("  유의한 CUSUM 변화점 없음")

    # 100회 창 이동 분산 - 분산이 갑자기 변하는 구간 탐지
    print("\n  [100회 이동 분산 - 변동성 변화 구간]")
    win = 100
    roll_var = np.array([sums[i:i+win].var() for i in range(n-win)])
    roll_rounds = rounds[win//2:win//2+len(roll_var)]

    # 분산 최대/최소 구간
    max_idx = roll_var.argmax()
    min_idx = roll_var.argmin()
    print(f"    분산 최대 구간 중심: {roll_rounds[max_idx]}회 (분산={roll_var[max_idx]:.1f})")
    print(f"    분산 최소 구간 중심: {roll_rounds[min_idx]}회 (분산={roll_var[min_idx]:.1f})")
    print(f"    초기(1~100회) 분산: {sums[:100].var():.1f}")
    print(f"    최근(최근100회) 분산: {sums[-100:].var():.1f}")

    # 번호별 변화점: 출현 패턴이 가장 크게 변한 번호
    print("\n  [번호별 출현 패턴 - 전반부 vs 후반부 가장 큰 변화 TOP5]")
    mid = n // 2
    num_changes = {}
    for num in range(1, 46):
        arr = appear[num-1]
        first_half = arr[:mid].mean()
        second_half = arr[mid:].mean()
        diff = abs(second_half - first_half)
        _, p = stats.mannwhitneyu(arr[:mid], arr[mid:], alternative='two-sided')
        num_changes[num] = (first_half, second_half, second_half - first_half, p)

    sorted_changes = sorted(num_changes.items(), key=lambda x: abs(x[1][2]), reverse=True)
    print("  번호 | 전반부율 | 후반부율 | 변화량  | p-value | 유의")
    print("  " + "-"*52)
    for num, (fh, sh, diff, p) in sorted_changes[:10]:
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(f"  {num:>3}번 | {fh:>8.4f} | {sh:>8.4f} | {diff:>+7.4f} | {p:>7.4f} | {sig}")

    # 변화점 이후 패턴 안정성 검증 (700회 이후 vs 현재)
    print("\n  [변화점 이후 패턴 안정성 - 700회 이후 vs 최근 200회]")
    mid2_idx = np.searchsorted(rounds, 700)
    seg_700 = all_numbers[mid2_idx:-200]
    seg_recent = all_numbers[-200:]
    if len(seg_700) > 50:
        s700 = [sum(ns) for ns in seg_700]
        srec = [sum(ns) for ns in seg_recent]
        _, p_stab = stats.mannwhitneyu(s700, srec, alternative='two-sided')
        print(f"    700~1015회 합계 평균: {np.mean(s700):.2f}")
        print(f"    최근 200회 합계 평균: {np.mean(srec):.2f}")
        print(f"    Mann-Whitney U p={p_stab:.4f} -> {'유의한 차이' if p_stab < 0.05 else '안정적 (차이 없음)'}")


def analysis7_lookback_window(rounds, all_numbers):
    sep()
    print("[분석 7] 최적 Lookback Window 분석")
    print("="*65)

    n = len(all_numbers)
    windows = [50, 100, 200, 500]

    print("\n  방법: N회 lookback으로 각 번호 출현빈도 추정 -> 다음 회차 예측 성능")
    print("  지표: 실제 당첨번호 6개 중 예측 TOP-6에 포함된 개수 평균")
    print("\n  Lookback | 평균매치수 | 최대매치수 | 분산  | 설명")
    print("  " + "-"*58)

    results = {}
    test_start = 500  # 500회부터 테스트 (충분한 학습 데이터 확보)

    for window in windows:
        matches = []
        for i in range(test_start, n):
            if i < window:
                continue
            # window 기간의 출현 빈도로 다음 번호 예측
            train = all_numbers[i-window:i]
            from collections import Counter
            cnt = Counter(x for ns in train for x in ns)
            # 빈도 기준 TOP-6 번호
            top6 = set(x for x, _ in cnt.most_common(6))
            actual = set(all_numbers[i])
            match = len(top6 & actual)
            matches.append(match)

        avg_m = np.mean(matches)
        max_m = np.max(matches)
        var_m = np.var(matches)
        results[window] = (avg_m, max_m, var_m)

        note = ""
        if window == 200:
            note = "<-- 현재 시스템"
        print(f"  {window:>8} | {avg_m:>10.4f} | {max_m:>10} | {var_m:>5.4f} | {note}")

    # 최적 window
    best_w = max(results, key=lambda w: results[w][0])
    print(f"\n  [결론] 평균 매치수 기준 최적 window: {best_w}회")

    # 현재 200회 vs 최적
    cur_avg = results[200][0]
    best_avg = results[best_w][0]
    if best_w != 200:
        print(f"  현재(200회) 평균매치: {cur_avg:.4f}")
        print(f"  최적({best_w}회) 평균매치: {best_avg:.4f}")
        diff_pct = (best_avg - cur_avg) / cur_avg * 100
        print(f"  개선 여지: {diff_pct:+.2f}%")
        print(f"  -> 현재 200회 설정이 {'최적에 가깝다' if abs(diff_pct) < 2 else '개선 가능'}")
    else:
        print(f"  -> 현재 200회 설정이 최적임")

    # 추가: N이 커질수록 성능이 개선되는가?
    print("\n  [Window 크기와 성능의 관계]")
    avgs = [results[w][0] for w in windows]
    x = np.arange(len(windows))
    slope, _, r, p, _ = stats.linregress(x, avgs)
    if p < 0.05:
        direction = "증가" if slope > 0 else "감소"
        print(f"  Window 증가 -> 성능 {direction} 추세 (기울기={slope:.4f}, p={p:.4f})")
    else:
        print(f"  Window 크기와 성능 간 유의한 선형 관계 없음 (p={p:.4f})")
        print(f"  -> 단순히 window를 키운다고 성능이 개선되지 않음")


def analysis_summary(rounds, all_numbers):
    sep()
    print("[종합 결론 및 시스템 개선 방향]")
    print("="*65)

    n = len(all_numbers)
    recent = all_numbers[-200:]
    past = all_numbers[:-200]

    # 현재 시스템이 놓치고 있는 패턴 요약
    print("""
  [핵심 발견사항]

  1. 추세 변화 번호 식별
     - 상승 추세 번호들은 현재 출현율이 전체 평균보다 높음
     - 시스템이 이동평균 출현율 가중치를 적용하지 않는다면 개선 여지 있음

  2. 합계 장기 추세
     - 통계적 유의성 여부에 따라 합계 필터 범위 조정 필요
     - 최근 구간 합계가 전체 평균과 다르면 sum_range 필터 동적 갱신 권장

  3. 구간별 번호 분포
     - 저번호/고번호 비율이 구간별로 유의하게 다른지 확인
     - 유의한 차이 존재 시: 구간별 필터 기준 분리 or 최근 가중치 강화

  4. 최근 200회 특성
     - 과거 대비 통계적으로 다른 특성이 있을 경우
     - 해당 특성의 필터 기준값을 최근 데이터 기반으로 재산정 권장

  5. 계절성/주기성
     - 유의한 자기상관 lag 발견 시: 해당 주기를 ML 특성으로 추가
     - 짝홀 회차 패턴 차이: 회차 패리티를 입력 특성으로 고려

  6. 변화점 분석
     - 변화점 이후 패턴이 안정적이라면: 변화점 이전 데이터 가중치 낮춤
     - 안정적이지 않다면: 최근 데이터 더 적극적으로 가중치 부여

  7. Lookback Window
     - 최적 window != 200회인 경우: config 조정 권장
     - window와 성능 간 선형 관계 없음 = 비선형 가중치 방식이 더 유효

  [필터/가중치 개선 우선순위]
  우선 1: sum_range 필터 -> 최근 100회 평균으로 동적 갱신
  우선 2: 번호 가중치 -> 최근 50회 출현율 기반 가중 샘플링
  우선 3: Lookback -> 최적 window로 교체 또는 멀티-윈도우 앙상블
""")


def main():
    print("로또 당첨번호 시계열 패턴 분석 시작")
    print("DB:", DB_PATH)

    rounds, all_numbers, dates, months = load_data()
    print(f"로드 완료: {len(rounds)}회차 ({rounds[0]}~{rounds[-1]}회)")

    appear = analysis1_moving_average_trend(rounds, all_numbers)
    sums = analysis2_sum_trend(rounds, all_numbers)
    analysis3_distribution_change(rounds, all_numbers)
    analysis4_recent200_unique(rounds, all_numbers)
    analysis5_seasonality(rounds, all_numbers, months)
    analysis6_changepoint(rounds, all_numbers, appear)
    analysis7_lookback_window(rounds, all_numbers)
    analysis_summary(rounds, all_numbers)

    print("\n" + "="*65)
    print("분석 완료")


if __name__ == "__main__":
    main()
