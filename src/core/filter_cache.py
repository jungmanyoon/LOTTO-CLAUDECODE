"""
FilterCache - 캐시 관리 컴포넌트

Phase 2.1: FilterManager에서 분리된 캐시 관리 컴포넌트
- 증분 필터링 캐시
- Thread-safe 캐시 접근
- 중간 결과 저장
- 배치 크기 최적화

Author: Claude Code Refactoring
Date: 2025-12-08
"""

import json
import logging
import sys
import threading
import psutil
from typing import Any, Dict, List, Optional, Set, Tuple

from .filter_interfaces import IFilterCache
from tqdm import tqdm


class FilterCache(IFilterCache):
    """캐시 관리 구현

    Thread-safe한 증분 필터링 캐시와 중간 결과 저장을 담당합니다.

    Attributes:
        db_manager: 데이터베이스 관리자
        incremental_cache: 증분 필터링 캐시 {key: (filter_index, combinations)}
        _cache_lock: Thread-safety를 위한 락
        batch_size: 현재 배치 크기
        memory_limit_mb: 메모리 제한 (MB)
    """

    def __init__(self, db_manager, memory_limit_mb: int = 1536):
        """FilterCache 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            memory_limit_mb: 메모리 제한 (MB, 기본값 1.5GB)
        """
        self.db_manager = db_manager
        self.incremental_cache: Dict[str, Tuple[int, List[str]]] = {}
        self._cache_lock = threading.RLock()
        self.memory_limit_mb = memory_limit_mb

        # 최적 배치 크기 계산
        self.batch_size = self.get_optimal_batch_size()

        logging.debug(f"[FilterCache] 초기화 완료 (배치 크기: {self.batch_size:,})")

    def get_cached_result(self, cache_key: str) -> Optional[Tuple[int, List[str]]]:
        """캐시된 결과 조회 (Thread-safe)

        Args:
            cache_key: 캐시 키

        Returns:
            (마지막 필터 인덱스, 남은 조합) 또는 None
        """
        with self._cache_lock:
            if cache_key in self.incremental_cache:
                return self.incremental_cache[cache_key]
            return None

    def set_cached_result(self, cache_key: str, filter_index: int, combinations: List[str]) -> None:
        """캐시 결과 저장 (Thread-safe)

        Args:
            cache_key: 캐시 키
            filter_index: 마지막 적용된 필터 인덱스
            combinations: 남은 조합 리스트
        """
        with self._cache_lock:
            self.incremental_cache[cache_key] = (filter_index, combinations)
            logging.debug(f"[FilterCache] 캐시 저장: {cache_key} (필터 {filter_index}, {len(combinations):,}개 조합)")

    def clear_cache(self, cache_key: Optional[str] = None) -> None:
        """캐시 삭제 (Thread-safe)

        Args:
            cache_key: 특정 키만 삭제 (None이면 전체 삭제)
        """
        with self._cache_lock:
            if cache_key is None:
                self.incremental_cache.clear()
                logging.info("[FilterCache] 전체 캐시 삭제됨")
            elif cache_key in self.incremental_cache:
                del self.incremental_cache[cache_key]
                logging.debug(f"[FilterCache] 캐시 삭제: {cache_key}")

    def save_intermediate_results(
        self,
        round_num: int,
        filter_name: str,
        excluded_combinations: Set[str]
    ) -> None:
        """중간 결과를 DB에 저장

        Args:
            round_num: 회차 번호
            filter_name: 필터 이름
            excluded_combinations: 제외된 조합 집합
        """
        if not excluded_combinations:
            return

        # [v5 FIX #25] excluded_combinations 무한 누적 차단 (data/filters 39GB+ 방지).
        # 근거(53에이전트 감사): 이 테이블은 저장만 되고 read 경로가 0건(get_excluded_combinations 미사용).
        # 회차마다 수백만 행이 무한 INSERT되어 디스크 39GB+ 점유 → 디스크 풀 시 시스템 정지 위험.
        # 디버그가 필요하면 환경변수 LOTTO_SAVE_EXCLUDED=1로 활성화.
        import os as _os
        if _os.environ.get('LOTTO_SAVE_EXCLUDED', '0') != '1':
            logging.debug(f"[FilterCache] {filter_name}: excluded 저장 생략(read 경로 없음, 누적 방지)")
            return

        try:
            excluded_list = list(excluded_combinations)
            batch_size = min(10000, len(excluded_list))

            # 배치 저장 진행 상태 표시
            import threading as _threading
            _tqdm_disable = _threading.current_thread() is not _threading.main_thread()
            with tqdm(
                total=len(excluded_list),
                desc=f"{filter_name} 필터 결과 저장",
                unit="조합",
                leave=False,
                file=sys.stdout,
                disable=_tqdm_disable
            ) as pbar:
                # 필터 DB 가져오기
                filter_db = self.db_manager.get_filter_db(filter_name)
                if not filter_db:
                    logging.error(f"[FilterCache] {filter_name} 필터의 DB를 찾을 수 없습니다.")
                    return

                # 일괄 처리로 저장
                for i in range(0, len(excluded_list), batch_size):
                    batch = excluded_list[i:i + batch_size]

                    # 제외된 조합을 excluded_combinations 테이블에 저장
                    filter_db.save_excluded_combinations(round_num, batch)

                    pbar.update(len(batch))

            logging.debug(f"[FilterCache] {filter_name}: {len(excluded_list):,}개 중간 결과 저장됨")

        except Exception as e:
            logging.error(f"[FilterCache] 중간 결과 저장 중 오류: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def save_filter_details(
        self,
        round_num: int,
        filter_name: str,
        filter_instance: Any,
        excluded_count: int,
        initial_count: int,
        current_filter_version: str
    ) -> None:
        """필터 상세 정보 저장

        Args:
            round_num: 회차 번호
            filter_name: 필터 이름
            filter_instance: 필터 인스턴스
            excluded_count: 제외된 조합 수
            initial_count: 초기 조합 수
            current_filter_version: 필터 버전
        """
        try:
            filter_db = self.db_manager.get_filter_db(filter_name)
            if not filter_db:
                return

            exclude_percent = (excluded_count / initial_count * 100) if initial_count > 0 else 0

            filter_details = {
                'excluded_count': excluded_count,
                'exclude_percent': exclude_percent,
                'criteria': filter_instance.get_criteria() if hasattr(filter_instance, 'get_criteria') else {},
                'version': current_filter_version
            }

            with filter_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO filter_details
                    (round, details)
                    VALUES (?, ?)
                ''', (round_num, json.dumps(filter_details)))
                conn.commit()

            logging.debug(f"[FilterCache] {filter_name} 필터 상세 정보 저장됨")

        except Exception as e:
            logging.error(f"[FilterCache] 필터 상세 정보 저장 중 오류: {e}")

    def get_optimal_batch_size(self) -> int:
        """시스템 메모리 기반 최적 배치 크기 계산 (PERF-002)

        DynamicBatchManager를 사용하여 메모리 상태에 따라 동적으로 배치 크기를 조절합니다.

        Returns:
            최적 배치 크기
        """
        try:
            # DynamicBatchManager 사용 (PERF-002 개선)
            from .dynamic_batch_manager import get_batch_manager
            batch_manager = get_batch_manager()
            optimal_batch_size = batch_manager.calculate_optimal_batch_size()

            logging.debug(f"[FilterCache] 동적 배치 크기: {optimal_batch_size:,}")
            return optimal_batch_size

        except ImportError:
            # DynamicBatchManager를 찾을 수 없는 경우 기존 로직 사용
            logging.warning("[FilterCache] DynamicBatchManager를 찾을 수 없음. 기본 로직 사용")
            return self._calculate_batch_size_fallback()
        except Exception as e:
            logging.warning(f"[FilterCache] 배치 크기 계산 실패: {e}. 기본값 사용")
            return self._calculate_batch_size_fallback()

    def _calculate_batch_size_fallback(self) -> int:
        """배치 크기 계산 폴백 로직

        DynamicBatchManager를 사용할 수 없는 경우의 대체 로직입니다.

        Returns:
            배치 크기
        """
        try:
            available_memory = psutil.virtual_memory().available
            memory_per_combination = 200  # 바이트 단위 추정치

            # 가용 메모리의 최대 50%까지 사용
            max_combinations = int(available_memory * 0.5 / memory_per_combination)
            optimal_batch_size = min(max_combinations, 50000)  # 상한값 설정

            return max(10000, optimal_batch_size)  # 최소 10000은 보장

        except Exception as e:
            logging.warning(f"[FilterCache] 폴백 배치 크기 계산 실패: {e}")
            return 10000

    def get_memory_usage(self) -> float:
        """현재 메모리 사용량 반환 (MB)"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    def check_memory_pressure(self) -> bool:
        """메모리 압박 상태 확인

        Returns:
            True if 메모리 압박 상태
        """
        try:
            memory_mb = psutil.virtual_memory().used / 1024 / 1024
            return memory_mb > self.memory_limit_mb
        except Exception:
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        with self._cache_lock:
            total_combinations = sum(
                len(combinations) for _, combinations in self.incremental_cache.values()
            )
            return {
                'cache_entries': len(self.incremental_cache),
                'total_cached_combinations': total_combinations,
                'batch_size': self.batch_size,
                'memory_usage_mb': self.get_memory_usage(),
                'memory_limit_mb': self.memory_limit_mb
            }
