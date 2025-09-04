"""fixed_step 필터 분석"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.db_manager import DatabaseManager
import sqlite3

def analyze_historical_fixed_steps():
    """역대 당첨 번호의 고정 간격 패턴 분석"""
    
    db_manager = DatabaseManager()
    conn = sqlite3.connect('data/lotto.db')
    cursor = conn.cursor()
    
    # 모든 당첨 번호 가져오기
    cursor.execute("""
        SELECT round, number1, number2, number3, number4, number5, number6
        FROM lotto_results
        ORDER BY round DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    print(f"\n총 {len(results)}회차 분석")
    print("="*60)
    
    # 간격별 통계
    step_stats = {}
    total_with_fixed_step = 0
    
    for row in results:
        round_num = row[0]
        numbers = sorted([row[1], row[2], row[3], row[4], row[5], row[6]])
        
        # 간격 계산
        gaps = []
        for i in range(1, len(numbers)):
            gaps.append(numbers[i] - numbers[i-1])
        
        # 동일한 간격이 연속으로 나타나는지 확인
        has_fixed_step = False
        for step in range(1, 10):  # 간격 1~9 확인
            consecutive_count = 0
            max_consecutive = 0
            
            for gap in gaps:
                if gap == step:
                    consecutive_count += 1
                    max_consecutive = max(max_consecutive, consecutive_count)
                else:
                    consecutive_count = 0
            
            if max_consecutive >= 2:  # 같은 간격이 2번 이상 연속
                has_fixed_step = True
                if step not in step_stats:
                    step_stats[step] = []
                step_stats[step].append((round_num, numbers, max_consecutive))
        
        if has_fixed_step:
            total_with_fixed_step += 1
    
    # 결과 출력
    print(f"\n고정 간격이 있는 회차: {total_with_fixed_step}개 ({total_with_fixed_step/len(results)*100:.2f}%)")
    print(f"고정 간격이 없는 회차: {len(results)-total_with_fixed_step}개 ({(len(results)-total_with_fixed_step)/len(results)*100:.2f}%)")
    
    print("\n간격별 상세 분석:")
    print("-"*60)
    
    for step in sorted(step_stats.keys()):
        occurrences = step_stats[step]
        print(f"\n간격 {step}:")
        print(f"  출현 횟수: {len(occurrences)}회 ({len(occurrences)/len(results)*100:.2f}%)")
        
        # 최근 5개 예시
        print(f"  최근 예시:")
        for round_num, numbers, count in occurrences[:5]:
            nums_str = ','.join(map(str, numbers))
            print(f"    {round_num}회: [{nums_str}] (연속 {count}개)")
    
    print("\n" + "="*60)
    print("💡 분석 결과:")
    print("="*60)
    
    if total_with_fixed_step / len(results) < 0.1:
        print("✅ 고정 간격 패턴은 실제로 매우 드물게 나타남 (10% 미만)")
        print("   → fixed_step 필터 설정이 너무 엄격함!")
    else:
        print(f"📊 고정 간격 패턴이 {total_with_fixed_step/len(results)*100:.1f}% 나타남")
    
    # 권장 설정
    print("\n권장 설정:")
    print("  - 간격 1: 3개 이상 연속일 때만 제외")
    print("  - 간격 2-3: 4개 이상 연속일 때만 제외")
    print("  - 간격 4-7: 5개 이상 연속일 때만 제외")
    print("  - 간격 8 이상: 제외하지 않음")

if __name__ == "__main__":
    analyze_historical_fixed_steps()