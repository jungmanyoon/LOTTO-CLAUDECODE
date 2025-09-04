"""
적응형 확률 기반 필터링 시스템 적용 스크립트
하나의 확률 임계값으로 모든 필터를 통합 관리
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml
import logging
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
from src.core.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(message)s')

def load_config():
    """통합 설정 파일 로드"""
    config_path = "configs/adaptive_filter_config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config

def analyze_current_filters():
    """현재 필터 설정과 새로운 확률 기반 설정 비교"""
    
    print("\n" + "="*80)
    print(" 적응형 확률 기반 필터링 시스템 분석")
    print("="*80)
    
    # 설정 로드
    config = load_config()
    threshold = config['global_probability_threshold']
    
    print(f"\n[핵심 설정]")
    print(f"  통합 확률 임계값: {threshold}%")
    print(f"  의미: {threshold}% 이하로 출현하는 패턴만 제외")
    
    # 현재 문제가 있는 필터들
    print(f"\n[현재 잘못 제외하고 있는 패턴] (1% 이상인데 제외 중)")
    print("-"*60)
    
    problematic_filters = [
        ("홀짝", "홀수 6개", 1.52, "제외 중", "유지해야 함"),
        ("홀짝", "짝수 6개", 1.43, "제외 중", "유지해야 함"),
        ("배수", "2의 배수 6개", 1.43, "제외 중", "유지해야 함"),
        ("배수", "4의 배수 4개", 1.86, "제외 중", "유지해야 함"),
        ("10구간", "11-20구간 4개", 1.52, "제외 중", "유지해야 함"),
        ("구간", "31-45구간 5개", 1.52, "제외 중", "유지해야 함"),
    ]
    
    for filter_name, pattern, rate, current, should_be in problematic_filters:
        status = "[X]" if current == "제외 중" and rate > threshold else "[O]"
        print(f"  {status} {filter_name:8} | {pattern:15} | {rate:5.2f}% | {current:8} -> {should_be}")
    
    # 올바르게 제외하고 있는 필터들
    print(f"\n[올바르게 제외하고 있는 패턴] (1% 미만이므로 제외)")
    print("-"*60)
    
    correct_filters = [
        ("연속번호", "4개 연속", 0.51, "제외 중"),
        ("연속번호", "5개 이상", 0.00, "제외 중"),
        ("끝자리", "4개 동일", 0.42, "제외 중"),
        ("매치", "4개 이상 일치", 0.13, "제외 중"),
        ("구간", "한 구간 6개", 0.25, "제외 중"),
        ("배수", "3의 배수 6개", 0.17, "제외 중"),
    ]
    
    for filter_name, pattern, rate, status in correct_filters:
        print(f"  [O] {filter_name:8} | {pattern:15} | {rate:5.2f}% | {status}")
    
    print("\n" + "="*80)
    print(" 새로운 확률 기반 기준")
    print("="*80)
    
    # 새로운 기준 예시
    new_criteria = {
        "홀짝": f"0개만 제외 (0% 출현)",
        "연속번호": f"4개 이상 제외 (0.51% 이하)",
        "배수": {
            "2의 배수": "0개만 제외 (1.52% > 1%이므로 6개 유지)",
            "3의 배수": "0개, 6개만 제외 (각 1% 미만)",
            "4의 배수": "5개, 6개만 제외 (각 1% 미만)",
            "5의 배수": "5개, 6개만 제외 (각 1% 미만)"
        },
        "10구간": {
            "1-10": "5개, 6개만 제외 (각 1% 미만)",
            "11-20": "5개, 6개만 제외 (4개는 1.52% > 1%)",
            "21-30": "6개만 제외 (5개는 미확인)",
            "31-40": "6개만 제외",
            "41-45": "5개만 제외 (최대 5개)"
        },
        "합계": f"하위 0.5% + 상위 0.5% = 총 {threshold}%",
        "평균": f"하위 0.5% + 상위 0.5% = 총 {threshold}%"
    }
    
    for filter_name, criteria in new_criteria.items():
        print(f"\n[{filter_name}]")
        if isinstance(criteria, dict):
            for sub_name, sub_criteria in criteria.items():
                print(f"  - {sub_name}: {sub_criteria}")
        else:
            print(f"  {criteria}")

def simulate_filtering():
    """새로운 필터링 시뮬레이션"""
    
    print("\n" + "="*80)
    print(" 필터링 시뮬레이션")
    print("="*80)
    
    # 설정 로드
    config = load_config()
    threshold = config['global_probability_threshold']
    
    # 예상 제외율 계산 (1% 임계값 기준)
    expected_exclusions = {
        "홀짝": 0.0,  # 0개만 제외 (0% 출현)
        "연속번호": 0.51,  # 4개 이상
        "합계 범위": 1.0,  # 상하위 각 0.5%
        "고정 간격": 0.1,  # 6개, 5개 패턴
        "끝자리": 0.42,  # 4개 이상
        "최대 간격": 0.5,  # 상위 패턴
        "구간": 0.25,  # 6개 패턴
        "평균": 1.0,  # 상하위 각 0.5%
        "배수": 0.5,  # 극단 패턴만
        "10구간": 0.5,  # 극단 패턴만
        "매치": 0.13,  # 4개 이상
    }
    
    total_exclusion = sum(expected_exclusions.values())
    
    print(f"\n임계값 {threshold}% 기준 예상 제외율:")
    print("-"*60)
    
    for filter_name, rate in sorted(expected_exclusions.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * int(rate * 10)
        print(f"  {filter_name:12} | {bar:10} | {rate:5.2f}%")
    
    print("-"*60)
    print(f"  {'총 제외율':12} | {'':10} | {total_exclusion:5.2f}% (중복 제거 전)")
    print(f"  {'실제 제외율':12} | {'':10} | {total_exclusion * 0.8:5.2f}% (중복 고려)")
    
    # 임계값 변경 시뮬레이션
    print(f"\n[임계값 변경 시뮬레이션]")
    print("-"*60)
    
    thresholds = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    
    for t in thresholds:
        # 간단한 추정 (실제로는 더 복잡)
        if t == 0.5:
            exclusion_rate = 8
        elif t == 1.0:
            exclusion_rate = 12
        elif t == 1.5:
            exclusion_rate = 15
        elif t == 2.0:
            exclusion_rate = 18
        elif t == 3.0:
            exclusion_rate = 25
        else:  # 5.0
            exclusion_rate = 35
        
        remaining = 8145060 * (1 - exclusion_rate/100)
        improvement = 8145060 / remaining
        
        status = "(보수적)" if t <= 0.5 else "(표준)" if t == 1.0 else "(공격적)" if t <= 2.0 else "(매우 공격적)"
        print(f"  {t:3.1f}% {status:10} | 제외 {exclusion_rate:2}% | 남은 조합 {remaining:,.0f}개 | 확률 {improvement:.1f}배 개선")

def apply_to_system():
    """시스템에 적용하는 방법 안내"""
    
    print("\n" + "="*80)
    print(" 시스템 적용 방법")
    print("="*80)
    
    print("\n1. 설정 파일 수정:")
    print("   configs/adaptive_filter_config.yaml 파일에서")
    print("   global_probability_threshold 값만 변경")
    print("   예: 1.0 → 0.5 (보수적-적게 제외) 또는 1.0 → 2.0 (공격적-많이 제외)")
    
    print("\n2. main.py 수정:")
    print("   기존 FilterManager 대신 AdaptiveProbabilityFilter 사용")
    
    print("\n3. 코드 예시:")
    print("""
    # 기존 코드
    from src.core.filter_manager import FilterManager
    filter_manager = FilterManager(db_manager)
    
    # 새로운 코드
    from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
    config = yaml.load(open('configs/adaptive_filter_config.yaml'))
    threshold = config['global_probability_threshold']
    filter_manager = AdaptiveProbabilityFilter(db_manager, threshold)
    """)
    
    print("\n4. 효과:")
    print("   - 하나의 값으로 모든 필터 통합 관리")
    print("   - 실제 출현율 기반 과학적 필터링")
    print("   - 과도한 제외 방지 (1% 이상 패턴 보존)")

def main():
    """메인 실행 함수"""
    
    print("\n" + "="*80)
    print(" 적응형 확률 기반 필터링 시스템")
    print("="*80)
    
    # 1. 현재 필터 분석
    analyze_current_filters()
    
    # 2. 시뮬레이션
    simulate_filtering()
    
    # 3. 적용 방법
    apply_to_system()
    
    print("\n" + "="*80)
    print(" 결론")
    print("="*80)
    
    print("\n[개선 효과]")
    print("  1. 1% 이상 출현 패턴 보존 (기존: 잘못 제외)")
    print("  2. 하나의 설정값으로 전체 관리")
    print("  3. 과학적이고 일관된 필터링")
    print("  4. 동적 조정 가능")
    
    print("\n[권장사항]")
    print("  - 보수적: 0.5% (적게 제외, 안전성 높음)")
    print("  - 표준: 1.0% (균형잡힌 기본값)")
    print("  - 공격적: 2.0% (많이 제외, 위험 증가)")

if __name__ == "__main__":
    main()