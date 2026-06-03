"""
Mean Reversion (평균 회귀) 분석기

평균 회귀 이론: 장기간 미출현한 번호("냉각 번호")는 통계적으로
평균 출현 빈도로 회귀할 확률이 높다.

주요 기능:
1. 번호별 미출현 기간 추적
2. Hot/Cold 번호 분류
3. Mean Reversion 시그널 감지
4. 가중치 점수 제공 (점수화 시스템 연동)

참고: 검토사항.txt의 "Mean Reversion" 권장사항 기반 구현

---
[N-W16] 파이프라인 미연결 - TODO
현재 상태: 완전 구현됨, 예측 파이프라인에 미연결

연결 방법 (main.py 예측 파이프라인에 추가 필요):
    # 초기화
    from src.analysis.mean_reversion_analyzer import MeanReversionAnalyzer
    mean_reversion = MeanReversionAnalyzer(db_manager=db_manager)
    mean_reversion.update_statistics()

    # 예측 후 조합 점수화에 활용 (generate_final_predictions_enhanced 내부)
    for combo in candidate_combinations:
        mr_score = mean_reversion.calculate_combination_score(list(combo))
        # mr_score['score'] 를 조합 가중치에 반영 (0-100 범위)

    # 또는 풀 다양성 가중치로 활용
    cold_numbers = [num for num, _ in mean_reversion.get_cold_numbers(top_n=15)]
    reversion_signals = mean_reversion.get_reversion_signals()  # [(num, strength), ...]

공개 API 요약:
    - update_statistics(force=False)             : 통계 갱신
    - get_cold_numbers(top_n=10)                 : 미출현 상위 번호 리스트
    - get_hot_numbers(top_n=10)                  : 고빈도 번호 리스트
    - get_reversion_signals(threshold=None)      : 회귀 시그널 번호 리스트
    - calculate_combination_score(numbers)       : 조합의 MR 점수 (0-100)
    - get_classification(number)                 : 번호 분류 ('hot'/'cold'/'neutral')
    - get_number_stats(number)                   : 번호 상세 통계 딕셔너리
---
"""

from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
from datetime import datetime
import logging
import numpy as np


class MeanReversionAnalyzer:
    """
    평균 회귀 분석기

    번호별 출현 패턴을 분석하여 평균 회귀 가능성이 높은 번호를 감지
    """

    # 번호 분류 임계값
    HOT_PERCENTILE = 75      # 상위 25% = Hot
    COLD_PERCENTILE = 25     # 하위 25% = Cold
    REVERSION_THRESHOLD = 1.5  # 평균의 1.5배 이상 미출현 시 회귀 시그널

    def __init__(self, db_manager, config: Dict[str, Any] = None):
        """
        Mean Reversion 분석기 초기화

        Args:
            db_manager: 데이터베이스 매니저
            config: 설정 옵션
                - hot_percentile: Hot 번호 임계값 (기본: 75)
                - cold_percentile: Cold 번호 임계값 (기본: 25)
                - reversion_threshold: 회귀 시그널 임계값 (기본: 1.5)
        """
        self.db_manager = db_manager
        self.config = config or {}

        # 설정값 적용
        self.hot_percentile = self.config.get('hot_percentile', self.HOT_PERCENTILE)
        self.cold_percentile = self.config.get('cold_percentile', self.COLD_PERCENTILE)
        self.reversion_threshold = self.config.get('reversion_threshold', self.REVERSION_THRESHOLD)

        # 통계 데이터 캐시
        self._number_stats: Dict[int, Dict] = {}
        self._last_update_round: int = 0
        self._classification: Dict[int, str] = {}  # hot/cold/neutral

        logging.info(f"[MeanReversion] 분석기 초기화 (Hot: {self.hot_percentile}%, Cold: {self.cold_percentile}%, 회귀임계값: {self.reversion_threshold})")

    def update_statistics(self, force: bool = False) -> None:
        """
        통계 데이터 업데이트

        Args:
            force: 강제 업데이트 여부
        """
        try:
            current_round = self.db_manager.get_last_round()

            # 이미 최신이면 스킵
            if not force and current_round == self._last_update_round:
                return

            # 모든 당첨번호 가져오기
            winning_numbers = self.db_manager.get_all_winning_numbers()
            if not winning_numbers:
                logging.warning("[MeanReversion] 당첨번호 데이터 없음")
                return

            # 번호별 통계 초기화
            stats = {i: {
                'total_appearances': 0,
                'last_appeared_round': 0,
                'appearance_rounds': [],
                'absence_periods': []
            } for i in range(1, 46)}

            # 통계 계산
            for round_idx, numbers in enumerate(winning_numbers, 1):
                # 문자열인 경우 파싱
                if isinstance(numbers, str):
                    try:
                        numbers = [int(x) for x in numbers.split(',')]
                    except (ValueError, AttributeError):
                        continue

                if isinstance(numbers, (list, tuple)) and len(numbers) >= 6:
                    for num in numbers[:6]:  # 보너스 제외
                        if 1 <= num <= 45:
                            stats[num]['total_appearances'] += 1
                            stats[num]['last_appeared_round'] = round_idx
                            stats[num]['appearance_rounds'].append(round_idx)

            # 미출현 기간 계산
            total_rounds = len(winning_numbers)
            for num in range(1, 46):
                s = stats[num]
                s['rounds_since_appearance'] = total_rounds - s['last_appeared_round']

                # 출현 간격 계산
                rounds = s['appearance_rounds']
                if len(rounds) >= 2:
                    gaps = [rounds[i+1] - rounds[i] for i in range(len(rounds)-1)]
                    s['avg_gap'] = np.mean(gaps)
                    s['max_gap'] = max(gaps)
                    s['min_gap'] = min(gaps)
                    s['gap_std'] = np.std(gaps)
                else:
                    s['avg_gap'] = total_rounds / max(1, s['total_appearances'])
                    s['max_gap'] = s['rounds_since_appearance']
                    s['min_gap'] = 0
                    s['gap_std'] = 0

                # 예상 출현률 (전체 회차 대비 출현 확률)
                s['expected_rate'] = s['total_appearances'] / total_rounds if total_rounds > 0 else 0

                # 회귀 강도 계산 (현재 미출현 기간 / 평균 출현 간격)
                if s['avg_gap'] > 0:
                    s['reversion_strength'] = s['rounds_since_appearance'] / s['avg_gap']
                else:
                    s['reversion_strength'] = 0

                # 출현 빈도 기반 편차 점수
                theoretical_appearances = total_rounds * (6 / 45)  # 이론적 평균 출현 횟수
                s['deviation_score'] = (s['total_appearances'] - theoretical_appearances) / theoretical_appearances if theoretical_appearances > 0 else 0

            self._number_stats = stats
            self._last_update_round = current_round
            self._update_classification()

            logging.info(f"[MeanReversion] 통계 업데이트 완료 (회차: {current_round}, 총 {total_rounds}개 분석)")

        except Exception as e:
            logging.error(f"[MeanReversion] 통계 업데이트 오류: {e}")

    def _update_classification(self) -> None:
        """번호 분류 업데이트 (Hot/Cold/Neutral)"""
        if not self._number_stats:
            return

        # 출현 빈도 기준 분류
        appearances = [(num, stats['total_appearances'])
                      for num, stats in self._number_stats.items()]
        appearances.sort(key=lambda x: x[1], reverse=True)

        total_numbers = len(appearances)
        hot_threshold = int(total_numbers * (100 - self.hot_percentile) / 100)
        cold_threshold = int(total_numbers * self.cold_percentile / 100)

        self._classification = {}
        for idx, (num, _) in enumerate(appearances):
            if idx < hot_threshold:
                self._classification[num] = 'hot'
            elif idx >= total_numbers - cold_threshold:
                self._classification[num] = 'cold'
            else:
                self._classification[num] = 'neutral'

        hot_count = sum(1 for c in self._classification.values() if c == 'hot')
        cold_count = sum(1 for c in self._classification.values() if c == 'cold')
        logging.debug(f"[MeanReversion] 분류 완료 - Hot: {hot_count}, Cold: {cold_count}, Neutral: {45 - hot_count - cold_count}")

    def get_number_stats(self, number: int) -> Dict[str, Any]:
        """
        특정 번호의 통계 정보 반환

        Args:
            number: 조회할 번호 (1-45)

        Returns:
            번호 통계 정보 딕셔너리
        """
        if not self._number_stats:
            self.update_statistics()

        return self._number_stats.get(number, {})

    def get_classification(self, number: int) -> str:
        """
        번호의 분류 반환 (hot/cold/neutral)

        Args:
            number: 조회할 번호 (1-45)

        Returns:
            'hot', 'cold', 또는 'neutral'
        """
        if not self._classification:
            self.update_statistics()

        return self._classification.get(number, 'neutral')

    def get_cold_numbers(self, top_n: int = 10) -> List[Tuple[int, Dict]]:
        """
        가장 오래 미출현한 번호들 반환

        Args:
            top_n: 반환할 개수

        Returns:
            (번호, 통계정보) 튜플 리스트
        """
        if not self._number_stats:
            self.update_statistics()

        sorted_by_absence = sorted(
            self._number_stats.items(),
            key=lambda x: x[1]['rounds_since_appearance'],
            reverse=True
        )

        return sorted_by_absence[:top_n]

    def get_hot_numbers(self, top_n: int = 10) -> List[Tuple[int, Dict]]:
        """
        가장 자주 출현한 번호들 반환

        Args:
            top_n: 반환할 개수

        Returns:
            (번호, 통계정보) 튜플 리스트
        """
        if not self._number_stats:
            self.update_statistics()

        sorted_by_frequency = sorted(
            self._number_stats.items(),
            key=lambda x: x[1]['total_appearances'],
            reverse=True
        )

        return sorted_by_frequency[:top_n]

    def get_reversion_signals(self, threshold: float = None) -> List[Tuple[int, float]]:
        """
        평균 회귀 시그널이 있는 번호들 반환

        Args:
            threshold: 회귀 강도 임계값 (None이면 기본값 사용)

        Returns:
            (번호, 회귀강도) 튜플 리스트 (회귀강도 내림차순)
        """
        if not self._number_stats:
            self.update_statistics()

        threshold = threshold or self.reversion_threshold

        signals = []
        for num, stats in self._number_stats.items():
            strength = stats.get('reversion_strength', 0)
            if strength >= threshold:
                signals.append((num, strength))

        signals.sort(key=lambda x: x[1], reverse=True)
        return signals

    def calculate_combination_score(self, numbers: List[int]) -> Dict[str, Any]:
        """
        조합의 Mean Reversion 점수 계산

        Args:
            numbers: 6개 번호 리스트

        Returns:
            점수 정보 딕셔너리
        """
        if not self._number_stats:
            self.update_statistics()

        if len(numbers) != 6:
            return {'score': 50.0, 'error': '6개 번호가 필요합니다'}

        hot_count = 0
        cold_count = 0
        neutral_count = 0
        reversion_scores = []

        for num in numbers:
            classification = self.get_classification(num)
            if classification == 'hot':
                hot_count += 1
            elif classification == 'cold':
                cold_count += 1
            else:
                neutral_count += 1

            stats = self._number_stats.get(num, {})
            reversion_scores.append(stats.get('reversion_strength', 0))

        # 점수 계산 (0-100)
        # 이상적인 조합: Hot 2개, Cold 2개, Neutral 2개 (균형)
        balance_score = 100 - abs(hot_count - 2) * 10 - abs(cold_count - 2) * 10

        # 회귀 강도 점수 (높을수록 회귀 가능성)
        avg_reversion = np.mean(reversion_scores)
        reversion_bonus = min(20, avg_reversion * 10)  # 최대 20점 보너스

        # 최종 점수
        final_score = max(0, min(100, balance_score + reversion_bonus))

        return {
            'score': final_score,
            'hot_count': hot_count,
            'cold_count': cold_count,
            'neutral_count': neutral_count,
            'avg_reversion_strength': avg_reversion,
            'balance_score': balance_score,
            'reversion_bonus': reversion_bonus,
            'number_details': {
                num: {
                    'classification': self.get_classification(num),
                    'reversion_strength': self._number_stats.get(num, {}).get('reversion_strength', 0),
                    'rounds_since_appearance': self._number_stats.get(num, {}).get('rounds_since_appearance', 0)
                } for num in numbers
            }
        }

    def get_recommended_numbers(self, count: int = 6, strategy: str = 'balanced') -> List[int]:
        """
        전략에 따른 추천 번호 반환

        Args:
            count: 추천 번호 개수 (기본: 6)
            strategy: 전략
                - 'balanced': Hot/Cold/Neutral 균형
                - 'cold_bias': 냉각 번호 우선
                - 'reversion': 회귀 시그널 우선

        Returns:
            추천 번호 리스트
        """
        if not self._number_stats:
            self.update_statistics()

        if strategy == 'balanced':
            # Hot 2개, Cold 2개, Neutral 2개
            hot = [n for n, c in self._classification.items() if c == 'hot']
            cold = [n for n, c in self._classification.items() if c == 'cold']
            neutral = [n for n, c in self._classification.items() if c == 'neutral']

            import random
            recommended = []
            recommended.extend(random.sample(hot, min(2, len(hot))))
            recommended.extend(random.sample(cold, min(2, len(cold))))
            remaining = count - len(recommended)
            if remaining > 0 and neutral:
                recommended.extend(random.sample(neutral, min(remaining, len(neutral))))

            return sorted(recommended)[:count]

        elif strategy == 'cold_bias':
            cold_numbers = self.get_cold_numbers(count + 2)
            return sorted([num for num, _ in cold_numbers[:count]])

        elif strategy == 'reversion':
            signals = self.get_reversion_signals(threshold=1.0)
            if len(signals) >= count:
                return sorted([num for num, _ in signals[:count]])
            else:
                # 회귀 시그널 부족 시 cold_bias로 보충
                return self.get_recommended_numbers(count, 'cold_bias')

        else:
            logging.warning(f"[MeanReversion] 알 수 없는 전략: {strategy}")
            return self.get_recommended_numbers(count, 'balanced')

    def get_analysis_report(self) -> Dict[str, Any]:
        """
        전체 분석 리포트 생성

        Returns:
            분석 리포트 딕셔너리
        """
        if not self._number_stats:
            self.update_statistics()

        return {
            'last_update_round': self._last_update_round,
            'hot_numbers': self.get_hot_numbers(10),
            'cold_numbers': self.get_cold_numbers(10),
            'reversion_signals': self.get_reversion_signals(),
            'classification_summary': {
                'hot': sum(1 for c in self._classification.values() if c == 'hot'),
                'cold': sum(1 for c in self._classification.values() if c == 'cold'),
                'neutral': sum(1 for c in self._classification.values() if c == 'neutral')
            },
            'recommended': {
                'balanced': self.get_recommended_numbers(6, 'balanced'),
                'cold_bias': self.get_recommended_numbers(6, 'cold_bias'),
                'reversion': self.get_recommended_numbers(6, 'reversion')
            }
        }


# 모듈 테스트용 코드
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')

    from src.core.db_manager import DatabaseManager

    logging.basicConfig(level=logging.INFO)

    db = DatabaseManager()
    analyzer = MeanReversionAnalyzer(db)

    print("\n=== Mean Reversion 분석 ===")
    analyzer.update_statistics()

    print("\n[HOT] Hot Numbers (상위 10개):")
    for num, stats in analyzer.get_hot_numbers(10):
        print(f"  {num:2d}: {stats['total_appearances']}회 출현 ({stats['rounds_since_appearance']}회차 전)")

    print("\n[COLD] Cold Numbers (하위 10개):")
    for num, stats in analyzer.get_cold_numbers(10):
        print(f"  {num:2d}: {stats['total_appearances']}회 출현 ({stats['rounds_since_appearance']}회차 전)")

    print("\n[UP] Mean Reversion 시그널:")
    for num, strength in analyzer.get_reversion_signals()[:5]:
        print(f"  {num:2d}: 회귀 강도 {strength:.2f}")

    print("\n[TARGET] 추천 번호:")
    print(f"  균형 전략: {analyzer.get_recommended_numbers(6, 'balanced')}")
    print(f"  냉각 우선: {analyzer.get_recommended_numbers(6, 'cold_bias')}")
    print(f"  회귀 우선: {analyzer.get_recommended_numbers(6, 'reversion')}")

    # 조합 점수 테스트
    test_combo = [3, 17, 25, 31, 38, 44]
    score_result = analyzer.calculate_combination_score(test_combo)
    print(f"\n[STAT] 조합 점수 ({test_combo}):")
    print(f"  점수: {score_result['score']:.1f}")
    print(f"  Hot/Cold/Neutral: {score_result['hot_count']}/{score_result['cold_count']}/{score_result['neutral_count']}")
    print(f"  평균 회귀 강도: {score_result['avg_reversion_strength']:.2f}")
