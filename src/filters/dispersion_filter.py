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
            
            # 범위의 30% 마진 추가 (15% → 30%로 증가)
            std_margin = (max_std - min_std) * 0.30
            min_std = max(1, min_std - std_margin)
            max_std = max_std + std_margin
            
            var_margin = (max_var - min_var) * 0.30
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
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"분산도 필터링 중 오류 발생: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations
    
    @staticmethod
    def _process_chunk(combinations_chunk: List[str], criteria: Dict[str, Any]) -> List[str]:
        """청크 단위 벡터화된 필터링 처리"""
        try:
            # 배열로 변환 (벡터화 처리)
            chunk_arrays = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    chunk_arrays.append(list(map(int, comb.split(','))))
                else:
                    chunk_arrays.append(comb)
            chunk_arrays = np.array(chunk_arrays, dtype=np.int8)

            # 정렬된 배열 생성
            sorted_arrays = np.sort(chunk_arrays, axis=1)

            n = len(combinations_chunk)
            valid_indices = np.ones(n, dtype=bool)

            # [filters-16-1] config(criteria)에 명시된 기준만 적용한다.
            # 과거: criteria.get(key, 하드코딩기본값)으로 gap/variance 기본값을 몰래 적용 ->
            #   특히 max_max_gap=30이 큰 분산 조합({1,2,3,4,5,45} 등)을 조용히 배제.
            #   사용자가 max_gap 필터를 명시적으로 껐는데도 dispersion이 covert 재적용하던 버그.
            # 이제 criteria에 없는 키는 검사를 건너뛴다(숨은 기본값 금지, 설정 우선순위 원칙 준수).

            # 표준편차
            if 'min_std_dev' in criteria or 'max_std_dev' in criteria:
                std_devs = np.std(chunk_arrays, axis=1)
                lo = criteria.get('min_std_dev', -np.inf)
                hi = criteria.get('max_std_dev', np.inf)
                valid_indices &= (std_devs >= lo) & (std_devs <= hi)

            # 분산
            if 'min_variance' in criteria or 'max_variance' in criteria:
                variances = np.var(chunk_arrays, axis=1)
                lo = criteria.get('min_variance', -np.inf)
                hi = criteria.get('max_variance', np.inf)
                valid_indices &= (variances >= lo) & (variances <= hi)

            # 갭 기준 (관련 키가 있을 때만 계산)
            gap_keys = ('min_min_gap', 'max_min_gap', 'min_max_gap',
                        'max_max_gap', 'min_avg_gap', 'max_avg_gap')
            if any(k in criteria for k in gap_keys):
                gaps = np.diff(sorted_arrays, axis=1)
                if 'min_min_gap' in criteria or 'max_min_gap' in criteria:
                    min_gaps = np.min(gaps, axis=1)
                    valid_indices &= (min_gaps >= criteria.get('min_min_gap', -np.inf)) & \
                                     (min_gaps <= criteria.get('max_min_gap', np.inf))
                if 'min_max_gap' in criteria or 'max_max_gap' in criteria:
                    max_gaps = np.max(gaps, axis=1)
                    valid_indices &= (max_gaps >= criteria.get('min_max_gap', -np.inf)) & \
                                     (max_gaps <= criteria.get('max_max_gap', np.inf))
                if 'min_avg_gap' in criteria or 'max_avg_gap' in criteria:
                    avg_gaps = np.mean(gaps, axis=1)
                    valid_indices &= (avg_gaps >= criteria.get('min_avg_gap', -np.inf)) & \
                                     (avg_gaps <= criteria.get('max_avg_gap', np.inf))

            # 유효한 조합만 반환
            return [combinations_chunk[i] for i in range(n) if valid_indices[i]]
            
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
        # 공개 API 사용: lotto_db 내부 구현에 직접 접근하지 않음
        raw_data = self.db_manager.get_numbers_with_bonus()
        # 최근 count개만 추출하고, 보너스 번호 제외한 본번호 6개만 반환
        recent_data = raw_data[-count:] if len(raw_data) >= count else raw_data
        return [list(entry[1][:6]) for entry in recent_data]