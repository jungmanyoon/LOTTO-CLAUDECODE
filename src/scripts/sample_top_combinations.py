"""
상위 조합 샘플링 스크립트

필터링된 조합 중에서 ML 예측과의 유사도를 기준으로 상위 5%를 선택합니다.
"""

import os
import sys
import sqlite3
import json
import numpy as np
from typing import List, Dict, Tuple
from datetime import datetime
import logging

# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.logger import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class TopCombinationSampler:
    """상위 조합 샘플링 클래스"""
    
    def __init__(self, target_percentage: float = 5.0):
        self.target_percentage = target_percentage
        self.ml_predictions = self.load_ml_predictions()
        
    def load_ml_predictions(self) -> List[List[int]]:
        """ML 예측 결과 로드"""
        # predictions JSON 파일에서 로드
        try:
            with open('predictions_20250728_185706.json', 'r') as f:
                data = json.load(f)
                
            predictions = []
            for pred in data['predictions']:
                predictions.append(pred['numbers'])
                
            logger.info(f"ML 예측 결과 로드 완료: {len(predictions)}개")
            return predictions

        except Exception as e:
            logging.error(f"샘플링 실패: {e}")
            # 파일이 없으면 하드코딩된 값 사용
            logger.warning("예측 파일을 찾을 수 없어 기본값 사용")
            return [
                [7, 13, 17, 22, 34, 45],
                [11, 15, 20, 27, 34, 45],
                [11, 19, 22, 34, 43, 45],
                [11, 16, 18, 21, 26, 36],
                [2, 12, 13, 27, 32, 33]
            ]
            
    def calculate_similarity_score(self, combo: List[int], predictions: List[List[int]]) -> float:
        """조합과 ML 예측들과의 유사도 계산"""
        total_score = 0.0
        
        for pred in predictions:
            # 공통 번호 개수
            common = len(set(combo) & set(pred))
            total_score += common * 10
            
            # 번호 차이의 평균
            diff = np.mean([abs(combo[i] - pred[i]) for i in range(6)])
            total_score += max(0, 50 - diff)
            
        return total_score / len(predictions)
        
    def sample_top_combinations(self):
        """상위 조합 샘플링"""
        logger.info("필터링된 조합 로드 중...")
        
        # DB 연결
        conn = sqlite3.connect('data/combinations.db')
        cursor = conn.cursor()
        
        # 전체 개수 확인
        cursor.execute("SELECT COUNT(*) FROM filtered_combinations WHERE round = 1182")
        total_count = cursor.fetchone()[0]
        target_count = int(total_count * (self.target_percentage / 100))
        
        logger.info(f"전체: {total_count:,}개 → 목표: {target_count:,}개 ({self.target_percentage}%)")
        
        # 메모리 제한으로 배치 처리
        batch_size = 100000
        scored_combinations = []
        
        logger.info("조합 점수 계산 중...")
        offset = 0
        
        while offset < total_count:
            # 배치 로드
            cursor.execute("""
                SELECT combination 
                FROM filtered_combinations 
                WHERE round = 1182
                LIMIT ? OFFSET ?
            """, (batch_size, offset))
            
            batch = cursor.fetchall()
            if not batch:
                break
                
            # 점수 계산
            for row in batch:
                combo_str = row[0]
                combo = [int(n) for n in combo_str.split(',')]
                score = self.calculate_similarity_score(combo, self.ml_predictions)
                
                scored_combinations.append((combo_str, score))
                
            offset += batch_size
            logger.info(f"  처리 진행: {min(offset, total_count):,}/{total_count:,}")
            
            # 메모리 절약을 위해 상위 N개만 유지
            if len(scored_combinations) > target_count * 2:
                scored_combinations.sort(key=lambda x: x[1], reverse=True)
                scored_combinations = scored_combinations[:target_count * 2]
                
        conn.close()
        
        # 최종 정렬 및 선택
        logger.info("최종 상위 조합 선택 중...")
        scored_combinations.sort(key=lambda x: x[1], reverse=True)
        top_combinations = scored_combinations[:target_count]
        
        return top_combinations, total_count
        
    def save_results(self, combinations: List[Tuple[str, float]], total_count: int):
        """결과 저장"""
        logger.info("결과 저장 중...")
        
        # DB에 저장
        conn = sqlite3.connect('data/combinations.db')
        cursor = conn.cursor()
        
        # 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS top_filtered_combinations (
                combination TEXT PRIMARY KEY,
                score REAL,
                round INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 기존 데이터 삭제
        cursor.execute("DELETE FROM top_filtered_combinations WHERE round = 1182")
        
        # 새 데이터 삽입
        data = [(combo, score, 1182) for combo, score in combinations]
        cursor.executemany("""
            INSERT INTO top_filtered_combinations (combination, score, round)
            VALUES (?, ?, ?)
        """, data)
        
        conn.commit()
        conn.close()
        
        # 텍스트 파일로도 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"top_combinations_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"상위 {self.target_percentage}% 조합 목록\n")
            f.write(f"생성 시간: {timestamp}\n")
            f.write(f"전체: {total_count:,}개 → 선택: {len(combinations):,}개\n")
            f.write("="*60 + "\n\n")
            
            for i, (combo, score) in enumerate(combinations[:100], 1):  # 상위 100개만
                f.write(f"{i:3d}. {combo} (점수: {score:.2f})\n")
                
        logger.info(f"결과 저장 완료: {filename}")
        
    def print_statistics(self, combinations: List[Tuple[str, float]], total_count: int):
        """통계 출력"""
        print("\n" + "="*60)
        print("상위 조합 샘플링 결과")
        print("="*60)
        print(f"전체 조합 수: {total_count:,}개")
        print(f"선택된 조합 수: {len(combinations):,}개")
        print(f"선택 비율: {self.target_percentage}%")
        
        if combinations:
            scores = [score for _, score in combinations]
            print(f"\n점수 분포:")
            print(f"  - 최고 점수: {max(scores):.2f}")
            print(f"  - 최저 점수: {min(scores):.2f}")
            print(f"  - 평균 점수: {np.mean(scores):.2f}")
            
            print(f"\n상위 10개 조합:")
            for i, (combo, score) in enumerate(combinations[:10], 1):
                print(f"  {i:2d}. {combo} (점수: {score:.2f})")
                
        print("="*60)
        
    def run(self):
        """메인 실행 함수"""
        logger.info("상위 조합 샘플링 시작...")
        
        # 상위 조합 샘플링
        top_combinations, total_count = self.sample_top_combinations()
        
        # 결과 저장
        self.save_results(top_combinations, total_count)
        
        # 통계 출력
        self.print_statistics(top_combinations, total_count)
        
        logger.info("상위 조합 샘플링 완료!")


if __name__ == "__main__":
    sampler = TopCombinationSampler(target_percentage=5.0)
    sampler.run()