# 입력 데이터 부족 문제 해결 보고서

## 문제 설명
**증상**: "입력 데이터 부족: 1개 (최소 필요: 10개)" 경고 메시지 발생

**발생 시점**: 백테스팅 초기 라운드 실행 시

## 원인 분석

### 1. 근본 원인
- `OptimizedBacktestingFramework`에서 백테스팅 초기 라운드 테스트 시 학습 데이터 부족
- 예: 라운드 2를 테스트할 때 라운드 1의 데이터만 사용 가능 (1개 데이터)

### 2. 문제 발생 경로
```python
# optimized_backtesting_framework.py (수정 전)
train_start = max(1, test_round - window_size)  # test_round=2, window_size=100 -> train_start=1
train_end = test_round - 1                      # test_round=2 -> train_end=1
# 결과: train_data에 라운드 1만 포함 (1개 데이터)
```

### 3. LSTM 예측기 반응
```python
# lstm_predictor.py
if available_length >= 10:  # 최소 10개 필요
    # 정상 처리
else:
    logging.warning(f"입력 데이터 부족: {len(recent_numbers)}개 (최소 필요: 10개)")
    return self._random_predictions(num_predictions)
```

## 해결 방법

### 1. OptimizedBacktestingFramework 수정 (Line 169-177)
```python
# 최소 10개의 데이터가 있는지 확인
if train_end - train_start + 1 < 10:
    # 최소 10개 데이터를 확보하기 위해 train_start 조정
    train_start = max(1, train_end - 9)

# 여전히 데이터가 부족하면 이 라운드는 건너뛰기
if train_end - train_start + 1 < 10:
    logging.debug(f"라운드 {test_round}: 학습 데이터 부족 ({train_end - train_start + 1}개)")
    continue
```

### 2. LSTMPredictor 추가 검증 (Line 366-369)
```python
# 입력 데이터 검증
if not recent_numbers or len(recent_numbers) == 0:
    logging.warning("입력 데이터가 없습니다. 랜덤 예측을 반환합니다.")
    return self._random_predictions(num_predictions)
```

## 수정 파일
1. `src/backtesting/optimized_backtesting_framework.py`
   - 최소 데이터 개수 검증 로직 추가
   - 데이터 부족 시 라운드 건너뛰기

2. `src/ml/lstm_predictor.py`
   - 빈 데이터 입력 시 안전한 처리
   - 명확한 경고 메시지

## 테스트 결과
- ✅ "입력 데이터 부족: 1개" 경고 제거됨
- ✅ 백테스팅이 최소 10개 데이터 확보 후 실행
- ✅ 데이터 부족한 초기 라운드는 자동으로 건너뜀
- ✅ LSTM 예측기가 빈 데이터도 안전하게 처리

## 성능 영향
- 백테스팅 초기 라운드(1-10)는 건너뛰므로 더 정확한 결과
- 불필요한 경고 메시지 제거로 로그 가독성 향상
- 예외 상황에서도 안정적인 동작 보장

## 검증 스크립트
`tests/test_data_shortage_fix.py` - 다양한 데이터 크기에 대한 처리 검증

---
*작성일: 2025-08-17*
*해결 완료*