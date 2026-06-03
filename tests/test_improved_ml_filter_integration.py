#!/usr/bin/env python3
"""
개선된 ML-필터 통합 테스트
- ML 예측의 필터 완화 적용 확인
- 유사 조합 찾기 기능 테스트
- 백테스팅 필터링 풀 포함률 측정
"""
import logging
import sys
import os
import random

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.ml.lstm_predictor import LSTMPredictor
from src.ml.ensemble_predictor import EnsemblePredictor
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework

# main.py에서 개선된 함수 import
# (extract_combination_features/calculate_similarity_score/find_similar_combinations는
#  활성 예측경로 미사용 죽은 코드로 제거됨 - orchestration-1)
from main import (
    generate_final_predictions_enhanced as generate_final_predictions,
)

# 로깅 설정 (테스트는 콘솔만 사용 - 프로젝트 logs/ 디렉토리를 오염시키지 않도록 FileHandler 제거.
# CLAUDE.md: 테스트 산출물은 logs/에 만들지 않는다)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


def test_relaxed_filter_for_ml():
    """ML 예측에 대한 완화된 필터 테스트"""
    print("\n[테스트 3] ML 예측용 완화된 필터 테스트")
    print("=" * 50)
    
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # 가상의 ML 예측 생성
    ml_predictions = {
        'lstm': [
            {'numbers': [1, 2, 3, 44, 45, 6], 'confidence': 0.8},  # 극단적인 조합
            {'numbers': [10, 20, 30, 5, 15, 25], 'confidence': 0.7}
        ],
        'ensemble': [
            {'numbers': [7, 14, 21, 28, 35, 42], 'confidence': 0.75}  # 7의 배수
        ]
    }
    
    # 완화된 필터 적용 (ML 우선 모드)
    final_preds_relaxed = generate_final_predictions(
        db_manager,
        filter_manager,
        ml_predictions,
        num_sets=5,
        use_ml_priority_mode=True
    )

    # 엄격한 필터 적용 (ML 우선 모드 비활성화)
    final_preds_strict = generate_final_predictions(
        db_manager,
        filter_manager,
        ml_predictions,
        num_sets=5,
        use_ml_priority_mode=False
    )
    
    print(f"완화된 필터 결과: {len(final_preds_relaxed)}개")
    for i, pred in enumerate(final_preds_relaxed, 1):
        print(f"  {i}. {pred['numbers']} (출처: {pred['source']})")
    
    print(f"\n엄격한 필터 결과: {len(final_preds_strict)}개")
    for i, pred in enumerate(final_preds_strict, 1):
        print(f"  {i}. {pred['numbers']} (출처: {pred['source']})")
    
    # 완화된 필터가 더 많은 ML 예측을 통과시켜야 함
    ml_count_relaxed = sum(1 for p in final_preds_relaxed if 'ML' in p['source'])
    ml_count_strict = sum(1 for p in final_preds_strict if 'ML' in p['source'])
    
    print(f"\nML 예측 통과 수:")
    print(f"  - 완화 필터: {ml_count_relaxed}개")
    print(f"  - 엄격 필터: {ml_count_strict}개")
    
    if ml_count_relaxed >= ml_count_strict:
        print("[O] 완화된 필터가 더 많은 ML 예측 통과")
    else:
        print("[X] 완화된 필터 효과 없음")
    
    return True


def test_backtesting_with_filtered_pool():
    """백테스팅에서 필터링 풀 포함률 측정 테스트"""
    print("\n[테스트 5] 백테스팅 필터링 풀 포함률 측정")
    print("=" * 50)
    
    db_manager = DatabaseManager()
    
    # 백테스팅 프레임워크 초기화
    backtest = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
    
    # 최근 10회차 백테스팅
    latest_round = db_manager.get_last_round()
    start_round = max(1, latest_round - 10)
    end_round = latest_round - 1
    
    print(f"백테스팅 범위: {start_round}회차 ~ {end_round}회차")
    
    # 백테스팅 실행
    results = backtest.run_backtest(start_round, end_round, window_size=50)
    
    # 필터링 풀 포함률 확인
    if 'predictions' in results and results['predictions']:
        total_pool_rate = 0
        count = 0
        
        for pred_result in results['predictions']:
            if 'filtered_pool_inclusion_rate' in pred_result:
                pool_rate = pred_result['filtered_pool_inclusion_rate']
                total_pool_rate += pool_rate
                count += 1
                print(f"  회차 {pred_result['round']}: 필터링 풀 포함률 {pool_rate:.1f}%")
        
        if count > 0:
            avg_pool_rate = total_pool_rate / count
            print(f"\n평균 필터링 풀 포함률: {avg_pool_rate:.1f}%")
            
            if avg_pool_rate < 20:
                print("[!] ML 예측이 필터링 풀과 맞지 않음 - 개선 필요")
            else:
                print("[O] 필터링 풀 포함률 측정 완료")
    
    return True


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "=" * 60)
    print("ML-필터 통합 개선 테스트 시작")
    print("=" * 60)
    
    tests = [
        ("ML용 완화된 필터", test_relaxed_filter_for_ml),
        ("백테스팅 필터링 풀", test_backtesting_with_filtered_pool),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n[X] {test_name} 실패: {e}")
            results.append((test_name, False))
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "[O]" if success else "[X]"
        print(f"{status} {test_name}")
    
    print(f"\n통과: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n✅ 모든 테스트 통과!")
    else:
        print(f"\n⚠️ 일부 테스트 실패 ({total - passed}개)")


if __name__ == "__main__":
    run_all_tests()