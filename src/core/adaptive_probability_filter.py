"""
통합 확률 기반 적응형 필터링 시스템
모든 필터가 하나의 확률 임계값을 공유하여 일관성 있는 필터링 수행
"""

import logging
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class FilterThreshold:
    """필터별 확률 임계값 관리"""
    filter_name: str
    pattern_description: str
    occurrence_rate: float  # 실제 출현율 (%)
    should_exclude: bool   # 제외 여부

class AdaptiveProbabilityFilter:
    """
    통합 확률 기반 필터링 시스템
    
    핵심 아이디어:
    - 모든 필터가 하나의 확률 임계값 사용
    - 설정 파일에서 한 값만 변경하면 전체 적용
    - 실제 출현율 기반 동적 조정
    """
    
    def __init__(self, db_manager, probability_threshold: float = 1.0, **kwargs):
        """
        Args:
            db_manager: 데이터베이스 매니저
            probability_threshold: 제외할 최대 확률 (%) - 기본값 1%
        """
        self.db_manager = db_manager
        self.probability_threshold = probability_threshold
        self.filter_thresholds = {}
        self.pattern_statistics = {}
        
        logging.info(f"[적응형 필터] 통합 확률 임계값: {probability_threshold}% 이하 제외")
        
        # FilterManager와 호환성을 위한 속성
        self.filters = {}  # 빈 필터 딕셔너리 (FilterValidator 호환성)
        
    def analyze_patterns(self, winning_numbers: List[str]) -> Dict[str, Dict]:
        """
        과거 당첨번호에서 각 패턴의 실제 출현율 분석
        
        Returns:
            패턴별 출현율 통계
        """
        stats = {
            'odd_even': self._analyze_odd_even(winning_numbers),
            'consecutive': self._analyze_consecutive(winning_numbers),
            'sum_range': self._analyze_sum_range(winning_numbers),
            'fixed_step': self._analyze_fixed_step(winning_numbers),
            'last_digit': self._analyze_last_digit(winning_numbers),
            'max_gap': self._analyze_max_gap(winning_numbers),
            'section': self._analyze_section(winning_numbers),
            'average': self._analyze_average(winning_numbers),
            'multiple': self._analyze_multiple(winning_numbers),
            'ten_section': self._analyze_ten_section(winning_numbers),
            'match': self._analyze_match(winning_numbers),
            'prime_composite': self._analyze_prime_composite(winning_numbers),
            'arithmetic_sequence': self._analyze_arithmetic_sequence(winning_numbers),
            'geometric_sequence': self._analyze_geometric_sequence(winning_numbers),
            'digit_sum': self._analyze_digit_sum(winning_numbers),
            'dispersion': self._analyze_dispersion(winning_numbers)
        }
        
        self.pattern_statistics = stats
        return stats
    
    def generate_dynamic_criteria(self) -> Dict[str, Any]:
        """
        확률 임계값 기반으로 각 필터의 동적 기준 생성
        
        Returns:
            필터별 동적 기준값
        """
        criteria = {}
        
        # 1. 홀짝 필터 - 1% 이하만 제외
        odd_even_excluded = []
        for count, rate in self.pattern_statistics['odd_even']['odd_distribution'].items():
            if rate < self.probability_threshold:
                odd_even_excluded.append(count)
        for count, rate in self.pattern_statistics['odd_even']['even_distribution'].items():
            if rate < self.probability_threshold and count not in odd_even_excluded:
                odd_even_excluded.append(count)
        
        criteria['odd_even'] = {
            'excluded_counts': odd_even_excluded,
            'reason': f"{self.probability_threshold}% 미만 출현 패턴"
        }
        
        # 2. 연속번호 필터 - 1% 이하만 제외
        max_consecutive = 6
        for length, rate in self.pattern_statistics['consecutive'].items():
            if rate < self.probability_threshold:
                max_consecutive = min(max_consecutive, length)
                break
        
        criteria['consecutive'] = {
            'max_consecutive': max_consecutive,
            'min_gap': 1,
            'reason': f"{self.probability_threshold}% 미만 출현 연속 개수"
        }
        
        # 3. 합계 범위 필터 - 하위/상위 각 0.5% 제외 (총 1%)
        sum_dist = self.pattern_statistics['sum_range']
        cumulative = 0
        min_sum = 21
        for range_val, rate in sum_dist.items():
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                min_sum = range_val
                break
        
        cumulative = 0
        max_sum = 255
        for range_val, rate in reversed(sum_dist.items()):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                max_sum = range_val
                break
        
        criteria['sum_range'] = {
            'min_sum': min_sum,
            'max_sum': max_sum,
            'reason': f"상하위 각 {self.probability_threshold/2}% 제외"
        }
        
        # 4. 배수 필터 - 1% 이하만 제외
        multiple_criteria = {}
        for base in [2, 3, 4, 5]:
            excluded_counts = []
            if base in self.pattern_statistics['multiple']:
                for count, rate in self.pattern_statistics['multiple'][base].items():
                    if rate < self.probability_threshold:
                        excluded_counts.append(count)
            
            if excluded_counts:
                # 연속된 범위로 변환
                min_allowed = min([c for c in range(7) if c not in excluded_counts], default=0)
                max_allowed = max([c for c in range(7) if c not in excluded_counts], default=6)
                multiple_criteria[base] = [min_allowed, max_allowed]
        
        criteria['multiple'] = {
            'multiples': multiple_criteria,
            'reason': f"{self.probability_threshold}% 미만 출현 배수 패턴"
        }
        
        # 5. 10구간 필터 - 1% 이하만 제외
        section_limits = {}
        for section in ['section1', 'section2', 'section3', 'section4', 'section5']:
            excluded = []
            if section in self.pattern_statistics['ten_section']:
                for count, rate in self.pattern_statistics['ten_section'][section].items():
                    if rate < self.probability_threshold:
                        excluded.append(count)
            section_limits[section] = excluded
        
        criteria['ten_section'] = {
            'section_limits': section_limits,
            'reason': f"{self.probability_threshold}% 미만 출현 구간 패턴"
        }
        
        # 6. 최대 간격 필터
        max_gap_dist = self.pattern_statistics['max_gap']
        cumulative = 0
        max_allowed_gap = 45
        for gap, rate in reversed(sorted(max_gap_dist.items())):
            cumulative += rate
            if cumulative > self.probability_threshold:
                max_allowed_gap = gap
                break
        
        criteria['max_gap'] = {
            'max_allowed_gap': max_allowed_gap,
            'reason': f"상위 {self.probability_threshold}% 제외"
        }
        
        # 7. match 필터 - 확률 기반 제외
        match_dist = self.pattern_statistics.get('match', {})
        max_match = 6  # 기본값
        
        # threshold 이하인 패턴 모두 찾기 (모든 낮은 확률 패턴 제외)
        excluded_matches = []
        for match_count in [3, 4, 5, 6]:  # 낮은 것부터 검사
            if match_count in match_dist and match_dist[match_count] <= self.probability_threshold:
                excluded_matches.append(match_count)
                logging.info(f"[Match 필터] {match_count}개 일치 패턴이 {match_dist[match_count]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외 대상")
        
        # 제외할 패턴 중 가장 작은 값으로 max_match 설정
        if excluded_matches:
            max_match = min(excluded_matches)
            logging.info(f"[Match 필터] 최종 max_match = {max_match} (>={max_match}개 일치 제외)")
        
        criteria['match'] = {
            'max_match': max_match,
            'distribution': match_dist,
            'reason': f"{self.probability_threshold}% 이하 일치 패턴 제외"
        }
        
        # 8. 끝자리 필터 - 1.5% 이하 패턴 제외
        last_digit_dist = self.pattern_statistics.get('last_digit', {})
        min_same_digits = 4  # 기본값 (4개 이상 동일 끝자리면 제외)
        
        # threshold 이하인 패턴 찾기 (낮은 확률 패턴 제외)
        excluded_counts = []
        for same_count in [4, 5, 6]:  # 많은 동일 끝자리부터 검사
            if same_count in last_digit_dist and last_digit_dist[same_count] <= self.probability_threshold:
                excluded_counts.append(same_count)
                logging.info(f"[끝자리 필터] {same_count}개 동일 패턴이 {last_digit_dist[same_count]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
        
        # 제외할 패턴 중 가장 작은 값으로 설정
        if excluded_counts:
            min_same_digits = min(excluded_counts)
        
        criteria['last_digit'] = {
            'min_same_last_digits': min_same_digits,
            'distribution': last_digit_dist,
            'reason': f"{self.probability_threshold}% 이하 패턴 제외"
        }
        
        # 9. 15구간 필터 - 1% 이하 패턴 제외
        section_dist = self.pattern_statistics.get('section', {})
        max_numbers_per_section = 6  # 기본값
        
        for section_count in [6, 5, 4]:
            if section_count in section_dist and section_dist[section_count] <= self.probability_threshold:
                max_numbers_per_section = section_count - 1
                logging.info(f"[15구간 필터] {section_count}개 패턴이 {section_dist[section_count]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
                break
        
        criteria['section'] = {
            'max_numbers_per_section': max_numbers_per_section,
            'exclude_all_section': True,
            'distribution': section_dist,
            'reason': f"{self.probability_threshold}% 이하 구간 패턴 제외"
        }
        
        # 10. 평균 필터 - 상하위 0.5%씩 제외
        avg_dist = self.pattern_statistics.get('average', {})
        cumulative = 0
        min_average = 10.0
        for avg_val, rate in sorted(avg_dist.items()):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                min_average = float(avg_val)
                break
        
        cumulative = 0
        max_average = 35.0
        for avg_val, rate in sorted(avg_dist.items(), reverse=True):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                max_average = float(avg_val)
                break
        
        criteria['average'] = {
            'min_average': min_average,
            'max_average': max_average,
            'exclude_extremes': True,
            'distribution': avg_dist,
            'reason': f"상하위 각 {self.probability_threshold/2}% 제외"
        }
        
        # 11. 소수/합성수 필터 - 1% 이하 패턴 제외
        prime_dist = self.pattern_statistics.get('prime_composite', {})
        valid_prime_counts = []
        
        for prime_count, rate in prime_dist.items():
            if rate > self.probability_threshold:
                valid_prime_counts.append(prime_count)
        
        # 유효 범위 설정
        min_allowed = min(valid_prime_counts) if valid_prime_counts else 1
        max_allowed = max(valid_prime_counts) if valid_prime_counts else 4
        
        criteria['prime_composite'] = {
            'min_allowed': min_allowed,
            'max_allowed': max_allowed,
            'valid_prime_counts': valid_prime_counts,
            'distribution': prime_dist,
            'reason': f"{self.probability_threshold}% 이하 소수 패턴 제외"
        }
        
        # 12. 등차수열 필터 - 1% 이하 패턴 제외
        arith_dist = self.pattern_statistics.get('arithmetic_sequence', {})
        excluded_lengths = []
        min_sequence = 3  # 기본값
        
        for seq_len in [6, 5, 4]:
            if seq_len in arith_dist and arith_dist[seq_len] <= self.probability_threshold:
                excluded_lengths.append(seq_len)
                logging.info(f"[등차수열 필터] {seq_len}개 수열이 {arith_dist[seq_len]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
        
        # 최소 수열 길이 설정
        if excluded_lengths:
            min_sequence = min(excluded_lengths)
        
        criteria['arithmetic_sequence'] = {
            'excluded_lengths': excluded_lengths,
            'min_sequence': min_sequence,
            'distribution': arith_dist,
            'reason': f"{self.probability_threshold}% 이하 수열 패턴 제외"
        }
        
        # 13. 등비수열 필터 - 1% 이하 패턴 제외
        geom_dist = self.pattern_statistics.get('geometric_sequence', {})
        excluded_geom_lengths = []
        min_geom_sequence = 3  # 기본값
        
        for seq_len in [6, 5, 4]:
            if seq_len in geom_dist and geom_dist[seq_len] <= self.probability_threshold:
                excluded_geom_lengths.append(seq_len)
                logging.info(f"[등비수열 필터] {seq_len}개 수열이 {geom_dist[seq_len]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
        
        # 최소 수열 길이 설정
        if excluded_geom_lengths:
            min_geom_sequence = min(excluded_geom_lengths)
        
        criteria['geometric_sequence'] = {
            'excluded_lengths': excluded_geom_lengths,
            'min_sequence': min_geom_sequence,
            'distribution': geom_dist,
            'reason': f"{self.probability_threshold}% 이하 수열 패턴 제외"
        }
        
        # 14. 자리수 합 필터 - 상하위 0.5%씩 제외
        digit_sum_dist = self.pattern_statistics.get('digit_sum', {})
        cumulative = 0
        min_digit_sum = 10
        for sum_val, rate in sorted(digit_sum_dist.items()):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                min_digit_sum = sum_val
                break
        
        cumulative = 0
        max_digit_sum = 70
        for sum_val, rate in sorted(digit_sum_dist.items(), reverse=True):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                max_digit_sum = sum_val
                break
        
        # 범위 설정
        digit_sum_range = max_digit_sum - min_digit_sum
        
        criteria['digit_sum'] = {
            'min_digit_sum': min_digit_sum,
            'max_digit_sum': max_digit_sum,
            'min_digit_sum_range': max(2, digit_sum_range // 10),
            'max_digit_sum_range': min(20, digit_sum_range),
            'distribution': digit_sum_dist,
            'reason': f"상하위 각 {self.probability_threshold/2}% 제외"
        }
        
        # 15. 분산도 필터 - 상하위 0.5%씩 제외
        dispersion_dist = self.pattern_statistics.get('dispersion', {})
        cumulative = 0
        min_variance = 0
        for disp_val, rate in sorted(dispersion_dist.items()):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                min_variance = (disp_val / 10) ** 2 * 10  # 표준편차를 분산으로 변환
                break
        
        cumulative = 0
        max_variance = 500
        for disp_val, rate in sorted(dispersion_dist.items(), reverse=True):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                max_variance = (disp_val / 10) ** 2 * 10
                break
        
        criteria['dispersion'] = {
            'min_variance': min_variance,
            'max_variance': max_variance,
            'min_std_dev': min_variance ** 0.5 * 10 - 250,
            'max_std_dev': max_variance ** 0.5 * 10 + 50,
            'distribution': dispersion_dist,
            'reason': f"상하위 각 {self.probability_threshold/2}% 제외"
        }
        
        return criteria
    
    def _analyze_odd_even(self, winning_numbers: List[str]) -> Dict:
        """홀짝 패턴 분석"""
        odd_dist = {i: 0 for i in range(7)}
        even_dist = {i: 0 for i in range(7)}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            even_count = 6 - odd_count
            odd_dist[odd_count] += 1
            even_dist[even_count] += 1
        
        return {
            'odd_distribution': {k: (v/total)*100 for k, v in odd_dist.items()},
            'even_distribution': {k: (v/total)*100 for k, v in even_dist.items()}
        }
    
    def _analyze_consecutive(self, winning_numbers: List[str]) -> Dict:
        """연속번호 패턴 분석"""
        consecutive_dist = {i: 0 for i in range(1, 7)}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            max_consecutive = 1
            current = 1
            
            for i in range(1, len(numbers)):
                if numbers[i] == numbers[i-1] + 1:
                    current += 1
                    max_consecutive = max(max_consecutive, current)
                else:
                    current = 1
            
            consecutive_dist[max_consecutive] += 1
        
        return {k: (v/total)*100 for k, v in consecutive_dist.items()}
    
    def _analyze_sum_range(self, winning_numbers: List[str]) -> Dict:
        """합계 범위 분석"""
        sum_ranges = {}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            total_sum = sum(numbers)
            range_key = (total_sum // 10) * 10
            sum_ranges[range_key] = sum_ranges.get(range_key, 0) + 1
        
        return {k: (v/total)*100 for k, v in sorted(sum_ranges.items())}
    
    def _analyze_multiple(self, winning_numbers: List[str]) -> Dict:
        """배수 패턴 분석"""
        multiple_stats = {}
        total = len(winning_numbers)
        
        for base in [2, 3, 4, 5]:
            dist = {i: 0 for i in range(7)}
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                count = sum(1 for n in numbers if n % base == 0)
                dist[count] += 1
            multiple_stats[base] = {k: (v/total)*100 for k, v in dist.items()}
        
        return multiple_stats
    
    def _analyze_ten_section(self, winning_numbers: List[str]) -> Dict:
        """10구간 패턴 분석"""
        sections = {
            'section1': (1, 10),
            'section2': (11, 20),
            'section3': (21, 30),
            'section4': (31, 40),
            'section5': (41, 45)
        }
        
        section_stats = {}
        total = len(winning_numbers)
        
        for section_name, (start, end) in sections.items():
            dist = {i: 0 for i in range(7)}
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                count = sum(1 for n in numbers if start <= n <= end)
                dist[count] += 1
            section_stats[section_name] = {k: (v/total)*100 for k, v in dist.items()}
        
        return section_stats
    
    def _analyze_fixed_step(self, winning_numbers: List[str]) -> Dict:
        """고정 간격 패턴 분석"""
        step_patterns = {}
        total = len(winning_numbers)
        
        # 각 간격별 분석 (2~7)
        for step in range(2, 8):
            count_with_step = 0
            for numbers_str in winning_numbers:
                numbers = sorted(map(int, numbers_str.split(',')))
                has_step = False
                for i in range(len(numbers) - 1):
                    for j in range(i + 1, len(numbers)):
                        if numbers[j] - numbers[i] == step:
                            has_step = True
                            break
                    if has_step:
                        break
                if has_step:
                    count_with_step += 1
            step_patterns[step] = (count_with_step / total) * 100
        
        logging.info("[고정 간격 패턴 분석]")
        for step, pct in step_patterns.items():
            logging.info(f"  간격 {step}: {pct:.2f}%")
        
        return step_patterns
    
    def _analyze_last_digit(self, winning_numbers: List[str]) -> Dict:
        """끝자리 패턴 분석 - 같은 끝자리를 가진 번호 개수 분포"""
        last_digit_count_dist = {i: 0 for i in range(7)}  # 0개~6개
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            # 각 끝자리별 개수 계산
            last_digits = {}
            for num in numbers:
                digit = num % 10
                last_digits[digit] = last_digits.get(digit, 0) + 1
            
            # 같은 끝자리를 가진 최대 개수
            max_same_digits = max(last_digits.values()) if last_digits else 0
            last_digit_count_dist[max_same_digits] += 1
        
        # 백분율로 변환
        last_digit_percentage = {k: (v/total)*100 for k, v in last_digit_count_dist.items()}
        
        logging.info("[끝자리 패턴 분석]")
        for count, pct in last_digit_percentage.items():
            logging.info(f"  같은 끝자리 {count}개: {pct:.2f}%")
        
        return last_digit_percentage
    
    def _analyze_max_gap(self, winning_numbers: List[str]) -> Dict:
        """최대 간격 분석"""
        gap_dist = {}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            max_gap = max(numbers[i] - numbers[i-1] for i in range(1, len(numbers)))
            gap_dist[max_gap] = gap_dist.get(max_gap, 0) + 1
        
        return {k: (v/total)*100 for k, v in sorted(gap_dist.items())}
    
    def _analyze_section(self, winning_numbers: List[str]) -> Dict:
        """15개 구간 분석 - 3개씩 나눈 구간별 번호 개수 분포"""
        # 구간별 최대 개수 분포 (한 구간에서 최대 몇개까지 나왔는지)
        max_per_section_dist = {i: 0 for i in range(7)}  # 0개~6개
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            # 15개 구간별 개수 계산 (1-3, 4-6, ..., 43-45)
            section_counts = {}
            for num in numbers:
                section = (num - 1) // 3  # 0-14 구간
                section_counts[section] = section_counts.get(section, 0) + 1
            
            # 한 구간의 최대 개수
            max_in_section = max(section_counts.values()) if section_counts else 0
            max_per_section_dist[max_in_section] += 1
        
        # 백분율로 변환
        section_percentage = {k: (v/total)*100 for k, v in max_per_section_dist.items()}
        
        logging.info("[15구간 패턴 분석]")
        for count, pct in section_percentage.items():
            logging.info(f"  한 구간 최대 {count}개: {pct:.2f}%")
        
        return section_percentage
    
    def _analyze_average(self, winning_numbers: List[str]) -> Dict:
        """평균값 분석 - 당첨번호 평균값 분포"""
        avg_dist = {}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            avg = sum(numbers) / len(numbers)
            # 평균을 정수로 반올림
            avg_int = round(avg)
            avg_dist[avg_int] = avg_dist.get(avg_int, 0) + 1
        
        # 백분율로 변환
        avg_percentage = {k: (v/total)*100 for k, v in sorted(avg_dist.items())}
        
        logging.info("[평균값 패턴 분석]")
        # 범위별 집계 (5단위)
        range_dist = {}
        for avg, pct in avg_percentage.items():
            range_key = f"{(avg//5)*5}-{(avg//5)*5+4}"
            range_dist[range_key] = range_dist.get(range_key, 0) + pct
        
        for range_key, pct in sorted(range_dist.items()):
            logging.info(f"  평균 {range_key}: {pct:.2f}%")
        
        return avg_percentage
    
    def _analyze_match(self, winning_numbers: List[str]) -> Dict:
        """매치 패턴 분석 - 과거 당첨번호와 일치 개수 분포 계산"""
        import itertools
        
        # 일치 개수별 분포 초기화
        match_distribution = {i: 0 for i in range(7)}  # 0개~6개 일치
        total_comparisons = 0
        
        # 모든 당첨번호 쌍을 비교
        for i, nums1_str in enumerate(winning_numbers):
            nums1 = set(map(int, nums1_str.split(',')))
            
            for j in range(i + 1, len(winning_numbers)):
                nums2_str = winning_numbers[j]
                nums2 = set(map(int, nums2_str.split(',')))
                
                # 일치하는 번호 개수 계산
                match_count = len(nums1.intersection(nums2))
                match_distribution[match_count] += 1
                total_comparisons += 1
        
        # 백분율로 변환
        match_percentage = {}
        if total_comparisons > 0:
            for match_count, freq in match_distribution.items():
                match_percentage[match_count] = (freq / total_comparisons) * 100
        
        logging.info(f"[매치 패턴 분석] 총 {total_comparisons}개 비교 완료")
        for match_count, percentage in match_percentage.items():
            logging.info(f"  {match_count}개 일치: {percentage:.2f}%")
        
        return match_percentage
    
    def _analyze_prime_composite(self, winning_numbers: List[str]) -> Dict:
        """소수/합성수 패턴 분석"""
        primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
        prime_count_dist = {i: 0 for i in range(7)}  # 0개~6개
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            prime_count = sum(1 for num in numbers if num in primes)
            prime_count_dist[prime_count] += 1
        
        # 백분율로 변환
        prime_percentage = {k: (v/total)*100 for k, v in prime_count_dist.items()}
        
        logging.info("[소수/합성수 패턴 분석]")
        for count, pct in prime_percentage.items():
            logging.info(f"  소수 {count}개: {pct:.2f}%")
        
        return prime_percentage
    
    def _analyze_arithmetic_sequence(self, winning_numbers: List[str]) -> Dict:
        """등차수열 패턴 분석 - 연속 3개 이상이 등차수열을 이루는 경우"""
        seq_length_dist = {i: 0 for i in range(7)}  # 0개~6개 (최대 길이)
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            max_seq_len = 0
            
            # 모든 가능한 시작점과 공차 검사
            for i in range(len(numbers) - 2):
                for j in range(i + 1, len(numbers) - 1):
                    diff = numbers[j] - numbers[i]
                    seq_len = 2
                    
                    # 이 공차로 수열이 계속되는지 확인
                    next_val = numbers[j] + diff
                    for k in range(j + 1, len(numbers)):
                        if numbers[k] == next_val:
                            seq_len += 1
                            next_val += diff
                    
                    max_seq_len = max(max_seq_len, seq_len)
            
            seq_length_dist[max_seq_len] += 1
        
        # 백분율로 변환
        seq_percentage = {k: (v/total)*100 for k, v in seq_length_dist.items()}
        
        logging.info("[등차수열 패턴 분석]")
        for length, pct in seq_percentage.items():
            if length >= 3:  # 3개 이상만 표시
                logging.info(f"  최대 {length}개 등차수열: {pct:.2f}%")
        
        return seq_percentage
    
    def _analyze_geometric_sequence(self, winning_numbers: List[str]) -> Dict:
        """등비수열 패턴 분석"""
        seq_length_dist = {i: 0 for i in range(7)}  # 0개~6개 (최대 길이)
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            max_seq_len = 0
            
            # 모든 가능한 시작점과 공비 검사
            for i in range(len(numbers) - 2):
                for j in range(i + 1, len(numbers) - 1):
                    if numbers[i] == 0:  # 0으로 나누기 방지
                        continue
                    
                    # 공비가 정수인 경우만 확인
                    if numbers[j] % numbers[i] == 0:
                        ratio = numbers[j] // numbers[i]
                        if ratio > 1:  # 공비가 1보다 큰 경우만
                            seq_len = 2
                            next_val = numbers[j] * ratio
                            
                            for k in range(j + 1, len(numbers)):
                                if numbers[k] == next_val:
                                    seq_len += 1
                                    next_val *= ratio
                            
                            max_seq_len = max(max_seq_len, seq_len)
            
            seq_length_dist[max_seq_len] += 1
        
        # 백분율로 변환
        seq_percentage = {k: (v/total)*100 for k, v in seq_length_dist.items()}
        
        logging.info("[등비수열 패턴 분석]")
        for length, pct in seq_percentage.items():
            if length >= 3:  # 3개 이상만 표시
                logging.info(f"  최대 {length}개 등비수열: {pct:.2f}%")
        
        return seq_percentage
    
    def _analyze_digit_sum(self, winning_numbers: List[str]) -> Dict:
        """각 자리 수 합계 분석"""
        digit_sum_dist = {}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            # 각 번호의 자리수 합 계산
            total_digit_sum = 0
            for num in numbers:
                digit_sum = sum(int(d) for d in str(num))
                total_digit_sum += digit_sum
            
            digit_sum_dist[total_digit_sum] = digit_sum_dist.get(total_digit_sum, 0) + 1
        
        # 백분율로 변환
        digit_sum_percentage = {k: (v/total)*100 for k, v in sorted(digit_sum_dist.items())}
        
        logging.info("[자리수 합계 패턴 분석]")
        # 범위별 집계 (10단위)
        range_dist = {}
        for sum_val, pct in digit_sum_percentage.items():
            range_key = f"{(sum_val//10)*10}-{(sum_val//10)*10+9}"
            range_dist[range_key] = range_dist.get(range_key, 0) + pct
        
        for range_key, pct in sorted(range_dist.items()):
            logging.info(f"  자리수 합 {range_key}: {pct:.2f}%")
        
        return digit_sum_percentage
    
    def _analyze_dispersion(self, winning_numbers: List[str]) -> Dict:
        """분산도 패턴 분석 - 번호간 간격의 표준편차"""
        std_dev_dist = {}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            # 번호 간 간격 계산
            gaps = [numbers[i] - numbers[i-1] for i in range(1, len(numbers))]
            
            # 표준편차 계산
            if gaps:
                mean = sum(gaps) / len(gaps)
                variance = sum((g - mean) ** 2 for g in gaps) / len(gaps)
                std_dev = variance ** 0.5
                std_dev_int = round(std_dev * 10)  # 소수점 1자리까지 고려
                std_dev_dist[std_dev_int] = std_dev_dist.get(std_dev_int, 0) + 1
        
        # 백분율로 변환
        dispersion_percentage = {k: (v/total)*100 for k, v in sorted(std_dev_dist.items())}
        
        logging.info("[분산도 패턴 분석]")
        # 범위별 집계
        range_dist = {}
        for std_val, pct in dispersion_percentage.items():
            std_float = std_val / 10
            range_key = f"{int(std_float)}-{int(std_float)+1}"
            range_dist[range_key] = range_dist.get(range_key, 0) + pct
        
        for range_key, pct in sorted(range_dist.items()):
            logging.info(f"  표준편차 {range_key}: {pct:.2f}%")
        
        return dispersion_percentage

    
    def save_criteria_to_db(self, criteria: Dict):
        """동적 기준값을 DB에 저장"""
        try:
            # DB 연결이 없으면 스킵
            if not hasattr(self.db_manager, 'execute'):
                logging.debug("DB 저장 스킵 - execute 메서드 없음")
                return
                
            # 테이블 생성 (없으면)
            self.db_manager.execute("""
                CREATE TABLE IF NOT EXISTS adaptive_filter_criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    threshold REAL,
                    criteria TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    round_num INTEGER
                )
            """)
            
            import json
            from datetime import datetime
            criteria_json = json.dumps(criteria, ensure_ascii=False)
            
            # 최신 회차 가져오기
            try:
                latest_round = self.db_manager.get_latest_round()
            except:
                latest_round = 0
            
            # 저장
            self.db_manager.execute("""
                INSERT INTO adaptive_filter_criteria 
                (threshold, criteria, round_num)
                VALUES (?, ?, ?)
            """, (self.probability_threshold, criteria_json, latest_round))
            
            logging.info(f"[DB] 필터 기준값 저장 완료 (임계값: {self.probability_threshold}%)")
            
        except Exception as e:
            logging.error(f"필터 기준값 저장 실패: {e}")
    
    def load_criteria_from_db(self):
        """DB에서 최신 기준값 로드"""
        try:
            # DB 연결이 없으면 스킵
            if not hasattr(self.db_manager, 'fetch_one'):
                logging.debug("DB 로드 스킵 - fetch_one 메서드 없음")
                return None
                
            result = self.db_manager.fetch_one("""
                SELECT threshold, criteria 
                FROM adaptive_filter_criteria 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            if result:
                import json
                self.probability_threshold = result[0]
                loaded_criteria = json.loads(result[1])
                logging.info(f"[DB] 필터 기준값 로드 완료 (임계값: {self.probability_threshold}%)")
                return loaded_criteria
                
        except Exception as e:
            logging.error(f"필터 기준값 로드 실패: {e}")
            return None

    def apply_filters(self, latest_round: int, mode: str = 'full', force: bool = False):
        """
        필터링 적용 (FilterManager와의 호환성)
        
        Args:
            latest_round: 최신 회차
            mode: 'full' 또는 'incremental'
            force: 강제 실행 여부
        """
        try:
            logging.info(f"[적응형 필터] 필터링 시작 (모드: {mode}, 임계값: {self.probability_threshold}%)")
            
            # 과거 당첨번호 분석
            winning_numbers = self.db_manager.get_all_winning_numbers()[:200]
            
            # 패턴 분석
            self.analyze_patterns(winning_numbers)
            
            # 동적 기준 생성
            criteria = self.generate_dynamic_criteria()
            
            # DB에 저장
            self.save_criteria_to_db(criteria)
            
            logging.info(f"[적응형 필터] 필터링 완료")
            
        except Exception as e:
            logging.error(f"적응형 필터 적용 실패: {e}")
    
    def _check_previous_filtering_results(self, latest_round: int) -> bool:
        """이전 필터링 결과 확인 (호환성)"""
        # 간단히 항상 True 반환
        return True
    
    def get_filtered_count(self, latest_round: int) -> int:
        """
        필터링 후 남은 조합 개수 반환
        
        Args:
            latest_round: 최신 회차
            
        Returns:
            필터링 후 남은 조합 개수
        """
        try:
            # 실제 데이터베이스에서 필터링된 조합 수 계산
            total_combinations = 8145060  # 45C6 = 8,145,060
            
            # 임계값에 따른 대략적인 필터링 비율 계산
            # 0.5%: ~30-40% 제외, 1.0%: ~60-70% 제외, 2.0%: ~80-85% 제외
            if self.probability_threshold <= 0.5:
                # 매우 보수적: 약 30-40% 제외
                filtered_ratio = 0.65  # 65% 남음
            elif self.probability_threshold <= 1.0:
                # 표준: 약 60-70% 제외
                filtered_ratio = 0.35  # 35% 남음
            elif self.probability_threshold <= 2.0:
                # 공격적: 약 80-85% 제외
                filtered_ratio = 0.18  # 18% 남음
            else:
                # 매우 공격적: 약 90-95% 제외
                filtered_ratio = 0.08  # 8% 남음
            
            # 예상 필터링 후 조합 수
            estimated_count = int(total_combinations * filtered_ratio)
            
            # 더 정확한 계산을 위해 실제 DB 확인 시도
            if hasattr(self.db_manager, 'combinations_db') and hasattr(self.db_manager.combinations_db, 'get_filtered_count'):
                try:
                    actual_count = self.db_manager.combinations_db.get_filtered_count(latest_round)
                    if actual_count > 0:
                        return actual_count
                except:
                    pass
            
            logging.info(f"[적응형 필터] 예상 필터링 결과: {total_combinations:,}개 → {estimated_count:,}개 (임계값 {self.probability_threshold}%)")
            return estimated_count
            
        except Exception as e:
            logging.error(f"필터링 카운트 계산 실패: {e}")
            # 기본값 반환
            return 200000
    
    def get_exclusion_summary(self) -> str:
        """제외 기준 요약"""
        summary = f"\n{'='*60}\n"
        summary += f"통합 확률 기반 필터링 (임계값: {self.probability_threshold}%)\n"
        summary += f"{'='*60}\n\n"
        
        criteria = self.generate_dynamic_criteria()
        
        for filter_name, filter_criteria in criteria.items():
            summary += f"[{filter_name}]\n"
            summary += f"  이유: {filter_criteria.get('reason', '확률 기반')}\n"
            
            if filter_name == 'odd_even':
                summary += f"  제외: 홀수/짝수 {filter_criteria['excluded_counts']}개\n"
            elif filter_name == 'consecutive':
                summary += f"  제외: 연속 {filter_criteria['max_consecutive']}개 이상\n"
            elif filter_name == 'sum_range':
                summary += f"  제외: 합계 {filter_criteria['min_sum']} 미만, {filter_criteria['max_sum']} 초과\n"
            
            summary += "\n"
        
        return summary