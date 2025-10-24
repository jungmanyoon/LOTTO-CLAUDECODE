"""
로깅 설정 모듈 - 테스트와의 호환성을 위한 셰임 모듈
"""

# src.logger 모듈의 setup_logging 함수를 재사용
try:
    from src.logger import setup_logging
except ImportError:
    # 대체 구현
    import logging
    import sys
    from pathlib import Path

    def setup_logging(log_file='logs/lotto_app.log', level=logging.INFO):
        """기본 로깅 설정"""
        # 로그 디렉토리 생성
        log_path = Path(log_file).parent
        log_path.mkdir(exist_ok=True, parents=True)

        # 로거 설정
        logger = logging.getLogger()
        logger.setLevel(level)

        # 기존 핸들러 제거
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 포맷터 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 파일 핸들러
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 콘솔 핸들러 (테스트 환경에서는 WARNING 이상만)
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = logging.WARNING if 'pytest' in sys.modules else level
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

# 모듈 내보내기
__all__ = ['setup_logging']