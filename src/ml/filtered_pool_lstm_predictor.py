#!/usr/bin/env python3
"""
필터링된 풀 기반 LSTM 예측기
필터링된 LSTM 예측기로 필터링된 조합 풀을 활용한 예측
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any
import json
import os
from .lstm_predictor import LSTMPredictor

class FilteredPoolLSTMPredictor(LSTMPredictor):
    """필터링된 풀 기반 LSTM 예측기"""

    def __init__(self, sequence_length: int = 50, model_path: str = None, filter_manager=None):
        """
        Args:
            sequence_length: 입력 시퀀스 길이
            model_path: 모델 저장 경로
            filter_manager: 필터 관리자 객체
        """
        super().__init__(sequence_length, model_path)
        self.filter_manager = filter_manager
        self.filtered_pool = []
        self.pool_size = 0

        # 필터링된 풀 기반 예측 설정 변수
        self.pool_based_prediction = True
        self.confidence_threshold = 0.7
        self.max_pool_size = 500000  # 최대 필터링된 풀 크기

        logging.info("FilteredPoolLSTMPredictor 초기화 완료")

    def set_filter_manager(self, filter_manager):
        """필터 관리자 설정"""
        self.filter_manager = filter_manager
        logging.info("필터 관리자 설정 완료")

    def update_filtered_pool(self, filtered_combinations: List[Tuple[int, ...]] = None):
        """필터링된 풀을 업데이트"""
        try:
            if filtered_combinations is not None:
                self.filtered_pool = filtered_combinations
            elif self.filter_manager is not None:
                # 필터 관리자로부터 필터링된 풀을 가져오기
                self.filtered_pool = self.filter_manager.get_filtered_combinations()
            else:
                logging.warning("필터 관리자가 설정되지 않았습니다")
                self.filtered_pool = []

            self.pool_size = len(self.filtered_pool)

            if self.pool_size == 0:
                logging.warning("필터링된 풀이 비어있습니다")
                return False

            # 풀 크기가 너무 클 경우 제한
            if self.pool_size > self.max_pool_size:
                self.filtered_pool = self.filtered_pool[:self.max_pool_size]
                self.pool_size = self.max_pool_size
                logging.info(f"필터링된 풀 크기를 {self.max_pool_size}로 제한했습니다")

            logging.info(f"필터링된 풀 업데이트 완료: {self.pool_size:,} 개")
            return True

        except Exception as e:
            logging.error(f"필터링된 풀 업데이트 오류: {e}")
            self.filtered_pool = []
            self.pool_size = 0
            return False

    def predict_from_filtered_pool(self, historical_data: List[List[int]], num_predictions: int = 5) -> List[List[int]]:
        """필터링된 풀에서 LSTM 기반 예측 수행"""
        try:
            if self.pool_size == 0:
                logging.warning("필터링된 풀이 비어있어서 기본 LSTM 예측을 사용")
                return self.predict(historical_data, num_predictions)

            # 기본 LSTM 예측 수행
            base_predictions = self.predict(historical_data, num_predictions)

            if not base_predictions:
                logging.warning("기본 LSTM 예측 실패")
                return []

            # 필터링된 풀에서 가장 유사한 조합 찾기
            filtered_predictions = []

            for prediction in base_predictions:
                # 예측값과 필터링된 풀의 조합 중에서 가장 유사한 것 찾기
                best_match = self._find_best_match_in_pool(prediction)

                if best_match:
                    filtered_predictions.append(list(best_match))
                else:
                    # 매칭되는 것이 없으면 원래 예측 사용
                    filtered_predictions.append(prediction)

            logging.info(f"필터링된 풀 기반 예측 완료: {len(filtered_predictions)}")
            return filtered_predictions

        except Exception as e:
            logging.error(f"필터링된 풀 예측 오류: {e}")
            # 오류 시 기본 LSTM 예측을 사용
            return self.predict(historical_data, num_predictions)

    def _find_best_match_in_pool(self, target_numbers: List[int]) -> Optional[Tuple[int, ...]]:
        """필터링된 풀에서 가장 유사한 조합 찾기"""
        try:
            if not self.filtered_pool:
                return None

            target_set = set(target_numbers)
            best_match = None
            best_score = -1

            # 성능을 위한 샘플링 적용 (풀이 너무 클 때)
            sample_size = min(10000, self.pool_size)
            if self.pool_size > sample_size:
                sample_indices = np.random.choice(self.pool_size, sample_size, replace=False)
                sample_pool = [self.filtered_pool[i] for i in sample_indices]
            else:
                sample_pool = self.filtered_pool

            for combination in sample_pool:
                combination_set = set(combination)

                # 교집합 개수로 기본 점수
                intersection = len(target_set & combination_set)

                # 자카드 유사도 계산
                union = len(target_set | combination_set)
                jaccard_similarity = intersection / union if union > 0 else 0

                # 번호 범위 유사도
                target_range = max(target_numbers) - min(target_numbers)
                combination_range = max(combination) - min(combination)
                range_similarity = 1 - abs(target_range - combination_range) / 45

                # 최종 점수 계산
                score = (intersection * 0.6 + jaccard_similarity * 0.3 + range_similarity * 0.1)

                if score > best_score:
                    best_score = score
                    best_match = combination

            # 최소 신뢰도 임계값 확인
            if best_score >= self.confidence_threshold:
                return best_match
            else:
                return None

        except Exception as e:
            logging.error(f"최적 매칭 조합 찾기 오류: {e}")
            return None

    def get_pool_statistics(self) -> Dict[str, Any]:
        """필터링된 풀 통계 정보 반환"""
        try:
            if not self.filtered_pool:
                return {
                    'pool_size': 0,
                    'status': 'empty',
                    'error': '필터링된 풀이 비어있습니다'
                }

            # 기본 통계
            all_numbers = [num for combination in self.filtered_pool for num in combination]

            stats = {
                'pool_size': self.pool_size,
                'status': 'active',
                'number_distribution': {},
                'range_distribution': {},
                'sum_distribution': {}
            }

            # 번호별 빈도 분석
            unique_numbers, counts = np.unique(all_numbers, return_counts=True)
            stats['number_distribution'] = dict(zip(unique_numbers.tolist(), counts.tolist()))

            # 범위 분석
            ranges = [max(combination) - min(combination) for combination in self.filtered_pool]
            stats['range_distribution'] = {
                'min': min(ranges),
                'max': max(ranges),
                'mean': np.mean(ranges),
                'std': np.std(ranges)
            }

            # 합계 분석
            sums = [sum(combination) for combination in self.filtered_pool]
            stats['sum_distribution'] = {
                'min': min(sums),
                'max': max(sums),
                'mean': np.mean(sums),
                'std': np.std(sums)
            }

            return stats

        except Exception as e:
            logging.error(f"풀 통계 계산 오류: {e}")
            return {
                'pool_size': self.pool_size,
                'status': 'error',
                'error': str(e)
            }

    def save_pool_cache(self, cache_path: str = None):
        """필터링된 풀 캐시 저장"""
        try:
            if cache_path is None:
                cache_path = 'cache/filtered_pool_cache.json'

            os.makedirs(os.path.dirname(cache_path), exist_ok=True)

            cache_data = {
                'filtered_pool': [list(combination) for combination in self.filtered_pool],
                'pool_size': self.pool_size,
                'timestamp': pd.Timestamp.now().isoformat(),
                'model_params': {
                    'sequence_length': self.sequence_length,
                    'confidence_threshold': self.confidence_threshold,
                    'max_pool_size': self.max_pool_size
                }
            }

            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logging.info(f"필터링된 풀 캐시 저장 완료: {cache_path}")
            return True

        except Exception as e:
            logging.error(f"필터링된 풀 캐시 저장 오류: {e}")
            return False

    def load_pool_cache(self, cache_path: str = None) -> bool:
        """필터링된 풀 캐시 로드"""
        try:
            if cache_path is None:
                cache_path = 'cache/filtered_pool_cache.json'

            if not os.path.exists(cache_path):
                logging.info("필터링된 풀 캐시 파일이 존재하지 않습니다")
                return False

            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            self.filtered_pool = [tuple(combination) for combination in cache_data['filtered_pool']]
            self.pool_size = cache_data['pool_size']

            # 저장된 파라미터 업데이트
            if 'model_params' in cache_data:
                params = cache_data['model_params']
                self.confidence_threshold = params.get('confidence_threshold', self.confidence_threshold)
                self.max_pool_size = params.get('max_pool_size', self.max_pool_size)

            logging.info(f"필터링된 풀 캐시 로드 완료: {self.pool_size:,} 개")
            return True

        except Exception as e:
            logging.error(f"필터링된 풀 캐시 로드 오류: {e}")
            return False