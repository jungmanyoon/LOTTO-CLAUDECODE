"""
근본 원인 분석 스크립트: 필터 통과율 보호 시스템이 작동하지 않는 이유 추적
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

print("=" * 80)
print("필터 통과율 보호 시스템 실행 흐름 추적")
print("=" * 80)

# 1. 데이터베이스 현황 확인
conn = sqlite3.connect('data/continuous_improvement.db')
cursor = conn.cursor()

print("\n[1단계] 데이터베이스 현황")
print("-" * 40)

cursor.execute('SELECT COUNT(*) FROM performance_history')
total = cursor.fetchone()[0]
print(f"총 레코드 수: {total}")

cursor.execute('SELECT COUNT(*) FROM performance_history WHERE filter_pass_rate IS NOT NULL AND filter_pass_rate > 0')
valid = cursor.fetchone()[0]
print(f"유효한 filter_pass_rate 레코드: {valid}")

cursor.execute('SELECT COUNT(*) FROM performance_history WHERE is_best_pass_rate = TRUE')
best = cursor.fetchone()[0]
print(f"is_best_pass_rate = TRUE 레코드: {best}")

# 2. 보호 로직 작동 조건 확인
print("\n[2단계] 보호 로직 작동 조건")
print("-" * 40)

# filter_validator.py:438의 조건 확인
print("\n조건 체크:")
print(f"  1) best_pass_rate_perf 존재 여부: {valid > 0}")
print(f"  2) best_pass_rate_perf.filter_pass_rate > 0: {valid > 0}")

if valid > 0:
    cursor.execute('''
        SELECT filter_pass_rate, avg_matches, created_at
        FROM performance_history
        WHERE is_best_pass_rate = TRUE
        ORDER BY filter_pass_rate DESC
        LIMIT 1
    ''')
    best_record = cursor.fetchone()
    if best_record:
        print(f"\n역대 최고 통과율 레코드:")
        print(f"  - filter_pass_rate: {best_record[0]:.2f}%")
        print(f"  - avg_matches: {best_record[1]}")
        print(f"  - created_at: {best_record[2]}")
    else:
        print("\n⚠️ filter_pass_rate > 0인 레코드가 있지만 is_best_pass_rate = TRUE인 레코드가 없습니다!")
        print("   → get_best_pass_rate_performance()가 None을 반환할 것입니다.")
else:
    print("\n❌ filter_pass_rate > 0인 레코드가 하나도 없습니다!")
    print("   → 보호 로직이 작동할 수 없습니다.")

# 3. 문제 진단
print("\n[3단계] 근본 원인 진단")
print("-" * 40)

if valid == 0:
    print("\n🔴 근본 원인: 데이터가 아직 저장되지 않음")
    print("\n가능한 시나리오:")
    print("  A) 코드 수정 후 프로그램을 재시작하지 않았음")
    print("  B) 코드 수정 후 재시작했지만 백테스팅이 아직 실행되지 않음")
    print("  C) 백테스팅은 실행되었지만 filter_pass_rate가 저장되지 않음 (버그)")

    # 최근 레코드 확인
    cursor.execute('SELECT id, avg_matches, created_at FROM performance_history ORDER BY id DESC LIMIT 5')
    recent = cursor.fetchall()
    print("\n최근 레코드 (filter_pass_rate는 모두 NULL):")
    for r in recent:
        print(f"  ID {r[0]}: avg_matches={r[1]:.2f}, created_at={r[2]}")

    print("\n✅ 해결 방법:")
    print("  1) main.py를 재시작하여 새 코드를 로드")
    print("  2) 백테스팅이 실행될 때까지 대기 (자동 실행)")
    print("  3) 또는 수동으로 백테스팅 트리거")

elif best == 0:
    print("\n🟡 근본 원인: filter_pass_rate 데이터는 있지만 is_best_pass_rate 플래그가 설정되지 않음")
    print("\n이는 save_performance() 메서드에 버그가 있음을 의미합니다.")
    print("  → continuous_improvement_engine.py:179-201 라인 확인 필요")
else:
    print("\n🟢 데이터는 정상: 보호 로직이 작동해야 합니다")
    print("\n그런데도 '📊 필터 통과율 비교:' 메시지가 안 나온다면:")
    print("  → filter_validator.py의 보호 로직에 버그가 있거나")
    print("  → 현재 실행 중인 프로세스가 구버전 코드를 사용 중")

# 4. 실행 계획 제안
print("\n[4단계] 즉시 취해야 할 조치")
print("-" * 40)

if valid == 0:
    print("\n✅ 다음 단계:")
    print("  1. 현재 실행 중인 main.py 프로세스 확인")
    print("     - Windows: tasklist | findstr python")
    print("  2. 프로세스가 실행 중이면 종료 후 재시작")
    print("  3. 프로세스가 없으면 main.py 실행")
    print("  4. 로그에서 '백테스팅 시작' 메시지 확인")
    print("  5. 백테스팅 완료 후 이 스크립트 다시 실행")
else:
    print("\n✅ 데이터 확인 완료, 다음 검증 필요:")
    print("  1. 현재 실행 중인 프로세스가 신규 코드를 로드했는지 확인")
    print("  2. filter_validator.py:438-444 로직이 실행되는지 로그 확인")
    print("  3. PerformanceTracker.get_best_pass_rate_performance() 반환값 확인")

conn.close()

print("\n" + "=" * 80)
