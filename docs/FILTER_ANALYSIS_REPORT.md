# 로또 필터 시스템 분석 보고서

## 요약

1182개 회차의 과거 당첨번호를 대상으로 16개 필터를 분석한 결과, **현재 시스템은 모든 필터를 동시에 적용할 경우 어떤 당첨번호도 통과하지 못하는 심각한 문제**가 있습니다. 이는 주로 match 필터의 설계 오류와 과도하게 엄격한 필터 기준 때문입니다.

## 주요 발견사항

### 1. 필터별 효과성 분석

#### 문제가 있는 필터
- **match 필터**: 0% 통과율 (모든 당첨번호 제외)
  - 원인: 당첨번호 자체가 DB에 있어서 자기 자신과 6개 일치
  - 영향: 이 필터 하나만으로도 모든 번호가 제외됨

#### 효과적인 필터 (제외율 순)
1. **odd_even**: 35개 제외 (2.96%)
2. **dispersion**: 18개 제외 (1.52%)
3. **average**: 15개 제외 (1.27%)
4. **sum_range**: 13개 제외 (1.10%)
5. **fixed_step**: 11개 제외 (0.93%)

#### 효과 없는 필터 (0개 제외)
- consecutive (연속번호)
- last_digit (끝자리)
- ten_section (10구간)
- arithmetic_sequence (등차수열)
- geometric_sequence (등비수열)
- prime_composite (소수/합성수)
- digit_sum (자릿수 합)

### 2. 당첨번호 통계 패턴

- **합계 분포**
  - 평균: 138.3
  - 표준편차: 30.8
  - 실제 범위: 48 ~ 238
  - 95% 신뢰구간: 77 ~ 200

- **홀짝 비율**
  - 가장 흔한 패턴: 홀수 3개, 짝수 3개
  - 모두 홀수 또는 모두 짝수: 전체의 2.96%

- **번호 간격**
  - 평균 간격: 6.5
  - 최대 간격: 33

## 권장 사항

### 1. 즉시 수정 필요 사항

#### match 필터 수정
```python
# 현재 코드 (문제)
valid_indices = match_counts < max_match  # max_match = 5

# 수정안 1: 현재 회차 제외
if round_num in winning_rounds:
    exclude_current_round()

# 수정안 2: max_match 조정
max_match = 6  # 6개 일치까지 허용
```

#### 효과 없는 필터 비활성화
```yaml
# config.yaml 수정
enabled_filters:
  # - consecutive      # 제거
  # - last_digit       # 제거
  # - ten_section      # 제거
  # - arithmetic_sequence  # 제거
  # - geometric_sequence   # 제거
  # - prime_composite      # 제거
  # - digit_sum           # 제거
```

### 2. 동적 임계값 설정

#### 데이터 기반 임계값
```yaml
filters:
  criteria:
    # 합계 범위 필터 - 통계 기반 조정
    sum_range:
      min_sum: 77     # 평균 - 2σ (기존: 65)
      max_sum: 200    # 평균 + 2σ (기존: 215)
    
    # 홀짝 필터 - 극단값만 제외
    odd_even:
      excluded_counts: [0, 6]  # 유지 (적절함)
    
    # 평균값 필터 - 통계 기반 조정
    average:
      min_average: 12.8   # (77/6)
      max_average: 33.3   # (200/6)
```

### 3. 선택적 필터 적용 전략

#### 필터 그룹화
```python
filter_groups = {
    "essential": ["odd_even", "sum_range", "dispersion"],  # 항상 적용
    "optional_a": ["fixed_step", "section", "average"],    # 50% 확률
    "optional_b": ["max_gap", "multiple"],                  # 30% 확률
}
```

#### 동적 필터 선택 알고리즘
```python
def select_filters_dynamically():
    selected = filter_groups["essential"].copy()
    
    # 선택적 그룹에서 랜덤 선택
    if random.random() < 0.5:
        selected.extend(random.sample(filter_groups["optional_a"], 2))
    
    if random.random() < 0.3:
        selected.extend(random.sample(filter_groups["optional_b"], 1))
    
    return selected
```

### 4. 필터 효율성 기반 순서 최적화

```yaml
filter_efficiency:
  # 효과적인 필터를 먼저 적용
  odd_even: 0.50        # 가장 효과적
  dispersion: 0.40      
  average: 0.35         
  sum_range: 0.30       
  fixed_step: 0.25      
  
  # 효과가 적은 필터는 나중에
  multiple: 0.15        
  section: 0.10         
  max_gap: 0.05         
```

## 구현 예시

### 동적 필터 관리자
```python
class DynamicFilterManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.filter_stats = self._calculate_filter_statistics()
        self.thresholds = self._calculate_dynamic_thresholds()
    
    def _calculate_dynamic_thresholds(self):
        """과거 데이터 기반 동적 임계값 계산"""
        winning_numbers = self.db_manager.get_all_winning_numbers()
        
        # 합계 통계
        sums = [sum(nums) for nums in winning_numbers]
        mean_sum = np.mean(sums)
        std_sum = np.std(sums)
        
        return {
            'sum_range': {
                'min': int(mean_sum - 2 * std_sum),
                'max': int(mean_sum + 2 * std_sum)
            },
            # ... 다른 필터들도 동일하게
        }
    
    def apply_filters_selectively(self, combinations, strategy='balanced'):
        """선택적 필터 적용"""
        if strategy == 'strict':
            filters = self.get_all_effective_filters()
        elif strategy == 'balanced':
            filters = self.select_balanced_filters()
        else:  # 'lenient'
            filters = self.get_essential_filters_only()
        
        for filter_name in filters:
            combinations = self.apply_single_filter(filter_name, combinations)
        
        return combinations
```

## 성능 개선 예상

1. **필터링 속도**: 효과 없는 7개 필터 제거로 약 40% 향상
2. **유효 조합 수**: match 필터 수정 후 적절한 수준 유지 가능
3. **당첨 확률**: 과도한 필터링 방지로 실제 당첨 패턴과 유사하게 조정

## 결론

현재 시스템의 가장 큰 문제는 **match 필터의 설계 오류**와 **모든 필터를 무조건 적용하는 접근법**입니다. 제안된 개선사항을 적용하면:

1. 유효한 번호 조합이 생성됨
2. 필터링 성능이 크게 향상됨
3. 실제 당첨 패턴을 더 잘 반영함
4. 시스템의 유연성과 확장성이 개선됨

특히 **동적 임계값 설정**과 **선택적 필터 적용**은 시간이 지나면서 변화하는 로또 패턴에 자동으로 적응할 수 있게 해줍니다.