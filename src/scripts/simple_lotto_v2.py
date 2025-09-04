#!/usr/bin/env python3
"""
Simple Lotto v2.0 - 정직하고 실용적인 로또 도구
Over-engineering을 버리고 실제 가치에 집중
"""

import random
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import sqlite3

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)


class SimpleLottoV2:
    """단순하고 정직한 로또 도구"""
    
    def __init__(self):
        self.db_path = os.path.join(project_root, 'data', 'lotto_numbers.db')
        self.show_disclaimer()
    
    def show_disclaimer(self):
        """정직한 안내 메시지"""
        print("""
╔══════════════════════════════════════════════════════════╗
║                  Simple Lotto v2.0                       ║
║                                                          ║
║  ⚠️  중요 안내                                           ║
║  • 이 프로그램은 로또를 예측할 수 없습니다              ║
║  • 로또는 완전한 무작위 추첨입니다                      ║
║  • 모든 번호의 당첨 확률은 동일합니다                   ║
║                                                          ║
║  ✅ 제공 기능                                            ║
║  • 재미있는 번호 생성                                    ║
║  • 과거 통계 조회 (참고용)                              ║
║  • 당첨 확률 계산기                                      ║
╚══════════════════════════════════════════════════════════╝
        """)
    
    def main_menu(self):
        """메인 메뉴"""
        while True:
            print("\n메뉴를 선택하세요:")
            print("1. 🎲 빠른 번호 생성 (완전 무작위)")
            print("2. 🎂 특별한 날 번호 (생일, 기념일)")
            print("3. 📊 과거 통계 보기 (재미로만)")
            print("4. 🧮 당첨 확률 계산기")
            print("5. 💾 내 번호 저장하기")
            print("0. 종료")
            
            choice = input("\n선택: ")
            
            if choice == '1':
                self.quick_pick()
            elif choice == '2':
                self.special_date_pick()
            elif choice == '3':
                self.show_statistics()
            elif choice == '4':
                self.probability_calculator()
            elif choice == '5':
                self.save_my_numbers()
            elif choice == '0':
                print("\n행운을 빕니다! 하지만 과도한 지출은 피하세요 😊")
                break
            else:
                print("잘못된 선택입니다.")
    
    def quick_pick(self):
        """빠른 번호 생성"""
        print("\n🎲 빠른 번호 생성")
        print("-" * 40)
        
        count = input("몇 세트를 생성할까요? (기본값: 5): ")
        count = int(count) if count.isdigit() else 5
        
        print(f"\n{count}세트의 번호를 생성합니다:")
        for i in range(count):
            numbers = sorted(random.sample(range(1, 46), 6))
            print(f"{i+1}세트: {' - '.join(map(str, numbers))}")
        
        print("\n💡 알고 계셨나요?")
        print("어떤 번호를 선택하든 당첨 확률은 1/8,145,060로 동일합니다!")
    
    def special_date_pick(self):
        """특별한 날 기반 번호 생성"""
        print("\n🎂 특별한 날 번호 생성")
        print("-" * 40)
        
        numbers = set()
        
        # 생일 입력
        birth = input("생일을 입력하세요 (예: 1990-05-15): ")
        try:
            date = datetime.strptime(birth, "%Y-%m-%d")
            numbers.add(date.day)
            numbers.add(date.month)
            numbers.add(date.year % 45 + 1)  # 년도를 45 이하로 변환
        except:
            print("날짜 형식이 잘못되었습니다.")
        
        # 좋아하는 숫자
        fav = input("좋아하는 숫자를 입력하세요 (쉼표로 구분): ")
        if fav:
            try:
                fav_nums = [int(n.strip()) for n in fav.split(',') if 1 <= int(n.strip()) <= 45]
                numbers.update(fav_nums)
            except:
                pass
        
        # 나머지는 무작위로 채우기
        while len(numbers) < 6:
            numbers.add(random.randint(1, 45))
        
        result = sorted(list(numbers)[:6])
        print(f"\n당신의 특별한 번호: {' - '.join(map(str, result))}")
        print("\n😊 재미있는 방법이지만, 당첨 확률은 여전히 같답니다!")
    
    def show_statistics(self):
        """과거 통계 표시"""
        print("\n📊 과거 당첨 번호 통계")
        print("-" * 40)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 전체 회차 수
            cursor.execute("SELECT COUNT(*) FROM winning_numbers")
            total_draws = cursor.fetchone()[0]
            
            # 번호별 출현 횟수
            freq = {}
            cursor.execute("SELECT numbers FROM winning_numbers")
            for row in cursor.fetchall():
                numbers = [int(n) for n in row[0].split(',')]
                for num in numbers:
                    freq[num] = freq.get(num, 0) + 1
            
            # 가장 많이/적게 나온 번호
            if freq:
                sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)
                most_common = sorted_freq[:5]
                least_common = sorted_freq[-5:]
                
                print(f"\n총 추첨 횟수: {total_draws}회")
                print("\n🔥 가장 많이 나온 번호 TOP 5:")
                for num, count in most_common:
                    print(f"  {num}번: {count}회 ({count/total_draws/6*100:.1f}%)")
                
                print("\n❄️ 가장 적게 나온 번호 TOP 5:")
                for num, count in least_common:
                    print(f"  {num}번: {count}회 ({count/total_draws/6*100:.1f}%)")
                
                # 이론적 확률과 비교
                expected = total_draws * 6 / 45
                print(f"\n📐 이론적 기댓값: {expected:.1f}회")
                print("실제 출현 횟수는 이론값 주변에서 무작위로 분포합니다.")
            
            conn.close()
            
        except Exception as e:
            print(f"통계 조회 중 오류: {e}")
        
        print("\n⚠️ 중요: 과거 통계는 미래 당첨과 아무런 관련이 없습니다!")
        print("각 추첨은 독립적인 사건입니다.")
    
    def probability_calculator(self):
        """당첨 확률 계산기"""
        print("\n🧮 로또 당첨 확률 계산기")
        print("-" * 40)
        
        # 기본 확률
        total_combinations = 8145060  # 45C6
        
        print(f"\n1등 당첨 확률: 1/{total_combinations:,} (0.0000123%)")
        print(f"2등 당첨 확률: 1/{total_combinations//6:,} (보너스 번호 일치)")
        print(f"3등 당첨 확률: 1/{total_combinations//216:,} (5개 번호 일치)")
        print(f"4등 당첨 확률: 1/{total_combinations//9720:,} (4개 번호 일치)")
        print(f"5등 당첨 확률: 1/{total_combinations//194400:,} (3개 번호 일치)")
        
        # 시뮬레이션
        games = input("\n몇 게임을 구매하시나요? (기본값: 1): ")
        games = int(games) if games.isdigit() else 1
        
        prob = 1 - (1 - 1/total_combinations) ** games
        print(f"\n{games}게임 구매 시 1등 당첨 확률: {prob:.8%}")
        
        # 비용 대비 기댓값
        cost = games * 1000
        expected_value = games * (1/total_combinations * 2000000000)  # 평균 1등 상금 20억
        
        print(f"\n💰 투자 비용: {cost:,}원")
        print(f"📈 기댓값: {expected_value:,.0f}원")
        print(f"📉 기대 손실: {cost - expected_value:,.0f}원 ({(cost-expected_value)/cost*100:.1f}%)")
        
        print("\n💡 결론: 로또는 수학적으로 손해보는 게임입니다.")
        print("재미로만 즐기시고, 절대 과도하게 구매하지 마세요!")
    
    def save_my_numbers(self):
        """내 번호 저장"""
        numbers = sorted(random.sample(range(1, 46), 6))
        
        save_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'numbers': numbers,
            'type': 'random'
        }
        
        filename = f"my_lotto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(project_root, 'output', filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 번호가 저장되었습니다: {filepath}")
        print(f"저장된 번호: {' - '.join(map(str, numbers))}")


def main():
    """메인 실행 함수"""
    print("\n🎯 Simple Lotto v2.0 시작합니다...")
    
    lotto = SimpleLottoV2()
    lotto.main_menu()


if __name__ == "__main__":
    main()