# 3차 코드리뷰 결과 — 극단성 풀 커버리지 (1230 탈락 진단)

> 실행: 2026-06-28. 입력 프롬프트: `docs/CODE_REVIEW_PROMPT_POOL_COVERAGE.md`.
> 방법: 5축 워크플로우(31에이전트, 발견별 적대검증) + 오케스트레이터 직접 측정 4건 + Codex(gpt-5.5) 적대 교차검증.
> Gemini(3.1-pro)는 호출 실패(CLI 인증 `IneligibleTierError`, 무료 티어 지원 종료 — 프롬프트 문제 아님).

## 한 줄 결론
1230 당첨조합 탈락은 **버그가 아니라 정상 분산**이다. 풀의 당첨조합 커버리지는 exact-combo 지표에서 무작위와 통계적으로 구분되지 않고(전 K구간 lift_lcb<1), Codex가 지적한 *올바른* end-to-end 부분일치 지표로 새로 측정해도 무작위풀을 견고하게 못 이긴다. **제품핵심 결함 0**, 유일 실결함은 성능과 무관한 측정 정직성 갭 1건(P2, 수정 완료).

---

## A. 측정 무결성 — 정상 (버그 없음)
대시보드 `평균 0.42 / 최고 1 / 3+ 0`은 회차 1230 본류 풀 50세트 라이브 집계로 **정확·정직**.
- `enhanced_dashboard_v2.py:2024-2044` renderInsights가 `data/predictions/predictions.db` round=1230 50건을 당첨번호 `[3,8,9,22,28,42]`(보너스45)와 set 교집합 집계 → avg=0.42/max=1/3plus=0/분포{0:29,1:21}로 비트수준 일치.
- 50건 전원 `ExtremePool-Diversity(K=1500K)` = 본류 `ExtremenessPoolPredictor.predict()`(폴백 0건). DB 저장=읽기 경로 일치. 보너스/등수/누설 모두 사후 표시 구조.
- (P3 수정 완료) hero mini "평균 일치"가 분모=50세트임을 미표기 → "평균 일치 (N세트)"로 보강.

## B. walk-forward 커버리지 — 누설0 정상, 신호 음성(포화)
누설0 도구는 **이미 존재**(`extremeness_threshold_selector.py:evaluate_threshold_curve`, fold마다 train=직전회차까지만 refit). K곡선(`results/extremeness_threshold_curve_1230.json`):

| K | coverage | 무작위(pool_ratio) | lift | lift_lcb |
|---|---|---|---|---|
| 1.0M | 0.129 | 0.123 | 1.05 | 0.873 |
| **1.5M(운영)** | 0.196 | 0.184 | 1.064 | 0.919 |
| 2.5M | 0.324 | 0.307 | 1.056 | 0.950 |
| 6.0M | 0.752 | 0.737 | 1.021 | 0.977 |

전 그리드(200K~6M) 모든 K에서 `lift_lcb<1.0`, `coverage≈pool_ratio`. 독립 2차 도구(`validate_pool_walkforward.py`)도 동일(lift 평균 1.105, lcb<1). AUC~0.51.

→ **1230 탈락 = 정상 분산(단정).** 정상인 이유는 "lift_lcb<1"이 아니라 **정책이 82%를 버리므로 단일회차 탈락확률 ≈80%가 당연**(Codex 보정 수용).

## C. 1230 점수 분해 — 데이터 본질, miscalibration 아님
생산 가중 scorer(fit≤1229): total **36.43 > cutoff 29.60** → 제거(percentile 32.8%). 무가중도 **11.01 > 8.74** → 제거(39.0%).
- 지배 성분 = **마할라노비스²**(연속특징), 이산 페널티 미미.
- 가중·무가중 모두 제거 → **가중치는 제거 원인 아님**. 원인은 3,8,9 저번호 군집이 만든 중간 마할라거리 + 18% 풀이 도달 못함. 미스캘리브레이션 아닌 약신호(AUC 0.51) 풀의 정상 동작.

## D. 결함 단정 + 개선안
### 제품핵심(극단풀→K→diversity_selector 5세트): 결함 0
누설0·산식정확·NO FAKE DATA·캐시 무효화 정상·선택기 겹침≤1 가드 정상. 적대검증 23건 중 22건 "정상/무편향 trade-off" 기각.

### 신규 측정 2건
- **가중 vs 무가중 집계 A/B** (`results/weighted_pool_walkforward.json`): K=1.5M 가중 lift_lcb 0.973 vs 무가중 0.919(둘 다 <1), K별 부호 반전 → **PoolOptimizer weights.json은 walk-forward 커버리지 no-op**.
- **★end-to-end 부분일치 A/B** (Codex 권고, `results/endtoend_partialmatch_walkforward.json`, 극단풀+selector vs 매칭 무작위풀+동일 selector, 6 fold×8 seed): any_2plus 순진 z=+2.34지만 **독립단위 paired t=1.89<2.04 비유의**(5장이 fold,seed마다 고정→holdout 강상관, 1080/2240 독립가정은 z 과대), any_3plus t=−0.41(상금티어 오히려 음), 6중 2 fold 음수. → **올바른 end-to-end 지표로도 풀은 무작위풀 못 이김 = 포화 결론 강화.** 약방향성(any_2plus +2~3%p)은 전략직관과 일치하나 비견고.

### 유일 실결함 (P2, 보조계층, 성능 무영향) — **수정 완료**
**K곡선/생산 scorer 정직성 갭**: 곡선은 무가중 scorer로 측정했는데 생산 build_pool은 가중 scorer로 풀을 형성 → 정책이 '다른 풀'의 커버리지로 K 선택.
- **수정**: `evaluate_threshold_curve`를 생산과 동일 가중 scorer로 통일(`_load_curve_weights`/`_make_curve_scorer`, measure what you ship) + 정책/곡선에 `scorer` 라벨 명시. 정책 재생성: K=1.5M 불변(evidence=weak), `scorer=weighted`, metrics=가중값(coverage 0.201, lift_lcb 0.946).
- K 불변이므로 생산 풀/5세트 변화 0. 가치는 정합성/정직성(성능 0 개선).

### 개선 레버 우선순위
1. (완료) 측정 정직성.
2. 커버리지/캘리브레이션은 포화 — K·스코어러·weights 전부 walk-forward 무작위 대비 유의 이득 없음(2개 독립 도구 + end-to-end A/B). 신규 필터/스코어 후보 탐색 비권장(과거 다중비교 음성).
3. 실효 레버는 5장 직교성/휠링(장수↑)이나 제약 외.

## E. 회귀
제품 소스(build_pool/predict/diversity_selector) 0 변경. P2는 측정 도구(evaluate_threshold_curve)·정책 메타 한정, 단위 테스트는 합성 곡선 주입이라 무영향. 전체 `pytest tests/ --timeout=300 --no-cov -q` 통과 유지(833 기준).

---

## 우선순위 요약
- **P2-1 (수정 완료)**: K곡선 무가중 vs 생산 가중 정직성 갭 → 가중 통일 + scorer 라벨.
- **P3-1 (수정 완료)**: 대시보드 hero mini "평균 일치 (N세트)" 라벨.
- **P0/P1: 없음.**

## 전체 건강도
- 제품핵심(극단풀→K→5세트): **정직·정확·견고 (결함 0)**.
- 보조/표시계층: 대체로 정직, 정직성 갭 1건 수정으로 해소.

## 산출물 (모두 추가/측정 도구 — 제품핵심 로직 불변)
- `src/scripts/validate_endtoend_partialmatch_walkforward.py` (신규, Codex 권고 end-to-end A/B)
- `src/scripts/validate_weighted_pool_walkforward.py` (신규, 가중/무가중 집계 A/B)
- `src/core/extremeness_threshold_selector.py` (P2: 곡선 가중 통일 + scorer 라벨)
- `src/scripts/enhanced_dashboard_v2.py` (P3: hero mini 라벨)
- `configs/extremeness_pool_policy.json`, `results/extremeness_threshold_curve_1230.json` (가중으로 재생성)
- `results/weighted_pool_walkforward.json`, `results/endtoend_partialmatch_walkforward.json` (측정 결과)
