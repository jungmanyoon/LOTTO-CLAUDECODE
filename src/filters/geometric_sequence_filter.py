# src/filters/geometric_sequence_filter.py

from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class GeometricSequenceFilter(BaseFilter):
    """등비수열 패턴 필터"""
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        self.default_criteria = {
            'min_sequence': 4,
            'exclude_lengths': [4, 5, 6]
        }
        if criteria:
            self.default_criteria.update(criteria)
        super().__init__(db_manager, self.default_criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_sequence' not in self.criteria:
            raise ValueError("'min_sequence' 값이 필요합니다.")

        if 'exclude_lengths' not in self.criteria:
            raise ValueError("'exclude_lengths' 값이 필요합니다.")

        min_sequence = self.criteria['min_sequence']
        if not isinstance(min_sequence, int) or min_sequence < 3:
            raise ValueError("'min_sequence'는 3 이상의 정수여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"geometric_sequence 필터 진행률",
                min_sequence=self.criteria['min_sequence'],
                exclude_lengths=self.criteria['exclude_lengths']
            )
        except Exception as e:
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"등비수열 필터링 중 오류 발생: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], **kwargs) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            min_sequence = kwargs.get('min_sequence', 4)
            exclude_lengths = kwargs.get('exclude_lengths', [4, 5, 6])

            filtered_combinations = []
            
            for comb in combinations_chunk:
                # 타입 체크 추가
                if isinstance(comb, str):
                    numbers = sorted(list(map(int, comb.split(','))))
                else:
                    numbers = sorted(comb)
                max_sequence = GeometricSequenceFilter._find_geometric_sequence_static(numbers)
                
                # 제거 조건 (둘 중 하나라도 해당하면 제거):
                # 1) max_sequence >= min_sequence: 강한 등비수열 패턴 보유
                # 2) max_sequence in exclude_lengths: 명시적 제외 길이 목록에 해당
                # 버그 수정: 기존 AND 조건(< min_sequence AND not in exclude_lengths)은
                # exclude_lengths에 >= min_sequence 값(기본값 [4,5,6])이 있을 때
                # max_sequence=4인 경우 첫 조건 False로 인해 필터를 통과해 버리는 문제 발생
                # OR 제거 조건으로 변경하여 exclude_lengths 독립 동작 보장
                should_exclude = (max_sequence >= min_sequence) or (max_sequence in exclude_lengths)
                if not should_exclude:
                    filtered_combinations.append(comb)

            return filtered_combinations

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}", exc_info=True)
            # 오류 발생 시 입력 조합을 그대로 반환하여 청크 전체 손실 방지
            return combinations_chunk
        
    @staticmethod
    def _find_geometric_sequence_static(numbers: List[int]) -> int:
        """정적 메서드로 구현된 등비수열 찾기"""
        n = len(numbers)
        max_length = 0

        for i in range(n-2):
            for j in range(i+1, n-1):
                if numbers[i] == 0:  # 0은 등비수열에서 제외
                    continue
                    
                ratio = numbers[j] / numbers[i]
                if not ratio.is_integer():  # 정수 비율만 고려
                    continue
                    
                current_length = 2
                last = numbers[j]
                
                for k in range(j+1, n):
                    next_term = last * ratio
                    if next_term > 45:  # 로또 번호 범위 초과
                        break
                    if numbers[k] == next_term:
                        current_length += 1
                        last = numbers[k]
                
                max_length = max(max_length, current_length)

        return max_length