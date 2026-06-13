# -*- coding: utf-8 -*-
"""
신규 극단성 특징 후보의 walk-forward blind 1차 스크리닝.

설계(2026-06-06, Codex gpt-5.5 + Gemini 3.1-pro + 웹 + Claude 합의):
  - 최종 예측은 극단성 풀(ExtremenessScorer) 이 좌우한다. "필터 추가"=극단성 점수에 새 특징 추가.
  - 후보를 '추가 꼬리페널티 항'으로 평가: variant_score = baseline_score + penalty_cand(value).
    -> baseline 점수에 더하기만 하면 되어 빠르고, 마할라노비스 정규성을 깨지 않는다(전문가 권고 정합).
  - blind: fold 마다 train_until 이하 당첨번호로만 scorer.fit + 페널티표 학습. holdout=그 이후 window 회차.
  - 주지표(전문가 합의, 등수적중은 너무 희소): (1) 당첨번호 점수 percentile(낮을수록 풀 중심=좋음),
    (2) 풀 보존율@K(높을수록 좋음). baseline 대비 fold 별 delta 와 개선 fold 비율 보고.
  - 이건 '1차 스크리닝'이다. 신호 있는 후보만 이후 순열검정+부트스트랩+BH-FDR+untouched hold-out 로
    엄격 확정한다(다중비교 착시 방지). 신호 0이면 정직하게 기각.

ASCII 출력(Windows), UTF-8, 이모지 금지.
"""
import os
import sys
import math
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.db_manager import DatabaseManager
from src.core.extremeness_scorer import ExtremenessScorer

K_POOL = 1_500_000


# ----------------------------------------------------------------------
# 후보 특징 함수: (M,6) int -> (M,) 값 (정수 또는 실수). positional_tail 은 별도 처리.
# ----------------------------------------------------------------------
def f_adjacent_pairs(c):
    g = np.diff(c.astype(np.int16), axis=1)
    return (g == 1).sum(axis=1).astype(np.int32)


def f_min_gap(c):
    g = np.diff(c.astype(np.int16), axis=1)
    return g.min(axis=1).astype(np.int32)


def f_empty_sections(c):
    sec = np.minimum((c.astype(np.int16) - 1) // 10, 4)  # 0..4
    M = c.shape[0]
    used = np.zeros((M, 5), dtype=bool)
    for s in range(5):
        used[:, s] = (sec == s).any(axis=1)
    return (5 - used.sum(axis=1)).astype(np.int32)


def f_mod3_max(c):
    r = c.astype(np.int16) % 3
    M = c.shape[0]
    best = np.zeros(M, dtype=np.int16)
    for k in range(3):
        best = np.maximum(best, (r == k).sum(axis=1))
    return best.astype(np.int32)


def f_mod5_max(c):
    r = c.astype(np.int16) % 5
    M = c.shape[0]
    best = np.zeros(M, dtype=np.int16)
    for k in range(5):
        best = np.maximum(best, (r == k).sum(axis=1))
    return best.astype(np.int32)


def f_digit_sum(c):
    ci = c.astype(np.int16)
    return ((ci // 10) + (ci % 10)).sum(axis=1).astype(np.int32)


def f_edge_band(c):
    ci = c.astype(np.int16)
    return (((ci <= 5) | (ci >= 41)).sum(axis=1)).astype(np.int32)


def f_gap_cv(c):
    g = np.diff(c.astype(np.float32), axis=1)
    mean = g.mean(axis=1)
    std = g.std(axis=1)
    return (std / np.maximum(mean, 1e-6)).astype(np.float32)


def f_last_digit_sum(c):
    return (c.astype(np.int16) % 10).sum(axis=1).astype(np.int32)


SCALAR_CANDIDATES = {
    'adjacent_pairs': f_adjacent_pairs,
    'min_gap': f_min_gap,
    'empty_sections': f_empty_sections,
    'mod3_max': f_mod3_max,
    'mod5_max': f_mod5_max,
    'digit_sum': f_digit_sum,
    'edge_band': f_edge_band,
    'gap_cv': f_gap_cv,
    'last_digit_sum': f_last_digit_sum,
}


# ----------------------------------------------------------------------
# 페널티 표(꼬리 -log 빈도) - train 당첨번호로 학습. 정수형은 배열 LUT, 실수형은 분위수 bin.
# ----------------------------------------------------------------------
def build_scalar_penalty(train_vals, alpha=0.5, nbins=12):
    train_vals = np.asarray(train_vals)
    is_int = np.allclose(train_vals, np.rint(train_vals)) and (np.ptp(train_vals) <= 60)
    N = len(train_vals)
    if is_int:
        tv = np.rint(train_vals).astype(np.int64)
        vmin = int(tv.min())
        vmax = int(tv.max())
        # 가능한 값 범위(관측 밖 값도 평활 + 최대페널티 대비)를 위해 약간 여유
        span = vmax - vmin + 1
        bins = max(span, 2)
        counts = np.bincount((tv - vmin), minlength=span).astype(np.float64)
        pen = -np.log((counts + alpha) / (N + alpha * bins))
        default = float(pen.max())

        def lut(vals):
            xi = np.rint(np.asarray(vals)).astype(np.int64) - vmin
            out = np.full(len(xi), default, dtype=np.float32)
            inb = (xi >= 0) & (xi < span)
            out[inb] = pen[xi[inb]].astype(np.float32)
            return out
        return lut
    else:
        edges = np.quantile(train_vals, np.linspace(0, 1, nbins + 1))
        inner = edges[1:-1]
        idx_train = np.digitize(train_vals, inner)
        counts = np.bincount(idx_train, minlength=nbins).astype(np.float64)
        pen = -np.log((counts + alpha) / (N + alpha * nbins))

        def lut(vals):
            ix = np.digitize(np.asarray(vals), inner)
            return pen[ix].astype(np.float32)
        return lut


def build_positional_penalty(train_winners, alpha=0.5):
    """정렬된 위치별(1~6) 값 분포 -log 빈도. 반환: combos(M,6) -> (M,) 페널티 합."""
    tw = np.sort(train_winners.astype(np.int64), axis=1)
    N = tw.shape[0]
    luts = []
    for p in range(6):
        counts = np.bincount(tw[:, p], minlength=46).astype(np.float64)  # 0..45
        pen = -np.log((counts + alpha) / (N + alpha * 45))
        luts.append(pen.astype(np.float32))

    def apply(combos):
        cc = np.sort(combos.astype(np.int64), axis=1)
        out = np.zeros(cc.shape[0], dtype=np.float32)
        for p in range(6):
            out += luts[p][cc[:, p]]
        return out
    return apply


# ----------------------------------------------------------------------
def main():
    folds = int(os.environ.get('CAND_FOLDS', '6'))
    window = int(os.environ.get('CAND_WINDOW', '40'))

    db = DatabaseManager()
    rows = []
    for r, t in db.get_numbers_with_bonus():
        rows.append((int(r), sorted(int(x) for x in t[:6])))
    rows.sort(key=lambda x: x[0])
    total = len(rows)
    all_rounds = np.array([r for r, _ in rows])
    all_nums = np.array([n for _, n in rows], dtype=np.int16)  # (T,6)

    first = max(1, total - folds * window)
    fold_specs = []
    s = first
    while s + window <= total:
        fold_specs.append((s, s + window))
        s += window
    print("[스크리닝] folds=%d window=%d, fold수=%d, 전체회차=%d" % (folds, window, len(fold_specs), total))

    all_combos = ExtremenessScorer.all_combinations()  # (8.14M,6) int8, read-only
    Mall = all_combos.shape[0]

    # 후보 값(전 조합) 1회 사전계산 (fold 무관). positional 은 fold별 LUT 필요.
    print("[스크리닝] 후보 특징 전수계산 중...", flush=True)
    cand_vals_all = {name: fn(all_combos) for name, fn in SCALAR_CANDIDATES.items()}

    cand_names = list(SCALAR_CANDIDATES.keys()) + ['positional_tail']
    # 누적: 후보별 fold별 delta(percentile), delta(retention)
    dpct = {c: [] for c in cand_names}
    dret = {c: [] for c in cand_names}

    for fi, (a, b) in enumerate(fold_specs):
        train_until = rows[a - 1][0]
        train_mask = all_rounds <= train_until
        train_w = all_nums[train_mask]               # (N,6)
        holdout_w = all_nums[a:b]                     # (W,6)

        scorer = ExtremenessScorer(db)
        scorer.fit(train_w)
        base_all = scorer.score(all_combos)           # (8.14M,) HEAVY
        base_sorted = np.sort(base_all)
        base_cut = base_sorted[K_POOL - 1]            # K번째 작은 점수 = 컷오프
        base_w = scorer.score(holdout_w)              # (W,)
        base_pct = np.searchsorted(base_sorted, base_w, side='right') / Mall
        base_ret = (base_w <= base_cut).astype(np.float32)
        bp = float(base_pct.mean())
        br = float(base_ret.mean())
        print("[fold %d] train<=%d holdout=%d  baseline 당첨 percentile=%.4f 보존율@K=%.3f"
              % (fi, train_until, len(holdout_w), bp, br), flush=True)

        for name in cand_names:
            if name == 'positional_tail':
                ap = build_positional_penalty(train_w)
                pen_all = ap(all_combos)
                pen_w = ap(holdout_w)
            else:
                fn = SCALAR_CANDIDATES[name]
                lut = build_scalar_penalty(fn(train_w))
                pen_all = lut(cand_vals_all[name])
                pen_w = lut(fn(holdout_w))
            var_all = base_all + pen_all
            var_sorted = np.sort(var_all)
            var_cut = var_sorted[K_POOL - 1]
            var_w = base_w + pen_w
            var_pct = float((np.searchsorted(var_sorted, var_w, side='right') / Mall).mean())
            var_ret = float((var_w <= var_cut).astype(np.float32).mean())
            dpct[name].append(bp - var_pct)   # +면 percentile 낮아짐 = 개선
            dret[name].append(var_ret - br)   # +면 보존율 높아짐 = 개선

    print("\n" + "=" * 78)
    print("[결과] 후보별 walk-forward 평균 delta (양수=baseline 대비 개선). 개선fold=개선된 fold수/총")
    print("%-18s | d_percentile(평균) | 개선fold | d_retention(평균) | 개선fold" % "후보")
    print("-" * 78)
    rank = []
    nf = len(fold_specs)
    for name in cand_names:
        mp = float(np.mean(dpct[name]))
        mr = float(np.mean(dret[name]))
        ip = int(np.sum(np.array(dpct[name]) > 0))
        ir = int(np.sum(np.array(dret[name]) > 0))
        rank.append((name, mp, ip, mr, ir))
    for name, mp, ip, mr, ir in sorted(rank, key=lambda x: -x[1]):
        print("%-18s | %+.6f         | %d/%d     | %+.5f         | %d/%d"
              % (name, mp, ip, nf, mr, ir, nf))
    print("=" * 78)
    print("[해석] d_percentile>0 + 개선fold가 대다수(>=%d/%d)면 1차 신호. 그 후보만 엄격검증 대상."
          % (int(0.7 * nf) + 1, nf))


if __name__ == '__main__':
    main()
