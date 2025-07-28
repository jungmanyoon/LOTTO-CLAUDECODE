
from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class SumRangeFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_sum' not in self.criteria or 'max_sum' not in self.criteria:
            raise ValueError("'min_sum'과 'max_sum' 값이 모두 필요합니다.")
            
        min_sum = self.criteria['min_sum']
        max_sum = self.criteria['max_sum']
        
        if not isinstance(min_sum, (int, float)) or not isinstance(max_sum, (int, float)):
            raise ValueError("합계 범위는 숫자여야 합니다.")
            
        if min_sum >= max_sum:
            raise ValueError("최소값이 최대값보다 작아야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"sum_range 필터 진행률",
                min_sum=self.criteria['min_sum'],
                max_sum=self.criteria['max_sum']
            )
        except Exception as e:
            logging.error(f"합계 범위 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      min_sum: float,
                      max_sum: float) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            chunk_arrays = np.array([
                list(map(int, comb.split(','))) 
                for comb in combinations_chunk
            ], dtype=np.int8)

            # 합계 계산
            sums = np.sum(chunk_arrays, axis=1)
            
            # 범위 조건 검사
            valid_mask = (sums >= min_sum) & (sums <= max_sum)
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []