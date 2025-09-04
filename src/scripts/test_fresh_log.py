#!/usr/bin/env python3
"""
완전히 새로운 프로세스에서 로그 초기화 테스트
"""
import os
import sys
import subprocess

# 프로젝트 루트 경로
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_file = os.path.join(project_root, "logs", "lotto_app.log")

print(f"로그 파일 경로: {log_file}")

# 기존 로그 파일 크기 확인
if os.path.exists(log_file):
    before_size = os.path.getsize(log_file)
    print(f"기존 로그 파일 크기: {before_size:,} bytes")
else:
    print("로그 파일이 없습니다.")
    before_size = 0

# 테스트 코드
test_code = '''
import logging
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 기존 핸들러 제거
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# logger 모듈의 초기화 플래그 제거 (있을 경우)
from src import logger
if hasattr(logger.setup_logging, '_initialized'):
    delattr(logger.setup_logging, '_initialized')

# 로깅 재설정
from src.logger import setup_logging
setup_logging()

# 테스트 로그 작성
logging.info("="*60)
logging.info("새로운 프로세스에서의 로그 테스트")
logging.info("="*60)
logging.info("이것이 로그 파일의 첫 번째 메시지여야 합니다.")

for i in range(3):
    logging.info(f"테스트 로그 #{i+1}")
    
logging.info("테스트 완료!")
'''

# 임시 파일로 저장
temp_file = os.path.join(project_root, "temp_log_test.py")
with open(temp_file, 'w', encoding='utf-8') as f:
    f.write(test_code)

# subprocess로 실행
print("\n새로운 Python 프로세스에서 테스트 실행 중...")
result = subprocess.run([sys.executable, temp_file], capture_output=True, text=True)

if result.stdout:
    print("표준 출력:")
    print(result.stdout)
if result.stderr:
    print("표준 에러:")
    print(result.stderr)

# 임시 파일 삭제
os.remove(temp_file)

# 로그 파일 크기 확인
if os.path.exists(log_file):
    after_size = os.path.getsize(log_file)
    print(f"\n새 로그 파일 크기: {after_size:,} bytes")
    
    if before_size > 0 and after_size < before_size:
        print("SUCCESS: 로그 파일이 초기화되었습니다!")
    elif before_size == 0:
        print("SUCCESS: 새 로그 파일이 생성되었습니다!")
    else:
        print("WARNING: 로그 파일이 초기화되지 않았습니다.")
        
    # 로그 파일 처음 몇 줄 확인
    print("\n로그 파일 내용 (처음 10줄):")
    print("-" * 60)
    with open(log_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i < 10:
                print(f"{i+1:3}: {line.rstrip()}")
            else:
                break
    print("-" * 60)