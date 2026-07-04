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

[2026-07-04 확장] 16필터 개념 잔여분 7종 추가(featmap 전수 대조): 정적 5종(max_quadrant_occ/
  max_multiple_cnt/iqr_outlier_cnt/ap_max_len/gp4_flag) + 동적 2종(max_match_history/
  prev_draw_overlap - 역사 의존이라 fold별 스냅샷/재계산, CAND_DYNAMIC=0 으로 생략 가능).
  결과를 results/candidate_features_walkforward.json 에도 저장(콘솔 전용 -> 영속화).

ASCII 출력(Windows), UTF-8, 이모지 금지.
"""
import os
import sys
import math
import json
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


# ----------------------------------------------------------------------
# [2026-07-04 후보 7종] 16필터 개념 잔여분 전수 소진 (featmap 대조 결과 미시험분).
# 정적 5종은 SCALAR_CANDIDATES 등록, 역사 의존 동적 2종(max_match_history/prev_draw_overlap)은
# main() 의 fold별 재계산 분기로 처리(사전계산 불가).
# ----------------------------------------------------------------------
def _bitmask(c):
    """(M,6) -> (M,) uint64 비트마스크 (번호 n -> bit n)."""
    ci = c.astype(np.uint64)
    bm = np.zeros(c.shape[0], dtype=np.uint64)
    for j in range(ci.shape[1]):
        bm |= np.uint64(1) << ci[:, j]
    return bm


def f_max_quadrant_occupancy(c):
    """balanced_quadrant(구필터 enabled:true, 스코어러 미표현): 1-11/12-22/23-33/34-45 최대 점유."""
    ci = c.astype(np.int16)
    q = np.minimum((ci - 1) // 11, 3)  # 0..3 (마지막 분할 34-45는 12개)
    best = np.zeros(c.shape[0], dtype=np.int16)
    for k in range(4):
        best = np.maximum(best, (q == k).sum(axis=1))
    return best.astype(np.int32)


def f_max_multiple_count(c):
    """multiple 필터 개념: k=3/4/5 배수 '정확 개수'의 최대 (mod_max 는 잔여류 근사였음)."""
    ci = c.astype(np.int16)
    best = np.zeros(c.shape[0], dtype=np.int16)
    for k in (3, 4, 5):
        best = np.maximum(best, (ci % k == 0).sum(axis=1))
    return best.astype(np.int32)


def f_iqr_outlier_count(c):
    """outlier_detection 필터 개념: 조합 내부 Tukey IQR(1.5x) 이상치 개수.
    combos 는 오름차순 정렬 규약이므로 6값 분위수를 선형보간 직접 계산(np.percentile 동치, 저메모리)."""
    cf = c.astype(np.float32)
    q1 = cf[:, 1] + 0.25 * (cf[:, 2] - cf[:, 1])   # 25% 위치=1.25
    q3 = cf[:, 3] + 0.75 * (cf[:, 4] - cf[:, 3])   # 75% 위치=3.75
    iqr = q3 - q1
    lo = (q1 - 1.5 * iqr)[:, None]
    hi = (q3 + 1.5 * iqr)[:, None]
    return (((cf < lo) | (cf > hi)).sum(axis=1)).astype(np.int32)


def f_ap_max_len(c):
    """arithmetic_sequence/fixed_step 통합 개념: 공차 자유 최장 등차수열 길이(2~6).
    모든 값쌍(15개)을 첫 두 항으로 보고 비트마스크로 체인 연장(벡터화)."""
    ci = c.astype(np.int16)
    bm = _bitmask(ci)
    M = c.shape[0]
    best = np.full(M, 2, dtype=np.int8)  # 임의 두 수는 항상 등차(길이 2)
    for i in range(5):
        for j in range(i + 1, 6):
            d = (ci[:, j] - ci[:, i]).astype(np.int16)
            ln = np.full(M, 2, dtype=np.int8)
            cur = (ci[:, j] + d).astype(np.int16)
            ok = np.ones(M, dtype=bool)
            for _ in range(4):
                valid = ok & (cur >= 1) & (cur <= 45)
                hit = np.zeros(M, dtype=bool)
                if valid.any():
                    hit[valid] = ((bm[valid] >> cur[valid].astype(np.uint64)) & np.uint64(1)).astype(bool)
                ln = ln + hit.astype(np.int8)
                ok = hit
                cur = cur + d
            best = np.maximum(best, ln)
    return best.astype(np.int32)


def _gp4_masks():
    """1..45 내 길이>=4 증가 등비수열(유리 공비 p/q>1)의 4항 비트마스크 전수 열거(수십 개)."""
    from math import gcd
    seen = set()
    for a in range(1, 46):
        for p in range(2, 46):
            for q in range(1, p):
                if gcd(p, q) != 1:
                    continue
                terms = [a]
                x = a
                ok = True
                for _ in range(3):
                    if (x * p) % q != 0:
                        ok = False
                        break
                    x = x * p // q
                    if x > 45:
                        ok = False
                        break
                    terms.append(x)
                if ok and len(set(terms)) == 4:
                    m = 0
                    for t in terms:
                        m |= (1 << t)
                    seen.add(m)
    return [np.uint64(m) for m in sorted(seen)]


_GP4_MASKS = _gp4_masks()


def f_gp4_flag(c):
    """geometric_sequence 필터 개념: 길이>=4 등비수열 포함 여부(0/1). 극희소 이벤트 - 형식적 완결용."""
    bm = _bitmask(c.astype(np.int16))
    out = np.zeros(c.shape[0], dtype=np.int32)
    for gm in _GP4_MASKS:
        out |= ((bm & gm) == gm).astype(np.int32)
    return out


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
    # [2026-07-04 후보7 - 정적 5종]
    'max_quadrant_occ': f_max_quadrant_occupancy,
    'max_multiple_cnt': f_max_multiple_count,
    'iqr_outlier_cnt': f_iqr_outlier_count,
    'ap_max_len': f_ap_max_len,
    'gp4_flag': f_gp4_flag,
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
        # [2026-07-04] 범위 밖 미관측 값 기본 페널티: 기존 pen.max()는 train 값이 상수(예: 희소
        # 플래그 전부 0 - gp4_flag/max_match_history 류)면 span=1이라 '관측된 유일 bin'의
        # 저페널티로 붕괴해 특징이 no-op가 됐다 -> 라플라스 미관측 확률 기반 페널티로 교체
        # (비상수 특징에서는 in-span 미관측 bin 페널티와 동일 = 기존 의미의 정확한 상한).
        default = float(-math.log(alpha / (N + alpha * bins)))

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
    # [2026-07-04] untouched hold-out 확정용 범위 제한: 스크리닝(최신 구간 hold-out)에서 생존한
    # 후보를, hold-out으로 한 번도 안 쓴 과거 구간에서 확정 검증할 때 사용. 0=전체(기본).
    end_round = int(os.environ.get('CAND_END_ROUND', '0'))
    if end_round > 0:
        rows = [x for x in rows if x[0] <= end_round]
        print("[스크리닝] CAND_END_ROUND=%d 적용 (untouched hold-out 확정 모드)" % end_round)
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

    # ---- [2026-07-04 후보7 - 동적 2종] 역사 의존 특징: fold 무관 사전계산 불가 ----
    # max_match_history: 조합 vs 'train 당첨조합들'의 최대 일치수 (회차 순서 running-max 1패스 후
    #   fold train_until 시점 스냅샷 - fold별 8.14M 재계산 없이 정확).
    # prev_draw_overlap: 직전 회차 당첨과의 겹침(이월수). 조합값은 '마지막 train 회차'와의 겹침으로
    #   고정 근사(임의 6수 집합에 대한 겹침 분포는 동일(초기하)이라 컷/분위 왜곡 무시 가능 - 정직 공개).
    #   holdout 당첨값은 '실제 직전 회차'와의 겹침(직전 회차는 예측 시점에 공지된 과거 = 누설 아님).
    dyn_names = []
    mmh_snap = {}
    mmh_w = pdo_w = w_bm = None
    _POP8 = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)

    def _popcount64(arr):
        return _POP8[arr.view(np.uint8).reshape(-1, 8)].sum(axis=1).astype(np.int16)

    if os.environ.get('CAND_DYNAMIC', '1') == '1':
        dyn_names = ['max_match_history', 'prev_draw_overlap']
        # 당첨조합 비트마스크
        w_bm = np.zeros(total, dtype=np.uint64)
        for i in range(total):
            m = np.uint64(0)
            for x in all_nums[i]:
                m |= np.uint64(1) << np.uint64(int(x))
            w_bm[i] = m
        # 당첨조합 자신의 역사값 (expanding: 회차 i 는 i 이전 회차들만 참조 - 누설 없음)
        mmh_w = np.zeros(total, dtype=np.int16)
        for i in range(1, total):
            mmh_w[i] = int(_popcount64(w_bm[:i] & w_bm[i]).max())
        pdo_w = np.zeros(total, dtype=np.int16)
        pdo_w[1:] = _popcount64(w_bm[:-1] & w_bm[1:])
        # 전 조합 running-max 스냅샷 (fold train_until 시점별)
        need_untils = sorted({rows[a - 1][0] for a, b in fold_specs})
        max_until = max(need_untils)
        print("[동적후보] 전 조합 presence 행렬 구성...", flush=True)
        P = np.zeros((Mall, 46), dtype=bool)
        _ar = np.arange(Mall)
        for j in range(6):
            P[_ar, all_combos[:, j].astype(np.int16)] = True
        del _ar
        run_max = np.zeros(Mall, dtype=np.int8)
        print("[동적후보] max_match_history running-max 1패스 (~%d회차, 수분 소요)..." % max_until, flush=True)
        _t0 = __import__('time').time()
        for i in range(total):
            if rows[i][0] > max_until:
                break
            m = P[:, all_nums[i]].sum(axis=1).astype(np.int8)
            np.maximum(run_max, m, out=run_max)
            if rows[i][0] in need_untils:
                mmh_snap[rows[i][0]] = run_max.copy()
            if (i + 1) % 200 == 0:
                print("  ... %d회 처리 (%.0fs)" % (i + 1, __import__('time').time() - _t0), flush=True)
        print("[동적후보] 준비 완료 (%.0fs)" % (__import__('time').time() - _t0), flush=True)

    cand_names = list(SCALAR_CANDIDATES.keys()) + ['positional_tail'] + dyn_names
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
            elif name == 'max_match_history':
                # [2026-07-04 동적] LUT=train 당첨의 expanding 최대일치(첫 회차 제외 - 이전 역사 없음).
                # 조합값=train_until 시점 스냅샷, holdout 당첨값도 동일 시점(train 당첨들만) 기준 = 일관/blind.
                lut = build_scalar_penalty(mmh_w[1:a])
                pen_all = lut(mmh_snap[train_until])
                hvals = np.array([int(_popcount64(w_bm[:a] & w_bm[i]).max())
                                  for i in range(a, b)], dtype=np.int64)
                pen_w = lut(hvals)
            elif name == 'prev_draw_overlap':
                # [2026-07-04 동적] LUT=train 이월수 분포. 조합값=마지막 train 회차와의 겹침(고정 근사),
                # holdout 당첨값=실제 직전 회차와의 겹침(직전 회차=공지된 과거, 누설 아님).
                lut = build_scalar_penalty(pdo_w[1:a])
                pen_all = lut(P[:, all_nums[a - 1]].sum(axis=1).astype(np.int64))
                pen_w = lut(pdo_w[a:b].astype(np.int64))
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

    # [2026-07-04] 결과 영속화 (기존 콘솔 전용 -> 재검증 근거 보존)
    out = {
        'meta': {'folds': len(fold_specs), 'window': window, 'total_rounds': total,
                 'K_pool': K_POOL, 'candidates': cand_names,
                 'note': '1차 스크리닝. 양성 신호는 그 자체로 채택 근거가 아님(순열검정+BH-FDR 확정 필요)'},
        'results': {name: {
            'd_percentile_mean': float(np.mean(dpct[name])),
            'd_percentile_folds_improved': int(np.sum(np.array(dpct[name]) > 0)),
            'd_retention_mean': float(np.mean(dret[name])),
            'd_retention_folds_improved': int(np.sum(np.array(dret[name]) > 0)),
            'per_fold_d_percentile': [float(x) for x in dpct[name]],
            'per_fold_d_retention': [float(x) for x in dret[name]],
        } for name in cand_names},
    }
    outpath = os.path.join(ROOT, 'results',
                           os.environ.get('CAND_OUT', 'candidate_features_walkforward.json'))
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("결과 저장: results/candidate_features_walkforward.json")


if __name__ == '__main__':
    main()
