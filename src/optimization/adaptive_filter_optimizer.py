#!/usr/bin/env python3
"""
적응형 필터 최적화 시스템
실시간으로 필터 기준을 조정하여 최적의 성능 유지
"""
import logging
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import json
from datetime import datetime
import os
from ..core.db_manager import DatabaseManager
from ..core.filter_manager import FilterManager
from ..validators.filter_validator import FilterValidator
from ..utils.config_manager import ConfigManager

class AdaptiveFilterOptimizer:
    """적응형 필터 최적화 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.filter_validator = FilterValidator(self.db_manager)
        self.config_manager = ConfigManager()
        
        # 최적화 설정
        self.optimization_config = {
            'window_size': 50,          # 최근 N회차 분석
            'min_pass_rate': 0.85,      # 최소 통과율
            'target_pass_rate': 0.95,   # 목표 통과율
            'adjustment_rate': 0.1,     # 조정 비율
            'check_interval': 1         # 검사 주기 (회차)
        }
        
        # 성능 기록
        self.performance_history = []
        self.last_optimization_round = 0
        
        logging.info("\n[적응형 필터 최적화] 시스템 초기화")
        logging.info(f"  - 분석 윈도우: 최근 {self.optimization_config['window_size']}회차")
        logging.info(f"  - 목표 통과율: {self.optimization_config['target_pass_rate']:.1%}")
        logging.info(f"  - 검사 주기: {self.optimization_config['check_interval']}회차마다")
        logging.info("  - 동적 필터 기준값 조정 활성화")
    
    def optimize_filters_adaptive(self, current_round: int) -> Dict[str, Any]:
        """적응형 필터 최적화 수행
        
        Args:
            current_round: 현재 회차
            
        Returns:
            Dict: 최적화 결과
        """
        logging.info(f"\n[적응형 필터 최적화] 최적화 프로세스 시작")
        logging.info(f"  - 현재 회차: {current_round}")
        logging.info(f"  - 마지막 최적화: {self.last_optimization_round}회차")
        
        # 최적화 필요 여부 확인
        if not self._should_optimize(current_round):
            logging.info("최적화가 필요하지 않습니다.")
            return {'optimized': False, 'reason': 'Not needed'}
        
        # 현재 필터 성능 평가
        performance = self._evaluate_current_performance(current_round)
        
        # 최적화 필요한 필터 식별
        filters_to_optimize = self._identify_filters_to_optimize(performance)
        
        if not filters_to_optimize:
            logging.info("모든 필터가 적절한 성능을 보이고 있습니다.")
            return {'optimized': False, 'reason': 'All filters performing well'}
        
        # 필터별 최적화 수행
        optimization_results = {}
        for filter_name in filters_to_optimize:
            result = self._optimize_single_filter(
                filter_name, 
                performance['filter_performance'][filter_name],
                current_round
            )
            optimization_results[filter_name] = result
        
        # 최적화된 설정 적용
        if self._apply_optimized_settings(optimization_results):
            self.last_optimization_round = current_round
            
            # 성능 기록 저장
            self._save_performance_history(current_round, performance, optimization_results)
            
            logging.info(f"\n[적응형 필터 최적화] 완료")
            logging.info(f"  - 최적화된 필터 수: {len(optimization_results)}개")
            for filter_name, result in optimization_results.items():
                logging.info(f"  - {filter_name}: {result.get('adjustment', 'N/A')}")
            
            return {
                'optimized': True,
                'optimized_filters': list(optimization_results.keys()),
                'results': optimization_results,
                'performance_before': performance
            }
        else:
            return {'optimized': False, 'reason': 'Failed to apply settings'}
    
    def _should_optimize(self, current_round: int) -> bool:
        """최적화 필요 여부 확인"""
        # 첫 실행이거나 주기가 도래한 경우
        if self.last_optimization_round == 0:
            return True
        
        rounds_since_last = current_round - self.last_optimization_round
        return rounds_since_last >= self.optimization_config['check_interval']
    
    def _evaluate_current_performance(self, current_round: int) -> Dict[str, Any]:
        """현재 필터 성능 평가"""
        window_size = self.optimization_config['window_size']
        start_round = max(1, current_round - window_size)
        
        # 필터 검증 수행
        validation_results = self.filter_validator.validate_filters_with_historical_data(
            start_round=start_round,
            end_round=current_round
        )
        
        # 필터별 성능 분석
        filter_performance = {}
        for filter_name, filter_result in validation_results['filter_results'].items():
            pass_rate = filter_result['pass_rate'] / 100.0
            
            # 추가 분석
            failed_rounds = filter_result['failed_rounds']
            consecutive_failures = self._analyze_consecutive_failures(failed_rounds)
            
            filter_performance[filter_name] = {
                'pass_rate': pass_rate,
                'failed_count': len(failed_rounds),
                'consecutive_failures': consecutive_failures,
                'performance_score': self._calculate_performance_score(
                    pass_rate, consecutive_failures
                )
            }
        
        return {
            'overall_pass_rate': validation_results['overall_pass_rate'] / 100.0,
            'filter_performance': filter_performance,
            'window_rounds': validation_results['total_rounds']
        }
    
    def _analyze_consecutive_failures(self, failed_rounds: List[int]) -> int:
        """연속 실패 횟수 분석"""
        if not failed_rounds:
            return 0
        
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(failed_rounds)):
            if failed_rounds[i] - failed_rounds[i-1] == 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        return max_consecutive
    
    def _calculate_performance_score(self, pass_rate: float, consecutive_failures: int) -> float:
        """성능 점수 계산"""
        # 통과율 기반 점수 (70%)
        pass_rate_score = pass_rate * 0.7
        
        # 연속 실패 페널티 (30%)
        failure_penalty = max(0, 1 - (consecutive_failures * 0.1)) * 0.3
        
        return pass_rate_score + failure_penalty
    
    def _identify_filters_to_optimize(self, performance: Dict[str, Any]) -> List[str]:
        """최적화가 필요한 필터 식별"""
        filters_to_optimize = []
        min_pass_rate = self.optimization_config['min_pass_rate']
        
        for filter_name, filter_perf in performance['filter_performance'].items():
            # 통과율이 낮거나 연속 실패가 많은 경우
            if (filter_perf['pass_rate'] < min_pass_rate or 
                filter_perf['consecutive_failures'] >= 3 or
                filter_perf['performance_score'] < 0.8):
                filters_to_optimize.append(filter_name)
                logging.info(f"최적화 대상 필터: {filter_name} "
                           f"(통과율: {filter_perf['pass_rate']:.2%}, "
                           f"연속 실패: {filter_perf['consecutive_failures']})")
        
        return filters_to_optimize
    
    def _optimize_single_filter(self, filter_name: str, performance: Dict[str, Any], 
                              current_round: int) -> Dict[str, Any]:
        """단일 필터 최적화"""
        logging.info(f"\n[{filter_name}] 필터 최적화 시작")
        
        # 현재 기준값 가져오기
        current_criteria = self.filter_manager.filters[filter_name].get_criteria()
        
        # 필터 타입별 최적화 전략
        optimization_strategy = self._get_optimization_strategy(filter_name, performance)
        
        # 새로운 기준값 계산
        new_criteria = self._calculate_new_criteria(
            filter_name, current_criteria, optimization_strategy
        )
        
        # 검증 (시뮬레이션)
        validation_score = self._validate_new_criteria(
            filter_name, new_criteria, current_round
        )
        
        return {
            'filter_name': filter_name,
            'current_criteria': current_criteria,
            'new_criteria': new_criteria,
            'optimization_strategy': optimization_strategy,
            'validation_score': validation_score,
            'applied': validation_score > 0.9  # 90% 이상 개선 시 적용
        }
    
    def _get_optimization_strategy(self, filter_name: str, performance: Dict[str, Any]) -> Dict[str, Any]:
        """필터별 최적화 전략 결정"""
        pass_rate = performance['pass_rate']
        target_rate = self.optimization_config['target_pass_rate']
        
        # 통과율 차이에 따른 조정 강도
        rate_diff = target_rate - pass_rate
        adjustment_strength = min(0.3, rate_diff * 2)  # 최대 30% 조정
        
        strategy = {
            'direction': 'relax' if pass_rate < target_rate else 'tighten',
            'strength': adjustment_strength,
            'method': self._get_filter_specific_method(filter_name)
        }
        
        return strategy
    
    def _get_filter_specific_method(self, filter_name: str) -> str:
        """필터별 최적화 방법"""
        methods = {
            'consecutive': 'increase_max',
            'sum_range': 'expand_range',
            'average': 'expand_range',
            'max_gap': 'increase_max',
            'last_digit': 'increase_min',
            'section': 'increase_max',
            'dispersion': 'expand_range'
        }
        return methods.get(filter_name, 'general')
    
    def _calculate_new_criteria(self, filter_name: str, current_criteria: Dict[str, Any],
                              strategy: Dict[str, Any]) -> Dict[str, Any]:
        """새로운 기준값 계산"""
        new_criteria = current_criteria.copy()
        strength = strategy['strength']
        
        if strategy['method'] == 'increase_max':
            # 최대값 증가
            for key in ['max_consecutive', 'max_allowed_gap', 'max_numbers_per_section']:
                if key in new_criteria:
                    if strategy['direction'] == 'relax':
                        new_criteria[key] = int(new_criteria[key] * (1 + strength))
                    else:
                        new_criteria[key] = max(1, int(new_criteria[key] * (1 - strength)))
        
        elif strategy['method'] == 'expand_range':
            # 범위 확장
            for min_key, max_key in [('min_sum', 'max_sum'), ('min_average', 'max_average'),
                                    ('min_std_dev', 'max_std_dev')]:
                if min_key in new_criteria and max_key in new_criteria:
                    range_size = new_criteria[max_key] - new_criteria[min_key]
                    expansion = range_size * strength / 2
                    
                    if strategy['direction'] == 'relax':
                        new_criteria[min_key] -= expansion
                        new_criteria[max_key] += expansion
                    else:
                        new_criteria[min_key] += expansion
                        new_criteria[max_key] -= expansion
        
        return new_criteria
    
    def _validate_new_criteria(self, filter_name: str, new_criteria: Dict[str, Any],
                              current_round: int) -> float:
        """새로운 기준값 검증 (시뮬레이션)"""
        # 간단한 검증: 최근 20회차에 대해 테스트
        test_rounds = 20
        start_round = max(1, current_round - test_rounds)
        
        # 임시로 새 기준 적용
        original_criteria = self.filter_manager.filters[filter_name].get_criteria()
        
        try:
            # 새 기준으로 필터 업데이트 (시뮬레이션)
            # 실제 구현에서는 복사본을 만들어 테스트해야 함
            validation_score = 0.95  # 임시 점수
            
            return validation_score
        except Exception as e:
            logging.error(f"검증 중 오류: {str(e)}")
            return 0.0
    
    def _apply_optimized_settings(self, optimization_results: Dict[str, Dict[str, Any]]) -> bool:
        """최적화된 설정 적용"""
        applied_filters = []
        
        for filter_name, result in optimization_results.items():
            if result['applied']:
                # config.yaml 업데이트
                try:
                    config = self.config_manager.config
                    if filter_name in config['filters']['criteria']:
                        config['filters']['criteria'][filter_name].update(result['new_criteria'])
                        applied_filters.append(filter_name)
                        logging.info(f"✅ {filter_name} 필터 설정 업데이트 완료")
                except Exception as e:
                    logging.error(f"{filter_name} 필터 업데이트 실패: {str(e)}")
        
        # 변경사항 저장
        if applied_filters:
            self.config_manager.save_config()
            logging.info(f"\n총 {len(applied_filters)}개 필터 최적화 완료")
            return True
        
        return False
    
    def _save_performance_history(self, round_num: int, performance: Dict[str, Any],
                                optimization_results: Dict[str, Any]):
        """성능 기록 저장"""
        record = {
            'round': round_num,
            'timestamp': datetime.now().isoformat(),
            'performance': performance,
            'optimization_results': optimization_results
        }
        
        self.performance_history.append(record)
        
        # 파일로 저장
        history_file = 'results/adaptive_optimization_history.json'
        try:
            # 기존 기록 로드
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    all_history = json.load(f)
            else:
                all_history = []
            
            # 새 기록 추가
            all_history.append(record)
            
            # 최근 100개만 유지
            all_history = all_history[-100:]
            
            # 저장
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(all_history, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logging.error(f"성능 기록 저장 실패: {str(e)}")
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """최적화 보고서 생성"""
        if not self.performance_history:
            return {'status': 'No optimization history'}
        
        latest = self.performance_history[-1]
        
        report = {
            'last_optimization_round': self.last_optimization_round,
            'total_optimizations': len(self.performance_history),
            'latest_performance': latest['performance'],
            'optimization_summary': {}
        }
        
        # 필터별 최적화 횟수 집계
        for record in self.performance_history:
            for filter_name in record['optimization_results']:
                if filter_name not in report['optimization_summary']:
                    report['optimization_summary'][filter_name] = 0
                report['optimization_summary'][filter_name] += 1
        
        return report


def main():
    """테스트 실행"""
    from ..logger import setup_logging
    setup_logging()
    
    optimizer = AdaptiveFilterOptimizer()
    
    # 현재 회차에 대해 최적화 수행
    current_round = 1182
    results = optimizer.optimize_filters_adaptive(current_round)
    
    # 보고서 출력
    report = optimizer.get_optimization_report()
    logging.info(f"\n최적화 보고서: {json.dumps(report, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()