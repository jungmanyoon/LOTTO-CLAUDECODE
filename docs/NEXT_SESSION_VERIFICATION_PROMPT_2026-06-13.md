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

### A. 활성 최적화 상태: 바뀌는가 / 저장되는가 / 불러와지는가
- [ ] A1. PoolOptimizer를 N trial 돌렸을 때 `data/pool_optimization.db`의 trial 수가 실제로 증가하는가?
      best_value가 갱신되면 `configs/extremeness_weights.json`에 export되는가? (쓰기 검증)
- [ ] A2. 재시작 후 같은 study(pool_optimization_v6)를 load_if_exists로 정확히 이어받는가?
      (불러오기 검증 - trial 수가 0으로 리셋되지 않아야 함)
- [ ] A3. `extremeness_weights.json`을 build_pool이 실제로 읽어 scorer에 적용하는가? 가중치를 일부러
      바꾸면 풀 캐시가 wver(mtime) 변화로 무효화되고 풀이 달라지는가? (write→read→effect 일관)
- [ ] A4. target_K 정책: 새 회차가 들어오면 `extremeness_pool_policy.json`의 round/effective_target_K가
      갱신되는가? 갱신 후 build_pool이 새 K로 풀을 만드는가? hysteresis가 의도대로 동작하는가?

### B. 백테스팅: 정확/누설0/저장/재현
- [ ] B1. `backtest_extremeness_prediction.run_pool_selection_backtest`가 train_until <= 회차로 누설 0인가?
      (이미 검증됐으나 재확인) 같은 seed/fold면 결과가 재현되는가?
- [ ] B2. 백테스트 결과가 어디에 저장되고(backtest_state.json / results/*.db / performance_stats.db),
      재시작 시 캐시가 코드/전략 변경을 반영하는가? 옛 결과를 새 전략에 잘못 재사용하지 않는가?
- [ ] B3. 대시보드 백테스트 범위(performance_dashboard latest-50~latest-1)와 main.py 범위가 일치해
      불필요한 RESET 재백테스트가 안 도는가? (이번 세션 stale RUNNING 가드 포함 확인)

### C. 학습(training): 재학습/저장/로드
- [ ] C1. 새 회차 시 LSTM/Ensemble이 trained_round != latest를 감지해 실제 재학습+재저장하는가?
      (cache/models 갱신 확인)
- [ ] C2. 모델 캐시를 지운 뒤(clear_model_cache 또는 reset_state --on training) 다음 실행에 재생성되는가?
- [ ] C3. 모델 구조/특징 코드를 바꿨을 때 옛 모델이 silent 재사용되지 않는가? (현재 _model_version='1.0'
      고정 = 코드변경 미감지 → 이 GAP을 reset_state로 메우거나 model_version 자동 bump 구현 검토)

### D. 코드변경 무효화: 실제로 작동하나
- [ ] D1. `extremeness_scorer.py`를 (의미 없는) 한 줄 수정 → mtime 변경 → 다음 build_pool이 캐시 미스로
      재계산하는가? (이번 세션 보강한 wver=max(weights mtime, scorer mtime) 실증)
- [ ] D2. `reset_state.py --on code-change --execute`가 의도한 캐시만 정확히 지우고, Optuna 누적은
      안 건드리는가? dry-run/execute 동작 정확한가?

### E. 새 회차/재시작 동기화 (end-to-end)
- [ ] E1. 새 회차를 모의 주입(또는 실제 새 회차)했을 때 SystemStateManager가 감지 → 패턴/필터/풀/ML
      재계산 체인이 도는가? 무엇이 재계산되고 무엇이 누락되는가?
- [ ] E2. `python main.py --once` 한 사이클 실제 실행 → 로그에서 (a)풀 형성(hybrid, 화이트박스 제거사유)
      (b)백테스트 누설0 (c)최종 5세트 생성(겹침<=1) (d)에러0 을 확인. 최종 5세트가 정상 출력되는가?

### F. 정직성/오염 (NO FAKE DATA)
- [ ] F1. 대시보드/로그에 가짜 지표나 stale RUNNING 거짓 "작동중"이 안 뜨는가?
- [ ] F2. 옛 전략(threshold v3/v4) 성능 레코드가 새 전략 baseline 비교에 섞여 잘못된 롤백/판단을
      유발하지 않는가? (performance_stats.db / continuous_improvement.db 태깅 검토)

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
