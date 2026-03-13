"""
필터 파이프라인 최적화 모듈
동적 우선순위 산정 및 효율성 기반 필터 정렬
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import time
import sqlite3
from collections import defaultdict
import numpy as np

@dataclass
class FilterStats:
    """필터 통계 정보"""
    name: str
    total_checked: int = 0
    total_excluded: int = 0
    avg_time_ms: float = 0.0
    exclusion_rate: float = 0.0
    efficiency_score: float = 0.0
    last_updated: float = field(default_factory=time.time)

class FilterOptimizer:
    """필터 파이프라인 최적화기"""

    # 기본 효율성 값 (fallback용)
    DEFAULT_EFFICIENCY = {
        'sum_range': 0.45,      # 가장 효율적
        'consecutive': 0.30,     # 높은 효율
        'max_gap': 0.25,        # 높은 효율
        'section': 0.22,        # 중간 효율
        'digit_sum': 0.20,      # 중간 효율
        'geometric_sequence': 0.20,
        'arithmetic_sequence': 0.18,
        'dispersion': 0.18,
        'odd_even': 0.15,
        'prime_composite': 0.15,
        'fixed_step': 0.15,
        'ten_section': 0.12,
        'last_digit': 0.10,
        'average': 0.10,
        'multiple': 0.08,
        'match': 0.05          # 가장 낮은 효율
    }

    def __init__(self, db_path: str = 'data/filter_stats.db'):
        """
        Args:
            db_path: 필터 통계 DB 경로
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.filter_stats: Dict[str, FilterStats] = {}
        self.warm_cache: Dict[str, float] = {}  # 워밍 캐시
        self._init_database()
        self._load_statistics()

    def _init_database(self):
        """필터 통계 데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filter_statistics (
                    filter_name TEXT PRIMARY KEY,
                    total_checked INTEGER DEFAULT 0,
                    total_excluded INTEGER DEFAULT 0,
                    avg_time_ms REAL DEFAULT 0.0,
                    exclusion_rate REAL DEFAULT 0.0,
                    efficiency_score REAL DEFAULT 0.0,
                    last_updated REAL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_efficiency
                ON filter_statistics(efficiency_score DESC)
            """)

    def _load_statistics(self):
        """DB에서 필터 통계 로드"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT filter_name, total_checked, total_excluded,
                           avg_time_ms, exclusion_rate, efficiency_score, last_updated
                    FROM filter_statistics
                """)
                for row in cursor:
                    stats = FilterStats(
                        name=row[0],
                        total_checked=row[1],
                        total_excluded=row[2],
                        avg_time_ms=row[3],
                        exclusion_rate=row[4],
                        efficiency_score=row[5],
                        last_updated=row[6]
                    )
                    self.filter_stats[stats.name] = stats

            self.logger.info(f"필터 통계 로드 완료: {len(self.filter_stats)}개")

        except Exception as e:
            self.logger.error(f"필터 통계 로드 실패: {str(e)}")
            # 실패 시 기본값 사용
            self._apply_default_efficiency()

    def _apply_default_efficiency(self):
        """기본 효율성 값 적용 (fallback)"""
        self.logger.info("기본 효율성 값 적용 (fallback)")
        for filter_name, efficiency in self.DEFAULT_EFFICIENCY.items():
            if filter_name not in self.filter_stats:
                self.filter_stats[filter_name] = FilterStats(
                    name=filter_name,
                    efficiency_score=efficiency,
                    exclusion_rate=efficiency  # 효율성을 제외율로 사용
                )

    def get_optimized_order(self, available_filters: List[str]) -> List[Tuple[str, float]]:
        """
        최적화된 필터 순서 반환

        Args:
            available_filters: 사용 가능한 필터 이름 리스트

        Returns:
            (필터명, 효율성) 튜플 리스트 (효율성 높은 순)
        """
        filter_scores = []

        for filter_name in available_filters:
            # 통계가 있으면 사용, 없으면 기본값
            if filter_name in self.filter_stats:
                score = self.filter_stats[filter_name].efficiency_score
            else:
                score = self.DEFAULT_EFFICIENCY.get(filter_name, 0.1)

            # 워밍 캐시가 있으면 가중 평균
            if filter_name in self.warm_cache:
                score = (score * 0.7 + self.warm_cache[filter_name] * 0.3)

            filter_scores.append((filter_name, score))

        # 효율성 높은 순으로 정렬
        filter_scores.sort(key=lambda x: x[1], reverse=True)

        self.logger.info("필터 순서 최적화 완료:")
        for name, score in filter_scores[:5]:  # 상위 5개만 로깅
            self.logger.info(f"  - {name}: {score:.3f}")

        return filter_scores

    def update_statistics(self, filter_name: str, checked: int, excluded: int, time_ms: float):
        """
        필터 통계 업데이트

        Args:
            filter_name: 필터 이름
            checked: 검사한 조합 수
            excluded: 제외한 조합 수
            time_ms: 처리 시간 (밀리초)
        """
        if filter_name not in self.filter_stats:
            self.filter_stats[filter_name] = FilterStats(name=filter_name)

        stats = self.filter_stats[filter_name]

        # 누적 통계 업데이트
        stats.total_checked += checked
        stats.total_excluded += excluded

        # 평균 시간 업데이트 (이동 평균)
        alpha = 0.3  # 이동 평균 가중치
        stats.avg_time_ms = (1 - alpha) * stats.avg_time_ms + alpha * time_ms

        # 제외율 계산
        if stats.total_checked > 0:
            stats.exclusion_rate = stats.total_excluded / stats.total_checked

        # 효율성 점수 계산 (제외율 / 시간)
        if stats.avg_time_ms > 0:
            stats.efficiency_score = (stats.exclusion_rate * 1000) / stats.avg_time_ms
        else:
            stats.efficiency_score = stats.exclusion_rate

        stats.last_updated = time.time()

        # DB 저장
        self._save_statistics(stats)

    def _save_statistics(self, stats: FilterStats):
        """통계를 DB에 저장"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO filter_statistics
                    (filter_name, total_checked, total_excluded, avg_time_ms,
                     exclusion_rate, efficiency_score, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (stats.name, stats.total_checked, stats.total_excluded,
                     stats.avg_time_ms, stats.exclusion_rate,
                     stats.efficiency_score, stats.last_updated))

        except Exception as e:
            self.logger.error(f"통계 저장 실패: {str(e)}")

    def warm_up_cache(self, sample_size: int = 50000) -> Dict[str, float]:
        """
        샘플 데이터로 필터 효율성 추정 (워밍 캐시)

        Args:
            sample_size: 샘플 크기

        Returns:
            필터별 추정 효율성
        """
        self.logger.info(f"워밍 캐시 생성 중 (샘플: {sample_size:,}개)")

        # 랜덤 샘플 생성
        from itertools import combinations
        import random

        all_combos = list(combinations(range(1, 46), 6))
        sample = random.sample(all_combos, min(sample_size, len(all_combos)))
        sample_array = np.array(sample)

        warm_results = {}

        # 각 필터별 간단한 테스트
        # 실제 필터 로직의 간소화 버전

        # 합계 범위 필터
        sums = np.sum(sample_array, axis=1)
        valid_sum = ((sums >= 83) & (sums <= 197)).sum()
        warm_results['sum_range'] = 1 - (valid_sum / sample_size)

        # 홀짝 필터
        odd_counts = np.sum(sample_array % 2 == 1, axis=1)
        valid_odd = ((odd_counts != 0) & (odd_counts != 6)).sum()
        warm_results['odd_even'] = 1 - (valid_odd / sample_size)

        # 연속 번호 필터 (간소화)
        consecutive_count = 0
        for combo in sample_array:
            sorted_combo = np.sort(combo)
            diffs = np.diff(sorted_combo)
            if np.any(diffs == 1):
                max_consecutive = np.max([len(list(g)) for k, g in
                                         __import__('itertools').groupby(diffs) if k == 1]) + 1
                if max_consecutive > 5:
                    consecutive_count += 1
        warm_results['consecutive'] = consecutive_count / sample_size

        # 나머지 필터는 기본값 사용
        for filter_name in self.DEFAULT_EFFICIENCY:
            if filter_name not in warm_results:
                warm_results[filter_name] = self.DEFAULT_EFFICIENCY[filter_name]

        self.warm_cache = warm_results
        self.logger.info(f"워밍 캐시 생성 완료")

        return warm_results

    def get_filter_report(self) -> str:
        """필터 효율성 리포트 생성"""
        lines = ["=" * 60]
        lines.append("필터 효율성 리포트")
        lines.append("=" * 60)

        # 효율성 순으로 정렬
        sorted_stats = sorted(
            self.filter_stats.values(),
            key=lambda x: x.efficiency_score,
            reverse=True
        )

        for stats in sorted_stats:
            lines.append(f"\n[{stats.name}]")
            lines.append(f"  검사: {stats.total_checked:,}개")
            lines.append(f"  제외: {stats.total_excluded:,}개")
            lines.append(f"  제외율: {stats.exclusion_rate:.2%}")
            lines.append(f"  평균 시간: {stats.avg_time_ms:.2f}ms")
            lines.append(f"  효율성 점수: {stats.efficiency_score:.3f}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def reset_statistics(self):
        """모든 통계 초기화"""
        self.filter_stats.clear()
        self.warm_cache.clear()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM filter_statistics")

        self._apply_default_efficiency()
        self.logger.info("필터 통계 초기화 완료")