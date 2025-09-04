#!/usr/bin/env python3
"""
현재 발생한 에러들 수정 테스트 스크립트
1. EnsemblePredictor predict 메서드 에러
2. 데이터베이스 락 문제
3. 모델 학습 상태 경고
"""
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import logging
from src.core.db_manager import DatabaseManager
from src.ml.ensemble_predictor import EnsemblePredictor
from src.ml.auto_ml_optimizer import AutoMLOptimizer

def test_ensemble_predictor():
    """EnsemblePredictor predict 메서드 수정 테스트"""
    print("\n[테스트 1] EnsemblePredictor predict 메서드 수정 테스트")
    try:
        db_manager = DatabaseManager()
        ensemble = EnsemblePredictor()
        
        # 최근 번호 가져오기
        recent_numbers = db_manager.get_recent_numbers(10)
        recent_numbers_str = [rn[1] for rn in recent_numbers[:5]]
        
        # predict_next_numbers 메서드 테스트
        predictions = ensemble.predict_next_numbers(recent_numbers_str, num_predictions=1)
        
        if predictions:
            print("[PASS] predict_next_numbers 메서드 정상 작동")
            print(f"   예측 결과: {predictions[0]['numbers']}")
        else:
            print("[WARN] 예측 결과가 비어있음")
            
    except AttributeError as e:
        if 'predict' in str(e):
            print(f"[FAIL] predict 메서드 에러 여전히 존재: {e}")
        else:
            print(f"[FAIL] 다른 AttributeError: {e}")
    except Exception as e:
        print(f"[FAIL] 예상치 못한 에러: {e}")

def test_auto_ml_optimizer():
    """AutoMLOptimizer _quick_validation 수정 테스트"""
    print("\n[테스트 2] AutoMLOptimizer _quick_validation 수정 테스트")
    try:
        db_manager = DatabaseManager()
        optimizer = AutoMLOptimizer(db_manager)
        
        # EnsemblePredictor로 테스트
        ensemble = EnsemblePredictor()
        
        # _quick_validation 호출
        score = optimizer._quick_validation(ensemble)
        
        print(f"[PASS] _quick_validation 정상 실행: 점수 = {score}")
        
    except AttributeError as e:
        if 'predict' in str(e):
            print(f"[FAIL] predict 메서드 에러: {e}")
        else:
            print(f"[FAIL] 다른 AttributeError: {e}")
    except Exception as e:
        print(f"[FAIL] 예상치 못한 에러: {e}")

def test_database_locks():
    """데이터베이스 락 문제 테스트"""
    print("\n[테스트 3] 데이터베이스 락 문제 테스트")
    try:
        # 여러 번 데이터베이스 접근 시도
        for i in range(5):
            db_manager = DatabaseManager()
            recent = db_manager.get_recent_numbers(1)
            print(f"   시도 {i+1}: 최근 회차 = {recent[0][0] if recent else 'None'}")
        
        print("[PASS] 데이터베이스 락 문제 없음")
        
    except Exception as e:
        if 'locked' in str(e):
            print(f"[FAIL] 데이터베이스 락 에러: {e}")
        else:
            print(f"[FAIL] 다른 에러: {e}")

def test_model_training_status():
    """모델 학습 상태 테스트"""
    print("\n[테스트 4] 모델 학습 상태 테스트")
    try:
        ensemble = EnsemblePredictor()
        
        print(f"   모델 학습 상태: {ensemble.is_trained}")
        print(f"   로드된 모델: {list(ensemble.models.keys())}")
        
        if not ensemble.is_trained:
            print("[WARN] 모델이 학습되지 않은 상태")
            print("   모델 학습을 시작하려면 충분한 데이터가 필요합니다")
        else:
            print("[PASS] 모델이 학습된 상태")
            
    except Exception as e:
        print(f"[FAIL] 에러 발생: {e}")

def main():
    """메인 테스트 실행"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
    )
    
    print("="*60)
    print("현재 에러 수정 사항 테스트 시작")
    print("="*60)
    
    # 각 테스트 실행
    test_ensemble_predictor()
    test_auto_ml_optimizer()
    test_database_locks()
    test_model_training_status()
    
    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)

if __name__ == "__main__":
    main()