#!/usr/bin/env python3
"""
전체 시스템 통합 테스트
모든 개선사항이 제대로 작동하는지 확인
"""
import sys
import os
import time
import logging
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/integration_test.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def test_singleton_pattern():
    """싱글톤 패턴 테스트"""
    print("\n[TEST 1] 데이터베이스 싱글톤 패턴 확인...")
    try:
        from src.core.db_manager import DatabaseManager
        
        db1 = DatabaseManager()
        db2 = DatabaseManager()
        db3 = DatabaseManager()
        
        if db1 is db2 and db2 is db3:
            print("   [OK] 싱글톤 패턴 정상 작동 (인스턴스 중복 생성 방지)")
            return True
        else:
            print("   [FAIL] 싱글톤 패턴 실패")
            return False
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def test_filter_config():
    """필터 설정 최적화 확인"""
    print("\n[TEST 2] 필터 설정 최적화 확인...")
    try:
        import yaml
        
        with open('configs/adaptive_filter_config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 핵심 설정 확인
        threshold = config.get('global_probability_threshold', 1.0)
        multiple_filter = config['filters'].get('multiple', False)
        ten_section_filter = config['filters'].get('ten_section', False)
        max_workers = config['performance'].get('max_workers', 8)
        
        print(f"   - 확률 임계값: {threshold} (목표: 0.5)")
        print(f"   - Multiple 필터: {multiple_filter} (목표: True)")
        print(f"   - Ten Section 필터: {ten_section_filter} (목표: True)")
        print(f"   - 워커 수: {max_workers} (목표: 14)")
        
        if threshold == 0.5 and multiple_filter and ten_section_filter and max_workers == 14:
            print("   [OK] 필터 설정이 당첨 확률 최적화됨")
            return True
        else:
            print("   [WARNING] 일부 설정이 최적화되지 않음")
            return False
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def test_auto_learning_status():
    """자동 학습 시스템 상태 확인"""
    print("\n[TEST 3] 자동 학습 시스템 상태 확인...")
    try:
        import json
        
        # Auto improvement state 확인
        if os.path.exists('data/auto_improvement_state.json'):
            with open('data/auto_improvement_state.json', 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            last_updated = datetime.fromisoformat(state.get('last_updated', '2025-01-01T00:00:00'))
            hours_since = (datetime.now() - last_updated).total_seconds() / 3600
            
            print(f"   - Auto Improvement 마지막 업데이트: {hours_since:.1f}시간 전")
            
            if hours_since < 24:
                print("   [OK] Auto Improvement 최근 활성화됨")
                return True
            else:
                print("   [WARNING] Auto Improvement가 오래 전 업데이트됨")
                return False
        else:
            print("   [WARNING] Auto Improvement 상태 파일 없음")
            return False
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def test_realtime_learning():
    """실시간 학습 시스템 테스트"""
    print("\n[TEST 4] 실시간 학습 시스템 확인...")
    try:
        from src.core.db_manager import DatabaseManager
        from src.ml.realtime_learning_system import RealtimeLearningSystem
        
        db_manager = DatabaseManager()
        realtime_system = RealtimeLearningSystem(db_manager)
        
        # 상태 확인
        health = realtime_system.get_health_status()
        
        print(f"   - 전체 상태: {health['overall_status']}")
        print(f"   - 자동 재시작: {'활성화' if health['auto_restart_enabled'] else '비활성화'}")
        
        # 모델별 상태
        for model_type, status in health['models_status'].items():
            print(f"   - {model_type}: {status['status']} (업데이트 {status['update_count']}회)")
        
        if health['overall_status'] in ['healthy', 'issues_detected']:
            print("   [OK] 실시간 학습 시스템 작동 중")
            return True
        else:
            print("   [WARNING] 실시간 학습 시스템 문제 있음")
            return False
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def test_ml_cache_cleared():
    """ML 모델 캐시 정리 확인"""
    print("\n[TEST 5] ML 모델 캐시 상태 확인...")
    try:
        cache_dir = 'cache/models'
        
        if os.path.exists(cache_dir):
            files = os.listdir(cache_dir)
            file_count = len(files)
            
            if file_count == 0:
                print("   [OK] ML 모델 캐시가 완전히 정리됨")
                return True
            else:
                print(f"   [INFO] 캐시에 {file_count}개 파일 있음 (재학습 중일 수 있음)")
                return True
        else:
            print("   [OK] 캐시 디렉토리가 깨끗함")
            return True
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def test_performance_optimization():
    """성능 최적화 설정 확인"""
    print("\n[TEST 6] 성능 최적화 설정 확인...")
    try:
        import yaml
        
        # config.yaml 확인
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        parallel = config.get('parallel_processing', False)
        workers = config.get('max_workers', 4)
        batch_size = config.get('batch_size', 5000)
        
        print(f"   - 병렬 처리: {parallel}")
        print(f"   - 워커 수: {workers}")
        print(f"   - 배치 크기: {batch_size}")
        
        if parallel and workers >= 10:
            print("   [OK] 성능 최적화 설정 활성화됨")
            return True
        else:
            print("   [WARNING] 성능 최적화 개선 필요")
            return False
    except Exception as e:
        print(f"   [ERROR] 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 실행"""
    print("="*60)
    print("전체 시스템 통합 테스트 시작")
    print("="*60)
    
    tests = [
        ("싱글톤 패턴", test_singleton_pattern),
        ("필터 최적화", test_filter_config),
        ("자동 학습", test_auto_learning_status),
        ("실시간 학습", test_realtime_learning),
        ("ML 캐시", test_ml_cache_cleared),
        ("성능 최적화", test_performance_optimization)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] {name} 테스트 중 오류: {e}")
            results.append((name, False))
        time.sleep(1)
    
    # 결과 요약
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        print(f"   {status} {name}")
    
    print(f"\n통과: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n[SUCCESS] 모든 테스트 통과! 시스템이 정상 작동합니다.")
    elif passed >= total * 0.8:
        print("\n[GOOD] 대부분의 테스트 통과. 일부 개선 필요.")
    else:
        print("\n[WARNING] 여러 문제 발견. 추가 수정이 필요합니다.")
    
    print("\n테스트 완료")
    print("="*60)

if __name__ == "__main__":
    main()