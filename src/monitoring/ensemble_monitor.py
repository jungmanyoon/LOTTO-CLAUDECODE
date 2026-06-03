"""
ENSEMBLE 모델 중점 모니터링 시스템
우수한 성능을 보이는 ENSEMBLE 모델을 집중 추적
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import deque
import os

class EnsemblePerformanceMonitor:
    """ENSEMBLE 모델 성능 모니터링"""
    
    def __init__(self):
        """모니터링 시스템 초기화"""
        self.performance_history = deque(maxlen=100)  # 최근 100회 예측 추적
        self.exceptional_predictions = []  # 4개 이상 일치한 우수 예측
        self.statistics = {
            'total_predictions': 0,
            'total_matches': 0,
            'match_distribution': {i: 0 for i in range(7)},  # 0~6개 일치
            'average_match_rate': 0.0,
            'best_prediction': None,
            'best_match_count': 0,
            '5_match_count': 0,  # 5개 일치 횟수
            '4_match_count': 0,  # 4개 일치 횟수
            'recent_trend': 'stable'  # 최근 추세
        }
        
        # 로그 파일 경로
        self.log_file = 'results/ensemble_performance.json'
        self.load_history()

        # [dashboard-monitoring-3] 주기적 영속화: record_prediction가 in-memory 누적만 하고
        # save_history()가 어디서도 호출되지 않아 통계가 디스크에 남지 않던 문제 방지.
        # N개 기록마다 자동 flush한다(장시간 실행 중에도 대시보드가 최신 통계를 읽도록).
        self._flush_interval = 50
        self._records_since_flush = 0

        logging.info("ENSEMBLE 모델 모니터링 시스템 초기화 완료")
    
    def record_prediction(self, 
                         prediction: List[int], 
                         actual: List[int],
                         round_num: int) -> Dict:
        """예측 결과 기록
        
        Args:
            prediction: 예측 번호
            actual: 실제 당첨 번호
            round_num: 회차 번호
            
        Returns:
            성능 지표
        """
        # 일치 개수 계산
        pred_set = set(prediction)
        actual_set = set(actual)
        match_count = len(pred_set & actual_set)
        matched_numbers = sorted(list(pred_set & actual_set))
        
        # 기록 생성
        record = {
            'round': round_num,
            'timestamp': datetime.now().isoformat(),
            'prediction': prediction,
            'actual': actual,
            'match_count': match_count,
            'matched_numbers': matched_numbers,
            'is_exceptional': match_count >= 4
        }
        
        # 히스토리에 추가
        self.performance_history.append(record)
        
        # 통계 업데이트
        self._update_statistics(record)
        
        # 우수 예측 기록
        if match_count >= 4:
            self._record_exceptional_prediction(record)
        
        # 추세 분석
        self._analyze_trend()
        
        # 실시간 알림
        self._send_alert(record)

        # [dashboard-monitoring-3] 주기적 디스크 영속화 (N개마다)
        self._records_since_flush += 1
        if self._records_since_flush >= self._flush_interval:
            self._records_since_flush = 0
            try:
                self.save_history()
            except Exception as e:
                logging.debug(f"[EnsembleMonitor] 주기적 히스토리 저장 실패: {e}")

        return {
            'match_count': match_count,
            'matched_numbers': matched_numbers,
            'is_exceptional': match_count >= 4,
            'current_average': self.statistics['average_match_rate'],
            'trend': self.statistics['recent_trend']
        }
    
    def _update_statistics(self, record: Dict):
        """통계 업데이트"""
        self.statistics['total_predictions'] += 1
        self.statistics['total_matches'] += record['match_count']
        self.statistics['match_distribution'][record['match_count']] += 1
        
        # 평균 일치율 계산
        if self.statistics['total_predictions'] > 0:
            self.statistics['average_match_rate'] = (
                self.statistics['total_matches'] / 
                (self.statistics['total_predictions'] * 6) * 100
            )
        
        # 최고 예측 업데이트
        if record['match_count'] > self.statistics['best_match_count']:
            self.statistics['best_match_count'] = record['match_count']
            self.statistics['best_prediction'] = record
        
        # 특별 카운트 업데이트
        if record['match_count'] == 5:
            self.statistics['5_match_count'] += 1
        elif record['match_count'] == 4:
            self.statistics['4_match_count'] += 1
    
    def _record_exceptional_prediction(self, record: Dict):
        """우수 예측 기록"""
        self.exceptional_predictions.append(record)
        
        # 로그에 특별 기록
        if record['match_count'] == 5:
            logging.info(f"[TARGET][TARGET][TARGET] ENSEMBLE 모델 대박 예측! 5개 일치!")
            logging.info(f"  회차: {record['round']}")
            logging.info(f"  예측: {record['prediction']}")
            logging.info(f"  실제: {record['actual']}")
            logging.info(f"  일치: {record['matched_numbers']}")
        elif record['match_count'] == 4:
            logging.info(f"[TARGET] ENSEMBLE 모델 우수 예측! 4개 일치!")
            logging.info(f"  회차: {record['round']}, 일치: {record['matched_numbers']}")
    
    def _analyze_trend(self):
        """최근 추세 분석"""
        if len(self.performance_history) < 10:
            self.statistics['recent_trend'] = 'insufficient_data'
            return
        
        # 최근 10회와 그 이전 10회 비교
        recent_10 = list(self.performance_history)[-10:]
        
        if len(self.performance_history) >= 20:
            previous_10 = list(self.performance_history)[-20:-10]
            
            recent_avg = np.mean([r['match_count'] for r in recent_10])
            previous_avg = np.mean([r['match_count'] for r in previous_10])
            
            if recent_avg > previous_avg * 1.1:
                self.statistics['recent_trend'] = 'improving'
            elif recent_avg < previous_avg * 0.9:
                self.statistics['recent_trend'] = 'declining'
            else:
                self.statistics['recent_trend'] = 'stable'
        else:
            self.statistics['recent_trend'] = 'stable'
    
    def _send_alert(self, record: Dict):
        """실시간 알림"""
        if record['match_count'] >= 5:
            # 5개 이상 일치 시 중요 알림
            alert_msg = f"[WARN] ENSEMBLE 모델 이상 성능 감지! {record['match_count']}개 일치"
            logging.warning(alert_msg)
            
            # 데이터 오염 가능성 체크
            if record['match_count'] == 6:
                logging.error("[ALERT] 데이터 오염 가능성! 6개 완전 일치 발생")
    
    def get_performance_report(self) -> Dict:
        """성능 보고서 생성"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'statistics': self.statistics,
            'recent_performance': list(self.performance_history)[-10:] if self.performance_history else [],
            'exceptional_predictions': self.exceptional_predictions[-5:],  # 최근 5개
            'performance_grade': self._calculate_grade()
        }
        
        return report
    
    def _calculate_grade(self) -> str:
        """성능 등급 계산"""
        if self.statistics['total_predictions'] == 0:
            return "N/A"
        
        avg_match = self.statistics['total_matches'] / self.statistics['total_predictions']
        
        if avg_match >= 2.0:
            return "S급 (탁월함)"
        elif avg_match >= 1.5:
            return "A급 (우수함)"
        elif avg_match >= 1.0:
            return "B급 (양호함)"
        elif avg_match >= 0.5:
            return "C급 (보통)"
        else:
            return "D급 (개선 필요)"
    
    def save_history(self):
        """히스토리 저장 - 0값 통계는 저장 스킵"""
        # [FIX N-W14] 초기화 직후 0값 통계를 JSON에 저장하는 문제 방지
        # total_predictions가 0이면 아직 실제 데이터가 없으므로 저장 스킵
        if self.statistics.get('total_predictions', 0) == 0:
            logging.debug("[EnsembleMonitor] 예측 데이터 없음(0), 히스토리 저장 스킵")
            return

        data = {
            'statistics': self.statistics,
            'performance_history': list(self.performance_history),
            'exceptional_predictions': self.exceptional_predictions
        }

        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_history(self):
        """히스토리 로드"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.statistics = data.get('statistics', self.statistics)
                    history = data.get('performance_history', [])
                    for record in history[-100:]:  # 최근 100개만 로드
                        self.performance_history.append(record)
                    self.exceptional_predictions = data.get('exceptional_predictions', [])
                logging.info(f"ENSEMBLE 모니터링 히스토리 로드 완료: {len(self.performance_history)}개 기록")
            except Exception as e:
                logging.error(f"히스토리 로드 실패: {e}")
    
    def print_summary(self):
        """요약 출력"""
        print("\n" + "="*60)
        print("ENSEMBLE 모델 성능 요약")
        print("="*60)
        print(f"총 예측 수: {self.statistics['total_predictions']}")
        print(f"평균 일치 개수: {self.statistics['total_matches'] / max(self.statistics['total_predictions'], 1):.2f}")
        print(f"평균 일치율: {self.statistics['average_match_rate']:.2f}%")
        print(f"성능 등급: {self._calculate_grade()}")
        print(f"최근 추세: {self.statistics['recent_trend']}")
        print(f"\n일치 분포:")
        for i in range(7):
            count = self.statistics['match_distribution'][i]
            if self.statistics['total_predictions'] > 0:
                percent = count / self.statistics['total_predictions'] * 100
                print(f"  {i}개 일치: {count}회 ({percent:.1f}%)")
        
        if self.statistics['best_prediction']:
            print(f"\n최고 예측: {self.statistics['best_match_count']}개 일치")
            print(f"  회차: {self.statistics['best_prediction']['round']}")
            print(f"  일치 번호: {self.statistics['best_prediction']['matched_numbers']}")
        
        print(f"\n특별 성과:")
        print(f"  5개 일치: {self.statistics['5_match_count']}회")
        print(f"  4개 일치: {self.statistics['4_match_count']}회")
        print("="*60)


# 싱글톤 인스턴스
_monitor_instance = None

def get_ensemble_monitor() -> EnsemblePerformanceMonitor:
    """싱글톤 모니터 인스턴스 반환"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = EnsemblePerformanceMonitor()
    return _monitor_instance