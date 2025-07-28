#!/bin/bash

echo "=========================================="
echo "로또 필터 시스템 전체 분석 시작"
echo "=========================================="

# 분석 디렉토리로 이동
cd "$(dirname "$0")/.."

# 1. 과거 당첨번호 간 일치도 분석
echo -e "\n[1/5] 과거 당첨번호 간 일치도 분석 중..."
python3 analyze_system/analyze_winning_number_matches.py

# 2. 필터 효과성 재평가
echo -e "\n[2/5] 필터 효과성 재평가 중..."
python3 analyze_system/analyze_filter_effectiveness.py

# 3. 개선된 백테스팅
echo -e "\n[3/5] 개선된 백테스팅 실행 중..."
python3 analyze_system/improved_backtesting.py

# 4. 필터 상관관계 분석
echo -e "\n[4/5] 필터 간 상관관계 분석 중..."
python3 analyze_system/filter_correlation_analysis.py

# 5. 동적 필터 관리 시스템
echo -e "\n[5/5] 동적 필터 관리 시스템 분석 중..."
python3 analyze_system/dynamic_filter_system.py

echo -e "\n=========================================="
echo "모든 분석이 완료되었습니다!"
echo "결과 파일들:"
echo "  - analyze_system/match_analysis_result.json"
echo "  - analyze_system/filter_effectiveness_result.json"
echo "  - analyze_system/improved_backtesting_result.json"
echo "  - analyze_system/filter_correlation_result.json"
echo "  - analyze_system/dynamic_filter_report.json"
echo "  - analyze_system/analysis_report.md"
echo "=========================================="