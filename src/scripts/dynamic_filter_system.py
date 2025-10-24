#!/usr/bin/env python3
"""
동적 필터 관리 시스템

필터의 성능을 실시간으로 모니터링하고
자동으로 기준값을 조정하는 적응형 시스템
"""

import json
import sys
import os
from typing import List, Dict, Tuple, Any, Optional
from collections import defaultdict, deque
import numpy as np
from datetime import datetime
from abc import ABC, abstractmethod

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager

class FilterPerformanceMonitor:
    """필터 성능 모니터링 클래스"""
    
    def __init__(self, window_size: int = 50):
        """
        Args:
            window_size: 성능 추적을 위한 윈도우 크기
        """
        self.window_size = window_size
        self.performance_history = defaultdict(lambda: {
            'pass_rates': deque(maxlen=window_size),
            'exclusion_rates': deque(maxlen=window_size),
            'false_negatives': deque(maxlen=window_size)
        })
        
    def update_performance(self, filter_name: str, pass_rate: float, 
                          exclusion_rate: float, false_negative: bool):
        """필터 성능 업데이트"""
        history = self.performance_history[filter_name]
        history['pass_rates'].append(pass_rate)
        history['exclusion_rates'].append(exclusion_rate)
        history['false_negatives'].append(1 if false_negative else 0)
    
    def get_performance_metrics(self, filter_name: str) -> Dict[str, float]:
        """필터 성능 메트릭 계산"""
        history = self.performance_history[filter_name]
        
        if not history['pass_rates']:
            return {
                'avg_pass_rate': 1.0,
                'avg_exclusion_rate': 0.0,
                'false_negative_rate': 0.0,
                'stability': 1.0
            }
        
        pass_rates = list(history['pass_rates'])
        exclusion_rates = list(history['exclusion_rates'])
        false_negatives = list(history['false_negatives'])
        
        return {
            'avg_pass_rate': np.mean(pass_rates),
            'avg_exclusion_rate': np.mean(exclusion_rates),
            'false_negative_rate': np.mean(false_negatives),
            'stability': 1 - np.std(pass_rates) if len(pass_rates) > 1 else 1.0
        }

class AdaptiveFilterStrategy(ABC):
    """적응형 필터 전략 기본 클래스"""
    
    @abstractmethod
    def adjust_criteria(self, current_criteria: Dict, performance_metrics: Dict) -> Dict:
        """필터 기준 조정"""
        pass

class ConservativeStrategy(AdaptiveFilterStrategy):
    """보수적 조정 전략"""
    
    def adjust_criteria(self, current_criteria: Dict, performance_metrics: Dict) -> Dict:
        """당첨번호 필터링을 최소화하는 방향으로 조정"""
        adjusted = current_criteria.copy()
        
        # 평균 통과율이 낮으면 기준 완화
        if performance_metrics['avg_pass_rate'] < 0.99:
            # 각 필터 타입별 조정 로직
            if 'max_match' in adjusted:
                adjusted['max_match'] = max(4, adjusted['max_match'] - 1)
            elif 'excluded_counts' in adjusted:
                # 홀짝 필터 등
                adjusted['excluded_counts'] = []  # 극단적인 경우만 제외
            elif 'max_consecutive' in adjusted:
                adjusted['max_consecutive'] = min(6, adjusted['max_consecutive'] + 1)
        
        return adjusted

class AggressiveStrategy(AdaptiveFilterStrategy):
    """공격적 조정 전략"""
    
    def adjust_criteria(self, current_criteria: Dict, performance_metrics: Dict) -> Dict:
        """제외율을 높이는 방향으로 조정"""
        adjusted = current_criteria.copy()
        
        # 제외율이 낮으면 기준 강화
        if performance_metrics['avg_exclusion_rate'] < 0.1:
            if 'max_match' in adjusted:
                adjusted['max_match'] = min(6, adjusted['max_match'] + 1)
            elif 'max_consecutive' in adjusted:
                adjusted['max_consecutive'] = max(2, adjusted['max_consecutive'] - 1)
        
        return adjusted

class BalancedStrategy(AdaptiveFilterStrategy):
    """균형잡힌 조정 전략"""
    
    def adjust_criteria(self, current_criteria: Dict, performance_metrics: Dict) -> Dict:
        """통과율과 제외율의 균형을 맞추는 방향으로 조정"""
        adjusted = current_criteria.copy()
        
        # 목표: 통과율 98% 이상, 제외율 5% 이상
        if performance_metrics['avg_pass_rate'] < 0.98:
            # 기준 완화
            self._relax_criteria(adjusted)
        elif performance_metrics['avg_exclusion_rate'] < 0.05:
            # 기준 강화
            self._tighten_criteria(adjusted)
        
        return adjusted
    
    def _relax_criteria(self, criteria: Dict):
        """기준 완화"""
        if 'max_match' in criteria:
            criteria['max_match'] = max(4, criteria['max_match'] - 1)
        # 다른 필터 타입별 완화 로직 추가
    
    def _tighten_criteria(self, criteria: Dict):
        """기준 강화"""
        if 'max_match' in criteria and criteria['max_match'] < 5:
            criteria['max_match'] = criteria['max_match'] + 1
        # 다른 필터 타입별 강화 로직 추가

class DynamicFilterManager:
    """동적 필터 관리 시스템"""
    
    def __init__(self, strategy: AdaptiveFilterStrategy = None):
        """
        Args:
            strategy: 적응형 전략 (기본값: BalancedStrategy)
        """
        self.db_manager = DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.monitor = FilterPerformanceMonitor()
        self.strategy = strategy or BalancedStrategy()
        self.enabled_filters = set(self.filter_manager.filters.keys())
        self.filter_scores = {}
        
    def evaluate_filter(self, filter_name: str, test_data: List[Dict]) -> Dict[str, float]:
        """필터 평가"""
        if filter_name not in self.filter_manager.filters:
            return {}
        
        filter_instance = self.filter_manager.filters[filter_name]
        
        total_tests = len(test_data)
        passed = 0
        
        for data in test_data:
            combination = ','.join(map(str, data['numbers']))
            try:
                result = filter_instance.apply([combination], data['round'])
                if result and len(result) > 0:
                    passed += 1
            except Exception as e:
                logging.error(f"동적 필터 실패: {e}")
        
        pass_rate = passed / total_tests if total_tests > 0 else 1.0
        
        # 제외율 계산 (샘플링)
        sample_size = min(10000, 8145060)
        sample_combinations = self._generate_sample_combinations(sample_size)
        
        try:
            filtered = filter_instance.apply(sample_combinations, test_data[-1]['round'])
            exclusion_rate = 1 - (len(filtered) / len(sample_combinations))
        except Exception as e:
            logging.error(f"시스템 실행 실패: {e}")
            exclusion_rate = 0.0
        
        return {
            'pass_rate': pass_rate,
            'exclusion_rate': exclusion_rate
        }
    
    def _generate_sample_combinations(self, size: int) -> List[str]:
        """샘플 조합 생성"""
        combinations = []
        for _ in range(size):
            numbers = sorted(np.random.choice(range(1, 46), 6, replace=False))
            combinations.append(','.join(map(str, numbers)))
        return combinations
    
    def update_filter_status(self, winning_data: List[Dict], lookback: int = 50):
        """필터 상태 업데이트"""
        recent_data = winning_data[-lookback:]
        
        print(f"\n최근 {lookback}회차 데이터로 필터 성능 평가 중...")
        
        for filter_name in self.filter_manager.filters.keys():
            metrics = self.evaluate_filter(filter_name, recent_data)
            
            if metrics:
                # 성능 기록 업데이트
                self.monitor.update_performance(
                    filter_name,
                    metrics['pass_rate'],
                    metrics['exclusion_rate'],
                    metrics['pass_rate'] < 1.0
                )
                
                # 성능 메트릭 계산
                performance = self.monitor.get_performance_metrics(filter_name)
                
                # 필터 점수 계산
                score = self._calculate_filter_score(performance)
                self.filter_scores[filter_name] = score
                
                print(f"{filter_name}: 점수 {score:.3f} "
                      f"(통과율 {performance['avg_pass_rate']*100:.1f}%, "
                      f"제외율 {performance['avg_exclusion_rate']*100:.1f}%)")
    
    def _calculate_filter_score(self, performance: Dict[str, float]) -> float:
        """필터 점수 계산"""
        # 가중치
        w_pass = 0.4      # 통과율 (높을수록 좋음)
        w_exclusion = 0.3  # 제외율 (적당해야 함)
        w_stability = 0.2  # 안정성 (높을수록 좋음)
        w_fnr = 0.1       # 거짓 음성률 (낮을수록 좋음)
        
        # 통과율 점수 (0.95 이상이면 만점)
        pass_score = min(performance['avg_pass_rate'] / 0.95, 1.0)
        
        # 제외율 점수 (0.05~0.15가 이상적)
        if performance['avg_exclusion_rate'] < 0.05:
            exclusion_score = performance['avg_exclusion_rate'] / 0.05
        elif performance['avg_exclusion_rate'] > 0.15:
            exclusion_score = max(0, 1 - (performance['avg_exclusion_rate'] - 0.15) / 0.15)
        else:
            exclusion_score = 1.0
        
        # 안정성 점수
        stability_score = performance['stability']
        
        # 거짓 음성률 점수
        fnr_score = 1 - performance['false_negative_rate']
        
        # 종합 점수
        total_score = (w_pass * pass_score + 
                      w_exclusion * exclusion_score + 
                      w_stability * stability_score + 
                      w_fnr * fnr_score)
        
        return total_score
    
    def auto_enable_disable_filters(self, threshold: float = 0.5):
        """필터 자동 활성화/비활성화"""
        changes = []
        
        for filter_name, score in self.filter_scores.items():
            if score < threshold and filter_name in self.enabled_filters:
                self.enabled_filters.remove(filter_name)
                changes.append(f"비활성화: {filter_name} (점수 {score:.3f})")
            elif score >= threshold and filter_name not in self.enabled_filters:
                self.enabled_filters.add(filter_name)
                changes.append(f"활성화: {filter_name} (점수 {score:.3f})")
        
        if changes:
            print("\n필터 상태 변경:")
            for change in changes:
                print(f"  - {change}")
        
        return changes
    
    def adjust_filter_criteria(self):
        """필터 기준값 자동 조정"""
        adjustments = []
        
        for filter_name in self.enabled_filters:
            filter_instance = self.filter_manager.filters.get(filter_name)
            if not filter_instance:
                continue
            
            # 현재 기준값
            current_criteria = filter_instance.get_criteria() if hasattr(filter_instance, 'get_criteria') else {}
            
            # 성능 메트릭
            performance = self.monitor.get_performance_metrics(filter_name)
            
            # 전략에 따라 기준 조정
            adjusted_criteria = self.strategy.adjust_criteria(current_criteria, performance)
            
            # 변경사항이 있으면 적용
            if adjusted_criteria != current_criteria:
                adjustments.append({
                    'filter': filter_name,
                    'before': current_criteria,
                    'after': adjusted_criteria
                })
                
                # 실제 적용 (filter_instance에 setter가 있다고 가정)
                if hasattr(filter_instance, 'set_criteria'):
                    filter_instance.set_criteria(adjusted_criteria)
        
        return adjustments
    
    def generate_report(self) -> Dict[str, Any]:
        """동적 관리 시스템 보고서 생성"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'enabled_filters': list(self.enabled_filters),
            'filter_scores': self.filter_scores,
            'performance_metrics': {},
            'recommendations': []
        }
        
        # 각 필터의 성능 메트릭
        for filter_name in self.filter_manager.filters.keys():
            metrics = self.monitor.get_performance_metrics(filter_name)
            report['performance_metrics'][filter_name] = metrics
        
        # 권장사항 생성
        sorted_filters = sorted(self.filter_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 최고 성능 필터
        if sorted_filters:
            best_filters = [f for f, s in sorted_filters[:5]]
            report['recommendations'].append({
                'type': 'best_performers',
                'filters': best_filters,
                'message': '현재 가장 효과적인 필터들입니다.'
            })
        
        # 개선이 필요한 필터
        poor_filters = [f for f, s in sorted_filters if s < 0.5]
        if poor_filters:
            report['recommendations'].append({
                'type': 'needs_improvement',
                'filters': poor_filters,
                'message': '기준 조정이나 비활성화를 고려해야 할 필터들입니다.'
            })
        
        return report

def main():
    """메인 분석 함수"""
    print("="*80)
    print("동적 필터 관리 시스템")
    print("="*80)
    
    # 데이터 로드
    with open('winning_numbers.json', 'r', encoding='utf-8') as f:
        winning_data = json.load(f)
    
    print(f"총 {len(winning_data)}개 회차 데이터 로드")
    
    # 전략 선택
    print("\n전략 선택:")
    print("1. Conservative (보수적) - 당첨번호 통과 우선")
    print("2. Aggressive (공격적) - 제외율 최대화")
    print("3. Balanced (균형) - 통과율과 제외율 균형")
    
    # 기본값: Balanced
    strategy = BalancedStrategy()
    print("\n균형잡힌 전략으로 진행합니다.")
    
    # 동적 필터 관리자 초기화
    manager = DynamicFilterManager(strategy)
    
    # 1. 필터 성능 평가
    print("\n" + "="*60)
    print("1. 필터 성능 평가")
    print("="*60)
    
    manager.update_filter_status(winning_data, lookback=100)
    
    # 2. 필터 자동 활성화/비활성화
    print("\n" + "="*60)
    print("2. 필터 자동 관리")
    print("="*60)
    
    changes = manager.auto_enable_disable_filters(threshold=0.6)
    
    if not changes:
        print("필터 상태 변경 없음")
    
    # 3. 필터 기준값 조정
    print("\n" + "="*60)
    print("3. 필터 기준값 자동 조정")
    print("="*60)
    
    adjustments = manager.adjust_filter_criteria()
    
    if adjustments:
        print("\n조정된 필터 기준:")
        for adj in adjustments:
            print(f"\n{adj['filter']}:")
            print(f"  변경 전: {adj['before']}")
            print(f"  변경 후: {adj['after']}")
    else:
        print("기준값 조정 없음")
    
    # 4. 최종 보고서 생성
    print("\n" + "="*60)
    print("4. 동적 관리 시스템 보고서")
    print("="*60)
    
    report = manager.generate_report()
    
    # 활성 필터
    print(f"\n활성 필터 ({len(report['enabled_filters'])}개):")
    for filter_name in report['enabled_filters']:
        score = report['filter_scores'].get(filter_name, 0)
        print(f"  - {filter_name}: 점수 {score:.3f}")
    
    # 권장사항
    print("\n권장사항:")
    for rec in report['recommendations']:
        print(f"\n[{rec['type']}]")
        print(f"{rec['message']}")
        for filter_name in rec['filters']:
            print(f"  - {filter_name}")
    
    # 보고서 저장
    with open('analyze_system/dynamic_filter_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print("\n✅ 분석 결과가 analyze_system/dynamic_filter_report.json에 저장되었습니다.")

if __name__ == "__main__":
    main()