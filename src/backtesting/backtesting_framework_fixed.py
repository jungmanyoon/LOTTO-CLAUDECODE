#!/usr/bin/env python3
"""
백테스팅 프레임워크 (버그 수정 버전)
데이터 무결성을 보장하는 개선된 백테스팅 프레임워크
"""
import logging
from typing import Dict, List, Tuple, Any
import numpy as np
from datetime import datetime
import json
from tqdm import tqdm
import os
import copy  # 추가: deep copy를 위해
from ..core.db_manager import DatabaseManager
from ..core.filter_manager import FilterManager
from ..ml.lstm_predictor import LSTMPredictor
from ..ml.ensemble_predictor import EnsemblePredictor
from ..probabilistic.monte_carlo_simulator import MonteCarloSimulator
from ..probabilistic.bayesian_inference import BayesianFilter as BayesianInference
from ..advanced.fractal_pattern_analyzer import FractalPatternAnalyzer

def convert_numpy_types(obj):
    """NumPy 타입을 JSON 직렬화 가능한 Python 기본 타입으로 변환"""
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
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    else:
        return obj

def validate_predictions(predictions: List[List[int]], actual_numbers: List[int], 
                        model_name: str, round_num: int) -> bool:
    """예측 결과의 유효성을 검증
    
    Args:
        predictions: 예측 번호 리스트
        actual_numbers: 실제 당첨 번호
        model_name: 모델 이름
        round_num: 회차 번호
        
    Returns:
        bool: 유효한 경우 True
    """
    for i, pred in enumerate(predictions):
        if not pred:
            continue
            
        matches = len(set(pred) & set(actual_numbers))
        
        # 4개 이상 일치는 통계적으로 매우 드문 경우 (경고)
        if matches >= 4:
            logging.warning(f"⚠️ 의심스러운 예측 발견!")
            logging.warning(f"  모델: {model_name}, 회차: {round_num}")
            logging.warning(f"  예측 #{i+1}: {pred}")
            logging.warning(f"  실제 번호: {actual_numbers}")
            logging.warning(f"  일치 개수: {matches}개")
            
            # 5개 이상 일치는 거의 불가능 (오류로 처리)
            if matches >= 5:
                logging.error(f"❌ 비정상적인 예측! 데이터 누출 가능성")
                return False
    
    return True

class BacktestingFramework:
    """개선된 백테스팅 프레임워크 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager()
        
        # 예측 모델 초기화
        self.lstm_predictor = LSTMPredictor()
        self.ensemble_predictor = EnsemblePredictor()
        self.monte_carlo = MonteCarloSimulator(db_manager)
        self.bayesian = BayesianInference()
        self.fractal = FractalPatternAnalyzer()
        
        # 결과 디렉토리 생성
        os.makedirs('results', exist_ok=True)
        
        # 데이터 무결성 검증 플래그
        self.enable_validation = True
        self.strict_mode = True  # 엄격 모드: 의심스러운 예측 시 중단
    
    def run_backtest(self, start_round: int, end_round: int, 
                    window_size: int = 100) -> Dict[str, Any]:
        """백테스팅 실행 (개선된 버전)
        
        Args:
            start_round: 시작 회차
            end_round: 종료 회차  
            window_size: 학습 윈도우 크기
            
        Returns:
            Dict: 백테스팅 결과
        """
        logging.info("\n백테스팅 시작: %d회차 ~ %d회차", start_round, end_round)
        logging.info("학습 윈도우 크기: %d회차", window_size)
        
        # 결과 초기화
        results = {
            'start_round': start_round,
            'end_round': end_round,
            'window_size': window_size,
            'predictions': [],
            'validation_warnings': []  # 검증 경고 추가
        }
        
        # 전체 당첨번호 데이터 가져오기
        all_numbers = self.db_manager.get_all_numbers()
        winning_numbers_dict = {
            round_num: [int(n) for n in numbers.split(',')]
            for round_num, numbers, _ in all_numbers
        }
        
        # 백테스팅 수행
        for test_round in tqdm(range(start_round, end_round + 1), desc="백테스팅 진행"):
            # 학습 데이터 범위
            train_start = max(1, test_round - window_size)
            train_end = test_round - 1
            
            # 예측 수행
            prediction_result = self._predict_for_round(
                test_round, train_start, train_end, winning_numbers_dict
            )
            
            # 실제 당첨번호와 비교
            if test_round in winning_numbers_dict:
                actual_numbers = winning_numbers_dict[test_round]
                prediction_result['actual_numbers'] = actual_numbers
                
                # 데이터 무결성 검증
                if self.enable_validation:
                    for model_name, predictions in prediction_result['predictions'].items():
                        if predictions:
                            is_valid = validate_predictions(
                                predictions, actual_numbers, model_name, test_round
                            )
                            
                            if not is_valid:
                                warning = {
                                    'round': test_round,
                                    'model': model_name,
                                    'message': '비정상적인 예측 발견'
                                }
                                results['validation_warnings'].append(warning)
                                
                                if self.strict_mode:
                                    logging.error("엄격 모드: 백테스팅 중단")
                                    raise ValueError(f"데이터 무결성 오류: {test_round}회차 {model_name}")
                
                # 일치 결과 계산
                prediction_result['matches'] = self._calculate_matches(
                    prediction_result['predictions'], actual_numbers
                )
            
            # 결과를 deep copy하여 저장 (원본 데이터 보호)
            results['predictions'].append(copy.deepcopy(prediction_result))
        
        # 성능 지표 계산
        results['performance_metrics'] = self._calculate_performance_metrics(
            results['predictions']
        )
        
        # 검증 요약 추가
        if results['validation_warnings']:
            logging.warning(f"총 {len(results['validation_warnings'])}개의 검증 경고 발생")
        
        # 결과 저장 (deep copy 사용)
        self._save_backtest_results(copy.deepcopy(results))
        
        # 결과 요약 출력
        self._print_backtest_summary(results)
        
        return results
    
    def _predict_for_round(self, round_num: int, train_start: int, train_end: int, 
                          winning_numbers_dict: Dict[int, List[int]]) -> Dict[str, Any]:
        """특정 회차에 대한 예측 수행 (원본 메서드와 동일)"""
        result = {
            'round': round_num,
            'train_range': (train_start, train_end),
            'predictions': {},
            'scores': {}
        }
        
        # 학습 데이터 준비
        train_data = [
            winning_numbers_dict[r] for r in range(train_start, train_end + 1)
            if r in winning_numbers_dict
        ]
        
        try:
            # 1. LSTM 예측
            lstm_predictions = self._get_lstm_predictions(train_data)
            result['predictions']['lstm'] = lstm_predictions[:5]
            
            # 2. Ensemble 예측
            ensemble_predictions = self._get_ensemble_predictions(train_data, train_end)
            result['predictions']['ensemble'] = ensemble_predictions[:5]
            
            # 3. Monte Carlo 예측
            mc_predictions = self._get_monte_carlo_predictions(train_data)
            result['predictions']['monte_carlo'] = mc_predictions[:5]
            
            # 4. 통합 예측 (각 모델의 최상위 예측 조합)
            combined = self._combine_predictions(result['predictions'])
            result['predictions']['combined'] = combined[:5]
            
        except Exception as e:
            logging.error(f"회차 {round_num} 예측 중 오류: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    # 나머지 메서드들은 원본과 동일...
    # (실제 구현 시 원본 파일의 나머지 메서드들을 복사)
    
    def _save_backtest_results(self, results: Dict[str, Any]):
        """백테스팅 결과 저장 (개선된 버전)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/backtest_results_fixed_{timestamp}.json"
        
        try:
            # NumPy 타입을 Python 기본 타입으로 변환
            converted_results = convert_numpy_types(results)
            
            # 저장 전 최종 검증
            if self.enable_validation:
                self._final_validation(converted_results)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(converted_results, f, ensure_ascii=False, indent=2)
            
            logging.info(f"\n백테스팅 결과 저장: {filename}")
            
            # 검증 경고가 있으면 별도 파일로 저장
            if 'validation_warnings' in results and results['validation_warnings']:
                warning_filename = f"results/validation_warnings_{timestamp}.json"
                with open(warning_filename, 'w', encoding='utf-8') as f:
                    json.dump(results['validation_warnings'], f, ensure_ascii=False, indent=2)
                logging.warning(f"검증 경고 저장: {warning_filename}")
                
        except Exception as e:
            logging.error(f"결과 저장 중 오류: {str(e)}")
    
    def _final_validation(self, results: Dict[str, Any]):
        """저장 전 최종 데이터 검증"""
        suspicious_count = 0
        
        for pred_result in results.get('predictions', []):
            if 'actual_numbers' not in pred_result:
                continue
                
            actual = pred_result['actual_numbers']
            
            for model_name, predictions in pred_result.get('predictions', {}).items():
                for pred in predictions:
                    if pred:
                        matches = len(set(pred) & set(actual))
                        if matches >= 4:
                            suspicious_count += 1
                            logging.warning(f"최종 검증: 의심스러운 예측 {suspicious_count}개 발견")
        
        if suspicious_count > 0:
            logging.error(f"⚠️ 총 {suspicious_count}개의 의심스러운 예측이 포함되어 있습니다!")
            if self.strict_mode:
                raise ValueError("데이터 무결성 최종 검증 실패")