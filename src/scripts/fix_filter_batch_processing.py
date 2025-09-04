#!/usr/bin/env python3
"""
필터링 배치 처리 수정 스크립트
- 대량의 조합을 배치로 처리하도록 수정
"""
import logging
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.db_manager import DatabaseManager
from src.core.specialized_databases import CombinationsDB
from src.logger import setup_logging

def add_batch_methods_to_combinations_db():
    """CombinationsDB에 배치 처리 메서드 추가"""
    
    def get_combinations_batch(self, offset=0, limit=100000):
        """조합을 배치로 가져오기
        
        Args:
            offset: 시작 위치
            limit: 가져올 개수
            
        Returns:
            List[str]: 조합 리스트
        """
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                mode = self._get_storage_mode()
                
                if mode == 'optimized':
                    query = "SELECT combination_blob FROM base_combinations_optimized LIMIT ? OFFSET ?"
                else:
                    query = "SELECT combination FROM base_combinations LIMIT ? OFFSET ?"
                    
                cursor.execute(query, (limit, offset))
                result = cursor.fetchall()
                
                combinations = []
                for row in result:
                    try:
                        if mode == 'optimized':
                            # blob에서 비트맵으로 변환 후 디코딩
                            from ..utils.validators import LottoValidator
                            bitmap = LottoValidator.bytes_to_bitmap(row[0])
                            numbers = LottoValidator.decode_combination(bitmap)
                            combinations.append(LottoValidator.combination_to_str(numbers))
                        else:
                            # 문자열 그대로 사용
                            combinations.append(row[0])
                    except Exception as e:
                        logging.error(f"조합 변환 중 오류 발생: {str(e)}")
                
                return combinations
        except Exception as e:
            logging.error(f"배치 조합 조회 중 오류 발생: {str(e)}")
            return []
    
    def get_filtered_combinations(self):
        """필터링된 조합 가져오기 (필터 테이블에서)"""
        try:
            with self._create_connection() as conn:
                cursor = conn.cursor()
                
                # filtered_combinations 테이블이 있는지 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filtered_combinations'")
                if not cursor.fetchone():
                    logging.warning("filtered_combinations 테이블이 없습니다. 전체 조합을 반환합니다.")
                    return self.get_base_combinations()
                
                # 필터링된 조합 가져오기
                cursor.execute("SELECT combination FROM filtered_combinations")
                result = cursor.fetchall()
                
                return [row[0] for row in result]
        except Exception as e:
            logging.error(f"필터링된 조합 조회 중 오류: {str(e)}")
            return []
    
    # 메서드 추가
    CombinationsDB.get_combinations_batch = get_combinations_batch
    CombinationsDB.get_filtered_combinations = get_filtered_combinations

def test_batch_loading(db_manager):
    """배치 로딩 테스트"""
    try:
        logging.info("\n배치 로딩 테스트 시작...")
        
        # 전체 개수 확인
        total_count = db_manager.combinations_db.count_all_combinations()
        logging.info(f"전체 조합 개수: {total_count:,}")
        
        if total_count == 0:
            logging.error("조합이 없습니다!")
            return False
        
        # 첫 번째 배치 테스트
        batch_size = 10000
        first_batch = db_manager.combinations_db.get_combinations_batch(0, batch_size)
        logging.info(f"첫 번째 배치 크기: {len(first_batch):,}")
        
        if first_batch:
            logging.info(f"첫 번째 조합 샘플: {first_batch[:3]}")
            return True
        else:
            logging.error("배치를 가져올 수 없습니다!")
            return False
            
    except Exception as e:
        logging.error(f"배치 로딩 테스트 중 오류: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    setup_logging()
    
    logging.info("\n" + "="*60)
    logging.info("필터링 배치 처리 수정")
    logging.info("="*60)
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 배치 메서드 추가
        add_batch_methods_to_combinations_db()
        logging.info("✅ 배치 처리 메서드 추가 완료")
        
        # 배치 로딩 테스트
        success = test_batch_loading(db_manager)
        
        if success:
            logging.info("\n✅ 배치 처리가 정상적으로 작동합니다!")
            
            # FilterManager의 필터링 프로세스도 배치로 수정 필요
            logging.info("\n💡 FilterManager도 배치 처리를 사용하도록 수정이 필요합니다.")
            logging.info("   대량의 조합을 메모리에 한 번에 로드하지 않고 배치로 처리해야 합니다.")
        else:
            logging.error("\n❌ 배치 처리 테스트 실패!")
            
        return success
        
    except Exception as e:
        logging.error(f"스크립트 실행 중 오류: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)