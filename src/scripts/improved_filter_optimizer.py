"""개선된 필터 최적화 모듈
메모리 효율성과 안정성을 개선한 버전
"""

from typing import List, Dict, Any, Callable, TypeVar, Generic, Optional
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
from itertools import islice
from functools import partial, wraps
from tqdm.auto import tqdm
import logging
import psutil
from multiprocessing import Manager, Value, Lock
import ctypes
import time
import traceback
import gc

T = TypeVar('T')

class FlushingLogger:
    """자동 플러시 기능이 있는 로거 래퍼"""
    @staticmethod
    def setup():
        """로거 설정에 자동 플러시 추가"""
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'flush'):
                # 각 로그 후 자동 플러시
                original_emit = handler.emit
                def flushing_emit(record):
                    original_emit(record)
                    handler.flush()
                handler.emit = flushing_emit

class MemoryMonitor:
    """메모리 사용량 모니터링"""
    def __init__(self, threshold_mb=2000):
        self.threshold_mb = threshold_mb
        self.initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        self.peak_memory = self.initial_memory
        
    def check(self):
        """현재 메모리 사용량 확인"""
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_increase = current_memory - self.initial_memory
        
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
            
        if memory_increase > self.threshold_mb:
            logging.warning(f"메모리 사용량 경고: {memory_increase:.1f}MB 증가 "
                          f"(현재: {current_memory:.1f}MB, 피크: {self.peak_memory:.1f}MB)")
            
        return current_memory, memory_increase
    
    def report(self):
        """최종 메모리 사용 보고"""
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        total_increase = final_memory - self.initial_memory
        logging.info(f"메모리 사용 보고 - 초기: {self.initial_memory:.1f}MB, "
                    f"최종: {final_memory:.1f}MB, 피크: {self.peak_memory:.1f}MB, "
                    f"증가량: {total_increase:.1f}MB")

class ImprovedFilterOptimizer(Generic[T]):
    def __init__(self, process_func: Callable[[List[str]], List[str]],
                 chunk_size: int = None,
                 max_workers: int = None,
                 use_parallel: bool = True,
                 memory_limit_gb: float = 6.0):
        """개선된 FilterOptimizer 초기화
        
        Args:
            process_func: 청크 처리 함수
            chunk_size: 청크 크기 (기본값: 50000)
            max_workers: 최대 작업자 수 (기본값: 메모리 기반 자동 계산)
            use_parallel: 병렬 처리 사용 여부 (기본값: True)
            memory_limit_gb: 메모리 제한 (GB, 기본값: 6.0)
        """
        self.process_func = process_func
        self.chunk_size = chunk_size or 50000  # 더 작은 청크 크기
        self.memory_limit_gb = memory_limit_gb
        
        # 메모리 기반 작업자 수 계산
        available_memory = psutil.virtual_memory().available
        memory_per_worker = 1 * 1024 * 1024 * 1024  # 1GB per worker
        max_workers_by_memory = max(1, int(available_memory / memory_per_worker))
        
        self.max_workers = max_workers or min(
            os.cpu_count() or 4, 
            max_workers_by_memory,
            6  # 최대 6개로 제한
        )
        
        self.use_parallel = use_parallel
        
        # 로거 설정
        FlushingLogger.setup()
        
    def optimize_filter(self, combinations: List[str], desc: str, **kwargs) -> List[str]:
        """필터 최적화 적용 (개선된 버전)"""
        try:
            if not combinations:
                return []
                
            total_items = len(combinations)
            start_time = time.time()
            memory_monitor = MemoryMonitor()
            
            logging.info(f"[필터 최적화] 시작: {total_items:,}개 조합")
            logging.info(f"[설정] 청크 크기: {self.chunk_size:,}, "
                        f"작업자: {self.max_workers}개, "
                        f"병렬 처리: {self.use_parallel}")
            
            # 작은 데이터셋은 직렬 처리
            if total_items < 10000 or not self.use_parallel:
                logging.info(f"직렬 처리 모드 사용")
                result = self._apply_serial_improved(combinations, desc, memory_monitor, **kwargs)
            else:
                logging.info(f"병렬 처리 모드 사용")
                result = self._apply_parallel_improved(combinations, desc, memory_monitor, **kwargs)
            
            elapsed = time.time() - start_time
            excluded_count = total_items - len(result)
            
            memory_monitor.report()
            
            logging.info(f"[필터 최적화] 완료: {len(result):,}/{total_items:,}개 남음, "
                        f"{excluded_count:,}개 제외됨 ({excluded_count/total_items*100:.2f}%) "
                        f"(소요 시간: {elapsed:.2f}초)")
            
            # 로그 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
                    
            return result

        except Exception as e:
            logging.error(f"필터 최적화 중 오류 발생: {str(e)}")
            logging.error(traceback.format_exc())
            return combinations
            
    def _apply_serial_improved(self, combinations: List[str], desc: str, 
                             memory_monitor: MemoryMonitor, **kwargs) -> List[str]:
        """개선된 직렬 처리"""
        total_items = len(combinations)
        filtered_combs = []
        
        with tqdm(total=total_items, desc=f"- {desc}", unit='조합',
                 leave=True, dynamic_ncols=True) as pbar:

            for i in range(0, total_items, self.chunk_size):
                chunk = combinations[i:i + self.chunk_size]
                
                # 메모리 체크
                current_memory, _ = memory_monitor.check()
                if current_memory > self.memory_limit_gb * 1024:
                    logging.warning(f"메모리 한계 근접: {current_memory:.1f}MB")
                    gc.collect()  # 가비지 컬렉션 강제 실행
                
                filtered_chunk = self.process_func(chunk, **kwargs)
                filtered_combs.extend(filtered_chunk)
                
                pbar.update(len(chunk))
                
                # 진행률 로깅 (10% 단위)
                progress = pbar.n / total_items * 100
                if progress % 10 < self.chunk_size / total_items * 100:
                    logging.info(f"진행률: {progress:.0f}% ({pbar.n:,}/{total_items:,})")

            return filtered_combs
            
    def _apply_parallel_improved(self, combinations: List[str], desc: str,
                               memory_monitor: MemoryMonitor, **kwargs) -> List[str]:
        """개선된 병렬 처리"""
        total_items = len(combinations)
        filtered_combs = []
        
        # 청크 분할
        chunks = []
        for i in range(0, total_items, self.chunk_size):
            chunks.append(combinations[i:i + self.chunk_size])
        
        logging.info(f"총 {len(chunks)}개 청크로 분할")
        
        # 작업 함수 정의
        wrapped_func = partial(self._process_chunk_wrapper_improved, 
                             base_func=self.process_func, **kwargs)
        
        # 타임아웃 설정
        timeout_per_chunk = 300  # 5분
        
        with tqdm(total=total_items, desc=f"- {desc}", unit='조합',
                 leave=True, dynamic_ncols=True) as pbar:
            
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # 배치 단위로 처리 (메모리 효율성)
                batch_size = self.max_workers * 2
                
                for batch_start in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[batch_start:batch_start + batch_size]
                    
                    # 메모리 체크
                    current_memory, memory_increase = memory_monitor.check()
                    
                    # 메모리 한계 도달 시 작업자 수 감소
                    if current_memory > self.memory_limit_gb * 1024:
                        logging.warning(f"메모리 한계 도달, 작업자 수 감소")
                        executor._max_workers = max(1, self.max_workers // 2)
                        gc.collect()
                    
                    # 배치 처리
                    future_to_chunk = {}
                    for chunk in batch_chunks:
                        future = executor.submit(wrapped_func, chunk)
                        future_to_chunk[future] = len(chunk)
                    
                    # 결과 수집 (타임아웃 포함)
                    completed = 0
                    try:
                        for future in as_completed(future_to_chunk, timeout=timeout_per_chunk):
                            chunk_size = future_to_chunk[future]
                            try:
                                result = future.result(timeout=60)
                                if result:
                                    filtered_combs.extend(result)
                                pbar.update(chunk_size)
                                completed += 1
                                
                                # 진행률 로깅
                                progress = pbar.n / total_items * 100
                                if progress % 10 < chunk_size / total_items * 100:
                                    logging.info(f"진행률: {progress:.0f}% "
                                               f"({pbar.n:,}/{total_items:,}), "
                                               f"메모리: {current_memory:.1f}MB")
                                    
                            except TimeoutError:
                                logging.error(f"청크 처리 타임아웃 (크기: {chunk_size})")
                                # 타임아웃된 청크는 원본 그대로 추가
                                filtered_combs.extend(batch_chunks[completed])
                                
                            except Exception as exc:
                                logging.error(f"청크 처리 오류: {str(exc)}")
                                logging.debug(traceback.format_exc())
                                
                    except TimeoutError:
                        logging.error(f"배치 처리 전체 타임아웃")
                        # 남은 청크들은 원본 그대로 추가
                        for i in range(completed, len(batch_chunks)):
                            filtered_combs.extend(batch_chunks[i])
            
            # 최종 메모리 정리
            gc.collect()
            
        return filtered_combs

    @staticmethod
    def _process_chunk_wrapper_improved(chunk: List[str], base_func: Callable, **kwargs) -> List[str]:
        """개선된 청크 처리 래퍼"""
        try:
            # 프로세스별 로깅 설정
            FlushingLogger.setup()
            
            # 처리 시작 로깅
            if len(chunk) > 10000:
                logging.debug(f"[Worker-{os.getpid()}] "
                            f"청크 처리 시작: {len(chunk):,}개")
            
            result = base_func(chunk, **kwargs)
            
            # 처리 완료 로깅
            if len(chunk) > 10000:
                logging.debug(f"[Worker-{os.getpid()}] "
                            f"청크 처리 완료: {len(chunk):,} -> {len(result):,}")
            
            return result
            
        except Exception as e:
            logging.error(f"[Worker-{os.getpid()}] "
                        f"청크 처리 중 오류: {str(e)}")
            logging.debug(traceback.format_exc())
            # 오류 시 빈 리스트 반환 (원본 반환하면 필터링 안됨)
            return []

# 사용 예시
if __name__ == "__main__":
    # 테스트를 위한 간단한 필터 함수
    def test_filter(chunk, **kwargs):
        """테스트용 필터 함수"""
        return [c for c in chunk if int(c.split(',')[0]) % 2 == 0]
    
    # 테스트 데이터 생성
    test_combinations = [f"{i},{i+1},{i+2},{i+3},{i+4},{i+5}" 
                        for i in range(1, 100001)]
    
    # 최적화 적용
    optimizer = ImprovedFilterOptimizer(test_filter, chunk_size=10000, max_workers=2)
    result = optimizer.optimize_filter(test_combinations, "테스트 필터")
    
    print(f"결과: {len(result):,}개")