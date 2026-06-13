# -*- coding: utf-8 -*-
"""
비모수 꼬리확률 스코어러 정직 검증 - blind walk-forward 5자 비교 (프로토타입 전용)

배경(2026-06-07): 사용자가 "옛 16패턴(명시적 패턴별 제거) 방식을 선호했는데 마할라노비스
극단성 풀로 바뀐 게 안 좋아진 것 같다"고 정확히 지적. 코드/진단으로 확인됨(마할라노비스가
'역사 평균에서 먼 것'을 제거 -> 가장자리 1,45 과잉제거 98.5%, 보존율 19.8%~무작위 18.4%).
사용자 결정: "넷 다 blind 비교 후 데이터로 결정."

본 도구는 '같은 특징 + 같은 역사 꼬리확률 기준'에서 결합 방식만 달리하여 공정 비교한다:
  RANDOM        : 무작위 K개 풀 (기준선, 기대 보존율 = K/N)
  CURRENT       : 현행 production. 마할라노비스거리^2(연속9) + 페널티(이산4). [ExtremenessScorer]
  OLD16(max)    : 옛 16패턴 AND/거부권 재현. S = max_f z_f (어느 한 특징이라도 역사 꼬리면 제거)
  TAIL_SUM      : 비모수 꼬리확률 독립합산. S = sum_f z_f
  TAIL_GROUPMAX : 비모수 꼬리확률 + 상관군 max-aggregation. S = sum_g max_{f in g} z_f (Codex 권장)
  (옵션 TAIL_COPULA: 가우시안 코퓰러 z^T R^-1 z, Gemini 권장. VAL_COPULA=1)

  z_f = -ln(min(p_L,p_U)), p = inclusive 경험 꼬리확률 (Jeffreys 평활). [TailProbabilityScorer]

blind: fold 마다 train_until 이하 당첨번호로만 분포 학습(fit), holdout window 회차로만 평가.
지표:
  1. 당첨 보존율 (primary) - holdout 당첨이 풀(K)에 포함되는 비율. 동일 K -> 직접 비교.
  2. 가장자리 제거율 - 번호1/45/1&45/중앙 제거율 (양끝 과잉제거 해소 확인).
  3. 포트폴리오 - 풀 무작위 5장의 회차당 최고일치 / P(3+적중) (다양성 선택은 모든 풀 공통이라 분리).
통계 가드(Codex+Gemini): 동일 K, primary 1개 고정, McNemar(신 vs 현행 paired), binomial(vs 무작위),
  부트스트랩 CI, 효과크기 임계 Delta>=3%p(SE~1.1%p), 하이퍼파라미터(K/특징/군) 사전 고정.

성능: 8.14M 특징을 1회만 추출해 캐시 -> fold 마다 searchsorted 채점만(빠름). CURRENT 만 마할라
자체 재계산(fold 당 ~16s).

ASCII 출력(Windows), UTF-8, 이모지 금지. production/DB/모델 일절 변경 안 함(읽기 전용 검증).
"""
import os
import sys
import math
import logging

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.db_manager import DatabaseManager
from src.core.extremeness_scorer import ExtremenessScorer
from src.core.tail_probability_scorer import TailProbabilityScorer, EDGE_NUMBERS

TOTAL = 8_145_060


# ----------------------------------------------------------------------
# 특징 캐시 (8.14M 1회 추출 - 조합은 고정이라 train 과 무관)
# ----------------------------------------------------------------------
def build_feature_cache(combos: np.ndarray, names) -> dict:
    """필요한 특징만 (M,) float32 로 1회 추출 후 캐시."""
    feats = TailProbabilityScorer._all_features(combos)  # 전체 dict float64
    return {n: feats[n].astype(np.float32) for n in names}


def print_spearman(feat_cache: dict, names, n_sample: int = 200000, seed: int = 0):
    """전체 조합 균등 샘플에서 특징 간 Spearman 상관 출력 (상관군 사전고정 검증)."""
    from scipy.stats import rankdata
    rng = np.random.RandomState(seed)
    M = len(next(iter(feat_cache.values())))
    idx = rng.choice(M, size=min(n_sample, M), replace=False)
    ranks = np.vstack([rankdata(feat_cache[n][idx].astype(np.float64)) for n in names])
    R = np.corrcoef(ranks)
    print('[Spearman 상관 |rho| (전체조합 %d 샘플)] 군집 사전고정 검증용' % len(idx))
    head = '            ' + ' '.join('%6s' % n[:6] for n in names)
    print(head)
    for i, n in enumerate(names):
        row = ' '.join('%6.2f' % abs(R[i, j]) for j in range(len(names)))
        print('  %-10s %s' % (n[:10], row))
    print('  (|rho|>=0.65 면 같은 상관군 후보)')
    print('-' * 72)


# ----------------------------------------------------------------------
# 보존율 (동점 공정 처리)
# ----------------------------------------------------------------------
def preservation_prob(sc_sorted: np.ndarray, vals: np.ndarray, K: int) -> np.ndarray:
    """각 당첨 조합 점수 v 가 '하위 K개 풀'에 들 기대 보존확률 [0,1].

    동점 처리(핵심): TAIL/OLD16 의 z=-log(이산 꼬리확률)은 동점이 많다. 단순 (v<=cut) 은
    동점 시 풀이 K 를 초과해 보존율을 부풀린다(마할라노비스는 연속이라 영향 적음 -> 불공정).
    정확히: lo=#{sc<v}, hi=#{sc<=v}.
      - hi<=K  : 동점그룹 전체가 K 안 -> 보존 1
      - lo>=K  : 동점그룹 전체가 K 밖 -> 보존 0
      - 그 외  : 경계에 걸침 -> (K-lo)/(hi-lo) (그룹 중 K 채우는 비율 = 기대 포함확률)
    모든 방식에 동일 규칙 -> 공정. (RANDOM 은 정확히 K 풀이라 베르누이 q 로 별도.)"""
    lo = np.searchsorted(sc_sorted, vals, side='left').astype(np.float64)
    hi = np.searchsorted(sc_sorted, vals, side='right').astype(np.float64)
    out = np.zeros(len(vals), dtype=np.float64)
    out[hi <= K] = 1.0
    mid = (lo < K) & (hi > K)
    out[mid] = (K - lo[mid]) / (hi[mid] - lo[mid])
    return out


# ----------------------------------------------------------------------
# 통계
# ----------------------------------------------------------------------
def mcnemar(new_pres, old_pres):
    """paired 보존 indicator -> McNemar (연속성보정). 반환 (b, c, chi2, p_approx).
    보존확률(0~1)은 0.5 임계로 이진화(동점 경계는 드물어 영향 미미)."""
    new_pres = np.asarray(new_pres, dtype=float) >= 0.5
    old_pres = np.asarray(old_pres, dtype=float) >= 0.5
    b = int(np.sum(new_pres & ~old_pres))   # 신만 보존
    c = int(np.sum(~new_pres & old_pres))   # 현행만 보존
    if b + c == 0:
        return b, c, 0.0, 1.0
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    # 자유도1 카이제곱 생존함수 근사 (정규 근사: p = erfc(sqrt(chi2/2)))
    p = math.erfc(math.sqrt(chi2 / 2.0))
    return b, c, chi2, p


def binom_z(p_hat, n, q):
    """보존율 p_hat (n회) 가 기대 q 와 다른지 정규근사 z, p."""
    if n == 0 or q <= 0 or q >= 1:
        return 0.0, 1.0
    se = math.sqrt(q * (1 - q) / n)
    z = (p_hat - q) / se
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return z, p


def bootstrap_ci(indicator, n_boot=2000, seed=7):
    """per-draw 보존 indicator -> 평균의 95% 부트스트랩 CI."""
    arr = np.asarray(indicator, dtype=float)
    n = len(arr)
    if n == 0:
        return (0.0, 0.0)
    rng = np.random.RandomState(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = arr[rng.randint(0, n, n)].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# ----------------------------------------------------------------------
# 메인
# ----------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.ERROR, format='%(message)s')
    folds = int(os.environ.get('VAL_FOLDS', '6'))
    window = int(os.environ.get('VAL_WINDOW', '40'))
    K = int(os.environ.get('VAL_K', '1500000'))
    do_portfolio = os.environ.get('VAL_PORTFOLIO', '1') != '0'
    do_copula = os.environ.get('VAL_COPULA', '0') != '0'
    n_sets = int(os.environ.get('VAL_SETS', '5'))

    db = DatabaseManager()
    rows = []
    for r, t in db.get_numbers_with_bonus():
        nums = sorted(int(x) for x in t[:6])
        bonus = int(t[6]) if len(t) > 6 and t[6] is not None else None
        rows.append((int(r), nums, bonus))
    rows.sort(key=lambda x: x[0])
    total = len(rows)

    first = max(1, total - folds * window)
    specs = []
    s = first
    while s + window <= total:
        specs.append((s, s + window))
        s += window
    if not specs:
        print('[검증] 데이터 부족')
        return

    combos = ExtremenessScorer.all_combinations()
    q = K / TOTAL

    # 특징 캐시 (TAIL 계열 공유)
    tail_names = list(TailProbabilityScorer.FEATURE_SET)
    print('[검증] 8.14M 특징 캐시 추출 중 (1회)...')
    feat_cache = build_feature_cache(combos, tail_names)
    print('[검증] 특징 캐시 완료: %d특징 x %dM' % (len(tail_names), TOTAL // 1_000_000))
    print('=' * 72)
    print_spearman(feat_cache, tail_names)

    # 비교 방식 정의
    tail_modes = [('OLD16(max)', 'max'), ('TAIL_SUM', 'sum'), ('TAIL_GROUPMAX', 'group_max')]
    if do_copula:
        tail_modes.append(('TAIL_COPULA', 'copula'))
    methods = ['RANDOM', 'CURRENT'] + [m[0] for m in tail_modes]

    # 누적기
    pres = {m: [] for m in methods}          # per-draw 보존 indicator
    edge = {m: {'all': [], 'n1': [], 'n45': [], 'both': [], 'mid': []} for m in methods}
    port_best = {m: [] for m in methods}     # 회차당 최고일치
    port_has3 = {m: [] for m in methods}     # 회차당 3+ 적중여부

    rng_global = np.random.RandomState(2026)

    # 가장자리 마스크 (8.14M, 1회)
    has1 = (combos == 1).any(axis=1)
    has45 = (combos == 45).any(axis=1)
    both = has1 & has45
    mid = ~(((combos <= 3) | (combos >= 43)).any(axis=1))

    def edge_rates(pool_mask):
        removed = ~pool_mask
        return {
            'all': float(removed.mean()),
            'n1': float(removed[has1].mean()),
            'n45': float(removed[has45].mean()),
            'both': float(removed[both].mean()),
            'mid': float(removed[mid].mean()),
        }

    def eval_portfolio(pool_idx, holdout, rng):
        """풀에서 무작위 n_sets 장 (회차마다 다시 뽑지 않고 fold당 1세트) -> holdout 평가."""
        pick = rng.choice(len(pool_idx), size=n_sets, replace=False)
        sets = [set(int(x) for x in combos[pool_idx[p]]) for p in pick]
        for (_r, nums, _b) in holdout:
            win = set(nums)
            ms = [len(st & win) for st in sets]
            port_best_local.append(max(ms))
            port_has3_local.append(1 if max(ms) >= 3 else 0)

    for fi, (a, b) in enumerate(specs):
        train_until = rows[a - 1][0]
        holdout = rows[a:b]
        W = np.array([h[1] for h in holdout], dtype=np.int16)

        # ---- CURRENT (마할라노비스) ----
        es = ExtremenessScorer(db)
        es.fit_until(train_until)
        sc = es.score(combos)
        pool_idx = ExtremenessScorer.select_pool(sc, K)   # 정확히 K개
        pool_mask = np.zeros(TOTAL, dtype=bool)
        pool_mask[pool_idx] = True
        sc_sorted = np.sort(sc)
        wsc = es.score(W)
        wp = preservation_prob(sc_sorted, wsc, K)          # 동점 공정 보존확률
        pres['CURRENT'].extend(float(x) for x in wp)
        er = edge_rates(pool_mask)
        for k2 in edge['CURRENT']:
            edge['CURRENT'][k2].append(er[k2])
        if do_portfolio:
            port_best_local, port_has3_local = [], []
            eval_portfolio(pool_idx, holdout, np.random.RandomState(100 + fi))
            port_best['CURRENT'].extend(port_best_local)
            port_has3['CURRENT'].extend(port_has3_local)

        # ---- TAIL 계열 (특징 캐시 공유) ----
        for label, mode in tail_modes:
            ts = TailProbabilityScorer(db, mode=mode)
            ts.fit_until(train_until)
            sc = ts._score_chunk(feat_cache)  # 8.14M (캐시 특징)
            pool_idx = TailProbabilityScorer.select_pool(sc, K)   # 정확히 K개
            pool_mask = np.zeros(TOTAL, dtype=bool)
            pool_mask[pool_idx] = True
            sc_sorted = np.sort(sc)
            wfeat = TailProbabilityScorer._all_features(W)
            wsc = ts._score_chunk({n: wfeat[n] for n in tail_names})
            wp = preservation_prob(sc_sorted, wsc, K)
            pres[label].extend(float(x) for x in wp)
            er = edge_rates(pool_mask)
            for k2 in edge[label]:
                edge[label][k2].append(er[k2])
            if do_portfolio:
                port_best_local, port_has3_local = [], []
                eval_portfolio(pool_idx, holdout, np.random.RandomState(100 + fi))
                port_best[label].extend(port_best_local)
                port_has3[label].extend(port_has3_local)

        # ---- RANDOM (무작위 K 풀) ----
        rpick = rng_global.choice(TOTAL, size=K, replace=False)
        rmask = np.zeros(TOTAL, dtype=bool)
        rmask[rpick] = True
        # 보존: holdout 당첨이 무작위 풀에 포함? (당첨조합 인덱스 검색은 비싸므로 기대확률 사용 + 실제 1샘플)
        # 실제: 각 당첨조합이 무작위 K 풀에 있을 확률 = K/N. per-draw 베르누이 샘플.
        rp = (rng_global.random(len(holdout)) < q)
        pres['RANDOM'].extend(bool(x) for x in rp)
        er = edge_rates(rmask)
        for k2 in edge['RANDOM']:
            edge['RANDOM'][k2].append(er[k2])
        if do_portfolio:
            port_best_local, port_has3_local = [], []
            eval_portfolio(np.flatnonzero(rmask), holdout, np.random.RandomState(100 + fi))
            port_best['RANDOM'].extend(port_best_local)
            port_has3['RANDOM'].extend(port_has3_local)

        print('[fold %d/%d] train<=%d, holdout %d회차 채점완료'
              % (fi + 1, len(specs), train_until, len(holdout)))

    n = len(pres['CURRENT'])
    print('=' * 72)
    print('[검증결과] blind walk-forward | folds=%d window=%d K=%d | 평가회차 n=%d'
          % (len(specs), window, K, n))
    print('  (기대 무작위 보존율 q=K/N=%.4f)' % q)
    print('-' * 72)

    # 1) 당첨 보존율 (primary)
    print('[1] 당첨 보존율 (primary) - 높을수록 좋음. 동일 K=%d' % K)
    print('  %-14s %8s  %16s   %s' % ('method', '보존율', '95%CI', 'vs무작위(z,p)'))
    base = np.mean(pres['CURRENT'])
    summary = {}
    for m in methods:
        ind = pres[m]
        pr = float(np.mean(ind))
        lo, hi = bootstrap_ci(ind)
        z, p = binom_z(pr, len(ind), q)
        summary[m] = pr
        print('  %-14s %7.1f%%  [%5.1f%%,%5.1f%%]   z=%+.2f p=%.3f'
              % (m, pr * 100, lo * 100, hi * 100, z, p))
    print('-' * 72)

    # McNemar: 각 TAIL/OLD16 vs CURRENT
    print('[1b] McNemar (신규 vs 현행 CURRENT, paired 보존 indicator)')
    for label, _mode in tail_modes:
        bb, cc, chi2, p = mcnemar(pres[label], pres['CURRENT'])
        delta = (summary[label] - summary['CURRENT']) * 100
        print('  %-14s vs CURRENT: 보존율차 %+.1f%%p | 신만보존 b=%d, 현행만 c=%d, chi2=%.2f, p=%.3f'
              % (label, delta, bb, cc, chi2, p))
    print('-' * 72)

    # 2) 가장자리 제거율
    print('[2] 가장자리 제거율 (전체 / 번호1 / 번호45 / 1&45 / 중앙) - 양끝 과잉제거 해소 확인')
    print('  %-14s %8s %8s %8s %8s %8s' % ('method', '전체', '번호1', '번호45', '1&45', '중앙'))
    for m in methods:
        e = {k2: float(np.mean(v)) for k2, v in edge[m].items()}
        print('  %-14s %7.1f%% %7.1f%% %7.1f%% %7.1f%% %7.1f%%'
              % (m, e['all'] * 100, e['n1'] * 100, e['n45'] * 100, e['both'] * 100, e['mid'] * 100))
    print('  (이상적: 번호1/45/1&45 가 전체에 수렴. CURRENT는 1&45가 전체보다 크게 높음=과잉제거)')
    print('-' * 72)

    # 3) 포트폴리오
    if do_portfolio:
        print('[3] 포트폴리오 (풀 무작위 %d장, 회차당) - mean best-match / P(회차 3+적중)' % n_sets)
        print('  %-14s %16s %16s' % ('method', 'mean_best', 'P(3+회차)'))
        for m in methods:
            mb = float(np.mean(port_best[m])) if port_best[m] else 0.0
            h3 = float(np.mean(port_has3[m])) if port_has3[m] else 0.0
            print('  %-14s %15.3f %15.1f%%' % (m, mb, h3 * 100))
        print('-' * 72)

    # 판정 보조
    print('[판정 보조] primary=당첨보존율, 효과크기 임계 Delta>=3%%p, SE~%.1f%%p'
          % (math.sqrt(q * (1 - q) / max(n, 1)) * 100))
    best_method = max(methods, key=lambda m: summary[m])
    print('  최고 보존율: %s (%.1f%%). CURRENT=%.1f%%, RANDOM=%.1f%%'
          % (best_method, summary[best_method] * 100,
             summary['CURRENT'] * 100, summary['RANDOM'] * 100))
    print('  주의: 본 구간은 2026-06-07 진단을 보고 설계됨 -> 완전 blind 아님. 동결 후 미래가 최종근거.')
    print('=' * 72)


if __name__ == '__main__':
    main()
