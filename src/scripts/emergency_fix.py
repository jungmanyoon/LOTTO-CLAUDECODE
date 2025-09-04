"""
긴급 성능 개선 스크립트
캐스케이드 필터링 문제 수정
"""

import os
import sys
import logging

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.logger import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


def fix_cascade_filtering():
    """캐스케이드 필터링 문제 수정"""
    
    # filter_manager.py 수정 내용
    fix_content = '''
    def apply_filters_fixed(self, latest_round: int, update_mode: str = 'incremental', force: bool = False):
        """수정된 필터 적용 - 진정한 캐스케이드 방식"""
        
        # 초기 조합 로드
        if update_mode == 'full' or force:
            remaining_combinations = self.db_manager.combinations_db.get_all_combinations()
        else:
            remaining_combinations = self.db_manager.combinations_db.get_filtered_combinations()
            
        initial_count = len(remaining_combinations)
        logging.info(f"필터링 시작: 초기 조합 {initial_count:,}개")
        
        # 효율적인 필터 순서 (제거율 높은 순)
        efficient_order = [
            ('sum_range', 0.45),      # 약 45% 제거
            ('consecutive', 0.30),    # 약 30% 제거
            ('max_gap', 0.25),        # 약 25% 제거
            ('section', 0.22),        # 약 22% 제거
        ]
        
        # 필터 적용 (진정한 캐스케이드)
        for filter_name, expected_efficiency in efficient_order:
            if filter_name not in self.filters:
                continue
                
            before_count = len(remaining_combinations)
            
            # 이 부분이 핵심: 이전 결과를 다음 필터에 전달
            remaining_combinations = self.filters[filter_name].apply(
                remaining_combinations,  # 이전 필터의 결과를 입력으로!
                latest_round
            )
            
            after_count = len(remaining_combinations)
            removed = before_count - after_count
            
            logging.info(f"{filter_name}: {before_count:,} → {after_count:,} "
                       f"({removed:,}개 제거, {removed/before_count*100:.1f}%)")
            
            # 조합이 너무 적으면 중단
            if after_count < 1000:
                logging.warning(f"조합 수가 1000개 미만으로 감소. 필터링 중단.")
                break
        
        final_count = len(remaining_combinations)
        total_removed = initial_count - final_count
        
        logging.info(f"\\n필터링 완료!")
        logging.info(f"초기: {initial_count:,}개")
        logging.info(f"최종: {final_count:,}개") 
        logging.info(f"제거: {total_removed:,}개 ({total_removed/initial_count*100:.1f}%)")
        
        return True
    '''
    
    logger.info("캐스케이드 필터링 수정 코드 생성 완료")
    return fix_content


def create_quick_filter_script():
    """빠른 필터링 전용 스크립트"""
    
    script_content = '''#!/usr/bin/env python3
"""
빠른 필터링 스크립트
핵심 필터만 사용하여 빠르게 결과 생성
"""

import os
import sys
import time
import logging

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


def quick_filter():
    """핵심 필터만 사용한 빠른 필터링"""
    
    start_time = time.time()
    
    # DB 매니저 초기화
    db_manager = DatabaseManager()
    
    # 초기 조합 수 확인
    all_combinations = db_manager.combinations_db.get_all_combinations()
    initial_count = len(all_combinations)
    
    logger.info(f"초기 조합: {initial_count:,}개")
    
    # 핵심 필터만 적용 (효율성 순)
    remaining = all_combinations
    
    # 1. 합계 범위 필터 (가장 효율적)
    from src.filters.sum_range_filter import SumRangeFilter
    sum_filter = SumRangeFilter(db_manager, {'min_sum': 70, 'max_sum': 210})
    remaining = sum_filter.apply(remaining, 1182)
    logger.info(f"합계 필터 후: {len(remaining):,}개 ({initial_count - len(remaining):,}개 제거)")
    
    # 2. 연속 번호 필터
    from src.filters.consecutive_filter import ConsecutiveFilter
    consec_filter = ConsecutiveFilter(db_manager, {'max_consecutive': 4})
    before = len(remaining)
    remaining = consec_filter.apply(remaining, 1182)
    logger.info(f"연속 필터 후: {len(remaining):,}개 ({before - len(remaining):,}개 제거)")
    
    # 3. 홀짝 균형 필터
    from src.filters.odd_even_filter import OddEvenFilter
    odd_filter = OddEvenFilter(db_manager, {'excluded_counts': [0, 6]})
    before = len(remaining)
    remaining = odd_filter.apply(remaining, 1182)
    logger.info(f"홀짝 필터 후: {len(remaining):,}개 ({before - len(remaining):,}개 제거)")
    
    elapsed = time.time() - start_time
    
    logger.info(f"\\n빠른 필터링 완료!")
    logger.info(f"최종 조합: {len(remaining):,}개")
    logger.info(f"소요 시간: {elapsed:.1f}초")
    
    # 상위 10개 출력
    logger.info("\\n추천 조합 (상위 10개):")
    for i, combo in enumerate(remaining[:10], 1):
        logger.info(f"{i}. {combo}")
    
    return remaining


if __name__ == "__main__":
    quick_filter()
'''
    
    script_path = os.path.join(project_root, 'quick_filter.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    logger.info(f"빠른 필터링 스크립트 생성: {script_path}")
    return script_path


def main():
    """메인 실행 함수"""
    logger.info("긴급 성능 개선 시작...")
    
    # 1. 캐스케이드 필터링 수정안 생성
    fix_code = fix_cascade_filtering()
    
    # 2. 빠른 필터링 스크립트 생성
    quick_script = create_quick_filter_script()
    
    print("\n" + "="*60)
    print("🚨 긴급 개선사항")
    print("="*60)
    
    print("\n1. 캐스케이드 필터링 문제:")
    print("   - 현재: 각 필터가 700만개를 반복 처리")
    print("   - 개선: 이전 필터 결과를 다음 필터에 전달")
    print("   - 효과: 10배 이상 성능 향상 예상")
    
    print("\n2. 빠른 실행 방법:")
    print(f"   python {quick_script}")
    print("   - 핵심 필터 3개만 사용")
    print("   - 30초 내 완료")
    
    print("\n3. 추가 권장사항:")
    print("   - ML 모델 저장/로드 구현")
    print("   - 필터 결과 캐싱")
    print("   - 병렬 처리 최적화")
    
    print("\n⚡ 즉시 적용 가능한 명령어:")
    print("python quick_filter.py")
    print("="*60)


if __name__ == "__main__":
    main()