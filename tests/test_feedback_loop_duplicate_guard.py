"""
[log-analysis-3] EnhancedFeedbackLoop 중복 백테스팅 가드 회귀 테스트

과거 버그: 피드백 루프 N회 반복이 매번 동일 파라미터로 run_backtest를 호출 -> 캐시 재사용으로
동일 결과가 반환되면 track_backtest가 N회 중복 호출되어 total_backtest_count 인플레이션 +
improvement_history 중복 레코드 + "1.102 -> 0.740" 동일 출력이 N회 반복됐다.

수정: 직전 반복과 동일한 성능 시그니처면 track_backtest 호출 없이 루프를 조기 종료한다.
"""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optimization.enhanced_feedback_loop import EnhancedFeedbackLoop


def _fixed_backtest_result():
    return {
        'predictions': [{'round': 1}],
        'performance_metrics': {
            'total_rounds': 10,
            'model_performance': {
                'lstm': {'avg_matches': 1.1},
                'ensemble': {'avg_matches': 1.0},
                'monte_carlo': {'avg_matches': 0.9},
            },
        },
    }


def test_duplicate_backtest_result_stops_after_one_track():
    """동일 백테스팅 결과가 반복되면 track_backtest는 1회만 호출되고 루프가 조기 종료된다."""
    # __init__의 무거운 실객체(LSTM/Ensemble/백테스팅 프레임워크) 생성을 우회
    efl = EnhancedFeedbackLoop.__new__(EnhancedFeedbackLoop)

    efl.backtesting_framework = MagicMock()
    efl.backtesting_framework.run_backtest.return_value = _fixed_backtest_result()

    im = MagicMock()
    im.config = {'max_iterations_per_session': 5}
    im.should_continue_improvement.return_value = True
    im.track_backtest.return_value = {
        'backtest_number': 1,
        'old_performance': {'overall': 1.0},
        'new_performance': {'overall': 1.0},
        'should_update': False,  # Step 3(모델 최적화) 미진입 -> self.models/auto_ml_optimizer 불필요
        'improvements': {},
    }
    im.state = {'current_performance': {'overall': 1.0}, 'total_backtest_count': 1}
    efl.improvement_manager = im

    efl.run_improvement_cycle(start_round=1, end_round=10, max_iterations=5)

    # 5회 반복하려 했으나 동일 결과 -> track_backtest는 1회만(중복 추적/카운터 인플레이션 방지)
    assert im.track_backtest.call_count == 1
    # run_backtest는 1회차(정상) + 2회차(중복 감지 후 break) = 2회
    assert efl.backtesting_framework.run_backtest.call_count == 2


def test_changing_backtest_result_keeps_iterating():
    """결과가 매번 달라지면 가드에 걸리지 않고 정상적으로 여러 번 추적한다(가드 오발동 방지)."""
    efl = EnhancedFeedbackLoop.__new__(EnhancedFeedbackLoop)

    results = []
    for matches in (1.1, 1.2, 1.3):
        r = _fixed_backtest_result()
        r['performance_metrics']['model_performance']['lstm']['avg_matches'] = matches
        results.append(r)

    efl.backtesting_framework = MagicMock()
    efl.backtesting_framework.run_backtest.side_effect = results

    im = MagicMock()
    im.config = {'max_iterations_per_session': 3}
    im.should_continue_improvement.return_value = True
    im.track_backtest.return_value = {
        'backtest_number': 1,
        'old_performance': {'overall': 1.0},
        'new_performance': {'overall': 1.0},
        'should_update': False,
        'improvements': {},
    }
    im.state = {'current_performance': {'overall': 1.0}, 'total_backtest_count': 1}
    efl.improvement_manager = im

    efl.run_improvement_cycle(start_round=1, end_round=10, max_iterations=3)

    # 3개 결과가 모두 다르므로 3회 모두 추적
    assert im.track_backtest.call_count == 3
