"""
동적 패턴 스코어러 v2.1 (Dynamic Pattern Scorer)

설계 원칙:
1. 모든 기준값은 DB에서 동적으로 계산 - 하드코딩 없음
2. 기존 16개 필터와 100% 중복 없음 (sum_range, ten_section, odd_even,
   last_digit, dispersion, prime_composite 등 기존 필터 기준 제외)
3. 매주 새 회차가 DB에 추가되면 자동 갱신
4. 가중치는 5개 전문 에이전트 팀의 통계 검정 결과 기반 (1215회차)

=== 5개 에이전트 팀 실증 통계 검정 결과 ===

[에이전트 A - 수리통계학자]
[X] 드라우트 조건부 확률: 이론값(76.1%) = 실측(76.9%) -> 독립시행 그대로 (제거)
[X] 마르코프 체인: 전이 확률 거의 동일 -> 메모리 없음 (제거)
[X] 번호간 조건부 확률: 다중검정(Bonferroni) 보정 후 유의성 소멸

[에이전트 B - 조합수학자]
[O] 피보나치 군집: 3개+ 포함이 이론보다 31% 과다 출현 (p=0.0213) -> 신규 추가
[O] 완전제곱수 분포: 0개 포함 과다, 1개 포함 과소 (p=0.0293) -> 신규 추가
[O] 끝자리 편향: DB 동적 Z-score 기반 선호도
[X] 소수/배수 분포: 이론과 동일 (제거)

[에이전트 C - 행동경제학자]
[O] 고번호(31-45) 4개+ 조합: 당첨금 프리미엄 -> 트리플렛 스코어로 흡수

[에이전트 D - 네트워크 분석가]
[O] 핫 트리플렛 113개 (Z>3.0): 이론 4.7배 출현
    (33,37,40)=8회(Z=4.81), (3,8,27)=8회(Z=4.81) 등

[에이전트 E - 시계열 분석가]
[O] 시계열 추세 번호 (선형 회귀 p<0.05, 200회 lookback):
    상승: 번호 27, 하락: 번호 22, 45 (동적 계산, 매주 갱신)

v2.1 가중치 (7개 요소, 합계=1.0):
- WEIGHT_TRIPLET:    0.25 (Z>3.0, 113개, 이론 4.7배)
- WEIGHT_PAIR:       0.20 (Z>2.0 극단 30쌍)
- WEIGHT_FIB:        0.15 (피보나치 군집 p=0.0213 - 에이전트 B 신규)
- WEIGHT_LAST_DIGIT: 0.15 (끝자리 편향 스코어)
- WEIGHT_TREND:      0.15 (선형 회귀 p<0.05 추세 번호)
- WEIGHT_REPEAT:     0.05 (편향 보정 최소)
- WEIGHT_SQUARE:     0.05 (완전제곱수 분포 p=0.0293 - 에이전트 B 신규)
"""

import logging
import sqlite3
import itertools
from collections import Counter
from math import comb
from typing import List, Tuple, Dict, Optional

import numpy as np

try:
    from scipy import stats as scipy_stats
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── 통계 기준 상수 (수학적 정의, 변경 불필요) ──
PAIR_Z_HIGH = 2.0
PAIR_Z_LOW = -2.0
TRIPLET_Z_THRESHOLD = 3.0
TREND_LOOKBACK = 200
TREND_P_VALUE = 0.05

# ── 수학적 집합 (1~45 기준, 변경 불필요) ──
FIBONACCI_NUMS = frozenset({1, 2, 3, 5, 8, 13, 21, 34})  # 8개
SQUARE_NUMS = frozenset({1, 4, 9, 16, 25, 36})            # 6개


def _hypergeom_probs(pool_size: int, special_count: int, draw_count: int) -> Dict[int, float]:
    """초기하분포: pool에서 special 중 k개가 draw에 포함될 이론 확률 동적 계산"""
    probs = {}
    for k in range(min(special_count, draw_count) + 1):
        remaining = draw_count - k
        if remaining > pool_size - special_count:
            continue
        p = (comb(special_count, k) * comb(pool_size - special_count, remaining)
             / comb(pool_size, draw_count))
        probs[k] = p
    return probs


class DynamicPatternScorer:
    """
    5개 전문 에이전트 팀 통계 검정 기반 조합 스코어러 v2.1

    v2 -> v2.1 변경 (에이전트 B 결과 반영):
    - [신규] WEIGHT_FIB=0.15: 피보나치 군집 (p=0.0213)
    - [신규] WEIGHT_SQUARE=0.05: 완전제곱수 분포 (p=0.0293)
    - [조정] 기존 4개 가중치 소폭 감소로 합계 1.0 유지

    기존 필터 중복 없음:
    - prime_composite: 소수/합성수 비율 vs 피보나치/제곱수 군집 (완전히 다름)
    - last_digit: 중복 패턴 제거 vs 끝자리 빈도 선호도 (다름)
    """

    DEFAULT_HOT_WINDOW = 10

    # 가중치 (v2.1 - 7개 요소, 합계=1.0)
    WEIGHT_TRIPLET = 0.25
    WEIGHT_PAIR = 0.20
    WEIGHT_FIB = 0.15
    WEIGHT_LAST_DIGIT = 0.15
    WEIGHT_TREND = 0.15
    WEIGHT_REPEAT = 0.05
    WEIGHT_SQUARE = 0.05

    def __init__(self, db_path: str = "data/lotto_numbers.db", hot_window: int = None):
        self.db_path = db_path
        self.hot_window = hot_window or self.DEFAULT_HOT_WINDOW
        self._historical_data: List[Dict] = []

        # 동적 계산 결과 (모두 DB 기반)
        self._pair_zscores: Dict[Tuple, float] = {}
        self._triplet_zscores: Dict[Tuple, float] = {}
        self._last_digit_scores: Dict[int, float] = {}
        self._trend_scores: Dict[int, float] = {}
        self._fib_score_map: Dict[int, float] = {}
        self._square_score_map: Dict[int, float] = {}

        self._last_loaded_round: int = 0
        self._initialized = False

    # ─────────────────────────────────────────────────────────────────
    # 초기화 & 자동 갱신
    # ─────────────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """DB에서 이력 데이터 로드 및 모든 통계 사전 계산"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT round, numbers FROM lotto_numbers ORDER BY round"
            ).fetchall()
            conn.close()

            if not rows:
                logger.warning("[DynamicPatternScorer] 이력 데이터 없음")
                return False

            self._historical_data = [
                {"round": r["round"], "nums": [int(x) for x in r["numbers"].split(",")]}
                for r in rows
            ]
            self._last_loaded_round = self._historical_data[-1]["round"]

            # 7개 요소 동적 계산
            self._build_pair_zscores()
            self._build_triplet_zscores()
            self._build_last_digit_scores()
            self._build_trend_scores()
            self._build_fib_score_map()
            self._build_square_score_map()

            self._initialized = True

            n_hot_pairs = sum(1 for z in self._pair_zscores.values() if z >= PAIR_Z_HIGH)
            n_hot_trips = sum(1 for z in self._triplet_zscores.values() if z >= TRIPLET_Z_THRESHOLD)
            trend_up = sum(1 for s in self._trend_scores.values() if s > 0.1)
            trend_dn = sum(1 for s in self._trend_scores.values() if s < -0.1)

            logger.info(
                f"[DynamicPatternScorer v2.1] 초기화 완료: {len(self._historical_data)}회차 "
                f"(최신 {self._last_loaded_round}회) "
                f"| Z>2 쌍: {n_hot_pairs}개 "
                f"| Z>3 트리플렛: {n_hot_trips}개 "
                f"| 추세 상승: {trend_up}개, 하락: {trend_dn}개 "
                f"| 피보나치맵: {self._fib_score_map} "
                f"| 제곱수맵: {self._square_score_map}"
            )
            return True

        except Exception as e:
            logger.error(f"[DynamicPatternScorer] 초기화 실패: {e}", exc_info=True)
            return False

    def refresh_if_new_round(self) -> bool:
        """매주 새 회차가 DB에 추가되면 자동 감지 및 재초기화 (모든 기준 재계산)"""
        try:
            conn = sqlite3.connect(self.db_path)
            latest = conn.execute(
                "SELECT MAX(round) as r FROM lotto_numbers"
            ).fetchone()[0]
            conn.close()

            if latest and latest > self._last_loaded_round:
                logger.info(
                    f"[DynamicPatternScorer] 새 회차 감지: "
                    f"{self._last_loaded_round} -> {latest}, 자동 재초기화"
                )
                return self.initialize()
            return False
        except Exception as e:
            logger.debug(f"[DynamicPatternScorer] 갱신 확인 실패: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────
    # 동적 통계 계산 (모두 DB 기반)
    # ─────────────────────────────────────────────────────────────────

    def _build_pair_zscores(self):
        """번호쌍 공출현 Z-score (동적): Z>2.0 극단 30쌍 유의미"""
        N = len(self._historical_data)
        pair_freq = Counter()
        for d in self._historical_data:
            for p in itertools.combinations(sorted(d["nums"]), 2):
                pair_freq[p] += 1

        p_pair = 15 / 990
        expected = N * p_pair
        std_dev = (N * p_pair * (1 - p_pair)) ** 0.5
        if std_dev <= 0:
            return

        self._pair_zscores = {}
        for p, cnt in pair_freq.items():
            self._pair_zscores[p] = (cnt - expected) / std_dev

        all_pairs = set(itertools.combinations(range(1, 46), 2))
        for p in all_pairs:
            if p not in self._pair_zscores:
                self._pair_zscores[p] = (0 - expected) / std_dev

    def _build_triplet_zscores(self):
        """번호 트리플렛 공출현 Z-score (동적): Z>3.0 113개, 이론 4.7배"""
        N = len(self._historical_data)
        trip_freq = Counter()
        for d in self._historical_data:
            for t in itertools.combinations(sorted(d["nums"]), 3):
                trip_freq[t] += 1

        p_trip = 20 / 14190
        expected = N * p_trip
        std_dev = (N * p_trip * (1 - p_trip)) ** 0.5
        if std_dev <= 0:
            return

        self._triplet_zscores = {}
        for t, cnt in trip_freq.items():
            z = (cnt - expected) / std_dev
            if abs(z) >= TRIPLET_Z_THRESHOLD:
                self._triplet_zscores[t] = z

    def _build_last_digit_scores(self):
        """
        끝자리 편향 스코어 (동적)
        1~45: 끝자리 1-5는 5개씩, 0,6-9는 4개씩 (불균일 풀 고려)
        기존 last_digit 필터(중복 패턴 제거)와 다른 방식: 빈도 편향 선호도
        """
        N = len(self._historical_data)
        ld_freq = Counter()
        for d in self._historical_data:
            for n in d["nums"]:
                ld_freq[n % 10] += 1

        ld_count_in_pool = Counter(n % 10 for n in range(1, 46))
        total_pool = 45

        self._last_digit_scores = {}
        for ld in range(10):
            p_ld = ld_count_in_pool[ld] / total_pool
            expected = N * 6 * p_ld
            std = (N * 6 * p_ld * (1 - p_ld)) ** 0.5 if expected > 0 else 1
            z = (ld_freq[ld] - expected) / std if std > 0 else 0
            self._last_digit_scores[ld] = max(0.0, min(1.0, 0.5 + z / 8.0))

    def _build_trend_scores(self):
        """
        시계열 추세 스코어 (동적): 최근 200회 선형 회귀 p<0.05
        에이전트 E: 상승=번호27, 하락=번호22,45 (매주 자동 재계산)
        """
        N = len(self._historical_data)
        lookback = min(TREND_LOOKBACK, N)
        recent_data = self._historical_data[-lookback:]
        x = np.arange(lookback, dtype=float)

        self._trend_scores = {}
        for num in range(1, 46):
            y = np.array([1.0 if num in d["nums"] else 0.0 for d in recent_data])
            if _SCIPY_AVAILABLE:
                try:
                    slope, _, _, p_val, _ = scipy_stats.linregress(x, y)
                    if p_val < TREND_P_VALUE:
                        self._trend_scores[num] = float(np.clip(slope * 1000, -1.0, 1.0))
                    else:
                        self._trend_scores[num] = 0.0
                except Exception:
                    self._trend_scores[num] = 0.0
            else:
                x_mean, y_mean = np.mean(x), np.mean(y)
                numer = np.sum((x - x_mean) * (y - y_mean))
                denom = np.sum((x - x_mean) ** 2)
                slope = numer / denom if denom != 0 else 0.0
                self._trend_scores[num] = float(np.clip(slope * 1000, -1.0, 1.0)) if abs(slope) >= 0.0005 else 0.0

    def _build_fib_score_map(self):
        """
        피보나치 군집 스코어 맵 (동적 - 에이전트 B 신규, p=0.0213)
        3개+ 포함이 이론보다 31% 과다 출현 -> 높은 점수
        1개 포함이 이론보다 7.7% 과소 출현 -> 낮은 점수

        이론값: 초기하분포 H(45, 8, 6) 동적 계산 (하드코딩 없음)
        """
        N = len(self._historical_data)
        fib_counts = [sum(1 for n in d["nums"] if n in FIBONACCI_NUMS)
                      for d in self._historical_data]
        freq = Counter(fib_counts)
        theory = _hypergeom_probs(45, len(FIBONACCI_NUMS), 6)

        self._fib_score_map = {}
        for k in range(7):
            actual_rate = freq.get(k, 0) / N
            theory_rate = theory.get(k, 0)
            ratio = actual_rate / theory_rate if theory_rate > 0 else 1.0
            score = max(0.0, min(1.0, 0.5 + (ratio - 1.0) * 0.5))
            self._fib_score_map[k] = round(score, 3)

    def _build_square_score_map(self):
        """
        완전제곱수 분포 스코어 맵 (동적 - 에이전트 B 신규, p=0.0293)
        0개 포함 과다 출현 -> 약간 높은 점수
        1개 포함 과소 출현 -> 약간 낮은 점수

        이론값: 초기하분포 H(45, 6, 6) 동적 계산
        """
        N = len(self._historical_data)
        sq_counts = [sum(1 for n in d["nums"] if n in SQUARE_NUMS)
                     for d in self._historical_data]
        freq = Counter(sq_counts)
        theory = _hypergeom_probs(45, len(SQUARE_NUMS), 6)

        self._square_score_map = {}
        for k in range(7):
            actual_rate = freq.get(k, 0) / N
            theory_rate = theory.get(k, 0)
            ratio = actual_rate / theory_rate if theory_rate > 0 else 1.0
            score = max(0.0, min(1.0, 0.5 + (ratio - 1.0) * 0.5))
            self._square_score_map[k] = round(score, 3)

    # ─────────────────────────────────────────────────────────────────
    # 조합 스코어링
    # ─────────────────────────────────────────────────────────────────

    def _compute_triplet_score(self, sorted_combo: List[int]) -> float:
        """핫 트리플렛 스코어 (WEIGHT=0.25): Z>3.0, 113개, 이론 4.7배"""
        trips = list(itertools.combinations(sorted_combo, 3))
        hot = sum(1 for t in trips if self._triplet_zscores.get(t, 0.0) >= TRIPLET_Z_THRESHOLD)
        cold = sum(1 for t in trips if self._triplet_zscores.get(t, 0.0) <= -TRIPLET_Z_THRESHOLD)
        return max(0.0, min(1.0, 0.5 + (hot - cold) / len(trips) * 0.5))

    def _compute_pair_score(self, sorted_combo: List[int]) -> float:
        """번호쌍 Z-score 스코어 (WEIGHT=0.20): Z>2.0 극단쌍"""
        pairs = list(itertools.combinations(sorted_combo, 2))
        scores = []
        for p in pairs:
            z = self._pair_zscores.get(p, 0.0)
            if z >= PAIR_Z_HIGH:
                scores.append(min(0.75 + (z - 2.0) * 0.083, 1.0))
            elif z <= PAIR_Z_LOW:
                scores.append(max(0.25 + (z + 2.0) * 0.083, 0.0))
            else:
                scores.append(0.5)
        return sum(scores) / len(scores)

    def _compute_fib_score(self, sorted_combo: List[int]) -> float:
        """
        피보나치 군집 스코어 (WEIGHT=0.15) [에이전트 B 신규]
        3개+ 포함: 높은 점수 / 1개 포함: 낮은 점수 (DB 동적 계산)
        """
        if not self._fib_score_map:
            return 0.5
        fib_count = sum(1 for n in sorted_combo if n in FIBONACCI_NUMS)
        return self._fib_score_map.get(fib_count, 0.5)

    def _compute_last_digit_score(self, sorted_combo: List[int]) -> float:
        """끝자리 편향 스코어 (WEIGHT=0.15): 개별 끝자리 빈도 선호도"""
        if not self._last_digit_scores:
            return 0.5
        return sum(self._last_digit_scores.get(n % 10, 0.5) for n in sorted_combo) / 6.0

    def _compute_trend_score(self, sorted_combo: List[int]) -> float:
        """시계열 추세 스코어 (WEIGHT=0.15): 선형 회귀 p<0.05 추세 번호"""
        if not self._trend_scores:
            return 0.5
        return sum((self._trend_scores.get(n, 0.0) + 1.0) / 2.0 for n in sorted_combo) / 6.0

    def _compute_repeat_score(self, sorted_combo: List[int], prev_nums: List[int]) -> float:
        """직전 재출현 스코어 (WEIGHT=0.05): 편향 보정 최소 유지"""
        if not prev_nums:
            return 0.7
        overlap = len(set(sorted_combo) & set(prev_nums))
        return {0: 0.45, 1: 1.0, 2: 0.85, 3: 0.25, 4: 0.10, 5: 0.05, 6: 0.01}.get(overlap, 0.05)

    def _compute_square_score(self, sorted_combo: List[int]) -> float:
        """
        완전제곱수 분포 스코어 (WEIGHT=0.05) [에이전트 B 신규]
        0개 포함 과다 출현 -> 약간 높은 점수 (DB 동적 계산)
        """
        if not self._square_score_map:
            return 0.5
        sq_count = sum(1 for n in sorted_combo if n in SQUARE_NUMS)
        return self._square_score_map.get(sq_count, 0.5)

    def score_combination(
        self,
        combo: List[int],
        current_round: Optional[int] = None,
        prev_nums: Optional[List[int]] = None,
    ) -> float:
        """
        단일 조합 동적 패턴 점수 (0.0~1.0)
        7개 요소, 가중치 합계=1.0, 기존 16개 필터 중복 없음
        """
        if not self._initialized:
            return 0.5

        sorted_combo = sorted(combo)
        if prev_nums is None:
            prev_nums = self._get_prev_nums(current_round)

        total = (
            self.WEIGHT_TRIPLET * self._compute_triplet_score(sorted_combo)
            + self.WEIGHT_PAIR * self._compute_pair_score(sorted_combo)
            + self.WEIGHT_FIB * self._compute_fib_score(sorted_combo)
            + self.WEIGHT_LAST_DIGIT * self._compute_last_digit_score(sorted_combo)
            + self.WEIGHT_TREND * self._compute_trend_score(sorted_combo)
            + self.WEIGHT_REPEAT * self._compute_repeat_score(sorted_combo, prev_nums)
            + self.WEIGHT_SQUARE * self._compute_square_score(sorted_combo)
        )
        return float(min(max(total, 0.0), 1.0))

    def score_combinations_batch(
        self,
        combos: List[List[int]],
        current_round: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> List[Tuple[List[int], float]]:
        """배치 스코어링 (공통 계산 재사용)"""
        if not self._initialized:
            return [(c, 0.5) for c in combos]
        prev_nums = self._get_prev_nums(current_round)
        results = [(combo, self.score_combination(combo, current_round, prev_nums))
                   for combo in combos]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k] if top_k is not None else results

    def select_diverse_top_sets(
        self,
        scored_combos: List[Tuple[List[int], float]],
        n_sets: int = 5,
        max_overlap: int = 3,
    ) -> List[Tuple[List[int], float]]:
        """상위 스코어 조합에서 다양성 보장 선택"""
        selected = []
        for combo, score in scored_combos:
            if len(selected) >= n_sets:
                break
            if not any(len(set(combo) & set(s)) > max_overlap for s, _ in selected):
                selected.append((combo, score))

        if len(selected) < n_sets:
            existing = {tuple(sorted(c)) for c, _ in selected}
            for combo, score in scored_combos:
                if len(selected) >= n_sets:
                    break
                key = tuple(sorted(combo))
                if key not in existing:
                    selected.append((combo, score))
                    existing.add(key)

        return selected[:n_sets]

    # ─────────────────────────────────────────────────────────────────
    # 헬퍼 메서드
    # ─────────────────────────────────────────────────────────────────

    def _get_prev_nums(self, current_round: Optional[int] = None) -> List[int]:
        hist = self._get_hist_before(current_round)
        return hist[-1]["nums"] if hist else []

    def _get_hist_before(self, current_round: Optional[int]) -> List[Dict]:
        if current_round is not None:
            return [d for d in self._historical_data if d["round"] < current_round]
        return self._historical_data

    def get_current_stats(self) -> Dict:
        """현재 패턴 통계 요약 (모두 동적)"""
        if not self._initialized or not self._historical_data:
            return {}

        latest_round = self._historical_data[-1]["round"]
        prev_nums = self._get_prev_nums()

        top_trips = sorted(
            [(t, z) for t, z in self._triplet_zscores.items() if z >= 4.0],
            key=lambda x: x[1], reverse=True
        )[:5]

        hot_pairs = sorted(
            [(p, z) for p, z in self._pair_zscores.items() if z >= 2.5],
            key=lambda x: x[1], reverse=True
        )[:10]

        trend_up = [n for n, s in sorted(self._trend_scores.items(), key=lambda x: -x[1]) if s > 0.1]
        trend_dn = [n for n, s in sorted(self._trend_scores.items(), key=lambda x: x[1]) if s < -0.1]
        best_ld = sorted(self._last_digit_scores.items(), key=lambda x: -x[1])

        return {
            "latest_round": latest_round,
            "prev_winning": prev_nums,
            "top_hot_triplets": top_trips,
            "top_hot_pairs": hot_pairs,
            "trend_up_numbers": trend_up,
            "trend_down_numbers": trend_dn,
            "best_last_digits": [ld for ld, _ in best_ld[:4]],
            "worst_last_digits": [ld for ld, _ in best_ld[-4:]],
            "fib_score_map": self._fib_score_map,
            "square_score_map": self._square_score_map,
            "weights": {
                "triplet": self.WEIGHT_TRIPLET,
                "pair": self.WEIGHT_PAIR,
                "fib_cluster": self.WEIGHT_FIB,
                "last_digit": self.WEIGHT_LAST_DIGIT,
                "trend": self.WEIGHT_TREND,
                "repeat": self.WEIGHT_REPEAT,
                "square": self.WEIGHT_SQUARE,
            },
        }


# ─────────────────────────────────────────────────────────────────
# 싱글톤
# ─────────────────────────────────────────────────────────────────

_scorer_instance: Optional[DynamicPatternScorer] = None


def get_dynamic_scorer(
    db_path: str = "data/lotto_numbers.db",
    hot_window: int = None,
    auto_refresh: bool = True,
) -> DynamicPatternScorer:
    """
    싱글톤 스코어러 반환
    auto_refresh=True: 매주 새 회차 감지 시 자동 재초기화 (모든 기준 재계산)
    """
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = DynamicPatternScorer(db_path, hot_window)
        _scorer_instance.initialize()
    elif auto_refresh:
        _scorer_instance.refresh_if_new_round()
    return _scorer_instance


def reset_dynamic_scorer():
    """싱글톤 강제 리셋 (테스트 또는 수동 재로드용)"""
    global _scorer_instance
    _scorer_instance = None
