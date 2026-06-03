"""
극단성 점수 -> 전체 풀 크기 / hold-out 커버리지 곡선 분석기

설계 합의 (2026-05-31, Codex gpt-5.5 + Gemini 3.1-pro + Claude):
  - "16개 AND 필터(임계값 레버가 죽어 풀이 항상 807만에 고정)"를 폐기하고
    단일 극단성 점수(ExtremenessScorer) + 목표 풀 크기 컷오프로 전환.
  - 이 스크립트는 사용자 요청 #1, #2를 구현:
      #1 "임계값 -> 전체 풀 크기" 곡선을 실제 8.14M으로 계산
      #2 "다 걸리기 직전의 최적 임계값"(knee) 탐지

핵심: 목표 풀 크기 K가 곧 "임계값"이다(단조·직접 제어). 각 K에 대해:
  - pool_ratio = K / 8,145,060
  - holdout_coverage = 최근 H회 당첨번호 중 풀에 포함되는 비율 (과적합 차단: 학습=R-H 이전)
  - lift = holdout_coverage / pool_ratio  (Codex/Gemini 합의 주지표; hold-out 필수)
  - marginal_efficiency = d(coverage)/d(pool_ratio)  (1에 가까울수록 "무작위 제거와 동일")

knee 정의(둘 다 보고):
  (A) Kneedle: 정규화 (pool_ratio, coverage) 곡선에서 대각선 대비 수직편차 최대점
  (B) marginal: marginal_efficiency 가 tau(기본 1.0) 를 처음 넘는 지점
      = "이 아래로 더 줄이면 극단이 아니라 정상 영역을 제거하기 시작"

사용법:
  python src/scripts/analyze_threshold_pool_curve.py
  python src/scripts/analyze_threshold_pool_curve.py --holdout 150 --out results/threshold_pool_curve.json
"""
import os
import sys
import json
import time
import argparse
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np


def kneedle(x: np.ndarray, y: np.ndarray) -> int:
    """정규화 곡선에서 대각선 대비 수직편차 최대 인덱스 (단조 증가 곡선 가정).
    x: pool_ratio 오름차순(0->1), y: coverage 오름차순. 반환: knee 인덱스."""
    xn = (x - x.min()) / (x.max() - x.min() + 1e-12)
    yn = (y - y.min()) / (y.max() - y.min() + 1e-12)
    diff = yn - xn  # concave: 대각선 위로 볼록한 정도
    return int(np.argmax(diff))


def main():
    parser = argparse.ArgumentParser(description="극단성 점수 -> 풀크기/커버리지 곡선")
    parser.add_argument('--holdout', type=int, default=150, help='hold-out 검증 회차 수(최근 N회)')
    parser.add_argument('--out', type=str, default='results/threshold_pool_curve.json')
    parser.add_argument('--tau', type=float, default=1.0, help='marginal knee 기준 (무작위=1.0)')
    args = parser.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS

    print("=" * 96)
    print("극단성 점수 -> 전체 풀 크기 / hold-out 커버리지 곡선 (과필터링 진단 + 최적 임계값)")
    print("=" * 96)

    db = DatabaseManager()
    all_rows = [(r, s) for r, s, _ in db.get_all_numbers()]
    latest_round = max(r for r, _ in all_rows)
    train_until = latest_round - args.holdout
    print(f"  최신 회차            : {latest_round}")
    print(f"  학습 범위            : 1 ~ {train_until}  (hold-out: {train_until+1} ~ {latest_round}, {args.holdout}회)")

    # 학습(hold-out 이전) / 검증(hold-out) 당첨번호
    win_train = np.array([sorted(int(x) for x in s.split(',')) for r, s in all_rows if r <= train_until], dtype=np.int16)
    win_holdout = np.array([sorted(int(x) for x in s.split(',')) for r, s in all_rows if r > train_until], dtype=np.int16)

    t0 = time.time()
    scorer = ExtremenessScorer(db)
    scorer.fit(win_train)
    combos = ExtremenessScorer.all_combinations()
    scores = scorer.score(combos)
    s_train = scorer.score(win_train)
    s_holdout = scorer.score(win_holdout)
    print(f"  채점 완료            : {time.time()-t0:.1f}s (전수 {TOTAL_COMBINATIONS:,} + 당첨)")
    print(f"  활성 특징            : {scorer.CONTINUOUS_FEATURES}")
    print(f"  페널티 차원          : {scorer.PENALTY_DIMS}")
    print("=" * 96)

    # 목표 풀 크기 그리드 (로그 간격 + 주요 지점)
    grid_K = [50_000, 100_000, 200_000, 300_000, 500_000, 700_000, 1_000_000,
              1_500_000, 2_000_000, 3_000_000, 4_000_000, 6_000_000, 8_000_000]
    grid_K = [k for k in grid_K if k <= TOTAL_COMBINATIONS]

    curve = []
    print(f"  {'목표풀K':>10} {'풀비율':>7} {'cutoff':>7} {'hold커버':>8} {'insmpl':>7} {'Lift':>6} {'한계효율':>7}")
    print("  " + "-" * 80)
    prev = None
    for K in grid_K:
        cutoff = ExtremenessScorer.cutoff_for_size(scores, K)
        # 동점 견고성: 실제 풀비율을 cutoff 이하 실측값으로 보정 (lift 과대평가 방지)
        pool_ratio = float((scores <= cutoff).mean())
        cov_hold = float((s_holdout <= cutoff).mean())
        cov_ins = float((s_train <= cutoff).mean())
        lift = cov_hold / pool_ratio if pool_ratio > 0 else 0.0
        row = {
            'target_K': K, 'pool_ratio': pool_ratio, 'cutoff': cutoff,
            'holdout_coverage': cov_hold, 'insample_coverage': cov_ins, 'lift': lift,
        }
        # 한계 효율 d(cov)/d(pool_ratio) (이전 그리드 대비)
        if prev is not None:
            dcov = cov_hold - prev['holdout_coverage']
            dpr = pool_ratio - prev['pool_ratio']
            marg = dcov / dpr if dpr != 0 else 0.0
        else:
            marg = float('nan')
        row['marginal_efficiency'] = marg
        curve.append(row)
        prev = row
        print(f"  {K:>10,} {pool_ratio*100:6.2f}% {cutoff:7.2f} {cov_hold*100:7.1f}% "
              f"{cov_ins*100:6.1f}% {lift:6.2f} {marg:7.2f}")
    print("  " + "-" * 80)

    # knee (A) Kneedle: pool_ratio 오름차순, coverage 오름차순
    pr = np.array([r['pool_ratio'] for r in curve])
    cv = np.array([r['holdout_coverage'] for r in curve])
    knee_idx = kneedle(pr, cv)
    knee_A = curve[knee_idx]

    # knee (B) 자유제거 경계(free-removal boundary):
    #   marginal_efficiency[i] = 풀을 curve[i-1]->curve[i]로 키울 때 얻는 커버리지/풀비율
    #   = 반대로 curve[i]->curve[i-1]로 "제거"할 때의 비용(coverage-per-pool).
    #   marginal < tau(1.0) 구간 = "제거해도 무작위보다 손해 안 보는(당첨번호가 거의 없는) 극단" -> 공짜 제거.
    #   큰 K에서 작은 K로 내려가며 첫 marginal>=tau(제거 비용이 무작위 이상) 지점이 자유제거 경계.
    knee_B = None
    for i in range(len(curve) - 1, 0, -1):
        m = curve[i]['marginal_efficiency']
        if m == m and m >= args.tau:  # m==m : NaN 아님
            knee_B = curve[i]
            break

    print(f"\n  [knee A - Kneedle]   목표풀 K={knee_A['target_K']:,} "
          f"(풀 {knee_A['pool_ratio']*100:.1f}%, hold커버 {knee_A['holdout_coverage']*100:.1f}%, lift {knee_A['lift']:.2f})")
    if knee_B:
        print(f"  [knee B - 자유제거경계] K~{knee_B['target_K']:,} 위쪽({knee_B['pool_ratio']*100:.1f}% 초과)은 "
              f"당첨번호 거의 없는 극단 -> 무손실 제거 가능. 이 아래로는 커버리지 비용 발생(사용자 선택).")
    else:
        print(f"  [knee B - 자유제거경계] 전 구간 한계효율 < tau({args.tau}) -> 어디까지 줄여도 무작위보다 유리")

    # 사용자 전략 해석
    print(f"\n  [해석] 당첨번호는 통계적으로 무작위 조합과 분포가 유사 -> 풀을 줄이면 커버리지도 감소.")
    print(f"         단 Lift>1 구간은 '극단 제거가 무작위보다 유리'함을 의미(사용자 전략의 정량 근거).")
    print(f"         사용자 전략(극단 최대 제거)에 따라 knee 이하로 K를 더 낮춰 강하게 제거할 수도 있음.")

    out_path = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'latest_round': latest_round, 'train_until': train_until, 'holdout': args.holdout,
            'total_combinations': TOTAL_COMBINATIONS,
            'features': scorer.CONTINUOUS_FEATURES, 'penalty_dims': scorer.PENALTY_DIMS,
            'curve': curve,
            'knee_kneedle': knee_A, 'knee_marginal': knee_B,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  [저장] {out_path}")
    print("=" * 96)


if __name__ == '__main__':
    main()
