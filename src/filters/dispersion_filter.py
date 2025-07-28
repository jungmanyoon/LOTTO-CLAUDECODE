"""번호 분산도 필터 구현

이 필터는 로또 번호의 분산도를 분석하여
실제 당첨 패턴과 맞지 않는 조합을 제외합니다.
"""

import logging
import math
from typing import Dict, List, Set, Tuple, Any
import json
import numpy as np
from collections import Counter
from tqdm import tqdm

from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class DispersionFilter(BaseFilter):
    """번호 분산도 필터 클래스"""

    def __init__(self, db_manager, criteria=None):
        """필터 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준 (선택적)
        """
        super().__init__(db_manager, criteria)
        self._initialize_criteria()
        self.optimizer = FilterOptimizer(self._process_chunk)

    def _initialize_criteria(self):
        """필터링 기준 초기화"""
        if not self._criteria:
            # 기본 필터링 기준 설정
            last_rounds_data = self._get_recent_winning_data(50)  # 최근 50회 데이터 분석
            
            # 분산도 분석
            std_devs = []  # 표준편차
            variances = []  # 분산
            
            for numbers in last_rounds_data:
                # 표준편차 계산
                std_dev = np.std(numbers)
                std_devs.append(std_dev)
                
                # 분산 계산
                variance = np.var(numbers)
                variances.append(variance)
            
            # 표준편차 범위 분석
            min_std = min(std_devs)
            max_std = max(std_devs)
            
            # 분산 범위 분석
            min_var = min(variances)
            max_var = max(variances)
            
            # 범위의 15% 마진 추가
            std_margin = (max_std - min_std) * 0.15
            min_std = max(1, min_std - std_margin)
            max_std = max_std + std_margin
            
            var_margin = (max_var - min_var) * 0.15
            min_var = max(1, min_var - var_margin)
            max_var = max_var + var_margin
            
            # 연속 번호 갭 분석 (인접한 번호 사이의 차이)
            gap_stats = []
            for numbers in last_rounds_data:
                sorted_nums = sorted(numbers)
                gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
                gap_stats.append({
                    'min_gap': min(gaps),
                    'max_gap': max(gaps),
                    'avg_gap': sum(gaps) / len(gaps)
                })
            
            # 갭 통계 계산
            min_min_gap = min(stat['min_gap'] for stat in gap_stats)
            max_min_gap = max(stat['min_gap'] for stat in gap_stats)
            min_max_gap = min(stat['max_gap'] for stat in gap_stats)
            max_max_gap = max(stat['max_gap'] for stat in gap_stats)
            min_avg_gap = min(stat['avg_gap'] for stat in gap_stats)
            max_avg_gap = max(stat['avg_gap'] for stat in gap_stats)
            
            # 기준 설정
            self._criteria = {
                "min_std_dev": min_std,
                "max_std_dev": max_std,
                "min_variance": min_var,
                "max_variance": max_var,
                "min_min_gap": min_min_gap,
                "max_min_gap": max_min_gap,
                "min_max_gap": min_max_gap,
                "max_max_gap": max_max_gap,
                "min_avg_gap": min_avg_gap,
                "max_avg_gap": max_avg_gap
            }
            
            logging.info(f"분산도 필터 기준 자동 설정: {self._criteria}")

    def _validate_criteria(self) -> bool:
        """필터링 기준 유효성 검사
        
        Returns:
            유효성 여부
        """
        if not self._criteria:
            return True
            
        required_keys = [
            "min_std_dev", "max_std_dev", 
            "min_variance", "max_variance",
            "min_min_gap", "max_min_gap", 
            "min_max_gap", "max_max_gap",
            "min_avg_gap", "max_avg_gap"
        ]
        
        return (
            isinstance(self._criteria, dict) and
            all(key in self._criteria for key in required_keys)
        )

    def apply(self, combinations: List[str], round_num: int = None) -> List[str]:
        """분산도 필터 적용 (최적화된 버전)
        
        Args:
            combinations: 필터링할 로또 번호 조합 목록
            round_num: 회차 번호 (선택적)
            
        Returns:
            필터링 후 남은 조합 목록
        """
        try:
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="dispersion 필터 진행률",
                criteria=self._criteria
            )
        except Exception as e:
            logging.error(f"분산도 필터링 중 오류 발생: {str(e)}")
            return combinations
    
    @staticmethod
    def _process_chunk(combinations_chunk: List[str], criteria: Dict[str, Any]) -> List[str]:
        """청크 단위 벡터화된 필터링 처리"""
        try:
            # 필터링 기준 로드
            min_std = criteria.get("min_std_dev", 0)
            max_std = criteria.get("max_std_dev", 50)
            min_var = criteria.get("min_variance", 0)
            max_var = criteria.get("max_variance", 1000)
            min_min_gap = criteria.get("min_min_gap", 1)
            max_min_gap = criteria.get("max_min_gap", 10)
            min_max_gap = criteria.get("min_max_gap", 1)
            max_max_gap = criteria.get("max_max_gap", 30)
            min_avg_gap = criteria.get("min_avg_gap", 1)
            max_avg_gap = criteria.get("max_avg_gap", 15)
            
            # 배열로 변환 (벡터화 처리)
            chunk_arrays = np.array([
                list(map(int, comb.split(',')))
                for comb in combinations_chunk
            ], dtype=np.int8)
            
            # 정렬된 배열 생성
            sorted_arrays = np.sort(chunk_arrays, axis=1)
            
            # 벡터화된 분산도 계산
            std_devs = np.std(chunk_arrays, axis=1)
            variances = np.var(chunk_arrays, axis=1)
            
            # 갭 계산 (벡터화)
            gaps = np.diff(sorted_arrays, axis=1)
            min_gaps = np.min(gaps, axis=1)
            max_gaps = np.max(gaps, axis=1)
            avg_gaps = np.mean(gaps, axis=1)
            
            # 벡터화된 조건 검사
            valid_std = (std_devs >= min_std) & (std_devs <= max_std)
            valid_var = (variances >= min_var) & (variances <= max_var)
            valid_min_gap = (min_gaps >= min_min_gap) & (min_gaps <= max_min_gap)
            valid_max_gap = (max_gaps >= min_max_gap) & (max_gaps <= max_max_gap)
            valid_avg_gap = (avg_gaps >= min_avg_gap) & (avg_gaps <= max_avg_gap)
            
            # 모든 조건을 만족하는 인덱스
            valid_indices = valid_std & valid_var & valid_min_gap & valid_max_gap & valid_avg_gap
            
            # 유효한 조합만 반환
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_indices[i]]
            
        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return combinations_chunk

    def _get_recent_winning_data(self, count: int) -> List[List[int]]:
        """최근 당첨 번호 데이터 조회
        
        Args:
            count: 조회할 회차 수
            
        Returns:
            당첨 번호 목록의 목록
        """
        numbers_data = self.db_manager.lotto_db.get_recent_numbers(count)
        return [[int(n) for n in numbers.split(",")] for _, numbers, _ in numbers_data] 