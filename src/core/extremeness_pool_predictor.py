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
import glob
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
                 spread: float = 0.5,
                 scoring_method: Optional[str] = None):
        self.db = db_manager
        self.weights_path = weights_path
        self.cache_dir = cache_dir
        self.spread = spread
        self.logger = logging.getLogger(__name__)
        # 점수 방식 (2026-06-13 사용자 채택, Claude+Codex gpt-5.5+Gemini 3.1-pro 합의): 기본 'hybrid'.
        #  - 'hybrid'        : 풀 '선택'은 마할라노비스(정확도 - blind 6fold 당첨보존율 21.2%로 최상),
        #    '제거 사유 설명'은 비모수 꼬리확률(tail)로 화이트박스 표시. 정확도+투명성 양립(권장 기본).
        #  - 'mahalanobis'   : 선택=마할라, 설명도 마할라(거리 숫자 1개, blackbox). env로 선택 가능.
        #  - 'tail_group_max': 선택·설명 모두 tail 꼬리확률. 보존율 점추정 18.8%로 약간 열위(비유의)
        #    라 기본에서 내림. 투명성만 원하면 env LOTTO_SCORING_METHOD=tail_group_max.
        #  근거: 보존율(=당첨번호 보존) 점추정 마할라 21.2% > tail 18.8%(McNemar 비유의 p>0.24).
        #  KPI=등수적중률이면 점추정 우위인 마할라로 '선택'하고, '설명'만 tail로 얻는 게 최선.
        self.scoring_method = scoring_method or os.environ.get('LOTTO_SCORING_METHOD', 'hybrid')
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
        # 선택(selection) 방식: 'hybrid'는 풀을 마할라노비스로 고르고(정확도) tail은 '설명'에만
        # 쓰므로 캐시/버전을 마할라노비스와 공유한다(동일 풀 -> 캐시 중복 방지).
        sel_method = 'mahalanobis' if self.scoring_method in ('mahalanobis', 'hybrid') else self.scoring_method
        # 캐시 버전(wver): 마할라(선택)는 weights.json mtime, tail(선택)은 스코어러 로직 파일 mtime.
        # [2026-06-13] 과거 tail은 wver=0 고정이라 알고리즘을 고쳐도 같은 회차/K면 옛 풀이 silent
        # 재사용됐다 -> 로직 파일 mtime을 버전에 포함해 코드 수정 즉시 캐시 무효화(마할라와 대칭).
        if sel_method == 'mahalanobis':
            # [2026-06-13 코드변경 무효화 보강] 가중치(weights.json) mtime '과' 스코어러 로직 파일
            # (extremeness_scorer.py) mtime의 최대값을 버전으로 쓴다. 과거엔 weights.json mtime만 반영해
            # 마할라 계산/특징셋 코드를 고쳐도(가중치 불변) 같은 회차/K면 옛 풀이 silent 재사용됐다.
            # -> 로직 파일 mtime을 OR로 포함해 '코드 변경 시에도' 캐시 자동 무효화(새 회차뿐 아니라).
            _scorer_py = os.path.join(self._project_root(), 'src', 'core', 'extremeness_scorer.py')
            _wmt = int(os.path.getmtime(wpath)) if os.path.exists(wpath) else 0
            _smt = int(os.path.getmtime(_scorer_py)) if os.path.exists(_scorer_py) else 0
            wver = max(_wmt, _smt)
        else:
            _scorer_py = os.path.join(self._project_root(), 'src', 'core', 'tail_probability_scorer.py')
            wver = int(os.path.getmtime(_scorer_py)) if os.path.exists(_scorer_py) else 0
        # 캐시 키에 '선택 방식' 포함 -> tail/mahalanobis 캐시 분리 공존(hybrid는 마할라와 공유).
        cache_path = os.path.join(self._project_root(), self.cache_dir,
                                  f"extremeness_pool_{sel_method}_{train_until}_{self.target_K}_w{wver}.npz")
        if not force and os.path.exists(cache_path):
            try:
                data = np.load(cache_path)
                self._pool_combos = data['combos']
                self._pool_quality = data['quality']
                self.logger.info(f"[극단풀] 캐시 로드: {cache_path} ({len(self._pool_combos):,}개)")
                _logfn = self._log_tail_diagnostics if sel_method == 'tail_group_max' \
                    else self._log_pool_diagnostics
                # 하위호환: 구캐시(diagnostics 키 없음)는 기본 제거율만 출력.
                if 'diagnostics' in data:
                    try:
                        diag = json.loads(str(data['diagnostics']))
                        _logfn(diag)
                        # [코드리뷰 2026-06-27 P3] hybrid 화이트박스 설명도 캐시 히트에서 재생(표시 일관성).
                        self._replay_hybrid_tail_explanations(diag)
                    except Exception as de:
                        self.logger.warning(f"[극단풀] 진단 요약 파싱 실패({de}) - 기본 표시")
                        _logfn(None)
                else:
                    _logfn(None)
                return len(self._pool_combos)
            except Exception as e:
                self.logger.warning(f"[극단풀] 캐시 로드 실패({e}) - 재계산")

        win_train = np.array(
            [sorted(int(x) for x in s.split(',')) for r, s, _ in self.db.get_all_numbers()
             if r <= train_until], dtype=np.int16)
        combos = ExtremenessScorer.all_combinations()

        if sel_method == 'tail_group_max':
            # [2026-06-07 사용자 채택] 비모수 꼬리확률(화이트박스). 각 특징 역사 꼬리확률 기반.
            from src.core.tail_probability_scorer import TailProbabilityScorer
            scorer = TailProbabilityScorer(self.db, mode='group_max')
            scorer.fit(win_train)
            scores = scorer.score(combos).astype(np.float32)
            pool_idx = TailProbabilityScorer.select_pool(scores, self.target_K)
            self._pool_combos = combos[pool_idx]
            self._pool_quality = (-scores[pool_idx]).astype(np.float32)
            diag = self._build_tail_diagnostics(scorer, scores, pool_idx, train_until)
            self._log_tail_diagnostics(diag)
        else:
            # 'mahalanobis' (구 현행, 롤백용): 마할라노비스거리^2 + 페널티.
            weight_json = self._load_weight_params()
            scorer, weighted = self._build_scorer(weight_json)
            scorer.fit(win_train)
            if weighted and getattr(scorer, '_feature_scale', None) is not None:
                S = np.diag(scorer._feature_scale).astype(np.float32)
                scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
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
            if self.scoring_method == 'hybrid':
                # 화이트박스 설명(표시 전용, 예측 불변): 선택은 마할라(정확도)로 하되, 제거된
                # 극단 예시를 비모수 꼬리확률(tail)로 '왜 버렸는지' 사람이 읽게 설명한다.
                try:
                    _explain = self._log_hybrid_tail_explanations(win_train, combos, scores, pool_idx)
                    # [코드리뷰 2026-06-27 P3] 설명을 diag에 보존 -> 캐시 히트 재실행에서도 재생(표시 일관성).
                    if _explain:
                        diag['hybrid_tail_explain'] = _explain
                except Exception as _he:
                    self.logger.debug(f"[극단풀-하이브리드] tail 설명 생략({_he})")

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
            # [코드리뷰 2026-06-27 P2] 같은 (선택방식, 학습회차, K)의 옛 wver npz 정리.
            # 캐시키가 결정적이라 옛 wver는 절대 재로드되지 않지만 디스크에 영구 누적되므로
            # (실측 다수 누적), 새 캐시 저장 직후 동일 prefix의 구버전 파일을 제거한다.
            try:
                _prefix = f"extremeness_pool_{sel_method}_{train_until}_{self.target_K}_w"
                _cdir = os.path.dirname(cache_path)
                for _old in glob.glob(os.path.join(_cdir, _prefix + "*.npz")):
                    if os.path.abspath(_old) != os.path.abspath(cache_path):
                        try:
                            os.remove(_old)
                        except OSError:
                            pass
            except Exception:
                pass
        except Exception as e:
            self.logger.warning(f"[극단풀] 캐시 저장 실패({e})")

        return len(pool_idx)

    # ------------------------------------------------------------------
    # 꼬리확률 제거 진단 (2026-06-07 사용자 채택 - '왜 버렸는지' 투명 표시)
    # ------------------------------------------------------------------
    def _build_tail_diagnostics(self, scorer, scores: np.ndarray,
                                pool_idx: np.ndarray, train_until: Optional[int]) -> dict:
        """비모수 꼬리확률 제거 사유 진단. 제거된 가장 극단 조합 + 특징별 '역사 하위 %' 사유.

        화이트박스 핵심: 마할라노비스(거리 숫자 1개, blackbox)와 달리 '어느 특징이 역사적으로
        하위 몇% 꼬리라 제거됐는가'를 explain()으로 사람이 읽게 표시한다. 표시 전용(예측 불변).
        """
        from src.core.extremeness_scorer import ExtremenessScorer as _ES
        total_n = len(scores)
        keep_n = len(pool_idx)
        removed_n = total_n - keep_n
        keep_mask = np.zeros(total_n, dtype=bool)
        keep_mask[pool_idx] = True
        removed_mask = ~keep_mask
        cutoff = float(scores[pool_idx].max()) if keep_n > 0 else float('nan')
        combos_all = _ES.all_combinations()

        # 제거된 가장 극단적 조합 Top-5 + 특징별 사유 (argpartition - 전체정렬 금지)
        examples = []
        if removed_n > 0:
            rem_idx = np.flatnonzero(removed_mask)
            rem_sc = scores[rem_idx]
            topn = min(5, removed_n)
            part = np.argpartition(rem_sc, removed_n - topn)[removed_n - topn:]
            part = part[np.argsort(rem_sc[part])[::-1]]
            for p in part:
                gi = int(rem_idx[p])
                nums = [int(x) for x in combos_all[gi]]
                ex = scorer.explain(nums)[:3]  # 상위 3개 제거 사유
                examples.append({
                    'numbers': nums,
                    'score': round(float(scores[gi]), 2),
                    'reasons': [[r['feature'], r['tail_pct'], r['tail_side']] for r in ex],
                })

        # 가장자리 제거율 (양끝은 역사상 드물어 데이터 본질적으로 많이 제거됨 - 검증 확인됨)
        has1 = (combos_all == 1).any(axis=1)
        has45 = (combos_all == 45).any(axis=1)
        both = has1 & has45
        edge = {
            'all': round(float(removed_mask.mean()) * 100, 1),
            'n1': round(float(removed_mask[has1].mean()) * 100, 1),
            'n45': round(float(removed_mask[has45].mean()) * 100, 1),
            'both': round(float(removed_mask[both].mean()) * 100, 1) if bool(both.any()) else 0.0,
        }

        pool_sum_mean = 0.0
        pool_odd_mean = 0.0
        if keep_n > 0:
            kc = self._pool_combos.astype(np.int32)
            pool_sum_mean = round(float(kc.sum(axis=1).mean()), 1)
            pool_odd_mean = round(float((kc % 2 == 1).sum(axis=1).mean()), 1)

        return {
            'total': int(total_n), 'keep': int(keep_n), 'removed': int(removed_n),
            'removed_pct': round(float((1 - keep_n / TOTAL_COMBINATIONS) * 100), 1),
            'cutoff': round(cutoff, 2) if keep_n > 0 else None,
            'edge': edge, 'examples': examples,
            'pool_sum_mean': pool_sum_mean, 'pool_odd_mean': pool_odd_mean,
            'method': 'tail_group_max',
            'train_until': int(train_until) if train_until is not None else None,
        }

    def _log_tail_diagnostics(self, diag: Optional[dict]) -> None:
        """꼬리확률 제거 진단을 ASCII/한국어로 로그 출력. diag=None(구캐시)이면 기본만."""
        if diag is None:
            if self._pool_combos is not None:
                keep_n = len(self._pool_combos)
                removed = (1 - keep_n / TOTAL_COMBINATIONS) * 100
                self.logger.info(
                    f"[극단풀-꼬리확률] 형성 완료: {keep_n:,}개 (제거율 {removed:.1f}%) "
                    f"- 진단 없음(구캐시). 재계산(force=True) 시 상세 사유 표시")
            return
        self.logger.info(
            f"[극단풀-꼬리확률] === 역사 꼬리확률 제거 진단 ({diag['total']:,} -> {diag['keep']:,}) ===")
        self.logger.info(
            f"  - 제거: {diag['removed']:,}개 ({diag['removed_pct']}%) | "
            f"컷오프 극단점수: {diag.get('cutoff')} (이 점수 초과분 제거)")
        e = diag.get('edge', {})
        self.logger.info(
            f"  - 가장자리 제거율: 전체 {e.get('all')}% / 번호1 {e.get('n1')}% / "
            f"번호45 {e.get('n45')}% / 1&45 {e.get('both')}% (양끝은 역사상 드물어 데이터본질적 제거)")
        for ex in diag.get('examples', []):
            reasons = ', '.join(f"{f}(역사하위 {p}% {s})" for f, p, s in ex['reasons'])
            self.logger.info(f"  - 제거 {ex['numbers']} score={ex['score']}: {reasons}")
        self.logger.info(
            f"  - 남은 풀 평균: 합계 ~{diag.get('pool_sum_mean')}, "
            f"홀수 ~{diag.get('pool_odd_mean')}개 (역대 당첨 분포 근접)")
        self.logger.info(
            f"  - 점수방식=tail_group_max(비모수 꼬리확률 화이트박스), 학습 ~{diag.get('train_until')}회")

    def _log_hybrid_tail_explanations(self, win_train, combos, scores, pool_idx) -> List[str]:
        """하이브리드 모드: 풀 '선택'은 마할라노비스(정확도)로 하되, '왜 이 극단을 버렸는지'를
        비모수 꼬리확률(tail)로 사람이 읽게 설명한다(표시 전용, 예측 불변).

        마할라가 제거한 가장 극단적인 조합 Top-5에 대해 tail.explain()으로 '어느 특징이
        역사 하위 몇% 꼬리라 극단인지'를 출력한다. 마할라(거리 숫자 1개=blackbox)의 약점인
        '설명 불가'를 보완하는 화이트박스 계층이며, tail은 선택에 전혀 관여하지 않는다.

        [코드리뷰 2026-06-27 P3] 로그 라인을 리스트로 모아 반환한다 -> 호출부가 diag에 직렬화해
        캐시 히트(0.2s 재실행)에서도 동일 설명을 재생(_replay_hybrid_tail_explanations). 과거엔
        재계산 경로에서만 보이고 캐시 히트하는 정상 운영 다수 사이클에선 설명이 통째로 누락됐다.
        """
        from src.core.tail_probability_scorer import TailProbabilityScorer
        total_n = len(scores)
        keep_mask = np.zeros(total_n, dtype=bool)
        keep_mask[pool_idx] = True
        removed_mask = ~keep_mask
        removed_n = int(removed_mask.sum())
        if removed_n == 0:
            return []
        tail = TailProbabilityScorer(self.db, mode='group_max')
        tail.fit(win_train)
        # 마할라 점수가 가장 큰(=가장 극단) 제거 조합 Top-5 (argpartition - 전체정렬 금지)
        rem_idx = np.flatnonzero(removed_mask)
        rem_sc = scores[rem_idx]
        topn = min(5, removed_n)
        part = np.argpartition(rem_sc, removed_n - topn)[removed_n - topn:]
        part = part[np.argsort(rem_sc[part])[::-1]]
        lines = ["[극단풀-하이브리드] 선택=마할라노비스(정확도), 제거사유는 아래 tail 꼬리확률로 설명(표시전용):"]
        for p in part:
            gi = int(rem_idx[p])
            nums = [int(x) for x in combos[gi]]
            try:
                ex = tail.explain(nums)[:3]
                reasons = ', '.join(
                    f"{r['feature']}(역사하위 {r['tail_pct']}% {r['tail_side']})" for r in ex)
            except Exception:
                reasons = '(설명 계산 실패)'
            lines.append(f"  - 제거 {nums}: {reasons}")
        for ln in lines:
            self.logger.info(ln)
        return lines

    def _replay_hybrid_tail_explanations(self, diag) -> None:
        """캐시 히트 시 빌드 때 diag에 보존한 hybrid tail 제거사유 설명을 그대로 출력(표시 전용).
        [코드리뷰 2026-06-27 P3] 재계산 경로에서만 보이던 화이트박스 설명을 캐시 히트에서도 재생해
        '하이브리드가 약속한 투명성'이 정상 운영 다수 사이클에서 silent 누락되던 것을 해소한다."""
        try:
            lines = (diag or {}).get('hybrid_tail_explain')
        except AttributeError:
            lines = None
        for ln in (lines or []):
            self.logger.info(ln)

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

    def _ticket_typicality(self, tickets) -> List[float]:
        """각 티켓의 '전형성' 백분위(0~1) 산출 - per-set 정직한 점수용.

        의미: pool_quality(=-극단성, 클수록 덜 극단적=더 전형적)의 풀 내 백분위.
        당첨확률이 아니라 '역대 분포 근접도'다. 풀에서 못 찾으면 0.5(중립).
        비용: 풀 품질 정렬 1회 + 티켓당 전수매칭(5회) - 무시 가능.
        """
        if self._pool_combos is None or self._pool_quality is None:
            return [0.5] * len(tickets)
        q = self._pool_quality
        pc = self._pool_combos
        q_sorted = np.sort(q)
        n = len(q_sorted)
        out = []
        for t in tickets:
            arr = np.array(sorted(int(x) for x in t), dtype=pc.dtype)
            match = np.where((pc == arr).all(axis=1))[0]
            if len(match):
                pct = float(np.searchsorted(q_sorted, q[match[0]]) / max(n, 1))
            else:
                pct = 0.5
            out.append(pct)
        return out

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

        # [2026-06-05] 정직한 per-set 점수: 모든 세트를 0.5(50%)로 고정하던 것을 '전형성 점수'로 교체.
        # 의미: 당첨확률이 아니라 "이 세트가 역대 당첨 분포에 얼마나 가까운가(=극단 회피도)"의 백분위.
        # 근거: pool_quality(=-극단성)가 클수록 덜 극단적/더 전형적. 풀 내 백분위를 50~95% 로 표시.
        # NO FAKE DATA: 가짜 '당첨확률'이 아니라 실제로 계산되는 전형성 지표.
        # 주의(정직성): 이 함수가 반환하는 dict 는 키 'confidence' 만 가지며, '당첨확률 아님'
        #   같은 disclaimer 라벨 자체를 emit 하지 않는다. 그 disclaimer 는 표시 계층
        #   (대시보드 툴팁 / main.py 백테스트 요약)에서 부착된다.
        typ = self._ticket_typicality(tickets)

        src = f"ExtremePool-Diversity(K={self.target_K//1000}K, cover={rep['unique_numbers']}/45)"
        out = []
        for t, ty in zip(tickets, typ):
            out.append({
                'numbers': sorted(int(x) for x in t),
                'confidence': round(0.5 + 0.45 * ty, 4),  # 전형성 백분위 -> 50~95% 표시(중립 50 고정 탈피)
                'source': src,
                'in_pool': True,
            })
        self.logger.info(f"[극단풀] {len(out)}세트 생성: 커버 {rep['unique_numbers']}/45번호, "
                        f"티켓간 최대겹침 {rep['max_pairwise_overlap']}")
        return out
