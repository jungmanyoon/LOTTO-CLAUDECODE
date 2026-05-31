"""
극단성 제거 + 5장 다양성 통합 예측 파이프라인 (사용자 전략 end-to-end)

흐름 (2026-05-31 셋이 합의한 신 아키텍처):
  1. ExtremenessScorer로 8.14M 전수 채점 (마할라노비스 + 희귀패턴 페널티)
  2. 목표 풀 크기 K(기본 1.5M, hold-out Lift 최고점)로 극단 상위 제거 -> 남은 풀
  3. FrequencyAnalyzer로 번호 가중치 산출 (빈도/최근성 약신호 결합)
  4. DiversitySelector(가중 max-coverage 그리디)로 5장 선택 -> 번호 커버리지 극대화

평가 모드(--evaluate): hold-out 최근 H회에 대해
  "다양성 5장" vs "무작위 5장(같은 풀)"의 best-match 분포 비교 -> 다양성 우위 정량 검증.

사용법:
  python src/scripts/generate_diverse_predictions.py                 # 1226 기준 5세트 생성
  python src/scripts/generate_diverse_predictions.py --K 1500000
  python src/scripts/generate_diverse_predictions.py --evaluate --holdout 100
"""
import os
import sys
import time
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


def build_pool(scorer, combos, scores, K):
    """가장 덜 극단적인 K개 인덱스 + 그 점수(품질=-극단성)."""
    idx = scorer.select_pool(scores, K)
    return idx, -scores[idx]  # quality = 낮은 극단성일수록 높음


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=1_500_000, help='목표 풀 크기 (기본 1.5M)')
    ap.add_argument('--tickets', type=int, default=5)
    ap.add_argument('--evaluate', action='store_true', help='hold-out 다양성 vs 무작위 평가')
    ap.add_argument('--holdout', type=int, default=100)
    ap.add_argument('--spread', type=float, default=0.5, help='번호 가중치 진폭(0=균등)')
    ap.add_argument('--candidate-sample', type=int, default=30000)
    ap.add_argument('--weights', type=str, default='configs/extremeness_weights.json',
                    help='PoolOptimizer가 저장한 가중치 JSON (없으면 균등 가중)')
    args = ap.parse_args()

    import json
    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
    from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

    db = DatabaseManager()
    all_rows = [(r, s) for r, s, _ in db.get_all_numbers()]
    latest_round = max(r for r, _ in all_rows)

    print("=" * 92)
    print(f"극단 제거(K={args.K:,}) + 5장 다양성 예측 파이프라인  |  최신 회차 {latest_round}")
    print("=" * 92)

    if args.evaluate:
        train_until = latest_round - args.holdout
        holdout_rounds = [(r, s) for r, s in all_rows if r > train_until]
        win_train = np.array([sorted(int(x) for x in s.split(',')) for r, s in all_rows if r <= train_until], dtype=np.int16)
    else:
        train_until = latest_round
        holdout_rounds = []
        win_train = np.array([sorted(int(x) for x in s.split(',')) for r, s in all_rows], dtype=np.int16)

    t0 = time.time()
    # 최적화된 가중치 로드 (있으면 가중 마할라노비스 + 페널티 가중 적용)
    weights_loaded = "균등(기본)"
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
        # 가중 마할라노비스: cov_inv -> S^T cov_inv S
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
        weights_loaded = f"최적화({args.weights}, AUC={wj.get('metrics',{}).get('auc_separation',0):.3f})"
    else:
        scorer = ExtremenessScorer(db)
        scorer.fit(win_train)
    combos = ExtremenessScorer.all_combinations()
    scores = scorer.score(combos)
    print(f"  채점 완료: {time.time()-t0:.1f}s  |  가중치: {weights_loaded}")

    pool_idx, pool_quality = build_pool(scorer, combos, scores, args.K)
    pool_combos = combos[pool_idx]  # (K,6)
    print(f"  풀 형성: {len(pool_idx):,}개 (전체의 {len(pool_idx)/TOTAL_COMBINATIONS*100:.1f}%, "
          f"{(1-len(pool_idx)/TOTAL_COMBINATIONS)*100:.1f}% 제거)")

    # 번호 가중치 (빈도/최근성)
    fa = FrequencyAnalyzer(db)
    weights = fa.compute_weights(until_round=train_until, spread=args.spread)
    top5 = np.argsort(-weights)[:5] + 1
    bot5 = np.argsort(weights)[:5] + 1
    print(f"  번호 가중치: 강세 {list(top5)} / 약세 {list(bot5)} (spread={args.spread})")

    pool_list = [tuple(int(x) for x in row) for row in pool_combos]

    if not args.evaluate:
        # ---- 실제 5세트 생성 ----
        selector = DiversitySelector(number_weights=weights)
        t0 = time.time()
        tickets = selector.select(pool_list, num_tickets=args.tickets,
                                  quality=pool_quality, candidate_sample=args.candidate_sample)
        rep = DiversitySelector.coverage_report(tickets)
        print(f"  5장 선택: {time.time()-t0:.1f}s")
        print("-" * 92)
        print(f"  >>> 회차 {latest_round+1} 예측 5세트 (극단 제거 풀 + 다양성 커버리지 극대화)")
        print("-" * 92)
        for i, t in enumerate(tickets, 1):
            print(f"    세트 {i}: {sorted(t)}")
        print("-" * 92)
        print(f"  커버리지: {rep['unique_numbers']}/45 번호 ({rep['coverage_pct']:.0f}%), "
              f"최대 티켓간겹침 {rep['max_pairwise_overlap']}, 평균겹침 {rep['avg_pairwise_overlap']:.2f}")
        print(f"  미커버 번호: {rep['missing_numbers']}")
        print("=" * 92)
        return

    # ---- 평가 모드: 다양성 vs 무작위 ----
    selector = DiversitySelector(number_weights=weights)
    rng = np.random.RandomState(0)
    div_best, rnd_best = [], []
    div_hits3plus, rnd_hits3plus = 0, 0  # 5장 중 1장이라도 3+ 맞춘 회차 수

    print(f"  [평가] hold-out {len(holdout_rounds)}회: 다양성 5장 vs 무작위 5장(동일 풀)")
    print("-" * 92)
    for r, s in holdout_rounds:
        wn = set(int(x) for x in s.split(','))
        # 다양성 5장
        div = selector.select(pool_list, num_tickets=args.tickets,
                              quality=pool_quality, candidate_sample=args.candidate_sample,
                              seed=r, local_search_iters=50)
        db_best = max(best_match(t, wn) for t in div)
        div_best.append(db_best)
        if db_best >= 3:
            div_hits3plus += 1
        # 무작위 5장 (같은 풀)
        ridx = rng.choice(len(pool_list), args.tickets, replace=False)
        rb = max(best_match(pool_list[i], wn) for i in ridx)
        rnd_best.append(rb)
        if rb >= 3:
            rnd_hits3plus += 1

    div_best = np.array(div_best); rnd_best = np.array(rnd_best)
    print(f"  다양성 5장: 평균 best-match={div_best.mean():.3f}, 3+회차={div_hits3plus}/{len(holdout_rounds)}, "
          f"분포 {np.bincount(div_best, minlength=5)[:5]}")
    print(f"  무작위 5장: 평균 best-match={rnd_best.mean():.3f}, 3+회차={rnd_hits3plus}/{len(holdout_rounds)}, "
          f"분포 {np.bincount(rnd_best, minlength=5)[:5]}")
    print("-" * 92)
    print(f"  다양성 우위(평균 best-match): {(div_best.mean()-rnd_best.mean()):+.3f}  "
          f"({'다양성 유리' if div_best.mean()>rnd_best.mean() else '차이 미미/무작위'})")
    print("=" * 92)


if __name__ == '__main__':
    main()
