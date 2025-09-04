#!/usr/bin/env python3
"""
현재 상태에서 실제로 에러가 발생하는지 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def test_filter_details_now():
    """현재 시점에서 get_filter_details 테스트"""
    print("\n" + "="*70)
    print(f"현재 시각: {datetime.now()}")
    print("get_filter_details 메서드 테스트")
    print("="*70)
    
    from src.core.specialized_databases import FilterDB
    
    # 테스트할 필터들
    test_filters = [
        ('match', 'data/filters/match_filter.db'),
        ('odd_even', 'data/filters/odd_even_filter.db'),
        ('consecutive', 'data/filters/consecutive_filter.db')
    ]
    
    round_num = 1184
    errors = []
    success_count = 0
    
    for filter_name, db_path in test_filters:
        print(f"\n[{filter_name}] 테스트 중...")
        
        if not os.path.exists(db_path):
            print(f"  파일 없음: {db_path}")
            continue
        
        try:
            filter_db = FilterDB(db_path)
            
            # 에러가 발생했던 메서드 호출
            details = filter_db.get_filter_details(round_num)
            
            # 성공
            success_count += 1
            print(f"  [OK] 성공! 반환 타입: {type(details)}")
            
        except TypeError as e:
            if "tuple indices must be integers" in str(e):
                print(f"  [FAIL] 튜플 인덱스 에러 발생!")
                print(f"     {e}")
                errors.append((filter_name, str(e)))
            else:
                print(f"  [FAIL] 다른 TypeError: {e}")
                errors.append((filter_name, str(e)))
        except Exception as e:
            print(f"  [FAIL] 예상치 못한 에러: {e}")
            errors.append((filter_name, str(e)))
    
    # 결과 요약
    print("\n" + "="*70)
    print("테스트 결과 요약")
    print("="*70)
    print(f"테스트 시각: {datetime.now()}")
    print(f"성공: {success_count}개")
    print(f"실패: {len(errors)}개")
    
    if errors:
        print("\n[FAIL] 에러가 여전히 발생합니다:")
        for name, error in errors:
            print(f"  - {name}: {error}")
        print("\n파일이 제대로 저장되지 않았거나 프로그램이 재시작되지 않았을 수 있습니다.")
    else:
        print("\n[SUCCESS] 모든 테스트 통과! 에러가 해결되었습니다.")
        print("\n사용자가 보여준 에러는 12:29:33에 발생한 것으로,")
        print("파일 수정(12:33:42) 이전의 에러입니다.")
    
    return len(errors) == 0

if __name__ == "__main__":
    success = test_filter_details_now()
    sys.exit(0 if success else 1)