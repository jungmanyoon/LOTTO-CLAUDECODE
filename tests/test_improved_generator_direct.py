
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.utils.improved_prediction_generator import generate_final_predictions_improved

class TestImprovedGenerator(unittest.TestCase):
    def setUp(self):
        self.db_manager = MagicMock()
        self.filter_manager = MagicMock()
        
    @patch('src.core.ml_filter_integration_manager.MLFilterIntegrationManager')
    def test_generate_predictions_confidence(self, MockIntegrationManager):
        # Setup mock
        mock_instance = MockIntegrationManager.return_value
        
        # Create dummy predictions with varying confidence
        dummy_predictions = [
            {'numbers': [1, 2, 3, 4, 5, 6], 'final_score': 0.9, 'model': 'test_model_1'},
            {'numbers': [7, 8, 9, 10, 11, 12], 'final_score': 0.6, 'model': 'test_model_2'},
            {'numbers': [13, 14, 15, 16, 17, 18], 'final_score': 0.4, 'model': 'test_model_3'}
        ]
        
        mock_instance.generate_filtered_pool_predictions.return_value = {
            'predictions': dummy_predictions,
            'metadata': {}
        }
        
        # Run generator
        predictions = generate_final_predictions_improved(
            self.db_manager, self.filter_manager, num_sets=5, use_filtered_pool_system=True
        )
        
        # Verify
        self.assertEqual(len(predictions), 3)
        self.assertEqual(predictions[0]['confidence'], 0.9)
        self.assertEqual(predictions[1]['confidence'], 0.6)
        self.assertTrue('ML-Integrated' in predictions[0]['source'])
        
        print("\nGenerated Predictions:")
        for pred in predictions:
            print(f"Confidence: {pred['confidence']}, Source: {pred['source']}")

if __name__ == '__main__':
    unittest.main()
