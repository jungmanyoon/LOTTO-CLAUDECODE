"""
교차 검증 시스템
ML 모델의 성능을 과거 데이터로 검증하고
예측 정확도를 개선합니다.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging
from sklearn.model_selection import TimeSeriesSplit

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.logger import setup_logging
from src.core.db_manager import DatabaseManager
from src.ml.lstm_predictor import LSTMPredictor
from src.ml.ensemble_predictor import EnsemblePredictor

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class CrossValidationSystem:
    """교차 검증 시스템"""
    
    def __init__(self, db_manager: DatabaseManager, n_splits: int = 5):
        """
        Args:
            db_manager: 데이터베이스 매니저
            n_splits: 교차 검증 분할 수
        """
        self.db_manager = db_manager
        self.n_splits = n_splits
        self.validation_results = []
        
    def load_historical_data(self) -> pd.DataFrame:
        """과거 당첨 데이터 로드"""
        winning_numbers = self.db_manager.lottery_db.get_all_winning_numbers()
        
        data = []
        for round_num, numbers in winning_numbers:
            data.append({
                'round': round_num,
                'numbers': numbers,
                'sum': sum(numbers),
                'odd_count': sum(1 for n in numbers if n % 2 == 1),
                'consecutive': self._count_consecutive(numbers),
                'std_dev': np.std(numbers)
            })
            
        return pd.DataFrame(data)
    
    def _count_consecutive(self, numbers: List[int]) -> int:
        """연속 번호 개수 계산"""
        sorted_nums = sorted(numbers)
        count = 0
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                count += 1
        return count
    
    def evaluate_model(self, model_type: str = 'ensemble') -> Dict[str, float]:
        """모델 교차 검증"""
        logger.info(f"{model_type} 모델 교차 검증 시작...")
        
        # 데이터 로드
        df = self.load_historical_data()
        
        # 시계열 분할
        tscv = TimeSeriesSplit(n_splits=self.n_splits)
        
        results = {
            'accuracy_scores': [],
            'hit_rates': [],
            'pattern_scores': []
        }
        
        for fold, (train_idx, test_idx) in enumerate(tscv.split(df)):
            logger.info(f"Fold {fold + 1}/{self.n_splits} 처리 중...")
            
            # 훈련/테스트 데이터 분할
            train_data = df.iloc[train_idx]
            test_data = df.iloc[test_idx]
            
            # 모델 학습
            if model_type == 'lstm':
                model = LSTMPredictor(self.db_manager)
                train_numbers = [(row['round'], row['numbers']) for _, row in train_data.iterrows()]
                model.train(train_numbers)
            else:
                model = EnsemblePredictor(self.db_manager)
                train_numbers = [(row['round'], row['numbers']) for _, row in train_data.iterrows()]
                model.train(train_numbers)
            
            # 예측 및 평가
            fold_results = self._evaluate_fold(model, test_data)
            
            results['accuracy_scores'].append(fold_results['accuracy'])
            results['hit_rates'].append(fold_results['hit_rate'])
            results['pattern_scores'].append(fold_results['pattern_score'])
            
        # 평균 성능 계산
        avg_results = {
            'avg_accuracy': np.mean(results['accuracy_scores']),
            'avg_hit_rate': np.mean(results['hit_rates']),
            'avg_pattern_score': np.mean(results['pattern_scores']),
            'std_accuracy': np.std(results['accuracy_scores']),
            'std_hit_rate': np.std(results['hit_rates']),
            'std_pattern_score': np.std(results['pattern_scores'])
        }
        
        logger.info(f"교차 검증 완료: 평균 정확도 {avg_results['avg_accuracy']:.2%}")
        
        return avg_results
    
    def _evaluate_fold(self, model, test_data: pd.DataFrame) -> Dict[str, float]:
        """한 폴드의 성능 평가"""
        total_predictions = 0
        correct_predictions = 0
        total_hits = 0
        pattern_matches = 0
        
        for _, row in test_data.iterrows():
            actual_numbers = row['numbers']
            
            # 예측 수행
            train_numbers = [(r['round'], r['numbers']) 
                           for _, r in test_data[test_data['round'] < row['round']].iterrows()]
            
            if len(train_numbers) < 10:
                continue
                
            predictions = model.predict_next_numbers(train_numbers, num_predictions=5)
            
            # 평가
            for pred in predictions:
                pred_numbers = pred['numbers']
                total_predictions += 1
                
                # 적중 개수
                hits = len(set(pred_numbers) & set(actual_numbers))
                total_hits += hits
                
                # 3개 이상 적중 시 정확한 예측으로 간주
                if hits >= 3:
                    correct_predictions += 1
                
                # 패턴 일치 평가
                if self._check_pattern_match(pred_numbers, actual_numbers):
                    pattern_matches += 1
        
        return {
            'accuracy': correct_predictions / max(total_predictions, 1),
            'hit_rate': total_hits / (total_predictions * 6) if total_predictions > 0 else 0,
            'pattern_score': pattern_matches / max(total_predictions, 1)
        }
    
    def _check_pattern_match(self, pred_numbers: List[int], actual_numbers: List[int]) -> bool:
        """패턴 일치 여부 확인"""
        # 홀짝 패턴
        pred_odd = sum(1 for n in pred_numbers if n % 2 == 1)
        actual_odd = sum(1 for n in actual_numbers if n % 2 == 1)
        
        # 합계 범위
        pred_sum = sum(pred_numbers)
        actual_sum = sum(actual_numbers)
        
        # 패턴이 유사한지 확인
        odd_match = abs(pred_odd - actual_odd) <= 1
        sum_match = abs(pred_sum - actual_sum) <= 20
        
        return odd_match and sum_match
    
    def optimize_parameters(self) -> Dict[str, Any]:
        """모델 파라미터 최적화"""
        logger.info("모델 파라미터 최적화 시작...")
        
        best_params = {}
        best_score = 0
        
        # 파라미터 그리드
        param_grid = {
            'sequence_length': [5, 10, 15],
            'lstm_units': [64, 128, 256],
            'dropout_rate': [0.2, 0.3, 0.4],
            'learning_rate': [0.001, 0.01, 0.1]
        }
        
        # 그리드 서치 (간단한 버전)
        for seq_len in param_grid['sequence_length']:
            for units in param_grid['lstm_units']:
                for dropout in param_grid['dropout_rate']:
                    for lr in param_grid['learning_rate']:
                        params = {
                            'sequence_length': seq_len,
                            'lstm_units': units,
                            'dropout_rate': dropout,
                            'learning_rate': lr
                        }
                        
                        # 파라미터로 모델 평가
                        score = self._evaluate_with_params(params)
                        
                        if score > best_score:
                            best_score = score
                            best_params = params
                            
        logger.info(f"최적 파라미터 찾기 완료: {best_params}")
        return best_params
    
    def _evaluate_with_params(self, params: Dict[str, Any]) -> float:
        """특정 파라미터로 모델 평가"""
        # 간단한 평가 (실제로는 더 복잡한 평가 필요)
        return np.random.random()  # 임시 구현
    
    def generate_report(self) -> str:
        """교차 검증 보고서 생성"""
        report = []
        report.append("="*60)
        report.append("로또 예측 시스템 교차 검증 보고서")
        report.append("="*60)
        report.append(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # LSTM 평가
        lstm_results = self.evaluate_model('lstm')
        report.append("1. LSTM 모델 성능")
        report.append(f"   - 평균 정확도: {lstm_results['avg_accuracy']:.2%}")
        report.append(f"   - 평균 적중률: {lstm_results['avg_hit_rate']:.2%}")
        report.append(f"   - 패턴 일치율: {lstm_results['avg_pattern_score']:.2%}")
        report.append("")
        
        # Ensemble 평가
        ensemble_results = self.evaluate_model('ensemble')
        report.append("2. Ensemble 모델 성능")
        report.append(f"   - 평균 정확도: {ensemble_results['avg_accuracy']:.2%}")
        report.append(f"   - 평균 적중률: {ensemble_results['avg_hit_rate']:.2%}")
        report.append(f"   - 패턴 일치율: {ensemble_results['avg_pattern_score']:.2%}")
        report.append("")
        
        # 권장사항
        report.append("3. 권장사항")
        if ensemble_results['avg_accuracy'] > lstm_results['avg_accuracy']:
            report.append("   - Ensemble 모델이 더 높은 정확도를 보입니다.")
        else:
            report.append("   - LSTM 모델이 더 높은 정확도를 보입니다.")
            
        report.append("   - 예측 결과는 참고용으로만 사용하시기 바랍니다.")
        report.append("   - 로또는 무작위 추첨이므로 예측의 한계가 있습니다.")
        
        return "\n".join(report)


def main():
    """메인 실행 함수"""
    # DB 매니저 초기화
    from src.core.db_structure import DatabasePaths
    db_paths = DatabasePaths()
    db_manager = DatabaseManager(db_paths)
    
    # 교차 검증 시스템 초기화
    cv_system = CrossValidationSystem(db_manager)
    
    # 보고서 생성
    report = cv_system.generate_report()
    
    # 결과 저장
    output_dir = os.path.join(project_root, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, 'cross_validation_report.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(report)
    print(f"\n보고서가 저장되었습니다: {output_file}")


if __name__ == "__main__":
    main()