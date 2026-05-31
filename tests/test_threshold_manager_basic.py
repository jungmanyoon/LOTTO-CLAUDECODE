# -*- coding: utf-8 -*-
"""
ThresholdManager 기본 단위 테스트

Phase 1: Critical Bug Fixes 검증
- Singleton pattern
- Threshold validation
- Observer pattern
- Change history tracking
"""

import pytest
import sys
from pathlib import Path
from decimal import Decimal

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.threshold_manager import ThresholdManager, get_threshold_manager


class TestThresholdManagerBasic:
    """ThresholdManager 기본 기능 테스트"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """각 테스트 전에 singleton 리셋"""
        ThresholdManager.reset_instance()
        yield
        ThresholdManager.reset_instance()

    def test_singleton_behavior(self):
        """Singleton pattern: 동일한 인스턴스 반환 (BUG-001 수정 검증)"""
        tm1 = get_threshold_manager()
        tm2 = get_threshold_manager()
        assert tm1 is tm2, "Singleton이 동일한 인스턴스를 반환하지 않음"

    def test_get_instance_thread_safe(self):
        """get_instance()가 thread-safe하게 작동 (BUG-001 수정 검증)"""
        import threading
        import time

        instances = []

        def create_instance():
            time.sleep(0.001)  # Simulate race condition
            instance = ThresholdManager.get_instance()
            instances.append(instance)

        # 10개 스레드 동시 실행
        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 모든 인스턴스가 동일해야 함
        assert len(set(id(inst) for inst in instances)) == 1, \
            "Race condition: 여러 인스턴스 생성됨"

    def test_get_threshold_default(self):
        """기본 threshold 값 확인"""
        tm = get_threshold_manager()
        threshold = tm.get_threshold()
        # get_threshold()는 float를 반환
        assert isinstance(threshold, float), f"Threshold가 float 타입이 아님: {type(threshold)}"
        assert 0.3 <= threshold <= 3.0, \
            f"Threshold가 범위를 벗어남: {threshold}"

    def test_update_threshold_valid(self):
        """유효한 threshold 업데이트"""
        tm = get_threshold_manager()
        tm.set_threshold(1.5)
        assert float(tm.get_threshold()) == 1.5, "Threshold 업데이트 실패"

    def test_update_threshold_invalid_low(self):
        """너무 낮은 threshold는 warning만 로깅 (ValueError raise 안 함)"""
        tm = get_threshold_manager()
        original = tm.get_threshold()
        tm.set_threshold(0.1)  # Below 0.3 minimum - warning only
        # Threshold가 변경되지 않아야 함
        assert tm.get_threshold() == original, "Invalid threshold가 적용됨"

    def test_update_threshold_invalid_high(self):
        """너무 높은 threshold는 warning만 로깅 (ValueError raise 안 함)"""
        tm = get_threshold_manager()
        original = tm.get_threshold()
        tm.set_threshold(5.0)  # Above 3.0 maximum - warning only
        # Threshold가 변경되지 않아야 함
        assert tm.get_threshold() == original, "Invalid threshold가 적용됨"

    def test_observer_registration(self):
        """Observer 등록 및 알림 (BUG-003 수정 검증)"""
        tm = get_threshold_manager()

        notified = []

        def test_observer(param, old_val, new_val):
            notified.append((param, old_val, new_val))

        tm.register_observer(test_observer)
        tm.set_threshold(1.8)

        assert len(notified) == 1, f"Observer 알림 횟수 오류: {len(notified)}"
        assert notified[0][0] == 'threshold', f"잘못된 파라미터: {notified[0][0]}"
        assert float(notified[0][2]) == 1.8, f"잘못된 새 값: {notified[0][2]}"

    def test_observer_exception_handling(self):
        """Observer 예외 처리 (BUG-003 수정 검증)"""
        tm = get_threshold_manager()

        notified = []

        def failing_observer(param, old_val, new_val):
            raise RuntimeError("Test exception")

        def working_observer(param, old_val, new_val):
            notified.append((param, old_val, new_val))

        # 두 observer 등록 (하나는 실패, 하나는 성공)
        tm.register_observer(failing_observer)
        tm.register_observer(working_observer)

        # Exception이 propagate되지 않고, working_observer는 실행되어야 함
        tm.set_threshold(1.2)

        assert len(notified) == 1, "Working observer가 실행되지 않음"
        assert float(notified[0][2]) == 1.2, "Observer가 잘못된 값 받음"

    def test_change_history_tracking(self):
        """변경 기록 추적"""
        tm = get_threshold_manager()

        initial = tm.get_threshold()
        tm.set_threshold(1.2)
        tm.set_threshold(1.4)

        history = tm.get_change_history()
        assert len(history) >= 2, f"변경 기록 부족: {len(history)}"

        # 최신 변경 확인 (get_change_history()는 최신순 반환 → history[0]이 최신)
        last_change = history[0]
        # Parameter 이름은 'threshold' 또는 'global_probability_threshold' 가능
        assert last_change.parameter in ['threshold', 'global_probability_threshold'], \
            f"잘못된 파라미터: {last_change.parameter}"
        assert float(last_change.new_value) == 1.4, \
            f"잘못된 새 값: {last_change.new_value}"

    def test_ml_thresholds(self):
        """ML 관련 threshold 값"""
        tm = get_threshold_manager()

        ml_relaxed = tm.get_ml_relaxed_threshold()
        ml_bypass = tm.get_ml_bypass_filters()  # 올바른 메서드 이름
        ml_weight = tm.get_ml_weight()

        assert isinstance(ml_relaxed, float), f"ML relaxed threshold가 float이 아님: {type(ml_relaxed)}"
        assert 0.3 <= ml_relaxed <= 3.0, \
            f"ML relaxed threshold 범위 오류: {ml_relaxed}"

        assert isinstance(ml_bypass, int), "ML bypass가 int가 아님"
        assert 10 <= ml_bypass <= 20, f"ML bypass 범위 오류: {ml_bypass}"

        assert isinstance(ml_weight, float), f"ML weight가 float이 아님: {type(ml_weight)}"
        assert 0.3 <= ml_weight <= 0.8, \
            f"ML weight 범위 오류: {ml_weight}"

    def test_update_ml_relaxed_threshold(self):
        """ML relaxed threshold 업데이트"""
        tm = get_threshold_manager()
        # [FIX] ml_relaxed는 global threshold보다 작아야 하는 불변식(threshold_manager.py:216).
        #       global을 1.0으로 올린 뒤 0.8 설정해야 클램프되지 않음.
        tm.set_threshold(1.0)
        tm.set_ml_relaxed_threshold(0.8)
        assert tm.get_ml_relaxed_threshold() == 0.8, \
            "ML relaxed threshold 업데이트 실패"

    def test_update_ml_bypass_threshold(self):
        """ML bypass filters 업데이트"""
        tm = get_threshold_manager()
        tm.set_ml_bypass_filters(18)
        assert tm.get_ml_bypass_filters() == 18, \
            "ML bypass filters 업데이트 실패"

    def test_update_ml_weight(self):
        """ML weight 업데이트"""
        tm = get_threshold_manager()
        tm.set_ml_weight(0.7)
        assert tm.get_ml_weight() == 0.7, \
            "ML weight 업데이트 실패"

    def test_observer_unregistration(self):
        """Observer 등록 해제"""
        tm = get_threshold_manager()

        # [FIX] set_threshold는 값이 실제로 바뀔 때만 observer를 호출하므로,
        #       싱글톤 상태 누수에 영향받지 않도록 등록 전 알려진 기준값(0.8)으로 먼저 설정한다.
        tm.set_threshold(0.8)

        notified = []

        def test_observer(param, old_val, new_val):
            notified.append((param, old_val, new_val))

        tm.register_observer(test_observer)
        tm.set_threshold(1.1)  # 0.8 -> 1.1 변경 보장 → 알림 1회
        assert len(notified) == 1, "Observer 등록 실패"

        tm.unregister_observer(test_observer)
        tm.set_threshold(1.3)
        assert len(notified) == 1, "Observer 해제 실패 (여전히 알림 받음)"

    def test_multiple_observers(self):
        """여러 Observer 동시 동작"""
        tm = get_threshold_manager()

        notifications = {'obs1': [], 'obs2': [], 'obs3': []}

        def obs1(param, old_val, new_val):
            notifications['obs1'].append((param, old_val, new_val))

        def obs2(param, old_val, new_val):
            notifications['obs2'].append((param, old_val, new_val))

        def obs3(param, old_val, new_val):
            notifications['obs3'].append((param, old_val, new_val))

        tm.register_observer(obs1)
        tm.register_observer(obs2)
        tm.register_observer(obs3)

        tm.set_threshold(1.6)

        assert len(notifications['obs1']) == 1, "Observer 1 알림 실패"
        assert len(notifications['obs2']) == 1, "Observer 2 알림 실패"
        assert len(notifications['obs3']) == 1, "Observer 3 알림 실패"

        # 모두 동일한 값 받아야 함
        assert float(notifications['obs1'][0][2]) == 1.6
        assert float(notifications['obs2'][0][2]) == 1.6
        assert float(notifications['obs3'][0][2]) == 1.6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
