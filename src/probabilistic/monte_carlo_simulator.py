#!/usr/bin/env python3
"""
Monte Carlo 시뮬레이션 기반 로또 번호 예측 시스템
확률적 시뮬레이션을 통한 최적 번호 조합 탐색
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
from collections import defaultdict, Counter
import multiprocessing as mp
from functools import partial
import time

class MonteCarloSimulator:
    """Monte Carlo 시뮬레이션 기반 로또 예측기"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 (과거 당첨번호 조회용)
        """
        self.db_manager = db_manager
        self.historical_data = None
        self.probability_matrix = None
        self.transition_matrix = None
        
        # 시뮬레이션 파라미터 (CPU 코어 수에 따른 동적 조정)
        cpu_count = mp.cpu_count()
        optimal_simulations = min(10000, max(5000, cpu_count * 1000))  # CPU당 1000회, 최소 5000, 최대 10000
        
        self.simulation_params = {
            'n_simulations': optimal_simulations,  # CPU 기반 동적 조정
            'confidence_level': 0.95,
            'convergence_threshold': 0.001,
            'max_iterations': 1000000,
            'adaptive_mode': True,  # 적응형 모드 활성화
            'cpu_cores': cpu_count
        }
        
        logging.info(f"몬테카를로 시뮬레이션: {cpu_count}코어 감지, {optimal_simulations}회 시뮬레이션 설정")
        
        # 확률 모델 파라미터
        self.probability_model = {
            'use_frequency': True,      # 출현 빈도 기반
            'use_patterns': True,       # 패턴 기반
            'use_correlations': True,   # 번호 간 상관관계
            'use_temporal': True        # 시간적 요소
        }
        
        # 결과 캐시
        self.cache = {
            'simulations': {},
            'probabilities': {},
            'best_combinations': []
        }
        
        # config 별칭 (하위 호환성)
        self.config = self.simulation_params
        
        logging.info("Monte Carlo 시뮬레이터 초기화 완료")
    
    def load_historical_data(self, winning_numbers: List[str] = None):
        """과거 당첨번호 데이터 로드 및 분석
        
        Args:
            winning_numbers: 당첨번호 리스트 (없으면 DB에서 로드)
        """
        if winning_numbers is None and self.db_manager:
            winning_numbers = self.db_manager.get_all_winning_numbers()
        
        if not winning_numbers:
            logging.error("과거 당첨번호 데이터가 없습니다.")
            return
        
        self.historical_data = []
        for nums_str in winning_numbers:
            numbers = [int(n) for n in nums_str.split(',')]
            self.historical_data.append(numbers)
        
        # 확률 행렬 계산
        self._calculate_probability_matrix()
        
        # 전이 행렬 계산
        self._calculate_transition_matrix()
        
        logging.debug(f"{len(self.historical_data)}개의 과거 데이터 로드 완료")
    
    def _calculate_probability_matrix(self):
        """번호별 출현 확률 행렬 계산"""
        # 기본 출현 빈도
        frequency = np.zeros(45)
        
        for numbers in self.historical_data:
            for num in numbers:
                frequency[num - 1] += 1
        
        # 정규화
        total_draws = len(self.historical_data) * 6
        base_probability = frequency / total_draws
        
        # 베이지안 스무딩 (극단값 방지)
        alpha = 1.0  # 스무딩 파라미터
        self.probability_matrix = (frequency + alpha) / (total_draws + 45 * alpha)
        
        # 추가 요소 반영
        if self.probability_model['use_patterns']:
            self._adjust_for_patterns()
        
        if self.probability_model['use_temporal']:
            self._adjust_for_temporal()
    
    def _calculate_transition_matrix(self):
        """번호 간 전이 확률 행렬 계산 (마르코프 체인)"""
        self.transition_matrix = np.zeros((45, 45))
        
        for i in range(len(self.historical_data) - 1):
            current = self.historical_data[i]
            next_draw = self.historical_data[i + 1]
            
            # 현재 번호에서 다음 번호로의 전이
            for curr_num in current:
                for next_num in next_draw:
                    self.transition_matrix[curr_num - 1][next_num - 1] += 1
        
        # 행별 정규화
        row_sums = self.transition_matrix.sum(axis=1)
        row_sums[row_sums == 0] = 1  # 0으로 나누기 방지
        self.transition_matrix = self.transition_matrix / row_sums[:, np.newaxis]
    
    def update_parameters(self, params: Dict[str, Any]):
        """시뮬레이션 파라미터 업데이트
        
        Args:
            params: 업데이트할 파라미터 딕셔너리
        """
        # 시뮬레이션 파라미터 업데이트
        for key, value in params.items():
            if key in self.simulation_params:
                self.simulation_params[key] = value
                logging.info(f"시뮬레이션 파라미터 업데이트: {key} = {value}")
            elif key in ['temperature', 'selection_pressure', 'mutation_rate', 'elite_ratio']:
                # 추가 파라미터를 simulation_params에 저장
                self.simulation_params[key] = value
                logging.info(f"새 파라미터 추가: {key} = {value}")
        
        # 캐시 초기화 (파라미터 변경으로 인한 결과 무효화)
        self.cache = {
            'simulations': {},
            'probabilities': {},
            'best_combinations': []
        }
        
        logging.info("Monte Carlo 시뮬레이터 파라미터 업데이트 완료")
    
    def _adjust_for_patterns(self):
        """패턴 기반 확률 조정"""
        # 최근 N회차의 패턴 분석
        recent_rounds = 50
        if len(self.historical_data) < recent_rounds:
            return
        
        recent_data = self.historical_data[-recent_rounds:]
        
        # 홀짝 패턴
        odd_even_pattern = defaultdict(float)
        for numbers in recent_data:
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            odd_even_pattern[odd_count] += 1
        
        # 가장 빈번한 홀짝 패턴
        most_common_odd = max(odd_even_pattern, key=odd_even_pattern.get)
        
        # 홀수 번호 가중치 조정
        for i in range(45):
            if (i + 1) % 2 == 1:  # 홀수
                if most_common_odd >= 3:
                    self.probability_matrix[i] *= 1.1
            else:  # 짝수
                if most_common_odd < 3:
                    self.probability_matrix[i] *= 1.1
        
        # 정규화
        self.probability_matrix /= self.probability_matrix.sum()
    
    def _adjust_for_temporal(self):
        """시간적 요소 기반 확률 조정 (비활성화됨)

        [FIX-05] 도박사의 오류(Gambler's Fallacy) 제거
        - 이전 로직: 오래 나오지 않은 번호 가중치 +20%, 최근 나온 번호 -10%
        - 문제: 각 추첨은 독립 사건이므로, 과거 미출현이 미래 출현 확률을 높이지 않음
        - 수정: 가중치 조정 로직을 비활성화하고 확률 행렬을 균등하게 유지
        """
        # 아래 로직은 도박사의 오류에 해당하여 비활성화
        # 각 로또 추첨은 독립 시행이므로, 출현 간격에 따른 가중치 조정은 통계적으로 무효함
        #
        # last_appearance = {}
        # for round_idx, numbers in enumerate(self.historical_data):
        #     for num in numbers:
        #         last_appearance[num] = round_idx
        # current_round = len(self.historical_data)
        # for num in range(1, 46):
        #     if num in last_appearance:
        #         gap = current_round - last_appearance[num]
        #         if gap > 20:
        #             self.probability_matrix[num - 1] *= 1.2
        #         elif gap < 5:
        #             self.probability_matrix[num - 1] *= 0.9
        # self.probability_matrix /= self.probability_matrix.sum()

        logging.debug("_adjust_for_temporal: 도박사의 오류 방지를 위해 시간 기반 가중치 조정 비활성화됨")
    
    def _generate_weighted_combination(self) -> List[int]:
        """가중치 기반 번호 조합 생성
        
        Returns:
            List[int]: 6개의 번호 조합
        """
        # 현재 확률 분포 사용
        probabilities = self.probability_matrix.copy()
        
        # 상관관계 반영
        if self.probability_model['use_correlations'] and self.transition_matrix is not None:
            # 첫 번호는 기본 확률로 선택
            first_num = np.random.choice(45, p=probabilities) + 1
            selected = [first_num]
            
            # 나머지 번호는 전이 확률 고려
            while len(selected) < 6:
                # 이미 선택된 번호들의 전이 확률 평균
                trans_probs = np.zeros(45)
                for num in selected:
                    trans_probs += self.transition_matrix[num - 1]
                trans_probs /= len(selected)
                
                # 기본 확률과 전이 확률 결합
                combined_probs = 0.7 * probabilities + 0.3 * trans_probs
                
                # 이미 선택된 번호 제외
                for num in selected:
                    combined_probs[num - 1] = 0
                
                # 정규화
                if combined_probs.sum() > 0:
                    combined_probs /= combined_probs.sum()
                else:
                    combined_probs = probabilities.copy()
                    for num in selected:
                        combined_probs[num - 1] = 0
                    combined_probs /= combined_probs.sum()
                
                # 다음 번호 선택
                next_num = np.random.choice(45, p=combined_probs) + 1
                selected.append(next_num)
        else:
            # 단순 가중치 샘플링
            selected = list(np.random.choice(45, 6, replace=False, p=probabilities) + 1)
        
        return sorted(selected)
    
    def _evaluate_combination(self, combination: List[int]) -> float:
        """조합 평가 점수 계산
        
        Args:
            combination: 6개 번호 조합
            
        Returns:
            float: 평가 점수 (높을수록 좋음)
        """
        score = 0.0
        
        # 1. 개별 번호 확률
        for num in combination:
            score += self.probability_matrix[num - 1] * 100
        
        # 2. 패턴 점수
        # 홀짝 균형
        odd_count = sum(1 for n in combination if n % 2 == 1)
        if 2 <= odd_count <= 4:
            score += 10
        
        # 합계 범위
        total_sum = sum(combination)
        if 100 <= total_sum <= 180:
            score += 10
        
        # 연속 번호 페널티
        consecutive = sum(1 for i in range(len(combination)-1) 
                         if combination[i+1] - combination[i] == 1)
        score -= consecutive * 5
        
        # 3. 과거 당첨 유사도
        if self.historical_data:
            max_similarity = 0
            for past_numbers in self.historical_data[-100:]:  # 최근 100회
                similarity = len(set(combination) & set(past_numbers))
                max_similarity = max(max_similarity, similarity)
            
            # 3-4개 일치가 이상적
            if max_similarity == 3 or max_similarity == 4:
                score += 15
            elif max_similarity >= 5:
                score -= 10  # 너무 유사하면 페널티
        
        return score
    
    def simulate_combinations(self, n_simulations: int = None, 
                           enable_early_termination: bool = True) -> List[Tuple[List[int], float]]:
        """Monte Carlo 시뮬레이션 실행 (최적화된 버전)
        
        Args:
            n_simulations: 시뮬레이션 횟수
            enable_early_termination: 조기 종료 활성화
            
        Returns:
            List[Tuple[List[int], float]]: (조합, 점수) 리스트
        """
        if n_simulations is None:
            n_simulations = self.simulation_params['n_simulations']
        
        if self.probability_matrix is None:
            logging.error("확률 행렬이 초기화되지 않았습니다. load_historical_data()를 먼저 실행하세요.")
            return []
        
        logging.info(f"최적화된 Monte Carlo 시뮬레이션 시작 (최대 n={n_simulations:,})")
        start_time = time.time()
        
        # 캐시 확인
        cache_key = f"sim_{n_simulations}_{hash(str(self.probability_matrix.data.tobytes()))}"
        if cache_key in self.cache['simulations']:
            logging.debug("캐시된 시뮬레이션 결과 사용")
            return self.cache['simulations'][cache_key]
        
        # 초기 배치 크기 설정 (작게 시작)
        batch_size = min(500, n_simulations)
        convergence_window = 200
        min_simulations = 1000
        
        all_results = []
        combinations_seen = defaultdict(list)
        convergence_scores = []
        
        current_simulations = 0
        
        while current_simulations < n_simulations:
            # 배치 시뮬레이션 실행
            batch_results = self._simulate_batch_vectorized(batch_size)
            
            # 결과 누적
            for combination, score in batch_results:
                combo_tuple = tuple(combination)
                combinations_seen[combo_tuple].append(score)
            
            current_simulations += batch_size
            
            # 수렴 검사 (최소 시뮬레이션 후)
            if (enable_early_termination and 
                current_simulations >= min_simulations and 
                current_simulations % convergence_window == 0):
                
                # 상위 조합들의 평균 점수 계산
                top_combinations = self._get_top_combinations(combinations_seen, 10)
                avg_score = np.mean([score for _, score in top_combinations])
                convergence_scores.append(avg_score)
                
                # 수렴 검사
                if len(convergence_scores) >= 3:
                    recent_scores = convergence_scores[-3:]
                    score_std = np.std(recent_scores)
                    score_mean = np.mean(recent_scores)
                    
                    # 수렴 조건: 표준편차가 평균의 1% 미만
                    if score_std < score_mean * 0.01:
                        logging.info(f"수렴 달성: {current_simulations:,}회 시뮬레이션 후 조기 종료")
                        break
            
            # 진행 상황 로그
            if current_simulations % 1000 == 0:
                elapsed = time.time() - start_time
                rate = current_simulations / elapsed
                logging.info(f"진행: {current_simulations:,}/{n_simulations:,} ({rate:.0f} sim/s)")
        
        # 최종 결과 생성
        all_results = self._get_top_combinations(combinations_seen, min(1000, len(combinations_seen)))
        
        # 결과 정렬
        all_results.sort(key=lambda x: x[1], reverse=True)
        
        # 상위 결과 캐싱
        self.cache['best_combinations'] = all_results[:100]
        self.cache['simulations'][cache_key] = all_results
        
        elapsed = time.time() - start_time
        logging.info(f"시뮬레이션 완료: {current_simulations:,}회, {elapsed:.1f}초 "
                    f"({current_simulations/elapsed:.0f} sim/s), 최고 점수: {all_results[0][1]:.2f}")
        
        return all_results
    
    def _simulate_batch_vectorized(self, batch_size: int) -> List[Tuple[List[int], float]]:
        """벡터화된 배치 시뮬레이션 실행 (성능 최적화)
        
        Args:
            batch_size: 배치 크기
            
        Returns:
            List[Tuple[List[int], float]]: (조합, 점수) 리스트
        """
        results = []
        
        # 배치 크기만큼 조합 생성 (벡터화)
        combinations = self._generate_batch_combinations(batch_size)
        
        # 배치 점수 계산 (벡터화)
        scores = self._evaluate_batch_combinations(combinations)
        
        # 결과 조합
        for combination, score in zip(combinations, scores):
            results.append((combination, score))
        
        return results
    
    def _generate_batch_combinations(self, batch_size: int) -> List[List[int]]:
        """배치 조합 생성 (벡터화된 버전)
        
        Args:
            batch_size: 생성할 조합 수
            
        Returns:
            List[List[int]]: 조합 리스트
        """
        combinations = []
        probabilities = self.probability_matrix.copy()
        
        # 상관관계를 사용하지 않는 경우 (더 빠름)
        if not self.probability_model['use_correlations']:
            # 행(조합) 단위로 6개 비복원 가중 추출 (ml-probabilistic-4)
            # 주의: np.random.choice(size=(batch_size,6), replace=False, p=...)는
            # batch_size*6개를 45개 모집단에서 '전체' 비복원 추출하므로
            # batch_size>=8(48>45)에서 ValueError가 발생한다(기본 batch=750이라 항상 실패).
            # 각 조합이 '서로 다른 6개 번호'가 되도록 행 단위로 추출해야 한다.
            combinations = [
                sorted((np.random.choice(45, size=6, replace=False, p=probabilities) + 1).tolist())
                for _ in range(batch_size)
            ]
        else:
            # 상관관계 사용하는 경우 (기존 방식)
            for _ in range(batch_size):
                combination = self._generate_weighted_combination()
                combinations.append(combination)
        
        return combinations
    
    def _evaluate_batch_combinations(self, combinations: List[List[int]]) -> List[float]:
        """배치 조합 평가 (벡터화된 버전)
        
        Args:
            combinations: 평가할 조합 리스트
            
        Returns:
            List[float]: 점수 리스트
        """
        # NumPy 배열로 변환
        combo_array = np.array(combinations)
        batch_size = len(combinations)
        
        # 1. 개별 번호 확률 점수 (벡터화)
        prob_scores = np.sum(self.probability_matrix[combo_array - 1], axis=1) * 100
        
        # 2. 패턴 점수들 (벡터화)
        # 홀수 개수
        odd_counts = np.sum(combo_array % 2, axis=1)
        odd_bonus = np.where((odd_counts >= 2) & (odd_counts <= 4), 10, 0)
        
        # 합계 범위
        sums = np.sum(combo_array, axis=1)
        sum_bonus = np.where((sums >= 100) & (sums <= 180), 10, 0)
        
        # 연속 번호 페널티 (벡터화)
        consecutive_counts = np.zeros(batch_size)
        for i in range(batch_size):
            combo = combinations[i]
            consecutive = sum(1 for j in range(len(combo)-1) 
                            if combo[j+1] - combo[j] == 1)
            consecutive_counts[i] = consecutive
        consecutive_penalty = consecutive_counts * 5
        
        # 기본 점수 계산
        scores = prob_scores + odd_bonus + sum_bonus - consecutive_penalty
        
        # 3. 과거 유사도 (최적화된 버전)
        if self.historical_data:
            similarity_bonus = self._calculate_batch_similarity_bonus(combinations)
            scores += similarity_bonus
        
        return scores.tolist()
    
    def _calculate_batch_similarity_bonus(self, combinations: List[List[int]]) -> np.ndarray:
        """배치 과거 유사도 보너스 계산 (최적화된 버전)
        
        Args:
            combinations: 조합 리스트
            
        Returns:
            np.ndarray: 유사도 보너스 배열
        """
        batch_size = len(combinations)
        bonus_scores = np.zeros(batch_size)
        
        # 최근 100회만 사용 (성능 최적화)
        recent_data = self.historical_data[-100:]
        recent_sets = [set(numbers) for numbers in recent_data]
        
        for i, combination in enumerate(combinations):
            combo_set = set(combination)
            max_similarity = 0
            
            for past_set in recent_sets:
                similarity = len(combo_set & past_set)
                max_similarity = max(max_similarity, similarity)
            
            # 3-4개 일치가 이상적
            if max_similarity == 3 or max_similarity == 4:
                bonus_scores[i] = 15
            elif max_similarity >= 5:
                bonus_scores[i] = -10  # 너무 유사하면 페널티
        
        return bonus_scores
    
    def _get_top_combinations(self, combinations_seen: Dict, top_k: int) -> List[Tuple[List[int], float]]:
        """상위 K개 조합 추출 (평균 점수 기준)
        
        Args:
            combinations_seen: {조합_tuple: [점수들]} 딕셔너리
            top_k: 추출할 상위 조합 수
            
        Returns:
            List[Tuple[List[int], float]]: 상위 조합 리스트
        """
        # 각 조합의 평균 점수 계산
        avg_scores = []
        for combo_tuple, scores in combinations_seen.items():
            avg_score = np.mean(scores)
            avg_scores.append((list(combo_tuple), avg_score))
        
        # 점수순 정렬 후 상위 K개 반환
        avg_scores.sort(key=lambda x: x[1], reverse=True)
        return avg_scores[:top_k]
    
    def _simulate_chunk(self, process_id: int, chunk_size: int) -> List[Tuple[List[int], float]]:
        """단일 프로세스에서 시뮬레이션 청크 실행 (레거시 지원)"""
        np.random.seed(process_id + int(time.time()))  # 프로세스별 다른 시드
        
        # 벡터화된 배치 시뮬레이션 사용
        return self._simulate_batch_vectorized(chunk_size)
    
    def get_best_combinations(self, n_combinations: int = 10, 
                            min_confidence: float = 0.7) -> List[Dict[str, Any]]:
        """최적 번호 조합 추출
        
        Args:
            n_combinations: 반환할 조합 수
            min_confidence: 최소 신뢰도
            
        Returns:
            List[Dict[str, Any]]: 최적 조합 리스트
        """
        if not self.cache['best_combinations']:
            # 시뮬레이션 실행
            self.simulate_combinations()
        
        best_combinations = []
        
        for combination, score in self.cache['best_combinations'][:n_combinations]:
            # 신뢰도 계산
            confidence = self._calculate_confidence(combination, score)
            
            if confidence >= min_confidence:
                # 상세 분석
                analysis = self._analyze_combination(combination)
                
                best_combinations.append({
                    'numbers': combination,
                    'score': float(score),
                    'confidence': float(confidence),
                    'analysis': analysis
                })
        
        return best_combinations
    
    def _calculate_confidence(self, combination: List[int], score: float) -> float:
        """조합의 '상대 점수' 계산 (이 배치 내 순위 정규화 - 당첨확률 아님).

        [2026-06-14 honesty] 반환값은 score를 이 배치(best_combinations) 내에서 min-max 정규화 후
        부스트/클램프한 '상대 순위 점수'다. 따라서 최고점 조합은 정의상 항상 ~1.0(100%)이 된다.
        이는 '당첨 확률'이 아니라 '이 배치 내 상대 우위'이며, 최종예측에선 ml_beta 다양성 보조신호로만 쓰인다.
        (표시 라벨이 '신뢰도'로 보여 확률로 오해될 수 있어 의미를 여기 명시.)

        Args:
            combination: 번호 조합
            score: 평가 점수

        Returns:
            float: 상대 점수 (0-1, 배치 내 순위 기반 - 당첨확률 아님)
        """
        # 점수 기반 신뢰도 (동적 최대값 사용)
        all_scores = [s for _, s in self.cache['best_combinations']]
        max_score = max(all_scores) if all_scores else 100.0
        min_score = min(all_scores) if all_scores else 0.0
        
        # 정규화된 점수 (0-1 범위)
        if max_score > min_score:
            score_confidence = (score - min_score) / (max_score - min_score)
        else:
            score_confidence = 0.5
        
        # 패턴 기반 신뢰도
        pattern_score = self._calculate_pattern_score(combination)
        
        # 종합 신뢰도 (더 현실적인 가중치)
        # 점수 50%, 패턴 30%, 기본 20%
        base_confidence = 0.5 * score_confidence + 0.3 * pattern_score + 0.2 * 0.5

        # 신뢰도 보정: 상위 예측에 대해 더 높은 신뢰도 부여
        # 최소 30%, 최대 100% (1.0) 제한
        enhanced_confidence = base_confidence * 1.15  # 15% 부스트 (더 보수적)

        # 100%를 넘지 않도록 제한
        return max(0.3, min(1.0, enhanced_confidence))
    
    def _calculate_pattern_score(self, combination: List[int]) -> float:
        """패턴 기반 점수 계산
        
        Args:
            combination: 번호 조합
            
        Returns:
            float: 패턴 점수 (0-1)
        """
        score = 0.0
        
        # 홀짝 균형 (3:3이 이상적)
        odd_count = sum(1 for n in combination if n % 2 == 1)
        odd_balance = 1.0 - abs(odd_count - 3) / 3.0
        score += odd_balance * 0.3
        
        # 번호 합계 (이상적인 범위: 100-170)
        total_sum = sum(combination)
        if 100 <= total_sum <= 170:
            sum_score = 1.0
        elif 70 <= total_sum <= 210:
            sum_score = 0.7
        else:
            sum_score = 0.4
        score += sum_score * 0.3
        
        # 연속 번호 패널티 (연속 번호가 적을수록 좋음)
        consecutive = sum(1 for i in range(len(combination)-1) 
                         if combination[i+1] - combination[i] == 1)
        consecutive_score = 1.0 - (consecutive / 5.0)
        score += consecutive_score * 0.2
        
        # 번호 분산 (적절한 분산이 좋음)
        std_dev = np.std(combination)
        if 10 <= std_dev <= 15:
            spread_score = 1.0
        elif 8 <= std_dev <= 17:
            spread_score = 0.7
        else:
            spread_score = 0.4
        score += spread_score * 0.2
        
        return min(1.0, score)
    
    def _analyze_combination(self, combination: List[int]) -> Dict[str, Any]:
        """조합 상세 분석
        
        Args:
            combination: 번호 조합
            
        Returns:
            Dict[str, Any]: 분석 결과
        """
        analysis = {
            'sum': sum(combination),
            'average': np.mean(combination),
            'std': np.std(combination),
            'odd_count': sum(1 for n in combination if n % 2 == 1),
            'even_count': sum(1 for n in combination if n % 2 == 0),
            'consecutive_pairs': sum(1 for i in range(len(combination)-1) 
                                   if combination[i+1] - combination[i] == 1),
            'max_gap': max(combination[i+1] - combination[i] 
                          for i in range(len(combination)-1)),
            'sections': {}
        }
        
        # 구간별 분포
        for i in range(5):
            section_count = sum(1 for n in combination 
                              if i * 9 + 1 <= n <= (i + 1) * 9)
            analysis['sections'][f'section_{i+1}'] = section_count
        
        # 과거 유사도
        if self.historical_data:
            similarities = []
            for past_numbers in self.historical_data[-50:]:
                similarity = len(set(combination) & set(past_numbers))
                similarities.append(similarity)
            
            analysis['avg_historical_similarity'] = np.mean(similarities)
            analysis['max_historical_similarity'] = max(similarities)
        
        return analysis
    
    def performance_benchmark(self, test_sizes: List[int] = None) -> Dict[str, Any]:
        """성능 벤치마크 테스트
        
        Args:
            test_sizes: 테스트할 시뮬레이션 크기들
            
        Returns:
            Dict[str, Any]: 벤치마크 결과
        """
        if test_sizes is None:
            test_sizes = [500, 1000, 2000, 5000]
        
        logging.info("성능 벤치마크 시작...")
        results = []
        
        for size in test_sizes:
            # 캐시 초기화
            self.cache['simulations'].clear()
            
            start_time = time.time()
            
            # 조기 종료 비활성화하여 정확한 측정
            simulation_results = self.simulate_combinations(size, enable_early_termination=False)
            
            elapsed = time.time() - start_time
            rate = size / elapsed if elapsed > 0 else 0
            
            results.append({
                'size': size,
                'elapsed': elapsed,
                'rate': rate,
                'top_score': simulation_results[0][1] if simulation_results else 0
            })
            
            logging.info(f"크기 {size:,}: {elapsed:.2f}초, {rate:.0f} sim/s")
        
        # 조기 종료 효과 테스트
        logging.info("조기 종료 효과 테스트...")
        start_time = time.time()
        early_results = self.simulate_combinations(5000, enable_early_termination=True)
        early_elapsed = time.time() - start_time
        
        return {
            'benchmark_results': results,
            'early_termination_test': {
                'elapsed': early_elapsed,
                'actual_simulations': len([r for r in early_results if r]),
                'improvement': f"{((results[-1]['elapsed'] - early_elapsed) / results[-1]['elapsed'] * 100):.1f}%"
            }
        }
    
    def clear_cache(self):
        """캐시 초기화"""
        self.cache = {
            'simulations': {},
            'probabilities': {},
            'best_combinations': []
        }
        logging.debug("Monte Carlo 시뮬레이터 캐시 초기화됨")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회
        
        Returns:
            Dict[str, Any]: 캐시 통계
        """
        return {
            'simulation_cache_size': len(self.cache['simulations']),
            'probability_cache_size': len(self.cache['probabilities']),
            'best_combinations_cached': len(self.cache['best_combinations']),
            'memory_usage_mb': self._estimate_cache_memory_usage()
        }
    
    def _estimate_cache_memory_usage(self) -> float:
        """캐시 메모리 사용량 추정
        
        Returns:
            float: 추정 메모리 사용량 (MB)
        """
        try:
            import sys
            
            total_size = 0
            
            # 시뮬레이션 캐시
            for key, value in self.cache['simulations'].items():
                total_size += sys.getsizeof(key) + sys.getsizeof(value)
            
            # 확률 캐시
            for key, value in self.cache['probabilities'].items():
                total_size += sys.getsizeof(key) + sys.getsizeof(value)
            
            # 최고 조합 캐시
            total_size += sys.getsizeof(self.cache['best_combinations'])

            return total_size / 1024 / 1024  # MB 변환
        except Exception as e:
            logging.error(f"몬테카를로 시뮬레이션 실패: {e}")
            return 0.0
    
    def convergence_test(self, target_combinations: int = 5, 
                        max_iterations: int = None) -> Dict[str, Any]:
        """수렴 테스트 - 안정적인 결과를 위한 최소 시뮬레이션 횟수 찾기
        
        Args:
            target_combinations: 추적할 상위 조합 수
            max_iterations: 최대 반복 횟수
            
        Returns:
            Dict[str, Any]: 수렴 테스트 결과
        """
        if max_iterations is None:
            max_iterations = self.simulation_params['max_iterations']
        
        logging.info("수렴 테스트 시작...")
        
        convergence_history = []
        current_best = []
        iterations = 1000
        converged = False
        
        while iterations <= max_iterations and not converged:
            # 시뮬레이션 실행
            results = self.simulate_combinations(iterations)
            
            # 상위 조합 추출
            new_best = [combo for combo, _ in results[:target_combinations]]
            
            # 이전 결과와 비교
            if current_best:
                similarity = len([c for c in new_best if c in current_best]) / target_combinations
                convergence_history.append({
                    'iterations': iterations,
                    'similarity': similarity
                })
                
                # 수렴 확인
                if similarity >= 1 - self.simulation_params['convergence_threshold']:
                    converged = True
                    logging.info(f"수렴 달성: {iterations:,}회 반복")
            
            current_best = new_best
            iterations = min(iterations * 2, max_iterations)
        
        return {
            'converged': converged,
            'required_iterations': iterations // 2 if converged else max_iterations,
            'convergence_history': convergence_history,
            'final_combinations': current_best
        }
    
    def save_results(self, filepath: str = 'monte_carlo_results.json'):
        """시뮬레이션 결과 저장
        
        Args:
            filepath: 저장할 파일 경로
        """
        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'simulation_params': self.simulation_params,
            'probability_model': self.probability_model,
            'best_combinations': self.get_best_combinations(20),
            'probability_matrix': self.probability_matrix.tolist() if self.probability_matrix is not None else None
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logging.info(f"결과 저장됨: {filepath}")


def main():
    """최적화된 테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    from src.core.db_manager import DatabaseManager
    
    # 데이터베이스에서 당첨번호 로드
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    
    if len(winning_numbers) < 50:
        print(f"데이터 부족: {len(winning_numbers)}개 (최소 50개 필요)")
        return
    
    # Monte Carlo 시뮬레이터 생성
    simulator = MonteCarloSimulator(db_manager)
    
    # 과거 데이터 로드
    simulator.load_historical_data(winning_numbers)
    
    print("="*60)
    print("[START] 최적화된 Monte Carlo 시뮬레이터 성능 테스트")
    print("="*60)
    
    # 성능 벤치마크
    print("\n[STAT] 성능 벤치마크 실행 중...")
    benchmark = simulator.performance_benchmark([1000, 2000, 5000])
    
    print("\n벤치마크 결과:")
    for result in benchmark['benchmark_results']:
        print(f"  • {result['size']:,}회 시뮬레이션: "
              f"{result['elapsed']:.2f}초 ({result['rate']:.0f} sim/s)")
    
    early_test = benchmark['early_termination_test']
    print(f"\n[FAST] 조기 종료 효과: {early_test['improvement']} 단축 "
          f"({early_test['elapsed']:.2f}초)")
    
    # 캐시 통계
    cache_stats = simulator.get_cache_stats()
    print(f"\n[SAVE] 캐시 통계: {cache_stats['simulation_cache_size']}개 캐시됨, "
          f"메모리 사용량: {cache_stats['memory_usage_mb']:.1f}MB")
    
    # 최적화된 시뮬레이션 실행 (조기 종료 활성화)
    print(f"\n[TARGET] 최적화된 시뮬레이션 실행 (최대 5,000회, 조기 종료 활성화)...")
    start_time = time.time()
    simulator.simulate_combinations(5000, enable_early_termination=True)
    elapsed = time.time() - start_time
    
    print(f"실행 시간: {elapsed:.2f}초")
    
    # 최적 조합 추출
    best_combinations = simulator.get_best_combinations(10, min_confidence=0.6)
    
    print("\n[BEST] 최적 번호 조합 (신뢰도 순):")
    for i, combo in enumerate(best_combinations, 1):
        numbers = combo['numbers']
        score = combo['score']
        confidence = combo['confidence']
        analysis = combo['analysis']
        
        print(f"\n{i:2d}. {numbers}")
        print(f"    점수: {score:6.2f} | 신뢰도: {confidence:5.1%} | "
              f"합계: {analysis['sum']:3d} | 홀수: {analysis['odd_count']}개")
        print(f"    연속쌍: {analysis['consecutive_pairs']}개 | "
              f"최대간격: {analysis['max_gap']:2d}")
    
    # 성능 개선 효과 요약
    print("\n" + "="*60)
    print("[UP] 성능 최적화 효과 요약")
    print("="*60)
    
    expected_old_time = 16.4  # 기존 시간
    improvement_percent = ((expected_old_time - elapsed) / expected_old_time) * 100
    
    print(f"• 기존 예상 시간: {expected_old_time:.1f}초")
    print(f"• 최적화 후 시간: {elapsed:.1f}초")
    print(f"• 성능 개선: {improvement_percent:.1f}% 단축")
    print(f"• 처리 속도: {5000/elapsed:.0f} 시뮬레이션/초")
    
    # 최적화 기법 설명
    print(f"\n[FIX] 적용된 최적화 기법:")
    print(f"  [O] 조기 종료 (수렴 감지)")
    print(f"  [O] 벡터화된 배치 처리")
    print(f"  [O] 결과 캐싱")
    print(f"  [O] 메모리 효율적 계산")
    print(f"  [O] 병렬 처리 오버헤드 제거")
    
    # 결과 저장
    simulator.save_results('optimized_monte_carlo_results.json')
    print(f"\n[SAVE] 결과가 optimized_monte_carlo_results.json에 저장되었습니다.")
    
    return {
        'elapsed_time': elapsed,
        'improvement_percent': improvement_percent,
        'simulations_per_second': 5000/elapsed,
        'best_combinations': best_combinations[:5]
    }

if __name__ == "__main__":
    main()