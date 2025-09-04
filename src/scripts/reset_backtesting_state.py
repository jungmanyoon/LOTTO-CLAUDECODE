"""
백테스팅 상태 리셋 스크립트
- 개선 이력을 초기화하여 새로운 개선 사이클 시작
"""

import json
import os
from datetime import datetime

def reset_backtesting_state():
    """백테스팅 상태 리셋"""
    state_file = 'data/auto_improvement_state.json'
    
    if os.path.exists(state_file):
        # 기존 상태 읽기
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        # 백업 생성
        backup_file = f'auto_improvement_state_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"백업 생성: {backup_file}")
        
        # 개선 이력만 리셋 (백테스팅 카운트는 유지)
        state['improvement_history'] = []
        state['last_update'] = datetime.now().isoformat()
        
        # 저장
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        print(f"백테스팅 상태 리셋 완료!")
        print(f"- 총 백테스팅 횟수: {state['total_backtest_count']}")
        print(f"- 개선 이력: 초기화됨")
        print(f"- 이제 백테스팅이 다시 실행됩니다.")
    else:
        print("상태 파일이 없습니다.")

if __name__ == "__main__":
    reset_backtesting_state()