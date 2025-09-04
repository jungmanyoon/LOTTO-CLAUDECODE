from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable, Set, Tuple, Type
import logging
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
import math
import time
import numpy as np

from src.utils.validators import LottoValidator

class BaseFilter(ABC):
    """필터 기본 클래스
    
    모든 필터 클래스가 상속받아야 하는 추상 기본 클래스입니다.
    필터링 로직의 인터페이스를 정의합니다.
    """
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        """BaseFilter 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준값 (기본값: None)
        """
        self.db_manager = db_manager
        self._criteria = criteria or {}
        self._validate_criteria()
        self._cached_results = {}
        self.computation_cost = 1.0  # 기본 계산 비용 (상속 클래스에서 조정)
        
        # 조기 종료 옵션
        self.use_early_termination = True
        self.early_termination_cache = {}
        
    @property
    def criteria(self):
        """호환성을 위한 criteria 속성"""
        return self._criteria
        
    @criteria.setter
    def criteria(self, value):
        """criteria 설정 시 _criteria 업데이트"""
        self._criteria = value

    @abstractmethod
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        pass
    
    def apply_filter(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용 (인터페이스 호환성 유지)
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        # 기본적으로 apply 메서드 호출하여 하위 호환성 유지
        return self.apply(combinations, round_num)
    
    def apply_early_termination(self, combinations: List[str], round_num: int = None) -> List[str]:
        """조합에 빠른 실패 전략 적용
        
        먼저 빠르게 실패하는 조건을 확인하여 필터링 효율성을 높입니다.
        
        Args:
            combinations: 확인할 조합 리스트
            round_num: (선택) 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        filtered_combinations = []
        total = len(combinations)
        processed = 0
        
        # 1개 조합 처리 시 불필요한 로그 제거
        if total > 1:
            logging.info(f"[빠른실패] {total}개 조합에 빠른 실패 전략 적용 중...")
        else:
            logging.debug(f"[DEBUG-빠른실패] {total}개 조합에 빠른 실패 전략 적용 중...")
        
        for combo in combinations:
            processed += 1
            
            # 캐시 확인
            cache_key = f"{round_num or 'none'}_{combo}"
            if cache_key in self.early_termination_cache:
                if self.early_termination_cache[cache_key]:
                    filtered_combinations.append(combo)
                continue
                
            # 조합 검사 - 빠른 실패 조건 확인
            if self.check_combination(combo, round_num):
                filtered_combinations.append(combo)
                self.early_termination_cache[cache_key] = True
            else:
                self.early_termination_cache[cache_key] = False
            
            # 진행 상황 로깅 (1% 단위)
            if processed % max(1, total // 100) == 0:
                progress = (processed / total) * 100
                if progress % 10 == 0:  # 10% 단위로만 로깅
                    logging.info(f"빠른 실패 처리 진행 중: {progress:.0f}% ({processed:,}/{total:,})")
        
        # 필터링 결과
        remaining = len(filtered_combinations)
        excluded = total - remaining
        # 1개 조합 처리 결과는 DEBUG로 처리
        if total > 1:
            logging.info(f"[빠른실패] 완료: {remaining:,}개 남음, {excluded:,}개 제외됨 ({(excluded/total)*100:.2f}%)")
        else:
            logging.debug(f"[DEBUG-빠른실패] 완료: {remaining:,}개 남음, {excluded:,}개 제외됨 ({(excluded/total)*100:.2f}%)")
        
        return filtered_combinations
    
    def check_combination(self, combination: str, round_num: int) -> bool:
        """단일 조합이 필터 조건을 만족하는지 확인
        
        필터별로 재정의하여 단일 조합 검사 로직 구현
        
        Args:
            combination: 검사할 조합
            round_num: 회차 번호
            
        Returns:
            bool: 조건 만족 여부
        """
        # 기본 구현은 apply 메서드를 호출
        return combination in self.apply([combination], round_num)
    
    def apply_parallel(self, combinations: List[str], num_workers: int = 4, round_num: int = None) -> List[str]:
        """병렬 처리를 사용하여 필터 적용
        
        Args:
            combinations: 로또 번호 조합 목록
            num_workers: 병렬 작업자 수
            round_num: 회차 번호 (선택적)
            
        Returns:
            필터링 후 남은 조합 목록
        """
        if len(combinations) < 1000:  # 작은 데이터는 일반 처리
            return self.apply(combinations, round_num)
            
        # 작업을 여러 청크로 분할
        chunks = np.array_split(combinations, num_workers * 2)
        chunks = [chunk.tolist() for chunk in chunks]
        
        # 병렬 처리
        filtered_combinations = []
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.apply, chunk, round_num) 
                      for chunk in chunks]
            for future in futures:
                filtered_combinations.extend(future.result())
            
        return filtered_combinations
    
    def apply_with_caching(self, combinations: List[str], round_num: int = None) -> List[str]:
        """캐싱을 사용하여 필터 적용
        
        이전 필터링 결과를 캐싱하여 성능 향상
        
        Args:
            combinations: 확인할 조합 리스트
            round_num: (선택) 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        # 캐시 키 생성 (라운드 + 필터 이름)
        cache_key = f"{round_num or 'none'}_{self.get_filter_name()}"
        
        logging.debug(f"[DEBUG-캐싱] 캐싱 모드로 필터 적용 중... (캐시 키: {cache_key})")
        
        # 캐시된 결과가 있으면 사용
        if cache_key in self._cached_results:
            logging.debug(f"[DEBUG-캐싱] 캐시된 결과 사용 (키: {cache_key})")
            cached_set = self._cached_results[cache_key]
            filtered = [c for c in combinations if c in cached_set]
            logging.debug(f"[DEBUG-캐싱] 캐시 히트: {len(filtered):,}/{len(combinations):,}개 남음")
            return filtered
        
        # 없으면 새로 계산하고 캐시
        logging.debug(f"[DEBUG-캐싱] 캐시 미스: 새로 계산 시작 (조합 수: {len(combinations):,}개)")
        filtered = self.apply(combinations, round_num)
        self._cached_results[cache_key] = set(filtered)
        logging.debug(f"[DEBUG-캐싱] 계산 완료: {len(filtered):,}/{len(combinations):,}개 남음")
        return filtered

    @abstractmethod
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사
        
        필터별로 필요한 기준값이 올바르게 설정되었는지 확인합니다.
        유효하지 않은 경우 ValueError를 발생시킵니다.
        """
        pass

    def get_filter_name(self) -> str:
        """필터 이름 반환"""
        return self.__class__.__name__

    def update_criteria(self, new_criteria: Dict[str, Any]) -> None:
        """필터링 기준값 업데이트"""
        self._criteria.update(new_criteria)
        self._validate_criteria()
        # 기준 변경 시 캐시 초기화
        self._cached_results = {}
        self.early_termination_cache = {}

    def get_criteria(self) -> Dict[str, Any]:
        """현재 필터링 기준값 조회
        
        Returns:
            Dict[str, Any]: 현재 기준값
        """
        return self._criteria.copy()
    
    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cached_results = {}
        self.early_termination_cache = {}
    
    def get_computation_cost(self) -> float:
        """필터의 계산 비용 반환
        
        높은 값은 더 많은 계산이 필요함을 의미
        필터 순서 최적화에 사용됨
        
        Returns:
            float: 계산 비용 (1.0 = 기본)
        """
        return self.computation_cost
    
    @staticmethod
    def combine_filters(filters: List['BaseFilter']) -> 'CompositeFilter':
        """여러 필터를 하나의 필터로 결합
        
        Args:
            filters: 결합할 필터 목록
            
        Returns:
            CompositeFilter: 결합된 필터 인스턴스
        """
        return CompositeFilter(filters)
    
    # 비트 연산 최적화 메서드
    @staticmethod
    def combination_to_bitmap(combination_str: str) -> int:
        """로또 조합 문자열을 비트맵으로 변환
        
        Args:
            combination_str: 로또 조합 문자열 (예: "1,2,3,4,5,6")
            
        Returns:
            int: 비트맵 표현 (각 번호는 비트 위치로 표현됨)
        """
        bitmap = 0
        for num in map(int, combination_str.split(',')):
            bitmap |= (1 << (num - 1))
        return bitmap
    
    @staticmethod
    def bitmap_to_combination(bitmap: int) -> List[int]:
        """비트맵을 로또 조합으로 변환
        
        Args:
            bitmap: 비트맵 표현
            
        Returns:
            List[int]: 로또 번호 리스트
        """
        combination = []
        for i in range(45):  # 로또 번호는 1-45
            if bitmap & (1 << i):
                combination.append(i + 1)
        return combination
    
    @staticmethod
    def count_bits(bitmap: int) -> int:
        """비트맵에서 1의 개수 계산 (로또 번호 개수)
        
        Args:
            bitmap: 비트맵 표현
            
        Returns:
            int: 1 비트 개수 (로또 번호 개수)
        """
        return bin(bitmap).count('1')
    
    @staticmethod
    def count_odd_bits(bitmap: int) -> int:
        """비트맵에서 홀수 위치 비트 개수 계산
        
        Args:
            bitmap: 비트맵 표현
            
        Returns:
            int: 홀수 위치의 1 비트 개수
        """
        # 홀수 위치(1, 3, 5, ...) 마스크
        odd_mask = 0
        for i in range(0, 45, 2):
            odd_mask |= (1 << i)
            
        return bin(bitmap & odd_mask).count('1')
    
    @staticmethod
    def count_even_bits(bitmap: int) -> int:
        """비트맵에서 짝수 위치 비트 개수 계산
        
        Args:
            bitmap: 비트맵 표현
            
        Returns:
            int: 짝수 위치의 1 비트 개수
        """
        # 짝수 위치(2, 4, 6, ...) 마스크
        even_mask = 0
        for i in range(1, 45, 2):
            even_mask |= (1 << i)
            
        return bin(bitmap & even_mask).count('1')

    def supports_early_termination(self) -> bool:
        """이 필터가 조기 종료 전략을 지원하는지 여부
        
        Returns:
            bool: 조기 종료 지원 여부
        """
        # 기본적으로 조기 종료를 지원하지 않음
        # 하위 클래스에서 재정의할 수 있음
        return False


class CompositeFilter(BaseFilter):
    """여러 필터를 결합한 복합 필터
    
    결합된 필터들은 AND 논리로 순차적으로 적용됨
    """
    
    def __init__(self, filters: List[BaseFilter]):
        """CompositeFilter 초기화
        
        Args:
            filters: 결합할 필터 목록
        """
        self.filters = filters
        self.db_manager = filters[0].db_manager if filters else None
        self._cached_results = {}
        
        # 계산 비용은 모든 필터의 합
        self.computation_cost = sum(f.get_computation_cost() for f in filters)
    
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """모든 하위 필터 적용
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        # 최적화: 가장 계산 비용이 낮은 필터부터 적용하여 빠르게 조합 수 줄임
        sorted_filters = sorted(self.filters, key=lambda f: f.get_computation_cost())
        
        filtered = combinations
        for filter_obj in sorted_filters:
            filtered = filter_obj.apply(filtered, round_num)
            # 필터링 후 조합이 없으면 바로 반환
            if not filtered:
                return []
                
        return filtered
    
    def _validate_criteria(self) -> None:
        """컴포지트 필터에서는 유효성 검사가 필요 없음"""
        pass
    
    def get_filter_name(self) -> str:
        """결합된 필터 이름 반환"""
        # 각 필터의 클래스 이름에서 'Filter' 부분을 제거하고 소문자로 변환
        filter_names = []
        for f in self.filters:
            name = f.get_filter_name()
            if name.endswith('Filter'):
                name = name[:-6]  # 'Filter' 부분 제거
            filter_names.append(name.lower())
        return '_'.join(filter_names)  # 언더스코어로 연결