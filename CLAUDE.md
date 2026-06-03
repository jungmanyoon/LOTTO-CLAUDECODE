# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 Quick Start (TL;DR)
```bash
python main.py              # ONE full cycle then EXIT (~4min): data/filter/ML/backtest/predict + dashboard(5001)
python main.py --24h        # PERSISTENT service: stays resident (scheduled predictions + continuous optimization)
python -m pytest tests/     # Run all tests (70% coverage minimum)
python src/scripts/clear_model_cache.py  # Fix most cache/model errors
```

> NOTE (런타임 검증 2026-06-03): plain `python main.py`는 한 사이클을 수행한 뒤 **자체 종료**합니다(약 4분).
> 대시보드(5001)와 백그라운드 최적화는 **daemon 스레드**라 프로세스 종료와 함께 멈춥니다.
> "무한 상주(대시보드 상시 + 무한 백그라운드 최적화)"가 필요하면 **`--24h`** 플래그를 쓰세요.
> 아래 문서의 "무한 반복/상주" 표현은 `--24h` 상주 모드 기준입니다.

**Key Files**: `config.yaml` (workers/batch), `configs/adaptive_filter_config.yaml` (thresholds)
**Key APIs**: `db.get_numbers_with_bonus()` (NOT `get_all_rounds()`), `ThresholdManager.get_instance()`

---

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
- `RULES.md` - Language rules (Korean responses)
- `requirements.txt` - Dependencies
- `pytest.ini` - Test configuration
- `.gitignore` - Git configuration
- `.coverage` - Coverage report

### File Cleanup
```bash
# Clean up temporary files manually (delete any temp files in root)
del test_*.py check_*.py verify_*.py *_FIX.md *_SUMMARY.md *_REPORT.md
```

### Enforcement
- `.gitignore` automatically excludes temporary file patterns
- Any violation of these rules will be called out immediately
- Professional standards: Keep it clean, keep it organized

---

## ⚠️ CRITICAL DATA INTEGRITY RULES

**NEVER use demo, dummy, fake, or sample data in production code!**

### Data Rules (MANDATORY)
1. **NO DEMO MODE**: All features must work with real data only
2. **NO FALLBACK TO FAKE DATA**: If real data is unavailable, show error/warning - NEVER generate fake data
3. **NO DUMMY PREDICTIONS**: All predictions must be based on actual ML/AI models and real historical data
4. **FAIL FAST**: If data is missing or corrupted, fail explicitly rather than silently using fake data

### Code Examples (CRITICAL)
```python
# ❌ 절대 금지 - NEVER DO THIS:
price = 50000  # 테스트용 하드코딩
balance = 1000000  # 임의값
dummy_data = {"numbers": [1,2,3,4,5,6]}  # 예시 데이터
sample_predictions = generate_fake_numbers()  # 더미 생성

# ✅ 반드시 이렇게 - ALWAYS DO THIS:
price = config.get('lottery_price')  # config.yaml에서 로드
balance = api.get_account_balance()  # 실제 API에서 로드
data = db.get_numbers_with_bonus()  # 실제 DB에서 로드
predictions = ml_model.predict(real_data)  # 실제 모델로 예측
```

### Why This Matters
- This is a lottery prediction system where accuracy is critical
- Fake/demo data can lead to false confidence and wrong decisions
- Users must always know they're seeing real analysis, not fabricated results
- **더미데이터로 테스트 → 실거래 시 예상치 못한 오류 발생**

### Allowed Exceptions (ONLY)
- **Unit tests**: Mock data allowed ONLY in `tests/` directory
- **Development debugging**: Clearly marked and never committed
- **테스트 시에도 테스트넷의 실제 데이터 사용 권장**

### Violations to Fix
- `demo_mode` flags in dashboard → Remove, always use real data
- `_generate_demo_*` functions → Remove or convert to error handlers
- Fallback fake data generators → Replace with proper error messages
- Hardcoded values (price, balance, etc.) → Load from config.yaml or API

---

## ⚠️ LANGUAGE RULES (See RULES.md)

**모든 응답은 한국어로!** (All responses must be in Korean)

1. **Language**: Always respond in **Korean (한국어)**
2. **Code Comments**: 주석도 반드시 **한국어**로 작성할 것
3. **Technical Terms**: 기술적인 용어는 영어를 병기하되 (ex: 변수(Variable)), 설명은 쉽게 한국어로 풀어서 할 것

---

## 📋 WORK PROGRESS DISPLAY FORMAT (작업 진행 상황 표시)

**매 단계마다 작업 진행 시 서두에 다음 형식으로 표시할 것:**

```
┌─────────────────────────────────────┐
│ 📍 단계: [현재/전체]                 │
│ 🎭 페르소나: [적용 역할]             │
│ 🛠️ 스킬: [사용 스킬]                │
│ 🤖 에이전트: [메인/서브]             │
│ 🔌 MCP: [연동 서버]                 │
│ 📋 작업: [수행 내용]                │
└─────────────────────────────────────┘
```

### Field Descriptions
| 필드 | 설명 | 예시 |
|------|------|------|
| 📍 단계 | 전체 작업 중 현재 위치 | [1/5], [3/7] |
| 🎭 페르소나 | 활성화된 역할 | Architect, Frontend, Backend, Security, QA |
| 🛠️ 스킬 | 사용 중인 프로젝트 스킬 | lotto-filter-expert, lotto-ml-trainer |
| 🤖 에이전트 | 에이전트 유형 | 메인, 서브(탐색), 서브(분석) |
| 🔌 MCP | 연동된 MCP 서버 | Context7, Sequential, Magic, Playwright |
| 📋 작업 | 현재 수행 중인 작업 | 필터 최적화 분석, 코드 리뷰 |

### Usage Rules
1. **복잡한 작업** (3단계 이상)에서는 반드시 표시
2. **각 단계 시작 시** 서두에 표시
3. **페르소나/스킬 변경 시** 새로 표시
4. **없음**으로 표시할 경우: 해당 항목이 적용되지 않을 때

---

## 🛠️ PROJECT-SPECIFIC SKILLS

This project has 5 custom Claude Code skills in `.claude/skills/`:

### Available Skills (Invoke with Skill tool)

| Skill | Purpose | Use When |
|-------|---------|----------|
| `lotto-filter-expert` | 16-filter system, adaptive filtering, threshold optimization | Modifying filter system, adjusting thresholds, ML-filter integration |
| `lotto-ml-trainer` | ML model training, caching, ensemble prediction | Model retraining, cache issues, TensorFlow setup |
| `lotto-db-manager` | Database operations, schema, indexing, query optimization | DB schema changes, query performance, data integrity |
| `lotto-backtester` | Backtesting, performance validation, Optuna auto-optimization | Backtesting setup, performance analysis, threshold tuning |
| `lotto-troubleshooter` | Problem diagnosis, system health, auto-repair, memory management | System errors, performance issues, memory problems |

### Skill Auto-Activation
Claude Code automatically activates appropriate skills based on context:
- Filter-related questions → `lotto-filter-expert`
- ML/model issues → `lotto-ml-trainer`
- Database problems → `lotto-db-manager`
- Performance validation → `lotto-backtester`
- General troubleshooting → `lotto-troubleshooter`

---

## CORE STRATEGY PHILOSOPHY (CRITICAL - READ BEFORE CRITICIZING)

**이 섹션을 먼저 읽지 않으면 이 시스템을 잘못 이해하게 된다.**

### 핵심 전략: "절대/거의 나올 수 없는 조합 제거"

이 시스템은 "다음 당첨번호를 예측"하는 시스템이 **아니다**.
이 시스템의 핵심은 **"8.14M 조합 중 역사적으로 거의 나올 수 없는 조합을 제거하여, 같은 구매 예산으로 더 그럴듯한 조합만 커버"**하는 전략이다.

### 수학적 근거 (AI가 혼동하지 말 것)

```
[잘못된 이해] "로또는 독립시행이므로 과거 패턴은 의미 없다 → 시스템 무의미"
[올바른 이해] "로또는 독립시행이지만, 역사적으로 단 한 번도 안 나온 패턴의
              조합을 제거하면 같은 예산으로 더 나은 영역을 커버할 수 있다"
```

**비유:** 어차피 1~10 사이 숫자 2개를 맞춰야 한다. 예산이 부족해 5세트만 구매 가능.
- 전략 없음: 무작위 5세트 구매
- 필터 전략: "두 숫자가 모두 같은 경우(중복)"는 규칙상 불가 → 제거 후 5세트 구매
- 필터 전략 2: "역사적으로 100회 중 한 번도 안 나온 패턴(예: 둘 다 1)" → 제거 후 구매
- 결과: 같은 5세트이지만 "더 가능성 높은 영역"에 집중

### ML/AI 모델의 올바른 역할

| 역할 구분 | 맞는가 | 설명 |
|----------|--------|------|
| "다음 당첨번호를 맞춘다" | X (불가능) | 독립시행으로 예측 불가 |
| "풀 내 번호 다양성 가중치 조정" | O (타당) | Pool-Diversity 방식 |
| "통계적으로 극단적인 조합 제거" | O (타당) | 필터 시스템의 핵심 |
| "1214회 당첨번호 기반 패턴 통계" | O (타당) | 거의 안 나오는 패턴 식별 |

### AI에게 지시 (MANDATORY)

1. **필터 시스템 비판 시**: "로또는 독립시행이므로 의미 없다"는 비판 금지.
   올바른 비판 기준은 "이 필터가 실제 당첨번호를 제거하는가?" (통과율 95%+ 필수)

2. **ML 모델 비판 시**: "당첨번호 예측" 역할로 평가하지 말 것.
   올바른 평가 기준은 "풀 내 다양성 가중치로서 작동하는가?"

3. **성능 평가 시**: 무작위 대비 "당첨번호를 포함하는 조합의 선택 비율"이 핵심.
   avg_matches가 아닌 "실제 당첨번호가 필터 통과하는 비율"이 1차 지표.

4. **개선 제안 시**: 위 핵심 전략에 반하는 제안(예: "ML 제거", "필터 폐기") 금지.
   개선은 항상 "같은 예산으로 더 좁고 정확한 풀 형성"을 목표로 해야 한다.

5. **[사용자 최종 확정 결정 2026-05-31] "어차피 1/8,145,060" 논쟁 영구 금지 (ABSOLUTE)**:
   - 사용자는 **"역사적으로 출현율이 극히 낮은(거의 안 나온) 극단 패턴을 최대한 찾아 제거하고,
     남은 풀에서 예측한다"**는 전략을 명시적·최종적으로 채택했다. 이는 사용자의 설계 권한이자
     변경 불가한 확정 결정이다.
   - 사용자는 **"매 회차가 독립시행으로 1/8,145,060"임을 이미 충분히 알고 있다.** 그 사실 위에서
     "역사적 극단 배제" 전략을 의도적으로 선택한 것이다.
   - 따라서 AI는 **"어차피 1/8,145,060이라 필터링/풀 축소가 무의미하다", "당첨확률을 못 높인다",
     "기대값으로 상쇄된다"는 순수 확률론적 비판을 이 프로그램에 절대 적용하지 않으며,
     이 논쟁/강의를 다시 꺼내는 것을 영구 금지한다.** (위반 시 즉시 중단하고 사용자 방법 구현으로 복귀)
   - **AI의 역할**: 확률 강의가 아니라, 사용자 방법("역사상 출현율 낮은 극단 패턴을 최대한 많이
     찾아 제거 → 남은 풀에서 다양성 있게 예측")을 정확히 구현하는 것이다.
   - **[2026-05-31 사용자 추가 결정] 통과율 95% 제약을 목표에서 제거**: 통과율(당첨번호 보존율)을
     강제 목표/제약으로 두지 않는다. 사용자는 "통과율 95%를 지키느라 제거를 못 하는 것"을 명시적으로
     거부했다. **"출현율 낮은 패턴을 최대한 많이 제거"가 우선 목표**이며, 통과율은 강제 제약이 아니라
     "참고 정보 지표"로만 표시한다. 제거 강도(임계값)는 사용자가 조절하거나 최대 제거 방향으로 설정한다.

---

## Project Overview
Korean lottery (로또) prediction system using ML/AI to analyze historical patterns. Applies probability-based filtering to reduce 8.14M combinations to ~300K (with 1.0% threshold), improving coverage efficiency by excluding statistically rare patterns from 1214+ historical draws.

**Repository Path**: `D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\`

## Common Commands
```bash
# Main Program Execution (All-in-One)
python main.py                           # ⚡ Run EVERYTHING ONCE then EXIT (~4min, F5 in IDE)
                                         #    ✅ Data collection & auto-update on new rounds
                                         #    ✅ Pattern analysis & filter updates
                                         #    ✅ ML/AI predictions
                                         #    ✅ Dashboard (http://127.0.0.1:5001, daemon - 프로세스 종료 시 함께 종료)
                                         #    ✅ Background optimization (daemon, 사이클 동안만 - 무한 상주는 --24h)
                                         #    ✅ New round auto-detection
                                         #    [!] plain 모드는 1사이클 후 자체 종료. 상주는 아래 --24h.

# Persistent / Optional Flags (선택사항)
python main.py --24h                     # 상주 모드: 새 회차 감지 + 예약 예측 + 무한 백그라운드 최적화 (Ctrl+C로 종료)
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

> [중요/런타임 검증 2026-06-03] 아래 "무한 반복/상주" 동작은 **`--24h` 상주 모드** 기준이다.
> plain `python main.py`는 데이터수집->필터링->ML->백테스팅->최종예측 **1사이클을 수행한 뒤 종료**하며,
> 백그라운드 최적화/대시보드는 daemon 스레드라 그 사이클 동안에만 동작한다(plain 모드 실측 약 2분).
> 무한 상주 최적화 + 상시 대시보드 + 새 회차 자동 감지/예약 예측을 원하면 `python main.py --24h`로 실행한다.

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
  - **Fixed Study Name**: `lotto_threshold_optimization_cmaes` for continuous learning (CMA-ES sampler)
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
- **Filter activation** (filters 토글이 SSOT, 코드에 'critical 강제 등록' 로직 없음): `configs/adaptive_filter_config.yaml`의 `filters` 섹션에서 `enabled: true`인 필터만 등록됨(`filter_core.py`). **odd_even/max_gap은 의도적 비활성(false)** — odd_even(6홀/6짝 제외)은 실제 당첨번호 약 2.85%(35/1226회)를 제거하는 정기 출현 패턴이라 핵심전략("출현율 극히 낮은 극단만 제거")에 위배되어 끔. (max_gap=0.16%만 제거하는 진짜 극단이라 True 복원은 백테스트 후 별도 검토)
- **Relaxable filters** (ML bypass): average, prime_composite, fixed_step, multiple, ten_section, digit_sum, dispersion, last_digit, arithmetic_sequence, geometric_sequence, section
- **Adaptive system**: `AdaptiveProbabilityFilter` in `src/core/adaptive_probability_filter.py` updates criteria dynamically
- **Management layers**:
  - `FilterManager` (`src/core/filter_manager.py`): Parallel processing coordination
  - `IntegratedFilterManager` (`src/core/integrated_filter_manager.py`): Unified filter orchestration
  - `AdaptiveFilterOptimizer` (`src/optimization/adaptive_filter_optimizer.py`): Automatic criteria optimization

#### ML Models
- **LSTM**: Time-series on 15-round sequences (ML-003: 50→15, 과적합 방지·메모리 절감; 단일소스=`lstm_predictor.py` 기본값) (`src/ml/lstm_predictor.py`)
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

## Warning Signs & Quick Fixes

| Symptom | Cause | Quick Fix |
|---------|-------|-----------|
| Average matches >3 | Data contamination | Check for winning number leakage in test data |
| All ML models same prediction | Cache corruption | `python src/scripts/clear_model_cache.py` |
| Memory >4GB | Large batch/cache | Reduce batch_size in config.yaml or run `auto_cache_cleaner.py` |
| Filter inclusion <10% | Threshold too strict | Auto-optimizer will adjust, or lower `global_probability_threshold` |
| Execution >15 min | Parallelization issue | Check max_workers in config.yaml (default: 12) |
| Dashboard connection error | Flask not running | Restart main.py or run `enhanced_dashboard_v2.py` manually |
| Frequent rollbacks | Unstable optimization | Increase validation_rounds (default: 50) |
| Optuna timeout | Too many trials | Reduce n_trials in optimizer config |
| Memory alerts | Cache bloat | `python src/scripts/auto_cache_cleaner.py --force` |
| Checkpoint corruption | Interrupted save | Delete `data/optimization_checkpoint.json` |
| StandardScaler error | Model cache issue | `python src/scripts/clear_model_cache.py` |
| `get_all_rounds()` error | Wrong API | Use `get_all_winning_numbers()` instead |

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
- **Test Markers**:
  - `@pytest.mark.unit` - Unit tests
  - `@pytest.mark.integration` - Integration tests
  - `@pytest.mark.slow` - Long-running tests (skip with `-m "not slow"`)
  - `@pytest.mark.critical` - Critical path tests
- **Test Isolation**: Each test should be independent and not rely on execution order
- **Fixtures**: Use pytest fixtures in `tests/conftest.py` for shared test resources
- **Coverage**: Minimum 70% enforced by pytest.ini (`--cov-fail-under=70`), aim for >80% for new features

### Code Formatting
```bash
black src tests --line-length 120    # Format code
flake8 src tests --max-line-length=120  # Lint check
pylint src                           # Static analysis
```

## Important Configuration Files

### ⚠️ Configuration File Priority (CRITICAL)
```
필터 설정 우선순위:
1. configs/adaptive_filter_config.yaml → 실제 사용됨 (필터 기준값)
2. config.yaml                         → 시스템 설정만 사용 (필터 설정 무시!)

config.yaml의 filters 섹션은 무시됩니다!
필터 기준값 변경시 반드시 adaptive_filter_config.yaml 수정
```

- **`config.yaml`**: 시스템 설정 전용 (필터 기준값 설정 **무시됨**)
  - Controls: FilterManager workers (12), batch sizes (60K), memory allocation (250MB/worker)
  - ML settings: Monte Carlo simulations, backtesting workers, LSTM/ensemble parameters
  - Database: Connection pool size (16), batch memory limits
  - **NOTE**: `filters.criteria` 섹션은 무시됨! → `adaptive_filter_config.yaml` 사용
- **`configs/adaptive_filter_config.yaml`**: **필터 설정의 단일 소스 (Single Source of Truth)**
  - `dynamic_criteria`: 모든 필터 기준값 (sum_range, match, average 등)
  - `adaptive_options`: `global_probability_threshold`, `ml_relaxed_threshold`
  - Auto-learning: Optimization targets, adjustment intervals, safety mode
  - Backtesting targets: Min/max average matches, target inclusion rate
  - **이 파일만 수정하면 필터 설정이 적용됩니다**
- **`configs/backup/`**: 자동 생성된 백업 파일들 (800+ 파일, 삭제 가능)
- **`requirements.txt`**: Python dependencies (use exact versions for stability)
- **`logs/lotto_app.log`**: Main application log file (auto-rotates at 10MB)
- **`data/system_state.json`**: System state tracking (auto-generated)
- **`.github/workflows/tests.yml`**: CI/CD pipeline configuration

## Quick Reference: Critical Decisions

### When Modifying Filters
1. **Always test with backtesting**: Use `OptimizedBacktestingFramework` to validate changes
2. **Check ML integration**: Ensure relaxable filters include new filter types in `main.py:generate_final_predictions_enhanced()`
3. **Update config file**: `configs/adaptive_filter_config.yaml`만 수정 (config.yaml 필터 설정은 무시됨!)
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

### Singleton Patterns (Critical)
The codebase uses singletons for shared state. Always use `get_instance()`:
```python
# CORRECT - Use singleton instance
from src.core.threshold_manager import ThresholdManager
threshold_mgr = ThresholdManager.get_instance()

# CORRECT - DatabaseManager singleton
from src.core.db_manager import DatabaseManager
db = DatabaseManager()  # Returns singleton

# WRONG - Never create new instances
threshold_mgr = ThresholdManager()  # Creates duplicate state!
```
**Singletons**: ThresholdManager, DatabaseManager, PerformanceStatsManager, ImprovedAutoImprovementManager

### CI/CD Pipeline
- **GitHub Actions**: Automated testing on push/PR (`.github/workflows/tests.yml`)
- **Test Matrix**: Python 3.8, 3.9, 3.10, 3.11 on Windows
- **Test Markers**: `@pytest.mark.unit` and `@pytest.mark.integration` for test classification
- **Code Coverage**: Codecov integration with XML reports
- **Linting**: Black, Flake8, Pylint (max line length 120)
- **Note**: Tests run on Windows platform to match production environment