import os
import yaml
import logging
from typing import Dict, Any, Optional

class ConfigManager:
    """설정 파일 관리 클래스"""
    
    def __init__(self, config_path: str = "config.yaml", adaptive_config_path: str = "configs/adaptive_filter_config.yaml"):
        """ConfigManager 초기화
        
        Args:
            config_path: 설정 파일 경로
            adaptive_config_path: 적응형 필터 설정 파일 경로
        """
        self.config_path = config_path
        self.adaptive_config_path = adaptive_config_path
        self.config = self._load_config()
        self.adaptive_config = self._load_adaptive_config()
        
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
    
    def _load_adaptive_config(self) -> Dict[str, Any]:
        """적응형 필터 설정 파일 로드
        
        Returns:
            Dict[str, Any]: 적응형 필터 설정 데이터
        """
        try:
            if not os.path.exists(self.adaptive_config_path):
                logging.warning(f"적응형 필터 설정 파일 '{self.adaptive_config_path}'을 찾을 수 없습니다.")
                return {}
                
            with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                adaptive_config = yaml.safe_load(f)
                
            if not adaptive_config:
                logging.warning("적응형 필터 설정 파일이 비어 있습니다.")
                return {}

            threshold_value = adaptive_config.get('global_probability_threshold', 1.0)
            # FIX: Proper formatting to show actual value (e.g., 1.4% not 1.0%)
            logging.info(f"적응형 필터 설정 로드 완료 - YAML 저장값: {threshold_value:.2f}% (Optuna 최적화 값, ThresholdManager가 관리)")
            return adaptive_config
            
        except Exception as e:
            logging.error(f"적응형 필터 설정 파일 로드 중 오류 발생: {str(e)}")
            return {}
    
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
        """특정 필터의 기준 값 가져오기 (적응형 설정 우선)
        
        Args:
            filter_name: 필터 이름
            
        Returns:
            Optional[Dict[str, Any]]: 필터 기준 값 또는 None
        """
        # 먼저 적응형 설정에서 기준값 가져오기
        if self.adaptive_config:
            # 전역 확률 임계값 가져오기
            global_threshold = self.adaptive_config.get('global_probability_threshold', 1.0)
            
            # 동적 기준값 가져오기
            dynamic_criteria = self.adaptive_config.get('dynamic_criteria', {})
            
            # 필터별 매핑
            filter_mapping = {
                'odd_even': dynamic_criteria.get('odd_even'),
                'consecutive': dynamic_criteria.get('consecutive'),
                'sum_range': dynamic_criteria.get('sum_range'),
                'multiple': dynamic_criteria.get('multiple'),
                'ten_section': dynamic_criteria.get('ten_section'),
                'max_gap': dynamic_criteria.get('max_gap'),
                'last_digit': dynamic_criteria.get('last_digit'),
                'average': dynamic_criteria.get('average'),
                'arithmetic_sequence': dynamic_criteria.get('arithmetic'),
                'geometric_sequence': dynamic_criteria.get('geometric'),
                'match': dynamic_criteria.get('match')  # ✅ CRITICAL FIX: match 필터 매핑 추가!
            }
            
            adaptive_criteria = filter_mapping.get(filter_name)
            if adaptive_criteria:
                # 전역 임계값 정보도 포함
                adaptive_criteria['global_threshold'] = global_threshold
                logging.debug(f"{filter_name} 필터: 적응형 설정 사용 (임계값: {global_threshold}%)")
                
                # multiple 필터의 경우 특별 처리
                if filter_name == "multiple" and isinstance(adaptive_criteria, dict):
                    converted_criteria = {
                        'multiples': {},  # multiples 키 추가
                        'global_threshold': global_threshold
                    }
                    for key, value in adaptive_criteria.items():
                        if key != 'global_threshold':
                            try:
                                converted_criteria['multiples'][int(key)] = value
                            except (ValueError, TypeError):
                                pass
                    return converted_criteria
                
                # ten_section 필터의 경우 특별 처리
                if filter_name == "ten_section" and isinstance(adaptive_criteria, dict):
                    section_limits = {}
                    for key, value in adaptive_criteria.items():
                        if key.startswith('section'):
                            section_limits[key] = value
                    return {
                        'section_limits': section_limits,
                        'global_threshold': global_threshold
                    }
                    
                return adaptive_criteria
        
        # 적응형 설정이 없으면 기존 설정 사용
        criteria = self.config.get("filters", {}).get("criteria", {})
        filter_criteria = criteria.get(filter_name)
        
        # multiple 필터의 경우 문자열 키를 정수로 변환
        if filter_name == "multiple" and filter_criteria and "multiples" in filter_criteria:
            converted_multiples = {}
            for key, value in filter_criteria["multiples"].items():
                try:
                    converted_multiples[int(key)] = value
                except ValueError:
                    logging.error(f"multiple 필터의 키 '{key}'를 정수로 변환할 수 없습니다.")
                    continue
            filter_criteria["multiples"] = converted_multiples
            
        return filter_criteria
    
    def get_global_probability_threshold(self) -> float:
        """전역 확률 임계값 가져오기
        
        Returns:
            float: 전역 확률 임계값 (%)
        """
        if self.adaptive_config:
            threshold = self.adaptive_config.get('global_probability_threshold', 1.0)
            return threshold
        return 1.0  # 기본값 1%
    
    def get_adaptive_filter_status(self, filter_name: str) -> bool:
        """특정 필터의 활성화 상태 확인
        
        Args:
            filter_name: 필터 이름
            
        Returns:
            bool: 필터 활성화 여부
        """
        if self.adaptive_config:
            filters = self.adaptive_config.get('filters', {})
            # 필터 이름 매핑 (config 파일의 이름과 실제 필터 이름이 다른 경우)
            name_mapping = {
                'arithmetic_sequence': 'arithmetic',
                'geometric_sequence': 'geometric'
            }
            config_name = name_mapping.get(filter_name, filter_name)
            return filters.get(config_name, True)  # 기본값 True
        return True
    
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