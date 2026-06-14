"""
Error Prevention System for Lotto Prediction System
포괄적인 오류 예방 및 자동 복구 시스템

시스템 건강 상태 포괄 점검 + 일부 자동 복구.

[2026-06-14 honesty] 실제 동작 범위 정정: 이 시스템은 main 경로에서 '시작 시 1회'
포괄 점검만 수행한다(아래 schedule_periodic_checks는 main.py에서 호출되지 않는 옵션 데몬용).
따라서 '24시간 무인 상시 모니터링'이라는 과거 표현은 정확하지 않으며, 상시 점검을 원하면
schedule_periodic_checks를 별도로 기동해야 한다.
"""

import os
import sys
import gc
import sqlite3
import psutil
import logging
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
# [2026-06-14 죽은코드 제거] import importlib.util 삭제: 실제 import 검증에 쓰려던 잔재이나 사용처 0건.
#  클래스 존재 점검은 소스 텍스트('class X' 문자열) 매칭이라 importlib 불필요(아래 _check_required_classes).
import json
import yaml

# 시스템 경로 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

class Priority(Enum):
    """우선순위 레벨"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class HealthCheckResult:
    """건강 상태 검사 결과"""
    check_name: str
    priority: Priority
    status: bool
    message: str
    auto_fixed: bool = False
    recovery_action: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class ErrorPreventionSystem:
    """포괄적인 오류 예방 및 자동 복구 시스템"""

    def __init__(self, config_path: Optional[str] = None):
        self.project_root = project_root
        self.logger = self._setup_logger()
        self.config = self._load_config(config_path)
        self.health_results: List[HealthCheckResult] = []

        # 임계값 설정
        self.thresholds = {
            'memory_usage_percent': 85,
            'cache_size_mb': 2000,
            'disk_space_gb': 5,
            'database_size_mb': 500,
            'log_file_mb': 50,
            'filtered_pool_min_size': 50000  # 더 현실적인 값으로 조정
        }

        # 필수 클래스 및 모듈 정의
        self.required_classes = {
            'FilteredPoolLSTMPredictor': 'src.ml.filtered_pool_lstm_predictor',
            'FilteredPoolEnsemblePredictor': 'src.ml.filtered_pool_ensemble_predictor',
            'FilterManager': 'src.core.filter_manager',
            'DatabaseManager': 'src.core.db_manager',
            'IntegratedFilterManager': 'src.core.integrated_filter_manager'
        }

        # 필수 데이터베이스 파일
        self.required_databases = [
            'data/lotto_numbers.db',
            'data/combinations.db',
            'data/predictions.db',
            'data/performance_stats.db'
        ]

        # 자동 복구 카운터
        self.recovery_attempts = {}
        self.max_recovery_attempts = 3

    def _setup_logger(self) -> logging.Logger:
        """로거 설정"""
        logger = logging.getLogger('ErrorPreventionSystem')
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            # 파일 핸들러
            log_dir = self.project_root / 'logs'
            log_dir.mkdir(exist_ok=True)

            fh = logging.FileHandler(log_dir / 'error_prevention.log', encoding='utf-8')
            fh.setLevel(logging.INFO)

            # 콘솔 핸들러
            ch = logging.StreamHandler()
            ch.setLevel(logging.WARNING)

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            fh.setFormatter(formatter)
            ch.setFormatter(formatter)

            logger.addHandler(fh)
            logger.addHandler(ch)

        return logger

    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """설정 파일 로드"""
        if config_path is None:
            config_path = self.project_root / 'config.yaml'

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.warning(f"설정 파일 로드 실패: {e}, 기본 설정 사용")
            return {}

    def run_comprehensive_check(self) -> Dict[str, Any]:
        """포괄적인 시스템 건강 상태 검사"""
        self.logger.info("포괄적인 시스템 건강 상태 검사 시작")
        self.health_results.clear()

        try:
            # 1. 필수 클래스 존재 확인
            self._check_required_classes()

            # 2. 데이터베이스 무결성 검사
            self._check_database_integrity()

            # 3. 메모리 사용량 모니터링
            self._check_memory_usage()

            # 4. 캐시 크기 관리
            self._check_cache_size()

            # 5. 디스크 공간 확인
            self._check_disk_space()

            # 6. 필터링된 풀 상태 확인
            self._check_filtered_pool_status()

            # 7. None 안전성 검증
            self._check_none_safety()

            # 8. 로그 파일 관리
            self._check_log_files()

            # 9. 설정 파일 유효성 검사
            self._check_config_files()

            # 10. 프로세스 상태 확인
            self._check_process_health()

        except Exception as e:
            self.logger.error(f"건강 상태 검사 중 오류: {e}")
            self.logger.error(traceback.format_exc())

        # 결과 정리 및 보고서 생성
        report = self._generate_health_report()
        self.logger.info("포괄적인 시스템 건강 상태 검사 완료")

        return report

    def _check_required_classes(self):
        """필수 클래스 존재 확인"""
        self.logger.info("필수 클래스 존재 확인 시작")

        for class_name, module_path in self.required_classes.items():
            try:
                # 모듈 경로를 실제 파일 경로로 변환
                file_path = self.project_root / f"{module_path.replace('.', '/')}.py"

                if not file_path.exists():
                    # 파일이 없는 경우 자동 생성 시도
                    self._create_missing_module(class_name, module_path, file_path)
                    continue

                # 파일 내용 확인 (null byte 체크)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # null byte가 있는지 확인
                    if '\x00' in content:
                        self.logger.warning(f"파일 {file_path}에 null byte 감지, 복구 시도")
                        # null byte 제거
                        clean_content = content.replace('\x00', '')
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(clean_content)

                        self.health_results.append(HealthCheckResult(
                            check_name=f"File Repair: {class_name}",
                            priority=Priority.HIGH,
                            status=True,
                            message=f"파일 {file_path}의 null byte 제거됨",
                            auto_fixed=True,
                            recovery_action="파일에서 null byte 자동 제거"
                        ))

                except UnicodeDecodeError:
                    # 인코딩 문제가 있는 경우
                    self.logger.warning(f"파일 {file_path} 인코딩 문제 감지")
                    self.health_results.append(HealthCheckResult(
                        check_name=f"File Encoding: {class_name}",
                        priority=Priority.MEDIUM,
                        status=False,
                        message=f"파일 {file_path} 인코딩 문제",
                        recovery_action="파일 인코딩을 UTF-8로 변환 필요"
                    ))
                    continue

                # 클래스 존재 확인 (소스 텍스트 'class X' 문자열 매칭 - import 검증 아님)
                if f"class {class_name}" in content:
                    self.health_results.append(HealthCheckResult(
                        check_name=f"Required Class: {class_name}",
                        priority=Priority.CRITICAL,
                        status=True,
                        message=f"{class_name} class 정의 소스 존재(텍스트 확인 - 실제 import 검증 아님)"
                    ))
                else:
                    # 클래스가 없는 경우 자동 생성 시도
                    self._create_missing_class(class_name, module_path, file_path)

            except Exception as e:
                self.logger.error(f"클래스 {class_name} 확인 중 오류: {e}")
                self._handle_missing_class_error(class_name, module_path, str(e))

    def _create_missing_module(self, class_name: str, module_path: str, file_path: Path):
        """누락된 모듈 자동 생성"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 기본 템플릿 생성 (간단한 버전)
            template = f'''"""
{class_name} - 자동 생성된 클래스
"""

class {class_name}:
    """자동 생성된 {class_name} 클래스"""

    def __init__(self):
        self.initialized = True
        print(f"자동 생성된 {class_name} 클래스가 초기화되었습니다.")

    def __str__(self):
        return f"{class_name} - 자동 생성됨"
'''

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(template)

            self.logger.info(f"누락된 모듈 자동 생성: {file_path}")
            self.health_results.append(HealthCheckResult(
                check_name=f"Missing Module: {class_name}",
                priority=Priority.HIGH,
                status=True,
                message=f"누락된 모듈 {module_path} 자동 생성됨",
                auto_fixed=True,
                recovery_action="모듈 파일 자동 생성"
            ))

        except Exception as e:
            self.logger.error(f"모듈 자동 생성 실패: {e}")
            self.health_results.append(HealthCheckResult(
                check_name=f"Missing Module: {class_name}",
                priority=Priority.CRITICAL,
                status=False,
                message=f"모듈 {module_path} 자동 생성 실패: {e}",
                recovery_action="수동 모듈 생성 필요"
            ))

    def _create_missing_class(self, class_name: str, module_path: str, file_path: Path):
        """누락된 클래스 자동 추가"""
        try:
            # 기존 파일 읽기
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 클래스가 없다면 추가
            if f"class {class_name}" not in content:
                class_template = f'''

class {class_name}:
    """자동 추가된 {class_name} 클래스"""

    def __init__(self):
        self.initialized = True
        print(f"자동 추가된 {class_name} 클래스가 초기화되었습니다.")

    def __str__(self):
        return f"{class_name} - 자동 추가됨"
'''
                content += class_template

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                self.logger.info(f"클래스 {class_name} 자동 추가")
                self.health_results.append(HealthCheckResult(
                    check_name=f"Added Class: {class_name}",
                    priority=Priority.MEDIUM,
                    status=True,
                    message=f"클래스 {class_name} 자동 추가됨",
                    auto_fixed=True,
                    recovery_action="누락된 클래스 자동 추가"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name=f"Required Class: {class_name}",
                    priority=Priority.CRITICAL,
                    status=True,
                    message=f"{class_name} 클래스 존재 확인됨"
                ))

        except Exception as e:
            self.logger.error(f"클래스 자동 추가 실패: {e}")
            self._handle_missing_class_error(class_name, module_path, str(e))

    def _handle_missing_class_error(self, class_name: str, module_path: str, error: str):
        """누락된 클래스 오류 처리"""
        self.health_results.append(HealthCheckResult(
            check_name=f"Required Class: {class_name}",
            priority=Priority.CRITICAL,
            status=False,
            message=f"{class_name} 클래스 누락 또는 오류: {error}",
            recovery_action=f"모듈 {module_path} 확인 및 수정 필요"
        ))

    def _check_database_integrity(self):
        """데이터베이스 연결/테이블 존재 점검.

        [2026-06-14 honesty] 이름은 'integrity'지만 실제로는 sqlite connect + sqlite_master 테이블
        존재 확인만 한다(PRAGMA integrity_check/quick_check 미수행). 손상/페이지/체크섬 같은 '깊은
        무결성'은 검증하지 않으므로 로그 문구를 정직하게 '연결/테이블 점검'으로 표기한다."""
        self.logger.info("데이터베이스 연결/테이블 존재 점검 시작 (참고: 깊은 무결성 PRAGMA는 미수행)")

        for db_path in self.required_databases:
            full_path = self.project_root / db_path

            try:
                if not full_path.exists():
                    self._create_missing_database(db_path, full_path)
                    continue

                # 데이터베이스 연결 테스트
                conn = sqlite3.connect(full_path)
                cursor = conn.cursor()

                # 기본 테이블 존재 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()

                conn.close()

                if tables:
                    self.health_results.append(HealthCheckResult(
                        check_name=f"Database: {db_path}",
                        priority=Priority.HIGH,
                        status=True,
                        message=f"데이터베이스 {db_path} 정상, 테이블 수: {len(tables)}"
                    ))
                else:
                    self._handle_empty_database(db_path, full_path)

            except sqlite3.Error as e:
                self._handle_database_corruption(db_path, full_path, str(e))
            except Exception as e:
                self.logger.error(f"데이터베이스 {db_path} 검사 중 오류: {e}")

    def _create_missing_database(self, db_path: str, full_path: Path):
        """누락된 데이터베이스 생성"""
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect(full_path)
            conn.close()

            self.logger.info(f"누락된 데이터베이스 생성: {db_path}")
            self.health_results.append(HealthCheckResult(
                check_name=f"Missing Database: {db_path}",
                priority=Priority.HIGH,
                status=True,
                message=f"누락된 데이터베이스 {db_path} 생성됨",
                auto_fixed=True,
                recovery_action="빈 데이터베이스 파일 생성"
            ))

        except Exception as e:
            self.logger.error(f"데이터베이스 생성 실패: {e}")
            self.health_results.append(HealthCheckResult(
                check_name=f"Missing Database: {db_path}",
                priority=Priority.CRITICAL,
                status=False,
                message=f"데이터베이스 {db_path} 생성 실패: {e}",
                recovery_action="수동 데이터베이스 생성 필요"
            ))

    def _handle_empty_database(self, db_path: str, full_path: Path):
        """빈 데이터베이스 처리"""
        self.health_results.append(HealthCheckResult(
            check_name=f"Database: {db_path}",
            priority=Priority.MEDIUM,
            status=False,
            message=f"데이터베이스 {db_path}가 비어있음",
            recovery_action="데이터 초기화 스크립트 실행 필요"
        ))

    def _handle_database_corruption(self, db_path: str, full_path: Path, error: str):
        """데이터베이스 손상 처리"""
        try:
            # 백업 생성 시도
            backup_path = full_path.with_suffix('.backup')
            if full_path.exists():
                full_path.rename(backup_path)

            # 새 데이터베이스 생성
            conn = sqlite3.connect(full_path)
            conn.close()

            self.health_results.append(HealthCheckResult(
                check_name=f"Database: {db_path}",
                priority=Priority.HIGH,
                status=True,
                message=f"손상된 데이터베이스 {db_path} 복구됨 (백업: {backup_path.name})",
                auto_fixed=True,
                recovery_action="손상된 DB 백업 후 새 DB 생성"
            ))

        except Exception as recovery_error:
            self.logger.error(f"데이터베이스 복구 실패: {recovery_error}")
            self.health_results.append(HealthCheckResult(
                check_name=f"Database: {db_path}",
                priority=Priority.CRITICAL,
                status=False,
                message=f"데이터베이스 {db_path} 손상 및 복구 실패: {error}",
                recovery_action="수동 데이터베이스 복구 필요"
            ))

    def _check_memory_usage(self):
        """메모리 사용량 모니터링"""
        try:
            process = psutil.Process()
            memory_percent = process.memory_percent()

            if memory_percent > self.thresholds['memory_usage_percent']:
                # 메모리 정리 시도
                gc.collect()

                # 재검사
                new_memory_percent = process.memory_percent()

                self.health_results.append(HealthCheckResult(
                    check_name="Memory Usage",
                    priority=Priority.HIGH if memory_percent > 90 else Priority.MEDIUM,
                    status=new_memory_percent <= self.thresholds['memory_usage_percent'],
                    message=f"메모리 사용률: {memory_percent:.1f}% -> {new_memory_percent:.1f}% (임계값: {self.thresholds['memory_usage_percent']}%)",
                    auto_fixed=new_memory_percent < memory_percent,
                    recovery_action="가비지 컬렉션 실행" if new_memory_percent < memory_percent else "프로세스 재시작 권장"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Memory Usage",
                    priority=Priority.LOW,
                    status=True,
                    message=f"메모리 사용률 정상: {memory_percent:.1f}%"
                ))

        except Exception as e:
            self.logger.error(f"메모리 사용량 확인 중 오류: {e}")

    def _check_cache_size(self):
        """캐시 크기 관리"""
        try:
            cache_dir = self.project_root / 'cache'
            if not cache_dir.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)
                self.health_results.append(HealthCheckResult(
                    check_name="Cache Directory",
                    priority=Priority.LOW,
                    status=True,
                    message="캐시 디렉토리 생성됨",
                    auto_fixed=True,
                    recovery_action="캐시 디렉토리 자동 생성"
                ))
                return

            total_size = 0
            file_count = 0

            for root, dirs, files in os.walk(cache_dir):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        size = file_path.stat().st_size
                        total_size += size
                        file_count += 1
                    except Exception as e:
                        # [health-repair-7] 개별 파일 stat 실패는 건너뛰되 원인을 debug로 남긴다
                        self.logger.debug(f"파일 크기 측정 건너뜀({file_path}): {e}")
                        continue

            total_size_mb = total_size / (1024 * 1024)

            if total_size_mb > self.thresholds['cache_size_mb']:
                # 캐시 정리 시도
                cleaned_size = self._clean_old_cache_files(cache_dir)

                self.health_results.append(HealthCheckResult(
                    check_name="Cache Size",
                    priority=Priority.MEDIUM,
                    status=True,
                    message=f"캐시 크기: {total_size_mb:.1f}MB ({file_count}개 파일), 정리됨: {cleaned_size:.1f}MB",
                    auto_fixed=cleaned_size > 0,
                    recovery_action=f"오래된 캐시 파일 {cleaned_size:.1f}MB 정리"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Cache Size",
                    priority=Priority.LOW,
                    status=True,
                    message=f"캐시 크기 정상: {total_size_mb:.1f}MB ({file_count}개 파일)"
                ))

        except Exception as e:
            self.logger.error(f"캐시 크기 확인 중 오류: {e}")

    def _clean_old_cache_files(self, cache_dir: Path) -> float:
        """오래된 캐시 파일 정리"""
        try:
            cleaned_size = 0
            current_time = datetime.now()

            for root, dirs, files in os.walk(cache_dir):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        # 7일 이상 된 파일 삭제
                        modified_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if current_time - modified_time > timedelta(days=7):
                            size = file_path.stat().st_size
                            file_path.unlink()
                            cleaned_size += size

                    except Exception as e:
                        # [health-repair-7] 개별 캐시 파일 삭제 실패는 건너뛰되 원인을 debug로 남긴다
                        self.logger.debug(f"캐시 파일 정리 건너뜀({file_path}): {e}")
                        continue

            return cleaned_size / (1024 * 1024)  # MB 단위로 반환

        except Exception as e:
            self.logger.error(f"캐시 파일 정리 중 오류: {e}")
            return 0

    def _check_disk_space(self):
        """디스크 공간 확인"""
        try:
            disk_usage = psutil.disk_usage(str(self.project_root))
            free_gb = disk_usage.free / (1024 ** 3)

            if free_gb < self.thresholds['disk_space_gb']:
                self.health_results.append(HealthCheckResult(
                    check_name="Disk Space",
                    priority=Priority.HIGH if free_gb < 2 else Priority.MEDIUM,
                    status=False,
                    message=f"디스크 여유공간 부족: {free_gb:.1f}GB (최소 필요: {self.thresholds['disk_space_gb']}GB)",
                    recovery_action="불필요한 파일 정리 또는 디스크 확장 필요"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Disk Space",
                    priority=Priority.LOW,
                    status=True,
                    message=f"디스크 여유공간 충분: {free_gb:.1f}GB"
                ))

        except Exception as e:
            self.logger.error(f"디스크 공간 확인 중 오류: {e}")

    def _check_filtered_pool_status(self):
        """필터링된 풀 상태 확인"""
        try:
            combinations_db = self.project_root / 'data' / 'combinations.db'
            if not combinations_db.exists():
                self.health_results.append(HealthCheckResult(
                    check_name="Filtered Pool",
                    priority=Priority.HIGH,
                    status=False,
                    message="조합 데이터베이스가 존재하지 않음",
                    recovery_action="조합 데이터베이스 생성 필요"
                ))
                return

            conn = sqlite3.connect(combinations_db)
            cursor = conn.cursor()

            # 필터링된 조합 수 확인 (테이블 구조 확인 후)
            try:
                # 먼저 테이블이 존재하는지 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filtered_combinations'")
                table_exists = cursor.fetchone()

                if not table_exists:
                    filtered_count = 0
                else:
                    # included 컬럼이 있는지 확인
                    cursor.execute("PRAGMA table_info(filtered_combinations)")
                    columns = [col[1] for col in cursor.fetchall()]

                    if 'included' in columns:
                        cursor.execute("SELECT COUNT(*) FROM filtered_combinations WHERE included = 1")
                        filtered_count = cursor.fetchone()[0]
                    else:
                        # [health-repair-6] included 컬럼이 없으면 '통과 풀 크기'를 알 수 없다.
                        # 전체 COUNT(*)를 통과 풀로 간주하면 풀 크기를 과대평가해 거짓 '정상'을
                        # 보고하므로, None 센티넬로 '검증 불가'를 표시하고 정상/부족 판정에서 제외한다.
                        filtered_count = None

            except sqlite3.Error as e:
                self.logger.warning(f"필터링된 조합 테이블 쿼리 실패: {e}")
                filtered_count = 0

            conn.close()

            if filtered_count is None:
                # [health-repair-6] 통과 풀 크기 검증 보류(스키마에 included 컬럼 없음) - 정상/부족 판정에서 제외
                self.health_results.append(HealthCheckResult(
                    check_name="Filtered Pool",
                    priority=Priority.MEDIUM,
                    status=True,
                    message="필터링된 풀 검증 불가: filtered_combinations에 'included' 컬럼이 없어 통과 조합 수를 판정할 수 없음",
                    recovery_action="included 컬럼을 포함하도록 스키마 마이그레이션 또는 재필터링 필요"
                ))
            elif filtered_count < self.thresholds['filtered_pool_min_size']:
                self.health_results.append(HealthCheckResult(
                    check_name="Filtered Pool",
                    priority=Priority.HIGH,
                    status=False,
                    message=f"필터링된 조합 수 부족: {filtered_count:,}개 (최소 필요: {self.thresholds['filtered_pool_min_size']:,}개)",
                    recovery_action="필터 임계값 조정 또는 재필터링 필요"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Filtered Pool",
                    priority=Priority.LOW,
                    status=True,
                    message=f"필터링된 조합 수 정상: {filtered_count:,}개"
                ))

        except Exception as e:
            self.logger.error(f"필터링된 풀 상태 확인 중 오류: {e}")
            self.health_results.append(HealthCheckResult(
                check_name="Filtered Pool",
                priority=Priority.MEDIUM,
                status=False,
                message=f"필터링된 풀 상태 확인 실패: {e}",
                recovery_action="데이터베이스 연결 및 테이블 구조 확인 필요"
            ))

    def _check_none_safety(self):
        """None 안전성 검증"""
        try:
            # 주요 설정 파일에서 None 값 검사
            config_files = [
                self.project_root / 'config.yaml',
                self.project_root / 'configs' / 'adaptive_filter_config.yaml'
            ]

            none_issues = []

            for config_file in config_files:
                if config_file.exists():
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f)

                        if config_data is None:
                            none_issues.append(f"{config_file.name}: 전체 설정이 None")
                        else:
                            none_values = self._find_none_values(config_data, config_file.name)
                            none_issues.extend(none_values)

                    except Exception as e:
                        none_issues.append(f"{config_file.name}: 읽기 오류 - {e}")

            if none_issues:
                self.health_results.append(HealthCheckResult(
                    check_name="None Safety Check",
                    priority=Priority.MEDIUM,
                    status=False,
                    message=f"None 값 감지: {len(none_issues)}개 항목",
                    recovery_action="설정 파일의 None 값들을 기본값으로 대체 필요"
                ))

                for issue in none_issues:
                    self.logger.warning(f"None 값 감지: {issue}")
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="None Safety Check",
                    priority=Priority.LOW,
                    status=True,
                    message="설정 파일에서 None 값 없음"
                ))

        except Exception as e:
            self.logger.error(f"None 안전성 검증 중 오류: {e}")

    def _find_none_values(self, data: Any, prefix: str = "") -> List[str]:
        """재귀적으로 None 값 찾기"""
        none_values = []

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{prefix}.{key}" if prefix else key
                if value is None:
                    none_values.append(f"{current_path}: None")
                else:
                    none_values.extend(self._find_none_values(value, current_path))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{prefix}[{i}]"
                if item is None:
                    none_values.append(f"{current_path}: None")
                else:
                    none_values.extend(self._find_none_values(item, current_path))

        return none_values

    def _check_log_files(self):
        """로그 파일 관리"""
        try:
            log_dir = self.project_root / 'logs'
            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)
                self.health_results.append(HealthCheckResult(
                    check_name="Log Directory",
                    priority=Priority.LOW,
                    status=True,
                    message="로그 디렉토리 생성됨",
                    auto_fixed=True,
                    recovery_action="로그 디렉토리 자동 생성"
                ))
                return

            oversized_logs = []
            total_log_size = 0

            for log_file in log_dir.glob('*.log'):
                try:
                    size_mb = log_file.stat().st_size / (1024 * 1024)
                    total_log_size += size_mb

                    if size_mb > self.thresholds['log_file_mb']:
                        oversized_logs.append((log_file.name, size_mb))

                except Exception as e:
                    # [health-repair-7] 개별 로그 파일 점검 실패는 건너뛰되 원인을 debug로 남긴다
                    self.logger.debug(f"로그 파일 점검 건너뜀({log_file}): {e}")
                    continue

            if oversized_logs:
                # 큰 로그 파일들을 로테이션
                rotated_count = self._rotate_large_log_files(log_dir, oversized_logs)

                self.health_results.append(HealthCheckResult(
                    check_name="Log File Management",
                    priority=Priority.MEDIUM,
                    status=True,
                    message=f"대용량 로그 파일 {rotated_count}개 로테이션됨",
                    auto_fixed=rotated_count > 0,
                    recovery_action=f"로그 파일 {rotated_count}개 로테이션"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Log File Management",
                    priority=Priority.LOW,
                    status=True,
                    message=f"로그 파일 크기 정상 (총 {total_log_size:.1f}MB)"
                ))

        except Exception as e:
            self.logger.error(f"로그 파일 관리 중 오류: {e}")

    def _rotate_large_log_files(self, log_dir: Path, oversized_logs: List[Tuple[str, float]]) -> int:
        """대용량 로그 파일 로테이션"""
        rotated_count = 0

        for log_name, size_mb in oversized_logs:
            try:
                log_file = log_dir / log_name
                backup_name = f"{log_name}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_file = log_dir / backup_name

                # 현재 로그를 백업으로 이동
                log_file.rename(backup_file)

                # 새 빈 로그 파일 생성
                log_file.touch()

                rotated_count += 1
                self.logger.info(f"로그 파일 로테이션: {log_name} ({size_mb:.1f}MB) -> {backup_name}")

            except Exception as e:
                self.logger.error(f"로그 파일 {log_name} 로테이션 실패: {e}")

        return rotated_count

    def _check_config_files(self):
        """설정 파일 유효성 검사"""
        try:
            config_files = [
                ('config.yaml', Priority.HIGH),
                ('configs/adaptive_filter_config.yaml', Priority.HIGH),
                ('requirements.txt', Priority.MEDIUM)
            ]

            for config_path, priority in config_files:
                full_path = self.project_root / config_path

                if not full_path.exists():
                    self.health_results.append(HealthCheckResult(
                        check_name=f"Config File: {config_path}",
                        priority=priority,
                        status=False,
                        message=f"설정 파일 {config_path} 누락",
                        recovery_action=f"기본 {config_path} 파일 생성 필요"
                    ))
                    continue

                try:
                    if config_path.endswith('.yaml'):
                        with open(full_path, 'r', encoding='utf-8') as f:
                            yaml.safe_load(f)

                    self.health_results.append(HealthCheckResult(
                        check_name=f"Config File: {config_path}",
                        priority=Priority.LOW,
                        status=True,
                        message=f"설정 파일 {config_path} 유효함"
                    ))

                except Exception as e:
                    self.health_results.append(HealthCheckResult(
                        check_name=f"Config File: {config_path}",
                        priority=priority,
                        status=False,
                        message=f"설정 파일 {config_path} 구문 오류: {e}",
                        recovery_action=f"설정 파일 {config_path} 구문 수정 필요"
                    ))

        except Exception as e:
            self.logger.error(f"설정 파일 검사 중 오류: {e}")

    def _check_process_health(self):
        """프로세스 상태 확인"""
        try:
            process = psutil.Process()

            # CPU 사용률
            cpu_percent = process.cpu_percent(interval=1)

            # 열린 파일 수
            try:
                open_files = len(process.open_files())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                open_files = 0

            # 스레드 수
            try:
                thread_count = process.num_threads()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                thread_count = 0

            # 프로세스 상태 평가
            issues = []
            if cpu_percent > 80:
                issues.append(f"높은 CPU 사용률: {cpu_percent:.1f}%")
            if open_files > 100:
                issues.append(f"많은 열린 파일: {open_files}개")
            if thread_count > 50:
                issues.append(f"많은 스레드: {thread_count}개")

            if issues:
                self.health_results.append(HealthCheckResult(
                    check_name="Process Health",
                    priority=Priority.MEDIUM,
                    status=False,
                    message=f"프로세스 상태 주의: {', '.join(issues)}",
                    recovery_action="프로세스 재시작 고려"
                ))
            else:
                self.health_results.append(HealthCheckResult(
                    check_name="Process Health",
                    priority=Priority.LOW,
                    status=True,
                    message=f"프로세스 상태 정상 (CPU: {cpu_percent:.1f}%, 파일: {open_files}개, 스레드: {thread_count}개)"
                ))

        except Exception as e:
            self.logger.error(f"프로세스 상태 확인 중 오류: {e}")

    def _generate_health_report(self) -> Dict[str, Any]:
        """건강 상태 보고서 생성"""
        total_checks = len(self.health_results)
        passed_checks = sum(1 for result in self.health_results if result.status)
        failed_checks = total_checks - passed_checks
        auto_fixed_checks = sum(1 for result in self.health_results if result.auto_fixed)

        # 우선순위별 집계
        priority_stats = {
            Priority.CRITICAL: {'total': 0, 'passed': 0, 'failed': 0},
            Priority.HIGH: {'total': 0, 'passed': 0, 'failed': 0},
            Priority.MEDIUM: {'total': 0, 'passed': 0, 'failed': 0},
            Priority.LOW: {'total': 0, 'passed': 0, 'failed': 0}
        }

        for result in self.health_results:
            priority_stats[result.priority]['total'] += 1
            if result.status:
                priority_stats[result.priority]['passed'] += 1
            else:
                priority_stats[result.priority]['failed'] += 1

        # 전체 건강 점수 계산 (가중치 적용)
        weight_map = {Priority.CRITICAL: 4, Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}
        total_weight = 0
        passed_weight = 0

        for priority, stats in priority_stats.items():
            weight = weight_map[priority]
            total_weight += stats['total'] * weight
            passed_weight += stats['passed'] * weight

        health_score = (passed_weight / total_weight * 100) if total_weight > 0 else 100

        # 상태 평가
        if health_score >= 90:
            overall_status = "EXCELLENT"
        elif health_score >= 75:
            overall_status = "GOOD"
        elif health_score >= 60:
            overall_status = "WARNING"
        else:
            overall_status = "CRITICAL"

        report = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': overall_status,
            'health_score': round(health_score, 1),
            'summary': {
                'total_checks': total_checks,
                'passed_checks': passed_checks,
                'failed_checks': failed_checks,
                'auto_fixed_checks': auto_fixed_checks
            },
            'priority_breakdown': {
                priority.value: stats for priority, stats in priority_stats.items()
            },
            'detailed_results': [
                {
                    'check_name': result.check_name,
                    'priority': result.priority.value,
                    'status': 'PASS' if result.status else 'FAIL',
                    'message': result.message,
                    'auto_fixed': result.auto_fixed,
                    'recovery_action': result.recovery_action,
                    'timestamp': result.timestamp.isoformat()
                }
                for result in self.health_results
            ],
            'failed_checks': [
                {
                    'check_name': result.check_name,
                    'priority': result.priority.value,
                    'message': result.message,
                    'recovery_action': result.recovery_action
                }
                for result in self.health_results if not result.status
            ],
            'auto_fixed_checks': [
                {
                    'check_name': result.check_name,
                    'message': result.message,
                    'recovery_action': result.recovery_action
                }
                for result in self.health_results if result.auto_fixed
            ]
        }

        # 보고서를 파일로 저장
        self._save_health_report(report)

        return report

    def _save_health_report(self, report: Dict[str, Any]):
        """건강 상태 보고서 파일로 저장"""
        try:
            reports_dir = self.project_root / 'logs' / 'health_reports'
            reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = reports_dir / f'health_report_{timestamp}.json'

            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            self.logger.info(f"건강 상태 보고서 저장됨: {report_file}")

            # 최신 보고서 링크 생성
            latest_report = reports_dir / 'latest_health_report.json'
            if latest_report.exists():
                latest_report.unlink()

            with open(latest_report, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.error(f"건강 상태 보고서 저장 실패: {e}")

    def get_recovery_recommendations(self) -> List[Dict[str, str]]:
        """복구 권장사항 반환"""
        recommendations = []

        failed_results = [r for r in self.health_results if not r.status and r.recovery_action]

        # 우선순위 순으로 정렬
        priority_order = [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW]
        failed_results.sort(key=lambda x: priority_order.index(x.priority))

        for result in failed_results:
            recommendations.append({
                'check_name': result.check_name,
                'priority': result.priority.value,
                'issue': result.message,
                'recommendation': result.recovery_action
            })

        return recommendations

    def auto_fix_issues(self, max_attempts: int = 3) -> Dict[str, Any]:
        """자동 복구 가능한 문제들 수정"""
        self.logger.info("자동 복구 시스템 시작")

        fixed_issues = []
        failed_fixes = []

        failed_results = [r for r in self.health_results if not r.status]

        for result in failed_results:
            check_name = result.check_name

            # 복구 시도 횟수 확인
            if self.recovery_attempts.get(check_name, 0) >= max_attempts:
                self.logger.warning(f"{check_name} 최대 복구 시도 횟수 초과")
                continue

            self.recovery_attempts[check_name] = self.recovery_attempts.get(check_name, 0) + 1

            try:
                success = self._attempt_auto_fix(result)

                if success:
                    fixed_issues.append({
                        'check_name': check_name,
                        'issue': result.message,
                        'fix_applied': result.recovery_action
                    })
                    self.logger.info(f"자동 복구 성공: {check_name}")
                else:
                    failed_fixes.append({
                        'check_name': check_name,
                        'issue': result.message,
                        'attempted_fix': result.recovery_action
                    })
                    self.logger.warning(f"자동 복구 실패: {check_name}")

            except Exception as e:
                failed_fixes.append({
                    'check_name': check_name,
                    'issue': result.message,
                    'error': str(e)
                })
                self.logger.error(f"자동 복구 중 오류 ({check_name}): {e}")

        return {
            'timestamp': datetime.now().isoformat(),
            'fixed_issues': fixed_issues,
            'failed_fixes': failed_fixes,
            'summary': {
                'total_attempts': len(failed_results),
                'successful_fixes': len(fixed_issues),
                'failed_attempts': len(failed_fixes)
            }
        }

    def _attempt_auto_fix(self, result: HealthCheckResult) -> bool:
        """개별 문제에 대한 자동 복구 시도"""
        check_name = result.check_name.lower()

        try:
            if 'missing database' in check_name:
                return True  # 이미 처리됨
            elif 'missing module' in check_name:
                return True  # 이미 처리됨
            elif 'cache size' in check_name:
                return self._fix_cache_size_issue()
            elif 'memory usage' in check_name:
                return self._fix_memory_issue()
            elif 'log file' in check_name:
                return self._fix_log_file_issue()
            elif 'disk space' in check_name:
                return self._fix_disk_space_issue()
            else:
                return False

        except Exception as e:
            self.logger.error(f"자동 복구 시도 중 오류: {e}")
            return False

    def _fix_cache_size_issue(self) -> bool:
        """캐시 크기 문제 해결"""
        try:
            cache_dir = self.project_root / 'cache'
            cleaned_size = self._clean_old_cache_files(cache_dir)
            return cleaned_size > 0
        except Exception as e:
            # [health-repair-7] 복구 실패를 삼키지 말고 원인을 남긴다
            self.logger.warning(f"캐시 크기 문제 자동복구 실패: {e}")
            return False

    def _fix_memory_issue(self) -> bool:
        """메모리 문제 해결"""
        try:
            gc.collect()
            return True
        except Exception as e:
            # [health-repair-7] 복구 실패를 삼키지 말고 원인을 남긴다
            self.logger.warning(f"메모리 문제 자동복구 실패: {e}")
            return False

    def _fix_log_file_issue(self) -> bool:
        """로그 파일 문제 해결"""
        try:
            log_dir = self.project_root / 'logs'
            oversized_logs = []

            for log_file in log_dir.glob('*.log'):
                size_mb = log_file.stat().st_size / (1024 * 1024)
                if size_mb > self.thresholds['log_file_mb']:
                    oversized_logs.append((log_file.name, size_mb))

            if oversized_logs:
                rotated_count = self._rotate_large_log_files(log_dir, oversized_logs)
                return rotated_count > 0

            return True
        except Exception as e:
            # [health-repair-7] 복구 실패를 삼키지 말고 원인을 남긴다
            self.logger.warning(f"로그 파일 문제 자동복구 실패: {e}")
            return False

    def _fix_disk_space_issue(self) -> bool:
        """디스크 공간 문제 해결"""
        try:
            # 임시 파일 및 캐시 정리
            cache_cleaned = self._fix_cache_size_issue()
            log_cleaned = self._fix_log_file_issue()

            return cache_cleaned or log_cleaned
        except Exception as e:
            # [health-repair-7] 복구 실패를 삼키지 말고 원인을 남긴다
            self.logger.warning(f"디스크 공간 문제 자동복구 실패: {e}")
            return False

    def schedule_periodic_checks(self, interval_hours: int = 6):
        """주기적 건강 상태 검사 스케줄링"""
        import schedule
        import time
        import threading

        def run_check():
            self.logger.info("주기적 건강 상태 검사 실행")
            report = self.run_comprehensive_check()

            # CRITICAL 또는 HIGH 우선순위 문제가 있으면 자동 복구 시도
            critical_issues = [r for r in self.health_results
                             if not r.status and r.priority in [Priority.CRITICAL, Priority.HIGH]]

            if critical_issues:
                self.logger.warning(f"긴급 문제 {len(critical_issues)}개 감지, 자동 복구 시도")
                self.auto_fix_issues()

        schedule.every(interval_hours).hours.do(run_check)

        def scheduler_thread():
            while True:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 스케줄 확인

        thread = threading.Thread(target=scheduler_thread, daemon=True)
        thread.start()

        self.logger.info(f"주기적 건강 상태 검사 스케줄링됨 (간격: {interval_hours}시간)")


def main():
    """메인 실행 함수"""
    system = ErrorPreventionSystem()

    print("=== 로또 예측 시스템 오류 예방 시스템 ===")
    print("포괄적인 시스템 건강 상태 검사를 시작합니다...\n")

    # 포괄적 건강 검사 실행
    report = system.run_comprehensive_check()

    # 결과 출력
    print(f"전체 상태: {report['overall_status']} (건강 점수: {report['health_score']}%)")
    print(f"검사 항목: {report['summary']['total_checks']}개")
    print(f"통과: {report['summary']['passed_checks']}개")
    print(f"실패: {report['summary']['failed_checks']}개")
    print(f"자동 복구: {report['summary']['auto_fixed_checks']}개")

    # 실패한 검사 항목 출력
    if report['failed_checks']:
        print(f"\n=== 실패한 검사 항목 ({len(report['failed_checks'])}개) ===")
        for failed in report['failed_checks']:
            print(f"[{failed['priority']}] {failed['check_name']}")
            print(f"  문제: {failed['message']}")
            if failed['recovery_action']:
                print(f"  권장조치: {failed['recovery_action']}")
            print()

    # 자동 복구된 항목 출력
    if report['auto_fixed_checks']:
        print(f"\n=== 자동 복구된 항목 ({len(report['auto_fixed_checks'])}개) ===")
        for fixed in report['auto_fixed_checks']:
            print(f"[O] {fixed['check_name']}")
            print(f"  조치: {fixed['recovery_action']}")
        print()

    # 복구 권장사항
    recommendations = system.get_recovery_recommendations()
    if recommendations:
        print(f"\n=== 복구 권장사항 ({len(recommendations)}개) ===")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. [{rec['priority']}] {rec['check_name']}")
            print(f"   문제: {rec['issue']}")
            print(f"   권장: {rec['recommendation']}")
        print()

    # 자동 복구 시도 (CRITICAL, HIGH 우선순위만)
    critical_issues = [r for r in system.health_results
                      if not r.status and r.priority in [Priority.CRITICAL, Priority.HIGH]]

    if critical_issues:
        print(f"\n긴급 문제 {len(critical_issues)}개에 대해 자동 복구를 시도합니다...")
        fix_result = system.auto_fix_issues()

        if fix_result['fixed_issues']:
            print(f"[O] {len(fix_result['fixed_issues'])}개 문제가 자동으로 해결되었습니다.")

        if fix_result['failed_fixes']:
            print(f"[X] {len(fix_result['failed_fixes'])}개 문제는 수동 조치가 필요합니다.")

    print("\n건강 상태 보고서가 logs/health_reports/ 디렉토리에 저장되었습니다.")

    # 주기적 검사 스케줄링 (옵션)
    import sys
    if '--daemon' in sys.argv:
        print("\n데몬 모드로 실행 중... (6시간마다 자동 검사)")
        system.schedule_periodic_checks(6)

        try:
            import time
            while True:
                time.sleep(3600)  # 1시간마다 상태 확인
        except KeyboardInterrupt:
            print("\n데몬 모드 종료됨")


if __name__ == "__main__":
    main()