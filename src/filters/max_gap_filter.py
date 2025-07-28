from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class MaxGapFilter(BaseFilter):
    """최대 간격 패턴 필터
    
    연속된 번호 사이의 최대 간격을 분석하고 필터링합니다.
    """
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'max_allowed_gap' not in self.criteria:
            raise ValueError("'max_allowed_gap' 값이 필요합니다.")
            
        max_gap = self.criteria['max_allowed_gap']
        if not isinstance(max_gap, int) or max_gap < 1 or max_gap > 40:
            raise ValueError("'max_allowed_gap'는 1에서 40 사이의 정수여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"max_gap 필터 진행률",
                max_allowed_gap=self.criteria['max_allowed_gap']
            )
        except Exception as e:
            logging.error(f"최대 간격 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      max_allowed_gap: int) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            chunk_arrays = np.array([
                list(map(int, comb.split(','))) 
                for comb in combinations_chunk
            ], dtype=np.int8)

            # 정렬된 배열 생성
            sorted_arrays = np.sort(chunk_arrays, axis=1)
            
            # 연속된 번호 사이의 차이 계산
            diffs = np.diff(sorted_arrays, axis=1)
            
            # 각 조합의 최대 간격 계산
            max_gaps = np.max(diffs, axis=1)
            
            # 최대 허용 간격보다 작은 조합만 선택
            valid_mask = max_gaps <= max_allowed_gap
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []

    def calculate_gap_statistics(self, winning_numbers: List[str]) -> Dict[int, float]:
        """당첨 번호의 간격 통계 계산"""
        try:
            gap_counts = {}
            total = len(winning_numbers)
            
            for numbers_str in winning_numbers:
                numbers = sorted(list(map(int, numbers_str.split(','))))
                diffs = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
                max_gap = max(diffs)
                gap_counts[max_gap] = gap_counts.get(max_gap, 0) + 1
                
            return {
                gap: (count / total * 100)
                for gap, count in gap_counts.items()
            }
            
        except Exception as e:
            logging.error(f"간격 통계 계산 중 오류 발생: {str(e)}")
            return {}