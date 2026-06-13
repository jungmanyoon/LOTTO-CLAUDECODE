# -*- coding: utf-8 -*-
"""
풀 크기(K) 튜닝 - blind walk-forward (2026-06-13, Codex gpt-5.5 + Gemini 3.1-pro 합의 레버 #1).

목적: 극단성 풀의 크기 K(현행 1.5M)를 '보존율'이 아니라 사용자가 실제로 받는
'최종 5세트의 등수 적중률(어떤 티켓이 3개+ 맞는 비율)' 기준으로 재최적화한다.
선택=마할라노비스(hybrid 기본의 정확도 경로), predict는 production
ExtremenessPoolPredictor.predict()를 그대로 호출(재구현 아님).

핵심 설계:
  - blind: 각 fold train_until = fold 시작 직전 회차 -> 미래정보 차단(누설 0).
  - paired: 모든 K가 같은 fold/seed/holdout을 공유(공정 비교).
  - 최적화: fold당 마할라노비스 전수채점(8.14M)을 1회만 수행하고, 같은 scores에서
    여러 K를 top-K로 잘라 평가(8.14M 전수패스를 K마다 반복하지 않음).
  - 지표: 등수적중률 P(>=3매치), mean best-match, p4(>=4매치), 5장 최대겹침.
  - 정직: 표본수 n과 표준오차(SE)를 함께 출력해 'K 차이가 노이즈인지' 판단 가능케 함.

ASCII 출력(Windows), UTF-8 인코딩, 이모지 금지.

사용:
  python src/scripts/tune_pool_size_walkforward.py
  (env) EXP_FOLDS=8 EXP_WINDOW=40 EXP_KLIST="800000,1200000,1500000,2000000,2800000"
"""
import os
import sys
import time
import math
import logging

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
from src.core.extremeness_scorer import ExtremenessScorer
from src.scripts.backtest_extremeness_prediction import eval_sets


def _hits(ranks):
    return sum(1 for r in ranks if r is not None)


def run(db, k_list, folds=8, window=40, num_sets=5, seeds=(42,), log=print):
    """다중 시드 blind walk-forward. fold당 마할라노비스 채점은 1회만 하고, 같은 scores에서
    여러 K x 여러 시드로 predict를 평가한다(시드=5장 선택 변동만 → K 순위 재현성 확인용)."""
    rows = []
    for r, t in db.get_numbers_with_bonus():
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

    # (K, seed_idx)별 누적기 - 각 시드는 같은 holdout을 보지만 5장 선택이 달라짐(재현성 검증)
    acc = {(K, si): {'bm': [], 'rank': []} for K in k_list for si in range(len(seeds))}
    overlap = {(K, si): [] for K in k_list for si in range(len(seeds))}
    ra = {si: {'bm': [], 'rank': []} for si in range(len(seeds))}
    rngs = {si: np.random.RandomState(1000 + seed) for si, seed in enumerate(seeds)}

    combos = ExtremenessScorer.all_combinations()
    log(f"[K튜닝] 전체 {total}회차, folds={len(fold_specs)} window={window}, "
        f"K후보={[k // 1000 for k in k_list]}K, 시드={list(seeds)}")
    log(f"[K튜닝] 조합 전체 {len(combos):,}개 로드. fold당 마할라노비스 1회 채점.")

    for fi, (a, b) in enumerate(fold_specs, 1):
        t0 = time.time()
        train_until = rows[a - 1][0]
        holdout = rows[a:b]

        # --- 마할라노비스 전수채점 1회 (build_pool의 mahalanobis 분기와 동일) ---
        epp = ExtremenessPoolPredictor(db)  # 기본 hybrid -> 선택=마할라노비스
        win_train = np.array([nums for (r, nums, _b) in rows if r <= train_until], dtype=np.int16)
        weight_json = epp._load_weight_params()
        scorer, weighted = epp._build_scorer(weight_json)
        scorer.fit(win_train)
        if weighted and getattr(scorer, '_feature_scale', None) is not None:
            S = np.diag(scorer._feature_scale).astype(np.float32)
            scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
        comp = scorer.score_components(combos)
        scores = comp['total']
        t_score = time.time() - t0

        for K in k_list:
            pool_idx = ExtremenessScorer.select_pool(scores, K)
            epp.target_K = K
            epp._pool_combos = combos[pool_idx]
            epp._pool_quality = (-scores[pool_idx]).astype(np.float32)
            epp._train_until = train_until
            for si, seed in enumerate(seeds):
                sets = epp.predict(num_sets=num_sets, seed=seed)
                prod_sets = [s2['numbers'] for s2 in sets]
                mo = 0
                for i in range(len(prod_sets)):
                    for j in range(i + 1, len(prod_sets)):
                        mo = max(mo, len(set(prod_sets[i]) & set(prod_sets[j])))
                overlap[(K, si)].append(mo)
                for (_tr, nums, bonus) in holdout:
                    draw = set(nums)
                    m, rk = eval_sets(prod_sets, draw, bonus)
                    acc[(K, si)]['bm'].append(m)
                    acc[(K, si)]['rank'].append(rk)

        # RAND_ALL (시드별 독립 rng)
        for si, seed in enumerate(seeds):
            rng = rngs[si]
            for (_tr, nums, bonus) in holdout:
                draw = set(nums)
                rsets = [sorted(rng.choice(range(1, 46), 6, replace=False).tolist()) for _ in range(num_sets)]
                m3, r3 = eval_sets(rsets, draw, bonus)
                ra[si]['bm'].append(m3)
                ra[si]['rank'].append(r3)

        log(f"[K튜닝] fold {fi}/{len(fold_specs)} (train<={train_until}) 완료 - "
            f"채점 {t_score:.1f}s, 누적 {time.time()-t0:.1f}s")

    n = len(acc[(k_list[0], 0)]['bm'])
    if n == 0:
        return None
    S = len(seeds)

    out = {'n': n, 'folds': len(fold_specs), 'window': window, 'seeds': list(seeds), 'per_K': {},
           'rand_all_hit': float(np.mean([_hits(ra[si]['rank']) / n for si in range(S)])),
           'rand_all_bm': float(np.mean([np.mean(ra[si]['bm']) for si in range(S)]))}
    for K in k_list:
        hits_by_seed = [_hits(acc[(K, si)]['rank']) / n for si in range(S)]
        bm_by_seed = [float(np.mean(acc[(K, si)]['bm'])) for si in range(S)]
        mean_hit = float(np.mean(hits_by_seed))
        out['per_K'][K] = {
            'rank_hit': mean_hit,
            'rank_hit_se': math.sqrt(mean_hit * (1 - mean_hit) / n),   # 표본오차(라운드 수 기준)
            'seed_hits': [round(h * 100, 1) for h in hits_by_seed],     # 시드별 값(재현성)
            'seed_spread': round((max(hits_by_seed) - min(hits_by_seed)) * 100, 1),
            'mean_bm': float(np.mean(bm_by_seed)),
            'max_overlap': max(max(overlap[(K, si)]) for si in range(S)),
        }
    return out


def main():
    logging.basicConfig(level=logging.ERROR, format='%(message)s')
    logging.disable(logging.WARNING)  # production 클래스의 info/warn 소음 억제(결과만)
    from src.core.db_manager import DatabaseManager

    folds = int(os.environ.get('EXP_FOLDS', '8'))
    window = int(os.environ.get('EXP_WINDOW', '40'))
    klist_env = os.environ.get('EXP_KLIST', '800000,1000000,1200000,1500000,1800000,2200000,2800000')
    k_list = [int(x) for x in klist_env.split(',')]
    seeds = tuple(int(x) for x in os.environ.get('EXP_SEEDS', '42').split(','))

    db = DatabaseManager()
    res = run(db, k_list, folds=folds, window=window, seeds=seeds, log=lambda m: print(m, flush=True))
    if not res:
        print('[K튜닝] 데이터 부족 또는 실패')
        return

    print('')
    print('=' * 82)
    print('[K 튜닝 결과] 최종 5세트 blind walk-forward | n=%d folds=%d window=%d seeds=%s'
          % (res['n'], res['folds'], res['window'], res['seeds']))
    print('=' * 82)
    print('%-9s | %-15s | %-18s | %-7s | %-7s | %-6s'
          % ('K', '평균등수적중(±SE)', '시드별값', '시드폭', 'mean_bm', '최대겹침'))
    print('-' * 82)
    best_k, best_hit = None, -1
    for K in k_list:
        d = res['per_K'][K]
        if d['rank_hit'] > best_hit:
            best_hit, best_k = d['rank_hit'], K
        print('%-9s | %5.1f%% (+-%4.1f%%) | %-18s | %4.1f%%  | %7.3f | %d'
              % ('%dK' % (K // 1000), d['rank_hit'] * 100, d['rank_hit_se'] * 100,
                 str(d['seed_hits']), d['seed_spread'], d['mean_bm'], d['max_overlap']))
    print('-' * 82)
    print('%-9s | %5.1f%%          |' % ('RAND_ALL', res['rand_all_hit'] * 100))
    print('=' * 82)
    # 정직 판정: 최고 K와 현행 1.5M의 차이가 표본오차/시드폭 안인가?
    cur = res['per_K'].get(1_500_000)
    bestd = res['per_K'][best_k]
    print('[정직 판정] 평균 등수적중 최고 K=%dK (%.1f%%). 현행 1500K=%s.'
          % (best_k // 1000, best_hit * 100,
             ('%.1f%%' % (cur['rank_hit'] * 100)) if cur else 'N/A'))
    if cur:
        diff = (bestd['rank_hit'] - cur['rank_hit']) * 100
        pooled_se = math.sqrt(bestd['rank_hit_se'] ** 2 + cur['rank_hit_se'] ** 2) * 100
        verdict = '노이즈 내(유의차 없음 - 현행 유지 안전)' if abs(diff) <= pooled_se else '유의 가능(추가 검증 권장)'
        print('[정직 판정] 최고K-현행 차이 %+.1f%%p, 합성 표본SE +-%.1f%%p -> %s'
              % (diff, pooled_se, verdict))
    # K 순위 재현성: 각 시드에서 현행 1500K가 일관되게 최저인가?
    if cur and len(res['seeds']) > 1:
        worst_counts = 0
        for si in range(len(res['seeds'])):
            seed_vals = {K: res['per_K'][K]['seed_hits'][si] for K in k_list}
            if min(seed_vals, key=seed_vals.get) == 1_500_000:
                worst_counts += 1
        print('[재현성] 현행 1500K가 최저인 시드: %d/%d (높을수록 1500K 열위가 진짜 신호)'
              % (worst_counts, len(res['seeds'])))


if __name__ == '__main__':
    main()
