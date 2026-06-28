# -*- coding: utf-8 -*-
"""
가중 vs 무가중 극단성 풀 walk-forward A/B (2026-06-27).

목적(F4 공백 메우기): 공표 K곡선(extremeness_threshold_selector.evaluate_threshold_curve)은
'무가중' ExtremenessScorer 로 측정되나, production build_pool 은 '가중' scorer
(configs/extremeness_weights.json best_params 의 alpha/pw_*/fw_* 주입 + cov_inv = S@cov_inv@S)
를 쓴다. 따라서 백그라운드 PoolOptimizer 가 산출한 가중치가 walk-forward 커버리지를
'집계적으로' 올리는가/내리는가/무효(no-op)인가를 누설0으로 측정한다.

핵심 설계(누설0 필수):
  - 각 fold f: train = fold 시작 직전 회차까지만(미래 차단). hold-out = fold(window회).
  - (A) 무가중 ExtremenessScorer: fit(fold train) 후 채점 (evaluate_threshold_curve 와 동일).
  - (B) 가중 scorer: fit(fold train) 후, 가중치(weights.json best_params)를 '고정 하이퍼파라미터'
    로 주입(build_pool 과 동일: penalty_weights=pw_*, alpha, _feature_scale=fw_*, cov_inv=S@cov_inv@S).
    => fit 은 fold train 으로만(누설0), weights 는 전체데이터 산물이지만 '고정 상수'로만 쓰므로
    fold hold-out 정보를 보지 않는다(=하이퍼파라미터 누설은 미세, 결과는 정직하게 표시).
  - 같은 fold 에서 A/B 모두 동일 hold-out/8.14M 으로 채점 -> paired 비교.
  - K=1.5M(기본) cutoff 로 풀 형성, hold-out 당첨조합 6개 전체가 풀 안에 드는지(coverage) 집계.
  - lift = coverage / pool_ratio, lift_lcb = wilson_lower(hits, n) / pool_ratio.

판정: 가중(B)의 lift_lcb 가 1.0 위로 올라가면 PoolOptimizer 실효 있음. 무가중(A)과 동급/이하면
  보조계층이 일하는 척하는 no-op(또는 과적합으로 해로움). 정직하게 출력.

ASCII 출력(Windows), UTF-8 인코딩, 이모지 금지.

사용:
  python src/scripts/validate_weighted_pool_walkforward.py
  (env) WPW_FOLDS=5 WPW_WINDOW=150 WPW_KLIST="1000000,1500000,2000000"
"""
import os
import sys
import json
import time
import math
import argparse
import logging

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
logging.getLogger().setLevel(logging.ERROR)
logging.disable(logging.WARNING)  # production 클래스 info/warn 소음 억제(결과만)

from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
from src.core.extremeness_threshold_selector import wilson_lower


def _build_unweighted_scorer(db, win_train):
    """무가중 ExtremenessScorer (evaluate_threshold_curve 와 동일: 균등 가중)."""
    scorer = ExtremenessScorer(db)
    scorer.fit(win_train)
    return scorer


def _build_weighted_scorer(db, win_train, weight_json):
    """가중 scorer (build_pool 의 mahalanobis 분기와 비트 단위 동일).

    재현 정확성을 위해 production 어댑터의 _build_scorer 를 그대로 쓴 뒤
    fit + cov_inv = S@cov_inv@S 를 동일 순서로 적용한다.
    """
    epp = ExtremenessPoolPredictor(db)
    scorer, weighted = epp._build_scorer(weight_json)
    scorer.fit(win_train)
    if weighted and getattr(scorer, '_feature_scale', None) is not None:
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
    return scorer, weighted


def run(db, k_list, folds=5, window=150, log=print):
    rows = sorted(((r, sorted(int(x) for x in s.split(',')))
                   for r, s, _ in db.get_all_numbers()), key=lambda x: x[0])
    total = len(rows)
    latest = rows[-1][0]
    if total < window + 2:
        log('[A/B] 데이터 부족')
        return None

    # 가중치 로드 (build_pool 과 동일 경로)
    epp = ExtremenessPoolPredictor(db)
    weight_json = epp._load_weight_params()
    if not (weight_json and 'best_params' in weight_json):
        log('[A/B][경고] extremeness_weights.json best_params 없음 -> 가중=무가중(no-op 자명)')

    # fold 분할 (evaluate_threshold_curve 와 동일 로직: 최근 folds*window, 오래된 fold 부터)
    first = max(1, total - folds * window)
    fold_specs = []
    s = first
    while s + window <= total:
        fold_specs.append((s, s + window))
        s += window
    if not fold_specs:
        log('[A/B] fold 생성 실패')
        return None

    combos = ExtremenessScorer.all_combinations()
    log(f"[A/B] 전체 {total}회 (최신 {latest}), folds={len(fold_specs)} window={window}, "
        f"K후보={[k // 1000 for k in k_list]}K, 조합={len(combos):,}")

    # K별 A/B 누적자
    acc = {arm: {K: {'hits': 0, 'pr_w': 0.0, 'cut_w': 0.0} for K in k_list}
           for arm in ('unw', 'w')}
    n_total = 0

    for fi, (a, b) in enumerate(fold_specs, 1):
        t0 = time.time()
        train_rows = rows[:a]
        holdout_rows = rows[a:b]
        if not train_rows or not holdout_rows:
            continue
        win_train = np.array([nums for _, nums in train_rows], dtype=np.int16)
        win_holdout = np.array([nums for _, nums in holdout_rows], dtype=np.int16)
        fold_n = len(holdout_rows)
        n_total += fold_n

        # (A) 무가중
        sc_u = _build_unweighted_scorer(db, win_train)
        scores_u = sc_u.score(combos)
        hold_u = sc_u.score(win_holdout)

        # (B) 가중
        sc_w, weighted = _build_weighted_scorer(db, win_train, weight_json)
        scores_w = sc_w.score(combos)
        hold_w = sc_w.score(win_holdout)

        for K in k_list:
            # A
            cut_u = ExtremenessScorer.cutoff_for_size(scores_u, K)
            pr_u = float((scores_u <= cut_u).mean())
            hits_u = int((hold_u <= cut_u).sum())
            acc['unw'][K]['hits'] += hits_u
            acc['unw'][K]['pr_w'] += pr_u * fold_n
            acc['unw'][K]['cut_w'] += cut_u * fold_n
            # B
            cut_w = ExtremenessScorer.cutoff_for_size(scores_w, K)
            pr_w = float((scores_w <= cut_w).mean())
            hits_w = int((hold_w <= cut_w).sum())
            acc['w'][K]['hits'] += hits_w
            acc['w'][K]['pr_w'] += pr_w * fold_n
            acc['w'][K]['cut_w'] += cut_w * fold_n

        log(f"[A/B] fold {fi}/{len(fold_specs)} (train<={train_rows[-1][0]}, hold {fold_n}) "
            f"weighted={weighted} - {time.time()-t0:.0f}s")

    if n_total == 0:
        return None

    def _row(arm, K):
        d = acc[arm][K]
        hits = d['hits']
        pr = d['pr_w'] / n_total
        cov = hits / n_total
        lift = (cov / pr) if pr > 0 else 0.0
        cov_lcb = wilson_lower(hits, n_total)
        lift_lcb = (cov_lcb / pr) if pr > 0 else 0.0
        return {
            'target_K': int(K), 'pool_ratio': pr, 'cutoff_mean': d['cut_w'] / n_total,
            'coverage': cov, 'observed_hits': int(hits),
            'expected_random_hits': n_total * pr,
            'lift': lift, 'coverage_lcb': cov_lcb, 'lift_lcb': lift_lcb,
        }

    return {
        'latest_round': latest, 'n_total': n_total, 'folds': len(fold_specs),
        'window': window, 'grid': [int(k) for k in k_list],
        'unweighted': [_row('unw', K) for K in k_list],
        'weighted': [_row('w', K) for K in k_list],
        'weights_meta': (weight_json.get('best_params') if weight_json else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folds', type=int, default=int(os.environ.get('WPW_FOLDS', '5')))
    ap.add_argument('--window', type=int, default=int(os.environ.get('WPW_WINDOW', '150')))
    ap.add_argument('--klist', type=str,
                    default=os.environ.get('WPW_KLIST', '1000000,1500000,2000000'))
    ap.add_argument('--out', type=str, default='results/weighted_pool_walkforward.json')
    args = ap.parse_args()
    k_list = [int(x) for x in args.klist.split(',')]

    from src.core.db_manager import DatabaseManager
    db = DatabaseManager()

    t0 = time.time()
    res = run(db, k_list, folds=args.folds, window=args.window,
              log=lambda m: print(m, flush=True))
    if not res:
        print('[A/B] 실패/데이터 부족')
        return

    print('')
    print('=' * 100)
    print('[가중 vs 무가중 극단성 풀 walk-forward A/B]  최신 %d  n=%d  folds=%d  window=%d'
          % (res['latest_round'], res['n_total'], res['folds'], res['window']))
    print('=' * 100)
    print('%-8s | %-4s | %-9s | %-9s | %-7s | %-8s | %-6s'
          % ('K', 'arm', 'pool_ratio', 'coverage', 'lift', 'lift_lcb', 'hits'))
    print('-' * 100)
    by_k = {r['target_K']: {} for r in res['unweighted']}
    for r in res['unweighted']:
        by_k[r['target_K']]['unw'] = r
    for r in res['weighted']:
        by_k[r['target_K']]['w'] = r
    for K in k_list:
        u = by_k[K]['unw']
        w = by_k[K]['w']
        for arm, d in (('무가중', u), ('가중', w)):
            print('%-8s | %-4s | %8.4f%% | %8.4f%% | %6.3f | %7.3f | %d'
                  % ('%dK' % (K // 1000), arm, d['pool_ratio'] * 100,
                     d['coverage'] * 100, d['lift'], d['lift_lcb'], d['observed_hits']))
        # paired 차이
        dcov = (w['coverage'] - u['coverage']) * 100
        dlift = w['lift'] - u['lift']
        dlcb = w['lift_lcb'] - u['lift_lcb']
        print('         | DIFF | (가중-무가중) coverage %+.4f%%p | lift %+.3f | lift_lcb %+.3f'
              % (dcov, dlift, dlcb))
        print('-' * 100)

    # 판정 (K=1.5M 기준)
    print('')
    base_k = 1_500_000 if 1_500_000 in by_k else k_list[len(k_list) // 2]
    u = by_k[base_k]['unw']
    w = by_k[base_k]['w']
    print('[정직 판정] 기준 K=%dK  n=%d' % (base_k // 1000, res['n_total']))
    print('  무가중: coverage=%.4f%%  lift=%.3f  lift_lcb=%.3f'
          % (u['coverage'] * 100, u['lift'], u['lift_lcb']))
    print('  가중  : coverage=%.4f%%  lift=%.3f  lift_lcb=%.3f'
          % (w['coverage'] * 100, w['lift'], w['lift_lcb']))
    if w['lift_lcb'] > 1.0 and w['lift_lcb'] > u['lift_lcb']:
        verdict = '가중치 실효 있음 (lift_lcb>1.0 이고 무가중보다 우위) -> PoolOptimizer 유의'
    elif abs(w['lift_lcb'] - u['lift_lcb']) < 0.03 and abs(w['coverage'] - u['coverage']) < 0.002:
        verdict = '가중=무가중 동급 (no-op) -> PoolOptimizer 보조계층이 일하는 척, 커버리지 무영향'
    elif w['coverage'] < u['coverage']:
        verdict = '가중이 무가중보다 열위 (과적합/해로움) -> PoolOptimizer 가중치가 커버리지를 깎음'
    else:
        verdict = '가중이 약간 다르나 lift_lcb<=1.0 (무작위와 비유의) -> 실효 불명/미미'
    print('  [결론] ' + verdict)

    res['verdict'] = verdict
    res['base_k'] = base_k
    outpath = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('  결과 저장: %s  (총 %.0fs)' % (args.out, time.time() - t0))


if __name__ == '__main__':
    main()
