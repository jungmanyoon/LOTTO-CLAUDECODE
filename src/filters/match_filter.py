from typing import Any, List, Dict, Set
import logging

from tqdm import tqdm
import numpy as np
from scipy.spatial.distance import cdist
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer

class MatchFilter(BaseFilter):
    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        super().__init__(db_manager, criteria)
        # FilterOptimizer에 전달할 래퍼 함수 생성
        self.optimizer = FilterOptimizer(self._process_chunk_wrapper)
                           
    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        if 'max_match' not in self.criteria:
            raise ValueError("'max_match' 값이 필요합니다.")
            
        max_match = self.criteria['max_match']
        if not isinstance(max_match, int) or max_match < 0 or max_match > 6:
            raise ValueError("'max_match'는 0에서 6 사이의 정수여야 합니다.")
        
        # 확률 분포 정보가 있으면 로그 출력
        if 'distribution' in self.criteria:
            dist = self.criteria['distribution']
            logging.info(f"[Match 필터] 확률 기반 설정 - max_match: {max_match}")
            if dist:
                for match_count, percentage in dist.items():
                    logging.debug(f"  {match_count}개 일치: {percentage:.2f}%")

    def apply_filter(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용 (시계열 고려 버전)
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 목록
        """
        try:
            # 백테스팅 모드: round_num이 지정된 경우 해당 회차 이전 번호만 사용
            if round_num and round_num > 0:
                # 시계열을 고려하여 해당 회차 이전의 당첨번호만 가져오기
                if hasattr(self.db_manager, 'get_winning_numbers_before'):
                    winning_numbers = self.db_manager.get_winning_numbers_before(round_num)
                    # DEBUG 로그 제거 - 반복적이고 불필요함
                else:
                    # 폴백: 메서드가 없으면 전체 당첨번호 사용 (기존 방식)
                    logging.warning("get_winning_numbers_before 메서드가 없어 전체 당첨번호 사용")
                    winning_numbers = self.db_manager.get_all_winning_numbers()
            else:
                # 일반 모드: 모든 당첨번호 사용
                winning_numbers = self.db_manager.get_all_winning_numbers()
                # DEBUG 로그 제거 - 반복적이고 불필요함
                
            if not winning_numbers:
                logging.warning("참고할 당첨 번호가 없습니다.")
                return combinations

            # 당첨 번호 배열 미리 생성 (타입 체크 추가)
            converted_winning = []
            for nums in winning_numbers:
                if isinstance(nums, str):
                    converted_winning.append(list(map(int, nums.split(','))))
                else:
                    converted_winning.append(nums)
            
            winning_arrays = np.array(converted_winning, dtype=np.int8)

            # max_match=6인 경우 특별 처리 (유사도 기반 필터링)
            if self.criteria['max_match'] == 6:
                logging.info("max_match=6: 유사도 기반 지능형 필터링 적용")
                return self._similarity_based_filtering(combinations, winning_arrays)
            
            # 일반적인 경우: 최적화된 청크 단위 처리
            return self.optimizer.optimize_filter(
                combinations=combinations,
                desc="match 필터 진행률",
                winning_arrays=winning_arrays,
                max_match=self.criteria['max_match']
            )

        except Exception as e:
            logging.error(f"번호 일치 필터링 중 오류 발생: {str(e)}")
            return combinations

    # 기존 apply 메서드 유지
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        # apply_filter 메서드 호출하여 동일한 기능 유지
        return self.apply_filter(combinations, round_num)
    
    @staticmethod
    def _process_chunk_wrapper(combinations_chunk: List[str], **kwargs) -> List[str]:
        """FilterOptimizer용 래퍼 함수 - 키워드 인수를 위치 인수로 변환"""
        winning_arrays = kwargs.get('winning_arrays')
        max_match = kwargs.get('max_match')
        logging.debug(f"_process_chunk_wrapper 호출: 조합 {len(combinations_chunk)}개, max_match={max_match}")
        result = MatchFilter._process_chunk(combinations_chunk, winning_arrays, max_match)
        logging.debug(f"_process_chunk_wrapper 결과: {len(result)}개 통과")
        return result

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      winning_arrays: np.ndarray = None,
                      max_match: int = None,
                      **kwargs) -> List[str]:
        """청크 단위 필터링 처리"""
        try:
            # 필수 매개변수 검증
            if winning_arrays is None or max_match is None:
                logging.error("_process_chunk: 필수 매개변수 누락")
                return combinations_chunk
            
            logging.debug(f"_process_chunk 호출: 조합 {len(combinations_chunk)}개, winning {len(winning_arrays)}개, max_match={max_match}")
                
            # 배열 변환 최적화 (타입 체크 추가)
            converted_chunks = []
            for comb in combinations_chunk:
                if isinstance(comb, str):
                    converted_chunks.append(list(map(int, comb.split(','))))
                else:
                    converted_chunks.append(comb)
            
            chunk_arrays = np.array(converted_chunks, dtype=np.int8)

            # 집합 비교로 일치 개수 계산 (순서 무관)
            match_counts = np.zeros(len(chunk_arrays), dtype=np.int8)
            for win_nums in winning_arrays:
                win_set = set(win_nums)
                for i, combo in enumerate(chunk_arrays):
                    combo_set = set(combo)
                    matches = len(win_set & combo_set)  # 교집합 크기
                    match_counts[i] = max(match_counts[i], matches)

            # 조건을 만족하는 조합만 선택
            valid_indices = match_counts < max_match
            
            # 디버그 로깅
            for i, (combo_str, matches) in enumerate(zip(combinations_chunk, match_counts)):
                if matches >= max_match:
                    logging.debug(f"  제외: {combo_str} (일치 개수: {matches} >= {max_match})")
                else:
                    logging.debug(f"  통과: {combo_str} (일치 개수: {matches} < {max_match})")
            
            # 메모리 효율을 위해 리스트 컴프리헨션 사용
            return [
                combinations_chunk[i] 
                for i in range(len(combinations_chunk)) 
                if valid_indices[i]
            ]

        except Exception as e:
            logging.error(f"청크 처리 중 오류 발생: {str(e)}")
            return combinations_chunk
    
    def _similarity_based_filtering(self, combinations: List[str], winning_arrays: np.ndarray) -> List[str]:
        """유사도 기반 지능형 필터링 (max_match=6일 때 사용)
        
        과거 당첨번호와의 유사도를 계산하여 너무 유사한 조합은 제외하고,
        적절한 거리를 유지하는 조합을 선택합니다.
        """
        try:
            # 유사도 임계값 설정 (조정 가능)
            similarity_threshold = 0.8  # 80% 이상 유사한 조합 제외
            min_diversity_score = 0.2   # 최소 다양성 점수
            
            filtered_combinations = []
            batch_size = 1000
            
            # 배치 단위로 처리
            for i in tqdm(range(0, len(combinations), batch_size), desc="유사도 기반 필터링"):
                batch = combinations[i:i + batch_size]
                batch_arrays = np.array([
                    list(map(int, comb.split(',')))
                    for comb in batch
                ], dtype=np.int8)
                
                # 각 조합에 대한 최대 유사도 계산
                max_similarities = []
                diversity_scores = []
                
                for comb_array in batch_arrays:
                    # Jaccard 유사도 계산 (교집합 / 합집합)
                    similarities = []
                    for win_array in winning_arrays:
                        intersection = np.sum(np.in1d(comb_array, win_array))
                        union = len(np.unique(np.concatenate([comb_array, win_array])))
                        similarity = intersection / union if union > 0 else 0
                        similarities.append(similarity)
                    
                    max_similarity = max(similarities) if similarities else 0
                    max_similarities.append(max_similarity)
                    
                    # 다양성 점수 계산 (번호의 분산 정도)
                    diversity = np.std(comb_array) / np.mean(comb_array)
                    diversity_scores.append(diversity)
                
                # 필터링 조건: 유사도가 너무 높지 않고, 적절한 다양성을 가진 조합
                for j, (comb, sim, div) in enumerate(zip(batch, max_similarities, diversity_scores)):
                    if sim < similarity_threshold and div >= min_diversity_score:
                        filtered_combinations.append(comb)
                    elif sim >= similarity_threshold:
                        logging.debug(f"제외: {comb} (유사도: {sim:.2f})")
            
            # 필터링 결과 로깅
            excluded_count = len(combinations) - len(filtered_combinations)
            exclusion_rate = (excluded_count / len(combinations)) * 100
            logging.info(f"유사도 기반 필터링 완료: {len(filtered_combinations):,}/{len(combinations):,}개 남음 "
                        f"({excluded_count:,}개 제외, {exclusion_rate:.2f}%)")
            
            return filtered_combinations
            
        except Exception as e:
            logging.error(f"유사도 기반 필터링 중 오류 발생: {str(e)}")
            # 오류 발생 시 원본 반환
            return combinations