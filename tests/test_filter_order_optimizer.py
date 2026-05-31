#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
필터 실행 순서 최적화기 테스트

Phase 3.2: 필터 상관관계 분석 및 최적화
- 상관관계 계산 테스트
- 최적화된 필터 순서 테스트
- 병렬 실행 그룹 분리 테스트
- 커버리지 계산 테스트
"""

import pytest
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.filter_order_optimizer import (
    FilterOrderOptimizer,
    FilterCorrelation,
    FilterEfficiency,
)


class TestFilterOrderOptimizerInit:
    """초기화 테스트"""

    def test_init_empty(self):
        """빈 초기화 테스트"""
        optimizer = FilterOrderOptimizer()

        assert optimizer.filter_results == {}
        assert optimizer.correlations == {}
        assert not optimizer._correlation_calculated

    def test_init_with_results(self):
        """결과 데이터로 초기화"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)

        assert optimizer.filter_results == results


class TestCalculateCorrelations:
    """상관관계 계산 테스트"""

    def test_basic_correlation(self):
        """기본 상관관계 계산"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'filter_b': {'filtered_rounds_list': [3, 4, 5, 6, 7]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        assert 'filter_a' in correlations
        assert 'filter_b' in correlations['filter_a']

        corr = correlations['filter_a']['filter_b']
        assert corr.overlap_count == 3
        assert abs(corr.jaccard_similarity - 3/7) < 0.01

    def test_match_filter_excluded(self):
        """match 필터 제외 확인"""
        results = {
            'match': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'filter_a': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        assert 'match' not in correlations

    def test_no_overlap(self):
        """중복 없는 경우"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [4, 5, 6]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        corr = correlations['filter_a']['filter_b']
        assert corr.overlap_count == 0
        assert corr.jaccard_similarity == 0.0

    def test_complete_overlap(self):
        """완전 중복"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        corr = correlations['filter_a']['filter_b']
        assert corr.jaccard_similarity == 1.0

    def test_empty_filter(self):
        """빈 필터 처리"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': []}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        corr = correlations['filter_a']['filter_b']
        assert corr.overlap_count == 0


class TestGetHighCorrelationPairs:
    """높은 상관관계 쌍 테스트"""

    def test_high_correlation_pairs(self):
        """높은 상관관계 쌍 반환"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'filter_b': {'filtered_rounds_list': [1, 2, 3, 4, 6]},  # 80% 중복
            'filter_c': {'filtered_rounds_list': [10, 11, 12, 13, 14]}  # 0% 중복
        }
        optimizer = FilterOrderOptimizer(results)

        pairs = optimizer.get_high_correlation_pairs(threshold=0.5)

        # filter_a, filter_b는 높은 상관관계
        assert len(pairs) >= 1
        assert any(
            ('filter_a' in pair[:2] and 'filter_b' in pair[:2])
            for pair in pairs
        )

    def test_no_high_correlation(self):
        """높은 상관관계 없음"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [10, 11, 12]}
        }
        optimizer = FilterOrderOptimizer(results)

        pairs = optimizer.get_high_correlation_pairs(threshold=0.5)

        assert len(pairs) == 0

    def test_duplicate_pairs_removed(self):
        """중복 쌍 제거 확인"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)

        pairs = optimizer.get_high_correlation_pairs(threshold=0.5)

        # (a, b)와 (b, a)가 중복되지 않아야 함
        assert len(pairs) == 1


class TestGetRedundantFilters:
    """중복 필터 식별 테스트"""

    def test_identify_redundant_filters(self):
        """중복 필터 식별"""
        results = {
            'sum_range': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'average': {'filtered_rounds_list': [1, 2, 3, 4, 5]}  # 완전 중복
        }
        optimizer = FilterOrderOptimizer(results)

        redundant = optimizer.get_redundant_filters(threshold=0.7)

        # average가 sum_range보다 효율 낮으므로 제거 후보
        assert 'average' in redundant

    def test_no_redundant_filters(self):
        """중복 필터 없음"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [10, 11, 12]}
        }
        optimizer = FilterOrderOptimizer(results)

        redundant = optimizer.get_redundant_filters(threshold=0.7)

        assert len(redundant) == 0


class TestGetOptimizedOrder:
    """최적화된 필터 순서 테스트"""

    def test_order_by_efficiency(self):
        """효율성 순 정렬"""
        optimizer = FilterOrderOptimizer()

        filters = ['average', 'sum_range', 'multiple']
        ordered = optimizer.get_optimized_order(filters)

        # sum_range(0.45) > average(0.10) > multiple(0.08)
        assert ordered[0][0] == 'sum_range'
        assert ordered[-1][0] == 'multiple'

    def test_dynamic_efficiency_override(self):
        """동적 효율성 덮어쓰기"""
        optimizer = FilterOrderOptimizer()

        filters = ['average', 'sum_range']
        dynamic = {'average': 0.9}  # average 효율 높임

        ordered = optimizer.get_optimized_order(filters, dynamic_efficiency=dynamic)

        # average가 동적 값(0.9)로 1위
        assert ordered[0][0] == 'average'

    def test_unknown_filter_default(self):
        """알 수 없는 필터 기본값"""
        optimizer = FilterOrderOptimizer()

        filters = ['unknown_filter', 'sum_range']
        ordered = optimizer.get_optimized_order(filters)

        # unknown_filter는 기본값 0.1
        unknown_entry = next(e for e in ordered if e[0] == 'unknown_filter')
        assert unknown_entry[1] == 0.1


class TestGetParallelFilterGroups:
    """병렬 필터 그룹 테스트"""

    def test_split_parallel_sequential(self):
        """병렬/순차 필터 분리"""
        optimizer = FilterOrderOptimizer()

        filters = ['odd_even', 'consecutive', 'sum_range', 'match']
        parallel, sequential = optimizer.get_parallel_filter_groups(filters)

        # 독립 필터: odd_even, sum_range
        assert 'odd_even' in parallel
        assert 'sum_range' in parallel

        # 의존 필터: consecutive, match
        assert 'consecutive' in sequential
        assert 'match' in sequential

    def test_all_parallel(self):
        """모두 독립 필터"""
        optimizer = FilterOrderOptimizer()

        filters = ['odd_even', 'sum_range', 'digit_sum']
        parallel, sequential = optimizer.get_parallel_filter_groups(filters)

        assert len(parallel) == 3
        assert len(sequential) == 0

    def test_all_sequential(self):
        """모두 순차 필터"""
        optimizer = FilterOrderOptimizer()

        filters = ['match', 'consecutive', 'max_gap']
        parallel, sequential = optimizer.get_parallel_filter_groups(filters)

        assert len(parallel) == 0
        assert len(sequential) == 3


class TestCalculateCoverage:
    """커버리지 계산 테스트"""

    def test_greedy_coverage(self):
        """탐욕 알고리즘 커버리지"""
        optimizer = FilterOrderOptimizer()

        filter_sets = {
            'filter_a': {1, 2, 3},
            'filter_b': {4, 5, 6},
            'filter_c': {1, 4, 7}
        }

        coverage = optimizer.calculate_coverage(filter_sets, 10)

        assert len(coverage) > 0
        # 커버리지가 점점 증가
        for i in range(1, len(coverage)):
            assert coverage[i]['coverage'] >= coverage[i-1]['coverage']

    def test_coverage_percentage(self):
        """커버리지 백분율 계산"""
        optimizer = FilterOrderOptimizer()

        filter_sets = {
            'filter_a': {1, 2, 3, 4, 5}
        }

        coverage = optimizer.calculate_coverage(filter_sets, 10)

        assert coverage[0]['coverage'] == 5
        assert coverage[0]['coverage_percentage'] == 50.0

    def test_empty_filter_sets(self):
        """빈 필터 집합"""
        optimizer = FilterOrderOptimizer()

        coverage = optimizer.calculate_coverage({}, 10)

        assert coverage == []

    def test_max_five_results(self):
        """최대 5개 결과"""
        optimizer = FilterOrderOptimizer()

        filter_sets = {f'filter_{i}': {i} for i in range(10)}

        coverage = optimizer.calculate_coverage(filter_sets, 100)

        assert len(coverage) <= 5


class TestGetFilterStatistics:
    """필터 통계 테스트"""

    def test_filter_statistics(self):
        """필터 통계 반환"""
        results = {
            'sum_range': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'odd_even': {'filtered_rounds_list': [1, 2]}
        }
        optimizer = FilterOrderOptimizer(results)

        stats = optimizer.get_filter_statistics()

        assert 'sum_range' in stats
        assert stats['sum_range']['filtered_count'] == 5
        assert stats['sum_range']['default_efficiency'] == 0.45
        assert stats['odd_even']['is_independent'] == True


class TestFilterCorrelationDataClass:
    """FilterCorrelation 데이터클래스 테스트"""

    def test_correlation_creation(self):
        """상관관계 객체 생성"""
        corr = FilterCorrelation(
            filter1='a',
            filter2='b',
            jaccard_similarity=0.5,
            overlap_count=10,
            overlap_percentage=50.0
        )

        assert corr.filter1 == 'a'
        assert corr.jaccard_similarity == 0.5


class TestDefaultEfficiency:
    """기본 효율성 값 테스트"""

    def test_all_filters_have_efficiency(self):
        """모든 주요 필터에 효율성 값 존재"""
        expected_filters = [
            'sum_range', 'consecutive', 'max_gap', 'section',
            'odd_even', 'prime_composite', 'fixed_step',
            'average', 'last_digit', 'multiple', 'match'
        ]

        for f in expected_filters:
            assert f in FilterOrderOptimizer.DEFAULT_EFFICIENCY

    def test_efficiency_range(self):
        """효율성 값 범위 (0.0 ~ 1.0)"""
        for name, eff in FilterOrderOptimizer.DEFAULT_EFFICIENCY.items():
            assert 0.0 <= eff <= 1.0, f"{name} 효율성 범위 오류: {eff}"


class TestIndependentFilters:
    """독립 필터 목록 테스트"""

    def test_independent_filters_defined(self):
        """독립 필터 정의 확인"""
        assert 'odd_even' in FilterOrderOptimizer.INDEPENDENT_FILTERS
        assert 'sum_range' in FilterOrderOptimizer.INDEPENDENT_FILTERS

    def test_match_not_independent(self):
        """match는 독립 필터가 아님"""
        assert 'match' not in FilterOrderOptimizer.INDEPENDENT_FILTERS


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_single_filter(self):
        """단일 필터"""
        results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        # 단일 필터는 상관관계 없음 (자기 자신 제외)
        assert 'filter_a' in correlations
        assert len(correlations['filter_a']) == 0

    def test_missing_filtered_rounds_list(self):
        """filtered_rounds_list 누락"""
        results = {
            'filter_a': {},  # filtered_rounds_list 없음
            'filter_b': {'filtered_rounds_list': [1, 2, 3]}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        # 빈 리스트로 처리
        assert 'filter_a' in correlations

    def test_large_filter_sets(self):
        """대용량 필터 집합"""
        results = {
            'filter_a': {'filtered_rounds_list': list(range(1000))},
            'filter_b': {'filtered_rounds_list': list(range(500, 1500))}
        }
        optimizer = FilterOrderOptimizer(results)
        correlations = optimizer.calculate_correlations()

        corr = correlations['filter_a']['filter_b']
        # 중복: 500-999 = 500개
        assert corr.overlap_count == 500


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
