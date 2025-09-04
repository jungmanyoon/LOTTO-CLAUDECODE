#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
로또 통계 검증 스크립트
1182회차까지의 로또 데이터 분석 통계를 전문가 관점에서 검증
"""

import sys
import os

# Windows 콘솔 한글 출력 설정
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
import sqlite3
import json
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Any

# 프로젝트 루트 디렉토리를 파이썬 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.db_manager import DatabaseManager
from src.core.pattern_manager import PatternManager
from src.logger import setup_logging

class LottoStatisticsAnalyzer:
    """로또 통계 분석 및 검증 클래스"""
    
    def __init__(self):
        """초기화"""
        # setup_logging() 제거 - main.py에서 이미 설정됨
        self.db_manager = DatabaseManager()
        # PatternManager는 현재 사용하지 않으므로 제거
        # self.pattern_manager = PatternManager(self.db_manager)
        self.winning_numbers = self._load_winning_numbers()
        logging.info(f"로또 통계 분석기 초기화 완료. 총 {len(self.winning_numbers)}회차 데이터 로드")
    
    def _load_winning_numbers(self) -> List[str]:
        """당첨 번호 로드"""
        try:
            with self.db_manager.lotto_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT numbers FROM lotto_numbers ORDER BY round')
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"당첨 번호 로드 실패: {str(e)}")
            return []
    
    def analyze_hot_cold_numbers(self, recent_rounds: int = 100) -> Dict[str, List]:
        """핫/콜드 넘버 분석
        
        Args:
            recent_rounds: 최근 몇 회차를 분석할지 (기본 100회차)
            
        Returns:
            Dict: 핫 넘버와 콜드 넘버 리스트
        """
        # 번호별 출현 빈도 계산
        number_frequency = defaultdict(int)
        
        # 최근 N회차 데이터만 사용
        recent_data = self.winning_numbers[-recent_rounds:] if len(self.winning_numbers) > recent_rounds else self.winning_numbers
        
        for numbers_str in recent_data:
            numbers = list(map(int, numbers_str.split(',')))
            for num in numbers:
                number_frequency[num] += 1
        
        # 모든 번호(1-45)에 대해 빈도 확인
        all_frequencies = []
        for num in range(1, 46):
            freq = number_frequency.get(num, 0)
            all_frequencies.append((num, freq))
        
        # 빈도순으로 정렬
        all_frequencies.sort(key=lambda x: x[1], reverse=True)
        
        # 핫 넘버 (상위 15개)
        hot_numbers = [(num, freq) for num, freq in all_frequencies[:15]]
        
        # 콜드 넘버 (하위 15개)
        cold_numbers = [(num, freq) for num, freq in all_frequencies[-15:]]
        cold_numbers.reverse()  # 가장 적게 나온 것부터 표시
        
        return {
            'hot_numbers': hot_numbers,
            'cold_numbers': cold_numbers,
            'analysis_rounds': len(recent_data)
        }
    
    def analyze_odd_even_distribution(self) -> Dict[str, float]:
        """홀짝 분포 분석"""
        odd_even_counts = defaultdict(int)
        total = len(self.winning_numbers)
        
        for numbers_str in self.winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            odd_count = sum(1 for num in numbers if num % 2 == 1)
            even_count = 6 - odd_count
            pattern = f"홀수{odd_count}/짝수{even_count}"
            odd_even_counts[pattern] += 1
        
        # 백분율 계산
        distribution = {}
        for pattern, count in odd_even_counts.items():
            percentage = (count / total) * 100
            distribution[pattern] = percentage
        
        return dict(sorted(distribution.items(), key=lambda x: x[1], reverse=True))
    
    def analyze_consecutive_patterns(self) -> Dict[str, float]:
        """연속 번호 패턴 분석"""
        consecutive_stats = defaultdict(int)
        total = len(self.winning_numbers)
        
        for numbers_str in self.winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            
            # 연속 번호 그룹 찾기
            consecutive_groups = []
            current_group = [numbers[0]]
            
            for i in range(1, len(numbers)):
                if numbers[i] == numbers[i-1] + 1:
                    current_group.append(numbers[i])
                else:
                    if len(current_group) > 1:
                        consecutive_groups.append(len(current_group))
                    current_group = [numbers[i]]
            
            if len(current_group) > 1:
                consecutive_groups.append(len(current_group))
            
            # 연속 번호 패턴 분류
            if not consecutive_groups:
                consecutive_stats['연속없음'] += 1
            else:
                # 가장 긴 연속
                max_consecutive = max(consecutive_groups)
                consecutive_stats[f'{max_consecutive}개연속'] += 1
        
        # 백분율 계산
        distribution = {}
        for pattern, count in consecutive_stats.items():
            percentage = (count / total) * 100
            distribution[pattern] = percentage
        
        return dict(sorted(distribution.items(), key=lambda x: x[0]))
    
    def analyze_fixed_interval_patterns(self) -> Dict[str, Dict[str, float]]:
        """고정 간격 패턴 분석"""
        interval_stats = {
            '3개_고정간격': defaultdict(int),
            '4개_고정간격': defaultdict(int),
            '5개_고정간격': defaultdict(int),
            '6개_고정간격': defaultdict(int)
        }
        total = len(self.winning_numbers)
        
        for numbers_str in self.winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            
            # 모든 가능한 간격 검사 (2~8)
            for interval in range(2, 9):
                # 각 시작점에서 고정 간격 패턴 찾기
                for start_idx in range(len(numbers)):
                    sequence = [numbers[start_idx]]
                    
                    for i in range(start_idx + 1, len(numbers)):
                        if numbers[i] - sequence[-1] == interval:
                            sequence.append(numbers[i])
                    
                    # 3개 이상의 고정 간격 패턴
                    if len(sequence) >= 3:
                        key = f'{len(sequence)}개_고정간격'
                        if key in interval_stats:
                            interval_stats[key][f'{interval}간격'] += 1
        
        # 백분율 계산
        result = {}
        for pattern_type, counts in interval_stats.items():
            result[pattern_type] = {}
            for interval, count in counts.items():
                percentage = (count / total) * 100
                result[pattern_type][interval] = percentage
        
        return result
    
    def analyze_arithmetic_sequence(self) -> Dict[int, float]:
        """등차수열 패턴 분석"""
        sequence_stats = defaultdict(int)
        total = len(self.winning_numbers)
        
        for numbers_str in self.winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            
            # 가장 긴 등차수열 찾기
            max_length = 0
            
            for i in range(len(numbers)):
                for j in range(i + 1, len(numbers)):
                    diff = numbers[j] - numbers[i]
                    sequence = [numbers[i], numbers[j]]
                    
                    # 다음 숫자들 확인
                    next_num = numbers[j] + diff
                    for k in range(j + 1, len(numbers)):
                        if numbers[k] == next_num:
                            sequence.append(numbers[k])
                            next_num += diff
                    
                    if len(sequence) >= 3:
                        max_length = max(max_length, len(sequence))
            
            if max_length >= 3:
                sequence_stats[f'{max_length}개_등차수열'] += 1
        
        # 백분율 계산
        distribution = {}
        for pattern, count in sequence_stats.items():
            percentage = (count / total) * 100
            distribution[pattern] = percentage
        
        return distribution
    
    def analyze_section_distribution(self) -> Dict[str, Dict[str, float]]:
        """구간별 분포 분석"""
        section_stats = defaultdict(lambda: defaultdict(int))
        total = len(self.winning_numbers)
        
        sections = [
            ('1-10구간', 1, 10),
            ('11-20구간', 11, 20),
            ('21-30구간', 21, 30),
            ('31-40구간', 31, 40),
            ('41-45구간', 41, 45)
        ]
        
        for numbers_str in self.winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            
            # 각 구간별 번호 개수 계산
            for section_name, start, end in sections:
                count = sum(1 for n in numbers if start <= n <= end)
                section_stats[section_name][f'{count}개'] += 1
        
        # 백분율 계산
        result = {}
        for section, counts in section_stats.items():
            result[section] = {}
            total_count = sum(counts.values())
            for count_str, freq in counts.items():
                percentage = (freq / total_count) * 100
                result[section][count_str] = percentage
        
        return result
    
    def analyze_ac_values(self) -> Dict[str, Any]:
        """AC값 (Arithmetic Complexity) 분석
        
        Returns:
            Dict: AC값 통계
        """
        ac_values = []
        
        for numbers_str in self.winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            ac = self._calculate_ac_value(numbers)
            ac_values.append(ac)
        
        # 통계 계산
        return {
            'avg': sum(ac_values) / len(ac_values) if ac_values else 0,
            'min': min(ac_values) if ac_values else 0,
            'max': max(ac_values) if ac_values else 0,
            'common_range': [
                sorted(ac_values)[int(len(ac_values) * 0.2)] if ac_values else 0,
                sorted(ac_values)[int(len(ac_values) * 0.8)] if ac_values else 0
            ],
            'distribution': self._get_ac_distribution(ac_values)
        }
    
    def _calculate_ac_value(self, numbers: List[int]) -> int:
        """AC값 계산 (Arithmetic Complexity)"""
        ac_set = set()
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                ac_set.add(numbers[j] - numbers[i])
        return len(ac_set)
    
    def _get_ac_distribution(self, ac_values: List[int]) -> Dict[int, float]:
        """AC값 분포 계산"""
        distribution = defaultdict(int)
        total = len(ac_values)
        
        for ac in ac_values:
            distribution[ac] += 1
        
        # 백분율로 변환
        return {
            ac: (count / total * 100)
            for ac, count in sorted(distribution.items())
        }
    
    def verify_statistics(self):
        """통계 검증 및 이상 여부 확인"""
        print("\n" + "="*70)
        print("로또 1182회차까지 통계 분석 검증 보고서")
        print("="*70)
        
        # 1. 홀짝 분포 검증
        print("\n[1. 홀짝 분포 분석]")
        odd_even_dist = self.analyze_odd_even_distribution()
        for pattern, percentage in list(odd_even_dist.items())[:5]:
            print(f"  {pattern}: {percentage:.2f}%")
        
        # 홀수3/짝수3 패턴 검증
        target_pattern = "홀수3/짝수3"
        if target_pattern in odd_even_dist:
            actual_percentage = odd_even_dist[target_pattern]
            print(f"\n  [검증] {target_pattern} = {actual_percentage:.2f}%")
            if 30 <= actual_percentage <= 40:
                print("  -> 정상 범위 (이론값: 31.25%, 실제값이 근사함)")
            else:
                print("  -> 주의: 이론값과 차이가 큼")
        
        # 2. 연속 번호 패턴 검증
        print("\n[2. 연속 번호 패턴 분석]")
        consecutive_dist = self.analyze_consecutive_patterns()
        for pattern, percentage in consecutive_dist.items():
            print(f"  {pattern}: {percentage:.2f}%")
        
        # 1개+2개 연속 합계 검증
        one_consecutive = consecutive_dist.get('연속없음', 0) + consecutive_dist.get('1개연속', 0)
        two_consecutive = consecutive_dist.get('2개연속', 0)
        total_percentage = one_consecutive + two_consecutive
        print(f"\n  [검증] 연속없음+2개연속 = {total_percentage:.2f}%")
        if 90 <= total_percentage <= 95:
            print("  -> 정상 범위 (대부분의 당첨번호가 작은 연속성을 가짐)")
        else:
            print("  -> 주의: 예상 범위를 벗어남")
        
        # 3. 고정 간격 패턴 검증
        print("\n[3. 고정 간격 패턴 분석]")
        interval_patterns = self.analyze_fixed_interval_patterns()
        
        # 6개 모두 고정 간격 검증
        six_interval = interval_patterns.get('6개_고정간격', {})
        total_six_interval = sum(six_interval.values())
        print(f"  6개 모두 고정 간격: {total_six_interval:.4f}%")
        if total_six_interval < 0.01:
            print("  -> 정상: 6개 모두 고정 간격은 극히 드물어야 함")
        else:
            print("  -> 주의: 예상보다 높은 빈도")
        
        # 4. 등차수열 패턴 검증
        print("\n[4. 등차수열 패턴 분석]")
        arithmetic_dist = self.analyze_arithmetic_sequence()
        for pattern, percentage in sorted(arithmetic_dist.items()):
            print(f"  {pattern}: {percentage:.2f}%")
        
        three_arithmetic = arithmetic_dist.get('3개_등차수열', 0)
        print(f"\n  [검증] 3개 연속 등차수열 = {three_arithmetic:.2f}%")
        if 40 <= three_arithmetic <= 50:
            print("  -> 정상 범위 (약 절반 정도의 당첨번호가 3개 등차수열을 포함)")
        else:
            print("  -> 주의: 예상 범위를 벗어남")
        
        # 5. 구간별 분포 균형성 검증
        print("\n[5. 구간별 분포 균형성 분석]")
        section_dist = self.analyze_section_distribution()
        
        # 각 구간의 평균 출현 개수 계산
        section_averages = {}
        for section, counts in section_dist.items():
            weighted_sum = sum(int(k[0]) * v for k, v in counts.items())
            total_percentage = sum(counts.values())
            average = weighted_sum / 100  # 백분율을 고려한 평균
            section_averages[section] = average
            print(f"  {section} 평균 출현: {average:.2f}개")
        
        # 균형성 검증
        values = list(section_averages.values())
        max_diff = max(values) - min(values)
        print(f"\n  [검증] 구간별 최대 차이 = {max_diff:.2f}개")
        if max_diff < 0.5:
            print("  -> 우수: 매우 균형잡힌 분포")
        elif max_diff < 1.0:
            print("  -> 정상: 적절한 균형성")
        else:
            print("  -> 주의: 구간별 편차가 큼")
        
        print("\n" + "="*70)
        print("검증 완료")
        print("="*70)

def main():
    """메인 실행 함수"""
    analyzer = LottoStatisticsAnalyzer()
    analyzer.verify_statistics()

if __name__ == "__main__":
    main()