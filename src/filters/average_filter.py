from typing import Any, List, Dict
import logging
import threading
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class AverageFilter(BaseFilter):
    """산술 평균 필터"""

    # 병렬 스레드 간 클래스 변수 접근 보호용 Lock
    _debug_lock: threading.Lock = threading.Lock()
    _main_debug_logged: bool = False

    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'min_average' not in self.criteria or 'max_average' not in self.criteria:
            raise ValueError("'min_average'와 'max_average' 값이 필요합니다.")
            
        min_avg = self.criteria['min_average']
        max_avg = self.criteria['max_average']
        
        if not isinstance(min_avg, (int, float)) or not isinstance(max_avg, (int, float)):
            raise ValueError("평균값 범위는 숫자여야 합니다.")
            
        if min_avg >= max_avg:
            raise ValueError("최소 평균값이 최대 평균값보다 작아야 합니다.")

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc=f"average 필터 진행률",
                min_average=self.criteria['min_average'],
                max_average=self.criteria['max_average']
            )
        except Exception as e:
            logging.error(f"평균값 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                    min_average: float,
                    max_average: float) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            # 타입 체크 추가
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.float32)

            # 각 조합의 평균값 계산
            averages = np.mean(chunk_arrays, axis=1)
            
            # 평균값 범위 체크 (극단값 자동 제외)
            valid_mask = (
                (averages >= min_average) & 
                (averages <= max_average)
            )
            
            # 디버깅: 대량 데이터 처리 시 로그 출력 (한 번만, Lock으로 병렬 접근 보호)
            if len(combinations_chunk) > 10000 and not getattr(AverageFilter, '_main_debug_logged', False):
                with AverageFilter._debug_lock:
                    # Double-checked locking: Lock 획득 후 다시 확인
                    if not AverageFilter._main_debug_logged:
                        logging.info(f"[AverageFilter MAIN] Criteria: min={min_average}, max={max_average}")
                        logging.info(f"[AverageFilter MAIN] Chunk size: {len(combinations_chunk)}")
                        logging.info(f"[AverageFilter MAIN] Sample averages: {averages[:10]}")
                        logging.info(f"[AverageFilter MAIN] Valid count: {np.sum(valid_mask)}/{len(averages)}")
                        AverageFilter._main_debug_logged = True
            
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            # 오류 시 입력 조합 보존하여 청크 전체 손실 방지 (필터 간 예외 정책 통일)
            return combinations_chunk