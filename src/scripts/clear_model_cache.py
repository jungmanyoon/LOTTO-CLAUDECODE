#!/usr/bin/env python3
"""
모델 캐시 정리 스크립트
손상된 캐시 파일로 인한 에러를 방지하기 위해 캐시를 정리합니다.
"""
import os
import shutil
import logging
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.logger import setup_logging


def clear_model_cache():
    """모델 캐시 디렉토리 정리"""
    setup_logging()
    
    cache_dirs = [
        "cache/models",  # 백테스팅 모델 캐시
        "models/ensemble"  # 앙상블 모델 캐시
    ]
    
    logging.info("="*60)
    logging.info("모델 캐시 정리 시작")
    logging.info("="*60)
    
    total_files = 0
    total_size = 0
    
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            logging.info(f"\n{cache_dir} 디렉토리 정리 중...")
            
            # 파일 수와 크기 계산
            files = os.listdir(cache_dir)
            dir_size = 0
            
            for file in files:
                file_path = os.path.join(cache_dir, file)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    dir_size += file_size
                    logging.info(f"  - {file} ({file_size/1024/1024:.2f} MB)")
            
            total_files += len(files)
            total_size += dir_size
            
            # 디렉토리 삭제 및 재생성
            try:
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                logging.info(f"✅ {cache_dir} 정리 완료")
            except Exception as e:
                logging.error(f"❌ {cache_dir} 정리 실패: {e}")
        else:
            logging.info(f"{cache_dir} 디렉토리가 존재하지 않습니다.")
    
    # 결과 요약
    logging.info("\n" + "="*60)
    logging.info("캐시 정리 완료")
    logging.info("="*60)
    logging.info(f"삭제된 파일: {total_files}개")
    logging.info(f"정리된 용량: {total_size/1024/1024:.2f} MB")
    logging.info("\n이제 새로운 캐시가 생성될 준비가 되었습니다.")
    
    return total_files, total_size


def main():
    """메인 실행 함수"""
    files, size = clear_model_cache()
    
    if files > 0:
        print(f"\n✅ {files}개 파일 ({size/1024/1024:.2f} MB) 정리 완료!")
        print("   main.py를 실행하면 새로운 캐시가 생성됩니다.")
    else:
        print("\n캐시 파일이 없습니다.")


if __name__ == "__main__":
    main()