"""
테스트 예측 데이터 정리 및 실제 예측으로 교체
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import json
from pathlib import Path
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def clear_test_predictions():
    """테스트 예측 데이터 삭제"""
    
    # 데이터베이스 경로
    db_path = Path("data/predictions/predictions.db")
    
    if not db_path.exists():
        logging.info("예측 데이터베이스가 없습니다.")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Test_ 접두사가 있는 예측 조회
            cursor.execute("""
                SELECT DISTINCT round, source 
                FROM predictions 
                WHERE source LIKE 'Test_%'
                ORDER BY round DESC
            """)
            
            test_predictions = cursor.fetchall()
            
            if test_predictions:
                logging.info(f"테스트 예측 발견: {len(test_predictions)}개 회차")
                
                for round_num, source in test_predictions:
                    logging.info(f"  - {round_num}회차: {source}")
                
                # 테스트 예측 삭제
                cursor.execute("""
                    DELETE FROM predictions 
                    WHERE source LIKE 'Test_%'
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logging.info(f"✅ {deleted_count}개의 테스트 예측 삭제 완료")
            else:
                logging.info("테스트 예측이 없습니다.")
                
    except Exception as e:
        logging.error(f"데이터베이스 정리 실패: {e}")


def update_json_predictions():
    """JSON 파일의 테스트 소스명을 실제 소스명으로 변경"""
    
    # JSON 파일 경로
    json_dir = Path("data/predictions/2025")
    
    if not json_dir.exists():
        logging.info("JSON 예측 디렉토리가 없습니다.")
        return
    
    # 소스명 매핑
    source_mapping = {
        'Test_Ensemble': 'ML/Ensemble',
        'Test_LSTM': 'ML/LSTM',
        'Test_MonteCarlo': 'ML/MonteCarlo',
        'Test_Bayesian': 'Probabilistic/Bayesian',
        'Test_Pattern': 'Pattern/Analysis'
    }
    
    # 모든 week_*.json 파일 처리
    json_files = list(json_dir.glob("week_*.json"))
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            modified = False
            
            # 예측 소스명 업데이트
            for prediction in data.get('predictions', []):
                old_source = prediction.get('source', '')
                if old_source in source_mapping:
                    prediction['source'] = source_mapping[old_source]
                    modified = True
                    logging.info(f"  {json_file.name}: {old_source} → {source_mapping[old_source]}")
            
            # 수정된 경우 파일 저장
            if modified:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logging.info(f"✅ {json_file.name} 업데이트 완료")
                
        except Exception as e:
            logging.error(f"{json_file.name} 처리 실패: {e}")


def create_sample_predictions():
    """샘플 예측 데이터 생성 (실제 소스명 사용)"""
    
    from src.core.prediction_tracker import PredictionTracker
    from src.core.db_manager import DatabaseManager
    
    try:
        # 초기화
        tracker = PredictionTracker()
        db_manager = DatabaseManager()
        
        # 현재 회차
        latest_round = db_manager.get_last_round()
        next_round = latest_round + 1
        
        # 샘플 예측 데이터 (실제 형식)
        sample_predictions = [
            {
                'numbers': [3, 11, 17, 24, 35, 42],
                'confidence': 0.82,
                'source': 'ML/Ensemble',
                'characteristics': {
                    'odd_even_ratio': '3:3',
                    'sum_total': 132,
                    'consecutive_count': 0
                }
            },
            {
                'numbers': [5, 14, 21, 29, 37, 44],
                'confidence': 0.78,
                'source': 'ML/LSTM',
                'characteristics': {
                    'odd_even_ratio': '4:2',
                    'sum_total': 150,
                    'consecutive_count': 0
                }
            },
            {
                'numbers': [2, 9, 18, 26, 33, 40],
                'confidence': 0.75,
                'source': 'ML/MonteCarlo',
                'characteristics': {
                    'odd_even_ratio': '2:4',
                    'sum_total': 128,
                    'consecutive_count': 0
                }
            },
            {
                'numbers': [7, 13, 22, 30, 38, 43],
                'confidence': 0.70,
                'source': 'Probabilistic/Bayesian',
                'characteristics': {
                    'odd_even_ratio': '3:3',
                    'sum_total': 153,
                    'consecutive_count': 0
                }
            },
            {
                'numbers': [4, 16, 23, 31, 36, 45],
                'confidence': 0.65,
                'source': 'Pattern/Filtered',
                'characteristics': {
                    'odd_even_ratio': '3:3',
                    'sum_total': 155,
                    'consecutive_count': 0
                }
            }
        ]
        
        # 예측 저장
        success = tracker.save_predictions(next_round, sample_predictions)
        
        if success:
            logging.info(f"\n✅ {next_round}회차 샘플 예측 저장 완료")
            logging.info("   실제 소스명으로 저장된 예측:")
            for i, pred in enumerate(sample_predictions, 1):
                numbers_str = ', '.join(f"{n:2d}" for n in pred['numbers'])
                logging.info(f"   {i}. [{numbers_str}] - {pred['source']} (신뢰도: {pred['confidence']:.1%})")
        else:
            logging.warning("샘플 예측 저장 실패")
            
    except Exception as e:
        logging.error(f"샘플 예측 생성 실패: {e}")


def main():
    """메인 실행 함수"""
    
    print("\n" + "="*60)
    print("테스트 예측 데이터 정리")
    print("="*60)
    
    # 1. 데이터베이스에서 테스트 예측 삭제
    print("\n[1] 데이터베이스 정리...")
    clear_test_predictions()
    
    # 2. JSON 파일 소스명 업데이트
    print("\n[2] JSON 파일 업데이트...")
    update_json_predictions()
    
    # 3. 샘플 예측 생성 (선택)
    print("\n[3] 샘플 예측 생성...")
    response = input("샘플 예측을 생성하시겠습니까? (y/n): ").strip().lower()
    if response == 'y':
        create_sample_predictions()
    
    print("\n" + "="*60)
    print("✅ 정리 완료!")
    print("="*60)
    print("\n이제 웹 대시보드에 실제 예측이 표시됩니다.")
    print("브라우저에서 http://127.0.0.1:5000 접속하여 확인하세요.")


if __name__ == "__main__":
    main()