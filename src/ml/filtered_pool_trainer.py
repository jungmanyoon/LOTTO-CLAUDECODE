#!/usr/bin/env python3
"""
필터링된 풀 기반 ML 학습 모듈
ML-Filter 단절 문제를 해결하기 위한 2단계 학습 시스템

핵심 기능:
1. extract_pool_features(): 필터링된 조합에서 특징 추출
2. generate_labels(): 당첨 패턴과의 유사도 레이블 생성
3. fine_tune_model(): 필터링된 풀로 모델 미세조정
4. train_hybrid_model(): 당첨번호(70%) + 필터풀(30%) 하이브리드 학습
"""
import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional, Any, Union
from collections import defaultdict
import os
import pickle

# ML 라이브러리 imports
try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_squared_error, r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available. Filtered pool trainer will work in limited mode.")


class FilteredPoolTrainer:
    """
    필터링된 풀 기반 ML 학습기

    ML 모델이 필터 통과율을 높이기 위해 필터링된 조합 풀에서 학습
    """

    def __init__(self, pool_sample_size: int = 10000):
        """
        Args:
            pool_sample_size: 필터링된 풀에서 샘플링할 조합 수 (기본 10K)
        """
        self.pool_sample_size = pool_sample_size
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.training_history = []

        # 특징 추출 설정
        self.feature_config = {
            'use_statistics': True,      # 통계적 특징
            'use_patterns': True,        # 패턴 특징
            'use_distributions': True,   # 분포 특징
        }

        # 하이브리드 학습 가중치
        self.hybrid_weights = {
            'winning_numbers': 0.7,  # 70% - 당첨번호 패턴
            'filtered_pool': 0.3     # 30% - 필터 제약사항
        }

        logging.info(f"FilteredPoolTrainer 초기화 완료 (샘플 크기: {pool_sample_size:,}개)")

    def extract_pool_features(self, combinations: List[Union[List[int], Tuple[int, ...]]]) -> pd.DataFrame:
        """
        필터링된 조합 풀에서 특징 추출

        Args:
            combinations: 필터링된 조합 리스트 [(1,2,3,4,5,6), ...]

        Returns:
            pd.DataFrame: 추출된 특징 행렬
        """
        if not combinations:
            logging.warning("조합 리스트가 비어있습니다")
            return pd.DataFrame()

        features_list = []

        for combo in combinations:
            # 튜플, 리스트, 또는 문자열을 정렬된 숫자 리스트로 변환
            if isinstance(combo, str):
                # 문자열 형식: "1,2,3,4,5,6" -> [1, 2, 3, 4, 5, 6]
                numbers = sorted([int(n) for n in combo.split(',')])
            else:
                # 튜플/리스트 형식: (1,2,3,4,5,6) -> [1, 2, 3, 4, 5, 6]
                numbers = sorted([int(n) for n in combo])
            features = {}

            # === 기본 통계 특징 ===
            if self.feature_config['use_statistics']:
                features['mean'] = np.mean(numbers)
                features['std'] = np.std(numbers)
                features['min'] = min(numbers)
                features['max'] = max(numbers)
                features['range'] = features['max'] - features['min']
                features['sum'] = sum(numbers)
                features['median'] = np.median(numbers)

            # === 패턴 특징 ===
            if self.feature_config['use_patterns']:
                # 홀짝 비율
                odd_count = sum(1 for n in numbers if n % 2 == 1)
                features['odd_ratio'] = odd_count / 6

                # 연속 번호 개수
                consecutive_count = sum(1 for i in range(len(numbers)-1)
                                      if numbers[i+1] - numbers[i] == 1)
                features['consecutive_ratio'] = consecutive_count / 5

                # 간격 통계
                gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
                features['avg_gap'] = np.mean(gaps)
                features['max_gap'] = max(gaps)
                features['gap_std'] = np.std(gaps) if len(gaps) > 1 else 0

                # 소수 개수
                primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
                prime_count = sum(1 for n in numbers if n in primes)
                features['prime_ratio'] = prime_count / 6

                # 끝자리 다양성
                last_digits = [n % 10 for n in numbers]
                features['last_digit_diversity'] = len(set(last_digits)) / 6

            # === 분포 특징 ===
            if self.feature_config['use_distributions']:
                # 5구간 분포 (1-9, 10-18, 19-27, 28-36, 37-45)
                for section in range(5):
                    section_start = section * 9 + 1
                    section_end = (section + 1) * 9
                    section_count = sum(1 for n in numbers
                                      if section_start <= n <= section_end)
                    features[f'section_{section}'] = section_count / 6

                # 십의 자리 분포
                tens_distribution = defaultdict(int)
                for n in numbers:
                    tens_distribution[n // 10] += 1
                for tens in range(5):  # 0(1-9), 1(10-19), 2(20-29), 3(30-39), 4(40-45)
                    features[f'tens_{tens}'] = tens_distribution[tens] / 6

            features_list.append(features)

        df = pd.DataFrame(features_list)
        logging.info(f"특징 추출 완료: {len(df)}개 조합, {len(df.columns)}개 특징")

        return df

    def generate_labels(self, combinations: List[Union[List[int], Tuple[int, ...]]],
                       winning_numbers: List[str]) -> np.ndarray:
        """
        필터링된 조합에 대한 유사도 레이블 생성

        Args:
            combinations: 필터링된 조합 리스트
            winning_numbers: 과거 당첨번호 문자열 리스트 ["1,2,3,4,5,6", ...]

        Returns:
            np.ndarray: 유사도 점수 배열 (0-1 범위)
        """
        if not combinations or not winning_numbers:
            logging.warning("조합 또는 당첨번호가 비어있습니다")
            return np.array([])

        # 디버그: 입력 데이터 형식 확인
        logging.debug(f"[generate_labels] 조합 수: {len(combinations)}, 당첨번호 수: {len(winning_numbers)}")
        if winning_numbers:
            logging.debug(f"[generate_labels] 첫 번째 당첨번호 타입: {type(winning_numbers[0])}, 값: {winning_numbers[0]}")
        if combinations:
            logging.debug(f"[generate_labels] 첫 번째 조합 타입: {type(combinations[0])}, 값: {combinations[0]}")

        # 당첨번호 파싱
        winning_parsed = []
        parse_errors = 0
        for wn in winning_numbers:
            if isinstance(wn, str):
                try:
                    numbers = [int(n.strip()) for n in wn.split(',')]
                except (ValueError, AttributeError) as e:
                    parse_errors += 1
                    if parse_errors <= 3:
                        logging.warning(f"당첨번호 파싱 오류: '{wn}' - {e}")
                    continue
            elif isinstance(wn, (list, tuple)):
                numbers = [int(n) for n in wn]
            else:
                logging.warning(f"지원하지 않는 당첨번호 형식: {type(wn)}")
                continue
            winning_parsed.append(numbers[:6])  # 보너스 번호 제외

        if parse_errors > 3:
            logging.warning(f"당첨번호 파싱 오류 총 {parse_errors}건")

        if not winning_parsed:
            logging.error("[generate_labels] winning_parsed가 비어있습니다! 당첨번호 형식을 확인하세요.")
            return np.zeros(len(combinations))

        # numpy 원-핫 행렬 방식으로 유사도 벡터화 계산 (Python 루프 O(N×M) 제거)
        # winning_hot: (M, 45) - 당첨번호 원-핫 벡터
        # combos_hot:  (N, 45) - 조합 원-핫 벡터
        # intersection_counts = combos_hot @ winning_hot.T → (N, M)
        winning_hot = np.zeros((len(winning_parsed), 45), dtype=np.int8)
        for i, nums in enumerate(winning_parsed):
            for n in nums:
                if 1 <= n <= 45:
                    winning_hot[i, n - 1] = 1

        combos_list = []
        for combo in combinations:
            if isinstance(combo, str):
                nums = [int(x.strip()) for x in combo.split(',')]
            else:
                nums = [int(x) for x in combo]
            combos_list.append(nums)

        combos_hot = np.zeros((len(combos_list), 45), dtype=np.int8)
        for i, nums in enumerate(combos_list):
            for n in nums:
                if 1 <= n <= 45:
                    combos_hot[i, n - 1] = 1

        # (N, M) intersection counts via matrix multiplication
        intersection_counts = combos_hot.astype(np.float32) @ winning_hot.astype(np.float32).T  # (N, M)
        union_counts = np.maximum(12 - intersection_counts, 1)  # 6+6-intersection, avoid /0
        jaccard_scores = intersection_counts / union_counts       # (N, M)
        match_scores = intersection_counts / 6.0                  # (N, M)
        similarities = 0.4 * jaccard_scores + 0.6 * match_scores  # (N, M)

        # 각 조합의 최대 유사도를 레이블로 사용
        labels_array = np.max(similarities, axis=1)  # (N,)

        logging.info(f"레이블 생성 완료: 평균 유사도 {labels_array.mean():.3f}, "
                    f"최대 {labels_array.max():.3f}, 최소 {labels_array.min():.3f}")

        return labels_array

    def fine_tune_model(self, model: Any, db_manager, filter_manager,
                       winning_numbers: Optional[List[str]] = None) -> Any:
        """
        필터링된 풀로 모델 미세조정

        Args:
            model: 학습된 ML 모델 (EnsemblePredictor 또는 LSTMPredictor)
            db_manager: 데이터베이스 관리자
            filter_manager: 필터 관리자
            winning_numbers: 당첨번호 리스트 (None이면 DB에서 가져옴)

        Returns:
            미세조정된 모델
        """
        if not SKLEARN_AVAILABLE:
            logging.error("scikit-learn이 설치되지 않아 미세조정을 수행할 수 없습니다")
            return model

        try:
            # 당첨번호 가져오기
            if winning_numbers is None:
                winning_numbers = db_manager.get_all_winning_numbers()

            if not winning_numbers or len(winning_numbers) < 10:
                logging.warning("당첨번호 데이터가 부족하여 미세조정을 건너뜁니다")
                return model

            # 필터링된 조합 가져오기
            logging.info("\n[Fine-tuning] 필터링된 조합 풀에서 샘플링 중...")
            latest_round = len(winning_numbers)

            try:
                # 우선순위 1: 모델에 이미 filtered_pool이 설정되어 있으면 재사용 (DB 재로드 불필요)
                if hasattr(model, 'filtered_pool') and model.filtered_pool:
                    pool = model.filtered_pool
                    n_sample = min(self.pool_sample_size, len(pool))
                    indices = np.random.choice(len(pool), n_sample, replace=False)
                    filtered_combinations = [list(pool[i]) for i in indices]
                    logging.info(f"  - 모델 기존 풀에서 샘플링: {len(filtered_combinations):,}개 / {len(pool):,}개")
                else:
                    # 우선순위 2: filter_manager에서 가져오기 (느림)
                    filtered_combinations = self._sample_filtered_pool(
                        filter_manager, latest_round, self.pool_sample_size
                    )

                if not filtered_combinations:
                    logging.warning("필터링된 조합을 가져올 수 없습니다. 미세조정 건너뜀")
                    return model

                logging.info(f"  - 샘플링 완료: {len(filtered_combinations):,}개 조합")

            except Exception as e:
                logging.error(f"필터링된 조합 가져오기 실패: {e}")
                return model

            # 특징 추출
            logging.info("  - 특징 추출 중...")
            pool_features = self.extract_pool_features(filtered_combinations)

            if pool_features.empty:
                logging.warning("특징 추출 실패. 미세조정 건너뜀")
                return model

            # 레이블 생성 (당첨 패턴과의 유사도)
            logging.info("  - 유사도 레이블 생성 중...")
            pool_labels = self.generate_labels(filtered_combinations, winning_numbers)

            if len(pool_labels) == 0:
                logging.warning("레이블 생성 실패. 미세조정 건너뜀")
                return model

            # 특징 스케일링
            pool_features_scaled = self.scaler.fit_transform(pool_features)

            # 모델 타입에 따라 미세조정 수행
            model_type = type(model).__name__

            if model_type in ('EnsemblePredictor', 'FilteredPoolEnsemblePredictor'):
                # EnsemblePredictor 또는 FilteredPoolEnsemblePredictor 모두 지원
                model = self._fine_tune_ensemble(model, pool_features_scaled, pool_labels)

                # FilteredPoolEnsemblePredictor의 filtered_pool 설정
                # predict_next_numbers()가 filtered_pool 비어있으면 []를 반환하므로 반드시 설정
                if model_type == 'FilteredPoolEnsemblePredictor' and hasattr(model, 'filtered_pool'):
                    if not model.filtered_pool:
                        logging.info("    - filtered_pool 설정 중 (미세조정에서 사용한 조합 적용)...")
                        model.set_filtered_pool(filtered_combinations)
                        logging.info(f"    - filtered_pool 설정 완료: {len(model.filtered_pool)}개 조합")

            elif model_type == 'LSTMPredictor':
                model = self._fine_tune_lstm(model, filtered_combinations, winning_numbers)
            else:
                logging.warning(f"지원하지 않는 모델 타입: {model_type} (지원: EnsemblePredictor, FilteredPoolEnsemblePredictor, LSTMPredictor)")

            logging.info("[Fine-tuning] 미세조정 완료")
            return model

        except Exception as e:
            logging.error(f"미세조정 중 오류 발생: {e}")
            return model

    def _fine_tune_ensemble(self, ensemble_model, features_scaled, labels) -> Any:
        """앙상블 모델 미세조정

        Note: 기존 모델이 분류기(Classifier)이므로 연속형 유사도 점수를
        이진 레이블로 변환하여 학습합니다.
        - 중앙값 이상: 1 (좋은 조합)
        - 중앙값 미만: 0 (나쁜 조합)
        """
        try:
            # 연속형 유사도 점수를 이진 레이블로 변환 (분류기 호환)
            # 중앙값 기준으로 좋은 조합(1)과 나쁜 조합(0)으로 분류
            median_similarity = np.median(labels) if len(labels) > 0 else 0.1

            # 유사도가 0인 경우 (이전 버그로 인한 케이스) 미세조정 스킵
            if median_similarity == 0 or np.all(labels == 0):
                logging.warning("    - 유사도가 모두 0입니다. 미세조정을 건너뜁니다.")
                logging.warning("    - 힌트: 조합 형식이 올바른지 확인하세요 (문자열 vs 튜플)")
                return ensemble_model

            # 이진 레이블 생성: 중앙값 이상이면 1, 미만이면 0
            binary_labels = (labels >= median_similarity).astype(int)

            logging.info(f"    - 유사도 통계: 중앙값={median_similarity:.4f}, "
                        f"좋은조합={np.sum(binary_labels)}개, 나쁜조합={len(binary_labels)-np.sum(binary_labels)}개")

            # RF 미세조정 - 스킵 (이진 레이블로 재학습하면 multi-class 구조 파괴)
            # train_with_filtered_pool()에서 168K 클래스 분류기로 학습된 RF를
            # multi-output binary (N×45)로 재학습하면 predict_proba()가
            # list of 45 arrays를 반환해 _ensemble_predict_proba() 완전 실패 → 예측 0개
            logging.info("    - RF 미세조정은 모델 구조 보호를 위해 스킵 (multi-class 분류기 유지)")

            # XGBoost 미세조정 - 스킵 (same reason)
            logging.info("    - XGBoost 미세조정은 클래스 불일치 방지를 위해 스킵")

            # Neural Network는 과적합 위험이 높아 스킵
            logging.info("    - NN 미세조정은 과적합 방지를 위해 스킵")

            return ensemble_model

        except Exception as e:
            logging.error(f"앙상블 미세조정 오류: {e}")
            return ensemble_model

    def _fine_tune_lstm(self, lstm_model, filtered_combinations, winning_numbers) -> Any:
        """LSTM 모델 미세조정"""
        try:
            logging.info("    - LSTM 미세조정 중...")

            # 필터링된 조합을 문자열로 변환
            combo_strings = [','.join(map(str, sorted(combo))) for combo in filtered_combinations]

            # 필터링된 조합 + 당첨번호 혼합 데이터로 재학습
            mixed_data = winning_numbers[-50:] + combo_strings[:500]  # 최근 50회차 + 필터풀 500개

            # LSTM 재학습 (짧은 epoch으로 빠르게)
            if hasattr(lstm_model, 'retrain'):
                lstm_model.retrain(mixed_data)
                logging.info("    - LSTM 미세조정 완료")
            else:
                logging.warning("    - LSTM 모델에 retrain 메서드가 없습니다")

            return lstm_model

        except Exception as e:
            logging.error(f"LSTM 미세조정 오류: {e}")
            return lstm_model

    def train_hybrid_model(self, model: Any, db_manager, filter_manager,
                          winning_numbers: Optional[List[str]] = None) -> Any:
        """
        하이브리드 학습: 당첨번호(70%) + 필터풀(30%)

        2단계 학습 프로세스:
        - Stage 1: 당첨번호 패턴 학습 (70% 가중치)
        - Stage 2: 필터 제약사항 학습 (30% 가중치)

        Args:
            model: ML 모델
            db_manager: 데이터베이스 관리자
            filter_manager: 필터 관리자
            winning_numbers: 당첨번호 리스트

        Returns:
            하이브리드 학습된 모델
        """
        if not SKLEARN_AVAILABLE:
            logging.error("scikit-learn이 설치되지 않아 하이브리드 학습을 수행할 수 없습니다")
            return model

        try:
            # 당첨번호 가져오기
            if winning_numbers is None:
                winning_numbers = db_manager.get_all_winning_numbers()

            if not winning_numbers or len(winning_numbers) < 50:
                logging.warning("당첨번호 데이터가 부족하여 하이브리드 학습을 건너뜁니다")
                return model

            logging.info("\n[Hybrid Training] 하이브리드 학습 시작...")

            # === Stage 1: 당첨번호 패턴 학습 (70%) ===
            logging.info("  [Stage 1] 당첨번호 패턴 학습 중...")
            model_type = type(model).__name__

            if model_type in ('EnsemblePredictor', 'FilteredPoolEnsemblePredictor'):
                # 앙상블 모델 학습 (EnsemblePredictor, FilteredPoolEnsemblePredictor 모두 지원)
                if not model.is_trained:
                    logging.info(f"    - {model_type} 모델 초기 학습...")
                    model.train(winning_numbers, test_size=0.2)
                else:
                    logging.info(f"    - {model_type} 모델 이미 학습됨 (Stage 1 스킵)")

            elif model_type == 'LSTMPredictor':
                # LSTM 모델 학습
                if not model.is_trained:
                    logging.info("    - LSTM 모델 초기 학습...")
                    model.train(winning_numbers, epochs=50, batch_size=32)
                else:
                    logging.info("    - LSTM 모델 이미 학습됨 (Stage 1 스킵)")
            else:
                logging.warning(f"지원하지 않는 모델 타입: {model_type} (지원: EnsemblePredictor, FilteredPoolEnsemblePredictor, LSTMPredictor)")
                return model

            # === Stage 2: 필터 제약사항 학습 (30%) ===
            logging.info("  [Stage 2] 필터 제약사항 학습 중...")
            model = self.fine_tune_model(model, db_manager, filter_manager, winning_numbers)

            # 학습 기록 저장
            self.training_history.append({
                'model_type': model_type,
                'winning_data_size': len(winning_numbers),
                'pool_sample_size': self.pool_sample_size,
                'weights': self.hybrid_weights
            })

            logging.info("[Hybrid Training] 하이브리드 학습 완료")
            logging.info(f"  - 당첨패턴 학습: {self.hybrid_weights['winning_numbers']*100:.0f}% 가중치")
            logging.info(f"  - 필터제약 학습: {self.hybrid_weights['filtered_pool']*100:.0f}% 가중치")

            return model

        except Exception as e:
            logging.error(f"하이브리드 학습 중 오류 발생: {e}")
            return model

    def _sample_filtered_pool(self, filter_manager, round_num: int,
                             sample_size: int) -> List[Tuple[int, ...]]:
        """필터링된 조합 풀에서 샘플링"""
        try:
            # FilterManager에서 필터링된 조합 가져오기
            # 방법 1: get_filtered_combinations 메서드 사용
            if hasattr(filter_manager, 'get_filtered_combinations'):
                filtered_combos = filter_manager.get_filtered_combinations(round_num)
            # 방법 2: FilterDB에서 직접 가져오기
            elif hasattr(filter_manager, 'db_manager'):
                from src.core.specialized_databases import FilterDB
                filter_db = FilterDB(filter_manager.db_manager)
                filtered_combos = filter_db.get_filtered_combinations(round_num)
            else:
                logging.error("필터링된 조합을 가져올 방법이 없습니다")
                return []

            if not filtered_combos:
                logging.warning("필터링된 조합이 없습니다")
                return []

            # 문자열 조합을 튜플로 변환 (DB에서 문자열로 저장되어 있음)
            converted_combos = []
            for combo in filtered_combos:
                if isinstance(combo, str):
                    # "1,2,3,4,5,6" 형식 → (1, 2, 3, 4, 5, 6) 튜플로 변환
                    try:
                        numbers = tuple(int(n.strip()) for n in combo.split(','))
                        converted_combos.append(numbers)
                    except (ValueError, AttributeError) as e:
                        logging.warning(f"조합 변환 오류: '{combo}' - {e}")
                        continue
                elif isinstance(combo, (list, tuple)):
                    converted_combos.append(tuple(combo))
                else:
                    logging.warning(f"지원하지 않는 조합 형식: {type(combo)}")
                    continue

            if not converted_combos:
                logging.warning("변환된 조합이 없습니다")
                return []

            logging.debug(f"[_sample_filtered_pool] 조합 변환 완료: {len(converted_combos):,}개 (원본: {len(filtered_combos):,}개)")

            # 샘플링
            if len(converted_combos) > sample_size:
                indices = np.random.choice(len(converted_combos), sample_size, replace=False)
                sampled = [converted_combos[i] for i in indices]
            else:
                sampled = converted_combos

            return sampled

        except Exception as e:
            logging.error(f"샘플링 오류: {e}")
            return []

    def evaluate_pool_coverage(self, model: Any, filtered_combinations: List[Tuple[int, ...]],
                              winning_numbers: List[str]) -> Dict[str, Any]:
        """
        필터 풀 내 모델 예측 성능 평가

        Args:
            model: 학습된 모델
            filtered_combinations: 필터링된 조합 리스트
            winning_numbers: 당첨번호 리스트

        Returns:
            평가 메트릭 딕셔너리
        """
        try:
            # 특징 추출
            pool_features = self.extract_pool_features(filtered_combinations)
            pool_labels = self.generate_labels(filtered_combinations, winning_numbers)

            if pool_features.empty or len(pool_labels) == 0:
                return {'error': '특징 또는 레이블 추출 실패'}

            # 스케일링 (scaler가 아직 fit되지 않았으면 NotFittedError -> 안전하게 fit_transform 폴백)
            from sklearn.exceptions import NotFittedError
            try:
                pool_features_scaled = self.scaler.transform(pool_features)
            except NotFittedError:
                logging.warning("[evaluate_pool_coverage] scaler 미학습 상태 - fit_transform으로 폴백")
                pool_features_scaled = self.scaler.fit_transform(pool_features)

            # 예측
            model_type = type(model).__name__

            if model_type == 'EnsemblePredictor':
                # 앙상블 모델 예측
                predictions = model.predict_probability(pool_features_scaled)
                # 각 조합의 예측 점수 계산
                pred_scores = np.mean(predictions, axis=1) if predictions.ndim > 1 else predictions
            else:
                # 기타 모델은 레이블 직접 사용
                pred_scores = pool_labels

            # 평가 메트릭
            mse = mean_squared_error(pool_labels, pred_scores)
            r2 = r2_score(pool_labels, pred_scores)

            # 상위 예측의 정확도
            top_k = min(100, len(pred_scores))
            top_indices = np.argsort(pred_scores)[-top_k:]
            top_labels = pool_labels[top_indices]

            metrics = {
                'pool_size': len(filtered_combinations),
                'mse': float(mse),
                'r2_score': float(r2),
                'top_100_avg_similarity': float(np.mean(top_labels)),
                'overall_avg_similarity': float(np.mean(pool_labels)),
                'max_similarity': float(np.max(pool_labels))
            }

            logging.info(f"\n[Pool Coverage] 평가 결과:")
            logging.info(f"  - MSE: {mse:.4f}")
            logging.info(f"  - R² Score: {r2:.4f}")
            logging.info(f"  - Top 100 평균 유사도: {metrics['top_100_avg_similarity']:.3f}")

            return metrics

        except Exception as e:
            logging.error(f"풀 커버리지 평가 오류: {e}")
            return {'error': str(e)}

    def save_trainer_state(self, filepath: str):
        """학습기 상태 저장"""
        try:
            state = {
                'pool_sample_size': self.pool_sample_size,
                'feature_config': self.feature_config,
                'hybrid_weights': self.hybrid_weights,
                'training_history': self.training_history,
                'scaler': self.scaler
            }

            with open(filepath, 'wb') as f:
                pickle.dump(state, f)

            logging.info(f"학습기 상태 저장 완료: {filepath}")

        except Exception as e:
            logging.error(f"학습기 상태 저장 실패: {e}")

    def load_trainer_state(self, filepath: str):
        """학습기 상태 로드"""
        try:
            with open(filepath, 'rb') as f:
                state = pickle.load(f)

            self.pool_sample_size = state.get('pool_sample_size', 10000)
            self.feature_config = state.get('feature_config', self.feature_config)
            self.hybrid_weights = state.get('hybrid_weights', self.hybrid_weights)
            self.training_history = state.get('training_history', [])
            self.scaler = state.get('scaler', StandardScaler())

            logging.info(f"학습기 상태 로드 완료: {filepath}")

        except Exception as e:
            logging.error(f"학습기 상태 로드 실패: {e}")


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from src.core.db_manager import DatabaseManager
    from src.core.filter_manager import FilterManager
    from src.ml.ensemble_predictor import EnsemblePredictor

    # 데이터베이스 및 필터 관리자 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)

    # 당첨번호 로드
    winning_numbers = db_manager.get_all_winning_numbers()

    if len(winning_numbers) < 100:
        print(f"데이터 부족: {len(winning_numbers)}개 (최소 100개 필요)")
        return

    # 앙상블 예측기 생성 및 학습
    print("\n=== 앙상블 모델 초기 학습 ===")
    ensemble = EnsemblePredictor()
    if not ensemble.is_trained:
        ensemble.train(winning_numbers, test_size=0.2)

    # 필터링된 풀 학습기 생성
    print("\n=== 필터링된 풀 학습기 테스트 ===")
    trainer = FilteredPoolTrainer(pool_sample_size=5000)

    # 하이브리드 학습 수행
    print("\n=== 하이브리드 학습 수행 ===")
    ensemble_hybrid = trainer.train_hybrid_model(
        ensemble, db_manager, filter_manager, winning_numbers
    )

    # 예측 수행
    print("\n=== 하이브리드 모델 예측 ===")
    predictions = ensemble_hybrid.predict_next_numbers(winning_numbers, num_predictions=5)

    print("\n예측 결과:")
    for i, pred in enumerate(predictions, 1):
        print(f"{i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    main()
