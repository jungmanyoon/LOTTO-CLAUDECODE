#!/usr/bin/env python3
"""
제약된 공간에서 학습하는 ML 예측기
필터링된 조합 풀 내에서만 학습하고 예측하는 시스템
"""

import logging
import numpy as np
from typing import List, Dict, Set, Tuple
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow.keras import layers, models
import pickle
import os

class ConstrainedPredictor:
    """필터링된 풀에서만 학습하는 예측기"""
    
    def __init__(self, filtered_pool_path: str = None):
        """
        Args:
            filtered_pool_path: 필터링된 조합 풀 경로
        """
        self.filtered_pool = set()
        self.pool_features = {}  # 각 조합의 특징 벡터
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        
        if filtered_pool_path:
            self.load_filtered_pool(filtered_pool_path)
    
    def load_filtered_pool(self, path: str = None):
        """필터링된 조합 풀 로드"""
        try:
            # DB에서 필터링된 조합 로드
            from ..core.db_manager import DatabaseManager
            db_manager = DatabaseManager()
            
            # 필터링된 조합 가져오기
            filtered_combos = db_manager.combinations_db.get_filtered_combinations(
                db_manager.get_latest_round()
            )
            
            logging.info(f"필터링된 조합 {len(filtered_combos):,}개 로드")
            
            # set으로 변환하여 빠른 검색
            for combo_str in filtered_combos:
                self.filtered_pool.add(tuple(map(int, combo_str.split(','))))
            
            # 각 조합의 특징 추출
            self._extract_pool_features()
            
        except Exception as e:
            logging.error(f"필터링된 풀 로드 실패: {e}")
    
    def _extract_pool_features(self):
        """모든 조합의 특징 벡터 추출"""
        for combo in self.filtered_pool:
            features = self._extract_features(combo)
            self.pool_features[combo] = features
    
    def _extract_features(self, numbers: tuple) -> np.ndarray:
        """조합의 특징 추출"""
        features = []
        numbers = sorted(numbers)
        
        # 기본 통계
        features.append(np.mean(numbers))  # 평균
        features.append(np.std(numbers))   # 표준편차
        features.append(max(numbers) - min(numbers))  # 범위
        features.append(sum(numbers))  # 합계
        
        # 홀짝 비율
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        features.append(odd_count / 6)
        
        # 연속 번호
        consecutive = 0
        for i in range(1, len(numbers)):
            if numbers[i] == numbers[i-1] + 1:
                consecutive += 1
        features.append(consecutive / 5)
        
        # 구간별 분포 (1-15, 16-30, 31-45)
        low = sum(1 for n in numbers if n <= 15)
        mid = sum(1 for n in numbers if 16 <= n <= 30)
        high = sum(1 for n in numbers if n > 30)
        features.extend([low/6, mid/6, high/6])
        
        # 간격 통계
        gaps = [numbers[i] - numbers[i-1] for i in range(1, len(numbers))]
        features.append(np.mean(gaps))
        features.append(np.std(gaps))
        features.append(max(gaps))
        
        return np.array(features)
    
    def train_on_constrained_space(self, winning_numbers: List[str]):
        """필터링된 공간 내에서만 학습"""
        logging.info("제약된 공간에서 ML 모델 학습 시작")
        
        # 학습 데이터 준비
        X_train = []
        y_train = []
        
        # 당첨번호를 positive samples로
        for winning_str in winning_numbers:
            numbers = tuple(sorted(map(int, winning_str.split(','))))
            
            # 이 조합이 필터 풀에 있는지 확인
            if numbers in self.filtered_pool:
                features = self._extract_features(numbers)
                X_train.append(features)
                y_train.append(1)  # 당첨
        
        # 필터 풀에서 negative samples 추가
        negative_samples = list(self.filtered_pool - set([
            tuple(sorted(map(int, w.split(',')))) for w in winning_numbers
        ]))
        
        # 균형잡힌 데이터셋을 위해 negative 샘플 수 조정
        n_negative = min(len(negative_samples), len(X_train) * 10)
        selected_negatives = np.random.choice(
            len(negative_samples), n_negative, replace=False
        )
        
        for idx in selected_negatives:
            combo = negative_samples[idx]
            features = self._extract_features(combo)
            X_train.append(features)
            y_train.append(0)  # 미당첨
        
        X_train = np.array(X_train)
        y_train = np.array(y_train)
        
        # 스케일링
        X_train = self.scaler.fit_transform(X_train)
        
        # 신경망 모델 구축
        self.model = models.Sequential([
            layers.Dense(64, activation='relu', input_shape=(X_train.shape[1],)),
            layers.Dropout(0.3),
            layers.Dense(32, activation='relu'),
            layers.Dropout(0.2),
            layers.Dense(16, activation='relu'),
            layers.Dense(1, activation='sigmoid')
        ])
        
        self.model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['accuracy']
        )
        
        # 학습
        history = self.model.fit(
            X_train, y_train,
            epochs=50,
            batch_size=32,
            validation_split=0.2,
            verbose=0
        )
        
        self.is_trained = True
        logging.info(f"제약된 공간 학습 완료: {len(self.filtered_pool):,}개 풀에서 학습")
        
        return history
    
    def predict_from_pool(self, n_predictions: int = 5) -> List[Dict]:
        """필터 풀에서 상위 예측 선택"""
        if not self.is_trained:
            logging.error("모델이 학습되지 않았습니다")
            return []
        
        predictions = []
        
        # 모든 필터 풀 조합에 대해 예측
        pool_list = list(self.filtered_pool)
        X_pool = []
        
        for combo in pool_list:
            features = self._extract_features(combo)
            X_pool.append(features)
        
        X_pool = np.array(X_pool)
        X_pool = self.scaler.transform(X_pool)
        
        # 예측 수행
        scores = self.model.predict(X_pool, verbose=0).flatten()
        
        # 상위 N개 선택
        top_indices = np.argsort(scores)[-n_predictions:][::-1]
        
        for idx in top_indices:
            combo = pool_list[idx]
            predictions.append({
                'numbers': sorted(combo),
                'confidence': float(scores[idx]),
                'model': 'constrained',
                'source': 'filtered_pool'
            })
        
        logging.info(f"필터 풀에서 {len(predictions)}개 예측 생성 (100% 필터 통과 보장)")
        
        return predictions
    
    def validate_prediction(self, numbers: List[int]) -> bool:
        """예측이 필터 풀에 있는지 확인"""
        return tuple(sorted(numbers)) in self.filtered_pool
    
    def get_pool_statistics(self) -> Dict:
        """필터 풀 통계"""
        if not self.filtered_pool:
            return {}
        
        stats = {
            'pool_size': len(self.filtered_pool),
            'pool_ratio': len(self.filtered_pool) / 8145060,
            'features_extracted': len(self.pool_features),
            'model_trained': self.is_trained
        }
        
        # 풀의 특성 분석
        all_numbers = []
        for combo in self.filtered_pool:
            all_numbers.extend(combo)
        
        stats['number_frequency'] = {}
        for num in range(1, 46):
            count = all_numbers.count(num)
            stats['number_frequency'][num] = count / len(self.filtered_pool)
        
        return stats
    
    def save_model(self, path: str = 'models/constrained_predictor.pkl'):
        """모델 저장"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'filtered_pool': self.filtered_pool,
                'pool_features': self.pool_features,
                'is_trained': self.is_trained
            }, f)
        
        logging.info(f"제약된 예측 모델 저장: {path}")
    
    def load_model(self, path: str = 'models/constrained_predictor.pkl'):
        """모델 로드"""
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
                self.filtered_pool = data['filtered_pool']
                self.pool_features = data['pool_features']
                self.is_trained = data['is_trained']
            
            logging.info(f"제약된 예측 모델 로드: {path}")
            return True
        return False