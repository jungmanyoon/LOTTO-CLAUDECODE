#!/usr/bin/env python3
"""
캐시 정리 스크립트
- 오래된 모델 캐시 삭제
- 최신 10개만 유지
- 백테스팅 결과 압축
"""

import os
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def clear_model_cache(cache_dir: str = "cache/models", keep_count: int = 10):
    """모델 캐시 정리 - 최신 N개만 유지"""
    cache_path = Path(cache_dir)
    
    if not cache_path.exists():
        logging.info(f"캐시 디렉토리가 없습니다: {cache_dir}")
        return
    
    # 모든 캐시 파일 수집
    cache_files = []
    for model_type in ['ensemble', 'lstm', 'monte_carlo']:
        pattern = f"{model_type}_*.pkl"
        files = list(cache_path.glob(pattern))
        cache_files.extend(files)
    
    logging.info(f"총 {len(cache_files)}개 캐시 파일 발견")
    
    if len(cache_files) <= keep_count:
        logging.info(f"캐시 파일이 {keep_count}개 이하입니다. 정리하지 않습니다.")
        return
    
    # 수정 시간 기준 정렬
    cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # 최신 N개 제외하고 삭제
    files_to_delete = cache_files[keep_count:]
    deleted_count = 0
    deleted_size = 0
    
    for file in files_to_delete:
        try:
            size = file.stat().st_size
            file.unlink()
            deleted_count += 1
            deleted_size += size
            logging.info(f"삭제: {file.name}")
        except Exception as e:
            logging.error(f"파일 삭제 실패: {file.name} - {e}")
    
    logging.info(f"캐시 정리 완료: {deleted_count}개 파일 삭제, {deleted_size/1024/1024:.2f}MB 절약")

def compress_old_results(results_dir: str = "results", days_old: int = 7):
    """오래된 백테스팅 결과 압축"""
    import zipfile
    
    results_path = Path(results_dir)
    if not results_path.exists():
        logging.info(f"결과 디렉토리가 없습니다: {results_dir}")
        return
    
    # 압축할 파일 수집
    cutoff_date = datetime.now() - timedelta(days=days_old)
    old_files = []
    
    for file in results_path.glob("backtest_*.json"):
        if file.stat().st_mtime < cutoff_date.timestamp():
            old_files.append(file)
    
    if not old_files:
        logging.info(f"{days_old}일 이상 된 백테스팅 결과가 없습니다.")
        return
    
    # 압축 파일 생성
    archive_name = f"archived_results_{datetime.now().strftime('%Y%m%d')}.zip"
    archive_path = results_path / "archive" / archive_name
    archive_path.parent.mkdir(exist_ok=True)
    
    compressed_count = 0
    compressed_size = 0
    
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in old_files:
            try:
                size = file.stat().st_size
                zipf.write(file, file.name)
                file.unlink()  # 압축 후 원본 삭제
                compressed_count += 1
                compressed_size += size
                logging.info(f"압축 및 삭제: {file.name}")
            except Exception as e:
                logging.error(f"파일 압축 실패: {file.name} - {e}")
    
    logging.info(f"결과 압축 완료: {compressed_count}개 파일, {compressed_size/1024/1024:.2f}MB → {archive_path.stat().st_size/1024/1024:.2f}MB")

def clear_temp_files(temp_dir: str = "temp"):
    """임시 파일 정리"""
    temp_path = Path(temp_dir)
    
    if not temp_path.exists():
        logging.info(f"임시 디렉토리가 없습니다: {temp_dir}")
        return
    
    deleted_count = 0
    deleted_size = 0
    
    for file in temp_path.glob("*"):
        if file.is_file():
            try:
                size = file.stat().st_size
                file.unlink()
                deleted_count += 1
                deleted_size += size
                logging.info(f"임시 파일 삭제: {file.name}")
            except Exception as e:
                logging.error(f"임시 파일 삭제 실패: {file.name} - {e}")
    
    logging.info(f"임시 파일 정리 완료: {deleted_count}개 파일, {deleted_size/1024:.2f}KB 삭제")

def optimize_database(db_path: str = "data/combinations.db"):
    """SQLite 데이터베이스 최적화"""
    import sqlite3
    
    if not Path(db_path).exists():
        logging.info(f"데이터베이스가 없습니다: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # VACUUM 실행 (DB 압축 및 최적화)
        logging.info("데이터베이스 VACUUM 실행 중...")
        cursor.execute("VACUUM")
        
        # 통계 업데이트
        cursor.execute("ANALYZE")
        
        conn.commit()
        conn.close()
        
        logging.info("데이터베이스 최적화 완료")
    except Exception as e:
        logging.error(f"데이터베이스 최적화 실패: {e}")

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("로또 예측 시스템 캐시 정리 시작")
    print("=" * 60)
    
    # 1. 모델 캐시 정리 (최신 10개만 유지)
    logging.info("\n[1/4] 모델 캐시 정리...")
    clear_model_cache(keep_count=10)
    
    # 2. 오래된 백테스팅 결과 압축 (7일 이상)
    logging.info("\n[2/4] 백테스팅 결과 압축...")
    compress_old_results(days_old=7)
    
    # 3. 임시 파일 정리
    logging.info("\n[3/4] 임시 파일 정리...")
    clear_temp_files()
    
    # 4. 데이터베이스 최적화
    logging.info("\n[4/4] 데이터베이스 최적화...")
    optimize_database()
    
    print("\n" + "=" * 60)
    print("캐시 정리 완료!")
    print("=" * 60)

if __name__ == "__main__":
    main()