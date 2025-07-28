import os
import yaml
import logging
from typing import Dict, Any, Optional

class ConfigManager:
    """설정 파일 관리 클래스"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """ConfigManager 초기화
        
        Args:
            config_path: 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드
        
        Returns:
            Dict[str, Any]: 설정 데이터
        """
        try:
            # config_path가 None인 경우 처리
            if self.config_path is None:
                logging.warning("설정 파일 경로가 지정되지 않았습니다. 기본 설정을 사용합니다.")
                return self._get_default_config()
                
            if not os.path.exists(self.config_path):
                logging.warning(f"설정 파일 '{self.config_path}'을 찾을 수 없습니다. 기본 설정을 사용합니다.")
                return self._get_default_config()
                
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            if not config:
                logging.warning("설정 파일이 비어 있습니다. 기본 설정을 사용합니다.")
                return self._get_default_config()
                
            return config
            
        except Exception as e:
            logging.error(f"설정 파일 로드 중 오류 발생: {str(e)}")
            return self._get_default_config()
    
    def save_config(self) -> bool:
        """현재 설정을 파일에 저장
        
        Returns:
            bool: 저장 성공 여부
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            logging.error(f"설정 파일 저장 중 오류 발생: {str(e)}")
            return False
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환
        
        Returns:
            Dict[str, Any]: 기본 설정
        """
        return {
            "database": {
                "storage_mode": "legacy",
                "batch_size": 10000,
                "max_batch_memory": 1000000
            },
            "filtering": {
                "use_parallel": True,
                "max_workers": 4
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "file": "logs/lotto_app.log",
                "max_size": 10485760,
                "backup_count": 5
            },
            "filters": {
                "enabled_filters": [
                    "match", "odd_even", "consecutive", "sum_range", 
                    "fixed_step", "last_digit", "max_gap", "section",
                    "average", "multiple", "ten_section", 
                    "arithmetic_sequence", "geometric_sequence"
                ],
                "filter_efficiency": {
                    "sum_range": 0.45,
                    "consecutive": 0.30,
                    "max_gap": 0.25,
                    "section": 0.22,
                    "geometric_sequence": 0.20,
                    "arithmetic_sequence": 0.18,
                    "odd_even": 0.15,
                    "fixed_step": 0.15,
                    "ten_section": 0.12,
                    "last_digit": 0.10,
                    "average": 0.10,
                    "multiple": 0.08,
                    "match": 0.05
                }
            }
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        """데이터베이스 설정 가져오기
        
        Returns:
            Dict[str, Any]: 데이터베이스 설정
        """
        return self.config.get("database", {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """로깅 설정 가져오기
        
        Returns:
            Dict[str, Any]: 로깅 설정
        """
        return self.config.get("logging", {})
    
    def get_filtering_config(self) -> Dict[str, Any]:
        """필터링 설정 가져오기
        
        Returns:
            Dict[str, Any]: 필터링 설정
        """
        return self.config.get("filtering", {})
    
    def get_enabled_filters(self) -> list:
        """활성화된 필터 목록 가져오기
        
        Returns:
            list: 활성화된 필터 이름 목록
        """
        return self.config.get("filters", {}).get("enabled_filters", [])
    
    def get_filter_efficiency(self) -> Dict[str, float]:
        """필터 효율성 정보 가져오기
        
        Returns:
            Dict[str, float]: 필터 이름과 효율성 값 매핑
        """
        return self.config.get("filters", {}).get("filter_efficiency", {})
    
    def get_filter_criteria(self, filter_name: str) -> Optional[Dict[str, Any]]:
        """특정 필터의 기준 값 가져오기
        
        Args:
            filter_name: 필터 이름
            
        Returns:
            Optional[Dict[str, Any]]: 필터 기준 값 또는 None
        """
        criteria = self.config.get("filters", {}).get("criteria", {})
        return criteria.get(filter_name)
    
    def update_filter_criteria(self, filter_name: str, criteria: Dict[str, Any]) -> bool:
        """필터 기준 값 업데이트
        
        Args:
            filter_name: 필터 이름
            criteria: 새 기준 값
            
        Returns:
            bool: 성공 여부
        """
        try:
            if "filters" not in self.config:
                self.config["filters"] = {}
            if "criteria" not in self.config["filters"]:
                self.config["filters"]["criteria"] = {}
                
            self.config["filters"]["criteria"][filter_name] = criteria
            return self.save_config()
        except Exception as e:
            logging.error(f"필터 기준 업데이트 중 오류 발생: {str(e)}")
            return False 