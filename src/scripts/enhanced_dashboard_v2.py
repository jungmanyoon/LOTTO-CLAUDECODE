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

# SECURITY: CSRF protection and Rate Limiting
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

# Werkzeug (Flask 내부 서버) 로그 레벨을 WARNING으로 설정
# API 요청 로그 (GET /api/...) 감소
werkzeug_log = logging.getLogger('werkzeug')
werkzeug_log.setLevel(logging.WARNING)

# SECURITY: Configure secret key for CSRF protection (SEC-001: 파일 기반 영구 키)
from pathlib import Path

def get_or_create_secret_key(key_file: str = '.secret_key') -> str:
    """SECRET_KEY를 파일에서 로드하거나 새로 생성

    Args:
        key_file: 키 파일 경로

    Returns:
        str: SECRET_KEY 값
    """
    # 프로젝트 루트 기준으로 경로 설정
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    key_path = Path(os.path.join(project_root, key_file))

    if key_path.exists():
        return key_path.read_text(encoding='utf-8').strip()

    # 새 키 생성 및 저장
    secret_key = os.urandom(32).hex()
    key_path.write_text(secret_key, encoding='utf-8')

    # Windows에서는 os.chmod가 제한적이므로 try-except로 처리
    try:
        os.chmod(str(key_path), 0o600)  # owner만 읽기/쓰기
    except (OSError, PermissionError):
        pass  # Windows에서는 권한 설정이 다르게 동작

    logging.info(f"새 SECRET_KEY 생성됨: {key_path}")
    return secret_key

app.config['SECRET_KEY'] = get_or_create_secret_key()

# SECURITY: Initialize CSRF protection
csrf = CSRFProtect(app)

# SECURITY: Initialize Rate Limiter (SEC-003: 강화된 Rate Limit)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[
        "100 per day",      # 하루 100 요청
        "20 per hour",      # 시간당 20 요청
        "5 per minute"      # 분당 5 요청
    ],
    storage_uri="memory://",
    strategy="fixed-window"
)

# Rate Limit 초과 시 JSON 응답 반환 (HTML 대신)
@app.errorhandler(429)
def ratelimit_handler(e):
    """Rate limit 초과 시 JSON 에러 반환"""
    return jsonify({
        'success': False,
        'error': '요청 한도 초과. 잠시 후 다시 시도해주세요.',
        'error_code': 'RATE_LIMIT_EXCEEDED'
    }), 429

# 일반 에러 핸들러 (500 에러)
@app.errorhandler(500)
def internal_error_handler(e):
    """내부 서버 오류 시 JSON 에러 반환"""
    return jsonify({
        'success': False,
        'error': '서버 내부 오류가 발생했습니다.',
        'error_code': 'INTERNAL_SERVER_ERROR'
    }), 500

# 404 에러 핸들러
@app.errorhandler(404)
def not_found_handler(e):
    """페이지를 찾을 수 없을 때 JSON 에러 반환"""
    return jsonify({
        'success': False,
        'error': '요청한 리소스를 찾을 수 없습니다.',
        'error_code': 'NOT_FOUND'
    }), 404


# ============================================================
# SEC-002: 토큰 기반 인증 시스템
# ============================================================
import secrets
from functools import wraps

class TokenAuthenticator:
    """간단한 토큰 기반 인증 (SEC-002)

    - 로컬호스트(127.0.0.1, localhost)는 인증 없이 허용
    - 외부 접근 시 Bearer 토큰 필요
    """

    def __init__(self, token_file: str = '.api_tokens'):
        self.token_file = token_file
        self.tokens = set()
        self._load_tokens()

    def _get_token_path(self) -> str:
        """토큰 파일 경로 반환"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(project_root, self.token_file)

    def _load_tokens(self):
        """저장된 토큰 로드"""
        token_path = self._get_token_path()
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    self.tokens = set(line.strip() for line in f if line.strip())
            except Exception as e:
                logging.warning(f"토큰 로드 실패: {e}")

    def generate_token(self) -> str:
        """새 토큰 생성 및 저장"""
        token = secrets.token_urlsafe(32)
        self.tokens.add(token)

        token_path = self._get_token_path()
        try:
            with open(token_path, 'a', encoding='utf-8') as f:
                f.write(token + '\n')
            # Windows에서는 chmod 제한적
            try:
                os.chmod(token_path, 0o600)
            except (OSError, PermissionError):
                pass
            logging.info(f"새 API 토큰 생성됨")
        except Exception as e:
            logging.error(f"토큰 저장 실패: {e}")

        return token

    def verify(self, token: str) -> bool:
        """토큰 검증"""
        return token in self.tokens

    def is_localhost(self, remote_addr: str) -> bool:
        """로컬호스트 여부 확인"""
        return remote_addr in ('127.0.0.1', 'localhost', '::1', None)


# 인증 관리자 초기화
authenticator = TokenAuthenticator()


def _mask_ip(ip: str) -> str:
    """IP 주소 마스킹 (SEC-005: 민감 정보 보호)

    예: 192.168.1.100 -> 192.168.*.***
    """
    if not ip:
        return 'unknown'
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    return ip[:len(ip)//2] + '*' * (len(ip) - len(ip)//2)


def require_auth(f):
    """인증 필요 데코레이터 (SEC-002)

    - 로컬호스트 접근: 인증 없이 허용
    - 외부 접근: Bearer 토큰 필요

    SEC-005: 토큰 값 로깅 금지, IP 마스킹 적용
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        remote_addr = request.remote_addr

        # 로컬호스트는 인증 없이 허용
        if authenticator.is_localhost(remote_addr):
            return f(*args, **kwargs)

        # 외부 접근은 토큰 검증
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            # SEC-005: IP 마스킹, 토큰 값 노출 금지
            logging.warning(f"[SEC] 인증 실패 - 헤더 없음 (IP: {_mask_ip(remote_addr)})")
            return jsonify({
                'success': False,
                'error': 'Authorization 헤더가 필요합니다 (Bearer 토큰)',
                'error_code': 'AUTH_REQUIRED'
            }), 401

        token = auth_header[7:]  # "Bearer " 제거

        if not authenticator.verify(token):
            # SEC-005: 토큰 값 노출 없이 실패 로깅
            logging.warning(f"[SEC] 인증 실패 - 잘못된 토큰 (IP: {_mask_ip(remote_addr)})")
            return jsonify({
                'success': False,
                'error': '유효하지 않은 토큰입니다',
                'error_code': 'AUTH_FAILED'
            }), 401

        return f(*args, **kwargs)
    return decorated


def require_auth_strict(f):
    """엄격한 인증 데코레이터 (민감한 API용)

    - 모든 접근에 토큰 필요 (로컬호스트 포함)

    SEC-005: 토큰 값 로깅 금지, IP 마스킹 적용
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        remote_addr = request.remote_addr
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            # SEC-005: IP 마스킹, 토큰 값 노출 금지
            logging.warning(f"[SEC-STRICT] 인증 실패 - 헤더 없음 (IP: {_mask_ip(remote_addr)})")
            return jsonify({
                'success': False,
                'error': 'Authorization 헤더가 필요합니다 (Bearer 토큰)',
                'error_code': 'AUTH_REQUIRED'
            }), 401

        token = auth_header[7:]

        if not authenticator.verify(token):
            # SEC-005: 토큰 값 노출 없이 실패 로깅
            logging.warning(f"[SEC-STRICT] 인증 실패 - 잘못된 토큰 (IP: {_mask_ip(remote_addr)})")
            return jsonify({
                'success': False,
                'error': '유효하지 않은 토큰입니다',
                'error_code': 'AUTH_FAILED'
            }), 401

        return f(*args, **kwargs)
    return decorated


# 토큰 생성 엔드포인트 (로컬호스트에서만 접근 가능)
@app.route('/api/generate-token', methods=['POST'])
@limiter.limit("3 per day")  # 하루 3번으로 제한
def generate_api_token():
    """API 토큰 생성 (로컬호스트 전용)"""
    if not authenticator.is_localhost(request.remote_addr):
        return jsonify({
            'success': False,
            'error': '토큰 생성은 로컬호스트에서만 가능합니다',
            'error_code': 'FORBIDDEN'
        }), 403

    token = authenticator.generate_token()
    return jsonify({
        'success': True,
        'token': token,
        'message': '토큰이 생성되었습니다. 안전하게 보관하세요.'
    })
# ============================================================


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
                    # 데이터무결성: 보너스가 없으면 가짜로 생성하지 않고 None 유지
                    # -> 2등(5+보너스) 판정은 자동 보류(데이터 없음)되며, 수집을 유도한다.
                    bonus = row[2]
                    if bonus is None:
                        self.logger.warning(
                            f"{actual_round}회차 보너스 번호 없음 -> 2등(5+보너스) 판정 보류. "
                            f"수집하려면 'python src/scripts/complete_bonus_collection.py' 실행"
                        )

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
            # DB 파일이 없으면 에러 반환 (데모 데이터 사용 금지)
            if not os.path.exists(self.predictions_db_path):
                self.logger.error(f"예측 DB 파일 없음: {self.predictions_db_path}")
                return {
                    'error': True,
                    'error_message': '예측 데이터베이스가 없습니다. main.py를 먼저 실행하세요.',
                    'total_predictions': 0,
                    'total_rounds': 0,
                    'avg_predictions_per_round': 0,
                    'rank_distribution': {'1등': 0, '2등': 0, '3등': 0, '4등': 0, '5등': 0},
                    'total_wins': 0
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

    def get_winning_statistics(self, round_num: Optional[int] = None) -> Dict:
        """당첨 통계 조회 (1~5등 당첨자 수, 당첨금액, 확률)

        Args:
            round_num: 특정 회차 (None이면 최근 회차)

        Returns:
            Dict: 당첨 통계 데이터
        """
        try:
            with sqlite3.connect(self.lotto_db_path) as conn:
                cursor = conn.cursor()

                # 특정 회차 또는 최근 회차
                if round_num:
                    cursor.execute("""
                        SELECT round, first_winners, first_prize, second_winners, second_prize,
                               third_winners, third_prize, fourth_winners, fourth_prize,
                               fifth_winners, fifth_prize, total_sales
                        FROM lotto_statistics WHERE round = ?
                    """, (round_num,))
                else:
                    cursor.execute("""
                        SELECT round, first_winners, first_prize, second_winners, second_prize,
                               third_winners, third_prize, fourth_winners, fourth_prize,
                               fifth_winners, fifth_prize, total_sales
                        FROM lotto_statistics ORDER BY round DESC LIMIT 1
                    """)

                row = cursor.fetchone()
                if row:
                    total_games = row[11] // 1000 if row[11] else 0  # 1게임 1000원 가정
                    return {
                        'round': row[0],
                        'statistics': {
                            # JavaScript에서 접근하기 쉬운 키
                            'first_winners': row[1],
                            'first_prize': row[2],
                            'second_winners': row[3],
                            'second_prize': row[4],
                            'third_winners': row[5],
                            'third_prize': row[6],
                            'fourth_winners': row[7],
                            'fourth_prize': row[8],
                            'fifth_winners': row[9],
                            'fifth_prize': row[10],
                            # 한글 키 (하위 호환성)
                            '1등': {'winners': row[1], 'prize': row[2],
                                   'probability': f"{(row[1]/total_games*100):.8f}%" if total_games else "N/A"},
                            '2등': {'winners': row[3], 'prize': row[4],
                                   'probability': f"{(row[3]/total_games*100):.6f}%" if total_games else "N/A"},
                            '3등': {'winners': row[5], 'prize': row[6],
                                   'probability': f"{(row[5]/total_games*100):.4f}%" if total_games else "N/A"},
                            '4등': {'winners': row[7], 'prize': row[8],
                                   'probability': f"{(row[7]/total_games*100):.4f}%" if total_games else "N/A"},
                            '5등': {'winners': row[9], 'prize': row[10],
                                   'probability': f"{(row[9]/total_games*100):.2f}%" if total_games else "N/A"}
                        },
                        'probabilities': {
                            'first_place_probability': '1/8,145,060',
                            'second_place_probability': '1/1,357,510',
                            'third_place_probability': '1/35,724',
                            'fourth_place_probability': '1/733',
                            'fifth_place_probability': '1/45'
                        },
                        'total_sales': row[11],
                        'total_games': total_games
                    }

                return {'error': True, 'error_message': '통계 데이터가 없습니다.'}

        except Exception as e:
            self.logger.error(f"당첨 통계 조회 실패: {e}")
            return {'error': True, 'error_message': str(e)}

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

                    # API 응답용 데이터 구조로 변환 (데모 모드 제거됨 - 실제 데이터만 사용)
                    result = {
                        'error': False,
                        'total_predictions': performance_summary['overall'].get('total_predictions', 0),
                        'average_matches': performance_summary['overall'].get('avg_match_rate', 0),
                        'test_period': performance_summary['overall'].get('test_period', 'N/A'),
                        'probability_threshold': performance_summary['overall'].get('probability_threshold'),
                        'model_performance': {},
                        # 필터 성능 데이터 포함 - 실제 데이터만 사용 (가짜 데이터 금지)
                        'filter_performance': performance_summary.get('filter_performance', {})
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

                    self.logger.info(f"API 응답 데이터 준비 완료 (DB): 총 예측={result['total_predictions']}, 필터 데이터 유무={result['filter_performance'].get('data_available', False)}")
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

                # JSON 데이터를 API 응답 형식으로 변환 (데모 모드 제거됨 - 실제 데이터만 사용)
                result = {
                    'error': False,
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

                self.logger.info(f"API 응답 데이터 준비 완료 (JSON): 총 예측={result['total_predictions']}")
                return result

            # 실제 데이터가 없을 경우 에러 반환 (데모 데이터 사용 금지)
            self.logger.error("백테스팅 데이터를 찾을 수 없습니다. main.py를 먼저 실행하세요.")
            return self._generate_error_response("백테스팅 데이터가 없습니다. main.py를 먼저 실행하세요.")

        except Exception as e:
            self.logger.error(f"백테스팅 데이터 로드 실패: {e}")
            return self._generate_error_response(f"백테스팅 데이터 로드 실패: {str(e)}")

    def _load_backtest_from_db(self, db_path: str) -> Optional[Dict]:
        """데이터베이스에서 백테스팅 성능 데이터 로드"""
        try:
            # [코드리뷰 2026-06-27 P3] 대용량 DB의 cleanup DELETE와 동시 조회 시 'database is
            # locked' 회피: 기본 5초 대신 120초 busy_timeout 부여(쓰기 측 WAL은 영속).
            with sqlite3.connect(db_path, timeout=120) as conn:
                conn.execute("PRAGMA busy_timeout=120000")
                cursor = conn.cursor()

                # 최신 세션 정보 조회 - 캐시 무효화를 위해 매번 새로 조회
                # combination_count, ml_inclusion_rate, probability_threshold 추가 조회
                cursor.execute("""
                    SELECT id, session_date, total_rounds, test_start_round, test_end_round,
                           combination_count, ml_inclusion_rate, probability_threshold
                    FROM backtest_sessions
                    ORDER BY session_date DESC, id DESC
                    LIMIT 1
                """)
                session_row = cursor.fetchone()

                if not session_row:
                    self.logger.warning("백테스팅 세션이 없습니다.")
                    return None

                session_id, session_date, total_rounds, start_round, end_round, \
                    combination_count, ml_inclusion_rate, probability_threshold = session_row

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

                # 필터 성능 데이터 계산 - 실제 데이터만 사용, 가짜 데이터 절대 금지
                total_combinations_before = 8145060  # 45C6 = 8,145,060 (수학적 상수)

                # 실제 데이터가 있는 경우에만 계산
                if combination_count and combination_count > 0:
                    total_combinations_after = combination_count
                    reduction_rate = round((1 - combination_count / total_combinations_before) * 100, 2)
                else:
                    # 실제 데이터가 없으면 None으로 표시 (가짜 데이터 금지)
                    total_combinations_after = None
                    reduction_rate = None

                # ML 포함률도 실제 데이터만 사용
                if ml_inclusion_rate is not None and ml_inclusion_rate > 0:
                    hit_rate_in_filtered_pool = round(ml_inclusion_rate * 100, 2)
                else:
                    hit_rate_in_filtered_pool = None

                return {
                    'overall': {
                        'total_sessions': 1,
                        'avg_match_rate': avg_match_rate,
                        'best_session_match': best_session_match,
                        'total_predictions': total_predictions_sum,
                        'test_period': f"{start_round}-{end_round}회차",
                        'session_date': session_date,
                        'probability_threshold': probability_threshold  # 확률 임계값 추가
                    },
                    'by_model': model_performance,
                    'filter_performance': {
                        'total_combinations_before': total_combinations_before,  # 전체 조합 수 (수학적 상수)
                        'total_combinations_after': total_combinations_after,    # 실제 필터링 후 조합 수 (None if 데이터 없음)
                        'reduction_rate': reduction_rate,                        # 실제 감소율 (None if 데이터 없음)
                        'hit_rate_in_filtered_pool': hit_rate_in_filtered_pool,  # 실제 ML 포함률 (None if 데이터 없음)
                        'data_available': combination_count is not None and combination_count > 0  # 데이터 유무 플래그
                    }
                }

        except Exception as e:
            self.logger.error(f"데이터베이스에서 백테스팅 데이터 로드 실패: {e}")
            return None

    def _generate_error_response(self, error_message: str) -> Dict:
        """에러 응답 생성 (데모 데이터 대신 사용)"""
        return {
            'error': True,
            'error_message': error_message,
            'total_predictions': 0,
            'average_matches': 0,
            'test_period': 'N/A',
            'model_performance': {}
        }

    # NOTE: _generate_demo_backtest_data() 함수 삭제됨 - 데모 데이터 사용 금지 정책
    # 대신 _generate_error_response()를 사용하여 에러 메시지 반환
    
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
                validation_result['warning_message'] = f"[ALERT] 경고: {round_num}회차 당첨번호가 {len(validation_result['failed_filters'])}개 필터에 의해 제외되었습니다!"
                self.logger.warning(validation_result['warning_message'])
            
            # 결과 저장
            self.filter_validation_results[round_num] = validation_result
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"필터 검증 중 오류: {e}")
            return {'passed': None, 'failed_filters': [], 'warning_message': None}

    def validate_prediction_numbers(self, numbers: List[int], source: str = "Unknown") -> Dict:
        """예측 번호가 필터에 위반되는지 확인 (새로운 검증 기능)"""
        validation_result = {
            'passed': True,
            'failed_filters': [],
            'warning_message': None,
            'in_filtered_pool': False,
            'filter_bypass_applied': False,
            'recommendation': 'accept'
        }

        try:
            # 기본 유효성 검사
            if len(numbers) != 6 or len(set(numbers)) != 6 or not all(1 <= n <= 45 for n in numbers):
                validation_result['passed'] = False
                validation_result['failed_filters'].append('기본 유효성')
                validation_result['recommendation'] = 'reject'
                return validation_result

            # 1. 홀짝 균형 필터 (극단적인 경우만 제외)
            odd_count = len([n for n in numbers if n % 2 == 1])
            if odd_count == 0 or odd_count == 6:
                validation_result['failed_filters'].append(f'홀짝 균형 (홀수: {odd_count}개)')

            # 2. 합계 범위 필터
            total_sum = sum(numbers)
            if total_sum < 68 or total_sum > 209:
                validation_result['failed_filters'].append(f'합계 범위 (합: {total_sum})')

            # 3. 연속 번호 필터 (3개 이상 연속)
            sorted_numbers = sorted(numbers)
            consecutive_count = 0
            max_consecutive = 0
            for i in range(len(sorted_numbers) - 1):
                if sorted_numbers[i+1] - sorted_numbers[i] == 1:
                    consecutive_count += 1
                    max_consecutive = max(max_consecutive, consecutive_count + 1)
                else:
                    consecutive_count = 0

            if max_consecutive >= 3:
                validation_result['failed_filters'].append(f'연속 번호 ({max_consecutive}개 연속)')

            # 4. 최대 간격 필터 (1-45 범위에서 너무 큰 간격)
            max_gap = max(sorted_numbers[i+1] - sorted_numbers[i] for i in range(len(sorted_numbers) - 1))
            if max_gap > 20:  # 20보다 큰 간격
                validation_result['failed_filters'].append(f'최대 간격 (간격: {max_gap})')

            # 실패한 필터가 있는지 확인
            if validation_result['failed_filters']:
                validation_result['passed'] = False

                # ML 예측인 경우 완화 로직 적용
                if source.startswith('ML/'):
                    # 중요 필터만 체크 (홀짝, 합계)
                    critical_failures = []
                    for failed_filter in validation_result['failed_filters']:
                        if '홀짝' in failed_filter or '합계' in failed_filter:
                            critical_failures.append(failed_filter)

                    if not critical_failures:
                        # 중요 필터만 통과하면 완화 적용
                        validation_result['filter_bypass_applied'] = True
                        validation_result['passed'] = True
                        validation_result['recommendation'] = 'accept_with_warning'
                        validation_result['warning_message'] = f"[WARN] ML 예측 완화 적용: {', '.join(validation_result['failed_filters'])}"
                    else:
                        validation_result['recommendation'] = 'reject'
                        validation_result['warning_message'] = f"[X] 중요 필터 실패: {', '.join(critical_failures)}"
                else:
                    validation_result['recommendation'] = 'reject'
                    validation_result['warning_message'] = f"[X] 필터 실패: {', '.join(validation_result['failed_filters'])}"

            # 필터링된 풀 확인 (실제 DB 확인은 성능상 생략, 데모 데이터 사용)
            validation_result['in_filtered_pool'] = validation_result['passed']  # 간단한 근사치

        except Exception as e:
            self.logger.error(f"예측 번호 검증 중 오류: {e}")
            validation_result['passed'] = False
            validation_result['failed_filters'].append(f'검증 오류: {str(e)}')
            validation_result['recommendation'] = 'reject'

        return validation_result

    def _generate_week_predictions_error(self, round_num: int, error_message: str) -> Dict:
        """주간 예측 에러 응답 생성 (데모 데이터 사용 금지 정책)"""
        return {
            'error': True,
            'error_message': error_message,
            'round': round_num,
            'predictions_by_date': {},
            'all_predictions': [],
            'winning_numbers': None,
            'total_predictions': 0,
            'date_count': 0,
            'filter_validation': {'passed': False, 'error': True}
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
                
                # 공식 당첨 통계 조회
                winning_statistics = self.get_winning_statistics(round_num) if winning_numbers else None

                return {
                    'round': round_num,
                    'predictions_by_date': predictions_by_date,
                    'all_predictions': all_predictions,
                    'winning_numbers': winning_numbers,
                    'winning_statistics': winning_statistics,
                    'total_predictions': len(all_predictions),
                    'date_count': len(predictions_by_date),
                    'filter_validation': filter_validation
                }
                
        except Exception as e:
            self.logger.error(f"주간 예측 조회 실패: {e}")
            # 에러 응답 반환 (데모 데이터 사용 금지 정책)
            return self._generate_week_predictions_error(round_num, f"예측 데이터 조회 실패: {str(e)}. main.py를 먼저 실행하세요.")
    


# HTML 템플릿 v2 - 개선된 UI
HTML_TEMPLATE_V2 = """
<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>로또 오라클 — AI 예측 분석</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <script>
      // 테마를 페인트 전에 적용해 깜빡임(FOUC) 방지
      (function () {
        try {
          var saved = localStorage.getItem('lotto-theme');
          if (!saved) {
            saved = (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
          }
          document.documentElement.setAttribute('data-theme', saved);
        } catch (e) { document.documentElement.setAttribute('data-theme', 'dark'); }
      })();
    </script>
    <style>
      /* ========== 디자인 토큰 ========== */
      :root {
        --font-sans: 'Pretendard Variable','Pretendard',-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;
        --font-mono: 'JetBrains Mono','SFMono-Regular',Consolas,monospace;
        --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-pill: 999px;
        --gap: 16px;
        /* 로또 공 공식 색상대 */
        --b1: #F5C518; --b2: #4D9DE8; --b3: #F0556B; --b4: #9AA3AF; --b5: #7FC24A;
      }
      /* 라이트 테마 */
      :root[data-theme="light"] {
        --bg: #F4F6F9; --bg-grad1: #EAF0FB; --bg-grad2: #F4F6F9;
        --elev: #FFFFFF; --elev-2: #FBFCFE; --inset: #EEF1F5;
        --border: rgba(17,24,39,.08); --border-strong: rgba(17,24,39,.16);
        --text: #14161B; --text-2: #3A4250; --muted: #7B8492;
        --accent: #2F6BF6; --accent-2: #6E9BFF; --accent-weak: rgba(47,107,246,.10);
        --good: #06B6A8; --good-weak: rgba(6,182,168,.12);
        --warn: #E8910B; --warn-weak: rgba(232,145,11,.12);
        --bad: #EC3B53; --bad-weak: rgba(236,59,83,.10);
        --shadow-1: 0 1px 3px rgba(20,30,55,.06), 0 1px 2px rgba(20,30,55,.04);
        --shadow-2: 0 8px 28px rgba(20,30,55,.10);
        --ball-bg-mix: #ffffff; --ball-text: #15171c; --ball-mode-solid: 1;
      }
      /* 다크 테마 */
      :root[data-theme="dark"] {
        --bg: #07080B; --bg-grad1: #0E1018; --bg-grad2: #07080B;
        --elev: #121319; --elev-2: #171922; --inset: #1C1F29;
        --border: rgba(255,255,255,.08); --border-strong: rgba(255,255,255,.16);
        --text: #ECEEF3; --text-2: #B4BcC9; --muted: #6C7585;
        --accent: #4D8DFF; --accent-2: #7FB0FF; --accent-weak: rgba(77,141,255,.14);
        --good: #1BD4C2; --good-weak: rgba(27,212,194,.12);
        --warn: #FBBF24; --warn-weak: rgba(251,191,36,.12);
        --bad: #FB5870; --bad-weak: rgba(251,88,112,.12);
        --shadow-1: 0 1px 3px rgba(0,0,0,.4);
        --shadow-2: 0 12px 40px rgba(0,0,0,.5);
        --ball-bg-mix: #14161d; --ball-text: #14161d; --ball-mode-solid: 0;
      }

      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html { scroll-behavior: smooth; }
      body {
        font-family: var(--font-sans);
        color: var(--text);
        background:
          radial-gradient(1200px 600px at 80% -10%, var(--bg-grad1), transparent 60%),
          var(--bg-grad2);
        background-attachment: fixed;
        min-height: 100vh;
        -webkit-font-smoothing: antialiased;
        transition: background-color .25s ease, color .25s ease;
      }
      a { color: var(--accent); text-decoration: none; }
      ::selection { background: var(--accent-weak); }

      /* 스크롤바 */
      ::-webkit-scrollbar { width: 9px; height: 9px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: var(--r-pill); }
      ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

      /* ========== 상단 네비 ========== */
      .app-nav {
        position: sticky; top: 0; z-index: 50;
        display: flex; align-items: center; gap: 14px;
        height: 60px; padding: 0 22px;
        background: color-mix(in srgb, var(--elev) 78%, transparent);
        backdrop-filter: saturate(160%) blur(16px);
        -webkit-backdrop-filter: saturate(160%) blur(16px);
        border-bottom: 1px solid var(--border);
      }
      .brand { display: flex; align-items: center; gap: 11px; flex-shrink: 0; }
      .brand-mark {
        width: 34px; height: 34px; border-radius: 10px;
        display: grid; place-items: center;
        font: 800 16px/1 var(--font-mono); color: #fff;
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
        box-shadow: 0 4px 14px var(--accent-weak);
      }
      .brand-name { font-size: 16px; font-weight: 800; letter-spacing: -.3px; }
      .brand-badge {
        font: 700 10px/1 var(--font-mono); color: var(--accent);
        background: var(--accent-weak); padding: 4px 8px; border-radius: var(--r-pill);
        letter-spacing: .04em;
      }
      .nav-spacer { flex: 1; }
      .nav-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }

      /* 데이터 상태 pill */
      .status-pill {
        display: inline-flex; align-items: center; gap: 7px;
        height: 30px; padding: 0 12px; border-radius: var(--r-pill);
        font-size: 12px; font-weight: 600; color: var(--text-2);
        background: var(--inset); border: 1px solid var(--border);
      }
      .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
      .status-pill.is-ok   { color: var(--good); background: var(--good-weak); border-color: transparent; }
      .status-pill.is-ok   .status-dot { background: var(--good); box-shadow: 0 0 0 4px var(--good-weak); animation: pulse 2s infinite; }
      .status-pill.is-load { color: var(--accent); background: var(--accent-weak); border-color: transparent; }
      .status-pill.is-load .status-dot { background: var(--accent); animation: pulse 1s infinite; }
      .status-pill.is-err  { color: var(--bad); background: var(--bad-weak); border-color: transparent; }
      .status-pill.is-err  .status-dot { background: var(--bad); }
      @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

      /* 폼 컨트롤 */
      select, .btn {
        height: 38px; font-family: inherit; font-size: 13px; font-weight: 600;
        border-radius: var(--r-sm); border: 1px solid var(--border);
        background: var(--elev); color: var(--text-2);
        cursor: pointer; outline: none; transition: all .15s ease;
      }
      select { padding: 0 32px 0 12px; appearance: none; -webkit-appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%237B8492'/%3E%3C/svg%3E");
        background-repeat: no-repeat; background-position: right 11px center; }
      select:hover, .btn:hover { border-color: var(--border-strong); }
      select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-weak); }
      .btn { padding: 0 14px; }
      .btn:hover { background: var(--inset); }
      .btn:active { transform: translateY(1px); }
      .btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
      .btn-primary {
        color: #fff; border-color: transparent;
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
        box-shadow: 0 4px 16px var(--accent-weak);
      }
      .btn-primary:hover { filter: brightness(1.06); background: linear-gradient(135deg, var(--accent), var(--accent-2)); }
      .btn-icon { width: 38px; padding: 0; display: grid; place-items: center; }
      .btn-icon svg { width: 17px; height: 17px; }

      /* ========== 벤토 레이아웃 ========== */
      .bento {
        max-width: 1320px; margin: 0 auto; padding: 22px;
        display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--gap);
        align-items: start;
      }
      .span-3 { grid-column: span 3; } .span-4 { grid-column: span 4; }
      .span-5 { grid-column: span 5; } .span-6 { grid-column: span 6; }
      .span-7 { grid-column: span 7; } .span-8 { grid-column: span 8; }
      .span-12 { grid-column: span 12; }

      .card {
        background: var(--elev); border: 1px solid var(--border);
        border-radius: var(--r-lg); padding: 20px;
        box-shadow: var(--shadow-1);
      }
      .card-h {
        display: flex; align-items: center; gap: 9px;
        font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
        color: var(--muted); margin-bottom: 16px;
      }
      .card-h .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
      .card-h .sub { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 600; color: var(--text-2); font-size: 12px; }

      /* ========== 당첨번호 hero ========== */
      .hero {
        position: relative; overflow: hidden;
        background:
          radial-gradient(600px 300px at 110% -40%, var(--accent-weak), transparent 70%),
          var(--elev);
        border: 1px solid var(--border);
      }
      .hero-top { display: flex; align-items: baseline; gap: 10px; margin-bottom: 18px; }
      .hero-round { font: 800 22px/1 var(--font-sans); letter-spacing: -.4px; }
      .hero-round b { color: var(--accent); font-family: var(--font-mono); }
      .hero-date { margin-left: auto; font-size: 12px; color: var(--muted); font-family: var(--font-mono); }
      .hero-balls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
      .hero-plus { font: 700 22px/1 var(--font-mono); color: var(--muted); margin: 0 2px; }
      .hero-note { color: var(--text-2); font-size: 14px; line-height: 1.7; }
      .hero-mini { display: flex; gap: 22px; margin-top: 18px; padding-top: 16px; border-top: 1px dashed var(--border); flex-wrap: wrap; }
      .hero-mini .mv { font: 700 20px/1 var(--font-mono); color: var(--text); }
      .hero-mini .ml { font-size: 11px; color: var(--muted); margin-top: 4px; }

      /* ========== 로또 공 ========== */
      .ball {
        --bc: var(--muted);
        position: relative; display: inline-grid; place-items: center;
        width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0;
        font: 700 15px/1 var(--font-mono);
        transition: transform .18s cubic-bezier(.34,1.56,.64,1);
      }
      .ball.lb-1 { --bc: var(--b1); } .ball.lb-2 { --bc: var(--b2); }
      .ball.lb-3 { --bc: var(--b3); } .ball.lb-4 { --bc: var(--b4); }
      .ball.lb-5 { --bc: var(--b5); }
      .ball:hover { transform: translateY(-3px) scale(1.06); }
      /* 라이트: 공식색 솔리드 + 내부 하이라이트 */
      :root[data-theme="light"] .ball {
        background: radial-gradient(circle at 34% 30%, color-mix(in srgb, var(--bc) 60%, #fff), var(--bc));
        color: #1c1d22; box-shadow: 0 3px 10px color-mix(in srgb, var(--bc) 40%, transparent);
      }
      /* 다크: 어두운 바탕 + 색은 테두리/숫자/글로우에만 (퀀트 배지) */
      :root[data-theme="dark"] .ball {
        background: var(--ball-bg-mix); color: var(--bc);
        border: 1.5px solid color-mix(in srgb, var(--bc) 70%, transparent);
        box-shadow: inset 0 0 14px -6px var(--bc), 0 0 0 1px rgba(0,0,0,.3);
      }
      .ball.sm { width: 34px; height: 34px; font-size: 12px; }
      .ball.is-bonus::after {
        content: 'B'; position: absolute; top: -5px; right: -5px;
        width: 17px; height: 17px; border-radius: 50%;
        font: 700 9px/1 var(--font-mono); display: grid; place-items: center;
        background: var(--accent); color: #fff; border: 2px solid var(--elev);
      }
      .ball.is-hit { outline: 2px solid var(--good); outline-offset: 2px; }

      /* ========== KPI 미니 ========== */
      .kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .kpi {
        background: var(--elev-2); border: 1px solid var(--border);
        border-radius: var(--r-md); padding: 15px 16px;
        transition: transform .15s, box-shadow .15s, border-color .15s;
      }
      .kpi:hover { transform: translateY(-2px); box-shadow: var(--shadow-1); border-color: var(--border-strong); }
      .kpi .v { font: 700 26px/1 var(--font-mono); letter-spacing: -1px; color: var(--text); }
      .kpi .v small { font-size: 13px; color: var(--muted); font-weight: 600; }
      .kpi .l { font-size: 11px; color: var(--muted); font-weight: 600; margin-top: 7px; }
      .kpi.accent .v { color: var(--accent); }
      .kpi.good .v { color: var(--good); }
      .kpi .trk { height: 3px; border-radius: var(--r-pill); background: var(--inset); margin-top: 9px; overflow: hidden; }
      .kpi .trk i { display: block; height: 100%; border-radius: var(--r-pill); background: var(--accent); transition: width 1s cubic-bezier(.22,1,.36,1); }
      .kpi.good .trk i { background: var(--good); }

      /* ========== 예측 카드 ========== */
      .pred-summary { font-size: 13px; color: var(--text-2); margin-bottom: 16px; display: flex; gap: 16px; flex-wrap: wrap; }
      .pred-summary b { color: var(--text); font-family: var(--font-mono); }
      .pred-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 13px; }
      .pred-card {
        background: var(--elev-2); border: 1px solid var(--border);
        border-radius: var(--r-md); padding: 16px 17px;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        animation: rise .4s ease both;
      }
      .pred-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-2); border-color: var(--accent); }
      @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      .pc-top { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
      .pc-set { font: 800 13px/1 var(--font-mono); letter-spacing: .06em; color: var(--text); }
      .pc-src {
        font: 700 10px/1 var(--font-mono); letter-spacing: .03em;
        padding: 5px 9px; border-radius: var(--r-pill);
        background: var(--accent-weak); color: var(--accent);
      }
      .pc-src.s-ml { background: var(--good-weak); color: var(--good); }
      .pc-src.s-pool { background: var(--accent-weak); color: var(--accent); }
      .pc-src.s-monte { background: var(--warn-weak); color: var(--warn); }
      .pc-ring { margin-left: auto; }
      .ring {
        --p: 0; width: 40px; height: 40px; border-radius: 50%;
        display: grid; place-items: center;
        background: conic-gradient(var(--accent) calc(var(--p) * 1%), var(--inset) 0);
      }
      .ring::before { content: ''; grid-area: 1/1; width: 30px; height: 30px; border-radius: 50%; background: var(--elev-2); }
      .ring span { grid-area: 1/1; font: 700 10px/1 var(--font-mono); color: var(--text-2); }
      .pc-balls { display: flex; gap: 8px; flex-wrap: wrap; }
      .pc-foot { display: flex; align-items: center; gap: 8px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); flex-wrap: wrap; }
      .pc-wait { font-size: 12px; color: var(--muted); }

      /* 칩/배지 */
      .chip { font: 700 11px/1 var(--font-mono); padding: 5px 9px; border-radius: var(--r-pill); }
      .chip-ok { background: var(--good-weak); color: var(--good); }
      .chip-warn { background: var(--warn-weak); color: var(--warn); }
      .chip-bad { background: var(--bad-weak); color: var(--bad); }
      .chip-neutral { background: var(--inset); color: var(--muted); }
      .match-badge { font: 700 11px/1 var(--font-mono); padding: 5px 9px; border-radius: var(--r-pill); background: var(--inset); color: var(--text-2); }
      .match-badge.hi { background: var(--good-weak); color: var(--good); }
      .rank-badge { font: 700 11px/1 var(--font-mono); padding: 5px 9px; border-radius: var(--r-pill); color: #fff; }
      .rk-1 { background: #E0A100; } .rk-2 { background: #9AA3AF; } .rk-3 { background: #C77B3B; }
      .rk-4 { background: var(--good); } .rk-5 { background: var(--accent); }

      /* ========== 분포 차트 ========== */
      .bar-chart { display: flex; gap: 7px; align-items: flex-end; height: 150px; padding: 14px 8px 26px; }
      .bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; position: relative; }
      .bar { width: 100%; max-width: 38px; border-radius: 5px 5px 0 0; min-height: 4px;
        background: linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 45%, transparent));
        position: relative; transition: height 1s cubic-bezier(.22,1,.36,1); }
      .bar.hi { background: linear-gradient(180deg, var(--good), color-mix(in srgb, var(--good) 45%, transparent)); }
      .bar-v { position: absolute; top: -18px; left: 50%; transform: translateX(-50%); font: 700 11px/1 var(--font-mono); color: var(--text-2); }
      .bar-l { position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%); font: 500 11px/1 var(--font-mono); color: var(--muted); white-space: nowrap; }

      /* 미니 통계 행 */
      .stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 11px; }
      .stat-cell { background: var(--elev-2); border: 1px solid var(--border); border-radius: var(--r-md); padding: 14px; text-align: center; }
      .stat-cell .v { font: 700 22px/1 var(--font-mono); letter-spacing: -.5px; color: var(--accent); }
      .stat-cell .l { font-size: 11px; color: var(--muted); margin-top: 6px; font-weight: 600; }

      /* details (진행적 공개) */
      details.disc { background: var(--elev); border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; }
      details.disc > summary {
        list-style: none; cursor: pointer; padding: 15px 18px;
        font-size: 13px; font-weight: 700; color: var(--text-2);
        display: flex; align-items: center; gap: 9px;
      }
      details.disc > summary::-webkit-details-marker { display: none; }
      details.disc > summary::after { content: '+'; margin-left: auto; font: 700 16px/1 var(--font-mono); color: var(--muted); }
      details.disc[open] > summary::after { content: '–'; }
      details.disc[open] > summary { border-bottom: 1px solid var(--border); }
      .disc-body { padding: 16px 18px; }

      /* 데이터 테이블(로그) */
      .data-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
      .data-table th { text-align: left; padding: 9px 11px; font: 700 11px/1 var(--font-mono); letter-spacing: .04em;
        text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--elev); }
      .data-table td { padding: 9px 11px; border-bottom: 1px solid var(--border); color: var(--text-2); vertical-align: middle; }
      .data-table tr:last-child td { border-bottom: none; }
      .data-table tbody tr:hover td { background: var(--accent-weak); }
      .table-scroll { max-height: 420px; overflow: auto; border-radius: var(--r-sm); border: 1px solid var(--border); }

      /* 필터 경고 */
      .warn-card { background: var(--bad-weak); border: 1px solid color-mix(in srgb, var(--bad) 30%, transparent); border-radius: var(--r-md); padding: 15px 18px; }
      .warn-card .wt { display: flex; align-items: center; gap: 9px; font-weight: 700; color: var(--bad); font-size: 14px; }
      .warn-card .wl { margin-top: 8px; font-size: 12px; color: var(--bad); display: flex; flex-wrap: wrap; gap: 6px; }

      /* 상태(로딩/빈/오류) */
      .state { padding: 38px 20px; text-align: center; color: var(--muted); }
      .state .spinner { width: 30px; height: 30px; margin: 0 auto 12px; border-radius: 50%;
        border: 3px solid var(--inset); border-top-color: var(--accent); animation: spin .85s linear infinite; }
      @keyframes spin { to { transform: rotate(360deg); } }
      .state-err { color: var(--bad); }

      /* 스켈레톤(예측 생성 중) */
      .skel-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 13px; }
      .skel { background: var(--elev-2); border: 1px solid var(--border); border-radius: var(--r-md); padding: 16px; height: 132px; position: relative; overflow: hidden; }
      .skel::after { content: ''; position: absolute; inset: 0;
        background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 8%, transparent), transparent);
        transform: translateX(-100%); animation: shimmer 1.3s infinite; }
      @keyframes shimmer { to { transform: translateX(100%); } }
      .gen-status { text-align: center; color: var(--accent); font: 600 13px/1.5 var(--font-mono); margin-bottom: 14px; }
      .gen-status .seq { color: var(--text-2); }

      /* 토스트 */
      .toast-host { position: fixed; right: 18px; bottom: 18px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; }
      .toast {
        min-width: 240px; max-width: 380px; padding: 13px 16px; border-radius: var(--r-md);
        background: var(--elev); border: 1px solid var(--border); box-shadow: var(--shadow-2);
        color: var(--text); font-size: 13px; line-height: 1.5;
        display: flex; gap: 11px; align-items: flex-start;
        animation: toastIn .3s cubic-bezier(.22,1,.36,1) both;
      }
      .toast.out { animation: toastOut .25s ease forwards; }
      .toast .tbar { width: 4px; align-self: stretch; border-radius: var(--r-pill); background: var(--accent); flex-shrink: 0; }
      .toast.ok .tbar { background: var(--good); } .toast.err .tbar { background: var(--bad); } .toast.warn .tbar { background: var(--warn); }
      .toast .tx b { display: block; margin-bottom: 2px; font-size: 13px; }
      .toast .tx span { color: var(--text-2); font-size: 12px; white-space: pre-line; }
      @keyframes toastIn { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
      @keyframes toastOut { to { opacity: 0; transform: translateX(40px); } }

      /* 저장 오버레이 */
      .save-overlay { position: fixed; inset: 0; z-index: 9998; display: none; place-items: center;
        background: color-mix(in srgb, var(--bg) 70%, transparent); backdrop-filter: blur(3px); }
      .save-overlay.active { display: grid; }
      .save-msg { background: var(--elev); border: 1px solid var(--border); padding: 26px 34px; border-radius: var(--r-lg); text-align: center; box-shadow: var(--shadow-2); }
      .save-msg .spinner { width: 30px; height: 30px; margin: 0 auto 12px; border-radius: 50%; border: 3px solid var(--inset); border-top-color: var(--accent); animation: spin .85s linear infinite; }

      /* ========== 반응형 ========== */
      @media (max-width: 1100px) {
        .span-7, .span-8 { grid-column: span 12; }
        .span-5 { grid-column: span 12; }
        .span-3, .span-4 { grid-column: span 6; }
      }
      @media (max-width: 720px) {
        .bento { padding: 14px; gap: 13px; }
        .app-nav { height: auto; padding: 10px 14px; flex-wrap: wrap; }
        .span-3, .span-4, .span-6 { grid-column: span 12; }
        .ball { width: 40px; height: 40px; font-size: 14px; }
        .nav-controls { width: 100%; }
        select { flex: 1; }
      }
    </style>
</head>
<body>
    <!-- 토스트 -->
    <div class="toast-host" id="toastHost"></div>

    <!-- 저장 오버레이 -->
    <div class="save-overlay" id="saveOverlay">
        <div class="save-msg">
            <div class="spinner"></div>
            <p style="font-size:14px; color:var(--text-2);">화면을 저장하는 중입니다...</p>
        </div>
    </div>

    <!-- 상단 네비 -->
    <nav class="app-nav">
        <div class="brand">
            <div class="brand-mark">L</div>
            <span class="brand-name">로또 오라클</span>
            <span class="brand-badge">AI ANALYTICS</span>
        </div>
        <div class="nav-spacer"></div>
        <div class="nav-controls">
            <span class="status-pill" id="statusPill"><span class="status-dot"></span><span id="statusText">연결 확인 중</span></span>
            <select id="roundSelect"><option value="">회차 선택...</option></select>
            <button class="btn" onclick="loadRoundData()">조회</button>
            <button class="btn" onclick="loadLatestRound()">최신</button>
            <button class="btn btn-primary" id="genBtn" onclick="generateNewPredictions(this)">새 예측 생성</button>
            <button class="btn btn-icon" title="화면 저장" onclick="saveScreenshot()" aria-label="저장">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            </button>
            <button class="btn btn-icon" id="themeBtn" title="테마 전환" onclick="toggleTheme()" aria-label="테마 전환"></button>
        </div>
    </nav>

    <!-- 벤토 본문 -->
    <main class="bento" id="dashboardContainer">

        <!-- 필터 경고 (필요 시) -->
        <div class="span-12" id="filterWarningWrap" style="display:none;">
            <div class="warn-card" id="filterWarning">
                <div class="wt">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    <span id="warningMessage"></span>
                </div>
                <div class="wl" id="failedFiltersList"></div>
            </div>
        </div>

        <!-- Row 1: 당첨번호 hero -->
        <section class="card hero span-7" id="winningSection">
            <div class="state"><div class="spinner"></div><p>당첨번호를 불러오는 중...</p></div>
        </section>

        <!-- Row 1: KPI 미니 -->
        <section class="card span-5" id="kpiSection">
            <div class="card-h"><span class="dot"></span>핵심 지표<span class="sub" id="kpiSub"></span></div>
            <div class="kpi-grid" id="kpiGrid">
                <div class="state" style="grid-column:1/-1;"><div class="spinner"></div><p>지표 로딩 중...</p></div>
            </div>
        </section>

        <!-- Row 2: 예측 카드 (주인공) -->
        <section class="card span-12" id="predictionsSection">
            <div class="card-h"><span class="dot"></span>이번 회차 AI 예측<span class="sub" id="predictionsSummary"></span></div>
            <div id="predictionsContent">
                <div class="state"><div class="spinner"></div><p>예측을 불러오는 중...</p></div>
            </div>
        </section>

        <!-- Row 3: 통계 영역 -->
        <section class="span-12" id="statsSection" style="display:grid; grid-template-columns: repeat(12,1fr); gap: var(--gap);">
            <div class="card span-5" id="distCard">
                <div class="card-h"><span class="dot"></span>맞춘 개수 분포</div>
                <div id="distChart"><div class="state">데이터 대기 중</div></div>
            </div>
            <div class="card span-4" id="backtestCard">
                <div class="card-h"><span class="dot"></span>백테스트 성능</div>
                <div id="backtestGrid"><div class="state"><div class="spinner"></div><p>로딩 중...</p></div></div>
            </div>
            <div class="card span-3" id="optimizerCard">
                <div class="card-h"><span class="dot"></span>자동 튜닝 현황 (Optuna)</div>
                <div id="optimizerStatusGrid"><div class="state"><div class="spinner"></div></div></div>
            </div>

            <!-- [지속학습 가시화 2026-07-04] 회차별 실측 추이 - "회차가 쌓일수록 좋아지는가" 확인용 -->
            <div class="card span-12" id="trendCard">
                <div class="card-h"><span class="dot"></span>회차별 실측 추이<span class="sub" id="trendSub"></span></div>
                <div id="trendChart"><div class="state">데이터 대기 중</div></div>
            </div>

            <div class="span-12" id="discWrap" style="display:flex; flex-direction:column; gap: var(--gap);">
                <details class="disc" id="logDetails">
                    <summary>전체 예측 로그 (회차별 상세)</summary>
                    <div class="disc-body" id="logBody"></div>
                </details>
                <details class="disc" id="officialDetails" style="display:none;">
                    <summary>공식 당첨통계 vs 내 예측 비교</summary>
                    <div class="disc-body" id="officialBody"></div>
                </details>
                <details class="disc" id="optHistDetails">
                    <summary>최적화 이력 / 시스템 분석</summary>
                    <div class="disc-body">
                        <div id="basicStatsGrid" style="margin-bottom:16px;"></div>
                        <div id="optimizerHistoryTable"></div>
                    </div>
                </details>
            </div>
        </section>

    </main>

    <script>
        let currentRound = null;
        let allRounds = [];
        let genStatusTimer = null;

        // ===== 공통 헬퍼 =====
        function escapeHtml(value) {
            if (value === null || value === undefined) return '';
            return String(value)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        // 모든 fetch를 통일: 타임아웃 + ok검사 + 파싱가드 -> {ok, data, error}
        async function fetchJson(url, opts) {
            opts = opts || {};
            const ctrl = new AbortController();
            const t = setTimeout(() => ctrl.abort(), opts.timeout || 20000);
            try {
                const res = await fetch(url, Object.assign({ signal: ctrl.signal }, opts));
                let data = null;
                try { data = await res.json(); } catch (e) { data = null; }
                if (!res.ok) {
                    const msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
                    return { ok: false, status: res.status, data: data, error: msg };
                }
                if (data && data.error) return { ok: false, status: res.status, data: data, error: (data.error_message || data.error) };
                return { ok: true, status: res.status, data: data, error: null };
            } catch (e) {
                return { ok: false, status: 0, data: null, error: (e.name === 'AbortError' ? '요청 시간 초과' : '서버에 연결할 수 없습니다') };
            } finally { clearTimeout(t); }
        }

        function setState(id, kind, msg) {
            const el = document.getElementById(id);
            if (!el) return;
            if (kind === 'loading') el.innerHTML = '<div class="state"><div class="spinner"></div><p>' + escapeHtml(msg || '불러오는 중...') + '</p></div>';
            else if (kind === 'empty') el.innerHTML = '<div class="state">' + escapeHtml(msg || '표시할 데이터가 없습니다.') + '</div>';
            else if (kind === 'error') el.innerHTML = '<div class="state state-err">' + escapeHtml(msg || '데이터를 불러올 수 없습니다.') + '</div>';
        }

        function setStatus(kind, text) {
            const pill = document.getElementById('statusPill');
            const txt = document.getElementById('statusText');
            pill.className = 'status-pill ' + (kind === 'ok' ? 'is-ok' : kind === 'error' ? 'is-err' : 'is-load');
            txt.textContent = text;
        }

        // 토스트
        function toast(title, message, type) {
            const host = document.getElementById('toastHost');
            const el = document.createElement('div');
            el.className = 'toast ' + (type || 'info');
            el.innerHTML = '<div class="tbar"></div><div class="tx"><b>' + escapeHtml(title) + '</b>' +
                (message ? '<span>' + escapeHtml(message) + '</span>' : '') + '</div>';
            host.appendChild(el);
            setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 250); }, type === 'err' ? 6000 : 4000);
        }

        // 테마 전환
        const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>';
        const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
        function applyThemeIcon() {
            const cur = document.documentElement.getAttribute('data-theme');
            const btn = document.getElementById('themeBtn');
            if (btn) btn.innerHTML = (cur === 'dark') ? SUN : MOON;
        }
        function toggleTheme() {
            const cur = document.documentElement.getAttribute('data-theme');
            const next = (cur === 'dark') ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            try { localStorage.setItem('lotto-theme', next); } catch (e) {}
            applyThemeIcon();
        }

        // 공 색상대(1-10,11-20,...) 클래스
        function ballZone(n) { return n <= 10 ? 1 : n <= 20 ? 2 : n <= 30 ? 3 : n <= 40 ? 4 : 5; }
        function ballHtml(n, opts) {
            opts = opts || {};
            let cls = 'ball lb-' + ballZone(n);
            if (opts.sm) cls += ' sm';
            if (opts.hit) cls += ' is-hit';
            if (opts.bonus) cls += ' is-bonus';
            return '<span class="' + cls + '">' + n + '</span>';
        }

        // ===== 서버 필터 기준 로드 (배지 검증용) =====
        window.FILTER_CRITERIA = { sum_min: 45, sum_max: 235, max_consecutive: 5 };
        fetchJson('/api/filter-criteria').then(r => { if (r.ok && r.data) window.FILTER_CRITERIA = r.data; });

        // 필터 검증 -> 칩 HTML
        function filterChip(numbers, source) {
            if (!numbers || numbers.length !== 6 || new Set(numbers).size !== 6)
                return '<span class="chip chip-bad">무효</span>';
            if (!numbers.every(n => n >= 1 && n <= 45))
                return '<span class="chip chip-bad">범위초과</span>';
            const failed = [];
            const oddCount = numbers.filter(n => n % 2 === 1).length;
            if (oddCount === 0 || oddCount === 6) failed.push('홀짝');
            const sum = numbers.reduce((a, b) => a + b, 0);
            const fc = window.FILTER_CRITERIA || {};
            if (sum < (fc.sum_min || 45) || sum > (fc.sum_max || 235)) failed.push('합계');
            const sorted = [...numbers].sort((a, b) => a - b);
            let run = 0, maxRun = 0;
            for (let i = 0; i < sorted.length - 1; i++) {
                if (sorted[i + 1] - sorted[i] === 1) { run++; maxRun = Math.max(maxRun, run + 1); }
                else run = 0;
            }
            if (maxRun > (fc.max_consecutive || 5)) failed.push('연속');
            if (failed.length === 0) return '<span class="chip chip-ok">통과</span>';
            if (source && source.startsWith('ML/')) {
                const critical = failed.filter(f => f === '홀짝' || f === '합계');
                return critical.length === 0
                    ? '<span class="chip chip-warn">완화</span>'
                    : '<span class="chip chip-bad">중요</span>';
            }
            return '<span class="chip chip-bad">미통과</span>';
        }

        // ===== 초기화 =====
        window.onload = async function () {
            applyThemeIcon();
            setStatus('load', '데이터 로딩 중');
            await loadQuickPredictionStatus();
            await loadRounds();
            await loadLatestRound();

            setInterval(() => {
                const s = document.getElementById('statsSection');
                if (s && s.style.display !== 'none') loadOptimizerStatus();
            }, 30000);
            setInterval(loadQuickPredictionStatus, 60000);
        };

        // 빠른 예측 상태 -> 상태 pill 보강
        async function loadQuickPredictionStatus() {
            const r = await fetchJson('/api/quick-prediction-status');
            if (!r.ok || !r.data) return;
            const d = r.data;
            if (d.quick_prediction_available) {
                const ready = d.cache_valid;
                window.__quickInfo = d;
            }
        }

        // 회차 목록
        async function loadRounds() {
            const r = await fetchJson('/api/rounds');
            const select = document.getElementById('roundSelect');
            if (!r.ok || !Array.isArray(r.data)) {
                setStatus('error', '서버 연결 실패');
                toast('회차 목록 로드 실패', r.error || '서버 연결을 확인해주세요.', 'err');
                return;
            }
            allRounds = r.data;
            select.innerHTML = '<option value="">회차 선택...</option>';
            allRounds.forEach(round => {
                const o = document.createElement('option');
                o.value = round; o.textContent = round + '회차';
                select.appendChild(o);
            });
        }

        async function loadLatestRound() {
            if (allRounds && allRounds.length > 0) {
                document.getElementById('roundSelect').value = allRounds[0];
                await loadWeekData();
            } else {
                setStatus('error', '회차 데이터 없음');
            }
        }

        async function loadRoundData() { await loadWeekData(); }

        // 회차(주간) 데이터 로드
        async function loadWeekData() {
            const roundNum = document.getElementById('roundSelect').value;
            if (!roundNum) { toast('회차를 선택해주세요', '', 'warn'); return; }
            currentRound = roundNum;
            setStatus('load', roundNum + '회차 로딩 중');
            setState('predictionsContent', 'loading', '예측을 불러오는 중...');

            const r = await fetchJson('/api/week-predictions/' + roundNum);
            if (!r.ok) {
                setStatus('error', '로드 실패');
                setState('winningSection', 'error', '당첨번호를 불러올 수 없습니다.');
                setState('predictionsContent', 'error', r.error || '예측 데이터를 불러올 수 없습니다.');
                toast('데이터 로드 실패', r.error || '서버 연결을 확인해주세요.', 'err');
                return;
            }
            const data = r.data || {};
            setStatus('ok', roundNum + '회차 · 정상');
            displayWinningNumbers(data.winning_numbers, roundNum);
            displayFilterWarning(data.filter_validation);
            displayWeekPredictions(data);
            displayKpis(data);
            showStatistics();
        }

        // 필터 경고
        function displayFilterWarning(validation) {
            const wrap = document.getElementById('filterWarningWrap');
            const msg = document.getElementById('warningMessage');
            const list = document.getElementById('failedFiltersList');
            if (validation && !validation.passed) {
                wrap.style.display = '';
                msg.textContent = validation.warning_message || '당첨번호가 필터에 의해 제외되었습니다.';
                list.innerHTML = '';
                if (validation.failed_filters && validation.failed_filters.length) {
                    validation.failed_filters.forEach(f => {
                        list.innerHTML += '<span class="chip chip-bad">' + escapeHtml(f) + '</span>';
                    });
                }
            } else {
                wrap.style.display = 'none';
            }
        }

        // 당첨번호 hero
        function displayWinningNumbers(winning, roundNum) {
            const sec = document.getElementById('winningSection');
            if (!winning) {
                sec.innerHTML =
                    '<div class="hero-top"><div class="hero-round">제 <b>' + escapeHtml(roundNum) + '</b>회</div>' +
                    '<div class="hero-date">추첨 예정 · 토 20:45</div></div>' +
                    '<div class="hero-note">아직 추첨되지 않은 회차입니다.<br>아래 AI 예측 5세트를 미리 확인하세요.</div>';
                return;
            }
            let balls = '';
            (winning.numbers || []).forEach(n => { balls += ballHtml(n); });
            balls += '<span class="hero-plus">+</span>' + ballHtml(winning.bonus, { bonus: true });
            sec.innerHTML =
                '<div class="hero-top"><div class="hero-round">제 <b>' + escapeHtml(winning.round) + '</b>회 당첨번호</div>' +
                '<div class="hero-date">' + escapeHtml(winning.date || '') + '</div></div>' +
                '<div class="hero-balls">' + balls + '</div>' +
                '<div class="hero-mini" id="heroMini"></div>';
        }

        // 예측 카드 + 로그 테이블 + 통계용 데이터 보관
        function displayWeekPredictions(data) {
            const content = document.getElementById('predictionsContent');
            const summary = document.getElementById('predictionsSummary');
            const preds = data.all_predictions || [];

            if (!preds.length) {
                summary.textContent = '';
                setState('predictionsContent', 'empty', '이 회차의 예측 데이터가 없습니다. "새 예측 생성"을 눌러보세요.');
                return;
            }

            const win = data.winning_numbers;
            summary.innerHTML = '예측기간 <b>' + (data.date_count || 0) + '</b>일 · 총 <b>' + (data.total_predictions || preds.length) + '</b>세트';

            // 날짜별 그룹 -> 최신 날짜 세트를 카드로 강조
            const byDate = {};
            preds.forEach(p => { const k = p.date || '-'; (byDate[k] = byDate[k] || []).push(p); });
            const dateKeys = Object.keys(byDate).sort();
            const featured = byDate[dateKeys[dateKeys.length - 1]] || preds;

            // 예측 카드
            let cards = '';
            featured.slice(0, 12).forEach((pred, i) => {
                const conf = Math.round((pred.confidence || 0) * 100);
                let balls = '';
                (pred.numbers || []).forEach(n => {
                    const hit = win && win.numbers && win.numbers.includes(n);
                    const bonus = win && n === win.bonus;
                    balls += ballHtml(n, { hit: hit, bonus: bonus });
                });
                const srcRaw = pred.source || '';
                const srcKind = srcRaw.startsWith('ML') ? 's-ml' : /monte/i.test(srcRaw) ? 's-monte' : 'pool';
                const srcLabel = escapeHtml((srcRaw.split('/')[0]) || 'AI');
                let foot;
                if (win) {
                    const m = pred.matches || 0;
                    foot = '<span class="match-badge ' + (m >= 3 ? 'hi' : '') + '">' + m + '개 일치</span>' +
                        (pred.rank ? '<span class="rank-badge rk-' + pred.rank + '">' + pred.rank + '등</span>' : '') +
                        filterChip(pred.numbers, srcRaw);
                } else {
                    foot = '<span class="pc-wait">추첨 대기</span>' + filterChip(pred.numbers, srcRaw);
                }
                cards +=
                    '<div class="pred-card" style="animation-delay:' + (i * 0.04) + 's">' +
                    '<div class="pc-top"><span class="pc-set">SET ' + (i + 1) + '</span>' +
                    '<span class="pc-src ' + (srcKind === 'pool' ? 's-pool' : srcKind) + '" title="' + escapeHtml(srcRaw) + '">' + srcLabel + '</span>' +
                    '<span class="pc-ring" title="AI 점수 (당첨 확률 아님 · 패턴 적합도+ML 혼합 점수)"><span class="ring" style="--p:' + conf + '"><span>' + conf + '</span></span></span></div>' +
                    '<div class="pc-balls">' + balls + '</div>' +
                    '<div class="pc-foot">' + foot + '</div></div>';
            });
            content.innerHTML = '<div style="font-size:11px;color:var(--muted);margin-bottom:12px;">각 카드 우측 원형 수치 = <b style="color:var(--text-2);">AI 점수</b> (패턴 적합도 + ML 혼합 · 당첨 확률 아님)</div><div class="pred-grid">' + cards + '</div>';

            // 전체 로그 테이블(진행적 공개)
            renderLogTable(preds, win);

            // 공식 통계 비교 + hero mini + 성과 보관
            renderInsights(data, preds);
        }

        function renderLogTable(preds, win) {
            const body = document.getElementById('logBody');
            let rows = '';
            preds.forEach(p => {
                let balls = '';
                (p.numbers || []).forEach(n => {
                    const hit = win && win.numbers && win.numbers.includes(n);
                    balls += ballHtml(n, { sm: true, hit: hit });
                });
                const conf = ((p.confidence || 0) * 100).toFixed(1);
                rows +=
                    '<tr><td style="white-space:nowrap;">' + escapeHtml(p.date || '') + '</td>' +
                    '<td style="text-align:center;">' + escapeHtml(p.round) + '</td>' +
                    '<td><div style="display:flex;gap:4px;flex-wrap:wrap;">' + balls + '</div></td>' +
                    '<td style="font-family:var(--font-mono);">' + conf + '%</td>' +
                    '<td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(p.source) + '">' + escapeHtml(p.source) + '</td>' +
                    '<td>' + (win ? (p.matches || 0) + '개' : '-') + '</td>' +
                    '<td>' + (win && p.rank ? '<span class="rank-badge rk-' + p.rank + '">' + p.rank + '등</span>' : '-') + '</td>' +
                    '<td>' + filterChip(p.numbers, p.source || '') + '</td></tr>';
            });
            body.innerHTML =
                '<div class="table-scroll"><table class="data-table"><thead><tr>' +
                '<th>날짜</th><th>회차</th><th>예측 번호</th><th>AI 점수</th><th>출처</th><th>일치</th><th>등수</th><th>필터</th>' +
                '</tr></thead><tbody>' + rows + '</tbody></table></div>';
        }

        // 성과/공식통계 비교 + hero mini
        function renderInsights(data, preds) {
            const win = data.winning_numbers;
            const total = preds.length;
            let totalMatches = 0, maxMatches = 0;
            const rankCounts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
            preds.forEach(p => {
                const m = p.matches || 0;
                totalMatches += m; maxMatches = Math.max(maxMatches, m);
                if (p.rank) rankCounts[p.rank]++;
            });

            if (win) {
                const avg = (totalMatches / total).toFixed(2);
                const threePlus = preds.filter(p => (p.matches || 0) >= 3).length;
                const heroMini = document.getElementById('heroMini');
                if (heroMini) {
                    // [2026-06-28 코드리뷰 P3] 분모(=해당 회차 누적 예측 세트수)를 라벨에 명시.
                    //   avg/최고/3+ 는 5세트가 아니라 'total'세트 누적 집계라 '5세트 성과'로 오인 소지 -> 세트수 표기.
                    heroMini.innerHTML =
                        '<div><div class="mv">' + avg + '</div><div class="ml">평균 일치 (' + total + '세트)</div></div>' +
                        '<div><div class="mv">' + maxMatches + '</div><div class="ml">최고 일치</div></div>' +
                        '<div><div class="mv">' + threePlus + '</div><div class="ml">3개+ 적중</div></div>';
                }

                // 공식 통계 비교 (collapsible)
                const ws = data.winning_statistics;
                const det = document.getElementById('officialDetails');
                if (ws && ws.statistics && ws.total_games) {
                    det.style.display = '';
                    const s = ws.statistics, g = ws.total_games;
                    const off = {
                        1: (s.first_winners / g * 100).toFixed(6), 2: (s.second_winners / g * 100).toFixed(6),
                        3: (s.third_winners / g * 100).toFixed(4), 4: (s.fourth_winners / g * 100).toFixed(4),
                        5: (s.fifth_winners / g * 100).toFixed(2)
                    };
                    const mine = {};
                    for (let r = 1; r <= 5; r++) mine[r] = (rankCounts[r] / total * 100).toFixed(4);
                    const labels = { 1: '1등', 2: '2등', 3: '3등', 4: '4등', 5: '5등' };
                    let rrows = '';
                    [1, 2, 3, 4, 5].forEach(r => {
                        rrows += '<tr><td>' + labels[r] + '</td><td style="text-align:right;font-family:var(--font-mono);">' +
                            (s[['first', 'second', 'third', 'fourth', 'fifth'][r - 1] + '_winners'] || 0).toLocaleString() + '명</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);">' + off[r] + '%</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);color:var(--good);">' + mine[r] + '%</td></tr>';
                    });
                    document.getElementById('officialBody').innerHTML =
                        '<div class="table-scroll" style="max-height:none;"><table class="data-table"><thead><tr>' +
                        '<th>등수</th><th style="text-align:right;">공식 당첨자</th><th style="text-align:right;">공식 확률</th><th style="text-align:right;">내 예측 비율</th>' +
                        '</tr></thead><tbody>' + rrows + '</tbody></table></div>' +
                        '<div style="margin-top:10px;font-size:12px;color:var(--muted);">총 판매 ' + g.toLocaleString() + '게임 기준 · 내 예측 ' + total + '세트의 등수 분포 비교</div>';
                } else {
                    det.style.display = 'none';
                }
            } else {
                const det = document.getElementById('officialDetails');
                if (det) det.style.display = 'none';
            }
        }

        // 시스템 핵심 지표(통과율/극단성 풀) - 회차 무관, 파일 기반이라 1회만 로드 후 캐시
        let __sysMetrics = null;
        async function loadSystemMetrics() {
            if (__sysMetrics) return __sysMetrics;
            const [inc, ext] = await Promise.all([
                fetchJson('/api/inclusion-rate'),
                fetchJson('/api/extremeness-pool')
            ]);
            const incData = (inc.ok && inc.data && inc.data.data) ? inc.data.data : null;
            __sysMetrics = {
                inclusion: incData && incData.overall ? incData.overall : null,
                pool: (ext.ok && ext.data && !ext.data.error) ? ext.data : null
            };
            return __sysMetrics;
        }
        function fmtK(n) {
            if (n == null) return '—';
            return n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + 'M' : Math.round(n / 1e3) + 'K';
        }

        // KPI 미니카드 (Row1) - 이 시스템의 진짜 핵심 지표 (당첨 예측 정확도가 아님)
        async function displayKpis(data) {
            const grid = document.getElementById('kpiGrid');
            document.getElementById('kpiSub').textContent = currentRound ? currentRound + '회차' : '';
            const m = await loadSystemMetrics();
            const preds = data.all_predictions || [];
            const win = data.winning_numbers;

            // 1) 필터 통과율(참고): (구)16필터가 역사적 당첨번호를 보존하는 비율.
            //    실제 예측에 쓰는 극단성 풀과는 별개 지표라 '참고'로 명시(2026-05-31 사용자 결정: 통과율은 강제목표 아닌 참고지표).
            const inc = m.inclusion;
            const inclPct = inc ? (inc.inclusion_rate * 100).toFixed(1) : null;
            const inclSub = inc ? (inc.passed + '/' + (inc.passed + inc.failed) + '회 · 16필터 기준') : '측정 데이터 없음';
            const c1 = '<div class="kpi"><div class="v">' + (inclPct != null ? inclPct + '<small>%</small>' : '—') + '</div>' +
                '<div class="l" title="역사적 당첨번호가 (구)16필터를 통과하는 비율. 참고 지표이며 실제 예측 풀(극단성 풀)과는 별개다.">필터 통과율 <span style="color:var(--muted);font-weight:600;">(참고)</span></div>' +
                '<div class="trk"><i style="width:' + (inclPct || 0) + '%"></i></div>' +
                '<div style="font-size:10px;color:var(--muted);margin-top:6px;">' + inclSub + '</div></div>';

            // 2) 극단성 풀 크기: 815만 중 극단패턴 제거 후 실제 예측에 쓰는 풀
            const pool = m.pool;
            const K = pool ? pool.target_K : null;
            const ratio = pool && pool.pool_ratio != null ? (pool.pool_ratio * 100).toFixed(1) : null;
            const c2 = '<div class="kpi accent"><div class="v">' + fmtK(K) + '</div>' +
                '<div class="l" title="815만 조합 중 역사적 극단 패턴을 제거하고 남긴, 실제 예측에 쓰이는 풀 크기">극단성 풀 크기</div>' +
                '<div class="trk"><i style="width:' + (ratio || 0) + '%"></i></div>' +
                '<div style="font-size:10px;color:var(--muted);margin-top:6px;">전체 8.14M의 ' + (ratio != null ? ratio + '%' : '—') + '</div></div>';

            // 3) 무작위 대비 적합도(lift): 이 풀이 무작위보다 당첨번호를 얼마나 더 담는가
            const lift = pool && pool.lift != null ? pool.lift.toFixed(2) : null;
            const cov = pool && pool.coverage != null ? (pool.coverage * 100).toFixed(1) : null;
            const liftGood = lift != null && parseFloat(lift) >= 1;
            const c3 = '<div class="kpi"><div class="v" style="color:' + (liftGood ? 'var(--good)' : 'var(--text)') + ';">' + (lift != null ? '&times;' + lift : '—') + '</div>' +
                '<div class="l" title="이 풀이 무작위 대비 당첨번호를 얼마나 더 잘 담는가 (1.0=무작위, 1 초과=우수)">무작위 대비 적합도</div>' +
                '<div style="font-size:10px;color:var(--muted);margin-top:9px;">당첨 포함률 ' + (cov != null ? cov + '%' : '—') + (pool && pool.reliable === false ? ' · 참고' : '') + '</div></div>';

            // 4) 이번 회차: 추첨됐으면 평균 일치, 아니면 예측 세트 수
            let c4;
            if (win && preds.length) {
                let tm = 0; preds.forEach(p => { tm += (p.matches || 0); });
                const avg = (tm / preds.length).toFixed(2);
                c4 = '<div class="kpi"><div class="v">' + avg + '</div><div class="l">이번 회차 평균 일치</div>' +
                    '<div class="trk"><i style="width:' + Math.min(100, avg / 2 * 100) + '%"></i></div>' +
                    '<div style="font-size:10px;color:var(--muted);margin-top:6px;">' + preds.length + '세트 기준</div></div>';
            } else {
                c4 = '<div class="kpi"><div class="v">' + (data.total_predictions || preds.length) + '</div><div class="l">이번 회차 예측 세트</div>' +
                    '<div style="font-size:10px;color:var(--muted);margin-top:9px;">추첨 대기</div></div>';
            }
            // 배치: 실제 메커니즘(극단성 풀 + 무작위 대비 적합도)을 상단에, 참고(필터 통과율)·이번 회차를 하단에
            grid.innerHTML = c2 + c3 + c1 + c4;
        }

        // ===== 통계 영역 =====
        async function showStatistics() {
            document.getElementById('statsSection').style.display = 'grid';
            loadOptimizerStatus();
            setState('backtestGrid', 'loading', '백테스트 로딩 중...');

            const [s, b, w, t] = await Promise.all([
                fetchJson('/api/stats'),
                fetchJson('/api/backtest-performance'),
                fetchJson('/api/winning-statistics'),
                fetchJson('/api/performance-trend')
            ]);
            displayBacktestPerformance(b.ok ? b.data : (b.data || {}));
            displayBasicStats(s.ok ? s.data : {});
            displayDistribution(s.ok ? s.data : {}, b.ok ? b.data : null);
            displayTrend(t.ok ? t.data : {});
        }

        // [지속학습 가시화 2026-07-04] 회차별 실측 best-match 추이 패널.
        // weekly_performance 실측 기록(성능 주장 아님) + 무작위 기대(초기하 정확값) 병기.
        function displayTrend(tr) {
            tr = tr || {};
            const wrap = document.getElementById('trendChart');
            const rows = tr.per_round || [];
            if (!tr.rounds_checked || !rows.length) {
                setState('trendChart', 'empty', '대조 완료된 회차가 아직 없습니다. 새 회차 발표 후 자동 누적됩니다.');
                return;
            }
            document.getElementById('trendSub').textContent =
                '최근 ' + tr.rounds_checked + '회 실측 (막대=최고 일치 개수, *=등수 당첨)';
            let bars = '';
            rows.forEach(r => {
                const h = Math.max((r.best_match / 6) * 100, 4);
                const hit = r.best_rank >= 1 && r.best_rank <= 5;
                bars += '<div class="bar-col"><div class="bar ' + (hit ? 'hi' : '') + '" style="height:' + h + '%">' +
                    '<span class="bar-v">' + r.best_match + (hit ? '*' : '') + '</span></div>' +
                    '<span class="bar-l">' + r.round + '</span></div>';
            });
            wrap.innerHTML = '<div class="bar-chart">' + bars + '</div>' +
                '<div style="display:flex; gap:16px; margin-top:8px; font-size:12px; color:var(--text-2); flex-wrap:wrap;">' +
                '<span>등수적중(5등+) <b style="font-family:var(--font-mono);color:var(--good);">' + tr.rank_hit_rounds + '/' + tr.rounds_checked +
                '회 (' + (tr.rank_hit_rate * 100).toFixed(1) + '%)</b></span>' +
                '<span>무작위 기대 <b style="font-family:var(--font-mono);color:var(--text);">' + (tr.random_expect * 100).toFixed(1) + '%</b></span>' +
                '<span>평균 best-match <b style="font-family:var(--font-mono);color:var(--text);">' + tr.avg_best_match.toFixed(2) + '</b></span>' +
                '<span style="color:var(--muted);">실측 기록 (당첨확률 예측 아님)</span></div>';
        }

        function displayBacktestPerformance(bt) {
            const grid = document.getElementById('backtestGrid');
            bt = bt || {};
            const models = Object.values(bt.model_performance || {});
            if (!bt.total_predictions && !models.length) {
                setState('backtestGrid', 'empty', '백테스트 데이터가 없습니다. main.py 실행 후 표시됩니다.');
                return;
            }
            const avgMatches = models.map(m => m.avg_matches || 0);
            const bestAvg = avgMatches.length ? Math.max.apply(null, avgMatches) : (bt.average_matches || 0);
            const totalPred = bt.total_predictions || models.reduce((a, m) => a + (m.total_predictions || 0), 0);
            const acc3 = models.length ? models.reduce((a, m) => a + (m.accuracy_3plus || 0), 0) / models.length : 0;
            const cells = [
                { v: bt.test_period || 'N/A', l: '테스트 기간' },
                { v: (bt.average_matches != null ? bt.average_matches : bestAvg).toFixed(3), l: '평균 일치' },
                { v: totalPred.toLocaleString(), l: '총 예측 수' },
                { v: acc3.toFixed(1) + '%', l: '3+ 정확도' }
            ];
            grid.innerHTML = '<div class="stat-row">' +
                cells.map(c => '<div class="stat-cell"><div class="v">' + c.v + '</div><div class="l">' + c.l + '</div></div>').join('') +
                '</div>';
            // 주의: 과거 여기서 보여주던 "풀 8.14M->304K 감소율(filter_performance)"은
            // 실제 예측에 미사용인 구(舊) 16필터 추정값이라 제거함. 실제 사용 풀(극단성 풀)
            // 지표는 상단 KPI(/api/extremeness-pool)에서 정직하게 표시한다.
        }

        function displayBasicStats(stats) {
            stats = stats || {};
            const grid = document.getElementById('basicStatsGrid');
            const cells = [
                { v: stats.total_predictions || 0, l: '총 예측' },
                { v: stats.total_rounds || 0, l: '분석 회차' },
                { v: stats.avg_predictions_per_round ? stats.avg_predictions_per_round.toFixed(1) : '0', l: '회차당 평균' },
                { v: stats.total_wins || 0, l: '총 당첨' }
            ];
            grid.innerHTML = '<div class="stat-row">' +
                cells.map(c => '<div class="stat-cell"><div class="v">' + c.v + '</div><div class="l">' + c.l + '</div></div>').join('') +
                '</div>';
        }

        // 맞춘 개수 분포 차트 (백테스트 우선, 없으면 stats)
        function displayDistribution(stats, backtest) {
            const wrap = document.getElementById('distChart');
            let dist = {};
            let hasReal = false;
            if (backtest && backtest.model_performance) {
                for (const k in backtest.model_performance) {
                    const md = backtest.model_performance[k].match_distribution;
                    if (md) { hasReal = true; for (let i = 0; i <= 6; i++) dist[i] = (dist[i] || 0) + (md['match_' + i] || 0); }
                }
            }
            if (!hasReal && stats && stats.match_distribution) dist = stats.match_distribution;
            const total = Object.values(dist).reduce((a, b) => a + b, 0);
            if (!total) { setState('distChart', 'empty', '분포 데이터가 아직 없습니다.'); return; }

            const counts = [];
            for (let i = 0; i <= 6; i++) counts.push(dist[i] || 0);
            const maxC = Math.max.apply(null, counts) || 1;
            const avg = (counts.reduce((s, c, i) => s + c * i, 0) / total).toFixed(2);
            const threePlus = counts.slice(3).reduce((a, b) => a + b, 0);

            let bars = '';
            counts.forEach((c, i) => {
                const h = (c / maxC) * 100;
                bars += '<div class="bar-col"><div class="bar ' + (i >= 3 ? 'hi' : '') + '" style="height:' + h + '%">' +
                    '<span class="bar-v">' + c + '</span></div><span class="bar-l">' + i + '개</span></div>';
            });
            wrap.innerHTML = '<div class="bar-chart">' + bars + '</div>' +
                '<div style="display:flex; gap:16px; margin-top:8px; font-size:12px; color:var(--text-2); flex-wrap:wrap;">' +
                '<span>평균 <b style="font-family:var(--font-mono);color:var(--text);">' + avg + '</b></span>' +
                '<span>3개+ <b style="font-family:var(--font-mono);color:var(--good);">' + threePlus + '</b></span>' +
                '<span style="color:var(--muted);">' + (hasReal ? '실측 데이터' : '추정') + '</span></div>';
        }

        // Optuna 최적화 상태/이력
        async function loadOptimizerStatus() {
            const [st, hi] = await Promise.all([
                fetchJson('/api/optimizer-status'),
                fetchJson('/api/optimizer-history')
            ]);
            displayOptimizerStatus(st.ok ? st.data : { running: false });
            displayOptimizerHistory(hi.ok && Array.isArray(hi.data) ? hi.data : []);
        }

        function displayOptimizerStatus(status) {
            status = status || {};
            const grid = document.getElementById('optimizerStatusGrid');
            const running = !!status.running;
            let remain = 'N/A';
            if (status.remaining_minutes > 0) {
                const h = Math.floor(status.remaining_minutes / 60), m = Math.floor(status.remaining_minutes % 60);
                remain = h > 0 ? (h + '시간 ' + m + '분') : (m + '분');
            }
            grid.innerHTML =
                '<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">' +
                '<span class="status-dot" style="background:' + (running ? 'var(--good)' : 'var(--muted)') + '"></span>' +
                '<b style="color:' + (running ? 'var(--good)' : 'var(--muted)') + ';font-size:14px;">' + (running ? '최적화 작동 중' : '대기 중') + '</b></div>' +
                '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">' +
                kpiMini(status.total_trials || 0, '누적 시도(회)') +
                kpiMini(status.total_runs || 0, '완료(회)') +
                kpiMini((status.best_score != null ? status.best_score.toFixed(3) : 'N/A'), '최고 점수(0~1)') +
                kpiMini(remain, '다음 실행까지') +
                '</div>' +
                (status.best_params ? '<div style="margin-top:11px; font-size:12px; color:var(--text-2);">필터 기준값 ' +
                    (status.best_params.threshold != null ? status.best_params.threshold.toFixed(2) + '%' : 'N/A') + ' · ML우회 ' +
                    (status.best_params.ml_bypass || 'N/A') + '개</div>' : '');
        }
        function kpiMini(v, l) {
            return '<div style="background:var(--elev-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:11px;text-align:center;">' +
                '<div style="font:700 18px/1 var(--font-mono);color:var(--text);">' + v + '</div>' +
                '<div style="font-size:10px;color:var(--muted);margin-top:5px;">' + l + '</div></div>';
        }

        function displayOptimizerHistory(history) {
            const t = document.getElementById('optimizerHistoryTable');
            if (!history || !history.length) { t.innerHTML = '<div class="state" style="padding:18px;">최적화 이력이 없습니다.</div>'; return; }
            let rows = '';
            history.forEach(it => {
                rows += '<tr><td>' + escapeHtml(new Date(it.date).toLocaleString('ko-KR')) + '</td>' +
                    '<td style="text-align:center;">' + (it.trials != null ? it.trials : '-') + '</td>' +
                    '<td style="text-align:center;font-family:var(--font-mono);">' + (it.threshold != null ? it.threshold.toFixed(2) : '-') + '</td>' +
                    '<td style="text-align:center;font-family:var(--font-mono);">' + (it.score != null ? it.score.toFixed(3) : '-') + '</td>' +
                    '<td style="text-align:center;font-family:var(--font-mono);">' + (it.avg_matches != null ? it.avg_matches.toFixed(3) : '-') + '</td></tr>';
            });
            t.innerHTML = '<table class="data-table"><thead><tr><th>날짜</th><th style="text-align:center;">시도(회)</th>' +
                '<th style="text-align:center;">필터기준값</th><th style="text-align:center;">점수</th><th style="text-align:center;">평균맞은개수</th>' +
                '</tr></thead><tbody>' + rows + '</tbody></table>';
        }

        // ===== 화면 저장 =====
        async function saveScreenshot() {
            const overlay = document.getElementById('saveOverlay');
            overlay.classList.add('active');
            try {
                const el = document.getElementById('dashboardContainer');
                const bg = getComputedStyle(document.body).backgroundColor;
                const canvas = await html2canvas(el, { scale: 2, logging: false, useCORS: true, backgroundColor: bg,
                    windowWidth: el.scrollWidth, windowHeight: el.scrollHeight });
                canvas.toBlob(async (blob) => {
                    const fd = new FormData();
                    fd.append('screenshot', blob, 'dashboard_screenshot.png');
                    const res = await fetch('/api/save-screenshot', { method: 'POST', body: fd });
                    if (res.ok) { const r = await res.json(); toast('화면을 저장했습니다', r.path || '', 'ok'); }
                    else { toast('저장 실패', '서버 오류가 발생했습니다.', 'err'); }
                    overlay.classList.remove('active');
                }, 'image/png');
            } catch (e) {
                toast('저장 실패', '화면 캡처 중 오류가 발생했습니다.', 'err');
                overlay.classList.remove('active');
            }
        }

        // ===== 새 예측 생성 (AI-네이티브 로딩) =====
        const GEN_STEPS = [
            '전체 조합 8,145,060개 로드',
            '역사적 극단 패턴 제거 중',
            '필터 풀 축소 8.14M → ~304K',
            'ML/몬테카를로 시뮬레이션',
            '최종 5세트 선별 중'
        ];
        function startGenSkeleton() {
            const content = document.getElementById('predictionsContent');
            let cards = '';
            for (let i = 0; i < 5; i++) cards += '<div class="skel"></div>';
            content.innerHTML = '<div class="gen-status" id="genStatus"></div><div class="skel-grid">' + cards + '</div>';
            let idx = 0;
            const el = document.getElementById('genStatus');
            const tick = () => {
                if (!el) return;
                el.innerHTML = '<span class="seq">[' + (idx + 1) + '/' + GEN_STEPS.length + ']</span> ' + GEN_STEPS[idx % GEN_STEPS.length];
                idx++;
            };
            tick();
            genStatusTimer = setInterval(tick, 1400);
        }
        function stopGenSkeleton() { if (genStatusTimer) { clearInterval(genStatusTimer); genStatusTimer = null; } }

        async function generateNewPredictions(btn) {
            btn = btn || document.getElementById('genBtn');
            const original = btn.textContent;
            btn.disabled = true; btn.textContent = '생성 중...';
            setStatus('load', '새 예측 생성 중');
            startGenSkeleton();
            try {
                const res = await fetch('/api/generate-predictions', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }
                });
                let result = null;
                try { result = await res.json(); } catch (e) {}
                if (!res.ok) {
                    let msg = '서버 오류가 발생했습니다.';
                    if (result && result.error) msg = result.error;
                    else if (res.status === 429) msg = '요청 한도 초과. 잠시 후 다시 시도해주세요.';
                    else if (res.status === 500) msg = '서버 내부 오류가 발생했습니다.';
                    stopGenSkeleton();
                    setStatus('error', '생성 실패');
                    setState('predictionsContent', 'error', msg);
                    toast('예측 생성 실패', msg, 'err');
                    return;
                }
                if (result && result.success) {
                    stopGenSkeleton();
                    toast(result.round + '회차 예측 생성 완료', '5세트가 새로 생성되었습니다.', 'ok');
                    await loadRounds();
                    document.getElementById('roundSelect').value = result.round;
                    await loadWeekData();
                    highlightNewPredictions();
                } else {
                    stopGenSkeleton();
                    setStatus('error', '생성 실패');
                    const msg = (result && result.error) || '알 수 없는 오류가 발생했습니다.';
                    setState('predictionsContent', 'error', msg);
                    toast('예측 생성 실패', msg, 'err');
                }
            } catch (e) {
                stopGenSkeleton();
                setStatus('error', '생성 실패');
                setState('predictionsContent', 'error', e.message || '오류가 발생했습니다.');
                toast('오류 발생', e.message || '네트워크 오류', 'err');
            } finally {
                btn.disabled = false; btn.textContent = original;
            }
        }

        function highlightNewPredictions() {
            document.querySelectorAll('.pred-card').forEach((card, idx) => {
                setTimeout(() => {
                    card.style.transition = 'all .5s';
                    card.style.boxShadow = '0 0 0 2px var(--good), var(--shadow-2)';
                    setTimeout(() => { card.style.boxShadow = ''; }, 1800);
                }, idx * 90);
            });
        }
    </script>
</body>
</html>
"""

# Flask 라우트 - 항상 새로운 인스턴스 생성
def get_dashboard():
    """매번 새로운 대시보드 인스턴스 반환"""
    return EnhancedLottoDashboard()

# dashboard = get_dashboard()  # 초기 인스턴스 - 캐싱 방지를 위해 비활성화 (각 API 호출마다 새 인스턴스 생성)

@app.route('/')
def index():
    """메인 페이지"""
    return render_template_string(HTML_TEMPLATE_V2)

@app.route('/api/rounds')
def get_rounds():
    """회차 목록 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    rounds = fresh_dashboard.get_all_rounds()
    return jsonify(rounds)

@app.route('/api/predictions/<int:round_num>')
def get_predictions(round_num):
    """특정 회차 예측 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    data = fresh_dashboard.get_predictions_by_round(round_num)
    return jsonify(data)

@app.route('/api/week-predictions/<int:round_num>')
def get_week_predictions(round_num):
    """특정 회차 전 일주일간 예측 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    data = fresh_dashboard.get_week_predictions(round_num)
    return jsonify(data)

@app.route('/api/stats')
def get_stats():
    """전체 통계 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    stats = fresh_dashboard.get_statistics()
    return jsonify(stats)

@app.route('/api/filter-criteria')
def get_filter_criteria():
    """[dashboard-monitoring-2] 클라이언트 검증 배지용 실제 필터 기준값 (config 단일 소스).

    하드코딩 드리프트 방지: 서버가 로드한 sum_range/consecutive 값을 그대로 내려준다.
    """
    try:
        fresh_dashboard = EnhancedLottoDashboard()
        fc = fresh_dashboard.filter_criteria or {}
        sr = fc.get('sum_range', {}) or {}
        cons = fc.get('consecutive', {}) or {}
        return jsonify({
            'sum_min': sr.get('min_sum', 45),
            'sum_max': sr.get('max_sum', 235),
            'max_consecutive': cons.get('max_consecutive', 5),
        })
    except Exception as e:
        logging.warning(f"[Dashboard] 필터 기준값 조회 실패: {e}")
        return jsonify({'error': True})

@app.route('/api/performance')
def get_performance():
    """최근 성능 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    performance = fresh_dashboard.get_recent_performance()
    return jsonify(performance)

@app.route('/api/performance-trend')
def get_performance_trend():
    """[지속학습 가시화 2026-07-04] 회차별 실측 성적 추이 API.

    weekly_performance의 대조 완료 회차별 best_match/best_rank를 시간순으로 반환해
    '회차가 쌓일수록 좋아지는가'를 사용자가 직접 확인하게 한다(실측 기록, 성능 주장 아님).
    """
    try:
        from src.core.prediction_tracker import PredictionTracker
        trend = PredictionTracker().get_recent_trend(20)
        return jsonify(trend)
    except Exception as e:
        return jsonify({'rounds_checked': 0, 'error': str(e)})

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
    logger.info(f"Flask API - 데이터 로드: {'성공' if not backtest_data.get('error', False) else '실패 - ' + backtest_data.get('error_message', '알 수 없는 에러')}")

    return jsonify(backtest_data)

@app.route('/api/inclusion-rate')
def get_inclusion_rate():
    """필터 Inclusion Rate 데이터 API

    results/inclusion_rate_report.json 파일이 있으면 반환,
    없으면 안내 메시지 반환
    """
    fresh_dashboard = EnhancedLottoDashboard()
    report_path = os.path.join(fresh_dashboard.project_root, 'results', 'inclusion_rate_report.json')

    if os.path.exists(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify({'error': False, 'data': data})
        except Exception as e:
            return jsonify({'error': True, 'message': str(e)})
    else:
        return jsonify({
            'error': True,
            'message': 'Inclusion Rate 데이터 없음. python src/scripts/measure_inclusion_rate.py 실행 필요'
        })

@app.route('/api/extremeness-pool')
def get_extremeness_pool():
    """극단성 풀(실제 최종 예측에 사용되는 풀) 지표 API.

    구(舊) 16필터 추정값이 아니라, 실제 예측 경로(ExtremenessPoolPredictor)가
    사용하는 풀의 크기(target_K)와 walk-forward 검증 적합도(coverage/lift)를
    정책 JSON + curve 파일에서 읽어 반환한다. 파일만 읽으므로 가볍다(풀 재구성 없음).
    데이터가 없으면 가짜값 대신 error=True 반환(데이터 무결성 정책).
    """
    fresh_dashboard = EnhancedLottoDashboard()
    root = fresh_dashboard.project_root
    TOTAL = 8145060  # C(45,6) 전체 조합 수(수학적 상수)
    policy_path = os.path.join(root, 'configs', 'extremeness_pool_policy.json')

    try:
        if not os.path.exists(policy_path):
            return jsonify({'error': True, 'message': '극단성 풀 정책 파일(configs/extremeness_pool_policy.json) 없음'})
        with open(policy_path, 'r', encoding='utf-8') as f:
            policy = json.load(f)

        target_K = int(policy.get('effective_target_K') or policy.get('raw_target_K') or 0)
        if target_K <= 0:
            return jsonify({'error': True, 'message': '극단성 풀 target_K 미설정'})

        resp = {
            'error': False,
            'target_K': target_K,
            'total_combinations': TOTAL,
            'pool_ratio': target_K / TOTAL,
            'round': policy.get('round'),
            'evidence': policy.get('evidence'),
        }

        # 최신 walk-forward curve 파일에서 target_K에 해당하는 적합도(coverage/lift) 보강
        results_dir = os.path.join(root, 'results')
        curve_files = []
        if os.path.isdir(results_dir):
            curve_files = sorted(
                fn for fn in os.listdir(results_dir)
                if fn.startswith('extremeness_threshold_curve_') and fn.endswith('.json')
            )
        if curve_files:
            with open(os.path.join(results_dir, curve_files[-1]), 'r', encoding='utf-8') as f:
                cdata = json.load(f)
            curve = cdata.get('curve', []) if isinstance(cdata, dict) else (cdata if isinstance(cdata, list) else [])
            if curve:
                entry = min(curve, key=lambda e: abs(int(e.get('target_K', 0)) - target_K))
                resp.update({
                    'coverage': entry.get('coverage'),
                    'lift': entry.get('lift'),
                    'coverage_lcb': entry.get('coverage_lcb'),
                    'lift_lcb': entry.get('lift_lcb'),
                    'reliable': entry.get('reliable'),
                    'observed_hits': entry.get('observed_hits'),
                    'expected_random_hits': entry.get('expected_random_hits'),
                    'curve_round': curve_files[-1],
                })
                if entry.get('pool_ratio') is not None:
                    resp['pool_ratio'] = entry.get('pool_ratio')
        return jsonify(resp)
    except Exception as e:
        logging.error(f"[API] 극단성 풀 지표 조회 실패: {e}")
        return jsonify({'error': True, 'message': str(e)})

@app.route('/api/winning-statistics')
@app.route('/api/winning-statistics/<int:round_num>')
def get_winning_statistics(round_num=None):
    """당첨 통계 API (1~5등 당첨자 수, 당첨금액, 확률)"""
    fresh_dashboard = EnhancedLottoDashboard()
    stats = fresh_dashboard.get_winning_statistics(round_num)
    return jsonify(stats)

@app.route('/api/generate-predictions', methods=['POST'])
@csrf.exempt  # API 엔드포인트는 CSRF 검증 제외 (Rate Limiting으로 보호)
@limiter.limit("30 per hour")  # Rate limit: 1시간에 30번
@require_auth  # SEC-002: 외부 접근 시 토큰 인증 필요
def generate_new_predictions():
    """캐시된 모델을 활용한 예측 생성 API

    SECURITY: Rate limited to 30 requests per hour to prevent abuse.
    """
    import sys as _sys

    try:
        # 프로젝트 루트 경로 설정
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _sys.path.insert(0, project_root)

        # [dashboard-monitoring-6] os.chdir는 프로세스 전역 cwd를 바꿔 동시 요청 간 race를 유발한다.
        # 서버 시작(run_enhanced_dashboard_v2)이 이미 cwd를 project_root로 고정하므로, 여기서는
        # 불변식(cwd==project_root)을 멱등적으로 보장만 하고 '원래 cwd로 복원'은 하지 않는다.
        # (잘못된 값으로 복원해 다른 동시 요청의 상대경로를 깨뜨리던 race를 제거.)
        if os.path.abspath(os.getcwd()) != os.path.abspath(project_root):
            os.chdir(project_root)

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

        # 다음 회차 계산
        from datetime import datetime
        latest_round = db_manager.get_last_round()
        next_round = latest_round + 1

        final_predictions = []

        # ============================================================
        # [신 아키텍처 2026-05-31] 0단계: 극단성 풀 + 5장 다양성 경로 (production 1차 경로와 동일)
        # - main.py와 동일하게 ExtremenessPoolPredictor 사용 -> 대시보드/메인 예측 정합 확보
        # - 디스크 캐시(0.2s 재사용)로 웹 버튼 응답 속도 확보. 실패 시 QuickEngine으로 폴백.
        # - 비활성화: 환경변수 LOTTO_USE_EXTREMENESS_POOL=0
        # ============================================================
        if os.environ.get('LOTTO_USE_EXTREMENESS_POOL', '1') != '0':
            try:
                from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
                import random as _random
                # [지속학습 감사 2026-07-04 P2] 정책 json(SSOT) 상속: 과거엔 K를 env/하드코딩
                # 1.5M으로 '명시 전달'해 자동 K 재탐색이 effective_target_K를 바꿔도 대시보드
                # 예측은 옛 K 풀로 만들어지는 잠재 단절이 있었다. env 미지정 시 target_K=None
                # -> predictor가 정책 json -> env -> 기본값 순으로 해석(main.py와 동일 경로).
                _k_env = os.environ.get('LOTTO_TARGET_POOL_K')
                _epp = ExtremenessPoolPredictor(
                    db_manager, target_K=int(_k_env) if _k_env else None)
                _epp.build_pool()  # 학습회차+K+가중치 동일 시 디스크 캐시 재사용
                # [2026-06-05] '새 예측 생성' 버튼을 누를 때마다 다른 5세트가 나오도록 seed 를 매번
                # 무작위로 바꾼다. (기존 seed=42 고정 -> 매번 동일 5세트 -> 누적 불가 문제 해결)
                # 풀은 동일(캐시 재사용)하므로 비용 없이 풀 안에서 다른 다양성 조합을 탐색해 누적된다.
                _seed = _random.randint(1, 2_000_000)
                _epp_preds = _epp.predict(num_sets=5, seed=_seed)
                if _epp_preds:
                    final_predictions.extend(_epp_preds)
                    logging.info(f"[API] 극단성 풀 경로로 {len(final_predictions)}개 예측 생성 (K={_epp.target_K:,})")
            except Exception as e:
                import traceback
                logging.warning(f"[API] 극단성 풀 경로 실패 - QuickEngine으로 폴백: {e}")
                logging.warning(traceback.format_exc())

        # QuickPredictionEngine 우선 사용 (ML 학습은 너무 오래 걸림)
        # NOTE: 극단성 풀 경로가 이미 5세트를 채웠으면 이 블록은 건너뜀(보충 전용).
        logging.info(f"[API] QuickPredictionEngine으로 {next_round}회차 예측 생성 시작...")

        # 1단계: QuickPredictionEngine으로 빠른 예측 생성 (극단성 풀 폴백/보충)
        if len(final_predictions) < 5:
          try:
            from src.core.quick_prediction_engine import QuickPredictionEngine
            quick_engine = QuickPredictionEngine()
            quick_predictions = quick_engine.generate_quick_predictions(
                num_sets=5,
                db_manager=db_manager,
                use_ml_cache=True  # 캐시된 ML 예측 사용
            )

            for pred in quick_predictions:
                pred_numbers = pred.get('numbers', pred) if isinstance(pred, dict) else pred
                if isinstance(pred, dict):
                    final_predictions.append(pred)
                else:
                    final_predictions.append({
                        'numbers': list(pred_numbers),
                        'confidence': 0.7,
                        'source': 'QuickEngine'
                    })

            logging.info(f"[API] QuickPredictionEngine으로 {len(final_predictions)}개 예측 생성 완료")
          except Exception as e:
            import traceback
            logging.warning(f"[API] QuickPredictionEngine 실패: {e}")
            logging.warning(traceback.format_exc())

        # 2단계: 부족한 예측은 필터 풀에서 보충
        if len(final_predictions) < 5:
            try:
                from src.core.quick_prediction_engine import QuickPredictionEngine
                quick_engine = QuickPredictionEngine()
                quick_predictions = quick_engine.generate_quick_predictions(
                    num_sets=5 - len(final_predictions),
                    db_manager=db_manager,
                    use_ml_cache=True  # 캐시된 ML 예측 사용
                )

                existing_numbers = [tuple(p['numbers']) for p in final_predictions]
                for pred in quick_predictions:
                    if len(final_predictions) >= 5:
                        break
                    pred_numbers = pred.get('numbers', pred) if isinstance(pred, dict) else pred
                    if tuple(pred_numbers) not in existing_numbers:
                        if isinstance(pred, dict):
                            final_predictions.append(pred)
                        else:
                            final_predictions.append({'numbers': list(pred_numbers), 'confidence': 0.6, 'source': 'QuickEngine'})
                        existing_numbers.append(tuple(pred_numbers))

                logging.info(f"[API] QuickPredictionEngine으로 {len(quick_predictions)}개 보충")
            except Exception as e:
                logging.warning(f"[API] QuickPredictionEngine 실패: {e}")
                import traceback
                logging.warning(traceback.format_exc())

        # 예측이 여전히 부족하면 다양한 출처로 보충
        if len(final_predictions) < 5:
            sources = ['Statistical', 'Pattern-Based', 'Frequency', 'Random-Pool']
            import random
            for i in range(5 - len(final_predictions)):
                # 필터링된 조합에서 랜덤 선택
                try:
                    filtered_combos = db_manager.combinations_db.get_filtered_combinations(next_round) or []
                    if not filtered_combos:
                        filtered_combos = db_manager.combinations_db.get_filtered_combinations(latest_round) or []
                    if filtered_combos:
                        existing_numbers = [tuple(p['numbers']) for p in final_predictions]
                        for _ in range(100):  # 최대 100번 시도
                            combo_str = random.choice(filtered_combos[:1000])
                            numbers = sorted([int(x) for x in combo_str.split(',')])
                            if tuple(numbers) not in existing_numbers:
                                final_predictions.append({
                                    'numbers': numbers,
                                    # [F1 2026-06-13 NO FAKE DATA] 과거: 0.5+random.uniform(0.1,0.3)로
                                    #  표시용 신뢰도를 무작위 조작(가짜 지표). 이 경로는 극단풀+QuickEngine이
                                    #  모두 5세트 미달일 때만 도달하는 최후 폴백이며, 실제 산출 근거가 없으므로
                                    #  무작위 대신 중립값(0.5) + 폴백 출처 라벨로 정직하게 표시한다.
                                    'confidence': 0.5,
                                    'source': f"{sources[i % len(sources)]} (fallback)"
                                })
                                break
                except Exception as e:
                    logging.warning(f"[API] 보충 예측 생성 실패: {e}")

        logging.info(f"[API] 최종 {len(final_predictions)}개 예측 생성 완료 (회차: {next_round})")

        # 예측이 비어있으면 실패 반환
        if not final_predictions:
            logging.error(f"[API] {next_round}회차 예측 생성 실패: 모든 ML 모델과 백업 방법이 실패했습니다.")
            return jsonify({
                'success': False,
                'error': '예측 생성 실패: ML 모델 및 백업 방법이 모두 실패했습니다. 서버 로그를 확인하세요.',
                'round': int(next_round)
            }), 500

        # 예측 저장
        prediction_tracker = PredictionTracker()

        # 예측 형식 변환 (main.py와 동일) - JSON 직렬화를 위해 numpy 타입을 Python 타입으로 변환
        # [2026-07-02] ExtremenessPoolPredictor.predict()는 characteristics를 반환하지 않아
        # 이 경로로 저장된 세트는 특성이 전부 빈 {}였다. main.py 사이클 저장과 동일하게
        # 저장 직전에 특성을 계산해 채운다.
        try:
            from main import analyze_number_characteristics as _analyze_chars
        except ImportError:
            _analyze_chars = None

        predictions_to_save = []
        for idx, pred in enumerate(final_predictions, 1):
            # 숫자 리스트를 Python int로 변환 (numpy int32 등을 처리)
            numbers = pred['numbers'] if isinstance(pred, dict) else pred
            if hasattr(numbers, 'tolist'):  # numpy array인 경우
                numbers = numbers.tolist()
            elif isinstance(numbers, list):  # 리스트인 경우 각 요소를 int로 변환
                numbers = [int(num) for num in numbers]

            characteristics = pred.get('characteristics', {}) if isinstance(pred, dict) else {}
            if not characteristics and _analyze_chars is not None:
                try:
                    characteristics = _analyze_chars(numbers)
                except Exception:
                    characteristics = {}

            predictions_to_save.append({
                'numbers': numbers,
                'confidence': float(pred.get('confidence', 0.7)) if isinstance(pred, dict) else 0.7,
                'source': pred.get('source', 'Dashboard') if isinstance(pred, dict) else 'Dashboard',
                'characteristics': characteristics
            })

        # 저장 (누적 저장)
        success = prediction_tracker.save_predictions(
            round_num=next_round,
            predictions=predictions_to_save,
            replace=False  # 기존 예측 유지
        )

        if success:
            logging.info(f"[API] {next_round}회차 예측 {len(predictions_to_save)}세트 생성 및 저장 완료")
        else:
            logging.error(f"[API] {next_round}회차 예측 저장 실패")
            return jsonify({
                'success': False,
                'error': '예측 저장 실패: 데이터베이스 오류가 발생했습니다.',
                'round': int(next_round)
            }), 500

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
        import traceback
        logging.error(f"[API] 예측 생성 중 오류: {str(e)}")
        logging.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/quick-prediction-status')
@limiter.limit("300 per hour")  # [2026-06-01] read-only 상태 폴링: 기본 limit(20/h) 초과 방지(로컬 전용)
def get_quick_prediction_status():
    """빠른 예측 시스템 상태 API"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 시스템 상태 파일 확인
        state_file = os.path.join(project_root, "data/system_state.json")
        quick_cache_dir = os.path.join(project_root, "cache")

        status = {
            'quick_prediction_available': True,
            'last_quick_prediction': None,
            'cache_valid': False,
            'ml_cache_valid': False,
            'filter_cache_valid': False,
            'db_round': 0,
            'recommended_action': 'quick_prediction'
        }

        # 시스템 상태 로드
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                status['db_round'] = state.get('last_round', 0)
                status['filter_cache_valid'] = state.get('filter_update_round', 0) >= status['db_round'] - 1

        # ML 캐시 상태 확인
        models_dir = os.path.join(quick_cache_dir, "models")
        if os.path.exists(models_dir):
            pkl_files = [f for f in os.listdir(models_dir) if f.endswith('.pkl')]
            h5_files = [f for f in os.listdir(models_dir) if f.endswith('.h5')]
            status['ml_cache_valid'] = bool(pkl_files or h5_files)

        # 빠른 예측 캐시 확인
        quick_predictions = [f for f in os.listdir(quick_cache_dir) if f.startswith('quick_predictions_')] if os.path.exists(quick_cache_dir) else []
        if quick_predictions:
            latest_cache = max(quick_predictions)
            cache_path = os.path.join(quick_cache_dir, latest_cache)
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                status['last_quick_prediction'] = cache_data.get('timestamp')
                status['cache_valid'] = True

        status['cache_valid'] = status['ml_cache_valid'] or status['filter_cache_valid']

        return jsonify(status)
    except Exception as e:
        logging.error(f"빠른 예측 상태 조회 실패: {e}")
        return jsonify({
            'quick_prediction_available': False,
            'error': str(e)
        }), 500

@app.route('/api/optimizer-status')
@limiter.limit("300 per hour")  # [2026-06-01] read-only 상태 폴링: 기본 limit 초과 방지(로컬 전용)
def get_optimizer_status():
    """백그라운드 최적화 상태 API"""
    try:
        status_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data/optimizer_status.json"
        )

        if os.path.exists(status_file):
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)

            # 다음 실행까지 남은 시간 계산
            if status.get('next_run'):
                from datetime import datetime
                try:
                    next_run = datetime.fromisoformat(status['next_run'])
                    now = datetime.now()
                    remaining_seconds = (next_run - now).total_seconds()
                    status['remaining_seconds'] = max(0, remaining_seconds)
                    status['remaining_minutes'] = max(0, remaining_seconds / 60)
                except Exception as e:
                    logging.debug(f"대시보드 실행 실패 (무시): {e}")
                    status['remaining_seconds'] = 0
                    status['remaining_minutes'] = 0

            return jsonify(status)
        else:
            # [2026-06-05] 상주(--24h) 최적화 스레드가 없을 때도 디스크에 누적된 v6 PoolOptimizer
            # 진행(data/pool_optimization.db)을 읽어 '누적 trials/최적 점수'를 표시한다.
            # (기존엔 무조건 0/N/A -> 사용자가 '왜 값이 없냐' 오해. 실제론 상주모드에서만 trial 증가.)
            _resp = {
                'running': False, 'last_run': None, 'next_run': None,
                'total_runs': 0, 'current_trial': 0, 'total_trials': 0,
                'best_params': None, 'best_score': None,
                'message': '백그라운드 최적화는 상주 모드(--24h)에서 동작합니다.'
            }
            try:
                _pool_db = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    'data/pool_optimization.db')
                if os.path.exists(_pool_db):
                    with sqlite3.connect(_pool_db) as _c:
                        _cur = _c.cursor()
                        _n = _cur.execute('SELECT COUNT(*) FROM trials').fetchone()
                        # [2026-06-06] 완료/진행 trial을 읽어 '실행 횟수'(완료 trial)·running을 진실되게
                        # 채운다. (기존엔 total_runs=0 고정 -> trial이 누적되는데도 '실행 횟수 0' 오표시.)
                        _done = _cur.execute("SELECT COUNT(*) FROM trials WHERE state='COMPLETE'").fetchone()
                        _run = _cur.execute("SELECT COUNT(*) FROM trials WHERE state='RUNNING'").fetchone()
                        # [2026-06-13 stale RUNNING 가드] 강제킬/크래시로 남은 orphan RUNNING이
                        # '최적화 작동 중'으로 거짓 표시되던 문제 수정. 절대시각 비교(타임존 위험)
                        # 대신 같은 DB의 상대시각만 사용: RUNNING의 최신 시작이 COMPLETE의 최신
                        # 완료보다 이후일 때만 '진짜 작동 중'으로 판정(옛 orphan은 이후 COMPLETE가
                        # 더 늦게 찍혀 자동 배제됨).
                        _run_start = _cur.execute("SELECT MAX(datetime_start) FROM trials WHERE state='RUNNING'").fetchone()
                        _done_end = _cur.execute("SELECT MAX(datetime_complete) FROM trials WHERE state='COMPLETE'").fetchone()
                        _b = _cur.execute('SELECT MAX(value) FROM trial_values').fetchone()
                    if _n and _n[0]:
                        _resp['total_trials'] = int(_n[0])
                    if _done and _done[0] is not None:
                        _resp['total_runs'] = int(_done[0])      # 완료된 최적화 trial 수(=실행 횟수)
                    _running_now = False
                    if _run_start and _run_start[0] is not None:
                        _latest_complete = _done_end[0] if (_done_end and _done_end[0] is not None) else None
                        # RUNNING 시작이 마지막 COMPLETE 완료보다 이후 = 현재 진짜 작동 중
                        _running_now = (_latest_complete is None) or (str(_run_start[0]) > str(_latest_complete))
                    if _running_now:
                        _resp['running'] = True
                        _resp['current_trial'] = int(_run[0]) if (_run and _run[0]) else 1
                    if _b and _b[0] is not None:
                        _resp['best_score'] = float(_b[0])
                    _resp['message'] = (
                        '백그라운드 최적화 진행 중 (상주 모드에서 자동 누적).' if _running_now
                        else '백그라운드 최적화 누적 기록 (orphan 제외, 상주 모드 실행 시 계속 증가).')
            except Exception as _oe:
                logging.debug(f"pool_optimization.db 읽기 실패(무시): {_oe}")
            return jsonify(_resp)
    except Exception as e:
        logging.error(f"최적화 상태 조회 실패: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimizer-history')
@limiter.limit("300 per hour")  # [2026-06-01] read-only 히스토리 폴링: 기본 limit 초과 방지(로컬 전용)
def get_optimizer_history():
    """최적화 히스토리 API.

    [2026-06-14 honesty] 과거: 죽은 옛 threshold 옵티마이저 DB(data/threshold_optimization.db,
    optimization_sessions 테이블)를 읽어 stale/빈 데이터를 반환했다. 현재 활성 최적화기는
    PoolOptimizer(Optuna study=pool_optimization_v6 @ data/pool_optimization.db)이므로 그 실제
    trial 누적/점수를 조회하도록 교정한다(최종예측 가중치 최적화의 실제 진행을 표시).
    """
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(root, "data/pool_optimization.db")

        if not os.path.exists(db_path):
            return jsonify([])

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Optuna 표준 스키마: trials(number,state,datetime_complete) + trial_values(value)
            cursor.execute("""
                SELECT t.number, tv.value, t.datetime_complete
                FROM trials t JOIN trial_values tv ON t.trial_id = tv.trial_id
                WHERE t.state = 'COMPLETE'
                ORDER BY t.trial_id DESC
                LIMIT 20
            """)
            history = []
            for number, value, dt in cursor.fetchall():
                history.append({
                    'date': dt,
                    'trials': number,          # Optuna trial 번호(누적)
                    'score': value,            # PoolOptimizer 목적함수 점수(AUC분리+lift)
                    # 아래 필드는 극단성 풀 가중치 최적화에는 해당 없음(옛 threshold 전용) -> null
                    'threshold': None, 'ml_bypass': None, 'ml_weight': None,
                    'avg_matches': None, 'ml_inclusion_rate': None, 'combinations': None,
                })
            return jsonify(history)
    except Exception as e:
        logging.error(f"최적화 히스토리 조회 실패: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-screenshot', methods=['POST'])
@csrf.exempt  # API 엔드포인트는 CSRF 검증 제외 (Rate Limiting으로 보호)
@require_auth  # SEC-002: 외부 접근 시 토큰 인증 필요
def save_screenshot():
    """스크린샷 저장 API

    SEC-004: 파일 업로드 검증
    - 허용 확장자: png, jpg, jpeg
    - 최대 파일 크기: 5MB
    - secure_filename 적용
    """
    try:
        if 'screenshot' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['screenshot']

        # SEC-004: 파일명 검증
        if not file.filename:
            return jsonify({'error': 'Invalid filename'}), 400

        # SEC-004: 확장자 검증 (이미지 파일만 허용)
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
        file_ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if file_ext not in ALLOWED_EXTENSIONS:
            return jsonify({
                'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}',
                'error_code': 'INVALID_FILE_TYPE'
            }), 400

        # SEC-004: 파일 크기 검증 (5MB 제한)
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.tell()
        file.seek(0)  # 파일 시작으로 복귀

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                'error': f'File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB',
                'error_code': 'FILE_TOO_LARGE'
            }), 400

        # SEC-004: 안전한 파일명 사용
        from werkzeug.utils import secure_filename
        safe_filename = secure_filename(file.filename) or 'dashboard_screenshot.png'

        # 고정 파일명으로 저장 (덮어쓰기)
        save_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'dashboard_screenshot.png'
        )
        file.save(save_path)

        logging.info(f"[API] 스크린샷 저장됨: {save_path} ({file_size // 1024}KB)")

        return jsonify({
            'success': True,
            'path': save_path,
            'size': file_size,
            'message': '화면이 성공적으로 저장되었습니다.'
        })

    except Exception as e:
        logging.error(f"[API] 스크린샷 저장 실패: {e}")
        return jsonify({'error': str(e)}), 500

def run_enhanced_dashboard_v2(host='127.0.0.1', port=5001):
    """향상된 대시보드 v2 실행

    SECURITY: debug parameter removed to prevent RCE vulnerability.
    Debug mode enables Werkzeug debugger with arbitrary code execution.
    """
    # [NEW] 중요: 프로젝트 루트로 작업 디렉토리 변경 (DatabaseManager가 상대 경로 사용)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    print(f"[INFO] Working directory: {os.getcwd()}")

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

    # SECURITY: debug=False hardcoded to prevent RCE attacks
    # Flask reloader 비활성화 (재시작 방지)
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    run_enhanced_dashboard_v2(port=5001)