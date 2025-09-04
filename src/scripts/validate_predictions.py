"""
실전 예측 검증 도구
예측한 번호와 실제 당첨 번호를 비교하여 성능을 평가
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from src.core.prediction_tracker import PredictionTracker
from src.core.db_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class PredictionValidator:
    """예측 검증 시스템"""
    
    def __init__(self):
        self.tracker = PredictionTracker()
        self.db_manager = DatabaseManager()
        self.results_dir = "results/validation"
        os.makedirs(self.results_dir, exist_ok=True)
    
    def validate_round(self, round_num: int) -> Dict:
        """특정 회차 예측 검증
        
        Args:
            round_num: 검증할 회차 번호
            
        Returns:
            검증 결과
        """
        logging.info(f"\n{'='*60}")
        logging.info(f"{round_num}회차 예측 검증 시작")
        logging.info(f"{'='*60}")
        
        # 예측 조회
        predictions = self.tracker.get_predictions(round_num)
        if not predictions:
            logging.warning(f"{round_num}회차 예측이 없습니다.")
            return {'error': 'No predictions found'}
        
        # 실제 당첨 번호 조회
        actual_data = self.db_manager.get_numbers_by_round(round_num)
        if not actual_data:
            logging.warning(f"{round_num}회차 당첨 번호가 아직 발표되지 않았습니다.")
            return {'error': 'Actual numbers not available'}
        
        # numbers 문자열을 리스트로 변환 (튜플: 회차, 번호, 추첨일)
        actual_numbers = list(map(int, actual_data[1].split(',')))[:6]  # 인덱스 1이 번호, 보너스 제외
        actual_set = set(actual_numbers)
        
        validation_results = {
            'round_num': round_num,
            'actual_numbers': actual_numbers,
            'prediction_count': len(predictions),
            'validations': [],
            'summary': {
                'best_match': 0,
                'avg_match': 0,
                'success_count': 0,  # 3개 이상 일치
                'exceptional_count': 0  # 5개 이상 일치
            }
        }
        
        total_matches = 0
        
        for pred in predictions:
            pred_set = set(pred['numbers'][:6])
            matched = pred_set & actual_set
            match_count = len(matched)
            
            # 일치 개수별 분류
            is_success = match_count >= 3
            is_exceptional = match_count >= 5
            
            validation = {
                'set_number': pred['set_number'],
                'prediction': pred['numbers'],
                'source': pred['source'],
                'confidence': pred['confidence'],
                'match_count': match_count,
                'matched_numbers': sorted(list(matched)),
                'is_success': is_success,
                'is_exceptional': is_exceptional
            }
            
            validation_results['validations'].append(validation)
            
            # 통계 업데이트
            total_matches += match_count
            if match_count > validation_results['summary']['best_match']:
                validation_results['summary']['best_match'] = match_count
            if is_success:
                validation_results['summary']['success_count'] += 1
            if is_exceptional:
                validation_results['summary']['exceptional_count'] += 1
            
            # 로그 출력
            self._log_validation(pred, match_count, matched, is_success, is_exceptional)
        
        # 평균 계산
        validation_results['summary']['avg_match'] = round(
            total_matches / len(predictions), 2
        ) if predictions else 0
        
        validation_results['summary']['success_rate'] = round(
            validation_results['summary']['success_count'] / len(predictions) * 100, 1
        ) if predictions else 0
        
        # 결과 저장
        self._save_validation_results(validation_results)
        
        # 요약 출력
        self._print_summary(validation_results)
        
        return validation_results
    
    def _log_validation(self, pred: Dict, match_count: int, matched: set, 
                       is_success: bool, is_exceptional: bool):
        """검증 결과 로그"""
        if is_exceptional:
            logging.info(f"[EXCEPTIONAL] 세트 {pred['set_number']} ({pred['source']}): "
                        f"{match_count}개 일치! 번호: {sorted(matched)}")
        elif is_success:
            logging.info(f"[SUCCESS] 세트 {pred['set_number']} ({pred['source']}): "
                        f"{match_count}개 일치, 번호: {sorted(matched)}")
        else:
            logging.info(f"[NORMAL] 세트 {pred['set_number']} ({pred['source']}): "
                        f"{match_count}개 일치")
    
    def _save_validation_results(self, results: Dict):
        """검증 결과 저장"""
        filename = os.path.join(
            self.results_dir,
            f"validation_{results['round_num']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logging.info(f"검증 결과 저장: {filename}")
    
    def _print_summary(self, results: Dict):
        """검증 요약 출력"""
        summary = results['summary']
        
        print(f"\n{'='*60}")
        print(f"{results['round_num']}회차 검증 결과 요약")
        print(f"{'='*60}")
        print(f"실제 당첨 번호: {results['actual_numbers']}")
        print(f"검증한 예측: {results['prediction_count']}세트")
        print(f"\n성능 지표:")
        print(f"  최고 일치: {summary['best_match']}개")
        print(f"  평균 일치: {summary['avg_match']}개")
        print(f"  성공 예측: {summary['success_count']}개 "
              f"({summary['success_rate']}%)")
        
        if summary['exceptional_count'] > 0:
            print(f"  [EXCEPTIONAL] 5개 이상 일치: {summary['exceptional_count']}개!")
        
        print(f"\n세트별 결과:")
        for val in results['validations']:
            status = "[EXCEPTIONAL]" if val['is_exceptional'] else (
                "[SUCCESS]" if val['is_success'] else "[NORMAL]"
            )
            print(f"  {status} 세트 {val['set_number']} ({val['source']}): "
                  f"{val['match_count']}개 일치")
            if val['match_count'] > 0:
                print(f"    일치 번호: {val['matched_numbers']}")
        
        print(f"{'='*60}")
    
    def analyze_performance_trend(self, recent_rounds: int = 10) -> Dict:
        """최근 성능 추세 분석
        
        Args:
            recent_rounds: 분석할 최근 회차 수
            
        Returns:
            추세 분석 결과
        """
        logging.info(f"\n최근 {recent_rounds}회차 성능 추세 분석")
        
        # 데이터베이스에서 최근 회차 조회
        latest_round = self.db_manager.get_last_round()
        if not latest_round:
            return {'error': 'No data available'}
        
        trend_data = {
            'rounds_analyzed': 0,
            'total_predictions': 0,
            'total_successes': 0,
            'best_performance': None,
            'worst_performance': None,
            'avg_match_by_round': [],
            'success_rate_trend': []
        }
        
        rounds_with_predictions = 0
        
        for i in range(recent_rounds):
            round_num = latest_round - i
            if round_num < 1:
                break
            
            # 예측이 있는지 확인
            predictions = self.tracker.get_predictions(round_num)
            if not predictions:
                continue
            
            # 실제 번호가 있는지 확인
            actual = self.db_manager.get_numbers_by_round(round_num)
            if not actual:
                continue
            
            # 검증
            validation = self.validate_round(round_num)
            if 'error' not in validation:
                rounds_with_predictions += 1
                summary = validation['summary']
                
                trend_data['rounds_analyzed'] += 1
                trend_data['total_predictions'] += validation['prediction_count']
                trend_data['total_successes'] += summary['success_count']
                
                round_performance = {
                    'round': round_num,
                    'avg_match': summary['avg_match'],
                    'success_rate': summary['success_rate']
                }
                
                trend_data['avg_match_by_round'].append(round_performance)
                trend_data['success_rate_trend'].append(summary['success_rate'])
                
                # 최고/최저 성능 업데이트
                if (trend_data['best_performance'] is None or 
                    summary['avg_match'] > trend_data['best_performance']['avg_match']):
                    trend_data['best_performance'] = {
                        'round': round_num,
                        'avg_match': summary['avg_match'],
                        'best_match': summary['best_match']
                    }
                
                if (trend_data['worst_performance'] is None or 
                    summary['avg_match'] < trend_data['worst_performance']['avg_match']):
                    trend_data['worst_performance'] = {
                        'round': round_num,
                        'avg_match': summary['avg_match']
                    }
        
        # 전체 통계 계산
        if trend_data['total_predictions'] > 0:
            trend_data['overall_success_rate'] = round(
                trend_data['total_successes'] / trend_data['total_predictions'] * 100, 1
            )
        else:
            trend_data['overall_success_rate'] = 0
        
        # 추세 분석
        if len(trend_data['success_rate_trend']) >= 3:
            recent_avg = sum(trend_data['success_rate_trend'][:3]) / 3
            older_avg = sum(trend_data['success_rate_trend'][-3:]) / 3
            
            if recent_avg > older_avg * 1.1:
                trend_data['trend'] = 'improving'
            elif recent_avg < older_avg * 0.9:
                trend_data['trend'] = 'declining'
            else:
                trend_data['trend'] = 'stable'
        else:
            trend_data['trend'] = 'insufficient_data'
        
        # 결과 저장
        self._save_trend_analysis(trend_data)
        
        # 요약 출력
        self._print_trend_summary(trend_data)
        
        return trend_data
    
    def _save_trend_analysis(self, trend_data: Dict):
        """추세 분석 결과 저장"""
        filename = os.path.join(
            self.results_dir,
            f"trend_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(trend_data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"추세 분석 결과 저장: {filename}")
    
    def _print_trend_summary(self, trend_data: Dict):
        """추세 분석 요약 출력"""
        print(f"\n{'='*60}")
        print("성능 추세 분석 요약")
        print(f"{'='*60}")
        print(f"분석 회차: {trend_data['rounds_analyzed']}회")
        print(f"총 예측: {trend_data['total_predictions']}세트")
        print(f"성공 예측: {trend_data['total_successes']}세트")
        print(f"전체 성공률: {trend_data['overall_success_rate']}%")
        
        if trend_data['best_performance']:
            print(f"\n최고 성능:")
            print(f"  회차: {trend_data['best_performance']['round']}")
            print(f"  평균 일치: {trend_data['best_performance']['avg_match']}개")
            print(f"  최고 일치: {trend_data['best_performance']['best_match']}개")
        
        if trend_data['worst_performance']:
            print(f"\n최저 성능:")
            print(f"  회차: {trend_data['worst_performance']['round']}")
            print(f"  평균 일치: {trend_data['worst_performance']['avg_match']}개")
        
        print(f"\n성능 추세: {trend_data['trend'].upper()}")
        
        if trend_data['avg_match_by_round']:
            print(f"\n최근 회차별 평균 일치:")
            for perf in trend_data['avg_match_by_round'][:5]:
                print(f"  {perf['round']}회: {perf['avg_match']}개 "
                      f"(성공률 {perf['success_rate']}%)")
        
        print(f"{'='*60}")


def main():
    """메인 실행 함수"""
    validator = PredictionValidator()
    
    # 최신 회차 검증
    db_manager = DatabaseManager()
    latest_round = db_manager.get_last_round()
    
    if latest_round:
        print(f"최신 회차({latest_round}) 예측 검증")
        result = validator.validate_round(latest_round)
        
        if 'error' not in result:
            print("\n예측 검증 완료!")
        else:
            print(f"\n검증 실패: {result['error']}")
    
    # 성능 추세 분석
    print("\n최근 10회차 성능 추세 분석")
    trend = validator.analyze_performance_trend(10)
    
    if 'error' not in trend:
        print("\n추세 분석 완료!")


if __name__ == "__main__":
    main()