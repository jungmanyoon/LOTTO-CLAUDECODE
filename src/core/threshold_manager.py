"""
임계값 중앙 관리 시스템 (Single Source of Truth)

목표: 시스템 전체에서 임계값이 일관되게 사용되도록 중앙 관리
- 싱글톤 패턴으로 전역 단일 인스턴스 보장
- Observer 패턴으로 자동 동기화
- Decimal을 사용하여 부동소수점 오류 완전 제거
- 변경 추적 로깅으로 디버깅 용이
"""

import logging
import threading
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, List, Optional, Dict, Any
from dataclasses import dataclass
import yaml
import os
from datetime import datetime

@dataclass
class ThresholdChange:
    """임계값 변경 이벤트"""
    parameter: str
    old_value: Any
    new_value: Any
    timestamp: datetime
    source: str  # 변경 소스 (config, optimizer, manual 등)

class ThresholdManager:
    """
    임계값 중앙 관리자 (Singleton Pattern)

    로또 예측 시스템의 모든 확률 임계값을 중앙에서 관리하는 싱글톤 클래스입니다.
    Observer 패턴을 사용하여 임계값 변경 시 연결된 모든 컴포넌트에 자동 전파합니다.

    핵심 기능:
        - 전역 임계값의 단일 진실 공급원 (Single Source of Truth)
        - Observer 패턴으로 모든 컴포넌트에 변경 자동 전파
        - Decimal 사용으로 부동소수점 오류 완전 제거
        - 변경 이력 추적 및 로깅 (최대 100개)
        - 설정 파일과 자동 동기화

    관리 임계값:
        - global_probability_threshold: 전역 확률 임계값 (0.3~3.0%)
        - ml_relaxed_threshold: ML 완화 임계값 (0.1~2.0%)
        - ml_bypass_filters: ML 우회 필터 수
        - ml_weight: ML 가중치

    사용 예시:
        >>> tm = ThresholdManager.get_instance()  # 싱글톤 인스턴스
        >>> threshold = tm.get_threshold()  # 현재 임계값
        >>> tm.set_threshold(1.5, source="optimizer")  # 임계값 설정
        >>> tm.register_observer(my_callback)  # Observer 등록

    Observer 패턴:
        임계값 변경 시 등록된 모든 observer 콜백이 호출됩니다.
        콜백 시그니처: callback(param: str, old_value: Any, new_value: Any)

        >>> def on_threshold_change(param, old_val, new_val):
        ...     print(f"{param}: {old_val} -> {new_val}")
        >>> tm.register_observer(on_threshold_change)

    Decimal 정밀도:
        모든 임계값은 Decimal 타입으로 저장되어 부동소수점 오류를 방지합니다.
        소수점 2자리까지 ROUND_HALF_UP 방식으로 반올림됩니다.

    Thread Safety:
        - 싱글톤 패턴에 threading.Lock 사용
        - 값 변경에 threading.RLock 사용
        - 모든 setter/getter는 thread-safe

    Attributes:
        _threshold: 전역 확률 임계값 (Decimal)
        _ml_relaxed_threshold: ML 완화 임계값 (Decimal)
        _observers: 등록된 observer 콜백 리스트
        _change_history: 변경 이력 리스트

    Note:
        - 항상 get_instance()로 인스턴스를 얻으세요.
        - 테스트 시 ThresholdManager.reset_instance()로 초기화하세요.
        - 설정 파일: configs/adaptive_filter_config.yaml

    See Also:
        - FilterManager: 임계값 observer로 등록됨
        - ThresholdOptimizer: Optuna 기반 임계값 최적화
        - SmartAutoLearning: 24시간 자동 학습 시스템
    """

    # 싱글톤 패턴
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        """ThresholdManager() 직접 호출 시에도 싱글톤 반환"""
        return cls.get_instance()

    @classmethod
    def get_instance(cls):
        """
        Thread-safe singleton instance getter

        Race condition 수정: double-checked locking 대신 single lock 사용
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = object.__new__(cls)
                cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """
        Separate initialization from __new__ to avoid race conditions

        이미 초기화되었으면 skip (중복 초기화 방지)
        """
        if hasattr(self, '_initialized_flag'):
            return

        self._initialized_flag = True

        # 임계값 파라미터 (Decimal로 정밀도 보장)
        self._threshold = Decimal("1.0")  # global_probability_threshold
        self._ml_relaxed_threshold = Decimal("0.5")  # ML 완화 임계값
        self._ml_bypass_filters = 15  # ML 우회 필터 수
        self._ml_weight = Decimal("0.6")  # ML 가중치

        # Observer 패턴: 변경 알림을 받을 콜백 리스트
        self._observers: List[Callable] = []

        # 변경 이력 추적
        self._change_history: List[ThresholdChange] = []
        self._max_history = 100  # 최대 이력 보관 개수

        # 설정 파일 경로
        self._config_path = "configs/adaptive_filter_config.yaml"

        # 스레드 안전성을 위한 락
        self._value_lock = threading.RLock()

        logging.info("[ThresholdManager] 중앙 관리자 초기화 완료")

    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 초기화 (테스트용)"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False
            logging.info("[ThresholdManager] 싱글톤 인스턴스 리셋 완료")

    # ========================================================================
    # 임계값 설정 메서드 (Setter)
    # ========================================================================

    def set_threshold(self, value: float, source: str = "manual") -> None:
        """
        전역 확률 임계값 설정 (global_probability_threshold)

        Args:
            value: 새로운 임계값 (0.3 ~ 3.0)
            source: 변경 소스 (config, optimizer, manual)
        """
        with self._value_lock:
            if value is None:
                logging.warning(f"[ThresholdManager] set_threshold: None 값 무시 (소스: {source})")
                return
            # Decimal로 변환 (소수점 2자리 반올림)
            new_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # 범위 검증 (YAML adaptive_options.min/max_threshold 연동; 미로드 시 0.3~3.0 기본)
            _min = getattr(self, '_min_threshold', Decimal("0.3"))
            _max = getattr(self, '_max_threshold', Decimal("3.0"))
            if not (_min <= new_value <= _max):
                logging.warning(f"[ThresholdManager] 임계값 범위 초과 무시: {new_value} (허용: {_min}~{_max})")
                return

            # 변경 감지
            if self._threshold != new_value:
                old_value = self._threshold
                self._threshold = new_value

                # 변경 이력 기록
                change = ThresholdChange(
                    parameter="global_probability_threshold",
                    old_value=float(old_value),
                    new_value=float(new_value),
                    timestamp=datetime.now(),
                    source=source
                )
                self._record_change(change)

                # Observer 알림
                self._notify_observers("threshold", old_value, new_value)

                # 로그 출력
                logging.info(f"[ThresholdManager] 임계값 변경: {float(old_value):.2f}% → {float(new_value):.2f}% (소스: {source})")

    def set_ml_relaxed_threshold(self, value: float, source: str = "manual") -> None:
        """
        ML 완화 임계값 설정

        Args:
            value: ML 완화 임계값 (0.1 ~ 2.0, global_threshold보다 낮아야 함)
            source: 변경 소스
        """
        with self._value_lock:
            if value is None:
                logging.warning(f"[ThresholdManager] set_ml_relaxed_threshold: None 값 무시 (소스: {source})")
                return
            new_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # 범위 검증
            if not (Decimal("0.1") <= new_value <= Decimal("2.0")):
                logging.warning(f"[ThresholdManager] ML 임계값 범위 초과 무시: {new_value} (허용: 0.1~2.0)")
                return

            # global_threshold보다 작아야 함
            if new_value >= self._threshold:
                logging.warning(f"[ThresholdManager] ML 임계값이 전역 임계값 이상이므로 조정: {new_value} → {self._threshold - Decimal('0.1')}")
                new_value = self._threshold - Decimal("0.1")

            if self._ml_relaxed_threshold != new_value:
                old_value = self._ml_relaxed_threshold
                self._ml_relaxed_threshold = new_value

                change = ThresholdChange(
                    parameter="ml_relaxed_threshold",
                    old_value=float(old_value),
                    new_value=float(new_value),
                    timestamp=datetime.now(),
                    source=source
                )
                self._record_change(change)

                self._notify_observers("ml_relaxed_threshold", old_value, new_value)
                logging.info(f"[ThresholdManager] ML 임계값 변경: {float(old_value):.2f}% → {float(new_value):.2f}% (소스: {source})")

    def set_ml_bypass_filters(self, value: int, source: str = "manual") -> None:
        """
        ML 우회 필터 수 설정

        Args:
            value: 우회 필터 수 (8 ~ 20)
            source: 변경 소스
        """
        with self._value_lock:
            if value is None:
                logging.warning(f"[ThresholdManager] set_ml_bypass_filters: None 값 무시 (소스: {source})")
                return
            if not (8 <= value <= 20):
                logging.warning(f"[ThresholdManager] ML 우회 필터 범위 초과 무시: {value} (허용: 8~20)")
                return

            if self._ml_bypass_filters != value:
                old_value = self._ml_bypass_filters
                self._ml_bypass_filters = value

                change = ThresholdChange(
                    parameter="ml_bypass_filters",
                    old_value=old_value,
                    new_value=value,
                    timestamp=datetime.now(),
                    source=source
                )
                self._record_change(change)

                self._notify_observers("ml_bypass_filters", old_value, value)
                logging.info(f"[ThresholdManager] ML 우회 필터 변경: {old_value} → {value} (소스: {source})")

    def set_ml_weight(self, value: float, source: str = "manual") -> None:
        """
        ML 가중치 설정

        Args:
            value: ML 가중치 (0.1 ~ 1.0)
            source: 변경 소스
        """
        with self._value_lock:
            if value is None:
                logging.warning(f"[ThresholdManager] set_ml_weight: None 값 무시 (소스: {source})")
                return
            new_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if not (Decimal("0.1") <= new_value <= Decimal("1.0")):
                logging.warning(f"[ThresholdManager] ML 가중치 범위 초과 무시: {new_value} (허용: 0.1~1.0)")
                return

            if self._ml_weight != new_value:
                old_value = self._ml_weight
                self._ml_weight = new_value

                change = ThresholdChange(
                    parameter="ml_weight",
                    old_value=float(old_value),
                    new_value=float(new_value),
                    timestamp=datetime.now(),
                    source=source
                )
                self._record_change(change)

                self._notify_observers("ml_weight", old_value, new_value)
                logging.info(f"[ThresholdManager] ML 가중치 변경: {float(old_value):.2f} → {float(new_value):.2f} (소스: {source})")

    # ========================================================================
    # 임계값 조회 메서드 (Getter)
    # ========================================================================

    def get_threshold(self) -> float:
        """전역 확률 임계값 조회 (global_probability_threshold)"""
        with self._value_lock:
            return float(self._threshold)

    def get_ml_relaxed_threshold(self) -> float:
        """ML 완화 임계값 조회"""
        with self._value_lock:
            return float(self._ml_relaxed_threshold)

    def get_ml_bypass_filters(self) -> int:
        """ML 우회 필터 수 조회"""
        with self._value_lock:
            return self._ml_bypass_filters

    def get_ml_weight(self) -> float:
        """ML 가중치 조회"""
        with self._value_lock:
            return float(self._ml_weight)

    def get_all_parameters(self) -> Dict[str, Any]:
        """모든 파라미터 조회"""
        with self._value_lock:
            return {
                'global_probability_threshold': float(self._threshold),
                'ml_relaxed_threshold': float(self._ml_relaxed_threshold),
                'ml_bypass_filters': self._ml_bypass_filters,
                'ml_weight': float(self._ml_weight)
            }

    # ========================================================================
    # Observer 패턴 구현
    # ========================================================================

    def register_observer(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        변경 알림을 받을 Observer 등록

        Args:
            callback: 콜백 함수 (parameter, old_value, new_value 인자)
        """
        with self._value_lock:
            if callback not in self._observers:
                self._observers.append(callback)
                logging.debug(f"[ThresholdManager] Observer 등록: {callback.__name__}")

    def unregister_observer(self, callback: Callable) -> None:
        """Observer 등록 해제"""
        with self._value_lock:
            if callback in self._observers:
                self._observers.remove(callback)
                logging.debug(f"[ThresholdManager] Observer 해제: {callback.__name__}")

    def _notify_observers(self, param: str, old_value: Any, new_value: Any) -> None:
        """
        모든 Observer에게 변경 알림

        실패한 observer를 수집하여 경고 로그 출력 (BUG-003 수정)
        다음 observer로 진행하여 부분 실패 허용
        """
        failed_observers = []

        with self._value_lock:
            # Copy list to avoid modification during iteration
            for observer in self._observers[:]:
                try:
                    observer(param, old_value, new_value)
                except Exception as e:
                    observer_name = getattr(observer, '__name__', repr(observer))
                    logging.error(f"[ThresholdManager] Observer 알림 실패 ({observer_name}): {e}")
                    failed_observers.append((observer_name, e))

        # Log summary if any failures occurred
        if failed_observers:
            logging.warning(
                f"[ThresholdManager] {len(failed_observers)}/{len(self._observers)} "
                f"observers failed for '{param}' update: {old_value} → {new_value}"
            )

    # ========================================================================
    # 설정 파일 연동
    # ========================================================================

    def load_from_config(self, config_path: Optional[str] = None) -> bool:
        """
        설정 파일에서 임계값 로드

        Args:
            config_path: 설정 파일 경로 (기본값: configs/adaptive_filter_config.yaml)

        Returns:
            bool: 로드 성공 여부
        """
        try:
            path = config_path or self._config_path

            if not os.path.exists(path):
                logging.warning(f"[ThresholdManager] 설정 파일 없음: {path}")
                return False

            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 임계값 허용 범위를 YAML(adaptive_options.min/max_threshold)에서 먼저 로드하여
            # set_threshold 검증에 반영한다 (단일 소스 - 과거 0.3~3.0 하드코딩으로 YAML 무시되던 문제 수정)
            adaptive_options = config.get('adaptive_options', {})
            try:
                if 'min_threshold' in adaptive_options:
                    self._min_threshold = Decimal(str(adaptive_options['min_threshold']))
                if 'max_threshold' in adaptive_options:
                    self._max_threshold = Decimal(str(adaptive_options['max_threshold']))
            except (ValueError, TypeError) as _e:
                logging.warning(f"[ThresholdManager] min/max_threshold 파싱 실패, 기본값(0.3~3.0) 유지: {_e}")

            # 설정값 로드 (source="config"로 명시)
            if 'global_probability_threshold' in config:
                self.set_threshold(config['global_probability_threshold'], source="config")

            if 'ml_relaxed_threshold' in config:
                self.set_ml_relaxed_threshold(config['ml_relaxed_threshold'], source="config")

            ml_integration = config.get('ml_integration', {})
            if 'ml_bypass_filters' in ml_integration:
                self.set_ml_bypass_filters(ml_integration['ml_bypass_filters'], source="config")

            if 'ml_weight' in ml_integration:
                self.set_ml_weight(ml_integration['ml_weight'], source="config")

            logging.info(f"[ThresholdManager] 설정 파일 로드 완료: {path}")
            return True

        except Exception as e:
            logging.error(f"[ThresholdManager] 설정 파일 로드 실패: {e}")
            return False

    def save_to_config(self, config_path: Optional[str] = None) -> bool:
        """
        현재 임계값을 설정 파일에 저장

        Args:
            config_path: 설정 파일 경로

        Returns:
            bool: 저장 성공 여부
        """
        try:
            path = config_path or self._config_path

            # 기존 설정 로드
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            # [O] 임계값 업데이트 (정밀도 보존)
            # Decimal → float 변환 시 정밀도 손실 방지:
            # 1.5 (Decimal) → 1.4000000000000001 (float) 현상 방지
            with self._value_lock:
                # 방법 1: round()로 부동소수점 오차 제거
                config['global_probability_threshold'] = round(float(self._threshold), 2)
                config['ml_relaxed_threshold'] = round(float(self._ml_relaxed_threshold), 2)

                if 'ml_integration' not in config:
                    config['ml_integration'] = {}

                config['ml_integration']['ml_bypass_filters'] = self._ml_bypass_filters
                config['ml_integration']['ml_weight'] = round(float(self._ml_weight), 2)

            # 파일 저장 (백업 생성 - configs/backup/ 하위에 최근 N개만 유지하여 디스크 누수 방지.
            # 이전: 매 저장마다 configs/ 루트에 타임스탬프 백업을 무제한 생성 -> 수백 개 누적)
            if os.path.exists(path):
                import shutil
                backup_dir = os.path.join(os.path.dirname(path) or '.', 'backup')
                os.makedirs(backup_dir, exist_ok=True)
                base = os.path.basename(path)
                backup_path = os.path.join(backup_dir, f"{base}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                shutil.copy(path, backup_path)
                # retention: 동일 파일 백업을 최근 10개만 유지
                try:
                    backups = sorted(f for f in os.listdir(backup_dir) if f.startswith(f"{base}.backup_"))
                    for old in backups[:-10]:
                        try:
                            os.remove(os.path.join(backup_dir, old))
                        except OSError:
                            pass
                except OSError:
                    pass
                logging.debug(f"[ThresholdManager] 설정 백업: {backup_path}")

            # [O] YAML 저장 시 float 정밀도 제어
            with open(path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    config,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False  # 순서 유지
                )

            logging.info(f"[ThresholdManager] 설정 파일 저장 완료: {path}")
            return True

        except Exception as e:
            logging.error(f"[ThresholdManager] 설정 파일 저장 실패: {e}")
            return False

    # ========================================================================
    # 변경 이력 관리
    # ========================================================================

    def _record_change(self, change: ThresholdChange) -> None:
        """변경 이력 기록"""
        with self._value_lock:
            self._change_history.append(change)

            # 최대 이력 개수 제한
            if len(self._change_history) > self._max_history:
                self._change_history = self._change_history[-self._max_history:]

    def get_change_history(self, limit: Optional[int] = None) -> List[ThresholdChange]:
        """
        변경 이력 조회

        Args:
            limit: 반환할 최대 이력 개수

        Returns:
            변경 이력 리스트 (최신순)
        """
        with self._value_lock:
            history = list(reversed(self._change_history))
            if limit:
                return history[:limit]
            return history

    def print_change_history(self, limit: int = 10) -> None:
        """변경 이력 출력"""
        history = self.get_change_history(limit)

        if not history:
            logging.info("[ThresholdManager] 변경 이력 없음")
            return

        logging.info(f"\n[ThresholdManager] 최근 {len(history)}개 변경 이력:")
        for i, change in enumerate(history, 1):
            logging.info(
                f"  {i}. [{change.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{change.parameter}: {change.old_value} → {change.new_value} "
                f"(소스: {change.source})"
            )

    # ========================================================================
    # 리소스 정리 (Phase 2.8)
    # ========================================================================

    def cleanup(self) -> None:
        """
        리소스 정리 - observer 목록 초기화 및 캐시 정리

        테스트 격리나 시스템 종료 시 호출
        """
        with self._value_lock:
            observer_count = len(self._observers)
            self._observers.clear()
            self._change_history.clear()
            logging.debug(f"[ThresholdManager] 정리 완료: {observer_count}개 observer 해제")

    def clear_observers(self) -> None:
        """Observer 목록만 초기화 (테스트 격리용)"""
        with self._value_lock:
            observer_count = len(self._observers)
            self._observers.clear()
            logging.debug(f"[ThresholdManager] {observer_count}개 observer 해제")

    # ========================================================================
    # 유틸리티 메서드
    # ========================================================================

    def __str__(self) -> str:
        """문자열 표현"""
        params = self.get_all_parameters()
        return (
            f"ThresholdManager(\n"
            f"  threshold={params['global_probability_threshold']:.2f}%,\n"
            f"  ml_relaxed={params['ml_relaxed_threshold']:.2f}%,\n"
            f"  ml_bypass={params['ml_bypass_filters']},\n"
            f"  ml_weight={params['ml_weight']:.2f}\n"
            f")"
        )

    def __repr__(self) -> str:
        return self.__str__()


# ============================================================================
# 편의 함수
# ============================================================================

def get_threshold_manager() -> ThresholdManager:
    """
    ThresholdManager 싱글톤 인스턴스 가져오기

    첫 호출 시 자동으로 설정 파일에서 임계값 로드

    Returns:
        ThresholdManager 인스턴스
    """
    manager = ThresholdManager.get_instance()

    # 첫 초기화 시에만 설정 파일 자동 로드 (중복 로드 방지)
    if not hasattr(manager, '_config_loaded'):
        manager.load_from_config()
        manager._config_loaded = True
        logging.info("[get_threshold_manager] 설정 파일 자동 로드 완료")

    return manager
