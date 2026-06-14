#!/usr/bin/env python3
"""
자동화된 필터 업데이트 스케줄러
매주 자동으로 필터를 업데이트하고 814만개 조합을 재필터링

[DEAD/미사용 - 최종예측 무관]
이 모듈(AutomatedFilterScheduler)은 현재 어떤 진입점에도 연결되어 있지 않다(미인스턴스화).
실제 주간 자동화 경로는 src/automation/auto_scheduler.py가 담당하며, 최종 5세트 예측은
극단성 풀(ExtremenessPoolPredictor)이 생성한다. 본 클래스의 정교한 5단계 파이프라인 로그
('STEP 1/5 백업' ~ '주간 업데이트 완료' 등)는 실제 운영에서 실행되지 않는다.
"""
import logging
import time
from datetime import datetime, timedelta
import json
import os
import threading
from typing import Dict, Any, Optional

class AutomatedFilterScheduler:
    """
    자동화된 필터 스케줄러
    - 매주 토요일 저녁 당첨번호 업데이트 후 필터 재조정
    - 814만개 조합 재필터링
    - 자동 백업 및 복구
    """
    
    def __init__(self, integrated_manager, db_manager):
        """
        Args:
            integrated_manager: IntegratedFilterManager 인스턴스
            db_manager: DatabaseManager 인스턴스
        """
        self.integrated_manager = integrated_manager
        self.db_manager = db_manager
        
        # 스케줄 설정
        self.schedule_day = 6  # 토요일 (0=월요일, 6=일요일)
        self.schedule_hour = 21  # 오후 9시
        
        # 히스토리 파일 경로
        self.history_file = 'data/scheduler_history.json'
        
        # 실행 히스토리
        self.execution_history = self._load_history()
        
        # 실행 상태 (Thread-Safe)
        self.is_running = False
        self.last_execution = None
        self._execution_lock = threading.Lock()  # Race Condition 방지

        logging.info("[자동화 스케줄러] 초기화 완료")
    
    def _load_history(self) -> list:
        """히스토리 로드"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (ImportError, AttributeError) as e:
                logging.debug(f"스케줄러 import 실패: {e}")
                return []
        return []
    
    def _save_history(self):
        """히스토리 저장"""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.execution_history[-100:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"히스토리 저장 실패: {e}")
    
    def check_new_round(self) -> Optional[int]:
        """
        새로운 회차 확인
        
        Returns:
            새 회차 번호 또는 None
        """
        try:
            current_round = self.db_manager.get_last_round()
            
            # 마지막 실행 회차 확인
            last_processed_round = self._get_last_processed_round()
            
            if current_round > last_processed_round:
                logging.info(f"[자동화] 새 회차 감지: {current_round} (이전: {last_processed_round})")
                return current_round
            
            return None
            
        except Exception as e:
            logging.error(f"회차 확인 실패: {e}")
            return None
    
    def _get_last_processed_round(self) -> int:
        """마지막으로 처리한 회차 번호"""
        if self.execution_history:
            return self.execution_history[-1].get('round', 0)
        return 0
    
    def execute_weekly_update(self, force: bool = False) -> Dict[str, Any]:
        """
        주간 업데이트 실행 (Thread-Safe)

        Args:
            force: 강제 실행 여부

        Returns:
            실행 결과
        """
        # FIX: Race Condition 방지 - 락 획득 시도
        if not self._execution_lock.acquire(blocking=False):
            logging.warning("[자동화] 이미 다른 업데이트가 진행 중입니다. 건너뜀")
            return {
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'message': 'Another update is already running',
                'skipped': True
            }

        try:
            # 이중 체크 (Double-checked locking)
            if self.is_running:
                logging.warning("[자동화] 업데이트가 이미 실행 중입니다")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'success': False,
                    'message': 'Update already running',
                    'skipped': True
                }

            self.is_running = True

            logging.info("\n" + "="*80)
            logging.info("[자동화] 주간 필터 업데이트 프로세스 시작")
            logging.info("="*80)

            start_time = time.time()
            result = {
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'steps': {}
            }

            try:
                # 1. 새 회차 확인
                new_round = self.check_new_round()
                if not new_round and not force:
                    logging.info("[자동화] 새 회차가 없습니다. 업데이트 건너뜀")
                    result['message'] = "No new round"
                    return result

                result['round'] = new_round or self.db_manager.get_last_round()

                # 2. 백업 생성
                logging.info("\n[STEP 1/5] 현재 상태 백업...")
                backup_result = self._create_backup()
                result['steps']['backup'] = backup_result

                # 3. 필터 업데이트
                logging.info("\n[STEP 2/5] 필터 기준 업데이트...")
                update_result = self.integrated_manager.update_filters_weekly(new_round)
                result['steps']['filter_update'] = {
                    'success': 'error' not in update_result,
                    'updated_filters': len(update_result.get('updated_filters', [])),
                    'duration': update_result.get('duration', 0)
                }

                # 4. 814만개 조합 재필터링
                logging.info("\n[STEP 3/5] 전체 조합 재필터링...")
                refilter_start = time.time()
                self._refilter_all_combinations()
                result['steps']['refiltering'] = {
                    'success': True,
                    'duration': time.time() - refilter_start
                }

                # 5. 검증
                logging.info("\n[STEP 4/5] 필터링 결과 검증...")
                validation_result = self._validate_filtering()
                result['steps']['validation'] = validation_result

                # 6. 리포트 생성
                logging.info("\n[STEP 5/5] 리포트 생성...")
                report = self._generate_report(result)
                result['steps']['report'] = {'success': True, 'path': report}

                # 성공 처리
                result['success'] = True
                result['duration'] = time.time() - start_time

                # 히스토리 저장
                self.execution_history.append(result)
                self._save_history()

                # 결과 출력
                logging.info("\n" + "="*80)
                logging.info("[자동화] 주간 업데이트 완료")
                logging.info(f"  - 회차: {result['round']}")
                logging.info(f"  - 소요 시간: {result['duration']:.1f}초")
                logging.info(f"  - 결과: {'성공' if result['success'] else '실패'}")
                logging.info("="*80)

            except Exception as e:
                logging.error(f"주간 업데이트 실패: {e}")
                import traceback
                traceback.print_exc()
                result['error'] = str(e)

            return result

        finally:
            # 락 해제 및 상태 초기화
            self.is_running = False
            self._execution_lock.release()
    
    def _create_backup(self) -> Dict[str, Any]:
        """백업 생성"""
        try:
            backup_dir = f"backup/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(backup_dir, exist_ok=True)
            
            # 설정 파일 백업
            import shutil
            config_files = [
                'config.yaml',
                'configs/adaptive_filter_config.yaml'
            ]
            
            for config in config_files:
                if os.path.exists(config):
                    shutil.copy2(config, backup_dir)
            
            logging.info(f"  백업 생성 완료: {backup_dir}")
            return {'success': True, 'path': backup_dir}
            
        except Exception as e:
            logging.error(f"백업 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def _refilter_all_combinations(self):
        """814만개 조합 재필터링"""
        try:
            # 전체 조합 수 확인
            total = self.db_manager.combinations_db.count_all_combinations()
            logging.info(f"  전체 조합: {total:,}개")
            
            # 배치 단위로 처리
            batch_size = 100000
            processed = 0
            filtered_count = 0
            
            for offset in range(0, total, batch_size):
                # 배치 가져오기
                batch = self._get_batch(offset, batch_size)
                if not batch:
                    break
                
                # 필터링
                filtered = self.integrated_manager.apply_all_filters(
                    batch, 
                    self.db_manager.get_last_round()
                )
                
                filtered_count += len(filtered)
                processed += len(batch)
                
                # 진행률 출력 (10% 단위)
                progress = (processed / total) * 100
                if progress % 10 < (batch_size / total) * 100:
                    logging.info(f"    진행: {progress:.0f}% ({filtered_count:,}/{processed:,})")
            
            exclusion_rate = (1 - filtered_count/total) * 100 if total > 0 else 0
            logging.info(f"  재필터링 완료: {filtered_count:,}/{total:,} ({exclusion_rate:.1f}% 제외)")
            
        except Exception as e:
            logging.error(f"재필터링 실패: {e}")
            raise
    
    def _get_batch(self, offset: int, limit: int) -> list:
        """배치 데이터 가져오기"""
        try:
            with self.db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT combination FROM base_combinations LIMIT ? OFFSET ?",
                    (limit, offset)
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"배치 로드 실패: {e}")
            return []
    
    def _validate_filtering(self) -> Dict[str, Any]:
        """필터링 검증"""
        try:
            # 최근 10개 당첨번호로 검증
            recent_winners = self.db_manager.get_all_winning_numbers()[:10]
            
            # 각 당첨번호가 필터를 통과하는지 확인
            passed = 0
            for winner in recent_winners:
                result = self.integrated_manager.apply_all_filters([winner], 1182)
                if result:
                    passed += 1
            
            pass_rate = (passed / len(recent_winners)) * 100 if recent_winners else 0
            
            logging.info(f"  검증 완료: {passed}/{len(recent_winners)} 통과 ({pass_rate:.1f}%)")
            
            return {
                'success': True,
                'pass_rate': pass_rate,
                'passed': passed,
                'total': len(recent_winners)
            }
            
        except Exception as e:
            logging.error(f"검증 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_report(self, result: Dict[str, Any]) -> str:
        """리포트 생성"""
        try:
            report_dir = 'reports'
            os.makedirs(report_dir, exist_ok=True)
            
            report_file = os.path.join(
                report_dir, 
                f"weekly_update_{result['round']}_{datetime.now().strftime('%Y%m%d')}.json"
            )
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logging.info(f"  리포트 생성: {report_file}")
            return report_file
            
        except Exception as e:
            logging.error(f"리포트 생성 실패: {e}")
            return ""
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태"""
        return {
            'is_running': self.is_running,
            'last_execution': self.last_execution,
            'last_processed_round': self._get_last_processed_round(),
            'total_executions': len(self.execution_history),
            'schedule': f"매주 토요일 {self.schedule_hour}시"
        }