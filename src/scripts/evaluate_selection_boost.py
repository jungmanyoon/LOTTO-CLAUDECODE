"""
선택 방식 보강 실측 (강화판): 5장/20장 구간 무작위 vs 다양성 - 왜 20장서 다양성이 졌나 + tail 안정화

evaluate_wheel_vs_cover.py 1차(train<=1126, K=1.5M, hold-out 100):
  - 20장: 무작위(풀내) 2.44/3+39/4+5 가 다양성(2.36/34/2)을 이김. 휠은 전 구간 열위.
Codex gpt-5.5 + Gemini 3.1-pro 재검토 합의:
  - 패배 원인: B(본질) 주 + A(부작용) 보조.
    B: 20장이면 무작위도 40~45 커버 -> 커버 한계효용 0. 다양성이 4+ 군집을 억제(고점 희생).
    A: 제약 repeat<=2는 120슬롯에 45*2=90 으로 빡빡 -> 억지 조합/풀 순도 저하.
  - 권장: "5장=1cover 다양성, 그 이상=극단성 풀 무작위(분산이 상단을 엶)".
  - 보강 누락 지적: (1)무작위 3시드 부족 - 4+ 희귀 꼬리라 30시드+ 필요
                    (2)가중 무작위(weight-proportional) 비교군 필요
                    (3)제약완화 다양성(repeat<=5,겹침<=3)

이 강화판이 측정:
  [5장] 무작위 30시드  vs  1cover(strict)
  [20장] 무작위 uniform 30시드 / 가중무작위 30시드 / 다양성 strict / 다양성 relax
  -> 무작위는 시드 분포(평균/표준편차/min~max)로 tail 안정화. 가중무작위로 가중치 tail 영향 확인.

사용법: python src/scripts/evaluate_selection_boost.py --holdout 100 --seeds 30
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
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np


def best_match(ticket, winning_set):
    return len(set(ticket) & winning_set)


class Accum:
    def __init__(self, name, n_tickets):
        self.name = name
        self.n_tickets = n_tickets
        self.best = []
        self.rounds_3plus = 0
        self.rounds_4plus = 0
        self.total_3plus_tickets = 0
        self.total_4plus_tickets = 0
        self.uniq_cover = []

    def add(self, tickets, winning_set):
        matches = [best_match(t, winning_set) for t in tickets]
        bm = max(matches) if matches else 0
        self.best.append(bm)
        if bm >= 3:
            self.rounds_3plus += 1
        if bm >= 4:
            self.rounds_4plus += 1
        self.total_3plus_tickets += sum(1 for m in matches if m >= 3)
        self.total_4plus_tickets += sum(1 for m in matches if m >= 4)
        self.uniq_cover.append(len(set(n for t in tickets for n in t)))

    def summary(self, total):
        best = np.array(self.best) if self.best else np.array([0])
        return {
            'name': self.name, 'tickets_per_round': self.n_tickets,
            'avg_best_match': round(float(best.mean()), 4),
            'rounds_3plus': self.rounds_3plus, 'rounds_4plus': self.rounds_4plus,
            'rounds_3plus_pct': round(self.rounds_3plus / total * 100, 1),
            'total_3plus_tickets': self.total_3plus_tickets,
            'total_4plus_tickets': self.total_4plus_tickets,
            'avg_unique_cover': round(float(np.mean(self.uniq_cover)), 1) if self.uniq_cover else 0,
            'best_match_dist': [int(x) for x in np.bincount(best, minlength=7)[:7]],
        }


def gumbel_topk(logp, k, rng):
    """가중 비복원 추출(Gumbel-top-k, O(N)). logp=log(p)에 Gumbel 노이즈 더해 top-k 인덱스."""
    u = rng.uniform(size=logp.shape[0]).clip(1e-12, 1 - 1e-12)
    g = -np.log(-np.log(u))
    keys = logp + g
    return np.argpartition(-keys, k)[:k]


def seed_summary(accs):
    r3 = np.array([a.rounds_3plus for a in accs], dtype=float)
    r4 = np.array([a.rounds_4plus for a in accs], dtype=float)
    avg = np.array([float(np.mean(a.best)) for a in accs])
    t3 = np.array([a.total_3plus_tickets for a in accs], dtype=float)
    return {
        'seeds': len(accs),
        'rounds_3plus': {'mean': round(r3.mean(), 1), 'std': round(r3.std(), 1),
                         'min': int(r3.min()), 'max': int(r3.max())},
        'rounds_4plus': {'mean': round(r4.mean(), 2), 'std': round(r4.std(), 2),
                         'min': int(r4.min()), 'max': int(r4.max())},
        'avg_best_match': {'mean': round(avg.mean(), 3), 'std': round(avg.std(), 3)},
        'total_3plus_tickets': {'mean': round(t3.mean(), 1), 'std': round(t3.std(), 1)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=1_500_000)
    ap.add_argument('--holdout', type=int, default=100)
    ap.add_argument('--seeds', type=int, default=30, help='무작위/가중무작위 시드 수(tail 안정화)')
    ap.add_argument('--candidate-sample', type=int, default=20000)
    ap.add_argument('--div-candidate', type=int, default=60000)
    ap.add_argument('--spread', type=float, default=0.5)
    ap.add_argument('--weights', type=str, default='configs/extremeness_weights.json')
    ap.add_argument('--out', type=str, default='results/selection_boost.json')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
    from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

    db = DatabaseManager()
    all_rows = [(r, s) for r, s, _ in db.get_all_numbers()]
    latest_round = max(r for r, _ in all_rows)
    train_until = latest_round - args.holdout
    holdout_rounds = [(r, s) for r, s in all_rows if r > train_until]
    win_train = np.array([sorted(int(x) for x in s.split(','))
                          for r, s in all_rows if r <= train_until], dtype=np.int16)

    print("=" * 96)
    print(f"선택방식 보강(강화)  |  최신 {latest_round}  train<= {train_until}  hold-out {len(holdout_rounds)}회  "
          f"K={args.K:,}  seeds={args.seeds}")
    print("=" * 96)

    t0 = time.time()
    wpath = os.path.join(PROJECT_ROOT, args.weights)
    if os.path.exists(wpath):
        with open(wpath, 'r', encoding='utf-8') as f:
            wj = json.load(f)
        bp = wj.get('best_params', {})
        pw = {d: bp.get(f"pw_{d}", 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
        scorer = ExtremenessScorer(db, alpha=bp.get('alpha', 0.5), penalty_weights=pw)
        scorer._feature_scale = np.array(
            [bp.get(f"fw_{f}", 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES], dtype=np.float32)
        scorer.fit(win_train)
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
        wlabel = f"최적화(AUC={wj.get('metrics', {}).get('auc_separation', 0):.3f})"
    else:
        scorer = ExtremenessScorer(db)
        scorer.fit(win_train)
        wlabel = "균등(기본)"

    combos = ExtremenessScorer.all_combinations()
    scores = scorer.score(combos)
    pool_idx = ExtremenessScorer.select_pool(scores, args.K)
    pool_arr = combos[pool_idx].astype(np.int16)        # (K,6)
    pool_list = [tuple(int(x) for x in row) for row in pool_arr]
    quality = -scores[pool_idx]
    N = len(pool_list)
    print(f"  채점/풀형성 {time.time()-t0:.1f}s  |  풀 {N:,}개  |  가중치 {wlabel}")

    fa = FrequencyAnalyzer(db)
    weights = fa.compute_weights(until_round=train_until, spread=args.spread)

    # 가중무작위용 조합 확률 p (조합 번호 가중치 합 비례)
    w_combo = weights[pool_arr - 1].sum(axis=1).astype(np.float64)  # (K,)
    p = w_combo / w_combo.sum()
    logp = np.log(p + 1e-12)

    sel_strict = DiversitySelector(number_weights=weights)
    sel_relax = DiversitySelector(number_weights=weights, max_number_repeat=5, max_pairwise_overlap=3)

    # 단일경로 전략
    cover5 = Accum('1cover 5장(strict)', 5)
    div20_strict = Accum('다양성 20장(strict repeat<=2)', 20)
    div20_relax = Accum('다양성 20장(relax repeat<=5)', 20)
    # 무작위 시드들
    Sd = args.seeds
    rand5 = [Accum(f'r5_{i}', 5) for i in range(Sd)]
    rand20u = [Accum(f'r20u_{i}', 20) for i in range(Sd)]
    rand20w = [Accum(f'r20w_{i}', 20) for i in range(Sd)]
    rngs = [np.random.RandomState(1000 + i) for i in range(Sd)]

    print("-" * 96)
    print(f"  보강 평가 시작 (candidate={args.candidate_sample}, div_candidate={args.div_candidate}) ...")
    t0 = time.time()
    for ri, (r, s) in enumerate(holdout_rounds, 1):
        wn = set(int(x) for x in s.split(','))

        # 단일경로(무거움)
        cover5.add(sel_strict.select(pool_list, num_tickets=5, quality=quality,
                   candidate_sample=args.candidate_sample, seed=r, local_search_iters=50), wn)
        div20_strict.add(sel_strict.select(pool_list, num_tickets=20, quality=quality,
                         candidate_sample=args.candidate_sample, seed=r, local_search_iters=60), wn)
        div20_relax.add(sel_relax.select(pool_list, num_tickets=20, quality=quality,
                        candidate_sample=args.div_candidate, seed=r, local_search_iters=80), wn)

        # 무작위 시드들(가벼움)
        for i in range(Sd):
            rg = rngs[i]
            rand5[i].add([pool_list[j] for j in rg.choice(N, 5, replace=False)], wn)
            rand20u[i].add([pool_list[j] for j in rg.choice(N, 20, replace=False)], wn)
            rand20w[i].add([pool_list[j] for j in gumbel_topk(logp, 20, rg)], wn)

        if ri % 20 == 0:
            print(f"    {ri}/{len(holdout_rounds)} 진행 ({time.time()-t0:.0f}s)")

    print(f"  평가 완료 {time.time()-t0:.0f}s")
    print("=" * 96)

    H = len(holdout_rounds)
    single = {k: a.summary(H) for k, a in
              [('cover5', cover5), ('div20_strict', div20_strict), ('div20_relax', div20_relax)]}
    rnd = {
        'rand5_uniform': seed_summary(rand5),
        'rand20_uniform': seed_summary(rand20u),
        'rand20_weighted': seed_summary(rand20w),
    }

    print("[1] 5장 구간")
    d = single['cover5']
    print(f"  1cover 5장(strict)        : avg={d['avg_best_match']:.3f} | 3+회차={d['rounds_3plus']}/{H} | "
          f"4+회차={d['rounds_4plus']} | 유니크={d['avg_unique_cover']:.0f}")
    rs = rnd['rand5_uniform']
    print(f"  무작위 5장({Sd}시드)        : avg={rs['avg_best_match']['mean']:.3f} | "
          f"3+회차 {rs['rounds_3plus']['mean']:.1f}±{rs['rounds_3plus']['std']:.1f} "
          f"({rs['rounds_3plus']['min']}~{rs['rounds_3plus']['max']}) | 4+회차 {rs['rounds_4plus']['mean']:.2f}")
    print("-" * 96)
    print("[2] 20장 구간")
    for key in ('div20_strict', 'div20_relax'):
        d = single[key]
        print(f"  {d['name']:<26}: avg={d['avg_best_match']:.3f} | 3+회차={d['rounds_3plus']}/{H} | "
              f"4+회차={d['rounds_4plus']} | 3+티켓={d['total_3plus_tickets']} | 유니크={d['avg_unique_cover']:.0f}")
    for key, lab in (('rand20_uniform', '무작위 20장(uniform)'), ('rand20_weighted', '가중무작위 20장')):
        rr = rnd[key]
        print(f"  {lab:<26}: avg={rr['avg_best_match']['mean']:.3f} | "
              f"3+회차 {rr['rounds_3plus']['mean']:.1f}±{rr['rounds_3plus']['std']:.1f} "
              f"({rr['rounds_3plus']['min']}~{rr['rounds_3plus']['max']}) | "
              f"4+회차 {rr['rounds_4plus']['mean']:.2f}±{rr['rounds_4plus']['std']:.2f} "
              f"({rr['rounds_4plus']['min']}~{rr['rounds_4plus']['max']}) | "
              f"3+티켓 {rr['total_3plus_tickets']['mean']:.1f}")
    print("=" * 96)

    out = {
        'meta': {
            'latest_round': latest_round, 'train_until': train_until, 'holdout': H,
            'K': args.K, 'seeds': Sd, 'weights': wlabel,
            'candidate_sample': args.candidate_sample, 'div_candidate': args.div_candidate,
            'note': 'pool 1회 채점(train 고정); 무작위/가중무작위/다양성 모두 극단성 풀(K) 내 선택',
        },
        'single_path': single,
        'random_seed_dist': rnd,
    }
    outpath = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: {args.out}")


if __name__ == '__main__':
    main()
