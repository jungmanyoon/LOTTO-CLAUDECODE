"""
강제 백테스팅 실행 스크립트
- should_continue_improvement() 결과와 관계없이 백테스팅 실행
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimization.auto_improvement_manager import AutoImprovementManager
from src.backtesting.integrated_backtester import IntegratedBacktester
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def run_forced_backtesting():
    """강제 백테스팅 실행"""
    logging.info("=== 강제 백테스팅 시작 ===")
    
    # 매니저 초기화
    improvement_manager = AutoImprovementManager()
    
    # 현재 상태 출력
    current_count = improvement_manager.state['total_backtest_count']
    logging.info(f"현재 백테스팅 횟수: {current_count}")
    
    # 백테스터 초기화
    backtester = IntegratedBacktester()
    
    # 백테스팅 실행
    logging.info("백테스팅 실행 중...")
    backtest_results = backtester.run_comprehensive_backtest(test_rounds=10)
    
    # 결과 기록 (카운트 증가)
    improvement_manager.record_improvement(backtest_results)
    
    # 새로운 카운트 확인
    new_count = improvement_manager.state['total_backtest_count']
    logging.info(f"백테스팅 완료! 새로운 횟수: {new_count}")
    
    # 상태 저장
    improvement_manager.save_state()
    
    return new_count - current_count

if __name__ == "__main__":
    increment = run_forced_backtesting()
    print(f"\n백테스팅 횟수가 {increment} 증가했습니다.")