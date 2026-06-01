# src/filters/ten_section_filter.py

from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class TenSectionFilter(BaseFilter):
    """10구간 분포 필터"""
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'section_limits' not in self.criteria:
            raise ValueError("'section_limits' 값이 필요합니다.")
            
        section_limits = self.criteria['section_limits']
        required_sections = ['section1', 'section2', 'section3', 'section4', 'section5']
        
        for section in required_sections:
            if section not in section_limits:
                raise ValueError(f"'{section}' 구간 제한이 필요합니다.")
            if not isinstance(section_limits[section], list):
                raise ValueError(f"'{section}' 구간 제한은 리스트여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"ten_section 필터 진행률",
                section_limits=self.criteria['section_limits']
            )
        except Exception as e:
            logging.error(f"10구간 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                    section_limits: Dict[str, List[int]]) -> List[str]:
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

            # 각 10구간별 번호 개수 계산
            sections = {
                'section1': np.sum((chunk_arrays >= 1) & (chunk_arrays <= 10), axis=1),
                'section2': np.sum((chunk_arrays >= 11) & (chunk_arrays <= 20), axis=1),
                'section3': np.sum((chunk_arrays >= 21) & (chunk_arrays <= 30), axis=1),
                'section4': np.sum((chunk_arrays >= 31) & (chunk_arrays <= 40), axis=1),
                'section5': np.sum((chunk_arrays >= 41) & (chunk_arrays <= 45), axis=1)
            }

            # 각 구간별 제한 조건 검사
            valid_mask = np.ones(len(combinations_chunk), dtype=bool)
            for section_name, counts in sections.items():
                excluded = section_limits[section_name]
                # ✓ 수정: 특정 값 제외 로직으로 변경
                if excluded:
                    section_mask = ~np.isin(counts, excluded)
                else:
                    section_mask = np.ones(len(counts), dtype=bool)
                valid_mask &= section_mask

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            # 오류 시 입력 조합 보존하여 청크 전체 손실 방지 (필터 간 예외 정책 통일)
            return combinations_chunk