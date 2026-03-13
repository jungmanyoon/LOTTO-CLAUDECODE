#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
커스텀 예외 클래스 모듈

Phase 1.4: Custom Exception Classes (CRITICAL)
- 체계적인 예외 계층 구조 제공
- 각 도메인별 명확한 예외 타입 정의
- 예외 처리 및 로깅 표준화

예외 계층 구조:
    LottoBaseException
    ├── DatabaseError
    │   ├── DatabaseConnectionError
    │   ├── DatabaseQueryError
    │   ├── DatabaseIntegrityError
    │   └── DatabaseTimeoutError
    ├── FilterError
    │   ├── FilterConfigError
    │   ├── FilterExecutionError
    │   └── FilterValidationError
    ├── MLError
    │   ├── ModelLoadError
    │   ├── ModelTrainingError
    │   ├── PredictionError
    │   └── ModelCacheError
    ├── ConfigError
    │   ├── ConfigFileNotFoundError
    │   ├── ConfigParseError
    │   └── ConfigValidationError
    ├── BacktestError
    │   ├── BacktestDataError
    │   └── BacktestExecutionError
    └── OptimizationError
        ├── ThresholdOptimizationError
        └── AutoLearningError
"""

from typing import Optional, Any, Dict
import traceback


class LottoBaseException(Exception):
    """
    모든 로또 예측 시스템 예외의 기본 클래스

    Attributes:
        message: 예외 메시지
        error_code: 예외 코드 (로깅 및 추적용)
        details: 추가 컨텍스트 정보
        cause: 원인 예외
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self._default_error_code()
        self.details = details or {}
        self.cause = cause

    def _default_error_code(self) -> str:
        """기본 에러 코드 반환"""
        return f"LOTTO_{self.__class__.__name__.upper()}"

    def to_dict(self) -> Dict[str, Any]:
        """예외 정보를 딕셔너리로 반환"""
        result = {
            'error_type': self.__class__.__name__,
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details
        }
        if self.cause:
            result['cause'] = str(self.cause)
            result['cause_type'] = type(self.cause).__name__
        return result

    def __str__(self) -> str:
        parts = [f"[{self.error_code}] {self.message}"]
        if self.details:
            parts.append(f"Details: {self.details}")
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        return " | ".join(parts)


# =============================================================================
# Database Exceptions
# =============================================================================

class DatabaseError(LottoBaseException):
    """데이터베이스 관련 기본 예외"""

    def __init__(
        self,
        message: str,
        db_path: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if db_path:
            details['db_path'] = db_path
        if query:
            # 보안을 위해 쿼리 일부만 저장
            details['query_preview'] = query[:200] if len(query) > 200 else query
        kwargs['details'] = details
        super().__init__(message, **kwargs)


class DatabaseConnectionError(DatabaseError):
    """데이터베이스 연결 실패 예외"""

    def _default_error_code(self) -> str:
        return "DB_CONNECTION_ERROR"


class DatabaseQueryError(DatabaseError):
    """쿼리 실행 실패 예외"""

    def _default_error_code(self) -> str:
        return "DB_QUERY_ERROR"


class DatabaseIntegrityError(DatabaseError):
    """데이터 무결성 위반 예외"""

    def _default_error_code(self) -> str:
        return "DB_INTEGRITY_ERROR"


class DatabaseTimeoutError(DatabaseError):
    """데이터베이스 작업 타임아웃 예외"""

    def __init__(self, message: str, timeout_seconds: Optional[float] = None, **kwargs):
        details = kwargs.get('details', {})
        if timeout_seconds:
            details['timeout_seconds'] = timeout_seconds
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "DB_TIMEOUT_ERROR"


class DatabasePoolExhaustedError(DatabaseError):
    """연결 풀 고갈 예외"""

    def _default_error_code(self) -> str:
        return "DB_POOL_EXHAUSTED"


# =============================================================================
# Filter Exceptions
# =============================================================================

class FilterError(LottoBaseException):
    """필터 관련 기본 예외"""

    def __init__(
        self,
        message: str,
        filter_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if filter_name:
            details['filter_name'] = filter_name
        kwargs['details'] = details
        super().__init__(message, **kwargs)


class FilterConfigError(FilterError):
    """필터 설정 오류 예외"""

    def _default_error_code(self) -> str:
        return "FILTER_CONFIG_ERROR"


class FilterExecutionError(FilterError):
    """필터 실행 중 오류 예외"""

    def __init__(
        self,
        message: str,
        combination_count: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if combination_count:
            details['combination_count'] = combination_count
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "FILTER_EXECUTION_ERROR"


class FilterValidationError(FilterError):
    """필터 검증 실패 예외"""

    def _default_error_code(self) -> str:
        return "FILTER_VALIDATION_ERROR"


class FilterThresholdError(FilterError):
    """필터 임계값 오류 예외"""

    def __init__(
        self,
        message: str,
        threshold_value: Optional[float] = None,
        valid_range: Optional[tuple] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if threshold_value is not None:
            details['threshold_value'] = threshold_value
        if valid_range:
            details['valid_range'] = valid_range
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "FILTER_THRESHOLD_ERROR"


# =============================================================================
# ML/Model Exceptions
# =============================================================================

class MLError(LottoBaseException):
    """머신러닝 관련 기본 예외"""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if model_name:
            details['model_name'] = model_name
        kwargs['details'] = details
        super().__init__(message, **kwargs)


class ModelLoadError(MLError):
    """모델 로드 실패 예외"""

    def __init__(
        self,
        message: str,
        model_path: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if model_path:
            details['model_path'] = model_path
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "ML_MODEL_LOAD_ERROR"


class ModelTrainingError(MLError):
    """모델 훈련 실패 예외"""

    def __init__(
        self,
        message: str,
        epochs_completed: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if epochs_completed is not None:
            details['epochs_completed'] = epochs_completed
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "ML_TRAINING_ERROR"


class PredictionError(MLError):
    """예측 생성 실패 예외"""

    def _default_error_code(self) -> str:
        return "ML_PREDICTION_ERROR"


class ModelCacheError(MLError):
    """모델 캐시 관련 예외"""

    def __init__(
        self,
        message: str,
        cache_path: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if cache_path:
            details['cache_path'] = cache_path
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "ML_CACHE_ERROR"


class EnsembleError(MLError):
    """앙상블 모델 관련 예외"""

    def __init__(
        self,
        message: str,
        failed_models: Optional[list] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if failed_models:
            details['failed_models'] = failed_models
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "ML_ENSEMBLE_ERROR"


# =============================================================================
# Configuration Exceptions
# =============================================================================

class ConfigError(LottoBaseException):
    """설정 관련 기본 예외"""

    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if config_file:
            details['config_file'] = config_file
        kwargs['details'] = details
        super().__init__(message, **kwargs)


class ConfigFileNotFoundError(ConfigError):
    """설정 파일 없음 예외"""

    def _default_error_code(self) -> str:
        return "CONFIG_FILE_NOT_FOUND"


class ConfigParseError(ConfigError):
    """설정 파일 파싱 실패 예외"""

    def __init__(
        self,
        message: str,
        line_number: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if line_number:
            details['line_number'] = line_number
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "CONFIG_PARSE_ERROR"


class ConfigValidationError(ConfigError):
    """설정 유효성 검증 실패 예외"""

    def __init__(
        self,
        message: str,
        invalid_keys: Optional[list] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if invalid_keys:
            details['invalid_keys'] = invalid_keys
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "CONFIG_VALIDATION_ERROR"


# =============================================================================
# Backtest Exceptions
# =============================================================================

class BacktestError(LottoBaseException):
    """백테스트 관련 기본 예외"""

    def __init__(
        self,
        message: str,
        round_number: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if round_number:
            details['round_number'] = round_number
        kwargs['details'] = details
        super().__init__(message, **kwargs)


class BacktestDataError(BacktestError):
    """백테스트 데이터 오류 예외"""

    def _default_error_code(self) -> str:
        return "BACKTEST_DATA_ERROR"


class BacktestExecutionError(BacktestError):
    """백테스트 실행 오류 예외"""

    def __init__(
        self,
        message: str,
        rounds_completed: Optional[int] = None,
        total_rounds: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if rounds_completed is not None:
            details['rounds_completed'] = rounds_completed
        if total_rounds is not None:
            details['total_rounds'] = total_rounds
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "BACKTEST_EXECUTION_ERROR"


# =============================================================================
# Optimization Exceptions
# =============================================================================

class OptimizationError(LottoBaseException):
    """최적화 관련 기본 예외"""
    pass


class ThresholdOptimizationError(OptimizationError):
    """임계값 최적화 오류 예외"""

    def __init__(
        self,
        message: str,
        trial_number: Optional[int] = None,
        current_best: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if trial_number is not None:
            details['trial_number'] = trial_number
        if current_best is not None:
            details['current_best'] = current_best
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "THRESHOLD_OPTIMIZATION_ERROR"


class AutoLearningError(OptimizationError):
    """자동 학습 오류 예외"""

    def _default_error_code(self) -> str:
        return "AUTO_LEARNING_ERROR"


class CheckpointError(OptimizationError):
    """체크포인트 관련 예외"""

    def __init__(
        self,
        message: str,
        checkpoint_path: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if checkpoint_path:
            details['checkpoint_path'] = checkpoint_path
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "CHECKPOINT_ERROR"


# =============================================================================
# Utility Exceptions
# =============================================================================

class DataCollectionError(LottoBaseException):
    """데이터 수집 관련 예외"""

    def __init__(
        self,
        message: str,
        source_url: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if source_url:
            details['source_url'] = source_url
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "DATA_COLLECTION_ERROR"


class ValidationError(LottoBaseException):
    """일반 검증 오류 예외"""

    def _default_error_code(self) -> str:
        return "VALIDATION_ERROR"


class ResourceExhaustedError(LottoBaseException):
    """리소스 고갈 예외 (메모리, CPU 등)"""

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        current_usage: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if resource_type:
            details['resource_type'] = resource_type
        if current_usage is not None:
            details['current_usage'] = current_usage
        kwargs['details'] = details
        super().__init__(message, **kwargs)

    def _default_error_code(self) -> str:
        return "RESOURCE_EXHAUSTED"


# =============================================================================
# Helper Functions
# =============================================================================

def wrap_exception(
    exc: Exception,
    wrapper_class: type = LottoBaseException,
    message: Optional[str] = None,
    **kwargs
) -> LottoBaseException:
    """
    일반 예외를 로또 시스템 예외로 래핑

    Args:
        exc: 원본 예외
        wrapper_class: 래핑할 예외 클래스
        message: 새 메시지 (없으면 원본 예외 메시지 사용)
        **kwargs: 추가 인자

    Returns:
        래핑된 예외

    Example:
        try:
            db.execute(query)
        except sqlite3.Error as e:
            raise wrap_exception(e, DatabaseQueryError, query=query)
    """
    return wrapper_class(
        message=message or str(exc),
        cause=exc,
        **kwargs
    )


def log_exception(exc: LottoBaseException, logger) -> None:
    """
    예외 정보를 로거에 기록

    Args:
        exc: 로또 시스템 예외
        logger: 로거 인스턴스
    """
    logger.error(
        f"Exception occurred: {exc.error_code}",
        extra=exc.to_dict()
    )
    if exc.cause:
        logger.debug(f"Traceback:\n{traceback.format_exc()}")


# =============================================================================
# Exception Registry for Error Code Lookup
# =============================================================================

EXCEPTION_REGISTRY = {
    'DB_CONNECTION_ERROR': DatabaseConnectionError,
    'DB_QUERY_ERROR': DatabaseQueryError,
    'DB_INTEGRITY_ERROR': DatabaseIntegrityError,
    'DB_TIMEOUT_ERROR': DatabaseTimeoutError,
    'DB_POOL_EXHAUSTED': DatabasePoolExhaustedError,
    'FILTER_CONFIG_ERROR': FilterConfigError,
    'FILTER_EXECUTION_ERROR': FilterExecutionError,
    'FILTER_VALIDATION_ERROR': FilterValidationError,
    'FILTER_THRESHOLD_ERROR': FilterThresholdError,
    'ML_MODEL_LOAD_ERROR': ModelLoadError,
    'ML_TRAINING_ERROR': ModelTrainingError,
    'ML_PREDICTION_ERROR': PredictionError,
    'ML_CACHE_ERROR': ModelCacheError,
    'ML_ENSEMBLE_ERROR': EnsembleError,
    'CONFIG_FILE_NOT_FOUND': ConfigFileNotFoundError,
    'CONFIG_PARSE_ERROR': ConfigParseError,
    'CONFIG_VALIDATION_ERROR': ConfigValidationError,
    'BACKTEST_DATA_ERROR': BacktestDataError,
    'BACKTEST_EXECUTION_ERROR': BacktestExecutionError,
    'THRESHOLD_OPTIMIZATION_ERROR': ThresholdOptimizationError,
    'AUTO_LEARNING_ERROR': AutoLearningError,
    'CHECKPOINT_ERROR': CheckpointError,
    'DATA_COLLECTION_ERROR': DataCollectionError,
    'VALIDATION_ERROR': ValidationError,
    'RESOURCE_EXHAUSTED': ResourceExhaustedError,
}


def get_exception_class(error_code: str) -> type:
    """에러 코드로 예외 클래스 조회"""
    return EXCEPTION_REGISTRY.get(error_code, LottoBaseException)
