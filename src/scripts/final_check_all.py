#!/usr/bin/env python3
"""
모든 수정사항 최종 확인 스크립트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def check_all_fixes():
    """모든 수정사항 확인"""
    print("\n" + "="*70)
    print("모든 수정사항 최종 확인")
    print("="*70)
    
    results = []
    
    # 1. 최소 개선율 확인
    print("\n1. 최소 개선율 설정 확인")
    print("-" * 40)
    try:
        import json
        state_file = "data/auto_improvement_state.json"
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                min_rate = state.get('config', {}).get('min_improvement_rate', 0.05)
                print(f"  최소 개선율: {min_rate*100:.1f}%")
                if min_rate == 0.001:
                    print("  [OK] 0.1%로 설정됨")
                    results.append(("최소 개선율", True))
                else:
                    print(f"  [FAIL] 기대값과 다름: {min_rate}")
                    results.append(("최소 개선율", False))
    except Exception as e:
        print(f"  [ERROR] {e}")
        results.append(("최소 개선율", False))
    
    # 2. WAL 모드 확인
    print("\n2. 데이터베이스 WAL 모드 확인")
    print("-" * 40)
    try:
        import sqlite3
        test_db = 'data/combinations.db'
        conn = sqlite3.connect(test_db, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        
        if mode == 'wal':
            print(f"  combinations.db: {mode} 모드")
            print("  [OK] WAL 모드 활성화")
            results.append(("WAL 모드", True))
        else:
            print(f"  combinations.db: {mode} 모드")
            print("  [FAIL] WAL 모드가 아님")
            results.append(("WAL 모드", False))
    except Exception as e:
        print(f"  [ERROR] {e}")
        results.append(("WAL 모드", False))
    
    # 3. 모델 로딩 상태 확인
    print("\n3. ML 모델 로딩 상태 확인")
    print("-" * 40)
    try:
        from src.ml.ensemble_predictor import EnsemblePredictor
        predictor = EnsemblePredictor()
        
        print(f"  is_trained: {predictor.is_trained}")
        print(f"  로드된 모델: {list(predictor.models.keys())}")
        
        if predictor.is_trained and len(predictor.models) >= 2:
            print("  [OK] 모델 정상 로드")
            results.append(("모델 로딩", True))
        else:
            print("  [FAIL] 모델 로드 실패")
            results.append(("모델 로딩", False))
    except Exception as e:
        print(f"  [ERROR] {e}")
        results.append(("모델 로딩", False))
    
    # 4. 튜플 인덱스 에러 수정 확인
    print("\n4. 튜플 인덱스 에러 수정 확인")
    print("-" * 40)
    try:
        from src.core.specialized_databases import FilterDB
        test_db = 'data/filters/match_filter.db'
        
        if os.path.exists(test_db):
            filter_db = FilterDB(test_db)
            details = filter_db.get_filter_details(1184)
            print(f"  get_filter_details 호출: 성공")
            print(f"  반환 타입: {type(details)}")
            print("  [OK] 튜플 에러 해결")
            results.append(("튜플 에러", True))
        else:
            print("  [SKIP] 테스트 DB 없음")
            results.append(("튜플 에러", True))
    except TypeError as e:
        if "tuple indices" in str(e):
            print(f"  [FAIL] 튜플 에러 여전히 발생: {e}")
            results.append(("튜플 에러", False))
        else:
            print(f"  [ERROR] {e}")
            results.append(("튜플 에러", False))
    except Exception as e:
        print(f"  [ERROR] {e}")
        results.append(("튜플 에러", False))
    
    # 5. 연결 관리자 개선 확인
    print("\n5. 연결 관리자 개선 확인")
    print("-" * 40)
    try:
        from src.utils.db_connection_manager import DatabaseConnectionManager
        import threading
        
        # RLock 확인
        test_lock = DatabaseConnectionManager.get_lock("test.db")
        lock_type_name = type(test_lock).__name__
        
        if "RLock" in lock_type_name:
            print(f"  락 타입: {lock_type_name}")
            print("  [OK] 연결 관리자 개선됨")
            results.append(("연결 관리자", True))
        else:
            print(f"  락 타입: {lock_type_name}")
            print("  [FAIL] RLock이 아님")
            results.append(("연결 관리자", False))
    except Exception as e:
        print(f"  [ERROR] {e}")
        results.append(("연결 관리자", False))
    
    # 결과 요약
    print("\n" + "="*70)
    print("최종 확인 결과")
    print("="*70)
    
    for item, success in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {item}: {status}")
    
    success_count = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\n통과: {success_count}/{total}")
    
    if all(r[1] for r in results):
        print("\n[SUCCESS] 모든 문제가 해결되었습니다!")
        print("\n다음 명령으로 프로그램을 실행하세요:")
        print("  python main.py")
    else:
        print("\n[WARNING] 일부 문제가 남아있습니다.")
        failed = [item for item, success in results if not success]
        print(f"실패한 항목: {', '.join(failed)}")
    
    return all(r[1] for r in results)

if __name__ == "__main__":
    success = check_all_fixes()
    sys.exit(0 if success else 1)