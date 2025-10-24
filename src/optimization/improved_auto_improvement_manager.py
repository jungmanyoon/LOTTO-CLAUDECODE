#!/usr/bin/env python3
"""
개선된 자동 개선 시스템 통합 관리자
- 매 백테스팅마다 성능 기준 업데이트
- 동적 임계값 조정
- 회차별 필터 재적용
"""
import logging
import json
import os
import yaml
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.core.performance_metrics import PerformanceMetrics


class ImprovedAutoImprovementManager:
    """개선된 자동 개선 시스템 통합 관리자"""

    def __init__(self, state_file: str = "data/improved_auto_improvement_state.json"):
        """
        Args:
            state_file: 상태 저장 파일 경로
        """
        self.state_file = state_file
        self.threshold_history_file = "data/threshold_history.json"
        self.state = self._load_state()

        # 기본 설정값 정의
        default_config = {
            'backtest_window_size': 100,
            'min_improvement_rate': 0.0,  # 조금이라도 개선되면 적용
            'max_iterations_per_session': 10,
            'performance_threshold': 999.0,   # 목표 성능 앜으면 계속 개선
            'auto_save_interval': 1,        # 매 반복마다 저장
            'dynamic_threshold_enabled': True,  # 동적 임계값 활성화
            'threshold_adjustment_rate': 0.1,   # 임계값 조정 비율
            'min_threshold': 0.3,  # 최소 임계값
            'max_threshold': 3.0,  # 최대 임계값
        }

        # 상태에서 config 불러오고 누락된 키는 기본값으로 채우기
        self.config = self.state.get('config', {})
        for key, value in default_config.items():
            if key not in self.config:
                self.config[key] = value

        # 상태에 config 업데이트
        self.state['config'] = self.config

        # 임계값 히스토리 로드
        self.threshold_history = self._load_threshold_history()

        logging.info(f"개선된 자동 개선 관리자 초기화 완료. 총 백테스팅 횟수: {self.state['total_backtest_count']}")

    def _load_state(self) -> Dict[str, Any]:
        """저장된 상태 불러오기"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                logging.info(f"이전 상태를 불러왔습니다: {self.state_file}")
                return state
            except Exception as e:
                logging.error(f"상태 파일 로드 실패: {e}")

        # 새로운 상태 생성
        return self._create_new_state()

    def _load_threshold_history(self) -> List[Dict[str, Any]]:
        """임계값 히스토리 로드"""
        if os.path.exists(self.threshold_history_file):
            try:
                with open(self.threshold_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"임계값 히스토리 로드 실패: {e}")
        return []

    def _create_new_state(self) -> Dict[str, Any]:
        """새로운 상태 생성"""
        return {
            'version': '2.0',  # 버전 업그레이드
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'total_backtest_count': 0,
            'improvement_history': [],
            'best_models': {
                'lstm': {'params': {}, 'performance': 0.0, 'round': 0},
                'ensemble': {'params': {}, 'performance': 0.0, 'round': 0},
                'monte_carlo': {'params': {}, 'performance': 0.0, 'round': 0}
            },
            'current_performance': {
                'lstm': 0.0,
                'ensemble': 0.0,
                'monte_carlo': 0.0,
                'overall': 0.0,
                'round': 0  # 어느 회차의 성능인지 추적
            },
            'last_backtest_performance': {  # 마지막 백테스팅 성능 저장
                'lstm': 0.0,
                'ensemble': 0.0,
                'monte_carlo': 0.0,
                'overall': 0.0,
                'round': 0
            },
            'config': {},
            'filter_settings': {
                'sum_range': {'min': 100, 'max': 170},
                'odd_even_ratio': {'min_odd': 2, 'max_odd': 4},
                'consecutive_numbers': {'max_consecutive': 2},
                'section_distribution': {'min_sections': 3},
                'prime_composite_ratio': {'min_prime': 1, 'max_prime': 4}
            },
            'current_threshold': 1.0,  # 현재 임계값
            'threshold_performance_map': {}  # 임계값별 성능 매핑
        }

    def save_state(self):
        """현재 상태 저장"""
        try:
            # 디렉토리 생성
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            # 상태 업데이트
            self.state['last_updated'] = datetime.now().isoformat()
            self.state['config'] = self.config

            # 파일에 저장
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)

            # 임계값 히스토리 저장
            with open(self.threshold_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.threshold_history, f, indent=2, ensure_ascii=False)

            logging.info(f"상태 저장 완료 - 총 백테스팅 횟수: {self.state['total_backtest_count']}")

        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")

    def track_backtest_improved(self, backtest_results: Dict[str, Any], round_num: int = None) -> Dict[str, Any]:
        """개선된 백테스팅 결과 추적

        Args:
            backtest_results: 백테스팅 결과
            round_num: 백테스팅한 회차 번호

        Returns:
            Dict: 개선 정보 및 업데이트 여부
        """
        # 백테스팅 횟수 증가
        old_count = self.state['total_backtest_count']
        self.state['total_backtest_count'] += 1
        logging.info(f"백테스팅 횟수 증가: {old_count} → {self.state['total_backtest_count']}")

        # 성능 추출
        new_performance = self._extract_performance(backtest_results)
        new_performance['round'] = round_num or 0

        # 이전 백테스팅 성능과 비교 (current_performance가 아닌 last_backtest_performance와 비교)
        old_performance = self.state['last_backtest_performance'].copy()

        # 개선 여부 판단
        improvement_info = {
            'backtest_number': self.state['total_backtest_count'],
            'timestamp': datetime.now().isoformat(),
            'round': round_num,
            'old_performance': old_performance,
            'new_performance': new_performance,
            'improvements': {},
            'should_update': False,
            'update_reasons': [],
            'threshold_used': self.state.get('current_threshold', 1.0)
        }

        # 각 모델별 개선 확인
        for model_type in ['lstm', 'ensemble', 'monte_carlo']:
            old_perf = old_performance.get(model_type, 0.0)
            new_perf = new_performance.get(model_type, 0.0)

            if old_perf > 0:
                improvement_rate = (new_perf - old_perf) / old_perf
            else:
                improvement_rate = 1.0 if new_perf > 0 else 0.0

            improvement_info['improvements'][model_type] = {
                'rate': improvement_rate,
                'absolute': new_perf - old_perf,
                'improved': improvement_rate > self.config.get('min_improvement_rate', 0.001)
            }

            # 최고 성능 업데이트
            if new_perf > self.state['best_models'][model_type]['performance']:
                self.state['best_models'][model_type]['performance'] = new_perf
                self.state['best_models'][model_type]['round'] = round_num or 0
                improvement_info['update_reasons'].append(f"{model_type} 최고 성능 갱신")
                improvement_info['should_update'] = True

        # 전체 성능 개선 확인
        old_overall = old_performance.get('overall', 0.0)
        new_overall = new_performance.get('overall', 0.0)

        if old_overall > 0:
            overall_improvement = (new_overall - old_overall) / old_overall
        else:
            overall_improvement = 1.0 if new_overall > 0 else 0.0

        # 전체 성능이 개선된 경우 current_performance 업데이트
        if overall_improvement > self.config.get('min_improvement_rate', 0.001):
            improvement_info['should_update'] = True
            improvement_info['update_reasons'].append("전체 성능 개선")
            self.state['current_performance'] = new_performance

        # 마지막 백테스팅 성능 항상 업데이트 (다음 비교를 위해)
        self.state['last_backtest_performance'] = new_performance

        # 임계값별 성능 기록
        current_threshold = self.state.get('current_threshold', 1.0)
        if current_threshold not in self.state['threshold_performance_map']:
            self.state['threshold_performance_map'][current_threshold] = []

        self.state['threshold_performance_map'][current_threshold].append({
            'round': round_num,
            'performance': new_overall,
            'timestamp': datetime.now().isoformat()
        })

        # 개선 이력 추가
        self.state['improvement_history'].append(improvement_info)

        # 이력 크기 제한 (최근 100개만 유지)
        if len(self.state['improvement_history']) > 100:
            self.state['improvement_history'] = self.state['improvement_history'][-100:]

        # 자동 저장
        self.save_state()

        return improvement_info

    def adjust_threshold_dynamically(self, performance: float) -> float:
        """성능에 따른 동적 임계값 조정

        Args:
            performance: 현재 성능 (평균 매칭 수)

        Returns:
            float: 조정된 임계값
        """
        if not self.config.get('dynamic_threshold_enabled', True):
            return self.state.get('current_threshold', 1.0)

        current_threshold = self.state.get('current_threshold', 1.0)
        new_threshold = current_threshold

        # 성능별 임계값 전략
        if performance < 0.8:
            # 성능이 낮으면 임계값을 낮춰서 더 많은 조합 포함
            new_threshold = max(
                self.config['min_threshold'],
                current_threshold * (1 - self.config['threshold_adjustment_rate'])
            )
            logging.info(f"성능 낮음 ({performance:.3f}) - 임계값 감소: {current_threshold:.2f} → {new_threshold:.2f}")
        elif performance > 1.8:
            # 성능이 너무 높으면 임계값을 높여서 더 많은 조합 제외
            new_threshold = min(
                self.config['max_threshold'],
                current_threshold * (1 + self.config['threshold_adjustment_rate'])
            )
            logging.info(f"성능 높음 ({performance:.3f}) - 임계값 증가: {current_threshold:.2f} → {new_threshold:.2f}")
        else:
            # 적정 성능 구간 (0.8 ~ 1.8)
            logging.info(f"성능 적정 ({performance:.3f}) - 임계값 유지: {current_threshold:.2f}")

        # 임계값 변경이 있으면 기록
        if new_threshold != current_threshold:
            self.threshold_history.append({
                'timestamp': datetime.now().isoformat(),
                'old_threshold': current_threshold,
                'new_threshold': new_threshold,
                'performance': performance,
                'reason': 'dynamic_adjustment'
            })

            # 상태 업데이트
            self.state['current_threshold'] = new_threshold

            # 설정 파일 업데이트
            self.update_threshold_in_config(new_threshold)

        return new_threshold

    def update_threshold_in_config(self, threshold: float):
        """설정 파일의 임계값 업데이트

        Args:
            threshold: 새로운 임계값
        """
        config_file = 'configs/adaptive_filter_config.yaml'

        try:
            # 현재 설정 로드
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # ✅ PRECISION FIX: 임계값 업데이트 (round로 부동소수점 오차 제거)
            config['global_probability_threshold'] = round(threshold, 2)

            # 설정 저장
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            logging.info(f"설정 파일에 임계값 업데이트: {round(threshold, 2)}")

        except Exception as e:
            logging.error(f"설정 파일 업데이트 실패: {e}")

    def update_filters_for_round(self, round_num: int, db_manager, filter_manager):
        """특정 회차를 위한 필터 업데이트

        Args:
            round_num: 회차 번호
            db_manager: 데이터베이스 매니저
            filter_manager: 필터 매니저
        """
        try:
            # 해당 회차까지의 당첨번호 가져오기
            all_numbers = db_manager.get_all_winning_numbers()
            numbers_up_to_round = [num for round, num in all_numbers if round <= round_num]

            # 적응형 필터 패턴 재분석
            if hasattr(filter_manager, 'adaptive_filter'):
                filter_manager.adaptive_filter.analyze_patterns(numbers_up_to_round)
                logging.info(f"회차 {round_num}까지의 데이터로 필터 패턴 재분석 완료")

            # 필터 재적용 (필요시)
            # 이 부분은 실제 필터 재생성 로직이 필요할 수 있음

        except Exception as e:
            logging.error(f"필터 업데이트 실패: {e}")

    def _extract_performance(self, backtest_results: Dict[str, Any]) -> Dict[str, float]:
        """
        백테스팅 결과에서 성능 추출 (통합 메트릭 시스템 사용)

        Returns raw avg_matches (0-6 scale) for all models.
        Use PerformanceMetrics.normalize_score() for comparisons.
        """
        performance = {
            'lstm': 0.0,
            'ensemble': 0.0,
            'monte_carlo': 0.0,
            'overall': 0.0
        }

        metrics = backtest_results.get('performance_metrics', {})
        model_performance = metrics.get('model_performance', {})

        # 각 모델 성능 추출 (raw avg_matches)
        for model_type in ['lstm', 'ensemble', 'monte_carlo']:
            model_metrics = model_performance.get(model_type, {})
            performance[model_type] = model_metrics.get('avg_matches', 0.0)

        # 전체 성능 계산 (가중 평균) - 통합 함수 사용
        performance['overall'] = PerformanceMetrics.calculate_overall_score(
            performance['lstm'],
            performance['ensemble'],
            performance['monte_carlo']
        )

        logging.debug(
            f"[Improved Auto Improvement] Extracted performance: "
            f"Overall={performance['overall']:.3f} (raw)"
        )

        return performance

    def get_optimization_summary(self) -> Dict[str, Any]:
        """최적화 요약 정보 반환"""
        summary = {
            'total_backtests': self.state['total_backtest_count'],
            'current_threshold': self.state.get('current_threshold', 1.0),
            'best_performance': {
                model: data['performance']
                for model, data in self.state['best_models'].items()
            },
            'current_performance': self.state['current_performance'],
            'last_performance': self.state['last_backtest_performance'],
            'threshold_history': self.threshold_history[-10:] if self.threshold_history else [],
            'improvements_count': sum(
                1 for h in self.state['improvement_history']
                if h.get('should_update', False)
            ),
            'last_improvement': None
        }

        # 마지막 개선 정보
        for h in reversed(self.state['improvement_history']):
            if h.get('should_update', False):
                summary['last_improvement'] = h
                break

        return summary

    def get_status_report(self) -> str:
        """현재 상태 보고서 생성"""
        report = []
        report.append("\n" + "="*60)
        report.append("🤖 개선된 자동 개선 시스템 상태 보고서")
        report.append("="*60)

        # 기본 정보
        report.append(f"\n📊 총 백테스팅 횟수: {self.state['total_backtest_count']}회")
        report.append(f"📅 시스템 생성일: {self.state.get('created_at', 'N/A')}")
        report.append(f"🔄 마지막 업데이트: {self.state.get('last_updated', 'N/A')}")

        # 현재 성능
        report.append(f"\n📈 현재 성능:")
        current = self.state['current_performance']
        report.append(f"  • LSTM: {current.get('lstm', 0):.3f}")
        report.append(f"  • Ensemble: {current.get('ensemble', 0):.3f}")
        report.append(f"  • Monte Carlo: {current.get('monte_carlo', 0):.3f}")
        report.append(f"  • 전체: {current.get('overall', 0):.3f}")

        # 최고 성능
        report.append(f"\n🏆 최고 성능:")
        for model, data in self.state['best_models'].items():
            report.append(f"  • {model}: {data['performance']:.3f} (회차: {data.get('round', 'N/A')})")

        # 임계값 정보
        report.append(f"\n⚙️ 임계값 설정:")
        report.append(f"  • 현재 임계값: {self.state.get('current_threshold', 1.0):.2f}%")
        report.append(f"  • 동적 조정: {'활성화' if self.config.get('dynamic_threshold_enabled', True) else '비활성화'}")

        # 최근 개선 이력
        report.append(f"\n📊 최근 개선 이력:")
        recent_improvements = [h for h in self.state['improvement_history'][-5:]]

        for i, history in enumerate(recent_improvements, 1):
            timestamp = history.get('timestamp', 'N/A')
            should_update = history.get('should_update', False)
            update_reasons = history.get('update_reasons', [])

            # 타임스탬프에서 날짜만 추출
            if timestamp != 'N/A':
                try:
                    date_only = timestamp.split('T')[0]
                except Exception as e:
                    logging.debug(f"개선 실패 (무시): {e}")
                    date_only = timestamp
            else:
                date_only = 'N/A'

            status = "✅ 개선" if should_update else "❌ 개선 없음"
            report.append(f"\n  [{i}회차] {date_only}")

            if should_update:
                report.append(f"    {status}: {', '.join(update_reasons)}")
            else:
                report.append(f"    {status}")

            # 개선 정보
            improvements = history.get('improvements', {})
            for model_type, imp_data in improvements.items():
                if imp_data.get('improved', False):
                    rate = imp_data.get('rate', 0) * 100
                    absolute = imp_data.get('absolute', 0)
                    report.append(f"    • {model_type}: +{rate:.1f}% (+{absolute:.3f})")

        report.append("\n" + "="*60)

        return '\n'.join(report)


# 싱글톤 인스턴스를 위한 전역 변수
_manager_instance = None


def get_improved_manager() -> ImprovedAutoImprovementManager:
    """개선된 자동 개선 관리자 싱글톤 인스턴스 반환"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ImprovedAutoImprovementManager()
    return _manager_instance