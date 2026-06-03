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

            max_match = self.criteria['max_match']

            # 조기 분기: max_match >= 6 이면 "6개 모두 일치(완전 일치)"한 조합만 제외 대상이다.
            # 이때는 8.14M x 당첨번호 전수 numpy 루프가 불필요하므로, 과거 당첨번호와의
            # 완전 일치 여부만 set 멤버십으로 단축 처리한다(수십초 -> 1초 미만).
            # NOTE: max_match < 6 일 때는 기존 numpy 청크 처리 경로를 그대로 사용한다(동작 보존).
            if max_match >= 6:
                return self._exclude_exact_matches(combinations, converted_winning)

            winning_arrays = np.array(converted_winning, dtype=np.int8)

            # 최적화된 청크 단위 처리 (max_match < 6 인 경우)
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="match 필터 진행률",
                winning_arrays=winning_arrays,
                max_match=max_match
            )

        except Exception as e:
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"번호 일치 필터링 중 오류 발생: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations

    # 기존 apply 메서드 유지
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        # apply_filter 메서드 호출하여 동일한 기능 유지
        return self.apply_filter(combinations, round_num)

    @staticmethod
    def _exclude_exact_matches(combinations: List[str],
                               converted_winning: List[List[int]]) -> List[str]:
        """max_match >= 6 전용 단축 경로: 과거 당첨번호와 6개 모두 일치하는 조합만 제외

        기존 numpy 경로(max_match=6)는 각 조합이 임의의 당첨번호와 공유하는 번호 수의
        최대값이 6(=완전 일치)인 경우만 제외한다. 로또 번호는 6개 모두 서로 다르므로
        "6개 공유 = 집합 동일"이다. 따라서 순서 무관 set 멤버십으로 동일 결과를 낸다.

        Args:
            combinations: 필터링할 조합 목록 (str "1,2,..." 또는 정수 리스트)
            converted_winning: 정수 리스트로 변환된 과거 당첨번호 목록

        Returns:
            List[str]: 완전 일치 조합을 제외한 목록
        """
        # 과거 당첨번호를 frozenset 집합으로 구성 (순서 무관 비교용)
        winning_sets: Set[frozenset] = {frozenset(nums) for nums in converted_winning}

        filtered: List[str] = []
        for comb in combinations:
            if isinstance(comb, str):
                comb_set = frozenset(map(int, comb.split(',')))
            else:
                comb_set = frozenset(comb)
            # 과거 당첨번호와 완전히 동일한 조합만 제외
            if comb_set not in winning_sets:
                filtered.append(comb)

        return filtered
    
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