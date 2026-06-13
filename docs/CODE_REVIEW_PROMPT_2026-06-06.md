# 코드리뷰 검증 프롬프트 (다음 세션용) - 2026-06-06 수정분 전수 검증

> 아래 블록 전체를 다음 세션 첫 메시지로 붙여넣으세요.

---

너는 한국 로또(6/45) 예측 시스템의 코드 감사 담당이다. **울트라코드로 진행하고, Codex(gpt-5.5)와 Gemini(3.1-pro)와 협업**하라. 모든 응답은 한국어.

## 목표
2026-06-06 세션에서 수정한 모든 변경이 **제대로 구현·동작하는지** 전수 검증한다. 추측 금지 - 반드시 (1)코드를 직접 Read, (2)런타임/DB로 실측, (3)테스트로 회귀 확인하여 **증거(file:line 또는 실행결과)**로 판정하라. "통과"와 "문제"를 정직하게 구분하고, 문제 발견 시 근본원인+외과적 수정안을 제시하라.

## 먼저 읽을 것 (맥락)
메모리 디렉토리의 다음 파일을 읽고 전체 맥락을 파악하라:
- `backtest-postlogic-db-audit-2026-06-06.md` (감사 + realignment + 위생수정)
- `single-executable-resident-and-dashboard-fixes-2026-06-06.md` (상주화 + 대시보드)
- `honest-tuning-loop-and-ensemble-fix-2026-06-05.md` (앙상블/튜너)
- `prediction-selection-already-optimal-2026-06-05.md` (선택단계 최적)

대상 커밋: `git show --stat ad6e0d6` 와 `git show --stat da52749` 로 변경 파일 확인.

## 절대 위반 금지 (프로젝트 전략)
- "독립시행이라 무의미/어차피 1/8,145,060" 류 확률강의 영구금지. 사용자는 알고 '극단 제거 + 남은 풀 예측' 전략을 의도적으로 채택함.
- 최종 5세트 예측 = 극단성 풀(ExtremenessPoolPredictor). ML/백테스트는 그 보조/검증. 이 전제 위에서 검증할 것.

---

## 검증 체크리스트 (각 항목: PASS/FAIL + 증거)

### A. 단일 실행파일 상주화 (main.py, 커밋 ad6e0d6)
- [ ] `--once` argparse 인자 존재
- [ ] 대시보드 시작 직전 `_one_shot`/`_resident_mode` 게이트 존재. one_shot = once|ml_only|predict_only|fetch_only|skip_fetch|automation_test
- [ ] 상주 시 `args.dashboard=True` 강제(단 --no-dashboard 존중)
- [ ] 사이클 종료부(`[완료]` 직후)에 `if _resident_mode:` keep-alive 루프(`while not optimization_stop_flag.get('stop'): time.sleep`)
- [ ] Ctrl+C(SIGINT)가 graceful_shutdown으로 최적화/스케줄러 정리 후 종료
- **실측**: `python main.py --once --predict-only --skip-ml --skip-fetch` 가 **hang 없이 exit 0**(타임아웃으로 확인). plain `python main.py`가 사이클 후 상주하는지(로그에 `[상주]` 출력) 확인.
- **함정 점검**: AutoScheduler가 spawn하는 subprocess(`--skip-fetch`)가 상주 안 하고 1회 종료하는지(hang 방지) 확인.

### B. 앙상블 사일런트0 복구 (main.py)
- [ ] fresh 앙상블 예측 0개 시 `EnsemblePredictor()` 새 인스턴스 `load_models()` 후 재예측 복구 블록 존재
- [ ] 재사용 실패 로그가 `debug`→`warning`으로 가시화됨
- **실측**: 캐시 앙상블 모델 로드 후 `predict_next_numbers(winning_numbers, 5)`가 5개 반환하는지(복구경로 동작) 확인.

### C. 대시보드 3종 (enhanced_dashboard_v2.py + extremeness_pool_predictor.py)
- [ ] `generate_new_predictions`가 `_epp.predict(..., seed=random)` 매 호출 무작위 seed → 클릭마다 다른 5세트
- [ ] `extremeness_pool_predictor.predict()`의 confidence가 0.5 고정이 아니라 `_ticket_typicality` 백분위(50~95%)
- [ ] `_ticket_typicality` 메서드 존재(pool_quality 백분위)
- [ ] `optimizer-status` API fallback이 `data/pool_optimization.db`에서 누적 trials/best 읽음
- **실측**: (1) predict를 seed 다르게 2회 → 번호 다름 + 점수 다 다름(50 아님). (2) pool_optimization.db 쿼리로 trials 수/best 확인. (3) 대시보드 재시작 후 OPTUNA 패널에 누적 trial 표시되는지(가능하면).

### D. 백테스트 realignment (main.py + backtest_extremeness_prediction.py, 커밋 da52749) **★핵심**
- [ ] `backtest_extremeness_prediction.py`에 `run_pool_selection_backtest(db, folds, window, K, ...)` 함수 존재, dict 반환(rank_hit_rate/mean_bm/rand_*/lift_*)
- [ ] **blind 검증**: 함수가 fold마다 `build_pool(train_until=fold_start-1)`로 미래정보 차단하는지 코드 확인
- [ ] main.py 백테스트 단계에서 `run_pool_selection_backtest` 호출 + `[풀 백테스트]` 로그(등수적중률/mean_bm/무작위 대비 lift)
- [ ] 최종 예측 출력에 `[검증]` 요약 + "절대 당첨확률 아님, 1.5M 풀 내 커버리지 최선 포트폴리오" 문구
- **실측**: `run_pool_selection_backtest(db, folds=5, window=30)` 실행 → PROD 등수적중률이 무작위(RAND_ALL)보다 높은지(이전 실측 PROD~12.7% vs 무작위~10.7%). **누설 적대검증**: PROD가 무작위보다 3~6개 매치로 폭증하면 누설(버그), 0.8~1.9 범위면 정상.

### E. DB/후속 위생 수정 (main.py, 커밋 da52749)
- [ ] **A 가짜추정 제거**: ml_inclusion_rate `*0.085` 하드코딩, combination_count `8145060*(1-thr/100)` 추정 코드가 **삭제**됨(grep으로 부재 확인)
- [ ] **B cleanup 배선**: 백테스트 후 `cleanup_old_data(keep_days=30)` 호출 존재. (실측: 호출 후 prediction_details 30일 초과 행 감소하는지 - 단 첫 호출은 무거우니 주의)
- [ ] **C 피드백 정직로그**: 피드백루프 진입 로그가 "자동 모델 개선중"이 아니라 "레거시(상태영속전용), 실제 최적화는 PoolOptimizer" 로 변경됨
- [ ] **D normalize_score 통일**: 자동조정 점수가 인라인 `min(1.0,avg/2.0)` 대신 `PerformanceMetrics.normalize_score` 사용(수식 동일성도 확인)
- **적대 점검**: 피드백루프(EnhancedFeedbackLoop)가 여전히 no-op인지(개선 영속 0), PoolOptimizer(pool_optimization.db)는 trial 누적·best 개선 중인지 대조.

### F. 무결성/회귀 (전체)
- [ ] `python -m py_compile main.py src/scripts/backtest_extremeness_prediction.py` OK
- [ ] `python -m pytest tests/ -k "backtest or performance or auto_adjust or feedback or threshold" --no-cov -q --timeout=120` 통과(이전 203 passed)
- [ ] **DB 스키마 변경 0 / 모델 재학습 0 확인** → 초기화 불필요(사용자 반복 우려)
- [ ] lotto_numbers.db / pool_optimization.db / performance_stats.db 손상 없음

### G. 정직성 최종 점검
- [ ] 어디에도 가짜 확률/더미 데이터가 metric으로 둔갑하지 않는지(CLAUDE.md NO FAKE DATA)
- [ ] 로그가 실제 동작과 일치하는지(거짓 "개선중" 없는지)
- [ ] 변경이 최종 5세트 예측 결과를 의도치 않게 바꾸지 않았는지(seed 동일 시 재현성, 단 dashboard는 의도적 seed 변동)

---

## 보고 형식
1. **요약 표**: 항목(A~G) × PASS/FAIL/부분 + 한 줄 근거
2. **FAIL/부분 상세**: 근본원인 + file:line + 외과적 수정안 + 검증법
3. **적대검증 결과**: 누설 없음 / 피드백 no-op / PoolOptimizer 개선 중 등 핵심 4건
4. **최종 판정**: "이번 수정 제대로 됐는가" 한 줄 결론 + 잔여 리스크

장황한 서론 금지. 발견을 증거로 뒷받침하라.
