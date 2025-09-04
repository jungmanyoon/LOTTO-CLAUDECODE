#!/usr/bin/env python3
"""
조합 데이터베이스 문제 해결 스크립트
- storage_mode 확인 및 설정
- 기본 조합 생성 확인
- 필요시 재생성
"""
import logging
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.db_manager import DatabaseManager
from src.core.combination_manager import CombinationManager
from src.utils.constants import LottoConstants
from src.logger import setup_logging

def check_db_meta_table(db_manager):
    """db_meta 테이블 확인 및 생성"""
    try:
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            
            # db_meta 테이블 존재 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_meta'")
            if not cursor.fetchone():
                logging.info("db_meta 테이블이 없습니다. 생성합니다...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS db_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                logging.info("db_meta 테이블 생성 완료")
                return False
            return True
    except Exception as e:
        logging.error(f"db_meta 테이블 확인 중 오류: {str(e)}")
        return False

def check_storage_mode(db_manager):
    """storage_mode 확인 및 설정"""
    try:
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            
            # storage_mode 확인
            cursor.execute("SELECT value FROM db_meta WHERE key='storage_mode'")
            result = cursor.fetchone()
            
            if not result:
                logging.info("storage_mode가 설정되어 있지 않습니다. 'legacy'로 설정합니다...")
                cursor.execute('''
                    INSERT INTO db_meta (key, value) VALUES ('storage_mode', 'legacy')
                ''')
                conn.commit()
                return 'legacy'
            
            mode = result[0]
            logging.info(f"현재 storage_mode: {mode}")
            return mode
    except Exception as e:
        logging.error(f"storage_mode 확인 중 오류: {str(e)}")
        return 'legacy'

def check_combinations_count(db_manager):
    """조합 개수 확인"""
    try:
        # 각 테이블의 개수 확인
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            
            # base_combinations 개수
            cursor.execute("SELECT COUNT(*) FROM base_combinations")
            legacy_count = cursor.fetchone()[0]
            
            # base_combinations_optimized 개수
            cursor.execute("SELECT COUNT(*) FROM base_combinations_optimized")
            optimized_count = cursor.fetchone()[0]
            
            logging.info(f"base_combinations (legacy) 개수: {legacy_count:,}")
            logging.info(f"base_combinations_optimized 개수: {optimized_count:,}")
            
            # 예상 개수와 비교
            expected_count = 8145060  # 45C6
            
            if legacy_count == expected_count:
                logging.info("✅ Legacy 테이블에 모든 조합이 있습니다.")
                return 'legacy', True
            elif optimized_count == expected_count:
                logging.info("✅ Optimized 테이블에 모든 조합이 있습니다.")
                return 'optimized', True
            else:
                logging.warning(f"⚠️ 예상 조합 수({expected_count:,})와 불일치합니다.")
                return None, False
                
    except Exception as e:
        logging.error(f"조합 개수 확인 중 오류: {str(e)}")
        return None, False

def fix_storage_mode_mismatch(db_manager, actual_mode):
    """storage_mode 불일치 수정"""
    try:
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            
            logging.info(f"storage_mode를 '{actual_mode}'로 업데이트합니다...")
            cursor.execute('''
                UPDATE db_meta SET value = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE key = 'storage_mode'
            ''', (actual_mode,))
            conn.commit()
            
            logging.info("✅ storage_mode 업데이트 완료")
            return True
    except Exception as e:
        logging.error(f"storage_mode 업데이트 중 오류: {str(e)}")
        return False

def regenerate_combinations(db_manager):
    """조합 재생성"""
    try:
        logging.info("\n" + "="*60)
        logging.info("조합 재생성을 시작합니다...")
        logging.info("="*60)
        
        # 기존 데이터 삭제
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM base_combinations")
            cursor.execute("DELETE FROM base_combinations_optimized")
            conn.commit()
            logging.info("기존 조합 데이터 삭제 완료")
        
        # 조합 생성
        combination_manager = CombinationManager(db_manager)
        success = combination_manager.generate_base_combinations()
        
        if success:
            logging.info("✅ 조합 재생성 완료!")
            
            # 생성된 조합 개수 확인
            actual_mode, has_all = check_combinations_count(db_manager)
            if has_all:
                # storage_mode 업데이트
                fix_storage_mode_mismatch(db_manager, actual_mode)
        else:
            logging.error("❌ 조합 재생성 실패!")
            
        return success
        
    except Exception as e:
        logging.error(f"조합 재생성 중 오류: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    setup_logging()
    
    logging.info("\n" + "="*60)
    logging.info("조합 데이터베이스 진단 및 복구 시작")
    logging.info("="*60)
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 1. db_meta 테이블 확인
        logging.info("\n[단계 1] db_meta 테이블 확인")
        has_meta = check_db_meta_table(db_manager)
        
        # 2. storage_mode 확인
        logging.info("\n[단계 2] storage_mode 확인")
        current_mode = check_storage_mode(db_manager)
        
        # 3. 조합 개수 확인
        logging.info("\n[단계 3] 조합 개수 확인")
        actual_mode, has_all_combinations = check_combinations_count(db_manager)
        
        # 4. 문제 해결
        if not has_all_combinations:
            logging.warning("\n⚠️ 조합이 부족합니다. 재생성이 필요합니다.")
            
            response = input("\n조합을 재생성하시겠습니까? (y/n): ")
            if response.lower() == 'y':
                success = regenerate_combinations(db_manager)
                if not success:
                    logging.error("조합 재생성에 실패했습니다.")
                    return False
            else:
                logging.info("조합 재생성을 건너뜁니다.")
                return False
                
        elif actual_mode and actual_mode != current_mode:
            logging.warning(f"\n⚠️ storage_mode 불일치: DB에는 '{current_mode}', 실제는 '{actual_mode}'")
            fix_storage_mode_mismatch(db_manager, actual_mode)
        else:
            logging.info("\n✅ 조합 데이터베이스가 정상입니다.")
        
        # 5. 최종 확인
        logging.info("\n[최종 확인]")
        count = db_manager.combinations_db.count_all_combinations()
        logging.info(f"총 조합 개수: {count:,}")
        
        # 샘플 조합 가져오기
        sample_combs = db_manager.get_base_combinations()[:5]
        if sample_combs:
            logging.info(f"샘플 조합: {sample_combs}")
        else:
            logging.warning("조합을 가져올 수 없습니다!")
            
        return True
        
    except Exception as e:
        logging.error(f"진단 중 오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)