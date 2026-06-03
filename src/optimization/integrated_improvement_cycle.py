#!/usr/bin/env python3
"""
통합 개선 사이클
- 회차별 필터 재적용
- 동적 백테스팅
- 실시간 개선 추적
"""
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import yaml


class IntegratedImprovementCycle:
    """통합 개선 사이클 관리자"""

    def __init__(self, db_manager, filter_manager, backtest_framework):
        """
        Args:
            db_manager: 데이터베이스 매니저
            filter_manager: 필터 매니저
            backtest_framework: 백테스팅 프레임워크
        """
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        self.backtest_framework = backtest_framework

        # 개선된 자동 개선 관리자
        from .improved_auto_improvement_manager import get_improved_manager
        self.improvement_manager = get_improved_manager()

        self.logger = logging.getLogger(__name__)

    def run_improvement_cycle(self, start_round: int = None, end_round: int = None,
                             window_size: int = 50) -> Dict[str, Any]:
        """통합 개선 사이클 실행

        Args:
            start_round: 시작 회차 (None이면 window_size만큼 이전)
            end_round: 종료 회차 (None이면 최신)
            window_size: 백테스팅 윈도우 크기

        Returns:
            Dict: 개선 사이클 결과
        """
        self.logger.info("="*60)
        self.logger.info("[SYNC] 통합 개선 사이클 시작")
        self.logger.info("="*60)

        # 회차 범위 설정
        latest_round = self.db_manager.get_last_round()
        if end_round is None:
            end_round = latest_round
        if start_round is None:
            start_round = max(1, end_round - window_size)

        self.logger.info(f"회차 범위: {start_round} ~ {end_round}")

        cycle_results = {
            'start_round': start_round,
            'end_round': end_round,
            'rounds_processed': 0,
            'improvements_found': 0,
            'threshold_adjustments': 0,
            'best_performance': 0.0,
            'worst_performance': float('inf'),
            'round_results': []
        }

        # 각 회차별로 처리
        for round_num in range(start_round, end_round + 1):
            self.logger.info(f"\n[회차 {round_num} 처리 시작]")

            round_result = self._process_single_round(round_num)
            cycle_results['round_results'].append(round_result)
            cycle_results['rounds_processed'] += 1

            # 개선 여부 확인
            if round_result.get('improved', False):
                cycle_results['improvements_found'] += 1

            # 임계값 조정 여부 확인
            if round_result.get('threshold_adjusted', False):
                cycle_results['threshold_adjustments'] += 1

            # 최고/최저 성능 추적
            performance = round_result.get('performance', 0.0)
            if performance > cycle_results['best_performance']:
                cycle_results['best_performance'] = performance
            if performance < cycle_results['worst_performance']:
                cycle_results['worst_performance'] = performance

            # 진행 상황 로그
            self._log_progress(round_num, end_round, cycle_results)

            # 짧은 대기 (시스템 부하 방지)
            time.sleep(0.1)

        # 최종 결과 요약
        self._log_cycle_summary(cycle_results)

        return cycle_results

    def _process_single_round(self, round_num: int) -> Dict[str, Any]:
        """단일 회차 처리

        Args:
            round_num: 회차 번호

        Returns:
            Dict: 회차 처리 결과
        """
        round_result = {
            'round': round_num,
            'timestamp': datetime.now().isoformat(),
            'filter_updated': False,
            'backtest_completed': False,
            'improved': False,
            'threshold_adjusted': False,
            'performance': 0.0,
            'errors': []
        }

        try:
            # 1. 필터 업데이트 (해당 회차까지의 데이터로)
            self.logger.info(f"  [1] 필터 업데이트 중...")
            filter_updated = self._update_filters_for_round(round_num)
            round_result['filter_updated'] = filter_updated

            if filter_updated:
                self.logger.info(f"     [O] 필터 업데이트 완료")
            else:
                self.logger.warning(f"     [X] 필터 업데이트 실패")

            # 2. 업데이트된 필터로 백테스팅
            self.logger.info(f"  [2] 백테스팅 실행 중...")
            backtest_results = self._run_backtest_for_round(round_num)
            round_result['backtest_completed'] = True

            # 3. 성능 평가 및 개선 추적
            self.logger.info(f"  [3] 성능 평가 중...")
            improvement_info = self.improvement_manager.track_backtest_improved(
                backtest_results, round_num
            )

            round_result['improved'] = improvement_info.get('should_update', False)
            round_result['performance'] = improvement_info['new_performance'].get('overall', 0.0)

            if round_result['improved']:
                reasons = ', '.join(improvement_info.get('update_reasons', []))
                self.logger.info(f"     [O] 개선 발견: {reasons}")
            else:
                self.logger.info(f"     - 개선 없음")

            # 4. 임계값 동적 조정
            self.logger.info(f"  [4] 임계값 조정 검토 중...")
            old_threshold = self.improvement_manager.state.get('current_threshold', 1.0)
            new_threshold = self.improvement_manager.adjust_threshold_dynamically(
                round_result['performance']
            )

            if new_threshold != old_threshold:
                round_result['threshold_adjusted'] = True
                self.logger.info(f"     [O] 임계값 조정: {old_threshold:.2f} -> {new_threshold:.2f}")
            else:
                self.logger.info(f"     - 임계값 유지: {old_threshold:.2f}")

        except Exception as e:
            self.logger.error(f"회차 {round_num} 처리 중 오류: {e}")
            round_result['errors'].append(str(e))

        return round_result

    def _update_filters_for_round(self, round_num: int) -> bool:
        """특정 회차를 위한 필터 업데이트

        Args:
            round_num: 회차 번호

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # 해당 회차까지의 당첨번호 가져오기
            all_numbers = self.db_manager.get_all_numbers()  # Returns List[Tuple[round, numbers_str, date]]
            numbers_up_to_round = []

            for r, nums_str, _ in all_numbers:
                if r <= round_num:
                    # 이미 문자열 형식이므로 그대로 사용
                    numbers_up_to_round.append(nums_str)

            if not numbers_up_to_round:
                self.logger.warning(f"회차 {round_num}까지의 데이터가 없습니다.")
                return False

            # 적응형 필터가 있는 경우 패턴 재분석
            if hasattr(self.filter_manager, 'adaptive_filter'):
                self.filter_manager.adaptive_filter.analyze_patterns(numbers_up_to_round)
                self.logger.debug(f"회차 {round_num}까지 {len(numbers_up_to_round)}개 데이터로 패턴 분석")
                return True

            # IntegratedFilterManager인 경우
            elif hasattr(self.filter_manager, 'filter_manager'):
                if hasattr(self.filter_manager.filter_manager, 'adaptive_filter'):
                    self.filter_manager.filter_manager.adaptive_filter.analyze_patterns(numbers_up_to_round)
                    self.logger.debug(f"회차 {round_num}까지 {len(numbers_up_to_round)}개 데이터로 패턴 분석")
                    return True

            return False

        except Exception as e:
            self.logger.error(f"필터 업데이트 실패: {e}")
            return False

    def _run_backtest_for_round(self, round_num: int) -> Dict[str, Any]:
        """특정 회차에 대한 백테스팅 실행

        Args:
            round_num: 회차 번호

        Returns:
            Dict: 백테스팅 결과
        """
        try:
            # 백테스팅 윈도우 설정 (해당 회차 이전 50회차)
            start_round = max(1, round_num - 50)
            end_round = round_num

            # 백테스팅 실행
            results = self.backtest_framework.run_backtest(
                start_round=start_round,
                end_round=end_round
            )

            return results

        except Exception as e:
            self.logger.error(f"백테스팅 실행 실패: {e}")
            # 기본 결과 반환
            return {
                'performance_metrics': {
                    'model_performance': {
                        'lstm': {'avg_matches': 0.0},
                        'ensemble': {'avg_matches': 0.0},
                        'monte_carlo': {'avg_matches': 0.0}
                    }
                },
                'error': str(e)
            }

    def _log_progress(self, current_round: int, end_round: int, cycle_results: Dict):
        """진행 상황 로그"""
        progress = (current_round - cycle_results['start_round'] + 1) / \
                  (end_round - cycle_results['start_round'] + 1) * 100

        self.logger.info(
            f"\n[STAT] 진행률: {progress:.1f}% | "
            f"처리: {cycle_results['rounds_processed']} | "
            f"개선: {cycle_results['improvements_found']} | "
            f"임계값 조정: {cycle_results['threshold_adjustments']}"
        )

    def _log_cycle_summary(self, cycle_results: Dict):
        """사이클 요약 로그"""
        self.logger.info("\n" + "="*60)
        self.logger.info("[STAT] 통합 개선 사이클 요약")
        self.logger.info("="*60)

        self.logger.info(f"\n회차 범위: {cycle_results['start_round']} ~ {cycle_results['end_round']}")
        self.logger.info(f"처리된 회차: {cycle_results['rounds_processed']}")
        self.logger.info(f"개선 발견: {cycle_results['improvements_found']}")
        self.logger.info(f"임계값 조정: {cycle_results['threshold_adjustments']}")
        self.logger.info(f"최고 성능: {cycle_results['best_performance']:.3f}")
        self.logger.info(f"최저 성능: {cycle_results['worst_performance']:.3f}")

        # 개선률 계산
        if cycle_results['rounds_processed'] > 0:
            improvement_rate = cycle_results['improvements_found'] / cycle_results['rounds_processed'] * 100
            self.logger.info(f"개선률: {improvement_rate:.1f}%")

        # 개선된 자동 개선 관리자의 상태 보고서 출력
        report = self.improvement_manager.get_status_report()
        self.logger.info(report)

    def run_adaptive_cycle(self, num_iterations: int = 5) -> List[Dict[str, Any]]:
        """적응형 개선 사이클 실행 (반복 학습)

        Args:
            num_iterations: 반복 횟수

        Returns:
            List: 각 반복의 결과
        """
        self.logger.info("\n" + "[SYNC]"*20)
        self.logger.info("[BRAIN] 적응형 개선 사이클 시작")
        self.logger.info("[SYNC]"*20)

        all_results = []
        latest_round = self.db_manager.get_last_round()

        for iteration in range(1, num_iterations + 1):
            self.logger.info(f"\n\n[반복 {iteration}/{num_iterations}]")
            self.logger.info("-"*40)

            # 각 반복마다 다른 윈도우로 학습
            window_size = 50 + (iteration - 1) * 10  # 50, 60, 70, ...
            start_round = max(1, latest_round - window_size)

            # 개선 사이클 실행
            cycle_result = self.run_improvement_cycle(
                start_round=start_round,
                end_round=latest_round,
                window_size=window_size
            )

            cycle_result['iteration'] = iteration
            all_results.append(cycle_result)

            # 성능이 목표에 도달하면 조기 종료
            if cycle_result['best_performance'] >= 1.5:
                self.logger.info(f"\n[TARGET] 목표 성능 달성! (성능: {cycle_result['best_performance']:.3f})")
                break

            # 반복 간 짧은 대기
            time.sleep(1)

        # 최종 요약
        self._log_adaptive_summary(all_results)

        return all_results

    def _log_adaptive_summary(self, all_results: List[Dict[str, Any]]):
        """적응형 사이클 요약 로그"""
        self.logger.info("\n" + "="*60)
        self.logger.info("[BRAIN] 적응형 개선 사이클 최종 요약")
        self.logger.info("="*60)

        total_improvements = sum(r['improvements_found'] for r in all_results)
        total_rounds = sum(r['rounds_processed'] for r in all_results)
        best_performance = max(r['best_performance'] for r in all_results)

        self.logger.info(f"\n총 반복: {len(all_results)}")
        self.logger.info(f"총 처리 회차: {total_rounds}")
        self.logger.info(f"총 개선 발견: {total_improvements}")
        self.logger.info(f"최고 성능 달성: {best_performance:.3f}")

        # 반복별 성능 추이
        self.logger.info("\n반복별 성능 추이:")
        for result in all_results:
            self.logger.info(
                f"  반복 {result['iteration']}: "
                f"최고 {result['best_performance']:.3f} / "
                f"개선 {result['improvements_found']}"
            )


def run_integrated_improvement(db_manager, filter_manager, backtest_framework,
                              mode: str = 'single', **kwargs) -> Any:
    """통합 개선 실행 헬퍼 함수

    Args:
        db_manager: 데이터베이스 매니저
        filter_manager: 필터 매니저
        backtest_framework: 백테스팅 프레임워크
        mode: 실행 모드 ('single' 또는 'adaptive')
        **kwargs: 추가 파라미터

    Returns:
        실행 결과
    """
    cycle = IntegratedImprovementCycle(db_manager, filter_manager, backtest_framework)

    if mode == 'adaptive':
        num_iterations = kwargs.get('num_iterations', 5)
        return cycle.run_adaptive_cycle(num_iterations)
    else:
        start_round = kwargs.get('start_round')
        end_round = kwargs.get('end_round')
        window_size = kwargs.get('window_size', 50)
        return cycle.run_improvement_cycle(start_round, end_round, window_size)