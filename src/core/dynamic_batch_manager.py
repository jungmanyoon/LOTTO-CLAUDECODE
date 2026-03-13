# src/core/dynamic_batch_manager.py
"""
동적 배치 크기 관리자 (PERF-002)

메모리 상태에 따라 배치 크기를 동적으로 조절하여 최적의 성능 유지
"""

import psutil
import logging
from typing import Tuple, Optional


class DynamicBatchManager:
    """메모리 기반 동적 배치 크기 관리

    시스템 메모리 상태를 모니터링하여 최적의 배치 크기를 계산합니다.
    메모리가 부족할 때는 배치 크기를 줄이고, 여유가 있을 때는 늘립니다.
    """

    # 배치당 예상 메모리 (조합 1개당 ~200 bytes)
    BYTES_PER_COMBINATION = 200

    # 안전 마진 (사용 가능 메모리의 60%만 사용)
    SAFETY_MARGIN = 0.6

    # 배치 크기 범위
    MIN_BATCH_SIZE = 10_000
    MAX_BATCH_SIZE = 100_000
    DEFAULT_BATCH_SIZE = 60_000

    # 메모리 임계값
    MEMORY_LOW_THRESHOLD = 80  # 80% 이상이면 배치 크기 감소
    MEMORY_CRITICAL_THRESHOLD = 90  # 90% 이상이면 최소 배치 크기 사용

    # 워커 설정
    MIN_WORKERS = 2
    MAX_WORKERS = 12
    DEFAULT_WORKERS = 8

    _instance: Optional['DynamicBatchManager'] = None

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.logger = logging.getLogger(__name__)
        self._last_batch_size = self.DEFAULT_BATCH_SIZE
        self._last_workers = self.DEFAULT_WORKERS

    @classmethod
    def get_instance(cls) -> 'DynamicBatchManager':
        """싱글톤 인스턴스 반환"""
        return cls()

    def get_memory_info(self) -> dict:
        """현재 메모리 상태 조회"""
        try:
            memory = psutil.virtual_memory()
            return {
                'total': memory.total,
                'available': memory.available,
                'used': memory.used,
                'percent': memory.percent,
                'available_gb': memory.available / (1024 ** 3),
                'used_gb': memory.used / (1024 ** 3)
            }
        except Exception as e:
            self.logger.warning(f"메모리 정보 조회 실패: {e}")
            return {
                'total': 0,
                'available': 0,
                'used': 0,
                'percent': 50,
                'available_gb': 0,
                'used_gb': 0
            }

    def calculate_optimal_batch_size(self) -> int:
        """현재 메모리 상태에 따른 최적 배치 크기 계산"""
        try:
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # 메모리 사용률에 따른 배치 크기 조정
            if memory_percent >= self.MEMORY_CRITICAL_THRESHOLD:
                # 위험: 최소 배치 크기
                batch_size = self.MIN_BATCH_SIZE
                self.logger.warning(
                    f"메모리 위험 ({memory_percent:.1f}%): "
                    f"배치 크기 최소화 → {batch_size:,}"
                )
            elif memory_percent >= self.MEMORY_LOW_THRESHOLD:
                # 경고: 배치 크기 감소
                reduction_factor = (memory_percent - self.MEMORY_LOW_THRESHOLD) / 20
                batch_size = int(
                    self.DEFAULT_BATCH_SIZE * (1 - reduction_factor * 0.5)
                )
                batch_size = max(self.MIN_BATCH_SIZE, batch_size)
                self.logger.info(
                    f"메모리 경고 ({memory_percent:.1f}%): "
                    f"배치 크기 감소 → {batch_size:,}"
                )
            else:
                # 정상: 사용 가능 메모리 기반 계산
                available_bytes = memory.available * self.SAFETY_MARGIN
                optimal_size = int(available_bytes / self.BYTES_PER_COMBINATION)
                batch_size = max(
                    self.MIN_BATCH_SIZE,
                    min(self.MAX_BATCH_SIZE, optimal_size)
                )

            self._last_batch_size = batch_size
            return batch_size

        except Exception as e:
            self.logger.error(f"배치 크기 계산 실패: {e}")
            return self.DEFAULT_BATCH_SIZE

    def calculate_optimal_workers(self) -> int:
        """현재 시스템 상태에 따른 최적 워커 수 계산"""
        try:
            # CPU 코어 수
            cpu_count = psutil.cpu_count(logical=False) or 4

            # 메모리 상태
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # 기본 워커 수 (CPU 코어의 75%)
            workers = max(self.MIN_WORKERS, int(cpu_count * 0.75))

            # 메모리 상태에 따른 조정
            if memory_percent >= self.MEMORY_CRITICAL_THRESHOLD:
                workers = self.MIN_WORKERS
            elif memory_percent >= self.MEMORY_LOW_THRESHOLD:
                workers = max(self.MIN_WORKERS, workers // 2)

            # 최대 제한
            workers = min(self.MAX_WORKERS, workers)

            self._last_workers = workers
            return workers

        except Exception as e:
            self.logger.error(f"워커 수 계산 실패: {e}")
            return self.DEFAULT_WORKERS

    def get_batch_config(self) -> Tuple[int, int]:
        """배치 크기와 워커 수 동시 반환

        Returns:
            Tuple[int, int]: (배치 크기, 워커 수)
        """
        batch_size = self.calculate_optimal_batch_size()
        workers = self.calculate_optimal_workers()
        return batch_size, workers

    def should_reduce_load(self) -> bool:
        """부하 감소 필요 여부 확인"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent >= self.MEMORY_LOW_THRESHOLD
        except Exception:
            return False

    def get_status(self) -> dict:
        """현재 상태 요약"""
        memory_info = self.get_memory_info()
        batch_size, workers = self.get_batch_config()

        return {
            'memory': {
                'percent': memory_info['percent'],
                'available_gb': round(memory_info['available_gb'], 2),
                'used_gb': round(memory_info['used_gb'], 2)
            },
            'config': {
                'batch_size': batch_size,
                'workers': workers
            },
            'thresholds': {
                'low': self.MEMORY_LOW_THRESHOLD,
                'critical': self.MEMORY_CRITICAL_THRESHOLD
            },
            'should_reduce_load': self.should_reduce_load()
        }


# 싱글톤 인스턴스
_manager: Optional[DynamicBatchManager] = None


def get_dynamic_batch_config() -> Tuple[int, int]:
    """동적 배치 설정 조회 (편의 함수)

    Returns:
        Tuple[int, int]: (배치 크기, 워커 수)
    """
    global _manager
    if _manager is None:
        _manager = DynamicBatchManager()
    return _manager.get_batch_config()


def get_batch_manager() -> DynamicBatchManager:
    """배치 관리자 인스턴스 반환"""
    global _manager
    if _manager is None:
        _manager = DynamicBatchManager()
    return _manager
