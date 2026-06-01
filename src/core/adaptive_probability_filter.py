"""
통합 확률 기반 적응형 필터링 시스템
모든 필터가 하나의 확률 임계값을 공유하여 일관성 있는 필터링 수행
"""

import logging
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import numpy as np
import threading
from src.core.threshold_manager import get_threshold_manager

@dataclass
class FilterThreshold:
    """필터별 확률 임계값 관리"""
    filter_name: str
    pattern_description: str
    occurrence_rate: float  # 실제 출현율 (%)
    should_exclude: bool   # 제외 여부

class AdaptiveProbabilityFilter:
    """
    통합 확률 기반 필터링 시스템 - 싱글톤 패턴으로 구현

    핵심 아이디어:
    - 모든 필터가 하나의 확률 임계값 사용
    - 설정 파일에서 한 값만 변경하면 전체 적용
    - 실제 출현율 기반 동적 조정
    """
    # 클래스 변수 - 싱글톤 패턴 구현
    _instance = None
    _lock = threading.Lock()  # 스레드 안전성을 위한 락
    _initialized = False

    def __new__(cls, db_manager=None, probability_threshold=0.1, **kwargs):
        """싱글톤 패턴: 인스턴스 생성 제어"""
        if cls._instance is None:
            with cls._lock:
                # double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super(AdaptiveProbabilityFilter, cls).__new__(cls)
                    logging.debug("[AdaptiveProbabilityFilter] 새 인스턴스 생성")
        return cls._instance

    def __init__(self, db_manager, probability_threshold: float = 0.1, **kwargs):
        """
        Args:
            db_manager: 데이터베이스 매니저
            probability_threshold: 제외할 최대 확률 (%) - 기본값 0.1%
        """
        # 중복 초기화 방지
        if AdaptiveProbabilityFilter._initialized:
            logging.debug("[적응형 필터] 이미 초기화됨 - 중복 초기화 방지")
            return

        with AdaptiveProbabilityFilter._lock:
            # double-checked locking으로 중복 초기화 재검증
            if AdaptiveProbabilityFilter._initialized:
                logging.debug("[적응형 필터] 이미 초기화됨 (락 내부) - 중복 초기화 방지")
                return

            logging.info("[적응형 필터] 초기화 시작")
            self.db_manager = db_manager

            # ThresholdManager 연동 (Single Source of Truth)
            self.threshold_manager = get_threshold_manager()

            # Observer 패턴으로 자동 동기화 등록 (threshold 읽기 전에 등록 - race condition 방지)
            self.threshold_manager.register_observer(self._on_threshold_change)

            # Observer 등록 후 threshold 읽기 (동기화 보장)
            self.probability_threshold = self.threshold_manager.get_threshold()

            self.filter_thresholds = {}
            self.pattern_statistics = {}
            self.patterns = {}  # 패턴 저장용 딕셔너리 추가

            logging.debug(f"[적응형 필터] 통합 확률 임계값: {self.probability_threshold}% 이하 제외 (ThresholdManager 연동)")

            # FilterManager와 호환성을 위한 속성
            self.filters = {}  # 빈 필터 딕셔너리 (FilterValidator 호환성)

            # 초기화 완료 플래그 설정
            AdaptiveProbabilityFilter._initialized = True
            logging.info("[적응형 필터] 초기화 완료")

    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 초기화 (테스트용)"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False
            logging.info("[AdaptiveProbabilityFilter] 싱글톤 인스턴스 초기화 완료")

    @classmethod
    def is_initialized(cls):
        """초기화 상태 확인"""
        return cls._initialized

    def _on_threshold_change(self, param: str, old_value: Any, new_value: Any):
        """
        ThresholdManager에서 임계값 변경 시 자동 호출되는 Observer 콜백

        Args:
            param: 변경된 파라미터 이름
            old_value: 이전 값
            new_value: 새 값
        """
        if param == "threshold" or param == "global_probability_threshold":
            self.probability_threshold = float(new_value)
            logging.info(f"[적응형 필터] 임계값 자동 동기화: {float(old_value):.2f}% → {float(new_value):.2f}%")

    def _reload_patterns(self):
        """
        임계값 변경 시 패턴 재로드 (Optuna 최적화용)

        DEPRECATED: 패턴 재분석은 불필요 (임계값만 변경하면 됨)
        패턴 자체는 변하지 않으며, 임계값만 변경되면 필터링 기준이 달라짐
        """
        logging.debug("[패턴 재로드] DEPRECATED - 패턴 재분석 불필요 (임계값만 변경됨)")
        # 패턴 재분석하지 않음 - 기존 패턴 유지

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
            'dispersion': self._analyze_dispersion(winning_numbers),
            'outlier_detection': self._analyze_outlier_detection(winning_numbers),
            'balanced_quadrant': self._analyze_balanced_quadrant(winning_numbers)
        }

        self.pattern_statistics = stats
        self.patterns = stats  # patterns 속성도 업데이트
        return stats

    def _identify_low_probability_patterns(self) -> Dict[str, List]:
        """임계값 이하의 낮은 확률 패턴들을 식별"""
        low_prob_patterns = {}

        if not self.pattern_statistics:
            return low_prob_patterns

        # 홀짝 패턴
        low_prob_patterns['odd_even'] = []
        if 'odd_even' in self.pattern_statistics:
            for count, rate in self.pattern_statistics['odd_even'].get('odd_distribution', {}).items():
                if rate < self.probability_threshold:
                    low_prob_patterns['odd_even'].append(count)
            for count, rate in self.pattern_statistics['odd_even'].get('even_distribution', {}).items():
                if rate < self.probability_threshold and count not in low_prob_patterns['odd_even']:
                    low_prob_patterns['odd_even'].append(count)

        # 합계 패턴 - 범위로 저장
        low_prob_patterns['sum_range'] = []
        if 'sum_range' in self.pattern_statistics:
            for sum_val, rate in self.pattern_statistics['sum_range'].items():
                if rate < self.probability_threshold:
                    # 개별 값을 범위로 변환 (±5 범위)
                    low_prob_patterns['sum_range'].append((sum_val - 5, sum_val + 5))

        # 연속번호 패턴
        low_prob_patterns['consecutive'] = []
        if 'consecutive' in self.pattern_statistics:
            for length, rate in self.pattern_statistics['consecutive'].items():
                if rate < self.probability_threshold and length >= 4:
                    low_prob_patterns['consecutive'].append(length)

        # 이상치 탐지 패턴 (OutlierDetection)
        low_prob_patterns['outlier_detection'] = []
        if 'outlier_detection' in self.pattern_statistics:
            for outlier_count, rate in self.pattern_statistics['outlier_detection'].items():
                if rate < self.probability_threshold:
                    low_prob_patterns['outlier_detection'].append(outlier_count)

        # 사분면 균형 패턴 (BalancedQuadrant)
        low_prob_patterns['balanced_quadrant'] = []
        if 'balanced_quadrant' in self.pattern_statistics:
            for quadrant_count, rate in self.pattern_statistics['balanced_quadrant'].items():
                if rate < self.probability_threshold and quadrant_count >= 4:  # 4개 이상 몰림만 제외
                    low_prob_patterns['balanced_quadrant'].append(quadrant_count)

        return low_prob_patterns

    def generate_dynamic_criteria(self) -> Dict[str, Any]:
        """
        확률 임계값 기반으로 각 필터의 동적 기준 생성

        CRITICAL FIX (2024-12-06):
        - global_probability_threshold 기반으로 항상 재계산
        - YAML 저장값은 확률 기반 계산이 불가능한 필터에만 폴백으로 사용
        - 모든 확률 기반 필터는 threshold에 따라 동적으로 결정됨

        Returns:
            필터별 동적 기준값
        """
        # YAML에서 폴백용 설정 로드 (확률 계산 불가능한 필터용)
        yaml_fallback = {}
        try:
            import yaml
            config_path = 'configs/adaptive_filter_config.yaml'
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            yaml_fallback = config.get('dynamic_criteria', {})
        except Exception as e:
            logging.warning(f"[적응형 필터] YAML 폴백 로드 실패: {e}")

        # [HOT] CRITICAL: 항상 probability_threshold 기반으로 재계산
        logging.info(f"[적응형 필터] probability_threshold={self.probability_threshold}% 기반 dynamic_criteria 계산 시작")
        criteria = {}

        # [KEY] 핵심 수정: pattern_statistics가 초기화되지 않은 경우 YAML 폴백 사용
        required_keys = ['odd_even', 'consecutive', 'sum_range', 'multiple', 'average', 'match', 'max_gap', 'ten_section']
        if not self.pattern_statistics or not all(key in self.pattern_statistics for key in required_keys):
            logging.info(f"[적응형 필터] pattern_statistics 미초기화 - YAML 폴백 사용")
            return yaml_fallback

        # 1. 홀짝 필터 - 1% 이하만 제외
        odd_even_excluded = []
        odd_even_stats = self.pattern_statistics.get('odd_even', {})
        if odd_even_stats and 'odd_distribution' in odd_even_stats:
            for count, rate in odd_even_stats.get('odd_distribution', {}).items():
                if rate < self.probability_threshold:
                    odd_even_excluded.append(count)
            for count, rate in odd_even_stats.get('even_distribution', {}).items():
                if rate < self.probability_threshold and count not in odd_even_excluded:
                    odd_even_excluded.append(count)
            criteria['odd_even'] = {
                'excluded_counts': odd_even_excluded,
                'reason': f"{self.probability_threshold}% 미만 출현 패턴"
            }
        else:
            criteria['odd_even'] = yaml_fallback.get('odd_even', {'excluded_counts': [0, 6]})

        # 2. 연속번호 필터 - 1% 이하만 제외
        max_consecutive = 6
        consecutive_stats = self.pattern_statistics.get('consecutive', {})
        if consecutive_stats:
            for length, rate in consecutive_stats.items():
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
        # [v5 FIX #1] 카운트 몰림 필터는 threshold 상한 1.0%로 클램프(당첨번호 과잉 제외 방지).
        # 근거(53에이전트 감사): threshold가 2.0~3.0으로 오르면 출현율 3% 미만 패턴을 모두 제외하여
        # 실제 당첨번호 제거 → 통과율 84% 급락/롤백. 실측상 th<=1.0에서 통과율 98%+ 유지.
        ten_section_threshold = min(self.probability_threshold, 1.0)
        section_limits = {}
        for section in ['section1', 'section2', 'section3', 'section4', 'section5']:
            excluded = []
            if section in self.pattern_statistics['ten_section']:
                for count, rate in self.pattern_statistics['ten_section'][section].items():
                    if rate < ten_section_threshold:
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

        # threshold 이하인 패턴 모두 찾기 (원래 로직 복구)
        excluded_matches = []
        for match_count in [3, 4, 5, 6]:
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
        
        # 15. 분산도 필터 - 번호 자체의 표준편차 기준 (DispersionFilter와 동일)
        dispersion_dist = self.pattern_statistics.get('dispersion', {})
        # dispersion_dist의 키는 std_dev * 10 정수값 (번호 자체 표준편차)
        cumulative = 0
        min_std_dev = 5.0  # 기본 최소값
        for disp_val, rate in sorted(dispersion_dist.items()):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                min_std_dev = disp_val / 10.0  # 원래 표준편차로 복원
                break

        cumulative = 0
        max_std_dev = 20.0  # 기본 최대값
        for disp_val, rate in sorted(dispersion_dist.items(), reverse=True):
            cumulative += rate
            if cumulative > self.probability_threshold / 2:
                max_std_dev = disp_val / 10.0  # 원래 표준편차로 복원
                break

        criteria['dispersion'] = {
            'min_std_dev': min_std_dev,
            'max_std_dev': max_std_dev,
            'min_variance': min_std_dev ** 2,  # 표준편차로부터 분산 계산
            'max_variance': max_std_dev ** 2,
            'distribution': dispersion_dist,
            'reason': f"상하위 각 {self.probability_threshold/2}% 제외 (번호 자체 표준편차)"
        }

        # 16. 이상치 탐지 필터 (OutlierDetection) - 1% 이하 패턴 제외
        # [v5 FIX #1] threshold 상한 1.0%로 클램프 (당첨번호 과잉 제외 방지)
        outlier_threshold = min(self.probability_threshold, 1.0)
        outlier_dist = self.pattern_statistics.get('outlier_detection', {})
        max_outliers = 6  # 기본값 (모든 이상치 허용)

        # threshold 이하인 패턴 찾기 (높은 이상치 개수부터 검사)
        for outlier_count in [6, 5, 4, 3, 2, 1]:
            if outlier_count in outlier_dist and outlier_dist[outlier_count] <= outlier_threshold:
                # 이 개수 이상 이상치는 제외
                max_outliers = outlier_count - 1
                logging.info(f"[이상치 필터] {outlier_count}개 이상치 패턴이 {outlier_dist[outlier_count]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
                break

        criteria['outlier_detection'] = {
            'max_outliers': max_outliers,
            'iqr_multiplier': 1.0,  # 고정값
            'distribution': outlier_dist,
            'reason': f"{self.probability_threshold}% 이하 이상치 패턴 제외"
        }

        # 17. 사분면 균형 필터 (BalancedQuadrant) - 1% 이하 패턴 제외
        # [v5 FIX #1] threshold 상한 1.0%로 클램프 (당첨번호 과잉 제외 방지)
        quadrant_threshold = min(self.probability_threshold, 1.0)
        quadrant_dist = self.pattern_statistics.get('balanced_quadrant', {})
        max_per_quadrant = 6  # 기본값 (모든 분포 허용)

        # threshold 이하인 패턴 찾기 (높은 몰림부터 검사)
        for quadrant_count in [6, 5, 4, 3, 2]:
            if quadrant_count in quadrant_dist and quadrant_dist[quadrant_count] <= quadrant_threshold:
                # 이 개수 이상 몰림은 제외
                max_per_quadrant = quadrant_count - 1
                logging.info(f"[사분면 필터] 한 사분면 {quadrant_count}개 몰림 패턴이 {quadrant_dist[quadrant_count]:.2f}% (임계값 {self.probability_threshold}% 이하)이므로 제외")
                break

        criteria['balanced_quadrant'] = {
            'max_per_quadrant': max_per_quadrant,
            'distribution': quadrant_dist,
            'reason': f"{self.probability_threshold}% 이하 사분면 몰림 패턴 제외"
        }

        # [HOT] YAML 폴백: 확률 계산이 불가능한 필터에 대해 YAML 값 사용
        # (예: ac_value, fixed_step 등 패턴 통계가 없는 필터)
        fallback_filters = ['ac_value', 'fixed_step']
        for filter_name in fallback_filters:
            if filter_name not in criteria and filter_name in yaml_fallback:
                criteria[filter_name] = yaml_fallback[filter_name]
                logging.info(f"[적응형 필터] {filter_name}: YAML 폴백 값 사용")

        # [HOT] 요약 로그: 계산된 주요 기준값
        logging.info(f"[적응형 필터] === probability_threshold={self.probability_threshold}% 기반 계산 완료 ===")
        logging.info(f"  - match: max_match={criteria.get('match', {}).get('max_match', 'N/A')}")
        logging.info(f"  - consecutive: max_consecutive={criteria.get('consecutive', {}).get('max_consecutive', 'N/A')}")
        logging.info(f"  - sum_range: {criteria.get('sum_range', {}).get('min_sum', 'N/A')}~{criteria.get('sum_range', {}).get('max_sum', 'N/A')}")
        logging.info(f"  - section: max_numbers_per_section={criteria.get('section', {}).get('max_numbers_per_section', 'N/A')}")

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
        """매치 패턴 분석 - 랜덤 조합 vs 과거 당첨번호 시뮬레이션 (MatchFilter와 동일 방식)"""
        import random
        # 고정 시드 RNG: 실행마다 match 필터 기준(max_match)이 달라지는 비결정성 제거(재현성 확보)
        rng = random.Random(42)

        # 과거 당첨번호를 set 리스트로 변환
        winning_sets = [set(map(int, nums_str.split(','))) for nums_str in winning_numbers]

        if not winning_sets:
            return {i: 0.0 for i in range(7)}

        # 랜덤 조합을 생성하여 과거 당첨번호와 최대 일치 수 시뮬레이션 (고정 시드로 결정적)
        num_simulations = 1000
        match_distribution = {i: 0 for i in range(7)}  # 0개~6개 일치

        for _ in range(num_simulations):
            sample = set(rng.sample(range(1, 46), 6))
            # 모든 과거 당첨번호와 비교하여 최대 일치 수 산출
            max_match = max(len(sample & win_set) for win_set in winning_sets)
            match_distribution[max_match] = match_distribution.get(max_match, 0) + 1

        # 백분율로 변환
        match_percentage = {k: (v / num_simulations) * 100 for k, v in match_distribution.items()}

        logging.info(f"[매치 패턴 분석] 랜덤 {num_simulations}개 vs 당첨번호 {len(winning_sets)}개 시뮬레이션")
        for match_count, percentage in sorted(match_percentage.items()):
            logging.info(f"  최대 {match_count}개 일치: {percentage:.2f}%")

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
        """분산도 패턴 분석 - 번호 자체의 표준편차 (DispersionFilter와 동일)"""
        std_dev_dist = {}
        total = len(winning_numbers)

        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            # 번호 자체의 표준편차 계산 (DispersionFilter의 np.std와 동일)
            mean = sum(numbers) / len(numbers)
            variance = sum((n - mean) ** 2 for n in numbers) / len(numbers)
            std_dev = variance ** 0.5
            std_dev_int = round(std_dev * 10)  # 소수점 1자리까지 고려
            std_dev_dist[std_dev_int] = std_dev_dist.get(std_dev_int, 0) + 1

        # 백분율로 변환
        dispersion_percentage = {k: (v/total)*100 for k, v in sorted(std_dev_dist.items())}

        logging.info("[분산도 패턴 분석 - 번호 자체 표준편차]")
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
            except Exception as e:
                logging.error(f"필터 적용 실패: {e}")
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
            # [v5 FIX #2] [:200] 제거: ORDER BY round ASC라 '가장 오래된 200회'(약 20년전)를
            # 분석하던 버그. 핵심 전략(전체 1214회 역사 패턴)상 전체 당첨번호로 분석해야 정확/안정적.
            winning_numbers = self.db_manager.get_all_winning_numbers()
            
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
        필터링 후 남은 조합 개수 반환 (실제 DB 조회 우선)

        Args:
            latest_round: 최신 회차

        Returns:
            필터링 후 남은 조합 개수
        """
        try:
            total_combinations = 8145060  # 45C6 = 8,145,060

            # 1. 실제 DB에서 필터링된 조합 수 조회 시도
            if hasattr(self.db_manager, 'combinations_db'):
                try:
                    # get_filtered_count 메서드 시도
                    if hasattr(self.db_manager.combinations_db, 'get_filtered_count'):
                        actual_count = self.db_manager.combinations_db.get_filtered_count(latest_round)
                        if actual_count > 0:
                            logging.info(f"[적응형 필터] 실제 필터링 결과: {total_combinations:,}개 → {actual_count:,}개")
                            return actual_count

                    # get_filtered_combinations 메서드 시도 (개수만)
                    if hasattr(self.db_manager.combinations_db, 'get_filtered_combinations'):
                        filtered = self.db_manager.combinations_db.get_filtered_combinations(latest_round)
                        if filtered:
                            actual_count = len(filtered)
                            logging.info(f"[적응형 필터] 실제 필터링 결과: {total_combinations:,}개 → {actual_count:,}개")
                            return actual_count
                except Exception as e:
                    logging.debug(f"DB 필터 카운트 조회 실패: {e}")

            # 2. 마지막 필터링 결과 캐시에서 조회
            if hasattr(self, '_last_filtered_count') and self._last_filtered_count > 0:
                logging.info(f"[적응형 필터] 캐시된 필터링 결과: {self._last_filtered_count:,}개")
                return self._last_filtered_count

            # 3. 실제 제외 개수가 기록되어 있으면 계산
            if hasattr(self, '_last_excluded_count'):
                actual_count = total_combinations - self._last_excluded_count
                if actual_count > 0:
                    logging.info(f"[적응형 필터] 계산된 필터링 결과: {total_combinations:,}개 → {actual_count:,}개")
                    return actual_count

            # 4. 기본값: 전체 조합 (필터링 실패 시)
            logging.warning(f"[적응형 필터] 실제 필터링 결과를 찾을 수 없음 - 전체 조합 반환: {total_combinations:,}개")
            return total_combinations

        except Exception as e:
            logging.error(f"필터링 카운트 계산 실패: {e}")
            return 8145060  # 전체 조합 반환
    
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

    def _analyze_outlier_detection(self, winning_numbers: List[str]) -> Dict:
        """조합 내부 IQR 기반 이상치 패턴 분석"""
        outlier_dist = {i: 0 for i in range(7)}  # 0~6개 이상치
        total = len(winning_numbers)

        iqr_multiplier = 1.0  # 기본 승수

        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))

            # 조합 내부 IQR 계산
            q1 = np.percentile(numbers, 25)
            q3 = np.percentile(numbers, 75)
            iqr = q3 - q1

            # 이상치 범위
            lower_bound = q1 - iqr_multiplier * iqr
            upper_bound = q3 + iqr_multiplier * iqr

            # 이상치 개수
            outlier_count = sum(
                1 for num in numbers
                if num < lower_bound or num > upper_bound
            )

            outlier_dist[outlier_count] += 1

        return {k: (v/total)*100 for k, v in outlier_dist.items()}

    def _analyze_balanced_quadrant(self, winning_numbers: List[str]) -> Dict:
        """4분면 균형 패턴 분석"""
        quadrant_dist = {i: 0 for i in range(7)}  # 0~6개 (한 사분면 최대값)
        total = len(winning_numbers)

        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))

            # 4분면 분할 (1-11, 12-22, 23-33, 34-45)
            quadrants = [
                sum(1 for n in numbers if 1 <= n <= 11),
                sum(1 for n in numbers if 12 <= n <= 22),
                sum(1 for n in numbers if 23 <= n <= 33),
                sum(1 for n in numbers if 34 <= n <= 45),
            ]

            max_in_quadrant = max(quadrants)
            quadrant_dist[max_in_quadrant] += 1

        return {k: (v/total)*100 for k, v in quadrant_dist.items()}