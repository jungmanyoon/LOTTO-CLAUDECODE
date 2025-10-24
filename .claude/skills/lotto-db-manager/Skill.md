---
name: Lotto Database Manager
description: Expert in database operations, schema management, indexing, query optimization, and data integrity for lotto system databases
---

# Lotto Database Manager Skill

전문 분야: 데이터베이스 작업, 스키마 관리, 인덱싱, 쿼리 최적화, 데이터 무결성

## Core Responsibilities

### 1. Database Architecture
- **lotto_numbers.db**: Historical winning numbers (1186+ rounds) with bonus
  - Table: `winning_numbers` (round, n1-n6, bonus, draw_date)
- **combinations.db**: Pre-filtered combinations cache
- **filters/*.db**: 16 individual filter analysis results
- **predictions.db**: Saved predictions for tracking
- **performance_stats.db**: Backtest metrics (434MB, 4.7M rows)
  - 12 strategic indexes for 10,000x performance improvement
- **backtest_results.db**: Detailed backtesting history

### 2. DatabaseManager Methods
**Correct Usage**:
```python
from src.core.db_manager import DatabaseManager

db = DatabaseManager()
# Always use context manager
with db:
    # Get basic data
    numbers = db.get_all_winning_numbers()  # List[Tuple[round, numbers]]

    # Get with bonus (PREFERRED)
    numbers = db.get_numbers_with_bonus()  # List[Tuple[round, (n1-n6, bonus)]]

    # For backtesting
    past_numbers = db.get_winning_numbers_before(round_num)

    # Update from official site
    db.fetch_and_save_lotto_data()
```

**Common Mistakes**:
- ❌ `db.get_all_rounds()` - DOESN'T EXIST
- ❌ Not using context manager (`with db:`)
- ❌ Accessing database without proper cleanup

### 3. Database Indexing (FIXED 2025-10-15)
**Performance Improvement**: 10,000x faster queries (2-5s → <1ms)

**12 Strategic Indexes** (`src/core/performance_stats_manager.py:115-179`):
- `idx_session_id`: Fast session-based queries
- `idx_round_num`: Round number lookups
- `idx_created_at`: Time-based queries
- `idx_model_name`: Model-specific filtering
- `idx_session_round`: Composite for complex queries
- `idx_session_created`: Session timeline queries
- `idx_round_created`: Round history queries
- `idx_model_round`: Model performance by round
- Plus 4 additional composite indexes

**Automatic Creation**: `_create_indexes()` on initialization

### 4. Connection Management
- **Primary pool**: 8 connections (`config.yaml`)
- **Context manager pattern**: ALWAYS required
- **Specialized databases** (`src/core/specialized_databases.py`):
  - `PatternsDB`: Pattern analysis storage
  - `FilterDB`: Filter results caching
  - `PerformanceDB`: Performance metrics with indexes

### 5. Bonus Number Handling (FIXED 2025-09-12)
- **Bonus number**: 7th element in tuple from `get_numbers_with_bonus()`
- **Usage**: 2nd place (5 + bonus) prize calculation
- **Backtesting**: Includes bonus matching for accurate rank calculation
- **Collection**: `python src/scripts/complete_bonus_collection.py`

### 6. Database Migration & Optimization
**Optimization Tools**:
```bash
# Optimize and compact databases
python src/scripts/optimize_databases.py

# Manual update winning numbers
python src/scripts/manual_update_winning_numbers.py

# Release database locks
python src/scripts/kill_db_locks.py
```

**Migration System** (`src/utils/db_migrator.py`):
- Schema version tracking
- Automatic migration execution
- Rollback capability

### 7. Common Issues & Solutions

#### Database Locks
- **Symptom**: "Database is locked" errors
- **Fix**: `python src/scripts/kill_db_locks.py`
- **Prevention**: Always use context managers

#### Missing Bonus Numbers
- **Symptom**: Bonus numbers null or random
- **Fix**: `python src/scripts/complete_bonus_collection.py`
- **Verification**: Check `get_numbers_with_bonus()` results

#### Slow Queries (FIXED 2025-10-15)
- **Symptom**: DELETE/SELECT taking 2-5 seconds
- **Cause**: Missing indexes on 4.7M row table
- **Fix**: Automatic index creation on initialization
- **Verification**: Query execution time <1ms

#### JSON Parsing Errors (FIXED 2025-10-10)
- **Symptom**: "JSON 파싱 실패" from concurrent writes
- **Cause**: Multiple processes writing to same JSON file
- **Fix**: Migrated to SQLite with transaction management
- **Database**: `results/filter_validation_YYYYMM.db`

### 8. Data Integrity Rules
- **UTF-8 encoding**: Always use `encoding='utf-8'` for file operations
- **Context managers**: Required for all database access
- **Transaction safety**: SQLite ensures ACID compliance
- **Backup before optimization**: Automatic backup creation
- **Validation after migration**: Automatic schema verification

### 9. Key Files
- `src/core/db_manager.py`: Main database manager
- `src/core/specialized_databases.py`: PatternsDB, FilterDB, PerformanceDB
- `src/core/performance_stats_manager.py`: Performance database with indexes
- `src/utils/db_connection_manager.py`: Connection pool management
- `src/utils/db_migrator.py`: Schema migration system
- `src/scripts/optimize_databases.py`: Database optimization tool

### 10. Critical Rules
- ALWAYS use context managers (`with db:`)
- NEVER call `get_all_rounds()` (doesn't exist)
- PREFER `get_numbers_with_bonus()` over basic methods
- CHECK for database locks before long operations
- VERIFY bonus numbers after data updates
- MONITOR query performance (>1s is abnormal with indexes)
- ENSURE UTF-8 encoding for Korean text

## When to Invoke This Skill

- Database schema modifications
- Query optimization or performance issues
- Data integrity problems
- Migration or upgrade operations
- Bonus number handling
- Database locking or corruption
- Index management and optimization

## Example Commands

```python
# Correct database access pattern
from src.core.db_manager import DatabaseManager

db = DatabaseManager()
with db:
    # Get winning numbers with bonus
    numbers = db.get_numbers_with_bonus()
    for round_num, (n1, n2, n3, n4, n5, n6, bonus) in numbers:
        print(f"Round {round_num}: {n1}-{n2}-{n3}-{n4}-{n5}-{n6} + {bonus}")

    # Get numbers before specific round (for backtesting)
    past_numbers = db.get_winning_numbers_before(1100)
```

```bash
# Database maintenance
python src/scripts/optimize_databases.py           # Optimize all databases
python src/scripts/complete_bonus_collection.py    # Collect missing bonus numbers
python src/scripts/kill_db_locks.py               # Release locks if stuck
```

## Performance Metrics
- Query time with indexes: <1ms (10,000x improvement)
- Database size: ~500MB total across all databases
- Connection pool: 8 connections optimal
- Batch operations: 60K combinations per batch
- Optimization time: ~2-5 minutes for all databases
