"""
대시보드 테스트 및 실행
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.scripts.dashboard import LottoDashboard

def test_dashboard():
    """대시보드 테스트 실행"""
    dashboard = LottoDashboard()
    
    print("\n" + "="*60)
    print("로또 예측 시스템 대시보드 - 현재 상태")
    print("="*60)
    
    # 한 번만 실행하여 현재 상태 확인
    dashboard.run_once()
    
    print("\n[INFO] 대시보드가 정상적으로 실행되었습니다.")
    print("[INFO] 실시간 모니터링을 원하시면 'python src/scripts/dashboard.py'를 실행하세요.")
    
    return True

if __name__ == "__main__":
    test_dashboard()