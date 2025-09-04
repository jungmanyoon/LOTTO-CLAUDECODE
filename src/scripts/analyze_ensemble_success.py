"""
ENSEMBLE 모델 성공 케이스 심층 분석 도구
5개 이상 일치한 케이스의 패턴을 찾아 재현 가능한 조건 도출
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter
import pandas as pd

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class EnsembleSuccessAnalyzer:
    """ENSEMBLE 모델 성공 케이스 분석기"""
    
    def __init__(self):
        """초기화"""
        self.success_cases = []  # 4개 이상 일치한 케이스
        self.exceptional_cases = []  # 5개 이상 일치한 케이스
        self.pattern_analysis = {}
        
    def load_backtest_results(self, result_files: List[str] = None):
        """백테스팅 결과 파일 로드"""
        
        if result_files is None:
            # results 폴더에서 최근 백테스팅 결과 파일 찾기
            results_dir = "results"
            result_files = []
            
            if os.path.exists(results_dir):
                for file in os.listdir(results_dir):
                    if file.startswith("backtest_results") and file.endswith(".json"):
                        result_files.append(os.path.join(results_dir, file))
            
            result_files.sort(reverse=True)  # 최신 파일 먼저
            result_files = result_files[:5]  # 최근 5개만
        
        logging.info(f"분석할 파일: {len(result_files)}개")
        
        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._extract_success_cases(data, file_path)
            except Exception as e:
                logging.error(f"파일 로드 실패 {file_path}: {e}")
    
    def _extract_success_cases(self, data: Dict, source_file: str):
        """백테스팅 데이터에서 성공 케이스 추출"""
        
        if 'model_performance' not in data:
            return
        
        # ENSEMBLE 모델 결과 찾기
        ensemble_data = data['model_performance'].get('ensemble', {})
        
        if 'predictions' in ensemble_data:
            for pred_data in ensemble_data['predictions']:
                match_count = pred_data.get('match_count', 0)
                
                if match_count >= 4:
                    case = {
                        'source': source_file,
                        'round': pred_data.get('round', 'unknown'),
                        'prediction': pred_data.get('prediction', []),
                        'actual': pred_data.get('actual', []),
                        'match_count': match_count,
                        'matched_numbers': pred_data.get('matches', [])
                    }
                    
                    self.success_cases.append(case)
                    
                    if match_count >= 5:
                        self.exceptional_cases.append(case)
    
    def analyze_patterns(self):
        """성공 케이스의 패턴 분석"""
        
        if not self.success_cases:
            logging.warning("분석할 성공 케이스가 없습니다.")
            return
        
        logging.info(f"총 {len(self.success_cases)}개 성공 케이스 분석 중...")
        logging.info(f"  - 4개 일치: {len([c for c in self.success_cases if c['match_count'] == 4])}개")
        logging.info(f"  - 5개 일치: {len([c for c in self.success_cases if c['match_count'] == 5])}개")
        logging.info(f"  - 6개 일치: {len([c for c in self.success_cases if c['match_count'] == 6])}개")
        
        # 1. 번호 빈도 분석
        self._analyze_number_frequency()
        
        # 2. 번호 간격 패턴 분석
        self._analyze_gap_patterns()
        
        # 3. 홀짝 비율 분석
        self._analyze_odd_even_ratio()
        
        # 4. 구간 분포 분석
        self._analyze_section_distribution()
        
        # 5. 연속 번호 패턴
        self._analyze_consecutive_patterns()
        
        # 6. 합계 범위 분석
        self._analyze_sum_range()
        
        # 7. 시간대/회차 패턴
        self._analyze_temporal_patterns()
    
    def _analyze_number_frequency(self):
        """성공 케이스에서 자주 나온 번호 분석"""
        
        all_numbers = []
        exceptional_numbers = []
        
        for case in self.success_cases:
            all_numbers.extend(case['prediction'])
            
            if case['match_count'] >= 5:
                exceptional_numbers.extend(case['prediction'])
        
        # 전체 빈도
        freq_all = Counter(all_numbers)
        # 5개 이상 일치 케이스의 빈도
        freq_exceptional = Counter(exceptional_numbers)
        
        self.pattern_analysis['number_frequency'] = {
            'all_cases': dict(freq_all.most_common(10)),
            'exceptional_cases': dict(freq_exceptional.most_common(10)) if exceptional_numbers else {}
        }
        
        logging.info("\n[번호 빈도 분석]")
        logging.info("가장 많이 예측된 번호 (전체):")
        for num, count in freq_all.most_common(5):
            logging.info(f"  {num}: {count}회")
        
        if freq_exceptional:
            logging.info("가장 많이 예측된 번호 (5개+ 일치):")
            for num, count in freq_exceptional.most_common(5):
                logging.info(f"  {num}: {count}회")
    
    def _analyze_gap_patterns(self):
        """번호 간격 패턴 분석"""
        
        gaps_all = []
        gaps_exceptional = []
        
        for case in self.success_cases:
            numbers = sorted(case['prediction'])
            gaps = [numbers[i+1] - numbers[i] for i in range(len(numbers)-1)]
            gaps_all.extend(gaps)
            
            if case['match_count'] >= 5:
                gaps_exceptional.extend(gaps)
        
        self.pattern_analysis['gap_patterns'] = {
            'all_cases': {
                'mean_gap': np.mean(gaps_all) if gaps_all else 0,
                'std_gap': np.std(gaps_all) if gaps_all else 0,
                'common_gaps': dict(Counter(gaps_all).most_common(5)) if gaps_all else {}
            },
            'exceptional_cases': {
                'mean_gap': np.mean(gaps_exceptional) if gaps_exceptional else 0,
                'std_gap': np.std(gaps_exceptional) if gaps_exceptional else 0,
                'common_gaps': dict(Counter(gaps_exceptional).most_common(5)) if gaps_exceptional else {}
            }
        }
        
        logging.info("\n[번호 간격 패턴]")
        if gaps_all:
            logging.info(f"평균 간격: {np.mean(gaps_all):.2f}")
            logging.info(f"표준편차: {np.std(gaps_all):.2f}")
    
    def _analyze_odd_even_ratio(self):
        """홀짝 비율 분석"""
        
        ratios_all = []
        ratios_exceptional = []
        
        for case in self.success_cases:
            odd_count = sum(1 for n in case['prediction'] if n % 2 == 1)
            ratio = f"{odd_count}:{6-odd_count}"
            ratios_all.append(ratio)
            
            if case['match_count'] >= 5:
                ratios_exceptional.append(ratio)
        
        self.pattern_analysis['odd_even_ratio'] = {
            'all_cases': dict(Counter(ratios_all).most_common()),
            'exceptional_cases': dict(Counter(ratios_exceptional).most_common()) if ratios_exceptional else {}
        }
        
        logging.info("\n[홀짝 비율 패턴]")
        for ratio, count in Counter(ratios_all).most_common(3):
            logging.info(f"  {ratio} - {count}회")
    
    def _analyze_section_distribution(self):
        """구간 분포 분석 (1-15, 16-30, 31-45)"""
        
        distributions_all = []
        distributions_exceptional = []
        
        for case in self.success_cases:
            section1 = sum(1 for n in case['prediction'] if 1 <= n <= 15)
            section2 = sum(1 for n in case['prediction'] if 16 <= n <= 30)
            section3 = sum(1 for n in case['prediction'] if 31 <= n <= 45)
            
            dist = f"{section1}-{section2}-{section3}"
            distributions_all.append(dist)
            
            if case['match_count'] >= 5:
                distributions_exceptional.append(dist)
        
        self.pattern_analysis['section_distribution'] = {
            'all_cases': dict(Counter(distributions_all).most_common()),
            'exceptional_cases': dict(Counter(distributions_exceptional).most_common()) if distributions_exceptional else {}
        }
        
        logging.info("\n[구간 분포 패턴]")
        for dist, count in Counter(distributions_all).most_common(3):
            logging.info(f"  {dist} - {count}회")
    
    def _analyze_consecutive_patterns(self):
        """연속 번호 패턴 분석"""
        
        consecutive_counts = []
        
        for case in self.success_cases:
            numbers = sorted(case['prediction'])
            consecutive = 0
            max_consecutive = 0
            
            for i in range(len(numbers)-1):
                if numbers[i+1] - numbers[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            
            consecutive_counts.append(max_consecutive)
        
        self.pattern_analysis['consecutive_patterns'] = {
            'distribution': dict(Counter(consecutive_counts))
        }
        
        logging.info("\n[연속 번호 패턴]")
        for count, freq in Counter(consecutive_counts).most_common():
            if count > 0:
                logging.info(f"  {count+1}개 연속: {freq}회")
    
    def _analyze_sum_range(self):
        """합계 범위 분석"""
        
        sums_all = []
        sums_exceptional = []
        
        for case in self.success_cases:
            total = sum(case['prediction'])
            sums_all.append(total)
            
            if case['match_count'] >= 5:
                sums_exceptional.append(total)
        
        self.pattern_analysis['sum_range'] = {
            'all_cases': {
                'mean': np.mean(sums_all) if sums_all else 0,
                'std': np.std(sums_all) if sums_all else 0,
                'min': min(sums_all) if sums_all else 0,
                'max': max(sums_all) if sums_all else 0
            },
            'exceptional_cases': {
                'mean': np.mean(sums_exceptional) if sums_exceptional else 0,
                'std': np.std(sums_exceptional) if sums_exceptional else 0,
                'min': min(sums_exceptional) if sums_exceptional else 0,
                'max': max(sums_exceptional) if sums_exceptional else 0
            }
        }
        
        logging.info("\n[합계 범위 패턴]")
        if sums_all:
            logging.info(f"평균 합계: {np.mean(sums_all):.1f}")
            logging.info(f"범위: {min(sums_all)} ~ {max(sums_all)}")
    
    def _analyze_temporal_patterns(self):
        """시간대/회차 패턴 분석"""
        
        rounds = []
        
        for case in self.success_cases:
            if case['round'] != 'unknown':
                rounds.append(case['round'])
        
        if rounds:
            # 회차 간격 분석
            rounds = [int(r) for r in rounds if r.isdigit()]
            if len(rounds) > 1:
                rounds.sort()
                intervals = [rounds[i+1] - rounds[i] for i in range(len(rounds)-1)]
                
                self.pattern_analysis['temporal_patterns'] = {
                    'round_intervals': {
                        'mean': np.mean(intervals),
                        'std': np.std(intervals)
                    }
                }
                
                logging.info("\n[시간 패턴]")
                logging.info(f"성공 케이스 평균 간격: {np.mean(intervals):.1f}회차")
    
    def generate_recommendations(self) -> Dict:
        """분석 결과를 바탕으로 추천 생성"""
        
        recommendations = {
            'high_frequency_numbers': [],
            'optimal_odd_even_ratio': '',
            'optimal_section_distribution': '',
            'optimal_sum_range': {},
            'avoid_patterns': [],
            'success_conditions': []
        }
        
        if not self.pattern_analysis:
            return recommendations
        
        # 1. 자주 나온 번호 추천
        if 'number_frequency' in self.pattern_analysis:
            freq = self.pattern_analysis['number_frequency']
            if freq.get('exceptional_cases'):
                top_numbers = list(freq['exceptional_cases'].keys())[:10]
            else:
                top_numbers = list(freq['all_cases'].keys())[:10]
            recommendations['high_frequency_numbers'] = top_numbers
        
        # 2. 최적 홀짝 비율
        if 'odd_even_ratio' in self.pattern_analysis:
            ratios = self.pattern_analysis['odd_even_ratio']['all_cases']
            if ratios:
                recommendations['optimal_odd_even_ratio'] = list(ratios.keys())[0]
        
        # 3. 최적 구간 분포
        if 'section_distribution' in self.pattern_analysis:
            dists = self.pattern_analysis['section_distribution']['all_cases']
            if dists:
                recommendations['optimal_section_distribution'] = list(dists.keys())[0]
        
        # 4. 최적 합계 범위
        if 'sum_range' in self.pattern_analysis:
            sum_data = self.pattern_analysis['sum_range']['all_cases']
            if sum_data['mean'] > 0:
                recommendations['optimal_sum_range'] = {
                    'min': int(sum_data['mean'] - sum_data['std']),
                    'max': int(sum_data['mean'] + sum_data['std'])
                }
        
        # 5. 성공 조건 요약
        if self.exceptional_cases:
            recommendations['success_conditions'].append(
                f"5개 이상 일치 달성: {len(self.exceptional_cases)}회"
            )
        
        return recommendations
    
    def save_analysis(self, filename: str = None):
        """분석 결과 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"results/ensemble_success_analysis_{timestamp}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        analysis_data = {
            'timestamp': datetime.now().isoformat(),
            'total_success_cases': len(self.success_cases),
            'exceptional_cases_count': len(self.exceptional_cases),
            'pattern_analysis': self.pattern_analysis,
            'recommendations': self.generate_recommendations(),
            'exceptional_cases_detail': self.exceptional_cases[:10]  # 상위 10개만
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"\n분석 결과 저장: {filename}")
    
    def print_summary(self):
        """분석 요약 출력"""
        
        print("\n" + "="*70)
        print("ENSEMBLE 모델 성공 케이스 분석 요약")
        print("="*70)
        
        print(f"\n총 성공 케이스: {len(self.success_cases)}개")
        print(f"  - 4개 일치: {len([c for c in self.success_cases if c['match_count'] == 4])}개")
        print(f"  - 5개 일치: {len([c for c in self.success_cases if c['match_count'] == 5])}개")
        print(f"  - 6개 일치: {len([c for c in self.success_cases if c['match_count'] == 6])}개")
        
        recommendations = self.generate_recommendations()
        
        if recommendations['high_frequency_numbers']:
            print(f"\n추천 번호 (빈도 높음): {recommendations['high_frequency_numbers'][:6]}")
        
        if recommendations['optimal_odd_even_ratio']:
            print(f"최적 홀짝 비율: {recommendations['optimal_odd_even_ratio']}")
        
        if recommendations['optimal_section_distribution']:
            print(f"최적 구간 분포: {recommendations['optimal_section_distribution']}")
        
        if recommendations['optimal_sum_range']:
            range_data = recommendations['optimal_sum_range']
            print(f"최적 합계 범위: {range_data['min']} ~ {range_data['max']}")
        
        if self.exceptional_cases:
            print("\n[5개 이상 일치 케이스 상세]")
            for i, case in enumerate(self.exceptional_cases[:3], 1):
                print(f"\n{i}. 회차 {case['round']}")
                print(f"   예측: {case['prediction']}")
                print(f"   실제: {case['actual']}")
                print(f"   일치: {case['matched_numbers']} ({case['match_count']}개)")
        
        print("="*70)


def main():
    """메인 실행 함수"""
    
    analyzer = EnsembleSuccessAnalyzer()
    
    # 백테스팅 결과 로드
    print("백테스팅 결과 파일 로드 중...")
    analyzer.load_backtest_results()
    
    # 패턴 분석
    print("\n패턴 분석 중...")
    analyzer.analyze_patterns()
    
    # 결과 저장
    analyzer.save_analysis()
    
    # 요약 출력
    analyzer.print_summary()
    
    print("\n분석 완료!")


if __name__ == "__main__":
    main()