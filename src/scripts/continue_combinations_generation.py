#!/usr/bin/env python3
"""
조합 생성 이어서 진행
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from itertools import combinations
import sqlite3
import time
from tqdm import tqdm

def continue_generation():
    """이어서 조합 생성"""
    
    db_path = "data/combinations.db"
    
    # 현재 저장된 수 확인
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM base_combinations")
    current_count = cursor.fetchone()[0]
    
    print(f"현재 저장된 조합: {current_count:,}개")
    
    if current_count >= 8145060:
        print("이미 모든 조합이 저장되어 있습니다.")
        return
    
    # 마지막 저장된 조합 확인
    cursor.execute("SELECT combination FROM base_combinations ORDER BY rowid DESC LIMIT 1")
    last_combo = cursor.fetchone()
    
    if last_combo:
        last_numbers = list(map(int, last_combo[0].split(',')))
        print(f"마지막 저장된 조합: {last_numbers}")
    else:
        last_numbers = None
    
    # 모든 조합 생성
    print("\n나머지 조합 생성 중...")
    all_numbers = list(range(1, 46))
    all_combinations = list(combinations(all_numbers, 6))
    
    # 시작 위치 찾기
    if last_numbers:
        start_idx = 0
        for i, combo in enumerate(all_combinations):
            if list(combo) == last_numbers:
                start_idx = i + 1
                break
    else:
        start_idx = current_count
    
    print(f"시작 인덱스: {start_idx:,}")
    remaining = len(all_combinations) - start_idx
    print(f"저장할 조합 수: {remaining:,}개")
    
    # 배치로 저장
    batch_size = 50000  # 더 작은 배치 사이즈
    num_batches = (remaining + batch_size - 1) // batch_size
    
    print(f"\n저장 시작 (배치 크기: {batch_size:,})")
    
    with tqdm(total=num_batches, desc="저장 중", unit="배치") as pbar:
        for batch_num in range(num_batches):
            batch_start = start_idx + (batch_num * batch_size)
            batch_end = min(batch_start + batch_size, len(all_combinations))
            
            batch = all_combinations[batch_start:batch_end]
            
            # 문자열로 변환
            batch_strings = [','.join(map(str, combo)) for combo in batch]
            
            # DB에 저장
            cursor.executemany(
                "INSERT INTO base_combinations (combination) VALUES (?)",
                [(combo,) for combo in batch_strings]
            )
            conn.commit()
            
            pbar.update(1)
            
            # 진행 상황
            total_saved = batch_end
            pbar.set_postfix({
                'total': f"{total_saved:,}",
                'progress': f"{total_saved/8145060*100:.1f}%"
            })
    
    # 최종 확인
    cursor.execute("SELECT COUNT(*) FROM base_combinations")
    final_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n[O] 저장 완료!")
    print(f"최종 조합 수: {final_count:,}개")
    
    if final_count == 8145060:
        print("[O] 전체 8,145,060개 조합이 성공적으로 저장되었습니다!")
    else:
        print(f"[WARN] {8145060 - final_count:,}개가 부족합니다.")

if __name__ == "__main__":
    try:
        continue_generation()
    except KeyboardInterrupt:
        print("\n중단되었습니다.")
    except Exception as e:
        print(f"오류: {str(e)}")
        import traceback
        traceback.print_exc()