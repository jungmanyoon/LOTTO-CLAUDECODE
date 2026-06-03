#!/usr/bin/env python3
"""
하이퍼파라미터 자동 튜닝 시스템
Optuna를 사용한 베이지안 최적화 기반 자동 튜닝
"""
import logging
from typing import Dict, List, Tuple, Any, Optional, Callable
import numpy as np
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
import json
import os
from datetime import datetime
from sklearn.model_selection import cross_val_score
from ..core.db_manager import DatabaseManager

class HyperparameterTuner:
    """하이퍼파라미터 자동 튜닝 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        
        # 튜닝 설정
        self.tuning_config = {
            'n_trials': 100,              # 시도 횟수
            'timeout': 3600,              # 최대 실행 시간 (초)
            'n_jobs': -1,                 # 병렬 처리 (-1: 모든 CPU 사용)
            'cv_folds': 5,                # 교차 검증 폴드 수
            'optimization_direction': 'maximize'  # 최적화 방향
        }
        
        # 모델별 탐색 공간 정의
        self.search_spaces = {
            'lstm': self._get_lstm_search_space(),
            'ensemble': self._get_ensemble_search_space(),
            'monte_carlo': self._get_monte_carlo_search_space()
        }
        
        # 튜닝 이력 저장
        self.tuning_history = []
        
        # Optuna 설정
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        
        logging.info("하이퍼파라미터 자동 튜닝 시스템 초기화 완료")
    
    def tune_model(self, model_type: str, model_instance: Any, 
                   training_data: Any, validation_metric: str = 'accuracy') -> Dict[str, Any]:
        """모델 하이퍼파라미터 튜닝
        
        Args:
            model_type: 모델 유형 ('lstm', 'ensemble', 'monte_carlo')
            model_instance: 튜닝할 모델 인스턴스
            training_data: 학습 데이터
            validation_metric: 검증 메트릭
            
        Returns:
            Dict: 최적 하이퍼파라미터 및 튜닝 결과
        """
        logging.info(f"\n[하이퍼파라미터 튜닝] {model_type} 모델 튜닝 시작...")
        
        # 목적 함수 생성
        objective = self._create_objective_function(
            model_type, model_instance, training_data, validation_metric
        )
        
        # Optuna study 생성
        study = optuna.create_study(
            direction=self.tuning_config['optimization_direction'],
            sampler=TPESampler(seed=42),
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10)
        )
        
        # 최적화 실행
        study.optimize(
            objective,
            n_trials=self.tuning_config['n_trials'],
            timeout=self.tuning_config['timeout'],
            n_jobs=1  # 모델 학습이 이미 병렬화되어 있으므로 1로 설정
        )
        
        # 결과 정리
        best_params = study.best_params
        best_value = study.best_value
        
        logging.info(f"최적 파라미터: {best_params}")
        logging.info(f"최적 성능: {best_value:.4f}")
        
        # 튜닝 결과 저장
        tuning_result = {
            'model_type': model_type,
            'best_params': best_params,
            'best_value': best_value,
            'n_trials': len(study.trials),
            'optimization_history': [
                {
                    'trial': trial.number,
                    'value': trial.value,
                    'params': trial.params,
                    'state': str(trial.state)
                }
                for trial in study.trials
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        self.tuning_history.append(tuning_result)
        self._save_tuning_history()
        
        # 중요도 분석
        importance = self._analyze_parameter_importance(study)
        tuning_result['parameter_importance'] = importance
        
        return tuning_result
    
    def _create_objective_function(self, model_type: str, model_instance: Any,
                                 training_data: Any, validation_metric: str) -> Callable:
        """모델별 목적 함수 생성"""
        
        if model_type == 'lstm':
            return self._create_lstm_objective(model_instance, training_data, validation_metric)
        elif model_type == 'ensemble':
            return self._create_ensemble_objective(model_instance, training_data, validation_metric)
        elif model_type == 'monte_carlo':
            return self._create_monte_carlo_objective(model_instance, training_data, validation_metric)
        else:
            raise ValueError(f"지원하지 않는 모델 유형: {model_type}")
    
    def _create_lstm_objective(self, lstm_model, training_data, validation_metric):
        """LSTM 모델 목적 함수"""
        def objective(trial):
            # 하이퍼파라미터 샘플링
            params = {
                'lstm_units': trial.suggest_categorical('lstm_units', [32, 64, 128, 256]),
                'dropout_rate': trial.suggest_float('dropout_rate', 0.1, 0.5),
                'learning_rate': trial.suggest_float('learning_rate', 1e-4, 1e-2, log=True),
                'batch_size': trial.suggest_categorical('batch_size', [16, 32, 64]),
                'sequence_length': trial.suggest_int('sequence_length', 30, 100, step=10)
            }
            
            # 모델 재구성
            lstm_model.rebuild_model(params)
            
            # 교차 검증
            scores = []
            for fold in range(self.tuning_config['cv_folds']):
                # 데이터 분할
                fold_size = len(training_data) // self.tuning_config['cv_folds']
                val_start = fold * fold_size
                val_end = (fold + 1) * fold_size
                
                train_data = training_data[:val_start] + training_data[val_end:]
                val_data = training_data[val_start:val_end]
                
                # 학습 및 검증
                score = lstm_model.train_with_validation(train_data, val_data)
                scores.append(score)
                
                # 조기 종료 확인
                if fold > 0 and np.mean(scores) < 0.5:
                    raise optuna.TrialPruned()
            
            return np.mean(scores)
        
        return objective
    
    def _create_ensemble_objective(self, ensemble_model, training_data, validation_metric):
        """앙상블 모델 목적 함수"""
        def objective(trial):
            # Random Forest 파라미터
            rf_params = {
                'n_estimators': trial.suggest_int('rf_n_estimators', 50, 300),
                'max_depth': trial.suggest_int('rf_max_depth', 5, 50),
                'min_samples_split': trial.suggest_int('rf_min_samples_split', 2, 20),
                'min_samples_leaf': trial.suggest_int('rf_min_samples_leaf', 1, 10),
                'max_features': trial.suggest_categorical('rf_max_features', ['sqrt', 'log2'])
            }
            
            # XGBoost 파라미터
            xgb_params = {
                'n_estimators': trial.suggest_int('xgb_n_estimators', 50, 300),
                'max_depth': trial.suggest_int('xgb_max_depth', 3, 10),
                'learning_rate': trial.suggest_float('xgb_learning_rate', 0.01, 0.3, log=True),
                'subsample': trial.suggest_float('xgb_subsample', 0.6, 1.0),
                'colsample_bytree': trial.suggest_float('xgb_colsample_bytree', 0.6, 1.0),
                'gamma': trial.suggest_float('xgb_gamma', 0, 1)
            }
            
            # Neural Network 파라미터
            nn_layers = trial.suggest_categorical('nn_layers', [1, 2, 3])
            nn_params = {
                'hidden_layer_sizes': tuple(
                    trial.suggest_int(f'nn_units_layer_{i}', 50, 200)
                    for i in range(nn_layers)
                ),
                'learning_rate_init': trial.suggest_float('nn_learning_rate', 1e-4, 1e-2, log=True),
                'alpha': trial.suggest_float('nn_alpha', 1e-4, 1e-2, log=True),
                'batch_size': trial.suggest_categorical('nn_batch_size', ['auto', 32, 64, 128])
            }
            
            # 모델 업데이트
            ensemble_model.update_hyperparameters(rf_params, xgb_params, nn_params)
            
            # 학습 및 평가 (train()이 None 반환할 수 있으므로 방어 처리)
            evaluation = ensemble_model.train(training_data, test_size=0.2)
            if evaluation is None:
                return 0.0

            # 앙상블 성능 반환
            return evaluation.get('ensemble', {}).get('accuracy', 0)
        
        return objective
    
    def _create_monte_carlo_objective(self, mc_model, training_data, validation_metric):
        """Monte Carlo 모델 목적 함수"""
        def objective(trial):
            # 시뮬레이션 파라미터
            params = {
                'n_simulations': trial.suggest_int('n_simulations', 1000, 50000, log=True),
                'temperature': trial.suggest_float('temperature', 0.5, 2.0),
                'selection_pressure': trial.suggest_float('selection_pressure', 1.0, 5.0),
                'mutation_rate': trial.suggest_float('mutation_rate', 0.01, 0.3),
                'elite_ratio': trial.suggest_float('elite_ratio', 0.05, 0.3),
                'convergence_threshold': trial.suggest_float('convergence_threshold', 0.001, 0.1, log=True)
            }
            
            # 파라미터 업데이트
            mc_model.update_parameters(params)
            
            # 검증을 위한 시뮬레이션
            # get_numbers_with_bonus() 사용: List[Tuple[round, (n1,n2,n3,n4,n5,n6,bonus)]]
            all_data = self.db_manager.get_numbers_with_bonus()
            if not all_data or len(all_data) < 15:
                return 0.0

            # 최근 20회차 추출 (회차 내림차순 정렬)
            all_data_sorted = sorted(all_data, key=lambda x: x[0], reverse=True)
            recent_data = all_data_sorted[:20]
            score = 0

            for i in range(10):
                # simulate_combinations() 사용 (simulate() 미존재)
                sim_results = mc_model.simulate_combinations(n_simulations=50)
                # 실제 당첨번호: 튜플의 두 번째 원소에서 앞 6개
                _, nums_tuple = recent_data[10 + i]
                actual_set = set(nums_tuple[:6])

                # 상위 예측 최대 5개와 실제 번호 비교
                for pred_combo, _score in sim_results[:5]:
                    matches = len(set(pred_combo) & actual_set)
                    score += matches / 6.0

            return score / (10 * 5)  # 평균 매칭 비율
        
        return objective
    
    def _get_lstm_search_space(self) -> Dict[str, Any]:
        """LSTM 모델 탐색 공간 정의"""
        return {
            'lstm_units': [32, 64, 128, 256],
            'dropout_rate': (0.1, 0.5),
            'learning_rate': (1e-4, 1e-2),
            'batch_size': [16, 32, 64],
            'sequence_length': (30, 100),
            'activation': ['relu', 'tanh'],
            'optimizer': ['adam', 'rmsprop']
        }
    
    def _get_ensemble_search_space(self) -> Dict[str, Any]:
        """앙상블 모델 탐색 공간 정의"""
        return {
            'rf': {
                'n_estimators': (50, 300),
                'max_depth': (5, 50),
                'min_samples_split': (2, 20),
                'min_samples_leaf': (1, 10)
            },
            'xgb': {
                'n_estimators': (50, 300),
                'max_depth': (3, 10),
                'learning_rate': (0.01, 0.3),
                'subsample': (0.6, 1.0)
            },
            'nn': {
                'hidden_layers': (1, 3),
                'units_per_layer': (50, 200),
                'learning_rate': (1e-4, 1e-2),
                'alpha': (1e-4, 1e-2)
            }
        }
    
    def _get_monte_carlo_search_space(self) -> Dict[str, Any]:
        """Monte Carlo 모델 탐색 공간 정의"""
        return {
            'n_simulations': (1000, 50000),
            'temperature': (0.5, 2.0),
            'selection_pressure': (1.0, 5.0),
            'mutation_rate': (0.01, 0.3),
            'elite_ratio': (0.05, 0.3),
            'convergence_threshold': (0.001, 0.1)
        }
    
    def _analyze_parameter_importance(self, study: optuna.Study) -> Dict[str, float]:
        """파라미터 중요도 분석"""
        try:
            importance = optuna.importance.get_param_importances(study)
            return importance
        except Exception as e:
            logging.error(f"하이퍼파라미터 튜닝 실패: {e}")
            # 중요도 계산 실패 시 빈 딕셔너리 반환
            return {}
    
    def _save_tuning_history(self):
        """튜닝 이력 저장"""
        history_path = 'results/hyperparameter_tuning_history.json'
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(self.tuning_history, f, ensure_ascii=False, indent=2)
    
    def get_best_params(self, model_type: str) -> Optional[Dict[str, Any]]:
        """특정 모델의 최적 파라미터 반환"""
        for result in reversed(self.tuning_history):
            if result['model_type'] == model_type:
                return result['best_params']
        return None
    
    def suggest_next_experiment(self, model_type: str) -> Dict[str, Any]:
        """다음 실험 제안"""
        # 이전 실험 결과 분석
        past_results = [r for r in self.tuning_history if r['model_type'] == model_type]
        
        if not past_results:
            return {
                'suggestion': '초기 탐색',
                'params': self.search_spaces.get(model_type, {})
            }
        
        # 가장 좋은 결과 분석
        best_result = max(past_results, key=lambda x: x['best_value'])
        best_params = best_result['best_params']
        
        # 개선 제안
        suggestions = []
        
        # 파라미터 중요도 기반 제안
        importance = best_result.get('parameter_importance', {})
        if importance:
            # 가장 중요한 파라미터 주변 탐색 제안
            most_important = max(importance.items(), key=lambda x: x[1])[0]
            suggestions.append(f"{most_important} 파라미터 주변을 더 세밀하게 탐색")
        
        # 성능 추세 기반 제안
        if len(past_results) > 3:
            recent_values = [r['best_value'] for r in past_results[-3:]]
            if all(recent_values[i] <= recent_values[i+1] for i in range(2)):
                suggestions.append("성능이 개선되고 있으므로 현재 방향으로 계속 탐색")
            else:
                suggestions.append("다른 탐색 영역으로 이동 고려")
        
        return {
            'suggestion': ' | '.join(suggestions) if suggestions else '추가 실험 필요',
            'best_params_so_far': best_params,
            'best_value_so_far': best_result['best_value']
        }
    
    def generate_tuning_report(self) -> str:
        """튜닝 보고서 생성"""
        report = []
        report.append("\n" + "="*60)
        report.append("하이퍼파라미터 튜닝 보고서")
        report.append("="*60)
        
        # 모델별 최적 결과
        for model_type in ['lstm', 'ensemble', 'monte_carlo']:
            model_results = [r for r in self.tuning_history if r['model_type'] == model_type]
            
            if model_results:
                best_result = max(model_results, key=lambda x: x['best_value'])
                report.append(f"\n[{model_type.upper()} 모델]")
                report.append(f"총 실험 횟수: {sum(r['n_trials'] for r in model_results)}")
                report.append(f"최적 성능: {best_result['best_value']:.4f}")
                report.append("최적 파라미터:")
                
                for param, value in best_result['best_params'].items():
                    report.append(f"  - {param}: {value}")
                
                # 파라미터 중요도
                importance = best_result.get('parameter_importance', {})
                if importance:
                    report.append("파라미터 중요도:")
                    sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
                    for param, imp in sorted_importance[:5]:
                        report.append(f"  - {param}: {imp:.3f}")
        
        return "\n".join(report)