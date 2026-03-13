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
        self._temp_config = None
        self._temp_adaptive_config = None

        # ✅ NEW: PerformanceTracker 인스턴스 (필터 스냅샷 저장용)
        try:
            from .continuous_improvement_engine import PerformanceTracker
            self.performance_tracker = PerformanceTracker()
        except ImportError:
            self.performance_tracker = None
            logging.warning("PerformanceTracker를 로드할 수 없습니다. 필터 스냅샷 저장 기능이 비활성화됩니다.")
        
    def apply_optimized_criteria(self, optimized_criteria: Dict, validation_results) -> bool:
        """FilterValidator의 최적화 제안을 실제로 적용
        
        Args:
            optimized_criteria: 최적화된 필터 기준
            validation_results: 검증 결과
            
        Returns:
            bool: 적용 성공 여부
        """
        if not optimized_criteria:
            logging.info("적용할 최적화 기준이 없습니다. 현재 설정이 적절합니다.")
            return True  # False 대신 True 반환 - 조정이 필요 없는 것도 성공으로 처리
            
        logging.info("\n" + "="*60)
        logging.info("🔧 필터 자동 조정 시스템 작동")
        logging.info("="*60)
        logging.info("📋 조정 대상 분석 중...")

        # 전체 통과율 정보 표시
        if isinstance(validation_results, dict):
            overall_rate = validation_results.get('overall_pass_rate', 100)
            logging.info(f"   전체 필터 통과율: {overall_rate:.1f}%")
            logging.info(f"   목표 통과율: 95.0%")
            if overall_rate < 85:
                logging.warning(f"   🚨 위험: 통과율이 85% 미만입니다!")
            elif overall_rate < 90:
                logging.warning(f"   ⚠️ 주의: 통과율이 90% 미만입니다!")
        
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
        logging.info("\n📊 필터별 통과율 분석:")

        # 필터 통과율 정렬 (낮은 순서대로)
        filter_pass_rates = []
        for filter_name, filter_result in validation_results.get('filter_results', {}).items():
            pass_rate = filter_result['pass_rate']
            status_icon = "✅" if pass_rate >= 90 else "⚠️" if pass_rate >= 85 else "🚨"
            logging.info(f"   {status_icon} {filter_name}: {pass_rate:.1f}%")
            filter_pass_rates.append((filter_name, pass_rate))

        # 통과율 기준 오름차순 정렬 (가장 낮은 통과율 먼저)
        filter_pass_rates.sort(key=lambda x: x[1])

        # 전체 통과율 확인
        overall_pass_rate = validation_results.get('overall_pass_rate', 100)

        # 🔥 FIX: 전체 통과율이 85% 미만이면 개별 통과율 85% 이상이라도 가장 낮은 3개 필터 조정
        filters_to_adjust = []

        for filter_name, pass_rate in filter_pass_rates:
            # 개별 필터 통과율 < 85%이면 무조건 조정
            if pass_rate < 85:
                filters_to_adjust.append((filter_name, pass_rate))
            # 전체 통과율 < 85%이고, 개별 필터 통과율 < 96%이면 조정 대상 추가
            elif overall_pass_rate < 85 and pass_rate < 96:
                filters_to_adjust.append((filter_name, pass_rate))

        # 최소 3개 필터 조정 보장 (전체 통과율이 85% 미만일 때)
        if overall_pass_rate < 85 and len(filters_to_adjust) < 3:
            for filter_name, pass_rate in filter_pass_rates:
                if (filter_name, pass_rate) not in filters_to_adjust:
                    filters_to_adjust.append((filter_name, pass_rate))
                    if len(filters_to_adjust) >= 3:
                        break

        if filters_to_adjust:
            logging.info(f"\n🎯 조정 대상 필터 ({len(filters_to_adjust)}개):")
            for filter_name, pass_rate in filters_to_adjust:
                logging.info(f"   - {filter_name}: {pass_rate:.1f}%")

        for filter_name, pass_rate in filters_to_adjust:
            logging.warning(f"🔧 [{filter_name}] 필터 조정 시작")
            logging.info(f"     현재 통과율: {pass_rate:.2f}%")
            logging.info(f"     목표 통과율: 95.0%")
            logging.info(f"     조정 필요도: {95.0 - pass_rate:.1f}%p 향상 필요")

            # 필터별 조정 적용
            if self._adjust_filter(filter_name, pass_rate, optimized_criteria.get(filter_name, {})):
                applied_count += 1
                adjustments.append({
                    'filter': filter_name,
                    'old_pass_rate': pass_rate,
                    'target_pass_rate': 95,
                    'timestamp': datetime.now().isoformat()
                })
                logging.info(f"     ✅ {filter_name} 필터 조정 완료")
            else:
                logging.error(f"     ❌ {filter_name} 필터 조정 실패")
        
        # 조정 이력 저장
        if adjustments:
            self.adjustment_history.extend(adjustments)
            self._save_adjustment_history()

            # 설정 파일 저장
            self._save_configs()

            # ✅ FIX: 싱글톤 FilterManager 초기화하여 다음 사이클에서 새 설정 적용
            try:
                from .filter_manager import FilterManager
                FilterManager.reset_instance()
                logging.info("✅ FilterManager 싱글톤 초기화 완료 - 다음 사이클에서 새 설정이 적용됩니다.")
            except Exception as e:
                logging.warning(f"FilterManager 초기화 실패: {e}")

            # ✅ NEW: 필터 조건 스냅샷 저장 (롤백 지원)
            if self.performance_tracker:
                try:
                    self._save_filter_snapshot(validation_results)
                except Exception as e:
                    logging.error(f"필터 스냅샷 저장 실패: {e}")

            # 조정 결과 요약
            logging.info("\n" + "="*50)
            logging.info("📊 필터 자동 조정 완료 요약")
            logging.info("="*50)
            logging.info(f"🎯 조정된 필터 수: {applied_count}개")

            for adj in adjustments:
                improvement = 95.0 - adj['old_pass_rate']
                logging.info(f"   • {adj['filter']}: {adj['old_pass_rate']:.1f}% → {adj['target_pass_rate']}% (예상 개선: +{improvement:.1f}%p)")

            logging.info(f"\n💾 설정 파일 업데이트:")
            logging.info(f"   • config.yaml")
            logging.info(f"   • configs/adaptive_filter_config.yaml")
            logging.info(f"   • 백업 파일 생성됨")

            logging.info(f"\n🔄 적용 안내:")
            logging.info(f"   다음 실행부터 새로운 필터 기준이 적용됩니다.")
            logging.info(f"   변경사항을 즉시 적용하려면 프로그램을 재시작하세요.")

            return True
        else:
            logging.info("\n✅ 모든 필터가 정상 범위(85% 이상) 내에 있습니다.")
            logging.info("조정이 필요한 필터가 없습니다.")
            return True  # False 대신 True 반환 - 조정이 필요 없는 것도 성공으로 처리
    
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

            # adaptive_filter_config.yaml 로드
            with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                adaptive_config = yaml.safe_load(f)

            # 필터별 조정 로직
            if filter_name == 'match':
                # match 필터 조정 - CRITICAL FIX!
                if 'dynamic_criteria' in adaptive_config and 'match' in adaptive_config['dynamic_criteria']:
                    old_max_match = adaptive_config['dynamic_criteria']['match'].get('max_match', 3)
                    # 통과율이 낮으면 max_match를 증가 (더 많은 매칭 허용)
                    new_max_match = min(old_max_match + 1, 6)  # 최대 6까지 허용
                    adaptive_config['dynamic_criteria']['match']['max_match'] = new_max_match
                    logging.info(f"       📝 adaptive_config.yaml - match.max_match: {old_max_match} → {new_max_match}")
                else:
                    # dynamic_criteria에 match가 없으면 추가
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['match'] = {'max_match': 4}
                    logging.info(f"       📝 adaptive_config.yaml - match 설정 추가: max_match=4")

            elif filter_name == 'multiple':
                # multiple 필터 조정 (config.yaml)
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'multiple' in config['filters']['criteria']:
                        # global_threshold 완화
                        old_threshold = config['filters']['criteria']['multiple'].get('global_threshold', 1.5)
                        new_threshold = min(old_threshold * adjustment_ratio, 3.0)  # 최대 3.0
                        config['filters']['criteria']['multiple']['global_threshold'] = round(new_threshold, 2)
                        logging.info(f"       📝 config.yaml - multiple.global_threshold: {old_threshold} → {new_threshold:.2f}")

                # adaptive_filter_config.yaml도 조정
                if 'dynamic_criteria' in adaptive_config and 'multiple' in adaptive_config['dynamic_criteria']:
                    # 허용 범위 확장
                    for key in adaptive_config['dynamic_criteria']['multiple']:
                        current_range = adaptive_config['dynamic_criteria']['multiple'][key]
                        if isinstance(current_range, list) and len(current_range) == 2:
                            # 범위를 약간 확장
                            adaptive_config['dynamic_criteria']['multiple'][key][1] = min(6, current_range[1] + 1)
                            logging.info(f"       📝 adaptive_config.yaml - multiple.{key}: {current_range} → {adaptive_config['dynamic_criteria']['multiple'][key]}")
            
            elif filter_name == 'consecutive':
                # consecutive 필터 조정 (config.yaml)
                if 'filters' in config and 'criteria' in config['filters']:
                    if 'consecutive' in config['filters']['criteria']:
                        old_max = config['filters']['criteria']['consecutive'].get('max_consecutive', 2)
                        new_max = min(old_max + 1, 4)  # 최대 4개까지 허용
                        config['filters']['criteria']['consecutive']['max_consecutive'] = new_max
                        logging.info(f"       📝 config.yaml - consecutive.max_consecutive: {old_max} → {new_max}")

                # adaptive_filter_config.yaml도 조정
                if 'dynamic_criteria' in adaptive_config and 'consecutive' in adaptive_config['dynamic_criteria']:
                    old_max = adaptive_config['dynamic_criteria']['consecutive'].get('max_consecutive', 3)
                    new_max = min(old_max + 1, 5)  # 최대 5개까지 허용
                    adaptive_config['dynamic_criteria']['consecutive']['max_consecutive'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - consecutive.max_consecutive: {old_max} → {new_max}")
            
            elif filter_name == 'sum_range':
                # sum_range 필터 조정 (config.yaml)
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
                        logging.info(f"       📝 config.yaml - sum_range: [{old_min}, {old_max}] → [{new_min}, {new_max}]")

                # adaptive_filter_config.yaml도 조정
                if 'dynamic_criteria' in adaptive_config and 'sum_range' in adaptive_config['dynamic_criteria']:
                    old_min = adaptive_config['dynamic_criteria']['sum_range'].get('min_sum', 50)
                    old_max = adaptive_config['dynamic_criteria']['sum_range'].get('max_sum', 230)
                    margin = int(10 * adjustment_ratio)
                    new_min = max(21, old_min - margin)
                    new_max = min(255, old_max + margin)
                    adaptive_config['dynamic_criteria']['sum_range']['min_sum'] = new_min
                    adaptive_config['dynamic_criteria']['sum_range']['max_sum'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - sum_range: [{old_min}, {old_max}] → [{new_min}, {new_max}]")
            
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
                # fixed_step 필터 조정 - adaptive_config.yaml 사용 (FIXED: 올바른 경로로 수정)
                if 'dynamic_criteria' in adaptive_config and 'fixed_step' in adaptive_config['dynamic_criteria']:
                    fixed_step_config = adaptive_config['dynamic_criteria']['fixed_step']
                    adjusted = False
                    for step_type in ['all_steps', 'partial_steps', 'four_steps', 'three_steps']:
                        if step_type in fixed_step_config:
                            old_req = fixed_step_config[step_type].get('required_matches', 4)
                            new_req = max(2, old_req - 1)  # 최소 2
                            if new_req != old_req:
                                fixed_step_config[step_type]['required_matches'] = new_req
                                logging.info(f"       📝 adaptive_config.yaml - fixed_step.{step_type}.required_matches: {old_req} → {new_req}")
                                adjusted = True
                    if not adjusted:
                        logging.info(f"       ✅ fixed_step 필터: 이미 최소 매칭 수에 도달 (required_matches=2)")

            elif filter_name == 'ten_section':
                # ten_section 필터 조정 (excluded list에서 값 제거로 통과율 향상)
                if 'dynamic_criteria' in adaptive_config and 'ten_section' in adaptive_config['dynamic_criteria']:
                    # 각 구간의 제외 리스트에서 값을 제거하여 더 많은 조합 허용
                    for section in ['section1', 'section2', 'section3', 'section4', 'section5']:
                        if section in adaptive_config['dynamic_criteria']['ten_section']:
                            excluded_list = adaptive_config['dynamic_criteria']['ten_section'][section]
                            if isinstance(excluded_list, list) and len(excluded_list) > 0:
                                old_excluded = excluded_list.copy()
                                # 통과율을 높이기 위해 제외 리스트에서 값 제거
                                # 전략: 6을 먼저 제거 (6개 허용), 그 다음 0 제거 (0개 허용)
                                if 6 in excluded_list:
                                    excluded_list.remove(6)
                                    logging.info(f"       📝 adaptive_config.yaml - ten_section.{section}: {old_excluded} → {excluded_list} (6개 허용)")
                                elif 0 in excluded_list:
                                    excluded_list.remove(0)
                                    logging.info(f"       📝 adaptive_config.yaml - ten_section.{section}: {old_excluded} → {excluded_list} (0개 허용)")
                                else:
                                    # 이미 모두 허용 상태
                                    logging.info(f"       ✅ ten_section.{section}: 이미 모든 개수 허용됨 (최적 상태)")

                                adaptive_config['dynamic_criteria']['ten_section'][section] = excluded_list
                            else:
                                logging.info(f"       ✅ ten_section.{section}: 이미 빈 제외 리스트 (최적 상태)")

            elif filter_name == 'odd_even':
                # odd_even 필터 조정
                if 'dynamic_criteria' in adaptive_config and 'odd_even' in adaptive_config['dynamic_criteria']:
                    # excluded_counts를 줄여서 더 많은 패턴 허용
                    old_excluded = adaptive_config['dynamic_criteria']['odd_even'].get('excluded_counts', [0, 6])
                    # 0과 6만 제외 (이미 최선)
                    logging.info(f"       📝 odd_even 필터는 이미 최적 상태 (제외: {old_excluded})")

            elif filter_name == 'max_gap':
                # max_gap 필터 조정
                if 'dynamic_criteria' in adaptive_config and 'max_gap' in adaptive_config['dynamic_criteria']:
                    old_max_gap = adaptive_config['dynamic_criteria']['max_gap'].get('max_allowed_gap', 30)
                    new_max_gap = min(old_max_gap + 2, 40)  # 최대 40까지 허용
                    adaptive_config['dynamic_criteria']['max_gap']['max_allowed_gap'] = new_max_gap
                    logging.info(f"       📝 adaptive_config.yaml - max_gap.max_allowed_gap: {old_max_gap} → {new_max_gap}")

            elif filter_name == 'average':
                # average 필터 조정
                if 'dynamic_criteria' in adaptive_config and 'average' in adaptive_config['dynamic_criteria']:
                    old_min = adaptive_config['dynamic_criteria']['average'].get('min_average', 10)
                    old_max = adaptive_config['dynamic_criteria']['average'].get('max_average', 38)
                    margin = int(2 * adjustment_ratio)
                    new_min = max(1, old_min - margin)
                    new_max = min(45, old_max + margin)
                    adaptive_config['dynamic_criteria']['average']['min_average'] = new_min
                    adaptive_config['dynamic_criteria']['average']['max_average'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - average: [{old_min}, {old_max}] → [{new_min}, {new_max}]")

            elif filter_name == 'ac_value':
                # ac_value 필터 조정 - min_ac를 낮춰서 더 많은 조합 허용
                if 'dynamic_criteria' in adaptive_config and 'ac_value' in adaptive_config['dynamic_criteria']:
                    old_min_ac = adaptive_config['dynamic_criteria']['ac_value'].get('min_ac', 7)
                    # min_ac를 1 낮춤 (최소 4까지, 너무 낮으면 의미 없음)
                    new_min_ac = max(4, old_min_ac - 1)
                    adaptive_config['dynamic_criteria']['ac_value']['min_ac'] = new_min_ac
                    logging.info(f"       📝 adaptive_config.yaml - ac_value.min_ac: {old_min_ac} → {new_min_ac}")
                else:
                    # dynamic_criteria에 ac_value가 없으면 추가
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['ac_value'] = {'min_ac': 6, 'max_ac': 10}
                    logging.info(f"       📝 adaptive_config.yaml - ac_value 설정 추가: min_ac=6, max_ac=10")

            elif filter_name == 'balanced_quadrant':
                # balanced_quadrant 필터 조정 - max_per_quadrant 높이기
                if 'dynamic_criteria' in adaptive_config and 'balanced_quadrant' in adaptive_config['dynamic_criteria']:
                    old_max = adaptive_config['dynamic_criteria']['balanced_quadrant'].get('max_per_quadrant', 3)
                    new_max = min(old_max + 1, 5)  # 최대 5까지 허용
                    adaptive_config['dynamic_criteria']['balanced_quadrant']['max_per_quadrant'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - balanced_quadrant.max_per_quadrant: {old_max} → {new_max}")
                else:
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['balanced_quadrant'] = {'max_per_quadrant': 4}
                    logging.info(f"       📝 adaptive_config.yaml - balanced_quadrant 설정 추가: max_per_quadrant=4")

            elif filter_name == 'dispersion':
                # dispersion 필터 조정 - 범위 확장
                if 'dynamic_criteria' in adaptive_config and 'dispersion' in adaptive_config['dynamic_criteria']:
                    old_min = adaptive_config['dynamic_criteria']['dispersion'].get('min_std_dev', 10.0)
                    old_max = adaptive_config['dynamic_criteria']['dispersion'].get('max_std_dev', 15.0)
                    new_min = max(5.0, old_min - 2.0)
                    new_max = min(20.0, old_max + 2.0)
                    adaptive_config['dynamic_criteria']['dispersion']['min_std_dev'] = new_min
                    adaptive_config['dynamic_criteria']['dispersion']['max_std_dev'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - dispersion: [{old_min}, {old_max}] → [{new_min}, {new_max}]")
                else:
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['dispersion'] = {'min_std_dev': 8.0, 'max_std_dev': 17.0}
                    logging.info(f"       📝 adaptive_config.yaml - dispersion 설정 추가")

            elif filter_name == 'digit_sum':
                # digit_sum 필터 조정 - 범위 확장
                if 'dynamic_criteria' in adaptive_config and 'digit_sum' in adaptive_config['dynamic_criteria']:
                    digit_sum_config = adaptive_config['dynamic_criteria']['digit_sum']

                    # min/max_digit_sum 조정
                    old_min = digit_sum_config.get('min_digit_sum', 10)
                    old_max = digit_sum_config.get('max_digit_sum', 40)
                    margin = int(3 * adjustment_ratio)
                    new_min = max(5, old_min - margin)
                    new_max = min(55, old_max + margin)
                    digit_sum_config['min_digit_sum'] = new_min
                    digit_sum_config['max_digit_sum'] = new_max
                    logging.info(f"       📝 adaptive_config.yaml - digit_sum: [{old_min}, {old_max}] → [{new_min}, {new_max}]")

                    # min/max_digit_sum_range 조정 (더 넓은 범위 허용)
                    old_range_min = digit_sum_config.get('min_digit_sum_range', 0)
                    old_range_max = digit_sum_config.get('max_digit_sum_range', 12)
                    new_range_min = max(0, old_range_min - 1)
                    new_range_max = min(18, old_range_max + 2)  # 최대 18까지 확장
                    digit_sum_config['min_digit_sum_range'] = new_range_min
                    digit_sum_config['max_digit_sum_range'] = new_range_max
                    logging.info(f"       📝 adaptive_config.yaml - digit_sum_range: [{old_range_min}, {old_range_max}] → [{new_range_min}, {new_range_max}]")
                else:
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['digit_sum'] = {
                        'min_digit_sum': 8,
                        'max_digit_sum': 45,
                        'min_digit_sum_range': 0,
                        'max_digit_sum_range': 12
                    }
                    logging.info(f"       📝 adaptive_config.yaml - digit_sum 설정 추가 (range 포함)")

            elif filter_name == 'outlier_detection':
                # outlier_detection 필터 조정 - 허용 이상치 수 증가
                if 'dynamic_criteria' in adaptive_config and 'outlier_detection' in adaptive_config['dynamic_criteria']:
                    old_max_outliers = adaptive_config['dynamic_criteria']['outlier_detection'].get('max_outliers', 1)
                    old_iqr = adaptive_config['dynamic_criteria']['outlier_detection'].get('iqr_multiplier', 1.0)
                    new_max_outliers = min(old_max_outliers + 1, 3)  # 최대 3까지 허용
                    new_iqr = min(old_iqr + 0.5, 2.5)  # IQR 배수 완화
                    adaptive_config['dynamic_criteria']['outlier_detection']['max_outliers'] = new_max_outliers
                    adaptive_config['dynamic_criteria']['outlier_detection']['iqr_multiplier'] = new_iqr
                    logging.info(f"       📝 adaptive_config.yaml - outlier_detection: max_outliers {old_max_outliers} → {new_max_outliers}, iqr {old_iqr} → {new_iqr}")
                else:
                    if 'dynamic_criteria' not in adaptive_config:
                        adaptive_config['dynamic_criteria'] = {}
                    adaptive_config['dynamic_criteria']['outlier_detection'] = {'max_outliers': 2, 'iqr_multiplier': 1.5}
                    logging.info(f"       📝 adaptive_config.yaml - outlier_detection 설정 추가")

            elif filter_name == 'last_digit':
                # last_digit 필터 조정 - 동일 끝자리 허용 수 증가
                if 'dynamic_criteria' in adaptive_config and 'last_digit' in adaptive_config['dynamic_criteria']:
                    old_min = adaptive_config['dynamic_criteria']['last_digit'].get('min_same_last_digits', 5)
                    new_min = min(old_min + 1, 6)  # 최대 6까지 허용
                    adaptive_config['dynamic_criteria']['last_digit']['min_same_last_digits'] = new_min
                    logging.info(f"       📝 adaptive_config.yaml - last_digit.min_same_last_digits: {old_min} → {new_min}")

            elif filter_name in ['arithmetic', 'arithmetic_sequence']:
                # arithmetic 필터 조정 - 제외 길이 완화
                if 'dynamic_criteria' in adaptive_config and 'arithmetic' in adaptive_config['dynamic_criteria']:
                    old_exclude = adaptive_config['dynamic_criteria']['arithmetic'].get('exclude_lengths', [5, 6])
                    # 제외 길이에서 하나 제거 (6만 제외하도록)
                    if 5 in old_exclude:
                        new_exclude = [l for l in old_exclude if l != 5]
                        adaptive_config['dynamic_criteria']['arithmetic']['exclude_lengths'] = new_exclude
                        logging.info(f"       📝 adaptive_config.yaml - arithmetic.exclude_lengths: {old_exclude} → {new_exclude}")
                    else:
                        logging.info(f"       ✅ arithmetic 필터: 이미 최적 상태 (exclude_lengths: {old_exclude})")

            elif filter_name in ['geometric', 'geometric_sequence']:
                # geometric 필터 조정 - 제외 길이 완화
                if 'dynamic_criteria' in adaptive_config and 'geometric' in adaptive_config['dynamic_criteria']:
                    old_exclude = adaptive_config['dynamic_criteria']['geometric'].get('exclude_lengths', [4, 5, 6])
                    # 제외 길이에서 하나 제거
                    if 4 in old_exclude:
                        new_exclude = [l for l in old_exclude if l != 4]
                        adaptive_config['dynamic_criteria']['geometric']['exclude_lengths'] = new_exclude
                        logging.info(f"       📝 adaptive_config.yaml - geometric.exclude_lengths: {old_exclude} → {new_exclude}")
                    elif 5 in old_exclude:
                        new_exclude = [l for l in old_exclude if l != 5]
                        adaptive_config['dynamic_criteria']['geometric']['exclude_lengths'] = new_exclude
                        logging.info(f"       📝 adaptive_config.yaml - geometric.exclude_lengths: {old_exclude} → {new_exclude}")
                    else:
                        logging.info(f"       ✅ geometric 필터: 이미 최적 상태 (exclude_lengths: {old_exclude})")

            else:
                # 기타 필터는 기본 완화 적용 (필터 비활성화로 통과율 향상)
                logging.info(f"       ⚠️ {filter_name} 필터에 대한 구체적인 조정 로직이 없습니다.")
                logging.info(f"       💡 해당 필터를 일시적으로 비활성화하여 통과율 향상을 시도합니다.")
                # 필터 비활성화 (filters 섹션에서 false로 설정)
                if 'filters' in adaptive_config:
                    if filter_name in adaptive_config['filters']:
                        adaptive_config['filters'][filter_name] = False
                        logging.info(f"       📝 adaptive_config.yaml - filters.{filter_name}: true → false")

            # 임시 config 저장
            self._temp_config = config
            self._temp_adaptive_config = adaptive_config
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

        # adaptive_filter_config.yaml 백업
        if os.path.exists(self.adaptive_config_path):
            backup_path = f"configs/backup/adaptive_filter_config_backup_{timestamp}.yaml"
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy(self.adaptive_config_path, backup_path)
            logging.info(f"적응형 설정 백업: {backup_path}")
    
    def _save_configs(self):
        """수정된 설정 저장 (전역 설정값 보존)"""
        if hasattr(self, '_temp_config') and self._temp_config:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._temp_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            logging.info(f"설정 저장 완료: {self.config_path}")

        if hasattr(self, '_temp_adaptive_config') and self._temp_adaptive_config:
            # ✅ FIX: 기존 YAML 로드하여 critical fields 보존
            try:
                with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f)
            except Exception as e:
                logging.error(f"기존 설정 로드 실패: {e}, 새 설정으로 진행")
                existing_config = {}

            # ✅ FIX: 전역 임계값 보존 (Optuna 최적화 값 보호)
            if 'global_probability_threshold' in existing_config:
                preserved_threshold = existing_config['global_probability_threshold']
                logging.info(f"[FilterAutoAdjuster] global_probability_threshold 보존: {preserved_threshold}%")

            # ✅ FIX: dynamic_criteria만 업데이트 (필터 기준값만 변경)
            if 'dynamic_criteria' in self._temp_adaptive_config:
                existing_config['dynamic_criteria'] = self._temp_adaptive_config['dynamic_criteria']
                logging.debug(f"[FilterAutoAdjuster] dynamic_criteria 업데이트 완료")

            # ✅ FIX: filters 활성화 상태 업데이트 (필요 시)
            if 'filters' in self._temp_adaptive_config:
                existing_config['filters'] = self._temp_adaptive_config['filters']

            # ✅ FIX: 보존된 config 저장
            with open(self.adaptive_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            logging.info(f"적응형 설정 저장 완료: {self.adaptive_config_path} (전역 임계값 보존됨)")

            # ✅ NEW: YAML 저장 후 메모리에 로드된 필터 인스턴스도 즉시 업데이트
            if hasattr(self, 'filter_manager') and self.filter_manager:
                try:
                    from ..utils.config_manager import ConfigManager as CM
                    temp_config_manager = CM()

                    updated_count = 0
                    for filter_name, filter_instance in self.filter_manager.filters.items():
                        new_criteria = temp_config_manager.get_filter_criteria(filter_name)
                        if new_criteria:
                            old_criteria = filter_instance.criteria.copy()
                            filter_instance.criteria = new_criteria

                            # match 필터 변경사항은 명시적으로 로깅
                            if filter_name == 'match' and 'max_match' in new_criteria:
                                old_max = old_criteria.get('max_match', 'N/A')
                                new_max = new_criteria.get('max_match', 'N/A')
                                if old_max != new_max:
                                    logging.info(f"   ✅ [{filter_name}] 필터 기준 실시간 적용: max_match {old_max} → {new_max}")
                                    updated_count += 1
                            elif filter_name in self._temp_adaptive_config.get('dynamic_criteria', {}):
                                # 다른 조정된 필터들도 카운트
                                updated_count += 1

                    if updated_count > 0:
                        logging.info(f"   ✅ 총 {updated_count}개 필터의 기준이 실시간으로 업데이트되었습니다.")
                        logging.info(f"   ⏭️  프로그램 재시작 없이 즉시 적용됩니다!")
                except Exception as e:
                    logging.error(f"   ⚠️ 필터 기준 실시간 업데이트 실패: {e}")

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

    def _save_filter_snapshot(self, validation_results):
        """✅ NEW: 필터 조건 스냅샷 저장 (롤백 지원용)

        Args:
            validation_results: 검증 결과 (overall_pass_rate 포함)
        """
        if not self.performance_tracker:
            return

        try:
            # 1. 현재 필터 조건 수집
            filter_criteria = {}

            # config.yaml 로드
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # adaptive_filter_config.yaml 로드
            with open(self.adaptive_config_path, 'r', encoding='utf-8') as f:
                adaptive_config = yaml.safe_load(f)

            # 모든 필터 조건 수집
            if 'filters' in config and 'criteria' in config['filters']:
                for filter_name, criteria in config['filters']['criteria'].items():
                    filter_criteria[filter_name] = criteria.copy()

            if 'dynamic_criteria' in adaptive_config:
                for filter_name, criteria in adaptive_config['dynamic_criteria'].items():
                    if filter_name in filter_criteria:
                        # 기존 criteria에 dynamic_criteria 병합
                        filter_criteria[filter_name].update(criteria)
                    else:
                        filter_criteria[filter_name] = criteria.copy()

            # 2. 현재 필터 통과율 추출
            overall_pass_rate = 0.0
            if isinstance(validation_results, dict):
                overall_pass_rate = validation_results.get('overall_pass_rate', 0.0)
            elif isinstance(validation_results, list) and validation_results:
                # 리스트에서 통과율 계산
                total_rounds = len(validation_results)
                passed_rounds = sum(1 for r in validation_results if r.get('passed', False))
                overall_pass_rate = (passed_rounds / total_rounds) * 100 if total_rounds > 0 else 0.0

            # 3. 최근 performance_history ID 조회 (스냅샷과 연결)
            # Note: 실제 구현에서는 backtesting 후 저장된 performance_history_id를 받아야 함
            # 지금은 임시로 마지막 ID를 사용
            import sqlite3
            with sqlite3.connect(self.performance_tracker.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(id) FROM performance_history")
                last_id = cursor.fetchone()[0]

            if last_id:
                # 4. 필터 조건 스냅샷 저장
                self.performance_tracker.save_filter_criteria_snapshot(
                    performance_history_id=last_id,
                    filter_criteria=filter_criteria,
                    filter_pass_rate=overall_pass_rate
                )
                logging.info(f"✅ 필터 조건 스냅샷 저장 완료 (Performance ID: {last_id})")

        except Exception as e:
            logging.error(f"필터 스냅샷 저장 중 오류: {e}")

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