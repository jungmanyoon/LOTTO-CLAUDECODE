# -*- coding: utf-8 -*-
"""
극단성 풀 제거강도 K 자동 재탐색기(extremeness_threshold_selector) 단위 테스트.

결정적 테스트: 고정 입력(곡선 dict)을 직접 구성해 select_target_k 규칙을 검증한다.
wilson_lower 는 알려진 수치로 검증. evaluate_threshold_curve 는 8.14M 채점이 무거워
단위 테스트에서는 직접 호출하지 않고, 규칙 함수에 합성 곡선을 주입해 검증한다.
"""
import math

import pytest

from src.core import extremeness_threshold_selector as sel


# ----------------------------------------------------------------------
# A) wilson_lower 수치 검증 (알려진 값)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_wilson_lower_known_values():
    # 50/100, z=1.96 -> 약 0.4038 (널리 알려진 Wilson 하한 값)
    assert abs(sel.wilson_lower(50, 100) - 0.4038) < 0.001
    # n=0 -> 0.0
    assert sel.wilson_lower(0, 0) == 0.0
    # 전부 성공(10/10) -> 1.0 보다 작은 하한 (약 0.7225)
    assert abs(sel.wilson_lower(10, 10) - 0.7225) < 0.001
    # 하한은 항상 [0,1]
    for x, n in [(1, 100), (99, 100), (0, 50), (50, 50)]:
        lcb = sel.wilson_lower(x, n)
        assert 0.0 <= lcb <= 1.0


@pytest.mark.unit
def test_wilson_lower_monotonic_in_x():
    # 같은 n에서 x가 클수록 하한도 단조 증가
    n = 200
    prev = -1.0
    for x in range(0, n + 1, 20):
        lcb = sel.wilson_lower(x, n)
        assert lcb >= prev - 1e-12
        prev = lcb


# ----------------------------------------------------------------------
# 합성 곡선 빌더 (결정적)
# ----------------------------------------------------------------------
def _row(k, pool_ratio, coverage, n_total, reliable=True):
    """관측치로부터 lift/lcb를 selector 와 동일 공식으로 재현한 곡선 row."""
    hits = int(round(coverage * n_total))
    expected = n_total * pool_ratio
    lift = coverage / pool_ratio if pool_ratio > 0 else 0.0
    cov_lcb = sel.wilson_lower(hits, n_total)
    lift_lcb = cov_lcb / pool_ratio if pool_ratio > 0 else 0.0
    return {
        'target_K': int(k),
        'pool_ratio': pool_ratio,
        'cutoff_mean': 0.0,
        'coverage': coverage,
        'observed_hits': hits,
        'expected_random_hits': expected,
        'lift': lift,
        'coverage_lcb': cov_lcb,
        'lift_lcb': lift_lcb,
        'reliable': bool(reliable),
    }


def _curve_result(curve, grid, n_total=300, latest_round=1226):
    return {
        'latest_round': latest_round,
        'folds': 2,
        'window': 150,
        'n_total': n_total,
        'grid': [int(k) for k in grid],
        'curve': curve,
        'report_grid': [],
    }


# ----------------------------------------------------------------------
# D) 선택 규칙: reliable + lift_lcb>1 인 가장 작은 K
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_select_confirmed_smallest_k_with_lcb_gt_1():
    grid = [500_000, 1_000_000, 1_500_000]
    # 500K: pool 6%, cov 9% -> lift 1.5, hits 큰 표본 -> lcb>1
    # 1.0M: pool 12%, cov 14% -> lift ~1.17
    curve = [
        _row(500_000, 0.06, 0.12, n_total=300),   # lift 2.0, 풍부한 hits
        _row(1_000_000, 0.12, 0.16, n_total=300),
        _row(1_500_000, 0.18, 0.22, n_total=300),
    ]
    cr = _curve_result(curve, grid)
    policy = sel.select_target_k(cr, previous_policy=None, grid=grid, selected_at='T')
    # confirmed 이고 가장 작은 신뢰 K 선택
    assert policy['evidence'] == 'confirmed'
    assert policy['raw_target_K'] == 500_000
    assert policy['effective_target_K'] == 500_000
    assert policy['selected_at'] == 'T'


@pytest.mark.unit
def test_select_weak_fallback_when_no_lcb_gt_1():
    grid = [500_000, 1_000_000, 1_500_000]
    # 모든 K가 lift~1 근방이라 lcb<1 -> confirmed 없음 -> weak fallback
    curve = [
        _row(500_000, 0.06, 0.061, n_total=300),
        _row(1_000_000, 0.12, 0.121, n_total=300),
        _row(1_500_000, 0.18, 0.181, n_total=300),
    ]
    cr = _curve_result(curve, grid)
    # 이전 정책 없음 -> fallback_k(1.5M) 사용, evidence weak
    policy = sel.select_target_k(cr, previous_policy=None, grid=grid,
                                 fallback_k=1_500_000, selected_at='T')
    assert policy['evidence'] == 'weak'
    assert policy['effective_target_K'] == 1_500_000


@pytest.mark.unit
def test_weak_fallback_uses_previous_effective():
    grid = [500_000, 1_000_000, 1_500_000]
    curve = [
        _row(500_000, 0.06, 0.061, n_total=300),
        _row(1_000_000, 0.12, 0.121, n_total=300),
        _row(1_500_000, 0.18, 0.181, n_total=300),
    ]
    cr = _curve_result(curve, grid)
    prev = {'effective_target_K': 1_000_000}
    policy = sel.select_target_k(cr, previous_policy=prev, grid=grid, selected_at='T')
    # confirmed 없음 -> 이전 effective(1.0M) 유지
    assert policy['evidence'] == 'weak'
    assert policy['raw_target_K'] == 1_000_000
    assert policy['effective_target_K'] == 1_000_000


# ----------------------------------------------------------------------
# C) reliable 필터: 작은 표본/관측은 후보 제외
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_reliable_filter_excludes_small_evidence_k():
    grid = [200_000, 1_500_000]
    # 200K: pool 2.4%, n_total=300 -> expected=7.2 < MIN_EXPECTED_HITS(15) -> 후보 제외
    #   reliable=False 로 직접 표시하여(곡선 빌더는 evaluate가 계산) lcb>1 이어도 선택 안 됨
    small = _row(200_000, 0.024, 0.05, n_total=300, reliable=False)
    big = _row(1_500_000, 0.18, 0.20, n_total=300, reliable=True)
    cr = _curve_result([small, big], grid)
    policy = sel.select_target_k(cr, previous_policy=None, grid=grid, selected_at='T')
    # 작은 K(200K)는 reliable=False라 lcb>1 이어도 후보 제외 -> 1.5M 선택
    assert policy['effective_target_K'] != 200_000


# ----------------------------------------------------------------------
# E) Hysteresis: CI 겹침 시 previous_K 유지
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_hysteresis_keeps_previous_when_ci_overlap():
    grid = [1_000_000, 1_250_000, 1_500_000]
    # raw 후보(1.0M)와 previous(1.25M)의 lift CI가 겹치도록 비슷한 lift 구성.
    # 둘 다 lift_lcb>1(=confirmed)이고 lift 점추정이 같아(1.4) CI가 서로 겹친다.
    curve = [
        _row(1_000_000, 0.12, 0.168, n_total=500),   # lift 1.4, lift_lcb~1.15
        _row(1_250_000, 0.15, 0.21, n_total=500),    # lift 1.4, lift_lcb~1.18 (겹침)
        _row(1_500_000, 0.18, 0.21, n_total=500),
    ]
    cr = _curve_result(curve, grid, n_total=500)
    prev = {'effective_target_K': 1_250_000}
    policy = sel.select_target_k(cr, previous_policy=prev, grid=grid, selected_at='T')
    # raw는 1.0M(가장 작은 confirmed)이지만 prev(1.25M) CI 겹침 -> prev 유지
    assert policy['raw_target_K'] == 1_000_000
    assert policy['effective_target_K'] == 1_250_000
    assert policy['hysteresis'] == 'kept_previous_ci_overlap'


@pytest.mark.unit
def test_hysteresis_limits_one_grid_step():
    grid = [500_000, 700_000, 900_000, 1_000_000, 1_250_000, 1_500_000]
    # raw가 500K(가장 작은 confirmed, 강한 lift)인데 prev는 1.5M -> 인덱스 격차 큼.
    # prev row는 reliable 하지만 CI가 raw와 분리되도록(겹치지 않게) 구성 -> CI 유지 미발동,
    # grid 1칸 제한만 발동해야 함.
    curve = [
        _row(500_000, 0.06, 0.18, n_total=400),     # lift 3.0 (강함, 분리)
        _row(700_000, 0.086, 0.10, n_total=400),
        _row(900_000, 0.11, 0.12, n_total=400),
        _row(1_000_000, 0.12, 0.13, n_total=400),
        _row(1_250_000, 0.15, 0.16, n_total=400),
        _row(1_500_000, 0.18, 0.185, n_total=400),  # prev, lift ~1.03
    ]
    cr = _curve_result(curve, grid, n_total=400)
    prev = {'effective_target_K': 1_500_000}
    policy = sel.select_target_k(cr, previous_policy=prev, grid=grid, selected_at='T')
    assert policy['raw_target_K'] == 500_000
    # 1칸만 이동: 1.5M 인덱스(5) -> 4 = 1.25M
    assert policy['effective_target_K'] == 1_250_000
    assert policy['hysteresis'] == 'limited_one_grid_step'


# ----------------------------------------------------------------------
# 정책 dict 스키마/저장 키 검증
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_policy_schema_keys():
    grid = [500_000, 1_500_000]
    curve = [
        _row(500_000, 0.06, 0.12, n_total=300),
        _row(1_500_000, 0.18, 0.20, n_total=300),
    ]
    cr = _curve_result(curve, grid)
    policy = sel.select_target_k(cr, previous_policy=None, grid=grid,
                                 selected_at='2026-06-03T00:00:00', round_num=1226)
    for key in ['version', 'round', 'selected_at', 'policy', 'raw_target_K',
                'effective_target_K', 'previous_target_K', 'evidence',
                'holdout_n', 'grid', 'selected_metrics']:
        assert key in policy, f"missing key {key}"
    assert policy['round'] == 1226
    for mkey in ['coverage', 'pool_ratio', 'lift', 'lift_lcb',
                 'observed_hits', 'expected_random_hits']:
        assert mkey in policy['selected_metrics']


@pytest.mark.unit
def test_ci_overlap_helper():
    # 분리(비겹침): a.lift_lcb > b.lift
    a = {'lift': 2.0, 'lift_lcb': 1.5}
    b = {'lift': 1.2, 'lift_lcb': 0.9}
    assert sel._ci_overlap(a, b) is False
    # 겹침
    c = {'lift': 1.3, 'lift_lcb': 1.0}
    d = {'lift': 1.35, 'lift_lcb': 1.05}
    assert sel._ci_overlap(c, d) is True
