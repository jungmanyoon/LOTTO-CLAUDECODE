#!/usr/bin/env python3
"""
스마트 자동 학습 시스템
- 프로그램 재시작 시 즉시 학습
- 동적 학습 주기 조정
- 재시작 빈도 추적
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import threading
import time

class SmartAutoLearning:
    """스마트 자동 학습 관리자"""
    
    def __init__(self, db_manager, config_path='data/smart_learning_config.json'):
        self.db_manager = db_manager
        self.config_path = config_path
        self.state_path = 'data/smart_learning_state.json'
        self.is_running = False
        self.learning_thread = None
        
        # 기본 설정
        self.default_config = {
            'min_interval_minutes': 30,  # 최소 학습 간격 (분)
            'max_interval_minutes': 60,  # 최대 학습 간격 (분)
            'restart_threshold_minutes': 30,  # 재시작 시 학습 트리거 시간
            'dynamic_adjustment': True,  # 동적 주기 조정 활성화
            'immediate_on_restart': True,  # 재시작 시 즉시 학습
            'track_restart_frequency': True,  # 재시작 빈도 추적
            'learning_triggers': {
                'time_based': True,  # 시간 기반 트리거
                'restart_based': True,  # 재시작 기반 트리거
                'round_based': True,  # 회차 변경 기반 트리거
                'performance_based': True  # 성능 기반 트리거
            }
        }
        
        # 설정 및 상태 로드
        self.config = self.load_config()
        self.state = self.load_state()
        
        # 재시작 감지 및 처리
        self.handle_restart()
        
    def load_config(self) -> Dict:
        """설정 파일 로드"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 기본값과 병합
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                logging.error(f"설정 파일 로드 실패: {e}")
        
        # 기본 설정 저장
        self.save_config(self.default_config)
        return self.default_config.copy()
    
    def save_config(self, config: Dict):
        """설정 파일 저장"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"설정 파일 저장 실패: {e}")
    
    def load_state(self) -> Dict:
        """상태 파일 로드"""
        default_state = {
            'last_learning_time': None,
            'last_restart_time': datetime.now().isoformat(),
            'restart_count_today': 0,
            'restart_history': [],
            'learning_history': [],
            'current_interval_minutes': self.config['max_interval_minutes'],
            'average_restart_interval': 60,  # 평균 재시작 간격 (분)
            'total_restart_count': 0,
            'total_learning_count': 0
        }
        
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    # 기본값 병합
                    for key, value in default_state.items():
                        if key not in state:
                            state[key] = value
                    return state
            except Exception as e:
                logging.error(f"상태 파일 로드 실패: {e}")
        
        return default_state
    
    def save_state(self):
        """상태 파일 저장"""
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        try:
            with open(self.state_path, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"상태 파일 저장 실패: {e}")
    
    def handle_restart(self):
        """프로그램 재시작 처리"""
        now = datetime.now()
        
        # 재시작 추적
        if self.config.get('track_restart_frequency', True):
            # 마지막 재시작 시간
            if self.state.get('last_restart_time'):
                last_restart = datetime.fromisoformat(self.state['last_restart_time'])
                interval = (now - last_restart).total_seconds() / 60  # 분 단위
                
                # 재시작 이력 업데이트 (최근 10개만 유지)
                self.state['restart_history'].append({
                    'time': now.isoformat(),
                    'interval_minutes': interval
                })
                if len(self.state['restart_history']) > 10:
                    self.state['restart_history'] = self.state['restart_history'][-10:]
                    self.save_state()  # 재시작 이력 업데이트 후 저장
                
                # 평균 재시작 간격 계산
                if len(self.state['restart_history']) >= 3:
                    intervals = [h['interval_minutes'] for h in self.state['restart_history'][-5:]]
                    self.state['average_restart_interval'] = sum(intervals) / len(intervals)
                    self.save_state()  # 평균 재시작 간격 업데이트 후 저장
            
            # 오늘 재시작 횟수 추적
            today = now.date()
            if self.state.get('last_restart_time'):
                last_date = datetime.fromisoformat(self.state['last_restart_time']).date()
                if last_date == today:
                    self.state['restart_count_today'] += 1
                else:
                    self.state['restart_count_today'] = 1
            else:
                self.state['restart_count_today'] = 1
            
            self.state['last_restart_time'] = now.isoformat()
            self.state['total_restart_count'] += 1
            self.save_state()  # 재시작 정보 업데이트 후 저장
        
        # 즉시 학습 필요 여부 판단
        should_learn = False
        reason = ""
        
        if self.config.get('immediate_on_restart', True):
            if self.state.get('last_learning_time'):
                last_learning = datetime.fromisoformat(self.state['last_learning_time'])
                minutes_since = (now - last_learning).total_seconds() / 60
                
                threshold = self.config.get('restart_threshold_minutes', 30)
                if minutes_since >= threshold:
                    should_learn = True
                    reason = f"재시작 감지: 마지막 학습으로부터 {minutes_since:.1f}분 경과"
                else:
                    logging.info(f"재시작 감지: 마지막 학습이 {minutes_since:.1f}분 전 (임계값: {threshold}분)")
            else:
                should_learn = True
                reason = "첫 실행: 초기 학습 필요"
        
        # 동적 학습 주기 조정
        if self.config.get('dynamic_adjustment', True):
            self.adjust_learning_interval()
        
        # 즉시 학습 실행
        if should_learn:
            logging.info(f"[SMART LEARNING] {reason}")
            self.trigger_learning(reason)
        
        # 백그라운드 학습 스케줄러 시작
        self.start_scheduler()
    
    def adjust_learning_interval(self):
        """동적 학습 주기 조정"""
        avg_restart = self.state.get('average_restart_interval', 60)
        min_interval = self.config['min_interval_minutes']
        max_interval = self.config['max_interval_minutes']
        
        # 재시작이 빈번하면 학습 주기를 줄임
        if avg_restart < 30:  # 30분 이내 자주 재시작
            new_interval = min_interval
            logging.info(f"[SMART LEARNING] 빈번한 재시작 감지: 학습 주기를 {new_interval}분으로 단축")
        elif avg_restart < 60:  # 1시간 이내 재시작
            new_interval = (min_interval + max_interval) / 2
            logging.info(f"[SMART LEARNING] 중간 빈도 재시작: 학습 주기를 {new_interval}분으로 조정")
        else:  # 1시간 이상 유지
            new_interval = max_interval
            logging.info(f"[SMART LEARNING] 안정적 실행: 학습 주기를 {new_interval}분으로 유지")
        
        self.state['current_interval_minutes'] = new_interval
        self.save_state()  # 학습 주기 변경 후 저장
    
    def trigger_learning(self, reason: str = "정기 학습"):
        """학습 트리거"""
        try:
            now = datetime.now()
            logging.info(f"[SMART LEARNING] 학습 시작: {reason}")
            
            # 학습 이력 추가
            self.state['learning_history'].append({
                'time': now.isoformat(),
                'reason': reason
            })
            if len(self.state['learning_history']) > 20:
                self.state['learning_history'] = self.state['learning_history'][-20:]
            
            self.state['last_learning_time'] = now.isoformat()
            self.state['total_learning_count'] += 1
            self.save_state()  # 학습 정보 업데이트 후 저장
            
            # 실제 학습 로직 호출 (비동기)
            threading.Thread(target=self.run_learning, args=(reason,), daemon=True).start()
            
        except Exception as e:
            logging.error(f"[SMART LEARNING] 학습 트리거 실패: {e}")
    
    def run_learning(self, reason: str):
        """실제 학습 실행"""
        try:
            logging.info(f"[SMART LEARNING] 학습 시작: {reason}")
            
            # 향상된 피드백 루프 시스템 실행
            try:
                from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop
                
                # 향상된 피드백 루프 초기화 (db_manager만 전달)
                enhanced_feedback = EnhancedFeedbackLoop(
                    db_manager=self.db_manager
                )
                
                # 최신 회차 정보 가져오기
                latest_round = self.db_manager.get_latest_round()
                if latest_round is None:
                    logging.warning("[SMART LEARNING] 데이터베이스에서 회차 정보를 가져올 수 없습니다.")
                    return

                # 자동 개선 실행 (1회) - 최근 50회차 백테스팅
                start_round = max(1, latest_round - 50)
                end_round = latest_round

                logging.info(f"[SMART LEARNING] 백테스팅 범위: {start_round}회차 ~ {end_round}회차")
                improvement_result = enhanced_feedback.run_improvement_cycle(
                    start_round=start_round,
                    end_round=end_round,
                    max_iterations=1
                )
                
                if improvement_result and improvement_result.get('improved', False):
                    logging.info(f"[SMART LEARNING] 성능 개선 완료!")
                    logging.info(f"  - 이전 성능: {improvement_result.get('old_performance', 0):.4f}")
                    logging.info(f"  - 새 성능: {improvement_result.get('new_performance', 0):.4f}")
                    logging.info(f"  - 개선율: {improvement_result.get('improvement_rate', 0):.2%}")
                else:
                    logging.info(f"[SMART LEARNING] 현재 최적 상태 유지")
                
                # 자동 개선 상태 업데이트
                state_file = 'data/auto_improvement_state.json'
                if os.path.exists(state_file):
                    with open(state_file, 'r', encoding='utf-8') as f:
                        auto_state = json.load(f)
                    auto_state['last_updated'] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(auto_state, f, indent=2, ensure_ascii=False)
                
                self.state['last_learning_success'] = True
                self.save_state()  # 학습 성공 상태 저장
                
            except ImportError as e:
                logging.warning(f"[SMART LEARNING] 향상된 피드백 루프 사용 불가: {e}")
                # 대체 학습 로직 (간단한 백테스팅)
                try:
                    from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
                    backtesting = OptimizedBacktestingFramework(self.db_manager)
                    result = backtesting.run_backtest(test_rounds=50)
                    logging.info(f"[SMART LEARNING] 백테스팅 완료: 평균 매치 {result.get('average_matches', 0):.2f}개")
                    self.state['last_learning_success'] = True
                    self.save_state()  # 학습 성공 상태 저장
                except Exception as e2:
                    logging.error(f"[SMART LEARNING] 대체 학습도 실패: {e2}")
                    self.state['last_learning_success'] = False
                    self.save_state()  # 대체 학습 실패 상태 저장
            
            logging.info(f"[SMART LEARNING] 학습 완료: {reason}")
            
        except Exception as e:
            logging.error(f"[SMART LEARNING] 학습 실행 실패: {e}")
            self.state['last_learning_success'] = False
            self.save_state()  # 학습 실패 상태 저장
    
    def start_scheduler(self):
        """백그라운드 학습 스케줄러 시작"""
        if not self.is_running:
            self.is_running = True
            self.learning_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            self.learning_thread.start()
            logging.info(f"[SMART LEARNING] 스케줄러 시작 (주기: {self.state['current_interval_minutes']}분)")
    
    def scheduler_loop(self):
        """스케줄러 루프"""
        while self.is_running:
            try:
                # 현재 학습 주기
                interval_seconds = self.state['current_interval_minutes'] * 60
                
                # 대기
                time.sleep(interval_seconds)
                
                if not self.is_running:
                    break
                
                # 학습 트리거
                self.trigger_learning("정기 학습")
                
                # 동적 조정
                if self.config.get('dynamic_adjustment', True):
                    self.adjust_learning_interval()
                
            except Exception as e:
                logging.error(f"[SMART LEARNING] 스케줄러 오류: {e}")
                time.sleep(60)  # 오류 시 1분 대기
    
    def stop(self):
        """스케줄러 중지"""
        self.is_running = False
        if self.learning_thread and self.learning_thread.is_alive():
            self.learning_thread.join(timeout=5)
        logging.info("[SMART LEARNING] 스케줄러 중지")
    
    def get_status(self) -> Dict:
        """현재 상태 반환"""
        now = datetime.now()
        status = {
            'is_running': self.is_running,
            'current_interval_minutes': self.state['current_interval_minutes'],
            'restart_count_today': self.state['restart_count_today'],
            'total_restart_count': self.state['total_restart_count'],
            'total_learning_count': self.state['total_learning_count'],
            'average_restart_interval': self.state['average_restart_interval']
        }
        
        if self.state.get('last_learning_time'):
            last_learning = datetime.fromisoformat(self.state['last_learning_time'])
            status['minutes_since_learning'] = (now - last_learning).total_seconds() / 60
        else:
            status['minutes_since_learning'] = None
        
        if self.state.get('last_restart_time'):
            last_restart = datetime.fromisoformat(self.state['last_restart_time'])
            status['minutes_since_restart'] = (now - last_restart).total_seconds() / 60
        else:
            status['minutes_since_restart'] = None
        
        return status