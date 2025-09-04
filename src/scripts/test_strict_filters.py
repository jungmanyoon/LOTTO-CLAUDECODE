#!/usr/bin/env python3
"""
엄격한 필터 설정 테스트
목표 통과율: 10-20%
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
import yaml
import time

def test_strict_filters():
    """엄격한 필터 테스트"""
    
    print("=" * 80)
    print("엄격한 필터 설정 테스트")
    print("목표 통과율: 10-20%")
    print("=" * 80)
    
    # 엄격한 설정 로드
    with open('configs/strict_filter_config.yaml', 'r', encoding='utf-8') as f:
        strict_config = yaml.safe_load(f)
    
    # DB 매니저 초기화
    db_manager = DatabaseManager()
    
    # 기존 config 백업
    with open('config.yaml', 'r', encoding='utf-8') as f:
        original_config = yaml.safe_load(f)
    
    # 엄격한 필터 설정을 config.yaml에 임시 적용
    config = original_config.copy()
    config['filters']['criteria'] = strict_config['filters']['criteria']
    
    # config.yaml 임시 업데이트
    with open('config.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    # 필터 매니저 재초기화
    filter_manager = FilterManager(db_manager)
    
    # 테스트할 조합 수
    test_sizes = [10000, 50000, 100000]
    
    results = {}
    
    for test_size in test_sizes:
        print(f"\n테스트 크기: {test_size:,}개")
        print("-" * 40)
        
        # 샘플 로드
        with db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT combination FROM base_combinations LIMIT {test_size}")
            combinations = [row[0] for row in cursor.fetchall()]
        
        print(f"로드된 조합: {len(combinations):,}개")
        
        # 필터 적용
        start_time = time.time()
        remaining = combinations[:]
        
        # 각 필터별 통계
        filter_stats = []
        
        for filter_name, filter_obj in filter_manager.filters.items():
            if filter_obj.criteria.get('enabled', True):
                input_count = len(remaining)
                filtered = filter_obj.apply(remaining, 1185)
                
                if filtered is not None:
                    output_count = len(filtered)
                    excluded = input_count - output_count
                    exclude_rate = (excluded / input_count * 100) if input_count > 0 else 0
                    
                    filter_stats.append({
                        'name': filter_name,
                        'input': input_count,
                        'output': output_count,
                        'excluded': excluded,
                        'exclude_rate': exclude_rate
                    })
                    
                    remaining = filtered
                    
                    if len(remaining) == 0:
                        break
        
        elapsed = time.time() - start_time
        
        # 결과 저장
        final_count = len(remaining)
        pass_rate = (final_count / test_size * 100) if test_size > 0 else 0
        
        results[test_size] = {
            'initial': test_size,
            'final': final_count,
            'pass_rate': pass_rate,
            'time': elapsed,
            'filter_stats': filter_stats
        }
        
        # 결과 출력
        print(f"\n최종 결과:")
        print(f"  초기: {test_size:,}개")
        print(f"  최종: {final_count:,}개")
        print(f"  통과율: {pass_rate:.2f}%")
        print(f"  처리 시간: {elapsed:.2f}초")
        
        # 목표 범위 체크
        if 10 <= pass_rate <= 20:
            print(f"  ✅ 목표 달성! (10-20% 범위)")
        elif pass_rate < 10:
            print(f"  ⚠️ 너무 엄격함 ({pass_rate:.2f}% < 10%)")
        else:
            print(f"  ⚠️ 너무 느슨함 ({pass_rate:.2f}% > 20%)")
        
        # 주요 병목 필터 (상위 5개)
        print(f"\n주요 병목 필터:")
        sorted_filters = sorted(filter_stats, key=lambda x: x['exclude_rate'], reverse=True)[:5]
        for i, fs in enumerate(sorted_filters, 1):
            print(f"  {i}. {fs['name']}: {fs['exclude_rate']:.1f}% 제외")
    
    # 전체 요약
    print("\n" + "=" * 80)
    print("전체 테스트 요약")
    print("=" * 80)
    
    for size, result in results.items():
        status = "✅" if 10 <= result['pass_rate'] <= 20 else "❌"
        print(f"{size:,}개: {result['pass_rate']:.2f}% {status}")
    
    # 권장사항
    print("\n권장사항:")
    avg_pass_rate = sum(r['pass_rate'] for r in results.values()) / len(results)
    
    if avg_pass_rate < 10:
        print("필터가 너무 엄격합니다. 다음을 완화하세요:")
        for size, result in results.items():
            if result['filter_stats']:
                worst_filter = sorted(result['filter_stats'], key=lambda x: x['exclude_rate'], reverse=True)[0]
                print(f"  - {worst_filter['name']} ({worst_filter['exclude_rate']:.1f}% 제외)")
    elif avg_pass_rate > 20:
        print("필터가 너무 느슨합니다. 다음을 강화하세요:")
        for size, result in results.items():
            if result['filter_stats']:
                best_filter = sorted(result['filter_stats'], key=lambda x: x['exclude_rate'])[0]
                print(f"  - {best_filter['name']} ({best_filter['exclude_rate']:.1f}% 제외)")
    else:
        print(f"적절한 설정입니다! 평균 통과율: {avg_pass_rate:.2f}%")
    
    # 814만개 예상
    if results:
        avg_rate = avg_pass_rate
        expected_pass = int(8145060 * avg_rate / 100)
        print(f"\n814만개 적용 시 예상:")
        print(f"  통과 조합: {expected_pass:,}개")
        print(f"  통과율: {avg_rate:.2f}%")
    
    # 원래 설정 복원
    with open('config.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(original_config, f, allow_unicode=True, default_flow_style=False)
    
    return results

if __name__ == "__main__":
    results = test_strict_filters()