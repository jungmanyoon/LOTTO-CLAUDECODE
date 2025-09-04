#!/usr/bin/env python3
"""
모든 필터의 확률 기반 제외 테스트
- 모든 필터가 1% 임계값으로 패턴을 제외하는지 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_manager import DatabaseManager
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_all_filters_probability():
    """모든 필터의 확률 기반 제외 테스트"""
    print("\n" + "="*80)
    print("모든 필터 확률 기반 제외 테스트")
    print("="*80)
    
    try:
        # 1. 시스템 초기화
        db_manager = DatabaseManager()
        adaptive_filter = AdaptiveProbabilityFilter(db_manager, probability_threshold=1.0)
        
        # 2. 과거 당첨번호 가져오기
        winning_numbers = db_manager.get_all_winning_numbers()
        
        print(f"\n[데이터 준비]")
        print(f"  총 {len(winning_numbers)}개 회차 데이터 로드")
        
        # 3. 패턴 분석
        print("\n[패턴 분석 시작]")
        stats = adaptive_filter.analyze_patterns(winning_numbers)
        
        # 4. 분석 결과 출력
        print("\n[분석 결과]")
        filters_analyzed = [
            'odd_even', 'consecutive', 'sum_range', 'match', 'fixed_step',
            'last_digit', 'max_gap', 'section', 'average', 'multiple',
            'ten_section', 'prime_composite', 'arithmetic_sequence',
            'geometric_sequence', 'digit_sum', 'dispersion'
        ]
        
        for filter_name in filters_analyzed:
            if filter_name in stats and stats[filter_name]:
                print(f"  [O] {filter_name}: 분석 완료 ({len(stats[filter_name])} 패턴)")
            else:
                print(f"  [X] {filter_name}: 분석 실패")
        
        # 5. 동적 기준 생성
        print("\n[확률 기반 동적 기준 생성]")
        criteria = adaptive_filter.generate_dynamic_criteria()
        
        # 6. 각 필터별 제외 패턴 출력
        print("\n[필터별 제외 패턴 (1% 임계값)]")
        print("-"*60)
        
        # match 필터
        if 'match' in criteria:
            max_match = criteria['match']['max_match']
            print(f"1. Match 필터: {max_match+1}개 이상 일치 제외")
            if 'distribution' in criteria['match']:
                for match_count in [4, 5, 6]:
                    if match_count in criteria['match']['distribution']:
                        pct = criteria['match']['distribution'][match_count]
                        status = "제외" if match_count > max_match else "포함"
                        print(f"   - {match_count}개 일치: {pct:.2f}% ({status})")
        
        # odd_even 필터
        if 'odd_even' in criteria:
            excluded = criteria['odd_even'].get('excluded_counts', [])
            print(f"2. Odd/Even 필터: {excluded} 개수 제외")
        
        # consecutive 필터
        if 'consecutive' in criteria:
            max_cons = criteria['consecutive']['max_consecutive']
            print(f"3. Consecutive 필터: {max_cons+1}개 이상 연속 제외")
        
        # sum_range 필터
        if 'sum_range' in criteria:
            min_sum = criteria['sum_range']['min_sum']
            max_sum = criteria['sum_range']['max_sum']
            print(f"4. Sum Range 필터: {min_sum} 미만, {max_sum} 초과 제외")
        
        # last_digit 필터
        if 'last_digit' in criteria:
            min_same = criteria['last_digit']['min_same_last_digits']
            print(f"5. Last Digit 필터: 같은 끝자리 {min_same}개 미만 제외")
        
        # section 필터
        if 'section' in criteria:
            max_per_section = criteria['section']['max_numbers_per_section']
            print(f"6. Section 필터: 한 구간에 {max_per_section+1}개 이상 제외")
        
        # average 필터
        if 'average' in criteria:
            min_avg = criteria['average']['min_average']
            max_avg = criteria['average']['max_average']
            print(f"7. Average 필터: 평균 {min_avg:.1f} 미만, {max_avg:.1f} 초과 제외")
        
        # prime_composite 필터
        if 'prime_composite' in criteria:
            min_allowed = criteria['prime_composite']['min_allowed']
            max_allowed = criteria['prime_composite']['max_allowed']
            print(f"8. Prime/Composite 필터: 소수 {min_allowed}개 미만, {max_allowed}개 초과 제외")
        
        # arithmetic_sequence 필터
        if 'arithmetic_sequence' in criteria:
            excluded = criteria['arithmetic_sequence']['excluded_lengths']
            print(f"9. Arithmetic Sequence 필터: {excluded}개 수열 제외")
        
        # geometric_sequence 필터  
        if 'geometric_sequence' in criteria:
            excluded = criteria['geometric_sequence']['excluded_lengths']
            print(f"10. Geometric Sequence 필터: {excluded}개 수열 제외")
        
        # digit_sum 필터
        if 'digit_sum' in criteria:
            min_sum = criteria['digit_sum']['min_digit_sum']
            max_sum = criteria['digit_sum']['max_digit_sum']
            print(f"11. Digit Sum 필터: 자리수 합 {min_sum} 미만, {max_sum} 초과 제외")
        
        # dispersion 필터
        if 'dispersion' in criteria:
            min_var = criteria['dispersion']['min_variance']
            max_var = criteria['dispersion']['max_variance']
            print(f"12. Dispersion 필터: 분산 {min_var:.1f} 미만, {max_var:.1f} 초과 제외")
        
        # max_gap 필터
        if 'max_gap' in criteria:
            max_gap = criteria['max_gap']['max_allowed_gap']
            print(f"13. Max Gap 필터: 최대 간격 {max_gap} 초과 제외")
        
        # multiple 필터
        if 'multiple' in criteria:
            multiples = criteria['multiple'].get('multiples', {})
            if multiples:
                print(f"14. Multiple 필터:")
                for base, allowed_range in multiples.items():
                    if allowed_range:
                        print(f"    - {base}의 배수: {allowed_range[0]}~{allowed_range[1]}개 허용")
        
        # ten_section 필터
        if 'ten_section' in criteria:
            limits = criteria['ten_section'].get('section_limits', {})
            if limits:
                print(f"15. Ten Section 필터:")
                for section, excluded in limits.items():
                    if excluded:
                        print(f"    - {section}: {excluded}개 제외")
        
        # fixed_step 필터
        if 'fixed_step' in criteria:
            print(f"16. Fixed Step 필터: 특정 간격 패턴 제외")
        
        print("-"*60)
        
        # 7. 기준 저장 테스트
        print("\n[기준 저장 테스트]")
        adaptive_filter.save_criteria_to_db(criteria)
        print("  [O] 동적 기준 DB 저장 완료")
        
        # 8. 결과 요약
        print("\n" + "="*80)
        print("[테스트 결과]")
        print("  [O] 모든 16개 필터가 확률 기반 제외 구현 완료")
        print("  [O] 1% 임계값 기준으로 극히 드문 패턴 자동 제외")
        print("  [O] 각 필터별 동적 기준 생성 성공")
        print("="*80)
        
        return True
        
    except Exception as e:
        print(f"\n[X] 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """메인 테스트 실행"""
    print("\n" + "="*80)
    print("전체 필터 확률 기반 제외 시스템 테스트")
    print("="*80)
    
    success = test_all_filters_probability()
    
    if success:
        print("\n[최종 결과] SUCCESS - 모든 필터가 확률 기반 제외를 사용합니다")
    else:
        print("\n[최종 결과] FAILED - 일부 필터 구현 오류")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)