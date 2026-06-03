#!/usr/bin/env python3
"""
중복 조합 확률 분석
과거에 나온 조합이 다시 나올 확률은?
"""

import math
import os
import sys

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)


def analyze_duplicate_probability():
    """중복 조합 확률 분석"""
    
    print("="*60)
    print("로또 중복 조합 확률 분석")
    print("="*60)
    
    # 기본 수치
    total_combinations = 8_145_060  # 45C6
    draws_so_far = 1_172  # 현재까지 추첨 횟수
    
    print(f"\n1. 기본 통계")
    print(f"   - 전체 가능한 조합: {total_combinations:,}개")
    print(f"   - 지금까지 추첨: {draws_so_far:,}회")
    print(f"   - 사용된 조합 비율: {draws_so_far/total_combinations*100:.4f}%")
    
    # 중복 확률 계산
    print(f"\n2. 중복 확률 계산")
    
    # 다음 추첨에서 기존 조합이 나올 확률
    prob_duplicate = draws_so_far / total_combinations
    prob_new = 1 - prob_duplicate
    
    print(f"   - 기존 조합이 나올 확률: {prob_duplicate:.8f} ({prob_duplicate*100:.6f}%)")
    print(f"   - 새로운 조합이 나올 확률: {prob_new:.8f} ({prob_new*100:.6f}%)")
    
    # 확률 개선 효과
    print(f"\n3. 필터링 효과 분석")
    
    # 원래 확률
    original_prob = 1 / total_combinations
    # 기존 조합 제외 후 확률
    filtered_prob = 1 / (total_combinations - draws_so_far)
    
    improvement = (filtered_prob - original_prob) / original_prob * 100
    
    print(f"   - 원래 당첨 확률: 1/{total_combinations:,} = {original_prob:.10f}")
    print(f"   - 필터 후 확률: 1/{total_combinations-draws_so_far:,} = {filtered_prob:.10f}")
    print(f"   - 확률 개선: {improvement:.6f}%")
    
    # 이 프로그램의 필터링 분석
    print(f"\n4. 현재 시스템의 필터링 분석")
    
    filtered_remaining = 7_045_722  # 필터 후 남은 조합
    excluded_by_filters = total_combinations - filtered_remaining
    
    print(f"   - 필터로 제외된 조합: {excluded_by_filters:,}개")
    print(f"   - 남은 조합: {filtered_remaining:,}개")
    
    # 문제점 분석
    print(f"\n5. 핵심 문제")
    
    print(f"""
   문제 1: 과도한 제외
   - match 필터가 제외하는 {draws_so_far}개 << 전체 필터가 제외하는 {excluded_by_filters:,}개
   - 불필요하게 {excluded_by_filters - draws_so_far:,}개를 더 제외함
   
   문제 2: 통계적 근거 부족
   - "연속 4개 이상 제외" -> 하지만 언젠가는 나올 수 있음
   - "홀수 6개 제외" -> 확률은 낮지만 가능함
   
   문제 3: 확률 개선 미미
   - {improvement:.6f}% 개선은 사실상 무의미
   - 1억원 어치 사도 당첨 확률 1.2%
    """)
    
    # 올바른 접근법
    print(f"\n6. 올바른 접근법")
    print(f"""
   A. Match 필터만 사용 (수학적으로 타당)
      - 기존 {draws_so_far:,}개 조합만 제외
      - 확률 개선: {improvement:.6f}%
   
   B. 극단값 필터만 추가 (합리적)
      - 합계 < 21 또는 > 252 (불가능)
      - 연속 6개 (1,2,3,4,5,6)
      - 이론적 근거가 있는 것만
   
   C. 나머지는 모두 가능
      - 홀수 6개도 가능 (P=1.5%)
      - 연속 4개도 가능 (P=0.5%)
      - 모든 조합은 동등한 확률
    """)
    
    # 추가 분석: 얼마나 기다려야 중복이 나올까?
    print(f"\n7. 중복 예상 시점")
    
    # Birthday Paradox 응용
    # P(중복) >= 0.5가 되는 시점
    n = 1
    while True:
        prob_no_dup = 1
        for i in range(n):
            prob_no_dup *= (total_combinations - i) / total_combinations
        prob_dup = 1 - prob_no_dup
        if prob_dup >= 0.5:
            break
        n += 1
    
    print(f"   - 50% 확률로 중복 발생: 약 {n:,}회 추첨 후")
    print(f"   - 현재 {draws_so_far:,}회 -> 중복 확률 {(1 - math.exp(-draws_so_far**2 / (2*total_combinations)))*100:.2f}%")
    print(f"   - 매주 1회 추첨 시: 약 {n//52:,}년 후 첫 중복 예상")
    
    # 결론
    print(f"\n8. 결론")
    print(f"""
   [O] 맞는 부분:
   - 기존 조합 제외는 수학적으로 타당
   - 확률이 아주 약간 개선됨 (0.014%)
   
   [X] 틀린 부분:
   - 다른 필터들은 과도하고 근거 부족
   - 복잡한 ML/AI는 무의미
   - 개선 효과가 너무 미미함
   
   [TIP] 현실적 조언:
   - 단순히 기존 {draws_so_far:,}개만 제외하면 충분
   - 나머지는 모두 동일한 확률
   - 복잡한 시스템은 불필요
    """)


def calculate_real_improvement():
    """실제 개선 효과 계산"""
    print("\n" + "="*60)
    print("실제 개선 효과 시뮬레이션")
    print("="*60)
    
    total = 8_145_060
    excluded = 1_172
    
    # 1게임 구매
    print("\n1게임 구매 시:")
    print(f"   일반: 1/{total:,} = 0.0000123%")
    print(f"   개선: 1/{total-excluded:,} = 0.0000124%")
    
    # 1000게임 구매 (100만원)
    games = 1000
    normal_prob = 1 - (1 - 1/total)**games
    improved_prob = 1 - (1 - 1/(total-excluded))**games
    
    print(f"\n1,000게임 구매 시 (100만원):")
    print(f"   일반: {normal_prob*100:.6f}%")
    print(f"   개선: {improved_prob*100:.6f}%")
    print(f"   차이: {(improved_prob-normal_prob)*100:.8f}%p")
    
    # 10만 게임 (1억원)
    games = 100_000
    normal_prob = 1 - (1 - 1/total)**games
    improved_prob = 1 - (1 - 1/(total-excluded))**games
    
    print(f"\n100,000게임 구매 시 (1억원):")
    print(f"   일반: {normal_prob*100:.4f}%")
    print(f"   개선: {improved_prob*100:.4f}%")
    print(f"   차이: {(improved_prob-normal_prob)*100:.6f}%p")
    
    print("\n결론: 1억원을 써도 0.17%p 개선... 사실상 무의미")


if __name__ == "__main__":
    analyze_duplicate_probability()
    calculate_real_improvement()