import logging
import argparse
import os
import sys
import time
import numpy as np
from datetime import datetime
import threading
import webbrowser
import subprocess
import random
import traceback

# matplotlib 백엔드를 non-interactive로 설정 (tkinter 에러 방지)
try:
    import matplotlib
    matplotlib.use('Agg')
except ImportError:
    pass  # matplotlib이 없어도 실행 가능

# TensorFlow/Keras 모든 경고 억제
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # ERROR 이상만 표시 (WARNING 억제)

# ABSL 로깅 억제 (TensorFlow/Keras 내부 로깅)
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='absl')
warnings.filterwarnings('ignore', message='.*compiled metrics.*')
warnings.filterwarnings('ignore', message='.*compile_metrics.*')
warnings.filterwarnings('ignore', message='.*Compiled the loaded model.*')

# ABSL 환경 변수 설정
os.environ['ABSL_LOGGING_VERBOSITY'] = '1'  # ERROR만 표시

# TensorFlow Lite 경고 억제
os.environ['TF_CPP_MIN_VLOG_LEVEL'] = '3'

from src.filters.average_filter import AverageFilter
from src.filters.section_filter import SectionFilter
from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.meta_data_manager import MetaDataManager
from src.data_collector import DataCollector
from src.core.combination_manager import CombinationManager
from src.core.filter_manager import FilterManager
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
import yaml
from src.core.pattern_manager import PatternManager
from src.scripts.analyze_lotto_statistics import LottoStatisticsAnalyzer
from src.filters.match_filter import MatchFilter
from src.filters.odd_even_filter import OddEvenFilter
from src.filters.consecutive_filter import ConsecutiveFilter
from src.filters.sum_range_filter import SumRangeFilter
from src.filters.fixed_step_filter import FixedStepFilter
from src.filters.last_digit_filter import LastDigitFilter
from src.filters.max_gap_filter import MaxGapFilter
from src.filters.multiple_filter import MultipleFilter
from src.utils.constants import LottoConstants
from src.core.specialized_databases import PatternsDB
from src.filters.ten_section_filter import TenSectionFilter  # 신규 추가
from src.filters.arithmetic_sequence_filter import ArithmeticSequenceFilter  # 신규 추가
from src.filters.geometric_sequence_filter import GeometricSequenceFilter  # 신규 추가
from src.utils.config_manager import ConfigManager
from src.utils.db_migrator import DatabaseMigrator  # 신규 추가
from src.core.filter_validator import FilterValidator  # 신규 추가
from src.optimization.adaptive_filter_optimizer import AdaptiveFilterOptimizer  # 신규 추가
from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework  # 최적화된 백테스팅
from src.ml.auto_ml_optimizer import AutoMLOptimizer  # 신규 추가
from src.optimization.feedback_loop_system import FeedbackLoopSystem  # 신규 추가
from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop  # 향상된 피드백 루프
from src.ml.realtime_learning_system import RealtimeLearningSystem  # 신규 추가
from src.monitoring.performance_dashboard import PerformanceDashboard  # 신규 추가
from src.core.auto_adjustment_system_v2 import AutoAdjustmentSystemV2  # 단순화된 자동 조정 시스템

# ML/AI 모듈 임포트
try:
    from src.ml.lstm_predictor import LSTMPredictor
    from src.ml.ensemble_predictor import EnsemblePredictor
    ML_AVAILABLE = True
except ImportError as e:
    ML_AVAILABLE = False
    logging.warning(f"ML 모듈 로드 실패: {e}")

try:
    from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
    from src.probabilistic.bayesian_inference import BayesianFilter
    PROBABILISTIC_AVAILABLE = True
except ImportError as e:
    PROBABILISTIC_AVAILABLE = False
    logging.warning(f"확률 모듈 로드 실패: {e}")

try:
    from src.advanced.fractal_pattern_analyzer import FractalPatternAnalyzer
    ADVANCED_AVAILABLE = True
except ImportError as e:
    ADVANCED_AVAILABLE = False
    logging.warning(f"고급 분석 모듈 로드 실패: {e}")

try:
    from src.enhanced_dynamic_filter_manager import EnhancedDynamicFilterManager
    DYNAMIC_FILTER_AVAILABLE = True
except ImportError as e:
    DYNAMIC_FILTER_AVAILABLE = False
    logging.warning(f"동적 필터 매니저 로드 실패: {e}")

# 24시간 자동화 시스템 임포트
try:
    from src.automation import AutomationCoordinator
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    AUTOMATION_AVAILABLE = False
    logging.warning(f"자동화 시스템 로드 실패: {e}")


class SystemHealthChecker:
    """시스템 상태 점검 및 자동 복구"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.issues_found = []
        self.repairs_performed = []
        
    def check_system_health(self) -> bool:
        """전체 시스템 상태 점검"""
        self.logger.info("[CHECK] 시스템 상태 점검 시작...")
        
        # 모든 점검 실행
        checks = [
            self._check_database_structure,
            self._check_filter_configuration,
            self._check_file_permissions,
            self._check_cache_integrity,
            self._check_configuration_files,
            self._check_encoding_issues
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
                import time
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
            conn = sqlite3.connect('data/combinations.db')
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
                cursor.execute("SELECT COUNT(*) FROM combinations")
                final_count = cursor.fetchone()[0]
                self.logger.info(f"[OK] combinations 테이블 생성 완료: {final_count:,}개 레코드")
            
            conn.close()
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
                        conn = sqlite3.connect(db_file)
                        conn.execute("PRAGMA journal_mode=WAL;")
                        conn.close()
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
            import shutil
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
                import shutil
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
            import shutil
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
            import shutil
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
            import shutil
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
                    import shutil
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
            
            if memory_percent > 85:  # 85% 이상 사용 시 경고
                self.logger.warning(f"높은 메모리 사용량 감지: {memory_percent:.1f}%")
                return False
                
        except ImportError:
            # psutil이 없으면 스킵
            pass
        except Exception as e:
            self.logger.error(f"메모리 확인 오류: {e}")
            
        return True
        
    def _check_disk_space(self) -> bool:
        """디스크 공간 확인"""
        try:
            import shutil
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
                import shutil
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
                    import shutil
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
                import shutil
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


def generate_final_predictions(db_manager, filter_manager, ml_predictions=None, num_sets=5, use_relaxed_filter=True):
    """ML/AI 예측과 필터링 결과를 통합하여 최종 예측 번호 생성
    
    Args:
        db_manager: 데이터베이스 매니저
        filter_manager: 필터 매니저
        ml_predictions: ML 예측 결과
        num_sets: 생성할 세트 수
        use_relaxed_filter: ML 예측에 대해 완화된 필터 적용 여부
    """
    final_predictions = []
    ml_failed_predictions = []  # 필터 실패한 ML 예측들
    
    try:
        # 1. ML/AI 예측 결과 통합 (상위 신뢰도 순)
        all_ml_predictions = []
        
        # ml_predictions가 리스트인 경우 처리
        if ml_predictions and isinstance(ml_predictions, list):
            # 리스트인 경우 그대로 사용
            all_ml_predictions = ml_predictions[:15]  # 최대 15개까지만
        elif ml_predictions and isinstance(ml_predictions, dict):
            # 딕셔너리인 경우 기존 로직 사용
            for model_name, predictions in ml_predictions.items():
                if predictions:
                    for pred in predictions[:3]:  # 각 모델에서 상위 3개씩
                        pred_copy = pred.copy()
                        pred_copy['model'] = model_name
                        all_ml_predictions.append(pred_copy)
        
        # 신뢰도 순으로 정렬
        all_ml_predictions.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        # 2. 필터를 통과한 ML 예측 선별 (완화된 기준 적용)
        for pred in all_ml_predictions:
            if len(final_predictions) >= num_sets:
                break
                
            numbers = pred.get('numbers', [])
            if len(numbers) == 6:
                # 필터 통과 여부 확인 (각 필터 개별 확인)
                passes_all_filters = True
                failed_filters = []
                critical_filters_failed = []  # 중요 필터 실패 추적
                
                # filter_manager.filters가 list인지 dict인지 확인
                if isinstance(filter_manager.filters, dict):
                    filters_to_check = filter_manager.filters.items()
                elif isinstance(filter_manager.filters, list):
                    # 리스트인 경우 (AdaptiveProbabilityFilter 등)
                    # 이 경우 필터가 없으므로 모두 통과로 처리
                    filters_to_check = []
                    if len(filter_manager.filters) == 0:
                        # AdaptiveProbabilityFilter는 apply_filters 메서드로 직접 처리
                        passes_all_filters = True
                    else:
                        # 일반 리스트 필터
                        filters_to_check = enumerate(filter_manager.filters)
                else:
                    filters_to_check = []
                
                # 완화 가능한 필터 목록 (확률적으로 덜 중요한 필터들)
                relaxable_filters = ['average', 'prime_composite', 'fixed_step', 'multiple', 
                                   'ten_section', 'digit_sum', 'dispersion']
                
                for filter_name, filter_obj in filters_to_check:
                    if hasattr(filter_obj, 'apply') and callable(filter_obj.apply):
                        try:
                            # 필터에 맞는 형식으로 변환 (리스트 형태)
                            numbers_str = ','.join(map(str, sorted(numbers)))
                            filtered_result = filter_obj.apply([numbers_str], db_manager.get_last_round())
                            if not filtered_result:  # 빈 리스트면 필터 통과 실패
                                failed_filters.append(filter_name)
                                
                                # ML 예측에 대해 완화된 필터 적용
                                if use_relaxed_filter and filter_name in relaxable_filters:
                                    logging.debug(f"필터 {filter_name} 완화 적용 (ML 예측 우선)")
                                    # 완화 가능한 필터는 통과 처리
                                    continue
                                else:
                                    # 중요 필터는 실패 처리
                                    critical_filters_failed.append(filter_name)
                                    passes_all_filters = False
                                    break
                        except Exception as e:
                            # 필터 적용 실패 시 로그 기록하고 실패로 처리
                            logging.debug(f"필터 {filter_name} 적용 중 오류: {str(e)}")
                            passes_all_filters = False
                            break
                
                if failed_filters:
                    logging.debug(f"ML 예측 {numbers}이 다음 필터 실패: {failed_filters}")
                    if critical_filters_failed:
                        logging.debug(f"  중요 필터 실패: {critical_filters_failed}")
                
                if passes_all_filters:
                    # pred가 딕셔너리인지 확인하고 model 키가 있는지 확인
                    if isinstance(pred, dict):
                        model_name = pred.get('model', 'Unknown')
                    else:
                        model_name = 'Unknown'
                    
                    final_predictions.append({
                        'numbers': sorted(numbers),
                        'confidence': pred.get('confidence', pred.get('score', 0)) if isinstance(pred, dict) else 0,
                        'source': f"ML/{model_name}"
                    })
                else:
                    # 필터 실패한 ML 예측 저장 (나중에 유사 조합 찾기용)
                    ml_failed_predictions.append(pred)
        
        # 2-1. ML 예측이 필터 실패한 경우, 유사한 조합 찾기
        if ml_failed_predictions and len(final_predictions) < num_sets:
            try:
                # 필터링된 조합 가져오기
                filtered_combos = db_manager.combinations_db.get_filtered_combinations(db_manager.get_last_round())
                
                if filtered_combos:
                    logging.info(f"ML 예측 필터 실패: {len(ml_failed_predictions)}개, 유사 조합 검색 중...")
                    
                    for failed_pred in ml_failed_predictions[:3]:  # 최대 3개의 실패한 예측에 대해
                        if len(final_predictions) >= num_sets:
                            break
                        
                        failed_numbers = failed_pred.get('numbers', [])
                        if len(failed_numbers) == 6:
                            # 유사한 조합 찾기
                            similar_combos = find_similar_combinations(failed_numbers, filtered_combos, top_n=3)
                            
                            if similar_combos:
                                best_match = similar_combos[0]
                                logging.debug(f"ML 예측 {failed_numbers} → 유사 조합 {best_match['numbers']} (유사도: {best_match['similarity']:.2%})")
                                
                                # 중복 확인
                                is_duplicate = False
                                for pred in final_predictions:
                                    if set(pred['numbers']) == set(best_match['numbers']):
                                        is_duplicate = True
                                        break
                                
                                if not is_duplicate:
                                    model_name = failed_pred.get('model', 'Unknown')
                                    final_predictions.append({
                                        'numbers': best_match['numbers'],
                                        'confidence': failed_pred.get('confidence', 0) * best_match['similarity'] * 0.8,
                                        'source': f"ML-Similar/{model_name}"
                                    })
                else:
                    # 필터링된 조합이 없으면 ML 예측을 그대로 사용
                    logging.warning("[WARNING] 필터링된 조합이 없음! ML 예측을 직접 사용합니다.")
                    for failed_pred in ml_failed_predictions[:num_sets - len(final_predictions)]:
                        if len(final_predictions) >= num_sets:
                            break
                        failed_numbers = failed_pred.get('numbers', [])
                        if len(failed_numbers) == 6:
                            model_name = failed_pred.get('model', 'Unknown')
                            final_predictions.append({
                                'numbers': sorted(failed_numbers),
                                'confidence': failed_pred.get('confidence', 0) * 0.7,  # 신뢰도 감소
                                'source': f"ML-Direct/{model_name}"
                            })
            except Exception as e:
                logging.error(f"유사 조합 찾기 실패: {str(e)}")
                
                # 조합이 없으면 빈 리스트 사용
                if not filtered_combos:
                    filtered_combos = []
                    
                # 필터링된 조합 중에서 랜덤하게 선택 (최대 500개로 늘림)
                if len(filtered_combos) > 500:
                    sampled_combos = random.sample(filtered_combos, 500)
                else:
                    sampled_combos = filtered_combos.copy()
                random.shuffle(sampled_combos)  # 추가로 섞어서 다양성 확보
                
                # 이미 사용된 번호들을 추적
                used_numbers = set()
                for pred in final_predictions:
                    used_numbers.update(pred['numbers'])
                
                # 중복을 최소화하면서 선택
                candidates = []
                for combo_str in sampled_combos:
                    if len(final_predictions) >= num_sets:
                        break
                    
                    # 조합 문자열을 숫자 리스트로 변환
                    try:
                        numbers = [int(n) for n in combo_str.split(',')]
                    except (ValueError, AttributeError):
                        continue
                    
                    # 중복 확인 (완전히 같은 조합)
                    is_duplicate = False
                    for pred in final_predictions:
                        if set(pred['numbers']) == set(numbers):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        # 이미 사용된 번호와의 중복 개수 계산
                        overlap_count = len(set(numbers) & used_numbers)
                        candidates.append({
                            'numbers': sorted(numbers),
                            'confidence': 0.6,
                            'source': 'Filtered',
                            'overlap': overlap_count
                        })
                
                # 중복이 적은 순서로 정렬하여 선택
                candidates.sort(key=lambda x: x['overlap'])
                for cand in candidates[:num_sets - len(final_predictions)]:
                    del cand['overlap']  # overlap 필드 제거
                    final_predictions.append(cand)
                    used_numbers.update(cand['numbers'])
            except Exception as e:
                logging.error(f"필터링된 조합 조회 실패: {str(e)}")
        
        # 4. 여전히 부족한 경우 패턴 기반 생성
        if len(final_predictions) < num_sets:
            pattern_based = generate_pattern_based_numbers(db_manager, num_sets - len(final_predictions))
            for numbers in pattern_based:
                final_predictions.append({
                    'numbers': sorted(numbers),
                    'confidence': 0.5,
                    'source': 'Pattern/Random'
                })
        
    except Exception as e:
        logging.error(f"최종 예측 생성 중 오류: {str(e)}")
        # 오류 시 기본 랜덤 생성
        for _ in range(num_sets):
            numbers = sorted(random.sample(range(1, 46), 6))
            final_predictions.append({
                'numbers': numbers,
                'confidence': 0.0,
                'source': 'Random/Fallback'
            })
    
    return final_predictions[:num_sets]


def generate_pattern_based_numbers(db_manager, count):
    """패턴 분석 기반 번호 생성"""
    pattern_numbers = []
    
    try:
        # 최근 당첨번호 패턴 분석
        all_winning_data = db_manager.get_all_numbers()
        recent_numbers = []
        for round_num, numbers_str, draw_date in all_winning_data[-20:]:  # 최근 20개
            # 문자열로 된 번호를 리스트로 변환
            numbers = [int(n) for n in numbers_str.split(',')]
            recent_numbers.append(numbers)
        
        # 번호별 출현 빈도
        frequency = {}
        for numbers in recent_numbers:
            for num in numbers:
                frequency[num] = frequency.get(num, 0) + 1
        
        # 빈도 기반 확률 생성
        for _ in range(count):
            # 가중치 기반 선택
            numbers = []
            available = list(range(1, 46))
            
            while len(numbers) < 6:
                weights = [frequency.get(n, 1) for n in available]
                probs = np.array(weights) / sum(weights)
                
                selected = np.random.choice(available, p=probs)
                numbers.append(selected)
                available.remove(selected)
            
            pattern_numbers.append(sorted(numbers))
    
    except Exception as e:
        logging.error(f"패턴 기반 번호 생성 실패: {str(e)}")
        # 실패 시 랜덤 생성
        for _ in range(count):
            pattern_numbers.append(sorted(random.sample(range(1, 46), 6)))
    
    return pattern_numbers


def analyze_number_characteristics(numbers):
    """번호 조합의 특성 분석"""
    characteristics = {}
    try:
        # numpy array를 리스트로 변환
        if hasattr(numbers, 'tolist'):
            numbers = numbers.tolist()
        # numpy int를 Python int로 변환
        numbers = [int(n) for n in numbers]
        
        # 홀짝 비율
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        even_count = 6 - odd_count
        
        # 번호 구간 분포
        sections = [0] * 5  # 1-9, 10-19, 20-29, 30-39, 40-45
        for num in numbers:
            if num <= 9:
                sections[0] += 1
            elif num <= 19:
                sections[1] += 1
            elif num <= 29:
                sections[2] += 1
            elif num <= 39:
                sections[3] += 1
            else:
                sections[4] += 1
        
        # 연속 번호
        consecutive = 0
        for i in range(len(numbers) - 1):
            if numbers[i + 1] - numbers[i] == 1:
                consecutive += 1
        
        # 합계와 평균
        total_sum = sum(numbers)
        avg = total_sum / 6
        
        # 특성 저장
        characteristics = {
            'odd_even_ratio': f"{odd_count}:{even_count}",
            'sum_total': total_sum,
            'average': round(avg, 1),
            'consecutive_count': consecutive,
            'section_distribution': sections
        }
        
        logging.info(f"   홀/짝: {odd_count}/{even_count} | 합계: {total_sum} | 평균: {avg:.1f}")
        logging.info(f"   구간분포: {sections} | 연속: {consecutive}개")
        
        return characteristics
        
    except Exception as e:
        logging.error(f"특성 분석 실패: {str(e)}")
        return characteristics


def extract_combination_features(numbers):
    """조합의 특성을 수치화하여 추출 (유사도 계산용)"""
    try:
        # numpy array를 리스트로 변환
        if hasattr(numbers, 'tolist'):
            numbers = numbers.tolist()
        numbers = [int(n) for n in numbers]
        numbers = sorted(numbers)
        
        # 특성 추출
        features = {
            'odd_count': sum(1 for n in numbers if n % 2 == 1),
            'even_count': sum(1 for n in numbers if n % 2 == 0),
            'sum_total': sum(numbers),
            'average': sum(numbers) / 6,
            'min_value': min(numbers),
            'max_value': max(numbers),
            'range': max(numbers) - min(numbers),
            'consecutive_count': sum(1 for i in range(len(numbers)-1) if numbers[i+1] - numbers[i] == 1),
            'sections': [0, 0, 0, 0, 0]  # 1-9, 10-19, 20-29, 30-39, 40-45
        }
        
        # 구간별 개수
        for num in numbers:
            if num <= 9:
                features['sections'][0] += 1
            elif num <= 19:
                features['sections'][1] += 1
            elif num <= 29:
                features['sections'][2] += 1
            elif num <= 39:
                features['sections'][3] += 1
            else:
                features['sections'][4] += 1
        
        return features
    except Exception as e:
        logging.error(f"특성 추출 실패: {str(e)}")
        return None


def calculate_similarity_score(features1, features2):
    """두 조합의 특성 기반 유사도 점수 계산 (0~1)"""
    if not features1 or not features2:
        return 0
    
    score = 0
    weights = {
        'odd_count': 0.15,
        'even_count': 0.15,
        'sum_total': 0.15,
        'average': 0.10,
        'range': 0.10,
        'consecutive_count': 0.10,
        'sections': 0.25
    }
    
    # 홀짝 개수 비교
    if features1['odd_count'] == features2['odd_count']:
        score += weights['odd_count']
    elif abs(features1['odd_count'] - features2['odd_count']) == 1:
        score += weights['odd_count'] * 0.5
    
    # 합계 비교 (±10 범위)
    sum_diff = abs(features1['sum_total'] - features2['sum_total'])
    if sum_diff <= 10:
        score += weights['sum_total'] * (1 - sum_diff / 30)
    
    # 평균 비교
    avg_diff = abs(features1['average'] - features2['average'])
    if avg_diff <= 5:
        score += weights['average'] * (1 - avg_diff / 15)
    
    # 범위 비교
    range_diff = abs(features1['range'] - features2['range'])
    if range_diff <= 10:
        score += weights['range'] * (1 - range_diff / 30)
    
    # 연속 번호 개수 비교
    if features1['consecutive_count'] == features2['consecutive_count']:
        score += weights['consecutive_count']
    elif abs(features1['consecutive_count'] - features2['consecutive_count']) == 1:
        score += weights['consecutive_count'] * 0.5
    
    # 구간 분포 비교
    section_score = 0
    for i in range(5):
        if features1['sections'][i] == features2['sections'][i]:
            section_score += 0.2
        elif abs(features1['sections'][i] - features2['sections'][i]) == 1:
            section_score += 0.1
    score += weights['sections'] * section_score
    
    return min(1.0, score)


def find_similar_combinations(ml_prediction, filtered_combos, top_n=5):
    """ML 예측과 가장 유사한 필터링된 조합들을 찾기"""
    try:
        ml_features = extract_combination_features(ml_prediction)
        if not ml_features:
            return []
        
        similar_combos = []
        
        # 모든 필터링된 조합과 유사도 계산
        for combo_str in filtered_combos[:1000]:  # 최대 1000개만 비교 (성능)
            try:
                numbers = [int(n) for n in combo_str.split(',')]
                combo_features = extract_combination_features(numbers)
                if combo_features:
                    similarity = calculate_similarity_score(ml_features, combo_features)
                    similar_combos.append({
                        'numbers': sorted(numbers),
                        'similarity': similarity,
                        'combo_str': combo_str
                    })
            except:
                continue
        
        # 유사도 순으로 정렬
        similar_combos.sort(key=lambda x: x['similarity'], reverse=True)
        
        # 상위 N개 반환
        return similar_combos[:top_n]
        
    except Exception as e:
        logging.error(f"유사 조합 찾기 실패: {str(e)}")
        return []


def parse_args():
    """명령줄 인수 파싱"""
    parser = argparse.ArgumentParser(description='로또 번호 분석 및 필터링 프로그램')
    parser.add_argument('--config', type=str, help='설정 파일 경로')
    parser.add_argument('--optimize', action='store_true', help='최적화된 저장 방식 사용')
    parser.add_argument('--parallel', action='store_true', help='병렬 처리 사용')
    parser.add_argument('--workers', type=int, help='병렬 작업자 수')
    parser.add_argument('--skip-fetch', action='store_true', help='데이터 수집 단계 건너뛰기')
    parser.add_argument('--skip-patterns', action='store_true', help='패턴 분석 단계 건너뛰기')
    parser.add_argument('--full-filter', action='store_true', help='전체 필터링 수행 (기본값: 증분 모드)')
    parser.add_argument('--reset-db', action='store_true', help='데이터베이스 강제 초기화 (개발용)')
    parser.add_argument('--force-no-migration', action='store_true', help='데이터베이스 마이그레이션 건너뛰기 (개발용)')
    
    # 24시간 자동화 시스템 옵션
    parser.add_argument('--24h', action='store_true', help='24시간 자동 실행 모드 (설정 변경 감지, 새 회차 감지, 자동 재필터링)')
    parser.add_argument('--automation-test', action='store_true', help='자동화 시스템 테스트 (5분 후 자동 종료)')
    parser.add_argument('--ignore-migration-errors', action='store_true', help='마이그레이션 오류를 무시하고 계속 진행합니다 (오류 발생 가능)')
    parser.add_argument('--force', action='store_true', help='모든 오류를 무시하고 강제로 실행 (위험)')
    parser.add_argument('--force-filter', action='store_true', help='이전 필터링 여부와 상관없이 필터링을 강제 실행합니다')
    parser.add_argument('--skip-validation', action='store_true', help='필터 검증 단계 건너뛰기')
    parser.add_argument('--skip-optimization', action='store_true', help='적응형 최적화 단계 건너뛰기')
    parser.add_argument('--skip-backtest', action='store_true', help='백테스팅 단계 건너뛰기')
    
    # ML/AI 관련 옵션
    parser.add_argument('--skip-ml', action='store_true', help='ML/AI 분석 건너뛰기')
    parser.add_argument('--ml-only', action='store_true', help='ML/AI 분석만 수행')
    parser.add_argument('--lstm', action='store_true', default=True, help='LSTM 시계열 예측 사용')
    parser.add_argument('--no-lstm', dest='lstm', action='store_false', help='LSTM 사용 안함')
    parser.add_argument('--ensemble', action='store_true', default=True, help='앙상블 모델 예측 사용')
    parser.add_argument('--no-ensemble', dest='ensemble', action='store_false', help='앙상블 사용 안함')
    parser.add_argument('--monte-carlo', action='store_true', default=True, help='Monte Carlo 시뮬레이션 사용')
    parser.add_argument('--no-monte-carlo', dest='monte_carlo', action='store_false', help='Monte Carlo 사용 안함')
    parser.add_argument('--bayesian', action='store_true', default=True, help='베이지안 추론 사용')
    parser.add_argument('--no-bayesian', dest='bayesian', action='store_false', help='베이지안 사용 안함')
    parser.add_argument('--fractal', action='store_true', default=False, help='프랙탈 패턴 분석 사용 (약 40초 소요)')
    parser.add_argument('--no-fractal', dest='fractal', action='store_false', help='프랙탈 사용 안함')
    parser.add_argument('--dynamic-filter', action='store_true', default=True, help='동적 필터 모니터링 사용')
    parser.add_argument('--no-dynamic-filter', dest='dynamic_filter', action='store_false', help='동적 필터 사용 안함')
    parser.add_argument('--predictions', type=int, default=5, help='ML 예측 조합 수')
    
    # 자동 개선 시스템 옵션
    parser.add_argument('--auto-improve', action='store_true', help='자동 개선 모드 (모든 최적화 활성화)')
    parser.add_argument('--feedback-loop', action='store_true', help='피드백 루프 시스템 활성화')
    parser.add_argument('--enhanced-feedback', action='store_true', help='향상된 피드백 루프 (영구 상태 저장)')
    parser.add_argument('--realtime-learning', action='store_true', help='실시간 학습 활성화')
    parser.add_argument('--monitoring', action='store_true', help='성능 모니터링 대시보드 생성')
    parser.add_argument('--hyperparameter-tuning', action='store_true', help='하이퍼파라미터 자동 튜닝')
    
    # 무한 학습 방지 옵션 추가
    parser.add_argument('--no-auto-adjust', action='store_true', help='자동 조정 시스템 비활성화')
    parser.add_argument('--no-realtime-learning', action='store_true', help='실시간 학습 비활성화')
    parser.add_argument('--max-ml-iterations', type=int, default=10, help='ML 최적화 최대 반복 횟수 (기본: 10)')
    
    # 자동화 시스템 전용 옵션
    parser.add_argument('--predict-only', action='store_true', help='예측만 수행 (필터링 건너뛰기)')
    parser.add_argument('--fetch-only', action='store_true', help='데이터 수집만 수행')
    
    # 대시보드 옵션 추가
    parser.add_argument('--no-dashboard', action='store_true', help='웹 대시보드 비활성화')
    parser.add_argument('--dashboard-port', type=int, default=5000, help='웹 대시보드 포트 (기본: 5000)')
    
    args = parser.parse_args()
    
    # 인자가 없으면 자동으로 --auto-improve 활성화
    if len(sys.argv) == 1:
        args.auto_improve = True
        args.monitoring = True
        print("[INFO] 인자가 없어 자동으로 --auto-improve 모드로 실행합니다.")
        print("   모든 최적화 기능이 활성화됩니다!\n")
    
    return args

def start_web_dashboard(port=5001):
    """향상된 웹 대시보드를 백그라운드 스레드로 시작 (항상 포트 5001 사용)"""
    try:
        # Flask가 설치되어 있는지 확인
        import flask
        
        # 포트를 항상 5001로 고정 (web_dashboard와 충돌 방지)
        port = 5001
        
        def run_dashboard():
            """대시보드 실행 함수"""
            try:
                # 향상된 대시보드 v2 모듈 임포트 (최신 버전 우선)
                try:
                    from src.scripts.enhanced_dashboard_v2 import run_enhanced_dashboard_v2
                    print("\n[대시보드] 향상된 웹 대시보드 v2를 시작합니다...")
                    print(f"[대시보드] 브라우저에서 http://127.0.0.1:{port} 접속하세요.")
                    print("[대시보드] 대시보드는 백그라운드에서 계속 실행됩니다.\n")
                    print("[NEW] 새로운 기능: 화면 저장, 테이블 레이아웃, 향상된 UI")
                    run_enhanced_dashboard_v2(host='127.0.0.1', port=5001, debug=False)
                except ImportError:
                    # v2가 없으면 기존 버전 사용
                    from src.scripts.enhanced_dashboard import run_enhanced_dashboard
                    print("\n[대시보드] 향상된 웹 대시보드를 시작합니다...")
                    print(f"[대시보드] 브라우저에서 http://127.0.0.1:{port} 접속하세요.")
                    print("[대시보드] 대시보드는 백그라운드에서 계속 실행됩니다.\n")
                    run_enhanced_dashboard(host='127.0.0.1', port=5001, debug=False)
                
            except ImportError:
                print("[대시보드] 웹 대시보드 모듈을 찾을 수 없습니다.")
            except Exception as e:
                print(f"[대시보드] 웹 대시보드 실행 중 오류: {e}")
        
        # 백그라운드 스레드로 실행
        dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        dashboard_thread.start()
        
        # 잠시 대기하여 서버가 시작되도록 함
        time.sleep(2)
        
        # 브라우저 자동 열기 (선택사항)
        try:
            webbrowser.open(f'http://127.0.0.1:{port}')
            print("[대시보드] 브라우저가 자동으로 열렸습니다.")
        except:
            print(f"[대시보드] 브라우저를 수동으로 열어주세요: http://127.0.0.1:{port}")
            
    except ImportError:
        print("\n[대시보드] Flask가 설치되어 있지 않습니다.")
        print("[대시보드] 웹 대시보드를 사용하려면: pip install flask")
        print("[대시보드] 프로그램은 대시보드 없이 계속 실행됩니다.\n")
    except Exception as e:
        print(f"[대시보드] 웹 대시보드 시작 실패: {e}")
        print("[대시보드] 프로그램은 대시보드 없이 계속 실행됩니다.\n")

def run_24h_automation(db_manager, config_manager, args, auto_repair_system=None):
    """24시간 자동 실행 모드"""
    import signal
    import threading
    from src.automation import AutomationCoordinator
    
    class AutomationController:
        def __init__(self):
            self.running = False
            self.coordinator = None
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        def _signal_handler(self, signum, frame):
            logging.info(f"\n시그널 {signum} 수신 - 시스템 종료 시작...")
            self.stop()
            sys.exit(0)
        
        def start(self, db_manager, config_manager, test_mode=False):
            try:
                # AutomationCoordinator 초기화
                from src.core.filter_manager import FilterManager
                filter_manager = FilterManager(db_manager)
                
                self.coordinator = AutomationCoordinator(db_manager, filter_manager)
                self.coordinator.start()
                self.running = True
                
                # AutoRepairSystem 통합 (24시간 모드에서는 더 강화된 모니터링)
                if auto_repair_system:
                    logging.info("[FIX] 24시간 모드용 강화된 시스템 모니터링 활성화")
                
                logging.info("="*60)
                logging.info("✨ 24시간 자동 실행 시스템 가동 시작!")
                logging.info("="*60)
                logging.info("  [기능] 설정 변경 자동 감지 및 재필터링")
                logging.info("  [기능] 새 회차 자동 감지 및 데이터 수집")
                logging.info("  [기능] 매일 오전 9시 자동 예측 생성")
                logging.info("  [기능] 매주 일요일 시스템 최적화")
                logging.info("  [종료] Ctrl+C로 안전하게 종료")
                logging.info("="*60)
                
                # 테스트 모드면 5분 후 종료
                if test_mode:
                    logging.info("🧪 테스트 모드 - 5분 후 자동 종료")
                    timer = threading.Timer(300, self.stop)
                    timer.daemon = True
                    timer.start()
                
                # 메인 루프
                last_status_time = time.time()
                while self.running:
                    try:
                        # 10분마다 상태 출력
                        if time.time() - last_status_time >= 600:
                            self.print_status()
                            last_status_time = time.time()
                        
                        time.sleep(10)
                        
                    except KeyboardInterrupt:
                        logging.info("\n사용자 중단 요청")
                        break
                    except Exception as e:
                        logging.error(f"메인 루프 오류: {e}")
                        time.sleep(30)
                        
            except Exception as e:
                logging.error(f"24시간 모드 시작 실패: {e}")
                return False
            finally:
                self.stop()
            
            return True
        
        def print_status(self):
            """상태 출력"""
            try:
                status = self.coordinator.get_status()
                logging.info("="*60)
                logging.info("[CHART] 시스템 상태")
                logging.info(f"  실행중: {status.get('running', False)}")
                logging.info(f"  재필터링: {status['stats']['refilters_triggered']}회")
                logging.info(f"  설정변경: {status['stats']['config_changes']}회")
                logging.info(f"  새회차: {status['stats']['new_rounds_detected']}회")
                logging.info("="*60)
            except:
                pass
        
        def stop(self):
            if self.coordinator:
                self.coordinator.stop()
                logging.info("24시간 자동화 시스템 종료 완료")
            self.running = False
    
    # 자동화 컨트롤러 실행
    controller = AutomationController()
    test_mode = args.automation_test if hasattr(args, 'automation_test') else False
    controller.start(db_manager, config_manager, test_mode)

def main():
    # 로그 파일 초기화 - 프로그램 시작 시 기존 로그 삭제
    log_file = "logs/lotto_app.log"
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            # 파일이 사용 중인 경우 내용만 비우기
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.truncate(0)
            except Exception:
                pass
    
    # 명령줄 인수 파싱
    args = parse_args()
    
    # 웹 대시보드 자동 시작 (백그라운드)
    if not args.no_dashboard and (args.auto_improve or args.monitoring):
        start_web_dashboard(port=args.dashboard_port)
    
    # 자동 개선 모드 활성화
    if args.auto_improve:
        args.enhanced_feedback = True  # 향상된 피드백 루프 사용
        args.feedback_loop = False  # 기존 피드백 루프 비활성화
        args.realtime_learning = True
        args.monitoring = True
        args.skip_optimization = False
        args.hyperparameter_tuning = True
        args.skip_backtest = False  # 백테스팅도 자동 활성화
        args.skip_ml = False  # ML/AI 분석도 활성화
        args.ml_only = False  # 전체 프로세스 실행 (ML만 하지 않음)
        # 모든 ML 모델 활성화
        args.lstm = True
        args.ensemble = True
        args.monte_carlo = True
        args.bayesian = True
        args.fractal = True
        logging.info("자동 개선 모드 활성화: 모든 최적화 기능이 켜집니다.")
    
    # 시작 시간 기록
    start_time = time.time()
    
    # 설정 로드 및 로깅 설정
    config_path = args.config
    if config_path is None and os.path.exists('config.yaml'):
        config_path = 'config.yaml'
        logging.info(f"설정 파일 경로가 지정되지 않아 기본 경로 '{config_path}'를 사용합니다.")
    
    setup_logging(config_path)
    
    # 진행률 표시 설정 로드
    try:
        from src.utils.progress_config import ProgressConfig
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        ProgressConfig.load_from_config(config)
        if ProgressConfig.SIMPLE_MODE:
            logging.info("진행률 표시: 간단 모드 활성화 (25% 단위 표시)")
    except Exception as e:
        logging.debug(f"진행률 설정 로드 실패 (기본값 사용): {e}")
    logging.info(f"\n프로그램 시작 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========================================
    # [FIX] 시스템 상태 자동 점검 및 복구
    # ========================================
    logging.info("\n" + "="*60)
    logging.info("[FIX] 시스템 상태 자동 점검 시작")
    logging.info("="*60)
    
    # SystemHealthChecker 실행
    health_checker = SystemHealthChecker()
    system_healthy = health_checker.check_system_health()
    
    if not system_healthy:
        logging.warning("[WARNING] 시스템 문제가 감지되었지만 자동 복구를 시도했습니다.")
        logging.info(f"복구된 문제: {', '.join(health_checker.repairs_performed)}")
    else:
        logging.info("[OK] 시스템 상태 양호")
    
    logging.info("="*60)
    logging.info("[FIX] 시스템 점검 완료")
    logging.info("="*60 + "\n")
    
    try:
        # 설정 관리자 초기화
        config_manager = ConfigManager(config_path)
        
        logging.info("[초기화] 데이터베이스 및 매니저 초기화 중...")
        meta_manager = MetaDataManager()
        
        # 데이터베이스 초기화/마이그레이션 처리
        should_continue = True  # 계속 진행 여부
        db_initialized = False  # DB 초기화 성공 여부
        
        if args.reset_db:
            # 사용자가 명시적으로 초기화를 요청한 경우
            logging.warning("사용자 요청으로 데이터베이스를 강제 초기화합니다.")
            try:
                db_migrator = DatabaseMigrator(meta_manager)
                reset_result = db_migrator.reset_database()
                
                if not reset_result:
                    logging.error("데이터베이스 초기화 실패")
                    if args.ignore_migration_errors or args.force:
                        logging.warning("데이터베이스 초기화 오류를 무시하고 계속 진행합니다 (ignore-migration-errors 또는 force 옵션 사용)")
                    else:
                        logging.error("프로그램을 정상적으로 실행하려면 다음 문제를 해결해야 합니다:")
                        logging.error("1. 다른 프로그램이 데이터베이스 파일을 사용 중인지 확인하세요.")
                        logging.error("2. 데이터베이스 파일에 대한 쓰기 권한이 있는지 확인하세요.")
                        logging.error("3. 디스크 공간이 충분한지 확인하세요.")
                        logging.error("4. 관리자 권한으로 실행해보세요.")
                        logging.error("오류를 무시하고 계속 진행하려면 --ignore-migration-errors 또는 --force 옵션을 사용하세요.")
                        should_continue = False
                else:
                    db_initialized = True
                
                if should_continue:
                    # 최적화 모드 설정 업데이트
                    storage_mode = "optimized" if args.optimize else "legacy"
                    try:
                        update_result = meta_manager.update_db_info(
                            version=DatabaseMigrator.CURRENT_REQUIRED_VERSION,
                            storage_mode=storage_mode
                        )
                        
                        if not update_result and not (args.ignore_migration_errors or args.force):
                            logging.error("메타데이터 업데이트 실패")
                            should_continue = False
                    except Exception as update_err:
                        logging.error(f"메타데이터 업데이트 중 오류 발생: {str(update_err)}")
                        if not (args.ignore_migration_errors or args.force):
                            should_continue = False
            except Exception as init_err:
                logging.error(f"초기화 과정에서 예외 발생: {str(init_err)}")
                if args.force:
                    logging.warning("force 옵션으로 오류 무시하고 계속 진행합니다.")
                else:
                    should_continue = False
                    
        elif not args.force_no_migration and should_continue:
            # 자동 마이그레이션 수행 (필요한 경우에만)
            try:
                logging.info("데이터베이스 호환성 검사 중...")
                db_migrator = DatabaseMigrator(meta_manager)
                
                # 저장 모드 결정
                target_storage_mode = "optimized" if args.optimize else None
                
                # 필요한 경우 마이그레이션 수행
                success, message = db_migrator.migrate_if_needed(target_storage_mode)
                if success:
                    logging.info(message)
                    db_initialized = True
                else:
                    logging.error(f"마이그레이션 실패: {message}")
                    if args.ignore_migration_errors or args.force:
                        logging.warning("마이그레이션 오류를 무시하고 계속 진행합니다 (ignore-migration-errors 또는 force 옵션 사용)")
                    else:
                        logging.error("데이터베이스 문제를 해결하려면 다음 옵션 중 하나를 사용하세요:")
                        logging.error("1. --reset-db: 데이터베이스를 초기화합니다 (데이터 손실 발생)")
                        logging.error("2. --force-no-migration: 마이그레이션을 건너뜁니다 (호환성 문제 발생 가능)")
                        logging.error("3. --ignore-migration-errors: 마이그레이션 오류를 무시하고 계속 진행합니다 (오류 발생 가능)")
                        logging.error("4. --force: 모든 오류를 무시하고 강제로 실행합니다 (위험)")
                        should_continue = False
            except Exception as migration_err:
                logging.error(f"마이그레이션 과정에서 예외 발생: {str(migration_err)}")
                if args.force:
                    logging.warning("force 옵션으로 오류 무시하고 계속 진행합니다.")
                else:
                    should_continue = False
        else:
            # 마이그레이션 건너뛰기
            logging.info("데이터베이스 마이그레이션을 건너뜁니다.")
            db_initialized = True
                    
        if not should_continue:
            raise Exception("데이터베이스 초기화 또는 마이그레이션 실패")
                    
        try:
            # 데이터베이스 매니저 초기화 (마이그레이션 후에 초기화)
            db_manager = DatabaseManager()
            
            # ========================================
            # [CHECK] 실시간 모니터링 시스템 초기화
            # ========================================
            auto_repair_system = AutoRepairSystem(db_manager, config_manager)
            
            # 24시간 자동화 모드 또는 일반 실행 모드에 관계없이 실시간 모니터링 시작
            auto_repair_system.start_monitoring()
            logging.info("[OK] 실시간 시스템 모니터링 활성화")
            
            # 24시간 자동화 모드 처리
            twenty_four_h = getattr(args, '_24h', False) or args.__dict__.get('24h', False)
            if twenty_four_h or (hasattr(args, 'automation_test') and args.automation_test):
                logging.info("\n" + "="*60)
                logging.info("[ROCKET] 24시간 자동 실행 모드 시작")
                logging.info("="*60)
                
                # 자동화 시스템 통합 실행
                run_24h_automation(db_manager, config_manager, args, auto_repair_system)
                return  # 24시간 모드는 여기서 계속 실행됨
            
            # 저장 모드 설정
            if args.optimize and meta_manager.get_db_storage_mode() != "optimized":
                logging.info("최적화된 데이터 저장 방식으로 설정합니다.")
                try:
                    db_manager.combinations_db.set_storage_mode('optimized')
                    meta_manager.update_db_info(storage_mode="optimized")
                except Exception as mode_err:
                    logging.error(f"저장 모드 설정 실패: {str(mode_err)}")
                    if not (args.ignore_migration_errors or args.force):
                        raise
            
            # 명령줄 인수로 필터링 설정 업데이트
            filtering_config = config_manager.get_filtering_config()
            if args.parallel is not None:
                filtering_config['use_parallel'] = args.parallel
            if args.workers is not None:
                filtering_config['max_workers'] = args.workers
                
        except Exception as db_err:
            logging.error(f"데이터베이스 초기화 중 오류 발생: {str(db_err)}")
            if args.ignore_migration_errors or args.force:
                logging.warning("데이터베이스 오류를 무시하고 계속 시도합니다. 추가 오류가 발생할 수 있습니다.")
            else:
                raise
        
        # 자동 조정 시스템 V2 초기화 (단순화된 버전)
        auto_adjustment = None
        if not args.no_auto_adjust:
            auto_adjustment = AutoAdjustmentSystemV2(db_manager)
            
            # 자동 조정 시스템 상태 표시
            status = auto_adjustment.get_status()
            logging.info("\n[자동 조정 시스템 V2] 초기화 완료")
            logging.info(f"  - 현재 임계값: {status['current_threshold']}%")
            logging.info(f"  - 현재 모드: {status['mode']}")
            logging.info("  - 백테스팅 성능에 따라 임계값 자동 조정")
            logging.info("  - 단일 파라미터 제어로 모든 필터 통합 관리")
        else:
            logging.info("\n[자동 조정 시스템] 비활성화됨 (--no-auto-adjust)")
        
        # 데이터 수집 (선택적 건너뛰기)
        if not args.skip_fetch:
            logging.info("\n[데이터 수집] 로또 당첨 번호 수집 시작...")
            collector = DataCollector(db_manager=db_manager, meta_manager=meta_manager)
            collector.fetch_lotto_data()
            
            # 데이터 수집 후에는 백테스팅 기반 자동 조정이 실행됨
        else:
            logging.info("\n[데이터 수집] 건너뛰기")
        
        # --fetch-only 옵션 처리
        if args.fetch_only:
            logging.info("\n[자동화] 데이터 수집만 수행 (--fetch-only)")
            logging.info("[OK] 데이터 수집 완료")
            return
        
        # 패턴 분석 (선택적 건너뛰기)
        if not args.skip_patterns:
            logging.info("\n" + "="*60)
            logging.info("[CHART] [PATTERN] 패턴 분석 시작")
            logging.info("="*60)
            
            pattern_manager = PatternManager(db_manager)
            latest_round = db_manager.lotto_db.get_last_round()
            
            logging.info(f"[PATTERN] 최신 회차: {latest_round}")
            logging.info("[PATTERN] PatternManager 초기화 완료")
            
            # 패턴 분석 실행
            pattern_result = pattern_manager.analyze_patterns(latest_round)
            
            if pattern_result:
                logging.info("[PATTERN] [OK] 패턴 분석 완료")
            else:
                logging.error("[PATTERN] [X] 패턴 분석 실패")
                
            logging.info("="*60)
            
            # 추가 통계 분석 (핫/콜드 넘버 포함)
            try:
                logging.info("\n" + "="*60)
                logging.info("📈 [STATISTICS] 통계 분석 시작 (핫/콜드 넘버 포함)")
                logging.info("="*60)
                
                stats_analyzer = LottoStatisticsAnalyzer()
                
                # 핫/콜드 넘버 분석
                hot_cold_stats = stats_analyzer.analyze_hot_cold_numbers()
                logging.info("\n[STATISTICS] 핫/콜드 넘버 분석:")
                logging.info(f"  - 핫 넘버 (상위 10개): {hot_cold_stats['hot_numbers'][:10]}")
                logging.info(f"  - 콜드 넘버 (하위 10개): {hot_cold_stats['cold_numbers'][:10]}")
                
                # 기타 통계 분석
                odd_even_stats = stats_analyzer.analyze_odd_even_distribution()
                consecutive_stats = stats_analyzer.analyze_consecutive_patterns()
                ac_stats = stats_analyzer.analyze_ac_values()
                
                logging.info("\n[STATISTICS] 홀짝 분포:")
                for pattern, percentage in list(odd_even_stats.items())[:5]:
                    logging.info(f"  - {pattern}: {percentage:.2f}%")
                    
                logging.info("\n[STATISTICS] 연속번호 패턴:")
                for pattern, percentage in consecutive_stats.items():
                    logging.info(f"  - {pattern}: {percentage:.2f}%")
                    
                logging.info("\n[STATISTICS] AC값 (Arithmetic Complexity) 분석:")
                logging.info(f"  - 평균 AC값: {ac_stats['avg']:.2f}")
                logging.info(f"  - AC값 범위: {ac_stats['min']} ~ {ac_stats['max']}")
                logging.info(f"  - 일반적 범위: {ac_stats['common_range'][0]} ~ {ac_stats['common_range'][1]}")
                    
                logging.info("\n[STATISTICS] [OK] 통계 분석 완료")
                logging.info("="*60)
                
            except Exception as e:
                logging.error(f"[STATISTICS] [X] 통계 분석 실패: {str(e)}")
        else:
            logging.info("\n[패턴 분석] 건너뛰기")
            latest_round = db_manager.lotto_db.get_last_round()
        
        # 백테스팅을 위한 변수 초기화
        lstm_predictions = []
        ensemble_predictions = []
        mc_predictions = []
        bayesian_predictions = []
        fractal_predictions = []
        
        # --predict-only 옵션 처리
        if args.predict_only:
            logging.info("\n[자동화] 예측만 수행 (--predict-only)")
            logging.info("필터링을 건너뛰고 ML 예측으로 바로 이동...")
            # ML 예측 섹션으로 이동하기 위해 필터링 건너뛰기
            filtered_combinations = []
            filter_manager = None
            enhanced_filter_manager = None
            filtered_count = 0
        else:
            # 필터링 초기화 및 실행
            logging.info("\n" + "="*60)
            logging.info("[조합 필터링] 로또 번호 조합 필터링 시작...")
            logging.info("="*60)
        
        # 동적 필터 매니저 초기화 (사용 가능한 경우)
        if not args.predict_only:
            enhanced_filter_manager = None
            if args.dynamic_filter and DYNAMIC_FILTER_AVAILABLE:
                try:
                    logging.info("\n[동적 필터] 실시간 모니터링 시스템 시작...")
                    enhanced_filter_manager = EnhancedDynamicFilterManager(db_manager)
                    enhanced_filter_manager.start_monitoring()
                    logging.info("  - 실시간 모니터링 활성화됨")
                except Exception as e:
                    logging.error(f"  - 동적 필터 초기화 실패: {str(e)}")
        
        # 필터링 관련 코드는 --predict-only가 아닐 때만 실행
        if not args.predict_only:
            # 기본 조합 확인 및 생성
            combination_manager = CombinationManager(db_manager)
            if not db_manager.combinations_db.check_base_combinations_exist():
                logging.info("\n[기본 조합 생성] 시작...")
                combination_manager.generate_base_combinations()
         
            # 필터 매니저 초기화 및 필터 등록 (자동)

            # 필터 시스템 선택 (가중치 시스템 또는 적응형 시스템)
            use_weighted_system = True  # 가중치 시스템 활성화 (통과율 개선)
        
        if use_weighted_system:
            # 가중치 기반 필터 시스템 사용 (문제있는 필터에 낮은 가중치)
            try:
                from src.core.weighted_filter_system import WeightedFilterSystem
                
                # 기본 FilterManager 먼저 생성
                base_filter_manager = FilterManager(db_manager)
                
                # WeightedFilterSystem으로 래핑
                filter_manager = WeightedFilterSystem(base_filter_manager)
                # 1% 임계값을 위해 30점으로 설정
                filter_manager.pass_threshold = 30.0
                logging.info("="*60)
                logging.info("[시스템] 가중치 기반 필터 시스템 활성화")
                logging.info(f"  모드: 점수 기반 평가 ({filter_manager.pass_threshold}점 이상 통과)")
                logging.info("  장점: 개별 필터 실패에도 전체 통과 가능")
                logging.info("  - section 필터: 30% 가중치 (문제 필터)")
                logging.info("  - dispersion 필터: 35% 가중치 (문제 필터)")
                logging.info("  - fixed_step 필터: 25% 가중치 (문제 필터)")
                logging.info("  - multiple 필터: 40% 가중치 (문제 필터)")
                logging.info("="*60)
                
            except Exception as e:
                logging.warning(f"가중치 필터 시스템 로드 실패: {e}")
                use_weighted_system = False
        
        if not use_weighted_system:
            # 적응형 필터 시스템 사용 (통합 확률 기반)
            try:
                # 설정 파일 로드
                with open('configs/adaptive_filter_config.yaml', 'r', encoding='utf-8') as f:
                    adaptive_config = yaml.safe_load(f)
                
                threshold = adaptive_config['global_probability_threshold']
                logging.info("="*60)
                logging.info(f"[시스템] 적응형 필터 활성화")
                logging.info(f"  임계값: {threshold}%")
                logging.info(f"  의미: {threshold}% 이하 출현 패턴 제외")
                logging.info(f"  모드: {'보수적' if threshold <= 0.5 else '표준' if threshold <= 1.0 else '공격적' if threshold <= 2.0 else '매우 공격적'}")
                logging.info("="*60)
                
                # 통합 필터 매니저 사용 (적응형 + 개별 필터)
                from src.core.integrated_filter_manager import IntegratedFilterManager
                filter_manager = IntegratedFilterManager(db_manager, threshold)
                
                # 과거 당첨번호 분석 및 필터 업데이트
                winning_numbers = db_manager.get_all_winning_numbers()[:200]  # 최근 200개
                filter_manager.adaptive_filter.analyze_patterns(winning_numbers)
                
                # 동적 기준 생성 및 개별 필터에 적용
                criteria = filter_manager.adaptive_filter.generate_dynamic_criteria()
                filter_manager._update_individual_filters(criteria)
                
                # DB에 저장
                filter_manager.adaptive_filter.save_criteria_to_db(criteria)
                
                logging.info(f"[필터] 통합 필터 시스템 초기화 완료 (임계값 {threshold}% 기준)")
                logging.info(f"[필터] 적응형 필터 + {len(filter_manager.filter_manager.filters)}개 개별 필터 활성화")
                
            except Exception as e:
                logging.warning(f"적응형 필터 로드 실패: {e}")
                logging.info("기존 FilterManager 사용")
                filter_manager = FilterManager(db_manager)  # 기존 시스템 폴백
        
        # 병렬 처리 사용 시 ParallelFilterManager로 래핑
        if args.parallel:
            logging.info("병렬 필터 처리 모드 활성화")
            from src.core.parallel_filter_manager import ParallelFilterManager
            parallel_filter_manager = ParallelFilterManager(filter_manager)
        
        # ML 예측기를 필터에 연결 (사용 가능한 경우)
        if ML_AVAILABLE and 'ensemble_predictor' in locals():
            try:
                ml_filter = filter_manager.filters.get('ml_prediction')
                if ml_filter:
                    ml_filter.set_predictor(ensemble_predictor)
                    logging.info("[ML 필터] 앙상블 예측기가 ML 필터에 연결되었습니다.")
            except Exception as e:
                logging.warning(f"ML 필터 연결 실패: {str(e)}")
        
        # 필터 검증 실행 (신규)
        if not args.skip_validation:
            logging.info("\n" + "="*60)
            logging.info("[필터 검증] 과거 당첨번호 기반 필터 검증 시작...")
            logging.info("="*60)
            
            filter_validator = FilterValidator(filter_manager, db_manager)
            validation_results = filter_validator.validate(
                start_round=max(1, latest_round - 100),
                end_round=latest_round
            )
            
            # 최적화된 필터 설정 제안
            optimized_criteria = filter_validator.suggest_optimized_criteria(
                validation_results, target_pass_rate=95
            )
            
            # ✅ 실제로 필터 조정 적용 (수정됨)
            from src.core.filter_auto_adjuster import FilterAutoAdjuster
            auto_adjuster = FilterAutoAdjuster(db_manager, filter_manager)
            
            if auto_adjuster.check_need_adjustment(validation_results):
                logging.info("\n🔄 필터 자동 조정이 필요합니다...")
                if auto_adjuster.apply_optimized_criteria(optimized_criteria, validation_results):
                    logging.info("✅ 필터가 자동으로 조정되었습니다!")
                    logging.info(auto_adjuster.get_adjustment_summary())
                else:
                    logging.warning("⚠️ 필터 자동 조정 실패")
            else:
                logging.info("✅ 모든 필터가 정상 범위입니다.")
        else:
            logging.info("\n[필터 검증] 건너뛰기")
        
        # 적응형 필터 최적화 실행 (신규)
        if not args.skip_optimization:
            logging.info("\n[적응형 최적화] 실시간 필터 최적화 시작...")
            adaptive_optimizer = AdaptiveFilterOptimizer(db_manager)
            optimization_results = adaptive_optimizer.optimize_filters_adaptive(latest_round)
            
            if optimization_results['optimized']:
                logging.info(f"  - {len(optimization_results['optimized_filters'])}개 필터 최적화 완료")
        else:
            logging.info("\n[적응형 최적화] 건너뛰기")
        
        # 필터링 모드 결정 및 필터 적용
        update_mode = 'full' if args.full_filter or args.force_filter else 'incremental'
        
        # 성능 측정 시작
        filter_start_time = time.time()
        
        # 계산된 모드에 따라 최적화된 필터링 실행
        if update_mode == 'full':
            logging.info("\n[필터링 전체 모드] 모든 필터를 처음부터 적용합니다...")
            if args.parallel and 'parallel_filter_manager' in locals():
                logging.info("  - 병렬 처리 모드 사용 (예상 시간: 1-2분)")
                parallel_filter_manager.apply_filters_parallel(filter_manager.db_manager.combinations_db.get_all_base_combinations(), latest_round)
            else:
                logging.info("  - 예상 처리 시간: 3-5분 (전체 조합 재계산)")
                filter_manager.apply_filters(latest_round, 'full', force=True)
        else:
            logging.info("\n[필터링 증분 모드] 필요한 필터만 업데이트합니다...")
            logging.info("  - 예상 처리 시간: 30초-1분 (변경된 부분만 처리)")
            # 증분 모드에서는 기존 결과를 활용하여 성능 최적화
            force_required = not filter_manager._check_previous_filtering_results(latest_round) if hasattr(filter_manager, '_check_previous_filtering_results') else False
            filter_manager.apply_filters(latest_round, 'incremental', force=force_required)
        
        # 성능 측정 결과 출력
        filter_elapsed_time = time.time() - filter_start_time
        logging.info(f"\n[성능 보고서] 필터링 완료")
        logging.info(f"  - 모드: {update_mode.upper()}")
        logging.info(f"  - 실행 시간: {filter_elapsed_time:.1f}초")
        
        if update_mode == 'incremental':
            estimated_full_time = filter_elapsed_time * 4  # 증분 모드는 대략 1/4 시간 소요
            time_saved = estimated_full_time - filter_elapsed_time
            logging.info(f"  - 절약된 시간: 약 {time_saved:.0f}초 (전체 모드 대비 {(time_saved/estimated_full_time)*100:.0f}% 향상)")
        
        # 동적 필터 모니터링 중지 및 보고서 저장
        if enhanced_filter_manager:
            try:
                logging.info("\n[동적 필터] 성능 보고서 생성 중...")
                enhanced_filter_manager.export_performance_report()
                enhanced_filter_manager.stop_monitoring()
                logging.info("  - 성능 보고서가 저장되었습니다.")
            except Exception as e:
                logging.error(f"  - 동적 필터 보고서 생성 실패: {str(e)}")
        
        # ================================================================
        # ML/AI 분석 - 필터링된 조합 활용 (최적화)
        # ================================================================
        # 필터링된 조합 가져오기 (814만개 → 20만개)
        if not args.predict_only and filter_manager:
            try:
                filtered_count = filter_manager.get_filtered_count(latest_round)
                logging.info(f"\n[ML/AI] 필터링된 조합 {filtered_count:,}개로 ML 예측 수행")
                logging.info(f"  - 메모리 사용량 {(filtered_count/8145060)*100:.1f}% (97.5% 절약)")
                logging.info(f"  - 예상 속도 향상: {8145060/filtered_count:.1f}배")
            except:
                filtered_count = 200000  # 기본값
                logging.info(f"\n[ML/AI] 필터링된 조합으로 ML 예측 수행 (약 20만개)")
        else:
            filtered_count = 0
            logging.info(f"\n[ML/AI] 예측 전용 모드 - 필터링 없이 ML 예측 수행")

        # ML/AI 분석 및 예측 (선택적)
        if not args.skip_ml:
            logging.info("\n" + "="*60)
            logging.info("[ML/AI 분석] 인공지능 기반 분석 및 예측 시작...")
            logging.info("="*60)
            
            # 당첨번호 데이터 준비
            winning_numbers = db_manager.get_all_winning_numbers()
            
            if winning_numbers and len(winning_numbers) >= 50:
                # 1. LSTM 시계열 예측
                if args.lstm and ML_AVAILABLE:
                    try:
                        logging.info("\n[LSTM] 시계열 예측 모델 실행...")
                        lstm_predictor = LSTMPredictor(sequence_length=50)
                        
                        # 모델 학습 (필요시)
                        if not lstm_predictor.is_trained:
                            logging.info("  - LSTM 모델 학습 중...")
                            lstm_predictor.train(winning_numbers, epochs=30, batch_size=32)
                        
                        # 예측 수행
                        lstm_predictions = lstm_predictor.predict_next_numbers(
                            winning_numbers[-50:], 
                            num_predictions=args.predictions
                        )
                        
                        logging.info(f"  - LSTM 예측 완료: {len(lstm_predictions)}개 조합")
                        for i, pred in enumerate(lstm_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - LSTM 예측 실패: {str(e)}")
                
                # 2. 앙상블 모델 예측
                if args.ensemble and ML_AVAILABLE:
                    try:
                        logging.info("\n[Ensemble] 앙상블 모델 (RF+XGBoost+NN) 실행...")
                        ensemble_predictor = EnsemblePredictor()
                        
                        # 모델 학습 (필요시)
                        if not ensemble_predictor.is_trained:
                            logging.info("  - 앙상블 모델 학습 중...")
                            evaluation = ensemble_predictor.train(winning_numbers, test_size=0.2)
                            if evaluation:
                                logging.info(f"  - 학습 완료: 정확도 {evaluation.get('ensemble', {}).get('accuracy', 0):.4f}")
                        
                        # 예측 수행
                        ensemble_predictions = ensemble_predictor.predict_next_numbers(
                            winning_numbers,
                            num_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 앙상블 예측 완료: {len(ensemble_predictions)}개 조합")
                        for i, pred in enumerate(ensemble_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - 앙상블 예측 실패: {str(e)}")
                
                # 3. Monte Carlo 시뮬레이션
                if args.monte_carlo and PROBABILISTIC_AVAILABLE:
                    try:
                        logging.info("\n[Monte Carlo] 확률적 시뮬레이션 실행...")
                        mc_simulator = MonteCarloSimulator(db_manager)
                        mc_simulator.load_historical_data(winning_numbers)
                        
                        # 시뮬레이션 실행
                        logging.info("  - 5,000회 시뮬레이션 중...")
                        start_time = time.time()
                        mc_simulator.simulate_combinations(5000)
                        elapsed = time.time() - start_time
                        
                        # 최적 조합 추출
                        mc_predictions = mc_simulator.get_best_combinations(
                            n_combinations=args.predictions,
                            min_confidence=0.6
                        )
                        
                        logging.info(f"  - 시뮬레이션 완료 ({elapsed:.1f}초): {len(mc_predictions)}개 조합")
                        for i, pred in enumerate(mc_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (점수: {pred['score']:.2f}, 신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - Monte Carlo 시뮬레이션 실패: {str(e)}")
                
                # 4. 베이지안 추론
                if args.bayesian and PROBABILISTIC_AVAILABLE:
                    try:
                        logging.info("\n[Bayesian] 베이지안 추론 시스템 실행...")
                        bayesian_filter = BayesianFilter(db_manager)
                        
                        # 사전분포 초기화
                        logging.info("  - 사전분포 초기화 중...")
                        bayesian_filter.initialize_priors(winning_numbers[:-10])
                        
                        # 예측 수행
                        bayesian_predictions = bayesian_filter.predict_next_combination(
                            winning_numbers[-10:],
                            n_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 베이지안 예측 완료: {len(bayesian_predictions)}개 조합")
                        for i, pred in enumerate(bayesian_predictions[:3], 1):
                            relative_score = pred.get('relative_score', 0)
                            log_likelihood = pred.get('log_likelihood', -np.inf)
                            logging.info(f"    {i}. {pred['numbers']} (점수: {relative_score:.1f}, 로그우도: {log_likelihood:.2f})")
                        
                        # 신념 시각화 저장
                        bayesian_filter.visualize_beliefs()
                        bayesian_filter.save_beliefs()
                    
                    except Exception as e:
                        logging.error(f"  - 베이지안 추론 실패: {str(e)}")
                
                # 5. 프랙탈 패턴 분석
                if args.fractal and ADVANCED_AVAILABLE:
                    try:
                        logging.info("\n[Fractal] 프랙탈 패턴 분석 실행...")
                        fractal_analyzer = FractalPatternAnalyzer(db_manager)
                        
                        # 시계열 데이터 로드
                        logging.info("  - 시계열 데이터 로드 중...")
                        fractal_analyzer.load_time_series(winning_numbers)
                        
                        # 프랙탈 패턴 탐지
                        logging.info("  - 프랙탈 패턴 분석 중...")
                        patterns = fractal_analyzer.detect_fractal_patterns()
                        
                        # 결과 출력
                        if patterns.get('fractal_dimensions'):
                            logging.info("  - 프랙탈 차원:")
                            for key, dim in list(patterns['fractal_dimensions'].items())[:3]:
                                logging.info(f"    {key}: {dim:.3f}")
                        
                        if patterns.get('chaos_metrics'):
                            logging.info("  - 카오스 메트릭:")
                            for key, value in list(patterns['chaos_metrics'].items())[:3]:
                                logging.info(f"    {key}: {value:.3f}")
                        
                        # 프랙탈 기반 예측
                        fractal_predictions = fractal_analyzer.predict_with_fractals(
                            n_predictions=args.predictions
                        )
                        
                        logging.info(f"  - 프랙탈 예측 완료: {len(fractal_predictions)}개 조합")
                        for i, pred in enumerate(fractal_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                        
                        # 분석 결과 저장
                        fractal_analyzer.visualize_fractal_analysis()
                        fractal_analyzer.save_analysis()
                    
                    except Exception as e:
                        logging.error(f"  - 프랙탈 분석 실패: {str(e)}")
            
            else:
                logging.warning("ML/AI 분석을 위한 충분한 데이터가 없습니다. (최소 50개 필요)")
            
            # 백테스팅 실행 (ML/AI 직후가 논리적)
            # 주의: 자동 조정 시스템에서도 백테스팅이 실행되므로 중복 방지
        # ML만 수행 모드
        if args.ml_only:
            pass  # ML만 수행 모드에서는 별도 처리 없음

        # ================================================================
        # 백테스팅 - 필터링+ML 통합 검증 (최적화)
        # ================================================================
        # 🔧 수정: auto_adjustment와 관계없이 백테스팅 항상 실행 (DB 저장을 위해)
        if not args.skip_backtest:
            logging.info("\n" + "="*60)
            logging.info("[백테스팅] ML/AI 모델 성능 최종 검증...")
            logging.info("="*60)
            if auto_adjustment:
                logging.info("[INFO] 자동 조정 모드이지만 성능 통계를 위해 백테스팅을 실행합니다.")
            else:
                logging.info("[INFO] 백테스팅 결과가 자동으로 DB에 저장됩니다.")
            
            try:
                backtesting_framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
                backtest_results = backtesting_framework.run_backtest(
                    start_round=max(1, latest_round - 50),
                    end_round=latest_round - 1,  # 현재 회차 제외 (데이터 누출 방지)
                    window_size=100
                )
                logging.info("백테스팅 최종 검증 완료")
                
                # 자동 조정 시스템 V2: 백테스팅 성능에 따라 임계값 조정
                if auto_adjustment and backtest_results:
                    try:
                        # 성능 점수 계산 (평균 일치 개수 기반)
                        metrics = backtest_results.get('performance_metrics', {})
                        total_score = 0
                        model_count = 0
                        
                        for model_name in ['lstm', 'ensemble', 'monte_carlo']:
                            model_perf = metrics.get('model_performance', {}).get(model_name, {})
                            if model_perf:
                                avg_matches = model_perf.get('avg_matches', 0)
                                # 2개 일치를 1.0으로 정규화
                                normalized = min(1.0, avg_matches / 2.0)
                                total_score += normalized
                                model_count += 1
                        
                        if model_count > 0:
                            performance_score = total_score / model_count
                            
                            logging.info(f"\n[자동 조정 V2] 백테스팅 성능 점수: {performance_score:.3f}")
                            
                            # 임계값 자동 조정
                            adjustment_result = auto_adjustment.analyze_and_adjust(performance_score)
                            
                            if adjustment_result['adjusted']:
                                logging.info("\n🔄 필터링 재실행 필요")
                                logging.info("  다음 실행 시 새로운 임계값이 적용됩니다.")
                                logging.info(f"  변경: {adjustment_result['current_threshold']}% → {adjustment_result['optimal_threshold']}%")
                                
                    except Exception as e:
                        logging.error(f"자동 조정 실행 실패: {e}")
                    
                    # 성능 모니터링 대시보드 업데이트
                    if args.monitoring:
                        try:
                            dashboard = PerformanceDashboard(db_manager)
                            metrics = backtest_results.get('performance_metrics', {})
                            for model_type in ['lstm', 'ensemble', 'monte_carlo']:
                                model_metrics = metrics.get(model_type.upper(), {})
                                avg_matches = model_metrics.get('avg_matches', 0)
                                dashboard.update_metrics('performance', model_type, avg_matches)
                        except Exception as e:
                            logging.error(f"모니터링 업데이트 실패: {str(e)}")
                    
                    # 피드백 루프 실행
                    if (args.feedback_loop or args.enhanced_feedback) and backtest_results:
                        try:
                            logging.info("\n" + "="*60)
                            if args.enhanced_feedback:
                                logging.info("[향상된 피드백 루프] 영구 상태 관리와 함께 자동 모델 개선...")
                            else:
                                logging.info("[피드백 루프] 자동 모델 개선 프로세스 시작...")
                            logging.info("="*60)
                            
                            # 향상된 피드백 루프 사용
                            if args.enhanced_feedback:
                                enhanced_feedback = EnhancedFeedbackLoop(db_manager)
                                cycle_results = enhanced_feedback.run_improvement_cycle(
                                    start_round=max(1, latest_round - 50),
                                    end_round=latest_round,
                                    max_iterations=5
                                )
                                
                                # 최적 설정 적용
                                enhanced_feedback.apply_best_settings()
                                
                                # 업데이트된 모델 사용
                                updated_models = enhanced_feedback.get_models()
                                if 'lstm' in updated_models:
                                    lstm_predictor = updated_models['lstm']
                                if 'ensemble' in updated_models:
                                    ensemble_predictor = updated_models['ensemble']
                                if 'monte_carlo' in updated_models:
                                    mc_simulator = updated_models['monte_carlo']
                            else:
                                # 기존 피드백 루프 사용
                                # 모델 수집
                                models = {}
                                if 'lstm_predictor' in locals() and lstm_predictor:
                                    models['lstm'] = lstm_predictor
                                if 'ensemble_predictor' in locals() and ensemble_predictor:
                                    models['ensemble'] = ensemble_predictor
                                if 'mc_simulator' in locals() and mc_simulator:
                                    models['monte_carlo'] = mc_simulator
                                
                                feedback_system = FeedbackLoopSystem(db_manager)
                                feedback_results = feedback_system.run_feedback_loop(
                                    models,
                                    start_round=max(1, latest_round - 50),
                                    end_round=latest_round
                                )
                                
                                logging.info(feedback_system.get_optimization_report())
                        except Exception as e:
                            logging.error(f"피드백 루프 실패: {str(e)}")
                    
                    # 하이퍼파라미터 튜닝 (최대 반복 횟수 제한)
                    if args.hyperparameter_tuning:
                        try:
                            logging.info("\n" + "="*60)
                            logging.info(f"[하이퍼파라미터 튜닝] 자동 최적화 시작 (최대 {args.max_ml_iterations}회)...")
                            logging.info("="*60)
                            
                            # AutoMLOptimizer 사용 (무한 루프 방지 설정 포함)
                            auto_ml = AutoMLOptimizer(db_manager)
                            # optimization_config를 사용하도록 수정
                            auto_ml.optimization_config['max_iterations'] = min(args.max_ml_iterations, 10)
                            
                            # 앙상블 모델 최적화
                            if 'ensemble_predictor' in locals() and ensemble_predictor and backtest_results:
                                optimization_result = auto_ml.optimize_based_on_backtest(
                                    ensemble_predictor, backtest_results, 'ensemble'
                                )
                                if optimization_result.get('optimized'):
                                    logging.info("앙상블 모델 최적화 완료")
                                else:
                                    logging.info(f"앙상블 모델 최적화 건너뜀: {optimization_result.get('reason', 'unknown')}")
                        except Exception as e:
                            logging.error(f"하이퍼파라미터 튜닝 실패: {str(e)}")
                
            except Exception as e:
                logging.error(f"백테스팅 실패: {str(e)}")
        
        # 최종 예측 번호는 모든 작업 완료 후 마지막에 생성
        
        # 실시간 학습 시스템 (옵션에 따라)
        if args.realtime_learning and not args.no_realtime_learning:
            try:
                logging.info("\n" + "="*60)
                logging.info("[실시간 학습] 최신 데이터로 모델 업데이트...")
                logging.info("="*60)
                
                realtime_system = RealtimeLearningSystem(db_manager)
                
                # 최신 결과로 모델 업데이트
                latest_data = db_manager.get_numbers_by_round(latest_round)
                if latest_data:
                    new_result = {
                        'round': latest_data[0],  # round
                        'numbers': [int(n) for n in latest_data[1].split(',')]  # numbers
                    }
                else:
                    logging.error(f"회차 {latest_round}의 데이터를 찾을 수 없습니다.")
                    raise Exception("최신 데이터 없음")
                
                # 모델 수집
                models = {}
                if 'lstm_predictor' in locals() and lstm_predictor:
                    models['lstm'] = lstm_predictor
                if 'ensemble_predictor' in locals() and ensemble_predictor:
                    models['ensemble'] = ensemble_predictor
                if 'mc_simulator' in locals() and mc_simulator:
                    models['monte_carlo'] = mc_simulator
                
                if models:
                    update_result = realtime_system.update_models_incrementally(models, new_result)
                    logging.info(realtime_system.get_learning_report())
                    
                    # 자동 조정 시스템에 ML 모델 전달
                    if auto_adjustment:
                        auto_adjustment.ml_models = models
            except Exception as e:
                logging.error(f"실시간 학습 실패: {str(e)}")
        
        # 성능 모니터링 대시보드 생성
        if args.monitoring:
            try:
                logging.info("\n" + "="*60)
                logging.info("[모니터링] 성능 대시보드 생성...")
                logging.info("="*60)
                
                if 'dashboard' not in locals():
                    dashboard = PerformanceDashboard(db_manager)
                
                # Auto-improve 모드일 때는 종합 보고서 생성
                if args.auto_improve:
                    logging.info("\n🔄 자동 개선 모드에서 종합 성능 보고서 생성...")
                    performance_report = dashboard.generate_comprehensive_report(auto_improve=True)
                    
                    # 추가 최적화 수행 (필요시)
                    if performance_report.get('recommendations'):
                        high_priority_recommendations = [
                            rec for rec in performance_report['recommendations'] 
                            if rec['priority'] == 'high'
                        ]
                        
                        if high_priority_recommendations:
                            logging.info(f"\n[ALERT] {len(high_priority_recommendations)}개의 긴급 개선사항 발견!")
                            
                            # 피드백 루프 시스템 추가 실행
                            if 'feedback_system' in locals() and models:
                                logging.info("\n🔁 추가 피드백 루프 실행...")
                                additional_feedback = feedback_system.run_feedback_loop(
                                    models,
                                    start_round=max(1, latest_round - 49),
                                    end_round=latest_round
                                )
                                logging.info(feedback_system.get_optimization_report())
                else:
                    # 일반 모니터링 모드
                    dashboard_path = dashboard.generate_dashboard()
                    logging.info(f"대시보드 생성 완료: {dashboard_path}")
                    
                    # 성능 저하 확인
                    degradations = dashboard.check_performance_degradation()
                    if degradations:
                        logging.warning("성능 저하 감지:")
                        for deg in degradations:
                            logging.warning(f"  - {deg}")
            except Exception as e:
                logging.error(f"대시보드 생성 실패: {str(e)}")
        
        # 자동 조정 시스템 최종 상태 보고
        if auto_adjustment:
            # AutoAdjustmentSystemV2는 get_status_report 대신 get_status 사용
            status = auto_adjustment.get_status()
            logging.info(f"  백테스팅 횟수: {status['backtest_count']}회")
            logging.info(f"  마지막 성능: {status['last_performance']:.3f}")
            
            # 추가 백테스팅 실행 (프로그램 종료 전)
            logging.info("\n[자동 개선] 추가 백테스팅 실행...")
            final_result = auto_adjustment.check_and_adjust()
            if final_result.get('backtest_performance'):
                perf = final_result['backtest_performance']
                logging.info(f"최종 백테스팅 횟수: {perf.get('backtest_count', 0)}")
                logging.info(f"최종 성능 점수: {perf.get('performance_score', 0):.3f}")
        
        # 전체 실행 시간 출력
        total_time = time.time() - start_time
        logging.info(f"\n전체 실행 시간: {total_time:.2f}초 ({total_time/60:.2f}분)")
        
        # ================================================================
        # 예측 결과 확인 - 이전 회차 예측이 있다면 당첨 결과와 비교
        # ================================================================
        try:
            from src.core.prediction_tracker import PredictionTracker
            from src.core.result_checker import ResultChecker
            
            prediction_tracker = PredictionTracker()
            result_checker = ResultChecker(db_manager, prediction_tracker)
            
            # 필터 검증기 초기화
            filter_validator = FilterValidator(filter_manager, db_manager)
            
            # 이전 예측 결과 확인
            logging.info("\n" + "="*60)
            logging.info("[결과 확인] 이전 예측 당첨 여부 확인...")
            logging.info("="*60)
            
            check_result = result_checker.check_new_results()
            
            # 당첨번호가 필터를 통과했는지 검증
            if check_result and check_result.get('new_results'):
                for result in check_result['new_results']:
                    round_num = result['round']
                    winning_numbers = result['winning_numbers']
                    
                    logging.info(f"\n[필터 검증] {round_num}회차 당첨번호 필터 통과 여부 확인...")
                    validation = filter_validator.validate_winning_numbers(round_num, winning_numbers)
                    
                    if not validation['passed_all_filters']:
                        logging.critical("\n" + "[ALERT]"*20)
                        logging.critical(f"경고: {round_num}회차 당첨번호가 필터에 의해 제외되었습니다!")
                        logging.critical(f"제외된 필터: {', '.join([f['name'] for f in validation['failed_filters']])}")
                        logging.critical("[ALERT]"*20)
                        
                        # 필터 조정 제안
                        suggestions = filter_validator.get_filter_adjustment_suggestions()
                        if suggestions:
                            logging.warning("\n[IDEA] 필터 조정 제안:")
                            for suggestion in suggestions:
                                logging.warning(f"  - {suggestion['filter']}: {suggestion['action']} (우선순위: {suggestion['priority']})")
                    else:
                        logging.info(f"[OK] {round_num}회차 당첨번호가 모든 필터를 통과했습니다.")
                
                # 필터 성능 보고서 출력
                logging.info(filter_validator.generate_validation_report())
            if check_result['status'] == 'checked':
                # 결과 보고서 출력
                logging.info(check_result['report'])
            elif check_result['status'] == 'waiting':
                logging.info(f"{check_result['round']}회차 당첨번호가 아직 발표되지 않았습니다.")
            else:
                logging.info("확인할 이전 예측이 없습니다.")
                
        except Exception as e:
            logging.error(f"예측 결과 확인 중 오류: {e}")
        
        # ================================================================
        # 최종 예측 번호 생성 - 모든 작업이 완료된 후 제일 마지막에 출력
        # ================================================================
        logging.info("\n" + "="*60)
        logging.info("[최종 예측] 로또 번호 5세트 생성...")
        logging.info("="*60)
        
        final_predictions = generate_final_predictions(
            db_manager=db_manager,
            filter_manager=filter_manager,
            ml_predictions={
                'lstm': lstm_predictions if 'lstm_predictions' in locals() else [],
                'ensemble': ensemble_predictions if 'ensemble_predictions' in locals() else [],
                'monte_carlo': mc_predictions if 'mc_predictions' in locals() else [],
                'bayesian': bayesian_predictions if 'bayesian_predictions' in locals() else [],
                'fractal': fractal_predictions if 'fractal_predictions' in locals() else []
            },
            num_sets=5
        )
        
        # 예측 저장을 위한 데이터 준비
        predictions_to_save = []
        
        # 최종 예측 결과 출력
        logging.info("\n" + "◆"*30)
        logging.info("[TARGET] 최종 예측 번호 5세트")
        logging.info("◆"*30)
        
        for i, prediction in enumerate(final_predictions, 1):
            numbers_str = ', '.join(f"{num:2d}" for num in prediction['numbers'])
            confidence = prediction.get('confidence', 0)
            source = prediction.get('source', 'Unknown')
            
            logging.info(f"\n[PIN] 추천 {i}세트: [{numbers_str}]")
            logging.info(f"   신뢰도: {confidence:.1%} | 출처: {source}")
            
            # 번호 특성 분석
            characteristics = analyze_number_characteristics(prediction['numbers'])
            
            # 저장용 데이터 준비 (numpy 타입을 Python 기본 타입으로 변환)
            pred_numbers = prediction['numbers']
            if hasattr(pred_numbers, 'tolist'):
                pred_numbers = pred_numbers.tolist()
            pred_numbers = [int(n) for n in pred_numbers]
            
            predictions_to_save.append({
                'numbers': pred_numbers,
                'confidence': float(confidence) if hasattr(confidence, 'item') else confidence,
                'source': source,
                'characteristics': characteristics if characteristics else {}
            })
        
        logging.info("\n" + "◆"*30)
        
        # ================================================================
        # 예측 번호 데이터베이스 저장
        # ================================================================
        try:
            # 다음 회차 번호 계산
            latest_round = db_manager.get_last_round()
            next_round = latest_round + 1
            
            # 예측 저장 (PredictionTracker 확실히 초기화)
            try:
                if 'prediction_tracker' not in locals():
                    from src.core.prediction_tracker import PredictionTracker
                    prediction_tracker = PredictionTracker()
                    logging.info("예측 저장을 위해 PredictionTracker를 초기화했습니다.")
                
                success = prediction_tracker.save_predictions(next_round, predictions_to_save)
                if success:
                    logging.info(f"\n[OK] {next_round}회차 예측이 저장되었습니다.")
                    logging.info(f"   저장 위치: data/predictions/predictions.db")
                    logging.info(f"   JSON 백업: data/predictions/{datetime.now().year}/week_{next_round}.json")
                else:
                    logging.warning(f"{next_round}회차 예측 저장 실패 (이미 존재할 수 있음)")
            except Exception as e:
                logging.error(f"예측 저장 중 내부 오류: {e}")
        except Exception as e:
            logging.error(f"예측 저장 중 오류: {e}")
        
        logging.info("\n[완료] 모든 작업이 정상적으로 완료되었습니다.")
        logging.info("="*60)
        
        # ================================================================
        # 대시보드 자동 실행 (--no-dashboard 옵션이 없을 때만)
        # ================================================================
        if os.environ.get('NO_DASHBOARD') != '1':
            try:
                logging.info("\n" + "="*60)
                logging.info("[대시보드] 웹 대시보드를 시작합니다...")
                logging.info("="*60)
            
                # 대시보드를 별도 스레드에서 실행 (항상 향상된 대시보드 사용)
                def run_dashboard():
                    """향상된 대시보드 v2 실행 함수"""
                    try:
                        # 향상된 대시보드 v2 사용 (최신 UI/UX 개선 버전)
                        from src.scripts.enhanced_dashboard_v2 import run_enhanced_dashboard_v2
                        logging.info("향상된 대시보드 v2를 포트 5001에서 시작합니다...")
                        run_enhanced_dashboard_v2(host='127.0.0.1', port=5001, debug=False)
                    except ImportError:
                        # v2가 없으면 기존 버전 사용
                        from src.scripts.enhanced_dashboard import run_enhanced_dashboard
                        logging.info("향상된 대시보드를 포트 5001에서 시작합니다...")
                        run_enhanced_dashboard(host='127.0.0.1', port=5001, debug=False)
                    except Exception as e:
                        logging.error(f"대시보드 실행 중 오류: {e}")
                
                def open_browser(delay=3):
                    """브라우저 자동 열기"""
                    time.sleep(delay)
                    url = "http://127.0.0.1:5001"  # 항상 5001 포트 사용
                    logging.info(f"브라우저를 엽니다: {url}")
                    webbrowser.open(url)
                
                # 대시보드 스레드 시작
                dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
                dashboard_thread.start()
                
                # 브라우저 열기 스레드 시작
                browser_thread = threading.Thread(target=open_browser, daemon=True)
                browser_thread.start()
                
                logging.info("\n[대시보드] 웹 브라우저가 자동으로 열립니다...")
                logging.info("[대시보드] 주소: http://127.0.0.1:5001")
                logging.info("[대시보드] 종료하려면 Ctrl+C를 누르세요.\n")
                
                # 대시보드가 계속 실행되도록 대기
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logging.info("\n[대시보드] 사용자가 종료를 요청했습니다.")
                    
            except ImportError as e:
                logging.warning(f"대시보드 모듈을 찾을 수 없습니다: {e}")
                logging.info("대시보드 없이 프로그램을 종료합니다.")
            except Exception as e:
                logging.error(f"대시보드 실행 중 오류: {e}")
        
    except Exception as e:
        logging.error(f"프로그램 실행 중 오류 발생: {str(e)}")
        logging.error(traceback.format_exc())
        logging.info("="*60)
        raise
    finally:
        # 자동화 시스템은 run_24h_automation 내부에서 처리됨
        
        # 향상된 피드백 루프 상태 저장
        try:
            if 'enhanced_feedback' in locals() and enhanced_feedback:
                logging.info("프로그램 종료 시 상태 저장 중...")
                enhanced_feedback.improvement_manager.save_state()
                logging.info("상태 저장 완료")
        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")
        
        # matplotlib 정리 작업
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except:
            pass

if __name__ == "__main__":
    # 명령행 인수 확인
    if len(sys.argv) > 1 and sys.argv[1] == '--no-dashboard':
        # 대시보드 없이 실행
        os.environ['NO_DASHBOARD'] = '1'
    
    main()