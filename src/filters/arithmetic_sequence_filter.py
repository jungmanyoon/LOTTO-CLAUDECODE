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
        """청크 단위 필터링 처리 (numpy 변환 최적화)"""
        try:
            min_sequence = kwargs.get('min_sequence', 5)
            exclude_lengths = kwargs.get('exclude_lengths', [5, 6])
            exclude_set = set(exclude_lengths)

            if not combinations_chunk:
                return []

            # 문자열을 숫자 배열로 일괄 변환 (파싱 오버헤드 최소화)
            converted = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted.append(sorted(map(int, comb.split(','))))
                else:
                    converted.append(sorted(comb))

            numbers_array = np.array(converted, dtype=np.int8)

            filtered_combinations = []
            for idx in range(len(numbers_array)):
                nums = numbers_array[idx]
                max_seq = ArithmeticSequenceFilter._find_arithmetic_sequence_static(nums.tolist())

                if max_seq < min_sequence and max_seq not in exclude_set:
                    filtered_combinations.append(combinations_chunk[idx])

            return filtered_combinations

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []

    @staticmethod
    def _find_arithmetic_sequence_static(numbers: List[int]) -> int:
        """최적화된 등차수열 탐색 (n=6 특화)

        n=6 고정이므로 dict 생성 대신 직접 계산으로 최적화
        """
        n = len(numbers)
        if n < 3:
            return n

        sorted_nums = sorted(numbers)
        max_length = 2

        # n=6이므로 15쌍의 공차만 확인 (dict 생성 비용 제거)
        for i in range(n - 2):
            for j in range(i + 1, n):
                diff = sorted_nums[j] - sorted_nums[i]
                if diff == 0:
                    continue
                length = 2
                last_val = sorted_nums[j]
                for k in range(j + 1, n):
                    if sorted_nums[k] == last_val + diff:
                        length += 1
                        last_val = sorted_nums[k]
                if length > max_length:
                    max_length = length
                    if max_length >= n:
                        return max_length

        return max_length