#!/usr/bin/env python3
"""
특정 회차의 필터링된 조합을 생성하는 스크립트
Round 1190과 1191을 위한 빠른 필터링
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
import logging
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('specific_rounds_filtering.log', encoding='utf-8')
    ]
)

def filter_specific_rounds(target_rounds=None):
    """특정 회차들만 필터링"""

    if target_rounds is None:
        target_rounds = [1190, 1191]

    print("=" * 80)
    print(f"특정 회차 필터링: {target_rounds}")
    print("=" * 80)

    # 초기화
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)

    # 기존 데이터 제거
    print(f"\n기존 데이터 제거 중...")
    try:
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM filtered_combinations WHERE round IN ({})'.format(
                ','.join(['?' for _ in target_rounds])
            ), target_rounds)
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"제거된 기존 데이터: {deleted_count:,}개")
    except Exception as e:
        print(f"기존 데이터 제거 실패: {e}")

    # 각 회차별로 필터링
    for round_num in target_rounds:
        print(f"\n회차 {round_num} 필터링 시작...")
        start_time = time.time()

        try:
            # 기본 조합 생성 확인
            base_count = 0
            with db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM base_combinations")
                base_count = cursor.fetchone()[0]

            if base_count == 0:
                print(f"기본 조합이 없습니다. 먼저 기본 조합을 생성해주세요.")
                continue

            print(f"기본 조합 수: {base_count:,}개")

            # 모든 기본 조합 가져오기
            all_combinations = []
            with db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT combination FROM base_combinations")
                all_combinations = [row[0] for row in cursor.fetchall()]

            print(f"로드된 조합 수: {len(all_combinations):,}개")

            # 필터 적용
            filtered_combinations = all_combinations

            # 활성화된 필터 목록
            enabled_filters = []
            for name, filter_obj in filter_manager.filters.items():
                if filter_obj.criteria.get('enabled', True):
                    enabled_filters.append(name)

            print(f"활성 필터: {len(enabled_filters)}개")
            print(f"필터 목록: {enabled_filters}")

            # 각 필터 순차 적용
            for filter_name in enabled_filters:
                if filter_name in filter_manager.filters:
                    filter_obj = filter_manager.filters[filter_name]
                    before_count = len(filtered_combinations)

                    print(f"  {filter_name} 필터 적용 중... ({before_count:,}개 → ?)")

                    try:
                        filtered_combinations = filter_obj.apply(filtered_combinations, round_num)

                        if filtered_combinations is None:
                            filtered_combinations = []

                        after_count = len(filtered_combinations)
                        excluded = before_count - after_count
                        exclude_rate = (excluded / before_count * 100) if before_count > 0 else 0

                        print(f"    결과: {after_count:,}개 (제외: {excluded:,}개, {exclude_rate:.2f}%)")

                        if after_count == 0:
                            print(f"    경고: {filter_name} 필터에서 모든 조합이 제외되었습니다!")
                            break

                    except Exception as e:
                        print(f"    오류: {filter_name} 필터 적용 실패: {e}")
                        continue

            # 결과 저장
            if filtered_combinations and len(filtered_combinations) > 0:
                print(f"\n회차 {round_num} 결과 저장 중... ({len(filtered_combinations):,}개)")

                try:
                    # 배치로 저장
                    batch_size = 10000
                    saved_count = 0

                    for i in range(0, len(filtered_combinations), batch_size):
                        batch = filtered_combinations[i:i+batch_size]
                        db_manager.combinations_db.save_filtered_combinations(round_num, batch)
                        saved_count += len(batch)

                        if saved_count % 50000 == 0:
                            print(f"    {saved_count:,}개 저장 완료...")

                    print(f"회차 {round_num} 저장 완료: {saved_count:,}개")

                except Exception as e:
                    print(f"저장 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"회차 {round_num}: 필터를 통과한 조합이 없습니다!")

            # 시간 측정
            elapsed_time = time.time() - start_time
            print(f"회차 {round_num} 처리 시간: {elapsed_time:.1f}초")

        except Exception as e:
            print(f"회차 {round_num} 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()

    # 최종 결과 확인
    print("\n" + "=" * 80)
    print("필터링 완료 - 최종 결과")
    print("=" * 80)

    try:
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT round, COUNT(*) FROM filtered_combinations WHERE round >= 1189 GROUP BY round ORDER BY round')
            result = cursor.fetchall()

            print("필터링된 조합 현황:")
            for r, c in result:
                print(f"  Round {r}: {c:,}개")

    except Exception as e:
        print(f"결과 확인 중 오류: {e}")

if __name__ == "__main__":
    try:
        filter_specific_rounds([1190, 1191])
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()