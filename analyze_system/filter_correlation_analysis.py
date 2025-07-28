#!/usr/bin/env python3
"""
필터 간 상관관계 분석

각 필터가 제외하는 조합들의 중복도를 분석하여
필터 간 독립성과 상호작용을 파악합니다.
"""

import json
import sys
import os
from typing import List, Dict, Tuple, Set, Any
from collections import defaultdict
import numpy as np
import pandas as pd
from tqdm import tqdm
from itertools import combinations as iter_combinations
import matplotlib.pyplot as plt
import seaborn as sns

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager

class FilterCorrelationAnalyzer:
    def __init__(self, sample_size: int = 100000):
        """
        Args:
            sample_size: 분석에 사용할 샘플 크기
        """
        self.sample_size = sample_size
        self.db_manager = DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        
    def generate_sample_combinations(self) -> List[str]:
        """샘플 조합 생성"""
        from itertools import combinations
        
        all_combinations = []
        # 전체 조합 중 무작위 샘플링
        all_numbers = list(range(1, 46))
        
        print(f"샘플 조합 {self.sample_size:,}개 생성 중...")
        
        # 전체 조합 수가 너무 많으므로 무작위 샘플링
        sampled_combinations = set()
        while len(sampled_combinations) < self.sample_size:
            # 무작위로 6개 숫자 선택
            selected = sorted(np.random.choice(all_numbers, 6, replace=False))
            combination = ','.join(map(str, selected))
            sampled_combinations.add(combination)
        
        return list(sampled_combinations)
    
    def analyze_filter_exclusions(self, combinations: List[str]) -> Dict[str, Set[int]]:
        """
        각 필터가 제외하는 조합의 인덱스 집합 반환
        
        Returns:
            Dict[filter_name, Set[excluded_indices]]
        """
        filter_exclusions = {}
        
        print("\n각 필터의 제외 패턴 분석 중...")
        
        for filter_name, filter_instance in tqdm(self.filter_manager.filters.items()):
            try:
                # 필터 적용
                filtered = filter_instance.apply(combinations, 1000)
                
                # 제외된 조합의 인덱스 찾기
                filtered_set = set(filtered) if filtered else set()
                excluded_indices = set()
                
                for i, combo in enumerate(combinations):
                    if combo not in filtered_set:
                        excluded_indices.add(i)
                
                filter_exclusions[filter_name] = excluded_indices
                
                print(f"{filter_name}: {len(excluded_indices):,}개 제외 "
                      f"({len(excluded_indices)/len(combinations)*100:.2f}%)")
                
            except Exception as e:
                print(f"{filter_name} 필터 분석 중 오류: {str(e)}")
                filter_exclusions[filter_name] = set()
        
        return filter_exclusions
    
    def calculate_correlation_matrix(self, filter_exclusions: Dict[str, Set[int]]) -> pd.DataFrame:
        """
        필터 간 상관관계 매트릭스 계산
        
        Jaccard 유사도 기반
        """
        filter_names = list(filter_exclusions.keys())
        n_filters = len(filter_names)
        
        # 상관관계 매트릭스 초기화
        correlation_matrix = np.zeros((n_filters, n_filters))
        
        print("\n필터 간 상관관계 계산 중...")
        
        for i, filter1 in enumerate(filter_names):
            for j, filter2 in enumerate(filter_names):
                if i == j:
                    correlation_matrix[i, j] = 1.0
                else:
                    set1 = filter_exclusions[filter1]
                    set2 = filter_exclusions[filter2]
                    
                    # Jaccard 유사도 계산
                    if len(set1) > 0 or len(set2) > 0:
                        intersection = len(set1 & set2)
                        union = len(set1 | set2)
                        jaccard = intersection / union if union > 0 else 0
                        correlation_matrix[i, j] = jaccard
                    else:
                        correlation_matrix[i, j] = 0
        
        # DataFrame으로 변환
        df_correlation = pd.DataFrame(
            correlation_matrix,
            index=filter_names,
            columns=filter_names
        )
        
        return df_correlation
    
    def analyze_filter_combinations(self, filter_exclusions: Dict[str, Set[int]], 
                                  max_combination_size: int = 3) -> Dict[str, Any]:
        """
        필터 조합의 효과 분석
        """
        combination_results = {}
        total_samples = len(next(iter(filter_exclusions.values())))
        
        print(f"\n필터 조합 효과 분석 (최대 {max_combination_size}개 조합)")
        
        for combo_size in range(2, max_combination_size + 1):
            print(f"\n{combo_size}개 필터 조합 분석 중...")
            
            for filter_combo in iter_combinations(filter_exclusions.keys(), combo_size):
                # 각 필터의 제외 집합
                individual_exclusions = [filter_exclusions[f] for f in filter_combo]
                
                # 합집합 (OR 연산)
                union_exclusions = set.union(*individual_exclusions)
                
                # 교집합 (AND 연산)
                intersection_exclusions = set.intersection(*individual_exclusions)
                
                # 중복도 계산
                total_individual = sum(len(s) for s in individual_exclusions)
                overlap_ratio = 1 - (len(union_exclusions) / total_individual) if total_individual > 0 else 0
                
                combination_results[filter_combo] = {
                    'union_exclusion_count': len(union_exclusions),
                    'union_exclusion_rate': len(union_exclusions) / total_samples,
                    'intersection_exclusion_count': len(intersection_exclusions),
                    'intersection_exclusion_rate': len(intersection_exclusions) / total_samples,
                    'overlap_ratio': overlap_ratio,
                    'synergy_score': len(union_exclusions) / total_individual if total_individual > 0 else 0
                }
        
        return combination_results
    
    def find_optimal_filter_set(self, filter_exclusions: Dict[str, Set[int]], 
                               target_exclusion_rate: float = 0.95) -> List[str]:
        """
        목표 제외율을 달성하는 최적 필터 세트 찾기
        """
        print(f"\n목표 제외율 {target_exclusion_rate*100:.1f}%를 달성하는 최적 필터 조합 탐색 중...")
        
        total_samples = self.sample_size
        selected_filters = []
        current_exclusions = set()
        
        # 그리디 알고리즘으로 최적 조합 찾기
        remaining_filters = list(filter_exclusions.keys())
        
        while len(current_exclusions) / total_samples < target_exclusion_rate and remaining_filters:
            best_filter = None
            best_new_exclusions = 0
            
            # 가장 많은 새로운 제외를 추가하는 필터 찾기
            for filter_name in remaining_filters:
                new_exclusions = len(filter_exclusions[filter_name] - current_exclusions)
                
                if new_exclusions > best_new_exclusions:
                    best_new_exclusions = new_exclusions
                    best_filter = filter_name
            
            if best_filter:
                selected_filters.append(best_filter)
                current_exclusions.update(filter_exclusions[best_filter])
                remaining_filters.remove(best_filter)
                
                current_rate = len(current_exclusions) / total_samples
                print(f"  + {best_filter}: 누적 제외율 {current_rate*100:.2f}% "
                      f"(+{best_new_exclusions/total_samples*100:.2f}%)")
            else:
                break
        
        return selected_filters
    
    def visualize_correlation_matrix(self, correlation_matrix: pd.DataFrame):
        """상관관계 매트릭스 시각화"""
        plt.figure(figsize=(12, 10))
        
        # 히트맵 생성
        sns.heatmap(correlation_matrix, 
                    annot=True, 
                    fmt='.2f', 
                    cmap='coolwarm', 
                    center=0,
                    square=True,
                    linewidths=0.5,
                    cbar_kws={"shrink": 0.8})
        
        plt.title('필터 간 상관관계 매트릭스 (Jaccard 유사도)', fontsize=16, pad=20)
        plt.xlabel('필터', fontsize=12)
        plt.ylabel('필터', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()
        
        # 이미지 저장
        plt.savefig('analyze_system/filter_correlation_heatmap.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("\n상관관계 히트맵이 'analyze_system/filter_correlation_heatmap.png'에 저장되었습니다.")

def main():
    """메인 분석 함수"""
    print("="*80)
    print("필터 간 상관관계 분석")
    print("="*80)
    
    # 분석기 초기화
    analyzer = FilterCorrelationAnalyzer(sample_size=50000)
    
    # 샘플 조합 생성
    sample_combinations = analyzer.generate_sample_combinations()
    
    # 1. 각 필터의 제외 패턴 분석
    print("\n" + "="*60)
    print("1. 필터별 제외 패턴 분석")
    print("="*60)
    
    filter_exclusions = analyzer.analyze_filter_exclusions(sample_combinations)
    
    # 2. 필터 간 상관관계 계산
    print("\n" + "="*60)
    print("2. 필터 간 상관관계 분석")
    print("="*60)
    
    correlation_matrix = analyzer.calculate_correlation_matrix(filter_exclusions)
    
    # 상관관계가 높은 필터 쌍 출력
    print("\n[상관관계가 높은 필터 쌍 (상위 10개)]")
    correlations = []
    for i in range(len(correlation_matrix)):
        for j in range(i+1, len(correlation_matrix)):
            filter1 = correlation_matrix.index[i]
            filter2 = correlation_matrix.columns[j]
            corr = correlation_matrix.iloc[i, j]
            correlations.append((filter1, filter2, corr))
    
    correlations.sort(key=lambda x: x[2], reverse=True)
    
    for filter1, filter2, corr in correlations[:10]:
        print(f"{filter1} ↔ {filter2}: {corr:.3f}")
    
    # 3. 필터 조합 효과 분석
    print("\n" + "="*60)
    print("3. 필터 조합 효과 분석")
    print("="*60)
    
    combination_results = analyzer.analyze_filter_combinations(filter_exclusions, max_combination_size=3)
    
    # 가장 효과적인 2개 조합
    print("\n[가장 효과적인 2개 필터 조합 (상위 5개)]")
    two_combos = [(k, v) for k, v in combination_results.items() if len(k) == 2]
    two_combos.sort(key=lambda x: x[1]['union_exclusion_rate'], reverse=True)
    
    for combo, stats in two_combos[:5]:
        print(f"{' + '.join(combo)}: 제외율 {stats['union_exclusion_rate']*100:.2f}%, "
              f"중복도 {stats['overlap_ratio']*100:.1f}%")
    
    # 4. 최적 필터 세트 찾기
    print("\n" + "="*60)
    print("4. 최적 필터 세트 탐색")
    print("="*60)
    
    optimal_filters = analyzer.find_optimal_filter_set(filter_exclusions, target_exclusion_rate=0.90)
    
    print(f"\n최적 필터 조합 ({len(optimal_filters)}개): {', '.join(optimal_filters)}")
    
    # 5. 독립성 분석
    print("\n" + "="*60)
    print("5. 필터 독립성 분석")
    print("="*60)
    
    # 각 필터의 평균 상관관계 계산
    independence_scores = {}
    for filter_name in correlation_matrix.index:
        # 자기 자신과의 상관관계 제외
        other_correlations = correlation_matrix.loc[filter_name, correlation_matrix.columns != filter_name]
        avg_correlation = other_correlations.mean()
        independence_scores[filter_name] = 1 - avg_correlation  # 독립성 점수
    
    # 독립성이 높은 필터 순위
    sorted_independence = sorted(independence_scores.items(), key=lambda x: x[1], reverse=True)
    
    print("\n[필터 독립성 순위]")
    for filter_name, score in sorted_independence[:10]:
        print(f"{filter_name:25s}: 독립성 점수 {score:.3f}")
    
    # 6. 시각화
    analyzer.visualize_correlation_matrix(correlation_matrix)
    
    # 결과 저장
    analysis_results = {
        'sample_size': analyzer.sample_size,
        'filter_exclusion_rates': {
            name: len(exclusions) / analyzer.sample_size 
            for name, exclusions in filter_exclusions.items()
        },
        'correlation_matrix': correlation_matrix.to_dict(),
        'high_correlations': [
            {'filter1': f1, 'filter2': f2, 'correlation': float(corr)}
            for f1, f2, corr in correlations[:20]
        ],
        'best_combinations': {
            str(combo): {
                'exclusion_rate': stats['union_exclusion_rate'],
                'overlap_ratio': stats['overlap_ratio']
            }
            for combo, stats in two_combos[:10]
        },
        'optimal_filter_set': optimal_filters,
        'independence_scores': independence_scores
    }
    
    with open('analyze_system/filter_correlation_result.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ 분석 결과가 analyze_system/filter_correlation_result.json에 저장되었습니다.")

if __name__ == "__main__":
    main()