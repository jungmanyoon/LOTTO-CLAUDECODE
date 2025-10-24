"""
적응형 필터 시스템 통합 패치 적용 스크립트
main.py와 관련 파일들을 자동으로 수정
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import shutil
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def backup_files():
    """수정할 파일들 백업"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        "main.py",
        "src/core/adaptive_probability_filter.py"
    ]
    
    for file in files_to_backup:
        if os.path.exists(file):
            backup_path = os.path.join(backup_dir, os.path.basename(file))
            shutil.copy2(file, backup_path)
            print(f"  백업: {file} -> {backup_path}")
    
    return backup_dir

def patch_main_py():
    """main.py 수정"""
    
    print("\n[1] main.py 패치 중...")
    
    with open("main.py", 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 1. import 추가 (37줄 근처)
    import_added = False
    for i, line in enumerate(lines):
        if "from src.core.filter_manager import FilterManager" in line:
            # 바로 다음 줄에 추가
            lines.insert(i+1, "from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter\n")
            lines.insert(i+2, "import yaml\n")
            import_added = True
            print("  [O] import 문 추가 완료")
            break
    
    if not import_added:
        print("  [X] import 위치를 찾을 수 없음")
        return False
    
    # 2. FilterManager 사용 부분 수정 (697줄 근처)
    filter_manager_found = False
    for i, line in enumerate(lines):
        if "filter_manager = FilterManager(db_manager)" in line and "# 기존" not in line:
            # 해당 줄을 새로운 코드로 교체
            indent = "        "  # 8칸 들여쓰기
            
            new_code = f'''
{indent}# 적응형 필터 시스템 사용 (통합 확률 기반)
{indent}try:
{indent}    # 설정 파일 로드
{indent}    with open('configs/adaptive_filter_config.yaml', 'r', encoding='utf-8') as f:
{indent}        adaptive_config = yaml.safe_load(f)
{indent}    
{indent}    threshold = adaptive_config['global_probability_threshold']
{indent}    logging.info("="*60)
{indent}    logging.info(f"[시스템] 적응형 필터 활성화")
{indent}    logging.info(f"  임계값: {{threshold}}%")
{indent}    logging.info(f"  의미: {{threshold}}% 이하 출현 패턴 제외")
{indent}    logging.info(f"  모드: {{'보수적' if threshold <= 0.5 else '표준' if threshold <= 1.0 else '공격적' if threshold <= 2.0 else '매우 공격적'}}")
{indent}    logging.info("="*60)
{indent}    
{indent}    # 적응형 필터 생성
{indent}    filter_manager = AdaptiveProbabilityFilter(db_manager, threshold)
{indent}    
{indent}    # 과거 당첨번호 분석
{indent}    winning_numbers = db_manager.get_winning_numbers(limit=200)
{indent}    filter_manager.analyze_patterns(winning_numbers)
{indent}    
{indent}    # 동적 기준 생성
{indent}    criteria = filter_manager.generate_dynamic_criteria()
{indent}    
{indent}    # DB에 저장
{indent}    filter_manager.save_criteria_to_db(criteria)
{indent}    
{indent}    logging.info(f"[필터] 동적 기준 생성 완료 (임계값 {{threshold}}% 기준)")
{indent}    
{indent}except Exception as e:
{indent}    logging.warning(f"적응형 필터 로드 실패: {{e}}")
{indent}    logging.info("기존 FilterManager 사용")
{indent}    filter_manager = FilterManager(db_manager)  # 기존 시스템 폴백
'''
            
            lines[i] = new_code
            filter_manager_found = True
            print("  [O] FilterManager 교체 완료")
            break
    
    if not filter_manager_found:
        print("  [X] FilterManager 사용 위치를 찾을 수 없음")
        return False
    
    # 파일 저장
    with open("main.py", 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("  [O] main.py 패치 완료")
    return True

def patch_adaptive_filter():
    """AdaptiveProbabilityFilter에 DB 함수 추가"""
    
    print("\n[2] AdaptiveProbabilityFilter 패치 중...")
    
    with open("src/core/adaptive_probability_filter.py", 'r', encoding='utf-8') as f:
        content = f.read()
    
    # DB 함수가 이미 있는지 확인
    if "save_criteria_to_db" in content:
        print("  [O] DB 저장 함수 이미 존재")
        return True
    
    # 클래스 끝 부분 찾기
    class_end = content.rfind("    def get_exclusion_summary")
    
    if class_end == -1:
        print("  [X] 클래스 끝을 찾을 수 없음")
        return False
    
    # DB 함수 추가
    db_functions = '''
    
    def save_criteria_to_db(self, criteria: Dict):
        """동적 기준값을 DB에 저장"""
        try:
            # DB 연결이 없으면 스킵
            if not hasattr(self.db_manager, 'execute'):
                logging.debug("DB 저장 스킵 - execute 메서드 없음")
                return
                
            # 테이블 생성 (없으면)
            self.db_manager.execute("""
                CREATE TABLE IF NOT EXISTS adaptive_filter_criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    threshold REAL,
                    criteria TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    round_num INTEGER
                )
            """)
            
            import json
            from datetime import datetime
            criteria_json = json.dumps(criteria, ensure_ascii=False)
            
            # 최신 회차 가져오기
            try:
                latest_round = self.db_manager.get_latest_round()
            except Exception as e:
            logging.error(f"패치 적용 실패: {e}")
                latest_round = 0
            
            # 저장
            self.db_manager.execute("""
                INSERT INTO adaptive_filter_criteria 
                (threshold, criteria, round_num)
                VALUES (?, ?, ?)
            """, (self.probability_threshold, criteria_json, latest_round))
            
            logging.info(f"[DB] 필터 기준값 저장 완료 (임계값: {self.probability_threshold}%)")
            
        except Exception as e:
            logging.error(f"필터 기준값 저장 실패: {e}")
    
    def load_criteria_from_db(self):
        """DB에서 최신 기준값 로드"""
        try:
            # DB 연결이 없으면 스킵
            if not hasattr(self.db_manager, 'fetch_one'):
                logging.debug("DB 로드 스킵 - fetch_one 메서드 없음")
                return None
                
            result = self.db_manager.fetch_one("""
                SELECT threshold, criteria 
                FROM adaptive_filter_criteria 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            if result:
                import json
                self.probability_threshold = result[0]
                loaded_criteria = json.loads(result[1])
                logging.info(f"[DB] 필터 기준값 로드 완료 (임계값: {self.probability_threshold}%)")
                return loaded_criteria
                
        except Exception as e:
            logging.error(f"필터 기준값 로드 실패: {e}")
            return None
'''
    
    # 함수 삽입
    content = content[:class_end] + db_functions + "\n" + content[class_end:]
    
    # 파일 저장
    with open("src/core/adaptive_probability_filter.py", 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("  [O] AdaptiveProbabilityFilter 패치 완료")
    return True

def verify_patch():
    """패치 검증"""
    
    print("\n[3] 패치 검증 중...")
    
    # main.py 확인
    with open("main.py", 'r', encoding='utf-8') as f:
        main_content = f.read()
    
    checks = {
        "AdaptiveProbabilityFilter import": "from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter" in main_content,
        "yaml import": "import yaml" in main_content,
        "설정 파일 로드": "adaptive_filter_config.yaml" in main_content,
        "임계값 로깅": "임계값:" in main_content,
        "적응형 필터 생성": "AdaptiveProbabilityFilter(db_manager" in main_content
    }
    
    # adaptive_probability_filter.py 확인
    with open("src/core/adaptive_probability_filter.py", 'r', encoding='utf-8') as f:
        adaptive_content = f.read()
    
    checks["DB 저장 함수"] = "save_criteria_to_db" in adaptive_content
    checks["DB 로드 함수"] = "load_criteria_from_db" in adaptive_content
    
    all_ok = True
    for check, result in checks.items():
        status = "[O]" if result else "[X]"
        print(f"  {status} {check}")
        if not result:
            all_ok = False
    
    return all_ok

def main():
    """메인 실행"""
    
    print("\n" + "="*80)
    print(" 적응형 필터 시스템 통합 패치")
    print("="*80)
    
    print("\n[백업 생성 중...]")
    backup_dir = backup_files()
    print(f"  백업 완료: {backup_dir}/")
    
    print("\n[패치 적용 중...]")
    
    # 1. main.py 패치
    main_success = patch_main_py()
    
    # 2. AdaptiveProbabilityFilter 패치
    adaptive_success = patch_adaptive_filter()
    
    # 3. 검증
    if main_success and adaptive_success:
        verify_success = verify_patch()
    else:
        verify_success = False
    
    print("\n" + "="*80)
    print(" 패치 결과")
    print("="*80)
    
    if verify_success:
        print("\n[성공] 모든 패치가 성공적으로 적용되었습니다!")
        print("\n이제 다음과 같이 작동합니다:")
        print("1. configs/adaptive_filter_config.yaml에서 임계값 변경")
        print("2. main.py 실행 시 자동으로 새 임계값 적용")
        print("3. 로그에 임계값 표시")
        print("4. DB에 기준값 저장")
        print("5. 필터링 시 새 기준 적용")
    else:
        print("\n[실패] 일부 패치가 실패했습니다.")
        print(f"백업 파일로 복구: {backup_dir}/")
    
    return verify_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)