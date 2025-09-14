#!/usr/bin/env python3
"""
데이터베이스 싱글톤 패턴 테스트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_singleton():
    print("\n[TEST] 데이터베이스 싱글톤 패턴 테스트")
    print("="*50)
    
    # 첫 번째 인스턴스 생성
    print("\n1. 첫 번째 DatabaseManager 인스턴스 생성...")
    db1 = DatabaseManager()
    print(f"   - 인스턴스 ID: {id(db1)}")
    
    # 두 번째 인스턴스 생성 시도
    print("\n2. 두 번째 DatabaseManager 인스턴스 생성 시도...")
    db2 = DatabaseManager()
    print(f"   - 인스턴스 ID: {id(db2)}")
    
    # 세 번째 인스턴스 생성 시도
    print("\n3. 세 번째 DatabaseManager 인스턴스 생성 시도...")
    db3 = DatabaseManager()
    print(f"   - 인스턴스 ID: {id(db3)}")
    
    # 네 번째 인스턴스 생성 시도
    print("\n4. 네 번째 DatabaseManager 인스턴스 생성 시도...")
    db4 = DatabaseManager()
    print(f"   - 인스턴스 ID: {id(db4)}")
    
    # 결과 확인
    print("\n[RESULT] 싱글톤 패턴 검증:")
    if db1 is db2 and db2 is db3 and db3 is db4:
        print("   [OK] 모든 인스턴스가 동일합니다 (싱글톤 패턴 성공)")
        print(f"   [OK] 단일 인스턴스 ID: {id(db1)}")
    else:
        print("   [FAIL] 인스턴스가 다릅니다 (싱글톤 패턴 실패)")
        print(f"   - db1: {id(db1)}")
        print(f"   - db2: {id(db2)}")
        print(f"   - db3: {id(db3)}")
        print(f"   - db4: {id(db4)}")
    
    print("\n" + "="*50)
    print("[TEST] 테스트 완료\n")

if __name__ == "__main__":
    test_singleton()