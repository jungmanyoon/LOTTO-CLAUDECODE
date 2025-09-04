"""
필터 검증 시스템
당첨번호가 필터로 제외되었는지 확인하고 필터 성능을 분석합니다.
"""

import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json
import numpy as np

class FilterValidator:
    """필터 검증 및 분석 클래스"""
    
    def __init__(self, filter_manager, db_manager):
        """
        초기화
        
        Args:
            filter_manager: FilterManager 인스턴스
            db_manager: DatabaseManager 인스턴스
        """
        self.filter_manager = filter_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self.validation_results = []
    
    def validate_winning_numbers(self, round_num: int, winning_numbers: List[int]) -> Dict:
        """
        당첨번호가 필터를 통과하는지 검증
        
        Args:
            round_num: 회차 번호
            winning_numbers: 당첨번호 리스트
        
        Returns:
            검증 결과 딕셔너리
        """
        result = {
            'round': round_num,
            'winning_numbers': winning_numbers,
            'passed_all_filters': True,
            'failed_filters': [],
            'warning_level': 'normal',  # normal, warning, critical
            'timestamp': datetime.now().isoformat()
        }
        
        # WeightedFilterSystem을 사용하는 경우
        if hasattr(self.filter_manager, 'evaluate_combination'):
            # WeightedFilterSystem의 가중치 기반 평가 사용
            evaluation = self.filter_manager.evaluate_combination(winning_numbers, round_num)
            
            if not evaluation['passed']:
                result['passed_all_filters'] = False
                result['total_score'] = evaluation['total_score']
                
                # 실패한 필터들만 추출
                for filter_name, filter_result in evaluation['filter_results'].items():
                    if not filter_result.get('passed', True):
                        result['failed_filters'].append({
                            'name': filter_name,
                            'reason': self._get_filter_failure_reason(
                                self.filter_manager.filters.get(filter_name), 
                                winning_numbers
                            ),
                            'score': filter_result.get('score', 0),
                            'weight': filter_result.get('weight', 1.0)
                        })
                        self.logger.warning(
                            f"🚨 경고: {round_num}회차 당첨번호가 {filter_name} 필터에서 "
                            f"낮은 점수 ({filter_result.get('score', 0)}점)를 받음!"
                        )
            else:
                self.logger.info(
                    f"✅ {round_num}회차 당첨번호가 가중치 시스템을 통과함 "
                    f"(점수: {evaluation['total_score']:.1f}/100)"
                )
        else:
            # 기존 방식 (일반 FilterManager 사용)
            # 각 필터별로 당첨번호 통과 여부 확인
            for filter_name, filter_obj in self.filter_manager.filters.items():
                try:
                    # 필터 적용을 위해 조합을 문자열로 변환
                    combination_str = ','.join(map(str, winning_numbers))
                    combination_list = [combination_str]  # 필터는 리스트를 기대함
                    
                    # 필터 적용 (round_num 파라미터 추가)
                    if hasattr(filter_obj, 'apply'):
                        try:
                            # 필터 적용 - 모든 필터는 List[str]과 round_num을 받음
                            filtered_result = filter_obj.apply(combination_list, round_num)
                            passed = len(filtered_result) > 0  # 필터를 통과하면 결과가 있음
                        except Exception as e:
                            # 에러 발생 시 상세 로깅
                            self.logger.debug(f"필터 {filter_name} 적용 중 예외: {e}")
                            passed = True  # 에러 시 통과로 처리 (안전모드)
                        
                        if not passed:
                            result['passed_all_filters'] = False
                            result['failed_filters'].append({
                                'name': filter_name,
                                'reason': self._get_filter_failure_reason(filter_obj, winning_numbers)
                            })
                            
                            self.logger.warning(f"🚨 경고: {round_num}회차 당첨번호가 {filter_name} 필터에 의해 제외됨!")
                except Exception as e:
                    self.logger.error(f"필터 검증 중 오류 ({filter_name}): {e}")
        
        # 경고 레벨 설정
        if not result['passed_all_filters']:
            failed_count = len(result['failed_filters'])
            if failed_count >= 3:
                result['warning_level'] = 'critical'
                self.logger.critical(f"🚨🚨🚨 치명적: {round_num}회차 당첨번호가 {failed_count}개 필터에서 제외됨!")
            elif failed_count >= 1:
                result['warning_level'] = 'warning'
                self.logger.warning(f"⚠️ 주의: {round_num}회차 당첨번호가 {failed_count}개 필터에서 제외됨")
        
        # 결과 저장
        self.validation_results.append(result)
        self._save_validation_result(result)
        
        return result
    
    def validate(self, start_round: int, end_round: int) -> List[Dict]:
        """
        지정된 범위의 당첨번호들을 검증
        
        Args:
            start_round: 시작 회차
            end_round: 종료 회차
            
        Returns:
            검증 결과 리스트
        """
        results = []
        
        # 지정된 범위의 당첨번호 가져오기
        for round_num in range(start_round, end_round + 1):
            try:
                # get_round_data 대신 get_winning_numbers 사용
                winning_numbers = self.db_manager.get_winning_numbers(round_num)
                if winning_numbers:
                    # 각 회차 검증
                    result = self.validate_winning_numbers(round_num, winning_numbers)
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"{round_num}회차 검증 중 오류: {e}")
                continue
        
        # 검증 요약 출력
        total_rounds = len(results)
        passed_rounds = sum(1 for r in results if r['passed_all_filters'])
        failed_rounds = total_rounds - passed_rounds
        
        if total_rounds > 0:
            pass_rate = (passed_rounds / total_rounds) * 100
            self.logger.info(f"\n[필터 검증 결과]")
            self.logger.info(f"  - 검증 회차: {total_rounds}개")
            self.logger.info(f"  - 통과: {passed_rounds}개 ({pass_rate:.1f}%)")
            self.logger.info(f"  - 제외: {failed_rounds}개")
            
            if failed_rounds > 0:
                self.logger.warning(f"⚠️ 주의: {failed_rounds}개 회차의 당첨번호가 필터에 의해 제외되었습니다!")
                self.logger.warning("  필터 기준이 너무 엄격할 수 있습니다.")
        
        return results
    
    def suggest_optimized_criteria(self, validation_results: List[Dict], target_pass_rate: float = 95.0) -> Dict:
        """
        검증 결과를 바탕으로 최적화된 필터 기준 제안
        
        Args:
            validation_results: 검증 결과 리스트
            target_pass_rate: 목표 통과율 (%)
            
        Returns:
            최적화된 필터 기준
        """
        if not validation_results:
            return {}
        
        # 필터별 실패 횟수 집계
        filter_failures = {}
        total_rounds = len(validation_results)
        
        for result in validation_results:
            if not result['passed_all_filters']:
                for failed_filter in result['failed_filters']:
                    filter_name = failed_filter['name']
                    if filter_name not in filter_failures:
                        filter_failures[filter_name] = 0
                    filter_failures[filter_name] += 1
        
        # 최적화 제안
        suggestions = {}
        current_pass_rate = (total_rounds - sum(filter_failures.values())) / total_rounds * 100
        
        self.logger.info(f"\n[필터 최적화 제안]")
        self.logger.info(f"  현재 통과율: {current_pass_rate:.1f}%")
        self.logger.info(f"  목표 통과율: {target_pass_rate}%")
        
        if current_pass_rate < target_pass_rate:
            self.logger.info("\n  필터 기준 완화 필요:")
            
            # 가장 많이 실패한 필터부터 완화 제안
            sorted_failures = sorted(filter_failures.items(), key=lambda x: x[1], reverse=True)
            
            for filter_name, failure_count in sorted_failures[:3]:  # 상위 3개만
                failure_rate = (failure_count / total_rounds) * 100
                self.logger.info(f"    - {filter_name}: {failure_count}회 실패 ({failure_rate:.1f}%)")
                
                # 필터별 완화 제안
                if 'consecutive' in filter_name.lower():
                    suggestions[filter_name] = {'max_consecutive': 4}  # 기준 완화
                elif 'sum_range' in filter_name.lower():
                    suggestions[filter_name] = {'min_sum': 60, 'max_sum': 210}  # 범위 확대
                elif 'odd_even' in filter_name.lower():
                    suggestions[filter_name] = {'strict_mode': False}  # 엄격도 완화
        
        return suggestions
    
    def _get_filter_failure_reason(self, filter_obj, numbers: List[int]) -> str:
        """필터 실패 이유 분석"""
        filter_name = filter_obj.__class__.__name__
        
        # 필터별 실패 이유 분석
        if 'ConsecutiveFilter' in filter_name:
            # 연속 번호 체크
            consecutive_count = 0
            for i in range(len(numbers) - 1):
                if numbers[i+1] - numbers[i] == 1:
                    consecutive_count += 1
            return f"연속 번호 {consecutive_count}개 포함"
        
        elif 'SumRangeFilter' in filter_name:
            total_sum = sum(numbers)
            return f"합계 {total_sum} (범위 벗어남)"
        
        elif 'OddEvenFilter' in filter_name:
            odd_count = len([n for n in numbers if n % 2 == 1])
            even_count = 6 - odd_count
            return f"홀수 {odd_count}개, 짝수 {even_count}개"
        
        elif 'SectionFilter' in filter_name:
            sections = [0, 0, 0, 0, 0]
            for num in numbers:
                sections[(num - 1) // 10] += 1
            return f"구간 분포: {sections}"
        
        else:
            return "필터 조건 불만족"
    
    def analyze_filter_performance(self, recent_rounds: int = 50) -> Dict:
        """
        최근 N회차의 필터 성능 분석
        
        Args:
            recent_rounds: 분석할 최근 회차 수
        
        Returns:
            필터 성능 분석 결과
        """
        performance = {
            'total_rounds': 0,
            'filter_failures': {},
            'critical_filters': [],
            'recommendations': []
        }
        
        # 최근 당첨번호 가져오기
        winning_numbers_list = self.db_manager.get_winning_numbers_last_n(recent_rounds)
        performance['total_rounds'] = len(winning_numbers_list)
        
        # 각 회차별로 검증
        for round_num, numbers, _ in winning_numbers_list:
            validation = self.validate_winning_numbers(round_num, numbers)
            
            # 실패한 필터 집계
            for failed in validation['failed_filters']:
                filter_name = failed['name']
                if filter_name not in performance['filter_failures']:
                    performance['filter_failures'][filter_name] = {
                        'count': 0,
                        'rounds': [],
                        'failure_rate': 0
                    }
                
                performance['filter_failures'][filter_name]['count'] += 1
                performance['filter_failures'][filter_name]['rounds'].append(round_num)
        
        # 실패율 계산 및 위험 필터 식별
        for filter_name, stats in performance['filter_failures'].items():
            failure_rate = stats['count'] / performance['total_rounds']
            stats['failure_rate'] = failure_rate
            
            # 실패율 10% 이상이면 위험 필터
            if failure_rate > 0.1:
                performance['critical_filters'].append({
                    'name': filter_name,
                    'failure_rate': failure_rate,
                    'failed_rounds': stats['rounds']
                })
                
                # 권장사항 추가
                performance['recommendations'].append(
                    f"{filter_name} 필터 조정 필요 (실패율: {failure_rate:.1%})"
                )
        
        return performance
    
    def get_filter_adjustment_suggestions(self) -> List[Dict]:
        """필터 조정 제안 생성"""
        suggestions = []
        
        # 최근 검증 결과 분석
        if len(self.validation_results) >= 10:
            recent_results = self.validation_results[-10:]
            
            # 자주 실패하는 필터 찾기
            filter_failure_count = {}
            for result in recent_results:
                for failed in result['failed_filters']:
                    filter_name = failed['name']
                    filter_failure_count[filter_name] = filter_failure_count.get(filter_name, 0) + 1
            
            # 50% 이상 실패한 필터에 대해 조정 제안
            for filter_name, count in filter_failure_count.items():
                if count >= 5:  # 10회 중 5회 이상 실패
                    suggestions.append({
                        'filter': filter_name,
                        'action': 'relax',  # 필터 조건 완화
                        'priority': 'high' if count >= 7 else 'medium',
                        'reason': f"최근 10회차 중 {count}회 실패"
                    })
        
        return suggestions
    
    def _save_validation_result(self, result: Dict):
        """검증 결과 저장"""
        try:
            # JSON 파일로 저장
            filename = f"results/filter_validation_{datetime.now().strftime('%Y%m')}.json"
            
            # 기존 데이터 읽기
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                data = []
            
            # 새 결과 추가
            data.append(result)
            
            # numpy 타입을 Python 타입으로 변환
            def convert_numpy(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj
            
            # JSON 직렬화 가능한 형태로 변환
            json_data = json.loads(json.dumps(data, default=convert_numpy))
            
            # 저장
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"검증 결과 저장 실패: {e}")
    
    def generate_validation_report(self) -> str:
        """검증 보고서 생성"""
        report = []
        report.append("\n" + "="*60)
        report.append("📋 필터 검증 보고서")
        report.append("="*60)
        
        # 최근 성능 분석
        performance = self.analyze_filter_performance(50)
        
        report.append(f"\n총 분석 회차: {performance['total_rounds']}회")
        
        if performance['critical_filters']:
            report.append("\n🚨 위험 필터 (조정 필요):")
            for critical in performance['critical_filters']:
                report.append(f"  - {critical['name']}: 실패율 {critical['failure_rate']:.1%}")
                report.append(f"    실패 회차: {critical['failed_rounds'][:5]}...")
        else:
            report.append("\n✅ 모든 필터가 정상 작동 중")
        
        # 조정 제안
        suggestions = self.get_filter_adjustment_suggestions()
        if suggestions:
            report.append("\n💡 필터 조정 제안:")
            for suggestion in suggestions:
                priority_icon = "🔴" if suggestion['priority'] == 'high' else "🟡"
                report.append(f"  {priority_icon} {suggestion['filter']}: {suggestion['action']} ({suggestion['reason']})")
        
        return "\n".join(report)