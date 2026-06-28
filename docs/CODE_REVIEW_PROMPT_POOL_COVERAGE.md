# 3차 코드리뷰 프롬프트 — "극단성 풀 커버리지" 진단·개선 (다음 세션 실행용)

> 작성: 2026-06-27 (1230회 당첨조합 풀 탈락 발견 계기). 다음 세션이 이 파일 하나만 읽어도 자족적으로 실행되도록 작성.
> effort: high 이상 + 워크플로우(다중에이전트 병렬 + 발견별 독립 적대검증 + walk-forward 누설0) 권장.

---

## 0. 계기와 즉석 확인 사실 (반드시 재검증부터)

- **표시 신호**: 제1230회 당첨번호 `3, 8, 9, 22, 28, 42 (+보너스 45)`. 대시보드 `평균 일치 0.42 / 최고 일치 1 / 3개+ 적중 0`.
- **이번 세션 즉석 확인(다음 세션이 먼저 재검증할 것)**: 1230회 예측에 쓰인 **1229 풀**(`cache/extremeness_pool_mahalanobis_1229_1500000_w*.npz`, K=1.5M)에 당첨조합 `(3,8,9,22,28,42)`가 **생존하지 못함(제거됨)**. 즉 "최고일치 1"은 하류 증상이고, **상류 사실은 "당첨조합이 극단성 풀에서 탈락"**이다.
  - 재검증 방법: 해당 npz의 `combos`(정렬된 (M,6) int)에서 `(3,8,9,22,28,42)` 행 존재 여부 멤버십 검사. dtype/정렬 함정 주의(저장은 오름차순). 1230 풀(1231 예측용)에서도 동일 확인.

---

## 1. 이 리뷰가 반드시 지켜야 할 평가 프레임 (위반 금지 — CLAUDE.md ABSOLUTE 정합)

이 시스템은 "다음 당첨번호를 맞추는" 시스템이 **아니다**. "역사상 출현율이 극히 낮은 극단 패턴을 제거하고, 같은 예산으로 더 그럴듯한 영역을 커버"하는 전략이다(사용자 최종 확정).

- **[금지 1] 단일 회차 avg_matches / 최고일치를 최적화 목표로 삼지 말 것.** 5세트로 8.14M을 커버할 수 없어 한 회차 max-match=1은 무작위에서도 매우 흔하다(5세트 중 2개 이상 맞은 티켓이 하나도 없을 확률 ~37%). 단일 회차는 통계적 노이즈이며, 이를 쫓는 튜닝은 데이터 준설(과적합)이다.
- **[금지 2] "어차피 1/8,145,060" 확률론 강의·논쟁 영구 금지**(CLAUDE.md ABSOLUTE). 전략의 정당성을 확률로 비판하지 말 것. ML 제거·필터 폐기·더미/랜덤 폴백 제안 금지.
- **[필수 평가지표 = 이 시스템의 1차 지표]**
  1. **통과율/커버리지**: "실제 당첨조합이 극단성 풀에 생존하는 walk-forward 비율." (1230은 이 비율의 한 표본이며 '탈락'으로 관측됨)
  2. "무작위 대비 당첨번호를 포함하는 조합의 선택 비율(lift)."
- **개선의 정의**: "같은 예산으로 더 좁고 정확한 풀" = **당첨 가능 영역을 잘못 버리지 않으면서** 극단을 제거. 따라서 핵심 질문은 *"풀이 winnable 영역을 과도하게 제거하고 있는가(캘리브레이션/버그), 아니면 사용자가 수용한 트레이드오프가 한 회차에 정상 분산으로 나타난 것인가"*이다.

---

## 2. 제품 핵심 경로 (1차/2차 리뷰에서 확정 — 이 경로만이 사용자 산출물)

- 최종 5세트: `main.py:~4021` `ExtremenessPoolPredictor(db)` → `build_pool()` → `predict(num_sets=5)`.
- 풀 '선택' = 마할라노비스 `src/core/extremeness_scorer.py`(ExtremenessScorer), 기본 `scoring_method='hybrid'`(sel_method='mahalanobis', tail은 설명 전용·예측 불변).
- 5세트 선택기 = `src/core/diversity_selector.py`(DiversitySelector.select). K SSOT = `configs/extremeness_pool_policy.json` `effective_target_K`(현재 1,500,000 = 8.14M의 약 18.4%만 keep).
- K 재탐색 = `src/core/extremeness_threshold_selector.py`. 가중치 = `configs/extremeness_weights.json`(백그라운드 PoolOptimizer 산물, build_pool wver에 mtime 반영).

---

## 3. 조사 축 (영향 큰 순)

### 축 1 — 측정 무결성 (먼저)
- 대시보드 `0.42 / 최고1 / 3+0`이 **올바른 회차(1230)·올바른 5세트·올바른 계산**인지. 표시 버그/회차 어긋남/보너스 처리/누설 없는지(`enhanced_dashboard_v2.py`, `rank_calculator.py`, `predictions.db`).
- 표시된 5세트가 실제 본류(ExtremenessPoolPredictor) 산출물인지, 레거시 폴백(`generate_final_predictions_enhanced`)·`src/utils/diversity_selector.py` 폴백이 아닌지. (2차 리뷰: unified_optimizer 사이클 print가 레거시 5세트를 보였던 전례 있음)

### 축 2 — 커버리지(★핵심 1차 지표)
- **walk-forward coverage 측정도구 신규 작성**(`src/scripts/`): 최근 N회(예: 50~100)에 대해 각 회차 r마다 `train_until=r-1`로 풀(K=1.5M) 빌드 → r회 **실제 당첨조합이 풀에 생존하는지** 집계 → **coverage 비율** 산출. **누설 0 필수**(r-1까지만 학습, 캐시 회차키 정확).
- 해석 기준: 무작위 기대 생존율 = keep 비율 = **18.4%**. coverage가
  - 80%+ → 풀이 winnable 영역을 잘 보존(정상). 1230은 그 안의 한 표본 miss.
  - 18% 근처 → 풀이 무작위 수준 = **체계적 결함**(스코어러가 winnable을 못 구분).
  - 그 사이 → 과제거 정도를 정량화하고 K/스코어러로 개선 여지 판단.
- 1230 탈락이 "정상 분산 내 한 표본"인지 "체계적 과제거"인지 walk-forward 분포로 단정.

### 축 3 — 왜 1230 당첨조합이 제거됐나 (점수 분해)
- `(3,8,9,22,28,42)`의 extremeness score를 `score_components()`로 분해: `mahalanobis2` + 각 penalty_dim(`max_consecutive`/`odd_count`/`max_same_last_digit`/`max_section_occupancy`) 기여. **어느 성분이 cutoff를 넘겼나**.
  - 직관 후보: 3,8,9 저번호 군집(low_count↑) + 8,9 연속 + 구간(1~10)에 3개 몰림(max_section_occupancy) + 42까지 큰 range. 이 중 무엇이 결정적인지 수치로.
- 그 제거가 **역사적으로 정당**한가(해당 패턴 실제 출현율 극히 낮음 = 전략상 올바른 제거) vs **스코어러 miscalibration**(공분산 추정/`_feature_scale` 스케일/weights 드리프트로 부당 과제거)인가.
- `configs/extremeness_weights.json`(백그라운드 최적화 산물) 드리프트가 과제거를 유발했는지: 가중 마할라(`cov_inv = S @ cov_inv @ S`) 적용 후 winnable이 밀려나는지. weights를 균등(미적용)으로 돌렸을 때 1230이 생존하는지 A/B.

### 축 4 — 풀 강도/캘리브레이션
- `effective_target_K=1,500,000`이 실제로 keep 18.4%인지, 의도와 일치하는지. **K가 너무 작아 winnable을 버리는지**(K↑가 coverage↑ 트레이드오프 — walk-forward로 K 곡선 그려 coverage vs K, lift vs K 동시 관찰).
- `cutoff_for_size`/`select_pool`가 정확히 K개인지(동점 처리), build_pool 코드 mtime 캐시무효화로 stale 풀 안 쓰는지(2차 리뷰에서 정합 확인됨, 재확인만).

### 축 5 — 5세트 선택 (설계목표 = 풀 커버리지, 단일매칭 아님)
- DiversitySelector가 풀에서 5장을 '번호 커버리지 극대화'로 뽑는데, **당첨번호 영역을 체계적으로 놓치는 편향**이 있는지. `FrequencyAnalyzer.compute_weights`의 freq/recency/ml 결합(`ml_beta`)이 저빈도 저번호(3,8,9류)를 과소가중해 선택에서 배제하는지.
- 단, 5장 max-match는 평가지표가 **아니다**. "풀 커버리지/직교성(겹침<=1)/번호 분산"이 설계대로인지만 본다. (2차 리뷰: 선택 단계는 walk-forward A/B에서 이미 1-cover 최적으로 확인된 바 있음 — 재논쟁 말고 버그만)

### 축 6 — 버그/누설/정직성
- 예측 파이프라인 stale weights/회차/캐시 재사용, ML 신호가 선택을 저하시키는지, 측정 누설(미래 회차 유입) 0. 새 회차(1230) 유입 시 풀/정책/가중치가 제대로 갱신·무효화됐는지.

---

## 4. 방법 (엄격히)

1. 발견마다 실제 파일을 Read/Grep으로 직접 읽고 file:line + 스니펫 근거. 추측 금지.
2. **walk-forward는 누설 0**(train_until=r-1만 사용). 측정도구는 `src/scripts/`에 신규 작성, 결과는 `results/`.
3. 발견마다 적대적 반증 먼저: 측정 아티팩트인가? 정상 분산인가? 다중비교 착시인가? 제품핵심(풀 커버리지)에 실제로 닿는가? 반증 실패한 것만 confirmed.
4. 코드 변경은 외과적 최소. 회귀는 `python -m pytest tests/ --timeout=300 --no-cov -q`(현재 통과 기준 확인). 큰 재설계는 "구조제안:"으로 분리하고 walk-forward 증거 동반.
5. 다중 렌즈 교차검증(coverage / 누설 / 캘리브레이션 / 정직성). 가능하면 Codex(gpt-5.5)+Gemini(3.1-pro)로 핵심 결론 적대검증.

## 5. 금지 (재강조)
- 단일 회차 매칭 최적화 / "1/8,145,060" 확률 강의 / 필터·ML 폐기 / 더미·랜덤 폴백 / 통과율 95% 하드제약 부활(참고지표로만).

## 6. 산출 형식
- **A. 측정 무결성**: 대시보드 0.42/최고1/3+0이 올바른 회차·5세트·계산인가(버그 유무).
- **B. walk-forward 커버리지**: 최근 N회 coverage 비율 + 무작위(18.4%) 대비 + K 곡선(coverage/lift vs K). **1230 탈락이 정상 분산인가 체계적 과제거인가 단정.**
- **C. 1230 점수 분해**: 어느 특징/penalty가 제거를 유발했나 + 역사적 정당성 vs miscalibration.
- **D. 결함 여부 단정 + 외과적 개선안**: 결함이면(과제거/캘리브레이션/버그) before→after·리스크·검증법. 정상 트레이드오프면 그 근거(coverage가 충분히 높다 등).
- **E. 회귀**: 변경 시 테스트 결과.

## 7. 참고 (이전 세션 메모리 — 중복 작업 방지)
- 1차/2차 코드리뷰: 제품핵심(극단풀→K→5세트) 계산·저장·로직 결함 0 확정. 선택 단계는 walk-forward A/B로 1-cover 최적 확인(겹침<=1 포화). 신규 필터 후보 탐색은 음성(데이터 준설)으로 반복 기각됨 → **개선 레버는 "필터 추가"가 아니라 "풀 커버리지/캘리브레이션(K·스코어러·weights)"과 "측정 정직성"에 있을 가능성**.
- 따라서 이 리뷰의 1순위 가설: **(a) 측정/표시 버그**, 또는 **(b) 풀이 winnable 영역을 과제거(스코어러/weights/K 캘리브레이션)** — 둘 중 무엇인지 walk-forward로 가른다. (c) 둘 다 아니면 "사용자가 수용한 트레이드오프의 정상 분산"임을 데이터로 단정.
