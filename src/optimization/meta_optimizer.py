"""
메타 최적화 시스템
- 알고리즘의 성능을 개선하는 메타 알고리즘
- 정체 상태를 감지하고 새로운 전략을 자동으로 시도
"""

import json
import numpy as np
from typing import Dict, List, Any, Tuple
from datetime import datetime
import logging
from dataclasses import dataclass
import random

logger = logging.getLogger(__name__)

@dataclass
class OptimizationStrategy:
    """최적화 전략 정의"""
    name: str
    description: str
    parameters: Dict[str, Any]
    risk_level: float  # 0.0 (안전) ~ 1.0 (위험)
    expected_gain: float  # 예상 성능 향상

class MetaOptimizer:
    """메타 최적화 엔진"""

    def __init__(self, state_file: str = 'data/auto_improvement_state.json'):
        # state_file 파라미터는 하위 호환성을 위해 유지하지만 실제로는 OptimizationDB 사용
        self.state_file = state_file
        self.strategies = self._initialize_strategies()
        self.exploration_rate = 0.2  # 20% 확률로 탐색
        self.exploitation_rate = 0.8  # 80% 확률로 활용
        
    def _initialize_strategies(self) -> List[OptimizationStrategy]:
        """다양한 최적화 전략 초기화"""
        return [
            # 보수적 전략
            OptimizationStrategy(
                name="conservative_tuning",
                description="안전한 범위 내에서 미세 조정",
                parameters={
                    "adjustment_rate": 0.05,
                    "filter_relaxation": 0.1,
                    "model_weight_shift": 0.05
                },
                risk_level=0.1,
                expected_gain=0.02
            ),
            
            # 균형 전략
            OptimizationStrategy(
                name="balanced_optimization",
                description="균형잡힌 개선 시도",
                parameters={
                    "adjustment_rate": 0.15,
                    "filter_relaxation": 0.2,
                    "model_weight_shift": 0.1,
                    "new_features": True
                },
                risk_level=0.3,
                expected_gain=0.05
            ),
            
            # 공격적 전략
            OptimizationStrategy(
                name="aggressive_exploration",
                description="대담한 변경으로 돌파구 찾기",
                parameters={
                    "adjustment_rate": 0.3,
                    "filter_relaxation": 0.4,
                    "model_weight_shift": 0.2,
                    "random_mutations": True,
                    "hybrid_models": True
                },
                risk_level=0.6,
                expected_gain=0.15
            ),
            
            # 혁신적 전략
            OptimizationStrategy(
                name="innovative_breakthrough",
                description="완전히 새로운 접근법 시도",
                parameters={
                    "complete_reset": False,
                    "new_algorithm": True,
                    "ensemble_redesign": True,
                    "adaptive_filters": True,
                    "quantum_inspired": True
                },
                risk_level=0.8,
                expected_gain=0.3
            ),
            
            # 하이브리드 전략
            OptimizationStrategy(
                name="hybrid_intelligence",
                description="다중 전략 동시 적용",
                parameters={
                    "multi_strategy": True,
                    "dynamic_switching": True,
                    "context_aware": True,
                    "self_adaptation": True
                },
                risk_level=0.5,
                expected_gain=0.1
            )
        ]
    
    def analyze_stagnation(self) -> Dict[str, Any]:
        """정체 상태 분석"""
        # [N-C04] 수정: 삭제된 JSON 파일(data/auto_improvement_state.json) 대신
        #   data/optimization.db (OptimizationDB)에서 상태 조회
        state = {}
        try:
            from src.core.optimization_db import OptimizationDB
            opt_db = OptimizationDB()
            # optimization_state 테이블에서 auto_improvement_state 키 조회
            stored = opt_db.get_state('auto_improvement_state')
            if stored:
                state = stored
            else:
                # 구버전 JSON 파일이 아직 존재하는 경우 폴백 (마이그레이션 이전 환경 대비)
                import os
                if os.path.exists(self.state_file):
                    with open(self.state_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
        except Exception as e:
            logger.warning(f"최적화 상태 로드 실패: {e}")
            state = {}

        history = state.get('improvement_history', [])
        if len(history) < 3:
            return {"stagnation_level": 0, "pattern": "insufficient_data"}
        
        # 최근 개선 패턴 분석
        recent_improvements = [h['should_update'] for h in history[-5:]]
        improvement_count = sum(recent_improvements)
        
        # 성능 추이 분석
        performances = [h['new_performance']['overall'] for h in history[-5:]]
        performance_trend = np.polyfit(range(len(performances)), performances, 1)[0]
        
        # 정체 수준 계산
        stagnation_level = 0.0
        if improvement_count == 0:
            stagnation_level = 1.0
        elif improvement_count == 1:
            stagnation_level = 0.7
        elif improvement_count == 2:
            stagnation_level = 0.4
        
        # 추세 반영
        if performance_trend < -0.01:  # 하락 추세
            stagnation_level = min(1.0, stagnation_level + 0.2)
        
        return {
            "stagnation_level": stagnation_level,
            "improvement_count": improvement_count,
            "performance_trend": performance_trend,
            "pattern": self._identify_pattern(history)
        }
    
    def _identify_pattern(self, history: List[Dict]) -> str:
        """개선 패턴 식별"""
        if not history:
            return "no_data"
        
        # 패턴 분석
        recent = history[-5:] if len(history) >= 5 else history
        
        # 진동 패턴 확인
        improvements = [h['should_update'] for h in recent]
        if improvements == [True, False, True, False, True]:
            return "oscillating"
        
        # 지속적 하락
        performances = [h['new_performance']['overall'] for h in recent]
        if all(performances[i] > performances[i+1] for i in range(len(performances)-1)):
            return "continuous_decline"
        
        # 정체
        if len(set(performances)) == 1:
            return "complete_stagnation"
        
        # 점진적 개선
        if all(performances[i] <= performances[i+1] for i in range(len(performances)-1)):
            return "gradual_improvement"
        
        return "mixed"
    
    def select_strategy(self, stagnation_analysis: Dict[str, Any]) -> OptimizationStrategy:
        """현재 상황에 맞는 전략 선택"""
        stagnation_level = stagnation_analysis['stagnation_level']
        pattern = stagnation_analysis['pattern']
        
        # 탐색 vs 활용 결정
        if random.random() < self.exploration_rate:
            # 탐색: 위험도 높은 전략 시도
            if stagnation_level > 0.7:
                # 심각한 정체: 혁신적 전략
                candidates = [s for s in self.strategies if s.risk_level > 0.6]
            else:
                # 보통 정체: 균형/공격적 전략
                candidates = [s for s in self.strategies if 0.3 <= s.risk_level <= 0.6]
        else:
            # 활용: 안전한 전략
            if stagnation_level < 0.3:
                # 잘 되고 있음: 보수적 전략
                candidates = [s for s in self.strategies if s.risk_level < 0.3]
            else:
                # 개선 필요: 균형 전략
                candidates = [s for s in self.strategies if 0.2 <= s.risk_level <= 0.5]
        
        # 패턴별 전략 조정
        if pattern == "oscillating":
            # 진동 패턴: 하이브리드 전략 우선
            hybrid = next((s for s in candidates if s.name == "hybrid_intelligence"), None)
            if hybrid:
                return hybrid
        elif pattern == "continuous_decline":
            # 지속 하락: 혁신적 전략 필요
            innovative = next((s for s in candidates if s.name == "innovative_breakthrough"), None)
            if innovative:
                return innovative
        
        # 기대 이익 기준으로 선택
        return max(candidates, key=lambda s: s.expected_gain / (s.risk_level + 0.1))
    
    def generate_optimization_plan(self, strategy: OptimizationStrategy) -> Dict[str, Any]:
        """선택된 전략에 따른 최적화 계획 생성"""
        plan = {
            "strategy_name": strategy.name,
            "timestamp": datetime.now().isoformat(),
            "risk_level": strategy.risk_level,
            "expected_gain": strategy.expected_gain,
            "actions": []
        }
        
        # 전략별 구체적 액션 생성
        if strategy.name == "conservative_tuning":
            plan["actions"] = [
                {"type": "adjust_filters", "params": {"relaxation": 0.1}},
                {"type": "tune_models", "params": {"learning_rate": 0.001}},
                {"type": "update_weights", "params": {"shift": 0.05}}
            ]
        
        elif strategy.name == "balanced_optimization":
            plan["actions"] = [
                {"type": "adjust_filters", "params": {"relaxation": 0.2}},
                {"type": "add_features", "params": {"count": 5}},
                {"type": "ensemble_rebalance", "params": {"method": "weighted"}},
                {"type": "hyperparameter_search", "params": {"trials": 20}}
            ]
        
        elif strategy.name == "aggressive_exploration":
            plan["actions"] = [
                {"type": "filter_mutation", "params": {"mutation_rate": 0.3}},
                {"type": "model_hybridization", "params": {"models": ["lstm", "transformer"]}},
                {"type": "feature_engineering", "params": {"aggressive": True}},
                {"type": "ensemble_expansion", "params": {"new_models": 2}}
            ]
        
        elif strategy.name == "innovative_breakthrough":
            plan["actions"] = [
                {"type": "algorithm_switch", "params": {"new_algo": "quantum_inspired"}},
                {"type": "complete_ensemble_redesign", "params": {}},
                {"type": "adaptive_filter_system", "params": {"learning_rate": 0.1}},
                {"type": "meta_learning", "params": {"episodes": 100}}
            ]
        
        elif strategy.name == "hybrid_intelligence":
            plan["actions"] = [
                {"type": "multi_strategy_fusion", "params": {"strategies": 3}},
                {"type": "context_aware_switching", "params": {}},
                {"type": "self_adaptation", "params": {"rate": 0.01}},
                {"type": "continuous_learning", "params": {"enabled": True}}
            ]
        
        return plan
    
    def evaluate_optimization_result(self, before: Dict, after: Dict) -> Dict[str, Any]:
        """최적화 결과 평가"""
        improvement = after['overall'] - before['overall']
        improvement_rate = improvement / (before['overall'] + 0.001)
        
        evaluation = {
            "success": improvement > 0,
            "improvement": improvement,
            "improvement_rate": improvement_rate,
            "meets_expectation": False,
            "recommendation": ""
        }
        
        # 기대치 대비 평가
        if improvement_rate > 0.1:
            evaluation["meets_expectation"] = True
            evaluation["recommendation"] = "continue_current_strategy"
        elif improvement_rate > 0.02:
            evaluation["recommendation"] = "adjust_parameters"
        else:
            evaluation["recommendation"] = "switch_strategy"
        
        return evaluation
    
    def adapt_exploration_rate(self, evaluation: Dict[str, Any]):
        """탐색률 동적 조정"""
        if evaluation["success"]:
            # 성공: 탐색 감소, 활용 증가
            self.exploration_rate = max(0.1, self.exploration_rate - 0.05)
        else:
            # 실패: 탐색 증가
            self.exploration_rate = min(0.5, self.exploration_rate + 0.1)
        
        self.exploitation_rate = 1.0 - self.exploration_rate
        
        logging.info(f"탐색률 조정: {self.exploration_rate:.2f} (탐색) / {self.exploitation_rate:.2f} (활용)")
    
    def get_meta_status(self) -> Dict[str, Any]:
        """메타 최적화 상태 반환"""
        return {
            "exploration_rate": self.exploration_rate,
            "exploitation_rate": self.exploitation_rate,
            "available_strategies": len(self.strategies),
            "strategy_details": [
                {
                    "name": s.name,
                    "risk": s.risk_level,
                    "expected_gain": s.expected_gain
                }
                for s in self.strategies
            ]
        }

# 메타 최적화 실행 함수
def run_meta_optimization():
    """메타 최적화 실행"""
    meta_optimizer = MetaOptimizer()
    
    # 1. 정체 상태 분석
    stagnation = meta_optimizer.analyze_stagnation()
    logging.info(f"정체 분석: {stagnation}")
    
    # 2. 전략 선택
    strategy = meta_optimizer.select_strategy(stagnation)
    logging.info(f"선택된 전략: {strategy.name} (위험도: {strategy.risk_level})")
    
    # 3. 최적화 계획 생성
    plan = meta_optimizer.generate_optimization_plan(strategy)
    logging.info(f"최적화 계획: {len(plan['actions'])}개 액션")
    
    return plan

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    plan = run_meta_optimization()
    print(json.dumps(plan, indent=2, ensure_ascii=False))