"""
간단한 파라미터 최적화 스크립트
필터 파라미터를 조정하여 성능을 개선
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import json
import yaml
from datetime import datetime
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SimpleParameterOptimizer:
    """간단한 파라미터 최적화"""
    
    def __init__(self):
        self.config_path = "config.yaml"
        self.results_dir = "results/optimization"
        os.makedirs(self.results_dir, exist_ok=True)
        
        # 현재 설정 로드
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.current_config = yaml.safe_load(f)
        
        logging.info("파라미터 최적화 시스템 초기화")
    
    def analyze_current_performance(self) -> Dict:
        """현재 설정의 성능 분석"""
        print("\n현재 설정 성능 분석 중...")
        
        from src.backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
        from src.core.db_manager import DatabaseManager
        
        db_manager = DatabaseManager()
        backtester = OptimizedBacktestingFramework(db_manager)
        
        # 최근 10회차 백테스팅
        results = backtester.run_backtest(
            start_round=1175,
            end_round=1185,
            model_types=['ensemble']
        )
        
        if results and 'performance_summary' in results:
            perf = results['performance_summary']
            
            performance = {
                'avg_match': perf.get('avg_match_count', 0),
                'three_plus_rate': perf.get('three_plus_rate', 0),
                'filtered_combinations': perf.get('filtered_combinations', 0),
                'pass_rate': perf.get('filtered_combinations', 0) / 8145060 * 100
            }
            
            return performance
        
        return {'error': 'Performance analysis failed'}
    
    def suggest_improvements(self, performance: Dict) -> List[Dict]:
        """성능 기반 개선 제안"""
        suggestions = []
        
        # 평균 일치가 낮으면
        if performance.get('avg_match', 0) < 1.0:
            suggestions.append({
                'area': 'Match Filter',
                'problem': '평균 일치 개수가 너무 낮음',
                'current': self.current_config['filters']['criteria']['match']['max_match'],
                'suggested': 4,
                'reason': 'Match 필터를 완화하여 더 많은 조합 허용'
            })
        
        # 패스율이 너무 낮으면
        if performance.get('pass_rate', 0) < 0.5:
            suggestions.append({
                'area': 'Sum Range',
                'problem': '필터링이 너무 엄격함',
                'current': [
                    self.current_config['filters']['criteria']['sum_range']['min_sum'],
                    self.current_config['filters']['criteria']['sum_range']['max_sum']
                ],
                'suggested': [85, 195],
                'reason': 'Sum Range를 넓혀서 더 많은 조합 허용'
            })
            
            suggestions.append({
                'area': 'Consecutive',
                'problem': '연속 번호 제한이 너무 엄격함',
                'current': self.current_config['filters']['criteria']['consecutive']['max_consecutive'],
                'suggested': 3,
                'reason': '연속 3개까지 허용하여 조합 증가'
            })
        
        # 패스율이 너무 높으면
        elif performance.get('pass_rate', 0) > 5.0:
            suggestions.append({
                'area': 'Dispersion',
                'problem': '필터링이 너무 느슨함',
                'current': [
                    self.current_config['filters']['criteria']['dispersion']['min_std_dev'],
                    self.current_config['filters']['criteria']['dispersion']['max_std_dev']
                ],
                'suggested': [8.0, 13.0],
                'reason': '분산도 범위를 좁혀서 필터링 강화'
            })
        
        return suggestions
    
    def apply_suggestion(self, suggestion: Dict) -> Dict:
        """개선 제안 적용"""
        new_config = self.current_config.copy()
        
        if suggestion['area'] == 'Match Filter':
            new_config['filters']['criteria']['match']['max_match'] = suggestion['suggested']
        
        elif suggestion['area'] == 'Sum Range':
            new_config['filters']['criteria']['sum_range']['min_sum'] = suggestion['suggested'][0]
            new_config['filters']['criteria']['sum_range']['max_sum'] = suggestion['suggested'][1]
        
        elif suggestion['area'] == 'Consecutive':
            new_config['filters']['criteria']['consecutive']['max_consecutive'] = suggestion['suggested']
        
        elif suggestion['area'] == 'Dispersion':
            new_config['filters']['criteria']['dispersion']['min_std_dev'] = suggestion['suggested'][0]
            new_config['filters']['criteria']['dispersion']['max_std_dev'] = suggestion['suggested'][1]
        
        return new_config
    
    def test_config(self, config: Dict) -> Dict:
        """설정 테스트"""
        # 임시 설정 파일 생성
        temp_config = "config_temp.yaml"
        with open(temp_config, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        # 원래 설정 백업
        original_config = self.config_path
        
        try:
            # 임시로 설정 변경
            os.rename(self.config_path, f"{self.config_path}.backup")
            os.rename(temp_config, self.config_path)
            
            # 성능 테스트
            performance = self.analyze_current_performance()
            
        finally:
            # 원래 설정 복원
            if os.path.exists(f"{self.config_path}.backup"):
                os.rename(self.config_path, temp_config)
                os.rename(f"{self.config_path}.backup", self.config_path)
        
        # 임시 파일 삭제
        if os.path.exists(temp_config):
            os.remove(temp_config)
        
        return performance
    
    def optimize_simple(self) -> Dict:
        """간단한 최적화 실행"""
        print("\n" + "="*60)
        print("파라미터 최적화 시작")
        print("="*60)
        
        # 현재 성능 분석
        current_perf = self.analyze_current_performance()
        
        print(f"\n현재 성능:")
        print(f"  평균 일치: {current_perf.get('avg_match', 0):.2f}개")
        print(f"  3개+ 일치율: {current_perf.get('three_plus_rate', 0):.1f}%")
        print(f"  패스율: {current_perf.get('pass_rate', 0):.2f}%")
        
        # 개선 제안 생성
        suggestions = self.suggest_improvements(current_perf)
        
        if not suggestions:
            print("\n현재 설정이 이미 최적화되어 있습니다!")
            return {'status': 'already_optimal', 'performance': current_perf}
        
        print(f"\n{len(suggestions)}개의 개선 제안:")
        for i, sugg in enumerate(suggestions, 1):
            print(f"\n{i}. {sugg['area']}")
            print(f"   문제: {sugg['problem']}")
            print(f"   현재값: {sugg['current']}")
            print(f"   제안값: {sugg['suggested']}")
            print(f"   이유: {sugg['reason']}")
        
        # 각 제안 테스트
        best_config = self.current_config
        best_perf = current_perf
        
        for sugg in suggestions:
            print(f"\n{sugg['area']} 개선 테스트 중...")
            
            # 제안 적용
            test_config = self.apply_suggestion(sugg)
            
            # 테스트
            test_perf = self.test_config(test_config)
            
            if test_perf.get('avg_match', 0) > best_perf.get('avg_match', 0):
                best_config = test_config
                best_perf = test_perf
                print(f"  [개선됨] 평균 일치: {test_perf.get('avg_match', 0):.2f}개")
            else:
                print(f"  [유지] 개선 효과 없음")
        
        # 결과 저장
        result = {
            'timestamp': datetime.now().isoformat(),
            'original_performance': current_perf,
            'optimized_performance': best_perf,
            'suggestions': suggestions,
            'improvement': {
                'avg_match': best_perf.get('avg_match', 0) - current_perf.get('avg_match', 0),
                'three_plus_rate': best_perf.get('three_plus_rate', 0) - current_perf.get('three_plus_rate', 0)
            }
        }
        
        # 결과 파일 저장
        result_path = os.path.join(
            self.results_dir,
            f"optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 최적 설정 저장
        if best_perf.get('avg_match', 0) > current_perf.get('avg_match', 0):
            optimal_path = os.path.join(
                self.results_dir,
                f"config_optimal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
            )
            with open(optimal_path, 'w', encoding='utf-8') as f:
                yaml.dump(best_config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"\n최적 설정 저장: {optimal_path}")
        
        return result
    
    def print_summary(self, result: Dict):
        """최적화 결과 요약"""
        print("\n" + "="*60)
        print("최적화 결과 요약")
        print("="*60)
        
        orig = result['original_performance']
        opt = result['optimized_performance']
        imp = result['improvement']
        
        print(f"\n원래 성능:")
        print(f"  평균 일치: {orig.get('avg_match', 0):.2f}개")
        print(f"  3개+ 일치율: {orig.get('three_plus_rate', 0):.1f}%")
        
        print(f"\n최적화 후:")
        print(f"  평균 일치: {opt.get('avg_match', 0):.2f}개")
        print(f"  3개+ 일치율: {opt.get('three_plus_rate', 0):.1f}%")
        
        if imp['avg_match'] > 0:
            print(f"\n개선 효과:")
            print(f"  평균 일치: +{imp['avg_match']:.2f}개")
            print(f"  3개+ 일치율: +{imp['three_plus_rate']:.1f}%")
            print("\n[SUCCESS] 파라미터 최적화 성공!")
        else:
            print("\n[INFO] 현재 설정이 이미 최적 상태입니다.")
        
        print("="*60)


def main():
    """메인 실행 함수"""
    optimizer = SimpleParameterOptimizer()
    
    # 최적화 실행
    result = optimizer.optimize_simple()
    
    # 결과 요약
    if 'status' not in result or result['status'] != 'already_optimal':
        optimizer.print_summary(result)


if __name__ == "__main__":
    main()