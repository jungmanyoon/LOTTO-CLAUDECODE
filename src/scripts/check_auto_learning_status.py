#!/usr/bin/env python3
"""
자동 학습 시스템 상태 모니터링 및 복구 스크립트
"""
import json
import os
import sys
import argparse
from datetime import datetime, timedelta
import logging

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def check_auto_learning_status():
    """자동 학습 시스템 상태 확인"""
    print("\n" + "="*60)
    print("[CHECK] 자동 학습 시스템 상태 점검")
    print("="*60)
    
    issues = []
    
    # 1. Auto Improvement 상태 확인
    auto_improve_file = 'data/auto_improvement_state.json'
    if os.path.exists(auto_improve_file):
        with open(auto_improve_file, 'r', encoding='utf-8') as f:
            auto_state = json.load(f)
        
        last_update = datetime.fromisoformat(auto_state.get('last_updated', '2025-01-01T00:00:00'))
        days_since = (datetime.now() - last_update).days
        
        print(f"\n[AUTO IMPROVEMENT]")
        print(f"  - 마지막 업데이트: {last_update.strftime('%Y-%m-%d %H:%M')}")
        print(f"  - 경과 일수: {days_since}일")
        print(f"  - 총 백테스팅 횟수: {auto_state.get('total_backtesting_count', 0)}회")
        
        if days_since > 7:
            issues.append(f"Auto Improvement가 {days_since}일 동안 업데이트되지 않음")
    else:
        issues.append("Auto Improvement 상태 파일이 없음")
    
    # 2. 실시간 학습 상태 확인
    realtime_file = 'data/realtime_learning_state.json'
    if os.path.exists(realtime_file):
        with open(realtime_file, 'r', encoding='utf-8') as f:
            realtime_state = json.load(f)
        
        print(f"\n[REALTIME LEARNING]")
        for model_name, model_data in realtime_state.items():
            if isinstance(model_data, dict) and 'last_update' in model_data:
                last_update = datetime.fromisoformat(model_data['last_update'])
                hours_since = (datetime.now() - last_update).total_seconds() / 3600
                
                print(f"\n  [{model_name.upper()}]")
                print(f"    - 마지막 업데이트: {last_update.strftime('%Y-%m-%d %H:%M')}")
                print(f"    - 경과 시간: {hours_since:.1f}시간")
                print(f"    - 업데이트 횟수: {model_data.get('update_count', 0)}회")
                print(f"    - 버퍼 크기: {len(model_data.get('buffer', []))}개")
                
                if hours_since > 24:
                    issues.append(f"{model_name} 모델이 {hours_since:.0f}시간 동안 업데이트되지 않음")
    else:
        issues.append("실시간 학습 상태 파일이 없음")
    
    # 3. 문제 요약 및 해결책
    print("\n" + "="*60)
    if issues:
        print("[WARNING] 발견된 문제:")
        for issue in issues:
            print(f"   - {issue}")
        
        print("\n[SOLUTION] 해결 방법:")
        print("   1. 자동 학습 재시작: python main.py --auto-improve")
        print("   2. 캐시 정리 후 재시작: python src/scripts/clear_model_cache.py")
        print("   3. 강제 재학습: python main.py --retrain-all")
        
        return False
    else:
        print("[OK] 모든 자동 학습 시스템이 정상 작동 중입니다!")
        return True

def restart_auto_learning():
    """자동 학습 시스템 재시작"""
    print("\n[RESTART] 자동 학습 시스템을 재시작합니다...")
    
    # 상태 파일 초기화
    auto_improve_file = 'data/auto_improvement_state.json'
    realtime_file = 'data/realtime_learning_state.json'
    
    # Auto Improvement 상태 초기화
    if os.path.exists(auto_improve_file):
        with open(auto_improve_file, 'r', encoding='utf-8') as f:
            auto_state = json.load(f)
        
        # 마지막 업데이트 시간만 현재로 변경
        auto_state['last_updated'] = datetime.now().isoformat()
        
        with open(auto_improve_file, 'w', encoding='utf-8') as f:
            json.dump(auto_state, f, indent=2, ensure_ascii=False)
        
        print("[OK] Auto Improvement 상태 초기화 완료")
    
    # 실시간 학습 상태 초기화
    if os.path.exists(realtime_file):
        with open(realtime_file, 'r', encoding='utf-8') as f:
            realtime_state = json.load(f)
        
        # 각 모델의 마지막 업데이트 시간 갱신
        for model_name, model_data in realtime_state.items():
            if isinstance(model_data, dict):
                model_data['last_update'] = datetime.now().isoformat()
                # 버퍼가 비어있으면 초기화
                if not model_data.get('buffer'):
                    model_data['buffer'] = []
        
        with open(realtime_file, 'w', encoding='utf-8') as f:
            json.dump(realtime_state, f, indent=2, ensure_ascii=False)
        
        print("[OK] 실시간 학습 상태 초기화 완료")
    
    print("\n[INFO] 이제 다음 명령어로 시스템을 실행하세요:")
    print("   python main.py --auto-improve")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='자동 학습 시스템 상태 모니터링')
    parser.add_argument('--restart', action='store_true', help='자동 학습 시스템 재시작')
    parser.add_argument('--log', action='store_true', help='상태를 로그 파일에 저장')
    
    args = parser.parse_args()
    
    if args.restart:
        restart_auto_learning()
    else:
        status_ok = check_auto_learning_status()
        
        if args.log:
            # 로그 파일에 상태 저장
            log_file = 'logs/auto_learning_monitor.log'
            os.makedirs('logs', exist_ok=True)
            
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format='%(asctime)s - %(message)s'
            )
            
            if status_ok:
                logging.info("자동 학습 시스템 정상 작동")
            else:
                logging.warning("자동 학습 시스템 문제 발견")
            
            print(f"\n[LOG] 로그가 {log_file}에 저장되었습니다.")
        
        return 0 if status_ok else 1

if __name__ == '__main__':
    sys.exit(main())