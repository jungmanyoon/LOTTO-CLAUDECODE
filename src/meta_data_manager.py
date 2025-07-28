import json
import os
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.utils.constants import LottoConstants

class MetaDataManager:
    def __init__(self, meta_file='data/meta.json'):
        self.meta_file = meta_file
        self._ensure_meta_directory()
        self._initialize_meta_data()

    def _ensure_meta_directory(self):
        """메타데이터 디렉토리가 존재하는지 확인하고 없으면 생성"""
        meta_dir = os.path.dirname(self.meta_file)
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir)

    def _initialize_meta_data(self):
        """메타데이터 파일 초기화"""
        if not os.path.exists(self.meta_file):
            default_meta = {
                'last_update': None,
                'processing_status': {
                    'collection': False,
                    'validation': False,
                    'pattern_analysis': False,
                    'filtering': False
                },
                'database_info': {
                    'version': "1.0",               # 데이터베이스 버전
                    'storage_mode': "legacy",       # 저장 모드 (legacy/optimized)
                    'schema_updated_at': None,      # 스키마 업데이트 시간
                    'compatible_versions': ["1.0"]  # 호환 가능한 버전들
                },
                'filtering_info': {
                    'last_filtered_round': None,
                    'last_filter_mode': None,
                    'filter_criteria_version': 2,  # 버전 업데이트
                    'filter_version': "2.0",      # 새로운 필터 추가로 버전 업데이트
                    'active_filters': []          # 활성화된 필터 목록
                },
                'pattern_analysis': {
                    'version': "2.0",             # 패턴 분석 버전
                    'last_analyzed_round': None,
                    'enabled_patterns': []        # 활성화된 패턴 목록
                },
                # 새로운 필터 설정
                'filter_settings': {
                    'multiple': {
                        'enabled': True,
                        'bases': LottoConstants.MultipleDefaults.BASES,
                        'max_counts': LottoConstants.MultipleDefaults.MAX_COUNTS,
                        'min_counts': LottoConstants.MultipleDefaults.MIN_COUNTS
                    },
                    'alternating_odd_even': {
                        'enabled': True,
                        'exclude_perfect': LottoConstants.AlternatingDefaults.EXCLUDE_PERFECT,
                        'min_alternating': LottoConstants.AlternatingDefaults.MIN_ALTERNATING
                    },
                    'sum_multiple': {
                        'enabled': True,
                        'bases': LottoConstants.SumMultipleDefaults.BASES,
                        'exclude_multiples': LottoConstants.SumMultipleDefaults.EXCLUDE_MULTIPLES,
                        'frequency_threshold': LottoConstants.SumMultipleDefaults.FREQUENCY_THRESHOLD
                    }
                },
                # 패턴 분석 설정
                'pattern_settings': {
                    'multiple_analysis': {
                        'enabled': True,
                        'bases': LottoConstants.MultipleDefaults.BASES
                    },
                    'alternating_analysis': {
                        'enabled': True,
                        'patterns': LottoConstants.AlternatingDefaults.PATTERNS
                    },
                    'sum_multiple_analysis': {
                        'enabled': True,
                        'bases': LottoConstants.SumMultipleDefaults.BASES
                    }
                }
            }
            self._save_meta_data(default_meta)

    def update_filter_settings(self, filter_type: str, settings: Dict[str, Any]) -> bool:
        """필터 설정 업데이트
        
        Args:
            filter_type: 필터 유형
            settings: 새로운 설정값
        
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            meta_data = self._load_meta_data()
            if 'filter_settings' not in meta_data:
                meta_data['filter_settings'] = {}
            
            if filter_type not in meta_data['filter_settings']:
                meta_data['filter_settings'][filter_type] = {}
            
            # 설정 업데이트
            meta_data['filter_settings'][filter_type].update(settings)
            meta_data['filtering_info']['filter_version'] = "2.0"  # 버전 업데이트
            
            self._save_meta_data(meta_data)
            logging.info(f"{filter_type} 필터 설정이 업데이트되었습니다.")
            return True
            
        except Exception as e:
            logging.error(f"필터 설정 업데이트 중 오류 발생: {str(e)}")
            return False

    def get_filter_settings(self, filter_type: str) -> Optional[Dict[str, Any]]:
        """필터 설정 조회"""
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('filter_settings', {}).get(filter_type)
        except Exception as e:
            logging.error(f"필터 설정 조회 중 오류 발생: {str(e)}")
            return None

    def update_pattern_settings(self, pattern_type: str, settings: Dict[str, Any]) -> bool:
        """패턴 분석 설정 업데이트"""
        try:
            meta_data = self._load_meta_data()
            if 'pattern_settings' not in meta_data:
                meta_data['pattern_settings'] = {}
            
            if pattern_type not in meta_data['pattern_settings']:
                meta_data['pattern_settings'][pattern_type] = {}
            
            # 설정 업데이트
            meta_data['pattern_settings'][pattern_type].update(settings)
            meta_data['pattern_analysis']['version'] = "2.0"  # 버전 업데이트
            
            self._save_meta_data(meta_data)
            logging.info(f"{pattern_type} 패턴 설정이 업데이트되었습니다.")
            return True
            
        except Exception as e:
            logging.error(f"패턴 설정 업데이트 중 오류 발생: {str(e)}")
            return False

    def get_pattern_settings(self, pattern_type: str) -> Optional[Dict[str, Any]]:
        """패턴 분석 설정 조회"""
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('pattern_settings', {}).get(pattern_type)
        except Exception as e:
            logging.error(f"패턴 설정 조회 중 오류 발생: {str(e)}")
            return None

    def get_enabled_filters(self) -> list:
        """활성화된 필터 목록 조회"""
        try:
            meta_data = self._load_meta_data()
            filter_settings = meta_data.get('filter_settings', {})
            return [
                filter_type for filter_type, settings in filter_settings.items()
                if settings.get('enabled', True)
            ]
        except Exception as e:
            logging.error(f"활성화된 필터 목록 조회 중 오류 발생: {str(e)}")
            return []

    def get_enabled_patterns(self) -> list:
        """활성화된 패턴 분석 목록 조회"""
        try:
            meta_data = self._load_meta_data()
            pattern_settings = meta_data.get('pattern_settings', {})
            return [
                pattern_type for pattern_type, settings in pattern_settings.items()
                if settings.get('enabled', True)
            ]
        except Exception as e:
            logging.error(f"활성화된 패턴 목록 조회 중 오류 발생: {str(e)}")
            return []

    def update_filter_version(self, new_version: str):
        """필터 버전 업데이트"""
        try:
            meta_data = self._load_meta_data()
            meta_data['filtering_info']['filter_version'] = new_version
            meta_data['filtering_info']['last_update'] = datetime.now().isoformat()
            self._save_meta_data(meta_data)
            logging.info(f"필터 버전이 {new_version}(으)로 업데이트되었습니다.")
        except Exception as e:
            logging.error(f"필터 버전 업데이트 중 오류 발생: {str(e)}")

    def get_filter_version(self) -> str:
        """현재 필터 버전 조회"""
        try:
            meta_data = self._load_meta_data()
            return meta_data['filtering_info'].get('filter_version', "1.0")
        except Exception as e:
            logging.error(f"필터 버전 조회 중 오류 발생: {str(e)}")
            return "1.0"

    def _load_meta_data(self):
        """메타데이터 로드"""
        try:
            if os.path.exists(self.meta_file):
                with open(self.meta_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"메타데이터 로드 중 오류 발생: {str(e)}")
            return {}

    def _save_meta_data(self, data):
        """메타데이터 저장"""
        try:
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"메타데이터 저장 중 오류 발생: {str(e)}")
            raise

    def update_last_update(self):
        """마지막 업데이트 시간 갱신"""
        try:
            meta_data = self._load_meta_data()
            meta_data['last_update'] = datetime.now().isoformat()
            self._save_meta_data(meta_data)
        except Exception as e:
            logging.error(f"마지막 업데이트 시간 갱신 중 오류 발생: {str(e)}")

    def get_last_update(self):
        """마지막 업데이트 시간 조회"""
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('last_update')
        except Exception as e:
            logging.error(f"마지막 업데이트 시간 조회 중 오류 발생: {str(e)}")
            return None

    def update_processing_status(self, process_name, status):
        """처리 상태 업데이트"""
        try:
            meta_data = self._load_meta_data()
            if 'processing_status' not in meta_data:
                meta_data['processing_status'] = {}
            meta_data['processing_status'][process_name] = status
            self._save_meta_data(meta_data)
        except Exception as e:
            logging.error(f"처리 상태 업데이트 중 오류 발생: {str(e)}")

    def get_processing_status(self, process_name):
        """처리 상태 조회"""
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('processing_status', {}).get(process_name, False)
        except Exception as e:
            logging.error(f"처리 상태 조회 중 오류 발생: {str(e)}")
            return False

    def reset_processing_status(self):
        """모든 처리 상태 초기화"""
        try:
            meta_data = self._load_meta_data()
            meta_data['processing_status'] = {
                'collection': False,
                'validation': False
            }
            self._save_meta_data(meta_data)
        except Exception as e:
            logging.error(f"처리 상태 초기화 중 오류 발생: {str(e)}")

    def delete_meta(self, meta_key):
        """메타데이터 키 삭제
        
        Args:
            meta_key: 삭제할 메타데이터 키
        
        Returns:
            bool: 삭제 성공 여부
        """
        try:
            meta_data = self._load_meta_data()
            if meta_key in meta_data:
                del meta_data[meta_key]
                self._save_meta_data(meta_data)
                logging.info(f"메타데이터 '{meta_key}'가 삭제되었습니다.")
                return True
            else:
                logging.warning(f"메타데이터 '{meta_key}'가 존재하지 않습니다.")
                return False
        except Exception as e:
            logging.error(f"메타데이터 삭제 중 오류 발생: {str(e)}")
            return False

    def get_db_version(self) -> str:
        """데이터베이스 버전 조회
        
        Returns:
            str: 현재 데이터베이스 버전
        """
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('database_info', {}).get('version', "1.0")
        except Exception as e:
            logging.error(f"데이터베이스 버전 조회 중 오류 발생: {str(e)}")
            return "1.0"
            
    def get_db_storage_mode(self) -> str:
        """데이터베이스 저장 모드 조회
        
        Returns:
            str: 현재 저장 모드 (legacy/optimized)
        """
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('database_info', {}).get('storage_mode', "legacy")
        except Exception as e:
            logging.error(f"데이터베이스 저장 모드 조회 중 오류 발생: {str(e)}")
            return "legacy"
            
    def update_db_info(self, version: str = None, storage_mode: str = None) -> bool:
        """데이터베이스 정보 업데이트
        
        Args:
            version: 새 데이터베이스 버전 (기본값: None)
            storage_mode: 새 저장 모드 (legacy/optimized) (기본값: None)
            
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            meta_data = self._load_meta_data()
            
            # 데이터베이스 정보 섹션이 없으면 생성
            if 'database_info' not in meta_data:
                meta_data['database_info'] = {
                    'version': "1.0",
                    'storage_mode': "legacy",
                    'schema_updated_at': None,
                    'compatible_versions': ["1.0"]
                }
                
            # 버전 업데이트
            if version:
                meta_data['database_info']['version'] = version
                # 호환 가능 버전에 추가
                if 'compatible_versions' not in meta_data['database_info']:
                    meta_data['database_info']['compatible_versions'] = []
                if version not in meta_data['database_info']['compatible_versions']:
                    meta_data['database_info']['compatible_versions'].append(version)
                meta_data['database_info']['schema_updated_at'] = datetime.now().isoformat()
                
            # 저장 모드 업데이트
            if storage_mode:
                meta_data['database_info']['storage_mode'] = storage_mode
                
            self._save_meta_data(meta_data)
            logging.info(f"데이터베이스 정보가 업데이트되었습니다. 버전: {version}, 저장 모드: {storage_mode}")
            return True
            
        except Exception as e:
            logging.error(f"데이터베이스 정보 업데이트 중 오류 발생: {str(e)}")
            return False
            
    def is_db_version_compatible(self, required_version: str) -> bool:
        """현재 데이터베이스 버전이 요구되는 버전과 호환되는지 확인
        
        Args:
            required_version: 필요한 최소 버전
            
        Returns:
            bool: 호환 여부
        """
        try:
            meta_data = self._load_meta_data()
            compatible_versions = meta_data.get('database_info', {}).get('compatible_versions', ["1.0"])
            
            # 완전히 동일한 버전이거나 호환 가능 목록에 있는 경우
            return (
                required_version == meta_data.get('database_info', {}).get('version', "1.0") or
                required_version in compatible_versions
            )
        except Exception as e:
            logging.error(f"데이터베이스 버전 호환성 확인 중 오류 발생: {str(e)}")
            return False

    def get_last_filtered_round(self) -> Optional[int]:
        """마지막으로 필터링된 회차 조회
        
        Returns:
            Optional[int]: 마지막으로 필터링된 회차 번호 또는 None
        """
        try:
            meta_data = self._load_meta_data()
            return meta_data.get('filtering_info', {}).get('last_filtered_round')
        except Exception as e:
            logging.error(f"마지막 필터링 회차 조회 중 오류 발생: {str(e)}")
            return None

    def update_last_filtered_round(self, round_num: int) -> None:
        """마지막 필터링 회차 업데이트
        
        Args:
            round_num: 업데이트할 회차 번호
        """
        try:
            meta_data = self._load_meta_data()
            if 'filtering_info' not in meta_data:
                meta_data['filtering_info'] = {}
            meta_data['filtering_info']['last_filtered_round'] = round_num
            meta_data['filtering_info']['last_update'] = datetime.now().isoformat()
            self._save_meta_data(meta_data)
            logging.info(f"마지막 필터링 회차가 {round_num}(으)로 업데이트되었습니다.")
        except Exception as e:
            logging.error(f"마지막 필터링 회차 업데이트 중 오류 발생: {str(e)}")