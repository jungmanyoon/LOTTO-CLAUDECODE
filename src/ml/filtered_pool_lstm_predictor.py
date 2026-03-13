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

# TENSORFLOW_AVAILABLE을 모듈 레벨에서 가져옴 (패치 가능하도록)
try:
    from .lstm_predictor import TENSORFLOW_AVAILABLE
except ImportError:
    TENSORFLOW_AVAILABLE = False

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

    def set_filtered_pool(self, filtered_combinations: List[List[int]]):
        """필터링된 풀 설정 (FilteredPoolEnsemblePredictor 호환 인터페이스)"""
        self.filtered_pool = [tuple(sorted(combo)) for combo in filtered_combinations]
        self.pool_size = len(self.filtered_pool)

        # combination_to_idx, idx_to_combination 딕셔너리 생성
        unique_combos = list(dict.fromkeys(self.filtered_pool))  # 순서 유지 중복 제거
        self.combination_to_idx = {combo: idx for idx, combo in enumerate(unique_combos)}
        self.idx_to_combination = {idx: combo for idx, combo in enumerate(unique_combos)}

        logging.info(f"FilteredPoolLSTMPredictor 풀 설정: {self.pool_size}개 조합")

    def prepare_training_data(self, historical_combinations: List[List[int]]) -> Tuple[np.ndarray, np.ndarray]:
        """학습 데이터 준비 (시퀀스 기반)"""
        if self.pool_size == 0:
            raise ValueError("필터링된 풀이 설정되지 않았습니다.")

        X_list = []
        y_list = []

        for i in range(self.sequence_length, len(historical_combinations)):
            # 시퀀스 구성: 이전 sequence_length 개 조합의 번호를 평탄화하여 특징으로 사용
            seq = historical_combinations[i - self.sequence_length:i]
            # 각 조합을 45차원 이진 벡터로 변환
            seq_features = []
            for combo in seq:
                vec = np.zeros(45)
                for num in combo:
                    if 1 <= num <= 45:
                        vec[num - 1] = 1.0
                seq_features.append(vec)
            X_list.append(seq_features)

            # 다음 조합의 풀 인덱스를 레이블로
            next_combo = tuple(sorted(historical_combinations[i]))
            if next_combo in self.combination_to_idx:
                y_list.append(self.combination_to_idx[next_combo])
            else:
                y_list.append(self._find_similar_combination(list(next_combo)))

        if not X_list:
            return np.array([]), np.array([])

        return np.array(X_list), np.array(y_list)

    def _find_similar_combination(self, combo: List[int]) -> int:
        """풀에서 가장 유사한 조합의 인덱스 반환"""
        combo_set = set(combo)
        best_idx = 0
        best_score = -1

        for idx, combination in self.idx_to_combination.items():
            intersection = len(combo_set & set(combination))
            if intersection > best_score:
                best_score = intersection
                best_idx = idx

        return best_idx

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

    def predict_from_filtered_pool(self, historical_data: List[List[int]],
                                  filtered_combinations: Optional[List[List[int]]] = None,
                                  num_predictions: int = 5) -> List[Dict[str, Any]]:
        """필터링된 풀에서 LSTM 기반 예측 수행 (dict 반환)"""
        # filtered_combinations가 제공되면 풀 업데이트
        if filtered_combinations is not None:
            self.set_filtered_pool(filtered_combinations)

        # TensorFlow 미사용 또는 풀 비어있을 때 폴백
        if not TENSORFLOW_AVAILABLE or self.pool_size == 0:
            return self._random_predictions_from_pool(
                filtered_combinations or list(self.filtered_pool),
                num_predictions
            )

        try:
            # 기본 LSTM 예측 수행
            base_predictions = self.predict(historical_data, num_predictions)

            if not base_predictions:
                logging.warning("기본 LSTM 예측 실패 - 랜덤 폴백")
                return self._random_predictions_from_pool(
                    filtered_combinations or list(self.filtered_pool),
                    num_predictions
                )

            # 필터링된 풀에서 가장 유사한 조합 찾기
            result = []
            for prediction in base_predictions:
                best_match = self._find_best_match_in_pool(prediction)
                numbers = list(best_match) if best_match else list(prediction)
                result.append({
                    'numbers': sorted(numbers),
                    'confidence': 0.5,
                    'source': 'filtered_pool_lstm'
                })

            logging.info(f"필터링된 풀 기반 예측 완료: {len(result)}")
            return result

        except Exception as e:
            logging.error(f"필터링된 풀 예측 오류: {e}")
            return self._random_predictions_from_pool(
                filtered_combinations or list(self.filtered_pool),
                num_predictions
            )

    def _random_predictions_from_pool(self, filtered_combinations: List[List[int]],
                                      num_predictions: int) -> List[Dict[str, Any]]:
        """풀에서 랜덤 예측 (폴백)"""
        if not filtered_combinations:
            import random
            return [{'numbers': sorted(random.sample(range(1, 46), 6)),
                     'confidence': 0.1, 'source': 'random_fallback'}
                    for _ in range(num_predictions)]

        indices = np.random.choice(
            len(filtered_combinations),
            min(num_predictions, len(filtered_combinations)),
            replace=False
        )
        return [{'numbers': list(filtered_combinations[i]),
                 'confidence': 1.0 / len(filtered_combinations),
                 'source': 'random_from_pool'}
                for i in indices]

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