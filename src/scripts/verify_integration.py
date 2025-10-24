"""
적응형 필터 시스템 통합 검증 스크립트
실제 프로그램 실행 시 통합 상태 확인
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_log_file():
    """로그 파일에서 적응형 필터 관련 메시지 확인"""
    
    print("\n" + "="*80)
    print(" 로그 파일 분석")
    print("="*80)
    
    log_file = "logs/lotto_app.log"
    
    if not os.path.exists(log_file):
        print("[X] 로그 파일이 없습니다")
        return False
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 최근 500줄 분석
    recent_lines = lines[-500:] if len(lines) > 500 else lines
    
    checks = {
        "시스템 활성화": False,
        "임계값 표시": False,
        "필터 생성": False,
        "패턴 분석": False,
        "DB 저장": False,
        "에러 발생": False
    }
    
    error_messages = []
    threshold_value = None
    
    for line in recent_lines:
        if "[시스템] 적응형 필터 활성화" in line:
            checks["시스템 활성화"] = True
        
        if "임계값:" in line and "%" in line:
            checks["임계값 표시"] = True
            # 임계값 추출
            try:
                import re
                match = re.search(r'임계값:\s*([\d.]+)%', line)
                if match:
                    threshold_value = float(match.group(1))
            except Exception as e:
                logging.error(f"검증 실패: {e}")
        
        if "AdaptiveProbabilityFilter" in line:
            checks["필터 생성"] = True
        
        if "패턴 분석" in line or "analyze_patterns" in line:
            checks["패턴 분석"] = True
        
        if "[DB] 필터 기준값 저장" in line:
            checks["DB 저장"] = True
        
        if "적응형 필터 로드 실패" in line:
            checks["에러 발생"] = True
            error_messages.append(line.strip())
    
    # 결과 출력
    print("\n[체크리스트]")
    for item, status in checks.items():
        if item == "에러 발생":
            if status:
                print(f"  [X] {item}")
                for err in error_messages[:3]:  # 최대 3개 에러 표시
                    print(f"      {err}")
            else:
                print(f"  [O] 에러 없음")
        else:
            symbol = "[O]" if status else "[X]"
            print(f"  {symbol} {item}")
    
    if threshold_value:
        print(f"\n[임계값 설정]")
        print(f"  현재 임계값: {threshold_value}%")
        
        if threshold_value <= 0.5:
            mode = "보수적"
        elif threshold_value <= 1.0:
            mode = "표준"
        elif threshold_value <= 2.0:
            mode = "공격적"
        else:
            mode = "매우 공격적"
        
        print(f"  모드: {mode}")
    
    return not checks["에러 발생"]

def check_config_file():
    """설정 파일 확인"""
    
    print("\n" + "="*80)
    print(" 설정 파일 확인")
    print("="*80)
    
    config_path = "configs/adaptive_filter_config.yaml"
    
    if not os.path.exists(config_path):
        print("[X] 설정 파일이 없습니다")
        return False
    
    import yaml
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        threshold = config.get('global_probability_threshold', None)
        
        if threshold:
            print(f"[O] 설정 파일 로드 성공")
            print(f"    임계값: {threshold}%")
            
            # 필터 활성화 상태
            filters = config.get('filters', {})
            active_count = sum(1 for v in filters.values() if v)
            print(f"    활성 필터: {active_count}개")
            
            return True
        else:
            print("[X] 임계값 설정이 없습니다")
            return False
            
    except Exception as e:
        print(f"[X] 설정 파일 로드 실패: {e}")
        return False

def check_database():
    """데이터베이스 상태 확인"""
    
    print("\n" + "="*80)
    print(" 데이터베이스 확인")
    print("="*80)
    
    import sqlite3
    
    # combinations.db 확인
    db_path = "data/combinations.db"
    
    if not os.path.exists(db_path):
        print("[X] combinations.db가 없습니다")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # adaptive_filter_criteria 테이블 확인
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='adaptive_filter_criteria'
        """)
        
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            print("[O] adaptive_filter_criteria 테이블 존재")
            
            # 데이터 확인
            cursor.execute("""
                SELECT COUNT(*), MAX(created_at) 
                FROM adaptive_filter_criteria
            """)
            
            count, last_update = cursor.fetchone()
            
            if count and count > 0:
                print(f"    저장된 기준: {count}개")
                print(f"    최종 업데이트: {last_update}")
            else:
                print("    [!] 저장된 기준 없음")
        else:
            print("[X] adaptive_filter_criteria 테이블 없음")
            print("    -> 첫 실행 시 자동 생성됩니다")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"[X] DB 확인 실패: {e}")
        return False

def provide_recommendations():
    """개선 권장사항 제공"""
    
    print("\n" + "="*80)
    print(" 권장사항")
    print("="*80)
    
    print("""
1. 프로그램 재실행:
   - main.py를 다시 실행하면 수정사항이 적용됩니다
   
2. 임계값 변경 테스트:
   - configs/adaptive_filter_config.yaml에서 
   - global_probability_threshold를 2.0으로 변경
   - main.py 재실행
   - 로그에서 "임계값: 2.0%" 확인
   
3. 로그 모니터링:
   - tail -f logs/lotto_app.log
   - "[시스템] 적응형 필터 활성화" 메시지 확인
   
4. DB 확인:
   - sqlite3 data/combinations.db
   - SELECT * FROM adaptive_filter_criteria;
    """)

def main():
    """메인 실행"""
    
    print("\n" + "="*80)
    print(" 적응형 필터 시스템 통합 검증")
    print(f" 검증 시간: {datetime.now()}")
    print("="*80)
    
    # 1. 로그 파일 확인
    log_ok = check_log_file()
    
    # 2. 설정 파일 확인
    config_ok = check_config_file()
    
    # 3. 데이터베이스 확인
    db_ok = check_database()
    
    # 최종 판정
    print("\n" + "="*80)
    print(" 최종 판정")
    print("="*80)
    
    if log_ok and config_ok and db_ok:
        print("\n[성공] 시스템이 정상적으로 통합되었습니다!")
        print("\n다음 단계:")
        print("1. 프로그램 재실행으로 완전한 통합 확인")
        print("2. 임계값 변경 테스트")
    else:
        print("\n[부분 성공] 일부 항목에 문제가 있습니다")
        print("\n해결 방법:")
        
        if not log_ok:
            print("- 프로그램 재실행 필요 (에러 수정됨)")
        if not config_ok:
            print("- 설정 파일 확인 필요")
        if not db_ok:
            print("- DB 초기화 필요 (첫 실행 시 자동)")
    
    # 권장사항
    provide_recommendations()

if __name__ == "__main__":
    main()