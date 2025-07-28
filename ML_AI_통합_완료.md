# ML/AI 통합 완료 🎉

## 통합된 기능들

### 1. **LSTM 시계열 예측** (`--lstm`)
- 3층 LSTM 네트워크 (128→64→32 유닛)
- 과거 50회차 패턴 학습
- 자동 모델 저장/로드

### 2. **앙상블 모델** (`--ensemble`)
- Random Forest (200 trees)
- XGBoost (200 estimators)
- Neural Network (4층)
- 가중 투표 방식

### 3. **Monte Carlo 시뮬레이션** (`--monte-carlo`)
- 10,000회 병렬 시뮬레이션
- 확률 행렬 + 전이 행렬
- 최적 조합 추출

### 4. **베이지안 추론** (`--bayesian`)
- 디리클레/베타 분포
- 사전→사후 확률 업데이트
- 신뢰구간 계산

### 5. **프랙탈 패턴 분석** (`--fractal`)
- Box-counting/Higuchi 차원
- 리아푸노프 지수
- 카오스 메트릭

### 6. **동적 필터 모니터링** (`--dynamic-filter`)
- 실시간 성능 추적
- 적응형 가중치 조정
- 성능 보고서 생성

### 7. **ML 예측 필터**
- 앙상블 모델 기반 필터링
- 자동으로 필터 체인에 통합

## 실행 방법

### 기본 실행 (모든 기능 포함)
```bash
python main.py
```

### ML/AI 분석만 실행
```bash
python main.py --ml-only
```

### ML/AI 제외하고 실행
```bash
python main.py --skip-ml
```

### 특정 ML 기능만 선택
```bash
python main.py --lstm --no-ensemble --no-monte-carlo
```

### 예측 개수 조정
```bash
python main.py --predictions 10
```

## 테스트

통합 테스트 실행:
```bash
python test_ml_integration.py
```

## 필요한 패키지

```bash
pip install tensorflow scikit-learn xgboost scipy matplotlib seaborn pywavelets
```

## 생성되는 파일들

- `models/lstm_lotto_predictor.h5` - LSTM 모델
- `models/ensemble/` - 앙상블 모델들
- `monte_carlo_results.json` - MC 시뮬레이션 결과
- `bayesian_beliefs.json` - 베이지안 신념 상태
- `bayesian_beliefs.png` - 베이지안 시각화
- `fractal_analysis.json` - 프랙탈 분석 결과
- `fractal_analysis.png` - 프랙탈 시각화
- `filter_performance_report.json` - 필터 성능 보고서

## 주의사항

1. 첫 실행시 ML 모델 학습으로 시간이 걸릴 수 있습니다.
2. TensorFlow가 없으면 LSTM이 작동하지 않습니다.
3. 최소 50개 이상의 과거 데이터가 필요합니다.

## 실행 예제

```bash
# 데이터 수집 건너뛰고 ML 포함 실행
python main.py --skip-fetch

# 빠른 테스트 (패턴 분석도 건너뛰기)
python main.py --skip-fetch --skip-patterns --predictions 3

# 특정 ML만 실행
python main.py --ml-only --lstm --ensemble
```

모든 ML/AI 기능이 main.py에 통합되어 단일 명령으로 실행 가능합니다! 🚀