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

    def __init__(self, sequence_length: int = 15, model_path: str = None, filter_manager=None):
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
        pool = []
        for combo in filtered_combinations:
            if isinstance(combo, str):
                # "1,2,3,4,5,6" 형식 문자열 파싱
                try:
                    nums = tuple(sorted(int(n.strip()) for n in combo.split(',')))
                    pool.append(nums)
                except (ValueError, AttributeError):
                    continue
            else:
                try:
                    pool.append(tuple(sorted(int(n) for n in combo)))
                except (ValueError, TypeError):
                    continue
        self.filtered_pool = pool
        self.pool_size = len(self.filtered_pool)

        # combination_to_idx, idx_to_combination 딕셔너리 생성
        unique_combos = list(dict.fromkeys(self.filtered_pool))  # 순서 유지 중복 제거
        self.combination_to_idx = {combo: idx for idx, combo in enumerate(unique_combos)}
        self.idx_to_combination = {idx: combo for idx, combo in enumerate(unique_combos)}

        logging.info(f"FilteredPoolLSTMPredictor 풀 설정: {self.pool_size}개 조합")

    def train_with_filtered_pool(self, historical_data: List[List[int]],
                                 filtered_pool: Optional[List[List[int]]] = None,
                                 epochs: int = 30, batch_size: int = 32,
                                 validation_split: float = 0.2, **kwargs):
        """필터링된 풀을 설정하고 부모 LSTM(45차원)을 학습한다.

        예측 경로(predict_from_filtered_pool)는 부모 predict_next_numbers(45차원 sigmoid 모델)를
        사용하고 그 결과를 풀에 매칭한다. 따라서 학습도 부모의 45차원 파이프라인으로 해야 한다.
        주의: 자식 prepare_training_data의 y는 ml-probabilistic-5에서 부모와 동일한 45차원으로 통일됐으나,
              입력 형식이 다르다(부모 train은 List[str], 자식은 List[List[int]]). 부모 train이 List[str]을
              넘기므로 학습 동안에는 부모 prepare_training_data(List[str]->45차원)를 일시 사용한다.

        Args:
            historical_data: 과거 당첨조합 (List[List[int]] 또는 'a,b,..' 문자열 리스트)
            filtered_pool: 필터 통과 풀 (제공 시 설정, 예측 매칭에 사용)
            epochs/batch_size/validation_split: 부모 train 인자
        Returns:
            학습 history (TensorFlow 미사용/데이터 부족 시 None)
        """
        if filtered_pool:
            self.set_filtered_pool(filtered_pool)

        # 부모가 기대하는 List[str] 형식으로 정규화
        historical_str = [
            nums if isinstance(nums, str) else ','.join(map(str, nums))
            for nums in historical_data
        ]

        # 학습 동안 부모의 45차원 prepare_training_data를 사용하도록 자식 오버라이드 일시 우회
        had_instance_attr = 'prepare_training_data' in self.__dict__
        self.prepare_training_data = lambda wn: LSTMPredictor.prepare_training_data(self, wn)
        try:
            return super().train(
                historical_str, epochs=epochs,
                batch_size=batch_size, validation_split=validation_split
            )
        finally:
            # 인스턴스 속성 제거 -> 다시 클래스 메서드(자식 오버라이드)로 복원
            if not had_instance_attr:
                del self.prepare_training_data

    def prepare_training_data(self, historical_combinations: List[List[int]]) -> Tuple[np.ndarray, np.ndarray]:
        """학습 데이터 준비 (시퀀스 기반, 45차원 멀티라벨)

        부모 LSTM(45-sigmoid)과 동일하게 X=(이전 sequence_length개 조합의 45차원 이진벡터 시퀀스),
        y=(다음 조합의 45차원 이진 멀티라벨)로 구성한다. 풀 제약은 예측 단계
        (_find_best_match_in_pool)에서 적용하므로 학습 y는 풀-인덱스가 아닌 실제 다음 조합을 쓴다.
        (ml-probabilistic-5: 과거 풀-인덱스 y는 45차원 출력 모델과 불일치해 학습이 무의미했음)
        """
        if self.pool_size == 0:
            raise ValueError("필터링된 풀이 설정되지 않았습니다.")

        X_list = []
        y_list = []

        for i in range(self.sequence_length, len(historical_combinations)):
            # 시퀀스 구성: 이전 sequence_length 개 조합을 각각 45차원 이진 벡터로
            seq = historical_combinations[i - self.sequence_length:i]
            seq_features = []
            for combo in seq:
                vec = np.zeros(45)
                for num in combo:
                    if 1 <= num <= 45:
                        vec[num - 1] = 1.0
                seq_features.append(vec)
            X_list.append(seq_features)

            # 다음 조합을 45차원 이진 멀티라벨 y로 (부모 모델 출력차원과 일치)
            target = np.zeros(45)
            for num in historical_combinations[i]:
                if 1 <= num <= 45:
                    target[num - 1] = 1.0
            y_list.append(target)

        if not X_list:
            return np.array([]), np.array([])

        return np.array(X_list), np.array(y_list)

    def _find_similar_combination(self, combo: List[int]) -> int:
        """풀에서 가장 유사한 조합(번호 교집합 최대)의 인덱스 반환 (numpy 벡터화).

        과거 순수 파이썬 이중 루프(O(pool))를 풀 이진행렬과 타깃 벡터의 행렬곱으로 대체.
        동점 시 가장 작은 인덱스를 반환(np.argmax 규약 = 기존 strict-greater 루프와 동일).
        """
        n_pool = len(self.idx_to_combination)
        if n_pool == 0:
            return 0

        # 풀 이진행렬 (pool_size x 45): 각 조합의 번호 위치를 1로
        pool_matrix = np.zeros((n_pool, 45), dtype=np.float32)
        for idx in range(n_pool):
            for num in self.idx_to_combination[idx]:
                if 1 <= num <= 45:
                    pool_matrix[idx, num - 1] = 1.0

        # 타깃 벡터 (45,)
        target = np.zeros(45, dtype=np.float32)
        for num in combo:
            if 1 <= num <= 45:
                target[num - 1] = 1.0

        # 교집합 크기 = 행렬곱, 최대 인덱스 반환
        intersections = pool_matrix @ target
        return int(np.argmax(intersections))

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
            # 기본 LSTM 예측 수행 (predict_next_numbers: List[str] 형식으로 변환)
            historical_str = [','.join(map(str, nums)) for nums in historical_data]
            base_predictions = self.predict_next_numbers(historical_str, num_predictions)

            if not base_predictions:
                logging.warning("기본 LSTM 예측 실패 - 랜덤 폴백")
                return self._random_predictions_from_pool(
                    filtered_combinations or list(self.filtered_pool),
                    num_predictions
                )

            # 필터링된 풀에서 가장 유사한 조합 찾기
            result = []
            for prediction in base_predictions:
                target = prediction['numbers'] if isinstance(prediction, dict) else prediction
                best_match = self._find_best_match_in_pool(target)
                numbers = list(best_match) if best_match else list(target)
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