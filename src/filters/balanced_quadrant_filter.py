"""
Balanced Quadrant Filter - 사분면 균형 필터

로또 번호 1-45를 4개 사분면으로 나누고, 각 사분면의 번호 분포를 분석:
- Q1: 1-11 (11개)
- Q2: 12-22 (11개)
- Q3: 23-33 (11개)
- Q4: 34-45 (12개)
- 한 사분면에 max_per_quadrant개 이상 몰리는 조합 제외

이론적 근거:
1. 균등 분포 원리: 당첨번호는 전체 범위에 골고루 분포
2. 과거 데이터 분석: 한 사분면에 4개 이상 나오는 경우 드뭄 (약 15%)
3. 몰림 현상 방지: 특정 구간 집중을 피해 다양성 확보
4. 확률적 균형: 각 사분면에서 고르게 선택될 확률이 더 높음
"""

from typing import List, Dict, Any
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class BalancedQuadrantFilter(BaseFilter):
    """사분면 균형 필터

    1-45를 4개 사분면으로 나누고 각 사분면의 번호 개수를 제한
    """

    # 사분면 정의 (클래스 상수)
    QUADRANTS = {
        'Q1': (1, 11),    # 1-11
        'Q2': (12, 22),   # 12-22
        'Q3': (23, 33),   # 23-33
        'Q4': (34, 45)    # 34-45
    }

    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        """BalancedQuadrantFilter 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준값
                - max_per_quadrant: 한 사분면 최대 허용 개수 (기본값: 3)
        """
        super().__init__(db_manager, criteria)
        self.computation_cost = 1.0
        self.optimizer = FilterOptimizer(self._process_chunk_wrapper)

        # 과거 당첨번호 사분면 분포 분석 (참고용)
        self._analyze_historical_quadrants()

    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        # 기본값 설정
        if 'max_per_quadrant' not in self.criteria:
            self.criteria['max_per_quadrant'] = 3  # 최대 3개까지 허용

        # 유효성 검사
        max_per_quadrant = self.criteria['max_per_quadrant']
        if not isinstance(max_per_quadrant, int) or max_per_quadrant < 0 or max_per_quadrant > 6:
            raise ValueError("'max_per_quadrant'는 0에서 6 사이의 정수여야 합니다.")

        logging.info(
            f"[BalancedQuadrantFilter] 초기화 완료 - "
            f"max_per_quadrant: {max_per_quadrant}"
        )

    def _analyze_historical_quadrants(self) -> None:
        """과거 당첨번호의 사분면 분포 분석 (참고용)

        각 당첨 조합의 사분면별 개수를 분석하여 통계 산출
        """
        try:
            # 과거 당첨번호 가져오기
            winning_numbers = self.db_manager.get_all_winning_numbers()

            if not winning_numbers:
                logging.warning("[BalancedQuadrantFilter] 당첨번호 데이터 없음")
                self.avg_max_per_quadrant = 2.5  # 기본값
                return

            # 각 조합의 사분면 최대 개수 계산
            max_counts = []

            for nums in winning_numbers:
                if isinstance(nums, str):
                    numbers = list(map(int, nums.split(',')))
                else:
                    numbers = list(nums[:6])  # 보너스 제외

                # 각 사분면별 개수 계산
                quadrant_counts = self._count_by_quadrant(numbers)
                max_count = max(quadrant_counts.values())
                max_counts.append(max_count)

            # 통계 계산
            self.avg_max_per_quadrant = np.mean(max_counts)
            self.max_per_quadrant_historical = max(max_counts)

            # 분포 계산
            unique, counts = np.unique(max_counts, return_counts=True)
            distribution = dict(zip(unique, counts))
            total = len(max_counts)

            logging.info(
                f"[BalancedQuadrantFilter] 과거 당첨번호 분석 완료 - "
                f"평균 최대: {self.avg_max_per_quadrant:.2f}개/사분면, "
                f"역대 최대: {self.max_per_quadrant_historical}개"
            )

            # 분포 상세 로깅 (DEBUG)
            logging.debug(f"  사분면 최대 개수 분포:")
            for count, freq in sorted(distribution.items()):
                pct = (freq / total) * 100
                logging.debug(f"    {count}개: {freq}회 ({pct:.1f}%)")

        except Exception as e:
            logging.error(f"[BalancedQuadrantFilter] 통계 분석 실패: {e}")
            self.avg_max_per_quadrant = 2.5
            self.max_per_quadrant_historical = 4

    def _count_by_quadrant(self, numbers: List[int]) -> Dict[str, int]:
        """번호들을 사분면별로 개수 계산

        Args:
            numbers: 번호 리스트 (6개)

        Returns:
            Dict[str, int]: 각 사분면별 개수
        """
        counts = {'Q1': 0, 'Q2': 0, 'Q3': 0, 'Q4': 0}

        for num in numbers:
            if 1 <= num <= 11:
                counts['Q1'] += 1
            elif 12 <= num <= 22:
                counts['Q2'] += 1
            elif 23 <= num <= 33:
                counts['Q3'] += 1
            elif 34 <= num <= 45:
                counts['Q4'] += 1

        return counts

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용 - numpy 벡터화된 사분면 균형 검사

        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호

        Returns:
            List[str]: 필터링된 조합 목록
        """
        if not combinations:
            return []

        return self.optimizer.optimize_filter(
            combinations=combinations,
            desc="balanced_quadrant 필터 진행률",
            max_per_quadrant=self.criteria['max_per_quadrant']
        )

    @staticmethod
    def _process_chunk_wrapper(combinations_chunk: List[str], **kwargs) -> List[str]:
        """FilterOptimizer용 래퍼 함수"""
        return BalancedQuadrantFilter._process_chunk_vectorized(
            combinations_chunk,
            kwargs.get('max_per_quadrant', 3)
        )

    @staticmethod
    def _process_chunk_vectorized(combinations_chunk: List[str],
                                  max_per_quadrant: int) -> List[str]:
        """청크 단위 벡터화 필터링"""
        try:
            chunk_arrays = np.array(
                [list(map(int, c.split(','))) for c in combinations_chunk],
                dtype=np.int8
            )

            # 각 사분면 카운트 (벡터화)
            q1 = np.sum((chunk_arrays >= 1) & (chunk_arrays <= 11), axis=1)
            q2 = np.sum((chunk_arrays >= 12) & (chunk_arrays <= 22), axis=1)
            q3 = np.sum((chunk_arrays >= 23) & (chunk_arrays <= 33), axis=1)
            q4 = np.sum((chunk_arrays >= 34) & (chunk_arrays <= 45), axis=1)

            max_counts = np.maximum(np.maximum(q1, q2), np.maximum(q3, q4))
            valid = max_counts <= max_per_quadrant

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid[i]]

        except Exception as e:
            logging.error(f"[BalancedQuadrantFilter] 청크 처리 오류: {e}")
            return combinations_chunk

    def check_combination(self, combination: str, round_num: int) -> bool:
        """단일 조합이 필터 조건을 만족하는지 확인

        Args:
            combination: 검사할 조합
            round_num: 회차 번호

        Returns:
            bool: 조건 만족 여부 (True = 통과)
        """
        max_per_quadrant = self.criteria['max_per_quadrant']

        # 조합을 숫자 리스트로 변환
        numbers = list(map(int, combination.split(',')))

        # 사분면별 개수 계산
        quadrant_counts = self._count_by_quadrant(numbers)
        max_count = max(quadrant_counts.values())

        # 최대 개수가 허용 범위 내면 통과
        return max_count <= max_per_quadrant

    def supports_early_termination(self) -> bool:
        """조기 종료 전략 지원 여부

        Returns:
            bool: 지원 여부 (True)
        """
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """필터 통계 정보 반환

        Returns:
            Dict[str, Any]: 통계 정보
        """
        return {
            'max_per_quadrant': self.criteria['max_per_quadrant'],
            'avg_max_per_quadrant': getattr(self, 'avg_max_per_quadrant', 0.0),
            'max_per_quadrant_historical': getattr(self, 'max_per_quadrant_historical', 4),
            'quadrants': self.QUADRANTS,
            'method': 'quadrant_balance'
        }
