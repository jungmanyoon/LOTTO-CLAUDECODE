"""로또 등수 계산 유틸리티"""

from typing import List, Optional

def calculate_lotto_rank(prediction: List[int], actual: List[int], bonus: int) -> Optional[int]:
    """
    로또 등수 계산 (보너스 번호 포함)
    
    Args:
        prediction: 예측 번호 6개
        actual: 실제 당첨번호 6개
        bonus: 보너스 번호
    
    Returns:
        등수 (1~5) 또는 None (낙첨)
    """
    pred_set = set(prediction)
    actual_set = set(actual)
    
    # 일치 개수
    match_count = len(pred_set & actual_set)
    
    # 보너스 일치 여부
    bonus_match = bonus in pred_set
    
    # 등수 판정
    if match_count == 6:
        return 1  # 1등: 6개 모두 일치
    elif match_count == 5 and bonus_match:
        return 2  # 2등: 5개 + 보너스
    elif match_count == 5:
        return 3  # 3등: 5개
    elif match_count == 4:
        return 4  # 4등: 4개
    elif match_count == 3:
        return 5  # 5등: 3개
    else:
        return None  # 낙첨


# 당첨금 정보 (2024년 기준 평균)
PRIZE_MONEY = {
    1: 2_000_000_000,  # 1등: 약 20억
    2: 50_000_000,     # 2등: 약 5천만원
    3: 1_500_000,      # 3등: 약 150만원
    4: 50_000,         # 4등: 5만원
    5: 5_000,          # 5등: 5천원
}