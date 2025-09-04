#!/usr/bin/env python3
"""
로그 파일 초기화 테스트
"""
import logging
import sys
import os
from pathlib import Path
import time

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import setup_logging

def test_log_reset():
    """로그 파일 초기화 테스트"""
    log_file = "logs/lotto_app.log"
    
    # 로그 파일이 있으면 크기 확인
    if os.path.exists(log_file):
        before_size = os.path.getsize(log_file)
        print(f"기존 로그 파일 크기: {before_size:,} bytes")
    else:
        print("로그 파일이 없습니다.")
        before_size = 0
    
    # 로깅 설정 초기화
    setup_logging()
    
    # 테스트 로그 작성
    logging.info("="*60)
    logging.info("로그 파일 초기화 테스트")
    logging.info("="*60)
    logging.info("이 메시지가 로그 파일의 첫 번째 메시지여야 합니다.")
    
    for i in range(5):
        logging.info(f"테스트 로그 메시지 #{i+1}")
    
    logging.info("테스트 완료!")
    
    # 로그 파일 크기 확인
    time.sleep(0.1)  # 파일 쓰기 대기
    if os.path.exists(log_file):
        after_size = os.path.getsize(log_file)
        print(f"\n새 로그 파일 크기: {after_size:,} bytes")
        
        if before_size > 0 and after_size < before_size:
            print("✅ 로그 파일이 초기화되었습니다!")
        elif before_size == 0:
            print("✅ 새 로그 파일이 생성되었습니다!")
        else:
            print("WARNING: 로그 파일이 초기화되지 않았습니다.")
            
        # 로그 파일 내용 확인 (처음 5줄)
        print("\n로그 파일 내용 (처음 5줄):")
        print("-" * 40)
        with open(log_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < 5:
                    print(line.rstrip())
                else:
                    break
        print("-" * 40)

if __name__ == "__main__":
    test_log_reset()