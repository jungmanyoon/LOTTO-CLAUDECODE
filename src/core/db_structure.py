import os
import sqlite3
import logging
from typing import Dict, Optional
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.utils.db_connection_manager import DatabaseConnectionManager

class DatabasePaths:
    """데이터베이스 파일 경로 관리"""
    
    def __init__(self, base_dir: str = 'data'):
        self.base_dir = base_dir
        self.filters_dir = os.path.join(base_dir, 'filters')
        
        # 각 DB 파일 경로 설정
        self.lotto_numbers = os.path.join(base_dir, 'lotto_numbers.db')
        self.combinations = os.path.join(base_dir, 'combinations.db')
        self.patterns = os.path.join(base_dir, 'patterns.db')
        
        # 필터별 DB 파일 - 새로운 필터 추가
        self.filter_paths = {
            # 기존 필터들
            'match': os.path.join(self.filters_dir, 'match_filter.db'),
            'odd_even': os.path.join(self.filters_dir, 'odd_even_filter.db'),
            'consecutive': os.path.join(self.filters_dir, 'consecutive_filter.db'),
            'sum_range': os.path.join(self.filters_dir, 'sum_range_filter.db'),
            'fixed_step': os.path.join(self.filters_dir, 'fixed_step_filter.db'),
            'last_digit': os.path.join(self.filters_dir, 'last_digit_filter.db'),
            'max_gap': os.path.join(self.filters_dir, 'max_gap_filter.db'),
            'section': os.path.join(self.filters_dir, 'section_filter.db'),
            'average': os.path.join(self.filters_dir, 'average_filter.db'),

            # 새로운 필터들 추가
            'multiple': os.path.join(self.filters_dir, 'multiple_filter.db'),
            'ten_section': os.path.join(self.filters_dir, 'ten_section_filter.db'),
            'arithmetic_sequence': os.path.join(self.filters_dir, 'arithmetic_sequence_filter.db'),
            'geometric_sequence': os.path.join(self.filters_dir, 'geometric_sequence_filter.db'),
            'prime_composite': os.path.join(self.filters_dir, 'prime_composite_filter.db'),
            'digit_sum': os.path.join(self.filters_dir, 'digit_sum_filter.db'),
            'dispersion': os.path.join(self.filters_dir, 'dispersion_filter.db'),
            'outlier_detection': os.path.join(self.filters_dir, 'outlier_detection_filter.db'),
            'balanced_quadrant': os.path.join(self.filters_dir, 'balanced_quadrant_filter.db')
        }
                
        self._ensure_directories()
    
    def _ensure_directories(self):
        """필요한 디렉토리 생성"""
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.filters_dir, exist_ok=True)

    def get_filter_db_path(self, filter_type: str) -> Optional[str]:
        """필터 타입에 해당하는 DB 파일 경로 반환
        
        Args:
            filter_type: 필터 유형
            
        Returns:
            Optional[str]: DB 파일 경로 또는 None
        """
        return self.filter_paths.get(filter_type)

    def get_all_db_paths(self) -> Dict[str, str]:
        """모든 데이터베이스 파일 경로 반환
        
        Returns:
            Dict[str, str]: 데이터베이스 이름과 경로 매핑
        """
        paths = {
            'lotto_numbers': self.lotto_numbers,
            'combinations': self.combinations,
            'patterns': self.patterns
        }
        paths.update({f"filter_{k}": v for k, v in self.filter_paths.items()})
        return paths

    def validate_paths(self) -> bool:
        """모든 데이터베이스 경로 유효성 검사
        
        Returns:
            bool: 모든 경로가 유효한지 여부
        """
        try:
            # 기본 디렉토리 확인
            if not os.path.exists(self.base_dir) or not os.path.exists(self.filters_dir):
                return False
            
            # 필수 DB 파일 확인
            required_dbs = [self.lotto_numbers, self.combinations, self.patterns]
            for db_path in required_dbs:
                if not os.path.exists(os.path.dirname(db_path)):
                    return False
            
            # 필터 DB 파일 디렉토리 확인
            for path in self.filter_paths.values():
                if not os.path.exists(os.path.dirname(path)):
                    return False
            
            return True
            
        except Exception as e:
            logging.error(f"경로 유효성 검사 중 오류 발생: {str(e)}")
            return False

class BaseDatabase:
    """데이터베이스 기본 클래스 - 개선된 연결 관리"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection_manager = DatabaseConnectionManager()
        self._initialize_database()
    
    def _initialize_database(self):
        """데이터베이스 초기화 - 하위 클래스에서 구현"""
        raise NotImplementedError
        
    def _create_connection(self):
        """데이터베이스 연결 생성 - 개선된 연결 관리자 사용"""
        # 새로운 연결 관리자를 사용하여 자동 재시도 및 락 관리
        return self.connection_manager.get_connection(self.db_path)
    
    def execute_query(self, query: str, params: tuple = None) -> Optional[list]:
        """쿼리 실행 with 자동 재시도"""
        return self.connection_manager.execute_with_retry(
            self.db_path, query, params
        )
    
    def check_integrity(self) -> bool:
        """데이터베이스 무결성 검사"""
        return self.connection_manager.check_database_integrity(self.db_path)
    
    def optimize(self) -> bool:
        """데이터베이스 최적화"""
        return self.connection_manager.optimize_database(self.db_path)