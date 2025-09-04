"""소수/합성수 분포 필터 구현

이 필터는 로또 번호 조합에서 소수와 합성수의 분포를 분석하여
실제 당첨 패턴과 맞지 않는 조합을 제외합니다.
"""

import logging
from typing import Dict, List, Set, Tuple, Any
import json
from collections import Counter
import numpy as np

from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class PrimeCompositeFilter(BaseFilter):
    """소수/합성수 분포 필터 클래스"""

    def __init__(self, db_manager, criteria=None):
        """필터 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준 (선택적)
        """
        super().__init__(db_manager, criteria)
        self.primes = self._generate_primes(45)  # 1-45 범위의 소수 목록 생성
        self._initialize_criteria()
        self.optimizer = FilterOptimizer(self._process_chunk)  # FilterOptimizer 사용

    def _generate_primes(self, limit: int) -> Set[int]:
        """주어진 범위 내의 소수 집합 생성
        
        Args:
            limit: 최대 범위
            
        Returns:
            소수 집합
        """
        # 에라토스테네스의 체 알고리즘
        sieve = [True] * (limit + 1)
        sieve[0] = sieve[1] = False
        
        for i in range(2, int(limit**0.5) + 1):
            if sieve[i]:
                for j in range(i*i, limit + 1, i):
                    sieve[j] = False
                    
        return {i for i in range(2, limit + 1) if sieve[i]}

    def _initialize_criteria(self):
        """필터링 기준 초기화"""
        if not self._criteria:
            # 기본 필터링 기준 설정
            last_rounds_data = self._get_recent_winning_data(30)  # 최근 30회 데이터 분석
            
            # 소수/합성수 분포 분석
            prime_counts = []
            for numbers in last_rounds_data:
                prime_count = sum(1 for num in numbers if num in self.primes)
                prime_counts.append(prime_count)
            
            # 빈도수 계산
            counter = Counter(prime_counts)
            valid_distributions = []
            
            # 가장 빈번한 분포 패턴 추출
            total_rounds = len(prime_counts)
            for count, frequency in counter.items():
                if frequency / total_rounds >= 0.02:  # 2% 이상 빈도의 패턴만 허용 (완화)
                    valid_distributions.append(count)
            
            # 기준 설정
            self._criteria = {
                "valid_prime_counts": valid_distributions,
                "min_allowed": min(valid_distributions) if valid_distributions else 0,
                "max_allowed": max(valid_distributions) if valid_distributions else 6
            }
            
            logging.info(f"소수/합성수 필터 기준 자동 설정: {self._criteria}")

    def _validate_criteria(self) -> bool:
        """필터링 기준 유효성 검사
        
        Returns:
            유효성 여부
        """
        if not self._criteria:
            return True
            
        return (
            isinstance(self._criteria, dict) and
            "valid_prime_counts" in self._criteria and
            isinstance(self._criteria["valid_prime_counts"], list) and
            "min_allowed" in self._criteria and
            "max_allowed" in self._criteria
        )

    def apply(self, combinations: List[str], round_num: int = None) -> List[str]:
        """소수/합성수 분포 필터 적용
        
        Args:
            combinations: 필터링할 로또 번호 조합 목록
            round_num: 회차 번호 (선택적)
            
        Returns:
            필터링 후 남은 조합 목록
        """
        try:
            # FilterOptimizer 사용하여 진행률 표시
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="prime_composite 필터 진행률",
                valid_counts=self._criteria.get("valid_prime_counts", []),
                min_allowed=self._criteria.get("min_allowed", 0),
                max_allowed=self._criteria.get("max_allowed", 6),
                primes=self.primes
            )
        except Exception as e:
            logging.error(f"소수/합성수 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], valid_counts: List[int], 
                      min_allowed: int, max_allowed: int, primes: Set[int]) -> List[str]:
        """청크 단위 필터링 처리
        
        Args:
            combinations_chunk: 처리할 조합 청크
            valid_counts: 유효한 소수 개수 목록
            min_allowed: 최소 허용 소수 개수
            max_allowed: 최대 허용 소수 개수
            primes: 소수 집합
            
        Returns:
            필터링된 조합 목록
        """
        try:
            result = []
            
            for combo in combinations_chunk:
                # 조합이 문자열인지 리스트인지 확인
                if isinstance(combo, str):
                    numbers = [int(n) for n in combo.split(",")]
                else:
                    numbers = combo
                
                # 소수 개수 계산
                prime_count = sum(1 for num in numbers if num in primes)
                
                # 허용 범위 내에 있거나 유효한 분포인 경우만 유지
                if prime_count in valid_counts or (min_allowed <= prime_count <= max_allowed):
                    result.append(combo)
                    
            return result
            
        except Exception as e:
            logging.error(f"소수/합성수 필터 청크 처리 중 오류: {str(e)}")
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