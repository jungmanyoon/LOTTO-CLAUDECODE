#!/usr/bin/env python3
"""
필터 상관관계 및 최적화 기회 분석 스크립트
"""
import json
import numpy as np
from collections import defaultdict
from typing import Dict, List, Set, Tuple
# Visualization libraries not used in current implementation
# import matplotlib.pyplot as plt
# import seaborn as sns

def load_analysis_results(filename: str = 'filter_analysis_result.json') -> Dict:
    """이전 분석 결과 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_winning_numbers(filename: str = 'winning_numbers.json') -> List[Dict]:
    """당첨번호 데이터 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_filter_overlaps(filter_results: Dict[str, Dict]) -> Dict:
    """필터 간 제외 번호 중복 분석"""
    overlaps = {}
    
    # match 필터는 모든 번호를 제외하므로 분석에서 제외
    active_filters = {name: result for name, result in filter_results.items() 
                     if name != 'match'}
    
    for filter1, result1 in active_filters.items():
        overlaps[filter1] = {}
        filtered_set1 = set(result1['filtered_rounds_list'])
        
        for filter2, result2 in active_filters.items():
            if filter1 != filter2:
                filtered_set2 = set(result2['filtered_rounds_list'])
                
                # 교집합 계산
                overlap = filtered_set1 & filtered_set2
                overlap_count = len(overlap)
                
                # Jaccard 유사도 계산
                union = filtered_set1 | filtered_set2
                jaccard = len(overlap) / len(union) if len(union) > 0 else 0
                
                overlaps[filter1][filter2] = {
                    'overlap_count': overlap_count,
                    'jaccard_similarity': jaccard,
                    'overlap_percentage': (overlap_count / len(filtered_set1) * 100) if len(filtered_set1) > 0 else 0
                }
    
    return overlaps

def analyze_filter_combinations(filter_results: Dict[str, Dict], winning_numbers: List[Dict]) -> Dict:
    """필터 조합 분석 - 어떤 조합이 가장 효과적인지"""
    # match 필터 제외
    active_filters = {name: result for name, result in filter_results.items() 
                     if name != 'match' and result['filtered_rounds'] > 0}
    
    total_rounds = len(winning_numbers)
    
    # 각 회차가 어떤 필터에 걸렸는지 기록
    round_filters = defaultdict(list)
    for filter_name, result in active_filters.items():
        for round_num in result['filtered_rounds_list']:
            round_filters[round_num].append(filter_name)
    
    # 필터 조합별 통계
    combination_stats = defaultdict(int)
    for round_num, filters in round_filters.items():
        if len(filters) > 0:
            # 필터를 정렬해서 일관된 키 생성
            combo_key = tuple(sorted(filters))
            combination_stats[combo_key] += 1
    
    # 분석 결과 정리
    analysis = {
        'single_filter_effectiveness': {},
        'multi_filter_combinations': {},
        'optimal_filter_sets': []
    }
    
    # 단일 필터 효과성
    for filter_name, result in active_filters.items():
        analysis['single_filter_effectiveness'][filter_name] = {
            'filtered_count': result['filtered_rounds'],
            'exclusion_rate': result['filtered_rounds'] / total_rounds * 100
        }
    
    # 다중 필터 조합
    for combo, count in combination_stats.items():
        if len(combo) > 1:  # 2개 이상의 필터 조합
            analysis['multi_filter_combinations'][', '.join(combo)] = {
                'count': count,
                'percentage': count / total_rounds * 100
            }
    
    # 최적 필터 세트 찾기 (최소 필터로 최대 제외)
    filter_coverage = calculate_filter_coverage(active_filters, total_rounds)
    analysis['optimal_filter_sets'] = filter_coverage
    
    return analysis

def calculate_filter_coverage(filters: Dict, total_rounds: int) -> List[Dict]:
    """최소 필터로 최대 커버리지 달성하는 조합 찾기"""
    # 각 필터의 제외 회차 집합
    filter_sets = {name: set(result['filtered_rounds_list']) 
                  for name, result in filters.items()}
    
    # 탐욕 알고리즘으로 최적 조합 찾기
    optimal_sets = []
    remaining_filters = list(filter_sets.keys())
    covered_rounds = set()
    selected_filters = []
    
    while remaining_filters and len(covered_rounds) < total_rounds:
        best_filter = None
        best_new_coverage = 0
        
        for filter_name in remaining_filters:
            new_coverage = len(filter_sets[filter_name] - covered_rounds)
            if new_coverage > best_new_coverage:
                best_new_coverage = new_coverage
                best_filter = filter_name
        
        if best_filter:
            selected_filters.append(best_filter)
            covered_rounds.update(filter_sets[best_filter])
            remaining_filters.remove(best_filter)
            
            optimal_sets.append({
                'filters': selected_filters.copy(),
                'coverage': len(covered_rounds),
                'coverage_percentage': len(covered_rounds) / total_rounds * 100,
                'filters_count': len(selected_filters)
            })
    
    return optimal_sets[:5]  # 상위 5개 조합만 반환

def analyze_winning_number_patterns(winning_numbers: List[Dict]) -> Dict:
    """당첨번호의 통계적 패턴 분석"""
    patterns = {
        'sum_distribution': [],
        'odd_even_distribution': defaultdict(int),
        'consecutive_distribution': defaultdict(int),
        'gap_distribution': [],
        'section_distribution': defaultdict(int)
    }
    
    for data in winning_numbers:
        numbers = data['numbers']
        
        # 합계 분포
        total_sum = sum(numbers)
        patterns['sum_distribution'].append(total_sum)
        
        # 홀짝 분포
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        patterns['odd_even_distribution'][odd_count] += 1
        
        # 연속번호 분포
        consecutive_count = 0
        for i in range(len(numbers) - 1):
            if numbers[i+1] - numbers[i] == 1:
                consecutive_count += 1
        patterns['consecutive_distribution'][consecutive_count] += 1
        
        # 간격 분포
        gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers) - 1)]
        patterns['gap_distribution'].extend(gaps)
        
        # 구간 분포 (10단위)
        for num in numbers:
            section = (num - 1) // 10
            patterns['section_distribution'][section] += 1
    
    # 통계 계산
    stats = {
        'sum_stats': {
            'mean': np.mean(patterns['sum_distribution']),
            'std': np.std(patterns['sum_distribution']),
            'min': min(patterns['sum_distribution']),
            'max': max(patterns['sum_distribution'])
        },
        'odd_even_most_common': max(patterns['odd_even_distribution'].items(), 
                                   key=lambda x: x[1])[0],
        'consecutive_most_common': max(patterns['consecutive_distribution'].items(), 
                                      key=lambda x: x[1])[0] if patterns['consecutive_distribution'] else 0,
        'gap_stats': {
            'mean': np.mean(patterns['gap_distribution']),
            'std': np.std(patterns['gap_distribution']),
            'max': max(patterns['gap_distribution'])
        }
    }
    
    return stats

def generate_recommendations(analysis_results: Dict, correlations: Dict, 
                           combinations: Dict, patterns: Dict) -> List[str]:
    """분석 결과를 바탕으로 권장사항 생성"""
    recommendations = []
    
    # 1. match 필터 개선
    recommendations.append(
        "1. **match 필터 개선 필요**\n"
        "   - 현재 match 필터는 모든 당첨번호를 제외합니다 (0% 통과율)\n"
        "   - 원인: 당첨번호 자체가 DB에 있어서 자기 자신과 6개 일치\n"
        "   - 해결책: 검사 대상에서 현재 회차 제외 또는 max_match를 6으로 설정"
    )
    
    # 2. 효과가 없는 필터 비활성화
    no_effect_filters = []
    for name, result in analysis_results['individual_filters'].items():
        if result['pass_rate'] == 100.0 and name != 'match':
            no_effect_filters.append(name)
    
    if no_effect_filters:
        recommendations.append(
            f"2. **효과 없는 필터 비활성화 권장**\n"
            f"   - 100% 통과율 필터: {', '.join(no_effect_filters)}\n"
            f"   - 이 필터들은 성능만 저하시키고 실제 필터링 효과가 없음"
        )
    
    # 3. 동적 임계값 설정
    recommendations.append(
        "3. **동적 임계값 설정**\n"
        f"   - 합계 범위: 평균 {patterns['sum_stats']['mean']:.1f}, "
        f"표준편차 {patterns['sum_stats']['std']:.1f}\n"
        f"   - 권장 범위: {patterns['sum_stats']['mean'] - 2*patterns['sum_stats']['std']:.0f} ~ "
        f"{patterns['sum_stats']['mean'] + 2*patterns['sum_stats']['std']:.0f}\n"
        f"   - 홀짝 비율: 가장 흔한 패턴은 홀수 {patterns['odd_even_most_common']}개"
    )
    
    # 4. 필터 우선순위
    effective_filters = sorted(
        [(name, result) for name, result in analysis_results['individual_filters'].items()
         if name != 'match' and result['filtered_rounds'] > 0],
        key=lambda x: x[1]['filtered_rounds'],
        reverse=True
    )
    
    if effective_filters:
        recommendations.append(
            "4. **필터 적용 우선순위**\n" +
            "\n".join([f"   {i+1}. {name}: {result['filtered_rounds']}개 제외" 
                      for i, (name, result) in enumerate(effective_filters[:5])])
        )
    
    # 5. 선택적 필터 적용
    if combinations['optimal_filter_sets']:
        best_set = combinations['optimal_filter_sets'][0]
        recommendations.append(
            f"5. **선택적 필터 적용**\n"
            f"   - 최적 필터 조합: {', '.join(best_set['filters'])}\n"
            f"   - 커버리지: {best_set['coverage_percentage']:.1f}%\n"
            f"   - 모든 필터를 항상 적용하지 말고 확률적으로 선택 적용"
        )
    
    return recommendations

def main():
    """메인 분석 함수"""
    print("="*60)
    print("필터 상관관계 및 최적화 분석")
    print("="*60)
    
    # 데이터 로드
    analysis_results = load_analysis_results()
    winning_numbers = load_winning_numbers()
    
    # 1. 필터 간 상관관계 분석
    print("\n[1] 필터 간 중복 분석")
    correlations = analyze_filter_overlaps(analysis_results['individual_filters'])
    
    # 상관관계가 높은 필터 쌍 출력
    high_correlations = []
    for filter1, overlaps in correlations.items():
        for filter2, overlap_data in overlaps.items():
            if overlap_data['jaccard_similarity'] > 0.3:  # 30% 이상 유사도
                high_correlations.append((filter1, filter2, overlap_data['jaccard_similarity']))
    
    if high_correlations:
        print("\n높은 상관관계를 가진 필터 쌍:")
        for f1, f2, similarity in sorted(high_correlations, key=lambda x: x[2], reverse=True)[:5]:
            print(f"  - {f1} <-> {f2}: {similarity:.2%} 유사도")
    
    # 2. 필터 조합 분석
    print("\n[2] 필터 조합 효과성 분석")
    combinations = analyze_filter_combinations(analysis_results['individual_filters'], winning_numbers)
    
    print("\n가장 효과적인 필터 조합:")
    for i, optimal in enumerate(combinations['optimal_filter_sets'][:3], 1):
        print(f"  {i}. {', '.join(optimal['filters'])}")
        print(f"     - 필터 개수: {optimal['filters_count']}개")
        print(f"     - 커버리지: {optimal['coverage_percentage']:.1f}%")
    
    # 3. 당첨번호 패턴 분석
    print("\n[3] 당첨번호 통계 패턴")
    patterns = analyze_winning_number_patterns(winning_numbers)
    
    print(f"\n합계 통계:")
    print(f"  - 평균: {patterns['sum_stats']['mean']:.1f}")
    print(f"  - 표준편차: {patterns['sum_stats']['std']:.1f}")
    print(f"  - 범위: {patterns['sum_stats']['min']} ~ {patterns['sum_stats']['max']}")
    
    print(f"\n홀짝 패턴:")
    print(f"  - 가장 흔한 홀수 개수: {patterns['odd_even_most_common']}개")
    
    print(f"\n간격 통계:")
    print(f"  - 평균 간격: {patterns['gap_stats']['mean']:.1f}")
    print(f"  - 최대 간격: {patterns['gap_stats']['max']}")
    
    # 4. 권장사항 생성
    print("\n" + "="*60)
    print("권장사항")
    print("="*60)
    
    recommendations = generate_recommendations(
        analysis_results, correlations, combinations, patterns
    )
    
    for recommendation in recommendations:
        print(f"\n{recommendation}")
    
    # 5. 결과 저장
    final_analysis = {
        'correlations': correlations,
        'combinations': combinations,
        'patterns': patterns,
        'recommendations': recommendations
    }
    
    with open('filter_optimization_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(final_analysis, f, ensure_ascii=False, indent=2)
    
    print("\n[O] 분석 결과가 filter_optimization_analysis.json 파일로 저장되었습니다.")

if __name__ == "__main__":
    main()