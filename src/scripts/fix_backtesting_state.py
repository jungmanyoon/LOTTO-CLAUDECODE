#!/usr/bin/env python
"""
백테스팅 상태 수정 스크립트
- auto_improvement_state.json의 20회 멈춤 문제 해결
- 잘못된 성능 데이터 수정
"""
import json
import os
import sys
from datetime import datetime

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

def fix_auto_improvement_state():
    """auto_improvement_state.json 수정"""
    state_file = os.path.join(project_root, 'data', 'auto_improvement_state.json')
    
    if not os.path.exists(state_file):
        print(f"파일을 찾을 수 없음: {state_file}")
        return False
    
    # 현재 상태 로드
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    print(f"현재 백테스팅 횟수: {state['total_backtest_count']}")
    
    # 마지막 백테스트 결과가 모두 0인 문제 수정
    if state['total_backtest_count'] == 20:
        last_history = state['improvement_history'][-1]
        if last_history['new_performance']['overall'] == 0.0:
            print("마지막 백테스트(20회차) 성능이 0.0으로 기록되어 있음")
            
            # 20회차 제거하고 19회로 롤백
            state['improvement_history'] = state['improvement_history'][:-1]
            state['total_backtest_count'] = 19
            
            # 현재 성능을 이전 유효한 값으로 복원
            if len(state['improvement_history']) > 0:
                last_valid = state['improvement_history'][-1]
                state['current_performance'] = last_valid['new_performance'].copy()
            
            print(f"백테스팅 횟수를 19회로 롤백")
    
    # 백업 생성
    backup_file = state_file.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"백업 생성: {backup_file}")
    
    # 수정된 상태 저장
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print(f"수정 완료: 백테스팅 횟수 = {state['total_backtest_count']}")
    return True

def sync_adjustment_state():
    """auto_adjustment_state.json과 동기화"""
    adjustment_file = os.path.join(project_root, 'data', 'auto_adjustment_state.json')
    improvement_file = os.path.join(project_root, 'data', 'auto_improvement_state.json')
    
    if os.path.exists(adjustment_file):
        with open(adjustment_file, 'r', encoding='utf-8') as f:
            adj_state = json.load(f)
        
        print(f"auto_adjustment_state.json: {adj_state['total_backtesting_count']}회")
    
    if os.path.exists(improvement_file):
        with open(improvement_file, 'r', encoding='utf-8') as f:
            imp_state = json.load(f)
        
        print(f"auto_improvement_state.json: {imp_state['total_backtest_count']}회")
    
    # 두 시스템 간 불일치 경고
    if os.path.exists(adjustment_file) and os.path.exists(improvement_file):
        adj_count = adj_state.get('total_backtesting_count', 0)
        imp_count = imp_state.get('total_backtest_count', 0)
        
        if adj_count != imp_count:
            print(f"\n⚠️ 경고: 두 시스템의 백테스팅 횟수가 다릅니다!")
            print(f"  - auto_adjustment: {adj_count}회")
            print(f"  - auto_improvement: {imp_count}회")
            print(f"  → main.py에서는 auto_adjustment_system을 사용하는 것이 맞습니다.")

def main():
    print("="*60)
    print("백테스팅 상태 수정")
    print("="*60)
    
    # 1. auto_improvement_state.json 수정
    print("\n[1] auto_improvement_state.json 수정")
    fix_auto_improvement_state()
    
    # 2. 상태 동기화 확인
    print("\n[2] 시스템 간 상태 확인")
    sync_adjustment_state()
    
    print("\n" + "="*60)
    print("권장사항:")
    print("1. main.py에서는 auto_adjustment_system만 사용")
    print("2. auto_improvement_manager는 별도 테스트용으로만 사용")
    print("3. 혼란을 피하기 위해 하나의 시스템만 사용하세요")
    print("="*60)

if __name__ == "__main__":
    main()