#!/usr/bin/env python3
"""
전체 8,145,060개 조합 생성 스크립트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from itertools import combinations
import logging
import time
from tqdm import tqdm

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def generate_all_combinations():
    """전체 8,145,060개 조합 생성"""
    
    print("=" * 80)
    print("전체 8,145,060개 조합 생성 시작")
    print("=" * 80)
    
    # 데이터베이스 초기화
    db_manager = DatabaseManager()
    
    # 기존 데이터 확인
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM base_combinations")
        current_count = cursor.fetchone()[0]
    
    print(f"\n현재 조합 수: {current_count:,}개")
    
    if current_count >= 8145060:
        print("이미 모든 조합이 생성되어 있습니다.")
        return
    
    # 조합 생성
    print("\n전체 조합 생성 중...")
    start_time = time.time()
    
    # 모든 가능한 조합 생성 (1~45 중 6개 선택)
    all_numbers = list(range(1, 46))
    total_combinations = list(combinations(all_numbers, 6))
    
    print(f"생성된 조합 수: {len(total_combinations):,}개")
    
    # 데이터베이스에 저장
    print("\n데이터베이스에 저장 중...")
    
    # 기존 데이터 삭제
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM base_combinations")
        conn.commit()
        print("기존 데이터 삭제 완료")
    
    # 배치로 저장
    batch_size = 100000
    num_batches = (len(total_combinations) + batch_size - 1) // batch_size
    
    with tqdm(total=num_batches, desc="저장 중", unit="배치") as pbar:
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(total_combinations))
            
            batch = total_combinations[start_idx:end_idx]
            
            # 문자열로 변환
            batch_strings = []
            for combo in batch:
                combo_str = ','.join(map(str, combo))
                batch_strings.append(combo_str)
            
            # 데이터베이스에 삽입
            with db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    "INSERT INTO base_combinations (combination) VALUES (?)",
                    [(combo,) for combo in batch_strings]
                )
                conn.commit()
            
            pbar.update(1)
    
    # 최종 확인
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM base_combinations")
        final_count = cursor.fetchone()[0]
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("생성 완료!")
    print("=" * 80)
    print(f"최종 조합 수: {final_count:,}개")
    print(f"소요 시간: {elapsed_time:.1f}초")
    print(f"처리 속도: {final_count/elapsed_time:.0f}개/초")
    
    # 샘플 확인
    print("\n샘플 조합 (처음 5개):")
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT combination FROM base_combinations LIMIT 5")
        for row in cursor.fetchall():
            print(f"  {row[0]}")
    
    print("\n샘플 조합 (마지막 5개):")
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT combination FROM base_combinations ORDER BY rowid DESC LIMIT 5")
        for row in cursor.fetchall():
            print(f"  {row[0]}")
    
    return final_count

if __name__ == "__main__":
    try:
        result = generate_all_combinations()
        print(f"\n✅ 전체 8,145,060개 조합이 성공적으로 생성되었습니다!")
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()