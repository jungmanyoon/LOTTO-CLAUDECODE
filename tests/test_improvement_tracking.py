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

if __name__ == "__main__":
    test_improvement_tracking()
