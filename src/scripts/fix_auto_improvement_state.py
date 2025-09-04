#!/usr/bin/env python3
"""
자동 개선 시스템 상태 파일 수정 스크립트
누락된 config 키를 추가하여 오류 해결
"""
import json
import os
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def fix_state_file():
    """상태 파일 수정"""
    state_file = "data/auto_improvement_state.json"
    
    if not os.path.exists(state_file):
        print(f"상태 파일이 없습니다: {state_file}")
        return
    
    # 기존 상태 로드
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    print("현재 상태 파일 구조:")
    print(f"- 키: {list(state.keys())}")
    
    # 기본 config 정의
    default_config = {
        'backtest_window_size': 100,
        'min_improvement_rate': 0.05,
        'max_iterations_per_session': 10,
        'performance_threshold': 1.5,
        'auto_save_interval': 1,
    }
    
    # config 확인 및 수정
    if 'config' not in state:
        print("\n⚠️ config 키가 없습니다. 추가합니다.")
        state['config'] = default_config
    else:
        print(f"\n현재 config 키: {list(state['config'].keys())}")
        # 누락된 키 추가
        for key, value in default_config.items():
            if key not in state['config']:
                print(f"  - {key} 추가: {value}")
                state['config'][key] = value
    
    # 백업 생성
    backup_file = state_file + ".backup"
    with open(backup_file, 'w', encoding='utf-8') as f:
        with open(state_file, 'r', encoding='utf-8') as original:
            f.write(original.read())
    print(f"\n백업 생성: {backup_file}")
    
    # 수정된 상태 저장
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 상태 파일 수정 완료: {state_file}")
    print(f"\n수정된 config:")
    for key, value in state['config'].items():
        print(f"  - {key}: {value}")

if __name__ == "__main__":
    fix_state_file()