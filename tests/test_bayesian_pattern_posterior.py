"""
[ml-probabilistic-3] BayesianFilter 패턴 사후분포 회귀 테스트

과거 버그: _update_with_recent_data가 사후분포를 평면 키 'patterns.odd_even.{N}'로 저장했으나
calculate_log_likelihood/visualize_beliefs는 중첩 posterior_beliefs['patterns']를 읽어,
패턴 우도가 우도계산에서 영구 무시됐다(균등 prior에서는 평면 prior 키 부재로 경고까지).

수정: readers가 직접 읽는 중첩 구조로 사후분포를 구성하도록 통일.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.probabilistic.bayesian_inference import BayesianFilter

RECENT = [
    '1,3,5,7,9,11',
    '2,4,6,8,10,12',
    '5,12,23,31,38,44',
    '7,14,21,28,35,42',
    '3,9,18,27,36,45',
]


@pytest.mark.parametrize("historical", [None, RECENT * 3], ids=["uniform_prior", "empirical_prior"])
def test_pattern_posterior_nested_and_contributes(historical):
    """양쪽 prior 초기화 모두에서 패턴 사후분포가 중첩 구조로 구성되고 우도에 기여하는지 검증."""
    bi = BayesianFilter()
    bi.initialize_priors(historical)
    bi._update_with_recent_data(RECENT)

    pb = bi.posterior_beliefs

    # 1) 핵심 버그 수정: 중첩 'patterns' 키가 존재해야 한다 (과거엔 영구 부재)
    assert 'patterns' in pb
    patterns = pb['patterns']

    # 2) readers가 기대하는 구조: odd_even[N]['params'] = (alpha, beta)
    assert isinstance(patterns.get('odd_even'), dict) and patterns['odd_even']
    odd_count = next(iter(patterns['odd_even']))
    beta_params = patterns['odd_even'][odd_count]['params']
    assert len(beta_params) == 2
    assert beta_params[0] > 0 and beta_params[1] > 0

    # 3) sum_range는 mean/std를 가진 정규분포 파라미터
    assert 'sum_range' in patterns
    sum_params = patterns['sum_range']['params']
    assert 'mean' in sum_params and 'std' in sum_params
    assert sum_params['std'] > 0  # logpdf 발산 방지

    # 4) 폐기된 평면 키 'patterns.odd_even.N'가 사후분포에 남지 않아야 한다
    assert not any(k.startswith('patterns.') for k in pb)

    # 5) calculate_log_likelihood가 실제로 패턴 항을 더하는지: 패턴 제거 전후 값이 달라야 한다
    combo = [1, 3, 5, 7, 9, 11]  # 홀수 6개
    ll_with_patterns = bi.calculate_log_likelihood(combo, {})
    saved = pb.pop('patterns')
    ll_without_patterns = bi.calculate_log_likelihood(combo, {})
    pb['patterns'] = saved
    assert ll_with_patterns != ll_without_patterns
