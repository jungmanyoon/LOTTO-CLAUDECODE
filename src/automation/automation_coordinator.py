#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
자동화 시스템 통합 관리자
모든 자동화 컴포넌트를 조율하고 관리
"""

import logging
import threading
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from .config_watcher import ConfigWatcher
from .auto_scheduler import AutoScheduler

class AutomationCoordinator:
    """자동화 시스템 통합 관리자"""
    
    def __init__(self, db_manager=None, filter_manager=None):
        """
        Args:
            db_manager: DatabaseManager 인스턴스
            filter_manager: FilterManager 인스턴스
        """
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        
        # 자동화 컴포넌트들
        self.config_watcher = ConfigWatcher(check_interval=30)
        self.auto_scheduler = AutoScheduler(db_manager)
        
        # 상태 관리
        self.running = False
        self.refiltering = False
        self.last_refilter_time = None
        
        # 통계
        self.stats = {
            'config_changes': 0,
            'refilters_triggered': 0,
            'new_rounds_detected': 0,
            'predictions_generated': 0,
            'errors_recovered': 0
        }
        
        # 콜백 등록
        self._register_callbacks()
        
        logging.info("[AutomationCoordinator] 통합 자동화 시스템 초기화 완료")
    
    def _register_callbacks(self):
        """각 컴포넌트에 콜백 등록"""
        
        # ConfigWatcher 콜백
        self.config_watcher.register_callback(
            'threshold_changed',
            self._handle_threshold_change
        )
        self.config_watcher.register_callback(
            'filter_changed',
            self._handle_filter_change
        )
        self.config_watcher.register_callback(
            'config_changed',
            self._handle_config_change
        )
        
        # AutoScheduler 콜백
        self.auto_scheduler.register_callback(
            'new_round_detected',
            self._handle_new_round
        )
        self.auto_scheduler.register_callback(
            'refilter_required',
            self._trigger_refilter
        )
        self.auto_scheduler.register_callback(
            'optimization_complete',
            self._handle_optimization_complete
        )
        
        logging.info("[AutomationCoordinator] 콜백 등록 완료")
    
    def start(self):
        """자동화 시스템 시작"""
        if not self.running:
            self.running = True
            
            # ConfigWatcher 시작
            self.config_watcher.start()
            logging.info("[AutomationCoordinator] ConfigWatcher 시작")
            
            # AutoScheduler 시작
            self.auto_scheduler.start()
            logging.info("[AutomationCoordinator] AutoScheduler 시작")
            
            # 모니터링 스레드 시작
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True
            )
            self.monitor_thread.start()
            
            logging.info("[AutomationCoordinator] 🚀 24시간 자동화 시스템 가동")
    
    def stop(self):
        """자동화 시스템 중지"""
        if self.running:
            self.running = False
            
            # 컴포넌트 중지
            self.config_watcher.stop()
            self.auto_scheduler.stop()
            
            # 모니터링 스레드 종료 대기
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.join(timeout=5)
            
            logging.info("[AutomationCoordinator] 자동화 시스템 중지")
    
    def _monitor_loop(self):
        """시스템 모니터링 루프"""
        while self.running:
            try:
                # 10분마다 상태 로깅
                time.sleep(600)
                self._log_status()
            except Exception as e:
                logging.error(f"[AutomationCoordinator] 모니터링 오류: {e}")
    
    def _handle_threshold_change(self, change_info: Dict[str, Any]):
        """Threshold 변경 처리"""
        old_value = change_info['old']
        new_value = change_info['new']
        
        logging.warning(f"""
        ╔════════════════════════════════════════╗
        ║  🔴 THRESHOLD 변경 감지                ║
        ║  {old_value} → {new_value}             ║
        ║  전체 재필터링을 시작합니다...         ║
        ╚════════════════════════════════════════╝
        """)
        
        self.stats['config_changes'] += 1
        
        # 재필터링 트리거
        self._trigger_refilter('threshold_change', new_value)
    
    def _handle_filter_change(self, changes: Dict[str, Any]):
        """필터 설정 변경 처리"""
        logging.warning(f"[AutomationCoordinator] 필터 설정 변경: {changes}")
        
        self.stats['config_changes'] += 1
        
        # 필터 변경 시 재필터링
        if 'filters' in changes:
            self._trigger_refilter('filter_config_change', changes)
        
        # 동적 기준 변경 시 필터 업데이트
        if 'dynamic_criteria' in changes:
            self._update_filter_criteria(changes['dynamic_criteria'])
    
    def _handle_config_change(self, config_name: str, changes: Dict[str, Any]):
        """일반 설정 변경 처리"""
        logging.info(f"[AutomationCoordinator] {config_name} 설정 변경")
        self.stats['config_changes'] += 1
    
    def _handle_new_round(self, round_num: int):
        """새 회차 감지 처리"""
        logging.warning(f"""
        ╔════════════════════════════════════════╗
        ║  🆕 새 회차 감지: {round_num}          ║
        ║  데이터 수집 및 재필터링 시작...       ║
        ╚════════════════════════════════════════╝
        """)
        
        self.stats['new_rounds_detected'] += 1
        
        # 재필터링 트리거
        self._trigger_refilter('new_round', round_num)
    
    def _trigger_refilter(self, reason: str, data: Any = None):
        """재필터링 트리거"""
        
        # 이미 재필터링 중이면 스킵
        if self.refiltering:
            logging.warning("[AutomationCoordinator] 이미 재필터링 진행 중...")
            return
        
        # 너무 자주 재필터링 방지 (최소 30분 간격)
        if self.last_refilter_time:
            elapsed = (datetime.now() - self.last_refilter_time).seconds
            if elapsed < 1800:  # 30분
                logging.info(f"[AutomationCoordinator] 재필터링 대기 (남은 시간: {1800-elapsed}초)")
                return
        
        self.refiltering = True
        self.stats['refilters_triggered'] += 1
        
        # 백그라운드 스레드에서 실행
        thread = threading.Thread(
            target=self._run_refilter,
            args=(reason, data),
            daemon=True
        )
        thread.start()
    
    def _run_refilter(self, reason: str, data: Any):
        """재필터링 실행"""
        try:
            logging.info(f"[AutomationCoordinator] 재필터링 시작 (이유: {reason})")
            start_time = time.time()
            
            # main.py 실행 (full-filter 모드)
            result = subprocess.run(
                ['python', 'main.py', '--full-filter', '--skip-fetch'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=3600  # 1시간 타임아웃
            )
            
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                logging.info(f"""
                ╔════════════════════════════════════════╗
                ║  ✅ 재필터링 완료                      ║
                ║  소요 시간: {elapsed/60:.1f}분         ║
                ║  이유: {reason}                        ║
                ╚════════════════════════════════════════╝
                """)
                
                # 예측 생성
                self._generate_predictions()
            else:
                logging.error(f"[AutomationCoordinator] 재필터링 실패: {result.stderr}")
                self._handle_error('refilter_failed', result.stderr)
                
        except Exception as e:
            logging.error(f"[AutomationCoordinator] 재필터링 오류: {e}")
            self._handle_error('refilter_error', str(e))
        finally:
            self.refiltering = False
            self.last_refilter_time = datetime.now()
    
    def _generate_predictions(self):
        """예측 생성"""
        try:
            logging.info("[AutomationCoordinator] 예측 생성 시작...")
            
            result = subprocess.run(
                ['python', 'main.py', '--predict-only'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=600  # 10분 타임아웃
            )
            
            if result.returncode == 0:
                self.stats['predictions_generated'] += 1
                logging.info("[AutomationCoordinator] ✅ 예측 생성 완료")
            else:
                logging.error(f"[AutomationCoordinator] 예측 생성 실패: {result.stderr}")
                
        except Exception as e:
            logging.error(f"[AutomationCoordinator] 예측 생성 오류: {e}")
    
    def _update_filter_criteria(self, new_criteria: Dict[str, Any]):
        """필터 기준 업데이트"""
        if self.filter_manager:
            try:
                # FilterManager의 기준 업데이트
                for filter_name, criteria in new_criteria.items():
                    if hasattr(self.filter_manager, 'update_filter_criteria'):
                        self.filter_manager.update_filter_criteria(filter_name, criteria)
                        
                logging.info("[AutomationCoordinator] 필터 기준 업데이트 완료")
            except Exception as e:
                logging.error(f"[AutomationCoordinator] 필터 기준 업데이트 실패: {e}")
    
    def _handle_optimization_complete(self):
        """최적화 완료 처리"""
        logging.info("[AutomationCoordinator] 주간 최적화 완료")
        
        # 최적화 후 예측 재생성
        self._generate_predictions()
    
    def _handle_error(self, error_type: str, error_msg: str):
        """오류 처리 및 복구"""
        logging.error(f"[AutomationCoordinator] 오류 발생: {error_type}")
        
        # 복구 시도
        if error_type == 'refilter_failed':
            # 캐시 클리어 후 재시도
            self._clear_cache()
            time.sleep(60)
            self._trigger_refilter('error_recovery', error_type)
            self.stats['errors_recovered'] += 1
    
    def _clear_cache(self):
        """캐시 클리어"""
        try:
            import shutil
            cache_dirs = ['cache/models', 'cache/filters']
            for cache_dir in cache_dirs:
                if Path(cache_dir).exists():
                    shutil.rmtree(cache_dir)
                    Path(cache_dir).mkdir(parents=True, exist_ok=True)
            logging.info("[AutomationCoordinator] 캐시 클리어 완료")
        except Exception as e:
            logging.error(f"[AutomationCoordinator] 캐시 클리어 실패: {e}")
    
    def _log_status(self):
        """상태 로깅"""
        status = self.get_status()
        logging.info(f"""
        ╔════════════════════════════════════════╗
        ║  📊 자동화 시스템 상태                 ║
        ╠════════════════════════════════════════╣
        ║  설정 변경: {status['stats']['config_changes']}회
        ║  재필터링: {status['stats']['refilters_triggered']}회
        ║  새 회차: {status['stats']['new_rounds_detected']}회
        ║  예측 생성: {status['stats']['predictions_generated']}회
        ║  오류 복구: {status['stats']['errors_recovered']}회
        ╚════════════════════════════════════════╝
        """)
    
    def get_status(self) -> Dict[str, Any]:
        """시스템 상태 반환"""
        return {
            'running': self.running,
            'refiltering': self.refiltering,
            'last_refilter': self.last_refilter_time.isoformat() if self.last_refilter_time else None,
            'stats': self.stats,
            'config_watcher': {
                'running': self.config_watcher.running,
                'current_threshold': self.config_watcher.get_current_threshold(),
                'change_history': len(self.config_watcher.get_change_history())
            },
            'scheduler': self.auto_scheduler.get_status()
        }
    
    def force_refilter(self):
        """수동 재필터링 트리거"""
        logging.info("[AutomationCoordinator] 수동 재필터링 요청")
        self._trigger_refilter('manual', None)
    
    def check_and_update(self):
        """즉시 확인 및 업데이트"""
        # 설정 변경 확인
        if self.config_watcher.check_immediate():
            logging.info("[AutomationCoordinator] 설정 변경 감지 및 처리")
        
        # 새 회차 확인
        self.auto_scheduler._check_new_round()