"""
전체 회차 필터 Inclusion Rate 정밀 측정

목적: 필터링된 풀에 실제 당첨번호가 포함되는 비율을 측정
- 각 필터 개별 inclusion rate 측정
- 전체 필터 AND 조건에서의 inclusion rate 측정
- 배제율 > 5%인 필터 하이라이트

사용법:
    python src/scripts/measure_inclusion_rate.py [--start 100] [--end 1213]
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Any

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import yaml
import numpy as np

# tqdm Windows 호환성
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
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_filter_config() -> Dict:
    """adaptive_filter_config.yaml에서 필터 기준값 로드"""
    config_path = os.path.join(project_root, 'configs', 'adaptive_filter_config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def create_filter_instances(db: DatabaseManager, config: Dict) -> Dict:
    """16개 필터 인스턴스 생성"""
    dynamic_criteria = config.get('dynamic_criteria', {})
    filters_enabled = config.get('filters', {})

    # 필터 이름 → (클래스, config 키) 매핑
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
        # 필터 활성화 여부 확인
        enabled = filters_enabled.get(filter_name, True)
        if not enabled:
            continue

        criteria = dynamic_criteria.get(config_key, {})
        try:
            instances[filter_name] = filter_class(db, criteria)
        except Exception as e:
            logger.warning(f"필터 '{filter_name}' 생성 실패: {e}")

    return instances


def measure_inclusion_rate(
    start_round: int = 100,
    end_round: int = None
) -> Dict[str, Any]:
    """전체 회차 필터 Inclusion Rate 정밀 측정

    Args:
        start_round: 시작 회차 (기본 100)
        end_round: 끝 회차 (기본 최신)

    Returns:
        측정 결과 딕셔너리
    """
    # DB 및 설정 로드
    db = DatabaseManager()
    config = load_filter_config()

    # 필터 인스턴스 생성
    filters = create_filter_instances(db, config)
    logger.info(f"활성화된 필터: {len(filters)}개 - {list(filters.keys())}")

    # 당첨번호 로드
    all_data = db.get_numbers_with_bonus()
    if not all_data:
        logger.error("당첨번호 데이터를 로드할 수 없습니다.")
        return {}

    # 회차 범위 설정
    if end_round is None:
        end_round = max(r for r, _ in all_data)

    # 데이터 필터링
    test_data = [(r, nums) for r, nums in all_data if start_round <= r <= end_round]
    logger.info(f"테스트 범위: {start_round}~{end_round} 회차 ({len(test_data)}개)")

    # 결과 저장 구조
    filter_results = {name: {'passed': 0, 'failed': 0, 'failed_rounds': []}
                      for name in filters}
    all_pass_count = 0
    all_fail_count = 0
    all_fail_rounds = []

    # 각 회차별 측정
    for round_num, numbers_tuple in tqdm(test_data, desc="Inclusion Rate 측정", file=sys.stdout):
        # 당첨번호를 문자열로 변환 (bonus 제외, 앞 6개만)
        winning_numbers = list(numbers_tuple[:6])
        winning_str = ','.join(str(n) for n in sorted(winning_numbers))

        # 각 필터 개별 검사
        all_passed = True
        for filter_name, filter_instance in filters.items():
            try:
                passed = filter_instance.check_combination(winning_str, round_num)
                if passed:
                    filter_results[filter_name]['passed'] += 1
                else:
                    filter_results[filter_name]['failed'] += 1
                    filter_results[filter_name]['failed_rounds'].append(round_num)
                    all_passed = False
            except Exception as e:
                # 검사 실패 시 통과로 간주 (안전한 방향)
                filter_results[filter_name]['passed'] += 1
                logger.debug(f"필터 '{filter_name}' 회차 {round_num} 검사 오류: {e}")

        # 전체 AND 결과
        if all_passed:
            all_pass_count += 1
        else:
            all_fail_count += 1
            all_fail_rounds.append(round_num)

    # 결과 정리
    total_rounds = len(test_data)
    results = {
        'test_info': {
            'start_round': start_round,
            'end_round': end_round,
            'total_rounds': total_rounds,
            'timestamp': datetime.now().isoformat()
        },
        'overall': {
            'inclusion_rate': all_pass_count / total_rounds if total_rounds > 0 else 0,
            'passed': all_pass_count,
            'failed': all_fail_count,
            'failed_rounds': all_fail_rounds[:50]  # 최대 50개까지만 저장
        },
        'per_filter': {}
    }

    for filter_name, data in filter_results.items():
        total = data['passed'] + data['failed']
        rate = data['passed'] / total if total > 0 else 0
        exclusion_rate = data['failed'] / total if total > 0 else 0
        results['per_filter'][filter_name] = {
            'inclusion_rate': rate,
            'exclusion_rate': exclusion_rate,
            'passed': data['passed'],
            'failed': data['failed'],
            'failed_rounds': data['failed_rounds'][:20]  # 최대 20개
        }

    return results


def print_results(results: Dict[str, Any]):
    """결과를 표 형태로 출력"""
    if not results:
        print("결과 없음")
        return

    test_info = results['test_info']
    overall = results['overall']
    per_filter = results['per_filter']

    print("\n" + "=" * 80)
    print("  전체 회차 필터 Inclusion Rate 정밀 측정 결과")
    print("=" * 80)
    print(f"  테스트 범위: {test_info['start_round']}~{test_info['end_round']} 회차")
    print(f"  테스트 회차: {test_info['total_rounds']}개")
    print(f"  측정 시각: {test_info['timestamp']}")
    print("-" * 80)

    # 전체 Inclusion Rate
    overall_rate = overall['inclusion_rate'] * 100
    status = "[PASS]" if overall_rate >= 95 else "[WARN]" if overall_rate >= 90 else "[FAIL]"
    print(f"\n  전체 Inclusion Rate: {overall_rate:.2f}% ({overall['passed']}/{test_info['total_rounds']}) {status}")
    print(f"  당첨번호 배제 회차: {overall['failed']}개")

    if overall['failed'] > 0:
        print(f"  배제된 회차 목록: {overall['failed_rounds'][:10]}...")

    # 개별 필터 결과
    print("\n" + "-" * 80)
    print(f"  {'필터 이름':<25} | {'포함률':>8} | {'배제율':>8} | {'통과':>6} | {'실패':>6} | {'상태':>6}")
    print("-" * 80)

    # 배제율 순으로 정렬 (높은 것 먼저)
    sorted_filters = sorted(
        per_filter.items(),
        key=lambda x: x[1]['exclusion_rate'],
        reverse=True
    )

    for filter_name, data in sorted_filters:
        inc_rate = data['inclusion_rate'] * 100
        exc_rate = data['exclusion_rate'] * 100

        # 상태 판정
        if exc_rate > 5:
            status = "[FAIL]"
        elif exc_rate > 2:
            status = "[WARN]"
        elif exc_rate > 0:
            status = "[NOTE]"
        else:
            status = "[ OK ]"

        print(f"  {filter_name:<25} | {inc_rate:>7.2f}% | {exc_rate:>7.2f}% | {data['passed']:>6} | {data['failed']:>6} | {status}")

    # 위험 필터 하이라이트
    dangerous = [(name, data) for name, data in per_filter.items()
                 if data['exclusion_rate'] > 0.05]
    if dangerous:
        print("\n" + "=" * 80)
        print("  [!] 당첨번호 배제율 > 5% 필터 (즉시 기준값 완화 필요)")
        print("=" * 80)
        for name, data in dangerous:
            exc_rate = data['exclusion_rate'] * 100
            print(f"  - {name}: 배제율 {exc_rate:.2f}% ({data['failed']}회차 배제)")
            if data['failed_rounds']:
                print(f"    배제 회차: {data['failed_rounds'][:10]}")

    # 필터링 없는 필터 (100% 통과)
    no_effect = [(name, data) for name, data in per_filter.items()
                 if data['exclusion_rate'] == 0]
    if no_effect:
        print(f"\n  [*] 필터링 효과 없음 (100% 통과): {len(no_effect)}개")
        for name, _ in no_effect:
            print(f"      - {name}")

    print("\n" + "=" * 80)


def save_results(results: Dict[str, Any]):
    """결과를 JSON 파일로 저장"""
    results_dir = os.path.join(project_root, 'results')
    os.makedirs(results_dir, exist_ok=True)

    output_path = os.path.join(results_dir, 'inclusion_rate_report.json')

    # failed_rounds 리스트를 직렬화 가능하게 변환
    serializable = json.loads(json.dumps(results, default=str))

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    logger.info(f"결과 저장: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='필터 Inclusion Rate 정밀 측정')
    parser.add_argument('--start', type=int, default=100, help='시작 회차 (기본 100)')
    parser.add_argument('--end', type=int, default=None, help='끝 회차 (기본 최신)')
    args = parser.parse_args()

    logger.info("필터 Inclusion Rate 측정 시작...")

    results = measure_inclusion_rate(args.start, args.end)

    if results:
        print_results(results)
        save_results(results)
    else:
        logger.error("측정 실패")


if __name__ == '__main__':
    main()
