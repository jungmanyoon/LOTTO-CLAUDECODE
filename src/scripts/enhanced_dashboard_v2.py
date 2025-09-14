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
import pytz  # 한국 시간대 처리를 위해 추가

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
        # 프로젝트 루트 디렉토리 기준으로 절대 경로 설정
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.db_path = os.path.join(self.project_root, "data/combinations.db")  # Legacy DB
        self.lotto_db_path = os.path.join(self.project_root, "data/lotto_numbers.db")  # Actual winning numbers DB
        self.predictions_db_path = os.path.join(self.project_root, "data/predictions/predictions.db")
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
                    SELECT numbers, draw_date, bonus_number 
                    FROM lotto_numbers 
                    WHERE round = ?
                """, (actual_round,))
                
                row = cursor.fetchone()
                if row:
                    # numbers는 "2,8,13,16,23,28" 형태
                    numbers_str = row[0]
                    numbers = [int(n) for n in numbers_str.split(',')]
                    
                    # 실제 보너스 번호 사용 (DB에서 조회)
                    bonus = row[2] if row[2] is not None else random.choice([n for n in range(1, 46) if n not in numbers])
                    
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
                
                # 맞춘 개수별 분포 (실제 결과가 있는 경우)
                cursor.execute("""
                    SELECT match_count, COUNT(*) as cnt
                    FROM prediction_results
                    GROUP BY match_count
                    ORDER BY match_count
                """)

                match_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
                for row in cursor.fetchall():
                    if row[0] is not None:
                        match_distribution[row[0]] = row[1]

                # 등수별 분포도 가져오기
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
                    'total_wins': sum(rank_stats.values()),
                    'match_distribution': match_distribution
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
            # 먼저 데이터베이스에서 실제 백테스팅 성능 데이터 로드 시도
            performance_db_path = os.path.join(self.project_root, "data/performance_stats.db")
            self.logger.info(f"백테스팅 DB 경로 확인: {performance_db_path}, 존재: {os.path.exists(performance_db_path)}")

            if os.path.exists(performance_db_path):
                self.logger.info("데이터베이스에서 백테스팅 데이터 로드 시도...")
                performance_summary = self._load_backtest_from_db(performance_db_path)
                if performance_summary:
                    self.logger.info(f"데이터베이스에서 백테스팅 데이터 로드 성공! 모델 수: {len(performance_summary.get('by_model', []))}")

                    # API 응답용 데이터 구조로 변환
                    result = {
                        'demo_mode': False,
                        'total_predictions': performance_summary['overall'].get('total_predictions', 0),
                        'average_matches': performance_summary['overall'].get('avg_match_rate', 0),
                        'test_period': performance_summary['overall'].get('test_period', 'N/A'),
                        'model_performance': {}
                    }

                    # 모델별 성능 데이터 변환
                    for model_data in performance_summary.get('by_model', []):
                        model_name = model_data['model']
                        result['model_performance'][model_name] = {
                            'total_predictions': model_data['total_predictions'],
                            'avg_matches': model_data['avg_matches'],
                            'best_match': model_data['best_match'],
                            'accuracy_3plus': model_data['avg_accuracy_3plus'],
                            'match_distribution': model_data.get('match_distribution', {})
                        }

                    self.logger.info(f"API 응답 데이터 준비 완료: demo_mode={result['demo_mode']}, 총 예측={result['total_predictions']}")
                    return result
                else:
                    self.logger.warning("데이터베이스에서 백테스팅 데이터 로드 실패")

            # JSON 파일에서 백테스팅 결과 로드 (백업)
            backtest_files = []
            possible_paths = [
                os.path.join(self.project_root, "results/backtest_results_*.json"),
                os.path.join(self.project_root, "logs/backtesting_results.json"),
                os.path.join(self.project_root, "cache/backtesting_results.json"),
                os.path.join(self.project_root, "data/backtesting_results.json"),
                os.path.join(self.project_root, "backtesting_results.json")
            ]

            import glob
            for path_pattern in possible_paths:
                if '*' in path_pattern:
                    files = glob.glob(path_pattern)
                    backtest_files.extend(files)
                elif os.path.exists(path_pattern):
                    backtest_files.append(path_pattern)

            if backtest_files:
                # 가장 최근 파일 로드
                latest_file = max(backtest_files, key=os.path.getmtime)

                with open(latest_file, 'r', encoding='utf-8') as f:
                    backtest_data = json.load(f)

                # JSON 데이터를 API 응답 형식으로 변환
                result = {
                    'demo_mode': False,
                    'total_predictions': 0,
                    'average_matches': 0,
                    'test_period': 'N/A',
                    'model_performance': {}
                }

                # JSON 데이터에서 필요한 정보 추출
                if 'summary' in backtest_data:
                    summary = backtest_data['summary']
                    result['test_period'] = f"{summary.get('test_start', 'N/A')}-{summary.get('test_end', 'N/A')}회차"

                if 'model_performance' in backtest_data:
                    for model_name, model_data in backtest_data['model_performance'].items():
                        result['model_performance'][model_name] = {
                            'total_predictions': model_data.get('total_predictions', 0),
                            'avg_matches': model_data.get('avg_matches', 0),
                            'best_match': model_data.get('max_matches', 0),
                            'accuracy_3plus': model_data.get('three_plus_rate', 0),
                            'match_distribution': model_data.get('match_distribution', {})
                        }
                        result['total_predictions'] += model_data.get('total_predictions', 0)
                        result['average_matches'] += model_data.get('avg_matches', 0) * model_data.get('total_predictions', 0)

                if result['total_predictions'] > 0:
                    result['average_matches'] /= result['total_predictions']

                self.logger.info(f"JSON 파일에서 백테스팅 데이터 로드: demo_mode={result['demo_mode']}, 총 예측={result['total_predictions']}")
                return result

            # 실제 데이터가 없을 경우 데모 데이터 생성
            self.logger.warning("백테스팅 데이터를 찾을 수 없습니다. 데모 모드로 전환합니다.")
            return self._generate_demo_backtest_data_api()

        except Exception as e:
            self.logger.warning(f"백테스팅 데이터 로드 실패: {e}")
            return self._generate_demo_backtest_data_api()

    def _load_backtest_from_db(self, db_path: str) -> Optional[Dict]:
        """데이터베이스에서 백테스팅 성능 데이터 로드"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # 최신 세션 정보 조회
                cursor.execute("""
                    SELECT id, session_date, total_rounds, test_start_round, test_end_round
                    FROM backtest_sessions
                    ORDER BY id DESC
                    LIMIT 1
                """)
                session_row = cursor.fetchone()

                if not session_row:
                    self.logger.warning("백테스팅 세션이 없습니다.")
                    return None

                session_id, session_date, total_rounds, start_round, end_round = session_row

                # 최신 세션의 모델 성능 데이터 조회
                cursor.execute("""
                    SELECT model_name, total_predictions, avg_matches, best_match,
                           accuracy_3plus, match_0, match_1, match_2, match_3, match_4, match_5, match_6
                    FROM model_performance
                    WHERE session_id = ?
                    ORDER BY model_name
                """, (session_id,))

                model_rows = cursor.fetchall()

                if not model_rows:
                    self.logger.warning(f"세션 {session_id}의 모델 성능 데이터가 없습니다.")
                    return None

                # 백테스팅 데이터 구조 생성
                model_performance = []
                total_predictions_sum = 0
                total_matches_sum = 0
                best_session_match = 0

                for row in model_rows:
                    model_name, total_preds, avg_matches, best_match, accuracy_3plus, \
                    match_0, match_1, match_2, match_3, match_4, match_5, match_6 = row

                    model_performance.append({
                        'model': model_name,
                        'total_predictions': total_preds,
                        'avg_matches': avg_matches,
                        'avg_accuracy_3plus': accuracy_3plus or 0.0,
                        'best_match': best_match,
                        'sessions': 1,  # 현재는 하나의 세션만 표시
                        'match_distribution': {
                            'match_0': match_0 or 0,
                            'match_1': match_1 or 0,
                            'match_2': match_2 or 0,
                            'match_3': match_3 or 0,
                            'match_4': match_4 or 0,
                            'match_5': match_5 or 0,
                            'match_6': match_6 or 0
                        }
                    })

                    total_predictions_sum += total_preds
                    total_matches_sum += avg_matches * total_preds
                    best_session_match = max(best_session_match, best_match)

                # 전체 통계 계산
                avg_match_rate = total_matches_sum / total_predictions_sum if total_predictions_sum > 0 else 0

                return {
                    'overall': {
                        'total_sessions': 1,
                        'avg_match_rate': avg_match_rate,
                        'best_session_match': best_session_match,
                        'total_predictions': total_predictions_sum,
                        'test_period': f"{start_round}-{end_round}회차",
                        'session_date': session_date
                    },
                    'by_model': model_performance,
                    'filter_performance': {
                        'total_combinations_before': 8145060,  # 고정값 (전체 조합 수)
                        'total_combinations_after': 300000,   # 예상 필터링 후 조합 수
                        'reduction_rate': 96.3,               # 예상 감소율
                        'hit_rate_in_filtered_pool': 85.0     # 예상 히트율
                    }
                }

        except Exception as e:
            self.logger.error(f"데이터베이스에서 백테스팅 데이터 로드 실패: {e}")
            return None

    def _generate_demo_backtest_data_api(self) -> Dict:
        """API 응답용 데모 백테스팅 데이터 생성"""
        return {
            'demo_mode': True,
            'total_predictions': 1000,
            'average_matches': 0.875,
            'test_period': '1139-1188회차',
            'model_performance': {
                'lstm': {
                    'total_predictions': 250,
                    'avg_matches': 0.76,
                    'best_match': 3,
                    'accuracy_3plus': 2.4,
                    'match_distribution': {
                        'match_0': 108,
                        'match_1': 100,
                        'match_2': 36,
                        'match_3': 6,
                        'match_4': 0
                    }
                },
                'ensemble': {
                    'total_predictions': 250,
                    'avg_matches': 1.08,
                    'best_match': 3,
                    'accuracy_3plus': 5.6,
                    'match_distribution': {
                        'match_0': 70,
                        'match_1': 106,
                        'match_2': 63,
                        'match_3': 11,
                        'match_4': 0
                    }
                },
                'monte_carlo': {
                    'total_predictions': 250,
                    'avg_matches': 0.74,
                    'best_match': 3,
                    'accuracy_3plus': 1.2,
                    'match_distribution': {
                        'match_0': 104,
                        'match_1': 109,
                        'match_2': 34,
                        'match_3': 3,
                        'match_4': 0
                    }
                },
                'combined': {
                    'total_predictions': 250,
                    'avg_matches': 0.91,
                    'best_match': 3,
                    'accuracy_3plus': 4.4,
                    'match_distribution': {
                        'match_0': 89,
                        'match_1': 108,
                        'match_2': 45,
                        'match_3': 8,
                        'match_4': 0
                    }
                }
            }
        }

    def _generate_demo_backtest_data(self) -> Dict:
        """데모 백테스팅 데이터 생성"""
        return {
            'available': True,
            'demo_mode': True,
            'last_updated': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),  # KST 시간대 적용
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
    
    def _convert_to_kst(self, datetime_str):
        """UTC 시간을 KST로 변환 - 예측 번호는 그대로 유지, 시간만 보정"""
        if not datetime_str:
            return datetime_str
        
        try:
            # IMPORTANT: 한국 시간대(KST) 유지 - 절대 변경하지 말 것!
            # 이 부분은 예측 번호를 변경하지 않고 시간 표시만 KST로 보정합니다.
            
            # 데이터베이스의 시간이 UTC로 저장된 경우 9시간 추가
            # 형식: "YYYY-MM-DD HH:MM:SS"
            if ' ' in datetime_str:
                from datetime import datetime
                dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                
                # UTC를 KST로 변환 (UTC + 9시간)
                kst_dt = dt.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone('Asia/Seoul'))
                
                # 한국 시간대로 표시 - 예측 번호는 그대로 유지
                return kst_dt.strftime('%Y-%m-%d %H:%M:%S')
                
        except Exception:
            # 변환 실패 시 원본 그대로 반환 (예측 번호 보존)
            pass
            
        return datetime_str
    
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
        today = datetime.now(pytz.timezone('Asia/Seoul'))  # KST 시간대 적용
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
                    'datetime': f'{date_str} {random.randint(10, 18):02d}:{random.randint(0, 59):02d}:00',  # 이미 KST 기준
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
                        'datetime': self._convert_to_kst(row[7]),  # KST로 변환
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

        /* 예측 생성 버튼 스타일 */
        button[onclick*="generateNewPredictions"] {
            background: #28a745 !important;
            color: white !important;
            font-weight: bold;
            padding: 10px 20px !important;
            border-radius: 8px;
            transition: all 0.3s;
            border: 2px solid #28a745 !important;
        }

        button[onclick*="generateNewPredictions"]:hover {
            background: #218838 !important;
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.3);
        }

        button[onclick*="generateNewPredictions"]:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: scale(1);
        }

        /* 예측 카드 하이라이트 애니메이션 */
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.02); }
            100% { transform: scale(1); }
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
                <button onclick="generateNewPredictions()" style="background: #28a745; color: white; font-weight: bold; padding: 10px 20px;">
                    🎯 새 예측 생성 (5세트)
                </button>
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
        window.onload = async function() {
            await loadRounds();  // loadRounds가 완료될 때까지 대기
            await loadLatestRound();  // 그 다음 최신 회차 로드
        };
        
        // 회차 목록 로드
        async function loadRounds() {
            try {
                console.log('Loading rounds...');
                const response = await fetch('/api/rounds');
                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }
                allRounds = await response.json();
                console.log('Loaded rounds:', allRounds);

                const select = document.getElementById('roundSelect');
                if (!select) {
                    console.error('roundSelect element not found');
                    return;
                }
                select.innerHTML = '<option value="">회차 선택...</option>';

                allRounds.forEach(round => {
                    const option = document.createElement('option');
                    option.value = round;
                    option.textContent = round + '회차';
                    select.appendChild(option);
                });
                console.log('Rounds added to select');
            } catch (error) {
                console.error('회차 로드 실패:', error);
                alert('회차 목록을 불러올 수 없습니다. 서버 연결을 확인해주세요.');
            }
        }
        
        // 최신 회차 로드
        async function loadLatestRound() {
            console.log('loadLatestRound called, allRounds:', allRounds);
            if (allRounds && allRounds.length > 0) {
                document.getElementById('roundSelect').value = allRounds[0];
                await loadWeekData();  // 일주일 데이터 로드로 변경
            } else {
                console.error('No rounds available');
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
            
            // API 응답 구조 확인
            if (!backtestStats || (!backtestStats.total_predictions && !backtestStats.model_performance)) {
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
            
            // 주요 통계 카드들 - 새로운 API 구조에 맞게 수정
            const modelData = Object.values(backtestStats.model_performance || {});
            
            const keyStats = [];
            if (modelData.length > 0 || backtestStats.total_predictions > 0) {
                const avgMatches = modelData.map(m => m.avg_matches || 0);
                const bestAvg = Math.max(...avgMatches) || backtestStats.average_matches || 0;
                const totalPredictions = backtestStats.total_predictions || modelData.reduce((sum, m) => sum + (m.total_predictions || 0), 0);
                const avgAccuracy = modelData.reduce((sum, m) => sum + (m.accuracy_3plus || 0), 0) / modelData.length || 0;

                keyStats.push(
                    { label: '테스트 기간', value: backtestStats.test_period || 'N/A' },
                    { label: '평균 일치', value: backtestStats.average_matches?.toFixed(3) || bestAvg.toFixed(3) },
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

            // 실제 데이터 사용 (match_distribution이 있으면 사용, 없으면 rank_distribution 기반 추정)
            let matchAnalysis;
            if (stats.match_distribution) {
                matchAnalysis = stats.match_distribution;
            } else {
                // 백업: rank_distribution 기반 추정 (정확하지 않음)
                matchAnalysis = {
                    0: Math.max(0, stats.total_predictions - stats.total_wins - 100),
                    1: Math.floor((stats.total_predictions || 0) * 0.35),
                    2: Math.floor((stats.total_predictions || 0) * 0.25),
                    3: rankData['5등'] || 0,
                    4: rankData['4등'] || 0,
                    5: (rankData['3등'] || 0) + (rankData['2등'] || 0),
                    6: rankData['1등'] || 0
                };
            }
            
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

        // 새 예측 생성 기능
        async function generateNewPredictions() {
            const btn = event.target;
            const originalText = btn.innerText;

            try {
                // 버튼 비활성화 및 로딩 표시
                btn.disabled = true;
                btn.innerText = '⏳ 생성 중...';
                btn.style.opacity = '0.6';

                // API 호출
                const response = await fetch('/api/generate-predictions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    // 성공 메시지
                    var message = '✅ ' + result.round + '회차 예측 5세트가 생성되었습니다!\\n\\n';
                    message += '생성된 예측:\\n';
                    result.predictions.forEach(function(p, i) {
                        message += (i+1) + '. [' + p.numbers.join(', ') + '] (신뢰도: ' + Math.round(p.confidence * 100) + '%)\\n';
                    });
                    alert(message);

                    // 회차 목록 새로고침
                    await loadRounds();

                    // 새로 생성된 회차 선택
                    document.getElementById('roundSelect').value = result.round;

                    // 새 예측 즉시 표시
                    await loadRoundData();

                    // 하이라이트 효과
                    highlightNewPredictions();
                } else {
                    alert('❌ 예측 생성 실패:\\n' + (result.error || '알 수 없는 오류가 발생했습니다.'));
                }
            } catch (error) {
                console.error('예측 생성 오류:', error);
                alert('❌ 오류 발생:\\n' + error.message);
            } finally {
                // 버튼 복구
                btn.disabled = false;
                btn.innerText = originalText;
                btn.style.opacity = '1';
            }
        }

        // 새로 생성된 예측 하이라이트 효과
        function highlightNewPredictions() {
            const predCards = document.querySelectorAll('.prediction-card');
            predCards.forEach((card, idx) => {
                setTimeout(() => {
                    card.style.transition = 'all 0.5s';
                    card.style.transform = 'scale(1.02)';
                    card.style.boxShadow = '0 0 20px rgba(40, 167, 69, 0.5)';

                    setTimeout(() => {
                        card.style.transform = 'scale(1)';
                        card.style.boxShadow = '';
                    }, 2000);
                }, idx * 100);
            });
        }

        // 초기 로드 - 위의 window.onload와 중복되므로 제거
    </script>
</body>
</html>
"""

# Flask 라우트 - 항상 새로운 인스턴스 생성
def get_dashboard():
    """매번 새로운 대시보드 인스턴스 반환"""
    return EnhancedLottoDashboard()

dashboard = get_dashboard()  # 초기 인스턴스

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
    # 새로운 대시보드 인스턴스 사용하여 최신 데이터 보장
    fresh_dashboard = EnhancedLottoDashboard()

    # 디버깅을 위한 로그
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Flask API - 프로젝트 루트: {fresh_dashboard.project_root}")

    performance_db_path = os.path.join(fresh_dashboard.project_root, "data/performance_stats.db")
    logger.info(f"Flask API - DB 경로: {performance_db_path}")
    logger.info(f"Flask API - DB 존재: {os.path.exists(performance_db_path)}")

    backtest_data = fresh_dashboard.get_backtest_performance()
    logger.info(f"Flask API - 데모 모드: {backtest_data.get('demo_mode', True)}")

    return jsonify(backtest_data)

@app.route('/api/generate-predictions', methods=['POST'])
def generate_new_predictions():
    """캐시된 모델을 활용한 예측 생성 API"""
    try:
        # 프로젝트 루트 경로 설정
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)

        # 필요한 모듈 import
        from main import generate_final_predictions
        from src.core.db_manager import DatabaseManager
        from src.core.integrated_filter_manager import IntegratedFilterManager
        from src.core.prediction_tracker import PredictionTracker
        import pickle
        import glob

        logging.info("[API] 예측 생성 시작...")

        # 기존 인스턴스 생성
        db_manager = DatabaseManager()
        filter_manager = IntegratedFilterManager(db_manager)

        # 캐시된 ML 예측 로드
        ml_predictions = {}
        cache_dir = os.path.join(project_root, 'cache', 'models')

        # 각 모델의 최신 캐시 파일 찾기
        if os.path.exists(cache_dir):
            # Ensemble 모델 캐시 찾기
            ensemble_files = glob.glob(os.path.join(cache_dir, 'ensemble_*.pkl'))
            if ensemble_files:
                # 가장 최신 파일 선택
                latest_ensemble = max(ensemble_files, key=os.path.getmtime)
                try:
                    with open(latest_ensemble, 'rb') as f:
                        ensemble_data = pickle.load(f)
                        # 예측 결과가 있으면 사용
                        if 'predictions' in ensemble_data:
                            ml_predictions['ensemble'] = ensemble_data['predictions'][:5]
                            logging.info(f"Ensemble 캐시 로드: {len(ml_predictions['ensemble'])}개")
                except Exception as e:
                    logging.warning(f"Ensemble 캐시 로드 실패: {e}")

            # 빈 ML 예측이면 기본값 설정
            if not ml_predictions:
                logging.info("캐시된 ML 예측이 없으므로 필터링된 조합에서 직접 생성")
                ml_predictions = {
                    'lstm': [],
                    'ensemble': [],
                    'monte_carlo': [],
                    'bayesian': [],
                    'fractal': [],
                    'combined': []
                }

        # main.py와 동일한 예측 생성
        final_predictions = generate_final_predictions(
            db_manager=db_manager,
            filter_manager=filter_manager,
            ml_predictions=ml_predictions,
            num_sets=5,
            use_relaxed_filter=True
        )

        # 다음 회차 번호 계산 (토요일 저녁 8시 기준)
        from datetime import datetime
        latest_round = db_manager.get_last_round()

        # 현재 시간 확인
        current_time = datetime.now()
        current_weekday = current_time.weekday()  # 0=월요일, 5=토요일, 6=일요일
        current_hour = current_time.hour

        # 토요일 저녁 8시를 기준으로 회차 결정
        # 중요: 항상 latest_round + 1 (DB에 이미 최신 회차가 반영됨)
        if current_weekday == 5 and current_hour < 20:  # 토요일 오후 8시 이전
            next_round = latest_round + 1  # 아직 이번 주 회차
            logging.info(f"[API] 토요일 {current_hour}시 - {next_round}회차 예측 생성")
        elif current_weekday == 5 and current_hour >= 20:  # 토요일 오후 8시 이후
            next_round = latest_round + 1  # 다음 주 회차 (DB가 이미 업데이트됨)
            logging.info(f"[API] 토요일 {current_hour}시 - 추첨 완료, {next_round}회차 예측 생성")
        elif current_weekday == 6:  # 일요일
            next_round = latest_round + 1  # 다음 주 회차
            logging.info(f"[API] 일요일 - {next_round}회차 예측 생성")
        else:  # 월~금요일
            next_round = latest_round + 1  # 이번 주 회차
            logging.info(f"[API] {['월','화','수','목','금'][current_weekday]}요일 - {next_round}회차 예측 생성")

        # 예측 저장
        prediction_tracker = PredictionTracker()

        # 예측 형식 변환 (main.py와 동일) - JSON 직렬화를 위해 numpy 타입을 Python 타입으로 변환
        predictions_to_save = []
        for idx, pred in enumerate(final_predictions, 1):
            # 숫자 리스트를 Python int로 변환 (numpy int32 등을 처리)
            numbers = pred['numbers'] if isinstance(pred, dict) else pred
            if hasattr(numbers, 'tolist'):  # numpy array인 경우
                numbers = numbers.tolist()
            elif isinstance(numbers, list):  # 리스트인 경우 각 요소를 int로 변환
                numbers = [int(num) for num in numbers]

            predictions_to_save.append({
                'numbers': numbers,
                'confidence': float(pred.get('confidence', 0.7)) if isinstance(pred, dict) else 0.7,
                'source': pred.get('source', 'Dashboard') if isinstance(pred, dict) else 'Dashboard',
                'characteristics': pred.get('characteristics', {}) if isinstance(pred, dict) else {}
            })

        # 저장 (누적 저장)
        success = prediction_tracker.save_predictions(
            round_num=next_round,
            predictions=predictions_to_save,
            replace=False  # 기존 예측 유지
        )

        if success:
            logging.info(f"[API] {next_round}회차 예측 5세트 생성 및 저장 완료")
        else:
            logging.warning(f"[API] {next_round}회차 예측 저장 실패")

        return jsonify({
            'success': success,
            'round': int(next_round),  # numpy int를 Python int로 변환
            'predictions': [
                {
                    'numbers': [int(num) for num in pred['numbers']],  # 각 숫자를 Python int로 변환
                    'confidence': float(pred.get('confidence', 0.7)),  # numpy float을 Python float으로 변환
                    'source': pred.get('source', 'Dashboard')
                }
                for pred in predictions_to_save
            ],
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logging.error(f"[API] 예측 생성 중 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
    print("  - [NEW] Prediction generation button (5 sets)")
    print("  - Screenshot save button")
    print("  - Winning numbers at top")
    print("  - Compact table layout")
    print("  - Enhanced UI/UX")
    print("  - Match distribution chart")
    print("="*60 + "\n")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    run_enhanced_dashboard_v2(port=5001, debug=True)