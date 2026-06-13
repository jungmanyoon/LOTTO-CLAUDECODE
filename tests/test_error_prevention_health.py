"""
[health-repair-6] ErrorPreventionSystem._check_filtered_pool_status 회귀 테스트

과거 버그: filtered_combinations에 'included' 컬럼이 없으면 전체 COUNT(*)를 통과 풀로 간주해
풀 크기를 과대평가 -> 거짓 '정상' 보고. 수정: None 센티넬로 '검증 불가'를 별도 표시.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.error_prevention_system import ErrorPreventionSystem, Priority


def _make_combinations_db(tmp_dir, with_included):
    data_dir = Path(tmp_dir) / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / 'combinations.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    if with_included:
        cur.execute('CREATE TABLE filtered_combinations (id INTEGER, included INTEGER)')
        cur.executemany('INSERT INTO filtered_combinations VALUES (?, ?)', [(i, 1) for i in range(10)])
    else:
        # included 컬럼 없이 다수 행 -> 전체 COUNT를 쓰면 거짓 '정상'이 됨
        cur.execute('CREATE TABLE filtered_combinations (id INTEGER)')
        cur.executemany('INSERT INTO filtered_combinations VALUES (?)', [(i,) for i in range(500000)])
    conn.commit()
    conn.close()
    return db_path


def test_pool_status_without_included_reports_unverifiable():
    """included 컬럼이 없으면 전체 COUNT를 통과 풀로 쓰지 않고 '검증 불가'로 보고해야 한다."""
    eps = ErrorPreventionSystem()
    with tempfile.TemporaryDirectory() as tmp:
        _make_combinations_db(tmp, with_included=False)
        eps.project_root = Path(tmp)
        eps.health_results = []
        eps._check_filtered_pool_status()

    result = eps.health_results[-1]
    assert '검증 불가' in result.message
    assert result.priority == Priority.MEDIUM
    assert result.status is True  # 하드 실패는 아님
    assert '정상' not in result.message  # 전체 카운트 기반 거짓 정상 금지


def test_pool_status_with_included_uses_passing_count():
    """included 컬럼이 있으면 통과(included=1) 수로 정상/부족을 판정한다(검증 불가 아님)."""
    eps = ErrorPreventionSystem()
    with tempfile.TemporaryDirectory() as tmp:
        _make_combinations_db(tmp, with_included=True)
        eps.project_root = Path(tmp)
        eps.health_results = []
        eps._check_filtered_pool_status()

    result = eps.health_results[-1]
    assert '검증 불가' not in result.message
    # included=1 인 10개는 min_size 미만이므로 '부족'으로 판정되어야 한다
    assert result.status is False
