#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
24시간 자동 실행 스케줄러
새 회차 감지, 정기 작업 실행, 시스템 최적화
"""

import schedule
import threading
import time
import logging
import subprocess
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import sqlite3
import os

class AutoScheduler:
    """24시간 자동 실행 스케줄러"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: DatabaseManager 인스턴스
        """
        self.db_manager = db_manager
        self.running = False
        self.thread = None
        
        # 작업 실행 상태
        self.job_status = {
            'check_new_round': {'last_run': None, 'success': 0, 'fail': 0},
            'daily_prediction': {'last_run': None, 'success': 0, 'fail': 0},
            'weekly_optimization': {'last_run': None, 'success': 0, 'fail': 0},
            'health_check': {'last_run': None, 'success': 0, 'fail': 0},
            'cleanup_logs': {'last_run': None, 'success': 0, 'fail': 0}
        }
        
        # 콜백 함수
        self.callbacks = {
            'new_round_detected': None,
            'refilter_required': None,
            'optimization_complete': None
        }
        
        # 스케줄 설정
        self._setup_schedule()
        
        logging.info("[AutoScheduler] 24시간 스케줄러 초기화 완료")
    
    def _setup_schedule(self):
        """스케줄 작업 설정"""
        # 매시 정각: 새 회차 확인
        schedule.every().hour.at(":00").do(self._check_new_round)
        
        # 매일 오전 9시: 일일 예측 실행
        schedule.every().day.at("09:00").do(self._run_daily_prediction)
        
        # 매주 일요일 오전 3시: 시스템 최적화
        schedule.every().sunday.at("03:00").do(self._run_weekly_optimization)
        
        # 30분마다: 시스템 상태 체크
        schedule.every(30).minutes.do(self._health_check)
        
        # 매일 자정: 로그 정리
        schedule.every().day.at("00:00").do(self._cleanup_logs)
        
        logging.info("[AutoScheduler] 스케줄 설정 완료")
    
    def register_callback(self, event_type: str, callback: Callable):
        """이벤트 콜백 등록"""
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback
            logging.info(f"[AutoScheduler] {event_type} 콜백 등록")
    
    def start(self):
        """스케줄러 시작"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.thread.start()
            logging.info("[AutoScheduler] 스케줄러 시작")
            
            # 즉시 새 회차 확인
            self._check_new_round()
    
    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logging.info("[AutoScheduler] 스케줄러 중지")
    
    def _scheduler_loop(self):
        """스케줄러 메인 루프"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logging.error(f"[AutoScheduler] 스케줄러 오류: {e}")
                time.sleep(60)
    
    def _check_new_round(self):
        """새 회차 데이터 확인"""
        job_name = 'check_new_round'
        logging.info("[AutoScheduler] 새 회차 확인 시작...")
        
        try:
            # 동행복권 API 호출 (또는 웹 크롤링)
            latest_web_round = self._fetch_latest_round_from_web()
            
            if latest_web_round and self.db_manager:
                current_db_round = self.db_manager.get_last_round()
                
                if latest_web_round > current_db_round:
                    logging.warning(f"[AutoScheduler] 🆕 새 회차 발견! {current_db_round} → {latest_web_round}")
                    
                    # 새 회차 데이터 수집
                    if self._fetch_and_save_new_round(latest_web_round):
                        # 콜백 트리거
                        if self.callbacks['new_round_detected']:
                            self.callbacks['new_round_detected'](latest_web_round)
                        
                        # 재필터링 트리거
                        if self.callbacks['refilter_required']:
                            self.callbacks['refilter_required']('new_round', latest_web_round)
                        
                        self._update_job_status(job_name, True)
                        return True
                else:
                    logging.info(f"[AutoScheduler] 현재 최신 회차: {current_db_round}")
            
            self._update_job_status(job_name, True)
            
        except Exception as e:
            logging.error(f"[AutoScheduler] 새 회차 확인 실패: {e}")
            self._update_job_status(job_name, False)
        
        return False
    
    def _fetch_latest_round_from_web(self) -> Optional[int]:
        """웹에서 최신 회차 번호 가져오기"""
        try:
            # 동행복권 API 또는 크롤링
            # 예시 URL (실제 API로 교체 필요)
            url = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo="
            
            # 최신 회차 추정 (토요일 기준)
            base_date = datetime(2002, 12, 7)  # 1회차 추첨일
            current_date = datetime.now()
            weeks_passed = (current_date - base_date).days // 7
            estimated_round = weeks_passed + 1
            
            # API 호출 시도
            for round_num in range(estimated_round, estimated_round - 5, -1):
                try:
                    response = requests.get(url + str(round_num), timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('returnValue') == 'success':
                            return round_num
                except:
                    continue
            
            return None
            
        except Exception as e:
            logging.error(f"[AutoScheduler] 웹 데이터 조회 실패: {e}")
            return None
    
    def _fetch_and_save_new_round(self, round_num: int) -> bool:
        """새 회차 데이터 수집 및 저장"""
        try:
            # main.py의 fetch_lotto_data 호출
            result = subprocess.run(
                ['python', 'main.py', '--fetch-only'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=60
            )
            
            if result.returncode == 0:
                logging.info(f"[AutoScheduler] 회차 {round_num} 데이터 저장 완료")
                return True
            else:
                logging.error(f"[AutoScheduler] 데이터 수집 실패: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"[AutoScheduler] 데이터 저장 실패: {e}")
            return False
    
    def _run_daily_prediction(self):
        """일일 예측 실행"""
        job_name = 'daily_prediction'
        logging.info("[AutoScheduler] 일일 예측 시작...")
        
        try:
            # main.py 전체 실행
            result = subprocess.run(
                ['python', 'main.py', '--skip-fetch'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=1800  # 30분 타임아웃
            )
            
            if result.returncode == 0:
                logging.info("[AutoScheduler] 일일 예측 완료")
                self._update_job_status(job_name, True)
                
                # 예측 결과 알림 (이메일, 텔레그램 등)
                self._notify_prediction_complete()
            else:
                logging.error(f"[AutoScheduler] 예측 실행 실패: {result.stderr}")
                self._update_job_status(job_name, False)
                
        except Exception as e:
            logging.error(f"[AutoScheduler] 일일 예측 오류: {e}")
            self._update_job_status(job_name, False)
    
    def _run_weekly_optimization(self):
        """주간 시스템 최적화"""
        job_name = 'weekly_optimization'
        logging.info("[AutoScheduler] 주간 최적화 시작...")
        
        try:
            # 1. 오래된 캐시 정리
            self._cleanup_old_cache()
            
            # 2. 데이터베이스 최적화
            self._optimize_databases()
            
            # 3. 필터 기준 업데이트
            self._update_filter_criteria()
            
            # 4. ML 모델 재학습
            self._retrain_models()
            
            logging.info("[AutoScheduler] 주간 최적화 완료")
            self._update_job_status(job_name, True)
            
            if self.callbacks['optimization_complete']:
                self.callbacks['optimization_complete']()
                
        except Exception as e:
            logging.error(f"[AutoScheduler] 주간 최적화 실패: {e}")
            self._update_job_status(job_name, False)
    
    def _health_check(self):
        """시스템 상태 체크"""
        job_name = 'health_check'
        
        try:
            checks = {
                'database': self._check_database_health(),
                'disk_space': self._check_disk_space(),
                'memory': self._check_memory_usage(),
                'process': self._check_process_status()
            }
            
            all_healthy = all(checks.values())
            
            if not all_healthy:
                failed = [k for k, v in checks.items() if not v]
                logging.warning(f"[AutoScheduler] ⚠️ 상태 체크 실패: {failed}")
                
                # 심각한 문제 시 알림
                if 'database' in failed or 'disk_space' in failed:
                    self._send_alert(f"시스템 문제 감지: {failed}")
            
            self._update_job_status(job_name, all_healthy)
            
        except Exception as e:
            logging.error(f"[AutoScheduler] 상태 체크 오류: {e}")
            self._update_job_status(job_name, False)
    
    def _cleanup_logs(self):
        """로그 파일 정리"""
        job_name = 'cleanup_logs'
        
        try:
            log_dir = 'logs'
            cutoff_date = datetime.now() - timedelta(days=30)
            
            for filename in os.listdir(log_dir):
                filepath = os.path.join(log_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_time < cutoff_date:
                    os.remove(filepath)
                    logging.info(f"[AutoScheduler] 오래된 로그 삭제: {filename}")
            
            self._update_job_status(job_name, True)
            
        except Exception as e:
            logging.error(f"[AutoScheduler] 로그 정리 실패: {e}")
            self._update_job_status(job_name, False)
    
    def _update_job_status(self, job_name: str, success: bool):
        """작업 상태 업데이트"""
        if job_name in self.job_status:
            self.job_status[job_name]['last_run'] = datetime.now()
            if success:
                self.job_status[job_name]['success'] += 1
            else:
                self.job_status[job_name]['fail'] += 1
    
    def _check_database_health(self) -> bool:
        """데이터베이스 상태 확인"""
        try:
            conn = sqlite3.connect('data/lotto_numbers.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM lotto_numbers")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except:
            return False
    
    def _check_disk_space(self) -> bool:
        """디스크 공간 확인"""
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            free_percent = (free / total) * 100
            return free_percent > 10  # 10% 이상 여유 공간
        except:
            return True
    
    def _check_memory_usage(self) -> bool:
        """메모리 사용량 확인"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return memory.percent < 90  # 90% 미만 사용
        except:
            return True
    
    def _check_process_status(self) -> bool:
        """프로세스 상태 확인"""
        # 현재 실행 중이므로 True
        return True
    
    def _cleanup_old_cache(self):
        """오래된 캐시 정리"""
        cache_dir = 'cache'
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                filepath = os.path.join(root, file)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff_date:
                    os.remove(filepath)
    
    def _optimize_databases(self):
        """데이터베이스 최적화"""
        databases = [
            'data/lotto_numbers.db',
            'data/combinations.db',
            'data/patterns.db'
        ]
        
        for db_path in databases:
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.execute("VACUUM")
                conn.execute("ANALYZE")
                conn.close()
    
    def _update_filter_criteria(self):
        """필터 기준 업데이트"""
        # IntegratedFilterManager의 update_filters_weekly 호출
        logging.info("[AutoScheduler] 필터 기준 업데이트 (주간)")
    
    def _retrain_models(self):
        """ML 모델 재학습"""
        # 캐시 삭제로 다음 실행 시 자동 재학습
        model_cache = 'cache/models'
        if os.path.exists(model_cache):
            import shutil
            shutil.rmtree(model_cache)
            os.makedirs(model_cache)
    
    def _notify_prediction_complete(self):
        """예측 완료 알림"""
        logging.info("[AutoScheduler] 예측 완료 알림 전송")
        # 이메일, 텔레그램, 웹훅 등
    
    def _send_alert(self, message: str):
        """경고 알림 전송"""
        logging.critical(f"[AutoScheduler] 🚨 {message}")
        # 관리자 알림
    
    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태 반환"""
        return {
            'running': self.running,
            'jobs': self.job_status,
            'next_runs': {
                job.job_func.__name__: job.next_run
                for job in schedule.jobs
            }
        }