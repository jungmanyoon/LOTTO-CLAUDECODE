# 로또 예측 시스템 아키텍처 문서

**프로젝트**: Korean Lottery (로또) Prediction System
**버전**: R0 (2025-12-07 기준)
**Repository**: `D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\`

---

## 시스템 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         로또 예측 시스템 전체 구조                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              사용자 인터페이스                                 │
├──────────────────────────────┬──────────────────────────────────────────────┤
│        main.py (Entry)       │        enhanced_dashboard_v2.py              │
│   - CLI 인터페이스            │   - Flask 웹 대시보드 (Port 5001)             │
│   - 자동 실행 파이프라인       │   - 실시간 예측 표시                          │
│   - 명령행 옵션 처리          │   - 예측 생성 버튼                            │
└──────────────────────────────┴──────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               Core 계층                                      │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│ DatabaseManager │ ThresholdManager│ FilterManager   │ PerformanceMetrics    │
│ (Singleton)     │ (Singleton)     │ (Singleton)     │ (Static)              │
│                 │                 │                 │                       │
│ - LottoNumbersDB│ - 임계값 관리   │ - 16개 필터 관리 │ - 점수 계산           │
│ - CombinationsDB│ - Observer 패턴 │ - 병렬 처리     │ - 정규화             │
│ - FilterDB      │ - Decimal 정밀도│ - 증분 필터링   │ - 오염 감지          │
│ - PatternsDB    │                 │                 │                       │
└─────────────────┴─────────────────┴─────────────────┴───────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│     필터링 시스템      │  │      ML/AI 모델       │  │    최적화 시스템       │
├───────────────────────┤  ├───────────────────────┤  ├───────────────────────┤
│ 16개 통계 필터:        │  │ LSTM Predictor       │  │ ThresholdOptimizer    │
│ - sum_range (45%)     │  │ - 50회차 시계열 학습   │  │ - Optuna TPE          │
│ - consecutive (30%)   │  │                       │  │ - 베이지안 최적화     │
│ - max_gap (25%)       │  │ Ensemble Predictor    │  │                       │
│ - odd_even (15%)      │  │ - RF + XGBoost + NN   │  │ SmartAutoLearning     │
│ - match (5%)          │  │                       │  │ - 24시간 자동 학습    │
│ - ...                 │  │ Monte Carlo           │  │ - 롤백 지원           │
│                       │  │ - 6,000 시뮬레이션    │  │                       │
│                       │  │                       │  │ FilterOrderOptimizer  │
│                       │  │ Bayesian Inference    │  │ - Jaccard 유사도      │
│                       │  │ - 확률적 추론         │  │                       │
└───────────────────────┘  └───────────────────────┘  └───────────────────────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            데이터 계층                                       │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────────────┤
│lotto_numbers │ combinations │ filters/*.db │   patterns   │ performance_    │
│    .db       │    .db       │  (16개)      │     .db      │   stats.db      │
└──────────────┴──────────────┴──────────────┴──────────────┴─────────────────┘
```

## 싱글톤 관계도

```
                    ┌─────────────────────┐
                    │   ThresholdManager  │
                    │     (Singleton)     │
                    │   - 임계값 중앙 관리 │
                    │   - Observer 패턴   │
                    └──────────┬──────────┘
                               │ notify_observers()
                    ┌──────────┼──────────┐
                    │          │          │
                    ▼          ▼          ▼
        ┌───────────────┐ ┌─────────┐ ┌──────────────────┐
        │ FilterManager │ │ Optim.  │ │ AutoImprovement  │
        │  (Singleton)  │ │         │ │    Manager       │
        └───────┬───────┘ └─────────┘ └──────────────────┘
                │
                ▼
        ┌───────────────────────────┐
        │    DatabaseManager        │
        │      (Singleton)          │
        │                           │
        │  ┌─────────────────────┐  │
        │  │   LottoNumbersDB    │  │
        │  │   CombinationsDB    │  │
        │  │   FilterDB (x16)    │  │
        │  │   PatternsDB        │  │
        │  └─────────────────────┘  │
        └───────────────────────────┘
```

## 데이터 흐름 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              데이터 처리 파이프라인                           │
└─────────────────────────────────────────────────────────────────────────────┘

 동행복권 ─────▶ fetch_and_save_lotto_data() ─────▶ LottoNumbersDB (1,186+ 회차)
                          │
                          ▼
 8,145,060 조합 ───────────────────────────────────────────────────────────────
        │
        ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                     FilterManager (병렬 처리)                            │
 │                                                                          │
 │  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   │
 │  │sum_range│ → │odd_even │ → │consec.  │ → │max_gap  │ → │ match   │   │
 │  │  45%    │   │  15%    │   │  30%    │   │  25%    │   │   5%    │   │
 │  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘   │
 │                                                                          │
 └─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
 ~300,000 조합 (확률 > 1.0% 통과) ─────────────────────────────────────────────
        │
        ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  LSTM (0.25) ──────┐                                                     │
 │  Ensemble (0.50) ──┼──▶ 가중 평균 ──▶ 20개 ML 예측 조합                  │
 │  Monte Carlo (0.25)┘                                                     │
 └─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
 ML 완화 임계값 (0.5%) 적용 ──▶ ~15% 포함률 목표
        │
        ▼
 최종 5개 세트 예측 ─────────▶ Dashboard (Port 5001) 표시
```

---

## 목차

1. [시스템 개요](#시스템-개요)
2. [아키텍처 패턴](#아키텍처-패턴)
3. [모듈 구조](#모듈-구조)
4. [데이터 흐름](#데이터-흐름)
5. [의존성 관리](#의존성-관리)
6. [설정 파일 가이드](#설정-파일-가이드)
7. [성능 최적화](#성능-최적화)
8. [확장 가이드](#확장-가이드)

---

## 시스템 개요

### 핵심 목표

한국 로또(1-45 중 6개 선택, 총 8,145,060 조합)에서 확률 기반 필터링과 ML/AI를 결합하여 당첨 가능성이 낮은 조합을 제외하고 최적의 예측 조합을 생성합니다.

**핵심 메트릭**:
- 입력: 8,145,060 조합 (전체)
- 필터링 후: ~300,000 조합 (96.3% 제외, threshold=1.0%)
- ML 예측: 5개 모델 앙상블
- 최종 출력: 5-10개 추천 조합
- 백테스팅 목표: 0.6-2.0 평균 일치 개수

### 시스템 특징

1. **완전 자동화**
   - F5 실행으로 모든 기능 자동 시작
   - 새 회차 자동 감지 및 업데이트
   - 백그라운드 최적화 (24/7 무한 반복)

2. **고성능 병렬 처리**
   - 12 workers (75% CPU 활용)
   - 60K 배치 크기 (31GB 메모리 최적화)
   - ProcessPoolExecutor 기반

3. **지능형 학습 시스템**
   - Optuna Bayesian 최적화 (140 trials/cycle)
   - 체크포인트 기반 누적 학습
   - 성능 저하 시 자동 롤백 (>10%)

4. **다중 ML 모델 앙상블**
   - LSTM (시계열)
   - Ensemble (RF+XGBoost+NN)
   - Monte Carlo (6K 시뮬레이션)
   - Bayesian Inference
   - Fractal Pattern Analysis

---

## 아키텍처 패턴

### 5-Layer Architecture

```
[Layer 5] Presentation
    └── Flask Dashboard (port 5001)

[Layer 4] Application Orchestration
    └── main.py (조율)

[Layer 3] Business Logic
    ├── FilterManager (필터링)
    ├── ML Models (예측)
    └── ThresholdOptimizer (최적화)

[Layer 2] Data Access
    └── DatabaseManager (Singleton)

[Layer 1] Infrastructure
    ├── ProcessPoolExecutor
    ├── TensorFlow/Keras
    └── Optuna
```

### 디자인 패턴

#### 1. Singleton Pattern (5개)

**DatabaseManager** (`src/core/db_manager.py`):
```python
class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

**적용 대상**:
- DatabaseManager: 전역 DB 연결 관리 (8 connections)
- ThresholdManager: 임계값 중앙 관리 (Observer 패턴 결합)
- FilterManager: 필터 실행 조율 (암시적)
- AdaptiveProbabilityFilter: 확률 필터 (암시적)
- IntegratedFilterManager: 통합 필터 조율 (암시적)

**장점**:
- 리소스 공유 (DB connection pool)
- 상태 일관성 (threshold 변경 시 전역 반영)
- Thread-safe (Lock 사용)

#### 2. Factory Pattern

**BaseFilter** (`src/filters/base_filter.py`):
```python
from abc import ABC, abstractmethod

class BaseFilter(ABC):
    @abstractmethod
    def apply(self, combinations: List[tuple]) -> List[tuple]:
        pass

    @abstractmethod
    def apply_filter(self, combination: tuple) -> bool:
        pass
```

**구현 예시** (`src/filters/odd_even_filter.py`):
```python
class OddEvenFilter(BaseFilter):
    def apply_filter(self, combination: tuple) -> bool:
        odd_count = sum(1 for num in combination if num % 2 == 1)
        return odd_count not in self.excluded_counts
```

**장점**:
- 일관된 인터페이스
- 새 필터 추가 용이 (BaseFilter 상속)
- 테스트 용이성 (Mock 필터)

#### 3. Observer Pattern

**ThresholdManager** (`src/core/threshold_manager.py`):
```python
class ThresholdManager:
    def __init__(self):
        self._callbacks = []

    def register_callback(self, callback):
        """Threshold 변경 시 호출될 콜백 등록"""
        self._callbacks.append(callback)

    def set_threshold(self, key, value):
        """Threshold 변경 및 콜백 호출"""
        self._thresholds[key] = value
        for callback in self._callbacks:
            callback(key, value)
```

**사용처**:
- FilterManager: Threshold 변경 시 필터 재초기화
- AdaptiveProbabilityFilter: Threshold 변경 시 패턴 재계산

#### 4. Strategy Pattern

**Optimization Strategies** (`src/optimization/`):
- `adaptive_filter_optimizer.py`: 필터 기준 동적 조정
- `enhanced_feedback_loop.py`: 예측 결과 피드백 반영
- `improved_auto_improvement_manager.py`: 자동 개선 관리

**교체 가능한 전략**:
```python
# main.py
if use_adaptive_optimizer:
    optimizer = AdaptiveFilterOptimizer()
else:
    optimizer = EnhancedFeedbackLoop()

optimizer.optimize()  # 공통 인터페이스
```

#### 5. Composite Pattern

**CompositeFilter** (`src/filters/base_filter.py`):
```python
class CompositeFilter(BaseFilter):
    def __init__(self, filters: List[BaseFilter]):
        self.filters = filters

    def apply_filter(self, combination: tuple) -> bool:
        return all(f.apply_filter(combination) for f in self.filters)
```

**사용 사례**:
- 여러 필터를 하나의 필터처럼 사용
- 필터 조합 계층화 (AND/OR 연산)

---

## 모듈 구조

### src/core/ (핵심 비즈니스 로직)

**책임**: 데이터 관리, 필터링, 임계값 관리

#### 주요 모듈

| 모듈 | 책임 | 패턴 | 의존성 |
|------|------|------|--------|
| `db_manager.py` | DB 연결 관리 (8 connections) | Singleton | specialized_databases |
| `filter_manager.py` | 16개 필터 병렬 실행 (12 workers) | Singleton (암시적) | FilterDB, ThresholdManager, BaseFilter |
| `integrated_filter_manager.py` | 적응형 + 정적 필터 통합 | Composite | FilterManager, AdaptiveProbabilityFilter |
| `threshold_manager.py` | 임계값 중앙 관리 | Singleton + Observer | 없음 (독립적) |
| `threshold_optimizer.py` | Bayesian 최적화 (Optuna) | Strategy | OptimizationCheckpointManager |
| `adaptive_probability_filter.py` | 확률 기반 필터링 | Singleton (암시적) | PatternManager, ThresholdManager |
| `pattern_manager.py` | 패턴 분석 및 저장 | None | PatternsDB |
| `specialized_databases.py` | 전문화된 DB 클래스 (4개) | None | db_manager |

#### 전문화된 데이터베이스

```python
# src/core/specialized_databases.py
class LottoNumbersDB:
    """당첨 번호 저장 (1186+ rounds)"""

class CombinationsDB:
    """필터링된 조합 캐시"""

class FilterDB:
    """필터 결과 저장 (16개 필터별)"""

class PatternsDB:
    """패턴 분석 결과 저장"""
```

### src/filters/ (필터 구현)

**책임**: 16개 필터 로직 구현

#### 필터 계층 구조

```
BaseFilter (ABC)
├── AverageFilter
├── SectionFilter
├── MatchFilter
├── OddEvenFilter
├── ConsecutiveFilter
├── SumRangeFilter
├── FixedStepFilter
├── LastDigitFilter
├── MaxGapFilter
├── MultipleFilter
├── TenSectionFilter
├── ArithmeticSequenceFilter
├── GeometricSequenceFilter
├── PrimeCompositeFilter
├── DigitSumFilter
└── DispersionFilter
```

#### 필터 분류

**Critical Filters** (항상 적용):
- odd_even: 홀짝 개수 (0개, 6개 제외)
- consecutive: 연속 번호 (최대 5개)
- sum_range: 합계 범위 (83-197)
- max_gap: 최대 간격 (최대 30)

**Relaxable Filters** (ML 예측 시 완화 가능):
- average: 평균 (14-32)
- prime_composite: 소수/합성수
- fixed_step: 등차 수열
- multiple: 배수 패턴
- ten_section: 10단위 구간
- digit_sum: 자릿수 합
- dispersion: 분산
- last_digit: 끝자리
- arithmetic_sequence: 등차수열
- geometric_sequence: 등비수열
- section: 구간 분포

### src/ml/ (머신러닝 모델)

**책임**: ML 예측 모델 구현

#### 모델 목록

| 모듈 | 알고리즘 | 입력 | 출력 |
|------|----------|------|------|
| `lstm_predictor.py` | LSTM (TensorFlow) | 50 rounds 시계열 | 6개 번호 예측 |
| `ensemble_predictor.py` | RF + XGBoost + NN | 특징 벡터 | 6개 번호 예측 |
| `super_ensemble.py` | 메타 앙상블 | 다중 모델 예측 | 최종 예측 |

#### 모델 캐싱

```python
# cache/models/
{model_name}_{data_hash}.pkl
{model_name}_{data_hash}_scaler.pkl
```

**캐시 무효화**: 7일 경과 또는 데이터 변경 시

### src/optimization/ (최적화 시스템)

**책임**: 성능 최적화 및 피드백 루프

| 모듈 | 책임 | 실행 주기 |
|------|------|-----------|
| `adaptive_filter_optimizer.py` | 필터 기준 동적 조정 | 5 rounds마다 |
| `enhanced_feedback_loop.py` | 예측 결과 피드백 반영 | 매 예측 후 |
| `improved_auto_improvement_manager.py` | 자동 개선 관리 | 매일 3AM |

### src/backtesting/ (백테스팅)

**책임**: 예측 시스템 성능 검증

**정식 버전**: `optimized_backtesting_framework.py`

**주요 기능**:
- 50 recent rounds 검증
- 보너스 번호 포함 2등 계산
- 병렬 처리 (10 workers)
- 성능 지표 저장 (performance_stats.db)

### src/probabilistic/ (확률 모델)

| 모듈 | 알고리즘 | 특징 |
|------|----------|------|
| `monte_carlo_simulator.py` | Monte Carlo | 6,000 simulations, 8 workers |
| `bayesian_inference.py` | Bayesian | 사후 확률 계산 |

### src/advanced/ (고급 분석)

**FractalPatternAnalyzer** (`fractal_pattern_analyzer.py`):
- 카오스 이론 기반 패턴 분석
- 프랙탈 차원 계산

### src/automation/ (자동화)

**AutoScheduler** (`auto_scheduler.py`):
- 새 회차 자동 감지
- 패턴/필터/ML 자동 업데이트
- 스케줄링 (매일 3AM)

### src/monitoring/ (모니터링)

**PerformanceDashboard** (`performance_dashboard.py`):
- 실시간 성능 지표 모니터링
- 메모리/CPU 사용률 추적

### src/utils/ (유틸리티)

| 모듈 | 책임 |
|------|------|
| `config_manager.py` | YAML 설정 로드 |
| `validators.py` | 입력 검증 |
| `memory_monitor.py` | 메모리 사용량 추적 |
| `logging_setup.py` | 로깅 설정 |
| `error_prevention_system.py` | 에러 예방 |

### src/scripts/ (스크립트)

**분류**:
- **Analysis**: `analyze_*.py` (필터/패턴/통계 분석)
- **Maintenance**: `clear_cache.py`, `optimize_databases.py`
- **Automation**: `background_optimizer.py`, `auto_threshold_optimizer.py`
- **Dashboard**: `enhanced_dashboard_v2.py` (port 5001)

---

## 데이터 흐름

### 전체 데이터 파이프라인

```
[1] 데이터 수집
DataCollector → 동행복권 API → DatabaseManager → lotto_numbers.db (1186+ rounds)

[2] 조합 생성
CombinationManager → 8,145,060 combinations → combinations.db (cache)

[3] 1단계 필터링 (확률 기반)
AdaptiveProbabilityFilter
├─ PatternManager (패턴 분석)
│  └─ patterns.db
├─ Threshold 검사 (1.0%)
└─ 결과: 8.14M → ~2M (75% 제외)

[4] 2단계 필터링 (정적 필터)
FilterManager (12 workers, 60K batch)
├─ [16 filters] × ProcessPoolExecutor
│  └─ FilterDB (결과 저장)
├─ ThresholdManager (임계값 적용)
└─ 결과: ~2M → ~300K (96.3% 총 제외)

[5] ML 예측 (병렬)
┌─ LSTMPredictor (시계열)
├─ EnsemblePredictor (RF+XGBoost+NN)
├─ MonteCarloSimulator (6K simulations, 8 workers)
├─ BayesianInference (확률 추론)
└─ FractalPatternAnalyzer (카오스 이론)
    ↓ weighted averaging
    결과: 5개 예측 조합

[6] ML-Filter 통합
generate_final_predictions_enhanced() (main.py)
├─ ML 예측 → 필터 검증 (1.0%)
├─ 실패 시 → Relaxed threshold (0.5%)
└─ 여전히 실패 → 유사 조합 매칭
    결과: ML inclusion rate ~8.5% (목표 15%)

[7] 백테스팅 검증
OptimizedBacktestingFramework (10 workers)
├─ 50 recent rounds 검증
├─ 보너스 번호 포함 2등 계산
└─ PerformanceStatsManager → performance_stats.db
    결과: 평균 일치 개수 (0.6-2.0 목표)

[8] 최적화 피드백 (백그라운드)
ThresholdOptimizer (별도 스레드)
├─ Optuna Bayesian Optimization (140 trials/cycle)
├─ OptimizationCheckpointManager (체크포인트 저장)
└─ 성능 저하 시 자동 롤백 (>10%)
    결과: 최적 파라미터 자동 적용

[9] 대시보드 표시
Flask Server (port 5001)
├─ 실시간 예측 결과
├─ 성능 지표 모니터링
└─ "새 예측 생성" 버튼
```

### 데이터베이스 구조

```
lotto_numbers.db
├─ winning_numbers (round, n1-n6, bonus, date)
└─ 1,186+ rounds

combinations.db
├─ filtered_combinations (combination, filter_pass)
└─ ~300K combinations

patterns.db (PatternsDB)
├─ odd_even_patterns
├─ consecutive_patterns
├─ match_patterns
└─ ... (16 filters × pattern types)

filters/*.db (FilterDB)
├─ match_filter.db
├─ odd_even_filter.db
└─ ... (16 filters)

predictions.db
├─ predictions (round, combination, model, confidence)
└─ 예측 히스토리

performance_stats.db
├─ model_performance (model, avg_matches, max_matches)
└─ filter_performance (filter, inclusion_rate, efficiency)

backtest_results.db
├─ backtest_results (round, predicted, actual, matches)
└─ 상세 백테스팅 히스토리
```

### 캐시 구조

```
cache/
├─ models/
│  ├─ lstm_{hash}.pkl
│  ├─ ensemble_{hash}.pkl
│  └─ ... (hash 기반 버전 관리, 1.7GB)
└─ filters/
   ├─ match_filter_{round}.pkl
   └─ ... (필터 결과 캐시)
```

---

## 의존성 관리

### 의존성 계층 (Dependency Layers)

```
[Application Layer]
    main.py
    └─ enhanced_dashboard_v2.py (Flask)
        ↓
[Orchestration Layer]
    IntegratedFilterManager
    └─ FilterManager
        └─ AdaptiveProbabilityFilter
            ↓
[Business Logic Layer]
    ├─ [16 Filters] (BaseFilter 상속)
    ├─ [5 ML Models]
    ├─ ThresholdOptimizer
    └─ SmartAutoLearning
        ↓
[Data Access Layer]
    DatabaseManager (Singleton)
    └─ specialized_databases (4 classes)
        ↓
[Infrastructure Layer]
    ├─ ProcessPoolExecutor (12 workers)
    ├─ TensorFlow/Keras (ML models)
    └─ Optuna (Bayesian optimization)
```

### 순환 참조 검증

**상태**: ✅ **없음** (2025-10-09 검증)

**검증 방법**:
```bash
python -c "from src.core import db_manager; from src.ml import lstm_predictor; print('OK')"
```

### 주요 의존성 체인

```
main.py
├─ DatabaseManager (Singleton)
│  └─ specialized_databases (LottoNumbersDB, CombinationsDB, FilterDB, PatternsDB)
├─ IntegratedFilterManager
│  ├─ FilterManager (12 workers)
│  │  ├─ BaseFilter (ABC)
│  │  │  └─ [16 concrete filters]
│  │  └─ ThresholdManager (Singleton + Observer)
│  └─ AdaptiveProbabilityFilter
│     └─ PatternManager
├─ ML Models
│  ├─ LSTMPredictor
│  ├─ EnsemblePredictor
│  ├─ MonteCarloSimulator
│  ├─ BayesianInference
│  └─ FractalPatternAnalyzer
└─ ThresholdOptimizer
   └─ OptimizationCheckpointManager
```

### 패키지 의존성 규칙

**허용**:
- `src.core` → `src.utils` (유틸리티 사용)
- `src.ml` → `src.utils` (유틸리티 사용)
- `src.filters` → `src.utils` (유틸리티 사용)
- `src.optimization` → `src.core` (core 컴포넌트 사용)
- `src.backtesting` → `src.core` + `src.ml` (검증 대상)

**금지**:
- ❌ `src.core` → `src.ml` (계층 위반)
- ❌ `src.utils` → `src.core` (순환 참조)
- ❌ `src.filters` → `src.core` (의존성 역전)

**예외**:
- `src.integration` (새 패키지, 향후 추가 예정)
  - core + ml 통합 허용
  - 예: `ultimate_prediction_system.py`

---

## 설정 파일 가이드

### 설정 파일 구조

**두 가지 설정 파일**:

1. **config.yaml** (시스템 전반 설정)
   - 위치: 프로젝트 루트
   - 변경 빈도: 낮음 (설치 후 거의 변경 없음)
   - 백업: 불필요

2. **configs/adaptive_filter_config.yaml** (적응형 필터 전용)
   - 위치: `configs/` 디렉토리
   - 변경 빈도: 높음 (주간 자동 업데이트)
   - 백업: 자동 생성 (`adaptive_filter_config_backup_*.yaml`)

### config.yaml (시스템 설정)

```yaml
# ============================================
# 시스템 전반 설정 (System-wide Configuration)
# - 설치 후 변경 빈도: 낮음
# - 백업 불필요
# ============================================

# 배치 크기 (조합 처리)
batch_size: 60000

# 데이터베이스 설정
database:
  batch_size: 60000
  connection_pool_size: 8
  max_batch_memory: 2000000000  # 2GB

# 필터 관리자 설정
filter_manager:
  max_workers: 12                # CPU 코어 수 (75% 활용)
  adaptive_batch_sizing: true
  memory_per_worker: 250000000   # 250MB

# 필터링 설정
filtering:
  batch_size: 60000
  chunk_size: 5000
  max_workers: 12
  use_parallel: true

# 필터 기준 (16개 필터)
filters:
  criteria:
    odd_even:
      excluded_counts: [0, 6]
    consecutive:
      max_consecutive: 5
    sum_range:
      min_sum: 83
      max_sum: 197
    # ... (16개 필터 기준)

  enabled_filters:
    - match
    - odd_even
    - consecutive
    # ... (16개 필터 활성화 목록)

  filter_efficiency:
    match: 0.05
    odd_even: 0.15
    # ... (필터별 효율성 지표)

# 로깅 설정
logging:
  file: logs/lotto_app.log
  level: INFO
  format: '%(asctime)s - %(levelname)s - %(message)s'
  max_size: 10485760  # 10MB
  backup_count: 5

# ML 모델 설정
ml_models:
  lstm:
    batch_size: 64
    epochs: 50
  ensemble:
    n_estimators: 100
    parallel_jobs: 4
  monte_carlo:
    n_simulations: 6000
    parallel_workers: 8
  backtesting:
    parallel_workers: 10
    chunk_size: 20

# 성능 설정
performance:
  auto_scaling: true
  cpu_threshold: 85
  memory_threshold: 80
  enable_monitoring: true
```

### adaptive_filter_config.yaml (필터 전용)

```yaml
# ============================================
# 적응형 필터 전용 설정 (Adaptive Filter Configuration)
# - 자동 업데이트: 주간 (SmartAutoLearning)
# - 백업 자동 생성: adaptive_filter_config_backup_*.yaml
# ============================================

# 전역 확률 임계값 (핵심 설정)
global_probability_threshold: 1.0  # 1.0% 미만 패턴 제외

# ML 완화 임계값
ml_relaxed_threshold: 0.5          # ML 예측 시 0.5%로 완화

# 적응형 필터 활성화 여부 (16개)
filters:
  match: true
  odd_even: true
  consecutive: true
  sum_range: true
  fixed_step: false
  last_digit: false
  max_gap: true
  section: false
  average: true
  multiple: true
  ten_section: true
  arithmetic: false
  geometric: false
  prime_composite: false
  digit_sum: false
  dispersion: false

# 동적 기준 (자동 조정됨)
dynamic_criteria:
  odd_even:
    excluded_counts: [0, 6]
  consecutive:
    max_consecutive: 5
  sum_range:
    min_sum: 50
    max_sum: 230
  # ... (16개 필터 동적 기준)

# 적응형 옵션
adaptive_options:
  auto_learning: true
  update_frequency: 5           # 5 rounds마다 업데이트
  min_threshold: 0.3
  max_threshold: 3.0
  safety_mode: true             # 안전 모드 (롤백 활성화)

# 백테스팅 목표
backtesting_targets:
  min_average_matches: 0.6
  max_average_matches: 2.0
  target_inclusion_rate: 0.25
  winning_probability_weight: 0.7

# ML 통합 설정
ml_integration:
  ml_weight: 0.6
  ensemble_confidence_threshold: 0.2
  ml_bypass_filters: 15          # ML 예측 시 완화 가능한 필터 수

# 로깅 설정 (필터 전용)
logging:
  log_excluded_patterns: true
  statistics_interval: 25
  verbosity: INFO

# 성능 설정 (필터 전용)
performance:
  batch_size: 10000
  enable_cache: true
  cache_ttl: 1800
  max_workers: 14
  parallel_processing: true
```

### 설정 로딩 예시

```python
from src.utils.config_manager import ConfigManager

# 시스템 설정 로드
system_config = ConfigManager.load_system_config()
batch_size = system_config['batch_size']
workers = system_config['filter_manager']['max_workers']

# 적응형 필터 설정 로드
filter_config = ConfigManager.load_adaptive_filter_config()
threshold = filter_config['global_probability_threshold']
ml_threshold = filter_config['ml_relaxed_threshold']

# 필터 기준 가져오기
criteria = ConfigManager.get_filter_criteria()
odd_even_criteria = criteria['odd_even']

# 적응형 필터 활성화 여부
enabled = ConfigManager.get_adaptive_filters_status()
is_match_enabled = enabled['match']
```

---

## 성능 최적화

### 병렬 처리 전략

#### FilterManager (12 workers)

```python
# src/core/filter_manager.py
class FilterManager:
    def __init__(self, db_manager, max_workers=12):
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.batch_size = 60000  # 60K 조합/배치
```

**최적화 포인트**:
- CPU 코어: 16개 → 12 workers (75% 활용)
- 배치 크기: 60,000 조합 (31GB 메모리 최적화)
- Worker 메모리: 250MB/worker
- 적응형 배치 크기: 메모리 사용량에 따라 동적 조정

#### MonteCarloSimulator (8 workers)

```python
# src/probabilistic/monte_carlo_simulator.py
class MonteCarloSimulator:
    def __init__(self, n_simulations=6000, parallel_workers=8):
        self.n_simulations = n_simulations
        self.parallel_workers = parallel_workers
        self.batch_size = 750  # 6000 / 8 = 750
```

#### OptimizedBacktestingFramework (10 workers)

```python
# src/backtesting/optimized_backtesting_framework.py
class OptimizedBacktestingFramework:
    def __init__(self, parallel_workers=10, chunk_size=20):
        self.parallel_workers = parallel_workers
        self.chunk_size = chunk_size
```

### 캐싱 전략

#### 1. 모델 캐싱

**위치**: `cache/models/`

**캐싱 기준**:
```python
import hashlib

def get_cache_key(model_name, data):
    data_hash = hashlib.md5(str(data).encode()).hexdigest()
    return f"{model_name}_{data_hash}"
```

**무효화 조건**:
- 7일 경과
- 데이터 변경 (hash 불일치)

#### 2. 필터 결과 캐싱

**위치**: `cache/filters/`

**캐싱 기준**:
```python
cache_key = f"{filter_name}_{round_num}.pkl"
```

**무효화 조건**:
- 새 회차 발생
- Threshold 변경

### 메모리 관리

#### MemoryMonitor

```python
# src/utils/memory_monitor.py
import psutil

class MemoryMonitor:
    def __init__(self):
        self.process = psutil.Process()

    def get_memory_usage(self):
        return self.process.memory_info().rss / (1024 * 1024)  # MB
```

**임계값**:
- 경고: 80% (배치 크기 축소)
- 위험: 90% (작업 일시 중지)

### 데이터베이스 최적화

#### Connection Pooling

```python
# src/core/db_manager.py
class DatabaseManager:
    def __init__(self, pool_size=8):
        self.pool = [sqlite3.connect('lotto_numbers.db') for _ in range(pool_size)]
```

#### Batch Insert

```python
def batch_insert(self, data, batch_size=1000):
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        cursor.executemany(query, batch)
```

---

## 확장 가이드

### 새 필터 추가

#### 1단계: BaseFilter 상속

```python
# src/filters/my_new_filter.py
from src.filters.base_filter import BaseFilter
from typing import List

class MyNewFilter(BaseFilter):
    """새 필터 설명"""

    def __init__(self, db_manager, **kwargs):
        super().__init__(db_manager)
        self.criteria = kwargs.get('criteria', {})

    def apply_filter(self, combination: tuple) -> bool:
        """
        필터 로직 구현

        Args:
            combination: (n1, n2, n3, n4, n5, n6) 튜플

        Returns:
            True: 조합 통과
            False: 조합 제외
        """
        # 필터 로직 구현
        return True

    def apply(self, combinations: List[tuple]) -> List[tuple]:
        """배치 필터링 (병렬 처리)"""
        return [c for c in combinations if self.apply_filter(c)]
```

#### 2단계: config.yaml 업데이트

```yaml
filters:
  criteria:
    my_new_filter:
      param1: value1
      param2: value2

  enabled_filters:
    - match
    - odd_even
    - my_new_filter  # 추가

  filter_efficiency:
    my_new_filter: 0.15  # 예상 효율성
```

#### 3단계: FilterManager 등록

```python
# src/core/filter_manager.py
from src.filters.my_new_filter import MyNewFilter

class FilterManager:
    def __init__(self, db_manager):
        self.filters = {
            'match': MatchFilter(db_manager),
            'odd_even': OddEvenFilter(db_manager),
            'my_new_filter': MyNewFilter(db_manager),  # 추가
            # ...
        }
```

#### 4단계: 테스트

```python
# tests/test_my_new_filter.py
import pytest
from src.filters.my_new_filter import MyNewFilter
from src.core.db_manager import DatabaseManager

def test_my_new_filter():
    db = DatabaseManager()
    filter = MyNewFilter(db)

    # 통과해야 하는 조합
    assert filter.apply_filter((1, 2, 3, 4, 5, 6)) == True

    # 제외되어야 하는 조합
    assert filter.apply_filter((1, 1, 1, 1, 1, 1)) == False
```

### 새 ML 모델 추가

#### 1단계: 모델 클래스 생성

```python
# src/ml/my_new_model.py
import numpy as np
from typing import List, Tuple

class MyNewModel:
    """새 ML 모델 설명"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.model = None

    def train(self, X, y):
        """모델 학습"""
        # 학습 로직 구현
        pass

    def predict(self, X) -> np.ndarray:
        """예측"""
        # 예측 로직 구현
        return np.array([[1, 2, 3, 4, 5, 6]])

    def generate_predictions(self, n_predictions=5) -> List[Tuple[int, ...]]:
        """예측 조합 생성"""
        predictions = []
        for _ in range(n_predictions):
            pred = self.predict(None)
            predictions.append(tuple(sorted(pred[0])))
        return predictions
```

#### 2단계: config.yaml 업데이트

```yaml
ml_models:
  my_new_model:
    param1: value1
    param2: value2
```

#### 3단계: main.py 통합

```python
# main.py
try:
    from src.ml.my_new_model import MyNewModel
    USE_MY_NEW_MODEL = True
except ImportError:
    USE_MY_NEW_MODEL = False

def generate_ml_predictions():
    predictions = []

    # 기존 모델
    if USE_LSTM:
        predictions.extend(lstm_predictor.generate_predictions())

    # 새 모델 추가
    if USE_MY_NEW_MODEL:
        my_model = MyNewModel(db_manager)
        predictions.extend(my_model.generate_predictions())

    return predictions
```

### 새 최적화 전략 추가

#### 1단계: Strategy 클래스 생성

```python
# src/optimization/my_new_optimizer.py
class MyNewOptimizer:
    """새 최적화 전략 설명"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def optimize(self):
        """최적화 실행"""
        # 최적화 로직 구현
        pass

    def evaluate(self):
        """성능 평가"""
        # 평가 로직 구현
        return {'metric': 0.85}
```

#### 2단계: main.py 통합

```python
# main.py
from src.optimization.my_new_optimizer import MyNewOptimizer

def run_background_optimization():
    optimizer = MyNewOptimizer(db_manager)
    optimizer.optimize()
    results = optimizer.evaluate()
    logging.info(f"최적화 결과: {results}")
```

---

## 부록

### A. 주요 상수

```python
# src/utils/constants.py
class LottoConstants:
    MIN_NUMBER = 1
    MAX_NUMBER = 45
    NUMBERS_PER_DRAW = 6
    TOTAL_COMBINATIONS = 8145060
```

### B. 데이터베이스 스키마

```sql
-- lotto_numbers.db
CREATE TABLE winning_numbers (
    round INTEGER PRIMARY KEY,
    n1 INTEGER,
    n2 INTEGER,
    n3 INTEGER,
    n4 INTEGER,
    n5 INTEGER,
    n6 INTEGER,
    bonus INTEGER,
    draw_date DATE
);

-- predictions.db
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER,
    combination TEXT,
    model TEXT,
    confidence REAL,
    created_at TIMESTAMP
);

-- performance_stats.db
CREATE TABLE model_performance (
    model TEXT PRIMARY KEY,
    avg_matches REAL,
    max_matches INTEGER,
    total_predictions INTEGER,
    updated_at TIMESTAMP
);
```

### C. 주요 알고리즘 복잡도

| 작업 | 시간 복잡도 | 공간 복잡도 |
|------|-------------|-------------|
| 조합 생성 | O(C(45, 6)) = O(8.14M) | O(8.14M) |
| 필터링 (1개) | O(n) | O(1) |
| 필터링 (16개) | O(16n) | O(n) |
| LSTM 예측 | O(seq_len × features) | O(model_size) |
| Ensemble 예측 | O(n_estimators × n_samples) | O(model_size) |
| Monte Carlo | O(n_simulations × 6) | O(n_simulations) |

### D. 성능 벤치마크

| 작업 | 시간 (초) | 메모리 (MB) |
|------|-----------|-------------|
| 데이터 수집 | 5-10 | 50 |
| 조합 생성 | 60-120 | 500 |
| 필터링 (8.14M → 300K) | 180-300 | 2000 |
| LSTM 학습 | 300-600 | 1000 |
| Ensemble 학습 | 120-240 | 500 |
| Monte Carlo (6K) | 60-120 | 300 |
| 백테스팅 (50 rounds) | 30-60 | 200 |
| 전체 파이프라인 (첫 실행) | 600-900 | 3000 |
| 전체 파이프라인 (캐시) | 120-180 | 1000 |

---

**문서 버전**: 1.0
**최종 업데이트**: 2025-10-09
**작성자**: Claude (Architect Persona)
**상태**: Draft (검토 필요)
