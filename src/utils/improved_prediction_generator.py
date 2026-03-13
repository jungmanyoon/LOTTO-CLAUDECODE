"""개선된 예측 생성기

필터링된 풀 기반 ML 시스템을 통합한 예측 생성
기존 시스템과의 호환성을 유지하면서 새로운 기능 제공
"""

import logging
import random
import time
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import numpy as np


def generate_final_predictions_improved(db_manager, filter_manager=None,
                                       ml_predictions=None, num_sets=5,
                                       use_strict_validation=True,
                                       use_filtered_pool_system=True):
    """개선된 최종 예측 번호 생성 함수

    Args:
        db_manager: 데이터베이스 매니저
        filter_manager: 필터 매니저 (선택사항)
        ml_predictions: ML 예측 결과 (선택사항)
        num_sets: 생성할 세트 수
        use_strict_validation: 엄격한 검증 모드 사용 여부
        use_filtered_pool_system: 새로운 필터링된 풀 시스템 사용 여부

    Returns:
        검증된 최종 예측 리스트
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()

    try:
        if use_filtered_pool_system:
            # 새로운 필터링된 풀 기반 시스템 사용
            logger.info("필터링된 풀 기반 ML 통합 시스템 사용")

            from ..core.ml_filter_integration_manager import MLFilterIntegrationManager

            integration_manager = MLFilterIntegrationManager(db_manager)
            result = integration_manager.generate_filtered_pool_predictions(
                num_predictions=num_sets,
                force_retrain=False
            )

            predictions = result.get('predictions', [])
            metadata = result.get('metadata', {})

            # 기존 형식으로 변환
            final_predictions = []
            for i, pred in enumerate(predictions):
                formatted_pred = {
                    'numbers': pred['numbers'],
                    'confidence': pred.get('final_score', pred.get('confidence', 0.0)),
                    'source': f"ML-Integrated/{pred.get('model', 'unknown')}",
                    'filter_status': 'passed' if pred.get('filter_passed', True) else 'relaxed',
                    'in_pool': True,  # 필터링된 풀에서 생성됨
                    'quality_score': pred.get('quality_score', 0.5),
                    'model_type': pred.get('model', 'integrated')
                }
                final_predictions.append(formatted_pred)

            generation_time = time.time() - start_time
            logger.info(f"필터링된 풀 시스템 예측 완료: {len(final_predictions)}개, "
                       f"소요시간: {generation_time:.2f}초")

            # 성능 정보 로깅
            if metadata:
                logger.info(f"필터링된 풀 크기: {metadata.get('filtered_pool_size', 0):,}개")
                logger.info(f"풀 감소율: {metadata.get('pool_reduction_ratio', 0):.2%}")

            return final_predictions

        else:
            # 기존 시스템 사용
            logger.info("기존 필터 시스템 사용")
            return _generate_legacy_predictions(db_manager, filter_manager, ml_predictions, num_sets, use_strict_validation)

    except Exception as e:
        logger.error(f"필터링된 풀 시스템 실패, 기존 시스템으로 폴백: {e}")
        return _generate_legacy_predictions(db_manager, filter_manager, ml_predictions, num_sets, use_strict_validation)


def _generate_legacy_predictions(db_manager, filter_manager, ml_predictions, num_sets, use_strict_validation):
    """기존 시스템을 사용한 예측 생성"""
    logger = logging.getLogger(__name__)
    final_predictions = []

    # FilterValidator 임포트 및 초기화
    try:
        from ..utils.filter_validator import FilterValidator
        validator = FilterValidator(db_manager, filter_manager)
    except ImportError:
        from src.utils.filter_validator import FilterValidator
        validator = FilterValidator(db_manager, filter_manager)

    # 통계 추적
    stats = {
        'ml_success': 0,
        'ml_failed': 0,
        'ml_relaxed': 0,
        'from_pool': 0,
        'total_attempts': 0
    }

    # 1. 필터링된 풀 가져오기
    try:
        last_round = db_manager.get_last_round()
        filtered_combinations = db_manager.combinations_db.get_filtered_combinations(last_round)
        if not filtered_combinations:
            logger.error("필터링된 조합 풀이 비어있습니다!")
            # 비상 모드: 필터 매니저를 통해 직접 생성
            logger.info("비상 모드: 필터를 통해 새로운 조합 생성 시도")
            filtered_combinations = _generate_emergency_pool(filter_manager, db_manager, 10000)
    except Exception as e:
        logger.error(f"필터링된 조합 가져오기 실패: {e}")
        filtered_combinations = []

    pool_size = len(filtered_combinations)
    logger.info(f"필터링된 풀 크기: {pool_size:,}개")

    # 2. ML 예측 검증 및 추가 (엄격한 검증 적용)
    if ml_predictions:
        all_ml_predictions = _process_ml_predictions(ml_predictions)

        for pred in all_ml_predictions:
            if len(final_predictions) >= num_sets:
                break

            stats['total_attempts'] += 1
            numbers = pred.get('numbers', [])
            confidence = pred.get('confidence', 0.0)
            model_name = pred.get('model', 'Unknown')

            if len(numbers) != 6:
                continue

            # 필터 검증 수행
            validation_result = validator.validate_prediction(
                numbers, last_round,
                is_ml_prediction=True,
                model_confidence=confidence
            )

            # 엄격한 검증 모드
            if use_strict_validation:
                # 필터링된 풀에 있는지 확인
                pool_check = validator.validate_against_filtered_pool(numbers, last_round)

                if pool_check['in_filtered_pool']:
                    # 풀에 포함된 경우만 추가
                    if not _is_duplicate(numbers, final_predictions):
                        final_predictions.append({
                            'numbers': sorted(numbers),
                            'confidence': confidence,
                            'source': f"ML/{model_name}",
                            'filter_status': 'passed',
                            'in_pool': True
                        })
                        stats['ml_success'] += 1
                        logger.info(f"ML 예측 추가 (풀 포함): {sorted(numbers)} - {model_name}")
                else:
                    # 풀에 없지만 중요 필터 통과한 고신뢰도 ML 예측
                    if not validation_result['critical_failures'] and confidence >= 0.85:
                        if not _is_duplicate(numbers, final_predictions):
                            final_predictions.append({
                                'numbers': sorted(numbers),
                                'confidence': confidence,
                                'source': f"ML-Relaxed/{model_name}",
                                'filter_status': 'relaxed',
                                'in_pool': False
                            })
                            stats['ml_relaxed'] += 1
                            logger.warning(f"ML 예측 추가 (완화 적용): {sorted(numbers)} - {model_name}")
                    else:
                        stats['ml_failed'] += 1
                        logger.debug(f"ML 예측 제외 (풀 미포함): {sorted(numbers)}")
            else:
                # 일반 검증 모드 (기존 방식)
                if validation_result['recommendation'] in ['accept', 'accept_with_warning']:
                    if not _is_duplicate(numbers, final_predictions):
                        final_predictions.append({
                            'numbers': sorted(numbers),
                            'confidence': confidence,
                            'source': f"ML/{model_name}",
                            'filter_status': validation_result['recommendation']
                        })
                        if validation_result['filter_bypass_applied']:
                            stats['ml_relaxed'] += 1
                        else:
                            stats['ml_success'] += 1
                else:
                    stats['ml_failed'] += 1

    # 3. 부족한 수만큼 필터링된 풀에서 선택
    if len(final_predictions) < num_sets and filtered_combinations:
        needed = num_sets - len(final_predictions)
        logger.info(f"필터링된 풀에서 {needed}개 추가 선택")

        # 무작위 샘플링
        sample_size = min(needed * 10, len(filtered_combinations))  # 충분한 후보 확보
        candidates = random.sample(filtered_combinations, sample_size)

        for combo_str in candidates:
            if len(final_predictions) >= num_sets:
                break

            numbers = list(map(int, combo_str.split(',')))

            # 중복 체크
            if not _is_duplicate(numbers, final_predictions):
                # 추가 검증 (선택사항)
                validation_result = validator.validate_prediction(
                    numbers, last_round,
                    is_ml_prediction=False,
                    model_confidence=0.0
                )

                final_predictions.append({
                    'numbers': sorted(numbers),
                    'confidence': 0.4,  # 필터 통과 풀 기반 고정 신뢰도 (ML 예측보다 낮음)
                    'source': 'FilterPool',
                    'filter_status': 'passed',
                    'in_pool': True
                })
                stats['from_pool'] += 1
                logger.info(f"필터 풀에서 선택: {sorted(numbers)}")

    # 4. 그래도 부족하면 비상 생성
    if len(final_predictions) < num_sets:
        logger.warning(f"목표 수({num_sets})에 미달. 비상 생성 모드 활성화.")
        final_predictions.extend(_generate_emergency_predictions(
            filter_manager, db_manager, num_sets - len(final_predictions)
        ))

    # 통계 출력
    logger.info("=" * 60)
    logger.info("예측 생성 통계:")
    logger.info(f"  ML 시도: {stats['total_attempts']}")
    logger.info(f"  ML 성공: {stats['ml_success']}")
    logger.info(f"  ML 완화: {stats['ml_relaxed']}")
    logger.info(f"  ML 실패: {stats['ml_failed']}")
    logger.info(f"  풀에서 선택: {stats['from_pool']}")
    logger.info(f"  최종 생성: {len(final_predictions)}")
    logger.info("=" * 60)

    return final_predictions[:num_sets]


def _process_ml_predictions(ml_predictions):
    """ML 예측 처리 및 정규화"""
    all_predictions = []

    if isinstance(ml_predictions, list):
        all_predictions = ml_predictions[:15]
    elif isinstance(ml_predictions, dict):
        for model_name, predictions in ml_predictions.items():
            if predictions:
                for pred in predictions[:3]:
                    pred_copy = pred.copy()
                    pred_copy['model'] = model_name
                    all_predictions.append(pred_copy)

    # 신뢰도 순 정렬
    all_predictions.sort(key=lambda x: x.get('confidence', 0), reverse=True)

    # 50% 이상 신뢰도만 선택 (최소 5개 보장)
    high_confidence = [p for p in all_predictions if p.get('confidence', 0) >= 0.50]
    if len(high_confidence) < 5:
        # 80% 미만이지만 상위 예측 추가
        remaining = all_predictions[len(high_confidence):5]
        high_confidence.extend(remaining)

    return high_confidence[:10]  # 최대 10개까지만 반환


def _is_duplicate(numbers: List[int], existing: List[Dict]) -> bool:
    """중복 체크"""
    numbers_set = set(sorted(numbers))
    for pred in existing:
        if set(pred['numbers']) == numbers_set:
            return True
    return False


def _generate_emergency_pool(filter_manager, db_manager, size: int) -> List[str]:
    """비상 상황용 필터링 풀 생성"""
    logger = logging.getLogger(__name__)
    emergency_pool = []

    try:
        # 모든 가능한 조합 생성 (샘플)
        from itertools import combinations
        all_numbers = list(range(1, 46))

        # 무작위 샘플링으로 후보 생성
        for _ in range(size * 10):  # 충분한 후보 생성
            numbers = sorted(random.sample(all_numbers, 6))
            combo_str = ','.join(map(str, numbers))

            # 기본 필터만 적용 (중요 필터만)
            if _passes_basic_filters(numbers):
                emergency_pool.append(combo_str)

            if len(emergency_pool) >= size:
                break

    except Exception as e:
        logger.error(f"비상 풀 생성 실패: {e}")

    return emergency_pool


def _passes_basic_filters(numbers: List[int]) -> bool:
    """기본 필터 통과 여부"""
    # 홀짝 비율
    odd_count = sum(1 for n in numbers if n % 2 == 1)
    if odd_count == 0 or odd_count == 6:
        return False

    # 합계 범위
    total = sum(numbers)
    if total < 100 or total > 200:
        return False

    # 연속 번호
    sorted_nums = sorted(numbers)
    consecutive_count = 0
    for i in range(len(sorted_nums) - 1):
        if sorted_nums[i+1] - sorted_nums[i] == 1:
            consecutive_count += 1
            if consecutive_count >= 3:  # 4개 이상 연속
                return False

    return True


def _generate_emergency_predictions(filter_manager, db_manager, needed: int) -> List[Dict]:
    """비상 예측 생성"""
    logger = logging.getLogger(__name__)
    emergency_predictions = []

    for _ in range(needed):
        # 기본 패턴 기반 생성
        numbers = _generate_balanced_numbers()
        emergency_predictions.append({
            'numbers': sorted(numbers),
            'confidence': 0.3,
            'source': 'Emergency',
            'filter_status': 'emergency'
        })
        logger.warning(f"비상 생성: {sorted(numbers)}")

    return emergency_predictions


def _generate_balanced_numbers() -> List[int]:
    """균형잡힌 번호 생성"""
    numbers = []

    # 구간별 분포
    sections = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 45)]
    section_counts = [1, 1, 2, 1, 1]  # 각 구간에서 선택할 개수

    for (start, end), count in zip(sections, section_counts):
        section_numbers = list(range(start, end + 1))
        selected = random.sample(section_numbers, min(count, len(section_numbers)))
        numbers.extend(selected)

    # 6개 맞추기
    while len(numbers) < 6:
        new_num = random.randint(1, 45)
        if new_num not in numbers:
            numbers.append(new_num)

    return numbers[:6]