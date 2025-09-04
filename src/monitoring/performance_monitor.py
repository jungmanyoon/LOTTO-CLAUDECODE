"""
성능 모니터링 시스템 (스텁 구현)
실제 구현을 위한 간단한 플레이스홀더
"""
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime


class PerformanceMonitor:
    """성능 모니터링 클래스"""
    
    def __init__(self):
        """성능 모니터 초기화"""
        self.metrics = {}
        self.start_times = {}
        logging.info("PerformanceMonitor 초기화 (스텁)")
    
    def start_timer(self, name: str):
        """타이머 시작"""
        self.start_times[name] = time.time()
    
    def end_timer(self, name: str) -> float:
        """타이머 종료 및 소요 시간 반환"""
        if name in self.start_times:
            elapsed = time.time() - self.start_times[name]
            self.metrics[name] = elapsed
            del self.start_times[name]
            return elapsed
        return 0.0
    
    def get_metrics(self) -> Dict[str, Any]:
        """수집된 메트릭 반환"""
        return self.metrics.copy()
    
    def log_performance(self, operation: str, duration: float, details: Optional[Dict] = None):
        """성능 로그 기록"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'duration': duration,
            'details': details or {}
        }
        logging.info(f"Performance: {operation} - {duration:.3f}s")
        
    def reset(self):
        """메트릭 초기화"""
        self.metrics.clear()
        self.start_times.clear()