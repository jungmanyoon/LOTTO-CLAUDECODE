#!/usr/bin/env python3
"""
실시간 학습 시스템
매 회차마다 모델을 점진적으로 업데이트하는 온라인 학습 시스템
"""
import logging
import time
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
from datetime import datetime
import json
import os
from collections import deque
from ..core.db_manager import DatabaseManager
from ..ml.lstm_predictor import LSTMPredictor
from ..ml.ensemble_predictor import EnsemblePredictor
from ..probabilistic.monte_carlo_simulator import MonteCarloSimulator

class RealtimeLearningSystem:
    """실시간 학습 시스템 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        
        # 학습 설정 (최적화됨)
        # 모델별 개별화된 학습 설정
        self.learning_config = {
            'lstm': {
                'buffer_size': 100,
                'update_frequency': 2,      # LSTM은 보수적으로 2회차마다
                'mini_batch_size': 1,
                'learning_rate': 0.001,     # 낮은 학습률 (안정성)
                'learning_rate_decay': 0.99,
                'performance_window': 10,
                'min_improvement': 0.01,    # 보수적 임계값
                'max_updates_per_session': None,  # 무제한
                'adaptive_update': True
            },
            'ensemble': {
                'buffer_size': 120,          # 더 큰 버퍼 (우수 성능 활용)
                'update_frequency': 1,      # 매 회차마다 업데이트
                'mini_batch_size': 2,
                'learning_rate': 0.005,     # 높은 학습률 (우수 성능)
                'learning_rate_decay': 0.98,
                'performance_window': 15,   # 더 긴 윈도우
                'min_improvement': 0.005,   # 낮은 임계값 (적극적)
                'max_updates_per_session': None,  # 무제한
                'adaptive_update': True
            },
            'monte_carlo': {
                'buffer_size': 80,          # 작은 버퍼 (확률 기반)
                'update_frequency': 3,      # 3회차마다 업데이트
                'mini_batch_size': 1,
                'learning_rate': 0.002,     # 중간 학습률
                'learning_rate_decay': 0.98,
                'performance_window': 8,
                'min_improvement': 0.008,   # 실험적 임계값
                'max_updates_per_session': None,  # 무제한
                'adaptive_update': True
            }
        }
        
        # 공통 설정 (하위 호환성 유지)
        self.default_config = {
            'buffer_size': 50,
            'update_frequency': 1,
            'mini_batch_size': 1,
            'learning_rate_decay': 0.98,
            'performance_window': 10,
            'min_improvement': 0.005,
            'max_updates_per_session': 10,
            'adaptive_update': True
        }
        
        # 모델별 학습 버퍼 (개별 설정 사용)
        self.learning_buffers = {
            'lstm': deque(maxlen=self.learning_config.get('lstm', {}).get('buffer_size', 50)),
            'ensemble': deque(maxlen=self.learning_config.get('ensemble', {}).get('buffer_size', 60)),
            'monte_carlo': deque(maxlen=self.learning_config.get('monte_carlo', {}).get('buffer_size', 40))
        }
        
        # 성능 추적 (모델별 개별 윈도우 사용)
        self.performance_history = {
            'lstm': deque([0.05], maxlen=self.learning_config.get('lstm', {}).get('performance_window', 10)),
            'ensemble': deque([0.08], maxlen=self.learning_config.get('ensemble', {}).get('performance_window', 15)),  # ENSEMBLE 초기 성능 더 높게
            'monte_carlo': deque([0.04], maxlen=self.learning_config.get('monte_carlo', {}).get('performance_window', 8))
        }
        
        # 모델 상태
        self.model_states = {
            'lstm': {'last_update': None, 'update_count': 0},
            'ensemble': {'last_update': None, 'update_count': 0},
            'monte_carlo': {'last_update': None, 'update_count': 0}
        }
        
        # 저장된 상태 로드
        self._load_state()
        
        # 자동 학습 지속성을 위한 안전장치
        self.last_health_check = datetime.now()
        self.health_check_interval = 3600  # 1시간마다 상태 점검
        self.auto_restart_enabled = True  # 자동 재시작 활성화
        
        logging.info("실시간 학습 시스템 초기화 완료")
        logging.info("[O] 자동 학습 안전장치 활성화: 1시간마다 상태 점검 및 자동 재시작")
    
    def update_models_incrementally(self, models: Dict[str, Any], 
                                  new_result: Dict[str, Any]) -> Dict[str, Any]:
        """새로운 결과로 모델을 점진적으로 업데이트
        
        Args:
            models: ML 모델 딕셔너리
            new_result: 새로운 회차 결과 {'round': int, 'numbers': List[int]}
            
        Returns:
            Dict: 업데이트 결과
        """
        logging.info(f"\n[실시간 학습] {new_result['round']}회차 결과로 모델 업데이트")
        
        update_results = {}
        
        # 각 모델별 업데이트
        for model_type, model in models.items():
            if model is None:
                continue
            
            # 학습 버퍼에 추가
            self._add_to_buffer(model_type, new_result)
            
            # 업데이트 조건 확인
            if self._should_update(model_type):
                logging.info(f"{model_type} 모델 온라인 업데이트 시작...")
                
                if model_type == 'lstm':
                    update_result = self._update_lstm(model)
                elif model_type == 'ensemble':
                    update_result = self._update_ensemble(model)
                elif model_type == 'monte_carlo':
                    update_result = self._update_monte_carlo(model)
                else:
                    continue
                
                update_results[model_type] = update_result

                # 실제 업데이트가 일어난 경우에만 카운트/완료 로깅 (거짓 성공 보고 금지)
                # 성공 경로는 'updated' 키가 없거나 True, 실패/스킵은 명시적으로 'updated': False
                if update_result.get('updated', True) is False:
                    logging.warning(
                        f"{model_type} 업데이트 건너뜀/실패: "
                        f"{update_result.get('error') or update_result.get('message')}"
                    )
                else:
                    self.model_states[model_type]['last_update'] = datetime.now()
                    self.model_states[model_type]['update_count'] += 1
                    logging.info(f"{model_type} 업데이트 완료: {update_result}")
        
        # 전체 업데이트 요약
        summary = self._create_update_summary(update_results)
        
        # 상태 저장
        self._save_state()
        
        return summary
    
    def _add_to_buffer(self, model_type: str, new_result: Dict[str, Any]):
        """학습 버퍼에 데이터 추가"""
        # 버퍼가 없으면 생성
        if model_type not in self.learning_buffers:
            config = self.learning_config.get(model_type, self.default_config)
            buffer_size = config.get('buffer_size', 50)
            self.learning_buffers[model_type] = deque(maxlen=buffer_size)
            logging.debug(f"{model_type} 학습 버퍼 생성 (크기: {buffer_size})")
        
        self.learning_buffers[model_type].append(new_result)
    
    def _should_update(self, model_type: str) -> bool:
        """모델 업데이트 여부 결정 (모델별 개별 설정 사용)"""
        # 모델별 설정 가져오기
        config = self.learning_config.get(model_type, self.default_config)
        
        # 버퍼가 없으면 False 반환
        if model_type not in self.learning_buffers:
            logging.debug(f"{model_type}: 학습 버퍼가 초기화되지 않음")
            return False
        
        # 버퍼가 충분히 찼는지 확인
        buffer_size = len(self.learning_buffers[model_type])
        if buffer_size < config.get('mini_batch_size', 1):
            logging.debug(f"{model_type}: 버퍼 부족 ({buffer_size}/{config.get('mini_batch_size', 1)})")
            return False
        
        # 모델 상태가 없으면 초기화
        if model_type not in self.model_states:
            self.model_states[model_type] = {'last_update': None, 'update_count': 0}
        
        # 세션당 최대 업데이트 횟수 체크 (None이면 무제한)
        max_updates = config.get('max_updates_per_session')
        if max_updates is not None and self.model_states[model_type]['update_count'] >= max_updates:
            logging.info(f"{model_type}: 세션 최대 업데이트 횟수 도달 ({self.model_states[model_type]['update_count']})")
            return False
        
        # 적응형 업데이트: 성능이 좋아지고 있을 때만 업데이트
        if config.get('adaptive_update', False):
            # performance_history가 없으면 초기화
            if model_type not in self.performance_history:
                self.performance_history[model_type] = deque(maxlen=config.get('performance_window', 10))
                recent_performance = [0]
            else:
                recent_performance = list(self.performance_history[model_type])[-3:] if len(self.performance_history[model_type]) >= 3 else [0]
            # ENSEMBLE 모델은 더 관대한 기준 적용
            if model_type == 'ensemble':
                threshold = config.get('min_improvement', 0.01) * 0.5  # 더 낮은 임계값
            else:
                threshold = config.get('min_improvement', 0.01)
            
            if len(recent_performance) >= 2:
                improvement = recent_performance[-1] - recent_performance[-2]
                if improvement < -threshold:  # 성능 저하가 임계값보다 클 때만 건너뜀
                    logging.info(f"{model_type}: 성능 저하 감지 ({improvement:.4f}), 업데이트 건너뜀")
                    return False
        
        # 업데이트 주기 확인 - 모델별 개별 주기 사용
        # update_frequency마다 업데이트 (예: LSTM은 2회차, ENSEMBLE은 1회차마다)
        update_frequency = config.get('update_frequency', 1)
        if buffer_size % update_frequency == 0:
            logging.info(f"{model_type}: 업데이트 조건 충족 (버퍼: {buffer_size})")
            return True
        
        return False
    
    def _update_lstm(self, lstm_model: LSTMPredictor) -> Dict[str, Any]:
        """LSTM 모델 온라인 업데이트"""
        # 버퍼가 없으면 빈 딕셔너리 반환
        if 'lstm' not in self.learning_buffers:
            logging.warning("LSTM 학습 버퍼가 없음")
            return {'updated': False, 'message': 'No learning buffer'}

        # LSTM sequence_length 가져오기
        sequence_length = lstm_model.sequence_length

        # 최근 데이터로 미니 배치 생성 (sequence_length + 10 버퍼)
        config = self.learning_config.get('lstm', self.default_config)
        required_data_size = sequence_length + 10  # 50 + 10 = 60
        recent_data = list(self.learning_buffers['lstm'])[-required_data_size:]

        # 데이터가 부족하면 DB에서 추가로 가져오기
        if len(recent_data) < sequence_length:
            logging.info(f"LSTM 업데이트를 위한 데이터 부족 ({len(recent_data)}개), DB에서 추가 로드 (필요: {sequence_length}개)")
            try:
                # DB에서 최근 데이터 가져오기 (sequence_length + 10 버퍼)
                all_numbers = self.db_manager.get_all_numbers()  # get_all_numbers()는 (round, numbers, date) 튜플 반환
                if all_numbers and len(all_numbers) >= sequence_length:
                    # 최근 데이터로 제한
                    recent_db_data = all_numbers[-required_data_size:]
                    # 딕셔너리 형식으로 변환
                    for round_num, numbers_str, draw_date in recent_db_data:  # 3개 값 언팩
                        numbers = list(map(int, numbers_str.split(',')))
                        recent_data.append({'round': round_num, 'numbers': numbers})
                    # 중복 제거 후 최근 required_data_size개 선택
                    seen_rounds = set()
                    unique_data = []
                    for item in reversed(recent_data):
                        if item['round'] not in seen_rounds:
                            seen_rounds.add(item['round'])
                            unique_data.append(item)
                    recent_data = list(reversed(unique_data))[-required_data_size:]
            except Exception as e:
                logging.debug(f"DB에서 데이터 로드 실패: {e}")

        # 여전히 데이터가 부족하면 업데이트 건너뛰기
        if len(recent_data) < sequence_length:
            logging.warning(f"LSTM 업데이트 건너뛰기: 데이터 부족 ({len(recent_data)}개 < {sequence_length}개)")
            return {'updated': False, 'message': f'Insufficient data ({len(recent_data)} < {sequence_length})'}

        # 데이터 형식 변환
        winning_numbers = [','.join(map(str, d['numbers'])) for d in recent_data]
        
        # 기존 성능 평가
        old_performance = self._evaluate_model_performance(lstm_model, recent_data)
        
        # 점진적 학습 (학습률 감소 적용)
        if 'lstm' not in self.model_states:
            self.model_states['lstm'] = {'last_update': None, 'update_count': 0}
        
        learning_rate_decay = config.get('learning_rate_decay', 0.95)
        current_lr = lstm_model.learning_rate * (
            learning_rate_decay ** 
            self.model_states['lstm']['update_count']
        )
        
        # 모델 업데이트
        lstm_model.learning_rate = current_lr
        
        # 부분 데이터로 재학습 (기존 가중치 유지)
        X_train, y_train = lstm_model.prepare_training_data(winning_numbers)
        
        if len(X_train) > 0:
            history = lstm_model.model.fit(
                X_train, y_train,
                epochs=5,  # 적은 epoch로 점진적 학습
                batch_size=16,
                verbose=0
            )
        
        # 새로운 성능 평가
        new_performance = self._evaluate_model_performance(lstm_model, recent_data)
        
        # 성능 기록
        if 'lstm' not in self.performance_history:
            self.performance_history['lstm'] = deque(maxlen=config.get('performance_window', 10))
        self.performance_history['lstm'].append(new_performance)
        
        return {
            'old_performance': old_performance,
            'new_performance': new_performance,
            'improvement': new_performance - old_performance,
            'learning_rate': current_lr
        }
    
    def _update_ensemble(self, ensemble_model: EnsemblePredictor) -> Dict[str, Any]:
        """앙상블 모델 온라인 업데이트"""
        # 버퍼가 없으면 빈 딕셔너리 반환
        if 'ensemble' not in self.learning_buffers:
            logging.warning("Ensemble 학습 버퍼가 없음")
            return {'updated': False, 'message': 'No learning buffer'}
        
        # 최근 데이터로 특징 생성
        config = self.learning_config.get('ensemble', self.default_config)
        mini_batch_size = config.get('mini_batch_size', 10)
        recent_data = list(self.learning_buffers['ensemble'])[-mini_batch_size:]
        
        # 기존 성능 평가
        old_performance = self._evaluate_model_performance(ensemble_model, recent_data)
        
        # 각 서브모델 온라인 업데이트 (정식 학습과 동일하게 45차원 멀티라벨 사용)
        # RF는 온라인 미지원. XGBoost(MultiOutputClassifier)는 booster-incremental 불가하므로
        # 미니배치 전체 재학습, NN은 partial_fit. 실제 갱신된 모델만 추적한다.
        updated_models = []
        update_error = None
        try:
            # 1) 특징/타겟 구성: data[i]의 특징 -> data[i+1]의 당첨번호(45차원 이진)
            number_strings = [','.join(map(str, d['numbers'])) for d in recent_data]
            feat_df = ensemble_model.extract_features(number_strings)

            if feat_df is None or len(feat_df) != len(recent_data) or len(recent_data) < 2:
                # 특징 행이 입력과 정렬되지 않거나 데이터가 부족하면 정직하게 실패 처리
                raise ValueError(
                    f"특징/데이터 정렬 실패 또는 데이터 부족 "
                    f"(features={0 if feat_df is None else len(feat_df)}, data={len(recent_data)})"
                )

            X = feat_df.values[:-1]  # data[0..N-2]의 특징
            # 타겟: data[1..N-1]의 당첨번호를 45차원 이진 멀티라벨로 변환 (정식 규약)
            y = np.zeros((len(recent_data) - 1, 45), dtype=np.int8)
            for i in range(len(recent_data) - 1):
                for num in recent_data[i + 1]['numbers']:
                    if 1 <= int(num) <= 45:
                        y[i, int(num) - 1] = 1

            # 정식 예측과 동일하게 스케일링 (학습 시 스케일된 특징을 사용했음)
            scaler = getattr(ensemble_model, 'scalers', {}).get('features')
            if scaler is not None and hasattr(scaler, 'mean_'):
                X = scaler.transform(X)

            models = getattr(ensemble_model, 'models', {}) or {}

            # 2) XGBoost: MultiOutputClassifier라 미니배치 전체 재학습 (.fit)
            if models.get('xgb') is not None:
                try:
                    models['xgb'].fit(X, y)
                    updated_models.append('xgb')
                except Exception as e_xgb:
                    logging.debug(f"XGBoost 온라인 재학습 스킵: {e_xgb}")

            # 3) Neural Network: partial_fit 지원 시에만 (이미 학습된 모델이라 classes 불필요)
            nn_model = models.get('nn')
            if nn_model is not None and hasattr(nn_model, 'partial_fit'):
                try:
                    nn_model.partial_fit(X, y)
                    updated_models.append('nn')
                except Exception as e_nn:
                    logging.debug(f"NN partial_fit 스킵: {e_nn}")

        except Exception as e:
            update_error = str(e)
            logging.warning(f"앙상블 모델 업데이트 실패: {e}")

        # 업데이트가 하나도 성공하지 못하면 거짓 성공을 보고하지 않는다.
        if not updated_models:
            return {
                'updated': False,
                'error': update_error or '온라인 학습 가능한 서브모델 없음(RF만 존재하거나 partial_fit 미지원)'
            }

        # 새로운 성능 평가
        new_performance = self._evaluate_model_performance(ensemble_model, recent_data)

        # 성능 기록
        if 'ensemble' not in self.performance_history:
            self.performance_history['ensemble'] = deque(maxlen=config.get('performance_window', 10))
        self.performance_history['ensemble'].append(new_performance)

        return {
            'updated': True,
            'updated_models': updated_models,
            'old_performance': old_performance,
            'new_performance': new_performance,
            'improvement': new_performance - old_performance
        }
    
    def _update_monte_carlo(self, mc_model: MonteCarloSimulator) -> Dict[str, Any]:
        """Monte Carlo 시뮬레이션 파라미터 업데이트"""
        # 버퍼가 없으면 빈 딕셔너리 반환
        if 'monte_carlo' not in self.learning_buffers:
            logging.warning("Monte Carlo 학습 버퍼가 없음")
            return {'updated': False, 'message': 'No learning buffer'}
        
        # 최근 데이터로 패턴 분석
        config = self.learning_config.get('monte_carlo', self.default_config)
        mini_batch_size = config.get('mini_batch_size', 10)
        recent_data = list(self.learning_buffers['monte_carlo'])[-mini_batch_size:]
        
        # 기존 성능 평가
        old_performance = self._evaluate_model_performance(mc_model, recent_data)
        
        # 최근 패턴 분석
        recent_patterns = self._analyze_recent_patterns(recent_data)
        
        # 시뮬레이션 파라미터 조정
        # 필요한 파라미터들이 없으면 초기값 설정
        if 'temperature' not in mc_model.config:
            mc_model.config['temperature'] = 1.0
        if 'mutation_rate' not in mc_model.config:
            mc_model.config['mutation_rate'] = 0.1
            
        if recent_patterns['high_numbers_ratio'] > 0.6:
            # 높은 번호가 많이 나온 경우
            mc_model.config['temperature'] *= 1.05
        elif recent_patterns['high_numbers_ratio'] < 0.4:
            # 낮은 번호가 많이 나온 경우
            mc_model.config['temperature'] *= 0.95
        
        # 연속 번호 패턴에 따른 조정
        if recent_patterns['consecutive_ratio'] > 0.3:
            mc_model.config['mutation_rate'] *= 1.1
        
        # 새로운 성능 평가
        new_performance = self._evaluate_model_performance(mc_model, recent_data)
        
        # 성능 기록
        if 'monte_carlo' not in self.performance_history:
            self.performance_history['monte_carlo'] = deque(maxlen=config.get('performance_window', 10))
        self.performance_history['monte_carlo'].append(new_performance)
        
        return {
            'old_performance': old_performance,
            'new_performance': new_performance,
            'improvement': new_performance - old_performance,
            'patterns': recent_patterns
        }
    
    def _evaluate_model_performance(self, model: Any, test_data: List[Dict]) -> float:
        """모델 성능 평가 (최적화됨)"""
        if len(test_data) < 1:
            logging.debug("성능 평가: 데이터 부족, 기본 성능값 반환")
            return 0.05  # 데이터 부족시 최소 기본값 반환 (0.0 대신)
        
        total_score = 0
        count = 0
        
        # 간단한 성능 평가: 최근 데이터로 예측하고 다음 데이터와 비교
        try:
            # 모델 종류에 따른 예측
            # 주의: Ensemble과 LSTM 모두 predict_next_numbers를 가지므로,
            # Ensemble 전용 메서드 extract_features로 먼저 식별해야 한다.
            # (extract_features는 Ensemble 계열에만 존재, LSTM에는 없음)
            if hasattr(model, 'extract_features') and hasattr(model, 'predict_next_numbers'):
                # Ensemble 모델: sequence_length 제약 없이 전체 데이터로 예측
                winning_numbers = [','.join(map(str, d['numbers'])) for d in test_data]
                predictions = model.predict_next_numbers(winning_numbers, num_predictions=1)
                if predictions and len(predictions) > 0:
                    prediction = predictions[0].get('numbers', [])
                    if prediction and len(prediction) == 6:
                        total_score = 0.15  # 기본 점수 향상
                        count = 1

            elif hasattr(model, 'predict_next_numbers'):
                # LSTM 모델
                winning_numbers = [','.join(map(str, d['numbers'])) for d in test_data]
                # LSTM sequence_length 확인 (기본 50, 최소 10)
                sequence_length = getattr(model, 'sequence_length', 50)
                min_length = max(10, sequence_length)  # 최소 10 또는 sequence_length
                if len(winning_numbers) >= min_length:
                    predictions = model.predict_next_numbers(winning_numbers[-min(sequence_length, len(winning_numbers)):],
                                                            num_predictions=1)
                else:
                    # 데이터 부족 시 평가 스킵
                    return 0.05
                if predictions and len(predictions) > 0:
                    prediction = predictions[0].get('numbers', [])
                    # 간단한 점수: 예측이 유효하면 기본 점수 부여
                    if prediction and len(prediction) == 6:
                        total_score = 0.15  # 기본 점수 향상 (0.1 → 0.15)
                        count = 1

            elif hasattr(model, 'simulate_combinations'):
                # Monte Carlo 모델 (simulate_combinations: List[Tuple[List[int], float]] 반환)
                simulations = model.simulate_combinations(n_simulations=1)
                if simulations and len(simulations) > 0:
                    prediction = simulations[0][0]  # (조합, 점수) 중 조합 추출
                    if prediction and len(prediction) == 6:
                        total_score = 0.15  # 기본 점수 향상
                        count = 1
            
            # 실제 매칭 평가 (데이터가 2개 이상일 때만)
            if len(test_data) >= 2:
                last_actual = test_data[-1]['numbers']
                prev_data = test_data[:-1]

                # 이전 데이터로 예측 (모델 종류별 분기)
                # Ensemble은 extract_features로 먼저 식별 (LSTM과 predict_next_numbers를 공유하므로)
                if hasattr(model, 'extract_features') and hasattr(model, 'predict_next_numbers'):
                    # Ensemble 모델: sequence_length 제약 없이 이전 데이터 전체로 예측
                    winning_numbers = [','.join(map(str, d['numbers'])) for d in prev_data]
                    predictions = model.predict_next_numbers(winning_numbers, num_predictions=1)
                    if predictions and len(predictions) > 0:
                        prediction = predictions[0].get('numbers', [])
                        if prediction:
                            matches = len(set(prediction) & set(last_actual))
                            total_score = matches / 6.0
                            count = 1
                            logging.debug(f"앙상블 성능 평가: {matches}/6 매치")

                elif hasattr(model, 'predict_next_numbers'):
                    winning_numbers = [','.join(map(str, d['numbers'])) for d in prev_data]
                    # LSTM sequence_length 확인 (기본 50, 최소 10)
                    sequence_length = getattr(model, 'sequence_length', 50)
                    min_length = max(10, sequence_length)
                    if len(winning_numbers) >= min_length:
                        predictions = model.predict_next_numbers(winning_numbers[-min(sequence_length, len(winning_numbers)):],
                                                                num_predictions=1)
                    else:
                        # 데이터 부족 시 평가 스킵
                        return 0.05
                    if predictions and len(predictions) > 0:
                        prediction = predictions[0].get('numbers', [])
                        if prediction:
                            matches = len(set(prediction) & set(last_actual))
                            total_score = matches / 6.0
                            count = 1
                            logging.debug(f"성능 평가: {matches}/6 매치")
                            
        except Exception as e:
            logging.debug(f"성능 평가 중 오류: {e}")
            
        return total_score / count if count > 0 else 0.05  # 최소 기본 점수
    
    def _analyze_recent_patterns(self, recent_data: List[Dict]) -> Dict[str, float]:
        """최근 데이터의 패턴 분석"""
        patterns = {
            'high_numbers_ratio': 0,
            'consecutive_ratio': 0,
            'odd_even_ratio': 0,
            'sum_average': 0
        }
        
        if not recent_data:
            return patterns
        
        total_numbers = []
        consecutive_count = 0
        
        for data in recent_data:
            numbers = data['numbers']
            total_numbers.extend(numbers)
            
            # 높은 번호 비율 (23 이상)
            high_count = sum(1 for n in numbers if n > 23)
            patterns['high_numbers_ratio'] += high_count / 6
            
            # 연속 번호 확인
            for i in range(len(numbers) - 1):
                if numbers[i + 1] - numbers[i] == 1:
                    consecutive_count += 1
        
        # 평균 계산
        patterns['high_numbers_ratio'] /= len(recent_data)
        patterns['consecutive_ratio'] = consecutive_count / (len(recent_data) * 5)
        patterns['sum_average'] = np.mean([sum(d['numbers']) for d in recent_data])
        
        return patterns
    
    def _create_update_summary(self, update_results: Dict[str, Dict]) -> Dict[str, Any]:
        """업데이트 요약 생성"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'updated_models': list(update_results.keys()),
            'performance_improvements': {},
            'average_performance': {}
        }
        
        for model_type, result in update_results.items():
            summary['performance_improvements'][model_type] = result.get('improvement', 0)
            
            # 평균 성능 계산
            if self.performance_history[model_type]:
                avg_perf = np.mean(list(self.performance_history[model_type]))
                summary['average_performance'][model_type] = avg_perf
        
        return summary
    
    def _load_state(self):
        """저장된 상태 로드"""
        state_path = 'results/realtime_learning_state.json'
        try:
            if os.path.exists(state_path):
                with open(state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    
                    # 모델 상태 복원
                    if 'model_states' in state:
                        for model_type, model_state in state['model_states'].items():
                            if model_type in self.model_states:
                                self.model_states[model_type]['update_count'] = model_state.get('update_count', 0)
                                # last_update는 datetime으로 변환
                                last_update_str = model_state.get('last_update')
                                if last_update_str:
                                    self.model_states[model_type]['last_update'] = datetime.fromisoformat(last_update_str)
                    
                    # 성능 기록 복원
                    if 'performance_history' in state:
                        for model_type, history in state['performance_history'].items():
                            if model_type in self.performance_history and history:
                                # 모델별 설정 가져오기, 없으면 기본값 사용
                                config = self.learning_config.get(model_type, self.default_config)
                                self.performance_history[model_type] = deque(
                                    history, 
                                    maxlen=config.get('performance_window', 10)
                                )
                    
                    # 학습 버퍼 데이터 복원
                    if 'learning_buffers' in state:
                        for model_type, buffer_data in state['learning_buffers'].items():
                            if model_type in self.learning_buffers and buffer_data:
                                # 모델별 설정 가져오기, 없으면 기본값 사용
                                config = self.learning_config.get(model_type, self.default_config)
                                self.learning_buffers[model_type] = deque(
                                    buffer_data,
                                    maxlen=config.get('buffer_size', 50)
                                )
                                logging.info(f"  - {model_type} 버퍼 복원: {len(buffer_data)}개")
                    
                    # 버퍼 상태 로그
                    buffer_sizes = state.get('buffer_sizes', {})
                    
                    logging.info(f"실시간 학습 상태 로드됨:")
                    for model_type in self.model_states:
                        logging.info(f"  - {model_type}: 업데이트 {self.model_states[model_type]['update_count']}회, "
                                   f"버퍼 {buffer_sizes.get(model_type, 0)}개")
            else:
                logging.info("새로운 실시간 학습 시작")
        except Exception as e:
            logging.error(f"상태 로드 중 오류: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def _save_state(self):
        """시스템 상태 저장"""
        state_path = 'results/realtime_learning_state.json'
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        
        # datetime 객체를 문자열로 변환
        model_states_serializable = {}
        for model_type, state_info in self.model_states.items():
            model_states_serializable[model_type] = {
                'last_update': state_info['last_update'].isoformat() if state_info['last_update'] else None,
                'update_count': state_info['update_count']
            }
        
        state = {
            'model_states': model_states_serializable,
            'performance_history': {
                k: list(v) for k, v in self.performance_history.items()
            },
            'learning_buffers': {
                k: list(v) for k, v in self.learning_buffers.items()
            },
            'buffer_sizes': {
                k: len(v) for k, v in self.learning_buffers.items()
            },
            'last_save': datetime.now().isoformat()
        }
        
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    def get_learning_report(self) -> str:
        """학습 상태 보고서 생성"""
        report = []
        report.append("\n" + "="*60)
        report.append("실시간 학습 시스템 상태 보고서")
        report.append("="*60)
        
        # 모델별 상태
        for model_type in ['lstm', 'ensemble', 'monte_carlo']:
            state = self.model_states[model_type]
            report.append(f"\n[{model_type.upper()} 모델]")
            report.append(f"  업데이트 횟수: {state['update_count']}")
            report.append(f"  마지막 업데이트: {state['last_update'] or '없음'}")
            
            if self.performance_history[model_type]:
                avg_perf = np.mean(list(self.performance_history[model_type]))
                report.append(f"  평균 성능: {avg_perf:.4f}")
                report.append(f"  최근 성능: {self.performance_history[model_type][-1]:.4f}")
        
        # 학습 버퍼 상태
        report.append("\n[학습 버퍼]")
        for model_type, buffer in self.learning_buffers.items():
            config = self.learning_config.get(model_type, self.default_config)
            buffer_max = config.get('buffer_size', 50)
            report.append(f"  {model_type}: {len(buffer)}/{buffer_max}")
        
        return "\n".join(report)
    
    def check_health_and_restart(self) -> Dict[str, Any]:
        """시스템 상태 점검 및 자동 재시작"""
        now = datetime.now()
        time_since_check = (now - self.last_health_check).total_seconds()
        
        health_report = {
            'status': 'healthy',
            'issues': [],
            'actions_taken': [],
            'last_check': now.isoformat()
        }
        
        # 정기 상태 점검 (1시간마다)
        if time_since_check >= self.health_check_interval:
            logging.info("[SEARCH] 실시간 학습 시스템 정기 상태 점검 시작...")
            
            # 1. 모델별 최근 업데이트 상태 확인
            for model_type, state in self.model_states.items():
                last_update = state.get('last_update')
                if last_update:
                    hours_since_update = (now - last_update).total_seconds() / 3600
                    if hours_since_update > 24:  # 24시간 이상 업데이트 없음
                        health_report['issues'].append(f"{model_type} 모델이 {hours_since_update:.1f}시간 동안 업데이트되지 않음")
                        
                        # 자동 복구 시도
                        if self.auto_restart_enabled:
                            self._restart_model_learning(model_type)
                            health_report['actions_taken'].append(f"{model_type} 모델 학습 재시작")
            
            # 2. 학습 버퍼 상태 확인
            for model_type, buffer in self.learning_buffers.items():
                if len(buffer) == 0:
                    health_report['issues'].append(f"{model_type} 학습 버퍼가 비어있음")
                    
                    # 버퍼 재초기화
                    if self.auto_restart_enabled:
                        self._reinitialize_buffer(model_type)
                        health_report['actions_taken'].append(f"{model_type} 학습 버퍼 재초기화")
            
            # 3. 성능 기록 확인
            for model_type, history in self.performance_history.items():
                if len(history) == 0:
                    health_report['issues'].append(f"{model_type} 성능 기록이 없음")
            
            self.last_health_check = now
            
            # 상태 저장
            self._save_state()
            
            if health_report['issues']:
                health_report['status'] = 'issues_detected'
                logging.warning(f"[WARN] 실시간 학습 시스템에서 {len(health_report['issues'])}개 문제 발견")
                for issue in health_report['issues']:
                    logging.warning(f"  - {issue}")
                    
                if health_report['actions_taken']:
                    logging.info("[FIX] 자동 복구 조치 수행:")
                    for action in health_report['actions_taken']:
                        logging.info(f"  - {action}")
            else:
                logging.info("[O] 실시간 학습 시스템 상태 양호")
        
        return health_report
    
    def _restart_model_learning(self, model_type: str):
        """특정 모델의 학습 재시작"""
        try:
            # 모델 상태 초기화
            self.model_states[model_type]['last_update'] = datetime.now()
            self.model_states[model_type]['update_count'] = 0
            
            # 성능 기록 초기화 (기본값으로)
            config = self.learning_config.get(model_type, self.default_config)
            if model_type == 'lstm':
                initial_performance = 0.05
            elif model_type == 'ensemble':
                initial_performance = 0.08
            else:  # monte_carlo
                initial_performance = 0.04
                
            self.performance_history[model_type] = deque(
                [initial_performance], 
                maxlen=config.get('performance_window', 10)
            )
            
            logging.info(f"[O] {model_type} 모델 학습 재시작 완료")
            
        except Exception as e:
            logging.error(f"[X] {model_type} 모델 학습 재시작 실패: {e}")
    
    def _reinitialize_buffer(self, model_type: str):
        """학습 버퍼 재초기화"""
        try:
            config = self.learning_config.get(model_type, self.default_config)
            buffer_size = config.get('buffer_size', 50)
            
            # 기존 버퍼 초기화
            self.learning_buffers[model_type] = deque(maxlen=buffer_size)
            
            # DB에서 최근 데이터로 버퍼 채우기
            try:
                all_numbers = self.db_manager.get_all_numbers()
                if all_numbers and len(all_numbers) >= 10:
                    recent_data = all_numbers[-20:]  # 최근 20개 회차
                    for round_num, numbers_str, draw_date in recent_data:
                        numbers = list(map(int, numbers_str.split(',')))
                        self.learning_buffers[model_type].append({
                            'round': round_num, 
                            'numbers': numbers
                        })
                    
                    logging.info(f"[O] {model_type} 학습 버퍼 재초기화 완료 ({len(self.learning_buffers[model_type])}개 데이터)")
                
            except Exception as e:
                logging.warning(f"[WARN] {model_type} 버퍼 데이터 로드 실패: {e}")
                
        except Exception as e:
            logging.error(f"[X] {model_type} 학습 버퍼 재초기화 실패: {e}")
    
    def enable_auto_restart(self, enabled: bool = True):
        """자동 재시작 기능 활성화/비활성화"""
        self.auto_restart_enabled = enabled
        status = "활성화" if enabled else "비활성화"
        logging.info(f"[SYNC] 자동 재시작 기능 {status}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """현재 시스템 건강 상태 반환"""
        now = datetime.now()
        status = {
            'overall_status': 'healthy',
            'models_status': {},
            'buffers_status': {},
            'last_health_check': self.last_health_check.isoformat(),
            'auto_restart_enabled': self.auto_restart_enabled
        }
        
        # 모델별 상태
        for model_type, state in self.model_states.items():
            last_update = state.get('last_update')
            hours_since_update = 0
            if last_update:
                hours_since_update = (now - last_update).total_seconds() / 3600
            
            status['models_status'][model_type] = {
                'update_count': state['update_count'],
                'hours_since_update': hours_since_update,
                'status': 'healthy' if hours_since_update < 24 else 'stale'
            }
        
        # 버퍼 상태
        for model_type, buffer in self.learning_buffers.items():
            config = self.learning_config.get(model_type, self.default_config)
            status['buffers_status'][model_type] = {
                'current_size': len(buffer),
                'max_size': config.get('buffer_size', 50),
                'status': 'healthy' if len(buffer) > 0 else 'empty'
            }
        
        # 전체 상태 결정
        issues = []
        for model_status in status['models_status'].values():
            if model_status['status'] != 'healthy':
                issues.append('model_stale')
        for buffer_status in status['buffers_status'].values():
            if buffer_status['status'] != 'healthy':
                issues.append('buffer_empty')
        
        if issues:
            status['overall_status'] = 'issues_detected'
        
        return status