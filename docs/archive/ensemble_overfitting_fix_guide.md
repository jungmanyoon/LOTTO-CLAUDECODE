# ENSEMBLE 모델 과적합 문제 해결 가이드

**작성일**: 2025-08-18 18:50  
**작성자**: Claude Code SuperClaude

## 🔴 문제 상황

### 백테스팅 결과의 이상 현상
- **ENSEMBLE 모델**: 평균 2.57개 일치, 3개 이상 51.76%, 6개 일치 3건
- **LSTM 모델**: 평균 0.65개 일치 (정상)
- **Monte Carlo**: 평균 0.76개 일치 (정상)

### 실제 사례 분석
**1135회차 실제 당첨번호**: `1, 6, 13, 19, 21, 33`

**ENSEMBLE 모델 예측**:
1. `[1, 6, 13, 19, 22, 33]` → 5개 일치!
2. `[1, 6, 13, 14, 19, 21]` → 5개 일치!

이는 **통계적으로 불가능한 수준**입니다.

## 🔍 원인 분석

### 1. 과적합 (Overfitting)
- Random Forest와 XGBoost는 학습 데이터를 "암기"할 수 있음
- 특히 데이터가 적을 때 심각함

### 2. 백테스팅 방식의 문제
```python
# 현재 백테스팅 프로세스
for each round:
    1. 모델 재학습 (1035-1134 데이터)
    2. 바로 예측 (1135 회차)
    3. 모델이 방금 본 패턴을 그대로 반복
```

### 3. 모델 파라미터 문제
현재 설정:
- `n_estimators=100` (너무 많음)
- `max_depth=None` (제한 없음 → 과적합)
- `min_samples_split=2` (너무 작음)

## ✅ 해결 방안

### 방안 1: 모델 파라미터 조정 (권장)

**수정 파일**: `src/ml/ensemble_predictor.py`

```python
# 기존 (과적합 발생)
RandomForestClassifier(
    n_estimators=100,
    max_depth=None,
    min_samples_split=2,
    min_samples_leaf=1
)

# 개선 (과적합 방지)
RandomForestClassifier(
    n_estimators=50,      # 줄임
    max_depth=5,          # 깊이 제한
    min_samples_split=10, # 증가
    min_samples_leaf=5,   # 증가
    max_features='sqrt'   # 특징 제한
)
```

### 방안 2: 백테스팅 방식 개선

**수정 파일**: `src/backtesting/optimized_backtesting_framework.py`

```python
# 옵션 1: 모델을 한 번만 학습
model = train_once(data_until_1100)
for round in [1101, 1102, ...]:
    predict(round)  # 재학습 없이 예측만

# 옵션 2: 주기적 재학습 (매 10회차)
if round % 10 == 0:
    retrain_model()
```

### 방안 3: 교차 검증 추가

```python
# 과적합 체크
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

if train_score - test_score > 0.2:  # 20% 이상 차이
    logging.warning("과적합 감지!")
    # 파라미터 조정 또는 조기 종료
```

## 📊 기대 효과

개선 후 예상 성능:
- **평균 일치**: 0.8~1.2개 (현실적)
- **3개 이상 일치율**: 2~5% (정상 범위)
- **신뢰도**: 최대 50%로 제한

## 🚀 적용 방법

### 즉시 적용 (임시)
```bash
# 수정된 모델 사용
python src/ml/ensemble_predictor_fixed.py
```

### 영구 적용
1. 기존 모델 백업
```bash
cp src/ml/ensemble_predictor.py src/ml/ensemble_predictor.backup
```

2. 수정 버전 적용
```bash
cp src/ml/ensemble_predictor_fixed.py src/ml/ensemble_predictor.py
```

3. 캐시 삭제 (중요!)
```bash
rm cache/models/ensemble_*.pkl
```

4. 재실행
```bash
python main.py
```

## ⚠️ 주의사항

1. **캐시 삭제 필수**: 과적합된 모델 캐시를 반드시 삭제
2. **성능 저하 예상**: 정상적인 성능(낮음)으로 돌아옴
3. **백테스팅 재실행**: 새 모델로 다시 검증 필요

## 📈 검증 방법

```python
# 검증 스크립트
def verify_model_performance():
    """모델 성능이 정상 범위인지 확인"""
    
    # 백테스팅 실행
    results = run_backtest()
    
    # 성능 체크
    avg_matches = results['ensemble']['avg_matches']
    
    if avg_matches > 1.5:
        print("⚠️ 여전히 과적합 가능성!")
    elif avg_matches < 0.5:
        print("⚠️ 성능이 너무 낮음!")
    else:
        print("✅ 정상 범위 (0.5~1.5개)")
```

## 💡 장기 개선 방안

1. **더 많은 데이터 수집**
   - 최소 200회차 이상 데이터 확보
   - 데이터 증강 기법 적용

2. **앙상블 전략 변경**
   - 단순 평균 대신 가중 평균
   - 신뢰도 기반 조합

3. **새로운 모델 도입**
   - LightGBM (과적합 방지 기능)
   - CatBoost (자동 정규화)

## 결론

ENSEMBLE 모델의 비정상적인 성능은 **과적합**이 원인입니다. 제안된 해결 방안을 적용하면 정상적인 성능으로 돌아올 것입니다. 

**기억하세요**: 로또 예측에서 평균 1개 이상 맞추는 것도 실제로는 매우 어렵습니다. 높은 성능은 대부분 버그나 과적합의 신호입니다.