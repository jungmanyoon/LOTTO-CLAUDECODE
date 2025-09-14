#!/usr/bin/env python3
"""
필터 성능 모니터링 시스템 테스트
실제 필터링 프로세스와 성능 추적이 올바르게 작동하는지 확인
"""

import logging
import sys
import os
import json
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('filter_performance_test.log', encoding='utf-8')
        ]
    )

def test_performance_tracker():
    """성능 추적기 단독 테스트"""
    print("\n" + "="*60)
    print("1. 성능 추적기 단독 테스트")
    print("="*60)
    
    try:
        from src.core.db_manager import DatabaseManager
        from src.core.filter_performance_tracker import FilterPerformanceTracker
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 성능 추적기 초기화
        tracker = FilterPerformanceTracker(db_manager)
        
        # 가상 필터링 세션 시뮬레이션
        round_num = 1186
        initial_combinations = 8145060
        
        # 세션 시작
        tracker.start_filtering_session(round_num, initial_combinations)
        print(f"[O] 세션 시작: 회차 {round_num}, 초기 조합 {initial_combinations:,}개")
        
        # 가상 필터 적용 시뮬레이션
        test_filters = [
            {'name': 'sum_range', 'before': 8145060, 'after': 7200000, 'time': 1.2},
            {'name': 'odd_even', 'before': 7200000, 'after': 6500000, 'time': 0.8},
            {'name': 'consecutive', 'before': 6500000, 'after': 5800000, 'time': 1.5},
            {'name': 'dispersion', 'before': 5800000, 'after': 5921820, 'time': 2.1}
        ]
        
        for filter_data in test_filters:
            criteria = {'test_criteria': True, 'threshold': 0.5}
            tracker.track_filter_application(
                filter_data['name'], 
                filter_data['before'], 
                filter_data['after'], 
                filter_data['time'], 
                criteria, 
                round_num
            )
            print(f"[O] {filter_data['name']}: {filter_data['before']:,} → {filter_data['after']:,} "
                  f"({(filter_data['before']-filter_data['after'])/filter_data['before']*100:.2f}% 제외)")
        
        # 세션 완료
        final_count = 5921820
        tracker.complete_filtering_session(final_count)
        print(f"[O] 세션 완료: 최종 {final_count:,}개 조합")
        
        # 실시간 통계 확인
        stats = tracker.get_real_time_stats()
        print(f"[O] 실시간 통계 수집 완료: {len(stats['filter_summary'])}개 필터")
        
        # 상세 분석 내보내기
        analysis = tracker.export_detailed_analysis('test_detailed_analysis.json')
        print(f"[O] 상세 분석 내보내기 완료")
        
        return True
        
    except Exception as e:
        print(f"[X] 성능 추적기 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_filter_manager_integration():
    """필터 매니저와의 통합 테스트"""
    print("\n" + "="*60)
    print("2. 필터 매니저 통합 테스트")
    print("="*60)
    
    try:
        from src.core.db_manager import DatabaseManager
        from src.core.filter_manager import FilterManager
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 필터 매니저 초기화 (성능 추적기 포함)
        filter_manager = FilterManager(db_manager)
        
        if hasattr(filter_manager, 'performance_tracker') and filter_manager.performance_tracker:
            print("[O] 필터 매니저에 성능 추적기 통합 완료")
            
            # 실시간 통계 테스트
            stats = filter_manager.performance_tracker.get_real_time_stats()
            print(f"[O] 통합된 성능 추적기에서 통계 수집 가능")
            
        else:
            print("[X] 성능 추적기가 필터 매니저에 통합되지 않음")
            return False
        
        # 필터 효율성 점수 테스트
        if hasattr(filter_manager.performance_tracker, 'get_filter_efficiency_scores'):
            efficiency_scores = filter_manager.performance_tracker.get_filter_efficiency_scores()
            print(f"[O] 필터 효율성 점수 계산 가능: {len(efficiency_scores)}개 필터")
        
        return True
        
    except Exception as e:
        print(f"[X] 필터 매니저 통합 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_dynamic_filter_manager():
    """향상된 동적 필터 매니저 테스트"""
    print("\n" + "="*60)
    print("3. 향상된 동적 필터 매니저 테스트")
    print("="*60)
    
    try:
        from src.core.db_manager import DatabaseManager
        from src.enhanced_dynamic_filter_manager import EnhancedDynamicFilterManager
        
        # DB 매니저 초기화
        db_manager = DatabaseManager()
        
        # 향상된 동적 필터 매니저 초기화
        enhanced_manager = EnhancedDynamicFilterManager(db_manager)
        
        # 성능 보고서 생성 테스트
        report = enhanced_manager.export_performance_report('test_performance_report.json')
        
        if report and 'filter_performances' in report:
            print(f"[O] 성능 보고서 생성 완료: {len(report['filter_performances'])}개 필터")
            
            # 실제 데이터 포함 여부 확인
            has_real_data = report.get('actual_filtering_data') is not None
            print(f"[O] 실제 필터링 데이터 포함: {'예' if has_real_data else '아니오'}")
            
            # 제로가 아닌 제외율을 가진 필터 확인
            non_zero_exclusions = 0
            for filter_name, perf in report['filter_performances'].items():
                exclusion_rate = perf.get('current_metrics', {}).get('avg_exclusion_rate', 0)
                if exclusion_rate > 0:
                    non_zero_exclusions += 1
                    print(f"  - {filter_name}: {exclusion_rate*100:.2f}% 제외율")
            
            if non_zero_exclusions > 0:
                print(f"[O] {non_zero_exclusions}개 필터에서 실제 제외율 데이터 확인")
            else:
                print("[!] 모든 필터의 제외율이 0% - 실제 데이터 수집 필요")
            
        else:
            print("[X] 성능 보고서 생성 실패")
            return False
        
        return True
        
    except Exception as e:
        print(f"[X] 향상된 동적 필터 매니저 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_report_file_validation():
    """생성된 보고서 파일 검증"""
    print("\n" + "="*60)
    print("4. 보고서 파일 검증")
    print("="*60)
    
    report_files = [
        'filter_performance_report.json',
        'test_performance_report.json',
        'test_detailed_analysis.json'
    ]
    
    all_valid = True
    
    for file_path in report_files:
        try:
            if Path(file_path).exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                print(f"[O] {file_path}: 유효한 JSON 파일")
                
                # 기본 구조 검증
                if 'filter_performances' in data:
                    filter_count = len(data['filter_performances'])
                    print(f"  - 필터 개수: {filter_count}")
                    
                    # 실제 성능 데이터 확인
                    real_data_count = 0
                    for filter_name, perf in data['filter_performances'].items():
                        metrics = perf.get('current_metrics', {})
                        if metrics.get('avg_exclusion_rate', 0) > 0:
                            real_data_count += 1
                    
                    print(f"  - 실제 데이터가 있는 필터: {real_data_count}/{filter_count}")
                    
                if 'generated_at' in data:
                    print(f"  - 생성 시간: {data['generated_at']}")
                    
            else:
                print(f"[!] {file_path}: 파일이 존재하지 않음")
                
        except Exception as e:
            print(f"[X] {file_path}: 검증 실패 - {e}")
            all_valid = False
    
    return all_valid

def main():
    """메인 테스트 함수"""
    setup_logging()
    
    print("[검사] 필터 성능 모니터링 시스템 테스트 시작")
    print(f"작업 디렉토리: {os.getcwd()}")
    
    test_results = []
    
    # 각 테스트 실행
    test_results.append(test_performance_tracker())
    test_results.append(test_filter_manager_integration())
    test_results.append(test_enhanced_dynamic_filter_manager())
    test_results.append(test_report_file_validation())
    
    # 결과 요약
    print("\n" + "="*60)
    print("[결과] 테스트 결과 요약")
    print("="*60)
    
    passed = sum(test_results)
    total = len(test_results)
    
    test_names = [
        "성능 추적기 단독 테스트",
        "필터 매니저 통합 테스트", 
        "향상된 동적 필터 매니저 테스트",
        "보고서 파일 검증"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, test_results)):
        status = "[O] 통과" if result else "[X] 실패"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n총 {passed}/{total} 테스트 통과 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("[성공] 모든 테스트가 성공적으로 완료되었습니다!")
        print("\n[다음 단계]:")
        print("1. python main.py 실행하여 실제 필터링 과정에서 성능 데이터 수집")
        print("2. filter_performance_report.json 파일에서 실제 제외율 확인")
        print("3. 대시보드에서 실시간 모니터링 확인")
    else:
        print("[주의] 일부 테스트가 실패했습니다. 위의 오류 메시지를 확인하세요.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)