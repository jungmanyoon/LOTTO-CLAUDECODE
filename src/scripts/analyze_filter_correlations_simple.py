#!/usr/bin/env python3
"""
필터 상관관계 및 최적화 분석 스크립트 (간소화 버전)
"""
import json
import numpy as np
from collections import defaultdict
from typing import Dict, List

def load_analysis_results(filename: str = 'filter_analysis_result.json') -> Dict:
    """이전 분석 결과 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_winning_numbers(filename: str = 'winning_numbers.json') -> List[Dict]:
    """당첨번호 데이터 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_winning_number_patterns(winning_numbers: List[Dict]) -> Dict:
    """당첨번호의 통계적 패턴 분석"""
    sum_distribution = []
    odd_even_distribution = defaultdict(int)
    consecutive_distribution = defaultdict(int)
    gap_distribution = []
    
    for data in winning_numbers:
        numbers = data['numbers']
        
        # 합계 분포
        total_sum = sum(numbers)
        sum_distribution.append(total_sum)
        
        # 홀짝 분포
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        odd_even_distribution[odd_count] += 1
        
        # 연속번호 개수
        consecutive_count = 0
        for i in range(len(numbers) - 1):
            if numbers[i+1] - numbers[i] == 1:
                consecutive_count += 1
        consecutive_distribution[consecutive_count] += 1
        
        # 간격 분포
        gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers) - 1)]
        gap_distribution.extend(gaps)
    
    # 통계 계산
    stats = {
        'sum_stats': {
            'mean': np.mean(sum_distribution),
            'std': np.std(sum_distribution),
            'min': min(sum_distribution),
            'max': max(sum_distribution)
        },
        'odd_even_most_common': max(odd_even_distribution.items(), key=lambda x: x[1])[0],
        'gap_stats': {
            'mean': np.mean(gap_distribution),
            'max': max(gap_distribution)
        }
    }
    
    return stats

def main():
    """메인 분석 함수"""
    print("="*60)
    print("필터 최적화 분석 (간소화 버전)")
    print("="*60)
    
    # 데이터 로드
    analysis_results = load_analysis_results()
    winning_numbers = load_winning_numbers()
    
    # 1. 필터 효과성 순위
    print("\n[1] 필터 효과성 분석")
    
    # match 필터 제외하고 정렬
    filter_effectiveness = []
    for name, result in analysis_results['individual_filters'].items():
        if name != 'match':
            filter_effectiveness.append({
                'name': name,
                'filtered': result['filtered_rounds'],
                'pass_rate': result['pass_rate']
            })
    
    # 필터링 개수로 정렬
    filter_effectiveness.sort(key=lambda x: x['filtered'], reverse=True)
    
    print("\n효과적인 필터 TOP 10:")
    for i, filter_info in enumerate(filter_effectiveness[:10], 1):
        print(f"{i:2d}. {filter_info['name']:20s}: "
              f"{filter_info['filtered']:3d}개 제외 (통과율 {filter_info['pass_rate']:6.2f}%)")
    
    # 효과 없는 필터
    no_effect_filters = [f for f in filter_effectiveness if f['filtered'] == 0]
    if no_effect_filters:
        print(f"\n효과 없는 필터 ({len(no_effect_filters)}개):")
        for filter_info in no_effect_filters:
            print(f"  - {filter_info['name']}")
    
    # 2. 당첨번호 패턴 분석
    print("\n[2] 당첨번호 통계 패턴")
    patterns = analyze_winning_number_patterns(winning_numbers)
    
    print(f"\n합계 통계:")
    print(f"  - 평균: {patterns['sum_stats']['mean']:.1f}")
    print(f"  - 표준편차: {patterns['sum_stats']['std']:.1f}")
    print(f"  - 범위: {patterns['sum_stats']['min']} ~ {patterns['sum_stats']['max']}")
    print(f"  - 권장 범위 (평균+-2s): "
          f"{patterns['sum_stats']['mean'] - 2*patterns['sum_stats']['std']:.0f} ~ "
          f"{patterns['sum_stats']['mean'] + 2*patterns['sum_stats']['std']:.0f}")
    
    print(f"\n홀짝 패턴:")
    print(f"  - 가장 흔한 홀수 개수: {patterns['odd_even_most_common']}개")
    
    print(f"\n간격 통계:")
    print(f"  - 평균 간격: {patterns['gap_stats']['mean']:.1f}")
    print(f"  - 최대 간격: {patterns['gap_stats']['max']}")
    
    # 3. 권장사항
    print("\n" + "="*60)
    print("주요 권장사항")
    print("="*60)
    
    print("\n1. **즉시 수정 필요**")
    print("   - match 필터: 현재 0% 통과율 (모든 번호 제외)")
    print("   - 원인: 당첨번호가 자기 자신과 6개 일치하여 제외됨")
    print("   - 해결: max_match를 6으로 설정하거나 현재 회차 제외")
    
    print("\n2. **비활성화 권장 필터**")
    if no_effect_filters:
        print(f"   - 효과 없는 필터 {len(no_effect_filters)}개: "
              f"{', '.join([f['name'] for f in no_effect_filters])}")
        print("   - 이 필터들은 성능만 저하시킴")
    
    print("\n3. **동적 임계값 설정 권장**")
    print(f"   - 합계 범위: 현재 65~215 -> "
          f"권장 {patterns['sum_stats']['mean'] - 2*patterns['sum_stats']['std']:.0f}~"
          f"{patterns['sum_stats']['mean'] + 2*patterns['sum_stats']['std']:.0f}")
    print(f"   - 홀짝 비율: 6:0 제외 -> 홀수 {patterns['odd_even_most_common']}개가 가장 흔함")
    
    print("\n4. **선택적 필터 적용**")
    print("   - 모든 필터를 항상 적용하면 유효한 조합이 없음")
    print("   - 필터를 확률적으로 선택 적용하거나 그룹화하여 적용")
    
    # 필터 그룹 제안
    print("\n5. **필터 그룹화 제안**")
    print("   - 그룹 A (기본): odd_even, sum_range, dispersion")
    print("   - 그룹 B (패턴): fixed_step, section, average") 
    print("   - 그룹 C (보조): max_gap, multiple")
    print("   - 각 그룹에서 1-2개씩 선택하여 적용")
    
    # 4. 결과 저장
    optimization_summary = {
        'filter_effectiveness': filter_effectiveness,
        'no_effect_filters': [f['name'] for f in no_effect_filters],
        'patterns': patterns,
        'recommendations': {
            'fix_match_filter': True,
            'disable_filters': [f['name'] for f in no_effect_filters],
            'dynamic_thresholds': {
                'sum_range': {
                    'current': [65, 215],
                    'recommended': [
                        int(patterns['sum_stats']['mean'] - 2*patterns['sum_stats']['std']),
                        int(patterns['sum_stats']['mean'] + 2*patterns['sum_stats']['std'])
                    ]
                },
                'odd_even': {
                    'exclude': [0, 6],
                    'most_common': patterns['odd_even_most_common']
                }
            }
        }
    }
    
    with open('filter_optimization_summary.json', 'w', encoding='utf-8') as f:
        json.dump(optimization_summary, f, ensure_ascii=False, indent=2)
    
    print("\n[O] 분석 결과가 filter_optimization_summary.json 파일로 저장되었습니다.")

if __name__ == "__main__":
    main()