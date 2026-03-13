# 로또 예측 시스템 - 코드 리뷰 문서

> **문서 버전**: 1.0
> **작성일**: 2025년 12월 6일
> **대상 프로젝트**: 로또 번호 예측 시스템 (ML/AI 기반)
> **코드베이스 규모**: ~26,000줄 (Python 100개+ 파일)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [핵심 컴포넌트 분석](#3-핵심-컴포넌트-분석)
4. [코드 품질 평가](#4-코드-품질-평가)
5. [테스트 현황](#5-테스트-현황)
6. [보안 및 성능](#6-보안-및-성능)
7. [개선 권장사항](#7-개선-권장사항)
8. [결론](#8-결론)

---

## 1. 프로젝트 개요

### 1.1 목적

한국 로또(6/45) 번호 예측 시스템으로, ML/AI 기술을 활용하여 8,145,060개의 가능한 조합에서 확률적으로 유망한 조합을 선별합니다.

### 1.2 핵심 가치

| 항목 | 설명 |
|------|------|
| **조합 감소율** | 96.3% (8.14M → ~300K) |
| **확률 개선** | 27배 (이론적) |
| **필터 시스템** | 16종 독립 필터 |
| **ML 모델** | 6종 앙상블 |
| **자동화** | 24시간 무중단 운영 |

### 1.3 기술 스택

```
언어: Python 3.8+
ML/DL: TensorFlow 2.8+, Keras, XGBoost, LightGBM, CatBoost
최적화: Optuna (Bayesian Optimization)
웹: Flask (Dashboard)
DB: SQLite (다중 데이터베이스)
테스트: pytest, pytest-cov
```

---

## 2. 시스템 아키텍처

### 2.1 전체 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py (4,400+ 줄)                     │
│                      시스템 진입점 및 조정자                      │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 데이터 수집    │     │  필터링 시스템   │     │   ML/AI 예측    │
│ DataCollector │     │  FilterManager  │     │ 6개 모델 앙상블  │
└───────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ lotto_numbers │     │  16개 필터 적용  │     │ LSTM, Ensemble  │
│     .db       │     │ 8.14M → ~300K   │     │ Monte Carlo 등  │
└───────────────┘     └─────────────────┘     └─────────────────┘
                                │                       │
                                └───────────┬───────────┘
                                            ▼
                              ┌─────────────────────────┐
                              │   최종 예측 통합        │
                              │ generate_final_         │
                              │ predictions_enhanced()  │
                              └─────────────────────────┘
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │   Flask Dashboard       │
                              │   (Port 5001)          │
                              └─────────────────────────┘
```

### 2.2 레이어 구조

```
src/
├── core/           # 핵심 비즈니스 로직 (38개 파일)
│   ├── db_manager.py           # DB 통합 관리 (Singleton)
│   ├── filter_manager.py       # 필터 체인 조정 (895줄)
│   ├── adaptive_probability_filter.py  # 확률 기반 필터 (661줄)
│   ├── threshold_manager.py    # 임계값 중앙 관리 (Singleton)
│   └── pattern_manager.py      # 패턴 분석 (662줄)
│
├── filters/        # 16개 독립 필터 구현
│   ├── base_filter.py          # 추상 기반 클래스
│   ├── match_filter.py         # 과거 당첨번호 일치
│   ├── odd_even_filter.py      # 홀짝 패턴
│   ├── sum_range_filter.py     # 합계 범위 (가장 효율적)
│   └── ... (13개 추가 필터)
│
├── ml/             # 머신러닝 모델 (10개 파일)
│   ├── lstm_predictor.py       # LSTM 시계열 예측
│   ├── ensemble_predictor.py   # RF+XGBoost+NN 앙상블
│   └── filtered_pool_ensemble_predictor.py
│
├── probabilistic/  # 확률 모델
│   ├── monte_carlo_simulator.py  # Monte Carlo (6,000회)
│   └── bayesian_inference.py     # 베이지안 추론
│
├── advanced/       # 고급 분석
│   └── fractal_pattern_analyzer.py  # 프랙탈/카오스 이론
│
├── backtesting/    # 백테스팅 프레임워크
│   └── optimized_backtesting_framework.py (726줄)
│
├── optimization/   # 최적화 시스템
│   └── improved_auto_improvement_manager.py
│
└── automation/     # 24시간 자동화
    └── auto_scheduler.py
```

### 2.3 디자인 패턴

| 패턴 | 적용 위치 | 목적 |
|------|----------|------|
| **Singleton** | DatabaseManager, ThresholdManager | 상태 일관성 |
| **Observer** | ThresholdManager | 임계값 변경 동기화 |
| **Strategy** | FilterManager | 필터 알고리즘 교체 |
| **Factory** | Filter 등록 | 필터 동적 생성 |
| **Template Method** | BaseFilter | 필터 공통 로직 |
| **Chain of Responsibility** | 필터 체인 | 순차적 필터링 |

---

## 3. 핵심 컴포넌트 분석

### 3.1 필터링 시스템 (16개 필터)

#### 필터 목록 및 효율성

| 순위 | 필터명 | 제외율 | 역할 |
|------|--------|--------|------|
| 1 | SumRangeFilter | 45% | 번호 합계 범위 (83~197) |
| 2 | ConsecutiveFilter | 30% | 연속번호 패턴 |
| 3 | MaxGapFilter | 25% | 번호 간 최대 간격 |
| 4 | SectionFilter | 22% | 15개 구간 분포 |
| 5 | GeometricSequenceFilter | 20% | 등비수열 패턴 |
| 6 | DigitSumFilter | 20% | 자리수 합계 |
| 7 | ArithmeticSequenceFilter | 18% | 등차수열 패턴 |
| 8 | DispersionFilter | 18% | 분산도 분석 |
| 9 | OddEvenFilter | 15% | 홀짝 비율 |
| 10 | FixedStepFilter | 15% | 고정 간격 패턴 |
| 11 | PrimeCompositeFilter | 15% | 소수/합성수 분포 |
| 12 | TenSectionFilter | 12% | 10구간 분석 |
| 13 | LastDigitFilter | 10% | 끝자리 패턴 |
| 14 | AverageFilter | 10% | 평균값 범위 |
| 15 | MultipleFilter | 8% | 배수 패턴 |
| 16 | MatchFilter | 5% | 과거 번호 일치 |

#### 필터 체인 최적화

```python
# 효율성 기반 자동 정렬
filter_order = sorted(filters, key=lambda f: f.exclusion_rate, reverse=True)
# 가장 많이 제외하는 필터 먼저 실행 → 후속 필터 부하 감소
```

### 3.2 ML/AI 모델 구조

#### 모델별 상세 사양

| 모델 | 아키텍처 | 과적합 방지 |
|------|----------|------------|
| **LSTM** | 3-layer (128→64→32), Dropout 0.35, BatchNorm | Early Stopping, L2 정규화 |
| **Random Forest** | 50 estimators, depth=3 | 얕은 트리, 큰 leaf 샘플 |
| **XGBoost** | 50 estimators, lr=0.01 | L1/L2 정규화 (2.0, 3.0) |
| **Neural Network** | (32, 16), ReLU | 강한 L2 (0.5) |
| **Monte Carlo** | 6,000회 시뮬레이션 | 조기 종료, 수렴 감지 |
| **Bayesian** | 사전/사후 확률 추론 | 스무딩 적용 |

#### 앙상블 가중치

```python
final_prediction = 0.3 * RF + 0.4 * XGBoost + 0.3 * NN
# XGBoost가 가장 높은 가중치 (0.4)
```

### 3.3 핵심 알고리즘

#### ML-필터 통합 (가장 중요한 로직)

```
문제: ML은 1,186개 역사 데이터 학습 → 필터는 300K 풀에서 선택
결과: ML 예측의 8.5%만 필터 통과 (15% 목표)

해결책 (generate_final_predictions_enhanced):
1. ML 완화 임계값 적용 (1.0% → 0.5%)
2. 완화 가능 필터 13개 정의
3. 유사 조합 매칭 (3-4개 번호 일치)
4. 하이브리드 필터링 (핵심 4개 + 완화 13개)
```

#### 자동 최적화 (Optuna)

```
Optuna TPE Sampler 사용
- 누적 학습: 0 → 25 → 50 → 75... 시행
- 체크포인트 기반 복구
- 자동 롤백 (10% 성능 저하 시)
- 매일 3AM 자동 실행 (KST)
```

---

## 4. 코드 품질 평가

### 4.1 종합 등급: **B-**

| 카테고리 | 점수 | 비고 |
|----------|------|------|
| 아키텍처 | B+ | 레이어 분리 양호, 일부 결합도 높음 |
| 코드 가독성 | B | 주석 충분, 일부 함수 과대 |
| 유지보수성 | C+ | 중복 코드 존재, 설정 분산 |
| 테스트 | C- | 17.76% 커버리지 (목표 70%) |
| 문서화 | B | CLAUDE.md 상세, API 문서 부족 |
| 성능 | A- | 병렬화 우수, 캐싱 전략 양호 |

### 4.2 강점

#### 잘 구현된 부분

1. **싱글톤 패턴 일관성**
```python
class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, base_dir='data'):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

2. **Observer 패턴 (ThresholdManager)**
```python
# 임계값 변경 시 모든 구독자에게 자동 통지
threshold_manager.register_observer(filter_manager)
threshold_manager.set_threshold(1.5)  # 자동 동기화
```

3. **병렬 처리 최적화**
```python
# 배치 크기 동적 결정
batch_size = min(
    100000,
    available_memory * 0.5 / memory_per_combination
)
# ProcessPoolExecutor로 멀티코어 활용
```

4. **TensorFlow 경고 억제**
```python
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore', category=UserWarning, module='absl')
```

5. **에러 복구 체계**
```python
class SystemHealthChecker:
    def check_system_health(self):
        self._auto_collect_bonus_numbers()
        self._auto_clean_cache()
        self._check_database_structure()
        # ... 7개 자동 점검
```

### 4.3 약점

#### 개선 필요 부분

1. **main.py 과대 (4,400+ 줄)**
```
문제: God Object 안티패턴
- 시스템 초기화
- 필터링 로직
- ML 예측 통합
- 대시보드 시작
- 자동화 조정
모두 한 파일에 집중

권장: 기능별 모듈 분리
- main.py (300줄 이하): 진입점만
- src/orchestration/: 통합 로직
- src/prediction/: 예측 생성
```

2. **중복 코드 (~900줄)**
```python
# adaptive_probability_filter.py에서 반복되는 패턴
# 각 필터별 동적 기준값 생성 로직이 유사함

# 개선안: 제네릭 함수로 통합
def generate_threshold_criteria(filter_name, statistics, threshold):
    """공통 기준값 생성 (16개 필터 통합)"""
    pass
```

3. **하드코딩된 설정**
```python
# filter_manager.py L423-440
filter_efficiency = {
    'sum_range': 0.45,  # 하드코딩!
    'match': 0.05,
    # ...
}
# config_manager 결과 무시됨

# 권장: 설정 파일에서 로드
efficiency = self.config_manager.get_filter_efficiency()
```

4. **필터 추가 시 수정 필요 위치 (3곳)**
```
1. filter_manager.py: _auto_register_filters()
2. adaptive_probability_filter.py: analyze_patterns()
3. adaptive_probability_filter.py: generate_dynamic_criteria()

권장: Plugin 시스템 도입
```

### 4.4 코드 메트릭스

| 메트릭 | 값 | 평가 |
|--------|-----|------|
| 총 줄 수 | ~26,000 | 중간 규모 |
| 평균 함수 길이 | 45줄 | 약간 높음 (30줄 권장) |
| 순환 복잡도 | 평균 8.5 | 양호 (10 이하) |
| 중복률 | ~5% | 허용 범위 (3% 이하 권장) |
| 주석 비율 | 15% | 양호 |

---

## 5. 테스트 현황

### 5.1 테스트 통계

| 항목 | 값 |
|------|-----|
| 테스트 파일 수 | 31개 |
| 테스트 함수 | 282개 |
| 코드 커버리지 | **17.76%** |
| 목표 커버리지 | 70% |
| 격차 | 52.24 포인트 |

### 5.2 테스트 분류

```
단위 테스트(Unit):      44개 (15.6%)  ← 부족
통합 테스트(Integration): 16개 (5.7%)   ← 매우 부족
느린 테스트(Slow):       24개 (8.5%)
일반 테스트:            198개 (70.2%)
```

### 5.3 커버리지 상세

#### 잘 테스트된 모듈 (상위 5개)

| 모듈 | 커버리지 | 평가 |
|------|---------|------|
| performance_metrics.py | 38% | 우수 |
| base_filter.py | 28% | 양호 |
| last_digit_filter.py | 28% | 양호 |
| memory_monitor.py | 25% | 양호 |
| logger.py | 23% | 보통 |

#### 테스트 부족 모듈 (하위 5개) - 긴급

| 모듈 | 줄 수 | 커버리지 | 상태 |
|------|------|---------|------|
| FilterManager | 895 | 6% | 🔴 위험 |
| PatternManager | 662 | 6% | 🔴 위험 |
| AdaptiveProbabilityFilter | 661 | 8% | 🔴 위험 |
| EnsemblePredictor | 517 | 8% | 🔴 위험 |
| OptimizedBacktesting | 726 | 9% | 🔴 위험 |

#### 테스트 없는 모듈 (0%) - 약 50개

- 7개 필터 (digit_sum, dispersion, ml_prediction 등)
- cross_validation.py (120줄)
- auto_adjustment_system.py (507줄)
- 대부분의 optimization/ 모듈

### 5.4 테스트 품질 평가: **C-**

**강점:**
- pytest 표준 구조 사용
- conftest.py 픽스처 체계 정립
- 테스트 마커 정의 (@unit, @integration, @slow)

**약점:**
- 핵심 모듈 거의 미테스트
- 통합 테스트 극소수 (5.7%)
- 9개 테스트 FAILED (test_auto_scheduler.py)
- E2E 테스트 부재

---

## 6. 보안 및 성능

### 6.1 보안 현황

| 항목 | 상태 | 비고 |
|------|------|------|
| SQL Injection | ✅ 안전 | 파라미터화된 쿼리 사용 |
| 파일 경로 | ⚠️ 주의 | 일부 절대 경로 하드코딩 |
| 민감 정보 | ✅ 안전 | API 키 없음 (공공 데이터) |
| 입력 검증 | ✅ 양호 | 번호 범위 검증 존재 |
| 로깅 | ✅ 양호 | 민감 정보 미포함 |

### 6.2 성능 현황

#### 실행 시간

| 작업 | 시간 | 비고 |
|------|------|------|
| 초기 실행 | 5-10분 | 모델 학습 포함 |
| 후속 실행 | 2-3분 | 캐시 활용 |
| 필터링 | 30-60초 | 8.14M → 300K |
| ML 예측 | 20-40초 | 6개 모델 순차 |

#### 메모리 사용

| 항목 | 크기 | 비고 |
|------|------|------|
| 모델 캐시 | ~1.7GB | 7일 TTL |
| 데이터베이스 | ~500MB | 6개 DB 합계 |
| 실행 시 피크 | ~4GB | 병렬 처리 시 |

### 6.3 성능 최적화 기법

1. **병렬 처리**
   - ProcessPoolExecutor (12 워커, 75% CPU)
   - numpy 벡터화 연산
   - 배치 처리 (60,000개 단위)

2. **캐싱**
   - 모델 캐시 (hash 기반 버전 관리)
   - LRU 캐시 (반복 연산 방지)
   - 결과 캐싱 (Monte Carlo)

3. **조기 종료**
   - 수렴 감지 (Monte Carlo)
   - Early Stopping (LSTM)
   - 빠른 실패 전략 (필터)

---

## 7. 개선 권장사항

### 7.1 즉시 개선 (1주일)

| 우선순위 | 항목 | 예상 효과 |
|---------|------|----------|
| **P0** | main.py 분리 (4,400줄 → 300줄) | 유지보수성 80% 향상 |
| **P0** | FilterManager 테스트 추가 (100개) | 커버리지 +15% |
| **P0** | 9개 실패 테스트 수정 | 안정성 확보 |
| **P1** | 중복 코드 제거 (~900줄) | 코드 크기 5% 감소 |

### 7.2 단기 개선 (1개월)

| 항목 | 설명 |
|------|------|
| **테스트 강화** | 커버리지 40% 달성 (~480개 테스트 추가) |
| **Plugin 시스템** | 필터 추가 시 1곳만 수정 |
| **설정 중앙화** | 하드코딩 제거, YAML 통합 |
| **API 문서화** | Sphinx 또는 pdoc 도입 |

### 7.3 중기 개선 (3개월)

| 항목 | 설명 |
|------|------|
| **테스트 70% 달성** | ~1,500개 테스트 |
| **ML-필터 갭 축소** | 포함률 8.5% → 15% |
| **동적 앙상블 가중치** | 성능 기반 자동 조정 |
| **특징 엔지니어링 확장** | 상관관계, 주기성 탐지 |

### 7.4 리팩토링 제안

#### main.py 분리 계획

```
현재: main.py (4,400줄)

목표:
├── main.py (300줄)           # 진입점만
├── src/orchestration/
│   ├── system_initializer.py  # 초기화
│   ├── prediction_coordinator.py  # 예측 통합
│   └── automation_manager.py  # 자동화
├── src/web/
│   └── dashboard_launcher.py  # 대시보드
└── src/health/
    └── system_checker.py      # 상태 점검
```

#### 필터 시스템 통합

```
현재:
  FilterManager (895줄) + AdaptiveProbabilityFilter (661줄)
  → 별도 동작, IntegratedFilterManager로 연동

목표:
  UnifiedFilterChain (단일 체인)
  - 확률 필터 (1단계)
  - 개별 필터 (2단계)
  - 명확한 책임 분리
```

---

## 8. 결론

### 8.1 종합 평가

| 관점 | 평가 | 요약 |
|------|------|------|
| **기능성** | A | 복잡한 요구사항 충실히 구현 |
| **아키텍처** | B+ | 레이어 분리 양호, 일부 결합도 높음 |
| **코드 품질** | B- | 가독성 양호, 중복/과대 함수 존재 |
| **테스트** | C- | 17.76% 커버리지, 핵심 모듈 미테스트 |
| **문서화** | B | CLAUDE.md 상세, API 문서 부족 |
| **성능** | A- | 병렬화/캐싱 우수 |

### 8.2 핵심 강점

1. **포괄적인 ML 시스템**: 6개 다양한 모델 통합
2. **체계적인 필터링**: 16개 필터로 27배 확률 개선
3. **자동화**: 24시간 무중단 운영, 자동 최적화
4. **에러 복구**: SystemHealthChecker 자동 수리
5. **성능 최적화**: 병렬 처리, 캐싱, 조기 종료

### 8.3 핵심 개선 필요 사항

1. **테스트 커버리지 52포인트 부족** (17.76% → 70%)
2. **main.py 과대** (4,400줄 → 300줄 분리 필요)
3. **중복 코드 ~900줄** (필터 기준값 생성)
4. **하드코딩된 설정** (필터 효율성 등)
5. **ML-필터 포함률** (8.5% → 15% 목표)

### 8.4 최종 권장사항

**즉시 실행:**
1. main.py 모듈 분리 시작
2. FilterManager 단위 테스트 100개 추가
3. 실패한 9개 테스트 수정

**향후 3개월:**
1. 테스트 커버리지 70% 달성
2. Plugin 기반 필터 시스템 도입
3. ML-필터 통합 개선

---

## 부록

### A. 파일 구조 요약

```
프로젝트 루트/
├── main.py              # 진입점 (4,400줄)
├── config.yaml          # 메인 설정
├── configs/
│   └── adaptive_filter_config.yaml  # 필터 설정
├── src/                 # 소스 코드 (100+ 파일)
├── tests/               # 테스트 (31 파일)
├── data/                # SQLite DB
├── cache/               # 모델 캐시
├── logs/                # 로그 파일
└── docs/                # 문서
```

### B. 주요 설정 파일

| 파일 | 용도 |
|------|------|
| config.yaml | 워커 수, 배치 크기, 메모리 제한 |
| adaptive_filter_config.yaml | 필터 임계값, ML 완화 임계값 |
| pytest.ini | 테스트 설정 (70% 커버리지 목표) |

### C. 실행 명령어

```bash
# 전체 시스템 실행
python main.py

# 테스트 실행
python -m pytest tests/ --cov=src

# 캐시 정리
python src/scripts/clear_model_cache.py

# 대시보드 수동 시작
python src/scripts/enhanced_dashboard_v2.py
```

---

**문서 작성**: Claude Code
**검토 상태**: 초안
**다음 검토 예정**: 코드 변경 시
