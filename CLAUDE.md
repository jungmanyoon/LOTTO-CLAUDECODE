# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Korean lottery (로또) prediction system using ML/AI to analyze historical patterns. Applies probability-based filtering to reduce 8.14M combinations to ~300K (with 1.5% threshold), improving odds by 27x through pattern exclusion.

## Common Commands
```bash
# Run main program (all features auto-execute)
python main.py

# Run with specific options
python main.py --skip-fetch              # Skip data collection
python main.py --ml-only                 # ML/AI analysis only
python main.py --no-parallel             # Disable parallel processing
python main.py --lstm --no-ensemble      # Use specific ML models

# Testing
python tests/test_all_filters_probability.py       # Test probability filtering
python tests/test_improved_ml_filter_integration.py # Test ML-filter integration
python -m pytest tests/                            # Run all tests

# Maintenance
python src/scripts/clear_model_cache.py  # Clear corrupted model cache
tail -f logs/lotto_app.log               # Real-time log monitoring
grep ERROR logs/lotto_app.log            # Filter errors only

# Dashboard (optional visualization)
python run_dashboard.py                  # Launch performance monitoring dashboard
```

## Architecture Overview

### Core Data Flow
```
1. Data Collection → 2. Filtering (815만→30만) → 3. ML Prediction → 4. Final Selection
```

### Critical Architecture Points

#### 1. ML-Filter Disconnect Issue
- **Problem**: ML learns from 1,186 historical winning numbers (시계열 패턴)
- **Filter**: Reduces 8.14M to ~300K combinations (probability <0.5% excluded)
- **Result**: ML predictions mostly fail filter validation (~8.5% inclusion rate)
- **Solution**: Implemented in `generate_final_predictions()`:
  - Relaxed filters for ML predictions (7 filters can be bypassed)
  - Similar combination matching when ML fails filters
  - See `find_similar_combinations()` and `extract_combination_features()`

#### 2. Probability Threshold Configuration
- **File**: `configs/adaptive_filter_config.yaml`
- **Key**: `global_probability_threshold` (line 67)
- **Current**: 1.5 (excludes patterns occurring <1.5% in history)
- **Impact**: Lower value = fewer exclusions = larger pool
  - 0.5% → ~500K combinations
  - 1.0% → ~300K combinations  
  - 1.5% → ~150K combinations (current setting)
- **Note**: Threshold directly affects filter pool size and computational requirements

#### 3. Database Structure
- **lotto_numbers.db**: Historical winning numbers (1186+ rounds)
- **combinations.db**: Pre-filtered combinations cache
- **filters/*.db**: 16 individual filter analysis results
- **predictions.db**: Saved predictions for tracking

#### 4. Model Caching System
- Location: `cache/models/` with hash-based versioning
- Clear corrupted cache: `python src/scripts/clear_model_cache.py`
- Cache invalidation: 7 days or data change

### Key Components

#### Filter System (16 filters)
All inherit from `BaseFilter`, managed by `FilterManager`:
- **Critical filters** (always applied): odd_even, consecutive, sum_range
- **Relaxable filters** (ML bypass): average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion
- **Adaptive system**: `AdaptiveProbabilityFilter` updates criteria weekly

#### ML Models  
- **LSTM**: Time-series on 50-round sequences (`lstm_predictor.py`)
- **Ensemble**: RF + XGBoost + NN (`ensemble_predictor.py`)
- **Monte Carlo**: Statistical simulation (`monte_carlo_simulator.py`)
- **Bayesian**: Probabilistic inference (`bayesian_inference.py`)

#### Integration Points
- `main.py:generate_final_predictions()`: ML-filter integration logic
- `optimized_backtesting_framework.py`: Performance validation with filter pool inclusion rate
- `integrated_filter_manager.py`: Combines adaptive and static filtering

## Critical Implementation Details

### Parallel Processing
- FilterManager: ProcessPoolExecutor (14 workers default)
- Batch size: 10,000 combinations
- Memory limit: 70% max usage

### DatabaseManager Methods
- Use `get_all_winning_numbers()` or `get_all_numbers()`
- NOT `get_all_rounds()` (doesn't exist)

### Encoding Issues
- Use `encoding='utf-8'` for file operations
- Replace emoji (✅, ❌) with ASCII ([O], [X]) in tests

## Known Issues & Solutions

### AdaptiveProbabilityFilter Match Filter Bug (FIXED 2024-08-28)
- **Issue**: Sequential check with `break` causing 4,5-match patterns not excluded
- **Location**: `src/core/adaptive_probability_filter.py:189-193`
- **Fix Applied**: Changed to check all patterns without early break (lines 189-198)
- **Impact**: Match filter now correctly excludes patterns ≤ threshold (3+ matches with 1.5%)

### StandardScaler AttributeError
- **Cause**: Corrupted model cache
- **Fix**: Run `python src/scripts/clear_model_cache.py`

### DatabaseManager attribute errors  
- **Common**: `get_all_rounds()` doesn't exist
- **Use**: `get_all_winning_numbers()` instead

## Performance Metrics
- First run: 5-10 minutes (training + filtering)
- Subsequent: 2-3 minutes (cached)
- Filter exclusion: ~98.2% (815만 → 15만 with 1.5% threshold)
- ML filter inclusion: ~8.5% (needs improvement)
- Target backtesting: 0.8-1.5 avg matches

## Warning Signs
- Average matches >3: Data contamination (winning numbers leaked into test)
- All ML models same prediction: Cache corruption, run clear_model_cache.py
- Memory >4GB: Reduce batch size in filter_manager.py
- Filter inclusion <10%: Threshold too restrictive, adjust in config
- Execution time >15 minutes: Check parallelization settings

## Korean Terms
- 회차 (hoecha): Round/Draw number
- 당첨번호 (dangcheom-beonho): Winning numbers
- 필터 (pilteo): Filter
- 예측 (yecheuk): Prediction
- 동행복권: Official lottery operator