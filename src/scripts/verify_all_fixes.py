#!/usr/bin/env python3
"""
모든 수정사항 검증 스크립트
1. 최소 개선율 설정 확인
2. WAL 모드 활성화 확인
3. 모델 학습 상태 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import json
from pathlib import Path

def check_min_improvement_rate():
    """최소 개선율 설정 확인"""
    print("\n" + "="*70)
    print("1. 최소 개선율 설정 확인")
    print("="*70)
    
    # auto_improvement_state.json 파일 확인
    state_file = "data/auto_improvement_state.json"
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            config = state.get('config', {})
            min_rate = config.get('min_improvement_rate', 0.05)
            print(f"[OK] 최소 개선율: {min_rate*100:.1f}% (기대값: 0.1%)")
            if min_rate == 0.001:
                print("   [OK] 0.1%로 올바르게 설정됨")
            else:
                print(f"   [WARNING] 기대값과 다름: {min_rate} vs 0.001")
    else:
        print("[FAIL] auto_improvement_state.json 파일이 없습니다")
        print("   새로 생성될 때 0.1%로 설정됩니다")
    
    # 소스 코드에서 확인
    manager_file = "src/optimization/auto_improvement_manager.py"
    if os.path.exists(manager_file):
        with open(manager_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "'min_improvement_rate': 0.001" in content:
                print("[OK] 소스 코드에 0.001 (0.1%) 설정 확인")
            else:
                print("[FAIL] 소스 코드에 0.001 설정이 없음")

def check_wal_mode():
    """WAL 모드 활성화 확인"""
    print("\n" + "="*70)
    print("2. 데이터베이스 WAL 모드 확인")
    print("="*70)
    
    # 모든 데이터베이스 파일 찾기
    db_files = []
    
    # 메인 데이터베이스
    main_dbs = [
        'data/combinations.db',
        'data/lotto_numbers.db',
        'data/patterns.db'
    ]
    
    for db in main_dbs:
        if os.path.exists(db):
            db_files.append(db)
    
    # 필터 데이터베이스
    filters_dir = 'data/filters'
    if os.path.exists(filters_dir):
        for file in os.listdir(filters_dir):
            if file.endswith('.db'):
                db_files.append(os.path.join(filters_dir, file))
    
    print(f"총 {len(db_files)}개 데이터베이스 확인")
    
    wal_count = 0
    for db_path in db_files:
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            
            if mode == 'wal':
                print(f"  [OK] {os.path.basename(db_path)}: WAL 모드")
                wal_count += 1
            else:
                print(f"  [FAIL] {os.path.basename(db_path)}: {mode} 모드")
            
            conn.close()
        except Exception as e:
            print(f"  [WARN] {os.path.basename(db_path)}: 확인 실패 - {e}")
    
    print(f"\n결과: {wal_count}/{len(db_files)} 데이터베이스가 WAL 모드")

def check_model_training():
    """모델 학습 상태 확인"""
    print("\n" + "="*70)
    print("3. ML 모델 학습 상태 확인")
    print("="*70)
    
    # 앙상블 모델 파일 확인 (새로운 경로)
    ensemble_dir = "models/ensemble"
    if os.path.exists(ensemble_dir):
        print("앙상블 모델 (models/ensemble/):")
        model_files = {
            'random_forest': 'rf.pkl',
            'xgboost': 'xgb.pkl',
            'neural_network': 'nn.pkl',
            'scalers': 'scalers.pkl',
            'config': 'ensemble_config.json'
        }
        
        for model_name, file_name in model_files.items():
            file_path = os.path.join(ensemble_dir, file_name)
            if os.path.exists(file_path):
                file_stat = os.stat(file_path)
                size_kb = file_stat.st_size / 1024
                print(f"  [OK] {model_name}: {size_kb:.1f} KB")
            else:
                print(f"  [FAIL] {model_name}: 파일 없음")
    
    # LSTM 모델 확인 (기존 경로)
    lstm_file = "models/lstm_lotto_predictor.h5"
    if os.path.exists(lstm_file):
        file_stat = os.stat(lstm_file)
        size_kb = file_stat.st_size / 1024
        print(f"\nLSTM 모델:\n  [OK] lstm: {size_kb:.1f} KB")
    else:
        print(f"\nLSTM 모델:\n  [FAIL] lstm: 파일 없음")

def check_database_connections():
    """데이터베이스 연결 테스트"""
    print("\n" + "="*70)
    print("4. 데이터베이스 연결 테스트")
    print("="*70)
    
    try:
        from src.core.specialized_databases import FilterDB
        
        # FilterDB 연결 테스트
        filter_db = FilterDB('data/filters/test_connection.db')
        
        # 테스트 쿼리 실행
        with filter_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result and result[0] == 1:
                print("[OK] FilterDB 연결 테스트 성공")
            else:
                print("[FAIL] FilterDB 연결 테스트 실패")
        
        # 정리
        os.remove('data/filters/test_connection.db')
        
    except Exception as e:
        print(f"[FAIL] 데이터베이스 연결 테스트 실패: {e}")

def main():
    """메인 실행 함수"""
    print("\n" + "="*70)
    print("모든 수정사항 검증 시작")
    print("="*70)
    
    # 1. 최소 개선율 확인
    check_min_improvement_rate()
    
    # 2. WAL 모드 확인
    check_wal_mode()
    
    # 3. 모델 학습 상태 확인
    check_model_training()
    
    # 4. 데이터베이스 연결 테스트
    check_database_connections()
    
    print("\n" + "="*70)
    print("검증 완료")
    print("="*70)
    print("\n권장사항:")
    print("1. WAL 모드가 아닌 DB가 있다면: python src/scripts/fix_db_lock_issue.py")
    print("2. 모델이 없다면: python src/scripts/train_models.py")
    print("3. 최소 개선율이 0.1%가 아니라면: main.py를 한 번 실행")

if __name__ == "__main__":
    main()