#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터베이스 인덱스 최적화 스크립트
Step 2 (데이터 레이어 개선) 작업의 일환

주요 작업:
1. lotto_numbers.db의 round 컬럼에 인덱스 추가
2. predictions.db의 round, prediction_date 컬럼에 인덱스 추가
3. performance_stats.db의 주요 검색 컬럼에 인덱스 추가
4. 인덱스 생성 전후 쿼리 성능 비교

작성일: 2025-10-09
작성자: Claude (Backend Persona)
"""

import sqlite3
import os
import time
from typing import Dict, List, Tuple
from pathlib import Path

# 로거 설정
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseIndexOptimizer:
    """데이터베이스 인덱스 최적화 클래스"""

    def __init__(self, db_root: str = "data"):
        self.db_root = Path(db_root)
        self.results = {}

    def optimize_lotto_numbers_db(self) -> Dict:
        """lotto_numbers.db 최적화"""
        db_path = self.db_root / "lotto_numbers.db"

        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return {}

        logger.info(f"Optimizing {db_path}...")

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 기존 인덱스 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='lotto_numbers'
            """)
            existing_indexes = [row[0] for row in cursor.fetchall()]
            logger.info(f"Existing indexes: {existing_indexes}")

            # 쿼리 성능 측정 (인덱스 추가 전)
            before_time = self._measure_query_time(cursor, """
                SELECT * FROM lotto_numbers WHERE round = 1000
            """)

            # round 컬럼 인덱스 추가
            if 'idx_lotto_numbers_round' not in existing_indexes:
                logger.info("Creating index on round column...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_lotto_numbers_round
                    ON lotto_numbers(round)
                """)
                conn.commit()
                logger.info("✅ Index created: idx_lotto_numbers_round")
            else:
                logger.info("✅ Index already exists: idx_lotto_numbers_round")

            # draw_date 컬럼 인덱스 추가
            if 'idx_lotto_numbers_draw_date' not in existing_indexes:
                logger.info("Creating index on draw_date column...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_lotto_numbers_draw_date
                    ON lotto_numbers(draw_date)
                """)
                conn.commit()
                logger.info("✅ Index created: idx_lotto_numbers_draw_date")
            else:
                logger.info("✅ Index already exists: idx_lotto_numbers_draw_date")

            # 쿼리 성능 측정 (인덱스 추가 후)
            after_time = self._measure_query_time(cursor, """
                SELECT * FROM lotto_numbers WHERE round = 1000
            """)

            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0

            result = {
                'database': 'lotto_numbers.db',
                'before_ms': before_time * 1000,
                'after_ms': after_time * 1000,
                'improvement_percent': improvement
            }

            logger.info(f"Performance improvement: {improvement:.1f}%")
            return result

    def optimize_predictions_db(self) -> Dict:
        """predictions.db 최적화"""
        db_path = self.db_root / "predictions" / "predictions.db"

        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return {}

        logger.info(f"Optimizing {db_path}...")

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 기존 인덱스 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='predictions'
            """)
            existing_indexes = [row[0] for row in cursor.fetchall()]
            logger.info(f"Existing indexes: {existing_indexes}")

            # 쿼리 성능 측정 (인덱스 추가 전)
            before_time = self._measure_query_time(cursor, """
                SELECT * FROM predictions WHERE round = 1187 ORDER BY prediction_date DESC
            """)

            # round 컬럼 인덱스 추가
            if 'idx_predictions_round' not in existing_indexes:
                logger.info("Creating index on round column...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_predictions_round
                    ON predictions(round)
                """)
                conn.commit()
                logger.info("✅ Index created: idx_predictions_round")
            else:
                logger.info("✅ Index already exists: idx_predictions_round")

            # prediction_date 컬럼 인덱스는 prediction_tracker.py에서 생성함 (idx_predictions_date)
            # 중복 방지: 이미 idx_predictions_date가 존재하므로 여기서는 생성하지 않음
            if 'idx_predictions_date' in existing_indexes:
                logger.info("✅ Index already exists: idx_predictions_date (created by PredictionTracker)")
            else:
                logger.warning("⚠️ Expected index idx_predictions_date not found - should be created by PredictionTracker")

            # 복합 인덱스 추가 (round + prediction_date)
            if 'idx_predictions_round_date' not in existing_indexes:
                logger.info("Creating composite index on (round, prediction_date)...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_predictions_round_date
                    ON predictions(round, prediction_date DESC)
                """)
                conn.commit()
                logger.info("✅ Index created: idx_predictions_round_date")
            else:
                logger.info("✅ Index already exists: idx_predictions_round_date")

            # 쿼리 성능 측정 (인덱스 추가 후)
            after_time = self._measure_query_time(cursor, """
                SELECT * FROM predictions WHERE round = 1187 ORDER BY prediction_date DESC
            """)

            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0

            result = {
                'database': 'predictions.db',
                'before_ms': before_time * 1000,
                'after_ms': after_time * 1000,
                'improvement_percent': improvement
            }

            logger.info(f"Performance improvement: {improvement:.1f}%")
            return result

    def optimize_performance_stats_db(self) -> Dict:
        """performance_stats.db 최적화"""
        db_path = self.db_root / "performance_stats.db"

        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return {}

        logger.info(f"Optimizing {db_path}...")

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 기존 인덱스 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index'
            """)
            existing_indexes = [row[0] for row in cursor.fetchall()]
            logger.info(f"Existing indexes: {existing_indexes}")

            # backtest_sessions 테이블 인덱스 (실제 스키마에 맞게 수정)
            indexes_to_create = [
                ("idx_backtest_sessions_created", "backtest_sessions", "created_at"),
                ("idx_backtest_sessions_threshold", "backtest_sessions", "probability_threshold"),
                ("idx_backtest_sessions_test_range", "backtest_sessions", "test_start_round, test_end_round"),
            ]

            created_count = 0
            for idx_name, table_name, column_spec in indexes_to_create:
                if idx_name not in existing_indexes:
                    logger.info(f"Creating index: {idx_name}...")
                    try:
                        cursor.execute(f"""
                            CREATE INDEX IF NOT EXISTS {idx_name}
                            ON {table_name}({column_spec})
                        """)
                        conn.commit()

                        # Verify index was actually created
                        cursor.execute("""
                            SELECT name FROM sqlite_master
                            WHERE type='index' AND name=?
                        """, (idx_name,))
                        if cursor.fetchone():
                            logger.info(f"✅ Index created: {idx_name}")
                            created_count += 1
                        else:
                            logger.warning(f"⚠️ Index creation reported success but not found: {idx_name}")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"❌ Could not create index {idx_name}: {e}")
                else:
                    logger.info(f"✅ Index already exists: {idx_name}")

            result = {
                'database': 'performance_stats.db',
                'indexes_created': created_count,
                'total_indexes': len(existing_indexes) + created_count
            }

            return result

    def _measure_query_time(self, cursor, query: str, iterations: int = 5) -> float:
        """쿼리 실행 시간 측정 (평균값 반환)"""
        times = []
        for _ in range(iterations):
            start = time.time()
            cursor.execute(query)
            cursor.fetchall()  # 모든 결과 가져오기
            elapsed = time.time() - start
            times.append(elapsed)

        return sum(times) / len(times)

    def run_all_optimizations(self) -> Dict:
        """모든 데이터베이스 최적화 실행"""
        logger.info("=" * 60)
        logger.info("Starting database index optimization...")
        logger.info("=" * 60)

        results = {}

        # 1. lotto_numbers.db
        results['lotto_numbers'] = self.optimize_lotto_numbers_db()
        logger.info("")

        # 2. predictions.db
        results['predictions'] = self.optimize_predictions_db()
        logger.info("")

        # 3. performance_stats.db
        results['performance_stats'] = self.optimize_performance_stats_db()
        logger.info("")

        # 결과 요약
        logger.info("=" * 60)
        logger.info("Optimization Summary:")
        logger.info("=" * 60)

        for db_name, result in results.items():
            if result:
                logger.info(f"\n{db_name}:")
                for key, value in result.items():
                    logger.info(f"  {key}: {value}")

        logger.info("\n✅ All optimizations completed!")

        return results


def main():
    """메인 실행 함수"""
    optimizer = DatabaseIndexOptimizer()
    results = optimizer.run_all_optimizations()

    # 결과를 파일로 저장
    import json
    from datetime import datetime

    result_file = f"db_index_optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Results saved to: {result_file}")


if __name__ == "__main__":
    main()
