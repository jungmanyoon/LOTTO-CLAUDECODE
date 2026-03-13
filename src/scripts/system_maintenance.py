#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시스템 유지보수 종합 스크립트

Phase 3.15: Cleanup 스크립트 개선
- 캐시 정리 자동화
- 오래된 백업 삭제
- DB vacuum 스케줄링
- 로그 아카이빙
"""
import os
import sys
import shutil
import logging
import sqlite3
import gzip
import schedule
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import setup_logging


class BackupCleaner:
    """백업 파일 정리 클래스"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

        # 백업 디렉토리들
        self.backup_dirs = [
            project_root / 'configs' / 'backup',
            project_root / 'backup',
            project_root / 'data' / 'backup',
        ]

        # 백업 파일 패턴
        self.backup_patterns = [
            '*_backup_*.yaml',
            '*.backup_*',
            '*.bak',
            '*_backup.*',
        ]

        # 설정
        self.max_backups_per_type = 5  # 유형별 최대 보관 개수
        self.max_backup_age_days = 30  # 최대 보관 일수

    def find_backup_files(self) -> List[Dict]:
        """모든 백업 파일 찾기"""
        backup_files = []

        for backup_dir in self.backup_dirs:
            if not backup_dir.exists():
                continue

            for pattern in self.backup_patterns:
                for file_path in backup_dir.glob(pattern):
                    if file_path.is_file():
                        try:
                            stat = file_path.stat()
                            backup_files.append({
                                'path': file_path,
                                'size': stat.st_size,
                                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                                'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
                                'type': self._get_backup_type(file_path)
                            })
                        except (OSError, IOError) as e:
                            self.logger.warning(f"백업 파일 정보 수집 실패: {file_path}, {e}")

        return backup_files

    def _get_backup_type(self, file_path: Path) -> str:
        """백업 파일 유형 추출"""
        name = file_path.name
        if 'adaptive_filter_config' in name:
            return 'adaptive_filter_config'
        elif 'config' in name:
            return 'config'
        elif 'model' in name:
            return 'model'
        elif 'data' in name:
            return 'data'
        else:
            return 'other'

    def select_files_for_deletion(self, backup_files: List[Dict]) -> List[Dict]:
        """삭제할 백업 파일 선택"""
        files_to_delete = []

        # 1. 오래된 파일 (30일 이상)
        for file_info in backup_files:
            if file_info['age_days'] >= self.max_backup_age_days:
                files_to_delete.append(file_info)

        # 2. 유형별 최대 개수 초과 파일
        by_type = {}
        for file_info in backup_files:
            backup_type = file_info['type']
            if backup_type not in by_type:
                by_type[backup_type] = []
            by_type[backup_type].append(file_info)

        for backup_type, files in by_type.items():
            # 최신순 정렬
            files.sort(key=lambda x: x['modified_time'], reverse=True)

            # 최대 개수 초과분 삭제 대상
            if len(files) > self.max_backups_per_type:
                excess = files[self.max_backups_per_type:]
                for file_info in excess:
                    if file_info not in files_to_delete:
                        files_to_delete.append(file_info)

        return files_to_delete

    def cleanup(self, dry_run: bool = False) -> Dict:
        """백업 파일 정리 실행"""
        self.logger.info("백업 파일 정리 시작")

        backup_files = self.find_backup_files()
        self.logger.info(f"발견된 백업 파일: {len(backup_files)}개")

        files_to_delete = self.select_files_for_deletion(backup_files)
        self.logger.info(f"삭제 대상: {len(files_to_delete)}개")

        deleted_count = 0
        deleted_size = 0

        for file_info in files_to_delete:
            if dry_run:
                self.logger.info(f"[DRY RUN] 삭제 예정: {file_info['path']} ({file_info['age_days']}일 전)")
            else:
                try:
                    file_info['path'].unlink()
                    deleted_count += 1
                    deleted_size += file_info['size']
                    self.logger.info(f"삭제됨: {file_info['path'].name}")
                except Exception as e:
                    self.logger.error(f"삭제 실패: {file_info['path']}, {e}")

        return {
            'total_files': len(backup_files),
            'deleted_count': deleted_count if not dry_run else len(files_to_delete),
            'deleted_size_mb': deleted_size / (1024 * 1024),
            'dry_run': dry_run
        }


class DatabaseVacuum:
    """데이터베이스 VACUUM 및 최적화"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

        # 데이터베이스 파일 위치
        self.db_paths = [
            project_root / 'lotto_numbers.db',
            project_root / 'combinations.db',
            project_root / 'predictions.db',
            project_root / 'performance_stats.db',
            project_root / 'backtest_results.db',
            project_root / 'threshold_optimization.db',
        ]

        # 필터 DB들
        filters_dir = project_root / 'filters'
        if filters_dir.exists():
            self.db_paths.extend(list(filters_dir.glob('*.db')))

    def get_database_stats(self, db_path: Path) -> Optional[Dict]:
        """데이터베이스 통계 수집"""
        if not db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 파일 크기
            file_size = db_path.stat().st_size

            # 페이지 정보
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]

            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]

            cursor.execute("PRAGMA freelist_count")
            freelist_count = cursor.fetchone()[0]

            # 무결성 검사
            cursor.execute("PRAGMA integrity_check(1)")
            integrity = cursor.fetchone()[0]

            conn.close()

            return {
                'path': db_path,
                'file_size_mb': file_size / (1024 * 1024),
                'page_count': page_count,
                'page_size': page_size,
                'freelist_count': freelist_count,
                'fragmentation_ratio': freelist_count / max(page_count, 1),
                'integrity': integrity == 'ok'
            }
        except Exception as e:
            self.logger.error(f"데이터베이스 통계 수집 실패: {db_path}, {e}")
            return None

    def vacuum_database(self, db_path: Path) -> Dict:
        """단일 데이터베이스 VACUUM 실행"""
        result = {
            'path': db_path,
            'success': False,
            'size_before_mb': 0,
            'size_after_mb': 0,
            'saved_mb': 0
        }

        if not db_path.exists():
            return result

        try:
            # 이전 크기
            size_before = db_path.stat().st_size
            result['size_before_mb'] = size_before / (1024 * 1024)

            # 연결 및 VACUUM
            conn = sqlite3.connect(str(db_path))

            # WAL 체크포인트
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

            # VACUUM 실행
            conn.execute("VACUUM")

            # ANALYZE 실행
            conn.execute("ANALYZE")

            conn.close()

            # 이후 크기
            size_after = db_path.stat().st_size
            result['size_after_mb'] = size_after / (1024 * 1024)
            result['saved_mb'] = (size_before - size_after) / (1024 * 1024)
            result['success'] = True

            self.logger.info(f"VACUUM 완료: {db_path.name} ({result['size_before_mb']:.2f} MB -> {result['size_after_mb']:.2f} MB)")

        except Exception as e:
            self.logger.error(f"VACUUM 실패: {db_path}, {e}")

        return result

    def vacuum_all(self, parallel: bool = True) -> Dict:
        """모든 데이터베이스 VACUUM 실행"""
        self.logger.info("데이터베이스 VACUUM 시작")

        existing_dbs = [db for db in self.db_paths if db.exists()]
        self.logger.info(f"대상 데이터베이스: {len(existing_dbs)}개")

        results = []

        if parallel:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.vacuum_database, db): db for db in existing_dbs}
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for db_path in existing_dbs:
                results.append(self.vacuum_database(db_path))

        # 집계
        total_saved = sum(r['saved_mb'] for r in results)
        success_count = sum(1 for r in results if r['success'])

        return {
            'total_databases': len(existing_dbs),
            'success_count': success_count,
            'total_saved_mb': total_saved,
            'details': results
        }


class LogArchiver:
    """로그 파일 아카이빙"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

        # 로그 디렉토리
        self.log_dir = project_root / 'logs'
        self.archive_dir = project_root / 'logs' / 'archive'

        # 설정
        self.max_log_age_days = 7  # 아카이빙 대상 나이
        self.max_archive_age_days = 30  # 아카이브 보관 기간
        self.compress_archives = True

    def find_logs_to_archive(self) -> List[Path]:
        """아카이빙할 로그 파일 찾기"""
        logs_to_archive = []

        if not self.log_dir.exists():
            return logs_to_archive

        for log_file in self.log_dir.glob('*.log*'):
            if log_file.is_file() and 'archive' not in str(log_file):
                try:
                    stat = log_file.stat()
                    age_days = (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days

                    if age_days >= self.max_log_age_days:
                        logs_to_archive.append(log_file)
                except (OSError, IOError):
                    continue

        return logs_to_archive

    def archive_log(self, log_path: Path) -> bool:
        """단일 로그 파일 아카이빙"""
        try:
            # 아카이브 디렉토리 생성
            self.archive_dir.mkdir(parents=True, exist_ok=True)

            # 아카이브 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"{log_path.stem}_{timestamp}"

            if self.compress_archives:
                archive_path = self.archive_dir / f"{archive_name}.gz"
                with open(log_path, 'rb') as f_in:
                    with gzip.open(archive_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                archive_path = self.archive_dir / f"{archive_name}.log"
                shutil.copy2(log_path, archive_path)

            # 원본 삭제
            log_path.unlink()

            self.logger.info(f"아카이브됨: {log_path.name} -> {archive_path.name}")
            return True

        except Exception as e:
            self.logger.error(f"아카이브 실패: {log_path}, {e}")
            return False

    def cleanup_old_archives(self) -> int:
        """오래된 아카이브 삭제"""
        deleted_count = 0

        if not self.archive_dir.exists():
            return deleted_count

        for archive_file in self.archive_dir.iterdir():
            if archive_file.is_file():
                try:
                    stat = archive_file.stat()
                    age_days = (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days

                    if age_days >= self.max_archive_age_days:
                        archive_file.unlink()
                        deleted_count += 1
                        self.logger.info(f"오래된 아카이브 삭제: {archive_file.name}")
                except Exception as e:
                    self.logger.error(f"아카이브 삭제 실패: {archive_file}, {e}")

        return deleted_count

    def archive_all(self) -> Dict:
        """모든 로그 아카이빙 실행"""
        self.logger.info("로그 아카이빙 시작")

        # 아카이빙할 로그 찾기
        logs_to_archive = self.find_logs_to_archive()
        self.logger.info(f"아카이빙 대상: {len(logs_to_archive)}개")

        archived_count = 0
        for log_path in logs_to_archive:
            if self.archive_log(log_path):
                archived_count += 1

        # 오래된 아카이브 정리
        deleted_archives = self.cleanup_old_archives()

        return {
            'logs_found': len(logs_to_archive),
            'archived_count': archived_count,
            'deleted_archives': deleted_archives
        }


class SystemMaintenance:
    """시스템 유지보수 통합 관리자"""

    def __init__(self, project_root: Path = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent

        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

        # 컴포넌트 초기화
        self.backup_cleaner = BackupCleaner(project_root)
        self.db_vacuum = DatabaseVacuum(project_root)
        self.log_archiver = LogArchiver(project_root)

        # 상태 파일
        self.state_file = project_root / 'data' / 'maintenance_state.json'

    def _load_state(self) -> Dict:
        """유지보수 상태 로드"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {'last_run': {}, 'history': []}

    def _save_state(self, state: Dict):
        """유지보수 상태 저장"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            self.logger.error(f"상태 저장 실패: {e}")

    def run_full_maintenance(self, dry_run: bool = False) -> Dict:
        """전체 유지보수 실행"""
        self.logger.info("=" * 60)
        self.logger.info("시스템 유지보수 시작")
        self.logger.info("=" * 60)

        start_time = datetime.now()
        results = {}

        # 1. 백업 정리
        self.logger.info("\n[1/3] 백업 파일 정리")
        results['backup_cleanup'] = self.backup_cleaner.cleanup(dry_run=dry_run)

        # 2. 데이터베이스 VACUUM
        self.logger.info("\n[2/3] 데이터베이스 최적화")
        if not dry_run:
            results['db_vacuum'] = self.db_vacuum.vacuum_all()
        else:
            results['db_vacuum'] = {'dry_run': True, 'message': 'VACUUM 스킵됨 (dry_run)'}

        # 3. 로그 아카이빙
        self.logger.info("\n[3/3] 로그 아카이빙")
        if not dry_run:
            results['log_archive'] = self.log_archiver.archive_all()
        else:
            results['log_archive'] = {'dry_run': True, 'message': '아카이빙 스킵됨 (dry_run)'}

        # 실행 시간
        elapsed = (datetime.now() - start_time).total_seconds()
        results['elapsed_seconds'] = elapsed

        # 상태 저장
        if not dry_run:
            state = self._load_state()
            state['last_run'] = {
                'timestamp': datetime.now().isoformat(),
                'results': results
            }
            # 최근 10개 기록만 유지
            state['history'].append(state['last_run'])
            state['history'] = state['history'][-10:]
            self._save_state(state)

        # 결과 로깅
        self.logger.info("\n" + "=" * 60)
        self.logger.info("시스템 유지보수 완료")
        self.logger.info("=" * 60)
        self.logger.info(f"실행 시간: {elapsed:.2f}초")

        return results

    def get_maintenance_status(self) -> Dict:
        """유지보수 상태 확인"""
        state = self._load_state()

        # 마지막 실행 시간 계산
        last_run = state.get('last_run', {})
        last_timestamp = last_run.get('timestamp')

        days_since_last = None
        if last_timestamp:
            last_dt = datetime.fromisoformat(last_timestamp)
            days_since_last = (datetime.now() - last_dt).days

        return {
            'last_run': last_timestamp,
            'days_since_last': days_since_last,
            'needs_maintenance': days_since_last is None or days_since_last >= 1,
            'history_count': len(state.get('history', []))
        }


def setup_scheduled_maintenance():
    """스케줄 유지보수 설정"""
    maintenance = SystemMaintenance()

    # 매일 새벽 4시에 실행
    schedule.every().day.at("04:00").do(maintenance.run_full_maintenance)

    logging.info("유지보수 스케줄 설정됨: 매일 04:00")

    return schedule


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='시스템 유지보수 스크립트')
    parser.add_argument('--full', action='store_true', help='전체 유지보수 실행')
    parser.add_argument('--backup', action='store_true', help='백업 정리만 실행')
    parser.add_argument('--vacuum', action='store_true', help='DB VACUUM만 실행')
    parser.add_argument('--archive', action='store_true', help='로그 아카이빙만 실행')
    parser.add_argument('--status', action='store_true', help='유지보수 상태 확인')
    parser.add_argument('--dry-run', action='store_true', help='실제 삭제 없이 미리보기')
    parser.add_argument('--schedule', action='store_true', help='스케줄 실행 모드')

    args = parser.parse_args()

    # 로깅 설정
    setup_logging()

    maintenance = SystemMaintenance()

    if args.status:
        status = maintenance.get_maintenance_status()
        print("\n[STATUS] 유지보수 상태")
        print(f"   마지막 실행: {status['last_run'] or '없음'}")
        if status['days_since_last'] is not None:
            print(f"   경과 일수: {status['days_since_last']}일")
        print(f"   유지보수 필요: {'예' if status['needs_maintenance'] else '아니오'}")
        print(f"   실행 기록: {status['history_count']}건")

    elif args.backup:
        result = maintenance.backup_cleaner.cleanup(dry_run=args.dry_run)
        print(f"\n[BACKUP] 백업 정리 완료")
        print(f"   전체 파일: {result['total_files']}개")
        print(f"   삭제됨: {result['deleted_count']}개")
        print(f"   정리된 용량: {result['deleted_size_mb']:.2f} MB")

    elif args.vacuum:
        result = maintenance.db_vacuum.vacuum_all()
        print(f"\n[VACUUM] 데이터베이스 최적화 완료")
        print(f"   대상 DB: {result['total_databases']}개")
        print(f"   성공: {result['success_count']}개")
        print(f"   절약된 용량: {result['total_saved_mb']:.2f} MB")

    elif args.archive:
        result = maintenance.log_archiver.archive_all()
        print(f"\n[ARCHIVE] 로그 아카이빙 완료")
        print(f"   아카이브됨: {result['archived_count']}개")
        print(f"   삭제된 아카이브: {result['deleted_archives']}개")

    elif args.schedule:
        print("[SCHEDULE] 유지보수 스케줄 모드 시작 (Ctrl+C로 종료)")
        setup_scheduled_maintenance()
        while True:
            schedule.run_pending()
            time.sleep(60)

    elif args.full or not any([args.backup, args.vacuum, args.archive, args.status, args.schedule]):
        result = maintenance.run_full_maintenance(dry_run=args.dry_run)
        print(f"\n[FULL] 전체 유지보수 완료 (실행시간: {result['elapsed_seconds']:.2f}초)")


if __name__ == "__main__":
    main()
