#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
임시 파일 정리 스크립트

프로젝트 루트의 불필요한 임시/테스트 파일을 cleanup_archive로 이동
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

# 프로젝트 루트
ROOT_DIR = Path(__file__).parent

# 보관 디렉토리
ARCHIVE_DIR = ROOT_DIR / "cleanup_archive"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TARGET_ARCHIVE = ARCHIVE_DIR / f"archive_{TIMESTAMP}"

# 유지할 필수 파일 (화이트리스트)
KEEP_FILES = {
    # Python 실행 파일
    "main.py",

    # 프로젝트 문서
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",

    # 설정 파일
    "requirements.txt",
    "pytest.ini",
    "config.yaml",
    ".gitignore",
    ".coverage",

    # 이 스크립트 자신
    "cleanup_temp_files.py",
}

# 삭제할 패턴 (블랙리스트)
DELETE_PATTERNS = {
    # 테스트 스크립트
    "test_*.py",
    "check_*.py",
    "verify_*.py",
    "run_*.py",

    # 임시 문서
    "*_FIX*.md",
    "*_SUMMARY.md",
    "*_REPORT.md",
    "*_ANALYSIS.md",
    "*_QUICK_REF.md",
    "*_IMPROVEMENTS.txt",
    "ISSUE*.md",
    "POST_*.md",

    # 데이터 파일
    "*.json",
    "*.png",
    "*.db",

    # 로그/임시
    "temp_*.txt",
    "*.log",
}

def should_archive(filename: str) -> bool:
    """파일을 아카이브해야 하는지 판단"""
    # 화이트리스트에 있으면 유지
    if filename in KEEP_FILES:
        return False

    # 블랙리스트 패턴 확인
    from fnmatch import fnmatch
    for pattern in DELETE_PATTERNS:
        if fnmatch(filename, pattern):
            return True

    return False

def archive_files():
    """임시 파일들을 아카이브로 이동"""
    # 아카이브 디렉토리 생성
    TARGET_ARCHIVE.mkdir(parents=True, exist_ok=True)

    archived_files = []

    # 루트 디렉토리의 파일들만 검사
    for item in ROOT_DIR.iterdir():
        if not item.is_file():
            continue

        filename = item.name

        if should_archive(filename):
            # 아카이브로 이동
            target_path = TARGET_ARCHIVE / filename
            shutil.move(str(item), str(target_path))
            archived_files.append(filename)
            print(f"[O] Archived: {filename}")

    return archived_files

def create_archive_readme(archived_files):
    """아카이브에 README 생성"""
    readme_path = TARGET_ARCHIVE / "README.md"

    content = f"""# 임시 파일 아카이브 - {TIMESTAMP}

## 아카이브 이유
프로젝트 루트의 임시/테스트 파일들을 정리하여 프로젝트 구조를 깔끔하게 유지

## 아카이브된 파일 ({len(archived_files)}개)

"""

    # 파일 타입별로 그룹화
    test_files = [f for f in archived_files if f.startswith(('test_', 'check_', 'verify_', 'run_'))]
    doc_files = [f for f in archived_files if f.endswith('.md')]
    json_files = [f for f in archived_files if f.endswith('.json')]
    other_files = [f for f in archived_files if f not in test_files + doc_files + json_files]

    if test_files:
        content += "### 테스트 스크립트\n"
        for f in sorted(test_files):
            content += f"- {f}\n"
        content += "\n"

    if doc_files:
        content += "### 임시 문서\n"
        for f in sorted(doc_files):
            content += f"- {f}\n"
        content += "\n"

    if json_files:
        content += "### JSON 데이터\n"
        for f in sorted(json_files):
            content += f"- {f}\n"
        content += "\n"

    if other_files:
        content += "### 기타\n"
        for f in sorted(other_files):
            content += f"- {f}\n"
        content += "\n"

    content += f"""
## 복구 방법

필요한 파일이 있다면:
```bash
# 특정 파일 복구
cp cleanup_archive/archive_{TIMESTAMP}/파일명 .

# 전체 복구
cp -r cleanup_archive/archive_{TIMESTAMP}/* .
```

## 삭제 안전성

이 아카이브는 안전하게 삭제 가능합니다 (30일 후 권장).
"""

    readme_path.write_text(content, encoding='utf-8')

def update_gitignore():
    """gitignore에 임시 파일 패턴 추가"""
    gitignore_path = ROOT_DIR / ".gitignore"

    # 기존 내용 읽기
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding='utf-8')
    else:
        existing = ""

    # 추가할 패턴 (이미 있으면 스킵)
    new_patterns = [
        "",
        "# 임시 파일 자동 제외 (cleanup_temp_files.py)",
        "test_*.py",
        "check_*.py",
        "verify_*.py",
        "run_*.py",
        "*_FIX*.md",
        "*_SUMMARY.md",
        "*_REPORT.md",
        "*_ANALYSIS.md",
        "*_QUICK_REF.md",
        "temp_*.txt",
        "*.log",
        "",
        "# JSON 결과 파일",
        "db_index_optimization_results_*.json",
        "duplicate_index_check_*.json",
        "test_detailed_analysis.json",
        "test_performance_report.json",
        "filter_performance_report.json",
        "bayesian_beliefs.json",
        "fractal_analysis.json",
    ]

    patterns_to_add = []
    for pattern in new_patterns:
        if pattern and pattern not in existing:
            patterns_to_add.append(pattern)

    if patterns_to_add:
        with open(gitignore_path, 'a', encoding='utf-8') as f:
            f.write("\n")
            f.write("\n".join(patterns_to_add))
            f.write("\n")
        print(f"\n[O] .gitignore updated: {len(patterns_to_add)} patterns added")

if __name__ == "__main__":
    print("=" * 60)
    print("임시 파일 정리 시작")
    print("=" * 60)
    print()

    # 1. 파일 아카이브
    print("[1/3] 임시 파일 아카이브 중...")
    archived = archive_files()

    # 2. 아카이브 README 생성
    print(f"\n[2/3] 아카이브 README 생성 중...")
    create_archive_readme(archived)

    # 3. gitignore 업데이트
    print(f"\n[3/3] .gitignore 업데이트 중...")
    update_gitignore()

    print()
    print("=" * 60)
    print(f"정리 완료! {len(archived)}개 파일이 아카이브되었습니다.")
    print(f"아카이브 위치: {TARGET_ARCHIVE}")
    print("=" * 60)
