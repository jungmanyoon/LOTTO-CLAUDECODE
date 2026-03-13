#!/usr/bin/env python3
"""
EnhancedCacheManager - 통합 지능형 캐시 관리 시스템
- 기존 CacheManager + IntelligentCacheManager 통합
- 설정 변경 기반 자동 무효화
- 계층적 캐시 전략 (메모리 + 디스크)
- 정합성 보장 메커니즘
"""

import os
import json
import pickle
import hashlib
import time
import sqlite3
import logging
import threading
import shutil
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import yaml

class CacheType(Enum):
    FILTER_RESULT = "filter_result"
    COMBINATIONS = "combinations"  
    PATTERNS = "patterns"
    ML_MODEL = "ml_model"
    CONFIG_HASH = "config_hash"

@dataclass
class CacheEntry:
    """캐시 엔트리 정보"""
    key: str
    cache_type: CacheType
    created_at: datetime
    last_used: datetime
    access_count: int
    data_size: int
    round_num: int
    config_hash: str
    dependencies: List[str]  # 의존하는 다른 캐시 키들
    is_valid: bool

class EnhancedCacheManager:
    """통합 지능형 캐시 관리자"""

    def __init__(self,
                 config_manager,
                 db_manager,
                 cache_dir: str = "cache"):
        """초기화

        Args:
            config_manager: ConfigManager 인스턴스
            db_manager: DatabaseManager 인스턴스
            cache_dir: 캐시 디렉토리 경로
        """
        self.config_manager = config_manager
        self.db_manager = db_manager

        # 캐시 디렉토리 설정
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 서브 디렉토리들
        self.filters_cache_dir = self.cache_dir / "filters"
        self.models_cache_dir = self.cache_dir / "models"
        self.patterns_cache_dir = self.cache_dir / "patterns"

        for subdir in [self.filters_cache_dir, self.models_cache_dir, self.patterns_cache_dir]:
            subdir.mkdir(parents=True, exist_ok=True)

        # 캐시 메타데이터 DB
        self.metadata_db_path = self.cache_dir / "cache_metadata.db"
        self._init_metadata_db()

        # 설정 파일에서 캐시 설정 로드
        cache_config = self._load_cache_config()

        # 메모리 캐시 (L1 캐시)
        self._memory_cache: Dict[str, Any] = {}
        self._memory_cache_size = cache_config.get('max_memory_entries', 200)
        self._memory_cache_lock = threading.RLock()

        # 캐시 설정 (설정 파일에서 로드)
        self.cache_ttl = 3600 * 24 * cache_config.get('ttl_days', 7)
        self.max_disk_cache_size = cache_config.get('max_disk_cache_mb', 2048) * 1024 * 1024
        self.memory_pressure_threshold = cache_config.get('memory_pressure_threshold', 80)
        self.auto_cleanup_enabled = cache_config.get('auto_cleanup_enabled', True)
        self.cleanup_target_percent = cache_config.get('cleanup_target_percent', 60)

        # 통계
        self.stats = {
            'memory_hits': 0,
            'disk_hits': 0,
            'misses': 0,
            'invalidations': 0,
            'evictions': 0,
            'memory_pressure_cleanups': 0
        }

        # 현재 설정 해시 계산
        self._current_config_hash = self._calculate_config_hash()

        logging.info(f"EnhancedCacheManager 초기화 완료: {self.cache_dir}")
        logging.info(f"캐시 설정 - TTL: {cache_config.get('ttl_days', 7)}일, "
                    f"최대 디스크: {cache_config.get('max_disk_cache_mb', 2048)}MB, "
                    f"메모리 항목: {self._memory_cache_size}")

    def _load_cache_config(self) -> Dict[str, Any]:
        """설정 파일에서 캐시 설정 로드"""
        try:
            if hasattr(self.config_manager, 'config') and self.config_manager.config:
                return self.config_manager.config.get('cache', {})
        except Exception as e:
            logging.warning(f"캐시 설정 로드 실패, 기본값 사용: {e}")
        return {}
    
    def _init_metadata_db(self):
        """캐시 메타데이터 DB 초기화"""
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    cache_type TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    last_used TIMESTAMP NOT NULL,
                    access_count INTEGER DEFAULT 1,
                    data_size INTEGER DEFAULT 0,
                    round_num INTEGER,
                    config_hash TEXT,
                    dependencies TEXT,  -- JSON array
                    is_valid BOOLEAN DEFAULT 1,
                    file_path TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    config_content TEXT,
                    invalidated_entries INTEGER DEFAULT 0
                )
            """)
            
            # 인덱스 생성
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_type ON cache_entries(cache_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_round_num ON cache_entries(round_num)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_config_hash ON cache_entries(config_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_is_valid ON cache_entries(is_valid)")
    
    def _calculate_config_hash(self) -> str:
        """현재 설정의 해시값 계산"""
        try:
            # 주요 설정들을 조합하여 해시 생성
            config_data = {
                'main_config': self.config_manager.config,
                'adaptive_config': self.config_manager.adaptive_config,
                'global_threshold': self.config_manager.get_global_probability_threshold()
            }
            
            # JSON 직렬화 후 해시
            config_str = json.dumps(config_data, sort_keys=True)
            return hashlib.sha256(config_str.encode()).hexdigest()
            
        except Exception as e:
            logging.error(f"설정 해시 계산 실패: {e}")
            return "unknown"
    
    def _generate_cache_key(self, 
                           cache_type: CacheType,
                           identifier: str,
                           round_num: int = 0,
                           additional_params: Optional[Dict] = None) -> str:
        """캐시 키 생성
        
        Args:
            cache_type: 캐시 타입
            identifier: 식별자 (필터명, 패턴명 등)
            round_num: 회차 번호
            additional_params: 추가 파라미터
        """
        # 기본 키 구성 요소
        key_parts = [
            cache_type.value,
            identifier,
            str(round_num),
            self._current_config_hash[:12]  # 처음 12자리만 사용
        ]
        
        # 추가 파라미터가 있으면 포함
        if additional_params:
            params_str = json.dumps(additional_params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            key_parts.append(params_hash)
        
        return "_".join(key_parts)
    
    def _get_file_path(self, cache_key: str, cache_type: CacheType) -> Path:
        """캐시 파일 경로 생성"""
        if cache_type == CacheType.FILTER_RESULT:
            return self.filters_cache_dir / f"{cache_key}.pkl"
        elif cache_type == CacheType.ML_MODEL:
            return self.models_cache_dir / f"{cache_key}.pkl"
        elif cache_type == CacheType.PATTERNS:
            return self.patterns_cache_dir / f"{cache_key}.pkl"
        else:
            return self.cache_dir / f"{cache_key}.pkl"
    
    def get(self, 
            cache_type: CacheType,
            identifier: str,
            round_num: int = 0,
            additional_params: Optional[Dict] = None) -> Optional[Any]:
        """캐시에서 데이터 조회
        
        Args:
            cache_type: 캐시 타입
            identifier: 식별자
            round_num: 회차 번호
            additional_params: 추가 파라미터
            
        Returns:
            캐시된 데이터 또는 None
        """
        cache_key = self._generate_cache_key(cache_type, identifier, round_num, additional_params)
        
        # 1. 메모리 캐시 확인
        with self._memory_cache_lock:
            if cache_key in self._memory_cache:
                entry = self._memory_cache[cache_key]
                if entry['is_valid'] and time.time() - entry['timestamp'] < self.cache_ttl:
                    self.stats['memory_hits'] += 1
                    self._update_access_time(cache_key)
                    logging.debug(f"메모리 캐시 히트: {cache_key}")
                    return entry['data']
                else:
                    # 만료된 메모리 캐시 제거
                    del self._memory_cache[cache_key]
        
        # 2. 디스크 캐시 확인
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                cursor = conn.execute("""
                    SELECT file_path, is_valid, created_at, config_hash
                    FROM cache_entries 
                    WHERE cache_key = ?
                """, (cache_key,))
                
                row = cursor.fetchone()
                if not row:
                    self.stats['misses'] += 1
                    return None
                
                file_path, is_valid, created_at, config_hash = row
                
                # 유효성 확인
                if not is_valid or config_hash != self._current_config_hash:
                    self.stats['misses'] += 1
                    return None
                
                # 만료 시간 확인
                created_time = datetime.fromisoformat(created_at).timestamp()
                if time.time() - created_time > self.cache_ttl:
                    self._invalidate_entry(cache_key)
                    self.stats['misses'] += 1
                    return None
                
                # 파일 존재 확인
                file_path_obj = Path(file_path) if file_path else self._get_file_path(cache_key, cache_type)
                if not file_path_obj.exists():
                    self._invalidate_entry(cache_key)
                    self.stats['misses'] += 1
                    return None
                
                # 데이터 로드
                with open(file_path_obj, 'rb') as f:
                    data = pickle.load(f)
                
                # 메모리 캐시에 추가
                self._add_to_memory_cache(cache_key, data)
                
                # 접근 시간 업데이트
                self._update_access_time(cache_key)
                
                self.stats['disk_hits'] += 1
                logging.debug(f"디스크 캐시 히트: {cache_key}")
                return data
                
        except Exception as e:
            logging.error(f"디스크 캐시 조회 실패: {cache_key}, {e}")
            self.stats['misses'] += 1
            return None
    
    def set(self, 
            cache_type: CacheType,
            identifier: str,
            data: Any,
            round_num: int = 0,
            additional_params: Optional[Dict] = None,
            dependencies: Optional[List[str]] = None) -> bool:
        """캐시에 데이터 저장
        
        Args:
            cache_type: 캐시 타입
            identifier: 식별자
            data: 저장할 데이터
            round_num: 회차 번호
            additional_params: 추가 파라미터
            dependencies: 의존하는 캐시 키들
            
        Returns:
            저장 성공 여부
        """
        cache_key = self._generate_cache_key(cache_type, identifier, round_num, additional_params)
        
        try:
            # 파일 경로 생성
            file_path = self._get_file_path(cache_key, cache_type)
            
            # 디스크에 저장
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
            
            # 데이터 크기 계산
            data_size = file_path.stat().st_size
            
            # 메타데이터 저장
            with sqlite3.connect(self.metadata_db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache_entries 
                    (cache_key, cache_type, created_at, last_used, access_count,
                     data_size, round_num, config_hash, dependencies, is_valid, file_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache_key,
                    cache_type.value,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    1,
                    data_size,
                    round_num,
                    self._current_config_hash,
                    json.dumps(dependencies or []),
                    True,
                    str(file_path)
                ))
            
            # 메모리 캐시에 추가
            self._add_to_memory_cache(cache_key, data)
            
            # 캐시 크기 관리
            self._manage_cache_size()
            
            logging.debug(f"캐시 저장 완료: {cache_key}")
            return True
            
        except Exception as e:
            logging.error(f"캐시 저장 실패: {cache_key}, {e}")
            return False
    
    def _add_to_memory_cache(self, cache_key: str, data: Any):
        """메모리 캐시에 데이터 추가"""
        with self._memory_cache_lock:
            # 크기 제한 확인
            if len(self._memory_cache) >= self._memory_cache_size:
                # LRU 방식으로 제거 (가장 오래 사용되지 않은 항목)
                oldest_key = min(
                    self._memory_cache.keys(),
                    key=lambda k: self._memory_cache[k]['last_used']
                )
                del self._memory_cache[oldest_key]
            
            # 새 항목 추가
            self._memory_cache[cache_key] = {
                'data': data,
                'timestamp': time.time(),
                'last_used': time.time(),
                'is_valid': True
            }
    
    def _update_access_time(self, cache_key: str):
        """접근 시간 업데이트"""
        # 메모리 캐시 업데이트
        with self._memory_cache_lock:
            if cache_key in self._memory_cache:
                self._memory_cache[cache_key]['last_used'] = time.time()
        
        # DB 업데이트 (비동기로)
        def update_db():
            try:
                with sqlite3.connect(self.metadata_db_path) as conn:
                    conn.execute("""
                        UPDATE cache_entries 
                        SET last_used = ?, access_count = access_count + 1
                        WHERE cache_key = ?
                    """, (datetime.now().isoformat(), cache_key))
            except Exception as e:
                logging.warning(f"접근 시간 업데이트 실패: {e}")
        
        threading.Thread(target=update_db, daemon=True).start()
    
    def _manage_cache_size(self):
        """캐시 크기 관리 (메모리 압박 감지 포함)"""
        try:
            # 1. 메모리 압박 확인 및 정리
            if self.auto_cleanup_enabled and self.check_memory_pressure():
                self.cleanup_on_memory_pressure()

            # 2. 전체 디스크 사용량 계산
            total_size = 0
            cache_files = []

            for cache_file in self.cache_dir.rglob("*.pkl"):
                if cache_file.exists():
                    size = cache_file.stat().st_size
                    mtime = cache_file.stat().st_mtime
                    cache_files.append((cache_file, size, mtime))
                    total_size += size

            # 3. 디스크 크기 초과 시 정리
            if total_size > self.max_disk_cache_size:
                logging.info(f"캐시 크기 초과: {total_size/1024/1024:.1f}MB, 정리 시작")

                # 접근 시간 기준 정렬 (오래된 것부터 - LRU)
                cache_files.sort(key=lambda x: x[2])

                target_size = self.max_disk_cache_size * self.cleanup_target_percent / 100
                for cache_file, size, _ in cache_files:
                    if total_size <= target_size:
                        break

                    # 파일 삭제
                    try:
                        cache_file.unlink()
                    except Exception:
                        continue

                    total_size -= size
                    self.stats['evictions'] += 1

                    # DB에서도 제거
                    cache_key = cache_file.stem
                    with sqlite3.connect(self.metadata_db_path) as conn:
                        conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))

                    # 메모리 캐시에서도 제거
                    with self._memory_cache_lock:
                        if cache_key in self._memory_cache:
                            del self._memory_cache[cache_key]

                logging.info(f"캐시 정리 완료: {total_size/1024/1024:.1f}MB")

        except Exception as e:
            logging.error(f"캐시 크기 관리 실패: {e}")
    
    def invalidate_by_config_change(self) -> int:
        """설정 변경으로 인한 캐시 무효화"""
        old_config_hash = self._current_config_hash
        new_config_hash = self._calculate_config_hash()
        
        if old_config_hash == new_config_hash:
            return 0  # 변경 없음
        
        logging.info(f"설정 변경 감지: {old_config_hash[:8]} -> {new_config_hash[:8]}")
        
        # 설정 해시 업데이트
        self._current_config_hash = new_config_hash
        
        # 이전 설정 기반 캐시들 무효화
        invalidated_count = 0
        
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 이전 설정 해시를 가진 캐시들 무효화
                cursor = conn.execute("""
                    UPDATE cache_entries 
                    SET is_valid = 0
                    WHERE config_hash != ?
                """, (new_config_hash,))
                
                invalidated_count = cursor.rowcount
                
                # 새 설정 버전 기록
                conn.execute("""
                    INSERT INTO config_versions (config_hash, created_at, config_content, invalidated_entries)
                    VALUES (?, ?, ?, ?)
                """, (
                    new_config_hash,
                    datetime.now().isoformat(),
                    json.dumps({
                        'main_config': self.config_manager.config,
                        'adaptive_config': self.config_manager.adaptive_config
                    }),
                    invalidated_count
                ))
            
            # 메모리 캐시 전체 무효화 (안전을 위해)
            with self._memory_cache_lock:
                self._memory_cache.clear()
            
            self.stats['invalidations'] += invalidated_count
            logging.info(f"설정 변경으로 {invalidated_count}개 캐시 무효화")
            
        except Exception as e:
            logging.error(f"설정 변경 캐시 무효화 실패: {e}")
        
        return invalidated_count
    
    def invalidate_by_new_round(self, new_round: int) -> int:
        """새 회차로 인한 캐시 무효화"""
        invalidated_count = 0
        
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 이전 회차 기반 캐시들 무효화
                cursor = conn.execute("""
                    UPDATE cache_entries 
                    SET is_valid = 0
                    WHERE round_num > 0 AND round_num < ?
                """, (new_round,))
                
                invalidated_count = cursor.rowcount
            
            # 메모리 캐시에서도 해당 항목들 제거
            with self._memory_cache_lock:
                keys_to_remove = [
                    key for key in self._memory_cache
                    if f"round_{new_round-1}_" in key or f"round_{new_round-2}_" in key
                ]
                for key in keys_to_remove:
                    del self._memory_cache[key]
            
            self.stats['invalidations'] += invalidated_count
            logging.info(f"새 회차 {new_round}로 {invalidated_count}개 캐시 무효화")
            
        except Exception as e:
            logging.error(f"새 회차 캐시 무효화 실패: {e}")
        
        return invalidated_count
    
    def _invalidate_entry(self, cache_key: str):
        """특정 캐시 엔트리 무효화"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                conn.execute("""
                    UPDATE cache_entries 
                    SET is_valid = 0
                    WHERE cache_key = ?
                """, (cache_key,))
            
            # 메모리 캐시에서도 제거
            with self._memory_cache_lock:
                if cache_key in self._memory_cache:
                    del self._memory_cache[cache_key]
            
        except Exception as e:
            logging.warning(f"캐시 엔트리 무효화 실패: {cache_key}, {e}")
    
    def clear_by_type(self, cache_type: CacheType) -> int:
        """특정 타입의 캐시 전체 삭제"""
        cleared_count = 0
        
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 파일들 조회
                cursor = conn.execute("""
                    SELECT cache_key, file_path 
                    FROM cache_entries 
                    WHERE cache_type = ?
                """, (cache_type.value,))
                
                entries = cursor.fetchall()
                
                for cache_key, file_path in entries:
                    # 파일 삭제
                    try:
                        if file_path and Path(file_path).exists():
                            Path(file_path).unlink()
                    except Exception:
                        pass
                    
                    # 메모리 캐시에서 제거
                    with self._memory_cache_lock:
                        if cache_key in self._memory_cache:
                            del self._memory_cache[cache_key]
                    
                    cleared_count += 1
                
                # DB에서 삭제
                conn.execute("DELETE FROM cache_entries WHERE cache_type = ?", (cache_type.value,))
            
            logging.info(f"{cache_type.value} 캐시 {cleared_count}개 삭제 완료")
            
        except Exception as e:
            logging.error(f"타입별 캐시 삭제 실패 {cache_type.value}: {e}")
        
        return cleared_count
    
    def clear_all(self):
        """전체 캐시 삭제"""
        try:
            # 디렉토리 전체 삭제 후 재생성
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
            
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            # 서브 디렉토리 재생성
            for subdir in [self.filters_cache_dir, self.models_cache_dir, self.patterns_cache_dir]:
                subdir.mkdir(parents=True, exist_ok=True)
            
            # 메모리 캐시 초기화
            with self._memory_cache_lock:
                self._memory_cache.clear()
            
            # 메타데이터 DB 재초기화
            self._init_metadata_db()
            
            logging.info("전체 캐시 삭제 완료")
            
        except Exception as e:
            logging.error(f"전체 캐시 삭제 실패: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 타입별 통계
                cursor = conn.execute("""
                    SELECT cache_type, COUNT(*) as count, SUM(data_size) as total_size
                    FROM cache_entries 
                    WHERE is_valid = 1
                    GROUP BY cache_type
                """)
                
                type_stats = {row[0]: {'count': row[1], 'size_mb': round(row[2]/1024/1024, 2)} 
                             for row in cursor.fetchall()}
                
                # 전체 통계
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_entries,
                        SUM(data_size) as total_size,
                        AVG(access_count) as avg_access_count
                    FROM cache_entries 
                    WHERE is_valid = 1
                """)
                
                total_stats = cursor.fetchone()
        except Exception as e:
            logging.error(f"캐시 통계 조회 실패: {e}")
            type_stats = {}
            total_stats = (0, 0, 0)
        
        # 메모리 캐시 통계
        with self._memory_cache_lock:
            memory_stats = {
                'entries': len(self._memory_cache),
                'max_entries': self._memory_cache_size
            }
        
        return {
            'performance': {
                'memory_hits': self.stats['memory_hits'],
                'disk_hits': self.stats['disk_hits'],
                'misses': self.stats['misses'],
                'hit_rate': round((self.stats['memory_hits'] + self.stats['disk_hits']) / 
                                max(sum(self.stats.values()), 1) * 100, 2)
            },
            'storage': {
                'total_entries': total_stats[0] or 0,
                'total_size_mb': round((total_stats[1] or 0) / 1024 / 1024, 2),
                'avg_access_count': round(total_stats[2] or 0, 1),
                'by_type': type_stats
            },
            'memory_cache': memory_stats,
            'maintenance': {
                'invalidations': self.stats['invalidations'],
                'evictions': self.stats['evictions'],
                'current_config_hash': self._current_config_hash[:12]
            }
        }
    
    def get_cache_status(self, latest_round: int) -> Dict[str, Any]:
        """캐시 상태 정보 (호환성 메서드)"""
        stats = self.get_stats()
        
        return {
            'is_valid': True,
            'latest_round': latest_round,
            'total_entries': stats['storage']['total_entries'],
            'size_mb': stats['storage']['total_size_mb'],
            'hit_rate': f"{stats['performance']['hit_rate']}%",
            'config_hash': self._current_config_hash[:12]
        }
    
    def cleanup_expired(self) -> int:
        """만료된 캐시 정리"""
        cleaned_count = 0
        cutoff_time = datetime.now() - timedelta(seconds=self.cache_ttl)

        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 만료된 엔트리들 조회
                cursor = conn.execute("""
                    SELECT cache_key, file_path
                    FROM cache_entries
                    WHERE created_at < ?
                """, (cutoff_time.isoformat(),))

                expired_entries = cursor.fetchall()

                for cache_key, file_path in expired_entries:
                    # 파일 삭제
                    try:
                        if file_path and Path(file_path).exists():
                            Path(file_path).unlink()
                    except Exception:
                        pass

                    # 메모리에서 제거
                    with self._memory_cache_lock:
                        if cache_key in self._memory_cache:
                            del self._memory_cache[cache_key]

                    cleaned_count += 1

                # DB에서 삭제
                conn.execute("DELETE FROM cache_entries WHERE created_at < ?",
                           (cutoff_time.isoformat(),))

            logging.info(f"만료된 캐시 {cleaned_count}개 정리 완료")

        except Exception as e:
            logging.error(f"만료된 캐시 정리 실패: {e}")

        return cleaned_count

    def check_memory_pressure(self) -> bool:
        """메모리 압박 상태 확인

        Returns:
            True if memory usage exceeds threshold
        """
        try:
            memory = psutil.virtual_memory()
            return memory.percent >= self.memory_pressure_threshold
        except Exception as e:
            logging.warning(f"메모리 상태 확인 실패: {e}")
            return False

    def cleanup_on_memory_pressure(self) -> int:
        """메모리 압박 시 캐시 자동 정리

        시스템 메모리 사용률이 임계값을 초과하면 캐시를 정리합니다.
        LRU 정책에 따라 오래 사용되지 않은 항목부터 삭제합니다.

        Returns:
            정리된 캐시 항목 수
        """
        if not self.auto_cleanup_enabled:
            return 0

        if not self.check_memory_pressure():
            return 0

        logging.warning(f"메모리 압박 감지 (사용률 >= {self.memory_pressure_threshold}%), 캐시 정리 시작")

        cleaned_count = 0

        try:
            # 1. 메모리 캐시 50% 정리 (LRU 기반)
            with self._memory_cache_lock:
                if len(self._memory_cache) > 0:
                    # 마지막 사용 시간 기준 정렬
                    sorted_keys = sorted(
                        self._memory_cache.keys(),
                        key=lambda k: self._memory_cache[k].get('last_used', 0)
                    )
                    # 절반 삭제
                    keys_to_remove = sorted_keys[:len(sorted_keys) // 2]
                    for key in keys_to_remove:
                        del self._memory_cache[key]
                        cleaned_count += 1

            # 2. 디스크 캐시 정리 (목표 사용률까지)
            target_size = self.max_disk_cache_size * self.cleanup_target_percent / 100

            with sqlite3.connect(self.metadata_db_path) as conn:
                # 현재 디스크 사용량 계산
                cursor = conn.execute("SELECT SUM(data_size) FROM cache_entries WHERE is_valid = 1")
                current_size = cursor.fetchone()[0] or 0

                if current_size > target_size:
                    # LRU 순서로 삭제 대상 조회
                    cursor = conn.execute("""
                        SELECT cache_key, file_path, data_size
                        FROM cache_entries
                        WHERE is_valid = 1
                        ORDER BY last_used ASC
                    """)

                    for cache_key, file_path, data_size in cursor.fetchall():
                        if current_size <= target_size:
                            break

                        # 파일 삭제
                        try:
                            if file_path and Path(file_path).exists():
                                Path(file_path).unlink()
                        except Exception:
                            pass

                        # DB에서 삭제
                        conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))

                        current_size -= (data_size or 0)
                        cleaned_count += 1
                        self.stats['evictions'] += 1

            self.stats['memory_pressure_cleanups'] += 1
            logging.info(f"메모리 압박 정리 완료: {cleaned_count}개 항목 삭제")

            # 메모리 상태 다시 확인
            memory = psutil.virtual_memory()
            logging.info(f"정리 후 메모리 사용률: {memory.percent}%")

        except Exception as e:
            logging.error(f"메모리 압박 정리 실패: {e}")

        return cleaned_count

    def update_ttl(self, ttl_days: int):
        """TTL 동적 업데이트

        Args:
            ttl_days: 새로운 TTL (일)
        """
        old_ttl_days = self.cache_ttl // (3600 * 24)
        self.cache_ttl = 3600 * 24 * ttl_days
        logging.info(f"캐시 TTL 업데이트: {old_ttl_days}일 -> {ttl_days}일")

    def update_max_size(self, max_mb: int):
        """최대 디스크 캐시 크기 동적 업데이트

        Args:
            max_mb: 새로운 최대 크기 (MB)
        """
        old_max_mb = self.max_disk_cache_size // (1024 * 1024)
        self.max_disk_cache_size = max_mb * 1024 * 1024
        logging.info(f"캐시 최대 크기 업데이트: {old_max_mb}MB -> {max_mb}MB")

        # 새 크기가 작으면 즉시 정리
        if max_mb < old_max_mb:
            self._manage_cache_size()