#!/usr/bin/env python3
"""
베이지안 추론 기반 로또 번호 예측 시스템
사전 확률과 관측 데이터를 결합하여 사후 확률 계산
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
from collections import defaultdict
from scipy import stats
from scipy.special import comb
try:
    import matplotlib
    matplotlib.use('Agg')  # 헤드리스 서버 호환
    import matplotlib.pyplot as plt
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    plt = None
    sns = None
    MATPLOTLIB_AVAILABLE = False

# numpy가 제대로 import되었는지 확인
if 'np' not in globals():
    import numpy as np

class BayesianFilter:
    """베이지안 추론 기반 로또 번호 필터"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자
        """
        self.db_manager = db_manager
        self.prior_beliefs = {}
        self.likelihood_models = {}
        self.posterior_beliefs = {}
        self.evidence_cache = {}
        
        # 베이지안 모델 파라미터
        self.model_params = {
            'alpha': 1.0,           # 디리클레 사전분포 파라미터
            'beta': 1.0,            # 베타 분포 파라미터
            'update_weight': 0.1,   # 업데이트 가중치
            'min_evidence': 10      # 최소 증거 수
        }
        
        # 추론 대상
        self.inference_targets = {
            'number_frequency': True,      # 번호 출현 빈도
            'pattern_probability': True,   # 패턴 출현 확률
            'correlation_strength': True,  # 번호 간 상관관계
            'temporal_dependency': True    # 시간적 의존성
        }
        
        logging.info("베이지안 필터 초기화 완료")
    
    def initialize_priors(self, historical_data: List[str] = None):
        """사전 확률 초기화
        
        Args:
            historical_data: 과거 당첨번호 데이터
        """
        if historical_data is None and self.db_manager:
            historical_data = self.db_manager.get_all_winning_numbers()
        
        if not historical_data:
            # 무정보 사전분포 (uniform prior)
            self._initialize_uniform_priors()
        else:
            # 데이터 기반 사전분포
            self._initialize_empirical_priors(historical_data)
    
    def _initialize_uniform_priors(self):
        """균등 사전분포 초기화"""
        # 번호 출현 확률 - 디리클레 분포
        self.prior_beliefs['number_frequency'] = {
            'distribution': 'dirichlet',
            'params': np.ones(45) * self.model_params['alpha']
        }
        
        # 패턴 확률 - 베타 분포
        self.prior_beliefs['patterns'] = {
            'odd_even': {
                'distribution': 'beta',
                'params': {i: (self.model_params['alpha'], self.model_params['beta']) 
                          for i in range(7)}  # 0~6개 홀수
            },
            'sum_range': {
                'distribution': 'normal',
                'params': {'mean': 138.3, 'std': 30.8}  # 역사적 평균
            },
            'consecutive': {
                'distribution': 'beta',
                'params': {i: (self.model_params['alpha'], self.model_params['beta']) 
                          for i in range(6)}  # 0~5개 연속
            }
        }
        
        # 상관관계 - 정규분포
        self.prior_beliefs['correlations'] = {
            'distribution': 'normal',
            'params': np.zeros((45, 45))  # 무상관 가정
        }
        
        logging.info("균등 사전분포 초기화 완료")
    
    def _initialize_empirical_priors(self, historical_data: List[str]):
        """경험적 사전분포 초기화
        
        Args:
            historical_data: 과거 당첨번호 데이터
        """
        # 데이터 변환
        numbers_list = []
        for nums_str in historical_data:
            numbers = [int(n) for n in nums_str.split(',')]
            numbers_list.append(numbers)
        
        # 1. 번호 빈도 사전분포
        frequency_counts = np.zeros(45)
        for numbers in numbers_list:
            for num in numbers:
                frequency_counts[num - 1] += 1
        
        # 디리클레 파라미터 (의사 카운트 추가)
        self.prior_beliefs['number_frequency'] = {
            'distribution': 'dirichlet',
            'params': frequency_counts + self.model_params['alpha']
        }
        
        # 2. 패턴 사전분포
        pattern_counts = self._calculate_pattern_statistics(numbers_list)
        self.prior_beliefs['patterns'] = pattern_counts
        
        # 패턴을 개별 키로도 저장 (update_beliefs와의 호환성을 위해)
        if 'odd_even' in pattern_counts:
            for odd_count, params in pattern_counts['odd_even'].items():
                self.prior_beliefs[f'patterns.odd_even.{odd_count}'] = params
        
        if 'consecutive' in pattern_counts:
            for consec_count, params in pattern_counts['consecutive'].items():
                self.prior_beliefs[f'patterns.consecutive.{consec_count}'] = params
        
        # 3. 상관관계 사전분포
        correlation_matrix = self._calculate_correlation_matrix(numbers_list)
        self.prior_beliefs['correlations'] = {
            'distribution': 'normal',
            'params': correlation_matrix,
            'covariance': np.eye(45) * 0.1  # 초기 불확실성
        }
        
        logging.info(f"경험적 사전분포 초기화 완료 (데이터: {len(historical_data)}개)")
    
    def _calculate_pattern_statistics(self, numbers_list: List[List[int]]) -> Dict:
        """패턴 통계 계산
        
        Args:
            numbers_list: 당첨번호 리스트
            
        Returns:
            Dict: 패턴별 통계
        """
        patterns = {
            'odd_even': defaultdict(int),
            'sum_range': [],
            'consecutive': defaultdict(int),
            'sections': defaultdict(int)
        }
        
        for numbers in numbers_list:
            # 홀짝 패턴
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            patterns['odd_even'][odd_count] += 1
            
            # 합계
            patterns['sum_range'].append(sum(numbers))
            
            # 연속 번호
            consecutive = sum(1 for i in range(len(numbers)-1) 
                            if numbers[i+1] - numbers[i] == 1)
            patterns['consecutive'][consecutive] += 1
            
            # 구간 분포
            for num in numbers:
                section = (num - 1) // 9
                patterns['sections'][section] += 1
        
        # 베타 분포 파라미터 계산
        total = len(numbers_list)
        pattern_params = {
            'odd_even': {},
            'consecutive': {},
            'sum_range': {
                'distribution': 'normal',
                'params': {
                    'mean': np.mean(patterns['sum_range']),
                    'std': np.std(patterns['sum_range'])
                }
            }
        }
        
        # 홀짝 베타 파라미터
        for i in range(7):
            successes = patterns['odd_even'].get(i, 0)
            failures = total - successes
            pattern_params['odd_even'][i] = {
                'distribution': 'beta',
                'params': (successes + self.model_params['alpha'], 
                          failures + self.model_params['beta'])
            }
        
        # 연속번호 베타 파라미터
        for i in range(6):
            successes = patterns['consecutive'].get(i, 0)
            failures = total - successes
            pattern_params['consecutive'][i] = {
                'distribution': 'beta',
                'params': (successes + self.model_params['alpha'], 
                          failures + self.model_params['beta'])
            }
        
        return pattern_params
    
    def _calculate_correlation_matrix(self, numbers_list: List[List[int]]) -> 'np.ndarray':
        """번호 간 상관관계 행렬 계산
        
        Args:
            numbers_list: 당첨번호 리스트
            
        Returns:
            np.ndarray: 상관관계 행렬
        """
        # 공출현 행렬
        co_occurrence = np.zeros((45, 45))
        
        for numbers in numbers_list:
            for i, num1 in enumerate(numbers):
                for j, num2 in enumerate(numbers):
                    if i != j:
                        co_occurrence[num1-1][num2-1] += 1
        
        # 정규화
        total_draws = len(numbers_list)
        if total_draws > 0:
            co_occurrence /= total_draws
        
        return co_occurrence
    
    def update_beliefs(self, evidence: Dict[str, Any], prior_key: str) -> Dict[str, Any]:
        """베이지안 업데이트 수행
        
        Args:
            evidence: 새로운 증거
            prior_key: 업데이트할 사전분포 키
            
        Returns:
            Dict[str, Any]: 사후분포
        """
        prior = self.prior_beliefs.get(prior_key, None)
        if prior is None:
            logging.warning(f"사전분포를 찾을 수 없음: {prior_key}")
            return {}
        
        # 분포 타입에 따른 업데이트
        distribution_type = prior.get('distribution')
        
        if distribution_type == 'dirichlet':
            posterior = self._update_dirichlet(prior['params'], evidence)
        elif distribution_type == 'beta':
            posterior = self._update_beta(prior['params'], evidence)
        elif distribution_type == 'normal':
            posterior = self._update_normal(prior['params'], evidence)
        else:
            logging.warning(f"지원하지 않는 분포: {distribution_type}")
            return prior
        
        # 사후분포 저장
        self.posterior_beliefs[prior_key] = posterior
        
        return posterior
    
    def _update_dirichlet(self, prior_params: 'np.ndarray', 
                         evidence: Dict[str, Any]) -> Dict[str, Any]:
        """디리클레 분포 업데이트
        
        Args:
            prior_params: 사전 파라미터
            evidence: 관측 카운트
            
        Returns:
            Dict[str, Any]: 사후분포
        """
        # 증거에서 카운트 추출
        counts = evidence.get('counts', np.zeros(45))
        
        # 사후 파라미터 = 사전 파라미터 + 관측 카운트
        posterior_params = prior_params + counts
        
        return {
            'distribution': 'dirichlet',
            'params': posterior_params,
            'mean': posterior_params / posterior_params.sum()
        }
    
    def _update_beta(self, prior_params: Tuple[float, float], 
                    evidence: Dict[str, Any]) -> Dict[str, Any]:
        """베타 분포 업데이트
        
        Args:
            prior_params: (alpha, beta) 파라미터
            evidence: 성공/실패 카운트
            
        Returns:
            Dict[str, Any]: 사후분포
        """
        successes = evidence.get('successes', 0)
        failures = evidence.get('failures', 0)
        
        # 사후 파라미터
        alpha_post = prior_params[0] + successes
        beta_post = prior_params[1] + failures
        
        return {
            'distribution': 'beta',
            'params': (alpha_post, beta_post),
            'mean': alpha_post / (alpha_post + beta_post),
            'variance': (alpha_post * beta_post) / ((alpha_post + beta_post)**2 * (alpha_post + beta_post + 1))
        }
    
    def _update_normal(self, prior_params: Dict[str, float], 
                      evidence: Dict[str, Any]) -> Dict[str, Any]:
        """정규분포 업데이트
        
        Args:
            prior_params: 평균, 표준편차
            evidence: 새로운 관측값
            
        Returns:
            Dict[str, Any]: 사후분포
        """
        prior_mean = prior_params.get('mean', 0)
        prior_std = prior_params.get('std', 1)
        prior_variance = prior_std ** 2
        
        # 관측값
        observations = evidence.get('observations', [])
        if not observations:
            return {'distribution': 'normal', 'params': prior_params}
        
        obs_mean = np.mean(observations)
        obs_variance = np.var(observations) if len(observations) > 1 else prior_variance
        n_obs = len(observations)
        
        # 사후 파라미터 (정밀도 가중 평균)
        prior_precision = 1 / prior_variance
        obs_precision = n_obs / obs_variance
        
        posterior_precision = prior_precision + obs_precision
        posterior_variance = 1 / posterior_precision
        
        posterior_mean = (prior_precision * prior_mean + obs_precision * obs_mean) / posterior_precision
        posterior_std = np.sqrt(posterior_variance)
        
        return {
            'distribution': 'normal',
            'params': {'mean': posterior_mean, 'std': posterior_std}
        }
    
    def calculate_log_likelihood(self, combination: List[int], 
                               given_evidence: Dict[str, Any]) -> float:
        """조합의 로그 우도 계산
        
        Args:
            combination: 6개 번호 조합
            given_evidence: 주어진 증거
            
        Returns:
            float: 로그 우도값
        """
        log_likelihood = 0.0
        
        # 1. 번호 빈도 우도
        if 'number_frequency' in self.posterior_beliefs:
            freq_dist = self.posterior_beliefs['number_frequency']
            if freq_dist['distribution'] == 'dirichlet':
                # 다항분포 우도
                probs = freq_dist['mean']
                for num in combination:
                    prob = probs[num - 1]
                    if prob > 0:
                        log_likelihood += np.log(prob)
                    else:
                        log_likelihood += np.log(1e-10)  # 매우 작은 값으로 대체
        
        # 2. 패턴 우도
        if 'patterns' in self.posterior_beliefs:
            patterns = self.posterior_beliefs['patterns']
            
            # 홀짝 패턴
            odd_count = sum(1 for n in combination if n % 2 == 1)
            if 'odd_even' in patterns and odd_count in patterns['odd_even']:
                beta_params = patterns['odd_even'][odd_count]['params']
                odd_prob = beta_params[0] / (beta_params[0] + beta_params[1])
                if odd_prob > 0:
                    log_likelihood += np.log(odd_prob)
                else:
                    log_likelihood += np.log(1e-10)
            
            # 합계 범위
            total_sum = sum(combination)
            if 'sum_range' in patterns:
                sum_dist = patterns['sum_range']['params']
                # 로그 확률밀도 사용
                log_sum_likelihood = stats.norm.logpdf(total_sum, 
                                                     sum_dist['mean'], 
                                                     sum_dist['std'])
                log_likelihood += log_sum_likelihood
        
        return log_likelihood
    
    def calculate_likelihood(self, combination: List[int], 
                           given_evidence: Dict[str, Any]) -> float:
        """조합의 우도 계산
        
        Args:
            combination: 6개 번호 조합
            given_evidence: 주어진 증거
            
        Returns:
            float: 우도값
        """
        log_likelihood = self.calculate_log_likelihood(combination, given_evidence)
        
        # 로그 스케일에서 실제 값으로 변환
        # 언더플로우 방지를 위해 안전하게 변환
        try:
            likelihood = np.exp(log_likelihood)
        except Exception as e:
            logging.error(f"베이지안 추론 실패: {e}")
            # 언더플로우 발생 시 매우 작은 값 반환
            likelihood = 1e-300
        
        return likelihood
    
    def predict_next_combination(self, recent_draws: List[str], 
                               n_predictions: int = 10) -> List[Dict[str, Any]]:
        """다음 회차 번호 예측
        
        Args:
            recent_draws: 최근 당첨번호
            n_predictions: 예측 조합 수
            
        Returns:
            List[Dict[str, Any]]: 예측 조합 리스트
        """
        # 최근 데이터로 사후분포 업데이트
        if recent_draws:
            self._update_with_recent_data(recent_draws[-10:])  # 최근 10회
        
        predictions = []
        
        # 사후분포에서 샘플링
        for _ in range(n_predictions * 10):  # 오버샘플링
            combination = self._sample_from_posterior()
            
            # 우도 계산 (로그 스케일)
            log_likelihood = self.calculate_log_likelihood(combination, {})
            
            # 사후 확률 (정규화 상수 무시)
            posterior_prob = np.exp(log_likelihood) if log_likelihood > -700 else 0  # 언더플로우 방지
            
            predictions.append({
                'numbers': combination,
                'likelihood': self.calculate_likelihood(combination, {}),
                'log_likelihood': log_likelihood,
                'posterior_prob': posterior_prob
            })
        
        # 로그 우도 기준으로 정렬 (더 안정적)
        predictions.sort(key=lambda x: x['log_likelihood'], reverse=True)
        top_predictions = predictions[:n_predictions]
        
        # 상대적 점수 계산 (가장 높은 것을 100점으로)
        if top_predictions:
            max_log_likelihood = top_predictions[0]['log_likelihood']
            for pred in top_predictions:
                # 로그 차이를 이용한 상대 점수
                log_diff = pred['log_likelihood'] - max_log_likelihood
                pred['relative_score'] = 100 * np.exp(log_diff) if log_diff > -10 else 0
        
        # 신뢰구간 계산
        for pred in top_predictions:
            pred['confidence_interval'] = self._calculate_confidence_interval(
                pred['numbers']
            )
        
        return top_predictions
    
    def _update_with_recent_data(self, recent_draws: List[str]):
        """최근 데이터로 사후분포 업데이트
        
        Args:
            recent_draws: 최근 당첨번호
        """
        # 번호 카운트
        number_counts = np.zeros(45)
        pattern_evidence = {
            'odd_even': defaultdict(int),
            'consecutive': defaultdict(int),
            'sum_observations': []
        }
        
        for nums_str in recent_draws:
            numbers = [int(n) for n in nums_str.split(',')]
            
            # 번호 빈도
            for num in numbers:
                number_counts[num - 1] += 1
            
            # 패턴
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            pattern_evidence['odd_even'][odd_count] += 1
            
            consecutive = sum(1 for i in range(len(numbers)-1) 
                            if numbers[i+1] - numbers[i] == 1)
            pattern_evidence['consecutive'][consecutive] += 1
            
            pattern_evidence['sum_observations'].append(sum(numbers))
        
        # 번호 빈도 업데이트
        self.update_beliefs(
            {'counts': number_counts},
            'number_frequency'
        )

        # 패턴 사후분포 업데이트 (ml-probabilistic-3)
        # 과거: update_beliefs(..., 'patterns.odd_even.{N}')가 평면 키로만 저장돼,
        #   calculate_log_likelihood/visualize_beliefs가 읽는 중첩 posterior_beliefs['patterns']에는
        #   전혀 반영되지 않아 패턴 우도가 영구 무시됐다(균등 prior에서는 평면 prior 키 부재 경고까지).
        #   -> readers가 직접 읽는 중첩 구조로 사후분포를 구성해 통일한다.
        total_draws = len(recent_draws)
        alpha0 = self.model_params.get('alpha', 1.0)
        beta0 = self.model_params.get('beta', 1.0)
        prior_patterns = self.prior_beliefs.get('patterns', {})
        if not isinstance(prior_patterns, dict):
            prior_patterns = {}

        patterns_posterior = {'odd_even': {}}

        # 홀짝: 베타 켤레 업데이트 (균등 prior alpha/beta + 최근 관측 successes/failures)
        for odd_count, count in pattern_evidence['odd_even'].items():
            successes = count
            failures = total_draws - count
            patterns_posterior['odd_even'][odd_count] = {
                'distribution': 'beta',
                'params': (alpha0 + successes, beta0 + failures)
            }

        # 합계: 최근 관측(>=2)이면 정규분포 파라미터 갱신, 부족하면 prior의 sum_range 보존
        sum_obs = pattern_evidence['sum_observations']
        if len(sum_obs) >= 2:
            patterns_posterior['sum_range'] = {
                'distribution': 'normal',
                'params': {
                    'mean': float(np.mean(sum_obs)),
                    'std': float(np.std(sum_obs)) or 1.0  # 0이면 logpdf 발산 방지
                }
            }
        elif isinstance(prior_patterns.get('sum_range'), dict):
            sr_params = prior_patterns['sum_range'].get('params', {})
            patterns_posterior['sum_range'] = {
                'distribution': 'normal',
                'params': {
                    'mean': sr_params.get('mean', 138.3),
                    'std': sr_params.get('std', 30.8)
                }
            }

        # readers가 기대하는 중첩 키로 저장 (평면 키 'patterns.odd_even.N' 방식 폐기)
        self.posterior_beliefs['patterns'] = patterns_posterior
    
    def _sample_from_posterior(self) -> List[int]:
        """사후분포에서 번호 조합 샘플링
        
        Returns:
            List[int]: 6개 번호 조합
        """
        # 번호 확률 분포
        if 'number_frequency' in self.posterior_beliefs:
            probs = self.posterior_beliefs['number_frequency']['mean']
        else:
            probs = np.ones(45) / 45  # 균등분포
        
        # 가중치 샘플링
        selected = np.random.choice(45, 6, replace=False, p=probs)
        
        return sorted([n + 1 for n in selected])
    
    def _calculate_confidence_interval(self, combination: List[int], 
                                     confidence_level: float = 0.95) -> Dict[str, float]:
        """신뢰구간 계산
        
        Args:
            combination: 번호 조합
            confidence_level: 신뢰수준
            
        Returns:
            Dict[str, float]: 신뢰구간
        """
        # 번호별 불확실성 집계
        uncertainties = []
        
        if 'number_frequency' in self.posterior_beliefs:
            params = self.posterior_beliefs['number_frequency']['params']
            # 디리클레 분산
            total = params.sum()
            for num in combination:
                var = params[num-1] * (total - params[num-1]) / (total**2 * (total + 1))
                uncertainties.append(np.sqrt(var))
        
        if uncertainties:
            mean_uncertainty = np.mean(uncertainties)
            z_score = stats.norm.ppf((1 + confidence_level) / 2)
            
            return {
                'lower': max(0, 1 - z_score * mean_uncertainty),
                'upper': min(1, 1 + z_score * mean_uncertainty)
            }
        
        return {'lower': 0.5, 'upper': 0.5}
    
    def visualize_beliefs(self, save_path: str = 'bayesian_beliefs.png'):
        """신념 시각화
        
        Args:
            save_path: 저장 경로
        """
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # 1. 번호 빈도 분포
        if 'number_frequency' in self.posterior_beliefs:
            ax = axes[0, 0]
            probs = self.posterior_beliefs['number_frequency']['mean']
            ax.bar(range(1, 46), probs)
            ax.set_xlabel('번호')
            ax.set_ylabel('확률')
            ax.set_title('번호별 출현 확률 (사후분포)')
        
        # 2. 홀짝 패턴 분포
        ax = axes[0, 1]
        if 'patterns' in self.posterior_beliefs:
            odd_probs = []
            for i in range(7):
                if i in self.posterior_beliefs['patterns'].get('odd_even', {}):
                    params = self.posterior_beliefs['patterns']['odd_even'][i]['params']
                    prob = params[0] / (params[0] + params[1])
                    odd_probs.append(prob)
                else:
                    odd_probs.append(1/7)
            
            ax.bar(range(7), odd_probs)
            ax.set_xlabel('홀수 개수')
            ax.set_ylabel('확률')
            ax.set_title('홀수 개수 분포 (사후분포)')
        
        # 3. 합계 분포
        ax = axes[1, 0]
        if 'patterns' in self.posterior_beliefs and 'sum_range' in self.posterior_beliefs['patterns']:
            sum_params = self.posterior_beliefs['patterns']['sum_range']['params']
            x = np.linspace(50, 250, 100)
            y = stats.norm.pdf(x, sum_params['mean'], sum_params['std'])
            ax.plot(x, y)
            ax.fill_between(x, y, alpha=0.3)
            ax.set_xlabel('번호 합계')
            ax.set_ylabel('확률 밀도')
            ax.set_title('번호 합계 분포 (사후분포)')
        
        # 4. 불확실성 히트맵
        ax = axes[1, 1]
        if 'number_frequency' in self.posterior_beliefs:
            params = self.posterior_beliefs['number_frequency']['params']
            uncertainties = []
            for i in range(45):
                total = params.sum()
                var = params[i] * (total - params[i]) / (total**2 * (total + 1))
                uncertainties.append(np.sqrt(var))
            
            uncertainty_matrix = np.array(uncertainties).reshape(9, 5)
            sns.heatmap(uncertainty_matrix, ax=ax, cmap='YlOrRd', 
                       xticklabels=range(1, 6), yticklabels=range(1, 10))
            ax.set_title('번호별 불확실성 (표준편차)')
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        logging.info(f"신념 시각화 저장됨: {save_path}")
    
    def save_beliefs(self, filepath: str = 'bayesian_beliefs.json'):
        """신념 상태 저장
        
        Args:
            filepath: 저장 경로
        """
        beliefs = {
            'prior_beliefs': self._serialize_beliefs(self.prior_beliefs),
            'posterior_beliefs': self._serialize_beliefs(self.posterior_beliefs),
            'model_params': self.model_params,
            'inference_targets': self.inference_targets
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(beliefs, f, ensure_ascii=False, indent=2)
        
        logging.info(f"신념 상태 저장됨: {filepath}")
    
    def _serialize_beliefs(self, beliefs: Dict) -> Dict:
        """신념 직렬화 (JSON 저장용)
        
        Args:
            beliefs: 신념 딕셔너리
            
        Returns:
            Dict: 직렬화된 신념
        """
        import numpy as np  # 메서드 내에서 numpy를 다시 import
        serialized = {}
        
        for key, value in beliefs.items():
            try:
                # numpy array인지 체크
                if hasattr(value, 'tolist') and hasattr(value, 'shape'):
                    serialized[key] = value.tolist()
                elif isinstance(value, dict):
                    serialized[key] = self._serialize_beliefs(value)
                else:
                    serialized[key] = value
            except Exception as e:
                # 에러 발생 시 그대로 저장
                serialized[key] = value
        
        return serialized


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
    
    # 베이지안 필터 생성
    bayesian = BayesianFilter(db_manager)
    
    # 사전분포 초기화
    print("사전분포 초기화 중...")
    bayesian.initialize_priors(winning_numbers[:-10])  # 최근 10개 제외
    
    # 최근 데이터로 업데이트
    print("\n최근 데이터로 사후분포 업데이트 중...")
    recent_draws = winning_numbers[-10:]
    
    # 예측 수행
    print("\n베이지안 예측 수행 중...")
    predictions = bayesian.predict_next_combination(recent_draws, n_predictions=5)
    
    print("\n베이지안 예측 결과:")
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        likelihood = pred['likelihood']
        log_likelihood = pred.get('log_likelihood', np.log(likelihood) if likelihood > 0 else -np.inf)
        relative_score = pred.get('relative_score', 0)
        confidence = pred['confidence_interval']
        
        print(f"\n{i}. {numbers}")
        print(f"   상대 점수: {relative_score:.1f}점")
        print(f"   로그 우도: {log_likelihood:.2f}")
        if likelihood > 1e-10:
            print(f"   우도: {likelihood:.2e}")  # 과학적 표기법
        else:
            print(f"   우도: < 1e-10 (매우 작음)")
        print(f"   신뢰구간: [{confidence['lower']:.2%}, {confidence['upper']:.2%}]")
    
    # 신념 시각화
    print("\n신념 상태 시각화 중...")
    bayesian.visualize_beliefs()
    
    # 결과 저장
    bayesian.save_beliefs()
    print("\n결과가 bayesian_beliefs.json에 저장되었습니다.")

if __name__ == "__main__":
    main()