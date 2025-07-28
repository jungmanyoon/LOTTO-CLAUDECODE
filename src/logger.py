import logging
import os
from datetime import datetime
import logging.handlers
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

def setup_logging(config_path: str = None):
    """로깅 설정 초기화
    
    Args:
        config_path: 설정 파일 경로 (기본값: None)
    """
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
            
        # 기존 로그 파일 초기화 (추가된 부분)
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== 새로운 로그 세션 시작: {datetime.now()} ===\n")
        
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