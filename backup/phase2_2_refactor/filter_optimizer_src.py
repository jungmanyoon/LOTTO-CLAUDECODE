from typing import List, Dict, Any, Callable, TypeVar, Generic, Optional
import numpy as np
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import islice
from functools import partial, wraps
# Progress bar imports - using wrapper for better control
try:
    from src.filters.tqdm_wrapper import filter_progress as tqdm
    from src.utils.progress_config import ProgressConfig
except ImportError:
    from tqdm.auto import tqdm
    class ProgressConfig:
        SIMPLE_MODE = False
import logging
import psutil
from multiprocessing import Manager, Value, Lock
import ctypes
import time

T = TypeVar('T')

class SharedCounter:
    """멀티프로세스 간 공유 카운터"""
    def __init__(self, initial_value=0):
        self.val = Value(ctypes.c_longlong, initial_value)
        self.lock = Lock()

    def increment(self, amount=1):
        with self.lock:
            self.val.value += amount
            return self.val.value

    def value(self):
        with self.lock:
            return self.val.value

class FilterOptimizer(Generic[T]):
    def __init__(self, process_func: Callable[[List[str]], List[str]],
                 chunk_size: int = None,
                 max_workers: int = None,
                 use_parallel: bool = True):
        """FilterOptimizer 초기화
        
        Args:
            process_func: 청크 처리 함수
            chunk_size: 청크 크기 (기본값: 100000)
            max_workers: 최대 작업자 수 (기본값: CPU 코어 수)
            use_parallel: 병렬 처리 사용 여부 (기본값: True)
        """
        self.process_func = process_func
        self.chunk_size = chunk_size or 150000  # 150K로 증가 (31GB RAM 최적화)
        self.max_workers = max_workers or max(1, min(os.cpu_count() or 4, 10))  # 최대 10개 프로세스로 제한 (CPU 75%)
        self.use_parallel = use_parallel
        
    def optimize_filter(self, combinations: List[str], desc: str, **kwargs) -> List[str]:
        """필터 최적화 적용
        
        Args:
            combinations: 필터링할 조합 목록
            desc: 진행 상황 설명 문자열
            **kwargs: 필터링 함수에 전달할 추가 매개변수
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            if not combinations:
                return []
                
            total_items = len(combinations)
            
            start_time = time.time()
            
            # DEBUG 로그 제거 - 반복적이고 불필요함
            
            # 작은 데이터셋은 병렬 처리 효과가 없으므로 직렬 처리
            if total_items < 10000 or not self.use_parallel:
                # DEBUG 로그 제거
                result = self._apply_serial(combinations, desc, **kwargs)
            else:
                # DEBUG 로그 제거
                result = self._apply_parallel(combinations, desc, **kwargs)
            
            elapsed = time.time() - start_time
            excluded_count = total_items - len(result)
            
            # DEBUG 로그 제거 - 대량 처리 시에만 요약 로그 출력
            if total_items >= 10000:
                logging.info(f"[Optimizer] 필터링 완료: {len(result):,}/{total_items:,}개 ({elapsed:.1f}초)")
                
            return result

        except Exception as e:
            logging.error(f"필터 최적화 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return combinations
            
    def _apply_serial(self, combinations: List[str], desc: str, **kwargs) -> List[str]:
        """직렬 처리로 필터 적용
        
        Args:
            combinations: 필터링할 조합 목록
            desc: 진행 상황 설명 문자열
            **kwargs: 필터링 함수에 전달할 추가 매개변수
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        total_items = len(combinations)
        # 빈 리스트는 그대로 반환
        if total_items == 0:
            logging.debug("빈 조합 리스트이므로 필터링 스킵")
            return combinations
        
        filtered_combs = []
        
        try:
            # ProgressConfig를 사용하여 진행률 표시 제어
            show_progress = hasattr(ProgressConfig, 'SIMPLE_MODE') and not ProgressConfig.SIMPLE_MODE
            
            # 단일 진행률 표시바 설정
            with tqdm(total=total_items, 
                    desc=f"- {desc}",
                    unit='조합',
                    position=0,
                    leave=False,  # 완료 후 진행률 바 제거
                    dynamic_ncols=True,
                    bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
                    disable=not show_progress,  # SIMPLE_MODE일 때는 비활성화
                    file=sys.stdout) as pbar:

                # 배치 처리
                for i in range(0, total_items, self.chunk_size):
                    chunk = combinations[i:i + self.chunk_size]
                    filtered_chunk = self.process_func(chunk, **kwargs)
                    filtered_combs.extend(filtered_chunk)
                    
                    # 진행률 업데이트
                    pbar.update(len(chunk))

                return filtered_combs
                
        except (OSError, IOError) as e:
            # tqdm 실패 시 진행률 표시 없이 처리
            logging.debug(f"진행률 표시 비활성화 (tqdm 오류): {e}")
            
            # 배치 처리 (진행률 표시 없음)
            for i in range(0, total_items, self.chunk_size):
                chunk = combinations[i:i + self.chunk_size]
                filtered_chunk = self.process_func(chunk, **kwargs)
                filtered_combs.extend(filtered_chunk)
                
                # SIMPLE_MODE일 때 큰 작업에 대해서만 진행률 로그
                if hasattr(ProgressConfig, 'SIMPLE_MODE') and ProgressConfig.SIMPLE_MODE:
                    if total_items >= 10000:  # 큰 작업에 대해서만
                        progress = (i / total_items) * 100
                        # 25%, 50%, 75% 지점에서만 로그
                        if progress >= 25 and i < self.chunk_size * 100:
                            logging.info(f"{desc}: 25% 완료")
                        elif progress >= 50 and i < self.chunk_size * 200:
                            logging.info(f"{desc}: 50% 완료")  
                        elif progress >= 75 and i < self.chunk_size * 300:
                            logging.info(f"{desc}: 75% 완료")
            
            return filtered_combs
            
    def _apply_parallel(self, combinations: List[str], desc: str, **kwargs) -> List[str]:
        """병렬 처리로 필터 적용

        Args:
            combinations: 필터링할 조합 목록
            desc: 진행 상황 설명 문자열
            **kwargs: 필터링 함수에 전달할 추가 매개변수

        Returns:
            List[str]: 필터링된 조합 목록
        """
        total_items = len(combinations)
        # 빈 리스트는 그대로 반환
        if total_items == 0:
            logging.debug("빈 조합 리스트이므로 필터링 스킵")
            return combinations

        filtered_combs = []
        pickle_error_detected = False

        # 청크 분할
        chunks = []
        for i in range(0, total_items, self.chunk_size):
            chunks.append(combinations[i:i + self.chunk_size])

        # 작업 함수 정의
        wrapped_func = partial(self._process_chunk_wrapper, base_func=self.process_func, **kwargs)

        try:
            # 진행률 표시바 설정
            with tqdm(total=total_items,
                    desc=f"- {desc}",
                    unit='조합',
                    position=0,
                    leave=True,
                    dynamic_ncols=True,
                    file=sys.stdout) as pbar:

                # 병렬 실행 (pickle 에러 시 직렬 처리로 fallback)
                try:
                    with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                        # 모든 청크에 대해 처리 작업 제출
                        future_to_chunk_size = {
                            executor.submit(wrapped_func, chunk): len(chunk)
                            for chunk in chunks
                        }

                        # 완료된 작업 결과 수집
                        for future in as_completed(future_to_chunk_size):
                            chunk_size = future_to_chunk_size[future]
                            try:
                                result = future.result()
                                filtered_combs.extend(result)
                                pbar.update(chunk_size)
                            except Exception as exc:
                                exc_str = str(exc).lower()
                                # pickle 관련 에러 감지
                                if "pickle" in exc_str or "lock" in exc_str or "_thread" in exc_str:
                                    pickle_error_detected = True
                                    logging.warning(f"병렬 처리 중 pickle 에러 감지: {exc}")
                                    break  # 루프 중단, 직렬 처리로 전환
                                else:
                                    logging.error(f"작업 처리 중 오류 발생: {str(exc)}")
                except (TypeError, AttributeError) as pickle_err:
                    # pickle 에러 발생 시 직렬 처리로 fallback
                    if "pickle" in str(pickle_err).lower() or "lock" in str(pickle_err).lower():
                        pickle_error_detected = True
                        logging.warning(f"병렬 처리 실패 (submit 단계): {pickle_err}")
                    else:
                        raise

                # pickle 에러 감지 시 직렬 처리로 전환
                if pickle_error_detected:
                    logging.info(f"직렬 처리로 전환하여 {desc} 재시작...")
                    filtered_combs = []  # 기존 결과 초기화
                    pbar.reset()  # 진행률 초기화
                    for chunk in chunks:
                        result = self.process_func(chunk, **kwargs)
                        filtered_combs.extend(result)
                        pbar.update(len(chunk))

            return filtered_combs

        except (OSError, IOError) as e:
            # tqdm 실패 시 진행률 표시 없이 직렬 처리
            logging.debug(f"진행률 표시 비활성화 (tqdm 오류): {e}")

            # 직렬 실행 (병렬 처리 대신 직렬로 안전하게 처리)
            filtered_combs = []
            for i, chunk in enumerate(chunks):
                result = self.process_func(chunk, **kwargs)
                filtered_combs.extend(result)

                # 매 10번째 청크마다 로그 출력
                if i % 10 == 0:
                    progress = ((i + 1) / len(chunks)) * 100
                    logging.debug(f"{desc}: {progress:.1f}% 완료")

            return filtered_combs

    @staticmethod
    def optimize_numpy_operation(func):
        """NumPy 연산 최적화를 위한 데코레이터"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_settings = np.seterr(all='ignore')
            try:
                return func(*args, **kwargs)
            finally:
                np.seterr(**old_settings)
        wrapper.__module__ = func.__module__
        return wrapper

    @staticmethod
    def _process_chunk_wrapper(chunk: List[str], base_func: Callable, **kwargs) -> List[str]:
        """청크 처리를 위한 래퍼 함수"""
        try:
            return base_func(chunk, **kwargs)
        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return []

    @staticmethod
    def convert_to_numpy_array(combinations: List[str], 
                             dtype: np.dtype = np.int8) -> np.ndarray:
        """조합 리스트를 NumPy 배열로 변환"""
        return np.array([
            list(map(int, comb.split(','))) 
            for comb in combinations
        ], dtype=dtype)