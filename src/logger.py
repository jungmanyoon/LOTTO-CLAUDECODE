import logging
import os
from datetime import datetime
import logging.handlers
from collections import defaultdict
import time
from .utils.config_manager import ConfigManager

class CustomFormatter(logging.Formatter):
    """커스텀 로그 포매터"""
    
    # 로그 레벨별 색상 설정
    grey = "\x1b[38;21m"
    blue = "\x1b[34;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    format_string = '%(asctime)s - %(levelname)s - %(message)s'

    FORMATS = {
        logging.DEBUG: grey + format_string + reset,
        logging.INFO: blue + format_string + reset,
        logging.WARNING: yellow + format_string + reset,
        logging.ERROR: red + format_string + reset,
        logging.CRITICAL: bold_red + format_string + reset
    }

    def format(self, record):
        """로그 레코드를 포맷팅"""
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class LogAggregator:
    """로그 집계 및 요약 클래스"""
    
    def __init__(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self.last_summary_time = time.time()
        self.summary_interval = 60  # 60초마다 요약
    
    def count(self, key):
        """카운터 증가"""
        self.counters[key] += 1
    
    def time(self, key, duration):
        """시간 기록"""
        self.timers[key].append(duration)
    
    def should_summarize(self):
        """요약이 필요한지 확인"""
        return time.time() - self.last_summary_time > self.summary_interval
    
    def get_summary(self):
        """요약 정보 반환"""
        summary = {}
        
        # 카운터 요약
        if self.counters:
            summary['counts'] = dict(self.counters)
        
        # 타이머 요약
        if self.timers:
            summary['timings'] = {}
            for key, times in self.timers.items():
                summary['timings'][key] = {
                    'count': len(times),
                    'total': sum(times),
                    'avg': sum(times) / len(times) if times else 0,
                    'min': min(times) if times else 0,
                    'max': max(times) if times else 0
                }
        
        # 초기화
        self.counters.clear()
        self.timers.clear()
        self.last_summary_time = time.time()
        
        return summary

# 전역 로그 집계기
log_aggregator = LogAggregator()

def setup_logging(config_path: str = None):
    """로깅 설정 초기화
    
    Args:
        config_path: 설정 파일 경로 (기본값: None)
    """
    # 이미 설정되어 있으면 스킵
    if hasattr(setup_logging, '_initialized') and setup_logging._initialized:
        return
        
    try:
        # 기본 로그 디렉토리 생성
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 설정 관리자 인스턴스 생성
        # config_path가 없어도 기본 설정을 사용할 수 있도록 처리
        config_manager = ConfigManager(config_path)
        
        # 로깅 설정 로드
        logging_config = config_manager.get_logging_config()
        
        # 로그 레벨 설정
        level_str = logging_config.get("level", "INFO")
        level = getattr(logging, level_str)
        
        # 로그 포맷 설정
        log_format = logging_config.get("format", "%(asctime)s - %(levelname)s - %(message)s")
        formatter = logging.Formatter(log_format)
        
        # 로그 파일 설정
        log_file = logging_config.get("file", "logs/lotto_app.log")
        max_size = logging_config.get("max_size", 10 * 1024 * 1024)  # 10MB 기본값
        backup_count = logging_config.get("backup_count", 5)
        
        # 로그 디렉토리 생성
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 프로그램 시작 시 로그 파일은 main.py에서 이미 초기화됨
        
        # 루트 로거 설정
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # 기존 핸들러 제거
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 콘솔 핸들러 설정
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 파일 핸들러 설정 (로테이션 지원)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        logging.info("로깅 설정이 완료되었습니다.")
        logging.info(f"로그 레벨: {level_str}, 로그 파일: {log_file}")
        
        # 초기화 완료 플래그 설정
        setup_logging._initialized = True
        
    except Exception as e:
        # 기본 로깅 설정 적용
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('logs/lotto_app_fallback.log', encoding='utf-8')
            ]
        )
        logging.error(f"로그 설정 중 오류 발생: {str(e)}")
        logging.warning("기본 로깅 설정을 사용합니다.")