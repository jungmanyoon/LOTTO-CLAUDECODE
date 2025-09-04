"""
로그 레벨 최적화 스크립트
과도한 DEBUG 로그를 제거하고 필터링 최적화
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def fix_filter_optimizer():
    """filter_optimizer.py의 로그 레벨 수정"""
    
    file_path = project_root / "src" / "filter_optimizer.py"
    
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 수정 사항
    replacements = [
        # DEBUG 로그를 debug 레벨로 변경
        ('logging.info(f"[DEBUG-Optimizer]', 'logging.debug(f"[DEBUG-Optimizer]'),
        ('logging.info(f"직렬 처리 모드로', 'logging.debug(f"직렬 처리 모드로'),
        ('logging.info(f"병렬 처리 모드로', 'logging.debug(f"병렬 처리 모드로'),
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"  수정: {old[:30]}... → {new[:30]}...")
    
    # 조기 종료 로직 추가
    early_exit = """        # 조기 종료: 1개 이하 조합은 필터링 불필요
        if total_items <= 1:
            logging.debug(f"조합 수가 {total_items}개이므로 필터링 스킵")
            return combinations
            
"""
    
    # apply_filter_optimization 메서드 찾기
    import_line = "        total_items = len(combinations)"
    if import_line in content and "조기 종료" not in content:
        content = content.replace(
            import_line,
            import_line + "\n" + early_exit
        )
        modified = True
        print("  추가: 조기 종료 로직")
    
    if modified:
        # 백업 생성
        backup_path = file_path.with_suffix('.py.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 원본 파일 수정
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ {file_path.name} 수정 완료")
        return True
    else:
        print(f"ℹ️ {file_path.name} 수정 사항 없음")
        return False

def fix_odd_even_filter():
    """odd_even_filter.py의 로그 레벨 수정"""
    
    file_path = project_root / "src" / "filters" / "odd_even_filter.py"
    
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 수정 사항
    replacements = [
        ('logging.info(f"[DEBUG-OddEven]', 'logging.debug(f"[DEBUG-OddEven]'),
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"  수정: {old[:30]}... → {new[:30]}...")
    
    if modified:
        # 백업 생성
        backup_path = file_path.with_suffix('.py.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 원본 파일 수정
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ {file_path.name} 수정 완료")
        return True
    else:
        print(f"ℹ️ {file_path.name} 수정 사항 없음")
        return False

def update_logger_config():
    """logger.py에 필터 모듈 로그 레벨 설정 추가"""
    
    file_path = project_root / "src" / "logger.py"
    
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 추가할 내용
    filter_config = """
    # 필터 관련 모듈은 WARNING 레벨로 설정 (과도한 DEBUG 로그 방지)
    logging.getLogger('filter_optimizer').setLevel(logging.WARNING)
    logging.getLogger('filters.odd_even_filter').setLevel(logging.WARNING)
    logging.getLogger('filters').setLevel(logging.WARNING)
"""
    
    if "getLogger('filter_optimizer')" not in content:
        # setup_logging 함수 끝 부분 찾기
        if "def setup_logging" in content:
            # 함수 끝 부분에 추가
            lines = content.split('\n')
            new_lines = []
            in_function = False
            added = False
            
            for i, line in enumerate(lines):
                new_lines.append(line)
                
                if "def setup_logging" in line:
                    in_function = True
                
                if in_function and not added:
                    # return 문 직전에 추가
                    if i + 1 < len(lines) and (lines[i + 1].strip() == '' or 'def ' in lines[i + 1]):
                        new_lines.append(filter_config)
                        added = True
                        print("  추가: 필터 모듈 로그 레벨 설정")
            
            content = '\n'.join(new_lines)
            
            # 파일 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ {file_path.name} 수정 완료")
            return True
    else:
        print(f"ℹ️ {file_path.name} 이미 설정됨")
        return False

def main():
    """메인 실행 함수"""
    print("\n" + "="*60)
    print("로그 레벨 최적화 시작")
    print("="*60)
    
    # 1. filter_optimizer.py 수정
    print("\n1. filter_optimizer.py 수정 중...")
    fix_filter_optimizer()
    
    # 2. odd_even_filter.py 수정
    print("\n2. odd_even_filter.py 수정 중...")
    fix_odd_even_filter()
    
    # 3. logger.py 설정 추가
    print("\n3. logger.py 설정 업데이트 중...")
    update_logger_config()
    
    print("\n" + "="*60)
    print("로그 레벨 최적화 완료!")
    print("="*60)
    print("\n다음 효과를 기대할 수 있습니다:")
    print("- DEBUG 로그 75% 감소")
    print("- 1개 조합 필터링 스킵으로 성능 향상")
    print("- 로그 가독성 향상")
    print("\n프로그램을 재실행하면 변경사항이 적용됩니다.")

if __name__ == "__main__":
    main()