from typing import List, Set, Dict, Any, Optional, Tuple
from .constants import LottoConstants
import struct

class LottoValidator:
    """로또 번호와 조합의 유효성을 검사하는 클래스"""
    
    @staticmethod
    def is_valid_number(number: int) -> bool:
        """단일 로또 번호의 유효성 검사
        
        Args:
            number: 검사할 번호
            
        Returns:
            bool: 유효성 여부
        """
        return (
            isinstance(number, int) and 
            LottoConstants.MIN_NUMBER <= number <= LottoConstants.MAX_NUMBER
        )

    @staticmethod
    def is_valid_combination(numbers: List[int]) -> bool:
        """로또 번호 조합의 유효성 검사
        
        Args:
            numbers: 검사할 번호 목록
            
        Returns:
            bool: 유효성 여부
        """
        if len(numbers) != LottoConstants.COMBINATION_SIZE:
            return False
            
        if len(set(numbers)) != LottoConstants.COMBINATION_SIZE:
            return False
            
        return all(LottoValidator.is_valid_number(num) for num in numbers)

    @staticmethod
    def is_valid_combination_string(combination: str) -> bool:
        """문자열 형식 조합의 유효성 검사
        
        Args:
            combination: 쉼표로 구분된 번호 문자열
            
        Returns:
            bool: 유효성 여부
        """
        try:
            numbers = list(map(int, combination.split(',')))
            return LottoValidator.is_valid_combination(numbers)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_filter_criteria(criteria: Dict[str, Any], filter_type: str) -> bool:
        """필터링 기준값의 유효성 검사
        
        Args:
            criteria: 검사할 기준값
            filter_type: 필터 유형
            
        Returns:
            bool: 유효성 여부
            
        Raises:
            ValueError: 유효하지 않은 기준값이 제공된 경우
        """
        if filter_type == LottoConstants.FilterTypes.MATCH:
            if 'max_match' not in criteria:
                raise ValueError("'max_match' 값이 필요합니다.")
            max_match = criteria['max_match']
            if not isinstance(max_match, int) or max_match < 0 or max_match > 6:
                raise ValueError("'max_match'는 0에서 6 사이의 정수여야 합니다.")
                
        elif filter_type == LottoConstants.FilterTypes.ODD_EVEN:
            if 'excluded_patterns' not in criteria:
                raise ValueError("'excluded_patterns' 값이 필요합니다.")
            patterns = criteria['excluded_patterns']
            if not isinstance(patterns, (list, tuple)):
                raise ValueError("'excluded_patterns'는 리스트여야 합니다.")
            if not all(isinstance(x, int) and 0 <= x <= 6 for x in patterns):
                raise ValueError("패턴값은 0에서 6 사이의 정수여야 합니다.")
                
        elif filter_type == LottoConstants.FilterTypes.CONSECUTIVE:
            if 'max_consecutive' not in criteria:
                raise ValueError("'max_consecutive' 값이 필요합니다.")
            max_consecutive = criteria['max_consecutive']
            if not isinstance(max_consecutive, int) or max_consecutive < 2:
                raise ValueError("'max_consecutive'는 2 이상의 정수여야 합니다.")
                
        elif filter_type == LottoConstants.FilterTypes.SUM_RANGE:
            if 'min_sum' not in criteria or 'max_sum' not in criteria:
                raise ValueError("'min_sum'과 'max_sum' 값이 모두 필요합니다.")
            min_sum = criteria['min_sum']
            max_sum = criteria['max_sum']
            if not isinstance(min_sum, int) or not isinstance(max_sum, int):
                raise ValueError("합계 범위는 정수여야 합니다.")
            if min_sum >= max_sum:
                raise ValueError("최소값이 최대값보다 작아야 합니다.")
                
        return True

    @staticmethod
    def create_error_report(combinations: List[str]) -> Dict[str, Any]:
        """조합 목록의 오류 리포트 생성
        
        Args:
            combinations: 검사할 조합 목록
            
        Returns:
            Dict: 오류 리포트
        """
        report = {
            'total': len(combinations),
            'valid': 0,
            'invalid': 0,
            'errors': {
                'wrong_format': 0,
                'invalid_numbers': 0,
                'duplicate_numbers': 0,
                'wrong_size': 0
            }
        }
        
        for comb in combinations:
            try:
                numbers = list(map(int, comb.split(',')))
                
                if len(numbers) != LottoConstants.COMBINATION_SIZE:
                    report['errors']['wrong_size'] += 1
                elif len(set(numbers)) != LottoConstants.COMBINATION_SIZE:
                    report['errors']['duplicate_numbers'] += 1
                elif not all(LottoValidator.is_valid_number(num) for num in numbers):
                    report['errors']['invalid_numbers'] += 1
                else:
                    report['valid'] += 1
                    continue
                    
            except (ValueError, TypeError):
                report['errors']['wrong_format'] += 1
                
            report['invalid'] += 1
            
        return report

    @staticmethod
    def encode_combination(numbers: List[int]) -> int:
        """로또 번호 조합(6개 숫자)을 비트맵 정수로 인코딩
        
        비트맵 인코딩: 1~45 각 번호의 존재 여부를 비트로 표현
        
        Args:
            numbers: 6개의 로또 번호 리스트 (1~45 사이 정수)
            
        Returns:
            int: 비트맵 정수 (0~2^45-1 사이 값)
        """
        if not numbers or len(numbers) != LottoConstants.COMBINATION_SIZE:
            raise ValueError(f"조합은 정확히 {LottoConstants.COMBINATION_SIZE}개의 번호로 구성되어야 합니다")
            
        bitmap = 0
        for num in numbers:
            if not LottoValidator.is_valid_number(num):
                raise ValueError(f"유효하지 않은 로또 번호: {num}")
            bitmap |= (1 << (num - 1))
            
        return bitmap
    
    @staticmethod
    def decode_combination(bitmap: int) -> List[int]:
        """비트맵 정수에서 로또 번호 조합 복원
        
        Args:
            bitmap: 비트맵 정수
            
        Returns:
            List[int]: 로또 번호 조합 (6개 번호 리스트)
        """
        numbers = []
        for i in range(LottoConstants.MAX_NUMBER):
            if bitmap & (1 << i):
                numbers.append(i + 1)
                
        return numbers
    
    @staticmethod
    def bitmap_to_bytes(bitmap: int) -> bytes:
        """비트맵 정수를 바이트 배열로 변환 (데이터베이스 저장용)
        
        Args:
            bitmap: 비트맵 정수
            
        Returns:
            bytes: 6바이트 배열
        """
        # 45비트는 최대 6바이트(48비트)에 저장 가능
        return struct.pack('<Q', bitmap)[:6]  # 8바이트 정수를 6바이트만 사용
    
    @staticmethod
    def bytes_to_bitmap(byte_data: bytes) -> int:
        """바이트 배열에서 비트맵 정수 복원
        
        Args:
            byte_data: 6바이트 배열
            
        Returns:
            int: 비트맵 정수
        """
        # 6바이트를 8바이트로 확장하여 언패킹
        full_bytes = byte_data + b'\x00\x00'  # 추가 2바이트
        return struct.unpack('<Q', full_bytes)[0]
    
    @staticmethod
    def combination_to_str(numbers: List[int]) -> str:
        """번호 리스트를 문자열로 변환
        
        Args:
            numbers: 번호 리스트
            
        Returns:
            str: 콤마로 구분된 번호 문자열
        """
        return ','.join(map(str, sorted(numbers)))
    
    @staticmethod
    def str_to_combination(comb_str: str) -> List[int]:
        """문자열에서 번호 리스트로 변환
        
        Args:
            comb_str: 콤마로 구분된 번호 문자열
            
        Returns:
            List[int]: 번호 리스트
        """
        return sorted([int(num) for num in comb_str.split(',')])