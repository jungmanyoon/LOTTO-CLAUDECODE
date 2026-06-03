"""
FilterOrchestrator - 필터 조정/실행 컴포넌트

Phase 2.1: FilterManager에서 분리된 필터 조정 컴포넌트
- 필터 실행 순서 최적화
- 전체 필터링 프로세스 관리
- 병렬/스트리밍 처리

Author: Claude Code Refactoring
Date: 2025-12-08
"""

import gc
import logging
import os
import sys
import time
import psutil
import numpy as np
from typing import Any, Dict, List, Optional, Tuple, Callable
from tqdm import tqdm

from .filter_interfaces import IFilterOrchestrator


class FilterOrchestrator(IFilterOrchestrator):
    """필터 조정/실행 구현

    필터 실행 순서 최적화와 전체 필터링 프로세스를 관리합니다.

    Attributes:
        db_manager: 데이터베이스 관리자
        filter_core: FilterCore 인스턴스
        filter_cache: FilterCache 인스턴스
        meta_manager: MetaDataManager 인스턴스
        performance_tracker: 성능 추적기
    """

    def __init__(
        self,
        db_manager,
        filter_core,
        filter_cache,
        meta_manager,
        performance_tracker=None
    ):
        """FilterOrchestrator 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            filter_core: FilterCore 인스턴스
            filter_cache: FilterCache 인스턴스
            meta_manager: MetaDataManager 인스턴스
            performance_tracker: 성능 추적기 (선택)
        """
        self.db_manager = db_manager
        self.filter_core = filter_core
        self.filter_cache = filter_cache
        self.meta_manager = meta_manager
        self.performance_tracker = performance_tracker
        self.stop_requested = False
        self.current_round = None

        logging.debug("[FilterOrchestrator] 초기화 완료")

    def get_optimized_filter_order(self) -> List[Tuple[str, Any]]:
        """최적화된 필터 실행 순서 반환

        효율성이 높은 필터가 먼저 실행되어 빠른 데이터 축소를 달성합니다.

        Returns:
            [(필터 이름, 필터 인스턴스), ...] 효율성 순
        """
        # 필터 효율성 가중치
        filter_efficiency = self.filter_core.get_filter_efficiency()

        # 활성화된 필터 목록
        available_filters = self.filter_core.get_registered_filters()

        # 효율성 순으로 정렬
        optimized_order = [
            (f, filter_efficiency.get(f, 0.1))
            for f in available_filters
        ]
        optimized_order.sort(key=lambda x: x[1], reverse=True)

        # 필터 인스턴스와 매핑
        ordered_filters = []
        for filter_name, efficiency in optimized_order:
            if filter_name in self.filter_core.filters:
                ordered_filters.append((filter_name, self.filter_core.filters[filter_name]))

        # Fallback: 최적화기에 문제가 있으면 기존 방식 사용
        if not ordered_filters:
            logging.warning("[FilterOrchestrator] 필터 최적화기 실패, 기본 순서 사용")
            ordered_filters = list(self.filter_core.filters.items())

        # 필터 순서 로깅 (상위 10개만)
        filter_order_str = ", ".join([
            f"{name}({efficiency:.2f})"
            for name, efficiency in optimized_order[:10]
        ])
        logging.info(f"필터 실행 순서 (동적 최적화): {filter_order_str}")

        return ordered_filters

    def update_filter_efficiency(self) -> bool:
        """필터 효율성 가중치 업데이트

        Returns:
            성공 여부
        """
        try:
            self.filter_core._update_filter_efficiency()
            return True
        except Exception as e:
            logging.error(f"[FilterOrchestrator] 필터 효율성 업데이트 실패: {e}")
            return False

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
        try:
            self.stop_requested = False
            self.current_round = latest_round

            # 필터 버전 가져오기
            current_filter_version = self.filter_core.current_filter_version
            db_filter_version = self.meta_manager.get_filter_version() if self.meta_manager else 0

            # 마지막 필터링된 회차 가져오기
            last_filtered_round = self.meta_manager.get_last_filtered_round() if self.meta_manager else None

            # 필터링 필요성 결정
            need_filtering = self._check_need_filtering(
                latest_round, last_filtered_round, current_filter_version,
                db_filter_version, update_mode, force
            )

            if not need_filtering:
                logging.info("이미 최신 필터링이 완료되었습니다.")
                self._display_filter_results(latest_round)
                return True

            # 디버그 로그 간소화
            logging.info(f"필터링 시작: 회차 {latest_round}, 모드 {update_mode}")

            # 전체 업데이트 모드나 강제 필터링인 경우 필터링 데이터 초기화
            if update_mode == 'full' or force:
                logging.info("전체 필터링 모드로 실행합니다.")
                self._reset_filtered_data()

            # 증분식 필터링 + 중간 결과 저장 모드
            if update_mode == 'incremental_with_save':
                return self._apply_incremental_with_save(latest_round)

            # 기본 조합 로드
            combinations = self._load_combinations(latest_round, update_mode, force)
            if not combinations:
                logging.error("필터링할 조합이 없습니다.")
                return False

            initial_count = len(combinations)
            logging.info(f"필터링 시작: 초기 조합: {initial_count:,}개")

            # 성능 추적기 세션 시작
            if self.performance_tracker:
                self.performance_tracker.start_filtering_session(latest_round, initial_count)

            # 시작 시간 및 메모리 사용량 기록
            start_time = time.time()
            process = psutil.Process()
            start_memory = process.memory_info().rss / 1024 / 1024

            # 필터 적용
            filtered_combinations = self._apply_all_filters(combinations, latest_round, initial_count)

            # [filters-16-6] 종료 요청/필터 실패는 None -> 저장 없이 실패 반환
            if filtered_combinations is None:
                return False

            # [filters-16-6] 빈 풀(과제거)은 []로 구분 - 직전 풀 보존(저장 스킵), 무의미한 빈 저장 방지
            if len(filtered_combinations) == 0:
                logging.warning(
                    "[필터 풀 과제거] 통과 조합 0개 - 직전 회차 풀을 유지하고 저장을 건너뜁니다."
                )
                return False

            # 모든 필터 적용 완료 후 최종 결과를 DB에 저장
            if not self._save_final_results(latest_round, filtered_combinations):
                return False

            # 성능 추적기 세션 완료
            if self.performance_tracker:
                self.performance_tracker.complete_filtering_session(len(filtered_combinations))

            # 필터 버전 업데이트
            if self.meta_manager:
                self.meta_manager.update_filter_version(current_filter_version)
                self.meta_manager.update_last_filtered_round(latest_round)

            # 성능 통계 로깅
            self._log_performance_stats(
                initial_count, len(filtered_combinations),
                start_time, start_memory, process
            )

            # 필터링 완료 후 실제 통계 표시
            self._display_filter_statistics_after_filtering(latest_round)

            return True

        except Exception as e:
            logging.error(f"필터 적용 중 오류 발생: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def apply_filters_streaming(self, latest_round: int) -> bool:
        """스트림 기반 필터 적용 (메모리 효율적)

        Args:
            latest_round: 최신 회차

        Returns:
            성공 여부
        """
        try:
            logging.info(f"스트림 기반 필터링 시작 (회차 {latest_round})")

            # 필터 파이프라인 생성
            filter_pipeline = []
            ordered_filters = self.get_optimized_filter_order()

            for filter_name, filter_instance in ordered_filters:
                filter_func = self._convert_filter_to_numpy(filter_name, filter_instance, latest_round)
                if filter_func:
                    filter_pipeline.append(filter_func)

            # 결과 저장 콜백
            def save_callback(passed_combinations):
                try:
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
                    logging.error(f"결과 저장 중 오류: {e}")

            # 스트림 처리 실행
            if hasattr(self, 'stream_processor') and self.stream_processor:
                stats = self.stream_processor.apply_filters_streaming(
                    filters=filter_pipeline,
                    save_callback=save_callback
                )

                total_processed = stats.get('total_processed', 0)
                if total_processed > 0:
                    exclusion_rate = stats['total_excluded'] / total_processed * 100
                else:
                    exclusion_rate = 0.0
                logging.info(
                    f"스트림 필터링 완료: {stats.get('total_passed', 0):,}개 통과 "
                    f"(제외율: {exclusion_rate:.2f}%)"
                )
            else:
                logging.warning("[FilterOrchestrator] stream_processor가 없습니다. 일반 필터링으로 전환합니다.")
                return self.apply_filters(latest_round, update_mode='full', force=True)

            return True

        except Exception as e:
            logging.error(f"스트림 필터링 중 오류: {e}")
            return False

    def _check_need_filtering(
        self,
        latest_round: int,
        last_filtered_round: Optional[int],
        current_filter_version: str,
        db_filter_version: str,
        update_mode: str,
        force: bool
    ) -> bool:
        """필터링 필요성 확인"""
        # 명령줄 인수에서 full_filter 가져오기
        force_filter = '--full-filter' in sys.argv or '--force-filter' in sys.argv

        if force:
            logging.info("강제 필터링 옵션이 지정되어 필터링을 실행합니다.")
            return True

        if not self._check_previous_filtering_results(latest_round):
            logging.info("이전 필터링 결과가 없어 필터링을 실행합니다.")
            return True

        if last_filtered_round is None:
            logging.info("이전에 필터링된 회차 정보가 없어 필터링을 실행합니다.")
            return True

        return (
            update_mode == 'full' or
            force_filter or
            last_filtered_round < latest_round or
            current_filter_version > db_filter_version
        )

    def _check_previous_filtering_results(self, round_num: int) -> bool:
        """이전 필터링 결과가 있는지 확인

        NOTE: 결과는 combinations_db에 저장되므로 거기서 체크해야 함.
        (filter_dbs의 filtered_combinations는 별도 테이블로 항상 비어있음)
        """
        try:
            # 실제 저장 위치인 combinations_db를 체크
            if hasattr(self.db_manager, 'combinations_db') and self.db_manager.combinations_db is not None:
                count = self.db_manager.combinations_db.get_filtered_combinations_count(round_num)
                if count > 0:
                    logging.debug(f"[캐시 확인] 회차 {round_num}의 필터링 결과 {count:,}개 존재 → 재필터링 불필요")
                    return True
            return False
        except Exception as e:
            logging.warning(f"이전 필터링 결과 확인 중 오류: {e}")
            return False

    def _reset_filtered_data(self) -> bool:
        """필터링 데이터 초기화"""
        try:
            total_filters = len(self.db_manager.filter_dbs)
            logging.info(f"\n[필터 초기화] 필터링 데이터 초기화 시작 ({total_filters}개 필터)")

            for idx, (filter_name, filter_db) in enumerate(self.db_manager.filter_dbs.items(), 1):
                logging.info(f"  [{idx}/{total_filters}] {filter_name} 필터 초기화 중...")
                with filter_db._create_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM filtered_combinations")
                    deleted_count = cursor.rowcount
                    conn.commit()

                logging.info(f"  [{idx}/{total_filters}] {filter_name} 완료 ({deleted_count:,}개 레코드 삭제)")

            logging.info(f"[필터 초기화] 모든 필터 데이터 초기화 완료")
            return True

        except Exception as e:
            logging.error(f"필터링 데이터 초기화 중 오류 발생: {e}")
            return False

    def _load_combinations(self, latest_round: int, update_mode: str, force: bool) -> List[str]:
        """조합 로드"""
        try:
            if update_mode == 'full' or force:
                total_count = self.db_manager.combinations_db.count_all_combinations()
                if total_count == 0:
                    logging.error("데이터베이스에 조합이 없습니다.")
                    return []

                logging.debug(f"전체 조합 수: {total_count:,}개")
                process_limit = total_count
                logging.info(f"전체 {process_limit:,}개 조합을 처리합니다.")

                return self._load_combinations_batch(process_limit)

            else:
                # 스트림 방식으로 조합 처리
                return self._load_combinations_stream()

        except Exception as e:
            logging.error(f"조합 로드 중 오류: {e}")
            return []

    def _load_combinations_batch(self, process_limit: int) -> List[str]:
        """배치로 조합 로드"""
        combinations = []
        batch_size = min(100000, process_limit)
        offset = 0

        try:
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
                                from ..utils.validators import LottoValidator
                                bitmap = LottoValidator.bytes_to_bitmap(row[0])
                                numbers = LottoValidator.decode_combination(bitmap)
                                combinations.append(LottoValidator.combination_to_str(numbers))
                            else:
                                combinations.append(row[0])
                        except Exception as e:
                            logging.error(f"조합 변환 중 오류 발생: {e}")

                    offset += current_batch_size

                    if offset % 1000000 == 0:
                        logging.debug(f"진행 상황: {offset:,}/{process_limit:,}개 로드 완료")

                logging.debug(f"로드 완료: 총 {len(combinations):,}개 조합")

        except Exception as e:
            logging.error(f"배치 조합 로드 중 오류: {e}")

        return combinations

    def _load_combinations_stream(self) -> List[str]:
        """스트림 방식으로 조합 로드"""
        combinations = []
        combinations_generator = self.db_manager.combinations_db.get_filtered_combinations_generator(batch_size=50000)
        batch_count = 0

        for batch in combinations_generator:
            combinations.extend(batch)
            batch_count += 1

            # 메모리 사용량 체크
            if self.filter_cache.check_memory_pressure():
                logging.warning(f"메모리 제한 도달, 처리 중단")
                break

            # 주기적 가비지 컬렉션
            if batch_count % 5 == 0:
                gc.collect()

            if batch_count % 10 == 0:
                memory_mb = self.filter_cache.get_memory_usage()
                logging.info(f"배치 처리 진행: {len(combinations):,}개 로드됨 (메모리: {memory_mb:.1f}MB)")

        logging.info(f"스트림 방식 조합 로드 완료: {len(combinations):,}개")
        return combinations

    def _apply_all_filters(
        self,
        combinations: List[str],
        latest_round: int,
        initial_count: int
    ) -> Optional[List[str]]:
        """모든 필터 적용"""
        filtered_combinations = combinations

        ordered_filters = self.get_optimized_filter_order()

        import threading as _threading
        _tqdm_disable = _threading.current_thread() is not _threading.main_thread()
        with tqdm(total=len(ordered_filters), desc="필터 적용 중", unit="필터", file=sys.stdout, disable=_tqdm_disable) as pbar:
            for filter_name, filter_instance in ordered_filters:
                # 종료 요청 시 즉시 중단 (긴 필터링이 강제 완주되는 것을 방지)
                if self.stop_requested:
                    logging.info("[FilterOrchestrator] 종료 요청 수신 - 필터링 중단")
                    return None
                # 필터 적용
                filtered_combinations = self.filter_core.apply_single_filter(
                    filter_name=filter_name,
                    filter_instance=filter_instance,
                    combinations=filtered_combinations,
                    round_num=latest_round
                )

                # 필터 적용 실패 체크
                if filtered_combinations is None:
                    logging.error(f"{filter_name} 필터 적용 실패, 필터링 중단")
                    return None

                # 현재 메모리 사용량 체크
                current_memory = self.filter_cache.get_memory_usage()

                # 진행 상태바 업데이트
                pbar.set_postfix(
                    filter=filter_name,
                    remaining=f"{len(filtered_combinations):,}",
                    excluded=f"{initial_count - len(filtered_combinations):,}",
                    memory=f"{current_memory:.0f}MB"
                )
                pbar.update(1)

                # [filters-16-6] 모든 조합이 필터링된 경우(과제거): None(종료/실패)과 구분해 빈 리스트 반환
                if len(filtered_combinations) == 0:
                    logging.warning(
                        "[필터 풀 과제거] 모든 조합이 필터링되어 통과 0개입니다. "
                        "제거 강도(임계값)가 과합니다 - 직전 회차 풀을 유지합니다. "
                        "global_probability_threshold를 낮추면 강도를 되돌릴 수 있습니다."
                    )
                    return []

        return filtered_combinations

    def _save_final_results(self, latest_round: int, filtered_combinations: List[str]) -> bool:
        """최종 결과 저장"""
        try:
            logging.info(f"[DB 저장] 회차 {latest_round}에 {len(filtered_combinations):,}개 조합 저장 중...")

            save_result = self.db_manager.combinations_db.save_filtered_combinations(
                latest_round, filtered_combinations
            )

            if save_result:
                saved_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)
                logging.info(f"[DB 저장] 완료 - 실제 저장: {saved_count:,}개")

                if saved_count != len(filtered_combinations):
                    logging.warning(
                        f"[DB 저장] 경고: 저장된 수({saved_count:,})가 "
                        f"입력된 수({len(filtered_combinations):,})와 다릅니다!"
                    )
                else:
                    logging.info(f"[O] DB 저장 검증 성공")
                return True
            else:
                logging.error(f"[DB 저장] save_filtered_combinations()가 False 반환")
                return False

        except Exception as e:
            logging.error(f"최종 조합 DB 저장 중 오류 발생: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def _log_performance_stats(
        self,
        initial_count: int,
        final_count: int,
        start_time: float,
        start_memory: float,
        process
    ) -> None:
        """성능 통계 로깅"""
        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024
        elapsed_time = end_time - start_time
        memory_usage = end_memory - start_memory

        logging.info("\n" + "=" * 60)
        logging.info("필터링 완료 - 성능 통계")
        logging.info("=" * 60)
        logging.info(f"- 초기 조합: {initial_count:,}개")
        logging.info(f"- 최종 조합: {final_count:,}개 ({final_count/initial_count:.2%})")
        logging.info(f"- 제외된 조합: {initial_count - final_count:,}개")
        logging.info(f"- 처리 시간: {elapsed_time:.2f}초")
        logging.info(f"- 처리 속도: {initial_count / elapsed_time:,.0f} 조합/초")
        logging.info(f"- 메모리 사용량: {memory_usage:.2f} MB")
        logging.info(f"- 현재 메모리: {end_memory:.2f} MB")
        logging.info("=" * 60 + "\n")

    def _apply_incremental_with_save(self, round_num: int) -> bool:
        """증분식 필터링 + 중간 결과 저장"""
        try:
            cache_key = f"incremental_{round_num}"

            # Thread-Safe 캐시 확인
            cached = self.filter_cache.get_cached_result(cache_key)
            if cached:
                last_filter_index, remaining_combinations = cached
                logging.info(f"이전 결과에서 계속: {len(remaining_combinations):,}개 조합")
            else:
                last_filter_index = 0
                remaining_combinations = self.db_manager.combinations_db.get_all_combinations()
                logging.info(f"증분식 필터링 시작: {len(remaining_combinations):,}개 조합")

            # 최적화된 필터 순서 가져오기
            sorted_filters = self.get_optimized_filter_order()

            import threading as _threading
            _tqdm_disable = _threading.current_thread() is not _threading.main_thread()
            with tqdm(
                total=len(sorted_filters) - last_filter_index,
                desc="증분식 필터링",
                unit="필터",
                initial=last_filter_index,
                file=sys.stdout,
                disable=_tqdm_disable
            ) as pbar:
                for i, (filter_name, filter_instance) in enumerate(sorted_filters[last_filter_index:], last_filter_index):
                    # 필터 적용
                    filtered_combinations = self.filter_core.apply_single_filter(
                        filter_name=filter_name,
                        filter_instance=filter_instance,
                        combinations=remaining_combinations,
                        round_num=round_num
                    )

                    pbar.set_postfix(
                        filter=filter_name,
                        remaining=f"{len(filtered_combinations):,}" if filtered_combinations else "0"
                    )
                    pbar.update(1)

                    if filtered_combinations is None:
                        logging.error(f"{filter_name} 필터 적용 실패")
                        return False

                    # 중간 결과 저장
                    excluded = set(remaining_combinations) - set(filtered_combinations)
                    if excluded:
                        self.filter_cache.save_intermediate_results(round_num, filter_name, excluded)

                    remaining_combinations = filtered_combinations

                    if len(remaining_combinations) == 0:
                        logging.warning("모든 조합이 필터링되었습니다.")
                        return False

                    # 캐시 업데이트
                    self.filter_cache.set_cached_result(cache_key, i + 1, remaining_combinations)

            # 필터 버전 업데이트
            if self.meta_manager:
                self.meta_manager.update_filter_version(self.filter_core.current_filter_version)
                self.meta_manager.update_last_filtered_round(round_num)

            logging.info(f"필터링 완료: {len(remaining_combinations):,}개 조합 남음")

            # 캐시 제거
            self.filter_cache.clear_cache(cache_key)

            return True

        except Exception as e:
            logging.error(f"증분식 필터링 중 오류 발생: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def _display_filter_results(self, round_num: int) -> None:
        """필터링 결과 표시"""
        try:
            logging.info("\n[필터링 결과 요약]")
            initial_count = len(self.db_manager.combinations_db.get_base_combinations())
            logging.info(f"- 초기 조합 수: {initial_count:,}개")

            # 각 필터 결과 로깅
            for filter_name in self.filter_core.get_registered_filters():
                filter_db = self.db_manager.get_filter_db(filter_name)
                if filter_db and hasattr(filter_db, 'get_filter_details'):
                    details = filter_db.get_filter_details(round_num)
                    if details and 'excluded_count' in details:
                        excluded = details['excluded_count']
                        percent = details.get('exclude_percent', 0)
                        logging.info(f"- {filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")

        except Exception as e:
            logging.error(f"필터링 결과 표시 중 오류: {e}")

    def _display_filter_statistics_after_filtering(self, round_num: int) -> None:
        """필터링 완료 후 실제 통계를 표시"""
        try:
            logging.info("\n========== 필터링 실행 결과 ==========")
            logging.info(f"회차: {round_num}")

            initial_count = len(self.db_manager.combinations_db.get_base_combinations())
            logging.info(f"초기 조합 수: {initial_count:,}개")

            for filter_name in self.filter_core.get_registered_filters():
                filter_db = self.db_manager.get_filter_db(filter_name)
                if filter_db:
                    if hasattr(filter_db, 'get_filtering_statistics'):
                        stats = filter_db.get_filtering_statistics(round_num)
                        if stats:
                            excluded = stats.get('excluded_combinations', 0)
                            percent = stats.get('exclude_percent', 0)
                            logging.info(f"- {filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")
                    elif hasattr(filter_db, 'get_filter_details'):
                        details = filter_db.get_filter_details(round_num)
                        if details and 'excluded_count' in details:
                            excluded = details['excluded_count']
                            percent = details.get('exclude_percent', 0)
                            logging.info(f"- {filter_name}: {excluded:,}개 제외 ({percent:.2f}%)")

            final_count = self.db_manager.combinations_db.get_filtered_combinations_count(round_num)
            logging.info(f"\n최종 남은 조합: {final_count:,}개")
            logging.info("=====================================\n")

        except Exception as e:
            logging.error(f"필터링 통계 표시 중 오류: {e}")

    def _convert_filter_to_numpy(self, filter_name: str, filter_instance, round_num: int = 0) -> Optional[Callable]:
        """필터를 numpy 최적화 함수로 변환"""
        try:
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

            else:
                # 기본 필터 함수
                def filter_func(batch: np.ndarray) -> np.ndarray:
                    mask = np.ones(len(batch), dtype=bool)
                    combo_strings = [','.join(map(str, sorted(combo))) for combo in batch]

                    try:
                        if hasattr(filter_instance, 'apply'):
                            filtered = filter_instance.apply(combo_strings, round_num)
                            filtered_set = set(filtered)
                            for i, combo_str in enumerate(combo_strings):
                                mask[i] = combo_str in filtered_set
                        elif hasattr(filter_instance, 'is_valid'):
                            for i, combo_str in enumerate(combo_strings):
                                mask[i] = filter_instance.is_valid(combo_str)
                    except Exception as e:
                        logging.error(f"필터 {filter_name} 적용 중 오류: {e}")

                    return mask

                return filter_func

        except Exception as e:
            logging.error(f"필터 변환 중 오류 ({filter_name}): {e}")
            return None

    def get_current_round(self) -> int:
        """현재 처리 중인 회차 번호 조회"""
        try:
            if hasattr(self, 'current_round') and self.current_round:
                return self.current_round

            if self.db_manager:
                last_round = self.db_manager.get_last_round()
                if last_round:
                    return last_round

            if self.meta_manager:
                last_filtered = self.meta_manager.get_last_filtered_round()
                if last_filtered:
                    return last_filtered

            return 0
        except Exception as e:
            logging.error(f"현재 회차 조회 중 오류 발생: {e}")
            return 0
