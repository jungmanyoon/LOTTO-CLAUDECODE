"""
간단한 강제 백테스팅 스크립트
"""
import json
from datetime import datetime

# 상태 파일 직접 수정
state_file = 'data/auto_improvement_state.json'

# 상태 읽기
with open(state_file, 'r', encoding='utf-8') as f:
    state = json.load(f)

# 백테스팅 횟수 증가
old_count = state['total_backtest_count']
state['total_backtest_count'] += 1
state['last_update'] = datetime.now().isoformat()

# 저장
with open(state_file, 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(f"백테스팅 횟수: {old_count} → {state['total_backtest_count']}")