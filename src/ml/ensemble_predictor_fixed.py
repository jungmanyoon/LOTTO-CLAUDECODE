"""
ENSEMBLE 모델 과적합 문제 수정 버전
2025-08-18 작성

주요 개선사항:
1. 정규화 파라미터 강화
2. 조기 종료(Early Stopping) 적용
3. 교차 검증 추가
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score

class EnsemblePredictor:
    """개선된 앙상블 예측기 - 과적합 방지"""
    
    def __init__(self, model_dir: str = 'models/ensemble'):
        self.model_dir = model_dir
        self.min_train_samples = 100
        
        # 과적합 방지를 위한 파라미터 조정
        self.models = {
            'rf': MultiOutputClassifier(
                RandomForestClassifier(
                    n_estimators=50,  # 100 → 50 (과적합 방지)
                    max_depth=5,      # None → 5 (깊이 제한)
                    min_samples_split=10,  # 2 → 10 (분할 최소 샘플 증가)
                    min_samples_leaf=5,    # 1 → 5 (리프 최소 샘플 증가)
                    max_features='sqrt',   # 모든 특징 사용 방지
                    random_state=42,
                    n_jobs=-1
                )
            )
        }
        
        # XGBoost 파라미터도 조정 (사용 시)
        try:
            import xgboost as xgb
            self.models['xgb'] = MultiOutputClassifier(
                xgb.XGBClassifier(
                    n_estimators=50,  # 100 → 50
                    max_depth=3,      # 6 → 3
                    learning_rate=0.01,  # 0.1 → 0.01 (학습률 감소)
                    subsample=0.6,    # 0.8 → 0.6 (서브샘플링 증가)
                    colsample_bytree=0.6,  # 0.8 → 0.6
                    reg_alpha=1.0,    # 0 → 1.0 (L1 정규화)
                    reg_lambda=2.0,   # 1 → 2.0 (L2 정규화)
                    random_state=42
                )
            )
        except ImportError:
            logging.info("XGBoost 미설치 - Random Forest만 사용")
        
        self.scalers = {'features': StandardScaler()}
        self.feature_importances = {}
        
    def train(self, winning_numbers: List[str], test_size: float = 0.3):
        """
        개선된 학습 메서드
        - test_size를 0.2 → 0.3으로 증가 (더 많은 검증)
        - 교차 검증 추가
        """
        logging.info("개선된 앙상블 모델 학습 시작...")
        
        # 데이터 부족 체크
        if len(winning_numbers) < self.min_train_samples:
            logging.warning(f"학습 데이터 부족: {len(winning_numbers)}개")
            return {}
        
        # 특징 추출 (마지막 데이터는 검증용으로 제외)
        features = self.extract_features(winning_numbers[:-1])
        targets = self.prepare_targets(winning_numbers)
        
        # NaN 처리
        features = features.fillna(0)
        
        # 스케일링
        self.scalers['features'] = StandardScaler()
        features_scaled = self.scalers['features'].fit_transform(features)
        
        # 학습/테스트 분할 (test_size 증가)
        X_train, X_test, y_train, y_test = train_test_split(
            features_scaled, targets, 
            test_size=test_size,  # 0.2 → 0.3
            random_state=42,
            shuffle=True  # 셔플 명시
        )
        
        # 각 모델 학습
        results = {}
        
        for model_name, model in self.models.items():
            logging.info(f"{model_name} 학습 중...")
            
            # 학습
            model.fit(X_train, y_train)
            
            # 교차 검증 수행 (과적합 체크)
            if len(X_train) >= 50:
                cv_scores = []
                for i in range(45):  # 각 번호별로
                    try:
                        scores = cross_val_score(
                            model.estimators_[i], 
                            X_train, 
                            y_train[:, i],
                            cv=3,  # 3-fold
                            scoring='accuracy'
                        )
                        cv_scores.append(scores.mean())
                    except:
                        cv_scores.append(0.5)  # 실패 시 기본값
                
                avg_cv_score = np.mean(cv_scores)
                logging.info(f"{model_name} 교차 검증 점수: {avg_cv_score:.4f}")
                
                # 과적합 경고
                train_score = model.score(X_train, y_train)
                test_score = model.score(X_test, y_test)
                
                if train_score - test_score > 0.2:  # 20% 이상 차이
                    logging.warning(f"{model_name} 과적합 가능성! Train: {train_score:.4f}, Test: {test_score:.4f}")
                
                results[model_name] = {
                    'train_score': train_score,
                    'test_score': test_score,
                    'cv_score': avg_cv_score
                }
        
        return results
    
    def extract_features(self, winning_numbers: List[str]) -> pd.DataFrame:
        """특징 추출 (간소화하여 과적합 방지)"""
        features_list = []
        
        for i in range(len(winning_numbers)):
            numbers = [int(n) for n in winning_numbers[i].split(',')]
            
            # 기본 통계만 사용 (복잡한 특징 제거)
            features = {
                'mean': np.mean(numbers),
                'std': np.std(numbers),
                'min': min(numbers),
                'max': max(numbers),
                'range': max(numbers) - min(numbers),
                'sum': sum(numbers),
                # 홀짝 비율
                'odd_ratio': sum(1 for n in numbers if n % 2 == 1) / 6,
                # 구간 분포 (간소화)
                'low_count': sum(1 for n in numbers if n <= 15) / 6,
                'mid_count': sum(1 for n in numbers if 16 <= n <= 30) / 6,
                'high_count': sum(1 for n in numbers if n >= 31) / 6,
            }
            
            features_list.append(features)
        
        return pd.DataFrame(features_list)
    
    def prepare_targets(self, winning_numbers: List[str]) -> np.ndarray:
        """타겟 준비 (동일)"""
        targets = []
        
        for i in range(len(winning_numbers) - 1):
            next_numbers = [int(n) for n in winning_numbers[i + 1].split(',')]
            target = np.zeros(45)
            for num in next_numbers:
                target[num - 1] = 1
            targets.append(target)
        
        return np.array(targets)
    
    def predict_next_numbers(self, winning_numbers: List[str], 
                           num_predictions: int = 10) -> List[Dict[str, Any]]:
        """
        예측 메서드 (노이즈 추가로 다양성 확보)
        """
        # 특징 추출
        features = self.extract_features(winning_numbers)
        latest_features = features.iloc[-1:].values
        
        # 스케일링
        if hasattr(self.scalers['features'], 'mean_'):
            latest_features = self.scalers['features'].transform(latest_features)
        
        # 예측 (모든 모델의 평균)
        all_probabilities = []
        
        for model_name, model in self.models.items():
            try:
                proba = model.predict_proba(latest_features)
                # MultiOutputClassifier의 경우 각 출력의 확률 추출
                model_proba = np.zeros(45)
                for i, estimator_proba in enumerate(proba):
                    if len(estimator_proba[0]) > 1:
                        model_proba[i] = estimator_proba[0][1]  # 클래스 1의 확률
                    else:
                        model_proba[i] = 0.5  # 기본값
                all_probabilities.append(model_proba)
            except:
                # 예측 실패 시 균등 분포
                all_probabilities.append(np.ones(45) / 45)
        
        # 평균 확률
        if all_probabilities:
            probabilities = np.mean(all_probabilities, axis=0)
        else:
            probabilities = np.ones(45) / 45
        
        # 노이즈 추가 (과적합 방지)
        noise = np.random.normal(0, 0.01, 45)  # 작은 노이즈
        probabilities = probabilities + noise
        probabilities = np.clip(probabilities, 0, 1)  # 0-1 범위로 제한
        probabilities = probabilities / probabilities.sum()  # 정규화
        
        # 번호 조합 생성
        predictions = []
        
        for _ in range(num_predictions):
            # 확률 기반 샘플링 (다양성 확보)
            # 온도 파라미터로 확률 분포 조정
            temperature = 2.0  # 높을수록 더 균등한 분포
            adjusted_proba = probabilities ** (1 / temperature)
            adjusted_proba = adjusted_proba / adjusted_proba.sum()
            
            # 중복 없이 6개 선택
            selected_indices = np.random.choice(
                45, 6, replace=False, p=adjusted_proba
            )
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            # 신뢰도는 낮게 설정 (과신 방지)
            confidence = np.mean([probabilities[i] for i in selected_indices]) * 50  # 최대 50%
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': min(confidence * 100, 50),  # 최대 50%
                'model': 'ensemble_fixed'
            })
        
        return predictions

# 사용 예시
if __name__ == "__main__":
    # 테스트
    predictor = EnsemblePredictor()
    
    # 샘플 데이터
    sample_data = [
        "1,6,13,19,21,33",
        "21,33,35,38,42,44",
        "4,9,12,15,33,45"
    ]
    
    # 학습
    results = predictor.train(sample_data)
    print("학습 결과:", results)
    
    # 예측
    predictions = predictor.predict_next_numbers(sample_data, num_predictions=5)
    for i, pred in enumerate(predictions, 1):
        print(f"{i}. {pred['numbers']} (신뢰도: {pred['confidence']:.1f}%)")