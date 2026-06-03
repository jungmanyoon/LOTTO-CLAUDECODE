"""
극단성 점수 엔진 (ExtremenessScorer)

설계 합의 (2026-05-31, Codex gpt-5.5 + Gemini 3.1-pro + Claude 교차검증):
  - "16개 독립 AND 필터"를 폐기하고, 각 조합에 단일 "극단성 점수(extremeness score)"를
    부여한 뒤 "목표 풀 크기 K"가 되도록 점수 상위(가장 극단적)부터 제거하는 단일 컷오프로
    제어한다. -> AND 누적 과필터링(1-(1-p)^16) 문제가 원천 소멸하고, 풀 크기가 직접·단조 제어됨.

극단성 점수 = 마할라노비스 거리(연속 극단) + 비모수 꼬리 페널티(이산 희귀 극단)
  score(x) = d2_mahalanobis(x) + sum_k w_k * penalty_k(x)
    - d2 = (x - mu)^T Sigma^-1 (x - mu)
        : 역사적 당첨번호의 평균/공분산 기준. 차원 간 상관(sum vs average 등)을 Sigma^-1이
          자동 보정하여 중복 가중을 방지.
    - penalty_k = -log((count_k + alpha) / (N + alpha * bins))
        : 역사적으로 거의 안 나온(0~1회) 이산 패턴(최장연속, 동일끝자리수, 구간몰림 등)에
          큰 페널티. 가우시안 가정의 마할라노비스가 놓치는 이산 극단을 상보적으로 포착.

핵심 전략(사용자 확정): "역사상 출현율 극히 낮은 극단 패턴을 최대한 많이 제거 -> 남은 풀에서
다양성 예측". 통과율은 강제 제약이 아니라 참고 지표(coverage).

사용 예:
  scorer = ExtremenessScorer(db)
  scorer.fit_until(round_num=1226)            # 1226회까지 당첨번호로 분포 학습
  combos = ExtremenessScorer.all_combinations()  # (8145060, 6) int8
  scores = scorer.score(combos)                # (8145060,) float32
  pool_idx = scorer.select_pool(scores, target_size=300_000)  # 가장 덜 극단인 30만
"""
import logging
import math
from itertools import combinations
from typing import List, Optional, Tuple

import numpy as np

TOTAL_COMBINATIONS = 8_145_060  # C(45, 6)
PRIMES_1_45 = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}


class ExtremenessScorer:
    """단일 극단성 점수 기반 풀 제어 엔진."""

    # 전체 조합 배열 캐시 (클래스 레벨).
    # all_combinations()는 params와 무관한 순수 상수 배열(8.14M x 6 int8 ~49MB)이므로
    # 최초 1회만 생성하고 이후 재사용한다. PoolOptimizer가 trial마다 호출하던
    # np.fromiter 전수 재생성(+GC 압박)을 제거한다. (결과 배열 동일성 보장: 동일 입력->동일 출력)
    _ALL_COMBINATIONS_CACHE: Optional[np.ndarray] = None

    # 마할라노비스에 쓰는 연속/순서형 특징 (완전상관 변수는 하나만: average는 sum과 100% 상관 -> 제외)
    CONTINUOUS_FEATURES = [
        'sum', 'std', 'max_gap', 'range', 'odd_count',
        'low_count', 'ac_value', 'prime_count', 'distinct_last_digits',
    ]
    # 비모수 꼬리 페널티에 쓰는 이산 차원 (역사적 희귀 극단 포착)
    PENALTY_DIMS = [
        'max_consecutive',       # 최장 연속 길이 (1~6)
        'odd_count',             # 홀수 개수 (0~6)
        'max_same_last_digit',   # 동일 끝자리 최대 개수 (1~6)
        'max_section_occupancy', # 십구간(5분할) 최대 점유 (1~6)
    ]

    def __init__(self, db_manager, alpha: float = 0.5, penalty_weights: Optional[dict] = None):
        self.db = db_manager
        self.alpha = alpha  # 라플라스 평활 상수
        self.penalty_weights = penalty_weights or {d: 1.0 for d in self.PENALTY_DIMS}
        self.logger = logging.getLogger(__name__)

        self.mu = None
        self.cov_inv = None
        self._penalty_tables = {}  # dim -> {value: penalty}
        self._feature_scale = None  # PoolOptimizer가 주입하는 가중 마할라노비스 스케일 (D,)
        self._fitted = False

    # ------------------------------------------------------------------
    # 조합 생성 / 특징 추출 (벡터화)
    # ------------------------------------------------------------------
    @classmethod
    def all_combinations(cls) -> np.ndarray:
        """전체 C(45,6) 조합을 (8145060, 6) int8 배열로 생성 (오름차순).

        params 무관 상수 배열이므로 클래스 레벨 캐시에 1회 생성 후 재사용한다.
        반환 배열은 읽기 전용(writeable=False)으로 표시하여 캐시 오염을 방지한다
        (score() 등은 내부에서 _to_array로 astype 복사하므로 원본을 변형하지 않음).
        """
        if cls._ALL_COMBINATIONS_CACHE is None:
            arr = np.fromiter(
                (n for combo in combinations(range(1, 46), 6) for n in combo),
                dtype=np.int8, count=TOTAL_COMBINATIONS * 6,
            )
            arr = arr.reshape(TOTAL_COMBINATIONS, 6)
            arr.setflags(write=False)  # 캐시 무결성 보호 (호출자 우발 변형 차단)
            cls._ALL_COMBINATIONS_CACHE = arr
        return cls._ALL_COMBINATIONS_CACHE

    @staticmethod
    def _to_array(combos) -> np.ndarray:
        """리스트/문자열 조합을 정렬된 (M,6) int 배열로 변환."""
        if isinstance(combos, np.ndarray):
            arr = combos.astype(np.int16)
        else:
            rows = []
            for c in combos:
                if isinstance(c, str):
                    rows.append([int(x) for x in c.split(',')])
                else:
                    rows.append(list(c))
            arr = np.array(rows, dtype=np.int16)
        arr.sort(axis=1)
        return arr

    @classmethod
    def _continuous_features(cls, combos: np.ndarray) -> np.ndarray:
        """(M,6) -> (M, D) 연속 특징 행렬 (float32). CONTINUOUS_FEATURES 순서."""
        c = combos.astype(np.float32)
        M = c.shape[0]
        gaps = np.diff(c, axis=1)  # (M,5)

        sum_ = c.sum(axis=1)
        std_ = c.std(axis=1)
        max_gap = gaps.max(axis=1)
        rng = c[:, -1] - c[:, 0]
        odd = (combos % 2 == 1).sum(axis=1).astype(np.float32)
        low = (combos <= 22).sum(axis=1).astype(np.float32)

        # AC value = (서로 다른 양의 차이 개수) - (n-1=5)
        ci = combos.astype(np.int16)
        # 15개 쌍 차이
        pair_idx = np.array(list(combinations(range(6), 2)))  # (15,2)
        diffs = np.abs(ci[:, pair_idx[:, 1]] - ci[:, pair_idx[:, 0]])  # (M,15)
        ds = np.sort(diffs, axis=1)
        distinct_diffs = 1 + (ds[:, 1:] != ds[:, :-1]).sum(axis=1)
        ac = (distinct_diffs - 5).astype(np.float32)

        # 소수 개수
        is_prime = np.zeros(46, dtype=bool)
        for p in PRIMES_1_45:
            is_prime[p] = True
        prime_count = is_prime[combos].sum(axis=1).astype(np.float32)

        # 서로 다른 끝자리 개수
        last = (combos % 10).astype(np.int16)
        ls = np.sort(last, axis=1)
        distinct_last = (1 + (ls[:, 1:] != ls[:, :-1]).sum(axis=1)).astype(np.float32)

        F = np.column_stack([
            sum_, std_, max_gap, rng, odd, low, ac, prime_count, distinct_last,
        ]).astype(np.float32)
        return F

    @classmethod
    def _discrete_values(cls, combos: np.ndarray) -> dict:
        """페널티용 이산 차원 값들 -> {dim: (M,) int 배열}."""
        gaps = np.diff(combos.astype(np.int16), axis=1)  # (M,5)
        isc = (gaps == 1).astype(np.int16)

        # 최장 연속 길이
        best = np.zeros(combos.shape[0], dtype=np.int16)
        cur = np.zeros(combos.shape[0], dtype=np.int16)
        for j in range(isc.shape[1]):
            cur = (cur + 1) * isc[:, j]
            best = np.maximum(best, cur)
        max_consecutive = best + 1  # 연속 없으면 1

        odd = (combos % 2 == 1).sum(axis=1).astype(np.int16)

        last = (combos % 10).astype(np.int16)
        max_same_last = np.zeros(combos.shape[0], dtype=np.int16)
        for d in range(10):
            cnt = (last == d).sum(axis=1).astype(np.int16)
            max_same_last = np.maximum(max_same_last, cnt)

        sec = np.minimum((combos.astype(np.int16) - 1) // 10, 4)  # 0..4
        max_sec = np.zeros(combos.shape[0], dtype=np.int16)
        for s in range(5):
            cnt = (sec == s).sum(axis=1).astype(np.int16)
            max_sec = np.maximum(max_sec, cnt)

        return {
            'max_consecutive': max_consecutive,
            'odd_count': odd,
            'max_same_last_digit': max_same_last,
            'max_section_occupancy': max_sec,
        }

    # ------------------------------------------------------------------
    # 학습 (역사적 당첨번호 분포)
    # ------------------------------------------------------------------
    def _winning_arrays_until(self, round_num: Optional[int]) -> np.ndarray:
        """round_num 이하(또는 전체) 당첨번호를 (N,6) 배열로 반환."""
        rows = []
        for r, numbers_str, _date in self.db.get_all_numbers():
            if round_num is not None and r > round_num:
                continue
            rows.append(sorted(int(x) for x in numbers_str.split(',')))
        return np.array(rows, dtype=np.int16)

    def fit(self, winning: np.ndarray):
        """당첨번호 배열 (N,6)로 mu/Sigma^-1 및 페널티 테이블 학습."""
        winning = self._to_array(winning)
        N = winning.shape[0]

        F = self._continuous_features(winning)
        self.mu = F.mean(axis=0)
        cov = np.cov(F, rowvar=False)
        # 특이행렬 방지: 의사역행렬 + 미세 정칙화
        cov = cov + np.eye(cov.shape[0], dtype=cov.dtype) * 1e-6
        self.cov_inv = np.linalg.pinv(cov).astype(np.float32)

        # 페널티 테이블: dim 값별 -log 평활빈도
        disc = self._discrete_values(winning)
        self._penalty_tables = {}
        for dim in self.PENALTY_DIMS:
            vals = disc[dim]
            max_v = int(vals.max()) if len(vals) else 6
            bins = max(max_v + 1, 7)
            counts = np.bincount(vals, minlength=bins).astype(np.float64)
            # 가능한 모든 값(0..6 등)에 대해 평활 빈도 -> 페널티
            table = {}
            for v in range(bins):
                cnt = counts[v] if v < len(counts) else 0
                p = (cnt + self.alpha) / (N + self.alpha * bins)
                table[v] = -math.log(p)
            self._penalty_tables[dim] = table

        self._fitted = True
        self.logger.info(f"[ExtremenessScorer] fit 완료: N={N}, 특징={len(self.CONTINUOUS_FEATURES)}, "
                         f"페널티차원={len(self.PENALTY_DIMS)}")
        return self

    def fit_until(self, round_num: Optional[int] = None):
        """round_num 이하 당첨번호로 학습 (None이면 전체)."""
        return self.fit(self._winning_arrays_until(round_num))

    # ------------------------------------------------------------------
    # 채점
    # ------------------------------------------------------------------
    def mahalanobis2(self, F: np.ndarray) -> np.ndarray:
        d = F - self.mu
        # (M,D)@(D,D) elementwise (M,D) -> sum axis1
        return np.einsum('ij,jk,ik->i', d, self.cov_inv, d).astype(np.float32)

    def _penalty_one_dim(self, dim: str, vals: np.ndarray) -> np.ndarray:
        """단일 페널티 차원 기여분 (가중치 적용 전 w*pen 그대로). penalty()/score()와
        동일한 수식/순서/dtype을 보장하기 위한 내부 단일소스.

        주의: w==0이면 0 배열을 반환한다. penalty()의 `continue`(아예 더하지 않음)와
        수치적으로 완전히 동일하다(0을 더하는 것과 더하지 않는 것은 같음)."""
        w = self.penalty_weights.get(dim, 1.0)
        if w == 0:
            return np.zeros(len(vals), dtype=np.float32)
        table = self._penalty_tables[dim]
        default = max(table.values())  # 미관측 값은 최대 페널티
        # np.unique를 한 번만 계산해 pen/lut 모두 재사용 (결과 불변, 효율 개선)
        uniq = np.unique(vals)
        pen = np.array([table.get(int(v), default) for v in uniq], dtype=np.float32)
        lut = {int(u): pen[i] for i, u in enumerate(uniq)}
        return w * np.array([lut[int(v)] for v in vals], dtype=np.float32)

    def penalty(self, combos: np.ndarray) -> np.ndarray:
        disc = self._discrete_values(combos)
        out = np.zeros(combos.shape[0], dtype=np.float32)
        for dim in self.PENALTY_DIMS:
            # _penalty_one_dim은 w==0이면 0 배열을 반환하므로 누적 결과 불변.
            out += self._penalty_one_dim(dim, disc[dim])
        return out

    def score(self, combos, chunk_size: int = 1_000_000) -> np.ndarray:
        """조합 점수 (높을수록 극단 -> 우선 제거). 대량은 청크 처리."""
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출 필요")
        combos = self._to_array(combos)
        M = combos.shape[0]
        if M <= chunk_size:
            F = self._continuous_features(combos)
            return self.mahalanobis2(F) + self.penalty(combos)
        out = np.empty(M, dtype=np.float32)
        for s in range(0, M, chunk_size):
            e = min(s + chunk_size, M)
            sub = combos[s:e]
            F = self._continuous_features(sub)
            out[s:e] = self.mahalanobis2(F) + self.penalty(sub)
        return out

    def score_components(self, combos, chunk_size: int = 1_000_000) -> dict:
        """score()와 '완전히 동일한 수식/순서/dtype'으로 점수를 계산하되, 성분별로 분해해
        반환한다(진단/로그 전용). total은 score()와 비트 단위로 동일하다.

        반환 dict:
          {
            'total': (M,) float32,                      # = mahalanobis2 + sum(penalty 차원)
            'mahalanobis2': (M,) float32,
            'pen_max_consecutive': (M,) float32,        # 가중치 적용 후 기여분 (w*penalty)
            'pen_odd_count': (M,) float32,
            'pen_max_same_last_digit': (M,) float32,
            'pen_max_section_occupancy': (M,) float32,
            'features': {                               # 직관 라벨용 이산 특징 (M,) int16
                'max_consecutive', 'odd_count',
                'max_same_last_digit', 'max_section_occupancy'
            }
          }

        동일성 보장: total[s:e] = mahalanobis2(F) + sum_dim(_penalty_one_dim(dim))
        이며, penalty()는 동일한 _penalty_one_dim을 동일 순서로 합산하므로
        total == score() (np.testing.assert_allclose rtol=0 atol=0 통과)."""
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출 필요")
        combos = self._to_array(combos)
        M = combos.shape[0]

        total = np.empty(M, dtype=np.float32)
        maha = np.empty(M, dtype=np.float32)
        pen_parts = {dim: np.empty(M, dtype=np.float32) for dim in self.PENALTY_DIMS}
        feat_parts = {dim: np.empty(M, dtype=np.int16) for dim in self.PENALTY_DIMS}

        for s in range(0, M, chunk_size):
            e = min(s + chunk_size, M)
            sub = combos[s:e]
            F = self._continuous_features(sub)
            m = self.mahalanobis2(F)
            maha[s:e] = m
            disc = self._discrete_values(sub)
            # 동일성 보장(핵심): score()는 `mahalanobis2(F) + penalty(sub)`이고
            # penalty()는 float32 0배열에서 PENALTY_DIMS 순서로 _penalty_one_dim을 누적한다.
            # 따라서 여기서도 '동일하게' float32 0에서 동일 순서로 페널티를 합산한 뒤
            # 마지막에 mahalanobis2를 더해야 부동소수 연산순서까지 일치한다.
            pen_sum = np.zeros(e - s, dtype=np.float32)
            for dim in self.PENALTY_DIMS:
                p = self._penalty_one_dim(dim, disc[dim])
                pen_parts[dim][s:e] = p
                feat_parts[dim][s:e] = disc[dim].astype(np.int16)
                pen_sum = pen_sum + p
            total[s:e] = m + pen_sum

        return {
            'total': total,
            'mahalanobis2': maha,
            'pen_max_consecutive': pen_parts['max_consecutive'],
            'pen_odd_count': pen_parts['odd_count'],
            'pen_max_same_last_digit': pen_parts['max_same_last_digit'],
            'pen_max_section_occupancy': pen_parts['max_section_occupancy'],
            'features': {
                'max_consecutive': feat_parts['max_consecutive'],
                'odd_count': feat_parts['odd_count'],
                'max_same_last_digit': feat_parts['max_same_last_digit'],
                'max_section_occupancy': feat_parts['max_section_occupancy'],
            },
        }

    # ------------------------------------------------------------------
    # 풀 선택 / 커버리지
    # ------------------------------------------------------------------
    @staticmethod
    def cutoff_for_size(scores: np.ndarray, target_size: int) -> float:
        """목표 풀 크기 K에 해당하는 점수 컷오프 (이 값 이하를 유지)."""
        target_size = min(max(target_size, 1), len(scores))
        # K번째로 작은 점수 = 컷오프
        return float(np.partition(scores, target_size - 1)[target_size - 1])

    @staticmethod
    def select_pool(scores: np.ndarray, target_size: int) -> np.ndarray:
        """가장 덜 극단적인 target_size개의 인덱스 반환."""
        target_size = min(max(target_size, 1), len(scores))
        idx = np.argpartition(scores, target_size - 1)[:target_size]
        return idx

    def coverage(self, holdout_winning, cutoff: float) -> float:
        """hold-out 당첨번호 중 점수<=cutoff(풀 포함) 비율."""
        w = self._to_array(holdout_winning)
        if len(w) == 0:
            return 1.0
        s = self.score(w)
        return float((s <= cutoff).mean())
