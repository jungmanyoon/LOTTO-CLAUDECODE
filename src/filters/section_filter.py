from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class SectionFilter(BaseFilter):
    """구간별 번호 분포 필터"""
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'max_numbers_per_section' not in self.criteria:
            raise ValueError("'max_numbers_per_section' 값이 필요합니다.")
            
        max_per_section = self.criteria['max_numbers_per_section']
        if not isinstance(max_per_section, int) or max_per_section < 2 or max_per_section > 6:
            raise ValueError("'max_numbers_per_section'는 2에서 6 사이의 정수여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"section 필터 진행률",
                max_numbers_per_section=self.criteria['max_numbers_per_section']
            )
        except Exception as e:
            logging.error(f"구간 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                    max_numbers_per_section: int) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            # 타입 체크 추가
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.int8)

            # 각 구간별 번호 개수 계산
            section1 = np.sum((chunk_arrays >= 1) & (chunk_arrays <= 15), axis=1)
            section2 = np.sum((chunk_arrays >= 16) & (chunk_arrays <= 30), axis=1)
            section3 = np.sum((chunk_arrays >= 31) & (chunk_arrays <= 45), axis=1)

            # 수정: 각 구간에서 6개 번호인 경우 제외
            valid_mask = (
                (section1 < 6) &  # 6개 모두 제외
                (section2 < 6) &  # 6개 모두 제외
                (section3 < 6) &  # 6개 모두 제외
                (section1 <= max_numbers_per_section) &
                (section2 <= max_numbers_per_section) &
                (section3 <= max_numbers_per_section)
            )

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            # 오류 시 입력 조합 보존하여 청크 전체 손실 방지 (필터 간 예외 정책 통일)
            return combinations_chunk