#!/usr/bin/env python3
"""
필터 자동 조정 시스템
FilterValidator의 제안을 실제로 적용하는 시스템
"""

import logging
import json
import yaml
import os
from typing import Dict, Any, List
from datetime import datetime
import shutil

class FilterAutoAdjuster:
    """필터 자동 조정 시스템"""
    
    def __init__(self, db_manager, filter_manager):
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        self.config_path = "config.yaml"
        self.adaptive_config_path = "configs/adaptive_filter_config.yaml"
        self.adjustment_history = []
        self.last_adjustment = None
        
    def apply_optimized_criteria(self, optimized_criteria: Dict, validation_results) -> bool:
        """FilterValidator의 최적화 제안을 실제로 적용
        
        Args:
            optimized_criteria: 최적화된 필터 기준
            validation_results: 검증 결과
            
        Returns:
            bool: 적용 성공 여부
        """
        if not optimized_criteria:
            logging.info("적용할 최적화 기준이 없습니다.")
            return False
            
        logging.info("\n" + "="*60)
        logging.info("🔧 필터 자동 조정 시스템 작동")
        logging.info("="*60)
        
        # 현재 설정 백업
        self._backup_configs()
        
        applied_count = 0
        adjustments = []
        
        # validation_results를 딕셔너리 형식으로 변환
        if isinstance(validation_results, list):
            # 리스트에서 필터별 통과율 계산
            total_rounds = len(validation_results) if validation_results else 0
            filter_results = {}
            
            if total_rounds > 0:
                # 각 필터별 실패 횟수 집계
                filter_fails = {}
                for result in validation_results:
                    for failed_filter in result.get('failed_filters', []):
                        filter_name = failed_filter.get('name', 'unknown')
                        filter_fails[filter_name] = filter_fails.get(filter_name, 0) + 1
                
                # 필터별 통과율 계산
                for filter_name, fail_count in filter_fails.items():
                    pass_rate = ((total_rounds - fail_count) / total_rounds) * 100
                    filter_results[filter_name] = {'pass_rate': pass_rate}
                    
            validation_results = {'filter_results': filter_results}
        
        # 각 필터별로 조정이 필요한지 확인
        for filter_name, filter_result in validation_results.get('filter_results', {}).items():
            pass_rate = filter_result['pass_rate']
            
            # 통과율이 낮은 필터만 조정 (< 85%)
            if pass_rate < 85:
                logging.warning(f"\n[{filter_name}] 필터 조정 필요")
                logging.warning(f"  현재 통과율: {pass_rate:.2f}%")
                
                # 필터별 조정 적용
                if self._adjust_filter(filter_name, pass_rate, optimized_criteria.get(filter_name, {})):
                    applied_count += 1
                    adjustments.append({
                        'filter': filter_name,
                        'old_pass_rate': pass_rate,
                        'target_pass_rate': 95,
                        'timestamp': datetime.now().isoformat()
                    })
                    logging.info(f"  ✅ {filter_name} 필터 조정 완료")
                else:
                    logging.error(f"  ❌ {filter_name} 필터 조정 실패")
        
        # 조정 이력 저장
        if adjustments:
            self.adjustment_history.extend(adjustments)
            self._save_adjustment_history()
            
            # 설정 파일 저장
            self._save_configs()
            
            logging.info(f"\n📊 총 {applied_count}개 필터 조정 완료")
            logging.info("다음 실행부터 새로운 필터 기준이 적용됩니다.")
            
            # 필터 매니저 리로드 권장
            logging.info("\n⚠️ 필터 설정이 변경되었습니다. 프로그램을 재시작하거나 필터를 다시 로드하세요.")
            
            return True
        else:
            logging.info("조정이 필요한 필터가 없습니다.")
            return False
    
    def _adjust_filter(self, filter_name: str, current_pass_rate: float, optimization_hints: Dict) -> bool:
        """개별 필터 조정
        
        Args:
            filter_name: 필터 이름
            current_pass_rate: 현재 통과율
            optimization_hints: 최적화 힌트
            
        Returns:
            bool: 조정 성공 여부
        """
        try:
            # 조정 비율 계산 (목표: 95%)
            adjustment_ratio = 95.0 / max(current_pass_rate, 1.0)
            
            # config.yaml 로드
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 필터별 조정 로직
            if filter_name == 'multiple':
                # multiple 필터 조정
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'multiple' in config['filters']['criteria']:
                        # global_threshold 완화
                        old_threshold = config['filters']['criteria']['multiple'].get('global_threshold', 1.5)
                        new_threshold = min(old_threshold * adjustment_ratio, 3.0)  # 최대 3.0
                        config['filters']['criteria']['multiple']['global_threshold'] = round(new_threshold, 2)
                        logging.info(f"    multiple.global_threshold: {old_threshold} → {new_threshold:.2f}")
            
            elif filter_name == 'consecutive':
                # consecutive 필터 조정
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'consecutive' in config['filters']['criteria']:
                        old_max = config['filters']['criteria']['consecutive'].get('max_consecutive', 2)
                        new_max = min(old_max + 1, 4)  # 최대 4개까지 허용
                        config['filters']['criteria']['consecutive']['max_consecutive'] = new_max
                        logging.info(f"    consecutive.max_consecutive: {old_max} → {new_max}")
            
            elif filter_name == 'sum_range':
                # sum_range 필터 조정
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'sum_range' in config['filters']['criteria']:
                        # 범위 확장
                        old_min = config['filters']['criteria']['sum_range'].get('min_sum', 90)
                        old_max = config['filters']['criteria']['sum_range'].get('max_sum', 190)
                        margin = int(5 * adjustment_ratio)
                        new_min = max(21, old_min - margin)
                        new_max = min(255, old_max + margin)
                        config['filters']['criteria']['sum_range']['min_sum'] = new_min
                        config['filters']['criteria']['sum_range']['max_sum'] = new_max
                        logging.info(f"    sum_range: [{old_min}, {old_max}] → [{new_min}, {new_max}]")
            
            elif filter_name == 'prime_composite':
                # prime_composite 필터 조정
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'prime_composite' in config['filters']['criteria']:
                        # 허용 범위 확장
                        old_min = config['filters']['criteria']['prime_composite'].get('min_allowed', 1)
                        old_max = config['filters']['criteria']['prime_composite'].get('max_allowed', 4)
                        new_min = max(0, old_min - 1)
                        new_max = min(6, old_max + 1)
                        config['filters']['criteria']['prime_composite']['min_allowed'] = new_min
                        config['filters']['criteria']['prime_composite']['max_allowed'] = new_max
                        logging.info(f"    prime_composite: [{old_min}, {old_max}] → [{new_min}, {new_max}]")
            
            elif filter_name == 'fixed_step':
                # fixed_step 필터 조정
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'fixed_step' in config['filters']['criteria']:
                        # required_matches 완화
                        for step_type in ['all_steps', 'four_steps', 'partial_steps', 'three_steps']:
                            if step_type in config['filters']['criteria']['fixed_step']:
                                old_req = config['filters']['criteria']['fixed_step'][step_type].get('required_matches', 4)
                                new_req = max(2, old_req - 1)  # 최소 2
                                config['filters']['criteria']['fixed_step'][step_type]['required_matches'] = new_req
                                logging.info(f"    fixed_step.{step_type}.required_matches: {old_req} → {new_req}")
            
            # 임시 config 저장
            self._temp_config = config
            return True
            
        except Exception as e:
            logging.error(f"필터 조정 중 오류: {e}")
            return False
    
    def _backup_configs(self):
        """설정 파일 백업"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # config.yaml 백업
        if os.path.exists(self.config_path):
            backup_path = f"configs/backup/config_backup_{timestamp}.yaml"
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy(self.config_path, backup_path)
            logging.info(f"설정 백업: {backup_path}")
    
    def _save_configs(self):
        """수정된 설정 저장"""
        if hasattr(self, '_temp_config'):
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._temp_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            logging.info(f"설정 저장 완료: {self.config_path}")
    
    def _save_adjustment_history(self):
        """조정 이력 저장"""
        history_path = "data/filter_adjustment_history.json"
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        
        try:
            # 기존 이력 로드
            if os.path.exists(history_path):
                with open(history_path, 'r', encoding='utf-8') as f:
                    all_history = json.load(f)
            else:
                all_history = []
            
            # 새 이력 추가
            all_history.extend(self.adjustment_history)
            
            # 최근 100개만 유지
            all_history = all_history[-100:]
            
            # 저장
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(all_history, f, ensure_ascii=False, indent=2)
            
            logging.info(f"조정 이력 저장: {history_path}")
            
        except Exception as e:
            logging.error(f"조정 이력 저장 실패: {e}")
    
    def check_need_adjustment(self, validation_results) -> bool:
        """조정이 필요한지 확인
        
        Args:
            validation_results: 검증 결과 (리스트 또는 딕셔너리)
            
        Returns:
            bool: 조정 필요 여부
        """
        # validation_results가 리스트인 경우 처리
        if isinstance(validation_results, list):
            if not validation_results:
                return False
                
            # 리스트에서 통과율 계산
            total_rounds = len(validation_results)
            passed_rounds = sum(1 for r in validation_results if r.get('passed_all_filters', True))
            overall_pass_rate = (passed_rounds / total_rounds) * 100 if total_rounds > 0 else 100
            
            # 전체 통과율이 85% 미만이면 조정 필요
            if overall_pass_rate < 85:
                return True
            
            # 각 필터별 통과율 계산
            filter_stats = {}
            for result in validation_results:
                for failed_filter in result.get('failed_filters', []):
                    filter_name = failed_filter.get('name', 'unknown')
                    if filter_name not in filter_stats:
                        filter_stats[filter_name] = {'failed': 0, 'total': total_rounds}
                    filter_stats[filter_name]['failed'] += 1
            
            # 개별 필터 중 하나라도 80% 미만이면 조정 필요
            for filter_name, stats in filter_stats.items():
                pass_rate = ((stats['total'] - stats['failed']) / stats['total']) * 100
                if pass_rate < 80:
                    return True
                    
        # validation_results가 딕셔너리인 경우 (기존 코드)
        elif isinstance(validation_results, dict):
            # 전체 통과율이 85% 미만이면 조정 필요
            if validation_results.get('overall_pass_rate', 100) < 85:
                return True
            
            # 개별 필터 중 하나라도 80% 미만이면 조정 필요
            for filter_name, filter_result in validation_results.get('filter_results', {}).items():
                if filter_result.get('pass_rate', 100) < 80:
                    return True
        
        return False
    
    def get_adjustment_summary(self) -> str:
        """조정 요약 정보"""
        if not self.adjustment_history:
            return "조정 이력이 없습니다."
        
        summary = "\n📊 필터 자동 조정 이력\n"
        summary += "="*40 + "\n"
        
        # 최근 5개 조정 이력
        recent = self.adjustment_history[-5:]
        for adj in recent:
            summary += f"• {adj['filter']}: {adj['old_pass_rate']:.1f}% → {adj['target_pass_rate']}%\n"
            summary += f"  시간: {adj['timestamp']}\n"
        
        return summary