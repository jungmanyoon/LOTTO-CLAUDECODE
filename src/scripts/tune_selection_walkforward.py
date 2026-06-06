# -*- coding: utf-8 -*-
"""
정직한 반복 최적화 루프: 5장 선택 knob 의 walk-forward(out-of-sample) 튜닝

사용자 질문(2026-06-05): "백테스트 결과 안 좋으면 임계값 바꾸고 재백테스트, 최고 결과까지
반복해야 하는 거 아니냐?" -> 맞다. 단 핵심은 '같은 과거에 숫자 오를 때까지'가 아니라
'안 본 미래 구간(walk-forward)'으로 채점해 과적합(노이즈 추종)을 막는 것이다. 본 도구는
선택 knob 그리드를 walk-forward 로 평가하고, baseline(현 production)을 '견고하게' 이기는
설정이 있을 때만 채택을 권고한다(없으면 baseline 유지가 정답).

knob 그리드(작게 유지 -> 다중검정 위험 최소화):
  - K(목표 풀 크기)     : {1.0M, 1.5M(baseline), 2.0M}
  - spread(번호가중 강도): {0.0(균등), 0.25, 0.5(baseline), 0.75}
  (ml_beta 는 ML 신호가 fold 마다 필요 -> ML-in-loop 비용이 커서 본 튜너에서 제외.
   ml_signal=None 으로 두어 그 영향을 배제한다. ml_beta 튜닝은 별도 ML-in-loop 연구로 분리.)

효율: 풀은 (fold, K)에만 의존하므로 fold/K 당 1회만 채점(8.14M)하고, 그 풀 위에서
spread 변형들을 모두 평가한다. baseline=(K=1.5M, spread=0.5).

정직성/과적합 가드:
  - 모든 평가는 train(과거)만으로 풀/가중치를 만들고 holdout(미래)으로 채점(blind).
  - 그리드를 작게 유지하고, 채택은 'baseline 대비 등수적중/mean_bm 이 양(+)이고 paired
    순증이 분명할 때'만 권고. 미미/음수면 baseline 유지(=과적합 회피).

ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import sys
import logging

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.ERROR, format='%(message)s')

from src.core.db_manager import DatabaseManager
from src.core.extremeness_scorer import ExtremenessScorer
from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

# 실험 공용 헬퍼 재사용
from src.scripts.exp_triple_coverage_walkforward import load_weight_params, build_weighted_scorer


def rank_of(m, bonus_match):
    if m == 6:
        return 1
    if m == 5 and bonus_match:
        return 2
    if m == 5:
        return 3
    if m == 4:
        return 4
    if m == 3:
        return 5
    return None


def eval_sets(sets, draw_set, bonus):
    best_m, best_rank = 0, None
    for nums in sets:
        s = set(int(x) for x in nums)
        m = len(s & draw_set)
        r = rank_of(m, (bonus in s) if bonus else False)
        if m > best_m:
            best_m = m
        if r is not None and (best_rank is None or r < best_rank):
            best_rank = r
    return best_m, best_rank


def main():
    FOLDS = int(os.environ.get('TUNE_FOLDS', '6'))
    WINDOW = int(os.environ.get('TUNE_WINDOW', '40'))
    CAND = int(os.environ.get('TUNE_CAND', '30000'))
    SEED = 42
    # env 로 그리드 재정의 가능(확인 재검증용). 예: TUNE_KGRID="1500000,2000000" TUNE_SPREAD="0.5,0.75"
    _kg = os.environ.get('TUNE_KGRID')
    _sg = os.environ.get('TUNE_SPREAD')
    K_GRID = [int(x) for x in _kg.split(',')] if _kg else [1_000_000, 1_500_000, 2_000_000]
    SPREAD_GRID = [float(x) for x in _sg.split(',')] if _sg else [0.0, 0.25, 0.5, 0.75]
    BASE = (1_500_000, 0.5)

    db = DatabaseManager()
    rows = []
    for r, t in db.get_numbers_with_bonus():
        nums = sorted(int(x) for x in t[:6])
        bonus = int(t[6]) if len(t) > 6 and t[6] is not None else None
        rows.append((int(r), nums, bonus))
    rows.sort(key=lambda x: x[0])
    # 완전 독립 구간 재검증용: TUNE_MAXROUND 지정 시 그 회차 이하만 사용(과거 구간 테스트).
    _maxr = os.environ.get('TUNE_MAXROUND')
    if _maxr:
        rows = [r for r in rows if r[0] <= int(_maxr)]
    total = len(rows)
    weight_json = load_weight_params()
    combos = ExtremenessScorer.all_combinations()

    first = max(1, total - FOLDS * WINDOW)
    fold_specs = []
    s = first
    while s + WINDOW <= total:
        fold_specs.append((s, s + WINDOW))
        s += WINDOW

    print('[tune] walk-forward 선택 knob 튜닝 | folds=%d window=%d | K=%s spread=%s'
          % (len(fold_specs), WINDOW, K_GRID, SPREAD_GRID))

    # 결과 누적: cfg(K,spread) -> best_match 리스트, best_rank 리스트
    cfgs = [(K, sp) for K in K_GRID for sp in SPREAD_GRID]
    bm = {c: [] for c in cfgs}
    rk = {c: [] for c in cfgs}

    for fi, (a, b) in enumerate(fold_specs):
        train_rows = rows[:a]
        holdout = rows[a:b]
        train_win = np.array([n for _, n, _ in train_rows], dtype=np.int16)
        train_until = train_rows[-1][0]

        # 번호 가중치는 spread 만 다르므로 fold당 1회 base 신호 재사용 위해 FrequencyAnalyzer 보관
        fa = FrequencyAnalyzer(db)

        for K in K_GRID:
            # (fold, K) 풀 1회 채점
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

            for sp in SPREAD_GRID:
                w = fa.compute_weights(until_round=train_until, spread=sp)
                sel = DiversitySelector(number_weights=w).select(
                    pool_list, num_tickets=5, quality=pool_quality,
                    candidate_sample=CAND, seed=SEED)
                for (_tr, nums, bonus) in holdout:
                    m, r = eval_sets(sel, set(nums), bonus)
                    bm[(K, sp)].append(m)
                    rk[(K, sp)].append(r)
        print('[fold %d] train<=%d holdout %d~%d (n=%d) 완료'
              % (fi, train_until, holdout[0][0], holdout[-1][0], len(holdout)))

    n = len(bm[BASE])
    print('\n========== walk-forward 결과 (n=%d, baseline=K1.5M/spread0.5) ==========' % n)
    base_bm = np.array(bm[BASE], dtype=float)
    base_win = sum(1 for r in rk[BASE] if r is not None)
    print('%-22s %8s %8s %9s %12s' % ('cfg(K,spread)', 'mean_bm', 'P>=3', '등수적중', 'vs base(순증)'))

    def mcnemar_net(base_rk, other_rk):
        # >=3(등수적중) 지표 paired 순증
        b01 = sum(1 for x, y in zip(base_rk, other_rk) if x is None and y is not None)
        b10 = sum(1 for x, y in zip(base_rk, other_rk) if x is not None and y is None)
        return b01 - b10

    ranked = []
    for c in cfgs:
        arr = np.array(bm[c], dtype=float)
        win = sum(1 for r in rk[c] if r is not None)
        net = mcnemar_net(rk[BASE], rk[c])
        tag = ' <= baseline' if c == BASE else ''
        ranked.append((c, arr.mean(), (arr >= 3).mean(), win, net))
        print('%-22s %8.3f %8.3f %6d/%d %+12d%s'
              % ('K%.1fM/sp%.2f' % (c[0] / 1e6, c[1]), arr.mean(), (arr >= 3).mean(),
                 win, n, net, tag))

    # 채택 권고: baseline 대비 mean_bm 와 등수적중 둘 다 개선 + 순증>0 인 cfg 중 최고
    cands = [r for r in ranked if r[0] != BASE and r[1] > base_bm.mean() + 1e-9
             and r[3] > base_win and r[4] > 0]
    print('\n========== 채택 권고 (정직 기준: mean_bm↑ & 등수적중↑ & 순증>0) ==========')
    if cands:
        cands.sort(key=lambda r: (r[4], r[1]), reverse=True)
        best = cands[0]
        print('후보 발견: K%.1fM/spread%.2f (mean_bm %.3f vs base %.3f, 등수적중 %d vs %d, 순증 %+d)'
              % (best[0][0] / 1e6, best[0][1], best[1], base_bm.mean(), best[3], base_win, best[4]))
        print('-> 단, 순증이 작으면(노이즈 의심) 추가 fold 확대 재검증 후 적용 권장.')
    else:
        print('baseline(K1.5M/spread0.5)을 견고하게 이기는 설정 없음 -> baseline 유지가 정답.')
        print('(이것이 과적합을 피한 정직한 결과: 약신호에서 무리한 튜닝은 미래 성능을 해친다.)')


if __name__ == '__main__':
    main()
