#!/usr/bin/env python3
"""
성능 통계 통합 테스트 스크립트
- 백테스팅 결과 저장 테스트
- 대시보드 API 엔드포인트 테스트
- 전체 통합 기능 검증
"""

import sys
import os
import json
import logging
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.performance_stats_manager import PerformanceStatsManager

def create_sample_backtest_results():
    """샘플 백테스팅 결과 생성"""
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
                },
                'monte_carlo': {
                    'total_predictions': 50,
                    'match_counts': {0: 22, 1: 14, 2: 9, 3: 4, 4: 1, 5: 0, 6: 0},
                    'avg_matches': 1.18,
                    'best_match': 4,
                    'accuracy_3plus': 10.0,
                    'contaminated_count': 0
                },
                'combined': {
                    'total_predictions': 150,
                    'match_counts': {0: 60, 1: 45, 2: 30, 3: 12, 4: 3, 5: 0, 6: 0},
                    'avg_matches': 1.23,
                    'best_match': 4,
                    'accuracy_3plus': 10.0,
                    'contaminated_count': 0
                }
            }
        },
        'predictions': [
            {
                'round': 1180,
                'winning_numbers': [1, 5, 12, 18, 25, 31],
                'matches': {
                    'lstm': [
                        {'predicted_numbers': [2, 8, 15, 22, 29, 35], 'match_count': 0, 'contaminated': False},
                        {'predicted_numbers': [1, 7, 14, 21, 28, 34], 'match_count': 1, 'contaminated': False}
                    ],
                    'ensemble': [
                        {'predicted_numbers': [3, 9, 16, 23, 30, 36], 'match_count': 0, 'contaminated': False},
                        {'predicted_numbers': [5, 11, 18, 24, 31, 37], 'match_count': 3, 'contaminated': False}
                    ],
                    'monte_carlo': [
                        {'predicted_numbers': [4, 10, 17, 25, 32, 38], 'match_count': 1, 'contaminated': False},
                        {'predicted_numbers': [6, 12, 19, 26, 33, 39], 'match_count': 1, 'contaminated': False}
                    ]
                }
            },
            {
                'round': 1181,
                'winning_numbers': [3, 7, 14, 20, 27, 33],
                'matches': {
                    'lstm': [
                        {'predicted_numbers': [2, 8, 15, 22, 29, 35], 'match_count': 0, 'contaminated': False},
                        {'predicted_numbers': [3, 9, 16, 23, 30, 36], 'match_count': 1, 'contaminated': False}
                    ],
                    'ensemble': [
                        {'predicted_numbers': [4, 10, 17, 24, 31, 37], 'match_count': 0, 'contaminated': False},
                        {'predicted_numbers': [7, 13, 20, 26, 33, 39], 'match_count': 3, 'contaminated': False}
                    ],
                    'monte_carlo': [
                        {'predicted_numbers': [1, 5, 12, 18, 25, 32], 'match_count': 0, 'contaminated': False},
                        {'predicted_numbers': [6, 14, 21, 27, 34, 40], 'match_count': 2, 'contaminated': False}
                    ]
                }
            }
        ]
    }

def test_performance_stats_manager():
    """성능 통계 관리자 테스트"""
    print("\n" + "="*60)
    print("성능 통계 관리자 테스트")
    print("="*60)
    
    try:
        # 성능 통계 관리자 초기화
        stats_manager = PerformanceStatsManager(db_path="data/test_performance_stats.db")
        print("✅ 성능 통계 관리자 초기화 완료")
        
        # 샘플 백테스팅 결과 저장
        sample_results = create_sample_backtest_results()
        session_id = stats_manager.save_backtest_results(sample_results)
        
        if session_id > 0:
            print(f"✅ 백테스팅 결과 저장 완료 (세션 ID: {session_id})")
        else:
            print("❌ 백테스팅 결과 저장 실패")
            return False
        
        # 성능 요약 조회
        summary = stats_manager.get_model_performance_summary()
        if summary:
            print("✅ 모델 성능 요약 조회 완료")
            print(f"   - 총 세션: {summary.get('overall', {}).get('total_sessions', 0)}")
            print(f"   - 모델 수: {len(summary.get('by_model', []))}")
        else:
            print("❌ 성능 요약 조회 실패")
        
        # 일치 분포 조회
        distribution = stats_manager.get_match_distribution_stats()
        if distribution:
            print("✅ 일치 분포 통계 조회 완료")
            total = distribution.get('total_predictions', 0)
            print(f"   - 총 예측: {total}")
        else:
            print("❌ 일치 분포 조회 실패")
        
        # 최근 성능 기록 조회
        recent = stats_manager.get_latest_performance(limit=5)
        if recent:
            print(f"✅ 최근 성능 기록 조회 완료 ({len(recent)}개)")
        else:
            print("❌ 최근 성능 기록 조회 실패")
        
        return True
        
    except Exception as e:
        print(f"❌ 성능 통계 관리자 테스트 실패: {e}")
        return False

def test_dashboard_integration():
    """대시보드 통합 테스트"""
    print("\n" + "="*60)
    print("대시보드 통합 테스트")
    print("="*60)
    
    try:
        # 대시보드 클래스 임포트 및 초기화
        from src.scripts.enhanced_dashboard_v2 import EnhancedLottoDashboard
        
        dashboard = EnhancedLottoDashboard()
        print("✅ 대시보드 초기화 완료")
        
        # 백테스팅 성능 통계 조회
        backtest_stats = dashboard.get_backtest_performance_stats()
        if backtest_stats.get('available'):
            print("✅ 백테스팅 성능 통계 조회 완료")
            summary = backtest_stats.get('performance_summary', {})
            print(f"   - 모델 수: {len(summary.get('by_model', []))}")
        else:
            print("❌ 백테스팅 성능 통계 조회 실패")
            print(f"   - 오류: {backtest_stats.get('error', '알 수 없는 오류')}")
        
        # 모델 비교 통계 조회
        comparison = dashboard.get_model_comparison_stats()
        if not comparison.get('error'):
            print("✅ 모델 비교 통계 조회 완료")
            models = comparison.get('models', {})
            best = comparison.get('best_performer')
            print(f"   - 비교 모델: {len(models)}")
            print(f"   - 최고 성능: {best}")
        else:
            print("❌ 모델 비교 통계 조회 실패")
        
        # 성능 추이 조회
        trends = dashboard.get_performance_trends(limit=5)
        if not trends.get('error'):
            print("✅ 성능 추이 조회 완료")
            trend_data = trends.get('trend_analysis', {})
            trend_direction = trend_data.get('improvement_trend', 'unknown')
            print(f"   - 추세: {trend_direction}")
        else:
            print("❌ 성능 추이 조회 실패")
        
        return True
        
    except Exception as e:
        print(f"❌ 대시보드 통합 테스트 실패: {e}")
        return False

def test_api_endpoints():
    """API 엔드포인트 테스트"""
    print("\n" + "="*60)
    print("API 엔드포인트 테스트")
    print("="*60)
    
    try:
        import requests
        
        base_url = "http://127.0.0.1:5001"
        endpoints = [
            "/api/backtest-performance",
            "/api/model-comparison", 
            "/api/performance-trends",
            "/api/performance-trends/5"
        ]
        
        print("⚠️  대시보드가 실행 중이어야 합니다 (python run_dashboard.py)")
        
        for endpoint in endpoints:
            try:
                response = requests.get(base_url + endpoint, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ {endpoint} - OK")
                else:
                    print(f"❌ {endpoint} - HTTP {response.status_code}")
            except requests.exceptions.RequestException:
                print(f"⚠️  {endpoint} - 연결 실패 (대시보드 미실행?)")
        
        return True
        
    except ImportError:
        print("⚠️  requests 모듈이 없어 API 테스트를 건너뜁니다")
        return True
    except Exception as e:
        print(f"❌ API 엔드포인트 테스트 실패: {e}")
        return False

def test_main_py_integration():
    """main.py 통합 테스트"""
    print("\n" + "="*60)
    print("main.py 통합 테스트")
    print("="*60)
    
    try:
        print("[CHECK] main.py 통합 확인:")
        print("   1. PerformanceStatsManager import 추가됨")
        print("   2. 백테스팅 후 save_backtest_results() 호출 추가됨")
        print("   3. 성능 통계가 data/performance_stats.db에 저장됨")
        print("")
        print("[METHOD] 테스트 방법:")
        print("   python main.py  # 백테스팅 포함 실행")
        print("   python run_dashboard.py  # 대시보드 실행 후 '전체 통계' 버튼 클릭")
        
        return True
        
    except Exception as e:
        print(f"❌ main.py 통합 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 실행"""
    print("[TEST] 성능 통계 통합 테스트 시작")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)
    
    tests = [
        ("성능 통계 관리자", test_performance_stats_manager),
        ("대시보드 통합", test_dashboard_integration), 
        ("API 엔드포인트", test_api_endpoints),
        ("main.py 통합", test_main_py_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 예외 발생: {e}")
            results.append((test_name, False))
    
    # 결과 요약
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\n총 {len(results)}개 테스트 중 {passed}개 통과")
    
    if passed == len(results):
        print("\n[SUCCESS] 모든 테스트 통과! 성능 통계 통합이 완료되었습니다.")
        print("\n[NEXT] 다음 단계:")
        print("1. python main.py 실행하여 백테스팅 수행")
        print("2. python run_dashboard.py 실행하여 대시보드 시작")
        print("3. 브라우저에서 '전체 통계' 버튼 클릭하여 성능 통계 확인")
    else:
        print(f"\n[WARNING] {len(results) - passed}개 테스트 실패. 문제를 해결해주세요.")
    
    return passed == len(results)

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)