# -*- coding: utf-8 -*-
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
import hashlib
import shutil
from pathlib import Path
import pytz  # 한국 시간대(KST) 처리 - 절대 제거하지 말 것!

# 개선된 예측 생성기 임포트
try:
    from src.utils.improved_prediction_generator import generate_final_predictions_improved
    USE_IMPROVED_GENERATOR = True
except ImportError:
    USE_IMPROVED_GENERATOR = False
    logging.warning("개선된 예측 생성기를 로드할 수 없습니다. 기존 방식 사용.")

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
# [2026-06-14 근본제거] AutoAdjustmentSystemV2 import 제거: 죽은 손잡이(global_probability_threshold)만
#  조정해 최종예측 무관이라 비활성화함(인스턴스화 안 함). 모듈 자체는 잔존하나 main.py는 미사용.
from src.optimization.unified_optimizer import UnifiedOptimizer  # Phase 3: 통합 최적화기
from src.core.continuous_improvement_engine import ContinuousImprovementEngine  # 지속적 개선 엔진
from src.core.threshold_optimizer import ThresholdOptimizer  # 임계값 최적화 시스템
from src.core.optimization_db import get_optimization_db  # Phase 2: 통합 최적화 DB
# Phase 1 정리: get_checkpoint_manager (DEPRECATED Grid Search), get_improved_manager (dead import) 제거
from src.utils.memory_monitor import MemoryMonitor, log_memory  # 메모리 모니터링
# from src.core.memory_efficient_patch import apply_emergency_patch, patch_filter_manager  # 메모리 효율성 패치 - 파일 없음
# from src.core.memory_efficient_combinations_manager import MemoryEfficientCombinationsManager  # 메모리 효율적 조합 관리 - 파일 없음
from src.scripts.auto_cache_cleaner import AutoCacheCleaner  # 자동 캐시 정리 시스템

# [FIX N-C27] ErrorPreventionSystem 연결 - 24시간 무인 운영 오류 예방
try:
    from src.utils.error_prevention_system import ErrorPreventionSystem
    ERROR_PREVENTION_AVAILABLE = True
except ImportError as e:
    ERROR_PREVENTION_AVAILABLE = False
    logging.warning(f"ErrorPreventionSystem 로드 실패: {e}")

# ML/AI 모듈 임포트
try:
    from src.ml.lstm_predictor import LSTMPredictor
    # 개선된 필터링 풀 기반 앙상블 예측기 사용 (우선순위)
    from src.ml.filtered_pool_ensemble_predictor import FilteredPoolEnsemblePredictor as EnsemblePredictor
    USE_FILTERED_POOL_ENSEMBLE = True
    ML_AVAILABLE = True
except ImportError as e:
    # 백워드 호환성: 기존 앙상블 예측기로 폴백
    try:
        from src.ml.ensemble_predictor import EnsemblePredictor
        USE_FILTERED_POOL_ENSEMBLE = False
        ML_AVAILABLE = True
        logging.warning(f"FilteredPoolEnsemblePredictor 로드 실패, 기존 EnsemblePredictor 사용: {e}")
    except ImportError as e2:
        ML_AVAILABLE = False
        logging.warning(f"ML 모듈 로드 실패: {e2}")

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
        self.bonus_collected = False
        self.cache_cleaned = False
        
    def check_system_health(self) -> bool:
        """전체 시스템 상태 점검"""
        self.logger.info("[CHECK] 시스템 상태 점검 시작...")
        
        # 보너스 번호 자동 수집
        self._auto_collect_bonus_numbers()

        # NOTE: 캐시 정리는 AutoCacheCleaner로 일원화 (중복 제거)

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
                            yaml.safe_load(f)  # 문법 검증 목적 로드 (YAMLError는 아래에서 처리)

                        # [health-repair-2 제거] 워커수/배치크기 "일관성" 자동수정 폐지.
                        # 과거: parallel_workers != 14 또는 batch_size < 10000 이면 config.yaml을
                        #   yaml.dump로 통째 재작성(주석/구조 파괴 + batch_size 60000->10000 덮어쓰기) +
                        #   timestamp 백업 무한 생성. 하드코딩 14는 실제 권장값(12)과도 불일치였다.
                        # config.yaml은 사용자가 직접 관리하는 단일 소스이므로 자동 재작성하지 않는다.

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
                    from src.scripts.complete_bonus_collection import collect_missing_bonus
                    result = collect_missing_bonus()
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
                total_combinations = combination_manager.generate_base_combinations()
                # generate_base_combinations()은 bool 또는 int를 반환할 수 있음
                # bool(True=1)에 :, 포맷 적용 시 "1개" 오로그 발생 → 타입 확인 후 포맷
                if isinstance(total_combinations, bool) or not isinstance(total_combinations, int):
                    self.logger.info("[OK] 조합 생성 완료")
                else:
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

            # 'multiple' 키가 없으면 수정 불필요
            return True

        except Exception as e:
            self.logger.error(f"multiple 필터 임계값 조정 실패: {e}")
            return False
    
    # [health-repair-2 제거] _repair_config_inconsistency 메서드 삭제.
    # config.yaml을 yaml.dump로 재작성하여 주석/구조를 파괴하고 batch_size를
    # 60000->10000으로 덮어쓰며 워커수를 14로 강제하던 파괴적 자동복구였다.
    # 호출처(_check_configuration_files의 일관성 트리거)와 함께 제거됨.

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
        self._last_memory_warning_time = 0  # 메모리 경고 쿨다운 타임스탬프
        self._last_memory_repair_warning_time = 0  # 메모리 복구 무효 경고 쿨다운

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
        """데이터베이스 연결 문제 복구 (싱글톤 제자리 재초기화)

        주의: DatabaseManager는 싱글톤이라 DatabaseManager()는 '새 인스턴스'가 아니라
        기존과 동일한 인스턴스를 반환한다. 따라서 단순 재할당만으로는 재연결 효과가 없다.
        실제 재연결은 다음 순서로 이루어진다.
          1) close_all_connections()가 lotto_db/combinations_db 등 속성을 삭제
          2) DatabaseManager() 호출 시 __init__이 hasattr(self,'lotto_db')==False를 보고
             '제자리에서' 연결을 다시 만든다 (동일 객체이므로 다른 참조에도 그대로 반영)
        반환값은 재초기화로 핵심 연결이 실제 복구됐는지 실측해 판정한다(거짓 성공 금지).
        """
        try:
            if not self.db_manager:
                self.logger.warning("DB 매니저 참조가 없어 연결 복구를 건너뜁니다.")
                return False

            # 1) 기존 연결 종료(속성 삭제) -> 2) 동일 싱글톤 제자리 재초기화
            self.db_manager.close_all_connections()
            time.sleep(2)
            from src.core.db_manager import DatabaseManager
            # 동일 싱글톤 객체를 재초기화한다(다른 참조도 같은 객체이므로 자동 반영)
            self.db_manager = DatabaseManager()

            # 재연결 실측: 핵심 DB 속성이 복구되고 간단한 조회가 동작하는지 확인
            if not hasattr(self.db_manager, 'lotto_db'):
                self.logger.error("DB 재초기화 후에도 핵심 연결(lotto_db)이 복구되지 않았습니다.")
                return False
            # 가벼운 조회로 실제 동작 확인
            self.db_manager.get_last_round()
            self.logger.info("[OK] 데이터베이스 연결 복구 완료(싱글톤 제자리 재초기화)")
            return True

        except Exception as e:
            self.logger.error(f"데이터베이스 연결 복구 실패: {e}")
            return False
            
    def _repair_high_memory_usage(self) -> bool:
        """높은 메모리 사용량 복구 (복구 후 실측으로 성공 판정 - 거짓 성공 보고 금지)"""
        try:
            import psutil
            mem_before = psutil.virtual_memory().percent
        except Exception:
            mem_before = None

        try:
            # 1) 가비지 컬렉션 (주의: 이 프로세스 메모리만 회수됨)
            import gc
            gc.collect()

            # 2) 모델 캐시의 임시(.tmp) 파일 정리
            cache_dir = 'cache/models'
            if os.path.exists(cache_dir):
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        if file.endswith('.tmp'):
                            try:
                                os.remove(os.path.join(root, file))
                            except OSError:
                                pass

            # 3) 복구 효과 실측 -> 실제 하락 여부로 성공 판정
            if mem_before is None:
                self.logger.warning("psutil 미사용으로 메모리 복구 효과를 측정할 수 없습니다.")
                return False

            import psutil  # mem_before is not None -> 위에서 import 성공 보장
            mem_after = psutil.virtual_memory().percent

            if mem_after < 90:
                self.logger.info(f"[OK] 메모리 복구: {mem_before:.1f}% -> {mem_after:.1f}%")
                return True
            if mem_before - mem_after >= 2.0:
                self.logger.info(f"메모리 일부 회수: {mem_before:.1f}% -> {mem_after:.1f}% (여전히 높음)")
                return True

            # gc로 회수되지 않음 -> 외부 프로세스이거나 대형 배치/캐시. 거짓 성공 보고하지 않는다.
            now = time.time()
            if now - self._last_memory_repair_warning_time >= 600:
                self.logger.warning(
                    f"메모리 회수 미미: {mem_before:.1f}% -> {mem_after:.1f}%. "
                    f"gc로 해소 불가(외부 프로세스이거나 대형 배치/캐시). "
                    f"config.yaml batch_size 축소 또는 'python src/scripts/clear_model_cache.py' 권장."
                )
                self._last_memory_repair_warning_time = now
            return False

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


def _is_duplicate_prediction(numbers, existing_predictions):
    """중복 예측 확인"""
    numbers_set = set(numbers)
    for pred in existing_predictions:
        if set(pred['numbers']) == numbers_set:
            return True
    return False


def generate_final_predictions_enhanced(db_manager, filter_manager, ml_predictions=None, num_sets=5, use_ml_priority_mode=True):
    """[Enhanced] ML 우선 모드로 개선된 예측 생성 - 포함률 15% 이상 목표

    주요 개선사항:
    1. ML 전용 완화된 임계값 시스템 (기본 1.0% → ML용 0.5%)
    2. 동적 포함률 조정 메커니즘 (실시간 모니터링)
    3. 하이브리드 필터링 (중요 필터 + 완화 필터)
    4. 개선된 유사 조합 매칭 알고리즘

    Args:
        db_manager: 데이터베이스 매니저
        filter_manager: 필터 매니저
        ml_predictions: ML 예측 결과
        num_sets: 생성할 세트 수
        use_ml_priority_mode: ML 우선 모드 사용 여부 (기본값 True)
    """
    final_predictions = []
    ml_failed_predictions = []
    ml_inclusion_stats = {'total': 0, 'passed': 0, 'failed': 0}

    # 통계 기반 가중치 계산기 초기화 (싱글톤)
    _stat_calc = None
    try:
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        _stat_calc = StatisticalWeightCalculator.get_instance(db_manager)
    except Exception as _e:
        logging.warning(f"[통계가중치] 초기화 실패 - ML 점수만 사용: {_e}")

    # 필터링 풀 크기 확인 - 최신 회차 자동 감지
    try:
        target_round = db_manager.get_last_round()
        filtered_combos_check = db_manager.combinations_db.get_filtered_combinations(target_round) or []

        # 해당 회차에 필터링 데이터가 없으면 최신 필터링 회차 사용
        if not filtered_combos_check:
            latest_filtered_round = db_manager.combinations_db.get_latest_filtered_round()
            if latest_filtered_round > 0:
                logging.info(f"회차 {target_round}의 필터링 데이터가 없어 회차 {latest_filtered_round} 사용")
                filtered_combos_check = db_manager.combinations_db.get_filtered_combinations(latest_filtered_round) or []
    except Exception as e:
        logging.error(f"필터링 조합 가져오기 실패: {e}")
        filtered_combos_check = []

    filtered_pool_size = len(filtered_combos_check)
    force_ml_direct_use = (filtered_pool_size == 0)

    # [v5 FIX #17] L3 풀 멤버십 검증용 정규화 set (1회 생성, O(1) 조회).
    # L3(고신뢰 ML)는 16필터 풀을 우회하므로, 최종 조합이 실제 사전필터링 풀 안에 있는지 검증해
    # "풀 밖" 조합이 최종 5세트에 들어가는 것을 막는다(핵심 전략: 좁은 풀 커버 보장).
    pool_member_set = set()
    for _c in filtered_combos_check:
        try:
            pool_member_set.add(tuple(sorted(int(x) for x in _c.split(','))))
        except Exception:
            pass

    # ML 우선 모드 설정 - ThresholdManager에서 로드 (BUG-002 수정)
    from src.core.threshold_manager import get_threshold_manager
    threshold_manager = get_threshold_manager()
    ml_relaxed_threshold = threshold_manager.get_ml_relaxed_threshold()

    logging.info(f"ML 완화된 임계값: {ml_relaxed_threshold}%")
    target_inclusion_rate = 0.15  # 목표 포함률 15%
    current_inclusion_rate = 0.0

    if force_ml_direct_use:
        logging.warning(f"[긴급] 필터링 풀이 {filtered_pool_size}개! ML 예측을 필터 없이 직접 사용합니다.")

    try:
        # 1. ML/AI 예측 결과 통합 및 전처리
        all_ml_predictions = []

        if ml_predictions and isinstance(ml_predictions, list):
            all_ml_predictions = ml_predictions[:20]  # 최대 20개로 확장 (더 많은 기회 제공)
        elif ml_predictions and isinstance(ml_predictions, dict):
            for model_name, predictions in ml_predictions.items():
                if predictions:
                    for pred in predictions[:5]:  # 각 모델에서 상위 5개씩 (기존 3개 → 5개)
                        pred_copy = pred.copy()
                        pred_copy['model'] = model_name
                        all_ml_predictions.append(pred_copy)

        # 신뢰도 순으로 정렬
        all_ml_predictions.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        ml_inclusion_stats['total'] = len(all_ml_predictions)

        logging.info(f"[ML 우선 모드] 총 {len(all_ml_predictions)}개 ML 예측 처리 시작, 목표 포함률: {target_inclusion_rate:.1%}")

        # 2. ML 우선 필터링 - 하이브리드 접근법
        for i, pred in enumerate(all_ml_predictions):
            if len(final_predictions) >= num_sets:
                break

            numbers = pred.get('numbers', [])
            if len(numbers) == 6:
                # 필터링 풀이 0개면 필터 체크 없이 바로 사용
                if force_ml_direct_use:
                    if not _is_duplicate_prediction(numbers, final_predictions):
                        final_predictions.append({
                            'numbers': sorted(numbers),
                            'confidence': pred.get('confidence', 0.7),
                            'source': f"ML-Direct/{pred.get('model', 'Unknown')}"
                        })
                        ml_inclusion_stats['passed'] += 1
                        logging.info(f"ML 예측 직접 사용 (필터링 풀 0개): {sorted(numbers)}")
                    continue

                # ML 우선 모드: 동적 완화 레벨 결정
                model_name = pred.get('model', 'Unknown')
                prediction_confidence = pred.get('confidence', 0)

                # 동적 완화 레벨 계산 (포함률이 낮으면 더 관대하게)
                # 분모는 '지금까지 평가를 마친 예측 수'(= 현재 인덱스 i)로 명확히 한다.
                # 첫 예측(i=0)은 아직 평가 표본이 없으므로 포함률을 0.0으로 두어
                # max(i,1) 사용 시 발생하던 첫 예측 포함률 과대평가를 제거한다.
                processed = i  # indices 0..i-1 만 이미 평가 완료
                current_inclusion_rate = (ml_inclusion_stats['passed'] / processed) if processed > 0 else 0.0
                need_more_relaxation = current_inclusion_rate < target_inclusion_rate

                # 완화 레벨 결정 (3단계)
                # [FIX] model_name 기반 자동 Level 3 부여 제거
                # 문제: 'lstm', 'ensemble' 모델은 신뢰도와 무관하게 자동 Level 3 → ml_inclusion 항상 ~1.0
                #       Optuna 최적화에서 ml_inclusion이 상수 편향(+0.1)으로 작동
                # 수정: 신뢰도 임계값만으로 결정 (0.6 → 0.70으로 상향)
                #       Level 3는 실제 고신뢰도 예측에만 적용 (진정한 필터 신호 회복)
                if prediction_confidence > 0.70:
                    relaxation_level = 3  # 최고 완화 (고신뢰도만)
                elif prediction_confidence > 0.50 or need_more_relaxation:
                    relaxation_level = 2  # 중간 완화
                else:
                    relaxation_level = 1  # 기본 완화

                # 하이브리드 필터링 실행
                passes_filter, filter_result = _apply_hybrid_filtering(
                    numbers, filter_manager, db_manager,
                    relaxation_level, ml_relaxed_threshold
                )

                if passes_filter:
                    # ML 예측 성공
                    final_numbers = sorted(numbers)
                    was_replaced = False
                    # [v5 FIX #17] L3는 16필터 풀을 우회하므로 풀 멤버십 검증.
                    # 풀 밖이면 풀 내 최근접 조합으로 치환(Codex 협업 결정: ML은 풀 밖 예외권이
                    # 아니라 풀 안 후보를 고르는 방향 신호). 치환 실패 시 복구 경로로 넘김.
                    if relaxation_level == 3 and not force_ml_direct_use:
                        if tuple(final_numbers) not in pool_member_set:
                            similar = _find_enhanced_similar_combinations(numbers, filtered_combos_check, top_n=1)
                            if similar and not _is_duplicate_prediction(similar[0]['numbers'], final_predictions):
                                final_numbers = sorted(similar[0]['numbers'])
                                was_replaced = True
                            else:
                                # 풀 내 치환 실패 → 최종에 넣지 않고 복구 경로로 (핵심 전략 보존)
                                ml_failed_predictions.append(pred)
                                ml_inclusion_stats['failed'] += 1
                                logging.debug(f"L3 풀 밖 + 치환 실패 → 복구 경로: {final_numbers}")
                                continue
                    final_predictions.append({
                        'numbers': final_numbers,
                        'confidence': prediction_confidence,
                        'source': f"ML-Enhanced/{model_name} (L{relaxation_level})" + ("+PoolProj" if was_replaced else ""),
                        'filter_info': filter_result,
                        'in_pool': True,
                        'was_replaced': was_replaced
                    })
                    ml_inclusion_stats['passed'] += 1
                    logging.info(f"ML 예측 통과 [{i+1}/{len(all_ml_predictions)}]: {final_numbers} "
                               f"({model_name}, 신뢰도: {prediction_confidence:.2%}, 완화레벨: {relaxation_level}"
                               f"{', 풀치환' if was_replaced else ''})")
                else:
                    # ML 예측 실패 → 복구 전략 적용
                    ml_failed_predictions.append(pred)
                    ml_inclusion_stats['failed'] += 1
                    logging.debug(f"ML 예측 필터 실패: {sorted(numbers)} ({model_name}) - {filter_result}")

        # 3. ML 실패 예측 복구 전략 - 개선된 다단계 접근법
        final_inclusion_rate = ml_inclusion_stats['passed'] / max(ml_inclusion_stats['total'], 1)
        logging.info(f"[ML 우선 모드] 1차 필터링 결과: {ml_inclusion_stats['passed']}/{ml_inclusion_stats['total']} "
                    f"({final_inclusion_rate:.1%}) 포함, 목표: {target_inclusion_rate:.1%}")

        if ml_failed_predictions and len(final_predictions) < num_sets:
            logging.info(f"[ML 복구 전략] {len(ml_failed_predictions)}개 실패 예측 복구 시도 중...")

            # 필터링된 조합 가져오기 - 최신 회차 자동 감지
            try:
                target_round = db_manager.get_last_round()
                filtered_combos = db_manager.combinations_db.get_filtered_combinations(target_round) or []

                # 해당 회차에 필터링 데이터가 없으면 최신 필터링 회차 사용
                if not filtered_combos:
                    latest_filtered_round = db_manager.combinations_db.get_latest_filtered_round()
                    if latest_filtered_round > 0:
                        logging.info(f"[ML 복구] 회차 {target_round}의 필터링 데이터가 없어 회차 {latest_filtered_round} 사용")
                        filtered_combos = db_manager.combinations_db.get_filtered_combinations(latest_filtered_round) or []
            except Exception as e:
                logging.error(f"필터링 조합 가져오기 실패: {e}")
                filtered_combos = []

            if not filtered_combos:
                # 필터링 풀이 없으면 고신뢰도 ML 예측 직접 사용
                logging.warning("[복구 전략] 필터링 풀 없음 - 고신뢰도 ML 예측 직접 사용")
                for failed_pred in ml_failed_predictions[:num_sets - len(final_predictions)]:
                    failed_numbers = failed_pred.get('numbers', [])
                    model_name = failed_pred.get('model', 'Unknown')
                    prediction_confidence = failed_pred.get('confidence', 0)

                    if (len(failed_numbers) == 6 and prediction_confidence > 0.4 and
                        not _is_duplicate_prediction(failed_numbers, final_predictions)):
                        final_predictions.append({
                            'numbers': sorted(failed_numbers),
                            'confidence': prediction_confidence * 0.9,  # 10% 패널티
                            'source': f"ML-Emergency/{model_name}"
                        })
                        logging.info(f"긴급 복구: {sorted(failed_numbers)} ({model_name}, 신뢰도: {prediction_confidence:.2%})")
            else:
                # 개선된 복구 전략 적용
                recovery_success_count = 0
                for failed_pred in ml_failed_predictions[:10]:  # 최대 10개 시도
                    if len(final_predictions) >= num_sets:
                        break

                    failed_numbers = failed_pred.get('numbers', [])
                    model_name = failed_pred.get('model', 'Unknown')
                    prediction_confidence = failed_pred.get('confidence', 0)

                    recovery_attempted = False

                    # 전략 1: 개선된 유사 조합 찾기 (가중치 기반)
                    if not recovery_attempted:
                        similar_combos = _find_enhanced_similar_combinations(failed_numbers, filtered_combos, top_n=3)
                        if similar_combos and similar_combos[0]['similarity'] > 0.33:  # [FIX] 0.5→0.33: 실제 당첨번호 평균 유사도(2개 공통=0.33) 기준
                            best_match = similar_combos[0]
                            if not _is_duplicate_prediction(best_match['numbers'], final_predictions):
                                confidence_boost = best_match['similarity'] * 0.9  # 유사도 기반 신뢰도 조정
                                final_predictions.append({
                                    'numbers': sorted(best_match['numbers']),
                                    'confidence': prediction_confidence * confidence_boost,
                                    'source': f"ML-Enhanced-Similar/{model_name}",
                                    'recovery_info': {
                                        'original': failed_numbers,
                                        'similarity': best_match['similarity'],
                                        'common_numbers': best_match['common_count']
                                    }
                                })
                                recovery_success_count += 1
                                recovery_attempted = True
                                logging.debug(f"유사 조합 복구: {failed_numbers} → {best_match['numbers']} "
                                            f"(유사도: {best_match['similarity']:.2%})")

                    # 전략 2: 부분 수정된 ML 예측 (신뢰도 높은 모델만)
                    if not recovery_attempted and prediction_confidence > 0.6:
                        adjusted_numbers = _adjust_ml_prediction_enhanced(failed_numbers, filtered_combos)
                        if (adjusted_numbers and
                            not _is_duplicate_prediction(adjusted_numbers, final_predictions)):
                            final_predictions.append({
                                'numbers': sorted(adjusted_numbers),
                                'confidence': prediction_confidence * 0.7,  # 30% 패널티
                                'source': f"ML-Adjusted/{model_name}",
                                'recovery_info': {
                                    'original': failed_numbers,
                                    'adjustments': [n for n in adjusted_numbers if n not in failed_numbers]
                                }
                            })
                            recovery_success_count += 1
                            recovery_attempted = True
                            logging.debug(f"수정 복구: {failed_numbers} → {adjusted_numbers}")

                logging.info(f"[ML 복구 결과] {recovery_success_count}개 예측 성공적으로 복구")

        # 4. 부족한 예측 수 필터링 풀에서 보충
        if len(final_predictions) < num_sets:
            logging.info(f"[풀 보충] 현재 {len(final_predictions)}개 예측, {num_sets}개까지 필터링 풀에서 보충")
            try:
                # 필터링된 조합 가져오기 - 최신 회차 자동 감지
                filtered_combos = []  # 기본값 (UnboundLocalError 방지)
                target_round = db_manager.get_last_round()
                filtered_combos = db_manager.combinations_db.get_filtered_combinations(target_round) or []

                # 해당 회차에 필터링 데이터가 없으면 최신 필터링 회차 사용
                if not filtered_combos:
                    latest_filtered_round = db_manager.combinations_db.get_latest_filtered_round()
                    if latest_filtered_round > 0:
                        logging.info(f"[풀 보충] 회차 {target_round}의 필터링 데이터가 없어 회차 {latest_filtered_round} 사용")
                        filtered_combos = db_manager.combinations_db.get_filtered_combinations(latest_filtered_round) or []

                if filtered_combos:
                    # ML 가중 다양성 선택: ML 선호도 + 다양성 결합
                    from src.utils.diversity_selector import DiversitySelector

                    # ML 예측 번호 빈도 맵 생성 (실패+성공 모두 활용)
                    ml_number_freq = {}
                    ml_source_preds = all_ml_predictions if all_ml_predictions else []
                    for ml_pred in ml_source_preds:
                        conf = ml_pred.get('confidence', 0.5)
                        for num in ml_pred.get('numbers', []):
                            ml_number_freq[num] = ml_number_freq.get(num, 0) + conf

                    available_combo_strs = []
                    available_combos_map = {}  # combo_str -> numbers list
                    combo_ml_scores = {}    # combo_str -> ML 선호도 점수 (raw)
                    combo_stat_scores = {}  # combo_str -> 통계 가중치 점수 (0~1)
                    final_combo_scores = {} # combo_str -> ML+통계 통합 점수

                    for combo_str in filtered_combos[:5000]:  # 5000개로 확대 (ML 점수로 재정렬)
                        try:
                            numbers = [int(x) for x in combo_str.split(',')]
                            if not _is_duplicate_prediction(numbers, final_predictions):
                                normalized_str = ','.join(str(n) for n in sorted(numbers))
                                available_combo_strs.append(normalized_str)
                                available_combos_map[normalized_str] = numbers
                                # ML 선호도 점수: 해당 조합의 번호들이 ML 예측에 얼마나 자주 등장했는지
                                ml_score = sum(ml_number_freq.get(n, 0) for n in numbers)
                                combo_ml_scores[normalized_str] = ml_score
                                # 통계 가중치 점수 (0~1)
                                if _stat_calc is not None:
                                    combo_stat_scores[normalized_str] = _stat_calc.calculate_combo_weight(numbers)
                                else:
                                    combo_stat_scores[normalized_str] = 0.5
                        except (ValueError, IndexError):
                            continue

                    # ML + 통계 결합 점수로 정렬 후 상위 후보 선택
                    if ml_number_freq and available_combo_strs:
                        # ML 점수 min-max 정규화 (풀 내 상대 순위 보존)
                        ml_raw_vals = list(combo_ml_scores.values())
                        ml_max = max(ml_raw_vals) if ml_raw_vals else 1.0
                        ml_min = min(ml_raw_vals) if ml_raw_vals else 0.0
                        ml_range = max(ml_max - ml_min, 1e-10)

                        # 통합 점수 = 0.65 * ML정규화 + 0.35 * 통계점수
                        _ALPHA_ML   = 0.65
                        _BETA_STAT  = 0.35
                        final_combo_scores = {}
                        for _s in available_combo_strs:
                            _ml_norm = (combo_ml_scores.get(_s, 0) - ml_min) / ml_range
                            _stat_s  = combo_stat_scores.get(_s, 0.5)
                            final_combo_scores[_s] = _ALPHA_ML * _ml_norm + _BETA_STAT * _stat_s

                        available_combo_strs.sort(
                            key=lambda s: final_combo_scores.get(s, 0),
                            reverse=True
                        )
                        # 상위 ML+통계 결합 후보에서 다양성 선택 (상위 300개)
                        ml_top_pool = available_combo_strs[:300]
                        pool_label = "Pool-ML-Stat-Diversity"
                        logging.info(f"[풀 보충] ML+통계 결합 기반 상위 {len(ml_top_pool)}개 후보에서 다양성 선택")
                    else:
                        # ML 정보 없을 때는 통계 점수만으로 정렬
                        if _stat_calc is not None and available_combo_strs:
                            available_combo_strs.sort(
                                key=lambda s: combo_stat_scores.get(s, 0.5),
                                reverse=True
                            )
                        ml_top_pool = available_combo_strs[:1000]
                        pool_label = "Pool-Stat-Diversity" if _stat_calc is not None else "Pool-Diversity"

                    # 부족한 만큼 다양성 극대화 선택
                    needed = num_sets - len(final_predictions)
                    existing_nums = [pred['numbers'] for pred in final_predictions]

                    selector = DiversitySelector()
                    selected_strs = selector.select_diverse(
                        pool=ml_top_pool,
                        n_select=min(needed, len(ml_top_pool)),
                        existing=existing_nums if existing_nums else None
                    )

                    # 신뢰도 계산 기준값: 루프 밖에서 1회만 계산
                    _max_int_score  = max(final_combo_scores.values()) if final_combo_scores else 0
                    _max_ml_score   = max(combo_ml_scores.values()) if combo_ml_scores else 1

                    for combo_str in selected_strs:
                        numbers = available_combos_map[combo_str]
                        # 통합 점수에 비례한 신뢰도 (0.3 ~ 0.55)
                        if final_combo_scores:
                            integrated_score = final_combo_scores.get(combo_str, 0)
                            confidence = 0.3 + 0.25 * (integrated_score / max(_max_int_score, 1e-10))
                        else:
                            # ML+통계 통합 점수 없을 때 기존 방식
                            ml_score = combo_ml_scores.get(combo_str, 0)
                            confidence = 0.3 + 0.2 * (ml_score / max(_max_ml_score, 1e-10))
                        final_predictions.append({
                            'numbers': sorted(numbers),
                            'confidence': round(confidence, 3),
                            'source': pool_label
                        })

                    if selected_strs:
                        diversity_score = selector.calculate_diversity_score(selected_strs)
                        logging.info(f"[풀 보충] {len(selected_strs)}개 조합 추가 (다양성 점수: {diversity_score:.1f}/100)")
            except Exception as e:
                logging.error(f"필터링 풀 보충 중 오류: {str(e)}")

        # 5a. 동적 패턴 스코어링 기반 재랭킹 (DB 분석 결과 적용)
        # 최근 10회 핫넘버, 번호쌍 공출현, 합계 중심성, 직전 재출현 적정량, 구간 균형
        # "제거" 대신 "재랭킹": 당첨번호 손실 없이 더 그럴듯한 조합 우선 선택
        try:
            from src.core.dynamic_pattern_scorer import get_dynamic_scorer
            _dps = get_dynamic_scorer()
            if _dps._initialized and len(final_predictions) > 1:
                # 현재 회차 계산 (동적)
                _current_round = None
                try:
                    _current_round = db_manager.get_latest_round() + 1
                except Exception:
                    pass

                # v2: 트리플렛/쌍 Z-score/끝자리/추세/직전재출현 스코어 (모두 동적)
                _prev_nums = _dps._get_prev_nums(_current_round)
                for _pred in final_predictions:
                    _dp_score = _dps.score_combination(
                        _pred['numbers'], _current_round, _prev_nums
                    )
                    # 기존 confidence와 동적 점수 혼합 (7:3 가중)
                    _pred['dynamic_score'] = round(_dp_score, 4)
                    _pred['confidence'] = round(
                        _pred.get('confidence', 0.5) * 0.7 + _dp_score * 0.3, 4
                    )

                # 동적 점수 기반 재정렬
                final_predictions.sort(key=lambda p: p['confidence'], reverse=True)

                # 통계 로그 (v2 통계 구조)
                _stats = _dps.get_current_stats()
                _top_trips = [str(t) for t, _ in _stats.get('top_hot_triplets', [])[:2]]
                _trend_up = _stats.get('trend_up_numbers', [])[:3]
                _trend_down = _stats.get('trend_down_numbers', [])[:3]
                logging.info(
                    f"[동적패턴v2] 재랭킹 완료 | "
                    f"핫트리플렛: {_top_trips} | "
                    f"추세상승: {_trend_up} | 추세하락: {_trend_down}"
                )
        except Exception as _e:
            logging.debug(f"[동적패턴v2] 스코어링 실패 (무시): {_e}")

        # 5. Wheeling System 적용 (선택적 - 커버리지 최적화)
        try:
            from src.optimization.wheeling_system import WheelingSystem, WheelType

            ws = WheelingSystem(db_manager)

            # 최종 예측에서 출현한 모든 번호 수집
            all_numbers_from_predictions = set()
            for pred in final_predictions:
                all_numbers_from_predictions.update(pred['numbers'])

            # 번호가 7개 이상이면 휠링 적용
            if len(all_numbers_from_predictions) >= 7:
                wheel_numbers = sorted(all_numbers_from_predictions)[:15]  # 최대 15개

                # 축소 휠 생성 (3개 일치 보장)
                wheel_result = ws.generate_wheel(
                    numbers=wheel_numbers,
                    guarantee=3,
                    wheel_type=WheelType.ABBREVIATED,
                    max_combinations=num_sets  # 요청된 세트 수만큼
                )

                # 휠링 결과를 예측에 휠링 정보로 보강
                if wheel_result.generated_combinations:
                    for i, _combo in enumerate(wheel_result.generated_combinations[:num_sets]):
                        if i < len(final_predictions):
                            # 기존 예측에 휠링 메타 정보 추가
                            final_predictions[i]['wheeling_info'] = {
                                'wheel_type': wheel_result.wheel_type.value,
                                'guarantee': wheel_result.guarantee_level,
                                'coverage': wheel_result.coverage_analysis.get('coverage_ratio', 0),
                                'total_wheel_combos': len(wheel_result.generated_combinations)
                            }

                    logging.info(f"[Wheeling] {len(wheel_result.generated_combinations)}개 조합 생성, "
                                f"커버리지: {wheel_result.coverage_analysis.get('coverage_ratio', 0):.1%}")
        except ImportError:
            logging.debug("WheelingSystem 모듈을 찾을 수 없어 휠링 미적용")
        except Exception as e:
            logging.debug(f"Wheeling System 적용 실패 (무시): {e}")

        # 6. 최종 통계 및 포함률 분석
        final_inclusion_rate = ml_inclusion_stats['passed'] / max(ml_inclusion_stats['total'], 1)
        total_ml_in_final = sum(1 for pred in final_predictions if 'ML' in pred['source'])

        logging.info("="*60)
        logging.info("[ML 우선 모드] 최종 결과 요약")
        logging.info("="*60)
        logging.info(f"[STAT] ML 예측 처리 통계:")
        logging.info(f"  - 총 ML 예측 수: {ml_inclusion_stats['total']}개")
        logging.info(f"  - 1차 필터 통과: {ml_inclusion_stats['passed']}개 ({final_inclusion_rate:.1%})")
        logging.info(f"  - 필터 실패: {ml_inclusion_stats['failed']}개")
        logging.info(f"  - 최종 ML 포함: {total_ml_in_final}개/{len(final_predictions)}개")
        logging.info(f"[TARGET] 포함률 성과:")
        logging.info(f"  - 목표 포함률: {target_inclusion_rate:.1%}")
        logging.info(f"  - 실제 포함률: {final_inclusion_rate:.1%}")
        if final_inclusion_rate >= target_inclusion_rate:
            logging.info("  - [O] 목표 달성!")
        else:
            logging.info(f"  - [!] 목표 미달성 (차이: {(target_inclusion_rate - final_inclusion_rate):.1%})")

        # 예측별 상세 정보
        for i, pred in enumerate(final_predictions, 1):
            source = pred.get('source', 'Unknown')
            confidence = pred.get('confidence', 0)
            recovery_info = pred.get('recovery_info', {})

            if recovery_info:
                original = recovery_info.get('original', [])
                similarity = recovery_info.get('similarity', 0)
                logging.info(f"  [{i}] {pred['numbers']} ({source}, 신뢰도: {confidence:.2%}) "
                           f"[복구: {original} → 유사도: {similarity:.1%}]")
            else:
                logging.info(f"  [{i}] {pred['numbers']} ({source}, 신뢰도: {confidence:.2%})")

        logging.info("="*60)

        return final_predictions

    except Exception as e:
        logging.error(f"개선된 예측 생성 중 오류: {str(e)}")
        return []


def generate_final_predictions_original(db_manager, filter_manager, ml_predictions=None, num_sets=5, use_relaxed_filter=True):
    """[기존 백업] ML/AI 예측과 필터링 결과를 통합하여 최종 예측 번호 생성

    Args:
        db_manager: 데이터베이스 매니저
        filter_manager: 필터 매니저
        ml_predictions: ML 예측 결과
        num_sets: 생성할 세트 수
        use_relaxed_filter: ML 예측에 대해 완화된 필터 적용 여부
    """
    # 개선된 버전을 호출하도록 변경
    return generate_final_predictions_enhanced(db_manager, filter_manager, ml_predictions, num_sets, True)


# 호환성을 위해 기본 함수명으로 개선된 버전 사용
def generate_final_predictions(db_manager, filter_manager, ml_predictions=None, num_sets=5, use_relaxed_filter=True):
    """ML/AI 예측과 필터링 결과를 통합하여 최종 예측 번호 생성 - 개선된 버전 사용"""
    return generate_final_predictions_enhanced(db_manager, filter_manager, ml_predictions, num_sets, True)


def combine_ml_predictions(lstm_predictions=None, ensemble_predictions=None,
                          mc_predictions=None, bayesian_predictions=None,
                          fractal_predictions=None, num_combined=5):
    """모든 ML 예측을 통합하여 Combined 예측 생성

    Args:
        lstm_predictions, ensemble_predictions, etc.: 각 모델의 예측 결과
        num_combined: 생성할 Combined 예측 수

    Returns:
        List[Dict]: Combined 예측 결과
    """
    combined_predictions = []

    try:
        # 모든 예측을 수집
        all_predictions = []
        prediction_sources = {
            'lstm': lstm_predictions or [],
            'ensemble': ensemble_predictions or [],
            'monte_carlo': mc_predictions or [],
            'bayesian': bayesian_predictions or [],
            'fractal': fractal_predictions or []
        }

        # 각 모델에서 상위 예측 추가
        for model_name, predictions in prediction_sources.items():
            if predictions:
                # 상위 3개씩 사용 (더 많은 예측 확보)
                for pred in predictions[:3]:
                    if isinstance(pred, dict) and 'numbers' in pred:
                        numbers = pred.get('numbers', [])
                        if isinstance(numbers, list) and len(numbers) == 6:
                            pred_copy = pred.copy()
                            pred_copy['source_model'] = model_name
                            all_predictions.append(pred_copy)

        if not all_predictions:
            logging.warning("[Combined] 결합할 ML 예측이 없습니다.")
            logging.warning(f"  - LSTM: {len(prediction_sources.get('lstm', []))}개")
            logging.warning(f"  - Ensemble: {len(prediction_sources.get('ensemble', []))}개")
            logging.warning(f"  - Monte Carlo: {len(prediction_sources.get('monte_carlo', []))}개")
            logging.warning(f"  - Bayesian: {len(prediction_sources.get('bayesian', []))}개")
            logging.warning(f"  - Fractal: {len(prediction_sources.get('fractal', []))}개")
            return []

        # 신뢰도 순으로 정렬
        all_predictions.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        # 번호별 가중 점수 계산
        number_scores = {}

        # Task 6: Combined 모델 가중치 정의 (투명성 개선)
        model_weights = {
            'lstm': 1.2,      # LSTM은 시계열 패턴에 강함
            'ensemble': 1.3,  # 앙상블은 일반적으로 안정적
            'monte_carlo': 1.0,
            'bayesian': 1.1,
            'fractal': 0.9    # 프랙탈은 실험적
        }

        # Task 6: 가중 평균 계산 과정 로깅
        logging.info(f"\n[Combined 모델 가중 평균 계산]")
        logging.info(f"  모델별 가중치:")
        for model, weight in model_weights.items():
            logging.info(f"    - {model:12s}: {weight:.2f}")
        logging.info(f"  총 예측 수: {len(all_predictions)}개")

        for pred in all_predictions:
            numbers = pred.get('numbers', [])
            confidence = pred.get('confidence', 0)
            source_model = pred.get('source_model', '')
            model_weight = model_weights.get(source_model, 1.0)

            weighted_score = confidence * model_weight

            # Task 6: 개별 예측 기여도 로깅 (상위 3개만)
            if all_predictions.index(pred) < 3:
                logging.debug(f"    [{source_model:10s}] 신뢰도 {confidence:.3f} × 가중치 {model_weight:.2f} = {weighted_score:.3f}")

            for num in numbers:
                if num not in number_scores:
                    number_scores[num] = 0
                number_scores[num] += weighted_score

        # 점수가 높은 번호들을 기반으로 조합 생성
        sorted_numbers = sorted(number_scores.items(), key=lambda x: x[1], reverse=True)

        def _ensure_six(nums):
            """선택 번호가 6개 미만이면 1~45 실제 번호 범위에서 보충해 항상 6개 보장.

            NO FAKE: 더미값이 아니라 실제 로또 번호 범위(1~45) 중 아직 선택되지 않은
            번호에서 균등 무작위로 보충한다. 모집단(고유 번호)이 6개 미만이라 전략이
            조용히 실패(예외->continue)하던 문제를 방지.
            """
            unique = list(dict.fromkeys(int(n) for n in nums))  # 중복 제거(순서 유지)
            if len(unique) >= 6:
                return sorted(unique[:6])
            remaining = [n for n in range(1, 46) if n not in unique]
            if remaining:
                need = 6 - len(unique)
                unique.extend(random.sample(remaining, min(need, len(remaining))))
            return sorted(unique[:6])

        # 다양한 전략으로 Combined 예측 생성
        strategies = [
            'top_scored',      # 최고 점수 번호들
            'balanced',        # 균형잡힌 선택
            'model_consensus', # 모델 합의
            'hybrid_random',   # 하이브리드 + 랜덤
            'weighted_sample'  # 가중 샘플링
        ]

        for i, strategy in enumerate(strategies[:num_combined]):
            try:
                if strategy == 'top_scored':
                    # 상위 점수 번호 중 6개 선택 (모집단 부족 시 _ensure_six가 1~45에서 보충)
                    selected = [num for num, score in sorted_numbers[:8]]
                    picked = random.sample(selected, min(6, len(selected)))
                    numbers = _ensure_six(picked)

                elif strategy == 'balanced':
                    # 고점수 + 중간점수 + 저점수 균형
                    # 각 구간이 비어 있을 수 있으므로 요청 개수를 구간 크기로 클램프
                    high = [num for num, score in sorted_numbers[:15]]
                    mid = [num for num, score in sorted_numbers[15:30]]
                    low = [num for num, score in sorted_numbers[30:45]]

                    numbers = []
                    numbers.extend(random.sample(high, min(3, len(high))))
                    numbers.extend(random.sample(mid, min(2, len(mid))))
                    numbers.extend(random.sample(low, min(1, len(low))))
                    numbers = _ensure_six(numbers)

                elif strategy == 'model_consensus':
                    # 가장 많은 모델이 예측한 번호들 우선
                    number_count = {}
                    for pred in all_predictions:
                        for num in pred.get('numbers', []):
                            number_count[num] = number_count.get(num, 0) + 1

                    consensus_numbers = sorted(number_count.items(), key=lambda x: x[1], reverse=True)
                    selected = [num for num, count in consensus_numbers[:12]]
                    picked = random.sample(selected, min(6, len(selected)))
                    numbers = _ensure_six(picked)

                elif strategy == 'hybrid_random':
                    # 상위 점수와 랜덤 조합
                    high_scored = [num for num, score in sorted_numbers[:20]]
                    numbers = random.sample(high_scored, min(4, len(high_scored)))

                    # 나머지는 1~45 실제 범위에서 보충 (목표 6개)
                    remaining = [n for n in range(1, 46) if n not in numbers]
                    need = 6 - len(numbers)
                    if need > 0 and remaining:
                        numbers.extend(random.sample(remaining, min(need, len(remaining))))
                    numbers = _ensure_six(numbers)

                else:  # weighted_sample
                    # 가중치 기반 샘플링 (모집단이 6개 미만이면 가능한 만큼만 뽑고 보충)
                    weights = np.array([score for num, score in sorted_numbers], dtype=float)
                    weight_sum = weights.sum()
                    sample_size = min(6, len(sorted_numbers))
                    if sample_size > 0 and weight_sum > 0:
                        selected_indices = np.random.choice(
                            len(sorted_numbers),
                            size=sample_size,
                            replace=False,
                            p=weights / weight_sum
                        )
                        picked = [sorted_numbers[idx][0] for idx in selected_indices]
                    else:
                        picked = [num for num, score in sorted_numbers[:sample_size]]
                    numbers = _ensure_six(picked)

                # 신뢰도 계산 (참여 모델 수와 평균 신뢰도 기반)
                avg_confidence = sum(pred.get('confidence', 0) for pred in all_predictions) / len(all_predictions)
                model_diversity = len([p for p in prediction_sources.values() if p])
                combined_confidence = avg_confidence * (0.8 + 0.1 * model_diversity)

                # Task 6: Combined 신뢰도 계산 과정 투명성
                if i == 0:  # 첫 번째 전략만 상세 로깅
                    logging.info(f"\n  [Combined 신뢰도 계산]")
                    logging.info(f"    - 평균 신뢰도: {avg_confidence:.3f}")
                    logging.info(f"    - 모델 다양성: {model_diversity}개")
                    logging.info(f"    - 최종 신뢰도: {avg_confidence:.3f} × (0.8 + 0.1 × {model_diversity}) = {combined_confidence:.3f}")

                combined_predictions.append({
                    'numbers': numbers,
                    'confidence': combined_confidence,
                    'model': 'combined',  # model 키 추가 (중요!)
                    'strategy': strategy,
                    'source_models': [name for name, preds in prediction_sources.items() if preds],
                    'model_count': model_diversity
                })

            except Exception as e:
                logging.debug(f"Combined 전략 {strategy} 실패: {e}")
                continue

        logging.info(f"[Combined] {len(combined_predictions)}개 예측 생성 완료")
        return combined_predictions

    except Exception as e:
        logging.error(f"Combined 예측 생성 실패: {e}")
        return []


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
    parser.add_argument('--once', action='store_true',
                        help='1회 실행 후 즉시 종료 (스크립트/CI/서브프로세스용). '
                             '기본은 사이클 완료 후 상주하여 대시보드(5001)+백그라운드 최적화(OPTUNA)+새 회차 감지를 유지.')
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

    # 최적화 체크포인트 시스템 옵션
    parser.add_argument('--optimize-threshold', action='store_true', help='임계값 자동 최적화 실행')
    parser.add_argument('--continue-optimization', action='store_true', help='중단된 최적화 이어서 실행')
    parser.add_argument('--optimization-iterations', type=int, default=0, help='최적화 반복 횟수 (기본값: 0=무제한, 숫자=제한)')
    parser.add_argument('--reset-checkpoint', action='store_true', help='최적화 체크포인트 초기화')
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
    parser.add_argument('--enhanced-feedback', action='store_true', default=True, help='향상된 피드백 루프 (영구 상태 저장)')
    parser.add_argument('--no-enhanced-feedback', dest='enhanced_feedback', action='store_false', help='향상된 피드백 루프 비활성화')
    parser.add_argument('--realtime-learning', action='store_true', help='실시간 학습 활성화')
    parser.add_argument('--monitoring', action='store_true', help='성능 모니터링 대시보드 생성')
    parser.add_argument('--hyperparameter-tuning', action='store_true', help='하이퍼파라미터 자동 튜닝')
    
    # 무한 학습 방지 옵션 추가
    parser.add_argument('--no-auto-adjust', action='store_true', help='자동 조정 시스템 비활성화')
    parser.add_argument('--no-realtime-learning', action='store_true', help='실시간 학습 비활성화')
    parser.add_argument('--max-ml-iterations', type=int, default=10, help='ML 최적화 최대 반복 횟수 (기본: 10)')

    # 성능 최적화 옵션 추가
    parser.add_argument('--stream-processing', action='store_true', help='스트림 기반 필터링 (메모리 효율적)')
    parser.add_argument('--no-parallel', action='store_true', help='병렬 처리 비활성화')
    parser.add_argument('--batch-size', type=int, default=50000, help='스트림 처리 배치 크기 (기본: 50,000)')
    parser.add_argument('--memory-limit', type=int, default=1500, help='메모리 제한 (MB, 기본: 1500)')
    parser.add_argument('--rss-warn-mb', type=int, default=4000, help='[P3-4] 전체 프로세스 RSS 경고 임계값 (MB, 기본: 4000). 실측 피크 약 3455MB 기준 헤드룸 포함. --memory-limit(필터 청크 제한)와 별개')

    # 자동화 시스템 전용 옵션
    parser.add_argument('--predict-only', action='store_true', help='예측만 수행 (필터링 건너뛰기)')
    parser.add_argument('--fetch-only', action='store_true', help='데이터 수집만 수행')
    # [최적화 2026-06-01, Codex gpt-5.5 + Gemini 3.1-pro 합의] 극단성 풀 전용 fast 모드.
    # 최종 예측은 ExtremenessPoolPredictor(8.14M 자체 채점→K풀)가 담당하므로, 그 앞단계의
    # 구 16필터 전체/증분 필터링(8.14M 재처리, 수 분)은 신 경로에 불필요한 낭비다.
    # 이 플래그가 켜지면: ①구 16필터 스킵 ②백테스트 자동복구(구 필터 재실행) 차단
    # ③포함률 통계는 미측정 처리. 구 경로/통계가 필요하면 이 플래그 없이 실행.
    # env LOTTO_FAST_EXTREMENESS_ONLY=1 로도 활성화 가능.
    parser.add_argument('--fast-extremeness-only', action='store_true',
                        help='극단성 풀 전용 fast 모드: 구 16필터 전체필터링/백테스트 자동복구 스킵 (F5 실행 단축)')
    
    # 대시보드 옵션 추가 (기본값: OFF, 성능 최적화를 위해 opt-in 방식으로 변경)
    parser.add_argument('--dashboard', action='store_true', help='웹 대시보드 활성화 (포트 5001)')
    parser.add_argument('--no-dashboard', action='store_true', help='[DEPRECATED] Use --dashboard to enable. Dashboard is now OFF by default.')
    parser.add_argument('--dashboard-port', type=int, default=5000, help='웹 대시보드 포트 (기본: 5000, 실제로는 5001 고정)')
    
    args = parser.parse_args()
    
    # 인자가 없으면 자동으로 --auto-improve + --dashboard 활성화
    if len(sys.argv) == 1:
        args.auto_improve = True
        args.monitoring = True
        args.realtime_learning = True  # 실시간 학습도 자동 활성화
        args.dashboard = True  # [O] 대시보드도 자동 활성화
        print("[INFO] 인자가 없어 자동으로 --auto-improve + --dashboard 모드로 실행합니다.")
        print("   모든 최적화 기능(실시간 학습, 웹 대시보드 포함)이 활성화됩니다!")
        print("   대시보드: http://127.0.0.1:5001\n")
    
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
                # 향상된 대시보드 v2 모듈 임포트
                try:
                    from src.scripts.enhanced_dashboard_v2 import run_enhanced_dashboard_v2
                    print("\n[대시보드] 향상된 웹 대시보드 v2를 시작합니다...")
                    print(f"[대시보드] 브라우저에서 http://127.0.0.1:{port} 접속하세요.")
                    print("[대시보드] 대시보드는 백그라운드에서 계속 실행됩니다.\n")
                    run_enhanced_dashboard_v2(host='127.0.0.1', port=5001)
                except ImportError:
                    print("[대시보드] 웹 대시보드 v2 모듈을 찾을 수 없습니다.")

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
        except Exception as e:
            # [health-repair-7] 베어 except 제거 - 자동 열기 실패 원인을 debug로 남긴다
            logging.debug(f"브라우저 자동 열기 실패: {e}")
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
                logging.info("[START] 24시간 자동 실행 시스템 가동 시작!")
                logging.info("="*60)
                logging.info("  [기능] 설정 변경 자동 감지 및 재필터링")
                logging.info("  [기능] 새 회차 자동 감지 및 데이터 수집")
                logging.info("  [기능] 매일 오전 9시 자동 예측 생성")
                logging.info("  [기능] 매주 일요일 시스템 최적화")
                logging.info("  [종료] Ctrl+C로 안전하게 종료")
                logging.info("="*60)
                
                # 테스트 모드면 5분 후 종료
                if test_mode:
                    logging.info("[TEST] 테스트 모드 - 5분 후 자동 종료")
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
            except Exception as e:
                # [health-repair-7] 베어 except 제거 - 상태 출력 실패 원인을 debug로 남긴다
                logging.debug(f"시스템 상태 출력 실패: {e}")
        
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
    # 스마트 학습 시스템 전역 변수 (종료 시 정리를 위해)
    global unified_optimizer_global, continuous_improvement_global, optimization_stop_flag, auto_scheduler_global
    unified_optimizer_global = None
    continuous_improvement_global = None
    optimization_stop_flag = {'stop': False}  # 백그라운드 최적화 종료 플래그
    auto_scheduler_global = None  # graceful_shutdown에서 정상 종료를 위해 전역 보관

    # 종료 신호 핸들러 설정
    import signal
    import atexit

    def graceful_shutdown(signum=None, frame=None):
        """우아한 종료 처리 (재진입 안전: signal + atexit + Phase3 finally 중복 호출 방지)"""
        if getattr(graceful_shutdown, '_done', False):
            return
        graceful_shutdown._done = True
        try:
            logging.info("\n프로그램 종료 신호 감지...")

            # Phase 3: UnifiedOptimizer 종료 (Optuna 최적화 + 피드백 루프 통합 처리)
            if unified_optimizer_global:
                logging.info("[UnifiedOptimizer] 통합 최적화기 종료 중...")
                # 백테스팅 프레임워크 싱글톤에도 종료 플래그 전파
                try:
                    from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
                    bt_instance = OptimizedBacktestingFramework.get_instance()
                    if bt_instance:
                        bt_instance.set_shutdown_flag(optimization_stop_flag)
                except Exception:
                    pass
                unified_optimizer_global.stop()
                logging.info("[UnifiedOptimizer] 종료 완료")

            if continuous_improvement_global:
                logging.info("[CONTINUOUS IMPROVEMENT] 지속적 개선 시스템 종료 중...")
                continuous_improvement_global.stop_continuous_improvement()
                logging.info("[CONTINUOUS IMPROVEMENT] 시스템 종료 완료")

            # AutoScheduler 종료 (백그라운드 스케줄 스레드 정상 종료)
            if auto_scheduler_global:
                try:
                    auto_scheduler_global.stop()
                    logging.info("[AutoScheduler] 스케줄러 종료 완료")
                except Exception:
                    pass

            # [dashboard-monitoring-3] EnsemblePerformanceMonitor 최종 영속화
            # (record_prediction 주기적 flush 외에, 종료 시 마지막 부분 배치까지 저장)
            try:
                from src.monitoring.ensemble_monitor import get_ensemble_monitor
                get_ensemble_monitor().save_history()
                logging.info("[EnsembleMonitor] 히스토리 최종 저장 완료")
            except Exception:
                pass
        except Exception as e:
            logging.error(f"종료 처리 중 오류: {e}")

        # 시그널(Ctrl+C=SIGINT / SIGTERM)로 호출된 경우, 핸들러가 반환만 하면
        # 메인 흐름이 계속 진행되어 즉시 멈추지 않는다. 실제로 프로세스를 종료한다 (orchestration-2).
        # atexit 경로(signum=None)에서는 sys.exit 재진입이 혼란을 유발하므로 제외.
        if signum is not None:
            sys.exit(0)

    # 신호 핸들러 등록
    signal.signal(signal.SIGINT, graceful_shutdown)  # Ctrl+C
    signal.signal(signal.SIGTERM, graceful_shutdown)  # 종료 신호
    atexit.register(graceful_shutdown)  # 프로그램 정상 종료 시
    
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

    # ========================================
    # 최적화 체크포인트 시스템 처리 (DEPRECATED - 코드 제거됨)
    # 백그라운드 Optuna 스레드가 동일 기능을 자동 수행합니다.
    # ========================================
    if args.optimize_threshold or args.continue_optimization:
        logging.warning("\n" + "="*60)
        logging.warning("[DEPRECATED] --optimize-threshold 플래그는 제거되었습니다.")
        logging.warning("   백그라운드 최적화가 main.py 실행 시 자동으로 시작됩니다.")
        logging.warning("="*60 + "\n")

    # [2026-06-06] 단일 실행파일 정책: plain `python main.py`(또는 인자 없는 F5)는 한 사이클로
    # 예측을 즉시 생성한 뒤에도 '종료하지 않고 상주'하여 대시보드(5001) + 백그라운드 최적화
    # (OPTUNA 누적) + 새 회차 자동 감지를 계속 유지한다. (--24h 플래그 없이도 '모두 실행')
    # - 1회만 돌고 끝내려면: --once
    # - 부분/자동 실행(--ml-only/--predict-only/--fetch-only/--skip-fetch/--automation-test)은
    #   서브프로세스(예: AutoScheduler)에서 호출되므로 자동으로 1회 실행 후 종료(상주 안 함 -> hang 방지).
    _one_shot = bool(
        getattr(args, 'once', False) or args.ml_only or args.predict_only or args.fetch_only
        or args.skip_fetch or getattr(args, 'automation_test', False)
    )
    _resident_mode = not _one_shot
    if _resident_mode and not args.dashboard and not getattr(args, 'no_dashboard', False):
        args.dashboard = True  # 상주 모드는 대시보드 항상 ON (단일 실행파일로 '모두 실행')

    # 웹 대시보드 시작 (상주 모드는 자동 ON, 그 외 opt-in)
    if args.dashboard:
        start_web_dashboard(port=5001)  # 항상 포트 5001 사용
        logging.info("[대시보드] 백그라운드에서 실행 중입니다 (http://127.0.0.1:5001)")
        logging.info("[대시보드] '새 예측 생성' 버튼으로 언제든지 예측을 생성할 수 있습니다.")
    elif args.no_dashboard:
        # Deprecation warning for old flag
        logging.warning("[대시보드] --no-dashboard flag is deprecated. Dashboard is now OFF by default.")
        logging.warning("[대시보드] Use --dashboard flag to enable the dashboard.")
    else:
        logging.info("[대시보드] 대시보드가 비활성화되어 있습니다. 사용하려면 --dashboard 플래그를 추가하세요.")
    
    # 자동 개선 모드 활성화
    if args.auto_improve:
        args.enhanced_feedback = True  # 향상된 피드백 루프 사용
        args.feedback_loop = False  # 기존 피드백 루프 비활성화
        args.realtime_learning = True
        args.monitoring = True
        args.skip_optimization = False
        # [P3-2 FIX] fractal은 argparse default=False라, 무인자/--auto-improve 경로에서
        # 2349 블록(realtime_learning이 이미 True라 스킵됨) 안의 args.fractal=True 대입에
        # 도달하지 못해 조용히 비활성이었다. '모든 최적화 활성화' 의도대로 여기서 직접 켠다.
        # (ML 자체를 끈 모드는 존중: 아래 2356 정책과 동일. --no-fractal로 끌 수 있음)
        if not args.skip_ml and not args.predict_only:
            args.fractal = True

    # 실시간 학습을 기본적으로 활성화 (명시적으로 비활성화하지 않은 경우)
    if not args.no_realtime_learning and not args.realtime_learning:
        args.realtime_learning = True
        args.hyperparameter_tuning = True
        logging.info("[O] 실시간 학습 시스템이 기본적으로 활성화되었습니다.")
        # [FIX 2026-05-31] 사용자가 명시적으로 끈 플래그(--skip-ml/--skip-backtest/--predict-only)는
        # 존중한다. 기존엔 무조건 skip_ml=False/모든모델=True로 덮어써 --skip-ml이 무력화됐음
        # (predict-only인데도 ensemble이 7.9M 학습 생성 → 병목). 명시 비활성 시 강제 활성 금지.
        if not args.skip_ml and not args.predict_only:
            args.skip_backtest = False  # 백테스팅도 자동 활성화
            args.ml_only = False  # 전체 프로세스 실행 (ML만 하지 않음)
            # 모든 ML 모델 활성화
            args.lstm = True
            args.ensemble = True
            args.monte_carlo = True
            args.bayesian = True
            args.fractal = True
            logging.info("자동 개선 모드 활성화: 모든 최적화 기능이 켜집니다.")
        else:
            logging.info("[실시간 학습] --skip-ml/--predict-only 존중: ML 모델 강제 활성화 안 함")
    
    # 시작 시간 기록
    start_time = time.time()

    # 메모리 모니터링 시작
    # [P3-4] 전체 프로세스 RSS 경고 임계값은 --rss-warn-mb(기본 4000)로 분리.
    #        --memory-limit(기본 1500)은 스트림 필터 청크 제한 전용이라 RSS 경고와 의미가 달라 섞지 않는다.
    memory_monitor = MemoryMonitor(threshold_mb=getattr(args, 'rss_warn_mb', None) or 4000)
    memory_monitor.start_monitoring(interval=1.0)
    log_memory("프로그램 시작")

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

    # ========================================
    # [FIX N-C27] ErrorPreventionSystem 초기화 및 포괄적 건강 점검
    # 24시간 무인 운영을 위한 추가 오류 예방 레이어
    # ========================================
    if ERROR_PREVENTION_AVAILABLE:
        try:
            _eps = ErrorPreventionSystem()
            _eps_result = _eps.run_comprehensive_check()
            # run_comprehensive_check()는 실패 항목을 최상위 'failed_checks' 리스트로 반환한다.
            # (과거 'results' 키 + boolean status 비교는 존재하지 않는 키라 항상 빈 리스트 -> 복구 미실행 버그)
            _critical = _eps_result.get('failed_checks', [])
            if _critical:
                logging.warning(f"[ErrorPrevention] {len(_critical)}개 잠재적 문제 감지 - 자동 복구 시도")
                _eps.auto_fix_issues()
            else:
                logging.info("[ErrorPrevention] 포괄적 건강 점검 통과")
        except Exception:
            logging.warning("[ErrorPrevention] 점검 중 오류 (비치명적)", exc_info=False)

    # ========================================
    # [CACHE] 자동 캐시 정리 시스템
    # ========================================
    try:
        cache_cleaner = AutoCacheCleaner()
        cache_status = cache_cleaner.get_cache_status()

        logging.info(f"[CACHE] 현재 캐시 크기: {cache_status['total_size_gb']:.2f} GB / {cache_status['max_size_gb']:.2f} GB")
        logging.info(f"[CACHE] 사용률: {cache_status['usage_percentage']:.1f}%")

        if cache_status['needs_cleanup']:
            logging.info("[CACHE] 캐시 정리가 필요합니다. 자동 정리를 실행합니다...")
            cleanup_result = cache_cleaner.run_cleanup()

            if cleanup_result['cleaned']:
                logging.info(f"[CACHE] 정리 완료: {cleanup_result['deleted_files']}개 파일 ({cleanup_result['deleted_size_mb']:.2f} MB) 삭제")
                logging.info(f"[CACHE] 정리 후 크기: {cleanup_result['total_size_gb']:.2f} GB")
            else:
                logging.info("[CACHE] 정리할 파일이 없습니다.")
        else:
            logging.info("[CACHE] 캐시 상태 양호 - 정리 불필요")

    except Exception as e:
        logging.warning(f"[CACHE] 캐시 정리 시스템 오류 (무시하고 계속): {e}")

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
            # [NEW] 시작 시 동기화 체크 및 자동 업데이트
            # ========================================
            try:
                logging.info("\n[시작 동기화] 시스템 상태 확인 중...")
                from src.core.system_state_manager import SystemStateManager

                state_mgr = SystemStateManager()
                latest_round = db_manager.get_latest_round()

                if state_mgr.check_sync_needed(latest_round):
                    logging.warning("[시작 동기화] 동기화 필요 - 자동 업데이트 시작...")

                    # 통합 필터 관리자로 자동 업데이트 실행
                    logging.info("[시작 동기화] 설정 로드 중...")

                    # ThresholdManager에서 threshold 가져오기 (BUG-002 수정)
                    from src.core.threshold_manager import get_threshold_manager
                    threshold_manager = get_threshold_manager()
                    threshold = threshold_manager.get_threshold()

                    from src.core.integrated_filter_manager import IntegratedFilterManager
                    filter_mgr = IntegratedFilterManager(db_manager, threshold)

                    # 자동 업데이트 실행
                    filter_mgr.on_new_round_added(latest_round)

                    # 시스템 상태 업데이트
                    state_mgr.update_state(latest_round, components=['all', 'pattern', 'filter', 'ml'])

                    logging.info("[시작 동기화] [O] 자동 업데이트 완료")
                else:
                    logging.info("[시작 동기화] [O] 시스템 동기화 상태 양호")

            except Exception as e:
                logging.error(f"[시작 동기화] 동기화 체크 실패: {e}")
                logging.info("[시작 동기화] 프로그램을 계속 진행합니다...")

            # NOTE: 사전 검증 블록 제거됨 (본 검증과 중복, 필터 시스템 초기화 전 실행되어 불완전)
            # 필터 검증은 필터 시스템 초기화 후 본 검증(FilterValidator)에서 수행됩니다.

            # ========================================
            # [CHECK] 실시간 모니터링 시스템 초기화
            # ========================================
            auto_repair_system = AutoRepairSystem(db_manager, config_manager)
            
            # 24시간 자동화 모드 또는 일반 실행 모드에 관계없이 실시간 모니터링 시작
            auto_repair_system.start_monitoring()
            logging.info("[OK] 실시간 시스템 모니터링 활성화")
            
            # ========================================
            # [Phase 3] 통합 최적화기 초기화
            # ========================================
            try:
                unified_optimizer_global = UnifiedOptimizer(db_manager)
                logging.info("[UnifiedOptimizer] 통합 최적화기 초기화 완료 (백그라운드 시작은 필터링 완료 후)")
            except Exception as e:
                logging.warning(f"[UnifiedOptimizer] 초기화 실패 (계속 진행): {e}")
                unified_optimizer_global = None

            # ========================================
            # [Phase 2] 통합 최적화 DB 초기화 및 마이그레이션
            # ========================================
            try:
                get_optimization_db().run_initial_migration()
                logging.info("[OPTIMIZATION DB] 통합 최적화 DB 초기화 완료 (data/optimization.db)")
            except Exception:
                logging.warning("[OPTIMIZATION DB] 초기화 실패 (비치명적, 계속 진행)")

            # ========================================
            # [NEW] 지속적 개선 엔진 초기화
            # ========================================
            continuous_improvement = None
            try:
                logging.info("\n[CONTINUOUS IMPROVEMENT] 지속적 개선 엔진 초기화 중...")
                continuous_improvement = ContinuousImprovementEngine(db_manager)
                # 전역 변수에 할당 (종료 시 정리를 위해)
                continuous_improvement_global = continuous_improvement

                # [v5 FIX #11] 단일 진입점 강제: ContinuousImprovementEngine 자동 스케줄러 비활성화.
                # 근거(Codex/Gemini 교차검증 + 53에이전트 감사): UnifiedOptimizer(Optuna)가
                # threshold 최적화 단일 진입점(MEMORY Phase3 통합). ContinuousImprovementEngine,
                # AutoAdjustmentV2, FilterAutoAdjuster가 동일 YAML/DB를 동시 수정하면 논리적 race로
                # threshold가 비결정적 진동 → 통과율 15.69%p 급락/자동 롤백 4회의 근본 원인.
                # 객체는 상태 조회/graceful shutdown용으로 유지하되 자동 조정 스케줄러는 끔.
                ENABLE_CONTINUOUS_IMPROVEMENT_SCHEDULER = False  # UnifiedOptimizer가 단일 진입점
                # 스케줄러 활성화 여부와 무관하게 상태를 먼저 조회(역대 최고 성능 로그용).
                # 이전엔 status가 if 블록 안에서만 할당돼 스케줄러 비활성 시 UnboundLocalError 발생했음.
                status = continuous_improvement.get_status()
                if ENABLE_CONTINUOUS_IMPROVEMENT_SCHEDULER:
                    continuous_improvement.start_continuous_improvement()
                    logging.info("[CONTINUOUS IMPROVEMENT] 지속적 개선 시스템 활성화 완료")
                    logging.info(f"  - 시스템 상태: {status['status']}")
                    logging.info(f"  - 자동 최적화: 매일 21:00 (토요일은 20:30)")
                    logging.info(f"  - 개선 기준: 조금이라도 개선되면 즉시 적용")
                else:
                    logging.info("[CONTINUOUS IMPROVEMENT] 자동 스케줄러 비활성화 (UnifiedOptimizer 단일 진입점)")
                    # [2026-06-14 honesty] 활성 최적화는 극단성 풀 가중치(pool 모드)다. threshold/criteria는 레거시.
                    logging.info("  - 최종예측용 극단성 풀 가중치(extremeness_weights.json)를 UnifiedOptimizer(PoolOptimizer v6, TPE)가 최적화")
                    logging.info("  - threshold/criteria(1.1%)는 레거시 컷오프로 최종 5세트 예측 미사용(최적화 안 함)")
                    logging.info("  - 객체는 상태 조회/종료 정리 용도로만 유지")

                if status.get('best_performance_ever'):
                    _bp = status['best_performance_ever']
                    logging.info(f"  - (참고) 레거시 ML 백테스트 최고 성적: 한 게임당 평균 {_bp['avg_matches']:.3f}개 맞음 (6개 중, 백분율 아님 / 무작위도 약 0.8개)")
                    logging.info(f"  - (참고) 당시 레거시 threshold 설정값: {_bp['threshold']}% -- 최종 극단성 풀 예측과는 무인과(죽은 컷오프)")

                # 초기 백테스팅 실행 (옵션)
                # NOTE: 활성 최적화는 PoolOptimizer(pool 모드, Optuna TPE). 구버전 Grid Search/CMA-ES threshold는 폐기.
                if not args.skip_backtest:
                    logging.info("[CONTINUOUS IMPROVEMENT] 백그라운드 최적화 준비됨 (실제 시작은 UnifiedOptimizer가 담당)")
                    logging.info("   - [O] Optuna TPE 기반 Bayesian 최적화 (pool 모드: 극단성 풀 가중치 탐색)")
                    logging.info("   - [O] 누적 학습: 최적화 시도를 10번씩 쌓아가며 점점 똑똑해짐 (0->10->20->30...회)")
                    logging.info("   - [O] SQLite persistence: 자동 중단/재시작 지원")
                    # optimization_result = continuous_improvement.manual_optimization()  # DISABLED (Grid Search)
                    # if optimization_result.get('success'):
                    #     logging.info(f"[O] 초기 최적화 완료: 성능 {optimization_result.get('improvement_rate', 0):.1%} 개선")
                    # else:
                    #     logging.info("초기 최적화: 현재 설정이 최적 상태")

            except Exception as e:
                logging.warning(f"지속적 개선 엔진 초기화 실패: {e}")
                continuous_improvement = None
                continuous_improvement_global = None

            # AutoScheduler 초기화 - 자동 업데이트를 위해 실행
            # NOTE: --fetch-only, --predict-only, --ml-only 모드에서는 건너뜀
            #       (subprocess에서 main.py를 호출할 때 무한 스폰 방지)
            if args.fetch_only or args.predict_only or getattr(args, 'ml_only', False):
                logging.info("[자동 업데이트] 서브프로세스 모드 - AutoScheduler 건너뜀")
            else:
                try:
                    from src.automation.auto_scheduler import AutoScheduler
                    auto_scheduler = AutoScheduler(db_manager)
                    auto_scheduler_global = auto_scheduler  # graceful_shutdown 접근용

                    # DatabaseManager 콜백 등록
                    auto_scheduler.setup_db_callbacks()
                    logging.info("[자동 업데이트] DatabaseManager 콜백 등록 완료")

                    auto_scheduler.start()  # 백그라운드에서 실행
                    logging.info("[자동 업데이트] 새 회차 자동 확인 기능이 활성화되었습니다.")
                    logging.info("[자동 업데이트] 토요일 20:45 ~ 21:30 집중 모니터링")
                    logging.info("[자동 업데이트] 다른 날은 3시간마다 확인")
                    logging.info("[자동 업데이트] 토요일 20시 기준으로 회차 자동 전환")
                except Exception as e:
                    logging.warning(f"[자동 업데이트] 초기화 실패 (수동 업데이트 필요): {e}")

            # Phase 3: UnifiedOptimizer 준비 완료 로그 (실제 시작은 필터링 완료 후)
            if unified_optimizer_global:
                logging.info("[UnifiedOptimizer] 백그라운드 최적화 준비 완료 (필터링 완료 후 시작 예정)")

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
        
        # [2026-06-14 근본제거] AutoAdjustmentSystemV2 비활성화(레거시 죽은 손잡이).
        #  이 시스템은 global_probability_threshold(옛 16필터/확률필터 컷오프) 하나만 백테스트 성능으로
        #  '자동 조정'했는데, 최종 5세트는 극단성 풀(ExtremenessPoolPredictor)이 담당하며 이 임계값을
        #  전혀 참조하지 않는다(grep 0건). 즉 조정해도 최종예측 불변(DEAD_THEATER) + state(0.75)/YAML(1.1)
        #  desync로 매 재시작 '자가 교정' 노이즈만 냈다. 실제 활성 최적화는 PoolOptimizer(extremeness_weights)
        #  + target_K 정책이 담당한다. -> 인스턴스화하지 않아 하위 모든 'if auto_adjustment:' 블록을 스킵.
        auto_adjustment = None
        logging.info("\n[자동 조정] 비활성(레거시): 옛 확률필터 컷오프 전용 -> 최종 5세트(극단성 풀) 예측과 무관")
        logging.info("  - 실제 활성 최적화: PoolOptimizer(극단성 풀 가중치) + target_K 정책")
        
        # 데이터 수집 (선택적 건너뛰기)
        if not args.skip_fetch:
            logging.info("\n[데이터 수집] 로또 당첨 번호 수집 시작...")
            collector = DataCollector(db_manager=db_manager, meta_manager=meta_manager)
            collector.fetch_lotto_data()

            # [NR-P0-2 FIX] 데이터 수집 직후 상태 재동기화 안전망.
            # 근본원인: 시작 동기화(위쪽 블록)는 데이터 수집 '전' DB 회차로 판단하므로, 수집으로 새로
            # 들어온 회차(예: 1217,1218)가 system_state에 반영되지 않아 1216에 멈춤. --fetch-only
            # subprocess 경로는 아래에서 즉시 return하므로 상태 갱신이 통째로 누락됨.
            # 여기서 최신 회차를 재조회해 필터기준 갱신 + 상태 갱신(두 경로 모두 보장).
            try:
                from src.core.system_state_manager import SystemStateManager as _SSM
                _ssm = _SSM()
                _latest2 = db_manager.get_latest_round()
                if _latest2 and _ssm.check_sync_needed(_latest2):
                    logging.warning(f"[수집후 동기화] 새 회차 감지 -> 상태/필터기준 갱신: {_latest2}회차")
                    try:
                        from src.core.integrated_filter_manager import IntegratedFilterManager as _IFM
                        from src.core.threshold_manager import get_threshold_manager as _gtm
                        _IFM(db_manager, _gtm().get_threshold()).on_new_round_added(_latest2)
                    except Exception as _fe:
                        logging.error(f"[수집후 동기화] 필터기준 갱신 실패: {_fe}")
                    _ssm.update_state(_latest2, components=['all', 'pattern', 'filter', 'ml'])
                    logging.info(f"[수집후 동기화] [O] 상태 갱신 완료: {_latest2}회차")
            except Exception as _se:
                logging.error(f"[수집후 동기화] 실패: {_se}")

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
            
            # 추가 통계 분석 (핫/콜드 넘버 포함) - 결과가 후속 파이프라인에서 미사용, DEBUG 레벨에서만 실행
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                try:
                    logging.debug("\n[STATISTICS] 통계 분석 시작 (핫/콜드 넘버 포함)")

                    stats_analyzer = LottoStatisticsAnalyzer()

                    hot_cold_stats = stats_analyzer.analyze_hot_cold_numbers()
                    logging.debug(f"[STATISTICS] 핫 넘버 (상위 10개): {hot_cold_stats['hot_numbers'][:10]}")
                    logging.debug(f"[STATISTICS] 콜드 넘버 (하위 10개): {hot_cold_stats['cold_numbers'][:10]}")

                    odd_even_stats = stats_analyzer.analyze_odd_even_distribution()
                    consecutive_stats = stats_analyzer.analyze_consecutive_patterns()
                    ac_stats = stats_analyzer.analyze_ac_values()

                    logging.debug(f"[STATISTICS] 홀짝 분포 상위 5개: {dict(list(odd_even_stats.items())[:5])}")
                    logging.debug(f"[STATISTICS] 연속번호 패턴: {consecutive_stats}")
                    logging.debug(f"[STATISTICS] AC값 평균: {ac_stats['avg']:.2f}, 범위: {ac_stats['min']}~{ac_stats['max']}")

                    logging.debug("[STATISTICS] [OK] 통계 분석 완료")

                except Exception as e:
                    logging.debug(f"[STATISTICS] [X] 통계 분석 실패: {str(e)}")
            else:
                logging.info("[STATISTICS] 통계 분석 건너뜀 (DEBUG 모드에서만 실행)")
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
        
        # FIX-08b: use_weighted_system 기본값 설정 (--predict-only 시 NameError 방지)
        use_weighted_system = True

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
            # [긴급 FIX] True->False: WeightedFilterSystem(점수 30점)은 "통과율 개선"을 위해
            # 거의 모든 조합을 통과시켜 풀이 791만(97%) 잔존 → 핵심 전략(800만→30만) 무력화.
            # 적응형 확률 필터(16필터 누적)로 전환하여 통계적 극단 제거 복원.
            # (WeightedFilterSystem 도입 이유였던 "통과율 낮음"은 P0/P1 수정으로 이미 100% 확보)
            use_weighted_system = False  # 적응형 확률 필터 활성화 (핵심 전략 복원)
        
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
                # ThresholdManager에서 threshold 가져오기 (BUG-002 수정)
                from src.core.threshold_manager import get_threshold_manager
                threshold_manager = get_threshold_manager()
                threshold = threshold_manager.get_threshold()

                # [2026-06-14 honesty] 이 적응형/16필터 계층은 최종 5세트(극단성 풀)에 미사용인 레거시다.
                #  과거 '모드: 공격적(많은 패턴 제외)' 라벨은 실제 16필터 직렬 누적 제거율(~0.5%)과 정반대라 삭제.
                logging.info("="*60)
                logging.info(f"[레거시 필터] 적응형/16필터 (참고용 - 최종 5세트는 극단성 풀이 담당)")
                logging.info(f"  컷오프 임계값: {threshold}% (옛 확률필터/앙상블 fine-tune 표본용, 최종예측 미사용)")
                logging.info("="*60)

                # 통합 필터 매니저 사용 (적응형 + 개별 필터)
                from src.core.integrated_filter_manager import IntegratedFilterManager
                filter_manager = IntegratedFilterManager(db_manager, threshold)
                
                # 과거 당첨번호 분석 및 필터 업데이트
                # [v5 FIX #2] 전체 역사 분석(기존 [:200]은 가장 오래된 200회 버그)
                winning_numbers = db_manager.get_all_winning_numbers()
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

        # 메모리 효율성 패치 적용 - 모듈이 없으므로 주석 처리
        # try:
        #     apply_emergency_patch()
        #     filter_manager = patch_filter_manager(filter_manager)

        #     # 메모리 효율적 조합 관리자 추가
        #     memory_efficient_manager = MemoryEfficientCombinationsManager(
        #         db_manager,
        #         max_memory_mb=args.memory_limit if hasattr(args, 'memory_limit') else 1500
        #     )
        #     filter_manager.memory_efficient_manager = memory_efficient_manager

        #     logging.info("[O] 메모리 효율성 패치 및 관리자 적용됨")
        #     logging.info(f"  - 메모리 임계값: {memory_efficient_manager.max_memory_mb:,}MB")
        #     logging.info(f"  - 배치 크기: {memory_efficient_manager.current_batch_size:,}개")
        # except Exception as e:
        #     logging.warning(f"메모리 패치 적용 실패: {e}")

        # 메모리 관련 기본 설정 적용
        logging.info("메모리 효율성 설정 적용")
        if hasattr(filter_manager, 'batch_size'):
            logging.info(f"  - 배치 크기: {filter_manager.batch_size:,}개")
        if hasattr(filter_manager, 'memory_limit_mb'):
            logging.info(f"  - 메모리 제한: {filter_manager.memory_limit_mb:,}MB")

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
            _v_start = max(1, latest_round - 100)
            _v_count = latest_round - _v_start + 1
            logging.info("\n" + "="*60)
            # 검증A(보존율): 최근 N회 당첨번호가 필터를 통과(보존)하는지 — 참고 지표.
            # (적응형 최적화 단계의 검증B와 모수/목적이 다르므로 라벨로 구분)
            logging.info(f"[필터 검증A/보존율] 최근 {_v_count}회 당첨번호 필터 통과(보존) 검증 시작 - 참고 지표...")
            logging.info("="*60)

            filter_validator = FilterValidator(filter_manager, db_manager)
            validation_results = filter_validator.validate(
                start_round=_v_start,
                end_round=latest_round
            )
            
            # [2026-06-14 죽은계산 제거] suggest_optimized_criteria(target_pass_rate=95) 호출 삭제:
            #  반환값 optimized_criteria가 이후 어디서도 사용되지 않는 죽은 계산이었다(grep 0건). 사용자 확정
            #  전략이 통과율 95% 제약을 제거했으므로 이 계산 자체가 무의미한 잔재. 통과율은 아래에서 참고지표로만 표시.

            # [전략 정합 2026-06-01] 사용자 확정 전략(MEMORY: user-strategy-final-decision):
            #   "통과율 95%를 강제 목표/제약으로 두지 않는다." 통과율 하락을 이유로 필터 기준을
            #   자동 완화하면 "출현율 낮은 극단 패턴 최대 제거" 목표와 정면 충돌한다.
            #   따라서 통과율 기반 필터 자동 조정을 비활성화하고, 통과율은 '참고 지표'로만 표시한다.
            #   제거 강도(임계값) 조정은 Optuna(극단성 풀) 단일 진입점에 위임한다.
            if isinstance(validation_results, dict):
                _pr = validation_results.get('pass_rate', validation_results.get('overall_pass_rate'))
                try:
                    if _pr is not None:
                        logging.info(f"[참고] 당첨번호 필터 통과율: {float(_pr):.2f}% (참고 지표 - 자동 조정하지 않음)")
                except (TypeError, ValueError):
                    pass
            logging.info("[전략] 통과율 기반 필터 자동 완화 비활성화 (사용자 확정: 통과율 제약 제거)")
        else:
            logging.info("\n[필터 검증] 건너뛰기")
        
        # 적응형 필터 최적화 실행 (신규)
        if not args.skip_optimization:
            logging.info("\n[적응형 최적화] 실시간 필터 최적화 시작...")
            adaptive_optimizer = AdaptiveFilterOptimizer(db_manager)
            optimization_results = adaptive_optimizer.optimize_filters_adaptive(latest_round)
            
            if optimization_results['optimized']:
                # [2026-06-14 honesty] 레거시 16필터 대상 최적화(최종예측=극단성 풀과 무관). config.yaml filters.criteria
                #  부재 시 실제 적용 0건일 수 있어 '완료'를 '점검/시도'로 정직 표기(NO_OP 거짓완료 방지).
                logging.info(f"  - (레거시 16필터) {len(optimization_results['optimized_filters'])}개 필터 기준 점검 - 최종예측 무관")
        else:
            logging.info("\n[적응형 최적화] 건너뛰기")
        
        # 필터링 모드 결정 및 필터 적용
        update_mode = 'full' if args.full_filter or args.force_filter else 'incremental'

        # [최적화 2026-06-01] 극단성 풀 전용 fast 모드 판정 (Codex+Gemini 합의).
        # 최종 예측이 ExtremenessPoolPredictor(자체 풀 생성)이고 fast 모드가 켜져 있으면
        # 구 16필터 전체/증분 필터링은 불필요한 낭비 -> 스킵. 백테스트 자동복구도 함께 차단.
        _fast_extreme = (getattr(args, 'fast_extremeness_only', False)
                         or os.environ.get('LOTTO_FAST_EXTREMENESS_ONLY', '0') == '1')

        # 성능 측정 시작
        filter_start_time = time.time()

        # 스트림 처리 모드 선택
        # [predict-only] 신 극단성 풀 경로(ExtremenessPoolPredictor)가 8.14M을 자체 채점/제거하여
        # 풀을 직접 만들므로, 여기서 16필터 전체 필터링(7.9M, 수 분 소요)은 불필요 -> 건너뜀.
        if args.predict_only or _fast_extreme:
            _why = "예측 전용" if args.predict_only else "fast 극단성 풀 전용"
            logging.info(f"\n[필터링] {_why} 모드 - 16필터 전체 필터링 건너뜀 (극단성 풀 경로가 자체 풀 생성)")
        elif args.stream_processing:
            logging.info("\n[STREAM] 스트림 처리 모드: 메모리 효율적인 스트림 기반 필터링을 사용합니다.")
            logging.info(f"  - 배치 크기: {args.batch_size:,}개")
            logging.info(f"  - 메모리 제한: {args.memory_limit}MB")
            logging.info("  - 예상 처리 시간: 2-3분 (메모리 사용량 90% 감소)")
            log_memory("스트림 필터링 시작 전")

            # 스트림 설정 업데이트
            if hasattr(filter_manager, 'stream_processor'):
                filter_manager.stream_processor.config.batch_size = args.batch_size
                filter_manager.stream_processor.config.memory_limit_mb = args.memory_limit

            # 스트림 기반 필터링 실행
            success = filter_manager.apply_filters_streaming(latest_round)
            log_memory("스트림 필터링 완료")
            if not success:
                logging.warning("스트림 처리 실패, 기존 방식으로 fallback")
                filter_manager.apply_filters(latest_round, 'full', force=True)
                log_memory("Fallback 필터링 완료")
        else:
            # 기존 방식 필터링
            # 계산된 모드에 따라 최적화된 필터링 실행
            if update_mode == 'full':
                logging.info("\n[필터링 전체 모드] 모든 필터를 처음부터 적용합니다...")
                log_memory("전체 필터링 시작 전")
                if args.parallel and 'parallel_filter_manager' in locals():
                    logging.info("  - 병렬 처리 모드 사용 (예상 시간: 1-2분)")
                    parallel_filter_manager.apply_filters_parallel(filter_manager.db_manager.combinations_db.get_all_base_combinations(), latest_round)
                else:
                    logging.info("  - 예상 처리 시간: 3-5분 (전체 조합 재계산)")
                    filter_manager.apply_filters(latest_round, 'full', force=True)
                log_memory("전체 필터링 완료")
            else:
                logging.info("\n[필터링 증분 모드] 필요한 필터만 업데이트합니다...")
                logging.info("  - 예상 처리 시간: 30초-1분 (변경된 부분만 처리)")
                log_memory("증분 필터링 시작 전")
                # 증분 모드에서는 기존 결과를 활용하여 성능 최적화
                force_required = not filter_manager._check_previous_filtering_results(latest_round) if hasattr(filter_manager, '_check_previous_filtering_results') else False
                filter_manager.apply_filters(latest_round, 'incremental', force=force_required)
                log_memory("증분 필터링 완료")
        
        # 성능 측정 결과 출력 (predict-only/fast 모드는 필터링을 건너뛰므로 보고서 불필요)
        filter_elapsed_time = time.time() - filter_start_time
        if not args.predict_only and not _fast_extreme:
            logging.info(f"\n[성능 보고서] 필터링 완료")
            logging.info(f"  - 모드: {update_mode.upper()}")
            logging.info(f"  - 실행 시간: {filter_elapsed_time:.1f}초")

            # [2026-06-06 가짜지표 제거] 과거: estimated_full_time = 실행시간*4(가정)로 빼서
            # 실행시간과 무관하게 항상 '75% 향상'이 찍히는 동어반복(실측 비교 없음, 0개 처리에도 '절약' 주장
            # -> CLAUDE.md NO FAKE DATA 위반)이었다. 실측 baseline이 없으므로 가짜 절약률/시간은 출력하지 않고
            # '변경분만 처리'라는 사실만 표기한다.
            if update_mode == 'incremental':
                logging.info("  - 증분 모드: 변경분만 처리(전체 8.14M 재처리 생략)")
        
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
        # 필터링된 조합 개수 조회 (로그 표시용 - 이후 ML 예측에는 직접 사용 안 함)
        if not args.predict_only and not _fast_extreme and filter_manager:
            try:
                # [P3-1] IntegratedFilterManager(기본 경로 래퍼)에는 get_filtered_count가 없어
                #        매 실행 AttributeError -> "필터링 조합 수 조회 실패" warning이 떴음.
                #        래퍼 타입과 무관하게 DB를 직접 COUNT하는 메서드로 교체(line 3445와 동일 API, 표시값 동일).
                filtered_count = db_manager.combinations_db.get_filtered_combinations_count(latest_round)
                if filtered_count and filtered_count > 0:
                    # [정직성 수정] 이 '구필터 통과 풀'은 최종 5세트 예측에 직접 쓰이지 않는다.
                    #   실제 최종 예측 풀은 극단성 풀(ExtremenessPoolPredictor)이 담당한다.
                    #   과거 "필터링된 조합 N개로 ML 예측 수행" 문구는 마치 이 풀로 예측하는 것처럼
                    #   오해를 유발했으므로, 레거시 진단용임을 명시한다. (변수/흐름은 보존)
                    ratio = filtered_count / 8145060 * 100
                    logging.info(f"\n[참고] 구필터 통과 풀 {filtered_count:,}개 "
                                 f"(레거시 진단용 - 최종 5세트 예측엔 미사용, 극단성 풀이 담당)")
                    logging.info(f"  - 전체(8,145,060) 대비 {ratio:.1f}% (참고 지표)")
                    logging.info(f"  - 실제 최종 예측 풀은 극단성 풀 (아래 [극단풀] 진단 로그 참조)")
                else:
                    logging.info(f"\n[참고] 구필터 통과 풀 개수 조회값 0/미상 "
                                 f"(레거시 진단용 - 최종 예측은 극단성 풀이 담당)")
            except Exception as e:
                # 가짜 '약 20만개' 하드코딩 대신, 조회 실패 사실과 원인을 정직하게 기록
                filtered_count = 0
                logging.warning(f"\n[참고] 구필터 통과 풀 개수 조회 실패 "
                                f"(레거시 진단용 - 최종 예측은 극단성 풀이 담당, 원인: {e})")
        else:
            filtered_count = 0
            logging.info(f"\n[ML/AI] 예측 전용 모드 - 필터링 없이 ML 예측 수행")

        # ML/AI 분석 및 예측 (선택적)
        if not args.skip_ml:
            logging.info("\n" + "="*60)
            logging.info("[ML/AI 분석] 인공지능 기반 분석 및 예측 시작...")
            logging.info("="*60)
            log_memory("ML/AI 분석 시작")
            
            # 당첨번호 데이터 준비
            winning_numbers = db_manager.get_all_winning_numbers()
            
            if winning_numbers and len(winning_numbers) >= 50:
                # 1. LSTM 시계열 예측
                if args.lstm and ML_AVAILABLE:
                    try:
                        logging.info("\n[LSTM] 시계열 예측 모델 실행...")
                        lstm_predictor = LSTMPredictor(sequence_length=15)  # [ml-lstm-ensemble-6] ML-003: 50->15 단일소스(lstm_predictor 기본값)와 일치

                        # 모델 학습 (필요시) - [C1 2026-06-13] 회차 무효화(ensemble과 대칭):
                        #  과거: h5가 있으면 is_trained=True라 새 회차가 와도 train()이 호출조차 안 돼
                        #  옛 가중치를 silent 재사용했다. -> 학습회차(trained_round)가 최신과 다르거나
                        #  미상(None, 레거시 h5/미학습)이면 재학습한다. 재학습 실패 시 is_trained=False로
                        #  남아 predict_next_numbers가 []를 반환하므로 stale 예측이 나가지 않는다.
                        _lstm_round = getattr(lstm_predictor, 'trained_round', None)
                        if (not lstm_predictor.is_trained) or (_lstm_round != latest_round):
                            if lstm_predictor.is_trained and _lstm_round != latest_round:
                                logging.info(f"  - LSTM 캐시 회차({_lstm_round}) != 최신({latest_round}) -> 재학습")
                                lstm_predictor.is_trained = False  # 재학습 실패 시 stale 예측 차단
                            else:
                                logging.info("  - LSTM 모델 학습 중...")
                            try:
                                lstm_predictor.train(winning_numbers, epochs=30, batch_size=32,
                                                     trained_round=latest_round)
                            except Exception as lstm_train_e:
                                logging.warning(f"  - LSTM 학습 실패: {lstm_train_e}")
                                logging.info("  - LSTM 모델을 건너뛰고 계속합니다...")
                                # continue 제거 - 여기서는 불필요
                        
                        # 예측 수행
                        lstm_predictions = lstm_predictor.predict_next_numbers(
                            winning_numbers[-15:],  # [ml-lstm-ensemble-6] sequence_length=15와 결합 정합
                            num_predictions=args.predictions
                        )
                        
                        logging.info(f"  - LSTM 예측 완료: {len(lstm_predictions)}개 조합")
                        for i, pred in enumerate(lstm_predictions[:3], 1):
                            logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%})")
                    
                    except Exception as e:
                        logging.error(f"  - LSTM 예측 실패: {str(e)}")
                
                # 2. 앙상블 모델 예측 (필터링된 풀 학습 통합)
                if args.ensemble and ML_AVAILABLE:
                    try:
                        logging.info("\n[Ensemble] 앙상블 모델 (RF+XGBoost+NN) 실행...")
                        ensemble_predictor = EnsemblePredictor()

                        # [재시작 최적화 2026-06-01] 저장된 모델 로드 시도 -> 데이터(회차) 무변경이면
                        # 재학습/미세조정(실측 약 8분)을 스킵. 회차 불일치/캐시없음/손상이면 정상 재학습(가드).
                        _ens_reuse = False
                        try:
                            ensemble_predictor.load_models()
                            _cached_round = getattr(ensemble_predictor, 'trained_round', None)
                            if ensemble_predictor.is_trained and _cached_round == latest_round:
                                _ens_reuse = True
                                logging.info(f"  - [최적화] 저장된 앙상블 모델 재사용 (학습회차 {_cached_round}=최신 {latest_round}, 재학습/미세조정 스킵)")
                            elif _cached_round is not None:
                                logging.info(f"  - 앙상블 캐시 회차({_cached_round}) != 최신({latest_round}) -> 재학습")
                                ensemble_predictor.is_trained = False
                        except Exception as _load_e:
                            # [가시화 2026-06-05] 재사용 실패가 debug로 묻히면 '불필요한 fresh 재학습 ->
                            # 간헐적 사일런트0' 원인을 추적할 수 없다. WARNING으로 올려 다음 실행에서
                            # 재사용 실패 사유(캐시 손상/메모리/회차불일치)를 즉시 보이게 한다.
                            logging.warning(f"  - 앙상블 캐시 로드/재사용 실패 -> fresh 재학습: {_load_e}")
                            ensemble_predictor.is_trained = False

                        # 모델 학습 (필요시) - 클래스 불균형 예외 처리 추가
                        if not ensemble_predictor.is_trained:
                            logging.info("  - 앙상블 모델 학습 중...")
                            try:
                                evaluation = ensemble_predictor.train(winning_numbers, test_size=0.2)
                                if evaluation:
                                    logging.info(f"  - 학습 완료: 정확도 {evaluation.get('ensemble', {}).get('accuracy', 0):.4f}")
                            except Exception as ensemble_train_e:
                                error_msg = str(ensemble_train_e)
                                if "least populated class" in error_msg or "minimum number of groups" in error_msg:
                                    logging.warning("  - 클래스 불균형 문제로 앙상블 학습 실패. 단순 모델로 대체")
                                    # 대체 모델 없음 - 앙상블 건너뛰기
                                    logging.info("  - 앙상블 모델을 건너뛰고 계속합니다...")
                                    ensemble_predictions = []  # 빈 예측 리스트로 설정
                                else:
                                    logging.warning(f"  - 앙상블 학습 실패: {ensemble_train_e}")
                                    logging.info("  - 앙상블 모델을 건너뛰고 계속합니다...")
                                    ensemble_predictions = []  # 빈 예측 리스트로 설정

                        # === 필터링된 풀 기반 미세조정 ===
                        # [재시작 최적화] 재사용(_ens_reuse) 시 이미 미세조정된 모델이 로드됐으므로 스킵.
                        if not _ens_reuse and filter_manager and ensemble_predictor.is_trained:
                            try:
                                # [2026-06-14 honesty] fine_tune_model은 RF/XGB/NN '재학습'을 구조 보호 위해 전부 스킵하는
                                #  no-op이며, 실제로 하는 일은 필터풀 10K 샘플을 앙상블의 '예측 후보풀'(filtered_pool)로
                                #  설정하는 것뿐이다. 과거 '미세조정 완료/통과율 8.5->15% 향상' 로그는 거짓이라 정정.
                                logging.info("\n  [Filtered Pool] 앙상블 예측 후보풀 설정(필터풀 10K 샘플)...")
                                from src.ml.filtered_pool_trainer import FilteredPoolTrainer

                                pool_trainer = FilteredPoolTrainer(pool_sample_size=10000)
                                ensemble_predictor = pool_trainer.fine_tune_model(
                                    ensemble_predictor, db_manager, filter_manager, winning_numbers
                                )
                                logging.info("  - 예측 후보풀 설정 완료 (RF/XGB/NN 재학습은 모델 구조 보호 위해 미수행)")
                                # [재시작 최적화] 미세조정 모델에 회차 도장 후 저장 -> 다음 재시작 시 재사용
                                try:
                                    ensemble_predictor.trained_round = latest_round
                                    ensemble_predictor.save_models()
                                    logging.info(f"  - 앙상블 모델 캐시 저장 (회차 {latest_round}) -> 다음 재시작 시 재사용")
                                except Exception as _save_e:
                                    logging.warning(f"  - 앙상블 모델 캐시 저장 실패: {_save_e}")
                            except Exception as finetune_e:
                                logging.warning(f"  - 필터링된 풀 미세조정 실패: {finetune_e}")
                                logging.info("  - 기본 앙상블 모델로 계속합니다...")

                        # 예측 수행 (재사용/학습성공 경로 모두에서 예측 생성)
                        # [2026-06-06 가드버그 수정] 과거: ensemble_predictions가 main.py:2881에서 []로
                        # 사전 초기화돼 'not in locals()'가 항상 False -> 캐시 재사용 경로에서
                        # predict_next_numbers가 호출조차 안 돼 매 실행 사일런트 0개가 발생했다.
                        # -> 예측이 비어있고 모델이 학습돼 있으면 실제로 예측을 수행하도록 교정한다.
                        # (학습 실패로 의도적 []인 경우는 is_trained=False라 자동 스킵.)
                        if not ensemble_predictions and getattr(ensemble_predictor, 'is_trained', False):
                            ensemble_predictions = ensemble_predictor.predict_next_numbers(
                                winning_numbers,
                                num_predictions=args.predictions
                            )

                        logging.info(f"  - 앙상블 예측 완료: {len(ensemble_predictions)}개 조합")
                        # [복구 2026-06-05] fresh 재학습 모델이 간헐적으로 0개를 내는 사일런트 실패 방어.
                        # 실측 진단: 디스크 캐시 앙상블 모델은 정상 동작(예측 10개 반환)이 확인됐다.
                        # 따라서 fresh 예측이 0개면 '검증된 캐시 모델'을 별도 인스턴스로 로드해 재시도하여
                        # ML 보조신호(번호 다양성 가중치 입력)를 복구한다. 캐시도 0개면 정직하게 빈 결과 유지.
                        if not ensemble_predictions:
                            try:
                                _ens_recovery = EnsemblePredictor()
                                _ens_recovery.load_models()
                                if getattr(_ens_recovery, 'is_trained', False):
                                    _rec_preds = _ens_recovery.predict_next_numbers(
                                        winning_numbers, num_predictions=args.predictions)
                                    if _rec_preds:
                                        ensemble_predictions = _rec_preds
                                        logging.info(
                                            f"  - [복구] fresh 0개 -> 검증된 캐시 앙상블 모델로 "
                                            f"{len(ensemble_predictions)}개 예측 복구")
                            except Exception as _rec_e:
                                logging.debug(f"  - 앙상블 캐시 복구 시도 실패: {_rec_e}")
                        # [가시화 2026-06-03] 캐시 복구도 실패해 여전히 0개면 사일런트 실패(scaler 입력
                        # feature 차원 불일치 학습 vs 예측, 또는 샘플링 전수 제외) 가능성이 높다.
                        # INFO로만 묻히지 않게 WARNING으로 원인 진단을 유도한다.
                        # (최종 5세트는 극단성 풀이 생성하므로 결과엔 영향 없음 - ML 보조신호만 결손.)
                        if not ensemble_predictions:
                            logging.warning(
                                "  - [진단] 앙상블 예측 0개 (fresh+캐시 복구 모두 실패) - "
                                "scaler feature 차원 불일치 또는 샘플링 전수 제외 가능성 -> 원인 점검 필요. "
                                "최종 5세트는 극단성 풀이 생성하므로 결과엔 영향 없음(ML 보조신호만 결손).")
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
                        
                        # 최적 조합 추출 - 더 많은 고신뢰도 예측 생성
                        mc_predictions = mc_simulator.get_best_combinations(
                            n_combinations=max(10, args.predictions * 2),  # 더 많은 예측 생성
                            min_confidence=0.5  # 신뢰도 제한 완화 (향상된 계산으로 보정)
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

            # 6. Combined 예측 생성 (모든 ML 예측 통합)
            try:
                logging.info("\n[Combined] ML 예측 통합 실행...")
                combined_predictions = combine_ml_predictions(
                    lstm_predictions=lstm_predictions if 'lstm_predictions' in locals() else None,
                    ensemble_predictions=ensemble_predictions if 'ensemble_predictions' in locals() else None,
                    mc_predictions=mc_predictions if 'mc_predictions' in locals() else None,
                    bayesian_predictions=bayesian_predictions if 'bayesian_predictions' in locals() else None,
                    fractal_predictions=fractal_predictions if 'fractal_predictions' in locals() else None,
                    num_combined=args.predictions
                )

                if combined_predictions:
                    logging.info(f"  - Combined 예측 완료: {len(combined_predictions)}개 조합")
                    for i, pred in enumerate(combined_predictions[:3], 1):
                        models = ", ".join(pred.get('source_models', []))
                        logging.info(f"    {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.2%}) [{models}]")
                else:
                    logging.warning("  - Combined 예측 생성 실패")

            except Exception as e:
                logging.error(f"  - Combined 예측 실패: {str(e)}")
                combined_predictions = []

            # 백테스팅 실행 (ML/AI 직후가 논리적)
            # 주의: 자동 조정 시스템에서도 백테스팅이 실행되므로 중복 방지
        else:
            # ML/AI 분석 건너뜀 (--skip-ml). 신 예측 경로(극단성 풀)는 ML 없이도 동작하므로 정상.
            # [FIX 2026-05-31] winning_numbers는 ML 블록 내부에서만 정의되므로 여기서 참조하지 않음
            # (--skip-ml이 실제로 동작하게 된 뒤 드러난 UnboundLocalError 수정).
            logging.info("[ML/AI] 건너뜀 (--skip-ml): 극단성 풀 경로가 ML 없이 5세트 생성")

        # ML만 수행 모드
        if args.ml_only:
            pass  # ML만 수행 모드에서는 별도 처리 없음

        # ================================================================
        # [Phase 3] UnifiedOptimizer 백그라운드 최적화 시작 (ML 학습 완료 후)
        # ================================================================
        # FIX: ML 학습 전에 시작하면 백테스팅에서 미학습 모델로 예측 시도 → WARNING 발생
        #      ML 학습 완료 후 시작하여 모델 캐시를 활용하도록 이동
        if unified_optimizer_global is not None:
            try:
                unified_optimizer_global.start_background(optimization_stop_flag)
                logging.info("[UnifiedOptimizer] 백그라운드 최적화 시작 (ML 학습 완료 후)")
            except Exception as e:
                logging.warning(f"[UnifiedOptimizer] 백그라운드 최적화 시작 실패: {e}")

        # ================================================================
        # 백테스팅 - 필터링+ML 통합 검증 (최적화)
        # ================================================================
        # [FIX] 수정: auto_adjustment와 관계없이 백테스팅 항상 실행 (DB 저장을 위해)
        if not args.skip_backtest:
            logging.info("\n" + "="*60)
            logging.info("[백테스팅] ML 보조신호(LSTM/Ensemble/MC) 자유예측 성능 검증 - 최종 5세트(극단성 풀)는 아래 [풀 백테스트]가 검증")
            logging.info("="*60)
            log_memory("백테스팅 시작")
            if auto_adjustment:
                logging.info("[INFO] 자동 조정 모드이지만 성능 통계를 위해 백테스팅을 실행합니다.")
            else:
                logging.info("[INFO] 백테스팅 결과가 자동으로 DB에 저장됩니다.")

            # ============================================================
            # FIX: Pre-Backtesting Validation - Ensure Filtered Pool Exists
            # ============================================================
            logging.info("\n[검증] 필터링된 조합 풀 확인 중...")
            filtered_count = db_manager.combinations_db.get_filtered_combinations_count(latest_round)
            logging.info(f"  - 회차 {latest_round}: {filtered_count:,}개 조합")

            if filtered_count == 0 and _fast_extreme:
                # [최적화 2026-06-01] fast 극단성 풀 모드에서는 구 16필터 풀이 없는 게 정상.
                # 자동복구로 apply_filters(full)를 돌리면 스킵한 의미가 사라지므로 차단한다.
                # 백테스트의 예측/매치 계산은 구 필터 풀과 무관(LSTM/Ensemble/MC가 생성),
                # combinations_db는 '풀 포함률 통계'에만 쓰이므로 이 지표만 미측정 처리된다.
                logging.info("[fast 모드] 구 16필터 풀 부재는 정상 - 자동복구 스킵 "
                             "(풀 포함률 통계만 미측정, 예측/매치/DB저장은 정상)")
            elif filtered_count == 0:
                logging.warning(f"[자동 복구] 회차 {latest_round}에 필터링된 조합이 없습니다!")
                logging.info("  - 필터링 재실행 중...")

                try:
                    # Force regenerate filtered combinations
                    filter_manager.apply_filters(latest_round, mode='full', force=True)

                    # Verify regeneration
                    filtered_count_after = db_manager.combinations_db.get_filtered_combinations_count(latest_round)

                    if filtered_count_after > 0:
                        logging.info(f"[O] 필터링 재실행 성공: {filtered_count_after:,}개 조합 생성")
                    else:
                        # [filters-16-6] 재필터링 후에도 0개 = 임계값 과강에 의한 '정상적 과제거' 가능성.
                        # 같은 임계값으로는 반복해도 0개이므로 추가 재시도 없이 직전 풀로 진행한다.
                        logging.warning(f"[X] 재필터링 후에도 0개 - 임계값 과강에 의한 과제거 가능성")
                        logging.info("  - 추가 재시도 없이 백테스팅은 이전 회차 풀을 사용합니다 "
                                     "(global_probability_threshold를 낮추면 풀이 복구됩니다)")

                except Exception as regen_error:
                    logging.error(f"[X] 필터링 재실행 중 오류: {regen_error}")
                    logging.info("  - 백테스팅은 이전 회차 데이터를 사용합니다")
            else:
                logging.info(f"[O] 필터링된 조합 풀 정상: {filtered_count:,}개")
            # ============================================================

            try:
                # 현재 임계값 정보 수집
                with open('configs/adaptive_filter_config.yaml', 'r', encoding='utf-8') as f:
                    adaptive_config = yaml.safe_load(f)

                threshold_info = {
                    'probability_threshold': adaptive_config.get('global_probability_threshold', 1.5),
                    'ml_bypass_filters': adaptive_config.get('ml_integration', {}).get('ml_bypass_filters', 12),
                    'ml_weight': adaptive_config.get('ml_integration', {}).get('ml_weight', 0.5),
                    'combination_count': 0,  # 백테스팅 후 업데이트됨
                    'ml_inclusion_rate': 0  # 백테스팅 후 계산됨
                }

                backtesting_framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
                backtest_results = backtesting_framework.run_backtest(
                    start_round=max(1, latest_round - 50),
                    end_round=latest_round - 1,  # 현재 회차 제외 (데이터 누출 방지)
                    window_size=100
                )

                # 임계값 정보를 백테스팅 결과에 추가
                if backtest_results:
                    # [정직화 2026-06-06] 과거: ml_inclusion_rate를 '예측수*0.085'(하드코딩 8.5% 추정)로,
                    # combination_count를 '8145060*(1-thr/100)'(추정)로 채워 metric으로 저장하려 했으나,
                    # (1) 둘 다 실측이 아닌 가짜 추정값이고 (2) DB 저장은 run_backtest 내부에서 이미
                    # 끝나 threshold_info가 도달하지 못해 항상 0/0.0으로 저장되던 죽은 코드였다(감사 확정).
                    # 또한 이 두 지표는 '구 16필터' 통계로, 최종 예측(극단성 풀)과 무관하다.
                    # -> 가짜 추정 계산을 제거한다. 실측이 필요하면 별도(필터 단계/풀 진단)에서 채운다.
                    # threshold_info의 실제 임계값(probability_threshold 등)만 결과에 부착(표시용).
                    backtest_results['threshold_info'] = threshold_info
                logging.info("백테스팅 최종 검증 완료")

                # [2026-06-06 정합] 풀-선택 백테스트: 사용자가 실제 받는 '1.5M 극단성 풀 5세트'를 blind 검증.
                # 위 legacy 백테스트는 ML 모델(8.14M 자유예측)을 채점하지만, 최종 예측은 극단성 풀이
                # 담당하므로 그 '실제 예측 경로'를 직접 채점한다(Codex gpt-5.5 + Gemini 3.1-pro 합의).
                # 무작위(같은 풀 / 전체) 대비 lift로 '진짜 우위'를 정직하게 보고. 최종예측엔 영향 없음(표시용).
                try:
                    from src.scripts.backtest_extremeness_prediction import run_pool_selection_backtest
                    _pool_bt = run_pool_selection_backtest(db_manager, folds=5, window=30)
                    if _pool_bt:
                        logging.info("\n" + "="*60)
                        logging.info("[풀 백테스트] 실제로 받는 5게임을 '과거 시점 기준'으로 공정 검증 (미래 안 봄)")
                        logging.info("="*60)
                        logging.info(
                            f"  - 5게임 중 하나라도 3개+ 맞은 비율(=등수 든 비율): {_pool_bt['rank_hit_rate']*100:.1f}% "
                            f"(같은 풀 무작위 {_pool_bt['rand_pool_hit']*100:.1f}% / 완전 무작위 {_pool_bt['rand_all_hit']*100:.1f}%)")
                        logging.info(
                            f"  - 한 회차에서 가장 많이 맞은 개수의 평균: {_pool_bt['mean_bm']:.3f}개 "
                            f"(같은 풀 무작위 {_pool_bt['rand_pool_bm']:.3f} / 완전 무작위 {_pool_bt['rand_all_bm']:.3f})")
                        logging.info(
                            f"  - 무작위보다 나은 정도: 등수 {_pool_bt['lift_rounds_vs_all']:+d}회 더 적중 "
                            f"(번호 다양화 효과만 {_pool_bt['lift_rounds_vs_pool']:+d}회), 검증 {_pool_bt['n']}회차")
                        logging.info("="*60)
                        globals()['_POOL_BACKTEST_SUMMARY'] = _pool_bt
                except Exception as _pe:
                    logging.warning(f"[풀 백테스트] 실행 실패(스킵, 최종예측엔 영향 없음): {_pe}")

                # [정리 2026-06-06] prediction_details 무한증가 방지: 30일 지난 백테스트 상세기록만 삭제.
                # (감사 확정: cleanup_old_data가 정의만 되고 호출처 0 -> 988MB/524만행 누적.)
                # 학습 데이터(당첨번호/모델/OPTUNA)와 무관 - 오래된 '백테스트 채점 상세'만 정리.
                # 주의: 첫 실행은 누적 backlog 삭제로 다소 시간 소요(이후 사이클은 소량). 파일 용량은
                # VACUUM이라야 줄지만, 운영 중 VACUUM은 잠금위험이라 별도(프로그램 정지 시) 수행 권장.
                try:
                    _psm = getattr(backtesting_framework, 'performance_stats_manager', None)
                    if _psm and hasattr(_psm, 'cleanup_old_data'):
                        _psm.cleanup_old_data(keep_days=30)
                        logging.info("[정리] 30일 경과 백테스트 상세기록 정리 완료(파일축소는 VACUUM 별도)")
                except Exception as _ce:
                    logging.warning(f"[정리] 백테스트 기록 정리 스킵: {_ce}")

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
                                # [정합 2026-06-06] 분산된 인라인 공식(min(1.0,avg/2.0)) 대신 통합
                                # PerformanceMetrics.normalize_score 단일소스 사용(수식 동일, source-of-truth 통일).
                                from src.core.performance_metrics import PerformanceMetrics as _PM
                                normalized = _PM.normalize_score(avg_matches)
                                total_score += normalized
                                model_count += 1
                        
                        if model_count > 0:
                            performance_score = total_score / model_count
                            
                            logging.info(f"\n[자동 조정 V2] 백테스팅 성능 점수: {performance_score:.3f}")

                            # [O] 임계값 자동 조정 (백테스팅 결과 재사용)
                            # 이유: 바로 위에서 백테스팅 완료했으므로 중복 실행 방지
                            adjustment_result = auto_adjustment.analyze_and_adjust(
                                performance_score,
                                skip_backtest=True  # 백테스팅 재실행 생략
                            )
                            
                            if adjustment_result['adjusted']:
                                logging.info("\n[ADJ] 필터링 재실행 필요")
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
                                # 실제 키는 소문자이므로 .upper() → .lower() 수정 (N-W22)
                                model_metrics = metrics.get(model_type.lower(), {})
                                avg_matches = model_metrics.get('avg_matches', 0)
                                dashboard.update_metrics('performance', model_type, avg_matches)
                        except Exception as e:
                            logging.error(f"모니터링 업데이트 실패: {str(e)}")
                    
                    # [2026-06-06] 레거시 no-op 피드백 루프 비실행: EnhancedFeedbackLoop/FeedbackLoopSystem 은
                    # 실질 no-op(개선이 best_params={}로 최종 예측에 미반영)이라 '[피드백 루프]' 로그가 혼란만 유발했다.
                    # 실제 '실행할수록 좋아지는' 최적화는 PoolOptimizer(OPTUNA, 백그라운드 누적 trial)가 담당.
                    # (본문은 비실행 - 변수 의존성 때문에 즉시 물리삭제 대신 게이트 차단. 추후 전용 정리에서 파일째 제거 예정.)
                    if False and (args.feedback_loop or args.enhanced_feedback) and backtest_results:
                        try:
                            logging.info("\n" + "="*60)
                            if args.enhanced_feedback:
                                # [정직화 2026-06-06] 감사 확정: 이 EnhancedFeedbackLoop.run_improvement_cycle은
                                # 실질 no-op이다(resume 캐시 반환, AutoMLOptimizer 0회 호출, best_models.params={},
                                # 개선 모델이 최종 예측(극단성 풀)에 도달하지 않음). 상태 영속/대시보드 표시 전용으로만 유지.
                                # 실제 '실행할수록 좋아지는' 최적화는 PoolOptimizer(OPTUNA, 백그라운드 누적 trial)가 담당한다.
                                logging.info("[피드백 루프(레거시)] 상태 영속 전용 - 실제 풀 최적화는 PoolOptimizer(OPTUNA)가 담당")
                            else:
                                logging.info("[피드백 루프(레거시)] 상태 점검 - 실제 최적화는 PoolOptimizer가 담당")
                            logging.info("="*60)
                            
                            # 향상된 피드백 루프 사용
                            if args.enhanced_feedback:
                                enhanced_feedback = EnhancedFeedbackLoop(db_manager)
                                cycle_results = enhanced_feedback.run_improvement_cycle(
                                    start_round=max(1, latest_round - 50),
                                    end_round=latest_round - 1,
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
                                    end_round=latest_round - 1
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
                    
                    # 자동 학습 시스템 상태 점검 및 자동 재시작
                    health_status = realtime_system.check_health_and_restart()
                    if health_status['status'] != 'healthy':
                        logging.warning(f"[!] 실시간 학습 시스템 상태 점검: {health_status['status']}")
                    
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
                    logging.info("\n[REPORT] 자동 개선 모드에서 종합 성능 보고서 생성...")
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
                                logging.info("\n[LOOP] 추가 피드백 루프 실행...")
                                additional_feedback = feedback_system.run_feedback_loop(
                                    models,
                                    start_round=max(1, latest_round - 49),
                                    end_round=latest_round - 1
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
            # [P3-6] 이 카운터는 '임계값 자동조정용 백테스트' 누적(별도 상태파일 auto_adjustment_state_v2.json).
            #        '모델개선 피드백루프' 누적(total_backtest_count)과는 측정대상이 달라 값이 다른 게 정상.
            logging.info(f"  [임계값 자동조정] 누적 백테스팅 횟수: {status['backtest_count']}회")
            logging.info(f"  마지막 성능: {status['last_performance']:.3f}")
            logging.info(f"  현재 임계값: {status['current_threshold']}%")
            logging.info(f"  모드: {status['mode']}")

            # [FIX] 프로그램 종료 시 불필요한 백테스팅 제거
            # 이유: 종료 직전 백테스팅이 임계값 조정 루프를 유발함
            # 백그라운드 최적화가 주기적으로 처리하므로 여기서는 상태만 출력
            #
            # 기존 코드 (제거됨):
            # logging.info("\n[자동 개선] 추가 백테스팅 실행...")
            # final_result = auto_adjustment.check_and_adjust()
            # if final_result.get('backtest_performance'):
            #     perf = final_result['backtest_performance']
            #     logging.info(f"최종 백테스팅 횟수: {perf.get('backtest_count', 0)}")
            #     logging.info(f"최종 성능 점수: {perf.get('performance_score', 0):.3f}")
        
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
                        # [2026-06-14 honesty] 이 16필터 검증은 최종예측(극단성 풀)에 미사용인 레거시 계층이고,
                        #  사용자 확정 전략상 '당첨번호 일부가 컷오프됨'은 버그가 아니라 의도된 동작(통과율=참고지표,
                        #  출현율 낮은 극단 최대 제거 우선)이다. -> CRITICAL ALERT를 INFO 참고로 강등(거짓 경보 제거).
                        logging.info(f"[참고/레거시] {round_num}회차 당첨번호가 옛 16필터 기준 일부 컷오프됨 "
                                     f"(필터: {', '.join([f['name'] for f in validation['failed_filters']])}) "
                                     f"- 최종 5세트(극단성 풀)와 무관, 의도된 동작")
                        
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
            # check_result가 빈 dict이면 KeyError 발생 → .get()으로 방어 (N-W23)
            check_status = check_result.get('status', 'unknown')
            if check_status == 'checked':
                # 결과 보고서 출력
                logging.info(check_result.get('report', ''))
            elif check_status == 'waiting':
                logging.info(f"{check_result.get('round', '?')}회차 당첨번호가 아직 발표되지 않았습니다.")
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

        # ML 예측 묶음 (신/구 경로 공통 입력)
        _ml_preds_bundle = {
            'lstm': lstm_predictions if 'lstm_predictions' in locals() else [],
            'ensemble': ensemble_predictions if 'ensemble_predictions' in locals() else [],
            'monte_carlo': mc_predictions if 'mc_predictions' in locals() else [],
            'bayesian': bayesian_predictions if 'bayesian_predictions' in locals() else [],
            'fractal': fractal_predictions if 'fractal_predictions' in locals() else [],
            'combined': combined_predictions if 'combined_predictions' in locals() else []
        }

        # ============================================================
        # [신 아키텍처 2026-05-31] 극단성 풀 + 5장 다양성 예측 (사용자 전략)
        # - 단일 극단성 점수로 목표 풀 크기 K(기본 1.5M)까지 극단 패턴 최대 제거
        # - 남은 풀에서 가중 max-coverage로 5장 다양성 극대화(많은 번호 맞추기)
        # - 통과율 강제 제약 없음. ML은 풀 내 번호 다양성 가중치로만 사용.
        # 비활성화: 환경변수 LOTTO_USE_EXTREMENESS_POOL=0 -> 구 ML-우선 경로로 폴백.
        # ============================================================
        final_predictions = None
        _use_extreme_pool = os.environ.get('LOTTO_USE_EXTREMENESS_POOL', '1') != '0'
        if _use_extreme_pool:
            try:
                from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor

                # [K 자동 재탐색 타이밍] 예측 직전에 정책 json(SSOT)이 stale(정책 round != 최신
                # DB round)이면 walk-forward Wilson LCB 곡선으로 운영 K를 재탐색한다.
                # 비용 주의: 재탐색은 fold별 8.14M 재채점이라 ~100s 소요.
                # [기본 활성 2026-06-03 사용자결정] 데이터가 새로 들어왔을 때만(정책 round != 최신 DB round)
                #   자동 재탐색하고, 데이터 무변경이면 비용 0으로 즉시 생략한다. 새 회차는 주 1회뿐이므로
                #   대부분 실행은 0s 생략, 새 회차 직후 첫 실행만 ~100s. -> "실행 시 항상 최신 데이터 기준
                #   K로 예측"이 보장된다(매 실행 자동 점검, 필요할 때만 재계산).
                # 비활성화(빠른 테스트 등): 환경변수 LOTTO_REFRESH_K_ON_PREDICT=0.
                # 참고: --24h 상주에서는 AutoScheduler(일요일3시/새회차)도 재탐색하나, stale 가드로 중복 무해.
                if os.environ.get('LOTTO_REFRESH_K_ON_PREDICT', '1') != '0':
                    try:
                        from src.core import extremeness_threshold_selector as _sel
                        _pol = _sel.load_policy()
                        _latest = db_manager.get_latest_round()
                        _pol_round = _pol.get('round') if _pol else None
                        if _pol is None or _pol_round != _latest:
                            logging.info(
                                f"[최종 예측] 새 데이터 감지(정책 round={_pol_round}, 최신={_latest}) "
                                f"-> K 자동 재탐색 실행(약 100s, 새 회차당 1회)")
                            _sel.refresh_policy(db_manager)
                        else:
                            logging.info(
                                f"[최종 예측] 정책 최신(round={_pol_round}) - K 재탐색 생략(데이터 무변경, 비용 0)")
                    except Exception as _re:
                        logging.warning(f"[최종 예측] K 재탐색 스킵(기존 정책 사용): {_re}")

                # target_K 미지정 -> 정책 json(SSOT) effective_target_K 사용(하위호환).
                _epp = ExtremenessPoolPredictor(db_manager)
                _epp.build_pool()  # 학습회차+K 동일 시 디스크 캐시 재사용(0.2s)
                final_predictions = _epp.predict(num_sets=5, ml_predictions=_ml_preds_bundle)
                logging.info(f"[최종 예측] 극단성 풀 경로 사용 (K={_epp.target_K:,})")
            except Exception as _e:
                logging.error(f"[최종 예측] 극단성 풀 경로 실패 - 구 경로로 폴백: {_e}")
                final_predictions = None

        # 폴백(또는 비활성화): 기존 ML-우선 하이브리드 경로
        if not final_predictions:
            final_predictions = generate_final_predictions(
                db_manager=db_manager,
                filter_manager=filter_manager,
                ml_predictions=_ml_preds_bundle,
                num_sets=5
            )

        # 예측 저장을 위한 데이터 준비
        predictions_to_save = []
        
        # 최종 예측 결과 출력
        logging.info("\n" + "="*30)
        logging.info("[RESULT] 최종 예측 번호 5세트")
        logging.info("="*30)
        
        for i, prediction in enumerate(final_predictions, 1):
            numbers_str = ', '.join(f"{num:2d}" for num in prediction['numbers'])
            confidence = prediction.get('confidence', 0)
            source = prediction.get('source', 'Unknown')
            
            logging.info(f"\n[PIN] 추천 {i}세트: [{numbers_str}]")
            # [2026-06-14 honesty] 극단성 풀 경로 confidence는 '전형성'(역대 분포 근접도) 백분위 = 당첨확률 아님.
            _conf_label = "전형성(역대분포 근접도, 당첨확률 아님)" if 'ExtremePool' in str(source) else "신뢰도(상대점수)"
            logging.info(f"   {_conf_label}: {confidence:.1%} | 출처: {source}")
            
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
        
        logging.info("\n" + "="*30)

        # [2026-06-06] 백테스트 검증 요약 첨부 - 사용자에게 '검증된 풀 내 최선'임을 정직 제시.
        # (Codex+Gemini 합의: '가장 높은 확률'은 절대 당첨확률이 아니라 극단 제거된 1.5M 풀 안에서
        #  백테스트로 검증된 커버리지 최선 포트폴리오임을 명시.)
        _pbt = globals().get('_POOL_BACKTEST_SUMMARY')
        if _pbt:
            logging.info(f"[검증] 위 5세트 '방식'의 최근 {_pbt['n']}회 blind 백테스트 성적:")
            logging.info(
                f"   - 등수적중률 {_pbt['rank_hit_rate']*100:.1f}% vs 무작위 {_pbt['rand_all_hit']*100:.1f}% "
                f"= 무작위 대비 {_pbt['lift_rounds_vs_all']:+d}회 우위 (평균 best-match {_pbt['mean_bm']:.2f})")
            logging.info(
                "   - 참고: '가장 높은 확률'은 절대 당첨확률이 아니라, 8.14M에서 극단 패턴을 제거한 "
                "1.5M 생존 풀 안에서 백테스트로 검증된 '커버리지 최선 5게임 포트폴리오'입니다.")

        # ================================================================
        # 예측 번호 데이터베이스 저장
        # ================================================================
        try:
            # 다음 회차 번호 계산 (토요일 저녁 8시 기준)
            latest_round = db_manager.get_last_round()

            # 현재 시간 확인
            current_time = datetime.now()
            current_weekday = current_time.weekday()  # 0=월요일, 5=토요일, 6=일요일
            current_hour = current_time.hour

            # 토요일 저녁 8시를 기준으로 회차 결정
            # 중요: 토요일 8시 이후에 당첨번호가 DB에 업데이트되면 latest_round가 이미 증가한 상태
            if current_weekday == 5 and current_hour < 20:  # 토요일 오후 8시 이전
                next_round = latest_round + 1  # 아직 이번 주 회차
                logging.info(f"토요일 {current_hour}시 - 아직 {next_round}회차 추첨 전")
            elif current_weekday == 5 and current_hour >= 20:  # 토요일 오후 8시 이후
                # 당첨번호가 이미 업데이트되었는지 확인
                # latest_round가 이미 오늘 추첨된 회차라면 +1, 아니면 현재 회차
                next_round = latest_round + 1  # 다음 주 회차
                logging.info(f"토요일 {current_hour}시 - {latest_round}회차 추첨 완료, {next_round}회차 예측")
            elif current_weekday == 6:  # 일요일
                next_round = latest_round + 1  # 다음 주 회차
                logging.info(f"일요일 - 다음 주 {next_round}회차 예측")
            else:  # 월~금요일
                next_round = latest_round + 1  # 이번 주 회차
                logging.info(f"{['월','화','수','목','금'][current_weekday]}요일 - 이번 주 {next_round}회차 예측")
            
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
        # 대시보드는 상단 start_web_dashboard() 호출로 이미 백그라운드 스레드에서 실행 중
        # 여기서 중복 기동하면 포트 5001 충돌(OSError) + while True 루프로 메인 스레드 블록
        # → 중복 기동 코드 제거 (N-C24 수정)
        # ================================================================
        if args.dashboard:
            logging.info("\n[대시보드] 이미 백그라운드에서 실행 중입니다.")
            logging.info("[대시보드] 주소: http://127.0.0.1:5001")

        # [2026-06-06] 상주 모드: 사이클 완료 후 종료하지 않고 대시보드 + 백그라운드 최적화(OPTUNA)
        # + 새 회차 자동 감지를 계속 유지한다. 모든 백그라운드 작업은 daemon 스레드라 메인 스레드가
        # 살아있어야 동작하므로 여기서 블록한다. Ctrl+C(SIGINT) 시 graceful_shutdown 이 최적화/
        # 스케줄러를 정리하고 sys.exit 한다. (1회만 실행하려면 --once)
        if _resident_mode:
            logging.info("\n" + "="*60)
            logging.info("[상주] 사이클 완료 - 종료하지 않고 상주합니다 (단일 실행파일로 모두 실행).")
            logging.info("[상주] 대시보드: http://127.0.0.1:5001  |  '새 예측 생성'으로 언제든 예측")
            logging.info("[상주] 백그라운드 최적화(OPTUNA) + 새 회차 자동 감지 유지 중")
            logging.info("[상주] 종료: Ctrl+C  (1회만 실행하려면: python main.py --once)")
            logging.info("="*60)
            try:
                while not optimization_stop_flag.get('stop', False):
                    time.sleep(5)
            except KeyboardInterrupt:
                graceful_shutdown(signal.SIGINT, None)
        
    except Exception as e:
        logging.error(f"프로그램 실행 중 오류 발생: {str(e)}")
        logging.error(traceback.format_exc())
        logging.info("="*60)
        raise
    finally:
        # 자동화 시스템은 run_24h_automation 내부에서 처리됨
        
        # Phase 3: UnifiedOptimizer 종료 처리 (graceful_shutdown에서도 처리되나 이중 안전장치)
        try:
            if unified_optimizer_global:
                unified_optimizer_global.stop()
        except Exception:
            pass
        
        # 향상된 피드백 루프 상태 저장
        try:
            if 'enhanced_feedback' in locals() and enhanced_feedback:
                logging.info("프로그램 종료 시 상태 저장 중...")
                enhanced_feedback.improvement_manager.save_state()
                logging.info("상태 저장 완료")
        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")
        
        # 메모리 모니터링 종료 및 리포트
        try:
            if 'memory_monitor' in locals():
                log_memory("프로그램 종료 전")
                memory_monitor.stop_monitoring()
                logging.info(memory_monitor.get_report())

                # 메모리 압박 상태 확인
                if memory_monitor.check_memory_pressure():
                    memory_monitor.suggest_gc()
        except Exception as e:
            logging.error(f"메모리 모니터링 종료 실패: {e}")

        # matplotlib 정리 작업
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception as e:
            # [health-repair-7] 베어 except 제거 - 정리 실패는 무시 가능하나 원인을 debug로 남긴다
            logging.debug(f"matplotlib 정리 실패(무시 가능): {e}")

def _apply_hybrid_filtering(numbers, filter_manager, db_manager, relaxation_level, ml_threshold=None):
    """
    하이브리드 필터링 시스템 - ML 예측에 최적화된 다단계 필터링

    Args:
        numbers: 검증할 번호 조합
        filter_manager: 필터 매니저
        db_manager: 데이터베이스 매니저
        relaxation_level: 완화 레벨 (1: 기본, 2: 중간, 3: 최고)
        ml_threshold: ML 전용 임계값 (None이면 ThresholdManager에서 가져옴)

    Returns:
        (passes_filter: bool, result_info: dict)
    """
    try:
        # ml_threshold가 None이면 ThresholdManager에서 가져오기 (BUG-002 수정)
        if ml_threshold is None:
            from src.core.threshold_manager import get_threshold_manager
            threshold_manager = get_threshold_manager()
            ml_threshold = threshold_manager.get_ml_relaxed_threshold()

        # 기본 유효성 검사
        if not (len(set(numbers)) == 6 and all(1 <= n <= 45 for n in numbers)):
            return False, {"error": "기본 유효성 검사 실패"}

        # 완화 레벨별 필터 적용 전략
        filter_strategies = {
            1: {  # 기본 완화
                'critical_only': ['odd_even'],
                'skip_filters': ['consecutive', 'match', 'pattern'],
                # relaxed_threshold = ml_threshold x 2 (예: 기준값 0.3% 가정 시 0.6%).
                # 실제 값은 ThresholdManager의 동적 ml_relaxed_threshold에 비례.
                'relaxed_threshold': ml_threshold * 2,
                'max_failures': 2
            },
            2: {  # 중간 완화
                'critical_only': ['odd_even'],
                'skip_filters': ['consecutive', 'match', 'pattern', 'frequency', 'recent'],
                # relaxed_threshold = ml_threshold x 1 (동적 기준값 그대로 사용).
                'relaxed_threshold': ml_threshold,
                'max_failures': 1
            },
            3: {  # 최고 완화 (고신뢰도 ML용)
                'critical_only': ['odd_even'],
                'skip_filters': ['consecutive', 'match', 'pattern', 'frequency', 'recent',
                               'multiple', 'ten_section', 'digit_sum', 'arithmetic_sequence'],
                # relaxed_threshold = ml_threshold x 0.5 (예: 기준값 0.3% 가정 시 0.15%).
                # 실제 값은 ThresholdManager의 동적 ml_relaxed_threshold에 비례.
                'relaxed_threshold': ml_threshold * 0.5,
                'max_failures': 0
            }
        }

        strategy = filter_strategies.get(relaxation_level, filter_strategies[1])
        failed_filters = []

        # Level 3: 고신뢰도 ML 예측은 기본 통계 검증만 (적응형 필터 우회)
        if relaxation_level >= 3:
            sorted_nums = sorted(numbers)
            odd_count = sum(1 for n in sorted_nums if n % 2 == 1)
            num_sum = sum(sorted_nums)
            max_gap = max(sorted_nums[i+1] - sorted_nums[i] for i in range(5))

            # 극단적 경우만 차단
            basic_checks = []
            if odd_count == 0 or odd_count == 6:
                basic_checks.append(f"odd_even_extreme({odd_count})")
            if num_sum < 30 or num_sum > 230:
                basic_checks.append(f"sum_extreme({num_sum})")
            if max_gap > 30:
                basic_checks.append(f"gap_extreme({max_gap})")

            if not basic_checks:
                return True, {
                    "method": "ml_basic_validation",
                    "relaxation_level": 3,
                    "odd_count": odd_count,
                    "sum": num_sum
                }
            else:
                failed_filters.extend(basic_checks)
                return False, {
                    "method": "ml_basic_validation",
                    "failed": basic_checks
                }

        # Level 1-2: AdaptiveProbabilityFilter 처리 (완화된 임계값)
        if hasattr(filter_manager, 'probability_threshold'):
            from src.core.threshold_manager import get_threshold_manager
            threshold_manager = get_threshold_manager()
            original_threshold = getattr(filter_manager, 'probability_threshold',
                                        threshold_manager.get_threshold())
            filter_manager.probability_threshold = strategy['relaxed_threshold']

            try:
                numbers_str = ','.join(map(str, sorted(numbers)))
                # WeightedFilterSystem은 apply() 없음 → filter_by_score_threshold() 사용
                # IntegratedFilterManager는 apply_all_filters() 사용
                last_round = db_manager.get_last_round()
                if hasattr(filter_manager, 'filter_by_score_threshold'):
                    filtered_result = filter_manager.filter_by_score_threshold(
                        [numbers_str], round_num=last_round)
                elif hasattr(filter_manager, 'apply_all_filters'):
                    filtered_result = filter_manager.apply_all_filters([numbers_str], last_round)
                else:
                    # 알 수 없는 타입: 통과 처리
                    filtered_result = [numbers_str]

                if filtered_result:
                    return True, {
                        "method": "adaptive_filter",
                        "threshold": strategy['relaxed_threshold'],
                        "relaxation_level": relaxation_level
                    }
                else:
                    failed_filters.append("adaptive_probability")
            finally:
                filter_manager.probability_threshold = original_threshold

        # 개별 필터 검사 (기존 시스템)
        elif hasattr(filter_manager, 'filters'):
            filters_to_check = []

            if isinstance(filter_manager.filters, dict):
                filters_to_check = filter_manager.filters.items()
            elif isinstance(filter_manager.filters, list):
                filters_to_check = enumerate(filter_manager.filters)

            for filter_name, filter_obj in filters_to_check:
                # 건너뛸 필터 확인
                if filter_name in strategy['skip_filters']:
                    continue

                # 필터 적용
                try:
                    if hasattr(filter_obj, 'apply'):
                        numbers_str = ','.join(map(str, sorted(numbers)))
                        result = filter_obj.apply([numbers_str], db_manager.get_last_round())

                        if not result:  # 필터 실패
                            failed_filters.append(filter_name)

                            # 중요 필터는 반드시 통과해야 함
                            if filter_name in strategy['critical_only']:
                                # 홀짝 필터는 극단적 경우만 차단 (모두 홀수 or 모두 짝수)
                                if filter_name == 'odd_even':
                                    odd_count = sum(1 for n in numbers if n % 2 == 1)
                                    if odd_count == 0 or odd_count == 6:
                                        return False, {
                                            "method": "individual_filters",
                                            "critical_failed": filter_name,
                                            "odd_count": odd_count
                                        }
                                else:
                                    return False, {
                                        "method": "individual_filters",
                                        "critical_failed": filter_name
                                    }
                except Exception as e:
                    logging.debug(f"필터 {filter_name} 적용 중 오류: {str(e)}")
                    failed_filters.append(f"{filter_name}_error")

        # 실패한 필터 수 확인
        if len(failed_filters) <= strategy['max_failures']:
            return True, {
                "method": "relaxed_filtering",
                "failed_filters": failed_filters,
                "relaxation_level": relaxation_level,
                "max_allowed_failures": strategy['max_failures']
            }
        else:
            return False, {
                "method": "too_many_failures",
                "failed_filters": failed_filters,
                "failure_count": len(failed_filters),
                "max_allowed": strategy['max_failures']
            }

    except Exception as e:
        logging.error(f"하이브리드 필터링 오류: {str(e)}")
        return False, {"error": str(e)}


def _adjust_ml_prediction_enhanced(failed_numbers, filtered_combos, max_changes=2):
    """
    개선된 ML 예측 조정 알고리즘 - 빈도 기반 지능형 수정

    Args:
        failed_numbers: 실패한 ML 예측 번호
        filtered_combos: 필터링된 조합들
        max_changes: 최대 변경 가능한 번호 수

    Returns:
        List[int] or None: 조정된 번호 조합
    """
    if not failed_numbers or len(failed_numbers) != 6:
        return None

    try:
        # 필터링된 조합들에서 번호별 빈도 분석
        number_frequency = {}
        for combo_str in filtered_combos[:5000]:  # 최대 5K개 분석
            try:
                numbers = [int(x) for x in combo_str.split(',')]
                for num in numbers:
                    number_frequency[num] = number_frequency.get(num, 0) + 1
            except (ValueError, IndexError):
                continue

        if not number_frequency:
            return None

        # 빈도 기준으로 정렬 (높은 빈도 순)
        frequent_numbers = sorted(number_frequency.items(), key=lambda x: x[1], reverse=True)

        # 현재 실패한 번호들의 빈도 확인
        failed_set = set(failed_numbers)
        low_freq_numbers = []

        for num in failed_numbers:
            freq = number_frequency.get(num, 0)
            avg_freq = sum(number_frequency.values()) / len(number_frequency)

            # 평균의 30% 미만이면 저빈도로 분류
            if freq < avg_freq * 0.3:
                low_freq_numbers.append((num, freq))

        if not low_freq_numbers:
            return None

        # 저빈도 번호를 고빈도 번호로 교체 (최대 max_changes개)
        adjusted = list(failed_numbers)
        changes_made = 0

        # 저빈도 번호들을 빈도 순으로 정렬 (가장 낮은 빈도부터)
        low_freq_numbers.sort(key=lambda x: x[1])

        for low_num, _ in low_freq_numbers:
            if changes_made >= max_changes:
                break

            # 아직 사용하지 않은 고빈도 번호 찾기
            for high_num, high_freq in frequent_numbers:
                if high_num not in adjusted:
                    # 번호 교체
                    idx = adjusted.index(low_num)
                    adjusted[idx] = high_num
                    changes_made += 1
                    logging.debug(f"번호 교체: {low_num} → {high_num} (빈도: {high_freq})")
                    break

        # 조정된 결과 검증
        if (len(set(adjusted)) == 6 and
            all(1 <= n <= 45 for n in adjusted) and
            changes_made > 0 and
            set(adjusted) != failed_set):
            return sorted(adjusted)

        return None

    except Exception as e:
        logging.error(f"개선된 ML 예측 조정 실패: {str(e)}")
        return None


def _find_enhanced_similar_combinations(target_numbers, filtered_combos, top_n=10):
    """
    개선된 유사 조합 찾기 알고리즘 - 가중치 기반 유사도 계산

    Args:
        target_numbers: 목표 번호 조합
        filtered_combos: 필터링된 조합들
        top_n: 상위 N개 반환

    Returns:
        List[dict]: 유사도 순으로 정렬된 조합들
    """
    if not filtered_combos or not target_numbers:
        return []

    target_set = set(target_numbers)
    similar_combos = []

    # 동적 검색 범위: 풀 크기의 최소 10% ~ 최대 50K개 (기존 고정 10K → 최대 5배 확장)
    search_limit = min(max(len(filtered_combos) // 10, 10000), 50000)
    for combo_str in filtered_combos[:search_limit]:  # 동적 범위 검색
        try:
            combo_numbers = [int(x) for x in combo_str.split(',')]
            combo_set = set(combo_numbers)

            # 다차원 유사도 계산
            # 1. 공통 번호 비율 (가중치 40%)
            common_count = len(target_set & combo_set)
            common_ratio = common_count / 6

            # 2. 번호 범위 유사성 (가중치 20%)
            target_range = max(target_numbers) - min(target_numbers)
            combo_range = max(combo_numbers) - min(combo_numbers)
            range_similarity = 1 - abs(target_range - combo_range) / 44  # 0~1

            # 3. 합계 유사성 (가중치 20%)
            target_sum = sum(target_numbers)
            combo_sum = sum(combo_numbers)
            max_diff = abs(target_sum - combo_sum)
            sum_similarity = 1 - min(max_diff / 135, 1)  # 최대 차이 135 기준

            # 4. 패턴 유사성 (가중치 20%)
            # 홀짝 패턴
            target_odd = sum(1 for n in target_numbers if n % 2 == 1)
            combo_odd = sum(1 for n in combo_numbers if n % 2 == 1)
            odd_similarity = 1 - abs(target_odd - combo_odd) / 6

            # 종합 유사도 계산
            similarity = (
                common_ratio * 0.4 +
                range_similarity * 0.2 +
                sum_similarity * 0.2 +
                odd_similarity * 0.2
            )

            # 보너스: 인접 번호가 많으면 추가 점수
            adjacent_bonus = 0
            for target_num in target_numbers:
                if any(abs(target_num - combo_num) == 1 for combo_num in combo_numbers):
                    adjacent_bonus += 0.02

            similarity += adjacent_bonus
            similarity = min(similarity, 1.0)  # 최대값 1.0 제한

            if similarity > 0.3:  # 최소 30% 유사도 이상만 고려
                similar_combos.append({
                    'numbers': combo_numbers,
                    'similarity': similarity,
                    'common_count': common_count,
                    'details': {
                        'common_ratio': common_ratio,
                        'range_similarity': range_similarity,
                        'sum_similarity': sum_similarity,
                        'pattern_similarity': odd_similarity,
                        'adjacent_bonus': adjacent_bonus
                    }
                })

        except (ValueError, IndexError):
            continue

    # 유사도 순으로 정렬
    similar_combos.sort(key=lambda x: x['similarity'], reverse=True)
    return similar_combos[:top_n]


if __name__ == "__main__":
    main()