---
name: Lotto Troubleshooter
description: Expert in diagnosing and fixing common issues, system health checks, auto-repair, memory management, and error prevention
---

# Lotto Troubleshooter Skill

전문 분야: 일반적인 문제 진단 및 해결, 시스템 건강 체크, 자동 복구, 메모리 관리, 에러 방지

## Core Responsibilities

### 1. System Health Monitoring
**SystemHealthChecker** (`src/utils/system_health_checker.py`):
- Database integrity checks
- Cache validity verification
- Model availability validation
- Automatic health reports

**AutoRepairSystem** (`src/utils/auto_repair_system.py`):
- Automatic issue detection
- Common problem fixes
- Recovery strategies:
  - Corrupted cache → Clear and rebuild
  - Database locks → Release and retry
  - Missing files → Regenerate

**ErrorPreventionSystem** (`src/utils/error_prevention_system.py`):
- Proactive error detection
- Automatic validation
- Resource monitoring
- Integration in main.py execution flow

### 2. Memory Management
**MemoryMonitor** (`src/utils/memory_monitor.py`):
- **Real-time tracking**: `@log_memory` decorator
- **Automatic alerts**: When memory exceeds 80% threshold
- **Integration**: All major components tracked
- **Usage**: Decorator on memory-intensive functions

**AutoCacheCleaner** (`src/scripts/auto_cache_cleaner.py`):
- **Intelligent cleanup**: Based on age and usage patterns
- **Cache strategy**:
  - Model cache: 7-day TTL, up to 1.7GB+
  - Pattern cache: LRU eviction by PatternsDB
  - Auto-cleanup: On memory pressure (>80%)
- **Manual cleanup**: `python src/scripts/auto_cache_cleaner.py --force`

**Memory Thresholds**:
- **Normal**: 0-60% (full operations)
- **Warning**: 60-80% (optimization recommended)
- **Critical**: >80% (automatic cleanup triggers)
- **Emergency**: >90% (defer non-critical operations)

### 3. Common Issues & Quick Fixes

#### StandardScaler AttributeError
```bash
# Symptom: AttributeError during ML model loading
# Cause: Corrupted model cache
# Fix:
python src/scripts/clear_model_cache.py
```

#### Database Locks
```bash
# Symptom: "Database is locked" errors
# Cause: Stale connections or interrupted operations
# Fix:
python src/scripts/kill_db_locks.py
```

#### JSON Parsing Errors (FIXED 2025-10-10)
```
# Symptom: "JSON 파싱 실패" from concurrent writes
# Cause: Multiple processes writing to same JSON file
# Status: FIXED - Migrated to SQLite with transaction management
# No action needed - automatic since October 2025
```

#### Bonus Number Issues (FIXED 2025-09-12)
```bash
# Symptom: Bonus numbers missing or random in dashboard
# Status: FIXED - get_numbers_with_bonus() properly implemented
# Verification:
python -c "from src.core.db_manager import DatabaseManager; db = DatabaseManager(); print(db.get_numbers_with_bonus()[-5:])"
```

#### Dashboard JavaScript Errors (FIXED 2025-09-13)
```
# Symptom: Template literals in Python strings causing syntax errors
# Status: FIXED - Proper newline escaping (\\n not \n)
# Location: enhanced_dashboard_v2.py generateNewPredictions function
```

#### Missing Database Indexes (FIXED 2025-10-15)
```
# Symptom: DELETE operations taking 2-5s on 4.7M row table
# Status: FIXED - 12 strategic indexes added automatically
# Performance: 10,000x improvement (2-5s → <1ms)
# Verification: Check query execution time
```

#### Performance Scoring Inconsistency (FIXED 2025-10-14)
```
# Symptom: Wrong optimization decisions (1.102 → 0.806 considered "worse")
# Status: FIXED - Unified PerformanceMetrics class
# Rule: Always use PerformanceMetrics.normalize_score() for comparisons
```

### 4. Warning Signs & Actions

#### Average Matches >3
- **Warning**: Data contamination (winning numbers leaked into test)
- **Action**: Check backtesting data splitting logic
- **Impact**: Unrealistic performance metrics

#### All ML Models Same Prediction
- **Warning**: Cache corruption
- **Action**: Run `clear_model_cache.py`
- **Impact**: ML predictions unreliable

#### Memory >4GB
- **Warning**: Excessive memory usage
- **Action**: Reduce batch size in config.yaml or run auto_cache_cleaner.py
- **Impact**: System slowdown or crashes

#### Filter Inclusion <10%
- **Warning**: Threshold too restrictive
- **Action**: Auto-optimizer will adjust automatically
- **Impact**: ML-filter integration poor

#### Execution Time >15 Minutes
- **Warning**: Parallelization issues
- **Action**: Check worker settings (default: 12 workers at 75% CPU)
- **Impact**: Performance degradation

#### Dashboard Connection Error
- **Warning**: Flask server not running
- **Action**: Check if port 5001 is available and server started
- **Impact**: No web interface access

#### Auto-Optimization Rollback Frequent
- **Warning**: Unstable optimization
- **Action**: Increase validation_rounds (default: 50)
- **Impact**: Optimization effectiveness reduced

#### Checkpoint Corruption
- **Warning**: Cannot resume optimization
- **Action**: Delete `data/optimization_checkpoint.json` and restart
- **Impact**: Lose cumulative optimization progress

### 5. Diagnostic Commands

```bash
# View logs (Windows)
type logs\lotto_app.log
findstr ERROR logs\lotto_app.log          # Filter errors only

# System health
python -c "from src.utils.system_health_checker import SystemHealthChecker; SystemHealthChecker().run_health_check()"

# Memory status
python -c "from src.utils.memory_monitor import MemoryMonitor; MemoryMonitor().log_memory()"

# Database status
python -c "from src.core.db_manager import DatabaseManager; db = DatabaseManager(); print(f'Total rounds: {len(db.get_all_winning_numbers())}')"

# Check optimization progress
python src/scripts/check_optimization_status.py

# Check auto-learning status
python src/scripts/check_auto_learning_status.py
```

### 6. File Encoding & Platform Issues

#### Windows Compatibility
- **Log viewing**: `type logs\lotto_app.log` (not `cat`)
- **Error filtering**: `findstr ERROR logs\lotto_app.log` (not `grep`)
- **Directory listing**: `dir /b` (not `ls`)
- **Reserved names**: Never create: CON, PRN, AUX, NUL, COM1-9, LPT1-9

#### Encoding Rules
- **Always use**: `encoding='utf-8'` for file operations
- **Korean text**: Required for proper 한글 handling
- **Testing**: Replace emoji (✅, ❌) with ASCII ([O], [X])

#### TensorFlow/Keras Console Output
- **Environment variables**: Set BEFORE imports (main.py:34-49)
  - `TF_ENABLE_ONEDNN_OPTS='0'`: Disable oneDNN logging
  - `TF_CPP_MIN_LOG_LEVEL='3'`: ERROR only
  - `ABSL_LOGGING_VERBOSITY='1'`: Suppress ABSL
- **Matplotlib backend**: 'Agg' (non-interactive)
- **Warning suppression**: All TF/Keras warnings filtered

### 7. Recovery Procedures

#### Full System Recovery
```bash
# 1. Clear all caches
python src/scripts/clear_model_cache.py
python src/scripts/auto_cache_cleaner.py --force

# 2. Release database locks
python src/scripts/kill_db_locks.py

# 3. Optimize databases
python src/scripts/optimize_databases.py

# 4. Verify data integrity
python -c "from src.core.db_manager import DatabaseManager; db = DatabaseManager(); with db: nums = db.get_numbers_with_bonus(); print(f'Verified {len(nums)} rounds with bonus')"

# 5. Restart main program
python main.py
```

#### Partial Recovery (Optimization Only)
```bash
# 1. Check current state
python src/scripts/check_optimization_status.py

# 2. If corrupted, reset
python src/scripts/check_optimization_status.py --reset

# 3. Restart optimization
python main.py  # Auto-optimization runs in background
```

### 8. Performance Optimization

#### Parallel Processing Tuning
- **Location**: `config.yaml`
- **Workers**: 12 (75% of 16 cores default)
- **Batch size**: 60K combinations
- **Memory per worker**: 250MB
- **Adjustment**: Based on system resources

#### Database Tuning
- **Connection pool**: 8 connections
- **Indexes**: 12 strategic indexes (automatic)
- **Query timeout**: 30 seconds
- **Optimization**: Run optimize_databases.py monthly

#### Cache Management
- **Model cache**: 7-day TTL, 1.7GB+ typical
- **Pattern cache**: LRU eviction
- **Cleanup threshold**: 80% memory usage
- **Manual cleanup**: auto_cache_cleaner.py --force

### 9. Key Files
- `src/utils/system_health_checker.py`: Health monitoring
- `src/utils/auto_repair_system.py`: Automatic repairs
- `src/utils/error_prevention_system.py`: Proactive error detection
- `src/utils/memory_monitor.py`: Memory tracking
- `src/scripts/auto_cache_cleaner.py`: Cache cleanup
- `src/scripts/clear_model_cache.py`: Model cache clearing
- `src/scripts/kill_db_locks.py`: Database lock release
- `src/scripts/optimize_databases.py`: Database optimization

### 10. Critical Rules
- CHECK logs first (type logs\lotto_app.log)
- USE context managers for database access
- MONITOR memory usage (>4GB warning)
- VERIFY data integrity after repairs
- CLEAR cache on AttributeError
- RELEASE locks before database operations
- OPTIMIZE databases monthly
- BACKUP before major changes

## When to Invoke This Skill

- System errors or unexpected behavior
- Performance degradation
- Memory or resource issues
- Database problems
- Cache corruption
- File encoding errors
- Platform compatibility issues
- General troubleshooting and diagnostics

## Example Diagnostic Flow

```
1. Check logs: type logs\lotto_app.log | findstr ERROR
2. Identify issue category:
   - ML errors → Clear cache
   - DB errors → Release locks
   - Memory errors → Run cache cleaner
   - Performance → Check config.yaml settings
3. Apply specific fix from Common Issues section
4. Verify resolution
5. Monitor for recurrence
```

## Performance Metrics
- Health check time: <5 seconds
- Cache cleanup: <30 seconds
- Database lock release: <3 seconds
- Full system recovery: <5 minutes
- Memory monitoring overhead: <1%
- Auto-repair success rate: >95%
