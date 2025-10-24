"""
가중치 기반 필터 시스템
각 필터의 중요도에 따라 가중치를 적용하여 유연한 필터링 수행
"""

import logging
from typing import List, Dict, Tuple
import numpy as np

class WeightedFilterSystem:
    """가중치 기반 필터 시스템"""
    
    def __init__(self, filter_manager):
        """
        초기화
        
        Args:
            filter_manager: FilterManager 인스턴스
        """
        self.filter_manager = filter_manager
        self.logger = logging.getLogger(__name__)
        
        # 필터별 가중치 (실제 성능 기반 조정)
        self.filter_weights = {
            'match': 1.0,            # 100% 통과율 - 핵심 필터
            'odd_even': 0.9,         # 100% 통과율 - 중요 필터
            'consecutive': 0.9,      # 100% 통과율 - 중요 필터
            'sum_range': 0.8,        # 94% 통과율 - 준중요 필터
            'last_digit': 0.7,       # 100% 통과율
            'max_gap': 0.7,          # 100% 통과율
            'section': 0.3,          # 64% 통과율 - 문제 필터 (낮은 가중치)
            'average': 0.8,          # 96% 통과율
            'multiple': 0.4,         # 82% 통과율 - 문제 필터
            'ten_section': 0.6,      # 100% 통과율
            'arithmetic_sequence': 0.5,  # 100% 통과율
            'geometric_sequence': 0.5,   # 100% 통과율
            'prime_composite': 0.6,       # 92% 통과율
            'digit_sum': 0.6,        # 100% 통과율
            'dispersion': 0.35,      # 78% 통과율 - 문제 필터
            'fixed_step': 0.25,      # 84% 통과율 - 문제 필터 (가장 낮은 가중치)
            'ml_prediction': 0.8     # ML 예측
        }
        
        # 통과 임계값 (100점 만점 기준)
        # 1% 임계값 = 99% 통과율을 위해 매우 낮은 점수 설정
        self.pass_threshold = 30.0  # 30점 이상이면 통과 (1% 임계값 반영)
        
        # 동적 조정 파라미터
        self.min_winning_pass_rate = 0.7  # 최소 당첨번호 통과율 70%
        self.adjustment_factor = 0.9      # 조정 계수
        
    def evaluate_combination(self, combination, round_num=None):
        """
        가중치 기반으로 조합 평가
        
        Args:
            combination: 평가할 번호 조합 (List[int] 또는 "1,2,3,4,5,6" 형식)
            round_num: 회차 번호 (선택적)
            
        Returns:
            Dict: {'passed': bool, 'total_score': float, 'filter_results': dict}
        """
        # 문자열이면 리스트로 변환
        if isinstance(combination, str):
            combination = [int(n) for n in combination.split(',')]
        
        total_score = 0.0
        max_possible_score = 0.0
        filter_results = {}
        
        for filter_name, filter_obj in self.filter_manager.filters.items():
            if filter_name not in self.filter_weights:
                continue
                
            weight = self.filter_weights[filter_name]
            max_possible_score += weight * 100
            
            try:
                # 필터 통과 여부 확인
                # 조합을 문자열로 변환하여 필터에 전달
                combination_str = ','.join(map(str, combination))
                
                # 필터 적용 (apply 메서드 사용)
                result = filter_obj.apply([combination_str], round_num)
                passed = len(result) > 0  # 결과가 있으면 통과
                score = 100 if passed else 0
                
                # 가중치 적용
                weighted_score = score * weight
                total_score += weighted_score
                
                filter_results[filter_name] = {
                    'passed': passed,
                    'score': score,
                    'weight': weight,
                    'weighted_score': weighted_score
                }
                
            except Exception as e:
                self.logger.warning(f"{filter_name} 필터 평가 실패: {e}")
                # 실패한 필터는 중립 점수 (50점) 부여
                weighted_score = 50 * weight
                total_score += weighted_score
                filter_results[filter_name] = {
                    'passed': None,
                    'score': 50,
                    'weight': weight,
                    'weighted_score': weighted_score,
                    'error': str(e)
                }
        
        # 정규화된 점수 계산 (0-100 범위)
        normalized_score = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
        
        # 통과 여부 결정
        passed = normalized_score >= self.pass_threshold
        
        return {
            'passed': passed,
            'total_score': normalized_score,
            'filter_results': filter_results
        }
    
    def auto_adjust_weights(self, validation_results: List[Dict]):
        """
        검증 결과를 기반으로 가중치 자동 조정
        
        Args:
            validation_results: 필터 검증 결과 리스트
        """
        if not validation_results:
            return
            
        # 각 필터의 통과율 계산
        filter_pass_rates = {}
        for filter_name in self.filter_weights:
            passed = sum(1 for r in validation_results 
                        if filter_name not in r.get('failed_filters', []))
            total = len(validation_results)
            filter_pass_rates[filter_name] = passed / total if total > 0 else 0
        
        # 가중치 조정
        for filter_name, pass_rate in filter_pass_rates.items():
            if pass_rate < 0.7:  # 70% 미만 통과율
                # 가중치 감소 (문제가 있는 필터)
                self.filter_weights[filter_name] *= 0.8
                self.filter_weights[filter_name] = max(0.1, self.filter_weights[filter_name])
                self.logger.info(f"{filter_name} 필터 가중치 감소: {self.filter_weights[filter_name]:.2f}")
                
            elif pass_rate > 0.95:  # 95% 이상 통과율
                # 가중치 증가 (신뢰할 수 있는 필터)
                self.filter_weights[filter_name] = min(1.0, self.filter_weights[filter_name] * 1.1)
                self.logger.info(f"{filter_name} 필터 가중치 증가: {self.filter_weights[filter_name]:.2f}")
    
    def adjust_threshold(self, winning_pass_rate: float):
        """
        당첨번호 통과율에 따라 임계값 조정
        
        Args:
            winning_pass_rate: 당첨번호 통과율 (0-1)
        """
        if winning_pass_rate < self.min_winning_pass_rate:
            # 통과율이 낮으면 임계값 낮춤
            self.pass_threshold *= self.adjustment_factor
            self.pass_threshold = max(50.0, self.pass_threshold)  # 최소 50점
            self.logger.info(f"통과 임계값 하향 조정: {self.pass_threshold:.1f}점")
            
        elif winning_pass_rate > 0.9:
            # 통과율이 너무 높으면 임계값 높임
            self.pass_threshold = min(80.0, self.pass_threshold * 1.05)
            self.logger.info(f"통과 임계값 상향 조정: {self.pass_threshold:.1f}점")
    
    def get_filter_importance_ranking(self) -> List[Tuple[str, float]]:
        """
        필터 중요도 순위 반환
        
        Returns:
            [(필터명, 가중치)] 리스트 (가중치 내림차순)
        """
        return sorted(self.filter_weights.items(), key=lambda x: x[1], reverse=True)
    
    def get_problem_filters(self, threshold: float = 0.4) -> List[str]:
        """
        문제가 있는 필터 목록 반환
        
        Args:
            threshold: 문제 필터 판단 기준 (기본 0.4)
            
        Returns:
            가중치가 threshold 미만인 필터 목록
        """
        return [name for name, weight in self.filter_weights.items() 
                if weight < threshold]
    
    # FilterManager 호환성을 위한 메서드들
    def apply_filters(self, round_num: int, mode: str = 'full', force: bool = False):
        """
        FilterManager의 apply_filters 메서드 래핑
        내부 filter_manager에 위임
        """
        return self.filter_manager.apply_filters(round_num, mode, force)
    
    @property
    def filters(self):
        """FilterManager의 filters 속성 접근"""
        return self.filter_manager.filters
    
    def update_threshold(self, threshold: float):
        """임계값 업데이트"""
        if hasattr(self.filter_manager, 'update_threshold'):
            self.filter_manager.update_threshold(threshold)
    
    def get_filtered_combinations(self, round_num: int = None):
        """
        필터링된 조합 가져오기 (Intelligent Fallback 포함)

        Args:
            round_num: 특정 회차 조합 가져오기 (None이면 모든 조합)

        Returns:
            List[str]: 필터링된 조합 리스트
        """
        # Use DatabaseManager singleton for canonical filtered pool access
        if hasattr(self.filter_manager, 'db_manager'):
            from .specialized_databases import FilterDB
            db_manager = self.filter_manager.db_manager
            filter_db = db_manager.combinations_db

            if round_num is not None:
                # Get combinations for specific round
                with filter_db._create_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT combination FROM filtered_combinations WHERE round = ?",
                        (round_num,)
                    )
                    results = cursor.fetchall()

                    # ============================================================
                    # FIX: Intelligent Fallback - Use latest available data
                    # ============================================================
                    if not results:
                        self.logger.warning(f"[폴백] 회차 {round_num}에 필터링된 조합이 없습니다")

                        # Find latest available round
                        cursor.execute(
                            "SELECT MAX(round) FROM filtered_combinations WHERE round < ?",
                            (round_num,)
                        )
                        fallback_round = cursor.fetchone()[0]

                        if fallback_round:
                            self.logger.info(f"  → 회차 {fallback_round} 데이터 사용 (최신 가용 데이터)")
                            cursor.execute(
                                "SELECT combination FROM filtered_combinations WHERE round = ?",
                                (fallback_round,)
                            )
                            results = cursor.fetchall()
                        else:
                            self.logger.error(f"  → 사용 가능한 필터링 데이터가 전혀 없습니다!")
                    # ============================================================

                    return [row[0] for row in results]
            else:
                # Get all combinations
                with filter_db._create_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT DISTINCT combination FROM filtered_combinations")
                    return [row[0] for row in cursor.fetchall()]

        return []
    
    def __getattr__(self, name):
        """
        WeightedFilterSystem에 없는 속성/메서드는 
        내부 filter_manager로 위임
        """
        return getattr(self.filter_manager, name)