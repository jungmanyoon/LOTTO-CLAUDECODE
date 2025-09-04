#!/usr/bin/env python3
"""
용어 통일 모듈
한글/영어 용어 매핑 및 일관된 로그 출력 지원
"""

class FilterTerminology:
    """필터 용어 통일 관리 클래스"""
    
    # 필터 이름 매핑 (영어 -> 한글)
    FILTER_NAMES = {
        'match': '번호 일치',
        'match_filter': '번호 일치',
        'MatchFilter': '번호 일치',
        
        'odd_even': '홀짝 분포',
        'odd_even_filter': '홀짝 분포',
        'OddEvenFilter': '홀짝 분포',
        
        'consecutive': '연속 번호',
        'consecutive_filter': '연속 번호',
        'ConsecutiveFilter': '연속 번호',
        
        'sum_range': '합계 범위',
        'sum_range_filter': '합계 범위',
        'SumRangeFilter': '합계 범위',
        
        'fixed_step': '고정 간격',
        'fixed_step_filter': '고정 간격',
        'FixedStepFilter': '고정 간격',
        
        'last_digit': '끝자리 분포',
        'last_digit_filter': '끝자리 분포',
        'LastDigitFilter': '끝자리 분포',
        
        'max_gap': '최대 간격',
        'max_gap_filter': '최대 간격',
        'MaxGapFilter': '최대 간격',
        
        'section': '구간 분포',
        'section_filter': '구간 분포',
        'SectionFilter': '구간 분포',
        
        'average': '평균값',
        'average_filter': '평균값',
        'AverageFilter': '평균값',
        
        'multiple': '배수 패턴',
        'multiple_filter': '배수 패턴',
        'MultipleFilter': '배수 패턴',
        
        'ten_section': '10구간 분포',
        'ten_section_filter': '10구간 분포',
        'TenSectionFilter': '10구간 분포',
        
        'arithmetic_sequence': '등차수열',
        'arithmetic_sequence_filter': '등차수열',
        'ArithmeticSequenceFilter': '등차수열',
        
        'geometric_sequence': '등비수열',
        'geometric_sequence_filter': '등비수열',
        'GeometricSequenceFilter': '등비수열',
        
        'prime_composite': '소수/합성수',
        'prime_composite_filter': '소수/합성수',
        'PrimeCompositeFilter': '소수/합성수',
        
        'digit_sum': '자릿수 합계',
        'digit_sum_filter': '자릿수 합계',
        'DigitSumFilter': '자릿수 합계',
        
        'dispersion': '분산도',
        'dispersion_filter': '분산도',
        'DispersionFilter': '분산도',
        
        'ml_prediction': 'ML 예측',
        'ml_prediction_filter': 'ML 예측',
        'MLPredictionFilter': 'ML 예측',
    }
    
    # 파라미터 이름 매핑
    PARAMETER_NAMES = {
        'max_match': '최대 일치 개수',
        'excluded_counts': '제외 개수',
        'max_consecutive': '최대 연속',
        'min_sum': '최소 합계',
        'max_sum': '최대 합계',
        'min_average': '최소 평균',
        'max_average': '최대 평균',
        'min_same_last_digits': '최소 동일 끝자리',
        'max_allowed_gap': '최대 허용 간격',
        'max_numbers_per_section': '구간당 최대 개수',
        'threshold': '임계값',
        'min_variance': '최소 분산',
        'max_variance': '최대 분산',
        'required_matches': '필요 매칭 수',
        'steps_to_exclude': '제외 간격',
    }
    
    # 공통 용어
    COMMON_TERMS = {
        'combination': '조합',
        'combinations': '조합',
        'round': '회차',
        'winning_numbers': '당첨번호',
        'threshold': '임계값',
        'distribution': '분포',
        'pattern': '패턴',
        'criteria': '기준값',
        'exclude': '제외',
        'filter': '필터',
        'batch': '배치',
        'chunk': '청크',
        'applied': '적용됨',
        'remaining': '남음',
        'excluded': '제외됨',
        'passed': '통과',
        'failed': '실패',
    }
    
    @classmethod
    def get_korean_name(cls, english_name: str, with_english: bool = False) -> str:
        """
        영어 필터명을 한글로 변환
        
        Args:
            english_name: 영어 필터명
            with_english: True면 "한글(영어)" 형식으로 반환
            
        Returns:
            한글 필터명
        """
        korean = cls.FILTER_NAMES.get(english_name, english_name)
        
        if with_english and english_name in cls.FILTER_NAMES:
            return f"{korean}({english_name})"
        
        return korean
    
    @classmethod
    def get_parameter_korean(cls, param_name: str, with_english: bool = False) -> str:
        """
        영어 파라미터명을 한글로 변환
        
        Args:
            param_name: 영어 파라미터명
            with_english: True면 "한글(영어)" 형식으로 반환
            
        Returns:
            한글 파라미터명
        """
        korean = cls.PARAMETER_NAMES.get(param_name, param_name)
        
        if with_english and param_name in cls.PARAMETER_NAMES:
            return f"{korean}({param_name})"
        
        return korean
    
    @classmethod
    def format_filter_log(cls, filter_name: str, before_count: int, after_count: int) -> str:
        """
        필터 로그 메시지 포맷팅
        
        Args:
            filter_name: 필터 이름
            before_count: 필터 적용 전 개수
            after_count: 필터 적용 후 개수
            
        Returns:
            포맷된 로그 메시지
        """
        korean_name = cls.get_korean_name(filter_name)
        excluded = before_count - after_count
        exclusion_rate = (excluded / before_count * 100) if before_count > 0 else 0
        
        return f"[{korean_name}] {before_count:,} → {after_count:,} ({exclusion_rate:.1f}% 제외)"
    
    @classmethod
    def format_filter_complete(cls, filter_name: str, total: int, remaining: int) -> str:
        """
        필터 완료 메시지 포맷팅
        
        Args:
            filter_name: 필터 이름
            total: 전체 개수
            remaining: 남은 개수
            
        Returns:
            포맷된 완료 메시지
        """
        korean_name = cls.get_korean_name(filter_name)
        excluded = total - remaining
        
        return f"[{korean_name}] 필터 완료: {remaining:,}/{total:,}개 남음 ({excluded:,}개 제외됨)"
    
    @classmethod
    def format_error(cls, filter_name: str, error: str) -> str:
        """
        필터 오류 메시지 포맷팅
        
        Args:
            filter_name: 필터 이름
            error: 오류 메시지
            
        Returns:
            포맷된 오류 메시지
        """
        korean_name = cls.get_korean_name(filter_name, with_english=True)
        return f"{korean_name} 필터링 중 오류 발생: {error}"
    
    @classmethod
    def get_filter_description(cls, filter_name: str) -> str:
        """
        필터 설명 반환
        
        Args:
            filter_name: 필터 이름
            
        Returns:
            필터 설명
        """
        descriptions = {
            'match': '과거 당첨번호와의 일치 개수를 검사합니다',
            'odd_even': '홀수/짝수 번호의 분포를 검사합니다',
            'consecutive': '연속된 번호의 개수를 제한합니다',
            'sum_range': '6개 번호의 합계 범위를 제한합니다',
            'fixed_step': '일정한 간격을 가진 번호들을 제외합니다',
            'last_digit': '끝자리 숫자의 분포를 검사합니다',
            'max_gap': '인접 번호 간 최대 간격을 제한합니다',
            'section': '1-45를 15개 구간으로 나눠 분포를 검사합니다',
            'average': '6개 번호의 평균값 범위를 제한합니다',
            'multiple': '특정 숫자의 배수 개수를 제한합니다',
            'ten_section': '1-45를 10개 구간으로 나눠 분포를 검사합니다',
            'arithmetic_sequence': '등차수열 패턴을 제외합니다',
            'geometric_sequence': '등비수열 패턴을 제외합니다',
            'prime_composite': '소수와 합성수의 개수 분포를 검사합니다',
            'digit_sum': '각 번호의 자릿수 합계를 검사합니다',
            'dispersion': '번호들의 분산도와 표준편차를 검사합니다',
            'ml_prediction': 'ML 모델의 예측 확률 기반으로 필터링합니다',
        }
        
        return descriptions.get(filter_name, '필터 설명이 없습니다')


# 전역 인스턴스 (편의를 위해)
terminology = FilterTerminology()
get_korean_name = terminology.get_korean_name
format_filter_log = terminology.format_filter_log
format_filter_complete = terminology.format_filter_complete
format_error = terminology.format_error