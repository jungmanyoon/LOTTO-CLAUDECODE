"""
리소스 모니터링 시스템 (스텁 구현)
"""
import psutil
import logging
from typing import Dict, Any


class ResourceMonitor:
    """시스템 리소스 모니터링 클래스"""
    
    def __init__(self):
        """리소스 모니터 초기화"""
        self.thresholds = {
            'memory_percent': 85.0,
            'cpu_percent': 80.0,
            'disk_percent': 90.0
        }
        logging.info("ResourceMonitor 초기화 (스텁)")
    
    def get_current_usage(self) -> Dict[str, float]:
        """현재 리소스 사용량 반환"""
        try:
            return {
                'memory_percent': psutil.virtual_memory().percent,
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'disk_percent': psutil.disk_usage('/').percent
            }
        except Exception as e:
            logging.error(f"리소스 모니터링 오류: {e}")
            return {
                'memory_percent': 0.0,
                'cpu_percent': 0.0,
                'disk_percent': 0.0
            }
    
    def check_resources(self) -> Dict[str, Any]:
        """리소스 상태 체크"""
        usage = self.get_current_usage()
        warnings = []
        
        for resource, value in usage.items():
            if value > self.thresholds.get(resource, 100):
                warnings.append(f"{resource}: {value:.1f}% (임계값 초과)")
        
        return {
            'usage': usage,
            'warnings': warnings,
            'healthy': len(warnings) == 0
        }
    
    def log_resource_status(self):
        """리소스 상태 로깅"""
        status = self.check_resources()
        if not status['healthy']:
            for warning in status['warnings']:
                logging.warning(f"리소스 경고: {warning}")