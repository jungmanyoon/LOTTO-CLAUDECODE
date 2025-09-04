"""
알림 시스템 (스텁 구현)
"""
import logging
from typing import List, Dict, Any
from datetime import datetime


class AlertSystem:
    """알림 시스템 클래스"""
    
    def __init__(self):
        """알림 시스템 초기화"""
        self.alerts = []
        self.alert_handlers = []
        logging.info("AlertSystem 초기화 (스텁)")
    
    def send_alert(self, level: str, message: str, details: Dict[str, Any] = None):
        """알림 전송"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            'details': details or {}
        }
        
        self.alerts.append(alert)
        
        # 로그로 출력 (실제 구현에서는 이메일, 슬랙 등으로 전송)
        if level == 'critical':
            logging.critical(f"🚨 CRITICAL: {message}")
        elif level == 'error':
            logging.error(f"❌ ERROR: {message}")
        elif level == 'warning':
            logging.warning(f"⚠️ WARNING: {message}")
        else:
            logging.info(f"ℹ️ INFO: {message}")
    
    def send_notification(self, message: str):
        """일반 알림 전송"""
        self.send_alert('info', message)
    
    def get_recent_alerts(self, count: int = 10) -> List[Dict[str, Any]]:
        """최근 알림 반환"""
        return self.alerts[-count:] if self.alerts else []
    
    def clear_alerts(self):
        """알림 초기화"""
        self.alerts.clear()