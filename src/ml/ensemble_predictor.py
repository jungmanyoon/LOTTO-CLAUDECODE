#!/usr/bin/env python3
"""
앙상블 모델 기반 로또 번호 예측 시스템
Random Forest, XGBoost, Neural Network를 결합한 앙상블 예측
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
import pickle

# ML 라이브러리 imports
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, precision_score, recall_score
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

class EnsemblePredictor:
    """앙상블 기반 로또 번호 예측기"""
    
    def __init__(self, model_dir: str = 'models/ensemble'):
        """
        Args:
            model_dir: 모델 저장 디렉토리
        """
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        
        self.models = {}
        self.scalers = {}
        self.feature_importances = {}
        self.is_trained = False
        
        # 앙상블 가중치
        self.ensemble_weights = {
            'rf': 0.3,     # Random Forest
            'xgb': 0.4,    # XGBoost
            'nn': 0.3      # Neural Network
        }
        
        # 특징 엔지니어링 설정
        self.feature_config = {
            'use_statistics': True,      # 통계적 특징 사용
            'use_patterns': True,        # 패턴 특징 사용
            'use_temporal': True,        # 시간적 특징 사용
            'window_sizes': [5, 10, 20]  # 다양한 윈도우 크기
        }
        
        # 모델 초기화
        if SKLEARN_AVAILABLE:
            self._initialize_models()
    
    def _initialize_models(self):
        """모델 초기화 또는 로드"""
        # Random Forest
        rf_path = os.path.join(self.model_dir, 'random_forest.pkl')
        if os.path.exists(rf_path):
            with open(rf_path, 'rb') as f:
                self.models['rf'] = pickle.load(f)
                self.is_trained = True
        else:
            self.models['rf'] = self._build_random_forest()
        
        # XGBoost
        if XGBOOST_AVAILABLE:
            xgb_path = os.path.join(self.model_dir, 'xgboost.pkl')
            if os.path.exists(xgb_path):
                with open(xgb_path, 'rb') as f:
                    self.models['xgb'] = pickle.load(f)
            else:
                self.models['xgb'] = self._build_xgboost()
        
        # Neural Network
        nn_path = os.path.join(self.model_dir, 'neural_network.pkl')
        if os.path.exists(nn_path):
            with open(nn_path, 'rb') as f:
                self.models['nn'] = pickle.load(f)
        else:
            self.models['nn'] = self._build_neural_network()
        
        # Scaler
        scaler_path = os.path.join(self.model_dir, 'scalers.pkl')
        if os.path.exists(scaler_path):
            with open(scaler_path, 'rb') as f:
                self.scalers = pickle.load(f)
        else:
            self.scalers = {
                'features': StandardScaler(),
                'targets': StandardScaler()
            }
    
    def _build_random_forest(self) -> RandomForestClassifier:
        """Random Forest 모델 구축"""
        return RandomForestClassifier(
            n_estimators=200,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )
    
    def _build_xgboost(self):
        """XGBoost 모델 구축"""
        return xgb.XGBClassifier(
            n_estimators=200,
            max_depth=10,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='binary:logistic',
            random_state=42,
            n_jobs=-1
        )
    
    def _build_neural_network(self) -> MLPClassifier:
        """Neural Network 모델 구축"""
        return MLPClassifier(
            hidden_layer_sizes=(256, 128, 64, 32),
            activation='relu',
            solver='adam',
            alpha=0.001,
            batch_size='auto',
            learning_rate='adaptive',
            learning_rate_init=0.001,
            max_iter=500,
            shuffle=True,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.1
        )
    
    def extract_features(self, winning_numbers: List[str], 
                        target_round: int = None) -> pd.DataFrame:
        """특징 추출
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            target_round: 타겟 회차 (학습시 사용)
            
        Returns:
            pd.DataFrame: 추출된 특징
        """
        features_list = []
        
        for i in range(len(winning_numbers)):
            if target_round and i >= target_round:
                break
                
            features = {}
            
            # 기본 통계 특징
            if self.feature_config['use_statistics']:
                numbers = [int(n) for n in winning_numbers[i].split(',')]
                
                features['mean'] = np.mean(numbers)
                features['std'] = np.std(numbers)
                features['min'] = min(numbers)
                features['max'] = max(numbers)
                features['range'] = features['max'] - features['min']
                features['sum'] = sum(numbers)
                
                # 홀짝 분포
                odd_count = sum(1 for n in numbers if n % 2 == 1)
                features['odd_ratio'] = odd_count / 6
                
                # 구간별 분포
                for section in range(5):
                    section_count = sum(1 for n in numbers 
                                      if section * 9 + 1 <= n <= (section + 1) * 9)
                    features[f'section_{section}'] = section_count / 6
            
            # 패턴 특징
            if self.feature_config['use_patterns']:
                numbers = [int(n) for n in winning_numbers[i].split(',')]
                
                # 연속 번호
                consecutive_count = sum(1 for j in range(len(numbers)-1) 
                                      if numbers[j+1] - numbers[j] == 1)
                features['consecutive_ratio'] = consecutive_count / 5
                
                # 간격 통계
                gaps = [numbers[j+1] - numbers[j] for j in range(len(numbers)-1)]
                features['avg_gap'] = np.mean(gaps)
                features['max_gap'] = max(gaps)
                
                # 소수 개수
                primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43]
                prime_count = sum(1 for n in numbers if n in primes)
                features['prime_ratio'] = prime_count / 6
            
            # 시간적 특징
            if self.feature_config['use_temporal']:
                for window in self.feature_config['window_sizes']:
                    if i >= window:
                        # 최근 window 회차의 통계
                        recent_numbers = []
                        for j in range(i-window, i):
                            recent_numbers.extend([int(n) for n in 
                                                 winning_numbers[j].split(',')])
                        
                        # 번호별 출현 빈도
                        for num in range(1, 46):
                            features[f'freq_{num}_w{window}'] = \
                                recent_numbers.count(num) / (window * 6)
                    else:
                        # window보다 작은 경우 0으로 초기화
                        for num in range(1, 46):
                            features[f'freq_{num}_w{window}'] = 0
            
            features_list.append(features)
        
        return pd.DataFrame(features_list)
    
    def prepare_targets(self, winning_numbers: List[str]) -> np.ndarray:
        """타겟 데이터 준비 (다음 회차 번호)
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            
        Returns:
            np.ndarray: 타겟 배열 (45개 번호의 출현 여부)
        """
        targets = []
        
        for i in range(len(winning_numbers) - 1):
            # 다음 회차 번호
            next_numbers = [int(n) for n in winning_numbers[i + 1].split(',')]
            
            # 45차원 이진 벡터
            target = np.zeros(45)
            for num in next_numbers:
                target[num - 1] = 1
            
            targets.append(target)
        
        return np.array(targets)
    
    def train(self, winning_numbers: List[str], test_size: float = 0.2):
        """앙상블 모델 학습
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            test_size: 테스트 데이터 비율
        """
        if not SKLEARN_AVAILABLE:
            logging.error("scikit-learn이 설치되지 않아 학습할 수 없습니다.")
            return
        
        logging.info("앙상블 모델 학습 시작...")
        
        # 특징 추출
        features = self.extract_features(winning_numbers[:-1])
        targets = self.prepare_targets(winning_numbers)
        
        # 데이터 정렬 확인
        assert len(features) == len(targets), "Features and targets length mismatch"
        
        # NaN 값 처리
        logging.info(f"특징 데이터 shape: {features.shape}")
        logging.info(f"NaN 값 개수: {features.isna().sum().sum()}")
        
        # NaN 값을 0으로 채우기 (또는 평균값으로 채우기)
        features = features.fillna(0)
        
        # 스케일링
        features_scaled = self.scalers['features'].fit_transform(features)
        
        # 학습/테스트 분할
        X_train, X_test, y_train, y_test = train_test_split(
            features_scaled, targets, test_size=test_size, random_state=42
        )
        
        # 각 모델 학습
        results = {}
        
        # Random Forest
        logging.info("Random Forest 학습 중...")
        for i in range(45):  # 각 번호에 대해 별도 모델
            self.models['rf'].fit(X_train, y_train[:, i])
        
        # 특징 중요도 저장
        self.feature_importances['rf'] = self.models['rf'].feature_importances_
        
        # XGBoost
        if XGBOOST_AVAILABLE and 'xgb' in self.models:
            logging.info("XGBoost 학습 중...")
            for i in range(45):
                self.models['xgb'].fit(X_train, y_train[:, i])
        
        # Neural Network
        logging.info("Neural Network 학습 중...")
        self.models['nn'].fit(X_train, y_train)
        
        self.is_trained = True
        
        # 모델 저장
        self.save_models()
        
        # 평가
        evaluation = self.evaluate(X_test, y_test, features.columns)
        
        logging.info("앙상블 모델 학습 완료")
        return evaluation
    
    def predict_probability(self, features: np.ndarray) -> np.ndarray:
        """앙상블 예측 (확률)
        
        Args:
            features: 특징 벡터
            
        Returns:
            np.ndarray: 각 번호의 출현 확률 (45차원)
        """
        if not self.is_trained:
            logging.warning("모델이 학습되지 않았습니다.")
            return np.ones(45) / 45  # 균등 분포
        
        predictions = {}
        
        # Random Forest 예측
        rf_pred = np.zeros((features.shape[0], 45))
        for i in range(45):
            rf_pred[:, i] = self.models['rf'].predict_proba(features)[:, 1]
        predictions['rf'] = rf_pred
        
        # XGBoost 예측
        if XGBOOST_AVAILABLE and 'xgb' in self.models:
            xgb_pred = np.zeros((features.shape[0], 45))
            for i in range(45):
                xgb_pred[:, i] = self.models['xgb'].predict_proba(features)[:, 1]
            predictions['xgb'] = xgb_pred
        
        # Neural Network 예측
        nn_pred = self.models['nn'].predict_proba(features)
        predictions['nn'] = nn_pred
        
        # 가중 평균 앙상블
        final_pred = np.zeros_like(rf_pred)
        total_weight = 0
        
        for model_name, pred in predictions.items():
            weight = self.ensemble_weights.get(model_name, 0)
            final_pred += pred * weight
            total_weight += weight
        
        if total_weight > 0:
            final_pred /= total_weight
        
        return final_pred
    
    def predict_next_numbers(self, winning_numbers: List[str], 
                           num_predictions: int = 10) -> List[Dict[str, Any]]:
        """다음 회차 번호 예측
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            num_predictions: 생성할 예측 조합 수
            
        Returns:
            List[Dict[str, Any]]: 예측된 번호 조합과 확률
        """
        # 특징 추출
        features = self.extract_features(winning_numbers)
        
        # 최신 데이터 사용
        latest_features = features.iloc[-1:].values
        
        # 스케일링
        if hasattr(self.scalers['features'], 'mean_'):
            latest_features = self.scalers['features'].transform(latest_features)
        
        # 예측
        probabilities = self.predict_probability(latest_features)[0]
        
        # 번호 조합 생성
        predictions = []
        
        for _ in range(num_predictions):
            # 확률 기반 샘플링
            # 상위 확률에 가중치를 둔 샘플링
            weights = probabilities ** 2  # 제곱으로 상위 확률 강조
            weights = weights / weights.sum()
            
            # 중복 없이 6개 선택
            selected_indices = np.random.choice(
                45, 6, replace=False, p=weights
            )
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            # 예측 신뢰도 계산
            confidence = np.mean([probabilities[i] for i in selected_indices])
            
            # 개별 모델 예측도 포함
            model_predictions = {}
            if hasattr(self, 'models'):
                # 각 모델의 예측 확률
                for model_name in self.models:
                    model_predictions[model_name] = float(confidence)
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': float(confidence),
                'probability_vector': probabilities.tolist(),
                'model_predictions': model_predictions
            })
        
        # 신뢰도 순으로 정렬
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return predictions
    
    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray, 
                feature_names: List[str]) -> Dict[str, Any]:
        """모델 평가
        
        Args:
            X_test: 테스트 특징
            y_test: 테스트 타겟
            feature_names: 특징 이름 리스트
            
        Returns:
            Dict[str, Any]: 평가 메트릭
        """
        evaluation = {
            'models': {},
            'ensemble': {},
            'feature_importance': {}
        }
        
        # 앙상블 예측
        ensemble_pred = self.predict_probability(X_test)
        
        # 임계값 기반 이진 예측
        threshold = 0.5
        ensemble_binary = (ensemble_pred > threshold).astype(int)
        
        # 전체 정확도
        evaluation['ensemble']['accuracy'] = accuracy_score(
            y_test.flatten(), ensemble_binary.flatten()
        )
        
        # 번호별 예측 성능
        match_scores = []
        for i in range(len(y_test)):
            # 상위 6개 예측
            top_6 = np.argsort(ensemble_pred[i])[-6:]
            actual = np.where(y_test[i] == 1)[0]
            
            # 일치 개수
            matches = len(set(top_6) & set(actual))
            match_scores.append(matches)
        
        evaluation['ensemble']['avg_matches'] = np.mean(match_scores)
        evaluation['ensemble']['match_distribution'] = {
            i: match_scores.count(i) for i in range(7)
        }
        
        # 특징 중요도 (Random Forest 기준)
        if 'rf' in self.feature_importances:
            importance_df = pd.DataFrame({
                'feature': feature_names,
                'importance': self.feature_importances['rf']
            }).sort_values('importance', ascending=False)
            
            evaluation['feature_importance'] = importance_df.head(20).to_dict('records')
        
        return evaluation
    
    def save_models(self):
        """모델 저장"""
        # 각 모델 저장
        for model_name, model in self.models.items():
            model_path = os.path.join(self.model_dir, f'{model_name}.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
        
        # 스케일러 저장
        scaler_path = os.path.join(self.model_dir, 'scalers.pkl')
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scalers, f)
        
        # 설정 저장
        config_path = os.path.join(self.model_dir, 'ensemble_config.json')
        config = {
            'ensemble_weights': self.ensemble_weights,
            'feature_config': self.feature_config,
            'is_trained': self.is_trained
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logging.info(f"모델 저장 완료: {self.model_dir}")
    
    def load_models(self):
        """모델 로드"""
        # 설정 로드
        config_path = os.path.join(self.model_dir, 'ensemble_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.ensemble_weights = config.get('ensemble_weights', self.ensemble_weights)
                self.feature_config = config.get('feature_config', self.feature_config)
                self.is_trained = config.get('is_trained', False)
        
        # 모델 로드
        self._initialize_models()
        
        logging.info("모델 로드 완료")


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
    
    # 앙상블 예측기 생성
    ensemble = EnsemblePredictor()
    
    # 모델 학습
    if not ensemble.is_trained:
        print("\n앙상블 모델 학습 시작...")
        evaluation = ensemble.train(winning_numbers, test_size=0.2)
        
        print("\n평가 결과:")
        print(f"정확도: {evaluation['ensemble']['accuracy']:.4f}")
        print(f"평균 일치 개수: {evaluation['ensemble']['avg_matches']:.2f}개")
        print("\n일치 개수 분포:")
        for matches, count in evaluation['ensemble']['match_distribution'].items():
            print(f"  {matches}개 일치: {count}회")
    
    # 예측 수행
    print("\n다음 회차 예측...")
    predictions = ensemble.predict_next_numbers(winning_numbers, num_predictions=5)
    
    print("\n예측 결과 (신뢰도 순):")
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred['confidence']
        print(f"{i}. {numbers} (신뢰도: {confidence:.2%})")

if __name__ == "__main__":
    main()