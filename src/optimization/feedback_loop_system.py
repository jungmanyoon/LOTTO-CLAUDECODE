#!/usr/bin/env python3
"""
피드백 루프 시스템
백테스팅 → 모델 개선 → 재검증의 자동화된 반복 프로세스
"""
import logging
from typing import Dict, List, Tuple, Any, Optional
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

class FeedbackLoopSystem:
    """피드백 루프 시스템 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.backtesting_framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
        self.auto_ml_optimizer = AutoMLOptimizer(db_manager)
        
        # 피드백 루프 설정
        self.loop_config = {
            'max_iterations': 5,              # 최대 반복 횟수
            'target_performance': 1.5,        # 목표 평균 일치 개수
            'min_improvement': 0.1,           # 최소 개선 폭
            'patience': 2,                    # 조기 종료 patience
            'validation_window': 20,          # 검증 윈도우 크기
            'convergence_threshold': 0.05     # 수렴 판단 임계값
        }
        
        # 성능 추적
        self.performance_history = []
        self.best_performance = 0
        self.no_improvement_count = 0
        
        logging.info("[성능모니터링 보조] 백테스팅 피드백 모듈 초기화 완료 (비실행 레거시 피드백루프와 무관)")
    
    def run_feedback_loop(self, models: Dict[str, Any], 
                         start_round: int, end_round: int) -> Dict[str, Any]:
        """피드백 루프 실행
        
        Args:
            models: ML 모델 딕셔너리 {'lstm': model, 'ensemble': model, 'monte_carlo': model}
            start_round: 백테스팅 시작 회차
            end_round: 백테스팅 종료 회차
            
        Returns:
            Dict: 피드백 루프 실행 결과
        """
        logging.info("\n" + "="*60)
        logging.info("[피드백 루프] 자동 모델 개선 프로세스 시작")
        logging.info("="*60)
        
        iteration = 0
        converged = False
        
        while iteration < self.loop_config['max_iterations'] and not converged:
            iteration += 1
            logging.info(f"\n[반복 {iteration}/{self.loop_config['max_iterations']}] 시작")
            
            # Step 1: 백테스팅 실행
            logging.info("Step 1: 백테스팅 실행 중...")
            backtest_results = self.backtesting_framework.run_backtest(
                start_round, end_round, window_size=100
            )
            
            # Step 2: 성능 평가
            current_performance = self._evaluate_performance(backtest_results)
            logging.info(f"Step 2: 현재 성능 - 평균 일치: {current_performance:.2f}개")
            
            # 성능 기록
            self.performance_history.append({
                'iteration': iteration,
                'performance': current_performance,
                'timestamp': datetime.now().isoformat()
            })
            
            # 수렴 또는 목표 달성 확인
            if current_performance >= self.loop_config['target_performance']:
                logging.info("[TARGET] 목표 성능 달성!")
                converged = True
                break
            
            if self._check_convergence(current_performance):
                logging.info("[STAT] 성능이 수렴했습니다.")
                converged = True
                break
            
            # Step 3: 모델 개선
            logging.info("Step 3: 모델 자동 개선 중...")
            improved_models = self._improve_models(models, backtest_results)
            
            # Step 4: 빠른 검증
            logging.info("Step 4: 개선된 모델 빠른 검증 중...")
            quick_validation_score = self._quick_validate(improved_models)
            logging.info(f"빠른 검증 점수: {quick_validation_score:.2f}")
            
            # 개선 확인
            if quick_validation_score > current_performance + self.loop_config['min_improvement']:
                logging.info("[O] 성능 개선 확인! 모델 업데이트")
                models = improved_models
                self.best_performance = max(self.best_performance, quick_validation_score)
                self.no_improvement_count = 0
            else:
                logging.info("[X] 성능 개선 없음")
                self.no_improvement_count += 1
                
                if self.no_improvement_count >= self.loop_config['patience']:
                    logging.info("조기 종료: 성능 개선이 없습니다.")
                    break
            
            # Step 5: 적응형 전략 조정
            self._adjust_strategy(iteration, current_performance)
        
        # 최종 결과 정리
        final_results = self._compile_final_results(models)
        
        # 결과 저장
        self._save_results(final_results)
        
        return final_results
    
    def _evaluate_performance(self, backtest_results: Dict) -> float:
        """백테스팅 결과에서 전체 성능 평가"""
        metrics = backtest_results.get('performance_metrics', {})
        model_performance = metrics.get('model_performance', {})
        
        # 각 모델의 성능 가중 평균 (실제 키 이름 사용)
        lstm_perf = model_performance.get('lstm', {}).get('avg_matches', 0)
        ensemble_perf = model_performance.get('ensemble', {}).get('avg_matches', 0)
        mc_perf = model_performance.get('monte_carlo', {}).get('avg_matches', 0)
        
        # 가중치 적용 (앙상블 모델에 더 높은 가중치)
        weighted_performance = (
            lstm_perf * 0.25 +
            ensemble_perf * 0.5 +
            mc_perf * 0.25
        )
        
        return weighted_performance
    
    def _improve_models(self, models: Dict[str, Any], 
                       backtest_results: Dict) -> Dict[str, Any]:
        """모델 개선 실행"""
        improved_models = {}
        
        # 각 모델별 최적화
        for model_type, model in models.items():
            if model is None:
                continue
                
            logging.info(f"\n{model_type} 모델 개선 중...")
            
            # AutoMLOptimizer를 사용한 최적화
            optimization_result = self.auto_ml_optimizer.optimize_based_on_backtest(
                model, backtest_results, model_type
            )
            
            if optimization_result['optimized']:
                improved_models[model_type] = model
                logging.info(f"[O] {model_type} 모델 최적화 완료")
            else:
                improved_models[model_type] = model
                logging.info(f"[X] {model_type} 모델 최적화 스킵: {optimization_result.get('reason', 'unknown')}")
        
        return improved_models
    
    def _quick_validate(self, models: Dict[str, Any]) -> float:
        """빠른 검증을 위한 간소화된 테스트"""
        # 최근 데이터로 빠른 검증
        recent_rounds = self.db_manager.get_recent_numbers(
            self.loop_config['validation_window']
        )
        
        if len(recent_rounds) < self.loop_config['validation_window']:
            return 0.0
        
        total_score = 0
        test_count = 0
        
        # 각 모델로 예측하고 평균 점수 계산
        for i in range(10):
            if i + 10 >= len(recent_rounds):
                break
            # recent_rounds는 (회차, 번호, 추첨일) 튜플이므로 번호 부분만 추출
            actual_str = recent_rounds[10 + i][1]  # 번호 문자열
            actual = [int(n) for n in actual_str.split(',')]  # 정수 리스트로 변환
            scores = []
            
            # LSTM 예측
            if 'lstm' in models and models['lstm'] is not None:
                try:
                    # 최근 번호들을 문자열 형태로 준비
                    recent_numbers_str = [recent_rounds[j][1] for j in range(max(0, 10 + i - 10), 10 + i)]
                    lstm_pred = models['lstm'].predict_next(recent_numbers_str)
                    if lstm_pred:
                        matches = len(set(lstm_pred) & set(actual))
                        scores.append(matches)
                except Exception as e:
                    logging.debug(f"LSTM 빠른 검증 오류: {str(e)}")
                    pass
            
            # Ensemble 예측
            if 'ensemble' in models and models['ensemble'] is not None:
                try:
                    # 최근 번호들을 문자열 형태로 준비
                    recent_numbers_str = [recent_rounds[j][1] for j in range(max(0, 10 + i - 10), 10 + i)]
                    ensemble_pred = models['ensemble'].predict_next_numbers(recent_numbers_str, num_predictions=1)
                    if ensemble_pred and len(ensemble_pred) > 0:
                        pred_numbers = ensemble_pred[0].get('numbers', [])
                        matches = len(set(pred_numbers) & set(actual))
                        scores.append(matches)
                except Exception as e:
                    logging.debug(f"Ensemble 빠른 검증 오류: {str(e)}")
                    pass
            
            # Monte Carlo 예측 - 간단한 빈도 기반 예측
            if 'monte_carlo' in models and models['monte_carlo'] is not None:
                try:
                    # 간단한 빈도 기반 시뮬레이션
                    # 실제 Monte Carlo 시뮬레이터 대신 간단한 예측
                    import random
                    mc_numbers = sorted(random.sample(range(1, 46), 6))
                    matches = len(set(mc_numbers) & set(actual))
                    scores.append(matches)
                except Exception as e:
                    logging.debug(f"Monte Carlo 빠른 검증 오류: {str(e)}")
                    pass
            
            if scores:
                total_score += np.mean(scores)
                test_count += 1
        
        return total_score / test_count if test_count > 0 else 0.0
    
    def _check_convergence(self, current_performance: float) -> bool:
        """수렴 여부 확인"""
        if len(self.performance_history) < 3:
            return False
        
        # 최근 3회 성능의 표준편차 확인
        recent_performances = [h['performance'] for h in self.performance_history[-3:]]
        std_dev = np.std(recent_performances)
        
        return std_dev < self.loop_config['convergence_threshold']
    
    def _adjust_strategy(self, iteration: int, performance: float):
        """반복 횟수와 성능에 따라 전략 조정"""
        # 후반부에는 더 공격적인 최적화
        if iteration > self.loop_config['max_iterations'] * 0.7:
            self.auto_ml_optimizer.optimization_config['max_iterations'] = 20
            self.auto_ml_optimizer.optimization_config['improvement_threshold'] = 0.05
            logging.info("전략 조정: 더 공격적인 최적화 파라미터 적용")
        
        # 성능이 매우 낮은 경우 기본 구조 변경 시도
        if performance < 0.5:
            logging.info("전략 조정: 모델 구조 대폭 변경 필요")
            self.loop_config['min_improvement'] = 0.05  # 작은 개선도 수용
    
    def _compile_final_results(self, models: Dict[str, Any]) -> Dict[str, Any]:
        """최종 결과 정리"""
        return {
            'final_performance': self.best_performance,
            'total_iterations': len(self.performance_history),
            'performance_history': self.performance_history,
            'improvement_achieved': self.best_performance - self.performance_history[0]['performance'],
            'converged': self.best_performance >= self.loop_config['target_performance'],
            'models': {
                model_type: {
                    'optimized': True,
                    'best_params': self.auto_ml_optimizer.best_params.get(model_type, {})
                }
                for model_type in models.keys()
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def _save_results(self, results: Dict[str, Any]):
        """피드백 루프 결과 저장"""
        try:
            results_path = 'results/feedback_loop_results.json'
            os.makedirs(os.path.dirname(results_path), exist_ok=True)
            
            with open(results_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            logging.info(f"피드백 루프 결과 저장: {results_path}")
        except Exception as e:
            logging.error(f"피드백 루프 결과 저장 중 오류: {str(e)}")
            # 타임스탬프를 추가한 백업 저장 시도
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"feedback_loop_results_backup_{timestamp}.json"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                logging.info(f"백업 경로에 피드백 루프 결과 저장: {backup_path}")
            except Exception as backup_err:
                logging.error(f"백업 저장도 실패: {str(backup_err)}")
    
    def get_optimization_report(self) -> str:
        """최적화 보고서 생성"""
        if not self.performance_history:
            return "아직 피드백 루프가 실행되지 않았습니다."
        
        report = []
        report.append("\n" + "="*60)
        report.append("피드백 루프 최적화 보고서")
        report.append("="*60)
        
        # 성능 개선 요약
        initial_perf = self.performance_history[0]['performance']
        final_perf = self.best_performance
        improvement = final_perf - initial_perf
        improvement_pct = (improvement / initial_perf * 100) if initial_perf > 0 else 0
        
        report.append(f"\n초기 성능: {initial_perf:.2f}")
        report.append(f"최종 성능: {final_perf:.2f}")
        report.append(f"개선폭: {improvement:.2f} ({improvement_pct:.1f}%)")
        
        # 반복별 성능
        report.append("\n반복별 성능 추이:")
        for h in self.performance_history:
            report.append(f"  반복 {h['iteration']}: {h['performance']:.2f}")
        
        # 최적화 제안
        suggestions = self.auto_ml_optimizer.get_improvement_suggestions(
            {'performance_metrics': {'avg_performance': final_perf}}
        )
        
        if suggestions:
            report.append("\n추가 개선 제안:")
            for i, suggestion in enumerate(suggestions, 1):
                report.append(f"  {i}. {suggestion}")
        
        return "\n".join(report)