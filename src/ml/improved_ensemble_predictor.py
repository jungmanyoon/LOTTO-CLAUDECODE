#!/usr/bin/env python3
"""
개선된 앙상블 모델 기반 로또 번호 예측 시스템
언더플로우 방지 및 신뢰도 향상을 위한 개선사항 포함
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
import pickle
from datetime import datetime

# ML 라이브러리 imports
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    from sklearn.calibration import CalibratedClassifierCV
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available. Ensemble predictor will work in limited mode.")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available. Will use alternative models.")

class ImprovedEnsemblePredictor:
    """개선된 앙상블 기반 로또 번호 예측기"""
    
    def __init__(self, model_dir: str = 'models/improved_ensemble'):
        """
        Args:
            model_dir: 모델 저장 디렉토리
        """
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        
        self.models = {}
        self.calibrated_models = {}  # 보정된 모델
        self.scalers = {}
        self.feature_importances = {}
        self.is_trained = False
        
        # 동적 앙상블 가중치 (성능 기반 조정)
        self.ensemble_weights = {
            'rf': 0.25,     # Random Forest
            'gb': 0.25,     # Gradient Boosting
            'xgb': 0.30,    # XGBoost
            'nn': 0.20      # Neural Network
        }
        
        # 성능 추적
        self.model_performance = {
            'rf': {'accuracy': 0, 'f1': 0},
            'gb': {'accuracy': 0, 'f1': 0},
            'xgb': {'accuracy': 0, 'f1': 0},
            'nn': {'accuracy': 0, 'f1': 0}
        }
        
        # 특징 엔지니어링 설정 (확장)
        self.feature_config = {
            'use_statistics': True,      # 통계적 특징 사용
            'use_patterns': True,        # 패턴 특징 사용
            'use_temporal': True,        # 시간적 특징 사용
            'use_frequency': True,       # 빈도 기반 특징
            'use_correlation': True,     # 상관관계 특징
            'window_sizes': [5, 10, 20, 50],  # 다양한 윈도우 크기
            'min_window_data': 10        # 최소 필요 데이터 수
        }
        
        # 안정성 설정
        self.stability_config = {
            'min_probability': 1e-10,    # 최소 확률 (언더플로우 방지)
            'max_probability': 0.999,    # 최대 확률
            'smoothing_alpha': 0.1,      # 라플라스 스무딩
            'temperature': 1.0           # 확률 분포 온도
        }
        
        # 모델 초기화
        if SKLEARN_AVAILABLE:
            self._initialize_models()
    
    def _initialize_models(self):
        """모델 초기화 또는 로드"""
        # Random Forest
        self.models['rf'] = self._build_random_forest()
        
        # Gradient Boosting
        self.models['gb'] = self._build_gradient_boosting()
        
        # XGBoost
        if XGBOOST_AVAILABLE:
            self.models['xgb'] = self._build_xgboost()
        
        # Neural Network
        self.models['nn'] = self._build_neural_network()
        
        # Scalers (다중 스케일러 사용)
        self.scalers = {
            'standard': StandardScaler(),
            'minmax': MinMaxScaler(feature_range=(0, 1))
        }
        
        # 저장된 모델 로드 시도
        self._load_saved_models()
    
    def _build_random_forest(self) -> RandomForestClassifier:
        """Random Forest 모델 구축 (개선된 하이퍼파라미터)"""
        return RandomForestClassifier(
            n_estimators=300,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            max_features='sqrt',
            bootstrap=True,
            oob_score=True,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'  # 클래스 불균형 처리
        )
    
    def _build_gradient_boosting(self) -> GradientBoostingClassifier:
        """Gradient Boosting 모델 구축"""
        return GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
            n_iter_no_change=20  # 조기 종료
        )
    
    def _build_xgboost(self):
        """XGBoost 모델 구축 (개선된 설정)"""
        return xgb.XGBClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='binary:logistic',
            eval_metric='logloss',
            random_state=42,
            n_jobs=-1,
            scale_pos_weight=7.5,  # 클래스 불균형 고려 (45개 중 6개 선택)
            reg_alpha=0.1,         # L1 정규화
            reg_lambda=1.0         # L2 정규화
        )
    
    def _build_neural_network(self) -> MLPClassifier:
        """Neural Network 모델 구축 (개선된 아키텍처)"""
        return MLPClassifier(
            hidden_layer_sizes=(512, 256, 128, 64),
            activation='relu',
            solver='adam',
            alpha=0.001,
            batch_size=32,
            learning_rate='adaptive',
            learning_rate_init=0.001,
            max_iter=1000,
            shuffle=True,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            tol=0.0001
        )
    
    def extract_features(self, winning_numbers: List[str], 
                        target_round: int = None) -> pd.DataFrame:
        """향상된 특징 추출
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            target_round: 타겟 회차 (학습시 사용)
            
        Returns:
            pd.DataFrame: 추출된 특징
        """
        features_list = []
        
        # 사용 가능한 데이터 수 확인 및 window_sizes 동적 조정
        available_data = len(winning_numbers)
        original_window_sizes = self.feature_config['window_sizes'].copy()
        
        # 데이터가 부족한 경우 window_sizes 조정
        if available_data < max(original_window_sizes):
            adjusted_sizes = [w for w in original_window_sizes if w <= available_data]
            if not adjusted_sizes and available_data >= 5:
                adjusted_sizes = [5]
            self.feature_config['window_sizes'] = adjusted_sizes
            logging.info(f"Window sizes 조정: {original_window_sizes} → {adjusted_sizes} (가용 데이터: {available_data}개)")
        
        # 번호별 출현 빈도 계산
        number_frequency = self._calculate_frequency(winning_numbers)
        
        for i in range(len(winning_numbers)):
            if target_round and i >= target_round:
                break
                
            features = {}
            numbers = [int(n) for n in winning_numbers[i].split(',')]
            
            # 1. 기본 통계 특징
            if self.feature_config['use_statistics']:
                features.update(self._extract_statistical_features(numbers))
            
            # 2. 패턴 특징
            if self.feature_config['use_patterns']:
                features.update(self._extract_pattern_features(numbers))
            
            # 3. 시간적 특징
            if self.feature_config['use_temporal'] and i > 0:
                features.update(self._extract_temporal_features(
                    numbers, winning_numbers[:i]
                ))
            
            # 4. 빈도 기반 특징
            if self.feature_config['use_frequency']:
                features.update(self._extract_frequency_features(
                    numbers, number_frequency, i
                ))
            
            # 5. 상관관계 특징
            if self.feature_config['use_correlation'] and i >= 10:
                features.update(self._extract_correlation_features(
                    numbers, winning_numbers[max(0, i-10):i]
                ))
            
            features_list.append(features)
        
        # 원래 window_sizes 복원
        self.feature_config['window_sizes'] = original_window_sizes
        
        return pd.DataFrame(features_list).fillna(0)
    
    def _extract_statistical_features(self, numbers: List[int]) -> Dict[str, float]:
        """통계적 특징 추출"""
        features = {}
        
        # 기본 통계
        features['mean'] = np.mean(numbers)
        features['std'] = np.std(numbers)
        features['min'] = min(numbers)
        features['max'] = max(numbers)
        features['range'] = features['max'] - features['min']
        features['sum'] = sum(numbers)
        features['median'] = np.median(numbers)
        
        # 분포 특징
        features['skewness'] = self._safe_division(
            np.mean([(n - features['mean'])**3 for n in numbers]),
            features['std']**3
        )
        features['kurtosis'] = self._safe_division(
            np.mean([(n - features['mean'])**4 for n in numbers]),
            features['std']**4
        ) - 3
        
        # 홀짝 분포
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        features['odd_ratio'] = odd_count / 6
        features['even_ratio'] = 1 - features['odd_ratio']
        
        # 구간별 분포 (10구간)
        for section in range(5):
            start = section * 9 + 1
            end = (section + 1) * 9
            if section == 4:  # 마지막 구간
                end = 45
            section_count = sum(1 for n in numbers if start <= n <= end)
            features[f'section_{section}_ratio'] = section_count / 6
        
        # 소수 분포
        primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
        prime_count = sum(1 for n in numbers if n in primes)
        features['prime_ratio'] = prime_count / 6
        
        return features
    
    def _extract_pattern_features(self, numbers: List[int]) -> Dict[str, float]:
        """패턴 특징 추출"""
        features = {}
        sorted_nums = sorted(numbers)
        
        # 연속 번호 패턴
        consecutive_count = sum(1 for i in range(len(sorted_nums)-1) 
                              if sorted_nums[i+1] - sorted_nums[i] == 1)
        features['consecutive_ratio'] = consecutive_count / 5
        
        # 간격 패턴
        gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
        features['avg_gap'] = np.mean(gaps)
        features['std_gap'] = np.std(gaps)
        features['min_gap'] = min(gaps)
        features['max_gap'] = max(gaps)
        
        # 끝자리 패턴
        last_digits = [n % 10 for n in numbers]
        unique_last_digits = len(set(last_digits))
        features['unique_last_digits_ratio'] = unique_last_digits / 6
        
        # 십의 자리 패턴
        tens_digits = [n // 10 for n in numbers]
        unique_tens_digits = len(set(tens_digits))
        features['unique_tens_digits_ratio'] = unique_tens_digits / 6
        
        # 등차수열 패턴
        arithmetic_seq = self._check_arithmetic_sequence(sorted_nums)
        features['has_arithmetic_seq'] = float(arithmetic_seq)
        
        return features
    
    def _extract_temporal_features(self, numbers: List[int], 
                                 previous_numbers: List[str]) -> Dict[str, float]:
        """시간적 특징 추출"""
        features = {}
        
        # 사용 가능한 데이터 수 확인
        available_data = len(previous_numbers)
        
        # 최근 N회차와의 유사도
        for window in self.feature_config['window_sizes']:
            # 데이터가 부족한 경우 경고 및 스킵
            if available_data < window:
                if window == 50:  # 50개 window에 대해서만 경고
                    logging.warning(f"입력 데이터 부족: {available_data}개 (필요: {window}개)")
                continue
                
            recent = previous_numbers[-window:]
            
            if recent:
                # 평균 일치 개수
                match_counts = []
                for prev_str in recent:
                    prev_nums = set(int(n) for n in prev_str.split(','))
                    matches = len(set(numbers) & prev_nums)
                    match_counts.append(matches)
                
                features[f'avg_match_last_{window}'] = np.mean(match_counts)
                features[f'max_match_last_{window}'] = max(match_counts)
                
                # 번호별 출현 빈도
                recent_freq = {}
                for prev_str in recent:
                    for n in prev_str.split(','):
                        num = int(n)
                        recent_freq[num] = recent_freq.get(num, 0) + 1
                
                # 현재 번호들의 최근 출현 빈도
                current_freq = [recent_freq.get(n, 0) for n in numbers]
                features[f'avg_recent_freq_{window}'] = np.mean(current_freq)
                features[f'std_recent_freq_{window}'] = np.std(current_freq)
        
        return features
    
    def _extract_frequency_features(self, numbers: List[int], 
                                  number_frequency: Dict[int, float],
                                  current_round: int) -> Dict[str, float]:
        """빈도 기반 특징 추출"""
        features = {}
        
        # 전체 빈도
        frequencies = [number_frequency.get(n, 0) for n in numbers]
        features['avg_frequency'] = np.mean(frequencies)
        features['std_frequency'] = np.std(frequencies)
        features['min_frequency'] = min(frequencies)
        features['max_frequency'] = max(frequencies)
        
        # 정규화된 빈도
        if current_round > 0:
            norm_frequencies = [f / current_round for f in frequencies]
            features['avg_norm_frequency'] = np.mean(norm_frequencies)
            features['std_norm_frequency'] = np.std(norm_frequencies)
        
        # 빈도 순위
        freq_ranks = self._get_frequency_ranks(number_frequency)
        ranks = [freq_ranks.get(n, 45) for n in numbers]
        features['avg_freq_rank'] = np.mean(ranks)
        features['best_freq_rank'] = min(ranks)
        
        return features
    
    def _extract_correlation_features(self, numbers: List[int], 
                                    recent_numbers: List[str]) -> Dict[str, float]:
        """상관관계 특징 추출"""
        features = {}
        
        # 번호 쌍 출현 빈도
        pair_frequency = {}
        for nums_str in recent_numbers:
            nums = [int(n) for n in nums_str.split(',')]
            for i in range(len(nums)):
                for j in range(i+1, len(nums)):
                    pair = tuple(sorted([nums[i], nums[j]]))
                    pair_frequency[pair] = pair_frequency.get(pair, 0) + 1
        
        # 현재 번호 쌍들의 출현 빈도
        current_pairs = []
        for i in range(len(numbers)):
            for j in range(i+1, len(numbers)):
                pair = tuple(sorted([numbers[i], numbers[j]]))
                current_pairs.append(pair_frequency.get(pair, 0))
        
        if current_pairs:
            features['avg_pair_frequency'] = np.mean(current_pairs)
            features['max_pair_frequency'] = max(current_pairs)
            features['pair_frequency_std'] = np.std(current_pairs)
        
        return features
    
    def _calculate_frequency(self, winning_numbers: List[str]) -> Dict[int, float]:
        """번호별 출현 빈도 계산"""
        frequency = {}
        for nums_str in winning_numbers:
            for n in nums_str.split(','):
                num = int(n)
                frequency[num] = frequency.get(num, 0) + 1
        return frequency
    
    def _get_frequency_ranks(self, frequency: Dict[int, float]) -> Dict[int, int]:
        """빈도 기반 순위 계산"""
        sorted_nums = sorted(frequency.items(), key=lambda x: x[1], reverse=True)
        ranks = {}
        for rank, (num, _) in enumerate(sorted_nums, 1):
            ranks[num] = rank
        return ranks
    
    def _check_arithmetic_sequence(self, numbers: List[int]) -> bool:
        """등차수열 확인"""
        if len(numbers) < 3:
            return False
        
        diffs = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
        return len(set(diffs)) == 1
    
    def _safe_division(self, numerator: float, denominator: float, 
                      default: float = 0.0) -> float:
        """안전한 나눗셈 (0으로 나누기 방지)"""
        if abs(denominator) < 1e-10:
            return default
        return numerator / denominator
    
    def train(self, winning_numbers: List[str]) -> Dict[str, Any]:
        """모델 학습 (개선된 버전)"""
        if not SKLEARN_AVAILABLE:
            logging.error("scikit-learn이 설치되지 않았습니다.")
            return {}
        
        logging.info("개선된 앙상블 모델 학습 시작...")
        
        # 특징 추출
        features = self.extract_features(winning_numbers)
        
        # 타겟 생성 (다음 회차 예측)
        targets = self._create_targets(winning_numbers)
        
        # 데이터 정렬
        min_len = min(len(features), len(targets))
        features = features[:min_len]
        targets = targets[:min_len]
        
        # 학습/테스트 분할
        X_train, X_test, y_train, y_test = train_test_split(
            features, targets, test_size=0.2, random_state=42, shuffle=False
        )
        
        # 스케일링
        X_train_scaled = self.scalers['standard'].fit_transform(X_train)
        X_test_scaled = self.scalers['standard'].transform(X_test)
        
        # 각 번호별로 개별 모델 학습
        self._train_individual_models(X_train_scaled, y_train, X_test_scaled, y_test)
        
        # 모델 보정 (Calibration)
        self._calibrate_models(X_train_scaled, y_train)
        
        # 앙상블 가중치 최적화
        self._optimize_ensemble_weights(X_test_scaled, y_test)
        
        self.is_trained = True
        
        # 모델 저장
        self.save_models()
        
        # 평가
        evaluation = self.evaluate(X_test_scaled, y_test, features.columns)
        
        logging.info("개선된 앙상블 모델 학습 완료")
        return evaluation
    
    def _train_individual_models(self, X_train: np.ndarray, y_train: np.ndarray,
                               X_test: np.ndarray, y_test: np.ndarray):
        """개별 모델 학습"""
        for model_name, model in self.models.items():
            if model_name == 'xgb' and not XGBOOST_AVAILABLE:
                continue
                
            logging.info(f"{model_name} 모델 학습 중...")
            
            # 교차 검증
            cv_scores = []
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            
            # 각 번호별 학습
            for num_idx in range(45):
                y_binary = y_train[:, num_idx]
                
                # 클래스 불균형 처리
                if y_binary.sum() > 0:  # 양성 샘플이 있는 경우만
                    model_copy = self._clone_model(model_name)
                    
                    # 교차 검증
                    cv_score = cross_val_score(
                        model_copy, X_train, y_binary, 
                        cv=skf, scoring='f1'
                    ).mean()
                    cv_scores.append(cv_score)
                    
                    # 전체 데이터로 학습
                    model_copy.fit(X_train, y_binary)
                    
                    # 테스트 성능 평가
                    y_pred = model_copy.predict(X_test)
                    accuracy = accuracy_score(y_test[:, num_idx], y_pred)
                    f1 = f1_score(y_test[:, num_idx], y_pred, zero_division=0)
                    
                    # 성능 저장
                    self.model_performance[model_name]['accuracy'] += accuracy / 45
                    self.model_performance[model_name]['f1'] += f1 / 45
            
            logging.info(f"{model_name} CV F1 Score: {np.mean(cv_scores):.4f}")
    
    def _calibrate_models(self, X_train: np.ndarray, y_train: np.ndarray):
        """모델 확률 보정"""
        logging.info("모델 확률 보정 중...")
        
        for model_name, model in self.models.items():
            if model_name == 'xgb' and not XGBOOST_AVAILABLE:
                continue
                
            # Platt 스케일링 또는 Isotonic 회귀를 사용한 보정
            calibrated = CalibratedClassifierCV(
                model, method='sigmoid', cv=3
            )
            
            # 전체 번호에 대한 평균 타겟으로 학습
            y_avg = y_train.mean(axis=1) > 0.1  # 임계값
            calibrated.fit(X_train, y_avg)
            
            self.calibrated_models[model_name] = calibrated
    
    def _optimize_ensemble_weights(self, X_test: np.ndarray, y_test: np.ndarray):
        """앙상블 가중치 최적화"""
        logging.info("앙상블 가중치 최적화 중...")
        
        # 각 모델의 성능 기반 가중치 조정
        total_f1 = sum(perf['f1'] for perf in self.model_performance.values())
        
        if total_f1 > 0:
            for model_name, perf in self.model_performance.items():
                self.ensemble_weights[model_name] = perf['f1'] / total_f1
        
        # 가중치 정규화
        total_weight = sum(self.ensemble_weights.values())
        for model_name in self.ensemble_weights:
            self.ensemble_weights[model_name] /= total_weight
        
        logging.info(f"최적화된 앙상블 가중치: {self.ensemble_weights}")
    
    def predict_probability(self, features: np.ndarray) -> np.ndarray:
        """개선된 앙상블 예측 (확률)"""
        if not self.is_trained:
            logging.warning("모델이 학습되지 않았습니다.")
            return np.ones(45) / 45
        
        # 스케일링
        if hasattr(self.scalers['standard'], 'mean_'):
            features_scaled = self.scalers['standard'].transform(features)
        else:
            features_scaled = features
        
        # 각 모델의 예측
        predictions = {}
        
        for model_name in self.models:
            if model_name == 'xgb' and not XGBOOST_AVAILABLE:
                continue
                
            # 보정된 모델 사용 (있는 경우)
            if model_name in self.calibrated_models:
                pred = self.calibrated_models[model_name].predict_proba(features_scaled)
                if pred.shape[1] == 2:  # 이진 분류
                    predictions[model_name] = pred[:, 1].reshape(-1, 1)
                else:
                    predictions[model_name] = pred
            else:
                # 기본 모델 사용
                model = self.models[model_name]
                if hasattr(model, 'predict_proba'):
                    pred = model.predict_proba(features_scaled)
                    if pred.shape[1] == 2:
                        predictions[model_name] = pred[:, 1].reshape(-1, 1)
                    else:
                        predictions[model_name] = pred
        
        # 가중 평균 앙상블
        ensemble_pred = np.zeros((features.shape[0], 45))
        
        for model_name, pred in predictions.items():
            weight = self.ensemble_weights.get(model_name, 0)
            # 예측 차원 맞추기
            if pred.shape[1] == 1:
                # 단일 출력을 45개로 복제 (임시)
                pred_expanded = np.tile(pred, (1, 45))
                ensemble_pred += pred_expanded * weight
            else:
                ensemble_pred += pred * weight
        
        # 확률 안정화 (언더플로우 방지)
        ensemble_pred = self._stabilize_probabilities(ensemble_pred)
        
        return ensemble_pred
    
    def _stabilize_probabilities(self, probabilities: np.ndarray) -> np.ndarray:
        """확률 안정화 (언더플로우/오버플로우 방지)"""
        # 최소/최대 클리핑
        probabilities = np.clip(
            probabilities, 
            self.stability_config['min_probability'],
            self.stability_config['max_probability']
        )
        
        # 라플라스 스무딩
        alpha = self.stability_config['smoothing_alpha']
        probabilities = (probabilities + alpha) / (1 + alpha * probabilities.shape[1])
        
        # 온도 스케일링
        temperature = self.stability_config['temperature']
        if temperature != 1.0:
            # 로그 공간에서 작업 (안정성)
            log_probs = np.log(probabilities + 1e-10)
            log_probs = log_probs / temperature
            # Softmax
            exp_probs = np.exp(log_probs - np.max(log_probs, axis=1, keepdims=True))
            probabilities = exp_probs / np.sum(exp_probs, axis=1, keepdims=True)
        
        # 정규화
        row_sums = probabilities.sum(axis=1, keepdims=True)
        probabilities = probabilities / (row_sums + 1e-10)
        
        return probabilities
    
    def predict_next_numbers(self, winning_numbers: List[str], 
                           num_predictions: int = 10) -> List[Dict[str, Any]]:
        """다음 회차 번호 예측 (개선된 버전)"""
        # 특징 추출
        features = self.extract_features(winning_numbers)
        
        # 최신 데이터 사용
        latest_features = features.iloc[-1:].values
        
        # 예측
        probabilities = self.predict_probability(latest_features)[0]
        
        # 번호 조합 생성 (다양한 전략 사용)
        predictions = []
        strategies = [
            ('weighted_sampling', 0.4),
            ('top_k', 0.3),
            ('balanced', 0.3)
        ]
        
        for strategy, ratio in strategies:
            n_preds = int(num_predictions * ratio)
            
            if strategy == 'weighted_sampling':
                # 확률 기반 가중 샘플링
                preds = self._weighted_sampling_prediction(probabilities, n_preds)
            elif strategy == 'top_k':
                # 상위 K개 선택
                preds = self._top_k_prediction(probabilities, n_preds)
            else:
                # 균형잡힌 선택
                preds = self._balanced_prediction(probabilities, n_preds)
            
            predictions.extend(preds)
        
        # 중복 제거 및 정렬
        unique_predictions = []
        seen = set()
        
        for pred in predictions:
            nums_tuple = tuple(pred['numbers'])
            if nums_tuple not in seen:
                seen.add(nums_tuple)
                unique_predictions.append(pred)
        
        # 신뢰도 순으로 정렬
        unique_predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return unique_predictions[:num_predictions]
    
    def _weighted_sampling_prediction(self, probabilities: np.ndarray, 
                                    n_predictions: int) -> List[Dict[str, Any]]:
        """가중 샘플링 예측"""
        predictions = []
        
        # 확률에 대한 비선형 변환 (상위 확률 강조)
        weights = probabilities ** 2
        weights = weights / weights.sum()
        
        for _ in range(n_predictions):
            # 중복 없이 6개 선택
            selected_indices = np.random.choice(
                45, 6, replace=False, p=weights
            )
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            # 신뢰도 계산
            confidence = float(np.mean([probabilities[i] for i in selected_indices]))
            
            # 개별 확률도 포함
            individual_probs = {
                num: float(probabilities[num-1]) 
                for num in selected_numbers
            }
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': confidence,
                'strategy': 'weighted_sampling',
                'individual_probabilities': individual_probs
            })
        
        return predictions
    
    def _top_k_prediction(self, probabilities: np.ndarray, 
                         n_predictions: int) -> List[Dict[str, Any]]:
        """상위 K개 예측"""
        predictions = []
        
        # 상위 15개 번호 선택
        top_15_indices = np.argsort(probabilities)[-15:]
        
        for _ in range(n_predictions):
            # 상위 15개 중 랜덤하게 6개 선택
            selected_indices = np.random.choice(top_15_indices, 6, replace=False)
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            confidence = float(np.mean([probabilities[i] for i in selected_indices]))
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': confidence,
                'strategy': 'top_k'
            })
        
        return predictions
    
    def _balanced_prediction(self, probabilities: np.ndarray, 
                           n_predictions: int) -> List[Dict[str, Any]]:
        """균형잡힌 예측"""
        predictions = []
        
        # 구간별로 번호 선택
        sections = [
            (0, 9), (9, 18), (18, 27), (27, 36), (36, 45)
        ]
        
        for _ in range(n_predictions):
            selected_numbers = []
            
            # 각 구간에서 1-2개씩 선택
            for start, end in sections:
                section_probs = probabilities[start:end]
                n_select = np.random.choice([1, 2], p=[0.6, 0.4])
                
                if n_select <= end - start:
                    indices = np.random.choice(
                        range(start, end), 
                        n_select, 
                        replace=False,
                        p=section_probs / section_probs.sum()
                    )
                    selected_numbers.extend([i + 1 for i in indices])
            
            # 6개로 조정
            if len(selected_numbers) > 6:
                # 확률 기반으로 6개 선택
                probs = [probabilities[n-1] for n in selected_numbers]
                probs = np.array(probs) / sum(probs)
                indices = np.random.choice(
                    len(selected_numbers), 6, replace=False, p=probs
                )
                selected_numbers = [selected_numbers[i] for i in indices]
            elif len(selected_numbers) < 6:
                # 부족한 만큼 추가
                remaining = list(set(range(1, 46)) - set(selected_numbers))
                remaining_probs = [probabilities[n-1] for n in remaining]
                remaining_probs = np.array(remaining_probs) / sum(remaining_probs)
                
                additional = np.random.choice(
                    remaining, 
                    6 - len(selected_numbers), 
                    replace=False,
                    p=remaining_probs
                )
                selected_numbers.extend(additional)
            
            selected_numbers = sorted(selected_numbers)
            confidence = float(np.mean([probabilities[n-1] for n in selected_numbers]))
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': confidence,
                'strategy': 'balanced'
            })
        
        return predictions
    
    def _create_targets(self, winning_numbers: List[str]) -> np.ndarray:
        """타겟 생성 (개선된 버전)"""
        targets = []
        
        for i in range(len(winning_numbers) - 1):
            # 다음 회차 번호
            next_numbers = [int(n) for n in winning_numbers[i + 1].split(',')]
            
            # 원-핫 인코딩
            target = np.zeros(45)
            for num in next_numbers:
                target[num - 1] = 1
            
            targets.append(target)
        
        return np.array(targets)
    
    def _clone_model(self, model_name: str):
        """모델 복제"""
        if model_name == 'rf':
            return self._build_random_forest()
        elif model_name == 'gb':
            return self._build_gradient_boosting()
        elif model_name == 'xgb':
            return self._build_xgboost()
        elif model_name == 'nn':
            return self._build_neural_network()
    
    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray, 
                feature_names: List[str]) -> Dict[str, Any]:
        """모델 평가 (개선된 버전)"""
        evaluation = {
            'models': self.model_performance,
            'ensemble': {},
            'feature_importance': {},
            'prediction_quality': {}
        }
        
        # 앙상블 예측
        ensemble_pred = self.predict_probability(X_test)
        
        # 다양한 평가 메트릭
        evaluation['ensemble'] = self._calculate_evaluation_metrics(
            ensemble_pred, y_test
        )
        
        # 예측 품질 평가
        evaluation['prediction_quality'] = self._evaluate_prediction_quality(
            ensemble_pred, y_test
        )
        
        # 특징 중요도 (Random Forest 기준)
        if 'rf' in self.models and hasattr(self.models['rf'], 'feature_importances_'):
            importance = self.models['rf'].feature_importances_
            importance_df = pd.DataFrame({
                'feature': feature_names,
                'importance': importance
            }).sort_values('importance', ascending=False)
            
            evaluation['feature_importance'] = importance_df.head(20).to_dict('records')
        
        return evaluation
    
    def _calculate_evaluation_metrics(self, predictions: np.ndarray, 
                                    targets: np.ndarray) -> Dict[str, float]:
        """평가 메트릭 계산"""
        metrics = {}
        
        # 임계값 기반 이진 예측
        threshold = 0.13  # 6/45
        binary_pred = (predictions > threshold).astype(int)
        
        # 전체 정확도
        metrics['accuracy'] = accuracy_score(
            targets.flatten(), binary_pred.flatten()
        )
        
        # 정밀도, 재현율, F1
        metrics['precision'] = precision_score(
            targets.flatten(), binary_pred.flatten(), zero_division=0
        )
        metrics['recall'] = recall_score(
            targets.flatten(), binary_pred.flatten(), zero_division=0
        )
        metrics['f1'] = f1_score(
            targets.flatten(), binary_pred.flatten(), zero_division=0
        )
        
        # 번호별 일치 평가
        match_counts = []
        for i in range(len(targets)):
            # 상위 6개 예측
            top_6 = np.argsort(predictions[i])[-6:]
            actual = np.where(targets[i] == 1)[0]
            
            # 일치 개수
            matches = len(set(top_6) & set(actual))
            match_counts.append(matches)
        
        metrics['avg_matches'] = float(np.mean(match_counts))
        metrics['match_distribution'] = {
            str(i): match_counts.count(i) for i in range(7)
        }
        
        # 3개 이상 맞춘 비율 (5등 이상)
        metrics['win_rate'] = float(sum(1 for m in match_counts if m >= 3) / len(match_counts))
        
        return metrics
    
    def _evaluate_prediction_quality(self, predictions: np.ndarray, 
                                   targets: np.ndarray) -> Dict[str, float]:
        """예측 품질 평가"""
        quality = {}
        
        # 확률 분포 평가
        avg_entropy = -np.mean(
            predictions * np.log(predictions + 1e-10) + 
            (1 - predictions) * np.log(1 - predictions + 1e-10)
        )
        quality['avg_entropy'] = float(avg_entropy)
        
        # 확률 분산
        quality['prob_variance'] = float(np.var(predictions))
        
        # 상위 확률과 하위 확률의 비율
        top_probs = np.sort(predictions, axis=1)[:, -6:].mean()
        bottom_probs = np.sort(predictions, axis=1)[:, :39].mean()
        quality['top_bottom_ratio'] = float(top_probs / (bottom_probs + 1e-10))
        
        # 예측 다양성
        unique_predictions = set()
        for pred in predictions:
            top_6 = tuple(np.argsort(pred)[-6:])
            unique_predictions.add(top_6)
        
        quality['prediction_diversity'] = len(unique_predictions) / len(predictions)
        
        return quality
    
    def save_models(self):
        """모델 저장 (개선된 버전)"""
        # 모델 저장
        for model_name, model in self.models.items():
            if model_name == 'xgb' and not XGBOOST_AVAILABLE:
                continue
            model_path = os.path.join(self.model_dir, f'{model_name}.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
        
        # 보정된 모델 저장
        if self.calibrated_models:
            calibrated_path = os.path.join(self.model_dir, 'calibrated_models.pkl')
            with open(calibrated_path, 'wb') as f:
                pickle.dump(self.calibrated_models, f)
        
        # 스케일러 저장
        scaler_path = os.path.join(self.model_dir, 'scalers.pkl')
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scalers, f)
        
        # 설정 및 성능 저장
        config_path = os.path.join(self.model_dir, 'config.json')
        config = {
            'feature_config': self.feature_config,
            'stability_config': self.stability_config,
            'ensemble_weights': self.ensemble_weights,
            'model_performance': self.model_performance,
            'is_trained': self.is_trained,
            'training_date': datetime.now().isoformat()
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logging.info(f"모델 저장 완료: {self.model_dir}")
    
    def _load_saved_models(self):
        """저장된 모델 로드"""
        try:
            # 설정 로드
            config_path = os.path.join(self.model_dir, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                self.feature_config.update(config.get('feature_config', {}))
                self.stability_config.update(config.get('stability_config', {}))
                self.ensemble_weights.update(config.get('ensemble_weights', {}))
                self.model_performance.update(config.get('model_performance', {}))
                self.is_trained = config.get('is_trained', False)
            
            # 모델 로드
            for model_name in ['rf', 'gb', 'xgb', 'nn']:
                model_path = os.path.join(self.model_dir, f'{model_name}.pkl')
                if os.path.exists(model_path):
                    with open(model_path, 'rb') as f:
                        self.models[model_name] = pickle.load(f)
            
            # 보정된 모델 로드
            calibrated_path = os.path.join(self.model_dir, 'calibrated_models.pkl')
            if os.path.exists(calibrated_path):
                with open(calibrated_path, 'rb') as f:
                    self.calibrated_models = pickle.load(f)
            
            # 스케일러 로드
            scaler_path = os.path.join(self.model_dir, 'scalers.pkl')
            if os.path.exists(scaler_path):
                with open(scaler_path, 'rb') as f:
                    self.scalers = pickle.load(f)
            
            if self.is_trained:
                logging.info("저장된 모델 로드 완료")
                
        except Exception as e:
            logging.warning(f"모델 로드 실패: {str(e)}")


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    from src.core.db_manager import DatabaseManager
    
    # 데이터베이스에서 당첨번호 로드
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    
    if len(winning_numbers) < 100:
        print(f"데이터 부족: {len(winning_numbers)}개 (최소 100개 필요)")
        return
    
    # 개선된 앙상블 예측기 생성
    predictor = ImprovedEnsemblePredictor()
    
    # 모델 학습 (저장된 모델이 없거나 재학습이 필요한 경우)
    if not predictor.is_trained or '--retrain' in sys.argv:
        print("모델 학습 중...")
        evaluation = predictor.train(winning_numbers[:-10])  # 최근 10개는 평가용
        
        print("\n모델 평가 결과:")
        print(f"- 앙상블 정확도: {evaluation['ensemble']['accuracy']:.4f}")
        print(f"- 평균 일치 개수: {evaluation['ensemble']['avg_matches']:.2f}")
        print(f"- 당첨 확률 (3개 이상): {evaluation['ensemble']['win_rate']:.2%}")
        
        print("\n일치 개수 분포:")
        for matches, count in evaluation['ensemble']['match_distribution'].items():
            print(f"  {matches}개 일치: {count}회")
    
    # 다음 회차 예측
    print("\n다음 회차 번호 예측:")
    predictions = predictor.predict_next_numbers(winning_numbers, num_predictions=5)
    
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred['confidence']
        strategy = pred.get('strategy', 'unknown')
        
        print(f"\n예측 {i} ({strategy}): {numbers}")
        print(f"  신뢰도: {confidence:.4f}")
        
        if 'individual_probabilities' in pred:
            print("  개별 확률:")
            for num, prob in pred['individual_probabilities'].items():
                print(f"    {num}: {prob:.4f}")
    
    # 앙상블 가중치 출력
    print(f"\n앙상블 가중치: {predictor.ensemble_weights}")
    
    # 상위 특징 출력
    if predictor.is_trained:
        print("\n중요한 특징 (상위 10개):")
        # 특징 중요도는 평가 결과에서 가져옴
        print("(모델 평가 시 확인 가능)")


if __name__ == "__main__":
    main()