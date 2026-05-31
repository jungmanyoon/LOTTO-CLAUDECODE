# 다음 세션 핸드오프 (2026-05-31 업데이트 2)

> 다음 세션 AI는 이 문서 + 메모리(MEMORY.md) + CLAUDE.md를 먼저 읽고 이어갈 것.

---

## 1. 사용자 최종 전략 결정 (절대 준수 — CLAUDE.md에 명시됨)

- **확률 논쟁 영구 금지**: "어차피 매 회차 1/8,145,060이라 필터/풀 축소가 무의미하다",
  "당첨확률 못 높인다", "기대값으로 상쇄된다"는 순수 확률론적 비판을 **절대 꺼내지 말 것.**
  사용자는 독립시행 1/814만을 충분히 알고, 그 위에서 "역사적 극단 배제" 전략을 의도적으로 선택함.
- **통과율 95% 제약 제거**: 통과율(당첨번호 보존율)을 강제 목표/제약으로 두지 않음.
  "출현율 낮은 패턴 최대 제거"가 우선. 통과율은 참고 지표로만 표시.
- **사용자 방법**: 역사적 극단 패턴 최대한 제거 → 남은 풀에서 다양성 예측 → 많은 번호 맞추기.

---

## 2. 이번 세션(과필터링 작업) 완료 내역 ★

핵심 통찰("과필터링")을 실측·해결. **상세: docs/EXTREMENESS_POOL_ARCHITECTURE.md**

### 발견
- **구 16필터 AND + global_probability_threshold 레버가 죽어있었음**: 임계값 0.5%→20%로
  20배 올려도 풀이 807만(전체 99.1%)에 고정 = 과소필터링(과필터링의 반대 문제).

### 해결 (Codex gpt-5.5 + Gemini 3.1-pro + Claude 만장일치)
- 16 AND 필터 폐기 → **단일 "극단성 점수" + "목표 풀 크기 K" 컷오프 1개**.
- 풀 크기 직접·단조 제어 + `1-(1-p)^16` 누적 과필터링 원천 소멸.

### 신규 파일 4개 (모두 검증 완료)
- `src/core/extremeness_scorer.py` — 마할라노비스(상관보정)+희귀패턴 페널티. 8.14M 채점 ~16s.
- `src/core/diversity_selector.py` — 빈도 가중치 + 가중 max-coverage 5장 선택.
- `src/core/pool_optimizer.py` — Optuna v6 (분리도AUC + 약한 lift_lcb, **통과율 제약 제거**).
- `src/scripts/analyze_threshold_pool_curve.py`, `generate_diverse_predictions.py`.

### 실측 결과 (정직한 데이터)
- 곡선(hold-out 150회): **K=1.5M(81.6% 제거)에서 Lift 1.27 최고** → 사용자 채택.
  분리도 AUC~0.51(미미) = 극단 특징만으론 미래 당첨 강하게 못 가림. 단 1.5M이 통계 최적점.
- **진짜 레버=5장 다양성(hold-out 100회): 3개+ 맞춘 회차 무작위 6 → 다양성 13 (2배↑).**
- Optuna v6 30 trials: best AUC=0.506, lift_lcb=1.157 → configs/extremeness_weights.json 저장.

### 1227 예측 5세트 (K=1.5M, 최적 가중치)
```
세트1: [7, 12, 14, 27, 31, 38]
세트2: [3, 15, 17, 33, 34, 36]
세트3: [4, 13, 16, 30, 37, 40]
세트4: [2, 11, 18, 32, 35, 39]
세트5: [5, 8, 20, 24, 43, 45]
```
커버 30/45번호, 티켓 간 겹침 0. (재생성: `python src/scripts/generate_diverse_predictions.py`)

---

## 3. main.py 통합 완료 ★ (이번 세션 추가)

신 아키텍처를 production main.py 본류에 연결 완료:

- **신규 어댑터** `src/core/extremeness_pool_predictor.py` `ExtremenessPoolPredictor`:
  단일 진입점. build_pool(8.14M 채점→K컷오프, **디스크 캐시 0.2s 재사용**) + predict(5장 다양성).
  ML 예측은 번호 다양성 가중치로 결합(ml_signal, CLAUDE.md 핵심전략 정합).
- **main.py:3979** 통합 블록 추가: 환경변수 `LOTTO_USE_EXTREMENESS_POOL`(기본 1=활성),
  `LOTTO_TARGET_POOL_K`(기본 1500000). **신 경로 우선, 실패 시 구 generate_final_predictions로 graceful 폴백.**
- **diversity_selector.py** `compute_weights`에 ml_signal/ml_beta 파라미터 추가(평탄 결합).
- **검증**: main.py 구문 OK, 통합블록 재현테스트 PASS(5세트/포맷호환/6번호), 회귀 272 passed
  (실패 6+에러 6은 모두 기존 - 내 파일 미임포트 확인됨).

## 4. 다음 세션 할 일 (남은 통합)

1. **diversity_selector 일원화**: 구 `src/utils/diversity_selector.py`(Hamming, main.py:1521 풀보충에서 사용 중)
   를 신 `src/core/diversity_selector.py`(가중 max-coverage)로 대체할지 결정. (현재는 신 경로가 우선이라
   구 풀보충 경로는 폴백 시에만 작동)
2. **백그라운드 최적화 교체**: 구 `threshold_optimizer.py`(v5, threshold 탐색) →
   신 `pool_optimizer.py`(v6, 가중치 탐색)로 unified_optimizer 루프 교체.
3. `python main.py` 전체 실행으로 최종 end-to-end 확인 (현재는 블록 단위까지 검증).
4. 대시보드(enhanced_dashboard_v2.py) 예측 표시도 신 경로와 정합되는지 확인.

---

## 4. 현재 시스템 상태
- 데이터: 1226 최신.
- 구 적응형 필터(use_weighted_system=False)는 그대로 (신 구조와 병존, 아직 main 연결 안 됨).
- 신 구조 산출물: configs/extremeness_weights.json, results/threshold_pool_curve.json,
  data/pool_optimization.db (Optuna 30 trials).
