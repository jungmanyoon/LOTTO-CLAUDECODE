#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시스템 상태 추적 및 동기화 관리자
새 로또 번호 발표 시 자동 업데이트 처리
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path


class SystemStateManager:
    """시스템 상태 추적 및 동기화 관리자"""

    STATE_FILE = "data/system_state.json"

    def __init__(self):
        """시스템 상태 관리자 초기화"""
        self.state_file = Path(self.STATE_FILE)
        self.state = self._load_state()

        logging.info("[SystemStateManager] 상태 관리자 초기화 완료")

    def _load_state(self) -> Dict[str, Any]:
        """상태 파일 로드"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                logging.info(f"[SystemState] 상태 파일 로드: 최신 회차 {state.get('last_round', 0)}")
                return state
            else:
                # 초기 상태 생성
                initial_state = {
                    "last_round": 0,
                    "pattern_analysis_round": 0,
                    "filter_update_round": 0,
                    "ml_cache_round": 0,
                    "last_update": datetime.now().isoformat()
                }
                self._save_state(initial_state)
                logging.info("[SystemState] 초기 상태 파일 생성")
                return initial_state
        except Exception as e:
            logging.error(f"[SystemState] 상태 파일 로드 실패: {e}")
            return {
                "last_round": 0,
                "pattern_analysis_round": 0,
                "filter_update_round": 0,
                "ml_cache_round": 0,
                "last_update": datetime.now().isoformat()
            }

    def _save_state(self, state: Dict[str, Any]):
        """상태 파일 저장"""
        try:
            # data 디렉토리 생성
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            logging.debug(f"[SystemState] 상태 파일 저장: 회차 {state.get('last_round', 0)}")
        except Exception as e:
            logging.error(f"[SystemState] 상태 파일 저장 실패: {e}")

    def check_sync_needed(self, db_round: int) -> bool:
        """
        동기화 필요 여부 확인

        Args:
            db_round: 데이터베이스의 최신 회차

        Returns:
            동기화 필요 여부
        """
        try:
            state_round = self.state.get('last_round', 0)
            pattern_round = self.state.get('pattern_analysis_round', 0)
            filter_round = self.state.get('filter_update_round', 0)
            ml_round = self.state.get('ml_cache_round', 0)

            # DB 회차가 상태 파일보다 최신인 경우
            if db_round > state_round:
                logging.warning(f"[SystemState] 🔄 새 회차 감지: {state_round} → {db_round}")
                logging.info(f"[SystemState] 현재 상태:")
                logging.info(f"  - 패턴 분석: {pattern_round}회차")
                logging.info(f"  - 필터 업데이트: {filter_round}회차")
                logging.info(f"  - ML 캐시: {ml_round}회차")
                return True

            # 상태 파일 컴포넌트별 불일치 확인
            if state_round > 0:
                if pattern_round < state_round:
                    logging.warning(f"[SystemState] ⚠️ 패턴 분석 미동기화: {pattern_round} < {state_round}")
                    return True
                if filter_round < state_round:
                    logging.warning(f"[SystemState] ⚠️ 필터 미동기화: {filter_round} < {state_round}")
                    return True
                if ml_round < state_round:
                    logging.warning(f"[SystemState] ⚠️ ML 캐시 미동기화: {ml_round} < {state_round}")
                    return True

            logging.info(f"[SystemState] ✅ 시스템 동기화 상태 양호 (회차: {db_round})")
            return False

        except Exception as e:
            logging.error(f"[SystemState] 동기화 체크 실패: {e}")
            return True  # 오류 시 안전하게 동기화 수행

    def update_state(self, round_num: int, components: Optional[list] = None):
        """
        시스템 상태 업데이트

        Args:
            round_num: 업데이트할 회차 번호
            components: 업데이트할 컴포넌트 목록
                       None이면 전체 업데이트
                       ['pattern', 'filter', 'ml'] 중 선택
        """
        try:
            if components is None:
                # 전체 업데이트
                components = ['all', 'pattern', 'filter', 'ml']

            if 'all' in components or not components:
                self.state['last_round'] = round_num

            if 'pattern' in components or 'all' in components:
                self.state['pattern_analysis_round'] = round_num
                logging.info(f"[SystemState] 패턴 분석 상태 업데이트: {round_num}회차")

            if 'filter' in components or 'all' in components:
                self.state['filter_update_round'] = round_num
                logging.info(f"[SystemState] 필터 상태 업데이트: {round_num}회차")

            if 'ml' in components or 'all' in components:
                self.state['ml_cache_round'] = round_num
                logging.info(f"[SystemState] ML 캐시 상태 업데이트: {round_num}회차")

            self.state['last_update'] = datetime.now().isoformat()

            self._save_state(self.state)

            logging.info(f"[SystemState] ✅ 상태 업데이트 완료: 회차 {round_num}")

        except Exception as e:
            logging.error(f"[SystemState] 상태 업데이트 실패: {e}")

    def get_last_round(self) -> int:
        """마지막 회차 번호 반환"""
        return self.state.get('last_round', 0)

    def get_component_round(self, component: str) -> int:
        """
        특정 컴포넌트의 마지막 업데이트 회차 반환

        Args:
            component: 'pattern', 'filter', 'ml' 중 하나

        Returns:
            해당 컴포넌트의 마지막 회차
        """
        key_map = {
            'pattern': 'pattern_analysis_round',
            'filter': 'filter_update_round',
            'ml': 'ml_cache_round'
        }

        key = key_map.get(component, f'{component}_round')
        return self.state.get(key, 0)

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            'last_round': self.state.get('last_round', 0),
            'pattern_round': self.state.get('pattern_analysis_round', 0),
            'filter_round': self.state.get('filter_update_round', 0),
            'ml_round': self.state.get('ml_cache_round', 0),
            'last_update': self.state.get('last_update', 'N/A'),
            'sync_status': 'OK' if self._is_synced() else 'OUT_OF_SYNC'
        }

    def _is_synced(self) -> bool:
        """모든 컴포넌트가 동기화되어 있는지 확인"""
        last_round = self.state.get('last_round', 0)
        pattern_round = self.state.get('pattern_analysis_round', 0)
        filter_round = self.state.get('filter_update_round', 0)
        ml_round = self.state.get('ml_cache_round', 0)

        return (
            last_round == pattern_round and
            last_round == filter_round and
            last_round == ml_round
        )

    def reset_component(self, component: str):
        """
        특정 컴포넌트 상태 리셋

        Args:
            component: 리셋할 컴포넌트 ('pattern', 'filter', 'ml')
        """
        key_map = {
            'pattern': 'pattern_analysis_round',
            'filter': 'filter_update_round',
            'ml': 'ml_cache_round'
        }

        key = key_map.get(component)
        if key:
            self.state[key] = 0
            self._save_state(self.state)
            logging.info(f"[SystemState] {component} 컴포넌트 리셋 완료")

    def force_sync(self, round_num: int):
        """
        강제 동기화 (모든 컴포넌트를 지정 회차로 업데이트)

        Args:
            round_num: 동기화할 회차
        """
        self.update_state(round_num, components=['all', 'pattern', 'filter', 'ml'])
        logging.info(f"[SystemState] 강제 동기화 완료: {round_num}회차")
