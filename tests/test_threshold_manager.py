"""
ThresholdManager 단위 테스트

목적: ThresholdManager의 핵심 기능 검증
- 싱글톤 패턴 동작
- Observer 패턴 동기화
- Decimal 정밀도 유지
- 설정 파일 연동
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.core.threshold_manager import ThresholdManager, get_threshold_manager
from decimal import Decimal
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_singleton_pattern():
    """싱글톤 패턴 테스트"""
    print("\n=== 테스트 1: 싱글톤 패턴 검증 ===")

    # 여러 번 인스턴스 생성 시도
    tm1 = ThresholdManager()
    tm2 = get_threshold_manager()
    tm3 = ThresholdManager()

    # 모두 동일한 인스턴스여야 함
    assert tm1 is tm2, "싱글톤 인스턴스 불일치 (tm1 vs tm2)"
    assert tm2 is tm3, "싱글톤 인스턴스 불일치 (tm2 vs tm3)"

    print("[OK] 싱글톤 패턴 정상 동작")


def test_threshold_precision():
    """부동소수점 정밀도 테스트"""
    print("\n=== 테스트 2: Decimal 정밀도 검증 ===")

    tm = get_threshold_manager()

    # 부동소수점 오류가 발생하기 쉬운 값 설정
    tm.set_threshold(1.7, source="test")

    # Decimal로 정확히 처리되어야 함 (1.7000000000000002가 아닌 1.70)
    threshold = tm.get_threshold()
    print(f"  설정값: 1.7")
    print(f"  반환값: {threshold}")
    print(f"  타입: {type(threshold)}")

    # 소수점 2자리 정밀도 확인
    assert abs(threshold - 1.7) < 0.001, f"정밀도 오류: {threshold} != 1.7"
    assert threshold == 1.7, f"정밀도 오류: {threshold} != 1.7"

    print("[OK] Decimal 정밀도 정상")


def test_observer_pattern():
    """Observer 패턴 동기화 테스트"""
    print("\n=== 테스트 3: Observer 패턴 검증 ===")

    tm = get_threshold_manager()

    # 변경 감지용 플래그
    callback_called = {'count': 0, 'param': None, 'old': None, 'new': None}

    def test_observer(param, old_value, new_value):
        """테스트용 Observer 콜백"""
        callback_called['count'] += 1
        callback_called['param'] = param
        callback_called['old'] = old_value
        callback_called['new'] = new_value
        print(f"  [Observer 호출] {param}: {old_value} → {new_value}")

    # Observer 등록
    tm.register_observer(test_observer)

    # 임계값 변경
    old_threshold = tm.get_threshold()
    tm.set_threshold(2.0, source="test")

    # Observer가 호출되었는지 확인
    assert callback_called['count'] > 0, "Observer가 호출되지 않음"
    assert callback_called['param'] == "threshold", f"잘못된 파라미터: {callback_called['param']}"
    assert callback_called['new'] == Decimal("2.0"), f"잘못된 새 값: {callback_called['new']}"

    print("[OK] Observer 패턴 정상 동작")

    # Observer 등록 해제
    tm.unregister_observer(test_observer)


def test_parameter_validation():
    """파라미터 범위 검증 테스트"""
    print("\n=== 테스트 4: 파라미터 범위 검증 ===")

    tm = get_threshold_manager()

    # 유효 범위 내 값
    tm.set_threshold(1.5, source="test")
    assert tm.get_threshold() == 1.5, "유효 값 설정 실패"
    print("  [+] 유효 범위 내 값 설정 성공 (1.5)")

    # 유효 범위 밖 값 (무시되어야 함)
    tm.set_threshold(5.0, source="test")  # 범위 초과 (3.0 초과)
    assert tm.get_threshold() == 1.5, "범위 초과 값이 적용됨"
    print("  [+] 범위 초과 값 차단 성공 (5.0 무시)")

    tm.set_threshold(0.1, source="test")  # 범위 미만 (0.3 미만)
    assert tm.get_threshold() == 1.5, "범위 미만 값이 적용됨"
    print("  [+] 범위 미만 값 차단 성공 (0.1 무시)")

    print("[OK] 파라미터 범위 검증 정상")


def test_ml_parameters():
    """ML 파라미터 설정 테스트"""
    print("\n=== 테스트 5: ML 파라미터 설정 ===")

    tm = get_threshold_manager()

    # [FIX] ml_relaxed_threshold는 global threshold보다 반드시 작아야 한다는 불변식이 있음
    #       (threshold_manager.py:216, CLAUDE.md "Should be lower than global threshold").
    #       global이 0.5면 ml_relaxed=0.5는 0.4로 클램프됨 → global을 1.0으로 올린 뒤 테스트.
    tm.set_threshold(1.0, source="test")

    # ML 파라미터 설정
    tm.set_ml_relaxed_threshold(0.5, source="test")
    tm.set_ml_bypass_filters(15, source="test")
    tm.set_ml_weight(0.6, source="test")

    # 검증
    assert tm.get_ml_relaxed_threshold() == 0.5, "ML 완화 임계값 설정 실패"
    assert tm.get_ml_bypass_filters() == 15, "ML 우회 필터 설정 실패"
    assert tm.get_ml_weight() == 0.6, "ML 가중치 설정 실패"

    # 전체 파라미터 조회
    params = tm.get_all_parameters()
    print(f"  전체 파라미터: {params}")

    print("[OK] ML 파라미터 설정 정상")


def test_change_history():
    """변경 이력 추적 테스트"""
    print("\n=== 테스트 6: 변경 이력 추적 ===")

    tm = get_threshold_manager()

    # 여러 변경 수행
    tm.set_threshold(1.0, source="config")
    tm.set_threshold(1.5, source="optimizer")
    tm.set_threshold(2.0, source="manual")

    # 변경 이력 조회
    history = tm.get_change_history(limit=5)
    print(f"  최근 {len(history)}개 변경 이력:")
    for i, change in enumerate(history, 1):
        print(f"    {i}. {change.parameter}: {change.old_value} → {change.new_value} (소스: {change.source})")

    assert len(history) > 0, "변경 이력이 기록되지 않음"

    print("[OK] 변경 이력 추적 정상")


def test_config_file_integration():
    """설정 파일 연동 테스트 (선택적)"""
    print("\n=== 테스트 7: 설정 파일 연동 (선택적) ===")

    tm = get_threshold_manager()
    config_path = "configs/adaptive_filter_config.yaml"

    if os.path.exists(config_path):
        # 설정 파일에서 로드
        success = tm.load_from_config(config_path)
        print(f"  설정 파일 로드: {'성공' if success else '실패'}")

        if success:
            print(f"  로드된 임계값: {tm.get_threshold()}")
            print("[OK] 설정 파일 로드 정상")
        else:
            print("[WARN]  설정 파일 로드 실패 (파일 형식 확인 필요)")
    else:
        print(f"  [WARN]  설정 파일 없음: {config_path}")


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "="*60)
    print("ThresholdManager 단위 테스트 시작")
    print("="*60)

    try:
        # 테스트 실행
        test_singleton_pattern()
        test_threshold_precision()
        test_observer_pattern()
        test_parameter_validation()
        test_ml_parameters()
        test_change_history()
        test_config_file_integration()

        print("\n" + "="*60)
        print("[OK] 모든 테스트 통과")
        print("="*60)

    except AssertionError as e:
        print(f"\n[FAIL] 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n[FAIL] 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
