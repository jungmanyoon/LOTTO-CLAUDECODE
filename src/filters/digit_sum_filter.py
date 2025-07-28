"""자릿수 합계 필터 구현

이 필터는 로또 번호 각 자릿수의 합계를 분석하여
실제 당첨 패턴과 맞지 않는 조합을 제외합니다.
"""

import logging
from typing import Dict, List, Set, Tuple, Any
import json
from collections import Counter
import numpy as np

from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class DigitSumFilter(BaseFilter):
    """자릿수 합계 필터 클래스"""

    def __init__(self, db_manager, criteria=None):
        """필터 초기화
        
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준 (선택적)
        """
        super().__init__(db_manager, criteria)
        self._initialize_criteria()
        self.optimizer = FilterOptimizer(self._process_chunk)  # FilterOptimizer 사용

    def _initialize_criteria(self):
        """필터링 기준 초기화"""
        if not self._criteria:
            # 기본 필터링 기준 설정
            last_rounds_data = self._get_recent_winning_data(50)  # 최근 50회 데이터 분석
            
            # 자릿수 합계 분석
            digit_sums = []
            digit_sum_ranges = []
            
            for numbers in last_rounds_data:
                # 각 번호의 자릿수 합 계산
                number_digit_sums = [sum(int(digit) for digit in str(num)) for num in numbers]
                # 자릿수 합의 총합
                total_digit_sum = sum(number_digit_sums)
                digit_sums.append(total_digit_sum)
                
                # 자릿수 합의 범위 계산
                digit_sum_range = max(number_digit_sums) - min(number_digit_sums)
                digit_sum_ranges.append(digit_sum_range)
            
            # 합계 범위 분석
            min_sum = min(digit_sums)
            max_sum = max(digit_sums)
            
            # 범위의 10% 마진 추가
            sum_margin = (max_sum - min_sum) * 0.1
            min_sum = max(1, min_sum - sum_margin)
            max_sum = max_sum + sum_margin
            
            # 자릿수 합의 범위에 대한 분석
            min_range = min(digit_sum_ranges)
            max_range = max(digit_sum_ranges)
            range_margin = (max_range - min_range) * 0.1
            min_range = max(0, min_range - range_margin)
            max_range = max_range + range_margin
            
            # 기준 설정
            self._criteria = {
                "min_digit_sum": int(min_sum),
                "max_digit_sum": int(max_sum),
                "min_digit_sum_range": int(min_range),
                "max_digit_sum_range": int(max_range)
            }
            
            logging.info(f"자릿수 합계 필터 기준 자동 설정: {self._criteria}")

    def _validate_criteria(self) -> bool:
        """필터링 기준 유효성 검사
        
        Returns:
            유효성 여부
        """
        if not self._criteria:
            return True
            
        return (
            isinstance(self._criteria, dict) and
            "min_digit_sum" in self._criteria and
            "max_digit_sum" in self._criteria and
            "min_digit_sum_range" in self._criteria and
            "max_digit_sum_range" in self._criteria
        )

    def apply(self, combinations: List[str], round_num: int = None) -> List[str]:
        """자릿수 합계 필터 적용
        
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
                desc="digit_sum 필터 진행률",
                min_sum=self._criteria.get("min_digit_sum", 0),
                max_sum=self._criteria.get("max_digit_sum", 100),
                min_range=self._criteria.get("min_digit_sum_range", 0),
                max_range=self._criteria.get("max_digit_sum_range", 100)
            )
        except Exception as e:
            logging.error(f"자릿수 합계 필터링 중 오류 발생: {str(e)}")
            return combinations

    @staticmethod
    def _process_chunk(combinations_chunk: List[str], min_sum: int, max_sum: int,
                     min_range: int, max_range: int) -> List[str]:
        """청크 단위 필터링 처리
        
        Args:
            combinations_chunk: 처리할 조합 청크
            min_sum: 최소 자릿수 합계
            max_sum: 최대 자릿수 합계
            min_range: 최소 자릿수 합 범위
            max_range: 최대 자릿수 합 범위
            
        Returns:
            필터링된 조합 목록
        """
        try:
            result = []
            
            for combo_str in combinations_chunk:
                # 문자열 조합을 정수 목록으로 변환
                numbers = [int(n) for n in combo_str.split(",")]
                
                # 각 번호의 자릿수 합 계산
                number_digit_sums = [sum(int(digit) for digit in str(num)) for num in numbers]
                
                # 자릿수 합의 총합과 범위 계산
                total_digit_sum = sum(number_digit_sums)
                digit_sum_range = max(number_digit_sums) - min(number_digit_sums)
                
                # 허용 범위 내에 있는 경우만 유지
                if (min_sum <= total_digit_sum <= max_sum and 
                    min_range <= digit_sum_range <= max_range):
                    result.append(combo_str)
                    
            return result
            
        except Exception as e:
            logging.error(f"자릿수 합계 필터 청크 처리 중 오류: {str(e)}")
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