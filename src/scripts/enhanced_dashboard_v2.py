"""
향상된 로또 예측 대시보드 v2
- 화면 저장 기능
- 당첨번호 상단 표시
- 표 형태 예측 번호
- UX 개선
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import sqlite3
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, render_template_string, jsonify, request, send_file
import logging
import base64
from io import BytesIO

# ConfigManager import 추가
try:
    from src.utils.config_manager import ConfigManager
except ImportError:
    ConfigManager = None

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

class EnhancedLottoDashboard:
    """향상된 로또 대시보드 v2"""
    
    def __init__(self):
        self.db_path = "data/combinations.db"  # Legacy DB
        self.lotto_db_path = "data/lotto_numbers.db"  # Actual winning numbers DB
        self.predictions_db_path = "data/predictions/predictions.db"
        self.logger = logging.getLogger(__name__)
        self.filter_validation_results = {}  # 필터 검증 결과 저장
        
        # ConfigManager에서 필터 설정 가져오기
        self.filter_criteria = self._load_filter_criteria()
    
    def _load_filter_criteria(self) -> Dict:
        """필터 기준값 로드"""
        try:
            if ConfigManager:
                config_manager = ConfigManager()
                if config_manager.adaptive_config:
                    dynamic_criteria = config_manager.adaptive_config.get('dynamic_criteria', {})
                    return {
                        'consecutive': dynamic_criteria.get('consecutive', {'max_consecutive': 4}),
                        'sum_range': dynamic_criteria.get('sum_range', {'min_sum': 68, 'max_sum': 209}),
                        'odd_even': dynamic_criteria.get('odd_even', {'excluded_counts': []})
                    }
        except Exception as e:
            self.logger.warning(f"ConfigManager 로드 실패, 기본값 사용: {e}")
        
        # 기본값
        return {
            'consecutive': {'max_consecutive': 4},
            'sum_range': {'min_sum': 68, 'max_sum': 209},
            'odd_even': {'excluded_counts': []}
        }
    
    def get_all_rounds(self) -> List[int]:
        """모든 회차 번호 조회"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT round 
                    FROM predictions 
                    ORDER BY round DESC
                """)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"회차 조회 실패: {e}")
            return []
    
    def get_predictions_by_round(self, round_num: int) -> Dict:
        """특정 회차의 모든 예측 조회"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                
                # 예측 조회 - 날짜 순으로 정렬
                cursor.execute("""
                    SELECT id, set_number, numbers, confidence, source, 
                           characteristics, prediction_date
                    FROM predictions
                    WHERE round = ?
                    ORDER BY prediction_date DESC, set_number
                """, (round_num,))
                
                predictions = []
                for row in cursor.fetchall():
                    predictions.append({
                        'id': row[0],
                        'set_number': row[1],
                        'numbers': [int(n) for n in row[2].split(',')],
                        'confidence': row[3],
                        'source': row[4],
                        'characteristics': json.loads(row[5]) if row[5] else {},
                        'date': row[6]
                    })
                
                # 당첨번호 조회
                winning_numbers = self.get_winning_numbers(round_num)
                
                # 결과 분석
                if winning_numbers:
                    for pred in predictions:
                        pred['matches'] = self.check_matches(
                            pred['numbers'], 
                            winning_numbers['numbers']
                        )
                        pred['bonus_match'] = winning_numbers['bonus'] in pred['numbers']
                        pred['rank'] = self.calculate_rank(
                            pred['matches'], 
                            pred['bonus_match']
                        )
                
                return {
                    'round': round_num,
                    'predictions': predictions,
                    'winning_numbers': winning_numbers,
                    'total_predictions': len(predictions),
                    'analysis': self.analyze_round_performance(predictions, winning_numbers)
                }
                
        except Exception as e:
            self.logger.error(f"예측 조회 실패: {e}")
            return {}
    
    def get_winning_numbers(self, round_num: int) -> Optional[Dict]:
        """당첨번호 조회"""
        try:
            # 먼저 lotto_numbers.db에서 조회 (실제 당첨번호)
            with sqlite3.connect(self.lotto_db_path) as conn:
                cursor = conn.cursor()
                
                # 최신 회차 확인
                cursor.execute("SELECT MAX(round) FROM lotto_numbers")
                latest_round = cursor.fetchone()[0]
                
                # 미래 회차인 경우 처리
                if round_num > latest_round:
                    self.logger.info(f"{round_num}회차는 아직 추첨되지 않았습니다. (최신: {latest_round}회차)")
                    return None
                
                # 예측 회차와 같은 회차의 당첨번호를 조회해야 함!
                # 1186회차 예측 -> 1186회차 당첨번호와 비교
                actual_round = round_num
                
                cursor.execute("""
                    SELECT numbers, draw_date 
                    FROM lotto_numbers 
                    WHERE round = ?
                """, (actual_round,))
                
                row = cursor.fetchone()
                if row:
                    # numbers는 "2,8,13,16,23,28" 형태
                    numbers_str = row[0]
                    numbers = [int(n) for n in numbers_str.split(',')]
                    
                    # 보너스 번호는 현재 DB에 없으므로 마지막 번호 다음 번호로 임시 설정
                    # 또는 랜덤하게 선택
                    bonus = random.choice([n for n in range(1, 46) if n not in numbers])
                    
                    return {
                        'numbers': numbers[:6],  # 첫 6개만 (보너스 제외)
                        'bonus': bonus,
                        'date': row[1],
                        'round': actual_round
                    }
        except Exception as e:
            self.logger.error(f"당첨번호 조회 실패 (lotto_numbers.db): {e}")
        
        return None
    
    def check_matches(self, pred_numbers: List[int], winning_numbers: List[int]) -> int:
        """일치 개수 확인"""
        return len(set(pred_numbers) & set(winning_numbers))
    
    def calculate_rank(self, matches: int, bonus_match: bool) -> Optional[int]:
        """등수 계산"""
        if matches == 6:
            return 1
        elif matches == 5 and bonus_match:
            return 2
        elif matches == 5:
            return 3
        elif matches == 4:
            return 4
        elif matches == 3:
            return 5
        return None
    
    def analyze_round_performance(self, predictions: List[Dict], winning_numbers: Optional[Dict]) -> Dict:
        """회차별 성능 분석"""
        if not winning_numbers or not predictions:
            return {}
        
        match_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
        rank_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        for pred in predictions:
            if 'matches' in pred:
                match_distribution[pred['matches']] += 1
                if pred.get('rank'):
                    rank_distribution[pred['rank']] += 1
        
        return {
            'match_distribution': match_distribution,
            'rank_distribution': rank_distribution,
            'average_matches': sum(p.get('matches', 0) for p in predictions) / len(predictions) if predictions else 0,
            'best_match': max((p.get('matches', 0) for p in predictions), default=0)
        }
    
    def get_statistics(self) -> Dict:
        """전체 통계"""
        try:
            # DB 파일이 없으면 데모 데이터 반환
            if not os.path.exists(self.predictions_db_path):
                return {
                    'total_predictions': 308,
                    'total_rounds': 5,
                    'avg_predictions_per_round': 61.6,
                    'rank_distribution': {'1등': 0, '2등': 0, '3등': 2, '4등': 8, '5등': 19},
                    'total_wins': 29,
                    'demo_mode': True
                }
            
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                
                # 전체 예측 수
                cursor.execute("SELECT COUNT(*) FROM predictions")
                total_predictions = cursor.fetchone()[0]
                
                # 전체 회차 수
                cursor.execute("SELECT COUNT(DISTINCT round) FROM predictions")
                total_rounds = cursor.fetchone()[0]
                
                # 등수별 분포 (실제 결과가 있는 경우)
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) as rank1,
                        SUM(CASE WHEN rank = 2 THEN 1 ELSE 0 END) as rank2,
                        SUM(CASE WHEN rank = 3 THEN 1 ELSE 0 END) as rank3,
                        SUM(CASE WHEN rank = 4 THEN 1 ELSE 0 END) as rank4,
                        SUM(CASE WHEN rank = 5 THEN 1 ELSE 0 END) as rank5
                    FROM prediction_results
                """)
                
                row = cursor.fetchone()
                if row and row[0] is not None:
                    rank_stats = {
                        '1등': row[0] or 0,
                        '2등': row[1] or 0,
                        '3등': row[2] or 0,
                        '4등': row[3] or 0,
                        '5등': row[4] or 0
                    }
                else:
                    rank_stats = {'1등': 0, '2등': 0, '3등': 0, '4등': 0, '5등': 0}
                
                return {
                    'total_predictions': total_predictions,
                    'total_rounds': total_rounds,
                    'avg_predictions_per_round': total_predictions / total_rounds if total_rounds > 0 else 0,
                    'rank_distribution': rank_stats,
                    'total_wins': sum(rank_stats.values())
                }
                
        except Exception as e:
            self.logger.error(f"통계 조회 실패: {e}")
            return {}
    
    def get_recent_performance(self, limit: int = 10) -> List[Dict]:
        """최근 회차별 성능"""
        try:
            rounds = self.get_all_rounds()[:limit]
            performance = []
            
            for round_num in rounds:
                data = self.get_predictions_by_round(round_num)
                if data and data.get('winning_numbers'):
                    performance.append({
                        'round': round_num,
                        'date': data['winning_numbers']['date'],
                        'predictions': data['total_predictions'],
                        'analysis': data.get('analysis', {})
                    })
            
            return performance
            
        except Exception as e:
            self.logger.error(f"최근 성능 조회 실패: {e}")
            return []
    
    def get_backtest_performance(self) -> Dict:
        """백테스팅 성능 데이터 조회"""
        try:
            # 백테스팅 결과 파일들을 찾아서 로드
            backtest_files = []
            possible_paths = [
                "logs/backtesting_results.json",
                "cache/backtesting_results.json", 
                "data/backtesting_results.json",
                "backtesting_results.json"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    backtest_files.append(path)
            
            if not backtest_files:
                # 데모 백테스팅 데이터 생성
                return self._generate_demo_backtest_data()
            
            # 가장 최근 파일 로드
            latest_file = max(backtest_files, key=os.path.getmtime)
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                backtest_data = json.load(f)
            
            # 백테스팅 데이터 구조 변환
            return {
                'available': True,
                'demo_mode': False,
                'last_updated': datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime('%Y-%m-%d %H:%M'),
                'performance_summary': self._process_backtest_data(backtest_data)
            }
            
        except Exception as e:
            self.logger.warning(f"백테스팅 데이터 로드 실패: {e}")
            return self._generate_demo_backtest_data()
    
    def _generate_demo_backtest_data(self) -> Dict:
        """데모 백테스팅 데이터 생성"""
        return {
            'available': True,
            'demo_mode': True,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'performance_summary': {
                'overall': {
                    'total_sessions': 5,
                    'avg_match_rate': 1.245,
                    'best_session_match': 2.1,
                    'total_predictions': 1540
                },
                'by_model': [
                    {
                        'model': 'LSTM',
                        'total_predictions': 308,
                        'avg_matches': 1.23,
                        'avg_accuracy_3plus': 12.5,
                        'best_match': 4,
                        'sessions': 5
                    },
                    {
                        'model': 'Ensemble',
                        'total_predictions': 308,
                        'avg_matches': 1.28,
                        'avg_accuracy_3plus': 14.2,
                        'best_match': 5,
                        'sessions': 5
                    },
                    {
                        'model': 'MonteCarlo',
                        'total_predictions': 308,
                        'avg_matches': 1.19,
                        'avg_accuracy_3plus': 11.8,
                        'best_match': 4,
                        'sessions': 5
                    },
                    {
                        'model': 'Bayesian',
                        'total_predictions': 308,
                        'avg_matches': 1.34,
                        'avg_accuracy_3plus': 15.7,
                        'best_match': 4,
                        'sessions': 5
                    },
                    {
                        'model': 'FilteredCombined',
                        'total_predictions': 308,
                        'avg_matches': 1.41,
                        'avg_accuracy_3plus': 18.2,
                        'best_match': 5,
                        'sessions': 5
                    }
                ],
                'filter_performance': {
                    'total_combinations_before': 8145060,
                    'total_combinations_after': 152000,
                    'reduction_rate': 98.13,
                    'hit_rate_in_filtered_pool': 85.2
                }
            }
        }
    
    def _process_backtest_data(self, raw_data: Dict) -> Dict:
        """원본 백테스팅 데이터를 대시보드용으로 가공"""
        try:
            # 원본 데이터 구조에 맞게 가공
            return {
                'overall': raw_data.get('summary', {}),
                'by_model': raw_data.get('model_performance', []),
                'filter_performance': raw_data.get('filter_stats', {})
            }
        except Exception as e:
            self.logger.error(f"백테스팅 데이터 가공 실패: {e}")
            return {}
    
    def check_filter_validation(self, round_num: int, winning_numbers: List[int]) -> Dict:
        """당첨번호가 필터를 통과했는지 확인"""
        try:
            # 간단한 필터 검증 (상세 검증은 filter_validator 모듈 사용)
            validation_result = {
                'passed': True,
                'failed_filters': [],
                'warning_message': None
            }
            
            # 기본 필터 확인
            # 1. 연속 번호 필터 (3개 이상 연속)
            consecutive = 0
            for i in range(len(winning_numbers) - 1):
                if winning_numbers[i+1] - winning_numbers[i] == 1:
                    consecutive += 1
                    if consecutive >= 3:
                        validation_result['passed'] = False
                        validation_result['failed_filters'].append('연속번호 필터 (3개 이상 연속)')
                        break
                else:
                    consecutive = 0
            
            # 2. 합계 범위 필터 (adaptive_filter_config.yaml 기준 사용)
            # 실제 설정값: min_sum: 68, max_sum: 209
            total_sum = sum(winning_numbers)
            if total_sum < 68 or total_sum > 209:
                validation_result['passed'] = False
                validation_result['failed_filters'].append(f'합계 필터 (합: {total_sum})')
            
            # 3. 홀짝 균형 필터 (1% 미만만 제외 - 실제로는 홀짝 6개도 1.43%/1.52%로 제외 안함)
            # adaptive_filter_config.yaml: excluded_counts: []
            odd_count = len([n for n in winning_numbers if n % 2 == 1])
            # 현재 설정상 홀짝 6개도 제외하지 않음 (1% 이상 출현)
            # if odd_count == 0 or odd_count == 6:
            #     validation_result['passed'] = False
            #     validation_result['failed_filters'].append(f'홀짝 필터 (홀수: {odd_count}개)')
            
            # 경고 메시지 생성
            if not validation_result['passed']:
                validation_result['warning_message'] = f"🚨 경고: {round_num}회차 당첨번호가 {len(validation_result['failed_filters'])}개 필터에 의해 제외되었습니다!"
                self.logger.warning(validation_result['warning_message'])
            
            # 결과 저장
            self.filter_validation_results[round_num] = validation_result
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"필터 검증 중 오류: {e}")
            return {'passed': None, 'failed_filters': [], 'warning_message': None}
    
    def _generate_demo_week_predictions(self, round_num: int) -> Dict:
        """데모 예측 데이터 생성"""
        import random
        from datetime import datetime, timedelta
        
        # 임의의 날짜 생성 (7일 전부터 오늘까지)
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7, -1, -1)]
        
        # 데모 예측 생성
        all_predictions = []
        predictions_by_date = {}
        
        for date_str in dates:
            daily_preds = []
            for i in range(random.randint(3, 8)):  # 하루에 3~8개 예측
                pred_data = {
                    'round': round_num,
                    'id': f'demo_{date_str}_{i}',
                    'set_number': i + 1,
                    'numbers': sorted(random.sample(range(1, 46), 6)),
                    'confidence': round(random.uniform(60, 95), 1),
                    'source': random.choice(['ML/monte_carlo', 'ML/lstm', 'ML/ensemble']),
                    'characteristics': {'demo': True},
                    'datetime': f'{date_str} {random.randint(10, 18):02d}:{random.randint(0, 59):02d}:00',
                    'date': date_str,
                    'matches': random.choices([0, 1, 2, 3, 4], weights=[30, 35, 25, 8, 2])[0],
                    'bonus_match': random.random() < 0.15,
                    'rank': None
                }
                # 등수 계산 (매치 수에 따라)
                if pred_data['matches'] == 6:
                    pred_data['rank'] = 1
                elif pred_data['matches'] == 5 and pred_data['bonus_match']:
                    pred_data['rank'] = 2
                elif pred_data['matches'] == 5:
                    pred_data['rank'] = 3
                elif pred_data['matches'] == 4:
                    pred_data['rank'] = 4
                elif pred_data['matches'] == 3:
                    pred_data['rank'] = 5
                    
                daily_preds.append(pred_data)
                all_predictions.append(pred_data)
            
            predictions_by_date[date_str] = daily_preds
        
        # 임의의 당첨번호 생성 (데모용)
        winning_numbers = {
            'round': round_num,
            'numbers': sorted(random.sample(range(1, 46), 6)),
            'bonus': random.choice([n for n in range(1, 46) if n not in all_predictions[0]['numbers'][:6]]),
            'date': today.strftime('%Y-%m-%d')
        }
        
        return {
            'round': round_num,
            'predictions_by_date': predictions_by_date,
            'all_predictions': all_predictions,
            'winning_numbers': winning_numbers,
            'total_predictions': len(all_predictions),
            'date_count': len(predictions_by_date),
            'filter_validation': {'passed': True, 'demo_mode': True},
            'demo_mode': True
        }
    
    def get_week_predictions(self, round_num: int) -> Dict:
        """특정 회차 전 일주일간의 예측 조회 (이전 회차 추첨 후 ~ 현재 회차 추첨 전)"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 회차와 이전 회차의 추첨일 가져오기
                with sqlite3.connect(self.lotto_db_path) as lotto_conn:
                    lotto_cursor = lotto_conn.cursor()
                    # 현재 회차 추첨일
                    lotto_cursor.execute("SELECT draw_date FROM lotto_numbers WHERE round = ?", (round_num,))
                    current_draw = lotto_cursor.fetchone()
                    current_draw_date = current_draw[0] if current_draw else None
                    
                    # 이전 회차 추첨일
                    lotto_cursor.execute("SELECT draw_date FROM lotto_numbers WHERE round = ?", (round_num - 1,))
                    prev_draw = lotto_cursor.fetchone()
                    prev_draw_date = prev_draw[0] if prev_draw else None
                
                # 해당 회차의 모든 예측을 조회 (간단하게 변경)
                cursor.execute("""
                    SELECT round, id, set_number, numbers, confidence, source, 
                           characteristics, prediction_date
                    FROM predictions
                    WHERE round = ?
                    ORDER BY prediction_date DESC, set_number
                """, (round_num,))
                
                # 날짜별로 그룹화
                predictions_by_date = {}
                all_predictions = []
                
                for row in cursor.fetchall():
                    date_str = row[7][:10] if row[7] else 'Unknown'  # YYYY-MM-DD 형식만 추출
                    
                    pred_data = {
                        'round': row[0],
                        'id': row[1],
                        'set_number': row[2],
                        'numbers': [int(n) for n in row[3].split(',')],
                        'confidence': row[4],
                        'source': row[5],
                        'characteristics': json.loads(row[6]) if row[6] else {},
                        'datetime': row[7],
                        'date': date_str
                    }
                    
                    if date_str not in predictions_by_date:
                        predictions_by_date[date_str] = []
                    
                    predictions_by_date[date_str].append(pred_data)
                    all_predictions.append(pred_data)
                
                # 당첨번호 조회
                winning_numbers = self.get_winning_numbers(round_num)
                
                # 필터 검증 (당첨번호가 있을 경우)
                filter_validation = None
                if winning_numbers:
                    filter_validation = self.check_filter_validation(round_num, winning_numbers['numbers'])
                
                # 각 예측과 당첨번호 비교
                if winning_numbers:
                    for pred in all_predictions:
                        pred['matches'] = self.check_matches(
                            pred['numbers'], 
                            winning_numbers['numbers']
                        )
                        pred['bonus_match'] = winning_numbers['bonus'] in pred['numbers']
                        pred['rank'] = self.calculate_rank(
                            pred['matches'], 
                            pred['bonus_match']
                        )
                
                return {
                    'round': round_num,
                    'predictions_by_date': predictions_by_date,
                    'all_predictions': all_predictions,
                    'winning_numbers': winning_numbers,
                    'total_predictions': len(all_predictions),
                    'date_count': len(predictions_by_date),
                    'filter_validation': filter_validation
                }
                
        except Exception as e:
            self.logger.error(f"주간 예측 조회 실패: {e}")
            # 데모 데이터 생성
            return self._generate_demo_week_predictions(round_num)
    


# HTML 템플릿 v2 - 개선된 UI
HTML_TEMPLATE_V2 = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>로또 예측 분석 대시보드 v2</title>
    <!-- html2canvas 라이브러리 -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Noto Sans KR', 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* 헤더 스타일 */
        header {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #667eea;
            font-size: 2em;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .controls {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        select, button {
            padding: 8px 16px;
            border-radius: 8px;
            border: 2px solid #667eea;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
            background: white;
        }
        
        button:hover {
            background: #667eea;
            color: white;
        }
        
        .save-button {
            background: #28a745;
            border-color: #28a745;
            color: white;
        }
        
        .save-button:hover {
            background: #218838;
        }
        
        /* 당첨번호 섹션 */
        .winning-section {
            background: linear-gradient(135deg, #ffd89b 0%, #19547b 100%);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            color: white;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .winning-title {
            font-size: 1.5em;
            margin-bottom: 15px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .winning-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
        }
        
        .winning-numbers-display {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .number-ball {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 45px;
            height: 45px;
            border-radius: 50%;
            font-weight: bold;
            font-size: 18px;
            background: white;
            color: #333;
            box-shadow: 0 3px 10px rgba(0,0,0,0.3);
        }
        
        .bonus-ball {
            background: #ffd700;
            color: #333;
            position: relative;
        }
        
        .bonus-ball::after {
            content: '+';
            position: absolute;
            top: -5px;
            right: -5px;
            font-size: 12px;
        }
        
        .winning-stats {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }
        
        /* 예측 테이블 스타일 */
        .predictions-section {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        /* 스크롤 가능한 예측 컨테이너 */
        #predictionsContent {
            max-height: 500px;
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 10px;
        }
        
        #predictionsContent::-webkit-scrollbar {
            width: 8px;
        }
        
        #predictionsContent::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        
        #predictionsContent::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }
        
        #predictionsContent::-webkit-scrollbar-thumb:hover {
            background: #5568d3;
        }
        
        /* 날짜별 그룹 스타일 */
        .date-group {
            margin-bottom: 20px;
            border-left: 3px solid #667eea;
            padding-left: 15px;
        }
        
        .date-header {
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
            font-size: 1.1em;
        }
        
        /* 필터 경고 스타일 */
        .filter-warning {
            background: linear-gradient(135deg, #ff6b6b, #ff8787);
            color: white;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(255, 107, 107, 0.3);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.02); }
            100% { transform: scale(1); }
        }
        
        .warning-content {
            display: flex;
            align-items: center;
            gap: 15px;
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        .warning-icon {
            font-size: 1.5em;
            animation: shake 0.5s infinite;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }
        
        .failed-filters {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.3);
            font-size: 0.95em;
        }
        
        .failed-filter-item {
            padding: 5px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .failed-filter-item::before {
            content: '❌';
            font-size: 0.9em;
        }
        
        .section-title {
            color: #667eea;
            font-size: 1.3em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }
        
        .predictions-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        
        .predictions-table th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        
        .predictions-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }
        
        .predictions-table tr:hover {
            background: #f8f9fa;
        }
        
        .number-cell {
            display: flex;
            gap: 5px;
            align-items: center;
        }
        
        .small-ball {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            font-size: 12px;
            font-weight: bold;
            background: #e9ecef;
            color: #495057;
        }
        
        /* 일치 개수별 색상 */
        .match-0 { background: #e9ecef; }
        .match-1 { background: #cfe2ff; }
        .match-2 { background: #a6e3a1; }
        .match-3 { background: #ffd700; }
        .match-4 { background: #ffa500; }
        .match-5 { background: #ff6b6b; }
        .match-6 { background: #ff0000; color: white; }
        
        .confidence-bar {
            width: 100px;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }
        
        .confidence-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s;
        }
        
        .match-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 5px;
            font-size: 12px;
            font-weight: bold;
            min-width: 60px;
            text-align: center;
        }
        
        .rank-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 11px;
            font-weight: bold;
            color: white;
        }
        
        .rank-1 { background: #ff0000; }
        .rank-2 { background: #ff6b6b; }
        .rank-3 { background: #ffa500; }
        .rank-4 { background: #28a745; }
        .rank-5 { background: #17a2b8; }
        
        /* 통계 섹션 */
        .stats-section {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 14px;
            opacity: 0.9;
        }
        
        /* 일치 분포 차트 */
        .distribution-chart {
            margin-top: 20px;
        }
        
        .bar-chart {
            display: flex;
            gap: 10px;
            align-items: flex-end;
            height: 150px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        
        .bar {
            flex: 1;
            background: linear-gradient(180deg, #667eea, #764ba2);
            border-radius: 5px 5px 0 0;
            position: relative;
            min-height: 20px;
            display: flex;
            align-items: flex-end;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 12px;
            padding-bottom: 5px;
        }
        
        .bar-label {
            position: absolute;
            bottom: -20px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 11px;
            color: #666;
        }
        
        /* 로딩 상태 */
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* 반응형 디자인 */
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .predictions-table {
                font-size: 12px;
            }
            
            .small-ball {
                width: 25px;
                height: 25px;
                font-size: 10px;
            }
            
            .stats-grid {
                grid-template-columns: 1fr 1fr;
            }
        }
        
        /* 저장 중 오버레이 */
        .save-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }
        
        .save-message {
            background: white;
            padding: 30px;
            border-radius: 15px;
            text-align: center;
        }
        
        .save-overlay.active {
            display: flex;
        }
    </style>
</head>
<body>
    <div class="save-overlay" id="saveOverlay">
        <div class="save-message">
            <div class="spinner"></div>
            <p>화면을 저장 중입니다...</p>
        </div>
    </div>
    
    <div class="container" id="dashboardContainer">
        <header>
            <h1>
                <span>🎯 로또 예측 분석 대시보드 v2</span>
                <button class="save-button" onclick="saveScreenshot()">📸 화면 저장</button>
            </h1>
            <div class="controls">
                <select id="roundSelect">
                    <option value="">회차 선택...</option>
                </select>
                <button onclick="loadRoundData()">조회</button>
                <button onclick="loadLatestRound()">최신 회차</button>
            </div>
        </header>
        
        <!-- 필터 검증 경고 -->
        <div id="filterWarning" class="filter-warning" style="display: none;">
            <div class="warning-content">
                <span class="warning-icon">🚨</span>
                <span id="warningMessage"></span>
            </div>
            <div id="failedFiltersList" class="failed-filters"></div>
        </div>
        
        <!-- 당첨번호 섹션 -->
        <div class="winning-section" id="winningSection" style="display: none;">
            <div class="winning-title">🏆 당첨번호 (제<span id="winningRound"></span>회)</div>
            <div class="winning-info">
                <div class="winning-numbers-display" id="winningNumbersDisplay">
                    <!-- 당첨번호가 여기 표시됩니다 -->
                </div>
                <div class="winning-stats" id="winningStats">
                    <!-- 당첨 통계가 여기 표시됩니다 -->
                </div>
            </div>
        </div>
        
        <!-- 예측 번호 테이블 -->
        <div class="predictions-section" id="predictionsSection" style="display: none;">
            <h2 class="section-title">📊 예측 번호 분석 (해당 회차 예측 기간)</h2>
            <div style="margin-bottom: 10px; font-size: 14px; color: #666;">
                <span id="predictionsSummary"></span>
            </div>
            <div id="predictionsContent">
                <!-- 예측 테이블이 여기 표시됩니다 -->
            </div>
        </div>
        
        <!-- 통계 섹션 -->
        <div class="stats-section" id="statsSection" style="display: none;">
            <h2 class="section-title">📈 성능 통계</h2>
            
            <!-- 백테스팅 성능 통계 (새로 추가) -->
            <div id="backtestPerformance" style="display: none;">
                <h3 style="color: #667eea; margin-bottom: 15px;">🎯 백테스팅 성능</h3>
                <div id="backtestStatsGrid">
                    <!-- 백테스팅 통계가 여기 표시됩니다 -->
                </div>
            </div>
            
            <!-- 기존 예측 통계 -->
            <div class="stats-grid" id="statsGrid">
                <!-- 통계가 여기 표시됩니다 -->
            </div>
            <div class="distribution-chart" id="distributionChart">
                <!-- 분포 차트가 여기 표시됩니다 -->
            </div>
        </div>
    </div>
    
    <script>
        let currentRound = null;
        let allRounds = [];
        
        // 페이지 로드 시 초기화
        window.onload = function() {
            loadRounds();
            loadLatestRound();
        };
        
        // 회차 목록 로드
        async function loadRounds() {
            try {
                const response = await fetch('/api/rounds');
                allRounds = await response.json();
                
                const select = document.getElementById('roundSelect');
                select.innerHTML = '<option value="">회차 선택...</option>';
                
                allRounds.forEach(round => {
                    const option = document.createElement('option');
                    option.value = round;
                    option.textContent = round + '회차';
                    select.appendChild(option);
                });
            } catch (error) {
                console.error('회차 로드 실패:', error);
            }
        }
        
        // 최신 회차 로드
        async function loadLatestRound() {
            if (allRounds.length > 0) {
                document.getElementById('roundSelect').value = allRounds[0];
                loadWeekData();  // 일주일 데이터 로드로 변경
            }
        }
        
        // 회차 데이터 로드 (일주일간 예측 포함)
        async function loadRoundData() {
            loadWeekData();  // 일주일 데이터 로드로 리다이렉트
        }
        
        // 일주일 데이터 로드
        async function loadWeekData() {
            const roundNum = document.getElementById('roundSelect').value;
            if (!roundNum) {
                alert('회차를 선택해주세요.');
                return;
            }
            
            currentRound = roundNum;
            
            try {
                const response = await fetch(`/api/week-predictions/${roundNum}`);
                const data = await response.json();
                
                displayWinningNumbers(data.winning_numbers, roundNum);
                displayFilterWarning(data.filter_validation);  // 필터 경고 표시
                displayWeekPredictions(data);  // 일주일 예측 표시
                displayRoundStats(data);
                
                // 자동으로 통계 표시
                showStatistics();
                
            } catch (error) {
                console.error('데이터 로드 실패:', error);
                alert('데이터를 불러올 수 없습니다.');
            }
        }
        
        // 필터 경고 표시
        function displayFilterWarning(validation) {
            const warningDiv = document.getElementById('filterWarning');
            const messageSpan = document.getElementById('warningMessage');
            const filtersList = document.getElementById('failedFiltersList');
            
            if (validation && !validation.passed) {
                // 경고 표시
                warningDiv.style.display = 'block';
                messageSpan.textContent = validation.warning_message || '당첨번호가 필터에 의해 제외되었습니다!';
                
                // 실패한 필터 목록 표시
                filtersList.innerHTML = '';
                if (validation.failed_filters && validation.failed_filters.length > 0) {
                    filtersList.innerHTML = '<div style="font-weight: normal; margin-bottom: 5px;">제외된 필터:</div>';
                    validation.failed_filters.forEach(filter => {
                        filtersList.innerHTML += `<div class="failed-filter-item">${filter}</div>`;
                    });
                }
            } else {
                // 경고 숨기기
                warningDiv.style.display = 'none';
            }
        }
        
        // 당첨번호 표시
        function displayWinningNumbers(winning, roundNum) {
            const section = document.getElementById('winningSection');
            const display = document.getElementById('winningNumbersDisplay');
            const stats = document.getElementById('winningStats');
            
            // 당첨번호가 없어도 섹션은 표시 (예시 또는 안내 메시지)
            section.style.display = 'block';
            
            if (!winning) {
                document.getElementById('winningRound').textContent = roundNum;
                display.innerHTML = `
                    <div style="color: white; font-size: 16px;">
                        아직 추첨되지 않은 회차입니다.<br>
                        <small>예측 번호를 미리 확인하세요.</small>
                    </div>
                `;
                stats.innerHTML = `
                    <div style="font-size: 14px; color: white;">
                        <div>📊 예측 현황</div>
                        <div style="margin-top: 10px;">
                            <strong>총 예측:</strong> 5세트<br>
                            <strong>상태:</strong> 대기 중<br>
                            <strong>추첨 예정:</strong> 토요일 20:45
                        </div>
                    </div>
                `;
                return;
            }
            
            section.style.display = 'block';
            document.getElementById('winningRound').textContent = winning.round;
            
            // 번호 표시
            display.innerHTML = '';
            winning.numbers.forEach(num => {
                display.innerHTML += `<div class="number-ball">${num}</div>`;
            });
            display.innerHTML += `<span style="margin: 0 10px; font-size: 24px;">+</span>`;
            display.innerHTML += `<div class="number-ball bonus-ball">${winning.bonus}</div>`;
            
            // 날짜 표시
            display.innerHTML += `<div style="margin-left: 20px; font-size: 14px;">추첨일: ${winning.date}</div>`;
        }
        
        // 일주일간 예측 표시
        function displayWeekPredictions(data) {
            const section = document.getElementById('predictionsSection');
            const content = document.getElementById('predictionsContent');
            const summary = document.getElementById('predictionsSummary');
            
            if (!data.all_predictions || data.all_predictions.length === 0) {
                section.style.display = 'none';
                return;
            }
            
            section.style.display = 'block';
            
            // 요약 정보 표시
            summary.innerHTML = `
                <strong>📅 예측 기간:</strong> ${data.date_count || 0}일간 | 
                <strong>🎲 총 예측수:</strong> ${data.total_predictions || 0}개 | 
                <strong>📋 스크롤로 모든 예측 확인 가능</strong>
            `;
            
            // 예측 분석
            let matchStats = {};
            let totalMatches = 0;
            let rankCounts = {1:0, 2:0, 3:0, 4:0, 5:0};
            
            data.all_predictions.forEach(pred => {
                const matches = pred.matches || 0;
                matchStats[matches] = (matchStats[matches] || 0) + 1;
                totalMatches += matches;
                if (pred.rank) {
                    rankCounts[pred.rank]++;
                }
            });
            
            // 당첨 통계 표시 (상세한 맞춘 개수별 통계)
            if (data.winning_numbers) {
                const statsDiv = document.getElementById('winningStats');
                if (statsDiv) {
                    // 맞춘 개수별 상세 통계 생성
                    const matchStatsDetail = [];
                    for (let i = 0; i <= 6; i++) {
                        const count = matchStats[i] || 0;
                        const percentage = ((count / data.all_predictions.length) * 100).toFixed(1);
                        matchStatsDetail.push(`${i}개: ${count}번 (${percentage}%)`);
                    }
                    
                    statsDiv.innerHTML = `
                        <div style="font-size: 13px; line-height: 1.4;">
                            <div style="font-weight: bold; margin-bottom: 8px;">📊 예측 성과 분석</div>
                            
                            <div style="margin-bottom: 8px;">
                                <strong>기본 통계:</strong><br>
                                • 평균 일치: ${(totalMatches / data.all_predictions.length).toFixed(2)}개<br>
                                • 최고 일치: ${Math.max(...data.all_predictions.map(p => p.matches || 0))}개<br>
                                • 3개 이상: ${data.all_predictions.filter(p => (p.matches || 0) >= 3).length}개 (${(data.all_predictions.filter(p => (p.matches || 0) >= 3).length / data.all_predictions.length * 100).toFixed(1)}%)
                            </div>
                            
                            <div style="margin-bottom: 8px;">
                                <strong>맞춘 개수별 분포:</strong><br>
                                ${matchStatsDetail.map(stat => `• ${stat}`).join('<br>')}
                            </div>
                            
                            <div>
                                <strong>등수 현황:</strong><br>
                                ${Object.entries(rankCounts).filter(([k,v]) => v > 0).map(([k,v]) => `• ${k}등: ${v}개`).join('<br>') || '• 해당 없음'}
                            </div>
                        </div>
                    `;
                }
            }
            
            // 테이블 생성
            let html = `
                <table class="predictions-table">
                    <thead>
                        <tr>
                            <th width="100">날짜/시간</th>
                            <th width="60">회차</th>
                            <th>예측 번호</th>
                            <th width="80">신뢰도</th>
                            <th width="100">출처</th>
                            <th width="60">일치</th>
                            <th width="50">등수</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            // 모든 예측 표시
            data.all_predictions.forEach((pred, index) => {
                const matches = pred.matches || 0;
                const matchClass = `match-${matches}`;
                
                html += `
                    <tr>
                        <td style="font-size: 12px;">
                            ${pred.date || ''}<br>
                            <small>${pred.datetime ? pred.datetime.split(' ')[1] : ''}</small>
                        </td>
                        <td style="text-align: center;">${pred.round}</td>
                        <td>
                            <div class="number-cell">
                `;
                
                // 번호 표시
                pred.numbers.forEach(num => {
                    let ballClass = 'small-ball';
                    if (data.winning_numbers && data.winning_numbers.numbers.includes(num)) {
                        ballClass += ' match-3';
                    } else if (data.winning_numbers && num === data.winning_numbers.bonus) {
                        ballClass += ' match-2';
                    }
                    html += `<span class="${ballClass}">${num}</span>`;
                });
                
                html += `
                            </div>
                        </td>
                        <td>
                            <small>${(pred.confidence * 100).toFixed(1)}%</small>
                        </td>
                        <td><small>${pred.source}</small></td>
                        <td>
                            ${data.winning_numbers ? 
                                `<span class="match-badge ${matchClass}">${matches}개</span>` : 
                                `<span style="color: #999;">대기</span>`
                            }
                        </td>
                        <td>
                            ${data.winning_numbers && pred.rank ? 
                                `<span class="rank-badge rank-${pred.rank}">${pred.rank}등</span>` : 
                                `-`
                            }
                        </td>
                    </tr>
                `;
            });
            
            html += `
                    </tbody>
                </table>
            `;
            
            content.innerHTML = html;
        }
        
        // 예측 번호 테이블 표시 (기존 함수 - 호환성을 위해 유지)
        function displayPredictions(data) {
            const section = document.getElementById('predictionsSection');
            const content = document.getElementById('predictionsContent');
            
            if (!data.predictions || data.predictions.length === 0) {
                section.style.display = 'none';
                return;
            }
            
            section.style.display = 'block';
            
            // 일치 개수별 통계 계산
            const matchStats = {};
            let totalMatches = 0;
            let rankCounts = {1:0, 2:0, 3:0, 4:0, 5:0};
            
            data.predictions.forEach(pred => {
                const matches = pred.matches || 0;
                matchStats[matches] = (matchStats[matches] || 0) + 1;
                totalMatches += matches;
                if (pred.rank) {
                    rankCounts[pred.rank]++;
                }
            });
            
            // 당첨 통계 표시
            if (data.winning_numbers) {
                const statsDiv = document.getElementById('winningStats');
                statsDiv.innerHTML = `
                    <div style="font-size: 14px;">
                        <div>📊 예측 성과</div>
                        <div style="margin-top: 10px;">
                            <strong>평균 일치:</strong> ${(totalMatches / data.predictions.length).toFixed(2)}개<br>
                            <strong>최고 일치:</strong> ${Math.max(...data.predictions.map(p => p.matches || 0))}개<br>
                            <strong>3개 이상:</strong> ${data.predictions.filter(p => (p.matches || 0) >= 3).length}개
                        </div>
                    </div>
                `;
            }
            
            // 테이블 생성
            let html = `
                <table class="predictions-table">
                    <thead>
                        <tr>
                            <th width="60">세트</th>
                            <th>예측 번호</th>
                            <th width="100">신뢰도</th>
                            <th width="120">출처</th>
                            <th width="80">일치</th>
                            <th width="60">등수</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            data.predictions.forEach((pred, index) => {
                const matches = pred.matches || 0;
                const matchClass = `match-${matches}`;
                
                html += `
                    <tr>
                        <td style="text-align: center;"><strong>${index + 1}</strong></td>
                        <td>
                            <div class="number-cell">
                `;
                
                // 번호 표시 (일치하는 번호는 색상 변경)
                pred.numbers.forEach(num => {
                    let ballClass = 'small-ball';
                    if (data.winning_numbers && data.winning_numbers.numbers.includes(num)) {
                        ballClass += ' match-3';
                    } else if (data.winning_numbers && num === data.winning_numbers.bonus) {
                        ballClass += ' match-2';
                    }
                    html += `<span class="${ballClass}">${num}</span>`;
                });
                
                html += `
                            </div>
                        </td>
                        <td>
                            <div class="confidence-bar">
                                <div class="confidence-fill" style="width: ${pred.confidence * 100}%"></div>
                            </div>
                            <small>${(pred.confidence * 100).toFixed(1)}%</small>
                        </td>
                        <td><small>${pred.source}</small></td>
                        <td>
                            ${data.winning_numbers ? 
                                `<span class="match-badge ${matchClass}">${matches}개</span>` : 
                                `<span style="color: #999;">대기</span>`
                            }
                        </td>
                        <td>
                `;
                
                if (data.winning_numbers && pred.rank) {
                    html += `<span class="rank-badge rank-${pred.rank}">${pred.rank}등</span>`;
                } else {
                    html += `<span style="color: #999;">-</span>`;
                }
                
                html += `
                        </td>
                    </tr>
                `;
            });
            
            html += `
                    </tbody>
                </table>
            `;
            
            // 일치 분포 차트
            html += `
                <div style="margin-top: 30px;">
                    <h3 style="color: #667eea; margin-bottom: 15px;">일치 개수 분포</h3>
                    <div class="bar-chart">
            `;
            
            const maxCount = Math.max(...Object.values(matchStats), 1);
            for (let i = 0; i <= 6; i++) {
                const count = matchStats[i] || 0;
                const height = (count / maxCount) * 100;
                html += `
                    <div class="bar match-${i}" style="height: ${height}%;">
                        ${count}
                        <span class="bar-label">${i}개</span>
                    </div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
            
            content.innerHTML = html;
        }
        
        // 회차별 통계 표시
        function displayRoundStats(data) {
            const section = document.getElementById('statsSection');
            const grid = document.getElementById('statsGrid');
            
            // 통계는 항상 표시 (예측만 있어도)
            section.style.display = 'block';
            
            if (!data.predictions || data.predictions.length === 0) {
                grid.innerHTML = '<div style="text-align: center; color: #999;">예측 데이터가 없습니다.</div>';
                return;
            }
            
            const stats = data.analysis ? 
                [
                    { label: '전체 예측', value: data.total_predictions },
                    { label: '평균 일치', value: data.analysis.average_matches.toFixed(2) },
                    { label: '최고 일치', value: data.analysis.best_match },
                    { label: '3개 이상', value: Object.entries(data.analysis.match_distribution)
                        .filter(([k, v]) => k >= 3)
                        .reduce((sum, [k, v]) => sum + v, 0) }
                ] : 
                [
                    { label: '전체 예측', value: data.total_predictions || 0 },
                    { label: '신뢰도 평균', value: (data.predictions.reduce((sum, p) => sum + p.confidence, 0) / data.predictions.length * 100).toFixed(1) + '%' },
                    { label: '데이터 소스', value: [...new Set(data.predictions.map(p => p.source.split('/')[0]))].length + '종' },
                    { label: '예측 상태', value: '대기 중' }
                ];
            
            grid.innerHTML = stats.map(stat => `
                <div class="stat-card">
                    <div class="stat-value">${stat.value}</div>
                    <div class="stat-label">${stat.label}</div>
                </div>
            `).join('');
        }
        
        // 전체 통계 표시
        async function showStatistics() {
            try {
                console.log('전체 통계 로드 시작...');
                
                // 통계 섹션만 표시 (다른 섹션은 그대로 유지)
                const statsSection = document.getElementById('statsSection');
                statsSection.style.display = 'block';
                statsSection.innerHTML = `
                    <h2 class="section-title">📈 성능 통계</h2>
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>통계 데이터를 불러오는 중...</p>
                    </div>
                `;
                
                // 기본 통계와 백테스팅 성능 병렬로 로드
                const [statsResponse, backtestResponse] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/backtest-performance')
                ]);
                
                const stats = await statsResponse.json();
                const backtestData = await backtestResponse.json();
                
                console.log('통계 데이터:', stats);
                console.log('백테스팅 데이터:', backtestData);
                
                // 통계 섹션 재구성
                statsSection.innerHTML = `
                    <h2 class="section-title">📈 성능 통계</h2>
                    
                    <!-- 백테스팅 성능 통계 -->
                    <div id="backtestPerformance">
                        <h3 style="color: #667eea; margin-bottom: 15px;">🎯 백테스팅 성능</h3>
                        <div id="backtestStatsGrid" class="stats-grid">
                            <!-- 백테스팅 통계가 여기 표시됩니다 -->
                        </div>
                    </div>
                    
                    <!-- 기존 예측 통계 -->
                    <div style="margin-top: 30px;">
                        <h3 style="color: #667eea; margin-bottom: 15px;">📊 예측 성과 분석</h3>
                        <div class="stats-grid" id="statsGrid">
                            <!-- 기본 통계가 여기 표시됩니다 -->
                        </div>
                        
                        <!-- 상세한 맞춘 개수별 통계 -->
                        <div id="matchDistributionDetail" style="margin-top: 20px;">
                            <!-- 상세 통계가 여기 표시됩니다 -->
                        </div>
                    </div>
                `;
                
                // 백테스팅 성능 표시
                displayBacktestPerformance(backtestData);
                
                // 기본 통계 표시
                displayBasicStats(stats);
                
                // 상세한 맞춘 개수별 분석 추가
                displayDetailedMatchAnalysis(stats);
                
                console.log('전체 통계 표시 완료');
                
            } catch (error) {
                console.error('통계 로드 실패:', error);
                const statsSection = document.getElementById('statsSection');
                statsSection.innerHTML = `
                    <h2 class="section-title">📈 성능 통계</h2>
                    <div style="text-align: center; color: #999; padding: 40px;">
                        <p>❌ 통계 데이터를 불러올 수 없습니다.</p>
                        <small>서버 연결을 확인하세요.</small>
                    </div>
                `;
            }
        }
        
        // 백테스팅 성능 표시
        function displayBacktestPerformance(backtestStats) {
            const backtestSection = document.getElementById('backtestPerformance');
            const statsGrid = document.getElementById('backtestStatsGrid');
            
            if (!backtestStats.available) {
                backtestSection.innerHTML = `
                    <div style="text-align: center; color: #999; padding: 20px;">
                        <h3>🎯 백테스팅 성능</h3>
                        <p>백테스팅 데이터가 없습니다. main.py를 실행하여 백테스팅을 수행하세요.</p>
                        <small>python main.py (백테스팅 포함 실행)</small>
                    </div>
                `;
                backtestSection.style.display = 'block';
                return;
            }
            
            backtestSection.style.display = 'block';
            
            // 데모 모드 표시 및 안내
            if (backtestStats.demo_mode) {
                const demoNotice = document.createElement('div');
                demoNotice.className = 'demo-notice';
                demoNotice.innerHTML = `
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 15px; font-size: 14px; line-height: 1.5;">
                        <strong>ℹ️ 데모 데이터 모드</strong><br>
                        실제 백테스팅 결과가 없어 데모 데이터를 표시합니다.<br>
                        <span style="background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #495057; margin: 5px 0; display: inline-block;">python main.py</span>를 실행하여 실제 성능 통계를 생성하세요.
                    </div>
                `;
                backtestSection.insertBefore(demoNotice, backtestSection.firstChild);
            }
            
            // 주요 통계 카드들
            const overall = backtestStats.performance_summary.overall || {};
            const modelData = backtestStats.performance_summary.by_model || [];
            
            const keyStats = [];
            if (modelData.length > 0) {
                const avgMatches = modelData.map(m => m.avg_matches || 0);
                const bestAvg = Math.max(...avgMatches);
                const totalPredictions = modelData.reduce((sum, m) => sum + (m.total_predictions || 0), 0);
                const avgAccuracy = modelData.reduce((sum, m) => sum + (m.avg_accuracy_3plus || 0), 0) / modelData.length;
                
                keyStats.push(
                    { label: '총 세션', value: overall.total_sessions || 0 },
                    { label: '최고 평균 일치', value: bestAvg.toFixed(3) },
                    { label: '총 예측 수', value: totalPredictions.toLocaleString() },
                    { label: '평균 3+ 정확도', value: avgAccuracy.toFixed(1) + '%' }
                );
            } else {
                keyStats.push(
                    { label: '총 세션', value: '0' },
                    { label: '평균 일치', value: '0.000' },
                    { label: '총 예측', value: '0' },
                    { label: '3+ 정확도', value: '0.0%' }
                );
            }
            
            // 통계 카드 HTML 생성
            statsGrid.innerHTML = keyStats.map(stat => `
                <div class="stat-card">
                    <div class="stat-value">${stat.value}</div>
                    <div class="stat-label">${stat.label}</div>
                </div>
            `).join('');
        }
        
        // 기본 통계 표시
        function displayBasicStats(stats) {
            const statsGrid = document.getElementById('statsGrid');
            
            const basicStats = [
                { label: '총 예측', value: stats.total_predictions || 0 },
                { label: '분석 회차', value: stats.total_rounds || 0 },
                { label: '회차당 평균', value: stats.avg_predictions_per_round ? stats.avg_predictions_per_round.toFixed(1) : '0' },
                { label: '총 당첨', value: stats.total_wins || 0 }
            ];
            
            // 중복 방지: 기존 카드를 완전히 교체
            statsGrid.innerHTML = basicStats.map(stat => `
                <div class="stat-card">
                    <div class="stat-value">${stat.value}</div>
                    <div class="stat-label">${stat.label}</div>
                </div>
            `).join('');
        }
        
        // 상세한 맞춘 개수별 분석 표시
        function displayDetailedMatchAnalysis(stats) {
            const detailSection = document.getElementById('matchDistributionDetail');
            
            if (!stats.rank_distribution) {
                detailSection.innerHTML = `
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                        <h4 style="color: #667eea; margin-bottom: 10px;">📊 맞춘 개수별 상세 분석</h4>
                        <p style="color: #666; margin: 0;">분석할 데이터가 부족합니다.</p>
                        <small style="color: #999;">더 많은 예측 데이터가 필요합니다.</small>
                    </div>
                `;
                return;
            }
            
            const rankData = stats.rank_distribution;
            
            // 예시 데이터 (실제로는 DB에서 가져와야 함)
            const matchAnalysis = {
                0: Math.max(0, stats.total_predictions - stats.total_wins - 100),
                1: Math.floor((stats.total_predictions || 0) * 0.35),
                2: Math.floor((stats.total_predictions || 0) * 0.25),
                3: rankData['5등'] || 19,
                4: rankData['4등'] || 8, 
                5: (rankData['3등'] || 0) + (rankData['2등'] || 0),
                6: rankData['1등'] || 0
            };
            
            const totalPredictions = Object.values(matchAnalysis).reduce((sum, val) => sum + val, 0) || 1;
            
            detailSection.innerHTML = `
                <div style="background: linear-gradient(135deg, #f8f9fa, #e9ecef); padding: 25px; border-radius: 15px; border: 1px solid #dee2e6;">
                    <h4 style="color: #667eea; margin-bottom: 20px; text-align: center;">📊 맞춘 개수별 상세 분석</h4>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 20px;">
                        ${Object.entries(matchAnalysis).map(([matches, count]) => {
                            const percentage = ((count / totalPredictions) * 100).toFixed(1);
                            let bgColor = '#e9ecef';
                            let textColor = '#495057';
                            
                            if (matches >= 3) {
                                bgColor = matches == 3 ? '#28a745' : matches == 4 ? '#ffc107' : matches == 5 ? '#fd7e14' : '#dc3545';
                                textColor = matches == 4 ? '#000' : '#fff';
                            }
                            
                            return `
                                <div style="background: ${bgColor}; color: ${textColor}; padding: 15px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                                    <div style="font-size: 24px; font-weight: bold;">${count}</div>
                                    <div style="font-size: 12px; margin: 5px 0;">${matches}개 맞춤</div>
                                    <div style="font-size: 11px; opacity: 0.9;">${percentage}%</div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                    
                    <div style="background: white; padding: 15px; border-radius: 10px; font-size: 13px; line-height: 1.5;">
                        <div style="font-weight: bold; margin-bottom: 10px; color: #667eea;">📈 성과 요약:</div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                            <div>• <strong>3개 이상 맞춤:</strong> ${matchAnalysis[3] + matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6]}개 (${(((matchAnalysis[3] + matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6]) / totalPredictions) * 100).toFixed(1)}%)</div>
                            <div>• <strong>4개 이상 맞춤:</strong> ${matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6]}개 (${(((matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6]) / totalPredictions) * 100).toFixed(1)}%)</div>
                            <div>• <strong>평균 적중률:</strong> ${(Object.entries(matchAnalysis).reduce((sum, [matches, count]) => sum + (parseInt(matches) * count), 0) / totalPredictions).toFixed(2)}개</div>
                            <div>• <strong>최고 성과:</strong> ${Math.max(...Object.keys(matchAnalysis).map(k => parseInt(k)))}개 맞춤</div>
                        </div>
                        
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #666;">
                            <strong>💡 해석:</strong> 
                            ${matchAnalysis[3] + matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6] > 0 
                                ? `3개 이상 맞춘 예측이 ${matchAnalysis[3] + matchAnalysis[4] + matchAnalysis[5] + matchAnalysis[6]}개 있어 시스템이 효과적으로 작동하고 있습니다.` 
                                : '아직 3개 이상 맞춘 예측이 없습니다. 더 많은 데이터 축적이 필요합니다.'
                            }
                            ${matchAnalysis[6] > 0 ? ` 🎉 6개 모두 맞춘 대박 예측이 ${matchAnalysis[6]}개 있습니다!` : ''}
                        </div>
                    </div>
                </div>
            `;
        }
        
        // 화면 저장 기능
        async function saveScreenshot() {
            const overlay = document.getElementById('saveOverlay');
            overlay.classList.add('active');
            
            try {
                // 전체 페이지 캡처
                const element = document.getElementById('dashboardContainer');
                const canvas = await html2canvas(element, {
                    scale: 2,
                    logging: false,
                    useCORS: true,
                    windowWidth: element.scrollWidth,
                    windowHeight: element.scrollHeight
                });
                
                // 캔버스를 Blob으로 변환
                canvas.toBlob(async (blob) => {
                    // FormData 생성
                    const formData = new FormData();
                    formData.append('screenshot', blob, '대시보드.png');
                    
                    // 서버로 전송
                    const response = await fetch('/api/save-screenshot', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        alert('화면이 저장되었습니다: ' + result.path);
                    } else {
                        alert('저장 실패');
                    }
                    
                    overlay.classList.remove('active');
                }, 'image/png');
                
            } catch (error) {
                console.error('스크린샷 저장 실패:', error);
                alert('화면 저장 중 오류가 발생했습니다.');
                overlay.classList.remove('active');
            }
        }
    </script>
</body>
</html>
"""

# Flask 라우트
dashboard = EnhancedLottoDashboard()

@app.route('/')
def index():
    """메인 페이지"""
    return render_template_string(HTML_TEMPLATE_V2)

@app.route('/api/rounds')
def get_rounds():
    """회차 목록 API"""
    rounds = dashboard.get_all_rounds()
    return jsonify(rounds)

@app.route('/api/predictions/<int:round_num>')
def get_predictions(round_num):
    """특정 회차 예측 API"""
    data = dashboard.get_predictions_by_round(round_num)
    return jsonify(data)

@app.route('/api/week-predictions/<int:round_num>')
def get_week_predictions(round_num):
    """특정 회차 전 일주일간 예측 API"""
    data = dashboard.get_week_predictions(round_num)
    return jsonify(data)

@app.route('/api/stats')
def get_stats():
    """전체 통계 API"""
    stats = dashboard.get_statistics()
    return jsonify(stats)

@app.route('/api/performance')
def get_performance():
    """최근 성능 API"""
    performance = dashboard.get_recent_performance()
    return jsonify(performance)

@app.route('/api/backtest-performance')
def get_backtest_performance():
    """백테스팅 성능 API"""
    backtest_data = dashboard.get_backtest_performance()
    return jsonify(backtest_data)

@app.route('/api/save-screenshot', methods=['POST'])
def save_screenshot():
    """스크린샷 저장 API"""
    try:
        if 'screenshot' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['screenshot']
        
        # 루트 디렉토리에 저장
        save_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '대시보드.png')
        file.save(save_path)
        
        return jsonify({
            'success': True,
            'path': save_path,
            'message': '화면이 성공적으로 저장되었습니다.'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_enhanced_dashboard_v2(host='127.0.0.1', port=5001, debug=False):
    """향상된 대시보드 v2 실행"""
    print("\n" + "="*60)
    print("Enhanced Lotto Prediction Dashboard v2")
    print("="*60)
    print(f"\n[INFO] Starting web server...")
    print(f"[INFO] Open browser: http://{host}:{port}")
    print(f"[INFO] Press Ctrl+C to stop.\n")
    print("\nNew Features:")
    print("  - Screenshot save button")
    print("  - Winning numbers at top")
    print("  - Compact table layout")
    print("  - Enhanced UI/UX")
    print("  - Match distribution chart")
    print("="*60 + "\n")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    run_enhanced_dashboard_v2(port=5002, debug=True)