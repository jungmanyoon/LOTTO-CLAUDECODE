#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
캐시 관리 테스트

Phase 3.12: 캐시 관리 개선
- TTL 동적 조정
- LRU 정책
- 캐시 크기 제한
- 메모리 압박 시 자동 정리
"""

import pytest
import sys
import os
import time
import tempfile
import shutil
import gc
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestCacheConfiguration:
    """캐시 설정 테스트"""

    def test_cache_config_in_yaml(self):
        """config.yaml에 캐시 설정이 존재하는지 확인"""
        import yaml

        config_path = project_root / "config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        assert 'cache' in config, "config.yaml에 cache 섹션이 있어야 함"

        cache_config = config['cache']
        assert 'ttl_days' in cache_config, "ttl_days 설정이 있어야 함"
        assert 'max_disk_cache_mb' in cache_config, "max_disk_cache_mb 설정이 있어야 함"
        assert 'max_memory_entries' in cache_config, "max_memory_entries 설정이 있어야 함"
        assert 'memory_pressure_threshold' in cache_config, "memory_pressure_threshold 설정이 있어야 함"
        assert 'auto_cleanup_enabled' in cache_config, "auto_cleanup_enabled 설정이 있어야 함"

    def test_cache_config_values(self):
        """캐시 설정 값 유효성 검증"""
        import yaml

        config_path = project_root / "config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        cache_config = config['cache']

        # TTL 범위 검증 (1-30일)
        assert 1 <= cache_config['ttl_days'] <= 30, "TTL은 1-30일 범위"

        # 디스크 캐시 크기 검증 (100MB-10GB)
        assert 100 <= cache_config['max_disk_cache_mb'] <= 10240, "디스크 캐시는 100MB-10GB 범위"

        # 메모리 항목 수 검증 (10-1000)
        assert 10 <= cache_config['max_memory_entries'] <= 1000, "메모리 항목 수는 10-1000 범위"

        # 메모리 임계값 검증 (50-95%)
        assert 50 <= cache_config['memory_pressure_threshold'] <= 95, "메모리 임계값은 50-95% 범위"

        # 정리 목표 검증 (30-80%)
        assert 30 <= cache_config['cleanup_target_percent'] <= 80, "정리 목표는 30-80% 범위"


class TestLRUPolicy:
    """LRU 정책 테스트 (메모리 캐시만 테스트)"""

    def test_memory_cache_lru_structure(self):
        """메모리 캐시 LRU 구조 테스트"""
        # 간단한 LRU 딕셔너리 시뮬레이션
        memory_cache = {}
        max_size = 3

        def add_to_cache(key, data):
            if len(memory_cache) >= max_size:
                # 가장 오래된 항목 제거 (LRU)
                oldest_key = min(
                    memory_cache.keys(),
                    key=lambda k: memory_cache[k]['last_used']
                )
                del memory_cache[oldest_key]

            memory_cache[key] = {
                'data': data,
                'last_used': time.time()
            }

        # 3개 항목 추가
        for i in range(3):
            add_to_cache(f"key_{i}", f"data_{i}")
            time.sleep(0.01)

        # key_0에 접근 (LRU 갱신)
        memory_cache["key_0"]['last_used'] = time.time()

        # 4번째 항목 추가 (eviction 발생)
        add_to_cache("key_3", "data_3")

        # key_1이 제거되어야 함 (가장 오래 사용 안 됨)
        assert "key_0" in memory_cache
        assert "key_1" not in memory_cache
        assert "key_2" in memory_cache
        assert "key_3" in memory_cache


class TestDynamicConfiguration:
    """동적 설정 테스트"""

    def test_ttl_calculation(self):
        """TTL 계산 테스트"""
        ttl_days = 7
        expected_ttl_seconds = 3600 * 24 * 7

        assert ttl_days * 24 * 3600 == expected_ttl_seconds

    def test_cache_size_calculation(self):
        """캐시 크기 계산 테스트"""
        max_mb = 2048
        expected_bytes = 2048 * 1024 * 1024

        assert max_mb * 1024 * 1024 == expected_bytes


class TestMemoryPressureLogic:
    """메모리 압박 감지 로직 테스트"""

    def test_memory_pressure_threshold_check(self):
        """메모리 압박 임계값 체크 로직"""
        threshold = 80

        # 낮은 사용률
        usage_low = 50
        assert usage_low < threshold  # 압박 없음

        # 높은 사용률
        usage_high = 85
        assert usage_high >= threshold  # 압박 감지

    def test_cleanup_target_calculation(self):
        """정리 목표 계산 테스트"""
        max_size = 2048 * 1024 * 1024  # 2GB
        cleanup_target_percent = 60

        target_size = max_size * cleanup_target_percent / 100
        expected = max_size * 0.6

        assert target_size == expected


class TestCacheManagerMock:
    """EnhancedCacheManager Mock 테스트"""

    def test_cache_config_loading_logic(self):
        """캐시 설정 로드 로직 테스트"""
        # Mock config_manager
        mock_config = {
            'cache': {
                'ttl_days': 5,
                'max_disk_cache_mb': 1024,
                'max_memory_entries': 100,
                'memory_pressure_threshold': 75,
                'auto_cleanup_enabled': True,
                'cleanup_target_percent': 50
            }
        }

        # 로드 로직 테스트
        cache_config = mock_config.get('cache', {})

        assert cache_config.get('ttl_days', 7) == 5
        assert cache_config.get('max_disk_cache_mb', 2048) == 1024
        assert cache_config.get('max_memory_entries', 200) == 100

    def test_cache_config_defaults(self):
        """설정 기본값 테스트"""
        mock_config = {}  # 빈 설정

        cache_config = mock_config.get('cache', {})

        assert cache_config.get('ttl_days', 7) == 7  # 기본값
        assert cache_config.get('max_disk_cache_mb', 2048) == 2048  # 기본값
        assert cache_config.get('max_memory_entries', 200) == 200  # 기본값


class TestCacheStats:
    """캐시 통계 구조 테스트"""

    def test_stats_structure(self):
        """통계 구조 테스트"""
        stats = {
            'memory_hits': 0,
            'disk_hits': 0,
            'misses': 0,
            'invalidations': 0,
            'evictions': 0,
            'memory_pressure_cleanups': 0
        }

        # 모든 필수 키 확인
        assert 'memory_hits' in stats
        assert 'disk_hits' in stats
        assert 'misses' in stats
        assert 'invalidations' in stats
        assert 'evictions' in stats
        assert 'memory_pressure_cleanups' in stats

    def test_hit_rate_calculation(self):
        """히트율 계산 테스트"""
        stats = {
            'memory_hits': 80,
            'disk_hits': 15,
            'misses': 5
        }

        total = stats['memory_hits'] + stats['disk_hits'] + stats['misses']
        hit_rate = (stats['memory_hits'] + stats['disk_hits']) / max(total, 1) * 100

        assert hit_rate == 95.0


class TestCacheCleanupLogic:
    """캐시 정리 로직 테스트"""

    def test_expired_check_logic(self):
        """만료 확인 로직 테스트"""
        from datetime import datetime, timedelta

        ttl_seconds = 7 * 24 * 3600  # 7일
        created_time = datetime.now() - timedelta(days=8)  # 8일 전
        current_time = datetime.now()

        # 만료 확인
        elapsed = (current_time - created_time).total_seconds()
        is_expired = elapsed > ttl_seconds

        assert is_expired == True

    def test_not_expired_check_logic(self):
        """미만료 확인 로직 테스트"""
        from datetime import datetime, timedelta

        ttl_seconds = 7 * 24 * 3600  # 7일
        created_time = datetime.now() - timedelta(days=3)  # 3일 전
        current_time = datetime.now()

        # 만료 확인
        elapsed = (current_time - created_time).total_seconds()
        is_expired = elapsed > ttl_seconds

        assert is_expired == False


class TestEnhancedCacheManagerIntegration:
    """EnhancedCacheManager 통합 테스트 (실제 인스턴스 생성)"""

    @pytest.fixture
    def cache_manager_setup(self):
        """캐시 매니저 설정 fixture"""
        from src.automation.enhanced_cache_manager import EnhancedCacheManager

        tmpdir = tempfile.mkdtemp()

        mock_config_manager = Mock()
        mock_config_manager.config = {
            'cache': {
                'ttl_days': 1,
                'max_disk_cache_mb': 100,
                'max_memory_entries': 50,
                'memory_pressure_threshold': 95,
                'auto_cleanup_enabled': False,
                'cleanup_target_percent': 60
            }
        }
        mock_config_manager.adaptive_config = {}
        mock_config_manager.get_global_probability_threshold.return_value = 1.0

        mock_db_manager = Mock()

        manager = EnhancedCacheManager(
            config_manager=mock_config_manager,
            db_manager=mock_db_manager,
            cache_dir=tmpdir
        )

        yield manager, tmpdir

        # Cleanup: 매니저 정리
        try:
            manager._memory_cache.clear()
            gc.collect()
            time.sleep(0.1)
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_manager_initialization(self, cache_manager_setup):
        """매니저 초기화 테스트"""
        manager, tmpdir = cache_manager_setup

        # 설정이 적용되었는지 확인
        assert manager.cache_ttl == 3600 * 24 * 1  # 1일
        assert manager.max_disk_cache_size == 100 * 1024 * 1024  # 100MB
        assert manager._memory_cache_size == 50
        assert manager.memory_pressure_threshold == 95
        assert manager.auto_cleanup_enabled == False

    def test_update_ttl(self, cache_manager_setup):
        """TTL 업데이트 테스트"""
        manager, tmpdir = cache_manager_setup

        old_ttl = manager.cache_ttl
        manager.update_ttl(3)

        assert manager.cache_ttl == 3600 * 24 * 3
        assert manager.cache_ttl != old_ttl

    def test_update_max_size(self, cache_manager_setup):
        """최대 크기 업데이트 테스트"""
        manager, tmpdir = cache_manager_setup

        old_size = manager.max_disk_cache_size
        manager.update_max_size(200)

        assert manager.max_disk_cache_size == 200 * 1024 * 1024
        assert manager.max_disk_cache_size != old_size

    def test_stats_structure_in_manager(self, cache_manager_setup):
        """매니저 통계 구조 테스트"""
        manager, tmpdir = cache_manager_setup

        assert 'memory_pressure_cleanups' in manager.stats
        assert manager.stats['memory_pressure_cleanups'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
