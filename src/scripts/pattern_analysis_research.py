"""
다차원 패턴 분석 - 연구 스크립트
목적: 1214회차+ 실제 당첨 데이터에서 통계적으로 유의미한 패턴 탐색
DB 구조: lotto_numbers 테이블, numbers 컬럼은 TEXT ("n1,n2,n3,n4,n5,n6")
"""
import sqlite3
import os
import sys
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

PROJECT_ROOT = r"d:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0"
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'lotto_numbers.db')


def load_winning_numbers():
    """당첨번호 로드 - (round, numbers_list, bonus, date) 형태"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT round, numbers, draw_date, bonus_number FROM lotto_numbers ORDER BY round"
    )
    rows = cursor.fetchall()
    conn.close()

    data = []
    for row in rows:
        round_num = row[0]
        nums = sorted([int(x) for x in row[1].split(',')])
        date_str = row[2]
        bonus = row[3]
        data.append({
            'round': round_num,
            'numbers': nums,
            'bonus': bonus,
            'date': date_str,
        })
    return data


# ===========================
# 분석 함수들
# ===========================

def analyze_number_frequency(data):
    """번호별 출현 빈도 분석"""
    print("\n" + "="*60)
    print("[분석 1] 번호별 출현 빈도")
    print("="*60)

    all_nums = []
    for d in data:
        all_nums.extend(d['numbers'])

    freq = Counter(all_nums)
    total_draws = len(data)
    expected = total_draws * 6 / 45

    print(f"총 회차: {total_draws}, 기대 출현횟수/번호: {expected:.2f}")
    print("\n출현 상위 10개 번호:")
    for num, cnt in freq.most_common(10):
        deviation = (cnt - expected) / expected * 100
        print(f"  번호 {num:2d}: {cnt}회 (기대대비 {deviation:+.1f}%)")

    print("\n출현 하위 10개 번호:")
    for num, cnt in freq.most_common()[-10:]:
        deviation = (cnt - expected) / expected * 100
        print(f"  번호 {num:2d}: {cnt}회 (기대대비 {deviation:+.1f}%)")

    # 전체 번호 출현 횟수
    print("\n전체 번호별 출현 횟수:")
    for num in range(1, 46):
        cnt = freq.get(num, 0)
        deviation = (cnt - expected) / expected * 100
        bar = '#' * int(cnt / expected * 5)
        print(f"  {num:2d}: {cnt:3d}회 ({deviation:+5.1f}%) {bar}")

    return freq


def analyze_consecutive_absence(data):
    """연속 미출현 패턴 분석"""
    print("\n" + "="*60)
    print("[분석 2] 연속 미출현 -> 출현 패턴")
    print("="*60)

    last_seen = {n: 0 for n in range(1, 46)}
    absence_prob = defaultdict(lambda: {'appeared': 0, 'total': 0})

    for i, draw in enumerate(data):
        for num in range(1, 46):
            absence_count = i - last_seen[num]
            appeared = num in draw['numbers']
            if absence_count < 80:
                absence_prob[absence_count]['total'] += 1
                if appeared:
                    absence_prob[absence_count]['appeared'] += 1

        for num in draw['numbers']:
            last_seen[num] = i + 1

    base_prob = 6 / 45 * 100
    significant = []

    print(f"\n미출현 N회차 후 출현 확률 (기대: 6/45 = {base_prob:.2f}%):")
    for n in range(1, 65):
        d = absence_prob[n]
        if d['total'] >= 30:
            prob = d['appeared'] / d['total'] * 100
            deviation = prob - base_prob
            chi2 = ((d['appeared'] - d['total'] * base_prob / 100) ** 2) / (d['total'] * base_prob / 100 + 0.001)
            print(f"  미출현 {n:2d}회 -> 출현확률: {prob:5.2f}% (편차: {deviation:+5.2f}%, n={d['total']:4d}, chi2={chi2:.3f})")
            if abs(deviation) > 2:
                significant.append((n, prob, deviation, d['total'], chi2))

    print(f"\n[유의미한 패턴] 편차 >2% 항목: {len(significant)}개")
    for n, prob, dev, total, chi2 in significant:
        tag = "출현 증가" if dev > 0 else "출현 감소"
        print(f"  미출현 {n:2d}회: {prob:.2f}% ({tag}, 편차 {dev:+.2f}%, n={total}, chi2={chi2:.3f})")

    return absence_prob, significant


def analyze_previous_round_correlation(data):
    """이전 회차 번호와 이번 회차 겹침 패턴"""
    print("\n" + "="*60)
    print("[분석 3] 이전 회차 연관성 - 겹침 번호 수")
    print("="*60)

    expected_overlap = 6 * 6 / 45

    for lag in [1, 2, 3, 4, 5]:
        overlaps = []
        for i in range(lag, len(data)):
            current = set(data[i]['numbers'])
            prev = set(data[i - lag]['numbers'])
            overlap = len(current & prev)
            overlaps.append(overlap)

        avg = statistics.mean(overlaps)
        std = statistics.stdev(overlaps) if len(overlaps) > 1 else 0
        dist = Counter(overlaps)

        print(f"\n  직전 {lag}회차와 겹침 (기대값: {expected_overlap:.3f}):")
        print(f"    평균: {avg:.4f}, 표준편차: {std:.4f}")
        print(f"    분포: {dict(sorted(dist.items()))}")
        total = sum(dist.values())
        for k in sorted(dist.keys()):
            pct = dist[k] / total * 100
            print(f"      겹침 {k}개: {dist[k]}회 ({pct:.1f}%)")

    # 전이 행렬: 직전 겹침 수 -> 이번 겹침 수
    print("\n  직전 회차 겹침 수 -> 이번 회차 겹침 수 전이 행렬:")
    transition = defaultdict(list)
    for i in range(2, len(data)):
        prev_overlap = len(set(data[i - 1]['numbers']) & set(data[i - 2]['numbers']))
        curr_overlap = len(set(data[i]['numbers']) & set(data[i - 1]['numbers']))
        transition[prev_overlap].append(curr_overlap)

    for k in sorted(transition.keys())[:7]:
        vals = transition[k]
        if len(vals) >= 10:
            avg = statistics.mean(vals)
            dist2 = Counter(vals)
            print(f"    이전 겹침={k} (n={len(vals)}) -> 현재 겹침 평균: {avg:.3f}, 분포: {dict(sorted(dist2.items()))}")


def analyze_sum_distribution(data):
    """당첨번호 합계 분포 분석"""
    print("\n" + "="*60)
    print("[분석 4] 당첨번호 합계 분포")
    print("="*60)

    sums = [sum(d['numbers']) for d in data]
    avg = statistics.mean(sums)
    std = statistics.stdev(sums)
    median = statistics.median(sums)
    theory_mean = (1 + 45) * 6 / 2  # = 138

    print(f"  합계 평균: {avg:.2f}")
    print(f"  이론적 기대값: {theory_mean:.0f}")
    print(f"  표준편차: {std:.2f}")
    print(f"  중앙값: {median}")
    print(f"  범위: {min(sums)} ~ {max(sums)}")

    # 구간별 분포
    bins = [
        (21, 80), (80, 100), (100, 110), (110, 120), (120, 130),
        (130, 140), (140, 150), (150, 160), (160, 170), (170, 180),
        (180, 200), (200, 230), (230, 280)
    ]
    total = len(sums)
    print("\n  구간별 분포:")
    for lo, hi in bins:
        cnt = sum(1 for s in sums if lo <= s < hi)
        pct = cnt / total * 100
        bar = '#' * int(pct / 2)
        print(f"    [{lo:3d}-{hi:3d}): {cnt:4d}회 ({pct:5.1f}%) {bar}")

    # 최근 50회 vs 전체 비교
    recent_50_sums = [sum(d['numbers']) for d in data[-50:]]
    print(f"\n  최근 50회 합계 평균: {statistics.mean(recent_50_sums):.2f} (전체: {avg:.2f})")
    print(f"  최근 50회 합계 표준편차: {statistics.stdev(recent_50_sums):.2f} (전체: {std:.2f})")


def analyze_date_correlation(data):
    """날짜와 번호 패턴 상관관계"""
    print("\n" + "="*60)
    print("[분석 5] 날짜 관련 패턴")
    print("="*60)

    base_date = datetime(2002, 12, 7)  # 1회차

    month_sums = defaultdict(list)
    month_odd_counts = defaultdict(list)

    for d in data:
        draw_date = base_date + timedelta(weeks=d['round'] - 1)
        month = draw_date.month
        nums_sum = sum(d['numbers'])
        odd_count = sum(1 for n in d['numbers'] if n % 2 == 1)
        month_sums[month].append(nums_sum)
        month_odd_counts[month].append(odd_count)

    print("  월별 당첨번호 합계 평균 및 홀수 개수:")
    overall_sum_avg = statistics.mean([sum(d['numbers']) for d in data])
    for month in range(1, 13):
        if month_sums[month]:
            s_avg = statistics.mean(month_sums[month])
            s_std = statistics.stdev(month_sums[month]) if len(month_sums[month]) > 1 else 0
            o_avg = statistics.mean(month_odd_counts[month])
            month_name = ['1월', '2월', '3월', '4월', '5월', '6월',
                          '7월', '8월', '9월', '10월', '11월', '12월'][month - 1]
            print(f"    {month_name}: 합계평균={s_avg:.1f}(+-{s_std:.1f}), 홀수평균={o_avg:.2f}, n={len(month_sums[month])}")

    # 회차 끝자리와 합계 상관
    print("\n  회차 끝자리(1의 자리)별 합계 평균:")
    digit_sums = defaultdict(list)
    digit_odd = defaultdict(list)
    for d in data:
        digit = d['round'] % 10
        digit_sums[digit].append(sum(d['numbers']))
        digit_odd[digit].append(sum(1 for n in d['numbers'] if n % 2 == 1))
    for digit in range(10):
        if digit_sums[digit]:
            s_avg = statistics.mean(digit_sums[digit])
            o_avg = statistics.mean(digit_odd[digit])
            print(f"    끝자리 {digit}: 합계평균={s_avg:.2f}, 홀수평균={o_avg:.2f}, n={len(digit_sums[digit])}")


def analyze_hot_cold_numbers(data, window=10):
    """최근 N회 핫/콜드 번호 분석"""
    print("\n" + "="*60)
    print(f"[분석 6] 핫/콜드 번호 패턴 (최근 {window}회 기준)")
    print("="*60)

    hot_counts = []     # 각 회차에서 당첨번호 중 핫번호 개수
    cold_counts = []
    neutral_counts = []

    for i in range(window, len(data)):
        recent = []
        for j in range(i - window, i):
            recent.extend(data[j]['numbers'])

        recent_freq = Counter(recent)
        sorted_nums = [n for n, _ in recent_freq.most_common()]
        hot_nums = set(sorted_nums[:10])
        cold_nums = set(sorted_nums[-15:])
        neutral_nums = set(range(1, 46)) - hot_nums - cold_nums

        current = set(data[i]['numbers'])
        hot_in_current = len(current & hot_nums)
        cold_in_current = len(current & cold_nums)
        neutral_in_current = len(current & neutral_nums)

        hot_counts.append(hot_in_current)
        cold_counts.append(cold_in_current)
        neutral_counts.append(neutral_in_current)

    n_samples = len(hot_counts)
    print(f"  분석 회차 수: {n_samples}")
    print(f"  핫 번호 (상위 10개) -> 당첨번호에 포함 평균: {statistics.mean(hot_counts):.3f}개/회")
    print(f"    기대값: 6 * 10/45 = {6*10/45:.3f}개")
    print(f"  콜드 번호 (하위 15개) -> 당첨번호에 포함 평균: {statistics.mean(cold_counts):.3f}개/회")
    print(f"    기대값: 6 * 15/45 = {6*15/45:.3f}개")
    print(f"  중립 번호 (나머지 20개) -> 당첨번호에 포함 평균: {statistics.mean(neutral_counts):.3f}개/회")
    print(f"    기대값: 6 * 20/45 = {6*20/45:.3f}개")

    # 분포
    hot_dist = Counter(hot_counts)
    cold_dist = Counter(cold_counts)
    print(f"\n  핫 번호 포함 수 분포: {dict(sorted(hot_dist.items()))}")
    print(f"  콜드 번호 포함 수 분포: {dict(sorted(cold_dist.items()))}")


def analyze_number_pair_patterns(data):
    """번호 쌍 동시 출현 패턴"""
    print("\n" + "="*60)
    print("[분석 7] 번호 쌍 동시 출현 편향")
    print("="*60)

    pair_count = defaultdict(int)
    total_draws = len(data)

    for d in data:
        nums = sorted(d['numbers'])
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair_count[(nums[i], nums[j])] += 1

    # 기대 동시 출현 횟수: C(6,2)/C(45,2) * total
    expected_pair = total_draws * 15 / 990
    print(f"  총 가능 쌍: C(45,2) = 990개")
    print(f"  기대 쌍 출현 횟수: {expected_pair:.2f}회")
    print(f"  실제 관측된 쌍 수: {len(pair_count)}개")

    total_possible_pairs = 990
    never_appeared = total_possible_pairs - len(pair_count)
    print(f"  한 번도 같이 안 나온 쌍: {never_appeared}개")

    sorted_pairs = sorted(pair_count.items(), key=lambda x: x[1], reverse=True)

    print(f"\n  자주 나오는 쌍 상위 20개:")
    for pair, cnt in sorted_pairs[:20]:
        ratio = cnt / expected_pair
        print(f"    {pair}: {cnt}회 (기대대비 {ratio:.2f}배)")

    print(f"\n  드물게 나오는 쌍 (1~2회):")
    rare_pairs = [(p, c) for p, c in sorted_pairs if c <= 2]
    print(f"    1회 출현: {sum(1 for p,c in rare_pairs if c==1)}쌍")
    print(f"    2회 출현: {sum(1 for p,c in rare_pairs if c==2)}쌍")

    # 연속 번호 쌍 분석
    consecutive_pairs = [(n, n + 1) for n in range(1, 45)]
    consec_count = [pair_count.get(p, 0) for p in consecutive_pairs]
    avg_consec = statistics.mean(consec_count)
    print(f"\n  연속 번호 쌍 평균 출현: {avg_consec:.2f}회 (전체 쌍 평균 대비 {avg_consec/expected_pair:.3f}배)")
    print("  연속 번호 쌍 출현 횟수:")
    for p, c in zip(consecutive_pairs, consec_count):
        ratio = c / expected_pair
        print(f"    {p}: {c}회 ({ratio:.2f}배)")

    return pair_count, expected_pair


def analyze_section_patterns(data):
    """구간별 번호 분포 패턴"""
    print("\n" + "="*60)
    print("[분석 8] 구간별 분포 패턴 (각 구간에서 몇 개 출현)")
    print("="*60)

    # 구간: 1-9(9개), 10-19(10개), 20-29(10개), 30-39(10개), 40-45(6개)
    sections = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]
    total_draws = len(data)

    for lo, hi in sections:
        size = hi - lo + 1
        expected = 6 * size / 45
        counts_in_section = [sum(1 for n in d['numbers'] if lo <= n <= hi) for d in data]

        avg = statistics.mean(counts_in_section)
        std = statistics.stdev(counts_in_section)
        dist = Counter(counts_in_section)

        print(f"\n  구간 [{lo:2d}-{hi:2d}] (크기 {size}개, 기대={expected:.3f}개):")
        print(f"    실제 평균: {avg:.4f}, 표준편차: {std:.4f}, 편차: {((avg-expected)/expected*100):+.2f}%")
        print(f"    분포: {dict(sorted(dist.items()))}")
        for k in sorted(dist.keys()):
            pct = dist[k] / total_draws * 100
            print(f"      {k}개: {dist[k]}회 ({pct:.1f}%)")


def analyze_odd_even_pattern(data):
    """홀수/짝수 패턴 분석"""
    print("\n" + "="*60)
    print("[분석 9] 홀수/짝수 비율 패턴")
    print("="*60)

    total = len(data)
    odd_dist = Counter()
    for d in data:
        odd_cnt = sum(1 for n in d['numbers'] if n % 2 == 1)
        odd_dist[odd_cnt] += 1

    # 이론값: 홀수 23개, 짝수 22개 중 6개 선택 (하이퍼지오메트릭)
    # P(X=k) = C(23,k)*C(22,6-k)/C(45,6)
    import math
    def comb(n, r):
        if r < 0 or r > n:
            return 0
        return math.comb(n, r)

    total_comb = comb(45, 6)
    print("  홀수 개수 분포 (홀수 23개, 짝수 22개 중 6개 선택):")
    print(f"  {'홀수수':>6} | {'실제':>6} {'실제%':>7} | {'이론%':>7} | {'편차':>7}")
    print("  " + "-"*45)
    for k in range(7):
        actual = odd_dist.get(k, 0)
        actual_pct = actual / total * 100
        theory_prob = comb(23, k) * comb(22, 6 - k) / total_comb * 100
        dev = actual_pct - theory_prob
        print(f"  홀수 {k}개: {actual:5d}회 ({actual_pct:6.2f}%) | 이론:{theory_prob:6.2f}% | 편차:{dev:+6.2f}%")


def analyze_prime_composite(data):
    """소수/합성수 패턴 분석"""
    print("\n" + "="*60)
    print("[분석 10] 소수/합성수 분포")
    print("="*60)

    primes_in_range = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
    # 1-45 중 소수: 14개, 비소수(1 포함): 31개

    total = len(data)
    prime_dist = Counter()
    for d in data:
        prime_cnt = sum(1 for n in d['numbers'] if n in primes_in_range)
        prime_dist[prime_cnt] += 1

    import math
    def comb(n, r):
        if r < 0 or r > n: return 0
        return math.comb(n, r)

    total_comb = comb(45, 6)
    n_primes = 14
    n_composites = 31

    print(f"  1-45 중 소수: {n_primes}개, 비소수: {n_composites}개")
    print(f"  {'소수수':>6} | {'실제':>6} {'실제%':>7} | {'이론%':>7} | {'편차':>7}")
    print("  " + "-"*45)
    for k in range(7):
        actual = prime_dist.get(k, 0)
        actual_pct = actual / total * 100
        theory_prob = comb(n_primes, k) * comb(n_composites, 6 - k) / total_comb * 100
        dev = actual_pct - theory_prob
        print(f"  소수 {k}개: {actual:5d}회 ({actual_pct:6.2f}%) | 이론:{theory_prob:6.2f}% | 편차:{dev:+6.2f}%")


def analyze_consecutive_numbers(data):
    """연속 번호 포함 패턴"""
    print("\n" + "="*60)
    print("[분석 11] 연속 번호 포함 패턴")
    print("="*60)

    total = len(data)
    consec_dist = Counter()
    max_consec_dist = Counter()

    for d in data:
        nums = sorted(d['numbers'])
        # 연속 번호 쌍 수 계산
        consec_pairs = sum(1 for i in range(len(nums) - 1) if nums[i + 1] - nums[i] == 1)
        consec_dist[consec_pairs] += 1

        # 최장 연속 구간
        max_run = 1
        cur_run = 1
        for i in range(1, len(nums)):
            if nums[i] - nums[i - 1] == 1:
                cur_run += 1
                max_run = max(max_run, cur_run)
            else:
                cur_run = 1
        max_consec_dist[max_run] += 1

    print("  연속 번호 쌍 수 분포:")
    for k in sorted(consec_dist.keys()):
        pct = consec_dist[k] / total * 100
        print(f"    연속쌍 {k}개: {consec_dist[k]}회 ({pct:.1f}%)")

    print("\n  최장 연속 구간 분포:")
    for k in sorted(max_consec_dist.keys()):
        pct = max_consec_dist[k] / total * 100
        print(f"    최장연속 {k}개: {max_consec_dist[k]}회 ({pct:.1f}%)")

    # 연속 번호 없는 회차 비율
    no_consec = consec_dist.get(0, 0)
    print(f"\n  연속 번호 없는 회차: {no_consec}회 ({no_consec/total*100:.1f}%)")
    print(f"  연속 번호 있는 회차: {total-no_consec}회 ({(total-no_consec)/total*100:.1f}%)")


def analyze_gap_patterns(data):
    """번호 간격 패턴 분석"""
    print("\n" + "="*60)
    print("[분석 12] 최대 간격(Max Gap) 및 번호 간격 분포")
    print("="*60)

    total = len(data)
    max_gaps = []
    avg_gaps = []
    all_gaps = []

    for d in data:
        nums = sorted(d['numbers'])
        gaps = [nums[i + 1] - nums[i] for i in range(len(nums) - 1)]
        # 양 끝 포함 (1부터 시작, 45까지)
        extended_gaps = [nums[0] - 1] + gaps + [45 - nums[-1]]
        max_gaps.append(max(gaps))
        avg_gaps.append(statistics.mean(gaps))
        all_gaps.extend(gaps)

    gap_dist = Counter(max_gaps)
    print(f"  최대 간격 평균: {statistics.mean(max_gaps):.3f}")
    print(f"  최대 간격 분포 (상위):")
    for k in sorted(gap_dist.keys()):
        pct = gap_dist[k] / total * 100
        if pct > 0.5:
            print(f"    최대간격 {k}: {gap_dist[k]}회 ({pct:.1f}%)")

    gap_counter = Counter(all_gaps)
    print(f"\n  전체 인접 번호 간격 분포 (총 {len(all_gaps)}개 간격):")
    for k in sorted(gap_counter.keys())[:20]:
        pct = gap_counter[k] / len(all_gaps) * 100
        print(f"    간격 {k:2d}: {gap_counter[k]}회 ({pct:.1f}%)")


def analyze_digit_sum_last_digit(data):
    """자릿수 합 및 끝자리 패턴"""
    print("\n" + "="*60)
    print("[분석 13] 자릿수 합 및 끝자리(일의 자리) 패턴")
    print("="*60)

    total = len(data)

    # 자릿수 합
    digit_sums = []
    for d in data:
        ds = sum(int(c) for n in d['numbers'] for c in str(n))
        digit_sums.append(ds)

    print(f"  자릿수 합 평균: {statistics.mean(digit_sums):.2f}")
    print(f"  자릿수 합 범위: {min(digit_sums)} ~ {max(digit_sums)}")
    ds_dist = Counter(digit_sums)
    print(f"  자릿수 합 분포 (빈도 상위):")
    for k, cnt in sorted(ds_dist.items(), key=lambda x: -x[1])[:15]:
        pct = cnt / total * 100
        print(f"    자릿수합 {k:2d}: {cnt}회 ({pct:.1f}%)")

    # 끝자리 분포
    print(f"\n  끝자리(일의 자리) 분포:")
    last_digits = []
    for d in data:
        for n in d['numbers']:
            last_digits.append(n % 10)
    ld_dist = Counter(last_digits)
    expected_ld = len(last_digits) / 10
    for digit in range(10):
        cnt = ld_dist.get(digit, 0)
        dev = (cnt - expected_ld) / expected_ld * 100
        print(f"    끝자리 {digit}: {cnt}회 ({cnt/len(last_digits)*100:.2f}%, 기대대비 {dev:+.1f}%)")

    # 끝자리 겹침 (같은 끝자리 번호 수)
    print(f"\n  동일 끝자리 번호 수 분포:")
    same_last_dist = Counter()
    for d in data:
        ld = [n % 10 for n in d['numbers']]
        max_same = max(Counter(ld).values())
        same_last_dist[max_same] += 1
    for k in sorted(same_last_dist.keys()):
        pct = same_last_dist[k] / total * 100
        print(f"    최대 같은 끝자리 {k}개: {same_last_dist[k]}회 ({pct:.1f}%)")


def analyze_bonus_number(data):
    """보너스 번호 패턴 분석"""
    print("\n" + "="*60)
    print("[분석 14] 보너스 번호 패턴")
    print("="*60)

    bonus_data = [d for d in data if d['bonus'] is not None]
    total = len(bonus_data)
    print(f"  보너스 번호 있는 회차: {total}개")

    bonuses = [d['bonus'] for d in bonus_data]
    freq = Counter(bonuses)
    expected = total / 45

    print(f"\n  보너스 번호 출현 빈도 (기대: {expected:.2f}회):")
    for num in range(1, 46):
        cnt = freq.get(num, 0)
        dev = (cnt - expected) / expected * 100
        if abs(dev) > 20:
            print(f"    번호 {num:2d}: {cnt}회 (기대대비 {dev:+.1f}%)")

    print("\n  보너스 번호 상위 15:")
    for num, cnt in freq.most_common(15):
        dev = (cnt - expected) / expected * 100
        print(f"    번호 {num:2d}: {cnt}회 ({dev:+.1f}%)")

    # 보너스가 당첨번호에 인접한 경우
    adjacent_count = 0
    for d in bonus_data:
        b = d['bonus']
        nums = d['numbers']
        if any(abs(b - n) == 1 for n in nums):
            adjacent_count += 1
    expected_adj = total * (1 - (39/45) * (38/44) * (37/43) * (36/42) * (35/41) * (34/40))
    print(f"\n  보너스가 당첨번호에 인접(차이1)한 회차: {adjacent_count}회 ({adjacent_count/total*100:.1f}%)")

    # 보너스와 당첨번호 1번의 차이 분포
    diff_dist = Counter()
    for d in bonus_data:
        b = d['bonus']
        diffs = [abs(b - n) for n in d['numbers']]
        diff_dist[min(diffs)] += 1

    print("  보너스와 가장 가까운 당첨번호와의 거리 분포:")
    for k in sorted(diff_dist.keys())[:15]:
        pct = diff_dist[k] / total * 100
        print(f"    거리 {k:2d}: {diff_dist[k]}회 ({pct:.1f}%)")


def analyze_winning_prize_correlation(data):
    """당첨번호 합계와 1등 인원 수 상관관계"""
    print("\n" + "="*60)
    print("[분석 15] 당첨번호 합계와 1등 인원 수 상관관계")
    print("="*60)

    db_path = os.path.join(PROJECT_ROOT, 'data', 'lotto_numbers.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.round, l.numbers, s.first_winners, s.first_prize
        FROM lotto_numbers l
        LEFT JOIN lotto_statistics s ON l.round = s.round
        WHERE s.first_winners IS NOT NULL AND s.first_winners > 0
        ORDER BY l.round
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"  1등 인원 있는 회차: {len(rows)}개")

    sums_winners = []
    for row in rows:
        nums = sorted([int(x) for x in row[1].split(',')])
        s = sum(nums)
        w = row[2]
        p = row[3]
        sums_winners.append((s, w, p))

    # 합계 구간별 1등 평균 인원
    bins = [(80, 120), (120, 140), (140, 160), (160, 180), (180, 230)]
    print("\n  합계 구간별 1등 평균 인원 및 평균 1인당 당첨금:")
    for lo, hi in bins:
        subset = [(s, w, p) for s, w, p in sums_winners if lo <= s < hi]
        if subset:
            avg_w = statistics.mean([x[1] for x in subset])
            avg_p_per_w = statistics.mean([x[2] / x[1] for x in subset if x[1] > 0])
            print(f"    합계 [{lo}-{hi}): n={len(subset)}, 1등 평균인원={avg_w:.2f}명, 1인당평균={avg_p_per_w/1e8:.2f}억")

    # 1등 인원 분포
    winners_dist = Counter([w for _, w, _ in sums_winners])
    print("\n  1등 인원 분포:")
    for k in sorted(winners_dist.keys())[:15]:
        pct = winners_dist[k] / len(sums_winners) * 100
        print(f"    1등 {k:2d}명: {winners_dist[k]}회 ({pct:.1f}%)")


def analyze_trend(data):
    """최근 추세 분석 - 마지막 50/100회 vs 전체"""
    print("\n" + "="*60)
    print("[분석 16] 최근 추세 분석")
    print("="*60)

    periods = [
        ("전체", data),
        ("최근 200회", data[-200:]),
        ("최근 100회", data[-100:]),
        ("최근 50회", data[-50:]),
        ("최근 20회", data[-20:]),
    ]

    for period_name, period_data in periods:
        sums = [sum(d['numbers']) for d in period_data]
        odd_avgs = [sum(1 for n in d['numbers'] if n % 2 == 1) for d in period_data]
        avg_sum = statistics.mean(sums)
        avg_odd = statistics.mean(odd_avgs)
        print(f"  {period_name} (n={len(period_data)}): 합계평균={avg_sum:.2f}, 홀수평균={avg_odd:.2f}")

    # 최근 20회 핫 번호
    recent_20 = []
    for d in data[-20:]:
        recent_20.extend(d['numbers'])
    hot_20 = Counter(recent_20).most_common(15)
    cold_20 = Counter(recent_20).most_common()[-15:]

    print(f"\n  최근 20회 핫 번호 (상위 15개): {sorted([n for n, _ in hot_20])}")
    print(f"  최근 20회 콜드 번호 (하위 15개): {sorted([n for n, _ in cold_20])}")

    # 현재 미출현 번호 (마지막 5회 기준)
    last_5_nums = set()
    for d in data[-5:]:
        last_5_nums.update(d['numbers'])
    not_in_last_5 = sorted(set(range(1, 46)) - last_5_nums)
    print(f"\n  최근 5회 미출현 번호 ({len(not_in_last_5)}개): {not_in_last_5}")

    # 현재 미출현 번호 (마지막 10회 기준)
    last_10_nums = set()
    for d in data[-10:]:
        last_10_nums.update(d['numbers'])
    not_in_last_10 = sorted(set(range(1, 46)) - last_10_nums)
    print(f"  최근 10회 미출현 번호 ({len(not_in_last_10)}개): {not_in_last_10}")

    # 각 번호별 마지막 출현 이후 경과 회차
    print(f"\n  현재 기준 각 번호별 미출현 경과 회차:")
    last_round = data[-1]['round']
    last_seen_round = {n: 0 for n in range(1, 46)}
    for d in data:
        for n in d['numbers']:
            last_seen_round[n] = d['round']

    absence_list = []
    for n in range(1, 46):
        absence = last_round - last_seen_round[n]
        absence_list.append((n, absence, last_seen_round[n]))

    absence_list.sort(key=lambda x: -x[1])
    print(f"  {'번호':>4} | {'미출현':>5} | {'마지막출현':>6}")
    print("  " + "-"*25)
    for n, absence, last in absence_list[:20]:
        print(f"  {n:4d} | {absence:5d}회 | {last:6d}회차")


def main():
    print("=== 로또 당첨번호 다차원 패턴 분석 ===")
    print(f"실행 시간: {datetime.now()}")
    print(f"DB 경로: {DB_PATH}")

    data = load_winning_numbers()
    if not data:
        print("[ERROR] 데이터 로드 실패!")
        return

    print(f"\n[데이터] 총 {len(data)}회차 로드")
    print(f"  첫 회차: {data[0]['round']}회 - {data[0]['numbers']} (보너스: {data[0]['bonus']}) / {data[0]['date']}")
    print(f"  마지막 회차: {data[-1]['round']}회 - {data[-1]['numbers']} (보너스: {data[-1]['bonus']}) / {data[-1]['date']}")

    freq = analyze_number_frequency(data)
    absence_prob, sig_absence = analyze_consecutive_absence(data)
    analyze_previous_round_correlation(data)
    analyze_sum_distribution(data)
    analyze_date_correlation(data)
    analyze_hot_cold_numbers(data, window=10)
    analyze_hot_cold_numbers(data, window=20)
    analyze_number_pair_patterns(data)
    analyze_section_patterns(data)
    analyze_odd_even_pattern(data)
    analyze_prime_composite(data)
    analyze_consecutive_numbers(data)
    analyze_gap_patterns(data)
    analyze_digit_sum_last_digit(data)
    analyze_bonus_number(data)
    analyze_winning_prize_correlation(data)
    analyze_trend(data)

    # 최종 요약
    print("\n" + "="*60)
    print("[종합 요약] 핵심 발견 패턴")
    print("="*60)

    # 핫/콜드 번호
    all_nums_flat = []
    for d in data[-20:]:
        all_nums_flat.extend(d['numbers'])
    freq_20 = Counter(all_nums_flat)
    hot_20 = sorted([n for n, _ in freq_20.most_common(15)])
    cold_20 = sorted([n for n, _ in freq_20.most_common()[-15:]])
    print(f"\n1. 최근 20회 핫 번호 (상위 15개): {hot_20}")
    print(f"   최근 20회 콜드 번호 (하위 15개): {cold_20}")

    # 유의미한 미출현 패턴
    print(f"\n2. 유의미한 미출현 패턴 (편차 >2%):")
    for n, prob, dev, total, chi2 in sig_absence:
        tag = "출현 증가" if dev > 0 else "출현 감소"
        print(f"   미출현 {n}회 -> 출현확률 {prob:.2f}% ({tag})")

    # 합계 분포
    sums = [sum(d['numbers']) for d in data]
    print(f"\n3. 합계 분포: 평균={statistics.mean(sums):.2f}, 표준편차={statistics.stdev(sums):.2f}")
    print(f"   권장 합계 범위 (평균+-1sigma): [{statistics.mean(sums)-statistics.stdev(sums):.0f} ~ {statistics.mean(sums)+statistics.stdev(sums):.0f}]")

    print("\n=== 분석 완료 ===")


if __name__ == '__main__':
    main()
