import concurrent.futures
import logging
import sys
import requests
from bs4 import BeautifulSoup
import time
import re
from tqdm import tqdm
from typing import Dict, Any, Optional, List, Tuple

class DataCollector:
    def __init__(self, db_manager=None, meta_manager=None, lotto_numbers_db=None):
        self.db_manager = db_manager
        self.meta_manager = meta_manager
        self.lotto_numbers_db = lotto_numbers_db  # 통계 저장용 LottoNumbersDB 인스턴스
        # 2025년 동행복권 사이트 개편으로 새 API 사용
        self.api_url = 'https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do'
        self.base_url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'  # 레거시 (폴백용)

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
            
            # tqdm으로 진행률 표시 (Windows stderr flush 오류 방지: file=sys.stdout)
            with tqdm(total=remaining_rounds,
                    desc="- 진행률",
                    unit="회차",
                    file=sys.stdout) as pbar:
                
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
        """새 API를 통해 가장 최신 회차 번호를 가져옴"""
        try:
            # 새 API 사용 (2025년 개편)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.dhlottery.co.kr/lt645/result'
            }
            response = requests.get(
                f'{self.api_url}?srchLtEpsd=all',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                lst = data.get('data', {}).get('list', [])
                if lst:
                    # 리스트의 마지막 항목이 최신 회차
                    latest = max(item.get('ltEpsd', 0) for item in lst)
                    logging.info(f"[DataCollector] 새 API로 최신 회차 확인: {latest}회")
                    return latest

            # 폴백: 레거시 방식 시도
            logging.warning("[DataCollector] 새 API 실패, 레거시 방식 시도...")
            return self._get_latest_round_legacy()

        except Exception as e:
            logging.error(f"최신 회차 번호 가져오기 중 에러 발생: {e}")
            # 폴백: 레거시 방식 시도
            return self._get_latest_round_legacy()

    def _get_latest_round_legacy(self):
        """레거시 방식으로 최신 회차 번호를 가져옴 (폴백용)"""
        try:
            response = requests.get(self.base_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                desc_tag = soup.find('meta', attrs={'name': 'description'})
                if desc_tag and 'content' in desc_tag.attrs:
                    round_match = re.search(r'(\d+)회', desc_tag['content'])
                    if round_match:
                        return int(round_match.group(1))
            return None
        except Exception as e:
            logging.error(f"레거시 방식 최신 회차 조회 실패: {e}")
            return None

    def collect_round_data(self, round_num, max_retries):
        """특정 회차의 데이터를 수집하고 저장 (당첨번호 + 통계)"""
        retries = 0
        while retries < max_retries:
            try:
                # 새 API 사용 (2025년 개편)
                result = self._collect_round_data_new_api(round_num)
                if result:
                    return True

                # 폴백: 레거시 방식 시도
                result = self._collect_round_data_legacy(round_num)
                if result:
                    return True

            except Exception as e:
                logging.debug(f"회차 {round_num} 수집 중 오류: {e}")

            retries += 1
            if retries < max_retries:
                time.sleep(1)

        return False

    def _collect_round_data_new_api(self, round_num: int) -> bool:
        """새 API를 통해 특정 회차의 데이터를 수집"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.dhlottery.co.kr/lt645/result'
            }
            response = requests.get(
                f'{self.api_url}?srchLtEpsd={round_num}',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                lst = data.get('data', {}).get('list', [])

                if lst and len(lst) > 0:
                    item = lst[0]

                    # 당첨번호 추출 (새 API 필드명)
                    numbers = [
                        item.get('tm1WnNo'),
                        item.get('tm2WnNo'),
                        item.get('tm3WnNo'),
                        item.get('tm4WnNo'),
                        item.get('tm5WnNo'),
                        item.get('tm6WnNo')
                    ]
                    bonus = item.get('bnsWnNo')

                    # 날짜 추출 (YYYYMMDD 형식)
                    date_str = item.get('ltRflYmd', '')
                    if date_str and len(date_str) == 8:
                        date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    else:
                        date = None

                    # 유효성 검사
                    if all(n is not None for n in numbers) and bonus is not None:
                        self.db_manager.insert_lotto_numbers_with_bonus(round_num, numbers, bonus, date)

                        # 통계 데이터 추출 및 저장
                        statistics = self._parse_statistics_from_api(item)
                        if statistics and self.lotto_numbers_db:
                            self.lotto_numbers_db.insert_statistics(round_num, statistics)

                        logging.debug(f"[새 API] {round_num}회 수집 완료: {numbers}+{bonus}")
                        return True

            return False

        except Exception as e:
            logging.debug(f"새 API로 {round_num}회 수집 실패: {e}")
            return False

    def _parse_statistics_from_api(self, item: Dict) -> Optional[Dict[str, Any]]:
        """새 API 응답에서 통계 데이터 추출"""
        try:
            statistics = {
                'first_winners': item.get('rnk1WnNope', 0),
                'first_prize': item.get('rnk1WnAmt', 0),
                'second_winners': item.get('rnk2WnNope', 0),
                'second_prize': item.get('rnk2WnAmt', 0),
                'third_winners': item.get('rnk3WnNope', 0),
                'third_prize': item.get('rnk3WnAmt', 0),
                'fourth_winners': item.get('rnk4WnNope', 0),
                'fourth_prize': item.get('rnk4WnAmt', 0),
                'fifth_winners': item.get('rnk5WnNope', 0),
                'fifth_prize': item.get('rnk5WnAmt', 0),
                'total_sales': item.get('totSelAmt', 0)
            }
            return statistics
        except Exception as e:
            logging.debug(f"통계 파싱 실패: {e}")
            return None

    def _collect_round_data_legacy(self, round_num: int) -> bool:
        """레거시 방식으로 특정 회차의 데이터를 수집 (폴백용)"""
        try:
            params = {'drwNo': round_num}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.base_url, params=params, headers=headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                result = self.parse_numbers(soup)
                date = self.parse_date(soup)

                if result and date:
                    numbers, bonus = result
                    self.db_manager.insert_lotto_numbers_with_bonus(round_num, numbers, bonus, date)

                    # 당첨 통계도 함께 수집 및 저장
                    statistics = self.parse_statistics(soup)
                    if statistics and self.lotto_numbers_db:
                        self.lotto_numbers_db.insert_statistics(round_num, statistics)

                    return True

            return False

        except Exception as e:
            logging.debug(f"레거시 방식으로 {round_num}회 수집 실패: {e}")
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
        """BeautifulSoup 객체에서 로또 번호와 보너스 번호를 추출"""
        try:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag and 'content' in desc_tag.attrs:
                numbers_match = re.search(r'당첨번호\s*([\d,]+)\+(\d+)', desc_tag['content'])
                if numbers_match:
                    main_numbers = [int(num) for num in numbers_match.group(1).split(',')]
                    bonus_number = int(numbers_match.group(2))
                    return (main_numbers, bonus_number)  # 튜플로 반환
            return None
        except Exception as e:
            logging.error(f"번호 파싱 중 에러 발생: {e}")
            return None

    def parse_statistics(self, soup) -> Optional[Dict[str, Any]]:
        """BeautifulSoup 객체에서 당첨 통계 정보를 추출

        동행복권 결과 페이지의 당첨 통계 테이블에서
        1~5등 당첨자 수와 당첨금액을 파싱합니다.

        Args:
            soup: BeautifulSoup 객체

        Returns:
            Dict: 통계 데이터 딕셔너리 또는 None
        """
        try:
            statistics = {
                'first_winners': 0, 'first_prize': 0,
                'second_winners': 0, 'second_prize': 0,
                'third_winners': 0, 'third_prize': 0,
                'fourth_winners': 0, 'fourth_prize': 0,
                'fifth_winners': 0, 'fifth_prize': 0,
                'total_sales': 0
            }

            # 당첨 통계 테이블 찾기 (class="tbl_data tbl_data_col")
            stats_table = soup.find('table', class_='tbl_data tbl_data_col')
            if not stats_table:
                # 대체 방법: 여러 테이블 중 당첨 정보가 포함된 테이블 찾기
                tables = soup.find_all('table')
                for table in tables:
                    if table.find('th', string=re.compile(r'등위|순위|당첨')):
                        stats_table = table
                        break

            if stats_table:
                rows = stats_table.find_all('tr')
                rank_mapping = {
                    '1등': ('first_winners', 'first_prize'),
                    '2등': ('second_winners', 'second_prize'),
                    '3등': ('third_winners', 'third_prize'),
                    '4등': ('fourth_winners', 'fourth_prize'),
                    '5등': ('fifth_winners', 'fifth_prize')
                }

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 4:
                        rank_text = cells[0].get_text(strip=True)

                        for rank_key, (winners_key, prize_key) in rank_mapping.items():
                            if rank_key in rank_text:
                                # 당첨자 수 파싱 (cells[2]: 당첨자 수)
                                winners_text = cells[2].get_text(strip=True) if len(cells) > 2 else '0'
                                winners_text = re.sub(r'[^\d]', '', winners_text)
                                statistics[winners_key] = int(winners_text) if winners_text else 0

                                # 1게임당 당첨금액 파싱 (cells[3]: 1게임당 당첨금액)
                                prize_text = cells[3].get_text(strip=True) if len(cells) > 3 else '0'
                                prize_text = re.sub(r'[^\d]', '', prize_text)
                                statistics[prize_key] = int(prize_text) if prize_text else 0
                                break

            # 총 판매액 파싱 (별도 섹션에서)
            sales_section = soup.find(string=re.compile(r'총\s*판매금액|총\s*판매액'))
            if sales_section:
                parent = sales_section.find_parent()
                if parent:
                    sales_text = parent.get_text()
                    sales_match = re.search(r'([\d,]+)\s*원', sales_text)
                    if sales_match:
                        sales_value = sales_match.group(1).replace(',', '')
                        statistics['total_sales'] = int(sales_value)

            # 유효한 데이터가 있는지 확인 (최소한 1등 데이터가 있어야 함)
            if statistics['first_winners'] > 0 or statistics['first_prize'] > 0:
                return statistics

            return None

        except Exception as e:
            logging.error(f"통계 파싱 중 에러 발생: {e}")
            return None

    def fetch_missing_statistics(self, max_rounds: int = 100) -> int:
        """누락된 회차의 통계 데이터만 수집

        기존 당첨번호는 있지만 통계가 누락된 회차를 찾아서
        해당 회차의 통계만 수집합니다.

        Args:
            max_rounds: 최대 수집할 회차 수 (기본값: 100)

        Returns:
            int: 수집 성공한 회차 수
        """
        if not self.lotto_numbers_db:
            logging.warning("LottoNumbersDB가 설정되지 않아 통계 수집을 건너뜁니다.")
            return 0

        try:
            missing_rounds = self.lotto_numbers_db.get_missing_statistics_rounds()
            if not missing_rounds:
                logging.info("모든 회차의 통계가 이미 저장되어 있습니다.")
                return 0

            # 최대 수집 회차 수 제한
            rounds_to_fetch = missing_rounds[:max_rounds]
            success_count = 0

            logging.info(f"통계 누락 회차 {len(rounds_to_fetch)}개 수집 시작...")

            import threading as _threading
            _tqdm_disable = _threading.current_thread() is not _threading.main_thread()
            for round_num in tqdm(rounds_to_fetch, desc="통계 수집", unit="회차", file=sys.stdout, disable=_tqdm_disable):
                try:
                    params = {'drwNo': round_num}
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    response = requests.get(self.base_url, params=params, headers=headers)

                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        statistics = self.parse_statistics(soup)

                        if statistics:
                            if self.lotto_numbers_db.insert_statistics(round_num, statistics):
                                success_count += 1

                    time.sleep(0.3)  # 서버 부하 방지를 위한 딜레이

                except Exception as e:
                    logging.debug(f"회차 {round_num} 통계 수집 실패: {e}")
                    continue

            logging.info(f"통계 수집 완료: {success_count}/{len(rounds_to_fetch)} 회차 성공")
            return success_count

        except Exception as e:
            logging.error(f"누락 통계 수집 중 오류: {e}")
            return 0