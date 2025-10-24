---
name: Lotto ML Trainer
description: Expert in ML model training, optimization, caching, and ensemble prediction for lotto system with LSTM, XGBoost, and Monte Carlo
---

# Lotto ML Trainer Skill

전문 분야: ML 모델 학습, 최적화, 캐싱, 앙상블 예측 (LSTM, XGBoost, Monte Carlo)

## Core Responsibilities

### 1. ML Model Architecture
- **LSTM**: Time-series on 50-round sequences (`src/ml/lstm_predictor.py`)
  - Batch size: 64, Epochs: 50
  - Sequential pattern learning from historical data
- **Ensemble**: RF + XGBoost + NN (`src/ml/ensemble_predictor.py`)
  - 100 estimators, 4 parallel jobs
  - Weighted averaging for final predictions
- **Monte Carlo**: 6,000 simulations with 8 parallel workers (`src/probabilistic/monte_carlo_simulator.py`)
  - Batch size: 750 simulations per worker
- **Bayesian**: Probabilistic inference (`src/probabilistic/bayesian_inference.py`)
- **Fractal**: Chaos theory patterns (`src/advanced/fractal_pattern_analyzer.py`)

### 2. Model Caching System
- **Location**: `cache/models/` with hash-based versioning
- **Size**: Can grow to 1.7GB+
- **Cache invalidation**: 7 days or data change
- **Clear corrupted cache**: `python src/scripts/clear_model_cache.py`
- **Auto-recreation**: Models rebuild on next run after clearing

### 3. TensorFlow/Keras Configuration
**Critical Environment Variables** (MUST be set before imports):
```python
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'  # Disable oneDNN logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'   # ERROR only
os.environ['ABSL_LOGGING_VERBOSITY'] = '1'  # Suppress ABSL
```

**Matplotlib Backend**:
```python
import matplotlib
matplotlib.use('Agg')  # Non-interactive, prevents tkinter errors
```

**Warning Suppression** (main.py:34-49):
- All TensorFlow/Keras warnings filtered
- Clean console output maintained

### 4. Performance Tracking
- **PerformanceStatsManager**: Records model performance across sessions
  - Location: `src/core/performance_stats_manager.py`
  - Database: `performance_stats.db` (434MB, 4.7M rows typical)
- **PerformanceMetrics**: Unified scoring system
  - Location: `src/core/performance_metrics.py`
  - Normalized scores (0-1): Use for comparisons
  - Raw scores (0-6): Store in database
  - Composite scores (0-100): Display only
  - Functions: `normalize_score()`, `calculate_overall_score()`, `compare_performance()`

### 5. ML-Filter Integration
**Problem**: ML predictions mostly fail filter validation (~8.5% inclusion)
- **Cause**: ML learns from 1,186 historical patterns, filters exclude based on probability
- **Solution** (`main.py:generate_final_predictions_enhanced()` line ~1207):
  - ML relaxed threshold: 0.5% (configurable)
  - Similar combination matching
  - Relaxable filters: 12 filters bypass for ML predictions

**Relaxable Filters**:
- average, prime_composite, fixed_step, multiple, ten_section, digit_sum
- dispersion, last_digit, arithmetic_sequence, geometric_sequence, section, sum_range, max_gap

### 6. Common Issues & Solutions

#### StandardScaler AttributeError
- **Cause**: Corrupted model cache
- **Fix**: `python src/scripts/clear_model_cache.py`

#### Performance Scoring Inconsistency (FIXED 2025-10-14)
- **Issue**: Different scoring formulas across modules
- **Fix**: Unified PerformanceMetrics class
- **Rule**: Always use `PerformanceMetrics.normalize_score()` for comparisons

#### High Memory Usage
- **Warning**: Memory >4GB
- **Solutions**:
  - Clear model cache: `python src/scripts/clear_model_cache.py`
  - Run cache cleaner: `python src/scripts/auto_cache_cleaner.py --force`
  - Reduce batch sizes in config.yaml

### 7. Key Files
- `src/ml/lstm_predictor.py`: LSTM time-series model
- `src/ml/ensemble_predictor.py`: Ensemble predictor (RF+XGBoost+NN)
- `src/ml/improved_ensemble_predictor.py`: Enhanced version
- `src/probabilistic/monte_carlo_simulator.py`: Monte Carlo simulation
- `src/probabilistic/bayesian_inference.py`: Bayesian inference
- `src/advanced/fractal_pattern_analyzer.py`: Fractal analysis
- `src/core/performance_metrics.py`: Unified scoring system
- `main.py`: TF/Keras configuration and model coordination

### 8. Critical Rules
- Set TF environment variables BEFORE any imports
- Always use PerformanceMetrics for scoring comparisons
- Clear cache on AttributeError or corruption
- Monitor memory usage (>4GB warning)
- Check ML-filter integration when modifying filters
- Use weighted averaging for ensemble predictions

## When to Invoke This Skill

- ML model training or retraining
- Model cache issues or corruption
- Performance scoring and comparison
- TensorFlow/Keras configuration issues
- ML-filter integration problems
- Memory optimization for ML operations
- Ensemble prediction coordination

## Example Commands

```python
# Clear corrupted model cache
python src/scripts/clear_model_cache.py

# Check memory usage
from src.utils.memory_monitor import MemoryMonitor
monitor = MemoryMonitor()
monitor.log_memory()

# Use unified scoring
from src.core.performance_metrics import PerformanceMetrics
pm = PerformanceMetrics()
normalized_score = pm.normalize_score(avg_matches=1.5, max_matches=4, inclusion_rate=0.12)
overall_score = pm.calculate_overall_score(1.5, 4, 0.12)
```

## Performance Metrics
- Initial run: 5-10 minutes (training + filtering)
- Subsequent runs: 2-3 minutes (with cache)
- ML integration: ~8.5% inclusion (target: 15%)
- Backtest accuracy: 0.8-1.5 avg matches
- Cache size: ~1.7GB typical
- Memory usage: <4GB optimal
