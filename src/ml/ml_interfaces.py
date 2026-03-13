# -*- coding: utf-8 -*-
"""
ML 인터페이스 및 기본 클래스

Phase 3.1: ML 아키텍처 재설계
- IMLPredictor: ML 예측기 인터페이스
- BaseMLPredictor: 공통 기능을 포함한 추상 기본 클래스

Author: Claude Code Refactoring
Date: 2025-12-08
"""

import os
import logging
import hashlib
import pickle
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime


class IMLPredictor(ABC):
    """ML 예측기 인터페이스

    모든 ML 예측기가 구현해야 하는 메서드를 정의합니다.
    """

    @abstractmethod
    def train(self, historical_data: List[Tuple], **kwargs) -> bool:
        """모델 학습

        Args:
            historical_data: 과거 당첨 번호 데이터
            **kwargs: 추가 학습 파라미터

        Returns:
            학습 성공 여부
        """
        pass

    @abstractmethod
    def predict_next_numbers(self, num_predictions: int = 5, **kwargs) -> List[List[int]]:
        """다음 번호 예측

        Args:
            num_predictions: 예측할 세트 수
            **kwargs: 추가 예측 파라미터

        Returns:
            예측된 번호 리스트 (각 세트는 6개 번호)
        """
        pass

    @abstractmethod
    def save_models(self, path: Optional[str] = None) -> bool:
        """모델 저장

        Args:
            path: 저장 경로 (None이면 기본 경로)

        Returns:
            저장 성공 여부
        """
        pass

    @abstractmethod
    def load_models(self, path: Optional[str] = None) -> bool:
        """모델 로드

        Args:
            path: 로드 경로 (None이면 기본 경로)

        Returns:
            로드 성공 여부
        """
        pass

    @property
    @abstractmethod
    def is_trained(self) -> bool:
        """모델이 학습되었는지 여부"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """모델 이름"""
        pass


class IHyperparameterOptimizable(ABC):
    """하이퍼파라미터 최적화 인터페이스"""

    @abstractmethod
    def update_hyperparameters(self, new_params: Dict[str, Any]) -> None:
        """하이퍼파라미터 업데이트

        Args:
            new_params: 새로운 파라미터 딕셔너리
        """
        pass

    @abstractmethod
    def apply_best_params(self, best_params: Dict[str, Any]) -> None:
        """최적 파라미터 적용

        Args:
            best_params: 최적 파라미터 딕셔너리
        """
        pass

    @abstractmethod
    def get_hyperparameters(self) -> Dict[str, Any]:
        """현재 하이퍼파라미터 반환"""
        pass


class IFilterAwarePredictor(ABC):
    """필터 인식 예측기 인터페이스

    필터링된 풀을 사용하는 예측기가 구현해야 하는 메서드입니다.
    """

    @abstractmethod
    def set_filtered_pool(self, filtered_combinations: List[str]) -> None:
        """필터링된 조합 풀 설정

        Args:
            filtered_combinations: 필터링된 조합 리스트 (예: ["1,2,3,4,5,6", ...])
        """
        pass

    @abstractmethod
    def predict_from_filtered_pool(self, num_predictions: int = 5, **kwargs) -> List[List[int]]:
        """필터링된 풀에서 예측

        Args:
            num_predictions: 예측할 세트 수
            **kwargs: 추가 파라미터

        Returns:
            예측된 번호 리스트
        """
        pass


class BaseMLPredictor(IMLPredictor, IHyperparameterOptimizable):
    """ML 예측기 기본 클래스

    공통 기능을 구현한 추상 기본 클래스입니다.

    Attributes:
        db_manager: 데이터베이스 관리자
        logger: 로거 인스턴스
        _is_trained: 학습 완료 여부
        _model_version: 모델 버전
        _hyperparameters: 현재 하이퍼파라미터
        _cache_dir: 캐시 디렉토리
    """

    # 기본 캐시 디렉토리
    DEFAULT_CACHE_DIR = "cache/models"

    # 캐시 유효 기간 (초) - 7일
    CACHE_TTL = 7 * 24 * 3600

    def __init__(self, db_manager=None, cache_dir: Optional[str] = None):
        """BaseMLPredictor 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            cache_dir: 캐시 디렉토리 경로
        """
        self.db_manager = db_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self._is_trained = False
        self._model_version = "1.0"
        self._hyperparameters: Dict[str, Any] = {}
        self._cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self._training_timestamp: Optional[datetime] = None

        # 캐시 디렉토리 생성
        os.makedirs(self._cache_dir, exist_ok=True)

    @property
    def is_trained(self) -> bool:
        """모델이 학습되었는지 여부"""
        return self._is_trained

    @property
    def model_name(self) -> str:
        """모델 이름 (서브클래스에서 오버라이드 권장)"""
        return self.__class__.__name__

    def get_hyperparameters(self) -> Dict[str, Any]:
        """현재 하이퍼파라미터 반환"""
        return self._hyperparameters.copy()

    def update_hyperparameters(self, new_params: Dict[str, Any]) -> None:
        """하이퍼파라미터 업데이트"""
        self._hyperparameters.update(new_params)
        self.logger.debug(f"[{self.model_name}] 하이퍼파라미터 업데이트됨: {list(new_params.keys())}")

    def apply_best_params(self, best_params: Dict[str, Any]) -> None:
        """최적 파라미터 적용 (기본 구현은 update_hyperparameters 호출)"""
        self.update_hyperparameters(best_params)
        self.logger.info(f"[{self.model_name}] 최적 파라미터 적용됨")

    def _get_cache_key(self, data_hash: str) -> str:
        """캐시 키 생성

        Args:
            data_hash: 데이터 해시

        Returns:
            캐시 키 문자열
        """
        return f"{self.model_name}_{self._model_version}_{data_hash}"

    def _compute_data_hash(self, data: Any) -> str:
        """데이터 해시 계산

        Args:
            data: 해시할 데이터

        Returns:
            MD5 해시 문자열
        """
        if isinstance(data, list):
            # 리스트의 경우 내용 기반 해시
            content = str(data[:100]) if len(data) > 100 else str(data)
        else:
            content = str(data)
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _get_cache_path(self, cache_key: str) -> str:
        """캐시 파일 경로 반환

        Args:
            cache_key: 캐시 키

        Returns:
            캐시 파일 전체 경로
        """
        return os.path.join(self._cache_dir, f"{cache_key}.pkl")

    def _is_cache_valid(self, cache_path: str) -> bool:
        """캐시 유효성 검사

        Args:
            cache_path: 캐시 파일 경로

        Returns:
            캐시가 유효하면 True
        """
        if not os.path.exists(cache_path):
            return False

        # 파일 수정 시간 확인
        mtime = os.path.getmtime(cache_path)
        age = datetime.now().timestamp() - mtime
        return age < self.CACHE_TTL

    def _save_to_cache(self, cache_key: str, data: Any) -> bool:
        """캐시에 저장

        Args:
            cache_key: 캐시 키
            data: 저장할 데이터

        Returns:
            저장 성공 여부
        """
        try:
            cache_path = self._get_cache_path(cache_key)
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            self.logger.debug(f"[{self.model_name}] 캐시 저장 완료: {cache_key}")
            return True
        except Exception as e:
            self.logger.warning(f"[{self.model_name}] 캐시 저장 실패: {e}")
            return False

    def _load_from_cache(self, cache_key: str) -> Optional[Any]:
        """캐시에서 로드

        Args:
            cache_key: 캐시 키

        Returns:
            로드된 데이터 또는 None
        """
        try:
            cache_path = self._get_cache_path(cache_key)
            if not self._is_cache_valid(cache_path):
                return None

            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            self.logger.debug(f"[{self.model_name}] 캐시 로드 완료: {cache_key}")
            return data
        except Exception as e:
            self.logger.warning(f"[{self.model_name}] 캐시 로드 실패: {e}")
            return None

    def clear_cache(self) -> int:
        """모델 캐시 정리

        Returns:
            삭제된 파일 수
        """
        count = 0
        try:
            for filename in os.listdir(self._cache_dir):
                if filename.startswith(self.model_name):
                    filepath = os.path.join(self._cache_dir, filename)
                    os.remove(filepath)
                    count += 1
            self.logger.info(f"[{self.model_name}] {count}개 캐시 파일 삭제됨")
        except Exception as e:
            self.logger.error(f"[{self.model_name}] 캐시 정리 실패: {e}")
        return count

    def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 반환

        Returns:
            모델 정보 딕셔너리
        """
        return {
            'name': self.model_name,
            'version': self._model_version,
            'is_trained': self._is_trained,
            'training_timestamp': self._training_timestamp.isoformat() if self._training_timestamp else None,
            'hyperparameters': self._hyperparameters,
            'cache_dir': self._cache_dir,
        }

    def _validate_prediction(self, numbers: List[int]) -> bool:
        """예측 번호 유효성 검사

        Args:
            numbers: 검증할 번호 리스트

        Returns:
            유효하면 True
        """
        if not numbers or len(numbers) != 6:
            return False

        # 범위 검사 (1-45)
        if not all(1 <= n <= 45 for n in numbers):
            return False

        # 중복 검사
        if len(set(numbers)) != 6:
            return False

        return True

    def _normalize_prediction(self, numbers: List[int]) -> List[int]:
        """예측 번호 정규화 (정렬)

        Args:
            numbers: 정규화할 번호 리스트

        Returns:
            정렬된 번호 리스트
        """
        return sorted(numbers)
