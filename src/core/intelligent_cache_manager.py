#!/usr/bin/env python3
"""
지능형 캐시 관리 시스템
- 필터링 결과 캐싱
- 새 당첨번호 시 동적 업데이트
- 증분 학습 지원
"""

import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple

class IntelligentCacheManager:
    """지능형 캐시 관리자"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db_path = self.cache_dir / "cache_metadata.db"
        self._init_cache_db()
        
    def _init_cache_db(self):
        """캐시 메타데이터 DB 초기화"""
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    cache_key TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    last_used TIMESTAMP,
                    filter_version TEXT,
                    filter_hash TEXT,
                    latest_round INTEGER,
                    total_combinations INTEGER,
                    filtered_combinations INTEGER,
                    pass_rate REAL,
                    is_valid BOOLEAN
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filter_versions (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP,
                    filter_config TEXT,
                    config_hash TEXT,
                    latest_round INTEGER,
                    reason TEXT
                )
            """)
    
    def get_filter_hash(self, filter_config: Dict) -> str:
        """필터 설정의 해시값 생성"""
        # 필터 설정을 정렬하여 일관된 해시 생성
        config_str = json.dumps(filter_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()
    
    def is_cache_valid(self, latest_round: int) -> Tuple[bool, Optional[str]]:
        """
        캐시 유효성 검사
        
        Returns:
            (유효여부, 무효화 이유)
        """
        # 1. 최신 회차 확인
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.execute("""
                SELECT latest_round, filter_hash, created_at
                FROM cache_metadata
                WHERE is_valid = 1
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                return False, "캐시가 없습니다"
            
            cached_round, cached_hash, created_at = row
            
            # 2. 새 회차 확인
            if latest_round > cached_round:
                return False, f"새 회차 발견 ({cached_round} → {latest_round})"
            
            # 3. 필터 설정 변경 확인
            current_config = self.db_manager.config.get('filters', {}).get('criteria', {})
            current_hash = self.get_filter_hash(current_config)
            
            if current_hash != cached_hash:
                return False, "필터 설정이 변경되었습니다"
            
            # 4. 캐시 만료 확인 (7일)
            created_date = datetime.fromisoformat(created_at)
            if datetime.now() - created_date > timedelta(days=7):
                return False, "캐시가 만료되었습니다 (7일 경과)"
            
            return True, None
    
    # 호환성을 위한 별칭 메서드들
    def save_cache(self, combinations: List[str], latest_round: int):
        """save_filtered_results의 별칭 (호환성)"""
        return self.save_filtered_results(combinations, latest_round)
    
    def load_cache(self, latest_round: int) -> Optional[List[str]]:
        """load_filtered_results의 별칭 (호환성)"""
        return self.load_filtered_results(latest_round)
    
    def save_filtered_combinations(self, combinations: List[str], latest_round: int):
        """save_filtered_results의 별칭 (호환성)"""
        return self.save_filtered_results(combinations, latest_round)
    
    def load_filtered_combinations(self) -> Optional[List[str]]:
        """가장 최신 캐시 로드"""
        # 최신 회차 조회
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.execute("SELECT MAX(latest_round) FROM cache_metadata WHERE is_valid = 1")
            row = cursor.fetchone()
            if row and row[0]:
                return self.load_filtered_results(row[0])
        return None
    
    def save_filtered_results(self, combinations: List[str], latest_round: int):
        """필터링 결과 저장"""
        
        # 1. 필터링 결과를 DB에 저장 (이미 filter_manager가 처리)
        # 여기서는 메타데이터만 저장
        
        filter_config = self.db_manager.config.get('filters', {}).get('criteria', {})
        filter_hash = self.get_filter_hash(filter_config)
        
        # 2. 캐시 메타데이터 저장
        with sqlite3.connect(self.cache_db_path) as conn:
            # 기존 캐시 무효화
            conn.execute("UPDATE cache_metadata SET is_valid = 0")
            
            # 새 캐시 정보 저장
            conn.execute("""
                INSERT OR REPLACE INTO cache_metadata 
                (cache_key, created_at, last_used, filter_version, filter_hash,
                 latest_round, total_combinations, filtered_combinations, pass_rate, is_valid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"filtered_{latest_round}_{filter_hash[:8]}",
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                "v2.0",
                filter_hash,
                latest_round,
                8145060,
                len(combinations),
                len(combinations) / 8145060 * 100,
                True
            ))
            
            # 필터 버전 기록
            conn.execute("""
                INSERT INTO filter_versions 
                (created_at, filter_config, config_hash, latest_round, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                json.dumps(filter_config),
                filter_hash,
                latest_round,
                "필터링 완료"
            ))
            
        logging.info(f"캐시 저장 완료: {len(combinations):,}개 조합 (회차: {latest_round})")
    
    def load_filtered_results(self, latest_round: int) -> Optional[List[str]]:
        """캐시된 필터링 결과 로드"""
        
        # 1. 캐시 유효성 확인
        is_valid, reason = self.is_cache_valid(latest_round)
        
        if not is_valid:
            logging.info(f"캐시 사용 불가: {reason}")
            return None
        
        # 2. 캐시된 결과 로드
        try:
            # DB에서 필터링된 조합 개수 확인 (메모리 효율적)
            filtered_count = self.db_manager.combinations_db.get_filtered_combinations_count()

            if filtered_count > 0:
                # 캐시 사용 시간 업데이트
                with sqlite3.connect(self.cache_db_path) as conn:
                    conn.execute("""
                        UPDATE cache_metadata 
                        SET last_used = ?
                        WHERE is_valid = 1
                    """, (datetime.now().isoformat(),))
                
                # 조합 로드 성공
                # 실제 조합 데이터는 필요시 스트림으로 로드
                logging.info(f"캐시에서 조합 정보 확인: {filtered_count:,}개")
                return f"cached:{filtered_count}"  # 캐시된 데이터 표시
            else:
                logging.warning("캐시가 비어있습니다")
                return None
                
        except Exception as e:
            logging.error(f"캐시 로드 실패: {str(e)}")
            return None
    
    def should_update_filters(self, new_round: int) -> bool:
        """
        필터 업데이트 필요 여부 판단
        
        새 회차가 나왔을 때:
        1. 패턴 분석
        2. 필터 성능 평가
        3. 업데이트 필요성 판단
        """
        
        # 1. 최근 10회차 분석
        recent_rounds = []
        for i in range(new_round - 10, new_round):
            round_data = self.db_manager.get_round_data(i)
            if round_data:
                recent_rounds.append(round_data['numbers'])
        
        if len(recent_rounds) < 5:
            return False  # 데이터 부족
        
        # 2. 현재 필터 성능 평가
        filter_performance = self._evaluate_filter_performance(recent_rounds)
        
        # 3. 업데이트 기준
        # - 필터 통과율이 목표(10-20%)를 벗어남
        # - 최근 당첨번호 중 50% 이상이 필터에서 제외됨
        # - 새로운 패턴 발견
        
        if filter_performance['pass_rate'] < 10 or filter_performance['pass_rate'] > 20:
            logging.info(f"필터 통과율 이상: {filter_performance['pass_rate']:.1f}%")
            return True
        
        if filter_performance['winning_excluded_rate'] > 50:
            logging.info(f"당첨번호 제외율 높음: {filter_performance['winning_excluded_rate']:.1f}%")
            return True
        
        return False
    
    def _evaluate_filter_performance(self, recent_rounds: List[List[int]]) -> Dict:
        """필터 성능 평가"""
        
        # 여기서는 간단한 평가만
        # 실제로는 각 필터별로 상세 평가 필요
        
        return {
            'pass_rate': 15.0,  # 현재 통과율
            'winning_excluded_rate': 20.0,  # 당첨번호 제외율
            'pattern_changes': []  # 패턴 변화
        }
    
    def update_with_new_round(self, new_round: int, new_numbers: List[int]):
        """
        새 회차 업데이트 처리
        
        1. 새 당첨번호 저장
        2. 필터 기준 재계산 필요성 확인
        3. 필요시 재필터링
        4. ML 모델 증분 학습
        """
        
        logging.info(f"새 회차 {new_round} 업데이트 시작: {new_numbers}")
        
        # 1. 새 당첨번호 저장
        self.db_manager.save_round_data(new_round, new_numbers)
        
        # 2. 필터 업데이트 필요성 확인
        if self.should_update_filters(new_round):
            logging.info("필터 기준 재계산 필요")
            
            # 필터 기준 업데이트
            self._update_filter_criteria(new_round)
            
            # 캐시 무효화
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.execute("UPDATE cache_metadata SET is_valid = 0")
            
            logging.info("필터 재처리 필요 - 캐시 무효화됨")
            return True  # 재필터링 필요
        else:
            logging.info("필터 기준 유지 - 캐시 유효")
            
            # ML 모델만 증분 학습
            self._incremental_ml_update(new_round, new_numbers)
            return False  # 재필터링 불필요
    
    def _update_filter_criteria(self, latest_round: int):
        """필터 기준 동적 업데이트"""
        
        # 최근 100회차 분석
        recent_data = []
        for i in range(max(1, latest_round - 100), latest_round + 1):
            round_data = self.db_manager.get_round_data(i)
            if round_data:
                recent_data.append(round_data['numbers'])
        
        if len(recent_data) < 50:
            logging.warning("데이터 부족으로 필터 업데이트 생략")
            return
        
        # 각 필터별 기준 재계산
        new_criteria = {}
        
        # 예: 합계 범위 재계산
        sums = [sum(numbers) for numbers in recent_data]
        new_criteria['sum_range'] = {
            'min_sum': min(sums) - 10,
            'max_sum': max(sums) + 10
        }
        
        # 예: 홀짝 패턴 재계산
        odd_even_patterns = []
        for numbers in recent_data:
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            odd_even_patterns.append(f"{odd_count}:{6-odd_count}")
        
        # 빈도 높은 패턴 선택
        from collections import Counter
        pattern_counts = Counter(odd_even_patterns)
        top_patterns = [p for p, _ in pattern_counts.most_common(5)]
        new_criteria['odd_even'] = {'patterns': top_patterns}
        
        # config 업데이트
        self.db_manager.config['filters']['criteria'].update(new_criteria)
        
        logging.info(f"필터 기준 업데이트 완료: {new_criteria}")
    
    def _incremental_ml_update(self, new_round: int, new_numbers: List[int]):
        """ML 모델 증분 학습"""
        
        logging.info(f"ML 모델 증분 학습: 회차 {new_round}")
        
        # 여기서는 간단히 로깅만
        # 실제로는 각 ML 모델의 update 메서드 호출
        
        # 예:
        # self.db_manager.ml_models['lstm'].incremental_update(new_round, new_numbers)
        # self.db_manager.ml_models['ensemble'].incremental_update(new_round, new_numbers)
        
    def get_cache_status(self) -> Dict:
        """캐시 상태 정보"""
        
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.execute("""
                SELECT cache_key, created_at, last_used, latest_round, 
                       filtered_combinations, pass_rate, is_valid
                FROM cache_metadata
                WHERE is_valid = 1
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                return {
                    'cache_key': row[0],
                    'created_at': row[1],
                    'last_used': row[2],
                    'latest_round': row[3],
                    'filtered_combinations': row[4],
                    'pass_rate': row[5],
                    'is_valid': bool(row[6])
                }
            else:
                return {'is_valid': False, 'message': '유효한 캐시 없음'}