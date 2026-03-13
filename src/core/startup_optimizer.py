#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스타트업 최적화 관리자 (Startup Optimizer)

프로그램 시작 시 최적의 실행 경로를 결정합니다.
- 최신 번호 확인
- 업데이트 필요 여부 판단
- 빠른 예측 vs 전체 파이프라인 분기
"""

import os
import json
import logging
import threading
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, List
import re

# 로깅 설정
logger = logging.getLogger(__name__)


class StartupOptimizer:
    """
    스타트업 최적화 관리자

    역할:
    1. 동행복권 API로 최신 회차 확인
    2. DB와 비교하여 업데이트 필요 여부 판단
    3. 캐시 상태 확인
    4. 최적 실행 경로 결정
    """

    _instance = None
    _lock = threading.Lock()

    # 동행복권 API URL
    DHLOTTERY_API_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo="

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StartupOptimizer, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_manager=None, base_dir: str = None):
        """
        스타트업 최적화 관리자 초기화

        Args:
            db_manager: DatabaseManager 인스턴스
            base_dir: 기본 디렉토리 경로
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.db_manager = db_manager
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent.parent
        self.cache_dir = self.base_dir / "cache"
        self.data_dir = self.base_dir / "data"

        # 상태 캐시
        self._latest_round_cache = None
        self._cache_time = None
        self._cache_ttl = 300  # 5분 캐시

        self._initialized = True
        logger.info("[StartupOptimizer] 스타트업 최적화 관리자 초기화 완료")

    def analyze_startup_state(self) -> Dict[str, Any]:
        """
        시작 상태 종합 분석

        Returns:
            분석 결과 딕셔너리:
            - needs_update: 업데이트 필요 여부
            - db_round: DB의 최신 회차
            - api_round: API의 최신 회차
            - cache_valid: 캐시 유효 여부
            - recommended_action: 권장 실행 모드
            - estimated_time: 예상 소요 시간
        """
        logger.info("[StartupOptimizer] 시작 상태 분석 중...")

        result = {
            'needs_update': False,
            'db_round': 0,
            'api_round': 0,
            'api_numbers': None,
            'api_bonus': None,
            'cache_valid': False,
            'ml_cache_valid': False,
            'filter_cache_valid': False,
            'recommended_action': 'quick_prediction',
            'estimated_time': '5-10초',
            'analysis_time': datetime.now().isoformat()
        }

        try:
            # 1. DB 최신 회차 확인
            result['db_round'] = self._get_db_latest_round()
            logger.info(f"[StartupOptimizer] DB 최신 회차: {result['db_round']}")

            # 2. 동행복권 API 최신 회차 확인
            api_result = self._check_latest_round_from_api()
            if api_result:
                result['api_round'] = api_result.get('round', 0)
                result['api_numbers'] = api_result.get('numbers')
                result['api_bonus'] = api_result.get('bonus')
                logger.info(f"[StartupOptimizer] API 최신 회차: {result['api_round']}")

            # 3. 업데이트 필요 여부 판단
            if result['api_round'] > result['db_round']:
                result['needs_update'] = True
                logger.info(f"[StartupOptimizer] 새 회차 발견: {result['db_round']} → {result['api_round']}")

            # 4. 캐시 상태 확인
            result['ml_cache_valid'] = self._check_ml_cache_valid(result['db_round'])
            result['filter_cache_valid'] = self._check_filter_cache_valid(result['db_round'])
            result['cache_valid'] = result['ml_cache_valid'] or result['filter_cache_valid']

            # 5. 권장 실행 모드 결정
            result['recommended_action'], result['estimated_time'] = self._determine_action(result)

            logger.info(f"[StartupOptimizer] 권장 모드: {result['recommended_action']} ({result['estimated_time']})")

        except Exception as e:
            logger.error(f"[StartupOptimizer] 상태 분석 실패: {e}")
            result['recommended_action'] = 'quick_prediction'
            result['estimated_time'] = '5-10초'

        return result

    def _get_db_latest_round(self) -> int:
        """DB에서 최신 회차 조회"""
        try:
            if self.db_manager is None:
                from src.core.db_manager import DatabaseManager
                self.db_manager = DatabaseManager()

            return self.db_manager.get_last_round()
        except Exception as e:
            logger.error(f"[StartupOptimizer] DB 조회 실패: {e}")
            return 0

    def _check_latest_round_from_api(self) -> Optional[Dict]:
        """동행복권 API에서 최신 회차 확인"""

        # 캐시 확인
        if self._latest_round_cache and self._cache_time:
            if datetime.now() - self._cache_time < timedelta(seconds=self._cache_ttl):
                return self._latest_round_cache

        try:
            # 예상 최신 회차 계산 (2002년 12월 7일 1회차 시작)
            start_date = datetime(2002, 12, 7)
            weeks_elapsed = (datetime.now() - start_date).days // 7
            estimated_round = weeks_elapsed + 1

            # API 호출 (예상 회차부터 시작)
            for round_num in range(estimated_round + 1, estimated_round - 3, -1):
                try:
                    response = requests.get(
                        f"{self.DHLOTTERY_API_URL}{round_num}",
                        timeout=5
                    )

                    if response.status_code == 200:
                        data = response.json()

                        if data.get('returnValue') == 'success':
                            numbers = [
                                data.get('drwtNo1'),
                                data.get('drwtNo2'),
                                data.get('drwtNo3'),
                                data.get('drwtNo4'),
                                data.get('drwtNo5'),
                                data.get('drwtNo6')
                            ]
                            bonus = data.get('bnusNo')

                            result = {
                                'round': round_num,
                                'numbers': numbers,
                                'bonus': bonus,
                                'draw_date': data.get('drwNoDate')
                            }

                            # 캐시 저장
                            self._latest_round_cache = result
                            self._cache_time = datetime.now()

                            return result

                except requests.RequestException:
                    continue

            logger.warning("[StartupOptimizer] API에서 최신 회차를 찾을 수 없음")
            return None

        except Exception as e:
            logger.error(f"[StartupOptimizer] API 호출 실패: {e}")
            return None

    def _check_ml_cache_valid(self, db_round: int) -> bool:
        """ML 모델 캐시 유효성 확인"""
        try:
            # 주요 캐시 파일 확인
            cache_files = [
                self.cache_dir / "models" / "ensemble_*.pkl",
                self.cache_dir / "models" / "lstm_*.pkl",
                self.cache_dir / "models" / "lstm_lotto_predictor.h5"
            ]

            # 실제 파일 존재 확인
            models_dir = self.cache_dir / "models"
            if models_dir.exists():
                pkl_files = list(models_dir.glob("*.pkl"))
                h5_files = list(models_dir.glob("*.h5"))

                if pkl_files or h5_files:
                    # 가장 최신 파일의 수정 시간 확인
                    all_files = pkl_files + h5_files
                    latest_file = max(all_files, key=lambda x: x.stat().st_mtime)
                    file_age = datetime.now() - datetime.fromtimestamp(latest_file.stat().st_mtime)

                    # 7일 이내면 유효
                    if file_age < timedelta(days=7):
                        logger.info(f"[StartupOptimizer] ML 캐시 유효: {latest_file.name}")
                        return True

            return False

        except Exception as e:
            logger.warning(f"[StartupOptimizer] ML 캐시 확인 실패: {e}")
            return False

    def _check_filter_cache_valid(self, db_round: int) -> bool:
        """필터 캐시 유효성 확인"""
        try:
            # 시스템 상태 파일 확인
            state_file = self.data_dir / "system_state.json"
            if state_file.exists():
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                filter_round = state.get('filter_update_round', 0)

                # 현재 DB 회차와 동일하면 유효
                if filter_round >= db_round - 1:  # 1회차 차이까지 허용
                    logger.info(f"[StartupOptimizer] 필터 캐시 유효: {filter_round}회차")
                    return True

            return False

        except Exception as e:
            logger.warning(f"[StartupOptimizer] 필터 캐시 확인 실패: {e}")
            return False

    def _determine_action(self, state: Dict) -> Tuple[str, str]:
        """최적 실행 모드 결정"""

        # 케이스 1: 업데이트 필요 없고 캐시 유효
        if not state['needs_update'] and state['cache_valid']:
            return 'quick_prediction', '5-10초'

        # 케이스 2: 업데이트 필요하지만 캐시 유효 (백그라운드 업데이트)
        if state['needs_update'] and state['cache_valid']:
            return 'quick_then_update', '10-15초 (예측 즉시, 업데이트 백그라운드)'

        # 케이스 3: 업데이트 필요하고 캐시 무효
        if state['needs_update'] and not state['cache_valid']:
            return 'full_pipeline_with_quick_first', '15-20초 (빠른 예측 먼저)'

        # 케이스 4: 업데이트 불필요하지만 캐시 무효
        if not state['needs_update'] and not state['cache_valid']:
            return 'statistical_prediction', '5-10초'

        return 'quick_prediction', '5-10초'

    def should_skip_full_pipeline(self, state: Dict = None) -> bool:
        """전체 파이프라인 스킵 가능 여부"""
        if state is None:
            state = self.analyze_startup_state()

        # 캐시가 유효하고 업데이트가 필요 없으면 스킵 가능
        return state['cache_valid'] and not state['needs_update']

    def get_quick_start_config(self) -> Dict:
        """빠른 시작을 위한 설정 반환"""
        state = self.analyze_startup_state()

        return {
            'skip_data_fetch': not state['needs_update'],
            'skip_pattern_analysis': state['filter_cache_valid'],
            'skip_filter_regeneration': state['filter_cache_valid'],
            'skip_ml_training': state['ml_cache_valid'],
            'use_cached_predictions': state['cache_valid'],
            'background_update': state['needs_update'] and state['cache_valid'],
            'state': state
        }

    def update_db_with_new_round(self, api_result: Dict) -> bool:
        """새 회차 데이터로 DB 업데이트"""
        try:
            if self.db_manager is None:
                from src.core.db_manager import DatabaseManager
                self.db_manager = DatabaseManager()

            round_num = api_result.get('round')
            numbers = api_result.get('numbers')
            bonus = api_result.get('bonus')
            draw_date = api_result.get('draw_date', datetime.now().strftime('%Y-%m-%d'))

            if round_num and numbers:
                # 보너스 번호 포함 저장
                if bonus:
                    result = self.db_manager.insert_lotto_numbers_with_bonus(
                        round_num, numbers, bonus, draw_date
                    )
                else:
                    result = self.db_manager.insert_lotto_numbers(
                        round_num, numbers, draw_date
                    )

                if result:
                    logger.info(f"[StartupOptimizer] {round_num}회차 데이터 저장 완료")
                    return True

            return False

        except Exception as e:
            logger.error(f"[StartupOptimizer] DB 업데이트 실패: {e}")
            return False


# 글로벌 인스턴스
_startup_optimizer = None


def get_startup_optimizer(db_manager=None) -> StartupOptimizer:
    """StartupOptimizer 싱글톤 인스턴스 반환"""
    global _startup_optimizer
    if _startup_optimizer is None:
        _startup_optimizer = StartupOptimizer(db_manager)
    return _startup_optimizer
