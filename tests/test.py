# test.py

import logging
from src.core.db_manager import DatabaseManager
from typing import Dict, List, Tuple
from collections import defaultdict

class LottoSectionAnalyzer:
    def __init__(self):
        try:
            self.db_manager = DatabaseManager()
            
            # 구간 정의 (1-10, 11-20, 21-30, 31-40, 41-45)
            self.sections = [
                (1, 10), (11, 20), (21, 30), (31, 40), (41, 45)
            ]
        except Exception as e:
            logging.error(f"초기화 중 오류 발생: {str(e)}")
            raise

    def analyze_section_distribution(self, winning_numbers: List[str]) -> Dict[Tuple[int, int], Dict[int, float]]:
        """구간별 번호 분포 분석"""
        try:
            section_stats = {section: defaultdict(int) for section in self.sections}
            total = len(winning_numbers)

            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                for section in self.sections:
                    start, end = section
                    # 각 구간별 번호 개수 계산
                    count = sum(1 for num in numbers if start <= num <= end)
                    section_stats[section][count] += 1

            # 백분율 계산 및 결과 정리
            result = {}
            for section, counts in section_stats.items():
                result[section] = {
                    k: (v/total)*100 
                    for k, v in counts.items()
                }

            return result
        except Exception as e:
            logging.error(f"구간별 분포 분석 중 오류 발생: {str(e)}")
            return {}

    def get_detailed_section_stats(self, section_stats: Dict) -> Dict:
        """구간별 상세 통계 계산"""
        try:
            detailed_stats = {}
            
            for section, stats in section_stats.items():
                start, end = section
                section_name = f"{start}-{end}"
                
                # 가장 많이 나온 개수와 그 비율
                max_count, max_percentage = max(stats.items(), key=lambda x: x[1])
                
                # 평균 출현 개수 계산
                weighted_avg = sum(count * percentage/100 for count, percentage in stats.items())
                
                detailed_stats[section_name] = {
                    'most_frequent': {
                        'count': max_count,
                        'percentage': max_percentage
                    },
                    'average_count': weighted_avg,
                    'distribution': dict(sorted(stats.items()))
                }
                
            return detailed_stats
        except Exception as e:
            logging.error(f"상세 통계 계산 중 오류 발생: {str(e)}")
            return {}

    def run_analysis(self):
        """분석 실행"""
        try:
            print("\n=== 로또 당첨번호 구간별 분석 시작 ===")
            
            winning_numbers = self.db_manager.lotto_db.get_all_winning_numbers()
            if not winning_numbers:
                print("분석할 당첨번호가 없습니다.")
                return

            print(f"\n총 분석 대상 당첨번호: {len(winning_numbers)}개")
            
            section_stats = self.analyze_section_distribution(winning_numbers)
            detailed_stats = self.get_detailed_section_stats(section_stats)
            
            # 수정된 결과 출력
            print("\n=== 구간별 번호 분포 분석 결과 ===")
            
            for section_name, stats in detailed_stats.items():
                print(f"\n[구간 {section_name}]")
                print(f"* 평균 출현 개수: {stats['average_count']:.2f}개")
                
                # 0개를 제외한 가장 높은 비율 찾기
                non_zero_stats = {k: v for k, v in stats['distribution'].items() if k > 0}
                if non_zero_stats:
                    max_count = max(non_zero_stats.items(), key=lambda x: x[1])
                    print(f"* 가장 많이 나온 패턴: {max_count[0]}개 ({max_count[1]:.2f}%)")
                
                print("* 상세 분포:")
                # 구간별 최대 가능 개수 설정
                max_possible = 6
                if section_name == "41-45":
                    max_possible = 5  # 41-45 구간은 최대 5개까지만 가능
                
                # 1부터 최대 가능 개수까지 모든 경우 출력
                for count in range(1, max_possible + 1):
                    percentage = stats['distribution'].get(count, 0.0)  # 없는 경우 0.0%로 표시
                    print(f"  - {count}개: {percentage:.2f}%")
            
            # 수정된 특이사항 출력
            print("\n=== 특이사항 ===")
            for section_name, stats in detailed_stats.items():
                # 4개 이상 출현하는 모든 경우 표시
                high_counts = {
                    count: pct for count, pct in stats['distribution'].items() 
                    if count >= 4
                }
                if high_counts:
                    print(f"\n구간 {section_name} 4개 이상 출현:")
                    max_possible = 6 if section_name != "41-45" else 5
                    for count in range(4, max_possible + 1):
                        percentage = high_counts.get(count, 0.0)
                        print(f"- {count}개: {percentage:.2f}%")
                        
            print("\n분석이 완료되었습니다.")

        except Exception as e:
            print(f"분석 중 오류 발생: {str(e)}")
            logging.error(f"상세 오류: {str(e)}", exc_info=True)

    def find_arithmetic_sequences(self, numbers: List[int], min_length: int = 3) -> List[List[int]]:
        """주어진 번호에서 등차수열 찾기"""
        try:
            numbers = sorted(numbers)
            n = len(numbers)
            sequences = []
            
            # 가능한 모든 시작점과 공차 조합 시도
            for i in range(n-2):
                for j in range(i+1, n-1):
                    diff = numbers[j] - numbers[i]
                    current_seq = [numbers[i], numbers[j]]
                    
                    # 다음 숫자들이 등차수열을 이루는지 확인
                    next_num = numbers[j] + diff
                    for k in range(j+1, n):
                        if numbers[k] == next_num:
                            current_seq.append(numbers[k])
                            next_num += diff
                    
                    if len(current_seq) >= min_length:
                        sequences.append(current_seq)
            
            return sequences
        except Exception as e:
            logging.error(f"등차수열 검색 중 오류 발생: {str(e)}")
            return []

    def find_geometric_sequences(self, numbers: List[int], min_length: int = 3) -> List[List[int]]:
        """주어진 번호에서 등비수열 찾기"""
        try:
            numbers = sorted(numbers)
            n = len(numbers)
            sequences = []
            
            # 가능한 모든 시작점과 공비 조합 시도
            for i in range(n-2):
                for j in range(i+1, n-1):
                    if numbers[i] == 0:  # 0은 등비수열에서 제외
                        continue
                    
                    ratio = numbers[j] / numbers[i]
                    if not ratio.is_integer():  # 정수 비율만 고려
                        continue
                        
                    current_seq = [numbers[i], numbers[j]]
                    next_num = int(numbers[j] * ratio)
                    
                    # 다음 숫자들이 등비수열을 이루는지 확인
                    for k in range(j+1, n):
                        if numbers[k] == next_num and next_num <= 45:
                            current_seq.append(numbers[k])
                            next_num = int(next_num * ratio)
                    
                    if len(current_seq) >= min_length:
                        sequences.append(current_seq)
            
            return sequences
        except Exception as e:
            logging.error(f"등비수열 검색 중 오류 발생: {str(e)}")
            return []

    def analyze_sequences(self, winning_numbers: List[str]) -> Dict:
        """등차수열과 등비수열 패턴 분석"""
        try:
            stats = {
                'arithmetic': defaultdict(int),
                'geometric': defaultdict(int)
            }
            
            total = len(winning_numbers)
            
            for numbers_str in winning_numbers:
                numbers = list(map(int, numbers_str.split(',')))
                
                # 등차수열 분석
                for min_len in range(3, 7):
                    arith_sequences = self.find_arithmetic_sequences(numbers, min_len)
                    if arith_sequences:
                        max_len = max(len(seq) for seq in arith_sequences)
                        stats['arithmetic'][max_len] += 1
                
                # 등비수열 분석
                for min_len in range(3, 7):
                    geom_sequences = self.find_geometric_sequences(numbers, min_len)
                    if geom_sequences:
                        max_len = max(len(seq) for seq in geom_sequences)
                        stats['geometric'][max_len] += 1
            
            # 백분율 계산
            result = {
                'arithmetic': {
                    length: (count/total*100) 
                    for length, count in stats['arithmetic'].items()
                },
                'geometric': {
                    length: (count/total*100) 
                    for length, count in stats['geometric'].items()
                }
            }
            
            return result
        except Exception as e:
            logging.error(f"수열 패턴 분석 중 오류 발생: {str(e)}")
            return {}

    def run_sequence_analysis(self):
        """수열 패턴 분석 실행"""
        try:
            print("\n=== 로또 당첨번호 수열 패턴 분석 시작 ===")
            
            winning_numbers = self.db_manager.lotto_db.get_all_winning_numbers()
            if not winning_numbers:
                print("분석할 당첨번호가 없습니다.")
                return

            print(f"\n총 분석 대상 당첨번호: {len(winning_numbers)}개")
            
            sequence_stats = self.analyze_sequences(winning_numbers)
            
            # 등차수열 결과 출력
            print("\n=== 등차수열 패턴 분석 결과 ===")
            print("연속된 숫자의 차이가 일정한 패턴")
            for length in range(3, 7):
                percentage = sequence_stats['arithmetic'].get(length, 0.0)
                print(f"* {length}개 연속 등차수열: {percentage:.2f}%")
                if length == 6:
                    print("  - 예시: 2,7,12,17,22,27 또는 1,10,19,28,37")
                elif length == 5:
                    print("  - 예시: 3,9,15,21,27 또는 2,12,22,32,42")
                elif length == 4:
                    print("  - 예시: 1,11,21,31 또는 5,15,25,35")
                elif length == 3:
                    print("  - 예시: 2,12,22 또는 5,15,25")
            
            # 등비수열 결과 출력
            print("\n=== 등비수열 패턴 분석 결과 ===")
            print("연속된 숫자의 비율이 일정한 패턴")
            for length in range(3, 7):
                percentage = sequence_stats['geometric'].get(length, 0.0)
                print(f"* {length}개 연속 등비수열: {percentage:.2f}%")
                if length == 6:
                    print("  - 예시: 1,2,4,8,16,32 또는 1,3,9,27")
                elif length == 5:
                    print("  - 예시: 1,2,4,8,16 또는 2,6,18")
                elif length == 4:
                    print("  - 예시: 2,4,8,16 또는 3,9,27")
                elif length == 3:
                    print("  - 예시: 2,4,8 또는 3,9,27")

            print("\n분석이 완료되었습니다.")

        except Exception as e:
            print(f"분석 중 오류 발생: {str(e)}")
            logging.error(f"상세 오류: {str(e)}", exc_info=True)


def main():
    try:
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # 분석 실행
        analyzer = LottoSectionAnalyzer()
        analyzer.run_analysis()
        analyzer.run_sequence_analysis()
        
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {str(e)}")
        logging.error(f"메인 프로그램 오류: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()