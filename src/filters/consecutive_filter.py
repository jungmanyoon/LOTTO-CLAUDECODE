
from typing import Any, List, Dict, Tuple
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer
from ..utils.constants import LottoConstants

class ConsecutiveFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        # 중앙 관리되는 기본 기준값 사용
        self.default_criteria = LottoConstants.FilterCriteria.CONSECUTIVE['default_criteria']
        
        # 기본값과 전달받은 기준값 병합
        if criteria:
            self.default_criteria.update(criteria)
        super().__init__(db_manager, self.default_criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'max_consecutive' not in self.criteria:
            raise ValueError("'max_consecutive' 값이 필요합니다.")
        if 'min_gap' not in self.criteria:  # 추가: min_gap 검사
            raise ValueError("'min_gap' 값이 필요합니다.")
            
        max_consecutive = self.criteria['max_consecutive']
        min_gap = self.criteria['min_gap']  # 추가: min_gap 값 가져오기
        
        if not isinstance(max_consecutive, int) or max_consecutive < 2:
            raise ValueError("'max_consecutive'는 2 이상의 정수여야 합니다.")
        if not isinstance(min_gap, int) or min_gap < 1:  # 추가: min_gap 유효성 검사
            raise ValueError("'min_gap'는 1 이상의 정수여야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"consecutive 필터 진행률",
                max_consecutive=self.criteria['max_consecutive'],
                min_gap=self.criteria['min_gap']  # 추가: min_gap 전달
            )
        except Exception as e:
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"연속 번호 필터링 중 오류 발생: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      max_consecutive: int,
                      min_gap: int) -> List[str]:
        """청크 단위 필터링 처리 (완전 벡터화)"""
        try:
            # 타입 체크 추가
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)

            chunk_arrays = np.array(converted_chunks, dtype=np.int8)

            # 정렬된 배열 생성
            sorted_arrays = np.sort(chunk_arrays, axis=1)

            # 연속된 번호 검사 - 완전 벡터화
            diffs = np.diff(sorted_arrays, axis=1)

            # 벡터화된 연속 카운트 계산 (컬럼 반복 = 5회만, 행 반복 아님)
            n_rows = len(chunk_arrays)
            max_consecutive_counts = np.ones(n_rows, dtype=np.int8)
            current_consecutive = np.ones(n_rows, dtype=np.int8)

            # 5개 컬럼만 반복 (수백만 행 반복 대신)
            for col in range(diffs.shape[1]):
                is_one = (diffs[:, col] == 1)
                current_consecutive = np.where(is_one, current_consecutive + 1, 1)
                max_consecutive_counts = np.maximum(max_consecutive_counts, current_consecutive)

            # 최소 간격 검사 (이미 벡터화됨)
            min_gaps = np.min(diffs, axis=1)

            # 조건을 만족하는 조합 선택
            valid_mask = (
                (max_consecutive_counts < max_consecutive) &
                (min_gaps >= min_gap)
            )

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            # 오류 시 입력 조합 보존하여 청크 전체 손실 방지 (필터 간 예외 정책 통일)
            return combinations_chunk

    # @deprecated - 분석 목적으로만 유지됨. 실제 필터링에는 _process_chunk 사용
    def _get_max_consecutive(self, numbers: List[int]) -> int:
        """가장 긴 연속 번호 개수 계산
        
        Args:
            numbers: 정렬된 번호 리스트
            
        Returns:
            int: 최대 연속 번호 개수
        """
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(numbers)):
            if numbers[i] == numbers[i-1] + 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
                
        return max_consecutive

    def _check_number_gaps(self, numbers: List[int], min_gap: int) -> bool:
        """번호 간의 간격이 기준을 충족하는지 검사
        
        Args:
            numbers: 정렬된 번호 리스트
            min_gap: 최소 간격
            
        Returns:
            bool: 간격 충족 여부
        """
        for i in range(1, len(numbers)):
            if numbers[i] - numbers[i-1] < min_gap:
                return False
        return True

    def get_consecutive_statistics(self, combinations: List[str]) -> Dict[int, float]:
        """조합 목록의 연속 번호 통계 계산
        
        Args:
            combinations: 분석할 조합 목록
            
        Returns:
            Dict[int, float]: 연속 번호 개수별 비율
        """
        try:
            pattern_counts = {i: 0 for i in range(1, 7)}
            total = len(combinations)
            
            for comb in combinations:
                if isinstance(comb, str):
                    numbers = sorted(map(int, comb.split(',')))
                else:
                    numbers = sorted(comb)
                max_consecutive = self._get_max_consecutive(numbers)
                pattern_counts[max_consecutive] += 1
                
            return {
                k: (v / total * 100)
                for k, v in pattern_counts.items()
            }
            
        except Exception as e:
            logging.error(f"연속 번호 통계 계산 중 오류 발생: {str(e)}")
            return {}

    def find_consecutive_sequences(self, numbers: List[int]) -> List[Tuple[int, int]]:
        """연속된 번호 시퀀스 찾기
        
        Args:
            numbers: 검사할 번호 리스트
            
        Returns:
            List[Tuple[int, int]]: (시작 번호, 연속 개수) 목록
        """
        if not numbers:
            return []
            
        sorted_numbers = sorted(numbers)
        sequences = []
        start = sorted_numbers[0]
        length = 1
        
        for i in range(1, len(sorted_numbers)):
            if sorted_numbers[i] == sorted_numbers[i-1] + 1:
                length += 1
            else:
                if length > 1:
                    sequences.append((start, length))
                start = sorted_numbers[i]
                length = 1
                
        if length > 1:
            sequences.append((start, length))
            
        return sequences

    def analyze_combination(self, combination: str) -> Dict:
        """단일 조합의 연속 번호 패턴 상세 분석
        
        Args:
            combination: 분석할 번호 조합
            
        Returns:
            Dict: 분석 결과
        """
        try:
            if isinstance(combination, str):
                numbers = list(map(int, combination.split(',')))
            else:
                numbers = combination
            sequences = self.find_consecutive_sequences(numbers)
            
            return {
                'max_consecutive': self._get_max_consecutive(sorted(numbers)),
                'sequences': [
                    {
                        'start': seq[0],
                        'length': seq[1],
                        'numbers': list(range(seq[0], seq[0] + seq[1]))
                    }
                    for seq in sequences
                ],
                'total_consecutive_numbers': sum(seq[1] for seq in sequences),
                'gaps': [
                    numbers[i] - numbers[i-1]
                    for i in range(1, len(numbers))
                ],
                'min_gap': min(numbers[i] - numbers[i-1] for i in range(1, len(numbers)))
            }
            
        except Exception as e:
            logging.error(f"조합 분석 중 오류 발생: {str(e)}")
            return {}

    def suggest_criteria(self, winning_numbers: List[str], percentile: float = 75) -> Dict:
        """과거 당첨 번호를 기반으로 필터링 기준 제안
        
        Args:
            winning_numbers: 과거 당첨 번호 목록
            percentile: 기준으로 사용할 백분위수
            
        Returns:
            Dict: 제안된 필터링 기준
        """
        try:
            consecutive_counts = []
            min_gaps = []
            
            for numbers_str in winning_numbers:
                if isinstance(numbers_str, str):
                    numbers = sorted(map(int, numbers_str.split(',')))
                else:
                    numbers = sorted(numbers_str)
                consecutive_counts.append(self._get_max_consecutive(numbers))
                min_gaps.extend(
                    numbers[i] - numbers[i-1]
                    for i in range(1, len(numbers))
                )
            
            from numpy import percentile as np_percentile
            suggested_max_consecutive = int(np_percentile(consecutive_counts, percentile))
            suggested_min_gap = max(1, int(np_percentile(min_gaps, 100 - percentile)))
            
            return {
                'max_consecutive': suggested_max_consecutive,
                'min_gap': suggested_min_gap,
                'analysis': {
                    'max_consecutive_distribution': {
                        count: (consecutive_counts.count(count) / len(consecutive_counts) * 100)
                        for count in set(consecutive_counts)
                    },
                    'gap_statistics': {
                        'min': min(min_gaps),
                        'max': max(min_gaps),
                        'average': sum(min_gaps) / len(min_gaps)
                    }
                }
            }
            
        except Exception as e:
            logging.error(f"필터링 기준 제안 중 오류 발생: {str(e)}")
            return {
                'max_consecutive': 3,  # 기본값
                'min_gap': 1
            }