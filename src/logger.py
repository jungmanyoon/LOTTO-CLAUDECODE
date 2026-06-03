import logging
import os
from datetime import datetime
import logging.handlers
from collections import defaultdict
import time
import json
import hashlib
from typing import Dict, Any, Optional
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

class JSONFormatter(logging.Formatter):
    """JSON 구조화 로그 포매터

    로그를 JSON 형식으로 출력하여 자동화된 분석 및 파싱을 용이하게 합니다.

    출력 형식:
    {
        "timestamp": "2025-10-11T12:34:56.789",
        "level": "INFO",
        "logger": "src.core.filter_manager",
        "message": "필터 처리 완료",
        "extra": {
            "filter_name": "odd_even",
            "processed": 1000,
            "excluded": 350
        }
    }

    사용 예:
        logger = logging.getLogger(__name__)
        logger.info("필터 완료", extra={"filter": "odd_even", "count": 1000})
    """

    def format(self, record):
        """로그 레코드를 JSON 형식으로 포맷팅

        Args:
            record: logging.LogRecord 인스턴스

        Returns:
            str: JSON 형식의 로그 문자열
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }

        # 추가 데이터 처리 (extra 필드)
        extra_data = {}
        for key, value in record.__dict__.items():
            # 표준 로그 필드 제외
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'exc_info',
                          'exc_text', 'stack_info', 'taskName']:
                # JSON 직렬화 가능한 타입만 포함
                try:
                    json.dumps(value)  # 직렬화 가능 여부 테스트
                    extra_data[key] = value
                except (TypeError, ValueError):
                    extra_data[key] = str(value)

        if extra_data:
            log_data["extra"] = extra_data

        # 예외 정보 추가
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)

class FrequencyLimitFilter(logging.Filter):
    """로그 빈도 제한 필터

    동일한 메시지가 짧은 시간 내에 반복되는 것을 방지합니다.

    설정 예:
        - max_per_second: 초당 최대 로그 수 (기본: 1)
        - window_size: 시간 윈도우 크기 (초 단위, 기본: 1)
        - cleanup_interval: 정리 간격 (초 단위, 기본: 60)

    사용 예:
        freq_filter = FrequencyLimitFilter(max_per_second=1, window_size=5)
        handler.addFilter(freq_filter)
    """

    def __init__(self, max_per_second: float = 1.0, window_size: float = 1.0,
                 cleanup_interval: float = 60.0):
        """FrequencyLimitFilter 초기화

        Args:
            max_per_second: 초당 최대 로그 수 (예: 1.0 = 1초에 1개)
            window_size: 시간 윈도우 크기 (초 단위)
            cleanup_interval: 정리 간격 (초 단위)
        """
        super().__init__()
        self.max_per_second = max_per_second
        self.window_size = window_size
        self.cleanup_interval = cleanup_interval

        # 메시지별 타임스탬프 추적 {message_key: [timestamp1, timestamp2, ...]}
        self.message_times: Dict[str, list] = defaultdict(list)

        # 마지막 정리 시간
        self.last_cleanup = time.time()

        # 통계 정보
        self.stats = {
            'total_messages': 0,
            'filtered_messages': 0,
            'unique_messages': 0
        }

    def _get_message_key(self, record: logging.LogRecord) -> str:
        """로그 레코드에서 고유 키 생성

        Args:
            record: logging.LogRecord 인스턴스

        Returns:
            str: 메시지 고유 키 (해시값)
        """
        # 로거 이름 + 메시지 템플릿으로 키 생성
        key_parts = [
            record.name,
            record.msg if isinstance(record.msg, str) else str(record.msg),
            str(record.levelno)
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    def _cleanup_old_entries(self):
        """오래된 타임스탬프 정리"""
        current_time = time.time()

        # cleanup_interval마다 한 번씩 정리
        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        cutoff_time = current_time - self.window_size * 2  # 여유를 두고 정리

        for message_key in list(self.message_times.keys()):
            # 오래된 타임스탬프 제거
            self.message_times[message_key] = [
                ts for ts in self.message_times[message_key]
                if ts > cutoff_time
            ]

            # 빈 리스트 제거
            if not self.message_times[message_key]:
                del self.message_times[message_key]

        self.last_cleanup = current_time

    def filter(self, record: logging.LogRecord) -> bool:
        """로그 레코드 필터링

        Args:
            record: logging.LogRecord 인스턴스

        Returns:
            bool: True면 로그 통과, False면 차단
        """
        self.stats['total_messages'] += 1

        # 주기적 정리
        self._cleanup_old_entries()

        current_time = time.time()
        message_key = self._get_message_key(record)

        # 첫 메시지는 항상 통과
        if message_key not in self.message_times:
            self.message_times[message_key] = [current_time]
            self.stats['unique_messages'] += 1
            return True

        # 시간 윈도우 내의 메시지 수 확인
        window_start = current_time - self.window_size
        recent_times = [ts for ts in self.message_times[message_key] if ts > window_start]

        # 최대 허용 횟수 계산
        max_messages = max(1, int(self.max_per_second * self.window_size))

        if len(recent_times) >= max_messages:
            # 빈도 초과 - 차단
            self.stats['filtered_messages'] += 1
            return False

        # 통과 - 타임스탬프 기록
        self.message_times[message_key].append(current_time)
        return True

    def get_stats(self) -> Dict[str, Any]:
        """필터 통계 정보 반환

        Returns:
            Dict[str, Any]: 통계 정보
        """
        return {
            'total_messages': self.stats['total_messages'],
            'filtered_messages': self.stats['filtered_messages'],
            'unique_messages': self.stats['unique_messages'],
            'filter_rate': (self.stats['filtered_messages'] / self.stats['total_messages'] * 100
                          if self.stats['total_messages'] > 0 else 0.0),
            'active_keys': len(self.message_times)
        }

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
    # 이미 설정되어 있으면 로거 반환 (None 반환 버그 수정)
    if hasattr(setup_logging, '_initialized') and setup_logging._initialized:
        return logging.getLogger()
        
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

        # TTY 여부에 따라 포맷터 선택
        import sys
        if sys.stdout.isatty():
            # 터미널에서는 컬러 포맷터 사용
            console_formatter = CustomFormatter()
        else:
            # 파일로 리다이렉트되거나 파이프일 때는 일반 포맷터
            console_formatter = logging.Formatter(log_format)

        # 파일용 포맷터는 항상 일반 포맷터
        file_formatter = logging.Formatter(log_format)

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

        # 콘솔 핸들러 설정 (컬러 포맷터 사용)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # 파일 핸들러 설정 (로테이션 지원)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            encoding='utf-8',
            mode='a'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        logging.info("로깅 설정이 완료되었습니다.")
        logging.info(f"로그 레벨: {level_str}, 로그 파일: {log_file}")

        # JSON 로깅 설정 (선택적)
        json_logging_enabled = logging_config.get("json_logging", False)
        if json_logging_enabled:
            json_formatter = JSONFormatter()
            # 파일 핸들러에만 JSON 포맷터 적용
            file_handler.setFormatter(json_formatter)
            logging.info("JSON 로깅이 활성화되었습니다.")

        # 빈도 제한 필터 설정 (선택적)
        freq_limit_config = logging_config.get("frequency_limit", {})
        if freq_limit_config.get("enabled", False):
            max_per_second = freq_limit_config.get("max_per_second", 1.0)
            window_size = freq_limit_config.get("window_size", 1.0)
            cleanup_interval = freq_limit_config.get("cleanup_interval", 60.0)

            freq_filter = FrequencyLimitFilter(
                max_per_second=max_per_second,
                window_size=window_size,
                cleanup_interval=cleanup_interval
            )

            # 모든 핸들러에 필터 추가
            for handler in root_logger.handlers:
                handler.addFilter(freq_filter)

            logging.info(f"로그 빈도 제한이 활성화되었습니다. "
                        f"(최대: {max_per_second}/초, 윈도우: {window_size}초)")

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

        # [O] FIX: except 블록에서도 플래그 설정 (중복 호출 방지)
        setup_logging._initialized = True

    # 항상 로거 반환 (None 반환 버그 수정)
    return logging.getLogger()

# ==================== 구조화 로깅 헬퍼 함수 ====================

def log_structured(level: int, event: str, **kwargs):
    """구조화된 로그 메시지 기록

    JSON 로깅과 함께 사용하면 자동화된 분석이 용이합니다.

    Args:
        level: 로그 레벨 (logging.INFO, logging.ERROR 등)
        event: 이벤트 이름/메시지
        **kwargs: 추가 구조화 데이터

    사용 예:
        log_structured(logging.INFO, "filter_completed",
                      filter_name="odd_even",
                      processed=10000,
                      excluded=3500,
                      duration_ms=123.45)

        출력 (JSON 모드):
        {
            "timestamp": "2025-10-11T12:34:56.789",
            "level": "INFO",
            "logger": "root",
            "message": "filter_completed",
            "extra": {
                "filter_name": "odd_even",
                "processed": 10000,
                "excluded": 3500,
                "duration_ms": 123.45
            }
        }
    """
    logger = logging.getLogger()
    logger.log(level, event, extra=kwargs)

def log_filter_progress(filter_name: str, progress_pct: float, **metrics):
    """필터 진행 상황을 표준화된 형식으로 로깅

    Args:
        filter_name: 필터 이름 (예: "odd_even", "consecutive")
        progress_pct: 진행률 (0-100)
        **metrics: 추가 메트릭 (processed, excluded, remaining 등)

    사용 예:
        log_filter_progress("odd_even", 45.5,
                           processed=50000,
                           excluded=18000,
                           remaining=60000,
                           duration_ms=234.56)

        출력 (일반 모드):
        2025-10-11 12:34:56 - INFO - Filter Progress: odd_even (45.5%) - processed=50000, excluded=18000

        출력 (JSON 모드):
        {
            "timestamp": "2025-10-11T12:34:56.789",
            "level": "INFO",
            "logger": "root",
            "message": "Filter Progress: odd_even (45.5%)",
            "extra": {
                "filter_name": "odd_even",
                "progress_pct": 45.5,
                "processed": 50000,
                "excluded": 18000,
                "remaining": 60000,
                "duration_ms": 234.56
            }
        }
    """
    # 메트릭을 문자열로 변환
    metric_str = ", ".join(f"{k}={v}" for k, v in metrics.items())

    # 메시지 생성
    message = f"Filter Progress: {filter_name} ({progress_pct:.1f}%)"
    if metric_str:
        message += f" - {metric_str}"

    # 구조화 데이터에 필터 이름과 진행률 추가
    extra_data = {
        "filter_name": filter_name,
        "progress_pct": progress_pct,
        **metrics
    }

    logger = logging.getLogger()
    logger.info(message, extra=extra_data)

def log_performance_metric(operation: str, duration_ms: float, **context):
    """성능 메트릭을 표준화된 형식으로 로깅

    Args:
        operation: 작업 이름 (예: "filter_processing", "ml_prediction")
        duration_ms: 소요 시간 (밀리초)
        **context: 추가 컨텍스트 (batch_size, record_count 등)

    사용 예:
        log_performance_metric("filter_processing", 1234.56,
                              filter_name="odd_even",
                              batch_size=60000,
                              records_processed=60000)
    """
    message = f"Performance: {operation} ({duration_ms:.2f}ms)"

    extra_data = {
        "operation": operation,
        "duration_ms": duration_ms,
        **context
    }

    logger = logging.getLogger()
    logger.info(message, extra=extra_data)

def log_error_with_context(error_type: str, error_msg: str, **context):
    """에러를 컨텍스트와 함께 로깅

    Args:
        error_type: 에러 타입 (예: "ValidationError", "DatabaseError")
        error_msg: 에러 메시지
        **context: 추가 컨텍스트 정보

    사용 예:
        log_error_with_context("ValidationError",
                              "필터 기준값이 잘못되었습니다",
                              filter_name="odd_even",
                              invalid_value=-1,
                              expected_range="[0, 6]")
    """
    message = f"Error [{error_type}]: {error_msg}"

    extra_data = {
        "error_type": error_type,
        "error_msg": error_msg,
        **context
    }

    logger = logging.getLogger()
    logger.error(message, extra=extra_data)

def configure_json_logging(enable: bool = True,
                          enable_frequency_limit: bool = True,
                          max_per_second: float = 1.0,
                          window_size: float = 1.0):
    """JSON 로깅 및 빈도 제한을 동적으로 설정

    이 함수는 setup_logging() 이후에 호출하여 JSON 로깅을 활성화할 수 있습니다.

    Args:
        enable: JSON 로깅 활성화 여부
        enable_frequency_limit: 빈도 제한 활성화 여부
        max_per_second: 초당 최대 로그 수 (빈도 제한용)
        window_size: 시간 윈도우 크기 (초 단위, 빈도 제한용)

    사용 예:
        # 기본 로깅 설정
        setup_logging()

        # JSON 로깅 및 빈도 제한 활성화
        configure_json_logging(enable=True,
                              enable_frequency_limit=True,
                              max_per_second=2.0,
                              window_size=5.0)

    설정 파일을 통한 제어 (config.yaml):
        logging:
          level: INFO
          format: '%(asctime)s - %(levelname)s - %(message)s'
          file: logs/lotto_app.log
          max_size: 10485760
          backup_count: 5
          # 새로운 옵션들
          json_logging: true  # JSON 로깅 활성화
          frequency_limit:
            enabled: true
            max_per_second: 1.0
            window_size: 1.0
    """
    root_logger = logging.getLogger()

    # JSON 로깅 활성화/비활성화
    if enable:
        json_formatter = JSONFormatter()
        for handler in root_logger.handlers:
            # 파일 핸들러에만 JSON 포맷터 적용 (콘솔은 읽기 편한 형식 유지)
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.setFormatter(json_formatter)
                logging.info("JSON 로깅이 활성화되었습니다.")

    # 빈도 제한 필터 추가
    if enable_frequency_limit:
        freq_filter = FrequencyLimitFilter(
            max_per_second=max_per_second,
            window_size=window_size
        )

        for handler in root_logger.handlers:
            handler.addFilter(freq_filter)

        logging.info(f"로그 빈도 제한이 활성화되었습니다. "
                    f"(최대: {max_per_second}/초, 윈도우: {window_size}초)")

def get_frequency_filter_stats() -> Optional[Dict[str, Any]]:
    """빈도 제한 필터의 통계 정보 반환

    Returns:
        Optional[Dict[str, Any]]: 통계 정보 또는 None (필터가 없는 경우)

    사용 예:
        stats = get_frequency_filter_stats()
        if stats:
            print(f"필터된 메시지: {stats['filtered_messages']}")
            print(f"필터링 비율: {stats['filter_rate']:.2f}%")
    """
    root_logger = logging.getLogger()

    for handler in root_logger.handlers:
        for filter_obj in handler.filters:
            if isinstance(filter_obj, FrequencyLimitFilter):
                return filter_obj.get_stats()

    return None