"""
tqdm wrapper for filters
필터에서 사용하는 tqdm을 래핑하여 중앙 제어
"""

import logging
from typing import Iterator, Optional, Any
import sys
sys.path.append('../../')
from src.utils.progress_config import ProgressConfig

try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    _tqdm = None

class FilterProgress:
    """필터 진행률 표시 래퍼 클래스"""
    
    def __init__(self, iterable: Iterator = None, total: Optional[int] = None, 
                 desc: Optional[str] = None, unit: str = "it", **kwargs):
        """
        Args:
            iterable: 반복 가능 객체
            total: 전체 아이템 수
            desc: 설명 (예: "average 필터 진행률")
            unit: 단위
            **kwargs: 추가 tqdm 파라미터
        """
        self.iterable = iterable
        self.total = total or (len(iterable) if iterable else None)
        self.desc = desc
        self.unit = unit
        self.current = 0
        self.pbar = None
        
        # ProgressConfig 설정 확인
        if TQDM_AVAILABLE and ProgressConfig.should_show_progress():
            # 간단한 모드일 때는 tqdm을 사용하지 않음
            if ProgressConfig.is_simple_mode():
                self.use_simple_log = True
                self._last_logged_percent = 0
            else:
                # tqdm 파라미터 설정
                params = ProgressConfig.get_tqdm_params(
                    desc=desc,
                    total=total,
                    unit=unit
                )
                params.update(kwargs)
                
                try:
                    self.pbar = _tqdm(iterable, **params)
                    self.use_simple_log = False
                except Exception as e:
                    logging.debug(f"tqdm 초기화 실패, 간단한 로그 사용: {e}")
                    self.use_simple_log = True
                    self._last_logged_percent = 0
        else:
            self.use_simple_log = True
            self._last_logged_percent = 0
    
    def __iter__(self):
        """반복자 구현"""
        if self.pbar is not None:
            return iter(self.pbar)
        elif self.iterable is not None:
            for item in self.iterable:
                self.current += 1
                self._log_progress()
                yield item
        else:
            return iter([])
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        if self.pbar is not None:
            self.pbar.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        if self.pbar is not None:
            self.pbar.__exit__(exc_type, exc_val, exc_tb)
        elif self.use_simple_log and self.total and self.current < self.total:
            # 마지막 로그 출력
            if self.desc:
                logging.info(f"{self.desc}: 완료 ({self.total:,}개 처리)")
    
    def update(self, n: int = 1):
        """진행률 업데이트"""
        self.current += n
        if self.pbar is not None:
            self.pbar.update(n)
        else:
            self._log_progress()
    
    def set_postfix(self, **kwargs):
        """추가 정보 설정"""
        if self.pbar is not None:
            self.pbar.set_postfix(**kwargs)
    
    def _log_progress(self):
        """간단한 진행률 로그"""
        if not self.use_simple_log or not self.total:
            return
        
        # total이 1인 경우 (단일 작업) 로그 생략
        if self.total == 1:
            return
            
        # total이 작은 경우 (10개 미만) 완료 시에만 로그
        if self.total < 10:
            if self.current >= self.total and self._last_logged_percent == 0:
                if self.desc:
                    logging.debug(f"{self.desc}: 완료")
                self._last_logged_percent = 100
            return
        
        # 25% 단위로만 로그 (큰 작업의 경우)
        percent = int((self.current / self.total) * 100)
        milestones = [25, 50, 75, 100]
        
        for milestone in milestones:
            if self._last_logged_percent < milestone <= percent:
                if self.desc:
                    logging.info(f"{self.desc}: {milestone}% 완료")
                else:
                    logging.info(f"진행률: {milestone}% 완료")
                self._last_logged_percent = milestone
                break

def filter_progress(iterable=None, total=None, desc=None, **kwargs):
    """필터용 진행률 표시 함수 (tqdm 대체)
    
    사용법:
        from src.filters.tqdm_wrapper import filter_progress
        
        # 기존: from tqdm import tqdm
        # for item in tqdm(items, desc="처리 중"):
        
        # 변경:
        for item in filter_progress(items, desc="처리 중"):
            process(item)
    """
    return FilterProgress(iterable, total, desc, **kwargs)