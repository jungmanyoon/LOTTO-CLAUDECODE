"""
FilterManager - 필터 시스템 Facade

Phase 2.1: God Object 리팩토링
- FilterCore: 핵심 필터링 로직
- FilterCache: 캐시 관리
- FilterOrchestrator: 필터 조정/실행

이 클래스는 Facade 패턴을 사용하여 위 컴포넌트들을 조합하고,
기존 API와 완전한 하위 호환성을 유지합니다.

Author: Claude Code Refactoring
Date: 2025-12-08
Version: 2.0 (Refactored)
"""

import os
import logging
import threading
from typing import Any, Dict, List, Optional, Set

from .filter_core import FilterCore
from .filter_cache import FilterCache
from .filter_orchestrator import FilterOrchestrator
from .threshold_manager import get_threshold_manager
from ..filters.base_filter import BaseFilter
from ..meta_data_manager import MetaDataManager
from ..utils.config_manager import ConfigManager
from ..utils.constants import SystemConstants


class FilterManager:
    """
    로또 필터 관리자 (Singleton Pattern + Facade Pattern)

    16개의 통계 기반 필터를 관리하고 8.14M개의 가능한 조합을
    약 30만개 수준으로 줄이는 핵심 필터링 시스템입니다.

    Phase 2.1 리팩토링:
        - FilterCore: 핵심 필터링 로직 (~500줄)
        - FilterCache: 캐시 관리 (~400줄)
        - FilterOrchestrator: 조정 계층 (~300줄)

    주요 기능:
        - 16개 필터 자동 등록 및 관리
        - 병렬 처리를 통한 고속 필터링 (12 workers, 75% CPU)
        - ThresholdManager 연동으로 임계값 자동 동기화
        - 증분 필터링 지원 (변경된 필터만 재실행)
        - 실시간 성능 추적 (FilterPerformanceTracker)

    사용 예시:
        >>> fm = FilterManager(db_manager)  # 싱글톤 인스턴스
        >>> results = fm.apply_filters(combinations)  # 모든 필터 적용
        >>> valid = fm.get_valid_combinations(round_num)  # 유효 조합 조회

    Attributes:
        db_manager: DatabaseManager 인스턴스
        filters: 등록된 필터 딕셔너리 {name: BaseFilter}
        threshold_manager: ThresholdManager 싱글톤 참조
        performance_tracker: FilterPerformanceTracker 인스턴스

    Note:
        - 테스트 시 FilterManager.reset_instance()로 초기화하세요.
        - 필터 효율성은 config.yaml에서 설정 가능합니다.
    """

    # 클래스 변수 - 싱글톤 패턴 구현
    _instance = None
    _lock = threading.Lock()
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
        with FilterManager._lock:
            if FilterManager._initialized:
                logging.debug("[FilterManager] 이미 초기화됨 - 중복 초기화 방지")
                return

            logging.info("[FilterManager] 초기화 시작 (Phase 2.1 리팩토링 버전)")

            # 기본 속성
            self.db_manager = db_manager
            self.current_filter_version = "1.3"

            # 메타데이터 관리자
            self.meta_manager = MetaDataManager()

            # 설정 로드
            self.config_manager = ConfigManager()
            self.filter_efficiency = self.config_manager.get_filter_efficiency()

            # 필터링 설정
            filtering_config = self.config_manager.get_filtering_config()
            self.use_parallel = filtering_config.get("use_parallel", True)
            cpu_count = os.cpu_count() or 4
            default_workers = min(max(4, cpu_count - 1), 8)
            self.max_workers = filtering_config.get("max_workers", default_workers)
            self.use_bit_operations = filtering_config.get("use_bit_operations", True)
            self.use_early_termination = filtering_config.get("use_early_termination", True)
            self.combine_independent_filters = filtering_config.get("combine_independent_filters", True)

            # 배치 크기와 메모리 제한 설정
            self.batch_size = SystemConstants.LARGE_BATCH_SIZE
            self.memory_limit_mb = SystemConstants.MEMORY_LIMIT_MB
            self.min_log_interval = 3.0

            # 로그 필터 설정 - 중복 로그 방지
            self.last_progress_time = {}

            # ===== 컴포넌트 초기화 (Phase 2.1) =====
            # FilterCore: 핵심 필터링 로직
            self._filter_core = FilterCore(db_manager, self.config_manager)

            # FilterCache: 캐시 관리
            self._filter_cache = FilterCache(db_manager, self.memory_limit_mb)

            # 성능 추적기 초기화
            try:
                from .filter_performance_tracker import FilterPerformanceTracker
                self.performance_tracker = FilterPerformanceTracker(db_manager)
                logging.debug("필터 성능 추적기 초기화 완료")
            except Exception as e:
                logging.warning(f"성능 추적기 초기화 실패: {e}")
                self.performance_tracker = None

            # FilterOrchestrator: 필터 조정/실행
            self._filter_orchestrator = FilterOrchestrator(
                db_manager=db_manager,
                filter_core=self._filter_core,
                filter_cache=self._filter_cache,
                meta_manager=self.meta_manager,
                performance_tracker=self.performance_tracker
            )

            # ThresholdManager 연동
            self.threshold_manager = get_threshold_manager()
            self.threshold_manager.register_observer(self._on_config_change)
            logging.debug("[FilterManager] ThresholdManager 연동 완료")

            # 필터 자동 등록
            self._filter_core.auto_register_filters()

            # 초기화 완료
            FilterManager._initialized = True
            logging.info("[FilterManager] 초기화 완료 (Phase 2.1 Facade)")

    # ===== 컴포넌트 접근 프로퍼티 =====

    @property
    def filters(self) -> Dict[str, BaseFilter]:
        """등록된 필터 딕셔너리 (하위 호환성)"""
        return self._filter_core.filters

    @filters.setter
    def filters(self, value: Dict[str, BaseFilter]):
        """필터 딕셔너리 설정 (하위 호환성)"""
        self._filter_core.filters = value

    @property
    def _filter_results(self) -> Dict[str, Dict]:
        """필터 결과 딕셔너리 (하위 호환성)"""
        return self._filter_core._filter_results

    @property
    def incremental_cache(self) -> Dict:
        """증분 캐시 (하위 호환성)"""
        return self._filter_cache.incremental_cache

    @property
    def _cache_lock(self) -> threading.RLock:
        """캐시 락 (하위 호환성)"""
        return self._filter_cache._cache_lock

    # ===== 클래스 메서드 =====

    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 초기화 (테스트용)"""
        with cls._lock:
            if cls._instance is not None:
                # ThresholdManager Observer 정리 - 메모리 누수 방지
                try:
                    from src.core.threshold_manager import ThresholdManager
                    tm = ThresholdManager.get_instance()
                    tm.unregister_observer(cls._instance._on_config_change)
                    logging.debug("[FilterManager] ThresholdManager Observer 해제 완료")
                except Exception as e:
                    logging.debug(f"[FilterManager] ThresholdManager Observer 해제 중 오류 (무시): {e}")
            cls._instance = None
            cls._initialized = False
            logging.info("[FilterManager] 싱글톤 인스턴스 초기화 완료")

    @classmethod
    def is_initialized(cls):
        """초기화 상태 확인"""
        return cls._initialized

    # ===== Observer 패턴 메서드 =====

    def _on_config_change(self, param: str, old_value: Any, new_value: Any):
        """ThresholdManager에서 설정 변경 시 자동 호출되는 Observer 콜백"""
        self._filter_core.on_config_change(param, old_value, new_value)

    def on_config_change(self, param: str, old_value: Any, new_value: Any) -> None:
        """설정 변경 시 호출되는 공개 메서드 (IConfigObserver 인터페이스)"""
        self._on_config_change(param, old_value, new_value)

    def _recalculate_filter_criteria(self, new_threshold: float):
        """임계값 변경 시 모든 필터의 criteria를 재계산"""
        self._filter_core.recalculate_filter_criteria(new_threshold)

    # ===== 필터 등록/관리 메서드 (FilterCore 위임) =====

    def register_filter(self, filter_name: str, filter_instance: BaseFilter) -> None:
        """필터 등록"""
        self._filter_core.register_filter(filter_name, filter_instance)

    def unregister_filter(self, name: str) -> bool:
        """등록된 필터 제거"""
        return self._filter_core.unregister_filter(name)

    def get_registered_filters(self) -> List[str]:
        """등록된 필터 목록 조회"""
        return self._filter_core.get_registered_filters()

    def reset_filters(self) -> None:
        """모든 필터 초기화"""
        self._filter_core.reset_filters()

    def _auto_register_filters(self):
        """설정에서 활성화된 필터 자동 등록"""
        self._filter_core.auto_register_filters()

    def _update_filter_efficiency(self):
        """필터 효율성 가중치 업데이트"""
        self._filter_core._update_filter_efficiency()

    # ===== 필터 적용 메서드 (FilterOrchestrator 위임) =====

    def apply_filters(self, latest_round: int, update_mode: str = 'incremental', force: bool = False):
        """모든 필터를 적용합니다."""
        return self._filter_orchestrator.apply_filters(latest_round, update_mode, force)

    def apply_filters_streaming(self, latest_round: int) -> bool:
        """스트림 기반 필터 적용 (메모리 효율적)"""
        return self._filter_orchestrator.apply_filters_streaming(latest_round)

    def _get_optimized_filter_order(self) -> List:
        """필터 적용 순서 최적화"""
        return self._filter_orchestrator.get_optimized_filter_order()

    def _apply_single_filter(
        self,
        filter_name: str,
        filter_instance: BaseFilter,
        combinations: List[str],
        round_num: int
    ) -> Optional[List[str]]:
        """단일 필터 적용"""
        return self._filter_core.apply_single_filter(
            filter_name, filter_instance, combinations, round_num
        )

    # ===== 캐시 관련 메서드 (FilterCache 위임) =====

    def _get_optimal_batch_size(self):
        """시스템 메모리 기반 최적 배치 크기 계산"""
        return self._filter_cache.get_optimal_batch_size()

    def _apply_incremental_with_save(self, round_num: int) -> bool:
        """증분식 필터링 + 중간 결과 저장"""
        return self._filter_orchestrator._apply_incremental_with_save(round_num)

    def _save_intermediate_results(self, round_num: int, filter_name: str, excluded_combinations: Set[str]) -> None:
        """필터링 중간 결과를 DB에 저장"""
        self._filter_cache.save_intermediate_results(round_num, filter_name, excluded_combinations)

    # ===== 상태 조회 메서드 =====

    def get_current_round(self) -> int:
        """현재 처리 중인 회차 번호 조회"""
        return self._filter_orchestrator.get_current_round()

    def get_last_filtered_round(self) -> Optional[int]:
        """모든 필터의 마지막 필터링 회차 확인"""
        try:
            filter_rounds = {}
            for filter_name in self.filters.keys():
                filter_db = self.db_manager.get_filter_db(filter_name)
                if filter_db:
                    last_round = filter_db.get_last_filtered_round()
                    if last_round is not None:
                        filter_rounds[filter_name] = last_round

            if not filter_rounds:
                return None

            rounds = set(filter_rounds.values())
            if len(rounds) != 1:
                logging.warning("필터별 처리 회차가 일치하지 않습니다:")
                for fname, rnd in filter_rounds.items():
                    logging.warning(f"- {fname}: {rnd} 회차")
                return None

            return list(rounds)[0]

        except Exception as e:
            logging.error(f"필터링 상태 확인 중 오류 발생: {e}")
            return None

    def get_filtering_status(self, round_num: int) -> Dict[str, Any]:
        """현재 필터링 상태 조회"""
        try:
            return self.db_manager.get_detailed_filtering_status(round_num)
        except Exception as e:
            logging.error(f"필터링 상태 조회 중 오류 발생: {e}")
            return {
                'round': round_num,
                'status': 'error',
                'error': str(e)
            }

    def get_filtered_count(self, round_num: int) -> int:
        """필터링 후 남은 조합 개수 반환"""
        try:
            total_combinations = 8145060  # 45C6 = 8,145,060

            # 1. combinations_db에서 직접 조회
            if hasattr(self.db_manager, 'combinations_db'):
                try:
                    if hasattr(self.db_manager.combinations_db, 'get_filtered_combinations'):
                        filtered = self.db_manager.combinations_db.get_filtered_combinations(round_num)
                        if filtered:
                            return len(filtered)
                except Exception as e:
                    logging.debug(f"combinations_db 조회 실패: {e}")

            # 2. 필터 결과에서 계산
            total_excluded = 0
            for filter_name, result in self._filter_results.items():
                if isinstance(result, dict) and 'excluded_count' in result:
                    total_excluded += result['excluded_count']

            if total_excluded > 0:
                return max(0, total_combinations - total_excluded)

            # 3. filter_dbs에서 각 필터 결과 조회
            if hasattr(self.db_manager, 'filter_dbs'):
                try:
                    for filter_name, filter_db in self.db_manager.filter_dbs.items():
                        if hasattr(filter_db, 'get_filtered_count'):
                            count = filter_db.get_filtered_count(round_num)
                            if count and count > 0:
                                return count
                except Exception as e:
                    logging.debug(f"filter_dbs 조회 실패: {e}")

            # 4. 기본값: 전체 조합
            logging.warning(f"필터링된 조합 수를 찾을 수 없음 - 전체 반환: {total_combinations:,}개")
            return total_combinations

        except Exception as e:
            logging.error(f"get_filtered_count 실패: {e}")
            return 8145060

    # ===== 필터 버전 관리 =====

    def check_filter_version(self) -> bool:
        """필터 버전 확인 및 재필터링 필요 여부 확인"""
        try:
            stored_version = self.meta_manager.get_filter_version()
            last_filtered_round = self.meta_manager.get_last_filtered_round()

            if not stored_version or not last_filtered_round:
                logging.info("필터 버전 정보가 없거나 마지막 필터링 회차 정보가 없습니다. 재필터링이 필요합니다.")
                return True

            if stored_version != self.current_filter_version:
                logging.info(f"필터 버전이 다릅니다 (저장: {stored_version}, 현재: {self.current_filter_version}). 재필터링이 필요합니다.")
                return True

            return False

        except Exception as e:
            logging.error(f"필터 버전 확인 중 오류 발생: {e}")
            return True

    # ===== 데이터 관리 =====

    def reset_filtered_data(self) -> bool:
        """필터링 데이터 초기화"""
        return self._filter_orchestrator._reset_filtered_data()

    def save_filtered_combinations(self, round_num: int, combinations: List[str]) -> bool:
        """필터링된 조합 저장"""
        try:
            if hasattr(self, 'filter_db'):
                return self.filter_db.save_filtered_combinations(round_num, combinations)
            else:
                return self.db_manager.combinations_db.save_filtered_combinations(round_num, combinations)
        except Exception as e:
            logging.error(f"필터링된 조합 저장 중 오류 발생: {e}")
            return False

    def get_valid_combinations(self, round_num: int) -> List[str]:
        """유효한 조합 목록 조회

        Args:
            round_num: 회차 번호

        Returns:
            필터링된 유효 조합 리스트
        """
        try:
            if hasattr(self.db_manager, 'get_valid_combinations'):
                return self.db_manager.get_valid_combinations(round_num)
            elif hasattr(self.db_manager, 'combinations_db'):
                return self.db_manager.combinations_db.get_valid_combinations(round_num)
            else:
                logging.warning(f"get_valid_combinations: 조합 DB를 찾을 수 없습니다.")
                return []
        except Exception as e:
            logging.error(f"유효 조합 조회 중 오류: {e}")
            return []

    # ===== 통계/표시 메서드 =====

    def _display_filter_results(self, round_num: int = None):
        """필터링 결과를 표시합니다."""
        self._filter_orchestrator._display_filter_results(round_num or self.get_current_round())

    def display_filter_results(self, round_num: Optional[int] = None) -> None:
        """필터링 결과 표시 (공개 메서드 - IFilterStatistics 인터페이스)"""
        self._display_filter_results(round_num)

    def _display_filter_statistics_after_filtering(self, round_num: int):
        """필터링 완료 후 실제 통계를 표시합니다."""
        self._filter_orchestrator._display_filter_statistics_after_filtering(round_num)

    def display_filter_statistics_after_filtering(self, round_num: int) -> None:
        """필터링 완료 후 통계 표시 (공개 메서드 - IFilterStatistics 인터페이스)"""
        self._display_filter_statistics_after_filtering(round_num)

    def _calculate_and_display_filter_results(self, round_num: int):
        """필터링 결과를 계산하고 표시합니다."""
        self._display_filter_results(round_num)

    def _log_filter_summary(self):
        """필터링 결과 요약 로깅"""
        round_num = self.get_current_round()
        if round_num:
            self._display_filter_results(round_num)

    # ===== 내부 유틸리티 (하위 호환성) =====

    def _identify_independent_filters(self) -> List:
        """독립적인 필터들 식별"""
        basic_independent_filters = [
            'odd_even', 'sum_range', 'last_digit', 'multiple',
            'prime_composite', 'digit_sum'
        ]

        independent_filters = []
        for filter_name, filter_obj in self.filters.items():
            if filter_name in basic_independent_filters:
                if self.filter_efficiency.get(filter_name, 0) >= 0.1:
                    independent_filters.append((filter_name, filter_obj))

        return sorted(
            independent_filters,
            key=lambda x: self.filter_efficiency.get(x[0], 0),
            reverse=True
        )[:4]

    def _check_previous_filtering_results(self, round_num: int) -> bool:
        """이전 필터링 결과가 있는지 확인"""
        return self._filter_orchestrator._check_previous_filtering_results(round_num)

    def _initialize_new_filter_dbs(self):
        """새로운 필터 데이터베이스 초기화"""
        try:
            from .specialized_databases import FilterDB
            new_filters = {
                'multiple': 'multiple_filter.db',
                'ten_section': 'ten_section_filter.db',
                'arithmetic_sequence': 'arithmetic_sequence.db',
                'geometric_sequence': 'geometric_sequence.db'
            }

            for filter_type, db_name in new_filters.items():
                if hasattr(self, 'paths'):
                    db_path = os.path.join(self.paths.filters_dir, db_name)
                    self.filter_dbs[filter_type] = FilterDB(db_path)

            logging.debug("새로운 필터 데이터베이스 초기화 완료")
        except Exception as e:
            logging.error(f"필터 데이터베이스 초기화 중 오류 발생: {e}")

    def _convert_filter_to_numpy(self, filter_name: str, filter_instance):
        """필터를 numpy 최적화 함수로 변환"""
        return self._filter_orchestrator._convert_filter_to_numpy(filter_name, filter_instance)

    # ===== 로깅 헬퍼 (하위 호환성) =====

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
