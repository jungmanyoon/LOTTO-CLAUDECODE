import logging

class FilterDB:
    """필터 결과를 저장하고 관리하는 데이터베이스 클래스"""
    def __init__(self, db_path, filter_name, combination_manager=None):
        """
        생성자
        :param db_path: 데이터베이스 파일 경로
        :param filter_name: 필터 이름
        :param combination_manager: 조합 관리자 인스턴스
        """
        self.db_path = db_path
        self.filter_name = filter_name
        self.combination_manager = combination_manager
        self.conn = None
        self.initialized = False
        self.init_database()
        
    def get_filtering_statistics(self, round_num):
        """
        특정 회차의 필터링 통계 정보를 반환합니다.
        :param round_num: 회차 번호
        :return: 통계 정보 (딕셔너리 형태)
        """
        try:
            # 데이터베이스 연결 확인
            self._ensure_connection()
            
            # 회차 정보 확인
            if not round_num:
                # 회차 정보가 없으면 가장 최근 회차 사용
                cursor = self.conn.cursor()
                cursor.execute("SELECT MAX(round) FROM filter_results")
                result = cursor.fetchone()
                if result and result[0]:
                    round_num = result[0]
                else:
                    # 데이터가 없으면 기본값 반환
                    return {
                        'total_combinations': 0,
                        'excluded_combinations': 0,
                        'exclude_percent': 0,
                        'filter_time': 0
                    }
            
            # 통계 정보 조회
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT total_count, excluded_count, filter_time
                FROM filter_stats
                WHERE round = ? AND filter_name = ?
            """, (round_num, self.filter_name))
            
            result = cursor.fetchone()
            
            if result:
                total_count, excluded_count, filter_time = result
                
                # 제외 비율 계산 (0 ~ 100%)
                exclude_percent = 0
                if total_count > 0:
                    exclude_percent = (excluded_count / total_count) * 100
                
                return {
                    'total_combinations': total_count,
                    'excluded_combinations': excluded_count,
                    'exclude_percent': exclude_percent,
                    'filter_time': filter_time
                }
            else:
                # 통계 정보가 없으면 기본값 반환
                return {
                    'total_combinations': 0,
                    'excluded_combinations': 0,
                    'exclude_percent': 0,
                    'filter_time': 0
                }
                
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 통계 조회 오류: {str(e)}")
            # 오류 발생 시 기본값 반환
            return {
                'total_combinations': 0,
                'excluded_combinations': 0,
                'exclude_percent': 0,
                'filter_time': 0
            }
    
    def save_filter_details(self, round_num: int, details: dict) -> bool:
        """필터 상세 정보 저장
        
        Args:
            round_num: 회차 번호
            details: 필터 상세 정보 딕셔너리
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            
            # filter_details 테이블이 없으면 생성
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    filter_name TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round, filter_name)
                )
            """)
            
            # 상세 정보를 JSON으로 저장
            import json
            details_json = json.dumps(details, ensure_ascii=False)
            
            cursor.execute("""
                INSERT OR REPLACE INTO filter_details (round, filter_name, details)
                VALUES (?, ?, ?)
            """, (round_num, self.filter_name, details_json))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 상세 정보 저장 오류: {str(e)}")
            return False
    
    def get_filter_details(self, round_num: int) -> dict:
        """필터 상세 정보 조회
        
        Args:
            round_num: 회차 번호
            
        Returns:
            dict: 필터 상세 정보
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT details FROM filter_details
                WHERE round = ? AND filter_name = ?
            """, (round_num, self.filter_name))
            
            result = cursor.fetchone()
            
            if result:
                import json
                return json.loads(result[0])
            else:
                return {}
                
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 상세 정보 조회 오류: {str(e)}")
            return {}
    
    def save_filter_criteria(self, round_num: int, criteria: dict) -> bool:
        """필터 기준값 저장 (동적 필터 시스템용)
        
        Args:
            round_num: 회차 번호
            criteria: 필터 기준값 딕셔너리
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            
            # filter_criteria 테이블이 없으면 생성
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    filter_name TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round, filter_name)
                )
            """)
            
            # 기준값을 JSON으로 저장
            import json
            criteria_json = json.dumps(criteria, ensure_ascii=False)
            
            cursor.execute("""
                INSERT OR REPLACE INTO filter_criteria (round, filter_name, criteria, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (round_num, self.filter_name, criteria_json))
            
            self.conn.commit()
            logging.info(f"필터 기준 정보 저장 성공: {self.filter_name}, 회차: {round_num}")
            return True
            
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 기준값 저장 오류: {str(e)}")
            return False
    
    def get_filter_criteria(self, round_num: int = None) -> dict:
        """필터 기준값 조회 (동적 필터 시스템용)
        
        Args:
            round_num: 회차 번호 (None이면 최신값)
            
        Returns:
            dict: 필터 기준값
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            
            if round_num:
                # 특정 회차의 기준값 조회
                cursor.execute("""
                    SELECT criteria FROM filter_criteria
                    WHERE round = ? AND filter_name = ?
                """, (round_num, self.filter_name))
            else:
                # 최신 기준값 조회
                cursor.execute("""
                    SELECT criteria FROM filter_criteria
                    WHERE filter_name = ?
                    ORDER BY round DESC, updated_at DESC
                    LIMIT 1
                """, (self.filter_name,))
            
            result = cursor.fetchone()
            
            if result:
                import json
                return json.loads(result[0])
            else:
                return {}
                
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 기준값 조회 오류: {str(e)}")
            return {}
    
    def set_criteria(self, criteria: dict, round_num: int = None) -> bool:
        """필터 기준값 설정 (동적 필터 시스템용)
        
        Args:
            criteria: 필터 기준값 딕셔너리
            round_num: 회차 번호 (None이면 현재 회차)
            
        Returns:
            bool: 설정 성공 여부
        """
        try:
            # round_num이 없으면 최신 회차 + 1 사용
            if not round_num:
                self._ensure_connection()
                cursor = self.conn.cursor()
                cursor.execute("SELECT MAX(round) FROM filter_criteria WHERE filter_name = ?", (self.filter_name,))
                result = cursor.fetchone()
                round_num = (result[0] + 1) if result and result[0] else 1
            
            # 기준값 저장
            return self.save_filter_criteria(round_num, criteria)
            
        except Exception as e:
            logging.error(f"{self.filter_name} 필터 기준값 설정 오류: {str(e)}")
            return False
    
    def init_database(self):
        """데이터베이스 초기화"""
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            
            # 기본 테이블들 생성
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    combination TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    filter_name TEXT NOT NULL,
                    total_count INTEGER NOT NULL,
                    excluded_count INTEGER NOT NULL,
                    filter_time REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round, filter_name)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    filter_name TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round, filter_name)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filter_criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    filter_name TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round, filter_name)
                )
            """)
            
            self.conn.commit()
            self.initialized = True
            
        except Exception as e:
            logging.error(f"{self.filter_name} 데이터베이스 초기화 오류: {str(e)}")
    
    def _ensure_connection(self):
        """데이터베이스 연결 확인 및 재연결"""
        if not self.conn:
            import sqlite3
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # Allow multi-threading access
                timeout=30.0
            )
            if not self.initialized:
                self.init_database() 