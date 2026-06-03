"""
극단성 풀 진단 추가의 '예측 불변성' 회귀 테스트.

검증 목표(외과적 변경 보장):
  1. score()와 score_components()['total']이 비트 단위로 동일 (np.testing.assert_allclose rtol=0 atol=0)
     -> 진단을 위해 도입한 score_components가 풀 선택 점수를 바꾸지 않음을 보장.
  2. select_pool(pool_idx 집합)이 score 기반으로 결정적이며, '컷오프<=재선택'이 아니라
     argpartition 인덱스 선택임을 확인 (동점 K변동 위험 없음).
  3. build_pool(force=True) -> predict(seed=42) 2회 호출 결과가 완전히 동일(결정성).
  4. 진단 로직(_build_pool_diagnostics)이 scores/combos 원본 배열을 변형하지 않음.

전 항목 ASCII/한국어. 이모지 금지.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.extremeness_scorer import ExtremenessScorer
from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
from src.core.db_manager import DatabaseManager


@pytest.fixture(scope="module")
def db():
    return DatabaseManager()


@pytest.fixture(scope="module")
def fitted_scorer(db):
    s = ExtremenessScorer(db)
    s.fit_until(None)  # 전체 당첨번호로 학습
    return s


def _rng_combos(n: int, seed: int = 7) -> np.ndarray:
    """무작위 정렬 조합 n개 생성 (1..45 중 6개 비복원)."""
    rng = np.random.default_rng(seed)
    rows = np.array([np.sort(rng.choice(np.arange(1, 46), size=6, replace=False)) for _ in range(n)],
                    dtype=np.int16)
    return rows


def test_score_components_total_equals_score(fitted_scorer):
    """score()와 score_components()['total']이 비트 단위로 동일해야 한다."""
    combos = _rng_combos(5000, seed=123)
    s_old = fitted_scorer.score(combos)
    comp = fitted_scorer.score_components(combos)
    s_new = comp['total']
    # rtol=0 atol=0: 완전 동일 요구
    np.testing.assert_allclose(s_old, s_new, rtol=0, atol=0)
    assert s_old.dtype == s_new.dtype == np.float32


def test_components_sum_equals_total(fitted_scorer):
    """성분 합(maha + 4페널티)이 total과 부동소수 동일 순서로 일치."""
    combos = _rng_combos(3000, seed=999)
    comp = fitted_scorer.score_components(combos)
    # score()와 동일한 순서로 재합산: maha + (penalty 차원 누적)
    pen_sum = np.zeros(len(combos), dtype=np.float32)
    for key in ['pen_max_consecutive', 'pen_odd_count',
                'pen_max_same_last_digit', 'pen_max_section_occupancy']:
        pen_sum = pen_sum + comp[key]
    recomputed = comp['mahalanobis2'] + pen_sum
    np.testing.assert_allclose(comp['total'], recomputed, rtol=0, atol=0)


def test_select_pool_is_score_based_not_cutoff_reselect(fitted_scorer):
    """select_pool 결과가 score 기반 argpartition이며 컷오프 재선택이 아님을 확인.

    핵심: '선택된 풀의 최대 점수(cutoff)'를 기준으로 scores<=cutoff를 다시 뽑으면
    동점 때문에 K가 달라질 수 있다. select_pool은 정확히 K개를 보장해야 한다.
    """
    scores = fitted_scorer.score(_rng_combos(20000, seed=55))
    K = 5000
    idx = ExtremenessScorer.select_pool(scores, K)
    assert len(idx) == K  # 정확히 K개
    assert len(set(idx.tolist())) == K  # 중복 없음

    # 결정성: 같은 입력 -> 같은 인덱스 집합
    idx2 = ExtremenessScorer.select_pool(scores, K)
    assert set(idx.tolist()) == set(idx2.tolist())

    # 선택된 풀은 '가장 작은 K개 점수'와 정확히 일치해야 함(극단 제거 정의)
    selected_scores = np.sort(scores[idx])
    smallest_k = np.sort(scores)[:K]
    np.testing.assert_allclose(selected_scores, smallest_k, rtol=0, atol=0)

    # 컷오프 재선택의 위험 시연: scores<=cutoff는 동점 때문에 K를 초과할 수 있음
    cutoff = scores[idx].max()
    leq_cutoff = int((scores <= cutoff).sum())
    assert leq_cutoff >= K  # >= K (동점이 있으면 초과). select_pool은 정확히 K로 고정.


def test_diagnostics_does_not_mutate_inputs(fitted_scorer):
    """_build_pool_diagnostics가 scores/combos 원본을 변형하지 않음을 확인."""
    predictor = ExtremenessPoolPredictor(fitted_scorer.db, target_K=8000)
    combos = ExtremenessScorer.all_combinations()

    # 전체 8.14M 대신 일부만으로 진단 호출(원본 변형 여부만 검증).
    sub = combos[:200000]
    comp = fitted_scorer.score_components(sub)
    scores = comp['total']

    scores_before = scores.copy()
    sub_before = sub.copy()
    comp_total_before = comp['total'].copy()
    comp_maha_before = comp['mahalanobis2'].copy()

    pool_idx = ExtremenessScorer.select_pool(scores, predictor.target_K)
    # predictor._pool_combos를 진단이 참조하므로 세팅
    predictor._pool_combos = sub[pool_idx]
    predictor._pool_quality = (-scores[pool_idx]).astype(np.float32)

    diag = predictor._build_pool_diagnostics(comp, scores, pool_idx,
                                             weighted=False, train_until=1226)

    # 원본 배열 불변 검증
    np.testing.assert_array_equal(scores, scores_before)
    np.testing.assert_array_equal(sub, sub_before)
    np.testing.assert_array_equal(comp['total'], comp_total_before)
    np.testing.assert_array_equal(comp['mahalanobis2'], comp_maha_before)

    # all_combinations 캐시가 읽기전용(변형 차단)인지 확인
    assert combos.flags.writeable is False

    # 진단 dict 형태 sanity
    assert diag['keep'] == len(pool_idx)
    assert diag['removed'] == len(sub) - len(pool_idx)


def test_predict_deterministic_same_seed(db):
    """build_pool(force=True) 후 predict(seed=42) 2회가 완전히 동일(결정성)."""
    # 빠른 검증을 위해 작은 K 사용(파이프라인 동일, 결정성만 검증).
    predictor = ExtremenessPoolPredictor(db, target_K=50000)
    n1 = predictor.build_pool(force=True)
    out1 = predictor.predict(num_sets=5, seed=42)

    # 같은 predictor 재호출(풀 동일) -> 결정성
    out1b = predictor.predict(num_sets=5, seed=42)
    nums1 = [o['numbers'] for o in out1]
    nums1b = [o['numbers'] for o in out1b]
    assert nums1 == nums1b, f"동일 seed 재예측 불일치: {nums1} vs {nums1b}"

    # 새 predictor로 풀 재형성(force) 후에도 동일해야 함(채점 결정성)
    predictor2 = ExtremenessPoolPredictor(db, target_K=50000)
    n2 = predictor2.build_pool(force=True)
    out2 = predictor2.predict(num_sets=5, seed=42)
    nums2 = [o['numbers'] for o in out2]
    assert n1 == n2, f"풀 크기 불일치: {n1} vs {n2}"
    assert nums1 == nums2, f"force 재형성 후 예측 불일치: {nums1} vs {nums2}"


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v', '-s']))
