"""
필터 시스템 인터페이스 정의 (ABC)

Phase 2.1: FilterManager 분할을 위한 추상 인터페이스
- IFilterCore: 핵심 필터링 로직
- IFilterCache: 캐시 관리
- IFilterOrchestrator: 필터 조정/실행

Author: Claude Code Refactoring
Date: 2025-12-08
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import logging


class IFilterCore(ABC):
    """핵심 필터링 로직 인터페이스

    단일 필터 등록, 적용, 관리를 담당합니다.
    """

    @abstractmethod
    def register_filter(self, filter_name: str, filter_instance: Any) -> None:
        """필터 등록

        Args:
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스 (BaseFilter)
        """
        pass

    @abstractmethod
    def unregister_filter(self, name: str) -> bool:
        """필터 등록 해제

        Args:
            name: 필터 이름

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    def get_registered_filters(self) -> List[str]:
        """등록된 필터 목록 반환"""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def reset_filters(self) -> None:
        """모든 필터 초기화"""
        pass

    @abstractmethod
    def recalculate_filter_criteria(self, new_threshold: float) -> None:
        """임계값 변경 시 필터 criteria 재계산

        Args:
            new_threshold: 새로운 확률 임계값 (%)
        """
        pass


class IFilterCache(ABC):
    """캐시 관리 인터페이스

    증분 필터링 캐시, 중간 결과 저장 등을 담당합니다.
    Thread-safe 구현이 필요합니다.
    """

    @abstractmethod
    def get_cached_result(self, cache_key: str) -> Optional[Tuple[int, List[str]]]:
        """캐시된 결과 조회

        Args:
            cache_key: 캐시 키

        Returns:
            (마지막 필터 인덱스, 남은 조합) 또는 None
        """
        pass

    @abstractmethod
    def set_cached_result(self, cache_key: str, filter_index: int, combinations: List[str]) -> None:
        """캐시 결과 저장

        Args:
            cache_key: 캐시 키
            filter_index: 마지막 적용된 필터 인덱스
            combinations: 남은 조합 리스트
        """
        pass

    @abstractmethod
    def clear_cache(self, cache_key: Optional[str] = None) -> None:
        """캐시 삭제

        Args:
            cache_key: 특정 키만 삭제 (None이면 전체 삭제)
        """
        pass

    @abstractmethod
    def save_intermediate_results(
        self,
        round_num: int,
        filter_name: str,
        excluded_combinations: Set[str]
    ) -> None:
        """중간 결과 저장

        Args:
            round_num: 회차 번호
            filter_name: 필터 이름
            excluded_combinations: 제외된 조합 집합
        """
        pass

    @abstractmethod
    def get_optimal_batch_size(self) -> int:
        """시스템 메모리 기반 최적 배치 크기 계산"""
        pass


class IFilterOrchestrator(ABC):
    """필터 조정/실행 인터페이스

    필터 실행 순서 최적화, 병렬 처리, 전체 필터링 프로세스 관리를 담당합니다.
    """

    @abstractmethod
    def get_optimized_filter_order(self) -> List[Tuple[str, Any]]:
        """최적화된 필터 실행 순서 반환

        Returns:
            [(필터 이름, 필터 인스턴스), ...] 효율성 순
        """
        pass

    @abstractmethod
    def apply_filters(
        self,
        latest_round: int,
        update_mode: str = 'incremental',
        force: bool = False
    ) -> bool:
        """모든 필터 적용

        Args:
            latest_round: 최신 회차
            update_mode: 'full' 또는 'incremental'
            force: 강제 필터링 여부

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    def apply_filters_streaming(self, latest_round: int) -> bool:
        """스트림 기반 필터 적용 (메모리 효율적)

        Args:
            latest_round: 최신 회차

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    def update_filter_efficiency(self) -> bool:
        """필터 효율성 가중치 업데이트

        Returns:
            성공 여부
        """
        pass


class IFilterStatistics(ABC):
    """필터 통계 인터페이스

    필터링 결과 표시, 상태 조회 등을 담당합니다.
    """

    @abstractmethod
    def get_filtering_status(self, round_num: int) -> Dict[str, Any]:
        """필터링 상태 조회

        Args:
            round_num: 회차 번호

        Returns:
            상태 정보 딕셔너리
        """
        pass

    @abstractmethod
    def get_filtered_count(self, round_num: int) -> int:
        """필터링 후 남은 조합 수 반환

        Args:
            round_num: 회차 번호

        Returns:
            남은 조합 수
        """
        pass

    @abstractmethod
    def display_filter_results(self, round_num: Optional[int] = None) -> None:
        """필터링 결과 표시

        Args:
            round_num: 회차 번호 (None이면 현재 회차)
        """
        pass

    @abstractmethod
    def display_filter_statistics_after_filtering(self, round_num: int) -> None:
        """필터링 완료 후 통계 표시

        Args:
            round_num: 회차 번호
        """
        pass


# Observer 콜백 타입
ConfigChangeCallback = Callable[[str, Any, Any], None]


class IConfigObserver(ABC):
    """설정 변경 관찰자 인터페이스"""

    @abstractmethod
    def on_config_change(self, param: str, old_value: Any, new_value: Any) -> None:
        """설정 변경 시 호출

        Args:
            param: 변경된 파라미터 이름
            old_value: 이전 값
            new_value: 새 값
        """
        pass
