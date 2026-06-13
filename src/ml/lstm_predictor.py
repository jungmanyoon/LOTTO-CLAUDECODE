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

    # TensorFlow 2.x 권장 import 방식
    from tensorflow import keras
    from keras.models import Sequential, load_model
    from keras.layers import LSTM, Dense, Dropout, BatchNormalization
    from keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
    from keras.optimizers import Adam
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logging.warning("TensorFlow not available. LSTM predictor will work in limited mode.")

class LSTMPredictor:
    """LSTM 기반 로또 번호 예측기"""
    
    def __init__(self, sequence_length: int = 15, model_path: str = None):
        """
        Args:
            sequence_length: 입력 시퀀스 길이 (과거 몇 회차를 볼 것인가)
                            ML-003 개선: 50 → 15 (과적합 방지 및 메모리 70% 절감)
            model_path: 저장된 모델 경로 (None이면 새로 생성)
        """
        self.sequence_length = sequence_length
        self.model_path = model_path or 'models/lstm_lotto_predictor.h5'
        self.model = None
        self.is_trained = False
        self.scaler_params = {}
        # [C1 2026-06-13] 학습 기준 회차 스탬프 (새 회차 무효화용). ensemble과 동일 패턴.
        #  - h5만으론 학습 회차를 알 수 없어 sidecar json(_round.json)에 저장/복원한다.
        #  - None이면 '회차 미상'(레거시 h5 또는 미학습) -> main.py 가드가 재학습을 유도한다.
        #  과거 결함: h5 존재만으로 is_trained=True가 되어 새 회차가 와도 옛 가중치를 silent 재사용.
        self.trained_round = None
        self.round_path = self.model_path.replace('.h5', '_round.json')

        # 모델 아키텍처 파라미터 (ML-003 개선: 경량화)
        self.lstm_units = [64, 32, 16]    # [128, 64, 32] → [64, 32, 16]
        self.dropout_rate = 0.35  # [O] FIX: 0.2 -> 0.35 (과적합 방지)
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
                # TensorFlow/Keras/ABSL 경고 완전 억제
                import warnings
                import absl.logging
                absl.logging.set_verbosity(absl.logging.ERROR)
                
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    warnings.filterwarnings('ignore', category=UserWarning)
                    warnings.filterwarnings('ignore', message='.*compiled metrics.*')
                    warnings.filterwarnings('ignore', message='.*compile_metrics.*')
                    warnings.filterwarnings('ignore', message='.*Compiled the loaded model.*')
                    
                    # 모델 로드 (compile=False로 로드하여 경고 방지)
                    self.model = load_model(self.model_path, compile=False)
                    
                    # 로드 후 명시적으로 compile (경고 없이)
                    self.model.compile(
                        optimizer='adam',
                        loss='mse',
                        metrics=['mae']
                    )
                    
                    # Dummy 평가로 metrics 빌드 (완전히 조용하게)
                    try:
                        import numpy as np
                        # 모델의 실제 입력 차원에 맞춰 dummy 데이터 생성
                        dummy_x = np.random.random((1, self.sequence_length, self.feature_dims))
                        dummy_y = np.random.random((1, self.output_dims))
                        self.model.evaluate(dummy_x, dummy_y, verbose=0)
                    except Exception:
                        # Dummy 평가 실패는 무시 (메트릭이 처음 사용될 때 빌드됨)
                        pass
                    
                self.is_trained = True
                # [C1] 학습 회차 스탬프 복원 (sidecar 없으면 None=회차미상 -> main.py 가드가 재학습)
                self.trained_round = self._load_trained_round()
                logging.debug(f"기존 모델 로드 및 컴파일 완료: {self.model_path} (학습회차={self.trained_round})")
            except Exception as e:
                logging.warning(f"모델 로드 실패: {str(e)}. 새 모델을 생성합니다.")
                # 기존 모델 파일이 손상되었거나 구조가 맞지 않으므로 삭제
                try:
                    os.remove(self.model_path)
                    logging.info(f"손상된 모델 파일 삭제: {self.model_path}")
                except (OSError, PermissionError) as e:
                    logging.debug(f"모델 파일 삭제 실패 (무시): {e}")
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
    
    def rebuild_model(self, params: Dict[str, Any]):
        """새로운 파라미터로 모델 재구성
        
        Args:
            params: 모델 파라미터
        """
        # 파라미터 업데이트
        if 'lstm_units' in params:
            if isinstance(params['lstm_units'], int):
                self.lstm_units = [params['lstm_units'], params['lstm_units']//2, params['lstm_units']//4]
            else:
                self.lstm_units = params['lstm_units']
        
        if 'dropout_rate' in params:
            self.dropout_rate = params['dropout_rate']
        
        if 'learning_rate' in params:
            self.learning_rate = params['learning_rate']
        
        # 모델 재생성
        self.model = self._build_lstm_model()
        self.is_trained = False
        logging.info(f"LSTM 모델 재구성 완료: {params}")
    
    def update_hyperparameters(self, params: Dict[str, Any]):
        """하이퍼파라미터 업데이트"""
        self.rebuild_model(params)
    
    def apply_best_params(self, params: Dict[str, Any]):
        """최적 파라미터 적용"""
        self.rebuild_model(params)
    
    def retrain(self, winning_numbers: Optional[List[str]] = None):
        """모델 재학습

        Args:
            winning_numbers: 당첨번호 리스트 (None이면 기존 데이터 사용)
        """
        if winning_numbers is None:
            logging.warning("재학습할 데이터가 제공되지 않았습니다.")
            return

        # 데이터 준비
        X_train, y_train = self.prepare_training_data(winning_numbers)

        # 시계열 기반 분할 (데이터 누수 방지)
        val_size = max(1, int(len(X_train) * 0.2))
        gap = self.sequence_length  # 시퀀스 길이만큼 갭 확보
        split_idx = len(X_train) - val_size - gap

        if split_idx < 5:
            # 데이터가 부족한 경우 갭 없이 분할
            gap = 0
            split_idx = len(X_train) - val_size

        X_val = X_train[split_idx + gap:]
        y_val = y_train[split_idx + gap:]
        X_train_split = X_train[:split_idx]
        y_train_split = y_train[:split_idx]

        # 간단한 학습 (빠른 재학습을 위해 epoch 줄임)
        history = self.model.fit(
            X_train_split, y_train_split,
            epochs=30,
            batch_size=32,
            validation_data=(X_val, y_val),
            verbose=0
        )

        self.is_trained = True
        logging.info("LSTM 모델 재학습 완료")
        return history
    
    def train_with_validation(self, train_data: List, val_data: List) -> float:
        """검증 데이터를 사용한 학습
        
        Args:
            train_data: 학습 데이터
            val_data: 검증 데이터
            
        Returns:
            float: 검증 점수
        """
        # 데이터 준비
        X_train, y_train = self.prepare_training_data(train_data)
        X_val, y_val = self.prepare_training_data(val_data)
        
        # 학습
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=50,
            batch_size=32,
            verbose=0,
            callbacks=[
                EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)
            ]
        )
        
        # 검증 점수 계산
        val_predictions = self.model.predict(X_val, verbose=0)
        
        # 예측 정확도 계산 (각 번호의 출현 여부를 얼마나 잘 맞추는지)
        val_score = 0
        for pred, actual in zip(val_predictions, y_val):
            # 상위 6개 예측
            top_6_indices = np.argsort(pred)[-6:]
            # 실제 출현 번호
            actual_indices = np.where(actual == 1)[0]
            # 일치 개수
            matches = len(set(top_6_indices) & set(actual_indices))
            val_score += matches / 6.0
        
        val_score = val_score / len(y_val)
        self.is_trained = True
        
        logging.info(f"LSTM 검증 점수: {val_score:.4f}")
        return val_score
    
    def prepare_training_data(self, winning_numbers: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """학습 데이터 준비

        Args:
            winning_numbers: 과거 당첨번호 리스트 (다양한 형식 지원)
                - 문자열: "1,2,3,4,5,6"
                - 튜플/리스트: (1,2,3,4,5,6) 또는 [1,2,3,4,5,6]
                - DB 형식: (round_num, (n1,n2,n3,n4,n5,n6,bonus))

        Returns:
            Tuple[np.ndarray, np.ndarray]: (X_train, y_train)
        """
        # 번호를 원-핫 인코딩으로 변환
        encoded_sequences = []

        for item in winning_numbers:
            # 다양한 입력 형식 처리
            if isinstance(item, str):
                # 문자열 형식: "1,2,3,4,5,6"
                numbers = [int(n) for n in item.split(',')]
            elif isinstance(item, (tuple, list)):
                if len(item) == 2 and isinstance(item[1], (tuple, list)):
                    # DB 형식: (round_num, (n1,n2,n3,n4,n5,n6,bonus))
                    nums = item[1]
                    numbers = [int(n) for n in nums[:6]]  # 보너스 제외
                else:
                    # 직접 튜플/리스트: (1,2,3,4,5,6) 또는 [1,2,3,4,5,6]
                    numbers = [int(n) for n in item[:6]]
            else:
                logging.warning(f"알 수 없는 데이터 형식: {type(item)}")
                continue

            # 45차원 벡터로 인코딩 (각 번호의 출현 여부)
            encoded = np.zeros(self.feature_dims)
            for num in numbers:
                if 1 <= num <= 45:  # 유효한 번호만 처리
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
              batch_size: int = 32, validation_split: float = 0.2,
              trained_round: Optional[int] = None):
        """모델 학습

        Args:
            winning_numbers: 과거 당첨번호 리스트
            epochs: 학습 에폭 수
            batch_size: 배치 크기
            validation_split: 검증 데이터 비율 (시간 기반 분할에 사용)
            trained_round: [C1] 이 학습이 반영한 최신 회차. 성공 후 sidecar에 저장되어
                           다음 실행에서 '회차 불일치 시 재학습' 판단 근거가 된다.
                           호출부(main.py)에서 latest_round를 주입한다(내부 추론 금지).
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

        # 시계열 기반 분할 (데이터 누수 방지)
        # Keras의 validation_split은 데이터를 랜덤하게 셔플하므로
        # 미래 데이터가 학습에 포함되는 누수 발생 가능
        val_size = max(1, int(len(X_train) * validation_split))
        gap = self.sequence_length  # 시퀀스 길이만큼 갭 확보 (학습/검증 데이터 간 정보 누수 방지)
        split_idx = len(X_train) - val_size - gap

        if split_idx < 10:
            # 데이터가 부족한 경우 갭을 줄여서라도 분할
            gap = max(0, len(X_train) - val_size - 10)
            split_idx = len(X_train) - val_size - gap
            logging.warning(f"데이터 부족으로 갭을 {gap}으로 축소")

        X_val = X_train[split_idx + gap:]
        y_val = y_train[split_idx + gap:]
        X_train_split = X_train[:split_idx]
        y_train_split = y_train[:split_idx]

        logging.info(f"시간 기반 분할: 학습 {len(X_train_split)}개, 갭 {gap}개, 검증 {len(X_val)}개")

        # 모델 저장 디렉토리 생성
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

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

        # 모델 학습 (시간 기반 분할된 검증 데이터 사용)
        history = self.model.fit(
            X_train_split, y_train_split,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            verbose=1
        )
        
        self.is_trained = True

        # [C1] 학습 회차 스탬프 저장 (성공 후에만). 새 회차 무효화 판단 근거.
        self.trained_round = trained_round
        self._save_trained_round(trained_round)

        # 학습 결과 저장
        self._save_training_history(history)

        logging.info(f"LSTM 모델 학습 완료 (학습회차={trained_round})")
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
            logging.warning("모델이 준비되지 않았습니다. 예측을 건너뜁니다.")
            return []

        # 입력 데이터 검증
        if not recent_numbers or len(recent_numbers) == 0:
            logging.warning("입력 데이터가 없습니다. 예측을 건너뜁니다.")
            return []
        
        # 입력 데이터 준비
        if len(recent_numbers) < self.sequence_length:
            # 데이터가 부족한 경우 동적으로 sequence_length 조정
            available_length = len(recent_numbers)
            if available_length >= 10:  # 최소 10개는 있어야 함
                logging.info(f"시퀀스 길이 조정: {self.sequence_length} → {available_length}")
                # 임시로 더 짧은 시퀀스 사용
                temp_sequence_length = available_length
                recent_sequence = recent_numbers
            else:
                logging.warning(f"입력 데이터 부족: {len(recent_numbers)}개 (최소 필요: 10개)")
                return []
        else:
            temp_sequence_length = self.sequence_length
            recent_sequence = recent_numbers[-self.sequence_length:]
        
        # 인코딩
        encoded_sequence = []
        for nums_str in recent_sequence:
            numbers = [int(n) for n in nums_str.split(',')]
            encoded = np.zeros(self.feature_dims)
            for num in numbers:
                encoded[num - 1] = 1
            encoded_sequence.append(encoded)
        
        # 입력 데이터 패딩 또는 트리밍
        if len(encoded_sequence) < self.sequence_length:
            # 패딩 추가 (앞쪽에 0으로 채우기)
            padding_length = self.sequence_length - len(encoded_sequence)
            padding = [np.zeros(self.feature_dims) for _ in range(padding_length)]
            encoded_sequence = padding + encoded_sequence
        elif len(encoded_sequence) > self.sequence_length:
            # 트리밍 (최근 데이터만 사용)
            encoded_sequence = encoded_sequence[-self.sequence_length:]
        
        X = np.array([encoded_sequence])
        
        # 예측
        probabilities = self.model.predict(X, verbose=0)[0]
        
        # 예측 결과를 바탕으로 번호 조합 생성
        predictions = []
        
        for _ in range(num_predictions):
            # 확률 기반 가중 샘플링 (노이즈 최소화)
            # 확률 제곱으로 상위 번호 강조 + 미세 노이즈
            enhanced_probs = probabilities ** 2
            noise = np.random.normal(0, 0.02, size=self.feature_dims)
            enhanced_probs = np.clip(enhanced_probs + noise, 1e-10, None)
            weights = enhanced_probs / enhanced_probs.sum()

            # 가중 확률 기반 6개 선택 (랜덤이 아닌 확률 비례)
            selected_indices = np.random.choice(
                self.feature_dims, 6, replace=False, p=weights
            )
            selected_numbers = sorted([int(i) + 1 for i in selected_indices])  # [P3-3] np.int32 -> 일반 int (로그 가독성)
            
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
    
    def predict_next(self, recent_numbers: List[str]) -> Optional[List[int]]:
        """다음 회차 번호 단일 예측 (백테스팅 호환용)
        
        Args:
            recent_numbers: 최근 당첨번호 리스트
            
        Returns:
            Optional[List[int]]: 예측된 6개 번호 리스트
        """
        predictions = self.predict_next_numbers(recent_numbers, num_predictions=1)
        
        if predictions:
            return predictions[0]['numbers']
        return None
    
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

    def predict_from_filtered_pool(self, recent_numbers: List[str],
                                  filtered_pool: List[List[int]],
                                  num_predictions: int = 10) -> List[Dict[str, Any]]:
        """필터링된 풀 내에서만 예측

        Args:
            recent_numbers: 최근 당첨번호 리스트
            filtered_pool: 필터를 통과한 조합들의 리스트
            num_predictions: 생성할 예측 조합 수

        Returns:
            List[Dict[str, Any]]: 필터링된 풀 내에서 선택된 예측 번호들
        """
        if not filtered_pool:
            logging.warning("필터링된 풀이 비어있습니다. 예측을 건너뜁니다.")
            return []

        # [FIX] LSTM 확률 벡터 기반 가중 선택 (기존: 순수 랜덤 → 신뢰도 0.0)
        # 모델이 준비된 경우 LSTM 확률로 각 조합의 스코어를 계산
        prob_vector = None
        if self.model is not None and recent_numbers:
            try:
                # predict_next_numbers()와 동일한 전처리로 확률 벡터 계산
                if len(recent_numbers) < self.sequence_length:
                    recent_seq = recent_numbers
                else:
                    recent_seq = recent_numbers[-self.sequence_length:]

                encoded_sequence = []
                for nums_str in recent_seq:
                    if isinstance(nums_str, (list, tuple)):
                        numbers = [int(n) for n in nums_str]
                    else:
                        numbers = [int(n) for n in str(nums_str).split(',')]
                    encoded = np.zeros(self.feature_dims)
                    for num in numbers:
                        if 1 <= num <= 45:
                            encoded[num - 1] = 1
                    encoded_sequence.append(encoded)

                # 시퀀스 길이 맞추기 (패딩)
                if len(encoded_sequence) < self.sequence_length:
                    padding = [np.zeros(self.feature_dims)] * (self.sequence_length - len(encoded_sequence))
                    encoded_sequence = padding + encoded_sequence

                X = np.array([encoded_sequence])
                prob_vector = self.model.predict(X, verbose=0)[0]  # shape: (45,)
            except Exception as e:
                logging.debug(f"LSTM 확률 벡터 계산 실패 (랜덤 폴백): {e}")
                prob_vector = None

        predictions = []
        if prob_vector is not None and len(filtered_pool) > 0:
            # 각 조합의 스코어 = 해당 번호들의 LSTM 확률 합산
            pool_array = np.array(filtered_pool)  # (N, 6)
            # 번호 인덱스(0-based)로 확률 조회 후 합산
            scores = np.sum(prob_vector[pool_array - 1], axis=1)  # (N,)

            # 음수 방지 후 정규화 (확률 기반 가중 샘플링)
            scores = np.maximum(scores, 1e-9)
            scores /= scores.sum()

            # 확률 기반 비복원 샘플링
            n_select = min(num_predictions, len(filtered_pool))
            selected_indices = np.random.choice(len(filtered_pool), size=n_select, replace=False, p=scores)

            for idx in selected_indices:
                combo = list(filtered_pool[idx])
                confidence = float(scores[idx] * len(filtered_pool))  # 상대적 선호도 (1.0 기준)
                predictions.append({
                    'numbers': sorted(combo),
                    'confidence': min(confidence, 1.0),
                    'probability_vector': prob_vector.tolist(),
                    'from_filtered_pool': True,
                    'selection_method': 'lstm_weighted'
                })
        else:
            # 모델 미준비 시 랜덤 폴백 (이 경우에만 랜덤)
            import random
            selected_combos = random.sample(list(filtered_pool), min(num_predictions, len(filtered_pool)))
            for combo in selected_combos:
                predictions.append({
                    'numbers': sorted(combo),
                    'confidence': 0.0,
                    'probability_vector': [1/45] * 45,
                    'from_filtered_pool': True,
                    'selection_method': 'random_fallback'
                })

        logging.info(f"필터링된 풀({len(filtered_pool)}개)에서 {len(predictions)}개 예측 생성 "
                     f"(방법: {'LSTM 확률 가중' if prob_vector is not None else '랜덤 폴백'})")
        return predictions
    
    def _save_trained_round(self, trained_round):
        """[C1] 학습 기준 회차를 sidecar json에 원자적으로 저장(멀티프로세스 IO 안전).

        trained_round=None이면 저장하지 않는다(회차 미상 표시 유지). tmp->os.replace로
        부분 작성 파일을 다른 프로세스가 읽는 것을 방지(MEMORY #10 원자적 쓰기 패턴)."""
        if trained_round is None:
            return
        try:
            os.makedirs(os.path.dirname(self.round_path), exist_ok=True)
            tmp = self.round_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'trained_round': int(trained_round)}, f)
            os.replace(tmp, self.round_path)
        except Exception as e:
            logging.debug(f"LSTM 학습회차 sidecar 저장 실패(무시): {e}")

    def _load_trained_round(self):
        """[C1] sidecar json에서 학습 기준 회차 복원 (없거나 손상 시 None)."""
        try:
            if os.path.exists(self.round_path):
                with open(self.round_path, 'r', encoding='utf-8') as f:
                    val = json.load(f).get('trained_round')
                    return int(val) if val is not None else None
        except Exception as e:
            logging.debug(f"LSTM 학습회차 sidecar 로드 실패(무시): {e}")
        return None

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
        with open(history_path, 'w', encoding='utf-8') as f:
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
            # TensorFlow/Keras/ABSL 경고 완전 억제
            import warnings
            import absl.logging
            absl.logging.set_verbosity(absl.logging.ERROR)
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                warnings.filterwarnings('ignore', category=UserWarning)
                warnings.filterwarnings('ignore', message='.*compiled metrics.*')
                warnings.filterwarnings('ignore', message='.*compile_metrics.*')
                warnings.filterwarnings('ignore', message='.*Compiled the loaded model.*')
                
                # 모델 로드 (compile=False로 로드하여 경고 방지)
                self.model = load_model(path, compile=False)
                
                # 로드 후 명시적으로 compile
                self.model.compile(
                    optimizer='adam',
                    loss='mse',
                    metrics=['mae']
                )
                
                # Dummy 평가로 metrics 빌드 (모델 입력 shape: (1, seq_len, feature_dims=45))
                import numpy as np
                dummy_x = np.zeros((1, self.sequence_length, self.feature_dims))
                dummy_y = np.zeros((1, self.feature_dims))
                self.model.evaluate(dummy_x, dummy_y, verbose=0)
                
            self.is_trained = True
            self.model_path = path
            logging.debug(f"모델 로드 및 컴파일 완료: {path}")
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
    
    # LSTM 예측기 생성 (ML-003: 기본값 15로 변경됨)
    predictor = LSTMPredictor(sequence_length=15)
    
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