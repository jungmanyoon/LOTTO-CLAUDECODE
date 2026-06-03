#!/usr/bin/env python3
"""
과거 당첨번호에 대한 필터 분석 스크립트
각 필터가 얼마나 많은 당첨번호를 제외하는지 분석
"""
import json
import sys
import os
from typing import List, Dict, Tuple
from collections import defaultdict

# 프로젝트 루트 경로를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.utils.config_manager import ConfigManager

def load_winning_numbers(filename: str = 'winning_numbers.json') -> List[Dict]:
    """저장된 당첨번호 데이터 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_filter_on_winning_numbers(filter_name: str, filter_instance, winning_numbers: List[Dict]) -> Dict:
    """
    특정 필터를 모든 당첨번호에 적용하여 분석
    
    Returns:
        Dict: {
            'total_rounds': 전체 회차 수,
            'filtered_rounds': 필터링된 회차 수,
            'pass_rate': 통과율 (%),
            'filtered_rounds_list': 필터링된 회차 번호 리스트
        }
    """
    total_rounds = len(winning_numbers)
    filtered_rounds = []
    
    for data in winning_numbers:
        round_num = data['round']
        numbers = data['numbers']
        
        # 각 필터의 apply 메서드는 조합 리스트를 받으므로 형식 맞추기
        combination = ','.join(map(str, numbers))
        combinations = [combination]
        
        # 필터 적용
        try:
            result = filter_instance.apply(combinations, round_num)
            
            # 필터링되었는지 확인 (결과가 비어있으면 필터링됨)
            if result is None or len(result) == 0:
                filtered_rounds.append(round_num)
        except Exception as e:
            print(f"Error applying {filter_name} filter on round {round_num}: {e}")
    
    filtered_count = len(filtered_rounds)
    pass_count = total_rounds - filtered_count
    pass_rate = (pass_count / total_rounds) * 100 if total_rounds > 0 else 0
    
    return {
        'total_rounds': total_rounds,
        'filtered_rounds': filtered_count,
        'pass_count': pass_count,
        'pass_rate': pass_rate,
        'filtered_rounds_list': filtered_rounds
    }

def analyze_combined_filters(filter_results: Dict[str, Dict], winning_numbers: List[Dict]) -> Dict:
    """
    모든 필터를 동시에 적용했을 때의 결과 분석
    """
    total_rounds = len(winning_numbers)
    all_filtered_rounds = set()
    
    # 각 필터에서 제외된 회차들의 합집합
    for filter_name, result in filter_results.items():
        all_filtered_rounds.update(result['filtered_rounds_list'])
    
    # 모든 필터를 통과한 회차
    passed_all_filters = total_rounds - len(all_filtered_rounds)
    pass_rate = (passed_all_filters / total_rounds) * 100 if total_rounds > 0 else 0
    
    # 필터별 제외 빈도 분석
    filter_exclusion_count = defaultdict(int)
    for round_num in range(1, total_rounds + 1):
        excluded_by = []
        for filter_name, result in filter_results.items():
            if round_num in result['filtered_rounds_list']:
                excluded_by.append(filter_name)
        
        if len(excluded_by) > 0:
            filter_exclusion_count[len(excluded_by)] += 1
    
    return {
        'total_rounds': total_rounds,
        'passed_all_filters': passed_all_filters,
        'pass_rate': pass_rate,
        'exclusion_distribution': dict(filter_exclusion_count),
        'total_filtered_rounds': len(all_filtered_rounds)
    }

def main():
    """메인 분석 함수"""
    print("="*60)
    print("로또 필터 분석 시작")
    print("="*60)
    
    # 당첨번호 데이터 로드
    winning_numbers = load_winning_numbers()
    print(f"\n[O] {len(winning_numbers)}개 회차의 당첨번호 데이터 로드 완료")
    
    # DB 매니저 및 필터 매니저 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    print(f"\n[O] {len(filter_manager.filters)}개의 필터가 등록되었습니다.")
    
    # 각 필터별 분석 결과 저장
    filter_results = {}
    
    print("\n" + "="*60)
    print("개별 필터 분석 결과")
    print("="*60)
    
    # 각 필터를 당첨번호에 적용
    for filter_name, filter_instance in filter_manager.filters.items():
        print(f"\n[{filter_name}] 필터 분석 중...", end='', flush=True)
        
        result = analyze_filter_on_winning_numbers(filter_name, filter_instance, winning_numbers)
        filter_results[filter_name] = result
        
        print(f" 완료!")
        print(f"  - 총 회차: {result['total_rounds']}개")
        print(f"  - 필터링된 회차: {result['filtered_rounds']}개")
        print(f"  - 통과한 회차: {result['pass_count']}개")
        print(f"  - 통과율: {result['pass_rate']:.2f}%")
        
        # 필터링된 회차가 많은 경우 샘플 출력
        if result['filtered_rounds'] > 0:
            sample_size = min(5, len(result['filtered_rounds_list']))
            print(f"  - 필터링된 회차 예시: {result['filtered_rounds_list'][:sample_size]}")
    
    # 필터별 통과율 순위
    print("\n" + "="*60)
    print("필터별 통과율 순위 (높은 순)")
    print("="*60)
    
    sorted_filters = sorted(filter_results.items(), key=lambda x: x[1]['pass_rate'], reverse=True)
    for i, (filter_name, result) in enumerate(sorted_filters, 1):
        print(f"{i:2d}. {filter_name:25s}: {result['pass_rate']:6.2f}% "
              f"(필터링: {result['filtered_rounds']:4d}개, 통과: {result['pass_count']:4d}개)")
    
    # 모든 필터 동시 적용 분석
    print("\n" + "="*60)
    print("모든 필터 동시 적용 결과")
    print("="*60)
    
    combined_result = analyze_combined_filters(filter_results, winning_numbers)
    print(f"- 총 회차: {combined_result['total_rounds']}개")
    print(f"- 모든 필터를 통과한 회차: {combined_result['passed_all_filters']}개")
    print(f"- 전체 통과율: {combined_result['pass_rate']:.2f}%")
    print(f"- 하나 이상의 필터에 걸린 회차: {combined_result['total_filtered_rounds']}개")
    
    print("\n필터 개수별 제외 분포:")
    for num_filters, count in sorted(combined_result['exclusion_distribution'].items()):
        print(f"  - {num_filters}개 필터에 제외: {count}개 회차")
    
    # 결과를 JSON 파일로 저장
    analysis_result = {
        'individual_filters': filter_results,
        'combined_analysis': combined_result,
        'filter_ranking': [(name, result['pass_rate']) for name, result in sorted_filters]
    }
    
    with open('filter_analysis_result.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    print("\n[O] 분석 결과가 filter_analysis_result.json 파일로 저장되었습니다.")
    
    # 주요 통찰
    print("\n" + "="*60)
    print("주요 통찰")
    print("="*60)
    
    if combined_result['passed_all_filters'] == 0:
        print("[WARN] 경고: 모든 필터를 동시에 적용하면 어떤 당첨번호도 통과하지 못합니다!")
        print("   -> 필터 기준을 완화하거나 선택적 적용이 필요합니다.")
    else:
        print(f"[O] {combined_result['pass_rate']:.2f}%의 당첨번호가 모든 필터를 통과합니다.")
    
    # 가장 엄격한 필터들
    print("\n가장 엄격한 필터 TOP 5:")
    for i, (filter_name, result) in enumerate(sorted_filters[-5:], 1):
        print(f"  {i}. {filter_name}: {result['pass_rate']:.2f}% 통과율")
    
    # 가장 관대한 필터들
    print("\n가장 관대한 필터 TOP 5:")
    for i, (filter_name, result) in enumerate(sorted_filters[:5], 1):
        print(f"  {i}. {filter_name}: {result['pass_rate']:.2f}% 통과율")

if __name__ == "__main__":
    main()