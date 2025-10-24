#!/usr/bin/env python3
"""
클래스 불균형 처리 유틸리티
Neural Network 학습 시 클래스 불균형 문제를 해결하는 도구
"""

import numpy as np
import logging
from typing import Tuple, Optional, Union, List
from sklearn.model_selection import StratifiedKFold, KFold
from sklearn.utils.class_weight import compute_class_weight
from collections import Counter


class ClassBalanceHandler:
    """클래스 불균형 처리를 위한 유틸리티 클래스"""

    def __init__(self, min_samples_per_class: int = 2, min_fold_size: int = 2):
        """
        Args:
            min_samples_per_class: 클래스당 최소 샘플 수
            min_fold_size: CV fold당 최소 샘플 수
        """
        self.min_samples_per_class = min_samples_per_class
        self.min_fold_size = min_fold_size

    def check_class_distribution(self, y: np.ndarray) -> dict:
        """클래스 분포 확인

        Args:
            y: 타겟 배열

        Returns:
            dict: 클래스 분포 정보
        """
        if y.ndim > 1:
            # 다중 출력의 경우 각 출력별로 확인
            distributions = {}
            for i in range(y.shape[1]):
                counter = Counter(y[:, i])
                distributions[f'output_{i}'] = {
                    'class_counts': dict(counter),
                    'min_class_size': min(counter.values()) if counter else 0,
                    'max_class_size': max(counter.values()) if counter else 0,
                    'n_classes': len(counter),
                    'imbalance_ratio': max(counter.values()) / min(counter.values()) if counter and min(counter.values()) > 0 else float('inf')
                }
            return distributions
        else:
            # 단일 출력
            counter = Counter(y)
            return {
                'class_counts': dict(counter),
                'min_class_size': min(counter.values()) if counter else 0,
                'max_class_size': max(counter.values()) if counter else 0,
                'n_classes': len(counter),
                'imbalance_ratio': max(counter.values()) / min(counter.values()) if counter and min(counter.values()) > 0 else float('inf')
            }

    def can_use_stratified_cv(self, y: np.ndarray, n_splits: int = 5) -> bool:
        """StratifiedKFold 사용 가능 여부 확인

        Args:
            y: 타겟 배열
            n_splits: CV fold 수

        Returns:
            bool: StratifiedKFold 사용 가능 여부
        """
        try:
            if y.ndim > 1:
                # 다중 출력의 경우 모든 출력이 조건을 만족해야 함
                for i in range(y.shape[1]):
                    y_single = y[:, i]
                    distribution = self.check_class_distribution(y_single)

                    # 각 클래스가 최소 fold 수만큼 샘플을 가져야 함
                    min_class_size = distribution['min_class_size']
                    if min_class_size < n_splits:
                        return False
                return True
            else:
                # 단일 출력
                distribution = self.check_class_distribution(y)
                min_class_size = distribution['min_class_size']
                return min_class_size >= n_splits

        except Exception as e:
            logging.debug(f"StratifiedKFold 확인 중 오류: {e}")
            return False

    def get_safe_cv_strategy(self, y: np.ndarray, desired_splits: int = 5) -> Tuple[object, int]:
        """안전한 CV 전략 선택

        Args:
            y: 타겟 배열
            desired_splits: 희망하는 fold 수

        Returns:
            Tuple[CV객체, 실제_fold_수]: CV 전략과 실제 사용할 fold 수
        """
        n_samples = len(y)

        # 샘플 수가 너무 적은 경우
        if n_samples < desired_splits:
            safe_splits = max(2, n_samples // 2)
            logging.warning(f"샘플 수 부족({n_samples}개). CV fold를 {desired_splits} -> {safe_splits}로 조정")
            return KFold(n_splits=safe_splits, shuffle=True, random_state=42), safe_splits

        # StratifiedKFold 사용 가능한지 확인
        if self.can_use_stratified_cv(y, desired_splits):
            logging.debug(f"StratifiedKFold 사용 가능 (splits={desired_splits})")
            return StratifiedKFold(n_splits=desired_splits, shuffle=True, random_state=42), desired_splits

        # 클래스별 최소 샘플 수 확인하여 안전한 fold 수 계산
        if y.ndim > 1:
            min_safe_splits = desired_splits
            for i in range(y.shape[1]):
                distribution = self.check_class_distribution(y[:, i])
                min_class_size = distribution['min_class_size']
                if min_class_size > 0:
                    # 각 클래스가 최소 1개씩은 각 fold에 들어갈 수 있도록
                    safe_splits_for_class = min(desired_splits, min_class_size)
                    min_safe_splits = min(min_safe_splits, safe_splits_for_class)

            safe_splits = max(2, min_safe_splits)
        else:
            distribution = self.check_class_distribution(y)
            min_class_size = distribution['min_class_size']
            safe_splits = max(2, min(desired_splits, min_class_size))

        if safe_splits < desired_splits:
            logging.warning(f"클래스 불균형으로 인해 CV fold를 {desired_splits} -> {safe_splits}로 조정")

        # StratifiedKFold를 한 번 더 시도
        try:
            if self.can_use_stratified_cv(y, safe_splits):
                return StratifiedKFold(n_splits=safe_splits, shuffle=True, random_state=42), safe_splits
        except Exception as e:
            logging.error(f"클래스 균형 처리 실패: {e}")

        # 최후의 수단으로 KFold 사용
        logging.debug(f"KFold 사용 (splits={safe_splits})")
        return KFold(n_splits=safe_splits, shuffle=True, random_state=42), safe_splits

    def compute_sample_weights(self, y: np.ndarray) -> Optional[np.ndarray]:
        """샘플 가중치 계산 (클래스 불균형 보정)

        Args:
            y: 타겟 배열

        Returns:
            Optional[np.ndarray]: 샘플 가중치 배열
        """
        try:
            if y.ndim > 1:
                # 다중 출력의 경우 평균 가중치 사용
                all_weights = []
                for i in range(y.shape[1]):
                    y_single = y[:, i]
                    unique_classes = np.unique(y_single)

                    if len(unique_classes) > 1:
                        class_weights = compute_class_weight(
                            'balanced',
                            classes=unique_classes,
                            y=y_single
                        )
                        sample_weights = np.array([class_weights[np.where(unique_classes == cls)[0][0]] for cls in y_single])
                        all_weights.append(sample_weights)

                if all_weights:
                    return np.mean(all_weights, axis=0)
                else:
                    return None
            else:
                # 단일 출력
                unique_classes = np.unique(y)
                if len(unique_classes) > 1:
                    class_weights = compute_class_weight('balanced', classes=unique_classes, y=y)
                    sample_weights = np.array([class_weights[np.where(unique_classes == cls)[0][0]] for cls in y])
                    return sample_weights
                else:
                    return None

        except Exception as e:
            logging.warning(f"샘플 가중치 계산 실패: {e}")
            return None

    def get_safe_model_params(self, model_type: str, y: np.ndarray) -> dict:
        """모델별 안전한 파라미터 반환

        Args:
            model_type: 모델 타입 ('rf', 'xgb', 'nn' 등)
            y: 타겟 배열

        Returns:
            dict: 안전한 파라미터 딕셔너리
        """
        distribution = self.check_class_distribution(y)

        params = {}

        if model_type == 'rf':
            # Random Forest 파라미터
            params.update({
                'class_weight': 'balanced',
                'min_samples_split': max(2, len(y) // 20),
                'min_samples_leaf': max(1, len(y) // 50),
                'max_depth': min(10, max(3, int(np.log2(len(y)))))
            })

        elif model_type == 'xgb':
            # XGBoost 파라미터
            if y.ndim == 1:
                imbalance_ratio = distribution.get('imbalance_ratio', 1.0)
                if imbalance_ratio > 5:  # 심한 불균형
                    params['scale_pos_weight'] = imbalance_ratio

            params.update({
                'reg_alpha': 0.1,
                'reg_lambda': 1.0,
                'min_child_weight': max(1, len(y) // 100)
            })

        elif model_type == 'nn':
            # Neural Network 파라미터
            params.update({
                'alpha': max(0.0001, 1.0 / len(y)),  # 데이터 크기에 반비례하는 정규화
                'early_stopping': True,
                'validation_fraction': min(0.2, max(0.1, 50 / len(y))),  # 최소 검증 데이터 보장
                'max_iter': min(1000, max(200, len(y) * 2))  # 데이터 크기에 비례하는 반복수
            })

        return params

    def log_class_distribution(self, y: np.ndarray, label: str = "타겟"):
        """클래스 분포 로깅

        Args:
            y: 타겟 배열
            label: 로그 레이블
        """
        distribution = self.check_class_distribution(y)

        if y.ndim > 1:
            logging.info(f"{label} 클래스 분포 (다중 출력):")
            for output_name, dist in distribution.items():
                logging.info(f"  {output_name}: {dist['class_counts']}")
                if dist['min_class_size'] < self.min_samples_per_class:
                    logging.warning(f"    클래스 불균형 경고: 최소 클래스 크기 {dist['min_class_size']}")
        else:
            logging.info(f"{label} 클래스 분포: {distribution['class_counts']}")
            if distribution['min_class_size'] < self.min_samples_per_class:
                logging.warning(f"클래스 불균형 경고: 최소 클래스 크기 {distribution['min_class_size']}")
            if distribution['imbalance_ratio'] > 10:
                logging.warning(f"심각한 클래스 불균형: 비율 {distribution['imbalance_ratio']:.2f}")


def safe_cross_val_score(estimator, X, y, cv=None, scoring=None,
                        error_score='raise', **kwargs):
    """안전한 교차 검증 점수 계산

    클래스 불균형을 자동으로 처리하는 cross_val_score 래퍼

    Args:
        estimator: 학습할 모델
        X: 특징 배열
        y: 타겟 배열
        cv: CV 전략 (None이면 자동 선택)
        scoring: 평가 메트릭
        error_score: 에러 시 반환할 점수
        **kwargs: 추가 인수

    Returns:
        np.ndarray: CV 점수 배열
    """
    from sklearn.model_selection import cross_val_score

    handler = ClassBalanceHandler()

    try:
        # CV 전략이 지정되지 않은 경우 자동 선택
        if cv is None:
            cv_strategy, n_splits = handler.get_safe_cv_strategy(y)
        else:
            cv_strategy = cv
            n_splits = getattr(cv, 'n_splits', 5)

        # 클래스 분포 로깅 (디버그 레벨)
        handler.log_class_distribution(y, "CV 입력")

        # 교차 검증 실행
        scores = cross_val_score(
            estimator, X, y,
            cv=cv_strategy,
            scoring=scoring,
            error_score=0.0 if error_score == 'raise' else error_score,
            **kwargs
        )

        logging.debug(f"CV 완료: 평균 {np.mean(scores):.4f} ± {np.std(scores):.4f}")
        return scores

    except Exception as e:
        logging.warning(f"교차 검증 실패: {e}")

        # 폴백: 더 단순한 전략 시도
        try:
            simple_cv = KFold(n_splits=2, shuffle=True, random_state=42)
            scores = cross_val_score(
                estimator, X, y,
                cv=simple_cv,
                scoring=scoring,
                error_score=0.0 if error_score == 'raise' else error_score,
                **kwargs
            )
            logging.info("단순 2-fold CV로 복구 성공")
            return scores

        except Exception as e2:
            logging.error(f"모든 CV 전략 실패: {e2}")
            if error_score == 'raise':
                raise e2
            else:
                return np.array([error_score])


# 편의 함수들
def check_class_balance(y: np.ndarray) -> bool:
    """클래스 균형 상태 확인"""
    handler = ClassBalanceHandler()
    distribution = handler.check_class_distribution(y)

    if y.ndim > 1:
        for dist in distribution.values():
            if dist['min_class_size'] < 2 or dist['imbalance_ratio'] > 20:
                return False
        return True
    else:
        return distribution['min_class_size'] >= 2 and distribution['imbalance_ratio'] <= 20


def get_recommended_cv_folds(y: np.ndarray) -> int:
    """권장 CV fold 수 반환"""
    handler = ClassBalanceHandler()
    _, n_splits = handler.get_safe_cv_strategy(y)
    return n_splits


def log_data_quality(X: np.ndarray, y: np.ndarray, name: str = "데이터"):
    """데이터 품질 로깅"""
    handler = ClassBalanceHandler()

    logging.info(f"{name} 품질 분석:")
    logging.info(f"  샘플 수: {len(X)}")
    logging.info(f"  특징 수: {X.shape[1] if X.ndim > 1 else 1}")
    logging.info(f"  타겟 차원: {y.shape}")

    # NaN 확인
    if np.isnan(X).any():
        logging.warning(f"  특징에 NaN 값 존재: {np.isnan(X).sum()}개")
    if np.isnan(y).any():
        logging.warning(f"  타겟에 NaN 값 존재: {np.isnan(y).sum()}개")

    # 클래스 분포 로깅
    handler.log_class_distribution(y, name)

    # CV 권장사항
    recommended_folds = get_recommended_cv_folds(y)
    logging.info(f"  권장 CV folds: {recommended_folds}")

    # 균형 상태
    is_balanced = check_class_balance(y)
    logging.info(f"  클래스 균형 상태: {'양호' if is_balanced else '불균형'}")