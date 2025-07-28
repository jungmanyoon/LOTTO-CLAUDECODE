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
        
        # 시뮬레이션 파라미터
        self.simulation_params = {
            'n_simulations': 10000,
            'confidence_level': 0.95,
            'convergence_threshold': 0.001,
            'max_iterations': 1000000
        }
        
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
        
        logging.info(f"{len(self.historical_data)}개의 과거 데이터 로드 완료")
    
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
        """시간적 요소 기반 확률 조정"""
        # 최근 출현 간격 분석
        last_appearance = {}
        
        for round_idx, numbers in enumerate(self.historical_data):
            for num in numbers:
                last_appearance[num] = round_idx
        
        current_round = len(self.historical_data)
        
        # 오래 나오지 않은 번호 가중치 증가
        for num in range(1, 46):
            if num in last_appearance:
                gap = current_round - last_appearance[num]
                if gap > 20:  # 20회 이상 미출현
                    self.probability_matrix[num - 1] *= 1.2
                elif gap < 5:  # 최근 5회 내 출현
                    self.probability_matrix[num - 1] *= 0.9
        
        # 정규화
        self.probability_matrix /= self.probability_matrix.sum()
    
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
    
    def simulate_combinations(self, n_simulations: int = None) -> List[Tuple[List[int], float]]:
        """Monte Carlo 시뮬레이션 실행
        
        Args:
            n_simulations: 시뮬레이션 횟수
            
        Returns:
            List[Tuple[List[int], float]]: (조합, 점수) 리스트
        """
        if n_simulations is None:
            n_simulations = self.simulation_params['n_simulations']
        
        if self.probability_matrix is None:
            logging.error("확률 행렬이 초기화되지 않았습니다. load_historical_data()를 먼저 실행하세요.")
            return []
        
        logging.info(f"Monte Carlo 시뮬레이션 시작 (n={n_simulations:,})")
        
        # 병렬 처리를 위한 프로세스 수
        n_cores = mp.cpu_count()
        chunk_size = n_simulations // n_cores
        
        # 병렬 시뮬레이션
        with mp.Pool(n_cores) as pool:
            # 각 프로세스에서 실행할 함수
            simulate_chunk = partial(self._simulate_chunk, chunk_size=chunk_size)
            
            # 병렬 실행
            results = pool.map(simulate_chunk, range(n_cores))
        
        # 결과 병합
        all_results = []
        for chunk_results in results:
            all_results.extend(chunk_results)
        
        # 점수순 정렬
        all_results.sort(key=lambda x: x[1], reverse=True)
        
        # 상위 결과 캐싱
        self.cache['best_combinations'] = all_results[:100]
        
        logging.info(f"시뮬레이션 완료. 최고 점수: {all_results[0][1]:.2f}")
        
        return all_results
    
    def _simulate_chunk(self, process_id: int, chunk_size: int) -> List[Tuple[List[int], float]]:
        """단일 프로세스에서 시뮬레이션 청크 실행"""
        np.random.seed(process_id + int(time.time()))  # 프로세스별 다른 시드
        
        results = []
        combination_scores = defaultdict(list)
        
        for _ in range(chunk_size):
            combination = self._generate_weighted_combination()
            score = self._evaluate_combination(combination)
            
            # 조합을 튜플로 변환 (해시 가능)
            combo_tuple = tuple(combination)
            combination_scores[combo_tuple].append(score)
        
        # 각 조합의 평균 점수 계산
        for combo_tuple, scores in combination_scores.items():
            avg_score = np.mean(scores)
            results.append((list(combo_tuple), avg_score))
        
        return results
    
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
        """조합의 신뢰도 계산
        
        Args:
            combination: 번호 조합
            score: 평가 점수
            
        Returns:
            float: 신뢰도 (0-1)
        """
        # 점수 기반 신뢰도
        max_possible_score = 100.0  # 이론적 최대 점수
        score_confidence = min(score / max_possible_score, 1.0)
        
        # 확률 기반 신뢰도
        prob_confidence = 1.0
        for num in combination:
            prob_confidence *= self.probability_matrix[num - 1] * 45  # 정규화
        prob_confidence = prob_confidence ** (1/6)  # 기하평균
        
        # 종합 신뢰도
        confidence = 0.7 * score_confidence + 0.3 * prob_confidence
        
        return confidence
    
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
    """테스트 및 시연"""
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
    
    # 수렴 테스트
    print("\n수렴 테스트 실행 중...")
    convergence = simulator.convergence_test(target_combinations=5)
    print(f"수렴 달성: {convergence['converged']}")
    if convergence['converged']:
        print(f"필요한 시뮬레이션 횟수: {convergence['required_iterations']:,}")
    
    # 시뮬레이션 실행
    print(f"\nMonte Carlo 시뮬레이션 실행 중 (n=10,000)...")
    simulator.simulate_combinations(10000)
    
    # 최적 조합 추출
    best_combinations = simulator.get_best_combinations(10, min_confidence=0.6)
    
    print("\n최적 번호 조합 (신뢰도 순):")
    for i, combo in enumerate(best_combinations, 1):
        numbers = combo['numbers']
        score = combo['score']
        confidence = combo['confidence']
        analysis = combo['analysis']
        
        print(f"\n{i}. {numbers}")
        print(f"   점수: {score:.2f}, 신뢰도: {confidence:.2%}")
        print(f"   합계: {analysis['sum']}, 홀수: {analysis['odd_count']}개")
        print(f"   연속쌍: {analysis['consecutive_pairs']}개, 최대간격: {analysis['max_gap']}")
    
    # 결과 저장
    simulator.save_results()
    print("\n결과가 monte_carlo_results.json에 저장되었습니다.")

if __name__ == "__main__":
    main()