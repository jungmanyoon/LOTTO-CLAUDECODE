"""
AC값(Arithmetic Complexity) 필터

AC값은 6개 숫자 간의 모든 차이 중 고유한 값의 개수를 기반으로 산출됩니다.
공식: AC = D - 5 (D = 고유 차이값 개수)

- 6개 숫자로 만들 수 있는 쌍의 개수: C(6,2) = 15개
- AC값 범위: 0 ~ 10
- 권장 범위: 7 ~ 10 (무작위성이 높은 조합)
- 제외 대상: 0 ~ 6 (인간적 패턴, 등차수열 등)

참고: 검토사항.txt의 "산술 복잡도(AC값)" 권장사항 기반 구현
"""

from typing import Any, List, Dict, Set
import logging
import numpy as np
from itertools import combinations as iter_combinations
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class ACValueFilter(BaseFilter):
    """
    AC값(Arithmetic Complexity) 기반 필터

    무작위성이 결여된 조합(낮은 AC값)을 필터링하여
    통계적으로 더 가능성 있는 조합만 남김
    """

    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        """
        AC값 필터 초기화

        Args:
            db_manager: 데이터베이스 매니저
            criteria: 필터 기준
                - min_ac: 최소 AC값 (기본: 7)
                - max_ac: 최대 AC값 (기본: 10)
                - use_scoring: 점수화 모드 사용 여부 (기본: False)
        """
        # 기본 기준값 설정
        self.default_criteria = {
            'min_ac': 7,      # 최소 AC값 (7 이상 권장)
            'max_ac': 10,     # 최대 AC값
            'use_scoring': False  # 점수화 모드 (Phase 2에서 활용)
        }

        if criteria:
            self.default_criteria.update(criteria)

        # 부모 클래스 초기화
        super().__init__(db_manager, self.default_criteria)

        # 최적화기 초기화
        self.optimizer = FilterOptimizer(self._process_chunk)

        # 계산 비용 설정 (중간 수준)
        self.computation_cost = 1.2

        logging.info(f"[ACValue] 필터 초기화: AC값 범위 {self._criteria['min_ac']}-{self._criteria['max_ac']}")

    def _validate_criteria(self) -> None:
        """기준값 유효성 검증"""
        min_ac = self._criteria.get('min_ac')
        max_ac = self._criteria.get('max_ac')

        if min_ac is None or max_ac is None:
            raise ValueError("'min_ac'와 'max_ac' 값이 모두 필요합니다.")

        if not isinstance(min_ac, (int, float)) or not isinstance(max_ac, (int, float)):
            raise ValueError("AC값 범위는 숫자여야 합니다.")

        if min_ac < 0 or max_ac > 10:
            raise ValueError("AC값 범위는 0-10 사이여야 합니다.")

        if min_ac > max_ac:
            raise ValueError("최소값이 최대값보다 작거나 같아야 합니다.")

    @staticmethod
    def calculate_ac_value(numbers: List[int]) -> int:
        """
        6개 숫자의 AC값 계산

        AC = D - 5
        D = 15개 숫자 쌍의 차이 중 고유한 값의 개수

        Args:
            numbers: 6개의 로또 번호 리스트

        Returns:
            AC값 (0-10 범위)
        """
        if len(numbers) != 6:
            raise ValueError("6개의 숫자가 필요합니다.")

        # 모든 쌍의 차이 계산 (15개)
        differences: Set[int] = set()
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                diff = abs(numbers[j] - numbers[i])
                differences.add(diff)

        # AC = D - 5 (D = 고유 차이값 개수)
        d = len(differences)
        ac = d - 5

        return ac

    @staticmethod
    def calculate_ac_value_vectorized(numbers_array: np.ndarray) -> np.ndarray:
        """
        벡터화된 AC값 계산 (대량 처리용)

        Args:
            numbers_array: (N, 6) 형태의 numpy 배열

        Returns:
            (N,) 형태의 AC값 배열
        """
        n_combinations = numbers_array.shape[0]
        ac_values = np.zeros(n_combinations, dtype=np.int8)

        # 각 조합에 대해 AC값 계산
        for idx in range(n_combinations):
            numbers = numbers_array[idx]
            differences = set()

            # 15개 쌍의 차이 계산
            for i in range(6):
                for j in range(i + 1, 6):
                    diff = abs(int(numbers[j]) - int(numbers[i]))
                    differences.add(diff)

            # AC = D - 5
            ac_values[idx] = len(differences) - 5

        return ac_values

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """
        AC값 필터 적용

        Args:
            combinations: 필터링할 조합 리스트
            round_num: 현재 회차

        Returns:
            필터링된 조합 리스트
        """
        if not combinations:
            return combinations

        try:
            filtered = self.optimizer.optimize_filter(
                combinations=combinations,
                desc="AC값 필터 진행률",
                min_ac=self._criteria['min_ac'],
                max_ac=self._criteria['max_ac']
            )

            excluded_count = len(combinations) - len(filtered)
            if len(combinations) > 1000:
                exclusion_rate = (excluded_count / len(combinations)) * 100
                logging.info(
                    f"[ACValue] 완료: {len(filtered):,}/{len(combinations):,}개 "
                    f"(제외율: {exclusion_rate:.1f}%, AC범위: {self._criteria['min_ac']}-{self._criteria['max_ac']})"
                )

            return filtered

        except Exception as e:
            logging.error(f"AC값 필터링 중 오류: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], min_ac: int, max_ac: int) -> List[str]:
        """
        청크 단위 AC값 필터링 처리

        Args:
            combinations_chunk: 처리할 조합 청크
            min_ac: 최소 AC값
            max_ac: 최대 AC값

        Returns:
            유효한 조합 리스트
        """
        try:
            if not combinations_chunk:
                return []

            # 문자열을 숫자 배열로 변환
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(list(comb))

            chunk_arrays = np.array(converted_chunks, dtype=np.int8)

            # 벡터화된 AC값 계산
            ac_values = ACValueFilter.calculate_ac_value_vectorized(chunk_arrays)

            # 유효 범위 필터링
            valid_mask = (ac_values >= min_ac) & (ac_values <= max_ac)

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"AC값 청크 처리 중 오류: {str(e)}")
            return []

    def get_ac_score(self, numbers: List[int]) -> float:
        """
        AC값 기반 점수 반환 (점수화 시스템용)

        Args:
            numbers: 6개의 로또 번호

        Returns:
            0-100 범위의 점수
        """
        ac = self.calculate_ac_value(numbers)

        # AC값별 점수 매핑
        score_map = {
            0: 0,    # 극히 희박
            1: 5,
            2: 10,
            3: 15,
            4: 20,
            5: 30,   # 낮음
            6: 50,   # 가중치 하향
            7: 70,   # 보통
            8: 85,   # 높음
            9: 95,   # 매우 높음
            10: 100  # 최적
        }

        return score_map.get(ac, 50)

    def analyze_historical_ac_distribution(self) -> Dict[int, int]:
        """
        역대 당첨번호의 AC값 분포 분석

        Returns:
            AC값별 출현 횟수 딕셔너리
        """
        try:
            winning_numbers = self.db_manager.get_all_winning_numbers()

            ac_distribution = {i: 0 for i in range(11)}

            for numbers in winning_numbers:
                if len(numbers) >= 6:
                    # 보너스 번호 제외하고 6개만 사용
                    main_numbers = list(numbers[:6])
                    ac = self.calculate_ac_value(main_numbers)
                    ac_distribution[ac] += 1

            total = sum(ac_distribution.values())

            logging.info("[ACValue] 역대 당첨번호 AC값 분포:")
            for ac, count in sorted(ac_distribution.items()):
                if count > 0:
                    percentage = (count / total) * 100
                    logging.info(f"  AC={ac}: {count}회 ({percentage:.1f}%)")

            return ac_distribution

        except Exception as e:
            logging.error(f"AC값 분포 분석 중 오류: {str(e)}")
            return {}


# 모듈 테스트용 코드
if __name__ == "__main__":
    # AC값 계산 테스트
    test_cases = [
        ([1, 2, 3, 4, 5, 6], "등차수열 - 낮은 AC"),
        ([5, 10, 15, 20, 25, 30], "5 간격 등차 - 낮은 AC"),
        ([3, 17, 25, 31, 38, 44], "무작위 패턴 - 높은 AC"),
        ([7, 14, 21, 28, 35, 42], "7배수 - 낮은 AC"),
    ]

    print("AC값 계산 테스트:")
    print("-" * 50)

    for numbers, description in test_cases:
        ac = ACValueFilter.calculate_ac_value(numbers)
        print(f"{numbers} -> AC={ac} ({description})")

    print("-" * 50)
    print("AC값 범위: 0-10")
    print("권장 범위: 7-10 (무작위성이 높은 조합)")
