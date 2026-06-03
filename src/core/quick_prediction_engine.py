#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빠른 예측 엔진 (Quick Prediction Engine)

프로그램 시작 시 캐시된 데이터를 활용하여 즉시 예측을 생성합니다.
전체 파이프라인 실행 없이 5-10초 내에 예측 결과를 제공합니다.
"""

import os
import json
import logging
import pickle
import random
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
import threading

# 로깅 설정
logger = logging.getLogger(__name__)


class QuickPredictionEngine:
    """
    캐시 기반 즉시 예측 엔진

    특징:
    - ML 모델 재학습 없이 캐시된 모델 사용
    - 필터링된 조합 풀에서 빠른 선택
    - 이전 성능 통계 기반 신뢰도 계산
    - 5-10초 내 예측 완료
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(QuickPredictionEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, base_dir: str = None):
        """
        빠른 예측 엔진 초기화

        Args:
            base_dir: 기본 디렉토리 경로
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent.parent
        self.cache_dir = self.base_dir / "cache"
        self.models_dir = self.cache_dir / "models"
        self.data_dir = self.base_dir / "data"

        # 캐시 상태
        self._cached_predictions = None
        self._cached_filtered_pool = None
        self._cached_performance_stats = None
        self._last_cache_load = None

        self._initialized = True
        logger.info("[QuickPrediction] 빠른 예측 엔진 초기화 완료")

    def generate_quick_predictions(self, num_sets: int = 5,
                                    db_manager=None,
                                    use_ml_cache: bool = True) -> List[Dict]:
        """
        캐시 기반 즉시 예측 생성 (다양성 보장)

        Args:
            num_sets: 생성할 예측 세트 수 (기본: 5)
            db_manager: DatabaseManager 인스턴스
            use_ml_cache: ML 캐시 사용 여부

        Returns:
            예측 결과 리스트
        """
        logger.info(f"[QuickPrediction] 빠른 예측 생성 시작 ({num_sets}세트)")
        start_time = datetime.now()

        predictions = []
        used_numbers = set()  # 중복 방지

        try:
            # 1. 캐시된 ML 예측 로드 시도 (랜덤 샘플링으로 다양성 확보)
            if use_ml_cache:
                ml_predictions = self._load_cached_ml_predictions()
                if ml_predictions:
                    logger.info(f"[QuickPrediction] 캐시된 ML 예측 {len(ml_predictions)}개 로드")

                    # ML 예측에서 일부 랜덤 선택 (최대 3개) + 필터 풀에서 나머지
                    ml_sample_size = min(3, len(ml_predictions), num_sets)
                    sampled_ml = random.sample(ml_predictions, ml_sample_size)

                    for pred in sampled_ml:
                        numbers_tuple = tuple(sorted(pred['numbers']))
                        if numbers_tuple not in used_numbers:
                            predictions.append(pred)
                            used_numbers.add(numbers_tuple)

                    logger.info(f"[QuickPrediction] ML 캐시에서 {len(predictions)}개 선택")

            # 2. 필터 풀에서 추가 (항상 다양성을 위해 풀에서 가져옴)
            if len(predictions) < num_sets:
                needed = num_sets - len(predictions) + 5  # 여유분 확보
                pool_predictions = self._get_from_filtered_pool(needed, db_manager)

                for pred in pool_predictions:
                    if len(predictions) >= num_sets:
                        break
                    numbers_tuple = tuple(sorted(pred['numbers']))
                    if numbers_tuple not in used_numbers:
                        predictions.append(pred)
                        used_numbers.add(numbers_tuple)

            # 3. 여전히 부족하면 추가 풀에서 가져오기
            if len(predictions) < num_sets:
                needed = num_sets - len(predictions) + 5
                additional_pool = self._get_additional_from_pool(needed, db_manager)

                for pred in additional_pool:
                    if len(predictions) >= num_sets:
                        break
                    numbers_tuple = tuple(sorted(pred['numbers']))
                    if numbers_tuple not in used_numbers:
                        predictions.append(pred)
                        used_numbers.add(numbers_tuple)

            # 3.5. 풀이 비어있어 예측이 없으면 비상 폴백 사용
            if len(predictions) == 0:
                logger.warning("[QuickPrediction] 필터링된 풀에서 예측 가져오기 실패 - 비상 폴백 사용")
                fallback_predictions = self._get_fallback_from_pool(num_sets)
                for pred in fallback_predictions:
                    numbers_tuple = tuple(sorted(pred['numbers']))
                    if numbers_tuple not in used_numbers:
                        predictions.append(pred)
                        used_numbers.add(numbers_tuple)

            # 4. 신뢰도 및 메타데이터 보정
            predictions = self._enhance_predictions(predictions, db_manager)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"[QuickPrediction] 빠른 예측 완료: {len(predictions)}세트, {elapsed:.2f}초 소요")

            return predictions[:num_sets]

        except Exception as e:
            logger.error(f"[QuickPrediction] 빠른 예측 생성 실패: {e}")
            # 폴백: 필터링된 풀에서 랜덤 선택 (간소화된 검증 사용 안함)
            return self._get_fallback_from_pool(num_sets)

    def _load_cached_ml_predictions(self) -> List[Dict]:
        """캐시된 ML 예측 로드"""
        predictions = []

        def _extract_prediction(pred, default_confidence: float, default_source: str) -> Dict:
            """예측 데이터에서 표준 형식으로 변환"""
            if isinstance(pred, dict):
                # dict 형태: {'numbers': [...], 'confidence': 0.7, ...}
                numbers = pred.get('numbers', [])
                if hasattr(numbers, 'tolist'):
                    numbers = numbers.tolist()
                return {
                    'numbers': [int(n) for n in numbers] if numbers else [],
                    'confidence': float(pred.get('confidence', default_confidence)),
                    'source': pred.get('source', default_source)
                }
            elif hasattr(pred, '__iter__') and not isinstance(pred, str):
                # 리스트/튜플 형태
                numbers = list(pred)
                if hasattr(numbers, 'tolist'):
                    numbers = numbers.tolist()
                return {
                    'numbers': [int(n) for n in numbers],
                    'confidence': default_confidence,
                    'source': default_source
                }
            return None

        try:
            # Ensemble 모델 캐시 확인
            ensemble_files = list(self.models_dir.glob("ensemble_predictions_*.pkl"))
            if ensemble_files:
                latest_file = max(ensemble_files, key=lambda x: x.stat().st_mtime)
                with open(latest_file, 'rb') as f:
                    ensemble_preds = pickle.load(f)
                    for pred in ensemble_preds[:5]:
                        extracted = _extract_prediction(pred, 0.75, 'Ensemble (cached)')
                        if extracted and len(extracted['numbers']) == 6:
                            predictions.append(extracted)
                logger.info(f"[QuickPrediction] Ensemble 캐시 로드: {latest_file.name} ({len(predictions)}개)")

            # LSTM 캐시 확인
            lstm_count_before = len(predictions)
            lstm_files = list(self.models_dir.glob("lstm_predictions_*.pkl"))
            if lstm_files:
                latest_file = max(lstm_files, key=lambda x: x.stat().st_mtime)
                with open(latest_file, 'rb') as f:
                    lstm_preds = pickle.load(f)
                    for pred in lstm_preds[:3]:
                        extracted = _extract_prediction(pred, 0.70, 'LSTM (cached)')
                        if extracted and len(extracted['numbers']) == 6:
                            predictions.append(extracted)
                logger.info(f"[QuickPrediction] LSTM 캐시 로드: {latest_file.name} ({len(predictions) - lstm_count_before}개)")

            # Monte Carlo 캐시 확인
            mc_count_before = len(predictions)
            mc_files = list(self.models_dir.glob("monte_carlo_*.pkl"))
            if mc_files:
                latest_file = max(mc_files, key=lambda x: x.stat().st_mtime)
                with open(latest_file, 'rb') as f:
                    mc_preds = pickle.load(f)
                    for pred in mc_preds[:3]:
                        extracted = _extract_prediction(pred, 0.65, 'MonteCarlo (cached)')
                        if extracted and len(extracted['numbers']) == 6:
                            predictions.append(extracted)
                logger.info(f"[QuickPrediction] Monte Carlo 캐시 로드: {latest_file.name} ({len(predictions) - mc_count_before}개)")

            if predictions:
                logger.info(f"[QuickPrediction] 총 {len(predictions)}개 ML 캐시 예측 로드 완료")

        except Exception as e:
            logger.warning(f"[QuickPrediction] ML 캐시 로드 실패: {e}")
            import traceback
            traceback.print_exc()

        return predictions

    def _get_from_filtered_pool(self, num_needed: int, db_manager=None) -> List[Dict]:
        """필터링된 조합 풀에서 예측 가져오기 (엄격한 필터 검증 포함)"""
        predictions = []

        try:
            import sqlite3
            db_path = self.base_dir / "data" / "combinations.db"

            if not db_path.exists():
                logger.warning(f"[QuickPrediction] combinations.db 없음: {db_path}")
                return predictions

            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()

                # top_filtered_combinations 테이블에서 충분히 많은 샘플 가져오기
                # 약 5.5%가 필터 실패하므로 넉넉히 가져옴
                cursor.execute("""
                    SELECT combination FROM filtered_combinations
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (num_needed * 50,))

                rows = cursor.fetchall()

                if rows:
                    # 점수 기반 정렬 + 필터 검증
                    scored = []
                    skipped = 0
                    for row in rows:
                        combo_str = row[0]
                        combo = tuple(int(n) for n in combo_str.split(','))

                        # 엄격한 필터 검증 (대시보드 기준과 동일)
                        if not self._validate_combination(list(combo)):
                            skipped += 1
                            continue

                        score = self._score_combination(combo)
                        scored.append((combo, score))

                    scored.sort(key=lambda x: x[1], reverse=True)

                    for combo, score in scored[:num_needed]:
                        predictions.append({
                            'numbers': sorted(list(combo)),
                            'confidence': min(0.70 + score * 0.1, 0.90),
                            'source': 'FilteredPool'
                        })

                    logger.info(f"[QuickPrediction] 필터 풀에서 {len(predictions)}개 선택 (검증 통과: {len(scored)}, 스킵: {skipped})")
                else:
                    logger.warning("[QuickPrediction] filtered_combinations 테이블이 비어있음")

        except Exception as e:
            logger.warning(f"[QuickPrediction] 필터 풀 로드 실패: {e}")
            import traceback
            traceback.print_exc()

        return predictions

    def _validate_combination(self, numbers: List[int]) -> bool:
        """조합이 필터 기준을 통과하는지 검증"""
        if len(numbers) != 6:
            return False

        sorted_nums = sorted(numbers)

        # 1. 홀짝 균형 (0개 또는 6개 모두 홀수/짝수는 제외)
        odd_count = len([n for n in numbers if n % 2 == 1])
        if odd_count == 0 or odd_count == 6:
            return False

        # 2. 합계 범위 (68~209) -> (60~230)으로 완화
        total_sum = sum(numbers)
        if total_sum < 60 or total_sum > 230:
            return False

        # 3. 연속 번호 (4개 이상 연속 제외 - 완화됨)
        consecutive = 0
        max_consecutive = 0
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive + 1)
            else:
                consecutive = 0
        if max_consecutive >= 4:  # 기존 3에서 4로 완화
            return False

        # 4. 최대 간격 (35 초과 제외 - 완화됨)
        max_gap = max(sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums) - 1))
        if max_gap > 35:  # 기존 20에서 35로 완화
            return False

        return True

    def _generate_statistical_predictions(self, num_needed: int, db_manager=None) -> List[Dict]:
        """통계 기반 예측 생성 (필터 검증 포함)"""
        predictions = []

        try:
            if db_manager is None:
                from src.core.db_manager import DatabaseManager
                db_manager = DatabaseManager()

            # 최근 50회차 당첨번호 분석
            recent_numbers = db_manager.lotto_db.get_recent_numbers(50)

            if recent_numbers:
                # 번호별 출현 빈도 계산
                frequency = {}
                for _, numbers_str, _ in recent_numbers:
                    numbers = [int(n) for n in numbers_str.split(',')]
                    for num in numbers:
                        frequency[num] = frequency.get(num, 0) + 1

                # 핫넘버 (자주 나오는 번호)
                sorted_freq = sorted(frequency.items(), key=lambda x: x[1], reverse=True)
                hot_numbers = [n for n, _ in sorted_freq[:15]]

                # 콜드넘버 (적게 나오는 번호)
                cold_numbers = [n for n, _ in sorted_freq[-10:]]

                max_attempts = num_needed * 20  # 최대 시도 횟수
                attempts = 0

                while len(predictions) < num_needed and attempts < max_attempts:
                    attempts += 1

                    # 핫넘버 3-4개 + 콜드넘버 1-2개 + 랜덤 1-2개
                    combo = set()
                    combo.update(random.sample(hot_numbers, random.randint(3, 4)))

                    remaining = 6 - len(combo)
                    if remaining > 0 and cold_numbers:
                        combo.update(random.sample(cold_numbers, min(remaining, 2)))

                    remaining = 6 - len(combo)
                    if remaining > 0:
                        all_nums = set(range(1, 46)) - combo
                        combo.update(random.sample(list(all_nums), remaining))

                    combo_list = sorted(list(combo))[:6]

                    # 필터 검증 통과 여부 확인
                    if self._validate_combination(combo_list):
                        # 중복 제거
                        combo_tuple = tuple(combo_list)
                        if not any(tuple(p['numbers']) == combo_tuple for p in predictions):
                            # 신뢰도 동적 계산 (핫넘버 비율 + 품질 점수 기반)
                            hot_count = len(set(combo_list) & set(hot_numbers))
                            quality_score = self._score_combination(tuple(combo_list))
                            # 기본 50% + 핫넘버 보너스 (최대 15%) + 품질 점수 (최대 20%)
                            confidence = 0.50 + (hot_count / 6) * 0.15 + min(quality_score * 0.05, 0.20)
                            confidence = min(max(confidence, 0.45), 0.85)  # 45%~85% 범위 제한

                            predictions.append({
                                'numbers': combo_list,
                                'confidence': round(confidence, 2),
                                'source': 'Statistical'
                            })

                logger.info(f"[QuickPrediction] 통계 기반 {len(predictions)}개 생성 (시도: {attempts})")

        except Exception as e:
            logger.warning(f"[QuickPrediction] 통계 예측 생성 실패: {e}")

        return predictions

    def _generate_fallback_predictions(self, num_sets: int) -> List[Dict]:
        """폴백 예측 생성 (최후의 수단) - 필터 검증 포함"""
        predictions = []

        odds = [n for n in range(1, 46) if n % 2 == 1]
        evens = [n for n in range(1, 46) if n % 2 == 0]

        max_attempts = num_sets * 30  # 최대 시도 횟수
        attempts = 0

        while len(predictions) < num_sets and attempts < max_attempts:
            attempts += 1

            # 홀짝 비율 3:3 또는 4:2 유지
            odd_count = random.choice([3, 4])
            even_count = 6 - odd_count

            combo = set()
            combo.update(random.sample(odds, odd_count))
            combo.update(random.sample(evens, even_count))

            combo_list = sorted(list(combo))

            # 필터 검증 통과 여부 확인
            if self._validate_combination(combo_list):
                # 중복 제거
                combo_tuple = tuple(combo_list)
                if not any(tuple(p['numbers']) == combo_tuple for p in predictions):
                    # 폴백 신뢰도 동적 계산 (기본 40% + 품질 점수)
                    quality_score = self._score_combination(tuple(combo_list))
                    confidence = 0.40 + min(quality_score * 0.05, 0.15)  # 40%~55% 범위
                    confidence = min(max(confidence, 0.35), 0.55)

                    predictions.append({
                        'numbers': combo_list,
                        'confidence': round(confidence, 2),
                        'source': 'Fallback'
                    })

        logger.info(f"[QuickPrediction] 폴백 예측 {len(predictions)}개 생성 (시도: {attempts})")
        return predictions

    def _get_additional_from_pool(self, num_needed: int, db_manager=None) -> List[Dict]:
        """
        필터링된 풀에서 추가 예측 가져오기 (통계 가중치 적용)

        [HOT] FIX: 간소화된 검증 대신 이미 필터링된 DB에서만 가져옴
        """
        predictions = []

        try:
            import sqlite3
            db_path = self.base_dir / "data" / "combinations.db"

            if not db_path.exists():
                logger.warning(f"[QuickPrediction] combinations.db 없음")
                return predictions

            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()

                # 다른 정렬 기준으로 가져오기 (합계 기준 정렬)
                cursor.execute("""
                    SELECT combination FROM filtered_combinations
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (num_needed * 10,))

                rows = cursor.fetchall()

                if rows:
                    # 점수 기반 선택
                    scored = []
                    for row in rows:
                        combo_str = row[0]
                        combo = tuple(int(n) for n in combo_str.split(','))
                        score = self._score_combination(combo)
                        scored.append((combo, score))

                    # 점수 순 정렬
                    scored.sort(key=lambda x: x[1], reverse=True)

                    for combo, score in scored[:num_needed]:
                        confidence = 0.55 + min(score * 0.15, 0.25)  # 55%~80%
                        predictions.append({
                            'numbers': sorted(list(combo)),
                            'confidence': round(confidence, 2),
                            'source': 'FilteredPool (additional)'
                        })

                    logger.info(f"[QuickPrediction] 필터링된 풀에서 추가 {len(predictions)}개 선택")

        except Exception as e:
            logger.warning(f"[QuickPrediction] 추가 풀 로드 실패: {e}")

        return predictions

    def _get_fallback_from_pool(self, num_sets: int) -> List[Dict]:
        """
        폴백: 필터링된 풀에서 랜덤 선택

        [HOT] FIX: 간소화된 검증으로 새로 생성하지 않고,
               이미 16개 필터를 통과한 조합에서만 선택

        [PIN] filtered_combinations가 비어있으면 비상 폴백 사용
        """
        predictions = []

        try:
            import sqlite3
            db_path = self.base_dir / "data" / "combinations.db"

            if not db_path.exists():
                logger.warning(f"[QuickPrediction] combinations.db 없음 - 비상 폴백 사용")
                return self._emergency_fallback(num_sets)

            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()

                # 랜덤하게 가져오기
                cursor.execute("""
                    SELECT combination FROM filtered_combinations
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (num_sets * 5,))

                rows = cursor.fetchall()

                if rows:
                    for row in rows[:num_sets]:
                        combo_str = row[0]
                        combo = [int(n) for n in combo_str.split(',')]
                        score = self._score_combination(tuple(combo))
                        confidence = 0.45 + min(score * 0.10, 0.15)  # 45%~60%

                        predictions.append({
                            'numbers': sorted(combo),
                            'confidence': round(confidence, 2),
                            'source': 'FilteredPool (fallback)'
                        })

                    logger.info(f"[QuickPrediction] 폴백: 필터링된 풀에서 {len(predictions)}개 선택")
                else:
                    # filtered_combinations 비어있음 - 비상 폴백 사용
                    logger.warning("[QuickPrediction] filtered_combinations 비어있음 - 비상 폴백 사용")
                    return self._emergency_fallback(num_sets)

        except Exception as e:
            logger.error(f"[QuickPrediction] 폴백 풀 로드 실패: {e}")
            return self._emergency_fallback(num_sets)

        return predictions

    def _emergency_fallback(self, num_sets: int) -> List[Dict]:
        """
        비상 폴백: filtered_combinations가 없을 때 사용

        [WARN] 경고: 4개 기본 필터만 검증 (16개 전체 필터 미통과 가능)
        [PIN] main.py를 먼저 실행하여 필터링 풀을 생성해야 함
        """
        predictions = []

        odds = [n for n in range(1, 46) if n % 2 == 1]
        evens = [n for n in range(1, 46) if n % 2 == 0]

        max_attempts = num_sets * 50
        attempts = 0

        while len(predictions) < num_sets and attempts < max_attempts:
            attempts += 1

            # 홀짝 비율 3:3 또는 4:2
            odd_count = random.choice([3, 4])
            even_count = 6 - odd_count

            combo = set()
            combo.update(random.sample(odds, odd_count))
            combo.update(random.sample(evens, even_count))
            combo_list = sorted(list(combo))

            # 기본 필터 검증 (4개만)
            if self._validate_combination(combo_list):
                combo_tuple = tuple(combo_list)
                if not any(tuple(p['numbers']) == combo_tuple for p in predictions):
                    score = self._score_combination(combo_tuple)
                    # 비상 폴백은 낮은 신뢰도 (30%~45%)
                    confidence = 0.30 + min(score * 0.05, 0.15)

                    predictions.append({
                        'numbers': combo_list,
                        'confidence': round(confidence, 2),
                        'source': 'Emergency'  # 필터링 풀 비어있음
                    })

        if predictions:
            logger.warning(f"[QuickPrediction] 비상 폴백 {len(predictions)}개 생성 - main.py 실행 권장!")
        else:
            logger.error("[QuickPrediction] 비상 폴백도 실패 - 예측 불가")

        return predictions

    def _score_combination(self, combo: tuple) -> float:
        """조합 점수 계산"""
        score = 0.0
        numbers = list(combo)

        # 합계 점수 (100-180 범위가 이상적)
        total = sum(numbers)
        if 100 <= total <= 180:
            score += 0.3
        elif 80 <= total <= 200:
            score += 0.1

        # 홀짝 균형 점수
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        if odd_count in [3, 4]:
            score += 0.3
        elif odd_count in [2, 5]:
            score += 0.1

        # 연속번호 페널티
        sorted_nums = sorted(numbers)
        consecutive = 0
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                consecutive += 1

        if consecutive <= 1:
            score += 0.2
        elif consecutive == 2:
            score += 0.1

        # 구간 분포 점수 (1-9, 10-19, 20-29, 30-39, 40-45)
        sections = [0] * 5
        for n in numbers:
            if n <= 9:
                sections[0] += 1
            elif n <= 19:
                sections[1] += 1
            elif n <= 29:
                sections[2] += 1
            elif n <= 39:
                sections[3] += 1
            else:
                sections[4] += 1

        # 적어도 3개 구간에 분포
        filled_sections = sum(1 for s in sections if s > 0)
        if filled_sections >= 4:
            score += 0.2
        elif filled_sections == 3:
            score += 0.1

        return min(score, 1.0)

    def _enhance_predictions(self, predictions: List[Dict], db_manager=None) -> List[Dict]:
        """예측 결과 보정 및 메타데이터 추가"""
        enhanced = []

        for i, pred in enumerate(predictions):
            numbers = pred.get('numbers', [])

            # 숫자 정렬 및 검증
            if len(numbers) >= 6:
                numbers = sorted(numbers[:6])
            else:
                # 부족한 경우 랜덤 추가
                available = set(range(1, 46)) - set(numbers)
                numbers.extend(random.sample(list(available), 6 - len(numbers)))
                numbers = sorted(numbers)

            # 특성 계산
            characteristics = {
                'sum': sum(numbers),
                'odd_count': sum(1 for n in numbers if n % 2 == 1),
                'even_count': sum(1 for n in numbers if n % 2 == 0),
                'avg': round(sum(numbers) / 6, 2),
                'range': max(numbers) - min(numbers),
                'generation_type': 'quick'
            }

            enhanced.append({
                'numbers': numbers,
                'confidence': pred.get('confidence', 0.5),
                'source': pred.get('source', 'Unknown'),
                'characteristics': characteristics,
                'set_number': i + 1
            })

        return enhanced

    def get_cached_stats(self) -> Dict:
        """캐시된 성능 통계 반환"""
        try:
            stats_file = self.data_dir / "quick_prediction_stats.json"
            if stats_file.exists():
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[QuickPrediction] 통계 로드 실패: {e}")

        return {
            'total_quick_predictions': 0,
            'avg_confidence': 0.0,
            'cache_hit_rate': 0.0,
            'last_update': None
        }

    def save_predictions_cache(self, predictions: List[Dict], round_num: int):
        """예측 결과 캐시 저장"""
        try:
            cache_file = self.cache_dir / f"quick_predictions_{round_num}.json"
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'round': round_num,
                    'timestamp': datetime.now().isoformat(),
                    'predictions': predictions
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"[QuickPrediction] 예측 캐시 저장: {cache_file}")

        except Exception as e:
            logger.error(f"[QuickPrediction] 캐시 저장 실패: {e}")

    def load_predictions_cache(self, round_num: int) -> Optional[List[Dict]]:
        """캐시된 예측 결과 로드"""
        try:
            cache_file = self.cache_dir / f"quick_predictions_{round_num}.json"
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('predictions', [])
        except Exception as e:
            logger.warning(f"[QuickPrediction] 캐시 로드 실패: {e}")

        return None


# 글로벌 인스턴스
_quick_engine = None


def get_quick_prediction_engine() -> QuickPredictionEngine:
    """QuickPredictionEngine 싱글톤 인스턴스 반환"""
    global _quick_engine
    if _quick_engine is None:
        _quick_engine = QuickPredictionEngine()
    return _quick_engine
