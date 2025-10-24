# 4단계: ML/AI 모델 검증 보고서

**작성일**: 2025-10-09
**분석 대상**: 로또 예측 시스템 ML/AI 모델
**Persona**: Analyzer + QA
**품질 점수**: 7.2/10

---

## 📋 목차

1. [검증 개요](#검증-개요)
2. [모델 인벤토리](#모델-인벤토리)
3. [핵심 모델 분석](#핵심-모델-분석)
4. [ML-필터 통합 문제](#ml-필터-통합-문제)
5. [모델 캐싱 시스템](#모델-캐싱-시스템)
6. [성능 추적](#성능-추적)
7. [백테스팅 검증](#백테스팅-검증)
8. [모델 버전 및 기술 부채](#모델-버전-및-기술-부채)
9. [TensorFlow/Keras 설정](#tensorflowkeras-설정)
10. [품질 평가](#품질-평가)
11. [주요 발견 사항](#주요-발견-사항)
12. [권장 사항](#권장-사항)

---

## 🎯 검증 개요

### 검증 목적
ML/AI 모델의 아키텍처, 성능, 통합 품질 검증 및 개선 기회 식별

### 검증 범위
- ✅ 5개 핵심 모델 (LSTM, Ensemble, Monte Carlo, Bayesian, Fractal)
- ✅ 9개 실험적/폐기 버전
- ✅ ML-필터 통합 (8.5% inclusion rate)
- ✅ 모델 캐싱 시스템 (1.7GB+)
- ✅ 백테스팅 프레임워크
- ✅ 성능 추적 시스템

### 주요 발견
- 🚨 **ENSEMBLE 모델 오버피팅 의심** (평균 일치: 2.08, 목표: 0.8-1.5)
- 🚨 **ML-필터 통합 실패** (8.5% vs 15% 목표)
- 🚨 **버전 증식 위기** (5개 ensemble 버전, 불안정한 primary)

---

## 📊 모델 인벤토리

### 프로덕션 모델 (5개 활성)

| 모델 | 위치 | 크기 | 아키텍처 | 상태 |
|-----|------|------|---------|------|
| **LSTM** | `src/ml/lstm_predictor.py` | 664 lines | 3-layer (128→64→32) + Dropout + BatchNorm | ✅ Production |
| **Ensemble** | `src/ml/ensemble_predictor.py` | 1,079 lines | RF + XGBoost + NN with MultiOutputClassifier | ✅ Production |
| **Monte Carlo** | `src/probabilistic/monte_carlo_simulator.py` | 972 lines | 6,000 simulations, 8 workers | ✅ Production |
| **Bayesian** | `src/probabilistic/bayesian_inference.py` | 200+ lines | Dirichlet priors, Beta distributions | ✅ Production |
| **Fractal** | `src/advanced/fractal_pattern_analyzer.py` | 200+ lines | Box-counting, Higuchi, wavelet | ✅ Production |

### 폐기/실험 버전 (9개 파일)

**Critical 발견**: 버전 증식은 기술 부채 신호

| 파일 | 크기 | 목적 | 상태 |
|-----|------|------|------|
| `ensemble_predictor.py` | 47,962 bytes | **PRIMARY** | ✅ Active |
| `ensemble_predictor_fixed.py` | 11,510 bytes | 버그 수정 | ⚠️ Fallback |
| `improved_ensemble_predictor.py` | 45,881 bytes | 개선 버전 | ❌ Experimental |
| `super_ensemble.py` | 14,119 bytes | Meta-ensemble | ❌ Experimental |
| `filtered_pool_ensemble_predictor.py` | 24,894 bytes | 필터 통합 | ❌ Experimental |
| `filtered_pool_lstm_predictor.py` | - | 필터 인식 LSTM | ❌ Experimental |
| `constrained_predictor.py` | - | 제약 조건 | ❌ Experimental |
| `advanced_models.py` | - | 고급 모델 | ❌ Experimental |
| `human_intuition_system.py` | - | 직관 시스템 | ❌ Experimental |

**분석**: Main.py는 `ensemble_predictor.py` (primary)를 import하며, 오류 시 `ensemble_predictor_fixed.py`로 fallback. 이는 primary 구현의 불안정성을 나타냄.

---

## 🧠 핵심 모델 분석

### LSTM Predictor (시계열 예측)

**아키텍처 품질**: ⭐⭐⭐⭐ (8/10)

**구조**:
```python
Sequential([
    LSTM(128, return_sequences=True) + Dropout(0.2) + BatchNorm,
    LSTM(64, return_sequences=True) + Dropout(0.2) + BatchNorm,
    LSTM(32) + Dropout(0.2) + BatchNorm,
    Dense(45, activation='sigmoid')  # 출력: 1-45 각 번호의 확률
])
```

**강점**:
- ✅ 적절한 정규화 (Dropout 0.2, L2 penalty)
- ✅ BatchNormalization으로 내부 공변량 이동 방지
- ✅ 시퀀스 길이: 50회차 (시간적 학습에 적합)
- ✅ Early stopping, ReduceLROnPlateau, ModelCheckpoint 콜백
- ✅ 조용한 TensorFlow 로깅 (깨끗한 콘솔 출력)

**약점**:
- ❌ **불충분한 학습 데이터**: 1,192 회차 → 50회차 시퀀스 후 ~1,142 학습 샘플
- ❌ **소규모 데이터셋 위험**: 모델이 일반화 가능한 특징 학습보다 패턴 암기 가능
- ❌ **검증 분할**: 20% 분할 → 228 검증 샘플만
- ❌ **특징 표현**: One-hot 인코딩 (45차원 벡터)은 단순함; 시간적 특징 부족

**학습 파라미터**:
- Epochs: 50 (기본값), batch_size: 64
- Optimizer: Adam (learning_rate=0.001)
- Loss: binary_crossentropy (다중 레이블 예측에 적합)

**오버피팅 위험**: **높음** - 깊은 LSTM 모델에 비해 소규모 데이터셋 (1,192 회차)

---

### Ensemble Predictor (RF + XGBoost + NN)

**아키텍처 품질**: ⭐⭐⭐⭐ (8/10)

**구성 요소 모델**:

1. **Random Forest**: 50 estimators, max_depth=3, min_samples_split=30
   - **과적합 방지 조치**: 매우 얕은 트리, 높은 min_samples 제약
   - MultiOutputClassifier 래퍼 (45개 이진 출력)

2. **XGBoost**: 50 estimators, max_depth=2, learning_rate=0.01
   - **공격적 정규화**: L1=2.0, L2=3.0, subsample=0.5
   - 극도로 얕은 트리 (depth=2)

3. **Neural Network**: MLPClassifier (32→16 hidden layers)
   - alpha=0.5 (매우 강한 L2 정규화)
   - Early stopping 활성화
   - 적응형 학습률

**특징 엔지니어링**:
```python
추출 특징 (회차당):
- 기본 통계: mean, std, min, max, range, sum
- 홀짝 비율
- 구간 분포 (5개 구간)
- 연속 번호 비율
- 간격 통계
- 소수 비율
- 시간적 특징: 빈도 윈도우 (5, 10, 20 회차)
```

**강점**:
- ✅ 풍부한 특징 추출 (20+ 특징)
- ✅ 모든 모델에 강한 정규화
- ✅ 데이터 증강 지원 (현재 과적합 방지를 위해 비활성화)
- ✅ 적절한 스케일러 상태 관리 (StandardScaler, 특징만)
- ✅ 해시 기반 버전 관리를 통한 모델 캐싱

**약점**:
- ❌ **클래스 불균형 처리**: 개별 이진 분류기로 fallback은 다중 출력 학습 어려움 나타냄
- ❌ **특징 폭발**: 시간적 빈도 특징 (45개 번호 × 3 윈도우 = 135 특징)이 차원의 저주 유발 가능
- ❌ **신뢰도 부풀림**: 예측이 30%로 제한되지만 앙상블 부스트로 종종 부풀려짐
- ❌ **학습 데이터 증강 비활성화**: 시스템이 증강으로 인한 과적합 위험 인식

**앙상블 가중치**: RF (30%), XGBoost (40%), NN (30%)

---

### Monte Carlo Simulator

**아키텍처 품질**: ⭐⭐⭐⭐⭐ (9/10)

**성능**: 탁월한 최적화 작업

**시뮬레이션 파라미터** (동적):
```python
- CPU 기반 스케일링: min(10,000, max(5,000, cpu_count * 1,000))
- 현재 시스템: 6,000 시뮬레이션 (10,000에서 최적화)
- 병렬 워커: 8개
- 배치 크기: 워커당 750개
- 조기 종료: 수렴 감지 (std < mean의 1%)
```

**최적화 기법**:
1. **벡터화된 배치 처리**: 루프 대신 NumPy 배열 연산
2. **조기 종료**: 상위 조합 수렴 시 중단
3. **결과 캐싱**: 해시 기반 메모이제이션
4. **확률 행렬**: 패턴/시간적 요인에 맞게 사전 계산 및 조정

**점수 시스템**:
- 개별 번호 확률 (100x 가중치)
- 패턴 보너스: 홀짝 균형, 합계 범위 (100-180)
- 연속 번호 패널티 (쌍당 -5)
- 역사적 유사성 보너스 (3-4 일치 이상적)

**강점**:
- ✅ 최고 수준의 성능 최적화
- ✅ 현실적인 신뢰도 점수 (30-100% 범위)
- ✅ 하드웨어 기반 적응형 시뮬레이션 크기 조정
- ✅ 포괄적인 패턴 분석

**약점**:
- ❌ **근본적 한계**: 무작위 샘플링은 결정론적 혼돈을 예측할 수 없음
- ❌ **패턴 과의존**: 역사적 패턴 지속성 가정이 결함 있을 수 있음

---

### Bayesian Inference

**아키텍처 품질**: ⭐⭐⭐ (7/10)

**구성 요소**:
- Dirichlet 사전 분포 (번호 빈도)
- Beta 분포 (패턴 확률)
- 정규 분포 (상관관계)
- 마르코프 체인 전이 행렬

**강점**:
- ✅ 수학적으로 엄밀한 확률론적 프레임워크
- ✅ 적절한 사전 분포 초기화 (경험적 vs. 균등)
- ✅ 증거 축적을 통한 베이지안 업데이트

**약점**:
- ❌ **제한된 통합**: 주 예측 흐름에 깊이 통합되지 않음
- ❌ **계산 비용**: 완전 베이지안 추론은 비쌈
- ❌ **희소 데이터**: 1,192 샘플은 강건한 사후 분포 추정에 불충분

---

### Fractal Pattern Analyzer

**아키텍처 품질**: ⭐⭐⭐ (6/10)

**분석 방법**:
- Box-counting 차원
- Higuchi 프랙탈 차원
- 웨이블릿 변환 (db4, 5-level decomposition)
- Lyapunov 지수 (혼돈 감지)
- 다중 스케일 자기 유사성 (10, 50, 100, 200)

**강점**:
- ✅ 고급 카오스 이론 적용
- ✅ 다중 스케일 분석
- ✅ PyWavelets 통합 (사용 가능 시)

**약점**:
- ❌ **의문스러운 적용 가능성**: 로또 추첨은 연속적 혼돈 시스템이 아닌 이산적 무작위 이벤트
- ❌ **과적합 위험**: 노이즈에서 패턴 찾기
- ❌ **성능 영향**: 계산 비용 높음, 기본적으로 비활성화
- ❌ **실험적 상태**: 로또 예측에 대해 검증되지 않음

---

## 🔗 ML-필터 통합 문제

### 핵심 이슈

**문제 진술**: ML 모델은 1,192개 당첨 조합에서 학습하지만, 필터는 <1.0% 역사적 발생률 기준으로 모든 가능 조합의 96.3%를 제외.

```
8,145,060 총 조합
    ↓ (1.0% 임계값 필터)
~300,000 조합 남음 (~3.7%)
    ↓ (ML 예측 테스트)
~8.5% 필터 통과 (목표: 15%)
```

**근본 원인**: 학습 도메인과 예측 공간 간 연결 끊김

1. **ML 학습 도메인**: 1,192개 역사적 당첨 패턴 (고확률 공간)
2. **필터 예측 도메인**: 8.14M 조합, 96.3% 제외
3. **결과**: ML은 당첨자와 유사한 패턴 예측하지만, 필터가 유사 패턴 제외

### 구현된 솔루션

**파일**: `main.py:1207` - `generate_final_predictions_enhanced()`

**전략**: ML 완화 임계값 시스템

```python
핵심 파라미터:
- global_probability_threshold: 1.0% (공격적 제외)
- ml_relaxed_threshold: 0.5% (ML 바이패스)
- ml_bypass_filters: 15 (ML이 우회 가능한 필터 수)

완화 가능 필터:
- average, prime_composite, fixed_step, multiple
- ten_section, digit_sum, dispersion, last_digit
- arithmetic_sequence, geometric_sequence, section
- sum_range, max_gap

Critical 필터 (항상 적용):
- odd_even, consecutive (품질 유지)
```

**효과**:
- 기본 ML inclusion: 8.5%
- 목표 ML inclusion: 15%
- 현재 설정: 0.5% 임계값 + 유사 조합 매칭
- 유사 조합 매칭: ML이 모든 필터 실패 시, 가장 가까운 통과 조합 찾기

**분석**: 이것은 근본 문제를 인정하지만 해결하지 않는 **임시방편 솔루션**. 시스템은 당첨자로부터 학습하지만 당첨자 유사 패턴이 필터링된 공간에서 예측해야 함.

---

## 💾 모델 캐싱 시스템

**아키텍처 품질**: ⭐⭐⭐⭐ (8/10)

**구현**: `src/backtesting/optimized_backtesting_framework.py:45-111`

```python
class ModelCache:
    cache_dir: "cache/models/"
    전략: 해시 기반 버전 관리 (학습 데이터의 MD5 정렬)
    레이어:
        1. 메모리 캐시 (dict)
        2. 디스크 캐시 (pickle 파일)
    무효화: 7일 또는 데이터 변경
```

**강점**:
- ✅ 중복 모델 학습 방지
- ✅ 2계층 캐싱 (메모리 + 디스크)
- ✅ 적절한 스케일러 상태 관리
- ✅ 해시 기반 버전 관리로 오래된 모델 방지

**약점**:
- ❌ **스토리지 증가**: 1.7GB+ 도달 가능 (문서화된 이슈)
- ❌ **Pickle 형식**: 버전 안전하지 않음 (Python/라이브러리 업그레이드 시 캐시 깨짐)
- ❌ **자동 정리 없음**: 수동 스크립트 필요 (`clear_model_cache.py`)
- ❌ **스케일러 오류**: 과거 StandardScaler AttributeErrors는 캐시 손상 나타냄

**캐시 관리**:
- 정리 스크립트: `src/scripts/clear_model_cache.py`
- 현재 크기: 0 files (최근 정리됨 또는 비어있음)
- 증가율: 주요 학습 세션당 ~500MB

---

## 📈 성능 추적

**시스템**: `PerformanceStatsManager` → `data/performance_stats.db`

**추적 메트릭**:
- 세션 메타데이터: 날짜, 회차, 테스트 범위
- 설정: 임계값, ML 바이패스 수, ML 가중치
- 모델별 통계: avg_matches, best_match, accuracy_3plus
- 일치 분포: 회차당 0-6 일치
- 오염 감지: 데이터 누출 체크

### 최근 백테스트 결과 (마지막 5 세션, 각 50 회차)

| 모델 | 평균 일치 | 최고 일치 | 비고 |
|-----|----------|----------|------|
| **ENSEMBLE** | 2.08 | 6.0 | ⚠️ **의심스럽게 높음** |
| COMBINED | 1.38 | 6.0 | 가중 앙상블 |
| TEST_MODEL | 1.50 | 3.0 | - |
| LSTM | 0.85 | 3.0 | 예상 범위 내 |
| MONTE_CARLO | 0.84 | 4.0 | 예상 범위 내 |

### 역사적 평균

| 모델 | 평균 일치 | 최고 일치 |
|-----|----------|----------|
| ENSEMBLE (caps) | 2.08 | 6.0 |
| COMBINED (caps) | 1.38 | 6.0 |
| ensemble (lower) | 1.07 | 3.8 |
| combined (lower) | 0.92 | 3.8 |
| lstm | 0.79 | 3.7 |
| monte_carlo | 0.76 | 3.1 |

**Critical 발견**: **ENSEMBLE 모델이 2.08 평균 일치** - 문서화된 목표 범위 0.8-1.5를 초과하며 3.0 오염 임계값에 근접.

**분석**:
- ✅ LSTM과 Monte Carlo는 예상 범위 내 (0.79-0.84)
- ⚠️ ENSEMBLE이 유의미하게 높음 (2.08 vs. 0.8-1.5 목표)
- ⚠️ 중복 항목 (ENSEMBLE/ensemble)은 일관성 없는 명명 제안
- 🚨 **ENSEMBLE 모델의 데이터 오염 또는 과적합 가능성**

---

## ✅ 백테스팅 검증

**프레임워크**: `OptimizedBacktestingFramework` (Singleton 패턴)

**기능**:
- 보너스 번호 지원 (2등 계산)
- 병렬 처리 (10 workers, chunk size 20)
- 재학습 방지를 위한 모델 캐싱
- 오염 감지 (avg_matches > 3.0 시 경고)
- 등수 계산 (1-5등 상금 등급)

**검증 프로세스**:
1. 시계열 분할 (시간순, look-ahead bias 방지)
2. 롤링 윈도우 학습 (예측 회차 이전 데이터만 사용)
3. 필터 검증 (예측이 필터 통과 확인)
4. 일치 카운팅 (예측 vs. 실제 번호 비교)

**강점**:
- ✅ 적절한 시계열 방법론
- ✅ 오염 감지
- ✅ 포괄적인 메트릭 추적
- ✅ 보너스 번호 통합 (현실적인 2등 계산)

**약점**:
- ❌ **교차 검증 없음**: 단일 시계열 분할
- ❌ **하이퍼파라미터 튜닝 검증 없음**: 검증 세트 과적합 가능
- ❌ **50회차 테스트 세트**: 통계적 유의성을 위한 샘플 크기 작음
- ❌ **최근 세션만**: 모든 테스트가 2025-10-09, 빈번한 재학습 제안

---

## 🔧 모델 버전 및 기술 부채

### 버전 증식 분석

**Primary 구현**: `ensemble_predictor.py` (47,962 bytes)
- Main.py에서 사용되는 프로덕션 모델
- 전체 특징 세트, MultiOutputClassifier
- 스케일러 상태 관리 개선

**Fallback 구현**: `ensemble_predictor_fixed.py` (11,510 bytes)
- 예외 발생 시만 import (main.py:3284-3285)
- 버그 수정이 포함된 단순화 버전
- Primary 구현의 불안정성 제안

**실험 버전**:
1. `improved_ensemble_predictor.py` (45,881 bytes) - primary의 95.7% 크기
   - 개선 사항이 포함된 대체 구현
   - Main.py에서 사용되지 않음

2. `super_ensemble.py` (14,119 bytes)
   - Meta-ensemble (앙상블의 앙상블)
   - 실험적, 프로덕션 준비 안됨

3. `filtered_pool_ensemble_predictor.py` (24,894 bytes)
   - 필터 인식 변형
   - 실험적 백테스팅 프레임워크에서 사용

### 기술 부채 평가

| 지표 | 심각도 | 증거 |
|-----|--------|------|
| 버전 증식 | 높음 | 5+ ensemble 버전, 9+ 총 ML 파일 |
| 불명확한 표준 버전 | 높음 | Primary에 fallback 있음, 불안정성 제안 |
| 데드 코드 | 중간 | 사용되지 않는 여러 실험 버전 |
| 폐기 전략 | 없음 | 명확한 폐기 또는 정리 계획 없음 |
| 문서화 격차 | 높음 | 버전 비교 문서 없음 |

**추정 기술 부채**: **4-8 개발자-일** (적절한 통합, 문서화, 폐기를 위해)

---

## ⚙️ TensorFlow/Keras 설정

**품질**: ⭐⭐⭐⭐⭐ (10/10)

**구현** (main.py:34-49, lstm_predictor.py:14-32):

```python
환경 변수 (import 전 설정):
- TF_ENABLE_ONEDNN_OPTS='0'
- TF_CPP_MIN_LOG_LEVEL='3' (ERROR만)
- ABSL_LOGGING_VERBOSITY='1'

Matplotlib 백엔드: 'Agg' (비대화형, tkinter 오류 방지)

경고 억제:
- TensorFlow 컴파일 메트릭 경고
- tensorflow 모듈의 UserWarning
- ABSL 프레임워크 로그
```

**모델 로딩**:
```python
# 적절한 compile=False 패턴
model = load_model(path, compile=False)
model.compile(optimizer='adam', loss='mse', metrics=['mae'])
# 메트릭 빌드를 위한 더미 평가
model.evaluate(dummy_x, dummy_y, verbose=0)
```

**강점**:
- ✅ 깨끗한 콘솔 출력
- ✅ tkinter 관련 충돌 방지
- ✅ 가짜 경고 없는 적절한 모델 로딩
- ✅ CLAUDE.md에 잘 문서화됨

**Best Practice**: 프로덕션 TensorFlow를 위한 **모범적** 설정 관리.

---

## 🏆 품질 평가

### ✅ 강점 (11개 주요 포인트)

1. ✅ **견고한 아키텍처**: 깨끗한 분리 (ML, 필터, 백테스팅, 핵심)
2. ✅ **적절한 정규화**: 모든 모델에 Dropout, L2, batch normalization
3. ✅ **모델 캐싱**: 해시 기반 버전 관리로 중복 학습 방지
4. ✅ **성능 추적**: 오염 감지 기능이 있는 포괄적인 통계 DB
5. ✅ **TensorFlow 설정**: 모범적인 로깅 및 경고 억제
6. ✅ **Monte Carlo 최적화**: 최고 수준의 벡터화 및 조기 종료
7. ✅ **백테스팅 프레임워크**: 적절한 시계열 분할, 보너스 번호 지원
8. ✅ **특징 엔지니어링**: 앙상블 모델의 풍부한 특징 추출
9. ✅ **오류 처리**: 우아한 성능 저하 (ensemble_fixed fallback)
10. ✅ **문서화**: CLAUDE.md가 훌륭한 시스템 개요 제공
11. ✅ **과적합 방지 조치**: 얕은 트리, 높은 정규화, 증강 비활성화

### ❌ 약점 (11개 주요 포인트)

1. ❌ **ML-필터 연결 끊김**: 8.5% inclusion rate vs. 15% 목표 (문서화된 이슈)
2. ❌ **소규모 학습 데이터셋**: 깊은 LSTM에 1,192 회차 불충분
3. ❌ **버전 증식**: 5+ ensemble 버전, 불명확한 표준 구현
4. ❌ **ENSEMBLE 과적합**: 2.08 평균 일치가 0.8-1.5 목표 범위 초과
5. ❌ **기술 부채**: 실험 모델에 대한 폐기 전략 없음
6. ❌ **캐시 관리**: 수동 정리 필요, 1.7GB+ 증가
7. ❌ **프랙탈 분석**: 이산 무작위 이벤트에 적용 가능성 의문
8. ❌ **특징 폭발**: 135+ 시간적 특징이 차원의 저주 유발 가능
9. ❌ **소규모 검증 세트**: 통계적 신뢰성을 위해 50회차 백테스트 불충분
10. ❌ **교차 검증 없음**: 백테스팅에서 단일 시계열 분할
11. ❌ **근본적 한계**: ML이 당첨자로부터 학습하지만 필터링된 공간에서 예측

### 🚨 Critical 이슈 (3개)

#### Issue 1: ENSEMBLE 모델 오염 위험 🔴 URGENT

**현상**:
- 평균 일치: 2.08 (목표: 0.8-1.5, 오염: >3.0)
- 목표 범위 38% 초과

**가능한 원인**:
1. 데이터 누출 (미래 정보 학습에 사용)
2. 특징 엔지니어링에서 look-ahead bias
3. 검증 세트 과적합
4. 부적절한 시계열 분할

**조치**:
- 백테스팅 시계열 분할 검증
- 특징 엔지니어링에서 데이터 누출 체크
- 학습 vs. 테스트 데이터 분리 검토
- 교차 검증 구현 (확장 윈도우)

**우선순위**: **높음**

---

#### Issue 2: ML-필터 통합 실패 🔴 URGENT

**현상**:
- 8.5% inclusion rate vs. 15% 목표
- Band-aid 솔루션 (ml_relaxed_threshold)이 근본 원인 해결 안 함

**근본 원인**:
- ML은 고확률 공간 (당첨자)에서 학습
- 필터는 저확률 공간 (역사적 <1.0%)에서 예측
- 학습 도메인 ≠ 예측 도메인

**조치**:
1. 필터링된 풀 대표 샘플 포함하도록 학습 재설계
2. 중요도 가중치 구현 (당첨자 vs. 필터 통과)
3. 목표: 품질 유지하면서 30%+ inclusion rate
4. 대안: 필터 임계값 완화 (1.0% → 0.5%)

**우선순위**: **높음**

---

#### Issue 3: 버전 관리 위기 🟡 MEDIUM

**현상**:
- 5개 ensemble 버전, fallback 패턴이 불안정성 제안
- 9+ 총 실험 ML 파일
- 명확한 폐기 전략 없음

**영향**:
- 유지보수 혼란 (어느 버전 사용?)
- 버그 수정 어려움 (모든 버전 업데이트?)
- 코드 리뷰 복잡성
- 테스트 커버리지 격차

**조치**:
1. 표준 ensemble_predictor 선택
2. 실험 버전 폐기
3. 모든 import 문 업데이트
4. 버전 히스토리 문서화
5. 폐기 정책 수립

**우선순위**: **중간**

---

## 💡 주요 발견 사항

### 모델 품질 점수

| 모델 | 아키텍처 | 통합 | 성능 | 전체 |
|-----|---------|------|------|------|
| LSTM | 8/10 | 7/10 | 7/10 | **7.3/10** |
| Ensemble | 8/10 | 6/10 | 6/10 | **6.7/10** |
| Monte Carlo | 9/10 | 8/10 | 9/10 | **8.7/10** |
| Bayesian | 7/10 | 5/10 | 6/10 | **6.0/10** |
| Fractal | 6/10 | 4/10 | 5/10 | **5.0/10** |

**시스템 전체 품질 점수: 7.2/10**

---

## 🎯 권장 사항

### 우선순위별 최적화 기회

#### 1. ENSEMBLE 오염 조사 (영향: 높음, 노력: 2일)

**작업**:
- 백테스팅 시계열 분할 검증
- 특징 엔지니어링에서 데이터 누출 체크
- 학습 vs. 테스트 데이터 분리 검토

**예상 영향**: 신뢰할 수 있는 성능 메트릭, 오염 제거

---

#### 2. 모델 버전 통합 (영향: 높음, 노력: 3일)

**작업**:
- 표준 ensemble_predictor 선택
- 실험 버전 폐기
- 모든 import 업데이트
- 버전 히스토리 문서화

**예상 영향**: 유지보수성 향상, 코드 명확성

---

#### 3. ML-필터 통합 재설계 (영향: 높음, 노력: 5일)

**작업**:
- 필터링된 풀 샘플로 모델 학습 (당첨자만이 아닌)
- 중요도 가중치 구현
- 목표: 품질 유지하면서 30%+ inclusion rate

**예상 영향**: ML 예측의 실제 적용성 향상

---

#### 4. 학습 데이터셋 확장 (영향: 중간, 노력: 1일)

**현재**: LSTM에 1,192 회차 불충분

**옵션**:
- A: 더 많은 역사 데이터 수집 (가능한 경우)
- B: 데이터 증강 신중히 사용
- C: 더 단순한 모델로 전환 (낮은 용량)

**예상 영향**: 과적합 감소, 일반화 개선

---

#### 5. 교차 검증 구현 (영향: 중간, 노력: 2일)

**작업**:
- 시계열 교차 검증 (확장 윈도우)
- 여러 테스트 분할에서 검증
- 통계적 유의성 테스트 (bootstrap 신뢰 구간)

**예상 영향**: 강건한 성능 추정치

---

#### 6. 캐시 관리 자동화 (영향: 낮음, 노력: 1일)

**작업**:
- 자동 캐시 정리 (LRU 제거)
- 캐시 크기 모니터링
- 버전 안전 형식으로 마이그레이션 (예: ONNX)

**예상 영향**: 디스크 공간 절약, 안정성 향상

---

## 📄 결론

로또 예측 시스템은 적절한 아키텍처, 정규화, 성능 추적을 갖춘 **전문적인 ML 엔지니어링 관행**을 보여줍니다. 그러나 세 가지 근본적 과제에 직면:

1. **과적합**: ENSEMBLE 모델이 의심스러운 성능 (2.08 평균 일치)
2. **ML-필터 불일치**: 모델이 당첨자로부터 학습하지만 필터링된 공간에서 예측 (8.5% 통과율)
3. **기술 부채**: 명확한 폐기 전략 없는 여러 ensemble 버전

**권장 조치**:
1. **즉시**: ENSEMBLE 오염 조사 (데이터 누출 위험)
2. **단기**: 모델 버전 통합, 교차 검증 구현
3. **장기**: ML-필터 통합 재설계, 학습 데이터셋 확장

**전체 평가**: 시스템은 실험용으로 프로덕션 준비되었으나 신뢰할 수 있는 장기 사용을 위해 최적화 필요. 코드베이스는 잘 구조화되고 유지 관리 가능하여 개선 구현이 간단함.

---

## 🔗 관련 문서

- [1단계: 아키텍처 분석](STEP1_ARCHITECTURE_ANALYSIS.md) - 전체 시스템 구조
- [2단계: 데이터 레이어 검증](STEP2_DATA_LAYER_ANALYSIS.md) - DB 무결성 및 데이터 수집
- [3단계: 필터 시스템 분석](STEP3_FILTER_SYSTEM_ANALYSIS.md) - 필터 아키텍처
- [CLAUDE.md](../CLAUDE.md) - 프로젝트 전체 가이드
- [config.yaml](../config.yaml) - 시스템 설정
- [adaptive_filter_config.yaml](../configs/adaptive_filter_config.yaml) - 필터 설정

---

**보고서 작성**: Claude (Analyzer + QA Personas)
**검증 방법**: Sub-Agent 위임, 전체 파일 읽기, 성능 통계 DB 분석
**분석 도구**: Read, Grep, Glob, Task (General-purpose sub-agent), Database queries
