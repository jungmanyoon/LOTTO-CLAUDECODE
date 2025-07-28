#!/usr/bin/env python3
"""
프랙탈 패턴 분석기
자기유사성과 카오스 이론을 활용한 로또 번호 패턴 분석
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
from collections import defaultdict
from scipy import signal
from scipy.stats import entropy
import matplotlib.pyplot as plt
import seaborn as sns
try:
    import pywt  # 웨이블릿 변환
    PYWAVELETS_AVAILABLE = True
except ImportError:
    PYWAVELETS_AVAILABLE = False
    logging.warning("PyWavelets not available. Some fractal analysis features will be limited.")

class FractalPatternAnalyzer:
    """프랙탈 패턴 분석기"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자
        """
        self.db_manager = db_manager
        self.time_series_data = None
        self.fractal_dimensions = {}
        self.chaos_metrics = {}
        self.wavelet_features = {}
        
        # 분석 파라미터
        self.analysis_params = {
            'scales': [10, 50, 100, 200],          # 다중 스케일
            'embedding_dim': 3,                     # 임베딩 차원
            'time_delay': 1,                        # 시간 지연
            'wavelet': 'db4',                       # 웨이블릿 종류
            'decomposition_level': 5,               # 분해 레벨
            'lyapunov_steps': 100                   # 리아푸노프 계산 단계
        }
        
        # 패턴 저장소
        self.patterns = {
            'self_similar': [],      # 자기유사 패턴
            'recurring': [],         # 반복 패턴
            'chaotic': [],          # 카오스 패턴
            'periodic': []          # 주기적 패턴
        }
        
        logging.info("프랙탈 패턴 분석기 초기화 완료")
    
    def load_time_series(self, winning_numbers: List[str] = None):
        """시계열 데이터 로드 및 변환
        
        Args:
            winning_numbers: 당첨번호 리스트
        """
        if winning_numbers is None and self.db_manager:
            winning_numbers = self.db_manager.get_all_winning_numbers()
        
        if not winning_numbers:
            logging.error("당첨번호 데이터가 없습니다.")
            return
        
        # 다차원 시계열 구성
        self.time_series_data = {
            'raw_numbers': [],
            'sums': [],
            'means': [],
            'stds': [],
            'ranges': [],
            'odd_counts': [],
            'entropy': []
        }
        
        for nums_str in winning_numbers:
            numbers = [int(n) for n in nums_str.split(',')]
            
            self.time_series_data['raw_numbers'].append(numbers)
            self.time_series_data['sums'].append(sum(numbers))
            self.time_series_data['means'].append(np.mean(numbers))
            self.time_series_data['stds'].append(np.std(numbers))
            self.time_series_data['ranges'].append(max(numbers) - min(numbers))
            self.time_series_data['odd_counts'].append(sum(1 for n in numbers if n % 2 == 1))
            
            # 엔트로피 계산
            hist, _ = np.histogram(numbers, bins=45, range=(1, 46))
            self.time_series_data['entropy'].append(entropy(hist + 1e-10))
        
        logging.info(f"{len(winning_numbers)}개의 시계열 데이터 로드 완료")
    
    def detect_fractal_patterns(self) -> Dict[str, Any]:
        """프랙탈 패턴 탐지
        
        Returns:
            Dict[str, Any]: 탐지된 패턴들
        """
        if self.time_series_data is None:
            logging.error("시계열 데이터가 로드되지 않았습니다.")
            return {}
        
        results = {}
        
        # 1. 자기유사성 분석
        self_similarity = self._analyze_self_similarity()
        results['self_similarity'] = self_similarity
        
        # 2. 프랙탈 차원 계산
        fractal_dims = self._calculate_fractal_dimensions()
        results['fractal_dimensions'] = fractal_dims
        
        # 3. 카오스 분석
        chaos_analysis = self._analyze_chaos()
        results['chaos_metrics'] = chaos_analysis
        
        # 4. 웨이블릿 변환 분석
        wavelet_analysis = self._wavelet_transform_analysis()
        results['wavelet_features'] = wavelet_analysis
        
        # 5. 패턴 추출
        patterns = self._extract_patterns()
        results['patterns'] = patterns
        
        return results
    
    def _analyze_self_similarity(self) -> Dict[str, float]:
        """자기유사성 분석
        
        Returns:
            Dict[str, float]: 스케일별 자기유사성 점수
        """
        similarity_scores = {}
        
        for scale in self.analysis_params['scales']:
            scores = []
            
            for key in ['sums', 'means', 'odd_counts']:
                if key not in self.time_series_data:
                    continue
                
                series = np.array(self.time_series_data[key])
                
                # 스케일별 분할
                if len(series) >= scale * 2:
                    # 상관관계 계산
                    correlations = []
                    for i in range(0, len(series) - scale, scale // 2):
                        segment1 = series[i:i + scale]
                        segment2 = series[i + scale:i + 2*scale]
                        
                        if len(segment2) == scale:
                            corr = np.corrcoef(segment1, segment2)[0, 1]
                            if not np.isnan(corr):
                                correlations.append(abs(corr))
                    
                    if correlations:
                        scores.append(np.mean(correlations))
            
            if scores:
                similarity_scores[f'scale_{scale}'] = np.mean(scores)
        
        return similarity_scores
    
    def _calculate_fractal_dimensions(self) -> Dict[str, float]:
        """프랙탈 차원 계산
        
        Returns:
            Dict[str, float]: 각 시계열의 프랙탈 차원
        """
        dimensions = {}
        
        for key in ['sums', 'means', 'ranges']:
            if key not in self.time_series_data:
                continue
            
            series = np.array(self.time_series_data[key])
            
            # Box-counting 차원
            box_dim = self._box_counting_dimension(series)
            dimensions[f'{key}_box'] = box_dim
            
            # Higuchi 프랙탈 차원
            higuchi_dim = self._higuchi_dimension(series)
            dimensions[f'{key}_higuchi'] = higuchi_dim
        
        self.fractal_dimensions = dimensions
        return dimensions
    
    def _box_counting_dimension(self, series: np.ndarray) -> float:
        """Box-counting 차원 계산
        
        Args:
            series: 시계열 데이터
            
        Returns:
            float: 프랙탈 차원
        """
        if len(series) < 10:
            return 1.0
        
        # 정규화
        series = (series - series.min()) / (series.max() - series.min() + 1e-10)
        
        # 박스 크기
        box_sizes = [2, 4, 8, 16, 32]
        counts = []
        
        for box_size in box_sizes:
            if box_size > len(series) / 4:
                break
            
            # 박스 개수 계산
            n_boxes = 0
            for i in range(0, len(series) - box_size + 1, box_size):
                segment = series[i:i + box_size]
                if segment.max() - segment.min() > 0:
                    n_boxes += 1
            
            if n_boxes > 0:
                counts.append((box_size, n_boxes))
        
        if len(counts) < 2:
            return 1.0
        
        # 로그-로그 회귀
        log_sizes = np.log([c[0] for c in counts])
        log_counts = np.log([c[1] for c in counts])
        
        # 기울기가 프랙탈 차원
        coeffs = np.polyfit(log_sizes, log_counts, 1)
        return abs(coeffs[0])
    
    def _higuchi_dimension(self, series: np.ndarray, kmax: int = 10) -> float:
        """Higuchi 프랙탈 차원 계산
        
        Args:
            series: 시계열 데이터
            kmax: 최대 k값
            
        Returns:
            float: 프랙탈 차원
        """
        N = len(series)
        if N < kmax * 2:
            kmax = N // 2
        
        if kmax < 2:
            return 1.0
        
        L = []
        k_values = range(1, kmax + 1)
        
        for k in k_values:
            Lk = []
            
            for m in range(k):
                Lmk = 0
                for i in range(1, int((N - m) / k)):
                    Lmk += abs(series[m + i * k] - series[m + (i - 1) * k])
                
                if int((N - m) / k) > 1:
                    Lmk = Lmk * (N - 1) / (k * int((N - m) / k))
                    Lk.append(Lmk)
            
            if Lk:
                L.append(np.mean(Lk))
        
        if len(L) < 2:
            return 1.0
        
        # 로그-로그 회귀
        log_k = np.log(list(k_values)[:len(L)])
        log_L = np.log(L)
        
        coeffs = np.polyfit(log_k, log_L, 1)
        return abs(coeffs[0])
    
    def _analyze_chaos(self) -> Dict[str, Any]:
        """카오스 분석
        
        Returns:
            Dict[str, Any]: 카오스 메트릭
        """
        chaos_metrics = {}
        
        for key in ['sums', 'entropy']:
            if key not in self.time_series_data:
                continue
            
            series = np.array(self.time_series_data[key])
            
            # 리아푸노프 지수
            lyapunov = self._calculate_lyapunov_exponent(series)
            chaos_metrics[f'{key}_lyapunov'] = lyapunov
            
            # 상관 차원
            corr_dim = self._correlation_dimension(series)
            chaos_metrics[f'{key}_correlation_dim'] = corr_dim
            
            # 예측 가능성 지표
            predictability = self._predictability_index(series)
            chaos_metrics[f'{key}_predictability'] = predictability
        
        self.chaos_metrics = chaos_metrics
        return chaos_metrics
    
    def _calculate_lyapunov_exponent(self, series: np.ndarray) -> float:
        """리아푸노프 지수 계산
        
        Args:
            series: 시계열 데이터
            
        Returns:
            float: 리아푸노프 지수
        """
        if len(series) < 100:
            return 0.0
        
        # 위상 공간 재구성
        embedding_dim = self.analysis_params['embedding_dim']
        time_delay = self.analysis_params['time_delay']
        
        # 임베딩
        embedded = []
        for i in range(len(series) - (embedding_dim - 1) * time_delay):
            vec = [series[i + j * time_delay] for j in range(embedding_dim)]
            embedded.append(vec)
        
        embedded = np.array(embedded)
        
        # 리아푸노프 지수 추정
        divergences = []
        
        for i in range(len(embedded) - 1):
            # 가장 가까운 이웃 찾기
            distances = np.linalg.norm(embedded - embedded[i], axis=1)
            distances[i] = np.inf  # 자기 자신 제외
            
            nearest_idx = np.argmin(distances)
            initial_distance = distances[nearest_idx]
            
            if initial_distance > 0:
                # 시간 진화 후 거리
                steps = min(self.analysis_params['lyapunov_steps'], 
                          len(embedded) - max(i, nearest_idx) - 1)
                
                if steps > 0:
                    final_distance = np.linalg.norm(
                        embedded[i + steps] - embedded[nearest_idx + steps]
                    )
                    
                    if final_distance > 0:
                        divergence = np.log(final_distance / initial_distance) / steps
                        divergences.append(divergence)
        
        return np.mean(divergences) if divergences else 0.0
    
    def _correlation_dimension(self, series: np.ndarray) -> float:
        """상관 차원 계산
        
        Args:
            series: 시계열 데이터
            
        Returns:
            float: 상관 차원
        """
        if len(series) < 50:
            return 1.0
        
        # 정규화
        series = (series - series.mean()) / (series.std() + 1e-10)
        
        # 임베딩
        embedding_dim = self.analysis_params['embedding_dim']
        embedded = []
        
        for i in range(len(series) - embedding_dim + 1):
            embedded.append(series[i:i + embedding_dim])
        
        embedded = np.array(embedded)
        
        # 거리 계산
        r_values = np.logspace(-2, 0, 10)
        correlations = []
        
        for r in r_values:
            count = 0
            total = 0
            
            for i in range(len(embedded)):
                for j in range(i + 1, len(embedded)):
                    distance = np.linalg.norm(embedded[i] - embedded[j])
                    if distance < r:
                        count += 1
                    total += 1
            
            if total > 0:
                correlations.append(count / total)
        
        # 로그-로그 회귀
        valid_indices = [i for i, c in enumerate(correlations) if c > 0]
        if len(valid_indices) < 2:
            return 1.0
        
        log_r = np.log(r_values[valid_indices])
        log_c = np.log([correlations[i] for i in valid_indices])
        
        coeffs = np.polyfit(log_r, log_c, 1)
        return abs(coeffs[0])
    
    def _predictability_index(self, series: np.ndarray) -> float:
        """예측 가능성 지표 계산
        
        Args:
            series: 시계열 데이터
            
        Returns:
            float: 예측 가능성 (0-1)
        """
        if len(series) < 10:
            return 0.5
        
        # 자기상관 기반 예측 가능성
        autocorr = np.correlate(series, series, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        autocorr = autocorr / autocorr[0]
        
        # 첫 10개 지연의 평균 자기상관
        predictability = np.mean(np.abs(autocorr[1:11]))
        
        return min(1.0, predictability)
    
    def _wavelet_transform_analysis(self) -> Dict[str, Any]:
        """웨이블릿 변환 분석
        
        Returns:
            Dict[str, Any]: 웨이블릿 특징
        """
        wavelet_features = {}
        
        for key in ['sums', 'means']:
            if key not in self.time_series_data:
                continue
            
            series = np.array(self.time_series_data[key])
            
            # 웨이블릿 분해
            try:
                if not PYWAVELETS_AVAILABLE:
                    raise ImportError("PyWavelets not available")
                    
                coeffs = pywt.wavedec(series, self.analysis_params['wavelet'], 
                                    level=self.analysis_params['decomposition_level'])
                
                # 각 레벨의 에너지
                energies = []
                for i, coeff in enumerate(coeffs):
                    energy = np.sum(coeff ** 2)
                    energies.append(energy)
                    wavelet_features[f'{key}_level_{i}_energy'] = energy
                
                # 총 에너지 대비 비율
                total_energy = sum(energies)
                if total_energy > 0:
                    for i, energy in enumerate(energies):
                        wavelet_features[f'{key}_level_{i}_ratio'] = energy / total_energy
                
            except Exception as e:
                logging.warning(f"웨이블릿 변환 오류: {str(e)}")
        
        self.wavelet_features = wavelet_features
        return wavelet_features
    
    def _extract_patterns(self) -> Dict[str, List[Any]]:
        """패턴 추출
        
        Returns:
            Dict[str, List[Any]]: 추출된 패턴들
        """
        patterns = {
            'self_similar': [],
            'recurring': [],
            'chaotic': [],
            'periodic': []
        }
        
        # 자기유사 패턴
        if hasattr(self, '_self_similarity_scores'):
            for scale, score in self._self_similarity_scores.items():
                if score > 0.7:  # 높은 자기유사성
                    patterns['self_similar'].append({
                        'scale': scale,
                        'score': score,
                        'type': 'high_similarity'
                    })
        
        # 카오스 패턴
        if self.chaos_metrics:
            for metric, value in self.chaos_metrics.items():
                if 'lyapunov' in metric and value > 0:
                    patterns['chaotic'].append({
                        'metric': metric,
                        'value': value,
                        'type': 'positive_lyapunov'
                    })
        
        # 주기적 패턴 탐지
        for key in ['sums', 'odd_counts']:
            if key in self.time_series_data:
                series = np.array(self.time_series_data[key])
                periods = self._find_periodicities(series)
                patterns['periodic'].extend(periods)
        
        self.patterns = patterns
        return patterns
    
    def _find_periodicities(self, series: np.ndarray) -> List[Dict[str, Any]]:
        """주기성 탐지
        
        Args:
            series: 시계열 데이터
            
        Returns:
            List[Dict[str, Any]]: 탐지된 주기들
        """
        if len(series) < 20:
            return []
        
        # FFT를 이용한 주기 탐지
        fft = np.fft.fft(series)
        frequencies = np.fft.fftfreq(len(series))
        
        # 파워 스펙트럼
        power = np.abs(fft) ** 2
        
        # 상위 피크 찾기
        peaks, properties = signal.find_peaks(power[:len(power)//2], 
                                            height=np.mean(power) * 2)
        
        periodicities = []
        for peak_idx in peaks[:5]:  # 상위 5개 피크
            if frequencies[peak_idx] > 0:
                period = 1 / frequencies[peak_idx]
                if 2 <= period <= len(series) / 2:
                    periodicities.append({
                        'period': float(period),
                        'strength': float(power[peak_idx]),
                        'frequency': float(frequencies[peak_idx])
                    })
        
        return periodicities
    
    def predict_with_fractals(self, n_predictions: int = 10) -> List[Dict[str, Any]]:
        """프랙탈 패턴 기반 예측
        
        Args:
            n_predictions: 예측 수
            
        Returns:
            List[Dict[str, Any]]: 예측 결과
        """
        if self.time_series_data is None:
            logging.error("시계열 데이터가 로드되지 않았습니다.")
            return []
        
        predictions = []
        
        # 최근 패턴 분석
        recent_patterns = self._analyze_recent_patterns()
        
        for _ in range(n_predictions):
            # 프랙탈 차원 기반 번호 생성
            numbers = self._generate_fractal_numbers(recent_patterns)
            
            # 카오스 조정
            if self.chaos_metrics:
                numbers = self._apply_chaos_adjustment(numbers)
            
            # 예측 신뢰도
            confidence = self._calculate_fractal_confidence(numbers)
            
            predictions.append({
                'numbers': sorted(numbers),
                'confidence': confidence,
                'fractal_dimension': self.fractal_dimensions.get('sums_higuchi', 1.5),
                'chaos_level': self.chaos_metrics.get('sums_lyapunov', 0.0)
            })
        
        # 신뢰도순 정렬
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return predictions
    
    def _analyze_recent_patterns(self) -> Dict[str, Any]:
        """최근 패턴 분석
        
        Returns:
            Dict[str, Any]: 최근 패턴 특성
        """
        recent_window = 20
        recent_patterns = {}
        
        for key in ['sums', 'means', 'odd_counts']:
            if key in self.time_series_data:
                recent_data = self.time_series_data[key][-recent_window:]
                recent_patterns[key] = {
                    'mean': np.mean(recent_data),
                    'std': np.std(recent_data),
                    'trend': np.polyfit(range(len(recent_data)), recent_data, 1)[0]
                }
        
        return recent_patterns
    
    def _generate_fractal_numbers(self, patterns: Dict[str, Any]) -> List[int]:
        """프랙탈 패턴 기반 번호 생성
        
        Args:
            patterns: 패턴 특성
            
        Returns:
            List[int]: 6개 번호
        """
        numbers = []
        
        # 프랙탈 차원에 따른 분포 조정
        if 'sums_higuchi' in self.fractal_dimensions:
            fractal_dim = self.fractal_dimensions['sums_higuchi']
            
            # 프랙탈 차원이 높을수록 더 복잡한 패턴
            if fractal_dim > 1.5:
                # 넓은 분포
                numbers = list(np.random.choice(range(1, 46), 6, replace=False))
            else:
                # 집중된 분포
                center = np.random.randint(10, 36)
                candidates = list(range(max(1, center-15), min(46, center+15)))
                numbers = list(np.random.choice(candidates, 6, replace=False))
        else:
            # 기본 랜덤
            numbers = list(np.random.choice(range(1, 46), 6, replace=False))
        
        return numbers
    
    def _apply_chaos_adjustment(self, numbers: List[int]) -> List[int]:
        """카오스 조정 적용
        
        Args:
            numbers: 초기 번호들
            
        Returns:
            List[int]: 조정된 번호들
        """
        if 'sums_lyapunov' in self.chaos_metrics:
            lyapunov = self.chaos_metrics['sums_lyapunov']
            
            if lyapunov > 0:  # 카오스적
                # 일부 번호를 랜덤하게 변경
                n_change = int(abs(lyapunov) * 6)
                n_change = min(n_change, 3)
                
                for _ in range(n_change):
                    idx = np.random.randint(0, 6)
                    new_num = np.random.randint(1, 46)
                    while new_num in numbers:
                        new_num = np.random.randint(1, 46)
                    numbers[idx] = new_num
        
        return numbers
    
    def _calculate_fractal_confidence(self, numbers: List[int]) -> float:
        """프랙탈 기반 신뢰도 계산
        
        Args:
            numbers: 번호 조합
            
        Returns:
            float: 신뢰도 (0-1)
        """
        confidence = 0.5  # 기본값
        
        # 프랙탈 차원 일치도
        if self.fractal_dimensions:
            # 번호 조합의 프랙탈 차원 계산
            test_series = [sum(numbers[i:i+2]) for i in range(5)]
            test_dim = self._higuchi_dimension(np.array(test_series), kmax=3)
            
            # 기존 차원과 비교
            avg_dim = np.mean(list(self.fractal_dimensions.values()))
            dim_diff = abs(test_dim - avg_dim)
            
            # 차이가 작을수록 높은 신뢰도
            confidence = max(0.3, 1.0 - dim_diff / 2)
        
        # 카오스 레벨 반영
        if self.chaos_metrics:
            avg_chaos = np.mean([v for k, v in self.chaos_metrics.items() 
                               if 'lyapunov' in k])
            if avg_chaos > 0:
                # 카오스가 높으면 신뢰도 감소
                confidence *= (1 - min(0.3, avg_chaos))
        
        return confidence
    
    def visualize_fractal_analysis(self, save_path: str = 'fractal_analysis.png'):
        """프랙탈 분석 시각화
        
        Args:
            save_path: 저장 경로
        """
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # 1. 시계열 플롯
        ax = axes[0, 0]
        if 'sums' in self.time_series_data:
            ax.plot(self.time_series_data['sums'])
            ax.set_title('번호 합계 시계열')
            ax.set_xlabel('회차')
            ax.set_ylabel('합계')
        
        # 2. 프랙탈 차원
        ax = axes[0, 1]
        if self.fractal_dimensions:
            dims = list(self.fractal_dimensions.values())
            labels = list(self.fractal_dimensions.keys())
            ax.bar(range(len(dims)), dims)
            ax.set_xticks(range(len(dims)))
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.set_title('프랙탈 차원')
            ax.set_ylabel('차원')
        
        # 3. 위상 공간
        ax = axes[1, 0]
        if 'sums' in self.time_series_data:
            series = np.array(self.time_series_data['sums'])
            if len(series) > 2:
                ax.scatter(series[:-1], series[1:], alpha=0.5, s=10)
                ax.set_xlabel('x(t)')
                ax.set_ylabel('x(t+1)')
                ax.set_title('위상 공간 (지연 임베딩)')
        
        # 4. 웨이블릿 스펙트로그램
        ax = axes[1, 1]
        if 'sums' in self.time_series_data:
            series = np.array(self.time_series_data['sums'])
            try:
                if not PYWAVELETS_AVAILABLE:
                    raise ImportError("PyWavelets not available")
                    
                coeffs = pywt.wavedec(series, 'db4', level=5)
                # 계수를 2D 배열로 재구성
                max_len = max(len(c) for c in coeffs)
                spec = np.zeros((len(coeffs), max_len))
                for i, c in enumerate(coeffs):
                    spec[i, :len(c)] = np.abs(c)
                
                im = ax.imshow(spec, aspect='auto', cmap='hot')
                ax.set_title('웨이블릿 계수')
                ax.set_xlabel('시간')
                ax.set_ylabel('스케일')
                plt.colorbar(im, ax=ax)
            except:
                pass
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        logging.info(f"프랙탈 분석 시각화 저장됨: {save_path}")
    
    def save_analysis(self, filepath: str = 'fractal_analysis.json'):
        """분석 결과 저장
        
        Args:
            filepath: 저장 경로
        """
        analysis = {
            'fractal_dimensions': self.fractal_dimensions,
            'chaos_metrics': self.chaos_metrics,
            'wavelet_features': self.wavelet_features,
            'patterns': self.patterns,
            'analysis_params': self.analysis_params
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        logging.info(f"프랙탈 분석 결과 저장됨: {filepath}")


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    from src.core.db_manager import DatabaseManager
    
    # 데이터베이스에서 당첨번호 로드
    db_manager = DatabaseManager()
    winning_numbers = db_manager.get_all_winning_numbers()
    
    if len(winning_numbers) < 100:
        print(f"데이터 부족: {len(winning_numbers)}개 (최소 100개 필요)")
        return
    
    # 프랙탈 분석기 생성
    analyzer = FractalPatternAnalyzer(db_manager)
    
    # 시계열 데이터 로드
    print("시계열 데이터 로드 중...")
    analyzer.load_time_series(winning_numbers)
    
    # 프랙탈 패턴 탐지
    print("\n프랙탈 패턴 분석 중...")
    patterns = analyzer.detect_fractal_patterns()
    
    print("\n=== 프랙탈 분석 결과 ===")
    
    # 프랙탈 차원
    print("\n프랙탈 차원:")
    for key, dim in patterns['fractal_dimensions'].items():
        print(f"  {key}: {dim:.3f}")
    
    # 카오스 메트릭
    print("\n카오스 메트릭:")
    for key, value in patterns['chaos_metrics'].items():
        print(f"  {key}: {value:.3f}")
    
    # 탐지된 패턴
    print("\n탐지된 패턴:")
    for pattern_type, pattern_list in patterns['patterns'].items():
        if pattern_list:
            print(f"  {pattern_type}: {len(pattern_list)}개")
    
    # 프랙탈 기반 예측
    print("\n프랙탈 기반 예측 수행 중...")
    predictions = analyzer.predict_with_fractals(5)
    
    print("\n예측 결과:")
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred['confidence']
        fractal_dim = pred['fractal_dimension']
        chaos_level = pred['chaos_level']
        
        print(f"\n{i}. {numbers}")
        print(f"   신뢰도: {confidence:.2%}")
        print(f"   프랙탈 차원: {fractal_dim:.3f}")
        print(f"   카오스 레벨: {chaos_level:.3f}")
    
    # 시각화
    print("\n시각화 생성 중...")
    analyzer.visualize_fractal_analysis()
    
    # 결과 저장
    analyzer.save_analysis()
    print("\n분석 결과가 fractal_analysis.json에 저장되었습니다.")

if __name__ == "__main__":
    main()