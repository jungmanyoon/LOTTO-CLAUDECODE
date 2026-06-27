"""
5장 다양성 선택기 (DiversitySelector) + 빈도 분석

NOTE (모듈 구분): 동명의 `src/utils/diversity_selector.py`(Farthest-Point Sampling, Hamming
거리 기반)와는 다른 구현이다. 이 `core` 버전은 가중 max-coverage(번호 커버리지 극대화)로
hold-out 검증에서 "3개+ 맞추기" 우위(6->13회)가 확인된 신 구현이며, production 1차 경로
(ExtremenessPoolPredictor)에서 사용한다. utils 버전은 구 ML-우선 경로(main.py:1521)의
폴백 보충용으로 잔존한다. 두 모듈은 import 경로가 달라 충돌하지 않는다.

설계 합의 (2026-05-31, Codex gpt-5.5 + Gemini 3.1-pro + Claude):
  - 풀 축소(극단 제거)만으로는 hold-out Lift~1.0 (당첨확률 향상 한계 명확).
  - "많은 번호 맞추기(3·4개 하위 등수 포함)"의 진짜 레버 = 5장의 번호 커버리지 극대화.
    => 최대 커버리지 문제(Maximum Coverage, NP-Hard)를 가중 그리디(63% 보장)로 푼다.

목적함수 (5장 집합 T):
  maximize  λ1*unique_coverage(T) + λ2*weighted_coverage(T) + λ3*Σ quality
            - λ4*pairwise_overlap_penalty(T)

제약 (Codex/Gemini 공통 권고):
  - 5장 전체 unique 번호 27~30개
  - 티켓 간 pairwise overlap <= 1
  - 한 번호 최대 반복 2회 (강한 번호만)

빈도 분석 (번호 가중치 w_n, n=1..45):
  사용자 전략("당첨확률 조금이라도 올리는 모든 방법") 반영. 단 노이즈 추종을 막기 위해
  여러 약신호를 평탄하게 결합(가중치 폭을 제한):
    w_n = 0.5(균등) + 0.5 * sigmoid_scaled(freq_z + recency_signal + ml_signal)
  - freq_z      : 전체 출현 빈도 표준화 (장기 빈도)
  - recency     : 최근 N회 출현 가중(hot) - 장기 미출현(cold) 보정
  - ml_signal   : (선택) 외부 ML pool-diversity 가중치 주입
"""
import logging
from itertools import combinations
from typing import List, Optional, Sequence, Tuple

import numpy as np


class FrequencyAnalyzer:
    """역사적 당첨번호 빈도/최근성 기반 번호 가중치(1..45) 산출."""

    def __init__(self, db_manager):
        self.db = db_manager
        self.logger = logging.getLogger(__name__)

    def _winning_arrays(self, until_round: Optional[int] = None) -> List[Tuple[int, List[int]]]:
        out = []
        for r, s, _ in self.db.get_all_numbers():
            if until_round is not None and r > until_round:
                continue
            out.append((r, sorted(int(x) for x in s.split(','))))
        return out

    def compute_weights(self, until_round: Optional[int] = None,
                        recency_window: int = 30, spread: float = 0.5,
                        ml_signal: Optional[np.ndarray] = None,
                        ml_beta: float = 0.4) -> np.ndarray:
        """번호별 가중치 (45,) 반환. 평균 1.0 근처, spread로 진폭 제어.

        spread=0이면 완전 균등(1.0), 클수록 빈도/최근성 신호 강조.

        Args:
            ml_signal: (45,) ML 예측 기반 번호 선호도(원시값). 주어지면 약신호로 결합.
                       핵심 전략상 ML은 "풀 내 다양성 가중치" 역할(당첨 예측 아님).
            ml_beta: ML 신호 결합 비중 (0=무시, 0.4=기본). 빈도/최근성과 평탄 결합.
        """
        rows = self._winning_arrays(until_round)
        if not rows:
            return np.ones(45, dtype=np.float32)

        rounds = [r for r, _ in rows]
        max_round = max(rounds)

        long_freq = np.zeros(46, dtype=np.float64)   # index 1..45
        recent_freq = np.zeros(46, dtype=np.float64)
        last_seen = {n: 0 for n in range(1, 46)}

        for r, nums in rows:
            for n in nums:
                long_freq[n] += 1
                if r > max_round - recency_window:
                    recent_freq[n] += 1
                last_seen[n] = max(last_seen[n], r)

        lf = long_freq[1:46]
        rf = recent_freq[1:46]
        # 장기 빈도 z-score
        fz = (lf - lf.mean()) / (lf.std() + 1e-9)
        # 최근 hot 신호 (최근 window 내 출현수 z-score)
        rz = (rf - rf.mean()) / (rf.std() + 1e-9)
        # cold 보정: 오래 안 나온 번호에 소폭 가산(미출현 회복 신호; 약하게)
        age = np.array([max_round - last_seen[n] for n in range(1, 46)], dtype=np.float64)
        az = (age - age.mean()) / (age.std() + 1e-9)

        # 약신호 결합 (각 0.5/0.3/0.2 비중)
        signal = 0.5 * fz + 0.3 * rz + 0.2 * az

        # ML 신호 결합 (있으면): 표준화 후 ml_beta 비중으로 가산 (평탄 결합, 노이즈 추종 방지)
        if ml_signal is not None and len(ml_signal) == 45:
            mz = np.asarray(ml_signal, dtype=np.float64)
            if mz.std() > 1e-9:
                mz = (mz - mz.mean()) / mz.std()
                signal = (1.0 - ml_beta) * signal + ml_beta * mz

        s = 1.0 / (1.0 + np.exp(-signal))           # (45,) in (0,1)
        weights = (1.0 - spread) + 2.0 * spread * s  # mean ~1.0, range [1-spread,1+spread]
        return weights.astype(np.float32)

    def get_pair_frequencies(self, until_round: Optional[int] = None,
                             normalize: bool = True) -> np.ndarray:
        """번호 쌍(i,j) 동시출현 빈도 행렬 (45,45) 반환 (0-based 인덱스, 대칭).

        triple-cover 선택기(DiversitySelector.select_triple_cover)의 triple 가중치
        (쌍빈도 합)에 사용. normalize=True면 양수 쌍 평균 1.0 근처로 정규화하여 단일빈도
        가중과 스케일을 맞춘다. 역사적으로 자주 함께 나온 쌍에 높은 값.
        """
        rows = self._winning_arrays(until_round)
        M = np.zeros((45, 45), dtype=np.float64)
        for _r, nums in rows:
            idx = [n - 1 for n in nums]
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    i, j = idx[a], idx[b]
                    M[i, j] += 1
                    M[j, i] += 1
        if normalize:
            pos = M[M > 0]
            mean = pos.mean() if pos.size else 1.0
            if mean > 0:
                M = M / mean
        return M.astype(np.float32)


class DiversitySelector:
    """필터링된 풀에서 5장을 번호 커버리지 극대화로 선택."""

    def __init__(self, number_weights: Optional[np.ndarray] = None,
                 lambda_cov: float = 1.0, lambda_wcov: float = 1.0,
                 lambda_quality: float = 0.3, lambda_overlap: float = 2.0,
                 max_number_repeat: int = 2, max_pairwise_overlap: int = 1):
        self.w = number_weights if number_weights is not None else np.ones(45, dtype=np.float32)
        self.lambda_cov = lambda_cov
        self.lambda_wcov = lambda_wcov
        self.lambda_quality = lambda_quality
        self.lambda_overlap = lambda_overlap
        self.max_number_repeat = max_number_repeat
        self.max_pairwise_overlap = max_pairwise_overlap
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _to_sets(pool) -> List[Tuple[int, ...]]:
        out = []
        for c in pool:
            if isinstance(c, str):
                out.append(tuple(int(x) for x in c.split(',')))
            else:
                out.append(tuple(int(x) for x in c))
        return out

    def select(self, pool, num_tickets: int = 5,
               quality: Optional[Sequence[float]] = None,
               candidate_sample: int = 20000, seed: int = 42,
               local_search_iters: int = 200) -> List[Tuple[int, ...]]:
        """풀에서 num_tickets개 선택.

        Args:
            pool: 조합 리스트 (문자열 'a,b,..' 또는 시퀀스)
            quality: 각 조합의 품질 점수(높을수록 좋음, 예: -극단성). None이면 0.
            candidate_sample: 그리디 평가용 후보 샘플 수 (속도/품질 trade-off)
            local_search_iters: 그리디 후 교체 개선 반복수
        """
        combos = self._to_sets(pool)
        n = len(combos)
        if n == 0:
            return []
        rng = np.random.RandomState(seed)

        if quality is None:
            quality = np.zeros(n, dtype=np.float32)
        else:
            quality = np.asarray(quality, dtype=np.float32)
        # 품질 정규화 (스케일 통일)
        if quality.std() > 1e-9:
            q_norm = (quality - quality.mean()) / quality.std()
        else:
            q_norm = quality

        # 후보 샘플링 (대형 풀 대비 속도)
        if n > candidate_sample:
            cand_idx = rng.choice(n, candidate_sample, replace=False)
        else:
            cand_idx = np.arange(n)

        selected_idx: List[int] = []
        covered = set()
        number_count = np.zeros(46, dtype=np.int16)

        def gain(idx) -> float:
            combo = combos[idx]
            new_nums = [x for x in combo if x not in covered]
            g = self.lambda_cov * len(new_nums)
            g += self.lambda_wcov * sum(self.w[x - 1] for x in new_nums)
            g += self.lambda_quality * float(q_norm[idx])
            # overlap penalty (이미 선택된 티켓들과)
            ov = 0
            for s_idx in selected_idx:
                inter = len(set(combo) & set(combos[s_idx]))
                ov += inter * inter
            g -= self.lambda_overlap * ov
            return g

        def feasible(idx) -> bool:
            combo = combos[idx]
            # 번호 반복 제약
            for x in combo:
                if number_count[x] + 1 > self.max_number_repeat:
                    return False
            # pairwise overlap 제약
            for s_idx in selected_idx:
                if len(set(combo) & set(combos[s_idx])) > self.max_pairwise_overlap:
                    return False
            return True

        # 그리디 선택
        for _ in range(num_tickets):
            best, best_g = None, -1e18
            relaxed = False
            search_space = cand_idx
            for idx in search_space:
                if idx in selected_idx:
                    continue
                if not feasible(idx):
                    continue
                g = gain(idx)
                if g > best_g:
                    best_g, best = g, idx
            # 제약으로 후보가 없으면 제약 완화(반복/overlap)하여 재시도
            if best is None:
                relaxed = True
                for idx in search_space:
                    if idx in selected_idx:
                        continue
                    g = gain(idx)
                    if g > best_g:
                        best_g, best = g, idx
            if best is None:
                break
            selected_idx.append(int(best))
            for x in combos[best]:
                covered.add(x)
                number_count[x] += 1
            if relaxed:
                # [E2 2026-06-13] 제약 완화(겹침<=1 보장 깨짐 가능)는 풀 다양성이 극단 부족할 때만
                #  발생한다(1.5M 풀에선 사실상 미발생). debug로 묻으면 '겹침<=1 절대보장'이 깨진 걸
                #  알 수 없으므로 warning으로 가시화한다. local-search 하드가드가 이후 다시 줄이려 시도함.
                self.logger.warning("[다양성] 제약 완화하여 티켓 선택(풀 다양성 부족 -> 겹침<=1 보장 일시 해제)")

        # 로컬 서치: 선택 티켓 1장을 후보로 교체 시 총 목적함수 개선되면 채택
        def total_objective(sel: List[int]) -> float:
            cov = set()
            for i in sel:
                cov |= set(combos[i])
            val = self.lambda_cov * len(cov)
            val += self.lambda_wcov * sum(self.w[x - 1] for x in cov)
            val += self.lambda_quality * sum(float(q_norm[i]) for i in sel)
            ov = 0
            for a in range(len(sel)):
                for b in range(a + 1, len(sel)):
                    inter = len(set(combos[sel[a]]) & set(combos[sel[b]]))
                    ov += inter * inter
            val -= self.lambda_overlap * ov
            return val

        # [2026-06-13 직교성 하드 가드] 로컬서치 교체가 pairwise overlap<=1 / 번호반복<=2 제약을
        # 깨지 않도록 feasibility를 명시적으로 재확인한다. 기존엔 total_objective의 overlap '패널티'만
        # 의존해 큰 커버리지 이득이 있으면 겹침 2가 끼어들 수 있었다(직교성=공멸방지의 핵심이라 하드화).
        def swap_feasible(sel: List[int], pos: int, new_idx: int) -> bool:
            new_set = set(combos[new_idx])
            # pairwise overlap 제약 (교체 대상 pos를 제외한 나머지 티켓들과)
            for k, s_idx in enumerate(sel):
                if k == pos:
                    continue
                if len(new_set & set(combos[s_idx])) > self.max_pairwise_overlap:
                    return False
            # 번호 반복 제약 (pos를 new로 바꿨을 때 어떤 번호도 max_number_repeat 초과 금지)
            cnt = np.zeros(46, dtype=np.int16)
            for k, s_idx in enumerate(sel):
                use = new_set if k == pos else set(combos[s_idx])
                for x in use:
                    cnt[x] += 1
            return bool((cnt <= self.max_number_repeat).all())

        cur_obj = total_objective(selected_idx)
        for _ in range(local_search_iters):
            # [코드리뷰 2026-06-27 P3] 기존의 `improved` 플래그 + 루프 끝 `if not improved: continue`는
            # for 본문 마지막 문장이라 분기 양쪽 결과가 동일한 죽은 코드였다(결과 불변). 제거함.
            trial = rng.choice(cand_idx)
            if trial in selected_idx:
                continue
            for pos in range(len(selected_idx)):
                if not swap_feasible(selected_idx, pos, int(trial)):
                    continue
                old = selected_idx[pos]
                selected_idx[pos] = int(trial)
                new_obj = total_objective(selected_idx)
                if new_obj > cur_obj + 1e-9:
                    cur_obj = new_obj
                    break
                selected_idx[pos] = old

        return [tuple(sorted(combos[i])) for i in selected_idx]

    @staticmethod
    def coverage_report(tickets: List[Tuple[int, ...]]) -> dict:
        """선택된 5장의 다양성 지표."""
        all_nums = [n for t in tickets for n in t]
        unique = set(all_nums)
        pairwise = []
        for a in range(len(tickets)):
            for b in range(a + 1, len(tickets)):
                pairwise.append(len(set(tickets[a]) & set(tickets[b])))
        from collections import Counter
        cnt = Counter(all_nums)
        return {
            'num_tickets': len(tickets),
            'unique_numbers': len(unique),
            'coverage_pct': len(unique) / 45 * 100,
            'max_pairwise_overlap': max(pairwise) if pairwise else 0,
            'avg_pairwise_overlap': float(np.mean(pairwise)) if pairwise else 0.0,
            'most_repeated': cnt.most_common(3),
            'missing_numbers': sorted(set(range(1, 46)) - unique),
        }
