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

# 모듈 레벨 임포트 (패치 가능하도록)
try:
    from ..core.continuous_improvement_engine import PerformanceTracker
except ImportError:
    PerformanceTracker = None


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
    
    def __init__(self, db_manager=None, config=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            config: 설정 딕셔너리 (백테스팅 설정 포함)
        """
        self.db_manager = db_manager or DatabaseManager()
        self.filter_manager = FilterManager(self.db_manager)
        self.config_manager = ConfigManager()
        self.validation_results = {}

        # ✅ FIX: 백테스팅 설정 로드
        if config is None:
            config = self.config_manager.config
        backtesting_config = config.get('backtesting', {})
        self.validation_window = backtesting_config.get('validation_window', 300)  # 51 → 300
        logging.info(f"[필터 검증] 검증 윈도우: {self.validation_window} 회차")

        logging.info("필터 검증 시스템 초기화 완료")

    def _check_filter_data_ready(self) -> bool:
        """필터 데이터가 준비되었는지 확인

        Returns:
            bool: 데이터가 준비되면 True, 아니면 False
        """
        try:
            # 1. 기본 데이터베이스 확인
            latest_round = self.db_manager.get_last_round()
            if not latest_round or latest_round < 1:
                logging.debug("[필터 검증] 회차 데이터 없음")
                return False

            # 2. 조합 데이터베이스 확인 (필터링된 조합이 있는지)
            try:
                # CombinationsDB는 db_path를 받아야 함
                if hasattr(self.db_manager, 'combinations_db') and self.db_manager.combinations_db:
                    filtered_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)

                    # 필터링된 조합이 있으면 데이터 준비 완료
                    if filtered_count and filtered_count > 0:
                        logging.debug(f"[필터 검증] 조합 DB 확인 완료: {filtered_count:,}개")
                        return True
                    else:
                        logging.debug(f"[필터 검증] 조합 DB 비어있음 (회차: {latest_round})")
                else:
                    logging.debug("[필터 검증] 조합 DB 인스턴스 없음")
            except Exception as e:
                # 조합 DB가 없거나 에러 발생 시 (첫 실행 등)
                logging.debug(f"[필터 검증] 조합 DB 확인 실패: {e}")

            # 3. 필터 데이터베이스 확인
            try:
                # FilterDB도 db_path를 받아야 함
                if hasattr(self.db_manager, 'filter_db') and self.db_manager.filter_db:
                    filter_db = self.db_manager.filter_db
                else:
                    # filter_db가 없으면 직접 생성 시도
                    from ..core.specialized_databases import FilterDB
                    filter_db = FilterDB(self.db_manager.paths.filters)

                # 최소 하나의 필터라도 데이터가 있는지 확인
                for filter_name in ['odd_even', 'consecutive', 'sum_range']:
                    try:
                        stats = filter_db.get_filter_stats(filter_name, latest_round)
                        if stats:
                            logging.debug(f"[필터 검증] 필터 DB 확인 완료: {filter_name}")
                            return True
                    except Exception:  # FIX HIGH: bare except → Exception
                        continue

                logging.debug("[필터 검증] 필터 DB 데이터 없음")
            except Exception as e:
                logging.debug(f"[필터 검증] 필터 DB 확인 실패: {e}")

            # 4. 모든 확인 실패 - 데이터 아직 준비 안됨
            return False

        except Exception as e:
            logging.debug(f"[필터 검증] 데이터 준비 확인 중 오류: {e}")
            return False

    def validate_filters_with_historical_data(self, start_round: int = 1, end_round: int = None, is_startup: bool = False) -> Dict[str, Any]:
        """과거 당첨번호가 현재 필터를 통과하는지 검증

        Args:
            start_round: 검증 시작 회차
            end_round: 검증 종료 회차 (None이면 최신 회차까지)
            is_startup: 시작 시 실행 여부 (True면 데이터 준비 상태 확인)

        Returns:
            Dict: 검증 결과
        """
        # 시작 시 실행이면 데이터 준비 상태 확인
        if is_startup:
            if not self._check_filter_data_ready():
                logging.info("ℹ️ 필터 데이터가 아직 준비되지 않았습니다. 검증을 건너뜁니다.")
                logging.info("   (첫 필터링 실행 후 데이터가 생성됩니다)")
                return {
                    'total_rounds': 0,
                    'overall_pass_count': 0,
                    'overall_pass_rate': 100.0,  # 기본값 100%로 설정하여 false warning 방지
                    'filter_results': {},
                    'skipped': True,
                    'reason': 'Filter data not ready yet - first run'
                }

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

        # ✅ FIX: 검증 윈도우 적용 (최근 N회차만 검증)
        # validation_window = 300인 경우, 최근 300회차만 검증
        adjusted_start_round = max(1, end_round - self.validation_window + 1)
        if start_round < adjusted_start_round:
            logging.info(f"[필터 검증] 검증 범위 조정: {start_round} → {adjusted_start_round} (최근 {self.validation_window}회차)")
            start_round = adjusted_start_round

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

        # ✅ FIX: 데이터베이스에도 필터 통과율 저장 (핵심!)
        self._save_to_performance_tracker(results)

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
        
        # ✅ NEW: 최고 필터 통과율 확인 및 보호
        try:
            from ..core.continuous_improvement_engine import PerformanceTracker
            tracker = PerformanceTracker()
            best_pass_rate_perf = tracker.get_best_pass_rate_performance()

            if best_pass_rate_perf and best_pass_rate_perf.filter_pass_rate > 0:
                best_pass_rate = best_pass_rate_perf.filter_pass_rate
                current_pass_rate = results['overall_pass_rate']

                logging.info(f"\n📊 필터 통과율 비교:")
                logging.info(f"   현재 통과율: {current_pass_rate:.2f}%")
                logging.info(f"   역대 최고 통과율: {best_pass_rate:.2f}%")

                # ✅ PROTECTION: 역대 최고 통과율보다 낮으면 경고 및 롤백 제안
                if current_pass_rate < best_pass_rate:
                    drop_amount = best_pass_rate - current_pass_rate
                    logging.warning(f"\n🚨 필터 통과율 하락 감지!")
                    logging.warning(f"   하락폭: -{drop_amount:.2f}%p")
                    logging.warning(f"   역대 최고 통과율({best_pass_rate:.2f}%)보다 낮습니다!")
                    logging.warning(f"   최고 성능 설정으로 롤백을 권장합니다.")

                    # 5%p 이상 하락 시 자동 롤백 트리거
                    if drop_amount >= 5.0:
                        logging.error(f"🔴 심각한 통과율 하락 감지! (>{drop_amount:.1f}%p)")
                        logging.error(f"   자동 롤백을 실행합니다...")
                        try:
                            from ..core.continuous_improvement_engine import ContinuousImprovementEngine
                            engine = ContinuousImprovementEngine(db_manager=self.db_manager)
                            success = engine.rollback_to_best_pass_rate()
                            if success:
                                logging.info(f"   ✅ 최고 성능 설정으로 롤백 완료")
                            else:
                                logging.error(f"   ❌ 롤백 실패")
                        except Exception as e:
                            logging.error(f"   롤백 실패: {e}")

        except ImportError:
            pass  # PerformanceTracker 없으면 스킵
        except Exception as e:
            logging.error(f"통과율 보호 체크 실패: {e}")

        # 경고 메시지 및 자동 조정
        if results['overall_pass_rate'] < 90:
            # FIX: Removed \n prefix to avoid empty WARNING lines + Added range info
            logging.warning(
                f"⚠️ 주의: 전체 통과율이 {results['overall_pass_rate']:.2f}%로 낮습니다! "
                f"(검증: {results['total_rounds']}개 회차, {results['overall_pass_count']}개 통과)"
            )
            logging.warning("필터 기준을 재조정해야 합니다.")

            # 85% 미만이면 자동 조정 실행
            if results['overall_pass_rate'] < 85:
                # FIX: Removed \n prefix to avoid empty WARNING lines
                logging.warning("🔄 필터 자동 조정을 시작합니다...")
                self._trigger_auto_adjustment(results)
    
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

    def _trigger_auto_adjustment(self, validation_results: Dict[str, Any]):
        """자동 필터 조정 실행

        Args:
            validation_results: 검증 결과
        """
        try:
            from ..core.filter_auto_adjuster import FilterAutoAdjuster

            # FilterAutoAdjuster 초기화
            auto_adjuster = FilterAutoAdjuster(self.db_manager, self.filter_manager)

            # 조정 필요성 확인
            if auto_adjuster.check_need_adjustment(validation_results):
                logging.info("🔧 필터 자동 조정 시스템을 실행합니다...")

                # 최적화 기준 생성
                optimized_criteria = self.suggest_optimized_criteria(validation_results, target_pass_rate=95)

                # 자동 조정 적용
                result = auto_adjuster.apply_optimized_criteria(optimized_criteria, validation_results)
                if result:
                    # 조정 요약 출력
                    summary = auto_adjuster.get_adjustment_summary()
                    if summary:
                        logging.info("✅ 필터 자동 조정이 완료되었습니다.")
                        logging.info("⚠️ 변경사항이 적용되려면 프로그램을 재시작해야 합니다.")
                        logging.info(summary)
                    else:
                        logging.info("✅ 현재 필터 설정이 적절하여 조정이 필요하지 않습니다.")
                else:
                    logging.error("❌ 필터 자동 조정 중 오류가 발생했습니다.")
            else:
                logging.info("ℹ️ 현재 필터 상태로는 자동 조정이 불필요합니다.")

        except Exception as e:
            logging.error(f"필터 자동 조정 중 오류 발생: {e}")
            import traceback
            logging.debug(traceback.format_exc())

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

    def _save_to_performance_tracker(self, results: Dict[str, Any]):
        """검증 결과를 PerformanceTracker 데이터베이스에 저장

        이 메서드가 핵심입니다!
        FilterValidator는 82.35%를 계산하지만 JSON에만 저장했습니다.
        이제 데이터베이스에도 저장하여 프로그램 재시작 시에도 유지됩니다.

        Args:
            results: 검증 결과 딕셔너리 (overall_pass_rate 포함)
        """
        try:
            # 모듈 레벨 PerformanceTracker 사용 (패치 가능)
            from ..core.continuous_improvement_engine import PerformanceMetrics
            from datetime import datetime

            tracker = PerformanceTracker()

            # PerformanceMetrics 객체 생성
            metrics = PerformanceMetrics(
                avg_matches=0,  # FilterValidator에서는 매치 수 계산 안 함
                best_match=0,
                accuracy_3plus=0,
                ml_inclusion_rate=0,
                combination_count=0,
                threshold=0,
                ml_bypass_filters=0,
                ml_weight=0,
                filter_pass_rate=results['overall_pass_rate'],  # ✅ 핵심: 계산된 통과율
                timestamp=datetime.now(),
                session_id=None
            )

            # 데이터베이스에 저장
            tracker.save_performance_result(
                metrics=metrics,
                round_number=None,  # 특정 회차가 아님
                is_baseline=False
            )

            logging.info(f"✅ [DB 저장 완료] 필터 통과율 {results['overall_pass_rate']:.2f}% → continuous_improvement.db")

        except Exception as e:
            logging.error(f"❌ [DB 저장 실패] 필터 통과율 저장 중 오류: {e}")
            import traceback
            logging.error(traceback.format_exc())


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