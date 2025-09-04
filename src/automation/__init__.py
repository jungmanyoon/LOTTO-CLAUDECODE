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
"""

from .config_watcher import ConfigWatcher
from .auto_scheduler import AutoScheduler
from .enhanced_cache_manager import EnhancedCacheManager, CacheType
from .metadata_manager import MetadataManager, ChangeType, ChangeLevel
from .automation_coordinator import AutomationCoordinator

__version__ = "1.0.0"
__author__ = "Claude Code Assistant"

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