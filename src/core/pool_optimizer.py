"""
풀 최적화기 (PoolOptimizer) - Optuna 재설계 v6

설계 합의 (2026-05-31, Codex gpt-5.5 + Gemini 3.1-pro + Claude 교차검증):
  구 패러다임(v2~v5): 단일 global_probability_threshold를 Optuna가 탐색 + 통과율 95% 제약.
    => [폐기] 실측상 threshold 레버가 죽어 풀이 항상 807만 고정. 통과율 제약은 사용자가 제거 결정.
  신 패러다임(v6): 풀 크기 K는 컷오프로 "직접" 제어(최적화 대상 아님).
    Optuna는 ExtremenessScorer의 차원 가중치(feature 스케일 + 페널티 가중)를 탐색하여
    "역사적 당첨번호가 무작위 조합보다 덜 극단적으로 평가되도록"(분리도) 만든다.

목적함수 (통과율 제약 제거):
  maximize  score = AUC_sep  +  lambda_lift * lift_lcb  -  lambda_reg * weight_complexity

  - AUC_sep : label(과거당첨 vs 무작위) 분리 AUC, score=-extremeness.
      => 노이즈에 강건한 주신호(표본 큼: 당첨 N + 무작위 M).
  - lift_lcb: hold-out 당첨번호의 풀(K) 포함 lift 의 로그 하한(K-fold).
      => Codex/Gemini 합의: lift는 "선택 신호"가 아닌 약한 "검증 보조항"으로만. (과적합 방지)
  - weight_complexity: 가중치 분산(L2) 소폭 페널티 (단순/안정 선호).

핵심 전략(사용자 확정): 통과율은 강제 목표가 아니라 참고지표. "극단 최대 제거 후 남은 풀에서
다양성 예측". K는 사용자가 곡선(analyze_threshold_pool_curve)으로 고른 값(기본 1.5M).
"""
import os
import logging
import math
import json
from typing import Dict, Optional, List

import numpy as np

try:
    import optuna
    from optuna.samplers import TPESampler
    _HAS_OPTUNA = True
except Exception:
    _HAS_OPTUNA = False

from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS


def _auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """이진 분류 AUC (rank 기반, sklearn 비의존). labels: 1=positive."""
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    # 동점 평균 랭크 보정
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    # 간단 보정: 동점 그룹 평균 랭크
    sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
    avg = sums / counts
    ranks = avg[inv]
    n_pos = labels.sum()
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    sum_pos = ranks[labels == 1].sum()
    return float((sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


class PoolOptimizer:
    """ExtremenessScorer 가중치를 Optuna로 최적화 (분리도 + 약한 lift)."""

    def __init__(self, db_manager, target_K: int = 1_500_000,
                 holdout: int = 150, n_folds: int = 3,
                 random_negatives: int = 200_000,
                 storage_path: str = "data/pool_optimization.db",
                 lambda_lift: float = 0.2, lambda_reg: float = 0.02):
        self.db = db_manager
        self.target_K = target_K
        self.holdout = holdout
        self.n_folds = n_folds
        self.random_negatives = random_negatives
        self.storage_path = storage_path
        self.lambda_lift = lambda_lift
        self.lambda_reg = lambda_reg
        self.logger = logging.getLogger(__name__)

        self.cont_features = ExtremenessScorer.CONTINUOUS_FEATURES
        self.penalty_dims = ExtremenessScorer.PENALTY_DIMS

        # 데이터 준비 (1회)
        rows = [(r, s) for r, s, _ in self.db.get_all_numbers()]
        self.latest_round = max(r for r, _ in rows)
        self._all_rows = rows
        # 무작위 음성 표본 (분리도 AUC용; 시드 고정)
        self._neg = self._sample_random(random_negatives, seed=7)

    # ------------------------------------------------------------------
    def _winning(self, lo: int, hi: int) -> np.ndarray:
        return np.array(
            [sorted(int(x) for x in s.split(',')) for r, s in self._all_rows if lo <= r <= hi],
            dtype=np.int16)

    def _sample_random(self, n: int, seed: int) -> np.ndarray:
        rng = np.random.RandomState(seed)
        out = set()
        while len(out) < n:
            c = tuple(sorted(rng.choice(np.arange(1, 46), 6, replace=False).tolist()))
            out.add(c)
        return np.array(list(out), dtype=np.int16)

    def _build_scorer(self, params: Dict) -> ExtremenessScorer:
        """params에서 feature 스케일/페널티 가중치를 ExtremenessScorer에 주입."""
        pw = {d: params.get(f"pw_{d}", 1.0) for d in self.penalty_dims}
        scorer = ExtremenessScorer(self.db, alpha=params.get('alpha', 0.5), penalty_weights=pw)
        # feature 스케일은 fit 후 cov_inv에 대각 곱으로 반영 (가중 마할라노비스)
        scorer._feature_scale = np.array(
            [params.get(f"fw_{f}", 1.0) for f in self.cont_features], dtype=np.float32)
        return scorer

    @staticmethod
    def _apply_scale(scorer: ExtremenessScorer):
        """가중 마할라노비스: cov_inv -> S^T cov_inv S (S=diag(feature_scale))."""
        s = getattr(scorer, '_feature_scale', None)
        if s is not None:
            S = np.diag(s).astype(np.float32)
            scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)

    # ------------------------------------------------------------------
    def evaluate(self, params: Dict, verbose: bool = False) -> Dict:
        """주어진 가중치로 분리도 AUC + lift LCB 계산 (K-fold hold-out)."""
        train_until = self.latest_round - self.holdout

        # (1) 분리도 AUC: train 구간 당첨 vs 무작위
        scorer = self._build_scorer(params)
        win_train = self._winning(1, train_until)
        scorer.fit(win_train)
        self._apply_scale(scorer)

        s_pos = scorer.score(win_train)
        s_neg = scorer.score(self._neg)
        labels = np.concatenate([np.ones(len(s_pos)), np.zeros(len(s_neg))])
        scores = np.concatenate([s_pos, s_neg])
        auc_sep = _auc(labels, np.concatenate([-s_pos, -s_neg]))  # score=-extremeness

        # (2) hold-out lift (K-fold over holdout window)
        holdout_win = self._winning(train_until + 1, self.latest_round)
        pool_ratio = self.target_K / TOTAL_COMBINATIONS
        lifts = []
        if len(holdout_win) >= self.n_folds:
            # 전수 채점으로 cutoff 산출 (가중 반영된 동일 scorer)
            combos = ExtremenessScorer.all_combinations()
            all_scores = scorer.score(combos)
            cutoff = ExtremenessScorer.cutoff_for_size(all_scores, self.target_K)
            folds = np.array_split(holdout_win, self.n_folds)
            for fold in folds:
                if len(fold) == 0:
                    continue
                sf = scorer.score(fold)
                cov = float((sf <= cutoff).mean())
                lift = cov / pool_ratio if pool_ratio > 0 else 0.0
                lifts.append(lift)
        if lifts:
            log_lifts = np.log(np.array(lifts) + 1e-9)
            lift_lcb = float(np.exp(log_lifts.mean() - 1.64 * log_lifts.std() / math.sqrt(len(log_lifts))))
            lift_mean = float(np.mean(lifts))
        else:
            lift_lcb = lift_mean = 1.0

        # (3) 정규화 페널티 (가중치 분산)
        fw = np.array([params.get(f"fw_{f}", 1.0) for f in self.cont_features])
        pw = np.array([params.get(f"pw_{d}", 1.0) for d in self.penalty_dims])
        complexity = float(np.var(fw) + np.var(pw))

        score = auc_sep + self.lambda_lift * math.log(max(lift_lcb, 1e-3)) - self.lambda_reg * complexity

        result = {
            'score': score, 'auc_separation': auc_sep,
            'lift_mean': lift_mean, 'lift_lcb': lift_lcb,
            'complexity': complexity, 'target_K': self.target_K,
        }
        if verbose:
            self.logger.info(f"[PoolOpt] score={score:.4f} AUC={auc_sep:.4f} "
                             f"lift_mean={lift_mean:.3f} lift_lcb={lift_lcb:.3f}")
        return result

    # ------------------------------------------------------------------
    def optimize(self, n_trials: int = 40, study_name: str = "pool_optimization_v6") -> Dict:
        if not _HAS_OPTUNA:
            raise RuntimeError("optuna 미설치")
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        storage = f"sqlite:///{self.storage_path}"
        study = optuna.create_study(
            study_name=study_name, storage=storage,
            direction="maximize", load_if_exists=True,
            sampler=TPESampler(seed=42))

        def objective(trial):
            params = {'alpha': trial.suggest_float('alpha', 0.1, 2.0)}
            for f in self.cont_features:
                params[f"fw_{f}"] = trial.suggest_float(f"fw_{f}", 0.2, 3.0)
            for d in self.penalty_dims:
                params[f"pw_{d}"] = trial.suggest_float(f"pw_{d}", 0.0, 3.0)
            res = self.evaluate(params)
            trial.set_user_attr('auc_separation', res['auc_separation'])
            trial.set_user_attr('lift_lcb', res['lift_lcb'])
            return res['score']

        study.optimize(objective, n_trials=n_trials)
        best = study.best_params
        best_res = self.evaluate(best, verbose=True)
        out = {'best_params': best, 'best_value': study.best_value, **best_res,
               'n_trials': len(study.trials)}
        self.logger.info(f"[PoolOpt] 최적 완료: score={study.best_value:.4f}, "
                        f"AUC={best_res['auc_separation']:.4f}, lift_lcb={best_res['lift_lcb']:.3f}")
        return out

    def save_best(self, result: Dict, path: str = "configs/extremeness_weights.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'target_K': self.target_K,
                'continuous_features': self.cont_features,
                'penalty_dims': self.penalty_dims,
                'best_params': result['best_params'],
                'metrics': {k: result[k] for k in ('auc_separation', 'lift_mean', 'lift_lcb', 'best_value')},
            }, f, ensure_ascii=False, indent=2)
        self.logger.info(f"[PoolOpt] 가중치 저장: {path}")
