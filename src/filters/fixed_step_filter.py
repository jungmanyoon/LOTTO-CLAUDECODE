from typing import Any, List, Dict
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class FixedStepFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        self.optimizer = FilterOptimizer(self._process_chunk)
        
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if not isinstance(self.criteria, dict):
            raise ValueError("criteria must be a dictionary")
            
        for key in ['all_steps', 'partial_steps', 'four_steps', 'three_steps', 'five_steps', 'six_steps']:  # 검사할 패턴 추가
            if key not in self.criteria:
                # five_steps와 six_steps는 선택적으로 처리
                if key in ['five_steps', 'six_steps']:
                    continue
                raise ValueError(f"'{key}' configuration is required")
                
            config = self.criteria[key]
            if not isinstance(config, dict):
                raise ValueError(f"'{key}' must be a dictionary")
                
            if 'steps_to_exclude' not in config:
                raise ValueError(f"'steps_to_exclude' is required in {key}")
                
            if 'required_matches' not in config:
                raise ValueError(f"'required_matches' is required in {key}")
                
            steps = config['steps_to_exclude']
            if not isinstance(steps, list) or not all(isinstance(s, int) and s >= 2 for s in steps):
                raise ValueError(f"'steps_to_exclude' in {key} must be a list of integers >= 2")
            
            matches = config['required_matches']
            if not isinstance(matches, int) or matches < 2 or matches > 6:  # 최소 매칭 수 2로 완화
                raise ValueError(f"'required_matches' in {key} must be between 2 and 6")

    def _has_fixed_step_pattern_vectorized(self, numbers: np.ndarray, steps: List[int], required_matches: int) -> bool:
        """벡터화된 고정 간격 패턴 검사
        
        Args:
            numbers: 검사할 숫자 배열
            steps: 제외할 간격 리스트
            required_matches: 필요한 연속 매칭 수
            
        Returns:
            bool: 패턴 존재 여부
        """
        sorted_nums = np.sort(numbers)
        
        for step in steps:
            # 간격 패턴 체크를 위한 빠른 알고리즘
            for start_idx in range(len(sorted_nums) - required_matches + 1):
                count = 1
                expected = sorted_nums[start_idx] + step
                
                for j in range(start_idx + 1, len(sorted_nums)):
                    if sorted_nums[j] == expected:
                        count += 1
                        expected += step
                        if count >= required_matches:
                            return True
                    elif sorted_nums[j] > expected:
                        break
        
        return False

    def _has_fixed_step_pattern(self, numbers: List[int], steps: List[int], required_matches: int) -> bool:
        """고정 간격 패턴 검사 (벡터화 래퍼)
        
        Args:
            numbers: 검사할 숫자 리스트
            steps: 제외할 간격 리스트
            required_matches: 필요한 연속 매칭 수
            
        Returns:
            bool: 패턴 존재 여부
        """
        return self._has_fixed_step_pattern_vectorized(
            np.array(numbers, dtype=np.int8),
            steps,
            required_matches
        )
    
    def _process_chunk(self, combinations_chunk: List[str], **kwargs) -> List[str]:
        """청크 단위 필터링 처리 (벡터화 개선)"""
        try:
            # 배열로 한 번에 변환 (타입 체크 추가)
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.int8)
            
            # 각 패턴에 대해 벡터화 검사
            patterns_to_check = [
                ('all_steps', kwargs['all_steps']),
                ('partial_steps', kwargs['partial_steps']),
                ('four_steps', kwargs['four_steps']),
                ('three_steps', kwargs['three_steps'])
            ]
            
            # five_steps와 six_steps가 있으면 추가
            if 'five_steps' in kwargs:
                patterns_to_check.append(('five_steps', kwargs['five_steps']))
            if 'six_steps' in kwargs:
                patterns_to_check.append(('six_steps', kwargs['six_steps']))
            
            valid_mask = np.ones(len(combinations_chunk), dtype=bool)
            
            # 각 조합에 대해 패턴 검사
            for i, numbers in enumerate(chunk_arrays):
                if not valid_mask[i]:
                    continue
                    
                for pattern_type, criteria in patterns_to_check:
                    if self._has_fixed_step_pattern_vectorized(
                        numbers,
                        criteria['steps_to_exclude'],
                        criteria['required_matches']
                    ):
                        valid_mask[i] = False
                        break
            
            # 유효한 조합만 반환
            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid_mask[i]]
            
        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return combinations_chunk

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용"""
        try:
            kwargs = {
                'combinations': combinations,
                'desc': f"fixed_step 필터 진행률",
                'all_steps': self.criteria['all_steps'],
                'partial_steps': self.criteria['partial_steps'],
                'four_steps': self.criteria['four_steps'],
                'three_steps': self.criteria['three_steps']
            }
            
            # five_steps와 six_steps가 있으면 추가
            if 'five_steps' in self.criteria:
                kwargs['five_steps'] = self.criteria['five_steps']
            if 'six_steps' in self.criteria:
                kwargs['six_steps'] = self.criteria['six_steps']
                
            return self.optimizer.optimize_filter(**kwargs)
        except Exception as e:
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"고정 간격 필터링 중 오류 발생: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations