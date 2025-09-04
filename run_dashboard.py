"""
향상된 로또 예측 대시보드 실행 스크립트
"""

import sys
import os
import webbrowser
import time
import threading

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from src.scripts.enhanced_dashboard_v2 import run_enhanced_dashboard_v2 as run_dashboard_func
except ImportError:
    from src.scripts.enhanced_dashboard import run_enhanced_dashboard as run_dashboard_func

def open_browser(url, delay=2):
    """지정된 시간 후 브라우저 열기"""
    time.sleep(delay)
    webbrowser.open(url)

def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("Enhanced Lotto Prediction Dashboard v2 Starting...")
    print("="*70)
    
    # 브라우저 자동 열기 (2초 후)
    url = "http://127.0.0.1:5001"
    browser_thread = threading.Thread(target=open_browser, args=(url,))
    browser_thread.daemon = True
    browser_thread.start()
    
    # 대시보드 실행
    try:
        run_dashboard_func(host='127.0.0.1', port=5001, debug=False)
    except KeyboardInterrupt:
        print("\n\n[INFO] 대시보드를 종료합니다...")
        print("="*70)
    except Exception as e:
        print(f"\n[ERROR] 오류 발생: {e}")
        print("="*70)

if __name__ == '__main__':
    main()