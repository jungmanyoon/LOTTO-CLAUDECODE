---
name: Lotto Filter Expert
description: Expert in 16-filter system, adaptive probability filtering, threshold optimization, and filter performance analysis for lotto prediction
---

# Lotto Filter Expert Skill

전문 분야: 16개 필터 시스템, 적응형 확률 필터링, 임계값 최적화, 필터 성능 분석

## Core Responsibilities

### 1. Filter System Architecture
- **16 Filters**: odd_even, consecutive, sum_range, max_gap (critical), average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section (relaxable)
- **AdaptiveProbabilityFilter**: 1차 필터링 (8.14M → ~300K combinations)
- **FilterManager**: 병렬 처리 조정 (12 workers, 60K batch size)
- **IntegratedFilterManager**: 통합 필터 오케스트레이션

### 2. Threshold Management
- **Primary Config**: `configs/adaptive_filter_config.yaml`
- **Global Threshold**: `global_probability_threshold` (0.3-3.0 auto-adjusted)
- **ML Relaxed Threshold**: 0.5% (ML 예측 통과율 향상)
- **ThresholdManager**: Singleton pattern with observer pattern for auto-propagation
- **Decimal Precision**: Uses Decimal type to eliminate floating-point errors

### 3. Performance Optimization
- **Target**: 96.3% reduction (8.14M → 300K combinations)
- **ML Integration**: ~8.5% inclusion rate (target: 15%)
- **Parallel Processing**: 12 workers at 75% CPU utilization
- **Memory Limits**: 80% max usage, 250MB per worker, 60K batch size

### 4. Common Issues & Solutions

#### ML-Filter Disconnect (FIXED 2024-08-28)
- **Issue**: ML learns from 1,186 winning numbers, but filters exclude most predictions
- **Solution**: Relaxed threshold system in `main.py:generate_final_predictions_enhanced()`
  - ML relaxed threshold: 0.5%
  - Similar combination matching when ML fails
  - Relaxable filters bypass for ML predictions

#### AdaptiveProbabilityFilter Match Filter Bug (FIXED 2024-08-28)
- **Location**: `src/core/adaptive_probability_filter.py:189-193`
- **Fix**: Changed to check all patterns without early break

#### Filter Validation JSON Errors (FIXED 2025-10-10)
- **Root Cause**: Concurrent writes to same JSON file
- **Fix**: Migrated to SQLite (`results/filter_validation_YYYYMM.db`)
- **Benefits**: Transaction management, automatic locking, no race conditions

### 5. Key Files
- `src/core/adaptive_probability_filter.py`: Adaptive filtering logic
- `src/core/filter_manager.py`: Parallel processing coordination
- `src/core/integrated_filter_manager.py`: Unified orchestration
- `src/core/threshold_manager.py`: Centralized threshold management
- `src/core/filter_validator.py`: Filter validation (SQLite-based)
- `src/filters/base_filter.py`: Base class for all filters

### 6. Critical Rules
- Always use ThresholdManager singleton for threshold access
- Never hardcode threshold values
- Check ML integration when modifying relaxable filters
- Monitor average matches >3 (data contamination warning)
- Use context managers for database access

## When to Invoke This Skill

- Filter system modifications or debugging
- Threshold optimization or configuration
- ML-filter integration issues
- Performance tuning for parallel processing
- Filter validation or effectiveness analysis
- AdaptiveProbabilityFilter troubleshooting

## Example Commands

```python
# Access thresholds via ThresholdManager
from src.core.threshold_manager import ThresholdManager
tm = ThresholdManager()
threshold = tm.get_global_threshold()

# Register threshold observer
tm.register_observer(my_filter_component)

# Update thresholds (auto-propagates to all observers)
tm.update_threshold('global_probability_threshold', Decimal('1.5'))
```

## Performance Metrics
- Filter efficiency: ~96.3% reduction typical
- ML integration: 8.5% inclusion (target: 15%)
- Execution time: 2-3 minutes with cache
- Memory usage: <4GB with 60K batch size
