#!/usr/bin/env python3
"""
ML-Filter 통합 관리자
필터링된 풀과 ML 모델을 연계하여 통합된 예측 시스템 제공
"""
import logging
import numpy as np
from typing import List, Dict, Tuple, Any, Optional
import json
import os
from datetime import datetime
import pickle
from concurrent.futures import ThreadPoolExecutor
import time

from .db_manager import DatabaseManager
from .filter_manager import FilterManager
from .filter_validator import FilterValidator
from ..ml.filtered_pool_lstm_predictor import FilteredPoolLSTMPredictor
from ..ml.filtered_pool_ensemble_predictor import FilteredPoolEnsemblePredictor


class MLFilterIntegrationManager:
    """ML-Filter 통합 관리자"""

    def __init__(self, db_manager: DatabaseManager = None):
        """
        Args:
            db_manager: 데이터베이스 관리자
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.filter_validator = FilterValidator(self.filter_manager, self.db_manager)

        # ML 모델들
        self.filtered_lstm = FilteredPoolLSTMPredictor()
        self.filtered_ensemble = FilteredPoolEnsemblePredictor()

        # 캐시 시스템
        self.filtered_pool_cache = {}
        self.model_cache = {}

        # 설정
        self.config = {
            'cache_ttl': 3600,  # 1시간
            'max_pool_size': 500000,  # 최대 풀 크기
            'min_pool_size': 10000,   # 최소 풀 크기
            'parallel_training': True,
            'model_weights': {
                'filtered_lstm': 0.4,
                'filtered_ensemble': 0.6
            }
        }

        # 성능 통계
        self.performance_stats = {
            'total_predictions': 0,
            'successful_predictions': 0,
            'filter_pass_rate': 0.0,
            'average_pool_size': 0,
            'training_time': 0.0,
            'prediction_time': 0.0
        }

        logging.info("ML-Filter 통합 관리자 초기화 완료")

    def generate_filtered_pool_predictions(self, num_predictions: int = 10,
                                         force_retrain: bool = False) -> Dict[str, Any]:
        """필터링된 풀 기반 통합 예측 생성"""
        logging.info("필터링된 풀 기반 통합 예측 시작...")
        start_time = time.time()

        try:
            # 1. 과거 데이터 준비
            historical_data = self._prepare_historical_data()
            if len(historical_data) < 50:
                raise ValueError(f"학습 데이터 부족: {len(historical_data)}개")

            # 2. 필터링된 풀 생성
            filtered_pool = self._get_current_filtered_pool()
            if len(filtered_pool) < self.config['min_pool_size']:
                raise ValueError(f"필터링된 풀 크기 부족: {len(filtered_pool)}개")

            logging.info(f"필터링된 풀 크기: {len(filtered_pool):,}개")

            # 3. 모델 학습 또는 로드
            models_ready = self._ensure_models_trained(historical_data, filtered_pool, force_retrain)

            if not models_ready:
                logging.warning("모델 준비 실패. 기본 예측 반환")
                return self._generate_fallback_predictions(filtered_pool, num_predictions)

            # 4. 통합 예측 수행
            predictions = self._generate_integrated_predictions(
                historical_data, filtered_pool, num_predictions
            )

            # 5. 예측 검증
            validated_predictions = self._validate_and_rank_predictions(predictions)

            # 6. 성능 통계 업데이트
            self._update_performance_stats(len(filtered_pool), time.time() - start_time)

            result = {
                'predictions': validated_predictions[:num_predictions],
                'metadata': {
                    'filtered_pool_size': len(filtered_pool),
                    'pool_reduction_ratio': len(filtered_pool) / 8145060,
                    'generation_time': time.time() - start_time,
                    'models_used': ['filtered_lstm', 'filtered_ensemble'],
                    'total_candidates': len(predictions)
                },
                'performance_stats': self.performance_stats.copy()
            }

            logging.info(f"통합 예측 완료: {len(validated_predictions)}개 생성 "
                        f"(소요시간: {result['metadata']['generation_time']:.2f}초)")

            return result

        except Exception as e:
            logging.error(f"통합 예측 생성 실패: {e}")
            return self._generate_fallback_predictions([], num_predictions)

    def _prepare_historical_data(self) -> List[List[int]]:
        """과거 데이터 준비"""
        try:
            winning_numbers = self.db_manager.get_all_winning_numbers()
            historical_combinations = []

            for combo_str in winning_numbers:
                numbers = [int(n) for n in combo_str.split(',')]
                historical_combinations.append(numbers)

            logging.debug(f"과거 데이터 준비 완료: {len(historical_combinations)}개")
            return historical_combinations

        except Exception as e:
            logging.error(f"과거 데이터 준비 실패: {e}")
            return []

    def _get_current_filtered_pool(self) -> List[List[int]]:
        """현재 필터링된 풀 가져오기"""
        cache_key = "current_filtered_pool"

        # 캐시 확인
        if cache_key in self.filtered_pool_cache:
            cache_data = self.filtered_pool_cache[cache_key]
            if time.time() - cache_data['timestamp'] < self.config['cache_ttl']:
                logging.debug("캐시된 필터링된 풀 사용")
                return cache_data['pool']

        try:
            logging.info("필터링된 풀 생성 중...")

            # 모든 조합 생성 (배치 처리)
            from itertools import combinations
            all_combinations = list(combinations(range(1, 46), 6))

            # 배치 단위로 필터링
            batch_size = 100000
            filtered_pool = []

            for i in range(0, len(all_combinations), batch_size):
                batch = all_combinations[i:i+batch_size]
                batch_strings = [','.join(map(str, combo)) for combo in batch]

                # 필터 적용
                filtered_batch = self.filter_manager.apply_all_filters(batch_strings)
                filtered_combos = [[int(n) for n in combo.split(',')] for combo in filtered_batch]
                filtered_pool.extend(filtered_combos)

                # 진행 상황 로깅
                progress = (i + batch_size) / len(all_combinations) * 100
                if i % (batch_size * 20) == 0:  # 20배치마다 로깅
                    logging.info(f"필터링 진행: {progress:.1f}% ({len(filtered_pool):,}개 통과)")

                # 최대 크기 제한
                if len(filtered_pool) >= self.config['max_pool_size']:
                    logging.info(f"최대 풀 크기 도달: {len(filtered_pool):,}개")
                    break

            # 캐시에 저장
            self.filtered_pool_cache[cache_key] = {
                'pool': filtered_pool,
                'timestamp': time.time()
            }

            logging.info(f"필터링된 풀 생성 완료: {len(filtered_pool):,}개")
            return filtered_pool

        except Exception as e:
            logging.error(f"필터링된 풀 생성 실패: {e}")
            return []

    def _ensure_models_trained(self, historical_data: List[List[int]],
                              filtered_pool: List[List[int]],
                              force_retrain: bool = False) -> bool:
        """모델이 학습되었는지 확인하고 필요시 학습"""
        try:
            models_ready = True

            # 데이터 해시 생성 (캐시 키용)
            data_hash = self._generate_data_hash(historical_data, len(filtered_pool))

            if force_retrain or not self._check_cached_models(data_hash):
                logging.info("모델 학습 시작...")
                training_start = time.time()

                if self.config['parallel_training']:
                    # 병렬 학습
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        lstm_future = executor.submit(
                            self._train_lstm_model, historical_data, filtered_pool
                        )
                        ensemble_future = executor.submit(
                            self._train_ensemble_model, historical_data, filtered_pool
                        )

                        lstm_success = lstm_future.result()
                        ensemble_success = ensemble_future.result()

                        models_ready = lstm_success or ensemble_success
                else:
                    # 순차 학습
                    lstm_success = self._train_lstm_model(historical_data, filtered_pool)
                    ensemble_success = self._train_ensemble_model(historical_data, filtered_pool)
                    models_ready = lstm_success or ensemble_success

                training_time = time.time() - training_start
                self.performance_stats['training_time'] = training_time

                if models_ready:
                    self._cache_trained_models(data_hash)
                    logging.info(f"모델 학습 완료 (소요시간: {training_time:.2f}초)")
                else:
                    logging.error("모든 모델 학습 실패")

            else:
                logging.info("캐시된 학습 모델 사용")

            return models_ready

        except Exception as e:
            logging.error(f"모델 학습 확인 실패: {e}")
            return False

    def _train_lstm_model(self, historical_data: List[List[int]],
                         filtered_pool: List[List[int]]) -> bool:
        """LSTM 모델 학습"""
        try:
            if len(historical_data) < 30:
                logging.warning("LSTM 학습 데이터 부족")
                return False

            self.filtered_lstm.train_with_filtered_pool(
                historical_data,
                filtered_pool,
                epochs=30,
                batch_size=32,
                validation_split=0.2
            )
            logging.debug("LSTM 모델 학습 완료")
            return True

        except Exception as e:
            logging.error(f"LSTM 모델 학습 실패: {e}")
            return False

    def _train_ensemble_model(self, historical_data: List[List[int]],
                            filtered_pool: List[List[int]]) -> bool:
        """Ensemble 모델 학습"""
        try:
            if len(historical_data) < 25:
                logging.warning("Ensemble 학습 데이터 부족")
                return False

            results = self.filtered_ensemble.train_with_filtered_pool(
                historical_data,
                filtered_pool,
                test_size=0.2
            )
            logging.debug("Ensemble 모델 학습 완료")
            return True

        except Exception as e:
            logging.error(f"Ensemble 모델 학습 실패: {e}")
            return False

    def _generate_integrated_predictions(self, historical_data: List[List[int]],
                                       filtered_pool: List[List[int]],
                                       num_predictions: int) -> List[Dict[str, Any]]:
        """통합 예측 생성"""
        all_predictions = []

        try:
            # LSTM 예측
            if self.filtered_lstm.is_trained:
                lstm_predictions = self.filtered_lstm.predict_from_filtered_pool(
                    historical_data, filtered_pool, num_predictions * 2
                )
                for pred in lstm_predictions:
                    pred['model'] = 'filtered_lstm'
                    pred['weight'] = self.config['model_weights']['filtered_lstm']
                all_predictions.extend(lstm_predictions)

        except Exception as e:
            logging.error(f"LSTM 예측 실패: {e}")

        try:
            # Ensemble 예측
            if self.filtered_ensemble.is_trained:
                ensemble_predictions = self.filtered_ensemble.predict_from_filtered_pool(
                    historical_data, filtered_pool, num_predictions * 2
                )
                for pred in ensemble_predictions:
                    pred['model'] = 'filtered_ensemble'
                    pred['weight'] = self.config['model_weights']['filtered_ensemble']
                all_predictions.extend(ensemble_predictions)

        except Exception as e:
            logging.error(f"Ensemble 예측 실패: {e}")

        # 가중 신뢰도 계산
        for pred in all_predictions:
            original_confidence = pred.get('confidence', 0.0)
            weight = pred.get('weight', 1.0)
            pred['weighted_confidence'] = original_confidence * weight

        # 중복 제거 및 정렬
        unique_predictions = self._remove_duplicate_predictions(all_predictions)
        unique_predictions.sort(key=lambda x: x['weighted_confidence'], reverse=True)

        logging.debug(f"통합 예측 생성: {len(unique_predictions)}개")
        return unique_predictions

    def _remove_duplicate_predictions(self, predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """중복 예측 제거"""
        seen_combos = set()
        unique_predictions = []

        for pred in predictions:
            combo_tuple = tuple(sorted(pred['numbers']))
            if combo_tuple not in seen_combos:
                seen_combos.add(combo_tuple)
                unique_predictions.append(pred)

        return unique_predictions

    def _validate_and_rank_predictions(self, predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """예측 검증 및 순위 결정"""
        validated_predictions = []

        for pred in predictions:
            try:
                numbers = pred['numbers']
                if len(numbers) != 6 or any(n < 1 or n > 45 for n in numbers):
                    continue

                # 필터 검증
                validation_result = self.filter_validator.validate_winning_numbers(1, numbers)
                pred['filter_passed'] = validation_result['passed_all_filters']
                pred['failed_filters'] = validation_result.get('failed_filters', [])

                # 추가 품질 점수 계산
                quality_score = self._calculate_quality_score(numbers)
                pred['quality_score'] = quality_score

                # 최종 점수 (가중 신뢰도 + 품질 점수)
                final_score = pred['weighted_confidence'] * 0.7 + quality_score * 0.3
                pred['final_score'] = final_score

                validated_predictions.append(pred)

            except Exception as e:
                logging.debug(f"예측 검증 실패: {e}")
                continue

        # 최종 점수로 정렬
        validated_predictions.sort(key=lambda x: x['final_score'], reverse=True)

        # 통과율 계산
        total_predictions = len(validated_predictions)
        passed_predictions = sum(1 for pred in validated_predictions if pred['filter_passed'])
        if total_predictions > 0:
            pass_rate = (passed_predictions / total_predictions) * 100
            self.performance_stats['filter_pass_rate'] = pass_rate

        logging.info(f"예측 검증 완료: {total_predictions}개 중 {passed_predictions}개 통과 ({pass_rate:.1f}%)")

        return validated_predictions

    def _calculate_quality_score(self, numbers: List[int]) -> float:
        """조합의 품질 점수 계산"""
        score = 0.0

        try:
            # 기본 통계
            total = sum(numbers)
            avg = total / 6

            # 합계 점수 (105-175 범위가 일반적)
            if 105 <= total <= 175:
                score += 0.2
            elif 90 <= total <= 190:
                score += 0.1

            # 홀짝 균형
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            if 2 <= odd_count <= 4:
                score += 0.2

            # 연속 번호 체크
            consecutive_count = sum(1 for i in range(len(numbers)-1)
                                  if numbers[i+1] - numbers[i] == 1)
            if consecutive_count <= 2:
                score += 0.2

            # 구간 분포
            sections = [0] * 5
            for num in numbers:
                section = min((num - 1) // 9, 4)
                sections[section] += 1

            if all(s <= 3 for s in sections):  # 한 구간에 너무 많이 몰리지 않음
                score += 0.2

            # 간격 분포
            gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
            if all(1 <= gap <= 15 for gap in gaps):
                score += 0.2

        except Exception as e:
            logging.debug(f"품질 점수 계산 실패: {e}")

        return min(score, 1.0)

    def _generate_fallback_predictions(self, filtered_pool: List[List[int]],
                                     num_predictions: int) -> Dict[str, Any]:
        """폴백 예측 생성"""
        logging.warning("폴백 예측 모드 실행")

        predictions = []

        if filtered_pool and len(filtered_pool) >= num_predictions:
            # 필터링된 풀에서 랜덤 선택
            import random
            selected_indices = random.sample(range(len(filtered_pool)), num_predictions)

            for i, idx in enumerate(selected_indices):
                predictions.append({
                    'numbers': filtered_pool[idx],
                    'confidence': 0.1,
                    'weighted_confidence': 0.1,
                    'final_score': 0.1,
                    'model': 'fallback',
                    'filter_passed': True,
                    'quality_score': 0.5,
                    'source': 'random_from_filtered_pool'
                })
        else:
            # 완전 랜덤 생성
            import random
            for i in range(num_predictions):
                numbers = sorted(random.sample(range(1, 46), 6))
                predictions.append({
                    'numbers': numbers,
                    'confidence': 0.05,
                    'weighted_confidence': 0.05,
                    'final_score': 0.05,
                    'model': 'fallback',
                    'filter_passed': False,
                    'quality_score': 0.2,
                    'source': 'random_fallback'
                })

        return {
            'predictions': predictions,
            'metadata': {
                'filtered_pool_size': len(filtered_pool),
                'pool_reduction_ratio': 0.0,
                'generation_time': 0.1,
                'models_used': ['fallback'],
                'total_candidates': len(predictions)
            },
            'performance_stats': self.performance_stats.copy()
        }

    def _generate_data_hash(self, historical_data: List[List[int]], pool_size: int) -> str:
        """데이터 해시 생성"""
        import hashlib
        data_str = f"{len(historical_data)}_{pool_size}_{str(historical_data[-5:])}"
        return hashlib.md5(data_str.encode()).hexdigest()

    def _check_cached_models(self, data_hash: str) -> bool:
        """캐시된 모델 확인"""
        cache_file = f"cache/models/integrated_models_{data_hash}.pkl"
        return os.path.exists(cache_file)

    def _cache_trained_models(self, data_hash: str):
        """학습된 모델 캐시"""
        try:
            os.makedirs("cache/models", exist_ok=True)
            cache_file = f"cache/models/integrated_models_{data_hash}.pkl"

            cache_data = {
                'lstm_trained': self.filtered_lstm.is_trained,
                'ensemble_trained': self.filtered_ensemble.is_trained,
                'timestamp': time.time()
            }

            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)

            logging.debug(f"모델 캐시 저장: {cache_file}")

        except Exception as e:
            logging.error(f"모델 캐시 저장 실패: {e}")

    def _update_performance_stats(self, pool_size: int, generation_time: float):
        """성능 통계 업데이트"""
        self.performance_stats['total_predictions'] += 1
        self.performance_stats['average_pool_size'] = (
            (self.performance_stats['average_pool_size'] * (self.performance_stats['total_predictions'] - 1) + pool_size)
            / self.performance_stats['total_predictions']
        )
        self.performance_stats['prediction_time'] = generation_time

    def get_performance_summary(self) -> Dict[str, Any]:
        """성능 요약 반환"""
        return {
            'performance_stats': self.performance_stats.copy(),
            'cache_status': {
                'filtered_pool_cached': len(self.filtered_pool_cache) > 0,
                'model_cache_size': len(self.model_cache)
            },
            'configuration': self.config.copy()
        }

    def clear_cache(self):
        """캐시 정리"""
        self.filtered_pool_cache.clear()
        self.model_cache.clear()
        logging.info("캐시 정리 완료")


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from src.logger import setup_logging
    setup_logging()

    # ML-Filter 통합 관리자 생성
    integration_manager = MLFilterIntegrationManager()

    print("ML-Filter 통합 예측 시스템 테스트 시작...")

    # 통합 예측 생성
    results = integration_manager.generate_filtered_pool_predictions(num_predictions=5)

    print("\n=== 통합 예측 결과 ===")
    predictions = results.get('predictions', [])
    for i, pred in enumerate(predictions, 1):
        numbers = pred['numbers']
        confidence = pred.get('final_score', 0)
        model = pred.get('model', 'unknown')
        filter_passed = pred.get('filter_passed', False)
        quality = pred.get('quality_score', 0)

        print(f"{i}. {numbers}")
        print(f"   - 모델: {model}")
        print(f"   - 최종 점수: {confidence:.3f}")
        print(f"   - 필터 통과: {'O' if filter_passed else 'X'}")
        print(f"   - 품질 점수: {quality:.3f}")

    print(f"\n=== 메타데이터 ===")
    metadata = results.get('metadata', {})
    print(f"필터링된 풀 크기: {metadata.get('filtered_pool_size', 0):,}개")
    print(f"감소율: {metadata.get('pool_reduction_ratio', 0):.2%}")
    print(f"생성 시간: {metadata.get('generation_time', 0):.2f}초")
    print(f"사용 모델: {metadata.get('models_used', [])}")

    print(f"\n=== 성능 통계 ===")
    performance = integration_manager.get_performance_summary()
    stats = performance['performance_stats']
    print(f"필터 통과율: {stats.get('filter_pass_rate', 0):.1f}%")
    print(f"평균 풀 크기: {stats.get('average_pool_size', 0):,.0f}개")
    print(f"학습 시간: {stats.get('training_time', 0):.2f}초")
    print(f"예측 시간: {stats.get('prediction_time', 0):.2f}초")


if __name__ == "__main__":
    main()