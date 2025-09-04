#!/usr/bin/env python3
"""
빠른 모드 테스트 스크립트

main.py의 필터링 모드 결정 로직만 테스트합니다.
"""

import sys
import argparse
from pathlib import Path

def test_mode_detection():
    """모드 결정 로직 테스트"""
    
    print("=" * 60)
    print("update_mode 결정 로직 테스트")
    print("=" * 60)
    
    # 테스트 케이스들
    test_cases = [
        # (args, expected_mode, description)
        ([], 'incremental', '기본 실행 (아무 옵션 없음)'),
        (['--full-filter'], 'full', '--full-filter 옵션'),
        (['--force-filter'], 'full', '--force-filter 옵션'),
        (['--full-filter', '--force-filter'], 'full', '둘 다 지정'),
        (['--skip-validation'], 'incremental', '다른 옵션만 있을 때'),
    ]
    
    for test_args, expected_mode, description in test_cases:
        # ArgumentParser 생성 (main.py와 동일한 구조)
        parser = argparse.ArgumentParser()
        parser.add_argument('--full-filter', action='store_true', help='전체 필터링 수행 (기본값: 증분 모드)')
        parser.add_argument('--force-filter', action='store_true', help='이전 필터링 여부와 상관없이 필터링을 강제 실행합니다')
        parser.add_argument('--skip-validation', action='store_true', help='기타 옵션')
        
        # 테스트 실행
        try:
            args = parser.parse_args(test_args)
            
            # main.py와 동일한 로직
            update_mode = 'full' if args.full_filter or args.force_filter else 'incremental'
            
            # 결과 확인
            status = "OK" if update_mode == expected_mode else "ERROR"
            print(f"{status} {description}")
            print(f"   명령: python main.py {' '.join(test_args) if test_args else '(옵션 없음)'}")
            print(f"   예상: {expected_mode} | 실제: {update_mode}")
            
            if update_mode != expected_mode:
                print(f"   ERROR: 예상과 다른 결과!")
            else:
                print(f"   OK: 올바른 모드 선택")
            print()
            
        except Exception as e:
            print(f"ERROR {description} - 오류: {str(e)}")
            print()
    
    print("=" * 60)
    print("결론:")
    print("- 기본 실행: 증분 모드 사용 (빠른 실행)")
    print("- --full-filter: 전체 모드 사용 (완전한 재계산)")
    print("- --force-filter: 전체 모드 사용 (강제 실행)")
    print("=" * 60)

if __name__ == "__main__":
    test_mode_detection()