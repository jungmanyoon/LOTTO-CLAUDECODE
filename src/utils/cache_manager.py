import os
import json
import pickle
import hashlib
import time
import logging
from typing import Any, Optional, Dict, List
from pathlib import Path
import shutil

class CacheManager:
    """필터링 결과 캐싱을 위한 매니저"""
    
    def __init__(self, cache_dir: str = "cache"):
        """캐시 매니저 초기화
        
        Args:
            cache_dir: 캐시 디렉토리 경로
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 캐시 설정
        self.cache_ttl = 3600 * 24  # 24시간
        self.max_cache_size = 1024 * 1024 * 1024  # 1GB
        
        # 메모리 캐시 (자주 사용되는 항목)
        self._memory_cache: Dict[str, Any] = {}
        self._memory_cache_size = 100  # 최대 100개 항목
        
        # 캐시 통계
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
        
        logging.info(f"캐시 매니저 초기화: {self.cache_dir}")
    
    def _generate_key(self, filter_name: str, round_num: int, 
                     combinations_hash: str, criteria: Dict) -> str:
        """캐시 키 생성
        
        Args:
            filter_name: 필터 이름
            round_num: 회차 번호
            combinations_hash: 조합 목록의 해시
            criteria: 필터 기준
            
        Returns:
            str: 캐시 키
        """
        # 키 구성 요소
        key_data = {
            'filter': filter_name,
            'round': round_num,
            'combinations': combinations_hash,
            'criteria': criteria
        }
        
        # JSON으로 직렬화 후 해시
        key_str = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()
        
        return f"{filter_name}_{round_num}_{key_hash[:16]}"
    
    def _get_combinations_hash(self, combinations: List[str]) -> str:
        """조합 목록의 해시 생성
        
        Args:
            combinations: 조합 목록
            
        Returns:
            str: 해시값
        """
        # 조합을 정렬하여 순서에 무관하게 만듦
        sorted_combos = sorted(combinations)
        
        # 처음과 마지막 일부 + 전체 개수로 해시 생성
        sample_size = min(100, len(sorted_combos))
        sample = sorted_combos[:sample_size] + sorted_combos[-sample_size:]
        sample.append(str(len(sorted_combos)))
        
        sample_str = '|'.join(sample)
        return hashlib.md5(sample_str.encode()).hexdigest()
    
    def get(self, filter_name: str, round_num: int, 
            combinations: List[str], criteria: Dict) -> Optional[List[str]]:
        """캐시에서 필터링 결과 조회
        
        Args:
            filter_name: 필터 이름
            round_num: 회차 번호
            combinations: 입력 조합
            criteria: 필터 기준
            
        Returns:
            Optional[List[str]]: 캐시된 결과 또는 None
        """
        try:
            # 캐시 키 생성
            combo_hash = self._get_combinations_hash(combinations)
            cache_key = self._generate_key(filter_name, round_num, combo_hash, criteria)
            
            # 메모리 캐시 확인
            if cache_key in self._memory_cache:
                self.stats['hits'] += 1
                logging.debug(f"메모리 캐시 히트: {cache_key}")
                return self._memory_cache[cache_key]['data']
            
            # 디스크 캐시 확인
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            if cache_file.exists():
                # 만료 시간 확인
                if time.time() - cache_file.stat().st_mtime < self.cache_ttl:
                    with open(cache_file, 'rb') as f:
                        data = pickle.load(f)
                    
                    # 메모리 캐시에 추가
                    self._add_to_memory_cache(cache_key, data)
                    
                    self.stats['hits'] += 1
                    logging.debug(f"디스크 캐시 히트: {cache_key}")
                    return data
                else:
                    # 만료된 캐시 삭제
                    cache_file.unlink()
                    self.stats['evictions'] += 1
            
            self.stats['misses'] += 1
            return None
            
        except Exception as e:
            logging.error(f"캐시 조회 중 오류: {str(e)}")
            return None
    
    def set(self, filter_name: str, round_num: int, 
            combinations: List[str], criteria: Dict, 
            result: List[str]) -> bool:
        """필터링 결과를 캐시에 저장
        
        Args:
            filter_name: 필터 이름
            round_num: 회차 번호
            combinations: 입력 조합
            criteria: 필터 기준
            result: 필터링 결과
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 캐시 키 생성
            combo_hash = self._get_combinations_hash(combinations)
            cache_key = self._generate_key(filter_name, round_num, combo_hash, criteria)
            
            # 디스크에 저장
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            with open(cache_file, 'wb') as f:
                pickle.dump(result, f)
            
            # 메모리 캐시에 추가
            self._add_to_memory_cache(cache_key, result)
            
            # 캐시 크기 관리
            self._manage_cache_size()
            
            logging.debug(f"캐시 저장: {cache_key}")
            return True
            
        except Exception as e:
            logging.error(f"캐시 저장 중 오류: {str(e)}")
            return False
    
    def _add_to_memory_cache(self, key: str, data: Any):
        """메모리 캐시에 항목 추가"""
        # 크기 제한 확인
        if len(self._memory_cache) >= self._memory_cache_size:
            # 가장 오래된 항목 제거 (간단한 FIFO)
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]
        
        self._memory_cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def _manage_cache_size(self):
        """캐시 크기 관리"""
        try:
            # 전체 캐시 크기 계산
            total_size = 0
            cache_files = []
            
            for cache_file in self.cache_dir.glob("*.pkl"):
                size = cache_file.stat().st_size
                mtime = cache_file.stat().st_mtime
                cache_files.append((cache_file, size, mtime))
                total_size += size
            
            # 크기 초과 시 오래된 파일부터 삭제
            if total_size > self.max_cache_size:
                # 수정 시간 기준 정렬
                cache_files.sort(key=lambda x: x[2])
                
                for cache_file, size, _ in cache_files:
                    if total_size <= self.max_cache_size:
                        break
                    
                    cache_file.unlink()
                    total_size -= size
                    self.stats['evictions'] += 1
                    
        except Exception as e:
            logging.error(f"캐시 크기 관리 중 오류: {str(e)}")
    
    def clear(self, filter_name: Optional[str] = None):
        """캐시 삭제
        
        Args:
            filter_name: 특정 필터의 캐시만 삭제 (None이면 전체)
        """
        try:
            if filter_name:
                # 특정 필터 캐시 삭제
                pattern = f"{filter_name}_*.pkl"
                for cache_file in self.cache_dir.glob(pattern):
                    cache_file.unlink()
                
                # 메모리 캐시에서도 제거
                keys_to_remove = [k for k in self._memory_cache if k.startswith(filter_name)]
                for key in keys_to_remove:
                    del self._memory_cache[key]
                
                logging.info(f"{filter_name} 필터 캐시 삭제 완료")
            else:
                # 전체 캐시 삭제
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self._memory_cache.clear()
                logging.info("전체 캐시 삭제 완료")
                
        except Exception as e:
            logging.error(f"캐시 삭제 중 오류: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        hit_rate = 0
        if self.stats['hits'] + self.stats['misses'] > 0:
            hit_rate = self.stats['hits'] / (self.stats['hits'] + self.stats['misses']) * 100
        
        # 캐시 크기 계산
        cache_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl"))
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': f"{hit_rate:.1f}%",
            'evictions': self.stats['evictions'],
            'memory_cache_size': len(self._memory_cache),
            'disk_cache_size': f"{cache_size / 1024 / 1024:.1f} MB",
            'cache_dir': str(self.cache_dir)
        }
    
    def preload_common_filters(self, round_num: int):
        """자주 사용되는 필터 결과를 미리 로드"""
        common_filters = ['sum_range', 'consecutive', 'odd_even', 'section']
        
        for filter_name in common_filters:
            pattern = f"{filter_name}_{round_num}_*.pkl"
            for cache_file in self.cache_dir.glob(pattern):
                if len(self._memory_cache) >= self._memory_cache_size:
                    break
                
                try:
                    key = cache_file.stem
                    with open(cache_file, 'rb') as f:
                        data = pickle.load(f)
                    self._add_to_memory_cache(key, data)
                    
                except Exception as e:
                    logging.warning(f"캐시 프리로드 실패: {cache_file}, {str(e)}")