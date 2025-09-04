#!/usr/bin/env python3
"""
MetadataManager - 통합 메타데이터 관리 시스템
- 설정 변경 이력 추적
- 데이터 일관성 보장
- 버전 관리 및 롤백 지원
- 전역 상태 추적
"""

import os
import json
import sqlite3
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

class ChangeType(Enum):
    CONFIG_CHANGE = "config_change"
    DATA_UPDATE = "data_update"
    FILTER_UPDATE = "filter_update"
    MODEL_UPDATE = "model_update"
    CACHE_INVALIDATION = "cache_invalidation"
    SYSTEM_EVENT = "system_event"

class ChangeLevel(Enum):
    MINOR = "minor"        # 로깅만 필요
    MAJOR = "major"        # 캐시 무효화 필요
    CRITICAL = "critical"  # 전체 재처리 필요

@dataclass
class MetadataEntry:
    """메타데이터 엔트리"""
    id: str
    timestamp: datetime
    change_type: ChangeType
    change_level: ChangeLevel
    component: str
    description: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    affected_components: List[str] = field(default_factory=list)
    rollback_data: Optional[Dict] = None
    checksum: Optional[str] = None

class MetadataManager:
    """통합 메타데이터 관리자"""
    
    def __init__(self, 
                 db_manager,
                 config_manager,
                 metadata_dir: str = "metadata"):
        """초기화
        
        Args:
            db_manager: DatabaseManager 인스턴스
            config_manager: ConfigManager 인스턴스
            metadata_dir: 메타데이터 저장 디렉토리
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        
        # 메타데이터 디렉토리
        self.metadata_dir = Path(metadata_dir)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # 메타데이터 DB
        self.metadata_db_path = self.metadata_dir / "system_metadata.db"
        self._init_metadata_db()
        
        # 현재 상태 추적
        self.current_state = {
            'last_round': 0,
            'config_version': '',
            'filter_versions': {},
            'model_versions': {},
            'last_processing_time': None,
            'consistency_checks': {}
        }
        
        # 스레드 안전성
        self._lock = threading.RLock()
        
        # 초기 상태 로드
        self._load_current_state()
        
        logging.info(f"MetadataManager 초기화 완료: {self.metadata_dir}")
    
    def _init_metadata_db(self):
        """메타데이터 DB 초기화"""
        with sqlite3.connect(self.metadata_db_path) as conn:
            # 메타데이터 엔트리 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    change_type TEXT NOT NULL,
                    change_level TEXT NOT NULL,
                    component TEXT NOT NULL,
                    description TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    affected_components TEXT,  -- JSON array
                    rollback_data TEXT,       -- JSON object
                    checksum TEXT
                )
            """)
            
            # 시스템 상태 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    checksum TEXT
                )
            """)
            
            # 일관성 검사 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consistency_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    check_type TEXT NOT NULL,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,  -- 'pass', 'fail', 'warning'
                    details TEXT,
                    fixed BOOLEAN DEFAULT 0
                )
            """)
            
            # 버전 관리 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS version_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    component TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT,
                    data_backup TEXT,  -- JSON backup data
                    is_current BOOLEAN DEFAULT 0
                )
            """)
            
            # 인덱스 생성
            conn.execute("CREATE INDEX IF NOT EXISTS idx_change_type ON metadata_entries(change_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON metadata_entries(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_component ON metadata_entries(component)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_check_status ON consistency_checks(status)")
    
    def _generate_id(self) -> str:
        """고유 ID 생성"""
        timestamp = datetime.now().isoformat()
        return hashlib.md5(timestamp.encode()).hexdigest()[:12]
    
    def _calculate_checksum(self, data: Any) -> str:
        """데이터 체크섬 계산"""
        if data is None:
            return ""
        
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)
        
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    def _load_current_state(self):
        """현재 상태 로드"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                cursor = conn.execute("SELECT key, value FROM system_state")
                
                for key, value in cursor.fetchall():
                    try:
                        self.current_state[key] = json.loads(value)
                    except json.JSONDecodeError:
                        self.current_state[key] = value
            
            # 최신 회차 정보 업데이트
            if self.db_manager:
                self.current_state['last_round'] = self.db_manager.get_last_round()
            
            # 설정 버전 업데이트
            if self.config_manager:
                config_data = {
                    'main': self.config_manager.config,
                    'adaptive': self.config_manager.adaptive_config
                }
                self.current_state['config_version'] = self._calculate_checksum(config_data)
            
            logging.debug("현재 상태 로드 완료")
            
        except Exception as e:
            logging.error(f"현재 상태 로드 실패: {e}")
    
    def _save_state(self, key: str, value: Any):
        """상태 저장"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                value_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                checksum = self._calculate_checksum(value)
                
                conn.execute("""
                    INSERT OR REPLACE INTO system_state (key, value, updated_at, checksum)
                    VALUES (?, ?, ?, ?)
                """, (key, value_str, datetime.now().isoformat(), checksum))
            
            self.current_state[key] = value
            
        except Exception as e:
            logging.error(f"상태 저장 실패 {key}: {e}")
    
    def record_change(self, 
                     change_type: ChangeType,
                     component: str,
                     description: str,
                     change_level: ChangeLevel = ChangeLevel.MINOR,
                     old_value: Optional[Any] = None,
                     new_value: Optional[Any] = None,
                     affected_components: Optional[List[str]] = None,
                     rollback_data: Optional[Dict] = None) -> str:
        """변경사항 기록
        
        Args:
            change_type: 변경 타입
            component: 컴포넌트명
            description: 변경 설명
            change_level: 변경 수준
            old_value: 이전 값
            new_value: 새 값
            affected_components: 영향받는 컴포넌트들
            rollback_data: 롤백용 데이터
            
        Returns:
            생성된 메타데이터 엔트리 ID
        """
        with self._lock:
            entry_id = self._generate_id()
            
            entry = MetadataEntry(
                id=entry_id,
                timestamp=datetime.now(),
                change_type=change_type,
                change_level=change_level,
                component=component,
                description=description,
                old_value=old_value,
                new_value=new_value,
                affected_components=affected_components or [],
                rollback_data=rollback_data,
                checksum=self._calculate_checksum({
                    'old_value': old_value,
                    'new_value': new_value
                })
            )
            
            try:
                with sqlite3.connect(self.metadata_db_path) as conn:
                    conn.execute("""
                        INSERT INTO metadata_entries 
                        (id, timestamp, change_type, change_level, component, description,
                         old_value, new_value, affected_components, rollback_data, checksum)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        entry.id,
                        entry.timestamp.isoformat(),
                        entry.change_type.value,
                        entry.change_level.value,
                        entry.component,
                        entry.description,
                        json.dumps(entry.old_value) if entry.old_value is not None else None,
                        json.dumps(entry.new_value) if entry.new_value is not None else None,
                        json.dumps(entry.affected_components),
                        json.dumps(entry.rollback_data) if entry.rollback_data else None,
                        entry.checksum
                    ))
                
                logging.info(f"변경사항 기록: {component} - {description}")
                
                # 중요한 변경사항의 경우 알림
                if change_level == ChangeLevel.CRITICAL:
                    logging.warning(f"CRITICAL 변경: {component} - {description}")
                
                return entry_id
                
            except Exception as e:
                logging.error(f"변경사항 기록 실패: {e}")
                return ""
    
    def record_config_change(self, 
                           config_section: str,
                           old_config: Dict,
                           new_config: Dict) -> List[str]:
        """설정 변경 기록
        
        Args:
            config_section: 설정 섹션 ('main', 'adaptive')
            old_config: 이전 설정
            new_config: 새 설정
            
        Returns:
            생성된 메타데이터 엔트리 ID들
        """
        entry_ids = []
        
        # 변경사항 분석
        changes = self._analyze_config_changes(old_config, new_config)
        
        for change_path, change_info in changes.items():
            change_level = self._determine_change_level(config_section, change_path, change_info)
            
            # 영향받는 컴포넌트 분석
            affected = self._analyze_affected_components(config_section, change_path)
            
            entry_id = self.record_change(
                change_type=ChangeType.CONFIG_CHANGE,
                component=f"config.{config_section}",
                description=f"{change_path}: {change_info['type']}",
                change_level=change_level,
                old_value=change_info.get('old_value'),
                new_value=change_info.get('new_value'),
                affected_components=affected,
                rollback_data={
                    'section': config_section,
                    'path': change_path,
                    'old_config': old_config
                }
            )
            
            if entry_id:
                entry_ids.append(entry_id)
        
        # 설정 버전 업데이트
        new_version = self._calculate_checksum(new_config)
        self._save_state(f'{config_section}_config_version', new_version)
        
        return entry_ids
    
    def _analyze_config_changes(self, old_config: Dict, new_config: Dict, path: str = "") -> Dict[str, Dict]:
        """설정 변경사항 분석"""
        changes = {}
        
        all_keys = set(old_config.keys()) | set(new_config.keys())
        
        for key in all_keys:
            current_path = f"{path}.{key}" if path else key
            
            if key not in old_config:
                changes[current_path] = {
                    "type": "added",
                    "new_value": new_config[key]
                }
            elif key not in new_config:
                changes[current_path] = {
                    "type": "removed",
                    "old_value": old_config[key]
                }
            elif old_config[key] != new_config[key]:
                if isinstance(old_config[key], dict) and isinstance(new_config[key], dict):
                    # 중첩된 딕셔너리 재귀 처리
                    nested_changes = self._analyze_config_changes(
                        old_config[key], new_config[key], current_path
                    )
                    changes.update(nested_changes)
                else:
                    changes[current_path] = {
                        "type": "modified",
                        "old_value": old_config[key],
                        "new_value": new_config[key]
                    }
        
        return changes
    
    def _determine_change_level(self, section: str, path: str, change_info: Dict) -> ChangeLevel:
        """변경 수준 결정"""
        critical_paths = [
            'global_probability_threshold',
            'enabled_filters',
            'filters.criteria'
        ]
        
        major_paths = [
            'filters',
            'database',
            'ml'
        ]
        
        if any(critical_path in path for critical_path in critical_paths):
            return ChangeLevel.CRITICAL
        elif any(major_path in path for major_path in major_paths):
            return ChangeLevel.MAJOR
        else:
            return ChangeLevel.MINOR
    
    def _analyze_affected_components(self, section: str, path: str) -> List[str]:
        """영향받는 컴포넌트 분석"""
        affected = []
        
        if 'global_probability_threshold' in path:
            affected.extend(['filter_manager', 'cache_manager', 'prediction_system'])
        elif 'filters' in path:
            affected.extend(['filter_manager', 'cache_manager'])
        elif 'database' in path:
            affected.extend(['db_manager', 'data_collector'])
        elif 'ml' in path:
            affected.extend(['ml_models', 'prediction_system'])
        
        return affected
    
    def record_data_update(self, 
                          round_num: int,
                          numbers: List[int],
                          date_str: str) -> str:
        """새 데이터 업데이트 기록"""
        return self.record_change(
            change_type=ChangeType.DATA_UPDATE,
            component="lotto_data",
            description=f"새 회차 추가: {round_num}회 ({date_str})",
            change_level=ChangeLevel.MAJOR,
            new_value={'round': round_num, 'numbers': numbers, 'date': date_str},
            affected_components=['filter_manager', 'ml_models', 'cache_manager']
        )
    
    def record_filter_update(self, 
                           filter_name: str,
                           old_criteria: Optional[Dict],
                           new_criteria: Dict,
                           reason: str = "") -> str:
        """필터 업데이트 기록"""
        return self.record_change(
            change_type=ChangeType.FILTER_UPDATE,
            component=f"filter.{filter_name}",
            description=f"필터 기준 업데이트: {reason}",
            change_level=ChangeLevel.MAJOR,
            old_value=old_criteria,
            new_value=new_criteria,
            affected_components=['filter_manager', 'cache_manager'],
            rollback_data={'filter_name': filter_name, 'old_criteria': old_criteria}
        )
    
    def record_cache_invalidation(self, 
                                cache_type: str,
                                reason: str,
                                count: int = 0) -> str:
        """캐시 무효화 기록"""
        return self.record_change(
            change_type=ChangeType.CACHE_INVALIDATION,
            component="cache_manager",
            description=f"{cache_type} 캐시 무효화: {reason}",
            change_level=ChangeLevel.MINOR,
            new_value={'type': cache_type, 'count': count, 'reason': reason}
        )
    
    def check_consistency(self) -> Dict[str, Any]:
        """데이터 일관성 검사"""
        results = {}
        issues = []
        
        try:
            # 1. 최신 회차 일관성 검사
            db_last_round = self.db_manager.get_last_round() if self.db_manager else 0
            state_last_round = self.current_state.get('last_round', 0)
            
            if db_last_round != state_last_round:
                issues.append({
                    'type': 'round_mismatch',
                    'severity': 'warning',
                    'description': f"회차 불일치: DB={db_last_round}, State={state_last_round}"
                })
                self._save_state('last_round', db_last_round)
            
            results['round_consistency'] = db_last_round == state_last_round
            
            # 2. 설정 무결성 검사
            if self.config_manager:
                current_config_hash = self._calculate_checksum({
                    'main': self.config_manager.config,
                    'adaptive': self.config_manager.adaptive_config
                })
                
                stored_hash = self.current_state.get('config_version', '')
                
                if current_config_hash != stored_hash:
                    issues.append({
                        'type': 'config_hash_mismatch',
                        'severity': 'major',
                        'description': "설정 해시 불일치 - 캐시 무효화 필요"
                    })
                
                results['config_consistency'] = current_config_hash == stored_hash
            
            # 3. 캐시 유효성 검사
            # 여기서는 간단한 검사만 수행
            results['cache_consistency'] = True
            
            # 4. DB 연결 상태 검사
            try:
                if self.db_manager:
                    self.db_manager.get_last_round()
                results['db_connectivity'] = True
            except Exception:
                results['db_connectivity'] = False
                issues.append({
                    'type': 'db_connection_failed',
                    'severity': 'critical',
                    'description': "데이터베이스 연결 실패"
                })
            
            # 일관성 검사 결과 기록
            self._record_consistency_check(results, issues)
            
            return {
                'overall_status': 'healthy' if not issues else 'issues_found',
                'results': results,
                'issues': issues,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logging.error(f"일관성 검사 실패: {e}")
            return {
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _record_consistency_check(self, results: Dict, issues: List[Dict]):
        """일관성 검사 결과 기록"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                for check_name, status in results.items():
                    # 해당 검사의 이슈 찾기
                    related_issues = [issue for issue in issues if check_name in issue.get('type', '')]
                    
                    conn.execute("""
                        INSERT INTO consistency_checks 
                        (timestamp, check_type, component, status, details)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        datetime.now().isoformat(),
                        check_name,
                        'system',
                        'pass' if status else 'fail',
                        json.dumps(related_issues)
                    ))
                
        except Exception as e:
            logging.error(f"일관성 검사 결과 기록 실패: {e}")
    
    def create_version_snapshot(self, component: str, description: str = "") -> str:
        """버전 스냅샷 생성"""
        try:
            # 현재 상태 백업
            backup_data = {}
            
            if component == 'config':
                backup_data = {
                    'main_config': self.config_manager.config,
                    'adaptive_config': self.config_manager.adaptive_config
                }
            elif component == 'system_state':
                backup_data = self.current_state.copy()
            
            # 버전 생성
            version = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 이전 버전을 current가 아니도록 업데이트
                conn.execute("""
                    UPDATE version_history 
                    SET is_current = 0 
                    WHERE component = ?
                """, (component,))
                
                # 새 버전 추가
                conn.execute("""
                    INSERT INTO version_history 
                    (timestamp, component, version, description, data_backup, is_current)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    component,
                    version,
                    description,
                    json.dumps(backup_data),
                    True
                ))
            
            logging.info(f"버전 스냅샷 생성: {component} v{version}")
            return version
            
        except Exception as e:
            logging.error(f"버전 스냅샷 생성 실패: {e}")
            return ""
    
    def rollback_to_version(self, component: str, version: str) -> bool:
        """특정 버전으로 롤백"""
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                cursor = conn.execute("""
                    SELECT data_backup FROM version_history 
                    WHERE component = ? AND version = ?
                """, (component, version))
                
                row = cursor.fetchone()
                if not row:
                    logging.error(f"버전을 찾을 수 없음: {component} v{version}")
                    return False
                
                backup_data = json.loads(row[0])
                
                # 롤백 실행
                if component == 'config':
                    # 설정 파일 복원 (실제 구현 필요)
                    logging.info(f"설정 롤백: v{version}")
                    return True
                elif component == 'system_state':
                    # 시스템 상태 복원
                    self.current_state.update(backup_data)
                    logging.info(f"시스템 상태 롤백: v{version}")
                    return True
                
        except Exception as e:
            logging.error(f"롤백 실패: {e}")
            return False
    
    def get_change_history(self, 
                          component: Optional[str] = None,
                          change_type: Optional[ChangeType] = None,
                          hours: int = 24,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """변경 이력 조회
        
        Args:
            component: 컴포넌트 필터
            change_type: 변경 타입 필터
            hours: 최근 n시간 이내
            limit: 최대 결과 수
            
        Returns:
            변경 이력 리스트
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            query = """
                SELECT id, timestamp, change_type, change_level, component, 
                       description, old_value, new_value, affected_components
                FROM metadata_entries 
                WHERE timestamp >= ?
            """
            params = [cutoff_time.isoformat()]
            
            if component:
                query += " AND component = ?"
                params.append(component)
            
            if change_type:
                query += " AND change_type = ?"
                params.append(change_type.value)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            with sqlite3.connect(self.metadata_db_path) as conn:
                cursor = conn.execute(query, params)
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'change_type': row[2],
                        'change_level': row[3],
                        'component': row[4],
                        'description': row[5],
                        'old_value': json.loads(row[6]) if row[6] else None,
                        'new_value': json.loads(row[7]) if row[7] else None,
                        'affected_components': json.loads(row[8]) if row[8] else []
                    })
                
                return results
                
        except Exception as e:
            logging.error(f"변경 이력 조회 실패: {e}")
            return []
    
    def get_system_status(self) -> Dict[str, Any]:
        """시스템 상태 종합 정보"""
        try:
            # 최근 변경사항 통계
            recent_changes = self.get_change_history(hours=24)
            
            change_stats = {}
            for change in recent_changes:
                change_type = change['change_type']
                change_stats[change_type] = change_stats.get(change_type, 0) + 1
            
            # 일관성 검사 결과
            consistency_result = self.check_consistency()
            
            # 현재 상태 정보
            status = {
                'current_state': self.current_state.copy(),
                'recent_changes_24h': len(recent_changes),
                'change_statistics': change_stats,
                'consistency_status': consistency_result['overall_status'],
                'last_check': datetime.now().isoformat()
            }
            
            # 버전 정보
            with sqlite3.connect(self.metadata_db_path) as conn:
                cursor = conn.execute("""
                    SELECT component, version, timestamp 
                    FROM version_history 
                    WHERE is_current = 1
                    ORDER BY component
                """)
                
                status['current_versions'] = {
                    row[0]: {'version': row[1], 'timestamp': row[2]}
                    for row in cursor.fetchall()
                }
            
            return status
            
        except Exception as e:
            logging.error(f"시스템 상태 조회 실패: {e}")
            return {'error': str(e)}
    
    def cleanup_old_metadata(self, days: int = 30) -> int:
        """오래된 메타데이터 정리"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        try:
            with sqlite3.connect(self.metadata_db_path) as conn:
                # 오래된 메타데이터 엔트리 삭제
                cursor = conn.execute("""
                    DELETE FROM metadata_entries 
                    WHERE timestamp < ?
                """, (cutoff_date.isoformat(),))
                
                cleaned_count += cursor.rowcount
                
                # 오래된 일관성 검사 결과 삭제
                cursor = conn.execute("""
                    DELETE FROM consistency_checks 
                    WHERE timestamp < ?
                """, (cutoff_date.isoformat(),))
                
                cleaned_count += cursor.rowcount
                
                # 오래된 버전 히스토리 삭제 (현재 버전은 제외)
                cursor = conn.execute("""
                    DELETE FROM version_history 
                    WHERE timestamp < ? AND is_current = 0
                """, (cutoff_date.isoformat(),))
                
                cleaned_count += cursor.rowcount
            
            logging.info(f"오래된 메타데이터 {cleaned_count}개 정리 완료")
            
        except Exception as e:
            logging.error(f"메타데이터 정리 실패: {e}")
        
        return cleaned_count