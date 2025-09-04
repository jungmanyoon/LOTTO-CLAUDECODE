"""필터 효율성 분석 스크립트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
import sqlite3

def analyze_filter_efficiency():
    """각 필터의 실제 효율성 분석"""
    
    db_manager = DatabaseManager()
    round_num = 1185
    
    print(f"\n{'='*60}")
    print(f"필터 효율성 분석 - {round_num}회차")
    print(f"{'='*60}")
    
    # 전체 조합 수
    total_combinations = 8145060
    print(f"\n초기 조합 수: {total_combinations:,}개")
    
    # 각 필터 DB에서 제외된 조합 수 확인
    filter_stats = {}
    filter_names = [
        'match', 'odd_even', 'consecutive', 'sum_range',
        'fixed_step', 'last_digit', 'max_gap', 'section', 'average',
        'multiple', 'ten_section', 'arithmetic_sequence', 'geometric_sequence',
        'prime_composite', 'digit_sum', 'dispersion', 'ml_prediction'
    ]
    
    print(f"\n{'필터명':<20} {'제외된 조합':<15} {'제외 비율':<10}")
    print("-" * 50)
    
    for filter_name in filter_names:
        db_path = f'data/filters/{filter_name}_filter.db'
        if not os.path.exists(db_path):
            continue
            
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # filter_details 테이블에서 정보 가져오기
            cursor.execute("""
                SELECT excluded_count, exclude_percent 
                FROM filter_details 
                WHERE round = ?
            """, (round_num,))
            
            result = cursor.fetchone()
            if result:
                excluded_count, exclude_percent = result
                filter_stats[filter_name] = {
                    'excluded': excluded_count,
                    'percent': exclude_percent
                }
                print(f"{filter_name:<20} {excluded_count:>12,}개 {exclude_percent:>8.2f}%")
            
            conn.close()
            
        except Exception as e:
            print(f"{filter_name:<20} 데이터 없음")
    
    # 최종 필터링된 조합 수 확인
    conn = sqlite3.connect('data/combinations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM filtered_combinations WHERE round = ?', (round_num,))
    final_count = cursor.fetchone()[0]
    conn.close()
    
    print("\n" + "="*50)
    print(f"최종 남은 조합: {final_count:,}개")
    print(f"총 제외된 조합: {total_combinations - final_count:,}개 ({(total_combinations - final_count) / total_combinations * 100:.2f}%)")
    
    # 필터 효율성 순위
    if filter_stats:
        print(f"\n{'='*60}")
        print("필터 효율성 순위 (제외 비율 기준)")
        print(f"{'='*60}")
        
        sorted_filters = sorted(filter_stats.items(), 
                               key=lambda x: x[1]['percent'], 
                               reverse=True)
        
        for rank, (name, stats) in enumerate(sorted_filters[:10], 1):
            print(f"{rank:2d}. {name:<20} {stats['percent']:>6.2f}% ({stats['excluded']:,}개 제외)")
    
    # 중요 통찰
    print(f"\n{'='*60}")
    print("중요 통찰")
    print(f"{'='*60}")
    print(f"• 표시된 제외 비율은 각 필터가 전체 814만개 중에서 제외하는 비율입니다")
    print(f"• 실제로는 필터가 순차적으로 적용되어 조합이 급격히 감소합니다")
    print(f"• 예: average 필터가 76%를 제외하면 나머지 필터는 24%에서만 작동")
    print(f"• 최종 결과: {total_combinations:,}개 → {final_count:,}개 (생존율 {final_count/total_combinations*100:.4f}%)")

if __name__ == "__main__":
    analyze_filter_efficiency()