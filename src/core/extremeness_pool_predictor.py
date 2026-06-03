"""
극단성 풀 예측기 (ExtremenessPoolPredictor) - production 통합 어댑터

신 아키텍처(2026-05-31, Codex+Gemini+Claude 합의)를 main.py 본류에 연결하는 단일 진입점.
흐름:
  1. ExtremenessScorer로 8.14M 채점 -> 목표 풀 크기 K(기본 1.5M) 컷오프로 극단 제거
  2. FrequencyAnalyzer로 번호 가중치 (빈도/최근성 + ML 신호 결합)
  3. DiversitySelector(가중 max-coverage)로 5장 선택 (커버리지 극대화)

성능:
  - 8.14M 채점 ~16-20s. production 반복 실행 대비 풀 인덱스를 디스크 캐시
    (cache/extremeness_pool_<train_until>_<K>.npz, 학습회차+K 동일 시 재사용).

핵심 전략(사용자 확정): 극단 최대 제거 + 남은 풀 다양성 예측. 통과율 강제 제약 없음.
ML은 "당첨 예측"이 아니라 "풀 내 번호 다양성 가중치"로만 사용(CLAUDE.md 핵심전략 정합).
"""
import os
import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np


class ExtremenessPoolPredictor:
    """극단 제거 풀 + 5장 다양성 예측 (main.py 통합용 어댑터)."""

    def __init__(self, db_manager, target_K: int = 1_500_000,
                 weights_path: str = "configs/extremeness_weights.json",
                 cache_dir: str = "cache",
                 spread: float = 0.5):
        self.db = db_manager
        self.target_K = target_K
        self.weights_path = weights_path
        self.cache_dir = cache_dir
        self.spread = spread
        self.logger = logging.getLogger(__name__)
        self._pool_combos = None      # (K, 6) int8
        self._pool_quality = None     # (K,) float32  (=-극단성)
        self._train_until = None

    # ------------------------------------------------------------------
    def _load_weight_params(self) -> Optional[Dict]:
        path = os.path.join(self._project_root(), self.weights_path) \
            if not os.path.isabs(self.weights_path) else self.weights_path
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"[극단풀] 가중치 로드 실패({e}) - 균등 가중 사용")
        return None

    @staticmethod
    def _project_root() -> str:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _build_scorer(self, weight_json: Optional[Dict]):
        from src.core.extremeness_scorer import ExtremenessScorer
        if weight_json and 'best_params' in weight_json:
            bp = weight_json['best_params']
            pw = {d: bp.get(f"pw_{d}", 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
            scorer = ExtremenessScorer(self.db, alpha=bp.get('alpha', 0.5), penalty_weights=pw)
            scorer._feature_scale = np.array(
                [bp.get(f"fw_{f}", 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES],
                dtype=np.float32)
            return scorer, True
        return ExtremenessScorer(self.db), False

    # ------------------------------------------------------------------
    def build_pool(self, train_until: Optional[int] = None, force: bool = False) -> int:
        """극단 제거 풀 형성 (캐시 활용). 반환: 풀 크기."""
        from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS

        if train_until is None:
            try:
                train_until = self.db.get_authoritative_round()
            except Exception:
                train_until = max(r for r, _, _ in self.db.get_all_numbers())
        self._train_until = train_until

        # 캐시 키에 가중치 파일 버전(mtime) 포함 → 백그라운드 최적화로 가중치가 갱신되면
        # 풀 캐시가 자동 무효화되어 새 가중치로 재계산됨.
        wpath = os.path.join(self._project_root(), self.weights_path) \
            if not os.path.isabs(self.weights_path) else self.weights_path
        wver = int(os.path.getmtime(wpath)) if os.path.exists(wpath) else 0
        cache_path = os.path.join(self._project_root(), self.cache_dir,
                                  f"extremeness_pool_{train_until}_{self.target_K}_w{wver}.npz")
        if not force and os.path.exists(cache_path):
            try:
                data = np.load(cache_path)
                self._pool_combos = data['combos']
                self._pool_quality = data['quality']
                self.logger.info(f"[극단풀] 캐시 로드: {cache_path} ({len(self._pool_combos):,}개)")
                return len(self._pool_combos)
            except Exception as e:
                self.logger.warning(f"[극단풀] 캐시 로드 실패({e}) - 재계산")

        weight_json = self._load_weight_params()
        scorer, weighted = self._build_scorer(weight_json)

        win_train = np.array(
            [sorted(int(x) for x in s.split(',')) for r, s, _ in self.db.get_all_numbers()
             if r <= train_until], dtype=np.int16)
        scorer.fit(win_train)
        if weighted and getattr(scorer, '_feature_scale', None) is not None:
            S = np.diag(scorer._feature_scale).astype(np.float32)
            scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)

        combos = ExtremenessScorer.all_combinations()
        scores = scorer.score(combos)
        pool_idx = ExtremenessScorer.select_pool(scores, self.target_K)
        self._pool_combos = combos[pool_idx]
        self._pool_quality = (-scores[pool_idx]).astype(np.float32)

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            # 원자적 쓰기 (extremeness-pool-1): 임시파일에 쓴 뒤 os.replace로 교체.
            # 동일 파라미터로 동시 build_pool(force) 시 부분 작성된 npz를 읽어
            # 캐시가 깨지는 것을 방지한다. file 핸들로 넘겨 .npz 자동접미사 문제 회피.
            tmp_cache = cache_path + '.tmp'
            with open(tmp_cache, 'wb') as f:
                np.savez_compressed(f, combos=self._pool_combos, quality=self._pool_quality)
            os.replace(tmp_cache, cache_path)
        except Exception as e:
            self.logger.warning(f"[극단풀] 캐시 저장 실패({e})")

        removed = (1 - len(pool_idx) / TOTAL_COMBINATIONS) * 100
        self.logger.info(f"[극단풀] 형성 완료: {len(pool_idx):,}개 (제거율 {removed:.1f}%, "
                        f"가중치 {'최적화' if weighted else '균등'}, 학습 ~{train_until}회)")
        return len(pool_idx)

    # ------------------------------------------------------------------
    @staticmethod
    def _ml_number_signal(ml_predictions) -> Optional[np.ndarray]:
        """ML 예측들에서 번호별 선호도(45,) 추출 (confidence 가중 빈도)."""
        if not ml_predictions:
            return None
        freq = np.zeros(45, dtype=np.float64)
        any_pred = False
        items = []
        if isinstance(ml_predictions, dict):
            # 'combined'은 개별 모델(lstm/ensemble/monte_carlo/bayesian/fractal)의 종합
            # 결과이므로, 개별 모델과 함께 합산하면 같은 신호가 이중 카운팅된다.
            # 따라서 dict 입력에서는 집계 키('combined')를 제외하고 개별 모델만 합산한다.
            _aggregate_keys = {'combined'}
            for _m, preds in ml_predictions.items():
                if _m in _aggregate_keys:
                    continue
                if preds:
                    items.extend(preds)
        elif isinstance(ml_predictions, list):
            items = ml_predictions
        for p in items:
            nums = p.get('numbers', []) if isinstance(p, dict) else []
            conf = p.get('confidence', 0.5) if isinstance(p, dict) else 0.5
            for n in nums:
                if 1 <= n <= 45:
                    freq[n - 1] += conf
                    any_pred = True
        return freq if any_pred else None

    def predict(self, num_sets: int = 5, ml_predictions=None,
                ml_beta: float = 0.4, seed: int = 42) -> List[Dict]:
        """최종 num_sets개 예측 생성. 반환: [{'numbers','confidence','source'}, ...]"""
        from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

        if self._pool_combos is None:
            self.build_pool()

        # 번호 가중치 (빈도/최근성 + ML 신호)
        fa = FrequencyAnalyzer(self.db)
        ml_sig = self._ml_number_signal(ml_predictions)
        weights = fa.compute_weights(until_round=self._train_until, spread=self.spread,
                                     ml_signal=ml_sig, ml_beta=ml_beta if ml_sig is not None else 0.0)

        pool_list = [tuple(int(x) for x in row) for row in self._pool_combos]
        selector = DiversitySelector(number_weights=weights)
        tickets = selector.select(pool_list, num_tickets=num_sets,
                                  quality=self._pool_quality, candidate_sample=30000, seed=seed)
        rep = DiversitySelector.coverage_report(tickets)

        src = f"ExtremePool-Diversity(K={self.target_K//1000}K, cover={rep['unique_numbers']}/45)"
        out = []
        for t in tickets:
            out.append({
                'numbers': sorted(int(x) for x in t),
                'confidence': 0.5,  # 다양성 선택은 신뢰도 개념 아님 - 중립값
                'source': src,
                'in_pool': True,
            })
        self.logger.info(f"[극단풀] 5세트 생성: 커버 {rep['unique_numbers']}/45번호, "
                        f"티켓간 최대겹침 {rep['max_pairwise_overlap']}")
        return out
