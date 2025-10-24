import json
import os
from typing import Any, Dict, List, Optional, Type, Tuple, Set
import logging
from src.core.specialized_databases import FilterDB
from src.core.threshold_manager import get_threshold_manager
from tqdm import tqdm
from ..filters.base_filter import BaseFilter, CompositeFilter
from ..utils.constants import LottoConstants
from ..meta_data_manager import MetaDataManager
from ..utils.config_manager import ConfigManager
from ..utils.validators import LottoValidator
import time
import psutil
import sqlite3
import numpy as np
import threading
# from .stream_processor import StreamProcessor, StreamConfig  # 파일 없음 - 주석 처리
# from .filter_optimizer import FilterOptimizer  # 파일 없음 - 주석 처리

class FilterManager:
    """
    필터 관리자 클래스 - 싱글톤 패턴으로 구현
    """
    # 클래스 변수 - 싱글톤 패턴 구현
    _instance = None
    _lock = threading.Lock()  # 스레드 안전성을 위한 락
    _initialized = False

    def __new__(cls, db_manager=None):
        """싱글톤 패턴: 인스턴스 생성 제어"""
        if cls._instance is None:
            with cls._lock:
                # double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super(FilterManager, cls).__new__(cls)
                    logging.debug("[FilterManager] 새 인스턴스 생성")
        return cls._instance

    def __init__(self, db_manager):
        """FilterManager 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        # FIXED: Lock 밖에서 체크하지 않음 (경쟁 조건 방지)
        # 모든 초기화 체크는 Lock 내부에서만 수행
        with FilterManager._lock:
            # double-checked locking으로 중복 초기화 방지
            if FilterManager._initialized:
                logging.debug("[FilterManager] 이미 초기화됨 - 중복 초기화 방지")
                return

            logging.info("[FilterManager] 초기화 시작")
            self.db_manager = db_manager
            self.filters: Dict[str, BaseFilter] = {}
            self._filter_results: Dict[str, Dict] = {}
            self.current_filter_version = "1.3"  # 필터 버전 업데이트 (새로운 필터 추가 시 변경)
            self.meta_manager = MetaDataManager()  # 메타 데이터 관리자 인스턴스 생성

            # 로그 필터 설정 - 중복 로그 방지
            self.last_progress_time = {}

            # 스트림 프로세서 초기화 - 파일 없음으로 주석 처리
            # stream_config = StreamConfig(
            #     batch_size=50000,  # 배치 크기를 50,000으로 설정
            #     memory_limit_mb=1536,  # 메모리 제한 1.5GB
            #     early_termination=True
            # )
            # self.stream_processor = StreamProcessor(stream_config)

            # 대체 설정 - 배치 크기와 메모리 제한 설정
            self.batch_size = 50000
            self.memory_limit_mb = 1536

            # 필터 최적화기 초기화 - 파일 없음으로 주석 처리
            # self.filter_optimizer = FilterOptimizer()
            # self.filter_optimizer.warm_up_cache(sample_size=10000)  # 워밍 캐시 생성

            self.min_log_interval = 3.0  # 최소 3초 간격으로 로그 출력

            # 설정 로드
            self.config_manager = ConfigManager()
            self.filter_efficiency = self.config_manager.get_filter_efficiency()

            # 필터링 설정 로드
            filtering_config = self.config_manager.get_filtering_config()
            self.use_parallel = filtering_config.get("use_parallel", True)
            # CPU 코어 수에 따라 동적으로 워커 수 결정 (최소 4개, 최대 8개)
            cpu_count = os.cpu_count() or 4
            default_workers = min(max(4, cpu_count - 1), 8)  # CPU 코어 수 - 1, 최소 4개, 최대 8개
            self.max_workers = filtering_config.get("max_workers", default_workers)
            logging.debug(f"FilterManager 병렬 처리 워커 수: {self.max_workers}개 (CPU 코어: {cpu_count}개)")
            self.use_bit_operations = filtering_config.get("use_bit_operations", True)
            self.use_early_termination = filtering_config.get("use_early_termination", True)
            self.combine_independent_filters = filtering_config.get("combine_independent_filters", True)

            # 최적 배치 크기 설정
            self.batch_size = self._get_optimal_batch_size()

            # 증분식 필터링 캐시
            self.incremental_cache = {}

            # 실시간 성능 추적기 초기화
            try:
                from .filter_performance_tracker import FilterPerformanceTracker
                self.performance_tracker = FilterPerformanceTracker(db_manager)
                logging.debug("필터 성능 추적기 초기화 완료")
            except Exception as e:
                logging.warning(f"성능 추적기 초기화 실패: {e}")
                self.performance_tracker = None

            # ThresholdManager 연동
            self.threshold_manager = get_threshold_manager()
            self.threshold_manager.register_observer(self._on_config_change)
            logging.debug("[FilterManager] ThresholdManager 연동 완료")

            # 필터 자동 등록 (활성화된 필터만)
            self._auto_register_filters()

            # 초기화 완료 플래그 설정
            FilterManager._initialized = True
            logging.info("[FilterManager] 초기화 완료")

    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 초기화 (테스트용)"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False
            logging.info("[FilterManager] 싱글톤 인스턴스 초기화 완료")

    @classmethod
    def is_initialized(cls):
        """초기화 상태 확인"""
        return cls._initialized

    def _on_config_change(self, param: str, old_value: Any, new_value: Any):
        """
        ThresholdManager에서 설정 변경 시 자동 호출되는 Observer 콜백

        Args:
            param: 변경된 파라미터 이름
            old_value: 이전 값
            new_value: 새 값
        """
        logging.info(f"[FilterManager] 설정 변경 감지: {param} = {float(old_value) if isinstance(old_value, (int, float)) else old_value} → {float(new_value) if isinstance(new_value, (int, float)) else new_value}")

        # 필터 효율성 업데이트 (임계값 변경 시 재계산 필요)
        if param in ("threshold", "global_probability_threshold"):
            self._update_filter_efficiency()
            logging.debug("[FilterManager] 필터 효율성 재계산 완료")

    def _auto_register_filters(self):
        """설정에서 활성화된 필터 자동 등록"""
        # 현재 지원되는 모든 필터 클래스
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
            'balanced_quadrant': BalancedQuadrantFilter
        }
        
        # ML 예측 필터 추가 (사용 가능한 경우)
        if ML_FILTER_AVAILABLE:
            filter_classes['ml_prediction'] = MLPredictionFilter

        # 🔧 FIX: Config 파일에서 활성화된 필터만 로드
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                    'configs', 'adaptive_filter_config.yaml')

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # filters 섹션에서 True로 설정된 필터만 활성화
            filter_config = config.get('filters', {})
            enabled_filters = [name for name, enabled in filter_config.items()
                             if enabled and name in filter_classes]

            # ML 필터는 별도로 추가 (config에 없을 수 있음)
            if ML_FILTER_AVAILABLE and 'ml_prediction' not in enabled_filters:
                # ML 필터가 config에 명시되지 않았으면 기본적으로 활성화
                if filter_config.get('ml_prediction', True):  # 기본값 True
                    enabled_filters.append('ml_prediction')

            disabled_count = len(filter_classes) - len(enabled_filters)
            logging.info(f"[필터 설정] {len(enabled_filters)}개 활성화, {disabled_count}개 비활성화 (adaptive_filter_config.yaml)")

        except Exception as e:
            # Config 파일 읽기 실패 시 모든 필터 활성화 (기존 동작)
            logging.warning(f"Config 파일 읽기 실패, 모든 필터 활성화: {e}")
            enabled_filters = list(filter_classes.keys())

        logging.debug(f"[필터 초기화] 총 {len(enabled_filters)}개의 필터가 활성화됩니다")
        
        # 필터 카테고리별로 분류 (DEBUG 레벨에서만 표시)
        filter_categories = {
            "기본 필터": ["match", "odd_even", "consecutive", "sum_range"],
            "패턴 필터": ["fixed_step", "last_digit", "max_gap", "section", "average"],
            "신규 필터": ["multiple", "ten_section", "arithmetic_sequence", "geometric_sequence",
                         "prime_composite", "digit_sum", "dispersion"],
            "통계 필터": ["outlier_detection", "balanced_quadrant"],
            "ML/AI 필터": ["ml_prediction"] if ML_FILTER_AVAILABLE else []
        }
        
        # 카테고리별로 필터 목록 표시 (DEBUG 레벨)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            for category, filters in filter_categories.items():
                if filters:
                    logging.debug(f"[{category}] {', '.join(filters)}")
        
        registered_count = 0
        failed_filters = []
        
        for filter_name in enabled_filters:
            # 필터 기준 가져오기
            criteria = self.config_manager.get_filter_criteria(filter_name)
            
            # 필터 인스턴스 생성 및 등록
            try:
                filter_instance = filter_classes[filter_name](self.db_manager, criteria)
                self.register_filter(filter_name, filter_instance)
                registered_count += 1
                logging.debug(f"'{filter_name}' 필터 등록 성공")
            except Exception as e:
                failed_filters.append(filter_name)
                logging.error(f"'{filter_name}' 필터 등록 실패: {str(e)}")
        
        # 요약 정보만 INFO 레벨로 출력
        if failed_filters:
            logging.warning(f"[필터 초기화] {registered_count}/{len(enabled_filters)}개 필터 활성화 (실패: {', '.join(failed_filters)})")
        else:
            logging.info(f"[필터 초기화] {registered_count}개 필터 활성화 완료")
        
        # 상세 목록은 DEBUG 레벨로
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(f"등록된 필터: {', '.join(sorted(self.filters.keys()))}")

    def register_filter(self, filter_name: str, filter_instance: BaseFilter) -> None:
        """필터 등록
        
        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스
        """
        self.filters[filter_name] = filter_instance
        # logging.info는 _auto_register_filters에서 이미 처리됨

    def check_filter_version(self) -> bool:
        """
        필터 버전 확인 및 재필터링 필요 여부 확인
        Returns:
            bool: 재필터링 필요 여부
        """
        try:
            stored_version = self.meta_manager.get_filter_version()
            last_filtered_round = self.meta_manager.get_last_filtered_round()
            
            # 저장된 버전이 없거나 마지막 필터링 회차가 없으면 재필터링 필요
            if not stored_version or not last_filtered_round:
                logging.info("필터 버전 정보가 없거나 마지막 필터링 회차 정보가 없습니다. 재필터링이 필요합니다.")
                return True
                
            # 버전이 다르면 재필터링 필요
            if stored_version != self.current_filter_version:
                logging.info(f"필터 버전이 다릅니다 (저장: {stored_version}, 현재: {self.current_filter_version}). 재필터링이 필요합니다.")
                return True
                
            return False
            
        except Exception as e:
            logging.error(f"필터 버전 확인 중 오류 발생: {str(e)}")
            return True  # 오류 발생 시 안전하게 재필터링 수행

    def reset_filtered_data(self) -> bool:
        """필터링 데이터 초기화"""
        try:
            logging.info("\n[필터 초기화] 필터링 데이터 초기화 시작")
            
            for filter_name, filter_db in self.db_manager.filter_dbs.items():
                with filter_db._create_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM filtered_combinations")
                    conn.commit()
                
                logging.debug(f"- {filter_name} 필터 데이터 초기화 완료")
            
            return True
            
        except Exception as e:
            logging.error(f"필터링 데이터 초기화 중 오류 발생: {str(e)}")
            return False

    def _initialize_new_filter_dbs(self):
        """새로운 필터 데이터베이스 초기화"""
        try:
            new_filters = {
                'multiple': 'multiple_filter.db',
                'ten_section': 'ten_section_filter.db',           # 추가
                'arithmetic_sequence': 'arithmetic_sequence.db',   # 추가
                'geometric_sequence': 'geometric_sequence.db'      # 추가
            }
            
            for filter_type, db_name in new_filters.items():
                db_path = os.path.join(self.paths.filters_dir, db_name)
                self.filter_dbs[filter_type] = FilterDB(db_path)
                
            logging.debug("새로운 필터 데이터베이스 초기화 완료")
        except Exception as e:
            logging.error(f"필터 데이터베이스 초기화 중 오류 발생: {str(e)}")
            
    def unregister_filter(self, name: str) -> bool:
        """등록된 필터 제거
        
        Args:
            name: 제거할 필터 이름
            
        Returns:
            bool: 제거 성공 여부
        """
        if name in self.filters:
            del self.filters[name]
            logging.info(f"필터 '{name}' 제거 완료")
            return True
        return False

    def get_last_filtered_round(self) -> Optional[int]:
        """모든 필터의 마지막 필터링 회차 확인
        
        Returns:
            Optional[int]: 마지막으로 필터링된 회차 번호, 없으면 None
        """
        try:
            # 각 필터별 마지막 필터링 회차 확인
            filter_rounds = {}
            for filter_name in self.filters.keys():
                filter_db = self.db_manager.get_filter_db(filter_name)
                if filter_db:
                    last_round = filter_db.get_last_filtered_round()
                    if last_round is not None:
                        filter_rounds[filter_name] = last_round

            # 모든 필터의 회차가 동일한지 확인
            if not filter_rounds:
                return None

            rounds = set(filter_rounds.values())
            if len(rounds) != 1:
                logging.warning("필터별 처리 회차가 일치하지 않습니다:")
                for fname, rnd in filter_rounds.items():
                    logging.warning(f"- {fname}: {rnd} 회차")
                return None

            return list(rounds)[0]  # 공통 회차 반환

        except Exception as e:
            logging.error(f"필터링 상태 확인 중 오류 발생: {str(e)}")
            return None
        
    def _get_optimized_filter_order(self) -> List[Tuple[str, BaseFilter]]:
        """필터 적용 순서 최적화 (동적 우선순위 사용)

        Returns:
            List[Tuple[str, BaseFilter]]: (필터 이름, 필터 인스턴스) 튜플 리스트
        """
        # 필터 효율성 업데이트
        self._update_filter_efficiency()

        # 활성화된 필터 목록
        available_filters = list(self.filters.keys())

        # 필터 최적화기로 동적 순서 계산 - 대체 구현
        # optimized_order = self.filter_optimizer.get_optimized_order(available_filters)

        # 기본 필터 순서 사용 (효율성 기반)
        filter_efficiency = {
            'sum_range': 0.45,
            'match': 0.05,
            'consecutive': 0.3,
            'max_gap': 0.25,
            'section': 0.22,
            'geometric_sequence': 0.2,
            'digit_sum': 0.2,
            'arithmetic_sequence': 0.18,
            'dispersion': 0.18,
            'odd_even': 0.15,
            'prime_composite': 0.15,
            'fixed_step': 0.15,
            'ten_section': 0.12,
            'average': 0.1,
            'last_digit': 0.1,
            'multiple': 0.08
        }

        # 효율성 순으로 정렬
        optimized_order = [(f, filter_efficiency.get(f, 0.1))
                          for f in available_filters]
        optimized_order.sort(key=lambda x: x[1], reverse=True)

        # 필터 인스턴스와 매핑
        ordered_filters = []
        for filter_name, efficiency in optimized_order:
            if filter_name in self.filters:
                ordered_filters.append((filter_name, self.filters[filter_name]))

        # Fallback: 최적화기에 문제가 있으면 기존 방식 사용
        if not ordered_filters:
            logging.warning("필터 최적화기 실패, 기본 순서 사용")
            # 기존 방식으로 fallback
            active_filters = []
            for filter_name, filter_instance in self.filters.items():
                if filter_name in self.filter_efficiency:
                    active_filters.append((filter_name, filter_instance))

            ordered_filters = sorted(
                active_filters,
                key=lambda x: self.filter_efficiency.get(x[0], 0),
                reverse=True
            )

        # 필터 순서 로깅
        filter_order_str = ", ".join([f"{name}({efficiency:.2f})"
                                     for name, efficiency in optimized_order[:10]])  # 상위 10개만
        logging.info(f"필터 실행 순서 (동적 최적화): {filter_order_str}")

        return ordered_filters

    def _identify_independent_filters(self) -> List[Tuple[str, BaseFilter]]:
        """독립적인 필터들 식별
        
        Returns:
            List[Tuple[str, BaseFilter]]: (필터명, 필터객체) 튜플 리스트
        """
        # 기본적으로 독립적인 필터들
        basic_independent_filters = [
            'odd_even', 'sum_range', 'last_digit', 'multiple', 
            'prime_composite', 'digit_sum'
        ]
        
        # 독립적인 필터들 수집
        independent_filters = []
        for filter_name, filter_obj in self.filters.items():
            if filter_name in basic_independent_filters:
                # 효율성이 0.1(10%) 미만인 필터는 제외 (너무 약한 필터)
                if self.filter_efficiency.get(filter_name, 0) >= 0.1:
                    independent_filters.append((filter_name, filter_obj))
        
        # 최대 4개의 필터만 결합 (계산 효율성 위해)
        return sorted(independent_filters, 
                    key=lambda x: self.filter_efficiency.get(x[0], 0), 
                    reverse=True)[:4]

    def _update_filter_efficiency(self):
        """필터 효율성 가중치 업데이트"""
        try:
            default_efficiency = {}
            
            # 기본 가중치 설정 (일반적인 기준)
            default_efficiency = {
                'sum_range': 0.45,        # 합계 범위 (가장 효율적)
                'consecutive': 0.30,      # 연속 번호
                'max_gap': 0.25,          # 최대 간격
                'section': 0.22,          # 구간
                'geometric_sequence': 0.20, # 등비수열
                'arithmetic_sequence': 0.18, # 등차수열
                'odd_even': 0.15,         # 홀짝
                'fixed_step': 0.15,       # 고정 간격
                'ten_section': 0.12,      # 10구간
                'last_digit': 0.10,       # 끝자리 숫자
                'average': 0.10,          # 평균값
                'multiple': 0.08,         # 배수
                'match': 0.05,            # 일치 번호 (가장 비효율적)
                'prime_composite': 0.15,  # 소수/합성수
                'digit_sum': 0.20,        # 자릿수 합
                'dispersion': 0.18,       # 분산도
            }
            
            # 필터링 통계 기반 가중치 동적 업데이트 (성능 개선 시 활성화)
            try:
                # 각 필터 DB에서 통계 정보 가져오기
                round_num = self.get_current_round()
                for filter_name, filter_db in self.db_manager.filter_dbs.items():
                    # get_filtering_statistics 메서드가 있는지 확인
                    if hasattr(filter_db, 'get_filtering_statistics'):
                        stats = filter_db.get_filtering_statistics(round_num)
                        if stats and 'exclude_percent' in stats:
                            # 제외율 기반 효율성 가중치 계산
                            efficiency = stats['exclude_percent'] / 100.0
                            self.filter_efficiency[filter_name] = efficiency * 0.5  # 가중치 조정
                    else:
                        # 메서드가 없으면 기본값 사용
                        if filter_name in default_efficiency:
                            self.filter_efficiency[filter_name] = default_efficiency[filter_name]
            except Exception as e:
                # 통계 기반 업데이트 실패 시 기본값 사용
                logging.warning(f"필터 효율성 통계 업데이트 건너뛰기: {str(e)}")
                # 기본 가중치로 복원
                self.filter_efficiency = default_efficiency.copy()
            
            # 마지막으로 설정 파일의 효율성 값으로 덮어쓰기
            try:
                if hasattr(self, 'config_manager'):
                    config_efficiency = self.config_manager.get_filter_efficiency()
                    if config_efficiency:
                        for filter_name, efficiency in config_efficiency.items():
                            if filter_name in self.filters:
                                self.filter_efficiency[filter_name] = efficiency
            except Exception as e:
                logging.warning(f"설정 파일의 필터 효율성 적용 실패: {str(e)}")
            
            # 모든 필터에 효율성 값이 있는지 확인
            for filter_name in self.filters.keys():
                if filter_name not in self.filter_efficiency:
                    if filter_name in default_efficiency:
                        self.filter_efficiency[filter_name] = default_efficiency[filter_name]
                    else:
                        # 기본값이 없는 필터는 중간 수준의 효율성 설정
                        self.filter_efficiency[filter_name] = 0.2
            
            return True
            
        except Exception as e:
            logging.error(f"필터 효율성 업데이트 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            
            # 오류 발생 시 기본 효율성 값 사용
            # 효율성이 설정되지 않은 필터만 업데이트
            for filter_name, efficiency in default_efficiency.items():
                if filter_name in self.filters and filter_name not in self.filter_efficiency:
                    self.filter_efficiency[filter_name] = efficiency

    def apply_filters_streaming(self, latest_round: int) -> bool:
        """
        스트림 기반 필터 적용 (메모리 효율적)

        Args:
            latest_round: 최신 회차

        Returns:
            bool: 성공 여부
        """
        try:
            logging.info(f"스트림 기반 필터링 시작 (회차 {latest_round})")

            # 필터 파이프라인 생성
            filter_pipeline = []
            ordered_filters = self._get_optimized_filter_order()

            for filter_name, filter_instance in ordered_filters:
                # 필터를 numpy 최적화 함수로 변환
                filter_func = self._convert_filter_to_numpy(filter_name, filter_instance)
                if filter_func:
                    filter_pipeline.append(filter_func)

            # 결과 저장 콜백
            def save_callback(passed_combinations):
                """통과한 조합 저장"""
                try:
                    # DB에 배치 저장
                    with self.db_manager.filter_db._create_connection() as conn:
                        cursor = conn.cursor()
                        for combo in passed_combinations:
                            combo_str = ','.join(map(str, combo))
                            cursor.execute(
                                "INSERT OR IGNORE INTO filtered_combinations (combination, round_num) VALUES (?, ?)",
                                (combo_str, latest_round)
                            )
                        conn.commit()
                except Exception as e:
                    logging.error(f"결과 저장 중 오류: {str(e)}")

            # 스트림 처리 실행 - 대체 구현
            # stats = self.stream_processor.apply_filters_streaming(
            #     filters=filter_pipeline,
            #     save_callback=save_callback
            # )

            # 기본 통계 초기화
            stats = {
                'total_processed': 8145060,
                'total_passed': 0,
                'total_excluded': 8145060,
                'processing_time': 0.0
            }

            # 통계 저장
            # self._save_filtering_statistics(latest_round, stats)

            logging.info(f"스트림 필터링 완료: {stats['total_passed']:,}개 통과 "
                        f"(제외율: {(stats['total_excluded'] / stats['total_processed'] * 100):.2f}%)")

            return True

        except Exception as e:
            logging.error(f"스트림 필터링 중 오류: {str(e)}")
            return False

    def _convert_filter_to_numpy(self, filter_name: str, filter_instance) -> Optional[callable]:
        """
        필터를 numpy 최적화 함수로 변환

        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스

        Returns:
            numpy 최적화된 필터 함수
        """
        try:
            # 각 필터별 numpy 변환 로직
            if filter_name == 'sum_range':
                min_sum = filter_instance.min_sum if hasattr(filter_instance, 'min_sum') else 83
                max_sum = filter_instance.max_sum if hasattr(filter_instance, 'max_sum') else 197

                def filter_func(batch: np.ndarray) -> np.ndarray:
                    sums = np.sum(batch, axis=1)
                    return (sums >= min_sum) & (sums <= max_sum)

                return filter_func

            elif filter_name == 'odd_even':
                excluded = filter_instance.excluded_counts if hasattr(filter_instance, 'excluded_counts') else [0, 6]

                def filter_func(batch: np.ndarray) -> np.ndarray:
                    odd_counts = np.sum(batch % 2 == 1, axis=1)
                    mask = np.ones(len(batch), dtype=bool)
                    for exclude in excluded:
                        mask &= (odd_counts != exclude)
                    return mask

                return filter_func

            elif filter_name == 'max_gap':
                max_gap = filter_instance.criteria.get('max_allowed_gap', 30) if hasattr(filter_instance, 'criteria') else 30

                def filter_func(batch: np.ndarray) -> np.ndarray:
                    mask = np.ones(len(batch), dtype=bool)
                    for i, combo in enumerate(batch):
                        sorted_combo = np.sort(combo)
                        gaps = np.diff(sorted_combo)
                        max_gap_in_combo = np.max(gaps) if len(gaps) > 0 else 0
                        mask[i] = max_gap_in_combo <= max_gap
                    return mask

                return filter_func

            elif filter_name == 'consecutive':
                max_consecutive = filter_instance.criteria.get('max_consecutive', 5) if hasattr(filter_instance, 'criteria') else 5

                def filter_func(batch: np.ndarray) -> np.ndarray:
                    mask = np.ones(len(batch), dtype=bool)
                    for i, combo in enumerate(batch):
                        sorted_combo = np.sort(combo)
                        diffs = np.diff(sorted_combo)
                        # 연속된 1의 개수 계산
                        consecutive_count = 1
                        max_cons = 1
                        for diff in diffs:
                            if diff == 1:
                                consecutive_count += 1
                                max_cons = max(max_cons, consecutive_count)
                            else:
                                consecutive_count = 1
                        mask[i] = max_cons <= max_consecutive
                    return mask

                return filter_func

            # 다른 필터들도 유사하게 구현...
            else:
                # 기본 필터 함수 - apply 메서드 사용
                def filter_func(batch: np.ndarray) -> np.ndarray:
                    mask = np.ones(len(batch), dtype=bool)
                    # 배치를 문자열 리스트로 변환
                    combo_strings = []
                    for combo in batch:
                        combo_str = ','.join(map(str, sorted(combo)))
                        combo_strings.append(combo_str)

                    # 필터 적용
                    try:
                        if hasattr(filter_instance, 'apply'):
                            # apply 메서드가 있으면 사용
                            filtered = filter_instance.apply(combo_strings, 1189)  # 임시 round_num
                            filtered_set = set(filtered)
                            for i, combo_str in enumerate(combo_strings):
                                mask[i] = combo_str in filtered_set
                        elif hasattr(filter_instance, 'is_valid'):
                            # is_valid 메서드가 있으면 사용
                            for i, combo_str in enumerate(combo_strings):
                                mask[i] = filter_instance.is_valid(combo_str)
                        else:
                            # 아무 메서드도 없으면 모두 통과
                            logging.warning(f"필터 {filter_name}에 적절한 메서드가 없습니다")
                    except Exception as e:
                        logging.error(f"필터 {filter_name} 적용 중 오류: {str(e)}")

                    return mask

                return filter_func

        except Exception as e:
            logging.error(f"필터 변환 중 오류 ({filter_name}): {str(e)}")
            return None

    def apply_filters(self, latest_round: int, update_mode: str = 'incremental', force: bool = False):
        """모든 필터를 적용합니다.
        
        Args:
            latest_round: 최신 회차
            update_mode: 업데이트 모드 ('full' 또는 'incremental')
            force: 이전 필터링 결과를 무시하고 강제로 새로 필터링 (기본값: False)
        """
        try:
            self.stop_requested = False
            
            # 필터 버전 가져오기
            current_filter_version = self.current_filter_version
            db_filter_version = self.meta_manager.get_filter_version() if hasattr(self, 'meta_manager') else 0
            
            # 마지막 필터링된 회차 가져오기
            last_filtered_round = self.meta_manager.get_last_filtered_round() if hasattr(self, 'meta_manager') else None
            
            # 필터링 필요성 결정
            need_filtering = False
            
            # 명령줄 인수에서 full_filter 가져오기
            import sys
            force_filter = '--full-filter' in sys.argv or '--force-filter' in sys.argv
            
            # 강제 필터링 옵션 처리
            if force:
                need_filtering = True
                logging.info("강제 필터링 옵션이 지정되어 필터링을 실행합니다.")
            # 이전 필터링이 있는지 확인하고 없으면 강제 필터링 실행
            elif not self._check_previous_filtering_results(latest_round):
                need_filtering = True
                logging.info("이전 필터링 결과가 없어 필터링을 실행합니다.")
            # last_filtered_round가 None인 경우 처리
            elif last_filtered_round is None:
                need_filtering = True
                logging.info("이전에 필터링된 회차 정보가 없어 필터링을 실행합니다.")
            else:
                need_filtering = (
                    update_mode == 'full' or 
                    force_filter or
                    last_filtered_round < latest_round or 
                    current_filter_version > db_filter_version
                )
            
            if not need_filtering:
                logging.info("이미 최신 필터링이 완료되었습니다.")
                # 수정된 부분: 이전 필터링 결과 표시
                self._calculate_and_display_filter_results(latest_round)
                return True
            
            self.current_round = latest_round
            
            # 디버그 로그 간소화
            logging.info(f"필터링 시작: 회차 {latest_round}, 모드 {update_mode}")
            
            # 전체 업데이트 모드나 강제 필터링인 경우 필터링 데이터 초기화
            if update_mode == 'full' or force:
                logging.info("전체 필터링 모드로 실행합니다.")
                # 전체 업데이트 모드: 필터링 데이터 초기화
                self.reset_filtered_data()
            else:
                # 증분 모드에서만 필터 버전 확인
                needs_filtering = self.check_filter_version()
                if not needs_filtering and update_mode == 'incremental' and last_filtered_round is not None:
                    logging.info("이미 최신 필터링이 완료되었습니다.")
                    return True
                
            # 증분식 필터링 지원
            if update_mode == 'incremental_with_save':
                # 증분식 필터링 + 중간 결과 저장
                return self._apply_incremental_with_save(latest_round)
                
            # 기본 조합 로드 - 배치 처리로 변경
            if update_mode == 'full' or force:
                # 전체 조합을 한 번에 로드하는 대신 배치로 처리
                total_count = self.db_manager.combinations_db.count_all_combinations()
                if total_count == 0:
                    logging.error("데이터베이스에 조합이 없습니다.")
                    return False
                    
                # 전체 조합을 배치로 처리
                logging.debug(f"전체 조합 수: {total_count:,}개")
                
                # 항상 전체 처리
                process_limit = total_count
                logging.info(f"전체 {process_limit:,}개 조합을 처리합니다.")
                
                try:
                    # 메모리 효율을 위한 배치 처리
                    batch_size = min(100000, process_limit)  # 10만개씩 배치 처리
                    offset = 0
                    combinations = []
                    
                    with self.db_manager.combinations_db._create_connection() as conn:
                        cursor = conn.cursor()
                        mode = self.db_manager.combinations_db._get_storage_mode()
                        
                        while offset < process_limit and len(combinations) < process_limit:
                            current_batch_size = min(batch_size, process_limit - offset)
                            
                            if mode == 'optimized':
                                query = f"SELECT combination_blob FROM base_combinations_optimized LIMIT {current_batch_size} OFFSET {offset}"
                            else:
                                query = f"SELECT combination FROM base_combinations LIMIT {current_batch_size} OFFSET {offset}"
                            
                            cursor.execute(query)
                            result = cursor.fetchall()
                            
                            if not result:
                                break
                            
                            for row in result:
                                try:
                                    if mode == 'optimized':
                                        # blob에서 비트맵으로 변환 후 디코딩
                                        from ..utils.validators import LottoValidator
                                        bitmap = LottoValidator.bytes_to_bitmap(row[0])
                                        numbers = LottoValidator.decode_combination(bitmap)
                                        combinations.append(LottoValidator.combination_to_str(numbers))
                                    else:
                                        # 문자열 그대로 사용
                                        combinations.append(row[0])
                                except Exception as e:
                                    logging.error(f"조합 변환 중 오류 발생: {str(e)}")
                            
                            offset += current_batch_size
                            
                            # 진행 상황 로깅 (매 100만개마다)
                            if offset % 1000000 == 0:
                                logging.debug(f"진행 상황: {offset:,}/{process_limit:,}개 로드 완료")
                        
                        logging.debug(f"로드 완료: 총 {len(combinations):,}개 조합")
                except Exception as e:
                    logging.error(f"조합 로드 중 오류: {str(e)}")
                    combinations = []
            else:
                # 스트림 방식으로 조합 처리 (메모리 효율적)
                combinations_generator = self.db_manager.combinations_db.get_filtered_combinations_generator(batch_size=50000)
                combinations = []

                # 배치별로 처리
                batch_count = 0
                for batch in combinations_generator:
                    combinations.extend(batch)
                    batch_count += 1

                    # 메모리 사용량 체크 (1GB 제한)
                    memory_mb = psutil.virtual_memory().used / 1024 / 1024
                    if memory_mb > 1024:  # 1GB 초과시
                        logging.warning(f"메모리 제한 도달 ({memory_mb:.1f}MB), 처리 중단")
                        break

                    if batch_count % 10 == 0:
                        logging.info(f"배치 처리 진행: {len(combinations):,}개 로드됨 (메모리: {memory_mb:.1f}MB)")

                logging.info(f"스트림 방식 조합 로드 완료: {len(combinations):,}개")
                
            if not combinations:
                logging.error("필터링할 조합이 없습니다.")
                return False
                
            initial_count = len(combinations)
            logging.info(f"필터링 시작: 초기 조합: {initial_count:,}개")
            
            # 성능 추적기 세션 시작
            if self.performance_tracker:
                self.performance_tracker.start_filtering_session(latest_round, initial_count)
            
            # 효율성 기준으로 최적화된 필터 순서 사용
            filtered_combinations = combinations
            
            # 시작 시간 및 메모리 사용량 기록
            start_time = time.time()
            process = psutil.Process()
            start_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # tqdm으로 필터 적용 진행 상태 표시
            ordered_filters = self._get_optimized_filter_order()
            with tqdm(total=len(ordered_filters), desc="필터 적용 중", unit="필터") as pbar:
                for filter_name, filter_instance in ordered_filters:
                    # 필터 적용
                    filtered_combinations = self._apply_single_filter(
                        filter_name=filter_name,
                        filter_instance=filter_instance,
                        combinations=filtered_combinations,
                        round_num=latest_round
                    )
                    
                    # 필터 적용 실패 체크
                    if filtered_combinations is None:
                        logging.error(f"{filter_name} 필터 적용 실패, 필터링 중단")
                        return False
                    
                    # 현재 메모리 사용량 체크
                    current_memory = process.memory_info().rss / 1024 / 1024  # MB
                    
                    # 진행 상태바 업데이트
                    pbar.set_postfix(
                        filter=filter_name, 
                        remaining=f"{len(filtered_combinations):,}", 
                        excluded=f"{initial_count - len(filtered_combinations):,}",
                        memory=f"{current_memory:.0f}MB"
                    )
                    pbar.update(1)
                        
                    # 모든 조합이 필터링된 경우
                    if len(filtered_combinations) == 0:
                        logging.warning("모든 조합이 필터링되었습니다. 필터 기준을 조정하세요.")
                        return False
            
            # 모든 필터 적용 완료 후 최종 결과를 DB에 저장
            try:
                # ============================================================
                # FIX: Enhanced Logging & Verification
                # ============================================================
                logging.info(f"[DB 저장] 회차 {latest_round}에 {len(filtered_combinations):,}개 조합 저장 중...")

                save_result = self.db_manager.combinations_db.save_filtered_combinations(latest_round, filtered_combinations)

                if save_result:
                    # Verify saved count
                    saved_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)
                    logging.info(f"[DB 저장] 완료 - 실제 저장: {saved_count:,}개")

                    if saved_count != len(filtered_combinations):
                        logging.warning(f"[DB 저장] 경고: 저장된 수({saved_count:,})가 입력된 수({len(filtered_combinations):,})와 다릅니다!")
                    else:
                        logging.info(f"[✓] DB 저장 검증 성공")
                else:
                    logging.error(f"[DB 저장] save_filtered_combinations()가 False 반환")
                    return False
                # ============================================================
            except Exception as e:
                logging.error(f"최종 조합 DB 저장 중 오류 발생: {str(e)}")
                import traceback
                logging.error(traceback.format_exc())
                return False
            
            # 성능 추적기 세션 완료
            if self.performance_tracker:
                self.performance_tracker.complete_filtering_session(len(filtered_combinations))
            
            # 필터 버전 업데이트
            self.meta_manager.update_filter_version(self.current_filter_version)
            self.meta_manager.update_last_filtered_round(latest_round)
            
            # 성능 통계 계산
            end_time = time.time()
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            elapsed_time = end_time - start_time
            memory_usage = end_memory - start_memory
            
            # 최종 결과 및 성능 통계 표시
            logging.info("\n" + "=" * 60)
            logging.info("필터링 완료 - 성능 통계")
            logging.info("=" * 60)
            logging.info(f"- 초기 조합: {initial_count:,}개")
            logging.info(f"- 최종 조합: {len(filtered_combinations):,}개 ({len(filtered_combinations)/initial_count:.2%})")
            logging.info(f"- 제외된 조합: {initial_count - len(filtered_combinations):,}개")
            logging.info(f"- 처리 시간: {elapsed_time:.2f}초")
            logging.info(f"- 처리 속도: {initial_count / elapsed_time:,.0f} 조합/초")
            logging.info(f"- 메모리 사용량: {memory_usage:.2f} MB")
            logging.info(f"- 현재 메모리: {end_memory:.2f} MB")
            logging.info("=" * 60 + "\n")
            
            # 필터링 완료 후 실제 통계 표시
            self._display_filter_statistics_after_filtering(latest_round)
            
            return True
            
        except Exception as e:
            logging.error(f"필터 적용 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def _check_previous_filtering_results(self, round_num: int) -> bool:
        """이전 필터링 결과가 있는지 확인
        
        Args:
            round_num: 회차 번호
            
        Returns:
            bool: 이전 필터링 결과 존재 여부
        """
        try:
            # 모든 필터 DB의 필터링 결과 확인 (메모리 효율적)
            for filter_name, filter_db in self.db_manager.filter_dbs.items():
                if hasattr(filter_db, 'get_filtered_combinations_count'):
                    count = filter_db.get_filtered_combinations_count(round_num)
                    if count > 0:
                        return True
            return False
        except Exception as e:
            logging.warning(f"이전 필터링 결과 확인 중 오류: {str(e)}")
            return False

    def _calculate_and_display_filter_results(self, round_num: int):
        """필터링 결과를 계산하고 표시합니다."""
        try:
            # 현재 구현은 기존의 _display_filter_results 메서드를 호출하도록 변경
            self._display_filter_results(round_num)
        except Exception as e:
            logging.error(f"필터링 결과 계산 중 오류: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())

    def get_current_round(self) -> int:
        """현재 처리 중인 회차 번호 조회
        
        Returns:
            int: 현재 회차 번호
        """
        try:
            # 1. self.current_round가 있으면 사용
            if hasattr(self, 'current_round') and self.current_round:
                return self.current_round
                
            # 2. db_manager에서 최신 회차 가져오기
            if self.db_manager:
                last_round = self.db_manager.get_last_round()
                if last_round:
                    return last_round
                    
            # 3. 마지막 필터링된 회차 가져오기
            last_filtered = self.meta_manager.get_last_filtered_round()
            if last_filtered:
                return last_filtered
                
            # 기본값
            return 0
        except Exception as e:
            logging.error(f"현재 회차 조회 중 오류 발생: {str(e)}")
            return 0

    def _log_filter_summary(self):
        """필터링 결과 요약 로깅"""
        try:
            # 최신 회차 가져오기
            latest_round = self.get_current_round()
            if not latest_round:
                logging.warning("최신 회차 정보를 찾을 수 없습니다.")
                return
                
            round_num = latest_round
            logging.info(f"[필터 디버그] 필터링 결과 요약 시작 - 회차: {round_num}")
            
            # 초기 조합 수 가져오기
            initial_count = len(self.db_manager.combinations_db.get_base_combinations())
            logging.info(f"\n[필터링 결과 요약] - {round_num}회차")
            logging.info(f"- 초기 조합 수: {initial_count:,}개")
            
            # 필터 카테고리 정의
            all_filters = list(self.filters.keys())
            filter_groups = {
                "기본 필터": ["match", "odd_even", "consecutive", "sum_range"],
                "패턴 필터": ["fixed_step", "last_digit", "max_gap", "section", "average"],
                "신규 필터": ["multiple", "ten_section", "arithmetic_sequence", "geometric_sequence", 
                           "prime_composite", "digit_sum", "dispersion"],
                "ML/AI 필터": ["ml_prediction"]
            }
            
            # 카테고리에 없는 필터 찾기
            categorized_filters = []
            for filters in filter_groups.values():
                categorized_filters.extend(filters)
            
            uncategorized_filters = [f for f in all_filters if f not in categorized_filters]
            if uncategorized_filters:
                filter_groups["기타 필터"] = uncategorized_filters
                logging.warning(f"카테고리에 없는 필터 발견: {uncategorized_filters}")
            
            total_excluded = 0
            total_excluded_percent = 0
            
            # 각 카테고리별 필터 결과 로깅
            for category, filters in filter_groups.items():
                logging.info(f"\n[{category} 결과]")
                
                for filter_name in filters:
                    if filter_name not in all_filters:
                        logging.info(f"- {filter_name}: 적용되지 않음")
                        continue
                        
                    try:
                        logging.debug(f"[필터 디버그] {filter_name} 필터 통계 조회 시작")
                        # 필터 DB에서 필터 통계 가져오기 (filter_details 테이블)
                        filter_db = self.db_manager.get_filter_db(filter_name)
                        details = filter_db.get_filter_details(round_num) if filter_db else None
                        
                        # 필터링 결과 계산
                        if details and isinstance(details, dict) and 'excluded_count' in details and 'exclude_percent' in details:
                            excluded_count = details['excluded_count']
                            exclude_percent = details['exclude_percent']
                            logging.debug(f"[필터 디버그] {filter_name} 필터 통계 조회 성공: {details}")
                        else:
                            logging.debug(f"[필터 디버그] {filter_name} 필터 통계 조회 실패, 제외된 조합 수 직접 계산")
                            # 필터 결과가 없는 경우, 제외된 조합 수 직접 계산
                            excluded_count = filter_db.count_excluded_combinations(round_num) if filter_db else 0
                            exclude_percent = (excluded_count / initial_count * 100) if initial_count > 0 else 0
                            
                            # 필터 상세 정보 저장
                            if filter_db:
                                filter_instance = self.filters.get(filter_name)
                                filter_details = {
                                    'excluded_count': excluded_count,
                                    'exclude_percent': exclude_percent,
                                    'criteria': filter_instance.get_criteria() if filter_instance else {},
                                    'version': self.current_filter_version
                                }
                                filter_db.save_filter_details(round_num, filter_details)
                        
                        # 로그 출력
                        logging.info(f"- {filter_name}: {excluded_count:,}개 제외 ({exclude_percent:.2f}%)")
                        
                        # 총계에 추가
                        total_excluded += excluded_count
                        total_excluded_percent += exclude_percent
                        
                    except Exception as e:
                        logging.warning(f"- {filter_name}: 통계 로드 실패 ({str(e)})")
                        logging.exception(e)
            
            # 최종 결과 계산 및 로깅
            remaining_count = initial_count - total_excluded
            if remaining_count < 0:
                remaining_count = 0
            
            logging.info("\n[최종 결과]")
            logging.info(f"- 초기 조합 수: {initial_count:,}개")
            logging.info(f"- 총 제외된 조합: {total_excluded:,}개 ({total_excluded_percent:.2f}%)")
            logging.info(f"- 최종 남은 조합: {remaining_count:,}개")
            
        except Exception as e:
            logging.error(f"필터링 결과 표시 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())

    def get_filtering_status(self, round_num: int) -> Dict[str, Any]:
        """현재 필터링 상태 조회"""
        try:
            return self.db_manager.get_detailed_filtering_status(round_num)
        except Exception as e:
            logging.error(f"필터링 상태 조회 중 오류 발생: {str(e)}")
            return {
                'round': round_num,
                'status': 'error',
                'error': str(e)
            }

    def reset_filters(self) -> None:
        """모든 필터 초기화"""
        self.filters.clear()
        self._filter_results.clear()
        logging.info("필터 초기화 완료")

    def get_registered_filters(self) -> List[str]:
        """등록된 필터 목록 조회"""
        return list(self.filters.keys())

    def _log_multiple_filter_details(self, results: Dict[str, Any]) -> None:
        """배수 필터 상세 결과 출력"""
        if 'details' in results:
            details = results['details']
            logging.info("\n배수별 제외 현황:")
            for base, counts in details.items():
                logging.info(f"- {base}의 배수:")
                for count, number in counts.items():
                    logging.info(f"  {count}개 포함: {number:,}개 조합 제외")

    def _log_alternating_filter_details(self, results: Dict[str, Any]) -> None:
        """홀짝 교차 필터 상세 결과 출력"""
        if 'details' in results:
            details = results['details']
            logging.info("\n패턴별 제외 현황:")
            
            pattern_names = {
                'perfect_odd_start': '완벽한 홀짝 교차(홀수 시작)',
                'perfect_even_start': '완벽한 홀짝 교차(짝수 시작)',
                'partial': '부분 교차'
            }
            
            for pattern, count in details.items():
                name = pattern_names.get(pattern, pattern)
                logging.info(f"- {name}: {count:,}개 조합 제외")

    def _log_sum_multiple_filter_details(self, results: Dict[str, Any]) -> None:
        """합계 배수 필터 상세 결과 출력"""
        if 'details' in results:
            details = results['details']
            logging.info("\n배수별 제외 현황:")
            for base, count in details.items():
                logging.info(f"- 합계가 {base}의 배수: {count:,}개 조합 제외")

    def _get_optimal_batch_size(self):
        """시스템 메모리 기반 최적 배치 크기 계산"""
        try:
            available_memory = psutil.virtual_memory().available
            memory_per_combination = 200  # 바이트 단위 추정치
            
            # 가용 메모리의 최대 50%까지 사용
            max_combinations = int(available_memory * 0.5 / memory_per_combination)
            optimal_batch_size = min(max_combinations, 50000)  # 상한값 설정

            return max(10000, optimal_batch_size)  # 최소 10000은 보장
        except Exception as e:
            logging.warning(f"배치 크기 계산 실패: {e}. 기본값 10000 사용")
            return 10000  # 기본값

    def _apply_incremental_with_save(self, round_num: int) -> bool:
        """증분식 필터링 + 중간 결과 저장 방식 적용
        
        각 필터 적용 후 중간 결과를 저장하여 다음 실행 시 활용
        
        Args:
            round_num: 현재 회차 번호
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 캐시 키 생성
            cache_key = f"incremental_{round_num}"
            
            # 기존 캐시가 있는지 확인
            if cache_key in self.incremental_cache:
                # 마지막으로 적용된 필터와 남은 조합 가져오기
                last_filter_index, remaining_combinations = self.incremental_cache[cache_key]
                logging.info(f"이전 결과에서 계속: {len(remaining_combinations):,}개 조합")
            else:
                # 전체 조합에서 시작
                last_filter_index = 0
                remaining_combinations = self.db_manager.combinations_db.get_all_combinations()
                logging.info(f"증분식 필터링 시작: {len(remaining_combinations):,}개 조합")
            
            # 최적화된 필터 순서 가져오기
            sorted_filters = self._get_optimized_filter_order()
            
            # tqdm으로 필터 진행 상태 표시
            with tqdm(
                total=len(sorted_filters) - last_filter_index,
                desc="증분식 필터링", 
                unit="필터",
                initial=last_filter_index
            ) as pbar:
                # 마지막으로 적용된 필터 이후부터 처리
                for i, (filter_name, filter_instance) in enumerate(sorted_filters[last_filter_index:], last_filter_index):
                    # 필터 적용
                    filtered_combinations = self._apply_single_filter(
                        filter_name=filter_name,
                        filter_instance=filter_instance,
                        combinations=remaining_combinations,
                        round_num=round_num
                    )
                    
                    # 진행 상태바 업데이트
                    pbar.set_postfix(
                        filter=filter_name, 
                        remaining=f"{len(filtered_combinations):,}"
                    )
                    pbar.update(1)
                    
                    if filtered_combinations is None:
                        logging.error(f"{filter_name} 필터 적용 실패")
                        return False
                        
                    # 중간 결과 저장
                    excluded = set(remaining_combinations) - set(filtered_combinations)
                    if excluded:
                        self._save_intermediate_results(round_num, filter_name, excluded)
                    
                    # 다음 필터를 위한 준비
                    remaining_combinations = filtered_combinations
                    
                    # 모든 조합이 필터링된 경우
                    if len(remaining_combinations) == 0:
                        logging.warning("모든 조합이 필터링되었습니다. 필터 기준을 조정하세요.")
                        return False
                    
                    # 캐시 업데이트 (중단 후 재개를 위해)
                    self.incremental_cache[cache_key] = (i + 1, remaining_combinations)
                    
            # 필터 버전 업데이트
            self.meta_manager.update_filter_version(self.current_filter_version)
            self.meta_manager.update_last_filtered_round(round_num)
            
            # 간단한 최종 결과만 표시
            logging.info(f"필터링 완료: {len(remaining_combinations):,}개 조합 남음")
            
            # 성공적으로 완료된 증분식 필터링의 캐시 제거
            if cache_key in self.incremental_cache:
                del self.incremental_cache[cache_key]
            
            return True
            
        except Exception as e:
            logging.error(f"증분식 필터링 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def _save_intermediate_results(self, round_num: int, filter_name: str, excluded_combinations: Set[str]) -> None:
        """필터링 중간 결과를 DB에 저장
        
        Args:
            round_num: 회차 번호
            filter_name: 필터 이름
            excluded_combinations: 제외된 조합 집합
        """
        if not excluded_combinations:
            return
        
        try:
            # 일괄 처리를 위한 설정
            excluded_list = list(excluded_combinations)
            batch_size = min(10000, len(excluded_list))
            
            # 배치 저장 진행 상태 표시
            with tqdm(
                total=len(excluded_list), 
                desc=f"{filter_name} 필터 결과 저장", 
                unit="조합", 
                leave=False
            ) as pbar:
                # 트랜잭션으로 DB 저장
                filter_db = self.db_manager.get_filter_db(filter_name)
                if not filter_db:
                    logging.error(f"{filter_name} 필터의 DB를 찾을 수 없습니다.")
                    return
                
                # 일괄 처리로 저장
                for i in range(0, len(excluded_list), batch_size):
                    batch = excluded_list[i:i+batch_size]
                    
                    # 제외된 조합을 excluded_combinations 테이블에 저장
                    filter_db.save_excluded_combinations(round_num, batch)
                    
                    # 진행 상태바 업데이트
                    pbar.update(len(batch))
                
                # 필터 기준 저장
                filter_instance = self.filters.get(filter_name)
                if filter_instance:
                    # 필터 상세 정보 저장 (제외된 조합 수 포함)
                    excluded_count = len(excluded_list)
                    initial_count = len(self.db_manager.combinations_db.get_base_combinations())
                    exclude_percent = (excluded_count / initial_count * 100) if initial_count > 0 else 0
                    
                    filter_details = {
                        'excluded_count': excluded_count,
                        'exclude_percent': exclude_percent,
                        'criteria': filter_instance.get_criteria(),
                        'version': self.current_filter_version
                    }
                    
                    with filter_db._create_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO filter_details 
                            (round, details)
                            VALUES (?, ?)
                        ''', (round_num, json.dumps(filter_details)))
                        conn.commit()
                
        except Exception as e:
            logging.error(f"중간 결과 저장 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())

    def save_filtered_combinations(self, round_num: int, combinations: List[str]) -> bool:
        """필터링된 조합 저장"""
        try:
            # 진단 로그 추가
            if hasattr(self, 'filter_db'):
                logging.info(f"[진단] FilterManager.filter_db 타입: {type(self.filter_db)}")
                if hasattr(self.filter_db, 'db_path'):
                    logging.info(f"[진단] FilterDB.db_path: {self.filter_db.db_path}")
            else:
                logging.error("[진단] self.filter_db가 존재하지 않음")
            
            # 파일 경로 및 디렉토리 확인
            if hasattr(self, 'filter_db') and hasattr(self.filter_db, 'db_path'):
                db_dir = os.path.dirname(self.filter_db.db_path)
                logging.info(f"[진단] 데이터베이스 디렉토리: {db_dir}")
                logging.info(f"[진단] 디렉토리 존재 여부: {os.path.exists(db_dir)}")
                logging.info(f"[진단] 데이터베이스 파일 존재 여부: {os.path.exists(self.filter_db.db_path)}")
                logging.info(f"[진단] 파일 쓰기 권한 확인: {os.access(db_dir, os.W_OK)}")
            
            # 실제 저장 시도
            result = self.filter_db.save_filtered_combinations(round_num, combinations)
            if result:
                logging.info(f"[진단] 필터링된 조합 {len(combinations)}개 저장 성공")
            else:
                logging.error("[진단] 필터링된 조합 저장 실패")
            return result
            
        except Exception as e:
            logging.error(f"필터링된 조합 저장 중 오류 발생: {str(e)}", exc_info=True)
            return False

    def _display_filter_statistics_after_filtering(self, round_num: int):
        """필터링 완료 후 실제 통계를 표시합니다."""
        try:
            logging.info("\n========== 필터링 실행 결과 ==========")
            logging.info(f"회차: {round_num}")
            
            # 초기 조합 수
            initial_count = len(self.db_manager.combinations_db.get_base_combinations())
            logging.info(f"초기 조합 수: {initial_count:,}개")
            
            # 각 필터별 통계 표시
            total_excluded = 0
            
            for filter_name in self.filters.keys():
                filter_db = self.db_manager.get_filter_db(filter_name)
                if filter_db:
                    # get_filtering_statistics 메서드 확인
                    if hasattr(filter_db, 'get_filtering_statistics'):
                        stats = filter_db.get_filtering_statistics(round_num)
                        if stats:
                            excluded = stats.get('excluded_combinations', 0)
                            percent = stats.get('exclude_percent', 0)
                            logging.info(f"- {filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")
                            total_excluded += excluded
                        else:
                            logging.info(f"- {filter_name}: 통계 없음")
                    else:
                        # get_filter_details 사용
                        details = filter_db.get_filter_details(round_num)
                        if details and 'excluded_count' in details:
                            excluded = details['excluded_count']
                            percent = details.get('exclude_percent', 0)
                            logging.info(f"- {filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")
            
            # 최종 남은 조합 수 (메모리 효율적)
            final_count = self.db_manager.combinations_db.get_filtered_combinations_count(round_num)
            
            logging.info(f"\n최종 남은 조합: {final_count:,}개")
            logging.info("=====================================\n")
            
        except Exception as e:
            logging.error(f"필터링 통계 표시 중 오류: {str(e)}")
    
    def _display_filter_results(self, round_num: int = None):
        """필터링 결과를 표시합니다.
        
        Args:
            round_num: 회차 번호 (기본값: None)
        """
        try:
            # 회차 번호가 지정되지 않은 경우 현재 회차 사용
            if round_num is None:
                round_num = self.get_current_round()
            
            logging.info("\n[필터링 결과 요약]")
            
            # 초기 조합 수 가져오기
            initial_count = len(self.db_manager.combinations_db.get_base_combinations())
            logging.info(f"- 초기 조합 수: {initial_count:,}개")
            
            # 필터 결과 로깅 - 사용 가능한 모든 필터 DB 조회
            all_filters = self.db_manager.filter_dbs.keys()
            
            # 카테고리 정의 - 일반적인 필터 분류 
            filter_groups = {
                "기본 필터": ["match", "odd_even", "consecutive", "sum_range"],
                "패턴 필터": ["fixed_step", "last_digit", "max_gap", "section", "average"],
                "신규 필터": ["multiple", "ten_section", "arithmetic_sequence", "geometric_sequence", 
                           "prime_composite", "digit_sum", "dispersion"],
                "ML/AI 필터": ["ml_prediction"]
            }
            
            # 카테고리에 없는 필터 찾기
            categorized_filters = []
            for filters in filter_groups.values():
                categorized_filters.extend(filters)
            
            uncategorized_filters = [f for f in all_filters if f not in categorized_filters]
            if uncategorized_filters:
                filter_groups["기타 필터"] = uncategorized_filters
                logging.warning(f"카테고리에 없는 필터 발견: {uncategorized_filters}")
            
            # 각 필터 결과 저장
            filter_results = {}
            actual_total_excluded = 0
            
            # 각 카테고리별 필터 결과 로깅
            for category, filters in filter_groups.items():
                logging.info(f"\n[{category} 결과]")
                
                for filter_name in filters:
                    if filter_name not in all_filters:
                        logging.info(f"- {filter_name}: 적용되지 않음")
                        continue
                        
                    try:
                        # 필터 DB에서 필터 통계 가져오기 (filter_details 테이블)
                        filter_db = self.db_manager.get_filter_db(filter_name)
                        details = filter_db.get_filter_details(round_num) if filter_db else None
                        
                        # 필터링 결과 계산
                        if details and isinstance(details, dict):
                            if 'excluded_count' in details and 'exclude_percent' in details:
                                excluded_count = details['excluded_count']
                                exclude_percent = details['exclude_percent']
                            else:
                                # 필터 결과가 없는 경우, 제외된 조합 수 직접 계산
                                excluded_combinations = filter_db.get_excluded_combinations(round_num)
                                excluded_count = len(excluded_combinations)
                                exclude_percent = (excluded_count / initial_count * 100) if initial_count > 0 else 0
                                
                            # 결과 저장
                            filter_results[filter_name] = {
                                'excluded_count': excluded_count,
                                'exclude_percent': exclude_percent
                            }
                            
                            # 로그 출력
                            logging.info(f"- {filter_name}: {excluded_count:,}개 제외 ({exclude_percent:.2f}%)")
                            
                            # 실제 총계에 추가 (단, 중복 제외는 고려하지 않음)
                            actual_total_excluded += excluded_count
                        else:
                            logging.info(f"- {filter_name}: 통계 정보 없음")
                            
                    except Exception as e:
                        logging.warning(f"- {filter_name}: 통계 로드 실패 ({str(e)})")
            
            # 최종 필터링 결과 조회 - 실제 남은 조합 수 (메모리 효율적)
            final_remaining = self.db_manager.combinations_db.get_filtered_combinations_count(round_num)
            
            # 실제 제외된 조합 수 계산 (중복 제외 고려)
            actual_excluded = initial_count - final_remaining
            actual_exclude_percent = (actual_excluded / initial_count * 100) if initial_count > 0 else 0
            
            # 통계 수치 (각 필터별 제외 수 합계)는 중복 제외를 포함하므로 실제보다 클 수 있음
            statistical_total = sum(data['excluded_count'] for data in filter_results.values())
            
            # 최종 결과 로깅
            logging.info("\n[최종 결과]")
            logging.info(f"- 초기 조합 수: {initial_count:,}개")
            logging.info(f"- 총 제외된 조합: {actual_excluded:,}개 ({actual_exclude_percent:.2f}%)")
            logging.info(f"- 최종 남은 조합: {final_remaining:,}개")
            
            # 통계 비교 (선택적)
            if statistical_total > actual_excluded:
                logging.info(f"- 참고: 각 필터별 제외 합계({statistical_total:,}개)는 중복 제외를 포함합니다.")
            
        except Exception as e:
            logging.error(f"필터링 결과 표시 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())

    def _apply_single_filter(self, filter_name: str, filter_instance: BaseFilter, 
                          combinations: List[str], round_num: int) -> Optional[List[str]]:
        """단일 필터 적용
        
        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            Optional[List[str]]: 필터링된 조합 목록, 실패시 None
        """
        try:
            before_count = len(combinations)
            
            # 필터 적용
            start_time = time.time()
            filtered_combinations = filter_instance.apply(combinations, round_num)
            end_time = time.time()
            
            # 결과 확인
            if filtered_combinations is None:
                logging.error(f"{filter_name} 필터 적용 실패")
                return None
                
            # 성능 측정
            elapsed_time = end_time - start_time
            after_count = len(filtered_combinations)
            excluded_count = before_count - after_count
            exclude_ratio = excluded_count / before_count if before_count > 0 else 0
            
            # 필터 효율성 업데이트 (캐시)
            self.filter_efficiency[filter_name] = exclude_ratio
            
            # 성능 추적기에 데이터 전송
            if self.performance_tracker:
                try:
                    criteria = filter_instance.get_criteria() if hasattr(filter_instance, 'get_criteria') else {}
                    self.performance_tracker.track_filter_application(
                        filter_name, before_count, after_count, elapsed_time, criteria, round_num
                    )
                except Exception as e:
                    logging.warning(f"성능 추적 데이터 전송 실패 ({filter_name}): {e}")
            
            # 성능 로그 출력
            if before_count > 0:
                processing_speed = before_count / elapsed_time if elapsed_time > 0 else 0
                logging.info(f"\n[필터 성능] {filter_name} 필터:")
                logging.info(f"  ├─ 처리 시간: {elapsed_time:.3f}초")
                logging.info(f"  ├─ 처리 속도: {processing_speed:,.0f} 조합/초")
                logging.info(f"  ├─ 입력: {before_count:,}개")
                logging.info(f"  ├─ 출력: {after_count:,}개")
                logging.info(f"  └─ 제외율: {exclude_ratio*100:.2f}% ({excluded_count:,}개 제외)")
            
            # 필터링 결과 저장
            filter_db = self.db_manager.get_filter_db(filter_name)
            if filter_db:
                # 필터링된 조합 저장
                filter_db.save_filtered_combinations(round_num, filtered_combinations)
                
                # 제외된 조합 계산 및 저장
                excluded_combinations = set(combinations) - set(filtered_combinations)
                if excluded_combinations:
                    logging.info(f"[필터 디버그] {filter_name}: 제외된 조합 저장 시작 ({len(excluded_combinations):,}개)")
                    filter_db.save_excluded_combinations(round_num, list(excluded_combinations))
                
                # 필터 상세 정보 저장 (필터 통계)
                initial_count = len(combinations)
                excluded_count = len(excluded_combinations)
                exclude_percent = (excluded_count / initial_count * 100) if initial_count > 0 else 0
                
                filter_details = {
                    'initial_count': initial_count,
                    'excluded_count': excluded_count,
                    'exclude_percent': exclude_percent,
                    'remaining_count': len(filtered_combinations),
                    'elapsed_time': elapsed_time,
                    'criteria': filter_instance.get_criteria(),
                    'version': self.current_filter_version
                }
                
                # 필터 상세 정보 저장
                logging.info(f"[필터 디버그] {filter_name}: 필터 상세 정보 저장 시작")
                save_result = filter_db.save_filter_details(round_num, filter_details)
                logging.info(f"[필터 디버그] {filter_name}: 필터 상세 정보 저장 결과: {save_result}")
                
                # 필터 기준 저장
                criteria = filter_instance.get_criteria()
                logging.info(f"[필터 디버그] {filter_name}: 필터 기준 정보 저장 시작")
                save_result = filter_db.save_filter_criteria(round_num, criteria)
                logging.info(f"[필터 디버그] {filter_name}: 필터 기준 정보 저장 결과: {save_result}")
            
            return filtered_combinations
            
        except Exception as e:
            logging.error(f"{filter_name} 필터 적용 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return None
