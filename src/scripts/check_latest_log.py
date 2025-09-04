#!/usr/bin/env python3
"""
최신 로그 확인 스크립트
"""
import os
from datetime import datetime

log_file = r"D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\logs\lotto_app.log"

if os.path.exists(log_file):
    # 파일의 마지막 100줄 읽기
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        last_100_lines = lines[-100:]
    
    print("="*70)
    print("최근 로그에서 tuple indices 에러 확인")
    print("="*70)
    
    found_errors = False
    for i, line in enumerate(last_100_lines):
        if "tuple indices" in line:
            found_errors = True
            # 시간 추출
            if line.startswith("2025-"):
                timestamp = line.split(" - ")[0]
                print(f"\n에러 발생 시간: {timestamp}")
            print(f"라인 {i}: {line.strip()}")
            # 다음 3줄도 출력
            for j in range(1, min(4, len(last_100_lines) - i)):
                print(f"  +{j}: {last_100_lines[i+j].strip()}")
    
    if not found_errors:
        print("\n최근 100줄에 'tuple indices' 에러가 없습니다.")
        print("에러가 해결된 것으로 보입니다.")
    
    # 파일 수정 시간 확인
    print("\n" + "="*70)
    print("파일 수정 시간 확인")
    print("="*70)
    
    specialized_db_file = r"D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\src\core\specialized_databases.py"
    if os.path.exists(specialized_db_file):
        mtime = os.path.getmtime(specialized_db_file)
        modified_time = datetime.fromtimestamp(mtime)
        print(f"specialized_databases.py 마지막 수정: {modified_time}")
    
    # 현재 시간
    print(f"현재 시간: {datetime.now()}")
    
else:
    print(f"로그 파일이 없습니다: {log_file}")