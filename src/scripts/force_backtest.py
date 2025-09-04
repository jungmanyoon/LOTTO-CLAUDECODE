#!/usr/bin/env python3
"""
백테스팅 강제 실행 스크립트
백테스팅 카운터가 증가하지 않는 문제를 해결하기 위한 스크립트
"""
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import logging
from src.core.db_manager import DatabaseManager
from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop

def main():
    """백테스팅 강제 실행"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
    )
    
    logging.info("백테스팅 강제 실행 시작...")
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 향상된 피드백 루프 초기화
        enhanced_feedback = EnhancedFeedbackLoop(db_manager)
        
        # 현재 상태 확인
        current_count = enhanced_feedback.improvement_manager.state['total_backtest_count']
        logging.info(f"현재 백테스팅 횟수: {current_count}")
        
        # 백테스팅 실행 (최근 50회차)
        latest_round = 1182  # 또는 db_manager.get_latest_round()
        start_round = max(1, latest_round - 50)
        
        logging.info(f"백테스팅 실행: {start_round}회차 ~ {latest_round}회차")
        
        # 강제로 백테스팅 실행 (개선 여부와 관계없이)
        logging.info("강제 백테스팅 실행 중...")
        
        # 백테스팅 프레임워크 직접 실행
        backtest_results = enhanced_feedback.backtesting_framework.run_backtest(
            start_round, latest_round, window_size=100
        )
        
        # 백테스팅 결과를 직접 추적
        improvement_info = enhanced_feedback.improvement_manager.track_backtest(backtest_results)
        
        logging.info(f"백테스팅 #{improvement_info['backtest_number']} 완료")
        logging.info(f"전체 성능: {improvement_info['old_performance']['overall']:.3f} → "
                    f"{improvement_info['new_performance']['overall']:.3f}")
        
        # 결과 확인
        new_count = enhanced_feedback.improvement_manager.state['total_backtest_count']
        logging.info(f"백테스팅 완료! 새로운 횟수: {new_count}")
        
        if new_count > current_count:
            logging.info(f"✅ 백테스팅 카운터가 {current_count}에서 {new_count}로 증가했습니다!")
        else:
            logging.warning("⚠️ 백테스팅 카운터가 증가하지 않았습니다.")
            
        # 상태 저장 강제 실행
        enhanced_feedback.improvement_manager.save_state()
        logging.info("상태 저장 완료")
        
        # 상태 보고서 출력 (이모지 제거를 위해 encode/decode 사용)
        report = enhanced_feedback.improvement_manager.get_status_report()
        try:
            print(report)
        except UnicodeEncodeError:
            # 이모지를 제거하고 출력
            safe_report = report.encode('ascii', 'ignore').decode('ascii')
            print(safe_report)
        
    except Exception as e:
        logging.error(f"백테스팅 실행 중 오류: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    main()