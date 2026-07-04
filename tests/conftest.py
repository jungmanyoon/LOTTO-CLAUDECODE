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


# ====================================================================
# [로그 격리] 테스트 로그가 운영 로그 파일(logs/lotto_app.log)을 오염시키지 않도록 차단
# --------------------------------------------------------------------
# 이유: ThresholdManager 등 일부 모듈은 root 로거(logging.warning/error)에 직접 기록한다.
#   어떤 모듈이든 한 번 setup_logging()을 호출하면 root 로거에 RotatingFileHandler(lotto_app.log)가
#   붙고, 그 이후 모든 테스트의 '의도된' WARNING/ERROR(경계값 거부 검증, 옵저버 실패 검증 등)가
#   운영 로그 파일에 섞여 들어간다. 그러면 실제 앱 실행 로그와 구분이 안 돼 오판을 부른다.
#   -> 테스트 중에는 운영 로그 파일 기록을 막고, 로그는 pytest 자체 캡처(caplog)에 맡긴다.
import logging as _logging
import logging.handlers as _logging_handlers


def _strip_production_log_handlers():
    """root 로거에 붙은 운영 로그 파일 핸들러(logs/ 또는 lotto_app)만 골라 제거한다.

    pytest 캡처 핸들러나 테스트가 의도적으로 만든 임시 파일 핸들러는 건드리지 않는다.
    """
    root = _logging.getLogger()
    for handler in root.handlers[:]:
        base = getattr(handler, "baseFilename", "") or ""
        normalized = base.replace("\\", "/")
        if "lotto_app" in normalized or "/logs/" in normalized:
            try:
                handler.close()
            except Exception:
                pass
            root.removeHandler(handler)


# conftest는 테스트 수집보다 먼저 로드되므로, 여기서 setup_logging을 '이미 완료' 상태로 표시하면
# 이후 어떤 모듈이 setup_logging()을 호출해도 운영 파일 핸들러를 새로 붙이지 않는다.
try:
    from src import logger as _proj_logger

    _proj_logger.setup_logging._initialized = True
except Exception:
    pass

# conftest 로드 시점에 이미 붙어 있던 운영 파일 핸들러가 있으면 청소한다.
_strip_production_log_handlers()


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
    # [F1 수정] 생성자 시그니처는 base_dir(디렉터리)다. 기존 db_path=(파일)는 잘못된 키워드라
    # 이 fixture가 소비되면 TypeError가 났다(현재 소비처 0이라 잠복). base_dir에 임시 디렉터리를
    # 전달하도록 교정(autouse reset_singletons가 매 테스트 DatabaseManager._instance를 리셋하므로 반영됨).
    db = DatabaseManager(base_dir=str(test_db_path.parent))

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


@pytest.fixture(scope="function", autouse=True)
def reset_singletons():
    """
    테스트 격리를 위한 싱글톤 리셋 픽스처

    모든 테스트 함수 전후로 자동 실행되어 싱글톤 상태를 초기화합니다.
    이를 통해 테스트 간 상태 오염을 방지합니다.

    Phase 1.2: Test Isolation Fix (CRITICAL)
    """
    # 테스트 실행 전: 싱글톤 인스턴스 저장
    saved_instances = {}

    # ThresholdManager 리셋
    # [CRITICAL 2026-05-31] _instance만 None으로 두면 안 된다.
    # ThresholdManager는 _instance와 _initialized를 '둘 다' 클래스 변수로 가진다.
    # _instance=None만 리셋하면 다음 ThresholdManager() 호출 시 __new__는 새 빈 객체를
    # 만들지만 __init__이 `if _initialized: return`으로 즉시 빠져나가 _thresholds/_observers가
    # 없는 빈 객체가 생성된다 → 이후 get_threshold() 등에서 AttributeError.
    # 이것이 풀스위트 순서의존 실패(단독 PASS, 풀스위트 FAIL)의 근본 원인이었다.
    # 따라서 _initialized도 함께 False로 리셋해 다음 생성이 실제 초기화를 수행하도록 한다.
    try:
        from src.core.threshold_manager import ThresholdManager
        if hasattr(ThresholdManager, '_instance'):
            saved_instances['ThresholdManager'] = ThresholdManager._instance
            ThresholdManager._instance = None
            ThresholdManager._initialized = False
    except ImportError:
        pass

    # DatabaseManager 리셋
    try:
        from src.core.db_manager import DatabaseManager
        if hasattr(DatabaseManager, '_instance'):
            saved_instances['DatabaseManager'] = DatabaseManager._instance
            DatabaseManager._instance = None
    except ImportError:
        pass

    # PerformanceStatsManager 리셋
    try:
        from src.core.performance_stats_manager import PerformanceStatsManager
        if hasattr(PerformanceStatsManager, '_instance'):
            saved_instances['PerformanceStatsManager'] = PerformanceStatsManager._instance
            PerformanceStatsManager._instance = None
    except ImportError:
        pass

    # ImprovedAutoImprovementManager 리셋
    # [CRITICAL 2026-05-31] 이 클래스의 진짜 싱글톤은 클래스 변수 _instance가 아니라
    # 모듈 전역 변수 _manager_instance다 (improved_auto_improvement_manager.py:567,
    # get_improved_manager()가 사용). 기존 코드는 존재하지 않는 ._instance를 리셋해 무효였다.
    # 모듈 전역 _manager_instance를 직접 None으로 리셋해야 실제 격리가 된다.
    try:
        import src.optimization.improved_auto_improvement_manager as _iaim
        if hasattr(_iaim, '_manager_instance'):
            saved_instances['ImprovedAutoImprovementManager'] = _iaim._manager_instance
            _iaim._manager_instance = None
    except ImportError:
        pass

    # ConfigManager 리셋
    try:
        from src.utils.config_manager import ConfigManager
        if hasattr(ConfigManager, '_instance'):
            saved_instances['ConfigManager'] = ConfigManager._instance
            ConfigManager._instance = None
    except ImportError:
        pass

    # SingletonMeta 기반 싱글톤 전체 리셋 (CRITICAL 2026-05-31)
    # OptimizedBacktestingFramework, AutomationCoordinator가 metaclass=SingletonMeta다.
    # 이들 인스턴스는 SingletonMeta._instances(클래스->인스턴스 dict)에 캐시되며,
    # __init__이 `if hasattr(self,'_initialized'): return`으로 가드되어 한 번 만들어지면
    # 이후 다른 db_manager로 호출해도 기존(오염된) 인스턴스를 그대로 반환한다.
    # 앞선 테스트가 Mock db_manager로 OptimizedBacktestingFramework를 생성하면 그 Mock이
    # 캐시에 남아, 이후 실제 db를 쓰는 테스트에서 run_backtest가 'Mock' object is not
    # iterable로 죽는다(test_backtesting_with_filtered_pool). _instances를 비워 매 테스트가
    # 깨끗한 인스턴스를 새로 만들도록 한다.
    try:
        from src.utils.singleton import SingletonMeta
        saved_instances['__SingletonMeta__'] = dict(SingletonMeta._instances)
        SingletonMeta._instances.clear()
    except ImportError:
        pass

    # [로그 격리] 이전 테스트나 모듈 import가 운영 로그 파일 핸들러를 새로 붙였을 수 있으므로
    # 매 테스트 시작 직전에도 한 번 더 청소한다(이중 안전망).
    _strip_production_log_handlers()

    yield  # 테스트 실행

    # 테스트 실행 후: 싱글톤 정리 (새로 생성된 인스턴스 정리)
    try:
        from src.core.threshold_manager import ThresholdManager
        if hasattr(ThresholdManager, '_instance') and ThresholdManager._instance is not None:
            try:
                # 리소스 정리가 필요한 경우
                if hasattr(ThresholdManager._instance, 'cleanup'):
                    ThresholdManager._instance.cleanup()
            except:
                pass
            ThresholdManager._instance = None
        # _instance 유무와 무관하게 _initialized를 반드시 False로 되돌린다.
        # (setup 주석 참고: 빈 객체 생성 방지. 다음 테스트의 setup에서 한 번 더 보장)
        ThresholdManager._initialized = False
    except ImportError:
        pass

    try:
        from src.core.db_manager import DatabaseManager
        if hasattr(DatabaseManager, '_instance') and DatabaseManager._instance is not None:
            try:
                if hasattr(DatabaseManager._instance, 'close'):
                    DatabaseManager._instance.close()
            except:
                pass
            DatabaseManager._instance = None
    except ImportError:
        pass

    try:
        from src.core.performance_stats_manager import PerformanceStatsManager
        if hasattr(PerformanceStatsManager, '_instance') and PerformanceStatsManager._instance is not None:
            try:
                if hasattr(PerformanceStatsManager._instance, 'close'):
                    PerformanceStatsManager._instance.close()
            except:
                pass
            PerformanceStatsManager._instance = None
    except ImportError:
        pass

    try:
        import src.optimization.improved_auto_improvement_manager as _iaim
        if getattr(_iaim, '_manager_instance', None) is not None:
            _iaim._manager_instance = None
    except ImportError:
        pass

    try:
        from src.utils.config_manager import ConfigManager
        if hasattr(ConfigManager, '_instance') and ConfigManager._instance is not None:
            ConfigManager._instance = None
    except ImportError:
        pass

    # SingletonMeta 기반 싱글톤 정리 (setup 주석 참고)
    try:
        from src.utils.singleton import SingletonMeta
        SingletonMeta._instances.clear()
    except ImportError:
        pass


# ====================================================================
# [운영 예측 DB 격리] 테스트가 운영 data/predictions/(predictions.db, week_*.json)를
# 오염시키지 않도록 차단
# --------------------------------------------------------------------
# 근거(2026-07-02 감사): test_dashboard.py의 rate-limit 테스트가 mock 없이 실제
# /api/generate-predictions 핸들러를 호출해 운영 predictions.db와 week_*.json에
# 실제 예측 5세트를 저장했다. 선행 테스트의 전역 random.seed(42)와 결합해
# '완전히 동일한 5세트'가 pytest 실행마다 누적(1230회 50세트 중 20세트,
# 1231회 30세트 중 25세트)되어, 사용자가 같은 조합을 중복 구매할 뻔한 실전
# 사고로 이어졌다. 기본 경로(db_path=None) 생성을 테스트 임시 폴더로 강제해
# 어떤 테스트도 운영 예측 저장소에 쓸 수 없게 한다.
# 명시적으로 db_path를 넘기는 테스트는 영향받지 않는다.
# ====================================================================
@pytest.fixture(scope="function", autouse=True)
def isolate_prediction_tracker(tmp_path, monkeypatch):
    """PredictionTracker 기본 저장 경로를 테스트 임시 폴더로 격리"""
    try:
        from src.core.prediction_tracker import PredictionTracker
    except ImportError:
        yield
        return

    original_init = PredictionTracker.__init__

    def _isolated_init(self, db_path=None):
        if db_path is None:
            db_path = tmp_path / "predictions_isolated" / "predictions.db"
        original_init(self, db_path=db_path)

    monkeypatch.setattr(PredictionTracker, "__init__", _isolated_init)
    yield


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
import importlib
import sys

import pytest


_ORDER_SENSITIVE_TEST_IMPORTS = {
    "ContinuousImprovementEngine": "src.core.continuous_improvement_engine",
    "FilteredPoolLSTMPredictor": "src.ml.filtered_pool_lstm_predictor",
    "MLFilterIntegrationManager": "src.core.ml_filter_integration_manager",
    "OptimizedBacktestingFramework": "src.backtesting.optimized_backtesting_framework",
}


def _clear_all_singleton_meta_instances():
    """Clear SingletonMeta caches even when a prior test left stale reloaded classes behind."""
    seen = set()

    for module in list(sys.modules.values()):
        module_dict = getattr(module, "__dict__", None)
        if not module_dict:
            continue

        for obj in list(module_dict.values()):
            candidates = []
            if isinstance(obj, type):
                candidates.append(type(obj))
                if getattr(obj, "__name__", None) == "SingletonMeta":
                    candidates.append(obj)

            for candidate in candidates:
                marker = id(candidate)
                if marker in seen:
                    continue
                seen.add(marker)

                if getattr(candidate, "__name__", None) != "SingletonMeta":
                    continue

                instances = getattr(candidate, "_instances", None)
                if isinstance(instances, dict):
                    instances.clear()


def _reset_order_sensitive_module_state():
    _clear_all_singleton_meta_instances()

    for module in list(sys.modules.values()):
        module_name = getattr(module, "__name__", "")
        if module_name.endswith("improved_auto_improvement_manager") and hasattr(module, "_manager_instance"):
            module._manager_instance = None

        module_dict = getattr(module, "__dict__", None)
        if not module_dict:
            continue

        for obj in list(module_dict.values()):
            if isinstance(obj, type) and getattr(obj, "__name__", None) == "ThresholdManager":
                if hasattr(obj, "_initialized"):
                    obj._initialized = False


def _refresh_order_sensitive_test_aliases(test_module):
    module_dict = getattr(test_module, "__dict__", None)
    if not module_dict:
        return

    for name, module_name in _ORDER_SENSITIVE_TEST_IMPORTS.items():
        if name not in module_dict:
            continue

        canonical_module = importlib.import_module(module_name)
        module_dict[name] = getattr(canonical_module, name)


@pytest.fixture(autouse=True)
def isolate_order_sensitive_singletons_and_import_aliases(request):
    _reset_order_sensitive_module_state()
    _refresh_order_sensitive_test_aliases(request.module)
    yield
    _reset_order_sensitive_module_state()
    _refresh_order_sensitive_test_aliases(request.module)
