"""필터 진단 및 최적화 스크립트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from itertools import combinations
import random

def analyze_average_filter():
    """평균값 필터 분석"""
    print("\n" + "="*60)
    print("평균값 필터 분석")
    print("="*60)
    
    # 로또 번호 1-45의 모든 6개 조합의 평균값 분포 분석
    # 샘플링으로 분석 (전체는 너무 많음)
    sample_size = 100000
    averages = []
    
    print(f"샘플 {sample_size:,}개 조합 생성 중...")
    for _ in range(sample_size):
        numbers = sorted(random.sample(range(1, 46), 6))
        avg = sum(numbers) / 6
        averages.append(avg)
    
    averages = np.array(averages)
    
    print(f"\n평균값 통계:")
    print(f"  최소값: {averages.min():.2f}")
    print(f"  최대값: {averages.max():.2f}")
    print(f"  중앙값: {np.median(averages):.2f}")
    print(f"  평균: {averages.mean():.2f}")
    print(f"  표준편차: {averages.std():.2f}")
    
    # 현재 설정 범위 분석
    min_avg = 10.5
    max_avg = 37.0
    
    in_range = ((averages >= min_avg) & (averages <= max_avg)).sum()
    out_range = sample_size - in_range
    
    print(f"\n현재 설정 (min: {min_avg}, max: {max_avg}):")
    print(f"  범위 내: {in_range:,}개 ({in_range/sample_size*100:.2f}%)")
    print(f"  범위 외: {out_range:,}개 ({out_range/sample_size*100:.2f}%)")
    
    # 권장 범위 계산 (평균 ± 2σ)
    recommended_min = averages.mean() - 2 * averages.std()
    recommended_max = averages.mean() + 2 * averages.std()
    
    print(f"\n권장 설정 (95% 포함):")
    print(f"  min_average: {recommended_min:.1f}")
    print(f"  max_average: {recommended_max:.1f}")
    
    # 다양한 범위별 포함률
    print(f"\n범위별 포함률 분석:")
    ranges = [
        (15, 32),  # 좁은 범위
        (12, 35),  # 중간 범위
        (10, 38),  # 넓은 범위
        (8, 40),   # 매우 넓은 범위
    ]
    
    for min_val, max_val in ranges:
        count = ((averages >= min_val) & (averages <= max_val)).sum()
        print(f"  [{min_val:2d}, {max_val:2d}]: {count/sample_size*100:5.2f}% 포함")

def analyze_consecutive_filter():
    """연속 번호 필터 분석"""
    print("\n" + "="*60)
    print("연속 번호 필터 분석")
    print("="*60)
    
    sample_size = 100000
    consecutive_counts = []
    
    print(f"샘플 {sample_size:,}개 조합 분석 중...")
    for _ in range(sample_size):
        numbers = sorted(random.sample(range(1, 46), 6))
        
        # 최대 연속 개수 계산
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(numbers)):
            if numbers[i] == numbers[i-1] + 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        consecutive_counts.append(max_consecutive)
    
    consecutive_counts = np.array(consecutive_counts)
    
    print("\n연속 번호 개수 분포:")
    for i in range(1, 7):
        count = (consecutive_counts == i).sum()
        print(f"  {i}개 연속: {count:,}개 ({count/sample_size*100:.2f}%)")
    
    # 현재 설정 (max_consecutive: 4)
    max_allowed = 4
    valid = (consecutive_counts <= max_allowed).sum()
    
    print(f"\n현재 설정 (max_consecutive: {max_allowed}):")
    print(f"  유효: {valid:,}개 ({valid/sample_size*100:.2f}%)")
    print(f"  제외: {sample_size-valid:,}개 ({(sample_size-valid)/sample_size*100:.2f}%)")

def recommend_filter_settings():
    """최적 필터 설정 권장"""
    print("\n" + "="*60)
    print("권장 필터 설정 (목표: 25-30% 제외)")
    print("="*60)
    
    recommendations = {
        "average": {
            "current": {"min": 10.5, "max": 37.0},
            "recommended": {"min": 12.0, "max": 35.0},
            "expected_exclusion": "약 20%"
        },
        "sum_range": {
            "current": {"min": 70, "max": 210},
            "recommended": {"min": 60, "max": 230},
            "expected_exclusion": "약 15%"
        },
        "consecutive": {
            "current": {"max": 4},
            "recommended": {"max": 3},
            "expected_exclusion": "약 5%"
        },
        "prime_composite": {
            "current": {"valid_counts": [1,2,3,4,5]},
            "recommended": {"valid_counts": [0,1,2,3,4,5,6]},
            "expected_exclusion": "약 0%"
        },
        "fixed_step": {
            "current": {"많은 스텝 제외"},
            "recommended": {"주요 패턴만 제외"},
            "expected_exclusion": "약 10%"
        }
    }
    
    total_expected = 0
    for filter_name, settings in recommendations.items():
        print(f"\n{filter_name} 필터:")
        print(f"  현재: {settings['current']}")
        print(f"  권장: {settings['recommended']}")
        print(f"  예상 제외율: {settings['expected_exclusion']}")
        
        # 제외율 숫자 추출
        exclusion = int(settings['expected_exclusion'].replace('약 ', '').replace('%', ''))
        total_expected += exclusion
    
    print(f"\n총 예상 제외율: 약 {total_expected}%")
    print(f"예상 남은 조합: 약 {int(8145060 * (100-total_expected)/100):,}개")

if __name__ == "__main__":
    analyze_average_filter()
    analyze_consecutive_filter()
    recommend_filter_settings()