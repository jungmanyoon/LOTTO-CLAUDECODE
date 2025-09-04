"""
로또 예측 시스템 - 최종 예측 번호 추출 스크립트

필터링된 조합과 ML 예측 결과를 통합하여 최종 추천 번호를 생성합니다.
"""

import os
import sys
import json
import sqlite3
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Set
from datetime import datetime
import logging

# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager
from src.meta_data_manager import MetaDataManager
from src.logger import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class PredictionExtractor:
    """예측 번호 추출 및 통합 클래스"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.meta_manager = MetaDataManager()
        self.ml_predictions = {
            'lstm': [],
            'ensemble': [],
            'monte_carlo': [],
            'bayesian': [],
            'fractal': []
        }
        self.filtered_combinations = []
        
    def load_ml_predictions(self):
        """ML 예측 결과 로드 (로그에서 추출)"""
        logger.info("ML 예측 결과 로드 중...")
        
        # 로그 파일에서 예측 결과 추출 (실제 구현시 더 정교하게)
        # 여기서는 하드코딩된 값 사용 (로그에서 확인한 값)
        self.ml_predictions['lstm'] = [
            {'numbers': [3, 5, 11, 12, 14, 24], 'confidence': 0.1394},
            {'numbers': [1, 13, 35, 39, 42, 44], 'confidence': 0.1359},
            {'numbers': [4, 8, 9, 12, 24, 38], 'confidence': 0.1355}
        ]
        
        self.ml_predictions['ensemble'] = [
            {'numbers': [2, 12, 13, 27, 32, 33], 'confidence': 0.1976},
            {'numbers': [5, 16, 20, 22, 35, 36], 'confidence': 0.1851},
            {'numbers': [4, 22, 23, 24, 28, 43], 'confidence': 0.1826}
        ]
        
        self.ml_predictions['monte_carlo'] = [
            {'numbers': [11, 19, 22, 34, 43, 45], 'score': 49.90, 'confidence': 0.6844},
            {'numbers': [7, 13, 17, 22, 34, 45], 'score': 49.87, 'confidence': 0.6834},
            {'numbers': [11, 15, 20, 27, 34, 45], 'score': 49.72, 'confidence': 0.6784}
        ]
        
        self.ml_predictions['bayesian'] = [
            {'numbers': [7, 14, 33, 34, 39, 40], 'likelihood': 0.000000},
            {'numbers': [7, 13, 17, 21, 43, 45], 'likelihood': 0.000000},
            {'numbers': [3, 18, 31, 33, 37, 38], 'likelihood': 0.000000}
        ]
        
        self.ml_predictions['fractal'] = [
            {'numbers': [19, 21, 29, 36, 39, 43], 'confidence': 0.9355},
            {'numbers': [12, 20, 24, 26, 27, 35], 'confidence': 0.9033},
            {'numbers': [11, 16, 18, 21, 26, 36], 'confidence': 0.7601}
        ]
        
        logger.info(f"ML 예측 결과 로드 완료: {sum(len(pred) for pred in self.ml_predictions.values())}개")
        
    def load_filtered_combinations(self, limit: int = 100000):
        """필터링된 조합 로드"""
        logger.info("필터링된 조합 로드 중...")
        
        try:
            # 최종 필터링된 조합 가져오기 - 직접 sqlite3 연결
            import sqlite3
            conn = sqlite3.connect('data/combinations.db')
            cursor = conn.cursor()
            
            # 필터링된 조합 수 확인
            cursor.execute("SELECT COUNT(*) FROM filtered_combinations WHERE round = 1182")
            count = cursor.fetchone()[0]
            logger.info(f"총 필터링된 조합 수: {count:,}개")
            
            # 무작위로 일부 샘플링 (메모리 제한)
            cursor.execute("""
                SELECT combination 
                FROM filtered_combinations 
                WHERE round = 1182
                ORDER BY RANDOM()
                LIMIT ?
            """, (limit,))
            
            self.filtered_combinations = [row[0] for row in cursor.fetchall()]
            logger.info(f"샘플링된 조합 수: {len(self.filtered_combinations):,}개")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"필터링된 조합 로드 실패: {str(e)}")
            self.filtered_combinations = []
            
    def calculate_combination_score(self, combination: List[int]) -> float:
        """조합의 종합 점수 계산"""
        score = 0.0
        
        # 1. 과거 당첨번호와의 유사도
        winning_numbers = self.db_manager.get_all_winning_numbers()
        if winning_numbers:
            recent_winners = winning_numbers[-50:]  # 최근 50회차
            for winner in recent_winners:
                match_count = len(set(combination) & set(winner))
                if match_count >= 3:  # 3개 이상 일치
                    score += match_count * 10
                    
        # 2. 번호 간격 균형도
        gaps = [combination[i+1] - combination[i] for i in range(5)]
        avg_gap = np.mean(gaps)
        if 5 <= avg_gap <= 8:  # 이상적인 간격
            score += 20
            
        # 3. 홀짝 균형
        odd_count = sum(1 for n in combination if n % 2 == 1)
        if 2 <= odd_count <= 4:  # 2:4, 3:3, 4:2 비율
            score += 15
            
        # 4. 구간 분포
        sections = [0, 0, 0]  # 1-15, 16-30, 31-45
        for n in combination:
            if n <= 15:
                sections[0] += 1
            elif n <= 30:
                sections[1] += 1
            else:
                sections[2] += 1
        
        if all(1 <= s <= 3 for s in sections):  # 각 구간에서 1-3개
            score += 15
            
        # 5. 합계 범위
        total_sum = sum(combination)
        if 100 <= total_sum <= 170:  # 이상적인 합계 범위
            score += 10
            
        return score
        
    def integrate_predictions(self, top_n: int = 10) -> List[Dict]:
        """ML 예측과 필터링 결과 통합"""
        logger.info("예측 결과 통합 중...")
        
        integrated_results = []
        
        # 1. ML 예측 조합들의 점수 계산
        for model_name, predictions in self.ml_predictions.items():
            for pred in predictions:
                combination = pred['numbers']
                base_score = self.calculate_combination_score(combination)
                
                # 모델별 가중치 적용
                model_weight = {
                    'lstm': 1.0,
                    'ensemble': 1.5,
                    'monte_carlo': 2.0,
                    'bayesian': 0.8,
                    'fractal': 1.8
                }.get(model_name, 1.0)
                
                # 신뢰도 적용
                confidence = pred.get('confidence', pred.get('score', 0) / 100)
                final_score = base_score * model_weight * (1 + confidence)
                
                integrated_results.append({
                    'combination': combination,
                    'model': model_name,
                    'confidence': confidence,
                    'base_score': base_score,
                    'final_score': final_score
                })
        
        # 2. 필터링된 조합 중 상위 점수 조합 추가
        logger.info("필터링된 조합 점수 계산 중...")
        for combo_str in self.filtered_combinations[:1000]:  # 상위 1000개만 계산
            combination = [int(n) for n in combo_str.split(',')]
            score = self.calculate_combination_score(combination)
            
            integrated_results.append({
                'combination': combination,
                'model': 'filtered',
                'confidence': 0.5,  # 기본 신뢰도
                'base_score': score,
                'final_score': score * 0.8  # 필터링 결과는 약간 낮은 가중치
            })
        
        # 3. 중복 제거 및 정렬
        unique_combinations = {}
        for result in integrated_results:
            combo_key = tuple(result['combination'])
            if combo_key not in unique_combinations or result['final_score'] > unique_combinations[combo_key]['final_score']:
                unique_combinations[combo_key] = result
        
        # 점수 기준 정렬
        sorted_results = sorted(unique_combinations.values(), key=lambda x: x['final_score'], reverse=True)
        
        return sorted_results[:top_n]
        
    def display_results(self, results: List[Dict]):
        """결과 출력"""
        print("\n" + "="*60)
        print("로또 예측 시스템 - 최종 추천 번호")
        print("="*60)
        
        for i, result in enumerate(results, 1):
            combination = result['combination']
            model = result['model']
            confidence = result['confidence']
            final_score = result['final_score']
            
            # 번호 문자열 생성
            numbers_str = ", ".join(f"{n:2d}" for n in combination)
            
            # 모델 이름 포맷팅
            model_display = {
                'lstm': 'LSTM 시계열',
                'ensemble': '앙상블 모델',
                'monte_carlo': 'Monte Carlo',
                'bayesian': '베이지안',
                'fractal': '프랙탈 분석',
                'filtered': '필터 통과'
            }.get(model, model)
            
            print(f"\n{i}. [{numbers_str}]")
            print(f"   - 예측 모델: {model_display}")
            print(f"   - 신뢰도: {confidence:.1%}")
            print(f"   - 종합 점수: {final_score:.1f}")
            
            # 특성 분석
            odd_count = sum(1 for n in combination if n % 2 == 1)
            total_sum = sum(combination)
            print(f"   - 특성: 홀{odd_count}/짝{6-odd_count}, 합계 {total_sum}")
            
        print("\n" + "="*60)
        print("※ 주의: 로또는 확률 게임입니다. 과도한 투자는 피하세요.")
        print("="*60)
        
    def save_results(self, results: List[Dict]):
        """결과를 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"predictions_{timestamp}.json"
        
        output_data = {
            'generated_at': timestamp,
            'round': self.meta_manager.get_last_filtered_round(),
            'predictions': []
        }
        
        for result in results:
            output_data['predictions'].append({
                'numbers': result['combination'],
                'model': result['model'],
                'confidence': float(result['confidence']),
                'score': float(result['final_score'])
            })
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"예측 결과 저장 완료: {filename}")
        
    def run(self):
        """메인 실행 함수"""
        logger.info("최종 예측 번호 추출 시작...")
        
        # 1. 데이터 로드
        self.load_ml_predictions()
        self.load_filtered_combinations(limit=10000)  # 메모리 제한으로 10,000개만
        
        # 2. 예측 통합
        final_results = self.integrate_predictions(top_n=10)
        
        # 3. 결과 출력
        self.display_results(final_results)
        
        # 4. 결과 저장
        self.save_results(final_results)
        
        logger.info("최종 예측 번호 추출 완료!")


if __name__ == "__main__":
    extractor = PredictionExtractor()
    extractor.run()