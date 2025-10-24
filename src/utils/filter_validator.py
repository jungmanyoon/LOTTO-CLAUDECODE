# -*- coding: utf-8 -*-
"""
필터 검증 시스템
예측된 번호가 실제로 필터 시스템을 통과하는지 검증
"""
import logging
from typing import List, Dict, Tuple, Any, Optional


class FilterValidator:
    """필터 검증 시스템"""

    def __init__(self, db_manager, filter_manager):
        """
        Args:
            db_manager: 데이터베이스 관리자
            filter_manager: 필터 관리자
        """
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        self.logger = logging.getLogger(__name__)

        # 진짜 중요한 필터들 (절대 완화하면 안 되는 필터)
        self.critical_filters = {
            'odd_even': '홀짝 비율',
            'sum_range': '번호 합 범위',
            'consecutive': '연속 번호',
            'max_gap': '최대 간격'
        }

        # 완화 가능한 필터들 (ML 예측에 대해서만)
        self.relaxable_filters = {
            'average': '평균값',
            'prime_composite': '소수/합성수',
            'fixed_step': '고정 간격',
            'multiple': '배수',
            'ten_section': '10의 자리',
            'digit_sum': '숫자 합',
            'dispersion': '분산',
            'last_digit': '마지막 자리',
            'arithmetic_sequence': '등차수열',
            'geometric_sequence': '등비수열',
            'section': '섹션 분포'
        }

    def validate_prediction(self, numbers: List[int], round_num: int,
                          is_ml_prediction: bool = False,
                          model_confidence: float = 0.0) -> Dict[str, Any]:
        """
        예측 번호의 필터 통과 여부를 검증

        Args:
            numbers: 예측 번호 리스트
            round_num: 회차 번호
            is_ml_prediction: ML 예측 여부
            model_confidence: 모델 신뢰도

        Returns:
            검증 결과 딕셔너리
        """
        validation_result = {
            'is_valid': True,
            'passed_filters': [],
            'failed_filters': [],
            'critical_failures': [],
            'relaxable_failures': [],
            'should_exclude': False,
            'exclusion_reason': '',
            'filter_bypass_applied': False,
            'recommendation': 'accept'
        }

        try:
            # 기본 유효성 검사
            if not self._basic_validation(numbers):
                validation_result['is_valid'] = False
                validation_result['should_exclude'] = True
                validation_result['exclusion_reason'] = '기본 유효성 검사 실패'
                validation_result['recommendation'] = 'reject'
                return validation_result

            # 필터 가져오기
            filters = self._get_filters()

            # 각 필터별로 검증
            for filter_name, filter_obj in filters.items():
                filter_result = self._test_single_filter(
                    filter_name, filter_obj, numbers, round_num
                )

                if filter_result['passed']:
                    validation_result['passed_filters'].append({
                        'name': filter_name,
                        'description': self._get_filter_description(filter_name)
                    })
                else:
                    failure_info = {
                        'name': filter_name,
                        'description': self._get_filter_description(filter_name),
                        'reason': filter_result.get('reason', '알 수 없음')
                    }
                    validation_result['failed_filters'].append(failure_info)

                    # 중요 필터 vs 완화 가능 필터 분류
                    if filter_name in self.critical_filters:
                        validation_result['critical_failures'].append(failure_info)
                    elif filter_name in self.relaxable_filters:
                        validation_result['relaxable_failures'].append(failure_info)

            # ML 예측에 대한 특별 처리
            if is_ml_prediction:
                bypass_result = self._apply_ml_bypass_logic(
                    validation_result, model_confidence
                )
                validation_result.update(bypass_result)

            # 최종 판정
            final_decision = self._make_final_decision(validation_result, is_ml_prediction)
            validation_result.update(final_decision)

        except Exception as e:
            self.logger.error(f"필터 검증 중 오류: {e}")
            validation_result['is_valid'] = False
            validation_result['should_exclude'] = True
            validation_result['exclusion_reason'] = f'검증 오류: {str(e)}'
            validation_result['recommendation'] = 'reject'

        return validation_result

    def _get_filters(self) -> Dict:
        """필터 매니저에서 필터 가져오기"""
        # IntegratedFilterManager 처리
        if hasattr(self.filter_manager, 'filter_manager'):
            # IntegratedFilterManager의 경우
            if hasattr(self.filter_manager.filter_manager, 'filters'):
                return self.filter_manager.filter_manager.filters
        # 일반 FilterManager 처리
        elif hasattr(self.filter_manager, 'filters'):
            return self.filter_manager.filters
        return {}

    def _basic_validation(self, numbers: List[int]) -> bool:
        """기본 유효성 검사"""
        return (
            len(numbers) == 6 and
            len(set(numbers)) == 6 and  # 중복 없음
            all(1 <= n <= 45 for n in numbers) and  # 범위 내
            min(numbers) != max(numbers)  # 모두 같지 않음
        )

    def _test_single_filter(self, filter_name: str, filter_obj: Any,
                           numbers: List[int], round_num: int) -> Dict[str, Any]:
        """단일 필터 테스트"""
        try:
            if hasattr(filter_obj, 'apply') and callable(filter_obj.apply):
                numbers_str = ','.join(map(str, sorted(numbers)))
                filtered_result = filter_obj.apply([numbers_str], round_num)

                return {
                    'passed': len(filtered_result) > 0,
                    'reason': '필터 기준 충족' if len(filtered_result) > 0 else '필터 기준 미충족'
                }
            else:
                return {'passed': True, 'reason': '필터 적용 불가'}

        except Exception as e:
            self.logger.error(f"필터 {filter_name} 테스트 실패: {e}")
            return {'passed': False, 'reason': f'필터 오류: {str(e)}'}

    def _apply_ml_bypass_logic(self, validation_result: Dict,
                              model_confidence: float) -> Dict[str, Any]:
        """ML 예측에 대한 우회 로직 적용"""
        bypass_result = {
            'filter_bypass_applied': False,
            'bypass_details': []
        }

        # 고신뢰도 모델 판정 (더 엄격한 기준)
        is_high_confidence = model_confidence >= 0.8  # 80% 이상만 고신뢰도로 인정

        if is_high_confidence:
            # 고신뢰도일 때만 완화 가능 필터 우회
            bypassed_filters = []
            for failure in validation_result['relaxable_failures']:
                bypassed_filters.append(failure['name'])
                bypass_result['bypass_details'].append(
                    f"완화 가능 필터 '{failure['name']}' 우회 (고신뢰도: {model_confidence:.1%})"
                )

            if bypassed_filters:
                bypass_result['filter_bypass_applied'] = True
                # 완화 가능 필터 실패를 제거
                validation_result['relaxable_failures'] = []
                validation_result['failed_filters'] = [
                    f for f in validation_result['failed_filters']
                    if f['name'] not in bypassed_filters
                ]

        return bypass_result

    def _make_final_decision(self, validation_result: Dict,
                           is_ml_prediction: bool) -> Dict[str, Any]:
        """최종 판정"""
        decision_result = {}

        # 중요 필터 실패가 있으면 무조건 제외
        if validation_result['critical_failures']:
            decision_result.update({
                'should_exclude': True,
                'exclusion_reason': f"중요 필터 실패: {', '.join([f['name'] for f in validation_result['critical_failures']])}",
                'recommendation': 'reject'
            })
        # 완화 가능 필터만 실패한 경우
        elif validation_result['relaxable_failures']:
            if is_ml_prediction and validation_result.get('filter_bypass_applied', False):
                # ML 예측이고 우회 적용된 경우 허용
                decision_result.update({
                    'should_exclude': False,
                    'exclusion_reason': '',
                    'recommendation': 'accept_with_warning'
                })
            else:
                # 일반 예측이거나 우회 미적용시 제외
                decision_result.update({
                    'should_exclude': True,
                    'exclusion_reason': f"완화 가능 필터 실패: {', '.join([f['name'] for f in validation_result['relaxable_failures']])}",
                    'recommendation': 'reject'
                })
        # 모든 필터 통과
        else:
            decision_result.update({
                'should_exclude': False,
                'exclusion_reason': '',
                'recommendation': 'accept'
            })

        return decision_result

    def _get_filter_description(self, filter_name: str) -> str:
        """필터 설명 반환"""
        descriptions = {**self.critical_filters, **self.relaxable_filters}
        return descriptions.get(filter_name, filter_name)

    def validate_against_filtered_pool(self, numbers: List[int],
                                     round_num: int) -> Dict[str, Any]:
        """
        필터링된 조합 풀과 비교하여 검증

        Args:
            numbers: 검증할 번호
            round_num: 회차 번호

        Returns:
            검증 결과
        """
        result = {
            'in_filtered_pool': False,
            'pool_size': 0,
            'exclusion_percentage': 0.0,
            'message': ''
        }

        try:
            # 필터링된 조합 가져오기
            filtered_combos = self.db_manager.combinations_db.get_filtered_combinations(round_num)
            if not filtered_combos:
                result['message'] = '필터링된 조합 풀이 없습니다.'
                return result

            result['pool_size'] = len(filtered_combos)

            # 번호 조합이 필터링된 풀에 있는지 확인
            numbers_str = ','.join(map(str, sorted(numbers)))
            result['in_filtered_pool'] = numbers_str in filtered_combos

            # 전체 조합 대비 필터링 비율 계산
            total_combinations = 8145060  # C(45,6)
            result['exclusion_percentage'] = (1 - len(filtered_combos) / total_combinations) * 100

            if result['in_filtered_pool']:
                result['message'] = f'필터링된 풀({len(filtered_combos):,}개)에 포함됨'
            else:
                result['message'] = f'필터링된 풀({len(filtered_combos):,}개)에서 제외됨 - 필터에 의해 제거된 조합'

        except Exception as e:
            self.logger.error(f"필터링 풀 검증 실패: {e}")
            result['message'] = f'검증 실패: {str(e)}'

        return result

    def get_filter_summary(self) -> Dict[str, Any]:
        """필터 시스템 요약 정보 반환"""
        filters = self._get_filters()
        return {
            'total_filters': len(filters),
            'critical_filters': list(self.critical_filters.keys()),
            'relaxable_filters': list(self.relaxable_filters.keys()),
            'filter_descriptions': {**self.critical_filters, **self.relaxable_filters}
        }