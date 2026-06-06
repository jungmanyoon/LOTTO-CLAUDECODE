# -*- coding: utf-8 -*-
"""
실험: 5장 선택 목적함수 walk-forward A/B (production 무수정)

목적(사용자 전략 정합): "어떤 티켓이든 3개+ 맞추기"(하위등수 적중) 기대를 올리는
5장 선택 방식을 정직하게 비교한다. 극단성 풀(K=1.5M) 형성은 동일하게 두고,
'선택 목적함수/번호가중치'만 바꿔 같은 train/풀에서 공정 비교(paired)한다.

비교 변형(variant):
  V0_base   : 현 production - DiversitySelector(가중치=freq/recency/cold) 1-cover 최대화
  V1_uniform: DiversitySelector(균등 가중치) 1-cover 최대화         (가중치 ablation)
  V2_triple : 3-tuple(triple) 커버리지 greedy (풀 내 triple 밀도 가중, 겹침<=1)
  V3_tripleU: 3-tuple 커버리지 greedy (균등 triple 가중 = 순수 distinct-triple 수)

검증(정직성):
  - walk-forward: 각 fold는 train=fold 이전 전체, holdout=이후 window회.
    fold마다 ExtremenessScorer를 새로 fit -> 미래정보 누설 차단.
  - 모든 variant가 동일 fold/풀/train 공유 -> 차이는 '선택 방식'에서만 발생(paired).
  - 지표: 각 (fold, holdout 회차)에서 5장 중 best-match. 집계: P(best>=2/3/4),
    평균 best-match. V2/V1을 V0과 McNemar(>=3 지표)로 paired 비교.

주의: 티켓은 fold당 1회 생성되어 window 동안 고정(frozen) -> recency 가중치엔 다소
불리하나, 모든 variant가 동일 조건이라 '선택 방식' 비교는 공정하다. 과적합 가드:
triple 밀도는 '과거 당첨'이 아니라 '생존 풀(1.5M)의 구조'에서만 계산 -> data leakage 없음.

ASCII 출력(Windows), UTF-8 인코딩, 이모지 금지.
"""
import os
import sys
import json
import logging
from itertools import combinations

import numpy as np

# 프로젝트 루트 경로
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.WARNING, format='%(message)s')

from src.core.db_manager import DatabaseManager
from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

# ---- triple 선형 인덱스 (0-based a<b<c -> a*2025 + b*45 + c) ----
TRIPLE_DIM = 45 * 45 * 45
POS_TRIPLES = list(combinations(range(6), 3))  # 6개 중 3개 위치조합 (20개)


def _triple_lin(a, b, c):
    return a * 2025 + b * 45 + c


def build_pool_triple_density(pool_combos: np.ndarray) -> np.ndarray:
    """생존 풀 (P,6) 내 각 triple(a<b<c, 0-based)의 출현 빈도 (TRIPLE_DIM,) float64."""
    density = np.zeros(TRIPLE_DIM, dtype=np.float64)
    p0 = pool_combos.astype(np.int64) - 1  # 0-based
    for (i, j, k) in POS_TRIPLES:
        lin = p0[:, i] * 2025 + p0[:, j] * 45 + p0[:, k]
        np.add.at(density, lin, 1.0)
    # 정규화: 양수 평균 1.0 근처 (스케일 통일)
    pos = density[density > 0]
    if pos.size:
        density = density / pos.mean()
    return density


def combo_triple_lins(combo) -> list:
    """정렬된 6개 번호(1-based) 조합 -> 20개 triple 선형인덱스."""
    s = sorted(int(x) - 1 for x in combo)  # 0-based 정렬
    return [_triple_lin(s[i], s[j], s[k]) for (i, j, k) in POS_TRIPLES]


def triple_coverage_select(pool_list, triple_weight, num_tickets=5,
                           candidate_sample=30000, seed=42,
                           max_pairwise_overlap=1, max_number_repeat=2):
    """3-tuple 커버리지 greedy (submodular, 1-1/e 보장).

    각 단계: 후보 중 '아직 안 덮인 triple의 가중합'이 최대인 조합을 선택.
    제약: 티켓간 겹침<=1, 한 번호 최대 2회 (V0와 동일 제약 -> 목적함수만 차이).
    triple_weight=None 이면 균등(1.0) = 순수 distinct-triple 수 최대화.
    """
    rng = np.random.RandomState(seed)
    n = len(pool_list)
    if n == 0:
        return []
    if n > candidate_sample:
        cand_idx = rng.choice(n, candidate_sample, replace=False)
    else:
        cand_idx = np.arange(n)

    # 후보 triple 인덱스 precompute
    cand_trips = {int(i): combo_triple_lins(pool_list[int(i)]) for i in cand_idx}

    covered = np.zeros(TRIPLE_DIM, dtype=bool)
    selected = []
    number_count = np.zeros(46, dtype=np.int16)

    def weight_of(lin):
        return 1.0 if triple_weight is None else float(triple_weight[lin])

    def feasible(idx):
        combo = pool_list[idx]
        for x in combo:
            if number_count[x] + 1 > max_number_repeat:
                return False
        cs = set(combo)
        for s_idx in selected:
            if len(cs & set(pool_list[s_idx])) > max_pairwise_overlap:
                return False
        return True

    def marginal_gain(idx):
        g = 0.0
        for lin in cand_trips[idx]:
            if not covered[lin]:
                g += weight_of(lin)
        return g

    for _ in range(num_tickets):
        best, best_g = None, -1.0
        relaxed_pool = None
        for idx in cand_idx:
            idx = int(idx)
            if idx in selected:
                continue
            if not feasible(idx):
                continue
            g = marginal_gain(idx)
            if g > best_g:
                best_g, best = g, idx
        if best is None:  # 제약으로 후보 없음 -> 완화
            for idx in cand_idx:
                idx = int(idx)
                if idx in selected:
                    continue
                g = marginal_gain(idx)
                if g > best_g:
                    best_g, best = g, idx
        if best is None:
            break
        selected.append(best)
        for lin in cand_trips[best]:
            covered[lin] = True
        for x in pool_list[best]:
            number_count[x] += 1

    return [tuple(sorted(pool_list[i])) for i in selected]


def best_match(tickets, draw_set):
    """5장 중 draw(6개)와의 최대 일치 수."""
    if not tickets:
        return 0
    return max(len(set(t) & draw_set) for t in tickets)


def load_weight_params():
    path = os.path.join(ROOT, 'configs', 'extremeness_weights.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def build_weighted_scorer(db, weight_json):
    """production과 동일하게 가중 ExtremenessScorer 구성."""
    if weight_json and 'best_params' in weight_json:
        bp = weight_json['best_params']
        pw = {d: bp.get('pw_%s' % d, 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
        scorer = ExtremenessScorer(db, alpha=bp.get('alpha', 0.5), penalty_weights=pw)
        scorer._feature_scale = np.array(
            [bp.get('fw_%s' % f, 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES],
            dtype=np.float32)
        return scorer, True
    return ExtremenessScorer(db), False


def main():
    K = int(os.environ.get('EXP_K', '1500000'))
    FOLDS = int(os.environ.get('EXP_FOLDS', '5'))
    WINDOW = int(os.environ.get('EXP_WINDOW', '40'))
    CAND = int(os.environ.get('EXP_CAND', '30000'))
    SEED = 42

    db = DatabaseManager()
    rows = []
    for r, s, _d in db.get_all_numbers():
        rows.append((int(r), sorted(int(x) for x in s.split(','))))
    rows.sort(key=lambda t: t[0])
    total = len(rows)
    print('[exp] total rounds=%d, K=%d, folds=%d, window=%d, candidate=%d'
          % (total, K, FOLDS, WINDOW, CAND))

    weight_json = load_weight_params()
    combos = ExtremenessScorer.all_combinations()

    # fold 경계: 최근 FOLDS*WINDOW 회차를 오래된 fold부터
    first_holdout = max(1, total - FOLDS * WINDOW)
    fold_specs = []
    s = first_holdout
    while s + WINDOW <= total:
        fold_specs.append((s, s + WINDOW))
        s += WINDOW

    variants = ['V0_base', 'V1_uniform', 'V2_triple', 'V3_tripleU']
    # 각 variant별 best-match 리스트 (모든 fold-holdout 회차)
    bm = {v: [] for v in variants}
    # paired (>=3 indicator) for McNemar: per round
    paired = {v: [] for v in variants}

    for fi, (a, b) in enumerate(fold_specs):
        train_rows = rows[:a]
        holdout_rows = rows[a:b]
        train_win = np.array([nums for _, nums in train_rows], dtype=np.int16)

        # 1) 가중 극단성 풀 (production 동일)
        scorer, weighted = build_weighted_scorer(db, weight_json)
        scorer.fit(train_win)
        if weighted and getattr(scorer, '_feature_scale', None) is not None:
            S = np.diag(scorer._feature_scale).astype(np.float32)
            scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
        scores = scorer.score(combos)
        pool_idx = ExtremenessScorer.select_pool(scores, K)
        pool_combos = combos[pool_idx]
        pool_quality = (-scores[pool_idx]).astype(np.float32)
        pool_list = [tuple(int(x) for x in row) for row in pool_combos]

        # 2) 번호 가중치 (train 기준)
        fa = FrequencyAnalyzer(db)
        train_until = train_rows[-1][0]
        w_weighted = fa.compute_weights(until_round=train_until, spread=0.5)
        w_uniform = np.ones(45, dtype=np.float32)

        # 3) triple 밀도 (생존 풀 구조 - leakage 없음)
        density = build_pool_triple_density(pool_combos)

        # 4) 각 variant 5장 생성 (동일 seed)
        sel_v0 = DiversitySelector(number_weights=w_weighted).select(
            pool_list, num_tickets=5, quality=pool_quality, candidate_sample=CAND, seed=SEED)
        sel_v1 = DiversitySelector(number_weights=w_uniform).select(
            pool_list, num_tickets=5, quality=pool_quality, candidate_sample=CAND, seed=SEED)
        sel_v2 = triple_coverage_select(pool_list, density, num_tickets=5,
                                        candidate_sample=CAND, seed=SEED)
        sel_v3 = triple_coverage_select(pool_list, None, num_tickets=5,
                                        candidate_sample=CAND, seed=SEED)
        sels = {'V0_base': sel_v0, 'V1_uniform': sel_v1,
                'V2_triple': sel_v2, 'V3_tripleU': sel_v3}

        # 진단: 각 variant의 고유 triple 수 / 고유번호 수
        diag = {}
        for v, sel in sels.items():
            cov_trip = set()
            for t in sel:
                cov_trip.update(combo_triple_lins(t))
            uniq_num = len(set(n for t in sel for n in t))
            diag[v] = (len(cov_trip), uniq_num)

        # 5) holdout 평가
        for _r, nums in holdout_rows:
            draw = set(nums)
            for v, sel in sels.items():
                m = best_match(sel, draw)
                bm[v].append(m)
                paired[v].append(1 if m >= 3 else 0)

        print('[fold %d] train<%d holdout %d~%d (n=%d) | uniqTriple/uniqNum: %s'
              % (fi, train_until, holdout_rows[0][0], holdout_rows[-1][0],
                 len(holdout_rows),
                 ', '.join('%s=%d/%d' % (v, diag[v][0], diag[v][1]) for v in variants)))

    # 집계
    print('\n========== 집계 (모든 fold-holdout 회차) ==========')
    n_eval = len(bm['V0_base'])
    print('평가 회차 수 n=%d' % n_eval)
    header = '%-12s %8s %8s %8s %8s' % ('variant', 'mean_bm', 'P(>=2)', 'P(>=3)', 'P(>=4)')
    print(header)
    for v in variants:
        arr = np.array(bm[v])
        print('%-12s %8.3f %8.3f %8.3f %8.3f'
              % (v, arr.mean(), (arr >= 2).mean(), (arr >= 3).mean(), (arr >= 4).mean()))

    # McNemar: V2 vs V0, V1 vs V0 (>=3 지표)
    def mcnemar(base, other):
        base = np.array(base); other = np.array(other)
        b01 = int(((base == 0) & (other == 1)).sum())  # base miss, other hit
        b10 = int(((base == 1) & (other == 0)).sum())  # base hit, other miss
        return b01, b10

    print('\n========== McNemar (>=3 적중 회차, V0 대비) ==========')
    for v in ['V1_uniform', 'V2_triple', 'V3_tripleU']:
        b01, b10 = mcnemar(paired['V0_base'], paired[v])
        net = b01 - b10
        print('%-12s: V0놓침+%s적중=%d, V0적중+%s놓침=%d, 순증=%+d'
              % (v, v, b01, v, b10, net))

    print('\n[해석 가이드] mean_bm/P(>=3)가 V0_base 대비 유의하게 높고 McNemar 순증>0 이면 개선.')


if __name__ == '__main__':
    main()
