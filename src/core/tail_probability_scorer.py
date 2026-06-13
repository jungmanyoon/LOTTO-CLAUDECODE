# -*- coding: utf-8 -*-
"""
비모수 꼬리확률 극단성 스코어러 (TailProbabilityScorer) - 프로토타입 (검증 전용)

배경(2026-06-07): 현행 ExtremenessScorer 는 점수 = 마할라노비스거리^2(연속9) + 페널티(이산4)
인데, 진단 결과 마할라노비스(=역사 평균에서의 거리)가 제거를 압도(+6.06 vs 페널티 +1.28)하여
"역사상 드문 패턴"이 아니라 "역사 평균에서 먼 조합"을 제거하고 있었다(사용자 의도 불일치 +
가장자리 1,45 과잉제거 98.5% + 당첨보존율 19.8% ~ 무작위 18.4%).

본 프로토타입은 그 제거 기준을 "비모수 꼬리확률(역사적 희귀도)"로 교체한다. 이는 사용자가
원래 선호한 "각 패턴별 역사상 출현율 낮은 극단만 명시적으로 제거"하는 16패턴 방식을, 풀 크기
직접 제어가 가능한 단일 점수 형태로 정식화한 것이다.

핵심 수식(Codex gpt-5.5 + Gemini 3.1-pro 합의):
  - 각 특징 f 에 대해 역사 당첨번호의 "포함 경험 꼬리확률"을 Jeffreys 평활(alpha=0.5)로 추정:
      C_L(x) = #{Y_i <= x},  C_U(x) = #{Y_i >= x}      (inclusive survival; 단순 1-eCDF 금지)
      p_L = (C_L + a) / (N + 2a),  p_U = (C_U + a) / (N + 2a)
      P_f(x) = min(p_L, p_U)        # 좌/우 꼬리 중 가까운 쪽의 희귀도
      z_f(x) = -ln(P_f(x))          # 클수록 역사적으로 드문 극단
    역사에 없던 값은 자연히 하한 P = a/(N+2a) -> 최대 페널티(폭주 cap 내장).
  - 다중 특징 합산 시 '상관 이중카운팅'(예: range-max_gap 동시 극단)을 막기 위해 mode 제공:
      mode='max'       : S = max_f z_f                 (옛 16패턴 AND/거부권 재현 - 어느 한 특징이라도 꼬리면 제거)
      mode='sum'       : S = sum_f z_f                 (보정 없음, 원안/대조군)
      mode='group_max' : S = sum_g max_{f in G_g} z_f  (상관군 대표 1개만 - Codex 권장/기본)
      mode='copula'    : S = z^T R^-1 z, z=Phi^-1(eCDF) (가우시안 코퓰러 랭크 - Gemini 권장)

    [옛 16패턴 방식과의 관계] 사용자가 선호한 옛 16패턴 필터는 "각 패턴이 독립 거부권을 가져,
    어느 한 패턴이라도 역사적으로 거의 안 나온 극단값이면 그 조합을 제거(AND 결합)"하는 구조다.
    이를 동일 특징/동일 역사 꼬리확률 기준에서 점수화하면 정확히 mode='max'(가장 극단인 특징
    하나가 점수를 결정)가 된다. 따라서 mode 만 바꾸면 옛 방식(AND) vs 신 방식(합산/군합산)을
    '결합 방식'만 달리하여 공정 비교할 수 있다. (실제 옛 필터 코드를 blind 로 돌리려면 production
    수정 + combinations_db 저장 + fold 당 ~3.5분 + threshold 로 풀크기 비제어 문제가 있어 부적합.)
  - 점수 상위(가장 극단)부터 제거하여 목표 풀 크기 K 유지.

투명성: explain(combo) 로 "어느 특징이 역사 하위 몇% 꼬리라 제거됐는가"를 사람이 읽는 형태로 출력.

주의: 본 파일은 프로토타입이다. 검증(blind walk-forward) 통과 + 사용자 승인 전에는
production(extremeness_scorer.py / extremeness_pool_predictor.py)을 절대 변경하지 않는다.
특징 추출은 ExtremenessScorer 의 검증된 함수를 그대로 재사용하여 현행과 '같은 특징 정의'로
공정 비교한다.
"""
import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS

try:
    from scipy.special import ndtri  # 표준정규 역CDF (copula 모드용)
    from scipy.stats import rankdata
    _HAS_SCIPY = True
except Exception:  # scipy 없으면 copula 모드 비활성(sum/group_max 는 정상 동작)
    _HAS_SCIPY = False


# 가장자리(양끝) 번호 - 생존율 가드레일 대상
EDGE_NUMBERS = (1, 2, 3, 4, 5, 41, 42, 43, 44, 45)


class TailProbabilityScorer:
    """비모수 양측 꼬리확률 기반 극단성 스코어러 (프로토타입)."""

    # 점수에 사용하는 특징 (Codex 권장: 중복/가장자리주범 제거)
    #  - 제외: std, low_count(=sum과 중복+가장자리 과잉제거 주범), distinct_last_digits(=max_same_last_digit 중복)
    #  - odd_count 는 연속/이산 양쪽에 있으나 한 번만(이산 취급, 양측꼬리)
    FEATURE_SET: Tuple[str, ...] = (
        'sum', 'range', 'max_gap', 'ac_value', 'prime_count',          # 연속/순서형 (양측 꼬리)
        'odd_count', 'max_consecutive', 'max_same_last_digit', 'max_section_occupancy',  # 이산
    )

    # 상관군 (Spearman |rho|>=0.65 사전군집 - 검증 스크립트가 실제 상관으로 확인/조정).
    # group_max 모드에서 군별 대표(최대 z) 하나만 합산 -> 상관 이중카운팅 완화.
    DEFAULT_GROUPS: Tuple[Tuple[str, ...], ...] = (
        ('sum',),
        ('range', 'max_gap'),
        ('odd_count',),
        ('max_consecutive', 'max_section_occupancy', 'ac_value'),
        ('max_same_last_digit',),
        ('prime_count',),
    )

    def __init__(self, db_manager, alpha: float = 0.5, mode: str = 'group_max',
                 feature_set: Optional[Sequence[str]] = None,
                 groups: Optional[Sequence[Sequence[str]]] = None,
                 copula_reg: float = 0.05):
        self.db = db_manager
        self.alpha = float(alpha)            # Jeffreys 평활 상수
        self.mode = mode                     # 'sum' | 'group_max' | 'copula'
        self.feature_set = tuple(feature_set) if feature_set else self.FEATURE_SET
        self.groups = tuple(tuple(g) for g in (groups or self.DEFAULT_GROUPS))
        self.copula_reg = float(copula_reg)  # copula R 정칙화 (n=1227 안정화)
        self.logger = logging.getLogger(__name__)

        self._sorted: Dict[str, np.ndarray] = {}   # 특징별 정렬된 역사값
        self._N = 0
        self._R_inv: Optional[np.ndarray] = None   # copula 모드 R^-1
        self._fitted = False

        if self.mode == 'copula' and not _HAS_SCIPY:
            raise RuntimeError("copula 모드는 scipy 필요 (scipy.special.ndtri/scipy.stats.rankdata)")

    # ------------------------------------------------------------------
    # 특징 추출 (현행 ExtremenessScorer 와 '동일 정의' 재사용 -> 공정 비교)
    # ------------------------------------------------------------------
    @classmethod
    def _all_features(cls, combos: np.ndarray) -> Dict[str, np.ndarray]:
        """(M,6) 조합 -> {특징이름: (M,) float64}. 연속9 + 이산4 전부 추출."""
        combos = ExtremenessScorer._to_array(combos)
        F = ExtremenessScorer._continuous_features(combos)   # (M,9), CONTINUOUS_FEATURES 순서
        out: Dict[str, np.ndarray] = {}
        for i, name in enumerate(ExtremenessScorer.CONTINUOUS_FEATURES):
            out[name] = F[:, i].astype(np.float64)
        disc = ExtremenessScorer._discrete_values(combos)    # dict
        for name, arr in disc.items():
            out[name] = arr.astype(np.float64)               # 이산은 연속이름과 odd_count만 겹침(이산값으로 덮음)
        return out

    # ------------------------------------------------------------------
    # 학습 (역사적 당첨번호 분포)
    # ------------------------------------------------------------------
    def _winning_until(self, round_num: Optional[int]) -> np.ndarray:
        rows = []
        for r, numbers_str, _date in self.db.get_all_numbers():
            if round_num is not None and r > round_num:
                continue
            rows.append(sorted(int(x) for x in numbers_str.split(',')))
        return np.array(rows, dtype=np.int16)

    def fit(self, winning: np.ndarray):
        """역사 당첨번호 (N,6) 로 특징별 분포(정렬값) + (copula) 상관행렬 학습."""
        winning = ExtremenessScorer._to_array(winning)
        self._N = int(winning.shape[0])
        feats = self._all_features(winning)
        self._sorted = {name: np.sort(feats[name]) for name in self.feature_set}

        if self.mode == 'copula':
            # Spearman 상관 = 랭크의 Pearson. (D,N) 랭크 행렬 -> 상관 -> 정칙화 -> 역행렬.
            cols = [rankdata(feats[name]) for name in self.feature_set]
            ranks = np.vstack(cols).astype(np.float64)      # (D,N)
            R = np.corrcoef(ranks)                          # (D,D)
            R = R + np.eye(R.shape[0]) * self.copula_reg
            self._R_inv = np.linalg.pinv(R).astype(np.float64)

        self._fitted = True
        self.logger.info(
            f"[TailProbScorer] fit 완료: N={self._N}, mode={self.mode}, "
            f"특징={len(self.feature_set)}개, 군={len(self.groups)}개")
        return self

    def fit_until(self, round_num: Optional[int] = None):
        return self.fit(self._winning_until(round_num))

    # ------------------------------------------------------------------
    # 꼬리확률 / z
    # ------------------------------------------------------------------
    def _tail_prob(self, name: str, x: np.ndarray) -> np.ndarray:
        """inclusive 양측 경험 꼬리확률 P_f(x) = min(p_L, p_U), Jeffreys 평활."""
        Ys = self._sorted[name]
        N = self._N
        a = self.alpha
        # C_L = #{Y<=x}, C_U = #{Y>=x}
        cl = np.searchsorted(Ys, x, side='right').astype(np.float64)
        cu = (N - np.searchsorted(Ys, x, side='left')).astype(np.float64)
        p_l = (cl + a) / (N + 2 * a)
        p_u = (cu + a) / (N + 2 * a)
        return np.minimum(p_l, p_u)

    def _tail_z(self, name: str, x: np.ndarray) -> np.ndarray:
        return -np.log(self._tail_prob(name, x))

    def _cdf_z(self, name: str, x: np.ndarray) -> np.ndarray:
        """copula 모드: z = Phi^-1(eCDF_f(x)), Jeffreys 평활 + clip."""
        Ys = self._sorted[name]
        N = self._N
        a = self.alpha
        cl = np.searchsorted(Ys, x, side='right').astype(np.float64)
        cdf = (cl + a) / (N + 2 * a)
        cdf = np.clip(cdf, 1e-6, 1.0 - 1e-6)
        return ndtri(cdf)

    # ------------------------------------------------------------------
    # 채점
    # ------------------------------------------------------------------
    def score(self, combos, chunk_size: int = 1_000_000) -> np.ndarray:
        """조합 극단성 점수 (높을수록 극단 -> 우선 제거). 대량은 청크 처리."""
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출 필요")
        combos = ExtremenessScorer._to_array(combos)
        M = combos.shape[0]
        out = np.empty(M, dtype=np.float64)
        for s in range(0, M, chunk_size):
            e = min(s + chunk_size, M)
            feats = self._all_features(combos[s:e])
            out[s:e] = self._score_chunk(feats)
        return out

    def _score_chunk(self, feats: Dict[str, np.ndarray]) -> np.ndarray:
        if self.mode == 'max':
            # 옛 16패턴 AND/거부권: 가장 극단인 특징 하나가 점수를 결정 (어느 한 특징이라도 꼬리면 제거).
            zs = [self._tail_z(name, feats[name]) for name in self.feature_set]
            return np.maximum.reduce(zs)
        if self.mode == 'sum':
            acc = None
            for name in self.feature_set:
                z = self._tail_z(name, feats[name])
                acc = z if acc is None else acc + z
            return acc
        if self.mode == 'group_max':
            acc = None
            for g in self.groups:
                zs = [self._tail_z(f, feats[f]) for f in g if f in self.feature_set]
                if not zs:
                    continue
                zmax = np.maximum.reduce(zs) if len(zs) > 1 else zs[0]
                acc = zmax if acc is None else acc + zmax
            return acc
        if self.mode == 'copula':
            Z = np.vstack([self._cdf_z(f, feats[f]) for f in self.feature_set])  # (D,m)
            # z_i^T R^-1 z_i  for each column i
            return np.einsum('di,dk,ki->i', Z, self._R_inv, Z)
        raise ValueError(f"알 수 없는 mode: {self.mode}")

    # ------------------------------------------------------------------
    # 풀 선택
    # ------------------------------------------------------------------
    @staticmethod
    def cutoff_for_size(scores: np.ndarray, target_size: int) -> float:
        target_size = min(max(target_size, 1), len(scores))
        return float(np.partition(scores, target_size - 1)[target_size - 1])

    @staticmethod
    def select_pool(scores: np.ndarray, target_size: int) -> np.ndarray:
        """가장 덜 극단적인 target_size개 인덱스."""
        target_size = min(max(target_size, 1), len(scores))
        return np.argpartition(scores, target_size - 1)[:target_size]

    def select_pool_guarded(self, scores: np.ndarray, combos: np.ndarray,
                            target_size: int, edge: Sequence[int] = EDGE_NUMBERS,
                            tau: float = 0.01, max_iter: int = 6,
                            lam_step: float = 0.25, lam_cap: float = 1.0
                            ) -> Tuple[np.ndarray, Dict]:
        """번호 생존율 가드레일(Codex 라그랑주). 가장자리 번호 생존율 r_j >= q-tau 강제.

        S_lambda(c) = S(c) - sum_{j in edge} lam_j * 1(j in c). 과소생존 번호에 점수 감점.
        반환: (pool_idx, info). info 에 반복/생존율 진단.
        """
        N_total = len(scores)
        q = target_size / N_total
        lam = {int(j): 0.0 for j in edge}
        # 번호 포함 마스크 사전계산 (edge 번호만)
        edge_mask = {int(j): (combos == j).any(axis=1) for j in edge}
        info = {'q': q, 'iters': 0, 'final_survival': {}}
        pool_idx = self.select_pool(scores, target_size)
        for it in range(max_iter):
            adj = scores
            if any(v > 0 for v in lam.values()):
                adj = scores.copy()
                for j, l in lam.items():
                    if l > 0:
                        adj[edge_mask[j]] -= l
            pool_idx = self.select_pool(adj, target_size)
            keep = np.zeros(N_total, dtype=bool)
            keep[pool_idx] = True
            short = []
            surv = {}
            for j in edge:
                jm = edge_mask[j]
                denom = int(jm.sum())
                r_j = float((keep & jm).sum() / denom) if denom else 1.0
                surv[int(j)] = r_j
                if r_j < q - tau and lam[int(j)] < lam_cap:
                    short.append(int(j))
            info['iters'] = it + 1
            info['final_survival'] = surv
            if not short:
                break
            for j in short:
                lam[j] = min(lam_cap, lam[j] + lam_step)
        info['lambda'] = lam
        return pool_idx, info

    # ------------------------------------------------------------------
    # 투명성: 제거 사유 설명
    # ------------------------------------------------------------------
    def explain(self, combo) -> List[Dict]:
        """단일 조합의 특징별 꼬리확률/희귀도 사유 (z 내림차순)."""
        arr = ExtremenessScorer._to_array([combo])
        feats = self._all_features(arr)
        N = self._N
        a = self.alpha
        rows = []
        for name in self.feature_set:
            x = feats[name]
            Ys = self._sorted[name]
            cl = float(np.searchsorted(Ys, x[0], side='right'))
            cu = float(N - np.searchsorted(Ys, x[0], side='left'))
            p_l = (cl + a) / (N + 2 * a)
            p_u = (cu + a) / (N + 2 * a)
            side = 'low' if p_l <= p_u else 'high'
            p = min(p_l, p_u)
            rows.append({
                'feature': name,
                'value': float(x[0]),
                'tail_side': side,
                'tail_pct': round(p * 100.0, 3),  # 역사적으로 이 방향 꼬리 몇 %
                'z': round(-math.log(p), 3),
            })
        rows.sort(key=lambda r: r['z'], reverse=True)
        return rows

    def coverage(self, holdout_winning, cutoff: float) -> float:
        # [2026-06-13] 빈 입력 가드를 _to_array 앞으로 이동. _to_array([])는 1D (0,) 배열에
        # arr.sort(axis=1)을 호출해 AxisError로 크래시했다(빈 holdout=1.0 계약이 도달 불가였음).
        # -> None/빈 입력을 먼저 처리해 빈 fold에서도 안전하게 1.0 반환.
        if holdout_winning is None or len(holdout_winning) == 0:
            return 1.0
        w = ExtremenessScorer._to_array(holdout_winning)
        if len(w) == 0:
            return 1.0
        s = self.score(w)
        return float((s <= cutoff).mean())
