#!/usr/bin/env python3
"""
통합 최적화 데이터베이스 관리자 (Phase 2)
- 분산된 7개 저장소를 data/optimization.db 단일 파일로 통합
- continuous_improvement.db 데이터 흡수
- ThresholdOptimizer 사용자 정의 테이블 통합
- JSON 상태 파일들 마이그레이션 지원

설계 원칙:
- configs/adaptive_filter_config.yaml: 필터 설정 Single Source of Truth (유지)
- data/optimization.db: 최적화 결과/상태 Single Source of Truth (신규)
- data/threshold_optimization.db: Optuna 내부 storage (변경 없음 - 누적 학습 보존)
"""
import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# 통합 DB 경로 (모듈 레벨 상수)
OPTIMIZATION_DB_PATH = "data/optimization.db"

# 마이그레이션 대상 JSON 파일 목록
JSON_STATE_FILES = {
    'smart_learning_state': 'data/smart_learning_state.json',
    'smart_learning_config': 'data/smart_learning_config.json',
    'auto_improvement_state': 'data/auto_improvement_state.json',
    'improved_auto_improvement_state': 'data/improved_auto_improvement_state.json',
    'optimization_checkpoint': 'data/optimization_checkpoint.json',
}


class OptimizationDB:
    """통합 최적화 데이터베이스 관리자

    Phase 2: 분산된 저장소를 단일 SQLite DB로 통합
    - optimization_trials: Optuna 세션 요약
    - performance_history: 백테스팅 성능 이력
    - best_parameters: 최적 파라미터 이력
    - optimization_sessions: 최적화 세션 메타데이터
    - optimization_state: 시스템 상태 (key-value, JSON 파일 대체)
    """

    def __init__(self, db_path: str = OPTIMIZATION_DB_PATH):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        """DB 스키마 초기화 (없으면 생성, 있으면 유지)"""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            # WAL 모드 + 타임아웃 설정 (병렬 접근 안전)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")

            # Optuna 세션 요약 (기존 threshold_optimization.db.optimization_sessions 흡수)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT,
                    study_name TEXT,
                    n_trials INTEGER,
                    best_threshold REAL,
                    best_ml_bypass INTEGER,
                    best_ml_weight REAL,
                    best_score REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 성능 이력 (기존 continuous_improvement.db.performance_history 흡수)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_number INTEGER,
                    avg_matches REAL NOT NULL,
                    best_match INTEGER,
                    accuracy_3plus REAL,
                    ml_inclusion_rate REAL,
                    combination_count INTEGER,
                    threshold REAL NOT NULL,
                    ml_bypass_filters INTEGER,
                    ml_weight REAL,
                    is_baseline BOOLEAN DEFAULT 0,
                    is_best BOOLEAN DEFAULT 0,
                    improvement_from_baseline REAL,
                    session_id INTEGER,
                    filter_pass_rate REAL,
                    is_best_pass_rate BOOLEAN DEFAULT 0,
                    source TEXT DEFAULT 'unified_optimizer',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 최적 파라미터 이력 (기존 threshold_optimization.db.best_parameters 흡수)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS best_parameters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    threshold REAL,
                    ml_bypass INTEGER,
                    ml_weight REAL,
                    score REAL,
                    avg_matches REAL,
                    ml_inclusion_rate REAL,
                    validation_rounds INTEGER,
                    is_active BOOLEAN DEFAULT 0,
                    applied_at TEXT,
                    rollback_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 최적화 세션 (기존 continuous_improvement.db.optimization_sessions 흡수)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_number INTEGER,
                    session_type TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT,
                    tests_count INTEGER,
                    improvements_found INTEGER,
                    best_threshold REAL,
                    best_ml_bypass INTEGER,
                    best_ml_weight REAL,
                    best_performance REAL,
                    baseline_performance REAL,
                    improvement_rate REAL,
                    applied BOOLEAN,
                    rollback_reason TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 시스템 상태 key-value 저장소 (JSON 파일 5개 대체)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 인덱스 생성
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_perf_round "
                "ON performance_history(round_number)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_perf_created "
                "ON performance_history(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_perf_avg "
                "ON performance_history(avg_matches)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_date "
                "ON optimization_trials(session_date)"
            )

            # [optimization-1] 스키마 수렴 마이그레이션:
            # PerformanceTracker(continuous_improvement_engine)도 같은 data/optimization.db에
            # performance_history/optimization_sessions를 '다른 스키마'로 CREATE IF NOT EXISTS 한다.
            # 먼저 만든 쪽 스키마로 고정되므로, 누락될 수 있는 컬럼을 ALTER로 보강해
            # 양쪽 INSERT가 "no such column"으로 실패하지 않도록 한다(멱등).
            for _table, _ddl in [
                ('performance_history', 'filter_pass_rate REAL'),
                ('performance_history', 'is_best_pass_rate BOOLEAN DEFAULT 0'),
                ('performance_history', "source TEXT DEFAULT 'unified_optimizer'"),
                ('optimization_sessions', 'session_date TEXT'),
            ]:
                try:
                    conn.execute(f"ALTER TABLE {_table} ADD COLUMN {_ddl}")
                except sqlite3.OperationalError:
                    pass  # 이미 존재하는 컬럼은 무시

            conn.commit()

    # ─────────────────────────────────────────
    # 상태 저장소 (JSON 파일 대체)
    # ─────────────────────────────────────────

    def get_state(self, key: str, default: Any = None) -> Any:
        """상태 값 조회 (JSON 역직렬화)"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                row = conn.execute(
                    "SELECT value_json FROM optimization_state WHERE key = ?",
                    (key,)
                ).fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            self.logger.warning(f"[OptimizationDB] get_state({key}) 실패: {e}")
        return default

    def set_state(self, key: str, value: Any):
        """상태 값 저장 (JSON 직렬화)"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    "PRAGMA journal_mode=WAL"
                )
                conn.execute("""
                    INSERT OR REPLACE INTO optimization_state (key, value_json, updated_at)
                    VALUES (?, ?, datetime('now'))
                """, (key, json.dumps(value, ensure_ascii=False, default=str)))
                conn.commit()
        except Exception as e:
            self.logger.error(f"[OptimizationDB] set_state({key}) 실패: {e}")

    # ─────────────────────────────────────────
    # 성능 이력
    # ─────────────────────────────────────────

    def save_performance(self, metrics: Dict) -> int:
        """성능 결과 저장, rowid 반환"""
        # 0값 쓰레기 데이터 방어: avg_matches=0이면 저장 거부
        avg = metrics.get('avg_matches', 0)
        threshold = metrics.get('threshold', 0)
        if avg == 0 and threshold == 0:
            self.logger.warning(
                f"[OptimizationDB] save_performance 거부: avg_matches=0, threshold=0 "
                f"(source={metrics.get('source', 'unknown')}) - 쓰레기 데이터 차단"
            )
            return -1
        if avg == 0:
            self.logger.warning(
                f"[OptimizationDB] save_performance 거부: avg_matches=0 "
                f"(source={metrics.get('source', 'unknown')}) - 백테스팅 실패 데이터 차단"
            )
            return -1
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.execute("""
                    INSERT INTO performance_history
                    (round_number, avg_matches, best_match, accuracy_3plus,
                     ml_inclusion_rate, combination_count, threshold,
                     ml_bypass_filters, ml_weight, is_baseline, is_best,
                     improvement_from_baseline, session_id, filter_pass_rate,
                     is_best_pass_rate, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics.get('round_number'),
                    metrics.get('avg_matches', 0),
                    metrics.get('best_match'),
                    metrics.get('accuracy_3plus'),
                    metrics.get('ml_inclusion_rate'),
                    metrics.get('combination_count'),
                    metrics.get('threshold', 1.0),
                    metrics.get('ml_bypass_filters'),
                    metrics.get('ml_weight'),
                    int(metrics.get('is_baseline', False)),
                    int(metrics.get('is_best', False)),
                    metrics.get('improvement_from_baseline'),
                    metrics.get('session_id'),
                    metrics.get('filter_pass_rate'),
                    int(metrics.get('is_best_pass_rate', False)),
                    metrics.get('source', 'unified_optimizer'),
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"[OptimizationDB] save_performance 실패: {e}")
            return -1

    def get_best_performance(self) -> Optional[Dict]:
        """avg_matches 기준 최고 성능 조회"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT * FROM performance_history
                    WHERE avg_matches > 0
                    ORDER BY avg_matches DESC
                    LIMIT 1
                """).fetchone()
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"[OptimizationDB] get_best_performance 실패: {e}")
            return None

    def get_recent_performance(self, limit: int = 50) -> List[Dict]:
        """최근 성능 이력 조회"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM performance_history
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"[OptimizationDB] get_recent_performance 실패: {e}")
            return []

    # ─────────────────────────────────────────
    # Optuna 세션 요약
    # ─────────────────────────────────────────

    def save_trial_summary(self, session_data: Dict) -> int:
        """Optuna 세션 요약 저장"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.execute("""
                    INSERT INTO optimization_trials
                    (session_date, study_name, n_trials, best_threshold,
                     best_ml_bypass, best_ml_weight, best_score,
                     avg_matches, ml_inclusion_rate, combination_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_data.get('session_date', datetime.now().isoformat()),
                    session_data.get('study_name', ''),
                    session_data.get('n_trials', 0),
                    session_data.get('best_threshold'),
                    session_data.get('best_ml_bypass'),
                    session_data.get('best_ml_weight'),
                    session_data.get('best_score'),
                    session_data.get('avg_matches'),
                    session_data.get('ml_inclusion_rate'),
                    session_data.get('combination_count'),
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"[OptimizationDB] save_trial_summary 실패: {e}")
            return -1

    # ─────────────────────────────────────────
    # 최적화 세션
    # ─────────────────────────────────────────

    def start_session(self, round_number: int, session_type: str) -> int:
        """최적화 세션 시작, session_id 반환"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.execute("""
                    INSERT INTO optimization_sessions
                    (round_number, session_type, start_time, status)
                    VALUES (?, ?, datetime('now'), 'running')
                """, (round_number, session_type))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"[OptimizationDB] start_session 실패: {e}")
            return -1

    def complete_session(self, session_id: int, result: Dict):
        """최적화 세션 완료 기록"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("""
                    UPDATE optimization_sessions
                    SET end_time=datetime('now'), status=?,
                        tests_count=?, best_threshold=?, best_ml_bypass=?,
                        best_ml_weight=?, best_performance=?,
                        baseline_performance=?, improvement_rate=?,
                        applied=?, rollback_reason=?
                    WHERE id=?
                """, (
                    result.get('status', 'completed'),
                    result.get('tests_count', 0),
                    result.get('best_threshold'),
                    result.get('best_ml_bypass'),
                    result.get('best_ml_weight'),
                    result.get('best_performance'),
                    result.get('baseline_performance'),
                    result.get('improvement_rate'),
                    int(result.get('improvement_applied', False)),
                    result.get('rollback_reason'),
                    session_id,
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"[OptimizationDB] complete_session 실패: {e}")

    # ─────────────────────────────────────────
    # 마이그레이션
    # ─────────────────────────────────────────

    def migrate_from_json_files(self, json_files: Dict[str, str] = None):
        """기존 JSON 파일들을 optimization_state 테이블로 마이그레이션

        Args:
            json_files: {state_key: file_path} 딕셔너리
                        None이면 JSON_STATE_FILES 상수 사용
        """
        targets = json_files or JSON_STATE_FILES
        migrated = 0
        for state_key, file_path in targets.items():
            if os.path.exists(file_path):
                try:
                    # 이미 마이그레이션된 경우 스킵
                    existing = self.get_state(f'migrated_{state_key}')
                    if existing:
                        continue

                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.set_state(state_key, data)
                    self.set_state(f'migrated_{state_key}', datetime.now().isoformat())
                    self.logger.info(
                        f"[OptimizationDB] 마이그레이션 완료: {file_path} -> {state_key}"
                    )
                    migrated += 1
                except Exception as e:
                    self.logger.warning(
                        f"[OptimizationDB] 마이그레이션 실패: {file_path}: {e}"
                    )
        if migrated > 0:
            self.logger.info(f"[OptimizationDB] JSON 파일 {migrated}개 마이그레이션 완료")

    def migrate_from_continuous_improvement_db(
        self,
        source_db_path: str = "data/continuous_improvement.db"
    ):
        """continuous_improvement.db 데이터를 optimization.db로 마이그레이션

        이미 마이그레이션된 경우 스킵 (idempotent).
        """
        if not os.path.exists(source_db_path):
            self.logger.info(f"[OptimizationDB] {source_db_path} 없음, 스킵")
            return

        # 이미 마이그레이션 완료 확인
        if self.get_state('migrated_continuous_improvement_db'):
            self.logger.info("[OptimizationDB] continuous_improvement.db 이미 마이그레이션됨")
            return

        try:
            with sqlite3.connect(source_db_path, timeout=10) as src:
                src.row_factory = sqlite3.Row

                # performance_history 마이그레이션
                try:
                    rows = src.execute("SELECT * FROM performance_history").fetchall()
                    for row in rows:
                        data = dict(row)
                        data['source'] = 'continuous_improvement_db'
                        self.save_performance(data)
                    self.logger.info(
                        f"[OptimizationDB] performance_history {len(rows)}개 마이그레이션"
                    )
                except Exception as e:
                    self.logger.warning(f"[OptimizationDB] performance_history 마이그레이션 실패: {e}")

                # optimization_sessions 마이그레이션
                try:
                    rows = src.execute("SELECT * FROM optimization_sessions").fetchall()
                    with sqlite3.connect(self.db_path, timeout=30) as dst:
                        dst.execute("PRAGMA journal_mode=WAL")
                        for row in rows:
                            data = dict(row)
                            dst.execute("""
                                INSERT OR IGNORE INTO optimization_sessions
                                (round_number, session_type, start_time, end_time,
                                 status, tests_count, best_threshold, best_ml_bypass,
                                 best_ml_weight, best_performance, baseline_performance,
                                 improvement_rate, applied, rollback_reason, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                data.get('round_number'), data.get('session_type'),
                                data.get('start_time'), data.get('end_time'),
                                data.get('status'), data.get('tests_count'),
                                data.get('best_threshold'), data.get('best_ml_bypass'),
                                data.get('best_ml_weight'), data.get('best_performance'),
                                data.get('baseline_performance'), data.get('improvement_rate'),
                                data.get('applied'), data.get('rollback_reason'),
                                data.get('created_at'),
                            ))
                        dst.commit()
                    self.logger.info(
                        f"[OptimizationDB] optimization_sessions {len(rows)}개 마이그레이션"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"[OptimizationDB] optimization_sessions 마이그레이션 실패: {e}"
                    )

            # 마이그레이션 완료 기록
            self.set_state(
                'migrated_continuous_improvement_db',
                datetime.now().isoformat()
            )
            self.logger.info("[OptimizationDB] continuous_improvement.db 마이그레이션 완료")

        except Exception as e:
            self.logger.error(f"[OptimizationDB] continuous_improvement.db 마이그레이션 실패: {e}")

    def run_initial_migration(self):
        """최초 실행 시 기존 저장소에서 데이터 마이그레이션 (일회성)"""
        self.migrate_from_json_files()
        self.migrate_from_continuous_improvement_db()


# ─────────────────────────────────────────────────────────────────
# 싱글톤 팩토리
# ─────────────────────────────────────────────────────────────────
_optimization_db_instance: Optional[OptimizationDB] = None


def get_optimization_db(db_path: str = OPTIMIZATION_DB_PATH) -> OptimizationDB:
    """OptimizationDB 싱글톤 인스턴스 반환"""
    global _optimization_db_instance
    if _optimization_db_instance is None:
        _optimization_db_instance = OptimizationDB(db_path)
    return _optimization_db_instance
