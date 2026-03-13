"""통계 기반 조합 가중치 계산기

1214회차+ 역사 데이터 기반으로 각 조합의 통계적 선호도를 계산한다.
핵심 원칙: "다음 당첨번호 예측"이 아닌 "역사적 패턴 기반 선호도 점수화"

분석 기반:
- 번호 출현 빈도 편향 (34번 +11.8%, 9번 -17.8% 등)
- 끝자리 편향 (끝자리 4,3,1이 많고, 9,8,0이 적음)
- 연속 미출현 패턴 (38-39회 미출현 후 출현율 약 7% 증가)
- 고빈도 번호 쌍 ((11,21), (33,40) 등)
- 합계 범위별 1등 인원 분포 (합계 높을수록 경쟁 소폭 감소)
"""
import threading
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ===========================
# 상수 정의 (1214회차 분석 결과)
# ===========================

# 끝자리 편향 가중치 (끝자리 0~9 각각)
# 기준: 기대값 대비 편차 → weight = 1.0 + deviation
DIGIT_WEIGHTS: Dict[int, float] = {
    0: 0.898, 1: 1.107, 2: 0.930, 3: 1.131, 4: 1.142,
    5: 1.096, 6: 0.899, 7: 1.020, 8: 0.888, 9: 0.846
}

# 번호별 기대 출현 횟수 (1214 * 6 / 45)
_EXPECTED_FREQ = 1214 * 6 / 45  # 161.87

# 실제 출현 횟수 (1214회차 기준 - 정적 참조값)
# 시스템 가동 중 DB에서 동적으로 계산되며, 이 값은 폴백용
_STATIC_FREQ: Dict[int, int] = {
    1: 162, 2: 152, 3: 162, 4: 158, 5: 153,
    6: 163, 7: 155, 8: 161, 9: 133, 10: 156,
    11: 167, 12: 177, 13: 174, 14: 169, 15: 161,
    16: 163, 17: 164, 18: 172, 19: 157, 20: 157,
    21: 162, 22: 141, 23: 146, 24: 163, 25: 150,
    26: 156, 27: 180, 28: 151, 29: 152, 30: 163,
    31: 162, 32: 141, 33: 173, 34: 181, 35: 165,
    36: 159, 37: 171, 38: 163, 39: 160, 40: 172,
    41: 147, 42: 163, 43: 159, 44: 165, 45: 171
}

# 고빈도 쌍 (기대값 18.39회의 1.5배 이상 = 28회+)
# (번호a, 번호b): 실제 출현 횟수
_HIGH_FREQ_PAIRS: Dict[Tuple[int, int], int] = {
    (11, 21): 34, (33, 40): 33, (6, 38): 31,
    (12, 24): 30, (37, 40): 29, (14, 15): 28,
    (3, 13): 28, (7, 38): 28, (27, 34): 28,
}

# 합계 범위별 1등 인원 가중치 (경쟁 감소 전략)
# 근거: 합계 160-180 구간에서 1등 평균 9.36명 (전체 평균 10.5명 대비 11% 적음)
_SUM_WEIGHTS: List[Tuple[int, int, float]] = [
    (21,  80, 0.60),   # 극단적 저합계 - 출현 희소하고 경쟁 많음
    (80,  120, 0.70),  # 저합계 - 1등 인원 많음
    (120, 140, 0.85),  # 정상 범위 저부
    (140, 160, 1.00),  # 기준값 (최빈 구간)
    (160, 180, 1.15),  # 경쟁 소폭 감소
    (180, 210, 1.05),  # 고합계 - 출현 희소하지만 경쟁 적음
    (210, 270, 0.75),  # 극단적 고합계 - 너무 드문 패턴
]

# 정규화 범위 (풀 독립적 - 전체 1~45 번호 기준 이론값)
_FREQ_RAW_MIN = 0.38   # 최저빈도 6개 조합 이론 최솟값 (0.85^6)
_FREQ_RAW_MAX = 2.31   # 최고빈도 6개 조합 이론 최댓값 (1.15^6)
_ABS_RAW_MIN  = -0.18  # 최대 음의 보정 (6개 번호 모두 -0.03)
_ABS_RAW_MAX  =  0.42  # 최대 양의 보정 (6개 번호 모두 +0.07)
_PAIR_RAW_MAX =  0.85  # 최대 쌍 점수

# 파생 정규화 범위 (위 상수들이 모두 정의된 이후 계산 - 모듈 로드 시 1회)
_DIGIT_W_MIN   = min(DIGIT_WEIGHTS.values())         # 0.846
_DIGIT_W_MAX   = max(DIGIT_WEIGHTS.values())         # 1.142
_DIGIT_W_RANGE = _DIGIT_W_MAX - _DIGIT_W_MIN         # 0.296
_SUM_W_MIN     = min(w for _, _, w in _SUM_WEIGHTS)  # 0.60
_SUM_W_MAX     = max(w for _, _, w in _SUM_WEIGHTS)  # 1.15
_SUM_W_RANGE   = _SUM_W_MAX - _SUM_W_MIN             # 0.55

# 미출현 회차별 출현 확률 보정값 (기대 13.33% 대비)
# n이 작은 구간(36회+)은 보정값 소폭만 적용
def _absence_score_for_number(absence_count: int) -> float:
    """단일 번호의 연속 미출현 기반 보정값"""
    if absence_count <= 10:
        return 0.0
    elif absence_count <= 18:
        # 선형 보간: 10회→0.0, 18회→-0.03
        return -0.03 * (absence_count - 10) / 8
    elif absence_count <= 21:
        return -0.03   # 19-21회: 출현 확률 약 -3% (n=300~460, 신뢰도 높음)
    elif absence_count <= 29:
        # 회복 구간: 21회→-0.03, 29회→0.0
        return -0.03 + 0.03 * (absence_count - 21) / 8
    elif absence_count <= 37:
        return 0.035   # 30-37회: 양의 보정
    else:
        return 0.07    # 38회+: 출현 확률 약 +7% (n=31~39, 보수적 적용)


class StatisticalWeightCalculator:
    """
    역사 데이터 기반 조합 통계 가중치 계산기.

    싱글톤 패턴으로 1회 초기화 후 재사용.
    DB에서 실제 출현 횟수를 읽어 동적으로 번호 빈도를 계산한다.
    """

    _instance: Optional['StatisticalWeightCalculator'] = None
    _lock = threading.Lock()

    # 각 요인별 기여 가중치 (합산 = 1.0)
    BETA_FREQ   = 0.35  # 번호 빈도 편향 (가장 신뢰도 높음)
    BETA_DIGIT  = 0.25  # 끝자리 편향
    BETA_ABS    = 0.20  # 연속 미출현 (n 제한적이라 중간)
    BETA_PAIR   = 0.15  # 고빈도 쌍 포함 여부
    BETA_SUM    = 0.05  # 합계 범위 (경쟁 감소 전략 - 보조적)

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._num_freq: Dict[int, int] = {}      # {번호: 실제 출현 횟수}
        self._num_weight: Dict[int, float] = {}  # {번호: 정규화된 빈도 가중치}
        self._current_absence: Dict[int, int] = {}  # {번호: 현재 연속 미출현 횟수}
        self._total_draws: int = 0
        self._expected_pair: float = 0.0  # 기대 쌍 출현 횟수 (총 회차 확정 후 계산)
        self._ready = False
        self._precompute_statistics()

    @classmethod
    def get_instance(cls, db_manager=None) -> 'StatisticalWeightCalculator':
        """싱글톤 인스턴스 반환. 최초 호출 시 db_manager 필수."""
        with cls._lock:
            if cls._instance is None:
                if db_manager is None:
                    raise RuntimeError("StatisticalWeightCalculator 최초 초기화 시 db_manager 필수")
                cls._instance = cls(db_manager)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """테스트 격리용. tests/ 디렉토리에서만 사용하라."""
        with cls._lock:
            cls._instance = None

    # ===========================
    # 초기화 및 사전 계산
    # ===========================

    def _precompute_statistics(self) -> None:
        """DB에서 데이터 로드 후 모든 통계를 사전 계산."""
        try:
            all_data = self.db_manager.get_numbers_with_bonus()
            if not all_data:
                logger.warning("[StatWeight] DB 데이터 없음 - 정적 빈도값 사용")
                self._num_freq = dict(_STATIC_FREQ)
                self._total_draws = 1214
            else:
                self._total_draws = len(all_data)
                self._num_freq = {n: 0 for n in range(1, 46)}
                for _, nums_tuple in all_data:
                    for n in nums_tuple[:6]:   # 보너스 제외
                        if 1 <= n <= 45:
                            self._num_freq[n] = self._num_freq.get(n, 0) + 1

                logger.info(f"[StatWeight] {self._total_draws}회차 데이터 로드 완료")

            # 번호별 빈도 가중치 계산 (편차 기반)
            expected = self._total_draws * 6 / 45
            for n in range(1, 46):
                actual = self._num_freq.get(n, expected)
                deviation = (actual - expected) / expected
                # [-0.20, +0.20] 클리핑 후 [0.85, 1.15] 스케일링
                deviation_clipped = max(-0.20, min(0.20, deviation))
                self._num_weight[n] = 1.0 + deviation_clipped * 0.75

            # 기대 쌍 출현 횟수 확정 (총 회차 × C(6,2)/C(45,2))
            self._expected_pair = self._total_draws * 15 / 990

            # 현재 미출현 회차 계산
            self._current_absence = self._compute_current_absence(all_data)

            self._ready = True
            logger.info("[StatWeight] 통계 사전 계산 완료")

        except Exception as e:
            logger.warning(f"[StatWeight] 초기화 실패 ({e}) - 정적 폴백값 사용")
            self._num_freq = dict(_STATIC_FREQ)
            self._total_draws = 1214
            expected = 161.87
            for n in range(1, 46):
                actual = self._num_freq.get(n, expected)
                deviation = (actual - expected) / expected
                deviation_clipped = max(-0.20, min(0.20, deviation))
                self._num_weight[n] = 1.0 + deviation_clipped * 0.75
            # 기대 쌍 출현 횟수 (폴백: 1214회차 기준)
            self._expected_pair = self._total_draws * 15 / 990
            # 미출현 데이터 없으므로 0으로 초기화
            self._current_absence = {n: 0 for n in range(1, 46)}
            self._ready = True

    def _compute_current_absence(self, all_data) -> Dict[int, int]:
        """각 번호의 현재 연속 미출현 회차 수 계산."""
        if not all_data:
            return {n: 0 for n in range(1, 46)}

        last_seen: Dict[int, int] = {n: 0 for n in range(1, 46)}
        for round_num, nums_tuple in sorted(all_data, key=lambda x: x[0]):
            for n in nums_tuple[:6]:
                if 1 <= n <= 45:
                    last_seen[n] = round_num

        latest_round = max(r for r, _ in all_data)
        return {n: (latest_round - last_seen[n]) for n in range(1, 46)}

    def refresh_absence_data(self) -> None:
        """새 회차 발표 후 호출 - 미출현 데이터 갱신."""
        try:
            all_data = self.db_manager.get_numbers_with_bonus()
            self._current_absence = self._compute_current_absence(all_data)
            logger.info("[StatWeight] 미출현 데이터 갱신 완료")
        except Exception as e:
            logger.warning(f"[StatWeight] 미출현 데이터 갱신 실패: {e}")

    # ===========================
    # 개별 가중치 요인
    # ===========================

    def _freq_weight_raw(self, numbers: List[int]) -> float:
        """번호 빈도 편향 원시 점수 (6개 번호 가중치의 곱)."""
        result = 1.0
        for n in numbers:
            result *= self._num_weight.get(n, 1.0)
        return result

    def _freq_weight_normalized(self, numbers: List[int]) -> float:
        """번호 빈도 가중치 [0, 1] 정규화."""
        raw = self._freq_weight_raw(numbers)
        return max(0.0, min(1.0, (raw - _FREQ_RAW_MIN) / (_FREQ_RAW_MAX - _FREQ_RAW_MIN)))

    def _digit_weight_normalized(self, numbers: List[int]) -> float:
        """끝자리 편향 가중치 [0, 1] 정규화."""
        if not numbers:
            return 0.5
        raw = sum(DIGIT_WEIGHTS.get(n % 10, 1.0) for n in numbers) / len(numbers)
        return max(0.0, min(1.0, (raw - _DIGIT_W_MIN) / _DIGIT_W_RANGE))

    def _absence_weight_normalized(
        self,
        numbers: List[int],
        absence_override: Optional[Dict[int, int]] = None
    ) -> float:
        """연속 미출현 패턴 가중치 [0, 1] 정규화."""
        absence = absence_override if absence_override is not None else self._current_absence
        raw = sum(_absence_score_for_number(absence.get(n, 0)) for n in numbers)
        return max(0.0, min(1.0, (raw - _ABS_RAW_MIN) / (_ABS_RAW_MAX - _ABS_RAW_MIN)))

    def _pair_weight_normalized(self, numbers: List[int]) -> float:
        """고빈도 쌍 포함 여부 가중치 [0, 1] 정규화."""
        num_set = frozenset(numbers)
        pair_score = 0.0

        for (a, b), count in _HIGH_FREQ_PAIRS.items():
            if {a, b}.issubset(num_set):
                multiplier = count / max(self._expected_pair, 1e-10)
                # 배율 기여도: (배율 - 1.0) * 0.5 (감쇄 적용)
                pair_score += (multiplier - 1.0) * 0.5

        return max(0.0, min(1.0, pair_score / _PAIR_RAW_MAX))

    def _sum_weight_normalized(self, numbers: List[int]) -> float:
        """합계 범위별 경쟁 감소 가중치 [0, 1] 정규화."""
        total = sum(numbers)
        raw = 0.85   # 기본값 (정의되지 않은 범위)
        for lo, hi, w in _SUM_WEIGHTS:
            if lo <= total < hi:
                raw = w
                break
        return max(0.0, min(1.0, (raw - _SUM_W_MIN) / _SUM_W_RANGE))

    # ===========================
    # 최종 가중치 계산
    # ===========================

    def calculate_combo_weight(
        self,
        numbers: List[int],
        absence_override: Optional[Dict[int, int]] = None
    ) -> float:
        """
        0.0~1.0 범위의 통계 가중치 반환.

        Args:
            numbers: 6개 번호 리스트 (정렬 불필요)
            absence_override: 특정 회차 기준 미출현 데이터 (None이면 현재 기준 사용)

        Returns:
            0.0~1.0 범위의 통계적 선호도 점수
        """
        if not self._ready or not numbers:
            return 0.5   # 초기화 실패 시 중립값

        try:
            w_freq  = self._freq_weight_normalized(numbers)
            w_digit = self._digit_weight_normalized(numbers)
            w_abs   = self._absence_weight_normalized(numbers, absence_override)
            w_pair  = self._pair_weight_normalized(numbers)
            w_sum   = self._sum_weight_normalized(numbers)

            return (self.BETA_FREQ  * w_freq  +
                    self.BETA_DIGIT * w_digit +
                    self.BETA_ABS   * w_abs   +
                    self.BETA_PAIR  * w_pair  +
                    self.BETA_SUM   * w_sum)

        except Exception as e:
            logger.debug(f"[StatWeight] 가중치 계산 오류 ({numbers}): {e}")
            return 0.5

    def get_weight_breakdown(self, numbers: List[int]) -> Dict[str, float]:
        """디버깅용: 각 요인별 가중치 분해."""
        return {
            'freq':  self._freq_weight_normalized(numbers),
            'digit': self._digit_weight_normalized(numbers),
            'absence': self._absence_weight_normalized(numbers),
            'pair':  self._pair_weight_normalized(numbers),
            'sum':   self._sum_weight_normalized(numbers),
            'total': self.calculate_combo_weight(numbers),
        }

    def get_current_absence(self) -> Dict[int, int]:
        """현재 미출현 회차 딕셔너리 반환 (디버깅 및 대시보드용)."""
        return dict(self._current_absence)

    def get_hot_numbers(self, top_n: int = 10) -> List[int]:
        """현재 기준 핫 번호 (빈도 가중치 상위 N개)."""
        sorted_nums = sorted(self._num_weight.items(), key=lambda x: x[1], reverse=True)
        return [n for n, _ in sorted_nums[:top_n]]

    def get_cold_numbers(self, top_n: int = 10) -> List[int]:
        """현재 기준 콜드 번호 (빈도 가중치 하위 N개)."""
        sorted_nums = sorted(self._num_weight.items(), key=lambda x: x[1])
        return [n for n, _ in sorted_nums[:top_n]]

    def get_long_absent_numbers(self, threshold: int = 20) -> List[Tuple[int, int]]:
        """장기 미출현 번호 목록 반환 (번호, 미출현 횟수)."""
        result = [(n, cnt) for n, cnt in self._current_absence.items() if cnt >= threshold]
        return sorted(result, key=lambda x: x[1], reverse=True)
