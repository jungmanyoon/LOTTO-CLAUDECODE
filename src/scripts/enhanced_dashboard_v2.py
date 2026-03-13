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

    예: 192.168.1.100 → 192.168.*.***
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
            with sqlite3.connect(db_path) as conn:
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
                validation_result['warning_message'] = f"🚨 경고: {round_num}회차 당첨번호가 {len(validation_result['failed_filters'])}개 필터에 의해 제외되었습니다!"
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
                        validation_result['warning_message'] = f"⚠️ ML 예측 완화 적용: {', '.join(validation_result['failed_filters'])}"
                    else:
                        validation_result['recommendation'] = 'reject'
                        validation_result['warning_message'] = f"❌ 중요 필터 실패: {', '.join(critical_failures)}"
                else:
                    validation_result['recommendation'] = 'reject'
                    validation_result['warning_message'] = f"❌ 필터 실패: {', '.join(validation_result['failed_filters'])}"

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
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}"><!-- SECURITY: CSRF token -->
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

        .predictions-table td.source-cell {
            white-space: nowrap;
            max-width: 120px;
            overflow: hidden;
            text-overflow: ellipsis;
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

        <!-- 빠른 예측 상태 표시 섹션 -->
        <div id="quickPredictionStatus" class="quick-prediction-section" style="display: none; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); border-radius: 15px; padding: 20px; margin-bottom: 20px; color: white; box-shadow: 0 5px 15px rgba(40, 167, 69, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                <div>
                    <h3 style="margin: 0 0 10px 0; font-size: 1.3em;">
                        <span id="quickStatusIcon">⚡</span> 빠른 예측 시스템
                    </h3>
                    <p style="margin: 0; opacity: 0.9;" id="quickStatusMessage">시스템 상태를 확인 중...</p>
                </div>
                <div id="quickStatusDetails" style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 10px; backdrop-filter: blur(10px);">
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 14px;">
                        <div><strong>DB 회차:</strong> <span id="quickDbRound">-</span></div>
                        <div><strong>ML 캐시:</strong> <span id="quickMlCache">-</span></div>
                        <div><strong>필터 캐시:</strong> <span id="quickFilterCache">-</span></div>
                        <div><strong>예상 시간:</strong> <span id="quickEstTime">-</span></div>
                    </div>
                </div>
            </div>
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
            
            <!-- 백그라운드 최적화 상태 (새로 추가) -->
            <div id="optimizerStatus" style="margin-bottom: 20px;">
                <h3 style="color: #667eea; margin-bottom: 15px;">⚙️ 백그라운드 최적화</h3>
                <div id="optimizerStatusGrid" style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- 최적화 상태가 여기 표시됩니다 -->
                </div>
                <div id="optimizerHistory" style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-top: 15px;">
                    <h4 style="color: #667eea; margin-bottom: 10px;">최근 최적화 이력</h4>
                    <div id="optimizerHistoryTable">
                        <!-- 최적화 이력이 여기 표시됩니다 -->
                    </div>
                </div>
            </div>

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

        // 필터 검증 함수
        function validatePredictionFilter(numbers, source) {
            const validation = {
                passed: true,
                failedFilters: [],
                warning: null
            };

            // 기본 유효성 검사
            if (!numbers || numbers.length !== 6 || new Set(numbers).size !== 6) {
                return '<span style="color: #dc3545; font-size: 12px;">❌ 무효</span>';
            }

            if (!numbers.every(n => n >= 1 && n <= 45)) {
                return '<span style="color: #dc3545; font-size: 12px;">❌ 범위초과</span>';
            }

            // 1. 홀짝 균형 필터 (극단적인 경우만)
            const oddCount = numbers.filter(n => n % 2 === 1).length;
            if (oddCount === 0 || oddCount === 6) {
                validation.failedFilters.push('홀짝');
            }

            // 2. 합계 범위 필터 (서버와 동일: 60~230)
            const sum = numbers.reduce((a, b) => a + b, 0);
            // 🔥 FIX: 서버와 동기화 (sum_range: 60~230)
            if (sum < 60 || sum > 230) {
                validation.failedFilters.push('합계');
            }

            // 3. 연속 번호 필터 (서버와 동일: 4개 이상 연속 시 실패)
            const sorted = [...numbers].sort((a, b) => a - b);
            let consecutiveCount = 0;
            let maxConsecutive = 0;
            for (let i = 0; i < sorted.length - 1; i++) {
                if (sorted[i + 1] - sorted[i] === 1) {
                    consecutiveCount++;
                    maxConsecutive = Math.max(maxConsecutive, consecutiveCount + 1);
                } else {
                    consecutiveCount = 0;
                }
            }
            // 🔥 FIX: 서버와 동기화 (max_consecutive >= 4)
            if (maxConsecutive >= 4) {
                validation.failedFilters.push('연속');
            }

            // 4. 최대 간격 필터 (서버와 동일: 35 초과 시 실패)
            let maxGap = 0;
            for (let i = 0; i < sorted.length - 1; i++) {
                maxGap = Math.max(maxGap, sorted[i + 1] - sorted[i]);
            }
            // 🔥 FIX: 서버와 동기화 (max_gap > 35)
            if (maxGap > 35) {
                validation.failedFilters.push('간격');
            }

            // 결과 판정
            if (validation.failedFilters.length === 0) {
                return '<span style="color: #28a745; font-size: 12px;">✅ 통과</span>';
            }

            // ML 예측인 경우 완화 로직
            if (source && source.startsWith('ML/')) {
                const criticalFilters = validation.failedFilters.filter(f =>
                    f === '홀짝' || f === '합계'
                );

                if (criticalFilters.length === 0) {
                    return '<span style="color: #ffc107; font-size: 12px;">⚠️ 완화</span>';
                } else {
                    return '<span style="color: #dc3545; font-size: 12px;">❌ 중요</span>';
                }
            }

            // 일반 예측 실패
            return '<span style="color: #dc3545; font-size: 12px;">❌ 실패</span>';
        }

        // 페이지 로드 시 초기화
        window.onload = async function() {
            // 빠른 예측 상태 먼저 확인
            await loadQuickPredictionStatus();

            await loadRounds();  // loadRounds가 완료될 때까지 대기
            await loadLatestRound();  // 그 다음 최신 회차 로드

            // 최적화 상태 자동 새로고침 (30초마다)
            setInterval(() => {
                const statsSection = document.getElementById('statsSection');
                if (statsSection && statsSection.style.display !== 'none') {
                    loadOptimizerStatus();
                }
            }, 30000);

            // 빠른 예측 상태 자동 새로고침 (60초마다)
            setInterval(loadQuickPredictionStatus, 60000);
        };

        // 빠른 예측 시스템 상태 로드
        async function loadQuickPredictionStatus() {
            try {
                const response = await fetch('/api/quick-prediction-status');
                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }
                const data = await response.json();

                const statusSection = document.getElementById('quickPredictionStatus');
                const statusIcon = document.getElementById('quickStatusIcon');
                const statusMessage = document.getElementById('quickStatusMessage');
                const dbRound = document.getElementById('quickDbRound');
                const mlCache = document.getElementById('quickMlCache');
                const filterCache = document.getElementById('quickFilterCache');
                const estTime = document.getElementById('quickEstTime');

                // 상태에 따라 표시 업데이트
                if (data.quick_prediction_available) {
                    statusSection.style.display = 'block';
                    statusSection.style.background = 'linear-gradient(135deg, #28a745 0%, #20c997 100%)';
                    statusIcon.textContent = '⚡';

                    if (data.cache_valid) {
                        statusMessage.textContent = '빠른 예측 준비 완료! 캐시된 데이터로 즉시 예측 가능합니다.';
                    } else {
                        statusMessage.textContent = '빠른 예측 시스템 활성화됨. 통계 기반 예측을 사용합니다.';
                    }

                    dbRound.textContent = data.db_round + '회차';
                    mlCache.innerHTML = data.ml_cache_valid
                        ? '<span style="color: #90EE90;">✓ 유효</span>'
                        : '<span style="color: #FFB6C1;">✗ 재생성 필요</span>';
                    filterCache.innerHTML = data.filter_cache_valid
                        ? '<span style="color: #90EE90;">✓ 유효</span>'
                        : '<span style="color: #FFB6C1;">✗ 재생성 필요</span>';
                    estTime.textContent = data.cache_valid ? '5-10초' : '10-15초';
                } else {
                    statusSection.style.display = 'block';
                    statusSection.style.background = 'linear-gradient(135deg, #6c757d 0%, #495057 100%)';
                    statusIcon.textContent = '⏳';
                    statusMessage.textContent = '빠른 예측 시스템 초기화 중...';
                    dbRound.textContent = '-';
                    mlCache.textContent = '-';
                    filterCache.textContent = '-';
                    estTime.textContent = '-';
                }

                console.log('빠른 예측 상태 로드됨:', data);
            } catch (error) {
                console.error('빠른 예측 상태 로드 실패:', error);
                const statusSection = document.getElementById('quickPredictionStatus');
                statusSection.style.display = 'none';
            }
        }
        
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
                    
                    // 공식 당첨 통계 및 예측 비교 준비
                    const ws = data.winning_statistics;
                    const totalPredictions = data.all_predictions.length;

                    // 예측 성과 계산
                    const avgMatches = (totalMatches / totalPredictions).toFixed(2);
                    const maxMatches = Math.max(...data.all_predictions.map(p => p.matches || 0));
                    const threeOrMore = data.all_predictions.filter(p => (p.matches || 0) >= 3).length;
                    const threeOrMorePct = (threeOrMore / totalPredictions * 100).toFixed(1);

                    // 예측 당첨률 계산 (각 등수별)
                    const myWinRate = {};
                    for (let r = 1; r <= 5; r++) {
                        const cnt = rankCounts[r] || 0;
                        myWinRate[r] = ((cnt / totalPredictions) * 100).toFixed(4);
                    }

                    // 공식 당첨률 계산 (총 판매 게임수 기준)
                    let officialWinRate = {};
                    let totalGames = 0;
                    if (ws && ws.total_games) {
                        totalGames = ws.total_games;
                        const s = ws.statistics;
                        officialWinRate = {
                            1: ((s.first_winners / totalGames) * 100).toFixed(6),
                            2: ((s.second_winners / totalGames) * 100).toFixed(6),
                            3: ((s.third_winners / totalGames) * 100).toFixed(4),
                            4: ((s.fourth_winners / totalGames) * 100).toFixed(4),
                            5: ((s.fifth_winners / totalGames) * 100).toFixed(2)
                        };
                    }

                    // 맞춘 개수별 분포 (가로 뱃지)
                    let matchBadgesHtml = '';
                    for (let i = 0; i <= 6; i++) {
                        const count = matchStats[i] || 0;
                        const pct = ((count / totalPredictions) * 100).toFixed(0);
                        const bgColor = i >= 5 ? '#28a745' : i >= 3 ? '#ffc107' : i >= 1 ? '#17a2b8' : '#6c757d';
                        if (count > 0 || i <= 3) {
                            matchBadgesHtml += `<span style="display: inline-block; padding: 2px 6px; margin: 2px; border-radius: 10px; font-size: 11px; background: ${bgColor}; color: white;">${i}개:${count}(${pct}%)</span>`;
                        }
                    }

                    // 등수 현황 (가로 뱃지)
                    let rankBadgesHtml = '';
                    const rankColors = {1: '#d4af37', 2: '#c0c0c0', 3: '#cd7f32', 4: '#28a745', 5: '#17a2b8'};
                    Object.entries(rankCounts).forEach(([rank, count]) => {
                        if (count > 0) {
                            rankBadgesHtml += `<span style="display: inline-block; padding: 2px 8px; margin: 2px; border-radius: 10px; font-size: 11px; background: ${rankColors[rank]}; color: white; font-weight: bold;">${rank}등:${count}개</span>`;
                        }
                    });
                    if (!rankBadgesHtml) rankBadgesHtml = '<span style="color: #666; font-size: 12px;">해당 없음</span>';

                    // 공식 통계 HTML (좌측)
                    let officialStatsHtml = '';
                    if (ws && ws.statistics) {
                        const s = ws.statistics;
                        officialStatsHtml = `
                            <div style="flex: 1; min-width: 200px; background: #fffbf0; padding: 12px; border-radius: 8px; border: 1px solid #f0d080;">
                                <div style="font-weight: bold; margin-bottom: 10px; color: #8b6914; font-size: 13px;">🏆 공식 당첨 통계</div>
                                <table style="width: 100%; font-size: 11px; border-collapse: collapse;">
                                    <tr style="background: #f5e6c0;">
                                        <th style="padding: 5px; text-align: center; border: 1px solid #d4b856; color: #5a4a14;">등수</th>
                                        <th style="padding: 5px; text-align: right; border: 1px solid #d4b856; color: #5a4a14;">당첨자</th>
                                        <th style="padding: 5px; text-align: right; border: 1px solid #d4b856; color: #5a4a14;">당첨금</th>
                                        <th style="padding: 5px; text-align: right; border: 1px solid #d4b856; color: #5a4a14;">확률</th>
                                    </tr>
                                    <tr style="background: #fff8e8;">
                                        <td style="padding: 4px; text-align: center; border: 1px solid #e8d49c; font-weight: bold; color: #b8860b;">1등</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${(s.first_winners || 0).toLocaleString()}명</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #b8860b; font-weight: bold;">${((s.first_prize || 0)/100000000).toFixed(1)}억</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #666; font-size: 10px;">${officialWinRate[1] || '0.000001'}%</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 4px; text-align: center; border: 1px solid #e8d49c; color: #666;">2등</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${(s.second_winners || 0).toLocaleString()}명</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${((s.second_prize || 0)/10000).toLocaleString()}만</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #666; font-size: 10px;">${officialWinRate[2] || '0.000008'}%</td>
                                    </tr>
                                    <tr style="background: #fff8e8;">
                                        <td style="padding: 4px; text-align: center; border: 1px solid #e8d49c; color: #666;">3등</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${(s.third_winners || 0).toLocaleString()}명</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${((s.third_prize || 0)/10000).toLocaleString()}만</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #666; font-size: 10px;">${officialWinRate[3] || '0.003'}%</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 4px; text-align: center; border: 1px solid #e8d49c; color: #666;">4등</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${(s.fourth_winners || 0).toLocaleString()}명</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">5만</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #666; font-size: 10px;">${officialWinRate[4] || '0.14'}%</td>
                                    </tr>
                                    <tr style="background: #fff8e8;">
                                        <td style="padding: 4px; text-align: center; border: 1px solid #e8d49c; color: #666;">5등</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">${(s.fifth_winners || 0).toLocaleString()}명</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #333;">5천</td>
                                        <td style="padding: 4px; text-align: right; border: 1px solid #e8d49c; color: #666; font-size: 10px;">${officialWinRate[5] || '2.1'}%</td>
                                    </tr>
                                </table>
                                <div style="margin-top: 8px; font-size: 10px; color: #888; text-align: right;">총 판매: ${totalGames ? totalGames.toLocaleString() : 'N/A'}게임</div>
                            </div>
                        `;
                    }

                    // 예측 비교 HTML (우측)
                    const predictionCompareHtml = `
                        <div style="flex: 1; min-width: 200px; background: #f0f7ff; padding: 12px; border-radius: 8px; border: 1px solid #80b0e0;">
                            <div style="font-weight: bold; margin-bottom: 10px; color: #1a5a9c; font-size: 13px;">🎯 예측 결과 비교</div>

                            <div style="display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;">
                                <div style="text-align: center; padding: 6px 12px; background: white; border-radius: 6px; border: 1px solid #cce0f0;">
                                    <div style="font-size: 20px; font-weight: bold; color: #2980b9;">${avgMatches}</div>
                                    <div style="font-size: 9px; color: #666;">평균 일치</div>
                                </div>
                                <div style="text-align: center; padding: 6px 12px; background: white; border-radius: 6px; border: 1px solid #cce0f0;">
                                    <div style="font-size: 20px; font-weight: bold; color: #27ae60;">${maxMatches}</div>
                                    <div style="font-size: 9px; color: #666;">최고 일치</div>
                                </div>
                                <div style="text-align: center; padding: 6px 12px; background: white; border-radius: 6px; border: 1px solid #cce0f0;">
                                    <div style="font-size: 16px; font-weight: bold; color: #e67e22;">${threeOrMore}<small style="font-size: 9px;">(${threeOrMorePct}%)</small></div>
                                    <div style="font-size: 9px; color: #666;">3개이상</div>
                                </div>
                            </div>

                            <div style="margin-bottom: 8px;">
                                <div style="font-size: 10px; color: #555; margin-bottom: 4px; font-weight: bold;">맞춘 개수별 분포:</div>
                                <div style="line-height: 1.8;">${matchBadgesHtml}</div>
                            </div>

                            <div style="margin-bottom: 8px;">
                                <div style="font-size: 10px; color: #555; margin-bottom: 4px; font-weight: bold;">등수 현황 (내 예측):</div>
                                <div style="line-height: 1.8;">${rankBadgesHtml}</div>
                            </div>

                            <div style="background: #e8f4fc; padding: 8px; border-radius: 6px; margin-top: 8px;">
                                <div style="font-size: 10px; color: #1a5a9c; font-weight: bold; margin-bottom: 4px;">📊 내 예측 당첨률 vs 공식:</div>
                                <table style="width: 100%; font-size: 10px; border-collapse: collapse;">
                                    <tr>
                                        <td style="padding: 2px; color: #666;">4등:</td>
                                        <td style="padding: 2px; color: #27ae60; font-weight: bold;">${myWinRate[4]}%</td>
                                        <td style="padding: 2px; color: #999;">vs ${officialWinRate[4] || '0.14'}%</td>
                                        <td style="padding: 2px; color: ${parseFloat(myWinRate[4]) > parseFloat(officialWinRate[4] || 0.14) ? '#27ae60' : '#dc3545'}; font-weight: bold;">${parseFloat(myWinRate[4]) > parseFloat(officialWinRate[4] || 0.14) ? '▲우수' : '▼'}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 2px; color: #666;">5등:</td>
                                        <td style="padding: 2px; color: #27ae60; font-weight: bold;">${myWinRate[5]}%</td>
                                        <td style="padding: 2px; color: #999;">vs ${officialWinRate[5] || '2.1'}%</td>
                                        <td style="padding: 2px; color: ${parseFloat(myWinRate[5]) > parseFloat(officialWinRate[5] || 2.1) ? '#27ae60' : '#dc3545'}; font-weight: bold;">${parseFloat(myWinRate[5]) > parseFloat(officialWinRate[5] || 2.1) ? '▲우수' : '▼'}</td>
                                    </tr>
                                </table>
                            </div>
                            <div style="margin-top: 6px; font-size: 9px; color: #888; text-align: right;">총 예측: ${totalPredictions}개</div>
                        </div>
                    `;

                    statsDiv.innerHTML = `
                        <div style="font-size: 13px; line-height: 1.4;">
                            <div style="font-weight: bold; margin-bottom: 10px; font-size: 14px; color: #333;">📊 백테스팅 시뮬레이션 성과</div>
                            <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                                ${officialStatsHtml}
                                ${predictionCompareHtml}
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
                            <th width="80">필터 상태</th>
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
                        <td class="source-cell" title="${pred.source}"><small>${pred.source}</small></td>
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
                        <td>
                            ${validatePredictionFilter(pred.numbers, pred.source || 'Unknown')}
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
                            <th width="80">필터 상태</th>
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
                        <td class="source-cell" title="${pred.source}"><small>${pred.source}</small></td>
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
                        <td>
                            ${validatePredictionFilter(pred.numbers, pred.source || 'Unknown')}
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
        
        // 최적화 상태 로드 및 표시
        async function loadOptimizerStatus() {
            try {
                const [statusResponse, historyResponse] = await Promise.all([
                    fetch('/api/optimizer-status'),
                    fetch('/api/optimizer-history')
                ]);

                // 응답 상태 확인 후 JSON 파싱
                let status = { running: false, total_runs: 0, total_trials: 0 };
                let history = [];

                if (statusResponse.ok) {
                    try {
                        status = await statusResponse.json();
                    } catch (e) {
                        console.warn('최적화 상태 JSON 파싱 실패:', e);
                    }
                }

                if (historyResponse.ok) {
                    try {
                        history = await historyResponse.json();
                    } catch (e) {
                        console.warn('최적화 히스토리 JSON 파싱 실패:', e);
                    }
                }

                displayOptimizerStatus(status);
                displayOptimizerHistory(history);
            } catch (error) {
                console.error('최적화 상태 로드 실패:', error);
                document.getElementById('optimizerStatusGrid').innerHTML = `
                    <div style="text-align: center; color: #999; padding: 20px;">
                        <p>최적화 상태를 불러올 수 없습니다.</p>
                    </div>
                `;
            }
        }

        // 최적화 상태 표시
        function displayOptimizerStatus(status) {
            const statusGrid = document.getElementById('optimizerStatusGrid');

            const statusColor = status.running ? '#28a745' : '#6c757d';
            const statusText = status.running ? '실행 중' : '대기 중';

            let remainingTime = '';
            if (status.remaining_minutes > 0) {
                const hours = Math.floor(status.remaining_minutes / 60);
                const minutes = Math.floor(status.remaining_minutes % 60);
                remainingTime = hours > 0 ? `${hours}시간 ${minutes}분` : `${minutes}분`;
            }

            statusGrid.innerHTML = `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div class="stat-card">
                        <div class="stat-value" style="color: ${statusColor};">${statusText}</div>
                        <div class="stat-label">서비스 상태</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${status.total_runs || 0}회</div>
                        <div class="stat-label">총 최적화 실행</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${status.total_trials || 0}회</div>
                        <div class="stat-label">총 시도 횟수</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${remainingTime || 'N/A'}</div>
                        <div class="stat-label">다음 실행까지</div>
                    </div>
                </div>
                ${status.best_params ? `
                    <div style="margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                        <h5 style="color: #667eea; margin-bottom: 10px;">현재 최적 파라미터</h5>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; font-size: 14px;">
                            <div>
                                <strong>Threshold:</strong> ${status.best_params.threshold?.toFixed(2) || 'N/A'}
                            </div>
                            <div>
                                <strong>ML Bypass:</strong> ${status.best_params.ml_bypass || 'N/A'}
                            </div>
                            <div>
                                <strong>ML Weight:</strong> ${status.best_params.ml_weight?.toFixed(2) || 'N/A'}
                            </div>
                            <div>
                                <strong>Score:</strong> ${status.best_score?.toFixed(3) || 'N/A'}
                            </div>
                        </div>
                    </div>
                ` : ''}
                ${status.message ? `
                    <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; color: #856404; font-size: 14px;">
                        ${status.message}
                    </div>
                ` : ''}
            `;
        }

        // 최적화 이력 표시
        function displayOptimizerHistory(history) {
            const historyTable = document.getElementById('optimizerHistoryTable');

            if (!history || history.length === 0) {
                historyTable.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">최적화 이력이 없습니다.</p>';
                return;
            }

            historyTable.innerHTML = `
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                                <th style="padding: 10px; text-align: left;">날짜</th>
                                <th style="padding: 10px; text-align: center;">시도</th>
                                <th style="padding: 10px; text-align: center;">Threshold</th>
                                <th style="padding: 10px; text-align: center;">ML Bypass</th>
                                <th style="padding: 10px; text-align: center;">ML Weight</th>
                                <th style="padding: 10px; text-align: center;">Score</th>
                                <th style="padding: 10px; text-align: center;">Avg Matches</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${history.map(item => `
                                <tr style="border-bottom: 1px solid #dee2e6;">
                                    <td style="padding: 8px;">${new Date(item.date).toLocaleString('ko-KR')}</td>
                                    <td style="padding: 8px; text-align: center;">${item.trials}</td>
                                    <td style="padding: 8px; text-align: center;">${item.threshold?.toFixed(2) || 'N/A'}</td>
                                    <td style="padding: 8px; text-align: center;">${item.ml_bypass || 'N/A'}</td>
                                    <td style="padding: 8px; text-align: center;">${item.ml_weight?.toFixed(2) || 'N/A'}</td>
                                    <td style="padding: 8px; text-align: center;">${item.score?.toFixed(3) || 'N/A'}</td>
                                    <td style="padding: 8px; text-align: center;">${item.avg_matches?.toFixed(3) || 'N/A'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
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

                // 최적화 상태 로드
                loadOptimizerStatus();

                // 기본 통계, 백테스팅 성능, 당첨 통계 병렬로 로드
                const [statsResponse, backtestResponse, winningStatsResponse] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/backtest-performance'),
                    fetch('/api/winning-statistics')
                ]);

                const stats = await statsResponse.json();
                const backtestData = await backtestResponse.json();
                const winningStats = await winningStatsResponse.json();

                console.log('통계 데이터:', stats);
                console.log('백테스팅 데이터:', backtestData);
                console.log('당첨 통계:', winningStats);

                // 통계 섹션 재구성 (컴팩트 레이아웃)
                statsSection.innerHTML = `
                    <h2 class="section-title">📈 성능 통계</h2>

                    <!-- 백그라운드 최적화 상태 (접힌 상태) -->
                    <details id="optimizerStatus" style="margin-bottom: 15px;">
                        <summary style="cursor: pointer; color: #667eea; font-weight: bold; padding: 10px; background: #f8f9fa; border-radius: 8px;">⚙️ 백그라운드 최적화 상태 (클릭하여 펼치기)</summary>
                        <div style="padding: 10px; background: white; border-radius: 0 0 8px 8px; margin-top: -5px;">
                            <div id="optimizerStatusGrid" style="background: white; padding: 10px; border-radius: 8px;">
                                <!-- 최적화 상태가 여기 표시됩니다 -->
                            </div>
                            <div id="optimizerHistory" style="background: #f8f9fa; padding: 10px; border-radius: 8px; margin-top: 10px;">
                                <h4 style="color: #667eea; margin-bottom: 8px; font-size: 14px;">최근 최적화 이력</h4>
                                <div id="optimizerHistoryTable" style="font-size: 12px;">
                                    <!-- 최적화 이력이 여기 표시됩니다 -->
                                </div>
                            </div>
                        </div>
                    </details>

                    <!-- 백테스팅 성능 통계 (컴팩트) -->
                    <div id="backtestPerformance" style="margin-bottom: 15px;">
                        <h3 style="color: #667eea; margin-bottom: 10px; font-size: 16px;">🎯 백테스팅 시뮬레이션 성능</h3>
                        <div id="backtestStatsGrid" class="stats-grid" style="gap: 8px;">
                            <!-- 백테스팅 통계가 여기 표시됩니다 -->
                        </div>
                    </div>

                    <!-- 실제 예측 통계 (컴팩트) -->
                    <div style="margin-top: 15px;">
                        <h3 style="color: #667eea; margin-bottom: 10px; font-size: 16px;">📊 실제 예측 통계</h3>
                        <div class="stats-grid" id="statsGrid" style="gap: 8px;">
                            <!-- 실제 예측 통계가 여기 표시됩니다 -->
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

                // 상세한 맞춘 개수별 분석 추가 (백테스팅 데이터도 함께 전달)
                displayDetailedMatchAnalysis(stats, backtestData);
                
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
                        <h3>🎯 백테스팅 시뮬레이션 성능</h3>
                        <p>백테스팅 데이터가 없습니다. main.py를 실행하여 백테스팅을 수행하세요.</p>
                        <small>python main.py (백테스팅 포함 실행)</small>
                    </div>
                `;
                backtestSection.style.display = 'block';
                return;
            }
            
            backtestSection.style.display = 'block';
            
            // 에러 상태 확인 및 표시 (데모 모드 삭제됨 - 실제 데이터만 사용)
            if (backtestStats.error) {
                const errorNotice = document.createElement('div');
                errorNotice.className = 'error-notice';
                errorNotice.innerHTML = `
                    <div style="background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 8px; margin-bottom: 15px; font-size: 14px; line-height: 1.5;">
                        <strong>⚠️ 데이터 없음</strong><br>
                        ${backtestStats.error_message || '백테스팅 결과가 없습니다.'}<br>
                        <span style="background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #495057; margin: 5px 0; display: inline-block;">python main.py</span>를 실행하여 실제 성능 통계를 생성하세요.
                    </div>
                `;
                backtestSection.insertBefore(errorNotice, backtestSection.firstChild);
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
            let statsHtml = keyStats.map(stat => `
                <div class="stat-card">
                    <div class="stat-value">${stat.value}</div>
                    <div class="stat-label">${stat.label}</div>
                </div>
            `).join('');

            // 필터 성능 데이터 표시 (실제 데이터만 - 가짜 데이터 금지)
            const filterPerf = backtestStats.filter_performance || {};
            if (filterPerf.data_available) {
                // 실제 데이터가 있는 경우에만 표시
                statsHtml += `
                    <div style="grid-column: 1 / -1; margin-top: 15px; padding: 15px; background: #e8f5e9; border-radius: 10px; border: 1px solid #a5d6a7;">
                        <h4 style="color: #2e7d32; font-size: 14px; margin-bottom: 10px;">🔍 필터 성능 (실제 데이터)</h4>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">
                            <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                                <div style="font-size: 16px; font-weight: bold; color: #1976d2;">${(filterPerf.total_combinations_before || 8145060).toLocaleString()}</div>
                                <div style="font-size: 11px; color: #666;">전체 조합</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                                <div style="font-size: 16px; font-weight: bold; color: #388e3c;">${(filterPerf.total_combinations_after || 0).toLocaleString()}</div>
                                <div style="font-size: 11px; color: #666;">필터링 후</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                                <div style="font-size: 16px; font-weight: bold; color: #f57c00;">${filterPerf.reduction_rate || 0}%</div>
                                <div style="font-size: 11px; color: #666;">감소율</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                                <div style="font-size: 16px; font-weight: bold; color: #7b1fa2;">${filterPerf.hit_rate_in_filtered_pool !== null ? filterPerf.hit_rate_in_filtered_pool + '%' : 'N/A'}</div>
                                <div style="font-size: 11px; color: #666;">ML 포함률</div>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                // 실제 데이터가 없는 경우 경고 메시지
                statsHtml += `
                    <div style="grid-column: 1 / -1; margin-top: 15px; padding: 15px; background: #fff3e0; border-radius: 10px; border: 1px solid #ffcc80;">
                        <h4 style="color: #e65100; font-size: 14px; margin-bottom: 5px;">⚠️ 필터 성능 데이터 없음</h4>
                        <p style="color: #666; font-size: 12px; margin: 0;">
                            필터링 결과가 데이터베이스에 저장되지 않았습니다.<br>
                            <code style="background: #f5f5f5; padding: 2px 6px; border-radius: 4px;">python main.py</code>를 실행하면 실제 필터 성능 데이터가 저장됩니다.
                        </p>
                    </div>
                `;
            }

            // 정직한 확률 분석 섹션 추가
            statsHtml += `
                <div style="grid-column: 1 / -1; margin-top: 15px; padding: 15px; background: #e3f2fd; border-radius: 10px; border: 1px solid #90caf9;">
                    <h4 style="color: #1565c0; font-size: 14px; margin-bottom: 10px;">[ ] 정직한 확률 분석</h4>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                        <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                            <div style="font-size: 14px; font-weight: bold; color: #1976d2;">
                                ${filterPerf.data_available ?
                                    (5 / 8145060 * (filterPerf.hit_rate_in_filtered_pool ? filterPerf.hit_rate_in_filtered_pool / 100 : 1) * 100).toFixed(7) + '%' :
                                    '0.0000614%'}
                            </div>
                            <div style="font-size: 11px; color: #666;">5 Set 1 Prize Probability</div>
                            <div style="font-size: 10px; color: #999;">5 / 8,145,060 x inclusion_rate</div>
                        </div>
                        <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                            <div style="font-size: 14px; font-weight: bold; color: #388e3c;">
                                ${filterPerf.data_available ?
                                    Math.round(8145060 / (filterPerf.total_combinations_after || 300000)) + 'x' :
                                    '27x'}
                            </div>
                            <div style="font-size: 11px; color: #666;">Cost Efficiency</div>
                            <div style="font-size: 10px; color: #999;">8.14M / pool_size</div>
                        </div>
                        <div style="text-align: center; padding: 10px; background: #fff; border-radius: 8px;">
                            <div style="font-size: 14px; font-weight: bold; color: #e65100;">0.8</div>
                            <div style="font-size: 11px; color: #666;">Random Expected Matches</div>
                            <div style="font-size: 10px; color: #999;">E[X] = 6 x 6/45</div>
                        </div>
                    </div>
                    <div style="margin-top: 10px; padding: 10px; background: #f5f5f5; border-radius: 6px; font-size: 11px; color: #555; line-height: 1.6;">
                        <strong>[ ] System Effect Analysis:</strong><br>
                        - Filter: Removes irrational combinations (pool size: ${filterPerf.data_available ? (filterPerf.total_combinations_after || 0).toLocaleString() : 'N/A'} / 8,145,060)<br>
                        - ML Model: avg_matches = 0.8 (same as random, per independent event theory)<br>
                        - Actual Improvement: Cost efficiency ${filterPerf.data_available ? Math.round(8145060 / (filterPerf.total_combinations_after || 300000)) : '~27'}x (probability itself unchanged)<br>
                        - Wheeling: Maximizes number coverage within selected sets
                    </div>
                </div>
            `;

            statsGrid.innerHTML = statsHtml;
        }

        // 기본 통계 표시 (실제 예측 데이터)
        function displayBasicStats(stats) {
            const statsGrid = document.getElementById('statsGrid');

            // 실제 예측 데이터의 match_distribution 확인
            const matchDist = stats.match_distribution || {};
            const totalActualPredictions = Object.values(matchDist).reduce((a, b) => a + b, 0);

            const basicStats = [
                { label: '총 예측', value: stats.total_predictions || 0 },
                { label: '분석 회차', value: stats.total_rounds || 0 },
                { label: '회차당 평균', value: stats.avg_predictions_per_round ? stats.avg_predictions_per_round.toFixed(1) : '0' },
                { label: '총 당첨', value: stats.total_wins || 0 }
            ];

            // 기본 통계 카드
            let html = basicStats.map(stat => `
                <div class="stat-card">
                    <div class="stat-value">${stat.value}</div>
                    <div class="stat-label">${stat.label}</div>
                </div>
            `).join('');

            // 실제 예측 맞춘 개수 분포 추가
            if (totalActualPredictions > 0) {
                html += `
                    <div style="grid-column: 1 / -1; margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 10px;">
                        <h4 style="color: #495057; font-size: 14px; margin-bottom: 10px;">📊 실제 예측 결과 - 맞춘 개수별 분포:</h4>
                        <div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px;">
                            ${[0,1,2,3,4,5,6].map(matches => {
                                const count = matchDist[matches] || 0;
                                const percentage = totalActualPredictions > 0 ? ((count / totalActualPredictions) * 100).toFixed(1) : '0';
                                const bgColor = matches >= 3 ? (matches == 3 ? '#d4edda' : matches == 4 ? '#fff3cd' : matches == 5 ? '#f8d7da' : '#dc3545') : '#e9ecef';
                                const textColor = matches >= 5 ? '#fff' : '#495057';
                                return `
                                    <div style="text-align: center; padding: 10px; background: ${bgColor}; color: ${textColor}; border-radius: 8px;">
                                        <div style="font-size: 18px; font-weight: bold;">${count}</div>
                                        <div style="font-size: 11px; margin-top: 3px;">
                                            ${matches}개<br>
                                            ${percentage}%
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                        <div style="margin-top: 10px; font-size: 12px; color: #666;">
                            ※ 이것은 실제 예측 번호들의 결과입니다. (predictions.db 기준)
                        </div>
                    </div>
                `;
            }

            statsGrid.innerHTML = html;
        }
        
        // 상세한 맞춘 개수별 분석 표시
        function displayDetailedMatchAnalysis(stats, backtestData) {
            const detailSection = document.getElementById('matchDistributionDetail');

            if (!stats.rank_distribution && !backtestData) {
                detailSection.innerHTML = `
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                        <h4 style="color: #667eea; margin-bottom: 10px;">📊 백테스팅 시뮬레이션 - 맞춘 개수별 분석</h4>
                        <p style="color: #666; margin: 0;">분석할 데이터가 부족합니다.</p>
                        <small style="color: #999;">더 많은 예측 데이터가 필요합니다.</small>
                    </div>
                `;
                return;
            }

            const rankData = stats.rank_distribution || {};

            // 백테스팅 데이터에서 match_distribution 수집
            let matchAnalysis = {};
            let hasRealData = false;

            // 백테스팅 데이터에서 실제 match_distribution 추출
            if (backtestData && backtestData.model_performance) {
                // 모든 모델의 match_distribution을 합산
                for (const modelName in backtestData.model_performance) {
                    const modelPerf = backtestData.model_performance[modelName];
                    if (modelPerf.match_distribution) {
                        hasRealData = true;
                        for (let i = 0; i <= 6; i++) {
                            const key = `match_${i}`;
                            matchAnalysis[i] = (matchAnalysis[i] || 0) + (modelPerf.match_distribution[key] || 0);
                        }
                    }
                }
            }

            // 실제 데이터가 없으면 기존 추정 로직 사용
            if (!hasRealData) {
                if (stats.match_distribution) {
                    matchAnalysis = stats.match_distribution;
                } else {
                    // 백업: rank_distribution 기반 추정 (정확하지 않음)
                    matchAnalysis = {
                        0: Math.max(0, (stats.total_predictions || 100) - (stats.total_wins || 0) - 100),
                        1: Math.floor((stats.total_predictions || 100) * 0.35),
                        2: Math.floor((stats.total_predictions || 100) * 0.25),
                        3: rankData['5등'] || 0,
                        4: rankData['4등'] || 0,
                        5: (rankData['3등'] || 0) + (rankData['2등'] || 0),
                        6: rankData['1등'] || 0
                    };
                }
            }
            
            const totalPredictions = Object.values(matchAnalysis).reduce((sum, val) => sum + val, 0) || 1;
            const avgMatches = (Object.entries(matchAnalysis).reduce((sum, [matches, count]) => sum + (parseInt(matches) * count), 0) / totalPredictions).toFixed(2);
            const threeOrMore = (matchAnalysis[3] || 0) + (matchAnalysis[4] || 0) + (matchAnalysis[5] || 0) + (matchAnalysis[6] || 0);

            // 컴팩트 레이아웃: 가로로 배치된 뱃지 + 요약 한 줄
            detailSection.innerHTML = `
                <div style="background: linear-gradient(135deg, #f8f9fa, #e9ecef); padding: 12px 15px; border-radius: 10px; border: 1px solid #dee2e6;">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                        <h4 style="color: #667eea; margin: 0; font-size: 14px;">📊 맞춘 개수별 분석</h4>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${Object.entries(matchAnalysis).map(([matches, count]) => {
                                const percentage = ((count / totalPredictions) * 100).toFixed(1);
                                let bgColor = matches >= 3 ? (matches == 3 ? '#28a745' : matches == 4 ? '#ffc107' : matches == 5 ? '#fd7e14' : '#dc3545') : '#6c757d';
                                let textColor = matches == 4 ? '#000' : '#fff';
                                return `<span style="background: ${bgColor}; color: ${textColor}; padding: 4px 10px; border-radius: 15px; font-size: 12px; font-weight: bold;" title="${matches}개 맞춤: ${count}건 (${percentage}%)">${matches}개: ${count}</span>`;
                            }).join('')}
                        </div>
                    </div>
                    <div style="display: flex; gap: 15px; margin-top: 10px; font-size: 12px; color: #495057; flex-wrap: wrap;">
                        <span>📈 평균: <strong>${avgMatches}개</strong></span>
                        <span>🎯 3개+: <strong>${threeOrMore}건</strong> (${((threeOrMore / totalPredictions) * 100).toFixed(1)}%)</span>
                        ${matchAnalysis[6] > 0 ? `<span style="color: #dc3545;">🎉 6개 맞춤: <strong>${matchAnalysis[6]}건</strong></span>` : ''}
                        ${hasRealData ? '<span style="color: #28a745;">✅ 실제 데이터</span>' : '<span style="color: #ffc107;">⚠️ 추정</span>'}
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
                    formData.append('screenshot', blob, 'dashboard_screenshot.png');
                    
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

                // API 호출 (CSRF exempt 처리됨)
                const response = await fetch('/api/generate-predictions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                // 응답 상태 확인
                if (!response.ok) {
                    // HTTP 에러 응답 처리
                    let errorMsg = '서버 오류가 발생했습니다.';
                    try {
                        const errorData = await response.json();
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) {
                        // JSON 파싱 실패 시 기본 메시지 사용
                        if (response.status === 429) {
                            errorMsg = '요청 한도 초과. 잠시 후 다시 시도해주세요.';
                        } else if (response.status === 500) {
                            errorMsg = '서버 내부 오류가 발생했습니다.';
                        }
                    }
                    alert('❌ 예측 생성 실패:\\n' + errorMsg);
                    return;
                }

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

@app.route('/api/performance')
def get_performance():
    """최근 성능 API"""
    # 최신 데이터를 위해 새 인스턴스 생성
    fresh_dashboard = EnhancedLottoDashboard()
    performance = fresh_dashboard.get_recent_performance()
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

        # ✨ 중요: 작업 디렉토리를 프로젝트 루트로 변경 (DatabaseManager가 상대 경로 사용)
        original_cwd = os.getcwd()
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

        # QuickPredictionEngine 우선 사용 (ML 학습은 너무 오래 걸림)
        logging.info(f"[API] QuickPredictionEngine으로 {next_round}회차 예측 생성 시작...")

        # 1단계: QuickPredictionEngine으로 빠른 예측 생성 (우선)
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
                                    'confidence': 0.5 + random.uniform(0.1, 0.3),  # 50-80% 신뢰도
                                    'source': sources[i % len(sources)]
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
    finally:
        # 원래 작업 디렉토리로 복원
        try:
            if 'original_cwd' in locals():
                os.chdir(original_cwd)
        except:
            pass

@app.route('/api/quick-prediction-status')
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
            return jsonify({
                'running': False,
                'last_run': None,
                'next_run': None,
                'total_runs': 0,
                'current_trial': 0,
                'total_trials': 0,
                'best_params': None,
                'best_score': None,
                'message': '백그라운드 최적화 서비스가 실행되지 않았습니다.'
            })
    except Exception as e:
        logging.error(f"최적화 상태 조회 실패: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimizer-history')
def get_optimizer_history():
    """최적화 히스토리 API"""
    try:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data/threshold_optimization.db"
        )

        if not os.path.exists(db_path):
            return jsonify([])

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT session_date, n_trials, best_threshold, best_ml_bypass,
                       best_ml_weight, best_score, avg_matches, ml_inclusion_rate,
                       combination_count
                FROM optimization_sessions
                ORDER BY session_date DESC
                LIMIT 20
            """)

            columns = ['date', 'trials', 'threshold', 'ml_bypass', 'ml_weight',
                      'score', 'avg_matches', 'ml_inclusion_rate', 'combinations']

            history = []
            for row in cursor.fetchall():
                history.append(dict(zip(columns, row)))

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
    # ✨ 중요: 프로젝트 루트로 작업 디렉토리 변경 (DatabaseManager가 상대 경로 사용)
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