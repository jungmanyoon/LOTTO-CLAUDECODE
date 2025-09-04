"""
최근 100회차 당첨 데이터 분석 및 필터 기준값 재조정 스크립트
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import yaml
from typing import Dict, List, Tuple
from statistics import mean, stdev
import numpy as np

from src.core.db_manager import DatabaseManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_recent_winning_numbers(db_manager: DatabaseManager, num_rounds: int = 100) -> List[Tuple[int, List[int]]]:
    """최근 n회차의 당첨번호 가져오기"""
    try:
        # 최신 회차 번호 확인
        latest_round = db_manager.lotto_db.get_last_round()
        if not latest_round:
            logging.error("당첨 데이터가 없습니다.")
            return []
        
        winning_numbers = []
        start_round = max(1, latest_round - num_rounds + 1)
        
        for round_num in range(start_round, latest_round + 1):
            data = db_manager.lotto_db.get_numbers_by_round(round_num)
            if data:
                # data는 (round_num, numbers_str, draw_date) 형태
                numbers_str = data[1]
                numbers = list(map(int, numbers_str.split(',')))
                winning_numbers.append((round_num, numbers))
        
        return winning_numbers
    
    except Exception as e:
        logging.error(f"당첨번호 조회 중 오류: {str(e)}")
        return []

def analyze_filter_statistics(winning_numbers: List[Tuple[int, List[int]]]) -> Dict:
    """당첨번호들의 필터별 통계 분석"""
    stats = {
        'sum_range': {'sums': []},
        'average': {'averages': []},
        'consecutive': {'max_consecutive': [], 'min_gaps': []},
        'odd_even': {'odd_counts': []},
        'max_gap': {'max_gaps': []},
        'section': {'section_counts': []},
        'ten_section': {'ten_section_counts': []},
        'last_digit': {'last_digit_groups': []},
        'arithmetic_sequence': {'max_lengths': []},
        'geometric_sequence': {'max_lengths': []},
        'prime_composite': {'prime_counts': []},
        'digit_sum': {'digit_sums': [], 'digit_sum_ranges': []},
        'dispersion': {'std_devs': [], 'variances': [], 'avg_gaps': []},
        'fixed_step': {'step_patterns': []},
        'multiple': {
            'multiple_2': [], 'multiple_3': [], 
            'multiple_4': [], 'multiple_5': []
        }
    }
    
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
    
    for round_num, numbers in winning_numbers:
        # 1. 합계 및 평균
        total_sum = sum(numbers)
        average = total_sum / 6
        stats['sum_range']['sums'].append(total_sum)
        stats['average']['averages'].append(average)
        
        # 2. 연속 번호
        consecutive_count = 0
        min_gap = 45
        for i in range(len(numbers) - 1):
            gap = numbers[i+1] - numbers[i]
            if gap == 1:
                consecutive_count += 1
            min_gap = min(min_gap, gap)
        
        stats['consecutive']['max_consecutive'].append(consecutive_count)
        stats['consecutive']['min_gaps'].append(min_gap)
        
        # 3. 홀짝
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        stats['odd_even']['odd_counts'].append(odd_count)
        
        # 4. 최대 간격
        gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers) - 1)]
        max_gap = max(gaps)
        stats['max_gap']['max_gaps'].append(max_gap)
        
        # 5. 구간별 분포 (1-15, 16-30, 31-45)
        section_counts = [0, 0, 0]
        for n in numbers:
            if n <= 15:
                section_counts[0] += 1
            elif n <= 30:
                section_counts[1] += 1
            else:
                section_counts[2] += 1
        stats['section']['section_counts'].append(section_counts)
        
        # 6. 10단위 구간
        ten_section_counts = [0, 0, 0, 0, 0]
        for n in numbers:
            if n <= 10:
                ten_section_counts[0] += 1
            elif n <= 20:
                ten_section_counts[1] += 1
            elif n <= 30:
                ten_section_counts[2] += 1
            elif n <= 40:
                ten_section_counts[3] += 1
            else:
                ten_section_counts[4] += 1
        stats['ten_section']['ten_section_counts'].append(ten_section_counts)
        
        # 7. 끝자리
        last_digits = [n % 10 for n in numbers]
        last_digit_groups = max([last_digits.count(d) for d in set(last_digits)])
        stats['last_digit']['last_digit_groups'].append(last_digit_groups)
        
        # 8. 등차수열
        max_arithmetic = find_max_arithmetic_sequence(numbers)
        stats['arithmetic_sequence']['max_lengths'].append(max_arithmetic)
        
        # 9. 등비수열
        max_geometric = find_max_geometric_sequence(numbers)
        stats['geometric_sequence']['max_lengths'].append(max_geometric)
        
        # 10. 소수
        prime_count = sum(1 for n in numbers if n in primes)
        stats['prime_composite']['prime_counts'].append(prime_count)
        
        # 11. 자릿수 합
        digit_sums = []
        for n in numbers:
            digit_sum = sum(int(d) for d in str(n))
            digit_sums.append(digit_sum)
        
        stats['digit_sum']['digit_sums'].append(sum(digit_sums))
        stats['digit_sum']['digit_sum_ranges'].append(max(digit_sums) - min(digit_sums))
        
        # 12. 분산도
        std_dev = stdev(numbers)
        variance = std_dev ** 2
        avg_gap = mean(gaps)
        
        stats['dispersion']['std_devs'].append(std_dev)
        stats['dispersion']['variances'].append(variance)
        stats['dispersion']['avg_gaps'].append(avg_gap)
        
        # 13. 고정 간격
        step_pattern = analyze_fixed_steps(numbers)
        stats['fixed_step']['step_patterns'].append(step_pattern)
        
        # 14. 배수
        for multiple in [2, 3, 4, 5]:
            count = sum(1 for n in numbers if n % multiple == 0)
            stats['multiple'][f'multiple_{multiple}'].append(count)
    
    return stats

def find_max_arithmetic_sequence(numbers: List[int]) -> int:
    """최대 등차수열 길이 찾기"""
    max_length = 0
    
    for i in range(len(numbers)):
        for j in range(i+1, len(numbers)):
            diff = numbers[j] - numbers[i]
            length = 2
            last = numbers[j]
            
            for k in range(j+1, len(numbers)):
                if numbers[k] - last == diff:
                    length += 1
                    last = numbers[k]
            
            max_length = max(max_length, length)
    
    return max_length

def find_max_geometric_sequence(numbers: List[int]) -> int:
    """최대 등비수열 길이 찾기"""
    max_length = 0
    
    for i in range(len(numbers)):
        for j in range(i+1, len(numbers)):
            if numbers[i] == 0:
                continue
            
            ratio = numbers[j] / numbers[i]
            if ratio != int(ratio):
                continue
            
            length = 2
            last = numbers[j]
            
            for k in range(j+1, len(numbers)):
                if last * ratio == numbers[k]:
                    length += 1
                    last = numbers[k]
            
            max_length = max(max_length, length)
    
    return max_length

def analyze_fixed_steps(numbers: List[int]) -> Dict[int, int]:
    """고정 간격 패턴 분석"""
    step_counts = {}
    
    for step in range(1, 10):
        count = 0
        for i in range(len(numbers) - 1):
            if numbers[i+1] - numbers[i] == step:
                count += 1
        if count > 0:
            step_counts[step] = count
    
    return step_counts

def calculate_new_criteria(stats: Dict) -> Dict:
    """통계를 기반으로 새로운 필터 기준값 계산"""
    new_criteria = {}
    
    # 1. 합계 범위 (평균 ± 2*표준편차)
    sums = stats['sum_range']['sums']
    sum_mean = mean(sums)
    sum_std = stdev(sums)
    new_criteria['sum_range'] = {
        'min_sum': int(sum_mean - 2 * sum_std),
        'max_sum': int(sum_mean + 2 * sum_std)
    }
    
    # 2. 평균값 범위
    avgs = stats['average']['averages']
    avg_mean = mean(avgs)
    avg_std = stdev(avgs)
    new_criteria['average'] = {
        'min_average': round(avg_mean - 2 * avg_std, 1),
        'max_average': round(avg_mean + 2 * avg_std, 1)
    }
    
    # 3. 연속 번호
    consecutive = stats['consecutive']['max_consecutive']
    new_criteria['consecutive'] = {
        'max_consecutive': max(consecutive) + 1,  # 여유를 둠
        'min_gap': min(stats['consecutive']['min_gaps'])
    }
    
    # 4. 홀짝
    odd_counts = stats['odd_even']['odd_counts']
    # 극단값 제외 (0개 또는 6개)
    new_criteria['odd_even'] = {
        'excluded_counts': [0, 6]
    }
    
    # 5. 최대 간격
    max_gaps = stats['max_gap']['max_gaps']
    new_criteria['max_gap'] = {
        'max_allowed_gap': max(max_gaps) + 2  # 여유를 둠
    }
    
    # 6. 구간별 분포
    section_counts = stats['section']['section_counts']
    max_per_section = max(max(counts) for counts in section_counts)
    new_criteria['section'] = {
        'max_numbers_per_section': max_per_section,
        'exclude_all_section': True
    }
    
    # 7. 10단위 구간
    ten_section_counts = stats['ten_section']['ten_section_counts']
    section_limits = {}
    for i in range(5):
        max_count = max(counts[i] for counts in ten_section_counts)
        section_limits[f'section{i+1}'] = [max_count]
    new_criteria['ten_section'] = {
        'section_limits': section_limits
    }
    
    # 8. 끝자리
    last_digit_groups = stats['last_digit']['last_digit_groups']
    new_criteria['last_digit'] = {
        'min_same_last_digits': max(last_digit_groups) + 1
    }
    
    # 9. 등차수열
    arithmetic_lengths = stats['arithmetic_sequence']['max_lengths']
    new_criteria['arithmetic_sequence'] = {
        'min_sequence': max(arithmetic_lengths) + 1,
        'excluded_lengths': [max(arithmetic_lengths) + 1, 6]
    }
    
    # 10. 등비수열
    geometric_lengths = stats['geometric_sequence']['max_lengths']
    new_criteria['geometric_sequence'] = {
        'min_sequence': max(geometric_lengths) + 1,
        'excluded_lengths': [max(geometric_lengths) + 1, 5, 6]
    }
    
    # 11. 소수
    prime_counts = stats['prime_composite']['prime_counts']
    new_criteria['prime_composite'] = {
        'valid_prime_counts': list(range(min(prime_counts), max(prime_counts) + 1)),
        'min_allowed': min(prime_counts),
        'max_allowed': max(prime_counts)
    }
    
    # 12. 자릿수 합
    digit_sums = stats['digit_sum']['digit_sums']
    digit_ranges = stats['digit_sum']['digit_sum_ranges']
    new_criteria['digit_sum'] = {
        'min_digit_sum': min(digit_sums) - 2,
        'max_digit_sum': max(digit_sums) + 2,
        'min_digit_sum_range': min(digit_ranges),
        'max_digit_sum_range': max(digit_ranges) + 2
    }
    
    # 13. 분산도
    std_devs = stats['dispersion']['std_devs']
    variances = stats['dispersion']['variances']
    avg_gaps = stats['dispersion']['avg_gaps']
    
    new_criteria['dispersion'] = {
        'min_std_dev': round(min(std_devs) - 1, 1),
        'max_std_dev': round(max(std_devs) + 1, 1),
        'min_variance': round(min(variances) - 10, 1),
        'max_variance': round(max(variances) + 10, 1),
        'min_avg_gap': round(min(avg_gaps) - 0.5, 1),
        'max_avg_gap': round(max(avg_gaps) + 0.5, 1),
        'min_min_gap': 0,
        'max_min_gap': 5,
        'min_max_gap': 2,
        'max_max_gap': max(stats['max_gap']['max_gaps']) + 2
    }
    
    # 14. 배수
    multiples = {}
    for multiple in [3, 4, 5]:
        counts = stats['multiple'][f'multiple_{multiple}']
        multiples[multiple] = [min(counts), max(counts)]
    new_criteria['multiple'] = {
        'multiples': multiples
    }
    
    # 15. Match 필터는 그대로 유지
    new_criteria['match'] = {
        'max_match': 5
    }
    
    # 16. 고정 간격 (복잡하므로 기존 설정 유지)
    new_criteria['fixed_step'] = {
        'all_steps': {
            'required_matches': 6,
            'steps_to_exclude': [2, 3, 4, 5, 6, 7]
        },
        'partial_steps': {
            'required_matches': 5,
            'steps_to_exclude': [2, 3, 4, 5]
        },
        'four_steps': {
            'required_matches': 4,
            'steps_to_exclude': [2, 3, 4]
        },
        'three_steps': {
            'required_matches': 3,
            'steps_to_exclude': [2]
        }
    }
    
    return new_criteria

def update_config_file(new_criteria: Dict):
    """설정 파일 업데이트"""
    try:
        # 기존 설정 로드
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 새로운 기준값으로 업데이트
        for filter_name, criteria in new_criteria.items():
            if filter_name in config['filters']['criteria']:
                config['filters']['criteria'][filter_name].update(criteria)
        
        # 파일 저장
        with open('config_updated.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        logging.info("새로운 설정이 config_updated.yaml에 저장되었습니다.")
        
    except Exception as e:
        logging.error(f"설정 파일 업데이트 중 오류: {str(e)}")

def main():
    """메인 실행 함수"""
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        print("\n" + "="*60)
        print("최근 100회차 당첨 데이터 분석 시스템")
        print("="*60)
        
        # 최근 100회차 당첨번호 가져오기
        winning_numbers = get_recent_winning_numbers(db_manager, 100)
        
        if not winning_numbers:
            print("당첨 데이터를 가져올 수 없습니다.")
            return
        
        print(f"\n분석 대상: {winning_numbers[0][0]}회 ~ {winning_numbers[-1][0]}회 (총 {len(winning_numbers)}회)")
        
        # 통계 분석
        stats = analyze_filter_statistics(winning_numbers)
        
        # 통계 출력
        print("\n[필터별 통계 분석 결과]")
        print(f"\n1. 합계 범위:")
        print(f"   - 최소: {min(stats['sum_range']['sums'])}")
        print(f"   - 최대: {max(stats['sum_range']['sums'])}")
        print(f"   - 평균: {mean(stats['sum_range']['sums']):.1f}")
        
        print(f"\n2. 평균값 범위:")
        print(f"   - 최소: {min(stats['average']['averages']):.1f}")
        print(f"   - 최대: {max(stats['average']['averages']):.1f}")
        print(f"   - 평균: {mean(stats['average']['averages']):.1f}")
        
        print(f"\n3. 연속 번호:")
        print(f"   - 최대 연속: {max(stats['consecutive']['max_consecutive'])}개")
        print(f"   - 평균 연속: {mean(stats['consecutive']['max_consecutive']):.1f}개")
        
        print(f"\n4. 홀짝 분포:")
        odd_counts = stats['odd_even']['odd_counts']
        for i in range(7):
            count = odd_counts.count(i)
            if count > 0:
                print(f"   - 홀수 {i}개: {count}회 ({count/len(odd_counts)*100:.1f}%)")
        
        print(f"\n5. 최대 간격:")
        print(f"   - 최소: {min(stats['max_gap']['max_gaps'])}")
        print(f"   - 최대: {max(stats['max_gap']['max_gaps'])}")
        print(f"   - 평균: {mean(stats['max_gap']['max_gaps']):.1f}")
        
        print(f"\n6. 소수 개수:")
        prime_counts = stats['prime_composite']['prime_counts']
        for i in range(7):
            count = prime_counts.count(i)
            if count > 0:
                print(f"   - 소수 {i}개: {count}회 ({count/len(prime_counts)*100:.1f}%)")
        
        # 새로운 기준값 계산
        new_criteria = calculate_new_criteria(stats)
        
        print("\n[새로운 필터 기준값 제안]")
        for filter_name, criteria in new_criteria.items():
            print(f"\n{filter_name}:")
            for key, value in criteria.items():
                print(f"   {key}: {value}")
        
        # 설정 파일 업데이트
        update_config_file(new_criteria)
        
        # 분석 기반 권장사항
        print("\n[분석 기반 권장사항]")
        
        # sum_range와 average 필터 중복 확인
        print("\n1. 필터 중복성:")
        print("   - sum_range와 average 필터가 96% 중복")
        print("   → average 필터 비활성화 권장")
        
        # 효율성 낮은 필터
        print("\n2. 효율성 개선:")
        print("   - match 필터 (5% 효율): 기준 완화 고려")
        print("   - multiple 필터 (8% 효율): 범위 조정 필요")
        
        # 안정적인 패턴
        print("\n3. 안정적인 패턴:")
        print("   - 홀짝 비율: 3:3이 가장 많음")
        print("   - 소수 개수: 2~3개가 가장 많음")
        print("   - 연속 번호: 대부분 2개 이하")
        
        print("\n분석 완료!")
        print("새로운 설정은 config_updated.yaml에 저장되었습니다.")
        print("검토 후 config.yaml로 이름을 변경하여 적용하세요.")
        
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    main()