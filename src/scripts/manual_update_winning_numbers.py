#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수동으로 최신 당첨번호 업데이트
"""

import sys
import os
import logging
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.db_manager import DatabaseManager
from src.data_collector import DataCollector

def main():
    """최신 당첨번호 수동 업데이트"""

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        # 데이터베이스 매니저 초기화
        db_manager = DatabaseManager()

        # 현재 DB의 마지막 회차 확인
        current_last_round = db_manager.get_last_round()
        logging.info(f"현재 DB 마지막 회차: {current_last_round}회")

        # 현재 날짜 기준으로 예상 회차 계산
        # 로또 1회차: 2002년 12월 7일 토요일
        base_date = datetime(2002, 12, 7)
        current_date = datetime.now()

        # 지난 토요일까지의 주 수 계산
        days_passed = (current_date - base_date).days
        weeks_passed = days_passed // 7
        estimated_round = weeks_passed + 1

        logging.info(f"현재 날짜 기준 예상 최신 회차: {estimated_round}회")

        # 최신 데이터 수집
        if estimated_round > current_last_round:
            logging.info(f"\n새로운 회차 발견! {current_last_round}회 → {estimated_round}회")
            logging.info("최신 당첨번호를 수집합니다...")

            # DataCollector를 사용하여 데이터 수집
            collector = DataCollector(db_manager)
            updated = collector.fetch_lotto_data()

            if updated:
                new_last_round = db_manager.get_last_round()
                logging.info(f"✅ 업데이트 완료! 최신 회차: {new_last_round}회")

                # 최신 회차 정보 표시
                if new_last_round > current_last_round:
                    for round_num in range(current_last_round + 1, new_last_round + 1):
                        winning_nums = db_manager.get_winning_numbers(round_num)
                        if winning_nums:
                            nums_with_bonus = db_manager.get_numbers_with_bonus()
                            bonus = None
                            for r, nums in nums_with_bonus:
                                if r == round_num and len(nums) == 7:
                                    bonus = nums[6]
                                    break

                            logging.info(f"  {round_num}회차: {', '.join(map(str, winning_nums[:6]))}" +
                                       (f" + 보너스 {bonus}" if bonus else ""))
            else:
                logging.warning("업데이트 실패 - 데이터 수집에 문제가 있습니다.")
        else:
            logging.info("이미 최신 데이터입니다.")

            # 마지막 회차 정보 표시
            winning_nums = db_manager.get_winning_numbers(current_last_round)
            if winning_nums:
                nums_with_bonus = db_manager.get_numbers_with_bonus()
                bonus = None
                for r, nums in nums_with_bonus:
                    if r == current_last_round and len(nums) == 7:
                        bonus = nums[6]
                        break

                logging.info(f"최신 {current_last_round}회차: {', '.join(map(str, winning_nums[:6]))}" +
                           (f" + 보너스 {bonus}" if bonus else ""))

    except Exception as e:
        logging.error(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())