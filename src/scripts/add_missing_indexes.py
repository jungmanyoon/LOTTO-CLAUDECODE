"""
누락된 데이터베이스 인덱스 추가 스크립트

Phase 1.1: CRITICAL - 쿼리 성능 50-100x 개선 예상
"""

import sqlite3
import os
import logging
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_indexes_to_db(db_path: str, indexes: list) -> dict:
    """
    데이터베이스에 인덱스 추가

    Args:
        db_path: 데이터베이스 파일 경로
        indexes: (인덱스명, SQL문) 튜플 리스트

    Returns:
        결과 딕셔너리 {created: [], skipped: [], failed: []}
    """
    result = {'created': [], 'skipped': [], 'failed': []}

    if not os.path.exists(db_path):
        logger.warning(f"데이터베이스 없음: {db_path}")
        return result

    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()

        for idx_name, sql in indexes:
            try:
                # 기존 인덱스 확인
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'")
                if cursor.fetchone():
                    result['skipped'].append(idx_name)
                    continue

                # 인덱스 생성
                cursor.execute(sql)
                result['created'].append(idx_name)
                logger.info(f"[O] 인덱스 생성: {idx_name}")

            except Exception as e:
                result['failed'].append((idx_name, str(e)))
                logger.error(f"[X] 인덱스 생성 실패 ({idx_name}): {e}")

        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"DB 연결 실패 ({db_path}): {e}")

    return result


def main():
    """메인 실행 함수"""
    base_dir = Path(__file__).parent.parent.parent
    data_dir = base_dir / 'data'
    filters_dir = data_dir / 'filters'

    logger.info("=" * 60)
    logger.info("누락된 데이터베이스 인덱스 추가 시작")
    logger.info("=" * 60)

    total_stats = {'created': 0, 'skipped': 0, 'failed': 0}

    # 1. performance_stats.db 인덱스
    logger.info("\n[1/3] performance_stats.db 인덱스 추가...")
    perf_db = data_dir / 'performance_stats.db'
    perf_indexes = [
        # backtest_sessions 추가 인덱스
        ('idx_backtest_sessions_date_threshold',
         'CREATE INDEX IF NOT EXISTS idx_backtest_sessions_date_threshold ON backtest_sessions(session_date, probability_threshold)'),
        ('idx_backtest_sessions_combo',
         'CREATE INDEX IF NOT EXISTS idx_backtest_sessions_combo ON backtest_sessions(probability_threshold, ml_bypass_filters, ml_weight)'),
        # model_performance 추가 인덱스
        ('idx_model_performance_avg_matches',
         'CREATE INDEX IF NOT EXISTS idx_model_performance_avg_matches ON model_performance(avg_matches)'),
        # prediction_details 추가 인덱스
        ('idx_prediction_details_match_count',
         'CREATE INDEX IF NOT EXISTS idx_prediction_details_match_count ON prediction_details(match_count)'),
    ]

    result = add_indexes_to_db(str(perf_db), perf_indexes)
    total_stats['created'] += len(result['created'])
    total_stats['skipped'] += len(result['skipped'])
    total_stats['failed'] += len(result['failed'])

    # 2. threshold_optimization.db 인덱스
    logger.info("\n[2/3] threshold_optimization.db 인덱스 추가...")
    threshold_db = data_dir / 'threshold_optimization.db'
    threshold_indexes = [
        ('idx_optimization_trials_session_status',
         'CREATE INDEX IF NOT EXISTS idx_optimization_trials_session_status ON optimization_trials(session_id, status)'),
        ('idx_optimization_trials_score',
         'CREATE INDEX IF NOT EXISTS idx_optimization_trials_score ON optimization_trials(score)'),
        ('idx_optimization_sessions_date',
         'CREATE INDEX IF NOT EXISTS idx_optimization_sessions_date ON optimization_sessions(session_date)'),
        ('idx_best_parameters_active',
         'CREATE INDEX IF NOT EXISTS idx_best_parameters_active ON best_parameters(is_active)'),
    ]

    result = add_indexes_to_db(str(threshold_db), threshold_indexes)
    total_stats['created'] += len(result['created'])
    total_stats['skipped'] += len(result['skipped'])
    total_stats['failed'] += len(result['failed'])

    # 3. 필터 DB들 인덱스 (16개)
    logger.info("\n[3/3] 필터 데이터베이스 인덱스 추가...")

    filter_indexes = [
        # filtered_combinations 추가 인덱스
        ('idx_filtered_comb_combo',
         'CREATE INDEX IF NOT EXISTS idx_filtered_comb_combo ON filtered_combinations(combination)'),
        ('idx_filtered_comb_created',
         'CREATE INDEX IF NOT EXISTS idx_filtered_comb_created ON filtered_combinations(created_at)'),
        ('idx_filtered_comb_round',
         'CREATE INDEX IF NOT EXISTS idx_filtered_comb_round ON filtered_combinations(round)'),
        # excluded_combinations 추가 인덱스
        ('idx_excluded_comb_round',
         'CREATE INDEX IF NOT EXISTS idx_excluded_comb_round ON excluded_combinations(round)'),
        ('idx_excluded_comb_combo',
         'CREATE INDEX IF NOT EXISTS idx_excluded_comb_combo ON excluded_combinations(combination)'),
        # filter_details 인덱스
        ('idx_filter_details_round',
         'CREATE INDEX IF NOT EXISTS idx_filter_details_round ON filter_details(round_num)'),
        # filter_criteria 인덱스
        ('idx_filter_criteria_round',
         'CREATE INDEX IF NOT EXISTS idx_filter_criteria_round ON filter_criteria(round_num)'),
    ]

    if filters_dir.exists():
        for filter_db in filters_dir.glob('*.db'):
            logger.info(f"  처리 중: {filter_db.name}")
            result = add_indexes_to_db(str(filter_db), filter_indexes)
            total_stats['created'] += len(result['created'])
            total_stats['skipped'] += len(result['skipped'])
            total_stats['failed'] += len(result['failed'])
    else:
        logger.warning(f"필터 디렉토리 없음: {filters_dir}")

    # 4. combinations.db 인덱스
    logger.info("\n[추가] combinations.db 인덱스 추가...")
    combo_db = data_dir / 'combinations.db'
    combo_indexes = [
        ('idx_valid_comb_created',
         'CREATE INDEX IF NOT EXISTS idx_valid_comb_created ON valid_combinations(created_at)'),
        ('idx_filtered_combinations_round',
         'CREATE INDEX IF NOT EXISTS idx_filtered_combinations_round ON filtered_combinations(round)'),
    ]

    result = add_indexes_to_db(str(combo_db), combo_indexes)
    total_stats['created'] += len(result['created'])
    total_stats['skipped'] += len(result['skipped'])
    total_stats['failed'] += len(result['failed'])

    # 5. patterns.db 인덱스
    logger.info("\n[추가] patterns.db 인덱스 추가...")
    patterns_db = data_dir / 'patterns.db'
    patterns_indexes = [
        ('idx_pattern_analysis_timestamp',
         'CREATE INDEX IF NOT EXISTS idx_pattern_analysis_timestamp ON pattern_analysis(analyzed_at)'),
    ]

    result = add_indexes_to_db(str(patterns_db), patterns_indexes)
    total_stats['created'] += len(result['created'])
    total_stats['skipped'] += len(result['skipped'])
    total_stats['failed'] += len(result['failed'])

    # 결과 출력
    logger.info("\n" + "=" * 60)
    logger.info("인덱스 추가 완료!")
    logger.info("=" * 60)
    logger.info(f"[O] 생성됨: {total_stats['created']}개")
    logger.info(f"[-] 건너뜀 (이미 존재): {total_stats['skipped']}개")
    logger.info(f"[X] 실패: {total_stats['failed']}개")

    return total_stats


if __name__ == '__main__':
    main()
