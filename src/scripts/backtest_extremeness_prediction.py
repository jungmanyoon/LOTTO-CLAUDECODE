# -*- coding: utf-8 -*-
"""
최종 5세트(극단성 풀 + 다양성) 전용 blind 백테스트 - production-faithful 정식 도구

배경(사용자 의도 2026-06-06): "8.14M에서 극단 제거 -> 1.5M 생존 풀 -> 이 풀로 백테스트/ML
-> 가장 당첨확률 높은 5세트 출력". 기존 run_backtest()는 legacy ML 모델(8.14M 자유예측)을
채점해 '실제 사용자에게 내는 1.5M 풀 5세트'를 검증하지 않는 괴리가 있었다. 본 도구는 그
괴리를 메워, production 클래스 ExtremenessPoolPredictor 를 '그대로' 호출해 blind walk-forward
로 최종 5세트를 검증한다.

설계 합의(Codex gpt-5.5 + Gemini 3.1-pro, 2026-06-06):
  - blind: 각 fold 는 train=fold 시작 직전까지, build_pool(train_until=fold_start-1) -> 미래정보 차단.
  - 비교 기준선: RAND_POOL(같은 풀 무작위 5장 = 다양성 선택의 순수 이득), RAND_ALL(8.14M 전체 무작위).
  - 지표: 등수적중률 P(어떤 티켓 >=3매치), mean best-match, 무작위 대비 lift.
  - ML 은 '자유 예측기'가 아니라 '풀 내부 번호 가중치(tie-breaker)'로만(ml_predictions 주입 시).

ASCII 출력(Windows), UTF-8 인코딩, 이모지 금지.
"""
import os
import sys
import logging
from typing import Optional

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor


def rank_of(match_count, bonus_match):
    """로또 등수(1~5등) - 6:1등, 5+보너스:2등, 5:3등, 4:4등, 3:5등, else None."""
    if match_count == 6:
        return 1
    if match_count == 5 and bonus_match:
        return 2
    if match_count == 5:
        return 3
    if match_count == 4:
        return 4
    if match_count == 3:
        return 5
    return None


def eval_sets(sets, draw_set, bonus):
    """5장 평가 -> (best_match, best_rank). best_rank=가장 높은 등수(숫자 작을수록 높음)."""
    best_m = 0
    best_rank = None
    for nums in sets:
        s = set(int(x) for x in nums)
        m = len(s & draw_set)
        bm = (bonus in s) if bonus else False
        r = rank_of(m, bm)
        if m > best_m:
            best_m = m
        if r is not None and (best_rank is None or r < best_rank):
            best_rank = r
    return best_m, best_rank


def run_pool_selection_backtest(db_manager, folds: int = 5, window: int = 30,
                                K: Optional[int] = None, num_sets: int = 5,
                                ml_predictions=None, seed: int = 42,
                                logger=None) -> dict:
    """1.5M 극단성 풀 -> 5세트 선택의 blind walk-forward 백테스트.

    production 클래스 ExtremenessPoolPredictor 를 그대로 호출(재구현 아님)하여,
    '사용자가 실제 받는 예측'을 검증한다. fold 당 풀을 1회 형성(캐시 재사용)하고 window 회차로 평가.

    반환 dict:
      {n, mean_bm, rank_hit_rate, p4, rand_pool_bm, rand_pool_hit, rand_all_bm, rand_all_hit,
       lift_bm_vs_all, lift_rounds_vs_all, lift_bm_vs_pool, lift_rounds_vs_pool, win_rounds,
       rand_pool_rounds, rand_all_rounds, K, folds, window}
    실패/데이터부족 시 None.
    """
    log = logger or logging.getLogger(__name__)
    rng = np.random.RandomState(seed)

    # [B2-note 2026-06-13] K 미지정(None)이면 production 예측과 '동일하게' 정책(effective_target_K)을
    #  상속한다. 과거엔 1.5M 하드코딩이라, walk-forward 재탐색으로 정책 K가 1.5M에서 이동하면
    #  '사용자가 실제 받는 풀 크기'와 다른 K를 검증하는 desync가 났다. None -> 정책 K로 측정 충실도 확보.
    if K is None:
        K = ExtremenessPoolPredictor(db_manager).target_K
        log.info(f"[풀백테스트] K 미지정 -> 정책 effective_target_K={K:,} 상속(production과 동일)")

    rows = []
    for r, t in db_manager.get_numbers_with_bonus():
        nums = sorted(int(x) for x in t[:6])
        bonus = int(t[6]) if len(t) > 6 and t[6] is not None else None
        rows.append((int(r), nums, bonus))
    rows.sort(key=lambda x: x[0])
    total = len(rows)
    if total < window + 2:
        return None

    first = max(1, total - folds * window)
    fold_specs = []
    s = first
    while s + window <= total:
        fold_specs.append((s, s + window))
        s += window
    if not fold_specs:
        return None

    prod_bm, prod_rank = [], []
    rp_bm, rp_rank = [], []
    ra_bm, ra_rank = [], []

    def random_all_sets():
        return [sorted(rng.choice(range(1, 46), 6, replace=False).tolist()) for _ in range(num_sets)]

    for (a, b) in fold_specs:
        train_until = rows[a - 1][0]
        holdout = rows[a:b]
        try:
            epp = ExtremenessPoolPredictor(db_manager, target_K=K)
            epp.build_pool(train_until=train_until)
            sets = epp.predict(num_sets=num_sets, ml_predictions=ml_predictions, seed=seed)
            prod_sets = [s2['numbers'] for s2 in sets]
            pool = epp._pool_combos
        except Exception as e:
            log.warning(f"[풀백테스트] fold(train<={train_until}) 실패: {e}")
            continue
        for (_tr, nums, bonus) in holdout:
            draw = set(nums)
            m, r = eval_sets(prod_sets, draw, bonus)
            prod_bm.append(m); prod_rank.append(r)
            idx = rng.choice(len(pool), num_sets, replace=False)
            rsets = [sorted(int(x) for x in pool[j]) for j in idx]
            m2, r2 = eval_sets(rsets, draw, bonus)
            rp_bm.append(m2); rp_rank.append(r2)
            m3, r3 = eval_sets(random_all_sets(), draw, bonus)
            ra_bm.append(m3); ra_rank.append(r3)

    n = len(prod_bm)
    if n == 0:
        return None

    def hits(rk):
        return sum(1 for r in rk if r is not None)

    prod_arr = np.array(prod_bm, dtype=float)
    rp_arr = np.array(rp_bm, dtype=float)
    ra_arr = np.array(ra_bm, dtype=float)
    win = hits(prod_rank); rpw = hits(rp_rank); raw = hits(ra_rank)
    return {
        'n': n, 'K': K, 'folds': len(fold_specs), 'window': window,
        'mean_bm': float(prod_arr.mean()),
        'rank_hit_rate': float(win / n),
        'p4': float((prod_arr >= 4).mean()),
        'win_rounds': win,
        'rand_pool_bm': float(rp_arr.mean()), 'rand_pool_hit': float(rpw / n), 'rand_pool_rounds': rpw,
        'rand_all_bm': float(ra_arr.mean()), 'rand_all_hit': float(raw / n), 'rand_all_rounds': raw,
        'lift_bm_vs_all': float(prod_arr.mean() - ra_arr.mean()),
        'lift_rounds_vs_all': int(win - raw),
        'lift_bm_vs_pool': float(prod_arr.mean() - rp_arr.mean()),
        'lift_rounds_vs_pool': int(win - rpw),
    }


def main():
    logging.basicConfig(level=logging.ERROR, format='%(message)s')
    from src.core.db_manager import DatabaseManager
    K = int(os.environ.get('EXP_K', '1500000'))
    FOLDS = int(os.environ.get('EXP_FOLDS', '8'))
    WINDOW = int(os.environ.get('EXP_WINDOW', '40'))
    db = DatabaseManager()
    res = run_pool_selection_backtest(db, folds=FOLDS, window=WINDOW, K=K)
    if not res:
        print('[backtest] 데이터 부족 또는 실패')
        return
    print('[backtest] 최종 5세트 전용 blind walk-forward | K=%d folds=%d window=%d n=%d'
          % (res['K'], res['folds'], res['window'], res['n']))
    print('%-12s | mean_bm=%.3f | 등수적중 %d/%d (%.1f%%)'
          % ('PROD(5세트)', res['mean_bm'], res['win_rounds'], res['n'], res['rank_hit_rate'] * 100))
    print('%-12s | mean_bm=%.3f | 등수적중 %d/%d (%.1f%%)'
          % ('RAND_POOL', res['rand_pool_bm'], res['rand_pool_rounds'], res['n'], res['rand_pool_hit'] * 100))
    print('%-12s | mean_bm=%.3f | 등수적중 %d/%d (%.1f%%)'
          % ('RAND_ALL', res['rand_all_bm'], res['rand_all_rounds'], res['n'], res['rand_all_hit'] * 100))
    print('[lift] PROD vs RAND_ALL : mean_bm %+.3f, 등수적중 %+d회'
          % (res['lift_bm_vs_all'], res['lift_rounds_vs_all']))
    print('[lift] PROD vs RAND_POOL: mean_bm %+.3f, 등수적중 %+d회 (다양성 순수 이득)'
          % (res['lift_bm_vs_pool'], res['lift_rounds_vs_pool']))


if __name__ == '__main__':
    main()
