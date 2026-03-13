#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mock 데이터베이스 레이어

Phase 1.5: Mock Database Layer (CRITICAL)
- 테스트 환경에서 실제 DB 대신 사용
- 빠르고 독립적인 테스트 실행
- 데이터 오염 방지

사용 예:
    from tests.mocks.mock_database import MockDatabaseManager

    @pytest.fixture
    def mock_db():
        db = MockDatabaseManager()
        db.setup_sample_data()
        yield db
        db.cleanup()
"""

from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import random


class MockDatabaseManager:
    """
    DatabaseManager의 Mock 구현

    실제 SQLite 연결 없이 메모리 내에서 동작합니다.
    테스트 격리와 속도를 위해 사용합니다.
    """

    _instance = None  # Singleton 패턴 지원

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: Mock에서는 사용되지 않지만 호환성을 위해 유지
        """
        self.db_path = db_path or ":memory:"
        self._winning_numbers: List[Tuple] = []
        self._predictions: List[Dict] = []
        self._filter_results: Dict[str, List] = {}
        self._connected = True
        self._transaction_active = False

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> 'MockDatabaseManager':
        """싱글톤 인스턴스 반환 (테스트용)"""
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스 리셋 (테스트 격리용)"""
        cls._instance = None

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        pass

    # =========================================================================
    # Sample Data Setup
    # =========================================================================

    def setup_sample_data(self, num_rounds: int = 100) -> None:
        """
        테스트용 샘플 데이터 생성

        Args:
            num_rounds: 생성할 회차 수
        """
        self._winning_numbers = []

        for round_num in range(1, num_rounds + 1):
            # 랜덤 당첨번호 생성 (1-45 중 6개 + 보너스)
            numbers = sorted(random.sample(range(1, 46), 6))
            remaining = [n for n in range(1, 46) if n not in numbers]
            bonus = random.choice(remaining)

            # 날짜 생성
            date = f"2002-{((round_num-1)//4)+1:02d}-{((round_num-1)%4)*7+7:02d}"

            self._winning_numbers.append((
                round_num,
                numbers,
                bonus,
                date
            ))

    def setup_realistic_data(self) -> None:
        """실제 로또 번호와 유사한 패턴의 데이터 생성"""
        # 실제 당첨번호 일부를 사용
        realistic_numbers = [
            (1, [1, 2, 3, 4, 5, 6], 7, "2002-12-07"),
            (2, [7, 11, 16, 35, 36, 44], 1, "2002-12-14"),
            (3, [2, 9, 16, 25, 26, 40], 42, "2002-12-21"),
            (4, [4, 7, 14, 30, 31, 38], 44, "2002-12-28"),
            (5, [2, 6, 12, 19, 22, 43], 15, "2003-01-04"),
            (6, [1, 6, 14, 15, 29, 41], 33, "2003-01-11"),
            (7, [10, 16, 18, 31, 33, 40], 34, "2003-01-18"),
            (8, [5, 9, 13, 23, 28, 44], 19, "2003-01-25"),
            (9, [6, 8, 13, 23, 26, 45], 41, "2003-02-01"),
            (10, [3, 6, 16, 22, 29, 40], 24, "2003-02-08"),
        ]
        self._winning_numbers = realistic_numbers

    # =========================================================================
    # DatabaseManager API Compatibility
    # =========================================================================

    def get_all_winning_numbers(self) -> List[Tuple[int, List[int]]]:
        """
        모든 당첨번호 조회 (보너스 제외)

        Returns:
            List[Tuple[round, numbers]]: 회차별 당첨번호 목록
        """
        return [(r, nums) for r, nums, _, _ in self._winning_numbers]

    def get_all_numbers(self) -> List[Tuple[int, List[int]]]:
        """get_all_winning_numbers의 별칭"""
        return self.get_all_winning_numbers()

    def get_numbers_with_bonus(self) -> List[Tuple[int, Tuple[int, ...]]]:
        """
        보너스 번호 포함 당첨번호 조회

        Returns:
            List[Tuple[round, (n1,n2,n3,n4,n5,n6,bonus)]]: 보너스 포함 당첨번호
        """
        result = []
        for round_num, numbers, bonus, _ in self._winning_numbers:
            nums_with_bonus = tuple(numbers + [bonus])
            result.append((round_num, nums_with_bonus))
        return result

    def get_winning_numbers_before(self, round_num: int) -> List[Tuple[int, List[int]]]:
        """
        특정 회차 이전의 당첨번호 조회

        Args:
            round_num: 기준 회차

        Returns:
            기준 회차 이전의 당첨번호 목록
        """
        return [(r, nums) for r, nums, _, _ in self._winning_numbers if r < round_num]

    def get_latest_round(self) -> int:
        """최신 회차 번호 반환"""
        if not self._winning_numbers:
            return 0
        return max(r for r, _, _, _ in self._winning_numbers)

    def get_winning_numbers_by_round(self, round_num: int) -> Optional[List[int]]:
        """
        특정 회차의 당첨번호 조회

        Args:
            round_num: 조회할 회차

        Returns:
            당첨번호 리스트 또는 None
        """
        for r, nums, _, _ in self._winning_numbers:
            if r == round_num:
                return nums
        return None

    def get_bonus_by_round(self, round_num: int) -> Optional[int]:
        """
        특정 회차의 보너스 번호 조회

        Args:
            round_num: 조회할 회차

        Returns:
            보너스 번호 또는 None
        """
        for r, _, bonus, _ in self._winning_numbers:
            if r == round_num:
                return bonus
        return None

    # =========================================================================
    # Additional Mock Methods
    # =========================================================================

    def save_prediction(self, prediction: Dict) -> int:
        """
        예측 결과 저장 (Mock)

        Args:
            prediction: 예측 데이터

        Returns:
            저장된 예측의 ID
        """
        prediction_id = len(self._predictions) + 1
        prediction['id'] = prediction_id
        prediction['created_at'] = datetime.now().isoformat()
        self._predictions.append(prediction)
        return prediction_id

    def get_predictions(self, limit: int = 10) -> List[Dict]:
        """최근 예측 조회"""
        return self._predictions[-limit:][::-1]

    def save_filter_result(self, filter_name: str, round_num: int, result: Any) -> None:
        """필터 결과 저장"""
        if filter_name not in self._filter_results:
            self._filter_results[filter_name] = []
        self._filter_results[filter_name].append({
            'round': round_num,
            'result': result,
            'created_at': datetime.now().isoformat()
        })

    def get_filter_results(self, filter_name: str) -> List[Dict]:
        """필터 결과 조회"""
        return self._filter_results.get(filter_name, [])

    # =========================================================================
    # Connection Management (Mock)
    # =========================================================================

    def connect(self) -> None:
        """연결 (Mock - 항상 성공)"""
        self._connected = True

    def close(self) -> None:
        """연결 종료 (Mock)"""
        self._connected = False

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected

    def begin_transaction(self) -> None:
        """트랜잭션 시작"""
        self._transaction_active = True

    def commit(self) -> None:
        """트랜잭션 커밋"""
        self._transaction_active = False

    def rollback(self) -> None:
        """트랜잭션 롤백"""
        self._transaction_active = False

    # =========================================================================
    # Test Utilities
    # =========================================================================

    def clear_all_data(self) -> None:
        """모든 Mock 데이터 초기화"""
        self._winning_numbers = []
        self._predictions = []
        self._filter_results = {}

    def add_winning_numbers(self, round_num: int, numbers: List[int],
                           bonus: int, date: Optional[str] = None) -> None:
        """
        당첨번호 직접 추가

        Args:
            round_num: 회차
            numbers: 당첨번호 리스트
            bonus: 보너스 번호
            date: 추첨 일자
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        self._winning_numbers.append((round_num, numbers, bonus, date))
        # 회차 순으로 정렬
        self._winning_numbers.sort(key=lambda x: x[0])

    def get_data_stats(self) -> Dict[str, int]:
        """Mock 데이터 통계 반환"""
        return {
            'winning_numbers_count': len(self._winning_numbers),
            'predictions_count': len(self._predictions),
            'filter_results_count': sum(len(v) for v in self._filter_results.values())
        }


class MockPerformanceStatsManager:
    """
    PerformanceStatsManager의 Mock 구현
    """

    _instance = None

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._stats: Dict[str, List] = {}
        self._sessions: List[Dict] = []

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> 'MockPerformanceStatsManager':
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def save_backtest_result(self, session_id: str, round_num: int,
                            predictions: List, actual: List,
                            match_count: int, **kwargs) -> int:
        """백테스트 결과 저장"""
        result_id = len(self._stats.get('backtest_results', [])) + 1
        if 'backtest_results' not in self._stats:
            self._stats['backtest_results'] = []
        self._stats['backtest_results'].append({
            'id': result_id,
            'session_id': session_id,
            'round_num': round_num,
            'predictions': predictions,
            'actual': actual,
            'match_count': match_count,
            **kwargs
        })
        return result_id

    def save_model_performance(self, model_name: str, round_num: int,
                              avg_matches: float, **kwargs) -> int:
        """모델 성능 저장"""
        result_id = len(self._stats.get('model_performance', [])) + 1
        if 'model_performance' not in self._stats:
            self._stats['model_performance'] = []
        self._stats['model_performance'].append({
            'id': result_id,
            'model_name': model_name,
            'round_num': round_num,
            'avg_matches': avg_matches,
            **kwargs
        })
        return result_id

    def get_model_performance(self, model_name: str,
                             limit: int = 10) -> List[Dict]:
        """모델 성능 조회"""
        results = self._stats.get('model_performance', [])
        filtered = [r for r in results if r['model_name'] == model_name]
        return filtered[-limit:][::-1]

    def get_best_performance(self, model_name: str) -> Optional[Dict]:
        """최고 성능 조회"""
        results = self.get_model_performance(model_name, limit=1000)
        if not results:
            return None
        return max(results, key=lambda x: x.get('avg_matches', 0))

    def close(self) -> None:
        """연결 종료 (Mock)"""
        pass


class MockThresholdManager:
    """
    ThresholdManager의 Mock 구현
    """

    _instance = None

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self._thresholds = {
            'global_probability_threshold': 1.0,
            'ml_relaxed_threshold': 0.5,
            'min_threshold': 0.3,
            'max_threshold': 3.0
        }
        self._observers = []

    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> 'MockThresholdManager':
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def get_threshold(self, key: str) -> float:
        """임계값 조회"""
        return self._thresholds.get(key, 1.0)

    def set_threshold(self, key: str, value: float) -> None:
        """임계값 설정"""
        self._thresholds[key] = value
        self._notify_observers(key, value)

    def register_observer(self, observer) -> None:
        """옵저버 등록"""
        if observer not in self._observers:
            self._observers.append(observer)

    def _notify_observers(self, key: str, value: float) -> None:
        """옵저버 알림"""
        for observer in self._observers:
            if hasattr(observer, 'on_threshold_change'):
                observer.on_threshold_change(key, value)

    def get_all_thresholds(self) -> Dict[str, float]:
        """모든 임계값 조회"""
        return self._thresholds.copy()

    def cleanup(self) -> None:
        """리소스 정리"""
        self._observers.clear()


class MockFilterDB:
    """
    FilterDB의 Mock 구현
    """

    def __init__(self, filter_name: str, db_dir: Optional[str] = None):
        self.filter_name = filter_name
        self.db_dir = db_dir
        self._filtered_combinations: List[Dict] = []
        self._excluded_combinations: List[Dict] = []

    def save_filtered_combination(self, round_num: int, combination: str,
                                  probability: float) -> int:
        """필터링된 조합 저장"""
        comb_id = len(self._filtered_combinations) + 1
        self._filtered_combinations.append({
            'id': comb_id,
            'round': round_num,
            'combination': combination,
            'probability': probability,
            'created_at': datetime.now().isoformat()
        })
        return comb_id

    def save_excluded_combination(self, round_num: int, combination: str,
                                  reason: str) -> int:
        """제외된 조합 저장"""
        exc_id = len(self._excluded_combinations) + 1
        self._excluded_combinations.append({
            'id': exc_id,
            'round': round_num,
            'combination': combination,
            'reason': reason,
            'created_at': datetime.now().isoformat()
        })
        return exc_id

    def get_filtered_combinations(self, round_num: int) -> List[Dict]:
        """필터링된 조합 조회"""
        return [c for c in self._filtered_combinations if c['round'] == round_num]

    def get_excluded_count(self, round_num: int) -> int:
        """제외된 조합 수 조회"""
        return len([c for c in self._excluded_combinations if c['round'] == round_num])

    def clear_round_data(self, round_num: int) -> None:
        """특정 회차 데이터 삭제"""
        self._filtered_combinations = [
            c for c in self._filtered_combinations if c['round'] != round_num
        ]
        self._excluded_combinations = [
            c for c in self._excluded_combinations if c['round'] != round_num
        ]

    def close(self) -> None:
        """연결 종료 (Mock)"""
        pass
