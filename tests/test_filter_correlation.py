#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
필터 상관관계 분석 테스트

Phase 3.2: 필터 상관관계 분석 및 최적화
- Jaccard 유사도 계산 테스트
- 필터 조합 분석 테스트
- 최적 필터 세트 선택 테스트
- 당첨번호 패턴 분석 테스트
"""

import pytest
import sys
import json
import tempfile
from pathlib import Path
from collections import defaultdict

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scripts.analyze_filter_correlations import (
    analyze_filter_overlaps,
    analyze_filter_combinations,
    calculate_filter_coverage,
    analyze_winning_number_patterns,
    generate_recommendations,
    load_analysis_results,
    load_winning_numbers,
)


class TestAnalyzeFilterOverlaps:
    """필터 중복 분석 테스트"""

    def test_basic_overlap_calculation(self):
        """기본 중복 계산 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3, 4, 5]
            },
            'filter_b': {
                'filtered_rounds_list': [3, 4, 5, 6, 7]
            }
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # filter_a -> filter_b 중복
        assert 'filter_a' in overlaps
        assert 'filter_b' in overlaps['filter_a']

        # 교집합: {3, 4, 5} = 3개
        assert overlaps['filter_a']['filter_b']['overlap_count'] == 3

        # Jaccard: 3 / 7 (union: {1,2,3,4,5,6,7})
        assert abs(overlaps['filter_a']['filter_b']['jaccard_similarity'] - 3/7) < 0.01

    def test_no_overlap(self):
        """중복 없는 경우 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3]
            },
            'filter_b': {
                'filtered_rounds_list': [4, 5, 6]
            }
        }

        overlaps = analyze_filter_overlaps(filter_results)

        assert overlaps['filter_a']['filter_b']['overlap_count'] == 0
        assert overlaps['filter_a']['filter_b']['jaccard_similarity'] == 0.0

    def test_complete_overlap(self):
        """완전 중복 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3]
            },
            'filter_b': {
                'filtered_rounds_list': [1, 2, 3]
            }
        }

        overlaps = analyze_filter_overlaps(filter_results)

        assert overlaps['filter_a']['filter_b']['overlap_count'] == 3
        assert overlaps['filter_a']['filter_b']['jaccard_similarity'] == 1.0

    def test_match_filter_excluded(self):
        """match 필터 제외 테스트"""
        filter_results = {
            'match': {
                'filtered_rounds_list': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            },
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3]
            }
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # match 필터는 분석에서 제외됨
        assert 'match' not in overlaps

    def test_empty_filter(self):
        """빈 필터 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3]
            },
            'filter_b': {
                'filtered_rounds_list': []
            }
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # 빈 필터와의 중복은 0
        assert overlaps['filter_a']['filter_b']['overlap_count'] == 0

    def test_multiple_filters(self):
        """다중 필터 테스트"""
        filter_results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
            'filter_b': {'filtered_rounds_list': [3, 4, 5, 6, 7]},
            'filter_c': {'filtered_rounds_list': [5, 6, 7, 8, 9]},
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # 모든 쌍에 대해 계산
        assert len(overlaps) == 3
        assert len(overlaps['filter_a']) == 2  # b, c
        assert len(overlaps['filter_b']) == 2  # a, c
        assert len(overlaps['filter_c']) == 2  # a, b


class TestCalculateFilterCoverage:
    """필터 커버리지 계산 테스트"""

    def test_greedy_algorithm(self):
        """탐욕 알고리즘 테스트"""
        filters = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [4, 5, 6]},
            'filter_c': {'filtered_rounds_list': [1, 4, 7]},  # 부분 중복
        }

        coverage = calculate_filter_coverage(filters, 10)

        assert len(coverage) > 0
        # 각 단계별로 커버리지 증가
        for i in range(1, len(coverage)):
            assert coverage[i]['coverage'] >= coverage[i-1]['coverage']

    def test_max_coverage_limit(self):
        """최대 커버리지 제한 테스트"""
        filters = {
            'filter_a': {'filtered_rounds_list': [1, 2]},
            'filter_b': {'filtered_rounds_list': [3, 4]},
        }

        coverage = calculate_filter_coverage(filters, 10)

        # 최대 5개까지만 반환
        assert len(coverage) <= 5

    def test_coverage_percentage(self):
        """커버리지 백분율 테스트"""
        filters = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3, 4, 5]},
        }

        coverage = calculate_filter_coverage(filters, 10)

        # 50% 커버리지
        assert coverage[0]['coverage_percentage'] == 50.0
        assert coverage[0]['coverage'] == 5

    def test_empty_filters(self):
        """빈 필터 집합 테스트"""
        filters = {}

        coverage = calculate_filter_coverage(filters, 10)

        assert coverage == []

    def test_filter_count_incremental(self):
        """필터 개수 증가 테스트"""
        filters = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]},
            'filter_b': {'filtered_rounds_list': [4, 5, 6]},
            'filter_c': {'filtered_rounds_list': [7, 8, 9]},
        }

        coverage = calculate_filter_coverage(filters, 10)

        # 필터 개수 순차 증가
        for i, step in enumerate(coverage, 1):
            assert step['filters_count'] == i


class TestAnalyzeFilterCombinations:
    """필터 조합 분석 테스트"""

    def test_single_filter_effectiveness(self):
        """단일 필터 효과성 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3],
                'filtered_rounds': 3
            },
            'filter_b': {
                'filtered_rounds_list': [4, 5],
                'filtered_rounds': 2
            }
        }

        winning_numbers = [{'numbers': [1,2,3,4,5,6]} for _ in range(10)]

        analysis = analyze_filter_combinations(filter_results, winning_numbers)

        assert 'single_filter_effectiveness' in analysis
        assert 'filter_a' in analysis['single_filter_effectiveness']
        assert analysis['single_filter_effectiveness']['filter_a']['filtered_count'] == 3
        assert analysis['single_filter_effectiveness']['filter_a']['exclusion_rate'] == 30.0

    def test_match_filter_excluded(self):
        """match 필터 제외 테스트"""
        filter_results = {
            'match': {
                'filtered_rounds_list': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                'filtered_rounds': 10
            },
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3],
                'filtered_rounds': 3
            }
        }

        winning_numbers = [{'numbers': [1,2,3,4,5,6]} for _ in range(10)]

        analysis = analyze_filter_combinations(filter_results, winning_numbers)

        # match 필터는 분석에서 제외
        assert 'match' not in analysis['single_filter_effectiveness']

    def test_multi_filter_combinations(self):
        """다중 필터 조합 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3],
                'filtered_rounds': 3
            },
            'filter_b': {
                'filtered_rounds_list': [2, 3, 4],
                'filtered_rounds': 3
            }
        }

        winning_numbers = [{'numbers': [1,2,3,4,5,6]} for _ in range(10)]

        analysis = analyze_filter_combinations(filter_results, winning_numbers)

        # 회차 2, 3은 두 필터 모두에 걸림 → 조합 생성
        assert 'multi_filter_combinations' in analysis

    def test_optimal_filter_sets_included(self):
        """최적 필터 세트 포함 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [1, 2, 3],
                'filtered_rounds': 3
            }
        }

        winning_numbers = [{'numbers': [1,2,3,4,5,6]} for _ in range(10)]

        analysis = analyze_filter_combinations(filter_results, winning_numbers)

        assert 'optimal_filter_sets' in analysis

    def test_zero_filtered_rounds_excluded(self):
        """0개 필터링 필터 제외 테스트"""
        filter_results = {
            'filter_a': {
                'filtered_rounds_list': [],
                'filtered_rounds': 0
            },
            'filter_b': {
                'filtered_rounds_list': [1, 2, 3],
                'filtered_rounds': 3
            }
        }

        winning_numbers = [{'numbers': [1,2,3,4,5,6]} for _ in range(10)]

        analysis = analyze_filter_combinations(filter_results, winning_numbers)

        # 0개 필터링 필터는 제외
        assert 'filter_a' not in analysis['single_filter_effectiveness']
        assert 'filter_b' in analysis['single_filter_effectiveness']


class TestAnalyzeWinningNumberPatterns:
    """당첨번호 패턴 분석 테스트"""

    def test_sum_distribution(self):
        """합계 분포 테스트"""
        winning_numbers = [
            {'numbers': [1, 2, 3, 4, 5, 6]},   # 합계: 21
            {'numbers': [10, 20, 30, 35, 40, 45]},  # 합계: 180
        ]

        patterns = analyze_winning_number_patterns(winning_numbers)

        assert 'sum_stats' in patterns
        assert patterns['sum_stats']['min'] == 21
        assert patterns['sum_stats']['max'] == 180
        assert patterns['sum_stats']['mean'] == (21 + 180) / 2

    def test_odd_even_distribution(self):
        """홀짝 분포 테스트"""
        winning_numbers = [
            {'numbers': [1, 3, 5, 7, 9, 11]},   # 홀수 6개
            {'numbers': [2, 4, 6, 8, 10, 12]},  # 홀수 0개
            {'numbers': [1, 2, 3, 4, 5, 6]},    # 홀수 3개
        ]

        patterns = analyze_winning_number_patterns(winning_numbers)

        # 가장 흔한 홀수 개수가 반환되어야 함
        assert 'odd_even_most_common' in patterns

    def test_consecutive_distribution(self):
        """연속번호 분포 테스트"""
        winning_numbers = [
            {'numbers': [1, 2, 3, 4, 5, 6]},   # 연속: 5개 쌍
            {'numbers': [1, 10, 20, 30, 40, 45]},  # 연속: 0개 쌍
        ]

        patterns = analyze_winning_number_patterns(winning_numbers)

        assert 'consecutive_most_common' in patterns

    def test_gap_distribution(self):
        """간격 분포 테스트"""
        winning_numbers = [
            {'numbers': [1, 11, 21, 31, 41, 45]},  # 간격: 10, 10, 10, 10, 4
        ]

        patterns = analyze_winning_number_patterns(winning_numbers)

        assert 'gap_stats' in patterns
        assert patterns['gap_stats']['max'] == 10

    def test_empty_winning_numbers(self):
        """빈 당첨번호 테스트"""
        winning_numbers = []

        # 빈 리스트 처리 시 오류 발생해야 함
        with pytest.raises((ValueError, ZeroDivisionError, IndexError)):
            analyze_winning_number_patterns(winning_numbers)


class TestGenerateRecommendations:
    """권장사항 생성 테스트"""

    @pytest.fixture
    def sample_analysis_results(self):
        """샘플 분석 결과"""
        return {
            'individual_filters': {
                'match': {'pass_rate': 0.0, 'filtered_rounds': 1000},
                'sum_range': {'pass_rate': 95.0, 'filtered_rounds': 50},
                'odd_even': {'pass_rate': 100.0, 'filtered_rounds': 0},
            }
        }

    @pytest.fixture
    def sample_correlations(self):
        """샘플 상관관계"""
        return {
            'sum_range': {
                'odd_even': {'jaccard_similarity': 0.5}
            }
        }

    @pytest.fixture
    def sample_combinations(self):
        """샘플 조합"""
        return {
            'optimal_filter_sets': [
                {
                    'filters': ['sum_range'],
                    'coverage_percentage': 50.0
                }
            ]
        }

    @pytest.fixture
    def sample_patterns(self):
        """샘플 패턴"""
        return {
            'sum_stats': {
                'mean': 150.0,
                'std': 30.0
            },
            'odd_even_most_common': 3
        }

    def test_recommendations_generated(self, sample_analysis_results,
                                       sample_correlations, sample_combinations,
                                       sample_patterns):
        """권장사항 생성 테스트"""
        recommendations = generate_recommendations(
            sample_analysis_results,
            sample_correlations,
            sample_combinations,
            sample_patterns
        )

        assert len(recommendations) > 0
        assert all(isinstance(r, str) for r in recommendations)

    def test_match_filter_recommendation(self, sample_analysis_results,
                                         sample_correlations, sample_combinations,
                                         sample_patterns):
        """match 필터 권장사항 테스트"""
        recommendations = generate_recommendations(
            sample_analysis_results,
            sample_correlations,
            sample_combinations,
            sample_patterns
        )

        # match 필터 개선 권장사항 포함
        match_rec = [r for r in recommendations if 'match' in r.lower()]
        assert len(match_rec) > 0

    def test_no_effect_filter_recommendation(self, sample_analysis_results,
                                             sample_correlations, sample_combinations,
                                             sample_patterns):
        """효과 없는 필터 권장사항 테스트"""
        recommendations = generate_recommendations(
            sample_analysis_results,
            sample_correlations,
            sample_combinations,
            sample_patterns
        )

        # odd_even은 100% 통과율이므로 비활성화 권장
        found_no_effect = any('효과 없는' in r or '비활성화' in r for r in recommendations)
        assert found_no_effect

    def test_dynamic_threshold_recommendation(self, sample_analysis_results,
                                              sample_correlations, sample_combinations,
                                              sample_patterns):
        """동적 임계값 권장사항 테스트"""
        recommendations = generate_recommendations(
            sample_analysis_results,
            sample_correlations,
            sample_combinations,
            sample_patterns
        )

        # 동적 임계값 권장사항 포함
        found_dynamic = any('동적' in r or '임계값' in r for r in recommendations)
        assert found_dynamic


class TestFileOperations:
    """파일 작업 테스트"""

    @pytest.fixture
    def temp_json_file(self):
        """임시 JSON 파일 생성"""
        tmpdir = tempfile.mkdtemp()
        json_path = Path(tmpdir) / 'test.json'
        yield json_path

        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_load_analysis_results(self, temp_json_file):
        """분석 결과 로드 테스트"""
        test_data = {
            'individual_filters': {
                'filter_a': {'pass_rate': 95.0}
            }
        }

        with open(temp_json_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)

        result = load_analysis_results(str(temp_json_file))

        assert result == test_data

    def test_load_winning_numbers(self, temp_json_file):
        """당첨번호 로드 테스트"""
        test_data = [
            {'numbers': [1, 2, 3, 4, 5, 6]},
            {'numbers': [7, 8, 9, 10, 11, 12]}
        ]

        with open(temp_json_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)

        result = load_winning_numbers(str(temp_json_file))

        assert result == test_data

    def test_load_invalid_json(self, temp_json_file):
        """잘못된 JSON 로드 테스트"""
        with open(temp_json_file, 'w', encoding='utf-8') as f:
            f.write("invalid json {")

        with pytest.raises(json.JSONDecodeError):
            load_analysis_results(str(temp_json_file))


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_single_filter(self):
        """단일 필터 테스트"""
        filter_results = {
            'filter_a': {'filtered_rounds_list': [1, 2, 3]}
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # 단일 필터는 자기 자신과 비교 안 함
        assert 'filter_a' in overlaps
        assert 'filter_a' not in overlaps['filter_a']

    def test_large_overlap_data(self):
        """대용량 중복 데이터 테스트"""
        filter_results = {
            'filter_a': {'filtered_rounds_list': list(range(1000))},
            'filter_b': {'filtered_rounds_list': list(range(500, 1500))}
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # 중복: 500-999 = 500개
        assert overlaps['filter_a']['filter_b']['overlap_count'] == 500

    def test_all_filters_same(self):
        """모든 필터 동일 테스트"""
        same_list = [1, 2, 3, 4, 5]
        filter_results = {
            'filter_a': {'filtered_rounds_list': same_list.copy()},
            'filter_b': {'filtered_rounds_list': same_list.copy()},
            'filter_c': {'filtered_rounds_list': same_list.copy()}
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # 모든 쌍이 100% 유사도
        for f1, f1_overlaps in overlaps.items():
            for f2, data in f1_overlaps.items():
                assert data['jaccard_similarity'] == 1.0


class TestJaccardSimilarity:
    """Jaccard 유사도 계산 검증"""

    def test_jaccard_formula(self):
        """Jaccard 공식 검증"""
        # A = {1, 2, 3}, B = {2, 3, 4}
        # 교집합 = {2, 3} = 2개
        # 합집합 = {1, 2, 3, 4} = 4개
        # Jaccard = 2/4 = 0.5

        filter_results = {
            'A': {'filtered_rounds_list': [1, 2, 3]},
            'B': {'filtered_rounds_list': [2, 3, 4]}
        }

        overlaps = analyze_filter_overlaps(filter_results)

        assert abs(overlaps['A']['B']['jaccard_similarity'] - 0.5) < 0.001

    def test_jaccard_symmetric(self):
        """Jaccard 대칭성 검증"""
        filter_results = {
            'A': {'filtered_rounds_list': [1, 2, 3, 4]},
            'B': {'filtered_rounds_list': [3, 4, 5, 6]}
        }

        overlaps = analyze_filter_overlaps(filter_results)

        # A→B와 B→A의 Jaccard가 동일해야 함
        assert (overlaps['A']['B']['jaccard_similarity'] ==
                overlaps['B']['A']['jaccard_similarity'])


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
