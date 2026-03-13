# -*- coding: utf-8 -*-
"""
시스템 상태 점검 및 자동 복구 모듈

Phase 2.3: main.py에서 분리된 시스템 건강 관리 컴포넌트
- SystemHealthChecker: 시스템 상태 점검 및 복구
- AutoRepairSystem: 실시간 모니터링 및 자동 수정

Author: Claude Code Refactoring
Date: 2025-12-08
"""

import os
import sys
import time
import logging
import threading
import shutil
import yaml
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable


class SystemHealthChecker:
    """시스템 상태 점검 및 자동 복구"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.issues_found = []
        self.repairs_performed = []
        self.bonus_collected = False
        self.cache_cleaned = False

    def check_system_health(self) -> bool:
        """전체 시스템 상태 점검"""
        self.logger.info("[CHECK] 시스템 상태 점검 시작...")

        # 보너스 번호 자동 수집
        self._auto_collect_bonus_numbers()

        # 캐시 상태 확인 및 필요시 정리
        self._auto_clean_cache()

        # 모든 점검 실행
        checks = [
            self._check_database_structure,
            self._check_filter_configuration,
            self._check_file_permissions,
            self._check_cache_integrity,
            self._check_configuration_files,
            self._check_encoding_issues,
            self._check_bonus_numbers
        ]

        all_passed = True
        for check in checks:
            try:
                if not check():
                    all_passed = False
            except Exception as e:
                self.logger.error(f"점검 중 오류 발생: {e}")
                all_passed = False

        if all_passed:
            self.logger.info("[OK] 모든 시스템 점검 통과")
        else:
            self.logger.warning(f"[WARNING] {len(self.issues_found)}개 문제 발견, 자동 복구 시도...")
            self._perform_auto_repair()

        return all_passed

    def _check_database_structure(self) -> bool:
        """데이터베이스 구조 점검"""
        try:
            # 데이터베이스 파일 존재 확인
            db_files = ['data/lotto_numbers.db', 'data/combinations.db']
            missing_files = []

            for db_file in db_files:
                if not os.path.exists(db_file):
                    missing_files.append(db_file)

            if missing_files:
                self.issues_found.append({
                    'type': 'missing_database',
                    'details': missing_files,
                    'repair': self._repair_missing_database
                })
                return False

            # combinations 테이블 존재 확인
            try:
                from src.core.db_manager import DatabaseManager
                db_manager = DatabaseManager()

                # combinations 테이블이 비어있는지 확인
                result = db_manager.combinations_db.count_all_combinations()
                if result == 0:
                    self.issues_found.append({
                        'type': 'empty_combinations',
                        'details': 'combinations 테이블이 비어있음',
                        'repair': self._repair_empty_combinations
                    })
                    return False

            except Exception as e:
                self.issues_found.append({
                    'type': 'database_connection_error',
                    'details': str(e),
                    'repair': self._repair_database_connection
                })
                return False

            return True

        except Exception as e:
            self.logger.error(f"데이터베이스 점검 오류: {e}")
            return False

    def _check_filter_configuration(self) -> bool:
        """필터 설정 점검"""
        try:
            # fixed_step 필터가 활성화되어 있는지 확인
            config_files = [
                'config.yaml',
                'configs/adaptive_filter_config.yaml'
            ]

            for config_file in config_files:
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)

                    # adaptive_filter_config.yaml 형식 처리
                    if 'adaptive_filter_config.yaml' in config_file:
                        # adaptive_filter_config.yaml은 필터명이 최상위 키
                        if 'fixed_step' in config and config.get('fixed_step', {}).get('enabled', False):
                            self.issues_found.append({
                                'type': 'fixed_step_enabled',
                                'details': f'{config_file}에서 fixed_step 필터 활성화됨 (0% 통과율 문제)',
                                'repair': lambda cf=config_file: self._repair_fixed_step_filter(cf)
                            })
                            self.logger.warning(f"[WARNING] fixed_step 필터가 활성화되어 있습니다. 자동 비활성화 필요.")
                            return False
                    # config.yaml 형식 처리
                    elif 'filters' in config:
                        filters = config.get('filters', {})
                        if isinstance(filters, dict):
                            for filter_name, filter_config in filters.items():
                                if 'fixed_step' in filter_name.lower():
                                    if isinstance(filter_config, dict) and filter_config.get('enabled', False):
                                        self.issues_found.append({
                                            'type': 'fixed_step_enabled',
                                            'details': f'{config_file}에서 fixed_step 필터 활성화됨',
                                            'repair': lambda cf=config_file: self._repair_fixed_step_filter(cf)
                                        })
                                        return False

                    # multiple 필터 임계값 확인 (너무 엄격한 경우)
                    if 'adaptive_filter_config.yaml' in config_file:
                        if 'multiple' in config:
                            threshold = config.get('multiple', {}).get('probability_threshold', 1.5)
                            if threshold > 1.8:
                                self.issues_found.append({
                                    'type': 'multiple_threshold_high',
                                    'details': f'multiple 필터 임계값이 너무 높음: {threshold}',
                                    'repair': lambda cf=config_file: self._repair_multiple_threshold(cf)
                                })

            return True

        except Exception as e:
            self.logger.error(f"필터 설정 점검 오류: {e}")
            return False

    def _check_file_permissions(self) -> bool:
        """파일 권한 점검"""
        try:
            # 중요 디렉토리 쓰기 권한 확인
            dirs = ['data', 'logs', 'cache', 'configs']

            for dir_name in dirs:
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)

                if not os.access(dir_name, os.W_OK):
                    self.issues_found.append({
                        'type': 'permission_error',
                        'details': f'{dir_name} 디렉토리 쓰기 권한 없음',
                        'repair': lambda: self._repair_permissions(dir_name)
                    })
                    return False

            return True

        except Exception as e:
            self.logger.error(f"파일 권한 점검 오류: {e}")
            return False

    def _check_cache_integrity(self) -> bool:
        """캐시 무결성 점검"""
        try:
            # 모델 캐시 확인
            cache_dir = 'cache/models'
            if os.path.exists(cache_dir):
                # 너무 오래된 캐시 파일 확인
                current_time = time.time()
                old_files = []

                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.getmtime(file_path) < current_time - (7 * 24 * 3600):  # 7일 이상
                            old_files.append(file_path)

                if old_files:
                    self.issues_found.append({
                        'type': 'old_cache_files',
                        'details': f'{len(old_files)}개 오래된 캐시 파일',
                        'repair': lambda: self._repair_old_cache(old_files)
                    })

            return True

        except Exception as e:
            self.logger.error(f"캐시 점검 오류: {e}")
            return False

    def _check_configuration_files(self) -> bool:
        """설정 파일 점검"""
        try:
            # 필수 설정 파일 확인
            required_configs = ['config.yaml']
            missing_configs = []

            for config_file in required_configs:
                if not os.path.exists(config_file):
                    missing_configs.append(config_file)

            if missing_configs:
                self.issues_found.append({
                    'type': 'missing_config',
                    'details': missing_configs,
                    'repair': lambda: self._repair_missing_config(missing_configs)
                })
                return False

            # 설정 파일 문법 확인 및 일관성 점검
            for config_file in required_configs:
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config = yaml.safe_load(f)

                        # 워커 수 일관성 점검
                        if 'filter_manager' in config:
                            worker_count = config.get('filter_manager', {}).get('parallel_workers', 8)
                            if worker_count != 14:  # 최적값으로 통일
                                self.issues_found.append({
                                    'type': 'config_inconsistency',
                                    'details': f'워커 수 불일치: {worker_count} → 14 필요',
                                    'repair': lambda cf=config_file: self._repair_config_inconsistency(cf)
                                })

                        # 배치 크기 점검
                        batch_size = config.get('batch_size', 1000)
                        if batch_size < 10000:  # 최적값
                            self.issues_found.append({
                                'type': 'batch_size_small',
                                'details': f'배치 크기 작음: {batch_size} → 10000 권장',
                                'repair': lambda cf=config_file: self._repair_config_inconsistency(cf)
                            })

                    except yaml.YAMLError as e:
                        self.issues_found.append({
                            'type': 'invalid_config_syntax',
                            'details': f'{config_file}: {str(e)}',
                            'repair': lambda cf=config_file: self._repair_config_syntax(cf)
                        })
                        return False

            return True

        except Exception as e:
            self.logger.error(f"설정 파일 점검 오류: {e}")
            return False

    def _auto_collect_bonus_numbers(self):
        """보너스 번호 자동 수집"""
        try:
            self.logger.info("[AUTO] 보너스 번호 확인 및 수집 중...")

            # 보너스 번호 누락 여부 확인
            from src.core.db_manager import DatabaseManager
            db_manager = DatabaseManager()

            # 누락된 보너스 번호가 있는지 확인
            missing_bonus = db_manager.lotto_db.get_missing_bonus_rounds()

            if missing_bonus and len(missing_bonus) > 0:
                self.logger.info(f"[INFO] {len(missing_bonus)}개 회차 보너스 번호 누락 발견")

                # 자동 수집 실행
                try:
                    from src.scripts.complete_bonus_collection import collect_all_bonus_numbers
                    result = collect_all_bonus_numbers(db_manager)
                    if result:
                        self.logger.info("[OK] 보너스 번호 수집 완료")
                        self.bonus_collected = True
                except Exception as e:
                    self.logger.warning(f"보너스 번호 자동 수집 실패: {e}")
            else:
                self.logger.info("[OK] 모든 보너스 번호 정상")

        except Exception as e:
            self.logger.warning(f"보너스 번호 확인 중 오류: {e}")

    def _auto_clean_cache(self):
        """캐시 자동 정리"""
        try:
            cache_dir = 'cache/models'
            if os.path.exists(cache_dir):
                # 캐시 파일 크기 확인
                total_size = sum(
                    os.path.getsize(os.path.join(cache_dir, f))
                    for f in os.listdir(cache_dir)
                    if os.path.isfile(os.path.join(cache_dir, f))
                )

                # 500MB 이상이면 정리
                if total_size > 500 * 1024 * 1024:
                    self.logger.info(f"[INFO] 캐시 크기 {total_size / 1024 / 1024:.1f}MB - 정리 시작")

                    # 오래된 캐시 파일 삭제
                    current_time = time.time()
                    for filename in os.listdir(cache_dir):
                        file_path = os.path.join(cache_dir, filename)
                        if os.path.isfile(file_path):
                            file_age = current_time - os.path.getmtime(file_path)
                            if file_age > 7 * 24 * 3600:  # 7일 이상
                                os.remove(file_path)
                                self.logger.info(f"[CLEAN] 오래된 캐시 삭제: {filename}")

                    self.cache_cleaned = True
                    self.logger.info("[OK] 캐시 정리 완료")

        except Exception as e:
            self.logger.warning(f"캐시 정리 중 오류: {e}")

    def _check_bonus_numbers(self) -> bool:
        """보너스 번호 데이터 점검"""
        try:
            from src.core.db_manager import DatabaseManager
            db_manager = DatabaseManager()

            # 전체 회차 수와 보너스 번호 있는 회차 수 확인
            total_rounds = db_manager.lotto_db.get_last_round()
            rounds_with_bonus = db_manager.lotto_db.count_rounds_with_bonus()

            if rounds_with_bonus < total_rounds - 1:  # 최신 회차는 제외
                missing = total_rounds - rounds_with_bonus - 1
                self.logger.warning(f"[WARNING] {missing}개 회차 보너스 번호 누락")
                return False

            return True

        except Exception as e:
            self.logger.error(f"보너스 번호 점검 오류: {e}")
            return False

    def _check_encoding_issues(self) -> bool:
        """인코딩 문제 점검"""
        try:
            # 주요 소스 파일의 인코딩 문제 확인
            source_files = ['main.py']

            for file_path in source_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 모든 이모지가 텍스트로 교체되었으므로 인코딩 문제 없음
                    except UnicodeDecodeError:
                        self.issues_found.append({
                            'type': 'unicode_error',
                            'details': f'{file_path} 유니코드 디코딩 오류',
                            'repair': lambda: self._repair_unicode_error(file_path)
                        })
                        return False

            return True

        except Exception as e:
            self.logger.error(f"인코딩 점검 오류: {e}")
            return False

    def _perform_auto_repair(self):
        """자동 복구 실행"""
        self.logger.info(f"[FIX] {len(self.issues_found)}개 문제 자동 복구 시작...")

        for issue in self.issues_found:
            try:
                self.logger.info(f"복구 중: {issue['type']} - {issue['details']}")
                if callable(issue['repair']):
                    success = issue['repair']()
                    if success:
                        self.repairs_performed.append(issue['type'])
                        self.logger.info(f"[OK] {issue['type']} 복구 완료")
                    else:
                        self.logger.error(f"[X] {issue['type']} 복구 실패")
            except Exception as e:
                self.logger.error(f"복구 중 오류 발생: {issue['type']} - {e}")

        if self.repairs_performed:
            self.logger.info(f"[FIX] {len(self.repairs_performed)}개 문제 복구 완료")

    def _repair_missing_database(self) -> bool:
        """누락된 데이터베이스 복구"""
        try:
            # 데이터베이스 디렉토리 생성
            os.makedirs('data', exist_ok=True)

            # DatabaseMigrator를 사용하여 초기화
            from src.meta_data_manager import MetaDataManager
            from src.utils.db_migrator import DatabaseMigrator

            meta_manager = MetaDataManager()
            db_migrator = DatabaseMigrator(meta_manager)
            return db_migrator.reset_database()

        except Exception as e:
            self.logger.error(f"데이터베이스 복구 실패: {e}")
            return False

    def _repair_empty_combinations(self) -> bool:
        """비어있는 combinations 테이블 복구"""
        try:
            self.logger.info("combinations 테이블을 filtered_combinations에서 복사 중...")

            import sqlite3
            # FIX HIGH: 컨텍스트 매니저 사용으로 연결 누수 방지
            with sqlite3.connect('data/combinations.db') as conn:
                cursor = conn.cursor()

                # filtered_combinations 테이블에서 데이터 확인
                cursor.execute("SELECT COUNT(*) FROM filtered_combinations")
                filtered_count = cursor.fetchone()[0]

                if filtered_count == 0:
                    self.logger.error("filtered_combinations 테이블도 비어있습니다. 전체 생성 필요.")
                    # 이 경우에만 전체 생성
                    from src.core.combination_manager import CombinationManager
                    from src.core.db_manager import DatabaseManager

                    db_manager = DatabaseManager()
                    combination_manager = CombinationManager(db_manager)
                    total_combinations = combination_manager.generate_all_combinations()
                    self.logger.info(f"[OK] {total_combinations:,}개 조합 생성 완료")
                else:
                    # filtered_combinations에서 combinations로 복사
                    self.logger.info(f"filtered_combinations에서 {filtered_count:,}개 데이터 복사 중...")

                    cursor.execute("DROP TABLE IF EXISTS combinations")
                    cursor.execute("""
                        CREATE TABLE combinations AS
                        SELECT * FROM filtered_combinations
                    """)

                    # 인덱스 생성
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_combinations_round
                        ON combinations(round)
                    """)

                    conn.commit()

                    # 검증
                    cursor.execute("SELECT COUNT(*) FROM filtered_combinations")
                    final_count = cursor.fetchone()[0]
                    self.logger.info(f"[OK] filtered_combinations 테이블 생성 완료: {final_count:,}개 레코드")

            return True

        except Exception as e:
            self.logger.error(f"combinations 테이블 복구 실패: {e}")
            return False

    def _repair_database_connection(self) -> bool:
        """데이터베이스 연결 문제 복구"""
        try:
            # 데이터베이스 파일 권한 수정
            db_files = ['data/lotto_numbers.db', 'data/combinations.db']

            for db_file in db_files:
                if os.path.exists(db_file):
                    # 파일 잠금 해제 시도
                    try:
                        import sqlite3
                        # FIX HIGH: 컨텍스트 매니저 사용으로 연결 누수 방지
                        with sqlite3.connect(db_file) as conn:
                            conn.execute("PRAGMA journal_mode=WAL;")
                    except Exception:
                        pass

            return True

        except Exception as e:
            self.logger.error(f"데이터베이스 연결 복구 실패: {e}")
            return False

    def _repair_fixed_step_filter(self, config_file: str) -> bool:
        """fixed_step 필터 비활성화"""
        try:
            # 백업 파일 생성
            backup_file = f"{config_file}.backup_{int(time.time())}"
            shutil.copy2(config_file, backup_file)
            self.logger.info(f"백업 생성: {backup_file}")

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # adaptive_filter_config.yaml 형식 처리
            if 'adaptive_filter_config.yaml' in config_file:
                if 'fixed_step' in config:
                    config['fixed_step']['enabled'] = False
                    self.logger.info("[OK] adaptive_filter_config.yaml에서 fixed_step 필터 비활성화")
            # config.yaml 형식 처리
            elif 'filters' in config:
                filters = config.get('filters', {})
                if isinstance(filters, dict):
                    for filter_name, filter_config in filters.items():
                        if 'fixed_step' in filter_name.lower():
                            if isinstance(filter_config, dict):
                                filter_config['enabled'] = False
                            else:
                                filters[filter_name] = False
                    self.logger.info("[OK] config.yaml에서 fixed_step 필터 비활성화")

            # 수정된 설정 저장
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            self.logger.info(f"[OK] {config_file}에서 fixed_step 필터 비활성화 완료 (0% 통과율 문제 해결)")
            return True

        except Exception as e:
            self.logger.error(f"fixed_step 필터 비활성화 실패: {e}")
            return False

    def _repair_multiple_threshold(self, config_file: str) -> bool:
        """multiple 필터 임계값 조정"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if 'multiple' in config:
                old_threshold = config['multiple'].get('probability_threshold', 2.0)
                config['multiple']['probability_threshold'] = 1.5  # 적정 수준으로 조정

                # 백업 파일 생성
                backup_file = f"{config_file}.backup_{int(time.time())}"
                shutil.copy2(config_file, backup_file)

                # 수정된 설정 저장
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                self.logger.info(f"[OK] multiple 필터 임계값 조정: {old_threshold} -> 1.5")
                return True

        except Exception as e:
            self.logger.error(f"multiple 필터 임계값 조정 실패: {e}")
            return False

    def _repair_config_inconsistency(self, config_file: str) -> bool:
        """설정 파일 불일치 복구 (워커 수, 배치 크기 통일)"""
        try:
            # 백업 생성
            backup_file = f"{config_file}.backup_{int(time.time())}"
            shutil.copy2(config_file, backup_file)

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 워커 수 통일 (14개)
            if 'filter_manager' in config:
                old_workers = config.get('filter_manager', {}).get('parallel_workers', 8)
                config.setdefault('filter_manager', {})['parallel_workers'] = 14
                self.logger.info(f"워커 수 조정: {old_workers} → 14")
            else:
                config['filter_manager'] = {'parallel_workers': 14}
                self.logger.info("워커 수 설정: 14")

            # 배치 크기 통일 (10000)
            old_batch = config.get('batch_size', 1000)
            config['batch_size'] = 10000
            self.logger.info(f"배치 크기 조정: {old_batch} → 10000")

            # 기타 최적화 설정
            if 'filtering' not in config:
                config['filtering'] = {}
            config['filtering']['use_parallel'] = True
            config['filtering']['max_workers'] = 14
            config['filtering']['batch_size'] = 10000

            # 수정된 설정 저장
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            self.logger.info(f"[OK] {config_file} 설정 일관성 복구 완료")
            return True

        except Exception as e:
            self.logger.error(f"설정 파일 불일치 복구 실패: {e}")
            return False

    def _repair_permissions(self, dir_name: str) -> bool:
        """파일 권한 복구"""
        try:
            os.chmod(dir_name, 0o755)
            return True
        except Exception as e:
            self.logger.error(f"권한 복구 실패 {dir_name}: {e}")
            return False

    def _repair_old_cache(self, old_files: list) -> bool:
        """오래된 캐시 파일 정리"""
        try:
            for file_path in old_files:
                os.remove(file_path)
            self.logger.info(f"[OK] {len(old_files)}개 오래된 캐시 파일 정리 완료")
            return True
        except Exception as e:
            self.logger.error(f"캐시 정리 실패: {e}")
            return False

    def _repair_missing_config(self, missing_configs: list) -> bool:
        """누락된 설정 파일 복구"""
        try:
            # 기본 설정 파일 생성
            default_config = {
                'database': {
                    'path': 'data/lotto_numbers.db',
                    'timeout': 30
                },
                'filtering': {
                    'use_parallel': True,
                    'max_workers': 14,
                    'batch_size': 10000
                },
                'logging': {
                    'level': 'INFO',
                    'file': 'logs/lotto_app.log'
                }
            }

            for config_file in missing_configs:
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

            return True

        except Exception as e:
            self.logger.error(f"설정 파일 복구 실패: {e}")
            return False

    def _repair_config_syntax(self, config_file: str) -> bool:
        """설정 파일 문법 오류 복구"""
        try:
            # 백업 생성 후 기본 설정으로 복구
            backup_file = f"{config_file}.error_backup_{int(time.time())}"
            shutil.copy2(config_file, backup_file)

            return self._repair_missing_config([config_file])

        except Exception as e:
            self.logger.error(f"설정 파일 문법 복구 실패: {e}")
            return False

    def _repair_encoding_error(self, file_path: str) -> bool:
        """인코딩 오류 복구"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 문제가 있는 문자 수정
            content = content.replace('enhanced_feedback', 'enhanced_feedback')

            # 백업 생성
            backup_file = f"{file_path}.encoding_backup_{int(time.time())}"
            shutil.copy2(file_path, backup_file)

            # 수정된 내용 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return True

        except Exception as e:
            self.logger.error(f"인코딩 오류 복구 실패: {e}")
            return False

    def _repair_unicode_error(self, file_path: str) -> bool:
        """유니코드 오류 복구"""
        try:
            # 다양한 인코딩으로 시도
            encodings = ['utf-8', 'cp949', 'euc-kr', 'latin1']

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()

                    # UTF-8으로 다시 저장
                    backup_file = f"{file_path}.unicode_backup_{int(time.time())}"
                    shutil.copy2(file_path, backup_file)

                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    return True

                except UnicodeDecodeError:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"유니코드 오류 복구 실패: {e}")
            return False


class AutoRepairSystem:
    """실시간 시스템 문제 감지 및 자동 수정"""

    def __init__(self, db_manager=None, config_manager=None):
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)
        self.monitoring = False
        self.repair_history = []
        self._last_memory_warning_time = 0  # 메모리 경고 쿨다운 타임스탬프

    def start_monitoring(self):
        """실시간 모니터링 시작"""
        self.monitoring = True
        self.logger.info("[CHECK] 실시간 시스템 모니터링 시작")

        # 모니터링 스레드 시작
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()

    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring = False
        self.logger.info("실시간 시스템 모니터링 중지")

    def _monitoring_loop(self):
        """모니터링 루프"""
        while self.monitoring:
            try:
                # 5분마다 시스템 상태 확인
                time.sleep(300)
                self._check_system_issues()

            except Exception as e:
                self.logger.error(f"모니터링 루프 오류: {e}")
                time.sleep(60)  # 오류 시 1분 후 재시도

    def _check_system_issues(self):
        """시스템 문제 확인"""
        issues_detected = []

        # 1. 데이터베이스 연결 확인
        if not self._check_database_health():
            issues_detected.append('database_connection')

        # 2. 메모리 사용량 확인
        if not self._check_memory_usage():
            issues_detected.append('high_memory_usage')

        # 3. 디스크 공간 확인
        if not self._check_disk_space():
            issues_detected.append('low_disk_space')

        # 4. 로그 파일 크기 확인
        if not self._check_log_file_size():
            issues_detected.append('large_log_file')

        # 문제가 감지되면 자동 복구 시도
        if issues_detected:
            self._auto_repair_issues(issues_detected)

    def _check_database_health(self) -> bool:
        """데이터베이스 상태 확인"""
        try:
            if self.db_manager:
                # 간단한 쿼리로 연결 확인
                self.db_manager.get_latest_round()
                return True
        except Exception as e:
            self.logger.error(f"데이터베이스 연결 문제 감지: {e}")
            return False
        return True

    def _check_memory_usage(self) -> bool:
        """메모리 사용량 확인"""
        try:
            import psutil
            memory_percent = psutil.virtual_memory().percent

            if memory_percent > 95:  # 95% 이상: CRITICAL - 항상 경고
                self.logger.warning(f"[CRITICAL] 매우 높은 메모리 사용량: {memory_percent:.1f}%")
                self._last_memory_warning_time = time.time()
                return False

            if memory_percent > 90:  # 90% 이상: WARNING - 쿨다운 적용 (10분)
                now = time.time()
                if now - self._last_memory_warning_time >= 600:
                    self.logger.warning(f"높은 메모리 사용량 감지: {memory_percent:.1f}%")
                    self._last_memory_warning_time = now
                return False

        except ImportError:
            pass
        except Exception as e:
            self.logger.error(f"메모리 확인 오류: {e}")

        return True

    def _check_disk_space(self) -> bool:
        """디스크 공간 확인"""
        try:
            total, used, free = shutil.disk_usage('.')
            free_percent = (free / total) * 100

            if free_percent < 10:  # 10% 미만 시 경고
                self.logger.warning(f"낮은 디스크 공간 감지: {free_percent:.1f}% 남음")
                return False

        except Exception as e:
            self.logger.error(f"디스크 공간 확인 오류: {e}")

        return True

    def _check_log_file_size(self) -> bool:
        """로그 파일 크기 확인"""
        try:
            log_file = 'logs/lotto_app.log'
            if os.path.exists(log_file):
                size_mb = os.path.getsize(log_file) / (1024 * 1024)

                if size_mb > 100:  # 100MB 이상 시 정리
                    self.logger.warning(f"큰 로그 파일 감지: {size_mb:.1f}MB")
                    return False

        except Exception as e:
            self.logger.error(f"로그 파일 확인 오류: {e}")

        return True

    def _auto_repair_issues(self, issues: list):
        """감지된 문제들 자동 복구"""
        for issue in issues:
            try:
                repair_func = getattr(self, f'_repair_{issue}', None)
                if repair_func:
                    self.logger.info(f"[FIX] 자동 복구 시작: {issue}")
                    success = repair_func()

                    if success:
                        self.repair_history.append({
                            'issue': issue,
                            'timestamp': datetime.now(),
                            'status': 'success'
                        })
                        self.logger.info(f"[OK] {issue} 복구 완료")
                    else:
                        self.logger.error(f"[X] {issue} 복구 실패")

            except Exception as e:
                self.logger.error(f"자동 복구 오류 {issue}: {e}")

    def _repair_database_connection(self) -> bool:
        """데이터베이스 연결 문제 복구"""
        try:
            # 데이터베이스 재연결 시도
            if self.db_manager:
                self.db_manager.close_all_connections()
                time.sleep(2)

                # 새 연결 생성
                from src.core.db_manager import DatabaseManager
                self.db_manager = DatabaseManager()

            return True

        except Exception as e:
            self.logger.error(f"데이터베이스 연결 복구 실패: {e}")
            return False

    def _repair_high_memory_usage(self) -> bool:
        """높은 메모리 사용량 복구"""
        try:
            # 캐시 정리
            import gc
            gc.collect()

            # 모델 캐시 정리
            cache_dir = 'cache/models'
            if os.path.exists(cache_dir):
                temp_files = []
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        if file.endswith('.tmp'):
                            temp_files.append(os.path.join(root, file))

                for temp_file in temp_files:
                    try:
                        os.remove(temp_file)
                    except:
                        pass

            return True

        except Exception as e:
            self.logger.error(f"메모리 정리 실패: {e}")
            return False

    def _repair_low_disk_space(self) -> bool:
        """낮은 디스크 공간 복구"""
        try:
            # 임시 파일 정리
            temp_dirs = ['cache/temp', 'logs/old', 'backup/old']

            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)

            # 오래된 로그 파일 압축
            logs_dir = 'logs'
            if os.path.exists(logs_dir):
                import gzip
                for file in os.listdir(logs_dir):
                    if file.endswith('.log') and file != 'lotto_app.log':
                        file_path = os.path.join(logs_dir, file)
                        if os.path.getmtime(file_path) < time.time() - (7 * 24 * 3600):  # 7일 이상
                            # gzip 압축
                            with open(file_path, 'rb') as f_in:
                                with gzip.open(f"{file_path}.gz", 'wb') as f_out:
                                    f_out.writelines(f_in)
                            os.remove(file_path)

            return True

        except Exception as e:
            self.logger.error(f"디스크 공간 정리 실패: {e}")
            return False

    def _repair_large_log_file(self) -> bool:
        """큰 로그 파일 정리"""
        try:
            log_file = 'logs/lotto_app.log'

            if os.path.exists(log_file):
                # 백업 생성
                backup_file = f"{log_file}.backup_{int(time.time())}"
                shutil.copy2(log_file, backup_file)

                # 로그 파일 크기 줄이기 (마지막 1000줄만 유지)
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if len(lines) > 1000:
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines[-1000:])

            return True

        except Exception as e:
            self.logger.error(f"로그 파일 정리 실패: {e}")
            return False
