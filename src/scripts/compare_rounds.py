"""회차별 필터링 차이 분석"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3

def compare_filtering_rounds():
    """1182회차와 1183회차 필터링 차이 분석"""
    
    print("\n" + "="*60)
    print("회차별 필터링 결과 비교")
    print("="*60)
    
    filters = [
        'average', 'sum_range', 'consecutive', 'odd_even',
        'prime_composite', 'fixed_step', 'match', 'section',
        'last_digit', 'max_gap', 'multiple', 'ten_section',
        'arithmetic_sequence', 'geometric_sequence', 'digit_sum', 'dispersion'
    ]
    
    rounds_to_compare = [1182, 1183, 1184, 1185]
    
    for round_num in rounds_to_compare:
        print(f"\n{round_num}회차 필터링 결과:")
        print("-"*50)
        
        total_excluded_by_filter = {}
        
        for filter_name in filters:
            try:
                conn = sqlite3.connect(f'data/filters/{filter_name}_filter.db')
                cursor = conn.cursor()
                
                # excluded_combinations 수
                cursor.execute('SELECT COUNT(*) FROM excluded_combinations WHERE round = ?', (round_num,))
                result = cursor.fetchone()
                excluded = result[0] if result else 0
                
                # filtered_combinations 수  
                cursor.execute('SELECT COUNT(*) FROM filtered_combinations WHERE round = ?', (round_num,))
                result = cursor.fetchone()
                filtered = result[0] if result else 0
                
                if excluded > 0 or filtered > 0:
                    total_excluded_by_filter[filter_name] = excluded
                    print(f"  {filter_name:20s}: 제외 {excluded:8,}개, 통과 {filtered:8,}개")
                
                conn.close()
            except Exception as e:
                pass
        
        # 최종 결과
        conn = sqlite3.connect('data/combinations.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM filtered_combinations WHERE round = ?', (round_num,))
        result = cursor.fetchone()
        final_count = result[0] if result else 0
        conn.close()
        
        print(f"\n  최종 결과: {final_count:,}개 (생존율 {final_count/8145060*100:.4f}%)")
        
        # 문제 분석
        if round_num == 1182:
            normal_count = final_count
        elif final_count < normal_count * 0.01:  # 1% 미만으로 떨어지면 문제
            print(f"  ⚠️ 문제 발생! 정상 대비 {final_count/normal_count*100:.2f}%만 생존")

if __name__ == "__main__":
    compare_filtering_rounds()