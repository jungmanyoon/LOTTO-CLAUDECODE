"""
잘못된 예측 데이터 정리 스크립트
- 비정상적인 회차 번호를 가진 예측 삭제
- 데이터베이스 무결성 검증
"""
import sqlite3
import logging
from pathlib import Path
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager

def clean_invalid_predictions():
    """잘못된 예측 데이터 정리"""
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # DatabaseManager로 현재 회차 확인
        db_manager = DatabaseManager()
        current_round = db_manager.get_last_round()
        max_valid_round = current_round + 10  # 최대 10회차 미래까지만 허용
        
        logging.info(f"현재 회차: {current_round}")
        logging.info(f"유효한 최대 회차: {max_valid_round}")
        
        # predictions.db 경로
        predictions_db = Path("data/predictions/predictions.db")
        
        if not predictions_db.exists():
            logging.warning("predictions.db 파일이 없습니다.")
            return
        
        # 데이터베이스 연결
        conn = sqlite3.connect(predictions_db)
        cursor = conn.cursor()
        
        # 비정상적인 회차 조회
        cursor.execute("""
            SELECT DISTINCT round 
            FROM predictions 
            WHERE round < 1 OR round > ?
            ORDER BY round
        """, (max_valid_round,))
        
        invalid_rounds = cursor.fetchall()
        
        if invalid_rounds:
            logging.info(f"비정상적인 회차 발견: {[r[0] for r in invalid_rounds]}")
            
            # 각 비정상 회차에 대해 정리
            for (round_num,) in invalid_rounds:
                # 해당 회차의 예측 개수 확인
                cursor.execute("""
                    SELECT COUNT(*) FROM predictions WHERE round = ?
                """, (round_num,))
                count = cursor.fetchone()[0]
                
                logging.info(f"  - {round_num}회차: {count}개 예측")
                
                # 삭제
                cursor.execute("""
                    DELETE FROM predictions WHERE round = ?
                """, (round_num,))
                
                # weekly_performance에서도 삭제
                cursor.execute("""
                    DELETE FROM weekly_performance WHERE round = ?
                """, (round_num,))
                
                logging.info(f"  - {round_num}회차 데이터 삭제 완료")
        else:
            logging.info("비정상적인 회차 데이터가 없습니다.")
        
        # 중복된 예측 확인 및 제거
        cursor.execute("""
            SELECT round, set_number, COUNT(*) as cnt
            FROM predictions
            GROUP BY round, set_number
            HAVING cnt > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            logging.info(f"\n중복된 예측 발견: {len(duplicates)}건")
            for round_num, set_num, cnt in duplicates:
                logging.info(f"  - {round_num}회차 세트{set_num}: {cnt}개")
                
                # 가장 최근 것만 남기고 삭제
                cursor.execute("""
                    DELETE FROM predictions 
                    WHERE round = ? AND set_number = ?
                    AND id NOT IN (
                        SELECT MAX(id) 
                        FROM predictions 
                        WHERE round = ? AND set_number = ?
                    )
                """, (round_num, set_num, round_num, set_num))
        else:
            logging.info("\n중복된 예측이 없습니다.")
        
        # 데이터 무결성 검증
        cursor.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE numbers IS NULL OR numbers = ''
        """)
        empty_predictions = cursor.fetchone()[0]
        
        if empty_predictions > 0:
            logging.warning(f"\n빈 예측 발견: {empty_predictions}개")
            cursor.execute("""
                DELETE FROM predictions
                WHERE numbers IS NULL OR numbers = ''
            """)
            logging.info("빈 예측 삭제 완료")
        
        # 변경사항 커밋
        conn.commit()
        
        # 최종 통계
        cursor.execute("SELECT COUNT(DISTINCT round) FROM predictions")
        total_rounds = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM predictions")
        total_predictions = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(round), MAX(round) FROM predictions")
        min_round, max_round = cursor.fetchone()
        
        logging.info("\n" + "="*50)
        logging.info("정리 완료 - 최종 통계:")
        logging.info(f"  - 총 회차 수: {total_rounds}")
        logging.info(f"  - 총 예측 수: {total_predictions}")
        logging.info(f"  - 회차 범위: {min_round} ~ {max_round}")
        logging.info("="*50)
        
        conn.close()
        
    except Exception as e:
        logging.error(f"정리 중 오류 발생: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    return True

if __name__ == "__main__":
    clean_invalid_predictions()