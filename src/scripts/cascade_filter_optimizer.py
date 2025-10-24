"""
캐스케이드 필터 최적화 시스템

단계별로 조합을 제거하여 메모리와 처리 시간을 대폭 절감합니다.
목표: 82.45% → 5% 이하로 통과율 감소
"""

import os
import sys
import sqlite3
import logging
import time
import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json

# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.logger import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class CascadeFilterOptimizer:
    """캐스케이드 필터 최적화 클래스"""
    
    def __init__(self, target_rate: float = 5.0):
        self.target_rate = target_rate
        self.conn = sqlite3.connect('data/combinations.db')
        self.ml_predictions = self.load_ml_predictions()
        
        # 캐스케이드 필터 단계 정의 (강도 순서대로)
        self.cascade_stages = [
            {
                'name': 'Stage 1: 극단값 제거',
                'filters': [
                    ('sum_extreme', self.filter_sum_extreme),
                    ('consecutive_extreme', self.filter_consecutive_extreme),
                    ('odd_even_extreme', self.filter_odd_even_extreme)
                ],
                'target_pass_rate': 50.0
            },
            {
                'name': 'Stage 2: 패턴 기반 필터',
                'filters': [
                    ('fixed_step_strict', self.filter_fixed_step_strict),
                    ('dispersion_strict', self.filter_dispersion_strict),
                    ('section_balance', self.filter_section_balance)
                ],
                'target_pass_rate': 25.0
            },
            {
                'name': 'Stage 3: ML 유사도 필터',
                'filters': [
                    ('ml_similarity', self.filter_ml_similarity)
                ],
                'target_pass_rate': 10.0
            },
            {
                'name': 'Stage 4: 최종 정밀 필터',
                'filters': [
                    ('historical_pattern', self.filter_historical_pattern),
                    ('final_selection', self.filter_final_selection)
                ],
                'target_pass_rate': 5.0
            }
        ]
        
        self.stats = {
            'initial_count': 0,
            'stage_results': [],
            'filter_effectiveness': {}
        }
        
    def load_ml_predictions(self) -> List[List[int]]:
        """ML 예측 결과 로드"""
        try:
            with open('predictions_20250728_185706.json', 'r') as f:
                data = json.load(f)
            return [pred['numbers'] for pred in data['predictions']]
        except Exception as e:
            logging.error(f"최적화 실패: {e}")
            return [
                [7, 13, 17, 22, 34, 45],
                [11, 15, 20, 27, 34, 45],
                [11, 19, 22, 34, 43, 45]
            ]
            
    def filter_sum_extreme(self, combinations: List[str]) -> List[str]:
        """극단적인 합계 제거 (매우 엄격)"""
        filtered = []
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            total_sum = sum(numbers)
            # 매우 좁은 범위만 허용 (역대 당첨번호 분석 기반)
            if 110 <= total_sum <= 160:
                filtered.append(combo_str)
        return filtered
        
    def filter_consecutive_extreme(self, combinations: List[str]) -> List[str]:
        """연속 번호 엄격 제한"""
        filtered = []
        for combo_str in combinations:
            numbers = sorted([int(n) for n in combo_str.split(',')])
            max_consecutive = 1
            current_consecutive = 1
            
            for i in range(1, len(numbers)):
                if numbers[i] == numbers[i-1] + 1:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 1
                    
            # 최대 2개 연속만 허용
            if max_consecutive <= 2:
                filtered.append(combo_str)
        return filtered
        
    def filter_odd_even_extreme(self, combinations: List[str]) -> List[str]:
        """홀짝 비율 엄격 제한"""
        filtered = []
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            # 2:4, 3:3, 4:2만 허용
            if odd_count in [2, 3, 4]:
                filtered.append(combo_str)
        return filtered
        
    def filter_fixed_step_strict(self, combinations: List[str]) -> List[str]:
        """고정 간격 패턴 엄격 제한"""
        filtered = []
        for combo_str in combinations:
            numbers = sorted([int(n) for n in combo_str.split(',')])
            
            # 간격 계산
            gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
            
            # 동일한 간격이 3개 이상 있으면 제외
            from collections import Counter
            gap_counts = Counter(gaps)
            if all(count < 3 for count in gap_counts.values()):
                filtered.append(combo_str)
        return filtered
        
    def filter_dispersion_strict(self, combinations: List[str]) -> List[str]:
        """분산도 엄격 제한"""
        filtered = []
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            
            # 표준편차 계산
            std_dev = np.std(numbers)
            
            # 번호 간 최소/최대 간격
            sorted_nums = sorted(numbers)
            gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
            min_gap = min(gaps)
            max_gap = max(gaps)
            
            # 엄격한 분산도 기준
            if 10.0 <= std_dev <= 13.0 and min_gap >= 1 and max_gap <= 15:
                filtered.append(combo_str)
        return filtered
        
    def filter_section_balance(self, combinations: List[str]) -> List[str]:
        """구간별 균형 필터"""
        filtered = []
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            
            # 3개 구간으로 나누기: 1-15, 16-30, 31-45
            section1 = sum(1 for n in numbers if 1 <= n <= 15)
            section2 = sum(1 for n in numbers if 16 <= n <= 30)
            section3 = sum(1 for n in numbers if 31 <= n <= 45)
            
            # 각 구간에 1-3개씩 균형있게 분포
            if 1 <= section1 <= 3 and 1 <= section2 <= 3 and 1 <= section3 <= 3:
                filtered.append(combo_str)
        return filtered
        
    def filter_ml_similarity(self, combinations: List[str]) -> List[str]:
        """ML 예측과의 유사도 기반 필터"""
        scored_combos = []
        
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            score = 0
            
            for pred in self.ml_predictions:
                # 공통 번호 개수
                common = len(set(numbers) & set(pred))
                score += common * 10
                
                # 번호 차이 평균
                sorted_nums = sorted(numbers)
                sorted_pred = sorted(pred)
                diff = sum(abs(sorted_nums[i] - sorted_pred[i]) for i in range(6)) / 6
                score += max(0, 30 - diff)
                
            scored_combos.append((combo_str, score / len(self.ml_predictions)))
            
        # 상위 40%만 선택
        scored_combos.sort(key=lambda x: x[1], reverse=True)
        cutoff = int(len(scored_combos) * 0.4)
        return [combo for combo, _ in scored_combos[:cutoff]]
        
    def filter_historical_pattern(self, combinations: List[str]) -> List[str]:
        """역대 당첨 패턴 분석 필터"""
        # 실제로는 역대 당첨번호 DB를 분석해야 하지만, 여기서는 간단한 규칙 적용
        filtered = []
        for combo_str in combinations:
            numbers = [int(n) for n in combo_str.split(',')]
            
            # 역대 당첨 패턴 기반 규칙
            # 1. 10단위 숫자가 2개 이하
            tens = [10, 20, 30, 40]
            tens_count = sum(1 for n in numbers if n in tens)
            
            # 2. 연속된 10구간에 4개 이상 몰리지 않음
            section_counts = [0] * 5  # 1-10, 11-20, 21-30, 31-40, 41-45
            for n in numbers:
                if n <= 10:
                    section_counts[0] += 1
                elif n <= 20:
                    section_counts[1] += 1
                elif n <= 30:
                    section_counts[2] += 1
                elif n <= 40:
                    section_counts[3] += 1
                else:
                    section_counts[4] += 1
                    
            if tens_count <= 2 and max(section_counts) <= 3:
                filtered.append(combo_str)
        return filtered
        
    def filter_final_selection(self, combinations: List[str]) -> List[str]:
        """최종 정밀 선택"""
        # 남은 조합이 목표보다 많으면 추가 필터링
        if len(combinations) > self.calculate_target_count():
            # 번호 간격의 표준편차가 가장 적절한 것들 선택
            scored_combos = []
            
            for combo_str in combinations:
                numbers = sorted([int(n) for n in combo_str.split(',')])
                gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
                gap_std = np.std(gaps)
                
                # 간격의 표준편차가 적당한 것이 좋음 (너무 균등하거나 불균등하지 않음)
                score = abs(gap_std - 3.5)  # 3.5가 이상적인 값
                scored_combos.append((combo_str, score))
                
            scored_combos.sort(key=lambda x: x[1])
            target_count = self.calculate_target_count()
            return [combo for combo, _ in scored_combos[:target_count]]
        else:
            return combinations
            
    def calculate_target_count(self) -> int:
        """목표 조합 수 계산"""
        return int(self.stats['initial_count'] * (self.target_rate / 100))
        
    def apply_cascade_filters(self):
        """캐스케이드 필터 적용"""
        logger.info("캐스케이드 필터링 시작...")
        
        # 초기 조합 로드 (배치 처리)
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM filtered_combinations WHERE round = 1182")
        self.stats['initial_count'] = cursor.fetchone()[0]
        logger.info(f"초기 조합 수: {self.stats['initial_count']:,}개")
        
        # 배치 크기 설정
        batch_size = 100000
        current_combinations = []
        
        # 첫 번째 배치 로드
        cursor.execute("""
            SELECT combination FROM filtered_combinations 
            WHERE round = 1182 LIMIT ?
        """, (batch_size * 10,))  # 초기에는 더 많이 로드
        
        current_combinations = [row[0] for row in cursor.fetchall()]
        stage_start_count = len(current_combinations)
        
        # 각 단계별로 필터 적용
        for stage_idx, stage in enumerate(self.cascade_stages):
            stage_name = stage['name']
            logger.info(f"\n{stage_name} 시작...")
            stage_start = len(current_combinations)
            
            # 단계 내 필터들 적용
            for filter_name, filter_func in stage['filters']:
                before_count = len(current_combinations)
                current_combinations = filter_func(current_combinations)
                after_count = len(current_combinations)
                
                if before_count > 0:
                    pass_rate = (after_count / before_count) * 100
                    excluded = before_count - after_count
                    
                    self.stats['filter_effectiveness'][filter_name] = {
                        'excluded': excluded,
                        'pass_rate': pass_rate
                    }
                    
                    logger.info(f"  - {filter_name}: {before_count:,} → {after_count:,} "
                              f"({pass_rate:.1f}% 통과, {excluded:,}개 제외)")
                    
                # 조합이 너무 적어지면 중단
                if after_count < self.calculate_target_count():
                    logger.warning(f"목표 개수 도달, 필터링 중단")
                    break
                    
            # 단계 결과 저장
            stage_end = len(current_combinations)
            stage_pass_rate = (stage_end / stage_start) * 100 if stage_start > 0 else 0
            
            self.stats['stage_results'].append({
                'stage': stage_name,
                'start_count': stage_start,
                'end_count': stage_end,
                'pass_rate': stage_pass_rate
            })
            
            logger.info(f"{stage_name} 완료: {stage_start:,} → {stage_end:,} ({stage_pass_rate:.1f}% 통과)")
            
            # 목표 달성 확인
            overall_pass_rate = (stage_end / self.stats['initial_count']) * 100
            if overall_pass_rate <= self.target_rate:
                logger.info(f"목표 통과율 달성! 현재: {overall_pass_rate:.2f}%")
                break
                
        return current_combinations
        
    def save_results(self, combinations: List[str]):
        """최종 결과 저장"""
        logger.info("최종 결과 저장 중...")
        
        cursor = self.conn.cursor()
        
        # 새 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cascade_filtered_combinations (
                combination TEXT PRIMARY KEY,
                round INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 기존 데이터 삭제
        cursor.execute("DELETE FROM cascade_filtered_combinations WHERE round = 1182")
        
        # 새 데이터 삽입
        data = [(combo, 1182) for combo in combinations]
        cursor.executemany("""
            INSERT INTO cascade_filtered_combinations (combination, round)
            VALUES (?, ?)
        """, data)
        
        self.conn.commit()
        
        # 상위 20개 예시 출력
        print("\n최종 선택된 조합 예시 (상위 20개):")
        print("="*50)
        for i, combo in enumerate(combinations[:20], 1):
            print(f"{i:2d}. {combo}")
            
        # 파일로도 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cascade_filtered_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"캐스케이드 필터링 결과\n")
            f.write(f"생성 시간: {datetime.now()}\n")
            f.write(f"전체: {self.stats['initial_count']:,}개 → 최종: {len(combinations):,}개\n")
            f.write(f"최종 통과율: {len(combinations)/self.stats['initial_count']*100:.2f}%\n")
            f.write("="*60 + "\n\n")
            
            for i, combo in enumerate(combinations, 1):
                f.write(f"{i}. {combo}\n")
                
        logger.info(f"결과 파일 저장: {filename}")
        
    def print_statistics(self):
        """통계 출력"""
        print("\n" + "="*70)
        print("캐스케이드 필터링 최종 통계")
        print("="*70)
        print(f"초기 조합 수: {self.stats['initial_count']:,}개")
        
        # 단계별 결과
        print("\n[단계별 필터링 결과]")
        for result in self.stats['stage_results']:
            print(f"{result['stage']}:")
            print(f"  {result['start_count']:,} → {result['end_count']:,} ({result['pass_rate']:.1f}% 통과)")
            
        # 필터별 효과성
        print("\n[필터별 효과성 (제외 개수 기준)]")
        sorted_filters = sorted(self.stats['filter_effectiveness'].items(), 
                              key=lambda x: x[1]['excluded'], reverse=True)
        
        for filter_name, stats in sorted_filters[:10]:  # 상위 10개만
            print(f"  {filter_name}: {stats['excluded']:,}개 제외 ({stats['pass_rate']:.1f}% 통과)")
            
        # 최종 결과
        if self.stats['stage_results']:
            final_count = self.stats['stage_results'][-1]['end_count']
            final_rate = (final_count / self.stats['initial_count']) * 100
            
            print(f"\n[최종 결과]")
            print(f"최종 조합 수: {final_count:,}개")
            print(f"최종 통과율: {final_rate:.2f}%")
            
            if final_rate <= self.target_rate:
                print(f"\n✓ 목표 달성! (목표: {self.target_rate}% 이하)")
            else:
                print(f"\n✗ 목표 미달성 (목표: {self.target_rate}% 이하)")
                print("추가 필터 강화가 필요합니다.")
                
        print("="*70)
        
    def run(self):
        """메인 실행 함수"""
        start_time = time.time()
        
        try:
            # 캐스케이드 필터 적용
            final_combinations = self.apply_cascade_filters()
            
            # 결과 저장
            self.save_results(final_combinations)
            
            # 통계 출력
            self.print_statistics()
            
            elapsed = time.time() - start_time
            logger.info(f"\n캐스케이드 필터링 완료! (소요시간: {elapsed:.1f}초)")
            
        except Exception as e:
            logger.error(f"캐스케이드 필터링 중 오류: {str(e)}")
            raise
        finally:
            self.conn.close()


if __name__ == "__main__":
    optimizer = CascadeFilterOptimizer(target_rate=5.0)
    optimizer.run()
