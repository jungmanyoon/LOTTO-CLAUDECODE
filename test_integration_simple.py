#!/usr/bin/env python3
"""
성능 통계 통합 테스트 스크립트 (간단 버전)
"""

import sys
import os
import json
import logging
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.performance_stats_manager import PerformanceStatsManager

def create_sample_data():
    """샘플 데이터 생성"""
    return {
        'performance_metrics': {
            'total_rounds': 10,
            'model_performance': {
                'lstm': {
                    'total_predictions': 50,
                    'match_counts': {0: 20, 1: 15, 2: 10, 3: 4, 4: 1, 5: 0, 6: 0},
                    'avg_matches': 1.2,
                    'best_match': 4,
                    'accuracy_3plus': 10.0,
                    'contaminated_count': 0
                },
                'ensemble': {
                    'total_predictions': 50,
                    'match_counts': {0: 18, 1: 16, 2: 11, 3: 4, 4: 1, 5: 0, 6: 0},
                    'avg_matches': 1.32,
                    'best_match': 4,
                    'accuracy_3plus': 10.0,
                    'contaminated_count': 0
                }
            }
        },
        'predictions': []
    }

def test_basic_functionality():
    """기본 기능 테스트"""
    print("\n테스트: 기본 기능")
    print("-" * 40)
    
    try:
        # 성능 통계 관리자 테스트
        stats_manager = PerformanceStatsManager(db_path="data/test_performance.db")
        print("[OK] 성능 통계 관리자 초기화")
        
        # 샘플 데이터 저장
        sample_data = create_sample_data()
        session_id = stats_manager.save_backtest_results(sample_data)
        
        if session_id > 0:
            print(f"[OK] 데이터 저장 완료 (세션 ID: {session_id})")
        else:
            print("[ERROR] 데이터 저장 실패")
            return False
        
        # 데이터 조회
        summary = stats_manager.get_model_performance_summary()
        if summary and 'by_model' in summary:
            print(f"[OK] 성능 요약 조회 완료 (모델 수: {len(summary['by_model'])})")
        else:
            print("[ERROR] 성능 요약 조회 실패")
            return False
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 기본 기능 테스트 실패: {e}")
        return False

def test_dashboard_integration():
    """대시보드 통합 테스트"""
    print("\n테스트: 대시보드 통합")
    print("-" * 40)
    
    try:
        from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard
        
        dashboard = EnhancedLottoDashboard()
        print("[OK] 대시보드 초기화")
        
        # API 메서드 테스트
        backtest_stats = dashboard.get_backtest_performance_stats()
        if backtest_stats:
            available = backtest_stats.get('available', False)
            print(f"[OK] 백테스팅 통계 조회 (available: {available})")
        else:
            print("[ERROR] 백테스팅 통계 조회 실패")
            return False
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 대시보드 통합 테스트 실패: {e}")
        return False

def main():
    """메인 테스트"""
    print("성능 통계 통합 테스트 시작")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 로깅 설정 (WARNING 레벨로 설정하여 불필요한 로그 숨기기)
    logging.basicConfig(level=logging.WARNING)
    
    tests = [
        ("기본 기능", test_basic_functionality),
        ("대시보드 통합", test_dashboard_integration)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"[PASS] {test_name}")
            else:
                print(f"[FAIL] {test_name}")
        except Exception as e:
            print(f"[ERROR] {test_name}: {e}")
    
    print("\n" + "=" * 60)
    print("테스트 결과")
    print("=" * 60)
    print(f"총 {total}개 테스트 중 {passed}개 통과")
    
    if passed == total:
        print("\n[SUCCESS] 모든 테스트 통과!")
        print("\n다음 단계:")
        print("1. python main.py 실행하여 백테스팅 수행")
        print("2. python run_dashboard.py 실행하여 대시보드 시작")
        print("3. 브라우저에서 '전체 통계' 버튼 클릭")
        return True
    else:
        print(f"\n[WARNING] {total - passed}개 테스트 실패")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)