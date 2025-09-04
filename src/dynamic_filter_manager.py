#!/usr/bin/env python3
"""
동적 필터 관리 시스템
과거 당첨번호 분석을 기반으로 필터 임계값을 동적으로 조정하고
선택적으로 필터를 적용하는 개선된 시스템
"""
import json
import random
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from collections import defaultdict

class DynamicFilterManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.winning_stats = self._analyze_winning_numbers()
        self.filter_effectiveness = self._load_filter_effectiveness()
        
        # 필터 그룹 정의
        self.filter_groups = {
            "essential": ["odd_even", "sum_range", "dispersion"],  # 항상 적용
            "optional_a": ["fixed_step", "section", "average"],    # 선택적 적용
            "optional_b": ["max_gap", "multiple"],                  # 보조 필터
            "disabled": ["consecutive", "last_digit", "ten_section", 
                        "arithmetic_sequence", "geometric_sequence", 
                        "prime_composite", "digit_sum"]              # 비활성화
        }
        
        # 적용 전략별 설정
        self.strategies = {
            "strict": {"essential": 1.0, "optional_a": 0.8, "optional_b": 0.6},
            "balanced": {"essential": 1.0, "optional_a": 0.5, "optional_b": 0.3},
            "lenient": {"essential": 1.0, "optional_a": 0.3, "optional_b": 0.1}
        }
        
        logging.info("동적 필터 관리자 초기화 완료")
    
    def _analyze_winning_numbers(self) -> Dict[str, Any]:
        """과거 당첨번호 통계 분석"""
        try:
            winning_numbers = self.db_manager.get_all_winning_numbers()
            if not winning_numbers:
                return self._get_default_stats()
            
            stats = {
                'sum': {'values': [], 'mean': 0, 'std': 0, 'min': 0, 'max': 0},
                'odd_count': defaultdict(int),
                'gaps': [],
                'consecutive_count': defaultdict(int),
                'section_distribution': defaultdict(int),
                'average': {'values': [], 'mean': 0, 'std': 0}
            }
            
            for nums_str in winning_numbers:
                numbers = sorted([int(n) for n in nums_str.split(',')])
                
                # 합계 통계
                total_sum = sum(numbers)
                stats['sum']['values'].append(total_sum)
                
                # 홀짝 분포
                odd_count = sum(1 for n in numbers if n % 2 == 1)
                stats['odd_count'][odd_count] += 1
                
                # 간격 통계
                gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
                stats['gaps'].extend(gaps)
                
                # 연속번호 개수
                consecutive = sum(1 for i in range(len(numbers)-1) 
                                if numbers[i+1] - numbers[i] == 1)
                stats['consecutive_count'][consecutive] += 1
                
                # 구간 분포
                for num in numbers:
                    section = (num - 1) // 10
                    stats['section_distribution'][section] += 1
                
                # 평균값
                avg = sum(numbers) / len(numbers)
                stats['average']['values'].append(avg)
            
            # 통계 계산
            stats['sum']['mean'] = np.mean(stats['sum']['values'])
            stats['sum']['std'] = np.std(stats['sum']['values'])
            stats['sum']['min'] = min(stats['sum']['values'])
            stats['sum']['max'] = max(stats['sum']['values'])
            
            stats['average']['mean'] = np.mean(stats['average']['values'])
            stats['average']['std'] = np.std(stats['average']['values'])
            
            stats['gaps_mean'] = np.mean(stats['gaps'])
            stats['gaps_max'] = max(stats['gaps'])
            
            # 가장 흔한 홀수 개수
            stats['most_common_odd_count'] = max(stats['odd_count'].items(), 
                                                key=lambda x: x[1])[0]
            
            return stats
            
        except Exception as e:
            logging.error(f"당첨번호 분석 중 오류: {str(e)}")
            return self._get_default_stats()
    
    def _get_default_stats(self) -> Dict[str, Any]:
        """기본 통계값 (분석 실패시 사용)"""
        return {
            'sum': {'mean': 138.3, 'std': 30.8, 'min': 48, 'max': 238},
            'average': {'mean': 23.0, 'std': 5.1},
            'most_common_odd_count': 3,
            'gaps_mean': 6.5,
            'gaps_max': 33
        }
    
    def _load_filter_effectiveness(self) -> Dict[str, float]:
        """필터 효과성 데이터 로드"""
        try:
            with open('filter_optimization_summary.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            effectiveness = {}
            for filter_info in data['filter_effectiveness']:
                # 필터링 개수를 기반으로 효과성 점수 계산
                score = filter_info['filtered'] / 1182.0  # 전체 회차 대비 비율
                effectiveness[filter_info['name']] = score
            
            return effectiveness
            
        except FileNotFoundError:
            # 파일이 없는 경우는 정상적인 상황 (첫 실행 등)
            logging.debug("필터 효과성 데이터 파일이 없습니다. 기본값을 사용합니다.")
            # 기본값 반환
            return {
                'odd_even': 0.030,
                'dispersion': 0.015,
                'average': 0.013,
                'sum_range': 0.011,
                'fixed_step': 0.009,
                'multiple': 0.004,
                'section': 0.003,
                'max_gap': 0.002
            }
        except Exception as e:
            # 다른 예외는 경고로 처리
            logging.warning(f"필터 효과성 데이터 로드 중 오류 발생: {str(e)}")
            # 기본값 반환
            return {
                'odd_even': 0.030,
                'dispersion': 0.015,
                'average': 0.013,
                'sum_range': 0.011,
                'fixed_step': 0.009,
                'multiple': 0.004,
                'section': 0.003,
                'max_gap': 0.002
            }
    
    def get_dynamic_criteria(self, filter_name: str) -> Dict[str, Any]:
        """필터별 동적 임계값 계산"""
        criteria = {}
        
        if filter_name == 'sum_range':
            # 평균 ± 2σ 범위
            mean = self.winning_stats['sum']['mean']
            std = self.winning_stats['sum']['std']
            criteria['min_sum'] = int(mean - 2 * std)
            criteria['max_sum'] = int(mean + 2 * std)
            
        elif filter_name == 'average':
            # 평균값 범위
            mean = self.winning_stats['average']['mean']
            std = self.winning_stats['average']['std']
            criteria['min_average'] = 10.0  # 고정값으로 설정 (매우 넓은 범위)
            criteria['max_average'] = 35.0  # 고정값으로 설정 (매우 넓은 범위)
            criteria['exclude_extremes'] = True
            
        elif filter_name == 'odd_even':
            # 극단값만 제외 (0개 또는 6개)
            criteria['excluded_counts'] = [0, 6]
            
        elif filter_name == 'max_gap':
            # 최대 간격의 95% 수준
            criteria['max_allowed_gap'] = int(self.winning_stats['gaps_max'] * 0.95)
            
        elif filter_name == 'dispersion':
            # 표준편차 기반 설정
            criteria['min_std_dev'] = 1.0
            criteria['max_std_dev'] = 18.0
            criteria['min_variance'] = 1.0
            criteria['max_variance'] = 280.0
            
        else:
            # 기타 필터는 기본값 사용
            return None
        
        return criteria
    
    def select_filters(self, strategy: str = 'balanced') -> List[str]:
        """전략에 따른 필터 선택"""
        if strategy not in self.strategies:
            strategy = 'balanced'
        
        selected = []
        probabilities = self.strategies[strategy]
        
        # Essential 필터는 항상 포함
        selected.extend(self.filter_groups['essential'])
        
        # Optional 필터는 확률적으로 선택
        for group_name in ['optional_a', 'optional_b']:
            if random.random() < probabilities[group_name]:
                # 그룹에서 일부 선택
                group_filters = self.filter_groups[group_name]
                num_select = max(1, int(len(group_filters) * probabilities[group_name]))
                selected.extend(random.sample(group_filters, num_select))
        
        # 효과성 순으로 정렬
        selected.sort(key=lambda x: self.filter_effectiveness.get(x, 0), reverse=True)
        
        return selected
    
    def get_filter_config(self, strategy: str = 'balanced') -> Dict[str, Any]:
        """전략별 필터 설정 생성"""
        selected_filters = self.select_filters(strategy)
        
        config = {
            'enabled_filters': selected_filters,
            'filter_criteria': {},
            'filter_efficiency': {}
        }
        
        # 각 필터의 동적 기준값 설정
        for filter_name in selected_filters:
            dynamic_criteria = self.get_dynamic_criteria(filter_name)
            if dynamic_criteria:
                config['filter_criteria'][filter_name] = dynamic_criteria
            
            # 효율성 점수 설정
            config['filter_efficiency'][filter_name] = \
                self.filter_effectiveness.get(filter_name, 0.1)
        
        return config
    
    def update_config_file(self, strategy: str = 'balanced'):
        """config.yaml 파일 업데이트"""
        import yaml
        
        try:
            # 기존 설정 로드
            with open('config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 필터 설정 업데이트
            new_filter_config = self.get_filter_config(strategy)
            
            config['filters']['enabled_filters'] = new_filter_config['enabled_filters']
            
            # 동적 기준값 업데이트
            for filter_name, criteria in new_filter_config['filter_criteria'].items():
                if filter_name in config['filters']['criteria']:
                    config['filters']['criteria'][filter_name].update(criteria)
            
            # 효율성 업데이트
            config['filters']['filter_efficiency'] = new_filter_config['filter_efficiency']
            
            # match 필터 수정
            if 'match' in config['filters']['criteria']:
                config['filters']['criteria']['match']['max_match'] = 6  # 6개까지 허용
            
            # 파일 저장
            with open('config_dynamic.yaml', 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logging.info(f"동적 설정이 config_dynamic.yaml에 저장되었습니다. (전략: {strategy})")
            return True
            
        except Exception as e:
            logging.error(f"설정 파일 업데이트 중 오류: {str(e)}")
            return False
    
    def print_statistics(self):
        """분석된 통계 정보 출력"""
        print("\n=== 당첨번호 통계 분석 결과 ===")
        print(f"\n합계 통계:")
        print(f"  - 평균: {self.winning_stats['sum']['mean']:.1f}")
        print(f"  - 표준편차: {self.winning_stats['sum']['std']:.1f}")
        print(f"  - 범위: {self.winning_stats['sum']['min']} ~ {self.winning_stats['sum']['max']}")
        
        print(f"\n평균값 통계:")
        print(f"  - 평균: {self.winning_stats['average']['mean']:.1f}")
        print(f"  - 표준편차: {self.winning_stats['average']['std']:.1f}")
        
        print(f"\n홀짝 패턴:")
        print(f"  - 가장 흔한 홀수 개수: {self.winning_stats['most_common_odd_count']}개")
        
        print(f"\n간격 통계:")
        print(f"  - 평균 간격: {self.winning_stats['gaps_mean']:.1f}")
        print(f"  - 최대 간격: {self.winning_stats['gaps_max']}")
        
        print("\n=== 필터 효과성 순위 ===")
        sorted_filters = sorted(self.filter_effectiveness.items(), 
                              key=lambda x: x[1], reverse=True)
        for i, (name, score) in enumerate(sorted_filters[:10], 1):
            print(f"{i:2d}. {name:20s}: {score*100:.2f}%")


def main():
    """테스트 및 시연"""
    import sys
    sys.path.append('.')
    from src.core.db_manager import DatabaseManager
    
    # DB 매니저 초기화
    db_manager = DatabaseManager()
    
    # 동적 필터 관리자 생성
    dynamic_manager = DynamicFilterManager(db_manager)
    
    # 통계 출력
    dynamic_manager.print_statistics()
    
    # 각 전략별 필터 선택 시연
    print("\n=== 전략별 필터 선택 ===")
    for strategy in ['strict', 'balanced', 'lenient']:
        selected = dynamic_manager.select_filters(strategy)
        print(f"\n{strategy} 전략: {len(selected)}개 필터")
        print(f"  선택된 필터: {', '.join(selected)}")
    
    # 동적 설정 생성
    print("\n=== 동적 설정 생성 ===")
    config = dynamic_manager.get_filter_config('balanced')
    print(f"활성 필터: {len(config['enabled_filters'])}개")
    
    # 동적 임계값 예시
    print("\n동적 임계값 예시:")
    for filter_name in ['sum_range', 'average', 'max_gap']:
        criteria = dynamic_manager.get_dynamic_criteria(filter_name)
        if criteria:
            print(f"\n{filter_name}:")
            for key, value in criteria.items():
                print(f"  - {key}: {value}")
    
    # 설정 파일 업데이트
    if dynamic_manager.update_config_file('balanced'):
        print("\n✅ config_dynamic.yaml 파일이 생성되었습니다.")

if __name__ == "__main__":
    main()