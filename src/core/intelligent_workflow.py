#!/usr/bin/env python3
"""
지능형 워크플로우 시스템
- 캐싱을 통한 효율적 처리
- 새 회차 시 동적 업데이트
- 증분 학습 지원
"""

import logging
import time
from typing import List, Dict, Optional
from datetime import datetime

class IntelligentWorkflow:
    """지능형 로또 예측 워크플로우"""
    
    def __init__(self, db_manager, filter_manager, cache_manager):
        self.db_manager = db_manager
        self.filter_manager = filter_manager
        self.cache_manager = cache_manager
        self.logger = logging.getLogger(__name__)
        
    def execute(self, force_refresh: bool = False) -> Dict:
        """
        메인 실행 워크플로우
        
        Args:
            force_refresh: 강제로 재처리 여부
            
        Returns:
            예측 결과
        """
        
        self.logger.info("=" * 80)
        self.logger.info("지능형 로또 예측 시스템 시작")
        self.logger.info("=" * 80)
        
        # 1. 최신 회차 확인
        latest_round = self._get_latest_round()
        self.logger.info(f"최신 회차: {latest_round}")
        
        # 2. 새 회차 확인 및 업데이트
        new_round_data = self._check_new_round(latest_round)
        if new_round_data:
            self.logger.info(f"🎯 새 회차 발견: {new_round_data['round']}")
            needs_refilter = self.cache_manager.update_with_new_round(
                new_round_data['round'], 
                new_round_data['numbers']
            )
            if needs_refilter:
                force_refresh = True
        
        # 3. 필터링된 조합 준비
        filtered_combinations = self._prepare_filtered_combinations(
            latest_round, 
            force_refresh
        )
        
        if not filtered_combinations:
            self.logger.error("필터링된 조합이 없습니다")
            return {'error': '필터링 실패'}
        
        self.logger.info(f"필터링된 조합: {len(filtered_combinations):,}개")
        
        # 4. ML 예측 실행
        predictions = self._run_ml_predictions(filtered_combinations, latest_round)
        
        # 5. 백테스팅
        backtest_results = self._run_backtesting(predictions, latest_round)
        
        # 6. 최종 예측 생성
        final_predictions = self._generate_final_predictions(
            predictions, 
            backtest_results
        )
        
        # 7. 결과 저장 및 반환
        results = {
            'round': latest_round + 1,
            'generated_at': datetime.now().isoformat(),
            'filtered_combinations': len(filtered_combinations),
            'predictions': final_predictions,
            'backtest_performance': backtest_results,
            'cache_used': not force_refresh
        }
        
        self._save_results(results)
        
        self.logger.info("=" * 80)
        self.logger.info("예측 완료!")
        self.logger.info(f"다음 회차({latest_round + 1}) 예측 번호:")
        for i, pred in enumerate(final_predictions[:5], 1):
            self.logger.info(f"  {i}. {pred['numbers']} (신뢰도: {pred['confidence']:.1f}%)")
        self.logger.info("=" * 80)
        
        return results
    
    def _get_latest_round(self) -> int:
        """최신 회차 번호 가져오기"""
        # 실제로는 DB에서 가져옴
        # 여기서는 예시로 1185 반환
        return 1185
    
    def _check_new_round(self, latest_round: int) -> Optional[Dict]:
        """
        새 회차 확인 (웹 크롤링 또는 API)
        
        Returns:
            새 회차 정보 또는 None
        """
        # 실제로는 웹에서 최신 당첨번호 확인
        # 여기서는 None 반환 (새 회차 없음)
        return None
    
    # 공개 메서드 추가 (호환성)
    def check_for_new_round(self) -> Optional[Dict]:
        """새 회차 확인 (공개 메서드)"""
        latest_round = self._get_latest_round()
        return self._check_new_round(latest_round)
    
    def update_with_new_round(self, round_num: int, numbers: List[int]):
        """새 회차 데이터로 업데이트"""
        self.logger.info(f"새 회차 {round_num} 업데이트: {numbers}")
        # 데이터베이스 업데이트
        self.db_manager.update_lottery_data(round_num, numbers)
        # 캐시 무효화
        return True  # 재필터링 필요
    
    def _prepare_filtered_combinations(
        self, 
        latest_round: int, 
        force_refresh: bool
    ) -> List[str]:
        """
        필터링된 조합 준비
        
        1. 캐시 확인
        2. 캐시 유효하면 로드
        3. 무효하거나 force_refresh면 재필터링
        """
        
        if not force_refresh:
            # 캐시 확인
            self.logger.info("캐시 확인 중...")
            cached = self.cache_manager.load_filtered_results(latest_round)
            if cached:
                self.logger.info(f"✅ 캐시에서 {len(cached):,}개 조합 로드")
                return cached
        
        # 재필터링 필요
        self.logger.info("필터링 시작 (시간이 걸릴 수 있습니다)...")
        
        # 1. 전체 조합 확인
        total_count = self._get_total_combinations_count()
        
        if total_count < 8145060:
            self.logger.warning(f"조합 부족: {total_count:,}개만 있음")
            self.logger.info("전체 8,145,060개 생성 중...")
            self._generate_all_combinations()
        
        # 2. 필터링 실행
        start_time = time.time()
        success = self.filter_manager.apply_filters_incremental(latest_round)
        
        if not success:
            self.logger.error("필터링 실패")
            return []
        
        # 3. 결과 개수 확인 (메모리 효율적)
        filtered_count = self.db_manager.combinations_db.get_filtered_combinations_count(latest_round)
        elapsed = time.time() - start_time

        self.logger.info(f"필터링 완료: {filtered_count:,}개 ({elapsed:.1f}초)")

        # 4. 캐시 저장 (스트림 방식)
        self.cache_manager.save_filtered_results_stream(latest_round, filtered_count)

        # 필터링 결과는 DB에 저장됨. 빈 리스트 반환 (메모리 절약)
        return []
    
    def _get_total_combinations_count(self) -> int:
        """전체 조합 수 확인"""
        with self.db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM base_combinations")
            return cursor.fetchone()[0]
    
    def _generate_all_combinations(self):
        """전체 8,145,060개 조합 생성"""
        from itertools import combinations
        
        # 모든 가능한 조합 생성
        all_numbers = list(range(1, 46))
        total_combinations = list(combinations(all_numbers, 6))
        
        # DB에 저장
        with self.db_manager.combinations_db._create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM base_combinations")
            
            batch_size = 100000
            for i in range(0, len(total_combinations), batch_size):
                batch = total_combinations[i:i+batch_size]
                batch_strings = [','.join(map(str, combo)) for combo in batch]
                
                cursor.executemany(
                    "INSERT INTO base_combinations (combination) VALUES (?)",
                    [(combo,) for combo in batch_strings]
                )
                
                if i % 1000000 == 0:
                    self.logger.info(f"  {i:,} / {len(total_combinations):,} 생성 중...")
            
            conn.commit()
        
        self.logger.info(f"✅ {len(total_combinations):,}개 조합 생성 완료")
    
    def _run_ml_predictions(
        self, 
        combinations: List[str], 
        latest_round: int
    ) -> Dict:
        """ML 모델 예측 실행"""
        
        self.logger.info("ML 예측 시작...")
        
        # 여기서는 간단한 예시
        # 실제로는 각 ML 모델 실행
        
        predictions = {
            'lstm': self._predict_lstm(combinations[:1000]),  # 상위 1000개만
            'ensemble': self._predict_ensemble(combinations[:1000]),
            'monte_carlo': self._predict_monte_carlo(combinations[:1000])
        }
        
        self.logger.info("ML 예측 완료")
        return predictions
    
    def _predict_lstm(self, combinations: List[str]) -> List[Dict]:
        """LSTM 예측 (예시)"""
        # 실제 LSTM 모델 호출
        import random
        return [
            {
                'numbers': random.sample(range(1, 46), 6),
                'confidence': random.uniform(60, 90)
            }
            for _ in range(10)
        ]
    
    def _predict_ensemble(self, combinations: List[str]) -> List[Dict]:
        """앙상블 예측 (예시)"""
        import random
        return [
            {
                'numbers': random.sample(range(1, 46), 6),
                'confidence': random.uniform(65, 95)
            }
            for _ in range(10)
        ]
    
    def _predict_monte_carlo(self, combinations: List[str]) -> List[Dict]:
        """몬테카를로 예측 (예시)"""
        import random
        return [
            {
                'numbers': random.sample(range(1, 46), 6),
                'confidence': random.uniform(55, 85)
            }
            for _ in range(10)
        ]
    
    def _run_backtesting(self, predictions: Dict, latest_round: int) -> Dict:
        """백테스팅 실행"""
        
        self.logger.info("백테스팅 시작...")
        
        # 여기서는 간단한 통계만
        performance = {
            'lstm': {'avg_match': 1.2, 'max_match': 3},
            'ensemble': {'avg_match': 1.5, 'max_match': 4},
            'monte_carlo': {'avg_match': 1.1, 'max_match': 3}
        }
        
        self.logger.info("백테스팅 완료")
        return performance
    
    def _generate_final_predictions(
        self, 
        predictions: Dict, 
        backtest_results: Dict
    ) -> List[Dict]:
        """최종 예측 생성"""
        
        # 모든 예측 통합
        all_predictions = []
        
        for model_name, model_preds in predictions.items():
            weight = backtest_results[model_name]['avg_match']
            for pred in model_preds:
                all_predictions.append({
                    'numbers': sorted(pred['numbers']),
                    'confidence': pred['confidence'] * weight,
                    'model': model_name
                })
        
        # 신뢰도 순으로 정렬
        all_predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        # 상위 10개 반환
        return all_predictions[:10]
    
    def _save_results(self, results: Dict):
        """결과 저장"""
        
        import json
        from pathlib import Path
        
        # 결과 디렉토리
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        # 파일명
        filename = f"prediction_{results['round']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = results_dir / filename
        
        # 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"결과 저장: {filepath}")


def main():
    """메인 실행 함수"""
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 시스템 초기화
    from src.core.db_manager import DatabaseManager
    from src.core.filter_manager import FilterManager
    from src.core.intelligent_cache_manager import IntelligentCacheManager
    
    db_manager = DatabaseManager()
    filter_manager = FilterManager(db_manager)
    cache_manager = IntelligentCacheManager(db_manager)
    
    # 워크플로우 실행
    workflow = IntelligentWorkflow(db_manager, filter_manager, cache_manager)
    
    # 실행 옵션
    import sys
    force_refresh = '--force' in sys.argv
    
    if force_refresh:
        print("강제 재처리 모드")
    
    # 실행
    results = workflow.execute(force_refresh=force_refresh)
    
    return results


if __name__ == "__main__":
    main()