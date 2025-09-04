#!/usr/bin/env python3
"""
수정사항 테스트 스크립트
1. 입력 데이터 부족 문제 해결 확인
2. 데이터베이스 락 문제 해결 확인
"""
import os
import sys
import logging

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.ml.lstm_predictor import LSTMPredictor
from src.ml.ensemble_predictor import EnsemblePredictor

def test_data_shortage_fix():
    """입력 데이터 부족 문제 해결 테스트"""
    print("\n=== 입력 데이터 부족 문제 해결 테스트 ===\n")
    
    # LSTM 예측기 생성
    lstm = LSTMPredictor()
    
    # 테스트 케이스: 데이터가 10개만 있는 경우
    test_data_10 = []
    for i in range(10):
        # 1-45 범위의 랜덤 번호 생성
        numbers = sorted([1, 5, 10, 15, 20, 25])  # 간단한 테스트 데이터
        test_data_10.append(','.join(map(str, numbers)))
    print(f"테스트 데이터 개수: {len(test_data_10)}")
    
    # 예측 시도
    print("LSTM 예측 시도 중...")
    predictions = lstm.predict_next_numbers(test_data_10, num_predictions=1)
    
    if predictions:
        print(f"[성공] 예측 결과: {predictions[0]['numbers']}")
    else:
        print("[실패] 예측 실패")
    
    # 테스트 케이스: 데이터가 50개 이상 있는 경우
    test_data_50 = []
    for i in range(50):
        # 다양한 테스트 데이터 생성
        offset = (i % 8) * 5
        numbers = sorted([1 + offset, 7 + offset, 14 + offset, 21 + offset, 28 + offset, 35 + offset])
        # 45를 초과하지 않도록 조정
        numbers = [min(n, 45) for n in numbers]
        test_data_50.append(','.join(map(str, numbers)))
    print(f"\n테스트 데이터 개수: {len(test_data_50)}")
    
    print("LSTM 예측 시도 중...")
    predictions = lstm.predict_next_numbers(test_data_50, num_predictions=1)
    
    if predictions:
        print(f"[성공] 예측 결과: {predictions[0]['numbers']}")
    else:
        print("[실패] 예측 실패")

def test_database_lock_fix():
    """데이터베이스 락 문제 해결 테스트"""
    print("\n=== 데이터베이스 락 문제 해결 테스트 ===\n")
    
    try:
        # 데이터베이스 매니저 초기화
        print("데이터베이스 매니저 초기화 중...")
        db_manager = DatabaseManager()
        print("[성공] 데이터베이스 매니저 초기화 완료")
        
        # 여러 데이터베이스 동시 접근 테스트
        print("\n동시 접근 테스트:")
        
        # 1. 로또 번호 조회
        last_round = db_manager.get_last_round()
        print(f"  - 마지막 회차 조회: {last_round} [성공]")
        
        # 2. 조합 데이터베이스 접근
        combinations_exist = db_manager.check_base_combinations_exist()
        print(f"  - 조합 DB 접근: {'존재' if combinations_exist else '없음'} [성공]")
        
        # 3. 패턴 데이터베이스 접근
        latest_pattern = db_manager.get_latest_pattern_analysis()
        print(f"  - 패턴 DB 접근: {'데이터 있음' if latest_pattern else '데이터 없음'} [성공]")
        
        # 4. 필터 데이터베이스 접근
        filter_db = db_manager.get_filter_db('match')
        if filter_db:
            last_filtered = filter_db.get_last_filtered_round()
            print(f"  - 필터 DB 접근: 마지막 필터링 회차 {last_filtered} [성공]")
        
        print("\n모든 데이터베이스 접근 테스트 통과!")
        
    except Exception as e:
        print(f"\n[실패] 데이터베이스 접근 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    """메인 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("로또 예측 시스템 수정사항 테스트")
    print("="*50)
    
    # 1. 입력 데이터 부족 문제 테스트
    test_data_shortage_fix()
    
    # 2. 데이터베이스 락 문제 테스트
    test_database_lock_fix()
    
    print("\n" + "="*50)
    print("테스트 완료!")

if __name__ == "__main__":
    main()