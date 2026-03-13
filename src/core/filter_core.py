"""
FilterCore - 핵심 필터링 로직

Phase 2.1: FilterManager에서 분리된 핵심 필터 관리 컴포넌트
- 필터 등록/해제
- 단일 필터 적용
- 필터 criteria 재계산

Author: Claude Code Refactoring
Date: 2025-12-08
"""

import os
import logging
import yaml
import time
from typing import Any, Dict, List, Optional, Set
from tqdm import tqdm

from .filter_interfaces import IFilterCore, IConfigObserver
from ..filters.base_filter import BaseFilter
from ..utils.config_manager import ConfigManager


class FilterCore(IFilterCore, IConfigObserver):
    """핵심 필터링 로직 구현

    필터 등록, 단일 필터 적용, criteria 관리를 담당합니다.

    Attributes:
        db_manager: 데이터베이스 관리자
        filters: 등록된 필터 딕셔너리 {name: BaseFilter}
        config_manager: 설정 관리자
        filter_efficiency: 필터 효율성 가중치
        current_filter_version: 필터 버전
    """

    def __init__(self, db_manager, config_manager: Optional[ConfigManager] = None):
        """FilterCore 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            config_manager: 설정 관리자 (없으면 새로 생성)
        """
        self.db_manager = db_manager
        self.filters: Dict[str, BaseFilter] = {}
        self._filter_results: Dict[str, Dict] = {}
        self.current_filter_version = "1.3"

        # 설정 관리자
        self.config_manager = config_manager or ConfigManager()
        self.filter_efficiency = self.config_manager.get_filter_efficiency()

        logging.debug("[FilterCore] 초기화 완료")

    def register_filter(self, filter_name: str, filter_instance: Any) -> None:
        """필터 등록

        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스 (BaseFilter)
        """
        self.filters[filter_name] = filter_instance
        logging.debug(f"[FilterCore] '{filter_name}' 필터 등록됨")

    def unregister_filter(self, name: str) -> bool:
        """필터 등록 해제

        Args:
            name: 필터 이름

        Returns:
            성공 여부
        """
        if name in self.filters:
            del self.filters[name]
            logging.info(f"[FilterCore] 필터 '{name}' 제거 완료")
            return True
        return False

    def get_registered_filters(self) -> List[str]:
        """등록된 필터 목록 반환"""
        return list(self.filters.keys())

    def reset_filters(self) -> None:
        """모든 필터 초기화"""
        self.filters.clear()
        self._filter_results.clear()
        logging.info("[FilterCore] 필터 초기화 완료")

    def apply_single_filter(
        self,
        filter_name: str,
        filter_instance: Any,
        combinations: List[str],
        round_num: int
    ) -> Optional[List[str]]:
        """단일 필터 적용

        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스
            combinations: 조합 리스트
            round_num: 회차 번호

        Returns:
            필터링된 조합 리스트 또는 None (실패 시)
        """
        try:
            start_time = time.time()
            initial_count = len(combinations)

            # 필터 적용
            if hasattr(filter_instance, 'apply'):
                filtered = filter_instance.apply(combinations, round_num)
            elif hasattr(filter_instance, 'filter'):
                filtered = filter_instance.filter(combinations, round_num)
            else:
                logging.warning(f"[FilterCore] '{filter_name}' 필터에 적용 메서드가 없습니다")
                return combinations

            elapsed_time = time.time() - start_time
            filtered_count = len(filtered) if filtered else 0
            excluded_count = initial_count - filtered_count

            # 필터 결과 저장
            self._filter_results[filter_name] = {
                'initial_count': initial_count,
                'filtered_count': filtered_count,
                'excluded_count': excluded_count,
                'exclude_percent': (excluded_count / initial_count * 100) if initial_count > 0 else 0,
                'elapsed_time': elapsed_time
            }

            logging.debug(
                f"[FilterCore] {filter_name}: {initial_count:,} → {filtered_count:,} "
                f"({excluded_count:,}개 제외, {elapsed_time:.2f}초)"
            )

            return filtered

        except Exception as e:
            logging.error(f"[FilterCore] '{filter_name}' 필터 적용 중 오류: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    def recalculate_filter_criteria(self, new_threshold: float) -> None:
        """임계값 변경 시 모든 필터의 criteria 재계산

        Args:
            new_threshold: 새로운 확률 임계값 (%)
        """
        try:
            logging.info(f"[FilterCore] 임계값 {new_threshold}% 기준으로 필터 criteria 재계산 시작")

            updated_count = 0

            for filter_name, filter_instance in self.filters.items():
                try:
                    # ConfigManager에서 해당 필터의 새 criteria 가져오기
                    new_criteria = self.config_manager.get_filter_criteria(filter_name)

                    if new_criteria:
                        old_criteria = filter_instance.criteria.copy() if hasattr(filter_instance, 'criteria') else {}

                        # criteria 업데이트
                        filter_instance.criteria = new_criteria

                        # 변경 사항 로깅
                        if old_criteria != new_criteria:
                            logging.debug(f"  [{filter_name}] criteria 업데이트됨")
                            updated_count += 1

                except Exception as e:
                    logging.warning(f"  [{filter_name}] criteria 업데이트 실패: {e}")

            logging.info(f"[FilterCore] 필터 criteria 재계산 완료: {updated_count}개 필터 업데이트됨")

        except Exception as e:
            logging.error(f"[FilterCore] 필터 criteria 재계산 중 오류: {e}")

    def on_config_change(self, param: str, old_value: Any, new_value: Any) -> None:
        """설정 변경 시 호출 (Observer 패턴)

        Args:
            param: 변경된 파라미터 이름
            old_value: 이전 값
            new_value: 새 값
        """
        logging.info(
            f"[FilterCore] 설정 변경 감지: {param} = "
            f"{float(old_value) if isinstance(old_value, (int, float)) else old_value} → "
            f"{float(new_value) if isinstance(new_value, (int, float)) else new_value}"
        )

        # 필터 효율성 업데이트 (임계값 변경 시 재계산 필요)
        if param in ("threshold", "global_probability_threshold"):
            self._update_filter_efficiency()
            logging.debug("[FilterCore] 필터 효율성 재계산 완료")

            # 필터 criteria 재계산
            self.recalculate_filter_criteria(float(new_value))

    def _update_filter_efficiency(self) -> None:
        """필터 효율성 가중치 업데이트"""
        try:
            # 기본 가중치 설정 (실측 제거율 기반 - 높을수록 먼저 실행)
            # 제거율 높은 필터 먼저 실행 → 후속 필터 처리 대상 감소 → 전체 시간 단축
            default_efficiency = {
                'sum_range': 0.50,             # 제거율 높음 - 최우선
                'dispersion': 0.45,            # 24,788개 제외 (0.31%)
                'odd_even': 0.42,              # 제거율 중상
                'max_gap': 0.40,               # 제거율 중상
                'last_digit': 0.38,            # 23,451개 제외 (0.29%)
                'section': 0.35,               # 제거율 중간
                'prime_composite': 0.32,       # 제거율 중간
                'ten_section': 0.30,           # 제거율 중간
                'multiple': 0.28,              # 제거율 중간
                'average': 0.25,               # 제거율 중간
                'fixed_step': 0.22,            # 제거율 중하
                'match': 0.03,                 # O(n*m) 순수 Python 루프 → 매우 느림, 마지막에 실행
                'balanced_quadrant': 0.15,     # 1,663개 제외 (0.02%)
                'consecutive': 0.12,           # 0개 제외 - 거의 무의미
                'ac_value': 0.10,              # 8,911개 제외 (0.11%) - 느리고 제거율 낮음
                'geometric_sequence': 0.08,    # 79개 제외 - 거의 무의미
                'arithmetic_sequence': 0.06,   # 8,130개 제외 (0.10%) - 느림
                'outlier_detection': 0.05,     # 제거율 낮음 - 벡터화됨
                'ml_prediction': 0.04,         # 예측기 없으면 패스스루 - 후순위
                'digit_sum': 0.03,             # 363개 제외 (0.004%) - 가장 느리고 제거율 최저
            }

            # 설정 파일의 효율성 값으로 덮어쓰기
            try:
                config_efficiency = self.config_manager.get_filter_efficiency()
                if config_efficiency:
                    for filter_name, efficiency in config_efficiency.items():
                        if filter_name in self.filters:
                            self.filter_efficiency[filter_name] = efficiency
            except Exception as e:
                logging.warning(f"설정 파일의 필터 효율성 적용 실패: {e}")

            # 모든 필터에 효율성 값이 있는지 확인
            for filter_name in self.filters.keys():
                if filter_name not in self.filter_efficiency:
                    if filter_name in default_efficiency:
                        self.filter_efficiency[filter_name] = default_efficiency[filter_name]
                    else:
                        self.filter_efficiency[filter_name] = 0.2

        except Exception as e:
            logging.error(f"[FilterCore] 필터 효율성 업데이트 중 오류: {e}")

    def auto_register_filters(self) -> None:
        """설정에서 활성화된 필터 자동 등록"""
        # 현재 지원되는 모든 필터 클래스 임포트
        from ..filters.match_filter import MatchFilter
        from ..filters.odd_even_filter import OddEvenFilter
        from ..filters.consecutive_filter import ConsecutiveFilter
        from ..filters.sum_range_filter import SumRangeFilter
        from ..filters.fixed_step_filter import FixedStepFilter
        from ..filters.last_digit_filter import LastDigitFilter
        from ..filters.max_gap_filter import MaxGapFilter
        from ..filters.section_filter import SectionFilter
        from ..filters.average_filter import AverageFilter
        from ..filters.multiple_filter import MultipleFilter
        from ..filters.ten_section_filter import TenSectionFilter
        from ..filters.arithmetic_sequence_filter import ArithmeticSequenceFilter
        from ..filters.geometric_sequence_filter import GeometricSequenceFilter
        from ..filters.prime_composite_filter import PrimeCompositeFilter
        from ..filters.digit_sum_filter import DigitSumFilter
        from ..filters.dispersion_filter import DispersionFilter
        from ..filters.outlier_detection_filter import OutlierDetectionFilter
        from ..filters.balanced_quadrant_filter import BalancedQuadrantFilter
        from ..filters.ac_value_filter import ACValueFilter

        # ML 예측 필터 (선택적)
        try:
            from ..filters.ml_prediction_filter import MLPredictionFilter
            ML_FILTER_AVAILABLE = True
        except ImportError:
            ML_FILTER_AVAILABLE = False
            logging.debug("ML 예측 필터를 사용할 수 없습니다.")

        # 필터 클래스 맵핑
        filter_classes = {
            'match': MatchFilter,
            'odd_even': OddEvenFilter,
            'consecutive': ConsecutiveFilter,
            'sum_range': SumRangeFilter,
            'fixed_step': FixedStepFilter,
            'last_digit': LastDigitFilter,
            'max_gap': MaxGapFilter,
            'section': SectionFilter,
            'average': AverageFilter,
            'multiple': MultipleFilter,
            'ten_section': TenSectionFilter,
            'arithmetic_sequence': ArithmeticSequenceFilter,
            'geometric_sequence': GeometricSequenceFilter,
            'prime_composite': PrimeCompositeFilter,
            'digit_sum': DigitSumFilter,
            'dispersion': DispersionFilter,
            'outlier_detection': OutlierDetectionFilter,
            'balanced_quadrant': BalancedQuadrantFilter,
            'ac_value': ACValueFilter
        }

        # ML 예측 필터 추가 (사용 가능한 경우)
        if ML_FILTER_AVAILABLE:
            filter_classes['ml_prediction'] = MLPredictionFilter

        # Config 파일에서 활성화된 필터만 로드
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'configs', 'adaptive_filter_config.yaml'
        )

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # filters 섹션에서 True로 설정된 필터만 활성화
            filter_config = config.get('filters', {})
            enabled_filters = [
                name for name, enabled in filter_config.items()
                if enabled and name in filter_classes
            ]

            # ML 필터는 별도로 추가 (config에 없을 수 있음)
            if ML_FILTER_AVAILABLE and 'ml_prediction' not in enabled_filters:
                if filter_config.get('ml_prediction', True):
                    enabled_filters.append('ml_prediction')

            disabled_count = len(filter_classes) - len(enabled_filters)
            logging.info(f"[필터 설정] {len(enabled_filters)}개 활성화, {disabled_count}개 비활성화")

        except Exception as e:
            logging.warning(f"Config 파일 읽기 실패, 모든 필터 활성화: {e}")
            enabled_filters = list(filter_classes.keys())

        # 필터 등록
        registered_count = 0
        failed_filters = []

        for filter_name in enabled_filters:
            criteria = self.config_manager.get_filter_criteria(filter_name)

            try:
                filter_instance = filter_classes[filter_name](self.db_manager, criteria)
                self.register_filter(filter_name, filter_instance)
                registered_count += 1
            except Exception as e:
                failed_filters.append(filter_name)
                logging.error(f"'{filter_name}' 필터 등록 실패: {e}")

        # 요약 정보
        if failed_filters:
            logging.warning(f"[필터 초기화] {registered_count}/{len(enabled_filters)}개 필터 활성화 (실패: {', '.join(failed_filters)})")
        else:
            logging.info(f"[필터 초기화] {registered_count}개 필터 활성화 완료")

        # 필터 등록 완료 후 효율성 가중치 업데이트 (필터 순서 최적화에 필요)
        self._update_filter_efficiency()

    def get_filter_results(self) -> Dict[str, Dict]:
        """필터 적용 결과 반환"""
        return self._filter_results.copy()

    def get_filter_efficiency(self) -> Dict[str, float]:
        """필터 효율성 가중치 반환"""
        return self.filter_efficiency.copy()
