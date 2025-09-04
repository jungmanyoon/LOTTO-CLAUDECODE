"""
필터 간 상관관계 분석 스크립트
- 필터 간 중복성 분석
- 효율적인 필터 조합 추천
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import time
import random
from typing import Dict, List, Tuple, Set
from collections import defaultdict
import numpy as np

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.core.parallel_filter_manager import ParallelFilterManager
from src.filters.base_filter import BaseFilter
import yaml

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_sample_combinations(num_samples: int = 10000) -> List[str]:
    """테스트용 샘플 조합 생성"""
    combinations = set()
    while len(combinations) < num_samples:
        numbers = sorted(random.sample(range(1, 46), 6))
        combo_str = ','.join(map(str, numbers))
        combinations.add(combo_str)
    return list(combinations)

def analyze_filter_correlation(filter_manager: FilterManager, enabled_filters: List[str]) -> Dict[str, Dict[str, float]]:
    """필터 간 상관관계 분석"""
    logging.info("필터 간 상관관계 분석 시작...")
    
    # 샘플 조합 생성
    sample_combinations = get_sample_combinations(10000)
    total_samples = len(sample_combinations)
    
    # 각 필터별 제외 조합 저장
    filter_exclusions = {}
    
    # 각 필터 개별 적용
    for filter_name, filter_instance in filter_manager.filters.items():
        if filter_name not in enabled_filters:
            continue
            
        logging.info(f"{filter_name} 필터 분석 중...")
        
        # 필터 적용
        remaining = filter_instance.apply(sample_combinations, 0)
        excluded = set(sample_combinations) - set(remaining)
        filter_exclusions[filter_name] = excluded
        
        logging.info(f"- {filter_name}: {len(excluded)}개 제외 ({len(excluded)/total_samples*100:.2f}%)")
    
    # 필터 간 상관관계 계산
    correlation_matrix = {}
    
    for filter1 in filter_exclusions:
        correlation_matrix[filter1] = {}
        
        for filter2 in filter_exclusions:
            if filter1 == filter2:
                correlation_matrix[filter1][filter2] = 1.0
                continue
            
            # 두 필터의 제외 조합 교집합
            intersection = filter_exclusions[filter1] & filter_exclusions[filter2]
            union = filter_exclusions[filter1] | filter_exclusions[filter2]
            
            # Jaccard 계수 계산 (교집합 / 합집합)
            if len(union) > 0:
                jaccard = len(intersection) / len(union)
            else:
                jaccard = 0.0
            
            # 중복도 계산 (filter1이 제외한 것 중 filter2도 제외한 비율)
            if len(filter_exclusions[filter1]) > 0:
                overlap_ratio = len(intersection) / len(filter_exclusions[filter1])
            else:
                overlap_ratio = 0.0
            
            # 상관계수는 두 지표의 평균
            correlation = (jaccard + overlap_ratio) / 2
            correlation_matrix[filter1][filter2] = correlation
    
    return correlation_matrix

def find_redundant_filters(correlation_matrix: Dict[str, Dict[str, float]], 
                          threshold: float = 0.7) -> List[Tuple[str, str, float]]:
    """중복도가 높은 필터 쌍 찾기"""
    redundant_pairs = []
    
    checked_pairs = set()
    
    for filter1, correlations in correlation_matrix.items():
        for filter2, correlation in correlations.items():
            if filter1 == filter2:
                continue
            
            # 이미 확인한 쌍은 건너뛰기
            pair = tuple(sorted([filter1, filter2]))
            if pair in checked_pairs:
                continue
            
            checked_pairs.add(pair)
            
            # 상관계수가 임계값 이상인 경우
            if correlation >= threshold:
                redundant_pairs.append((filter1, filter2, correlation))
    
    # 상관계수 높은 순으로 정렬
    redundant_pairs.sort(key=lambda x: x[2], reverse=True)
    
    return redundant_pairs

def analyze_filter_combinations(filter_manager: FilterManager) -> Dict[str, Dict]:
    """효율적인 필터 조합 분석"""
    logging.info("\n효율적인 필터 조합 분석 시작...")
    
    # 샘플 조합
    sample_combinations = get_sample_combinations(5000)
    initial_count = len(sample_combinations)
    
    # 필터 그룹별 분석
    filter_groups = {
        'mathematical': ['arithmetic_sequence', 'geometric_sequence', 'fixed_step', 'consecutive'],
        'statistical': ['sum_range', 'average', 'dispersion', 'max_gap'],
        'distribution': ['section', 'ten_section', 'odd_even', 'last_digit'],
        'pattern': ['prime_composite', 'multiple', 'digit_sum'],
        'historical': ['match']
    }
    
    group_results = {}
    
    for group_name, filter_names in filter_groups.items():
        logging.info(f"\n{group_name} 그룹 분석:")
        
        # 그룹 내 필터들만 적용
        remaining = sample_combinations.copy()
        filter_effects = []
        
        for filter_name in filter_names:
            if filter_name not in filter_manager.filters:
                continue
            
            filter_instance = filter_manager.filters[filter_name]
            before_count = len(remaining)
            remaining = filter_instance.apply(remaining, 0)
            after_count = len(remaining)
            
            effect = (before_count - after_count) / before_count * 100 if before_count > 0 else 0
            filter_effects.append((filter_name, effect))
            
            logging.info(f"  - {filter_name}: {effect:.2f}% 제외")
        
        group_effect = (initial_count - len(remaining)) / initial_count * 100
        
        group_results[group_name] = {
            'total_effect': group_effect,
            'remaining_count': len(remaining),
            'filter_effects': filter_effects
        }
        
        logging.info(f"  그룹 전체 효과: {group_effect:.2f}% 제외")
    
    return group_results

def recommend_filter_optimization(correlation_matrix: Dict[str, Dict[str, float]], 
                                 filter_efficiency: Dict[str, float]) -> List[Dict]:
    """필터 최적화 추천"""
    recommendations = []
    
    # 1. 중복도 높은 필터 확인
    redundant_filters = find_redundant_filters(correlation_matrix, threshold=0.6)
    
    for filter1, filter2, correlation in redundant_filters[:5]:  # 상위 5개
        eff1 = filter_efficiency.get(filter1, 0)
        eff2 = filter_efficiency.get(filter2, 0)
        
        if eff1 > eff2:
            keep, remove = filter1, filter2
        else:
            keep, remove = filter2, filter1
        
        recommendations.append({
            'type': 'redundancy',
            'message': f"{filter1}와 {filter2}의 중복도가 {correlation:.2%}입니다.",
            'action': f"{keep} 필터만 유지하고 {remove} 필터는 비활성화 고려",
            'priority': 'medium' if correlation < 0.8 else 'high'
        })
    
    # 2. 효율성 낮은 필터 확인
    low_efficiency_filters = [
        (name, eff) for name, eff in filter_efficiency.items() 
        if eff < 0.05 and name in correlation_matrix
    ]
    
    for filter_name, efficiency in low_efficiency_filters:
        recommendations.append({
            'type': 'low_efficiency',
            'message': f"{filter_name} 필터의 효율성이 {efficiency:.2%}로 매우 낮습니다.",
            'action': f"{filter_name} 필터의 기준 완화 또는 비활성화 고려",
            'priority': 'low'
        })
    
    # 3. 독립적이면서 효율적인 필터 추천
    independent_filters = []
    for filter_name in correlation_matrix:
        avg_correlation = np.mean([
            corr for other, corr in correlation_matrix[filter_name].items() 
            if other != filter_name
        ])
        if avg_correlation < 0.3 and filter_efficiency.get(filter_name, 0) > 0.1:
            independent_filters.append((filter_name, avg_correlation))
    
    if independent_filters:
        independent_filters.sort(key=lambda x: x[1])
        top_independent = [name for name, _ in independent_filters[:3]]
        
        recommendations.append({
            'type': 'independent',
            'message': "독립적이면서 효율적인 필터들입니다.",
            'action': f"우선 적용 추천: {', '.join(top_independent)}",
            'priority': 'high'
        })
    
    return recommendations

def main():
    """메인 실행 함수"""
    try:
        # 설정 로드
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        # 간단한 config 객체 생성
        class Config:
            def __init__(self, data):
                self.data = data
                self.filtering = type('obj', (object,), {'use_parallel': data.get('filtering', {}).get('use_parallel', False)})
        
        config = Config(config_dict)
        
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 필터 매니저 초기화
        if config.filtering.use_parallel:
            filter_manager = ParallelFilterManager(db_manager)
        else:
            filter_manager = FilterManager(db_manager)
        
        # 필터가 이미 등록되어 있으므로 생략
        
        # enabled_filters 가져오기
        enabled_filters = config_dict.get('filters', {}).get('enabled_filters', [])
        
        print("\n" + "="*60)
        print("필터 상관관계 분석 시스템")
        print("="*60)
        
        # 1. 필터 간 상관관계 분석
        correlation_matrix = analyze_filter_correlation(filter_manager, enabled_filters)
        
        # 2. 중복도 높은 필터 출력
        print("\n[중복도 높은 필터 쌍]")
        redundant_filters = find_redundant_filters(correlation_matrix, threshold=0.5)
        
        for filter1, filter2, correlation in redundant_filters[:10]:
            print(f"- {filter1} ↔ {filter2}: {correlation:.2%} 중복")
        
        # 3. 필터 조합 분석
        combination_results = analyze_filter_combinations(filter_manager)
        
        print("\n[필터 그룹별 효과]")
        for group_name, results in combination_results.items():
            print(f"\n{group_name} 그룹:")
            print(f"  전체 효과: {results['total_effect']:.2f}% 제외")
            print(f"  남은 조합: {results['remaining_count']:,}개")
        
        # 4. 최적화 추천
        print("\n[필터 최적화 추천사항]")
        # filter_efficiency 가져오기
        filter_efficiency = config_dict.get('filters', {}).get('filter_efficiency', {})
        recommendations = recommend_filter_optimization(
            correlation_matrix, 
            filter_efficiency
        )
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. [{rec['priority'].upper()}] {rec['type']}")
            print(f"   {rec['message']}")
            print(f"   → {rec['action']}")
        
        # 5. 상관관계 매트릭스 상위 출력
        print("\n[필터 간 평균 상관도]")
        avg_correlations = {}
        
        for filter_name in correlation_matrix:
            avg_corr = np.mean([
                corr for other, corr in correlation_matrix[filter_name].items() 
                if other != filter_name
            ])
            avg_correlations[filter_name] = avg_corr
        
        sorted_correlations = sorted(avg_correlations.items(), key=lambda x: x[1], reverse=True)
        
        for filter_name, avg_corr in sorted_correlations:
            status = "높음" if avg_corr > 0.5 else "보통" if avg_corr > 0.3 else "낮음"
            print(f"- {filter_name}: {avg_corr:.2%} ({status})")
        
        print("\n분석 완료!")
        
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    main()