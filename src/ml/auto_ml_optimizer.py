#!/usr/bin/env python3
"""
ML 모델 자동 개선 시스템
백테스팅 결과를 기반으로 ML 모델을 자동으로 개선
"""
import logging
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.metrics import mean_squared_error
import optuna
from datetime import datetime
import json
import os

class AutoMLOptimizer:
    """ML 모델 자동 최적화 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager
        self.optimization_history = []
        self.best_params = {}

        # Optuna 데이터베이스 경로 설정
        self.optuna_db_path = os.path.join('data', 'optuna_study.db')
        os.makedirs('data', exist_ok=True)

        # 최적화 설정
        self.optimization_config = {
            'min_performance_threshold': 0.9,  # 최소 평균 일치 개수
            'target_performance': 1.2,         # 최대로 추구할 목표 평균 일치 개수
            'max_iterations': 10,              # 최대 반복 횟수
            'patience': 3,                     # 조기 종료 patience
            'improvement_threshold': 0.05      # 성능 향상 임계값
        }

        logging.info(f"ML 모델 자동 최적화 시스템 초기화 완료 (Optuna DB: {self.optuna_db_path})")

    def optimize_based_on_backtest(self, model, backtest_results: Dict, model_type: str = 'ensemble') -> Dict[str, Any]:
        """백테스팅 결과를 기반으로 모델 최적화

        Args:
            model: 최적화할 ML 모델
            backtest_results: 백테스팅 결과
            model_type: 모델 유형 ('ensemble', 'lstm', 'monte_carlo')

        Returns:
            Dict: 최적화 결과
        """
        logging.info(f"\n[AutoML] {model_type} 모델 자동 최적화 시작...")

        # 모델이 None인지 확인
        if model is None:
            logging.warning(f"AutoML: {model_type} 모델이 None입니다. 최적화를 건너뜁니다.")
            return {
                'optimized': False,
                'reason': 'model_is_none',
                'model_type': model_type
            }

        current_performance = self._extract_performance(backtest_results, model_type)
        logging.info(f"현재 성능: 평균 일치 {current_performance:.2f}개")

        improvement_threshold = self.optimization_config.get('improvement_threshold', 0.05)
        min_threshold = self.optimization_config.get('min_performance_threshold', 0.9)
        configured_target = self.optimization_config.get('target_performance', 1.2)

        desired_target = max(min_threshold, current_performance + improvement_threshold)
        target_performance = min(configured_target, desired_target)

        logging.info(f"[AutoML] 목표 성능: {target_performance:.3f} (현재 {current_performance:.3f})")

        if current_performance >= target_performance - 1e-6:
            logging.info("현재 성능이 목표치를 이미 충족했습니다.")
            return {'optimized': False, 'reason': 'already_optimal', 'target_performance': target_performance}

        if model_type == 'ensemble':
            optimized_model = self._optimize_ensemble(model, backtest_results)
        elif model_type == 'lstm':
            optimized_model = self._optimize_lstm(model, backtest_results)
        elif model_type == 'monte_carlo':
            optimized_model = self._optimize_monte_carlo(model, backtest_results)
        else:
            logging.warning(f"지원하지 않는 모델 유형: {model_type}")
            return {'optimized': False, 'reason': 'unsupported_model'}

        result = {
            'optimized': True,
            'model_type': model_type,
            'before_performance': current_performance,
            'target_performance': target_performance,
            'best_params': self.best_params.get(model_type, {}),
            'optimization_time': datetime.now().isoformat()
        }

        self.optimization_history.append(result)
        self._save_optimization_history()

        return result

    def _optimize_ensemble(self, ensemble_model, backtest_results: Dict) -> Any:
        """앙상블 모델 최적화"""
        if ensemble_model is None:
            logging.warning("AutoML: 앙상블 모델이 None입니다. 최적화를 건너뜁니다.")
            return None

        logging.info("앙상블 모델 하이퍼파라미터 최적화 중...")

        # Optuna를 사용한 베이지안 최적화
        def objective(trial):
            # Random Forest 파라미터
            rf_params = {
                'n_estimators': trial.suggest_int('rf_n_estimators', 50, 300),
                'max_depth': trial.suggest_int('rf_max_depth', 5, 50),
                'min_samples_split': trial.suggest_int('rf_min_samples_split', 2, 20),
                'min_samples_leaf': trial.suggest_int('rf_min_samples_leaf', 1, 10)
            }
            
            # XGBoost 파라미터
            xgb_params = {
                'n_estimators': trial.suggest_int('xgb_n_estimators', 50, 300),
                'max_depth': trial.suggest_int('xgb_max_depth', 3, 10),
                'learning_rate': trial.suggest_float('xgb_learning_rate', 0.01, 0.3),
                'subsample': trial.suggest_float('xgb_subsample', 0.6, 1.0)
            }
            
            # Neural Network 파라미터
            nn_params = {
                'hidden_layer_sizes': trial.suggest_categorical(
                    'nn_hidden_layer_sizes', 
                    [(100,), (100, 50), (200, 100), (100, 50, 25)]
                ),
                'learning_rate_init': trial.suggest_float('nn_learning_rate', 0.0001, 0.01),
                'alpha': trial.suggest_float('nn_alpha', 0.0001, 0.01)
            }
            
            # 모델 업데이트
            ensemble_model.update_hyperparameters(rf_params, xgb_params, nn_params)
            
            # 간단한 검증 (실제로는 백테스팅 재실행)
            score = self._quick_validation(ensemble_model)
            
            return score
        
        # 최적화 실행 (과도한 학습 방지를 위해 trial 수 감소)
        n_trials = 10  # 50 → 10으로 감소 (Optuna trials)

        # SQLite storage for persistent study
        storage_url = f"sqlite:///{self.optuna_db_path}"

        study = optuna.create_study(
            study_name='ensemble_optimization',
            storage=storage_url,
            load_if_exists=True,  # Resume existing study
            direction='maximize'
        )
        
        # 조기 종료 콜백 추가
        def early_stopping_callback(study, trial):
            # 최근 5회 개선이 없으면 중단
            if len(study.trials) > 5:
                recent_scores = [t.value for t in study.trials[-5:] if t.value is not None]
                if len(recent_scores) >= 5:
                    improvement = max(recent_scores) - min(recent_scores)
                    if improvement < 0.001:  # 0.1% 미만 개선
                        logging.info("조기 종료: 성능 개선이 미미함")
                        study.stop()
        
        study.optimize(objective, n_trials=n_trials, callbacks=[early_stopping_callback])
        
        # 최고 파라미터 저장
        self.best_params['ensemble'] = study.best_params
        logging.info(f"최적 파라미터: {study.best_params}")
        logging.info(f"최고 점수: {study.best_value}")
        
        # 모델에 최적 파라미터 적용
        ensemble_model.apply_best_params(study.best_params)
        
        return ensemble_model
    
    def _optimize_lstm(self, lstm_model, backtest_results: Dict) -> Any:
        """LSTM 모델 최적화"""
        if lstm_model is None:
            logging.warning("AutoML: LSTM 모델이 None입니다. 최적화를 건너뜁니다.")
            return None

        logging.info("LSTM 모델 아키텍처 및 하이퍼파라미터 최적화 중...")

        def objective(trial):
            # LSTM 아키텍처 파라미터
            params = {
                'lstm_units': trial.suggest_categorical('lstm_units', [32, 64, 128, 256]),
                'dropout_rate': trial.suggest_float('dropout_rate', 0.1, 0.5),
                'learning_rate': trial.suggest_float('learning_rate', 0.0001, 0.01),
                'batch_size': trial.suggest_categorical('batch_size', [16, 32, 64]),
                'epochs': trial.suggest_int('epochs', 50, 200)
            }
            
            # 새로운 모델 구성
            lstm_model.rebuild_model(params)
            
            # 학습 및 검증
            score = self._train_and_validate_lstm(lstm_model, params)
            
            return score
        
        # 조기 종료 콜백 정의
        def early_stopping_callback(study, trial):
            if len(study.trials) > 5:
                recent_scores = [t.value for t in study.trials[-5:] if t.value is not None]
                if len(recent_scores) >= 5:
                    improvement = max(recent_scores) - min(recent_scores)
                    if improvement < 0.001:
                        logging.info("조기 종료: 성능 개선이 미미함")
                        study.stop()
        
        # 최적화 실행
        # SQLite storage for persistent study
        storage_url = f"sqlite:///{self.optuna_db_path}"

        study = optuna.create_study(
            study_name='lstm_optimization',
            storage=storage_url,
            load_if_exists=True,  # Resume existing study
            direction='maximize'
        )
        n_trials = 10  # 30 → 10으로 감소 (LSTM trials)
        study.optimize(objective, n_trials=n_trials, callbacks=[early_stopping_callback])
        
        # 최고 파라미터 저장
        self.best_params['lstm'] = study.best_params
        logging.info(f"LSTM 최적 파라미터: {study.best_params}")
        
        # 최적 파라미터로 모델 재구성
        lstm_model.rebuild_model(study.best_params)
        lstm_model.retrain()
        
        return lstm_model
    
    def _optimize_monte_carlo(self, mc_model, backtest_results: Dict) -> Any:
        """Monte Carlo 시뮬레이션 최적화"""
        if mc_model is None:
            logging.warning("AutoML: Monte Carlo 모델이 None입니다. 최적화를 건너뜁니다.")
            return None

        logging.info("Monte Carlo 시뮬레이션 파라미터 최적화 중...")

        def objective(trial):
            params = {
                'n_simulations': trial.suggest_int('n_simulations', 5000, 50000),
                'temperature': trial.suggest_float('temperature', 0.5, 2.0),
                'selection_pressure': trial.suggest_float('selection_pressure', 1.0, 5.0),
                'mutation_rate': trial.suggest_float('mutation_rate', 0.01, 0.2),
                'elite_ratio': trial.suggest_float('elite_ratio', 0.05, 0.3)
            }
            
            # 파라미터 업데이트
            mc_model.update_parameters(params)
            
            # 검증
            score = self._validate_monte_carlo(mc_model)
            
            return score
        
        # 조기 종료 콜백 정의
        def early_stopping_callback(study, trial):
            if len(study.trials) > 5:
                recent_scores = [t.value for t in study.trials[-5:] if t.value is not None]
                if len(recent_scores) >= 5:
                    improvement = max(recent_scores) - min(recent_scores)
                    if improvement < 0.001:
                        logging.info("조기 종료: 성능 개선이 미미함")
                        study.stop()
        
        # 최적화 실행
        # SQLite storage for persistent study
        storage_url = f"sqlite:///{self.optuna_db_path}"

        study = optuna.create_study(
            study_name='monte_carlo_optimization',
            storage=storage_url,
            load_if_exists=True,  # Resume existing study
            direction='maximize'
        )
        n_trials = 10  # 40 → 10으로 감소 (Monte Carlo trials)
        study.optimize(objective, n_trials=n_trials, callbacks=[early_stopping_callback])
        
        # 최고 파라미터 저장
        self.best_params['monte_carlo'] = study.best_params
        logging.info(f"Monte Carlo 최적 파라미터: {study.best_params}")
        
        # 최적 파라미터 적용
        mc_model.update_parameters(study.best_params)
        
        return mc_model
    
    def _extract_performance(self, backtest_results: Dict, model_type: str) -> float:
        """백테스팅 결과에서 성능 지표 추출"""
        try:
            # 로그에 백테스팅 결과 구조 출력
            if backtest_results:
                logging.debug(f"백테스팅 결과 키: {list(backtest_results.keys())}")
            
            # performance_metrics가 있는지 확인
            if 'performance_metrics' not in backtest_results:
                logging.warning(f"performance_metrics가 백테스팅 결과에 없습니다.")
                # 대체 방법: model_performance에서 직접 찾기
                if 'model_performance' in backtest_results:
                    model_perf = backtest_results['model_performance']
                    if model_type.upper() in model_perf:
                        return model_perf[model_type.upper()].get('avg_matches', 0.0)
                return 0.0
            
            metrics = backtest_results.get('performance_metrics', {})
            
            # model_performance를 확인
            model_performance = metrics.get('model_performance', {})
            if model_performance:
                model_metrics = model_performance.get(model_type.upper(), {})
                avg_matches = model_metrics.get('avg_matches', 0.0)
                logging.info(f"{model_type} 성능: {avg_matches:.2f}개")
                return avg_matches
            
            # 대체: 직접 model_type으로 찾기
            model_metrics = metrics.get(model_type.upper(), {})
            return model_metrics.get('avg_matches', 0.0)
            
        except Exception as e:
            logging.error(f"성능 추출 중 오류: {e}")
            return 0.0
    
    def _quick_validation(self, model) -> float:
        """빠른 검증을 위한 간단한 테스트"""
        # 모델이 None인 경우 체크
        if model is None:
            logging.warning("AutoML: 검증할 모델이 None입니다. 검증을 건너뜁니다.")
            return 0.0

        # [2026-06-13] _optimize_ensemble objective는 매 trial update_hyperparameters를 호출하는데,
        #  이는 하이퍼파라미터 변경 후 재학습이 필요하다는 의미로 is_trained=False로 둔다. 미학습 모델로
        #  predict_next_numbers를 5회 호출하면 매번 "모델이 준비되지 않았습니다" 경고만 나고 점수는 0이
        #  된다(검증 불가). trial마다 전체 재학습은 비용이 과도하고, 최종 예측은 PoolOptimizer/극단성 풀이
        #  담당하므로, 미학습 시에는 예측 검증을 건너뛰고 중립 점수(0.0)를 반환해 로그 노이즈를 제거한다.
        if not getattr(model, 'is_trained', True):
            logging.debug("AutoML: 모델 미학습(하이퍼파라미터 변경 직후) - 예측 검증 건너뜀(중립 0.0)")
            return 0.0

        # 최근 10회차로 빠른 검증
        recent_numbers = self.db_manager.get_recent_numbers(10)

        score = 0
        for i in range(5):
            # recent_numbers는 (회차, 번호문자열, 추첨일) 튜플의 리스트
            # 번호 문자열만 추출하여 전달
            recent_numbers_str = [rn[1] for rn in recent_numbers[:5+i]]
            # EnsemblePredictor는 predict 메서드가 없으므로 predict_next_numbers 사용
            if hasattr(model, 'predict_next_numbers'):
                predictions_list = model.predict_next_numbers(recent_numbers_str, num_predictions=1)
                predictions = predictions_list[0]['numbers'] if predictions_list else []
            else:
                predictions = model.predict(recent_numbers_str)
            
            # 실제 번호도 튜플에서 추출하고 정수 리스트로 변환
            actual_str = recent_numbers[5+i][1]
            actual = [int(n) for n in actual_str.split(',')]
            
            # 예측 결과와 실제 번호 비교
            if predictions:
                # predictions는 번호 리스트
                if isinstance(predictions, list) and len(predictions) > 0:
                    # predictions가 중첩 리스트인 경우
                    if isinstance(predictions[0], list):
                        matches = len(set(predictions[0]) & set(actual))
                    # predictions가 단순 번호 리스트인 경우
                    elif isinstance(predictions[0], int):
                        matches = len(set(predictions) & set(actual))
                    else:
                        matches = 0
                    score += matches
        
        return score / 5 if score > 0 else 0.0
    
    def _train_and_validate_lstm(self, lstm_model, params: Dict) -> float:
        """LSTM 모델 학습 및 검증"""
        # 모델이 None인 경우 체크
        if lstm_model is None:
            logging.warning("AutoML: LSTM 모델이 None입니다. 학습 및 검증을 건너뜁니다.")
            return 0.0

        # 데이터 준비
        all_numbers = self.db_manager.get_all_numbers()

        if len(all_numbers) < 100:
            return 0.0

        # Optuna가 탐색한 epochs 값 추출 (없으면 기본값 50)
        epochs = params.get('epochs', 50)

        # train()으로 epochs 전달 (train_with_validation은 epochs 미지원)
        try:
            lstm_model.train(all_numbers[:-20], epochs=epochs)
        except Exception as e:
            logging.warning(f"LSTM train() 실패: {e}")
            return 0.0

        # 검증 점수 계산 (evaluate_model 사용)
        try:
            metrics = lstm_model.evaluate_model(all_numbers[-20:])
            return float(metrics.get('avg_match_rate', 0.0))
        except Exception as e:
            logging.warning(f"LSTM 검증 실패: {e}")
            return 0.0
    
    def _validate_monte_carlo(self, mc_model) -> float:
        """Monte Carlo 모델 검증"""
        # 모델이 None인 경우 체크
        if mc_model is None:
            logging.warning("AutoML: Monte Carlo 모델이 None입니다. 검증을 건너뜁니다.")
            return 0.0

        # 최근 데이터로 검증
        recent_numbers = self.db_manager.get_recent_numbers(20)

        score = 0
        for i in range(10):
            # simulate_combinations: List[Tuple[List[int], float]] 반환
            predictions = mc_model.simulate_combinations(n_simulations=5)

            # 실제 번호를 튜플에서 추출하고 정수 리스트로 변환
            actual_str = recent_numbers[10+i][1]
            actual = [int(n) for n in actual_str.split(',')]

            # 상위 예측과 실제 번호 비교 (반환값: (조합, 점수) 튜플 리스트)
            if predictions and len(predictions) > 0:
                best_prediction = predictions[0][0]  # (조합, 점수) 중 조합 추출
                matches = len(set(best_prediction) & set(actual))
                score += matches

        return score / 10 if score > 0 else 0.0
    
    def _save_optimization_history(self):
        """최적화 이력 저장"""
        history_path = 'results/optimization_history.json'
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(self.optimization_history, f, ensure_ascii=False, indent=2)
    
    def get_improvement_suggestions(self, backtest_results: Dict) -> List[str]:
        """백테스팅 결과를 기반으로 개선 제안 생성"""
        suggestions = []
        
        # 각 모델의 성능 확인
        metrics = backtest_results.get('performance_metrics', {})
        
        # LSTM 모델 체크
        lstm_metrics = metrics.get('LSTM', {})
        if lstm_metrics.get('total_predictions', 0) == 0:
            suggestions.append("LSTM 모델이 작동하지 않습니다. 모델 구조 및 데이터 형식을 확인하세요.")
        elif lstm_metrics.get('avg_matches', 0) < 1.0:
            suggestions.append("LSTM 모델의 시퀀스 길이를 조정하거나 더 많은 특징을 추가해보세요.")
        
        # Ensemble 모델 체크
        ensemble_metrics = metrics.get('ENSEMBLE', {})
        if ensemble_metrics.get('avg_matches', 0) < 1.0:
            suggestions.append("앙상블 모델의 개별 모델 가중치를 재조정하세요.")
            suggestions.append("더 다양한 특징 공학(feature engineering)을 시도해보세요.")
        
        # Monte Carlo 체크
        mc_metrics = metrics.get('MONTE_CARLO', {})
        if mc_metrics.get('avg_matches', 0) < 1.0:
            suggestions.append("Monte Carlo 시뮬레이션 횟수를 늘리고 온도 파라미터를 조정하세요.")
        
        # 전체적인 제안
        if all(metrics.get(m, {}).get('avg_matches', 0) < 1.0 for m in ['LSTM', 'ENSEMBLE', 'MONTE_CARLO']):
            suggestions.append("필터링 단계를 먼저 최적화하여 후보군을 줄인 후 ML 모델을 적용하세요.")
            suggestions.append("과거 데이터의 패턴을 더 깊이 분석하여 새로운 특징을 발견하세요.")
        
        return suggestions