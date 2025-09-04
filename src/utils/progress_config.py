"""
Progress bar configuration module
진행률 표시 설정을 중앙에서 관리
"""

import os
import logging
from typing import Optional

class ProgressConfig:
    """진행률 표시 설정 관리 클래스"""
    
    # 전역 설정 (config.yaml에서 덮어쓸 수 있음)
    DISABLE_PROGRESS_BARS = False  # True로 설정하면 모든 진행률 표시 비활성화
    SIMPLE_MODE = True  # True로 설정하면 간단한 로그 메시지만 표시
    SILENT_FILTERS = True  # True로 설정하면 필터 진행률 로그 최소화
    
    @classmethod
    def load_from_config(cls, config_dict: dict) -> None:
        """config.yaml에서 설정 로드"""
        if 'progress_display' in config_dict:
            progress_config = config_dict['progress_display']
            cls.DISABLE_PROGRESS_BARS = progress_config.get('disable_all', False)
            cls.SIMPLE_MODE = progress_config.get('simple_mode', True)
    
    @classmethod
    def should_show_progress(cls) -> bool:
        """진행률 표시 여부 결정"""
        # 환경 변수로도 제어 가능
        if os.getenv('DISABLE_PROGRESS_BARS', '').lower() in ('true', '1', 'yes'):
            return False
        return not cls.DISABLE_PROGRESS_BARS
    
    @classmethod
    def is_simple_mode(cls) -> bool:
        """간단한 모드 사용 여부"""
        # 환경 변수로도 제어 가능
        if os.getenv('PROGRESS_SIMPLE_MODE', '').lower() in ('true', '1', 'yes'):
            return True
        return cls.SIMPLE_MODE
    
    @classmethod
    def get_tqdm_params(cls, desc: str = None, total: Optional[int] = None, 
                       unit: str = "it", disable: bool = None) -> dict:
        """tqdm 파라미터 생성
        
        Args:
            desc: 진행률 설명
            total: 전체 아이템 수
            unit: 단위
            disable: 강제 비활성화
            
        Returns:
            dict: tqdm 파라미터
        """
        if disable is None:
            disable = not cls.should_show_progress()
        
        params = {
            'desc': desc,
            'total': total,
            'unit': unit,
            'disable': disable,
            'leave': False,  # 완료 후 진행률 바 제거
            'ncols': 100,    # 고정 너비로 깔끔하게 표시
            'mininterval': 1.0,  # 업데이트 간격 늘려서 로그 감소
            'miniters': 1000,  # 최소 1000개마다 업데이트
        }
        
        # 간단한 모드에서는 더 적게 업데이트
        if cls.is_simple_mode():
            params['mininterval'] = 5.0  # 5초마다만 업데이트
            params['miniters'] = 10000  # 10000개마다만 업데이트
            
        return params
    
    @classmethod
    def log_progress(cls, current: int, total: int, desc: str = "", 
                     show_percent: bool = True) -> None:
        """간단한 진행률 로그 (tqdm 대신 사용)
        
        Args:
            current: 현재 진행 수
            total: 전체 수
            desc: 설명
            show_percent: 퍼센트 표시 여부
        """
        if not cls.should_show_progress():
            return
            
        if show_percent and total > 0:
            percent = (current / total) * 100
            if percent in [25, 50, 75, 100]:  # 25% 단위로만 로그
                logging.info(f"{desc}: {percent:.0f}% 완료 ({current:,}/{total:,})")
        elif current == total:
            logging.info(f"{desc}: 완료 ({total:,}개 처리)")

# 기본 설정 (필요시 변경)
# ProgressConfig.DISABLE_PROGRESS_BARS = True  # 모든 진행률 바 비활성화
# ProgressConfig.SIMPLE_MODE = True  # 간단한 모드 활성화