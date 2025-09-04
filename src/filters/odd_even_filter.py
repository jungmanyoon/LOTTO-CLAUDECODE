from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer
from ..utils.constants import LottoConstants

class OddEvenFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        # 기본 기준값: 홀수/짝수 0개 또는 6개인 조합 제외 (0% 패턴)
        self.default_criteria = {'excluded_counts': [0, 6]}
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
            # DEBUG 로그 제거 - 반복적이고 불필요함
            
            filtered = self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"홀짝 필터 진행률",
                excluded_counts=self.criteria['excluded_counts']
            )
            
            excluded_count = len(combinations) - len(filtered)
            # 대량 처리 시에만 로그 출력 (1000개 이상)
            if len(combinations) > 1000:
                logging.info(f"[OddEven] 홀짝 필터 완료: {len(filtered):,}/{len(combinations):,}개 남음 ({excluded_count:,}개 제외됨)")
            
            # 샘플 로그는 개발 디버깅 시에만 필요하므로 제거
            
            return filtered
        except Exception as e:
            logging.error(f"홀짝 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], excluded_counts: List[int]) -> List[str]:
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

            # 홀수 개수 계산
            odd_counts = np.sum(chunk_arrays % 2 == 1, axis=1)
            even_counts = 6 - odd_counts
            
            # 홀수나 짝수가 6개인 조합 제외
            valid_mask = ~np.isin(odd_counts, excluded_counts) & ~np.isin(even_counts, excluded_counts)
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return []