"""백테스팅 카운터 관리자 - 동기화 문제 해결"""
import threading
from typing import Dict, Any
import logging


class CounterManager:
    """스레드 안전한 카운터 관리자"""
    
    def __init__(self):
        self._counters = {}
        self._lock = threading.Lock()
        self._round_results = {}
        
    def increment(self, counter_name: str, amount: int = 1) -> int:
        """카운터 증가 (스레드 안전)
        
        Args:
            counter_name: 카운터 이름
            amount: 증가량
            
        Returns:
            증가된 값
        """
        with self._lock:
            if counter_name not in self._counters:
                self._counters[counter_name] = 0
            self._counters[counter_name] += amount
            return self._counters[counter_name]
    
    def get(self, counter_name: str) -> int:
        """카운터 값 조회
        
        Args:
            counter_name: 카운터 이름
            
        Returns:
            현재 값
        """
        with self._lock:
            return self._counters.get(counter_name, 0)
    
    def reset(self, counter_name: str):
        """카운터 초기화
        
        Args:
            counter_name: 카운터 이름
        """
        with self._lock:
            if counter_name in self._counters:
                self._counters[counter_name] = 0
    
    def reset_all(self):
        """모든 카운터 초기화"""
        with self._lock:
            self._counters.clear()
            self._round_results.clear()
    
    def set_round_result(self, round_num: int, model: str, result: Dict[str, Any]):
        """회차별 결과 저장
        
        Args:
            round_num: 회차 번호
            model: 모델 이름
            result: 결과 데이터
        """
        with self._lock:
            if round_num not in self._round_results:
                self._round_results[round_num] = {}
            self._round_results[round_num][model] = result
    
    def get_round_result(self, round_num: int, model: str = None) -> Dict[str, Any]:
        """회차별 결과 조회
        
        Args:
            round_num: 회차 번호
            model: 모델 이름 (None이면 전체)
            
        Returns:
            결과 데이터
        """
        with self._lock:
            if round_num not in self._round_results:
                return {}
            
            if model:
                return self._round_results[round_num].get(model, {})
            else:
                return self._round_results[round_num]
    
    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환
        
        Returns:
            통계 정보
        """
        with self._lock:
            total_rounds = len(self._round_results)
            models = set()
            
            for round_data in self._round_results.values():
                models.update(round_data.keys())
            
            return {
                'total_rounds': total_rounds,
                'total_models': len(models),
                'models': list(models),
                'counters': dict(self._counters),
                'rounds_processed': list(self._round_results.keys())
            }
    
    def log_status(self):
        """현재 상태 로깅"""
        stats = self.get_statistics()
        logging.info(f"[CounterManager] 처리된 회차: {stats['total_rounds']}개")
        logging.info(f"[CounterManager] 활성 모델: {stats['models']}")
        for counter_name, value in stats['counters'].items():
            logging.info(f"[CounterManager] {counter_name}: {value}")


# 전역 카운터 매니저 인스턴스 (싱글톤)
_counter_manager_instance = None
_lock = threading.Lock()


def get_counter_manager() -> CounterManager:
    """전역 카운터 매니저 인스턴스 반환"""
    global _counter_manager_instance
    
    if _counter_manager_instance is None:
        with _lock:
            if _counter_manager_instance is None:
                _counter_manager_instance = CounterManager()
                logging.info("카운터 매니저 초기화 완료")
    
    return _counter_manager_instance