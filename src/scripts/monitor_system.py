"""시스템 리소스 모니터링 스크립트
필터링 프로세스 실행 중 시스템 상태를 모니터링합니다.
"""

import psutil
import time
import logging
from datetime import datetime
import os
import sys
import json
from typing import Dict, List

class SystemMonitor:
    """시스템 리소스 모니터"""
    
    def __init__(self, interval: int = 5, log_file: str = "logs/system_monitor.log"):
        self.interval = interval
        self.log_file = log_file
        self.stats_history = []
        
        # 로깅 설정
        self._setup_logging()
        
    def _setup_logging(self):
        """로깅 설정"""
        # 로그 디렉토리 생성
        log_dir = os.path.dirname(self.log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 로거 설정
        self.logger = logging.getLogger('SystemMonitor')
        self.logger.setLevel(logging.INFO)
        
        # 파일 핸들러
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 포맷터
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 핸들러 추가
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def get_python_processes(self) -> List[Dict]:
        """Python 프로세스 정보 수집"""
        python_processes = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent']):
                try:
                    if 'python' in proc.info['name'].lower():
                        # 메모리 정보
                        memory_info = proc.info['memory_info']
                        memory_mb = memory_info.rss / (1024 * 1024) if memory_info else 0
                        
                        # 명령줄 정보
                        cmdline = proc.info.get('cmdline', [])
                        script_name = 'unknown'
                        if cmdline and len(cmdline) > 1:
                            for arg in cmdline[1:]:
                                if arg.endswith('.py'):
                                    script_name = os.path.basename(arg)
                                    break
                        
                        python_processes.append({
                            'pid': proc.info['pid'],
                            'script': script_name,
                            'memory_mb': round(memory_mb, 1),
                            'cpu_percent': proc.info.get('cpu_percent', 0)
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            self.logger.error(f"프로세스 정보 수집 오류: {e}")
            
        return python_processes
        
    def collect_stats(self) -> Dict:
        """시스템 통계 수집"""
        try:
            # CPU 정보
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
            
            # 메모리 정보
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024**3)
            memory_available_gb = memory.available / (1024**3)
            memory_total_gb = memory.total / (1024**3)
            
            # 디스크 정보
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024**3)
            
            # 프로세스 정보
            current_process = psutil.Process()
            process_memory_mb = current_process.memory_info().rss / (1024**2)
            process_cpu_percent = current_process.cpu_percent(interval=0.1)
            num_threads = current_process.num_threads()
            
            # Python 프로세스 정보
            python_processes = self.get_python_processes()
            
            stats = {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count,
                    'per_core': cpu_per_core
                },
                'memory': {
                    'percent': memory_percent,
                    'used_gb': round(memory_used_gb, 2),
                    'available_gb': round(memory_available_gb, 2),
                    'total_gb': round(memory_total_gb, 2)
                },
                'disk': {
                    'percent': disk_percent,
                    'free_gb': round(disk_free_gb, 2)
                },
                'current_process': {
                    'memory_mb': round(process_memory_mb, 1),
                    'cpu_percent': process_cpu_percent,
                    'threads': num_threads
                },
                'python_processes': python_processes
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"통계 수집 오류: {e}")
            return {}
            
    def check_alerts(self, stats: Dict):
        """경고 조건 확인"""
        alerts = []
        
        # CPU 경고
        if stats['cpu']['percent'] > 95:
            alerts.append(f"[WARN] CPU 사용률 높음: {stats['cpu']['percent']}%")
            
        # 메모리 경고
        if stats['memory']['percent'] > 90:
            alerts.append(f"[WARN] 메모리 사용률 높음: {stats['memory']['percent']}%")
        elif stats['memory']['percent'] > 80:
            alerts.append(f"[FAST] 메모리 사용률 주의: {stats['memory']['percent']}%")
            
        # 디스크 경고
        if stats['disk']['percent'] > 95:
            alerts.append(f"[WARN] 디스크 사용률 높음: {stats['disk']['percent']}%")
            
        # Python 프로세스 메모리 경고
        for proc in stats['python_processes']:
            if proc['memory_mb'] > 2000:  # 2GB 이상
                alerts.append(f"[WARN] Python 프로세스 메모리 높음: "
                            f"{proc['script']} (PID: {proc['pid']}) - {proc['memory_mb']}MB")
                
        return alerts
        
    def format_log_message(self, stats: Dict) -> str:
        """로그 메시지 포맷"""
        msg_parts = [
            f"CPU: {stats['cpu']['percent']}% (코어: {stats['cpu']['count']})",
            f"메모리: {stats['memory']['percent']}% "
            f"(사용: {stats['memory']['used_gb']}GB/{stats['memory']['total_gb']}GB)",
            f"디스크: {stats['disk']['percent']}% (여유: {stats['disk']['free_gb']}GB)"
        ]
        
        # Python 프로세스 정보
        if stats['python_processes']:
            proc_info = []
            for proc in stats['python_processes']:
                proc_info.append(f"{proc['script']}({proc['memory_mb']}MB)")
            msg_parts.append(f"Python 프로세스: {', '.join(proc_info)}")
            
        return " | ".join(msg_parts)
        
    def save_stats_summary(self):
        """통계 요약 저장"""
        if not self.stats_history:
            return
            
        summary_file = self.log_file.replace('.log', '_summary.json')
        
        # 요약 통계 계산
        cpu_values = [s['cpu']['percent'] for s in self.stats_history]
        memory_values = [s['memory']['percent'] for s in self.stats_history]
        
        summary = {
            'monitoring_period': {
                'start': self.stats_history[0]['timestamp'],
                'end': self.stats_history[-1]['timestamp'],
                'duration_seconds': len(self.stats_history) * self.interval
            },
            'cpu': {
                'average': round(sum(cpu_values) / len(cpu_values), 1),
                'max': max(cpu_values),
                'min': min(cpu_values)
            },
            'memory': {
                'average': round(sum(memory_values) / len(memory_values), 1),
                'max': max(memory_values),
                'min': min(memory_values)
            },
            'sample_count': len(self.stats_history)
        }
        
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            self.logger.info(f"통계 요약 저장: {summary_file}")
        except Exception as e:
            self.logger.error(f"통계 요약 저장 오류: {e}")
            
    def monitor(self, duration: int = None):
        """시스템 모니터링 시작
        
        Args:
            duration: 모니터링 지속 시간(초). None이면 무한 실행
        """
        self.logger.info("="*60)
        self.logger.info("시스템 모니터링 시작")
        self.logger.info(f"간격: {self.interval}초")
        if duration:
            self.logger.info(f"지속 시간: {duration}초")
        self.logger.info("="*60)
        
        start_time = time.time()
        
        try:
            while True:
                # 통계 수집
                stats = self.collect_stats()
                if stats:
                    self.stats_history.append(stats)
                    
                    # 로그 출력
                    log_msg = self.format_log_message(stats)
                    self.logger.info(log_msg)
                    
                    # 경고 확인
                    alerts = self.check_alerts(stats)
                    for alert in alerts:
                        self.logger.warning(alert)
                        
                    # 로그 플러시
                    for handler in self.logger.handlers:
                        if hasattr(handler, 'flush'):
                            handler.flush()
                
                # 종료 조건 확인
                if duration and (time.time() - start_time) > duration:
                    break
                    
                # 대기
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.logger.info("사용자에 의해 모니터링 중단")
        except Exception as e:
            self.logger.error(f"모니터링 오류: {e}")
        finally:
            # 통계 요약 저장
            self.save_stats_summary()
            self.logger.info("시스템 모니터링 종료")
            
def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='시스템 리소스 모니터링')
    parser.add_argument('--interval', type=int, default=5,
                       help='모니터링 간격(초, 기본값: 5)')
    parser.add_argument('--duration', type=int, default=None,
                       help='모니터링 지속 시간(초, 기본값: 무한)')
    parser.add_argument('--log-file', type=str, default='logs/system_monitor.log',
                       help='로그 파일 경로')
    
    args = parser.parse_args()
    
    # 모니터 생성 및 실행
    monitor = SystemMonitor(interval=args.interval, log_file=args.log_file)
    monitor.monitor(duration=args.duration)
    
if __name__ == "__main__":
    main()