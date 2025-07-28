from typing import List, Set, Dict, Optional, Tuple, Generator
import logging
from itertools import combinations
from tqdm import tqdm
from math import comb
from ..utils.constants import LottoConstants
from ..utils.validators import LottoValidator

class CombinationManager:
    """로또 번호 조합 생성 및 관리를 담당하는 클래스
    
    이 클래스는 로또 번호 조합의 생성, 검증, 저장 및 관리를 담당합니다.
    대량의 조합을 효율적으로 처리하기 위한 배치 처리 기능을 포함합니다.
    
    Attributes:
        db_manager: 데이터베이스 관리자 인스턴스
        validator: 로또 번호 검증기 인스턴스
    """
    
    def __init__(self, db_manager):
        """CombinationManager 초기화
        
        Args:
            db_manager: 데이터베이스 작업을 처리할 매니저 인스턴스
        """
        self.db_manager = db_manager
        self.validator = LottoValidator()
        self.batch_size = LottoConstants.BATCH_SIZE

    def generate_base_combinations(self) -> bool:
        """기본 로또 번호 조합 생성
        
        1부터 45까지의 숫자 중 6개를 선택하는 모든 조합을 생성하고 저장합니다.
        배치 처리를 통해 메모리를 효율적으로 관리합니다.
        
        Returns:
            bool: 생성 성공 여부
        """
        logging.info("\n[조합 생성] 기본 로또 조합 생성 시작")
        try:
            total_combinations = self._calculate_total_combinations()  # 45C6 = 8,145,060
            processed_count = 0
            batch = []
            
            # combinations() 함수를 사용하여 모든 가능한 조합 생성
            all_combs = combinations(range(1, LottoConstants.MAX_NUMBER + 1), 
                                LottoConstants.COMBINATION_SIZE)
            
            with tqdm(total=total_combinations, desc="조합 생성 진행률", unit="조합") as pbar:
                for comb in all_combs:
                    if self._is_valid_combination(comb):
                        # 정렬된 번호를 문자열로 변환
                        batch.append(','.join(map(str, sorted(comb))))
                        processed_count += 1
                        
                        # 배치 크기에 도달하면 저장
                        if len(batch) >= self.batch_size:
                            self.db_manager.save_base_combinations(batch)
                            pbar.update(len(batch))
                            batch = []
                
                # 마지막 배치 처리
                if batch:
                    self.db_manager.save_base_combinations(batch)
                    pbar.update(len(batch))
            
            if processed_count != total_combinations:
                logging.error(f"생성된 조합 수({processed_count:,}개)가 " 
                            f"예상 조합 수({total_combinations:,}개)와 일치하지 않습니다.")
                return False
                
            logging.info(f"총 {total_combinations:,}개의 조합 생성 완료")
            return True
            
        except Exception as e:
            logging.error(f"조합 생성 중 오류 발생: {str(e)}")
            return False

    def get_combinations_subset(self, start_idx: int, size: int) -> List[str]:
        """특정 범위의 조합 가져오기
        
        Args:
            start_idx: 시작 인덱스
            size: 가져올 조합의 개수
            
        Returns:
            List[str]: 조합 목록
        """
        combinations = self.db_manager.get_base_combinations()
        return combinations[start_idx:start_idx + size] if combinations else []

    def validate_and_save_combinations(self, combinations: List[str]) -> Tuple[int, int]:
        """조합 목록의 유효성을 검사하고 저장
        
        Args:
            combinations: 검사 및 저장할 조합 목록
            
        Returns:
            Tuple[int, int]: (성공 수, 실패 수)
        """
        valid_combs = []
        invalid_count = 0
        
        for comb in combinations:
            numbers = list(map(int, comb.split(',')))
            if self._is_valid_combination(numbers):
                valid_combs.append(comb)
            else:
                invalid_count += 1
                
        success_count = len(valid_combs)
        if valid_combs:
            self.db_manager.save_base_combinations(valid_combs)
            
        return success_count, invalid_count

    def get_combinations_status(self) -> Dict[str, int]:
        """조합 생성 현황 조회
        
        Returns:
            Dict[str, int]: 현황 정보 (전체 개수, 유효 개수 등)
        """
        total = self._calculate_total_combinations()
        current = len(self.db_manager.get_base_combinations())
        
        return {
            'total_possible': total,
            'current_count': current,
            'remaining': total - current
        }

    def _calculate_total_combinations(self) -> int:
        """전체 가능한 조합 수 계산
        
        Returns:
            int: 전체 조합 수 (45C6 = 8,145,060)
        """
        return comb(LottoConstants.MAX_NUMBER, LottoConstants.COMBINATION_SIZE)

    def _is_valid_combination(self, numbers: List[int]) -> bool:
        """번호 조합의 유효성 검사
        
        Args:
            numbers: 검사할 번호 목록
            
        Returns:
            bool: 유효성 여부
        """
        if len(numbers) != LottoConstants.COMBINATION_SIZE:
            return False
            
        if len(set(numbers)) != LottoConstants.COMBINATION_SIZE:
            return False
            
        if not all(self.validator.is_valid_number(num) for num in numbers):
            return False
            
        return True

    def get_combination_batches(self, batch_size: Optional[int] = None) -> Generator[List[str], None, None]:
        """조합을 배치 단위로 가져오는 제너레이터
        
        Args:
            batch_size: 배치 크기 (기본값: self.batch_size)
            
        Yields:
            List[str]: 조합 배치
        """
        size = batch_size or self.batch_size
        combinations = self.db_manager.get_base_combinations()
        
        for i in range(0, len(combinations), size):
            yield combinations[i:i + size]

    def clear_invalid_combinations(self) -> int:
        """유효하지 않은 조합 제거
        
        Returns:
            int: 제거된 조합 수
        """
        removed_count = 0
        for batch in self.get_combination_batches():
            invalid_combs = [
                comb for comb in batch 
                if not self._is_valid_combination(list(map(int, comb.split(','))))
            ]
            if invalid_combs:
                removed_count += len(invalid_combs)
        return removed_count

    def validate_combination_format(self, combination: str) -> bool:
        """조합 문자열 형식 검사
        
        Args:
            combination: 검사할 조합 문자열 (예: "1,2,3,4,5,6")
            
        Returns:
            bool: 형식 유효성 여부
        """
        try:
            numbers = list(map(int, combination.split(',')))
            return (
                len(numbers) == LottoConstants.COMBINATION_SIZE and
                all(1 <= num <= LottoConstants.MAX_NUMBER for num in numbers) and
                len(set(numbers)) == LottoConstants.COMBINATION_SIZE
            )
        except (ValueError, TypeError):
            return False