"""
병렬 필터 매니저
- 필터들을 병렬로 처리하여 성능 향상
- multiprocessing 활용
"""

import logging
import time
from typing import List, Dict, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing as mp
from functools import partial

class ParallelFilterManager:
    """병렬 필터 처리 매니저"""
    
    def __init__(self, filter_manager):
        """
        Args:
            filter_manager: 기존 FilterManager 인스턴스
        """
        self.filter_manager = filter_manager
        # CPU 코어 수에 따라 동적으로 워커 수 결정 (최소 4개, 최대 8개)
        cpu_count = mp.cpu_count() or 4
        self.n_workers = min(max(4, cpu_count - 1), 8)  # CPU 코어 수 - 1, 최소 4개, 최대 8개
        logging.info(f"병렬 필터 매니저 초기화: {self.n_workers}개 워커 (CPU 코어: {cpu_count}개)")
    
    def apply_filters_parallel(self, combinations: List[str], round_num: int) -> List[str]:
        """필터를 병렬로 적용
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            필터링된 조합 목록
        """
        if not combinations:
            return []
        
        start_time = time.time()
        initial_count = len(combinations)
        
        # 독립적으로 실행 가능한 필터 그룹
        independent_filters = [
            'odd_even',
            'consecutive', 
            'sum_range',
            'fixed_step',
            'last_digit',
            'max_gap',
            'average',
            'arithmetic_sequence',
            'geometric_sequence',
            'prime_composite',
            'digit_sum',
            'dispersion'
        ]
        
        # 종속적 필터 (순차 실행 필요)
        dependent_filters = [
            'match',  # 당첨번호 DB 접근
            'section',
            'multiple',
            'ten_section',
            'ml_prediction'  # ML 모델 사용
        ]
        
        # 1단계: 독립 필터들 병렬 처리
        filtered_combinations = self._apply_independent_filters_parallel(
            combinations, independent_filters, round_num
        )
        
        # 2단계: 종속 필터들 순차 처리
        for filter_name in dependent_filters:
            if filter_name in self.filter_manager.filters:
                filter_obj = self.filter_manager.filters[filter_name]
                if filter_obj.criteria.get('enabled', True):
                    try:
                        before_count = len(filtered_combinations)
                        filtered_combinations = filter_obj.apply(filtered_combinations, round_num)
                        after_count = len(filtered_combinations)
                        
                        if before_count != after_count:
                            logging.info(f"{filter_name} 필터: {before_count:,} → {after_count:,}")
                    except Exception as e:
                        logging.error(f"{filter_name} 필터 적용 중 오류: {e}")
        
        elapsed_time = time.time() - start_time
        final_count = len(filtered_combinations)
        pass_rate = (final_count / initial_count * 100) if initial_count > 0 else 0
        
        logging.info(f"병렬 필터링 완료: {initial_count:,} → {final_count:,} "
                    f"({pass_rate:.2f}% 통과, {elapsed_time:.2f}초)")
        
        return filtered_combinations
    
    def _apply_independent_filters_parallel(self, combinations: List[str], 
                                           filter_names: List[str], 
                                           round_num: int) -> List[str]:
        """독립 필터들을 병렬로 적용
        
        각 필터를 별도 프로세스에서 실행하고 결과를 교집합으로 결합
        """
        if not filter_names:
            return combinations
        
        # 활성화된 필터만 선택
        active_filters = []
        for name in filter_names:
            if name in self.filter_manager.filters:
                filter_obj = self.filter_manager.filters[name]
                if filter_obj.criteria.get('enabled', True):
                    active_filters.append(name)
        
        if not active_filters:
            return combinations
        
        # 청크 단위로 분할하여 처리
        chunk_size = max(1000, len(combinations) // (self.n_workers * 2))
        chunks = [combinations[i:i+chunk_size] 
                 for i in range(0, len(combinations), chunk_size)]
        
        results = []
        
        # ThreadPoolExecutor 사용 (I/O 바운드 작업)
        with ThreadPoolExecutor(max_workers=self.n_workers) as executor:
            futures = []
            
            for chunk in chunks:
                future = executor.submit(
                    self._apply_filters_to_chunk,
                    chunk, active_filters, round_num
                )
                futures.append(future)
            
            # 결과 수집
            for future in as_completed(futures):
                try:
                    chunk_result = future.result(timeout=30)
                    results.extend(chunk_result)
                except Exception as e:
                    logging.error(f"청크 처리 중 오류: {e}")
        
        return results
    
    def _apply_filters_to_chunk(self, chunk: List[str], 
                               filter_names: List[str], 
                               round_num: int) -> List[str]:
        """청크에 여러 필터를 순차 적용"""
        filtered_chunk = chunk
        
        for filter_name in filter_names:
            if filter_name in self.filter_manager.filters:
                filter_obj = self.filter_manager.filters[filter_name]
                try:
                    filtered_chunk = filter_obj.apply(filtered_chunk, round_num)
                except Exception as e:
                    logging.error(f"{filter_name} 필터 적용 오류: {e}")
        
        return filtered_chunk
    
    def get_filter_statistics(self) -> Dict[str, Any]:
        """필터별 통계 정보 반환"""
        stats = {
            'total_filters': len(self.filter_manager.filters),
            'enabled_filters': sum(1 for f in self.filter_manager.filters.values() 
                                 if f.criteria.get('enabled', True)),
            'n_workers': self.n_workers,
            'filter_details': {}
        }
        
        for name, filter_obj in self.filter_manager.filters.items():
            stats['filter_details'][name] = {
                'enabled': filter_obj.criteria.get('enabled', True),
                'criteria': filter_obj.criteria
            }
        
        return stats