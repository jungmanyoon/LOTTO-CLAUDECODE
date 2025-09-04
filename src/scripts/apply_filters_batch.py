#!/usr/bin/env python3
"""
전체 814만개 조합을 배치로 필터링하는 스크립트
메모리 효율적으로 처리하고 진행 상황을 표시
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
import logging
import time
import psutil
from tqdm import tqdm

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('batch_filtering.log', encoding='utf-8')
    ]
)

def apply_filters_in_batches():
    """배치 단위로 필터 적용"""
    
    print("=" * 80)
    print("전체 조합 필터링 시작")
    print("=" * 80)
    
    # 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    
    # 전체 조합 수 확인
    with db_manager.combinations_db._create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM base_combinations")
        total_count = cursor.fetchone()[0]
    
    print(f"\n전체 조합 수: {total_count:,}개")
    
    # 활성화된 필터 확인
    enabled_filters = []
    for name, filter_obj in filter_manager.filters.items():
        if filter_obj.criteria.get('enabled', True):
            enabled_filters.append(name)
    
    print(f"활성 필터: {len(enabled_filters)}개")
    print(f"필터 목록: {enabled_filters}")
    
    # 배치 크기 설정 (메모리 고려)
    batch_size = 100000  # 10만개씩 처리
    num_batches = (total_count + batch_size - 1) // batch_size
    
    print(f"\n배치 크기: {batch_size:,}개")
    print(f"배치 수: {num_batches}개")
    
    # 전체 통계 초기화
    total_processed = 0
    total_passed = 0
    all_filtered_combinations = []
    
    # 시작 시간
    start_time = time.time()
    
    # 배치별로 처리
    print("\n배치 처리 시작...")
    with tqdm(total=num_batches, desc="배치 처리 중", unit="배치") as pbar:
        for batch_num in range(num_batches):
            offset = batch_num * batch_size
            
            # 현재 배치 로드
            with db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT combination FROM base_combinations LIMIT {batch_size} OFFSET {offset}")
                batch_combinations = [row[0] for row in cursor.fetchall()]
            
            if not batch_combinations:
                break
            
            batch_start = len(batch_combinations)
            
            # 각 필터 순차 적용
            filtered = batch_combinations
            for filter_name in enabled_filters:
                if filter_name in filter_manager.filters:
                    filter_obj = filter_manager.filters[filter_name]
                    filtered = filter_obj.apply(filtered, 1185)
                    
                    if filtered is None or len(filtered) == 0:
                        break
            
            # 배치 결과 저장
            if filtered:
                batch_passed = len(filtered)
                all_filtered_combinations.extend(filtered)
            else:
                batch_passed = 0
            
            # 통계 업데이트
            total_processed += batch_start
            total_passed += batch_passed
            
            # 메모리 사용량 체크
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            # 진행 상태 업데이트
            pbar.set_postfix(
                processed=f"{total_processed:,}",
                passed=f"{total_passed:,}",
                rate=f"{(total_passed/total_processed*100):.2f}%",
                memory=f"{memory_mb:.0f}MB"
            )
            pbar.update(1)
            
            # 메모리가 너무 많이 사용되면 경고
            if memory_mb > 4000:  # 4GB 이상
                logging.warning(f"메모리 사용량 높음: {memory_mb:.0f}MB")
                
                # 중간 결과 저장
                if len(all_filtered_combinations) > 1000000:
                    print(f"\n중간 저장: {len(all_filtered_combinations):,}개")
                    # DB에 저장 로직 추가 가능
                    all_filtered_combinations = all_filtered_combinations[-100000:]  # 최근 10만개만 유지
    
    # 처리 시간 계산
    elapsed_time = time.time() - start_time
    
    # 최종 결과
    print("\n" + "=" * 80)
    print("필터링 완료!")
    print("=" * 80)
    print(f"처리된 조합: {total_processed:,}개")
    print(f"통과한 조합: {total_passed:,}개")
    print(f"통과율: {(total_passed/total_processed*100):.2f}%")
    print(f"처리 시간: {elapsed_time:.1f}초")
    print(f"처리 속도: {total_processed/elapsed_time:.0f}개/초")
    
    # 필터별 예상 통계 (샘플 기반)
    print("\n예상 필터별 제외율 (샘플 기반):")
    sample_size = min(10000, len(all_filtered_combinations))
    if sample_size > 0:
        sample = all_filtered_combinations[:sample_size]
        
        for filter_name in enabled_filters[:5]:  # 상위 5개만 표시
            if filter_name in filter_manager.filters:
                filter_obj = filter_manager.filters[filter_name]
                filtered_sample = filter_obj.apply(sample[:], 1185)
                if filtered_sample is not None:
                    exclude_rate = (1 - len(filtered_sample)/len(sample)) * 100
                    print(f"  {filter_name}: {exclude_rate:.1f}% 제외")
    
    # 결과 저장
    if total_passed > 0:
        print(f"\n최종 {total_passed:,}개 조합을 데이터베이스에 저장 중...")
        try:
            # 배치로 저장 (메모리 효율)
            save_batch_size = 10000
            for i in range(0, len(all_filtered_combinations), save_batch_size):
                batch = all_filtered_combinations[i:i+save_batch_size]
                db_manager.combinations_db.save_filtered_combinations(1185, batch)
                
                if i % 100000 == 0 and i > 0:
                    print(f"  {i:,}개 저장 완료...")
            
            print("저장 완료!")
        except Exception as e:
            logging.error(f"저장 중 오류: {str(e)}")
    
    return total_passed

if __name__ == "__main__":
    try:
        result = apply_filters_in_batches()
        print(f"\n최종 결과: {result:,}개 조합이 모든 필터를 통과했습니다.")
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()