---
name: Lotto Backtester
description: Expert in backtesting framework, performance validation, rank calculation, and auto-optimization with Optuna for lotto system
---

# Lotto Backtester Skill

전문 분야: 백테스팅 프레임워크, 성능 검증, 등수 계산, Optuna 자동 최적화

## Core Responsibilities

### 1. Backtesting Framework
- **OptimizedBacktestingFramework** (`src/backtesting/optimized_backtesting_framework.py`)
  - 10 workers, chunk size 20, cache size 100
  - Bonus number support for 2nd place calculation
  - Parallel processing for historical validation
- **BacktestingFramework** (`src/backtesting/backtesting_framework.py`)
  - Legacy framework, still functional
  - Complete historical analysis capability

### 2. Rank Calculation System
**RankCalculator** (`src/utils/rank_calculator.py`):
- **1등**: 6 matches
- **2등**: 5 matches + bonus
- **3등**: 5 matches
- **4등**: 4 matches
- **5등**: 3 matches

**Bonus Logic**:
```python
from src.utils.rank_calculator import RankCalculator

calc = RankCalculator()
rank = calc.calculate_rank(
    prediction=[1, 2, 3, 4, 5, 6],
    winning_numbers=[1, 2, 3, 4, 5, 7],
    bonus_number=6  # 5 matches + bonus = 2nd place
)
# Returns: 2
```

### 3. Auto-Optimization System
**ThresholdOptimizer** (`src/core/threshold_optimizer.py`):
- **Algorithm**: Bayesian optimization using Optuna TPE sampler
- **Cumulative Learning**: Study persists across restarts (25 → 50 → 75... trials)
- **Study Name**: `lotto_threshold_optimization` (fixed for continuity)
- **Checkpoint System**: `OptimizationCheckpointManager` saves/restores state
- **Resume Capability**: Automatically loads previous trials

**SmartAutoLearning** (`src/core/smart_auto_learning.py`):
- **24-hour cycle**: Daily at 3AM (configurable in KST timezone)
- **25 trials per run**: Cumulative across sessions
- **Safety features**: Auto-rollback if performance degrades >10%
- **Validation**: 50 recent rounds (configurable)

**Management Commands**:
```bash
# Check cumulative optimization progress
python src/scripts/check_optimization_status.py

# Reset study and start from 0
python src/scripts/check_optimization_status.py --reset

# Check auto-learning status
python src/scripts/check_auto_learning_status.py
```

### 4. Performance Metrics
**PerformanceStatsManager** (`src/core/performance_stats_manager.py`):
- **Automatic tracking**: During backtesting operations
- **Metrics stored**:
  - Average matches: Mean number of matching numbers
  - Max matches: Best performance in session
  - Filter inclusion rates: Percentage of predictions passing filters
- **Database**: `performance_stats.db` (434MB, 4.7M rows)
- **12 strategic indexes**: For 10,000x query performance

**PerformanceMetrics** (`src/core/performance_metrics.py`):
- **Unified scoring system**: Single source of truth
- **Three score types**:
  - Normalized (0-1): Use for comparisons and optimization
  - Raw (0-6): Store in database for integrity
  - Composite (0-100): Display only, NOT for decisions
- **Key functions**:
  - `normalize_score()`: Convert raw to normalized
  - `calculate_overall_score()`: Compute composite score
  - `compare_performance()`: Compare two performance sets

### 5. Continuous Improvement System
**ImprovedAutoImprovementManager** (`src/optimization/improved_auto_improvement_manager.py`):
- **Singleton pattern**: Coordinates all improvement systems
- **Checkpoint integration**: Persistent state across restarts
- **Components**:
  - ThresholdOptimizer: Parameter optimization
  - SmartAutoLearning: Daily learning cycles
  - ContinuousImprovementEngine: Real-time adjustments

**OptimizationCheckpointManager** (`src/core/optimization_checkpoint_manager.py`):
- **Storage**: `data/optimization_checkpoint.json`
- **State tracking**: Trials, best parameters, performance history
- **Resume capability**: Automatic recovery after interruption

### 6. Performance Targets
**Backtesting Targets** (`configs/adaptive_filter_config.yaml`):
- **Min average matches**: 0.6 (acceptable lower bound)
- **Max average matches**: 2.0 (acceptable upper bound)
- **Target average**: 0.8-1.5 (optimal range)
- **Warning threshold**: >3.0 (data contamination)
- **Filter inclusion**: >10% (ML integration target: 15%)

### 7. Common Issues & Solutions

#### Average Matches >3
- **Symptom**: Unrealistically high performance
- **Cause**: Data contamination (winning numbers leaked into test set)
- **Fix**: Check data splitting logic in backtesting framework

#### All ML Models Same Prediction
- **Symptom**: Identical predictions across models
- **Cause**: Cache corruption
- **Fix**: `python src/scripts/clear_model_cache.py`

#### Auto-Optimization Rollback Frequent
- **Symptom**: Frequent rollbacks during optimization
- **Cause**: `validation_rounds` too small or unstable thresholds
- **Fix**: Increase `validation_rounds` in config (default: 50)

#### Optuna Trials Timeout
- **Symptom**: Optimization takes >2 hours per cycle
- **Cause**: `n_trials` too high or complex objective function
- **Fix**: Reduce `n_trials` in optimizer config (default: 30)

#### No 2nd Place Winners
- **Status**: Working correctly (bonus implementation complete)
- **Verification**: Check `get_numbers_with_bonus()` returns bonus

### 8. Key Files
- `src/backtesting/optimized_backtesting_framework.py`: Main backtesting engine
- `src/backtesting/backtesting_framework.py`: Legacy framework
- `src/utils/rank_calculator.py`: Prize rank calculation with bonus
- `src/core/threshold_optimizer.py`: Bayesian optimization with Optuna
- `src/core/smart_auto_learning.py`: Daily auto-learning cycle
- `src/core/performance_stats_manager.py`: Performance tracking
- `src/core/performance_metrics.py`: Unified scoring system
- `src/optimization/improved_auto_improvement_manager.py`: Orchestration
- `src/core/optimization_checkpoint_manager.py`: Checkpoint management

### 9. Critical Rules
- ALWAYS validate on 50+ recent rounds
- USE PerformanceMetrics.normalize_score() for comparisons
- MONITOR average matches (0.6-2.0 acceptable, >3 warning)
- CHECK bonus number handling in rank calculation
- VERIFY cumulative trial count with check_optimization_status.py
- ROLLBACK if performance degrades >10%
- ENSURE checkpoint saves before program exit

## When to Invoke This Skill

- Backtesting setup or validation
- Performance metric analysis
- Auto-optimization configuration
- Rank calculation verification
- Threshold tuning and optimization
- Performance degradation investigation
- Cumulative learning management

## Example Commands

```python
# Run backtesting
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework

framework = OptimizedBacktestingFramework()
results = framework.run_backtest(
    predictions=my_predictions,
    start_round=1000,
    end_round=1186
)

# Calculate rank with bonus
from src.utils.rank_calculator import RankCalculator

calc = RankCalculator()
rank = calc.calculate_rank(
    prediction=[3, 7, 19, 28, 35, 42],
    winning_numbers=[3, 7, 19, 28, 35, 40],
    bonus_number=42  # 2nd place (5 + bonus)
)

# Use unified performance metrics
from src.core.performance_metrics import PerformanceMetrics

pm = PerformanceMetrics()
normalized = pm.normalize_score(avg_matches=1.2, max_matches=4, inclusion_rate=0.15)
composite = pm.calculate_overall_score(1.2, 4, 0.15)
```

```bash
# Optimization management
python src/scripts/check_optimization_status.py        # View cumulative progress
python src/scripts/check_optimization_status.py --reset  # Start fresh
python src/scripts/check_auto_learning_status.py       # Check learning status
```

## Performance Metrics
- Backtest accuracy: 0.8-1.5 avg matches (acceptable)
- Optimization cycle: ~1.5 hours per 25 trials
- Cumulative trials: Persistent across restarts
- Rollback time: <3 seconds
- Validation rounds: 50 recent rounds default
- Checkpoint save: <100ms
