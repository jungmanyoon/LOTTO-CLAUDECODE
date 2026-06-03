#!/usr/bin/env python3
"""
각 필터의 실제 효과성 재평가

시계열 분할 방식으로 백테스팅하여 과적합을 방지하고
실제 예측력을 평가합니다.
"""

import json
import sys
import os
from typing import List, Dict, Tuple, Any
from collections import defaultdict
import numpy as np
from tqdm import tqdm
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager

def split_data_by_time(winning_data: List[Dict], 
                      train_end: int = 800, 
                      val_end: int = 1000) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    데이터를 시계열로 분할
    
    Args:
        winning_data: 전체 당첨번호 데이터
        train_end: 학습 데이터 마지막 회차
        val_end: 검증 데이터 마지막 회차
        
    Returns:
        Tuple[train, validation, test]: 분할된 데이터
    """
    train_data = [d for d in winning_data if d['round'] <= train_end]
    val_data = [d for d in winning_data if train_end < d['round'] <= val_end]
    test_data = [d for d in winning_data if d['round'] > val_end]
    
    return train_data, val_data, test_data

def calculate_filter_statistics(filter_name: str, filter_instance: Any, 
                              all_combinations: List[str]) -> Dict[str, Any]:
    """
    필터의 통계 계산 (전체 조합 대상)
    
    Args:
        filter_name: 필터 이름
        filter_instance: 필터 인스턴스
        all_combinations: 전체 8,145,060개 조합
        
    Returns:
        Dict: 필터 통계
    """
    print(f"\n[{filter_name}] 필터 분석 중...")
    
    # 샘플링으로 빠른 추정 (전체의 1%)
    sample_size = min(81450, len(all_combinations))
    sample_indices = np.random.choice(len(all_combinations), sample_size, replace=False)
    sample_combinations = [all_combinations[i] for i in sample_indices]
    
    # 필터 적용
    try:
        filtered = filter_instance.apply(sample_combinations, 1000)  # 임의 회차
        excluded_count = len(sample_combinations) - len(filtered)
        exclude_rate = excluded_count / len(sample_combinations)
        
        # 전체 추정
        estimated_excluded = int(exclude_rate * len(all_combinations))
        
        return {
            'sample_size': sample_size,
            'sample_excluded': excluded_count,
            'exclude_rate': exclude_rate,
            'estimated_total_excluded': estimated_excluded,
            'estimated_remaining': len(all_combinations) - estimated_excluded
        }
    except Exception as e:
        print(f"  오류 발생: {str(e)}")
        return {
            'error': str(e),
            'exclude_rate': 0.0
        }

def evaluate_filter_on_winning_numbers(filter_name: str, filter_instance: Any,
                                     train_data: List[Dict], test_data: List[Dict]) -> Dict[str, Any]:
    """
    당첨번호에 대한 필터 평가
    
    Args:
        filter_name: 필터 이름
        filter_instance: 필터 인스턴스
        train_data: 학습 데이터 (필터 기준 설정용)
        test_data: 테스트 데이터 (평가용)
        
    Returns:
        Dict: 평가 결과
    """
    # 테스트 데이터에서 필터링된 당첨번호 확인
    filtered_winning_numbers = []
    
    for data in test_data:
        round_num = data['round']
        numbers = data['numbers']
        combination = ','.join(map(str, numbers))
        
        try:
            result = filter_instance.apply([combination], round_num)
            if not result or len(result) == 0:
                # 필터에 걸림 (제외됨)
                filtered_winning_numbers.append({
                    'round': round_num,
                    'numbers': numbers,
                    'date': data['draw_date']
                })
        except Exception as e:
            pass
    
    # 평가 지표 계산
    total_test = len(test_data)
    filtered_count = len(filtered_winning_numbers)
    pass_rate = (total_test - filtered_count) / total_test if total_test > 0 else 1.0
    
    return {
        'total_test_rounds': total_test,
        'filtered_winning_count': filtered_count,
        'pass_rate': pass_rate,
        'filtered_rounds': [f['round'] for f in filtered_winning_numbers[:10]]  # 최대 10개만
    }

def analyze_filter_independence(filter_results: Dict[str, List[str]]) -> Dict[str, float]:
    """
    필터 간 독립성 분석
    
    Args:
        filter_results: 각 필터가 제외한 조합들
        
    Returns:
        Dict: 필터 간 중복도
    """
    independence_matrix = {}
    
    filter_names = list(filter_results.keys())
    for i, filter1 in enumerate(filter_names):
        for j, filter2 in enumerate(filter_names):
            if i >= j:
                continue
                
            set1 = set(filter_results[filter1])
            set2 = set(filter_results[filter2])
            
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            
            # Jaccard 유사도
            jaccard = intersection / union if union > 0 else 0
            
            independence_matrix[f"{filter1}-{filter2}"] = 1 - jaccard
    
    return independence_matrix

def generate_all_combinations() -> List[str]:
    """
    모든 가능한 로또 조합 생성 (8,145,060개)
    메모리 효율을 위해 문자열로 저장
    """
    from itertools import combinations
    
    all_combinations = []
    for combo in combinations(range(1, 46), 6):
        all_combinations.append(','.join(map(str, combo)))
    
    return all_combinations

def main():
    """메인 분석 함수"""
    print("="*80)
    print("필터 효과성 재평가 (시계열 분할 백테스팅)")
    print("="*80)
    
    # 데이터 로드
    with open('winning_numbers.json', 'r', encoding='utf-8') as f:
        winning_data = json.load(f)
    
    # 시계열 분할
    train_data, val_data, test_data = split_data_by_time(winning_data, 800, 1000)
    
    print(f"\n데이터 분할:")
    print(f"- 학습 데이터: 1-800회차 ({len(train_data)}개)")
    print(f"- 검증 데이터: 801-1000회차 ({len(val_data)}개)")
    print(f"- 테스트 데이터: 1001-{winning_data[-1]['round']}회차 ({len(test_data)}개)")
    
    # DB 및 필터 매니저 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    print(f"\n등록된 필터: {len(filter_manager.filters)}개")
    
    # 전체 조합 생성 (샘플링용)
    print("\n전체 조합 샘플 생성 중...")
    all_combinations = generate_all_combinations()
    print(f"총 {len(all_combinations):,}개 조합 생성 완료")
    
    # 필터별 분석 결과 저장
    filter_analysis = {}
    filter_excluded_combinations = {}
    
    print("\n" + "="*60)
    print("필터별 효과성 분석")
    print("="*60)
    
    for filter_name, filter_instance in filter_manager.filters.items():
        print(f"\n[{filter_name}] 필터 분석 시작")
        
        # 1. 전체 조합에 대한 필터 효과
        stats = calculate_filter_statistics(filter_name, filter_instance, all_combinations)
        
        # 2. 당첨번호에 대한 필터 평가
        winning_eval = evaluate_filter_on_winning_numbers(
            filter_name, filter_instance, train_data, test_data
        )
        
        # 결과 저장
        filter_analysis[filter_name] = {
            'statistics': stats,
            'winning_evaluation': winning_eval,
            'criteria': filter_instance.get_criteria() if hasattr(filter_instance, 'get_criteria') else {}
        }
        
        # 결과 출력
        if 'exclude_rate' in stats:
            print(f"  - 제외율: {stats['exclude_rate']*100:.2f}%")
            print(f"  - 추정 제외 조합: {stats['estimated_total_excluded']:,}개")
            print(f"  - 당첨번호 통과율: {winning_eval['pass_rate']*100:.2f}%")
            
            if winning_eval['filtered_winning_count'] > 0:
                print(f"  [WARN] 테스트 기간 중 {winning_eval['filtered_winning_count']}개 당첨번호가 필터링됨!")
                print(f"     필터링된 회차: {winning_eval['filtered_rounds']}")
    
    # 필터 효과성 순위
    print("\n" + "="*60)
    print("필터 효과성 순위")
    print("="*60)
    
    # 제외율 기준 순위
    print("\n[제외율 순위]")
    sorted_by_exclude = sorted(
        [(name, data['statistics'].get('exclude_rate', 0)) 
         for name, data in filter_analysis.items()],
        key=lambda x: x[1],
        reverse=True
    )
    
    for i, (name, rate) in enumerate(sorted_by_exclude[:10], 1):
        winning_pass = filter_analysis[name]['winning_evaluation']['pass_rate']
        print(f"{i:2d}. {name:25s}: 제외율 {rate*100:6.2f}%, 당첨번호 통과율 {winning_pass*100:6.2f}%")
    
    # 당첨번호 필터링 문제가 있는 필터
    print("\n[[WARN] 주의가 필요한 필터]")
    problematic_filters = [
        (name, data) for name, data in filter_analysis.items()
        if data['winning_evaluation']['filtered_winning_count'] > 0
    ]
    
    if problematic_filters:
        sorted_problematic = sorted(
            problematic_filters,
            key=lambda x: x[1]['winning_evaluation']['filtered_winning_count'],
            reverse=True
        )
        
        for name, data in sorted_problematic:
            count = data['winning_evaluation']['filtered_winning_count']
            rate = data['winning_evaluation']['pass_rate']
            print(f"- {name}: {count}개 당첨번호 필터링 (통과율 {rate*100:.2f}%)")
    else:
        print("- 모든 필터가 테스트 기간의 당첨번호를 통과시켰습니다.")
    
    # 최적 필터 조합 제안
    print("\n" + "="*60)
    print("최적 필터 조합 제안")
    print("="*60)
    
    # 효과적이면서 안전한 필터 선별
    safe_effective_filters = [
        name for name, data in filter_analysis.items()
        if data['statistics'].get('exclude_rate', 0) > 0.05  # 5% 이상 제외
        and data['winning_evaluation']['pass_rate'] >= 0.98  # 98% 이상 당첨번호 통과
    ]
    
    print(f"\n안전하고 효과적인 필터 {len(safe_effective_filters)}개:")
    for name in safe_effective_filters:
        exclude_rate = filter_analysis[name]['statistics']['exclude_rate']
        pass_rate = filter_analysis[name]['winning_evaluation']['pass_rate']
        print(f"- {name}: 제외율 {exclude_rate*100:.2f}%, 통과율 {pass_rate*100:.2f}%")
    
    # 결과 저장
    analysis_result = {
        'analysis_date': datetime.now().isoformat(),
        'data_split': {
            'train': f"1-800 ({len(train_data)} rounds)",
            'validation': f"801-1000 ({len(val_data)} rounds)",
            'test': f"1001-{winning_data[-1]['round']} ({len(test_data)} rounds)"
        },
        'filter_analysis': filter_analysis,
        'effectiveness_ranking': [
            {
                'rank': i+1,
                'filter': name,
                'exclude_rate': rate,
                'winning_pass_rate': filter_analysis[name]['winning_evaluation']['pass_rate']
            }
            for i, (name, rate) in enumerate(sorted_by_exclude)
        ],
        'problematic_filters': [
            {
                'filter': name,
                'filtered_winning_count': data['winning_evaluation']['filtered_winning_count'],
                'filtered_rounds': data['winning_evaluation']['filtered_rounds']
            }
            for name, data in problematic_filters
        ],
        'safe_effective_filters': safe_effective_filters
    }
    
    with open('analyze_system/filter_effectiveness_result.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    print("\n[O] 분석 결과가 analyze_system/filter_effectiveness_result.json에 저장되었습니다.")

if __name__ == "__main__":
    main()