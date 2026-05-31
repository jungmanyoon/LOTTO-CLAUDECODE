#!/usr/bin/env python3
"""
Comprehensive tests for bug fixes

NOTE: This file contains script-style tests that verify source code patterns.
      For pytest compatibility, all execution code is wrapped in main().
      Run directly: python tests/test_bug_fixes.py
      Or import functions for pytest usage.
"""
import sys
import os
import re
import pytest

# Set proper paths
PROJECT_ROOT = r'd:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0'


def read_source_file(relative_path):
    """Read source file from project root"""
    full_path = os.path.join(PROJECT_ROOT, relative_path)
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


# ==== Pytest-Compatible Test Functions ====

def test_filter_manager_thread_safety():
    """Test 1: Thread-Safety in FilterManager (Phase 2.1 Refactored)

    After Phase 2.1 refactoring:
    - FilterManager uses singleton lock for thread-safe instance creation
    - FilterCache handles cache-related locking (delegated component)
    """
    # Check FilterManager has threading for singleton lock
    fm_source = read_source_file('src/core/filter_manager.py')
    assert 'import threading' in fm_source, 'Missing threading import in FilterManager'
    assert '_lock = threading.Lock()' in fm_source, 'Missing singleton _lock in FilterManager'

    # Check FilterCache has cache lock (Phase 2.1 delegation)
    cache_source = read_source_file('src/core/filter_cache.py')
    assert 'import threading' in cache_source, 'Missing threading import in FilterCache'
    assert '_cache_lock' in cache_source, 'Missing _cache_lock in FilterCache'
    assert 'with self._cache_lock:' in cache_source, 'Missing lock usage in FilterCache'


def test_ml_filter_integration_manager_thread_safety():
    """Test 2: Thread-Safety in MLFilterIntegrationManager"""
    source = read_source_file('src/core/ml_filter_integration_manager.py')
    assert 'import threading' in source, 'Missing threading import'
    assert '_cache_lock = threading.RLock()' in source, 'Missing _cache_lock initialization'
    assert 'def _evict_expired_cache' in source, 'Missing _evict_expired_cache method'
    assert 'def _evict_lru_if_needed' in source, 'Missing _evict_lru_if_needed method'


def test_cache_eviction_policy():
    """Test 3: Cache Eviction Logic"""
    source = read_source_file('src/core/ml_filter_integration_manager.py')
    assert 'current_time - data.get' in source and 'ttl' in source.lower(), 'TTL eviction logic missing'
    assert 'max_entries' in source and 'oldest_key' in source, 'LRU eviction logic missing'


def test_pattern_column_mapping():
    """Test 4: Pattern Column Mapping Logic"""
    source = read_source_file('src/core/specialized_databases.py')
    assert "'match': 'number_match_patterns'" in source, 'Missing match to number_match_patterns mapping'
    assert "'multiple_patterns': 'multiple_patterns'" in source, 'Missing multiple_patterns mapping'
    assert 'column_to_pattern_mapping' in source, 'Missing reverse mapping'
    assert 'pattern_column_mapping' in source, 'Missing pattern_column_mapping in get_pattern_statistics'


def test_geometric_sequence_zero_division():
    """Test 5: Geometric Sequence Division by Zero Prevention"""
    source = read_source_file('src/core/pattern_manager.py')
    assert 'EPSILON' in source, 'Should have EPSILON for floating-point comparison'
    has_zero_check = ('== 0' in source and ('continue' in source or 'last != 0' in source))
    assert has_zero_check, 'Should check for zero in geometric sequence'


def test_database_connection_manager_isolation():
    """Test 6: DatabaseConnectionManager isolation_level"""
    source = read_source_file('src/utils/db_connection_manager.py')
    assert "isolation_level='DEFERRED'" in source, 'Should use DEFERRED isolation level'
    assert 'RuntimeError' in source, 'Should catch RuntimeError for lock release'


def test_pattern_manager_log_fix():
    """Test 7: Pattern Manager _log_pattern_analysis fix"""
    source = read_source_file('src/core/pattern_manager.py')
    assert "patterns['match']" in source, 'Should access patterns["match"]'

    # Make sure number_match is NOT accessed directly (except in mapping contexts)
    lines = source.split('\n')
    bad_lines = []
    for i, line in enumerate(lines, 1):
        if "patterns['number_match']" in line:
            if 'mapping' not in line.lower() and 'column' not in line.lower():
                bad_lines.append(f"Line {i}: {line.strip()}")

    assert len(bad_lines) == 0, f'Should NOT access patterns["number_match"]: {bad_lines}'


def test_observer_failure_handling():
    """Test 8: Observer failure handling in DatabaseManager"""
    source = read_source_file('src/core/db_manager.py')
    assert 'failed_callbacks' in source, 'Missing failed_callbacks tracking'
    assert 'callbacks failed' in source.lower(), 'Missing failure summary logging'


# ==== Script Mode Execution ====

def run_script_mode():
    """Run tests in script mode with formatted output"""
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

    print('=' * 60)
    print('Comprehensive Test Suite for Bug Fixes')
    print('=' * 60)

    test_functions = [
        ('FilterManager Thread-Safety', test_filter_manager_thread_safety),
        ('MLFilterIntegrationManager Thread-Safety', test_ml_filter_integration_manager_thread_safety),
        ('Cache Eviction Policy', test_cache_eviction_policy),
        ('Pattern Column Mapping', test_pattern_column_mapping),
        ('Geometric Sequence No ZeroDivision', test_geometric_sequence_zero_division),
        ('DatabaseConnectionManager', test_database_connection_manager_isolation),
        ('Pattern Manager Log Fix', test_pattern_manager_log_fix),
        ('Observer Failure Handling', test_observer_failure_handling),
    ]

    test_results = []

    for i, (name, test_func) in enumerate(test_functions, 1):
        print(f'\n[Test {i}] {name}...')
        try:
            test_func()
            test_results.append((name, 'PASS'))
            print(f'  [O] {name} passed')
        except Exception as e:
            test_results.append((name, f'FAIL: {e}'))
            print(f'  [X] FAIL: {e}')

    # Summary
    print('\n' + '=' * 60)
    print('Test Summary')
    print('=' * 60)
    passed = sum(1 for _, r in test_results if r == 'PASS')
    failed = sum(1 for _, r in test_results if r != 'PASS')
    print(f'Passed: {passed}/{len(test_results)}')
    print(f'Failed: {failed}/{len(test_results)}')

    if failed > 0:
        print('\nFailed Tests:')
        for name, result in test_results:
            if result != 'PASS':
                print(f'  - {name}: {result}')
        return 1
    else:
        print('\n[SUCCESS] All tests passed!')
        return 0


if __name__ == '__main__':
    exit_code = run_script_mode()
    sys.exit(exit_code)
