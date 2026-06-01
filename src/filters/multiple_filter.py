from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class MultipleFilter(BaseFilter):
    """배수 패턴 필터
    
    특정 수의 배수가 몇 개 포함되어 있는지를 기준으로 필터링합니다.
    """
    
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'multiples' not in self.criteria:
            raise ValueError("'multiples' 설정이 필요합니다.")
            
        multiples = self.criteria['multiples']
        if not isinstance(multiples, dict):
            raise ValueError("'multiples'는 딕셔너리 형태여야 합니다.")
            
        for base, limits in multiples.items():
            if not isinstance(base, int) or base < 2:
                raise ValueError(f"배수 기준값({base})은 2 이상의 정수여야 합니다.")
            if not isinstance(limits, (list, tuple)) or len(limits) != 2:
                raise ValueError(f"배수 제한({limits})은 [최소값, 최대값] 형태여야 합니다.")
            
            # 수정: 각 배수별 최대 가능 개수 검증 추가
            max_possible = len([n for n in range(1, 46) if n % base == 0])
            if limits[1] > max_possible:
                raise ValueError(f"{base}의 배수는 1-45 사이에 {max_possible}개만 존재합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="배수 패턴 필터링 진행률",
                multiples=self.criteria['multiples']
            )
        except Exception as e:
            logging.error(f"배수 패턴 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      multiples: Dict[int, List[int]]) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            # 타입 체크 추가
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.int16)

            valid_indices = np.ones(len(combinations_chunk), dtype=bool)

            # 각 배수별로 검사
            for base, (min_count, max_count) in multiples.items():
                # 수정: 1-45 사이의 유효한 배수만 검사
                valid_multiples = set(n for n in range(1, 46) if n % base == 0)
                # 각 조합에서 유효한 배수의 개수 계산
                multiple_counts = np.sum(
                    np.isin(chunk_arrays, list(valid_multiples)), 
                    axis=1
                )
                # 조건을 만족하지 않는 조합 제외
                valid_indices &= (multiple_counts >= min_count) & (multiple_counts <= max_count)

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_indices[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            # 오류 시 입력 조합 보존하여 청크 전체 손실 방지 (필터 간 예외 정책 통일)
            return combinations_chunk

    def calculate_multiple_statistics(self, winning_numbers: List[str]) -> Dict[int, Dict[int, float]]:
        """당첨 번호의 배수 통계 계산"""
        try:
            stats = {}
            total = len(winning_numbers)
            
            for base in [2, 3, 4, 5]:  # 분석할 배수들
                # 1-45 사이의 유효한 배수 개수 계산
                max_possible = len([n for n in range(1, 46) if n % base == 0])
                count_distribution = {i: 0 for i in range(max_possible + 1)}  # 0부터 최대 가능 개수까지
                
                for numbers_str in winning_numbers:
                    if isinstance(numbers_str, str):
                        numbers = list(map(int, numbers_str.split(',')))
                    else:
                        numbers = numbers_str
                    valid_multiples = [n for n in range(1, 46) if n % base == 0]
                    multiple_count = sum(1 for n in numbers if n in valid_multiples)
                    count_distribution[multiple_count] += 1
                
                # 오름차순 정렬된 통계 반환
                sorted_stats = {}
                for count in sorted(count_distribution.keys()):
                    frequency = count_distribution[count]
                    if frequency > 0:  # 빈도가 0인 경우 제외
                        percentage = (frequency / total * 100)
                        sorted_stats[count] = percentage
                
                stats[base] = sorted_stats
                
            return stats
            
        except Exception as e:
            logging.error(f"배수 통계 계산 중 오류 발생: {str(e)}")
            return {}