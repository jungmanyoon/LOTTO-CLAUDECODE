"""
[optimization-6] ThresholdOptimizer._calculate_score v6 검증

사용자 최종확정 결정(2026-05-31): "통과율(당첨번호 보존율) 강제 제약 제거,
출현율 낮은 극단 패턴을 최대한 많이 제거(풀 축소)가 우선 목표, 통과율은 참고 지표".

본 테스트는 v5의 통과율 95% hard constraint(deficit*10 절벽)가 v6에서 제거되어
- (1) 풀 축소가 통과율보다 우선되고
- (2) 동일 통과율이면 좁은 풀이 고점이며
- (3) 빈 풀(통과율 0, 전부 제거)은 최고점이 아니고(완전붕괴 방지)
- (4) 통과율 경계(0.95) 부근에서 점수가 연속적(절벽 없음)
임을 확인한다.

ThresholdOptimizer.__init__은 우회(__new__ + logger 주입)하고 순수 점수 함수만 검증.
"""
import logging

import pytest

from src.core.threshold_optimizer import ThresholdOptimizer


def _make_optimizer():
    """__init__(설정/DB 로드)을 우회한 경량 인스턴스. _calculate_score는 self.logger만 사용."""
    opt = ThresholdOptimizer.__new__(ThresholdOptimizer)
    opt.logger = logging.getLogger("test_threshold_score")
    return opt


def _score(opt, *, pool, win_incl, avg=1.0):
    """_calculate_score 호출 헬퍼 (ml_inclusion/threshold는 v6 미사용 인자)."""
    return opt._calculate_score(
        avg_matches=avg,
        ml_inclusion=0.1,
        combination_count=pool,
        threshold=1.0,
        winning_inclusion_rate=win_incl,
    )


@pytest.mark.unit
def test_pool_shrink_beats_higher_inclusion():
    """(1) 풀 축소 우선: 좁은 풀+낮은 통과율(0.90)이 넓은 풀+높은 통과율(0.96)을 이긴다.

    v5라면 0.90은 deficit*10 절벽으로 추락해 절대 선택 불가였다. v6는 절벽이 없으므로
    극단 제거(풀 축소)가 통과율 약간의 손실을 이긴다 = 핵심 전략.
    """
    opt = _make_optimizer()
    narrow_low = _score(opt, pool=150_000, win_incl=0.90)
    wide_high = _score(opt, pool=5_000_000, win_incl=0.96)
    assert narrow_low > wide_high


@pytest.mark.unit
def test_same_inclusion_narrower_pool_wins():
    """(2) 동일 통과율이면 좁은 풀이 고점(풀 축소 보상)."""
    opt = _make_optimizer()
    narrow = _score(opt, pool=150_000, win_incl=0.95)
    wide = _score(opt, pool=5_000_000, win_incl=0.95)
    assert narrow > wide


@pytest.mark.unit
def test_empty_pool_not_optimal():
    """(3) 완전붕괴 방지: 같은 좁은 풀이라도 통과율 0(전부 제거)은 통과율 0.95보다 낮다.

    통과율 약한 보조항(W_INCLUSION)이 '풀=0이 최고점' 되는 무의미 해를 막는다.
    """
    opt = _make_optimizer()
    empty = _score(opt, pool=100_000, win_incl=0.0)
    healthy = _score(opt, pool=100_000, win_incl=0.95)
    assert healthy > empty


@pytest.mark.unit
def test_no_cliff_at_inclusion_boundary():
    """(4) 절벽 없음: 통과율 0.96 -> 0.94 경계 통과 시 점수 점프가 미세(연속적)하다.

    v5라면 0.94는 hard constraint로 약 0.2 점프(절벽). v6는 W_INCLUSION*0.02 = 0.004 수준.
    """
    opt = _make_optimizer()
    above = _score(opt, pool=300_000, win_incl=0.96)
    below = _score(opt, pool=300_000, win_incl=0.94)
    gap = abs(above - below)
    # 절벽(>=0.1)이 없고, 통과율 차 0.02 * 약한 가중치(0.2) 수준의 미세 차이만 존재
    assert gap < 0.05


@pytest.mark.unit
def test_inclusion_below_95_no_catastrophic_penalty():
    """(보강) 통과율 0.80 trial이 deficit*10 같은 파국적 음수 점수로 추락하지 않는다.

    v5: score ~= 0.80 - (0.95-0.80)*10 - pool_penalty = 0.80 - 1.5 - ... < -0.7 (선택 불가).
    v6: 절벽 제거로 정상 범위 점수.
    """
    opt = _make_optimizer()
    score = _score(opt, pool=200_000, win_incl=0.80)
    assert score > 0.0
