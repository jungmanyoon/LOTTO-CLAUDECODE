"""
엄격한 필터 적용 스크립트

기존 필터링된 조합에 더 엄격한 기준을 적용하여 통과율을 5% 이하로 감소시킵니다.
"""

import os
import sys
import sqlite3
import logging
import time
from typing import List, Dict, Tuple
from datetime import datetime
import yaml

# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.meta_data_manager import MetaDataManager
from src.logger import setup_logging
from src.utils.config_manager import ConfigManager

# 로깅 설정
setup_logging("config_strict.yaml")
logger = logging.getLogger(__name__)


class StrictFilterApplicator:
    """엄격한 필터 적용 클래스"""
    
    def __init__(self, config_path: str = "config_strict.yaml"):
        self.config_path = config_path
        self.db_manager = DatabaseManager()
        self.meta_manager = MetaDataManager()
        
        # 엄격한 설정 로드
        self.load_strict_config()
        
        # 필터 매니저 초기화 (새 설정으로)
        self.filter_manager = FilterManager(self.db_manager)
        
        # 통계 정보
        self.stats = {
            'initial_count': 0,
            'final_count': 0,
            'filter_stats': {}
        }
        
    def load_strict_config(self):
        """엄격한 설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 필터 기준값 업데이트
            self.filter_criteria = config.get('filter_criteria', {})
            logger.info(f"엄격한 설정 로드 완료: {self.config_path}")
            
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {str(e)}")
            raise
            
    def apply_strict_criteria(self):
        """각 필터에 엄격한 기준값 적용"""
        logger.info("엄격한 필터 기준값 적용 중...")
        
        # 각 필터의 criteria 업데이트
        for filter_name, criteria in self.filter_criteria.items():
            if filter_name in self.filter_manager.filters:
                filter_obj = self.filter_manager.filters[filter_name]
                filter_obj._criteria = criteria
                logger.info(f"{filter_name} 필터 기준값 업데이트 완료")
                
    def get_current_filtered_combinations(self) -> List[str]:
        """현재 필터링된 조합 가져오기"""
        logger.info("기존 필터링된 조합 로드 중...")
        
        conn = sqlite3.connect('data/combinations.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT combination 
            FROM filtered_combinations 
            WHERE round = 1182
        """)
        
        combinations = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        logger.info(f"로드된 조합 수: {len(combinations):,}개")
        return combinations
        
    def apply_filters_batch(self, combinations: List[str], batch_size: int = 100000) -> List[str]:
        """배치 단위로 필터 적용"""
        total = len(combinations)
        filtered_combinations = []
        
        logger.info(f"배치 필터링 시작 (배치 크기: {batch_size:,})")
        
        for i in range(0, total, batch_size):
            batch = combinations[i:i+batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            logger.info(f"배치 {batch_num}/{total_batches} 처리 중...")
            
            # 각 필터 순차적으로 적용
            current_batch = batch
            for filter_name, filter_obj in self.filter_manager.filters.items():
                if len(current_batch) == 0:
                    break
                    
                before_count = len(current_batch)
                current_batch = filter_obj.apply(current_batch, 1182)
                after_count = len(current_batch)
                
                # 통계 업데이트
                if filter_name not in self.stats['filter_stats']:
                    self.stats['filter_stats'][filter_name] = {
                        'excluded': 0,
                        'pass_rate': 0
                    }
                
                self.stats['filter_stats'][filter_name]['excluded'] += (before_count - after_count)
                
                if before_count > 0:
                    pass_rate = (after_count / before_count) * 100
                    logger.debug(f"  - {filter_name}: {before_count:,} → {after_count:,} ({pass_rate:.2f}% 통과)")
                    
            filtered_combinations.extend(current_batch)
            logger.info(f"  배치 {batch_num} 완료: {len(current_batch):,}개 통과")
            
        return filtered_combinations
        
    def save_results(self, combinations: List[str]):
        """결과 저장"""
        logger.info("엄격한 필터링 결과 저장 중...")
        
        # 새 테이블에 저장
        conn = sqlite3.connect('data/combinations.db')
        cursor = conn.cursor()
        
        # 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strict_filtered_combinations (
                combination TEXT PRIMARY KEY,
                round INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 기존 데이터 삭제
        cursor.execute("DELETE FROM strict_filtered_combinations WHERE round = 1182")
        
        # 새 데이터 삽입
        data = [(combo, 1182) for combo in combinations]
        cursor.executemany("""
            INSERT INTO strict_filtered_combinations (combination, round)
            VALUES (?, ?)
        """, data)
        
        conn.commit()
        conn.close()
        
        logger.info(f"엄격한 필터링 결과 저장 완료: {len(combinations):,}개")
        
    def print_statistics(self):
        """통계 출력"""
        print("\n" + "="*60)
        print("엄격한 필터링 결과 통계")
        print("="*60)
        print(f"초기 조합 수: {self.stats['initial_count']:,}개")
        print(f"최종 조합 수: {self.stats['final_count']:,}개")
        
        if self.stats['initial_count'] > 0:
            total_pass_rate = (self.stats['final_count'] / self.stats['initial_count']) * 100
            print(f"전체 통과율: {total_pass_rate:.2f}%")
            
        print("\n필터별 제외 통계:")
        for filter_name, stats in sorted(self.stats['filter_stats'].items(), 
                                       key=lambda x: x[1]['excluded'], 
                                       reverse=True):
            if stats['excluded'] > 0:
                print(f"  - {filter_name}: {stats['excluded']:,}개 제외")
                
        print("="*60)
        
    def run(self):
        """메인 실행 함수"""
        start_time = time.time()
        logger.info("엄격한 필터 적용 시작...")
        
        # 1. 엄격한 기준값 적용
        self.apply_strict_criteria()
        
        # 2. 기존 필터링된 조합 로드
        combinations = self.get_current_filtered_combinations()
        self.stats['initial_count'] = len(combinations)
        
        # 3. 엄격한 필터 적용
        filtered_combinations = self.apply_filters_batch(combinations)
        self.stats['final_count'] = len(filtered_combinations)
        
        # 4. 결과 저장
        self.save_results(filtered_combinations)
        
        # 5. 통계 출력
        self.print_statistics()
        
        # 6. 메타데이터 업데이트
        self.meta_manager.update_filter_info(
            filter_version="2.0-strict",
            last_filtered_round=1182
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"엄격한 필터 적용 완료! (소요시간: {elapsed_time:.1f}초)")
        
        # 목표 달성 여부 확인
        if self.stats['initial_count'] > 0:
            final_rate = (self.stats['final_count'] / self.stats['initial_count']) * 100
            if final_rate <= 5.0:
                logger.info(f"✓ 목표 달성! 통과율 {final_rate:.2f}% (목표: 5% 이하)")
            else:
                logger.warning(f"✗ 목표 미달성. 통과율 {final_rate:.2f}% (목표: 5% 이하)")
                logger.info("더 엄격한 기준이 필요합니다.")


if __name__ == "__main__":
    applicator = StrictFilterApplicator()
    applicator.run()