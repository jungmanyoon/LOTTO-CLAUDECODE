
from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class LastDigitFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        """
        끝자리 필터 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준값 (기본값: None)
                     예: {'min_same_last_digits': 3}
        """
        super().__init__(db_manager, criteria)
        # 성능 최적화를 위한 FilterOptimizer 추가 - 래퍼 함수 사용
        self.optimizer = FilterOptimizer(self._process_chunk_wrapper)
    
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_same_last_digits' not in self.criteria:
            raise ValueError("'min_same_last_digits' 값이 필요합니다.")
        
        min_digits = self.criteria['min_same_last_digits']
        if not isinstance(min_digits, int) or min_digits < 2:
            raise ValueError("'min_same_last_digits'는 2 이상의 정수여야 합니다.")
    
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"last_digit 필터 진행률",
                min_same_last_digits=self.criteria['min_same_last_digits']
            )
        except Exception as e:
            logging.error(f"끝자리 필터링 중 오류 발생: {str(e)}")
            return combinations
    
    @staticmethod
    def _process_chunk_wrapper(combinations_chunk: List[str], **kwargs) -> List[str]:
        """FilterOptimizer용 래퍼 함수 - 키워드 인수를 위치 인수로 변환"""
        min_same_last_digits = kwargs.get('min_same_last_digits')
        return LastDigitFilter._process_chunk(combinations_chunk, min_same_last_digits)

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      min_same_last_digits: int = None,
                      **kwargs) -> List[str]:
        """청크 단위 필터링 처리 - NumPy 최적화 적용
        
        Args:
            combinations_chunk: 처리할 조합 목록
            min_same_last_digits: 최소 동일 끝자리 개수
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            # 필수 매개변수 검증
            if min_same_last_digits is None:
                logging.error("_process_chunk: min_same_last_digits 매개변수 누락")
                return combinations_chunk
                
            # 문자열 조합을 NumPy 배열로 변환 (타입 체크 추가)
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.int8)
            
            # 끝자리 숫자 추출 (모듈로 연산)
            last_digits = chunk_arrays % 10
            
            # 각 끝자리 숫자의 빈도 계산
            max_same_digits = np.zeros(len(chunk_arrays), dtype=np.int8)
            
            # 0부터 9까지의 각 끝자리에 대해 검사
            for digit in range(10):
                digit_count = np.sum(last_digits == digit, axis=1)
                max_same_digits = np.maximum(max_same_digits, digit_count)
            
            # 최소 기준 이상의 동일 끝자리를 가진 조합 필터링
            valid_mask = max_same_digits < min_same_last_digits
            
            return [combinations_chunk[i] for i in range(len(chunk_arrays)) if valid_mask[i]]
            
        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return combinations_chunk