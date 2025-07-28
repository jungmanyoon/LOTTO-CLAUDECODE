from typing import Dict, Final, List, Tuple

class LottoConstants:
    """로또 관련 상수 정의"""
    
    # 기본 상수
    MIN_NUMBER: Final[int] = 1
    MAX_NUMBER: Final[int] = 45
    COMBINATION_SIZE: Final[int] = 6
    
    # 배치 처리 관련
    BATCH_SIZE: Final[int] = 10000
    MAX_BATCH_MEMORY: Final[int] = 1000000

    # 필터 기준값 설정
    class FilterCriteria:
        """필터별 기준값 설정"""
        
        # Match 필터
        MATCH = {
            'max_match': 4  # 당첨번호와 일치하는 번호가 4개 이상인 조합 제외
        }
        
        # 홀짝 필터
        ODD_EVEN = {
            'excluded_counts': [6]  # 홀수 또는 짝수가 6개인 조합 제외
        }
                
        # 연속 번호 필터
        CONSECUTIVE = {
            'max_consecutive': 4,  # 4개 이상 연속된 번호가 있는 조합 제외
            'min_gap': 1,         # 최소 간격 기준값
            'default_criteria': {  # 기본 기준값 정의
                'max_consecutive': 4,
                'min_gap': 1
            }
        }
        
        # 합계 범위 필터
        SUM_RANGE = {
            'min_sum': 67,
            'max_sum': 209.5  # 6개 번호의 합이 67~209.5 범위를 벗어나는 조합 제외
        }
        
        # 고정 간격 필터
        FIXED_STEP = {
            'all_steps': {  # 6개 모두 동일 간격인 경우
                'steps_to_exclude': list(range(2, 9)),
                'required_matches': 6
            },
            'partial_steps': {  # 5개 연속 동일 간격인 경우
                'steps_to_exclude': list(range(2, 9)),
                'required_matches': 5
            },
            'four_steps': {  # 4개 연속 동일 간격인 경우
                'steps_to_exclude': list(range(2, 9)),
                'required_matches': 4
            },
            'three_steps': {  # 3개 연속 동일 간격인 경우
                'steps_to_exclude': [],
                'required_matches': 3
            }
        }
        
        # 끝자리 숫자 필터
        LAST_DIGIT = {
            'min_same_last_digits': 4  # 끝자리 숫자가 4개 이상 동일한 조합 제외
        }
        
        # 최대 간격 필터
        MAX_GAP = {
            'max_allowed_gap': 26  # 인접한 두 숫자의 최대 간격이 26 이상인 조합 제외
        }
        
        # 구간 필터
        SECTION = {
            'max_numbers_per_section': 5,  # 각 구간당 최대 5개
            'exclude_all_section': True    # 한 구간에 6개 모두 있는 경우 제외
        }
        
        # 평균값 필터
        AVERAGE = {
            'min_average': 11.2,
            'max_average': 36.5,
            'exclude_extremes': True  # 극단적인 평균값 제외
        }
        
        # 배수 필터
        MULTIPLE = {
            'multiples': {
                3: [0, 5],  # 3의 배수는 0~5개 허용 (6개만 제외)
                4: [0, 3],  # 4의 배수는 0~3개 허용 (4개 이상 제외)
                5: [0, 3]   # 5의 배수는 0~3개 허용 (4개 이상 제외)
            }
        }

        # 10구간 필터 - 이미 수정됨
        TEN_SECTION = {
            'section_limits': {
                'section1': [4, 5, 6],    # [구간 1-10] 4,5,6개 제외
                'section2': [5, 6],       # [구간 11-20] 5,6개 제외
                'section3': [5, 6],       # [구간 21-30] 5,6개 제외
                'section4': [5, 6],       # [구간 31-40] 5,6개 제외
                'section5': [4, 5]        # [구간 41-45] 4,5개 제외
            }
        }
        
        # 등차수열 필터 - 구조 수정
        ARITHMETIC_SEQUENCE = {
            'min_sequence': 5,  # 5개 이상 연속 제외
            'excluded_lengths': [5, 6]  # 5개 또는 6개 연속 제외
        }
        
        # 등비수열 필터 - 구조 수정
        GEOMETRIC_SEQUENCE = {
            'min_sequence': 4,  # 4개 이상 연속 제외
            'excluded_lengths': [4, 5, 6]  # 4,5,6개 연속 제외
        }

    # 배수 패턴 관련
    class MultipleDefaults:
        """배수 패턴 기본값"""
        BASES: Final[List[int]] = [2, 3, 4, 5]  # 분석할 배수들
        MAX_COUNTS: Final[Dict[int, int]] = {
            2: 3,  # 2의 배수는 최대 3개
            3: 2,  # 3의 배수는 최대 2개
            4: 2,  # 4의 배수는 최대 2개
            5: 2   # 5의 배수는 최대 2개
        }
        MIN_COUNTS: Final[Dict[int, int]] = {
            2: 1,  # 2의 배수는 최소 1개
            3: 1,  # 3의 배수는 최소 1개
            4: 0,  # 4의 배수는 최소 0개
            5: 0   # 5의 배수는 최소 0개
        }
    
    # 홀짝 교차 패턴 관련
    class AlternatingDefaults:
        """홀짝 교차 패턴 기본값"""
        PATTERNS: Final[List[str]] = ['perfect_odd_start', 'perfect_even_start', 'partial']
        EXCLUDE_PERFECT: Final[bool] = True  # 완벽한 홀짝 교차 패턴 제외
        MIN_ALTERNATING: Final[int] = 3      # 최소 교차 횟수
        
        # 교차 패턴 정의
        PERFECT_ODD_START: Final[List[int]] = [1, 0, 1, 0, 1, 0]  # 홀-짝-홀-짝-홀-짝
        PERFECT_EVEN_START: Final[List[int]] = [0, 1, 0, 1, 0, 1] # 짝-홀-짝-홀-짝-홀
        
        # 패턴별 출현 빈도 임계값
        FREQUENCY_THRESHOLDS: Final[Dict[str, float]] = {
            'perfect_odd_start': 5.0,   # 5% 이상이면 제외
            'perfect_even_start': 5.0,  # 5% 이상이면 제외
            'partial': 15.0            # 15% 이상이면 제외
        }

    # 합계 배수 패턴 관련
    class SumMultipleDefaults:
        """합계 배수 패턴 기본값"""
        BASES: Final[List[int]] = [3, 5, 7, 9]  # 분석할 배수
        EXCLUDE_MULTIPLES: Final[bool] = True    # 배수 합계 제외
        FREQUENCY_THRESHOLD: Final[float] = 10.0  # 10% 이상 출현하는 배수 제외
        
        # 배수별 임계값
        THRESHOLDS: Final[Dict[int, float]] = {
            3: 12.0,  # 3의 배수 합계가 12% 이상이면 제외
            5: 8.0,   # 5의 배수 합계가 8% 이상이면 제외
            7: 6.0,   # 7의 배수 합계가 6% 이상이면 제외
            9: 5.0    # 9의 배수 합계가 5% 이상이면 제외
        }
        
        # 배수별 허용 범위
        RANGES: Final[Dict[int, Tuple[int, int]]] = {
            3: (69, 195),  # 3의 배수 합계 허용 범위
            5: (70, 190),  # 5의 배수 합계 허용 범위
            7: (70, 189),  # 7의 배수 합계 허용 범위
            9: (72, 189)   # 9의 배수 합계 허용 범위
        }

    # 필터링 옵션 관련
    class FilterOptions:
        """필터링 옵션 기본값"""
        ENABLE_ALL: Final[bool] = True           # 모든 필터 활성화
        PARALLEL_PROCESSING: Final[bool] = True  # 병렬 처리 사용
        MAX_WORKERS: Final[int] = 4             # 최대 작업자 수
        CHUNK_SIZE: Final[int] = 10000         # 청크 크기
        
        # 필터별 가중치 (중요도)
        WEIGHTS: Final[Dict[str, float]] = {
            'match': 1.0,
            'odd_even': 0.8,
            'consecutive': 0.7,
            'sum_range': 0.6,
            'fixed_step': 0.5,
            'last_digit': 0.4,
            'max_gap': 0.4,
            'section': 0.3,
            'average': 0.3,
            'multiple': 0.3,
            'alternating_odd_even': 0.3,
            'sum_multiple': 0.3
        }
        
    # 패턴 분석 관련
    class PatternTypes:
        """패턴 분석 유형"""
        NUMBER_FREQUENCY: Final[str] = 'number_frequency'
        PAIR_FREQUENCY: Final[str] = 'pair_frequency'
        ODD_EVEN: Final[str] = 'odd_even'
        CONSECUTIVE: Final[str] = 'consecutive'
        SUM_RANGE: Final[str] = 'sum_range'
        FIXED_STEP: Final[str] = 'fixed_step'
        LAST_DIGIT: Final[str] = 'last_digit'
        MAX_GAP: Final[str] = 'max_gap'
        SECTION: Final[str] = 'section'
        AVERAGE: Final[str] = 'average'
        MULTIPLE: Final[str] = 'multiple'
        TEN_SECTION: Final[str] = 'ten_section_distribution'
        ARITHMETIC_SEQUENCE: Final[str] = 'arithmetic_sequence'
        GEOMETRIC_SEQUENCE: Final[str] = 'geometric_sequence'

    
    # 필터 타입
    class FilterTypes:
        """필터 유형"""
        MATCH: Final[str] = 'match'
        ODD_EVEN: Final[str] = 'odd_even'
        CONSECUTIVE: Final[str] = 'consecutive'
        SUM_RANGE: Final[str] = 'sum_range'
        FIXED_STEP: Final[str] = 'fixed_step'
        LAST_DIGIT: Final[str] = 'last_digit'
        MAX_GAP: Final[str] = 'max_gap'
        SECTION: Final[str] = 'section'
        AVERAGE: Final[str] = 'average'
        MULTIPLE: Final[str] = 'multiple'
    
    # 데이터베이스 관련
    class DatabaseDefaults:
        """데이터베이스 기본값"""
        TIMEOUT: Final[int] = 30
        MAX_RETRIES: Final[int] = 3
        BATCH_SIZE: Final[int] = 5000
        
        TABLES: Final[Dict[str, str]] = {
            'LOTTO_NUMBERS': 'lotto_numbers',
            'COMBINATIONS': 'combinations',
            'PATTERNS': 'pattern_analysis',
            'FILTERED': 'filtered_combinations'
        }
    
    # 필터링 모드
    class FilteringModes:
        """필터링 모드"""
        NORMAL: Final[str] = 'normal'      # 일반 필터링
        STRICT: Final[str] = 'strict'      # 엄격한 필터링
        RELAXED: Final[str] = 'relaxed'    # 느슨한 필터링
        
        CRITERIA: Final[Dict[str, Dict]] = {
            'normal': {
                'max_match': 4,
                'consecutive': 3,
                'sum_range': (67, 200)
            },
            'strict': {
                'max_match': 3,
                'consecutive': 2,
                'sum_range': (90, 180)
            },
            'relaxed': {
                'max_match': 5,
                'consecutive': 4,
                'sum_range': (50, 220)
            }
        }
    
    # 신규: 구간 정의
    class SectionRanges:
        """번호 구간 정의"""
        FIFTEEN_SECTIONS: Final[List[Tuple[int, int]]] = [
            (1, 15), (16, 30), (31, 45)
        ]
        
        TEN_SECTIONS: Final[List[Tuple[int, int]]] = [
            (1, 10), (11, 20), (21, 30), (31, 40), (41, 45)
        ]

    # 신규: 수열 패턴 관련
    class SequencePatterns:
        """수열 패턴 설정"""
        MIN_SEQUENCE_LENGTH: Final[int] = 3
        MAX_SEQUENCE_LENGTH: Final[int] = 6
        MAX_RATIO: Final[int] = 3  # 등비수열의 최대 비율

    # 메시지 템플릿
    class Messages:
        """로그 메시지"""
        INIT_START: Final[str] = "[초기화] 데이터베이스 및 매니저 초기화 중..."
        DATA_COLLECTION: Final[str] = "[데이터 수집] 로또 당첨 번호 수집 시작..."
        PATTERN_ANALYSIS: Final[str] = "[패턴 분석] 데이터 패턴 분석 시작..."
        FILTERING_START: Final[str] = "[조합 필터링] 로또 번호 조합 필터링 시작..."
        PROCESS_COMPLETE: Final[str] = "[완료] 모든 작업이 정상적으로 완료되었습니다."
        
        # 패턴 관련 메시지
        MULTIPLE_PATTERN: Final[str] = "[배수 패턴] {base}의 배수 분석 중..."
        ALTERNATING_PATTERN: Final[str] = "[홀짝 교차] 패턴 분석 중..."
        SUM_MULTIPLE_PATTERN: Final[str] = "[합계 배수] 패턴 분석 중..."
        
        # 필터 관련 메시지
        MULTIPLE_FILTER: Final[str] = "[배수 필터] {count}개 조합 제외됨 ({ratio:.2f}%)"
        ALTERNATING_FILTER: Final[str] = "[홀짝 교차 필터] {count}개 조합 제외됨 ({ratio:.2f}%)"
        SUM_MULTIPLE_FILTER: Final[str] = "[합계 배수 필터] {count}개 조합 제외됨 ({ratio:.2f}%)"

        # 오류 메시지
        ERROR_INVALID_FILTER: Final[str] = "잘못된 필터 유형입니다: {filter_type}"
        ERROR_INVALID_PATTERN: Final[str] = "잘못된 패턴 유형입니다: {pattern_type}"
        ERROR_INVALID_MODE: Final[str] = "잘못된 필터링 모드입니다: {mode}"
        ERROR_DB_CONNECTION: Final[str] = "데이터베이스 연결 오류: {error}"
        ERROR_DATA_FETCH: Final[str] = "데이터 조회 중 오류 발생: {error}"
        ERROR_DATA_SAVE: Final[str] = "데이터 저장 중 오류 발생: {error}"

        # 진행 상태 메시지
        PROGRESS_COMBINATION: Final[str] = "조합 생성 진행률: {progress:.1f}% ({current:,}/{total:,})"
        PROGRESS_FILTER: Final[str] = "{filter_name} 필터 진행률: {progress:.1f}% ({current:,}/{total:,})"
        PROGRESS_PATTERN: Final[str] = "{pattern_name} 패턴 분석 진행률: {progress:.1f}% ({current:,}/{total:,})"

        # 결과 요약 메시지
        SUMMARY_FILTER: Final[str] = """
[필터링 결과 요약]
- 초기 조합 수: {initial:,}개
- 제외된 조합 수: {filtered:,}개
- 남은 조합 수: {remaining:,}개
- 필터링 비율: {ratio:.2f}%
"""
        SUMMARY_PATTERN: Final[str] = """
[패턴 분석 결과 요약]
{pattern_results}
"""