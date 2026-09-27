"""
Automation Package - 24시간 자동 실행 시스템

이 패키지는 로또 예측 시스템의 24시간 자동 실행을 위한
모든 자동화 컴포넌트들을 포함합니다.

주요 컴포넌트:
- ConfigWatcher: 설정 파일 변경 감지 및 자동 대응
- AutoScheduler: 스케줄 기반 자동 실행 시스템
- EnhancedCacheManager: 지능형 캐시 관리 시스템
- MetadataManager: 메타데이터 및 변경 이력 관리
- AutomationCoordinator: 모든 컴포넌트 통합 관리자

[2026-09-27] 구성요소를 '필요할 때' 불러온다(PEP 562 모듈 __getattr__).
예전에는 패키지를 불러오기만 해도 auto_scheduler 등이 즉시 import 되어 'schedule' 같은 패키지가
필수였다. 그래서 가벼운 의존성만 설치하는 매시 발행 작업이 src.automation.draw_clock(표준 라이브러리만
쓰는 추첨 시각 계산)을 불러오다 ModuleNotFoundError 로 멈췄다. `from src.automation import X` 사용법은 같다.
"""

from importlib import import_module

__version__ = "1.0.0"
__author__ = "Claude Code Assistant"

_LAZY = {
    'ConfigWatcher': ('.config_watcher', 'ConfigWatcher'),
    'AutoScheduler': ('.auto_scheduler', 'AutoScheduler'),
    'EnhancedCacheManager': ('.enhanced_cache_manager', 'EnhancedCacheManager'),
    'CacheType': ('.enhanced_cache_manager', 'CacheType'),
    'MetadataManager': ('.metadata_manager', 'MetadataManager'),
    'ChangeType': ('.metadata_manager', 'ChangeType'),
    'ChangeLevel': ('.metadata_manager', 'ChangeLevel'),
    'AutomationCoordinator': ('.automation_coordinator', 'AutomationCoordinator'),
}

__all__ = [
    # Core classes
    'ConfigWatcher',
    'AutoScheduler',
    'EnhancedCacheManager',
    'MetadataManager',
    'AutomationCoordinator',

    # Data classes and enums
    'CacheType',
    'ChangeType',
    'ChangeLevel'
]


def __getattr__(name):
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        value = getattr(import_module(module_name, __name__), attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
