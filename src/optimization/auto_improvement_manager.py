#!/usr/bin/env python3
"""
자동 개선 시스템 통합 관리자
프로그램 재시작 시에도 상태를 유지하는 영구적인 개선 시스템
"""
import logging
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np
from pathlib import Path

class AutoImprovementManager:
    """자동 개선 시스템 통합 관리자"""
    
    def __init__(self, state_file: str = "data/auto_improvement_state.json"):
        """
        Args:
            state_file: 상태 저장 파일 경로
        """
        self.state_file = state_file
        self.state = self._load_state()
        
        # 기본 설정값 정의
        default_config = {
            'backtest_window_size': 100,
            'min_improvement_rate': 0.001,  # 0.1% 이상 개선 시에도 업데이트 (로또는 미세한 개선도 중요)
            'max_iterations_per_session': 10,
            'performance_threshold': 1.5,   # 목표 성능
            'auto_save_interval': 1,        # 매 반복마다 저장
        }
        
        # 상태에서 config 불러오고 누락된 키는 기본값으로 채우기
        self.config = self.state.get('config', {})
        for key, value in default_config.items():
            if key not in self.config:
                self.config[key] = value
        
        # 상태에 config 업데이트
        self.state['config'] = self.config
        
        logging.info(f"자동 개선 관리자 초기화 완료. 총 백테스팅 횟수: {self.state['total_backtest_count']}")
        
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
    
    def _create_new_state(self) -> Dict[str, Any]:
        """새로운 상태 생성"""
        return {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'total_backtest_count': 0,
            'improvement_history': [],
            'best_models': {
                'lstm': {'params': {}, 'performance': 0.0},
                'ensemble': {'params': {}, 'performance': 0.0},
                'monte_carlo': {'params': {}, 'performance': 0.0}
            },
            'current_performance': {
                'lstm': 0.0,
                'ensemble': 0.0,
                'monte_carlo': 0.0,
                'overall': 0.0
            },
            'config': {},
            'filter_settings': {
                'sum_range': {'min': 100, 'max': 170},
                'odd_even_ratio': {'min_odd': 2, 'max_odd': 4},
                'consecutive_numbers': {'max_consecutive': 2},
                'section_distribution': {'min_sections': 3},
                'prime_composite_ratio': {'min_prime': 1, 'max_prime': 4}
            }
        }
    
    def save_state(self):
        """현재 상태 저장"""
        try:
            # 디렉토리 생성
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            # 상태 업데이트
            self.state['last_updated'] = datetime.now().isoformat()
            # config 확실히 포함
            self.state['config'] = self.config
            
            # 현재 백테스팅 카운트 로깅
            logging.info(f"상태 저장 시작 - 총 백테스팅 횟수: {self.state['total_backtest_count']}")
            
            # 파일 저장
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            
            logging.info(f"상태 저장 완료: {self.state_file} (백테스팅 횟수: {self.state['total_backtest_count']})")
        except Exception as e:
            logging.error(f"상태 저장 실패: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def track_backtest(self, backtest_results: Dict[str, Any]) -> Dict[str, Any]:
        """백테스팅 결과 추적 및 개선 여부 판단
        
        Args:
            backtest_results: 백테스팅 결과
            
        Returns:
            Dict: 개선 정보 및 업데이트 여부
        """
        # 백테스팅 횟수 증가
        old_count = self.state['total_backtest_count']
        self.state['total_backtest_count'] += 1
        logging.info(f"백테스팅 횟수 증가: {old_count} → {self.state['total_backtest_count']}")
        
        # 성능 추출
        new_performance = self._extract_performance(backtest_results)
        old_performance = self.state['current_performance'].copy()
        
        # 개선 여부 판단
        improvement_info = {
            'backtest_number': self.state['total_backtest_count'],
            'timestamp': datetime.now().isoformat(),
            'old_performance': old_performance,
            'new_performance': new_performance,
            'improvements': {},
            'should_update': False,
            'update_reasons': []
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
                'improved': improvement_rate > self.config.get('min_improvement_rate', 0.05)
            }
            
            # 개선된 경우 최고 성능 업데이트
            if new_perf > self.state['best_models'][model_type]['performance']:
                self.state['best_models'][model_type]['performance'] = new_perf
                improvement_info['update_reasons'].append(f"{model_type} 최고 성능 갱신")
        
        # 전체 성능 개선 확인
        old_overall = old_performance.get('overall', 0.0)
        new_overall = new_performance.get('overall', 0.0)
        
        if old_overall > 0:
            overall_improvement = (new_overall - old_overall) / old_overall
        else:
            overall_improvement = 1.0 if new_overall > 0 else 0.0
        
        # 업데이트 여부 결정
        if overall_improvement > self.config.get('min_improvement_rate', 0.05):
            improvement_info['should_update'] = True
            improvement_info['update_reasons'].append("전체 성능 개선")
            self.state['current_performance'] = new_performance
        
        # 개선 이력 추가
        self.state['improvement_history'].append(improvement_info)
        
        # 이력 크기 제한 (최근 100개만 유지)
        if len(self.state['improvement_history']) > 100:
            self.state['improvement_history'] = self.state['improvement_history'][-100:]
        
        # 자동 저장
        if self.state['total_backtest_count'] % self.config['auto_save_interval'] == 0:
            self.save_state()
        
        return improvement_info
    
    def update_model_params(self, model_type: str, params: Dict[str, Any]):
        """모델 파라미터 업데이트 (개선된 경우에만)
        
        Args:
            model_type: 모델 유형
            params: 새로운 파라미터
        """
        if model_type in self.state['best_models']:
            self.state['best_models'][model_type]['params'] = params
            logging.info(f"{model_type} 모델 파라미터 업데이트 완료")
    
    def update_filter_settings(self, new_settings: Dict[str, Any]) -> bool:
        """필터 설정 업데이트 (개선된 경우에만)
        
        Args:
            new_settings: 새로운 필터 설정
            
        Returns:
            bool: 업데이트 여부
        """
        # 현재 설정과 비교
        if new_settings != self.state['filter_settings']:
            self.state['filter_settings'] = new_settings
            logging.info("필터 설정 업데이트 완료")
            return True
        return False
    
    def get_best_params(self, model_type: str) -> Dict[str, Any]:
        """최고 성능 모델 파라미터 반환
        
        Args:
            model_type: 모델 유형
            
        Returns:
            Dict: 최고 성능 파라미터
        """
        return self.state['best_models'].get(model_type, {}).get('params', {})
    
    def get_current_filter_settings(self) -> Dict[str, Any]:
        """현재 필터 설정 반환"""
        return self.state['filter_settings'].copy()
    
    def _extract_performance(self, backtest_results: Dict[str, Any]) -> Dict[str, float]:
        """백테스팅 결과에서 성능 추출"""
        performance = {
            'lstm': 0.0,
            'ensemble': 0.0,
            'monte_carlo': 0.0,
            'overall': 0.0
        }
        
        metrics = backtest_results.get('performance_metrics', {})
        model_performance = metrics.get('model_performance', {})
        
        # 각 모델 성능 추출
        for model_type in ['lstm', 'ensemble', 'monte_carlo']:
            model_metrics = model_performance.get(model_type, {})
            performance[model_type] = model_metrics.get('avg_matches', 0.0)
        
        # 전체 성능 계산 (가중 평균)
        performance['overall'] = (
            performance['lstm'] * 0.25 +
            performance['ensemble'] * 0.5 +
            performance['monte_carlo'] * 0.25
        )
        
        return performance
    
    def get_status_report(self) -> str:
        """현재 상태 보고서 생성"""
        report = []
        report.append("\n" + "="*60)
        report.append("🤖 자동 개선 시스템 상태 보고서")
        report.append("="*60)
        
        # 기본 정보
        report.append(f"\n📊 총 백테스팅 횟수: {self.state['total_backtest_count']}회")
        report.append(f"📅 시스템 생성일: {self.state['created_at']}")
        report.append(f"🔄 마지막 업데이트: {self.state['last_updated']}")
        
        # 현재 성능
        report.append("\n📈 현재 성능:")
        perf = self.state['current_performance']
        report.append(f"  • LSTM: {perf['lstm']:.3f}")
        report.append(f"  • Ensemble: {perf['ensemble']:.3f}")
        report.append(f"  • Monte Carlo: {perf['monte_carlo']:.3f}")
        report.append(f"  • 전체: {perf['overall']:.3f}")
        
        # 최고 성능
        report.append("\n🏆 최고 성능:")
        for model_type, info in self.state['best_models'].items():
            report.append(f"  • {model_type}: {info['performance']:.3f}")
        
        # 최근 개선 이력
        if self.state['improvement_history']:
            report.append("\n📊 최근 개선 이력:")
            recent = self.state['improvement_history'][-5:]  # 최근 5개
            for hist in recent:
                report.append(f"\n  [{hist['backtest_number']}회차] {hist['timestamp'][:19]}")
                if hist['should_update']:
                    report.append(f"    ✅ 업데이트: {', '.join(hist['update_reasons'])}")
                else:
                    report.append("    ❌ 개선 없음")
                
                for model, imp in hist['improvements'].items():
                    if imp['improved']:
                        report.append(f"    • {model}: +{imp['rate']*100:.1f}% ({imp['absolute']:+.3f})")
        
        # 설정값
        report.append("\n⚙️ 현재 설정:")
        report.append(f"  • 최소 개선율: {self.config.get('min_improvement_rate', 0.05)*100:.1f}%")
        report.append(f"  • 목표 성능: {self.config['performance_threshold']:.2f}")
        
        report.append("\n" + "="*60)
        
        return "\n".join(report)
    
    def should_continue_improvement(self) -> bool:
        """개선을 계속해야 하는지 판단"""
        # 목표 성능 달성 확인
        current_overall = self.state['current_performance']['overall']
        if current_overall >= self.config['performance_threshold']:
            logging.info("목표 성능 달성! 개선 프로세스 완료.")
            return False
        
        # 최근 개선 이력 확인 (최근 5회)
        if len(self.state['improvement_history']) >= 5:
            recent_improvements = self.state['improvement_history'][-5:]
            improved_count = sum(1 for h in recent_improvements if h['should_update'])
            
            if improved_count == 0:
                logging.info("최근 5회 백테스팅에서 개선 없음. 개선 프로세스 중단.")
                return False
        
        return True
    
    def reset_session_counter(self):
        """세션 카운터 리셋 (새로운 개선 사이클 시작)"""
        self.state['session_backtest_count'] = 0
        logging.info("새로운 개선 세션 시작")