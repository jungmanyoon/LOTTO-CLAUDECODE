#!/usr/bin/env python3
"""
통합 필터 관리 시스템
AdaptiveProbabilityFilter와 개별 필터들을 통합 관리
"""
import logging
from typing import Dict, List, Any, Optional
import time
from datetime import datetime
import json

class IntegratedFilterManager:
    """
    통합 필터 관리자
    - 확률 기반 필터링과 개별 필터를 통합
    - 매주 자동으로 필터 기준 업데이트
    - 동적 필터 관리
    """
    
    def __init__(self, db_manager, probability_threshold: float = 0.1):
        """
        Args:
            db_manager: 데이터베이스 매니저
            probability_threshold: 확률 임계값 (%) - 기본값 0.1%로 완화
        """
        self.db_manager = db_manager
        self.probability_threshold = probability_threshold

        # ML 관련 설정 (기본값)
        self.ml_bypass_filters = None  # update_config()로 설정됨
        self.ml_weight = None  # update_config()로 설정됨

        # 적응형 필터 초기화
        from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
        self.adaptive_filter = AdaptiveProbabilityFilter(
            db_manager,
            probability_threshold
        )

        # 기존 FilterManager 초기화
        from src.core.filter_manager import FilterManager
        self.filter_manager = FilterManager(db_manager)

        # 필터 업데이트 히스토리
        self.update_history = []

        # 필터 성능 추적
        self.filter_performance = {}

        # ThresholdManager Observer 등록 (임계값 변경 시 자동 업데이트)
        from src.core.threshold_manager import get_threshold_manager
        self.threshold_manager = get_threshold_manager()
        self.threshold_manager.register_observer(self._on_threshold_change)
        logging.debug("[통합 필터] ThresholdManager Observer 등록 완료")

        logging.info(f"[통합 필터] 초기화 완료 (임계값: {probability_threshold}%)")

    @property
    def filters(self):
        """FilterValidator 호환성을 위한 filters 속성 (내부 filter_manager.filters 반환)"""
        return self.filter_manager.filters

    def _on_threshold_change(self, param: str, old_value, new_value):
        """
        ThresholdManager에서 설정 변경 시 자동 호출되는 Observer 콜백

        Args:
            param: 변경된 파라미터 이름
            old_value: 이전 값
            new_value: 새 값
        """
        if param in ("threshold", "global_probability_threshold"):
            logging.info(f"[통합 필터] 임계값 변경 감지: {float(old_value):.2f}% → {float(new_value):.2f}%")

            # 1. 내부 임계값 업데이트
            self.probability_threshold = float(new_value)

            # 2. AdaptiveProbabilityFilter 임계값 업데이트
            self.adaptive_filter.probability_threshold = float(new_value)

            # 3. 패턴 재분석 및 dynamic_criteria 재계산
            self.adaptive_filter._reload_patterns()

            # 4. 새 dynamic_criteria로 개별 필터 업데이트
            dynamic_criteria = self.adaptive_filter.generate_dynamic_criteria()
            self._update_individual_filters(dynamic_criteria)

            logging.info(f"[통합 필터] 임계값 변경에 따른 필터 기준 재계산 완료")

    def update_config(self, probability_threshold=None, ml_bypass_filters=None, ml_weight=None):
        """
        동적으로 필터 설정 업데이트 (Optuna 최적화용)

        Args:
            probability_threshold: 확률 임계값 (%)
            ml_bypass_filters: ML 바이패스 필터 수
            ml_weight: ML 가중치
        """
        updated = []

        if probability_threshold is not None and probability_threshold != self.probability_threshold:
            self.probability_threshold = probability_threshold
            self.adaptive_filter.probability_threshold = probability_threshold
            # 패턴 재분석 (임계값 변경 반영)
            self.adaptive_filter._reload_patterns()
            # [HOT] FIX: dynamic_criteria 재계산 및 개별 필터 업데이트
            dynamic_criteria = self.adaptive_filter.generate_dynamic_criteria()
            self._update_individual_filters(dynamic_criteria)
            updated.append(f"threshold={probability_threshold}")
            logging.info(f"[설정 업데이트] 확률 임계값: {probability_threshold}%")

        if ml_bypass_filters is not None:
            self.ml_bypass_filters = ml_bypass_filters
            updated.append(f"ml_bypass={ml_bypass_filters}")
            logging.info(f"[설정 업데이트] ML 바이패스: {ml_bypass_filters}")

        if ml_weight is not None:
            self.ml_weight = ml_weight
            updated.append(f"ml_weight={ml_weight}")
            logging.info(f"[설정 업데이트] ML 가중치: {ml_weight}")

        if updated:
            logging.info(f"[설정 업데이트] 완료: {', '.join(updated)}")

        return len(updated) > 0

    def apply_filters_streaming(self, latest_round: int) -> bool:
        """스트림 필터링 메서드 - FilterManager 호환"""
        return self.filter_manager.apply_filters_streaming(latest_round)

    def apply_filters(self, latest_round: int, mode: str = 'full', force: bool = False) -> bool:
        """
        통합 필터 적용 - AdaptiveProbabilityFilter의 임계값을 실제로 사용

        Args:
            latest_round: 적용할 회차
            mode: 필터링 모드 ('full', 'incremental')
            force: 강제 실행 여부

        Returns:
            성공 여부
        """
        try:
            logging.info(f"[통합 필터] 임계값 {self.probability_threshold}% 기준으로 필터링 시작")

            # 1. 먼저 개별 필터들 적용
            logging.info("[통합 필터] 1단계: 개별 필터 적용")
            result = self.filter_manager.apply_filters(latest_round, mode, force)

            # 2. AdaptiveProbabilityFilter로 추가 필터링
            logging.info(f"[통합 필터] 2단계: 확률 임계값 필터 적용 ({self.probability_threshold}%)")

            # 현재 필터링된 조합 수 확인
            before_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)
            logging.info(f"  - 개별 필터 후 조합 수: {before_count:,}개")

            if before_count > 500000:  # 너무 많으면 확률 필터 강화
                logging.info(f"  - 조합이 너무 많음. 확률 필터로 추가 제거 필요")

                # AdaptiveProbabilityFilter의 패턴 분석 기반 필터링
                filtered = self._apply_probability_filter(latest_round)

                # 결과 확인
                after_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)
                logging.info(f"  - 확률 필터 후 조합 수: {after_count:,}개")
                logging.info(f"  - 제거된 조합: {before_count - after_count:,}개")

            return result

        except Exception as e:
            logging.error(f"[통합 필터] 필터링 오류: {e}")
            return False

    def _apply_probability_filter(self, latest_round: int) -> bool:
        """확률 기반 추가 필터링"""
        try:
            # 패턴 분석 결과 가져오기
            patterns = self.adaptive_filter.patterns
            if not patterns:
                # 패턴이 없으면 분석 먼저 수행
                # [v5 FIX #2] 전체 역사 분석(기존 [:200]은 가장 오래된 200회 버그)
                winning_numbers = self.db_manager.get_all_winning_numbers()
                patterns = self.adaptive_filter.analyze_patterns(winning_numbers)

            # 임계값 이하 패턴들로 필터링
            low_prob_patterns = self.adaptive_filter._identify_low_probability_patterns()

            # DB에서 조합들을 배치로 처리하며 필터링
            batch_size = 10000
            offset = 0
            removed_count = 0

            while True:
                # 배치 가져오기
                combinations = self.db_manager.combinations_db.get_filtered_combinations_batch(
                    latest_round, offset, batch_size
                )

                if not combinations:
                    break

                # 각 조합에 대해 확률 검사
                to_remove = []
                for combo in combinations:
                    if self._is_low_probability(combo, low_prob_patterns):
                        to_remove.append(combo)

                # 낮은 확률 조합 제거
                if to_remove:
                    self.db_manager.combinations_db.remove_combinations(latest_round, to_remove)
                    removed_count += len(to_remove)

                offset += batch_size

                if offset % 100000 == 0:
                    logging.info(f"    처리 진행: {offset:,}개 검사, {removed_count:,}개 제거")

            logging.info(f"  - 확률 필터 완료: 총 {removed_count:,}개 추가 제거")
            return True

        except Exception as e:
            logging.error(f"확률 필터 적용 오류: {e}")
            return False

    def _is_low_probability(self, combination: str, low_prob_patterns: Dict) -> bool:
        """조합이 낮은 확률 패턴인지 확인"""
        numbers = list(map(int, combination.split(',')))

        # 여러 패턴 체크
        checks = 0

        # 홀짝 패턴
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        if odd_count in low_prob_patterns.get('odd_even', []):
            checks += 1

        # 합 범위
        total = sum(numbers)
        for low_range in low_prob_patterns.get('sum_range', []):
            if low_range[0] <= total <= low_range[1]:
                checks += 1
                break

        # 연속 번호
        consecutive = 0
        for i in range(len(numbers) - 1):
            if numbers[i+1] - numbers[i] == 1:
                consecutive += 1
        if consecutive in low_prob_patterns.get('consecutive', []):
            checks += 1

        # 3개 이상 패턴 매치시 제거 (완화된 필터링)
        # 기존: checks >= 1 (너무 엄격)
        # 변경: checks >= 3 (여러 악조건이 겹칠 때만 제거)
        return checks >= 3

    def update_filters_weekly(self, new_round: int = None) -> Dict[str, Any]:
        """
        매주 실행: 새 당첨번호로 필터 업데이트
        
        Args:
            new_round: 새로운 회차 번호 (없으면 자동 감지)
            
        Returns:
            업데이트 결과
        """
        logging.info("="*60)
        logging.info("[통합 필터] 주간 필터 업데이트 시작")
        logging.info("="*60)
        
        start_time = time.time()
        
        try:
            # 1. 최신 회차 확인
            if new_round is None:
                new_round = self.db_manager.get_last_round()
            
            logging.info(f"1단계: 최신 회차 {new_round}번 데이터 확인")
            
            # 2. 과거 당첨번호 가져오기 (전체 역사)
            # [v5 FIX #2] 전체 역사 분석(기존 [:200]은 가장 오래된 200회 버그)
            winning_numbers = self.db_manager.get_all_winning_numbers()
            logging.info(f"2단계: 전체 {len(winning_numbers)}개 당첨번호로 패턴 분석")
            
            # 3. 적응형 필터로 패턴 분석
            patterns = self.adaptive_filter.analyze_patterns(winning_numbers)
            
            # 패턴 통계 로깅
            self._log_pattern_statistics(patterns)
            
            # 4. 동적 기준 생성
            logging.info("3단계: 동적 필터 기준 생성")
            dynamic_criteria = self.adaptive_filter.generate_dynamic_criteria()
            
            # 5. 각 필터에 새 기준 적용
            logging.info("4단계: 개별 필터 업데이트")
            updated_filters = self._update_individual_filters(dynamic_criteria)
            
            # 6. DB에 새 기준 저장
            self.adaptive_filter.save_criteria_to_db(dynamic_criteria)
            
            # 7. 필터 성능 평가
            performance = self._evaluate_filter_performance(winning_numbers[-10:])
            
            # 8. 업데이트 히스토리 저장
            update_info = {
                'round': new_round,
                'timestamp': datetime.now().isoformat(),
                'threshold': self.probability_threshold,
                'patterns': patterns,
                'criteria': dynamic_criteria,
                'performance': performance,
                'updated_filters': updated_filters,
                'duration': time.time() - start_time
            }
            
            self.update_history.append(update_info)

            # [NR-원인3 FIX] combinations.db 풀 재생성(새 기준 적용).
            # 근거: 기존 update_filters_weekly는 criteria만 갱신하고 실제 815만->30만 풀을
            # 재생성하지 않아 '새 기준 vs 옛 풀' 불일치가 발생(새 회차 시 1217 풀 누락 등).
            # 이 메서드는 AutoScheduler 트리거 체인(_trigger_filter_update) 전용이며 main.py
            # 본 필터링과 호출 경로가 분리되어 있으므로 여기서 풀을 재필터링해야 예측이 최신 풀 사용.
            # (시작 동기화/수집후 안전망 경로는 main.py 본 필터링이 풀을 생성하므로 중복 없음)
            try:
                logging.info("5단계: combinations.db 풀 재생성(새 기준 적용)")
                pool_ok = self.apply_filters(new_round, mode='full', force=True)
                update_info['pool_regenerated'] = bool(pool_ok)
                logging.info(f"[통합 필터] 풀 재생성 {'완료' if pool_ok else '실패/스킵'}")
            except Exception as _pe:
                logging.error(f"[통합 필터] 풀 재생성 실패: {_pe}")
                update_info['pool_regenerated'] = False

            # 결과 요약 출력
            logging.info("\n" + "="*60)
            logging.info("[업데이트 완료]")
            logging.info(f"  - 회차: {new_round}")
            logging.info(f"  - 업데이트된 필터: {len(updated_filters)}개")
            logging.info(f"  - 풀 재생성: {update_info.get('pool_regenerated', False)}")
            logging.info(f"  - 소요 시간: {update_info['duration']:.1f}초")
            logging.info("="*60)

            return update_info
            
        except Exception as e:
            logging.error(f"주간 필터 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    def _update_individual_filters(self, criteria: Dict[str, Any]) -> List[str]:
        """개별 필터에 새 기준 적용"""
        updated = []

        for filter_name, filter_criteria in criteria.items():
            try:
                # 필터 이름 매핑 (동적 기준 → 필터 인스턴스 이름)
                filter_instance_name = filter_name
                if filter_name == 'arithmetic':
                    filter_instance_name = 'arithmetic_sequence'
                elif filter_name == 'geometric':
                    filter_instance_name = 'geometric_sequence'

                if filter_instance_name in self.filter_manager.filters:
                    # 기존 필터 업데이트
                    old_criteria = self.filter_manager.filters[filter_instance_name].criteria.copy()

                    # 필터별 필수 키 보장
                    updated_criteria = filter_criteria.copy()

                    # arithmetic_sequence와 geometric_sequence 필터에 exclude_lengths 보장
                    if filter_instance_name in ['arithmetic_sequence', 'geometric_sequence']:
                        if 'exclude_lengths' not in updated_criteria:
                            # 기존 criteria나 default에서 가져오기
                            if 'exclude_lengths' in old_criteria:
                                updated_criteria['exclude_lengths'] = old_criteria['exclude_lengths']
                            else:
                                # 기본값 설정
                                if filter_instance_name == 'arithmetic_sequence':
                                    updated_criteria['exclude_lengths'] = [5, 6]
                                else:  # geometric_sequence
                                    updated_criteria['exclude_lengths'] = [4, 5, 6]

                    self.filter_manager.filters[filter_instance_name].criteria = updated_criteria

                    # 변경 사항 로그
                    if old_criteria != updated_criteria:
                        logging.info(f"  [{filter_instance_name}] 필터 기준 업데이트")
                        self._log_criteria_changes(filter_instance_name, old_criteria, updated_criteria)
                        updated.append(filter_instance_name)

            except Exception as e:
                logging.error(f"  [{filter_name}] 필터 업데이트 실패: {e}")

        return updated
    
    def _log_criteria_changes(self, filter_name: str, old: Dict, new: Dict):
        """기준 변경 사항 로깅"""
        for key in new:
            if key not in old:
                logging.debug(f"    + {key}: {new[key]}")
            elif old[key] != new[key]:
                logging.debug(f"    ~ {key}: {old[key]} → {new[key]}")
    
    def _log_pattern_statistics(self, patterns: Dict[str, Any]):
        """패턴 통계 로깅"""
        logging.info("\n[패턴 분석 결과]")
        
        # match 패턴
        if 'match' in patterns:
            logging.info("  번호 일치 분포:")
            for count, pct in sorted(patterns['match'].items()):
                status = "제외" if pct <= self.probability_threshold else "유지"
                logging.info(f"    {count}개: {pct:.2f}% [{status}]")
        
        # 홀짝 패턴
        if 'odd_even' in patterns:
            logging.info("  홀수 개수 분포:")
            odd_dist = patterns['odd_even'].get('odd_distribution', {})
            for count, pct in sorted(odd_dist.items()):
                if pct > 0:
                    status = "제외" if pct <= self.probability_threshold else "유지"
                    logging.info(f"    {count}개: {pct:.2f}% [{status}]")
    
    def _evaluate_filter_performance(self, recent_winners: List[str]) -> Dict[str, float]:
        """필터 성능 평가"""
        performance = {}
        
        for filter_name, filter_obj in self.filter_manager.filters.items():
            try:
                # 최근 당첨번호가 필터를 통과하는지 확인
                pass_count = 0
                for winner in recent_winners:
                    if self._check_combination_passes_filter(winner, filter_obj):
                        pass_count += 1
                
                pass_rate = (pass_count / len(recent_winners)) * 100 if recent_winners else 0
                performance[filter_name] = pass_rate
                
            except Exception as e:
                logging.error(f"필터 성능 평가 실패 ({filter_name}): {e}")
                performance[filter_name] = -1
        
        return performance
    
    def _check_combination_passes_filter(self, combination: str, filter_obj) -> bool:
        """단일 조합이 필터를 통과하는지 확인"""
        try:
            result = filter_obj.apply([combination], 1182)
            return len(result) > 0
        except Exception as e:
            logging.error(f"통합 필터 적용 실패: {e}")
            return False
    
    def apply_all_filters(self, combinations: List[str], round_num: int) -> List[str]:
        """
        모든 필터 적용 (통합 방식)
        
        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호
            
        Returns:
            필터링된 조합 목록
        """
        logging.info(f"[통합 필터] 전체 필터링 시작 (입력: {len(combinations):,}개)")
        
        # 기존 FilterManager의 필터들 적용
        filtered = combinations
        for filter_name, filter_obj in self.filter_manager.filters.items():
            before_count = len(filtered)
            filtered = filter_obj.apply(filtered, round_num)
            after_count = len(filtered)
            
            if before_count != after_count:
                exclusion_rate = (1 - after_count/before_count) * 100
                logging.info(f"  [{filter_name}] {before_count:,} → {after_count:,} ({exclusion_rate:.1f}% 제외)")
        
        logging.info(f"[통합 필터] 필터링 완료 (출력: {len(filtered):,}개)")
        return filtered
    
    def refresh_combination_database(self, force: bool = False):
        """
        814만개 조합 재필터링
        
        Args:
            force: 강제 재필터링 여부
        """
        logging.info("\n" + "="*60)
        logging.info("[통합 필터] 전체 조합 DB 재필터링 시작")
        logging.info("="*60)
        
        try:
            # 전체 조합 수 확인
            total_count = self.db_manager.combinations_db.count_all_combinations()
            logging.info(f"전체 조합 수: {total_count:,}개")
            
            # 배치 처리
            batch_size = 100000
            filtered_total = 0
            
            for offset in range(0, total_count, batch_size):
                # 배치 가져오기
                batch = self._get_combinations_batch(offset, batch_size)
                
                if batch:
                    # 필터 적용
                    filtered = self.apply_all_filters(batch, self.db_manager.get_last_round())
                    filtered_total += len(filtered)
                    
                    # 진행률 출력
                    progress = ((offset + len(batch)) / total_count) * 100
                    logging.info(f"  진행률: {progress:.1f}% ({filtered_total:,}개 통과)")
            
            exclusion_rate = (1 - filtered_total/total_count) * 100
            logging.info(f"\n재필터링 완료: {total_count:,} → {filtered_total:,} ({exclusion_rate:.1f}% 제외)")
            
        except Exception as e:
            logging.error(f"재필터링 실패: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_combinations_batch(self, offset: int, limit: int) -> List[str]:
        """조합 배치 가져오기"""
        try:
            with self.db_manager.combinations_db._create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT combination FROM base_combinations LIMIT ? OFFSET ?",
                    (limit, offset)
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"배치 로드 실패: {e}")
            return []
    
    def on_new_round_added(self, round_num: int):
        """
        새 회차 추가 시 자동 업데이트 핸들러

        Args:
            round_num: 새로 추가된 회차 번호
        """
        try:
            logging.info("="*60)
            logging.info(f"[통합 필터] 새 회차 자동 업데이트 시작: {round_num}회차")
            logging.info("="*60)

            # 1. 패턴 재분석
            logging.info("[통합 필터] 1단계: 패턴 재분석 중...")
            # [v5 FIX #2] 전체 역사 분석(기존 [:200]은 가장 오래된 200회 버그)
            winning_numbers = self.db_manager.get_all_winning_numbers()
            patterns = self.adaptive_filter.analyze_patterns(winning_numbers)
            self.db_manager.save_pattern_analysis(round_num, patterns)
            logging.info(f"[통합 필터] [O] 패턴 재분석 완료: {len(patterns)}개 패턴")

            # 2. 동적 기준 생성
            logging.info("[통합 필터] 2단계: 동적 필터 기준 생성 중...")
            dynamic_criteria = self.adaptive_filter.generate_dynamic_criteria()
            self.adaptive_filter.save_criteria_to_db(dynamic_criteria)
            logging.info(f"[통합 필터] [O] 동적 기준 생성 완료: {len(dynamic_criteria)}개 기준")

            # 3. 개별 필터 업데이트
            logging.info("[통합 필터] 3단계: 개별 필터 업데이트 중...")
            updated_filters = self._update_individual_filters(dynamic_criteria)
            logging.info(f"[통합 필터] [O] 필터 업데이트 완료: {len(updated_filters)}개 필터")

            # 4. 업데이트 히스토리 저장
            from datetime import datetime
            update_info = {
                'round': round_num,
                'timestamp': datetime.now().isoformat(),
                'threshold': self.probability_threshold,
                'patterns': len(patterns),
                'updated_filters': updated_filters,
                'auto_triggered': True
            }
            self.update_history.append(update_info)

            logging.info("="*60)
            logging.info(f"[통합 필터] [O] 새 회차 자동 업데이트 완료: {round_num}회차")
            logging.info("="*60)

        except Exception as e:
            logging.error(f"[통합 필터] 자동 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()

    def get_filtered_combinations(self, round_num: int = None) -> List[str]:
        """
        필터링된 조합 가져오기 (FilteredPoolEnsemblePredictor 호환성)

        Args:
            round_num: 특정 회차 조합 가져오기 (None이면 최신 회차)

        Returns:
            List[str]: 필터링된 조합 리스트
        """
        try:
            if round_num is None:
                round_num = self.db_manager.get_last_round()

            # FilterDB에서 필터링된 조합 가져오기
            if hasattr(self.db_manager, 'combinations_db'):
                filter_db = self.db_manager.combinations_db

                with filter_db._create_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT combination FROM filtered_combinations WHERE round = ?",
                        (round_num,)
                    )
                    combinations = [row[0] for row in cursor.fetchall()]

                    logging.debug(f"[IntegratedFilterManager] 회차 {round_num}: {len(combinations):,}개 조합 반환")
                    return combinations
            else:
                logging.warning("[IntegratedFilterManager] combinations_db not found")
                return []

        except Exception as e:
            logging.error(f"[IntegratedFilterManager] get_filtered_combinations 오류: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            'probability_threshold': self.probability_threshold,
            'active_filters': list(self.filter_manager.filters.keys()),
            'last_update': self.update_history[-1] if self.update_history else None,
            'total_updates': len(self.update_history)
        }