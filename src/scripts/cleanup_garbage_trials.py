"""
오염된 Optuna trial 및 DB 레코드 정리 스크립트

문제: 프로그램 종료 시 백그라운드 Optuna 최적화 스레드가 즉시 중단되지 않아
avg_matches=0, score<0.3인 쓰레기 trial이 대량 저장됨

정리 대상:
1. Optuna study (threshold_optimization.db): score < 0.3인 trial -> PRUNED 상태로 변경
2. continuous_improvement.db: avg_matches=0 또는 threshold=0 레코드 삭제
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def cleanup_optuna_study(db_path: str = "data/threshold_optimization.db", score_threshold: float = 0.3, dry_run: bool = True):
    """Optuna study에서 score < threshold인 trial을 PRUNED 상태로 변경

    Args:
        db_path: Optuna DB 경로
        score_threshold: 이 값 미만의 score를 가진 trial을 정리
        dry_run: True면 실제 변경 없이 확인만
    """
    if not os.path.exists(db_path):
        logger.warning(f"DB 파일 없음: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 현황 조회
        cursor.execute("SELECT COUNT(*) FROM trial_values WHERE value < ?", (score_threshold,))
        garbage_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM trial_values")
        total_count = cursor.fetchone()[0]

        pct = (garbage_count / total_count * 100) if total_count > 0 else 0.0
        logger.info(f"[Optuna] score < {score_threshold} trial: {garbage_count}/{total_count}개 ({pct:.1f}%)")

        if garbage_count == 0:
            logger.info("[Optuna] 정리할 데이터 없음")
            return

        if dry_run:
            logger.info(f"[Optuna] DRY RUN: {garbage_count}개 trial을 PRUNED로 변경 예정")
            # 상위 10개 샘플 출력
            cursor.execute("""
                SELECT tv.trial_id, tv.value, t.state
                FROM trial_values tv
                JOIN trials t ON tv.trial_id = t.trial_id
                WHERE tv.value < ?
                ORDER BY tv.value ASC
                LIMIT 10
            """, (score_threshold,))
            for row in cursor.fetchall():
                logger.info(f"  trial_id={row[0]}, score={row[1]:.4f}, state={row[2]}")
            return

        # PRUNED 상태 = 'PRUNED' (Optuna TrialState)
        # Optuna에서 state 값: COMPLETE=1, PRUNED=2, FAIL=3, WAITING=4
        # trial_values에서 score < threshold인 trial의 state를 PRUNED(2)로 변경
        cursor.execute("""
            UPDATE trials SET state = 'PRUNED'
            WHERE trial_id IN (
                SELECT trial_id FROM trial_values WHERE value < ?
            ) AND state = 'COMPLETE'
        """, (score_threshold,))
        updated = cursor.rowcount

        conn.commit()
        logger.info(f"[Optuna] {updated}개 trial을 PRUNED 상태로 변경 완료")

    except Exception as e:
        logger.error(f"[Optuna] 정리 실패: {e}")
        conn.rollback()
    finally:
        conn.close()


def cleanup_continuous_improvement(db_path: str = "data/optimization.db", dry_run: bool = True):
    """optimization.db (구: continuous_improvement.db)에서 비정상 레코드 삭제

    [N-W20] 수정: data/continuous_improvement.db → data/optimization.db
    (Phase 2 리팩토링에서 continuous_improvement.db가 optimization.db로 통합됨)

    Args:
        db_path: DB 경로 (기본값: data/optimization.db)
        dry_run: True면 실제 변경 없이 확인만
    """
    if not os.path.exists(db_path):
        logger.warning(f"DB 파일 없음: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM performance_history WHERE avg_matches = 0 OR threshold = 0")
        abnormal_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM performance_history")
        total_count = cursor.fetchone()[0]

        logger.info(f"[CI] 비정상 레코드 (avg_matches=0 OR threshold=0): {abnormal_count}/{total_count}개")

        if abnormal_count == 0:
            logger.info("[CI] 정리할 데이터 없음")
            return

        if dry_run:
            logger.info(f"[CI] DRY RUN: {abnormal_count}개 레코드 삭제 예정")
            cursor.execute("""
                SELECT id, avg_matches, threshold, filter_pass_rate, created_at
                FROM performance_history
                WHERE avg_matches = 0 OR threshold = 0
                LIMIT 10
            """)
            for row in cursor.fetchall():
                logger.info(f"  id={row[0]}, avg_matches={row[1]}, threshold={row[2]}, filter_pass_rate={row[3]}, created={row[4]}")
            return

        cursor.execute("DELETE FROM performance_history WHERE avg_matches = 0 OR threshold = 0")
        deleted = cursor.rowcount
        conn.commit()
        logger.info(f"[CI] {deleted}개 비정상 레코드 삭제 완료")

    except Exception as e:
        logger.error(f"[CI] 정리 실패: {e}")
        conn.rollback()
    finally:
        conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="오염된 Optuna trial 및 DB 레코드 정리")
    parser.add_argument("--execute", action="store_true", help="실제 정리 실행 (기본: dry-run)")
    parser.add_argument("--score-threshold", type=float, default=0.3, help="이 점수 미만 trial 정리 (기본: 0.3)")
    args = parser.parse_args()

    dry_run = not args.execute
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN 모드 - 실제 변경 없이 확인만 합니다")
        logger.info("실제 실행: python src/scripts/cleanup_garbage_trials.py --execute")
        logger.info("=" * 60)

    cleanup_optuna_study(score_threshold=args.score_threshold, dry_run=dry_run)
    print()
    cleanup_continuous_improvement(dry_run=dry_run)

    if dry_run:
        print()
        logger.info("=" * 60)
        logger.info("위 데이터를 실제로 정리하려면 --execute 옵션을 추가하세요")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
