#!/usr/bin/env python3
"""
LSTM 기반 로또 번호 예측 모델
시계열 패턴을 학습하여 다음 회차 번호 예측
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os

# TensorFlow/Keras imports
try:
    # TensorFlow 경고 억제 설정
    import warnings
    warnings.filterwarnings('ignore', message='.*compiled metrics.*')
    warnings.filterwarnings('ignore', message='.*compile_metrics.*')
    warnings.filterwarnings('ignore', category=UserWarning, module='tensorflow')
    
    import tensorflow as tf
    # TensorFlow 로깅 레벨 설정
    tf.get_logger().setLevel('ERROR')
    
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
    from tensorflow.keras.optimizers import Adam
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logging.warning("TensorFlow not available. LSTM predictor will work in limited mode.")

class LSTMPredictor:
    """LSTM 기반 로또 번호 예측기"""
    
    def __init__(self, sequence_length: int = 50, model_path: str = None):
        """
        Args:
            sequence_length: 입력 시퀀스 길이 (과거 몇 회차를 볼 것인가)
            model_path: 저장된 모델 경로 (None이면 새로 생성)
        """
        self.sequence_length = sequence_length
        self.model_path = model_path or 'models/lstm_lotto_predictor.h5'
        self.model = None
        self.is_trained = False
        self.scaler_params = {}
        
        # 모델 아키텍처 파라미터
        self.lstm_units = [128, 64, 32]
        self.dropout_rate = 0.2
        self.learning_rate = 0.001
        
        # 데이터 전처리 파라미터
        self.feature_dims = 45  # 로또 번호 1-45
        self.output_dims = 45   # 각 번호의 출현 확률
        
        # 모델 로드 또는 생성
        if TENSORFLOW_AVAILABLE:
            self._initialize_model()
        
    def _initialize_model(self):
        """모델 초기화"""
        if os.path.exists(self.model_path):
            try:
                # TensorFlow 경고 억제
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=UserWarning, module='tensorflow')
                    warnings.filterwarnings('ignore', message='.*compiled metrics.*')
                    warnings.filterwarnings('ignore', message='.*compile_metrics.*')
                    self.model = load_model(self.model_path)
                self.is_trained = True
                logging.info(f"기존 모델 로드됨: {self.model_path}")
            except Exception as e:
                logging.warning(f"모델 로드 실패: {str(e)}. 새 모델을 생성합니다.")
                self.model = self._build_lstm_model()
        else:
            self.model = self._build_lstm_model()
    
    def _build_lstm_model(self) -> Sequential:
        """LSTM 모델 구축
        
        Returns:
            Sequential: 컴파일된 LSTM 모델
        """
        model = Sequential([
            # 첫 번째 LSTM 레이어
            LSTM(self.lstm_units[0], 
                 return_sequences=True, 
                 input_shape=(self.sequence_length, self.feature_dims),
                 kernel_regularizer=tf.keras.regularizers.l2(0.01)),
            Dropout(self.dropout_rate),
            BatchNormalization(),
            
            # 두 번째 LSTM 레이어
            LSTM(self.lstm_units[1], return_sequences=True),
            Dropout(self.dropout_rate),
            BatchNormalization(),
            
            # 세 번째 LSTM 레이어
            LSTM(self.lstm_units[2], return_sequences=False),
            Dropout(self.dropout_rate),
            BatchNormalization(),
            
            # 출력 레이어
            Dense(self.output_dims, activation='sigmoid')
        ])
        
        # 모델 컴파일
        optimizer = Adam(learning_rate=self.learning_rate)
        model.compile(
            optimizer=optimizer,
            loss='binary_crossentropy',
            metrics=['binary_accuracy', 'AUC']
        )
        
        logging.info("새 LSTM 모델 생성됨")
        return model
    
    def prepare_training_data(self, winning_numbers: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """학습 데이터 준비
        
        Args:
            winning_numbers: 과거 당첨번호 리스트 (문자열 형태)
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (X_train, y_train)
        """
        # 번호를 원-핫 인코딩으로 변환
        encoded_sequences = []
        
        for nums_str in winning_numbers:
            numbers = [int(n) for n in nums_str.split(',')]
            # 45차원 벡터로 인코딩 (각 번호의 출현 여부)
            encoded = np.zeros(self.feature_dims)
            for num in numbers:
                encoded[num - 1] = 1
            encoded_sequences.append(encoded)
        
        encoded_sequences = np.array(encoded_sequences)
        
        # 시퀀스 생성
        X, y = [], []
        for i in range(len(encoded_sequences) - self.sequence_length):
            X.append(encoded_sequences[i:i + self.sequence_length])
            y.append(encoded_sequences[i + self.sequence_length])
        
        return np.array(X), np.array(y)
    
    def train(self, winning_numbers: List[str], epochs: int = 100, 
              batch_size: int = 32, validation_split: float = 0.2):
        """모델 학습
        
        Args:
            winning_numbers: 과거 당첨번호 리스트
            epochs: 학습 에폭 수
            batch_size: 배치 크기
            validation_split: 검증 데이터 비율
        """
        if not TENSORFLOW_AVAILABLE:
            logging.error("TensorFlow가 설치되지 않아 학습할 수 없습니다.")
            return
        
        logging.info("LSTM 모델 학습 시작...")
        
        # 데이터 준비
        X_train, y_train = self.prepare_training_data(winning_numbers)
        
        if len(X_train) < 10:
            logging.error(f"학습 데이터가 부족합니다: {len(X_train)}개")
            return
        
        # 콜백 설정
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True
            ),
            ModelCheckpoint(
                self.model_path,
                monitor='val_loss',
                save_best_only=True
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=0.00001
            )
        ]
        
        # 모델 학습
        history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=callbacks,
            verbose=1
        )
        
        self.is_trained = True
        
        # 학습 결과 저장
        self._save_training_history(history)
        
        logging.info("LSTM 모델 학습 완료")
        return history
    
    def predict_next_numbers(self, recent_numbers: List[str], 
                           num_predictions: int = 10) -> List[Dict[str, Any]]:
        """다음 회차 번호 예측
        
        Args:
            recent_numbers: 최근 당첨번호 리스트 (최소 sequence_length개)
            num_predictions: 생성할 예측 조합 수
            
        Returns:
            List[Dict[str, Any]]: 예측된 번호 조합과 확률
        """
        if not TENSORFLOW_AVAILABLE or not self.is_trained:
            logging.warning("모델이 준비되지 않았습니다. 랜덤 예측을 반환합니다.")
            return self._random_predictions(num_predictions)
        
        # 입력 데이터 준비
        if len(recent_numbers) < self.sequence_length:
            logging.warning(f"입력 데이터 부족: {len(recent_numbers)}개 (필요: {self.sequence_length}개)")
            return self._random_predictions(num_predictions)
        
        # 최근 sequence_length개의 데이터만 사용
        recent_sequence = recent_numbers[-self.sequence_length:]
        
        # 인코딩
        encoded_sequence = []
        for nums_str in recent_sequence:
            numbers = [int(n) for n in nums_str.split(',')]
            encoded = np.zeros(self.feature_dims)
            for num in numbers:
                encoded[num - 1] = 1
            encoded_sequence.append(encoded)
        
        X = np.array([encoded_sequence])
        
        # 예측
        probabilities = self.model.predict(X, verbose=0)[0]
        
        # 예측 결과를 바탕으로 번호 조합 생성
        predictions = []
        
        for _ in range(num_predictions):
            # 확률 기반 샘플링 + 노이즈
            noisy_probs = probabilities + np.random.normal(0, 0.1, size=self.feature_dims)
            noisy_probs = np.clip(noisy_probs, 0, 1)
            
            # 상위 확률 번호 선택
            top_indices = np.argsort(noisy_probs)[-15:]  # 상위 15개
            
            # 이 중에서 6개 랜덤 선택
            selected_indices = np.random.choice(top_indices, 6, replace=False)
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            # 예측 신뢰도 계산
            confidence = np.mean([probabilities[i] for i in selected_indices])
            
            predictions.append({
                'numbers': selected_numbers,
                'confidence': float(confidence),
                'probability_vector': probabilities.tolist()
            })
        
        # 신뢰도 순으로 정렬
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return predictions
    
    def _random_predictions(self, num_predictions: int) -> List[Dict[str, Any]]:
        """랜덤 예측 생성 (폴백 메서드)"""
        predictions = []
        
        for _ in range(num_predictions):
            numbers = sorted(np.random.choice(range(1, 46), 6, replace=False).tolist())
            predictions.append({
                'numbers': numbers,
                'confidence': 0.0,
                'probability_vector': [1/45] * 45  # 균등 분포
            })
        
        return predictions
    
    def _save_training_history(self, history):
        """학습 히스토리 저장"""
        history_dict = {
            'loss': history.history['loss'],
            'val_loss': history.history.get('val_loss', []),
            'binary_accuracy': history.history.get('binary_accuracy', []),
            'val_binary_accuracy': history.history.get('val_binary_accuracy', []),
            'epochs': len(history.history['loss'])
        }
        
        history_path = self.model_path.replace('.h5', '_history.json')
        with open(history_path, 'w') as f:
            json.dump(history_dict, f, indent=2)
        
        logging.info(f"학습 히스토리 저장됨: {history_path}")
    
    def evaluate_model(self, test_numbers: List[str]) -> Dict[str, float]:
        """모델 평가
        
        Args:
            test_numbers: 테스트용 당첨번호 리스트
            
        Returns:
            Dict[str, float]: 평가 메트릭
        """
        if not TENSORFLOW_AVAILABLE or not self.is_trained:
            return {'error': 'Model not available'}
        
        X_test, y_test = self.prepare_training_data(test_numbers)
        
        if len(X_test) == 0:
            return {'error': 'Insufficient test data'}
        
        # 모델 평가
        results = self.model.evaluate(X_test, y_test, verbose=0)
        
        metrics = {
            'loss': float(results[0]),
            'binary_accuracy': float(results[1]),
            'auc': float(results[2]) if len(results) > 2 else 0.0
        }
        
        # 추가 평가: 실제 당첨번호와의 일치도
        predictions = self.model.predict(X_test, verbose=0)
        match_scores = []
        
        for pred, actual in zip(predictions, y_test):
            # 상위 6개 예측 번호
            top_6 = np.argsort(pred)[-6:]
            actual_numbers = np.where(actual == 1)[0]
            
            # 일치 개수
            matches = len(set(top_6) & set(actual_numbers))
            match_scores.append(matches / 6.0)
        
        metrics['avg_match_rate'] = float(np.mean(match_scores))
        
        return metrics
    
    def save_model(self, path: str = None):
        """모델 저장"""
        if not TENSORFLOW_AVAILABLE or self.model is None:
            logging.error("저장할 모델이 없습니다.")
            return
        
        save_path = path or self.model_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self.model.save(save_path)
        logging.info(f"모델 저장됨: {save_path}")
    
    def load_model(self, path: str):
        """모델 로드"""
        if not TENSORFLOW_AVAILABLE:
            logging.error("TensorFlow가 설치되지 않아 모델을 로드할 수 없습니다.")
            return
        
        try:
            self.model = load_model(path)
            self.is_trained = True
            self.model_path = path
            logging.info(f"모델 로드됨: {path}")
        except Exception as e:
            logging.error(f"모델 로드 실패: {str(e)}")


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
    
    # LSTM 예측기 생성
    predictor = LSTMPredictor(sequence_length=50)
    
    # 데이터 분할
    train_size = int(len(winning_numbers) * 0.8)
    train_data = winning_numbers[:train_size]
    test_data = winning_numbers[train_size:]
    
    print(f"학습 데이터: {len(train_data)}개")
    print(f"테스트 데이터: {len(test_data)}개")
    
    # 모델 학습
    if not predictor.is_trained:
        print("\n모델 학습 시작...")
        predictor.train(train_data, epochs=50, batch_size=32)
    
    # 모델 평가
    print("\n모델 평가...")
    evaluation = predictor.evaluate_model(test_data)
    print(f"평가 결과: {evaluation}")
    
    # 예측 수행
    print("\n다음 회차 예측...")
    recent_numbers = winning_numbers[-50:]  # 최근 50회차
    predictions = predictor.predict_next_numbers(recent_numbers, num_predictions=5)
    
    print("\n예측 결과 (신뢰도 순):")
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred['confidence']
        print(f"{i}. {numbers} (신뢰도: {confidence:.2%})")

if __name__ == "__main__":
    main()