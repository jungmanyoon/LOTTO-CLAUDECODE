#!/usr/bin/env python3
"""
자동 조정 시스템 테스트 스크립트
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from datetime import datetime
import json
import yaml

from src.core.db_manager import DatabaseManager
from src.core.auto_adjustment_system import AutoAdjustmentSystem

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/test_auto_adjustment.log', encoding='utf-8')
    ]
)

def test_auto_adjustment():
    """자동 조정 시스템 테스트"""
    print("\n" + "="*60)
    print("[TEST] 자동 조정 시스템 테스트")
    print("="*60)
    
    try:
        # 1. 시스템 초기화
        print("\n1. 시스템 초기화 중...")
        db_manager = DatabaseManager()
        auto_system = AutoAdjustmentSystem(db_manager)
        print("[OK] 시스템 초기화 완료")
        
        # 2. 현재 상태 확인
        print("\n2. 현재 상태 확인")
        latest_round = db_manager.lotto_db.get_last_round()
        print(f"   - 현재 DB 최신 회차: {latest_round}")
        
        # 3. 패턴 분석 테스트
        print("\n3. 최근 패턴 분석 실행...")
        pattern_analysis = auto_system._analyze_recent_patterns()
        
        print("\n[분석] 패턴 분석 결과:")
        if 'patterns' in pattern_analysis:
            patterns = pattern_analysis['patterns']
            
            # 핫넘버
            if 'hot_numbers' in patterns:
                hot_info = patterns['hot_numbers']
                print(f"\n[HOT] 핫넘버 (평균 출현 {hot_info['avg_frequency']:.1f}회 이상):")
                print(f"   {hot_info['numbers']}")
            
            # 콜드넘버
            if 'cold_numbers' in patterns:
                cold_info = patterns['cold_numbers']
                print(f"\n[COLD] 콜드넘버:")
                print(f"   {cold_info['numbers'][:10]}...")  # 처음 10개만
            
            # 합계 범위
            if 'sum_range' in patterns:
                sum_info = patterns['sum_range']
                print(f"\n[SUM] 합계 통계:")
                print(f"   - 평균: {sum_info['mean']:.1f}")
                print(f"   - 범위: {sum_info['min']} ~ {sum_info['max']}")
                print(f"   - 추천 범위: {sum_info['percentile_10']:.0f} ~ {sum_info['percentile_90']:.0f}")
            
            # 연속번호
            if 'consecutive' in patterns:
                cons_info = patterns['consecutive']
                print(f"\n[SEQ] 연속번호:")
                print(f"   - 평균 개수: {cons_info['avg_count']:.2f}")
                print(f"   - 출현 빈도: {cons_info['frequency']:.1%}")
            
            # AC값
            if 'ac_value' in patterns:
                ac_info = patterns['ac_value']
                print(f"\n[AC] AC값 (Arithmetic Complexity):")
                print(f"   - 평균: {ac_info['avg']:.1f}")
                print(f"   - 권장 범위: {ac_info['common_range'][0]:.0f} ~ {ac_info['common_range'][1]:.0f}")
        
        # 4. 필터 조정 시뮬레이션
        print("\n\n4. 필터 조정 시뮬레이션...")
        
        # 조정 필요성 판단
        should_adjust = auto_system._should_adjust_filters(pattern_analysis)
        print(f"   - 조정 필요: {'예' if should_adjust else '아니오'}")
        
        if should_adjust or True:  # 테스트를 위해 강제 실행
            # 필터 조정값 계산
            adjustments = auto_system._adjust_filter_criteria(pattern_analysis)
            
            print("\n[FILTER] 조정 예정 필터:")
            for filter_name, criteria in adjustments.items():
                print(f"\n   [{filter_name}]")
                for key, value in criteria.items():
                    print(f"     - {key}: {value}")
            
            # 현재 설정과 비교
            print("\n5. 현재 설정과 비교")
            with open('config.yaml', 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)
            
            current_filters = current_config.get('filters', {})
            
            print("\n[CHANGE] 변경 사항:")
            for filter_name, new_criteria in adjustments.items():
                if filter_name in current_filters:
                    current = current_filters[filter_name]
                    print(f"\n   [{filter_name}]")
                    for key, new_value in new_criteria.items():
                        old_value = current.get(key, 'N/A')
                        if old_value != new_value:
                            print(f"     {key}: {old_value} → {new_value} [변경]")
                        else:
                            print(f"     {key}: {old_value} (변경 없음)")
                else:
                    print(f"\n   [{filter_name}] [NEW] 새로운 필터")
        
        # 6. 전체 프로세스 테스트
        print("\n\n6. 전체 자동 조정 프로세스 실행")
        
        # 자동 모드로 실행 (테스트용)
        import sys
        if hasattr(sys, 'argv') and len(sys.argv) > 1 and sys.argv[1] == '--auto':
            choice = 'n'  # 자동 모드에서는 실제 조정 스킵
            print("   [자동 모드] 실제 조정은 스킵합니다.")
        else:
            try:
                choice = input("   실제로 조정을 실행하시겠습니까? (y/n): ")
            except EOFError:
                choice = 'n'
                print("   [비대화형 모드] 실제 조정은 스킵합니다.")
        
        if choice.lower() == 'y':
            print("\n   조정 실행 중...")
            results = auto_system.check_and_adjust()
            
            print("\n[OK] 조정 완료!")
            print(f"   - 새 데이터: {'있음' if results['new_data'] else '없음'}")
            print(f"   - 필터 조정: {'완료' if results['filters_adjusted'] else '미실행'}")
            print(f"   - 모델 업데이트: {'완료' if results['models_updated'] else '미실행'}")
            
            if results['filters_adjusted']:
                print(f"   - 조정된 필터 수: {len(results.get('filter_adjustments', {}))}")
        
        # 7. 상태 보고서
        print("\n7. 시스템 상태 보고서")
        print(auto_system.get_status_report())
        
        # 8. 조정 이력 확인
        history_path = 'results/adjustment_history.json'
        if os.path.exists(history_path):
            print(f"\n8. 조정 이력 저장 위치: {history_path}")
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
                if history:
                    print(f"   - 총 조정 횟수: {len(history)}")
                    print(f"   - 마지막 조정: {history[-1]['timestamp']}")
        
        print("\n" + "="*60)
        print("[OK] 테스트 완료!")
        print("="*60)
        
    except Exception as e:
        print(f"\n[ERROR] 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_auto_adjustment()