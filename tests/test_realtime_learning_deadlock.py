"""
[P2-2] 실시간 학습 게이트 데드락(영구 정체) 해소 회귀 테스트

배경(런타임 검증 2026-06-03, RUNTIME_VERIFICATION_TODO.md):
  adaptive_update 게이트가 "직전 1스텝 성능 비교"로만 판정 -> 성능이 한 번 크게 떨어지면
  업데이트가 차단되고, 차단되면 performance_history가 갱신되지 않아 같은 두 값으로 영원히 비교
  -> 영구 차단(데드락). 실제로 LSTM 마지막 업데이트가 2025-09에 멈춰 9개월간 정체.

수정(realtime_learning_system.py):
  (1) 단발 비교 -> 최근값 vs 직전 평균(추세) 비교로 노이즈 완화
  (2) 연속 N회(MAX_CONSECUTIVE_SKIPS=3) 막히면 강제 1회 통과 -> 데드락 탈출
  (3) 평가 실패(None)는 history에 기록하지 않아 추세 오염 차단 (실제 0매치 0.0은 기록)
"""
import pytest
from collections import deque
from unittest.mock import MagicMock

from src.ml.realtime_learning_system import RealtimeLearningSystem


@pytest.fixture
def rls(tmp_path, monkeypatch):
    """results/ 상태파일이 프로젝트를 오염시키지 않도록 작업 디렉토리 격리."""
    monkeypatch.chdir(tmp_path)
    system = RealtimeLearningSystem(db_manager=MagicMock())
    return system


def _fill_buffer(system, model_type, count):
    """update_frequency 주기 조건을 충족시키기 위한 버퍼 채우기."""
    system.learning_buffers[model_type] = deque(
        [{'round': i, 'numbers': [1, 2, 3, 4, 5, 6]} for i in range(count)],
        maxlen=200,
    )


@pytest.mark.unit
def test_deadlock_resolved_force_update_after_consecutive_skips(rls):
    """[P2-2] 큰 성능 하락 후에도 연속 스킵 N회면 강제 1회 업데이트(데드락 해소)."""
    mt = 'lstm'  # update_frequency=2
    # 큰 하락 추세 주입 (0.15 -> 0.0). 수정 전이라면 이 상태에서 영원히 False.
    rls.performance_history[mt] = deque([0.15, 0.0], maxlen=10)
    _fill_buffer(rls, mt, 2)  # 2 % 2 == 0 -> 주기 조건 충족

    # 1, 2회째는 추세 하락으로 막힘 + 카운터 누적
    assert rls._should_update(mt) is False
    assert rls.model_states[mt]['consecutive_skips'] == 1
    assert rls._should_update(mt) is False
    assert rls.model_states[mt]['consecutive_skips'] == 2

    # 3회째(MAX_CONSECUTIVE_SKIPS=3) 강제 통과 -> 데드락 탈출, 카운터 리셋
    assert rls._should_update(mt) is True
    assert rls.model_states[mt]['consecutive_skips'] == 0


@pytest.mark.unit
def test_consecutive_skips_reset_on_recovery(rls):
    """[P2-2] 성능 추세가 회복되면 스킵 카운터가 리셋된다."""
    mt = 'lstm'
    rls.performance_history[mt] = deque([0.15, 0.0], maxlen=10)
    _fill_buffer(rls, mt, 2)

    assert rls._should_update(mt) is False
    assert rls.model_states[mt]['consecutive_skips'] == 1

    # 상승 추세로 교체 (latest 0.2 > prior_avg 0.0)
    rls.performance_history[mt] = deque([0.0, 0.2], maxlen=10)
    rls._should_update(mt)
    assert rls.model_states[mt]['consecutive_skips'] == 0


@pytest.mark.unit
def test_trend_compare_tolerates_single_noise(rls):
    """[P2-2] 단발 노이즈(직전 한 번 하락)에는 막히지 않는다(추세 비교)."""
    mt = 'monte_carlo'  # update_frequency=3
    # 전반적으로 양호한 추세에서 마지막만 살짝 하락: [0.15, 0.18, 0.16]
    # latest=0.16, prior_avg=mean(0.15,0.18)=0.165 -> improvement=-0.005,
    # threshold=min_improvement(0.008) -> -0.005 < -0.008? No -> 막지 않음
    rls.performance_history[mt] = deque([0.15, 0.18, 0.16], maxlen=8)
    _fill_buffer(rls, mt, 3)  # 3 % 3 == 0 주기 충족
    assert rls._should_update(mt) is True
    assert rls.model_states[mt]['consecutive_skips'] == 0


@pytest.mark.unit
def test_evaluate_returns_none_on_empty_data(rls):
    """[P2-2] 데이터가 없으면 평가 불가 -> None (구버전의 0.05 대체)."""
    assert rls._evaluate_model_performance(MagicMock(), []) is None


@pytest.mark.unit
def test_real_zero_match_returns_zero_not_none(rls):
    """[P2-2] 실제 0매치는 None이 아니라 0.0 (정상 신호이므로 history에 기록되어야 함)."""
    model = MagicMock(spec=['predict_next_numbers', 'sequence_length'])  # LSTM 취급
    model.sequence_length = 1
    model.predict_next_numbers.return_value = [{'numbers': [40, 41, 42, 43, 44, 45]}]
    # 매칭 평가(prev_data >= min_length=10)를 타도록 11개 제공, 정답과 전혀 안 겹침
    test_data = [{'round': i, 'numbers': [1, 2, 3, 4, 5, 6]} for i in range(11)]
    score = rls._evaluate_model_performance(model, test_data)
    assert score == 0.0


@pytest.mark.unit
def test_none_performance_not_appended_to_history(rls):
    """[P2-2] 평가 실패(None)는 performance_history에 기록되지 않는다(추세 오염 방지)."""
    mt = 'monte_carlo'
    mc = MagicMock(spec=['simulate_combinations', 'config'])
    mc.config = {}
    mc.simulate_combinations.return_value = []  # 시뮬레이션 실패 -> 평가 None
    rls.learning_buffers[mt] = deque([{'round': 1, 'numbers': [1, 2, 3, 4, 5, 6]}], maxlen=80)

    before = len(rls.performance_history[mt])
    result = rls._update_monte_carlo(mc)
    after = len(rls.performance_history[mt])

    assert after == before  # None이라 append되지 않음
    assert result['improvement'] == 0.0  # None-safe improvement
    assert result['new_performance'] is None


@pytest.mark.unit
def test_consecutive_skips_persisted_across_save_load(rls):
    """[P2-2] 연속 스킵 카운터는 save/load로 영속화되어 단발 실행 간에도 누적된다."""
    mt = 'ensemble'
    rls.model_states[mt]['consecutive_skips'] = 2
    rls._save_state()

    # 같은 cwd(tmp_path)에서 새 인스턴스 로드
    reloaded = RealtimeLearningSystem(db_manager=MagicMock())
    assert reloaded.model_states[mt]['consecutive_skips'] == 2


@pytest.mark.unit
def test_load_state_backward_compat_missing_skips(rls, tmp_path):
    """[P2-2] 구버전 상태파일(consecutive_skips 키 없음) 로드 시 0으로 안전 복원."""
    import json
    import os

    # consecutive_skips 키가 없는 구버전 상태파일 작성
    os.makedirs('results', exist_ok=True)
    legacy = {
        'model_states': {
            'lstm': {'last_update': None, 'update_count': 5},  # skips 키 없음
        },
        'performance_history': {'lstm': [0.1, 0.12]},
        'learning_buffers': {},
    }
    with open('results/realtime_learning_state.json', 'w', encoding='utf-8') as f:
        json.dump(legacy, f)

    system = RealtimeLearningSystem(db_manager=MagicMock())
    assert system.model_states['lstm']['update_count'] == 5
    assert system.model_states['lstm']['consecutive_skips'] == 0  # 기본 0


@pytest.mark.unit
def test_monte_carlo_maxlen_deadlock_force_update(rls):
    """[P2-2 보강] monte_carlo(buffer maxlen=80, freq=3 -> 80%3=2)가 버퍼 maxlen에 도달해
    주기가 영구 미충족이어도, 강제통과가 return True로 즉시 동작해 데드락이 재발하지 않는다.

    적대검증이 잡은 케이스: 강제통과를 'return True'가 아니라 '주기 확인 위임'으로 두면
    monte_carlo만 80%3!=0에 갇혀 consecutive_skips가 1->2->0 순환만 하고 영원히 업데이트 안 됨.
    """
    mt = 'monte_carlo'  # update_frequency=3, buffer maxlen=80
    rls.performance_history[mt] = deque([0.15, 0.0], maxlen=8)
    # 버퍼를 maxlen(80)까지 채워 80 % 3 = 2 (주기 영구 미충족) 상태로 고정
    rls.learning_buffers[mt] = deque(
        [{'round': i, 'numbers': [1, 2, 3, 4, 5, 6]} for i in range(80)], maxlen=80
    )
    assert len(rls.learning_buffers[mt]) == 80
    assert 80 % 3 != 0  # 주기 미충족 전제

    # 1, 2회 막힘 -> 3회째 강제 통과 (주기 미충족이어도 return True로 즉시 통과)
    assert rls._should_update(mt) is False
    assert rls._should_update(mt) is False
    assert rls._should_update(mt) is True
    assert rls.model_states[mt]['consecutive_skips'] == 0

    # 강제통과 후 다시 막히다가 또 3회째 강제통과 -> 주기적으로 풀림(데드락 없음)
    assert rls._should_update(mt) is False
    assert rls._should_update(mt) is False
    assert rls._should_update(mt) is True
    assert rls.model_states[mt]['consecutive_skips'] == 0
