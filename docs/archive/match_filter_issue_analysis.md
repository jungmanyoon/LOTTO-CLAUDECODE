# Match 필터 문제점 상세 분석

## 문제 요약
Match 필터가 백테스팅에서 모든 당첨번호를 필터링하는 치명적인 문제 발견

## 근본 원인

### 1. 자기 참조 문제 (Self-Reference Problem)
```python
# match_filter.py의 apply_filter 메서드
winning_numbers = self.db_manager.get_all_winning_numbers()  # 모든 과거 당첨번호
```

- Match 필터는 **모든 과거 당첨번호**와 비교합니다
- 백테스팅 시 테스트하려는 당첨번호도 이미 DB에 저장되어 있습니다
- 자기 자신과 비교하면 6개가 일치하므로 무조건 필터링됩니다

### 2. 필터링 조건 문제
```python
valid_indices = match_counts < max_match  # max_match=5
```

- `<` 연산자 사용: 5개 미만(0~4개)만 통과
- 자기 자신은 6개 일치 → 무조건 제외

## 해결 방안

### 즉시 조치 (Quick Fix)
1. **max_match를 7로 설정**
   - 완전 일치(6개)를 초과하는 경우는 없으므로 사실상 필터 비활성화
   - config.yaml 수정: `max_match: 7`

2. **Match 필터 비활성화**
   - config.yaml의 enabled_filters에서 'match' 제거

### 근본적 해결책
1. **시계열 고려 필터링**
   ```python
   def apply_filter(self, combinations: List[str], round_num: int) -> List[str]:
       # round_num 이전의 당첨번호만 가져오기
       winning_numbers = self.db_manager.get_winning_numbers_before(round_num)
   ```

2. **자기 제외 로직 추가**
   ```python
   # 테스트 중인 조합이 이미 당첨번호인 경우 제외하지 않음
   if combination in winning_numbers:
       continue
   ```

3. **필터 기준 재설정**
   - 5개 일치가 실제로 18건 발생했으므로
   - `max_match: 6` (5개까지 허용, 6개만 제외)
   - 또는 `max_match: 5`로 유지하되 `<=` 연산자로 변경

## 영향 분석

### 현재 상태
- 백테스팅: 모든 당첨번호 필터링 (통과율 0%)
- 실제 운영: 과거 당첨번호와 유사한 조합 과도하게 제외

### 수정 후 예상
- 백테스팅: 정상적인 통과율 (98% 이상)
- 실제 운영: 완전 일치(6개)만 제외하거나 필터 비활성화

## 권장 구현

```python
def apply_filter(self, combinations: List[str], round_num: int) -> List[str]:
    """개선된 Match 필터"""
    try:
        # round_num 이전의 당첨번호만 가져오기
        if hasattr(self.db_manager, 'get_winning_numbers_before'):
            winning_numbers = self.db_manager.get_winning_numbers_before(round_num)
        else:
            # 폴백: 모든 당첨번호 가져오기
            winning_numbers = self.db_manager.get_all_winning_numbers()
            
        if not winning_numbers:
            return combinations
            
        # 나머지 로직은 동일...
```

이 문제는 백테스팅 방법론의 근본적인 결함을 보여주며, 시계열 데이터의 특성을 고려하지 않은 필터 설계의 위험성을 잘 보여줍니다.