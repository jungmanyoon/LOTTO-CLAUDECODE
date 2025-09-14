#!/usr/bin/env python3
"""
실시간 필터 성능 추적 시스템
필터링 과정 중 실제 데이터를 수집하고 분석하는 모듈
"""

import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict, deque
import threading
from pathlib import Path

class FilterPerformanceTracker:
    """실시간 필터 성능 추적기"""
    
    def __init__(self, db_manager, max_history: int = 100):
        """
        Args:
            db_manager: 데이터베이스 관리자
            max_history: 저장할 최대 히스토리 수
        """
        self.db_manager = db_manager
        self.max_history = max_history
        
        # 실시간 통계
        self.current_session = {
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'start_time': datetime.now(),
            'total_input_combinations': 0,
            'total_output_combinations': 0,
            'filters': {}
        }
        
        # 필터별 실시간 데이터
        self.filter_stats = defaultdict(lambda: {
            'total_processed': 0,
            'total_excluded': 0,
            'processing_times': deque(maxlen=10),
            'exclusion_rates': deque(maxlen=10),
            'pass_rates': deque(maxlen=10),
            'last_round': None,
            'criteria_history': deque(maxlen=5)
        })
        
        # 히스토리 데이터
        self.session_history = deque(maxlen=max_history)
        
        # 스레드 안전성을 위한 락
        self._lock = threading.Lock()
        
        logging.info("[필터 성능 추적기] 초기화 완료")
    
    def start_filtering_session(self, round_num: int, initial_combinations: int):
        """필터링 세션 시작"""
        with self._lock:
            self.current_session = {
                'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
                'start_time': datetime.now(),
                'round_num': round_num,
                'total_input_combinations': initial_combinations,
                'total_output_combinations': 0,
                'filters': {},
                'completed': False
            }
            
            logging.info(f"[성능 추적] 필터링 세션 시작 - 회차: {round_num}, 입력: {initial_combinations:,}개")
    
    def track_filter_application(self, filter_name: str, before_count: int, after_count: int, 
                               processing_time: float, criteria: Dict[str, Any], round_num: int):
        """필터 적용 결과 추적"""
        with self._lock:
            excluded_count = before_count - after_count
            exclusion_rate = (excluded_count / before_count) if before_count > 0 else 0.0
            pass_rate = (after_count / before_count) if before_count > 0 else 0.0
            
            # 필터별 통계 업데이트
            stats = self.filter_stats[filter_name]
            stats['total_processed'] += before_count
            stats['total_excluded'] += excluded_count
            stats['processing_times'].append(processing_time)
            stats['exclusion_rates'].append(exclusion_rate)
            stats['pass_rates'].append(pass_rate)
            stats['last_round'] = round_num
            stats['criteria_history'].append({
                'round': round_num,
                'criteria': criteria.copy(),
                'timestamp': datetime.now()
            })
            
            # 현재 세션에 필터 결과 추가
            self.current_session['filters'][filter_name] = {
                'before_count': before_count,
                'after_count': after_count,
                'excluded_count': excluded_count,
                'exclusion_rate': exclusion_rate * 100,
                'pass_rate': pass_rate * 100,
                'processing_time': processing_time,
                'criteria': criteria.copy(),
                'timestamp': datetime.now().isoformat()
            }
            
            # 로깅
            logging.info(f"[성능 추적] {filter_name}: {before_count:,} → {after_count:,} "
                        f"({exclusion_rate*100:.2f}% 제외, {processing_time:.3f}초)")
    
    def complete_filtering_session(self, final_combinations: int):
        """필터링 세션 완료"""
        with self._lock:
            self.current_session['total_output_combinations'] = final_combinations
            self.current_session['end_time'] = datetime.now()
            self.current_session['completed'] = True
            
            # 전체 감소율 계산
            initial = self.current_session['total_input_combinations']
            overall_reduction = ((initial - final_combinations) / initial * 100) if initial > 0 else 0
            self.current_session['overall_reduction_rate'] = overall_reduction
            
            # 세션을 히스토리에 추가
            self.session_history.append(self.current_session.copy())
            
            # 성능 보고서 생성
            self._generate_performance_report()
            
            logging.info(f"[성능 추적] 필터링 세션 완료 - 출력: {final_combinations:,}개 "
                        f"(전체 감소: {overall_reduction:.2f}%)")
    
    def get_real_time_stats(self) -> Dict[str, Any]:
        """실시간 통계 반환"""
        with self._lock:
            real_time_data = {
                'current_session': self.current_session.copy(),
                'filter_summary': {},
                'overall_stats': self._calculate_overall_stats()
            }
            
            # 필터별 요약 통계
            for filter_name, stats in self.filter_stats.items():
                avg_exclusion_rate = sum(stats['exclusion_rates']) / len(stats['exclusion_rates']) \
                                   if stats['exclusion_rates'] else 0.0
                avg_pass_rate = sum(stats['pass_rates']) / len(stats['pass_rates']) \
                               if stats['pass_rates'] else 0.0
                avg_processing_time = sum(stats['processing_times']) / len(stats['processing_times']) \
                                     if stats['processing_times'] else 0.0
                
                real_time_data['filter_summary'][filter_name] = {
                    'total_processed': stats['total_processed'],
                    'total_excluded': stats['total_excluded'],
                    'avg_exclusion_rate': avg_exclusion_rate * 100,
                    'avg_pass_rate': avg_pass_rate * 100,
                    'avg_processing_time': avg_processing_time,
                    'last_round': stats['last_round'],
                    'recent_performance': {
                        'exclusion_rates': list(stats['exclusion_rates']),
                        'pass_rates': list(stats['pass_rates']),
                        'processing_times': list(stats['processing_times'])
                    }
                }
            
            return real_time_data
    
    def _calculate_overall_stats(self) -> Dict[str, Any]:
        """전체 통계 계산"""
        if not self.session_history:
            return {}
        
        recent_sessions = list(self.session_history)[-10:]  # 최근 10개 세션
        
        total_input = sum(s.get('total_input_combinations', 0) for s in recent_sessions)
        total_output = sum(s.get('total_output_combinations', 0) for s in recent_sessions)
        avg_reduction = sum(s.get('overall_reduction_rate', 0) for s in recent_sessions) / len(recent_sessions)
        
        return {
            'recent_sessions_count': len(recent_sessions),
            'total_input_combinations': total_input,
            'total_output_combinations': total_output,
            'average_reduction_rate': avg_reduction,
            'sessions_timeline': [
                {
                    'session_id': s['session_id'],
                    'round_num': s.get('round_num'),
                    'reduction_rate': s.get('overall_reduction_rate', 0),
                    'filter_count': len(s.get('filters', {})),
                    'start_time': s['start_time'].isoformat() if isinstance(s['start_time'], datetime) else s['start_time']
                }
                for s in recent_sessions
            ]
        }
    
    def _generate_performance_report(self):
        """성능 보고서 생성 및 저장"""
        try:
            report = {
                'generated_at': datetime.now().isoformat(),
                'session_info': self.current_session.copy(),
                'filter_performances': {},
                'overall_statistics': self._calculate_overall_stats(),
                'recommendations': self._generate_recommendations()
            }
            
            # datetime 객체를 문자열로 변환
            if isinstance(report['session_info']['start_time'], datetime):
                report['session_info']['start_time'] = report['session_info']['start_time'].isoformat()
            if 'end_time' in report['session_info'] and isinstance(report['session_info']['end_time'], datetime):
                report['session_info']['end_time'] = report['session_info']['end_time'].isoformat()
            
            # 필터별 상세 성능 데이터
            for filter_name, stats in self.filter_stats.items():
                if stats['total_processed'] > 0:
                    avg_exclusion_rate = sum(stats['exclusion_rates']) / len(stats['exclusion_rates']) \
                                       if stats['exclusion_rates'] else 0.0
                    avg_pass_rate = sum(stats['pass_rates']) / len(stats['pass_rates']) \
                                   if stats['pass_rates'] else 0.0
                    
                    report['filter_performances'][filter_name] = {
                        'current_metrics': {
                            'avg_pass_rate': avg_pass_rate,
                            'avg_exclusion_rate': avg_exclusion_rate,
                            'total_processed': stats['total_processed'],
                            'total_excluded': stats['total_excluded'],
                            'false_negative_rate': 0.0,  # 실제 계산 로직 필요
                            'stability': min(1.0, len(stats['processing_times']) / 10.0)
                        },
                        'current_criteria': stats['criteria_history'][-1]['criteria'] if stats['criteria_history'] else {},
                        'effectiveness_score': avg_exclusion_rate,
                        'performance_trend': {
                            'exclusion_rates': list(stats['exclusion_rates']),
                            'processing_times': list(stats['processing_times'])
                        }
                    }
            
            # 보고서 저장
            report_path = Path('filter_performance_report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            # 결과 디렉토리에도 저장
            results_dir = Path('results')
            results_dir.mkdir(exist_ok=True)
            results_report_path = results_dir / 'filter_performance_report.json'
            with open(results_report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"[성능 보고서] 저장 완료: {report_path}")
            
        except Exception as e:
            logging.error(f"성능 보고서 생성 실패: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def _generate_recommendations(self) -> List[str]:
        """성능 개선 권장사항 생성"""
        recommendations = []
        
        # 필터별 성능 분석
        for filter_name, stats in self.filter_stats.items():
            if not stats['exclusion_rates']:
                continue
            
            avg_exclusion = sum(stats['exclusion_rates']) / len(stats['exclusion_rates'])
            avg_time = sum(stats['processing_times']) / len(stats['processing_times']) \
                      if stats['processing_times'] else 0
            
            # 비효율적인 필터 감지
            if avg_exclusion < 0.01:  # 1% 미만 제외
                recommendations.append(f"{filter_name}: 제외율이 매우 낮음 ({avg_exclusion*100:.2f}%) - 기준 조정 검토")
            
            # 느린 필터 감지
            if avg_time > 1.0:  # 1초 이상
                recommendations.append(f"{filter_name}: 처리 시간이 느림 ({avg_time:.2f}초) - 최적화 검토")
            
            # 불안정한 필터 감지
            if len(stats['exclusion_rates']) > 3:
                variance = sum((r - avg_exclusion) ** 2 for r in stats['exclusion_rates']) / len(stats['exclusion_rates'])
                if variance > 0.1:  # 분산이 큰 경우
                    recommendations.append(f"{filter_name}: 성능이 불안정함 (분산: {variance:.3f}) - 기준 안정화 필요")
        
        return recommendations
    
    def get_filter_efficiency_scores(self) -> Dict[str, float]:
        """필터 효율성 점수 반환 (필터 매니저와 호환)"""
        efficiency_scores = {}
        
        for filter_name, stats in self.filter_stats.items():
            if stats['exclusion_rates']:
                avg_exclusion = sum(stats['exclusion_rates']) / len(stats['exclusion_rates'])
                avg_time = sum(stats['processing_times']) / len(stats['processing_times']) \
                          if stats['processing_times'] else 1.0
                
                # 효율성 = 제외율 / 처리시간 (정규화)
                efficiency = avg_exclusion / max(avg_time, 0.001)  # 0으로 나누기 방지
                efficiency_scores[filter_name] = min(efficiency, 1.0)  # 최대 1.0으로 제한
            else:
                efficiency_scores[filter_name] = 0.0
        
        return efficiency_scores
    
    def export_detailed_analysis(self, output_path: str = 'detailed_filter_analysis.json'):
        """상세 분석 데이터 내보내기"""
        try:
            analysis = {
                'export_time': datetime.now().isoformat(),
                'session_summary': {
                    'total_sessions': len(self.session_history),
                    'current_session': self.current_session.copy()
                },
                'filter_detailed_stats': {},
                'trend_analysis': self._analyze_trends(),
                'performance_insights': self._generate_insights()
            }
            
            # datetime 변환
            if isinstance(analysis['session_summary']['current_session']['start_time'], datetime):
                analysis['session_summary']['current_session']['start_time'] = \
                    analysis['session_summary']['current_session']['start_time'].isoformat()
            
            # 필터별 상세 통계
            for filter_name, stats in self.filter_stats.items():
                analysis['filter_detailed_stats'][filter_name] = {
                    'total_processed': stats['total_processed'],
                    'total_excluded': stats['total_excluded'],
                    'historical_data': {
                        'exclusion_rates': list(stats['exclusion_rates']),
                        'pass_rates': list(stats['pass_rates']),
                        'processing_times': list(stats['processing_times'])
                    },
                    'criteria_evolution': [
                        {
                            'round': c['round'],
                            'criteria': c['criteria'],
                            'timestamp': c['timestamp'].isoformat() if isinstance(c['timestamp'], datetime) else c['timestamp']
                        }
                        for c in stats['criteria_history']
                    ]
                }
            
            # 파일 저장
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"[상세 분석] 저장 완료: {output_path}")
            return analysis
            
        except Exception as e:
            logging.error(f"상세 분석 내보내기 실패: {e}")
            return {}
    
    def _analyze_trends(self) -> Dict[str, Any]:
        """성능 트렌드 분석"""
        trends = {}
        
        for filter_name, stats in self.filter_stats.items():
            if len(stats['exclusion_rates']) < 3:
                continue
            
            rates = list(stats['exclusion_rates'])
            times = list(stats['processing_times'])
            
            # 트렌드 계산 (단순 선형 회귀)
            n = len(rates)
            x_avg = (n - 1) / 2
            y_avg = sum(rates) / n
            
            numerator = sum((i - x_avg) * (rates[i] - y_avg) for i in range(n))
            denominator = sum((i - x_avg) ** 2 for i in range(n))
            
            if denominator != 0:
                slope = numerator / denominator
                trend_direction = "증가" if slope > 0.01 else "감소" if slope < -0.01 else "안정"
            else:
                trend_direction = "안정"
            
            trends[filter_name] = {
                'exclusion_rate_trend': trend_direction,
                'slope': slope if 'slope' in locals() else 0.0,
                'stability': 1.0 - (max(rates) - min(rates)) if rates else 1.0
            }
        
        return trends
    
    def _generate_insights(self) -> List[str]:
        """성능 인사이트 생성"""
        insights = []
        
        # 전체 성능 분석
        total_processed = sum(stats['total_processed'] for stats in self.filter_stats.values())
        total_excluded = sum(stats['total_excluded'] for stats in self.filter_stats.values())
        
        if total_processed > 0:
            overall_exclusion = (total_excluded / total_processed) * 100
            insights.append(f"전체 제외율: {overall_exclusion:.2f}%")
        
        # 가장 효율적인 필터
        best_filter = None
        best_exclusion = 0
        
        for filter_name, stats in self.filter_stats.items():
            if stats['exclusion_rates']:
                avg_exclusion = sum(stats['exclusion_rates']) / len(stats['exclusion_rates'])
                if avg_exclusion > best_exclusion:
                    best_exclusion = avg_exclusion
                    best_filter = filter_name
        
        if best_filter:
            insights.append(f"가장 효율적인 필터: {best_filter} ({best_exclusion*100:.2f}% 제외)")
        
        return insights