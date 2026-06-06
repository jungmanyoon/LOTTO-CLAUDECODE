# -*- coding: utf-8 -*-
"""
최종 5세트(극단성 풀 + 다양성) 전용 blind 백테스트 - production-faithful 정식 도구

배경(사용자 검증 요청 2026-06-05): 기존 run_backtest()는 ML 모델(LSTM/앙상블/MC)을
검증하지, 사용자가 실제로 받는 '최종 5세트(극단성 풀 + 다양성 선택)'를 직접 검증하지
않는 갭이 있었다. 본 도구는 그 갭을 메운다.

방법(정직한 blind walk-forward):
  - production 클래스 ExtremenessPoolPredictor 를 '그대로' 호출(재구현 아님)한다.
  - 각 fold 는 train = fold 시작 직전까지의 전체 회차, holdout = 이후 window 회차.
    build_pool(train_until=fold_start-1) -> fold 시작 시점 데이터만으로 풀/가중치 형성
    (미래정보 누설 차단). predict() 로 5세트 생성 후 holdout 실제 당첨번호로 채점.
  - 비교 기준선:
      RAND_POOL : 같은 극단성 풀에서 무작위 5장 (다양성 선택의 순수 이득 측정)
      RAND_ALL  : 8.14M 전체에서 무작위 5장 (풀+다양성 결합 이득 측정)
  - 지표: 5장 중 best-match 평균, P(best>=2/3/4/5), 등수 분포.

주의/정직성:
  - 가중치 파일 configs/extremeness_weights.json 은 전체 데이터로 적합된 현 운영값을
    모든 fold 에 동일 적용한다(=production 동작과 동일). 이는 '특징 스케일' 파라미터일 뿐
    당첨번호 누설이 아니며, 번호가중치(FrequencyAnalyzer)는 train_until 로 blind 처리된다.
  - 티켓은 fold 당 1회 생성되어 window 동안 고정(frozen)된다(per-round 대비 약간 보수적).
    EXP_MODE=perround 로 두면 최근 EXP_RECENT 회차를 매 회차 풀 재형성하여 가장 faithful
    하게 평가한다(느림: 회차당 ~16s).

ASCII 출력(Windows), UTF-8 인코딩, 이모지 금지.
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


def summarize(name, best_matches, best_ranks, n):
    arr = np.array(best_matches, dtype=float)
    p2 = (arr >= 2).mean()
    p3 = (arr >= 3).mean()
    p4 = (arr >= 4).mean()
    p5 = (arr >= 5).mean()
    # 등수 적중 회차 수 (5등 이상=rank<=5 즉 not None)
    win_rounds = sum(1 for r in best_ranks if r is not None)
    print('%-10s | mean_bm=%.3f | P>=2=%.3f P>=3=%.3f P>=4=%.3f P>=5=%.4f | 등수적중 %d/%d (%.1f%%)'
          % (name, arr.mean(), p2, p3, p4, p5, win_rounds, n, 100.0 * win_rounds / n))
    return {'mean_bm': arr.mean(), 'p3': p3, 'win_rounds': win_rounds}


def main():
    K = int(os.environ.get('EXP_K', '1500000'))
    FOLDS = int(os.environ.get('EXP_FOLDS', '8'))
    WINDOW = int(os.environ.get('EXP_WINDOW', '40'))
    MODE = os.environ.get('EXP_MODE', 'fold')   # fold | perround
    RECENT = int(os.environ.get('EXP_RECENT', '30'))
    SEED = 42

    db = DatabaseManager()
    # (round, sorted6, bonus)
    rows = []
    for r, t in db.get_numbers_with_bonus():
        nums = sorted(int(x) for x in t[:6])
        bonus = int(t[6]) if len(t) > 6 and t[6] is not None else None
        rows.append((int(r), nums, bonus))
    rows.sort(key=lambda x: x[0])
    total = len(rows)
    rng = np.random.RandomState(SEED)

    print('[backtest] 최종 5세트 전용 blind walk-forward | rounds=%d K=%d mode=%s'
          % (total, K, MODE))

    prod_bm, prod_rank = [], []
    rp_bm, rp_rank = [], []
    ra_bm, ra_rank = [], []

    # 8.14M 전체 무작위용 (RAND_ALL) - 풀과 무관, 매 평가마다 무작위 5장
    def random_all_sets():
        sets = []
        for _ in range(5):
            sets.append(sorted(rng.choice(range(1, 46), 6, replace=False).tolist()))
        return sets

    if MODE == 'perround':
        targets = [rows[i] for i in range(total - RECENT, total)]
        for (tr, nums, bonus) in targets:
            train_until = tr - 1
            epp = ExtremenessPoolPredictor(db, target_K=K)
            epp.build_pool(train_until=train_until)
            sets = epp.predict(num_sets=5, ml_predictions=None, seed=SEED)
            pool = epp._pool_combos
            draw = set(nums)
            bm, rk = eval_sets([s['numbers'] for s in sets], draw, bonus)
            prod_bm.append(bm); prod_rank.append(rk)
            # RAND_POOL
            idx = rng.choice(len(pool), 5, replace=False)
            rsets = [sorted(int(x) for x in pool[j]) for j in idx]
            bm2, rk2 = eval_sets(rsets, draw, bonus)
            rp_bm.append(bm2); rp_rank.append(rk2)
            # RAND_ALL
            bm3, rk3 = eval_sets(random_all_sets(), draw, bonus)
            ra_bm.append(bm3); ra_rank.append(rk3)
            print('  회차 %d: prod best=%d(rank %s) | randpool=%d | randall=%d'
                  % (tr, bm, rk, bm2, bm3))
    else:
        first_holdout = max(1, total - FOLDS * WINDOW)
        s = first_holdout
        fold_specs = []
        while s + WINDOW <= total:
            fold_specs.append((s, s + WINDOW))
            s += WINDOW
        for fi, (a, b) in enumerate(fold_specs):
            train_until = rows[a - 1][0]  # fold 시작 직전 회차
            holdout = rows[a:b]
            epp = ExtremenessPoolPredictor(db, target_K=K)
            epp.build_pool(train_until=train_until)
            sets = epp.predict(num_sets=5, ml_predictions=None, seed=SEED)
            prod_sets = [s2['numbers'] for s2 in sets]
            pool = epp._pool_combos
            for (tr, nums, bonus) in holdout:
                draw = set(nums)
                bm, rk = eval_sets(prod_sets, draw, bonus)
                prod_bm.append(bm); prod_rank.append(rk)
                idx = rng.choice(len(pool), 5, replace=False)
                rsets = [sorted(int(x) for x in pool[j]) for j in idx]
                bm2, rk2 = eval_sets(rsets, draw, bonus)
                rp_bm.append(bm2); rp_rank.append(rk2)
                bm3, rk3 = eval_sets(random_all_sets(), draw, bonus)
                ra_bm.append(bm3); ra_rank.append(rk3)
            print('[fold %d] train<=%d holdout %d~%d (n=%d)'
                  % (fi, train_until, holdout[0][0], holdout[-1][0], len(holdout)))

    n = len(prod_bm)
    print('\n========== 집계 (n=%d 평가 회차) ==========' % n)
    p = summarize('PROD(5세트)', prod_bm, prod_rank, n)
    rp = summarize('RAND_POOL', rp_bm, rp_rank, n)
    ra = summarize('RAND_ALL', ra_bm, ra_rank, n)
    print('\n[lift] PROD vs RAND_ALL  : mean_bm %+.3f, 등수적중 %+d회'
          % (p['mean_bm'] - ra['mean_bm'], p['win_rounds'] - ra['win_rounds']))
    print('[lift] PROD vs RAND_POOL : mean_bm %+.3f, 등수적중 %+d회 (다양성 선택의 순수 이득)'
          % (p['mean_bm'] - rp['mean_bm'], p['win_rounds'] - rp['win_rounds']))
    print('\n[해석] PROD가 RAND_ALL/RAND_POOL보다 등수적중 회차/mean_bm이 높으면 실제 이득.')


if __name__ == '__main__':
    main()
