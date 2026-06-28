"""
극단성 풀 제거강도 K 자동 재탐색기 (ExtremenessThresholdSelector)

설계 합의 (2026-06-03, Codex gpt-5.5 + Gemini 3.1-pro + Claude 교차검증):
  사용자 요구: "데이터가 업데이트되면 임계값(K=제거강도)을 자동 재탐색해 최적 필터 제거를
  찾고, 남은 풀로 예측한다." 통과율은 강제 제약이 아니라 참고지표. 극단 최대 제거 선호.

정직성(중요): 극단성 점수 AUC ~ 0.51 (매우 약한 신호)이다. 이 약신호 위에서 "데이터 노이즈를
  추종한 과적합(노이즈 추종)"을 방지하는 것이 본 모듈의 핵심이다. 따라서 우리는 "수학적 최적 K"를
  주장하지 않는다. 우리가 고르는 것은 "현재 검증 창(walk-forward hold-out)에서 통계적으로 가장
  방어 가능한 운영 K"다.

알고리즘 요약:
  A) Wilson score interval 하한(wilson_lower): 작은 표본(hold-out 당첨번호 수십~수백개)에서
     비율(coverage)의 신뢰 하한을 계산. 단순 p +- z*sqrt(p(1-p)/n) 보다 작은 n에서 견고.
  B) walk-forward lift curve(evaluate_threshold_curve): 최근 데이터를 여러 fold로 나눠
     각 fold는 train=fold 이전 / hold-out=fold 로 평가. fold마다 ExtremenessScorer를 새로 fit
     하여 미래 정보 누설(과적합)을 차단. 각 K에 대해 fold별 hold-in 개수를 누적해 누적 coverage와
     누적 n을 얻고, lift = coverage / pool_ratio, lift_lcb = wilson_lower(cov_hits, n) / pool_ratio.
  C) 후보 신뢰성 필터(reliable): expected_random_hits = n_total * pool_ratio >= MIN_EXPECTED_HITS
     이고 observed_hits >= MIN_OBSERVED_HITS 인 K만 자동 선택 후보로 인정(작은 K는 보고만).
  D) 선택 규칙(select_target_k): 신뢰 가능 후보 중 lift_lcb > 1.0 인 '가장 작은 K'(극단 최대 제거
     + 통계적 유의 효율)를 raw_K로 선택. 없으면 raw_K = 정책 fallback(이전 effective 또는 1.5M),
     evidence='weak'. 있으면 evidence='confirmed'.
  E) Hysteresis(thrashing 방지): previous_K가 현재 곡선에서 신뢰 가능하고 그 lift CI가 raw_K의
     lift CI와 겹치면 previous_K를 유지. 또한 grid 인덱스 기준 한 주에 1칸까지만 이동을 허용한다.

설계 가드:
  - 같은 effective_target_K면 build_pool/predict 결과가 불변(예측 5세트 회귀 안전).
  - datetime은 호출부에서 주입 가능하게(테스트 결정성). 순수 함수 위주.
  - 이모지 금지, 한국어 주석/로그. ASCII 대체([O]/[X]/-> 등).
"""
import os
import json
import math
import logging
from typing import Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# C(45, 6)
TOTAL_COMBINATIONS = 8_145_060

# 자동 선택 후보로 인정할 목표 풀 크기 그리드 (50K/100K 등 너무 작은 값은 보고용 - 후보 제외).
# 너무 촘촘하게 두면 다중 검정(여러 K를 동시에 보며 우연히 LCB>1인 것을 고름) 위험 -> 적당 간격.
DEFAULT_GRID: List[int] = [
    200_000, 300_000, 400_000, 500_000, 700_000, 900_000,
    1_000_000, 1_250_000, 1_500_000, 1_750_000, 2_000_000,
    2_500_000, 3_000_000, 4_000_000, 5_000_000, 6_000_000,
]
# 보고용(자동 후보 제외) 작은 K
REPORT_ONLY_GRID: List[int] = [50_000, 100_000]

# 후보 신뢰성 임계 (작은 표본에서 우연 효과 배제)
MIN_EXPECTED_HITS = 15   # n_total * pool_ratio (무작위 기대 포함 수) 하한
MIN_OBSERVED_HITS = 10   # 실제 풀에 포함된 hold-out 당첨번호 수 하한

# walk-forward 기본 파라미터
DEFAULT_FOLDS = 5
DEFAULT_WINDOW = 150

# 정책 fallback 기본 K (현 데이터에서 LCB>1 후보 부재 시 사용)
DEFAULT_FALLBACK_K = 1_500_000


# ----------------------------------------------------------------------
# A) Wilson score interval lower bound
# ----------------------------------------------------------------------
def wilson_lower(x: int, n: int, z: float = 1.96) -> float:
    """이항 비율 x/n 의 Wilson score interval 하한.

    작은 n에서도 [0,1] 범위를 벗어나지 않고 견고하다. n=0이면 0.0 반환.

    공식:
      p = x/n
      denom  = 1 + z^2/n
      center = (p + z^2/(2n)) / denom
      margin = z*sqrt( p(1-p)/n + z^2/(4 n^2) ) / denom
      return max(0.0, center - margin)
    """
    if n <= 0:
        return 0.0
    p = x / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return max(0.0, center - margin)


# ----------------------------------------------------------------------
# [2026-06-28 3차 코드리뷰 P2 정직성 갭 수정] 곡선 scorer = 생산 build_pool과 동일(가중)으로 통일.
#   과거: 이 곡선은 무가중 ExtremenessScorer로 coverage/lift/pool_ratio를 측정했으나, 생산
#   build_pool(extremeness_pool_predictor.py:_build_scorer)은 weights.json fw_*를 cov_inv=S@cov_inv@S로
#   주입한 '가중' scorer로 풀을 형성한다 -> 정책이 '실제 출고하는 풀과 다른 풀'의 커버리지로 K를 골랐다.
#   수정: "measure what you ship" - 곡선도 동일 가중 scorer로 측정. 가중치 부재/손상 시 무가중 폴백하고
#   scorer 라벨('weighted'/'unweighted')을 정책/곡선에 정직 표기.
#   주의(정직성): weights.json best_params는 전체데이터 산물을 '고정 하이퍼파라미터'로 주입하므로 미세
#   하이퍼파라미터 누설(가중쪽 낙관)이 있으나, 이는 생산 predict가 쓰는 바로 그 가중치라 '출고 풀'을
#   정확히 측정하는 게 목적이다. 참고: walk-forward A/B(validate_weighted_pool_walkforward)상 가중/무가중
#   커버리지 차이는 비유의(노이즈, 전 K lift_lcb<1)라 선택 K는 사실상 불변(1.5M weak fallback).
# ----------------------------------------------------------------------
def _load_curve_weights(weights_path=os.path.join('configs', 'extremeness_weights.json')):
    """weights.json best_params 로드. (best_params, label) 반환. 없으면 (None, 'unweighted')."""
    p = weights_path if os.path.isabs(weights_path) else os.path.join(_project_root(), weights_path)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                wj = json.load(f)
            if wj and 'best_params' in wj:
                return wj['best_params'], 'weighted'
        except Exception as e:
            logger.warning(f"[K선택] 가중치 로드 실패({e}) - 무가중 측정으로 폴백")
    return None, 'unweighted'


def _make_curve_scorer(db_manager, best_params, win_train):
    """생산 build_pool(_build_scorer + fit + cov_inv=S@cov_inv@S)과 동일한 (옵션)가중 scorer 생성.
    best_params=None이면 무가중. 생산 코드와 수식/순서 일치(회귀 방지)."""
    from src.core.extremeness_scorer import ExtremenessScorer
    if not best_params:
        scorer = ExtremenessScorer(db_manager)
        scorer.fit(win_train)
        return scorer
    pw = {d: best_params.get(f"pw_{d}", 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
    scorer = ExtremenessScorer(db_manager, alpha=best_params.get('alpha', 0.5), penalty_weights=pw)
    scorer._feature_scale = np.array(
        [best_params.get(f"fw_{f}", 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES],
        dtype=np.float32)
    scorer.fit(win_train)
    S = np.diag(scorer._feature_scale).astype(np.float32)
    scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
    return scorer


# ----------------------------------------------------------------------
# 내부 유틸: 당첨번호 로드
# ----------------------------------------------------------------------
def _load_winning_rows(db_manager) -> List:
    """db에서 (round, sorted(numbers)) 리스트를 회차 오름차순으로 반환."""
    rows = []
    for r, numbers_str, _date in db_manager.get_all_numbers():
        nums = sorted(int(x) for x in numbers_str.split(','))
        rows.append((int(r), nums))
    rows.sort(key=lambda t: t[0])
    return rows


def _resolve_latest_round(db_manager) -> int:
    """최신 회차 번호 해석 (get_latest_round -> get_last_round -> get_all_numbers 순)."""
    for attr in ('get_latest_round', 'get_last_round'):
        fn = getattr(db_manager, attr, None)
        if callable(fn):
            try:
                val = fn()
                if val:
                    return int(val)
            except Exception:
                pass
    rows = _load_winning_rows(db_manager)
    return max(r for r, _ in rows) if rows else 0


# ----------------------------------------------------------------------
# B) walk-forward lift curve
# ----------------------------------------------------------------------
def evaluate_threshold_curve(db_manager,
                             grid: Optional[Sequence[int]] = None,
                             folds: int = DEFAULT_FOLDS,
                             window: int = DEFAULT_WINDOW,
                             include_report_only: bool = True) -> Dict:
    """walk-forward 방식으로 각 K의 hold-out coverage/lift/lift_lcb 곡선을 계산.

    절차:
      1) 최근 folds*window 회차를 가장 오래된 fold부터 슬라이딩 윈도우로 분할.
      2) 각 fold f에 대해: train = fold 시작 이전 모든 회차, hold-out = fold(window회).
         ExtremenessScorer를 train으로 새로 fit (미래 정보 누설 차단).
      3) 8.14M 채점 -> 각 K의 cutoff(=K번째 작은 점수)와 실제 pool_ratio(<=cutoff 비율) 산출.
         hold-out 당첨번호 점수가 cutoff 이하이면 hit -> fold별 hit를 누적.
      4) 누적: cov_hits(전체 fold 합), n_total(전체 hold-out 수), pool_ratio는 fold별 가중 평균.
         lift = coverage / pool_ratio, lift_lcb = wilson_lower(cov_hits, n_total)/pool_ratio.

    반환:
      {
        'latest_round', 'folds', 'window', 'n_total',
        'grid', 'curve': [row,...], 'report_grid': [row,...]   (작은 K - 후보 제외)
      }
    각 row: {target_K, pool_ratio, cutoff_mean, coverage, observed_hits, expected_random_hits,
            lift, coverage_lcb, lift_lcb, reliable}
    """
    from src.core.extremeness_scorer import ExtremenessScorer

    if grid is None:
        grid = list(DEFAULT_GRID)
    candidate_grid = [int(k) for k in grid if k <= TOTAL_COMBINATIONS]

    # 보고용 작은 K(자동 후보 제외)를 곡선엔 포함하되 reliable=False가 되도록 별도 표시
    report_grid = [k for k in REPORT_ONLY_GRID if k <= TOTAL_COMBINATIONS] if include_report_only else []
    eval_grid = sorted(set(candidate_grid) | set(report_grid))

    rows = _load_winning_rows(db_manager)
    latest_round = max(r for r, _ in rows) if rows else 0
    total_rows = len(rows)

    # 최근 folds*window 회차를 hold-out 풀로 사용. 데이터가 부족하면 fold 수를 줄인다.
    # [코드리뷰 2026-06-27 P3] 'need = folds * window'는 이후 분할이 eff_folds 기반으로 재계산되며
    # 한 번도 참조되지 않는 죽은 변수라 제거함.
    if total_rows < window + 1:
        # 데이터가 너무 적으면 단일 fold(가능한 만큼)로 축소
        usable_window = max(1, min(window, total_rows - 1))
        fold_specs = [(total_rows - usable_window, total_rows)]  # (start_idx, end_idx) in rows
        eff_folds = 1
        eff_window = usable_window
    else:
        eff_window = window
        max_folds = (total_rows - 1) // window  # train이 최소 1회는 있어야 함
        eff_folds = max(1, min(folds, max_folds))
        # 가장 최근 eff_folds*window 회차를 사용 (오래된 fold부터)
        first_holdout_idx = max(1, total_rows - eff_folds * window)
        fold_specs = []
        s = first_holdout_idx
        while s + eff_window <= total_rows:
            fold_specs.append((s, s + eff_window))
            s += eff_window
        # 마지막에 남는 잔여 회차가 window 미만이면 무시(누적 곡선 견고성 우선)
        eff_folds = len(fold_specs)

    # 각 K별 누적자
    cov_hits = {k: 0 for k in eval_grid}     # 풀에 포함된 hold-out 당첨번호 누적 수
    n_total_k = {k: 0 for k in eval_grid}    # 누적 hold-out 수 (모든 K 동일하지만 일관성 위해 dict)
    pool_ratio_acc = {k: 0.0 for k in eval_grid}  # fold별 pool_ratio * fold_n 누적 (가중 평균용)
    cutoff_acc = {k: 0.0 for k in eval_grid}      # fold별 cutoff * fold_n 누적 (가중 평균용)
    n_total = 0

    combos = ExtremenessScorer.all_combinations()
    # [2026-06-28 P2] 생산 build_pool과 동일한 (가중) scorer로 곡선 측정 (measure what you ship).
    best_params, scorer_label = _load_curve_weights()

    for (start_idx, end_idx) in fold_specs:
        train_rows = rows[:start_idx]
        holdout_rows = rows[start_idx:end_idx]
        if not train_rows or not holdout_rows:
            continue

        win_train = np.array([nums for _, nums in train_rows], dtype=np.int16)
        win_holdout = np.array([nums for _, nums in holdout_rows], dtype=np.int16)
        fold_n = len(holdout_rows)
        n_total += fold_n

        scorer = _make_curve_scorer(db_manager, best_params, win_train)
        scores = scorer.score(combos)
        s_holdout = scorer.score(win_holdout)

        for k in eval_grid:
            cutoff = ExtremenessScorer.cutoff_for_size(scores, k)
            pr = float((scores <= cutoff).mean())  # 동점 견고: 실측 풀비율
            hits = int((s_holdout <= cutoff).sum())
            cov_hits[k] += hits
            n_total_k[k] += fold_n
            pool_ratio_acc[k] += pr * fold_n
            cutoff_acc[k] += cutoff * fold_n

    def _build_row(k: int, is_candidate: bool) -> Dict:
        nk = n_total_k[k]
        pr = (pool_ratio_acc[k] / nk) if nk > 0 else (k / TOTAL_COMBINATIONS)
        cutoff_mean = (cutoff_acc[k] / nk) if nk > 0 else float('nan')
        hits = cov_hits[k]
        coverage = (hits / nk) if nk > 0 else 0.0
        expected_random = nk * pr
        lift = (coverage / pr) if pr > 0 else 0.0
        cov_lcb = wilson_lower(hits, nk)
        lift_lcb = (cov_lcb / pr) if pr > 0 else 0.0
        reliable = bool(
            is_candidate
            and expected_random >= MIN_EXPECTED_HITS
            and hits >= MIN_OBSERVED_HITS
        )
        return {
            'target_K': int(k),
            'pool_ratio': pr,
            'cutoff_mean': cutoff_mean,
            'coverage': coverage,
            'observed_hits': int(hits),
            'expected_random_hits': float(expected_random),
            'lift': lift,
            'coverage_lcb': cov_lcb,
            'lift_lcb': lift_lcb,
            'reliable': reliable,
        }

    curve = [_build_row(k, is_candidate=True) for k in sorted(candidate_grid)]
    report_rows = [_build_row(k, is_candidate=False) for k in sorted(report_grid)]

    return {
        'latest_round': int(latest_round),
        # [코드리뷰 2026-06-27 P3] eff_folds/eff_window는 if/else 양 분기에서 항상 대입되므로
        # 'in locals()' else 가지는 도달 불가능한 죽은 가드였다. 직접 사용으로 단순화.
        'folds': int(eff_folds),
        'window': int(eff_window),
        'n_total': int(n_total),
        'grid': [int(k) for k in sorted(candidate_grid)],
        'curve': curve,
        'report_grid': report_rows,
        # [2026-06-28 P2] 곡선을 어떤 scorer로 측정했는지 정직 표기('weighted'=생산 일치 / 'unweighted'=폴백).
        'scorer': scorer_label,
    }


# ----------------------------------------------------------------------
# D/E) 선택 규칙 + Hysteresis
# ----------------------------------------------------------------------
def _find_row(curve: List[Dict], k: int) -> Optional[Dict]:
    for row in curve:
        if row['target_K'] == k:
            return row
    return None


def _ci_overlap(row_a: Dict, row_b: Dict) -> bool:
    """두 K의 lift 신뢰구간(점추정 lift 와 하한 lift_lcb 로 근사한 구간)이 겹치는지.

    상한 CI를 별도 계산하지 않으므로, '하한이 상대 점추정 이하' 양방향 조건으로 겹침을 근사한다:
      a.lift_lcb <= b.lift  AND  b.lift_lcb <= a.lift
    (보수적: 둘 중 하나라도 상대 점추정보다 위로 분리되면 비겹침으로 본다.)
    """
    return (row_a['lift_lcb'] <= row_b['lift'] + 1e-12) and (row_b['lift_lcb'] <= row_a['lift'] + 1e-12)


def select_target_k(curve_result: Dict,
                    previous_policy: Optional[Dict] = None,
                    grid: Optional[Sequence[int]] = None,
                    fallback_k: int = DEFAULT_FALLBACK_K,
                    selected_at: Optional[str] = None,
                    round_num: Optional[int] = None) -> Dict:
    """곡선과 이전 정책으로부터 운영 K(정책)를 결정.

    규칙:
      D) 신뢰 가능(reliable) 후보 중 lift_lcb > 1.0 인 '가장 작은 K' = raw_target_K (evidence=confirmed).
         없으면 raw_target_K = fallback(이전 effective_target_K 우선, 없으면 fallback_k), evidence=weak.
      E) Hysteresis:
         - previous_K가 현재 곡선에서 reliable 하고 그 lift CI가 raw_K의 lift CI와 겹치면 previous_K 유지.
         - grid 인덱스 기준 한 주 1칸 이동 제한(이전->raw 사이 격차가 2칸 이상이면 1칸만 이동).
      effective_target_K = 위 hysteresis 적용 결과.

    반환 policy dict (extremeness_pool_policy.json 스키마).
    """
    curve = curve_result.get('curve', [])
    if grid is None:
        grid = curve_result.get('grid') or list(DEFAULT_GRID)
    grid = sorted(int(k) for k in grid)

    prev_effective = None
    if previous_policy:
        prev_effective = previous_policy.get('effective_target_K')
    if prev_effective is not None:
        try:
            prev_effective = int(prev_effective)
        except (TypeError, ValueError):
            prev_effective = None

    # D) reliable + lift_lcb>1 인 가장 작은 K
    reliable_pos = [r for r in curve if r.get('reliable') and r.get('lift_lcb', 0.0) > 1.0]
    reliable_pos.sort(key=lambda r: r['target_K'])
    if reliable_pos:
        raw_row = reliable_pos[0]
        raw_target_K = int(raw_row['target_K'])
        evidence = 'confirmed'
    else:
        raw_target_K = int(prev_effective) if prev_effective else int(fallback_k)
        raw_row = _find_row(curve, raw_target_K)
        evidence = 'weak'

    effective_target_K = raw_target_K
    hysteresis_note = 'none'

    # E) Hysteresis - previous_K 유지 조건 (CI 겹침)
    prev_row = _find_row(curve, prev_effective) if prev_effective else None
    if prev_effective and prev_row is not None and prev_row.get('reliable') and raw_row is not None:
        if _ci_overlap(prev_row, raw_row):
            effective_target_K = int(prev_effective)
            hysteresis_note = 'kept_previous_ci_overlap'

    # E) grid 1칸 이동 제한 (effective 가 prev 대비 2칸 이상 벗어나면 1칸만 이동)
    if prev_effective and prev_effective in grid and effective_target_K in grid and hysteresis_note == 'none':
        i_prev = grid.index(int(prev_effective))
        i_eff = grid.index(int(effective_target_K))
        if abs(i_eff - i_prev) > 1:
            step = 1 if i_eff > i_prev else -1
            effective_target_K = int(grid[i_prev + step])
            hysteresis_note = 'limited_one_grid_step'

    sel_row = _find_row(curve, effective_target_K) or raw_row or {}
    selected_metrics = {
        'coverage': sel_row.get('coverage'),
        'pool_ratio': sel_row.get('pool_ratio'),
        'lift': sel_row.get('lift'),
        'lift_lcb': sel_row.get('lift_lcb'),
        'observed_hits': sel_row.get('observed_hits'),
        'expected_random_hits': sel_row.get('expected_random_hits'),
    }

    if round_num is None:
        round_num = curve_result.get('latest_round')

    policy = {
        'version': 1,
        'round': int(round_num) if round_num is not None else None,
        'selected_at': selected_at,
        'policy': 'walk_forward_wilson_lcb_min_k',
        'raw_target_K': int(raw_target_K),
        'effective_target_K': int(effective_target_K),
        'previous_target_K': int(prev_effective) if prev_effective else None,
        'evidence': evidence,
        'hysteresis': hysteresis_note,
        'holdout_n': int(curve_result.get('n_total', 0)),
        'folds': int(curve_result.get('folds', 0)),
        'window': int(curve_result.get('window', 0)),
        'grid': [int(k) for k in grid],
        'selected_metrics': selected_metrics,
        # [2026-06-28 P2 정직성] 곡선/선택 metrics를 어떤 scorer로 측정했는지 명시.
        #   'weighted' = 생산 build_pool과 동일 가중 scorer(= 출고하는 풀의 커버리지). 'unweighted' = 폴백.
        'scorer': curve_result.get('scorer', 'unknown'),
    }
    return policy


# ----------------------------------------------------------------------
# 정책 파일 I/O
# ----------------------------------------------------------------------
def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


POLICY_PATH = os.path.join('configs', 'extremeness_pool_policy.json')
CURVE_DIR = 'results'


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_project_root(), path)


def load_policy(path: str = POLICY_PATH) -> Optional[Dict]:
    """정책 json 로드 (없거나 손상 시 None)."""
    p = _abs(path)
    if not os.path.exists(p):
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[K선택] 정책 로드 실패({e}) - None 반환")
        return None


def save_policy(policy: Dict, path: str = POLICY_PATH) -> bool:
    """정책 json 저장 (원자적 쓰기, ensure_ascii=True 로 이모지/비ASCII 차단)."""
    p = _abs(path)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(policy, f, ensure_ascii=True, indent=2)
        os.replace(tmp, p)
        return True
    except Exception as e:
        logger.warning(f"[K선택] 정책 저장 실패({e})")
        return False


def save_curve(curve_result: Dict, round_num: Optional[int] = None,
               curve_dir: str = CURVE_DIR) -> Optional[str]:
    """전체 curve를 results/extremeness_threshold_curve_<round>.json 으로 저장. 경로 반환."""
    if round_num is None:
        round_num = curve_result.get('latest_round', 0)
    d = _abs(curve_dir)
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"extremeness_threshold_curve_{round_num}.json")
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(curve_result, f, ensure_ascii=True, indent=2)
        os.replace(tmp, path)
        return path
    except Exception as e:
        logger.warning(f"[K선택] 곡선 저장 실패({e})")
        return None


def refresh_policy(db_manager,
                   grid: Optional[Sequence[int]] = None,
                   folds: int = DEFAULT_FOLDS,
                   window: int = DEFAULT_WINDOW,
                   selected_at: Optional[str] = None,
                   policy_path: str = POLICY_PATH,
                   save: bool = True) -> Dict:
    """현재 DB 데이터로 K를 재탐색하고 정책을 저장하는 고수준 진입점.

    실패해도 기존 정책을 보존(예외를 호출부로 던지지 않고 기존 정책 반환)하도록 방어한다.
    selected_at(타임스탬프)은 호출부에서 주입(테스트 결정성). 미지정 시 datetime.now() 사용.
    """
    prev = load_policy(policy_path)
    try:
        if selected_at is None:
            from datetime import datetime
            selected_at = datetime.now().isoformat(timespec='seconds')
        curve_result = evaluate_threshold_curve(db_manager, grid=grid, folds=folds, window=window)
        round_num = _resolve_latest_round(db_manager)
        policy = select_target_k(curve_result, previous_policy=prev, grid=grid,
                                 selected_at=selected_at, round_num=round_num)
        if save:
            save_curve(curve_result, round_num=round_num)
            save_policy(policy, policy_path)
        logger.info(
            f"[K선택] 재탐색 완료: effective_K={policy['effective_target_K']:,}, "
            f"evidence={policy['evidence']}, hysteresis={policy['hysteresis']}, "
            f"holdout_n={policy['holdout_n']}, "
            f"lift_lcb={policy['selected_metrics'].get('lift_lcb')}")
        return policy
    except Exception as e:
        logger.error(f"[K선택] 재탐색 실패({e}) - 기존 정책 유지")
        return prev or {
            'version': 1, 'round': None, 'selected_at': selected_at,
            'policy': 'fallback', 'raw_target_K': DEFAULT_FALLBACK_K,
            'effective_target_K': DEFAULT_FALLBACK_K, 'previous_target_K': None,
            'evidence': 'weak', 'hysteresis': 'none', 'holdout_n': 0,
            'grid': list(DEFAULT_GRID), 'selected_metrics': {},
        }
