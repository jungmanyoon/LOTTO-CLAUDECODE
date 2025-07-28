from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class AverageFilter(BaseFilter):
    """산술 평균 필터"""
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_average' not in self.criteria or 'max_average' not in self.criteria:
            raise ValueError("'min_average'와 'max_average' 값이 필요합니다.")
            
        min_avg = self.criteria['min_average']
        max_avg = self.criteria['max_average']
        
        if not isinstance(min_avg, (int, float)) or not isinstance(max_avg, (int, float)):
            raise ValueError("평균값 범위는 숫자여야 합니다.")
            
        if min_avg >= max_avg:
            raise ValueError("최소 평균값이 최대 평균값보다 작아야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"average 필터 진행률",
                min_average=self.criteria['min_average'],
                max_average=self.criteria['max_average']
            )
        except Exception as e:
            logging.error(f"평균값 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                    min_average: float,
                    max_average: float) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            chunk_arrays = np.array([
                list(map(int, comb.split(','))) 
                for comb in combinations_chunk
            ], dtype=np.float32)

            # 각 조합의 평균값 계산
            averages = np.mean(chunk_arrays, axis=1)
            
            # 수정: 극단적인 평균값 제외 (8.0~11.2 이하와 36.5~39.7 이상)
            valid_mask = (
                (averages > 11.2) &   # 8.0~11.2 구간 제외
                (averages < 36.5) &   # 36.5~39.7 구간 제외
                (averages >= min_average) & 
                (averages <= max_average)
            )
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []