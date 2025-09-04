
# main.py 수정 가이드

## 1단계: ML/AI 예측 블록 이동
- 현재 위치: 674-942행
- 이동 위치: 1060행 (필터링 완료 후)

## 2단계: ML 입력 데이터 변경
```python
# 변경 전:
winning_numbers = db_manager.get_all_winning_numbers()  # 814만개

# 변경 후:
filtered_combinations = filter_manager.get_filtered_combinations()  # 20만개
winning_numbers = filtered_combinations
```

## 3단계: 백테스팅 위치 조정
- 필터링 + ML 통합 후에 실행되도록 조정

## 4단계: 실행 순서 확인
1. 초기화
2. 데이터 수집
3. 패턴 분석
4. ✅ 필터링 (우선)
5. ✅ ML/AI 예측 (필터링 후)
6. 백테스팅
7. 피드백 루프
8. 실시간 학습
9. 최종 예측
