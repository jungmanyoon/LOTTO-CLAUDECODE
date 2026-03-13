#!/usr/bin/env python3
"""
최적화된 백테스팅 프레임워크
- 모델 캐싱으로 재학습 방지
- 병렬 처리로 속도 향상
- 프랙탈 분석 최적화
"""
import logging
import gc  # Phase 2.5: 명시적 가비지 컬렉션
import sys

# Windows 백그라운드 스레드 tqdm 호환성: sys.stderr를 안전한 래퍼로 교체
class _SafeStderr:
    """Windows 백그라운드 스레드에서 sys.stderr.flush() 오류 방지 래퍼"""
    def write(self, s):
        try:
            sys.stdout.write(s)
        except Exception:
            pass
    def flush(self):
        try:
            sys.stdout.flush()
        except Exception:
            pass
    def isatty(self):
        return False
    def fileno(self):
        import io
        raise io.UnsupportedOperation("fileno")
    def encoding(self):
        return 'utf-8'

# tqdm 4.66+은 file=sys.stdout이어도 status_printer에서 sys.stderr.flush()를 항상 호출함
# sys.stderr를 SafeStderr로 교체
sys.stderr = _SafeStderr()

# tqdm status_printer monkey-patch: sys.stderr/stdout.flush() 오류를 안전하게 처리
# tqdm 4.66+은 file=sys.stdout이어도 status_printer에서 sys.stderr.flush()를 항상 호출하므로 패치 필요
try:
    from tqdm.std import tqdm as _tqdm_cls
    from tqdm.std import disp_len as _tqdm_disp_len  # 삭제하지 않는 이름으로 저장

    @staticmethod
    def _safe_status_printer(file):
        from tqdm.std import disp_len  # 함수 내부에서 직접 임포트 (클로저 참조 문제 방지)
        fp = file
        fp_flush = getattr(fp, 'flush', lambda: None)
        if fp in (sys.stderr, sys.stdout):
            try:
                getattr(sys.stderr, 'flush', lambda: None)()
            except (OSError, ValueError, AttributeError):
                pass
            try:
                getattr(sys.stdout, 'flush', lambda: None)()
            except (OSError, ValueError, AttributeError):
                pass

        def fp_write(s):
            try:
                fp.write(str(s))
                fp_flush()
            except (OSError, ValueError, AttributeError):
                pass

        last_len = [0]

        def print_status(s):
            try:
                len_s = disp_len(s)
                fp_write('\r' + s + (' ' * max(last_len[0] - len_s, 0)))
                last_len[0] = len_s
            except (OSError, ValueError, AttributeError):
                pass

        return print_status

    _tqdm_cls.status_printer = _safe_status_printer
    del _tqdm_cls, _tqdm_disp_len
except Exception:
    pass  # monkey-patch 실패 시 무시

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
from datetime import datetime
import json
from tqdm import tqdm
import os
import hashlib
import copy  # 버그 수정: deep copy 추가
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing as mp
import pickle
from functools import lru_cache
import threading  # Thread safety for predictor training

# ENSEMBLE 모니터링 추가
try:
    from src.monitoring.ensemble_monitor import get_ensemble_monitor
    ENSEMBLE_MONITOR_AVAILABLE = True
except ImportError:
    ENSEMBLE_MONITOR_AVAILABLE = False
    logging.warning("ENSEMBLE 모니터링 모듈을 찾을 수 없습니다. 모니터링 없이 진행합니다.")
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')

from ..core.db_manager import DatabaseManager
from ..core.filter_manager import FilterManager
from ..core.filter_validator import FilterValidator
from ..ml.lstm_predictor import LSTMPredictor
from ..ml.ensemble_predictor import EnsemblePredictor
from ..probabilistic.monte_carlo_simulator import MonteCarloSimulator
from ..probabilistic.bayesian_inference import BayesianFilter as BayesianInference
from ..advanced.fractal_pattern_analyzer import FractalPatternAnalyzer
from ..utils.singleton import SingletonMeta
from ..utils.counter_manager import get_counter_manager
from ..core.performance_stats_manager import PerformanceStatsManager



class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)


class ModelCache:
    """모델 캐싱 시스템"""
    def __init__(self):
        self.cache = {}
        self.cache_dir = "cache/models"
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # results 디렉토리도 생성
        os.makedirs("results", exist_ok=True)
    
    def get_data_hash(self, data: List[List[int]]) -> str:
        """데이터의 해시값 생성"""
        data_str = str(sorted([tuple(d) for d in data]))
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def get_cached_model(self, model_type: str, data_hash: str) -> Optional[Any]:
        """캐시된 모델 반환"""
        cache_key = f"{model_type}_{data_hash}"
        
        # 메모리 캐시 확인
        if cache_key in self.cache:
            logging.debug(f"메모리 캐시에서 {model_type} 모델 로드")
            return self.cache[cache_key]
        
        # 디스크 캐시 확인
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    model = pickle.load(f)
                self.cache[cache_key] = model
                logging.debug(f"디스크 캐시에서 {model_type} 모델 로드")
                return model
            except (ImportError, OSError) as e:
                logging.debug(f"캐시 디렉토리 생성 실패 (무시): {e}")

        return None
    
    def save_model(self, model_type: str, data_hash: str, model: Any):
        """모델을 캐시에 저장"""
        cache_key = f"{model_type}_{data_hash}"
        
        # 메모리 캐시 저장
        self.cache[cache_key] = model
        
        # 디스크 캐시 저장 - ensemble 모델의 경우 특별 처리
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        try:
            # Ensemble 모델의 경우 scaler 상태 확인 (targets scaler는 사용하지 않음)
            if model_type == 'ensemble' and hasattr(model, 'scalers'):
                # targets scaler는 제거
                if 'targets' in model.scalers:
                    del model.scalers['targets']
                
                # features scaler만 확인
                for scaler_name, scaler in model.scalers.items():
                    if scaler_name == 'features':  # features scaler만 체크
                        if hasattr(scaler, 'mean_') and scaler.mean_ is not None:
                            logging.debug(f"Ensemble {scaler_name} scaler는 fit된 상태입니다.")
                        else:
                            logging.warning(f"Ensemble {scaler_name} scaler가 fit되지 않은 상태입니다.")
            
            with open(cache_file, 'wb') as f:
                pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
            logging.debug(f"{model_type} 모델 캐시 저장 완료")
        except Exception as e:
            logging.warning(f"모델 디스크 캐시 저장 실패: {e}")


class OptimizedBacktestingFramework(metaclass=SingletonMeta):
    """최적화된 백테스팅 프레임워크 (싱글톤)"""

    @classmethod
    def get_instance(cls):
        """싱글톤 인스턴스 반환 (존재하지 않으면 None)"""
        return getattr(cls, '_instances', {}).get(cls, None)

    def __init__(self, db_manager=None, enable_fractal=False, config=None):
        """
        Args:
            db_manager: 데이터베이스 관리자
            enable_fractal: 프랙탈 분석 활성화 여부 (기본: False)
            config: 설정 딕셔너리 (백테스팅 설정 포함)
        """
        # 이미 초기화되었는지 확인
        if hasattr(self, '_initialized'):
            return

        self.db_manager = db_manager or DatabaseManager()

        # ✅ FIX: 백테스팅 설정 로드
        self.config = config or {}
        backtesting_config = self.config.get('backtesting', {})
        self.validation_window = backtesting_config.get('validation_window', 300)  # 51 → 300
        self.training_window = backtesting_config.get('training_window', 150)
        self.min_confidence_level = backtesting_config.get('min_confidence_level', 0.95)
        logging.info(f"[백테스팅] 검증 윈도우: {self.validation_window} 회차 (훈련: {self.training_window} 회차)")
        
        # WeightedFilterSystem 사용 (1% 임계값 적용)
        try:
            from ..core.weighted_filter_system import WeightedFilterSystem
            base_filter_manager = FilterManager(self.db_manager)
            self.filter_manager = WeightedFilterSystem(base_filter_manager)
            # 1% 임계값을 위해 30점으로 설정
            self.filter_manager.pass_threshold = 30.0
            logging.info(f"[백테스팅] WeightedFilterSystem 활성화 (임계값: {self.filter_manager.pass_threshold}점)")
        except ImportError:
            # WeightedFilterSystem이 없으면 기본 FilterManager 사용
            self.filter_manager = FilterManager(self.db_manager)
            logging.warning("[백테스팅] WeightedFilterSystem을 찾을 수 없어 기본 FilterManager 사용")
        
        self.filter_validator = FilterValidator(self.filter_manager, self.db_manager)
        
        # ML/AI 모델 초기화
        self.lstm_predictor = LSTMPredictor()
        self.ensemble_predictor = EnsemblePredictor()
        self.monte_carlo = MonteCarloSimulator(db_manager)
        self.bayesian_filter = BayesianInference(db_manager)

        # Thread safety locks for concurrent predictor training
        self._lstm_training_lock = threading.Lock()
        self._ensemble_training_lock = threading.Lock()

        # 프랙탈 분석은 선택적으로만 활성화
        self.enable_fractal = enable_fractal
        if enable_fractal:
            self.fractal_analyzer = FractalPatternAnalyzer(db_manager)

        # 캐싱 시스템
        self.model_cache = ModelCache()
        self.prediction_cache = {}
        self.processed_rounds = set()  # 중복 체크용 세트 추가
        
        # 병렬 처리 설정 (CPU 사용률 최적화)
        # 최대 8코어로 제한하여 CPU 사용률을 낮춤
        # Guarantee minimum 1 worker to prevent crashes on single-core systems
        self.n_jobs = max(1, min(8, mp.cpu_count() - 1))
        
        # 카운터 매니저
        self.counter_manager = get_counter_manager()

        # 성능 통계 매니저
        self.performance_stats_manager = PerformanceStatsManager()

        # Jackpot tracking for systematic contamination detection
        self._jackpot_count = 0
        self._jackpot_threshold = 2  # Flag systematic contamination after 2+ jackpots

        # 전역 종료 플래그 (외부에서 설정하여 백테스팅 조기 중단)
        self._shutdown_flag = None  # dict 참조: {'stop': True/False}

        self._initialized = True
        logging.info(f"최적화된 백테스팅 프레임워크 초기화 완료 (싱글톤, 병렬 처리: {self.n_jobs} 코어)")

        # 상태 파일 경로
        self.state_file = "data/backtest_state.json"
        self._state_save_lock = threading.Lock()  # save_state 멀티스레드 경합 방지

    def set_shutdown_flag(self, flag: dict):
        """외부 종료 플래그 설정 (예: optimization_stop_flag)"""
        self._shutdown_flag = flag

    def _is_shutting_down(self) -> bool:
        """종료 플래그 확인"""
        if self._shutdown_flag and self._shutdown_flag.get('stop', False):
            return True
        return False

    def save_state(self, state: Dict[str, Any]):
        """백테스팅 상태 저장 (스레드 락으로 동시 접근 방지)"""
        with self._state_save_lock:
            try:
                os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                tmp_file = self.state_file + '.tmp'
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
                for attempt in range(3):
                    try:
                        os.replace(tmp_file, self.state_file)
                        break
                    except OSError:
                        if attempt < 2:
                            import time
                            time.sleep(0.1)
                        else:
                            raise
            except Exception as e:
                logging.error(f"백테스팅 상태 저장 실패: {e}")

    def load_state(self) -> Optional[Dict[str, Any]]:
        """백테스팅 상태 로드"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # 다른 프로세스가 쓰는 중일 수 있으므로 삭제하지 않고 None 반환
                logging.debug(f"백테스팅 상태 파일 읽기 실패 (쓰기 중 충돌 가능). 새로 시작합니다: {self.state_file}")
                return None
            except Exception as e:
                logging.error(f"백테스팅 상태 로드 실패: {e}")
        return None

    def clear_state(self):
        """백테스팅 상태 삭제"""
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
                logging.info("백테스팅 상태 파일이 삭제되었습니다.")
            except Exception as e:
                logging.error(f"백테스팅 상태 삭제 실패: {e}")

        # LSTM/Ensemble is_trained 플래그 초기화
        # 이유: 싱글톤 재사용 시 이전 trial에서 학습된 모델이 다음 trial에서 재사용되는 것을 방지
        # 각 trial의 각 test_round는 고유한 train_data로 모델을 학습해야 함
        if hasattr(self, 'lstm_predictor') and self.lstm_predictor is not None:
            self.lstm_predictor.is_trained = False
            logging.debug("[캐시 초기화] lstm_predictor.is_trained 초기화 완료")

        if hasattr(self, 'ensemble_predictor') and self.ensemble_predictor is not None:
            self.ensemble_predictor.is_trained = False
            logging.debug("[캐시 초기화] ensemble_predictor.is_trained 초기화 완료")

    def update_parameters(self, threshold: float = None, ml_bypass: int = None, ml_weight: float = None):
        """
        백테스팅 파라미터 업데이트 (재초기화 없이)

        Args:
            threshold: 확률 임계값
            ml_bypass: ML bypass 필터 수
            ml_weight: ML 가중치
        """
        # filter_manager 업데이트
        if hasattr(self.filter_manager, 'update_config'):
            self.filter_manager.update_config(
                probability_threshold=threshold,
                ml_bypass_filters=ml_bypass,
                ml_weight=ml_weight
            )
        elif hasattr(self.filter_manager, 'probability_threshold'):
            # IntegratedFilterManager가 아닌 경우
            if threshold is not None:
                self.filter_manager.probability_threshold = threshold
            if ml_bypass is not None:
                self.filter_manager.ml_bypass_filters = ml_bypass
            if ml_weight is not None:
                self.filter_manager.ml_weight = ml_weight

        # framework 자체 속성 업데이트
        if ml_bypass is not None:
            self.ml_bypass_filters = ml_bypass
        if ml_weight is not None:
            self.ml_weight = ml_weight

        # ============================================================
        # 🚀 PERFORMANCE OPTIMIZATION: 캐시만 초기화 (패턴 재분석 없음)
        # ============================================================
        if hasattr(self, 'prediction_cache'):
            self.prediction_cache.clear()
            logging.debug("[캐시 초기화] prediction_cache 초기화 완료")

        if hasattr(self, 'processed_rounds'):
            self.processed_rounds.clear()
            logging.debug("[캐시 초기화] processed_rounds 초기화 완료")

        # 파라미터 변경 시에도 모델 is_trained 초기화 (다음 백테스팅에서 새 데이터로 재훈련)
        if hasattr(self, 'lstm_predictor') and self.lstm_predictor is not None:
            self.lstm_predictor.is_trained = False
        if hasattr(self, 'ensemble_predictor') and self.ensemble_predictor is not None:
            self.ensemble_predictor.is_trained = False

        # Phase 2.5: 캐시 초기화 후 명시적 가비지 컬렉션
        gc.collect()

        # ============================================================
        # 🔧 FIX: 파라미터 변경 시 백테스팅 상태 파일 삭제
        # 이유: 파라미터가 다르면 이전 캐시된 결과 사용 불가
        # ============================================================
        if hasattr(self, 'state_file') and os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
                logging.info(f"[상태 초기화] 백테스팅 상태 파일 삭제: {self.state_file}")
            except Exception as e:
                logging.warning(f"[상태 초기화] 상태 파일 삭제 실패: {e}")

        logging.info(f"[파라미터 업데이트] threshold={threshold}, ml_bypass={ml_bypass}, ml_weight={ml_weight}")

    def run_backtest(self, start_round: int, end_round: int, window_size: int = 100) -> Dict[str, Any]:
        """최적화된 백테스팅 실행"""
        # tqdm 4.66+이 sys.stderr.flush()를 항상 호출하므로 스레드 실행 시마다 안전화
        if not isinstance(sys.stderr, _SafeStderr):
            sys.stderr = _SafeStderr()
        logging.debug(f"\n최적화된 백테스팅 시작: {start_round}회차 ~ {end_round}회차")
        logging.info(f"학습 윈도우 크기: {window_size}회차")
        
        # 카운터 초기화
        self.counter_manager.reset_all()
        
        results = {
            'start_round': start_round,
            'end_round': end_round,
            'window_size': window_size,
            'predictions': [],
            'performance_metrics': {}
        }

        # 상태 로드 및 재개 확인
        saved_state = self.load_state()
        if saved_state:
            # 설정이 동일한지 확인 (start_round와 window_size가 같으면 재개 가능)
            if (saved_state['start_round'] == start_round and 
                saved_state['window_size'] == window_size):
                
                last_processed = saved_state.get('last_processed_round', start_round - 1)
                if last_processed >= start_round:
                    logging.info(f"\n[RESUME] 이전 백테스팅 상태를 발견했습니다. {last_processed + 1}회차부터 재개합니다.")
                    
                    # 이전 결과 복원
                    results['predictions'] = saved_state.get('predictions', [])
                    
                    # 시작 회차 조정
                    start_round = last_processed + 1
                    
                    if start_round > end_round:
                        logging.info("이미 모든 회차가 완료되었습니다.")
                        return results
            else:
                logging.info("[RESET] 설정이 변경되어 새로운 백테스팅을 시작합니다.")
                self.clear_state()
        
        # 전체 당첨번호 데이터 가져오기 (보너스 번호 포함)
        all_numbers_with_bonus = self.db_manager.get_numbers_with_bonus()
        winning_numbers_dict = {}
        bonus_numbers_dict = {}
        
        for round_num, numbers_tuple in all_numbers_with_bonus:
            # numbers_tuple: (n1, n2, n3, n4, n5, n6, bonus)
            winning_numbers_dict[round_num] = list(numbers_tuple[:6])
            bonus_numbers_dict[round_num] = numbers_tuple[6] if len(numbers_tuple) > 6 else None
        
        # 백테스팅 수행 - 배치 처리
        test_rounds = list(range(start_round, end_round + 1))
        batch_size = min(10, len(test_rounds))  # 10회차씩 배치 처리
        
        for i in range(0, len(test_rounds), batch_size):
            # 종료 플래그 확인 - 배치 시작 전 조기 중단
            if self._is_shutting_down():
                logging.info("[SHUTDOWN] 종료 플래그 감지 - 백테스팅 조기 중단")
                break

            batch_rounds = test_rounds[i:i+batch_size]

            # 병렬 예측 수행
            with ThreadPoolExecutor(max_workers=self.n_jobs) as executor:
                futures = []
                for test_round in batch_rounds:
                    train_start = max(1, test_round - window_size)
                    train_end = test_round - 1
                    
                    # 최소 10개의 데이터가 있는지 확인
                    if train_end - train_start + 1 < 10:
                        # 최소 10개 데이터를 확보하기 위해 train_start 조정
                        train_start = max(1, train_end - 9)
                    
                    # 여전히 데이터가 부족하면 이 라운드는 건너뛰기
                    if train_end - train_start + 1 < 10:
                        logging.debug(f"라운드 {test_round}: 학습 데이터 부족 ({train_end - train_start + 1}개)")
                        continue
                    
                    try:
                        future = executor.submit(
                            self._predict_for_round_optimized,
                            test_round, train_start, train_end, winning_numbers_dict, bonus_numbers_dict
                        )
                        futures.append((test_round, future))
                    except RuntimeError as e:
                        # 인터프리터 종료 중 future 스케줄 불가 시 무시
                        logging.debug(f"라운드 {test_round} future 스케줄 실패 (종료 중): {e}")
                        break
                
                # 결과 수집: tqdm은 항상 disable=True (status_printer가 sys.stderr를 직접 flush하므로 Windows 백그라운드 스레드 오류 방지)
                _futures_iter = iter(futures)
                for test_round, future in _futures_iter:
                    prediction_result = future.result()

                    # 카운터 증가
                    self.counter_manager.increment('total_rounds')

                    # 실제 당첨번호와 비교 (보너스 번호 포함)
                    if test_round in winning_numbers_dict:
                        actual_numbers = winning_numbers_dict[test_round]
                        bonus_number = bonus_numbers_dict.get(test_round)
                        prediction_result['actual_numbers'] = actual_numbers
                        prediction_result['bonus_number'] = bonus_number
                        prediction_result['matches'] = self._calculate_matches(
                            prediction_result.get('predictions', {}), actual_numbers, bonus_number
                        )

                        # 결과 저장
                        for model_name in prediction_result.get('predictions', {}).keys():
                            self.counter_manager.set_round_result(
                                test_round, model_name, prediction_result['matches'].get(model_name, {})
                            )
                    else:
                        # 당첨번호가 없는 경우에도 빈 matches 필드 보장
                        prediction_result['matches'] = {}

                    results['predictions'].append(prediction_result)
            
            # 배치 완료 후 상태 저장
            current_state = {
                'start_round': results['start_round'],
                'end_round': results['end_round'],
                'window_size': results['window_size'],
                'last_processed_round': batch_rounds[-1],
                'predictions': results['predictions'],
                'timestamp': datetime.now().isoformat()
            }
            self.save_state(current_state)

        # 성능 지표 계산
        results['performance_metrics'] = self._calculate_performance_metrics(results['predictions'])
        
        # 결과 저장
        self._save_backtest_results(results)  # JSON 파일 저장
        self._save_to_database(results)       # DB 저장 (BUG FIX: 누락된 호출 추가)
        self._print_backtest_summary(results)
        
        return results

    def _predict_for_round_optimized(self, round_num: int, train_start: int, train_end: int,
                                   winning_numbers_dict: Dict[int, List[int]],
                                   bonus_numbers_dict: Dict[int, Optional[int]]) -> Dict[str, Any]:
        """최적화된 회차별 예측"""
        # 종료 플래그 확인 - 라운드 시작 전 조기 중단
        if self._is_shutting_down():
            return {
                'round': round_num,
                'train_range': (train_start, train_end),
                'predictions': {'lstm': [], 'ensemble': [], 'monte_carlo': [], 'combined': []},
                'matches': {},
                'scores': {},
                'filter_validation': {},
                'filter_pass_rate': {},
                'shutdown': True
            }

        # 중복 체크
        if round_num in self.processed_rounds:
            logging.debug(f"이미 처리된 회차 건너뛰기: {round_num}")
            cache_key = f"{round_num}_{train_start}_{train_end}"
            if cache_key in self.prediction_cache:
                return self.prediction_cache[cache_key]
            else:
                # [FIX] 캐시 미스 시 빈 결과 대신 재생성 시도 (병렬 처리 중 정상 발생)
                logging.debug(f"캐시 미스 감지: 회차 {round_num}. 예측을 재생성합니다.")
                # 중복 처리 표시 제거 후 아래 코드로 진행하여 신규 예측 생성
                self.processed_rounds.remove(round_num)
                # 재귀 호출 대신 아래로 진행
        
        # 처리 완료 표시
        self.processed_rounds.add(round_num)
        
        # 캐시 확인
        cache_key = f"{round_num}_{train_start}_{train_end}"
        if cache_key in self.prediction_cache:
            logging.debug(f"캐시된 예측 사용: 회차 {round_num}")
            cached_result = self.prediction_cache[cache_key]

            # 🔧 CRITICAL FIX: 캐시된 결과에 대해서도 filter validation 재수행
            # (필터 설정이 변경될 수 있으므로 매번 다시 검증 필요)
            if 'predictions' in cached_result and cached_result['predictions']:
                self._validate_predictions_with_filter(cached_result, round_num)
                logging.debug(f"[CACHE FIX] 캐시된 결과에 filter_validation 재수행 완료: 회차 {round_num}")

            return cached_result
        
        result = {
            'round': round_num,
            'train_range': (train_start, train_end),
            'predictions': {},
            'scores': {},
            'filter_validation': {},  # 필터 검증 결과
            'filter_pass_rate': {}  # 모델별 필터 통과율
        }
        
        # 학습 데이터 준비
        train_data = [
            winning_numbers_dict[r] for r in range(train_start, train_end + 1)
            if r in winning_numbers_dict
        ]
        
        # 데이터 해시 생성
        data_hash = self.model_cache.get_data_hash(train_data)
        
        try:
            # 병렬로 각 모델 예측 수행
            with ThreadPoolExecutor(max_workers=3) as executor:
                try:
                    # LSTM 예측
                    lstm_future = executor.submit(
                        self._get_lstm_predictions_cached, train_data, data_hash
                    )

                    # Ensemble 예측
                    ensemble_future = executor.submit(
                        self._get_ensemble_predictions_cached, train_data, train_end, data_hash
                    )

                    # Monte Carlo 예측 (최적화됨)
                    mc_future = executor.submit(
                        self._get_monte_carlo_predictions_optimized, train_data
                    )
                except RuntimeError:
                    # 인터프리터 종료 중 future 스케줄 불가
                    logging.debug(f"회차 {round_num}: 인터프리터 종료 중 모델 예측 스킵")
                    result['matches'] = {}
                    return result
                
                # 결과 수집 (개별 에러 처리)
                try:
                    lstm_results = lstm_future.result()
                    result['predictions']['lstm'] = lstm_results[:5] if lstm_results else []
                except Exception as e:
                    logging.error(f"LSTM 예측 실패 (회차 {round_num}): {str(e)}")
                    result['predictions']['lstm'] = []
                
                try:
                    ensemble_results = ensemble_future.result()
                    result['predictions']['ensemble'] = ensemble_results[:5] if ensemble_results else []
                except Exception as e:
                    logging.error(f"Ensemble 예측 실패 (회차 {round_num}): {str(e)}")
                    result['predictions']['ensemble'] = []
                
                try:
                    mc_results = mc_future.result()
                    result['predictions']['monte_carlo'] = mc_results[:5] if mc_results else []
                except Exception as e:
                    logging.error(f"Monte Carlo 예측 실패 (회차 {round_num}): {str(e)}")
                    result['predictions']['monte_carlo'] = []
                
                # 통합 예측
                if any(result['predictions'].values()):
                    combined = self._combine_predictions(result['predictions'])
                    result['predictions']['combined'] = combined[:5]
                else:
                    result['predictions']['combined'] = []
                
                # 필터 검증 수행
                self._validate_predictions_with_filter(result, round_num)
        
        except Exception as e:
            logging.error(f"회차 {round_num} 예측 중 전체 오류: {str(e)}")
            result['error'] = str(e)
            # 기본값 설정
            result['predictions'] = {
                'lstm': [],
                'ensemble': [],
                'monte_carlo': [],
                'combined': []
            }
            result['matches'] = {}

        # matches 필드 보장 (캐싱 전)
        if 'matches' not in result:
            result['matches'] = {}

        # 결과 캐싱
        self.prediction_cache[cache_key] = result
        
        return result

    def _get_lstm_predictions_cached(self, train_data: List[List[int]], data_hash: str) -> List[List[int]]:
        """캐싱된 LSTM 예측"""
        try:
            # 캐시 확인
            cached_model = self.model_cache.get_cached_model('lstm', data_hash)

            if cached_model:
                self.lstm_predictor = cached_model
            else:
                # 모델 학습 (Thread-safe with double-check pattern)
                if not hasattr(self, 'lstm_predictor') or not self.lstm_predictor:
                    logging.warning("LSTM predictor가 초기화되지 않았습니다.")
                    return []

                # Double-check lock pattern: check before and after acquiring lock
                if not hasattr(self.lstm_predictor, 'is_trained') or not self.lstm_predictor.is_trained:
                    with self._lstm_training_lock:
                        # Check again after acquiring lock (another thread might have trained)
                        if not hasattr(self.lstm_predictor, 'is_trained') or not self.lstm_predictor.is_trained:
                            winning_numbers_str = [','.join(map(str, nums)) for nums in train_data]
                            if len(winning_numbers_str) >= 50:
                                logging.debug(f"[Thread {threading.current_thread().name}] Training LSTM model...")
                                self.lstm_predictor.train(winning_numbers_str, epochs=30, batch_size=32)
                                self.model_cache.save_model('lstm', data_hash, self.lstm_predictor)
                            else:
                                logging.warning(f"LSTM 학습 데이터 부족: {len(winning_numbers_str)}개")
                                return []
            
            # 예측 수행
            winning_numbers_str = [','.join(map(str, nums)) for nums in train_data]
            sequence_length = min(50, len(winning_numbers_str))
            recent_numbers = winning_numbers_str[-sequence_length:]
            
            predictions = self.lstm_predictor.predict_next_numbers(
                recent_numbers,
                num_predictions=10
            )
            
            # 결과 변환
            result = []
            for pred in predictions[:5]:
                if isinstance(pred, dict) and 'numbers' in pred:
                    numbers = pred['numbers']
                    # numbers가 리스트인지 확인
                    if isinstance(numbers, list):
                        result.append(numbers)
                    elif isinstance(numbers, str):
                        # 문자열인 경우 파싱
                        result.append([int(n) for n in numbers.split(',')])
                    elif isinstance(numbers, (int, np.integer)):
                        # 단일 정수인 경우 건너뛰기
                        logging.warning(f"LSTM 예측이 단일 정수로 반환됨: {numbers}")
                        continue
            
            return result
            
        except Exception as e:
            logging.error(f"LSTM 예측 중 오류: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return []
    
    def _get_ensemble_predictions_cached(self, train_data: List[List[int]], 
                                       current_round: int, data_hash: str) -> List[List[int]]:
        """캐싱된 앙상블 예측"""
        try:
            # 캐시 확인
            cached_model = self.model_cache.get_cached_model('ensemble', data_hash)
            
            if cached_model:
                self.ensemble_predictor = cached_model
                # 캐시된 모델의 scaler 상태 확인
                if not hasattr(self.ensemble_predictor.scalers['features'], 'mean_'):
                    logging.warning("캐시된 ensemble 모델의 scaler가 손상됨. 재학습 필요.")
                    cached_model = None  # 재학습 강제

            if not cached_model:
                # 모델 학습 (Thread-safe with double-check pattern)
                if not hasattr(self, 'ensemble_predictor') or not self.ensemble_predictor:
                    logging.warning("Ensemble predictor가 초기화되지 않았습니다.")
                    return []

                # Double-check lock pattern: check before and after acquiring lock
                if not hasattr(self.ensemble_predictor, 'is_trained') or not self.ensemble_predictor.is_trained:
                    with self._ensemble_training_lock:
                        # Check again after acquiring lock (another thread might have trained)
                        if not hasattr(self.ensemble_predictor, 'is_trained') or not self.ensemble_predictor.is_trained:
                            logging.debug(f"[Thread {threading.current_thread().name}] Training Ensemble model...")
                            winning_numbers_data = [','.join(map(str, numbers)) for numbers in train_data]
                            self.ensemble_predictor.train(winning_numbers_data)
                            self.model_cache.save_model('ensemble', data_hash, self.ensemble_predictor)
            
            # 예측 수행
            winning_numbers_data = [','.join(map(str, numbers)) for numbers in train_data]
            predictions = self.ensemble_predictor.predict_next_numbers(
                winning_numbers_data,
                num_predictions=10
            )
            
            # 결과 변환 (안전한 방식)
            result = []
            for pred in predictions[:5]:
                if isinstance(pred, dict) and 'numbers' in pred:
                    numbers = pred['numbers']
                    if isinstance(numbers, list):
                        result.append(numbers)
                    elif isinstance(numbers, str):
                        result.append([int(n) for n in numbers.split(',')])
                elif isinstance(pred, list):
                    result.append(pred)
            
            return result
            
        except Exception as e:
            logging.error(f"Ensemble 예측 중 오류: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return []
    
    def _get_monte_carlo_predictions_optimized(self, train_data: List[List[int]]) -> List[List[int]]:
        """최적화된 Monte Carlo 예측"""
        try:
            # 빈도 분석 (벡터화)
            all_numbers = np.concatenate(train_data)
            unique, counts = np.unique(all_numbers, return_counts=True)
            number_freq = np.zeros(45)
            number_freq[unique - 1] = counts
            
            # 확률 계산
            probs = number_freq / number_freq.sum()
            
            # 병렬 시뮬레이션 (벡터화)
            n_simulations = 2000  # 10000에서 2000으로 감소
            predictions = np.zeros((n_simulations, 6), dtype=int)
            
            # 배치 시뮬레이션
            for i in range(0, n_simulations, 100):
                batch_size = min(100, n_simulations - i)
                for j in range(batch_size):
                    predictions[i+j] = np.sort(np.random.choice(45, 6, replace=False, p=probs) + 1)
            
            # 가장 빈번한 조합 찾기 (해시 기반)
            combo_counts = {}
            for pred in predictions:
                key = tuple(pred)
                combo_counts[key] = combo_counts.get(key, 0) + 1
            
            # 상위 5개 반환
            top_combos = sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            return [list(combo) for combo, _ in top_combos]
            
        except Exception as e:
            logging.error(f"Monte Carlo 예측 중 오류: {str(e)}")
            return []
    
    def _combine_predictions(self, all_predictions: Dict[str, List[List[int]]]) -> List[List[int]]:
        """여러 모델의 예측을 통합"""
        combined = []
        
        # 각 모델의 최상위 예측 수집
        for model_name, predictions in all_predictions.items():
            if predictions:
                combined.extend(predictions[:2])  # 각 모델에서 2개씩
        
        # 중복 제거
        unique_combined = []
        seen = set()
        for pred in combined:
            pred_tuple = tuple(pred)
            if pred_tuple not in seen:
                seen.add(pred_tuple)
                unique_combined.append(pred)
        
        return unique_combined[:5]
    
    def _round_has_db_pool(self, round_num: int) -> bool:
        """Check if filtered pool exists for this round in database

        Returns:
            bool: True if DB pool data exists for this round, False otherwise
        """
        try:
            db_manager = DatabaseManager()
            filter_db = db_manager.combinations_db

            with filter_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM filtered_combinations WHERE round = ? LIMIT 1",
                    (round_num,)
                )
                result = cursor.fetchone()
                count = result[0] if result else 0
                return count > 0
        except Exception as e:
            logging.debug(f"DB pool check error: {e}")
            return False

    def _check_prediction_in_filtered_pool(self, prediction: List[int], round_num: int) -> bool:
        """Check if prediction exists in pre-computed filtered pool from database
        
        This is different from filter validation:
        - Filter validation: Checks if prediction passes current filter criteria (runtime)
        - Pool inclusion: Checks if prediction exists in pre-filtered pool (database)
        
        The pool may be outdated or use different threshold values.
        """
        try:
            # DB pool 없으면 filter_validator 폴백 사용 (validator 없으면 패널티 없음)
            if not self._round_has_db_pool(round_num):
                logging.debug(f"Round {round_num} has no DB pool data - using filter validator")
                if hasattr(self, 'filter_validator') and self.filter_validator:
                    try:
                        result = self.filter_validator.validate_winning_numbers(round_num, prediction)
                        return result.get('passed_all_filters', True)
                    except Exception as ve:
                        logging.debug(f"Filter validator error: {ve}")
                        return False
                return True  # validator 없으면 패널티 없음

            # Convert prediction to string format for database lookup
            pred_str = ','.join(map(str, sorted(prediction)))

            # Use DatabaseManager singleton for canonical filtered pool access
            db_manager = DatabaseManager()
            filter_db = db_manager.combinations_db  # Use persisted combinations database

            # Check if combination exists in filtered pool for this round
            with filter_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM filtered_combinations WHERE round = ? AND combination = ?",
                    (round_num, pred_str)
                )
                result = cursor.fetchone()
                exists = result[0] > 0 if result else False

            return exists

        except Exception as e:
            logging.debug(f"Pool check error (falling back to filter validation): {e}")
            # Fallback: filter_validator 사용, validator도 실패 시 False 반환
            try:
                if hasattr(self, 'filter_validator') and self.filter_validator:
                    validation_result = self.filter_validator.validate_winning_numbers(round_num, prediction)
                    return validation_result.get('passed_all_filters', False)
            except Exception:
                pass
            return False

    def _validate_predictions_with_filter(self, result: Dict[str, Any], round_num: int) -> None:
        """예측 번호들이 필터를 통과하는지 검증 + 필터링된 풀 내 포함 여부 확인"""
        try:
            if not hasattr(self, 'filter_validator') or not self.filter_validator:
                logging.debug(f"필터 검증기가 없어 검증을 건너뜁니다")
                return
                
            # 각 모델의 예측에 대해 필터 검증
            filter_validations = {}
            total_predictions = 0
            passed_predictions = 0
            in_filtered_pool = 0  # 필터링된 풀에 포함된 예측 수
            
            for model_name, predictions in result.get('predictions', {}).items():
                if not predictions:
                    continue
                    
                model_validations = []
                model_passed = 0
                model_in_pool = 0
                
                for pred in predictions:
                    if not pred or len(pred) != 6:
                        continue
                        
                    total_predictions += 1
                    
                    # 필터 검증 수행
                    validation_result = self.filter_validator.validate_winning_numbers(
                        round_num, pred
                    )
                    
                    # 필터링된 풀에 포함되는지 확인
                    is_in_pool = self._check_prediction_in_filtered_pool(pred, round_num)
                    if is_in_pool:
                        model_in_pool += 1
                        in_filtered_pool += 1
                    
                    if validation_result['passed_all_filters']:
                        model_passed += 1
                        passed_predictions += 1
                        model_validations.append({
                            'prediction': pred,
                            'passed': True,
                            'in_filtered_pool': is_in_pool,
                            'failed_filters': []
                        })
                    else:
                        model_validations.append({
                            'prediction': pred,
                            'passed': False,
                            'in_filtered_pool': is_in_pool,
                            'failed_filters': validation_result['failed_filters']
                        })
                        
                        # 경고 로그 (디버그 레벨로 변경)
                        failed_filter_names = [f['name'] for f in validation_result['failed_filters']]
                        logging.debug(
                            f"[백테스팅] {model_name} 예측 {pred} 필터 실패: {failed_filter_names}"
                        )
                
                # 모델별 통과율 계산
                if len(model_validations) > 0:
                    pass_rate = (model_passed / len(model_validations)) * 100
                    pool_inclusion_rate = (model_in_pool / len(model_validations)) * 100
                    
                    filter_validations[model_name] = {
                        'validations': model_validations,
                        'pass_rate': pass_rate,
                        'pool_inclusion_rate': pool_inclusion_rate,
                        'passed': model_passed,
                        'in_pool': model_in_pool,
                        'total': len(model_validations)
                    }
                    
                    # 로그 출력 개선 - 두 지표의 의미 명확화
                    logging.info(
                        f"[백테스팅] {model_name} - "
                        f"필터 통과율(런타임): {pass_rate:.1f}% ({model_passed}/{len(model_validations)}), "
                        f"DB 풀 포함률: {pool_inclusion_rate:.1f}% ({model_in_pool}/{len(model_validations)})"
                    )

                    # Only warn if DB pool data exists for this round
                    if pool_inclusion_rate < 20 and self._round_has_db_pool(round_num):
                        logging.warning(
                            f"⚠️ {model_name} 예측이 필터링 풀에 거의 포함되지 않음: {pool_inclusion_rate:.1f}%"
                        )
                    elif pool_inclusion_rate < 20:
                        logging.debug(
                            f"[DB 풀 없음] {model_name} 낮은 포함률은 DB 데이터 부재로 인함: {pool_inclusion_rate:.1f}%"
                        )
            
            # 결과에 필터 검증 정보 추가
            result['filter_validation'] = filter_validations
            
            # 전체 통과율 계산
            if total_predictions > 0:
                overall_pass_rate = (passed_predictions / total_predictions) * 100
                overall_pool_rate = (in_filtered_pool / total_predictions) * 100
                
                result['filter_pass_rate'] = overall_pass_rate
                result['filtered_pool_inclusion_rate'] = overall_pool_rate
                
                logging.info(
                    f"[백테스팅 요약] "
                    f"전체 필터 통과율(런타임): {overall_pass_rate:.1f}% ({passed_predictions}/{total_predictions}), "
                    f"DB 풀 포함률: {overall_pool_rate:.1f}% ({in_filtered_pool}/{total_predictions})"
                )

                # Only warn if DB pool data exists for this round
                if overall_pool_rate < 15 and self._round_has_db_pool(round_num):
                    # Only warn if SEVERELY low (< 5%) AND first occurrence
                    # Known issue: ML-Filter disconnect (CLAUDE.md:115-125) with automatic mitigation
                    if overall_pool_rate < 5 and not hasattr(self, '_ml_pool_warning_shown'):
                        logging.warning(
                            f"🚨 ML 예측의 DB 풀 포함률이 매우 낮음: {overall_pool_rate:.1f}%"
                        )
                        logging.info("→ ML-필터 통합 개선이 권장됨 (자동 완화 로직 활성: relaxed threshold, similar matching)")
                        self._ml_pool_warning_shown = True
                    else:
                        # Normal case for known issue with mitigation
                        logging.info(
                            f"[ML-필터] DB 풀 포함률: {overall_pool_rate:.1f}% "
                            f"(완화 로직 활성: relaxed threshold, similar matching)"
                        )
                elif overall_pool_rate < 15:
                    logging.debug(
                        f"[DB 풀 없음] 낮은 전체 포함률은 DB 데이터 부재로 인함: {overall_pool_rate:.1f}%"
                    )
            else:
                result['filter_pass_rate'] = 0
                result['filtered_pool_inclusion_rate'] = 0
                
        except Exception as e:
            logging.error(f"필터 검증 중 오류 발생: {e}")
            result['filter_validation'] = {}
            result['filter_pass_rate'] = 0
            result['filtered_pool_inclusion_rate'] = 0
    
    def _calculate_matches(self, predictions: Dict[str, List[List[int]]], actual: List[int], bonus: Optional[int] = None) -> Dict[str, Any]:
        """예측과 실제 당첨번호 비교 (보너스 번호 포함)"""
        matches = {}
        actual_set = set(actual)
        
        # 이미 경고한 예측 추적 (중복 경고 방지)
        warned_predictions = set()
        
        for model_name, model_predictions in predictions.items():
            model_matches = []
            for pred in model_predictions:
                pred_set = set(pred)
                match_count = len(pred_set & actual_set)
                bonus_match = bonus in pred_set if bonus else False
                pred_tuple = tuple(pred)
                
                # 높은 일치 개수 통계적 검증
                contaminated = False
                if match_count > 4:
                    # 이미 경고한 예측인지 확인
                    if pred_tuple not in warned_predictions:
                        # 5개 일치 확률: 약 0.003%, 6개 일치 확률: 약 0.000012%
                        # 전체 백테스팅에서 5개 이상 일치가 전체의 1% 미만이면 성과로 판단
                        if match_count == 5:
                            # 5개 일치는 드물지만 가능한 우수 성과
                            logging.info(f"🎯 [모델: {model_name}] 우수한 예측 성과! {match_count}개 일치 (예측: {pred}, 실제: {actual})")
                        elif match_count == 6:
                            # 6개 완전 일치는 통계적 이상치 (1 in 8.14M, 0.0000123%)
                            # Single jackpot: Flag for review (legitimate possibility)
                            # Multiple jackpots: Systematic contamination (abort)
                            self._jackpot_count += 1
                            logging.warning(f"🎰 JACKPOT! [모델: {model_name}] 6/6 완전 일치 감지 (#{self._jackpot_count})")
                            logging.warning(f"   예측: {pred}, 실제: {actual}")
                            logging.warning(f"   확률: 1 in 8,145,060 (0.0000123%) - 검토 필요")

                            # Only abort on systematic contamination (multiple jackpots)
                            if self._jackpot_count >= self._jackpot_threshold:
                                contaminated = True
                                raise ValueError(
                                    f"❌ Systematic data contamination detected!\n"
                                    f"   Multiple jackpots ({self._jackpot_count}) exceed threshold ({self._jackpot_threshold}).\n"
                                    f"   Latest: Model={model_name}, Prediction={pred}, Actual={actual}\n"
                                    f"   This indicates systematic access to future information."
                                )
                        warned_predictions.add(pred_tuple)
                    else:
                        # Combined 모델이 재사용한 경우
                        logging.debug(f"[모델: {model_name}] 동일 예측 재사용: {pred}")
                    
                    # 예측이 실제와 완전히 동일한 순서로 일치하는 경우 (매우 드물지만 가능)
                    if pred == actual:
                        logging.info(f"💎 [모델: {model_name}] 완벽한 예측! 번호와 순서까지 일치: {pred}")
                        # contaminated = False로 유지 (정상적인 예측으로 간주)
                
                # ENSEMBLE 모델 모니터링
                if ENSEMBLE_MONITOR_AVAILABLE and model_name == 'ensemble':
                    try:
                        monitor = get_ensemble_monitor()
                        monitor.record_prediction(
                            prediction=pred,
                            actual=actual,
                            round_num=round_num
                        )
                    except Exception as e:
                        logging.debug(f"ENSEMBLE 모니터링 기록 실패: {e}")
                
                # 등수 계산 (보너스 포함)
                rank = None
                if match_count == 6:
                    rank = 1  # 1등
                elif match_count == 5 and bonus_match:
                    rank = 2  # 2등 (5개 + 보너스)
                elif match_count == 5:
                    rank = 3  # 3등
                elif match_count == 4:
                    rank = 4  # 4등
                elif match_count == 3:
                    rank = 5  # 5등
                    
                model_matches.append({
                    'prediction': pred,
                    'match_count': match_count,
                    'bonus_match': bonus_match,
                    'rank': rank,
                    'matches': sorted(list(pred_set & actual_set)),
                    'contaminated': contaminated  # 오염 여부 기록
                })
            matches[model_name] = model_matches
        
        return matches
    
    def _calculate_performance_metrics(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """백테스팅 성능 지표 계산"""
        metrics = {
            'total_rounds': len(predictions),
            'model_performance': {},
            'match_distribution': {i: 0 for i in range(7)}
        }

        # 모델별 성능 계산 (고정 모델 + predictions 데이터의 동적 모델 포함)
        default_models = ['lstm', 'ensemble', 'monte_carlo', 'combined']
        dynamic_models = set()
        for pred_result in predictions:
            if 'matches' in pred_result:
                dynamic_models.update(pred_result['matches'].keys())
        model_names = list(dict.fromkeys(default_models + list(dynamic_models)))
        for model in model_names:
            model_metrics = {
                'total_predictions': 0,
                'match_counts': {i: 0 for i in range(7)},
                'avg_matches': 0,
                'best_match': 0,
                'accuracy_3plus': 0,
                'contaminated_count': 0,  # 오염된 예측 카운트
                'filter_passed_count': 0  # 필터 통과한 예측 수 (Optuna 최적화용)
            }

            total_matches = 0
            predictions_3plus = 0
            filter_passed_count = 0  # 필터 통과 카운터

            for pred_result in predictions:
                # 필터 검증 결과 수집
                filter_validation = pred_result.get('filter_validation', {})

                # 🔍 DEBUG: filter_validation 확인
                if not filter_validation:
                    logging.debug(f"[DEBUG] pred_result에 filter_validation 없음: keys={pred_result.keys()}")

                if model in filter_validation:
                    model_filter_info = filter_validation[model]
                    # 해당 모델의 필터 통과 수 누적
                    passed = model_filter_info.get('passed', 0)
                    filter_passed_count += passed
                    logging.debug(f"[DEBUG] {model} filter_passed: {passed}, 누적: {filter_passed_count}")

                # 매치 결과 수집
                if 'matches' in pred_result and model in pred_result['matches']:
                    for match_info in pred_result['matches'][model]:
                        match_count = match_info['match_count']
                        model_metrics['match_counts'][match_count] += 1
                        model_metrics['total_predictions'] += 1
                        total_matches += match_count

                        # 오염된 데이터 체크
                        if match_info.get('contaminated', False):
                            model_metrics['contaminated_count'] += 1

                        # 카운터 매니저에도 기록
                        self.counter_manager.increment(f'{model}_predictions')
                        self.counter_manager.increment(f'{model}_matches', match_count)

                        if match_count >= 3:
                            predictions_3plus += 1
                            self.counter_manager.increment(f'{model}_3plus')

                        if match_count > model_metrics['best_match']:
                            model_metrics['best_match'] = match_count

            # 필터 통과 수를 model_metrics에 저장
            model_metrics['filter_passed_count'] = filter_passed_count

            if model_metrics['total_predictions'] > 0:
                model_metrics['avg_matches'] = total_matches / model_metrics['total_predictions']
                model_metrics['accuracy_3plus'] = predictions_3plus / model_metrics['total_predictions'] * 100
                # 필터 통과율도 계산
                model_metrics['filter_pass_rate'] = (filter_passed_count / model_metrics['total_predictions']) * 100
            else:
                # [FIX] 예측 수가 0인 경우 명시적 경고 및 기본값 설정
                model_metrics['filter_pass_rate'] = 0
                model_metrics['avg_matches'] = 0.0
                model_metrics['accuracy_3plus'] = 0.0
                logging.warning(f"⚠️ 모델 {model}의 예측 수가 0입니다! 백테스팅 결과를 확인하세요.")

            metrics['model_performance'][model] = model_metrics

        # ✅ FIX: 전체 필터 통과율 계산 (continuous_improvement_engine이 필요로 함)
        # 모든 모델의 필터 통과율을 집계하여 overall_filter_pass_rate 계산
        total_predictions_all_models = 0
        total_passed_all_models = 0

        for model_name, model_data in metrics['model_performance'].items():
            total_predictions_all_models += model_data.get('total_predictions', 0)
            total_passed_all_models += model_data.get('filter_passed_count', 0)

        if total_predictions_all_models > 0:
            metrics['overall_filter_pass_rate'] = (total_passed_all_models / total_predictions_all_models) * 100
        else:
            metrics['overall_filter_pass_rate'] = 0.0

        # overall_avg_matches 계산 (continuous_improvement_engine이 참조)
        total_matches_all = 0
        total_preds_all = 0
        for model_name, model_data in metrics['model_performance'].items():
            preds = model_data.get('total_predictions', 0)
            if preds > 0:
                total_matches_all += model_data.get('avg_matches', 0) * preds
                total_preds_all += preds

        if total_preds_all > 0:
            metrics['overall_avg_matches'] = total_matches_all / total_preds_all
        else:
            metrics['overall_avg_matches'] = 0.0

        return metrics
    
    def _save_backtest_results(self, results: Dict[str, Any]):
        """백테스팅 결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/backtest_results_optimized_{timestamp}.json"
        
        try:
            # 버그 수정: deep copy로 저장 시점의 데이터 보호
            results_to_save = copy.deepcopy(results)
            # NumPy 타입 변환
            def convert_numpy(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj
            
            # 재귀적 변환
            import json
            converted_results = json.loads(
                json.dumps(results_to_save, default=convert_numpy)
            )
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(converted_results, f, ensure_ascii=False, indent=2)
            logging.info(f"\n백테스팅 결과 저장: {filename}")
        except Exception as e:
            logging.error(f"결과 저장 중 오류: {str(e)}")

    def _validate_results(self, metrics: Dict[str, Any], model_name: str):
        """백테스팅 결과 오염 검증

        Args:
            metrics: 백테스팅 메트릭 딕셔너리
            model_name: 검증할 모델 이름

        Raises:
            ValueError: 오염이 감지된 경우
        """
        if model_name not in metrics.get('model_performance', {}):
            logging.warning(f"⚠️ 모델 {model_name}의 메트릭을 찾을 수 없습니다.")
            return

        model_metrics = metrics['model_performance'][model_name]
        avg_matches = model_metrics.get('avg_matches', 0)
        total_predictions = model_metrics.get('total_predictions', 0)

        # 보수적 임계값: 1.5 (정상 범위: 0.8-1.5)
        contamination_threshold = 1.5

        if total_predictions == 0:
            logging.warning(f"⚠️ 모델 {model_name}의 예측 수가 0입니다.")
            return

        if avg_matches > contamination_threshold:
            error_msg = (
                f"❌ Data contamination detected in {model_name}!\n"
                f"   Average matches: {avg_matches:.2f} (threshold: {contamination_threshold})\n"
                f"   Expected range: 0.8-1.5\n"
                f"   Total predictions: {total_predictions}\n"
                f"   This indicates the model has access to future information.\n"
                f"   Please check:\n"
                f"   1. Feature engineering for look-ahead bias\n"
                f"   2. Model cache key includes round number\n"
                f"   3. Training/test data separation"
            )
            logging.error(error_msg)
            raise ValueError(error_msg)

        logging.info(f"✅ Contamination check passed for {model_name}: avg_matches={avg_matches:.2f}")

    def _save_to_database(self, results: Dict[str, Any]):
        """백테스팅 결과를 데이터베이스에 저장"""
        try:
            # NumPy 타입을 Python 기본 타입으로 변환
            def convert_numpy_types(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {key: convert_numpy_types(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
                return obj
            
            # 상세 예측 결과를 PerformanceStatsManager가 기대하는 형식으로 변환
            formatted_results = self._format_results_for_db(results)
            # NumPy 타입 변환 적용
            formatted_results = convert_numpy_types(formatted_results)
            
            # DB에 저장
            session_id = self.performance_stats_manager.save_backtest_results(formatted_results)
            
            if session_id > 0:
                logging.info(f"백테스팅 결과 DB 저장 완료 (세션 ID: {session_id})")
            else:
                logging.warning("백테스팅 결과 DB 저장에 실패했습니다")
                
        except Exception as e:
            logging.error(f"백테스팅 결과 DB 저장 중 오류: {str(e)}")
    
    def _format_results_for_db(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """DB 저장을 위해 결과 형식 변환"""
        formatted_predictions = []
        
        for pred_result in results.get('predictions', []):
            round_num = pred_result.get('round')
            actual_numbers = pred_result.get('actual_numbers', [])
            
            # 각 모델의 예측과 매치 결과를 통합
            formatted_pred = {
                'round': round_num,
                'winning_numbers': actual_numbers,
                'matches': {}
            }
            
            # 예측 결과와 매치 결과를 결합
            predictions = pred_result.get('predictions', {})
            matches = pred_result.get('matches', {})
            
            for model_name in predictions.keys():
                model_matches = []
                
                if model_name in matches:
                    # 기존 매치 정보 사용
                    for match_info in matches[model_name]:
                        model_matches.append({
                            'predicted_numbers': match_info.get('prediction', []),
                            'match_count': match_info.get('match_count', 0),
                            'contaminated': match_info.get('contaminated', False),
                            'filter_passed': True  # 기본값
                        })
                else:
                    # 예측만 있고 매치 정보가 없는 경우
                    for pred in predictions[model_name]:
                        model_matches.append({
                            'predicted_numbers': pred,
                            'match_count': 0,
                            'contaminated': False,
                            'filter_passed': True
                        })
                
                formatted_pred['matches'][model_name] = model_matches
            
            formatted_predictions.append(formatted_pred)
        
        # 기존 결과에 형식화된 예측 추가
        formatted_results = results.copy()
        formatted_results['predictions'] = formatted_predictions
        
        return formatted_results
    
    def _print_backtest_summary(self, results: Dict[str, Any]):
        """백테스팅 결과 요약 출력"""
        logging.info("\n" + "="*60)
        logging.info("최적화된 백테스팅 결과 요약")
        logging.info("="*60)
        
        metrics = results['performance_metrics']
        logging.info(f"\n총 테스트 회차: {metrics['total_rounds']}개")
        
        for model_name, model_metrics in metrics['model_performance'].items():
            logging.info(f"\n[{model_name.upper()} 모델 성능]")
            logging.info(f"- 총 예측 수: {model_metrics['total_predictions']}개")
            logging.info(f"- 평균 일치 개수: {model_metrics['avg_matches']:.2f}개")
            logging.info(f"- 최고 일치 개수: {model_metrics['best_match']}개")
            logging.info(f"- 3개 이상 일치율: {model_metrics['accuracy_3plus']:.2f}%")

            # 필터 통과율 표시 (Optuna 최적화에 중요)
            if 'filter_passed_count' in model_metrics and model_metrics['total_predictions'] > 0:
                filter_pass_rate = model_metrics.get('filter_pass_rate', 0)
                filter_passed_count = model_metrics.get('filter_passed_count', 0)
                logging.info(f"- 필터 통과율: {filter_pass_rate:.2f}% ({filter_passed_count}/{model_metrics['total_predictions']})")

            # 오염된 데이터 표시
            if model_metrics.get('contaminated_count', 0) > 0:
                logging.warning(f"- ⚠️ 데이터 오염 감지: {model_metrics['contaminated_count']}개 (6개 완전 일치)")

            logging.info("- 일치 개수 분포:")
            for i in range(7):
                if model_metrics['match_counts'][i] > 0:
                    percentage = model_metrics['match_counts'][i] / model_metrics['total_predictions'] * 100
                    logging.info(f"  {i}개 일치: {model_metrics['match_counts'][i]}개 ({percentage:.2f}%)")


    def generate_performance_report(self, results: Dict[str, Any]) -> str:
        """성능 보고서 생성"""
        report = []
        report.append("\n" + "="*80)
        report.append("로또 예측 시스템 성능 보고서")
        report.append("="*80)
        
        # 백테스팅 정보
        if 'start_round' in results:
            report.append(f"\n테스트 기간: {results['start_round']}회 ~ {results['end_round']}회")
        
        metrics = results.get('performance_metrics', {})
        if 'total_rounds' in metrics:
            report.append(f"테스트 회차 수: {metrics['total_rounds']}개")
        
        # 모델별 성능
        report.append("\n모델별 성능 분석:")
        
        model_performance = metrics.get('model_performance', {})
        for model_name, model_metrics in model_performance.items():
            report.append(f"\n[{model_name.upper()}]")
            report.append(f"  - 평균 일치 개수: {model_metrics.get('avg_matches', 0):.2f}개")
            report.append(f"  - 3개 이상 일치율: {model_metrics.get('accuracy_3plus', 0):.2f}%")
            report.append(f"  - 최고 일치 개수: {model_metrics.get('best_match', 0)}개")
            
            # 일치 분포
            if 'match_counts' in model_metrics:
                report.append("  - 일치 개수 분포:")
                total_pred = model_metrics.get('total_predictions', 1)
                if total_pred > 0:
                    for i in range(7):
                        count = model_metrics['match_counts'].get(i, 0)
                        if count > 0:
                            pct = count / total_pred * 100
                            report.append(f"    {i}개: {count}회 ({pct:.1f}%)")
        
        return '\n'.join(report)


def main():
    """테스트 실행"""
    from ..logger import setup_logging
    setup_logging()
    
    # 최적화된 프레임워크 사용
    framework = OptimizedBacktestingFramework(enable_fractal=False)  # 프랙탈 비활성화
    
    # 최근 50회차에 대해 백테스팅 수행
    results = framework.run_backtest(
        start_round=1133,
        end_round=1182,
        window_size=100
    )
    
    logging.info("\n최적화된 백테스팅 완료!")


if __name__ == "__main__":
    main()