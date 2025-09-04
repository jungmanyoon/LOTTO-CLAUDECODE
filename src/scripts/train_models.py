#!/usr/bin/env python3
"""
모델 학습 스크립트
모든 ML 모델을 학습시키고 저장합니다.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from src.core.db_manager import DatabaseManager
from src.ml.ensemble_predictor import EnsemblePredictor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def train_ensemble_model():
    """앙상블 모델 학습"""
    print("\n" + "="*50)
    print("앙상블 모델 학습 시작")
    print("="*50)
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 마지막 회차 확인
        last_round = db_manager.get_last_round()
        print(f"마지막 회차: {last_round}")
        
        # 최근 200회차 데이터 가져오기
        recent_data = db_manager.get_recent_numbers(200)
        print(f"학습 데이터: {len(recent_data)}회차")
        
        if len(recent_data) < 50:
            print("[WARNING] 학습 데이터가 부족합니다 (최소 50회차 필요)")
            return False
        
        # 앙상블 예측기 초기화
        predictor = EnsemblePredictor()
        
        # 모델 학습
        print("\n모델 학습 중...")
        # recent_data는 (회차, 번호문자열, 날짜) 튜플의 리스트
        # 번호 문자열만 추출
        numbers_only = [data[1] for data in recent_data]
        predictor.train(numbers_only)
        
        # 모델 저장
        print("모델 저장 중...")
        predictor.save_models()
        
        print("\n[SUCCESS] 모델 학습 완료!")
        print(f"학습된 모델: {list(predictor.models.keys())}")
        print(f"학습 상태: {predictor.is_trained}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 모델 학습 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("ML 모델 학습 프로그램")
    print("="*70)
    
    success = train_ensemble_model()
    
    if success:
        print("\n" + "="*70)
        print("[SUCCESS] 모든 모델이 성공적으로 학습되었습니다!")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("[FAIL] 모델 학습에 실패했습니다.")
        print("="*70)
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)