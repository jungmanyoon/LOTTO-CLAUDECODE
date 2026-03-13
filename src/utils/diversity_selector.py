"""
Maximum Diversity Selection - 풀 내 최대 다양성 조합 선택

필터링된 조합 풀에서 서로 가장 다른 N개의 조합을 선택하여
커버리지를 극대화합니다.

알고리즘: Greedy Farthest-Point Sampling
1. 시작점 하나를 랜덤 선택
2. 기존 선택된 조합들로부터 가장 먼 조합을 다음으로 추가
3. N개가 될 때까지 반복
"""

import logging
import random
from typing import List, Set, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)


class DiversitySelector:
    """풀 내 최대 다양성 조합 선택기"""

    def __init__(self, seed: Optional[int] = None):
        """
        Args:
            seed: 랜덤 시드 (재현성 위해, None이면 시간 기반)
        """
        self.rng = random.Random(seed)

    @staticmethod
    def _parse_combination(combo_str: str) -> Set[int]:
        """조합 문자열을 정수 set으로 변환"""
        return set(int(x) for x in combo_str.split(','))

    @staticmethod
    def _hamming_distance(combo1: Set[int], combo2: Set[int]) -> int:
        """두 조합 간의 해밍 거리 (비공통 번호 수)

        범위: 0 (동일) ~ 12 (완전히 다름)
        """
        return len(combo1 ^ combo2)  # 대칭차집합 크기

    def select_diverse(
        self,
        pool: List[str],
        n_select: int = 5,
        existing: Optional[List[List[int]]] = None
    ) -> List[str]:
        """풀에서 서로 가장 다른 n_select개 조합 선택

        Greedy Farthest-Point Sampling 알고리즘 사용

        Args:
            pool: 필터링된 조합 리스트 ("1,2,3,4,5,6" 형태)
            n_select: 선택할 조합 수
            existing: 이미 선택된 조합들 (이것들과도 다양해야 함)

        Returns:
            선택된 조합 문자열 리스트
        """
        if not pool:
            return []

        if n_select >= len(pool):
            return pool[:n_select]

        # 풀을 set으로 파싱
        pool_sets = [self._parse_combination(c) for c in pool]

        # 이미 선택된 조합이 있으면 포함
        selected_indices = []
        selected_sets = []

        if existing:
            for nums in existing:
                selected_sets.append(set(nums))

        # 시작점: 이미 선택된 것이 없으면 랜덤 하나 선택
        if not selected_sets:
            start_idx = self.rng.randint(0, len(pool) - 1)
            selected_indices.append(start_idx)
            selected_sets.append(pool_sets[start_idx])

        # 나머지 선택: 기존 선택과 가장 먼 것 추가
        remaining_needed = n_select - len(selected_indices)

        for _ in range(remaining_needed):
            best_idx = -1
            best_min_dist = -1

            for i, combo_set in enumerate(pool_sets):
                if i in selected_indices:
                    continue

                # 기존 선택 모두와의 최소 거리 계산
                min_dist = min(
                    self._hamming_distance(combo_set, sel)
                    for sel in selected_sets
                )

                # 최소 거리가 가장 큰 것 선택 (maximin 기준)
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = i

            if best_idx >= 0:
                selected_indices.append(best_idx)
                selected_sets.append(pool_sets[best_idx])
            else:
                break

        return [pool[i] for i in selected_indices]

    def calculate_diversity_score(self, combinations: List[str]) -> float:
        """조합 집합의 다양성 점수 계산

        Args:
            combinations: 조합 문자열 리스트

        Returns:
            0-100 범위의 다양성 점수
            - 100: 모든 조합이 완전히 다름
            - 0: 모든 조합이 동일
        """
        if len(combinations) < 2:
            return 100.0

        combo_sets = [self._parse_combination(c) for c in combinations]
        distances = []

        for i in range(len(combo_sets)):
            for j in range(i + 1, len(combo_sets)):
                distances.append(self._hamming_distance(combo_sets[i], combo_sets[j]))

        if not distances:
            return 0.0

        # 최대 거리는 12 (6개 모두 다름)
        avg_distance = np.mean(distances)
        return min(100.0, (avg_distance / 12.0) * 100)

    def calculate_coverage(
        self,
        combinations: List[str],
        coverage_level: int = 3
    ) -> float:
        """조합 집합의 번호 커버리지 비율

        Args:
            combinations: 조합 문자열 리스트
            coverage_level: 커버리지 레벨 (3=3개 이상 일치)

        Returns:
            0-1 범위의 커버리지 비율
        """
        if not combinations:
            return 0.0

        combo_sets = [self._parse_combination(c) for c in combinations]
        all_numbers = set()
        for combo in combo_sets:
            all_numbers.update(combo)

        # 전체 45개 번호 중 커버된 비율
        return len(all_numbers) / 45.0
