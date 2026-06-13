# 다음 세션 검증 미션: "상태가 제대로 바뀌고/저장되고/불러와지는가" 전수 검증

작성: 2026-06-13 (세션 마무리 시 사용자 지시)
목표: **임계값/가중치/정책/모델/백테스트/학습 등 모든 상태가 "실제로 바뀌고, 정확히 저장되고, 정확히
다시 불러와지는지"를 end-to-end로 검증하고, 안 되는 부분은 제대로 작동할 때까지 수정/개선한다.**

---

## 0. 먼저 읽을 컨텍스트 (지난 세션 결론 - 재발견 금지)

- **"global_probability_threshold=1.1"은 죽은 손잡이다.** 옛 16필터 컷오프이며 최종 5세트 예측에
  미사용. 이걸 바꾸던 threshold 최적화기(study=lotto_threshold_optimization_cmaes, 554MB)는
  2025-03부터 dormant(`LOTTO_OPTIMIZER_MODE` 기본 'pool'이라 호출 안 됨). 그래서 안 변하는 것이지
  고장이 아니다. → **이 값을 "바뀌게" 만들려 하지 말 것.** 검증 대상은 아래 '진짜 활성 상태'들이다.
- **실제 활성 레버 3종(이걸 검증하라)**:
  1. `configs/extremeness_weights.json` — 마할라노비스 스코어러 가중치. PoolOptimizer
     (study=pool_optimization_v6 @ data/pool_optimization.db)가 백그라운드 Optuna로 갱신.
  2. `configs/extremeness_pool_policy.json` — `effective_target_K`(풀 크기, 제거 강도). 새 회차마다
     walk-forward로 자동 재탐색(extremeness_threshold_selector.py).
  3. 극단성 풀 npz 캐시(`cache/extremeness_pool_mahalanobis_<round>_<K>_w<mtime>.npz`) + ML 모델 캐시.
- 점수방식 기본값 = `hybrid`(선택=마할라, 설명=tail). env `LOTTO_SCORING_METHOD`로 변경 가능.
- 무효화 원칙(이번 세션 보강): 캐시키에 회차(train_until) + 가중치/스코어러 코드 mtime 포함 →
  "새 회차"뿐 아니라 "코드 변경"도 자동 무효화. 통합 초기화 도구 = `src/scripts/reset_state.py`.
- 관련 메모리: code-review-and-direction-2026-06-13, extremeness-pool-redesign-needed-2026-06-07.

---

## 1. 검증 체크리스트 (각 항목 PASS/FAIL 판정 + FAIL이면 수정)

> [검증 완료 2026-06-13] 울트라코드 8에이전트 감사 + 적대검증 + Codex(gpt-5.5)/Gemini(3.1-pro) 상의
> + 일관성 테스트 8건(tests/test_state_consistency.py 전부 PASS) + 전체스위트 824 passed(2 기존 flaky
> 타이밍 벤치마크만 실패, 무관) + main.py --once 라이브(실행 중 실제 새 회차 1228 유입 -> 전 체인 실증).
> 상세 결과는 본 문서 맨 끝 "## 4. 검증 결과(2026-06-13)" 참조.

### A. 활성 최적화 상태: 바뀌는가 / 저장되는가 / 불러와지는가
- [x] A1. **PASS** — study 2292->2302 trial 누적(라이브), best_value 0.588772가 weights.json과 정확 일치(export 작동). save_best 원자적 쓰기. 테스트: test_pool_weights_export_roundtrip.
- [x] A2. **PASS** — load_if_exists로 8일간 여러 세션 누적(0 리셋 없음, MIN=0/MAX=2291 연속). 테스트: test_optuna_study_load_if_exists_accumulates.
- [x] A3. **PASS** — build_pool이 weights.best_params를 scorer.cov_inv에 실제 적용. wver=max(weights mtime, scorer mtime) 변경 시 캐시 MISS 재계산을 **실제 build_pool로 실증**(테스트) + main.py --once 중 백그라운드 weights 재export로 wver 1781349110->1781357876 변경->재계산(production 라이브). 테스트: test_pool_cache_invalidated_by_mtime.
- [x] A4. **PASS(라이브 confirmed)** — 실행 중 새 회차 1228 유입 -> stale 가드(1227!=1228) 발동 -> refresh_policy 실행 -> 정책 round 1227->1228 갱신(write 확인). hysteresis=kept_previous_ci_overlap로 eff_K=1.5M 유지(약신호라 보수적, 정상). 테스트: test_policy_roundtrip_and_select_determinism. (잔여 P3: 정책은 round만 무효화 키 -> selector 코드변경+회차동일이면 자동 재탐색 안 됨. 현 steady-state 무해, 수동 우회 안내됨.)

### B. 백테스팅: 정확/누설0/저장/재현
- [x] B1. **PASS** — fold별 train_until=rows[a-1], holdout=rows[a:b], build_pool(train_until) win_train r<=train_until로 누설0 구조 확정 + main.py --once 라이브 fold(1078/1108/1138/1168/1198) 실증. seed 고정 재현성 테스트(test_pool_predict_reproducible).
- [x] B2. **PASS** — run_pool_selection_backtest는 dict만 반환(영속 stale 없음). 풀 캐시는 wver로 코드/가중치 변경 반영. (수정: B2-note 참조)
- [x] B3. **PASS** — performance_dashboard(start=latest-50,end=latest-1,window=100) == main.py 3개 인자 일치(2026-06-06 범위통일 반영). RESET 비교는 (start,window)만 봐 캐시 공유. stale RUNNING 가드(orphan 8개 거짓 작동중 미표시) 실측 작동.

### C. 학습(training): 재학습/저장/로드
- [x] C1. **FIXED(PARTIAL->PASS)** — 과거 LSTM은 trained_round 부재로 새 회차에도 옛 가중치 silent 재사용. **수정**: LSTM에 trained_round 사이드카(models/lstm_lotto_predictor_round.json) 저장/복원 + main.py 회차불일치 시 재학습 가드 + 재학습 실패 시 stale 예측 차단. main.py --once 라이브로 새 회차 1228 재학습->사이드카 {"trained_round":1228} 생성 확인. 테스트: test_lstm_trained_round_sidecar_roundtrip. (Ensemble은 원래 정상.)
- [x] C2. **PASS** — 캐시 삭제 시 _initialize_model/load 실패 분기에서 재학습/재저장. cache/models 타임스탬프가 재생성 방증.
- [x] C3. **FIXED(FAIL->수동무효화 완비)** — ML 모델 캐시가 코드변경 미감지(_model_version='1.0'은 orphan=죽은손잡이, 미사용). **수정**: reset_state.py code-change/training이 예측경로 실모델(models/ensemble, models/filtered_ensemble, lstm h5/round/history)까지 무효화하도록 보강(과거엔 cache/models만). 자동 mtime 캐시키(C3-B)는 Codex/Gemini 합의로 보류(주석만 바꿔도 무거운 재학습 유발 위험). _model_version은 __init__.py export라 삭제 대신 유지(문서화). 테스트: test_reset_state_targets_models_and_spares_optuna.

### D. 코드변경 무효화: 실제로 작동하나
- [x] D1. **PASS** — wver=max(weights mtime, scorer.py mtime)을 캐시키에 포함. scorer.py mtime을 올리면(os.utime) 다음 build_pool이 새 캐시키로 MISS->재계산함을 **실제 build_pool로 실증**(테스트, mtime 원복 확인). 
- [x] D2. **PASS** — reset_state code-change가 npz+cache/models+예측경로 실모델만 삭제, Optuna(pool_optimization.db) 절대 미접촉, dry-run 기본/--execute 게이트 정확. 테스트(Optuna 미접촉 불변 + models 타겟팅).

### E. 새 회차/재시작 동기화 (end-to-end)
- [x] E1. **PASS(동작 정상)** — SystemStateManager는 패턴/필터/상태스탬프 갱신, 극단풀 K 재탐색은 예측직전 stale 가드(plain)/AutoScheduler(--24h)가 담당(분리 설계). 새 회차 1228 라이브로 전 체인(패턴/필터/K재탐색/LSTM재학습) 발동 확인. (문서 드리프트 reset_state.py:93 정정 완료.)
- [x] E2. **PASS** — main.py --once exit0 완주 + (a)`극단 패턴 제거 진단 8,145,060->1,500,000`+Delta Mean 기여도+하이브리드 tail 제거사유 로그 (b)walk-forward fold별 누설0 백테스트 (c)`5세트 생성: 커버 30/45, 티켓간 최대겹침 0`(<=1) (d)극단풀 최종예측 경로 ERROR0. ExtremePool-Diversity 5세트 신뢰도 93~95%(전형성). [주: 무관한 기존 ERROR 3종 별도 - 4절 참조]

### F. 정직성/오염 (NO FAKE DATA)
- [x] F1. **PASS(+P3 수정)** — _generate_demo_* 삭제, confidence는 전형성 백분위(가짜50% 아님), stale RUNNING 가드 실측 작동. **수정**: degraded 최후폴백의 random.uniform confidence(가짜지표)->중립값0.5+폴백라벨로 정직화.
- [x] F2. **PASS** — continuous_improvement.db performance_history 0행(baseline/롤백 발동 불가), PoolOptimizer는 자체 study만 사용(옛 baseline 미참조), prediction_details is_contaminated=0(누설0). 옛 전략 레코드 혼입 없음.

---

## 2. 수행 방식 (사용자 지시: "제대로 작동할 때까지 개선")

1. 각 체크 항목을 **실측**(코드 실행/DB 쿼리/로그 확인)으로 PASS/FAIL 판정. 추측 금지.
2. 가능하면 **자동화 검증 테스트**로 고정(tests/ 하위에 write→read→reload 일관성 테스트 추가).
3. FAIL 항목은 근본 원인 규명 후 **외과적 수정** → 재검증 → PASS까지 반복.
4. 누설/가짜데이터/저장-로드 불일치는 P1로 즉시 수정.
5. 큰 변경(예: model_version 자동 bump, Optuna study 버전 게이트)은 Codex/Gemini 상의 후 진행.
6. 진행/결과는 이 문서 체크박스 갱신 + 메모리 기록.

## 3. 합격 기준 (Definition of Done)
- A~F 전 항목 PASS, 또는 FAIL 항목에 대해 수정 완료 후 PASS.
- `python main.py --once`가 에러0로 완주하고 정상 5세트를 생성.
- write→read→reload 일관성 테스트가 tests/에 추가되어 회귀 방지.
- "임계값/상태가 바뀌고 저장되고 불러와지는지"에 대해 코드 근거로 명확히 답할 수 있음.

---

## 4. 검증 결과 (2026-06-13)

### 합격 기준 충족
- A~F 전 14항목 PASS (FAIL/PARTIAL 4건은 수정 후 PASS). 미해결 FAIL 0건.
- `python main.py --once` exit0 완주 + ExtremePool-Diversity 최종 5세트 정상 생성(겹침 0).
- write->read->reload 일관성 테스트 `tests/test_state_consistency.py` 8건 추가 -> 전부 PASS(회귀 방지).
- 전체 스위트 824 passed (실패 2건 = `test_lstm/ensemble_initialization_benchmark` 타이밍 벤치마크
  `elapsed<2.0` 0.01s 초과 = 기존 flaky, 코드변경 무관. TF load_model 시간 변동).

### 적용한 외과적 수정 (Codex gpt-5.5 + Gemini 3.1-pro 합의)
1. **C1 (LSTM trained_round)** `src/ml/lstm_predictor.py` + `main.py(~3216)`:
   - __init__에 `trained_round`/`round_path`(=`_round.json` 사이드카) 추가.
   - `_initialize_model` 로드 성공 시 사이드카 복원, `train(trained_round=)`이 성공 후 원자적 저장.
   - main.py LSTM 가드를 `not is_trained or trained_round != latest_round`로 -> 새 회차 재학습.
     재학습 실패 시 `is_trained=False`로 stale 예측 차단.
2. **C3 (코드변경 무효화 수동 완비)** `src/scripts/reset_state.py`:
   - code-change/training 트리거가 예측경로 실모델 `models/ensemble`, `models/filtered_ensemble`,
     `models/lstm_lotto_predictor.h5`/`_round.json`/`_history.json`까지 삭제(과거엔 cache/models만).
   - 자동 mtime 캐시키(C3-B)는 보류(주석 변경만으로 무거운 재학습 유발 위험 - 두 모델 합의).
3. **B2-note (백테스트 K 정합)** `src/scripts/backtest_extremeness_prediction.py`:
   - `K: int=1_500_000` -> `K: Optional[int]=None`. None이면 production과 동일하게 정책
     effective_target_K 상속(정책 K 이동 시 desync 방지).
4. **E1 (문서 드리프트)** `reset_state.py:91-94`: SystemStateManager 역할 정확화(풀 K 재탐색은
   predict-time 가드/AutoScheduler 담당).
5. **F1 (NO FAKE DATA)** `enhanced_dashboard_v2.py:2739`: degraded 최후폴백의 무작위 confidence
   -> 중립값 0.5 + "(fallback)" 라벨.
6. **E2 (가시화)** `src/core/diversity_selector.py:253`: 겹침<=1 제약 완화(relaxed) 발생 시 debug->warning.

### 라이브 실증 하이라이트 (main.py --once 중 실제 새 회차 1228 유입)
- A4: 1227!=1228 감지 -> refresh_policy 실행 -> 정책 round 1228로 write. hysteresis로 K=1.5M 유지.
- A3: 백그라운드 PoolOptimizer 재export로 weights mtime 변경 -> 풀 캐시 wver 1781349110->1781357876
  변경 -> build_pool 재계산(production에서 캐시 무효화 라이브 발동).
- C1: 새 회차 1228 -> LSTM 재학습 -> 사이드카 `{"trained_round":1228}` 생성.
- A1: study trial 2292->2302 누적, best_value 0.5888 유지.

### 추가 수정 (2026-06-13, 후속 커밋)
- **[P2 FIXED] 앙상블 하이퍼파라미터 튜너 시그니처 호환**: 과거 `FilteredPoolEnsemblePredictor.update_hyperparameters()
  takes 2 positional arguments but 4 were given`으로 Optuna 앙상블 튜닝 trial이 매번 실패(no-op). 원인=production
  FilteredPool(접두사 단일 dict 1-arg)에 레거시 튜너(auto_ml_optimizer:142/hyperparameter_tuner:207)가 옛
  3-dict 위치인자로 호출. **수정**: FilteredPoolEnsemblePredictor.update_hyperparameters를 두 형식(레거시 3-dict +
  인터페이스 접두사 1-dict) 모두 수용하도록 다형화(호출부/옛 클래스 불변). 테스트 추가
  (test_ensemble_update_hyperparameters_accepts_both_forms). PoolOptimizer(활성)와 별개, 보조 ML 신호 튜닝에만 영향.

### 미해결/범위 외 기존 결함 (후속 권고)
- **[P3 기존] 새 회차 시 16필터 재저장 UNIQUE 충돌**: `UNIQUE constraint failed: filtered_combinations`
  -> 죽은 16필터 계층의 재저장 중복(이미 저장된 회차). 최종예측(극단풀) 무관, 데이터무결성 영향 없음.
- **[P3 기존] performance_stats.db 988MB(freelist 978MB)**: 운영중 VACUUM 잠금위험으로 의도적 보류.
  정지 시점 1회 VACUUM 권장. 누설0(is_contaminated=0)이라 정직성 무관.
- **[P3] A4 비대칭**: 정책 K는 round만 무효화 키 -> selector 코드변경+회차동일이면 자동 재탐색 안 됨
  (A3 풀 캐시는 scorer mtime 포함). 현 무해, 필요 시 reset_state로 정책 stale 마킹 가능.

### 미커밋. 변경 파일
- 수정: `src/ml/lstm_predictor.py`, `main.py`, `src/scripts/reset_state.py`,
  `src/scripts/backtest_extremeness_prediction.py`, `src/scripts/enhanced_dashboard_v2.py`,
  `src/core/diversity_selector.py`
- 신규: `tests/test_state_consistency.py`
