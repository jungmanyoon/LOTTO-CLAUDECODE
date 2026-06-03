import sys
import os
import logging
import json
import shutil
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optimization.improved_auto_improvement_manager import ImprovedAutoImprovementManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_improvement_tracking():
    print("Testing Improvement Tracking...")
    
    # Clean up previous state
    state_file = "data/improved_auto_improvement_state.json"
    if os.path.exists(state_file):
        os.remove(state_file)
        print("Removed existing state file.")

    # Mock DB Manager
    mock_db = MagicMock()
    
    # Initialize Manager
    manager = ImprovedAutoImprovementManager()
    
    # 1. Initial Baseline
    print("\n--- Step 1: Initial Baseline (Avg Matches: 1.0) ---")
    results_baseline = {
        'performance_metrics': {
            'model_performance': {
                'lstm': {'avg_matches': 1.0},
                'ensemble': {'avg_matches': 1.0},
                'monte_carlo': {'avg_matches': 1.0}
            }
        }
    }
    manager.track_backtest_improved(results_baseline)
    
    # Verify state
    state = manager._load_state()
    print(f"Best LSTM: {state['best_models']['lstm']['performance']}")
    assert state['best_models']['lstm']['performance'] == 1.0
    
    # 2. Lower Score (Should NOT update)
    print("\n--- Step 2: Lower Score (Avg Matches: 0.8) ---")
    results_lower = {
        'performance_metrics': {
            'model_performance': {
                'lstm': {'avg_matches': 0.8},
                'ensemble': {'avg_matches': 0.8},
                'monte_carlo': {'avg_matches': 0.8}
            }
        }
    }
    manager.track_backtest_improved(results_lower)
    
    # Verify state
    state = manager._load_state()
    print(f"Best LSTM: {state['best_models']['lstm']['performance']}")
    assert state['best_models']['lstm']['performance'] == 1.0
    
    # 3. Higher Score (Should UPDATE)
    print("\n--- Step 3: Higher Score (Avg Matches: 1.2) ---")
    results_higher = {
        'performance_metrics': {
            'model_performance': {
                'lstm': {'avg_matches': 1.2},
                'ensemble': {'avg_matches': 1.2},
                'monte_carlo': {'avg_matches': 1.2}
            }
        }
    }
    manager.track_backtest_improved(results_higher)
    
    # Verify state
    state = manager._load_state()
    print(f"Best LSTM: {state['best_models']['lstm']['performance']}")
    assert state['best_models']['lstm']['performance'] == 1.2
    
    print("\nSUCCESS: Improvement tracking verified.")

def test_legacy_manager_rollback_symmetry(tmp_path):
    """[log-analysis-4] 구버전 AutoImprovementManager(실사용 경로)가 성능 대폭 하락(>10%) 시
    신버전(ImprovedAutoImprovementManager)과 동일하게 롤백을 트리거하는지(대칭화) 검증.

    수정 전: 구버전은 개선 분기만 있어 -33%/-66% 하락을 조용히 무시(비대칭).
    수정 후: elif overall_improvement < -0.10 분기로 경고 + ContinuousImprovementEngine.rollback_to_best 호출.
    """
    from unittest.mock import patch
    from src.optimization.auto_improvement_manager import AutoImprovementManager

    state_file = str(tmp_path / "legacy_auto_improvement_state.json")
    manager = AutoImprovementManager(state_file=state_file)

    # 1) 기준선 수립: 높은 성능 -> current_performance 설정 (0에서 개선되므로 should_update=True)
    high = {'performance_metrics': {'model_performance': {
        'lstm': {'avg_matches': 1.5},
        'ensemble': {'avg_matches': 1.5},
        'monte_carlo': {'avg_matches': 1.5},
    }}}
    info1 = manager.track_backtest(high)
    assert info1['should_update'] is True
    assert manager.state['current_performance']['overall'] > 0

    # 2) 대폭 하락(1.5 -> 0.5, 약 -66%): 롤백 트리거 검증 (지연 import 대상 모킹)
    low = {'performance_metrics': {'model_performance': {
        'lstm': {'avg_matches': 0.5},
        'ensemble': {'avg_matches': 0.5},
        'monte_carlo': {'avg_matches': 0.5},
    }}}
    with patch('src.core.continuous_improvement_engine.ContinuousImprovementEngine') as MockEngine:
        mock_engine = MockEngine.return_value
        mock_engine.rollback_to_best.return_value = True
        info2 = manager.track_backtest(low)

    # 하락 시 업데이트는 안 하되, 롤백을 트리거해야 함 (신버전과 대칭)
    assert info2['should_update'] is False
    assert info2.get('should_rollback') is True
    assert info2.get('rollback_executed') is True
    mock_engine.rollback_to_best.assert_called_once()
    print("\nSUCCESS: Legacy manager rollback symmetry verified.")


if __name__ == "__main__":
    test_improvement_tracking()
