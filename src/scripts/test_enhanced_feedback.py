#!/usr/bin/env python3
"""
향상된 피드백 루프 테스트 스크립트
프로그램 재시작 시에도 상태가 유지되는지 확인
"""
import os
import sys
import json
import logging

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop
from src.optimization.auto_improvement_manager import AutoImprovementManager

def test_state_persistence():
    """상태 영속성 테스트"""
    setup_logging()
    
    logging.info("\n" + "="*60)
    logging.info("향상된 피드백 루프 상태 영속성 테스트")
    logging.info("="*60)
    
    # 1. 상태 관리자 초기화 및 현재 상태 확인
    improvement_manager = AutoImprovementManager()
    
    # 현재 상태 출력
    print("\n[현재 저장된 상태]")
    print(improvement_manager.get_status_report())
    
    # 2. 이전 백테스팅 횟수 확인
    previous_count = improvement_manager.state['total_backtest_count']
    logging.info(f"\n이전 총 백테스팅 횟수: {previous_count}회")
    
    # 3. 향상된 피드백 루프 실행 (짧은 테스트)
    db_manager = DatabaseManager()
    enhanced_loop = EnhancedFeedbackLoop(db_manager)
    
    # 짧은 백테스팅 실행 (최근 10회차만)
    logging.info("\n테스트를 위해 짧은 백테스팅 실행...")
    cycle_results = enhanced_loop.run_improvement_cycle(
        start_round=1173,  # 최근 10회차
        end_round=1182,
        max_iterations=2   # 2번만 반복
    )
    
    # 4. 상태 재확인
    logging.info("\n[업데이트된 상태]")
    # 새로운 인스턴스로 상태 확인 (재시작 시뮬레이션)
    new_manager = AutoImprovementManager()
    current_count = new_manager.state['total_backtest_count']
    
    print(new_manager.get_status_report())
    
    # 5. 테스트 결과
    logging.info("\n" + "="*60)
    logging.info("테스트 결과")
    logging.info("="*60)
    logging.info(f"이전 백테스팅 횟수: {previous_count}회")
    logging.info(f"현재 백테스팅 횟수: {current_count}회")
    logging.info(f"증가량: {current_count - previous_count}회")
    
    if current_count > previous_count:
        logging.info("✅ 상태가 성공적으로 저장되고 불러와졌습니다!")
    else:
        logging.warning("❌ 상태 저장/불러오기에 문제가 있을 수 있습니다.")
    
    # 6. 최적 파라미터 확인
    logging.info("\n[저장된 최적 파라미터]")
    for model_type in ['lstm', 'ensemble', 'monte_carlo']:
        params = new_manager.get_best_params(model_type)
        if params:
            logging.info(f"{model_type}: {len(params)}개 파라미터 저장됨")
        else:
            logging.info(f"{model_type}: 파라미터 없음")
    
    # 7. 필터 설정 확인
    filter_settings = new_manager.get_current_filter_settings()
    logging.info("\n[저장된 필터 설정]")
    for filter_name, settings in filter_settings.items():
        logging.info(f"{filter_name}: {settings}")

def test_improvement_logic():
    """개선 로직 테스트"""
    logging.info("\n" + "="*60)
    logging.info("개선 판단 로직 테스트")
    logging.info("="*60)
    
    manager = AutoImprovementManager()
    
    # 테스트용 백테스팅 결과 생성
    test_results = {
        'performance_metrics': {
            'model_performance': {
                'lstm': {'avg_matches': 1.2},
                'ensemble': {'avg_matches': 1.5},
                'monte_carlo': {'avg_matches': 1.3}
            }
        }
    }
    
    # 개선 추적
    improvement_info = manager.track_backtest(test_results)
    
    logging.info(f"\n백테스팅 #{improvement_info['backtest_number']}")
    logging.info(f"개선 여부: {'✅ 예' if improvement_info['should_update'] else '❌ 아니오'}")
    logging.info(f"이유: {', '.join(improvement_info['update_reasons']) if improvement_info['update_reasons'] else '개선 없음'}")
    
    # 각 모델별 개선 정보
    logging.info("\n모델별 개선 정보:")
    for model, info in improvement_info['improvements'].items():
        logging.info(f"  {model}: {info['rate']*100:+.1f}% ({'개선' if info['improved'] else '유지'})")

def check_state_file():
    """상태 파일 직접 확인"""
    state_file = "data/auto_improvement_state.json"
    
    if os.path.exists(state_file):
        logging.info(f"\n상태 파일 존재: {state_file}")
        
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        logging.info(f"파일 생성일: {state.get('created_at', 'Unknown')}")
        logging.info(f"마지막 업데이트: {state.get('last_updated', 'Unknown')}")
        logging.info(f"총 백테스팅 횟수: {state.get('total_backtest_count', 0)}회")
        logging.info(f"개선 이력 수: {len(state.get('improvement_history', []))}개")
    else:
        logging.info(f"\n상태 파일이 없습니다: {state_file}")
        logging.info("첫 실행 시 자동으로 생성됩니다.")

if __name__ == "__main__":
    # 상태 파일 확인
    check_state_file()
    
    # 상태 영속성 테스트
    test_state_persistence()
    
    # 개선 로직 테스트
    test_improvement_logic()
    
    logging.info("\n테스트 완료!")