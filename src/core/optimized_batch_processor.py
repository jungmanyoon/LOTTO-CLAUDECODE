#!/usr/bin/env python3
"""
최적화된 배치 처리 시스템
메모리 효율적인 814만개 조합 처리
"""
import logging
import psutil
import gc
from typing import List, Dict, Any, Generator
import time

class OptimizedBatchProcessor:
    """
    메모리 최적화된 배치 처리기
    - 동적 배치 크기 조정
    - 메모리 모니터링
    - 가비지 컬렉션 최적화
    """
    
    def __init__(self, db_manager, filter_manager, max_memory_usage: float = 0.7):
        """
        Args:
            db_manager: 데이터베이스 매니저
            filter_manager: 필터 매니저
            max_memory_usage: 최대 메모리 사용률 (0.7 = 70%)
        """
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        self.max_memory_usage = max_memory_usage
        
        # 배치 크기 설정
        self.min_batch_size = 10000
        self.max_batch_size = 200000
        self.current_batch_size = 100000
        
        # 통계
        self.stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'batches_processed': 0,
            'memory_peaks': [],
            'processing_times': []
        }
        
        logging.info(f"[배치 처리기] 초기화 (최대 메모리: {max_memory_usage*100:.0f}%)")
    
    def get_memory_usage(self) -> float:
        """현재 메모리 사용률"""
        return psutil.virtual_memory().percent / 100
    
    def adjust_batch_size(self) -> int:
        """
        메모리 상태에 따른 동적 배치 크기 조정
        
        Returns:
            조정된 배치 크기
        """
        memory_usage = self.get_memory_usage()
        
        if memory_usage > self.max_memory_usage:
            # 메모리 부족: 배치 크기 감소
            self.current_batch_size = max(
                self.min_batch_size,
                int(self.current_batch_size * 0.7)
            )
            logging.warning(f"메모리 부족 ({memory_usage*100:.1f}%) - 배치 크기 감소: {self.current_batch_size:,}")
            
            # 가비지 컬렉션 강제 실행
            gc.collect()
            
        elif memory_usage < 0.5:
            # 메모리 여유: 배치 크기 증가
            self.current_batch_size = min(
                self.max_batch_size,
                int(self.current_batch_size * 1.2)
            )
            logging.debug(f"메모리 여유 ({memory_usage*100:.1f}%) - 배치 크기 증가: {self.current_batch_size:,}")
        
        return self.current_batch_size
    
    def process_combinations_in_batches(self, round_num: int) -> Dict[str, Any]:
        """
        814만개 조합을 배치로 처리
        
        Args:
            round_num: 회차 번호
            
        Returns:
            처리 결과
        """
        logging.info("\n" + "="*60)
        logging.info("[배치 처리] 최적화된 필터링 시작")
        logging.info("="*60)
        
        start_time = time.time()
        
        try:
            # 전체 조합 수
            total_count = self.db_manager.combinations_db.count_all_combinations()
            logging.info(f"전체 조합: {total_count:,}개")
            
            # 초기 메모리 상태
            initial_memory = self.get_memory_usage()
            logging.info(f"초기 메모리: {initial_memory*100:.1f}%")
            
            # 배치 처리
            for batch, batch_info in self.batch_generator(total_count):
                # 메모리 체크 및 배치 크기 조정
                self.adjust_batch_size()
                
                # 필터링
                filtered = self.filter_manager.apply_all_filters(batch, round_num)
                
                # 필터링된 결과 저장 (옵션)
                # self.save_filtered_batch(filtered, batch_info)
                
                # 통계 업데이트
                self.update_statistics(len(batch), len(filtered))
                
                # 진행률 출력
                self.print_progress(batch_info, total_count)
                
                # 메모리 정리 (주기적)
                if self.stats['batches_processed'] % 10 == 0:
                    gc.collect()
            
            # 최종 결과
            duration = time.time() - start_time
            result = self.generate_report(duration, total_count)
            
            logging.info("\n" + "="*60)
            logging.info("[배치 처리] 완료")
            logging.info(f"  - 처리 시간: {duration:.1f}초")
            logging.info(f"  - 처리 속도: {total_count/duration:.0f}개/초")
            logging.info(f"  - 제외율: {result['exclusion_rate']:.1f}%")
            logging.info(f"  - 최대 메모리: {result['max_memory']:.1f}%")
            logging.info("="*60)
            
            return result
            
        except Exception as e:
            logging.error(f"배치 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def batch_generator(self, total_count: int) -> Generator:
        """
        배치 생성기 (메모리 효율적)
        
        Yields:
            (batch, batch_info) 튜플
        """
        offset = 0
        batch_num = 0
        
        while offset < total_count:
            # 현재 배치 크기
            batch_size = min(self.current_batch_size, total_count - offset)
            
            # 배치 가져오기
            batch = self._get_batch(offset, batch_size)
            
            if not batch:
                break
            
            batch_info = {
                'batch_num': batch_num,
                'offset': offset,
                'size': len(batch)
            }
            
            yield batch, batch_info
            
            offset += batch_size
            batch_num += 1
    
    def _get_batch(self, offset: int, limit: int) -> List[str]:
        """데이터베이스에서 배치 가져오기"""
        try:
            with self.db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT combination FROM base_combinations LIMIT ? OFFSET ?",
                    (limit, offset)
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"배치 로드 실패: {e}")
            return []
    
    def update_statistics(self, batch_size: int, filtered_size: int):
        """통계 업데이트"""
        self.stats['total_processed'] += batch_size
        self.stats['total_filtered'] += filtered_size
        self.stats['batches_processed'] += 1
        self.stats['memory_peaks'].append(self.get_memory_usage())
    
    def print_progress(self, batch_info: Dict, total_count: int):
        """진행률 출력"""
        progress = ((batch_info['offset'] + batch_info['size']) / total_count) * 100
        memory = self.get_memory_usage() * 100
        exclusion_rate = 0
        
        if self.stats['total_processed'] > 0:
            exclusion_rate = (1 - self.stats['total_filtered'] / self.stats['total_processed']) * 100
        
        # 10% 단위로만 출력
        if progress % 10 < (self.current_batch_size / total_count) * 100:
            logging.info(
                f"  진행: {progress:.0f}% | "
                f"제외율: {exclusion_rate:.1f}% | "
                f"메모리: {memory:.1f}% | "
                f"배치: {self.current_batch_size:,}"
            )
    
    def generate_report(self, duration: float, total_count: int) -> Dict[str, Any]:
        """처리 결과 리포트 생성"""
        exclusion_rate = 0
        if self.stats['total_processed'] > 0:
            exclusion_rate = (1 - self.stats['total_filtered'] / self.stats['total_processed']) * 100
        
        max_memory = max(self.stats['memory_peaks']) * 100 if self.stats['memory_peaks'] else 0
        
        return {
            'success': True,
            'total_processed': self.stats['total_processed'],
            'total_filtered': self.stats['total_filtered'],
            'exclusion_rate': exclusion_rate,
            'batches': self.stats['batches_processed'],
            'duration': duration,
            'throughput': total_count / duration if duration > 0 else 0,
            'max_memory': max_memory,
            'avg_batch_size': self.stats['total_processed'] / self.stats['batches_processed'] 
                             if self.stats['batches_processed'] > 0 else 0
        }
    
    def reset_statistics(self):
        """통계 초기화"""
        self.stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'batches_processed': 0,
            'memory_peaks': [],
            'processing_times': []
        }
        gc.collect()