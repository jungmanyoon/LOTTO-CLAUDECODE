"""
최종 예측 통합 시스템

ML 예측 유사도와 캐스케이드 필터링 결과를 통합하여
최종 추천 번호를 생성합니다.
"""

import os
import sys
import sqlite3
import json
import numpy as np
from typing import List, Dict, Tuple, Set
from datetime import datetime
import logging

# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.logger import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class FinalPredictionIntegrator:
    """최종 예측 통합 클래스"""
    
    def __init__(self, top_n: int = 10):
        self.top_n = top_n
        self.ml_predictions = self.load_ml_predictions()
        self.conn = sqlite3.connect('data/combinations.db')
        
    def load_ml_predictions(self) -> List[List[int]]:
        """ML 예측 결과 로드"""
        try:
            with open('predictions_20250728_185706.json', 'r') as f:
                data = json.load(f)
            return [pred['numbers'] for pred in data['predictions']]
        except Exception as e:
            logging.error(f"예측 통합 실패: {e}")
            return [
                [7, 13, 17, 22, 34, 45],
                [11, 15, 20, 27, 34, 45],
                [11, 19, 22, 34, 43, 45]
            ]
            
    def load_cascade_filtered(self) -> List[str]:
        """캐스케이드 필터링 결과 로드"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT combination 
            FROM cascade_filtered_combinations 
            WHERE round = 1182
            LIMIT 10000
        """)
        return [row[0] for row in cursor.fetchall()]
        
    def load_ml_similarity_filtered(self) -> List[Tuple[str, float]]:
        """ML 유사도 기반 필터링 결과 로드"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT combination, score 
            FROM top_filtered_combinations 
            WHERE round = 1182
            ORDER BY score DESC
            LIMIT 10000
        """)
        return [(row[0], row[1]) for row in cursor.fetchall()]
        
    def calculate_comprehensive_score(self, combo_str: str) -> float:
        """종합 점수 계산"""
        numbers = [int(n) for n in combo_str.split(',')]
        score = 0.0
        
        # 1. ML 예측과의 유사도 (40%)
        ml_score = 0
        for pred in self.ml_predictions:
            common = len(set(numbers) & set(pred))
            ml_score += common * 15
            
            sorted_nums = sorted(numbers)
            sorted_pred = sorted(pred)
            diff = sum(abs(sorted_nums[i] - sorted_pred[i]) for i in range(6)) / 6
            ml_score += max(0, 40 - diff)
            
        score += (ml_score / len(self.ml_predictions)) * 0.4
        
        # 2. 통계적 특성 점수 (30%)
        stat_score = 0
        
        # 합계 범위 (이상적: 130-140)
        total_sum = sum(numbers)
        if 130 <= total_sum <= 140:
            stat_score += 25
        elif 120 <= total_sum <= 150:
            stat_score += 15
        elif 110 <= total_sum <= 160:
            stat_score += 5
            
        # 홀짝 균형 (이상적: 3:3)
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        if odd_count == 3:
            stat_score += 25
        elif odd_count in [2, 4]:
            stat_score += 15
            
        # 분산도
        std_dev = np.std(numbers)
        if 11 <= std_dev <= 12:
            stat_score += 25
        elif 10 <= std_dev <= 13:
            stat_score += 15
            
        # 구간 균형
        sections = [0, 0, 0]  # 1-15, 16-30, 31-45
        low_numbers = 0  # 1-6 개수
        for n in numbers:
            if n <= 6:
                low_numbers += 1
            if n <= 15:
                sections[0] += 1
            elif n <= 30:
                sections[1] += 1
            else:
                sections[2] += 1
                
        if all(1 <= s <= 3 for s in sections):
            stat_score += 20
            
        # 낮은 번호대(1-6) 보너스
        if low_numbers >= 1:
            stat_score += 10  # 최소 1개 포함 시 보너스
        if low_numbers == 2:
            stat_score += 5   # 2개일 때 추가 보너스
            
        score += stat_score * 0.3
        
        # 3. 역대 당첨 패턴 점수 (30%)
        pattern_score = 0
        
        # 연속 번호 제한
        sorted_nums = sorted(numbers)
        max_consecutive = 1
        current_consecutive = 1
        for i in range(1, len(sorted_nums)):
            if sorted_nums[i] == sorted_nums[i-1] + 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
                
        if max_consecutive <= 2:
            pattern_score += 30
        elif max_consecutive == 3:
            pattern_score += 10
            
        # 간격 패턴
        gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
        if 2 <= min(gaps) <= 3 and 10 <= max(gaps) <= 15:
            pattern_score += 30
            
        # 끝자리 다양성
        last_digits = set(n % 10 for n in numbers)
        if len(last_digits) >= 4:
            pattern_score += 20
            
        # 10단위 숫자 제한
        tens = sum(1 for n in numbers if n % 10 == 0)
        if tens <= 1:
            pattern_score += 20
            
        score += pattern_score * 0.3
        
        return score
        
    def integrate_predictions(self) -> List[Tuple[str, float, str]]:
        """예측 결과 통합"""
        logger.info("예측 결과 통합 시작...")
        
        # 1. 캐스케이드 필터링 결과 로드
        cascade_filtered = self.load_cascade_filtered()
        cascade_set = set(cascade_filtered)
        logger.info(f"캐스케이드 필터링 결과: {len(cascade_filtered)}개")
        
        # 2. ML 유사도 필터링 결과 로드
        ml_filtered = self.load_ml_similarity_filtered()
        logger.info(f"ML 유사도 필터링 결과: {len(ml_filtered)}개")
        
        # 3. 교집합 찾기
        intersection_combos = []
        for combo, ml_score in ml_filtered:
            if combo in cascade_set:
                comprehensive_score = self.calculate_comprehensive_score(combo)
                intersection_combos.append((combo, comprehensive_score, "교집합"))
                
        logger.info(f"교집합 조합: {len(intersection_combos)}개")
        
        # 4. 교집합이 부족하면 각각의 최상위 조합 추가
        final_combos = intersection_combos[:]
        
        if len(final_combos) < self.top_n:
            # ML 최상위 추가
            for combo, ml_score in ml_filtered[:50]:
                if combo not in cascade_set and len(final_combos) < self.top_n * 2:
                    comprehensive_score = self.calculate_comprehensive_score(combo)
                    final_combos.append((combo, comprehensive_score, "ML상위"))
                    
            # 캐스케이드 최상위 추가
            for combo in cascade_filtered[:50]:
                if len(final_combos) < self.top_n * 2:
                    found = False
                    for existing_combo, _, _ in final_combos:
                        if existing_combo == combo:
                            found = True
                            break
                    if not found:
                        comprehensive_score = self.calculate_comprehensive_score(combo)
                        final_combos.append((combo, comprehensive_score, "캐스케이드"))
                        
        # 5. 종합 점수로 정렬
        final_combos.sort(key=lambda x: x[1], reverse=True)
        
        return final_combos[:self.top_n]
        
    def analyze_numbers_frequency(self, combinations: List[Tuple[str, float, str]]) -> Dict[int, int]:
        """추천 조합의 번호 빈도 분석"""
        frequency = {}
        for combo_str, _, _ in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            for num in numbers:
                frequency[num] = frequency.get(num, 0) + 1
        return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True))
        
    def print_final_recommendations(self, recommendations: List[Tuple[str, float, str]]):
        """최종 추천 결과 출력"""
        print("\n" + "="*70)
        print("로또 번호 최종 추천 (AI + 통계 분석 통합)")
        print("="*70)
        print(f"\n분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"추천 조합 수: {len(recommendations)}개\n")
        
        for i, (combo, score, source) in enumerate(recommendations, 1):
            numbers = combo.split(',')
            print(f"{i:2d}. {' - '.join(numbers):25} (점수: {score:5.1f}, 출처: {source})")
            
        # 번호 빈도 분석
        frequency = self.analyze_numbers_frequency(recommendations)
        
        print("\n[자주 나타나는 번호 TOP 10]")
        for num, count in list(frequency.items())[:10]:
            print(f"  {num:2d}번: {count}회 ({count/len(recommendations)*100:.0f}%)")
            
        # 통계 요약
        all_numbers = []
        for combo_str, _, _ in recommendations:
            all_numbers.extend([int(n) for n in combo_str.split(',')])
            
        print("\n[추천 번호 통계]")
        print(f"  - 평균: {np.mean(all_numbers):.1f}")
        if frequency:
            print(f"  - 최빈값 구간: {min(frequency, key=frequency.get)}-{max(frequency, key=frequency.get)}")
        
        # 구간별 분포
        sections = [0, 0, 0]
        for num in all_numbers:
            if num <= 15:
                sections[0] += 1
            elif num <= 30:
                sections[1] += 1
            else:
                sections[2] += 1
                
        total = sum(sections)
        if total > 0:
            print(f"\n[구간별 분포]")
            print(f"  - 1-15: {sections[0]}개 ({sections[0]/total*100:.1f}%)")
            print(f"  - 16-30: {sections[1]}개 ({sections[1]/total*100:.1f}%)")
            print(f"  - 31-45: {sections[2]}개 ({sections[2]/total*100:.1f}%)")
        
        print("\n" + "="*70)
        print("* 추천 설명: 교집합 > ML상위 > 캐스케이드 순으로 신뢰도가 높습니다.")
        print("* 여러 회차에 분산 투자하시기를 권장합니다.")
        print("="*70)
        
    def save_recommendations(self, recommendations: List[Tuple[str, float, str]]):
        """추천 결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"final_recommendations_{timestamp}.json"
        
        data = {
            "timestamp": timestamp,
            "recommendations": [
                {
                    "rank": i + 1,
                    "numbers": [int(n) for n in combo.split(',')],
                    "combination": combo,
                    "score": round(score, 2),
                    "source": source
                }
                for i, (combo, score, source) in enumerate(recommendations)
            ],
            "statistics": {
                "total_combinations_analyzed": self.stats['total_analyzed'],
                "cascade_filtered": self.stats['cascade_filtered'],
                "ml_filtered": self.stats['ml_filtered'],
                "intersection_count": self.stats['intersection']
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"추천 결과 저장: {filename}")
        
    def run(self):
        """메인 실행 함수"""
        logger.info("최종 예측 통합 시작...")
        
        self.stats = {
            'total_analyzed': 0,
            'cascade_filtered': 0,
            'ml_filtered': 0,
            'intersection': 0
        }
        
        try:
            # 예측 통합
            recommendations = self.integrate_predictions()
            
            # 통계 업데이트
            self.stats['cascade_filtered'] = len(self.load_cascade_filtered())
            self.stats['ml_filtered'] = len(self.load_ml_similarity_filtered())
            self.stats['intersection'] = sum(1 for _, _, source in recommendations if source == "교집합")
            self.stats['total_analyzed'] = self.stats['cascade_filtered'] + self.stats['ml_filtered']
            
            # 결과 출력
            self.print_final_recommendations(recommendations)
            
            # 결과 저장
            self.save_recommendations(recommendations)
            
            logger.info("최종 예측 통합 완료!")
            
        except Exception as e:
            logger.error(f"최종 예측 통합 중 오류: {str(e)}")
            raise
        finally:
            self.conn.close()


if __name__ == "__main__":
    integrator = FinalPredictionIntegrator(top_n=10)
    integrator.run()
