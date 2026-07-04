# -*- coding: utf-8 -*-
"""
[재미용 대량 예측 2026-07-04] 극단성 풀에서 5세트를 1회 생성해 저장.

GitHub Actions bulk-predict.yml 이 30분마다 호출 -> 다음 회차 예측을 대량 누적한다.
추첨 후 '일주일치 수천 세트 중 최고 몇 개 맞았나'를 보는 재미용이다.

[정직성] 이것은 '성능 파악용'이 아니다. 10~30분마다 만들어도 전부 '같은 회차' 예측이라
통계 표본이 1개다(시험 문제 하나를 여러 번 푸는 것과 동일). 또 세트를 많이 만들수록
당첨 확률이 오르는 건 '많이 사면 확률↑'(예산)이지 전략 성능이 아니다. 진짜 성능은
'여러 회차 누적'(대시보드 추이 패널) 또는 walk-forward 백테스트로 봐야 한다.

경량: 극단성 풀 예측만 수행(numpy 기반). ML/TF/백테스트/최적화 없음. 중복 조합은
PredictionTracker.save_predictions 의 중복 가드로 저장 스킵(신규 조합만 누적).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import logging
logging.getLogger().setLevel(logging.WARNING)


def main():
    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor
    from src.core.prediction_tracker import PredictionTracker

    db = DatabaseManager()
    latest = db.get_last_round()
    next_round = int(latest) + 1

    epp = ExtremenessPoolPredictor(db)
    epp.build_pool()  # 캐시(회차+K+가중치 동일) 있으면 즉시, 없으면 8.14M 채점(clean 약 1-2분)

    # 매 실행 다른 seed -> 풀 안에서 다른 다양성 조합 5세트 (풀은 동일, 비용 없음)
    seed = int(time.time() * 1000) % 2_000_000
    preds = epp.predict(num_sets=5, seed=seed)
    if not preds:
        print("[bulk] 예측 생성 실패(빈 결과) - 저장 생략")
        return

    tracker = PredictionTracker()
    # replace=False + 중복 조합 가드 -> 이미 있는 조합은 스킵, 신규만 누적
    tracker.save_predictions(next_round, preds, replace=False)
    print(f"[bulk] {next_round}회 예측 5세트 생성/저장 시도 완료 (seed={seed})")


if __name__ == '__main__':
    main()
