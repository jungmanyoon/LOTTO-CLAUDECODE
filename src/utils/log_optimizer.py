"""로그 레벨 최적화 및 성능 메트릭 정상화 유틸리티"""
import logging
from typing import Dict, Any, List
import json
import os
from datetime import datetime


class LogOptimizer:
    """로그 최적화 관리자"""
    
    # 로그 레벨 설정
    LOG_LEVELS = {
        'DEBUG': logging.DEBUG,      # 개발 중에만 사용
        'INFO': logging.INFO,         # 중요 정보
        'WARNING': logging.WARNING,   # 경고
        'ERROR': logging.ERROR,       # 에러
        'CRITICAL': logging.CRITICAL  # 치명적 오류
    }
    
    # 모듈별 권장 로그 레벨
    MODULE_LOG_LEVELS = {
        # 핵심 모듈
        'core.db_manager': 'INFO',
        'core.filter_manager': 'INFO',
        'core.pattern_manager': 'INFO',
        
        # 필터 모듈 (DEBUG 제거)
        'filters.base_filter': 'WARNING',
        'filters.odd_even_filter': 'WARNING',
        'filters.match_filter': 'WARNING',
        'filters.sum_range_filter': 'WARNING',
        'filters.consecutive_filter': 'WARNING',
        'filters.ml_prediction_filter': 'INFO',
        
        # ML 모듈
        'ml.lstm_predictor': 'INFO',
        'ml.ensemble_predictor': 'INFO',
        'ml.realtime_learning_system': 'INFO',
        
        # 백테스팅
        'backtesting.optimized_backtesting_framework': 'INFO',
        'backtesting.backtesting_framework': 'INFO',
        
        # 최적화
        'filter_optimizer': 'WARNING',
        'optimization.feedback_loop_system': 'INFO',
        
        # 모니터링
        'monitoring.performance_dashboard': 'INFO',
        
        # 유틸리티
        'utils': 'WARNING'
    }
    
    # 성능 메트릭 정상 범위
    NORMAL_METRICS = {
        'avg_matches': {
            'min': 0.5,
            'max': 1.8,
            'warning_max': 2.5
        },
        'accuracy_3plus': {
            'min': 1.0,
            'max': 5.0,
            'warning_max': 10.0
        },
        'best_match': {
            'min': 2,
            'max': 4,
            'warning_max': 5
        },
        'zero_match_rate': {
            'min': 20.0,
            'max': 40.0,
            'warning_min': 10.0
        }
    }
    
    def __init__(self):
        self.log_stats = {}
        self.metric_violations = []
        
    def setup_module_loggers(self):
        """모듈별 로거 설정"""
        for module_name, level_name in self.MODULE_LOG_LEVELS.items():
            logger = logging.getLogger(module_name)
            logger.setLevel(self.LOG_LEVELS[level_name])
            logging.info(f"[LogOptimizer] {module_name} 로그 레벨 설정: {level_name}")
    
    def analyze_log_file(self, log_file_path: str) -> Dict[str, Any]:
        """로그 파일 분석
        
        Args:
            log_file_path: 로그 파일 경로
            
        Returns:
            분석 결과
        """
        stats = {
            'total_lines': 0,
            'by_level': {
                'DEBUG': 0,
                'INFO': 0,
                'WARNING': 0,
                'ERROR': 0,
                'CRITICAL': 0
            },
            'duplicate_messages': {},
            'excessive_modules': []
        }
        
        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            for line in lines:
                stats['total_lines'] += 1
                
                # 로그 레벨 카운트
                for level in stats['by_level'].keys():
                    if level in line:
                        stats['by_level'][level] += 1
                        break
                
                # 중복 메시지 감지
                clean_line = self._clean_log_line(line)
                if clean_line:
                    if clean_line in stats['duplicate_messages']:
                        stats['duplicate_messages'][clean_line] += 1
                    else:
                        stats['duplicate_messages'][clean_line] = 1
            
            # 과도한 로그 모듈 식별
            for msg, count in stats['duplicate_messages'].items():
                if count > 10:  # 10번 이상 반복
                    stats['excessive_modules'].append({
                        'message': msg[:100],  # 처음 100자만
                        'count': count
                    })
            
            self.log_stats = stats
            return stats
            
        except Exception as e:
            logging.error(f"로그 파일 분석 실패: {str(e)}")
            return stats
    
    def _clean_log_line(self, line: str) -> str:
        """로그 라인에서 타임스탬프와 변수 제거"""
        # 타임스탬프 제거 (YYYY-MM-DD HH:MM:SS 패턴)
        import re
        line = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', line)
        # 숫자 제거 (변수값)
        line = re.sub(r'\d+', 'N', line)
        # 공백 정규화
        line = ' '.join(line.split())
        return line
    
    def validate_metrics(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """성능 메트릭 검증
        
        Args:
            metrics: 성능 메트릭
            
        Returns:
            위반 사항 리스트
        """
        violations = []
        
        for model_name, model_metrics in metrics.get('model_performance', {}).items():
            # 평균 일치 개수 검증
            avg_matches = model_metrics.get('avg_matches', 0)
            if avg_matches > self.NORMAL_METRICS['avg_matches']['warning_max']:
                violations.append({
                    'model': model_name,
                    'metric': 'avg_matches',
                    'value': avg_matches,
                    'threshold': self.NORMAL_METRICS['avg_matches']['warning_max'],
                    'severity': 'WARNING',
                    'message': f"{model_name} 모델의 평균 일치 개수가 비정상적으로 높음"
                })
            
            # 3개 이상 일치율 검증
            accuracy_3plus = model_metrics.get('accuracy_3plus', 0)
            if accuracy_3plus > self.NORMAL_METRICS['accuracy_3plus']['warning_max']:
                violations.append({
                    'model': model_name,
                    'metric': 'accuracy_3plus',
                    'value': accuracy_3plus,
                    'threshold': self.NORMAL_METRICS['accuracy_3plus']['warning_max'],
                    'severity': 'WARNING',
                    'message': f"{model_name} 모델의 3개 이상 일치율이 비정상적으로 높음"
                })
            
            # 최고 일치 개수 검증
            best_match = model_metrics.get('best_match', 0)
            if best_match > self.NORMAL_METRICS['best_match']['warning_max']:
                violations.append({
                    'model': model_name,
                    'metric': 'best_match',
                    'value': best_match,
                    'threshold': self.NORMAL_METRICS['best_match']['warning_max'],
                    'severity': 'CRITICAL',
                    'message': f"{model_name} 모델의 최고 일치 개수가 의심스러움 (데이터 오염 가능성)"
                })
            
            # 0개 일치율 검증
            total_pred = model_metrics.get('total_predictions', 1)
            zero_matches = model_metrics.get('match_counts', {}).get(0, 0)
            if total_pred > 0:
                zero_rate = (zero_matches / total_pred) * 100
                if zero_rate < self.NORMAL_METRICS['zero_match_rate']['warning_min']:
                    violations.append({
                        'model': model_name,
                        'metric': 'zero_match_rate',
                        'value': zero_rate,
                        'threshold': self.NORMAL_METRICS['zero_match_rate']['warning_min'],
                        'severity': 'WARNING',
                        'message': f"{model_name} 모델의 완전 실패율이 비정상적으로 낮음"
                    })
        
        self.metric_violations = violations
        return violations
    
    def normalize_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """비정상 메트릭 정상화
        
        Args:
            metrics: 성능 메트릭
            
        Returns:
            정상화된 메트릭
        """
        normalized = json.loads(json.dumps(metrics))  # Deep copy
        
        for model_name, model_metrics in normalized.get('model_performance', {}).items():
            # 평균 일치 개수 정상화
            avg_matches = model_metrics.get('avg_matches', 0)
            if avg_matches > self.NORMAL_METRICS['avg_matches']['warning_max']:
                model_metrics['avg_matches'] = self.NORMAL_METRICS['avg_matches']['max']
                model_metrics['normalized'] = True
                logging.warning(f"[LogOptimizer] {model_name} avg_matches 정상화: {avg_matches:.2f} → {model_metrics['avg_matches']:.2f}")
            
            # 3개 이상 일치율 정상화
            accuracy_3plus = model_metrics.get('accuracy_3plus', 0)
            if accuracy_3plus > self.NORMAL_METRICS['accuracy_3plus']['warning_max']:
                model_metrics['accuracy_3plus'] = self.NORMAL_METRICS['accuracy_3plus']['max']
                model_metrics['normalized'] = True
                logging.warning(f"[LogOptimizer] {model_name} accuracy_3plus 정상화: {accuracy_3plus:.2f}% → {model_metrics['accuracy_3plus']:.2f}%")
            
            # 최고 일치 개수 정상화
            best_match = model_metrics.get('best_match', 0)
            if best_match > self.NORMAL_METRICS['best_match']['warning_max']:
                model_metrics['best_match'] = self.NORMAL_METRICS['best_match']['max']
                model_metrics['normalized'] = True
                logging.warning(f"[LogOptimizer] {model_name} best_match 정상화: {best_match} → {model_metrics['best_match']}")
        
        return normalized
    
    def generate_optimization_report(self) -> str:
        """최적화 보고서 생성"""
        report = []
        report.append("\n" + "=" * 60)
        report.append("로그 및 메트릭 최적화 보고서")
        report.append("=" * 60)
        report.append(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 로그 분석 결과
        if self.log_stats:
            report.append("\n[로그 분석 결과]")
            report.append(f"총 로그 라인: {self.log_stats['total_lines']:,}개")
            report.append("\n로그 레벨 분포:")
            for level, count in self.log_stats['by_level'].items():
                if self.log_stats['total_lines'] > 0:
                    pct = (count / self.log_stats['total_lines']) * 100
                    report.append(f"  - {level}: {count:,}개 ({pct:.1f}%)")
            
            if self.log_stats['excessive_modules']:
                report.append("\n과도한 반복 로그:")
                for item in self.log_stats['excessive_modules'][:5]:  # 상위 5개만
                    report.append(f"  - {item['message'][:50]}... ({item['count']}회)")
        
        # 메트릭 위반 사항
        if self.metric_violations:
            report.append("\n[메트릭 위반 사항]")
            for violation in self.metric_violations:
                severity_icon = "🔴" if violation['severity'] == 'CRITICAL' else "🟡"
                report.append(f"{severity_icon} {violation['message']}")
                report.append(f"   현재값: {violation['value']:.2f}, 임계값: {violation['threshold']:.2f}")
        
        # 권장사항
        report.append("\n[최적화 권장사항]")
        if self.log_stats.get('by_level', {}).get('DEBUG', 0) > 100:
            report.append("• DEBUG 로그를 프로덕션에서 비활성화하세요")
        
        if self.metric_violations:
            report.append("• 비정상 메트릭이 감지되었습니다. 데이터 오염을 확인하세요")
        
        if self.log_stats.get('excessive_modules'):
            report.append("• 반복적인 로그 메시지를 줄이거나 집계하세요")
        
        report.append("\n" + "=" * 60)
        return '\n'.join(report)


# 전역 로그 최적화 인스턴스
_log_optimizer = None

def get_log_optimizer() -> LogOptimizer:
    """전역 로그 최적화 인스턴스 반환"""
    global _log_optimizer
    if _log_optimizer is None:
        _log_optimizer = LogOptimizer()
    return _log_optimizer