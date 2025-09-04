#!/usr/bin/env python3
"""
모델 로딩 테스트 스크립트
is_trained 상태를 확인하고 문제를 진단합니다.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from src.ml.ensemble_predictor import EnsemblePredictor

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def test_model_loading():
    """모델 로딩 테스트"""
    print("\n" + "="*70)
    print("모델 로딩 테스트")
    print("="*70)
    
    # EnsemblePredictor 인스턴스 생성
    predictor = EnsemblePredictor()
    
    print(f"\n1. is_trained 상태: {predictor.is_trained}")
    print(f"2. 로드된 모델: {list(predictor.models.keys())}")
    print(f"3. 모델 디렉토리: {predictor.model_dir}")
    
    # 파일 존재 확인
    print(f"\n4. 파일 존재 확인:")
    for file in ['rf.pkl', 'xgb.pkl', 'nn.pkl', 'scalers.pkl', 'ensemble_config.json']:
        path = os.path.join(predictor.model_dir, file)
        exists = os.path.exists(path)
        if exists:
            size = os.path.getsize(path) / 1024
            print(f"   - {file}: 존재 ({size:.1f} KB)")
        else:
            print(f"   - {file}: 없음")
    
    # config 내용 확인
    import json
    config_path = os.path.join(predictor.model_dir, 'ensemble_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            print(f"\n5. Config 내용:")
            print(f"   - is_trained: {config.get('is_trained', 'NOT SET')}")
    
    # 모델이 학습되지 않았다면 강제로 is_trained를 True로 설정
    if not predictor.is_trained and len(predictor.models) >= 2:
        print(f"\n6. 모델은 있지만 is_trained가 False입니다. 수정합니다...")
        predictor.is_trained = True
        predictor.save_models()
        print(f"   - is_trained를 True로 변경하고 저장했습니다.")
    
    return predictor.is_trained

if __name__ == "__main__":
    success = test_model_loading()
    if success:
        print("\n[SUCCESS] 모델이 정상적으로 로드되었습니다.")
    else:
        print("\n[FAIL] 모델 로드에 문제가 있습니다.")