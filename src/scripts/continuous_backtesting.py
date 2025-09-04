"""
지속적인 백테스팅 실행 스크립트
- 성능 개선 여부와 관계없이 백테스팅 계속 실행
"""

import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.optimization.auto_improvement_manager import AutoImprovementManager
from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ContinuousBacktestingManager(AutoImprovementManager):
    """지속적인 백테스팅을 위한 커스텀 매니저"""
    
    def should_continue_improvement(self, force=True) -> bool:
        """항상 True를 반환하여 백테스팅 계속 실행"""
        if force:
            logging.info("강제 실행 모드: 백테스팅을 계속 진행합니다.")
            return True
        return super().should_continue_improvement()

def run_continuous_backtesting(num_iterations=5):
    """지정된 횟수만큼 백테스팅 실행"""
    # 커스텀 매니저 사용
    improvement_manager = ContinuousBacktestingManager()
    
    # 원래 메서드 백업
    original_method = improvement_manager.should_continue_improvement
    
    # 강제 실행 메서드로 교체
    improvement_manager.should_continue_improvement = lambda: True
    
    # 피드백 루프 생성
    feedback_loop = EnhancedFeedbackLoop(
        ml_optimizer=None,
        filter_optimizer=None,
        improvement_manager=improvement_manager
    )
    
    # 초기 상태
    start_count = improvement_manager.state['total_backtest_count']
    logging.info(f"시작 백테스팅 횟수: {start_count}")
    
    # 지정된 횟수만큼 실행
    for i in range(num_iterations):
        logging.info(f"\n=== 백테스팅 라운드 {i+1}/{num_iterations} ===")
        
        # 한 번의 개선 사이클 실행
        result = feedback_loop.run_improvement_cycle(max_iterations=1)
        
        current_count = improvement_manager.state['total_backtest_count']
        logging.info(f"현재 백테스팅 횟수: {current_count}")
    
    # 메서드 복원
    improvement_manager.should_continue_improvement = original_method
    
    # 최종 결과
    end_count = improvement_manager.state['total_backtest_count']
    logging.info(f"\n총 {end_count - start_count}회의 백테스팅이 추가로 실행되었습니다.")
    logging.info(f"최종 백테스팅 횟수: {end_count}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations', type=int, default=3, help='백테스팅 실행 횟수')
    args = parser.parse_args()
    
    run_continuous_backtesting(args.iterations)