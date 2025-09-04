"""
동적 전략 관리자
- 상황에 따라 예측 전략을 자동으로 전환
- 공격적/균형/보수적 모드 지원
"""

import numpy as np
import json
import logging
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

class StrategyMode(Enum):
    """전략 모드"""
    CONSERVATIVE = "conservative"  # 보수적 (안전)
    BALANCED = "balanced"  # 균형
    AGGRESSIVE = "aggressive"  # 공격적
    ADAPTIVE = "adaptive"  # 적응형
    EXPERIMENTAL = "experimental"  # 실험적

@dataclass
class StrategyProfile:
    """전략 프로필"""
    mode: StrategyMode
    name: str
    description: str
    filter_strictness: float  # 0.0 (느슨함) ~ 1.0 (엄격함)
    prediction_diversity: float  # 0.0 (집중) ~ 1.0 (다양함)
    risk_tolerance: float  # 0.0 (위험 회피) ~ 1.0 (위험 감수)
    model_selection: List[str]  # 사용할 모델 목록
    combination_count: int  # 생성할 조합 수

class DynamicStrategyManager:
    """동적 전략 관리자"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = config_path
        self.current_mode = StrategyMode.BALANCED
        self.performance_history = []
        self.mode_history = []
        self.strategies = self._initialize_strategies()
        self.switch_threshold = 0.05  # 전환 임계값
        self.stability_window = 5  # 안정성 확인 윈도우
        
    def _initialize_strategies(self) -> Dict[StrategyMode, StrategyProfile]:
        """전략 프로필 초기화"""
        return {
            StrategyMode.CONSERVATIVE: StrategyProfile(
                mode=StrategyMode.CONSERVATIVE,
                name="보수적 전략",
                description="검증된 패턴과 안전한 예측에 집중",
                filter_strictness=0.9,  # 매우 엄격한 필터링
                prediction_diversity=0.2,  # 낮은 다양성
                risk_tolerance=0.1,  # 낮은 위험 감수
                model_selection=[
                    'ensemble_classic',  # 검증된 앙상블
                    'gradient_boosting',  # 안정적인 부스팅
                    'extra_trees'  # 안정적인 트리
                ],
                combination_count=5  # 적은 조합
            ),
            
            StrategyMode.BALANCED: StrategyProfile(
                mode=StrategyMode.BALANCED,
                name="균형 전략",
                description="안정성과 혁신의 균형",
                filter_strictness=0.6,  # 중간 필터링
                prediction_diversity=0.5,  # 중간 다양성
                risk_tolerance=0.5,  # 중간 위험
                model_selection=[
                    'lstm',
                    'ensemble_classic',
                    'lightgbm',
                    'catboost',
                    'transformer'
                ],
                combination_count=10  # 표준 조합
            ),
            
            StrategyMode.AGGRESSIVE: StrategyProfile(
                mode=StrategyMode.AGGRESSIVE,
                name="공격적 전략",
                description="높은 위험, 높은 보상 추구",
                filter_strictness=0.3,  # 느슨한 필터링
                prediction_diversity=0.8,  # 높은 다양성
                risk_tolerance=0.8,  # 높은 위험 감수
                model_selection=[
                    'transformer',
                    'quantum_inspired',
                    'hybrid_deep',
                    'lightgbm',
                    'catboost',
                    'svm'
                ],
                combination_count=20  # 많은 조합
            ),
            
            StrategyMode.ADAPTIVE: StrategyProfile(
                mode=StrategyMode.ADAPTIVE,
                name="적응형 전략",
                description="실시간으로 최적 전략 선택",
                filter_strictness=0.5,  # 동적 조정
                prediction_diversity=0.6,  # 동적 조정
                risk_tolerance=0.6,  # 동적 조정
                model_selection='dynamic',  # 성능 기반 선택
                combination_count=15  # 동적 조정
            ),
            
            StrategyMode.EXPERIMENTAL: StrategyProfile(
                mode=StrategyMode.EXPERIMENTAL,
                name="실험적 전략",
                description="새로운 패턴과 알고리즘 테스트",
                filter_strictness=0.2,  # 매우 느슨함
                prediction_diversity=1.0,  # 최대 다양성
                risk_tolerance=1.0,  # 최대 위험
                model_selection=[
                    'quantum_inspired',
                    'hybrid_deep',
                    'transformer',
                    'naive_bayes',
                    'knn'
                ],
                combination_count=30  # 최대 조합
            )
        }
    
    def analyze_current_situation(self) -> Dict[str, Any]:
        """현재 상황 분석"""
        analysis = {
            'performance_trend': self._calculate_performance_trend(),
            'volatility': self._calculate_volatility(),
            'recent_success_rate': self._calculate_recent_success_rate(),
            'stability_score': self._calculate_stability_score(),
            'jackpot_proximity': self._analyze_jackpot_proximity(),
            'pattern_confidence': self._analyze_pattern_confidence()
        }
        
        # 종합 점수 계산
        analysis['overall_score'] = self._calculate_overall_score(analysis)
        
        return analysis
    
    def _calculate_performance_trend(self) -> float:
        """성능 추세 계산 (-1.0 ~ 1.0)"""
        if len(self.performance_history) < 3:
            return 0.0
        
        recent = self.performance_history[-10:]
        if len(recent) < 3:
            return 0.0
        
        # 선형 회귀로 추세 계산
        x = np.arange(len(recent))
        y = np.array(recent)
        
        if len(x) > 1:
            trend = np.polyfit(x, y, 1)[0]
            return np.clip(trend * 10, -1.0, 1.0)  # 정규화
        
        return 0.0
    
    def _calculate_volatility(self) -> float:
        """변동성 계산 (0.0 ~ 1.0)"""
        if len(self.performance_history) < 5:
            return 0.5
        
        recent = self.performance_history[-20:]
        volatility = np.std(recent)
        
        return min(volatility * 2, 1.0)  # 정규화
    
    def _calculate_recent_success_rate(self) -> float:
        """최근 성공률 계산 (0.0 ~ 1.0)"""
        if len(self.performance_history) < 1:
            return 0.5
        
        recent = self.performance_history[-10:]
        success_threshold = 0.8  # 평균 0.8개 이상 맞추면 성공
        
        success_count = sum(1 for p in recent if p >= success_threshold)
        return success_count / len(recent)
    
    def _calculate_stability_score(self) -> float:
        """안정성 점수 계산 (0.0 ~ 1.0)"""
        if len(self.mode_history) < self.stability_window:
            return 0.5
        
        # 최근 모드 변경 빈도 확인
        recent_modes = self.mode_history[-self.stability_window:]
        mode_changes = sum(1 for i in range(1, len(recent_modes)) 
                          if recent_modes[i] != recent_modes[i-1])
        
        # 변경이 적을수록 안정적
        stability = 1.0 - (mode_changes / (self.stability_window - 1))
        return stability
    
    def _analyze_jackpot_proximity(self) -> float:
        """대박 근접도 분석 (0.0 ~ 1.0)"""
        # 실제로는 과거 당첨 패턴과 현재 예측 비교
        # 여기서는 시뮬레이션
        if len(self.performance_history) < 5:
            return 0.5
        
        # 최근 성능이 급상승하면 대박 근접
        recent = self.performance_history[-5:]
        if all(recent[i] < recent[i+1] for i in range(len(recent)-1)):
            return 0.8
        
        return 0.3
    
    def _analyze_pattern_confidence(self) -> float:
        """패턴 신뢰도 분석 (0.0 ~ 1.0)"""
        # 패턴이 일관되게 나타나는지 확인
        if len(self.performance_history) < 10:
            return 0.5
        
        recent = self.performance_history[-20:]
        mean_performance = np.mean(recent)
        std_performance = np.std(recent)
        
        # 변동성이 낮고 평균이 높으면 신뢰도 높음
        if std_performance < 0.2 and mean_performance > 0.8:
            return 0.9
        elif std_performance > 0.5:
            return 0.3
        
        return 0.5
    
    def _calculate_overall_score(self, analysis: Dict[str, Any]) -> float:
        """종합 점수 계산"""
        weights = {
            'performance_trend': 0.25,
            'volatility': -0.15,  # 변동성은 부정적
            'recent_success_rate': 0.30,
            'stability_score': 0.15,
            'jackpot_proximity': 0.10,
            'pattern_confidence': 0.20
        }
        
        score = 0.0
        for key, weight in weights.items():
            if key == 'volatility':
                score += weight * (1 - analysis[key])  # 변동성은 반대로
            else:
                score += weight * analysis.get(key, 0.5)
        
        return np.clip(score, 0.0, 1.0)
    
    def recommend_strategy(self, situation: Dict[str, Any]) -> StrategyMode:
        """상황에 맞는 전략 추천"""
        score = situation['overall_score']
        trend = situation['performance_trend']
        volatility = situation['volatility']
        stability = situation['stability_score']
        
        # 규칙 기반 전략 선택
        if score > 0.8 and trend > 0.5:
            # 성능 좋고 상승 추세: 공격적
            return StrategyMode.AGGRESSIVE
        
        elif score < 0.3 or volatility > 0.7:
            # 성능 나쁘거나 변동성 높음: 보수적
            return StrategyMode.CONSERVATIVE
        
        elif stability < 0.3:
            # 불안정함: 적응형
            return StrategyMode.ADAPTIVE
        
        elif score > 0.6 and volatility < 0.3:
            # 성능 괜찮고 안정적: 실험적 시도
            return StrategyMode.EXPERIMENTAL
        
        else:
            # 기본: 균형
            return StrategyMode.BALANCED
    
    def should_switch_strategy(self, current_performance: float) -> bool:
        """전략 전환 필요 여부 판단"""
        if len(self.performance_history) < 3:
            return False
        
        # 성능 기록
        self.performance_history.append(current_performance)
        
        # 현재 상황 분석
        situation = self.analyze_current_situation()
        recommended = self.recommend_strategy(situation)
        
        # 현재 전략과 추천 전략이 다르고, 점수 차이가 임계값 이상이면 전환
        if recommended != self.current_mode:
            current_strategy = self.strategies[self.current_mode]
            recommended_strategy = self.strategies[recommended]
            
            # 위험도 차이 고려
            risk_diff = abs(current_strategy.risk_tolerance - 
                          recommended_strategy.risk_tolerance)
            
            if situation['overall_score'] < 0.3 or situation['overall_score'] > 0.7:
                # 극단적 상황에서는 즉시 전환
                return True
            elif risk_diff > 0.5:
                # 위험도 차이가 크면 신중하게
                return situation['stability_score'] > 0.5
            else:
                return True
        
        return False
    
    def switch_strategy(self, new_mode: StrategyMode) -> Dict[str, Any]:
        """전략 전환"""
        old_mode = self.current_mode
        self.current_mode = new_mode
        self.mode_history.append(new_mode)
        
        # 전략 프로필 가져오기
        new_strategy = self.strategies[new_mode]
        
        # 설정 업데이트
        updates = {
            'strategy_switched': True,
            'old_mode': old_mode.value,
            'new_mode': new_mode.value,
            'timestamp': datetime.now().isoformat(),
            'config_updates': self._generate_config_updates(new_strategy)
        }
        
        logging.info(f"전략 전환: {old_mode.value} → {new_mode.value}")
        
        return updates
    
    def _generate_config_updates(self, strategy: StrategyProfile) -> Dict[str, Any]:
        """전략에 따른 설정 업데이트 생성"""
        updates = {
            'filters': {
                'strictness_multiplier': strategy.filter_strictness,
                'enabled_filters': self._select_filters(strategy)
            },
            'ml': {
                'active_models': strategy.model_selection,
                'ensemble_diversity': strategy.prediction_diversity,
                'prediction_count': strategy.combination_count
            },
            'risk_management': {
                'risk_tolerance': strategy.risk_tolerance,
                'safety_checks': strategy.risk_tolerance < 0.3
            }
        }
        
        return updates
    
    def _select_filters(self, strategy: StrategyProfile) -> List[str]:
        """전략에 따른 필터 선택"""
        all_filters = [
            'match', 'odd_even', 'consecutive', 'sum_range',
            'fixed_step', 'last_digit', 'max_gap', 'section',
            'average', 'multiple', 'ten_section', 'arithmetic_sequence',
            'geometric_sequence', 'prime_composite', 'digit_sum',
            'dispersion', 'ml_prediction'
        ]
        
        if strategy.filter_strictness > 0.8:
            # 보수적: 모든 필터 사용
            return all_filters
        elif strategy.filter_strictness > 0.5:
            # 균형: 주요 필터만
            return all_filters[:12]
        else:
            # 공격적: 최소 필터
            return ['match', 'odd_even', 'consecutive', 'sum_range', 'ml_prediction']
    
    def get_current_strategy_info(self) -> Dict[str, Any]:
        """현재 전략 정보 반환"""
        current_strategy = self.strategies[self.current_mode]
        
        return {
            'mode': self.current_mode.value,
            'name': current_strategy.name,
            'description': current_strategy.description,
            'settings': {
                'filter_strictness': current_strategy.filter_strictness,
                'prediction_diversity': current_strategy.prediction_diversity,
                'risk_tolerance': current_strategy.risk_tolerance,
                'combination_count': current_strategy.combination_count
            },
            'active_models': current_strategy.model_selection,
            'performance_history_length': len(self.performance_history),
            'mode_history': [m.value for m in self.mode_history[-10:]]
        }
    
    def save_state(self, filepath: str = 'dynamic_strategy_state.json'):
        """상태 저장"""
        state = {
            'current_mode': self.current_mode.value,
            'performance_history': self.performance_history[-100:],  # 최근 100개만
            'mode_history': [m.value for m in self.mode_history[-50:]],  # 최근 50개만
            'last_updated': datetime.now().isoformat()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def load_state(self, filepath: str = 'dynamic_strategy_state.json'):
        """상태 로드"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            self.current_mode = StrategyMode(state.get('current_mode', 'balanced'))
            self.performance_history = state.get('performance_history', [])
            self.mode_history = [StrategyMode(m) for m in state.get('mode_history', [])]
            
            logging.info(f"전략 상태 로드: 현재 모드 = {self.current_mode.value}")
            
        except Exception as e:
            logging.warning(f"전략 상태 로드 실패: {str(e)}")

# 테스트 함수
def test_dynamic_strategy():
    """동적 전략 테스트"""
    manager = DynamicStrategyManager()
    
    # 시뮬레이션 데이터
    performance_data = [
        0.5, 0.6, 0.7, 0.8, 0.9,  # 상승 추세
        0.8, 0.7, 0.6, 0.5, 0.4,  # 하락 추세
        0.9, 0.3, 0.8, 0.2, 0.9,  # 높은 변동성
        0.7, 0.7, 0.7, 0.7, 0.7   # 안정적
    ]
    
    for i, performance in enumerate(performance_data):
        print(f"\n라운드 {i+1}: 성능 = {performance}")
        
        # 전략 전환 확인
        if manager.should_switch_strategy(performance):
            situation = manager.analyze_current_situation()
            recommended = manager.recommend_strategy(situation)
            result = manager.switch_strategy(recommended)
            print(f"전략 전환: {result['old_mode']} → {result['new_mode']}")
        
        # 현재 전략 정보
        info = manager.get_current_strategy_info()
        print(f"현재 전략: {info['name']} (위험도: {info['settings']['risk_tolerance']})")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_dynamic_strategy()