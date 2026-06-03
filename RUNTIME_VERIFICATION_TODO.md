# 실제 실행(런타임) 검증 결과 (TODO)

> 2026-06-03. 코드리뷰 81건 수정·커밋(c69d9b4, 794 passed)이 **실제 `python main.py` 실행 로그**에서
> 의도대로 작동하는지 검증. 단위테스트를 넘어 런타임 증거로 확인.
> 검증 방식: 격리 콘솔 러너로 main.py 2회 실행(정상 사이클 1회 + 작업중 SIGINT 1회) + 26 AI 에이전트
> 워크플로우(7영역 병렬 분석 + 적대검증).
> 근거 로그(동결 스냅샷): `logs/_verify_app_snapshot.log`(run1, 1530줄), `logs/_verify_app_snapshot2.log`(run2),
> `logs/_verify_console_snapshot.log`(run1 stdout).

## 사용법
- 완료 시 `- [ ]` -> `- [x]` 로 바꾸고 줄 끝에 `(완료: YYYY-MM-DD, 커밋해시)` 표기.
- 각 항목은 [심각도] + 로그근거(라인인용) + 수정안 + 쉬운설명(비유) 포함.

---

## 핵심 결론 (한 줄 요약)

**81건 수정의 핵심은 실제 실행에서 거의 다 의도대로 작동했다.** ERROR/Traceback 0건(run1), 가짜데이터 0건,
통과율95% 강제제약 제거 작동, 종료 데이터오염 다층방어(정상종료 경로) 작동, 극단성 풀(8.14M->1.5M) 캐시 작동.
**치명적 P0/P1 런타임 실패는 없음.** 다만 **신규/잔존 이슈 P2 3건 + P3 7건**을 새로 발견했다.

비유: "리모델링한 공장을 실제로 가동해 보니, 큰 기계들은 다 제대로 돌았다. 빨간 경고등도 안 켜졌다.
그런데 (1)5개 예측기 중 1~2개가 조용히 빈손으로 돌아오고, (2)온라인 학습 라인이 9개월째 멈춰 있고,
(3)가동 중에 비상정지 버튼(Ctrl+C)을 누르면 곧바로 안 서고 강제차단에 의존하는 점이 보였다."

---

## A. 81건 수정 - 런타임 작동 매핑 (실제 로그로 확인)

| 수정 항목 | 상태 | 로그 근거 |
|-----------|------|-----------|
| optimization-6 (통과율95% hard constraint 제거) | [O] 작동확인 | run1 snap:647 "통과율 기반 필터 자동 완화 비활성화(사용자 확정: 통과율 제약 제거)", snap:826/835 "목적: 분리도 AUC + 약한 lift LCB (통과율 제약 없음)" |
| optimization-7 (극단성 풀/all_combinations 캐시) | [O] 작동확인 | run1 snap:1441 "[극단풀] 캐시 로드: extremeness_pool_1226_1500000...npz (1,500,000개)" - 8.14M 재생성 없이 캐시 재사용 |
| 극단성 풀 최종예측 경로 (핵심전략) | [O] 작동확인 | run1 snap:1443 "극단성 풀 경로 사용 (K=1,500,000)", snap:1442 "5세트 생성: 커버 30/45번호, 티켓간 최대겹침 0" (다양성 레버 작동) |
| optimization-1 (OptimizationDB 스키마 통합) | [O] 작동확인 | "no such column" 에러 0건, 최적화 DB 정상 init |
| 0개 제거 조기탈출 (필터 63분 낭비 제거) | [O] 작동확인 | run1 snap:720 "확률 필터: 제거 후보 패턴 부족 -> 전수 스캔 생략(0개 제거 확정)" |
| 종료 데이터오염 다층방어 (정상/atexit 경로) | [O] 작동확인 | run1 snap:1488 "[PoolOpt] 종료 신호 감지 - Optuna study 조기 중단", snap:1497 상태저장, 깨끗한 종료 |
| 쓰레기 trial 방지 (avg=0/score=0.15 거부+TrialPruned) | [O] 작동확인 | 종료 중 쓰레기 trial 대량생산 없음, PoolOpt 조기중단 |
| feedback-loop 중복 가드 | [O] 작동확인 | run1 snap:1226 "[중복 가드] ... 개선 사이클 조기 종료" (시그니처 동일 감지) |
| health-repair (성능 하락 자동 롤백) | [O] 작동확인 | run1 snap:1194-1207 "성능 대폭 하락 -25.5% 감지 -> 백업 -> 최고성능 설정 롤백 완료" |
| ml-probabilistic-1 (거짓'완료' 제거->정직 실패로깅) | [O] 작동확인 | run1 snap:735-736 WARNING+원인명시+폴백, snap:1300-1301 "성능 저하 감지, 업데이트 건너뜀"(거짓 완료 아님) |
| ml-probabilistic-2 (FilteredPoolLSTM train) | [O] 작동확인 | LSTM 학습/예측 정상(snap:744 "LSTM 예측 완료: 5개"), 메서드 부재 예외 없음 |
| dashboard-monitoring-1 (가짜 보너스 random 제거) | [O] 작동확인 | 실DB get_numbers_with_bonus 사용, 가짜 보너스 생성 흔적 0건 |
| 02642b1 (거짓'약 20만개' 제거+조회실패 원인로깅) | [O] 작동확인 | run1 snap:735-736 조회 실패 원인까지 정직 로깅 |
| avg_matches 정상 산출(overall_avg_matches 키) | [O] 작동확인 | run1 백테스팅 모델별 avg 0.79~0.88 정상(snap:1104-1151), 0 삼킴 없음 |
| ml-lstm-ensemble-1 (ensemble random 제거->정직 빈리스트) | [!] 부분작동 | "정직한 빈리스트" 자체는 작동하나, 근본 차원불일치로 앙상블이 조용히 0개 기여 (->P2-1) |
| LSTM sequence_length=15 | [?] 불명 | 런타임 로그에 명시 미출력(설정값-코드검증 사항). 별도 코드확인 필요 |
| orchestration-2 (시그널 핸들러 sys.exit 실제종료) | [?] 불명/주의 | run1은 atexit 경로(정상종료)라 SIGINT 경로 미검증. run2 SIGINT 작업중 발동 실패 (->P2-3) |

**소결**: 16개 핵심 매핑 중 작동확인 14, 부분작동 1, 불명 2. 미작동 0.

---

## B. 신규/잔존 이슈 (우선순위별)

### [P2-1] 앙상블 실시간 예측이 사일런트 0개 반환 (scaler 특징차원 81 vs 131 불일치)
- [x] **수정 완료** (2026-06-03, 미커밋)
- 영역: ML 예측 / 관찰성
- 로그 근거: run1 snap:751 "[최적화] 저장된 앙상블 모델 재사용(학습회차 1226=최신, 재학습/미세조정 스킵)" -> snap:752 "앙상블 예측 완료: 0개 조합" (두 줄 사이 WARNING/ERROR/Traceback 전무, timestamp 동일=즉시 0개). 결과: snap:788 "총 예측 수: 9개", snap:792 "모델 다양성: 3개", snap:796-798 출처 "[lstm, monte_carlo, bayesian]" (ensemble 기여 누락). 대조: 백테스팅 경로에선 ensemble 정상(snap:844-851 "ensemble 5/5", snap:1246 "Ensemble: 1.400").
- 근본원인(워크플로우 규명): 저장된 앙상블 모델 **재사용 경로**에서 scaler가 기대하는 특징 차원(예: 81)과 실제 입력 차원(예: 131)이 불일치 -> 내부에서 빈 결과로 떨어지나 그 경로에 경고가 없어 사일런트.
- 영향: ML "Combined" 예측이 5종(lstm/ensemble/mc/bayesian/fractal) 중 3종으로만 합성됨. **단, 최종 5세트는 극단성 풀(K=1.5M)에서 생성되므로 최종 출력 자체는 정상** -> blast radius 제한적(그래서 P1 아닌 P2).
- 수정안:
  1. (필수) `src/ml/filtered_pool_ensemble_predictor.py`: 학습 시 사용한 특징 컬럼 순서를 `self.feature_columns`에 저장하고 `save_models()`의 `ensemble_config_filtered.json`에 `feature_columns` 키 추가. `load_models()`에서 복원 -> `predict_from_filtered_pool`의 reindex 분기(약 line 490) 활성화로 `reindex(columns=feature_columns, fill_value=0)` 강제 차원 일치.
  2. (관찰성) `main.py:3276` 직전 `if len(ensemble_predictions)==0:` 시 진단 WARNING 출력(is_trained, filtered_pool 크기, pool_size 등) -> 매 실행마다 0개가 정상인지 결함인지 로그로 판별.
- 쉬운 설명: 5명의 예측가 중 1명(앙상블)이 "어제 쓰던 자(scaler)"로 "오늘 더 긴 종이(131칸)"를 재려다 칸이 안 맞아 백지로 제출. 시험관은 "제출 완료(0장)"로만 기록해 아무도 눈치 못 챔. 학습 때 쓴 칸 목록을 저장해 두고 잴 때 그 칸에 맞추면 해결.
- **근본원인 100% 재현 확정**: 캐시 config(`models/filtered_ensemble/ensemble_config_filtered.json`)에 `feature_columns` 미저장 + scaler `n_features_in_=131` 확인. 실제 캐시로 `predict_next_numbers` 호출 시 `ValueError: X has 81 features, but StandardScaler is expecting 131 features` 발생 -> except 824에서 `logging.exception`이 ERROR로 찍히나, **run1/run2 메인 로그엔 전무**(main.py 로깅 설정에서 이 예외가 사라져 완전 사일런트 0개 = 관찰성 결함 동반).
- **적용한 수정** (`src/ml/filtered_pool_ensemble_predictor.py`):
  1. `__init__`에 `self.feature_columns = None` 초기화.
  2. `save_models()` config에 `'feature_columns'` 저장(영속화).
  3. `load_models()`에서 복원 + **구버전 캐시 self-heal**: is_trained=True인데 feature_columns 없으면 명시 WARNING 후 `is_trained=False`로 내려 재학습 유도(조용한 실패 금지). 재학습 시 feature_columns가 저장되어 이후 재사용은 정상 앙상블 가중예측.
- **검증**: (a) save/load 라운드트립 feature_columns 131개 복원 [O], (b) 구캐시 self-heal(is_trained->False)+경고 [O], (c) 실제 구캐시 predict가 사일런트 0개 대신 정직 폴백(source=random_from_pool, 실제 풀 조합 5개)+경고 노출 [O], (d) 관련 단위테스트 **44 passed**(test_filtered_pool_system/trainer/ml_models/improved_ml_filter_integration).
- 부수효과: 다음 main.py 실행 시 구캐시(2026-06-01) 1회 재학습(약 8분) 후 자가치유. 이후 재사용 정상.

### [P2-2] 실시간 학습 루프 영구 정체 (성능 1회 하락 후 업데이트 영구 차단)
- [ ] **수정 필요**
- 영역: ML / 데이터 무결성
- 로그 근거: run1 snap:1300 "lstm: 성능 저하 감지(-0.1500), 업데이트 건너뜀", snap:1301 "ensemble: 성능 저하 감지(-0.1667), 업데이트 건너뜀", snap:1308-1311 "[LSTM] 업데이트 횟수:17 / 마지막 업데이트: **2025-09-02** / 평균 0.1000 / 최근 0.0000" (ENSEMBLE 마지막 2025-08-29, MC 2025-09-14).
- 근본원인: adaptive_update 게이트가 "직전 1스텝 성능 비교"로만 판정. 성능 0.15->0.0 한 번 하락하면 이후 매번 "저하"로 판정되어 업데이트를 영구 차단. 결과적으로 온라인 학습이 약 9개월간 멈춤. 또한 단발 실행(plain main.py)은 24시간 자동복구 경로에 도달하지 못함.
- 영향: 핵심전략상 ML은 "풀 다양성 가중치" 역할이라 치명적이진 않으나, 새 회차 데이터가 반영 안 되어 점점 낡아짐.
- 수정안: `src/ml/realtime_learning_system.py` 게이트(약 line 220-224)를 "최근 N개 추세 비교"로 완화하거나 `consecutive_skips >= 3`이면 강제 1회 업데이트. 성능 0.0이 "실제 0일치"인지 "평가실패"인지 구분해, 평가실패면 history에 0.0을 append하지 않도록 보강(약 line 313-315/403-405).
- 쉬운 설명: "한 번 성적 떨어진 학생은 다시는 공부 못 하게" 막아둔 셈. 9개월째 책을 안 펴고 있다. "3번 연속 막히면 한 번은 그냥 시켜주기" 규칙을 넣어야 함.

### [P2-3] 작업 중 SIGINT(Ctrl+C)가 graceful_shutdown을 발동 못 시킴 -> 강제킬 의존 (런타임 전용 발견)
- [ ] **확인/수정 필요** (run2 검증)
- 영역: 종료 / 데이터 안전
- 로그 근거: run2 시작 13:29:18, SIGINT 전송 시점 13:31:08(백테스팅+PoolOpt v6 워커 시작 snap2:833 직후). 이후 **약 62초간 백테스팅 166줄 추가 출력**, "프로그램 종료 신호 감지"/KeyboardInterrupt/graceful 마커 **전무**, 75초 타임아웃 후 강제 종료(exit 1). 러너 상태: `graceful_shutdown:false, ctrl_c_result 전부 true`(신호 전달 자체는 성공).
- 대조: run1(정상 사이클 완료->자체 종료)은 **atexit 경로**로 graceful_shutdown 정상 작동(3초내 깨끗이 종료).
- 해석: 81건의 "종료 데이터오염 다층방어"는 **정상/atexit 종료 경로만 보호**하고, 현실적으로 가장 흔한 "작업 중 Ctrl+C" 경로에서는 main 스레드가 멀티프로세싱 백테스트의 네이티브 대기에 묶여 SIGINT를 즉시 처리하지 못해 graceful_shutdown이 아예 안 돈다. (Windows + ProcessPoolExecutor 신호전달 한계 가능성)
- 데이터오염 위험: SQLite WAL의 원자성 덕에 강제킬 시에도 부분저장 흔적은 관찰 안 됨(위험 완화됨). 그러나 "다층방어가 우회된다"는 점은 설계 의도와 어긋남.
- 수정안(택1): (a) 백그라운드 워치독 스레드가 stop_flag 감지 시 일정 시간 내 미종료면 os._exit 전에 핵심 정리만 보장, (b) 백테스트 future 수집 루프에 stop_flag 체크 주기 삽입(네이티브 대기 단축), (c) 최소한 "작업 중 Ctrl+C는 강제킬될 수 있음"을 문서화 + 실제 사용자 터미널에서 재확인.
- 쉬운 설명: 기계가 한창 돌 때 비상정지 버튼을 눌렀는데, 기계가 "지금 큰 작업 중이라" 1분 넘게 못 듣다가 결국 차단기를 내려야 멈췄다. 평소(작업 끝나고 종료)엔 잘 멈춘다.

### [P3-1] IntegratedFilterManager.get_filtered_count 메서드 부재 (표시용 죽은 호출)
- [ ] 수정 권장(경미)
- 로그 근거: run1 snap:736 "필터링 조합 수 조회 실패 ... 'IntegratedFilterManager' object has no attribute 'get_filtered_count'".
- 적대검증 결론: ML이 실제 쓰는 풀은 정상 공급되고, 이 호출은 **로그 표시용 죽은 호출**일 뿐(폴백 동작). 기능 영향 없음, 매 실행 WARNING 노이즈만.
- 수정안: `get_filtered_count` 메서드를 추가하거나 해당 호출부를 제거. (호출부는 snap:735 직전 ML 풀 크기 조회 지점)

### [P3-2] Fractal 모델 미실행 (Combined가 5종 중 3종만 합성)
- [ ] 확인 권장
- 로그 근거: run1 snap:796-798 Combined 출처 "[lstm, monte_carlo, bayesian]"에 ensemble/fractal 없음. 가중치 테이블엔 fractal 존재하나 "프랙탈 예측 완료" 로그 부재.
- 영향: P2-1(앙상블 누락)과 합쳐 ML 다양성이 5->3으로 축소. 최종 출력은 극단성 풀이라 제한적.
- 수정안: fractal 예측 경로가 의도적 비활성인지(조건부) 확인 후, 활성이어야 하면 호출부 점검.

### [P3-3] LSTM/Bayesian 예측 raw 로깅에 np.int32 원시 타입 노출
- [ ] 수정 권장(미관)
- 로그 근거: run1 snap:745 "[np.int32(8), np.int32(16), ...]", snap:773 동일. (Monte Carlo는 일반 int)
- 적대검증 결론: downstream 무해(최종 5세트/JSON/DB 저장 전부 일반 int, 직렬화 에러 0건). 순수 로그 가독성 문제.
- 수정안: 로그 출력 직전 `[int(x) for x in combo]` 변환.

### [P3-4] 메모리 모니터 임계값(1500MB)이 실제 피크(3455MB)와 비현실적 괴리
- [ ] 조정 권장
- 로그 근거: run1 snap:1518 "여유율(피크 기준): 0.0% (피크 3455.3MB / 임계값 1500.0MB)", snap:808 백테스팅 시작 2701MB, snap:1521 GC로 761MB 해제 후 정상 종료.
- 적대검증: 알림 기능 자체가 (참고지표라) 즉시 위험은 아니나 임계값이 사실상 상시 초과라 무의미. 수정안: 임계값을 현실값(약 3.5~4GB)으로 재조정하거나 배치 크기 축소 검토.

### [P3-5] 백테스팅 검증윈도우 설정(300회차) vs 실제 실행(50개) 불일치
- [ ] 확인 권장
- 로그 근거: run1 console "검증 윈도우: 300 회차(훈련: 150)" vs 실제 백테스팅 회차 수 50개대 관찰. 설정-실행 불일치(자동조정 영향 가능).

### [P3-6] 백테스팅 횟수 카운터 불일치 (성능보고서 288회 vs 자동개선관리자 873회)
- [ ] 확인 권장(관찰성)
- 로그 근거: run1 snap:1424 "백테스팅 횟수: 288회" vs snap:1232/1497 "총 누적 백테스팅 횟수: 873회". 서로 다른 카운터가 다른 값 -> 어느 게 진짜인지 혼동.

### [P3-7] 필터링 결과 요약 로그 순서 역전
- [ ] 수정 권장(미관)
- 로그 근거: run1 "이미 최신 필터링 완료"(snap:~714 부근) 출력 후 약 49초 뒤 "초기 조합 수: 8,145,060개" 요약(snap:716) 출력 -> 시간 순서가 어색해 오독 유발.

---

## C. 관찰 사항 (버그 아님, 설계/문서 확인 필요)

### [관찰-1] plain `python main.py`는 한 사이클 후 자체 종료 (무한 상주 아님) — 조사 완료, A안(문서보강) 적용
- [x] **해결: 문서 보강** (2026-06-03, 미커밋 / 사용자 결정=A안 저위험)
- 적용: CLAUDE.md(Quick Start + Common Commands + Complete Automation 섹션) 및 README.md(Quick Start + 기본 실행)에 "plain=원샷 1사이클 후 종료, 상주는 `--24h`, 대시보드/백그라운드최적화는 daemon"을 명시. 코드 무변경.
- 조사 확정 근거:
  1. 상주 무한루프(`run_24h_automation`의 `while self.running`)는 `--24h` 플래그가 있을 때만 호출(main.py:2713-2721)되고, 그마저 line 2721에서 `return`하므로 **예측 사이클과는 다른 경로**(AutomationCoordinator, 매일 09시 예약 예측).
  2. 대시보드 스레드는 `threading.Thread(..., daemon=True)`(main.py:2109) -> **main 종료 시 함께 죽음**.
  3. 백그라운드 최적화 `UnifiedOptimizer.start_background`도 `daemon=True` 스레드(unified_optimizer.py)로 즉시 반환 -> 메인 스레드 사이클 동안만 생존(plain에서 약 2분, 4 trials).
  4. start_background 호출(main.py:3422) 이후 **블로킹 keep-alive 없음** -> 백테스팅->최종예측->finally->프로세스 종료.
  5. `--24h` 게이팅은 오래된 커밋(c506336 등)부터 존재 -> **이번 81건이 만든 회귀 아님**(장기 설계).
- 결론: plain `python main.py` = **원샷 1사이클 후 종료가 설계대로의 동작**. CLAUDE.md(239 "Background optimization 무한 반복", 306)의 "무한 상주" 설명만 plain 모드와 불일치(과장).
- 선택지(택1, 사용자 결정):
  - (A) **문서 보강**(저위험): CLAUDE.md/README에 "plain=원샷 1사이클, 상주는 --24h"를 명시. 코드 무변경.
  - (B) **코드 keep-alive 추가**(동작 변경): run() 끝(finally 직전)에 dashboard/background-opt 활성 + not --24h일 때 `optimization_stop_flag` 기반 블로킹 루프를 둬 프로세스를 상주시켜 대시보드(5001) 유지 + 백그라운드 최적화 지속. 문서의 "무한 반복" 의도와 일치.

### [관찰-2] run2에서 EnsembleMonitor 히스토리 JSON 로드 실패 1건
- 근거: run2 snap2:831 "ERROR - 히스토리 로드 실패: Expecting value: line 19 column 9 (char 385)". run1엔 없음. dashboard-monitoring-3(save_history)이 쓴 JSON이 일부 손상됐을 가능성(부분쓰기/동시쓰기). 재현성 낮음 -> 모니터링 권장.

---

## D. 다음 세션 착수 권장 순서
1. **P2-1** 앙상블 차원불일치(feature_columns 저장/복원) - 가장 구체적이고 영향 명확한 코드버그.
2. **P2-2** 실시간 학습 게이트 완화 - 9개월 정체 해소.
3. **P2-3** 작업중 SIGINT 종료 - 실제 터미널에서 재확인 후 워치독/주기체크 도입 여부 결정.
4. P3 일괄(get_filtered_count/np.int32/메모리임계값/카운터·윈도우 불일치/로그순서) - 외과적 경미 수정.
5. 관찰-1(상주모드 정책) 사용자 확정.

> 검증 한계: run1은 plain 모드 1사이클(약 4분)이라 (a)LSTM seq=15 런타임 미로깅, (b)threshold 모드 최적화(pool 모드만 관찰), (c)대시보드 동적 API는 미수집. 필요 시 `--24h` 장시간 런 또는 대시보드 상호작용 런으로 보강 가능.

---

## E. 다음 세션 시작 프롬프트 (복붙용)

> 아래 블록을 다음 세션의 첫 메시지로 그대로 붙여넣으면 이어서 작업 가능.

```
로또 예측 시스템 후속 작업. 직전 세션에서 런타임 검증(실제 main.py 2회 실행 + 26에이전트 워크플로우)을
완료하고, P2-1(앙상블 사일런트 0개 = 재사용 경로 scaler 81 vs 131 차원불일치)을 수정·커밋했다.
상주모드 간극은 문서보강(A안)으로 마무리했다.

작업추적: 루트 RUNTIME_VERIFICATION_TODO.md(이 파일) + 메모리 runtime-verification-2026-06-03.md.
근거 로그(보존됨, logs/는 gitignore): logs/_verify_app_snapshot.log(run1 정상사이클),
logs/_verify_app_snapshot2.log(run2 작업중 SIGINT), logs/_verify_console_snapshot.log.

이번 세션 목표: 남은 이슈를 우선순위대로 수정.
1) [P2-2] 실시간 학습 영구정체: adaptive_update 게이트가 성능 1회 하락 후 영구 차단(마지막 실제
   업데이트 2025-09, 9개월 정체). src/ml/realtime_learning_system.py ~line220 게이트를
   "연속 스킵 N회면 강제 1회" 또는 "최근 N개 추세 비교"로 완화 + 평가실패 시 history에 0.0 미기록.
2) [P2-3] 작업중 SIGINT graceful 미발동: run2에서 백테스팅 중 Ctrl+C가 62초간 무처리->강제킬(exit1).
   먼저 실제 터미널에서 재현·확인 후, 필요시 워치독/주기적 stop_flag 체크 도입
   (Windows+ProcessPoolExecutor 신호 전달 한계 가능성 고려).
3) [P3 일괄] get_filtered_count 메서드부재, fractal 미실행(Combined 3/5), np.int32 로깅,
   메모리임계값 1500MB, 검증윈도우 300vs50, 백테스팅카운터 288vs873, 필터요약 로그순서.

규칙(필수):
- 핵심전략 절대준수: "역사적 극단패턴 제거->남은풀 다양성예측". 확률론 비판/통과율95% 강제 금지(통과율=참고지표).
- 가짜/더미 데이터 fail-fast. 추측 금지, 실제 코드/로그만 근거(파일:라인 인용).
- 외과적 변경. 수정 후 관련 단위테스트 통과 확인.
- 모든 응답 한글 + 쉬운 설명(비유) 곁들임.
- 검증 필요 시 격리 콘솔 러너로 main.py 재실행 가능(직전 세션 방식: 새 콘솔+CTRL_C_EVENT, logs/ gitignore).

부수 정리(착수 전 사용자 확인): 이전 세션 미커밋 잔여물(CODE_REVIEW_TODO.md 수정 +
untracked 새 테스트 3종/스크립트 등)을 함께 커밋할지 사용자에게 확인할 것.

먼저 P2-2부터 src/ml/realtime_learning_system.py를 읽고 게이트 로직을 진단한 뒤 수정안을 제시해줘.
울트라코드(워크플로우)로 진행해.
```
