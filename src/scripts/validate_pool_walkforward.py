"""
극단성 풀 walk-forward 미래검증 - 풀이 과거 과적합인가, 미래에도 당첨을 보존하나

가드레일(워크플로우 회의론 검증)이 제안한 방법론 의무:
  "단일 극단성점수 컷(K)의 미래 hold-out 검증" - 과거로 만든 풀이 그 이후(미래) 당첨조합을
  무작위 풀보다 잘 보존(coverage)하는지 여러 시점에서 일관성 확인.

방법:
  여러 train cutoff t에 대해:
    1. t회까지 당첨번호로만 ExtremenessScorer fit (미래 누수 없음, 균등가중=점수자체 검증)
    2. 8.14M 채점 -> 점수 하위 K개 = 풀, cutoff 점수 계산
    3. 미래(t+1 ~ 1226) 당첨조합의 점수 <= cutoff 비율 = coverage
    4. baseline = K/8.14M (무작위 풀의 기대 coverage). lift = coverage / baseline.
  lift가 여러 시점에서 일관되게 >1 이면 극단성 풀이 미래에도 유효(견고).
  lift ~1 이면 풀 축소는 하되 미래 보존 이득은 무작위와 동일(점수 신호 약함).

주의: 가중치(extremeness_weights.json)는 전체데이터 최적화라 미래누수 위험 -> 여기선 균등가중
  (순수 극단성 점수)으로 검증. 가중 효과는 별도(메모리상 AUC~0.505로 미미).

[2026-07-04 통계 정직화] cutoff별 future 구간(r>t 전체)은 서로 '중첩'된다(예: cutoff 800의
  future가 1100의 future를 완전 포함) -> fold간 비독립이라 종합 평균/최소는 참고용이며 독립
  표본 요약이 아니다. 각 fold lift에 Wilson 95% 하한(lift_lcb)을 병기하고, 판정은 자의적
  임계(min>1.05) 대신 CI 기반(전 fold lift_lcb>1)으로 한다. 비중첩 엄밀 설계는
  validate_endtoend_partialmatch_walkforward.py(window 분리)가 담당.

사용법: python src/scripts/validate_pool_walkforward.py --K 1500000
"""
import os
import sys
import math
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


def _wilson_lower(x, n, z=1.96):
    """이항 비율 Wilson 95% 하한. [2026-07-04] lift 불확실성 병기용 (n=0 방어)."""
    if n == 0:
        return 0.0
    p = x / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2 * n)
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - rad) / denom)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=1_500_000)
    ap.add_argument('--cutoffs', type=str, default='800,900,1000,1100,1150',
                    help='train cutoff 회차들 (쉼표구분)')
    ap.add_argument('--out', type=str, default='results/pool_walkforward.json')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS

    db = DatabaseManager()
    all_rows = sorted(((r, sorted(int(x) for x in s.split(',')))
                       for r, s, _ in db.get_all_numbers()), key=lambda x: x[0])
    latest = all_rows[-1][0]
    cutoffs = [int(x) for x in args.cutoffs.split(',')]
    baseline = args.K / TOTAL_COMBINATIONS

    print("=" * 96)
    print(f"극단성 풀 walk-forward 미래검증  |  최신 {latest}  K={args.K:,}  "
          f"baseline(무작위 coverage)={baseline*100:.2f}%")
    print("=" * 96)

    # 8.14M 조합은 한 번만 생성(재사용)
    t0 = time.time()
    combos = ExtremenessScorer.all_combinations()
    print(f"  조합 생성 {time.time()-t0:.1f}s ({len(combos):,})")

    results = []
    for t in cutoffs:
        train = np.array([nums for r, nums in all_rows if r <= t], dtype=np.int16)
        future = np.array([nums for r, nums in all_rows if r > t], dtype=np.int16)
        if len(future) < 30:
            print(f"  [skip] cutoff {t}: 미래 {len(future)}회 (너무 적음)")
            continue

        ts = time.time()
        scorer = ExtremenessScorer(db)   # 균등가중(순수 점수)
        scorer.fit(train)
        scores = scorer.score(combos)
        cutoff_score = ExtremenessScorer.cutoff_for_size(scores, args.K)
        pool_size = int((scores <= cutoff_score).sum())

        future_scores = scorer.score(future)
        in_pool = future_scores <= cutoff_score
        coverage = float(in_pool.mean())
        lift = coverage / baseline
        # [2026-07-04] 불확실성 병기: coverage Wilson 95% 하한 -> lift 하한.
        # future 수십~수백 회면 lift SE ~0.2대라 fold간 lift 차이 대부분이 노이즈 범위임을 정직 표시.
        cov_lcb = _wilson_lower(int(in_pool.sum()), int(len(future)))
        lift_lcb = cov_lcb / baseline

        # 과거(train) 자기 coverage도 참고(과적합 정도): train 당첨이 풀에 얼마나
        train_scores = scorer.score(train)
        train_cov = float((train_scores <= cutoff_score).mean())

        results.append({
            'cutoff': t, 'future_rounds': int(len(future)),
            'pool_size': pool_size, 'removal_pct': round((1 - pool_size / TOTAL_COMBINATIONS) * 100, 2),
            'future_coverage': round(coverage * 100, 2),
            'train_coverage': round(train_cov * 100, 2),
            'lift': round(lift, 3),
            'lift_lcb': round(lift_lcb, 3),  # [2026-07-04] Wilson 95% 하한 기반 lift 하한
            'overfit_gap': round((train_cov - coverage) * 100, 2),  # train-future 차이(클수록 과적합)
        })
        print(f"  cutoff {t:>4} | 미래 {len(future):>3}회 | 풀 {pool_size:,} (제거 {(1-pool_size/TOTAL_COMBINATIONS)*100:.1f}%) "
              f"| 미래커버 {coverage*100:>5.2f}% | 과거커버 {train_cov*100:>5.2f}% | "
              f"lift {lift:.3f} (95%하한 {lift_lcb:.3f}) | 과적합갭 {(train_cov-coverage)*100:+.2f}%p | {time.time()-ts:.0f}s")

    # 종합
    if results:
        lifts = np.array([r['lift'] for r in results])
        lcbs = np.array([r['lift_lcb'] for r in results])
        covs = np.array([r['future_coverage'] for r in results])
        gaps = np.array([r['overfit_gap'] for r in results])
        print("-" * 96)
        print(f"  [종합] lift 평균 {lifts.mean():.3f} (범위 {lifts.min():.3f}~{lifts.max():.3f}, std {lifts.std():.3f})")
        print(f"         미래커버 평균 {covs.mean():.2f}% (무작위 {baseline*100:.2f}%)")
        print(f"         과적합갭 평균 {gaps.mean():+.2f}%p (작을수록 견고, 큰 양수면 과거과적합)")
        print("  [주의] cutoff별 future 구간은 중첩(r>t 전체) -> fold간 비독립이라 위 평균/최소는 참고용")
        # [2026-07-04] 자의적 임계(min>1.05) 대신 CI 기반 판정: 전 fold Wilson 95% 하한 lift>1 이어야 견고.
        verdict = ("극단성 풀이 미래에도 일관되게 유효(견고: 전 fold lift 95% 하한>1)" if lcbs.min() > 1.0
                   else "lift>1이나 95% CI가 1을 포함(무작위와 비유의) - 풀축소 대비 미래보존 이득 제한적"
                   if lifts.mean() > 1.0
                   else "미래 보존 이득 없음(무작위와 동일) - 점수 신호 미약")
        print(f"  [판정] {verdict}")

    out = {
        'meta': {'latest': latest, 'K': args.K, 'baseline_pct': round(baseline * 100, 3),
                 'cutoffs': cutoffs, 'note': '균등가중 순수 극단성 점수, 미래 누수 없음'},
        'results': results,
    }
    outpath = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: {args.out}")


if __name__ == '__main__':
    main()
