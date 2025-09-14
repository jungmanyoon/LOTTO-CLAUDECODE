#!/usr/bin/env python3
"""
ML 예측과 필터링 풀 통합 개선사항 테스트
"""

import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from main import generate_final_predictions, combine_ml_predictions

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def create_test_ml_predictions():
    """테스트용 ML 예측 데이터 생성"""
    return {
        'ensemble': [
            {'numbers': [1, 5, 12, 23, 34, 45], 'confidence': 0.85, 'model': 'ensemble'},
            {'numbers': [3, 7, 15, 25, 36, 42], 'confidence': 0.78, 'model': 'ensemble'},
            {'numbers': [2, 9, 18, 27, 35, 44], 'confidence': 0.72, 'model': 'ensemble'}
        ],
        'lstm': [
            {'numbers': [4, 8, 16, 24, 33, 41], 'confidence': 0.82, 'model': 'lstm'},
            {'numbers': [6, 11, 19, 26, 37, 43], 'confidence': 0.75, 'model': 'lstm'},
            {'numbers': [1, 10, 20, 28, 38, 45], 'confidence': 0.68, 'model': 'lstm'}
        ],
        'monte_carlo': [
            {'numbers': [5, 13, 21, 29, 32, 40], 'confidence': 0.71, 'model': 'monte_carlo'},
            {'numbers': [7, 14, 22, 30, 39, 42], 'confidence': 0.66, 'model': 'monte_carlo'}
        ]
    }

def test_combine_ml_predictions():
    """Combined 예측 생성 테스트"""
    logger.info("=== Combined 예측 생성 테스트 ===")

    test_predictions = create_test_ml_predictions()

    combined_predictions = combine_ml_predictions(
        lstm_predictions=test_predictions['lstm'],
        ensemble_predictions=test_predictions['ensemble'],
        mc_predictions=test_predictions['monte_carlo'],
        num_combined=5
    )

    logger.info(f"생성된 Combined 예측 수: {len(combined_predictions)}")
    for i, pred in enumerate(combined_predictions):
        logger.info(f"  {i+1}. {pred['numbers']} (신뢰도: {pred['confidence']:.3f}, 전략: {pred['strategy']})")

    return combined_predictions

def test_ml_filter_integration():
    """ML 예측과 필터링 통합 테스트"""
    logger.info("=== ML 예측과 필터링 통합 테스트 ===")

    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()

        # 필터 매니저 초기화
        filter_manager = FilterManager(db_manager)

        # 테스트 ML 예측 데이터
        test_predictions = create_test_ml_predictions()

        # Combined 예측 생성
        combined_predictions = combine_ml_predictions(
            lstm_predictions=test_predictions['lstm'],
            ensemble_predictions=test_predictions['ensemble'],
            mc_predictions=test_predictions['monte_carlo'],
            num_combined=3
        )

        # 모든 ML 예측을 리스트 형태로 준비
        all_ml_predictions = []

        # 기존 모델 예측들 추가
        for model_name, predictions in test_predictions.items():
            all_ml_predictions.extend(predictions)

        # Combined 예측 추가
        for pred in combined_predictions:
            pred_copy = pred.copy()
            pred_copy['model'] = 'combined'
            all_ml_predictions.append(pred_copy)

        logger.info(f"총 ML 예측 수: {len(all_ml_predictions)}")

        # 최종 예측 생성 (개선된 로직 테스트)
        final_predictions = generate_final_predictions(
            db_manager=db_manager,
            filter_manager=filter_manager,
            ml_predictions=all_ml_predictions,
            num_sets=5,
            use_relaxed_filter=True
        )

        logger.info(f"\n=== 최종 예측 결과 ===")
        logger.info(f"생성된 최종 예측 수: {len(final_predictions)}")

        # 소스별 통계
        source_stats = {}
        for pred in final_predictions:
            source = pred['source']
            if source not in source_stats:
                source_stats[source] = 0
            source_stats[source] += 1

        logger.info(f"\n소스별 통계:")
        for source, count in source_stats.items():
            logger.info(f"  {source}: {count}개")

        logger.info(f"\n최종 예측 상세:")
        for i, pred in enumerate(final_predictions):
            logger.info(f"  {i+1}. {pred['numbers']} (신뢰도: {pred['confidence']:.3f}, 소스: {pred['source']})")

        # 성공 지표 계산
        ml_direct_count = sum(1 for pred in final_predictions if pred['source'].startswith('ML/'))
        ml_total_count = sum(1 for pred in final_predictions if pred['source'].startswith('ML'))

        inclusion_rate = (ml_total_count / len(final_predictions)) * 100 if final_predictions else 0
        direct_rate = (ml_direct_count / len(final_predictions)) * 100 if final_predictions else 0

        logger.info(f"\n=== 성능 지표 ===")
        logger.info(f"ML 예측 포함률: {inclusion_rate:.1f}% ({ml_total_count}/{len(final_predictions)})")
        logger.info(f"ML 직접 통과율: {direct_rate:.1f}% ({ml_direct_count}/{len(final_predictions)})")

        # 목표 달성 여부 확인
        target_inclusion_rate = 30.0  # 목표: 30% 이상
        if inclusion_rate >= target_inclusion_rate:
            logger.info(f"✅ 목표 달성! ML 예측 포함률 {inclusion_rate:.1f}% >= {target_inclusion_rate}%")
        else:
            logger.info(f"❌ 목표 미달성. ML 예측 포함률 {inclusion_rate:.1f}% < {target_inclusion_rate}%")

        return final_predictions, inclusion_rate

    except Exception as e:
        logger.error(f"테스트 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None, 0

def main():
    """메인 함수"""
    logger.info("ML 예측과 필터링 풀 통합 개선사항 테스트 시작")

    # 1. Combined 예측 생성 테스트
    combined_predictions = test_combine_ml_predictions()

    print("\n" + "="*60 + "\n")

    # 2. ML-필터 통합 테스트
    final_predictions, inclusion_rate = test_ml_filter_integration()

    print("\n" + "="*60 + "\n")

    if final_predictions:
        logger.info("✅ 모든 테스트 완료!")
        logger.info(f"최종 ML 예측 포함률: {inclusion_rate:.1f}%")

        if inclusion_rate >= 30.0:
            logger.info("🎉 목표 달성! ML 예측의 필터링 풀 포함률이 30% 이상으로 향상되었습니다.")
        else:
            logger.info("⚠️  추가 개선이 필요합니다. 현재 포함률이 목표에 미달합니다.")
    else:
        logger.error("❌ 테스트 실패!")

if __name__ == "__main__":
    main()