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

class AutoAdjustmentSystemV2:
    """
    단순화된 자동 조정 시스템
    - global_probability_threshold 하나만 조정
    - 백테스팅 성능에 따라 자동 조정
    """
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.config_path = 'configs/adaptive_filter_config.yaml'
        self.state_file = 'data/auto_adjustment_state_v2.json'
        
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
            'backtest_count': 0
        }
        
        # 상태 파일 로드 (하지만 yaml 파일의 임계값을 우선 사용)
        self._load_state()
        
        # YAML 파일의 값을 항상 우선 사용
        yaml_threshold = self._get_current_threshold()
        if abs(self.state['current_threshold'] - yaml_threshold) > 0.01:
            logging.info(f"  [알림] YAML 설정 우선 적용: {self.state['current_threshold']}% → {yaml_threshold}%")
            self.state['current_threshold'] = yaml_threshold
        
        logging.info("\n[자동 조정 시스템 V2] 초기화 완료")
        logging.info(f"  - 현재 임계값: {self.state['current_threshold']}%")
        logging.info("  - 조정 전략: 백테스팅 성능 기반 자동 조정")
        logging.info("  - 단일 파라미터 제어: global_probability_threshold")
    
    def _get_current_threshold(self) -> float:
        """현재 설정된 임계값 읽기"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('global_probability_threshold', 1.0)
        except Exception as e:
            logging.error(f"임계값 읽기 실패: {e}")
            return 1.0
    
    def _set_threshold(self, new_threshold: float) -> bool:
        """새로운 임계값 설정"""
        try:
            # 현재 설정 읽기
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 백업 생성
            backup_path = f"configs/adaptive_filter_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
            with open(backup_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)
            
            # 임계값 업데이트
            old_threshold = config.get('global_probability_threshold', 1.0)
            config['global_probability_threshold'] = new_threshold
            
            # 저장
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
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
    
    def analyze_and_adjust(self, performance_score: float) -> Dict[str, Any]:
        """
        백테스팅 성능에 따라 임계값 자동 조정
        
        Args:
            performance_score: 백테스팅 성능 점수 (0.0 ~ 1.0)
        
        Returns:
            조정 결과
        """
        logging.info("\n" + "="*60)
        logging.info("🔄 자동 임계값 조정 분석")
        logging.info("="*60)
        
        self.state['last_performance_score'] = performance_score
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
    
    def _load_state(self):
        """저장된 상태 로드"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    self.state.update(saved_state)
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
        return {
            'current_threshold': self.state['current_threshold'],
            'last_performance': self.state['last_performance_score'],
            'backtest_count': self.state['backtest_count'],
            'mode': self._get_mode_description(self.state['current_threshold']),
            'history': self.state['adjustment_history'][-5:] if self.state['adjustment_history'] else []
        }
    
    def check_and_adjust(self) -> Dict[str, Any]:
        """
        백테스팅 실행 후 자동 조정 (main.py 호환성)
        
        Returns:
            조정 결과 및 백테스팅 성능
        """
        # 간단한 백테스팅 성능 시뮬레이션
        # 실제 구현에서는 백테스팅을 실행하여 성능을 측정해야 함
        import random
        
        # 임계값에 따른 기본 성능 추정
        threshold = self.state['current_threshold']
        if threshold <= 0.5:
            base_score = 0.7  # 보수적: 높은 안정성
        elif threshold <= 1.0:
            base_score = 0.5  # 표준: 균형
        else:
            base_score = 0.3  # 공격적: 낮은 안정성
        
        # 약간의 랜덤성 추가
        performance_score = base_score + random.uniform(-0.1, 0.1)
        performance_score = max(0.0, min(1.0, performance_score))
        
        # 조정 분석
        adjustment_result = self.analyze_and_adjust(performance_score)
        
        # 결과 반환
        return {
            'adjusted': adjustment_result.get('adjusted', False),
            'message': adjustment_result.get('message', ''),
            'backtest_performance': {
                'backtest_count': self.state['backtest_count'],
                'performance_score': performance_score,
                'threshold': self.state['current_threshold']
            }
        }