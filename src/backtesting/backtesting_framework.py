#!/usr/bin/env python3
"""
백테스팅 프레임워크
과거 데이터를 사용하여 예측 성능을 검증
"""
import logging
import sys
from typing import Dict, List, Tuple, Any
import numpy as np
from datetime import datetime
import json
from tqdm import tqdm
import os
import copy  # 버그 수정: deep copy 추가
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

class BacktestingFramework:
    """백테스팅 프레임워크 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        
        # ML/AI 모델 초기화
        self.lstm_predictor = LSTMPredictor()
        self.ensemble_predictor = EnsemblePredictor()
        self.monte_carlo = MonteCarloSimulator(db_manager)
        self.bayesian_filter = BayesianInference(db_manager)
        self.fractal_analyzer = FractalPatternAnalyzer(db_manager)
        
        self.backtest_results = []
        logging.info("백테스팅 프레임워크 초기화 완료")
    
    def run_backtest(self, start_round: int, end_round: int, window_size: int = 100) -> Dict[str, Any]:
        """백테스팅 실행
        
        Args:
            start_round: 백테스팅 시작 회차
            end_round: 백테스팅 종료 회차
            window_size: 학습에 사용할 과거 데이터 윈도우 크기
            
        Returns:
            Dict: 백테스팅 결과
        """
        logging.info(f"\n백테스팅 시작: {start_round}회차 ~ {end_round}회차")
        logging.info(f"학습 윈도우 크기: {window_size}회차")
        
        results = {
            'start_round': start_round,
            'end_round': end_round,
            'window_size': window_size,
            'predictions': [],
            'performance_metrics': {}
        }
        
        # 전체 당첨번호 데이터 가져오기
        all_numbers = self.db_manager.get_all_numbers()
        winning_numbers_dict = {
            round_num: [int(n) for n in numbers.split(',')]
            for round_num, numbers, _ in all_numbers  # 3개의 값 언패킹
        }
        
        # 백테스팅 수행
        import threading as _threading
        _tqdm_disable = _threading.current_thread() is not _threading.main_thread()
        for test_round in tqdm(range(start_round, end_round + 1), desc="백테스팅 진행", file=sys.stdout, disable=_tqdm_disable):
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
                prediction_result['matches'] = self._calculate_matches(
                    prediction_result['predictions'], actual_numbers
                )
            
            # 버그 수정: deep copy로 원본 데이터 보호
            results['predictions'].append(copy.deepcopy(prediction_result))
        
        # 성능 지표 계산
        results['performance_metrics'] = self._calculate_performance_metrics(results['predictions'])
        
        # 결과 저장 (버그 수정: deep copy 사용)
        self._save_backtest_results(copy.deepcopy(results))
        
        # 결과 요약 출력
        self._print_backtest_summary(results)
        
        return results
    
    def _predict_for_round(self, round_num: int, train_start: int, train_end: int, 
                          winning_numbers_dict: Dict[int, List[int]]) -> Dict[str, Any]:
        """특정 회차에 대한 예측 수행
        
        Args:
            round_num: 예측할 회차
            train_start: 학습 시작 회차
            train_end: 학습 종료 회차
            winning_numbers_dict: 당첨번호 딕셔너리
            
        Returns:
            Dict: 예측 결과
        """
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
            result['predictions']['lstm'] = lstm_predictions[:5]  # 상위 5개
            
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
    
    def _get_lstm_predictions(self, train_data: List[List[int]]) -> List[List[int]]:
        """LSTM 모델 예측"""
        try:
            # LSTM predictor가 없으면 종료
            if not self.lstm_predictor:
                logging.warning("LSTM predictor가 초기화되지 않았습니다.")
                return []
            
            # 데이터를 LSTM이 요구하는 형식으로 변환 (List[str])
            winning_numbers_str = [','.join(map(str, nums)) for nums in train_data]
            
            # 모델 학습 확인 및 필요시 학습
            if not self.lstm_predictor.is_trained:
                logging.info("LSTM 모델 학습 중...")
                # 최소 50개 데이터가 있을 때만 학습
                if len(winning_numbers_str) >= 50:
                    self.lstm_predictor.train(winning_numbers_str, epochs=30, batch_size=32)
                else:
                    logging.warning(f"LSTM 학습을 위한 데이터 부족: {len(winning_numbers_str)}개 (최소 50개 필요)")
                    return []
            
            # 예측 수행 - 올바른 메서드 사용
            sequence_length = min(50, len(winning_numbers_str))
            recent_numbers = winning_numbers_str[-sequence_length:]
            
            predictions = self.lstm_predictor.predict_next_numbers(
                recent_numbers,
                num_predictions=10
            )
            
            # 예측 결과를 List[List[int]] 형식으로 변환
            result = []
            for pred in predictions[:5]:
                if isinstance(pred, dict) and 'numbers' in pred:
                    # pred['numbers']가 이미 정수 리스트인 경우
                    if isinstance(pred['numbers'], list):
                        result.append(pred['numbers'])
                    # pred['numbers']가 문자열인 경우 파싱
                    elif isinstance(pred['numbers'], str):
                        numbers = [int(n) for n in pred['numbers'].split(',')]
                        result.append(sorted(numbers))
            
            return result
            
        except Exception as e:
            logging.error(f"LSTM 예측 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return []
    
    def _get_ensemble_predictions(self, train_data: List[List[int]], current_round: int) -> List[List[int]]:
        """앙상블 모델 예측"""
        try:
            # 데이터 준비
            winning_numbers_data = []
            for i, numbers in enumerate(train_data):
                # 문자열로 변환
                numbers_str = ','.join(map(str, numbers))
                winning_numbers_data.append(numbers_str)
            
            # 모델 학습 (필요시)
            if not self.ensemble_predictor.is_trained:
                self.ensemble_predictor.train(winning_numbers_data)
            
            # 예측 수행
            predictions = self.ensemble_predictor.predict_next_numbers(
                winning_numbers_data,
                num_predictions=10
            )
            return [pred['numbers'] for pred in predictions[:5]]
        except Exception as e:
            logging.error(f"앙상블 예측 오류: {str(e)}")
            return []
    
    def _get_monte_carlo_predictions(self, train_data: List[List[int]]) -> List[List[int]]:
        """Monte Carlo 시뮬레이션 예측"""
        try:
            # 빈도 분석
            number_freq = {i: 0 for i in range(1, 46)}
            for numbers in train_data:
                for num in numbers:
                    number_freq[num] += 1
            
            # 시뮬레이션으로 예측 생성
            predictions = []
            for _ in range(1000):  # 1000회 시뮬레이션
                # 빈도 기반 확률로 번호 선택
                probs = np.array([number_freq[i] for i in range(1, 46)])
                probs = probs / probs.sum()
                
                selected = np.random.choice(45, 6, replace=False, p=probs) + 1
                predictions.append(sorted(selected.tolist()))
            
            # 가장 많이 나온 조합 상위 5개 반환
            from collections import Counter
            combo_counts = Counter([tuple(p) for p in predictions])
            top_combos = combo_counts.most_common(5)

            return [list(combo) for combo, _ in top_combos]
        except Exception as e:
            logging.error(f"백테스트 실패: {e}")
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
    
    def _calculate_matches(self, predictions: Dict[str, List[List[int]]], actual: List[int]) -> Dict[str, Any]:
        """예측과 실제 당첨번호 비교"""
        matches = {}
        
        for model_name, model_predictions in predictions.items():
            model_matches = []
            for pred in model_predictions:
                match_count = len(set(pred) & set(actual))
                model_matches.append({
                    'prediction': pred,
                    'match_count': match_count,
                    'matches': sorted(list(set(pred) & set(actual)))
                })
            matches[model_name] = model_matches
        
        return matches
    
    def _calculate_performance_metrics(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """백테스팅 성능 지표 계산"""
        metrics = {
            'total_rounds': len(predictions),
            'model_performance': {},
            'match_distribution': {i: 0 for i in range(7)}  # 0~6개 일치
        }
        
        # 모델별 성능 계산
        model_names = ['lstm', 'ensemble', 'monte_carlo', 'combined']
        for model in model_names:
            model_metrics = {
                'total_predictions': 0,
                'match_counts': {i: 0 for i in range(7)},
                'avg_matches': 0,
                'best_match': 0,
                'accuracy_3plus': 0  # 3개 이상 맞춘 비율
            }
            
            total_matches = 0
            predictions_3plus = 0
            
            for pred_result in predictions:
                if 'matches' in pred_result and model in pred_result['matches']:
                    for match_info in pred_result['matches'][model]:
                        match_count = match_info['match_count']
                        model_metrics['match_counts'][match_count] += 1
                        model_metrics['total_predictions'] += 1
                        total_matches += match_count
                        
                        if match_count >= 3:
                            predictions_3plus += 1
                        
                        if match_count > model_metrics['best_match']:
                            model_metrics['best_match'] = match_count
            
            if model_metrics['total_predictions'] > 0:
                model_metrics['avg_matches'] = total_matches / model_metrics['total_predictions']
                model_metrics['accuracy_3plus'] = predictions_3plus / model_metrics['total_predictions'] * 100
            
            metrics['model_performance'][model] = model_metrics
        
        return metrics
    
    def _save_backtest_results(self, results: Dict[str, Any]):
        """백테스팅 결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/backtest_results_{timestamp}.json"
        
        try:
            # 버그 수정: deep copy로 저장 시점의 데이터 보호
            results_to_save = copy.deepcopy(results)
            # NumPy 타입을 Python 기본 타입으로 변환
            converted_results = convert_numpy_types(results_to_save)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(converted_results, f, ensure_ascii=False, indent=2)
            logging.info(f"\n백테스팅 결과 저장: {filename}")
        except Exception as e:
            logging.error(f"결과 저장 중 오류: {str(e)}")
    
    def _print_backtest_summary(self, results: Dict[str, Any]):
        """백테스팅 결과 요약 출력"""
        logging.info("\n" + "="*60)
        logging.info("백테스팅 결과 요약")
        logging.info("="*60)
        
        metrics = results['performance_metrics']
        logging.info(f"\n총 테스트 회차: {metrics['total_rounds']}개")
        
        for model_name, model_metrics in metrics['model_performance'].items():
            logging.info(f"\n[{model_name.upper()} 모델 성능]")
            logging.info(f"- 총 예측 수: {model_metrics['total_predictions']}개")
            logging.info(f"- 평균 일치 개수: {model_metrics['avg_matches']:.2f}개")
            logging.info(f"- 최고 일치 개수: {model_metrics['best_match']}개")
            logging.info(f"- 3개 이상 일치율: {model_metrics['accuracy_3plus']:.2f}%")
            
            logging.info("- 일치 개수 분포:")
            for i in range(7):
                if model_metrics['match_counts'][i] > 0:
                    percentage = model_metrics['match_counts'][i] / model_metrics['total_predictions'] * 100
                    logging.info(f"  {i}개 일치: {model_metrics['match_counts'][i]}개 ({percentage:.2f}%)")
    
    def evaluate_improvement(self, current_results: Dict[str, Any], 
                           previous_results: Dict[str, Any] = None) -> Dict[str, Any]:
        """성능 개선 평가
        
        Args:
            current_results: 현재 백테스팅 결과
            previous_results: 이전 백테스팅 결과 (비교용)
            
        Returns:
            Dict: 개선 평가 결과
        """
        evaluation = {
            'timestamp': datetime.now().isoformat(),
            'current_performance': {},
            'improvements': {},
            'recommendations': []
        }
        
        # 현재 성능 분석
        metrics = current_results.get('performance_metrics', {})
        for model_name, model_metrics in metrics.get('model_performance', {}).items():
            evaluation['current_performance'][model_name] = {
                'avg_matches': model_metrics.get('avg_matches', 0),
                'accuracy_3plus': model_metrics.get('accuracy_3plus', 0),
                'best_match': model_metrics.get('best_match', 0)
            }
        
        # 이전 결과와 비교
        if previous_results:
            prev_metrics = previous_results.get('performance_metrics', {})
            for model_name in evaluation['current_performance']:
                if model_name in prev_metrics.get('model_performance', {}):
                    prev_model = prev_metrics['model_performance'][model_name]
                    curr_model = evaluation['current_performance'][model_name]
                    
                    evaluation['improvements'][model_name] = {
                        'avg_matches_diff': curr_model['avg_matches'] - prev_model.get('avg_matches', 0),
                        'accuracy_3plus_diff': curr_model['accuracy_3plus'] - prev_model.get('accuracy_3plus', 0),
                        'improved': curr_model['avg_matches'] > prev_model.get('avg_matches', 0)
                    }
        
        # 개선 권장사항 생성
        self._generate_recommendations(evaluation)
        
        return evaluation
    
    def _generate_recommendations(self, evaluation: Dict[str, Any]):
        """성능 기반 개선 권장사항 생성"""
        recommendations = []
        
        for model_name, performance in evaluation['current_performance'].items():
            # LSTM 모델 권장사항
            if model_name == 'lstm' and performance['avg_matches'] < 1.0:
                recommendations.append({
                    'model': 'LSTM',
                    'issue': '낮은 평균 일치율',
                    'suggestion': '시퀀스 길이 증가 또는 레이어 깊이 조정 필요'
                })
            
            # Ensemble 모델 권장사항
            elif model_name == 'ensemble' and performance['accuracy_3plus'] < 5.0:
                recommendations.append({
                    'model': 'Ensemble',
                    'issue': '3개 이상 일치율 저조',
                    'suggestion': '모델 가중치 재조정 또는 특징 엔지니어링 개선'
                })
            
            # Monte Carlo 권장사항
            elif model_name == 'monte_carlo' and performance['avg_matches'] < 1.2:
                recommendations.append({
                    'model': 'Monte Carlo',
                    'issue': '시뮬레이션 정확도 부족',
                    'suggestion': '시뮬레이션 횟수 증가 또는 확률 분포 조정'
                })
        
        evaluation['recommendations'] = recommendations
    
    def generate_performance_report(self, results: Dict[str, Any]) -> str:
        """성능 보고서 생성"""
        report = []
        report.append("\n" + "="*80)
        report.append("🎯 로또 예측 시스템 성능 보고서")
        report.append("="*80)
        
        # 백테스팅 정보
        report.append(f"\n📅 테스트 기간: {results['start_round']}회 ~ {results['end_round']}회")
        report.append(f"📊 테스트 회차 수: {results['performance_metrics']['total_rounds']}개")
        
        # 모델별 성능
        report.append("\n📈 모델별 성능 분석:")
        metrics = results['performance_metrics']
        
        for model_name, model_metrics in metrics['model_performance'].items():
            report.append(f"\n[{model_name.upper()}]")
            report.append(f"  • 평균 일치 개수: {model_metrics['avg_matches']:.2f}개")
            report.append(f"  • 3개 이상 일치율: {model_metrics['accuracy_3plus']:.2f}%")
            report.append(f"  • 최고 일치 개수: {model_metrics['best_match']}개")
            
            # 일치 분포
            report.append("  • 일치 개수 분포:")
            for i in range(7):
                count = model_metrics['match_counts'][i]
                if count > 0:
                    pct = count / model_metrics['total_predictions'] * 100
                    bar = '█' * int(pct / 2)
                    report.append(f"    {i}개: {bar} {count}회 ({pct:.1f}%)")
        
        # 개선 평가
        evaluation = self.evaluate_improvement(results)
        if evaluation['recommendations']:
            report.append("\n💡 개선 권장사항:")
            for rec in evaluation['recommendations']:
                report.append(f"  • [{rec['model']}] {rec['issue']}: {rec['suggestion']}")
        
        # 전체 요약
        report.append("\n📊 전체 요약:")
        best_model = max(metrics['model_performance'].items(), 
                        key=lambda x: x[1]['avg_matches'])
        report.append(f"  • 최고 성능 모델: {best_model[0].upper()}")
        report.append(f"  • 최고 평균 일치: {best_model[1]['avg_matches']:.2f}개")
        
        report.append("\n" + "="*80)
        
        return "\n".join(report)


def main():
    """테스트 실행"""
    from ..logger import setup_logging
    setup_logging()
    
    framework = BacktestingFramework()
    
    # 최근 50회차에 대해 백테스팅 수행
    # 1133~1182회차를 테스트 (1033~1132 데이터로 학습)
    results = framework.run_backtest(
        start_round=1133,
        end_round=1182,
        window_size=100
    )
    
    logging.info("\n백테스팅 완료!")


if __name__ == "__main__":
    main()