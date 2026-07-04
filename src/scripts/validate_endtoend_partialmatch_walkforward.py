# -*- coding: utf-8 -*-
"""
end-to-end 부분일치 walk-forward A/B (극단성 풀 + 5장 선택기 vs 매칭 무작위풀 + 동일 선택기)

배경(2026-06-27, 3차 코드리뷰 Codex gpt-5.5 적대검증 권고):
  기존 도구(validate_pool_walkforward / evaluate_threshold_curve)는 "전체 6조합 정확 생존(exact
  coverage)"만 측정한다. 그러나 이 시스템의 실제 산출물은 '풀에서 고른 5장'이고, 그 5장은
  DiversitySelector가 '번호 커버리지/직교성'으로 뽑아 '부분일치(3+/4+)'와 '번호단위 적중'을
  노린다. 따라서 풀의 가치를 정직하게 보려면 selector '이후' 지표를, 동일 K/seed의 무작위풀 +
  동일 selector baseline 대비 paired 로 봐야 한다(평가-전략 일치).

방법(누설0):
  여러 train cutoff t 마다:
    1. 극단성 풀(생산과 동일: 가중 scorer, K) 형성 (r<=t 로만 fit, 미래누설 차단)
    2. 무작위 풀(같은 크기 K) 형성 (matched baseline)
    3. FrequencyAnalyzer 가중치(until_round=t)로 번호 가중 (생산 동일 빈도/최근성 성분.
       [2026-07-04 정직화] 단 생산의 ml_signal(ml_beta=0.4)은 blind fold에 주입 불가(현재 ML은
       전체데이터 학습 산물=미래누설)라 제외 - 양팔(ext/rnd) 동일 가중이라 paired 결론은 불변이나
       'ML 가중 성분'은 이 도구가 검증하지 않음을 명시)
    4. seed 반복(selector 운 분리): seed 마다 두 풀 각각에서 DiversitySelector로 5장 선택
       (동일 selector·동일 seed·동일 후보수를 두 풀에 적용. [2026-07-04 정직화] 단 quality(-극단성)는
        생산 충실상 ext 팔에만 전달되므로 측정 효과는 '풀 내용 + 품질가중 선택'의 결합효과다 -
        순수 pool content 격리가 아님. 격리가 필요하면 ext+quality=None ablation 팔 추가)
    5. hold-out(t+1 .. t+window) 실제 당첨조합마다 부분일치 지표 집계:
       max_ticket_match / count_3plus / count_2plus / union_hit / sum_matches
  [2026-07-04 통계 재설계] 1차 판정(사전등록) = any_2plus의 fold-level paired t (fold=독립 단위).
  draw 단위 z와 (fold,seed) t는 클러스터 상관(동일 풀·hold-out 공유, ICC 실측 ~0.16)으로 과대라
  참고로 강등. 2차 지표는 탐색용(Holm 보정 필요). any_2plus는 과거 실행에서 사후 선택된 최량
  지표이므로(winner's curse) 신규 fold만의 감도분석 병기가 필수다.

해석:
  - 극단풀이 무작위풀 대비 부분일치(특히 3+/2+ 적중률, union_hit)를 '유의하게' 올리면 -> exact
    coverage 가 무작위여도(=풀 선택 신호 약함) 부분일치 관점에선 풀이 전략적 가치 있음 -> 결론 보강/수정.
  - 차이가 노이즈(유의하지 않음)면 -> exact coverage 결론(포화)이 end-to-end 에서도 견고.

주의(정직성): weights.json(가중 scorer) 은 전체데이터 산물을 '고정 하이퍼파라미터'로 주입 -> 미세한
  하이퍼파라미터 누설은 가중쪽에 유리한 방향(보수적). fit/풀형성/가중치산출은 모두 r<=t 로만.

사용법: python src/scripts/validate_endtoend_partialmatch_walkforward.py
        [--cutoffs 1050,1100,1150,1200] [--window 50] [--K 1500000] [--seeds 6] [--cand 30000]
ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import sys
import time
import json
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np
from scipy.stats import t as _student_t  # [2026-07-04] 정확 자유도 기반 t 임계값(하드코딩 2.04 대체)


def _build_weighted_scorer(epp, db, win_train):
    """build_pool 의 가중 분기를 비트동일 재현 (생산 충실)."""
    from src.core.extremeness_scorer import ExtremenessScorer  # noqa
    weight_json = epp._load_weight_params()
    scorer, weighted = epp._build_scorer(weight_json)
    scorer.fit(win_train)
    if weighted and getattr(scorer, '_feature_scale', None) is not None:
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
    return scorer, weighted


def _ticket_metrics(tickets, win):
    """5장 tickets(list of tuple) vs 당첨 6번호 set -> 부분일치 지표 dict."""
    wset = set(int(x) for x in win)
    matches = [len(set(int(x) for x in t) & wset) for t in tickets]
    union = set()
    for t in tickets:
        union |= set(int(x) for x in t)
    union_hit = len(union & wset)
    return {
        'max_match': max(matches) if matches else 0,
        'count_3plus': sum(1 for m in matches if m >= 3),
        'count_2plus': sum(1 for m in matches if m >= 2),
        'sum_matches': sum(matches),
        'union_hit': union_hit,
        'any_3plus': 1 if any(m >= 3 for m in matches) else 0,
        'any_2plus': 1 if any(m >= 2 for m in matches) else 0,
    }


def _two_prop_z(x1, n1, x2, n2):
    """두 비율 차의 z (pooled). n=0 방어."""
    if n1 == 0 or n2 == 0:
        return 0.0
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = (p * (1 - p) * (1.0 / n1 + 1.0 / n2)) ** 0.5
    if se == 0:
        return 0.0
    return (p1 - p2) / se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cutoffs', type=str, default='1050,1100,1150,1200')
    ap.add_argument('--window', type=int, default=50, help='각 cutoff 의 hold-out 미래 회차 수')
    ap.add_argument('--K', type=int, default=1_500_000)
    ap.add_argument('--seeds', type=int, default=6)
    ap.add_argument('--cand', type=int, default=30000, help='selector candidate_sample (생산=30000)')
    ap.add_argument('--out', type=str, default='results/endtoend_partialmatch_walkforward.json')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
    from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

    db = DatabaseManager()
    epp = ExtremenessPoolPredictor(db, target_K=args.K)  # 가중치/캐시 경로 재사용용 어댑터
    all_rows = sorted(((r, sorted(int(x) for x in s.split(',')))
                       for r, s, _ in db.get_all_numbers()), key=lambda x: x[0])
    latest = all_rows[-1][0]
    cutoffs = sorted(int(x) for x in args.cutoffs.split(','))
    # [2026-07-04 P3] cutoff 간격 < window 면 hold-out 이 조용히 중첩되어 fold 독립성(fold-level
    # paired t 의 전제)이 붕괴한다 -> 하드 가드. (기본/기존 실행은 간격=window=50 이라 영향 없음)
    _gaps = [b - a for a, b in zip(cutoffs, cutoffs[1:])]
    if _gaps and min(_gaps) < args.window:
        raise SystemExit(
            f"[오류] cutoff 최소 간격({min(_gaps)}) < window({args.window}) - hold-out 중첩으로 "
            f"fold 독립성 붕괴. 간격 >= window 로 지정하라.")
    K = args.K

    print("=" * 100)
    print(f"end-to-end 부분일치 walk-forward A/B | 최신 {latest} | K={K:,} | seeds={args.seeds} | "
          f"cand={args.cand} | window={args.window}")
    print("극단성 풀+선택기  vs  무작위 풀(동일 K)+동일 선택기  (둘 다 동일 FrequencyAnalyzer 가중)")
    print("=" * 100)

    combos = ExtremenessScorer.all_combinations()  # (8.14M,6) int8

    # 누적 집계기 (ext/rnd) - paired
    agg = {cond: {'max_match': [], 'count_3plus': [], 'count_2plus': [], 'sum_matches': [],
                  'union_hit': [], 'any_3plus': 0, 'any_2plus': 0, 'n': 0}
           for cond in ('ext', 'rnd')}
    # 독립성 보정용 단위 관측: 5장 tickets 가 (fold,seed) 마다 고정이라 hold-out draws 는 강하게
    #   상관 -> draw 단위 관측(n_obs)을 독립으로 보면 z 과대. 나아가 같은 fold 의 seed 들도 동일
    #   풀·동일 hold-out 을 공유해 상관(ICC 실측 ~0.16) -> (fold,seed) t 도 과대(유효표본 절반 이하).
    #   [2026-07-04 재설계] 1차 판정 = fold-level paired t (아래). (fold,seed) t 는 참고로 강등.
    unit_diff_2 = []   # per (fold,seed): ext_any2_rate - rnd_any2_rate
    unit_diff_3 = []
    unit_diff_max = []
    unit_diff_union = []
    per_fold = []      # 일관성 점검용

    for t in cutoffs:
        holdout = [nums for r, nums in all_rows if t < r <= t + args.window]
        if len(holdout) < 5:
            print(f"  [skip] cutoff {t}: hold-out {len(holdout)}회 (너무 적음)")
            continue
        win_train = np.array([nums for r, nums in all_rows if r <= t], dtype=np.int16)

        ts = time.time()
        # (A) 극단성 풀 (가중 scorer, 생산 충실)
        scorer, weighted = _build_weighted_scorer(epp, db, win_train)
        scores = scorer.score(combos)
        ext_idx = ExtremenessScorer.select_pool(scores, K)
        ext_pool = combos[ext_idx]
        ext_quality = (-scores[ext_idx]).astype(np.float32)  # -극단성 (생산 _pool_quality 동일)

        # (B) 무작위 풀 (matched baseline, 같은 K) - 결정적 시드
        rng_pool = np.random.RandomState(10_000 + t)
        rnd_idx = rng_pool.choice(TOTAL_COMBINATIONS, K, replace=False)
        rnd_pool = combos[rnd_idx]

        # (C) 번호 가중치 (생산 동일: until_round=t)
        fa = FrequencyAnalyzer(db)
        weights = fa.compute_weights(until_round=t, spread=epp.spread)

        fold_e2 = []; fold_r2 = []; fold_e3 = []; fold_r3 = []
        # seed 반복: selector 운 분리. 두 풀에 '동일 seed/동일 후보수' 적용.
        for seed in range(args.seeds):
            # 극단풀: candidate_sample 만큼 풀에서 무작위 샘플(=selector 내부 동작과 동치) 후 선택
            rsel = np.random.RandomState(seed)
            ce = rsel.choice(len(ext_pool), min(args.cand, len(ext_pool)), replace=False)
            tickets_ext = DiversitySelector(number_weights=weights).select(
                ext_pool[ce], num_tickets=5, quality=ext_quality[ce],
                candidate_sample=args.cand, seed=seed)
            # 무작위풀: 동일 절차 (quality 없음 - 무작위풀엔 극단성 의미 없음)
            rsel2 = np.random.RandomState(seed)
            cr = rsel2.choice(len(rnd_pool), min(args.cand, len(rnd_pool)), replace=False)
            tickets_rnd = DiversitySelector(number_weights=weights).select(
                rnd_pool[cr], num_tickets=5, quality=None,
                candidate_sample=args.cand, seed=seed)

            # (fold,seed) 단위 누적기
            u = {'ext': {'a2': 0, 'a3': 0, 'mx': [], 'un': []}, 'rnd': {'a2': 0, 'a3': 0, 'mx': [], 'un': []}}
            for win in holdout:
                me = _ticket_metrics(tickets_ext, win)
                mr = _ticket_metrics(tickets_rnd, win)
                for cond, m in (('ext', me), ('rnd', mr)):
                    for key in ('max_match', 'count_3plus', 'count_2plus', 'sum_matches', 'union_hit'):
                        agg[cond][key].append(m[key])
                    agg[cond]['any_3plus'] += m['any_3plus']
                    agg[cond]['any_2plus'] += m['any_2plus']
                    agg[cond]['n'] += 1
                    u[cond]['a2'] += m['any_2plus']; u[cond]['a3'] += m['any_3plus']
                    u[cond]['mx'].append(m['max_match']); u[cond]['un'].append(m['union_hit'])
            hn = len(holdout)
            e2 = u['ext']['a2'] / hn; r2 = u['rnd']['a2'] / hn
            e3 = u['ext']['a3'] / hn; r3 = u['rnd']['a3'] / hn
            unit_diff_2.append(e2 - r2); unit_diff_3.append(e3 - r3)
            unit_diff_max.append(float(np.mean(u['ext']['mx']) - np.mean(u['rnd']['mx'])))
            unit_diff_union.append(float(np.mean(u['ext']['un']) - np.mean(u['rnd']['un'])))
            fold_e2.append(e2); fold_r2.append(r2); fold_e3.append(e3); fold_r3.append(r3)

        per_fold.append({'cutoff': t, 'holdout': len(holdout),
                         'ext_any2': float(np.mean(fold_e2)), 'rnd_any2': float(np.mean(fold_r2)),
                         'ext_any3': float(np.mean(fold_e3)), 'rnd_any3': float(np.mean(fold_r3)),
                         # [2026-07-04] fold-level paired 차이(1차 판정용): seed 평균 후 fold 단위.
                         'd_any2': float(np.mean(fold_e2) - np.mean(fold_r2)),
                         'd_any3': float(np.mean(fold_e3) - np.mean(fold_r3)),
                         'd_max_match': float(np.mean(unit_diff_max[-args.seeds:])),
                         'd_union_hit': float(np.mean(unit_diff_union[-args.seeds:]))})
        n_obs = args.seeds * len(holdout)
        print(f"  cutoff {t:>4} | hold-out {len(holdout):>3}회 x seed {args.seeds} = {n_obs} obs "
              f"| 풀제거 {(1-K/TOTAL_COMBINATIONS)*100:.1f}% | {time.time()-ts:.0f}s")

    # 종합
    def _mean(cond, key):
        a = agg[cond][key]
        return float(np.mean(a)) if a else 0.0

    n = agg['ext']['n']
    print("-" * 100)
    print(f"  [집계] 총 관측 {n} (paired). 극단풀(ext) vs 무작위풀(rnd) 평균:")
    rows = []
    for key in ('union_hit', 'max_match', 'sum_matches', 'count_2plus', 'count_3plus'):
        e, r = _mean('ext', key), _mean('rnd', key)
        diff = e - r
        rows.append((key, e, r, diff))
        print(f"    {key:<12} ext={e:.4f}  rnd={r:.4f}  DIFF={diff:+.4f}")

    z2 = _two_prop_z(agg['ext']['any_2plus'], n, agg['rnd']['any_2plus'], n)
    z3 = _two_prop_z(agg['ext']['any_3plus'], n, agg['rnd']['any_3plus'], n)
    p2e, p2r = agg['ext']['any_2plus'] / n, agg['rnd']['any_2plus'] / n
    p3e, p3r = agg['ext']['any_3plus'] / n, agg['rnd']['any_3plus'] / n
    print(f"    any_2plus%   ext={p2e*100:.2f}%  rnd={p2r*100:.2f}%  (z={z2:+.2f})")
    print(f"    any_3plus%   ext={p3e*100:.2f}%  rnd={p3r*100:.2f}%  (z={z3:+.2f})")

    # === 독립성 보정 paired t-test ((fold,seed) 단위) ===
    def _paired_t(diffs):
        a = np.array(diffs, dtype=np.float64)
        m = len(a)
        if m < 2:
            return 0.0, 0.0, 0.0
        mean = a.mean(); sd = a.std(ddof=1)
        se = sd / (m ** 0.5) if sd > 0 else 0.0
        tval = mean / se if se > 0 else 0.0
        return float(mean), float(tval), int(m)

    print("-" * 100)
    print(f"  [참고] (fold,seed)=paired 단위 t-test ({n}개 상관 draw 관측 대신 단위로. 단 같은 fold의")
    print("         seed들도 풀·hold-out을 공유해 상관(ICC~0.16) -> 이 t도 과대. 1차 판정은 아래 fold-level):")
    for nm, diffs in (('any_2plus_rate', unit_diff_2), ('any_3plus_rate', unit_diff_3),
                      ('max_match', unit_diff_max), ('union_hit', unit_diff_union)):
        mean, tval, m = _paired_t(diffs)
        _tc = float(_student_t.ppf(0.975, max(m - 1, 1)))  # [2026-07-04] 정확 df 임계(2.04 하드코딩 제거)
        flag = '유의' if abs(tval) > _tc else '비유의'
        print(f"    {nm:<16} meanDIFF(ext-rnd)={mean:+.4f}  t={tval:+.2f} (n_units={m}, 임계 {_tc:.2f}) -> {flag}")

    # === [2026-07-04 사전등록 1차 판정] fold-level paired t (fold=독립 단위) ===
    fold_metrics = {
        'any_2plus_rate': [pf['d_any2'] for pf in per_fold],
        'any_3plus_rate': [pf['d_any3'] for pf in per_fold],
        'max_match': [pf['d_max_match'] for pf in per_fold],
        'union_hit': [pf['d_union_hit'] for pf in per_fold],
    }
    print("-" * 100)
    print("  [1차 판정(사전등록)] fold-level paired t. 1차 지표=any_2plus_rate 단 1개,")
    print("   나머지는 탐색용 2차 지표(다중비교 Holm 보정 필요). hold-out 길이 이질 fold는 등가중 집계(공개):")
    fold_level = {}
    for nm, diffs in fold_metrics.items():
        mean, tval, m = _paired_t(diffs)
        df = max(m - 1, 1)
        tcrit = float(_student_t.ppf(0.975, df))
        sig = abs(tval) > tcrit
        fold_level[nm] = {'mean_diff': mean, 't': tval, 'n_folds': m, 'df': df,
                          't_crit': round(tcrit, 3), 'significant': bool(sig)}
        print(f"    {nm:<16} meanDIFF={mean:+.4f}  t={tval:+.2f} (n_folds={m}, df={df}, "
              f"임계 {tcrit:.2f}) -> {'유의' if sig else '비유의'}")
    # 검정력 정직 공개: 이 설계로 검출 가능한 최소효과(MDE, 80% 검정력 근사)
    _d2 = np.array(fold_metrics['any_2plus_rate'], dtype=np.float64)
    if len(_d2) >= 2:
        _se2 = _d2.std(ddof=1) / (len(_d2) ** 0.5)
        _df2 = len(_d2) - 1
        _mde = (float(_student_t.ppf(0.975, _df2)) + float(_student_t.ppf(0.80, _df2))) * _se2
        print(f"  [검정력 공개] any_2plus fold-level se={_se2*100:.2f}%p -> 80% 검정력 최소검출효과(MDE) "
              f"~{_mde*100:.2f}%p. 비유의는 '효과 없음'의 증명이 아니라 'MDE 미만 효과는 이 설계로 "
              f"판정 불가'를 뜻한다(저검정력 오독 방지).")

    print("  [fold별 일관성] any_2plus (ext vs rnd):")
    for pf in per_fold:
        d2 = pf['ext_any2'] - pf['rnd_any2']
        print(f"    cutoff {pf['cutoff']}: ext={pf['ext_any2']*100:.1f}% rnd={pf['rnd_any2']*100:.1f}% "
              f"DIFF={d2*100:+.1f}%p (hold-out {pf['holdout']})")

    # 정직한 판정 [2026-07-04 재설계]: 1차 지표(any_2plus) fold-level paired t + fold 일관성
    fl2 = fold_level['any_2plus_rate']
    folds_pos = sum(1 for pf in per_fold if pf['ext_any2'] > pf['rnd_any2'])
    robust = fl2['significant'] and fl2['mean_diff'] > 0 and folds_pos >= max(1, int(0.75 * len(per_fold)))
    verdict = ("극단풀이 무작위풀 대비 부분일치(2+)를 fold-level paired t 유의 + fold일관으로 개선 = "
               "전형성 이득 확정 (주의: 2일치는 무배당(5등=3일치부터) - 등수 경제성이 아닌 구조적 이득)"
               if robust
               else "극단풀 부분일치 우위가 1차 판정(fold-level paired t)에서 비유의(약신호/노이즈) - "
                    "exact coverage 포화 결론과 정합")
    print("-" * 100)
    print(f"  [정직한 판정] {verdict}")
    _, _tu2, _mu2 = _paired_t(unit_diff_2)
    print(f"    (참고: draw 단위 z={z2:+.2f}({n}개 상관관측)와 (fold,seed) t={_tu2:+.2f}(n={_mu2})는 모두 "
          f"클러스터 상관으로 과대 -> fold-level t={fl2['t']:+.2f}(n_folds={fl2['n_folds']})가 1차. "
          f"any_2plus는 과거 실행에서 지표 7종 중 사후 선택된 최량 지표(winner's curse) -> "
          f"신규 fold만의 감도분석 병기 필수.)")

    out = {
        'meta': {'latest': latest, 'K': K, 'cutoffs': cutoffs, 'window': args.window,
                 'seeds': args.seeds, 'cand': args.cand, 'n_obs': n,
                 'note': 'ext=극단성 가중풀(+품질가중 선택)+selector, rnd=무작위풀(동일K)+동일selector(quality=None), '
                         '둘 다 동일 FrequencyAnalyzer 빈도/최근성 가중(ML 가중 제외), 누설0'},
        'preregistered': {
            'primary_metric': 'any_2plus fold-level paired t (양측 alpha=0.05)',
            'secondary_metrics': ['any_3plus', 'union_hit', 'max_match', 'count_3plus'],
            'secondary_correction': 'Holm(탐색용)',
            'sensitivity_rule': "이전 실행(cutoffs 950~1200)에 재사용된 fold를 제외한 신규 fold만의 "
                                "fold-level t 병기 (winner's curse 방어)",
            'honesty_note': '2일치(any_2plus)는 무배당(5등=3일치부터) - 유의해도 전형성/구조 이득이지 '
                            '등수 경제성 직접 증명 아님',
        },
        'fold_level_t': fold_level,
        'means': {k: {'ext': e, 'rnd': r, 'diff': d} for (k, e, r, d) in rows},
        'any_2plus': {'ext_pct': p2e, 'rnd_pct': p2r, 'z_naive_correlated': z2},
        'any_3plus': {'ext_pct': p3e, 'rnd_pct': p3r, 'z_naive_correlated': z3},
        'paired_t_unit': {
            'any_2plus_rate': {'mean_diff': _paired_t(unit_diff_2)[0], 't': _paired_t(unit_diff_2)[1]},
            'any_3plus_rate': {'mean_diff': _paired_t(unit_diff_3)[0], 't': _paired_t(unit_diff_3)[1]},
            'max_match': {'mean_diff': _paired_t(unit_diff_max)[0], 't': _paired_t(unit_diff_max)[1]},
            'union_hit': {'mean_diff': _paired_t(unit_diff_union)[0], 't': _paired_t(unit_diff_union)[1]},
            'n_units': len(unit_diff_2),
        },
        'per_fold': per_fold,
        'verdict': verdict,
    }
    outpath = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: {args.out}")


if __name__ == '__main__':
    main()
