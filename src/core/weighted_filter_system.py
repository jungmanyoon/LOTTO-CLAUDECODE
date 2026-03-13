"""
가중치 기반 필터 시스템
각 필터의 중요도에 따라 가중치를 적용하여 유연한 필터링 수행
"""

import logging
from typing import List, Dict, Tuple, Any
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
            'ml_prediction': 0.8,    # ML 예측
            'ac_value': 0.85,        # AC값 (산술 복잡도) - 무작위성 검증에 중요
            'mean_reversion': 0.7    # Phase 3: Mean Reversion (평균 회귀) 분석
        }

        # Mean Reversion 분석기 (지연 초기화)
        self._mean_reversion_analyzer = None

        # 점수화 모드 설정
        self.use_scoring_mode = True  # True: 점수 기반, False: 이진 필터링
        
        # 통과 임계값 (100점 만점 기준)
        # 1% 임계값 = 99% 통과율을 위해 매우 낮은 점수 설정
        self.pass_threshold = 30.0  # 30점 이상이면 통과 (1% 임계값 반영)
        
        # 동적 조정 파라미터
        self.min_winning_pass_rate = 0.7  # 최소 당첨번호 통과율 70%
        self.adjustment_factor = 0.9      # 조정 계수
        
    def evaluate_combination(self, combination, round_num=None):
        """
        가중치 기반으로 조합 평가

        점수화 모드(use_scoring_mode=True)에서는 각 필터의 score_combination()을
        사용하여 0-100 범위의 세분화된 점수를 산출합니다.
        이진 모드(use_scoring_mode=False)에서는 기존 apply() 기반 0/100 점수를 사용합니다.

        Args:
            combination: 평가할 번호 조합 (List[int] 또는 "1,2,3,4,5,6" 형식)
            round_num: 회차 번호 (선택적)

        Returns:
            Dict: {
                'passed': bool,
                'total_score': float (0-100),
                'quality_tier': str ('excellent'/'good'/'acceptable'/'poor'),
                'filter_results': dict
            }
        """
        # 문자열이면 리스트로 변환, 리스트면 문자열로도 준비
        if isinstance(combination, str):
            combination_list = [int(n) for n in combination.split(',')]
            combination_str = combination
        else:
            combination_list = list(combination)
            combination_str = ','.join(map(str, combination))

        total_score = 0.0
        max_possible_score = 0.0
        filter_results = {}

        for filter_name, filter_obj in self.filter_manager.filters.items():
            if filter_name not in self.filter_weights:
                continue

            weight = self.filter_weights[filter_name]
            max_possible_score += weight * 100

            try:
                if self.use_scoring_mode and hasattr(filter_obj, 'score_combination'):
                    # 점수화 모드: score_combination() 사용 (0-100 연속 점수)
                    score = filter_obj.score_combination(combination_str, round_num)
                    passed = score >= 50.0  # 50점 이상이면 통과로 간주
                else:
                    # 이진 모드: apply() 사용 (0 또는 100)
                    result = filter_obj.apply([combination_str], round_num)
                    passed = len(result) > 0
                    score = 100.0 if passed else 0.0

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

        # Phase 3: Mean Reversion 점수 추가
        try:
            mr_weight = self.filter_weights.get('mean_reversion', 0.7)
            max_possible_score += mr_weight * 100

            if self._mean_reversion_analyzer is None:
                from src.analysis.mean_reversion_analyzer import MeanReversionAnalyzer
                self._mean_reversion_analyzer = MeanReversionAnalyzer(
                    self.filter_manager.db_manager
                )
                self._mean_reversion_analyzer.update_statistics()

            mr_result = self._mean_reversion_analyzer.calculate_combination_score(combination_list)
            mr_score = mr_result.get('score', 50.0)
            mr_weighted = mr_score * mr_weight
            total_score += mr_weighted

            filter_results['mean_reversion'] = {
                'passed': mr_score >= 50,
                'score': mr_score,
                'weight': mr_weight,
                'weighted_score': mr_weighted,
                'details': {
                    'hot_count': mr_result.get('hot_count', 0),
                    'cold_count': mr_result.get('cold_count', 0),
                    'avg_reversion_strength': mr_result.get('avg_reversion_strength', 0)
                }
            }
        except Exception as e:
            self.logger.debug(f"Mean Reversion 분석 스킵: {e}")

        # 정규화된 점수 계산 (0-100 범위)
        normalized_score = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0

        # 품질 등급 결정
        if normalized_score >= 85:
            quality_tier = 'excellent'
        elif normalized_score >= 70:
            quality_tier = 'good'
        elif normalized_score >= self.pass_threshold:
            quality_tier = 'acceptable'
        else:
            quality_tier = 'poor'

        # 통과 여부 결정
        passed = normalized_score >= self.pass_threshold

        return {
            'passed': passed,
            'total_score': normalized_score,
            'quality_tier': quality_tier,
            'filter_results': filter_results
        }

    def rank_combinations(self, combinations: List[str], round_num: int = None,
                          top_n: int = None) -> List[Tuple[str, float, str]]:
        """
        조합들을 점수 기반으로 랭킹

        Args:
            combinations: 랭킹할 조합 리스트
            round_num: 회차 번호
            top_n: 상위 N개만 반환 (None이면 전체)

        Returns:
            List of (combination, score, quality_tier) tuples, 점수 내림차순
        """
        scored_combinations = []

        for combo in combinations:
            try:
                result = self.evaluate_combination(combo, round_num)
                scored_combinations.append((
                    combo,
                    result['total_score'],
                    result['quality_tier']
                ))
            except Exception as e:
                self.logger.warning(f"조합 {combo} 평가 실패: {e}")
                scored_combinations.append((combo, 0.0, 'poor'))

        # 점수 내림차순 정렬
        scored_combinations.sort(key=lambda x: x[1], reverse=True)

        if top_n is not None:
            return scored_combinations[:top_n]

        return scored_combinations

    def filter_by_score_threshold(self, combinations: List[str], round_num: int = None,
                                   min_score: float = None) -> List[str]:
        """
        점수 임계값 이상인 조합만 필터링

        이진 필터링 대신 점수 기반 필터링을 수행합니다.
        위음성(False Negative) 리스크를 줄이기 위해 임계값 미만도
        완전히 제외하지 않고 낮은 우선순위로 처리할 수 있습니다.

        Args:
            combinations: 필터링할 조합 리스트
            round_num: 회차 번호
            min_score: 최소 점수 (None이면 self.pass_threshold 사용)

        Returns:
            임계값 이상 점수를 받은 조합 리스트 (점수 내림차순)
        """
        threshold = min_score if min_score is not None else self.pass_threshold
        ranked = self.rank_combinations(combinations, round_num)

        return [combo for combo, score, _ in ranked if score >= threshold]
    
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