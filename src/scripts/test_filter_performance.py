"""
필터링 성능 테스트 스크립트
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import time
import yaml

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.core.parallel_filter_manager import ParallelFilterManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/filter_performance.log', encoding='utf-8')
    ]
)

def test_filter_performance(mode='auto'):
    """필터링 성능 테스트"""
    try:
        # 설정 로드
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()
        
        # 필터 매니저 초기화 (병렬 처리 사용)
        filter_manager = ParallelFilterManager(db_manager)
        
        print("\n" + "="*60)
        print("필터링 성능 테스트")
        print("="*60)
        
        # 현재 회차 확인
        latest_round = db_manager.lotto_db.get_last_round()
        print(f"\n현재 최신 회차: {latest_round}")
        
        # 테스트 옵션
        if mode == 'auto':
            # 자동 모드: 증분 모드로 실행
            update_mode = 'incremental'
            force = False
            print("\n자동 모드: 증분 필터링으로 실행합니다.")
        else:
            print("\n테스트 옵션:")
            print("1. 증분 모드 (이전 필터링 결과 활용)")
            print("2. 전체 모드 (모든 조합 재필터링)")
            print("3. 강제 모드 (캐시 무시)")
            
            choice = input("\n선택 (1-3): ")
            
            if choice == '1':
                update_mode = 'incremental'
                force = False
            elif choice == '2':
                update_mode = 'full'
                force = False
            elif choice == '3':
                update_mode = 'full'
                force = True
            else:
                print("잘못된 선택입니다.")
                return
        
        print(f"\n필터링 시작 (모드: {update_mode}, 강제: {force})")
        print("-" * 60)
        
        # 필터링 실행
        start_time = time.time()
        success = filter_manager.apply_filters(latest_round, update_mode, force)
        end_time = time.time()
        
        total_time = end_time - start_time
        
        if success:
            print(f"\n✅ 필터링 성공!")
            print(f"총 소요 시간: {total_time:.2f}초")
            
            # 최종 결과 확인
            final_combinations = db_manager.combinations_db.get_filtered_combinations()
            if final_combinations:
                print(f"최종 조합 수: {len(final_combinations):,}개")
                
                # 샘플 출력
                print("\n샘플 조합 (최대 10개):")
                for i, combo in enumerate(final_combinations[:10], 1):
                    print(f"  {i}. {combo}")
        else:
            print(f"\n❌ 필터링 실패!")
        
        # 성능 요약
        print("\n" + "="*60)
        print("성능 테스트 완료")
        print("="*60)
        print(f"- 총 소요 시간: {total_time:.2f}초")
        print(f"- 로그 파일: logs/filter_performance.log")
        
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    test_filter_performance()