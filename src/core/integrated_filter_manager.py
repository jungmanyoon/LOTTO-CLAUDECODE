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
    
    def __init__(self, db_manager, probability_threshold: float = 1.0):
        """
        Args:
            db_manager: 데이터베이스 매니저
            probability_threshold: 확률 임계값 (%)
        """
        self.db_manager = db_manager
        self.probability_threshold = probability_threshold
        
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
        
        logging.info(f"[통합 필터] 초기화 완료 (임계값: {probability_threshold}%)")
    
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
            
            # 2. 과거 당첨번호 가져오기 (최근 200개)
            winning_numbers = self.db_manager.get_all_winning_numbers()[:200]
            logging.info(f"2단계: 최근 {len(winning_numbers)}개 당첨번호로 패턴 분석")
            
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
            
            # 결과 요약 출력
            logging.info("\n" + "="*60)
            logging.info("[업데이트 완료]")
            logging.info(f"  - 회차: {new_round}")
            logging.info(f"  - 업데이트된 필터: {len(updated_filters)}개")
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
                if filter_name in self.filter_manager.filters:
                    # 기존 필터 업데이트
                    old_criteria = self.filter_manager.filters[filter_name].criteria.copy()
                    self.filter_manager.filters[filter_name].criteria = filter_criteria
                    
                    # 변경 사항 로그
                    if old_criteria != filter_criteria:
                        logging.info(f"  [{filter_name}] 필터 기준 업데이트")
                        self._log_criteria_changes(filter_name, old_criteria, filter_criteria)
                        updated.append(filter_name)
                        
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
        except:
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
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            'probability_threshold': self.probability_threshold,
            'active_filters': list(self.filter_manager.filters.keys()),
            'last_update': self.update_history[-1] if self.update_history else None,
            'total_updates': len(self.update_history)
        }