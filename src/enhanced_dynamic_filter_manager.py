#!/usr/bin/env python3
"""
향상된 동적 필터 관리 시스템
실시간 모니터링, 자동 조정, 적응형 가중치 시스템을 포함
"""
import json
import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from collections import defaultdict, deque
from datetime import datetime
import threading

try:
    from .dynamic_filter_manager import DynamicFilterManager
except ImportError:
    from dynamic_filter_manager import DynamicFilterManager

try:
    # [adaptive-threshold-1] 실제 구현은 src/scripts/dynamic_filter_system.py 에 있다.
    # 과거 경로 'analyze_system.dynamic_filter_system'는 존재하지 않아 항상 ImportError ->
    # 폴백 스텁(adjust_criteria/update_performance 결측)이 동작해 auto_adjust_all_filters가
    # AttributeError로 깨졌다. 올바른 경로로 교정한다.
    from src.scripts.dynamic_filter_system import FilterPerformanceMonitor, BalancedStrategy
except ImportError:
    try:
        from scripts.dynamic_filter_system import FilterPerformanceMonitor, BalancedStrategy
    except ImportError:
        # 최후 폴백 스텁 (실제 모듈 import가 모두 실패한 경우에만 사용)
        # 주의: 실제 클래스와 동일한 인터페이스(update_performance/adjust_criteria)를 제공해야
        #       auto_adjust_all_filters에서 AttributeError가 발생하지 않는다.
        class FilterPerformanceMonitor:
            def __init__(self, window_size: int = 50):
                self.metrics = {}
                self.window_size = window_size

            def update_metric(self, filter_name: str, metric: str, value: float):
                if filter_name not in self.metrics:
                    self.metrics[filter_name] = {}
                self.metrics[filter_name][metric] = value

            def update_performance(self, filter_name: str, pass_rate: float,
                                   exclusion_rate: float, false_negative: bool):
                """실제 FilterPerformanceMonitor와 동일한 인터페이스 (스텁)"""
                self.metrics.setdefault(filter_name, {}).update({
                    'avg_pass_rate': pass_rate,
                    'avg_exclusion_rate': exclusion_rate,
                    'false_negative_rate': 1.0 if false_negative else 0.0,
                })

            def get_performance_summary(self) -> Dict:
                return self.metrics

            def get_performance_metrics(self, filter_name: str) -> Dict[str, float]:
                """필터 성능 메트릭 반환"""
                # 해당 필터의 메트릭이 없으면 기본값 반환
                if filter_name not in self.metrics:
                    return {
                        'avg_pass_rate': 1.0,
                        'avg_exclusion_rate': 0.0,
                        'false_negative_rate': 0.0,
                        'stability': 1.0
                    }

                # 저장된 메트릭 반환 (기본값으로 채움)
                metrics = self.metrics[filter_name]
                return {
                    'avg_pass_rate': metrics.get('avg_pass_rate', 1.0),
                    'avg_exclusion_rate': metrics.get('avg_exclusion_rate', 0.0),
                    'false_negative_rate': metrics.get('false_negative_rate', 0.0),
                    'stability': metrics.get('stability', 1.0)
                }

        class BalancedStrategy:
            def __init__(self):
                pass

            def adjust_criteria(self, current_criteria: Dict, performance_metrics: Dict) -> Dict:
                """실제 BalancedStrategy와 동일한 인터페이스 (스텁: 조정 없이 그대로 반환)"""
                return dict(current_criteria) if current_criteria else current_criteria

            def calculate_weights(self, performances: Dict) -> Dict[str, float]:
                # 간단한 균등 가중치 반환
                if not performances:
                    return {}
                return {k: 1.0 / len(performances) for k in performances}

class AdaptiveWeightManager:
    """적응형 가중치 관리자"""
    
    def __init__(self):
        self.weights = {}
        self.performance_history = defaultdict(list)
        self.adjustment_history = []
        
    def calculate_dynamic_weights(self, filter_performances: Dict[str, Dict]) -> Dict[str, float]:
        """필터 성능 기반 동적 가중치 계산
        
        Args:
            filter_performances: 필터별 성능 메트릭
            
        Returns:
            Dict[str, float]: 필터별 가중치
        """
        weights = {}
        
        # 성능 점수 계산 (다중 메트릭 고려)
        scores = {}
        for filter_name, perf in filter_performances.items():
            # 종합 점수: 통과율, 제외율, 안정성 고려
            score = (
                perf.get('avg_pass_rate', 1.0) * 0.4 +  # 당첨번호 통과율
                min(perf.get('avg_exclusion_rate', 0.0), 0.1) * 10 * 0.3 +  # 적절한 제외율
                perf.get('stability', 1.0) * 0.3  # 안정성
            )
            scores[filter_name] = score
            
        # 점수 정규화하여 가중치 계산
        total_score = sum(scores.values())
        if total_score > 0:
            for filter_name, score in scores.items():
                weights[filter_name] = score / total_score
        else:
            # 모든 필터에 동일 가중치
            num_filters = len(filter_performances)
            for filter_name in filter_performances:
                weights[filter_name] = 1.0 / num_filters if num_filters > 0 else 0.0
                
        # 가중치 히스토리 저장
        self.adjustment_history.append({
            'timestamp': datetime.now(),
            'weights': weights.copy()
        })
        
        return weights
    
    def get_optimized_weights(self, current_weights: Dict[str, float], 
                            target_performance: Dict[str, float]) -> Dict[str, float]:
        """목표 성능 달성을 위한 최적화된 가중치 계산
        
        베이지안 최적화 원리를 단순화하여 적용
        """
        optimized = current_weights.copy()
        
        for filter_name, current_weight in current_weights.items():
            if filter_name in target_performance:
                # 목표와 현재 성능의 차이
                performance_gap = target_performance[filter_name] - current_weight
                
                # 가중치 조정 (학습률 0.1 적용)
                adjustment = performance_gap * 0.1
                optimized[filter_name] = max(0.05, min(0.95, current_weight + adjustment))
        
        # 정규화
        total = sum(optimized.values())
        if total > 0:
            for key in optimized:
                optimized[key] = optimized[key] / total
                
        return optimized

class EnhancedDynamicFilterManager(DynamicFilterManager):
    """향상된 동적 필터 관리자"""
    
    def __init__(self, db_manager, strategy=None, auto_adjust_interval=1):
        """
        Args:
            db_manager: 데이터베이스 관리자
            strategy: 적응형 전략 (기본값: BalancedStrategy)
            auto_adjust_interval: 자동 조정 간격 (회차 단위)
        """
        super().__init__(db_manager)
        
        self.strategy = strategy or BalancedStrategy()
        self.auto_adjust_interval = auto_adjust_interval
        self.performance_threshold = 0.7
        
        # 성능 모니터링
        self.monitor = FilterPerformanceMonitor(window_size=50)
        self.weight_manager = AdaptiveWeightManager()
        
        # 실시간 모니터링을 위한 변수
        self.last_adjustment_round = 0
        self.monitoring_enabled = False
        self.monitoring_thread = None
        
        # 필터별 실시간 통계
        self.real_time_stats = defaultdict(lambda: {
            'total_processed': 0,
            'total_excluded': 0,
            'false_negatives': 0,
            'processing_time': deque(maxlen=10)
        })
        
        logging.info("\n[동적 필터 시스템] 향상된 동적 필터 관리자 초기화")
        logging.info(f"  - 자동 조정 간격: {self.auto_adjust_interval}회차마다")
        logging.info(f"  - 성능 임계값: {self.performance_threshold:.1%}")
        logging.info(f"  - 모니터링 윈도우: 최근 50회차")
        logging.info("  - 실시간 가중치 조정 활성화")
    
    def start_monitoring(self):
        """실시간 모니터링 시작"""
        self.monitoring_enabled = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        logging.info("실시간 모니터링 시작됨")
    
    def stop_monitoring(self):
        """실시간 모니터링 중지"""
        self.monitoring_enabled = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logging.info("실시간 모니터링 중지됨")
    
    def _monitoring_loop(self):
        """백그라운드 모니터링 루프"""
        while self.monitoring_enabled:
            try:
                # 10초마다 성능 체크
                time.sleep(10)
                self._check_performance_and_adjust()
            except Exception as e:
                logging.error(f"모니터링 루프 오류: {str(e)}")
    
    def update_performance_metrics(self, filter_name: str, round_num: int, 
                                 metrics: Dict[str, Any]):
        """필터 성능 메트릭 업데이트
        
        Args:
            filter_name: 필터 이름
            round_num: 회차 번호
            metrics: 성능 메트릭 (pass_rate, exclusion_rate, processing_time 등)
        """
        # 실시간 통계 업데이트
        stats = self.real_time_stats[filter_name]
        stats['total_processed'] += metrics.get('total', 0)
        stats['total_excluded'] += metrics.get('excluded', 0)
        stats['false_negatives'] += metrics.get('false_negatives', 0)
        
        if 'processing_time' in metrics:
            stats['processing_time'].append(metrics['processing_time'])
        
        # 성능 모니터 업데이트
        pass_rate = metrics.get('pass_rate', 1.0)
        exclusion_rate = metrics.get('exclusion_rate', 0.0)
        false_negative = metrics.get('false_negative', False)
        
        self.monitor.update_performance(filter_name, pass_rate, 
                                       exclusion_rate, false_negative)
        
        # 자동 조정 체크
        if round_num - self.last_adjustment_round >= self.auto_adjust_interval:
            self._check_performance_and_adjust()
            self.last_adjustment_round = round_num
    
    def _check_performance_and_adjust(self):
        """성능 체크 및 자동 조정"""
        try:
            # 모든 필터의 성능 메트릭 수집
            all_metrics = {}
            for filter_name in self.filter_groups['essential'] + \
                           self.filter_groups['optional_a'] + \
                           self.filter_groups['optional_b']:
                metrics = self.monitor.get_performance_metrics(filter_name)
                all_metrics[filter_name] = metrics
            
            # 조정이 필요한지 확인
            if self._should_adjust(all_metrics):
                self.auto_adjust_all_filters(all_metrics)
                
        except Exception as e:
            logging.error(f"성능 체크 및 조정 중 오류: {str(e)}")
    
    def _should_adjust(self, metrics: Dict[str, Dict]) -> bool:
        """조정이 필요한지 판단
        
        Args:
            metrics: 필터별 성능 메트릭
            
        Returns:
            bool: 조정 필요 여부
        """
        # 전체 평균 통과율이 임계값보다 낮으면 조정 필요
        avg_pass_rates = [m['avg_pass_rate'] for m in metrics.values()]
        if avg_pass_rates:
            overall_pass_rate = np.mean(avg_pass_rates)
            if overall_pass_rate < self.performance_threshold:
                return True
        
        # 특정 필터의 false negative rate가 높으면 조정 필요
        for filter_metrics in metrics.values():
            if filter_metrics['false_negative_rate'] > 0.1:  # 10% 이상
                return True
        
        return False
    
    def auto_adjust_all_filters(self, metrics: Dict[str, Dict] = None):
        """모든 필터 자동 조정
        
        Args:
            metrics: 필터별 성능 메트릭 (None이면 자동 수집)
        """
        if metrics is None:
            metrics = {}
            for filter_name in self.filter_groups['essential'] + \
                           self.filter_groups['optional_a'] + \
                           self.filter_groups['optional_b']:
                metrics[filter_name] = self.monitor.get_performance_metrics(filter_name)
        
        # 동적 가중치 계산
        new_weights = self.weight_manager.calculate_dynamic_weights(metrics)
        
        # 각 필터의 기준값 조정
        for filter_name, filter_metrics in metrics.items():
            current_criteria = self.get_dynamic_criteria(filter_name)
            if current_criteria:
                # 전략에 따른 기준값 조정
                adjusted_criteria = self.strategy.adjust_criteria(
                    current_criteria, filter_metrics
                )
                
                # 조정된 기준값 저장
                self._save_adjusted_criteria(filter_name, adjusted_criteria)
        
        # 필터 효율성 업데이트
        self.filter_effectiveness.update(new_weights)
        
        logging.info(f"\n[동적 필터 조정] 자동 조정 완료")
        logging.info(f"  - 조정된 필터 수: {len(metrics)}개")
        logging.info(f"  - 조정된 필터 목록:")
        for filter_name, weight in sorted(new_weights.items(), key=lambda x: x[1], reverse=True)[:10]:
            logging.info(f"    • {filter_name}: 가중치 {weight:.3f}")
        logging.info(f"  - 평균 통과율: {np.mean([m['avg_pass_rate'] for m in metrics.values()]):.2%}")
        logging.info(f"  - 평균 제외율: {np.mean([m.get('avg_exclusion_rate', 0) for m in metrics.values()]):.2%}")
    
    def _save_adjusted_criteria(self, filter_name: str, criteria: Dict[str, Any]):
        """조정된 기준값 저장
        
        Args:
            filter_name: 필터 이름
            criteria: 조정된 기준값
        """
        try:
            # FilterDB를 통해 저장 (현재 회차로)
            from ..core.filter_db import FilterDB
            filter_db = FilterDB(
                f"data/filters/{filter_name}.db",
                filter_name
            )
            filter_db.set_criteria(criteria)
            
        except Exception as e:
            logging.error(f"{filter_name} 필터 기준값 저장 오류: {str(e)}")
    
    def get_real_time_dashboard(self) -> Dict[str, Any]:
        """실시간 대시보드 데이터 반환"""
        dashboard = {
            'timestamp': datetime.now().isoformat(),
            'filters': {},
            'overall_metrics': {
                'total_processed': 0,
                'total_excluded': 0,
                'average_exclusion_rate': 0.0,
                'average_processing_time': 0.0
            }
        }
        
        total_processed = 0
        total_excluded = 0
        processing_times = []
        
        for filter_name, stats in self.real_time_stats.items():
            # 필터별 통계
            exclusion_rate = (stats['total_excluded'] / stats['total_processed'] * 100) \
                           if stats['total_processed'] > 0 else 0.0
            
            avg_time = np.mean(list(stats['processing_time'])) \
                      if stats['processing_time'] else 0.0
            
            dashboard['filters'][filter_name] = {
                'total_processed': stats['total_processed'],
                'total_excluded': stats['total_excluded'],
                'exclusion_rate': exclusion_rate,
                'false_negatives': stats['false_negatives'],
                'avg_processing_time': avg_time,
                'performance_metrics': self.monitor.get_performance_metrics(filter_name)
            }
            
            total_processed += stats['total_processed']
            total_excluded += stats['total_excluded']
            if stats['processing_time']:
                processing_times.extend(list(stats['processing_time']))
        
        # 전체 메트릭
        dashboard['overall_metrics']['total_processed'] = total_processed
        dashboard['overall_metrics']['total_excluded'] = total_excluded
        dashboard['overall_metrics']['average_exclusion_rate'] = \
            (total_excluded / total_processed * 100) if total_processed > 0 else 0.0
        dashboard['overall_metrics']['average_processing_time'] = \
            np.mean(processing_times) if processing_times else 0.0
        
        return dashboard
    
    def export_performance_report(self, output_path: str = 'filter_performance_report.json'):
        """성능 보고서 내보내기 (실제 필터링 데이터 사용)"""
        try:
            # 실제 필터 매니저의 성능 추적기에서 데이터 가져오기
            real_time_stats = None
            if hasattr(self, 'db_manager'):
                try:
                    from .core.filter_manager import FilterManager
                    filter_manager = FilterManager(self.db_manager)
                    if hasattr(filter_manager, 'performance_tracker') and filter_manager.performance_tracker:
                        real_time_stats = filter_manager.performance_tracker.get_real_time_stats()
                except Exception as e:
                    logging.warning(f"실제 성능 데이터 로드 실패: {e}")
            
            # 기본 보고서 구조
            report = {
                'generated_at': datetime.now().isoformat(),
                'monitoring_period': {
                    'start': self.weight_manager.adjustment_history[0]['timestamp'].isoformat() 
                            if self.weight_manager.adjustment_history else None,
                    'end': datetime.now().isoformat()
                },
                'filter_performances': {},
                'weight_evolution': self.weight_manager.adjustment_history,
                'real_time_dashboard': self.get_real_time_dashboard(),
                'actual_filtering_data': real_time_stats  # 실제 필터링 데이터 추가
            }
            
            # 실제 데이터가 있으면 우선 사용
            if real_time_stats and 'filter_summary' in real_time_stats:
                for filter_name, stats in real_time_stats['filter_summary'].items():
                    report['filter_performances'][filter_name] = {
                        'current_metrics': {
                            'avg_pass_rate': stats['avg_pass_rate'] / 100.0,  # 0-1 범위로 정규화
                            'avg_exclusion_rate': stats['avg_exclusion_rate'] / 100.0,
                            'total_processed': stats['total_processed'],
                            'total_excluded': stats['total_excluded'],
                            'false_negative_rate': 0.0,  # 추후 계산 로직 추가
                            'stability': min(1.0, len(stats.get('recent_performance', {}).get('processing_times', [])) / 10.0)
                        },
                        'current_criteria': self.get_dynamic_criteria(filter_name),
                        'effectiveness_score': stats['avg_exclusion_rate'] / 100.0,
                        'performance_details': {
                            'avg_processing_time': stats['avg_processing_time'],
                            'last_round': stats['last_round'],
                            'recent_trends': stats.get('recent_performance', {})
                        }
                    }
            else:
                # 실제 데이터가 없으면 기존 방식 사용 (하지만 개선된 메트릭)
                for filter_name in self.filter_groups.get('essential', []) + \
                                 self.filter_groups.get('optional_a', []) + \
                                 self.filter_groups.get('optional_b', []):
                    # 실시간 통계에서 실제 데이터 찾기
                    real_stats = self.real_time_stats.get(filter_name, {})
                    total_processed = real_stats.get('total_processed', 0)
                    total_excluded = real_stats.get('total_excluded', 0)
                    
                    if total_processed > 0:
                        actual_exclusion_rate = total_excluded / total_processed
                        actual_pass_rate = 1.0 - actual_exclusion_rate
                    else:
                        actual_exclusion_rate = 0.0
                        actual_pass_rate = 1.0
                    
                    report['filter_performances'][filter_name] = {
                        'current_metrics': {
                            'avg_pass_rate': actual_pass_rate,
                            'avg_exclusion_rate': actual_exclusion_rate,
                            'total_processed': total_processed,
                            'total_excluded': total_excluded,
                            'false_negative_rate': 0.0,
                            'stability': 1.0 if len(real_stats.get('processing_time', [])) > 5 else 0.5
                        },
                        'current_criteria': self.get_dynamic_criteria(filter_name),
                        'effectiveness_score': actual_exclusion_rate
                    }
            
            # 파일로 저장
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            # 결과 디렉토리에도 저장
            results_output = output_path.replace('.json', '_enhanced.json')
            with open(f'results/{results_output}', 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"[개선된 성능 보고서] 저장 완료: {output_path}")
            logging.info(f"실제 필터링 데이터 포함: {'예' if real_time_stats else '아니오'}")
            
            return report
            
        except Exception as e:
            logging.error(f"성능 보고서 생성 실패: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return {}


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append('.')
    from src.core.db_manager import DatabaseManager
    
    # DB 매니저 초기화
    db_manager = DatabaseManager()
    
    # 향상된 동적 필터 관리자 생성
    enhanced_manager = EnhancedDynamicFilterManager(
        db_manager,
        auto_adjust_interval=1  # 매 회차마다 자동 조정
    )
    
    # 실시간 모니터링 시작
    enhanced_manager.start_monitoring()
    
    # 통계 출력
    enhanced_manager.print_statistics()
    
    # 시뮬레이션: 성능 메트릭 업데이트
    print("\n=== 성능 시뮬레이션 ===")
    for round_num in range(1, 11):
        for filter_name in ['odd_even', 'sum_range', 'dispersion']:
            # 가상의 성능 메트릭
            metrics = {
                'total': 1000,
                'excluded': np.random.randint(50, 150),
                'pass_rate': np.random.uniform(0.95, 0.99),
                'exclusion_rate': np.random.uniform(0.05, 0.15),
                'processing_time': np.random.uniform(0.1, 0.5),
                'false_negative': np.random.random() < 0.05
            }
            
            enhanced_manager.update_performance_metrics(filter_name, round_num, metrics)
        
        time.sleep(0.1)  # 시뮬레이션 지연
    
    # 대시보드 출력
    print("\n=== 실시간 대시보드 ===")
    dashboard = enhanced_manager.get_real_time_dashboard()
    print(f"전체 처리: {dashboard['overall_metrics']['total_processed']:,}개")
    print(f"전체 제외: {dashboard['overall_metrics']['total_excluded']:,}개")
    print(f"평균 제외율: {dashboard['overall_metrics']['average_exclusion_rate']:.2f}%")
    
    # 성능 보고서 내보내기
    enhanced_manager.export_performance_report()
    print("\n[O] 성능 보고서가 filter_performance_report.json에 저장되었습니다.")
    
    # 모니터링 중지
    enhanced_manager.stop_monitoring()

if __name__ == "__main__":
    main()