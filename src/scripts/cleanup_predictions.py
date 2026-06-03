"""
예측 데이터 정리 - 최신 5개만 유지
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def cleanup_json_predictions():
    """JSON 파일에서 최신 5개 예측만 유지"""
    
    json_file = Path("data/predictions/2025/week_1186.json")
    
    if not json_file.exists():
        logging.error(f"파일이 없습니다: {json_file}")
        return
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 현재 예측 개수
        current_count = len(data.get('predictions', []))
        logging.info(f"현재 예측 개수: {current_count}개")
        
        if current_count > 5:
            # 최신 5개만 유지 (뒤에서 5개 선택)
            data['predictions'] = data['predictions'][-5:]
            
            # set 번호 재정렬
            for i, pred in enumerate(data['predictions'], 1):
                pred['set'] = i
            
            # 파일 저장
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logging.info(f"[O] 최신 5개 예측만 유지 완료")
            
            # 정리된 예측 출력
            print("\n정리된 예측 (1186회차):")
            for pred in data['predictions']:
                numbers_str = ', '.join(f"{n:2d}" for n in pred['numbers'])
                print(f"  Set {pred['set']}: [{numbers_str}] - {pred['source']} (신뢰도: {pred['confidence']:.1%})")
        else:
            logging.info("이미 5개 이하의 예측만 있습니다.")
            
    except Exception as e:
        logging.error(f"파일 처리 실패: {e}")


def main():
    """메인 실행"""
    print("\n" + "="*60)
    print("예측 데이터 정리")
    print("="*60)
    
    cleanup_json_predictions()
    
    print("\n" + "="*60)
    print("완료!")
    print("="*60)


if __name__ == "__main__":
    main()