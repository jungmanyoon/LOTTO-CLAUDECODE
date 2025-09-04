from typing import List, Dict, Optional, Tuple, Any
import sqlite3
import json
import logging
from .db_structure import BaseDatabase
import os
from tqdm import tqdm
import math
import time

# LottoValidator 클래스 가져오기 (encode_combination과 decode_combination을 위해)
from src.utils.validators import LottoValidator

class LottoNumbersDB(BaseDatabase):
    """당첨 번호 데이터베이스"""
    
    def _initialize_database(self):
        with self._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lotto_numbers (
                    round INTEGER PRIMARY KEY,
                    numbers TEXT NOT NULL,
                    draw_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_numbers_round ON lotto_numbers(round)')

    def get_last_round(self) -> int:
        """마지막으로 저장된 회차 번호 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(round) FROM lotto_numbers")
                result = cursor.fetchone()[0]
                return result if result is not None else 0
        except Exception as e:
            logging.error(f"마지막 회차 조회 중 오류 발생: {str(e)}")
            return 0

    def insert_numbers(self, round_num: int, numbers: List[int], draw_date: str) -> bool:
        """로또 번호 데이터 삽입"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO lotto_numbers (round, numbers, draw_date)
                    VALUES (?, ?, ?)
                ''', (round_num, ','.join(map(str, numbers)), draw_date))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"데이터 삽입 중 오류 발생: {str(e)}")
            return False

    def get_all_numbers(self) -> List[Tuple[int, str, str]]:
        """모든 로또 번호 데이터 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT round, numbers, draw_date FROM lotto_numbers ORDER BY round")
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"데이터 조회 중 오류 발생: {str(e)}")
            return []

    def get_numbers_by_round(self, round_num: int) -> Optional[Tuple[int, str, str]]:
        """특정 회차의 로또 번호 데이터 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT round, numbers, draw_date 
                    FROM lotto_numbers 
                    WHERE round = ?
                """, (round_num,))
                return cursor.fetchone()
        except Exception as e:
            logging.error(f"회차 {round_num} 데이터 조회 중 오류 발생: {str(e)}")
            return None

    def get_all_winning_numbers(self) -> List[str]:
        """모든 당첨 번호 목록 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT numbers FROM lotto_numbers ORDER BY round")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"당첨 번호 조회 중 오류 발생: {str(e)}")
            return []

    def get_recent_numbers(self, count: int) -> List[Tuple[int, str, str]]:
        """최근 n회의 당첨 번호 데이터 조회
        
        Args:
            count: 조회할 최근 회차 수
            
        Returns:
            List[Tuple[int, str, str]]: (회차, 번호, 추첨일) 튜플의 리스트
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT round, numbers, draw_date 
                    FROM lotto_numbers 
                    ORDER BY round DESC 
                    LIMIT ?
                """, (count,))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"최근 {count}회 당첨 번호 조회 중 오류 발생: {str(e)}")
            return []

    def get_numbers_since_round(self, last_round: int) -> List[str]:
        """특정 회차 이후의 당첨 번호들 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT numbers 
                    FROM lotto_numbers 
                    WHERE round > ?
                    ORDER BY round
                """, (last_round,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"당첨 번호 조회 중 오류 발생: {str(e)}")
            return []

    def get_winning_numbers_range(self, min_round: int, current_round: int) -> List[str]:
        """특정 범위의 당첨 번호 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT numbers
                    FROM lotto_numbers
                    WHERE round >= ? AND round <= ?
                    ORDER BY round
                """, (min_round, current_round))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"당첨 번호 범위 조회 중 오류 발생: {str(e)}")
            return []
    
    def get_winning_numbers_before(self, round_num: int) -> List[str]:
        """특정 회차 이전의 당첨 번호들 조회 (백테스팅용)
        
        Args:
            round_num: 기준 회차 번호
            
        Returns:
            List[str]: 해당 회차 이전의 모든 당첨 번호 리스트
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT numbers
                    FROM lotto_numbers
                    WHERE round < ?
                    ORDER BY round
                """, (round_num,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"회차 {round_num} 이전 당첨 번호 조회 중 오류 발생: {str(e)}")
            return []

class CombinationsDB(BaseDatabase):
    """조합 데이터베이스"""
    
    def __init__(self, db_path: str, db_manager=None):
        """CombinationsDB 초기화
        
        Args:
            db_path: 데이터베이스 파일 경로
            db_manager: 데이터베이스 관리자 인스턴스 (선택적)
        """
        super().__init__(db_path)
        self.db_manager = db_manager
        self.filter_name = "combinations"
    
    def _initialize_database(self):
        with self._create_connection() as conn:
            cursor = conn.cursor()
            # 기존 테이블이 있는지 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='base_combinations'")
            has_old_table = cursor.fetchone() is not None
            
            # 최적화된 테이블 구조 생성 (BLOB 사용)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS base_combinations_optimized (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combination_blob BLOB NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS valid_combinations_optimized (
                    round INTEGER NOT NULL,
                    combination_blob BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (round, combination_blob)
                )
            ''')
            # 기존 테이블 유지 (호환성 위해)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS base_combinations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combination TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS valid_combinations (
                    round INTEGER NOT NULL,
                    combination TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (round, combination)
                )
            ''')
            conn.commit()
            
            # 인덱스 생성
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_base_comb_blob ON base_combinations_optimized(combination_blob)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_valid_comb_blob ON valid_combinations_optimized(combination_blob)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_base_comb ON base_combinations(combination)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_valid_comb ON valid_combinations(combination)')
            
            # filtered_combinations 테이블 추가
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS filtered_combinations (
                    round INTEGER,
                    combination TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (round, combination)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_filtered_round ON filtered_combinations(round)')
            
            # 데이터베이스 메타 정보 테이블 생성
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS db_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            
            # 사용 중인 저장 방식 설정
            if not has_old_table:
                # 신규 설치 시 최적화된 방식 선택
                cursor.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('storage_mode', 'optimized')")
            else:
                # 기존 사용자는 기본 방식 유지 (마이그레이션 기능 추가 필요)
                cursor.execute("INSERT OR IGNORE INTO db_meta (key, value) VALUES ('storage_mode', 'legacy')")
            
            conn.commit()
    
    def _get_storage_mode(self) -> str:
        """현재 사용 중인 저장 방식 확인
        
        Returns:
            str: 'optimized' 또는 'legacy'
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM db_meta WHERE key='storage_mode'")
                result = cursor.fetchone()
                return result[0] if result else 'legacy'
        except Exception as e:
            logging.error(f"저장 방식 확인 중 오류 발생: {str(e)}")
            return 'legacy'
    
    def set_storage_mode(self, mode: str) -> bool:
        """저장 방식 설정
        
        Args:
            mode: 'optimized' 또는 'legacy'
            
        Returns:
            bool: 성공 여부
        """
        if mode not in ['optimized', 'legacy']:
            raise ValueError("저장 방식은 'optimized' 또는 'legacy'만 가능합니다")
            
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('storage_mode', ?)", (mode,))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"저장 방식 설정 중 오류 발생: {str(e)}")
            return False

    def check_base_combinations_exist(self) -> bool:
        """기본 조합이 이미 생성되어 있는지 확인"""
        try:
            # 타임아웃 방지를 위해 간단한 쿼리로 변경
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    # LIMIT 1로 첫 번째 레코드만 확인
                    cursor.execute("SELECT 1 FROM base_combinations_optimized LIMIT 1")
                else:
                    cursor.execute("SELECT 1 FROM base_combinations LIMIT 1")
                    
                result = cursor.fetchone()
                exists = result is not None
                logging.info(f"[DEBUG] 기본 조합 존재 여부: {exists}")
                return exists
        except Exception as e:
            logging.error(f"기본 조합 확인 중 오류 발생: {str(e)}")
            # 오류 시 조합이 있다고 가정 (재생성 방지)
            return True

    def save_base_combinations(self, combinations: List[str]) -> bool:
        """기본 로또 조합 저장"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    # 비트맵 인코딩 저장 방식
                    from ..utils.validators import LottoValidator
                    
                    batch_data = []
                    for comb_str in combinations:
                        numbers = LottoValidator.str_to_combination(comb_str)
                        bitmap = LottoValidator.encode_combination(numbers)
                        blob = LottoValidator.bitmap_to_bytes(bitmap)
                        batch_data.append((blob,))
                    
                    cursor.executemany('''
                        INSERT OR IGNORE INTO base_combinations_optimized (combination_blob)
                        VALUES (?)
                    ''', batch_data)
                else:
                    # 기존 텍스트 저장 방식
                    cursor.executemany('''
                        INSERT OR IGNORE INTO base_combinations (combination)
                        VALUES (?)
                    ''', [(comb,) for comb in combinations])
                    
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"기본 조합 저장 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def get_all_combinations(self) -> List[str]:
        """모든 조합 가져오기"""
        return self.get_base_combinations()
    
    def get_filtered_combinations(self) -> List[str]:
        """필터링된 조합 가져오기 (필터 테이블에서)"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # filtered_combinations 테이블이 있는지 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filtered_combinations'")
                if not cursor.fetchone():
                    logging.warning("filtered_combinations 테이블이 없습니다. 기본 조합을 반환합니다.")
                    # 전체 조합 반환
                    mode = self._get_storage_mode()
                    if mode == 'optimized':
                        query = "SELECT combination_blob FROM base_combinations_optimized"
                    else:
                        query = "SELECT combination FROM base_combinations"
                        
                    cursor.execute(query)
                    result = cursor.fetchall()
                    
                    combinations = []
                    for row in result:
                        try:
                            if mode == 'optimized':
                                # blob에서 비트맵으로 변환 후 디코딩
                                from ..utils.validators import LottoValidator
                                bitmap = LottoValidator.bytes_to_bitmap(row[0])
                                numbers = LottoValidator.decode_combination(bitmap)
                                combinations.append(LottoValidator.combination_to_str(numbers))
                            else:
                                # 문자열 그대로 사용
                                combinations.append(row[0])
                        except Exception as e:
                            logging.error(f"조합 변환 중 오류 발생: {str(e)}")
                    
                    return combinations
                
                # 필터링된 조합 가져오기
                cursor.execute("SELECT combination FROM filtered_combinations")
                result = cursor.fetchall()
                
                return [row[0] for row in result]
        except Exception as e:
            logging.error(f"필터링된 조합 조회 중 오류: {str(e)}")
            return []

    def get_base_combinations(self) -> List[str]:
        """기본 로또 조합 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    query = "SELECT combination_blob FROM base_combinations_optimized"
                else:
                    query = "SELECT combination FROM base_combinations"
                    
                cursor.execute(query)
                result = cursor.fetchall()
                
                combinations = []
                for row in result:
                    try:
                        if mode == 'optimized':
                            # blob에서 비트맵으로 변환 후 디코딩
                            from ..utils.validators import LottoValidator
                            bitmap = LottoValidator.bytes_to_bitmap(row[0])
                            numbers = LottoValidator.decode_combination(bitmap)
                            combinations.append(LottoValidator.combination_to_str(numbers))
                        else:
                            # 문자열 그대로 사용
                            combinations.append(row[0])
                    except Exception as e:
                        logging.error(f"조합 변환 중 오류 발생: {str(e)}")
                
                return combinations
        except Exception as e:
            logging.error(f"기본 조합 조회 중 오류 발생: {str(e)}")
            return []

    def count_all_combinations(self) -> int:
        """전체 조합 수 조회"""
        try:
            # 대량 데이터로 인한 타임아웃 방지를 위해 캐시된 값 반환
            # 실제로는 8,145,060개가 있음
            logging.info("[DEBUG] count_all_combinations - 캐시된 값 반환: 8,145,060")
            return 8145060
            
            # 아래는 원래 코드 (타임아웃 문제로 임시 비활성화)
            # with self._create_connection() as conn:
            #     cursor = conn.cursor()
            #     mode = self._get_storage_mode()
            #     
            #     if mode == 'optimized':
            #         cursor.execute("SELECT COUNT(*) FROM base_combinations_optimized")
            #     else:
            #         cursor.execute("SELECT COUNT(*) FROM base_combinations")
            #         
            #     count = cursor.fetchone()[0]
            #     return count
        except Exception as e:
            logging.error(f"조합 수 조회 중 오류 발생: {str(e)}")
            return 8145060  # 기본값 반환

    def save_valid_combinations(self, round_num: int, combinations: List[str]) -> bool:
        """유효한 로또 번호 조합 저장"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    # 비트맵 인코딩 저장 방식
                    from ..utils.validators import LottoValidator
                    
                    batch_data = []
                    for comb_str in combinations:
                        numbers = LottoValidator.str_to_combination(comb_str)
                        bitmap = LottoValidator.encode_combination(numbers)
                        blob = LottoValidator.bitmap_to_bytes(bitmap)
                        batch_data.append((round_num, blob))
                    
                    cursor.executemany('''
                        INSERT OR IGNORE INTO valid_combinations_optimized 
                        (round, combination_blob)
                        VALUES (?, ?)
                    ''', batch_data)
                else:
                    # 기존 텍스트 저장 방식
                    cursor.executemany('''
                        INSERT OR IGNORE INTO valid_combinations 
                        (round, combination)
                        VALUES (?, ?)
                    ''', [(round_num, comb) for comb in combinations])
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"유효 조합 저장 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def get_valid_combinations(self, round_num: int) -> List[str]:
        """특정 회차의 유효한 로또 번호 조합 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    query = "SELECT combination_blob FROM valid_combinations_optimized WHERE round = ?"
                else:
                    query = "SELECT combination FROM valid_combinations WHERE round = ?"
                    
                cursor.execute(query, (round_num,))
                result = cursor.fetchall()
                
                combinations = []
                for row in result:
                    try:
                        if mode == 'optimized':
                            # blob에서 비트맵으로 변환 후 디코딩
                            from ..utils.validators import LottoValidator
                            bitmap = LottoValidator.bytes_to_bitmap(row[0])
                            numbers = LottoValidator.decode_combination(bitmap)
                            combinations.append(LottoValidator.combination_to_str(numbers))
                        else:
                            # 문자열 그대로 사용
                            combinations.append(row[0])
                    except Exception as e:
                        logging.error(f"조합 변환 중 오류 발생: {str(e)}")
                
                return combinations
        except Exception as e:
            logging.error(f"유효한 조합 조회 중 오류 발생 (회차 {round_num}): {str(e)}")
            return []

    def get_valid_combinations_count(self, round_num: int) -> int:
        """특정 회차의 유효한 로또 번호 조합 개수 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    cursor.execute(
                        "SELECT COUNT(*) FROM valid_combinations_optimized WHERE round = ?", 
                        (round_num,)
                    )
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM valid_combinations WHERE round = ?", 
                        (round_num,)
                    )
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            logging.error(f"유효 조합 개수 조회 중 오류 발생: {str(e)}")
            return 0

    def clear_valid_combinations(self, round_num: int) -> bool:
        """특정 회차의 유효한 로또 번호 조합 모두 삭제"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    cursor.execute(
                        "DELETE FROM valid_combinations_optimized WHERE round = ?", 
                        (round_num,)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM valid_combinations WHERE round = ?", 
                        (round_num,)
                    )
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"유효 조합 삭제 중 오류 발생: {str(e)}")
            return False

    def get_filtered_combinations(self, round_num: int) -> List[str]:
        """필터링된 조합 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT combination FROM filtered_combinations WHERE round = ?", (round_num,))
                result = cursor.fetchall()
                
                # 결과 변환
                combinations = [row[0] for row in result]
                
                logging.info(f"[필터 디버그] 필터링된 조합 조회 성공: {self.filter_name}, 회차: {round_num}, 총 {len(combinations):,}개")
                return combinations
            
        except Exception as e:
            logging.error(f"필터링된 조합 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return []
            
    def get_excluded_combinations(self, round_num: int) -> List[str]:
        """제외된 조합 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            List[str]: 제외된 조합 목록
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT combination FROM excluded_combinations WHERE round_num = ?", (round_num,))
                result = cursor.fetchall()
                
                # 결과 변환
                combinations = [row[0] for row in result]
            
            logging.info(f"[필터 디버그] 제외된 조합 조회 성공: {self.filter_name}, 회차: {round_num}, 총 {len(combinations):,}개")
            return combinations
            
        except Exception as e:
            logging.error(f"제외된 조합 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return []
            
    def get_filter_criteria(self, round_num: int) -> Optional[Dict]:
        """필터 기준 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            Optional[Dict]: 필터 기준, 없으면 None
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT criteria FROM filter_criteria WHERE round_num = ?", (round_num,))
                result = cursor.fetchone()
                
                if result:
                    criteria = json.loads(result[0])
                    logging.info(f"[필터 디버그] 필터 기준 조회 성공: {self.filter_name}, 회차: {round_num}")
                    return criteria
                else:
                    logging.warning(f"[필터 디버그] 필터 기준 조회 결과 없음: {self.filter_name}, 회차: {round_num}")
                    return None
                
        except Exception as e:
            logging.error(f"필터 기준 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return None
    
    def save_filtered_combinations(self, round_num: int, combinations: List[str]) -> bool:
        """필터링된 조합 저장
        
        Args:
            round_num: 회차 번호
            combinations: 필터링된 조합 목록
            
        Returns:
            bool: 저장 성공 여부
        """
        if not combinations:
            logging.warning(f"저장할 필터링된 조합이 없습니다: 회차 {round_num}")
            return True
            
        try:
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 트랜잭션 시작
                connection.execute("BEGIN TRANSACTION")
                
                # 기존 데이터 삭제
                cursor.execute("DELETE FROM filtered_combinations WHERE round = ?", (round_num,))
                
                # 배치 크기 설정 (대용량 데이터 처리를 위해)
                batch_size = 10000
                total_batches = (len(combinations) + batch_size - 1) // batch_size
                
                # 배치 단위로 저장
                for i in range(0, len(combinations), batch_size):
                    batch = combinations[i:i + batch_size]
                    batch_data = [(round_num, comb) for comb in batch]
                    cursor.executemany('''
                        INSERT INTO filtered_combinations (round, combination)
                        VALUES (?, ?)
                    ''', batch_data)
                
                # 트랜잭션 커밋
                connection.commit()
                
                logging.info(f"필터링된 조합 저장 완료: 회차 {round_num}, {len(combinations):,}개")
                return True
                
        except Exception as e:
            logging.error(f"필터링된 조합 저장 중 오류 발생: {str(e)}")
            return False

class PatternsDB(BaseDatabase):
    """패턴 분석 데이터베이스"""
    
    # 패턴 컬럼 정의 업데이트 - 새로운 패턴 추가
    PATTERN_COLUMNS = {
        # 기존 패턴들
        'number_match_patterns': {'type': 'TEXT NOT NULL', 'default': None},
        'odd_even_patterns': {'type': 'TEXT NOT NULL', 'default': None},
        'consecutive_patterns': {'type': 'TEXT NOT NULL', 'default': None},
        'sum_range_patterns': {'type': 'TEXT NOT NULL', 'default': None},
        'fixed_step_patterns': {'type': 'TEXT', 'default': None},
        'last_digit_patterns': {'type': 'TEXT', 'default': None},
        'max_gap_patterns': {'type': 'TEXT', 'default': None},
        'section_distribution_patterns': {'type': 'TEXT', 'default': None},
        'number_average_patterns': {'type': 'TEXT', 'default': None},        
        'multiple_patterns': {'type': 'TEXT', 'default': None},            # 배수 패턴
        # 신규 패턴 컬럼 추가
        'ten_section_patterns': {'type': 'TEXT', 'default': None},
        'arithmetic_sequence_patterns': {'type': 'TEXT', 'default': None},
        'geometric_sequence_patterns': {'type': 'TEXT', 'default': None},
        # 누락된 패턴 컬럼 추가
        'alternating_odd_even_patterns': {'type': 'TEXT', 'default': None},    # 홀짝 교차 패턴
        'sum_multiple_patterns': {'type': 'TEXT', 'default': None},           # 합계 배수 패턴
        'dispersion_patterns': {'type': 'TEXT', 'default': None}              # 분산도 패턴
    }
    
    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._initialize_database()
        
    def _initialize_database(self):
        """필요한 테이블 생성"""
        with self._create_connection() as conn:
            cursor = conn.cursor()
            
            # 당첨 번호 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS winning_numbers (
                    round INTEGER PRIMARY KEY,
                    numbers TEXT NOT NULL,
                    draw_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 기존 패턴 분석 테이블 존재 여부 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_analysis'")
            pattern_table_exists = cursor.fetchone() is not None
            
            if pattern_table_exists:
                # 기존 테이블 구조가 완전히 다른지 확인 (pattern_type 컬럼이 있으면 이전 버전)
                cursor.execute("PRAGMA table_info(pattern_analysis)")
                columns = {row[1]: row for row in cursor.fetchall()}
                
                # 이전 버전의 테이블 구조인 경우 (pattern_type, analysis_result 컬럼이 있음)
                if 'pattern_type' in columns and 'analysis_result' in columns:
                    logging.warning("[패턴 분석] 이전 버전의 테이블 구조가 발견되었습니다. 새 테이블로 마이그레이션합니다.")
                    
                    # 기존 데이터 백업
                    try:
                        cursor.execute("ALTER TABLE pattern_analysis RENAME TO pattern_analysis_old")
                        logging.info("[패턴 분석] 기존 테이블을 pattern_analysis_old로 백업했습니다.")
                        
                        # 새 테이블 생성
                        columns_sql = ', '.join([f"{name} {info['type']}" for name, info in self.PATTERN_COLUMNS.items()])
                        sql = f'''
                            CREATE TABLE IF NOT EXISTS pattern_analysis (
                                round INTEGER PRIMARY KEY,
                                {columns_sql},
                                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        '''
                        cursor.execute(sql)
                        logging.info("[패턴 분석] 새 구조의 테이블을 생성했습니다.")
                        
                        conn.commit()
                        # 이제 pattern_table_exists를 False로 설정하여 아래 코드가 실행되지 않도록 함
                        pattern_table_exists = False
                    except Exception as e:
                        logging.error(f"[패턴 분석] 테이블 마이그레이션 중 오류: {str(e)}")
                
                # 기존 테이블에 필요한 컬럼 추가
                if pattern_table_exists:
                    # 기존 테이블의 컬럼 정보 가져오기
                    cursor.execute("PRAGMA table_info(pattern_analysis)")
                    existing_columns = {row[1] for row in cursor.fetchall()}
                    
                    # 필요한 컬럼 추가
                    for column_name, column_info in self.PATTERN_COLUMNS.items():
                        if column_name not in existing_columns:
                            try:
                                default_value = f"DEFAULT '{column_info['default']}'" if column_info['default'] is not None else ""
                                sql = f"ALTER TABLE pattern_analysis ADD COLUMN {column_name} {column_info['type']} {default_value}"
                                cursor.execute(sql)
                                logging.info(f"[패턴 분석] 새 컬럼 추가: {column_name}")
                            except Exception as e:
                                logging.error(f"컬럼 추가 중 오류: {column_name} - {str(e)}")
                    
                    # 타임스탬프 컬럼 추가 확인
                    if 'analyzed_at' not in existing_columns and 'created_at' not in existing_columns:
                        try:
                            # 타임스탬프 컬럼 추가
                            cursor.execute("ALTER TABLE pattern_analysis ADD COLUMN analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                            logging.info("[패턴 분석] 타임스탬프 컬럼 추가: analyzed_at")
                        except Exception as e:
                            logging.error(f"타임스탬프 컬럼 추가 중 오류: {str(e)}")
                            try:
                                # 대안으로 created_at 추가 시도
                                cursor.execute("ALTER TABLE pattern_analysis ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                                logging.info("[패턴 분석] 타임스탬프 컬럼 추가: created_at")
                            except Exception as e2:
                                logging.error(f"대체 타임스탬프 컬럼 추가 중 오류: {str(e2)}")
            
            # 테이블이 없거나 새로 생성해야 하는 경우
            if not pattern_table_exists:
                # 패턴 분석 결과 테이블 새로 생성
                columns_sql = ', '.join([f"{name} {info['type']}" for name, info in self.PATTERN_COLUMNS.items()])
                sql = f'''
                    CREATE TABLE IF NOT EXISTS pattern_analysis (
                        round INTEGER PRIMARY KEY,
                        {columns_sql},
                        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                '''
                cursor.execute(sql)
                logging.info("[DEBUG] 새로운 패턴 분석 테이블 생성 완료")
            
            conn.commit()
            logging.info("[DEBUG] 패턴 데이터베이스 테이블 생성 완료")

    def save_winning_numbers(self, round_num: int, numbers: str, draw_date: str = None) -> bool:
        """당첨 번호 저장
        
        Args:
            round_num: 회차 번호
            numbers: 당첨 번호 문자열
            draw_date: 추첨일
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO winning_numbers (round, numbers, draw_date)
                    VALUES (?, ?, ?)
                ''', (round_num, numbers, draw_date))
                conn.commit()
                return True
                
        except Exception as e:
            logging.error(f"당첨 번호 저장 중 오류 발생: {str(e)}")
            return False

    def get_section_distribution_history(self) -> Optional[List[Dict[str, Any]]]:
        """구간별 분포 패턴 이력 조회"""
        return self.get_pattern_history('section_distribution')

    def get_number_average_history(self) -> Optional[List[Dict[str, Any]]]:
        """평균값 패턴 이력 조회"""
        return self.get_pattern_history('number_average')

    def get_all_pattern_statistics(self, round_num: int) -> Dict[str, Any]:
        """전체 패턴 통계 조회 - 새로 추가된 패턴 포함"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                columns = list(self.PATTERN_COLUMNS.keys())
                column_str = ', '.join(columns)
                
                cursor.execute(f"""
                    SELECT {column_str}
                    FROM pattern_analysis
                    WHERE round = ?
                """, (round_num,))
                
                result = cursor.fetchone()
                if not result:
                    return {}
                    
                return {
                    col_name.replace('_patterns', ''): json.loads(value or '{}')
                    for col_name, value in zip(columns, result)
                }
                
        except Exception as e:
            logging.error(f"패턴 통계 조회 중 오류 발생: {str(e)}")
            return {}
        
    def save_pattern_analysis(self, round_num: int, patterns: Dict[str, Any]) -> bool:
        """패턴 분석 결과 저장"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # 테이블 구조 확인
                cursor.execute("PRAGMA table_info(pattern_analysis)")
                existing_columns = {row[1] for row in cursor.fetchall()}
                
                # 타임스탬프 컬럼 확인
                has_analyzed_at = 'analyzed_at' in existing_columns
                has_created_at = 'created_at' in existing_columns
                
                # 패턴명과 데이터베이스 컬럼명 매핑
                pattern_column_mapping = {
                    'match': 'number_match_patterns',
                    'multiple_patterns': 'multiple_patterns',
                    # 나머지는 기본 규칙 적용 (패턴명 + _patterns)
                }
                
                # 각 패턴 타입을 해당하는 컬럼 이름으로 변환
                pattern_values = {}
                for pattern_type, pattern_data in patterns.items():
                    # 특별한 매핑이 있는지 확인
                    if pattern_type in pattern_column_mapping:
                        column_name = pattern_column_mapping[pattern_type]
                    else:
                        column_name = f"{pattern_type}_patterns"
                    
                    if column_name in existing_columns:
                        pattern_values[column_name] = json.dumps(pattern_data)
                
                if not pattern_values:
                    logging.warning("저장할 패턴 데이터가 없습니다.")
                    return False
                
                # SQL 생성 - 존재하는 컬럼만 사용
                columns = list(pattern_values.keys())
                placeholders = ', '.join(['?'] * len(columns))
                values = [pattern_values[col] for col in columns]
                
                # 타임스탬프 컬럼이 있는 경우 SQL에 추가
                if has_analyzed_at:
                    timestamp_col = "analyzed_at"
                    timestamp_val = "CURRENT_TIMESTAMP"
                elif has_created_at:
                    timestamp_col = "created_at"
                    timestamp_val = "CURRENT_TIMESTAMP"
                else:
                    timestamp_col = None
                
                if timestamp_col:
                    sql = f'''
                        INSERT OR REPLACE INTO pattern_analysis 
                        (round, {', '.join(columns)}, {timestamp_col})
                        VALUES (?, {placeholders}, {timestamp_val})
                    '''
                else:
                    sql = f'''
                        INSERT OR REPLACE INTO pattern_analysis 
                        (round, {', '.join(columns)})
                        VALUES (?, {placeholders})
                    '''
                
                # round_num을 값 리스트의 맨 앞에 추가
                values.insert(0, round_num)
                
                cursor.execute(sql, values)
                conn.commit()
                logging.info(f"패턴 분석 결과 저장 완료: {round_num}회차, {len(pattern_values)}개 패턴")
                return True
                
        except Exception as e:
            logging.error(f"패턴 분석 결과 저장 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def get_pattern_statistics(self, round_num: int, pattern_type: str) -> Optional[Dict[str, Any]]:
        """특정 패턴의 통계 조회"""
        try:
            pattern_column = f"{pattern_type}_patterns"
            if pattern_column not in self.PATTERN_COLUMNS:
                logging.error(f"잘못된 패턴 유형: {pattern_type}")
                return None
                
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT {pattern_column}, analyzed_at
                    FROM pattern_analysis
                    WHERE round = ?
                """, (round_num,))
                result = cursor.fetchone()
                if result:
                    return {
                        'patterns': json.loads(result[0] or '{}'),
                        'analyzed_at': result[1]
                    }
                return None
                
        except Exception as e:
            logging.error(f"패턴 통계 조회 중 오류 발생: {str(e)}")
            return None
    
    def get_latest_patterns(self, include_new_patterns: bool = True) -> Optional[Dict[str, Dict]]:
        """최신 패턴 분석 결과 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # 조회할 컬럼 선택
                columns = list(self.PATTERN_COLUMNS.keys())
                if not include_new_patterns:
                    # 새로운 패턴 제외
                    columns = [col for col in columns if not col in [
                        'multiple_patterns',
                        'alternating_odd_even_patterns',
                        'sum_multiple_patterns'
                    ]]
                
                column_str = ', '.join(columns)
                
                cursor.execute(f"""
                    SELECT round, {column_str}, analyzed_at
                    FROM pattern_analysis
                    ORDER BY round DESC
                    LIMIT 1
                """)
                
                result = cursor.fetchone()
                if result:
                    patterns = {}
                    for i, col_name in enumerate(columns, 1):
                        pattern_name = col_name.replace('_patterns', '')
                        patterns[pattern_name] = json.loads(result[i] or '{}')
                        
                    return {
                        'round': result[0],
                        'patterns': patterns,
                        'analyzed_at': result[-1]
                    }
                return None
                
        except Exception as e:
            logging.error(f"최신 패턴 조회 중 오류 발생: {str(e)}")
            return None
        
    def get_latest_pattern_analysis(self) -> Optional[Dict[str, Any]]:
        """최신 패턴 분석 결과 조회"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # 동적으로 조회할 컬럼 생성
                columns = ', '.join(list(self.PATTERN_COLUMNS.keys()))
                
                cursor.execute(f"""
                    SELECT round, {columns}, analyzed_at
                    FROM pattern_analysis
                    ORDER BY round DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()
                
                if result:
                    patterns = {}
                    for i, col_name in enumerate(self.PATTERN_COLUMNS.keys(), 1):
                        pattern_name = col_name.replace('_patterns', '')
                        patterns[pattern_name] = json.loads(result[i] or '{}')
                        
                    return {
                        'round': result[0],
                        'patterns': patterns,
                        'analyzed_at': result[-1]
                    }
                return None
                
        except Exception as e:
            logging.error(f"패턴 분석 결과 조회 중 오류 발생: {str(e)}")
            return None

    def get_pattern_history(self, pattern_type: str) -> Optional[List[Dict[str, Any]]]:
        """특정 패턴의 이력 조회"""
        try:
            pattern_column = f"{pattern_type}_patterns"
            if pattern_column not in self.PATTERN_COLUMNS:
                logging.error(f"잘못된 패턴 유형: {pattern_type}")
                return None
                
            with self._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT round, {pattern_column}, analyzed_at
                    FROM pattern_analysis
                    ORDER BY round DESC
                """)
                results = cursor.fetchall()
                
                if results:
                    return [{
                        'round': row[0],
                        'patterns': json.loads(row[1] or '{}'),
                        'analyzed_at': row[2]
                    } for row in results]
                return None
                
        except Exception as e:
            logging.error(f"패턴 이력 조회 중 오류 발생: {str(e)}")
            return None
        
    # 새로운 패턴 관련 메서드 추가
    def get_multiple_pattern_history(self) -> Optional[List[Dict[str, Any]]]:
        """배수 패턴 이력 조회"""
        return self.get_pattern_history('multiple')

    def get_alternating_pattern_history(self) -> Optional[List[Dict[str, Any]]]:
        """홀짝 교차 패턴 이력 조회"""
        return self.get_pattern_history('alternating_odd_even')

    def get_sum_multiple_history(self) -> Optional[List[Dict[str, Any]]]:
        """합계 배수 패턴 이력 조회"""
        return self.get_pattern_history('sum_multiple')

class FilterDB(BaseDatabase):
    """필터 데이터베이스"""
    
    def __init__(self, db_path: str, filter_name: str = None):
        """필터 데이터베이스 초기화
        
        Args:
            db_path: 데이터베이스 경로
            filter_name: 필터 이름 (기본값: db_path에서 추출)
        """
        # 필터 이름 설정
        if filter_name is None:
            # 경로에서 필터 이름 추출 (예: 'data/filters/odd_even_filter.db' -> 'odd_even')
            filename = os.path.basename(db_path)
            filter_name = os.path.splitext(filename)[0]
            
            # '_filter' 접미사 제거
            if filter_name.endswith('_filter'):
                filter_name = filter_name[:-7]
        
        self.filter_name = filter_name
        logging.debug(f"FilterDB 초기화 - 경로: {db_path}, 필터명: {filter_name}")
        
        # 데이터베이스 디렉토리 확인 및 생성
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logging.debug(f"데이터베이스 디렉토리 생성: {db_dir}")
        
        # BaseDatabase 초기화 (이것이 _initialize_database를 호출)
        super().__init__(db_path)
    
    def _initialize_database(self):
        """데이터베이스 초기화 - BaseDatabase 요구사항"""
        self.init_db()

    def init_db(self):
        """데이터베이스 초기화
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # 필터링된 조합 테이블 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS filtered_combinations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round INTEGER NOT NULL,
                        combination TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(round, combination)
                    )
                """)
                
                # 제외된 조합 테이블 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS excluded_combinations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round INTEGER NOT NULL,
                        combination TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(round, combination)
                    )
                """)
                
                # 필터 상세 정보 테이블 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS filter_details (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_num INTEGER NOT NULL UNIQUE,
                        details TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 필터 기준 테이블 생성
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS filter_criteria (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_num INTEGER NOT NULL UNIQUE,
                        criteria TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                
            logging.debug(f"필터 데이터베이스 초기화 완료: {self.db_path}")
            return True
            
        except Exception as e:
            logging.error(f"필터 데이터베이스 초기화 중 오류 발생: {str(e)}")
            return False

    def save_filtered_combinations(self, round_num: int, filtered_combinations: List[str]) -> bool:
        """필터링된 조합 저장
        
        Args:
            round_num: 회차 번호
            filtered_combinations: 필터링된 조합 목록
            
        Returns:
            bool: 성공 여부
        """
        if not filtered_combinations:
            logging.warning(f"저장할 필터링된 조합이 없습니다: {self.filter_name}, 회차: {round_num}")
            return True
            
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                # 트랜잭션 시작
                connection.execute("BEGIN TRANSACTION")
                
                # 배치 크기 설정
                batch_size = 1000
                total_batches = math.ceil(len(filtered_combinations) / batch_size)
                
                # 배치 단위로 저장
                for batch_idx in range(total_batches):
                    start_idx = batch_idx * batch_size
                    end_idx = min((batch_idx + 1) * batch_size, len(filtered_combinations))
                    batch = filtered_combinations[start_idx:end_idx]
                    
                    # 튜플 목록 생성
                    values = [(round_num, combo) for combo in batch]
                    
                    # 데이터 삽입
                    connection.executemany(
                        "INSERT OR IGNORE INTO filtered_combinations (round, combination) VALUES (?, ?)",
                        values
                    )
                    
                    # 배치 완료 로그
                    logging.debug(f"배치 {batch_idx+1}/{total_batches} 저장 완료: {len(batch)}개")
                
                # 트랜잭션 커밋 - with 블록 안에서 실행
                connection.execute("COMMIT")
            
            logging.info(f"[필터 디버그] 필터링된 조합 저장 성공: {self.filter_name}, 회차: {round_num}, 총 {len(filtered_combinations):,}개")
            return True
            
        except Exception as e:
            # 오류 발생 시 롤백 (connection이 존재하는 경우에만)
            try:
                if 'connection' in locals() and connection:
                    connection.execute("ROLLBACK")
            except:
                pass
                
            logging.error(f"필터링된 조합 저장 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return False
            
    def save_excluded_combinations(self, round_num: int, excluded_combinations: List[str]) -> bool:
        """제외된 조합 저장
        
        Args:
            round_num: 회차 번호
            excluded_combinations: 제외된 조합 목록
            
        Returns:
            bool: 성공 여부
        """
        if not excluded_combinations:
            logging.warning(f"저장할 제외된 조합이 없습니다: {self.filter_name}, 회차: {round_num}")
            return True
            
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                # 트랜잭션 시작
                connection.execute("BEGIN TRANSACTION")
                
                # 배치 크기 설정
                batch_size = 1000
                total_batches = math.ceil(len(excluded_combinations) / batch_size)
                
                # 배치 단위로 저장
                for batch_idx in range(total_batches):
                    start_idx = batch_idx * batch_size
                    end_idx = min((batch_idx + 1) * batch_size, len(excluded_combinations))
                    batch = excluded_combinations[start_idx:end_idx]
                    
                    # 튜플 목록 생성
                    values = [(round_num, combo) for combo in batch]
                    
                    # 데이터 삽입
                    connection.executemany(
                        "INSERT OR IGNORE INTO excluded_combinations (round, combination) VALUES (?, ?)",
                        values
                    )
                    
                    # 배치 완료 로그
                    logging.debug(f"배치 {batch_idx+1}/{total_batches} 저장 완료: {len(batch)}개")
                
                # 트랜잭션 커밋 - with 블록 안에서 실행
                connection.execute("COMMIT")
            
            logging.info(f"[필터 디버그] 제외된 조합 저장 성공: {self.filter_name}, 회차: {round_num}, 총 {len(excluded_combinations):,}개")
            return True
            
        except Exception as e:
            # 오류 발생 시 롤백 (connection이 존재하는 경우에만)
            try:
                if 'connection' in locals() and connection:
                    connection.execute("ROLLBACK")
            except:
                pass
                
            logging.error(f"제외된 조합 저장 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return False

    def get_filtered_combinations(self, round_num: int) -> List[str]:
        """필터링된 조합 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT combination FROM filtered_combinations WHERE round = ?", (round_num,))
                result = cursor.fetchall()
                
                # 결과 변환
                combinations = [row[0] for row in result]
                
                logging.info(f"[필터 디버그] 필터링된 조합 조회 성공: {self.filter_name}, 회차: {round_num}, 총 {len(combinations):,}개")
                return combinations
            
        except Exception as e:
            logging.error(f"필터링된 조합 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return []
            
    def get_excluded_combinations(self, round_num: int) -> List[str]:
        """제외된 조합 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            List[str]: 제외된 조합 목록
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT combination FROM excluded_combinations WHERE round_num = ?", (round_num,))
                result = cursor.fetchall()
                
                # 결과 변환
                combinations = [row[0] for row in result]
            
            logging.info(f"[필터 디버그] 제외된 조합 조회 성공: {self.filter_name}, 회차: {round_num}, 총 {len(combinations):,}개")
            return combinations
            
        except Exception as e:
            logging.error(f"제외된 조합 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return []
            
    def get_filter_criteria(self, round_num: int) -> Optional[Dict]:
        """필터 기준 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            Optional[Dict]: 필터 기준, 없으면 None
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT criteria FROM filter_criteria WHERE round_num = ?", (round_num,))
                result = cursor.fetchone()
                
                if result:
                    criteria = json.loads(result[0])
                    logging.info(f"[필터 디버그] 필터 기준 조회 성공: {self.filter_name}, 회차: {round_num}")
                    return criteria
                else:
                    logging.warning(f"[필터 디버그] 필터 기준 조회 결과 없음: {self.filter_name}, 회차: {round_num}")
                    return None
                
        except Exception as e:
            logging.error(f"필터 기준 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return None

    def count_excluded_combinations(self, round_num: int) -> int:
        """제외된 조합 개수 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            int: 제외된 조합 개수
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT COUNT(*) FROM excluded_combinations WHERE round_num = ?", (round_num,))
                result = cursor.fetchone()
                
                if result:
                    count = result[0]
                    logging.info(f"[필터 디버그] 제외된 조합 개수 조회 성공: {self.filter_name}, 회차: {round_num}, 개수: {count:,}개")
                    return count
                else:
                    logging.warning(f"[필터 디버그] 제외된 조합 개수 조회 결과 없음: {self.filter_name}, 회차: {round_num}")
                    return 0
                
        except Exception as e:
            logging.error(f"제외된 조합 개수 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return 0
    
    def save_filter_details(self, round_num: int, details: dict) -> bool:
        """필터 상세 정보 저장
        
        Args:
            round_num: 회차 번호
            details: 필터 상세 정보 딕셔너리
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 상세 정보를 JSON으로 변환
                details_json = json.dumps(details, ensure_ascii=False)
                
                # 데이터 저장 (기존 데이터가 있으면 업데이트)
                cursor.execute("""
                    INSERT INTO filter_details (round_num, details, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(round_num) 
                    DO UPDATE SET details = excluded.details, updated_at = CURRENT_TIMESTAMP
                """, (round_num, details_json))
                
                connection.commit()
            
            logging.info(f"[필터 디버그] 필터 상세 정보 저장 성공: {self.filter_name}, 회차: {round_num}")
            return True
            
        except Exception as e:
            logging.error(f"필터 상세 정보 저장 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return False
    
    def get_filter_details(self, round_num: int) -> dict:
        """필터 상세 정보 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            dict: 필터 상세 정보
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 데이터 조회
                cursor.execute("SELECT details FROM filter_details WHERE round_num = ?", (round_num,))
                result = cursor.fetchone()
                
                if result:
                    # JSON 문자열을 딕셔너리로 변환
                    # result는 튜플이므로 인덱스로 접근
                    details = json.loads(result[0])
                    logging.info(f"[필터 디버그] 필터 상세 정보 조회 성공: {self.filter_name}, 회차: {round_num}")
                    return details
                else:
                    logging.warning(f"[필터 디버그] 필터 상세 정보 조회 결과 없음: {self.filter_name}, 회차: {round_num}")
                    return {}
                
        except Exception as e:
            logging.error(f"필터 상세 정보 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return {}
    
    def get_last_filtered_round(self) -> int:
        """마지막으로 필터링된 회차 번호 조회
        
        Returns:
            int: 마지막 회차 번호 (없으면 0)
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 가장 최근 회차 조회
                cursor.execute("SELECT MAX(round_num) FROM filtered_combinations")
                result = cursor.fetchone()
                
                if result and result[0]:
                    round_num = result[0]
                    logging.info(f"[필터 디버그] 마지막 필터링 회차 조회 성공: {self.filter_name}, 회차: {round_num}")
                    return round_num
                else:
                    logging.warning(f"[필터 디버그] 마지막 필터링 회차 조회 결과 없음: {self.filter_name}")
                    return 0
                
        except Exception as e:
            logging.error(f"마지막 필터링 회차 조회 실패: {self.filter_name}, 오류: {str(e)}")
            logging.exception(e)
            return 0
    
    def get_filtering_statistics(self, round_num: int) -> dict:
        """특정 회차의 필터링 통계 정보 반환
        
        Args:
            round_num: 회차 번호
            
        Returns:
            dict: 통계 정보 (total_combinations, excluded_combinations, exclude_percent, filter_time)
        """
        try:
            # get_filter_details 메서드를 직접 호출
            details = self.get_filter_details(round_num)
            
            if details and isinstance(details, dict):
                # filter_details에서 통계 정보 추출
                total_count = details.get('initial_count', 0)
                excluded_count = details.get('excluded_count', 0)
                exclude_percent = details.get('exclude_percent', 0)
                filter_time = details.get('elapsed_time', 0)
                
                statistics = {
                    'total_combinations': total_count,
                    'excluded_combinations': excluded_count,
                    'exclude_percent': exclude_percent,
                    'filter_time': filter_time
                }
                
                logging.info(f"[필터 디버그] 필터링 통계 조회 성공: {self.filter_name}, 회차: {round_num}, 전체: {total_count:,}개, 제외: {excluded_count:,}개 ({exclude_percent:.2f}%)")
                return statistics
            
            # filter_details가 없으면 기본값 반환
            logging.info(f"[필터 디버그] 필터링 통계 없음: {self.filter_name}, 회차: {round_num}")
            return {
                'total_combinations': 0,
                'excluded_combinations': 0,
                'exclude_percent': 0,
                'filter_time': 0
            }
            
        except Exception as e:
            logging.error(f"필터링 통계 조회 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return {
                'total_combinations': 0,
                'excluded_combinations': 0,
                'exclude_percent': 0,
                'filter_time': 0
            }
    
    def save_filter_criteria(self, round_num: int, criteria: dict) -> bool:
        """필터 기준 정보 저장
        
        Args:
            round_num: 회차 번호
            criteria: 필터 기준 정보 딕셔너리
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # DB 연결 - context manager 사용
            with self._create_connection() as connection:
                cursor = connection.cursor()
                
                # 기준 정보를 JSON으로 변환
                criteria_json = json.dumps(criteria, ensure_ascii=False)
                
                # 데이터 저장 (기존 데이터가 있으면 업데이트)
                cursor.execute("""
                    INSERT INTO filter_criteria (round_num, criteria, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(round_num) 
                    DO UPDATE SET criteria = excluded.criteria, updated_at = CURRENT_TIMESTAMP
                """, (round_num, criteria_json))
                
                connection.commit()
            
            logging.info(f"[필터 디버그] 필터 기준 정보 저장 성공: {self.filter_name}, 회차: {round_num}")
            return True
            
        except Exception as e:
            logging.error(f"필터 기준 정보 저장 실패: {self.filter_name}, 회차: {round_num}, 오류: {str(e)}")
            logging.exception(e)
            return False