import os
from typing import Dict, List, Optional, Tuple, Any
import logging
import sqlite3
import threading
from .db_structure import DatabasePaths
from .specialized_databases import (
    LottoNumbersDB,
    CombinationsDB,
    FilterDB,
    PatternsDB
)
from ..utils.constants import LottoConstants

class DatabaseManager:
    """
    통합 데이터베이스 관리자 (Singleton Pattern)

    로또 예측 시스템의 모든 데이터베이스 접근을 중앙 관리하는 싱글톤 클래스입니다.
    여러 특화된 데이터베이스(당첨번호, 조합, 필터, 패턴)를 통합하여
    일관된 인터페이스를 제공합니다.

    주요 기능:
        - 당첨번호 데이터 관리 (LottoNumbersDB)
        - 조합 데이터 캐싱 (CombinationsDB)
        - 16개 필터 결과 저장 (FilterDB)
        - 패턴 분석 결과 저장 (PatternsDB)
        - 이벤트 기반 콜백 시스템

    사용 예시:
        >>> db = DatabaseManager()  # 싱글톤 인스턴스 반환
        >>> numbers = db.get_numbers_with_bonus()  # 보너스 포함 당첨번호
        >>> last_round = db.get_last_round()  # 마지막 회차

    Thread Safety:
        - 싱글톤 패턴에 threading.Lock 사용
        - 각 특화 DB는 자체 연결 풀 관리
        - WAL 모드로 동시 읽기/쓰기 지원

    Events:
        - new_round_added: 새 회차 추가 시
        - data_updated: 데이터 업데이트 시
        - pattern_updated: 패턴 분석 완료 시
        - filter_updated: 필터 결과 업데이트 시

    Note:
        - 절대 직접 인스턴스를 생성하지 마세요. DatabaseManager()로 접근하세요.
        - 테스트 시 DatabaseManager._instance = None으로 초기화하세요.

    See Also:
        - LottoNumbersDB: 당첨번호 전용 DB
        - CombinationsDB: 조합 데이터 전용 DB
        - FilterDB: 필터 결과 전용 DB
        - PatternsDB: 패턴 분석 전용 DB
    """

    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls, base_dir: str = 'data'):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    logging.info("[SINGLETON] DatabaseManager 인스턴스 생성")
        return cls._instance
    
    def __init__(self, base_dir: str = 'data'):
        # 이미 초기화되었으면 재초기화 방지 (인스턴스 속성 기반 체크)
        # _initialized 클래스 변수만 체크하면 _instance=None 리셋 후 빈 인스턴스 생성 버그 발생
        if hasattr(self, 'lotto_db'):
            return

        with DatabaseManager._lock:
            if hasattr(self, 'lotto_db'):
                return

            self.paths = DatabasePaths(base_dir)

            # 이벤트 콜백 시스템 초기화
            self.event_callbacks = {
                'new_round_added': [],
                'data_updated': [],
                'pattern_updated': [],
                'filter_updated': []
            }

            # 각 데이터베이스 초기화
            self.lotto_db = LottoNumbersDB(self.paths.lotto_numbers)
            self.combinations_db = CombinationsDB(self.paths.combinations)
            self.patterns_db = PatternsDB(self.paths.patterns)

            # 기존 필터 데이터베이스 초기화
            self.filter_dbs: Dict[str, FilterDB] = {
                filter_type: FilterDB(path)
                for filter_type, path in self.paths.filter_paths.items()
            }

            # 새로운 필터 데이터베이스 초기화 - 수정된 부분
            self._initialize_new_filter_dbs()

            DatabaseManager._initialized = True
            logging.info("[SINGLETON] 데이터베이스 매니저 초기화 완료 (단일 인스턴스)")

    def _initialize_new_filter_dbs(self):
        """새로운 필터 데이터베이스 초기화 - 개선된 동시성 처리"""
        import time
        max_retries = 3
        retry_delay = 1.0
        
        try:
            # filters 디렉토리 확인 및 생성
            if not os.path.exists(self.paths.filters_dir):
                os.makedirs(self.paths.filters_dir)
            
            new_filters = {
                'multiple': 'multiple_filter.db',
                'ten_section': 'ten_section_filter.db',           # 추가
                'arithmetic_sequence': 'arithmetic_sequence.db',   # 추가
                'geometric_sequence': 'geometric_sequence.db',      # 추가
                # 새로운 필터들 추가
                'prime_composite': 'prime_composite_filter.db',
                'digit_sum': 'digit_sum_filter.db',
                'dispersion': 'dispersion_filter.db',
                'ml_prediction': 'ml_prediction_filter.db',       # ML 예측 필터 추가
                'ac_value': 'ac_value_filter.db'                  # AC값 필터 추가
            }
            
            # 각 필터의 DB 파일 생성 및 초기화
            for filter_type, db_name in new_filters.items():
                db_path = os.path.join(self.paths.filters_dir, db_name)
                
                # 재시도 로직 추가
                for attempt in range(max_retries):
                    try:
                        self.filter_dbs[filter_type] = FilterDB(db_path)
                        
                        # DB 연결 테스트
                        with self.filter_dbs[filter_type]._create_connection() as conn:
                            if conn is not None:
                                logging.info(f"필터 데이터베이스 초기화 완료: {filter_type}")
                                break  # 성공시 반복 종료
                            else:
                                logging.error(f"필터 데이터베이스 초기화 실패: {filter_type}")
                                
                    except sqlite3.OperationalError as e:
                        if "database is locked" in str(e) and attempt < max_retries - 1:
                            logging.warning(f"데이터베이스 잠금 발생, 재시도 중... ({filter_type}, 시도 {attempt + 1}/{max_retries})")
                            time.sleep(retry_delay * (attempt + 1))  # 점진적 대기
                        else:
                            raise
                
            logging.info("새로운 필터 데이터베이스 초기화 완료")
            
        except Exception as e:
            logging.error(f"필터 데이터베이스 초기화 중 오류 발생: {str(e)}")

    def get_filter_db(self, filter_type: str) -> Optional[FilterDB]:
        """특정 필터의 데이터베이스 반환"""
        try:
            if filter_type not in self.filter_dbs:
                logging.error(f"알 수 없는 필터 타입: {filter_type}")
                return None
            return self.filter_dbs[filter_type]
        except Exception as e:
            logging.error(f"필터 DB 조회 중 오류 발생: {str(e)}")
            return None

    # 당첨 번호 관련 메서드들
    def register_callback(self, event: str, callback: callable):
        """
        이벤트 콜백 등록

        Args:
            event: 이벤트 타입 ('new_round_added', 'data_updated', 'pattern_updated', 'filter_updated')
            callback: 콜백 함수
        """
        if event in self.event_callbacks:
            self.event_callbacks[event].append(callback)
            logging.info(f"[DatabaseManager] {event} 콜백 등록됨")
        else:
            logging.warning(f"[DatabaseManager] 알 수 없는 이벤트: {event}")

    def _trigger_callbacks(self, event: str, *args, **kwargs):
        """
        등록된 콜백 실행

        Args:
            event: 이벤트 타입
            *args, **kwargs: 콜백 함수에 전달할 인자

        Note:
            부분 실패를 허용하며, 실패한 콜백은 로그에 기록
        """
        if event in self.event_callbacks:
            failed_callbacks = []
            for callback in self.event_callbacks[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    callback_name = getattr(callback, '__name__', repr(callback))
                    logging.error(f"[DatabaseManager] {event} 콜백 실행 오류 ({callback_name}): {e}")
                    failed_callbacks.append((callback_name, e))

            # 실패 요약 로그
            if failed_callbacks:
                logging.warning(
                    f"[DatabaseManager] {len(failed_callbacks)}/{len(self.event_callbacks[event])} "
                    f"callbacks failed for '{event}' event"
                )

    def get_last_round(self) -> int:
        """마지막으로 저장된 회차 번호 조회"""
        return self.lotto_db.get_last_round()

    def insert_lotto_numbers(self, round_num: int, numbers: List[int], draw_date: str) -> bool:
        """로또 번호 데이터 삽입"""
        result = self.lotto_db.insert_numbers(round_num, numbers, draw_date)
        if result:
            # 새 회차 추가 이벤트 트리거
            self._trigger_callbacks('new_round_added', round_num)
            logging.info(f"[DatabaseManager] 새 회차 추가 이벤트 발생: {round_num}회차")
        return result

    def insert_lotto_numbers_with_bonus(self, round_num: int, numbers: List[int], bonus: int, draw_date: str) -> bool:
        """로또 번호와 보너스 번호 데이터 삽입"""
        result = self.lotto_db.insert_numbers_with_bonus(round_num, numbers, bonus, draw_date)
        if result:
            # 새 회차 추가 이벤트 트리거
            self._trigger_callbacks('new_round_added', round_num)
            logging.info(f"[DatabaseManager] 새 회차 추가 이벤트 발생: {round_num}회차")
        return result

    def get_all_numbers(self) -> List[Tuple[int, str, str]]:
        """모든 로또 번호 데이터 조회"""
        return self.lotto_db.get_all_numbers()

    def get_numbers_by_round(self, round_num: int) -> Optional[Tuple[int, str, str]]:
        """특정 회차의 로또 번호 데이터 조회"""
        return self.lotto_db.get_numbers_by_round(round_num)
    
    def get_recent_numbers(self, count: int) -> List[Tuple[int, str, str]]:
        """최근 n회의 당첨 번호 데이터 조회
        
        Args:
            count: 조회할 최근 회차 수
            
        Returns:
            List[Tuple[int, str, str]]: (회차, 번호, 추첨일) 튜플의 리스트
        """
        return self.lotto_db.get_recent_numbers(count)

    def get_all_winning_numbers(self) -> List[str]:
        """모든 당첨 번호 목록 조회"""
        return self.lotto_db.get_all_winning_numbers()
    
    def get_winning_numbers_before(self, round_num: int) -> List[str]:
        """특정 회차 이전의 당첨 번호들 조회 (백테스팅용)"""
        return self.lotto_db.get_winning_numbers_before(round_num)
    
    def get_winning_numbers(self, round_num: int) -> Optional[List[int]]:
        """특정 회차의 당첨 번호를 리스트로 반환
        
        Args:
            round_num: 회차 번호
            
        Returns:
            당첨 번호 리스트 또는 None
        """
        result = self.get_numbers_by_round(round_num)
        if result:
            _, numbers_str, _ = result
            return [int(n) for n in numbers_str.split(',')]
        return None
    
    def get_winning_numbers_last_n(self, n: int) -> List[Tuple[int, List[int], str]]:
        """최근 n회차의 당첨 번호를 반환
        
        Args:
            n: 조회할 회차 수
            
        Returns:
            (회차, 당첨번호리스트, 날짜) 튜플의 리스트
        """
        recent_data = self.get_recent_numbers(n)
        result = []
        for round_num, numbers_str, date_str in recent_data:
            numbers = [int(n) for n in numbers_str.split(',')]
            result.append((round_num, numbers, date_str))
        return result

    # 조합 관련 메서드들
    def check_base_combinations_exist(self) -> bool:
        """기본 조합이 이미 생성되어 있는지 확인"""
        return self.combinations_db.check_base_combinations_exist()

    def save_base_combinations(self, combinations: List[str]) -> bool:
        """기본 로또 조합 저장"""
        return self.combinations_db.save_base_combinations(combinations)

    def get_base_combinations(self) -> List[str]:
        """기본 로또 조합 조회"""
        return self.combinations_db.get_base_combinations()

    def save_valid_combinations(self, round_num: int, combinations: List[str]) -> bool:
        """유효한 로또 번호 조합 저장"""
        return self.combinations_db.save_valid_combinations(round_num, combinations)

    def get_valid_combinations(self, round_num: int) -> List[str]:
        """특정 회차의 유효한 조합 조회"""
        return self.combinations_db.get_valid_combinations(round_num)

    # 필터링 관련 메서드들
    def get_last_filtered_round(self) -> int:
        """마지막으로 필터링된 회차 조회"""
        return max(
            (db.get_last_filtered_round() for db in self.filter_dbs.values()),
            default=0
        )

    def save_filtered_combinations(self, round_num: int, combinations: List[str], 
                                 filter_type: str) -> bool:
        """필터링된 조합 저장"""
        filter_db = self.get_filter_db(filter_type)
        if not filter_db:
            logging.error(f"알 수 없는 필터 타입: {filter_type}")
            return False
        return filter_db.save_filtered_combinations(round_num, combinations)

    def get_filtered_statistics(self, round_num: int) -> Dict[str, Dict[str, Any]]:
        """필터링 결과 통계"""
        stats = {}
        for filter_type, db in self.filter_dbs.items():
            filter_stats = db.get_filtering_statistics(round_num)
            if filter_stats:
                stats[filter_type] = filter_stats
        return stats

    # 패턴 분석 관련 메서드들
    def save_pattern_analysis(self, round_num: int, patterns: Dict[str, Any]) -> bool:
        """패턴 분석 결과 저장"""
        return self.patterns_db.save_pattern_analysis(round_num, patterns)

    def get_latest_pattern_analysis(self) -> Optional[Dict[str, Any]]:
        """최신 패턴 분석 결과 조회"""
        return self.patterns_db.get_latest_pattern_analysis()

    def get_pattern_history(self, pattern_type: str) -> Optional[List[Dict[str, Any]]]:
        """특정 패턴의 이력 조회"""
        return self.patterns_db.get_pattern_history(pattern_type)

    # 추가 유틸리티 메서드들
    def get_numbers_since_round(self, last_round: int) -> List[str]:
        """특정 회차 이후의 당첨 번호들 조회"""
        return self.lotto_db.get_numbers_since_round(last_round)

    def get_winning_numbers_range(self, min_round: int, current_round: int) -> List[str]:
        """특정 범위의 당첨 번호 조회"""
        return self.lotto_db.get_winning_numbers_range(min_round, current_round)

    def save_filter_criteria(self, round_num: int, filter_type: str, criteria: Dict) -> bool:
        """필터링 기준 저장"""
        filter_db = self.get_filter_db(filter_type)
        if not filter_db:
            logging.error(f"알 수 없는 필터 타입: {filter_type}")
            return False
        return filter_db.save_filter_criteria(round_num, criteria)

    def get_detailed_filtering_status(self, round_num: int) -> Dict[str, Any]:
        """상세 필터링 상태 조회"""
        total_combinations = len(self.get_base_combinations())
        filtered_counts = {}
        
        for filter_type, db in self.filter_dbs.items():
            stats = db.get_filtering_statistics(round_num)
            if stats:
                filtered_counts[filter_type] = stats['filtered_count']
        
        total_filtered = sum(filtered_counts.values())
        
        return {
            'total': total_combinations,
            'filtered': filtered_counts,
            'remaining': total_combinations - total_filtered
        }
    
    # 새로운 메서드들 추가
    def get_multiple_pattern_statistics(self, round_num: int) -> Dict[str, Any]:
        """배수 패턴 통계 조회"""
        return self.patterns_db.get_pattern_statistics(
            round_num, 
            LottoConstants.PatternTypes.MULTIPLE
        )
    
    def save_multiple_filter_results(self, round_num: int, filtered_combinations: List[str],
                                   details: Dict[str, Any]) -> bool:
        """배수 필터 결과 저장"""
        try:
            # 필터링된 조합 저장
            self.save_filtered_combinations(
                round_num, 
                filtered_combinations, 
                LottoConstants.FilterTypes.MULTIPLE
            )
            
            # 상세 정보 저장
            filter_db = self.get_filter_db(LottoConstants.FilterTypes.MULTIPLE)
            if filter_db:
                filter_db.save_filter_details(round_num, details)
            return True
        except Exception as e:
            logging.error(f"배수 필터 결과 저장 중 오류 발생: {str(e)}")
            return False   
    
    def get_combined_pattern_statistics(self, round_num: int) -> Dict[str, Dict[str, Any]]:
        """모든 패턴의 통계 조회"""
        try:
            stats = {}
            
            # 기존 패턴 통계 조회
            existing_patterns = [
                LottoConstants.PatternTypes.NUMBER_FREQUENCY,
                LottoConstants.PatternTypes.ODD_EVEN,
                LottoConstants.PatternTypes.CONSECUTIVE,
                LottoConstants.PatternTypes.SUM_RANGE,
                LottoConstants.PatternTypes.FIXED_STEP,
                LottoConstants.PatternTypes.LAST_DIGIT,
                LottoConstants.PatternTypes.MAX_GAP,
                LottoConstants.PatternTypes.SECTION,
                LottoConstants.PatternTypes.AVERAGE
            ]
            
            # 새로운 패턴 통계 조회
            new_patterns = [
                LottoConstants.PatternTypes.MULTIPLE,
                LottoConstants.PatternTypes.ALTERNATING_ODD_EVEN,
                LottoConstants.PatternTypes.SUM_MULTIPLE
            ]
            
            for pattern_type in existing_patterns + new_patterns:
                pattern_stats = self.patterns_db.get_pattern_statistics(round_num, pattern_type)
                if pattern_stats:
                    stats[pattern_type] = pattern_stats
            
            return stats
            
        except Exception as e:
            logging.error(f"패턴 통계 조회 중 오류 발생: {str(e)}")
            return {}
    
    def get_filter_statistics_by_group(self, round_num: int) -> Dict[str, Dict[str, Any]]:
        """필터 그룹별 통계 조회"""
        try:
            stats = {
                '기본 필터': {},
                '패턴 필터': {},
                '신규 필터': {}
            }
            
            # 기본 필터 통계
            basic_filters = ['match', 'odd_even', 'consecutive', 'sum_range']
            for filter_type in basic_filters:
                filter_db = self.get_filter_db(filter_type)
                if filter_db:
                    stats['기본 필터'][filter_type] = filter_db.get_filtering_statistics(round_num)
            
            # 패턴 필터 통계
            pattern_filters = ['fixed_step', 'last_digit', 'max_gap', 'section', 'average']
            for filter_type in pattern_filters:
                filter_db = self.get_filter_db(filter_type)
                if filter_db:
                    stats['패턴 필터'][filter_type] = filter_db.get_filtering_statistics(round_num)
            
            # 신규 필터 통계
            new_filters = ['multiple', 'alternating_odd_even', 'sum_multiple']
            for filter_type in new_filters:
                filter_db = self.get_filter_db(filter_type)
                if filter_db:
                    stats['신규 필터'][filter_type] = filter_db.get_filtering_statistics(round_num)
            
            return stats
            
        except Exception as e:
            logging.error(f"필터 그룹별 통계 조회 중 오류 발생: {str(e)}")
            return {}

    def get_multiple_filter_details(self, round_num: int) -> Optional[Dict[str, Any]]:
        """배수 필터 상세 정보 조회"""
        filter_db = self.get_filter_db(LottoConstants.FilterTypes.MULTIPLE)
        return filter_db.get_filter_details(round_num) if filter_db else None

    def get_alternating_filter_details(self, round_num: int) -> Optional[Dict[str, Any]]:
        """홀짝 교차 필터 상세 정보 조회"""
        filter_db = self.get_filter_db(LottoConstants.FilterTypes.ALTERNATING_ODD_EVEN)
        return filter_db.get_filter_details(round_num) if filter_db else None

    def get_sum_multiple_filter_details(self, round_num: int) -> Optional[Dict[str, Any]]:
        """합계 배수 필터 상세 정보 조회"""
        filter_db = self.get_filter_db(LottoConstants.FilterTypes.SUM_MULTIPLE)
        return filter_db.get_filter_details(round_num) if filter_db else None

    def create_filter_db(self, filter_name: str) -> Optional[FilterDB]:
        """새로운 필터 데이터베이스 생성
        
        Args:
            filter_name: 생성할 필터 데이터베이스 이름
            
        Returns:
            FilterDB 인스턴스 또는 None (오류 시)
        """
        try:
            # filters 디렉토리 확인 및 생성
            if not os.path.exists(self.paths.filters_dir):
                os.makedirs(self.paths.filters_dir)
                
            # 이미 존재하는 필터인지 확인
            if filter_name in self.filter_dbs:
                return self.filter_dbs[filter_name]
                
            # 새 필터 데이터베이스 생성
            db_path = os.path.join(self.paths.filters_dir, f"{filter_name}.db")
            filter_db = FilterDB(db_path)
            
            # DB 연결 테스트
            with filter_db._create_connection() as conn:
                if conn is not None:
                    logging.info(f"새로운 필터 데이터베이스 생성 완료: {filter_name}")
                    # 필터 DB 딕셔너리에 추가
                    self.filter_dbs[filter_name] = filter_db
                    return filter_db
                else:
                    logging.error(f"필터 데이터베이스 생성 실패: {filter_name}")
                    return None
                    
        except Exception as e:
            logging.error(f"필터 데이터베이스 생성 중 오류 발생: {str(e)}")
            return None

    def get_numbers_with_bonus(self) -> List[Tuple[int, Tuple[int, ...]]]:
        """보너스 번호를 포함한 모든 당첨번호 조회
        
        Returns:
            List[Tuple[int, Tuple[int, ...]]]: (회차, (번호1,번호2,...,번호6,보너스)) 튜플 리스트
        """
        return self.lotto_db.get_numbers_with_bonus()
    
    def get_latest_round(self) -> int:
        """가장 최신 회차 번호 조회
        
        Returns:
            int: 최신 회차 번호
        """
        return self.lotto_db.get_latest_round()
    
    def close_all_connections(self):
        """모든 데이터베이스 연결 종료
        
        각 데이터베이스의 연결을 안전하게 종료합니다.
        """
        try:
            # 각 데이터베이스 연결 종료
            if hasattr(self, 'lotto_db'):
                self.lotto_db = None
            if hasattr(self, 'combinations_db'):
                self.combinations_db = None
            if hasattr(self, 'patterns_db'):
                self.patterns_db = None
            
            # 필터 데이터베이스 연결 종료
            if hasattr(self, 'filter_dbs'):
                for filter_name in self.filter_dbs:
                    self.filter_dbs[filter_name] = None
                self.filter_dbs.clear()
            
            logging.info("모든 데이터베이스 연결이 종료되었습니다.")
        except Exception as e:
            logging.error(f"데이터베이스 연결 종료 중 오류: {e}")
    
    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 리셋 (테스트 용도)"""
        with cls._lock:
            if cls._instance:
                # 기존 연결 종료
                if hasattr(cls._instance, 'close_all_connections'):
                    cls._instance.close_all_connections()
                cls._instance = None
                cls._initialized = False
                logging.info("[SINGLETON] DatabaseManager 인스턴스 리셋 완료")
