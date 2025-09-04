"""
자동 조정 시스템
새로운 로또 번호가 나올 때 필터와 모델을 자동으로 조정하는 통합 시스템
"""
import logging
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import yaml
import json
import os
from collections import deque, defaultdict

from ..core.db_manager import DatabaseManager
from ..core.filter_manager import FilterManager
from ..core.parallel_filter_manager import ParallelFilterManager
from ..ml.realtime_learning_system import RealtimeLearningSystem
from ..data_collector import DataCollector


class AutoAdjustmentSystem:
    """자동 조정 시스템 - 새 데이터에 따라 필터와 모델을 동적으로 조정"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        """
        Args:
            db_manager: 데이터베이스 관리자
        """
        self.db_manager = db_manager or DatabaseManager()
        self.data_collector = DataCollector(self.db_manager)
        self.filter_manager = ParallelFilterManager(self.db_manager)
        self.realtime_learning = RealtimeLearningSystem(self.db_manager)
        
        # 성능 모니터링 시스템 초기화
        from ..monitoring.performance_dashboard import PerformanceDashboard
        self.performance_monitor = PerformanceDashboard(self.db_manager)
        
        # 백테스팅 상태 추적
        self.backtesting_state = {
            'total_backtesting_count': 0,
            'last_backtest_round': 0,
            'performance_scores': [],
            'improvement_history': []
        }
        
        # 상태 파일 경로
        self.state_file = 'data/auto_adjustment_state.json'
        self._load_state()
        
        # 조정 설정
        self.config = {
            'check_interval': 3600,  # 1시간마다 체크 (초)
            'analysis_window': 200,  # 최근 N회차 분석 (100 → 200으로 증가)
            'min_data_for_adjustment': 20,  # 최소 데이터 수
            'adjustment_threshold': 0.15,  # 15% 이상 변화 시 조정 (10% → 15%)
            'pattern_detection_window': 100,  # 패턴 감지 윈도우 (50 → 100)
            'filter_update_frequency': 1,  # 매 회차마다 필터 업데이트 (매회 새로운 로또 번호 나올 때마다)
            'performance_threshold': 0.60,  # 성능 임계값 (0.85 → 0.60 현실적으로)
        }
        
        # 패턴 추적
        self.pattern_history = {
            'hot_numbers': deque(maxlen=100),  # 핫넘버 추적
            'cold_numbers': deque(maxlen=100),  # 콜드넘버 추적
            'sum_trends': deque(maxlen=100),  # 합계 추세
            'consecutive_patterns': deque(maxlen=100),  # 연속번호 패턴
            'odd_even_ratios': deque(maxlen=100),  # 홀짝 비율
            'section_distributions': deque(maxlen=100),  # 구간 분포
        }
        
        # 필터 조정 이력
        self.adjustment_history = []
        
        # 성능 메트릭
        self.performance_metrics = {
            'filter_accuracy': deque(maxlen=50),
            'prediction_accuracy': deque(maxlen=50),
            'adjustment_impact': deque(maxlen=50),
        }
        
        logging.info("\n[자동 조정 시스템] 초기화 완료")
        logging.info(f"  - 체크 간격: {self.config['check_interval']}초")
        logging.info(f"  - 분석 윈도우: 최근 {self.config['analysis_window']}회차")
        logging.info(f"  - 필터 업데이트 주기: {self.config['filter_update_frequency']}회차마다")
        logging.info(f"  - 성능 임계값: {self.config['performance_threshold']:.2f}")
        logging.info(f"  - 조정 임계값: {self.config['adjustment_threshold']:.1%} 변화 시")
        logging.info("  - 패턴 추적: 핫/콜드넘버, 합계추세, 연속패턴, 홀짝비율, 구간분포")
    
    def start_monitoring(self, check_on_startup: bool = True):
        """자동 모니터링 시작"""
        logging.debug("자동 조정 시스템 모니터링 시작")
        
        if check_on_startup:
            self.check_and_adjust()
        
        # 주기적 체크 (실제 운영에서는 스케줄러 사용)
        import threading
        def periodic_check():
            # 무한 루프 방지를 위한 개선
            max_iterations = self.config.get('max_iterations', 10)
            iteration = 0
            
            while iteration < max_iterations and self._running:
                # 최소 대기 시간 보장
                wait_time = max(self.config['check_interval'], 3600)  # 최소 1시간
                logging.info(f"[자동 조정] 다음 체크까지 {wait_time/3600:.1f}시간 대기")
                
                time.sleep(wait_time)
                
                if not self._running:
                    break
                    
                try:
                    # 성능 임계치 확인
                    should_adjust = self._should_perform_adjustment()
                    if should_adjust:
                        logging.info(f"[자동 조정] 체크 {iteration + 1}/{max_iterations} 실행")
                        self.check_and_adjust()
                    else:
                        logging.info("[자동 조정] 성능 임계치 충족, 건너뛰기")
                    
                    iteration += 1
                except Exception as e:
                    logging.error(f"자동 조정 중 오류: {e}")
                    logging.error(f"스택 트레이스: {traceback.format_exc()}")
                    # 오류 발생 시 5회 이상이면 중단
                    if iteration > 5:
                        logging.error("잦은 오류로 인해 자동 조정 중단")
                        break
            
            logging.info("[자동 조정] 주기적 체크 종료")
        
        # 스레드 실행 전 플래그 설정
        self._running = True
        self._monitor_thread = threading.Thread(target=periodic_check, daemon=True)
        self._monitor_thread.start()
        
        return self._monitor_thread
    
    def stop_monitoring(self):
        """모니터링 중지"""
        logging.info("[자동 조정] 모니터링 중지 요청")
        self._running = False
        if hasattr(self, '_monitor_thread'):
            self._monitor_thread.join(timeout=5)
            logging.info("[자동 조정] 모니터링 종료됨")
    
    def _load_state(self):
        """저장된 상태 로드"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    self.backtesting_state.update(saved_state)
                logging.debug(f"자동 조정 상태 로드됨: 백테스팅 {self.backtesting_state['total_backtesting_count']}회 실행됨")
            else:
                logging.debug("새로운 자동 조정 상태 시작")
        except Exception as e:
            logging.error(f"상태 로드 중 오류: {e}")
    
    def _save_state(self):
        """현재 상태 저장"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.backtesting_state, f, ensure_ascii=False, indent=2)
            logging.debug(f"자동 조정 상태 저장됨: 백테스팅 {self.backtesting_state['total_backtesting_count']}회")
        except Exception as e:
            logging.error(f"상태 저장 중 오류: {e}")
    
    def _should_perform_adjustment(self) -> bool:
        """조정이 필요한지 판단"""
        try:
            # 최근 백테스팅 결과가 있는지 확인
            if not self.backtesting_state['performance_scores']:
                logging.info("백테스팅 기록이 없어 조정 실행")
                return True
            
            # 최근 성능 점수 확인
            recent_scores = self.backtesting_state['performance_scores'][-5:]  # 최근 5회
            avg_recent_performance = sum(recent_scores) / len(recent_scores) if recent_scores else 0
            
            # 성능 임계치 확인
            performance_threshold = self.config.get('performance_threshold', 0.85)
            
            # 성능이 임계치 이하이거나 백테스팅 횟수가 적으면 조정
            should_adjust = (avg_recent_performance < performance_threshold or 
                           self.backtesting_state['total_backtesting_count'] < 3)
            
            logging.info(f"성능 판단: 평균 {avg_recent_performance:.3f}, 임계값 {performance_threshold:.3f}, 조정 필요: {should_adjust}")
            return should_adjust
            
        except Exception as e:
            logging.error(f"성능 확인 중 오류: {e}")
            return True  # 오류 시 조정 실행
    
    def check_and_adjust(self) -> Dict[str, Any]:
        """새 데이터 확인 및 자동 조정 실행"""
        # 중복 실행 방지
        if hasattr(self, '_last_check_time'):
            elapsed = time.time() - self._last_check_time
            if elapsed < 300:  # 5분 이내에 다시 실행되면 건너뛰기
                logging.warning(f"[자동 조정] 너무 빠른 재실행 방지 ({elapsed:.1f}초 경과)")
                return {'skipped': True, 'reason': 'too_soon'}
        
        self._last_check_time = time.time()
        
        logging.info("\n" + "="*60)
        logging.info("🔄 자동 조정 시스템 - 데이터 확인 및 백테스팅")
        logging.info("="*60)
        
        adjustment_results = {
            'timestamp': datetime.now(),
            'new_data': False,
            'filters_adjusted': False,
            'models_updated': False,
            'adjustments': []
        }
        
        try:
            # 1. 새 데이터 확인
            new_rounds = self._check_for_new_data()
            
            if not new_rounds:
                logging.info("새로운 데이터가 없습니다.")
                # 새 데이터가 없어도 백테스팅은 실행
                logging.info("백테스팅은 계속 실행합니다.")
            
            adjustment_results['new_data'] = True
            adjustment_results['new_rounds'] = new_rounds
            
            logging.info(f"✅ 새로운 회차 감지: {new_rounds}")
            
            # 2. 패턴 분석
            pattern_analysis = self._analyze_recent_patterns()
            adjustment_results['pattern_analysis'] = pattern_analysis
            
            # 3. 필터 조정 필요성 판단
            if self._should_adjust_filters(pattern_analysis):
                logging.info("\n📊 필터 조정이 필요합니다.")
                
                # 4. 필터 기준값 동적 조정
                filter_adjustments = self._adjust_filter_criteria(pattern_analysis)
                adjustment_results['filters_adjusted'] = True
                adjustment_results['filter_adjustments'] = filter_adjustments
                
                # 5. 조정된 필터 적용
                self._apply_adjusted_filters(filter_adjustments)
            
            # 6. ML 모델 업데이트 (새 데이터가 있을 때만)
            if new_rounds:
                for round_data in new_rounds:
                    ml_update_result = self.realtime_learning.update_models_incrementally(
                        self._get_ml_models(),
                        round_data
                    )
                    adjustment_results['models_updated'] = True
            
            # 7. 백테스팅 실행 및 성능 평가 (항상 실행)
            logging.info("\n📊 백테스팅 실행...")
            backtest_performance = self._run_performance_backtest()
            adjustment_results['backtest_performance'] = backtest_performance
            
            # 백테스팅 결과를 로그에 출력
            if backtest_performance:
                logging.info(f"백테스팅 횟수: {backtest_performance.get('backtest_count', 0)}")
                logging.info(f"성능 점수: {backtest_performance.get('performance_score', 0):.3f}")
            
            # 8. 성능 평가 및 피드백
            self._evaluate_adjustment_performance(adjustment_results)
            
            # 9. 조정 이력 저장
            self._save_adjustment_history(adjustment_results)
            
            # 10. 상태 저장
            self._save_state()
            
            logging.info("\n✅ 자동 조정 완료")
            
        except Exception as e:
            logging.error(f"자동 조정 중 오류 발생: {e}")
            adjustment_results['error'] = str(e)
        
        return adjustment_results
    
    def _check_for_new_data(self) -> List[Dict[str, Any]]:
        """새로운 로또 데이터 확인"""
        # 현재 DB의 마지막 회차
        last_db_round = self.db_manager.lotto_db.get_last_round()
        
        # 웹에서 최신 회차 확인
        latest_web_round = self.data_collector.get_latest_round()
        
        if latest_web_round <= last_db_round:
            return []
        
        # 새 데이터 수집
        self.data_collector.fetch_lotto_data()
        
        # 새로 추가된 회차 정보 반환
        new_rounds = []
        for round_num in range(last_db_round + 1, latest_web_round + 1):
            result = self.db_manager.lotto_db.get_numbers_by_round(round_num)
            if result:
                round_no, numbers_str, date = result
                numbers = [int(n) for n in numbers_str.split(',')]
                new_rounds.append({
                    'round': round_num,
                    'numbers': numbers
                })
        
        return new_rounds
    
    def _analyze_recent_patterns(self) -> Dict[str, Any]:
        """최근 패턴 분석 (동적 패턴 추적의 핵심)"""
        window_size = self.config['analysis_window']
        latest_round = self.db_manager.lotto_db.get_last_round()
        start_round = max(1, latest_round - window_size + 1)
        
        logging.info("\n" + "="*60)
        logging.info("📊 동적 패턴 분석 시작")
        logging.info(f"분석 범위: {start_round}회 ~ {latest_round-1}회 (총 {window_size}회)")
        logging.info("="*60)
        
        # 최근 당첨번호 가져오기
        recent_numbers = []
        # 현재 회차는 제외하여 데이터 누출 방지
        for round_num in range(start_round, latest_round):
            result = self.db_manager.lotto_db.get_numbers_by_round(round_num)
            if result:
                round_no, numbers_str, date = result
                numbers = [int(n) for n in numbers_str.split(',')]
                recent_numbers.append((round_num, numbers))
        
        analysis = {
            'timestamp': datetime.now(),
            'window_size': len(recent_numbers),
            'patterns': {}
        }
        
        if not recent_numbers:
            logging.warning("분석할 데이터가 없습니다.")
            return analysis
        
        # 1. 핫/콜드 넘버 분석
        number_frequency = defaultdict(int)
        for _, numbers in recent_numbers:
            for num in numbers:
                number_frequency[num] += 1
        
        avg_frequency = sum(number_frequency.values()) / 45
        hot_numbers = [num for num, freq in number_frequency.items() 
                      if freq > avg_frequency * 1.2]
        cold_numbers = [num for num in range(1, 46) 
                       if number_frequency.get(num, 0) < avg_frequency * 0.8]
        
        logging.info(f"\n[핫넘버 분석]")
        logging.info(f"  - 평균 출현: {avg_frequency:.1f}회")
        logging.info(f"  - 핫넘버 (120% 이상): {hot_numbers[:10]}... (총 {len(hot_numbers)}개)")
        logging.info(f"  - 콜드넘버 (80% 이하): {cold_numbers[:10]}... (총 {len(cold_numbers)}개)")
        
        analysis['patterns']['hot_numbers'] = {
            'numbers': hot_numbers,
            'avg_frequency': avg_frequency,
            'threshold': avg_frequency * 1.2
        }
        
        analysis['patterns']['cold_numbers'] = {
            'numbers': cold_numbers,
            'threshold': avg_frequency * 0.8
        }
        
        # 2. 합계 범위 분석
        sums = [sum(numbers) for _, numbers in recent_numbers]
        sum_stats = {
            'min': min(sums),
            'max': max(sums),
            'mean': np.mean(sums),
            'std': np.std(sums),
            'percentile_10': np.percentile(sums, 10),
            'percentile_90': np.percentile(sums, 90)
        }
        
        logging.info(f"\n[합계 범위 분석]")
        logging.info(f"  - 범위: {sum_stats['min']} ~ {sum_stats['max']}")
        logging.info(f"  - 평균: {sum_stats['mean']:.1f} (표준편차: {sum_stats['std']:.1f})")
        logging.info(f"  - 권장 범위: {sum_stats['percentile_10']:.0f} ~ {sum_stats['percentile_90']:.0f} (10~90 percentile)")
        
        analysis['patterns']['sum_range'] = sum_stats
        
        # 3. 연속번호 패턴
        consecutive_counts = []
        consecutive_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for _, numbers in recent_numbers:
            count = 0
            for i in range(len(numbers) - 1):
                if numbers[i + 1] - numbers[i] == 1:
                    count += 1
            consecutive_counts.append(count)
            if count in consecutive_distribution:
                consecutive_distribution[count] += 1
        
        consecutive_stats = {
            'avg_count': np.mean(consecutive_counts),
            'max_count': max(consecutive_counts),
            'frequency': sum(1 for c in consecutive_counts if c > 0) / len(consecutive_counts)
        }
        
        logging.info(f"\n[연속번호 패턴 분석]")
        logging.info(f"  - 평균 연속 개수: {consecutive_stats['avg_count']:.2f}개")
        logging.info(f"  - 최대 연속: {consecutive_stats['max_count']}개")
        logging.info(f"  - 연속 출현율: {consecutive_stats['frequency']:.1%}")
        for count, freq in consecutive_distribution.items():
            if freq > 0:
                logging.info(f"    {count}개 연속: {freq}회 ({freq/len(consecutive_counts)*100:.1f}%)")
        
        analysis['patterns']['consecutive'] = consecutive_stats
        
        # 4. 홀짝 비율
        odd_counts = []
        odd_even_distribution = {}
        for _, numbers in recent_numbers:
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            even_count = 6 - odd_count
            odd_counts.append(odd_count)
            ratio = f"{odd_count}:{even_count}"
            odd_even_distribution[ratio] = odd_even_distribution.get(ratio, 0) + 1
        
        logging.info(f"\n[홀짝 비율 분석]")
        logging.info(f"  - 평균 홀수 개수: {np.mean(odd_counts):.1f}개")
        sorted_ratios = sorted(odd_even_distribution.items(), key=lambda x: x[1], reverse=True)
        for ratio, count in sorted_ratios[:5]:
            logging.info(f"    {ratio} 비율: {count}회 ({count/len(odd_counts)*100:.1f}%)")
        
        analysis['patterns']['odd_even'] = {
            'avg_odd_count': np.mean(odd_counts),
            'common_ratios': self._get_common_values(odd_counts, top_n=3)
        }
        
        # 5. 구간 분포
        section_distributions = []
        for _, numbers in recent_numbers:
            sections = [0] * 5  # 1-9, 10-19, 20-29, 30-39, 40-45
            for num in numbers:
                if num <= 9:
                    sections[0] += 1
                elif num <= 19:
                    sections[1] += 1
                elif num <= 29:
                    sections[2] += 1
                elif num <= 39:
                    sections[3] += 1
                else:
                    sections[4] += 1
            section_distributions.append(sections)
        
        avg_sections = np.mean(section_distributions, axis=0)
        
        logging.info(f"\n[구간 분포 분석]")
        section_labels = ['1-9', '10-19', '20-29', '30-39', '40-45']
        for i, label in enumerate(section_labels):
            logging.info(f"  - {label}: 평균 {avg_sections[i]:.2f}개")
        
        analysis['patterns']['sections'] = {
            'avg_distribution': avg_sections.tolist(),
            'balanced_threshold': 0.5  # 각 구간 최소 0.5개
        }
        
        # 6. AC값 (Arithmetic Complexity)
        ac_values = []
        for _, numbers in recent_numbers:
            ac = self._calculate_ac_value(numbers)
            ac_values.append(ac)
        
        analysis['patterns']['ac_value'] = {
            'avg': np.mean(ac_values),
            'min': min(ac_values),
            'max': max(ac_values),
            'common_range': [np.percentile(ac_values, 20), np.percentile(ac_values, 80)]
        }
        
        logging.info("\n" + "="*60)
        logging.info("📊 동적 패턴 분석 완료 - 필터 조정 근거 확보")
        logging.info("="*60)
        
        # 패턴 이력 업데이트
        self._update_pattern_history(analysis['patterns'])
        
        return analysis
    
    def _should_adjust_filters(self, pattern_analysis: Dict[str, Any]) -> bool:
        """필터 조정 필요성 판단"""
        if not self.pattern_history['sum_trends']:
            return True  # 첫 실행
        
        # 최근 N회차마다 필터 업데이트
        last_adjustment = self.adjustment_history[-1] if self.adjustment_history else None
        if last_adjustment:
            rounds_since_adjustment = (self.db_manager.lotto_db.get_last_round() - 
                                     last_adjustment.get('round', 0))
            if rounds_since_adjustment >= self.config['filter_update_frequency']:
                return True
        
        # 패턴 변화율 확인
        threshold = self.config['adjustment_threshold']
        
        # 합계 범위 변화
        current_sum_mean = pattern_analysis['patterns']['sum_range']['mean']
        recent_sum_trends = list(self.pattern_history['sum_trends'])[-10:]
        if recent_sum_trends:
            historical_sum_mean = np.mean([p['mean'] for p in recent_sum_trends])
            sum_change = abs(current_sum_mean - historical_sum_mean) / historical_sum_mean
        else:
            sum_change = 0
        
        if sum_change > threshold:
            logging.info(f"합계 평균 {sum_change:.1%} 변화 감지")
            return True
        
        # 핫넘버 변화
        current_hot = set(pattern_analysis['patterns']['hot_numbers']['numbers'])
        if len(self.pattern_history['hot_numbers']) > 0:
            previous_hot = set(self.pattern_history['hot_numbers'][-1])
            hot_change = len(current_hot ^ previous_hot) / 45  # 변화된 번호 비율
            if hot_change > threshold:
                logging.info(f"핫넘버 {hot_change:.1%} 변화 감지")
                return True
        
        return False
    
    def _adjust_filter_criteria(self, pattern_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """필터 기준값 동적 조정"""
        adjustments = {}
        patterns = pattern_analysis['patterns']
        
        # 1. 합계 범위 필터 조정
        sum_stats = patterns['sum_range']
        adjustments['sum_range'] = {
            'min_sum': int(sum_stats['percentile_10']),
            'max_sum': int(sum_stats['percentile_90'])
        }
        
        # 2. 연속번호 필터 조정
        consecutive_stats = patterns['consecutive']
        if consecutive_stats['frequency'] > 0.7:  # 70% 이상에서 연속번호 출현
            adjustments['consecutive'] = {
                'max_consecutive': int(consecutive_stats['avg_count'] + 1)
            }
        else:
            adjustments['consecutive'] = {
                'max_consecutive': max(1, int(consecutive_stats['avg_count']))
            }
        
        # 3. 홀짝 필터 조정
        odd_even_stats = patterns['odd_even']
        common_ratios = odd_even_stats['common_ratios']
        adjustments['odd_even'] = {
            'allowed_ratios': common_ratios + [
                (r[0]-1, r[1]+1) for r in common_ratios if r[0] > 0
            ] + [
                (r[0]+1, r[1]-1) for r in common_ratios if r[1] > 0
            ]
        }
        
        # 4. 구간 필터 조정
        section_stats = patterns['sections']
        adjustments['section'] = {
            'min_sections': sum(1 for count in section_stats['avg_distribution'] 
                               if count >= section_stats['balanced_threshold'])
        }
        
        # 5. 핫/콜드 넘버 기반 조정
        hot_numbers = patterns['hot_numbers']['numbers']
        cold_numbers = patterns['cold_numbers']['numbers']
        
        adjustments['hot_cold'] = {
            'hot_numbers': hot_numbers,
            'cold_numbers': cold_numbers,
            'min_hot_numbers': min(2, len(hot_numbers)),
            'max_cold_numbers': min(3, len(cold_numbers))
        }
        
        # 6. AC값 필터 조정
        ac_stats = patterns['ac_value']
        adjustments['ac_value'] = {
            'min_ac': int(ac_stats['common_range'][0]),
            'max_ac': int(ac_stats['common_range'][1])
        }
        
        # 7. 최대 간격 필터 조정
        max_gaps = []
        recent_numbers = self._get_recent_winning_numbers(50)
        for _, numbers in recent_numbers:
            gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
            max_gaps.append(max(gaps))
        
        adjustments['max_gap'] = {
            'max_gap': int(np.percentile(max_gaps, 90))
        }
        
        logging.info("\n📊 필터 조정 내역:")
        logging.info(f"총 {len(adjustments)}개 필터 기준값 조정:")
        
        for filter_name, criteria in adjustments.items():
            logging.info(f"\n  [{filter_name}]")
            for key, value in criteria.items():
                if isinstance(value, list):
                    logging.info(f"    - {key}: {value[:3]}{'...' if len(value) > 3 else ''}")
                else:
                    logging.info(f"    - {key}: {value}")
        
        return adjustments
    
    def _apply_adjusted_filters(self, adjustments: Dict[str, Any]):
        """조정된 필터 기준 적용"""
        # 설정 파일 존재 확인
        config_path = 'config.yaml'
        if not os.path.exists(config_path):
            logging.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
            return
        
        try:
            # 현재 설정 로드
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"설정 파일 로드 오류: {e}")
            return
        
        # 백업 생성
        backup_path = f"configs/config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with open(backup_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        # 필터 기준값 업데이트
        filters = config.get('filters', {})
        
        for filter_name, new_criteria in adjustments.items():
            if filter_name in filters:
                filters[filter_name].update(new_criteria)
            else:
                # 새로운 필터 추가
                filters[filter_name] = new_criteria
        
        # 동적 설정 파일 저장
        dynamic_config_path = 'configs/config_dynamic.yaml'
        try:
            os.makedirs(os.path.dirname(dynamic_config_path), exist_ok=True)
            with open(dynamic_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            logging.info(f"✅ 동적 필터 설정 저장: {dynamic_config_path}")
        except Exception as e:
            logging.error(f"동적 설정 파일 저장 오류: {e}")
            return
        
        # 필터 매니저 재초기화 (새 설정 적용)
        self.filter_manager = ParallelFilterManager(self.db_manager)
        
        # 필터 재적용
        latest_round = self.db_manager.lotto_db.get_last_round()
        self.filter_manager.apply_filters(latest_round, update_mode='incremental')
    
    def _run_performance_backtest(self) -> Dict[str, Any]:
        """성능 평가를 위한 백테스팅 실행"""
        try:
            # 백테스팅 횟수 증가
            self.backtesting_state['total_backtesting_count'] += 1
            current_round = self.db_manager.lotto_db.get_last_round()
            self.backtesting_state['last_backtest_round'] = current_round
            
            logging.info(f"\n🔄 백테스팅 #{self.backtesting_state['total_backtesting_count']} 실행 (회차: {current_round})")
            
            # 백테스팅 실행
            from ..backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
            backtest_framework = OptimizedBacktestingFramework(self.db_manager)
            
            # 최근 20회차에 대해 백테스팅
            start_round = max(1, current_round - 19)
            end_round = current_round
            
            results = backtest_framework.run_backtest(
                start_round=start_round,
                end_round=end_round,
                window_size=50
            )
            
            # 성능 점수 계산
            performance_score = self._calculate_overall_performance(results)
            self.backtesting_state['performance_scores'].append(performance_score)
            
            # 최근 10개 성능 점수만 유지
            if len(self.backtesting_state['performance_scores']) > 10:
                self.backtesting_state['performance_scores'] = self.backtesting_state['performance_scores'][-10:]
            
            logging.info(f"백테스팅 성능 점수: {performance_score:.3f}")
            
            # 백테스팅 상태를 즉시 저장
            self._save_state()
            
            return {
                'backtest_count': self.backtesting_state['total_backtesting_count'],
                'performance_score': performance_score,
                'results': results
            }
            
        except Exception as e:
            logging.error(f"백테스팅 실행 중 오류: {e}")
            
            # 오류가 발생해도 상태 저장
            self._save_state()
            
            return {
                'backtest_count': self.backtesting_state['total_backtesting_count'],
                'performance_score': 0.0,
                'error': str(e)
            }
    
    def _calculate_overall_performance(self, backtest_results: Dict[str, Any]) -> float:
        """전체 성능 점수 계산"""
        try:
            metrics = backtest_results.get('performance_metrics', {})
            model_performance = metrics.get('model_performance', {})
            
            if not model_performance:
                return 0.0
            
            # 각 모델의 평균 일치 개수 수집
            avg_matches = []
            for model_name, model_metrics in model_performance.items():
                avg_match = model_metrics.get('avg_matches', 0)
                avg_matches.append(avg_match)
            
            # 전체 평균 계산 (정규화: 0~1 범위)
            overall_avg = sum(avg_matches) / len(avg_matches) if avg_matches else 0
            normalized_score = min(1.0, overall_avg / 2.0)  # 2개 일치를 1.0 기준으로 정규화
            
            return normalized_score
            
        except Exception as e:
            logging.error(f"성능 점수 계산 중 오류: {e}")
            return 0.0
    
    def _get_ml_models(self) -> Dict[str, Any]:
        """ML 모델 인스턴스 반환"""
        # ml_models 속성이 설정되었는지 확인
        if hasattr(self, 'ml_models') and self.ml_models:
            return self.ml_models
        else:
            logging.warning("ML 모델이 설정되지 않았습니다.")
            return {
                'lstm': None,
                'ensemble': None,
                'monte_carlo': None
            }
    
    def _evaluate_adjustment_performance(self, adjustment_results: Dict[str, Any]):
        """조정 성능 평가"""
        if not adjustment_results.get('filters_adjusted'):
            return
        
        # 필터 조정 효과 측정
        latest_round = self.db_manager.lotto_db.get_last_round()
        
        # 조정 전후 필터링 결과 비교
        before_count = adjustment_results.get('before_filter_count', 0)
        after_count = len(self.db_manager.combinations_db.get_filtered_combinations())
        
        if before_count > 0:
            reduction_rate = (before_count - after_count) / before_count
            self.performance_metrics['filter_accuracy'].append({
                'round': latest_round,
                'reduction_rate': reduction_rate,
                'final_count': after_count
            })
            
            logging.info(f"\n📈 조정 효과:")
            logging.info(f"  - 조정 전: {before_count:,}개")
            logging.info(f"  - 조정 후: {after_count:,}개")
            logging.info(f"  - 감소율: {reduction_rate:.2%}")
    
    def _save_adjustment_history(self, results: Dict[str, Any]):
        """조정 이력 저장"""
        try:
            history_entry = {
                'timestamp': results['timestamp'].isoformat(),
                'round': self.db_manager.lotto_db.get_last_round(),
                'adjustments': results.get('filter_adjustments', {}),
                'performance': {
                    'filters_adjusted': results.get('filters_adjusted', False),
                    'models_updated': results.get('models_updated', False)
                }
            }
            
            self.adjustment_history.append(history_entry)
            
            # 파일로 저장
            history_path = 'results/adjustment_history.json'
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(self.adjustment_history, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logging.error(f"조정 이력 저장 오류: {e}")
    
    def _update_pattern_history(self, patterns: Dict[str, Any]):
        """패턴 이력 업데이트"""
        self.pattern_history['hot_numbers'].append(patterns['hot_numbers']['numbers'])
        self.pattern_history['cold_numbers'].append(patterns['cold_numbers']['numbers'])
        self.pattern_history['sum_trends'].append(patterns['sum_range'])
        self.pattern_history['consecutive_patterns'].append(patterns['consecutive'])
        self.pattern_history['odd_even_ratios'].append(patterns['odd_even'])
        self.pattern_history['section_distributions'].append(patterns['sections'])
    
    def _get_recent_winning_numbers(self, count: int) -> List[Tuple[int, List[int]]]:
        """최근 당첨번호 가져오기"""
        latest_round = self.db_manager.lotto_db.get_last_round()
        start_round = max(1, latest_round - count + 1)
        
        winning_numbers = []
        # 현재 회차는 제외 (데이터 누출 방지)
        for round_num in range(start_round, latest_round):
            result = self.db_manager.lotto_db.get_numbers_by_round(round_num)
            if result:
                round_no, numbers_str, date = result
                numbers = [int(n) for n in numbers_str.split(',')]
                winning_numbers.append((round_num, numbers))
        
        return winning_numbers
    
    def _calculate_ac_value(self, numbers: List[int]) -> int:
        """AC값 계산 (Arithmetic Complexity)"""
        ac_set = set()
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                ac_set.add(numbers[j] - numbers[i])
        return len(ac_set)
    
    def _get_common_values(self, values: List[int], top_n: int = 3) -> List[Tuple[int, int]]:
        """가장 흔한 값들 반환"""
        from collections import Counter
        counter = Counter(values)
        common = counter.most_common(top_n)
        
        # 홀짝 비율로 변환 (예: 3개 홀수 -> (3, 3))
        ratios = []
        for odd_count, _ in common:
            even_count = 6 - odd_count
            ratios.append((odd_count, even_count))
        
        return ratios
    
    def get_status_report(self) -> str:
        """시스템 상태 보고서"""
        report = []
        report.append("\n" + "="*60)
        report.append("[AUTO] 자동 조정 시스템 상태 보고서")
        report.append("="*60)
        
        # 기본 정보
        latest_round = self.db_manager.lotto_db.get_last_round()
        report.append(f"\n[INFO] 기본 정보:")
        report.append(f"  - 현재 회차: {latest_round}")
        report.append(f"  - 체크 주기: {self.config['check_interval']}초")
        report.append(f"  - 분석 윈도우: 최근 {self.config['analysis_window']}회차")
        
        # 백테스팅 상태
        report.append(f"\n[BACKTEST] 백테스팅 상태:")
        report.append(f"  - 총 백테스팅 횟수: {self.backtesting_state['total_backtesting_count']}회")
        report.append(f"  - 마지막 백테스팅 회차: {self.backtesting_state['last_backtest_round']}")
        
        if self.backtesting_state['performance_scores']:
            recent_scores = self.backtesting_state['performance_scores'][-3:]
            avg_score = sum(recent_scores) / len(recent_scores)
            report.append(f"  - 최근 평균 성능: {avg_score:.3f} (최근 {len(recent_scores)}회 평균)")
            report.append(f"  - 성능 기록: {[f'{s:.3f}' for s in recent_scores]}")
        else:
            report.append(f"  - 성능 기록: 없음")
        
        # 조정 이력
        if self.adjustment_history:
            last_adjustment = self.adjustment_history[-1]
            report.append(f"\n[ADJUST] 마지막 조정:")
            report.append(f"  - 시간: {last_adjustment['timestamp']}")
            report.append(f"  - 회차: {last_adjustment['round']}")
            report.append(f"  - 조정 항목: {len(last_adjustment['adjustments'])}개")
        
        # 패턴 추세
        if self.pattern_history['sum_trends']:
            recent_sum_trends = list(self.pattern_history['sum_trends'])[-10:]
            recent_sums = [p['mean'] for p in recent_sum_trends]
            report.append(f"\n[TREND] 최근 패턴 추세:")
            report.append(f"  - 평균 합계: {np.mean(recent_sums):.1f}")
            hot_numbers_list = list(self.pattern_history['hot_numbers'])
            if hot_numbers_list:
                report.append(f"  - 핫넘버 수: {len(hot_numbers_list[-1])}개")
            else:
                report.append(f"  - 핫넘버 수: 0개")
        
        # 성능 메트릭
        if self.performance_metrics['filter_accuracy']:
            accuracy_list = list(self.performance_metrics['filter_accuracy'])
            recent_accuracy = accuracy_list[-5:] if len(accuracy_list) >= 5 else accuracy_list
            if recent_accuracy:
                avg_reduction = np.mean([m['reduction_rate'] for m in recent_accuracy])
                report.append(f"\n[PERF] 성능 지표:")
                report.append(f"  - 평균 필터 감소율: {avg_reduction:.2%}")
        
        report.append("\n" + "="*60)
        
        return "\n".join(report)


# 사용 예시
if __name__ == "__main__":
    # 자동 조정 시스템 초기화
    auto_system = AutoAdjustmentSystem()
    
    # 즉시 체크 및 조정
    results = auto_system.check_and_adjust()
    
    # 상태 보고서 출력
    print(auto_system.get_status_report())
    
    # 자동 모니터링 시작 (백그라운드)
    # monitor_thread = auto_system.start_monitoring()