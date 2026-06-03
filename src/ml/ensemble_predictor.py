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
    from sklearn.model_selection import cross_val_score
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    from sklearn.multioutput import MultiOutputClassifier
    from sklearn.utils.validation import check_is_fitted
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
        self._nn_is_individual = False  # Neural Network 모델 타입 플래그
        
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
        
        # 최소 학습 데이터 요구사항 완화
        self.min_train_samples = 80  # [O] FIX: 30 -> 80 (모델 안정성 향상)
        self.min_sequence_length = 10  # 최소 시퀀스 길이

        # 모델 초기화 및 캐시된 모델 로드
        if SKLEARN_AVAILABLE:
            # 저장된 설정이 있으면 먼저 로드
            config_path = os.path.join(self.model_dir, 'ensemble_config.json')
            if os.path.exists(config_path):
                self.load_models()  # 캐시된 모델 로드
            else:
                self._initialize_models()  # 새로운 모델 초기화

    def _parse_numbers(self, item) -> List[int]:
        """다양한 형식의 당첨번호 데이터를 파싱하여 숫자 리스트로 변환

        Args:
            item: 당첨번호 데이터 (다양한 형식 지원)
                - 문자열: "1,2,3,4,5,6"
                - 튜플/리스트: (1,2,3,4,5,6) 또는 [1,2,3,4,5,6]
                - DB 형식: (round_num, (n1,n2,n3,n4,n5,n6,bonus))

        Returns:
            List[int]: 정렬된 6개 번호 리스트
        """
        if isinstance(item, str):
            # 문자열 형식: "1,2,3,4,5,6"
            return sorted([int(n) for n in item.split(',')])
        elif isinstance(item, (tuple, list)):
            if len(item) == 2 and isinstance(item[1], (tuple, list)):
                # DB 형식: (round_num, (n1,n2,n3,n4,n5,n6,bonus))
                nums = item[1]
                return sorted([int(n) for n in nums[:6]])  # 보너스 제외
            else:
                # 직접 튜플/리스트: (1,2,3,4,5,6) 또는 [1,2,3,4,5,6]
                return sorted([int(n) for n in item[:6]])
        else:
            logging.warning(f"알 수 없는 데이터 형식: {type(item)}")
            return []
    
    def _initialize_models(self):
        """모델 초기화 또는 로드"""
        # 모델 로드 상태 추적
        models_loaded = []
        
        # Random Forest - 실제 파일명에 맞게 수정
        rf_path = os.path.join(self.model_dir, 'rf.pkl')
        if os.path.exists(rf_path):
            with open(rf_path, 'rb') as f:
                self.models['rf'] = pickle.load(f)
                models_loaded.append('rf')
                logging.debug(f"Random Forest 모델 로드: {rf_path}")
        else:
            # 이전 파일명 체크 (호환성)
            old_rf_path = os.path.join(self.model_dir, 'random_forest.pkl')
            if os.path.exists(old_rf_path):
                with open(old_rf_path, 'rb') as f:
                    self.models['rf'] = pickle.load(f)
                    models_loaded.append('rf')
                    logging.debug(f"Random Forest 모델 로드 (이전 파일): {old_rf_path}")
            else:
                self.models['rf'] = self._build_random_forest()
                logging.info("Random Forest 모델 새로 생성")
        
        # XGBoost - 실제 파일명에 맞게 수정
        if XGBOOST_AVAILABLE:
            xgb_path = os.path.join(self.model_dir, 'xgb.pkl')
            if os.path.exists(xgb_path):
                with open(xgb_path, 'rb') as f:
                    self.models['xgb'] = pickle.load(f)
                    models_loaded.append('xgb')
                    logging.debug(f"XGBoost 모델 로드: {xgb_path}")
            else:
                # 이전 파일명 체크 (호환성)
                old_xgb_path = os.path.join(self.model_dir, 'xgboost.pkl')
                if os.path.exists(old_xgb_path):
                    with open(old_xgb_path, 'rb') as f:
                        self.models['xgb'] = pickle.load(f)
                        models_loaded.append('xgb')
                        logging.debug(f"XGBoost 모델 로드 (이전 파일): {old_xgb_path}")
                else:
                    self.models['xgb'] = self._build_xgboost()
                    logging.info("XGBoost 모델 새로 생성")
        
        # Neural Network - 실제 파일명에 맞게 수정
        nn_path = os.path.join(self.model_dir, 'nn.pkl')
        if os.path.exists(nn_path):
            with open(nn_path, 'rb') as f:
                loaded_nn = pickle.load(f)

                # 리스트 형태(개별 모델)는 사용 안 함 - MultiOutputClassifier만 사용
                if isinstance(loaded_nn, list):
                    logging.warning("기존 NN 모델이 리스트 형태(개별 모델)입니다. MultiOutputClassifier로 재생성합니다.")
                    self.models['nn'] = self._build_neural_network()
                    self._nn_is_individual = False
                else:
                    self.models['nn'] = loaded_nn
                    models_loaded.append('nn')
                    self._nn_is_individual = False  # 항상 MultiOutputClassifier 사용
                    logging.debug(f"Neural Network 모델 로드: {nn_path}")
        else:
            # 이전 파일명 체크 (호환성)
            old_nn_path = os.path.join(self.model_dir, 'neural_network.pkl')
            if os.path.exists(old_nn_path):
                with open(old_nn_path, 'rb') as f:
                    loaded_nn = pickle.load(f)

                    # 리스트 형태(개별 모델)는 사용 안 함
                    if isinstance(loaded_nn, list):
                        logging.warning("기존 NN 모델(이전)이 리스트 형태입니다. MultiOutputClassifier로 재생성합니다.")
                        self.models['nn'] = self._build_neural_network()
                        self._nn_is_individual = False
                    else:
                        self.models['nn'] = loaded_nn
                        models_loaded.append('nn')
                        self._nn_is_individual = False
                        logging.debug(f"Neural Network 모델 로드 (이전 파일): {old_nn_path}")
            else:
                self.models['nn'] = self._build_neural_network()
                self._nn_is_individual = False  # MultiOutputClassifier 사용
                logging.info("Neural Network 모델 새로 생성")
        
        # Scaler
        scaler_path = os.path.join(self.model_dir, 'scalers.pkl')
        if os.path.exists(scaler_path):
            try:
                with open(scaler_path, 'rb') as f:
                    self.scalers = pickle.load(f)
                
                # 로드된 scaler의 상태 확인
                # targets scaler는 사용하지 않으므로 제거
                if 'targets' in self.scalers:
                    del self.scalers['targets']
                    logging.info("targets scaler 제거 (사용하지 않음)")
                
                for scaler_name, scaler in self.scalers.items():
                    if not hasattr(scaler, 'mean_') or scaler.mean_ is None:
                        logging.warning(f"{scaler_name} scaler가 손상됨. 재초기화합니다.")
                        self.scalers[scaler_name] = StandardScaler()
                    else:
                        logging.debug(f"{scaler_name} scaler 정상 로드됨")
                        
            except Exception as e:
                logging.warning(f"Scaler 로드 실패: {e}. 새로 초기화합니다.")
                self.scalers = {
                    'features': StandardScaler()
                }
        else:
            self.scalers = {
                'features': StandardScaler()
            }
        
        # 모든 모델이 로드되었는지 확인
        # XGBoost가 없는 경우는 2개, 있는 경우는 3개 모델 필요
        required_models = ['rf', 'nn']
        if XGBOOST_AVAILABLE:
            required_models.append('xgb')
        
        # 설정 파일이 있으면 로드
        config_path = os.path.join(self.model_dir, 'ensemble_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                saved_is_trained = config.get('is_trained', False)
        else:
            saved_is_trained = False
        
        # 실제 로드된 모델과 저장된 상태를 모두 확인
        all_models_loaded = all(model in models_loaded for model in required_models)
        self.is_trained = all_models_loaded and saved_is_trained
        
        if self.is_trained:
            logging.debug(f"모든 모델이 로드됨: {models_loaded}")
        else:
            logging.debug(f"모델 학습 필요. 로드된 모델: {models_loaded}, 요구 모델: {required_models}")
    
    def _build_random_forest(self):
        """Random Forest 모델 구축 - MultiOutput으로 감싸서 반환 (ML-001 개선)"""
        base_rf = RandomForestClassifier(
            n_estimators=100,         # 50 → 100 (충분한 앙상블)
            max_depth=6,              # 3 → 6 (적절한 깊이로 패턴 학습)
            min_samples_split=10,     # 30 → 10 (더 세밀한 분할 허용)
            min_samples_leaf=4,       # 15 → 4 (리프 노드 조건 완화)
            max_features='sqrt',
            class_weight='balanced',  # 불균형 데이터 처리
            random_state=42,
            n_jobs=1  # MultiOutputClassifier가 병렬 처리를 하므로 1로 설정
        )
        return MultiOutputClassifier(base_rf, n_jobs=-1)  # 모든 코어 활용
    
    def _build_xgboost(self):
        """XGBoost 모델 구축 - MultiOutput으로 감싸서 반환 (ML-002 개선)"""
        base_xgb = xgb.XGBClassifier(
            n_estimators=150,         # 100 → 150 (예측 안정성 향상)
            max_depth=4,              # 2 → 4 (적절한 트리 깊이)
            learning_rate=0.05,       # 0.01 → 0.05 (적절한 학습률)
            subsample=0.8,            # 0.5 → 0.8 (더 많은 데이터 사용)
            colsample_bytree=0.8,     # 0.5 → 0.8 (더 많은 특성 사용)
            reg_alpha=0.5,            # 2.0 → 0.5 (L1 정규화 완화)
            reg_lambda=0.5,           # 3.0 → 0.5 (L2 정규화 완화)
            objective='binary:logistic',
            tree_method='hist',       # 빠른 히스토그램 기반 분할
            random_state=42,
            n_jobs=1  # MultiOutputClassifier가 병렬 처리를 하므로 1로 설정
        )
        return MultiOutputClassifier(base_xgb, n_jobs=-1)  # 모든 코어 활용
    
    def _build_neural_network(self):
        """Neural Network 모델 구축 - 클래스 불균형을 고려한 설정"""
        # 단순한 구조와 강한 정규화로 과적합 방지
        base_nn = MLPClassifier(
            hidden_layer_sizes=(32, 16),  # 더 단순한 구조
            activation='relu',
            solver='adam',
            alpha=0.5,  # 매우 강한 L2 정규화
            batch_size='auto',
            learning_rate='adaptive',
            learning_rate_init=0.001,
            max_iter=300,  # 적당한 학습
            shuffle=True,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,  # 검증 데이터 비율
            n_iter_no_change=20  # early stopping patience
        )
        # MultiOutputClassifier 사용
        return MultiOutputClassifier(base_nn, n_jobs=1)
    
    def _train_neural_network_safe(self, X_train, y_train):
        """안전한 Neural Network 학습 - 클래스 불균형 처리"""
        # NN 모델이 None인지 먼저 확인
        if self.models.get('nn') is None:
            logging.warning("NN 모델이 None입니다. 모델을 재생성합니다.")
            self.models['nn'] = self._build_neural_network()
            if self.models['nn'] is None:
                logging.error("NN 모델 재생성 실패. RF와 XGBoost만 사용합니다.")
                return

        # 각 번호별 출현 빈도 확인
        min_samples_per_class = 2

        # 각 출력(번호)에 대해 클래스 분포 확인
        for i in range(y_train.shape[1]):
            y_col = y_train[:, i]
            unique, counts = np.unique(y_col, return_counts=True)
            min_count = min(counts) if len(counts) > 0 else 0

            if min_count < min_samples_per_class and len(unique) > 1:
                logging.debug(f"번호 {i+1}: 클래스 불균형 감지 (최소 샘플: {min_count})")

        # 일반 학습 시도
        self.models['nn'].fit(X_train, y_train)
        self._nn_is_individual = False  # MultiOutputClassifier 사용
        logging.debug("Neural Network 학습 성공")

    def _train_neural_network_fallback(self, X_train, y_train):
        """폴백 Neural Network 학습 - 개별 이진 분류기 사용"""
        from sklearn.neural_network import MLPClassifier

        logging.info("개별 이진 분류기로 Neural Network 학습 중...")

        # 개별 분류기들을 저장할 리스트
        individual_models = []

        # 각 번호에 대해 개별적으로 학습
        for i in range(y_train.shape[1]):
            y_col = y_train[:, i]

            # 클래스가 하나뿐인 경우 스킵
            unique_classes = np.unique(y_col)
            if len(unique_classes) == 1:
                # 항상 같은 값을 예측하는 더미 모델
                individual_models.append(None)
                continue

            # 개별 MLPClassifier 생성 (더 단순한 구조)
            model = MLPClassifier(
                hidden_layer_sizes=(16,),  # 매우 단순한 구조
                activation='relu',
                solver='lbfgs',  # 작은 데이터셋에 적합
                alpha=1.0,  # 매우 강한 정규화
                max_iter=500,
                random_state=42 + i
            )

            try:
                model.fit(X_train, y_col)
                individual_models.append(model)
            except Exception as e:
                logging.debug(f"번호 {i+1} 학습 실패: {e}")
                individual_models.append(None)

        # 개별 모델들을 저장 (MultiOutputClassifier 대체)
        self.models['nn'] = individual_models
        self._nn_is_individual = True  # 개별 모델 사용 플래그
        logging.info("개별 이진 분류기 학습 완료")

    def _augment_training_data(self, winning_numbers: List[str]) -> List[str]:
        """데이터 증강으로 학습 데이터 확대
        
        통계적 특성을 유지하면서 변형된 데이터 생성
        """
        # 데이터 증강 비활성화 (과적합 방지)
        # 원본 데이터만 사용
        return list(winning_numbers)
        
        # 아래 코드는 주석 처리 (나중에 필요시 활성화)
        """
        augmented = list(winning_numbers)  # 원본 데이터 유지
        
        for combo_str in winning_numbers:
            numbers = [int(n) for n in combo_str.split(',')]
            
            # 1가지 증강 전략만 사용 (3 -> 1, 과적합 방지)
            for strategy in range(1):
                new_numbers = []
                
                if strategy == 0:
                    # 전략 1: ±2 범위 내에서 무작위 변형
                    for num in numbers:
                        noise = np.random.randint(-2, 3)
                        new_num = max(1, min(45, num + noise))
                        new_numbers.append(new_num)
                
                elif strategy == 1:
                    # 전략 2: 1-2개 번호만 교체
                    new_numbers = numbers.copy()
                    num_to_replace = np.random.randint(1, 3)
                    indices = np.random.choice(6, num_to_replace, replace=False)
                    for idx in indices:
                        # 기존 번호 제외하고 새 번호 선택
                        available = [n for n in range(1, 46) if n not in new_numbers]
                        if available:
                            new_numbers[idx] = np.random.choice(available)
                
                else:
                    # 전략 3: 통계적 특성 유지하며 생성
                    mean = np.mean(numbers)
                    std = np.std(numbers)
                    # 비슷한 평균과 표준편차를 가진 번호 생성
                    candidates = []
                    while len(candidates) < 6:
                        num = int(np.random.normal(mean, std))
                        if 1 <= num <= 45 and num not in candidates:
                            candidates.append(num)
                    new_numbers = sorted(candidates)
                
                # 중복 제거 및 정렬
                new_numbers = sorted(list(set(new_numbers)))
                
                # 6개가 되도록 조정
                if len(new_numbers) < 6:
                    available = [n for n in range(1, 46) if n not in new_numbers]
                    need = 6 - len(new_numbers)
                    new_numbers.extend(np.random.choice(available, need, replace=False))
                elif len(new_numbers) > 6:
                    new_numbers = new_numbers[:6]
                
                new_numbers = sorted(new_numbers)
                augmented.append(','.join(map(str, new_numbers)))
        
        # 중복 제거
        augmented = list(set(augmented))
        logging.info(f"데이터 증강: {len(winning_numbers)}개 → {len(augmented)}개")
        
        return augmented
        """
    
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
                numbers = self._parse_numbers(winning_numbers[i])
                if not numbers:
                    continue

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
                numbers = self._parse_numbers(winning_numbers[i])
                if not numbers:
                    continue

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
                            recent_numbers.extend(self._parse_numbers(winning_numbers[j]))
                        
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
            next_numbers = self._parse_numbers(winning_numbers[i + 1])
            if not next_numbers:
                continue

            # 45차원 이진 벡터
            target = np.zeros(45)
            for num in next_numbers:
                if 1 <= num <= 45:
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
        
        # 첫 번째 학습일 때만 info 레벨로 출력
        if not hasattr(self, '_training_logged'):
            logging.info("앙상블 모델 학습 시작...")
            self._training_logged = True
        else:
            logging.debug("앙상블 모델 학습 시작...")
        
        # 데이터 부족 체크
        if len(winning_numbers) < self.min_train_samples:
            logging.warning(f"학습 데이터 부족: {len(winning_numbers)}개 (최소 {self.min_train_samples}개 필요)")
            # 데이터 증강은 과적합 위험이 있으므로 제한적으로 사용
            if len(winning_numbers) >= 30:  # 최소 30개 이상일 때만 증강
                augmented = self._augment_training_data(winning_numbers[:int(len(winning_numbers)*0.7)])  # 70%만 증강
                winning_numbers = winning_numbers + augmented[:20]  # 최대 20개만 추가
                logging.info(f"제한적 데이터 증강 후: {len(winning_numbers)}개")
            else:
                logging.error("데이터가 너무 적어 학습할 수 없습니다.")
                return {}
        
        # 특징 추출 - 타겟 회차 제한으로 데이터 오염 방지
        # winning_numbers[:-1]에서 feature를 추출하고, targets는 [1:]에서 추출
        features = self.extract_features(winning_numbers, target_round=len(winning_numbers)-1)
        targets = self.prepare_targets(winning_numbers)
        
        # 데이터 정렬 확인
        assert len(features) == len(targets), "Features and targets length mismatch"
        
        # NaN 값 처리
        logging.info(f"특징 데이터 shape: {features.shape}")
        logging.info(f"NaN 값 개수: {features.isna().sum().sum()}")
        
        # NaN 값을 0으로 채우기 (또는 평균값으로 채우기)
        features = features.fillna(0)
        
        # 시간 기반 분할 먼저 수행 (데이터 누수 방지)
        # StandardScaler의 fit_transform을 전체 데이터에 적용하면
        # 테스트 데이터의 통계 정보가 학습에 누수됨
        split_idx = int(len(features) * (1 - test_size))

        train_features = features.values[:split_idx]
        test_features = features.values[split_idx:]
        y_train = targets[:split_idx]
        y_test = targets[split_idx:]

        # 스케일링 - 학습 데이터에서만 fit, 테스트 데이터에는 transform만
        self.scalers['features'] = StandardScaler()
        X_train = self.scalers['features'].fit_transform(train_features)
        X_test = self.scalers['features'].transform(test_features)
        
        # 각 모델 학습
        results = {}
        
        # Random Forest
        logging.debug("Random Forest 학습 중...")
        self.models['rf'].fit(X_train, y_train)
        
        # 특징 중요도 저장 (MultiOutputClassifier의 경우 각 estimator의 평균)
        if hasattr(self.models['rf'], 'estimators_'):
            feature_importances = np.mean([
                estimator.feature_importances_ 
                for estimator in self.models['rf'].estimators_
            ], axis=0)
            self.feature_importances['rf'] = feature_importances
        
        # XGBoost
        if XGBOOST_AVAILABLE and 'xgb' in self.models:
            logging.debug("XGBoost 학습 중...")
            self.models['xgb'].fit(X_train, y_train)
        
        # Neural Network - 클래스 불균형 처리 추가
        logging.debug("Neural Network 학습 중...")
        try:
            # 데이터 크기 확인
            if X_train.shape[0] < 10:
                logging.warning(f"Neural Network 학습 데이터가 너무 적습니다: {X_train.shape[0]}개")
                # 기본 모델로 재초기화
                self.models['nn'] = self._build_neural_network()
                self._nn_is_individual = False  # MultiOutputClassifier 사용
            else:
                # 클래스 불균형 체크 및 처리
                self._train_neural_network_safe(X_train, y_train)
        except Exception as e:
            error_msg = str(e)
            logging.warning(f"Neural Network 학습 실패: {e}")
            logging.debug(f"X_train shape: {X_train.shape}")
            logging.debug(f"y_train shape: {y_train.shape}")

            # 실패 시 새로운 MultiOutputClassifier로 재초기화 (리스트 사용 안 함)
            self.models['nn'] = self._build_neural_network()
            self._nn_is_individual = False  # MultiOutputClassifier 사용

            # 재시도 한 번만 허용
            if "least populated class" not in error_msg.lower():
                try:
                    logging.info("NN 모델 재초기화 후 재시도...")
                    self.models['nn'].fit(X_train, y_train)
                    logging.info("NN 모델 재학습 성공")
                except Exception as e2:
                    logging.warning(f"NN 모델 재학습도 실패: {e2}. NN 비활성화")
                    self.models['nn'] = None
                    self._nn_is_individual = False
        
        self.is_trained = True
        
        # 모델 저장
        self.save_models()
        
        # 평가
        evaluation = self.evaluate(X_test, y_test, features.columns)
        
        logging.info("앙상블 모델 학습 완료")
        return evaluation
    
    def update_hyperparameters(self, rf_params: Dict[str, Any], 
                             xgb_params: Dict[str, Any], 
                             nn_params: Dict[str, Any]):
        """하이퍼파라미터 업데이트
        
        Args:
            rf_params: Random Forest 파라미터
            xgb_params: XGBoost 파라미터
            nn_params: Neural Network 파라미터
        """
        # Random Forest 파라미터 업데이트
        # 빌더(_build_random_forest)를 재사용해 MultiOutputClassifier 래핑을 유지한다.
        # 하이퍼파라미터는 래퍼가 아닌 내부 추정기(estimator)에 estimator__ 접두사로 적용한다.
        if 'rf' not in self.models or not self.is_trained:
            self.models['rf'] = self._build_random_forest()
        if rf_params:
            self.models['rf'].set_params(
                **{f'estimator__{param}': value for param, value in rf_params.items()}
            )

        # XGBoost 파라미터 업데이트 (동일하게 MultiOutputClassifier 래핑 유지)
        if XGBOOST_AVAILABLE:
            if 'xgb' not in self.models or not self.is_trained:
                self.models['xgb'] = self._build_xgboost()
            if xgb_params:
                self.models['xgb'].set_params(
                    **{f'estimator__{param}': value for param, value in xgb_params.items()}
                )

        # Neural Network 파라미터 업데이트 (동일하게 MultiOutputClassifier 래핑 유지)
        if 'nn' not in self.models or not self.is_trained:
            self.models['nn'] = self._build_neural_network()
        if nn_params:
            self.models['nn'].set_params(
                **{f'estimator__{param}': value for param, value in nn_params.items()}
            )
        
        # 재학습 필요 플래그 - 모델이 이미 존재하면 trained 상태 유지
        # 파라미터만 업데이트하고 재학습은 필요시에만 수행
        if all(model in self.models for model in ['rf', 'xgb', 'nn']):
            # 모델이 모두 있으면 trained 상태 유지
            logging.info("앙상블 모델 하이퍼파라미터 업데이트 완료 - 학습 상태 유지")
        else:
            # 모델이 없으면 학습 필요
            self.is_trained = False
            logging.info("앙상블 모델 하이퍼파라미터 업데이트 완료 - 학습 필요")
    
    def apply_best_params(self, best_params: Dict[str, Any]):
        """최적 파라미터 적용
        
        Args:
            best_params: 최적화된 파라미터 딕셔너리
        """
        # 파라미터 분리
        rf_params = {k.replace('rf_', ''): v for k, v in best_params.items() if k.startswith('rf_')}
        xgb_params = {k.replace('xgb_', ''): v for k, v in best_params.items() if k.startswith('xgb_')}
        nn_params = {k.replace('nn_', ''): v for k, v in best_params.items() if k.startswith('nn_')}
        
        # 업데이트 실행
        self.update_hyperparameters(rf_params, xgb_params, nn_params)
        
        logging.info("최적 파라미터 적용 완료")
    
    def predict_probability(self, features: np.ndarray) -> np.ndarray:
        """앙상블 예측 (확률)
        
        Args:
            features: 특징 벡터
            
        Returns:
            np.ndarray: 각 번호의 출현 확률 (45차원)
        """
        if not self.is_trained:
            logging.warning("모델이 학습되지 않았습니다. 예측을 건너뜁니다.")
            return np.zeros(45)
        
        predictions = {}
        
        # Random Forest 예측
        try:
            # 모델이 학습되었는지 확인
            check_is_fitted(self.models['rf'])
            # MultiOutputClassifier의 predict_proba는 각 출력에 대한 확률을 리스트로 반환
            rf_proba = self.models['rf'].predict_proba(features)
            # 각 클래스에 대해 양성 클래스(1)의 확률만 추출
            # rf_proba는 리스트이므로, 각 원소에 대해 처리
            if isinstance(rf_proba, list):
                rf_pred = np.array([proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
                                   for proba in rf_proba]).T
            else:
                # 단일 출력의 경우 (호환성)
                rf_pred = rf_proba
            predictions['rf'] = rf_pred
        except Exception as e:
            if "instance is not fitted yet" in str(e):
                logging.debug(f"RF 모델이 아직 학습되지 않았습니다. 기본값 사용")
            else:
                logging.warning(f"RF 예측 실패: {e}")
            predictions['rf'] = np.ones((features.shape[0], 45)) / 45
        
        # XGBoost 예측
        if XGBOOST_AVAILABLE and 'xgb' in self.models:
            try:
                # 모델이 학습되었는지 확인
                check_is_fitted(self.models['xgb'])
                # MultiOutputClassifier의 predict_proba는 각 출력에 대한 확률을 리스트로 반환
                xgb_proba = self.models['xgb'].predict_proba(features)
                # 각 클래스에 대해 양성 클래스(1)의 확률만 추출
                # xgb_proba는 리스트이므로, 각 원소에 대해 처리
                if isinstance(xgb_proba, list):
                    xgb_pred = np.array([proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
                                        for proba in xgb_proba]).T
                else:
                    # 단일 출력의 경우 (호환성)
                    xgb_pred = xgb_proba
                predictions['xgb'] = xgb_pred
            except Exception as e:
                if "instance is not fitted yet" in str(e) or "has not been fitted" in str(e):
                    logging.debug(f"XGBoost 모델이 아직 학습되지 않았습니다. 기본값 사용")
                else:
                    logging.warning(f"XGBoost 예측 실패: {e}")
                predictions['xgb'] = np.ones((features.shape[0], 45)) / 45
        
        # Neural Network 예측
        try:
            # NN 모델이 None인 경우 (학습 실패)
            if self.models.get('nn') is None:
                logging.debug("NN 모델이 학습되지 않음. 기본값 사용")
                predictions['nn'] = np.ones((features.shape[0], 45)) / 45
            else:
                # 실제 모델 타입을 확인하여 플래그 재설정
                actual_is_individual = isinstance(self.models['nn'], list)
                if hasattr(self, '_nn_is_individual') and self._nn_is_individual != actual_is_individual:
                    logging.debug(f"NN 플래그 불일치 감지. 플래그: {self._nn_is_individual}, 실제: {actual_is_individual}. 자동 보정")
                    self._nn_is_individual = actual_is_individual

                # 개별 모델 사용 여부 확인
                if actual_is_individual:
                    # 개별 이진 분류기들로 예측
                    logging.debug("NN: 개별 모델 사용")

                    nn_predictions = []
                    for i, model in enumerate(self.models['nn']):
                        if model is None:
                            # 학습 실패한 번호는 평균 확률
                            nn_predictions.append(np.ones(features.shape[0]) * 0.133)  # 6/45
                        else:
                            try:
                                # 확률 예측
                                proba = model.predict_proba(features)
                                if proba.shape[1] > 1:
                                    nn_predictions.append(proba[:, 1])
                                else:
                                    nn_predictions.append(proba[:, 0])
                            except (ImportError, AttributeError) as e:
                                logging.debug(f"모듈 import 실패 (무시): {e}")
                                nn_predictions.append(np.ones(features.shape[0]) * 0.133)
                    predictions['nn'] = np.array(nn_predictions).T
                else:
                    # MultiOutputClassifier 사용
                    logging.debug("NN: MultiOutputClassifier 사용")

                    check_is_fitted(self.models['nn'])
                    nn_proba = self.models['nn'].predict_proba(features)
                    # 각 클래스에 대해 양성 클래스(1)의 확률만 추출
                    if isinstance(nn_proba, list):
                        # MultiOutputClassifier의 경우 리스트 반환
                        nn_pred = np.array([proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
                                           for proba in nn_proba]).T
                    else:
                        # 단일 출력의 경우
                        nn_pred = nn_proba
                    predictions['nn'] = nn_pred
        except Exception as e:
            if "instance is not fitted yet" in str(e):
                logging.debug(f"NN 모델이 아직 학습되지 않았습니다. 기본값 사용")
            elif "object is not iterable" in str(e):
                logging.warning(f"NN 예측 실패 - MultiOutputClassifier iteration 오류: {e}")
                logging.debug(f"NN 모델 타입: {type(self.models['nn'])}, 개별 플래그: {getattr(self, '_nn_is_individual', 'undefined')}")
                # 플래그 재설정 시도
                self._nn_is_individual = isinstance(self.models['nn'], list)
                logging.debug(f"플래그 재설정: {self._nn_is_individual}")
            else:
                logging.warning(f"NN 예측 실패: {e}")
            predictions['nn'] = np.ones((features.shape[0], 45)) / 45
        
        # 가중 평균 앙상블
        # predictions 중 하나를 템플릿으로 사용
        if predictions:
            template_pred = next(iter(predictions.values()))
            final_pred = np.zeros_like(template_pred)
        else:
            # 모든 예측이 실패한 경우 기본값
            final_pred = np.ones((features.shape[0], 45)) / 45
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
        if not self.is_trained:
            logging.warning("앙상블 모델이 학습되지 않았습니다. 예측을 건너뜁니다.")
            return []

        # 특징 추출
        features = self.extract_features(winning_numbers)
        
        # 최신 데이터 사용
        latest_features = features.iloc[-1:].values
        
        # 스케일링
        if hasattr(self.scalers['features'], 'mean_'):
            latest_features = self.scalers['features'].transform(latest_features)
        
        # 예측
        probabilities = self.predict_probability(latest_features)
        if probabilities.ndim > 1:
            probabilities = probabilities[0]
        
        # 확률 배열 검증
        if not isinstance(probabilities, np.ndarray) or len(probabilities) != 45:
            logging.warning(f"예상치 못한 확률 형태: {type(probabilities)}, shape: {getattr(probabilities, 'shape', 'N/A')}")
            return []
        if probabilities.sum() == 0:
            logging.warning("모델 확률 벡터가 모두 0입니다. 예측을 건너뜁니다.")
            return []
        
        # 번호 조합 생성
        predictions = []
        
        for _ in range(num_predictions):
            # 확률 기반 샘플링
            # 상위 확률에 가중치를 둔 샘플링
            weights = probabilities ** 2  # 제곱으로 상위 확률 강조
            total = weights.sum()
            if total == 0:
                logging.warning("확률 벡터 합이 0입니다. 예측을 건너뜁니다.")
                break
            weights = weights / total
            
            # 중복 없이 6개 선택
            selected_indices = np.random.choice(
                45, 6, replace=False, p=weights
            )
            selected_numbers = sorted([i + 1 for i in selected_indices])
            
            # 예측 결과 검증
            if len(selected_numbers) != 6:
                logging.error(f"예측 번호 개수 오류: {len(selected_numbers)}개")
                continue
            if any(n < 1 or n > 45 for n in selected_numbers):
                logging.error(f"예측 번호 범위 오류: {selected_numbers}")
                continue
            if len(set(selected_numbers)) != 6:
                logging.error(f"예측 번호 중복 오류: {selected_numbers}")
                continue
            
            # 예측 신뢰도 계산 (현실적인 범위로 조정)
            confidence = np.mean([probabilities[i] for i in selected_indices])
            confidence = min(confidence, 0.3)  # 최대 30%로 제한
            
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

    def predict_from_filtered_pool(self, winning_numbers_str: List[str],
                                  filtered_pool: List[List[int]],
                                  num_predictions: int = 10) -> List[Dict[str, Any]]:
        """필터링된 풀 내에서만 예측

        Args:
            winning_numbers_str: 과거 당첨번호 문자열 리스트
            filtered_pool: 필터를 통과한 조합들의 리스트
            num_predictions: 생성할 예측 조합 수

        Returns:
            List[Dict[str, Any]]: 필터링된 풀 내에서 선택된 예측 번호들
        """
        if not filtered_pool:
            logging.warning("필터링된 풀이 비어있습니다. 기본 예측 반환")
            return self.predict_next_numbers(winning_numbers_str, num_predictions)

        # 앙상블 45차원 확률 벡터 계산 (predict_next_numbers와 동일 파이프라인)
        # -> 각 조합의 스코어 = 해당 번호들의 확률 합. 가짜 신뢰도 하드코딩 금지.
        prob_vector = None
        if self.is_trained:
            try:
                features = self.extract_features(winning_numbers_str)
                latest_features = features.iloc[-1:].values
                if hasattr(self.scalers['features'], 'mean_'):
                    latest_features = self.scalers['features'].transform(latest_features)
                probabilities = self.predict_probability(latest_features)
                if probabilities.ndim > 1:
                    probabilities = probabilities[0]
                if isinstance(probabilities, np.ndarray) and len(probabilities) == 45 and probabilities.sum() > 0:
                    prob_vector = probabilities
                else:
                    logging.debug("앙상블 확률 벡터가 유효하지 않습니다(랜덤 폴백)")
            except Exception as e:
                logging.debug(f"앙상블 확률 벡터 계산 실패(랜덤 폴백): {e}")

        predictions = []
        if prob_vector is not None:
            # 각 조합의 스코어 = 해당 번호들의 앙상블 확률 합산 (LSTM과 동일 규약)
            pool_array = np.array(filtered_pool)  # (N, 6)
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
                    'selection_method': 'ensemble_weighted'
                })
        else:
            # 모델 미준비/확률 실패 시에만 랜덤 폴백 (정직하게 confidence=0.0)
            import random
            selected_combos = random.sample(list(filtered_pool), min(num_predictions, len(filtered_pool)))
            for combo in selected_combos:
                predictions.append({
                    'numbers': sorted(combo),
                    'confidence': 0.0,
                    'probability_vector': [1 / 45] * 45,
                    'from_filtered_pool': True,
                    'selection_method': 'random_fallback'
                })

        logging.info(f"필터링된 풀({len(filtered_pool)}개)에서 {len(predictions)}개 앙상블 예측 생성 "
                     f"(방법: {'앙상블 확률 가중' if prob_vector is not None else '랜덤 폴백'})")
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
        
        logging.debug(f"모델 저장 완료: {self.model_dir}")
    
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
        
        logging.debug("모델 로드 완료")


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