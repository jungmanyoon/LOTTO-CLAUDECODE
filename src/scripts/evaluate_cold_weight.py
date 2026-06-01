"""
콜드(미출현) 가중치 비중 효과 실측 - 5장 다양성에서 콜드 강조가 도움되나

배경: diversity_selector.FrequencyAnalyzer.compute_weights는 이미
  signal = 0.5*freq_z + 0.3*recency_z + 0.2*age_z(=콜드/오래안나옴) 로 콜드 신호를 0.2 비중 반영.
사용자 요청("콜드번호 반영")은 사실상 "이 콜드 비중(age_z 계수)을 올리면 5장 성능이 좋아지나"의 실측.
mean_reversion_analyzer의 reversion_strength도 본질적으로 age_z와 같은 축이라 별도 연결은 중복.

방법(production 코드 미변경, 실측만):
  compute_weights 로직을 복제해 (fz,rz,az) 비중을 파라미터화. 여러 비중 프로파일로
  hold-out 100회 5장 다양성 선택 -> 3+회수/4+회수/평균best 비교. 무작위5장도 baseline.
  콜드 강조가 3+회수를 유의하게 늘리면 production 비중 상향 검토, 아니면 현행 유지.

사용법: python src/scripts/evaluate_cold_weight.py --holdout 100 --seeds 5
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


def compute_weights_custom(rows, until_round, fz_w, rz_w, az_w, spread=0.5, recency_window=30):
    """diversity_selector.compute_weights 로직 복제 + (fz,rz,az) 비중 파라미터화."""
    use = [(r, nums) for r, nums in rows if until_round is None or r <= until_round]
    if not use:
        return np.ones(45, dtype=np.float32)
    max_round = max(r for r, _ in use)
    long_freq = np.zeros(46); recent_freq = np.zeros(46)
    last_seen = {n: 0 for n in range(1, 46)}
    for r, nums in use:
        for n in nums:
            long_freq[n] += 1
            if r > max_round - recency_window:
                recent_freq[n] += 1
            last_seen[n] = max(last_seen[n], r)
    lf = long_freq[1:46]; rf = recent_freq[1:46]
    fz = (lf - lf.mean()) / (lf.std() + 1e-9)
    rz = (rf - rf.mean()) / (rf.std() + 1e-9)
    age = np.array([max_round - last_seen[n] for n in range(1, 46)], dtype=np.float64)
    az = (age - age.mean()) / (age.std() + 1e-9)
    signal = fz_w * fz + rz_w * rz + az_w * az
    s = 1.0 / (1.0 + np.exp(-signal))
    w = (1.0 - spread) + 2.0 * spread * s
    return w.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=1_500_000)
    ap.add_argument('--holdout', type=int, default=100)
    ap.add_argument('--seeds', type=int, default=5)
    ap.add_argument('--candidate-sample', type=int, default=20000)
    ap.add_argument('--out', type=str, default='results/cold_weight_eval.json')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
    from src.core.diversity_selector import DiversitySelector

    db = DatabaseManager()
    all_rows = sorted(((r, sorted(int(x) for x in s.split(','))) for r, s, _ in db.get_all_numbers()),
                      key=lambda x: x[0])
    latest = all_rows[-1][0]
    train_until = latest - args.holdout
    holdout = [(r, set(nums)) for r, nums in all_rows if r > train_until]
    win_train = np.array([nums for r, nums in all_rows if r <= train_until], dtype=np.int16)

    print("=" * 92)
    print(f"콜드 가중치 효과 실측  |  최신 {latest}  train<= {train_until}  hold-out {len(holdout)}회  seeds={args.seeds}")
    print("=" * 92)

    # 극단성 풀 1회 (최적화 가중치 적용 = production 정합)
    t0 = time.time()
    wpath = os.path.join(PROJECT_ROOT, 'configs/extremeness_weights.json')
    if os.path.exists(wpath):
        wj = json.load(open(wpath, encoding='utf-8')); bp = wj.get('best_params', {})
        pw = {d: bp.get(f"pw_{d}", 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
        scorer = ExtremenessScorer(db, alpha=bp.get('alpha', 0.5), penalty_weights=pw)
        scorer._feature_scale = np.array([bp.get(f"fw_{f}", 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES], dtype=np.float32)
        scorer.fit(win_train)
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
    else:
        scorer = ExtremenessScorer(db); scorer.fit(win_train)
    combos = ExtremenessScorer.all_combinations()
    scores = scorer.score(combos)
    pool_idx = ExtremenessScorer.select_pool(scores, args.K)
    pool_list = [tuple(int(x) for x in row) for row in combos[pool_idx]]
    quality = -scores[pool_idx]
    N = len(pool_list)
    print(f"  채점/풀 {time.time()-t0:.1f}s  풀 {N:,}")

    # 비중 프로파일 (fz, rz, az)
    profiles = {
        'cold_off (0.6/0.4/0.0)': (0.6, 0.4, 0.0),
        'baseline (0.5/0.3/0.2)': (0.5, 0.3, 0.2),
        'cold_mid (0.4/0.25/0.35)': (0.4, 0.25, 0.35),
        'cold_strong (0.3/0.2/0.5)': (0.3, 0.2, 0.5),
        'cold_only (0.0/0.0/1.0)': (0.0, 0.0, 1.0),
    }
    rows = [(r, nums) for r, nums in all_rows]

    def eval_weights(w):
        sel = DiversitySelector(number_weights=w)
        best=[]; n3=0; n4=0
        for r, wn in holdout:
            bms=[]
            for sd in range(args.seeds):
                tickets = sel.select(pool_list, num_tickets=5, quality=quality,
                                     candidate_sample=args.candidate_sample, seed=r*7+sd, local_search_iters=40)
                bms.append(max(len(set(t)&wn) for t in tickets))
            bm=max(bms) if args.seeds>1 else bms[0]  # seed 중 최선? 아니 평균이 공정
            bm=float(np.mean(bms))
            best.append(bm)
            # 3+/4+는 seed 평균이 회차당 기대. 회차 단위 판정은 평균 best 기준
            if np.mean(bms)>=3: n3+=1
            if np.mean(bms)>=4: n4+=1
        return np.array(best), n3, n4

    print("-"*92)
    out={}
    for name,(fzw,rzw,azw) in profiles.items():
        w = compute_weights_custom(rows, train_until, fzw, rzw, azw)
        t1=time.time()
        best,n3,n4 = eval_weights(w)
        out[name]={'avg_best':round(float(best.mean()),3),'rounds_3plus':n3,'rounds_4plus':n4,
                   'top5_weighted_numbers':[int(x) for x in (np.argsort(-w)[:5]+1)]}
        print(f"  {name:<26} avg={best.mean():.3f} | 3+회차={n3}/{len(holdout)} | 4+회차={n4} | 강세번호{[int(x) for x in (np.argsort(-w)[:5]+1)]} | {time.time()-t1:.0f}s")

    # 무작위 5장 baseline (seed 평균)
    rng=np.random.RandomState(0)
    rbest=[]; rn3=0
    for r,wn in holdout:
        bms=[max(len(set(pool_list[i])&wn) for i in rng.choice(N,5,replace=False)) for _ in range(args.seeds)]
        rbest.append(np.mean(bms))
        if np.mean(bms)>=3: rn3+=1
    print(f"  {'random5 (baseline)':<26} avg={np.mean(rbest):.3f} | 3+회차={rn3}/{len(holdout)}")
    out['random5']={'avg_best':round(float(np.mean(rbest)),3),'rounds_3plus':rn3}
    print("="*92)

    js={'meta':{'latest':latest,'train_until':train_until,'holdout':len(holdout),'K':args.K,'seeds':args.seeds},'results':out}
    op=os.path.join(PROJECT_ROOT,args.out); os.makedirs(os.path.dirname(op),exist_ok=True)
    json.dump(js,open(op,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(f"  결과 저장: {args.out}")


if __name__ == '__main__':
    main()
