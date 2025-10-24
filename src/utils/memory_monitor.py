"""
메모리 사용량 모니터링 모듈
실시간 메모리 추적 및 리포트
"""

import psutil
import logging
import time
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import threading

@dataclass
class MemorySnapshot:
    """메모리 스냅샷"""
    timestamp: float
    rss_mb: float  # Resident Set Size (실제 사용 메모리)
    vms_mb: float  # Virtual Memory Size (가상 메모리)
    available_mb: float  # 시스템 사용 가능 메모리
    percent: float  # 시스템 메모리 사용률
    description: str = ""

class MemoryMonitor:
    """메모리 사용량 모니터"""

    def __init__(self, threshold_mb: int = 500, enable_warnings: bool = False):
        """
        Args:
            threshold_mb: 메모리 임계값 (MB)
            enable_warnings: 메모리 경고 활성화 여부
        """
        self.threshold_mb = threshold_mb
        self.enable_warnings = enable_warnings  # 경고 활성화 플래그
        self.logger = logging.getLogger(__name__)
        self.process = psutil.Process()
        self.snapshots: List[MemorySnapshot] = []
        self.baseline_mb: Optional[float] = None
        self.peak_mb: float = 0
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None

    def start_monitoring(self, interval: float = 1.0):
        """백그라운드 모니터링 시작

        Args:
            interval: 모니터링 간격 (초)
        """
        if self.monitoring:
            return

        self.monitoring = True
        self.baseline_mb = self.get_current_memory()

        def monitor_loop():
            while self.monitoring:
                snapshot = self.take_snapshot()
                if self.enable_warnings and snapshot.rss_mb > self.threshold_mb:
                    self.logger.warning(f"⚠️ 메모리 임계값 초과: {snapshot.rss_mb:.1f}MB > {self.threshold_mb}MB")
                time.sleep(interval)

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info(f"메모리 모니터링 시작 (임계값: {self.threshold_mb}MB)")

    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.logger.info("메모리 모니터링 중지")

    def get_current_memory(self) -> float:
        """현재 메모리 사용량 반환 (MB)"""
        return self.process.memory_info().rss / 1024 / 1024

    def get_system_memory(self) -> Dict[str, float]:
        """시스템 메모리 정보 반환"""
        mem = psutil.virtual_memory()
        return {
            'total_mb': mem.total / 1024 / 1024,
            'available_mb': mem.available / 1024 / 1024,
            'used_mb': mem.used / 1024 / 1024,
            'percent': mem.percent
        }

    def take_snapshot(self, description: str = "") -> MemorySnapshot:
        """메모리 스냅샷 생성"""
        mem_info = self.process.memory_info()
        sys_mem = psutil.virtual_memory()

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=mem_info.rss / 1024 / 1024,
            vms_mb=mem_info.vms / 1024 / 1024,
            available_mb=sys_mem.available / 1024 / 1024,
            percent=sys_mem.percent,
            description=description
        )

        self.snapshots.append(snapshot)
        self.peak_mb = max(self.peak_mb, snapshot.rss_mb)

        return snapshot

    def log_memory_usage(self, stage: str = ""):
        """메모리 사용량 로깅"""
        snapshot = self.take_snapshot(stage)

        if self.baseline_mb:
            delta = snapshot.rss_mb - self.baseline_mb
            self.logger.info(f"💾 [{stage}] 메모리: {snapshot.rss_mb:.1f}MB "
                           f"(+{delta:.1f}MB), 시스템: {snapshot.percent:.1f}%")
        else:
            self.logger.info(f"💾 [{stage}] 메모리: {snapshot.rss_mb:.1f}MB, "
                           f"시스템: {snapshot.percent:.1f}%")

    def get_report(self) -> str:
        """메모리 사용 리포트 생성"""
        if not self.snapshots:
            return "메모리 스냅샷이 없습니다."

        lines = ["=" * 60]
        lines.append("📊 메모리 사용량 리포트")
        lines.append("=" * 60)

        if self.baseline_mb:
            current = self.get_current_memory()
            total_used = current - self.baseline_mb
            lines.append(f"\n기준선: {self.baseline_mb:.1f}MB")
            lines.append(f"현재: {current:.1f}MB")
            lines.append(f"사용량: {total_used:.1f}MB")
            lines.append(f"최대값: {self.peak_mb:.1f}MB")

        # 시스템 메모리
        sys_mem = self.get_system_memory()
        lines.append(f"\n시스템 메모리:")
        lines.append(f"  - 전체: {sys_mem['total_mb']:.1f}MB")
        lines.append(f"  - 사용 가능: {sys_mem['available_mb']:.1f}MB")
        lines.append(f"  - 사용률: {sys_mem['percent']:.1f}%")

        # 주요 스냅샷
        if len(self.snapshots) > 0:
            lines.append(f"\n주요 스냅샷 (최근 5개):")
            for snapshot in self.snapshots[-5:]:
                if snapshot.description:
                    lines.append(f"  - {snapshot.description}: {snapshot.rss_mb:.1f}MB")

        # 메모리 효율성
        if self.baseline_mb and self.peak_mb:
            efficiency = (1 - (self.peak_mb - self.baseline_mb) / self.threshold_mb) * 100
            efficiency = max(0, min(100, efficiency))
            lines.append(f"\n메모리 효율성: {efficiency:.1f}%")

        lines.append("=" * 60)
        return "\n".join(lines)

    def check_memory_pressure(self) -> bool:
        """메모리 압박 상태 확인"""
        current = self.get_current_memory()
        sys_mem = psutil.virtual_memory()

        # 프로세스가 임계값 초과 또는 시스템 메모리 80% 이상 사용
        if current > self.threshold_mb or sys_mem.percent > 80:
            if self.enable_warnings:
                self.logger.warning(f"⚠️ 메모리 압박 감지: "
                                  f"프로세스 {current:.1f}MB, 시스템 {sys_mem.percent:.1f}%")
            return True
        return False

    def suggest_gc(self) -> bool:
        """가비지 컬렉션 제안"""
        if self.check_memory_pressure():
            import gc
            self.logger.info("🔧 가비지 컬렉션 실행...")
            before = self.get_current_memory()
            gc.collect()
            after = self.get_current_memory()
            freed = before - after
            self.logger.info(f"✅ 메모리 {freed:.1f}MB 해제됨")
            return True
        return False

    def __enter__(self):
        """컨텍스트 관리자 진입"""
        self.baseline_mb = self.get_current_memory()
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 관리자 종료"""
        self.stop_monitoring()
        self.logger.info(self.get_report())

# 전역 모니터 인스턴스
_global_monitor: Optional[MemoryMonitor] = None

def get_memory_monitor(enable_warnings: bool = False) -> MemoryMonitor:
    """전역 메모리 모니터 반환"""
    global _global_monitor
    if _global_monitor is None:
        # 기본적으로 경고 비활성화, 임계값은 1500MB로 설정
        _global_monitor = MemoryMonitor(threshold_mb=1500, enable_warnings=enable_warnings)
    return _global_monitor

def log_memory(stage: str = ""):
    """간편 메모리 로깅"""
    monitor = get_memory_monitor()
    monitor.log_memory_usage(stage)