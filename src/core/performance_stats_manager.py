"""
성능 통계 관리자
백테스팅 결과를 데이터베이스에 저장하고 조회하는 모듈
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import os

class PerformanceStatsManager:
    """백테스팅 성능 통계 관리"""
    
    def __init__(self, db_path: str = "data/performance_stats.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        
        # 데이터베이스 디렉토리 생성
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 테이블 생성
        self._create_tables()
    
    def _create_tables(self):
        """성능 통계 테이블 생성"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 백테스팅 세션 테이블 (임계값 추적 추가)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT NOT NULL,
                    total_rounds INTEGER NOT NULL,
                    test_start_round INTEGER,
                    test_end_round INTEGER,
                    session_config TEXT,
                    probability_threshold REAL DEFAULT 1.5,
                    ml_bypass_filters INTEGER DEFAULT 12,
                    ml_weight REAL DEFAULT 0.5,
                    combination_count INTEGER,
                    ml_inclusion_rate REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 기존 테이블에 누락된 컬럼 추가 (ALTER TABLE)
            self._migrate_backtest_sessions_table(cursor)
            
            # 모델별 성능 지표 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    model_name TEXT NOT NULL,
                    total_predictions INTEGER DEFAULT 0,
                    avg_matches REAL DEFAULT 0,
                    best_match INTEGER DEFAULT 0,
                    accuracy_3plus REAL DEFAULT 0,
                    contaminated_count INTEGER DEFAULT 0,
                    match_0 INTEGER DEFAULT 0,
                    match_1 INTEGER DEFAULT 0,
                    match_2 INTEGER DEFAULT 0,
                    match_3 INTEGER DEFAULT 0,
                    match_4 INTEGER DEFAULT 0,
                    match_5 INTEGER DEFAULT 0,
                    match_6 INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES backtest_sessions (id)
                )
            """)
            
            # 상세 예측 결과 테이블 (선택적)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prediction_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    round_num INTEGER,
                    model_name TEXT NOT NULL,
                    predicted_numbers TEXT,
                    actual_numbers TEXT,
                    match_count INTEGER,
                    is_contaminated BOOLEAN DEFAULT FALSE,
                    filter_passed BOOLEAN DEFAULT TRUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES backtest_sessions (id)
                )
            """)
            
            # 전체 통계 뷰 생성
            cursor.execute("""
                CREATE VIEW IF NOT EXISTS performance_summary AS
                SELECT
                    bs.session_date,
                    bs.total_rounds,
                    mp.model_name,
                    mp.total_predictions,
                    mp.avg_matches,
                    mp.best_match,
                    mp.accuracy_3plus,
                    mp.contaminated_count,
                    (mp.match_3 + mp.match_4 + mp.match_5 + mp.match_6) as successful_predictions,
                    mp.created_at
                FROM backtest_sessions bs
                JOIN model_performance mp ON bs.id = mp.session_id
                ORDER BY bs.created_at DESC, mp.model_name
            """)

            # 성능 최적화를 위한 인덱스 생성
            self._create_indexes(cursor)

            conn.commit()

    def _create_indexes(self, cursor):
        """성능 최적화를 위한 인덱스 생성"""
        try:
            # model_performance 테이블 인덱스
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_session
                ON model_performance(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_model
                ON model_performance(model_name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_created
                ON model_performance(created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_composite
                ON model_performance(session_id, model_name)
            """)

            # prediction_details 테이블 인덱스
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_details_session
                ON prediction_details(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_details_round
                ON prediction_details(round_num)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_details_model
                ON prediction_details(model_name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_details_created
                ON prediction_details(created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_details_composite
                ON prediction_details(session_id, round_num)
            """)

            # backtest_sessions 테이블 인덱스
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_sessions_created
                ON backtest_sessions(created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_sessions_threshold
                ON backtest_sessions(probability_threshold)
            """)

            self.logger.info("데이터베이스 인덱스 생성 완료")

        except Exception as e:
            self.logger.warning(f"인덱스 생성 중 오류 (무시 가능): {e}")

    def _migrate_backtest_sessions_table(self, cursor):
        """backtest_sessions 테이블 스키마 마이그레이션"""
        try:
            # 현재 테이블의 컬럼 정보 확인
            cursor.execute("PRAGMA table_info(backtest_sessions)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # 필요한 컬럼 목록
            required_columns = {
                'probability_threshold': 'REAL DEFAULT 1.0',
                'ml_bypass_filters': 'INTEGER DEFAULT 8',
                'ml_weight': 'REAL DEFAULT 0.4',
                'combination_count': 'INTEGER',
                'ml_inclusion_rate': 'REAL'
            }

            # 누락된 컬럼 추가
            for column_name, column_def in required_columns.items():
                if column_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE backtest_sessions ADD COLUMN {column_name} {column_def}")
                        self.logger.info(f"백테스팅 세션 테이블에 {column_name} 컬럼 추가 완료")
                    except sqlite3.OperationalError as e:
                        # 이미 존재하는 컬럼이면 무시
                        if "duplicate column name" not in str(e).lower():
                            self.logger.warning(f"컬럼 {column_name} 추가 실패: {e}")

        except Exception as e:
            self.logger.error(f"테이블 마이그레이션 중 오류: {e}")

    def save_backtest_results(self, backtest_results: Dict[str, Any]) -> int:
        """백테스팅 결과를 데이터베이스에 저장"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 백테스팅 세션 정보 저장
                session_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                performance_metrics = backtest_results.get('performance_metrics', {})
                total_rounds = performance_metrics.get('total_rounds', 0)
                
                # 테스트 범위 추출
                predictions = backtest_results.get('predictions', [])
                test_start_round = min([p.get('round', 0) for p in predictions]) if predictions else 0
                test_end_round = max([p.get('round', 0) for p in predictions]) if predictions else 0
                
                # 설정 정보 저장 (임계값 정보 포함)
                config_info = {
                    'filter_enabled': backtest_results.get('filter_enabled', True),
                    'model_types': list(performance_metrics.get('model_performance', {}).keys()),
                    'test_range': f"{test_start_round}-{test_end_round}"
                }

                # 임계값 관련 정보 추출
                threshold_info = backtest_results.get('threshold_info', {})
                probability_threshold = threshold_info.get('probability_threshold', 1.0)
                ml_bypass_filters = threshold_info.get('ml_bypass_filters', 8)
                ml_weight = threshold_info.get('ml_weight', 0.4)
                combination_count = threshold_info.get('combination_count', 0)
                ml_inclusion_rate = threshold_info.get('ml_inclusion_rate', 0.0)

                # 컬럼 존재 여부 확인 및 안전한 INSERT
                cursor.execute("PRAGMA table_info(backtest_sessions)")
                existing_columns = {row[1] for row in cursor.fetchall()}

                # 기본 컬럼들 (항상 존재해야 함)
                base_columns = ['session_date', 'total_rounds', 'test_start_round', 'test_end_round', 'session_config']
                base_values = [session_date, total_rounds, test_start_round, test_end_round,
                              json.dumps(config_info, ensure_ascii=False)]

                # 선택적 컬럼들 (존재할 경우에만 포함)
                optional_columns = {
                    'probability_threshold': probability_threshold,
                    'ml_bypass_filters': ml_bypass_filters,
                    'ml_weight': ml_weight,
                    'combination_count': combination_count,
                    'ml_inclusion_rate': ml_inclusion_rate
                }

                # 존재하는 컬럼만 포함하여 INSERT 문 생성
                insert_columns = base_columns[:]
                insert_values = base_values[:]

                for col_name, col_value in optional_columns.items():
                    if col_name in existing_columns:
                        insert_columns.append(col_name)
                        insert_values.append(col_value)

                # 동적 INSERT 문 실행
                columns_str = ', '.join(insert_columns)
                placeholders = ', '.join(['?'] * len(insert_values))

                cursor.execute(f"""
                    INSERT INTO backtest_sessions ({columns_str})
                    VALUES ({placeholders})
                """, insert_values)
                
                session_id = cursor.lastrowid
                
                # 모델별 성능 지표 저장
                model_performances = performance_metrics.get('model_performance', {})
                for model_name, model_metrics in model_performances.items():
                    match_counts = model_metrics.get('match_counts', {})
                    
                    cursor.execute("""
                        INSERT INTO model_performance 
                        (session_id, model_name, total_predictions, avg_matches, best_match, 
                         accuracy_3plus, contaminated_count, match_0, match_1, match_2, 
                         match_3, match_4, match_5, match_6)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        session_id, model_name,
                        model_metrics.get('total_predictions', 0),
                        round(model_metrics.get('avg_matches', 0), 3),
                        model_metrics.get('best_match', 0),
                        round(model_metrics.get('accuracy_3plus', 0), 2),
                        model_metrics.get('contaminated_count', 0),
                        match_counts.get(0, 0), match_counts.get(1, 0), match_counts.get(2, 0),
                        match_counts.get(3, 0), match_counts.get(4, 0), match_counts.get(5, 0),
                        match_counts.get(6, 0)
                    ))
                
                # 상세 예측 결과 저장 (선택적으로 최근 결과만)
                for pred_result in predictions[-50:]:  # 최근 50개만 저장
                    round_num = pred_result.get('round', 0)
                    actual_numbers = pred_result.get('winning_numbers', [])
                    
                    for model_name, matches_info in pred_result.get('matches', {}).items():
                        for match_info in matches_info[:5]:  # 모델당 최대 5개만 저장
                            cursor.execute("""
                                INSERT INTO prediction_details 
                                (session_id, round_num, model_name, predicted_numbers, 
                                 actual_numbers, match_count, is_contaminated, filter_passed)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                session_id, round_num, model_name,
                                json.dumps(match_info.get('predicted_numbers', [])),
                                json.dumps(actual_numbers),
                                match_info.get('match_count', 0),
                                match_info.get('contaminated', False),
                                match_info.get('filter_passed', True)
                            ))
                
                conn.commit()
                
                self.logger.info(f"백테스팅 결과 저장 완료 (세션 ID: {session_id})")
                return session_id
                
        except Exception as e:
            self.logger.error(f"백테스팅 결과 저장 실패: {e}")
            return -1
    
    def get_latest_performance(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 성능 통계 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM performance_summary 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    result = dict(zip(columns, row))
                    results.append(result)
                
                return results
                
        except Exception as e:
            self.logger.error(f"최근 성능 통계 조회 실패: {e}")
            return []
    
    def get_model_performance_summary(self) -> Dict[str, Any]:
        """모델별 성능 요약 통계"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 전체 통계
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT session_id) as total_sessions,
                        MAX(created_at) as last_updated
                    FROM model_performance
                """)
                overall_stats = dict(zip(['total_sessions', 'last_updated'], cursor.fetchone() or (0, None)))
                
                # 모델별 평균 성능
                cursor.execute("""
                    SELECT 
                        model_name,
                        COUNT(*) as session_count,
                        AVG(avg_matches) as avg_matches,
                        MAX(best_match) as best_match_ever,
                        AVG(accuracy_3plus) as avg_accuracy_3plus,
                        SUM(total_predictions) as total_predictions,
                        AVG(contaminated_count) as avg_contaminated
                    FROM model_performance 
                    GROUP BY model_name
                    ORDER BY avg_matches DESC
                """)
                
                columns = [desc[0] for desc in cursor.description]
                model_stats = []
                
                for row in cursor.fetchall():
                    stats = dict(zip(columns, row))
                    # 소수점 정리
                    for key in ['avg_matches', 'avg_accuracy_3plus', 'avg_contaminated']:
                        if stats[key] is not None:
                            stats[key] = round(stats[key], 3)
                    model_stats.append(stats)
                
                # 최근 세션별 성능 추이
                cursor.execute("""
                    SELECT 
                        bs.session_date,
                        bs.total_rounds,
                        AVG(mp.avg_matches) as session_avg_matches,
                        MAX(mp.best_match) as session_best_match
                    FROM backtest_sessions bs
                    JOIN model_performance mp ON bs.id = mp.session_id
                    GROUP BY bs.id, bs.session_date, bs.total_rounds
                    ORDER BY bs.created_at DESC
                    LIMIT 10
                """)
                
                columns = [desc[0] for desc in cursor.description]
                session_trends = []
                
                for row in cursor.fetchall():
                    trend = dict(zip(columns, row))
                    if trend['session_avg_matches'] is not None:
                        trend['session_avg_matches'] = round(trend['session_avg_matches'], 3)
                    session_trends.append(trend)
                
                return {
                    'overall': overall_stats,
                    'by_model': model_stats,
                    'recent_trends': session_trends
                }
                
        except Exception as e:
            self.logger.error(f"모델 성능 요약 통계 조회 실패: {e}")
            return {}
    
    def get_match_distribution_stats(self) -> Dict[str, Any]:
        """일치 개수별 분포 통계"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 전체 일치 분포
                cursor.execute("""
                    SELECT 
                        SUM(match_0) as match_0, SUM(match_1) as match_1, SUM(match_2) as match_2,
                        SUM(match_3) as match_3, SUM(match_4) as match_4, SUM(match_5) as match_5,
                        SUM(match_6) as match_6,
                        SUM(total_predictions) as total_predictions
                    FROM model_performance
                """)
                
                overall_dist = cursor.fetchone()
                total_predictions = overall_dist[7] if (overall_dist and overall_dist[7] is not None) else 0
                
                distribution = {}
                if total_predictions and total_predictions > 0:
                    for i in range(7):
                        count = overall_dist[i] if (overall_dist and overall_dist[i] is not None) else 0
                        distribution[f'match_{i}'] = {
                            'count': count,
                            'percentage': round((count / total_predictions) * 100, 2) if count and count > 0 else 0
                        }
                
                # 모델별 일치 분포
                cursor.execute("""
                    SELECT 
                        model_name,
                        match_0, match_1, match_2, match_3, match_4, match_5, match_6,
                        total_predictions
                    FROM model_performance
                    ORDER BY created_at DESC
                """)
                
                model_distributions = {}
                for row in cursor.fetchall():
                    model_name = row[0]
                    model_total = row[8]
                    
                    if model_total and model_total > 0:
                        model_dist = {}
                        for i in range(7):
                            count = row[i+1] if row[i+1] is not None else 0
                            model_dist[f'match_{i}'] = {
                                'count': count,
                                'percentage': round((count / model_total) * 100, 2) if count and count > 0 else 0
                            }
                        model_distributions[model_name] = model_dist
                
                return {
                    'overall_distribution': distribution,
                    'by_model': model_distributions,
                    'total_predictions': total_predictions
                }
                
        except Exception as e:
            self.logger.error(f"일치 분포 통계 조회 실패: {e}")
            return {}
    
    def cleanup_old_data(self, keep_days: int = 30):
        """오래된 데이터 정리"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 30일 이전 데이터 삭제
                cursor.execute("""
                    DELETE FROM prediction_details 
                    WHERE created_at < datetime('now', '-{} days')
                """.format(keep_days))
                
                deleted_details = cursor.rowcount
                
                # 상세 데이터가 없는 세션의 성능 데이터도 정리 (선택적)
                cursor.execute("""
                    DELETE FROM model_performance 
                    WHERE created_at < datetime('now', '-{} days')
                    AND session_id NOT IN (
                        SELECT DISTINCT session_id FROM prediction_details
                    )
                """.format(keep_days * 2))  # 성능 데이터는 더 오래 보관
                
                deleted_performance = cursor.rowcount
                
                # 관련 데이터가 없는 세션 삭제
                cursor.execute("""
                    DELETE FROM backtest_sessions 
                    WHERE id NOT IN (
                        SELECT DISTINCT session_id FROM model_performance
                    )
                """)
                
                deleted_sessions = cursor.rowcount
                
                conn.commit()
                
                self.logger.info(f"데이터 정리 완료: 세션 {deleted_sessions}개, 성능 {deleted_performance}개, 상세 {deleted_details}개 삭제")

        except Exception as e:
            self.logger.error(f"데이터 정리 실패: {e}")

    def get_threshold_performance_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """임계값별 성능 이력 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        bs.session_date,
                        bs.probability_threshold,
                        bs.ml_bypass_filters,
                        bs.ml_weight,
                        bs.combination_count,
                        bs.ml_inclusion_rate,
                        AVG(mp.avg_matches) as avg_matches,
                        MAX(mp.best_match) as best_match,
                        AVG(mp.accuracy_3plus) as accuracy_3plus,
                        COUNT(DISTINCT mp.model_name) as model_count
                    FROM backtest_sessions bs
                    LEFT JOIN model_performance mp ON bs.id = mp.session_id
                    GROUP BY bs.id
                    ORDER BY bs.created_at DESC
                    LIMIT ?
                """, (limit,))

                columns = [desc[0] for desc in cursor.description]
                results = []

                for row in cursor.fetchall():
                    result = dict(zip(columns, row))
                    # 반올림 처리
                    if result['avg_matches'] is not None:
                        result['avg_matches'] = round(result['avg_matches'], 3)
                    if result['accuracy_3plus'] is not None:
                        result['accuracy_3plus'] = round(result['accuracy_3plus'], 2)
                    if result['ml_inclusion_rate'] is not None:
                        result['ml_inclusion_rate'] = round(result['ml_inclusion_rate'], 4)
                    results.append(result)

                return results

        except Exception as e:
            self.logger.error(f"임계값 성능 이력 조회 실패: {e}")
            return []

    def get_optimal_threshold_stats(self) -> Dict[str, Any]:
        """최적 임계값 통계 분석"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 임계값별 평균 성능
                cursor.execute("""
                    SELECT
                        probability_threshold,
                        COUNT(*) as session_count,
                        AVG(CAST(
                            (SELECT AVG(avg_matches) FROM model_performance WHERE session_id = bs.id)
                            as REAL
                        )) as avg_performance,
                        AVG(ml_inclusion_rate) as avg_ml_inclusion,
                        AVG(combination_count) as avg_combinations
                    FROM backtest_sessions bs
                    WHERE probability_threshold IS NOT NULL
                    GROUP BY probability_threshold
                    ORDER BY avg_performance DESC
                """)

                threshold_stats = []
                columns = [desc[0] for desc in cursor.description]
                for row in cursor.fetchall():
                    stat = dict(zip(columns, row))
                    if stat['avg_performance'] is not None:
                        stat['avg_performance'] = round(stat['avg_performance'], 3)
                    if stat['avg_ml_inclusion'] is not None:
                        stat['avg_ml_inclusion'] = round(stat['avg_ml_inclusion'], 4)
                    threshold_stats.append(stat)

                # 최적 임계값 찾기 (평균 매칭 기준)
                cursor.execute("""
                    SELECT
                        bs.probability_threshold,
                        bs.ml_bypass_filters,
                        bs.ml_weight,
                        AVG(mp.avg_matches) as avg_matches,
                        bs.ml_inclusion_rate,
                        bs.combination_count
                    FROM backtest_sessions bs
                    LEFT JOIN model_performance mp ON bs.id = mp.session_id
                    WHERE bs.probability_threshold IS NOT NULL
                    GROUP BY bs.id
                    ORDER BY avg_matches DESC
                    LIMIT 1
                """)

                best_session = cursor.fetchone()
                best_threshold_info = None
                if best_session:
                    columns = ['probability_threshold', 'ml_bypass_filters', 'ml_weight',
                              'avg_matches', 'ml_inclusion_rate', 'combination_count']
                    best_threshold_info = dict(zip(columns, best_session))
                    if best_threshold_info['avg_matches'] is not None:
                        best_threshold_info['avg_matches'] = round(best_threshold_info['avg_matches'], 3)

                return {
                    'threshold_performance': threshold_stats,
                    'best_threshold': best_threshold_info,
                    'total_sessions_analyzed': len(threshold_stats)
                }

        except Exception as e:
            self.logger.error(f"최적 임계값 통계 분석 실패: {e}")
            return {}