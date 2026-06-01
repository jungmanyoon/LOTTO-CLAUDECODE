# 다음 세션 핸드오프 (2026-06-01 업데이트 4)

> 다음 세션 AI는 이 문서 + 메모리(MEMORY.md) + CLAUDE.md를 먼저 읽고 이어갈 것.
> 메모리 핵심: [[extremeness-pool-architecture-2026-05-31]], [[user-strategy-final-decision]],
> [[test-isolation-order-dependent-fix]], [[deep-pattern-hunt-negative-2026-06-01]],
> [[user-prefers-simple-explanations]], [[log-audit-fixes-2026-06-01]]

> **로그 진단·수정(2026-06-01)**: [[log-audit-fixes-2026-06-01]] — 필터 63분 낭비 제거(구 증분필터
> 0개제거 조기탈출 가드) + 대시보드 rate limit 상향 + 통과율 자동롤백 제거 + np.float_/status 버그.
> FilterValidator 3개·DiversitySelector 2개 = 동명 별개 클래스(통합 부적절, docstring 구분 명시).
> 보류(다음): fast-extremeness-only 기본전환(ML 필터풀 의존성 확인 필요), FilterValidator rename(13곳).

## 0. 이번 세션 요약 (2026-06-01 업데이트 4) ★최신

[작업] 휠링 검토 + 극단패턴 심층발굴 + 극단성풀 미래검증. (사용자: 모든 보고에 쉬운 설명 필수 — [[user-prefers-simple-explanations]])

- **휠링 기각**: hold-out 100회 실측 — 휠(좁은 N개 covering)은 1cover 5장에 전 구간 열위
  (avg 0.93~1.5 vs 1.81). 사용자 사용모델: 5장=동행복권 1용지 단위(제약 아님), 그때그때
  N세트 추천 → 공유자가 골라 구매. wheeling_system.py 보존(연결 안 함).
- **무작위 vs 다양성(참고)**: 20장 규모선 무작위(풀내)가 다양성 제어를 근소 우위(다양성은 5장에서만 유효).
  단 사용자 "무작위 말고 데이터 기반" 요구 → 극단 발굴로 전환.
- **★극단패턴 추가발굴 = 음성(중요)**: [[deep-pattern-hunt-negative-2026-06-01]]. 6전문가
  워크플로우(26에이전트)+적대검증. 20규칙 발굴 → 진짜 쓸 규칙 0개(다중비교/표본부족 착시,
  기존필터 중복 15/20). "역사상 0회 극단→제거" 추가발굴 **재시도 금지**.
- **★극단성풀 walk-forward 미래검증 = 견고**: 5시점(800~1150) 미래 lift 평균 1.10(범위
  0.97~1.29), 최근일수록 우위(1100→1.29). 위험한 과적합 없음 → 극단풀+5장다양성 그대로 유지.
- 신규 스크립트 5개(git 추적): evaluate_wheel_vs_cover / evaluate_selection_boost /
  analyze_extreme_patterns / analyze_deep_patterns / validate_pool_walkforward. 결과 results/*.json.
- **콜드 가중치 실측 완료**: 콜드 비중↑ 무의미/역효과(evaluate_cold_weight.py — cold_off 1.92 >
  baseline 1.86 > cold_only 1.85, 무작위 1.74). **콜드 연결 안 함 확정, 현행 0.2 유지**(사용자 결정).
  cold_off 미세 우위는 단일시드 노이즈 → 향후 다시드 확정 시 비중 하향 여지.
- [미완/선택] diversity_selector 일원화(구 utils Farthest-Point vs 신 core 1cover; 이미 '분리 유지'
  결정됨·import 경로 달라 충돌 없음 → 추가 조치 불필요. 정리하려면 구 utils docstring에 용도 명시 정도).

---

## 1. 사용자 최종 전략 결정 (절대 준수 — CLAUDE.md에 명시됨)

- **확률 논쟁 영구 금지**: "어차피 매 회차 1/8,145,060이라 무의미", "당첨확률 못 높인다",
  "기대값으로 상쇄된다"는 순수 확률론적 비판을 **절대 꺼내지 말 것.** 사용자는 독립시행
  1/814만을 충분히 알고, 그 위에서 "역사적 극단 배제" 전략을 의도적으로 선택함.
- **통과율 95% 제약 제거**: 통과율은 강제 목표가 아니라 참고 지표.
- **사용자 방법**: 역사적 극단 패턴 최대한 제거 → 남은 풀에서 다양성 예측 → 많은 번호 맞추기.
- **AI 역할**: 확률 강의 X, 사용자 방법을 정확히 구현 + 실측으로 최선을 골라내기 O.

---

## 2. 현재 시스템 상태 (2026-06-01)

- **데이터**: 1226 최신 (1227 미발표 — 동행복권 사이트도 1226).
- **테스트**: **전체 809 passed, 0 failed** (순서의존 4건 격리 완료, 3회 재현). 추적 테스트 37개.
- **최종 예측 경로**: ExtremenessPoolPredictor (극단성 풀 K=1.5M + 5장 1-cover 다양성).
  main.py:4008~, 대시보드 모두 신 경로 통합 완료. ML은 번호 다양성 가중치로 결합.
- **1227 예측 5세트** (K=1.5M): `[7,12,14,27,31,38] [3,15,17,33,34,36] [4,13,16,30,37,40]
  [2,11,18,32,35,39] [5,8,20,24,43,45]` — 커버 30/45, 티켓겹침 0. 1227 발표 시 갱신 필요.
- **git**: lotto/feature/major-system-upgrade 원격 동기화 완료(0 ahead). 최근 커밋:
  92d9208(테스트31편입) ← 6e48e67(fast모드) ← eb79f0e(순서의존격리+triple반증).

---

## 3. 완료된 작업 누적 (커밋 순)

| 커밋 | 내용 |
|------|------|
| 1ae2a7c | 극단성 풀 + 5장 다양성 아키텍처 (신규 6파일 + main 통합 + Optuna v6) |
| c244cf3 | --skip-ml/--predict-only 플래그 존중 + 버그 3건 |
| f3ba38a | 대시보드 예측을 극단성 풀 경로로 정합 |
| f3e77a7 | 회귀 테스트 4건 + gitignore 루트 앵커 |
| **eb79f0e** | **순서의존 테스트 4건 격리(809 passed) + triple-cover 시도·반증** |
| **6e48e67** | **F5 최적화: --fast-extremeness-only (구 16필터 스킵)** |
| **92d9208** | **정식 테스트 31개 git 추적 편입 (37개로 복원)** |

### 핵심 실측 결론 (정직한 음성 결과 — 반복 금지, 이미 검증됨)
- **분리도 AUC ≈ 0.51 벽**: PoolOptimizer 가중치를 어떻게 튜닝해도 AUC 0.4935~0.5099.
  "극단성 특징만으로는 미래 당첨을 분리 못함"은 독립시행상 근본 한계 (재시도 불필요).
- **triple-cover 반증**: 쌍빈도 가중 3-부분집합 커버리지(select_triple_cover)는 기존 1-cover를
  못 이김. random 8.33 / **1cover 11.33(최선)** / triple 11.0. → production은 1cover 유지.
- 즉 검증된 레버는 **"극단 최대 제거(K=1.5M, 81.6%) + 1cover 5장 다양성"** 뿐.

---

## 4. 다음 세션 후보 작업 (우선순위)

### A. wheeling_system 기반 전략 탐색 (탐색형, 사용자 결정 필요) ★
- **발견**: `src/optimization/wheeling_system.py`에 이미 "n-k-g 휠"(n개 번호로 k장 조합, g개
  보장) covering design이 구현돼 있음. Codex/Gemini가 triple-cover 대안으로 지목한 정석.
- **핵심 질문(사용자에게)**: 현재 "5장 고정" 전략을 유지할지, 아니면 "N개 번호 선택 → 휠로
  더 많은 장수로 k개 보장 커버" 전략을 허용할지. 후자는 구매 장수↑(예산↑)를 수반.
  - 5장 고정 유지 시: 휠링 적용 불가(휠은 보통 7~20장).
  - 예산 허용 시: 극단성 풀 상위 N개 번호 → 휠로 3·4개 보장 조합 생성 → hold-out 검증.
- **선행 작업**: 사용자에게 "몇 장까지 구매 가능한지(예산)" 확인 후 진행.

### B. diversity_selector 일원화 (위생, 선택)
- 구 `src/utils/diversity_selector.py`(Hamming, main.py:1521 폴백)와
  신 `src/core/diversity_selector.py`(1-cover, production) 병존 중. 충돌 없으나 혼란 소지.
  구를 폐기하거나 명확히 분리할지 결정.

### C. 백그라운드 최적화 의미 재검토 (선택)
- PoolOptimizer v6가 AUC 0.51 벽에 막혀 가중치 튜닝 이득이 거의 없음(0.519→0.525).
  백그라운드 최적화를 계속 돌릴 가치가 있는지, 아니면 다른 목적함수로 바꿀지 검토.
  (단 새 목적함수도 독립시행 한계는 동일 — 신중히)

### D. 1227 발표 시 데이터 갱신 + 5세트 재생성 (정기)
- 1227 발표되면 `python main.py`(또는 --fast-extremeness-only)로 갱신 + 신 5세트 생성.

---

## 5. 운영 명령 메모

```bash
# F5 빠른 실행(구 16필터 스킵, 권장 신규)
python main.py --fast-extremeness-only
# 또는 env: LOTTO_FAST_EXTREMENESS_ONLY=1 python main.py

# 예측만 (가장 빠름, 19초급)
python main.py --predict-only --skip-ml

# 전체 테스트 (809 passed 기준)
python -m pytest tests/ --timeout=300 --no-cov -p no:cacheprovider -q

# 극단성 풀 5세트 직접 생성
python src/scripts/generate_diverse_predictions.py --K 1500000
```

### 환경 주의사항 (이 세션에서 겪은 것)
- git-bash의 `python3`에는 optuna 없음 → **반드시 `python`** 사용.
- 무거운 작업(main/pytest)은 **백그라운드(run_in_background)** + 로그 파일 폴링. 한 응답에
  도구 과다 투입 시 배치 취소됨 → 소수씩.
- 다른 Claude 프로세스 startup cleanup이 **untracked 임시파일을 삭제**함 → 임시 산출물은
  src/scripts 등 추적 경로에 두지 말 것(평가 스크립트가 삭제됐던 사례 있음).
- 콘솔 한글 깨짐 → 로그는 python으로 키워드 grep하거나 ASCII 치환해 확인.
