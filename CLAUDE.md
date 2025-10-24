# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ CRITICAL FILE MANAGEMENT RULES

**NEVER create temporary files in project root!** This is a professional codebase, not a playground.

### File Creation Rules (MANDATORY)
1. **NO TEST FILES in root**: `test_*.py`, `check_*.py`, `verify_*.py` → Use `tests/` directory
2. **NO TEMP DOCS in root**: `*_FIX.md`, `*_SUMMARY.md`, `*_REPORT.md` → Use `docs/` or don't create
3. **NO JSON dumps in root**: `*.json` results → Use `results/` or `data/` directory
4. **NO TEMP LOGS in root**: `temp_*.txt`, `*.log` → Use `logs/` directory

### Allowed Root Files ONLY
- `main.py` - Entry point
- `README.md` - User documentation
- `CLAUDE.md` - This file (AI guidance)
- `AGENTS.md` - Agent configuration
- `requirements.txt` - Dependencies
- `pytest.ini` - Test configuration
- `.gitignore` - Git configuration
- `.coverage` - Coverage report

### File Cleanup
```bash
# Clean up temporary files (if you made a mess)
python cleanup_temp_files.py
```

### Enforcement
- `.gitignore` automatically excludes temporary file patterns
- Any violation of these rules will be called out immediately
- Professional standards: Keep it clean, keep it organized

## Project Overview
Korean lottery (로또) prediction system using ML/AI to analyze historical patterns. Applies probability-based filtering to reduce 8.14M combinations to ~300K (with 1.0% threshold), improving odds by 27x through pattern exclusion.

**Repository Path**: `D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\`

## Common Commands
```bash
# Main Program Execution (All-in-One)
python main.py                           # ⚡ Run EVERYTHING automatically (F5 in IDE)
                                         #    ✅ Data collection & auto-update on new rounds
                                         #    ✅ Pattern analysis & filter updates
                                         #    ✅ ML/AI predictions
                                         #    ✅ Dashboard (http://127.0.0.1:5001)
                                         #    ✅ Background optimization (무한 반복)
                                         #    ✅ New round auto-detection

# Optional Flags (선택사항)
python main.py --skip-fetch              # Skip data collection
python main.py --ml-only                 # ML/AI analysis only
python main.py --no-parallel             # Disable parallel processing
python main.py --lstm --no-ensemble      # Use specific ML models
python main.py --no-monte-carlo          # Skip Monte Carlo simulation

# Testing
pip install pytest pytest-cov            # Install test dependencies
python -m pytest tests/                  # Run all tests
python -m pytest tests/test_file.py -v   # Run single test file with verbose output
python -m pytest tests/ -k "test_name"   # Run specific test by name
python -m pytest --cov=src tests/        # Run tests with coverage report
python -m pytest -m unit                 # Run unit tests only
python -m pytest -m integration          # Run integration tests only

# Maintenance & Troubleshooting
python src/scripts/clear_model_cache.py  # Clear corrupted model cache (1.7GB cache)
type logs\lotto_app.log                  # View logs on Windows (use tail -f on Linux/Mac)
findstr ERROR logs\lotto_app.log         # Filter errors only (Windows)
python src/scripts/kill_db_locks.py      # Release database locks if stuck

# Dashboard & Monitoring (Port 5001)
# NOTE: Dashboard starts automatically with main.py
python src/scripts/enhanced_dashboard_v2.py  # Manual dashboard start (if needed)
python src/scripts/start_dashboard.py        # Alternative dashboard start

# Data Management
python src/scripts/complete_bonus_collection.py    # Collect missing bonus numbers
python src/scripts/optimize_databases.py           # Optimize and compact databases
python src/scripts/manual_update_winning_numbers.py # Manual update winning numbers

# Auto-Learning & Threshold Optimization
# NOTE: Background optimization runs automatically with main.py
python src/scripts/check_auto_learning_status.py    # Check auto-learning status
python src/scripts/check_optimization_status.py     # Check optimization progress (cumulative trials)
python src/scripts/check_optimization_status.py --reset  # Reset study (start from 0)

# Analysis & Debugging Scripts
python src/scripts/analyze_filters.py               # Analyze filter effectiveness
python src/scripts/analyze_filter_correlations.py   # Filter correlation analysis
python src/scripts/validate_predictions.py          # Validate generated predictions
python src/scripts/auto_cache_cleaner.py           # Clean cache automatically
python src/scripts/analyze_lotto_statistics.py      # Analyze historical patterns and statistics
```

## Architecture Overview

### Core Data Flow
```
1. Data Collection → 2. Filtering (815만→30만) → 3. ML Prediction → 4. Final Selection → 5. Dashboard Display
```

### Complete Automation System (F5 실행으로 모든 것 자동화)

**Main Execution (`python main.py` 또는 F5)에서 자동 실행되는 모든 기능**:

1. **데이터 수집 & 자동 업데이트**
   - 동행복권 사이트에서 최신 당첨번호 자동 수집
   - 새 회차 감지 시 자동 패턴 재분석 및 필터 업데이트
   - 프로그램 재시작 시 동기화 자동 확인

2. **백그라운드 무한 최적화** (체크포인트 기반)
   - 별도 스레드에서 자동 실행 (사용자 작업 방해 없음)
   - 140개 파라미터 조합 사이클 무한 반복 (0→140→280→420...)
   - Optuna TPE (Tree-structured Parzen Estimator) sampler로 지능적 파라미터 탐색
   - 최적 파라미터 자동 적용 및 체크포인트 저장
   - **별도 명령 불필요** - main.py 실행만으로 자동 시작
   - **구버전 Grid Search(25회) 비활성화됨**
   - 체크포인트 시스템: `OptimizationCheckpointManager`로 진행 상황 저장 및 복구

3. **웹 대시보드**
   - 포트 5001에서 자동 시작
   - 실시간 예측 결과 표시
   - "새 예측 생성" 버튼으로 언제든 예측 가능

4. **시스템 건강 모니터링**
   - SystemHealthChecker: 자동 건강 체크
   - AutoRepairSystem: 실시간 문제 감지 및 자동 수리

**완전 자동화 시나리오**:
- **시나리오 1 (프로그램 실행 중)**: 새 로또 번호 발표 → AutoScheduler 자동 감지 → 패턴/필터/ML 자동 업데이트
- **시나리오 2 (프로그램 재시작)**: main.py 시작 → SystemStateManager 동기화 확인 → 필요시 자동 업데이트

### Critical Architecture Points

#### 0. TensorFlow/Keras Logging Configuration
- **Environment Variables**: Always set before imports to prevent verbose output
  - `TF_ENABLE_ONEDNN_OPTS='0'`: Disables oneDNN optimizations logging
  - `TF_CPP_MIN_LOG_LEVEL='3'`: Shows only ERROR messages
  - `ABSL_LOGGING_VERBOSITY='1'`: Suppresses ABSL framework logs
- **Matplotlib Backend**: Set to 'Agg' (non-interactive) to prevent tkinter errors
- **Warnings Suppression**: All TensorFlow/Keras warnings filtered in main.py (lines 34-49)
- **Note**: These settings are critical for clean console output and must be maintained

#### 1. ML-Filter Disconnect Issue
- **Problem**: ML learns from 1,186 historical winning numbers (시계열 패턴)
- **Filter**: Reduces 8.14M to ~300K combinations (probability <1.0% excluded)
- **Result**: ML predictions mostly fail filter validation (~8.5% inclusion rate)
- **Solution**: Implemented in `main.py:generate_final_predictions_enhanced()` (line ~1207):
  - ML relaxed threshold: 0.5% (configurable in adaptive_filter_config.yaml)
  - Similar combination matching when ML fails filters
  - Relaxable filters: average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section, sum_range, max_gap

#### 2. Probability Threshold Configuration
- **File**: `configs/adaptive_filter_config.yaml`
- **Key**: `global_probability_threshold` (adaptive_options section)
- **Default Range**: 0.3 to 3.0 (auto-adjusted by ThresholdOptimizer)
- **Impact**: Lower value = fewer exclusions = larger pool
  - 0.5% → ~500K combinations
  - 1.0% → ~300K combinations
  - 2.0% → ~200K combinations
- **Note**: Threshold directly affects filter pool size and computational requirements
- **Auto-Optimization**: ThresholdOptimizer continuously adjusts this value for optimal performance using Optuna

**ML Relaxed Threshold**:
- **Purpose**: Allows ML predictions to pass filter validation with relaxed criteria
- **Default**: 0.5% (configurable in adaptive_filter_config.yaml)
- **Goal**: Improves ML prediction inclusion rate from ~8.5% to target 15%
- **Rule**: Should be lower than global threshold for better ML integration

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
- **PerformanceMetrics**: Unified scoring system (single source of truth for all formulas)
  - **Normalized scores (0-1)**: Use for comparisons and optimization decisions
  - **Raw scores (0-6)**: Store in database for data integrity
  - **Composite scores (0-100)**: Display only, NOT for decisions
  - **Functions**: `normalize_score()`, `calculate_overall_score()`, `compare_performance()`
  - Location: `src/core/performance_metrics.py`
  - Quick Ref: `docs/PERFORMANCE_METRICS_QUICK_REF.md`
  - Full Docs: `PERFORMANCE_SCORING_FIX.md`
- **Metrics tracked**: Average matches, max matches, filter inclusion rates
- **Integration**: Automatically saves stats during backtesting
- Location: `src/core/performance_stats_manager.py`

#### 6. Auto-Learning & Threshold Optimization System
- **ThresholdOptimizer**: Bayesian optimization using Optuna for finding optimal thresholds
  - **Cumulative Learning**: Study persists across program restarts (25 → 50 → 75 → ... trials)
  - **Fixed Study Name**: `lotto_threshold_optimization` for continuous learning
  - **Resume Capability**: Automatically loads previous trials and continues from where it left off
- **SmartAutoLearning**: 24-hour cycle automatic optimization with rollback capability
- **FilterPerformanceTracker**: Real-time filter effectiveness monitoring
- **Optimization cycle**: Daily at 3AM (configurable), 25 trials per run (cumulative)
- **Safety features**: Auto-rollback if performance degrades >10%, validation on 50 recent rounds
- **Management**: `check_optimization_status.py` to view cumulative trials, `--reset` to start fresh
- Files: `src/core/threshold_optimizer.py`, `src/core/smart_auto_learning.py`

#### 7. Dashboard System (Enhanced v2)
- **Port**: 5001 (Flask web server)
- **Auto-start**: Dashboard starts automatically when running `main.py`
- **Features**: Real-time predictions display, on-demand prediction generation, performance metrics
- **Prediction Button**: Generate 5 new prediction sets without re-running main.py
- **JavaScript Issues**: Ensure proper escaping of newlines in Python strings (\\n not \n)
- File: `src/scripts/enhanced_dashboard_v2.py`

#### 8. System State Management
- **SystemStateManager**: Tracks system state across restarts (`src/core/system_state_manager.py`)
- **State file**: `data/system_state.json` stores last round, pattern analysis, filter updates
- **Auto-sync**: Detects new rounds and automatically triggers updates
- **Integration**: Works with AutoScheduler for continuous monitoring

#### 9. Threshold Management System
- **ThresholdManager**: Centralized threshold management with singleton pattern (`src/core/threshold_manager.py`)
- **Single Source of Truth**: All components use same threshold values
- **Observer Pattern**: Automatic propagation of threshold changes to all subscribers
- **Decimal Precision**: Uses Decimal type to eliminate floating-point errors
- **Change Tracking**: Logs all threshold changes for debugging and audit
- **Configuration**: Loads from `configs/adaptive_filter_config.yaml`

#### 10. Checkpoint & Improvement Management
- **OptimizationCheckpointManager**: Persistent checkpoint system for optimization state (`src/core/optimization_checkpoint_manager.py`)
- **Checkpoint Storage**: `data/optimization_checkpoint.json` stores trials, best parameters, performance history
- **Resume Capability**: Automatically resumes optimization from last checkpoint after interruption
- **ImprovedAutoImprovementManager**: Singleton manager coordinating all auto-improvement systems (`src/optimization/improved_auto_improvement_manager.py`)
- **Integration**: Works with ThresholdOptimizer, SmartAutoLearning, ContinuousImprovementEngine

#### 11. Memory & Cache Management
- **MemoryMonitor**: Real-time memory usage tracking with threshold alerts (`src/utils/memory_monitor.py`)
- **AutoCacheCleaner**: Intelligent cache cleanup based on age and usage patterns (`src/scripts/auto_cache_cleaner.py`)
- **Cache Strategy**:
  - Model cache: 7-day TTL, can grow to 1.7GB+
  - Pattern cache: Managed by PatternsDB with LRU eviction
  - Automatic cleanup on memory pressure (>80% usage)
- **Manual Cache Management**: `python src/scripts/auto_cache_cleaner.py --force` for immediate cleanup

### Key Components

#### Filter System (16 filters)
All inherit from `BaseFilter` in `src/filters/base_filter.py`:
- **Critical filters** (always applied): odd_even, consecutive, sum_range, max_gap
- **Relaxable filters** (ML bypass): average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section
- **Adaptive system**: `AdaptiveProbabilityFilter` in `src/core/adaptive_probability_filter.py` updates criteria dynamically
- **Management layers**:
  - `FilterManager` (`src/core/filter_manager.py`): Parallel processing coordination
  - `IntegratedFilterManager` (`src/core/integrated_filter_manager.py`): Unified filter orchestration
  - `AdaptiveFilterOptimizer` (`src/optimization/adaptive_filter_optimizer.py`): Automatic criteria optimization

#### ML Models
- **LSTM**: Time-series on 50-round sequences (`src/ml/lstm_predictor.py`)
- **Ensemble**: RF + XGBoost + NN (`src/ml/ensemble_predictor.py`)
- **Monte Carlo**: 6,000 simulations with 8 parallel workers (`src/probabilistic/monte_carlo_simulator.py`)
- **Bayesian**: Probabilistic inference (`src/probabilistic/bayesian_inference.py`)
- **Fractal**: Chaos theory patterns (`src/advanced/fractal_pattern_analyzer.py`)
- **Model coordination**: Predictions combined via weighted averaging in `main.py`

#### Integration Points
- `main.py:generate_final_predictions_enhanced()` (line ~1207): ML-filter integration logic with relaxed thresholds
- `src/utils/improved_prediction_generator.py`: Enhanced prediction generation with intelligent fallback strategies
  - Automatically used when available (USE_IMPROVED_GENERATOR flag)
  - Provides better ML-filter integration and similar combination matching
- `src/backtesting/optimized_backtesting_framework.py`: Performance validation with bonus number support
- `src/core/integrated_filter_manager.py`: Combines adaptive and static filtering
- `src/utils/rank_calculator.py`: Prize rank calculation (1-5등) with bonus logic
- `src/scripts/enhanced_dashboard_v2.py`: Current dashboard implementation (port 5001)

## Critical Implementation Details

### Parallel Processing Configuration
- **FilterManager**: ProcessPoolExecutor (12 workers default at 75% CPU utilization)
- **Batch size**: 60,000 combinations (optimized for 31GB memory system)
- **Memory limits**: 80% max usage threshold, 2GB max batch memory, 250MB per worker
- **Database pool**: 8 connections with context manager pattern
- **Dynamic allocation**: Adaptive batch sizing and worker scaling based on system resources
- **Configuration**: All settings in `config.yaml` under `filter_manager` and `filtering` sections
- **Windows compatibility**: System optimized for Windows platform with appropriate path handling

### DatabaseManager Methods
- Use `get_all_winning_numbers()` or `get_all_numbers()` for basic data
- `get_numbers_with_bonus()`: Returns List[Tuple[round, (n1,n2,n3,n4,n5,n6,bonus)]]
- `get_winning_numbers_before(round_num)`: For backtesting, gets numbers before specific round
- NOT `get_all_rounds()` (doesn't exist)
- `fetch_and_save_lotto_data()`: Updates from official site (동행복권)

### File Encoding & Platform Compatibility
- **Encoding**: Always use `encoding='utf-8'` for file operations (Korean text support)
- **Testing**: Replace emoji (✅, ❌) with ASCII ([O], [X]) for Windows compatibility
- **Paths**: Use raw strings (`r"path"`) or forward slashes, avoid backslashes
- **Windows-specific commands**:
  - Log viewing: `type logs\lotto_app.log` (not `cat`)
  - Error filtering: `findstr ERROR logs\lotto_app.log` (not `grep`)
  - Directory listing: `dir /b` (not `ls`)
- **Windows Reserved Names**: Never create files named: CON, PRN, AUX, NUL, COM1-9, LPT1-9
- **Console Output**: TensorFlow/Keras warnings suppressed via environment variables (see main.py:34-49)
- **Korean timezone**: pytz required for KST timezone handling (auto-scheduler dependency)
  - **Critical Dependency**: Do NOT remove pytz import from main.py (line 17)
  - Used by AutoScheduler for daily 3AM optimization scheduling in KST timezone
  - Removal will cause scheduler and time-based automation failures

### Bonus Number Handling
- Bonus number is 7th element in winning numbers tuple from `get_numbers_with_bonus()`
- Used for 2nd place (5 + bonus) prize calculation
- Backtesting now includes bonus matching for accurate rank calculation
- Complete collection script: `src/scripts/complete_bonus_collection.py`

## System Health & Auto-Repair

### Error Prevention System
- **Location**: `src/utils/error_prevention_system.py`
- **Features**: Proactive error detection, automatic validation, resource monitoring
- **Integration**: Automatically enabled in main.py execution flow

### Auto-Repair Capabilities
- **SystemHealthChecker**: Monitors database integrity, cache validity, model availability
- **AutoRepairSystem**: Automatically fixes common issues (corrupted cache, database locks, missing files)
- **Recovery Strategies**: Automatic rollback on performance degradation, checkpoint restoration

### Monitoring Tools
- **MemoryMonitor**: Real-time memory usage tracking with `log_memory()` decorator (`src/utils/memory_monitor.py`)
  - Automatic alerts when memory exceeds 80% threshold
  - Integration with all major components for tracking memory consumption
  - Usage: `@log_memory` decorator on memory-intensive functions
- **PerformanceStatsManager**: Records and analyzes system performance across sessions
  - Tracks average matches, max matches, filter inclusion rates
  - Historical performance comparison and trend analysis
- **FilterPerformanceTracker**: Real-time monitoring of filter effectiveness
  - Per-filter efficiency metrics and correlation analysis
  - Auto-adjustment recommendations based on performance data

## Known Issues & Solutions

### AdaptiveProbabilityFilter Match Filter Bug (FIXED 2024-08-28)
- **Issue**: Sequential check with `break` causing 4,5-match patterns not excluded
- **Location**: `src/core/adaptive_probability_filter.py:189-193`
- **Fix Applied**: Changed to check all patterns without early break
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

### JSON Parsing Errors in Filter Validation (FIXED 2025-10-10)
- **Issue**: "JSON 파싱 실패" and "JSON 형식 오류" warnings from concurrent writes
- **Root Cause**: Multiple parallel processes writing to same JSON file, file locking (fcntl) not available on Windows
- **Location**: `src/core/filter_validator.py:347-423`
- **Fix Applied**: Migrated from JSON file storage to SQLite database storage
  - Database: `results/filter_validation_YYYYMM.db`
  - Features: Built-in transaction management, automatic locking (30s timeout), UNIQUE constraints
  - Benefits: Cross-platform compatibility, no race conditions, guaranteed data integrity
- **Testing**: All unit tests passed (concurrent writes, duplicate prevention, query performance)
- **Impact**: No more JSON corruption, reliable concurrent writes from parallel processes
- **Documentation**: See `JSON_FIX_SUMMARY.md` for detailed technical information

### Performance Scoring Formula Inconsistency (FIXED 2025-10-14)
- **Issue**: Auto-improvement system making wrong optimization decisions (1.102 → 0.806 considered "worse")
- **Root Cause**: Two different scoring formulas existed across modules
  - Formula 1: `normalized_score = avg_matches / 2.0` (0-1 range)
  - Formula 2: Raw weighted average (0-6 range)
  - System compared apples to oranges when evaluating improvements
- **Fix Applied**: Created unified `PerformanceMetrics` class as single source of truth
  - Location: `src/core/performance_metrics.py`
  - Standardized on: Raw storage (0-6), normalized comparisons (0-1), composite display (0-100)
  - Updated 5 consumer files to use unified functions
- **Testing**: 44/44 unit tests passed, comprehensive coverage of all scenarios

### Missing Database Indexes (FIXED 2025-10-15)
- **Issue**: DELETE operations taking 2-5s on 4.7M row table, full table scans
- **Root Cause**: No indexes on frequently queried columns (session_id, round_num, created_at)
- **Impact**: 434MB performance_stats.db with slow cleanup operations and query performance
- **Fix Applied**: Added 12 strategic indexes to PerformanceStatsManager
  - Location: `src/core/performance_stats_manager.py:115-179`
  - Indexes: session_id, round_num, created_at, model_name, composite indexes
  - Automatic creation on initialization via `_create_indexes()` method
- **Performance Gain**: 10,000x improvement (2-5s → <1ms for DELETE, <0.1ms for SELECT)
- **Testing**: All queries now use index seeks, 12 indexes verified, integration tests passed
- **Documentation**: See `DATABASE_INDEX_FIX_SUMMARY.md` for detailed analysis

## Performance Metrics
- **Initial run**: 5-10 minutes (data collection + training + filtering)
- **Subsequent runs**: 2-3 minutes (leverages model cache)
- **Filter efficiency**: ~96.3% reduction (8.14M → 300K combinations typical)
- **ML integration**: ~8.5% inclusion rate (target: 15% with relaxed thresholds)
- **Backtest accuracy**: 0.8-1.5 avg matches (acceptable range: 0.6-2.0)
- **Dashboard**: Real-time updates, auto-refresh, runs on port 5001
- **Auto-optimization**:
  - Optuna TPE sampler with cumulative learning (0→25→50→75... trials)
  - ~1.5 hours per 25-trial cycle
  - Auto-rollback in <3 seconds if performance degrades >10%
  - Study persistence across program restarts
- **System utilization**:
  - CPU: 12 workers (75% of 16 cores)
  - Memory: 60K batch size, 250MB per worker
  - Monte Carlo: 6,000 simulations, 8 workers, batch 750
  - Backtesting: 10 workers, chunk 20, cache 100
  - LSTM: Batch 64, 50 epochs
  - Ensemble: 100 estimators, 4 parallel jobs

## Warning Signs
- Average matches >3: Data contamination (winning numbers leaked into test)
- All ML models same prediction: Cache corruption, run clear_model_cache.py
- Memory >4GB: Reduce batch size in config.yaml (default: 60,000) or run auto_cache_cleaner.py
- Filter inclusion <10%: Threshold too restrictive, auto-optimizer will adjust
- Execution time >15 minutes: Check parallelization settings (12 workers default at 75% CPU)
- No 2nd place winners in backtest: Bonus implementation working correctly
- Dashboard connection error: Check if Flask server is running on port 5001
- Auto-optimization rollback frequent: Check validation_rounds setting (default: 50)
- Optuna trials timeout: Reduce n_trials in optimizer config (default: 30)
- Memory alerts frequent: Monitor with MemoryMonitor, check cache size (1.7GB+ model cache)
- Checkpoint corruption: Delete `data/optimization_checkpoint.json` and restart optimization

## Environment Setup
- **Python**: 3.8+ required (tested with 3.11.9)
- **Install**: `pip install -r requirements.txt`
- **Key packages**: tensorflow>=2.8.0, scikit-learn>=1.0.0, xgboost>=1.5.0, flask>=2.0.0, psutil>=5.9.0, optuna>=3.0.0, schedule>=1.2.0, pytz (required for KST timezone), PyWavelets>=1.1.0
- **Additional ML**: catboost>=1.2, lightgbm>=3.3.0, keras>=2.8.0
- **Testing**: pytest>=7.0.0, pytest-cov>=3.0.0, Flask-WTF, Flask-Limiter
- **Code Quality**: black, flake8, pylint (for development)
- **Platform**: Windows (command prompt or PowerShell recommended)
- **Storage**: ~2GB for model cache, ~500MB for databases
- **Ports**: 5001 (Flask dashboard server - ensure available)
- **Memory**: 4GB+ recommended, 8GB+ optimal (31GB available optimally utilized)
- **CPU**: Multi-core recommended (optimized for 16 cores, default 12 workers at 75%)

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
- **Test Markers**: Use `@pytest.mark.unit` for unit tests, `@pytest.mark.integration` for integration tests
- **Test Isolation**: Each test should be independent and not rely on execution order
- **Fixtures**: Use pytest fixtures in `tests/conftest.py` for shared test resources
- **Coverage Target**: Aim for >80% code coverage for new features

## Important Configuration Files
- **`config.yaml`**: Main system configuration (workers, batch sizes, parallel processing)
  - Controls: FilterManager workers (12), batch sizes (60K), memory allocation (250MB/worker)
  - ML settings: Monte Carlo simulations, backtesting workers, LSTM/ensemble parameters
  - Database: Connection pool size (16), batch memory limits
- **`configs/adaptive_filter_config.yaml`**: Adaptive filter thresholds and probability settings
  - Controls: Dynamic filter criteria, probability thresholds, ML integration settings
  - Key settings: `global_probability_threshold` (2.0), `ml_relaxed_threshold` (0.5)
  - Auto-learning: Optimization targets, adjustment intervals, safety mode
  - Backtesting targets: Min/max average matches, target inclusion rate
- **`requirements.txt`**: Python dependencies (use exact versions for stability)
- **`logs/lotto_app.log`**: Main application log file (auto-rotates at 10MB)
- **`data/system_state.json`**: System state tracking (auto-generated)
- **`.github/workflows/tests.yml`**: CI/CD pipeline configuration

## Quick Reference: Critical Decisions

### When Modifying Filters
1. **Always test with backtesting**: Use `OptimizedBacktestingFramework` to validate changes
2. **Check ML integration**: Ensure relaxable filters include new filter types in `main.py:generate_final_predictions_enhanced()`
3. **Update config files**: Both `config.yaml` and `configs/adaptive_filter_config.yaml`
4. **Monitor performance**: Watch for average matches >3 (data contamination)
5. **Use ThresholdManager**: Access thresholds via singleton instance, never hardcode values
6. **Observer Pattern**: Register components that need threshold updates as observers

### When Adding ML Models
1. **Cache integration**: Use hash-based versioning in `cache/models/`
2. **Performance tracking**: Register with `PerformanceStatsManager`
3. **Error handling**: Handle TensorFlow/Keras warnings (see main.py:34-49)
4. **Integration point**: Add to `main.py:generate_final_predictions_enhanced()`

### When Optimizing Performance
1. **Parallel processing**: Configure workers in `config.yaml` (max_workers, batch_size)
2. **Memory limits**: Monitor with `MemoryMonitor`, adjust batch sizes if >4GB
3. **Database access**: Always use context managers (`with db:`)
4. **Caching strategy**: Leverage `IntelligentCacheManager` for repeated operations

## Korean Terms & Glossary
- **회차 (hoecha)**: Round/Draw number
- **당첨번호 (dangcheom-beonho)**: Winning numbers
- **필터 (pilteo)**: Filter
- **예측 (yecheuk)**: Prediction
- **동행복권**: Official lottery operator (https://www.dhlottery.co.kr)
- **보너스**: Bonus number (for 2nd place)
- **시계열 패턴**: Time-series pattern
- **자동 학습**: Auto-learning
- **임계값**: Threshold
- **백테스팅**: Backtesting
- **포함률**: Inclusion rate (percentage of ML predictions passing filters)
- **완화된 필터**: Relaxed filter (allows ML predictions with lower thresholds)

## System Architecture Notes

### Multi-Layer Filter Architecture
1. **CombinationManager**: Generates all 8.14M combinations
2. **AdaptiveProbabilityFilter**: First-stage filtering based on historical pattern probabilities
3. **FilterManager**: Applies 16 individual filters in parallel (12 workers)
4. **IntegratedFilterManager**: Orchestrates both adaptive and static filtering
5. **ML Prediction Integration**: Relaxed criteria for ML-generated combinations

### Continuous Improvement Loop
1. **SmartAutoLearning**: Runs daily at 3AM, optimizes thresholds (`src/core/smart_auto_learning.py`)
2. **ThresholdOptimizer**: Bayesian optimization (Optuna) on filter criteria (`src/core/threshold_optimizer.py`)
   - Uses cumulative learning with persistent study across restarts
   - Checkpoint-based resumption via OptimizationCheckpointManager
3. **ContinuousImprovementEngine**: Coordinates all improvement systems (`src/core/continuous_improvement_engine.py`)
4. **PerformanceStatsManager**: Tracks historical performance across sessions
5. **Auto-rollback**: Reverts changes if performance degrades >10%
6. **ImprovedAutoImprovementManager**: Singleton orchestrating all auto-improvement components
   - Manages checkpoint state and recovery
   - Coordinates between optimizer, learning system, and improvement engine

### Database Connections
- Primary DB connection pool: 8 connections (`config.yaml`)
- All database access should use context managers (`with db:`)
- Specialized databases in `src/core/specialized_databases.py`: PatternsDB, FilterDB, PerformanceDB
- Database schema migrations via `src/utils/db_migrator.py`

### CI/CD Pipeline
- **GitHub Actions**: Automated testing on push/PR (`.github/workflows/tests.yml`)
- **Test Matrix**: Python 3.8, 3.9, 3.10, 3.11 on Windows
- **Test Markers**: `@pytest.mark.unit` and `@pytest.mark.integration` for test classification
- **Code Coverage**: Codecov integration with XML reports
- **Linting**: Black, Flake8, Pylint (max line length 120)
- **Note**: Tests run on Windows platform to match production environment