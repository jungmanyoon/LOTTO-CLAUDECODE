#!/usr/bin/env python3
"""
ML/AI 통합 테스트 스크립트
main.py의 모든 기능이 정상 작동하는지 확인
"""
import logging
import sys
import os
import subprocess

def test_integration():
    """통합 테스트 실행"""
    print("="*60)
    print("ML/AI 통합 테스트 시작")
    print("="*60)
    
    # 테스트 케이스들
    test_cases = [
        {
            "name": "기본 실행 (모든 ML/AI 기능 포함)",
            "args": ["python", "main.py", "--skip-fetch"],
            "expected": ["ML/AI 분석", "LSTM", "Ensemble", "Monte Carlo", "Bayesian", "Fractal"]
        },
        {
            "name": "ML만 실행",
            "args": ["python", "main.py", "--ml-only", "--skip-fetch", "--skip-patterns"],
            "expected": ["ML/AI 분석", "LSTM", "Ensemble", "Monte Carlo"]
        },
        {
            "name": "ML 제외 실행",
            "args": ["python", "main.py", "--skip-ml", "--skip-fetch"],
            "expected_not": ["ML/AI 분석", "LSTM", "Ensemble"]
        },
        {
            "name": "특정 ML 기능만 실행",
            "args": ["python", "main.py", "--skip-fetch", "--lstm", "--no-ensemble", "--no-monte-carlo", "--no-bayesian", "--no-fractal"],
            "expected": ["LSTM"],
            "expected_not": ["Ensemble", "Monte Carlo", "Bayesian", "Fractal"]
        }
    ]
    
    # 각 테스트 케이스 실행
    for i, test in enumerate(test_cases, 1):
        print(f"\n테스트 {i}: {test['name']}")
        print("-" * 40)
        
        try:
            # 명령 실행
            result = subprocess.run(
                test["args"],
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            
            # 결과 확인
            output = result.stdout + result.stderr
            success = True
            
            # 예상 문자열 확인
            if "expected" in test:
                for expected in test["expected"]:
                    if expected not in output:
                        print(f"❌ '{expected}'를 찾을 수 없습니다.")
                        success = False
                    else:
                        print(f"✅ '{expected}' 확인됨")
            
            # 예상하지 않은 문자열 확인
            if "expected_not" in test:
                for not_expected in test["expected_not"]:
                    if not_expected in output:
                        print(f"❌ '{not_expected}'가 있으면 안됩니다.")
                        success = False
                    else:
                        print(f"✅ '{not_expected}' 없음 확인")
            
            # 에러 확인
            if result.returncode != 0:
                print(f"❌ 프로그램이 에러로 종료됨 (코드: {result.returncode})")
                success = False
                
                # 에러 메시지 출력
                if "error" in output.lower() or "exception" in output.lower():
                    print("\n에러 내용:")
                    for line in output.split('\n'):
                        if 'error' in line.lower() or 'exception' in line.lower():
                            print(f"  {line}")
            
            if success:
                print(f"✅ 테스트 성공!")
            else:
                print(f"❌ 테스트 실패!")
                print("\n전체 출력 (마지막 50줄):")
                print('\n'.join(output.split('\n')[-50:]))
                
        except subprocess.TimeoutExpired:
            print(f"❌ 테스트 타임아웃 (5분 초과)")
        except Exception as e:
            print(f"❌ 테스트 실행 중 오류: {str(e)}")
    
    print("\n" + "="*60)
    print("통합 테스트 완료")
    print("="*60)

def check_dependencies():
    """의존성 확인"""
    print("\n의존성 확인:")
    print("-" * 40)
    
    dependencies = {
        'tensorflow': 'TensorFlow (LSTM)',
        'sklearn': 'scikit-learn (Ensemble)',
        'xgboost': 'XGBoost (Ensemble)',
        'scipy': 'SciPy (통계 분석)',
        'matplotlib': 'Matplotlib (시각화)',
        'seaborn': 'Seaborn (시각화)',
        'pywt': 'PyWavelets (프랙탈 분석)'
    }
    
    missing = []
    for module, name in dependencies.items():
        try:
            __import__(module)
            print(f"✅ {name} 설치됨")
        except ImportError:
            print(f"❌ {name} 미설치")
            missing.append(module)
    
    if missing:
        print(f"\n⚠️ 누락된 패키지: {', '.join(missing)}")
        print(f"설치 명령: pip install {' '.join(missing)}")
    
    return len(missing) == 0

if __name__ == "__main__":
    # 의존성 확인
    if not check_dependencies():
        print("\n⚠️ 일부 기능이 제한될 수 있습니다.")
    
    # 통합 테스트 실행
    test_integration()