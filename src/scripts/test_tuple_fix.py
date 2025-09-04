#!/usr/bin/env python3
"""
튜플 인덱스 에러 수정 확인 테스트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from src.core.specialized_databases import FilterDB

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def test_filter_details_fix():
    """get_filter_details 메서드 수정 확인"""
    print("\n" + "="*70)
    print("튜플 인덱스 에러 수정 확인")
    print("="*70)
    
    # 테스트할 필터 DB
    test_filters = [
        'data/filters/match_filter.db',
        'data/filters/odd_even_filter.db'
    ]
    
    round_num = 1184
    errors = []
    
    for db_path in test_filters:
        db_name = os.path.basename(db_path)
        print(f"\n테스트: {db_name}")
        print("-" * 40)
        
        if not os.path.exists(db_path):
            print(f"  [SKIP] 파일이 없습니다")
            continue
        
        try:
            # FilterDB 인스턴스 생성
            filter_db = FilterDB(db_path)
            
            # get_filter_details 호출 (에러가 발생했던 메서드)
            details = filter_db.get_filter_details(round_num)
            
            print(f"  [OK] get_filter_details 호출 성공")
            if details:
                print(f"  반환된 상세 정보 타입: {type(details)}")
            else:
                print(f"  상세 정보가 없습니다 (정상)")
            
        except TypeError as e:
            if "tuple indices must be integers" in str(e):
                print(f"  [FAIL] 튜플 인덱스 에러가 여전히 발생!")
                errors.append((db_name, str(e)))
            else:
                print(f"  [ERROR] 다른 TypeError: {e}")
                errors.append((db_name, str(e)))
        except Exception as e:
            print(f"  [ERROR] 예상치 못한 에러: {e}")
            errors.append((db_name, str(e)))
    
    # 결과 요약
    print("\n" + "="*70)
    print("테스트 결과")
    print("="*70)
    
    if not errors:
        print("\n[SUCCESS] 모든 테스트 통과!")
        print("\n수정 내용:")
        print("- specialized_databases.py 1524번 줄")
        print("- result['details'] → result[0]")
        print("- 튜플을 딕셔너리처럼 접근하는 문제 해결")
        return True
    else:
        print("\n[FAIL] 에러 발생:")
        for db_name, error in errors:
            print(f"  - {db_name}: {error}")
        return False

if __name__ == "__main__":
    success = test_filter_details_fix()
    sys.exit(0 if success else 1)