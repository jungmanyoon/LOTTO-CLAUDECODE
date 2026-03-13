from typing import Dict, List, Optional
import logging
from collections import defaultdict, OrderedDict
import time
import threading

class PatternManager:
    """당첨 번호의 패턴을 분석하고 관리하는 클래스"""

    # ============================================================
    # FIX CRITICAL-12: 캐시 크기 제한 상수
    # ============================================================
    MAX_CACHE_ENTRIES = 50  # 최대 캐시 항목 수
    CACHE_TTL_SECONDS = 3600  # 캐시 TTL (1시간)

    def __init__(self, db_manager):
        """PatternManager 초기화

        Args:
            db_manager: DatabaseManager 인스턴스
        """
        self.db_manager = db_manager  # db_manager 저장
        self.db = db_manager.patterns_db
        self.winning_numbers = []  # 빈 리스트로 초기화

        # ============================================================
        # 🚀 PERFORMANCE OPTIMIZATION: 패턴 분석 캐싱 (크기 제한 적용)
        # ============================================================
        # FIX CRITICAL-12: OrderedDict로 변경하여 LRU 퇴출 지원
        self._pattern_cache = OrderedDict()  # data_hash -> {'data': patterns, 'timestamp': time}
        self._cache_lock = threading.RLock()  # 스레드 안전성
        self._last_data_hash = None

        # 당첨 번호 데이터 로드 시도
        try:
            self._sync_winning_numbers(db_manager.lotto_db)
            self._load_winning_numbers()
        except Exception as e:
            logging.error(f"당첨 번호 초기화 중 오류 발생: {str(e)}")
            self.winning_numbers = []  # 오류 발생 시 빈 리스트로 재설정

    # ============================================================
    # FIX CRITICAL-12: 캐시 관리 메서드 추가
    # ============================================================
    def _evict_expired_cache(self) -> int:
        """만료된 캐시 항목 퇴출 (TTL 기반)

        Returns:
            int: 퇴출된 항목 수
        """
        current_time = time.time()
        expired_keys = []

        with self._cache_lock:
            for key, value in self._pattern_cache.items():
                if current_time - value.get('timestamp', 0) > self.CACHE_TTL_SECONDS:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._pattern_cache[key]

        if expired_keys:
            logging.debug(f"패턴 캐시: {len(expired_keys)}개 만료 항목 퇴출")

        return len(expired_keys)

    def _evict_lru_if_needed(self) -> int:
        """캐시 크기 초과 시 LRU 퇴출

        Returns:
            int: 퇴출된 항목 수
        """
        evicted = 0

        with self._cache_lock:
            while len(self._pattern_cache) >= self.MAX_CACHE_ENTRIES:
                # OrderedDict에서 가장 오래된 항목 (첫 번째) 제거
                oldest_key = next(iter(self._pattern_cache))
                del self._pattern_cache[oldest_key]
                evicted += 1

        if evicted:
            logging.debug(f"패턴 캐시: LRU 정책으로 {evicted}개 항목 퇴출")

        return evicted

    def _get_cached_patterns(self, data_hash: str) -> Optional[Dict]:
        """캐시에서 패턴 조회 (LRU 업데이트 포함)

        Args:
            data_hash: 데이터 해시

        Returns:
            Optional[Dict]: 캐시된 패턴 또는 None
        """
        with self._cache_lock:
            if data_hash in self._pattern_cache:
                entry = self._pattern_cache[data_hash]
                current_time = time.time()

                # TTL 확인
                if current_time - entry.get('timestamp', 0) > self.CACHE_TTL_SECONDS:
                    del self._pattern_cache[data_hash]
                    return None

                # LRU 업데이트: 항목을 끝으로 이동
                self._pattern_cache.move_to_end(data_hash)
                return entry.get('data')

        return None

    def _set_cached_patterns(self, data_hash: str, patterns: Dict) -> None:
        """캐시에 패턴 저장

        Args:
            data_hash: 데이터 해시
            patterns: 저장할 패턴
        """
        # 먼저 만료된 항목 정리
        self._evict_expired_cache()

        with self._cache_lock:
            # 크기 제한 확인 및 LRU 퇴출
            self._evict_lru_if_needed()

            # 새 항목 저장
            self._pattern_cache[data_hash] = {
                'data': patterns,
                'timestamp': time.time()
            }

            # OrderedDict에서 끝으로 이동 (가장 최근 사용)
            self._pattern_cache.move_to_end(data_hash)

    def get_cache_stats(self) -> Dict:
        """캐시 상태 통계 반환

        Returns:
            Dict: 캐시 통계 정보
        """
        with self._cache_lock:
            current_time = time.time()
            valid_count = sum(
                1 for v in self._pattern_cache.values()
                if current_time - v.get('timestamp', 0) <= self.CACHE_TTL_SECONDS
            )

            return {
                'total_entries': len(self._pattern_cache),
                'valid_entries': valid_count,
                'max_entries': self.MAX_CACHE_ENTRIES,
                'ttl_seconds': self.CACHE_TTL_SECONDS
            }

    def _sync_winning_numbers(self, lotto_db):
        """당첨 번호 동기화

        Args:
            lotto_db: LottoNumbersDB 인스턴스
        """
        try:
            # LottoNumbersDB에서 당첨 번호 가져오기
            with lotto_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT round, numbers, draw_date FROM lotto_numbers ORDER BY round')
                rows = cursor.fetchall()
                
            # PatternsDB에 당첨 번호 저장
            for row in rows:
                round_num, numbers, draw_date = row
                self.db.save_winning_numbers(round_num, numbers, draw_date)
                
            logging.debug(f"당첨 번호 동기화 완료: {len(rows)}개")
                
        except Exception as e:
            logging.error(f"당첨 번호 동기화 중 오류 발생: {str(e)}")

    def _load_winning_numbers(self):
        """당첨 번호 데이터 로드"""
        try:
            with self.db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT numbers FROM winning_numbers ORDER BY round')
                result = cursor.fetchall()
                if result:
                    self.winning_numbers = [row[0] for row in result]
                    logging.info(f"당첨 번호 {len(self.winning_numbers)}개 로드 완료")
                else:
                    logging.warning("당첨 번호 데이터가 없습니다.")
                    self.winning_numbers = []
        except Exception as e:
            logging.error(f"당첨 번호 로드 중 오류 발생: {str(e)}")
            self.winning_numbers = []  # 오류 발생 시 빈 리스트로 초기화

    def _get_data_hash(self, winning_numbers: List[str]) -> str:
        """데이터 해시값 생성 (캐시 키로 사용)"""
        import hashlib
        data_str = '|'.join(sorted(winning_numbers))
        return hashlib.md5(data_str.encode()).hexdigest()

    def analyze_patterns(self, round_num: int = None) -> bool:
        """전체 패턴 분석 수행 (캐싱 지원)"""
        try:
            logging.info("\n" + "="*60)
            logging.info("🔍 [패턴 분석 시스템] 분석 시작")
            logging.info("="*60)

            if round_num is None:
                round_num = self.db_manager.lotto_db.get_last_round()

            if round_num is None:
                logging.error("분석할 회차 정보를 찾을 수 없습니다.")
                return False

            winning_numbers = self.winning_numbers
            if not winning_numbers:
                logging.error("분석할 당첨 번호가 없습니다.")
                return False

            # ============================================================
            # 🚀 PERFORMANCE OPTIMIZATION: 캐시 확인 (FIX CRITICAL-12: 크기 제한 적용)
            # ============================================================
            data_hash = self._get_data_hash(winning_numbers)
            cached_patterns = self._get_cached_patterns(data_hash)
            if data_hash == self._last_data_hash and cached_patterns is not None:
                logging.info(f"✅ 캐시된 패턴 분석 결과 사용 (hash: {data_hash[:8]}...)")
                self.db_manager.save_pattern_analysis(round_num, cached_patterns)
                return True

            logging.info(f"✅ 분석 대상: {round_num}회차")
            logging.info(f"✅ 분석할 데이터: {len(winning_numbers)}개 회차")

            patterns = {}
            successful_patterns = []
            failed_patterns = []
            
            # 모든 패턴 분석을 순차적으로 수행
            pattern_analyses = [
                ('match', self._analyze_match_patterns),
                ('odd_even', self._analyze_odd_even_patterns),
                ('consecutive', self._analyze_consecutive_patterns),
                ('sum_range', self._analyze_sum_patterns),
                ('fixed_step', self._analyze_fixed_step_patterns),
                ('last_digit', self._analyze_last_digit_patterns),
                ('max_gap', self._analyze_max_gap_patterns),
                ('section_distribution', self._analyze_section_patterns),
                ('number_average', self._analyze_average_patterns),
                ('multiple_patterns', self._analyze_multiple_patterns),
                # 새로운 패턴 분석 추가
                ('ten_section', self._analyze_ten_section_patterns),  # 10구간 분석 추가 (DB컬럼: ten_section_patterns)
                ('arithmetic_sequence', self._analyze_arithmetic_sequence),       # 등차수열 분석 추가
                ('geometric_sequence', self._analyze_geometric_sequence),          # 등비수열 분석 추가
                ('alternating_odd_even', self._analyze_alternating_odd_even_patterns),  # 홀짝 교차 패턴 분석 추가
                ('sum_multiple', self._analyze_sum_multiple_patterns)                 # 합계 배수 패턴 분석 추가
            ]
            
            logging.info(f"\n📊 총 {len(pattern_analyses) + 1}개 패턴 분석 진행:")
            
            for pattern_name, analysis_func in pattern_analyses:
                try:
                    logging.info(f"  - {pattern_name} 패턴 분석 중...")
                    patterns[pattern_name] = analysis_func(winning_numbers)
                    successful_patterns.append(pattern_name)
                except Exception as e:
                    logging.error(f"    ❌ {pattern_name} 패턴 분석 실패: {str(e)}")
                    patterns[pattern_name] = {}
                    failed_patterns.append(pattern_name)
            
            # 16. 분산도 패턴 분석
            try:
                logging.info("  - dispersion 패턴 분석 중...")
                patterns['dispersion'] = self._analyze_dispersion_patterns(winning_numbers)
                successful_patterns.append('dispersion')
            except Exception as e:
                logging.error(f"    ❌ dispersion 패턴 분석 실패: {str(e)}")
                patterns['dispersion'] = {}
                failed_patterns.append('dispersion')
            
            logging.info(f"\n📈 분석 결과 요약:")
            logging.info(f"  - 성공: {len(successful_patterns)}개")
            logging.info(f"  - 실패: {len(failed_patterns)}개")
            
            if failed_patterns:
                logging.info(f"  - 실패한 패턴: {', '.join(failed_patterns)}")

            if any(patterns.values()):
                # ============================================================
                # 🚀 PERFORMANCE OPTIMIZATION: 패턴 분석 결과 캐싱 (FIX CRITICAL-12: 크기 제한 적용)
                # ============================================================
                self._set_cached_patterns(data_hash, patterns)
                self._last_data_hash = data_hash
                cache_stats = self.get_cache_stats()
                logging.info(f"✅ 패턴 분석 결과 캐시 저장 (hash: {data_hash[:8]}..., 항목: {cache_stats['total_entries']}/{cache_stats['max_entries']})")

                self.db_manager.save_pattern_analysis(round_num, patterns)
                self._log_pattern_analysis(patterns)
                return True
            else:
                logging.error("모든 패턴 분석이 실패했습니다.")
                return False

        except Exception as e:
            logging.error(f"패턴 분석 중 오류 발생: {str(e)}")
            return False

    def _analyze_patterns(self):
        """모든 패턴 분석 실행"""
        try:
            patterns = {}
            
            # 1. 번호 일치 패턴
            patterns['match'] = self._analyze_match_patterns()
            # 2. 홀짝 패턴
            patterns['odd_even'] = self._analyze_odd_even_patterns()
            # 3-15. 기존 패턴들
            # ... 기존 패턴 분석 코드 ...
            
            # 16. 분산도 패턴 분석
            patterns['dispersion'] = self._analyze_dispersion_patterns(self.winning_numbers)
            
            return patterns
            
        except Exception as e:
            logging.error(f"패턴 분석 중 오류 발생: {str(e)}")
            return {}

    def _analyze_dispersion_patterns(self, winning_numbers):
        """분산도 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록(문자열 목록 또는 단일 문자열)
            
        Returns:
            Dict: 분산도 분석 결과
        """
        try:
            # 입력 유형 확인 및 처리
            all_results = []
            
            # 단일 문자열인 경우
            if isinstance(winning_numbers, str):
                try:
                    numbers = [int(n.strip()) for n in winning_numbers.split(',')]
                    result = self._calculate_single_dispersion(numbers)
                    all_results.append(result)
                except Exception as e:
                    logging.error(f"단일 문자열 분산도 계산 오류: {str(e)}")
                    return None
            
            # 리스트인 경우
            elif isinstance(winning_numbers, list):
                # 빈 리스트 체크
                if not winning_numbers:
                    logging.error("분석할 당첨 번호가 없습니다.")
                    return None
                    
                # 문자열 리스트(당첨 번호 목록)인 경우
                for numbers_str in winning_numbers:
                    try:
                        # 문자열인 경우 처리
                        if isinstance(numbers_str, str):
                            numbers = [int(n.strip()) for n in numbers_str.split(',')]
                        # 이미 정수 리스트인 경우 
                        elif isinstance(numbers_str, list) and all(isinstance(n, int) for n in numbers_str):
                            numbers = numbers_str
                        else:
                            logging.error(f"지원되지 않는 데이터 형식: {type(numbers_str)}")
                            continue
                            
                        result = self._calculate_single_dispersion(numbers)
                        all_results.append(result)
                    except Exception as e:
                        logging.error(f"리스트 항목 분산도 계산 오류: {str(e)}, 데이터: {numbers_str}")
                        continue
            else:
                logging.error(f"지원되지 않는 입력 타입: {type(winning_numbers)}")
                return None
            
            # 결과 종합
            if not all_results:
                logging.error("분산도 계산 결과가 없습니다.")
                return None
            
            # 결과 통계 계산
            return self._calculate_dispersion_statistics(all_results)
            
        except Exception as e:
            logging.error(f"분산도 계산 중 오류 발생: {str(e)}")
            return None
        
    def _calculate_single_dispersion(self, numbers):
        """단일 번호 조합의 분산도 계산
        
        Args:
            numbers: 정수 리스트
            
        Returns:
            Dict: 분산도 분석 결과
        """
        # 모든 입력이 정수인지 확인
        numbers = [int(n) if isinstance(n, str) else n for n in numbers]
        
        # 평균 계산
        mean = sum(numbers) / len(numbers)
        
        # 분산 계산
        variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
        
        # 표준편차 계산
        std_dev = variance ** 0.5
        
        # 최소/최대 간격 계산
        sorted_nums = sorted(numbers)
        gaps = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
        min_gap = min(gaps)
        max_gap = max(gaps)
        avg_gap = sum(gaps) / len(gaps)
        
        # 분산도 분류
        low_threshold = 10
        high_threshold = 15
        
        if std_dev < low_threshold:
            category = "low"
        elif std_dev > high_threshold:
            category = "high"
        else:
            category = "medium"
        
        return {
            'variance': variance,
            'std_dev': std_dev,
            'min_gap': min_gap,
            'max_gap': max_gap,
            'avg_gap': avg_gap,
            'category': category
        }
        
    def _calculate_dispersion_statistics(self, all_results):
        """분산도 통계 계산
        
        Args:
            all_results: 분산도 계산 결과 목록
            
        Returns:
            Dict: 통합된 분산도 분석 결과
        """
        total = len(all_results)
        
        # 카테고리별 통계
        categories = {'low': 0, 'medium': 0, 'high': 0}
        for result in all_results:
            categories[result['category']] += 1
        
        # 백분율 계산
        patterns = {k: (v / total * 100) for k, v in categories.items()}
        
        # 평균값 계산
        avg_variance = sum(r['variance'] for r in all_results) / total
        avg_std_dev = sum(r['std_dev'] for r in all_results) / total
        avg_min_gap = sum(r['min_gap'] for r in all_results) / total
        avg_max_gap = sum(r['max_gap'] for r in all_results) / total
        avg_gap = sum(r['avg_gap'] for r in all_results) / total
        
        return {
            'avg_variance': avg_variance,
            'avg_std_dev': avg_std_dev,
            'avg_min_gap': avg_min_gap,
            'avg_max_gap': avg_max_gap,
            'avg_gap': avg_gap,
            'patterns': patterns
        }

    def _log_patterns(self, patterns):
        """패턴 분석 결과 로깅"""
        try:
            # 기존 패턴 로깅 (1-15)
            # ... 기존 패턴 로깅 코드 ...
            
            # 16. 분산도 패턴 출력
            if 'dispersion' in patterns:
                logging.info("\n16. 분산도 패턴 분석 결과:")
                dispersion = patterns['dispersion']
                if dispersion and 'patterns' in dispersion:
                    logging.info("    번호들의 분산도 분포")
                    logging.info(f"    * 낮은 분산도 (집중형): {dispersion['patterns']['low']:.2f}%")
                    logging.info(f"    * 중간 분산도 (균형형): {dispersion['patterns']['medium']:.2f}%")
                    logging.info(f"    * 높은 분산도 (분산형): {dispersion['patterns']['high']:.2f}%")
                    
        except Exception as e:
            logging.error(f"패턴 로깅 중 오류 발생: {str(e)}")

    def _analyze_match_patterns(self, winning_numbers: List[str]) -> Dict[int, float]:
        """당첨 번호 간 일치 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[int, float]: 일치하는 번호 개수별 비율
        """
        match_counts = {i: 0 for i in range(7)}
        total = len(winning_numbers)
        
        for i, numbers_str in enumerate(winning_numbers):
            numbers_set = set(map(int, numbers_str.split(',')))
            for j, other_str in enumerate(winning_numbers):
                if i != j:
                    other_set = set(map(int, other_str.split(',')))
                    match_count = len(numbers_set.intersection(other_set))
                    match_counts[match_count] += 1
        
        total_comparisons = total * (total - 1)
        return {k: (v / total_comparisons * 100) for k, v in match_counts.items()}

    def _analyze_odd_even_patterns(self, winning_numbers: List[str]) -> Dict[str, Dict[int, float]]:
        """홀짝 패턴 분석 - 홀수와 짝수 모두 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, Dict[int, float]]: 홀수/짝수 개수별 비율
        """
        try:
            total = len(winning_numbers)
            stats = {
                'odd': {i: 0 for i in range(1, 7)},   # 홀수 1~6개
                'even': {i: 0 for i in range(1, 7)}   # 짝수 1~6개
            }
            
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                odd_count = sum(1 for num in numbers if num % 2 == 1)
                even_count = 6 - odd_count  # 전체 6개에서 홀수 개수를 뺀 값
                
                if odd_count > 0:   # 홀수가 1개 이상인 경우만
                    stats['odd'][odd_count] += 1
                if even_count > 0:  # 짝수가 1개 이상인 경우만
                    stats['even'][even_count] += 1
                    
            # 백분율 계산
            result = {
                'odd': {k: (v / total * 100) for k, v in stats['odd'].items() if v > 0},
                'even': {k: (v / total * 100) for k, v in stats['even'].items() if v > 0}
            }
            
            return result
                
        except Exception as e:
            logging.error(f"홀짝 패턴 분석 중 오류 발생: {str(e)}")
            return {}

    def _analyze_consecutive_patterns(self, winning_numbers: List[str]) -> Dict[int, float]:
        """연속 번호 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[int, float]: 연속 번호 개수별 비율
        """
        consecutive_counts = {i: 0 for i in range(1, 7)}
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = sorted(map(int, numbers_str.split(',')))
            max_consecutive = 1
            current_consecutive = 1
            
            for i in range(1, len(numbers)):
                if numbers[i] == numbers[i-1] + 1:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 1
                    
            consecutive_counts[max_consecutive] += 1
            
        return {k: (v / total * 100) for k, v in consecutive_counts.items()}

    def _analyze_sum_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """번호 합계 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, float]: 합계 범위별 비율
        """
        sums = []
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            sums.append(sum(numbers))
            
        min_sum = min(sums)
        max_sum = max(sums)
        interval = (max_sum - min_sum) / 20  # 20개 구간으로 나눔
        
        ranges = {i: 0 for i in range(20)}
        total = len(winning_numbers)
        
        for sum_val in sums:
            range_idx = min(19, int((sum_val - min_sum) / interval))
            ranges[range_idx] += 1
            
        return {
            f"구간 {min_sum + interval*k:.1f}~{min_sum + interval*(k+1):.1f}": 
            (v / total * 100) 
            for k, v in ranges.items()
        }  

    def get_latest_patterns(self) -> Optional[Dict]:
        """최신 패턴 분석 결과 조회"""
        return self.db_manager.get_latest_pattern_analysis()

    def get_pattern_history(self, pattern_type: str) -> Optional[List[Dict]]:
        """특정 패턴의 이력 조회
        
        Args:
            pattern_type: 'number_match', 'odd_even', 'consecutive', 'sum_range' 중 하나
            
        Returns:
            Optional[List[Dict]]: 패턴 이력 또는 None
        """
        return self.db_manager.get_pattern_history(pattern_type)
    
    def _analyze_fixed_step_patterns(self, winning_numbers: List[str]) -> Dict[str, Dict[str, float]]:
        """고정 간격 패턴 분석 개선 버전
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, Dict[str, float]]: 패턴 유형별 분포
        """
        if not winning_numbers:
            return {}
            
        pattern_stats = {
            'all_steps': defaultdict(int),      # 6개 모두 동일 간격
            'partial_steps': defaultdict(int),   # 5개 연속 동일 간격
            'four_steps': defaultdict(int),      # 4개 연속 동일 간격
            'three_steps': defaultdict(int)      # 3개 연속 동일 간격
        }
        
        total = len(winning_numbers)
        result = {}  # result 변수를 try 블록 밖에서 초기화
        
        def _find_step_patterns(numbers: List[int], step: int) -> List[List[int]]:
            """모든 가능한 시작점에서 패턴 찾기"""
            patterns = []
            n = len(numbers)
            
            for i in range(n-1):
                current_pattern = [numbers[i]]
                last_num = numbers[i]
                
                for j in range(i+1, n):
                    if numbers[j] - last_num == step:
                        current_pattern.append(numbers[j])
                        last_num = numbers[j]
                        
                        if len(current_pattern) >= 3:
                            patterns.append(current_pattern.copy())
            
            return patterns

        try:
            # 각 당첨 번호에 대해 패턴 분석
            for numbers_str in winning_numbers:
                numbers = sorted(list(map(int, numbers_str.split(','))))
                
                # 각 간격에 대해 패턴 검사
                for step in range(2, 9):  # 2~8 간격 검사
                    patterns = _find_step_patterns(numbers, step)
                    
                    # 발견된 패턴 분류
                    for pattern in patterns:
                        pattern_len = len(pattern)
                        if pattern_len == 6:
                            pattern_stats['all_steps'][f"{step}간격"] += 1
                        elif pattern_len == 5:
                            pattern_stats['partial_steps'][f"{step}간격"] += 1
                        elif pattern_len == 4:
                            pattern_stats['four_steps'][f"{step}간격"] += 1
                        elif pattern_len == 3:
                            pattern_stats['three_steps'][f"{step}간격"] += 1

            # 백분율 계산 및 결과 정리
            for pattern_type, stats in pattern_stats.items():
                temp_dict = {}
                
                # 모든 간격에 대해 결과 저장 (0% 포함)
                for step in range(2, 9):
                    key = f"{step}간격"
                    if key in stats:
                        temp_dict[key] = (stats[key] / total * 100)
                    else:
                        temp_dict[key] = 0.0
                        
                result[pattern_type] = temp_dict

        except Exception as e:
            logging.error(f"고정 간격 패턴 분석 중 오류 발생: {str(e)}")
            return {}
            
        return result

    def _analyze_last_digit_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """끝자리 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, float]: 동일 끝자리 숫자 개수별 비율
        """
        last_digit_counts = {i: 0 for i in range(1, 7)}  # 1개부터 6개까지 초기화
        total = len(winning_numbers)
        
        for comb_str in winning_numbers:
            numbers = list(map(int, comb_str.split(',')))
            last_digits = [num % 10 for num in numbers]
            digit_freq = defaultdict(int)
            
            # 각 끝자리 숫자의 빈도 계산
            for digit in last_digits:
                digit_freq[digit] += 1
            
            # 가장 많이 나온 끝자리의 빈도 저장
            max_same = max(digit_freq.values())
            last_digit_counts[max_same] += 1
        
        # 백분율 계산 (모든 경우에 대해)
        return {
            f"{count}_same_last_digits": (value / total * 100)
            for count, value in last_digit_counts.items()
        }
        
    def _log_pattern_analysis(self, patterns: Dict) -> None:
        """패턴 분석 결과 출력"""
        logging.info("\n1. 번호 일치 패턴 분포:")
        # FIX: 'number_match' → 'match' (패턴 저장 키와 일치)
        for k, v in patterns['match'].items():
            logging.info(f"   {k}개 일치: {v:.2f}%")
            
        logging.info("\n2. 홀짝 분포:")
        if 'odd_even' in patterns:
            odd_even_stats = patterns['odd_even']
            
            # 홀수 분포 출력
            logging.info("\n   [홀수 분포]")
            for count, ratio in sorted(odd_even_stats.get('odd', {}).items()):
                if count > 0:  # 1개 이상만 출력
                    logging.info(f"   - {count}개: {ratio:.2f}%")
            
            # 짝수 분포 출력
            logging.info("\n   [짝수 분포]")
            for count, ratio in sorted(odd_even_stats.get('even', {}).items()):
                if count > 0:  # 1개 이상만 출력
                    logging.info(f"   - {count}개: {ratio:.2f}%")
                    
            # 가장 많이 나온 패턴 표시
            odd_max = max(odd_even_stats.get('odd', {}).items(), key=lambda x: x[1], default=(0, 0))
            even_max = max(odd_even_stats.get('even', {}).items(), key=lambda x: x[1], default=(0, 0))
            
            logging.info("\n   [분석 결과]")
            logging.info(f"   - 가장 많은 홀수 패턴: {odd_max[0]}개 ({odd_max[1]:.2f}%)")
            logging.info(f"   - 가장 많은 짝수 패턴: {even_max[0]}개 ({even_max[1]:.2f}%)")            
            
        logging.info("\n3. 연속 번호 패턴:")
        for k, v in patterns['consecutive'].items():
            logging.info(f"   {k}개 연속: {v:.2f}%")
            
        logging.info("\n4. 번호 합계 분포:")
        for range_str, v in patterns['sum_range'].items():
            logging.info(f"   {range_str}: {v:.2f}%")
        
        logging.info("\n5. 고정 간격 패턴 분포:")
        pattern_types = {
            'all_steps': '6개 모두',
            'partial_steps': '5개 연속',
            'four_steps': '4개 연속',
            'three_steps': '3개 연속'
        }
        
        for pattern_key, pattern_name in pattern_types.items():
            logging.info(f"   [{pattern_name} 고정 간격]")
            pattern_data = patterns['fixed_step'].get(pattern_key, {})
            
            for step in range(2, 9):
                key = f"{step}간격"
                value = pattern_data.get(key, 0.0)
                examples = [
                    f"{i},{i+step},{i+2*step},{i+3*step},{i+4*step},{i+5*step}"
                    for i in range(1, min(6, 46-5*step))
                ][:3]
                example_str = " 또는 ".join(examples) + "..."
                logging.info(f"   {key}: {value:.4f}% (예: {example_str})")      
                
        logging.info("\n6. 끝자리 패턴 분포:")
        if patterns['last_digit']:
            for i in range(1, 7):
                key = f"{i}_same_last_digits"
                value = patterns['last_digit'].get(key, 0)
                logging.info(f"   {i}개 동일 끝자리: {value:.2f}%")
        else:
            logging.info("   끝자리 패턴 분석에 실패했습니다.")

        logging.info("\n7. 최대 간격 패턴 분포:")
        if patterns.get('max_gap'):
            sorted_gaps = sorted(
                [(int(k.split('_')[1]), v) for k, v in patterns['max_gap'].items()],
                key=lambda x: x[0]
            )
            for gap, percentage in sorted_gaps:
                logging.info(f"   간격 {gap}칸: {percentage:.2f}%")
        else:
            logging.info("   최대 간격 패턴 분석에 실패했습니다.")
        
        logging.info("\n8. 구간별 번호 분포:")
        if patterns.get('section_distribution'):
            for section, counts in patterns['section_distribution'].items():
                section_name = {
                    'section1': '1-15 구간',
                    'section2': '16-30 구간',
                    'section3': '31-45 구간'
                }.get(section, section)
                logging.info(f"   [{section_name}]")
                for count, percentage in counts.items():
                    logging.info(f"   {count}개 번호: {percentage:.2f}%")
        else:
            logging.info("   구간별 분포 패턴 분석에 실패했습니다.")
        
        logging.info("\n9. 번호 평균값 분포:")
        if patterns.get('number_average'):
            for range_str, percentage in patterns['number_average'].items():
                logging.info(f"   {range_str}: {percentage:.2f}%")
        else:
            logging.info("   평균값 패턴 분석에 실패했습니다.")            

        logging.info("\n10. 배수 패턴 분포:")
        if patterns.get('multiple_patterns'):
            for base, counts in patterns['multiple_patterns'].items():
                logging.info(f"   [{base}의 배수]")
                for count, percentage in counts.items():
                    logging.info(f"   {count}개: {percentage:.2f}%")
        else:
            logging.info("   배수 패턴 분석에 실패했습니다.")

        # 11. 10구간 분석 결과 추가
        logging.info("\n11. 10구간 분석 결과:")
        if patterns.get('ten_section'):
            sections = {
                'section_1': '[구간 1-10]',
                'section_2': '[구간 11-20]',
                'section_3': '[구간 21-30]',
                'section_4': '[구간 31-40]',
                'section_5': '[구간 41-45]'
            }
            for section, name in sections.items():
                data = patterns['ten_section'].get(section, {})
                logging.info(f"   {name}")
                total_numbers = sum(count * pct/100 for count, pct in data.items())
                max_pattern = max(data.items(), key=lambda x: x[1], default=(0, 0))
                logging.info(f"   * 평균 출현 개수: {total_numbers:.2f}개")
                logging.info(f"   * 가장 많이 나온 패턴: {max_pattern[0]}개 ({max_pattern[1]:.2f}%)")
                logging.info("   * 상세 분포:")
                for count in range(7):
                    if count in data:
                        logging.info(f"   - {count}개: {data[count]:.2f}%")

        # 12. 등차수열 패턴 결과 추가
        logging.info("\n12. 등차수열 패턴 분석 결과:")
        if patterns.get('arithmetic_sequence'):
            logging.info("   연속된 숫자의 차이가 일정한 패턴")
            for length in range(3, 7):
                percentage = patterns['arithmetic_sequence'].get(length, 0.0)
                logging.info(f"   * {length}개 연속 등차수열: {percentage:.2f}%")
                if length == 3:
                    logging.info("   - 예시: 2,12,22 또는 5,15,25")
                elif length == 4:
                    logging.info("   - 예시: 1,11,21,31 또는 5,15,25,35")
                elif length == 5:
                    logging.info("   - 예시: 3,9,15,21,27 또는 2,12,22,32,42")
                elif length == 6:
                    logging.info("   - 예시: 2,7,12,17,22,27 또는 1,10,19,28,37")

        # 13. 등비수열 패턴 분석 결과 추가
        logging.info("\n13. 등비수열 패턴 분석 결과:")
        if patterns.get('geometric_sequence'):
            logging.info("   연속된 숫자의 비율이 일정한 패턴")
            for length in range(3, 7):
                percentage = patterns['geometric_sequence'].get(length, 0.0)
                logging.info(f"   * {length}개 연속 등비수열: {percentage:.2f}%")
                if length == 3:
                    logging.info("   - 예시: 2,4,8 또는 3,9,27")
                elif length == 4:
                    logging.info("   - 예시: 2,4,8,16 또는 3,9,27")
                elif length == 5:
                    logging.info("   - 예시: 1,2,4,8,16 또는 2,6,18")
                elif length == 6:
                    logging.info("   - 예시: 1,2,4,8,16,32 또는 1,3,9,27")
                    
        # 14. 홀짝 교차 패턴 결과 추가
        logging.info("\n14. 홀짝 교차 패턴 분석 결과:")
        if patterns.get('alternating_odd_even'):
            logging.info("   홀수와 짝수가 교대로 나타나는 패턴")
            pattern_names = {
                'perfect_alternating': '완벽한 교차',
                'one_break': '1번 깨짐',
                'two_breaks': '2번 깨짐',
                'three_or_more_breaks': '3번 이상 깨짐'
            }
            for pattern, name in pattern_names.items():
                percentage = patterns['alternating_odd_even'].get(pattern, 0.0)
                logging.info(f"   * {name}: {percentage:.2f}%")
            
            # 예시 추가
            logging.info("   - 완벽한 교차 예시: 2,3,4,5,8,9 (짝-홀-짝-홀-짝-홀)")
            logging.info("   - 1번 깨짐 예시: 3,4,5,6,7,10 (홀-짝-홀-짝-홀-짝에서 5,6이 패턴을 깸)")
        else:
            logging.info("   홀짝 교차 패턴 분석에 실패했습니다.")
            
        # 15. 합계 배수 패턴 결과 추가
        logging.info("\n15. 합계 배수 패턴 분석 결과:")
        if patterns.get('sum_multiple'):
            logging.info("   당첨 번호 합계가 특정 수의 배수인 패턴")
            
            # 배수별 비율 정렬해서 출력
            sorted_multiples = sorted(
                [(int(key.split('_')[-1]), val) for key, val in patterns['sum_multiple'].items()],
                key=lambda x: x[0]
            )
            
            for base, percentage in sorted_multiples:
                logging.info(f"   * {base}의 배수: {percentage:.2f}%")
                
            # 가장 빈도가 높은 배수 찾기
            if sorted_multiples:
                max_multiple = max(sorted_multiples, key=lambda x: x[1])
                logging.info(f"   * 가장 많이 나타난 배수: {max_multiple[0]}의 배수 ({max_multiple[1]:.2f}%)")
        else:
            logging.info("   합계 배수 패턴 분석에 실패했습니다.")

        # 16. 분산도 패턴 분석 결과 추가
        logging.info("\n16. 분산도 패턴 분석 결과:")
        if patterns.get('dispersion'):
            logging.info("   번호들의 분산도 분포")
            if 'patterns' in patterns['dispersion']:
                dispersion_patterns = patterns['dispersion']['patterns']
                logging.info(f"   * 낮은 분산도 (집중형): {dispersion_patterns.get('low', 0):.2f}%")
                logging.info(f"   * 중간 분산도 (균형형): {dispersion_patterns.get('medium', 0):.2f}%")
                logging.info(f"   * 높은 분산도 (분산형): {dispersion_patterns.get('high', 0):.2f}%")
            
            # 평균 분산도 통계 출력
            if 'avg_std_dev' in patterns['dispersion']:
                logging.info(f"   * 평균 표준편차: {patterns['dispersion']['avg_std_dev']:.2f}")
                logging.info(f"   * 평균 분산: {patterns['dispersion']['avg_variance']:.2f}")
                logging.info(f"   * 평균 최소 간격: {patterns['dispersion']['avg_min_gap']:.2f}")
                logging.info(f"   * 평균 최대 간격: {patterns['dispersion']['avg_max_gap']:.2f}")
        else:
            logging.info("   분산도 패턴 분석에 실패했습니다.")

    def _analyze_max_gap_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """최대 간격 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, float]: 간격별 출현 비율 (20-40까지 모두 포함)
        """
        try:
            # 20부터 40까지의 간격에 대한 카운트 초기화
            gap_counts = {i: 0 for i in range(20, 41)}
            total = len(winning_numbers)
            
            for numbers_str in winning_numbers:
                numbers = sorted(list(map(int, numbers_str.split(','))))
                diffs = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
                max_gap = max(diffs)
                if max_gap >= 20:  # 20 이상의 간격만 카운트
                    gap_counts[max_gap] = gap_counts.get(max_gap, 0) + 1
            
            # 무조건 20-40까지 모든 간격의 비율 계산
            result = {
                f'gap_{gap}': (gap_counts[gap] / total * 100)
                for gap in range(20, 41)
            }
            
            return result
                
        except Exception as e:
            logging.error(f"최대 간격 패턴 분석 중 오류 발생: {str(e)}")
            return {}
    
    def _analyze_section_patterns(self, winning_numbers: List[str]) -> Dict[str, Dict[int, float]]:
        """구간별 번호 분포 패턴 분석"""
        section_counts = {
            'section1': {i: 0 for i in range(7)},  # 1-15
            'section2': {i: 0 for i in range(7)},  # 16-30
            'section3': {i: 0 for i in range(7)}   # 31-45
        }
        total = len(winning_numbers)
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            
            # 각 구간별 번호 개수 계산
            counts = {
                'section1': sum(1 for n in numbers if 1 <= n <= 15),
                'section2': sum(1 for n in numbers if 16 <= n <= 30),
                'section3': sum(1 for n in numbers if 31 <= n <= 45)
            }
            
            for section, count in counts.items():
                section_counts[section][count] += 1
        
        # 백분율 계산
        return {
            section: {
                count: (freq / total * 100)
                for count, freq in section_counts[section].items()
            }
            for section, counts in section_counts.items()
        }

    def _analyze_average_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """당첨 번호의 평균값 분포 분석"""
        averages = []
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            averages.append(sum(numbers) / len(numbers))
        
        # 최소/최대 평균값 확인
        min_avg = min(averages)
        max_avg = max(averages)
        interval = (max_avg - min_avg) / 10  # 10개 구간으로 나눔
        
        # 구간별 분포 계산
        ranges = {i: 0 for i in range(10)}
        total = len(winning_numbers)
        
        for avg in averages:
            range_idx = min(9, int((avg - min_avg) / interval))
            ranges[range_idx] += 1
        
        return {
            f"구간 {min_avg + interval*k:.1f}~{min_avg + interval*(k+1):.1f}": 
            (v / total * 100) 
            for k, v in ranges.items()
        }

    def _analyze_multiple_patterns(self, winning_numbers: List[str]) -> Dict[int, Dict[int, float]]:
        """배수 패턴 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict: 배수별 출현 빈도
        """
        try:
            multiples = {2: {}, 3: {}, 4: {}, 5: {}}  # 각 배수별 통계
            total = len(winning_numbers)
            
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                
                # 각 배수별로 개수 카운트
                for base in multiples.keys():
                    count = sum(1 for n in numbers if n % base == 0)
                    multiples[base][count] = multiples[base].get(count, 0) + 1
            
            # 백분율 계산
            for base in multiples:
                multiples[base] = {
                    count: (freq / total * 100)
                    for count, freq in multiples[base].items()
                }
                
            return multiples
            
        except Exception as e:
            logging.error(f"배수 패턴 분석 중 오류 발생: {str(e)}")
            return {}

    # 신규: 10구간 분석
    def _analyze_ten_section_patterns(self, winning_numbers: List[str]) -> Dict[str, Dict[int, float]]:
        """10개 구간별 번호 분포 분석"""
        section_counts = {
            f"section_{i}": {j: 0 for j in range(7)}  
            for i in range(1, 6)  # 5개 구간 (1-10, 11-20, 21-30, 31-40, 41-45)
        }
        total = len(winning_numbers)
        
        sections = [
            (1, 10), (11, 20), (21, 30), (31, 40), (41, 45)
        ]
        
        for numbers_str in winning_numbers:
            numbers = list(map(int, numbers_str.split(',')))
            
            for i, (start, end) in enumerate(sections, 1):
                count = sum(1 for n in numbers if start <= n <= end)
                section_counts[f"section_{i}"][count] += 1
        
        # 백분율 계산
        return {
            section: {
                count: (freq / total * 100)
                for count, freq in section_counts[section].items()
            }
            for section, counts in section_counts.items()
        }

    # 신규: 등차수열 분석
    def _analyze_arithmetic_sequence(self, winning_numbers: List[str]) -> Dict[int, float]:
        """등차수열 패턴 분석"""
        sequence_counts = {i: 0 for i in range(3, 7)}  # 3개부터 6개까지
        total = len(winning_numbers)

        for numbers_str in winning_numbers:
            numbers = sorted(list(map(int, numbers_str.split(','))))
            max_sequence = self._find_max_arithmetic_sequence(numbers)
            if max_sequence >= 3:
                sequence_counts[max_sequence] += 1

        return {
            length: (count / total * 100)
            for length, count in sequence_counts.items()
        }

    def _find_max_arithmetic_sequence(self, numbers: List[int]) -> int:
        """가장 긴 등차수열의 길이 찾기"""
        n = len(numbers)
        max_length = 2

        for i in range(n-2):
            for j in range(i+1, n-1):
                d = numbers[j] - numbers[i]
                current_length = 2
                last = numbers[j]
                
                for k in range(j+1, n):
                    if numbers[k] - last == d:
                        current_length += 1
                        last = numbers[k]
                
                max_length = max(max_length, current_length)

        return max_length if max_length >= 3 else 0

    # 신규: 등비수열 분석
    def _analyze_geometric_sequence(self, winning_numbers: List[str]) -> Dict[int, float]:
        """등비수열 패턴 분석"""
        sequence_counts = {i: 0 for i in range(3, 7)}  # 3개부터 6개까지
        total = len(winning_numbers)

        for numbers_str in winning_numbers:
            numbers = sorted(list(map(int, numbers_str.split(','))))
            max_sequence = self._find_max_geometric_sequence(numbers)
            if max_sequence >= 3:
                sequence_counts[max_sequence] += 1

        return {
            length: (count / total * 100)
            for length, count in sequence_counts.items()
        }

    def _find_max_geometric_sequence(self, numbers: List[int]) -> int:
        """가장 긴 등비수열의 길이 찾기

        FIX: 부동소수점 비교 및 Division by Zero 문제 수정
        """
        n = len(numbers)
        max_length = 2
        EPSILON = 1e-9  # 부동소수점 비교 허용 오차

        for i in range(n-2):
            for j in range(i+1, n-1):
                if numbers[j] == 0 or numbers[i] == 0: continue  # 0으로는 나눌 수 없음
                ratio = numbers[j] / numbers[i]
                # FIX: 부동소수점 비교에 허용 오차 적용
                if abs(ratio - 1.0) < EPSILON: continue  # 비율이 1이면 동일한 수

                current_length = 2
                last = numbers[j]

                for k in range(j+1, n):
                    # FIX: last가 0인 경우 Division by Zero 방지 및 부동소수점 비교
                    if last != 0 and abs(numbers[k] / last - ratio) < EPSILON:
                        current_length += 1
                        last = numbers[k]

                max_length = max(max_length, current_length)

        return max_length if max_length >= 3 else 0

    # 추가: 홀짝 교차 패턴 분석
    def _analyze_alternating_odd_even_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """홀짝 교차 패턴 분석 - 홀짝이 교대로 나오는 패턴
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, float]: 홀짝 교차 패턴의 빈도 비율
        """
        try:
            total = len(winning_numbers)
            alternating_counts = {
                'perfect_alternating': 0,  # 완벽하게 홀짝 교차
                'one_break': 0,            # 한 번 깨짐
                'two_breaks': 0,           # 두 번 깨짐
                'three_or_more_breaks': 0  # 세 번 이상 깨짐
            }
            
            for numbers_str in winning_numbers:
                numbers = sorted(map(int, numbers_str.split(',')))
                
                # 홀짝 교차 패턴 체크
                breaks = 0
                for i in range(1, len(numbers)):
                    current_parity = numbers[i] % 2
                    prev_parity = numbers[i-1] % 2
                    if current_parity == prev_parity:
                        breaks += 1
                
                if breaks == 0:
                    alternating_counts['perfect_alternating'] += 1
                elif breaks == 1:
                    alternating_counts['one_break'] += 1
                elif breaks == 2:
                    alternating_counts['two_breaks'] += 1
                else:
                    alternating_counts['three_or_more_breaks'] += 1
                    
            # 백분율 계산
            result = {
                k: (v / total * 100) for k, v in alternating_counts.items()
            }
            
            return result
                
        except Exception as e:
            logging.error(f"홀짝 교차 패턴 분석 중 오류 발생: {str(e)}")
            return {}

    # 추가: 합계 배수 패턴 분석
    def _analyze_sum_multiple_patterns(self, winning_numbers: List[str]) -> Dict[str, float]:
        """합계 배수 패턴 분석 - 당첨 번호 합이 특정 수의 배수인지 분석
        
        Args:
            winning_numbers: 당첨 번호 목록
            
        Returns:
            Dict[str, float]: 합계가 각 배수인 경우의 비율
        """
        try:
            total = len(winning_numbers)
            multiples = {i: 0 for i in range(1, 11)}  # 1~10의 배수
            
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                numbers_sum = sum(numbers)
                
                # 각 배수별로 체크
                for base in multiples.keys():
                    if numbers_sum % base == 0:
                        multiples[base] += 1
            
            # 백분율 계산
            result = {
                f"multiple_of_{base}": (count / total * 100)
                for base, count in multiples.items()
            }
            
            return result
                
        except Exception as e:
            logging.error(f"합계 배수 패턴 분석 중 오류 발생: {str(e)}")
            return {}