#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터베이스 초기화 스크립트
기존 데이터베이스를 모두 삭제하고 새로 시작
"""

import os
import shutil
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def clean_databases():
    """데이터베이스 폴더 삭제"""
    
    data_folder = 'data'
    
    if os.path.exists(data_folder):
        try:
            # data 폴더 삭제
            shutil.rmtree(data_folder)
            logging.info(f"{data_folder} 폴더가 삭제되었습니다.")
            logging.info("프로그램을 다시 실행하면 새로운 데이터베이스가 생성됩니다.")
        except Exception as e:
            logging.error(f"폴더 삭제 중 오류 발생: {str(e)}")
            logging.info("수동으로 data 폴더를 삭제해주세요.")
    else:
        logging.info("data 폴더가 존재하지 않습니다.")
    
    # logs 폴더의 로그 파일도 정리
    log_file = 'logs/lotto_app.log'
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
            logging.info("기존 로그 파일이 삭제되었습니다.")
        except Exception as e:
            logging.error(f"로그 파일 삭제 중 오류: {str(e)}")

if __name__ == "__main__":
    logging.info("=== 데이터베이스 초기화 시작 ===")
    
    response = input("정말로 모든 데이터베이스를 삭제하시겠습니까? (y/N): ")
    
    if response.lower() == 'y':
        clean_databases()
        logging.info("\n초기화 완료! main.py를 실행하여 새로 시작하세요.")
    else:
        logging.info("초기화가 취소되었습니다.")