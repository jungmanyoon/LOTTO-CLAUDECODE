#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pytest 설정 및 공통 픽스처

이 파일은 모든 테스트에서 공통으로 사용하는 픽스처와 설정을 정의합니다.
"""

import pytest
import sys
import os
from pathlib import Path
import tempfile
import shutil

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def project_root_dir():
    """프로젝트 루트 디렉토리 경로"""
    return project_root


@pytest.fixture(scope="session")
def test_db_dir(tmp_path_factory):
    """테스트용 임시 데이터베이스 디렉토리"""
    db_dir = tmp_path_factory.mktemp("data")
    return db_dir


@pytest.fixture(scope="function")
def test_db_path(test_db_dir):
    """테스트용 임시 데이터베이스 경로"""
    return test_db_dir / "test_lotto.db"


@pytest.fixture(scope="function")
def db_manager(test_db_path):
    """테스트용 DatabaseManager 인스턴스"""
    from src.core.db_manager import DatabaseManager

    # 테스트용 DB 경로로 DatabaseManager 생성
    db = DatabaseManager(db_path=str(test_db_path))

    yield db

    # 테스트 후 정리
    try:
        db.close()
    except:
        pass


@pytest.fixture(scope="function")
def sample_lotto_numbers():
    """테스트용 샘플 로또 번호"""
    return [
        (1, [1, 2, 3, 4, 5, 6], 7, "2002-12-07"),
        (2, [7, 8, 9, 10, 11, 12], 13, "2002-12-14"),
        (3, [14, 15, 16, 17, 18, 19], 20, "2002-12-21"),
        (4, [21, 22, 23, 24, 25, 26], 27, "2002-12-28"),
        (5, [28, 29, 30, 31, 32, 33], 34, "2003-01-04"),
    ]


@pytest.fixture(scope="function")
def mock_filter_manager(db_manager):
    """테스트용 FilterManager 목업"""
    from src.core.filter_manager import FilterManager
    return FilterManager(db_manager)


@pytest.fixture(scope="function")
def temp_cache_dir(tmp_path):
    """테스트용 임시 캐시 디렉토리"""
    cache_dir = tmp_path / "cache" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture(scope="function")
def temp_config_file(tmp_path):
    """테스트용 임시 설정 파일"""
    config_file = tmp_path / "test_config.yaml"
    config_content = """
# Test configuration
filtering:
  batch_size: 1000
  memory_limit_mb: 100

filter_manager:
  max_workers: 2
  connection_pool_size: 4
"""
    config_file.write_text(config_content, encoding='utf-8')
    return config_file


# 테스트 설정
def pytest_configure(config):
    """Pytest 설정"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "critical: marks tests as critical path tests"
    )


def pytest_collection_modifyitems(config, items):
    """테스트 수집 후 수정"""
    # 기본적으로 모든 테스트를 unit으로 마킹
    for item in items:
        if "integration" not in item.keywords and "slow" not in item.keywords:
            item.add_marker(pytest.mark.unit)
