"""
인간 직관 통합 시스템
- 전문가의 경험과 직관을 AI와 결합
- 도메인 지식을 활용한 예측 개선
"""

import numpy as np
import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class ExpertRule:
    """전문가 규칙"""
    name: str
    description: str
    rule_type: str  # 'filter', 'boost', 'penalty'
    confidence: float  # 0.0 ~ 1.0
    conditions: Dict[str, Any]
    action: Dict[str, Any]

class ExpertKnowledgeBase:
    """전문가 지식 베이스"""
    
    def __init__(self):
        self.rules = self._initialize_expert_rules()
        self.patterns = self._initialize_patterns()
        self.intuitions = self._initialize_intuitions()
        
    def _initialize_expert_rules(self) -> List[ExpertRule]:
        """전문가 규칙 초기화"""
        return [
            # 통계적 규칙
            ExpertRule(
                name="birthday_paradox",
                description="생일 번호(1-31)가 3개 이상 나올 확률이 높음",
                rule_type="boost",
                confidence=0.7,
                conditions={"birthday_count": ">=3"},
                action={"score_multiplier": 1.2}
            ),
            
            ExpertRule(
                name="golden_ratio",
                description="황금비율에 가까운 번호 분포 선호",
                rule_type="boost",
                confidence=0.6,
                conditions={"ratio_check": "golden"},
                action={"score_multiplier": 1.15}
            ),
            
            ExpertRule(
                name="avoid_all_even",
                description="모두 짝수인 조합은 역사상 없었음",
                rule_type="filter",
                confidence=0.95,
                conditions={"even_count": 6},
                action={"exclude": True}
            ),
            
            ExpertRule(
                name="prime_presence",
                description="소수가 2-3개 포함된 조합 선호",
                rule_type="boost",
                confidence=0.65,
                conditions={"prime_count": [2, 3]},
                action={"score_multiplier": 1.1}
            ),
            
            # 심리적 규칙
            ExpertRule(
                name="avoid_obvious_patterns",
                description="1,2,3,4,5,6 같은 명백한 패턴 회피",
                rule_type="penalty",
                confidence=0.9,
                conditions={"is_obvious_pattern": True},
                action={"score_multiplier": 0.1}
            ),
            
            ExpertRule(
                name="lucky_numbers",
                description="문화적 행운 번호 포함 시 가산점",
                rule_type="boost",
                confidence=0.5,
                conditions={"has_lucky_numbers": True},
                action={"score_multiplier": 1.05}
            ),
            
            # 시즌별 규칙
            ExpertRule(
                name="seasonal_tendency",
                description="계절별 번호 출현 경향",
                rule_type="boost",
                confidence=0.6,
                conditions={"matches_season": True},
                action={"score_multiplier": 1.1}
            ),
            
            # 최근 트렌드
            ExpertRule(
                name="hot_cold_balance",
                description="핫넘버와 콜드넘버의 균형",
                rule_type="boost",
                confidence=0.7,
                conditions={"hot_cold_ratio": [0.4, 0.6]},
                action={"score_multiplier": 1.15}
            )
        ]
    
    def _initialize_patterns(self) -> Dict[str, Any]:
        """전문가가 발견한 패턴"""
        return {
            "fibonacci_preference": {
                "numbers": [1, 2, 3, 5, 8, 13, 21, 34],
                "description": "피보나치 수열 번호 선호",
                "weight": 1.1
            },
            "corner_numbers": {
                "numbers": [1, 7, 39, 45],
                "description": "모서리 번호 포함 경향",
                "weight": 1.05
            },
            "center_cluster": {
                "range": [15, 30],
                "description": "중앙 범위 번호 집중",
                "weight": 1.08
            },
            "decade_distribution": {
                "pattern": "1-2-2-1",
                "description": "10단위별 분포 패턴",
                "weight": 1.12
            }
        }
    
    def _initialize_intuitions(self) -> Dict[str, Any]:
        """전문가의 직관적 지식"""
        return {
            "feeling_factors": {
                "symmetry": 0.7,  # 대칭적 분포 선호
                "spacing": 0.8,   # 적절한 간격 선호
                "diversity": 0.9, # 다양성 선호
                "memorability": 0.6  # 기억하기 쉬운 조합
            },
            "avoid_factors": {
                "too_clustered": 0.3,  # 너무 몰린 번호
                "too_scattered": 0.4,  # 너무 흩어진 번호
                "too_regular": 0.2,    # 너무 규칙적
                "too_random": 0.5      # 너무 무작위
            }
        }

class HumanIntuitionIntegrator:
    """인간 직관 통합기"""
    
    def __init__(self):
        self.knowledge_base = ExpertKnowledgeBase()
        self.learning_history = []
        self.expert_feedback = []
        
    def evaluate_with_intuition(self, numbers: List[int], ai_score: float) -> Dict[str, Any]:
        """AI 예측에 인간 직관 적용"""
        evaluation = {
            'original_score': ai_score,
            'intuition_adjustments': [],
            'final_score': ai_score,
            'confidence': 0.5,
            'expert_notes': []
        }
        
        # 각 규칙 적용
        for rule in self.knowledge_base.rules:
            if self._check_rule_conditions(numbers, rule):
                adjustment = self._apply_rule(rule, evaluation['final_score'])
                evaluation['intuition_adjustments'].append({
                    'rule': rule.name,
                    'description': rule.description,
                    'impact': adjustment['impact'],
                    'confidence': rule.confidence
                })
                evaluation['final_score'] = adjustment['new_score']
                
                if adjustment['impact'] != 0:
                    evaluation['expert_notes'].append(
                        f"{rule.description} (신뢰도: {rule.confidence:.0%})"
                    )
        
        # 패턴 체크
        pattern_score = self._evaluate_patterns(numbers)
        if pattern_score != 1.0:
            evaluation['final_score'] *= pattern_score
            evaluation['intuition_adjustments'].append({
                'rule': 'pattern_analysis',
                'description': '전문가 패턴 분석',
                'impact': pattern_score - 1.0,
                'confidence': 0.7
            })
        
        # 직관적 평가
        intuition_score = self._evaluate_intuition(numbers)
        evaluation['final_score'] *= intuition_score
        evaluation['intuition_adjustments'].append({
            'rule': 'expert_intuition',
            'description': '전문가 직관',
            'impact': intuition_score - 1.0,
            'confidence': 0.6
        })
        
        # 최종 신뢰도 계산
        evaluation['confidence'] = self._calculate_confidence(
            ai_score, 
            evaluation['final_score'],
            len(evaluation['intuition_adjustments'])
        )
        
        return evaluation
    
    def _check_rule_conditions(self, numbers: List[int], rule: ExpertRule) -> bool:
        """규칙 조건 확인"""
        conditions = rule.conditions
        
        # 생일 번호 체크
        if 'birthday_count' in conditions:
            birthday_count = sum(1 for n in numbers if 1 <= n <= 31)
            if conditions['birthday_count'].startswith('>='):
                required = int(conditions['birthday_count'][2:])
                return birthday_count >= required
        
        # 짝수 개수 체크
        if 'even_count' in conditions:
            even_count = sum(1 for n in numbers if n % 2 == 0)
            return even_count == conditions['even_count']
        
        # 소수 개수 체크
        if 'prime_count' in conditions:
            primes = [2,3,5,7,11,13,17,19,23,29,31,37,41,43]
            prime_count = sum(1 for n in numbers if n in primes)
            if isinstance(conditions['prime_count'], list):
                return prime_count in conditions['prime_count']
            return prime_count == conditions['prime_count']
        
        # 황금비율 체크
        if 'ratio_check' in conditions and conditions['ratio_check'] == 'golden':
            sorted_nums = sorted(numbers)
            ratios = []
            for i in range(len(sorted_nums)-1):
                if sorted_nums[i] > 0:
                    ratios.append(sorted_nums[i+1] / sorted_nums[i])
            golden_ratio = 1.618
            return any(abs(r - golden_ratio) < 0.1 for r in ratios)
        
        # 명백한 패턴 체크
        if 'is_obvious_pattern' in conditions:
            # 연속된 6개 번호
            sorted_nums = sorted(numbers)
            is_consecutive = all(sorted_nums[i+1] - sorted_nums[i] == 1 
                               for i in range(5))
            # 등차수열
            if len(set(sorted_nums[i+1] - sorted_nums[i] for i in range(5))) == 1:
                return True
            return is_consecutive
        
        # 행운 번호 체크
        if 'has_lucky_numbers' in conditions:
            lucky_numbers = [7, 8, 3, 9]  # 문화적 행운 번호
            return any(n in lucky_numbers for n in numbers)
        
        # 핫/콜드 비율 체크
        if 'hot_cold_ratio' in conditions:
            # 실제로는 최근 출현 빈도 확인 필요
            # 여기서는 시뮬레이션
            hot_numbers = [n for n in numbers if n % 3 == 0]  # 임시
            ratio = len(hot_numbers) / 6
            min_ratio, max_ratio = conditions['hot_cold_ratio']
            return min_ratio <= ratio <= max_ratio
        
        return False
    
    def _apply_rule(self, rule: ExpertRule, current_score: float) -> Dict[str, Any]:
        """규칙 적용"""
        action = rule.action
        
        if rule.rule_type == 'filter' and action.get('exclude'):
            return {'new_score': 0.0, 'impact': -current_score}
        
        elif 'score_multiplier' in action:
            multiplier = action['score_multiplier']
            new_score = current_score * multiplier
            return {
                'new_score': new_score,
                'impact': new_score - current_score
            }
        
        return {'new_score': current_score, 'impact': 0.0}
    
    def _evaluate_patterns(self, numbers: List[int]) -> float:
        """패턴 평가"""
        score_multiplier = 1.0
        patterns = self.knowledge_base.patterns
        
        # 피보나치 체크
        fib_numbers = patterns['fibonacci_preference']['numbers']
        fib_count = sum(1 for n in numbers if n in fib_numbers)
        if fib_count >= 2:
            score_multiplier *= patterns['fibonacci_preference']['weight']
        
        # 모서리 번호 체크
        corner_numbers = patterns['corner_numbers']['numbers']
        if any(n in corner_numbers for n in numbers):
            score_multiplier *= patterns['corner_numbers']['weight']
        
        # 중앙 클러스터 체크
        center_range = patterns['center_cluster']['range']
        center_count = sum(1 for n in numbers 
                          if center_range[0] <= n <= center_range[1])
        if 2 <= center_count <= 4:
            score_multiplier *= patterns['center_cluster']['weight']
        
        return score_multiplier
    
    def _evaluate_intuition(self, numbers: List[int]) -> float:
        """직관적 평가"""
        intuitions = self.knowledge_base.intuitions
        feeling_score = 1.0
        
        # 대칭성 평가
        sorted_nums = sorted(numbers)
        center = 23  # 1-45의 중앙
        symmetry = 0
        for num in sorted_nums:
            mirror = center * 2 - num
            if 1 <= mirror <= 45 and mirror in sorted_nums:
                symmetry += 1
        
        if symmetry >= 2:
            feeling_score *= (1 + intuitions['feeling_factors']['symmetry'] * 0.1)
        
        # 간격 평가
        gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(5)]
        avg_gap = np.mean(gaps)
        gap_std = np.std(gaps)
        
        if 5 <= avg_gap <= 10 and gap_std < 5:
            feeling_score *= (1 + intuitions['feeling_factors']['spacing'] * 0.1)
        
        # 너무 몰려있거나 흩어져있으면 감점
        if max(gaps) < 3:
            feeling_score *= intuitions['avoid_factors']['too_clustered']
        elif min(gaps) > 15:
            feeling_score *= intuitions['avoid_factors']['too_scattered']
        
        return feeling_score
    
    def _calculate_confidence(self, ai_score: float, final_score: float, 
                            num_adjustments: int) -> float:
        """신뢰도 계산"""
        # AI와 직관의 일치도
        agreement = 1 - abs(ai_score - final_score) / max(ai_score, 0.01)
        
        # 조정 횟수가 적을수록 신뢰도 높음
        adjustment_factor = 1 - (num_adjustments * 0.05)
        
        # 최종 신뢰도
        confidence = (agreement * 0.7 + adjustment_factor * 0.3)
        
        return np.clip(confidence, 0.1, 0.95)
    
    def learn_from_feedback(self, prediction: List[int], actual: List[int], 
                           expert_comment: Optional[str] = None):
        """전문가 피드백으로부터 학습"""
        matches = len(set(prediction) & set(actual))
        
        feedback = {
            'timestamp': datetime.now().isoformat(),
            'prediction': prediction,
            'actual': actual,
            'matches': matches,
            'expert_comment': expert_comment,
            'success': matches >= 3  # 3개 이상 맞추면 성공
        }
        
        self.expert_feedback.append(feedback)
        
        # 규칙 신뢰도 업데이트
        if matches >= 4:  # 좋은 예측
            # 사용된 규칙의 신뢰도 증가
            for rule in self.knowledge_base.rules:
                if self._check_rule_conditions(prediction, rule):
                    rule.confidence = min(0.95, rule.confidence * 1.05)
        elif matches <= 1:  # 나쁜 예측
            # 사용된 규칙의 신뢰도 감소
            for rule in self.knowledge_base.rules:
                if self._check_rule_conditions(prediction, rule):
                    rule.confidence = max(0.1, rule.confidence * 0.95)
    
    def get_expert_insights(self) -> Dict[str, Any]:
        """전문가 인사이트 제공"""
        insights = {
            'total_rules': len(self.knowledge_base.rules),
            'high_confidence_rules': [],
            'recent_performance': self._calculate_recent_performance(),
            'top_patterns': self._get_top_patterns(),
            'recommendations': []
        }
        
        # 높은 신뢰도 규칙
        for rule in self.knowledge_base.rules:
            if rule.confidence > 0.8:
                insights['high_confidence_rules'].append({
                    'name': rule.name,
                    'description': rule.description,
                    'confidence': rule.confidence
                })
        
        # 추천사항
        if insights['recent_performance'] < 0.5:
            insights['recommendations'].append(
                "AI 예측에 더 의존하고 직관적 조정을 줄이세요"
            )
        else:
            insights['recommendations'].append(
                "현재 직관적 조정이 잘 작동하고 있습니다"
            )
        
        return insights
    
    def _calculate_recent_performance(self) -> float:
        """최근 성능 계산"""
        if len(self.expert_feedback) < 5:
            return 0.5
        
        recent = self.expert_feedback[-20:]
        success_count = sum(1 for f in recent if f['success'])
        
        return success_count / len(recent)
    
    def _get_top_patterns(self) -> List[Dict[str, Any]]:
        """상위 패턴 추출"""
        pattern_scores = []
        
        for name, pattern in self.knowledge_base.patterns.items():
            score = pattern.get('weight', 1.0)
            pattern_scores.append({
                'name': name,
                'description': pattern['description'],
                'weight': score
            })
        
        # 가중치 기준 정렬
        pattern_scores.sort(key=lambda x: x['weight'], reverse=True)
        
        return pattern_scores[:5]

def create_human_ai_hybrid_system():
    """인간-AI 하이브리드 시스템 생성"""
    return HumanIntuitionIntegrator()

if __name__ == "__main__":
    # 테스트
    integrator = create_human_ai_hybrid_system()
    
    # 테스트 번호
    test_numbers = [7, 14, 21, 28, 35, 42]
    ai_score = 0.75
    
    # 직관 적용
    result = integrator.evaluate_with_intuition(test_numbers, ai_score)
    
    print("=== 인간 직관 통합 결과 ===")
    print(f"원본 AI 점수: {result['original_score']:.3f}")
    print(f"최종 점수: {result['final_score']:.3f}")
    print(f"신뢰도: {result['confidence']:.1%}")
    print(f"\n전문가 노트:")
    for note in result['expert_notes']:
        print(f"  - {note}")
    
    # 인사이트
    insights = integrator.get_expert_insights()
    print(f"\n높은 신뢰도 규칙: {len(insights['high_confidence_rules'])}개")