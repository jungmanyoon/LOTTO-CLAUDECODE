# ThresholdManager 사용 가이드

## 개요

ThresholdManager는 로또 예측 시스템 전체에서 임계값을 중앙 관리하는 Single Source of Truth 시스템입니다.

### 문제점 해결

**기존 문제**:
- 동일 trial 내에서 임계값이 1.0% → 1.8% → 2.1%로 변경됨
- 여러 컴포넌트가 독립적으로 임계값 로드 (동기화 부재)
- 부동소수점 오류: `1.7000000000000002`

**해결 방법**:
- 싱글톤 패턴으로 전역 단일 인스턴스 보장
- Observer 패턴으로 자동 동기화
- Decimal 사용으로 부동소수점 오류 완전 제거
- 변경 추적 로깅으로 디버깅 용이

---

## 아키텍처

### 싱글톤 패턴
```python
from src.core.threshold_manager import get_threshold_manager

# 어디서 호출하든 동일한 인스턴스 반환
tm1 = get_threshold_manager()
tm2 = get_threshold_manager()
assert tm1 is tm2  # True
```

### Observer 패턴
```python
def my_callback(param, old_value, new_value):
    print(f"{param}: {old_value} → {new_value}")

tm = get_threshold_manager()
tm.register_observer(my_callback)  # 변경 감지 콜백 등록

tm.set_threshold(2.0)  # 자동으로 my_callback 호출됨
```

### Decimal 정밀도
```python
tm = get_threshold_manager()
tm.set_threshold(1.7)  # 내부적으로 Decimal("1.70")로 저장

threshold = tm.get_threshold()
print(threshold)  # 1.7 (1.7000000000000002 아님)
```

---

## 사용 방법

### 1. 기본 사용

```python
from src.core.threshold_manager import get_threshold_manager

# 싱글톤 인스턴스 가져오기
tm = get_threshold_manager()

# 임계값 설정
tm.set_threshold(1.5, source="manual")

# 임계값 조회
threshold = tm.get_threshold()
print(f"현재 임계값: {threshold}%")
```

### 2. 설정 파일 연동

```python
# 설정 파일에서 로드
tm.load_from_config("configs/adaptive_filter_config.yaml")

# 설정 파일에 저장
tm.save_to_config("configs/adaptive_filter_config.yaml")
```

### 3. ML 파라미터 관리

```python
# ML 완화 임계값 (global_threshold보다 작아야 함)
tm.set_ml_relaxed_threshold(0.5, source="optimizer")

# ML 우회 필터 수
tm.set_ml_bypass_filters(15, source="config")

# ML 가중치
tm.set_ml_weight(0.6, source="optimizer")

# 모든 파라미터 조회
params = tm.get_all_parameters()
print(params)
# {
#   'global_probability_threshold': 1.5,
#   'ml_relaxed_threshold': 0.5,
#   'ml_bypass_filters': 15,
#   'ml_weight': 0.6
# }
```

### 4. Observer 패턴 활용

```python
class MyComponent:
    def __init__(self):
        self.tm = get_threshold_manager()
        self.threshold = self.tm.get_threshold()

        # 변경 감지 Observer 등록
        self.tm.register_observer(self._on_threshold_change)

    def _on_threshold_change(self, param, old_value, new_value):
        """임계값 변경 시 자동 호출"""
        if param == "threshold":
            self.threshold = float(new_value)
            print(f"[자동 동기화] {old_value:.2f}% → {new_value:.2f}%")

# 사용 예
component = MyComponent()
tm = get_threshold_manager()
tm.set_threshold(2.0)  # component._on_threshold_change 자동 호출
```

### 5. 변경 이력 추적

```python
# 변경 이력 조회
history = tm.get_change_history(limit=10)

for change in history:
    print(f"[{change.timestamp}] {change.parameter}: "
          f"{change.old_value} → {change.new_value} "
          f"(소스: {change.source})")

# 변경 이력 출력 (간편 메서드)
tm.print_change_history(limit=5)
```

---

## 통합 예제

### AdaptiveProbabilityFilter 통합

```python
# src/core/adaptive_probability_filter.py

from src.core.threshold_manager import get_threshold_manager

class AdaptiveProbabilityFilter:
    def __init__(self, db_manager):
        self.db_manager = db_manager

        # ThresholdManager 연동
        self.threshold_manager = get_threshold_manager()
        self.probability_threshold = self.threshold_manager.get_threshold()

        # Observer 등록 (자동 동기화)
        self.threshold_manager.register_observer(self._on_threshold_change)

    def _on_threshold_change(self, param, old_value, new_value):
        """임계값 변경 시 자동 동기화"""
        if param == "threshold":
            self.probability_threshold = float(new_value)
            logging.info(f"[적응형 필터] 임계값 자동 동기화: {old_value}% → {new_value}%")
```

### FilterManager 통합

```python
# src/core/filter_manager.py

from src.core.threshold_manager import get_threshold_manager

class FilterManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager

        # ThresholdManager 연동
        self.threshold_manager = get_threshold_manager()
        self.threshold_manager.register_observer(self._on_config_change)

    def _on_config_change(self, param, old_value, new_value):
        """설정 변경 시 필터 효율성 재계산"""
        logging.info(f"[FilterManager] 설정 변경: {param} = {old_value} → {new_value}")

        if param in ("threshold", "global_probability_threshold"):
            self._update_filter_efficiency()
```

### AutoThresholdOptimizer 통합

```python
# src/scripts/auto_threshold_optimizer.py

from src.core.threshold_manager import get_threshold_manager

class AutoThresholdOptimizer:
    def __init__(self):
        # ThresholdManager 연동
        self.threshold_manager = get_threshold_manager()
        self.threshold_manager.load_from_config()

    def run_backtesting_with_config(self, config):
        """백테스팅 실행 with ThresholdManager"""
        # 파라미터 추출
        threshold = config.get('global_probability_threshold', 1.0)
        ml_bypass = config.get('ml_integration', {}).get('ml_bypass_filters', 8)
        ml_weight = config.get('ml_integration', {}).get('ml_weight', 0.4)

        # ThresholdManager에 설정 (모든 컴포넌트에 자동 전파)
        self.threshold_manager.set_threshold(threshold, source="optimizer")
        self.threshold_manager.set_ml_bypass_filters(ml_bypass, source="optimizer")
        self.threshold_manager.set_ml_weight(ml_weight, source="optimizer")

        # 백테스팅 실행 (모든 컴포넌트가 자동으로 새 값 사용)
        results = framework.run_backtest(...)
        return results
```

---

## API 레퍼런스

### 임계값 설정 (Setter)

#### `set_threshold(value, source="manual")`
전역 확률 임계값 설정

- **파라미터**:
  - `value` (float): 0.3 ~ 3.0
  - `source` (str): 변경 소스 (config, optimizer, manual)
- **효과**: 모든 Observer에게 변경 알림 자동 전파

#### `set_ml_relaxed_threshold(value, source="manual")`
ML 완화 임계값 설정

- **파라미터**:
  - `value` (float): 0.1 ~ 2.0 (global_threshold보다 작아야 함)
  - `source` (str): 변경 소스

#### `set_ml_bypass_filters(value, source="manual")`
ML 우회 필터 수 설정

- **파라미터**:
  - `value` (int): 8 ~ 20
  - `source` (str): 변경 소스

#### `set_ml_weight(value, source="manual")`
ML 가중치 설정

- **파라미터**:
  - `value` (float): 0.1 ~ 1.0
  - `source` (str): 변경 소스

### 임계값 조회 (Getter)

#### `get_threshold() -> float`
전역 확률 임계값 조회

#### `get_ml_relaxed_threshold() -> float`
ML 완화 임계값 조회

#### `get_ml_bypass_filters() -> int`
ML 우회 필터 수 조회

#### `get_ml_weight() -> float`
ML 가중치 조회

#### `get_all_parameters() -> Dict[str, Any]`
모든 파라미터 한번에 조회

### Observer 패턴

#### `register_observer(callback)`
변경 알림을 받을 Observer 등록

- **파라미터**:
  - `callback` (Callable): `callback(param, old_value, new_value)` 형식

#### `unregister_observer(callback)`
Observer 등록 해제

### 설정 파일 연동

#### `load_from_config(config_path=None) -> bool`
설정 파일에서 임계값 로드

- **파라미터**:
  - `config_path` (str, optional): 설정 파일 경로
- **반환**: 로드 성공 여부

#### `save_to_config(config_path=None) -> bool`
현재 임계값을 설정 파일에 저장

- **파라미터**:
  - `config_path` (str, optional): 설정 파일 경로
- **반환**: 저장 성공 여부

### 변경 이력

#### `get_change_history(limit=None) -> List[ThresholdChange]`
변경 이력 조회 (최신순)

- **파라미터**:
  - `limit` (int, optional): 반환할 최대 개수

#### `print_change_history(limit=10)`
변경 이력 출력 (콘솔)

---

## 검증 방법

### 1. 단위 테스트 실행

```bash
python tests/test_threshold_manager.py
```

**테스트 항목**:
- 싱글톤 패턴 검증
- Decimal 정밀도 검증
- Observer 패턴 동작 확인
- 파라미터 범위 검증
- ML 파라미터 설정
- 변경 이력 추적
- 설정 파일 연동

### 2. 통합 테스트

```python
from src.core.threshold_manager import get_threshold_manager
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
from src.core.filter_manager import FilterManager
from src.core.db_manager import DatabaseManager

# 컴포넌트 초기화
db_manager = DatabaseManager()
tm = get_threshold_manager()
adaptive_filter = AdaptiveProbabilityFilter(db_manager)
filter_manager = FilterManager(db_manager)

# 임계값 변경
print(f"변경 전: adaptive_filter.probability_threshold = {adaptive_filter.probability_threshold}")
tm.set_threshold(2.0, source="test")
print(f"변경 후: adaptive_filter.probability_threshold = {adaptive_filter.probability_threshold}")

# 자동 동기화 확인
assert adaptive_filter.probability_threshold == 2.0
```

### 3. 변경 이력 확인

```python
tm = get_threshold_manager()

# 여러 변경 수행
tm.set_threshold(1.0, source="config")
tm.set_threshold(1.5, source="optimizer")
tm.set_threshold(2.0, source="manual")

# 이력 출력
tm.print_change_history(limit=10)
```

**출력 예시**:
```
[ThresholdManager] 최근 3개 변경 이력:
  1. [2025-10-04 20:00:00] global_probability_threshold: 1.5 → 2.0 (소스: manual)
  2. [2025-10-04 19:55:00] global_probability_threshold: 1.0 → 1.5 (소스: optimizer)
  3. [2025-10-04 19:50:00] global_probability_threshold: 2.1 → 1.0 (소스: config)
```

---

## 마이그레이션 가이드

### 기존 코드 수정 방법

#### Before (기존 방식)
```python
# 각 컴포넌트가 독립적으로 설정 로드
import yaml

with open('configs/adaptive_filter_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

threshold = config.get('global_probability_threshold', 1.0)
```

#### After (ThresholdManager 사용)
```python
from src.core.threshold_manager import get_threshold_manager

# 중앙 관리자에서 조회 (자동 동기화)
tm = get_threshold_manager()
threshold = tm.get_threshold()
```

### Observer 등록 방법

#### Before (수동 업데이트)
```python
class MyFilter:
    def __init__(self, threshold):
        self.threshold = threshold

    def update_threshold(self, new_threshold):
        # 수동으로 업데이트 필요
        self.threshold = new_threshold
```

#### After (자동 동기화)
```python
from src.core.threshold_manager import get_threshold_manager

class MyFilter:
    def __init__(self):
        self.tm = get_threshold_manager()
        self.threshold = self.tm.get_threshold()

        # Observer 등록 (자동 동기화)
        self.tm.register_observer(self._on_threshold_change)

    def _on_threshold_change(self, param, old_value, new_value):
        if param == "threshold":
            self.threshold = float(new_value)
            # 자동으로 업데이트됨!
```

---

## 디버깅 팁

### 1. 임계값 변경 추적

```python
# 로깅 레벨을 DEBUG로 설정하여 상세 로그 확인
import logging
logging.basicConfig(level=logging.DEBUG)

tm = get_threshold_manager()
tm.set_threshold(1.5)  # 변경 로그 자동 출력
```

### 2. Observer 호출 확인

```python
def debug_observer(param, old_value, new_value):
    import traceback
    print(f"\n[Observer 호출]")
    print(f"  파라미터: {param}")
    print(f"  이전 값: {old_value}")
    print(f"  새 값: {new_value}")
    print(f"  호출 스택:")
    traceback.print_stack()

tm = get_threshold_manager()
tm.register_observer(debug_observer)
tm.set_threshold(2.0)  # 호출 스택과 함께 출력
```

### 3. 변경 소스 추적

```python
# 변경 이력에서 소스 확인
tm = get_threshold_manager()
history = tm.get_change_history(limit=20)

# optimizer에서 변경한 이력만 필터링
optimizer_changes = [c for c in history if c.source == "optimizer"]
print(f"optimizer 변경 이력: {len(optimizer_changes)}개")
```

---

## 주의사항

### 1. 스레드 안전성
- ThresholdManager는 스레드 안전하게 설계됨
- 멀티스레드 환경에서도 안전하게 사용 가능

### 2. 파라미터 범위
- 각 파라미터는 유효 범위 검증이 적용됨
- 범위 밖 값은 자동으로 무시되며 로그 출력

### 3. 설정 파일 백업
- `save_to_config()` 호출 시 기존 파일 자동 백업
- 백업 파일: `{config_path}.backup_{timestamp}`

### 4. Observer 메모리 누수 방지
- Observer 등록 후 반드시 `unregister_observer()` 호출
- 또는 컴포넌트 소멸 시 자동 해제되도록 구현

---

## 성공 기준

✅ **100% 일관성**: 모든 컴포넌트가 동일한 임계값 사용
✅ **자동 동기화**: Observer 패턴으로 수동 업데이트 불필요
✅ **정밀도 보장**: Decimal 사용으로 부동소수점 오류 완전 제거
✅ **변경 추적**: 모든 변경 이력 기록 및 디버깅 용이
✅ **설정 연동**: YAML 파일과 양방향 동기화

---

## FAQ

### Q: ThresholdManager를 사용하면 성능에 영향이 있나요?
A: 싱글톤 패턴과 Decimal 사용으로 인한 오버헤드는 무시할 수 있는 수준입니다. Observer 알림도 동기식으로 빠르게 처리됩니다.

### Q: 기존 코드와 호환성은 어떻게 되나요?
A: ThresholdManager는 기존 코드와 병행 사용 가능합니다. 점진적으로 마이그레이션하면 됩니다.

### Q: 설정 파일과 메모리 상태가 불일치하면 어떻게 되나요?
A: ThresholdManager는 메모리 상태를 우선합니다. `load_from_config()`를 명시적으로 호출하여 설정 파일에서 다시 로드할 수 있습니다.

### Q: Observer가 너무 많이 등록되면 문제가 되나요?
A: Observer는 리스트로 관리되며 호출 오버헤드는 O(n)입니다. 일반적으로 10개 미만의 Observer를 사용하므로 성능 문제는 없습니다.

---

## 관련 파일

- **구현**: `src/core/threshold_manager.py`
- **테스트**: `tests/test_threshold_manager.py`
- **사용 예**:
  - `src/core/adaptive_probability_filter.py`
  - `src/core/filter_manager.py`
  - `src/scripts/auto_threshold_optimizer.py`
- **설정**: `configs/adaptive_filter_config.yaml`
