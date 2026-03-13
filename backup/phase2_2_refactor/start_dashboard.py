"""
통합 대시보드 시작 스크립트
- 항상 향상된 대시보드(enhanced_dashboard)만 실행
- 포트 5001 사용
"""

import sys
import os
import time
import threading
import webbrowser

# 경로 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def start_enhanced_dashboard(port=5001, auto_open=True):
    """향상된 대시보드 시작"""
    try:
        # 향상된 대시보드만 임포트 (web_dashboard는 사용하지 않음)
        from src.scripts.enhanced_dashboard import run_enhanced_dashboard
        
        print("\n" + "="*70)
        print("Enhanced Lotto Prediction Dashboard")
        print("="*70)
        print(f"\n[INFO] Starting enhanced dashboard on port {port}...")
        print(f"[INFO] URL: http://127.0.0.1:{port}")
        print("[INFO] Press Ctrl+C to stop.\n")
        
        # 브라우저 자동 열기
        if auto_open:
            def open_browser():
                time.sleep(2)
                webbrowser.open(f"http://127.0.0.1:{port}")
            
            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()
        
        # 향상된 대시보드 실행
        run_enhanced_dashboard(host='127.0.0.1', port=port, debug=False)
        
    except ImportError as e:
        print(f"\n[ERROR] Failed to import enhanced dashboard: {e}")
        print("[INFO] Please check if enhanced_dashboard.py exists in src/scripts/")
    except KeyboardInterrupt:
        print("\n\n[INFO] Dashboard stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] Error running dashboard: {e}")
        import traceback
        traceback.print_exc()

def main():
    """메인 실행 함수"""
    # 명령줄 인자 처리
    import argparse
    parser = argparse.ArgumentParser(description='Start Enhanced Lotto Dashboard')
    parser.add_argument('--port', type=int, default=5001, help='Port number (default: 5001)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    args = parser.parse_args()
    
    # 향상된 대시보드 시작
    start_enhanced_dashboard(port=args.port, auto_open=not args.no_browser)

if __name__ == '__main__':
    main()