#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시스템 유지보수 테스트

Phase 3.15: Cleanup 스크립트 개선
- 캐시 정리 자동화
- 오래된 백업 삭제
- DB vacuum 스케줄링
- 로그 아카이빙
"""

import pytest
import sys
import os
import time
import tempfile
import shutil
import sqlite3
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestBackupCleaner:
    """백업 정리 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리 생성"""
        tmpdir = tempfile.mkdtemp()
        project_root = Path(tmpdir)

        # 백업 디렉토리 생성
        backup_dir = project_root / 'configs' / 'backup'
        backup_dir.mkdir(parents=True)

        yield project_root

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_find_backup_files(self, temp_project):
        """백업 파일 찾기 테스트"""
        from src.scripts.system_maintenance import BackupCleaner

        # 테스트 백업 파일 생성
        backup_dir = temp_project / 'configs' / 'backup'
        (backup_dir / 'adaptive_filter_config_backup_20251201.yaml').touch()
        (backup_dir / 'config.bak').touch()
        (backup_dir / 'model_backup.pkl').touch()

        cleaner = BackupCleaner(temp_project)
        backup_files = cleaner.find_backup_files()

        assert len(backup_files) >= 2  # yaml과 bak 파일

    def test_backup_type_detection(self, temp_project):
        """백업 유형 감지 테스트"""
        from src.scripts.system_maintenance import BackupCleaner

        cleaner = BackupCleaner(temp_project)

        assert cleaner._get_backup_type(Path('adaptive_filter_config_backup.yaml')) == 'adaptive_filter_config'
        assert cleaner._get_backup_type(Path('config_backup.yaml')) == 'config'
        assert cleaner._get_backup_type(Path('model_backup.pkl')) == 'model'
        assert cleaner._get_backup_type(Path('data_backup.db')) == 'data'
        assert cleaner._get_backup_type(Path('unknown.bak')) == 'other'

    def test_select_files_for_deletion_by_age(self, temp_project):
        """나이 기반 삭제 대상 선택 테스트"""
        from src.scripts.system_maintenance import BackupCleaner

        cleaner = BackupCleaner(temp_project)
        cleaner.max_backup_age_days = 30

        backup_files = [
            {'path': Path('old.bak'), 'age_days': 35, 'type': 'other', 'modified_time': datetime.now() - timedelta(days=35)},
            {'path': Path('new.bak'), 'age_days': 5, 'type': 'other', 'modified_time': datetime.now() - timedelta(days=5)},
        ]

        to_delete = cleaner.select_files_for_deletion(backup_files)

        assert len(to_delete) == 1
        assert to_delete[0]['path'] == Path('old.bak')

    def test_select_files_for_deletion_by_count(self, temp_project):
        """개수 기반 삭제 대상 선택 테스트"""
        from src.scripts.system_maintenance import BackupCleaner

        cleaner = BackupCleaner(temp_project)
        cleaner.max_backups_per_type = 2
        cleaner.max_backup_age_days = 365  # 나이 기준은 무시

        backup_files = [
            {'path': Path('config1.bak'), 'age_days': 1, 'type': 'config', 'modified_time': datetime.now() - timedelta(days=1)},
            {'path': Path('config2.bak'), 'age_days': 2, 'type': 'config', 'modified_time': datetime.now() - timedelta(days=2)},
            {'path': Path('config3.bak'), 'age_days': 3, 'type': 'config', 'modified_time': datetime.now() - timedelta(days=3)},
        ]

        to_delete = cleaner.select_files_for_deletion(backup_files)

        # 최대 2개만 유지, 가장 오래된 1개 삭제
        assert len(to_delete) == 1
        assert to_delete[0]['path'] == Path('config3.bak')

    def test_cleanup_dry_run(self, temp_project):
        """Dry run 테스트"""
        from src.scripts.system_maintenance import BackupCleaner

        backup_dir = temp_project / 'configs' / 'backup'
        test_file = backup_dir / 'test_backup.bak'
        test_file.touch()

        # 파일 시간을 과거로 설정
        old_time = time.time() - (31 * 24 * 60 * 60)  # 31일 전
        os.utime(test_file, (old_time, old_time))

        cleaner = BackupCleaner(temp_project)
        result = cleaner.cleanup(dry_run=True)

        # 파일이 삭제되지 않아야 함
        assert test_file.exists()
        assert result['dry_run'] == True


class TestDatabaseVacuum:
    """데이터베이스 VACUUM 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리 생성"""
        tmpdir = tempfile.mkdtemp()
        project_root = Path(tmpdir)
        project_root.mkdir(exist_ok=True)

        yield project_root

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_get_database_stats(self, temp_project):
        """데이터베이스 통계 수집 테스트"""
        from src.scripts.system_maintenance import DatabaseVacuum

        # 테스트 데이터베이스 생성
        db_path = temp_project / 'test.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")
        for i in range(100):
            conn.execute("INSERT INTO test (data) VALUES (?)", (f"data_{i}",))
        conn.commit()
        conn.close()

        vacuum = DatabaseVacuum(temp_project)
        vacuum.db_paths = [db_path]

        stats = vacuum.get_database_stats(db_path)

        assert stats is not None
        assert stats['integrity'] == True
        assert stats['file_size_mb'] > 0

    def test_vacuum_database(self, temp_project):
        """단일 데이터베이스 VACUUM 테스트"""
        from src.scripts.system_maintenance import DatabaseVacuum

        # 테스트 데이터베이스 생성
        db_path = temp_project / 'test.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")

        # 데이터 추가 후 삭제 (조각화 유발)
        for i in range(1000):
            conn.execute("INSERT INTO test (data) VALUES (?)", (f"data_{i}" * 100,))
        conn.commit()
        conn.execute("DELETE FROM test WHERE id > 100")
        conn.commit()
        conn.close()

        vacuum = DatabaseVacuum(temp_project)
        vacuum.db_paths = [db_path]

        result = vacuum.vacuum_database(db_path)

        assert result['success'] == True
        assert result['size_before_mb'] > 0

    def test_vacuum_nonexistent_db(self, temp_project):
        """존재하지 않는 데이터베이스 VACUUM 테스트"""
        from src.scripts.system_maintenance import DatabaseVacuum

        vacuum = DatabaseVacuum(temp_project)
        result = vacuum.vacuum_database(temp_project / 'nonexistent.db')

        assert result['success'] == False


class TestLogArchiver:
    """로그 아카이빙 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리 생성"""
        tmpdir = tempfile.mkdtemp()
        project_root = Path(tmpdir)

        # 로그 디렉토리 생성
        log_dir = project_root / 'logs'
        log_dir.mkdir(parents=True)

        yield project_root

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_find_logs_to_archive(self, temp_project):
        """아카이빙 대상 로그 찾기 테스트"""
        from src.scripts.system_maintenance import LogArchiver

        log_dir = temp_project / 'logs'

        # 오래된 로그 생성
        old_log = log_dir / 'old.log'
        old_log.write_text("old log content")
        old_time = time.time() - (8 * 24 * 60 * 60)  # 8일 전
        os.utime(old_log, (old_time, old_time))

        # 새 로그 생성
        new_log = log_dir / 'new.log'
        new_log.write_text("new log content")

        archiver = LogArchiver(temp_project)
        archiver.max_log_age_days = 7

        logs_to_archive = archiver.find_logs_to_archive()

        assert len(logs_to_archive) == 1
        assert logs_to_archive[0].name == 'old.log'

    def test_archive_log_compressed(self, temp_project):
        """로그 압축 아카이빙 테스트"""
        from src.scripts.system_maintenance import LogArchiver

        log_dir = temp_project / 'logs'
        test_log = log_dir / 'test.log'
        test_log.write_text("test log content\n" * 100)

        archiver = LogArchiver(temp_project)
        archiver.compress_archives = True

        result = archiver.archive_log(test_log)

        assert result == True
        assert not test_log.exists()  # 원본 삭제됨
        assert (temp_project / 'logs' / 'archive').exists()

        # 압축 파일 확인
        archives = list((temp_project / 'logs' / 'archive').glob('*.gz'))
        assert len(archives) == 1

        # 압축 해제 확인
        with gzip.open(archives[0], 'rt') as f:
            content = f.read()
        assert 'test log content' in content

    def test_cleanup_old_archives(self, temp_project):
        """오래된 아카이브 삭제 테스트"""
        from src.scripts.system_maintenance import LogArchiver

        archive_dir = temp_project / 'logs' / 'archive'
        archive_dir.mkdir(parents=True)

        # 오래된 아카이브 생성
        old_archive = archive_dir / 'old.gz'
        old_archive.touch()
        old_time = time.time() - (35 * 24 * 60 * 60)  # 35일 전
        os.utime(old_archive, (old_time, old_time))

        # 새 아카이브 생성
        new_archive = archive_dir / 'new.gz'
        new_archive.touch()

        archiver = LogArchiver(temp_project)
        archiver.max_archive_age_days = 30

        deleted_count = archiver.cleanup_old_archives()

        assert deleted_count == 1
        assert not old_archive.exists()
        assert new_archive.exists()


class TestSystemMaintenance:
    """시스템 유지보수 통합 테스트"""

    @pytest.fixture
    def temp_project(self):
        """임시 프로젝트 디렉토리 생성"""
        tmpdir = tempfile.mkdtemp()
        project_root = Path(tmpdir)

        # 필요한 디렉토리 생성
        (project_root / 'configs' / 'backup').mkdir(parents=True)
        (project_root / 'logs').mkdir(parents=True)
        (project_root / 'data').mkdir(parents=True)

        yield project_root

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_maintenance_status(self, temp_project):
        """유지보수 상태 확인 테스트"""
        from src.scripts.system_maintenance import SystemMaintenance

        maintenance = SystemMaintenance(temp_project)
        status = maintenance.get_maintenance_status()

        assert 'last_run' in status
        assert 'needs_maintenance' in status
        assert status['needs_maintenance'] == True  # 처음 실행 전

    def test_run_full_maintenance_dry_run(self, temp_project):
        """전체 유지보수 dry run 테스트"""
        from src.scripts.system_maintenance import SystemMaintenance

        maintenance = SystemMaintenance(temp_project)
        result = maintenance.run_full_maintenance(dry_run=True)

        assert 'backup_cleanup' in result
        assert 'db_vacuum' in result
        assert 'log_archive' in result
        assert 'elapsed_seconds' in result

    def test_state_persistence(self, temp_project):
        """상태 저장/로드 테스트"""
        from src.scripts.system_maintenance import SystemMaintenance

        maintenance = SystemMaintenance(temp_project)

        # 상태 저장
        test_state = {
            'last_run': {
                'timestamp': datetime.now().isoformat(),
                'results': {'test': 'value'}
            },
            'history': []
        }
        maintenance._save_state(test_state)

        # 상태 로드
        loaded_state = maintenance._load_state()

        assert 'last_run' in loaded_state
        assert loaded_state['last_run']['results']['test'] == 'value'


class TestMaintenanceLogic:
    """유지보수 로직 단위 테스트"""

    def test_backup_file_sorting(self):
        """백업 파일 정렬 로직 테스트"""
        files = [
            {'modified_time': datetime(2025, 1, 3), 'type': 'config'},
            {'modified_time': datetime(2025, 1, 1), 'type': 'config'},
            {'modified_time': datetime(2025, 1, 2), 'type': 'config'},
        ]

        # 최신순 정렬
        sorted_files = sorted(files, key=lambda x: x['modified_time'], reverse=True)

        assert sorted_files[0]['modified_time'] == datetime(2025, 1, 3)
        assert sorted_files[-1]['modified_time'] == datetime(2025, 1, 1)

    def test_age_calculation(self):
        """파일 나이 계산 로직 테스트"""
        from datetime import datetime, timedelta

        # 10일 전 파일
        file_time = datetime.now() - timedelta(days=10)
        age_days = (datetime.now() - file_time).days

        assert age_days == 10

    def test_size_calculation(self):
        """크기 계산 로직 테스트"""
        bytes_size = 1536 * 1024 * 1024  # 1.5 GB
        mb = bytes_size / (1024 * 1024)
        gb = bytes_size / (1024 ** 3)

        assert mb == 1536
        assert gb == 1.5


class TestCacheCleanerIntegration:
    """캐시 정리 통합 테스트 (기존 auto_cache_cleaner.py)"""

    def test_auto_cache_cleaner_import(self):
        """auto_cache_cleaner 모듈 임포트 테스트"""
        from src.scripts.auto_cache_cleaner import AutoCacheCleaner

        assert AutoCacheCleaner is not None

    def test_cache_cleaner_initialization(self):
        """캐시 정리 초기화 테스트"""
        from src.scripts.auto_cache_cleaner import AutoCacheCleaner

        with tempfile.TemporaryDirectory() as tmpdir:
            cleaner = AutoCacheCleaner(tmpdir)

            assert cleaner.max_cache_size_gb == 1.5
            assert cleaner.max_file_age_days == 7

    def test_cache_size_calculation(self):
        """캐시 크기 계산 테스트"""
        from src.scripts.auto_cache_cleaner import AutoCacheCleaner

        with tempfile.TemporaryDirectory() as tmpdir:
            # 테스트 파일 생성
            cache_dir = Path(tmpdir) / 'cache' / 'models'
            cache_dir.mkdir(parents=True)
            test_file = cache_dir / 'test.pkl'
            test_file.write_bytes(b'x' * 1024)  # 1KB

            cleaner = AutoCacheCleaner(tmpdir)
            cleaner.cache_dirs = {'models': cache_dir}

            size = cleaner.get_total_cache_size()
            assert size >= 1024


class TestScheduleIntegration:
    """스케줄 통합 테스트"""

    def test_schedule_setup(self):
        """스케줄 설정 테스트"""
        import schedule

        # 스케줄 클리어
        schedule.clear()

        # 테스트 작업 등록
        schedule.every().day.at("04:00").do(lambda: None)

        jobs = schedule.get_jobs()
        assert len(jobs) == 1

        # 클리어
        schedule.clear()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
