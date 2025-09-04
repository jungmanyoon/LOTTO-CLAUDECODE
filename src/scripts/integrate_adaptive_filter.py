"""
적응형 필터 시스템 통합 스크립트
main.py와 기존 시스템에 새로운 확률 기반 필터를 통합
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import yaml
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_current_status():
    """현재 시스템 통합 상태 점검"""
    
    print("\n" + "="*80)
    print(" 적응형 필터 시스템 통합 상태 점검")
    print("="*80)
    
    issues = []
    
    # 1. main.py 확인
    print("\n[1단계] main.py 확인")
    print("-"*60)
    
    with open("main.py", 'r', encoding='utf-8') as f:
        main_content = f.read()
    
    if "AdaptiveProbabilityFilter" not in main_content:
        print("  [X] main.py가 기존 FilterManager 사용 중")
        print("      -> 새로운 AdaptiveProbabilityFilter 미사용")
        issues.append("main.py 수정 필요")
    else:
        print("  [O] main.py가 AdaptiveProbabilityFilter 사용 중")
    
    # 2. 설정 파일 로드 확인
    print("\n[2단계] 설정 파일 로드 확인")
    print("-"*60)
    
    if "adaptive_filter_config.yaml" not in main_content:
        print("  [X] 새로운 설정 파일 미사용")
        print("      -> configs/adaptive_filter_config.yaml 로드 안 됨")
        issues.append("설정 파일 로드 코드 추가 필요")
    else:
        print("  [O] adaptive_filter_config.yaml 로드 중")
    
    # 3. DB 저장 로직 확인
    print("\n[3단계] DB 저장 로직 확인")
    print("-"*60)
    
    db_files = [
        "data/combinations.db",
        "data/filters/filter_criteria.db"
    ]
    
    for db_file in db_files:
        if os.path.exists(db_file):
            mod_time = os.path.getmtime(db_file)
            mod_date = datetime.fromtimestamp(mod_time)
            print(f"  [?] {db_file}")
            print(f"      최종 수정: {mod_date}")
        else:
            print(f"  [X] {db_file} 없음")
    
    # 4. 로그 설정 확인
    print("\n[4단계] 로그 표시 확인")
    print("-"*60)
    
    log_file = "logs/lotto_app.log"
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            recent_logs = f.readlines()[-100:]  # 최근 100줄
            
        threshold_logged = False
        for line in recent_logs:
            if "임계값" in line or "threshold" in line.lower():
                threshold_logged = True
                break
        
        if not threshold_logged:
            print("  [X] 로그에 임계값 표시 안 됨")
            issues.append("로그에 임계값 표시 추가 필요")
        else:
            print("  [O] 로그에 임계값 표시됨")
    
    # 5. 필터 기준값 저장 확인
    print("\n[5단계] 필터 기준값 저장 메커니즘")
    print("-"*60)
    
    # AdaptiveProbabilityFilter 클래스 확인
    adaptive_filter_path = "src/core/adaptive_probability_filter.py"
    with open(adaptive_filter_path, 'r', encoding='utf-8') as f:
        adaptive_content = f.read()
    
    if "save_criteria" not in adaptive_content and "save_to_db" not in adaptive_content:
        print("  [X] 필터 기준값 DB 저장 함수 없음")
        issues.append("DB 저장 함수 구현 필요")
    
    if "load_criteria" not in adaptive_content and "load_from_db" not in adaptive_content:
        print("  [X] 필터 기준값 DB 로드 함수 없음")
        issues.append("DB 로드 함수 구현 필요")
    
    # 결과 요약
    print("\n" + "="*80)
    print(" 점검 결과 요약")
    print("="*80)
    
    if issues:
        print("\n[발견된 문제점]")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\n[모든 항목 정상]")
    
    return issues

def generate_integration_code():
    """통합을 위한 코드 생성"""
    
    print("\n" + "="*80)
    print(" 필요한 수정 코드")
    print("="*80)
    
    print("\n[1] main.py 수정 코드:")
    print("-"*60)
    print("""
# main.py 상단에 추가 (37줄 근처)
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
import yaml

# main.py 697줄 근처 수정
# 기존 코드:
# filter_manager = FilterManager(db_manager)

# 새로운 코드:
try:
    # 적응형 필터 설정 로드
    with open('configs/adaptive_filter_config.yaml', 'r', encoding='utf-8') as f:
        adaptive_config = yaml.safe_load(f)
    
    threshold = adaptive_config['global_probability_threshold']
    logging.info(f"[시스템] 적응형 필터 활성화 - 임계값: {threshold}%")
    
    # 적응형 필터 사용
    filter_manager = AdaptiveProbabilityFilter(db_manager, threshold)
    
    # 과거 당첨번호 분석
    winning_numbers = db_manager.get_all_winning_numbers()
    filter_manager.analyze_patterns(winning_numbers)
    
    # 동적 기준 생성 및 로깅
    criteria = filter_manager.generate_dynamic_criteria()
    logging.info(f"[필터] 동적 기준 생성 완료 (임계값 {threshold}% 기준)")
    
except Exception as e:
    logging.warning(f"적응형 필터 로드 실패: {e}")
    logging.info("기존 FilterManager 사용")
    filter_manager = FilterManager(db_manager)
    """)
    
    print("\n[2] AdaptiveProbabilityFilter 클래스에 추가할 DB 저장 코드:")
    print("-"*60)
    print("""
def save_criteria_to_db(self, criteria: Dict):
    '''동적 기준값을 DB에 저장'''
    try:
        # DB 테이블 생성 (없으면)
        self.db_manager.execute('''
            CREATE TABLE IF NOT EXISTS adaptive_filter_criteria (
                id INTEGER PRIMARY KEY,
                threshold REAL,
                criteria TEXT,
                created_at TIMESTAMP,
                round_num INTEGER
            )
        ''')
        
        import json
        criteria_json = json.dumps(criteria)
        
        # 저장
        self.db_manager.execute('''
            INSERT INTO adaptive_filter_criteria 
            (threshold, criteria, created_at, round_num)
            VALUES (?, ?, ?, ?)
        ''', (self.probability_threshold, criteria_json, 
              datetime.now(), self.db_manager.get_latest_round()))
        
        logging.info(f"[DB] 필터 기준값 저장 완료 (임계값: {self.probability_threshold}%)")
        
    except Exception as e:
        logging.error(f"필터 기준값 저장 실패: {e}")

def load_criteria_from_db(self):
    '''DB에서 최신 기준값 로드'''
    try:
        result = self.db_manager.fetch_one('''
            SELECT threshold, criteria 
            FROM adaptive_filter_criteria 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        
        if result:
            import json
            self.probability_threshold = result[0]
            return json.loads(result[1])
            
    except Exception as e:
        logging.error(f"필터 기준값 로드 실패: {e}")
        return None
    """)
    
    print("\n[3] 로그 표시 개선 코드:")
    print("-"*60)
    print("""
# FilterManager.apply_filters() 시작 부분에 추가
logging.info("="*60)
logging.info(f"[필터링 시작] 임계값: {self.probability_threshold}%")
logging.info(f"  - 의미: {self.probability_threshold}% 이하 출현 패턴 제외")
logging.info(f"  - 모드: {'보수적' if self.probability_threshold <= 0.5 else '표준' if self.probability_threshold <= 1.0 else '공격적'}")
logging.info("="*60)
    """)

def check_workflow():
    """임계값 변경 시 워크플로우 확인"""
    
    print("\n" + "="*80)
    print(" 임계값 변경 워크플로우")
    print("="*80)
    
    print("""
[정상적인 워크플로우]

1. configs/adaptive_filter_config.yaml 수정
   └─> global_probability_threshold: 2.0 (변경)

2. main.py 실행
   └─> 설정 파일 로드
   └─> 새 임계값으로 AdaptiveProbabilityFilter 생성
   └─> 로그: "[시스템] 적응형 필터 활성화 - 임계값: 2.0%"

3. 패턴 분석 실행
   └─> 과거 당첨번호 분석
   └─> 새 임계값 기준으로 제외 패턴 계산
   └─> 로그: "[필터] 동적 기준 생성 완료 (임계값 2.0% 기준)"

4. DB 저장
   └─> adaptive_filter_criteria 테이블에 저장
   └─> 임계값, 기준값, 시간 기록
   └─> 로그: "[DB] 필터 기준값 저장 완료"

5. 필터링 실행
   └─> 새 기준으로 조합 필터링
   └─> 로그: "임계값 2.0% 기준 - X개 제외, Y개 남음"

6. 결과 저장
   └─> filtered_combinations 테이블 업데이트
   └─> 통계 정보 저장
    """)

def main():
    """메인 실행 함수"""
    
    print("\n" + "="*80)
    print(" 적응형 필터 시스템 통합 검사")
    print("="*80)
    
    # 1. 현재 상태 점검
    issues = check_current_status()
    
    # 2. 수정 코드 제공
    if issues:
        generate_integration_code()
    
    # 3. 워크플로우 설명
    check_workflow()
    
    # 최종 메시지
    print("\n" + "="*80)
    print(" 결론")
    print("="*80)
    
    if issues:
        print("\n[경고] 새로운 시스템이 통합되지 않았습니다!")
        print("\n필요한 작업:")
        print("1. main.py 수정 - AdaptiveProbabilityFilter 사용")
        print("2. DB 저장/로드 함수 추가")
        print("3. 로그 표시 개선")
        print("4. 설정 파일 로드 코드 추가")
    else:
        print("\n[성공] 모든 통합이 완료되었습니다!")

if __name__ == "__main__":
    main()