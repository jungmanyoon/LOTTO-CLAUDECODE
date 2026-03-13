#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
필터 실행 순서 최적화 모듈

Phase 3.2: 필터 상관관계 분석 및 최적화
- Jaccard 유사도 기반 중복 필터 식별
- 동적 필터 순서 최적화
- 독립 필터 병렬화 지원
"""

import logging
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class FilterCorrelation:
    """필터 상관관계 데이터"""
    filter1: str
    filter2: str
    jaccard_similarity: float
    overlap_count: int
    overlap_percentage: float


@dataclass
class FilterEfficiency:
    """필터 효율성 데이터"""
    name: str
    exclusion_rate: float  # 제외율 (0.0 ~ 1.0)
    execution_time_ms: float = 0.0
    is_independent: bool = True


class FilterOrderOptimizer:
    """필터 실행 순서 최적화기"""

    # 기본 필터 효율성 값 (제외율 기반)
    DEFAULT_EFFICIENCY = {
        'sum_range': 0.45,
        'consecutive': 0.30,
        'max_gap': 0.25,
        'section': 0.22,
        'ac_value': 0.22,
        'geometric_sequence': 0.20,
        'digit_sum': 0.20,
        'arithmetic_sequence': 0.18,
        'dispersion': 0.18,
        'odd_even': 0.15,
        'prime_composite': 0.15,
        'fixed_step': 0.15,
        'ten_section': 0.12,
        'average': 0.10,
        'last_digit': 0.10,
        'multiple': 0.08,
        'match': 0.05,
    }

    # 독립적인 필터 (병렬 실행 가능)
    INDEPENDENT_FILTERS = {
        'odd_even', 'sum_range', 'last_digit', 'multiple',
        'prime_composite', 'digit_sum', 'dispersion', 'average'
    }

    # 상호 의존적인 필터 쌍 (순차 실행 필요)
    DEPENDENT_FILTER_PAIRS = {
        ('match', 'consecutive'),  # match 결과가 consecutive에 영향
        ('section', 'ten_section'),  # 유사한 구간 분석
    }

    # 중복도 높은 필터 쌍 (Jaccard > 0.5)
    HIGH_CORRELATION_THRESHOLD = 0.5

    def __init__(self, filter_results: Optional[Dict[str, Dict]] = None):
        """
        Args:
            filter_results: 필터별 결과 데이터 {filter_name: {filtered_rounds_list: [...]}}
        """
        self.filter_results = filter_results or {}
        self.correlations: Dict[str, Dict[str, FilterCorrelation]] = {}
        self.efficiencies: Dict[str, FilterEfficiency] = {}
        self._correlation_calculated = False

    def calculate_correlations(self) -> Dict[str, Dict[str, FilterCorrelation]]:
        """필터 간 상관관계 계산

        Returns:
            중첩 딕셔너리 {filter1: {filter2: FilterCorrelation}}
        """
        if not self.filter_results:
            return {}

        self.correlations = {}

        # match 필터 제외 (모든 번호 제외하므로)
        active_filters = {
            name: result for name, result in self.filter_results.items()
            if name != 'match'
        }

        for filter1, result1 in active_filters.items():
            self.correlations[filter1] = {}
            filtered_set1 = set(result1.get('filtered_rounds_list', []))

            for filter2, result2 in active_filters.items():
                if filter1 != filter2:
                    filtered_set2 = set(result2.get('filtered_rounds_list', []))

                    # 교집합
                    overlap = filtered_set1 & filtered_set2
                    overlap_count = len(overlap)

                    # 합집합
                    union = filtered_set1 | filtered_set2

                    # Jaccard 유사도
                    jaccard = len(overlap) / len(union) if union else 0.0

                    # 중복 비율
                    overlap_pct = (
                        overlap_count / len(filtered_set1) * 100
                        if filtered_set1 else 0.0
                    )

                    self.correlations[filter1][filter2] = FilterCorrelation(
                        filter1=filter1,
                        filter2=filter2,
                        jaccard_similarity=jaccard,
                        overlap_count=overlap_count,
                        overlap_percentage=overlap_pct
                    )

        self._correlation_calculated = True
        return self.correlations

    def get_high_correlation_pairs(
        self, threshold: float = HIGH_CORRELATION_THRESHOLD
    ) -> List[Tuple[str, str, float]]:
        """높은 상관관계 필터 쌍 반환

        Args:
            threshold: Jaccard 유사도 임계값

        Returns:
            [(filter1, filter2, similarity), ...] 리스트 (중복 제거)
        """
        if not self._correlation_calculated:
            self.calculate_correlations()

        pairs = set()

        for filter1, filter1_corr in self.correlations.items():
            for filter2, corr in filter1_corr.items():
                if corr.jaccard_similarity >= threshold:
                    # 알파벳순 정렬하여 중복 방지
                    pair_key = tuple(sorted([filter1, filter2]))
                    pairs.add((*pair_key, corr.jaccard_similarity))

        return sorted(pairs, key=lambda x: x[2], reverse=True)

    def get_redundant_filters(
        self, threshold: float = 0.7
    ) -> List[str]:
        """중복 필터 목록 반환 (제거 후보)

        높은 상관관계(>threshold)를 가진 필터 쌍에서 효율성이 낮은 것 반환

        Args:
            threshold: 중복 판단 Jaccard 임계값

        Returns:
            제거 후보 필터 이름 리스트
        """
        high_corr_pairs = self.get_high_correlation_pairs(threshold)
        redundant = []

        for filter1, filter2, _ in high_corr_pairs:
            # 효율성 비교
            eff1 = self.DEFAULT_EFFICIENCY.get(filter1, 0.1)
            eff2 = self.DEFAULT_EFFICIENCY.get(filter2, 0.1)

            # 효율성 낮은 필터가 제거 후보
            if eff1 < eff2:
                if filter1 not in redundant:
                    redundant.append(filter1)
            else:
                if filter2 not in redundant:
                    redundant.append(filter2)

        return redundant

    def get_optimized_order(
        self,
        available_filters: List[str],
        dynamic_efficiency: Optional[Dict[str, float]] = None
    ) -> List[Tuple[str, float]]:
        """최적화된 필터 실행 순서 반환

        1. 효율성(제외율) 높은 필터 우선
        2. 독립적인 필터 그룹화 (병렬 실행 지원)
        3. 의존 필터는 순서 유지

        Args:
            available_filters: 사용 가능한 필터 이름 리스트
            dynamic_efficiency: 동적 효율성 값 (덮어쓰기)

        Returns:
            [(filter_name, efficiency), ...] 정렬된 리스트
        """
        efficiency_map = self.DEFAULT_EFFICIENCY.copy()

        # 동적 효율성 적용
        if dynamic_efficiency:
            efficiency_map.update(dynamic_efficiency)

        # 효율성 순 정렬
        ordered = [
            (f, efficiency_map.get(f, 0.1))
            for f in available_filters
            if f in efficiency_map or f in self.DEFAULT_EFFICIENCY
        ]

        # 없는 필터 추가 (기본값 0.1)
        for f in available_filters:
            if f not in efficiency_map:
                ordered.append((f, 0.1))

        ordered.sort(key=lambda x: x[1], reverse=True)

        return ordered

    def get_parallel_filter_groups(
        self,
        available_filters: List[str]
    ) -> Tuple[List[str], List[str]]:
        """병렬 실행 가능 필터와 순차 실행 필터 분리

        Args:
            available_filters: 사용 가능한 필터 리스트

        Returns:
            (parallel_filters, sequential_filters) 튜플
        """
        parallel = []
        sequential = []

        for f in available_filters:
            if f in self.INDEPENDENT_FILTERS:
                parallel.append(f)
            else:
                sequential.append(f)

        return parallel, sequential

    def calculate_coverage(
        self,
        filter_sets: Dict[str, Set[int]],
        total_rounds: int
    ) -> List[Dict]:
        """최소 필터로 최대 커버리지 달성 조합 (탐욕 알고리즘)

        Args:
            filter_sets: {filter_name: set(filtered_rounds)} 딕셔너리
            total_rounds: 전체 회차 수

        Returns:
            단계별 커버리지 정보 리스트
        """
        if not filter_sets:
            return []

        optimal_sets = []
        remaining_filters = list(filter_sets.keys())
        covered_rounds = set()
        selected_filters = []

        while remaining_filters and len(covered_rounds) < total_rounds:
            best_filter = None
            best_new_coverage = 0

            for filter_name in remaining_filters:
                new_coverage = len(filter_sets[filter_name] - covered_rounds)
                if new_coverage > best_new_coverage:
                    best_new_coverage = new_coverage
                    best_filter = filter_name

            if best_filter:
                selected_filters.append(best_filter)
                covered_rounds.update(filter_sets[best_filter])
                remaining_filters.remove(best_filter)

                optimal_sets.append({
                    'filters': selected_filters.copy(),
                    'coverage': len(covered_rounds),
                    'coverage_percentage': len(covered_rounds) / total_rounds * 100,
                    'filters_count': len(selected_filters)
                })

        return optimal_sets[:5]  # 상위 5개만

    def get_filter_statistics(self) -> Dict[str, Dict]:
        """필터별 통계 요약

        Returns:
            {filter_name: {filtered_count, exclusion_rate, ...}}
        """
        stats = {}

        for filter_name, result in self.filter_results.items():
            filtered_list = result.get('filtered_rounds_list', [])
            filtered_count = len(filtered_list)

            stats[filter_name] = {
                'filtered_count': filtered_count,
                'default_efficiency': self.DEFAULT_EFFICIENCY.get(filter_name, 0.1),
                'is_independent': filter_name in self.INDEPENDENT_FILTERS
            }

        return stats


def create_optimizer_from_analysis(analysis_file: str) -> FilterOrderOptimizer:
    """분석 결과 파일로부터 최적화기 생성

    Args:
        analysis_file: filter_analysis_result.json 파일 경로

    Returns:
        FilterOrderOptimizer 인스턴스
    """
    import json

    try:
        with open(analysis_file, 'r', encoding='utf-8') as f:
            analysis = json.load(f)

        filter_results = analysis.get('individual_filters', {})
        return FilterOrderOptimizer(filter_results)

    except Exception as e:
        logging.warning(f"분석 파일 로드 실패: {e}")
        return FilterOrderOptimizer()
