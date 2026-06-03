#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
설정 파일 변경 자동 감지 시스템
24시간 자동 실행을 위한 핵심 컴포넌트
"""

import os
import hashlib
import json
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import yaml

class ConfigWatcher:
    """설정 파일 변경 자동 감지 및 처리"""
    
    def __init__(self, check_interval: int = 30):
        """
        Args:
            check_interval: 변경 확인 주기 (초)
        """
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        
        # 감시 대상 파일들
        self.watched_files = {
            'adaptive_config': 'configs/adaptive_filter_config.yaml',
            'main_config': 'config.yaml'
        }
        
        # 파일별 해시 저장
        self.file_hashes = {}
        self.last_values = {}
        
        # 변경 이력
        self.change_history = []
        
        # 콜백 함수들
        self.callbacks = {
            'threshold_changed': [],
            'filter_changed': [],
            'config_changed': []
        }
        
        # 초기 해시 계산
        self._initialize_hashes()
        
        logging.info("[ConfigWatcher] 설정 감시 시스템 초기화 완료")
    
    def _initialize_hashes(self):
        """초기 파일 해시 계산"""
        for name, path in self.watched_files.items():
            if os.path.exists(path):
                self.file_hashes[name] = self._calculate_hash(path)
                self.last_values[name] = self._load_config(path)
                logging.info(f"[ConfigWatcher] {name} 초기 해시: {self.file_hashes[name][:8]}...")
    
    def _calculate_hash(self, filepath: str) -> str:
        """파일 해시 계산"""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logging.error(f"[ConfigWatcher] 해시 계산 실패: {filepath}, {e}")
            return ""
    
    def _load_config(self, filepath: str) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"[ConfigWatcher] 설정 로드 실패: {filepath}, {e}")
            return {}
    
    def register_callback(self, event_type: str, callback: Callable):
        """변경 이벤트 콜백 등록"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            logging.info(f"[ConfigWatcher] {event_type} 콜백 등록")
    
    def start(self):
        """감시 시작"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._watch_loop, daemon=True)
            self.thread.start()
            logging.info(f"[ConfigWatcher] 감시 시작 (주기: {self.check_interval}초)")
    
    def stop(self):
        """감시 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logging.info("[ConfigWatcher] 감시 중지")
    
    def _watch_loop(self):
        """감시 루프"""
        while self.running:
            try:
                self._check_changes()
                time.sleep(self.check_interval)
            except Exception as e:
                logging.error(f"[ConfigWatcher] 감시 중 오류: {e}")
                time.sleep(self.check_interval)
    
    def _check_changes(self):
        """파일 변경 확인"""
        for name, path in self.watched_files.items():
            if not os.path.exists(path):
                continue
            
            current_hash = self._calculate_hash(path)
            
            if current_hash != self.file_hashes.get(name, ""):
                # 변경 감지!
                old_config = self.last_values.get(name, {})
                new_config = self._load_config(path)
                
                logging.info(f"[ConfigWatcher] [WARN] {name} 변경 감지!")

                # 변경 내용 분석
                changes = self._analyze_changes(name, old_config, new_config)

                # 의미 있는 변경이 있을 때만 이력 저장 + 콜백 트리거
                # (주석/공백만 바뀐 해시 변경, 또는 감시하지 않는 키 변경은
                #  빈 changes가 되므로 빈 이력 누적을 막는다.)
                if changes:
                    # 이력 저장
                    self.change_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'file': name,
                        'changes': changes,
                        'old_hash': self.file_hashes.get(name, "")[:8],
                        'new_hash': current_hash[:8]
                    })

                    # 콜백 트리거
                    self._trigger_callbacks(name, changes)

                # 해시 및 값 업데이트 (의미 변경 여부와 무관하게 항상 갱신해
                # 동일 변경을 매 주기 재감지하지 않도록 한다)
                self.file_hashes[name] = current_hash
                self.last_values[name] = new_config
    
    def _analyze_changes(self, config_name: str, old_config: Dict, new_config: Dict) -> Dict[str, Any]:
        """변경 내용 상세 분석"""
        changes = {}
        
        if config_name == 'adaptive_config':
            # global_probability_threshold 확인
            old_threshold = old_config.get('global_probability_threshold')
            new_threshold = new_config.get('global_probability_threshold')
            
            if old_threshold != new_threshold:
                changes['global_probability_threshold'] = {
                    'old': old_threshold,
                    'new': new_threshold,
                    'impact': 'full_refilter_required'
                }
                logging.warning(f"[ConfigWatcher] [RED] Threshold 변경: {old_threshold} -> {new_threshold}")
            
            # 필터 활성화 상태 확인
            old_filters = old_config.get('filters', {})
            new_filters = new_config.get('filters', {})
            
            filter_changes = {}
            for filter_name in new_filters:
                if old_filters.get(filter_name) != new_filters.get(filter_name):
                    filter_changes[filter_name] = {
                        'old': old_filters.get(filter_name),
                        'new': new_filters.get(filter_name)
                    }
            
            if filter_changes:
                changes['filters'] = filter_changes
                logging.warning(f"[ConfigWatcher] [RED] 필터 설정 변경: {list(filter_changes.keys())}")
            
            # dynamic_criteria 확인
            old_criteria = old_config.get('dynamic_criteria', {})
            new_criteria = new_config.get('dynamic_criteria', {})
            
            if old_criteria != new_criteria:
                changes['dynamic_criteria'] = {
                    'old': old_criteria,
                    'new': new_criteria,
                    'impact': 'filter_update_required'
                }
                logging.warning("[ConfigWatcher] [RED] 동적 기준 변경")

        elif config_name == 'main_config':
            # config.yaml(시스템 설정) 변경 분석
            # 워커/배치/최적화/필터매니저 등 시스템 운영 파라미터가 바뀌면
            # 의미 있는 변경으로 기록하고 config_changed 콜백을 발화시킨다.
            # (이전에는 adaptive_config 전용 분석이라 main_config 변경이 빈 changes로
            #  무시되어 빈 이력만 누적되고 콜백도 발화되지 않았다.)
            watched_keys = [
                'max_workers', 'batch_size', 'optimization', 'filter_manager',
                'filtering', 'ml_models', 'ml_prediction', 'backtesting',
                'parallel_processing', 'performance', 'database', 'cache'
            ]
            section_changes = {}
            for key in watched_keys:
                old_val = old_config.get(key)
                new_val = new_config.get(key)
                if old_val != new_val:
                    section_changes[key] = {'old': old_val, 'new': new_val}

            if section_changes:
                changes['main_config_sections'] = section_changes
                changes['impact'] = 'system_settings_reload_recommended'
                logging.warning(
                    f"[ConfigWatcher] [RED] 시스템 설정 변경: {list(section_changes.keys())}"
                )

        return changes
    
    def _trigger_callbacks(self, config_name: str, changes: Dict[str, Any]):
        """변경에 따른 콜백 트리거"""
        if not changes:
            return

        # YAML 변경 감지 즉시 ThresholdManager 런타임 갱신 (N-W17)
        if config_name == 'adaptive_config':
            try:
                from src.core.threshold_manager import ThresholdManager
                ThresholdManager.get_instance().load_from_config()
                logging.info("[ConfigWatcher] ThresholdManager 런타임 갱신 완료")
            except Exception as e:
                logging.error(f"[ConfigWatcher] ThresholdManager 갱신 실패: {e}")

        # threshold 변경
        if 'global_probability_threshold' in changes:
            for callback in self.callbacks['threshold_changed']:
                try:
                    callback(changes['global_probability_threshold'])
                except Exception as e:
                    logging.error(f"[ConfigWatcher] threshold 콜백 오류: {e}")
        
        # 필터 변경
        if 'filters' in changes or 'dynamic_criteria' in changes:
            for callback in self.callbacks['filter_changed']:
                try:
                    callback(changes)
                except Exception as e:
                    logging.error(f"[ConfigWatcher] filter 콜백 오류: {e}")
        
        # 일반 설정 변경
        for callback in self.callbacks['config_changed']:
            try:
                callback(config_name, changes)
            except Exception as e:
                logging.error(f"[ConfigWatcher] config 콜백 오류: {e}")
    
    def get_current_threshold(self) -> float:
        """현재 threshold 값 반환"""
        config = self.last_values.get('adaptive_config', {})
        return config.get('global_probability_threshold', 1.0)
    
    def get_change_history(self) -> list:
        """변경 이력 반환"""
        return self.change_history.copy()
    
    def check_immediate(self) -> bool:
        """즉시 변경 확인"""
        self._check_changes()
        return len(self.change_history) > 0