"""
Threshold vs Pool Size vs Inclusion Rate 시뮬레이션

목적: global_probability_threshold를 변화시킬 때
      풀 크기와 당첨번호 포함률 변화를 정밀 측정

사용법:
    python src/scripts/threshold_simulation.py
"""

import sys
import os
import json
import logging
import random
import itertools
from datetime import datetime
from typing import Dict, List, Tuple, Any

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import yaml
import numpy as np
from tqdm import tqdm

from src.core.db_manager import DatabaseManager

# 필터 클래스 임포트
from src.filters.sum_range_filter import SumRangeFilter
from src.filters.odd_even_filter import OddEvenFilter
from src.filters.consecutive_filter import ConsecutiveFilter
from src.filters.max_gap_filter import MaxGapFilter
from src.filters.average_filter import AverageFilter
from src.filters.match_filter import MatchFilter
from src.filters.multiple_filter import MultipleFilter
from src.filters.digit_sum_filter import DigitSumFilter
from src.filters.dispersion_filter import DispersionFilter
from src.filters.last_digit_filter import LastDigitFilter
from src.filters.ten_section_filter import TenSectionFilter
from src.filters.fixed_step_filter import FixedStepFilter
from src.filters.prime_composite_filter import PrimeCompositeFilter
from src.filters.arithmetic_sequence_filter import ArithmeticSequenceFilter
from src.filters.geometric_sequence_filter import GeometricSequenceFilter
from src.filters.section_filter import SectionFilter
from src.filters.ac_value_filter import ACValueFilter
from src.filters.balanced_quadrant_filter import BalancedQuadrantFilter
from src.filters.outlier_detection_filter import OutlierDetectionFilter

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전체 조합 수 (C(45,6))
TOTAL_COMBINATIONS = 8_145_060
# 테스트할 threshold 값 목록
THRESHOLDS = [0.3, 0.5, 0.7, 1.0, 1.3, 1.5, 2.0, 2.5, 3.0]
# 풀 크기 추정용 샘플 수
SAMPLE_SIZE = 10_000
# 예측 세트 수 (실효 확률 계산용)
PREDICTION_SETS = 5


def load_filter_config() -> Dict:
    """adaptive_filter_config.yaml에서 필터 기준값 로드"""
    config_path = os.path.join(project_root, 'configs', 'adaptive_filter_config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def create_filter_instances(db: DatabaseManager, config: Dict) -> Dict:
    """16개 필터 인스턴스 생성 (measure_inclusion_rate.py 로직 재활용)"""
    dynamic_criteria = config.get('dynamic_criteria', {})
    filters_enabled = config.get('filters', {})

    filter_map = {
        'sum_range': (SumRangeFilter, 'sum_range'),
        'odd_even': (OddEvenFilter, 'odd_even'),
        'consecutive': (ConsecutiveFilter, 'consecutive'),
        'max_gap': (MaxGapFilter, 'max_gap'),
        'average': (AverageFilter, 'average'),
        'match': (MatchFilter, 'match'),
        'multiple': (MultipleFilter, 'multiple'),
        'digit_sum': (DigitSumFilter, 'digit_sum'),
        'dispersion': (DispersionFilter, 'dispersion'),
        'last_digit': (LastDigitFilter, 'last_digit'),
        'ten_section': (TenSectionFilter, 'ten_section'),
        'fixed_step': (FixedStepFilter, 'fixed_step'),
        'prime_composite': (PrimeCompositeFilter, 'prime_composite'),
        'arithmetic_sequence': (ArithmeticSequenceFilter, 'arithmetic'),
        'geometric_sequence': (GeometricSequenceFilter, 'geometric'),
        'section': (SectionFilter, 'section'),
        'ac_value': (ACValueFilter, 'ac_value'),
        'balanced_quadrant': (BalancedQuadrantFilter, 'balanced_quadrant'),
        'outlier_detection': (OutlierDetectionFilter, 'outlier_detection'),
    }

    instances = {}
    for filter_name, (filter_class, config_key) in filter_map.items():
        enabled = filters_enabled.get(filter_name, True)
        if not enabled:
            continue
        criteria = dynamic_criteria.get(config_key, {})
        try:
            instances[filter_name] = filter_class(db, criteria)
        except Exception as e:
            logger.warning(f"[!] '{filter_name}' 생성 실패: {e}")

    return instances


def generate_random_combinations(n: int) -> List[str]:
    """랜덤 로또 조합 n개 생성 (1~45 중 6개 선택)"""
    combos = set()
    all_numbers = list(range(1, 46))
    while len(combos) < n:
        nums = sorted(random.sample(all_numbers, 6))
        combos.add(','.join(str(x) for x in nums))
    return list(combos)


def measure_inclusion_rate_for_threshold(
    filters: Dict,
    test_data: List[Tuple[int, tuple]],
    threshold: float,
    config: Dict,
    db: DatabaseManager
) -> Dict[str, Any]:
    """특정 threshold에서 당첨번호 포함률 측정

    threshold 변경이 영향을 미치는 필터:
    - AdaptiveProbabilityFilter가 threshold 기반으로 동적 기준을 생성
    - 하지만 개별 16개 필터는 config.yaml의 dynamic_criteria로 동작
    - 따라서 threshold 변경 시 dynamic_criteria를 재계산해야 함

    현실적으로는: threshold 변경이 AdaptiveProbabilityFilter의
    generate_dynamic_criteria()를 통해 필터 기준값에 영향

    여기서는 현재 설정된 필터 기준으로 개별 필터 포함률을 측정
    """
    total = len(test_data)
    all_pass_count = 0
    all_fail_rounds = []

    per_filter_fail = {name: 0 for name in filters}

    for round_num, numbers_tuple in test_data:
        winning_numbers = list(numbers_tuple[:6])
        winning_str = ','.join(str(n) for n in sorted(winning_numbers))

        all_passed = True
        for filter_name, filter_instance in filters.items():
            try:
                passed = filter_instance.check_combination(winning_str, round_num)
                if not passed:
                    per_filter_fail[filter_name] += 1
                    all_passed = False
            except Exception:
                pass  # 오류 시 통과로 간주

        if all_passed:
            all_pass_count += 1
        else:
            all_fail_rounds.append(round_num)

    inclusion_rate = all_pass_count / total if total > 0 else 0
    return {
        'inclusion_rate': inclusion_rate,
        'passed': all_pass_count,
        'failed': total - all_pass_count,
        'failed_rounds': all_fail_rounds[:30],
        'per_filter_fail': per_filter_fail
    }


def estimate_pool_size_for_threshold(
    filters: Dict,
    sample_combos: List[str],
    latest_round: int
) -> Dict[str, Any]:
    """샘플링 기반 풀 크기 추정

    랜덤 조합 SAMPLE_SIZE개에 대해 필터 통과율을 측정하고
    전체 조합 수에 곱하여 풀 크기를 추정
    """
    passed_count = 0
    per_filter_pass = {name: 0 for name in filters}

    for combo_str in sample_combos:
        all_passed = True
        for filter_name, filter_instance in filters.items():
            try:
                passed = filter_instance.check_combination(combo_str, latest_round)
                if passed:
                    per_filter_pass[filter_name] += 1
                else:
                    all_passed = False
            except Exception:
                per_filter_pass[filter_name] += 1  # 오류 시 통과 간주

        if all_passed:
            passed_count += 1

    sample_total = len(sample_combos)
    pass_rate = passed_count / sample_total if sample_total > 0 else 0
    estimated_pool = int(pass_rate * TOTAL_COMBINATIONS)

    per_filter_rates = {}
    for name, count in per_filter_pass.items():
        per_filter_rates[name] = count / sample_total if sample_total > 0 else 0

    return {
        'sample_pass_rate': pass_rate,
        'estimated_pool_size': estimated_pool,
        'sample_passed': passed_count,
        'sample_total': sample_total,
        'per_filter_pass_rate': per_filter_rates
    }


def run_simulation() -> Dict[str, Any]:
    """전체 시뮬레이션 실행"""
    print("\n" + "=" * 85)
    print("  Threshold vs Pool Size vs Inclusion Rate 시뮬레이션")
    print("=" * 85)

    # DB 및 설정 로드
    db = DatabaseManager()
    config = load_filter_config()

    # 당첨번호 로드
    all_data = db.get_numbers_with_bonus()
    if not all_data:
        print("[ERROR] 당첨번호 데이터를 로드할 수 없습니다.")
        return {}

    latest_round = max(r for r, _ in all_data)

    # 최근 200회차로 포함률 측정
    start_round = max(1, latest_round - 199)
    test_data = [(r, nums) for r, nums in all_data if start_round <= r <= latest_round]
    print(f"  테스트 범위: {start_round}~{latest_round} 회차 ({len(test_data)}개)")
    print(f"  전체 조합 수: {TOTAL_COMBINATIONS:,}")
    print(f"  풀 크기 추정용 샘플: {SAMPLE_SIZE:,}개")
    print(f"  현재 threshold: {config.get('global_probability_threshold', 'N/A')}%")

    # 랜덤 샘플 조합 생성 (모든 threshold에서 동일 샘플 사용)
    print("\n  랜덤 조합 샘플 생성 중...")
    sample_combos = generate_random_combinations(SAMPLE_SIZE)
    print(f"  샘플 {len(sample_combos):,}개 생성 완료")

    # 필터 인스턴스 생성 (현재 설정 기준)
    filters = create_filter_instances(db, config)
    active_filter_names = list(filters.keys())
    print(f"  활성화 필터: {len(filters)}개")

    # --- 현재 설정 기준 포함률 + 풀 크기 측정 ---
    # 16개 필터의 기준값은 YAML에서 로드된 고정값
    # threshold는 AdaptiveProbabilityFilter가 기준값을 동적 생성할 때만 영향
    # 여기서는 각 threshold에서 AdaptiveProbabilityFilter의 동적 기준을 재계산하여 적용

    results = {
        'simulation_info': {
            'timestamp': datetime.now().isoformat(),
            'test_range': f"{start_round}~{latest_round}",
            'test_rounds': len(test_data),
            'sample_size': SAMPLE_SIZE,
            'total_combinations': TOTAL_COMBINATIONS,
            'active_filters': active_filter_names,
            'thresholds_tested': THRESHOLDS
        },
        'threshold_results': {}
    }

    # AdaptiveProbabilityFilter 사용하여 threshold별 동적 기준 생성
    from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter

    # 싱글톤 리셋 후 새로 생성
    AdaptiveProbabilityFilter.reset_instance()
    adaptive_filter = AdaptiveProbabilityFilter(db, probability_threshold=1.0)

    # 패턴 분석 (당첨번호 기반)
    winning_strs = []
    for _, nums in all_data:
        w = list(nums[:6])
        winning_strs.append(','.join(str(n) for n in sorted(w)))

    print("\n  패턴 분석 중...")
    adaptive_filter.analyze_patterns(winning_strs)
    print("  패턴 분석 완료")

    print("\n" + "-" * 85)
    print(f"  {'Threshold':>10} | {'Pool Size':>12} | {'감소율':>8} | {'Inclusion':>10} | "
          f"{'배제회차':>8} | {'실효1등확률':>16}")
    print("-" * 85)

    for threshold in tqdm(THRESHOLDS, desc="Threshold 시뮬레이션", file=sys.stdout):
        # AdaptiveProbabilityFilter의 threshold 변경
        adaptive_filter.probability_threshold = threshold

        # threshold에 따른 동적 기준 재생성
        dynamic_criteria = adaptive_filter.generate_dynamic_criteria()

        # 동적 기준으로 필터 재생성
        config_copy = dict(config)
        config_copy['dynamic_criteria'] = dynamic_criteria
        threshold_filters = create_filter_instances(db, config_copy)

        # 1. 포함률 측정 (최근 200회차)
        inc_result = measure_inclusion_rate_for_threshold(
            threshold_filters, test_data, threshold, config_copy, db
        )

        # 2. 풀 크기 추정 (샘플링)
        pool_result = estimate_pool_size_for_threshold(
            threshold_filters, sample_combos, latest_round
        )

        # 실효 1등 확률 계산
        pool_size = pool_result['estimated_pool_size']
        if pool_size > 0:
            effective_odds = pool_size / PREDICTION_SETS
        else:
            effective_odds = TOTAL_COMBINATIONS / PREDICTION_SETS

        # 감소율 계산
        reduction_rate = (1 - pool_size / TOTAL_COMBINATIONS) * 100 if pool_size > 0 else 0

        # 결과 저장
        result_entry = {
            'threshold': threshold,
            'pool_size': pool_size,
            'reduction_rate': round(reduction_rate, 2),
            'sample_pass_rate': round(pool_result['sample_pass_rate'] * 100, 4),
            'inclusion_rate': round(inc_result['inclusion_rate'] * 100, 2),
            'included_rounds': inc_result['passed'],
            'excluded_rounds': inc_result['failed'],
            'excluded_round_list': inc_result['failed_rounds'],
            'effective_odds': int(effective_odds),
            'per_filter_fail_count': inc_result['per_filter_fail'],
            'per_filter_sample_pass_rate': {
                k: round(v * 100, 2) for k, v in pool_result['per_filter_pass_rate'].items()
            }
        }
        results['threshold_results'][str(threshold)] = result_entry

        # 콘솔 출력
        inc_rate_str = f"{inc_result['inclusion_rate'] * 100:.1f}%"
        pool_str = f"{pool_size:>10,}"
        reduction_str = f"{reduction_rate:.1f}%"
        excluded_str = f"{inc_result['failed']}개"
        odds_str = f"1/{int(effective_odds):,}"

        print(f"  {threshold:>8.1f}% | {pool_str} | {reduction_str:>7} | "
              f"{inc_rate_str:>9} | {excluded_str:>7} | {odds_str:>15}")

    # 싱글톤 리셋 (다른 모듈에 영향 방지)
    AdaptiveProbabilityFilter.reset_instance()

    return results


def find_optimal_threshold(results: Dict) -> Dict[str, Any]:
    """최적 threshold 추천

    기준:
    - 포함률 >= 95% (당첨번호 배제 최소화)
    - 풀 크기가 작을수록 좋음 (확률 개선)
    - 실효 확률이 높을수록 좋음
    """
    threshold_data = results.get('threshold_results', {})
    if not threshold_data:
        return {}

    candidates = []
    for key, data in threshold_data.items():
        inc_rate = data['inclusion_rate']
        pool_size = data['pool_size']
        threshold = data['threshold']

        # 포함률 95% 이상인 것만 후보
        if inc_rate >= 95.0:
            candidates.append({
                'threshold': threshold,
                'inclusion_rate': inc_rate,
                'pool_size': pool_size,
                'effective_odds': data['effective_odds'],
                'reduction_rate': data['reduction_rate']
            })

    if not candidates:
        # 95% 미달이면 포함률이 가장 높은 것 선택
        best = max(threshold_data.values(), key=lambda x: x['inclusion_rate'])
        return {
            'recommended_threshold': best['threshold'],
            'reason': f"포함률 95% 이상 조건 미충족. 최대 포함률 {best['inclusion_rate']:.1f}% 기준 선택",
            'inclusion_rate': best['inclusion_rate'],
            'pool_size': best['pool_size'],
            'effective_odds': best['effective_odds'],
            'warning': True
        }

    # 포함률 95% 이상 중 풀 크기가 가장 작은 것 (확률 최대화)
    optimal = min(candidates, key=lambda x: x['pool_size'])

    return {
        'recommended_threshold': optimal['threshold'],
        'reason': f"포함률 {optimal['inclusion_rate']:.1f}% 유지하면서 풀 크기 최소화",
        'inclusion_rate': optimal['inclusion_rate'],
        'pool_size': optimal['pool_size'],
        'effective_odds': optimal['effective_odds'],
        'reduction_rate': optimal['reduction_rate'],
        'warning': False,
        'all_candidates': candidates
    }


def print_detailed_results(results: Dict):
    """상세 결과 출력"""
    threshold_data = results.get('threshold_results', {})
    if not threshold_data:
        return

    # threshold별 필터 실패 분석
    print("\n" + "=" * 85)
    print("  Threshold별 필터 배제 분석 (당첨번호 배제 건수)")
    print("=" * 85)

    # 모든 필터 이름 수집
    all_filter_names = set()
    for data in threshold_data.values():
        all_filter_names.update(data.get('per_filter_fail_count', {}).keys())
    filter_names = sorted(all_filter_names)

    # 테이블 헤더
    header = f"  {'필터':>22} |"
    for t in THRESHOLDS:
        header += f" {t:.1f}% |"
    print(header)
    print("  " + "-" * (25 + len(THRESHOLDS) * 7))

    for fname in filter_names:
        row = f"  {fname:>22} |"
        for t in THRESHOLDS:
            key = str(t)
            fail_count = threshold_data.get(key, {}).get('per_filter_fail_count', {}).get(fname, 0)
            if fail_count > 0:
                row += f" {fail_count:>4} |"
            else:
                row += f"    - |"
        print(row)

    # 최적 threshold 추천
    optimal = find_optimal_threshold(results)
    if optimal:
        print("\n" + "=" * 85)
        print("  [*] 최적 Threshold 추천")
        print("=" * 85)
        warn_marker = " [WARN]" if optimal.get('warning') else ""
        print(f"  추천값: {optimal['recommended_threshold']}%{warn_marker}")
        print(f"  사유: {optimal['reason']}")
        print(f"  포함률: {optimal['inclusion_rate']:.1f}%")
        print(f"  추정 풀 크기: {optimal['pool_size']:,}")
        print(f"  실효 1등 확률 (5세트): 1/{optimal['effective_odds']:,}")
        if 'reduction_rate' in optimal:
            print(f"  조합 감소율: {optimal['reduction_rate']:.1f}%")
        print("=" * 85)


def save_results(results: Dict, optimal: Dict):
    """결과를 JSON 파일로 저장"""
    results_dir = os.path.join(project_root, 'results')
    os.makedirs(results_dir, exist_ok=True)

    output = {
        'simulation_results': results,
        'optimal_recommendation': optimal
    }

    output_path = os.path.join(results_dir, 'threshold_simulation_report.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  결과 저장: {output_path}")


def main():
    print("\n  Threshold Simulation 시작...")
    print(f"  시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = run_simulation()

    if results:
        print_detailed_results(results)
        optimal = find_optimal_threshold(results)
        save_results(results, optimal)
    else:
        print("[ERROR] 시뮬레이션 실패")

    print("\n  시뮬레이션 완료.")


if __name__ == '__main__':
    main()
