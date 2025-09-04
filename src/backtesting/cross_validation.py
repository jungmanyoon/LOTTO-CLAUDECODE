"""
백테스팅 교차 검증 시스템
과적합 방지를 위한 k-fold 교차 검증
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json
import os

class BacktestingCrossValidator:
    """백테스팅 교차 검증"""
    
    def __init__(self, n_folds: int = 5):
        """
        Args:
            n_folds: 교차 검증 폴드 수 (기본값: 5)
        """
        self.n_folds = n_folds
        self.validation_results = []
        logging.info(f"교차 검증 시스템 초기화 ({n_folds}-fold)")
    
    def split_data(self, data: List[List[int]], 
                   stratified: bool = False) -> List[Tuple[List, List]]:
        """데이터를 k-fold로 분할
        
        Args:
            data: 전체 로또 데이터
            stratified: 층화 샘플링 여부
            
        Returns:
            [(train_data, test_data), ...] 형태의 폴드 리스트
        """
        n_samples = len(data)
        fold_size = n_samples // self.n_folds
        
        folds = []
        
        for i in range(self.n_folds):
            # 테스트 세트 인덱스
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_folds - 1 else n_samples
            
            # 훈련 세트와 테스트 세트 분리
            test_indices = list(range(test_start, test_end))
            train_indices = list(range(0, test_start)) + list(range(test_end, n_samples))
            
            train_data = [data[idx] for idx in train_indices]
            test_data = [data[idx] for idx in test_indices]
            
            folds.append((train_data, test_data))
            
            logging.info(f"Fold {i+1}: 훈련 {len(train_data)}개, 테스트 {len(test_data)}개")
        
        return folds
    
    def validate_model(self, model_func, data: List[List[int]], 
                       model_name: str = "model") -> Dict:
        """모델 교차 검증
        
        Args:
            model_func: 모델 예측 함수 (train_data를 받아 predictions 반환)
            data: 전체 데이터
            model_name: 모델 이름
            
        Returns:
            검증 결과
        """
        logging.info(f"{model_name} 교차 검증 시작")
        
        folds = self.split_data(data)
        fold_results = []
        
        for fold_idx, (train_data, test_data) in enumerate(folds):
            logging.info(f"Fold {fold_idx + 1}/{self.n_folds} 검증 중...")
            
            # 모델 훈련 및 예측
            try:
                predictions = model_func(train_data)
                
                # 성능 평가
                fold_performance = self._evaluate_fold(
                    predictions, test_data, fold_idx
                )
                fold_results.append(fold_performance)
                
            except Exception as e:
                logging.error(f"Fold {fold_idx + 1} 검증 실패: {e}")
                fold_results.append({
                    'fold': fold_idx + 1,
                    'error': str(e),
                    'avg_matches': 0,
                    'match_distribution': {}
                })
        
        # 전체 결과 집계
        validation_summary = self._aggregate_results(fold_results, model_name)
        self.validation_results.append(validation_summary)
        
        return validation_summary
    
    def _evaluate_fold(self, predictions: List[List[int]], 
                       test_data: List[List[int]], 
                       fold_idx: int) -> Dict:
        """폴드 성능 평가"""
        
        total_matches = []
        match_distribution = {i: 0 for i in range(7)}
        
        # 예측 개수와 테스트 데이터 개수 맞추기
        min_len = min(len(predictions), len(test_data))
        
        for pred, actual in zip(predictions[:min_len], test_data[:min_len]):
            pred_set = set(pred[:6]) if len(pred) > 6 else set(pred)
            actual_set = set(actual[:6]) if len(actual) > 6 else set(actual)
            
            match_count = len(pred_set & actual_set)
            total_matches.append(match_count)
            match_distribution[match_count] += 1
        
        avg_matches = np.mean(total_matches) if total_matches else 0
        std_matches = np.std(total_matches) if total_matches else 0
        
        # 3개 이상 일치율
        three_plus = sum(match_distribution[i] for i in range(3, 7))
        three_plus_rate = three_plus / len(total_matches) * 100 if total_matches else 0
        
        return {
            'fold': fold_idx + 1,
            'n_samples': len(total_matches),
            'avg_matches': round(avg_matches, 3),
            'std_matches': round(std_matches, 3),
            'match_distribution': match_distribution,
            'three_plus_rate': round(three_plus_rate, 2),
            'max_matches': max(total_matches) if total_matches else 0
        }
    
    def _aggregate_results(self, fold_results: List[Dict], 
                          model_name: str) -> Dict:
        """폴드 결과 집계"""
        
        # 유효한 폴드만 필터링
        valid_folds = [f for f in fold_results if 'error' not in f]
        
        if not valid_folds:
            return {
                'model_name': model_name,
                'status': 'failed',
                'error': 'All folds failed'
            }
        
        # 평균 성능 계산
        avg_matches_per_fold = [f['avg_matches'] for f in valid_folds]
        three_plus_rates = [f['three_plus_rate'] for f in valid_folds]
        
        # 과적합 지표 계산 (폴드 간 성능 편차)
        overfitting_score = np.std(avg_matches_per_fold) if len(avg_matches_per_fold) > 1 else 0
        
        # 안정성 평가
        if overfitting_score < 0.1:
            stability = "매우 안정"
        elif overfitting_score < 0.2:
            stability = "안정"
        elif overfitting_score < 0.3:
            stability = "보통"
        elif overfitting_score < 0.5:
            stability = "불안정"
        else:
            stability = "매우 불안정"
        
        return {
            'model_name': model_name,
            'timestamp': datetime.now().isoformat(),
            'n_folds': self.n_folds,
            'valid_folds': len(valid_folds),
            'overall_performance': {
                'avg_matches': round(np.mean(avg_matches_per_fold), 3),
                'std_matches': round(np.std(avg_matches_per_fold), 3),
                'min_matches': round(min(avg_matches_per_fold), 3),
                'max_matches': round(max(avg_matches_per_fold), 3),
                'three_plus_rate': round(np.mean(three_plus_rates), 2)
            },
            'overfitting_metrics': {
                'score': round(overfitting_score, 4),
                'stability': stability,
                'fold_variance': round(np.var(avg_matches_per_fold), 4)
            },
            'fold_details': valid_folds
        }
    
    def compare_models(self, results: Optional[List[Dict]] = None) -> Dict:
        """모델 간 비교"""
        
        if results is None:
            results = self.validation_results
        
        if not results:
            return {'error': 'No validation results available'}
        
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'n_models': len(results),
            'models': []
        }
        
        for result in results:
            if result.get('status') == 'failed':
                continue
            
            model_summary = {
                'name': result['model_name'],
                'avg_matches': result['overall_performance']['avg_matches'],
                'three_plus_rate': result['overall_performance']['three_plus_rate'],
                'stability': result['overfitting_metrics']['stability'],
                'overfitting_score': result['overfitting_metrics']['score']
            }
            comparison['models'].append(model_summary)
        
        # 최고 성능 모델 찾기
        if comparison['models']:
            best_model = max(comparison['models'], 
                           key=lambda x: x['avg_matches'])
            most_stable = min(comparison['models'], 
                            key=lambda x: x['overfitting_score'])
            
            comparison['best_performance'] = best_model['name']
            comparison['most_stable'] = most_stable['name']
        
        return comparison
    
    def save_results(self, filename: str = None):
        """검증 결과 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"results/cross_validation_{timestamp}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        results = {
            'validation_results': self.validation_results,
            'comparison': self.compare_models()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logging.info(f"교차 검증 결과 저장: {filename}")
        
        # 요약 출력
        self.print_summary()
    
    def print_summary(self):
        """검증 결과 요약 출력"""
        
        comparison = self.compare_models()
        
        print("\n" + "="*60)
        print("교차 검증 결과 요약")
        print("="*60)
        
        for result in self.validation_results:
            if result.get('status') == 'failed':
                print(f"\n{result['model_name']}: 검증 실패")
                continue
            
            print(f"\n{result['model_name']}:")
            perf = result['overall_performance']
            overfit = result['overfitting_metrics']
            
            print(f"  평균 일치: {perf['avg_matches']}개")
            print(f"  3개+ 일치율: {perf['three_plus_rate']}%")
            print(f"  안정성: {overfit['stability']}")
            print(f"  과적합 점수: {overfit['score']:.4f}")
        
        if comparison.get('best_performance'):
            print(f"\n최고 성능: {comparison['best_performance']}")
            print(f"가장 안정적: {comparison['most_stable']}")
        
        print("="*60)