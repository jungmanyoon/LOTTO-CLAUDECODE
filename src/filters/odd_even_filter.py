from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer
from ..utils.constants import LottoConstants

class OddEvenFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        # 기본 기준값: 홀수/짝수 6개인 조합 제외
        self.default_criteria = {'excluded_counts': [6]}
        if criteria:
            self.default_criteria.update(criteria)
        super().__init__(db_manager, self.default_criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'excluded_counts' not in self.criteria:
            raise ValueError("'excluded_counts' 값이 필요합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            logging.info(f"[DEBUG-OddEven] 홀짝 필터 시작: {len(combinations):,}개 조합, 제외 기준: {self.criteria['excluded_counts']}")
            
            filtered = self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"홀짝 필터 진행률",
                excluded_counts=self.criteria['excluded_counts']
            )
            
            excluded_count = len(combinations) - len(filtered)
            logging.info(f"[DEBUG-OddEven] 홀짝 필터 완료: {len(filtered):,}/{len(combinations):,}개 남음 ({excluded_count:,}개 제외됨)")
            
            # 샘플 조합 확인
            if len(filtered) > 0 and len(filtered) < len(combinations):
                sample_before = combinations[:3]
                sample_after = filtered[:3]
                logging.info(f"[DEBUG-OddEven] 필터링 전 샘플: {sample_before}")
                logging.info(f"[DEBUG-OddEven] 필터링 후 샘플: {sample_after}")
            
            return filtered
        except Exception as e:
            logging.error(f"홀짝 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], excluded_counts: List[int]) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            chunk_arrays = np.array([
                list(map(int, comb.split(','))) 
                for comb in combinations_chunk
            ], dtype=np.int8)

            # 홀수 개수 계산
            odd_counts = np.sum(chunk_arrays % 2 == 1, axis=1)
            even_counts = 6 - odd_counts
            
            # 홀수나 짝수가 6개인 조합 제외
            valid_mask = ~np.isin(odd_counts, excluded_counts) & ~np.isin(even_counts, excluded_counts)
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []