# src/filters/arithmetic_sequence_filter.py

from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class ArithmeticSequenceFilter(BaseFilter):
    """등차수열 패턴 필터"""
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        self.default_criteria = {
            'min_sequence': 5,
            'exclude_lengths': [5, 6]
        }
        if criteria:
            self.default_criteria.update(criteria)
        super().__init__(db_manager, self.default_criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_sequence' not in self.criteria:
            raise ValueError("'min_sequence' 값이 필요합니다.")
            
        if 'exclude_lengths' not in self.criteria:  # 수정: 파라미터 이름 변경
            raise ValueError("'exclude_lengths' 값이 필요합니다.")
            
        min_sequence = self.criteria['min_sequence']
        if not isinstance(min_sequence, int) or min_sequence < 3:
            raise ValueError("'min_sequence'는 3 이상의 정수여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"arithmetic_sequence 필터 진행률",
                min_sequence=self.criteria['min_sequence'],
                exclude_lengths=self.criteria['exclude_lengths']
            )
        except Exception as e:
            logging.error(f"등차수열 필터링 중 오류 발생: {str(e)}")
            return combinations

    def _find_arithmetic_sequence(self, numbers: List[int]) -> int:
        """가장 긴 등차수열의 길이 찾기"""
        n = len(numbers)
        max_length = 0

        for i in range(n-2):
            for j in range(i+1, n-1):
                d = numbers[j] - numbers[i]
                current_length = 2
                last = numbers[j]
                
                for k in range(j+1, n):
                    if numbers[k] - last == d:
                        current_length += 1
                        last = numbers[k]
                
                max_length = max(max_length, current_length)

        return max_length

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], **kwargs) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            min_sequence = kwargs.get('min_sequence', 5)
            exclude_lengths = kwargs.get('exclude_lengths', [5, 6])

            filtered_combinations = []
            
            for comb in combinations_chunk:
                numbers = sorted(list(map(int, comb.split(','))))
                max_sequence = ArithmeticSequenceFilter._find_arithmetic_sequence_static(numbers)
                
                if max_sequence < min_sequence or max_sequence not in exclude_lengths:
                    filtered_combinations.append(comb)

            return filtered_combinations

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []

    @staticmethod
    def _find_arithmetic_sequence_static(numbers: List[int]) -> int:
        """정적 메서드로 구현된 등차수열 찾기"""
        n = len(numbers)
        max_length = 0

        for i in range(n-2):
            for j in range(i+1, n-1):
                d = numbers[j] - numbers[i]
                current_length = 2
                last = numbers[j]
                
                for k in range(j+1, n):
                    if numbers[k] - last == d:
                        current_length += 1
                        last = numbers[k]
                
                max_length = max(max_length, current_length)

        return max_length