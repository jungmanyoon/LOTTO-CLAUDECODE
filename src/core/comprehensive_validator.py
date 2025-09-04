"""
통합 검증 시스템
모든 필터, 백테스팅, 예측을 통합하여 검증하는 시스템
"""

import logging
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

class ComprehensiveValidator:
    """통합 검증 클래스"""
    
    def __init__(self, filter_manager, db_manager):
        """
        초기화
        
        Args:
            filter_manager: FilterManager 인스턴스
            db_manager: DatabaseManager 인스턴스
        """
        self.filter_manager = filter_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self.validation_history = []
        
        # 검증 결과 저장 디렉토리
        self.results_dir = "results/validation"
        os.makedirs(self.results_dir, exist_ok=True)
    
    def validate_combination(self, numbers: List[int], round_num: int = None) -> Dict[str, Any]:
        """
        단일 조합에 대한 종합 검증
        
        Args:
            numbers: 검증할 번호 리스트 (6개)
            round_num: 회차 번호 (선택)
        
        Returns:
            검증 결과 딕셔너리
        """
        result = {
            'numbers': numbers,
            'round_num': round_num,
            'timestamp': datetime.now().isoformat(),
            'passed_filters': [],
            'failed_filters': [],
            'overall_pass': True,
            'statistics': {},
            'warnings': []
        }
        
        # 기본 통계 계산
        result['statistics'] = self._calculate_statistics(numbers)
        
        # 각 필터별로 직접 검증
        for filter_name, filter_obj in self.filter_manager.filters.items():
            try:
                # 조합을 필터 형식으로 변환
                combination_str = ','.join(map(str, sorted(numbers)))
                combinations_list = [combination_str]
                
                # 필터 적용
                try:
                    # round_num이 있으면 사용, 없으면 기본값
                    if round_num is not None:
                        filtered = filter_obj.apply(combinations_list, round_num)
                    else:
                        filtered = filter_obj.apply(combinations_list, 0)
                    
                    # 필터 통과 여부 확인
                    passed = len(filtered) > 0
                    
                    if passed:
                        result['passed_filters'].append(filter_name)
                    else:
                        result['failed_filters'].append({
                            'name': filter_name,
                            'reason': self._analyze_filter_failure(filter_name, filter_obj, numbers)
                        })
                        result['overall_pass'] = False
                        
                except Exception as e:
                    # 필터 적용 중 에러 발생
                    self.logger.debug(f"필터 {filter_name} 적용 중 예외: {e}")
                    # 에러가 발생한 필터는 건너뛰고 경고 추가
                    result['warnings'].append(f"{filter_name} 필터 검증 실패: {str(e)}")
                    
            except Exception as e:
                self.logger.error(f"필터 {filter_name} 검증 중 오류: {e}")
                result['warnings'].append(f"{filter_name} 필터 오류: {str(e)}")
        
        # 검증 결과 저장
        self.validation_history.append(result)
        
        return result
    
    def _calculate_statistics(self, numbers: List[int]) -> Dict[str, Any]:
        """번호 조합의 통계 계산"""
        stats = {}
        
        # 기본 통계
        stats['sum'] = sum(numbers)
        stats['mean'] = np.mean(numbers)
        stats['std'] = np.std(numbers)
        stats['min'] = min(numbers)
        stats['max'] = max(numbers)
        stats['range'] = max(numbers) - min(numbers)
        
        # 홀짝 분포
        odd_count = len([n for n in numbers if n % 2 == 1])
        stats['odd_count'] = odd_count
        stats['even_count'] = 6 - odd_count
        
        # 연속 번호 체크
        sorted_nums = sorted(numbers)
        consecutive_count = 0
        max_consecutive = 0
        current_consecutive = 1
        
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        stats['max_consecutive'] = max_consecutive
        
        # 구간 분포 (1-10, 11-20, 21-30, 31-40, 41-45)
        sections = [0, 0, 0, 0, 0]
        for num in numbers:
            if num <= 10:
                sections[0] += 1
            elif num <= 20:
                sections[1] += 1
            elif num <= 30:
                sections[2] += 1
            elif num <= 40:
                sections[3] += 1
            else:
                sections[4] += 1
        stats['section_distribution'] = sections
        
        # 끝자리 분포
        last_digits = {}
        for num in numbers:
            last_digit = num % 10
            last_digits[last_digit] = last_digits.get(last_digit, 0) + 1
        stats['last_digits'] = last_digits
        
        return stats
    
    def _analyze_filter_failure(self, filter_name: str, filter_obj: Any, numbers: List[int]) -> str:
        """필터 실패 이유 분석"""
        
        # 필터별 상세 분석
        if 'sum_range' in filter_name.lower():
            total_sum = sum(numbers)
            if hasattr(filter_obj, 'criteria'):
                min_sum = filter_obj.criteria.get('min_sum', 67)
                max_sum = filter_obj.criteria.get('max_sum', 209)
                if total_sum < min_sum:
                    return f"합계 {total_sum}이 최소값 {min_sum}보다 작음"
                elif total_sum > max_sum:
                    return f"합계 {total_sum}이 최대값 {max_sum}보다 큼"
            return f"합계 {total_sum} 범위 벗어남"
        
        elif 'consecutive' in filter_name.lower():
            sorted_nums = sorted(numbers)
            max_consecutive = 1
            current = 1
            for i in range(len(sorted_nums) - 1):
                if sorted_nums[i+1] - sorted_nums[i] == 1:
                    current += 1
                    max_consecutive = max(max_consecutive, current)
                else:
                    current = 1
            
            if hasattr(filter_obj, 'criteria'):
                max_allowed = filter_obj.criteria.get('max_consecutive', 4)
                return f"연속 번호 {max_consecutive}개 (최대 {max_allowed}개 허용)"
            return f"연속 번호 {max_consecutive}개 포함"
        
        elif 'odd_even' in filter_name.lower():
            odd_count = len([n for n in numbers if n % 2 == 1])
            even_count = 6 - odd_count
            return f"홀수 {odd_count}개, 짝수 {even_count}개"
        
        elif 'section' in filter_name.lower():
            sections = [0, 0, 0, 0, 0]
            for num in numbers:
                if num <= 10:
                    sections[0] += 1
                elif num <= 20:
                    sections[1] += 1
                elif num <= 30:
                    sections[2] += 1
                elif num <= 40:
                    sections[3] += 1
                else:
                    sections[4] += 1
            return f"구간 분포: {sections}"
        
        else:
            return "필터 조건 불만족"
    
    def batch_validate(self, combinations: List[List[int]], round_num: int = None) -> Dict[str, Any]:
        """
        여러 조합을 일괄 검증
        
        Args:
            combinations: 검증할 조합 리스트
            round_num: 회차 번호 (선택)
        
        Returns:
            일괄 검증 결과
        """
        results = {
            'total': len(combinations),
            'passed': 0,
            'failed': 0,
            'details': [],
            'filter_statistics': {},
            'timestamp': datetime.now().isoformat()
        }
        
        # 각 조합 검증
        for combo in combinations:
            validation = self.validate_combination(combo, round_num)
            
            if validation['overall_pass']:
                results['passed'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append(validation)
            
            # 필터별 통계 집계
            for failed in validation['failed_filters']:
                filter_name = failed['name']
                if filter_name not in results['filter_statistics']:
                    results['filter_statistics'][filter_name] = {
                        'failed_count': 0,
                        'reasons': []
                    }
                results['filter_statistics'][filter_name]['failed_count'] += 1
                results['filter_statistics'][filter_name]['reasons'].append(failed['reason'])
        
        # 통과율 계산
        results['pass_rate'] = (results['passed'] / results['total']) * 100 if results['total'] > 0 else 0
        
        return results
    
    def validate_with_adaptive_threshold(self, numbers: List[int], threshold: float = 1.0) -> Dict[str, Any]:
        """
        적응형 임계값을 고려한 검증
        
        Args:
            numbers: 검증할 번호 리스트
            threshold: 확률 임계값 (%)
        
        Returns:
            적응형 검증 결과
        """
        result = self.validate_combination(numbers)
        
        # 통계 기반 확률 계산
        stats = result['statistics']
        
        # 합계 확률 (간단한 정규분포 가정)
        mean_sum = 138  # 1-45의 6개 평균 합
        std_sum = 30   # 표준편차 (추정값)
        sum_z_score = abs(stats['sum'] - mean_sum) / std_sum
        sum_probability = self._z_score_to_probability(sum_z_score)
        
        # 홀짝 확률
        odd_even_probability = self._calculate_odd_even_probability(stats['odd_count'])
        
        # 연속 번호 확률
        consecutive_probability = self._calculate_consecutive_probability(stats['max_consecutive'])
        
        # 전체 확률 (간단한 곱셈 규칙)
        overall_probability = sum_probability * odd_even_probability * consecutive_probability * 100
        
        result['probability_analysis'] = {
            'sum_probability': sum_probability * 100,
            'odd_even_probability': odd_even_probability * 100,
            'consecutive_probability': consecutive_probability * 100,
            'overall_probability': overall_probability,
            'threshold': threshold,
            'adaptive_pass': overall_probability >= threshold
        }
        
        return result
    
    def _z_score_to_probability(self, z_score: float) -> float:
        """Z-score를 확률로 변환 (간단한 근사)"""
        # 표준정규분포 근사
        if z_score > 3:
            return 0.001
        elif z_score > 2:
            return 0.023
        elif z_score > 1:
            return 0.159
        else:
            return 0.5
    
    def _calculate_odd_even_probability(self, odd_count: int) -> float:
        """홀짝 분포 확률 계산"""
        # 이항분포 근사
        probabilities = {
            0: 0.0156,  # 모두 짝수
            1: 0.0938,
            2: 0.2344,
            3: 0.3125,  # 가장 높은 확률
            4: 0.2344,
            5: 0.0938,
            6: 0.0156   # 모두 홀수
        }
        return probabilities.get(odd_count, 0.01)
    
    def _calculate_consecutive_probability(self, max_consecutive: int) -> float:
        """연속 번호 확률 계산"""
        # 경험적 확률
        probabilities = {
            1: 0.50,   # 연속 없음
            2: 0.40,   # 2개 연속
            3: 0.08,   # 3개 연속
            4: 0.015,  # 4개 연속
            5: 0.004,  # 5개 연속
            6: 0.001   # 모두 연속
        }
        return probabilities.get(max_consecutive, 0.001)
    
    def save_validation_report(self, filename: str = None) -> str:
        """검증 보고서 저장"""
        if not filename:
            filename = f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = os.path.join(self.results_dir, filename)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_validations': len(self.validation_history),
            'validation_history': self.validation_history[-100:],  # 최근 100개만
            'summary': self._generate_summary()
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"검증 보고서 저장 완료: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"보고서 저장 실패: {e}")
            return None
    
    def _generate_summary(self) -> Dict[str, Any]:
        """검증 요약 생성"""
        if not self.validation_history:
            return {}
        
        total = len(self.validation_history)
        passed = sum(1 for v in self.validation_history if v['overall_pass'])
        failed = total - passed
        
        # 필터별 실패 통계
        filter_failures = {}
        for validation in self.validation_history:
            for failed_filter in validation['failed_filters']:
                name = failed_filter['name']
                filter_failures[name] = filter_failures.get(name, 0) + 1
        
        return {
            'total_validations': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'filter_failure_counts': filter_failures,
            'most_failed_filter': max(filter_failures.items(), key=lambda x: x[1])[0] if filter_failures else None
        }