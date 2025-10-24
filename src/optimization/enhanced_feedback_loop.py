#!/usr/bin/env python3
"""
향상된 피드백 루프 시스템
자동 개선 관리자와 통합하여 영구적인 상태 관리 제공
"""
import logging
from typing import Dict, List, Any, Optional
import numpy as np
from datetime import datetime
import json
import os

from ..core.db_manager import DatabaseManager
from ..backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
from ..ml.auto_ml_optimizer import AutoMLOptimizer
from ..ml.lstm_predictor import LSTMPredictor
from ..ml.ensemble_predictor import EnsemblePredictor
from ..probabilistic.monte_carlo_simulator import MonteCarloSimulator
from .auto_improvement_manager import AutoImprovementManager
from .feedback_loop_system import FeedbackLoopSystem

class EnhancedFeedbackLoop:
    """향상된 피드백 루프 시스템"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.improvement_manager = AutoImprovementManager()
        self.base_feedback_loop = FeedbackLoopSystem(db_manager)
        self.backtesting_framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
        self.auto_ml_optimizer = AutoMLOptimizer(db_manager)
        
        # 모델 초기화
        self.models = self._initialize_models()
        
        logging.info("향상된 피드백 루프 시스템 초기화 완료")
        
    def _initialize_models(self) -> Dict[str, Any]:
        """모델 초기화 및 이전 최적 파라미터 적용"""
        models = {
            'lstm': LSTMPredictor(),
            'ensemble': EnsemblePredictor(),
            'monte_carlo': MonteCarloSimulator(self.db_manager)
        }
        
        # 저장된 최적 파라미터 적용
        for model_type, model in models.items():
            best_params = self.improvement_manager.get_best_params(model_type)
            if best_params:
                logging.info(f"{model_type} 모델에 이전 최적 파라미터 적용")
                self._apply_params_to_model(model, best_params, model_type)
        
        return models
    
    def _apply_params_to_model(self, model: Any, params: Dict[str, Any], model_type: str):
        """모델에 파라미터 적용"""
        try:
            if model_type == 'lstm' and hasattr(model, 'rebuild_model'):
                model.rebuild_model(params)
            elif model_type == 'ensemble' and hasattr(model, 'apply_best_params'):
                model.apply_best_params(params)
            elif model_type == 'monte_carlo' and hasattr(model, 'update_parameters'):
                model.update_parameters(params)
        except Exception as e:
            logging.error(f"{model_type} 모델 파라미터 적용 실패: {e}")
    
    def run_improvement_cycle(self, start_round: int, end_round: int, 
                            max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """개선 사이클 실행
        
        Args:
            start_round: 백테스팅 시작 회차
            end_round: 백테스팅 종료 회차
            max_iterations: 최대 반복 횟수 (None이면 자동 결정)
            
        Returns:
            Dict: 개선 사이클 결과
        """
        logging.info("\n" + "="*60)
        logging.info("🚀 향상된 자동 개선 사이클 시작")
        logging.info(f"📊 [시작 시점] 현재까지 총 백테스팅 횟수: {self.improvement_manager.state['total_backtest_count']}회")
        logging.info("="*60)

        # 시작 시점에서는 상태 보고서를 출력하지 않음 (혼란 방지)
        # 백테스팅이 실제로 실행된 후에만 의미있는 횟수가 표시됨
        
        if max_iterations is None:
            max_iterations = self.improvement_manager.config['max_iterations_per_session']
        
        iteration = 0
        cycle_results = {
            'start_time': datetime.now().isoformat(),
            'iterations': [],
            'total_improvements': 0,
            'final_performance': None
        }
        
        while iteration < max_iterations and self.improvement_manager.should_continue_improvement():
            iteration += 1
            logging.info(f"\n[반복 {iteration}/{max_iterations}] 시작")
            
            # Step 1: 백테스팅 실행
            logging.info("Step 1: 백테스팅 실행 중...")
            backtest_results = self.backtesting_framework.run_backtest(
                start_round, end_round, window_size=100
            )
            
            # Step 2: 개선 추적 및 판단
            logging.info("Step 2: 성능 평가 및 개선 판단...")
            improvement_info = self.improvement_manager.track_backtest(backtest_results)
            
            logging.info(f"백테스팅 #{improvement_info['backtest_number']} 완료")
            logging.info(f"전체 성능: {improvement_info['old_performance']['overall']:.3f} → "
                        f"{improvement_info['new_performance']['overall']:.3f}")
            
            # Step 3: 개선이 있는 경우에만 모델 업데이트
            if improvement_info['should_update']:
                logging.info("✅ 성능 개선 확인! 모델 최적화 시작...")
                
                # 모델 최적화
                for model_type, model in self.models.items():
                    if improvement_info['improvements'][model_type]['improved']:
                        logging.info(f"{model_type} 모델 최적화 중...")
                        
                        # AutoMLOptimizer를 사용한 최적화
                        optimization_result = self.auto_ml_optimizer.optimize_based_on_backtest(
                            model, backtest_results, model_type
                        )
                        
                        if optimization_result['optimized']:
                            # 최적화된 파라미터 저장
                            best_params = self.auto_ml_optimizer.best_params.get(model_type, {})
                            self.improvement_manager.update_model_params(model_type, best_params)
                            
                            cycle_results['total_improvements'] += 1
            else:
                logging.info("❌ 성능 개선 없음. 파라미터 유지.")
            
            # 반복 결과 기록
            cycle_results['iterations'].append({
                'iteration': iteration,
                'backtest_number': improvement_info['backtest_number'],
                'improved': improvement_info['should_update'],
                'performance': improvement_info['new_performance']
            })
            
            # 중간 상태 저장
            self.improvement_manager.save_state()
        
        # 최종 결과 정리
        cycle_results['end_time'] = datetime.now().isoformat()
        cycle_results['final_performance'] = self.improvement_manager.state['current_performance']
        
        # 최종 보고서 출력
        logging.info("\n" + "="*60)
        logging.info("🏁 개선 사이클 완료!")
        logging.info(f"📊 [완료 시점] 총 백테스팅 횟수: {self.improvement_manager.state['total_backtest_count']}회")
        logging.info(f"📈 이번 사이클에서 실행된 반복 횟수: {iteration}회")
        logging.info(f"✅ 총 누적 백테스팅 횟수: {self.improvement_manager.state['total_backtest_count']}회")
        logging.info("="*60)

        # 완료 후 전체 상태 보고서 출력
        try:
            logging.info(self.improvement_manager.get_status_report())
        except Exception as e:
            logging.debug(f"상태 보고서 출력 중 오류 (무시됨): {e}")
        
        return cycle_results
    
    def apply_best_settings(self):
        """최고 성능 설정 적용"""
        logging.info("최고 성능 설정을 적용합니다...")
        
        # 필터 설정 적용
        filter_settings = self.improvement_manager.get_current_filter_settings()
        logging.info(f"필터 설정: {filter_settings}")
        
        # 모델 파라미터 적용
        for model_type, model in self.models.items():
            best_params = self.improvement_manager.get_best_params(model_type)
            if best_params:
                self._apply_params_to_model(model, best_params, model_type)
                logging.info(f"{model_type} 모델에 최적 파라미터 적용 완료")
    
    def get_models(self) -> Dict[str, Any]:
        """현재 모델 반환"""
        return self.models
    
    def get_filter_settings(self) -> Dict[str, Any]:
        """현재 필터 설정 반환"""
        return self.improvement_manager.get_current_filter_settings()


def demo_continuous_improvement():
    """지속적인 개선 데모"""
    from ..logger import setup_logging
    setup_logging()
    
    # 시스템 초기화
    enhanced_loop = EnhancedFeedbackLoop()
    
    # 개선 사이클 실행 (최근 50회차 백테스팅)
    results = enhanced_loop.run_improvement_cycle(
        start_round=1133,
        end_round=1182,
        max_iterations=5  # 5번 반복
    )
    
    # 결과 출력
    logging.info(f"\n총 개선 횟수: {results['total_improvements']}")
    logging.info(f"최종 성능: {results['final_performance']}")
    
    # 최적 설정 적용
    enhanced_loop.apply_best_settings()
    
    return enhanced_loop


if __name__ == "__main__":
    demo_continuous_improvement()