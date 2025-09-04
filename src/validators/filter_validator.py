#!/usr/bin/env python3
"""
필터 검증 시스템
과거 당첨번호가 현재 필터를 통과하는지 검증
"""
import logging
import json
import sys
from typing import Dict, List, Tuple, Any
from tqdm import tqdm
import numpy as np
from ..core.db_manager import DatabaseManager
from ..core.filter_manager import FilterManager
from ..utils.config_manager import ConfigManager


def convert_numpy_types(obj):
    """NumPy 타입을 JSON 직렬화 가능한 Python 기본 타입으로 변환"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    else:
        return obj

class FilterValidator:
    """필터 검증 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.config_manager = ConfigManager()
        self.validation_results = {}
        
        logging.info("필터 검증 시스템 초기화 완료")
    
    def validate_filters_with_historical_data(self, start_round: int = 1, end_round: int = None) -> Dict[str, Any]:
        """과거 당첨번호가 현재 필터를 통과하는지 검증
        
        Args:
            start_round: 검증 시작 회차
            end_round: 검증 종료 회차 (None이면 최신 회차까지)
            
        Returns:
            Dict: 검증 결과
        """
        logging.info("\n" + "="*60)
        logging.info("필터 검증 시스템 시작")
        logging.info("="*60)
        
        # 모든 당첨번호 데이터 가져오기
        all_numbers_data = self.db_manager.get_all_numbers()  # [(round, numbers, date), ...]
        if not all_numbers_data:
            logging.error("당첨번호 데이터가 없습니다.")
            return {}
            
        # 회차 정보와 함께 정리
        # get_all_numbers()는 (round, numbers, draw_date) 형식으로 반환
        all_winning_numbers = [(round_num, numbers) for round_num, numbers, draw_date in all_numbers_data]
        
        if end_round is None:
            end_round = len(all_winning_numbers)
        
        # 검증할 회차 범위
        validation_range = range(max(0, start_round-1), min(end_round, len(all_winning_numbers)))
        total_rounds = len(validation_range)
        
        logging.info(f"검증 범위: {start_round}회차 ~ {end_round}회차 (총 {total_rounds}개)")
        
        # 각 필터별 통과 결과 저장
        filter_pass_counts = {filter_name: 0 for filter_name in self.filter_manager.filters.keys()}
        filter_pass_details = {filter_name: [] for filter_name in self.filter_manager.filters.keys()}
        overall_pass_count = 0
        overall_pass_details = []
        
        # 진행 상태 표시
        try:
            with tqdm(total=total_rounds, desc="당첨번호 검증 중", file=sys.stdout) as pbar:
                for round_idx in validation_range:
                    round_num, winning_str = all_winning_numbers[round_idx]
                    winning_numbers = [int(n) for n in winning_str.split(',')]
                    
                    # 각 필터 검증
                    all_filters_passed = True
                    filter_results = {}
                    
                    for filter_name, filter_instance in self.filter_manager.filters.items():
                        # 필터 통과 여부 확인
                        passed = self._check_filter_pass(filter_instance, winning_numbers, round_num)
                        filter_results[filter_name] = passed
                        
                        if passed:
                            filter_pass_counts[filter_name] += 1
                        else:
                            all_filters_passed = False
                            filter_pass_details[filter_name].append(round_num)
                    
                    if all_filters_passed:
                        overall_pass_count += 1
                    else:
                        overall_pass_details.append({
                            'round': round_num,
                            'numbers': winning_numbers,
                            'failed_filters': [name for name, passed in filter_results.items() if not passed]
                        })
                    
                    pbar.update(1)
        except Exception as e:
            # tqdm 에러 발생 시 진행바 없이 실행
            logging.warning(f"진행바 표시 실패, 계속 진행: {e}")
            for round_idx in validation_range:
                round_num, winning_str = all_winning_numbers[round_idx]
                winning_numbers = [int(n) for n in winning_str.split(',')]
                
                # 각 필터 검증
                all_filters_passed = True
                filter_results = {}
                
                for filter_name, filter_instance in self.filter_manager.filters.items():
                    # 필터 통과 여부 확인
                    passed = self._check_filter_pass(filter_instance, winning_numbers, round_num)
                    filter_results[filter_name] = passed
                    
                    if passed:
                        filter_pass_counts[filter_name] += 1
                    else:
                        all_filters_passed = False
                        filter_pass_details[filter_name].append(round_num)
                
                if all_filters_passed:
                    overall_pass_count += 1
                else:
                    overall_pass_details.append({
                        'round': round_num,
                        'numbers': winning_numbers,
                        'failed_filters': [name for name, passed in filter_results.items() if not passed]
                    })
        
        # 결과 계산
        results = {
            'total_rounds': total_rounds,
            'overall_pass_count': overall_pass_count,
            'overall_pass_rate': overall_pass_count / total_rounds * 100,
            'filter_results': {}
        }
        
        # 각 필터별 통과율 계산
        for filter_name in self.filter_manager.filters.keys():
            pass_count = filter_pass_counts[filter_name]
            pass_rate = pass_count / total_rounds * 100
            
            results['filter_results'][filter_name] = {
                'pass_count': pass_count,
                'pass_rate': pass_rate,
                'failed_rounds': filter_pass_details[filter_name][:10]  # 처음 10개만
            }
        
        # 상세 분석
        results['failed_details'] = overall_pass_details[:20]  # 처음 20개만
        
        # 결과 저장
        self.validation_results = results
        self._save_validation_results(results)
        
        # 결과 출력
        self._print_validation_summary(results)
        
        return results
    
    def _check_filter_pass(self, filter_instance: Any, numbers: List[int], round_num: int) -> bool:
        """특정 필터에 대한 통과 여부 확인
        
        Args:
            filter_instance: 필터 인스턴스
            numbers: 당첨번호 리스트
            round_num: 회차 번호
            
        Returns:
            bool: 통과 여부
        """
        # 번호를 문자열 조합으로 변환
        combination_str = ','.join(map(str, sorted(numbers)))
        
        # 필터 적용
        try:
            # 필터의 apply 메서드를 직접 호출하여 확인
            result = filter_instance.apply([combination_str], round_num)
            return len(result) > 0  # 결과가 있으면 통과
        except Exception as e:
            logging.error(f"필터 검증 중 오류: {str(e)}")
            return False
    
    def optimize_filter_thresholds(self, target_pass_rate: float = 0.95) -> Dict[str, Any]:
        """필터 임계값을 자동으로 최적화
        
        Args:
            target_pass_rate: 목표 통과율 (0.0 ~ 1.0)
            
        Returns:
            Dict: 최적화된 필터 설정
        """
        logging.info(f"\n필터 임계값 최적화 시작 (목표 통과율: {target_pass_rate*100:.1f}%)")
        
        optimized_criteria = {}
        
        # 각 필터별로 최적화
        for filter_name, filter_instance in self.filter_manager.filters.items():
            logging.info(f"\n[{filter_name}] 필터 최적화 중...")
            
            # 현재 기준값 가져오기
            current_criteria = filter_instance.get_criteria()
            
            # 필터 타입에 따라 최적화 방법 다르게 적용
            if filter_name == 'sum_range':
                optimized = self._optimize_range_filter(filter_name, current_criteria, target_pass_rate)
            elif filter_name == 'average':
                optimized = self._optimize_range_filter(filter_name, current_criteria, target_pass_rate, is_average=True)
            elif filter_name == 'consecutive':
                optimized = self._optimize_max_value_filter(filter_name, current_criteria, target_pass_rate)
            else:
                # 기본값 유지
                optimized = current_criteria
                
            optimized_criteria[filter_name] = optimized
            logging.info(f"  최적화 완료: {optimized}")
        
        return optimized_criteria
    
    def _optimize_range_filter(self, filter_name: str, current_criteria: Dict, target_pass_rate: float, is_average: bool = False) -> Dict:
        """범위 기반 필터 최적화"""
        # 과거 당첨번호 분석
        all_winning_numbers = self.db_manager.get_all_winning_numbers()
        
        if is_average:
            values = []
            for nums_str in all_winning_numbers:
                numbers = [int(n) for n in nums_str.split(',')]
                values.append(np.mean(numbers))
        else:
            values = []
            for nums_str in all_winning_numbers:
                numbers = [int(n) for n in nums_str.split(',')]
                values.append(sum(numbers))
        
        # 백분위수 계산
        lower_percentile = (1 - target_pass_rate) / 2 * 100
        upper_percentile = 100 - lower_percentile
        
        min_val = np.percentile(values, lower_percentile)
        max_val = np.percentile(values, upper_percentile)
        
        if is_average:
            return {
                'min_average': round(min_val, 1),
                'max_average': round(max_val, 1)
            }
        else:
            return {
                'min_sum': int(min_val),
                'max_sum': int(max_val)
            }
    
    def _optimize_max_value_filter(self, filter_name: str, current_criteria: Dict, target_pass_rate: float) -> Dict:
        """최대값 기반 필터 최적화"""
        # 과거 당첨번호 분석
        all_winning_numbers = self.db_manager.get_all_winning_numbers()
        
        values = []
        for nums_str in all_winning_numbers:
            numbers = sorted([int(n) for n in nums_str.split(',')])
            
            if filter_name == 'consecutive':
                # 연속 번호 개수 계산
                max_consecutive = 1
                current_consecutive = 1
                for i in range(1, len(numbers)):
                    if numbers[i] == numbers[i-1] + 1:
                        current_consecutive += 1
                        max_consecutive = max(max_consecutive, current_consecutive)
                    else:
                        current_consecutive = 1
                values.append(max_consecutive)
        
        # 백분위수 계산
        percentile = target_pass_rate * 100
        max_val = np.percentile(values, percentile)
        
        return {
            'max_consecutive': int(np.ceil(max_val))
        }
    
    def _save_validation_results(self, results: Dict[str, Any]):
        """검증 결과 저장"""
        output_path = "results/filter_validation_results.json"
        
        try:
            # NumPy 타입을 Python 기본 타입으로 변환
            converted_results = convert_numpy_types(results)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(converted_results, f, ensure_ascii=False, indent=2)
            logging.info(f"\n검증 결과가 {output_path}에 저장되었습니다.")
        except Exception as e:
            logging.error(f"결과 저장 중 오류: {str(e)}")
    
    def _print_validation_summary(self, results: Dict[str, Any]):
        """검증 결과 요약 출력"""
        logging.info("\n" + "="*60)
        logging.info("필터 검증 결과 요약")
        logging.info("="*60)
        
        logging.info(f"\n총 검증 회차: {results['total_rounds']}개")
        logging.info(f"전체 필터 통과: {results['overall_pass_count']}개 ({results['overall_pass_rate']:.2f}%)")
        
        logging.info("\n[필터별 통과율]")
        for filter_name, filter_result in results['filter_results'].items():
            pass_rate = filter_result['pass_rate']
            status = "⚠️" if pass_rate < 90 else "✅"
            logging.info(f"{status} {filter_name}: {pass_rate:.2f}% ({filter_result['pass_count']}/{results['total_rounds']})")
        
        # 실패한 필터 상세 정보
        if results['failed_details']:
            logging.info("\n[전체 필터 통과 실패 사례 (최대 5개)]")
            for i, detail in enumerate(results['failed_details'][:5]):
                logging.info(f"\n{i+1}. {detail['round']}회차: {detail['numbers']}")
                logging.info(f"   실패 필터: {', '.join(detail['failed_filters'])}")
        
        # 경고 메시지
        if results['overall_pass_rate'] < 90:
            logging.warning(f"\n⚠️ 주의: 전체 통과율이 {results['overall_pass_rate']:.2f}%로 낮습니다!")
            logging.warning("필터 기준을 재조정해야 합니다.")
    
    def suggest_optimized_criteria(self, validation_results: Dict[str, Any], target_pass_rate: float = 95) -> Dict[str, Any]:
        """검증 결과를 바탕으로 최적화된 필터 기준 제안
        
        Args:
            validation_results: 필터 검증 결과
            target_pass_rate: 목표 통과율 (기본값: 95%)
            
        Returns:
            Dict: 최적화된 필터 기준
        """
        optimized_criteria = {}
        
        for filter_name, filter_result in validation_results['filter_results'].items():
            pass_rate = filter_result['pass_rate']
            
            # 통과율이 목표치보다 낮은 경우 최적화 제안
            if pass_rate < target_pass_rate:
                adjustment_ratio = target_pass_rate / pass_rate if pass_rate > 0 else 2.0
                
                # 필터별 최적화 기준 계산
                if filter_name == 'consecutive':
                    optimized_criteria[filter_name] = self._optimize_consecutive_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                elif filter_name == 'sum_range':
                    optimized_criteria[filter_name] = self._optimize_sum_range_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                elif filter_name == 'average':
                    optimized_criteria[filter_name] = self._optimize_average_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                elif filter_name == 'max_gap':
                    optimized_criteria[filter_name] = self._optimize_max_gap_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                elif filter_name == 'dispersion':
                    optimized_criteria[filter_name] = self._optimize_dispersion_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                elif filter_name == 'section':
                    optimized_criteria[filter_name] = self._optimize_section_filter(
                        filter_result.get('details', {}), adjustment_ratio
                    )
                # 기타 필터들은 기본 조정
                else:
                    optimized_criteria[filter_name] = {
                        'adjustment_ratio': adjustment_ratio,
                        'current_pass_rate': pass_rate,
                        'target_pass_rate': target_pass_rate
                    }
                
                logging.info(f"[{filter_name}] 필터 최적화 제안: 통과율 {pass_rate:.2f}% → {target_pass_rate:.2f}%")
        
        return optimized_criteria
    
    def _optimize_consecutive_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """연속 번호 필터 최적화"""
        current_max = details.get('max_consecutive', 2)
        new_max = max(2, min(5, int(current_max * adjustment_ratio)))
        return {'max_consecutive': new_max}
    
    def _optimize_sum_range_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """합계 범위 필터 최적화"""
        current_min = details.get('min_sum', 100)
        current_max = details.get('max_sum', 177)
        range_expansion = (current_max - current_min) * (adjustment_ratio - 1) / 2
        
        return {
            'min_sum': max(21, int(current_min - range_expansion)),
            'max_sum': min(255, int(current_max + range_expansion))
        }
    
    def _optimize_average_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """평균값 필터 최적화"""
        current_min = details.get('min_average', 20.0)
        current_max = details.get('max_average', 25.0)
        range_expansion = (current_max - current_min) * (adjustment_ratio - 1) / 2
        
        return {
            'min_average': max(3.5, current_min - range_expansion),
            'max_average': min(42.5, current_max + range_expansion)
        }
    
    def _optimize_max_gap_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """최대 간격 필터 최적화"""
        current_max = details.get('max_allowed_gap', 25)
        new_max = min(40, int(current_max * adjustment_ratio))
        return {'max_allowed_gap': new_max}
    
    def _optimize_dispersion_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """분산 필터 최적화"""
        current_min = details.get('min_std_dev', 10.0)
        current_max = details.get('max_std_dev', 15.0)
        range_expansion = (current_max - current_min) * (adjustment_ratio - 1) / 2
        
        return {
            'min_std_dev': max(5.0, current_min - range_expansion),
            'max_std_dev': min(20.0, current_max + range_expansion)
        }
    
    def _optimize_section_filter(self, details: Dict[str, Any], adjustment_ratio: float) -> Dict[str, Any]:
        """구간 필터 최적화"""
        current_max = details.get('max_numbers_per_section', 3)
        new_max = min(6, int(current_max * adjustment_ratio))
        return {'max_numbers_per_section': new_max}
    
    def apply_optimized_settings_to_config(self, optimized_criteria: Dict[str, Any]) -> bool:
        """최적화된 필터 설정을 config.yaml에 자동 반영
        
        Args:
            optimized_criteria: 최적화된 필터 설정
            
        Returns:
            bool: 성공 여부
        """
        import yaml
        
        try:
            # 현재 config.yaml 읽기
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.yaml')
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 최적화된 설정 반영
            for filter_name, criteria in optimized_criteria.items():
                if filter_name in config['filters']['criteria']:
                    # 기존 설정과 병합
                    if isinstance(criteria, dict):
                        config['filters']['criteria'][filter_name].update(criteria)
                    else:
                        config['filters']['criteria'][filter_name] = criteria
                    
                    logging.info(f"[Config 업데이트] {filter_name}: {criteria}")
            
            # config.yaml에 저장
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            logging.info("\n✅ config.yaml에 최적화된 필터 설정이 자동 반영되었습니다.")
            return True
            
        except Exception as e:
            logging.error(f"Config 파일 업데이트 중 오류: {str(e)}")
            return False


def main():
    """테스트 실행"""
    validator = FilterValidator()
    
    # 최근 100회차 검증
    results = validator.validate_filters_with_historical_data(start_round=1083, end_round=1182)
    
    # 필터 최적화 제안
    if results['overall_pass_rate'] < 90:
        logging.info("\n필터 최적화를 시작합니다...")
        optimized = validator.optimize_filter_thresholds(target_pass_rate=0.95)
        
        logging.info("\n[최적화된 필터 설정]")
        for filter_name, criteria in optimized.items():
            logging.info(f"{filter_name}: {criteria}")


if __name__ == "__main__":
    from ..logger import setup_logging
    setup_logging()
    main()