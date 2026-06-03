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

TOTAL_COMBINATIONS = 8_145_060  # C(45, 6)


class ExtremenessPoolPredictor:
    """극단 제거 풀 + 5장 다양성 예측 (main.py 통합용 어댑터)."""

    def __init__(self, db_manager, target_K: Optional[int] = None,
                 weights_path: str = "configs/extremeness_weights.json",
                 cache_dir: str = "cache",
                 spread: float = 0.5):
        self.db = db_manager
        self.weights_path = weights_path
        self.cache_dir = cache_dir
        self.spread = spread
        self.logger = logging.getLogger(__name__)
        # target_K 결정 (하위호환): 명시 인자가 오면 그 값을 그대로 쓴다(기존 호출처 불변).
        # 명시 인자가 없으면(None) 정책 json(SSOT) -> 환경변수 -> 기본 1.5M 순으로 해석한다.
        if target_K is not None:
            self.target_K = int(target_K)
        else:
            self.target_K = self._resolve_target_k()
        self._pool_combos = None      # (K, 6) int8
        self._pool_quality = None     # (K,) float32  (=-극단성)
        self._train_until = None

    # ------------------------------------------------------------------
    def _resolve_target_k(self) -> int:
        """운영 target_K 해석 (우선순위: 정책 json -> 환경변수 -> 기본 1.5M).

        - configs/extremeness_pool_policy.json 의 effective_target_K 가 SSOT(단일 진실).
          (주간/새회차 자동 재탐색이 이 파일을 갱신한다.)
        - 정책 파일이 없거나 손상되면 환경변수 EXTREMENESS_TARGET_K / LOTTO_TARGET_POOL_K,
          그래도 없으면 기본 1.5M.
        - 주의: configs/extremeness_weights.json 의 target_K 키는 더 이상 권위가 없다(무시).
          정책 json 이 SSOT 이며, weights.json 의 target_K 는 레거시/참고값일 뿐이다.
        """
        # 1) 정책 json (SSOT)
        try:
            from src.core.extremeness_threshold_selector import load_policy
            policy = load_policy()
            if policy and policy.get('effective_target_K'):
                k = int(policy['effective_target_K'])
                self.logger.info(
                    f"[극단풀] target_K=정책 json effective_target_K={k:,} "
                    f"(evidence={policy.get('evidence')}, round={policy.get('round')})")
                return k
        except Exception as e:
            self.logger.warning(f"[극단풀] 정책 json 로드 실패({e}) - 환경변수/기본값 사용")

        # 2) 환경변수
        for env_key in ('EXTREMENESS_TARGET_K', 'LOTTO_TARGET_POOL_K'):
            val = os.environ.get(env_key)
            if val:
                try:
                    k = int(val)
                    self.logger.info(f"[극단풀] target_K={env_key}={k:,} (정책 json 없음)")
                    return k
                except ValueError:
                    pass

        # 3) 기본값
        self.logger.info("[극단풀] target_K=기본값 1,500,000 (정책 json/환경변수 없음)")
        return 1_500_000

    # ------------------------------------------------------------------
    def _resolve_round(self) -> int:
        """학습 기준(최신) 회차 해석.

        구버전은 db.get_authoritative_round() 를 호출했으나 이 메서드는 db_manager 에
        존재하지 않아 매 호출이 AttributeError -> except 폴백으로 빠지는 버그였다.
        실제 존재하는 API(get_latest_round -> get_last_round)를 우선 사용하고,
        둘 다 실패하면 get_all_numbers 의 최대 회차로 폴백한다.
        """
        for attr in ('get_latest_round', 'get_last_round'):
            fn = getattr(self.db, attr, None)
            if callable(fn):
                try:
                    val = fn()
                    if val:
                        return int(val)
                except Exception:
                    continue
        return max(r for r, _, _ in self.db.get_all_numbers())

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
            train_until = self._resolve_round()
        self._train_until = train_until

        # 캐시 키에 가중치 파일 버전(mtime) 포함 -> 백그라운드 최적화로 가중치가 갱신되면
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
                # 하위호환: 구캐시(diagnostics 키 없음)는 기본 제거율만 출력.
                if 'diagnostics' in data:
                    try:
                        diag = json.loads(str(data['diagnostics']))
                        self._log_pool_diagnostics(diag)
                    except Exception as de:
                        self.logger.warning(f"[극단풀] 진단 요약 파싱 실패({de}) - 기본 표시")
                        self._log_pool_diagnostics(None)
                else:
                    self._log_pool_diagnostics(None)
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
        # score() 대신 score_components()를 1회 호출(추가 전수패스 금지). total을 선택에
        # 그대로 사용하므로 점수/풀이 score() 사용과 비트 단위로 동일하다(회귀 보장).
        comp = scorer.score_components(combos)
        scores = comp['total']
        pool_idx = ExtremenessScorer.select_pool(scores, self.target_K)
        self._pool_combos = combos[pool_idx]
        self._pool_quality = (-scores[pool_idx]).astype(np.float32)

        # 진단 요약 생성(원본 scores 절대 수정 금지, 전체정렬 금지). 로그 + 캐시 저장.
        diag = self._build_pool_diagnostics(comp, scores, pool_idx, weighted, train_until)
        self._log_pool_diagnostics(diag)

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            # 원자적 쓰기 (extremeness-pool-1): 임시파일에 쓴 뒤 os.replace로 교체.
            # 동일 파라미터로 동시 build_pool(force) 시 부분 작성된 npz를 읽어
            # 캐시가 깨지는 것을 방지한다. file 핸들로 넘겨 .npz 자동접미사 문제 회피.
            # diagnostics는 JSON 문자열(ensure_ascii=True, 이모지/비ASCII 차단)로 함께 저장.
            diag_str = json.dumps(diag, ensure_ascii=True)
            tmp_cache = cache_path + '.tmp'
            with open(tmp_cache, 'wb') as f:
                np.savez_compressed(f, combos=self._pool_combos,
                                    quality=self._pool_quality,
                                    diagnostics=np.array(diag_str))
            os.replace(tmp_cache, cache_path)
        except Exception as e:
            self.logger.warning(f"[극단풀] 캐시 저장 실패({e})")

        return len(pool_idx)

    # ------------------------------------------------------------------
    # 극단 제거 진단 (Codex 구조 + Gemini Delta Mean) - 표시 전용, 예측 불변
    # ------------------------------------------------------------------
    def _build_pool_diagnostics(self, comp: dict, scores: np.ndarray,
                                pool_idx: np.ndarray, weighted: bool,
                                train_until: Optional[int]) -> dict:
        """극단 제거 근거 진단 요약 생성.

        통계 방법(Gemini 3.1-pro 채택): '성분 점수 단순 합 비율'은 마할라노비스가
        스케일상 항상 지배하는 착시를 준다. 대신 **Delta Mean**을 쓴다:
          delta_i = mean(성분_i | 제거군) - mean(성분_i | 유지군)
        음수는 0으로 클램프 후 합으로 정규화 -> "무엇이 극단성을 가중시켰는가"의 기여도%.

        주의: 원본 scores를 절대 수정하지 않고, Top-5는 argpartition(전체정렬 금지)로 추출.
        컷오프는 '설명용 수치'일 뿐, 'scores<=cutoff 재선택' 같은 동점 K변동 로직은 쓰지 않는다.
        """
        total_n = len(scores)
        keep_n = len(pool_idx)
        removed_n = total_n - keep_n

        # 유지군/제거군 마스크 (원본 scores 불변 - 인덱스 마스크만 사용)
        keep_mask = np.zeros(total_n, dtype=bool)
        keep_mask[pool_idx] = True
        removed_mask = ~keep_mask

        # 컷오프(설명용): 유지된 K개 중 최대 점수 = 컷오프 경계. 이 값 초과분이 제거됨.
        cutoff = float(scores[pool_idx].max()) if keep_n > 0 else float('nan')

        # --- Delta Mean 기여도 (성분: 마할라노비스 + 4개 페널티 차원) ---
        comp_keys = [
            ('마할라노비스', 'mahalanobis2'),
            ('끝자리', 'pen_max_same_last_digit'),
            ('구간몰림', 'pen_max_section_occupancy'),
            ('연속', 'pen_max_consecutive'),
            ('홀짝', 'pen_odd_count'),
        ]
        deltas = {}
        for label, key in comp_keys:
            arr = comp[key]
            if removed_n > 0 and keep_n > 0:
                d = float(arr[removed_mask].mean() - arr[keep_mask].mean())
            else:
                d = 0.0
            deltas[label] = max(0.0, d)  # 음수 클램프
        delta_sum = sum(deltas.values())
        contrib = {}
        for label, _ in comp_keys:
            contrib[label] = (deltas[label] / delta_sum * 100.0) if delta_sum > 0 else 0.0

        # --- 직관 라벨 비율(제거군 대상, 중복 허용) ---
        feats = comp['features']
        intuitive = {}
        if removed_n > 0:
            mc = feats['max_consecutive'][removed_mask]
            msld = feats['max_same_last_digit'][removed_mask]
            mso = feats['max_section_occupancy'][removed_mask]
            oc = feats['odd_count'][removed_mask]
            intuitive['구간 4+몰림'] = float((mso >= 4).mean() * 100.0)
            intuitive['끝자리 3+동일'] = float((msld >= 3).mean() * 100.0)
            # 홀짝 쏠림: 0,1,5,6 (6홀/6짝/5홀1짝/1홀5짝)
            intuitive['홀짝 쏠림'] = float(np.isin(oc, [0, 1, 5, 6]).mean() * 100.0)
            intuitive['연속 4+'] = float((mc >= 4).mean() * 100.0)
        else:
            intuitive = {'구간 4+몰림': 0.0, '끝자리 3+동일': 0.0, '홀짝 쏠림': 0.0, '연속 4+': 0.0}

        # --- 제거된 가장 극단적 조합 Top-5 (argpartition - 전체정렬 금지) ---
        examples = []
        if removed_n > 0:
            removed_indices = np.flatnonzero(removed_mask)
            removed_scores = scores[removed_indices]  # 원본 불변(읽기만)
            topn = min(5, removed_n)
            # 점수 내림차순 Top-N: 부분선택 후 그 안에서만 정렬(전체정렬 금지)
            part = np.argpartition(removed_scores, removed_n - topn)[removed_n - topn:]
            part = part[np.argsort(removed_scores[part])[::-1]]
            from src.core.extremeness_scorer import ExtremenessScorer as _ES
            combos_all = _ES.all_combinations()
            mc_all = feats['max_consecutive']
            for p in part:
                gi = int(removed_indices[p])
                nums = [int(x) for x in combos_all[gi]]
                examples.append({
                    'numbers': nums,
                    'score': round(float(scores[gi]), 2),
                    'max_consecutive': int(mc_all[gi]),
                })

        # --- 남은 풀 평균(역대 분포 근접 확인용) ---
        pool_sum_mean = 0.0
        pool_odd_mean = 0.0
        if keep_n > 0:
            kc = self._pool_combos.astype(np.int32)
            pool_sum_mean = float(kc.sum(axis=1).mean())
            pool_odd_mean = float((kc % 2 == 1).sum(axis=1).mean())

        return {
            'total': int(total_n),
            'keep': int(keep_n),
            'removed': int(removed_n),
            'removed_pct': float((1 - keep_n / TOTAL_COMBINATIONS) * 100.0),
            'cutoff': round(cutoff, 2) if keep_n > 0 else None,
            'contrib': {k: round(v, 1) for k, v in contrib.items()},
            'intuitive': {k: round(v, 1) for k, v in intuitive.items()},
            'examples': examples,
            'pool_sum_mean': round(pool_sum_mean, 1),
            'pool_odd_mean': round(pool_odd_mean, 1),
            'weighted': bool(weighted),
            'train_until': int(train_until) if train_until is not None else None,
        }

    def _log_pool_diagnostics(self, diag: Optional[dict]) -> None:
        """진단 요약을 ASCII/한국어로 로그 출력. diag=None(구캐시/실패)이면 기본만."""
        if diag is None:
            # 구캐시(진단 없음) 또는 파싱 실패: 풀 크기/제거율만 표시.
            if self._pool_combos is not None:
                keep_n = len(self._pool_combos)
                removed = (1 - keep_n / TOTAL_COMBINATIONS) * 100
                self.logger.info(
                    f"[극단풀] 형성 완료: {keep_n:,}개 (제거율 {removed:.1f}%) "
                    f"- 진단 요약 없음(구캐시). 재계산(force=True) 시 상세 진단 표시")
            return

        total_n = diag['total']
        keep_n = diag['keep']
        removed_n = diag['removed']
        removed_pct = diag['removed_pct']
        cutoff = diag.get('cutoff')

        self.logger.info(
            f"[극단풀] === 극단 패턴 제거 진단 ({total_n:,} -> {keep_n:,}) ===")
        cut_str = f"{cutoff}" if cutoff is not None else "N/A"
        self.logger.info(
            f"  - 제거: {removed_n:,}개 ({removed_pct:.1f}%) | "
            f"컷오프 극단점수: {cut_str} (이 점수 초과분 제거)")

        # 기여도(Delta Mean): contrib dict는 삽입 순서 유지(마할라/끝자리/구간/연속/홀짝)
        contrib = diag.get('contrib', {})
        contrib_str = ", ".join(f"{k} {v:.1f}%" for k, v in contrib.items())
        self.logger.info(
            f"  - 제거 근거 기여도(Delta Mean, 유지군 대비 제거군 초과분): {contrib_str}")
        # 홀짝은 마할라노비스(odd_count 특징)와 페널티 양쪽에 들어가 이중계산 가능 -> 명시
        self.logger.info(
            f"    (참고: 홀짝은 마할라노비스 특징과 페널티에 모두 반영되어 일부 중복 집계됨)")

        intuitive = diag.get('intuitive', {})
        intu_str = ", ".join(f"{k} {v:.1f}%" for k, v in intuitive.items())
        self.logger.info(f"  - 제거 조합 직관 지표(중복 집계): {intu_str}")

        examples = diag.get('examples', [])
        if examples:
            ex_strs = []
            for ex in examples:
                nums = ex['numbers']
                mc = ex.get('max_consecutive', 0)
                tag = f"(연속{mc})" if mc >= 2 else ""
                ex_strs.append(f"{nums}{tag} score={ex['score']}")
            self.logger.info(f"  - 제거된 가장 극단적인 조합 예시: " + " / ".join(ex_strs))

        self.logger.info(
            f"  - 남은 풀 평균: 합계 ~{diag.get('pool_sum_mean')}, "
            f"홀수 ~{diag.get('pool_odd_mean')}개 (역대 당첨 분포 근접)")
        self.logger.info(
            f"  - 가중치 {'최적화' if diag.get('weighted') else '균등'}, "
            f"학습 ~{diag.get('train_until')}회")

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
