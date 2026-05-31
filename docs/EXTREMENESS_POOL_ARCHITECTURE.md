# 극단성 점수 + 목표 풀 크기 아키텍처 (2026-05-31)

> 사용자 전략("역사적 극단 패턴 최대 제거 → 남은 풀에서 다양성 예측")의 신 구현.
> Codex(gpt-5.5) + Gemini(3.1-pro) + Claude 3자 교차검증 합의.

## 1. 배경: 왜 바꿨나 (구 구조의 결함)

### 구 구조 (16개 AND 필터 + global_probability_threshold)
- 각 필터가 "역사적 출현율 < threshold(%)" 카테고리를 개별 제외 → AND로 합성.
- **[실측 결함]** 임계값을 0.5% → 20%로 **20배 올려도 풀이 807만(전체 99.1%)에 고정**.
  즉 임계값 레버가 죽어 풀 크기를 제어하지 못함(과소필터링). 동시에 잘못 조이면
  `1-(1-p)^16` 누적으로 급격히 과필터링되는 계단현상 위험 공존.
- generate_dynamic_criteria가 거의 불변/비단조 (sum_range가 th와 무관하게 [120,170] 근처).

### 신 구조 (단일 극단성 점수 + 목표 풀 크기 K 컷오프)
- 모든 조합에 **단일 극단성 점수** 부여 → 가장 극단적인 것부터 제거 → **목표 풀 크기 K** 1개로 제어.
- **(1) 풀 크기가 직접·단조 제어** (2) **AND 누적 과필터링 원천 소멸** (컷오프 1개)
  (3) "극단 최대 제거"가 K로 직관적 표현.

## 2. 컴포넌트

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `src/core/extremeness_scorer.py` | `ExtremenessScorer` | 극단성 점수(마할라노비스+희귀패턴 페널티), 8.14M 채점 ~16s |
| `src/core/diversity_selector.py` | `FrequencyAnalyzer`, `DiversitySelector` | 번호 빈도/최근성 가중치 + 가중 max-coverage 5장 선택 |
| `src/core/pool_optimizer.py` | `PoolOptimizer` | Optuna로 점수 가중치 최적화 (분리도 AUC + 약한 lift LCB) |
| `src/scripts/analyze_threshold_pool_curve.py` | - | "K → 풀크기/hold-out 커버리지" 곡선 + knee 탐지 |
| `src/scripts/generate_diverse_predictions.py` | - | end-to-end 파이프라인 + 다양성 vs 무작위 평가 |

### 극단성 점수 공식
```
score(x) = d2_mahalanobis(x) + Σ_k w_k * penalty_k(x)
  d2          = (x-μ)^T Σ^-1 (x-μ)        # 연속 9특징, 상관 자동보정(중복가중 방지)
  penalty_k   = -log((count_k+α)/(N+α·bins))  # 이산 희귀 극단(최장연속/동일끝자리/구간몰림 등)
```
- 연속 특징(9): sum, std, max_gap, range, odd_count, low_count, ac_value, prime_count, distinct_last_digits
  (average는 sum과 완전상관 → 제외하여 특이행렬 방지)
- 페널티 차원(4): max_consecutive, odd_count, max_same_last_digit, max_section_occupancy
- 높은 점수 = 극단 = 우선 제거. `cutoff_for_size(scores, K)`로 K번째 점수 = 컷오프.

## 3. 실측 곡선 (학습 1~1076 / hold-out 최근 150회)

| 목표풀 K | 제거율 | hold-out 당첨커버 | Lift(무작위 대비) |
|---|---|---|---|
| 300K | 96.3% | 2.7% | 0.72 |
| 1.0M | 87.7% | 13.3% | 1.09 |
| **1.5M** | **81.6%** | 23.3% | **1.27 (최대)** |
| 2.0M | 75.4% | 26.0% | 1.06 |
| 6.0M | 26.3% | 74.0% | 1.00 |

- **knee(Kneedle) = K=1.5M** (lift 최고점). 사용자 채택값.
- **정직한 한계**: 극단성 점수의 분리도 AUC ≈ 0.51 (무작위 0.5 대비 미미). 즉 "역사적 극단"
  특징만으로는 미래 당첨을 강하게 가려내지 못함. **단 K=1.5M에서 Lift 1.27** = "최대 제거 +
  통계적 최적"이 동시 만족하는 지점이 데이터로 존재.

## 4. 진짜 레버: 5장 다양성 (검증됨)

hold-out 100회 실측 (동일 K=1.5M 풀에서):

| | 평균 best-match | **3개+ 맞춘 회차** | 분포 [1·2·3·4개] |
|---|---|---|---|
| **다양성 5장 (가중 max-coverage)** | **1.830** | **13/100** | [30, 57, **13**, 0] |
| 무작위 5장 | 1.620 | 6/100 | [43, 50, 5, 1] |

- **다양성 커버리지 극대화가 "3개+ 맞추기"를 6→13회로 2배 이상 향상.**
  사용자 전략("많은 번호 맞추기, 하위 등수 포함")의 핵심 레버는 풀 축소가 아니라 **5장 다양성**.
- 알고리즘: 가중 max-coverage 그리디(63% 보장) + 로컬서치.
  제약: 5장 unique 27~30번호, 티켓 간 겹침 ≤1, 번호 반복 ≤2.

## 5. Optuna 재설계 (v6, 통과율 제약 제거)

- **구 v5**: global_probability_threshold 탐색 + 통과율 95% 제약 → 사용자 결정으로 폐기.
- **신 v6 (`PoolOptimizer`)**: K는 컷오프로 고정. Optuna는 점수 가중치(feature scale + 페널티)를
  탐색하여 다음을 최대화:
  ```
  score = AUC_separation + λ_lift·log(lift_lcb) - λ_reg·weight_complexity
  ```
  - AUC_separation: 과거당첨 vs 무작위 분리도(표본 큼, 강건한 주신호)
  - lift_lcb: hold-out lift의 로그 K-fold 하한 (약한 보조항, 노이즈 추종 방지 — Codex/Gemini 합의)
  - 통과율(winning_inclusion) **제약 완전 제거** (사용자 결정).

## 6. 사용법
```bash
# 곡선 분석 (최적 K 탐색)
python src/scripts/analyze_threshold_pool_curve.py --holdout 150

# 5세트 생성 (K=1.5M)
python src/scripts/generate_diverse_predictions.py --K 1500000

# 다양성 vs 무작위 검증
python src/scripts/generate_diverse_predictions.py --evaluate --holdout 100

# 가중치 최적화 (Optuna)
# PoolOptimizer(db, target_K=1_500_000).optimize(n_trials=30) → configs/extremeness_weights.json
```

## 7. 남은 통합 작업 (다음 세션)
- main.py `generate_final_predictions_enhanced`에 신 파이프라인 연결 (현재는 standalone 스크립트).
- `configs/extremeness_weights.json` 로드하여 ExtremenessScorer 가중치 적용.
- 기존 `src/utils/diversity_selector.py`(Hamming 기반)와 신 `src/core/diversity_selector.py`
  (가중 max-coverage, 검증상 우수) 통합/대체 결정.
