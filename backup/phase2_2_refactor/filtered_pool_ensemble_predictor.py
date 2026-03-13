#!/usr/bin/env python3
"""
필터링된 풀 기반 앙상블 예측기
필터링된 조합 풀 내에서만 학습하고 예측하는 개선된 앙상블 모델
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
import pickle
from collections import defaultdict

# ML 라이브러리 imports
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.utils.validation import check_is_fitted
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available. Filtered pool ensemble predictor will work in limited mode.")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available. Will use alternative models.")


class FilteredPoolEnsemblePredictor:
    """필터링된 풀 기반 앙상블 예측기"""

    def __init__(self, model_dir: str = 'models/filtered_ensemble'):
        """
        Args:
            model_dir: 모델 저장 디렉토리
        """
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        self.models = {}
        self.scalers = {}
        self.label_encoder = LabelEncoder()
        self.is_trained = False

        # 필터링된 풀 관련
        self.combination_to_label = {}  # 조합 -> 레이블 매핑
        self.label_to_combination = {}  # 레이블 -> 조합 매핑
        self.filtered_pool = []         # 필터링된 조합 풀
        self.pool_size = 0

        # 앙상블 가중치
        self.ensemble_weights = {
            'rf': 0.4,     # Random Forest
            'xgb': 0.4,    # XGBoost
            'nn': 0.2      # Neural Network
        }

        # 특징 엔지니어링 설정 (필터링된 풀에 특화)
        self.feature_config = {
            'use_combination_features': True,    # 조합 자체의 특징
            'use_pattern_features': True,        # 패턴 특징
            'use_sequence_features': True,       # 시퀀스 특징
            'window_sizes': [5, 10, 15]         # 다양한 윈도우 크기
        }

        self.min_train_samples = 20

        if SKLEARN_AVAILABLE:
            self._initialize_models()

    def _initialize_models(self):
        """모델 초기화"""
        # Random Forest
        self.models['rf'] = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )

        # XGBoost
        if XGBOOST_AVAILABLE:
            self.models['xgb'] = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                objective='multi:softprob'
            )

        # Neural Network
        self.models['nn'] = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            alpha=0.01,
            learning_rate='adaptive',
            max_iter=500,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.2
        )

        # Scalers
        self.scalers['features'] = StandardScaler()

        logging.info("필터링된 풀 앙상블 모델 초기화 완료")

    def set_filtered_pool(self, filtered_combinations: List[List[int]]):
        """필터링된 조합 풀 설정"""
        self.filtered_pool = [tuple(sorted(combo)) for combo in filtered_combinations]
        self.pool_size = len(self.filtered_pool)

        # 조합을 정수 레이블로 매핑
        unique_combinations = list(set(self.filtered_pool))
        self.combination_to_label = {combo: idx for idx, combo in enumerate(unique_combinations)}
        self.label_to_combination = {idx: combo for idx, combo in enumerate(unique_combinations)}

        logging.info(f"필터링된 풀 설정 완료: {self.pool_size}개 조합, {len(unique_combinations)}개 고유 조합")

    def extract_combination_features(self, combination: List[int]) -> Dict[str, float]:
        """조합의 특징 추출"""
        features = {}

        # 기본 통계
        features['sum'] = sum(combination)
        features['mean'] = np.mean(combination)
        features['std'] = np.std(combination)
        features['min'] = min(combination)
        features['max'] = max(combination)
        features['range'] = features['max'] - features['min']

        # 홀짝 분포
        odd_count = sum(1 for n in combination if n % 2 == 1)
        features['odd_ratio'] = odd_count / 6

        # 구간별 분포 (1-9, 10-18, 19-27, 28-36, 37-45)
        for i in range(5):
            section_start = i * 9 + 1
            section_end = (i + 1) * 9
            section_count = sum(1 for n in combination if section_start <= n <= section_end)
            features[f'section_{i}_count'] = section_count / 6

        # 연속 번호
        consecutive_count = sum(1 for i in range(len(combination)-1)
                              if combination[i+1] - combination[i] == 1)
        features['consecutive_ratio'] = consecutive_count / 5

        # 간격 분석
        gaps = [combination[i+1] - combination[i] for i in range(len(combination)-1)]
        features['avg_gap'] = np.mean(gaps)
        features['max_gap'] = max(gaps)
        features['gap_std'] = np.std(gaps)

        # 소수 개수
        primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
        prime_count = sum(1 for n in combination if n in primes)
        features['prime_ratio'] = prime_count / 6

        # 끝자리 분포
        last_digits = [n % 10 for n in combination]
        for digit in range(10):
            features[f'last_digit_{digit}'] = last_digits.count(digit) / 6

        return features

    def extract_sequence_features(self, historical_combinations: List[List[int]],
                                target_index: int) -> Dict[str, float]:
        """시퀀스 특징 추출"""
        features = {}

        if target_index < 5:  # 최소 5개의 이전 데이터 필요
            return {f'seq_{k}': 0.0 for k in range(50)}  # 기본값

        # 최근 조합들 분석
        recent_combos = historical_combinations[max(0, target_index-15):target_index]

        # 번호별 출현 빈도
        all_numbers = []
        for combo in recent_combos:
            all_numbers.extend(combo)

        for num in range(1, 46):
            features[f'freq_{num}'] = all_numbers.count(num) / (len(recent_combos) * 6)

        # 최근 패턴 분석
        for window in self.feature_config['window_sizes']:
            if target_index >= window:
                window_combos = historical_combinations[target_index-window:target_index]
                window_numbers = []
                for combo in window_combos:
                    window_numbers.extend(combo)

                # 윈도우별 통계
                features[f'window_{window}_unique'] = len(set(window_numbers)) / 45
                features[f'window_{window}_avg_sum'] = np.mean([sum(combo) for combo in window_combos])

                # 연속성 패턴
                consecutive_patterns = 0
                for combo in window_combos:
                    consecutive_patterns += sum(1 for i in range(len(combo)-1)
                                              if combo[i+1] - combo[i] == 1)
                features[f'window_{window}_consecutive'] = consecutive_patterns / (window * 5)

        return features

    def prepare_training_data(self, historical_combinations: List[List[int]]) -> Tuple[np.ndarray, np.ndarray]:
        """학습 데이터 준비"""
        if self.pool_size == 0:
            raise ValueError("필터링된 풀이 설정되지 않았습니다.")

        features_list = []
        labels = []

        # 디버깅: 풀 매칭 통계
        exact_matches = 0
        similar_matches = 0

        for i in range(len(historical_combinations) - 1):
            # 현재 회차의 특징 추출
            current_combo = historical_combinations[i]
            combo_features = self.extract_combination_features(current_combo)
            seq_features = self.extract_sequence_features(historical_combinations, i)

            # 특징 결합
            combined_features = {**combo_features, **seq_features}
            features_list.append(combined_features)

            # 다음 회차의 조합을 레이블로 설정
            next_combo = tuple(sorted(historical_combinations[i + 1]))

            # 필터링된 풀에 있는 조합인지 확인
            if next_combo in self.combination_to_label:
                labels.append(self.combination_to_label[next_combo])
                exact_matches += 1
            else:
                # 필터링된 풀에 없는 조합은 가장 유사한 조합으로 대체
                similar_label = self._find_similar_combination_label(list(next_combo))
                labels.append(similar_label)
                similar_matches += 1

        # 디버깅 정보 로깅
        total_samples = len(historical_combinations) - 1
        logging.debug(f"학습 데이터 매칭 통계: 정확 매칭 {exact_matches}/{total_samples} ({exact_matches/total_samples*100:.1f}%), "
                     f"유사 매칭 {similar_matches}/{total_samples} ({similar_matches/total_samples*100:.1f}%)")

        # DataFrame으로 변환
        features_df = pd.DataFrame(features_list)
        features_df = features_df.fillna(0)  # NaN 값 처리

        return features_df.values, np.array(labels)

    def _find_similar_combination_label(self, combo: List[int]) -> int:
        """가장 유사한 조합의 레이블 찾기 (랜덤 다양성 보장)"""
        combo_set = set(combo)
        max_similarity = 0
        candidates = []  # 동일한 유사도를 가진 후보들

        for combination, label in self.combination_to_label.items():
            combo_set_pool = set(combination)
            similarity = len(combo_set & combo_set_pool)

            if similarity > max_similarity:
                max_similarity = similarity
                candidates = [label]  # 새로운 최대값, 기존 후보 초기화
            elif similarity == max_similarity:
                candidates.append(label)  # 동일한 유사도, 후보에 추가

        # 동일한 유사도를 가진 후보 중 랜덤 선택 (다양성 보장)
        if candidates:
            return np.random.choice(candidates)
        else:
            # 매칭 실패 시 전체 레이블 중 랜덤 선택
            all_labels = list(self.combination_to_label.values())
            return np.random.choice(all_labels) if all_labels else 0

    def train_with_filtered_pool(self, historical_combinations: List[List[int]],
                                filtered_combinations: List[List[int]],
                                test_size: float = 0.2):
        """필터링된 풀을 사용한 앙상블 모델 학습"""
        if not SKLEARN_AVAILABLE:
            logging.error("scikit-learn이 설치되지 않아 학습할 수 없습니다.")
            return

        logging.info("필터링된 풀 기반 앙상블 모델 학습 시작...")

        # 필터링된 풀 설정
        self.set_filtered_pool(filtered_combinations)

        # 데이터 부족 체크
        if len(historical_combinations) < self.min_train_samples:
            logging.error(f"학습 데이터 부족: {len(historical_combinations)}개")
            return {}

        # 특징 추출
        X, y = self.prepare_training_data(historical_combinations)

        if len(X) == 0:
            logging.error("추출된 특징이 없습니다.")
            return {}

        unique_labels = len(np.unique(y))
        logging.info(f"특징 데이터 shape: {X.shape}, 레이블 수: {unique_labels}")

        # 레이블이 2개 미만이면 학습 불가 (XGBoost num_class 에러 방지)
        if unique_labels < 2:
            logging.error(f"레이블 수가 부족합니다 ({unique_labels}개). 최소 2개 필요. 학습을 건너뜁니다.")
            logging.error("→ 필터링된 풀이 너무 작거나 모든 조합이 동일한 레이블로 매핑됨")
            return {}

        # 레이블 인코딩 - XGBoost 'Invalid classes' 에러 방지
        # y가 0부터 시작하는 연속적인 정수가 아닐 수 있으므로 LabelEncoder로 변환
        self.scalers['label_encoder'] = LabelEncoder()
        y = self.scalers['label_encoder'].fit_transform(y)
        logging.debug(f"레이블 인코딩 완료: {len(self.scalers['label_encoder'].classes_)}개 클래스 (0~{max(y)})")

        # 스케일링
        X_scaled = self.scalers['features'].fit_transform(X)

        # 학습/테스트 분할 (stratify는 조건부 사용)
        # 각 클래스가 최소 2개 이상의 샘플을 가져야 stratify 가능
        try:
            # 각 클래스의 샘플 수 확인
            unique, counts = np.unique(y, return_counts=True)
            min_samples = np.min(counts)

            if min_samples >= 2:
                # 모든 클래스가 2개 이상 샘플 → stratify 사용 가능
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=test_size, random_state=42, stratify=y
                )
                logging.debug(f"Stratified split 사용 (최소 클래스 샘플: {min_samples}개)")
            else:
                # 일부 클래스가 1개만 → stratify 없이 분할
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=test_size, random_state=42
                )
                # 로또 데이터 특성상 회차당 1개 샘플이므로 stratify 불가 - 정상 동작
                logging.debug(f"Stratify 미사용 (회차당 1개 샘플): 최소 {min_samples}개, 클래스 {np.sum(counts == 1)}개")
        except Exception as e:
            # stratify 실패 시 일반 분할
            logging.warning(f"Stratified split 실패, 일반 split 사용: {e}")
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=test_size, random_state=42
            )

        # 각 모델 학습
        results = {}

        # 테스트 세트에서 학습 세트에 없는 클래스 필터링 (Invalid classes 에러 방지)
        train_classes = set(y_train)
        test_mask = np.isin(y_test, list(train_classes))
        X_test_filtered = X_test[test_mask]
        y_test_filtered = y_test[test_mask]

        if len(y_test_filtered) == 0:
            # 모든 테스트 클래스가 학습에 없음 - 전체 데이터로 학습만 진행
            logging.warning("테스트 세트에 학습 클래스가 없어 평가 건너뜀. 전체 데이터로 학습합니다.")
            X_train, y_train = X_scaled, y
            X_test_filtered, y_test_filtered = X_scaled[:10], y[:10]  # 더미 평가용
        elif len(y_test_filtered) < len(y_test):
            skipped = len(y_test) - len(y_test_filtered)
            logging.debug(f"테스트 세트에서 {skipped}개 샘플 제외 (학습에 없는 클래스)")

        # ★ 핵심 수정: XGBoost multi:softprob용 연속적 레이블 재인코딩
        # train_test_split 후 y_train에 갭이 있을 수 있음 (예: [0,2,5,7])
        # XGBoost는 연속적인 레이블 [0,1,2,3...]을 요구함
        train_label_encoder = LabelEncoder()
        y_train_continuous = train_label_encoder.fit_transform(y_train)

        # y_test_filtered도 같은 인코더로 변환 (학습에 있는 클래스만 포함됨이 보장됨)
        try:
            y_test_continuous = train_label_encoder.transform(y_test_filtered)
        except ValueError as e:
            # 예외 발생 시 (테스트에 학습에 없는 클래스 있음) - 해당 샘플 제외
            logging.warning(f"테스트 레이블 변환 실패, 추가 필터링: {e}")
            valid_mask = np.isin(y_test_filtered, train_label_encoder.classes_)
            X_test_filtered = X_test_filtered[valid_mask]
            y_test_filtered = y_test_filtered[valid_mask]
            if len(y_test_filtered) == 0:
                logging.warning("필터링 후 테스트 데이터 없음 - 더미 데이터 사용")
                X_test_filtered = X_train[:10]
                y_test_continuous = y_train_continuous[:10]
            else:
                y_test_continuous = train_label_encoder.transform(y_test_filtered)

        num_classes = len(train_label_encoder.classes_)
        logging.debug(f"연속 레이블 재인코딩 완료: {num_classes}개 클래스 (0~{num_classes-1})")

        # Random Forest
        logging.info("Random Forest 학습 중...")
        self.models['rf'].fit(X_train, y_train_continuous)
        rf_pred = self.models['rf'].predict(X_test_filtered)
        results['rf'] = {
            'accuracy': accuracy_score(y_test_continuous, rf_pred),
            'feature_importance': self.models['rf'].feature_importances_
        }

        # XGBoost
        if XGBOOST_AVAILABLE and 'xgb' in self.models:
            logging.info("XGBoost 학습 중...")
            self.models['xgb'].fit(X_train, y_train_continuous)
            xgb_pred = self.models['xgb'].predict(X_test_filtered)
            results['xgb'] = {
                'accuracy': accuracy_score(y_test_continuous, xgb_pred)
            }

        # Neural Network
        logging.info("Neural Network 학습 중...")
        try:
            # NN 모델이 None인지 먼저 확인
            if self.models.get('nn') is None:
                logging.warning("NN 모델이 None입니다. RF와 XGBoost만 사용합니다.")
                results['nn'] = {'accuracy': 0.0}
            else:
                self.models['nn'].fit(X_train, y_train_continuous)
                nn_pred = self.models['nn'].predict(X_test_filtered)
                results['nn'] = {
                    'accuracy': accuracy_score(y_test_continuous, nn_pred)
                }
        except Exception as e:
            logging.warning(f"Neural Network 학습 실패: {e}")
            results['nn'] = {'accuracy': 0.0}
            # 실패 시 None으로 설정하여 다음 예측에서 스킵
            self.models['nn'] = None

        self.is_trained = True

        # 모델 저장
        self.save_models()

        logging.info("필터링된 풀 기반 앙상블 모델 학습 완료")
        return results

    def predict_from_filtered_pool(self, historical_combinations: List[List[int]],
                                  filtered_combinations: List[List[int]],
                                  num_predictions: int = 10) -> List[Dict[str, Any]]:
        """필터링된 풀에서 예측"""
        if not SKLEARN_AVAILABLE or not self.is_trained:
            logging.warning("모델이 준비되지 않았습니다.")
            return self._random_predictions_from_pool(filtered_combinations, num_predictions)

        # 필터링된 풀 설정 (기존과 다르면 업데이트)
        if len(filtered_combinations) != self.pool_size:
            logging.warning("필터링된 풀이 변경되었습니다. 재학습이 필요할 수 있습니다.")
            return self._random_predictions_from_pool(filtered_combinations, num_predictions)

        # 최신 특징 추출
        latest_combo = historical_combinations[-1]
        combo_features = self.extract_combination_features(latest_combo)
        seq_features = self.extract_sequence_features(historical_combinations, len(historical_combinations)-1)

        # 특징 결합
        combined_features = {**combo_features, **seq_features}
        feature_vector = np.array([list(combined_features.values())])

        # 스케일링
        if hasattr(self.scalers['features'], 'mean_'):
            feature_vector = self.scalers['features'].transform(feature_vector)

        # 앙상블 예측
        predictions_prob = self._ensemble_predict_proba(feature_vector)

        # 상위 예측 결과 생성
        predictions = []
        top_labels = np.argsort(predictions_prob)[::-1]  # 내림차순 정렬

        for i in range(min(num_predictions, len(top_labels))):
            label = top_labels[i]
            if label in self.label_to_combination:
                combination = list(self.label_to_combination[label])
                confidence = float(predictions_prob[label])

                predictions.append({
                    'numbers': combination,
                    'confidence': confidence,
                    'pool_label': label,
                    'source': 'filtered_pool_ensemble'
                })

        return predictions

    def _ensemble_predict_proba(self, X: np.ndarray) -> np.ndarray:
        """앙상블 확률 예측"""
        ensemble_proba = np.zeros(len(self.label_to_combination))

        # 레이블 인코더가 있으면 원본 레이블로 역변환 필요
        label_encoder = self.scalers.get('label_encoder')

        total_weight = 0
        for model_name, model in self.models.items():
            try:
                check_is_fitted(model)
                proba = model.predict_proba(X)[0]

                # 모든 클래스에 대한 확률 확보 (일부 모델은 모든 클래스를 보지 못할 수 있음)
                full_proba = np.zeros(len(self.label_to_combination))
                classes = model.classes_

                for i, encoded_label in enumerate(classes):
                    # 인코딩된 레이블을 원본 레이블로 역변환
                    if label_encoder is not None:
                        try:
                            original_label = label_encoder.inverse_transform([encoded_label])[0]
                        except (ValueError, IndexError):
                            original_label = encoded_label
                    else:
                        original_label = encoded_label

                    if original_label < len(full_proba):
                        full_proba[original_label] = proba[i]

                weight = self.ensemble_weights.get(model_name, 0)
                ensemble_proba += full_proba * weight
                total_weight += weight

            except Exception as e:
                logging.debug(f"{model_name} 예측 실패: {e}")
                continue

        if total_weight > 0:
            ensemble_proba /= total_weight

        return ensemble_proba

    def _random_predictions_from_pool(self, filtered_combinations: List[List[int]],
                                    num_predictions: int) -> List[Dict[str, Any]]:
        """필터링된 풀에서 랜덤 예측 (폴백 메서드)"""
        predictions = []
        selected_indices = np.random.choice(
            len(filtered_combinations),
            min(num_predictions, len(filtered_combinations)),
            replace=False
        )

        for i, idx in enumerate(selected_indices):
            predictions.append({
                'numbers': filtered_combinations[idx],
                'confidence': 1.0 / len(filtered_combinations),
                'pool_label': idx,
                'source': 'random_from_pool'
            })

        return predictions

    def save_models(self):
        """모델 저장"""
        # 각 모델 저장
        for model_name, model in self.models.items():
            model_path = os.path.join(self.model_dir, f'{model_name}_filtered.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)

        # 스케일러 저장
        scaler_path = os.path.join(self.model_dir, 'scalers_filtered.pkl')
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scalers, f)

        # 매핑 정보 저장
        mapping_path = os.path.join(self.model_dir, 'pool_mapping.pkl')
        mapping_data = {
            'combination_to_label': self.combination_to_label,
            'label_to_combination': self.label_to_combination,
            'filtered_pool': self.filtered_pool
        }
        with open(mapping_path, 'wb') as f:
            pickle.dump(mapping_data, f)

        # 설정 저장
        config_path = os.path.join(self.model_dir, 'ensemble_config_filtered.json')
        config = {
            'ensemble_weights': self.ensemble_weights,
            'feature_config': self.feature_config,
            'is_trained': self.is_trained,
            'pool_size': self.pool_size
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        logging.debug(f"필터링된 풀 앙상블 모델 저장 완료: {self.model_dir}")

    def load_models(self):
        """모델 로드"""
        try:
            # 설정 로드
            config_path = os.path.join(self.model_dir, 'ensemble_config_filtered.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.ensemble_weights = config.get('ensemble_weights', self.ensemble_weights)
                    self.feature_config = config.get('feature_config', self.feature_config)
                    self.is_trained = config.get('is_trained', False)
                    self.pool_size = config.get('pool_size', 0)

            # 매핑 정보 로드
            mapping_path = os.path.join(self.model_dir, 'pool_mapping.pkl')
            if os.path.exists(mapping_path):
                with open(mapping_path, 'rb') as f:
                    mapping_data = pickle.load(f)
                    self.combination_to_label = mapping_data['combination_to_label']
                    self.label_to_combination = mapping_data['label_to_combination']
                    self.filtered_pool = mapping_data['filtered_pool']

            # 모델들 로드
            for model_name in ['rf', 'xgb', 'nn']:
                model_path = os.path.join(self.model_dir, f'{model_name}_filtered.pkl')
                if os.path.exists(model_path):
                    with open(model_path, 'rb') as f:
                        self.models[model_name] = pickle.load(f)

            # 스케일러 로드
            scaler_path = os.path.join(self.model_dir, 'scalers_filtered.pkl')
            if os.path.exists(scaler_path):
                with open(scaler_path, 'rb') as f:
                    self.scalers = pickle.load(f)

            logging.debug("필터링된 풀 앙상블 모델 로드 완료")

        except Exception as e:
            logging.warning(f"모델 로드 실패: {e}")
            self._initialize_models()

    def update_hyperparameters(self, params: Dict[str, Any]):
        """하이퍼파라미터 업데이트"""
        # Random Forest 파라미터 업데이트
        rf_params = {k.replace('rf_', ''): v for k, v in params.items() if k.startswith('rf_')}
        if rf_params:
            self.models['rf'].set_params(**rf_params)

        # XGBoost 파라미터 업데이트
        xgb_params = {k.replace('xgb_', ''): v for k, v in params.items() if k.startswith('xgb_')}
        if xgb_params and XGBOOST_AVAILABLE and 'xgb' in self.models:
            self.models['xgb'].set_params(**xgb_params)

        # Neural Network 파라미터 업데이트
        nn_params = {k.replace('nn_', ''): v for k, v in params.items() if k.startswith('nn_')}
        if nn_params:
            self.models['nn'].set_params(**nn_params)

        # 앙상블 가중치 업데이트
        if 'ensemble_weights' in params:
            self.ensemble_weights.update(params['ensemble_weights'])

        self.is_trained = False  # 재학습 필요
        logging.info(f"필터링된 풀 앙상블 하이퍼파라미터 업데이트: {params}")

    # ============================================================================
    # Backward Compatibility Wrappers for main.py
    # ============================================================================

    def train(self, winning_numbers: List[str], test_size: float = 0.2) -> Optional[Dict[str, Any]]:
        """
        Backward compatibility wrapper for main.py
        Converts winning_numbers (string format) to historical combinations and trains the model

        Args:
            winning_numbers: List of winning number strings (e.g., ["1,2,3,4,5,6"])
            test_size: Test set ratio (not used in filtered pool approach)

        Returns:
            Optional[Dict[str, Any]]: Evaluation metrics (always returns None for compatibility)
        """
        try:
            # Convert string format to list of integers
            historical_combinations = []
            for wn_str in winning_numbers:
                if isinstance(wn_str, str):
                    numbers = [int(n.strip()) for n in wn_str.split(',')]
                    historical_combinations.append(numbers[:6])  # Only first 6 numbers (exclude bonus)
                elif isinstance(wn_str, (list, tuple)):
                    historical_combinations.append(list(wn_str[:6]))

            # For backward compatibility, we need a filtered pool
            # Use a default filter strategy or load from cache
            # In real usage, the filtered pool should be provided by FilterManager
            from src.core.integrated_filter_manager import IntegratedFilterManager
            from src.core.db_manager import DatabaseManager

            logging.info("필터링된 풀 생성 중 (backward compatibility mode)...")
            db_manager = DatabaseManager()
            filter_manager = IntegratedFilterManager(db_manager)

            # Get filtered combinations (this might take time on first run)
            filtered_combinations = filter_manager.get_filtered_combinations()

            if not filtered_combinations:
                logging.warning("필터링된 조합 풀이 비어있습니다. 학습을 건너뜁니다.")
                return None

            # Train with filtered pool
            self.train_with_filtered_pool(historical_combinations, filtered_combinations, test_size)

            # Return None for compatibility (original returns evaluation metrics)
            return None

        except Exception as e:
            logging.error(f"Backward compatibility train() 실패: {e}")
            return None

    def predict_next_numbers(self, winning_numbers: List[str],
                            num_predictions: int = 10) -> List[Dict[str, Any]]:
        """
        Backward compatibility wrapper for main.py
        Converts winning_numbers (string format) and calls predict_from_filtered_pool

        Args:
            winning_numbers: List of winning number strings (e.g., ["1,2,3,4,5,6"])
            num_predictions: Number of predictions to generate

        Returns:
            List[Dict[str, Any]]: Predictions with numbers, confidence, etc.
        """
        try:
            # Convert string format to list of integers
            historical_combinations = []
            for wn_str in winning_numbers:
                if isinstance(wn_str, str):
                    numbers = [int(n.strip()) for n in wn_str.split(',')]
                    historical_combinations.append(numbers[:6])  # Only first 6 numbers
                elif isinstance(wn_str, (list, tuple)):
                    historical_combinations.append(list(wn_str[:6]))

            # Check if we have a filtered pool set
            if not self.filtered_pool:
                logging.warning("필터링된 풀이 설정되지 않았습니다. 기본 랜덤 예측 사용")
                # Generate some basic predictions
                import random
                predictions = []
                for i in range(num_predictions):
                    numbers = sorted(random.sample(range(1, 46), 6))
                    predictions.append({
                        'numbers': numbers,
                        'confidence': 0.5,
                        'source': 'filtered_pool_ensemble_fallback'
                    })
                return predictions

            # Use the advanced scoring-based prediction
            return self.predict_from_filtered_pool(
                historical_combinations,
                self.filtered_pool,
                num_predictions
            )

        except Exception as e:
            logging.error(f"Backward compatibility predict_next_numbers() 실패: {e}")
            # Fallback to random predictions
            import random
            predictions = []
            for i in range(num_predictions):
                numbers = sorted(random.sample(range(1, 46), 6))
                predictions.append({
                    'numbers': numbers,
                    'confidence': 0.3,
                    'source': 'filtered_pool_ensemble_error_fallback'
                })
            return predictions


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from src.core.db_manager import DatabaseManager
    from src.core.filter_manager import FilterManager

    # 데이터베이스에서 당첨번호 로드
    db_manager = DatabaseManager()
    historical_data = db_manager.get_all_winning_numbers()

    if len(historical_data) < 50:
        print(f"데이터 부족: {len(historical_data)}개 (최소 50개 필요)")
        return

    # 과거 당첨번호를 리스트로 변환
    historical_combinations = []
    for combo_str in historical_data:
        numbers = [int(n) for n in combo_str.split(',')]
        historical_combinations.append(numbers)

    # 필터링된 조합 생성 (예시)
    print("필터링된 조합 생성 중...")
    filtered_combinations = []
    try:
        filter_manager = FilterManager(db_manager)
        all_combinations = filter_manager.generate_all_combinations()
        filtered_results = filter_manager.apply_all_filters(all_combinations[:50000])  # 테스트용
        filtered_combinations = [[int(n) for n in combo.split(',')] for combo in filtered_results]
    except Exception as e:
        logging.error(f"예측 생성 실패: {e}")
        # 폴백: 랜덤 조합 생성
        import random
        for _ in range(5000):
            combo = sorted(random.sample(range(1, 46), 6))
            filtered_combinations.append(combo)

    print(f"필터링된 조합 수: {len(filtered_combinations)}개")

    # 필터링된 풀 앙상블 예측기 생성
    predictor = FilteredPoolEnsemblePredictor()

    # 데이터 분할
    train_size = int(len(historical_combinations) * 0.8)
    train_data = historical_combinations[:train_size]
    test_data = historical_combinations[train_size:]

    print(f"학습 데이터: {len(train_data)}개")
    print(f"테스트 데이터: {len(test_data)}개")

    # 모델 학습
    print("\n필터링된 풀 기반 앙상블 학습 시작...")
    results = predictor.train_with_filtered_pool(
        train_data,
        filtered_combinations,
        test_size=0.2
    )

    if results:
        print("\n학습 결과:")
        for model_name, metrics in results.items():
            print(f"{model_name}: 정확도 {metrics['accuracy']:.4f}")

    # 예측 수행
    print("\n다음 회차 예측...")
    predictions = predictor.predict_from_filtered_pool(
        historical_combinations,
        filtered_combinations,
        num_predictions=5
    )

    print("\n예측 결과 (신뢰도 순):")
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred['confidence']
        source = pred['source']
        print(f"{i}. {numbers} (신뢰도: {confidence:.4f}, 출처: {source})")


if __name__ == "__main__":
    main()