#!/usr/bin/env python3
"""
백테스팅 JSON 결과를 데이터베이스로 마이그레이션하는 스크립트
"""

import json
import os
import glob
import sys
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append('src')

from core.performance_stats_manager import PerformanceStatsManager

def find_latest_backtest_results():
    """가장 최근 백테스팅 결과 파일 찾기"""
    pattern = "results/backtest_results_optimized_*.json"
    files = glob.glob(pattern)
    
    if not files:
        print("[X] 백테스팅 결과 파일을 찾을 수 없습니다.")
        return None
    
    # 가장 최근 파일 선택 (파일명의 날짜 기준)
    latest_file = max(files, key=os.path.getctime)
    print(f"[O] 최신 백테스팅 결과 파일: {latest_file}")
    return latest_file

def convert_json_to_db_format(json_data):
    """JSON 데이터를 PerformanceStatsManager 형식으로 변환"""
    try:
        # JSON 데이터에서 필요한 정보 추출
        performance_metrics = {}
        total_rounds = json_data.get('total_rounds', 0)
        
        # 모델별 성능 데이터 추출
        model_performance = {}
        predictions = json_data.get('predictions', [])
        
        if predictions:
            # 모델별 성능 통계 계산
            models = set()
            for pred in predictions:
                for model_name in pred.get('matches', {}).keys():
                    models.add(model_name)
            
            for model_name in models:
                model_stats = {
                    'total_predictions': 0,
                    'avg_matches': 0,
                    'best_match': 0,
                    'accuracy_3plus': 0,
                    'contaminated_count': 0,
                    'match_counts': {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
                }
                
                total_matches = 0
                three_plus_count = 0
                contaminated = 0
                
                for pred in predictions:
                    matches_info = pred.get('matches', {}).get(model_name, [])
                    for match_info in matches_info:
                        match_count = match_info.get('match_count', 0)
                        model_stats['total_predictions'] += 1
                        model_stats['match_counts'][match_count] += 1
                        total_matches += match_count
                        
                        if match_count >= 3:
                            three_plus_count += 1
                        
                        if match_info.get('contaminated', False):
                            contaminated += 1
                        
                        if match_count > model_stats['best_match']:
                            model_stats['best_match'] = match_count
                
                # 평균 계산
                if model_stats['total_predictions'] > 0:
                    model_stats['avg_matches'] = total_matches / model_stats['total_predictions']
                    model_stats['accuracy_3plus'] = (three_plus_count / model_stats['total_predictions']) * 100
                
                model_stats['contaminated_count'] = contaminated
                model_performance[model_name.upper()] = model_stats
        
        performance_metrics = {
            'total_rounds': total_rounds,
            'model_performance': model_performance
        }
        
        # PerformanceStatsManager가 요구하는 형식으로 변환
        converted_data = {
            'performance_metrics': performance_metrics,
            'predictions': predictions
        }
        
        return converted_data
        
    except Exception as e:
        print(f"[X] 데이터 변환 오류: {e}")
        return None

def migrate_backtest_data():
    """백테스팅 데이터 마이그레이션"""
    print("\n" + "="*50)
    print("백테스팅 데이터 마이그레이션 시작")
    print("="*50)
    
    # 1. 최신 백테스팅 결과 파일 찾기
    latest_file = find_latest_backtest_results()
    if not latest_file:
        return False
    
    # 2. JSON 데이터 로드
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        print(f"[O] JSON 데이터 로드 완료: {len(json_data.get('predictions', []))}개 예측")
    except Exception as e:
        print(f"[X] JSON 파일 로드 실패: {e}")
        return False
    
    # 3. 데이터 변환
    converted_data = convert_json_to_db_format(json_data)
    if not converted_data:
        return False
    
    print(f"[O] 데이터 변환 완료")
    print(f"   - 모델 수: {len(converted_data['performance_metrics']['model_performance'])}")
    print(f"   - 총 라운드: {converted_data['performance_metrics']['total_rounds']}")
    
    # 4. 데이터베이스에 저장
    try:
        stats_manager = PerformanceStatsManager()
        session_id = stats_manager.save_backtest_results(converted_data)
        
        if session_id > 0:
            print(f"[O] 데이터베이스 저장 완료 (세션 ID: {session_id})")
            
            # 저장된 데이터 검증
            summary = stats_manager.get_model_performance_summary()
            print(f"[O] 검증 완료:")
            print(f"   - 총 세션: {summary.get('overall', {}).get('total_sessions', 0)}")
            print(f"   - 모델 수: {len(summary.get('by_model', []))}")
            
            return True
        else:
            print("[X] 데이터베이스 저장 실패")
            return False
            
    except Exception as e:
        print(f"[X] 데이터베이스 저장 중 오류: {e}")
        return False

if __name__ == "__main__":
    success = migrate_backtest_data()
    
    if success:
        print("\n[O] 마이그레이션 완료!")
        print("   대시보드에서 백테스팅 결과를 확인할 수 있습니다.")
    else:
        print("\n[X] 마이그레이션 실패!")
    
    print("="*50)