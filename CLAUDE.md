# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Korean lottery (로또) prediction system using ML/AI to analyze historical patterns. Applies probability-based filtering to reduce 8.14M combinations to ~300K (with 1.0% threshold), improving odds by 27x through pattern exclusion.

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
pip install pytest pytest-cov                      # Install test dependencies
python -m pytest tests/                            # Run all tests
python -m pytest tests/test_file.py -v             # Run single test file with verbose output
python -m pytest tests/ -k "test_name"             # Run specific test by name
python -m pytest --cov=src tests/                  # Run tests with coverage report

# Maintenance & Troubleshooting
python src/scripts/clear_model_cache.py  # Clear corrupted model cache (1.7GB cache)
tail -f logs/lotto_app.log               # Real-time log monitoring (Linux/Mac)
type logs\lotto_app.log | more           # View logs on Windows
findstr ERROR logs\lotto_app.log         # Filter errors only (Windows)

# Dashboard & Monitoring (Port 5001)
python run_dashboard.py                  # Launch performance monitoring dashboard
python src/scripts/enhanced_dashboard_v2.py  # Alternative dashboard start

# Bonus Number Collection
python src/scripts/complete_bonus_collection.py  # Collect missing bonus numbers

# Auto-Learning & Threshold Optimization
python src/scripts/check_auto_learning_status.py  # Check auto-learning status
python src/scripts/auto_threshold_optimizer.py    # Run threshold optimization (30 trials)
python src/scripts/auto_threshold_optimizer.py --rollback  # Rollback to previous settings

# Utility Scripts
python src/scripts/analyze_filters.py             # Analyze filter effectiveness
python src/scripts/optimize_databases.py          # Optimize and compact databases
python src/scripts/kill_db_locks.py               # Release database locks if stuck
```

## Quick Start
```bash
# First time setup
pip install -r requirements.txt

# Run the complete system (auto-executes all features)
python main.py

# Launch dashboard for monitoring (opens on http://localhost:5001)
python src/scripts/enhanced_dashboard_v2.py
```

## Architecture Overview

### Core Data Flow
```
1. Data Collection → 2. Filtering (815만→30만) → 3. ML Prediction → 4. Final Selection → 5. Dashboard Display
```

### System Health & Auto-Repair
- **SystemHealthChecker**: Monitors system health and performs automatic repairs
- **AutoRepairSystem**: Real-time problem detection and automatic fixes
- Both systems run automatically when `main.py` is executed

### Critical Architecture Points

#### 1. ML-Filter Disconnect Issue
- **Problem**: ML learns from 1,186 historical winning numbers (시계열 패턴)
- **Filter**: Reduces 8.14M to ~300K combinations (probability <1.0% excluded)
- **Result**: ML predictions mostly fail filter validation (~8.5% inclusion rate)
- **Solution**: Implemented in `main.py:generate_final_predictions()` (line ~1100):
  - Relaxed filters for ML predictions (11 filters can be bypassed)
  - Similar combination matching when ML fails filters
  - Relaxable filters: average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section

#### 2. Probability Threshold Configuration
- **File**: `configs/adaptive_filter_config.yaml`
- **Key**: `global_probability_threshold` (line 67)
- **Current**: 1.0 (excludes patterns occurring <1.0% in history)
- **Impact**: Lower value = fewer exclusions = larger pool
  - 0.5% → ~500K combinations
  - 1.0% → ~300K combinations (current setting)
  - 1.5% → ~150K combinations
- **Note**: Threshold directly affects filter pool size and computational requirements

#### 3. Database Structure
- **lotto_numbers.db**: Historical winning numbers (1186+ rounds) with bonus numbers
- **combinations.db**: Pre-filtered combinations cache
- **filters/*.db**: 16 individual filter analysis results
- **predictions.db**: Saved predictions for tracking
- **performance_stats.db**: Backtest performance metrics & model statistics
- **backtest_results.db**: Detailed backtesting history

#### 4. Model Caching System  
- Location: `cache/models/` with hash-based versioning (can grow to 1.7GB+)
- Clear corrupted cache: `python src/scripts/clear_model_cache.py`
- Cache invalidation: 7 days or data change
- Auto-recreated on next run after clearing

#### 5. Performance Statistics System
- **PerformanceStatsManager**: Tracks model performance across sessions
- **Metrics tracked**: Average matches, max matches, filter inclusion rates
- **Integration**: Automatically saves stats during backtesting
- Location: `src/core/performance_stats_manager.py`

#### 6. Auto-Learning & Threshold Optimization System
- **ThresholdOptimizer**: Bayesian optimization using Optuna for finding optimal thresholds
- **SmartAutoLearning**: 24-hour cycle automatic optimization with rollback capability
- **FilterPerformanceTracker**: Real-time filter effectiveness monitoring
- **Optimization cycle**: Daily at 3AM (configurable), 30 trials per optimization
- **Safety features**: Auto-rollback if performance degrades >10%, validation on 50 recent rounds
- Files: `src/core/threshold_optimizer.py`, `src/core/smart_auto_learning.py`

#### 7. Dashboard System (Enhanced v2)
- **Port**: 5001 (Flask web server)
- **Auto-start**: Dashboard starts automatically when running `main.py`
- **Features**: Real-time predictions display, on-demand prediction generation, performance metrics
- **Prediction Button**: Generate 5 new prediction sets without re-running main.py
- **JavaScript Issues**: Ensure proper escaping of newlines in Python strings (\\n not \n)
- File: `src/scripts/enhanced_dashboard_v2.py`

### Key Components

#### Filter System (16 filters)
All inherit from `BaseFilter`, managed by `FilterManager`:
- **Critical filters** (always applied): odd_even, consecutive, sum_range, max_gap
- **Relaxable filters** (ML bypass): average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section
- **Adaptive system**: `AdaptiveProbabilityFilter` updates criteria weekly

#### ML Models  
- **LSTM**: Time-series on 50-round sequences (`src/ml/lstm_predictor.py`)
- **Ensemble**: RF + XGBoost + NN (`src/ml/ensemble_predictor.py`)
- **Monte Carlo**: Statistical simulation (`src/probabilistic/monte_carlo_simulator.py`)
- **Bayesian**: Probabilistic inference (`src/probabilistic/bayesian_inference.py`)
- **Fractal**: Chaos theory patterns (`src/advanced/fractal_pattern_analyzer.py`)

#### Integration Points
- `main.py:generate_final_predictions()` (line ~1100): ML-filter integration logic
- `src/backtesting/optimized_backtesting_framework.py`: Performance validation with bonus number support
- `src/core/integrated_filter_manager.py`: Combines adaptive and static filtering  
- `src/utils/rank_calculator.py`: Prize rank calculation (1-5등) with bonus logic
- `src/scripts/enhanced_dashboard_v2.py`: Current dashboard implementation (port 5001)

## Critical Implementation Details

### Parallel Processing Configuration
- FilterManager: ProcessPoolExecutor (14 workers default, configurable in `config.yaml`)
- Batch size: 10,000 combinations (configurable in `config.yaml`)
- Memory limit: 70% max usage
- Dynamic worker allocation based on system resources

### DatabaseManager Methods
- Use `get_all_winning_numbers()` or `get_all_numbers()` for basic data
- `get_numbers_with_bonus()`: Returns List[Tuple[round, (n1,n2,n3,n4,n5,n6,bonus)]]
- `get_winning_numbers_before(round_num)`: For backtesting, gets numbers before specific round
- NOT `get_all_rounds()` (doesn't exist)
- `fetch_and_save_lotto_data()`: Updates from official site (동행복권)

### File Encoding & Platform Compatibility
- Always use `encoding='utf-8'` for file operations
- Replace emoji (✅, ❌) with ASCII ([O], [X]) in tests
- Windows paths: Use raw strings or forward slashes
- Log viewing: Use `type` instead of `cat` on Windows

### Bonus Number Handling
- Bonus number is 7th element in winning numbers tuple from `get_numbers_with_bonus()`
- Used for 2nd place (5 + bonus) prize calculation
- Backtesting now includes bonus matching for accurate rank calculation
- Complete collection script: `src/scripts/complete_bonus_collection.py`

## Known Issues & Solutions

### AdaptiveProbabilityFilter Match Filter Bug (FIXED 2024-08-28)
- **Issue**: Sequential check with `break` causing 4,5-match patterns not excluded
- **Location**: `src/core/adaptive_probability_filter.py:189-193`
- **Fix Applied**: Changed to check all patterns without early break (lines 189-198)
- **Impact**: Match filter now correctly excludes patterns ≤ threshold (3+ matches with 1.0%)

### StandardScaler AttributeError
- **Cause**: Corrupted model cache
- **Fix**: Run `python src/scripts/clear_model_cache.py`

### DatabaseManager attribute errors  
- **Common**: `get_all_rounds()` doesn't exist
- **Use**: `get_all_winning_numbers()` instead

### Bonus Number Issues (FIXED 2025-09-12)
- **Previous Issue**: Bonus numbers were missing or random in dashboard
- **Fix Applied**: `get_numbers_with_bonus()` method properly implemented
- **Current Status**: Backtesting correctly calculates 2nd place (5+bonus) winners

### Dashboard JavaScript Errors (FIXED 2025-09-13)
- **Issue**: Template literals in Python strings causing syntax errors
- **Location**: `enhanced_dashboard_v2.py` generateNewPredictions function
- **Fix**: Escape newlines properly (\\n not \n) in JavaScript strings within Python
- **Impact**: All dashboard buttons and functions now work correctly

## Performance Metrics
- First run: 5-10 minutes (training + filtering)
- Subsequent: 2-3 minutes (cached)
- Filter exclusion: ~96.3% (815만 → 30만 with 1.0% threshold)
- ML filter inclusion: ~8.5% (target: 15% with auto-optimization)
- Target backtesting: 0.8-1.5 avg matches
- Dashboard refresh: Real-time with 1-second intervals
- Performance stats DB: Auto-saves every backtest session
- Auto-optimization: 30 Optuna trials, ~2 hours per cycle
- Threshold rollback: <3 seconds on performance degradation

## Warning Signs
- Average matches >3: Data contamination (winning numbers leaked into test)
- All ML models same prediction: Cache corruption, run clear_model_cache.py
- Memory >4GB: Reduce batch size in config.yaml (default: 10,000)
- Filter inclusion <10%: Threshold too restrictive, auto-optimizer will adjust
- Execution time >15 minutes: Check parallelization settings (14 workers default)
- No 2nd place winners in backtest: Bonus implementation working correctly
- Dashboard connection error: Check if Flask server is running on port 5001
- Auto-optimization rollback frequent: Check validation_rounds setting (default: 50)
- Optuna trials timeout: Reduce n_trials in optimizer config (default: 30)

## Environment Setup
- Python 3.8+ required (tested with 3.11.9)
- Install dependencies: `pip install -r requirements.txt`
- Key packages: tensorflow, scikit-learn, xgboost, flask, psutil, optuna
- Windows platform: Use command prompt or PowerShell for best compatibility
- Storage requirements: ~2GB for model cache, ~500MB for databases

## Development Practices

### Code Style
- UTF-8 encoding for all files
- Type hints encouraged for new functions
- Logging over print statements
- Configuration via YAML files (config.yaml, configs/adaptive_filter_config.yaml)

### Database Access Pattern
```python
from src.core.db_manager import DatabaseManager

db = DatabaseManager()
# Always use context manager or ensure proper cleanup
with db:
    numbers = db.get_numbers_with_bonus()  # Preferred method
    # NOT db.get_all_rounds() - doesn't exist
```

### Testing Guidelines
- Run tests before committing changes
- ASCII output for Windows compatibility (no emoji in tests)
- Mock database calls for unit tests
- Integration tests use test databases

## Korean Terms
- 회차 (hoecha): Round/Draw number
- 당첨번호 (dangcheom-beonho): Winning numbers
- 필터 (pilteo): Filter
- 예측 (yecheuk): Prediction
- 동행복권: Official lottery operator
- 보너스: Bonus number (for 2nd place)