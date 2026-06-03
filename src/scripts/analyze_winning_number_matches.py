#!/usr/bin/env python3
"""
과거 당첨번호 간 일치도 분석

1182회차의 당첨번호들이 서로 얼마나 일치하는지 분석하여
Match 필터의 타당성을 검증합니다.
"""

import json
import sys
import os
from typing import List, Dict, Tuple
from collections import defaultdict
import numpy as np
from itertools import combinations

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_winning_numbers(filename: str = 'winning_numbers.json') -> List[Dict]:
    """당첨번호 데이터 로드"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def count_matches(numbers1: List[int], numbers2: List[int]) -> int:
    """두 번호 세트 간의 일치하는 개수 계산"""
    return len(set(numbers1) & set(numbers2))

def analyze_match_distribution(winning_data: List[Dict]) -> Dict[int, List[Tuple[int, int]]]:
    """
    모든 당첨번호 쌍의 일치도 분석
    
    Returns:
        Dict[int, List[Tuple[int, int]]]: 일치 개수별 회차 쌍 리스트
    """
    match_distribution = defaultdict(list)
    total_pairs = 0
    
    print("당첨번호 간 일치도 분석 중...")
    
    # 모든 회차 쌍에 대해 일치도 계산
    for i in range(len(winning_data)):
        for j in range(i + 1, len(winning_data)):
            round1 = winning_data[i]['round']
            round2 = winning_data[j]['round']
            numbers1 = winning_data[i]['numbers']
            numbers2 = winning_data[j]['numbers']
            
            matches = count_matches(numbers1, numbers2)
            match_distribution[matches].append((round1, round2))
            total_pairs += 1
    
    print(f"총 {total_pairs:,}개의 회차 쌍 분석 완료")
    
    return dict(match_distribution)

def calculate_theoretical_probability(match_count: int) -> float:
    """
    이론적 확률 계산
    
    Args:
        match_count: 일치하는 번호 개수
        
    Returns:
        float: 이론적 확률
    """
    # C(6, match_count) * C(39, 6-match_count) / C(45, 6)
    from math import comb
    
    total_combinations = comb(45, 6)
    matching_combinations = comb(6, match_count) * comb(39, 6 - match_count)
    
    return matching_combinations / total_combinations

def analyze_consecutive_matches(winning_data: List[Dict], match_threshold: int = 3) -> Dict:
    """
    연속된 회차 간의 일치도 분석
    
    Args:
        winning_data: 당첨번호 데이터
        match_threshold: 분석할 최소 일치 개수
        
    Returns:
        Dict: 연속 회차 분석 결과
    """
    consecutive_matches = defaultdict(int)
    high_matches = []
    
    for i in range(len(winning_data) - 1):
        round1 = winning_data[i]['round']
        round2 = winning_data[i + 1]['round']
        numbers1 = winning_data[i]['numbers']
        numbers2 = winning_data[i + 1]['numbers']
        
        matches = count_matches(numbers1, numbers2)
        consecutive_matches[matches] += 1
        
        if matches >= match_threshold:
            high_matches.append({
                'rounds': (round1, round2),
                'matches': matches,
                'numbers1': numbers1,
                'numbers2': numbers2,
                'common': list(set(numbers1) & set(numbers2))
            })
    
    return {
        'distribution': dict(consecutive_matches),
        'high_matches': high_matches
    }

def analyze_match_patterns(winning_data: List[Dict]) -> Dict:
    """
    일치 패턴의 상세 분석
    """
    # 일치도별 최근 발생 회차
    last_occurrence = {i: [] for i in range(7)}
    
    for i in range(len(winning_data)):
        for j in range(i + 1, len(winning_data)):
            matches = count_matches(winning_data[i]['numbers'], winning_data[j]['numbers'])
            gap = winning_data[j]['round'] - winning_data[i]['round']
            last_occurrence[matches].append({
                'rounds': (winning_data[i]['round'], winning_data[j]['round']),
                'gap': gap,
                'date1': winning_data[i]['draw_date'],
                'date2': winning_data[j]['draw_date']
            })
    
    # 각 일치도별 최근 10개 사례만 유지
    for matches in last_occurrence:
        last_occurrence[matches] = sorted(
            last_occurrence[matches], 
            key=lambda x: x['rounds'][1], 
            reverse=True
        )[:10]
    
    return last_occurrence

def main():
    """메인 분석 함수"""
    print("="*80)
    print("로또 당첨번호 간 일치도 분석")
    print("="*80)
    
    # 데이터 로드
    winning_data = load_winning_numbers()
    total_rounds = len(winning_data)
    print(f"\n총 {total_rounds}개 회차 데이터 로드 완료")
    
    # 1. 전체 일치도 분포 분석
    print("\n" + "="*60)
    print("1. 전체 당첨번호 간 일치도 분포")
    print("="*60)
    
    match_distribution = analyze_match_distribution(winning_data)
    
    # 통계 출력
    total_pairs = sum(len(pairs) for pairs in match_distribution.values())
    
    print("\n일치 개수별 발생 빈도:")
    for match_count in range(7):
        if match_count in match_distribution:
            count = len(match_distribution[match_count])
            percentage = (count / total_pairs) * 100
            theoretical_prob = calculate_theoretical_probability(match_count) * 100
            
            print(f"{match_count}개 일치: {count:,}회 ({percentage:.4f}%) "
                  f"[이론적 확률: {theoretical_prob:.4f}%]")
            
            # 차이 분석
            if percentage > 0:
                diff = ((percentage - theoretical_prob) / theoretical_prob) * 100
                print(f"  -> 이론값 대비: {diff:+.2f}%")
    
    # 2. 5개 이상 일치 사례 상세 분석
    print("\n" + "="*60)
    print("2. 5개 이상 일치 사례 상세 분석")
    print("="*60)
    
    high_match_found = False
    for match_count in [6, 5]:
        if match_count in match_distribution and match_distribution[match_count]:
            high_match_found = True
            print(f"\n{match_count}개 일치 사례:")
            for round1, round2 in match_distribution[match_count][:5]:  # 최대 5개만 표시
                idx1 = round1 - 1
                idx2 = round2 - 1
                numbers1 = winning_data[idx1]['numbers']
                numbers2 = winning_data[idx2]['numbers']
                common = sorted(list(set(numbers1) & set(numbers2)))
                
                print(f"  - {round1}회차 vs {round2}회차")
                print(f"    {round1}회차: {numbers1}")
                print(f"    {round2}회차: {numbers2}")
                print(f"    공통번호: {common}")
    
    if not high_match_found:
        print("5개 이상 일치하는 사례가 없습니다.")
        print("-> Match 필터의 max_match=5 기준은 타당합니다.")
    
    # 3. 4개 일치 사례 분석
    print("\n" + "="*60)
    print("3. 4개 일치 사례 분석")
    print("="*60)
    
    if 4 in match_distribution:
        four_match_count = len(match_distribution[4])
        print(f"총 {four_match_count}개의 4개 일치 사례 발견")
        
        # 최근 10개 사례만 표시
        print("\n최근 4개 일치 사례 (최대 10개):")
        recent_cases = sorted(match_distribution[4], key=lambda x: max(x[0], x[1]), reverse=True)[:10]
        
        for round1, round2 in recent_cases:
            idx1 = round1 - 1
            idx2 = round2 - 1
            gap = abs(round2 - round1)
            print(f"  - {round1}회차 vs {round2}회차 (간격: {gap}회차)")
    
    # 4. 연속 회차 간 일치도 분석
    print("\n" + "="*60)
    print("4. 연속 회차 간 일치도 분석")
    print("="*60)
    
    consecutive_analysis = analyze_consecutive_matches(winning_data)
    
    print("\n연속 회차 일치도 분포:")
    for match_count in range(7):
        if match_count in consecutive_analysis['distribution']:
            count = consecutive_analysis['distribution'][match_count]
            percentage = (count / (total_rounds - 1)) * 100
            print(f"{match_count}개 일치: {count}회 ({percentage:.2f}%)")
    
    if consecutive_analysis['high_matches']:
        print(f"\n연속 회차에서 3개 이상 일치 사례: {len(consecutive_analysis['high_matches'])}건")
        for case in consecutive_analysis['high_matches'][:5]:
            print(f"  - {case['rounds'][0]}회차 -> {case['rounds'][1]}회차: "
                  f"{case['matches']}개 일치 (공통: {case['common']})")
    
    # 5. Match 필터 기준 제안
    print("\n" + "="*60)
    print("5. Match 필터 기준 제안")
    print("="*60)
    
    # 통계 기반 제안
    print("\n분석 결과 기반 제안:")
    
    if 6 not in match_distribution or not match_distribution[6]:
        print("- 6개 일치(완전 일치): 발생 사례 없음 -> 필터링 불필요")
    
    if 5 not in match_distribution or not match_distribution[5]:
        print("- 5개 일치: 발생 사례 없음 -> max_match=5 설정 타당")
    else:
        print(f"- 5개 일치: {len(match_distribution[5])}건 발생 -> max_match=5 재검토 필요")
    
    if 4 in match_distribution:
        four_match_prob = (len(match_distribution[4]) / total_pairs) * 100
        if four_match_prob < 0.1:  # 0.1% 미만
            print(f"- 4개 일치: {four_match_prob:.4f}% -> max_match=4도 고려 가능")
    
    # 결과 저장
    analysis_result = {
        'total_rounds': total_rounds,
        'total_pairs_analyzed': total_pairs,
        'match_distribution': {k: len(v) for k, v in match_distribution.items()},
        'high_match_cases': {
            5: match_distribution.get(5, [])[:10],
            4: match_distribution.get(4, [])[:20]
        },
        'consecutive_matches': consecutive_analysis,
        'recommendations': {
            'current_max_match_5': '5개 이상 일치 사례가 없으므로 타당' if 5 not in match_distribution or not match_distribution[5] else '재검토 필요',
            'consider_max_match_4': '4개 일치 확률이 매우 낮으므로 고려 가능' if 4 in match_distribution and len(match_distribution[4]) / total_pairs < 0.001 else '현재 기준 유지'
        }
    }
    
    with open('analyze_system/match_analysis_result.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    print("\n[O] 분석 결과가 analyze_system/match_analysis_result.json에 저장되었습니다.")

if __name__ == "__main__":
    main()