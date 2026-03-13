"""
휠링 시스템 (Wheeling System)
당첨 커버리지 확대를 위한 조합 최적화 시스템

휠링은 선택한 번호들로 최적의 조합 집합을 생성하여
특정 등수 이상 당첨을 보장하는 기법입니다.

주요 개념:
- Full Wheel: 모든 가능한 조합 (완벽한 커버리지, 많은 티켓)
- Abbreviated Wheel: 줄인 조합으로 최소 매칭 보장
- n-k-g 방식: n개 번호에서 k개 조합으로 최소 g개 일치 보장
"""

import logging
from typing import List, Dict, Tuple, Set, Any, Optional
from itertools import combinations
import numpy as np
from dataclasses import dataclass, field
from enum import Enum


class WheelType(Enum):
    """휠 타입"""
    FULL = "full"           # 전체 휠 (모든 조합)
    ABBREVIATED = "abbreviated"  # 축소 휠
    BALANCED = "balanced"   # 균형 휠 (모든 번호 동등 출현)
    KEY = "key"             # 키 번호 휠 (특정 번호 필수 포함)


class GuaranteeLevel(Enum):
    """보장 등급"""
    WIN_3 = 3  # 4등 (3개 일치)
    WIN_4 = 4  # 3등 (4개 일치)
    WIN_5 = 5  # 2등 (5개 일치)
    WIN_6 = 6  # 1등 (6개 일치)


@dataclass
class WheelPattern:
    """휠 패턴 정의"""
    name: str
    numbers_selected: int     # 선택한 번호 개수 (n)
    numbers_per_combo: int    # 조합당 번호 수 (k, 로또는 6)
    guarantee: int            # 보장 매칭 수 (g)
    combinations_count: int   # 필요한 조합 수
    pattern: List[Tuple[int, ...]] = field(default_factory=list)

    def __str__(self):
        return f"{self.name}: {self.numbers_selected}개 → {self.combinations_count}조합, {self.guarantee}개 보장"


@dataclass
class WheelResult:
    """휠링 결과"""
    wheel_type: WheelType
    input_numbers: List[int]
    generated_combinations: List[Tuple[int, ...]]
    guarantee_level: int
    coverage_analysis: Dict[str, float]
    estimated_cost: int  # 티켓 비용 (1장 1000원 기준)


class WheelingSystem:
    """
    휠링 시스템

    선택한 번호들로 최적의 조합 집합을 생성하여
    하위 등수(3-5등) 당첨 확률을 높입니다.

    사용 예:
        ws = WheelingSystem()

        # 기본 휠: 10개 번호로 3개 일치 보장
        result = ws.generate_wheel([1,5,10,15,20,25,30,35,40,45])

        # 키 번호 휠: 특정 번호 필수 포함
        result = ws.generate_key_wheel([3,17,25], [31,38,44,7,12])
    """

    # 표준 축소 휠 패턴 (입증된 패턴들)
    STANDARD_WHEELS = {
        # (n, k, g): (조합 수, 패턴)
        # n=선택 번호 수, k=조합 크기(6), g=보장 매칭 수
        (7, 6, 3): WheelPattern("7-6-3", 7, 6, 3, 4, [
            (0,1,2,3,4,5), (0,1,2,3,4,6), (0,1,2,5,6,6), (0,3,4,5,6,6)
        ]),
        (8, 6, 3): WheelPattern("8-6-3", 8, 6, 3, 6, [
            (0,1,2,3,4,5), (0,1,2,3,6,7), (0,1,4,5,6,7),
            (0,2,3,4,5,7), (1,2,3,4,6,7), (1,2,4,5,6,7)
        ]),
        (9, 6, 3): WheelPattern("9-6-3", 9, 6, 3, 9, [
            (0,1,2,3,4,5), (0,1,2,6,7,8), (0,3,4,5,6,7),
            (0,3,4,5,6,8), (1,2,3,4,7,8), (1,2,3,5,6,8),
            (1,2,4,5,6,7), (1,3,4,6,7,8), (2,3,5,6,7,8)
        ]),
        (10, 6, 3): WheelPattern("10-6-3", 10, 6, 3, 14, []),
        (10, 6, 4): WheelPattern("10-6-4", 10, 6, 4, 50, []),
        (12, 6, 3): WheelPattern("12-6-3", 12, 6, 3, 22, []),
        (12, 6, 4): WheelPattern("12-6-4", 12, 6, 4, 132, []),
        (15, 6, 3): WheelPattern("15-6-3", 15, 6, 3, 42, []),
        (15, 6, 4): WheelPattern("15-6-4", 15, 6, 4, 253, []),
        (20, 6, 3): WheelPattern("20-6-3", 20, 6, 3, 81, []),
    }

    def __init__(self, db_manager=None):
        """
        초기화

        Args:
            db_manager: DatabaseManager 인스턴스 (선택적, 분석용)
        """
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self.ticket_price = 1000  # 1장 가격

    def generate_wheel(
        self,
        numbers: List[int],
        guarantee: int = 3,
        wheel_type: WheelType = WheelType.ABBREVIATED,
        max_combinations: int = 100
    ) -> WheelResult:
        """
        휠 생성

        Args:
            numbers: 선택한 번호들 (7-20개 권장)
            guarantee: 보장 매칭 수 (3=4등, 4=3등, 5=2등)
            wheel_type: 휠 타입
            max_combinations: 최대 조합 수 제한

        Returns:
            WheelResult: 생성된 휠 결과
        """
        numbers = sorted(set(numbers))
        n = len(numbers)

        if n < 6:
            raise ValueError("최소 6개 이상의 번호가 필요합니다")
        if n > 45:
            raise ValueError("번호는 1-45 범위여야 합니다")
        if guarantee < 3 or guarantee > 6:
            raise ValueError("보장 수는 3-6 범위여야 합니다")

        self.logger.info(f"휠 생성: {n}개 번호, {guarantee}개 보장, 타입={wheel_type.value}")

        if wheel_type == WheelType.FULL:
            combos = self._generate_full_wheel(numbers)
        elif wheel_type == WheelType.ABBREVIATED:
            combos = self._generate_abbreviated_wheel(numbers, guarantee, max_combinations)
        elif wheel_type == WheelType.BALANCED:
            combos = self._generate_balanced_wheel(numbers, guarantee, max_combinations)
        else:
            combos = self._generate_abbreviated_wheel(numbers, guarantee, max_combinations)

        # 커버리지 분석
        coverage = self._analyze_coverage(numbers, combos, guarantee)

        return WheelResult(
            wheel_type=wheel_type,
            input_numbers=numbers,
            generated_combinations=combos,
            guarantee_level=guarantee,
            coverage_analysis=coverage,
            estimated_cost=len(combos) * self.ticket_price
        )

    def generate_key_wheel(
        self,
        key_numbers: List[int],
        pool_numbers: List[int],
        guarantee: int = 3,
        max_combinations: int = 50
    ) -> WheelResult:
        """
        키 번호 휠 생성

        키 번호는 모든 조합에 필수 포함됩니다.

        Args:
            key_numbers: 필수 포함 번호들 (1-3개 권장)
            pool_numbers: 나머지 후보 번호들
            guarantee: 보장 매칭 수
            max_combinations: 최대 조합 수

        Returns:
            WheelResult: 생성된 휠 결과
        """
        key_numbers = sorted(set(key_numbers))
        pool_numbers = sorted(set(pool_numbers) - set(key_numbers))

        if len(key_numbers) > 5:
            raise ValueError("키 번호는 5개 이하여야 합니다")
        if len(key_numbers) + len(pool_numbers) < 6:
            raise ValueError("전체 번호가 6개 이상이어야 합니다")

        remaining_slots = 6 - len(key_numbers)
        all_numbers = key_numbers + pool_numbers

        combos = []
        for pool_combo in combinations(pool_numbers, remaining_slots):
            combo = tuple(sorted(key_numbers + list(pool_combo)))
            combos.append(combo)
            if len(combos) >= max_combinations:
                break

        coverage = self._analyze_coverage(all_numbers, combos, guarantee)

        return WheelResult(
            wheel_type=WheelType.KEY,
            input_numbers=all_numbers,
            generated_combinations=combos,
            guarantee_level=guarantee,
            coverage_analysis=coverage,
            estimated_cost=len(combos) * self.ticket_price
        )

    def _generate_full_wheel(self, numbers: List[int]) -> List[Tuple[int, ...]]:
        """전체 휠 생성 (모든 조합)"""
        return list(combinations(numbers, 6))

    def _generate_abbreviated_wheel(
        self,
        numbers: List[int],
        guarantee: int,
        max_combinations: int
    ) -> List[Tuple[int, ...]]:
        """
        축소 휠 생성

        커버링 코드 알고리즘 사용:
        모든 g-조합이 최소 하나의 6-조합에 포함되도록 보장
        """
        n = len(numbers)

        # 표준 패턴 확인
        key = (n, 6, guarantee)
        if key in self.STANDARD_WHEELS:
            pattern = self.STANDARD_WHEELS[key]
            if pattern.pattern:
                return [tuple(numbers[i] for i in idx) for idx in pattern.pattern]

        # 그리디 커버링 알고리즘
        return self._greedy_covering(numbers, guarantee, max_combinations)

    def _generate_balanced_wheel(
        self,
        numbers: List[int],
        guarantee: int,
        max_combinations: int
    ) -> List[Tuple[int, ...]]:
        """
        균형 휠 생성

        모든 번호가 가능한 한 동일한 횟수로 출현하도록 함
        """
        n = len(numbers)
        all_combos = list(combinations(range(n), 6))

        # 번호별 출현 횟수 추적
        appearance_count = {i: 0 for i in range(n)}
        selected_combos = []

        # 탐욕적으로 균형잡힌 조합 선택
        while len(selected_combos) < max_combinations and all_combos:
            # 현재 가장 적게 출현한 번호들을 포함하는 조합 우선
            best_combo = None
            best_score = float('inf')

            for combo in all_combos[:min(100, len(all_combos))]:  # 효율성 위해 제한
                # 이 조합의 번호들 중 최대 출현 횟수
                max_count = max(appearance_count[i] for i in combo)
                if max_count < best_score:
                    best_score = max_count
                    best_combo = combo

            if best_combo is None:
                break

            selected_combos.append(tuple(numbers[i] for i in best_combo))
            for i in best_combo:
                appearance_count[i] += 1
            all_combos.remove(best_combo)

            # 커버리지 체크
            if self._check_coverage(numbers, selected_combos, guarantee):
                break

        return selected_combos

    def _greedy_covering(
        self,
        numbers: List[int],
        guarantee: int,
        max_combinations: int
    ) -> List[Tuple[int, ...]]:
        """
        그리디 커버링 알고리즘

        모든 g-부분집합이 최소 하나의 6-조합에 포함되도록
        최소 개수의 조합을 선택합니다.
        """
        n = len(numbers)

        # 커버해야 할 모든 g-조합
        uncovered = set(combinations(range(n), guarantee))

        # 선택된 조합들
        selected = []

        # 모든 가능한 6-조합
        all_combos = list(combinations(range(n), 6))

        while uncovered and len(selected) < max_combinations:
            best_combo = None
            best_coverage = 0

            # 가장 많은 미커버 g-조합을 포함하는 6-조합 선택
            for combo in all_combos:
                # 이 조합이 커버하는 g-조합 수 계산
                covered_count = sum(
                    1 for g_combo in combinations(combo, guarantee)
                    if g_combo in uncovered
                )
                if covered_count > best_coverage:
                    best_coverage = covered_count
                    best_combo = combo

            if best_combo is None or best_coverage == 0:
                break

            # 선택하고 커버된 것들 제거
            selected.append(tuple(numbers[i] for i in best_combo))
            for g_combo in combinations(best_combo, guarantee):
                uncovered.discard(g_combo)
            all_combos.remove(best_combo)

        self.logger.debug(f"그리디 커버링: {len(selected)}개 조합으로 {guarantee}개 보장")
        return selected

    def _check_coverage(
        self,
        numbers: List[int],
        combos: List[Tuple[int, ...]],
        guarantee: int
    ) -> bool:
        """커버리지 완성 여부 체크"""
        n = len(numbers)
        number_to_idx = {num: i for i, num in enumerate(numbers)}

        all_g_combos = set(combinations(range(n), guarantee))
        covered = set()

        for combo in combos:
            indices = tuple(number_to_idx[num] for num in combo)
            for g_combo in combinations(indices, guarantee):
                covered.add(g_combo)

        return len(covered) >= len(all_g_combos)

    def _analyze_coverage(
        self,
        numbers: List[int],
        combos: List[Tuple[int, ...]],
        guarantee: int
    ) -> Dict[str, float]:
        """
        커버리지 분석

        Returns:
            Dict: 분석 결과
        """
        n = len(numbers)
        number_to_idx = {num: i for i, num in enumerate(numbers)}

        # g-조합 커버리지
        all_g_combos = set(combinations(range(n), guarantee))
        covered_g = set()

        for combo in combos:
            try:
                indices = tuple(number_to_idx[num] for num in combo)
                for g_combo in combinations(indices, guarantee):
                    covered_g.add(g_combo)
            except KeyError:
                continue

        # 번호별 출현 횟수
        number_frequency = {num: 0 for num in numbers}
        for combo in combos:
            for num in combo:
                if num in number_frequency:
                    number_frequency[num] += 1

        avg_frequency = np.mean(list(number_frequency.values())) if number_frequency else 0
        freq_std = np.std(list(number_frequency.values())) if len(number_frequency) > 1 else 0

        return {
            'total_combinations': len(combos),
            'coverage_ratio': len(covered_g) / len(all_g_combos) if all_g_combos else 0,
            'covered_subsets': len(covered_g),
            'total_subsets': len(all_g_combos),
            'avg_number_frequency': avg_frequency,
            'frequency_std': freq_std,
            'balance_score': 100 * (1 - freq_std / avg_frequency) if avg_frequency > 0 else 0
        }

    def optimize_from_predictions(
        self,
        predictions: List[List[int]],
        top_n: int = 10,
        guarantee: int = 3,
        max_combinations: int = 30
    ) -> WheelResult:
        """
        ML 예측 결과를 바탕으로 최적화된 휠 생성

        여러 예측에서 공통적으로 나타나는 번호들을 키 번호로,
        나머지를 풀 번호로 사용합니다.

        Args:
            predictions: ML 예측 조합 리스트
            top_n: 사용할 상위 예측 수
            guarantee: 보장 매칭 수
            max_combinations: 최대 조합 수

        Returns:
            WheelResult: 최적화된 휠 결과
        """
        if not predictions:
            raise ValueError("예측 결과가 없습니다")

        predictions = predictions[:top_n]

        # 번호별 출현 빈도 계산
        frequency = {}
        for pred in predictions:
            for num in pred:
                frequency[num] = frequency.get(num, 0) + 1

        # 빈도 기준 정렬
        sorted_numbers = sorted(frequency.keys(), key=lambda x: frequency[x], reverse=True)

        # 상위 3개는 키 번호, 나머지는 풀
        key_threshold = len(predictions) * 0.6  # 60% 이상 출현 시 키 번호
        key_numbers = [n for n in sorted_numbers if frequency[n] >= key_threshold][:3]
        pool_numbers = [n for n in sorted_numbers if n not in key_numbers][:12]

        if len(key_numbers) == 0:
            # 키 번호가 없으면 일반 휠 사용
            all_numbers = sorted_numbers[:15]
            return self.generate_wheel(all_numbers, guarantee, WheelType.ABBREVIATED, max_combinations)
        else:
            return self.generate_key_wheel(key_numbers, pool_numbers, guarantee, max_combinations)

    def calculate_expected_return(
        self,
        wheel_result: WheelResult,
        match_probability: Dict[int, float] = None
    ) -> Dict[str, float]:
        """
        기대 수익 계산

        Args:
            wheel_result: 휠 결과
            match_probability: 매칭 확률 (기본값 사용 가능)

        Returns:
            Dict: 기대 수익 분석
        """
        if match_probability is None:
            # 로또 기본 확률 (대략적)
            match_probability = {
                3: 0.0177,   # 4등: 1/56.65
                4: 0.00093,  # 3등: 1/1075
                5: 0.0000195, # 2등: 1/51,238.16 (보너스 포함)
                6: 0.0000000123  # 1등: 1/8,145,060
            }

        # 등수별 상금 (2024년 평균 기준)
        prize_amounts = {
            3: 5000,       # 4등: 고정 5,000원
            4: 50000,      # 3등: 약 5만원 (변동)
            5: 1500000,    # 2등: 약 150만원 (변동)
            6: 2000000000  # 1등: 약 20억원 (변동)
        }

        n_combos = len(wheel_result.generated_combinations)
        total_cost = n_combos * self.ticket_price

        # 각 등수별 기대값
        expected_values = {}
        total_expected = 0

        for matches in [3, 4, 5, 6]:
            if matches >= wheel_result.guarantee_level:
                # 휠 보장으로 확률 상승 효과 (단순화된 모델)
                boost_factor = 1.5 if matches == wheel_result.guarantee_level else 1.2
                adjusted_prob = match_probability[matches] * n_combos * boost_factor
                adjusted_prob = min(1.0, adjusted_prob)  # 확률 상한

                ev = adjusted_prob * prize_amounts[matches]
                expected_values[f'{matches}개_일치'] = {
                    'probability': adjusted_prob,
                    'prize': prize_amounts[matches],
                    'expected_value': ev
                }
                total_expected += ev

        roi = ((total_expected - total_cost) / total_cost) * 100 if total_cost > 0 else 0

        return {
            'total_cost': total_cost,
            'total_expected_value': total_expected,
            'net_expected_value': total_expected - total_cost,
            'roi_percent': roi,
            'breakdown': expected_values
        }

    def format_wheel_output(
        self,
        wheel_result: WheelResult,
        include_analysis: bool = True
    ) -> str:
        """
        휠 결과를 보기 좋게 포맷

        Args:
            wheel_result: 휠 결과
            include_analysis: 분석 포함 여부

        Returns:
            str: 포맷된 문자열
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"휠링 시스템 결과 ({wheel_result.wheel_type.value})")
        lines.append("=" * 60)

        lines.append(f"\n입력 번호: {wheel_result.input_numbers}")
        lines.append(f"보장 등급: {wheel_result.guarantee_level}개 일치 보장")
        lines.append(f"생성된 조합 수: {len(wheel_result.generated_combinations)}")
        lines.append(f"예상 비용: {wheel_result.estimated_cost:,}원")

        lines.append(f"\n--- 조합 목록 ---")
        for i, combo in enumerate(wheel_result.generated_combinations, 1):
            lines.append(f"{i:3}. {combo}")

        if include_analysis:
            cov = wheel_result.coverage_analysis
            lines.append(f"\n--- 커버리지 분석 ---")
            lines.append(f"커버리지: {cov['coverage_ratio']*100:.1f}% ({cov['covered_subsets']}/{cov['total_subsets']})")
            lines.append(f"번호 평균 출현: {cov['avg_number_frequency']:.1f}회")
            lines.append(f"균형 점수: {cov['balance_score']:.1f}/100")

            # 기대 수익 계산
            expected = self.calculate_expected_return(wheel_result)
            lines.append(f"\n--- 기대 수익 분석 ---")
            lines.append(f"총 비용: {expected['total_cost']:,}원")
            lines.append(f"기대 수익: {expected['total_expected_value']:,.0f}원")
            lines.append(f"순 기대값: {expected['net_expected_value']:,.0f}원")
            lines.append(f"ROI: {expected['roi_percent']:.2f}%")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# 사용 예시
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    ws = WheelingSystem()

    # 예시 1: 10개 번호로 3개 일치 보장 휠
    print("\n=== 예시 1: 축소 휠 ===")
    numbers = [3, 7, 12, 17, 23, 28, 33, 38, 42, 45]
    result = ws.generate_wheel(numbers, guarantee=3, max_combinations=20)
    print(ws.format_wheel_output(result))

    # 예시 2: 키 번호 휠
    print("\n=== 예시 2: 키 번호 휠 ===")
    key = [7, 17, 33]  # 반드시 포함
    pool = [3, 12, 23, 28, 38, 42, 45]
    result = ws.generate_key_wheel(key, pool, guarantee=3, max_combinations=10)
    print(ws.format_wheel_output(result))

    # 예시 3: 균형 휠
    print("\n=== 예시 3: 균형 휠 ===")
    result = ws.generate_wheel(numbers, guarantee=3, wheel_type=WheelType.BALANCED, max_combinations=15)
    print(ws.format_wheel_output(result))
