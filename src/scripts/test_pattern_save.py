#!/usr/bin/env python3
"""
패턴 분석 저장 테스트 - 16개 패턴이 모두 저장되는지 확인
"""
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.core.pattern_manager import PatternManager

# 로깅 설정
setup_logging()

def test_pattern_save():
    """패턴 저장 테스트"""
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 패턴 매니저 초기화
        pattern_manager = PatternManager(db_manager)
        
        # 최신 회차 가져오기
        latest_round = db_manager.lotto_db.get_last_round()
        logging.info(f"최신 회차: {latest_round}")
        
        # 패턴 분석 실행
        logging.info("패턴 분석 시작...")
        success = pattern_manager.analyze_patterns(latest_round)
        
        if success:
            logging.info("패턴 분석 완료! 저장된 패턴 확인 중...")
            
            # 저장된 패턴 조회
            saved_patterns = db_manager.get_latest_pattern_analysis()
            
            if saved_patterns and 'patterns' in saved_patterns:
                patterns = saved_patterns['patterns']
                logging.info(f"\n✅ 저장된 패턴 개수: {len(patterns)}개")
                logging.info("저장된 패턴 목록:")
                
                expected_patterns = [
                    'number_match', 'odd_even', 'consecutive', 'sum_range',
                    'fixed_step', 'last_digit', 'max_gap', 'section_distribution',
                    'number_average', 'multiple', 'ten_section', 'arithmetic_sequence',
                    'geometric_sequence', 'alternating_odd_even', 'sum_multiple', 'dispersion'
                ]
                
                for i, pattern_name in enumerate(patterns.keys(), 1):
                    logging.info(f"  {i}. {pattern_name}")
                
                # 누락된 패턴 확인
                missing_patterns = []
                for expected in expected_patterns:
                    if expected not in patterns:
                        missing_patterns.append(expected)
                
                if missing_patterns:
                    logging.warning(f"\n⚠️ 누락된 패턴: {missing_patterns}")
                else:
                    logging.info("\n✅ 모든 16개 패턴이 성공적으로 저장되었습니다!")
                    
                # 각 패턴 데이터 확인
                logging.info("\n패턴별 데이터 확인:")
                for pattern_name, pattern_data in patterns.items():
                    if pattern_data:
                        logging.info(f"  - {pattern_name}: 데이터 있음 ✓")
                    else:
                        logging.warning(f"  - {pattern_name}: 데이터 없음 ✗")
                        
            else:
                logging.error("저장된 패턴을 찾을 수 없습니다.")
        else:
            logging.error("패턴 분석 실패!")
            
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pattern_save()