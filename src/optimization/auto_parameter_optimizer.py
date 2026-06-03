"""
자동 파라미터 최적화 시스템
필터 파라미터를 자동으로 조정하여 최적의 성능을 찾는 시스템
"""

import logging
import json
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import yaml
import random
import itertools

class AutoParameterOptimizer:
    """자동 파라미터 최적화 시스템"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.results_dir = "results/optimization"
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 현재 설정 로드
        self.current_config = self._load_config()
        
        # 최적화 이력
        self.optimization_history = []
        
        # 파라미터 범위 정의
        self.parameter_bounds = self._define_parameter_bounds()
        
        logging.info("자동 파라미터 최적화 시스템 초기화")
    
    def _load_config(self) -> Dict:
        """현재 설정 파일 로드"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _save_config(self, config: Dict, backup: bool = True):
        """설정 파일 저장"""
        if backup:
            # 백업 생성
            backup_path = f"{self.config_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            with open(backup_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.current_config, f, allow_unicode=True, default_flow_style=False)
        
        # 새 설정 저장
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    def _define_parameter_bounds(self) -> Dict[str, Tuple[float, float]]:
        """파라미터 최적화 범위 정의"""
        return {
            # Match 필터
            'match_max': (2, 5),  # 최대 일치 개수
            
            # Odd/Even 필터
            'odd_even_min': (1, 3),  # 최소 홀수 개수
            'odd_even_max': (3, 5),  # 최대 홀수 개수
            
            # Consecutive 필터
            'consecutive_max': (2, 4),  # 최대 연속 개수
            
            # Sum Range 필터
            'sum_min': (70, 110),  # 최소 합계
            'sum_max': (160, 210),  # 최대 합계
            
            # Average 필터
            'avg_min': (10, 18),  # 최소 평균
            'avg_max': (28, 37),  # 최대 평균
            
            # Dispersion 필터
            'std_dev_min': (5, 10),  # 최소 표준편차
            'std_dev_max': (12, 18),  # 최대 표준편차
            
            # Section 필터
            'section_max': (2, 4),  # 구간당 최대 개수
            
            # Filter Efficiency (실행 순서 가중치)
            'efficiency_dispersion': (0.01, 0.2),
            'efficiency_sum_range': (0.01, 0.5),
            'efficiency_consecutive': (0.01, 0.4),
            'efficiency_odd_even': (0.01, 0.3)
        }
    
    def _params_to_config(self, params: List[float]) -> Dict:
        """파라미터 배열을 설정 딕셔너리로 변환"""
        config = self.current_config.copy()
        
        # 파라미터 매핑
        idx = 0
        
        # Match 필터
        config['filters']['criteria']['match']['max_match'] = int(params[idx])
        idx += 1
        
        # Odd/Even 필터
        odd_min = int(params[idx])
        odd_max = int(params[idx + 1])
        excluded = []
        for i in range(7):
            if i < odd_min or i > odd_max:
                excluded.append(i)
        config['filters']['criteria']['odd_even']['excluded_counts'] = excluded
        idx += 2
        
        # Consecutive 필터
        config['filters']['criteria']['consecutive']['max_consecutive'] = int(params[idx])
        idx += 1
        
        # Sum Range 필터
        config['filters']['criteria']['sum_range']['min_sum'] = int(params[idx])
        config['filters']['criteria']['sum_range']['max_sum'] = int(params[idx + 1])
        idx += 2
        
        # Average 필터
        config['filters']['criteria']['average']['min_average'] = float(params[idx])
        config['filters']['criteria']['average']['max_average'] = float(params[idx + 1])
        idx += 2
        
        # Dispersion 필터
        config['filters']['criteria']['dispersion']['min_std_dev'] = float(params[idx])
        config['filters']['criteria']['dispersion']['max_std_dev'] = float(params[idx + 1])
        idx += 2
        
        # Section 필터
        config['filters']['criteria']['section']['max_numbers_per_section'] = int(params[idx])
        idx += 1
        
        # Filter Efficiency
        config['filters']['filter_efficiency']['dispersion'] = float(params[idx])
        config['filters']['filter_efficiency']['sum_range'] = float(params[idx + 1])
        config['filters']['filter_efficiency']['consecutive'] = float(params[idx + 2])
        config['filters']['filter_efficiency']['odd_even'] = float(params[idx + 3])
        
        return config
    
    def _evaluate_parameters(self, params: List[float]) -> float:
        """파라미터 성능 평가 (최소화 목표)"""
        config = self._params_to_config(params)
        
        # 임시 설정 파일 생성
        temp_config = "config_temp.yaml"
        with open(temp_config, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        try:
            # 백테스팅으로 성능 평가
            from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
            from src.core.db_manager import DatabaseManager
            
            db_manager = DatabaseManager()
            backtester = OptimizedBacktestingFramework(db_manager)
            
            # [N-C07] 수정:
            #   결함1: model_types 파라미터 제거 (run_backtest 시그니처에 없음)
            #          실제 시그니처: run_backtest(start_round, end_round, window_size=100)
            #   결함2: 반환 키 'performance_summary' -> 실제 키 'performance_metrics' 사용
            results = backtester.run_backtest(
                start_round=1165,
                end_round=1185
            )

            # 성능 지표 계산
            if results and 'performance_metrics' in results:
                perf = results['performance_metrics']

                # 모델별 성능에서 평균 일치 개수 집계
                model_performances = perf.get('model_performance', {})
                total_matches = 0
                total_predictions = 0
                for model_metrics in model_performances.values():
                    avg = model_metrics.get('avg_matches', 0)
                    preds = model_metrics.get('total_predictions', 0)
                    total_matches += avg * preds
                    total_predictions += preds
                avg_match = total_matches / total_predictions if total_predictions > 0 else 0

                filter_stats = results.get('filter_statistics', {})
                filtered_combos = filter_stats.get('total_combinations_after_filter', 100000)
                pass_rate = filtered_combos / 8145060
                
                # 패스율이 너무 낮으면 패널티 (0.5% 미만)
                if pass_rate < 0.005:
                    penalty = 10
                # 패스율이 너무 높으면 패널티 (5% 초과)
                elif pass_rate > 0.05:
                    penalty = 5
                else:
                    penalty = 0
                
                # 점수 계산 (낮을수록 좋음)
                score = -avg_match + penalty + abs(pass_rate - 0.02) * 100
                
                logging.info(f"평가 점수: {score:.4f} (평균 일치: {avg_match:.2f}, 패스율: {pass_rate:.4%})")
                
            else:
                score = 1000  # 실패 시 높은 점수
            
        except Exception as e:
            logging.error(f"파라미터 평가 실패: {e}")
            score = 1000
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_config):
                os.remove(temp_config)
        
        return score
    
    def optimize(self, max_iterations: int = 50, sample_size: int = 10) -> Dict:
        """파라미터 최적화 실행 (Grid Search + Random Search)
        
        Args:
            max_iterations: 최대 반복 횟수
            sample_size: 각 반복에서 평가할 샘플 수
            
        Returns:
            최적화 결과
        """
        logging.info(f"파라미터 최적화 시작 (반복: {max_iterations}, 샘플: {sample_size})")
        
        best_params = None
        best_score = float('inf')
        evaluations = 0
        
        # 그리드 서치 + 랜덤 서치 조합
        for iteration in range(max_iterations):
            # 랜덤 파라미터 생성
            candidates = []
            for _ in range(sample_size):
                params = []
                for min_val, max_val in self.parameter_bounds.values():
                    if isinstance(min_val, int) and isinstance(max_val, int):
                        value = random.randint(min_val, max_val)
                    else:
                        value = random.uniform(min_val, max_val)
                    params.append(value)
                candidates.append(params)
            
            # 각 후보 평가
            for params in candidates:
                score = self._evaluate_parameters(params)
                evaluations += 1
                
                if score < best_score:
                    best_score = score
                    best_params = params
                    logging.info(f"새로운 최적값 발견: 점수 {best_score:.4f}")
                
                # 콜백
                self._optimization_callback(params, best_score)
            
            logging.info(f"반복 {iteration + 1}/{max_iterations} 완료")
        
        # 최적 파라미터로 설정 생성
        optimal_config = self._params_to_config(best_params)
        
        # 결과 저장
        optimization_result = {
            'timestamp': datetime.now().isoformat(),
            'optimal_params': best_params,
            'optimal_score': best_score,
            'iterations': max_iterations,
            'evaluations': evaluations,
            'success': True,
            'message': 'Optimization completed',
            'history': self.optimization_history
        }
        
        # 결과 파일 저장
        result_path = os.path.join(
            self.results_dir,
            f"optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(optimization_result, f, ensure_ascii=False, indent=2)
        
        logging.info(f"최적화 완료: 점수 {best_score:.4f}")
        
        # 최적 설정 저장 옵션
        self._save_optimal_config(optimal_config)
        
        return optimization_result
    
    def _optimization_callback(self, params, best_score):
        """최적화 과정 콜백"""
        iteration = len(self.optimization_history) + 1
        
        self.optimization_history.append({
            'iteration': iteration,
            'params': params,
            'best_score': best_score
        })
    
    def _save_optimal_config(self, optimal_config: Dict):
        """최적 설정 저장"""
        # 최적 설정 파일로 저장
        optimal_path = os.path.join(
            self.results_dir,
            f"config_optimal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        )
        
        with open(optimal_path, 'w', encoding='utf-8') as f:
            yaml.dump(optimal_config, f, allow_unicode=True, default_flow_style=False)
        
        logging.info(f"최적 설정 저장: {optimal_path}")
        
        # 사용자에게 적용 여부 확인
        print("\n" + "="*60)
        print("파라미터 최적화 완료!")
        print("="*60)
        print(f"최적 설정이 저장되었습니다: {optimal_path}")
        print("\n주요 변경사항:")
        self._print_config_diff(self.current_config, optimal_config)
        print("="*60)
    
    def _print_config_diff(self, old_config: Dict, new_config: Dict):
        """설정 변경사항 출력"""
        # Match 필터
        old_match = old_config['filters']['criteria']['match']['max_match']
        new_match = new_config['filters']['criteria']['match']['max_match']
        if old_match != new_match:
            print(f"  Match 최대 일치: {old_match} -> {new_match}")
        
        # Sum Range 필터
        old_sum_min = old_config['filters']['criteria']['sum_range']['min_sum']
        new_sum_min = new_config['filters']['criteria']['sum_range']['min_sum']
        old_sum_max = old_config['filters']['criteria']['sum_range']['max_sum']
        new_sum_max = new_config['filters']['criteria']['sum_range']['max_sum']
        if old_sum_min != new_sum_min or old_sum_max != new_sum_max:
            print(f"  Sum Range: [{old_sum_min}, {old_sum_max}] -> [{new_sum_min}, {new_sum_max}]")
        
        # Average 필터
        old_avg_min = old_config['filters']['criteria']['average']['min_average']
        new_avg_min = new_config['filters']['criteria']['average']['min_average']
        old_avg_max = old_config['filters']['criteria']['average']['max_average']
        new_avg_max = new_config['filters']['criteria']['average']['max_average']
        if old_avg_min != new_avg_min or old_avg_max != new_avg_max:
            print(f"  Average: [{old_avg_min:.1f}, {old_avg_max:.1f}] -> [{new_avg_min:.1f}, {new_avg_max:.1f}]")
    
    def apply_optimal_config(self, config_path: str):
        """최적 설정 적용
        
        Args:
            config_path: 적용할 최적 설정 파일 경로
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            optimal_config = yaml.safe_load(f)
        
        # 백업 후 적용
        self._save_config(optimal_config, backup=True)
        
        logging.info(f"최적 설정 적용 완료: {config_path}")
        print(f"\n최적 설정이 적용되었습니다!")
        print(f"백업 파일: {self.config_path}.backup_*")


def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("자동 파라미터 최적화 시스템")
    print("="*70)
    
    optimizer = AutoParameterOptimizer()
    
    # 간단한 최적화 실행 (테스트용)
    print("\n테스트 최적화 실행 (5회 반복, 샘플 크기 5)")
    result = optimizer.optimize(max_iterations=5, sample_size=5)
    
    if result['success']:
        print(f"\n최적화 성공!")
        print(f"최적 점수: {result['optimal_score']:.4f}")
        print(f"총 평가 횟수: {result['evaluations']}")
    else:
        print(f"\n최적화 실패: {result['message']}")


if __name__ == "__main__":
    main()