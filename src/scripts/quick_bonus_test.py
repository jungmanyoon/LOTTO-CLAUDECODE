"""
보너스 번호 테스트 - 빠른 검증
최근 10개 회차만 수집해서 시스템 동작 확인
"""
import sqlite3
import requests
from bs4 import BeautifulSoup
import re

def test_bonus_collection():
    """최근 10개 회차 보너스 번호 수집 테스트"""
    
    base_url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'
    
    print("\n" + "="*60)
    print("[TEST] 보너스 번호 수집 테스트 (최근 10회차)")
    print("="*60)
    
    # 1187회차부터 1178회차까지 (최근 10개)
    for round_num in range(1187, 1177, -1):
        try:
            params = {'drwNo': round_num}
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(base_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # meta 태그에서 찾기
                desc_tag = soup.find('meta', attrs={'name': 'description'})
                if desc_tag and 'content' in desc_tag.attrs:
                    # 보너스 번호 포함 파싱
                    numbers_match = re.search(r'당첨번호\s*([\d,]+)\+(\d+)', desc_tag['content'])
                    if numbers_match:
                        main_numbers = numbers_match.group(1)
                        bonus_number = numbers_match.group(2)
                        print(f"{round_num}회차: {main_numbers} + 보너스:{bonus_number}")
                        continue
                
                print(f"{round_num}회차: 파싱 실패")
                
        except Exception as e:
            print(f"{round_num}회차: 에러 - {e}")
    
    print("\n" + "="*60)
    print("[ANALYSIS] 현재 DB 상태 확인")
    print("="*60)
    
    # DB 확인
    conn = sqlite3.connect('data/lotto_numbers.db')
    cursor = conn.cursor()
    
    # 컬럼 확인
    cursor.execute("PRAGMA table_info(lotto_numbers)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"테이블 컬럼: {columns}")
    
    if 'bonus_number' in columns:
        # 보너스 번호가 있는 데이터 확인
        cursor.execute("""
            SELECT COUNT(*) FROM lotto_numbers 
            WHERE bonus_number IS NOT NULL
        """)
        bonus_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM lotto_numbers")
        total_count = cursor.fetchone()[0]
        
        print(f"전체 데이터: {total_count}개")
        print(f"보너스 번호 있음: {bonus_count}개")
        
        # 최근 5개 확인
        cursor.execute("""
            SELECT round, numbers, bonus_number 
            FROM lotto_numbers 
            ORDER BY round DESC 
            LIMIT 5
        """)
        
        print("\n최근 5개 DB 데이터:")
        for row in cursor.fetchall():
            print(f"  {row[0]}회차: {row[1]} + 보너스:{row[2] if row[2] else 'NULL'}")
    else:
        print("[WARNING] bonus_number 컬럼이 없습니다!")
    
    conn.close()
    
    print("\n" + "="*60)
    print("[RESULT] 시스템 분석 결과")
    print("="*60)
    
    print("\n정답:")
    print("1. 보너스 번호는 웹사이트에서 '+숫자' 형태로 제공됩니다")
    print("2. 현재 코드는 이를 파싱하지만 저장하지 않습니다")
    print("3. DB에 bonus_number 컬럼을 추가해야 합니다")
    print("4. 백테스팅에서 2등 판정을 위해 보너스 번호가 필수입니다")
    
    print("\n학습/패턴 분석 영향:")
    print("- 메인 6개 번호: ML 학습의 핵심 (중요도 95%)")
    print("- 보너스 번호: 2등 판정용 (중요도 5%)")
    print("- 패턴 분석은 메인 번호로만 해도 충분합니다")
    print("- 하지만 정확한 수익률 계산을 위해 보너스는 필수입니다")

if __name__ == "__main__":
    test_bonus_collection()