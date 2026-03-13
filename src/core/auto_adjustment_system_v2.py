"""
자동 조정 시스템 V2 - global_probability_threshold만 조정
백테스팅 결과에 따라 임계값을 자동으로 조정하는 단순화된 시스템
"""
import logging
import time
import yaml
import os
from typing import Dict, Any, Optional
from datetime import datetime
import json
from ..backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
from .performance_metrics import PerformanceMetrics

class AutoAdjustmentSystemV2:
    """
    단순화된 자동 조정 시스템
    - global_probability_threshold 하나만 조정
    - 백테스팅 성능에 따라 자동 조정
    """
    
    def __init__(self, db_manager, config=None):
        self.db_manager = db_manager
        self.config_path = 'configs/adaptive_filter_config.yaml'
        self.state_file = 'data/auto_adjustment_state_v2.json'

        # ✅ ThresholdManager 통합 (Single Source of Truth)
        from .threshold_manager import get_threshold_manager
        self.threshold_manager = get_threshold_manager()

        # 조정 전략 설정
        self.adjustment_strategy = {
            'excellent': {'threshold': 0.5, 'min_score': 0.8},   # 매우 좋음: 보수적 유지
            'good': {'threshold': 0.75, 'min_score': 0.6},      # 좋음: 약간 보수적
            'normal': {'threshold': 1.0, 'min_score': 0.4},     # 보통: 표준
            'poor': {'threshold': 1.5, 'min_score': 0.2},       # 나쁨: 공격적
            'very_poor': {'threshold': 2.0, 'min_score': 0.0}   # 매우 나쁨: 매우 공격적
        }

        # 상태 추적
        self.state = {
            'current_threshold': self._get_current_threshold(),
            'last_performance_score': 0.0,
            'adjustment_history': [],
            'backtest_count': 0,
            'last_backtest_round': None,
            'performance_history': []
        }

        # ✅ FIX: 백테스팅 설정 로드
        if config is None:
            from ..utils.config_manager import ConfigManager
            config = ConfigManager().config
        backtesting_config = config.get('backtesting', {})
        self.backtest_window = backtesting_config.get('validation_window', 300)  # 50 → 300
        logging.info(f"[자동 조정 V2] 백테스트 윈도우: {self.backtest_window} 회차")

        self.backtesting_framework = OptimizedBacktestingFramework(self.db_manager, config=config)

        # 상태 파일 로드 (하지만 yaml 파일의 임계값을 우선 사용)
        self._load_state()
        
        # YAML 파일의 값을 항상 우선 사용
        yaml_threshold = self._get_current_threshold()
        if abs(self.state['current_threshold'] - yaml_threshold) > 0.01:
            logging.info(f"  [알림] YAML 설정 우선 적용: {self.state['current_threshold']}% → {yaml_threshold}%")
            self.state['current_threshold'] = yaml_threshold
        
        # debug 레벨: main.py에서 동일 메시지를 info로 출력하므로 중복 방지
        logging.debug("[자동 조정 시스템 V2] __init__ 완료 (임계값: %s%%)", self.state['current_threshold'])
    
    def _get_current_threshold(self) -> float:
        """현재 설정된 임계값 읽기 (ThresholdManager 사용)"""
        try:
            # ✅ ThresholdManager에서 가져오기 (Decimal 정밀도)
            return float(self.threshold_manager.get_threshold())
        except Exception as e:
            logging.error(f"임계값 읽기 실패: {e}")
            return 1.0
    
    def _set_threshold(self, new_threshold: float) -> bool:
        """새로운 임계값 설정 (ThresholdManager 사용)"""
        try:
            # ✅ ThresholdManager에 위임 (Decimal 정밀도 + Observer 패턴)
            old_threshold = self.threshold_manager.get_threshold()
            self.threshold_manager.set_threshold(new_threshold, source="auto_adjustment_v2")

            # ✅ 설정 파일에 저장 (ThresholdManager가 처리)
            success = self.threshold_manager.save_to_config()

            if not success:
                logging.error("임계값 저장 실패")
                return False
            
            logging.info(f"✅ 임계값 변경: {old_threshold}% → {new_threshold}%")
            
            # 상태 업데이트
            self.state['current_threshold'] = new_threshold
            self.state['adjustment_history'].append({
                'timestamp': datetime.now().isoformat(),
                'old_threshold': old_threshold,
                'new_threshold': new_threshold,
                'reason': f"성능 점수 {self.state['last_performance_score']:.3f}"
            })
            
            # 최근 10개 이력만 유지
            if len(self.state['adjustment_history']) > 10:
                self.state['adjustment_history'] = self.state['adjustment_history'][-10:]
            
            self._save_state()
            return True
            
        except Exception as e:
            logging.error(f"임계값 설정 실패: {e}")
            return False
    
    def analyze_and_adjust(
        self,
        performance_score: float,
        skip_backtest: bool = False
    ) -> Dict[str, Any]:
        """
        백테스팅 성능에 따라 임계값 자동 조정

        Args:
            performance_score: 백테스팅 성능 점수 (0.0 ~ 1.0)
            skip_backtest: True일 경우 백테스팅 생략 (이미 실행된 경우)

        Returns:
            조정 결과
        """
        logging.info("\n" + "="*60)
        logging.info("🔄 자동 임계값 조정 분석")
        if skip_backtest:
            logging.info("   (기존 백테스팅 결과 재사용)")
        logging.info("="*60)

        self.state['last_performance_score'] = performance_score
        if not skip_backtest:
            self.state['backtest_count'] += 1

        # 현재 성능 평가
        logging.info(f"백테스팅 성능: {performance_score:.3f}")
        
        # 최적 임계값 결정
        optimal_threshold = self._determine_optimal_threshold(performance_score)
        current_threshold = self.state['current_threshold']
        
        result = {
            'performance_score': performance_score,
            'current_threshold': current_threshold,
            'optimal_threshold': optimal_threshold,
            'adjusted': False
        }
        
        # 조정 필요 여부 판단
        if abs(optimal_threshold - current_threshold) > 0.01:  # 0.01% 이상 차이
            logging.info(f"\n📊 임계값 조정 필요")
            logging.info(f"  현재: {current_threshold}%")
            logging.info(f"  권장: {optimal_threshold}%")
            
            # 조정 실행
            if self._set_threshold(optimal_threshold):
                result['adjusted'] = True
                result['message'] = f"임계값 조정 완료: {current_threshold}% → {optimal_threshold}%"
                
                # 모드 설명
                mode = self._get_mode_description(optimal_threshold)
                logging.info(f"  모드: {mode}")
                
                # 예상 효과
                self._log_expected_impact(optimal_threshold)
            else:
                result['message'] = "임계값 조정 실패"
        else:
            logging.info(f"✅ 현재 임계값 {current_threshold}% 유지 (최적 상태)")
            result['message'] = "임계값 조정 불필요"
        
        self._save_state()
        return result
    
    def _determine_optimal_threshold(self, performance_score: float) -> float:
        """성능 점수에 따른 최적 임계값 결정"""
        
        # 성능에 따른 임계값 매핑
        for level, config in self.adjustment_strategy.items():
            if performance_score >= config['min_score']:
                return config['threshold']
        
        # 기본값
        return 1.0
    
    def _get_mode_description(self, threshold: float) -> str:
        """임계값에 따른 모드 설명"""
        if threshold <= 0.5:
            return "매우 보수적 (희귀 패턴만 제외)"
        elif threshold <= 0.75:
            return "보수적 (적은 패턴 제외)"
        elif threshold <= 1.0:
            return "표준 (균형잡힌 필터링)"
        elif threshold <= 1.5:
            return "공격적 (많은 패턴 제외)"
        else:
            return "매우 공격적 (대량 패턴 제외)"
    
    def _log_expected_impact(self, threshold: float):
        """임계값 변경의 예상 영향"""
        total = 8145060
        
        # 임계값별 예상 필터링 비율
        if threshold <= 0.5:
            remaining = int(total * 0.65)  # 65% 남음
        elif threshold <= 0.75:
            remaining = int(total * 0.50)  # 50% 남음
        elif threshold <= 1.0:
            remaining = int(total * 0.35)  # 35% 남음
        elif threshold <= 1.5:
            remaining = int(total * 0.25)  # 25% 남음
        else:
            remaining = int(total * 0.15)  # 15% 남음
        
        logging.info(f"\n  [예상 효과]")
        logging.info(f"  - 필터링 후: 약 {remaining:,}개 조합")
        logging.info(f"  - 축소율: {(1 - remaining/total)*100:.1f}%")
    
    def _run_backtest_performance(self) -> Optional[Dict[str, Any]]:
        """Run a backtest to evaluate current performance."""
        try:
            latest_round = self.db_manager.lotto_db.get_last_round()
            if latest_round is None:
                logging.warning("[Auto Adjustment V2] No latest round information available for backtesting.")
                return None

            start_round = max(1, latest_round - self.backtest_window + 1)
            logging.info(
                f"\n[Auto Adjustment V2] Running backtest for rounds {start_round}~{latest_round} (window {self.backtest_window})"
            )

            results = self.backtesting_framework.run_backtest(
                start_round=start_round,
                end_round=latest_round,
                window_size=self.backtest_window
            )

            performance_score = self._calculate_overall_performance(results)

            return {
                'start_round': start_round,
                'end_round': latest_round,
                'performance_score': performance_score,
                'metrics': results.get('performance_metrics', {})
            }
        except Exception as e:
            logging.error(f"[Auto Adjustment V2] Backtest execution failed: {e}")
            return None

    def _calculate_overall_performance(self, backtest_results: Dict[str, Any]) -> float:
        """
        Calculate normalized performance score from backtest results.

        Uses unified PerformanceMetrics system for consistent scoring.
        Returns normalized score in [0, 1] range.
        """
        try:
            metrics = backtest_results.get('performance_metrics', {}) if backtest_results else {}
            model_performance = metrics.get('model_performance', {})

            if not isinstance(model_performance, dict) or not model_performance:
                return 0.0

            avg_matches = []
            for model_metrics in model_performance.values():
                if not isinstance(model_metrics, dict):
                    continue
                avg_match = model_metrics.get('avg_matches')
                if avg_match is not None:
                    avg_matches.append(avg_match)

            if not avg_matches:
                return 0.0

            # Calculate raw average across all models
            overall_avg_raw = sum(avg_matches) / len(avg_matches)

            # Use unified normalization formula
            normalized_score = PerformanceMetrics.normalize_score(overall_avg_raw)

            logging.debug(
                f"[Auto Adjustment V2] Performance: raw={overall_avg_raw:.3f}, "
                f"normalized={normalized_score:.3f}"
            )

            return normalized_score
        except Exception as e:
            logging.error(f"[Auto Adjustment V2] Failed to calculate performance: {e}")
            return 0.0


    def _load_state(self):
        """저장된 상태 로드"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    self.state.update(saved_state)
                    self.state.setdefault('adjustment_history', [])
                    self.state.setdefault('performance_history', [])
                    self.state.setdefault('last_backtest_round', None)
                logging.debug(f"자동 조정 상태 로드: {self.state['backtest_count']}회 실행")
        except Exception as e:
            logging.error(f"상태 로드 실패: {e}")
    
    def _save_state(self):
        """현재 상태 저장"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        adjustment_history = self.state['adjustment_history'][-5:] if self.state['adjustment_history'] else []
        performance_history = self.state['performance_history'][-5:] if self.state['performance_history'] else []

        return {
            'current_threshold': self.state['current_threshold'],
            'last_performance': self.state['last_performance_score'],
            'backtest_count': self.state['backtest_count'],
            'last_backtest_round': self.state.get('last_backtest_round'),
            'mode': self._get_mode_description(self.state['current_threshold']),
            'history': adjustment_history,
            'performance_history': performance_history
        }
    
    def check_and_adjust(self) -> Dict[str, Any]:
        """
        백테스팅 결과 기반으로 임계값을 점검하고 조정

        Returns:
            Dict[str, Any]: 조정 실행 결과와 백테스트 성능
        """
        backtest_result = self._run_backtest_performance()
        fallback_used = False

        if backtest_result:
            performance_score = backtest_result['performance_score']
            self.state['last_backtest_round'] = backtest_result.get('end_round')

            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'round': backtest_result.get('end_round'),
                'performance_score': performance_score
            }
            self.state['performance_history'].append(history_entry)
            if len(self.state['performance_history']) > 20:
                self.state['performance_history'] = self.state['performance_history'][-20:]
        else:
            fallback_used = True
            logging.warning("[Auto Adjustment V2] Backtest unavailable; using last known performance score.")
            performance_score = max(0.0, min(1.0, self.state.get('last_performance_score', 0.0)))

        adjustment_result = self.analyze_and_adjust(performance_score)

        report = {
            'adjusted': adjustment_result.get('adjusted', False),
            'message': adjustment_result.get('message', ''),
            'backtest_performance': {
                'backtest_count': self.state['backtest_count'],
                'performance_score': performance_score,
                'threshold': self.state['current_threshold'],
                'fallback_used': fallback_used
            }
        }

        if backtest_result:
            report['backtest_performance']['start_round'] = backtest_result.get('start_round')
            report['backtest_performance']['end_round'] = backtest_result.get('end_round')
            report['backtest_performance']['metrics'] = backtest_result.get('metrics')

        return report
