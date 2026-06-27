#!/usr/bin/env python3
"""
자동 캐시 정리 시스템
- 캐시 크기 모니터링 (1.5GB 초과시 자동 정리)
- 나이 기반 정리 (7일 이상 된 파일 삭제)
- 스마트 정리 (사용 빈도 기반 보존)
- 주기적 실행 지원
"""
import os
import shutil
import logging
import sys
import time
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 프로젝트 루트를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.logger import setup_logging


class AutoCacheCleaner:
    """자동 캐시 정리 시스템"""

    def __init__(self, project_root: str = None):
        """
        초기화

        Args:
            project_root: 프로젝트 루트 경로
        """
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        self.project_root = Path(project_root)

        # 캐시 디렉토리 설정
        self.cache_dirs = {
            'models': self.project_root / 'cache' / 'models',
            'filtered_combinations': self.project_root / 'cache' / 'filtered_combinations',
            'filters': self.project_root / 'cache' / 'filters',
            'ensemble_models': self.project_root / 'models' / 'ensemble'
        }

        # 설정값
        self.max_cache_size_gb = 1.5  # 최대 캐시 크기 (GB)
        self.max_file_age_days = 7    # 최대 파일 보관 일수
        self.usage_tracking_file = self.project_root / 'cache' / 'usage_tracker.json'

        # 사용량 추적 데이터
        self.usage_data = self._load_usage_data()

        # 로깅 설정
        setup_logging()
        self.logger = logging.getLogger(__name__)

    def _load_usage_data(self) -> Dict:
        """사용량 추적 데이터 로드"""
        if self.usage_tracking_file.exists():
            try:
                with open(self.usage_tracking_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                return {'file_access_count': {}, 'last_cleanup': None}
        return {'file_access_count': {}, 'last_cleanup': None}

    def _save_usage_data(self):
        """사용량 추적 데이터 저장"""
        try:
            self.usage_tracking_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_tracking_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"사용량 데이터 저장 실패: {e}")

    def track_file_access(self, file_path: str):
        """파일 접근 추적 (외부에서 호출)"""
        file_key = str(Path(file_path).relative_to(self.project_root))

        if file_key not in self.usage_data['file_access_count']:
            self.usage_data['file_access_count'][file_key] = 0

        self.usage_data['file_access_count'][file_key] += 1
        self._save_usage_data()

    def get_directory_size(self, directory: Path) -> int:
        """디렉토리 크기 계산 (bytes)"""
        total_size = 0
        if directory.exists():
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    try:
                        total_size += file_path.stat().st_size
                    except (OSError, IOError):
                        continue
        return total_size

    def get_total_cache_size(self) -> int:
        """전체 캐시 크기 계산 (bytes)"""
        total_size = 0
        for cache_dir in self.cache_dirs.values():
            total_size += self.get_directory_size(cache_dir)
        # [코드리뷰 2026-06-27 P2] cache/ 루트 직속 npz(극단풀 디스크 캐시)도 합산.
        # cache_dirs에 없어 캐시크기 로그가 과소보고되던 것을 교정(하위 디렉토리 중복 없음).
        cache_root = self.project_root / 'cache'
        if cache_root.exists():
            for f in cache_root.glob('*.npz'):
                try:
                    total_size += f.stat().st_size
                except (OSError, IOError):
                    continue
        return total_size

    def get_file_info(self, file_path: Path) -> Dict:
        """파일 정보 수집"""
        try:
            stat = file_path.stat()
            file_key = str(file_path.relative_to(self.project_root))
            access_count = self.usage_data['file_access_count'].get(file_key, 0)

            return {
                'path': file_path,
                'size': stat.st_size,
                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                'access_count': access_count,
                'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
            }
        except Exception as e:
            self.logger.warning(f"파일 정보 수집 실패 {file_path}: {e}")
            return None

    def collect_cache_files(self) -> List[Dict]:
        """모든 캐시 파일 정보 수집"""
        all_files = []

        for cache_name, cache_dir in self.cache_dirs.items():
            if cache_dir.exists():
                for file_path in cache_dir.rglob('*'):
                    if file_path.is_file():
                        file_info = self.get_file_info(file_path)
                        if file_info:
                            file_info['cache_type'] = cache_name
                            all_files.append(file_info)

        # [코드리뷰 2026-06-27 P2] cache/ 루트 직속 npz(극단풀 디스크 캐시)는 cache_dirs에
        # 없어 7일/용량 정리에서 누락돼 영구 누적됐다. 하위 디렉토리 중복 없이 직속 .npz만 수집.
        cache_root = self.project_root / 'cache'
        if cache_root.exists():
            for file_path in cache_root.glob('*.npz'):
                if file_path.is_file():
                    file_info = self.get_file_info(file_path)
                    if file_info:
                        file_info['cache_type'] = 'extremeness_pool'
                        all_files.append(file_info)

        return all_files

    def should_cleanup_by_size(self) -> bool:
        """크기 기준 정리 필요 여부 확인"""
        total_size_gb = self.get_total_cache_size() / (1024**3)
        return total_size_gb > self.max_cache_size_gb

    def should_cleanup_by_time(self) -> bool:
        """시간 기준 정리 필요 여부 확인"""
        last_cleanup = self.usage_data.get('last_cleanup')
        if not last_cleanup:
            return True

        last_cleanup_date = datetime.fromisoformat(last_cleanup)
        return (datetime.now() - last_cleanup_date).days >= 1  # 매일 체크

    def select_files_for_deletion(self, files: List[Dict]) -> List[Dict]:
        """삭제할 파일 선택 (스마트 알고리즘)"""
        files_to_delete = []

        # 1. 오래된 파일 (7일 이상)
        old_files = [f for f in files if f['age_days'] >= self.max_file_age_days]
        files_to_delete.extend(old_files)

        # 2. 크기가 클 경우 추가 정리
        if self.should_cleanup_by_size():
            remaining_files = [f for f in files if f not in files_to_delete]

            # 사용 빈도가 낮은 파일부터 정리 (액세스 카운트 기준)
            remaining_files.sort(key=lambda x: (x['access_count'], -x['age_days']))

            current_size = sum(f['size'] for f in files)
            target_size = int(self.max_cache_size_gb * 0.8 * (1024**3))  # 80%까지 줄이기

            deleted_size = sum(f['size'] for f in files_to_delete)

            for file_info in remaining_files:
                if current_size - deleted_size <= target_size:
                    break

                # 중요한 파일은 보호 (최근 1일 내 사용된 파일)
                if (file_info['access_count'] > 0 and
                    file_info['age_days'] < 1):
                    continue

                files_to_delete.append(file_info)
                deleted_size += file_info['size']

        return files_to_delete

    def delete_files(self, files_to_delete: List[Dict]) -> Tuple[int, int]:
        """파일 삭제 실행"""
        deleted_count = 0
        deleted_size = 0

        for file_info in files_to_delete:
            try:
                file_path = file_info['path']
                file_size = file_info['size']

                file_path.unlink()
                deleted_count += 1
                deleted_size += file_size

                self.logger.info(f"삭제됨: {file_path.name} ({file_size/1024/1024:.2f} MB)")

                # 사용량 추적에서도 제거
                file_key = str(file_path.relative_to(self.project_root))
                if file_key in self.usage_data['file_access_count']:
                    del self.usage_data['file_access_count'][file_key]

            except Exception as e:
                self.logger.error(f"파일 삭제 실패 {file_info['path']}: {e}")

        return deleted_count, deleted_size

    def cleanup_empty_directories(self):
        """빈 디렉토리 정리"""
        for cache_dir in self.cache_dirs.values():
            if cache_dir.exists():
                for root, dirs, files in os.walk(cache_dir, topdown=False):
                    root_path = Path(root)
                    if not files and not dirs and root_path != cache_dir:
                        try:
                            root_path.rmdir()
                            self.logger.info(f"빈 디렉토리 삭제: {root_path}")
                        except Exception as e:
                            self.logger.warning(f"디렉토리 삭제 실패 {root_path}: {e}")

    def run_cleanup(self, force: bool = False) -> Dict:
        """캐시 정리 실행"""
        self.logger.info("="*60)
        self.logger.info("자동 캐시 정리 시작")
        self.logger.info("="*60)

        # 현재 상태 확인
        total_size_gb = self.get_total_cache_size() / (1024**3)
        self.logger.info(f"현재 캐시 크기: {total_size_gb:.2f} GB")

        # 정리 필요 여부 확인
        need_cleanup = force or self.should_cleanup_by_size() or self.should_cleanup_by_time()

        if not need_cleanup:
            self.logger.info("정리가 필요하지 않습니다.")
            return {
                'cleaned': False,
                'deleted_files': 0,
                'deleted_size_mb': 0,
                'total_size_gb': total_size_gb
            }

        # 파일 정보 수집
        all_files = self.collect_cache_files()
        self.logger.info(f"총 {len(all_files)}개 파일 발견")

        # 삭제할 파일 선택
        files_to_delete = self.select_files_for_deletion(all_files)

        if not files_to_delete:
            self.logger.info("삭제할 파일이 없습니다.")
            return {
                'cleaned': False,
                'deleted_files': 0,
                'deleted_size_mb': 0,
                'total_size_gb': total_size_gb
            }

        self.logger.info(f"삭제 예정 파일: {len(files_to_delete)}개")

        # 삭제 실행
        deleted_count, deleted_size = self.delete_files(files_to_delete)

        # 빈 디렉토리 정리
        self.cleanup_empty_directories()

        # 정리 완료 시간 기록
        self.usage_data['last_cleanup'] = datetime.now().isoformat()
        self._save_usage_data()

        # 최종 크기 확인
        final_size_gb = self.get_total_cache_size() / (1024**3)

        # 결과 로깅
        self.logger.info("\n" + "="*60)
        self.logger.info("캐시 정리 완료")
        self.logger.info("="*60)
        self.logger.info(f"삭제된 파일: {deleted_count}개")
        self.logger.info(f"정리된 용량: {deleted_size/1024/1024:.2f} MB")
        self.logger.info(f"정리 전 크기: {total_size_gb:.2f} GB")
        self.logger.info(f"정리 후 크기: {final_size_gb:.2f} GB")

        return {
            'cleaned': True,
            'deleted_files': deleted_count,
            'deleted_size_mb': deleted_size/1024/1024,
            'total_size_gb': final_size_gb,
            'size_before_gb': total_size_gb
        }

    def get_cache_status(self) -> Dict:
        """캐시 상태 정보 반환"""
        total_size_gb = self.get_total_cache_size() / (1024**3)
        all_files = self.collect_cache_files()

        # 디렉토리별 크기
        dir_sizes = {}
        for cache_name, cache_dir in self.cache_dirs.items():
            size_gb = self.get_directory_size(cache_dir) / (1024**3)
            dir_sizes[cache_name] = size_gb

        # 오래된 파일 수
        old_files = len([f for f in all_files if f['age_days'] >= self.max_file_age_days])

        return {
            'total_size_gb': total_size_gb,
            'max_size_gb': self.max_cache_size_gb,
            'usage_percentage': (total_size_gb / self.max_cache_size_gb) * 100,
            'total_files': len(all_files),
            'old_files': old_files,
            'directory_sizes': dir_sizes,
            'needs_cleanup': self.should_cleanup_by_size(),
            'last_cleanup': self.usage_data.get('last_cleanup')
        }


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='자동 캐시 정리 시스템')
    parser.add_argument('--force', action='store_true', help='강제 정리 실행')
    parser.add_argument('--status', action='store_true', help='캐시 상태만 확인')
    parser.add_argument('--max-size', type=float, default=1.5, help='최대 캐시 크기 (GB)')
    parser.add_argument('--max-age', type=int, default=7, help='최대 파일 보관 일수')

    args = parser.parse_args()

    # 정리 시스템 초기화
    cleaner = AutoCacheCleaner()
    cleaner.max_cache_size_gb = args.max_size
    cleaner.max_file_age_days = args.max_age

    if args.status:
        # 상태만 확인
        status = cleaner.get_cache_status()
        print(f"\n[STATUS] 캐시 상태:")
        print(f"   전체 크기: {status['total_size_gb']:.2f} GB / {status['max_size_gb']:.2f} GB")
        print(f"   사용률: {status['usage_percentage']:.1f}%")
        print(f"   전체 파일: {status['total_files']}개")
        print(f"   오래된 파일: {status['old_files']}개")
        print(f"   정리 필요: {'예' if status['needs_cleanup'] else '아니오'}")

        if status['directory_sizes']:
            print(f"\n[DIRS] 디렉토리별 크기:")
            for dir_name, size_gb in status['directory_sizes'].items():
                print(f"   {dir_name}: {size_gb:.2f} GB")

        if status['last_cleanup']:
            last_cleanup = datetime.fromisoformat(status['last_cleanup'])
            print(f"\n[TIME] 마지막 정리: {last_cleanup.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        # 정리 실행
        result = cleaner.run_cleanup(force=args.force)

        if result['cleaned']:
            print(f"\n[OK] 캐시 정리 완료!")
            print(f"   삭제된 파일: {result['deleted_files']}개")
            print(f"   정리된 용량: {result['deleted_size_mb']:.2f} MB")
            print(f"   정리 후 크기: {result['total_size_gb']:.2f} GB")
        else:
            print(f"\n[INFO] 정리 불필요 (현재 크기: {result['total_size_gb']:.2f} GB)")


if __name__ == "__main__":
    main()