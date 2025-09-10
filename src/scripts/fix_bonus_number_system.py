#!/usr/bin/env python3
"""
🚨 보너스 번호 시스템 전면 수정 스크립트
작성일: 2024-12-19
작성자: Claude Code Expert

이 스크립트는 로또 시스템의 근본적 결함을 수정합니다:
1. 데이터베이스에 bonus_number 컬럼 추가
2. 데이터 수집 로직 수정
3. 과거 데이터 재수집 (보너스 번호 포함)
4. 백테스팅 2등 판정 로직 추가
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from typing import Tuple, Optional, List
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.logger import setup_logging
from tqdm import tqdm

class BonusNumberFixer:
    """보너스 번호 시스템 수정 클래스"""
    
    def __init__(self):
        setup_logging()
        self.base_url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'
        self.db_path = 'data/lotto_numbers.db'
        logging.info("="*70)
        logging.info("[CRITICAL] 보너스 번호 시스템 전면 수정 시작")
        logging.info("="*70)
    
    def step1_modify_database_schema(self):
        """Step 1: 데이터베이스 스키마 수정"""
        logging.info("\n[Step 1] 데이터베이스 스키마 수정")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 현재 스키마 확인
            cursor.execute("PRAGMA table_info(lotto_numbers)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'bonus_number' not in columns:
                # bonus_number 컬럼 추가
                cursor.execute("ALTER TABLE lotto_numbers ADD COLUMN bonus_number INTEGER")
                conn.commit()
                logging.info("[OK] bonus_number 컬럼 추가 완료")
            else:
                logging.info("[INFO] bonus_number 컬럼이 이미 존재합니다")
            
            # 확인
            cursor.execute("PRAGMA table_info(lotto_numbers)")
            columns = cursor.fetchall()
            logging.info("현재 테이블 구조:")
            for col in columns:
                logging.info(f"  - {col[1]}: {col[2]}")
            
        except Exception as e:
            logging.error(f"[ERROR] 스키마 수정 실패: {e}")
            return False
        finally:
            conn.close()
        
        return True
    
    def parse_numbers_with_bonus(self, soup) -> Optional[Tuple[List[int], int]]:
        """웹페이지에서 메인 번호와 보너스 번호 파싱"""
        try:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag and 'content' in desc_tag.attrs:
                # 당첨번호와 보너스 번호 추출
                numbers_match = re.search(r'당첨번호\s*([\d,]+)\+(\d+)', desc_tag['content'])
                if numbers_match:
                    main_numbers = [int(num) for num in numbers_match.group(1).split(',')]
                    bonus_number = int(numbers_match.group(2))
                    return main_numbers, bonus_number
            
            # 대체 방법: num_win 클래스 찾기
            win_nums = soup.find_all('span', class_='ball_645')
            if len(win_nums) >= 7:
                main_numbers = [int(num.text) for num in win_nums[:6]]
                bonus_number = int(win_nums[6].text)
                return main_numbers, bonus_number
                
        except Exception as e:
            logging.error(f"파싱 오류: {e}")
        
        return None
    
    def parse_date(self, soup):
        """추첨 날짜 파싱"""
        try:
            date_tag = soup.find('p', class_='desc')
            if date_tag:
                date_match = re.search(r'\((\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', date_tag.text)
                if date_match:
                    year, month, day = date_match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception as e:
            logging.error(f"날짜 파싱 오류: {e}")
        return None
    
    def step2_recollect_all_data(self):
        """Step 2: 모든 회차 데이터 재수집 (보너스 번호 포함)"""
        logging.info("\n[Step 2] 전체 데이터 재수집 (보너스 번호 포함)")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 최신 회차 확인
        cursor.execute("SELECT MAX(round) FROM lotto_numbers")
        latest_round = cursor.fetchone()[0] or 1187
        
        logging.info(f"수집 범위: 1회차 ~ {latest_round}회차")
        
        success_count = 0
        error_count = 0
        
        with tqdm(total=latest_round, desc="데이터 수집") as pbar:
            for round_num in range(1, latest_round + 1):
                try:
                    # 웹페이지 요청
                    params = {'drwNo': round_num}
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    response = requests.get(self.base_url, params=params, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        result = self.parse_numbers_with_bonus(soup)
                        
                        if result:
                            main_numbers, bonus_number = result
                            date = self.parse_date(soup)
                            
                            # 데이터베이스 업데이트
                            numbers_str = ','.join(map(str, main_numbers))
                            
                            # 기존 데이터가 있으면 UPDATE, 없으면 INSERT
                            cursor.execute("""
                                INSERT OR REPLACE INTO lotto_numbers 
                                (round, numbers, bonus_number, draw_date, created_at)
                                VALUES (?, ?, ?, ?, datetime('now'))
                            """, (round_num, numbers_str, bonus_number, date))
                            
                            success_count += 1
                            
                            # 10회차마다 커밋
                            if round_num % 10 == 0:
                                conn.commit()
                        else:
                            error_count += 1
                            logging.warning(f"[ERROR] {round_num}회차 파싱 실패")
                    
                    # 서버 부하 방지
                    time.sleep(0.1)
                    
                except Exception as e:
                    error_count += 1
                    logging.error(f"[ERROR] {round_num}회차 수집 오류: {e}")
                
                pbar.update(1)
        
        conn.commit()
        conn.close()
        
        logging.info(f"\n[OK] 수집 완료: 성공 {success_count}회차, 실패 {error_count}회차")
        
        return success_count > 0
    
    def step3_verify_data(self):
        """Step 3: 데이터 검증"""
        logging.info("\n[Step 3] 데이터 검증")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 보너스 번호가 있는 데이터 확인
        cursor.execute("""
            SELECT COUNT(*) FROM lotto_numbers 
            WHERE bonus_number IS NOT NULL
        """)
        bonus_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM lotto_numbers")
        total_count = cursor.fetchone()[0]
        
        logging.info(f"전체 데이터: {total_count}개")
        logging.info(f"보너스 번호 있음: {bonus_count}개 ({bonus_count/total_count*100:.1f}%)")
        
        # 최근 5개 데이터 확인
        cursor.execute("""
            SELECT round, numbers, bonus_number, draw_date 
            FROM lotto_numbers 
            ORDER BY round DESC 
            LIMIT 5
        """)
        
        logging.info("\n최근 5개 회차 데이터:")
        for row in cursor.fetchall():
            round_num, numbers, bonus, date = row
            logging.info(f"  {round_num}회차 ({date}): {numbers} + {bonus}")
        
        conn.close()
        
        return bonus_count > 0
    
    def step4_create_rank_calculation_function(self):
        """Step 4: 등수 계산 함수 생성"""
        logging.info("\n[Step 4] 등수 계산 함수 생성")
        
        code = '''
def calculate_lotto_rank(prediction: List[int], actual: List[int], bonus: int) -> Optional[int]:
    """
    로또 등수 계산 (보너스 번호 포함)
    
    Args:
        prediction: 예측 번호 6개
        actual: 실제 당첨번호 6개
        bonus: 보너스 번호
    
    Returns:
        등수 (1~5) 또는 None (낙첨)
    """
    pred_set = set(prediction)
    actual_set = set(actual)
    
    # 일치 개수
    match_count = len(pred_set & actual_set)
    
    # 보너스 일치 여부
    bonus_match = bonus in pred_set
    
    # 등수 판정
    if match_count == 6:
        return 1  # 1등: 6개 모두 일치
    elif match_count == 5 and bonus_match:
        return 2  # 2등: 5개 + 보너스
    elif match_count == 5:
        return 3  # 3등: 5개
    elif match_count == 4:
        return 4  # 4등: 4개
    elif match_count == 3:
        return 5  # 5등: 3개
    else:
        return None  # 낙첨
'''
        
        # 파일로 저장
        func_file = 'src/utils/rank_calculator.py'
        os.makedirs(os.path.dirname(func_file), exist_ok=True)
        
        with open(func_file, 'w', encoding='utf-8') as f:
            f.write('"""로또 등수 계산 유틸리티"""\n\n')
            f.write('from typing import List, Optional\n\n')
            f.write(code)
            f.write('\n\n')
            f.write('# 당첨금 정보 (2024년 기준 평균)\n')
            f.write('PRIZE_MONEY = {\n')
            f.write('    1: 2_000_000_000,  # 1등: 약 20억\n')
            f.write('    2: 50_000_000,     # 2등: 약 5천만원\n')
            f.write('    3: 1_500_000,      # 3등: 약 150만원\n')
            f.write('    4: 50_000,         # 4등: 5만원\n')
            f.write('    5: 5_000,          # 5등: 5천원\n')
            f.write('}\n')
        
        logging.info(f"[OK] 등수 계산 함수 생성: {func_file}")
        
        return True
    
    def run_all_steps(self):
        """모든 단계 실행"""
        steps = [
            (self.step1_modify_database_schema, "데이터베이스 스키마 수정"),
            (self.step2_recollect_all_data, "전체 데이터 재수집"),
            (self.step3_verify_data, "데이터 검증"),
            (self.step4_create_rank_calculation_function, "등수 계산 함수 생성")
        ]
        
        for step_func, step_name in steps:
            logging.info(f"\n{'='*70}")
            logging.info(f"실행 중: {step_name}")
            logging.info('='*70)
            
            if not step_func():
                logging.error(f"[ERROR] {step_name} 실패!")
                return False
        
        logging.info("\n" + "="*70)
        logging.info("[SUCCESS] 보너스 번호 시스템 수정 완료!")
        logging.info("="*70)
        logging.info("\n다음 단계:")
        logging.info("1. main.py를 실행하여 새로운 데이터로 예측 수행")
        logging.info("2. 백테스팅에서 2등 판정이 제대로 되는지 확인")
        logging.info("3. 대시보드에서 보너스 번호가 일관되게 표시되는지 확인")
        
        return True

def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("[WARNING] 보너스 번호 시스템 전면 수정을 시작합니다.")
    print("이 작업은 전체 데이터를 재수집하므로 시간이 걸릴 수 있습니다.")
    print("="*70 + "\n")
    
    response = input("계속하시겠습니까? (y/n): ")
    if response.lower() != 'y':
        print("작업을 취소했습니다.")
        return
    
    fixer = BonusNumberFixer()
    fixer.run_all_steps()

if __name__ == "__main__":
    main()