import concurrent.futures
import logging
import requests
from bs4 import BeautifulSoup
import time
import re
from tqdm import tqdm

class DataCollector:
    def __init__(self, db_manager=None, meta_manager=None):
        self.db_manager = db_manager
        self.meta_manager = meta_manager
        self.base_url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'

    def fetch_lotto_data(self, max_retries=3):
        """로또 당첨 번호와 날짜를 웹사이트에서 크롤링하여 데이터베이스에 저장"""
        try:
            logging.info("\n[1단계] 최신 회차 정보 확인 중...")
            latest_round = self.get_latest_round()
            if latest_round is None:
                logging.error("최신 회차 번호를 가져오지 못했습니다.")
                return

            # 마지막으로 저장된 회차 확인
            last_saved_round = self.db_manager.get_last_round()
            logging.info(f"- 웹사이트 최신 회차: {latest_round}")
            logging.info(f"- DB 저장된 마지막 회차: {last_saved_round}")
            
            if last_saved_round >= latest_round:
                logging.info("\n[작업 완료] 데이터가 이미 최신 상태입니다.")
                logging.info("="*60)
                return
                
            start_round = (last_saved_round + 1) if last_saved_round else 1
            remaining_rounds = latest_round - start_round + 1
            logging.info(f"- 수집 필요 회차: {remaining_rounds}회 ({start_round}회 → {latest_round}회)")

            logging.info("\n[2단계] 데이터 수집 시작...")
            
            # 배치 처리를 위한 설정
            batch_size = 10
            success_count = 0
            error_count = 0
            
            # tqdm으로 진행률 표시
            with tqdm(total=remaining_rounds, 
                    desc="- 진행률", 
                    unit="회차") as pbar:
                
                for batch_start in range(start_round, latest_round + 1, batch_size):
                    batch_end = min(batch_start + batch_size, latest_round + 1)
                    batch_rounds = range(batch_start, batch_end)
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_round = {
                            executor.submit(self.collect_round_data, round_num, max_retries): round_num 
                            for round_num in batch_rounds
                        }
                        
                        for future in concurrent.futures.as_completed(future_to_round):
                            if future.result():
                                success_count += 1
                            else:
                                error_count += 1
                            pbar.update(1)

            # 수집 결과 요약
            logging.info("\n[3단계] 데이터 수집 결과")
            logging.info(f"- 성공: {success_count}회차")
            logging.info(f"- 실패: {error_count}회차")
            logging.info("="*60)

        except Exception as e:
            logging.error(f"데이터 수집 중 오류 발생: {str(e)}")
            logging.info("="*60)
            raise

    def get_latest_round(self):
        """웹사이트에서 가장 최신 회차 번호를 가져옴"""
        try:
            response = requests.get(self.base_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                desc_tag = soup.find('meta', attrs={'name': 'description'})
                if desc_tag and 'content' in desc_tag.attrs:
                    round_match = re.search(r'(\d+)회', desc_tag['content'])
                    if round_match:
                        return int(round_match.group(1))
            return None
        except Exception as e:
            logging.error(f"최신 회차 번호 가져오기 중 에러 발생: {e}")
            return None

    def collect_round_data(self, round_num, max_retries):
        """특정 회차의 데이터를 수집하고 저장"""
        retries = 0
        while retries < max_retries:
            try:
                params = {'drwNo': round_num}
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(self.base_url, params=params, headers=headers)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    numbers = self.parse_numbers(soup)
                    date = self.parse_date(soup)
                    
                    if numbers and date:
                        self.db_manager.insert_lotto_numbers(round_num, numbers, date)
                        # logging.info(f"회차 {round_num} 데이터 수집 및 저장 성공") # 이 줄 제거
                        return True
                    
                # logging.warning(f"회차 {round_num} 데이터 수집 실패") # 이 줄 제거
                
            except Exception as e:
                # logging.error(f"회차 {round_num} 데이터 수집 중 에러 발생: {e}") # 이 줄 제거
                pass  # 에러 발생 시 조용히 재시도
            
            retries += 1
            if retries < max_retries:
                time.sleep(1)
        
        return False

    def parse_date(self, soup):
        """BeautifulSoup 객체에서 추첨 날짜를 추출"""
        try:
            date_tag = soup.find('p', class_='desc')
            if date_tag:
                date_match = re.search(r'\((\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', date_tag.text)
                if date_match:
                    year, month, day = date_match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            return None
        except Exception as e:
            logging.error(f"날짜 파싱 중 에러 발생: {e}")
            return None

    def parse_numbers(self, soup):
        """BeautifulSoup 객체에서 로또 번호를 추출"""
        try:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag and 'content' in desc_tag.attrs:
                numbers_match = re.search(r'당첨번호\s*([\d,]+)\+(\d+)', desc_tag['content'])
                if numbers_match:
                    return [int(num) for num in numbers_match.group(1).split(',')]
            return None
        except Exception as e:
            logging.error(f"번호 파싱 중 에러 발생: {e}")
            return None