"""
실시간 대시보드 프로토타입
로또 예측 시스템의 상태와 성능을 실시간으로 모니터링
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class LottoDashboard:
    """로또 예측 시스템 대시보드"""
    
    def __init__(self):
        self.refresh_interval = 5  # 5초마다 갱신
        self.components = {
            'system_status': self._get_system_status,
            'recent_predictions': self._get_recent_predictions,
            'performance_metrics': self._get_performance_metrics,
            'filter_status': self._get_filter_status,
            'ml_models': self._get_ml_status
        }
    
    def _clear_screen(self):
        """화면 지우기"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _get_system_status(self) -> Dict:
        """시스템 상태 조회"""
        from src.core.db_manager import DatabaseManager
        
        try:
            db_manager = DatabaseManager()
            latest_round = db_manager.get_last_round()
            
            return {
                'status': 'ONLINE',
                'latest_round': latest_round,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'database': 'Connected'
            }
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def _get_recent_predictions(self) -> List[Dict]:
        """최근 예측 조회 - 가장 최신 5세트"""
        from src.core.prediction_tracker import PredictionTracker
        
        try:
            tracker = PredictionTracker()
            
            # 최근 미확인 예측
            unchecked = tracker.get_latest_unchecked()
            
            if unchecked:
                predictions = []
                # set_number 역순으로 정렬 (최신순)
                sorted_preds = sorted(unchecked['predictions'], key=lambda x: x['set_number'], reverse=True)
                
                # 최신 5개만 선택
                for pred in sorted_preds[:5]:
                    predictions.append({
                        'round': unchecked['round'],
                        'set': pred['set_number'],
                        'numbers': pred['numbers'],
                        'source': pred['source'],
                        'confidence': pred.get('confidence', 0)
                    })
                
                # 다시 set_number 순서대로 정렬하여 표시
                predictions.sort(key=lambda x: x['set'])
                    
                return predictions
            
            return []
            
        except Exception as e:
            logging.error(f"예측 조회 실패: {e}")
            return []
    
    def _get_performance_metrics(self) -> Dict:
        """성능 지표 조회"""
        try:
            # 성능 요약 파일 확인
            perf_file = "results/performance_summary.json"
            if os.path.exists(perf_file):
                with open(perf_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        'avg_match': data.get('avg_match_count', 0),
                        'three_plus_rate': data.get('three_plus_rate', 0),
                        'best_match': data.get('best_match_count', 0),
                        'last_updated': data.get('timestamp', 'Unknown')
                    }
            
            return {
                'avg_match': 0,
                'three_plus_rate': 0,
                'best_match': 0,
                'last_updated': 'No data'
            }
            
        except Exception as e:
            logging.error(f"성능 지표 조회 실패: {e}")
            return {}
    
    def _get_filter_status(self) -> Dict:
        """필터 상태 조회"""
        import yaml
        
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            active_filters = config.get('filters', {}).get('enabled_filters', [])
            
            return {
                'total_filters': len(active_filters),
                'active_filters': active_filters[:5],  # 상위 5개만
                'pass_rate': 'Calculating...'
            }
            
        except Exception as e:
            logging.error(f"필터 상태 조회 실패: {e}")
            return {
                'total_filters': 0,
                'active_filters': [],
                'pass_rate': 'Error'
            }
    
    def _get_ml_status(self) -> Dict:
        """ML 모델 상태 조회"""
        try:
            # 모델 상태 파일 확인
            models = ['lstm', 'ensemble', 'monte_carlo']
            model_status = {}
            
            for model in models:
                cache_file = f"cache/models/{model}_model_cache.pkl"
                if os.path.exists(cache_file):
                    mod_time = os.path.getmtime(cache_file)
                    model_status[model] = {
                        'status': 'Ready',
                        'last_updated': datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
                    }
                else:
                    model_status[model] = {
                        'status': 'Not initialized',
                        'last_updated': 'N/A'
                    }
            
            return model_status
            
        except Exception as e:
            logging.error(f"ML 상태 조회 실패: {e}")
            return {}
    
    def _draw_header(self):
        """헤더 그리기"""
        print("=" * 80)
        print(" " * 25 + "LOTTO PREDICTION DASHBOARD")
        print("=" * 80)
    
    def _draw_system_status(self, status: Dict):
        """시스템 상태 표시"""
        print("\n[SYSTEM STATUS]")
        print("-" * 40)
        print(f"Status: {status.get('status', 'UNKNOWN')}")
        print(f"Latest Round: {status.get('latest_round', 'N/A')}")
        print(f"Database: {status.get('database', 'Unknown')}")
        print(f"Time: {status.get('timestamp', 'N/A')}")
    
    def _draw_predictions(self, predictions: List[Dict]):
        """예측 표시"""
        print("\n[RECENT PREDICTIONS]")
        print("-" * 40)
        
        if predictions:
            for pred in predictions[:3]:  # 상위 3개만 표시
                numbers = ', '.join(map(str, pred['numbers']))
                print(f"Round {pred['round']} Set {pred['set']}: [{numbers}]")
                print(f"  Source: {pred['source']}, Confidence: {pred['confidence']:.2f}")
        else:
            print("No recent predictions")
    
    def _draw_performance(self, metrics: Dict):
        """성능 지표 표시"""
        print("\n[PERFORMANCE METRICS]")
        print("-" * 40)
        
        if metrics:
            print(f"Average Match: {metrics.get('avg_match', 0):.2f} numbers")
            print(f"3+ Match Rate: {metrics.get('three_plus_rate', 0):.1f}%")
            print(f"Best Match: {metrics.get('best_match', 0)} numbers")
            print(f"Updated: {metrics.get('last_updated', 'N/A')}")
        else:
            print("No performance data available")
    
    def _draw_filters(self, filters: Dict):
        """필터 상태 표시"""
        print("\n[FILTER STATUS]")
        print("-" * 40)
        print(f"Total Filters: {filters.get('total_filters', 0)}")
        
        active = filters.get('active_filters', [])
        if active:
            print("Active: " + ", ".join(active[:5]))
        else:
            print("No active filters")
    
    def _draw_ml_models(self, models: Dict):
        """ML 모델 상태 표시"""
        print("\n[ML MODELS]")
        print("-" * 40)
        
        if models:
            for name, info in models.items():
                status = info.get('status', 'Unknown')
                updated = info.get('last_updated', 'N/A')
                print(f"{name.upper()}: {status} (Updated: {updated})")
        else:
            print("No ML model information")
    
    def _draw_footer(self):
        """푸터 그리기"""
        print("\n" + "=" * 80)
        print("Press Ctrl+C to exit | Auto-refresh every 5 seconds")
        print("=" * 80)
    
    def render(self):
        """대시보드 렌더링"""
        self._clear_screen()
        
        # 데이터 수집
        data = {}
        for name, func in self.components.items():
            try:
                data[name] = func()
            except Exception as e:
                logging.error(f"Component {name} failed: {e}")
                data[name] = {}
        
        # 화면 그리기
        self._draw_header()
        self._draw_system_status(data.get('system_status', {}))
        self._draw_predictions(data.get('recent_predictions', []))
        self._draw_performance(data.get('performance_metrics', {}))
        self._draw_filters(data.get('filter_status', {}))
        self._draw_ml_models(data.get('ml_models', {}))
        self._draw_footer()
    
    def run(self):
        """대시보드 실행"""
        print("Starting Lotto Dashboard...")
        time.sleep(1)
        
        try:
            while True:
                self.render()
                time.sleep(self.refresh_interval)
                
        except KeyboardInterrupt:
            print("\n\nDashboard stopped by user.")
            print("Goodbye!")
    
    def run_once(self):
        """대시보드 한 번만 실행 (테스트용)"""
        self.render()


def main():
    """메인 실행 함수"""
    dashboard = LottoDashboard()
    
    print("\n" + "="*60)
    print("로또 예측 시스템 대시보드")
    print("="*60)
    print("\n옵션:")
    print("1. 실시간 모니터링 (5초마다 갱신)")
    print("2. 현재 상태만 확인")
    print("3. 종료")
    
    choice = input("\n선택 (1-3): ").strip()
    
    if choice == '1':
        dashboard.run()
    elif choice == '2':
        dashboard.run_once()
    else:
        print("종료합니다.")


if __name__ == "__main__":
    main()