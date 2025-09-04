# 📚 로또 시스템 용어 사전 (Terminology Dictionary)

## 🎯 max_match란?
**번호 일치 필터(match_filter)**의 핵심 파라미터입니다.
- `max_match = 4`: 과거 당첨번호와 **4개 이상 일치**하는 조합을 제외
- 예: 과거 당첨번호 [1,2,3,4,5,6]과 새 조합 [1,2,3,4,7,8]은 4개 일치로 제외됨

---

## 📋 필터 용어 통일 매핑

### 1️⃣ 번호 일치 필터 (match_filter)
- **영어명**: MatchFilter, match_filter
- **한글명**: 번호 일치 필터
- **설명**: 과거 당첨번호와의 일치 개수를 검사
- **주요 파라미터**: 
  - `max_match`: 최대 일치 허용 개수
- **로그 표시**: "번호 일치 패턴 분포"

### 2️⃣ 홀짝 분포 필터 (odd_even_filter)
- **영어명**: OddEvenFilter, odd_even_filter
- **한글명**: 홀짝 분포 필터
- **설명**: 홀수/짝수 개수 분포 검사
- **주요 파라미터**: 
  - `excluded_counts`: 제외할 홀수 개수 리스트
- **로그 표시**: "홀짝 분포"

### 3️⃣ 연속 번호 필터 (consecutive_filter)
- **영어명**: ConsecutiveFilter, consecutive_filter
- **한글명**: 연속 번호 필터
- **설명**: 연속된 번호의 개수 제한
- **주요 파라미터**: 
  - `max_consecutive`: 최대 연속 번호 개수
- **로그 표시**: "연속 번호"

### 4️⃣ 합계 범위 필터 (sum_range_filter)
- **영어명**: SumRangeFilter, sum_range_filter
- **한글명**: 합계 범위 필터
- **설명**: 6개 번호의 합계 범위 제한
- **주요 파라미터**: 
  - `min_sum`: 최소 합계
  - `max_sum`: 최대 합계
- **로그 표시**: "번호 합계 범위"

### 5️⃣ 고정 간격 필터 (fixed_step_filter)
- **영어명**: FixedStepFilter, fixed_step_filter
- **한글명**: 고정 간격 필터
- **설명**: 일정한 간격을 가진 번호들 제외
- **주요 파라미터**: 
  - `steps_to_exclude`: 제외할 간격 리스트
  - `required_matches`: 필요한 매칭 수
- **로그 표시**: "고정 간격 패턴"

### 6️⃣ 끝자리 분포 필터 (last_digit_filter)
- **영어명**: LastDigitFilter, last_digit_filter
- **한글명**: 끝자리 분포 필터
- **설명**: 끝자리 숫자의 분포 검사
- **주요 파라미터**: 
  - `min_same_last_digits`: 동일 끝자리 최소 개수
- **로그 표시**: "끝자리 분포"

### 7️⃣ 최대 간격 필터 (max_gap_filter)
- **영어명**: MaxGapFilter, max_gap_filter
- **한글명**: 최대 간격 필터
- **설명**: 인접 번호 간 최대 간격 제한
- **주요 파라미터**: 
  - `max_allowed_gap`: 허용 최대 간격
- **로그 표시**: "최대 간격"

### 8️⃣ 구간 분포 필터 (section_filter)
- **영어명**: SectionFilter, section_filter
- **한글명**: 구간 분포 필터 (15구간)
- **설명**: 1-45를 15개 구간으로 나눠 분포 검사
- **주요 파라미터**: 
  - `max_numbers_per_section`: 구간당 최대 번호 개수
- **로그 표시**: "구간별 분포"

### 9️⃣ 평균값 필터 (average_filter)
- **영어명**: AverageFilter, average_filter
- **한글명**: 평균값 필터
- **설명**: 6개 번호의 평균값 범위 제한
- **주요 파라미터**: 
  - `min_average`: 최소 평균
  - `max_average`: 최대 평균
- **로그 표시**: "평균값 범위"

### 🔟 배수 패턴 필터 (multiple_filter)
- **영어명**: MultipleFilter, multiple_filter
- **한글명**: 배수 패턴 필터
- **설명**: 특정 숫자의 배수 개수 제한
- **주요 파라미터**: 
  - `multiples`: 각 배수별 제외 개수
- **로그 표시**: "배수 패턴"

### 1️⃣1️⃣ 10구간 분포 필터 (ten_section_filter)
- **영어명**: TenSectionFilter, ten_section_filter
- **한글명**: 10구간 분포 필터
- **설명**: 1-45를 10개 구간으로 나눠 분포 검사
- **주요 파라미터**: 
  - `section_limits`: 각 구간별 제한
- **로그 표시**: "10구간 분포"

### 1️⃣2️⃣ 등차수열 필터 (arithmetic_sequence_filter)
- **영어명**: ArithmeticSequenceFilter
- **한글명**: 등차수열 필터
- **설명**: 등차수열 패턴 제외
- **주요 파라미터**: 
  - `min_sequence`: 최소 수열 길이
  - `excluded_lengths`: 제외할 수열 길이
- **로그 표시**: "등차수열 패턴"

### 1️⃣3️⃣ 등비수열 필터 (geometric_sequence_filter)
- **영어명**: GeometricSequenceFilter
- **한글명**: 등비수열 필터
- **설명**: 등비수열 패턴 제외
- **주요 파라미터**: 
  - `min_sequence`: 최소 수열 길이
  - `excluded_lengths`: 제외할 수열 길이
- **로그 표시**: "등비수열 패턴"

### 1️⃣4️⃣ 소수/합성수 필터 (prime_composite_filter)
- **영어명**: PrimeCompositeFilter
- **한글명**: 소수/합성수 분포 필터
- **설명**: 소수와 합성수 개수 분포 검사
- **주요 파라미터**: 
  - `min_allowed`: 최소 소수 개수
  - `max_allowed`: 최대 소수 개수
- **로그 표시**: "소수/합성수 분포"

### 1️⃣5️⃣ 자릿수 합계 필터 (digit_sum_filter)
- **영어명**: DigitSumFilter, digit_sum_filter
- **한글명**: 자릿수 합계 필터
- **설명**: 각 번호의 자릿수 합계 검사
- **주요 파라미터**: 
  - `min_digit_sum`: 최소 자릿수 합
  - `max_digit_sum`: 최대 자릿수 합
- **로그 표시**: "자릿수 합계"

### 1️⃣6️⃣ 분산도 필터 (dispersion_filter)
- **영어명**: DispersionFilter, dispersion_filter
- **한글명**: 분산도 필터
- **설명**: 번호들의 분산도와 표준편차 검사
- **주요 파라미터**: 
  - `min_variance`: 최소 분산
  - `max_variance`: 최대 분산
- **로그 표시**: "번호 분산도"

### 1️⃣7️⃣ ML 예측 필터 (ml_prediction_filter)
- **영어명**: MLPredictionFilter
- **한글명**: 머신러닝 예측 필터
- **설명**: ML 모델의 예측 확률 기반 필터링
- **주요 파라미터**: 
  - `threshold`: 예측 확률 임계값
- **로그 표시**: "ML 예측"

---

## 🔧 통일된 로그 출력 형식

### 필터 시작/종료
```python
# 현재 (혼용)
"[OddEven] 홀짝 필터 완료"
"[Match 필터] 확률 기반 설정"

# 개선안 (통일)
"[홀짝 분포] 필터 완료"
"[번호 일치] 확률 기반 설정"
```

### 필터 결과
```python
# 현재 (혼용)
"match 필터: 100 → 20 (80% 제외)"
"odd_even: 20 → 18 (10% 제외)"

# 개선안 (통일)
"번호 일치: 100 → 20 (80% 제외)"
"홀짝 분포: 20 → 18 (10% 제외)"
```

### 오류 메시지
```python
# 현재 (혼용)
"번호 일치 필터링 중 오류 발생"
"Error in odd_even filter"

# 개선안 (통일)
"번호 일치 필터링 중 오류 발생"
"홀짝 분포 필터링 중 오류 발생"
```

---

## 📊 공통 용어

| 영어 | 한글 | 설명 |
|------|------|------|
| combination | 조합 | 6개 번호 묶음 |
| round | 회차 | 추첨 회차 번호 |
| winning numbers | 당첨번호 | 실제 당첨된 번호 |
| threshold | 임계값 | 필터 기준값 |
| distribution | 분포 | 패턴의 분포 상태 |
| pattern | 패턴 | 번호 배열 패턴 |
| criteria | 기준값 | 필터 판단 기준 |
| exclude | 제외 | 조건 미충족으로 제거 |
| filter | 필터 | 조건 검사기 |
| batch | 배치 | 묶음 처리 단위 |
| chunk | 청크 | 작업 분할 단위 |

---

## 🎨 표시 권장사항

### 1. 사용자 인터페이스
- **한글 우선**: "번호 일치 필터"
- **필요시 영어 병기**: "번호 일치 필터(match)"

### 2. 로그 출력
- **한글 통일**: "[번호 일치] 8,090개 제외"
- **오류시 영어 포함**: "번호 일치 필터(match_filter) 오류"

### 3. 설정 파일
- **영어 유지**: `match_filter`, `odd_even_filter` (기술적 호환성)
- **주석에 한글**: `# 번호 일치 필터 설정`

### 4. 코드 내부
- **클래스명 영어**: `MatchFilter`, `OddEvenFilter`
- **주석 한글**: `# 번호 일치 패턴 검사`
- **로그 메시지 한글**: `"번호 일치 필터 완료"`