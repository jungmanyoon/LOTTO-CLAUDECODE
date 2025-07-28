#!/usr/bin/env python3
"""
개선된 백테스팅 방법론 구현

롤링 윈도우 방식과 시계열 분할을 사용하여
실제 예측 환경을 시뮬레이션합니다.
"""

import json
import sys
import os
from typing import List, Dict, Tuple, Any
from collections import defaultdict
import numpy as np
from datetime import datetime
from tqdm import tqdm

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager

class ImprovedBacktesting:
    def __init__(self, window_size: int = 100, test_size: int = 10):
        """
        Args:
            window_size: 학습에 사용할 과거 데이터 크기
            test_size: 테스트할 미래 데이터 크기
        """
        self.window_size = window_size
        self.test_size = test_size
        self.db_manager = DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        
    def rolling_window_test(self, winning_data: List[Dict], start_round: int = 200) -> Dict[str, Any]:
        """
        롤링 윈도우 백테스팅
        
        Args:
            winning_data: 전체 당첨번호 데이터
            start_round: 백테스팅 시작 회차
            
        Returns:
            Dict: 백테스팅 결과
        """
        results = defaultdict(lambda: {
            'total_tests': 0,
            'filtered_count': 0,
            'pass_count': 0,
            'filtered_rounds': []
        })
        
        # 시작 회차부터 끝까지 롤링
        total_rounds = len(winning_data)
        
        print(f"\n롤링 윈도우 백테스팅 시작 (window={self.window_size}, test={self.test_size})")
        
        with tqdm(total=(total_rounds - start_round) // self.test_size, desc="백테스팅 진행") as pbar:
            for current_round in range(start_round, total_rounds - self.test_size, self.test_size):
                # 학습 데이터: current_round-window_size ~ current_round
                train_start = max(1, current_round - self.window_size)
                train_data = [d for d in winning_data if train_start <= d['round'] <= current_round]
                
                # 테스트 데이터: current_round+1 ~ current_round+test_size
                test_data = [d for d in winning_data if current_round < d['round'] <= current_round + self.test_size]
                
                if len(test_data) == 0:
                    break
                
                # 각 필터에 대해 테스트
                for filter_name, filter_instance in self.filter_manager.filters.items():
                    # 필터 기준을 학습 데이터로 업데이트 (가능한 경우)
                    if hasattr(filter_instance, 'update_criteria'):
                        filter_instance.update_criteria(train_data)
                    
                    # 테스트 데이터에 필터 적용
                    for test_case in test_data:
                        combination = ','.join(map(str, test_case['numbers']))
                        
                        try:
                            result = filter_instance.apply([combination], test_case['round'])
                            
                            results[filter_name]['total_tests'] += 1
                            
                            if not result or len(result) == 0:
                                # 필터링됨
                                results[filter_name]['filtered_count'] += 1
                                results[filter_name]['filtered_rounds'].append(test_case['round'])
                            else:
                                # 통과
                                results[filter_name]['pass_count'] += 1
                        except Exception as e:
                            pass
                
                pbar.update(1)
        
        # 결과 계산
        final_results = {}
        for filter_name, data in results.items():
            total = data['total_tests']
            if total > 0:
                final_results[filter_name] = {
                    'total_tests': total,
                    'filtered_count': data['filtered_count'],
                    'pass_count': data['pass_count'],
                    'pass_rate': data['pass_count'] / total,
                    'precision': 1.0,  # 필터링한 것 중 실제 비당첨 비율 (로또는 항상 1.0)
                    'sample_filtered_rounds': data['filtered_rounds'][:10]
                }
        
        return final_results
    
    def walk_forward_analysis(self, winning_data: List[Dict], 
                            train_period: int = 200,
                            test_period: int = 50) -> Dict[str, Any]:
        """
        Walk-forward 분석
        
        Args:
            winning_data: 전체 당첨번호 데이터
            train_period: 학습 기간
            test_period: 테스트 기간
            
        Returns:
            Dict: 분석 결과
        """
        walk_forward_results = []
        
        total_rounds = len(winning_data)
        current_position = train_period
        
        print(f"\nWalk-forward 분석 시작 (train={train_period}, test={test_period})")
        
        while current_position + test_period <= total_rounds:
            # 현재 구간 설정
            train_start = current_position - train_period
            train_end = current_position
            test_start = current_position
            test_end = current_position + test_period
            
            train_data = [d for d in winning_data if train_start < d['round'] <= train_end]
            test_data = [d for d in winning_data if test_start < d['round'] <= test_end]
            
            # 각 필터 성능 평가
            period_results = {
                'period': f"{train_start}-{train_end} → {test_start}-{test_end}",
                'filters': {}
            }
            
            for filter_name, filter_instance in self.filter_manager.filters.items():
                filtered_count = 0
                
                for test_case in test_data:
                    combination = ','.join(map(str, test_case['numbers']))
                    
                    try:
                        result = filter_instance.apply([combination], test_case['round'])
                        if not result or len(result) == 0:
                            filtered_count += 1
                    except:
                        pass
                
                pass_rate = (len(test_data) - filtered_count) / len(test_data) if len(test_data) > 0 else 1.0
                period_results['filters'][filter_name] = {
                    'pass_rate': pass_rate,
                    'filtered_count': filtered_count
                }
            
            walk_forward_results.append(period_results)
            current_position += test_period
        
        # 결과 집계
        aggregated_results = self._aggregate_walk_forward_results(walk_forward_results)
        
        return {
            'detailed_results': walk_forward_results,
            'aggregated_results': aggregated_results
        }
    
    def _aggregate_walk_forward_results(self, walk_forward_results: List[Dict]) -> Dict[str, Any]:
        """Walk-forward 결과 집계"""
        filter_stats = defaultdict(list)
        
        for period_result in walk_forward_results:
            for filter_name, stats in period_result['filters'].items():
                filter_stats[filter_name].append(stats['pass_rate'])
        
        aggregated = {}
        for filter_name, pass_rates in filter_stats.items():
            aggregated[filter_name] = {
                'mean_pass_rate': np.mean(pass_rates),
                'std_pass_rate': np.std(pass_rates),
                'min_pass_rate': np.min(pass_rates),
                'max_pass_rate': np.max(pass_rates),
                'consistency_score': 1 - np.std(pass_rates)  # 일관성 점수
            }
        
        return aggregated
    
    def filter_stability_analysis(self, winning_data: List[Dict]) -> Dict[str, Any]:
        """
        필터 안정성 분석
        시간에 따른 필터 성능 변화 추적
        """
        # 데이터를 4개 구간으로 분할
        quarter_size = len(winning_data) // 4
        quarters = [
            winning_data[i:i+quarter_size] 
            for i in range(0, len(winning_data), quarter_size)
        ]
        
        stability_results = defaultdict(list)
        
        print("\n필터 안정성 분석 중...")
        
        for i, quarter_data in enumerate(quarters):
            print(f"  - {i+1}/4 분기 분석 중...")
            
            for filter_name, filter_instance in self.filter_manager.filters.items():
                filtered_count = 0
                
                for data in quarter_data:
                    combination = ','.join(map(str, data['numbers']))
                    
                    try:
                        result = filter_instance.apply([combination], data['round'])
                        if not result or len(result) == 0:
                            filtered_count += 1
                    except:
                        pass
                
                pass_rate = (len(quarter_data) - filtered_count) / len(quarter_data)
                stability_results[filter_name].append(pass_rate)
        
        # 안정성 메트릭 계산
        final_stability = {}
        for filter_name, quarterly_rates in stability_results.items():
            # 변동성 계산
            volatility = np.std(quarterly_rates)
            # 추세 계산 (선형 회귀)
            x = np.arange(len(quarterly_rates))
            trend = np.polyfit(x, quarterly_rates, 1)[0]
            
            final_stability[filter_name] = {
                'quarterly_pass_rates': quarterly_rates,
                'volatility': volatility,
                'trend': trend,  # 양수면 개선, 음수면 악화
                'stability_score': 1 - volatility  # 0~1, 높을수록 안정적
            }
        
        return final_stability

def main():
    """메인 분석 함수"""
    print("="*80)
    print("개선된 백테스팅 분석")
    print("="*80)
    
    # 데이터 로드
    with open('winning_numbers.json', 'r', encoding='utf-8') as f:
        winning_data = json.load(f)
    
    print(f"총 {len(winning_data)}개 회차 데이터 로드")
    
    # 백테스팅 인스턴스 생성
    backtester = ImprovedBacktesting(window_size=100, test_size=10)
    
    # 1. 롤링 윈도우 테스트
    print("\n" + "="*60)
    print("1. 롤링 윈도우 백테스팅")
    print("="*60)
    
    rolling_results = backtester.rolling_window_test(winning_data, start_round=200)
    
    # 결과 출력
    print("\n[롤링 윈도우 결과]")
    sorted_filters = sorted(
        rolling_results.items(),
        key=lambda x: x[1]['pass_rate'],
        reverse=True
    )
    
    for filter_name, stats in sorted_filters[:10]:
        print(f"{filter_name:25s}: 통과율 {stats['pass_rate']*100:6.2f}%, "
              f"필터링 {stats['filtered_count']:4d}/{stats['total_tests']:4d}회")
    
    # 2. Walk-forward 분석
    print("\n" + "="*60)
    print("2. Walk-forward 분석")
    print("="*60)
    
    walk_forward_results = backtester.walk_forward_analysis(winning_data)
    
    print("\n[Walk-forward 집계 결과]")
    sorted_wf = sorted(
        walk_forward_results['aggregated_results'].items(),
        key=lambda x: x[1]['consistency_score'],
        reverse=True
    )
    
    for filter_name, stats in sorted_wf[:10]:
        print(f"{filter_name:25s}: 평균 통과율 {stats['mean_pass_rate']*100:6.2f}% "
              f"(±{stats['std_pass_rate']*100:4.2f}%), "
              f"일관성 {stats['consistency_score']:.3f}")
    
    # 3. 안정성 분석
    print("\n" + "="*60)
    print("3. 필터 안정성 분석")
    print("="*60)
    
    stability_results = backtester.filter_stability_analysis(winning_data)
    
    print("\n[안정성 분석 결과]")
    sorted_stability = sorted(
        stability_results.items(),
        key=lambda x: x[1]['stability_score'],
        reverse=True
    )
    
    for filter_name, stats in sorted_stability[:10]:
        trend_str = "개선중" if stats['trend'] > 0 else "악화중"
        print(f"{filter_name:25s}: 안정성 {stats['stability_score']:.3f}, "
              f"변동성 {stats['volatility']:.4f}, 추세 {trend_str}")
        quarterly = stats['quarterly_pass_rates']
        print(f"  분기별 통과율: " + 
              " → ".join([f"{rate*100:.1f}%" for rate in quarterly]))
    
    # 종합 평가
    print("\n" + "="*60)
    print("4. 종합 평가")
    print("="*60)
    
    # 각 필터의 종합 점수 계산
    filter_scores = {}
    
    for filter_name in backtester.filter_manager.filters.keys():
        if filter_name in rolling_results and filter_name in stability_results:
            # 롤링 윈도우 통과율 (40%)
            rolling_score = rolling_results[filter_name]['pass_rate'] * 0.4
            
            # Walk-forward 일관성 (30%)
            wf_score = walk_forward_results['aggregated_results'][filter_name]['consistency_score'] * 0.3
            
            # 안정성 점수 (30%)
            stability_score = stability_results[filter_name]['stability_score'] * 0.3
            
            filter_scores[filter_name] = {
                'total_score': rolling_score + wf_score + stability_score,
                'rolling_pass_rate': rolling_results[filter_name]['pass_rate'],
                'consistency': walk_forward_results['aggregated_results'][filter_name]['consistency_score'],
                'stability': stability_results[filter_name]['stability_score']
            }
    
    # 종합 순위
    print("\n[종합 필터 순위]")
    sorted_scores = sorted(
        filter_scores.items(),
        key=lambda x: x[1]['total_score'],
        reverse=True
    )
    
    for i, (filter_name, scores) in enumerate(sorted_scores, 1):
        print(f"{i:2d}. {filter_name:25s}: 종합점수 {scores['total_score']:.3f}")
        print(f"    - 통과율: {scores['rolling_pass_rate']*100:.2f}%")
        print(f"    - 일관성: {scores['consistency']:.3f}")
        print(f"    - 안정성: {scores['stability']:.3f}")
    
    # 결과 저장
    final_results = {
        'analysis_date': datetime.now().isoformat(),
        'rolling_window_results': rolling_results,
        'walk_forward_results': walk_forward_results,
        'stability_results': stability_results,
        'comprehensive_scores': filter_scores,
        'recommendations': {
            'best_filters': [name for name, _ in sorted_scores[:5]],
            'worst_filters': [name for name, _ in sorted_scores[-5:]],
            'most_stable': [name for name, _ in sorted_stability[:3]],
            'most_consistent': [name for name, _ in sorted_wf[:3]]
        }
    }
    
    with open('analyze_system/improved_backtesting_result.json', 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ 분석 결과가 analyze_system/improved_backtesting_result.json에 저장되었습니다.")

if __name__ == "__main__":
    main()