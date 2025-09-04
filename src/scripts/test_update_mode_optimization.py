#!/usr/bin/env python3
"""
update_mode 최적화 테스트 스크립트

이 스크립트는 전체 모드와 증분 모드의 성능 차이를 측정합니다.
"""

import sys
import os
import time
import logging
from pathlib import Path

# 프로젝트 루트 디렉토리를 sys.path에 추가
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_filter_modes(db_manager: DatabaseManager, latest_round: int):
    """전체 모드와 증분 모드의 성능 비교 테스트"""
    
    filter_manager = FilterManager(db_manager)
    
    print("="*80)
    print("필터링 모드 성능 비교 테스트")
    print("="*80)
    
    # 1. 전체 모드 테스트
    print("\n[테스트 1] 전체 모드 (full mode) 성능 측정")
    print("-" * 50)
    
    start_time = time.time()
    
    try:
        filter_manager.apply_filters(latest_round, 'full', force=True)
        full_mode_time = time.time() - start_time
        print(f"OK 전체 모드 완료: {full_mode_time:.1f}초")
    except Exception as e:
        print(f"ERROR 전체 모드 실패: {str(e)}")
        return
    
    # 잠시 대기
    time.sleep(2)
    
    # 2. 증분 모드 테스트 (기존 결과 활용)
    print("\n[테스트 2] 증분 모드 (incremental mode) 성능 측정")
    print("-" * 50)
    
    start_time = time.time()
    
    try:
        # 증분 모드는 기존 결과가 있으면 빠르게 처리됨
        filter_manager.apply_filters(latest_round, 'incremental', force=False)
        incremental_mode_time = time.time() - start_time
        print(f"OK 증분 모드 완료: {incremental_mode_time:.1f}초")
    except Exception as e:
        print(f"ERROR 증분 모드 실패: {str(e)}")
        return
    
    # 3. 성능 비교 결과
    print("\n[성능 비교 결과]")
    print("="*50)
    print(f"전체 모드 시간:    {full_mode_time:.1f}초")
    print(f"증분 모드 시간:    {incremental_mode_time:.1f}초")
    
    if incremental_mode_time > 0:
        performance_ratio = full_mode_time / incremental_mode_time
        time_saved = full_mode_time - incremental_mode_time
        percentage_saved = (time_saved / full_mode_time) * 100
        
        print(f"성능 향상 비율:    {performance_ratio:.1f}배")
        print(f"절약된 시간:      {time_saved:.1f}초")
        print(f"시간 절약률:      {percentage_saved:.1f}%")
        
        if performance_ratio >= 2.0:
            print("EXCELLENT 우수한 성능 향상!")
        elif performance_ratio >= 1.5:
            print("GOOD 좋은 성능 향상")
        else:
            print("WARNING 성능 향상 미미")
    else:
        print("WARNING 증분 모드가 너무 빨라서 정확한 측정이 어려움")

def main():
    """메인 함수"""
    setup_logging()
    
    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 최신 회차 가져오기
        latest_round = db_manager.get_last_round()
        if not latest_round:
            print("최신 회차를 가져올 수 없습니다.")
            return
        
        print(f"INFO 테스트 대상: {latest_round}회차")
        
        # 성능 비교 테스트 실행
        test_filter_modes(db_manager, latest_round)
        
        print("\n" + "="*80)
        print("테스트 완료!")
        print("\nTIP 사용법:")
        print("  - 일반 실행: python main.py (증분 모드 사용)")
        print("  - 전체 모드: python main.py --full-filter")
        print("  - 강제 모드: python main.py --force-filter")
        print("="*80)
        
    except Exception as e:
        print(f"ERROR 테스트 실행 중 오류: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)