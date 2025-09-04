#!/usr/bin/env python3
"""
모든 수정사항을 종합적으로 테스트
2025-08-16 최종 수정 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import json
from datetime import datetime
import sqlite3
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)

def test_database_connection_fixed():
    """Cannot operate on a closed database 에러 수정 확인"""
    print("\n" + "="*70)
    print("1. Database Connection 에러 수정 확인")
    print("="*70)
    
    try:
        from src.core.specialized_databases import FilterDB
        
        # 테스트 데이터
        test_db_path = 'data/filters/test_filter.db'
        filter_db = FilterDB(test_db_path)
        
        # 큰 데이터셋으로 테스트 (배치 처리 테스트)
        test_combinations = [f"1,2,3,4,5,{i}" for i in range(6, 2000)]
        
        # save_filtered_combinations 테스트
        success = filter_db.save_filtered_combinations(9999, test_combinations)
        
        if success:
            print("  [OK] save_filtered_combinations 성공 (COMMIT 에러 해결됨)")
        else:
            print("  [FAIL] save_filtered_combinations 실패")
            return False
        
        # save_excluded_combinations 테스트  
        excluded = [f"7,8,9,10,11,{i}" for i in range(12, 1000)]
        success = filter_db.save_excluded_combinations(9999, excluded)
        
        if success:
            print("  [OK] save_excluded_combinations 성공 (COMMIT 에러 해결됨)")
        else:
            print("  [FAIL] save_excluded_combinations 실패")
            return False
            
        print("  [SUCCESS] Database connection 에러가 완전히 해결되었습니다!")
        return True
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def test_backtest_count_saving():
    """백테스팅 횟수 저장 문제 해결 확인"""
    print("\n" + "="*70)
    print("2. 백테스팅 횟수 저장 문제 해결 확인")
    print("="*70)
    
    try:
        from src.optimization.auto_improvement_manager import AutoImprovementManager
        
        # 매니저 생성
        manager = AutoImprovementManager()
        
        # 현재 상태 확인
        current_count = manager.state['total_backtest_count']
        print(f"  현재 백테스팅 횟수: {current_count}")
        
        # 테스트 백테스팅 결과 생성
        test_results = {
            'lstm': {'accuracy': 0.75},
            'ensemble': {'accuracy': 0.80},
            'monte_carlo': {'accuracy': 0.78}
        }
        
        # track_backtest 호출
        improvement_info = manager.track_backtest(test_results)
        new_count = manager.state['total_backtest_count']
        
        print(f"  track_backtest 후 횟수: {new_count}")
        
        # 수동으로 save_state 호출
        manager.save_state()
        
        # 파일에서 다시 읽어와서 확인
        with open('data/auto_improvement_state.json', 'r', encoding='utf-8') as f:
            saved_state = json.load(f)
        
        saved_count = saved_state['total_backtest_count']
        print(f"  파일에 저장된 횟수: {saved_count}")
        
        if saved_count == new_count:
            print("  [OK] 백테스팅 횟수가 정상적으로 저장됨")
            
            # last_updated 시간 확인
            last_updated = saved_state.get('last_updated', '')
            print(f"  마지막 업데이트: {last_updated}")
            
            # 현재 시간과 비교
            from datetime import datetime
            try:
                update_time = datetime.fromisoformat(last_updated)
                time_diff = datetime.now() - update_time
                if time_diff.total_seconds() < 60:  # 1분 이내
                    print("  [OK] 방금 업데이트됨")
                else:
                    print(f"  [WARNING] {time_diff.total_seconds():.0f}초 전 업데이트")
            except:
                pass
                
            print("  [SUCCESS] 백테스팅 횟수 저장 문제가 해결되었습니다!")
            return True
        else:
            print(f"  [FAIL] 저장된 횟수({saved_count})와 메모리 횟수({new_count})가 다름")
            return False
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def test_tuple_index_error():
    """튜플 인덱스 에러 수정 확인"""
    print("\n" + "="*70)
    print("3. 튜플 인덱스 에러 수정 확인")
    print("="*70)
    
    try:
        from src.core.specialized_databases import FilterDB
        
        test_filters = [
            ('match', 'data/filters/match_filter.db'),
            ('odd_even', 'data/filters/odd_even_filter.db'),
        ]
        
        round_num = 1184
        all_success = True
        
        for filter_name, db_path in test_filters:
            if not os.path.exists(db_path):
                print(f"  [{filter_name}] 파일 없음 - 스킵")
                continue
                
            try:
                filter_db = FilterDB(db_path)
                details = filter_db.get_filter_details(round_num)
                print(f"  [{filter_name}] [OK] get_filter_details 성공")
            except TypeError as e:
                if "tuple indices" in str(e):
                    print(f"  [{filter_name}] [FAIL] 튜플 에러 여전히 발생")
                    all_success = False
                else:
                    print(f"  [{filter_name}] [ERROR] {e}")
                    all_success = False
            except Exception as e:
                print(f"  [{filter_name}] [ERROR] {e}")
                all_success = False
        
        if all_success:
            print("  [SUCCESS] 튜플 인덱스 에러가 완전히 해결되었습니다!")
        return all_success
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def test_model_loading():
    """모델 로딩 상태 확인"""
    print("\n" + "="*70)
    print("4. ML 모델 로딩 상태 확인")
    print("="*70)
    
    try:
        from src.ml.ensemble_predictor import EnsemblePredictor
        
        predictor = EnsemblePredictor()
        
        print(f"  모델 학습 상태: {predictor.is_trained}")
        print(f"  로드된 모델: {list(predictor.models.keys())}")
        
        if predictor.is_trained and len(predictor.models) >= 2:
            print("  [OK] 모델이 정상적으로 로드됨")
            print("  [SUCCESS] 모델 로딩이 정상입니다!")
            return True
        else:
            print("  [WARNING] 모델이 완전히 로드되지 않음")
            return False
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def run_comprehensive_test():
    """종합 테스트 실행"""
    print("\n" + "="*70)
    print("[TEST] 종합 테스트 시작")
    print(f"테스트 시간: {datetime.now()}")
    print("="*70)
    
    results = []
    
    # 1. Database connection 에러 테스트
    results.append(("Database Connection", test_database_connection_fixed()))
    
    # 2. 백테스팅 횟수 저장 테스트
    results.append(("Backtest Count Save", test_backtest_count_saving()))
    
    # 3. 튜플 인덱스 에러 테스트
    results.append(("Tuple Index Error", test_tuple_index_error()))
    
    # 4. 모델 로딩 테스트
    results.append(("Model Loading", test_model_loading()))
    
    # 결과 요약
    print("\n" + "="*70)
    print("[SUMMARY] 테스트 결과 요약")
    print("="*70)
    
    success_count = 0
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {test_name}: {status}")
        if success:
            success_count += 1
    
    total = len(results)
    print(f"\n통과: {success_count}/{total}")
    
    if success_count == total:
        print("\n[SUCCESS] 모든 테스트를 통과했습니다!")
        print("프로그램을 정상적으로 실행할 수 있습니다.")
        print("\n실행 명령:")
        print("  python main.py --auto-improve")
        return True
    else:
        print(f"\n[WARNING] {total - success_count}개의 테스트가 실패했습니다.")
        failed = [name for name, success in results if not success]
        print(f"실패한 테스트: {', '.join(failed)}")
        return False

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)