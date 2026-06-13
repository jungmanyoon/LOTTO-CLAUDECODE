# -*- coding: utf-8 -*-
"""
상태 저장/로드/무효화 write->read->reload 일관성 회귀 테스트 (2026-06-13 검증 미션 산출물)

배경: "임계값/가중치/정책/모델/백테스트 등 모든 상태가 실제로 바뀌고, 정확히 저장되고,
정확히 다시 불러와지는가"를 end-to-end로 고정한다(NEXT_SESSION_VERIFICATION_PROMPT_2026-06-13).

검증 항목 매핑:
  A1 - PoolOptimizer.save_best -> extremeness_weights.json export round-trip
  A2 - Optuna study load_if_exists 누적 영속(재시작 시 trial 0 리셋 안 됨)
  A3 - extremeness_weights.json mtime 변경 -> 풀 캐시(wver) 무효화
  A4 - extremeness_pool_policy.json save/load round-trip + select_target_k 결정성
  B1 - run pool predict 재현성(같은 seed -> 같은 5세트)
  C1 - LSTM trained_round sidecar 저장/복원
  C3 + D2 - reset_state code-change가 예측경로 실모델(models/)을 무효화 + Optuna 누적은 미접촉
  D1 - extremeness_scorer.py mtime 변경 -> 풀 캐시(wver) 무효화(코드변경 무효화 보강)

성능: 풀 캐시/예측 테스트는 ExtremenessScorer._ALL_COMBINATIONS_CACHE를 소형(3000개) 배열로
monkeypatch하여 8.14M 전수 채점 없이 build_pool 캐시키 로직을 그대로 검증한다(빠름, TF 불필요).
ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import json
import glob

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ----------------------------------------------------------------------
# 공통 픽스처
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def db():
    """실제 lotto_numbers.db 싱글톤 (read-only 사용)."""
    from src.core.db_manager import DatabaseManager
    return DatabaseManager()


@pytest.fixture
def small_combos():
    """ExtremenessScorer 전체조합 클래스 캐시를 소형(3000개) 유효 조합으로 교체.

    build_pool/score가 8.14M 대신 3000개만 처리하므로 캐시키 무효화 로직을 빠르게 검증.
    테스트 종료 후 None으로 원복하여 다른 테스트에 영향 없음.
    """
    from src.core.extremeness_scorer import ExtremenessScorer
    rng = np.random.RandomState(0)
    s = set()
    while len(s) < 3000:
        c = tuple(sorted(int(x) for x in rng.choice(range(1, 46), 6, replace=False)))
        s.add(c)
    arr = np.array(sorted(s), dtype=np.int8)
    arr.setflags(write=False)
    orig = ExtremenessScorer._ALL_COMBINATIONS_CACHE
    ExtremenessScorer._ALL_COMBINATIONS_CACHE = arr
    try:
        yield arr
    finally:
        ExtremenessScorer._ALL_COMBINATIONS_CACHE = orig


# ----------------------------------------------------------------------
# A1: PoolOptimizer.save_best -> weights.json export round-trip
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_pool_weights_export_roundtrip(db, tmp_path):
    from src.core.pool_optimizer import PoolOptimizer
    opt = PoolOptimizer(db, random_negatives=200)  # 가볍게
    result = {
        'best_params': {
            'alpha': 0.6348, 'fw_sum': 2.17, 'fw_std': 2.49, 'pw_odd_count': 2.22,
        },
        'auc_separation': 0.5103, 'lift_mean': 1.520, 'lift_lcb': 1.436, 'best_value': 0.5887,
    }
    path = str(tmp_path / 'extremeness_weights.json')
    opt.save_best(result, path=path)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # write -> read 일관: best_params 전체 + metrics 4키 + target_K가 정확히 보존
    assert data['best_params'] == result['best_params']
    assert data['metrics']['best_value'] == result['best_value']
    assert data['metrics']['auc_separation'] == result['auc_separation']
    assert data['metrics']['lift_lcb'] == result['lift_lcb']
    assert data['target_K'] == opt.target_K
    # 캐시 무효화 일관: 스코어러가 읽는 키와 동일해야 함
    from src.core.extremeness_scorer import ExtremenessScorer
    assert data['continuous_features'] == ExtremenessScorer.CONTINUOUS_FEATURES
    assert data['penalty_dims'] == ExtremenessScorer.PENALTY_DIMS


# ----------------------------------------------------------------------
# A2: Optuna study load_if_exists 누적 영속 (재시작 시 0 리셋 안 됨)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_optuna_study_load_if_exists_accumulates(tmp_path):
    optuna = pytest.importorskip("optuna")
    storage = f"sqlite:///{(tmp_path / 'study.db').as_posix()}"
    name = "pool_optimization_v6"

    def obj(trial):
        return trial.suggest_float("x", 0.0, 1.0)

    s1 = optuna.create_study(study_name=name, storage=storage, direction="maximize", load_if_exists=True)
    s1.optimize(obj, n_trials=3)
    assert len(s1.trials) == 3

    # "재시작" 시뮬레이션: 같은 이름/스토리지로 다시 생성 -> 0 리셋이 아니라 이어받기
    s2 = optuna.create_study(study_name=name, storage=storage, direction="maximize", load_if_exists=True)
    assert len(s2.trials) == 3, "load_if_exists가 기존 trial을 이어받지 못함(0 리셋)"
    s2.optimize(obj, n_trials=2)

    s3 = optuna.create_study(study_name=name, storage=storage, direction="maximize", load_if_exists=True)
    assert len(s3.trials) == 5, "trial이 누적되지 않음"


# ----------------------------------------------------------------------
# A3 + D1: weights.json / extremeness_scorer.py mtime 변경 -> 풀 캐시 무효화
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_pool_cache_invalidated_by_mtime(db, tmp_path, small_combos):
    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor

    scorer_py = os.path.join(ROOT, 'src', 'core', 'extremeness_scorer.py')
    orig_scorer_mt = os.path.getmtime(scorer_py)

    wpath = str(tmp_path / 'w.json')
    with open(wpath, 'w', encoding='utf-8') as f:
        json.dump({'best_params': {}}, f)  # 존재만 하면 mtime이 wver에 반영됨
    cache_dir = str(tmp_path / 'cache')

    def build_and_list():
        epp = ExtremenessPoolPredictor(
            db, target_K=500, weights_path=wpath, cache_dir=cache_dir,
            scoring_method='mahalanobis')
        epp.build_pool(train_until=1200)
        return set(os.path.basename(p) for p in glob.glob(os.path.join(cache_dir, '*.npz')))

    w_mt = os.path.getmtime(wpath)
    try:
        files0 = build_and_list()
        assert files0, "최초 build_pool이 캐시 파일을 만들지 않음"

        # D1: scorer.py mtime을 weights보다 위로 올림 -> wver=max=scorer_mt -> 새 캐시키
        os.utime(scorer_py, (w_mt + 1000, w_mt + 1000))
        files1 = build_and_list()
        new_after_scorer = files1 - files0
        assert new_after_scorer, "D1 실패: scorer.py mtime 변경이 풀 캐시를 무효화하지 못함"

        # A3: weights.json mtime을 scorer보다 위로 올림 -> wver=max=weights_mt -> 또 새 캐시키
        os.utime(wpath, (w_mt + 2000, w_mt + 2000))
        files2 = build_and_list()
        new_after_weights = files2 - files1
        assert new_after_weights, "A3 실패: weights.json mtime 변경이 풀 캐시를 무효화하지 못함"

        # 캐시 파일명에 wver가 실제로 반영되어 서로 다른 파일임을 확인
        assert len(files2) >= 3, f"무효화 시 새 캐시가 누적되어야 함: {files2}"
    finally:
        os.utime(scorer_py, (orig_scorer_mt, orig_scorer_mt))  # 원복(중요)


# ----------------------------------------------------------------------
# A4: 정책 save/load round-trip + select_target_k 결정성
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_policy_roundtrip_and_select_determinism(tmp_path):
    from src.core import extremeness_threshold_selector as sel

    curve_result = {
        'latest_round': 1227, 'folds': 5, 'window': 150, 'n_total': 750,
        'grid': [1_000_000, 1_500_000, 2_000_000],
        'curve': [
            {'target_K': 1_000_000, 'pool_ratio': 0.12, 'cutoff_mean': 1.0, 'coverage': 0.13,
             'observed_hits': 90, 'expected_random_hits': 90.0, 'lift': 1.05,
             'coverage_lcb': 0.10, 'lift_lcb': 0.85, 'reliable': True},
            {'target_K': 1_500_000, 'pool_ratio': 0.18, 'cutoff_mean': 1.0, 'coverage': 0.19,
             'observed_hits': 140, 'expected_random_hits': 138.0, 'lift': 1.05,
             'coverage_lcb': 0.16, 'lift_lcb': 0.91, 'reliable': True},
            {'target_K': 2_000_000, 'pool_ratio': 0.24, 'cutoff_mean': 1.0, 'coverage': 0.25,
             'observed_hits': 180, 'expected_random_hits': 180.0, 'lift': 1.04,
             'coverage_lcb': 0.22, 'lift_lcb': 0.92, 'reliable': True},
        ],
        'report_grid': [],
    }
    prev = {'effective_target_K': 1_500_000}

    p1 = sel.select_target_k(curve_result, previous_policy=prev,
                             selected_at='2026-06-13T00:00:00', round_num=1227)
    p2 = sel.select_target_k(curve_result, previous_policy=prev,
                             selected_at='2026-06-13T00:00:00', round_num=1227)
    assert p1 == p2, "select_target_k가 같은 입력에 비결정적"

    # 모든 후보 lift_lcb<=1 -> confirmed 없음 -> evidence=weak, raw=prev(1.5M)
    assert p1['evidence'] == 'weak'
    assert p1['effective_target_K'] == 1_500_000

    path = str(tmp_path / 'policy.json')
    assert sel.save_policy(p1, path=path) is True
    loaded = sel.load_policy(path=path)
    assert loaded == p1, "정책 save->load round-trip 불일치"


# ----------------------------------------------------------------------
# B1: 풀 예측 재현성 (같은 seed -> 같은 5세트)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_pool_predict_reproducible(db, tmp_path, small_combos):
    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
    epp = ExtremenessPoolPredictor(
        db, target_K=500, weights_path=str(tmp_path / 'w.json'),
        cache_dir=str(tmp_path / 'cache'), scoring_method='mahalanobis')
    epp.build_pool(train_until=1200)

    t1 = [p['numbers'] for p in epp.predict(num_sets=5, seed=42)]
    t2 = [p['numbers'] for p in epp.predict(num_sets=5, seed=42)]
    assert t1 == t2, "같은 seed인데 예측 5세트가 재현되지 않음"
    assert len(t1) == 5


# ----------------------------------------------------------------------
# C1: LSTM trained_round sidecar 저장/복원
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_lstm_trained_round_sidecar_roundtrip(tmp_path):
    from src.ml.lstm_predictor import LSTMPredictor
    mp = str(tmp_path / 'm.h5')
    lp = LSTMPredictor(model_path=mp)
    assert lp.trained_round is None  # 초기엔 회차 미상
    assert lp.round_path.endswith('_round.json')

    lp._save_trained_round(1227)
    assert lp._load_trained_round() == 1227

    # 별도 인스턴스가 sidecar에서 동일 회차를 복원하는가 (write->reload)
    lp2 = LSTMPredictor(model_path=mp)
    assert lp2._load_trained_round() == 1227

    # None은 저장하지 않음(회차 미상 표시 유지)
    lp3 = LSTMPredictor(model_path=str(tmp_path / 'n.h5'))
    lp3._save_trained_round(None)
    assert lp3._load_trained_round() is None


# ----------------------------------------------------------------------
# C3 + D2: reset_state code-change가 예측경로 실모델 무효화 + Optuna 미접촉
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_reset_state_targets_models_and_spares_optuna():
    from src.scripts.reset_state import plan_for, ROOT as RS_ROOT
    delete, archive, notes = plan_for('code-change')
    rels = [os.path.relpath(p, RS_ROOT).replace('\\', '/') for p in delete]

    # D2 핵심 불변: Optuna 누적 스터디/DB는 절대 삭제 대상이 아님
    for r in rels:
        assert not r.endswith('.db'), f"reset_state가 DB를 삭제 대상에 포함: {r}"
        assert 'pool_optimization' not in r, f"Optuna 풀 스터디 접촉: {r}"
        assert 'optuna' not in r.lower(), f"Optuna 접촉: {r}"

    # C3: 예측경로 실모델이 실재하면 code-change 삭제 대상에 포함돼야 함
    lstm_h5 = os.path.join(RS_ROOT, 'models', 'lstm_lotto_predictor.h5')
    if os.path.exists(lstm_h5):
        assert any('lstm_lotto_predictor.h5' in r for r in rels), \
            "C3 회귀: lstm h5가 code-change 삭제 대상에 없음"
    fe = os.path.join(RS_ROOT, 'models', 'filtered_ensemble')
    if os.path.exists(fe):
        assert any('filtered_ensemble' in r for r in rels), \
            "C3 회귀: models/filtered_ensemble가 삭제 대상에 없음"

    # dry-run 계획만 생성(실삭제 아님): notes에 안내가 포함
    assert any('무효화' in n for n in notes)


# ----------------------------------------------------------------------
# B2-note: 백테스트 K=None -> 정책 effective_target_K 상속(production 정합)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_backtest_k_none_inherits_policy(db):
    """run_pool_selection_backtest(K=None)이 정책 effective_target_K를 상속하는지 확인.

    무거운 8.14M 채점을 피하기 위해 ExtremenessPoolPredictor의 _resolve_target_k 경로만
    검증한다(백테스트가 K=None일 때 production과 동일 K를 쓰는 구조 보장)."""
    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
    from src.core import extremeness_threshold_selector as sel

    pol = sel.load_policy()
    expected_k = int(pol['effective_target_K']) if pol and pol.get('effective_target_K') else 1_500_000

    # backtest가 K=None일 때 쓰는 것과 동일 경로
    resolved = ExtremenessPoolPredictor(db).target_K
    assert resolved == expected_k, \
        f"K=None 시 백테스트가 상속할 정책 K({expected_k})와 predictor 해석값({resolved}) 불일치"


# ----------------------------------------------------------------------
# P2 fix: 앙상블 하이퍼파라미터 튜너 시그니처 호환 (레거시 3-dict + 인터페이스 1-dict)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_ensemble_update_hyperparameters_accepts_both_forms():
    """FilteredPoolEnsemblePredictor.update_hyperparameters가 두 호출 형식을 모두 수용하는지.

    과거: production 예측기(FilteredPool, 접두사 단일 dict)에 레거시 튜너(auto_ml_optimizer/
    hyperparameter_tuner)가 3-dict 위치인자로 호출 -> 'takes 2 positional arguments but 4 were
    given'으로 앙상블 Optuna 튜닝이 매 trial 실패(no-op)했다. 본 테스트로 회귀 방지."""
    pytest.importorskip("sklearn")
    from src.ml.filtered_pool_ensemble_predictor import FilteredPoolEnsemblePredictor

    e = FilteredPoolEnsemblePredictor()
    if 'rf' not in e.models:
        pytest.skip("sklearn 모델 미초기화 환경")

    # (2) 레거시 3-dict 위치인자(auto_ml_optimizer:142 / hyperparameter_tuner:207 형식)
    e.update_hyperparameters({'n_estimators': 210}, {'n_estimators': 107}, {'alpha': 0.0086})
    assert e.models['rf'].get_params()['n_estimators'] == 210, "레거시 3-dict rf 파라미터 미적용"

    # (1) 인터페이스 접두사 단일 dict
    e2 = FilteredPoolEnsemblePredictor()
    e2.update_hyperparameters({'rf_n_estimators': 150})
    assert e2.models['rf'].get_params()['n_estimators'] == 150, "접두사 1-dict rf 파라미터 미적용"
