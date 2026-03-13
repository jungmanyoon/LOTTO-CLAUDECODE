from typing import Any, List, Dict, Set
import logging

import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class MatchFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        # FilterOptimizer에 전달할 래퍼 함수 생성
        self.optimizer = FilterOptimizer(self._process_chunk_wrapper)
                           
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'max_match' not in self.criteria:
            raise ValueError("'max_match' 값이 필요합니다.")
            
        max_match = self.criteria['max_match']
        if not isinstance(max_match, int) or max_match < 0 or max_match > 6:
            raise ValueError("'max_match'는 0에서 6 사이의 정수여야 합니다.")
        
        # 확률 분포 정보가 있으면 로그 출력
        if 'distribution' in self.criteria:
            dist = self.criteria['distribution']
            logging.info(f"[Match 필터] 확률 기반 설정 - max_match: {max_match}")
            if dist:
                for match_count, percentage in dist.items():
                    logging.debug(f"  {match_count}개 일치: {percentage:.2f}%")

    def apply_filter(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용 (시계열 고려 버전)
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            # 백테스팅 모드: round_num이 지정된 경우 해당 회차 이전 번호만 사용
            if round_num and round_num > 0:
                # 시계열을 고려하여 해당 회차 이전의 당첨번호만 가져오기
                if hasattr(self.db_manager, 'get_winning_numbers_before'):
                    winning_numbers = self.db_manager.get_winning_numbers_before(round_num)
                    # DEBUG 로그 제거 - 반복적이고 불필요함
                else:
                    # 폴백: 메서드가 없으면 전체 당첨번호 사용 (기존 방식)
                    logging.warning("get_winning_numbers_before 메서드가 없어 전체 당첨번호 사용")
                    winning_numbers = self.db_manager.get_all_winning_numbers()
            else:
                # 일반 모드: 모든 당첨번호 사용
                winning_numbers = self.db_manager.get_all_winning_numbers()
                # DEBUG 로그 제거 - 반복적이고 불필요함
                
            if not winning_numbers:
                logging.warning("참고할 당첨 번호가 없습니다.")
                return combinations

            # 당첨 번호 배열 미리 생성 (타입 체크 추가)
            converted_winning = []
            for nums in winning_numbers:
                if isinstance(nums, str):
                    converted_winning.append(list(map(int, nums.split(','))))
                else:
                    converted_winning.append(nums)
            
            winning_arrays = np.array(converted_winning, dtype=np.int8)

            # 최적화된 청크 단위 처리 (모든 max_match 값에 동일하게 적용)
            # NOTE: max_match=6이면 완전 일치만 제외 (실질적으로 필터링 거의 없음)
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="match 필터 진행률",
                winning_arrays=winning_arrays,
                max_match=self.criteria['max_match']
            )

        except Exception as e:
            logging.error(f"번호 일치 필터링 중 오류 발생: {str(e)}")
            return combinations

    # 기존 apply 메서드 유지
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        # apply_filter 메서드 호출하여 동일한 기능 유지
        return self.apply_filter(combinations, round_num)
    
    @staticmethod
    def _process_chunk_wrapper(combinations_chunk: List[str], **kwargs) -> List[str]:
        """FilterOptimizer용 래퍼 함수 - 키워드 인수를 위치 인수로 변환

        PERF-003: 청크 단위 로깅 제거 (성능 최적화)
        """
        winning_arrays = kwargs.get('winning_arrays')
        max_match = kwargs.get('max_match')
        # PERF-003: 반복 호출되는 DEBUG 로그 제거
        return MatchFilter._process_chunk(combinations_chunk, winning_arrays, max_match)

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      winning_arrays: np.ndarray = None,
                      max_match: int = None,
                      **kwargs) -> List[str]:
        """청크 단위 필터링 처리 (numpy 벡터화)

        np.isin 벡터화로 Python 이중 루프 제거 → ~100x 속도 향상
        """
        try:
            if winning_arrays is None or max_match is None:
                logging.error("_process_chunk: 필수 매개변수 누락")
                return combinations_chunk

            # 배열 변환
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)

            chunk_arrays = np.array(converted_chunks, dtype=np.int8)

            # numpy 벡터화: 각 당첨번호에 대해 일치 수 계산
            max_matches = np.zeros(len(chunk_arrays), dtype=np.int8)
            for win_nums in winning_arrays:
                # np.isin: chunk_arrays의 각 원소가 win_nums에 포함되는지 (N,6) boolean
                matches_per_combo = np.sum(np.isin(chunk_arrays, win_nums), axis=1).astype(np.int8)
                np.maximum(max_matches, matches_per_combo, out=max_matches)

            valid_indices = max_matches < max_match

            return [
                combinations_chunk[i]
                for i in range(len(combinations_chunk))
                if valid_indices[i]
            ]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return combinations_chunk