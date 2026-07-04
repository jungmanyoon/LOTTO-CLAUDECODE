#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
24시간 자동 실행 스케줄러
새 회차 감지, 정기 작업 실행, 시스템 최적화
"""

import schedule as schedule_module
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
        
        # 독립 스케줄러 인스턴스 (global schedule 모듈과 충돌 방지)
        self.scheduler = schedule_module.Scheduler()

        # 스케줄 설정
        self._setup_schedule()

        logging.info("[AutoScheduler] 24시간 스케줄러 초기화 완료")
    
    def _setup_schedule(self):
        """스케줄 작업 설정

        [automation-3 - 타임존 가정 명시]
        아래 시각 지정 잡(특정 시:분에 실행)은 모두 "한국 표준시(KST)" 기준 시각이다.
        그러나 schedule 모듈의 .at()는 별도 tz 인자를 주지 않으면 OS 로컬 시간을 사용하므로,
        이 스케줄러는 "운영 호스트의 OS 로컬 타임존이 항상 KST(Asia/Seoul)로 고정되어 있다"는
        전제 하에 동작한다. (로또 추첨/발표가 한국 시간 기준이므로 KST 호스트가 정상 운영 환경)

        - 토요일 20:45 = 로또 추첨 시각(KST)
        - 일일 예측 09:00 / 주간 최적화 일요일 03:00 / 로그 정리 자정 00:00 모두 KST 기준

        주의: 운영 호스트가 KST가 아닌 다른 타임존이라면 위 시각들이 의도와 어긋나 동작한다.
              (schedule 1.1+ 의 .at(time, "Asia/Seoul") tz 인자로 고정 가능하나, 호스트 KST
               전제가 유지되는 한 추가 변경 없이 안전하다.)
        """
        # 토요일 저녁 8시 45분부터 9시 30분까지 1분마다 새 회차 확인 (KST 기준)
        # (로또 추첨 시간: 토요일 저녁 8시 45분 KST)
        for minute in range(45, 60):  # 8시 45분 ~ 8시 59분
            self.scheduler.every().saturday.at(f"20:{minute:02d}").do(self._check_new_round_intensive)
        for minute in range(0, 31):  # 9시 00분 ~ 9시 30분 (여유있게)
            self.scheduler.every().saturday.at(f"21:{minute:02d}").do(self._check_new_round_intensive)

        # 다른 날은 3시간마다 확인 (토요일 제외) - 상대 간격이라 타임존 무관
        self.scheduler.every(3).hours.do(self._check_new_round_if_not_saturday)

        # 매일 오전 9시: 일일 예측 실행 (KST 기준 - 호스트 KST 전제)
        self.scheduler.every().day.at("09:00").do(self._run_daily_prediction)

        # 매주 일요일 오전 3시: 시스템 최적화 (KST 기준 - 호스트 KST 전제)
        self.scheduler.every().sunday.at("03:00").do(self._run_weekly_optimization)

        # 30분마다: 시스템 상태 체크 - 상대 간격이라 타임존 무관
        self.scheduler.every(30).minutes.do(self._health_check)

        # 매일 자정: 로그 정리 (KST 기준 - 호스트 KST 전제)
        self.scheduler.every().day.at("00:00").do(self._cleanup_logs)

        logging.info("[AutoScheduler] 스케줄 설정 완료 (시각 지정 잡은 KST 기준, 호스트 KST 전제)")
        logging.info("[AutoScheduler] 토요일 20:45 ~ 21:30 (KST) 집중 모니터링 활성화")
    
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
                self.scheduler.run_pending()
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

                # None 체크 추가하여 NoneType 비교 오류 방지
                if current_db_round is not None and latest_web_round > current_db_round:
                    logging.warning(f"[AutoScheduler] [NEW] 새 회차 발견! {current_db_round} -> {latest_web_round}")
                    
                    # 새 회차 데이터 수집
                    if self._fetch_and_save_new_round(latest_web_round):
                        # 콜백 트리거
                        if self.callbacks['new_round_detected']:
                            self.callbacks['new_round_detected'](latest_web_round)

                        # [NR-P0-1 FIX] 일반 경로도 토요일 경로(_check_new_round_intensive)와 동일하게
                        # 트리거 체인을 직접 호출. 기존엔 일반 경로가 _trigger_update_chain을 호출하지 않아
                        # system_state(패턴/필터/ML/last_round)가 갱신되지 않고 1216에 멈추는 근본 원인이었음.
                        # subprocess(--fetch-only)로 저장하면 부모의 new_round_added 콜백이 발동 안 하므로
                        # 여기서 명시적으로 체인을 호출해야 상태/패턴/필터가 갱신됨.
                        logging.info("[AutoScheduler] [SYNC] 자동 업데이트 체인 시작(일반 경로)...")
                        self._trigger_update_chain(latest_web_round)

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

    def _check_new_round_intensive(self):
        """토요일 집중 모니터링 - 당첨번호 확인 후 자동 실행"""
        job_name = 'check_new_round_intensive'
        current_time = datetime.now()
        logging.info(f"[AutoScheduler] [TARGET] 토요일 집중 모니터링 시작 ({current_time.strftime('%H:%M:%S')})")

        try:
            # 새 회차 확인
            latest_web_round = self._fetch_latest_round_from_web()

            if latest_web_round and self.db_manager:
                current_db_round = self.db_manager.get_last_round()

                # None 체크 추가하여 NoneType 비교 오류 방지
                if current_db_round is not None and latest_web_round > current_db_round:
                    logging.warning(f"[AutoScheduler] [!] 새 당첨번호 발표! {current_db_round} -> {latest_web_round}")

                    # 새 회차 데이터 수집
                    if self._fetch_and_save_new_round(latest_web_round):
                        logging.info(f"[AutoScheduler] [O] {latest_web_round}회차 당첨번호 저장 완료!")

                        # 콜백 트리거 - 새 회차 감지
                        if self.callbacks['new_round_detected']:
                            self.callbacks['new_round_detected'](latest_web_round)

                        # 자동 업데이트 콜백 체인 실행
                        logging.info("[AutoScheduler] [SYNC] 자동 업데이트 체인 시작...")
                        self._trigger_update_chain(latest_web_round)

                        # 자동 재필터링 실행
                        logging.info("[AutoScheduler] [SYNC] 자동 재필터링 시작...")
                        if self.callbacks['refilter_required']:
                            self.callbacks['refilter_required']('new_round', latest_web_round)

                        # 자동 예측 생성 (토요일 밤에만)
                        if current_time.hour >= 20:  # 저녁 8시 이후
                            logging.info("[AutoScheduler] [RANDOM] 새 회차 예측 생성 시작...")
                            self._run_prediction_for_new_round(latest_web_round + 1)

                        # 최적화 콜백 실행
                        if self.callbacks['optimization_complete']:
                            self.callbacks['optimization_complete']()

                        self._update_job_status(job_name, True)

                        # 성공 시 30분 대기 후 다시 확인 (중복 실행 방지)
                        logging.info("[AutoScheduler] 당첨번호 업데이트 완료. 30분 후 재확인.")
                        return True
                else:
                    logging.info(f"[AutoScheduler] 아직 {latest_web_round}회차 당첨번호 미발표")

            self._update_job_status(job_name, True)

        except Exception as e:
            logging.error(f"[AutoScheduler] 집중 모니터링 실패: {e}")
            self._update_job_status(job_name, False)

        return False

    def _check_new_round_if_not_saturday(self):
        """토요일이 아닐 때만 새 회차 확인"""
        if datetime.now().weekday() != 5:  # 5 = Saturday
            return self._check_new_round()
        else:
            logging.info("[AutoScheduler] 토요일은 집중 모니터링 시간에만 확인")
            return False

    def _run_prediction_for_new_round(self, next_round: int):
        """새 회차를 위한 예측 생성"""
        try:
            logging.info(f"[AutoScheduler] {next_round}회차 예측 생성 중...")

            # [automation-7 FIX] 미사용 DataCollector 생성/임포트 제거(죽은 코드).
            # 실제 예측은 아래 subprocess(main.py --skip-fetch --ml-only)가 수행한다.
            # main.py의 예측 로직 실행
            result = subprocess.run(
                ['python', 'main.py', '--skip-fetch', '--ml-only'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=300  # 5분 타임아웃
            )

            if result.returncode == 0:
                logging.info(f"[AutoScheduler] [O] {next_round}회차 예측 생성 완료!")

                # 예측 완료 알림
                self._notify_prediction_complete()
            else:
                logging.error(f"[AutoScheduler] 예측 생성 실패: {result.stderr}")

        except Exception as e:
            logging.error(f"[AutoScheduler] 예측 생성 오류: {e}")

    def _fetch_latest_round_from_web(self) -> Optional[int]:
        """새 API를 통해 최신 회차 번호 가져오기"""
        try:
            # 2025년 개편된 새 API 사용
            api_url = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.dhlottery.co.kr/lt645/result'
            }

            response = requests.get(
                f'{api_url}?srchLtEpsd=all',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                lst = data.get('data', {}).get('list', [])
                if lst:
                    # 리스트에서 최신 회차 찾기
                    latest = max(item.get('ltEpsd', 0) for item in lst)
                    logging.info(f"[AutoScheduler] 새 API로 최신 회차 확인: {latest}회")
                    return latest

            # 폴백: 기존 방식 시도 (레거시)
            logging.warning("[AutoScheduler] 새 API 실패, 레거시 방식 시도...")
            return self._fetch_latest_round_legacy()

        except requests.exceptions.RequestException as e:
            # [버그수정 2026-06-27] 네트워크/DNS 단절 등 예상 가능한 외부 요인은 오프라인 폴백 (과경보 금지)
            logging.warning(f"[AutoScheduler] 네트워크 미연결로 새 API 조회 실패, 오프라인 폴백 시도: {e}")
            return self._fetch_latest_round_legacy()
        except Exception as e:
            # JSON 키 누락/응답 구조 변경 등 진짜 코드 점검이 필요한 경우만 ERROR 유지
            logging.error(f"[AutoScheduler] 웹 데이터 파싱 오류(코드 점검 필요): {e}")
            return self._fetch_latest_round_legacy()

    def _fetch_latest_round_legacy(self) -> Optional[int]:
        """레거시 방식으로 최신 회차 번호 가져오기 (폴백용)"""
        try:
            # 최신 회차 추정 (토요일 기준)
            base_date = datetime(2002, 12, 7)  # 1회차 추첨일
            current_date = datetime.now()
            weeks_passed = (current_date - base_date).days // 7
            estimated_round = weeks_passed + 1

            # 예전 API 시도 (작동하지 않을 수 있음)
            url = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo="
            for round_num in range(estimated_round, estimated_round - 5, -1):
                try:
                    response = requests.get(url + str(round_num), timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('returnValue') == 'success':
                            return round_num
                except (requests.RequestException, ValueError, KeyError) as e:
                    logging.debug(f"회차 {round_num} 조회 실패: {e}")
                    continue

            # 최종 폴백: 추정값 반환
            # [버그수정 2026-06-27] 네트워크 단절로 동행복권 접근 불가 시 추정 회차로 폴백함을 정직하게 표기
            logging.warning(f"[AutoScheduler] 네트워크 미연결로 동행복권 접근 불가 -> 추정 회차로 오프라인 폴백: {estimated_round}회")
            return estimated_round

        except requests.exceptions.RequestException as e:
            # [버그수정 2026-06-27] 네트워크 단절은 오프라인 폴백 (과경보 금지)
            logging.warning(f"[AutoScheduler] 네트워크 미연결로 레거시 조회 실패(오프라인): {e}")
            return None
        except Exception as e:
            # 진짜 코드 점검이 필요한 경우만 ERROR 유지
            logging.error(f"[AutoScheduler] 레거시 회차 처리 중 오류(코드 점검 필요): {e}")
            return None
    
    def _fetch_and_save_new_round(self, round_num: int) -> bool:
        """새 회차 데이터 수집 및 저장"""
        try:
            # main.py의 fetch_lotto_data 호출
            # [O] FIX: 데이터 수집 타임아웃 60초 -> 180초 (3분)
            result = subprocess.run(
                ['python', 'main.py', '--fetch-only'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=180  # 데이터 수집은 1-2분 소요 가능
            )
            
            if result.returncode == 0:
                # [지속학습 감사 2026-07-04 P2] 부모 프로세스 캐시 무효화: 저장은 subprocess
                # (--fetch-only, 자식)에서 일어나 자식의 invalidate_cache만 호출된다. 부모(상주)
                # 프로세스의 클래스 레벨 인메모리 캐시(_winning_numbers_cache 등)가 남으면 이어지는
                # 갱신 체인(패턴 재분석/16필터 기준 재계산 - 보조계층)이 새 회차 없는 stale 데이터로
                # 돌 수 있어 부모 쪽도 명시 무효화한다(최종예측 경로는 무캐시 직조회라 원래 안전).
                try:
                    from src.core.specialized_databases import LottoNumbersDB
                    LottoNumbersDB.invalidate_cache()
                except Exception as _ic_e:
                    logging.debug(f"[AutoScheduler] 부모 캐시 무효화 생략: {_ic_e}")
                logging.info(f"[AutoScheduler] 회차 {round_num} 데이터 저장 완료")
                return True
            else:
                logging.error(f"[AutoScheduler] 데이터 수집 실패: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"[AutoScheduler] 데이터 저장 실패: {e}")
            return False
    
    def _is_main_py_running(self) -> bool:
        """현재 main.py 프로세스가 이미 실행 중인지 확인"""
        try:
            import psutil
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.pid != current_pid and 'python' in proc.name().lower():
                        cmdline = proc.cmdline()
                        if any('main.py' in arg for arg in cmdline):
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return False

    def _run_daily_prediction(self):
        """일일 예측 실행"""
        job_name = 'daily_prediction'

        # 이미 main.py가 실행 중이면 중복 실행 방지
        if self._is_main_py_running():
            logging.info("[AutoScheduler] 이미 main.py가 실행 중입니다. 일일 예측 subprocess 실행을 건너뜁니다.")
            self._update_job_status(job_name, True)
            return

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

            # 5. 극단성 풀 제거강도 K 자동 재탐색 (주간 데이터 기준 운영 K 갱신)
            #    데이터fetch -> 가중치 재학습(위 단계) -> K curve 재계산 -> 정책 저장 순.
            latest_round = None
            try:
                latest_round = self.db_manager.get_latest_round() if self.db_manager else None
            except Exception:
                latest_round = None
            self._refresh_extremeness_k(latest_round or 0)

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
                # 심각한 항목(database, disk_space)은 WARNING, memory만 실패 시 INFO
                critical_failed = [k for k in failed if k in ('database', 'disk_space')]
                if critical_failed:
                    logging.warning(f"[AutoScheduler] 상태 체크 실패: {failed}")
                    self._send_alert(f"시스템 문제 감지: {failed}")
                else:
                    logging.info(f"[AutoScheduler] 상태 체크 - 비정상 항목: {failed}")
            
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
            # FIX HIGH: 컨텍스트 매니저 사용으로 연결 누수 방지
            with sqlite3.connect('data/lotto_numbers.db') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM lotto_numbers")
                count = cursor.fetchone()[0]
                return count > 0
        except sqlite3.Error as e:
            logging.warning(f"DB 가용성 확인 실패: {e}")
            return False
    
    def _check_disk_space(self) -> bool:
        """디스크 공간 확인"""
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            free_percent = (free / total) * 100
            return free_percent > 10  # 10% 이상 여유 공간
        except (ImportError, OSError) as e:
            logging.debug(f"디스크 공간 확인 실패: {e}. 기본값 True 반환")
            return True
    
    def _check_memory_usage(self) -> bool:
        """메모리 사용량 확인 (95% 이상만 실패 - 필터링 중 90%대는 정상)"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return memory.percent < 95  # 95% 미만 사용
        except (ImportError, AttributeError) as e:
            logging.debug(f"메모리 사용량 확인 실패: {e}. 기본값 True 반환")
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
                # FIX HIGH: 컨텍스트 매니저 사용으로 연결 누수 방지
                with sqlite3.connect(db_path) as conn:
                    conn.execute("VACUUM")
                    conn.execute("ANALYZE")
    
    def _update_filter_criteria(self):
        """주간 필터 기준 갱신.

        [코드리뷰 2026-06-27] 실제 criteria/풀 갱신은 새 회차 감지 경로
        (_trigger_filter_update -> IntegratedFilterManager.update_filters_weekly)가 담당한다.
        과거 이 메서드는 미배선 stub인데 '필터 기준 업데이트' 로그만 찍어 일한 척했다(정직성 결함).
        또한 레거시 16필터는 최종 예측(극단성 풀)에 미사용이라 주간 중복 갱신은 불필요하므로,
        실제 갱신은 새 회차 경로에 위임하고 여기서는 그 사실만 정직하게 기록한다(no-op)."""
        logging.info("[AutoScheduler] 주간 필터 기준 갱신은 새 회차 감지 경로가 담당 (여기선 no-op)")
    
    def _retrain_models(self):
        """ML 모델 재학습"""
        # 캐시 삭제로 다음 실행 시 자동 재학습
        model_cache = 'cache/models'
        if os.path.exists(model_cache):
            import shutil
            shutil.rmtree(model_cache)
            os.makedirs(model_cache)
    
    def _notify_prediction_complete(self):
        """예측 완료 통지.
        [코드리뷰 2026-06-27] 외부 알림 채널(이메일/텔레그램/웹훅)은 미구현이라 실제 '전송'은
        일어나지 않는다. '전송' 표현이 외부 발신을 오인시키므로 내부 로깅만임을 정직 표기."""
        logging.info("[AutoScheduler] 예측 완료 (알림 채널 미구성: 내부 로깅만)")

    def _send_alert(self, message: str):
        """경고 통지.
        [코드리뷰 2026-06-27] 외부 알림 채널 미구현, 내부 로깅만 수행(정직 표기)."""
        logging.critical(f"[AutoScheduler] [!] {message} (알림 채널 미구성: 내부 로깅만)")
    
    def _trigger_update_chain(self, round_num: int):
        """
        새 회차 추가 시 자동 업데이트 콜백 체인 실행

        Args:
            round_num: 새로 추가된 회차 번호
        """
        try:
            logging.info(f"[AutoScheduler] 자동 업데이트 체인 시작: {round_num}회차")

            # 1. 패턴 재분석
            self._trigger_pattern_reanalysis(round_num)

            # 2. 필터 업데이트
            self._trigger_filter_update(round_num)

            # 3. ML 캐시 무효화
            self._invalidate_ml_cache()

            # 4. 시스템 상태 업데이트
            self._update_system_state(round_num)

            # 5. 극단성 풀 제거강도 K 자동 재탐색 (새 데이터 -> 운영 K 갱신)
            #    실패해도 기존 정책을 유지하므로 체인을 중단시키지 않는다.
            self._refresh_extremeness_k(round_num)

            logging.info(f"[AutoScheduler] [O] 자동 업데이트 체인 완료: {round_num}회차")

        except Exception as e:
            logging.error(f"[AutoScheduler] 자동 업데이트 체인 실패: {e}")

    def _refresh_extremeness_k(self, round_num: int):
        """극단성 풀 제거강도 K(=임계값) 자동 재탐색 후 정책 json 저장.

        흐름: 데이터fetch(이미 완료) -> (가중치 최적화는 별도 백그라운드) ->
        walk-forward Wilson LCB 곡선 재계산 -> select_target_k -> 정책 json 저장.
        예측은 이후 이 정책 json(SSOT)을 읽어 풀을 형성한다(ExtremenessPoolPredictor).

        정직성: AUC ~ 0.51 약신호이므로 '수학적 최적 K'가 아니라 '현재 검증창에서 가장
        방어 가능한 운영 K'를 고른다. 실패 시 기존 정책을 유지(방어).

        주의(상주): 이 메서드는 --24h 상주 모드의 AutoScheduler 에서 새 회차/주간 시점에
        호출된다. plain main.py(1사이클 후 종료)에서는 main.py 의 동기 stale 체크가 담당한다.
        """
        try:
            logging.info("[AutoScheduler] 5/5: 극단성 풀 K 자동 재탐색 시작...")
            from src.core import extremeness_threshold_selector as sel
            policy = sel.refresh_policy(self.db_manager)
            logging.info(
                f"[AutoScheduler] [O] K 재탐색 완료: effective_K={policy.get('effective_target_K'):,}, "
                f"evidence={policy.get('evidence')} (round={policy.get('round')})")
        except Exception as e:
            logging.error(f"[AutoScheduler] 극단성 풀 K 재탐색 실패(기존 정책 유지): {e}")

    def _trigger_pattern_reanalysis(self, round_num: int):
        """패턴 재분석 트리거"""
        try:
            logging.info("[AutoScheduler] 1/4: 패턴 재분석 시작...")

            # PatternManager를 사용한 패턴 분석
            from src.core.pattern_manager import PatternManager
            pattern_mgr = PatternManager(self.db_manager)

            # 최신 회차 번호 조회 후 analyze_patterns(round_num) 호출
            all_rounds = self.db_manager.get_numbers_with_bonus()
            latest_round = all_rounds[-1][0] if all_rounds else round_num
            pattern_mgr.analyze_patterns(latest_round)

            logging.info(f"[AutoScheduler] [O] 패턴 재분석 완료: 회차={latest_round}")

        except Exception as e:
            logging.error(f"[AutoScheduler] 패턴 재분석 실패: {e}")

    def _trigger_filter_update(self, round_num: int):
        """필터 업데이트 트리거"""
        try:
            logging.info("[AutoScheduler] 2/4: 필터 업데이트 시작...")

            # IntegratedFilterManager를 통한 필터 업데이트
            from src.core.integrated_filter_manager import IntegratedFilterManager

            # [automation-4 FIX] 임계값을 직접 YAML 파싱(잘못된 기본값 2.0, 단일 소스 우회)하지 않고
            # ThresholdManager 싱글톤(단일 소스 of truth)에서 조회한다.
            # ThresholdManager는 첫 호출 시 adaptive_filter_config.yaml을 자동 로드하므로
            # 항상 현재 적용 중인 실제 임계값과 일치한다.
            from src.core.threshold_manager import get_threshold_manager
            threshold = get_threshold_manager().get_threshold()

            filter_mgr = IntegratedFilterManager(self.db_manager, threshold)
            update_result = filter_mgr.update_filters_weekly(round_num)

            logging.info(f"[AutoScheduler] [O] 필터 업데이트 완료: {update_result.get('updated_filters', [])}개 필터")

        except Exception as e:
            logging.error(f"[AutoScheduler] 필터 업데이트 실패: {e}")

    def _invalidate_ml_cache(self):
        """ML 캐시 점검 (3/4)

        [2026-06-06 수정] 과거: cache/models 전체를 shutil.rmtree로 삭제 -> 새 회차 감지마다
        재사용 가능한 모델까지 통째로 날려 다음 실행이 처음부터 재학습(느림)하게 만들었다.
        그러나 LSTM/앙상블은 trained_round != 최신회차면 자동 재학습+재저장(회차 스탬프 재사용
        로직)하므로 캐시를 '물리 삭제'할 필요가 없다(불필요+파괴적, 재사용 최적화 무력화).
        -> 물리 삭제 제거. 모델 staleness 는 회차 스탬프 비교가 안전하게 처리한다.
        """
        try:
            logging.info("[AutoScheduler] 3/4: ML 캐시 점검 (회차 스탬프 기반 - 물리삭제 없음)")
            # 의도적 no-op: 회차 불일치 시 각 예측기가 자동 재학습/재저장하므로 캐시 보존이 안전.
            logging.info("[AutoScheduler] [O] ML 캐시는 회차 스탬프로 자동 갱신됨 (재사용 최적화 보존)")
        except Exception as e:
            logging.error(f"[AutoScheduler] ML 캐시 점검 실패: {e}")

    def _update_system_state(self, round_num: int):
        """시스템 상태 업데이트"""
        try:
            logging.info("[AutoScheduler] 4/4: 시스템 상태 업데이트 시작...")

            from src.core.system_state_manager import SystemStateManager

            state_mgr = SystemStateManager()
            state_mgr.update_state(round_num, components=['all', 'pattern', 'filter', 'ml'])

            logging.info(f"[AutoScheduler] [O] 시스템 상태 업데이트 완료: {round_num}회차")

        except Exception as e:
            logging.error(f"[AutoScheduler] 시스템 상태 업데이트 실패: {e}")

    def setup_db_callbacks(self):
        """DatabaseManager 콜백 등록"""
        if self.db_manager:
            # 새 회차 추가 시 자동 업데이트
            self.db_manager.register_callback('new_round_added', self._on_new_round_added)
            logging.info("[AutoScheduler] DatabaseManager 콜백 등록 완료")

    def _on_new_round_added(self, round_num: int):
        """새 회차 추가 시 콜백 핸들러"""
        logging.info(f"[AutoScheduler] [NEW] 새 회차 감지: {round_num}회차")
        self._trigger_update_chain(round_num)

    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태 반환"""
        return {
            'running': self.running,
            'jobs': self.job_status,
            'next_runs': {
                job.job_func.__name__: job.next_run
                for job in self.scheduler.jobs
            }
        }