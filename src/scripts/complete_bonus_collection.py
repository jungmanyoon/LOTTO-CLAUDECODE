#!/usr/bin/env python3
"""
보너스 번호 수집 완료 스크립트
빠르게 누락된 보너스 번호만 수집
"""
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
from tqdm import tqdm

def collect_missing_bonus():
    """누락된 보너스 번호만 수집"""
    
    print("\n" + "="*60)
    print("[START] 누락된 보너스 번호 수집")
    print("="*60)
    
    conn = sqlite3.connect('data/lotto_numbers.db')
    cursor = conn.cursor()
    
    # 보너스 번호가 없는 회차들 가져오기
    cursor.execute("""
        SELECT round FROM lotto_numbers 
        WHERE bonus_number IS NULL 
        ORDER BY round DESC
    """)
    missing_rounds = [r[0] for r in cursor.fetchall()]
    
    print(f"수집 대상: {len(missing_rounds)}개 회차")
    
    base_url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    success_count = 0
    error_count = 0
    
    with tqdm(total=len(missing_rounds), desc="보너스 수집") as pbar:
        for round_num in missing_rounds:
            try:
                params = {'drwNo': round_num}
                response = requests.get(base_url, params=params, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # meta 태그에서 보너스 번호 추출
                    desc_tag = soup.find('meta', attrs={'name': 'description'})
                    if desc_tag and 'content' in desc_tag.attrs:
                        numbers_match = re.search(r'당첨번호\s*([\d,]+)\+(\d+)', desc_tag['content'])
                        if numbers_match:
                            bonus_number = int(numbers_match.group(2))
                            
                            # 보너스 번호만 업데이트
                            cursor.execute("""
                                UPDATE lotto_numbers 
                                SET bonus_number = ? 
                                WHERE round = ?
                            """, (bonus_number, round_num))
                            
                            success_count += 1
                            
                            # 10개마다 커밋
                            if success_count % 10 == 0:
                                conn.commit()
                                
                        else:
                            # 대체 방법
                            win_nums = soup.find_all('span', class_='ball_645')
                            if len(win_nums) >= 7:
                                bonus_number = int(win_nums[6].text)
                                cursor.execute("""
                                    UPDATE lotto_numbers 
                                    SET bonus_number = ? 
                                    WHERE round = ?
                                """, (bonus_number, round_num))
                                success_count += 1
                            else:
                                error_count += 1
                    else:
                        error_count += 1
                
                # 서버 부하 방지
                time.sleep(0.05)  # 50ms 대기
                
            except Exception as e:
                error_count += 1
                if error_count <= 5:  # 처음 5개 에러만 출력
                    print(f"Error {round_num}: {e}")
            
            pbar.update(1)
    
    # 최종 커밋
    conn.commit()
    
    print(f"\n[COMPLETE] 성공: {success_count}, 실패: {error_count}")
    
    # 최종 확인
    cursor.execute("SELECT COUNT(*) FROM lotto_numbers WHERE bonus_number IS NOT NULL")
    final_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM lotto_numbers")
    total = cursor.fetchone()[0]
    
    print(f"최종 상태: {final_count}/{total} ({final_count/total*100:.1f}%)")
    
    # 샘플 확인
    cursor.execute("""
        SELECT round, numbers, bonus_number 
        FROM lotto_numbers 
        ORDER BY round DESC 
        LIMIT 5
    """)
    
    print("\n최근 5개 데이터:")
    for row in cursor.fetchall():
        print(f"  {row[0]}회차: {row[1]} + 보너스:{row[2]}")
    
    conn.close()

if __name__ == "__main__":
    collect_missing_bonus()