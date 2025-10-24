"""
필터 통과율 데이터 생성을 위한 백테스팅 트리거 스크립트

사용법:
    python trigger_backtest.py

이 스크립트는:
1. 백테스팅 실행하여 overall_filter_pass_rate 계산
2. 데이터베이스에 filter_pass_rate 저장
3. 보호 시스템 활성화
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.continuous_improvement_engine import ContinuousImprovementEngine
from src.core.db_manager import DatabaseManager

def main():
    print("\n" + "="*80)
    print("[START] Filter Pass Rate Data Generation Script")
    print("="*80)

    # DatabaseManager 초기화
    print("\n[1/4] Initializing DatabaseManager...")
    db = DatabaseManager()
    print("   [OK] DatabaseManager initialized")

    # ContinuousImprovementEngine 초기화
    print("\n[2/4] Initializing ContinuousImprovementEngine...")
    engine = ContinuousImprovementEngine(db_manager=db)
    print("   [OK] ContinuousImprovementEngine initialized")

    # 백테스팅 실행
    print("\n[3/4] Running backtesting (2-3 minutes)...")
    print("   - Measuring performance on recent 50 rounds")
    print("   - Calculating overall_filter_pass_rate")
    print("   - Analyzing per-filter pass rates")

    try:
        result = engine._measure_current_performance()

        print(f"\n   [OK] Backtesting completed!")
        print(f"\n   [RESULTS] Performance Metrics:")
        print(f"      - Average matches: {result.avg_matches:.2f}")
        print(f"      - Best match: {result.best_match}")
        print(f"      - Filter pass rate: {result.filter_pass_rate:.2f}%  <-- KEY VALUE!")
        print(f"      - ML inclusion rate: {result.ml_inclusion_rate:.2f}%")

        # 데이터 저장
        print("\n[4/4] Saving to database...")
        engine.tracker.save_performance(result)
        print("   [OK] Database save completed!")

        # 검증
        print("\n" + "="*80)
        print("[SUCCESS] Protection system is now activated!")
        print("="*80)
        print("\nNext steps:")
        print("1. Database filter_pass_rate saved: [OK]")
        print(f"2. Saved value: {result.filter_pass_rate:.2f}%")
        print("3. Protection message will appear on next run")
        print("\nRestart the program or wait for next filter validation")
        print("to see the protection system in action.\n")

    except Exception as e:
        print(f"\n   [ERROR] Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
