from typing import List, Dict, Any, Callable, TypeVar, Generic, Optional
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import islice
from functools import partial, wraps
from tqdm.auto import tqdm
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
        self.chunk_size = chunk_size or 100000
        self.max_workers = max_workers or max(1, min(os.cpu_count() or 4, 8))  # 최대 8개 프로세스로 제한
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
            
            logging.info(f"[DEBUG-Optimizer] 필터 최적화 시작: {total_items:,}개 조합, 매개변수: {kwargs}")
            
            # 작은 데이터셋은 병렬 처리 효과가 없으므로 직렬 처리
            if total_items < 10000 or not self.use_parallel:
                logging.info(f"직렬 처리 모드로 {total_items}개 조합 필터링...")
                result = self._apply_serial(combinations, desc, **kwargs)
            else:
                logging.info(f"병렬 처리 모드로 {total_items}개 조합 필터링 (작업자: {self.max_workers}개)...")
                result = self._apply_parallel(combinations, desc, **kwargs)
            
            elapsed = time.time() - start_time
            excluded_count = total_items - len(result)
            logging.info(f"[DEBUG-Optimizer] 필터링 완료: {len(result):,}/{total_items:,}개 남음, {excluded_count:,}개 제외됨 ({excluded_count/total_items*100:.2f}%) (소요 시간: {elapsed:.2f}초)")

            # 구체적인 필터링 결과 샘플 확인
            if len(result) > 0 and len(result) < total_items:
                sample_input = combinations[:3]
                sample_output = result[:3]
                excluded_sample = [x for x in sample_input if x not in set(result)][:3]
                logging.info(f"[DEBUG-Optimizer] 입력 샘플: {sample_input}")
                logging.info(f"[DEBUG-Optimizer] 출력 샘플: {sample_output}")
                if excluded_sample:
                    logging.info(f"[DEBUG-Optimizer] 제외된 샘플: {excluded_sample}")
                
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
        filtered_combs = []
        
        # 단일 진행률 표시바 설정
        with tqdm(total=total_items, 
                desc=f"- {desc}",
                unit='조합',
                position=0,
                leave=True,
                dynamic_ncols=True,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:

            # 배치 처리
            for i in range(0, total_items, self.chunk_size):
                chunk = combinations[i:i + self.chunk_size]
                filtered_chunk = self.process_func(chunk, **kwargs)
                filtered_combs.extend(filtered_chunk)
                
                # 진행률 업데이트
                pbar.update(len(chunk))

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
        filtered_combs = []
        
        # 청크 분할
        chunks = []
        for i in range(0, total_items, self.chunk_size):
            chunks.append(combinations[i:i + self.chunk_size])
        
        # 작업 함수 정의
        wrapped_func = partial(self._process_chunk_wrapper, base_func=self.process_func, **kwargs)
        
        # 진행률 표시바 설정
        with tqdm(total=total_items, 
                desc=f"- {desc}",
                unit='조합',
                position=0,
                leave=True,
                dynamic_ncols=True) as pbar:
            
            # 병렬 실행
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
                        logging.error(f"작업 처리 중 오류 발생: {str(exc)}")
            
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