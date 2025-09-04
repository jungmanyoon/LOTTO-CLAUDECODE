"""
메타 최적화 실행기
- 메타 최적화 계획을 실제로 실행하는 모듈
"""

import logging
import json
from typing import Dict, Any, List
import yaml
from datetime import datetime
import os
import sys

# 프로젝트 루트 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.optimization.meta_optimizer import MetaOptimizer
from src.optimization.auto_improvement_manager import AutoImprovementManager
from src.core.filter_manager import FilterManager
from src.core.db_manager import DatabaseManager

class MetaOptimizationExecutor:
    """메타 최적화 실행기"""
    
    def __init__(self):
        self.meta_optimizer = MetaOptimizer()
        self.improvement_manager = AutoImprovementManager()
        self.db_manager = DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.config_file = 'config.yaml'
        
    def execute_optimization_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """최적화 계획 실행"""
        results = {
            "plan_name": plan["strategy_name"],
            "start_time": datetime.now().isoformat(),
            "actions_executed": [],
            "success": True,
            "errors": []
        }
        
        logging.info(f"메타 최적화 계획 실행 시작: {plan['strategy_name']}")
        
        for action in plan["actions"]:
            try:
                result = self._execute_action(action)
                results["actions_executed"].append({
                    "action": action,
                    "result": result,
                    "status": "success"
                })
                logging.info(f"액션 성공: {action['type']}")
            except Exception as e:
                results["errors"].append({
                    "action": action,
                    "error": str(e)
                })
                logging.error(f"액션 실패: {action['type']} - {str(e)}")
                results["success"] = False
        
        results["end_time"] = datetime.now().isoformat()
        return results
    
    def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """개별 액션 실행"""
        action_type = action["type"]
        params = action.get("params", {})
        
        if action_type == "adjust_filters":
            return self._adjust_filters(params)
        elif action_type == "tune_models":
            return self._tune_models(params)
        elif action_type == "update_weights":
            return self._update_weights(params)
        elif action_type == "add_features":
            return self._add_features(params)
        elif action_type == "ensemble_rebalance":
            return self._ensemble_rebalance(params)
        elif action_type == "hyperparameter_search":
            return self._hyperparameter_search(params)
        elif action_type == "filter_mutation":
            return self._filter_mutation(params)
        elif action_type == "model_hybridization":
            return self._model_hybridization(params)
        elif action_type == "adaptive_filter_system":
            return self._enable_adaptive_filters(params)
        else:
            return {"status": "not_implemented", "action": action_type}
    
    def _adjust_filters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """필터 조정"""
        relaxation = params.get("relaxation", 0.1)
        
        # config.yaml 읽기
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 필터 기준 완화
        adjustments = {
            "sum_range": {
                "min_sum": int(config['filters']['criteria']['sum_range']['min_sum'] * (1 - relaxation)),
                "max_sum": int(config['filters']['criteria']['sum_range']['max_sum'] * (1 + relaxation))
            },
            "consecutive": {
                "max_consecutive": min(4, config['filters']['criteria']['consecutive']['max_consecutive'] + 1)
            },
            "odd_even": {
                "patterns": ['1:5', '2:4', '3:3', '4:2', '5:1']  # 더 다양한 패턴
            }
        }
        
        # config 업데이트
        for filter_name, settings in adjustments.items():
            if filter_name in config['filters']['criteria']:
                config['filters']['criteria'][filter_name].update(settings)
        
        # 저장
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        return {"filters_adjusted": len(adjustments), "relaxation": relaxation}
    
    def _tune_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """모델 튜닝"""
        learning_rate = params.get("learning_rate", 0.001)
        
        # config 업데이트
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # LSTM 학습률 조정
        if 'ml' in config and 'lstm' in config['ml']:
            config['ml']['lstm']['learning_rate'] = learning_rate
            config['ml']['lstm']['epochs'] = 100  # 더 많은 학습
            config['ml']['lstm']['hidden_size'] = 256  # 더 큰 모델
        
        # Ensemble 설정 조정
        if 'ml' in config and 'ensemble' in config['ml']:
            config['ml']['ensemble']['models'] = [
                'random_forest',
                'xgboost', 
                'neural_network',
                'gradient_boosting',  # 새 모델 추가
                'extra_trees'  # 새 모델 추가
            ]
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        return {"models_tuned": True, "new_learning_rate": learning_rate}
    
    def _update_weights(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """가중치 업데이트"""
        shift = params.get("shift", 0.05)
        
        # 현재 성능 기반 가중치 조정
        state = self.improvement_manager.state
        current_perf = state.get('current_performance', {})
        
        # 성능 기반 가중치 계산
        total_perf = sum(current_perf.get(m, 0) for m in ['lstm', 'ensemble', 'monte_carlo'])
        
        new_weights = {}
        if total_perf > 0:
            for model in ['lstm', 'ensemble', 'monte_carlo']:
                base_weight = current_perf.get(model, 0) / total_perf
                # 성능 좋은 모델 가중치 증가
                if current_perf.get(model, 0) > 0.85:
                    new_weights[model] = min(0.6, base_weight + shift)
                else:
                    new_weights[model] = max(0.1, base_weight - shift/2)
        
        # 정규화
        total_weight = sum(new_weights.values())
        for model in new_weights:
            new_weights[model] /= total_weight
        
        # 상태 저장
        state['model_weights'] = new_weights
        self.improvement_manager.save_state()
        
        return {"weights_updated": new_weights}
    
    def _add_features(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """새로운 특성 추가"""
        count = params.get("count", 5)
        
        # 새로운 특성 정의
        new_features = [
            "hot_cold_ratio",  # 핫/콜드 넘버 비율
            "prime_position_pattern",  # 소수 위치 패턴
            "fibonacci_presence",  # 피보나치 수열 포함
            "geometric_mean",  # 기하평균
            "number_spacing_variance"  # 번호 간격 분산
        ]
        
        # feature_config.json 생성
        feature_config = {
            "version": "2.0",
            "features": {
                "existing": [
                    "sum", "odd_even", "consecutive", "sections", 
                    "avg", "std_dev", "min_gap", "max_gap"
                ],
                "new": new_features[:count]
            },
            "feature_engineering": {
                "enabled": True,
                "auto_select": True,
                "importance_threshold": 0.01
            }
        }
        
        with open('feature_config.json', 'w', encoding='utf-8') as f:
            json.dump(feature_config, f, indent=2, ensure_ascii=False)
        
        return {"features_added": count, "new_features": new_features[:count]}
    
    def _ensemble_rebalance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """앙상블 재균형"""
        method = params.get("method", "weighted")
        
        # 앙상블 설정 파일 생성/업데이트
        ensemble_config = {
            "version": "2.0",
            "rebalance_method": method,
            "models": {
                "random_forest": {"weight": 0.25, "n_estimators": 200},
                "xgboost": {"weight": 0.30, "max_depth": 10},
                "neural_network": {"weight": 0.20, "hidden_layers": [128, 64]},
                "gradient_boosting": {"weight": 0.15, "n_estimators": 150},
                "extra_trees": {"weight": 0.10, "n_estimators": 100}
            },
            "voting": "soft" if method == "weighted" else "hard",
            "calibration": {
                "enabled": True,
                "method": "isotonic"
            }
        }
        
        os.makedirs('models/ensemble', exist_ok=True)
        with open('models/ensemble/ensemble_config.json', 'w', encoding='utf-8') as f:
            json.dump(ensemble_config, f, indent=2, ensure_ascii=False)
        
        return {"ensemble_rebalanced": True, "method": method}
    
    def _hyperparameter_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """하이퍼파라미터 탐색"""
        trials = params.get("trials", 20)
        
        # 탐색 공간 정의
        search_space = {
            "lstm": {
                "learning_rate": [0.0001, 0.001, 0.01],
                "hidden_size": [64, 128, 256, 512],
                "num_layers": [2, 3, 4],
                "dropout": [0.1, 0.2, 0.3]
            },
            "random_forest": {
                "n_estimators": [100, 200, 300],
                "max_depth": [10, 20, 30, None],
                "min_samples_split": [2, 5, 10]
            },
            "xgboost": {
                "learning_rate": [0.01, 0.1, 0.3],
                "max_depth": [3, 6, 9],
                "n_estimators": [100, 200, 300]
            }
        }
        
        # 결과 저장
        search_config = {
            "search_space": search_space,
            "trials": trials,
            "optimization_metric": "average_matches",
            "method": "random_search"  # 또는 "bayesian_optimization"
        }
        
        with open('hyperparameter_search_config.json', 'w', encoding='utf-8') as f:
            json.dump(search_config, f, indent=2, ensure_ascii=False)
        
        return {"search_configured": True, "trials": trials}
    
    def _filter_mutation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """필터 변이"""
        mutation_rate = params.get("mutation_rate", 0.3)
        
        # 필터 변이 설정
        mutation_config = {
            "enabled": True,
            "mutation_rate": mutation_rate,
            "mutation_types": [
                "boundary_shift",  # 경계값 이동
                "criteria_swap",   # 기준 교체
                "random_perturbation",  # 랜덤 변형
                "adaptive_threshold"  # 적응형 임계값
            ],
            "mutation_strength": {
                "low": 0.1,
                "medium": 0.3,
                "high": 0.5
            }
        }
        
        with open('filter_mutation_config.json', 'w', encoding='utf-8') as f:
            json.dump(mutation_config, f, indent=2, ensure_ascii=False)
        
        return {"mutation_configured": True, "rate": mutation_rate}
    
    def _model_hybridization(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """모델 하이브리드화"""
        models = params.get("models", ["lstm", "transformer"])
        
        # 하이브리드 모델 설정
        hybrid_config = {
            "enabled": True,
            "base_models": models,
            "fusion_method": "attention",  # attention 메커니즘으로 결합
            "architecture": {
                "lstm_branch": {
                    "hidden_size": 256,
                    "num_layers": 3
                },
                "transformer_branch": {
                    "d_model": 128,
                    "n_heads": 8,
                    "n_layers": 4
                },
                "fusion_layer": {
                    "hidden_size": 512,
                    "dropout": 0.2
                }
            }
        }
        
        with open('hybrid_model_config.json', 'w', encoding='utf-8') as f:
            json.dump(hybrid_config, f, indent=2, ensure_ascii=False)
        
        return {"hybridization_configured": True, "models": models}
    
    def _enable_adaptive_filters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """적응형 필터 시스템 활성화"""
        learning_rate = params.get("learning_rate", 0.1)
        
        # config.yaml 업데이트
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 적응형 필터 설정 추가
        config['adaptive_filters'] = {
            'enabled': True,
            'learning_rate': learning_rate,
            'update_frequency': 1,  # 매 회차마다 업데이트
            'performance_threshold': 0.7,
            'adaptation_methods': [
                'reinforcement_learning',
                'evolutionary_algorithm',
                'gradient_based'
            ]
        }
        
        # 자동 조정 활성화
        config['auto_adjustment']['enabled'] = True
        config['realtime_learning']['enabled'] = True
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        return {"adaptive_filters_enabled": True, "learning_rate": learning_rate}

def execute_meta_optimization():
    """메타 최적화 실행 메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    executor = MetaOptimizationExecutor()
    meta_optimizer = MetaOptimizer()
    
    # 1. 현재 상태 분석
    logging.info("=== 메타 최적화 시작 ===")
    stagnation = meta_optimizer.analyze_stagnation()
    logging.info(f"정체 수준: {stagnation['stagnation_level']:.2f}")
    logging.info(f"패턴: {stagnation['pattern']}")
    
    # 2. 전략 선택
    strategy = meta_optimizer.select_strategy(stagnation)
    logging.info(f"선택된 전략: {strategy.name}")
    logging.info(f"위험도: {strategy.risk_level}, 예상 이득: {strategy.expected_gain}")
    
    # 3. 최적화 계획 생성
    plan = meta_optimizer.generate_optimization_plan(strategy)
    
    # 4. 계획 실행
    results = executor.execute_optimization_plan(plan)
    
    # 5. 결과 저장
    with open('meta_optimization_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logging.info(f"=== 메타 최적화 완료 ===")
    logging.info(f"성공: {results['success']}")
    logging.info(f"실행된 액션: {len(results['actions_executed'])}")
    
    return results

if __name__ == "__main__":
    execute_meta_optimization()