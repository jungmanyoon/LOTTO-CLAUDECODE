# -*- coding: utf-8 -*-
"""
[정식 예측 대량 생성 2026-07-04] 다음 회차 예측 5세트를 '정식 예측 기능 그대로' 1회 생성/저장.

용도(사용자 확정): 사람들이 이 많은 예측 중에서 골라 실제 로또를 구매한다. 따라서 '아무 번호'가
아니라 프로그램의 정식 예측 경로(극단성 풀 8.14M 채점 -> 1.5M -> 다양성 5장 선택 + ML 보조신호)를
그대로 사용한다. GitHub Actions bulk-predict.yml 이 정해진 간격으로 호출 -> 정식 예측을 대량 누적.

[정식 100% 재현 - 경량 방식] 주간 작업(main.py)이 저장한 ML 보조신호(data/ml_signal.json, 45번호
선호도 벡터)를 로드해 predict(ml_signal=...)로 주입한다. ML 신호는 회차 고정=결정적이라, 매번
LSTM/앙상블을 재실행하지 않고도 주간 정식 예측과 동일한 방식(ML 포함)으로 5세트를 만든다.
(신호 파일이 없거나 회차 불일치면 극단풀+다양성만 = 대시보드 '새 예측 생성' 버튼과 동일.)

경량: 극단성 풀 채점 + 다양성 선택 + 저장된 ML 신호 주입(numpy 기반, TF/모델 재학습 없음).
중복 조합은 PredictionTracker.save_predictions 의 중복 가드로 스킵(서로 다른 조합만 누적).
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

    # [2026-07-04] 정식 예측 100% 재현: 주간 작업이 저장한 ML 보조신호(45벡터)를 로드해 주입한다.
    # ML 신호는 회차 고정=결정적이라, 주간 1회 계산분을 그 회차 내내 재사용해 ML 모델 재실행 없이
    # 정식(ML 포함) 예측을 그대로 만든다. 신호가 없거나 회차 불일치면 극단풀+다양성만(즉석 예측과 동일).
    ml_signal = None
    try:
        import json
        import numpy as np
        sig_path = os.path.join(ROOT, 'data', 'ml_signal.json')
        if os.path.exists(sig_path):
            with open(sig_path, 'r', encoding='utf-8') as f:
                _sd = json.load(f)
            if int(_sd.get('round', -1)) == next_round and _sd.get('signal'):
                ml_signal = np.array(_sd['signal'], dtype=np.float64)
                print(f"[bulk] 정식 ML 신호 로드(round={next_round}) - 정식 예측 재현")
            else:
                print(f"[bulk] ML 신호 회차 불일치(저장 {_sd.get('round')} != 예측 {next_round}) - 극단풀만")
    except Exception as _me:
        print(f"[bulk] ML 신호 로드 생략({_me}) - 극단풀+다양성만")

    # 매 실행 다른 seed -> 풀 안에서 다른 다양성 조합 5세트 (풀은 동일, 비용 없음)
    seed = int(time.time() * 1000) % 2_000_000
    preds = epp.predict(num_sets=5, seed=seed, ml_signal=ml_signal)
    if not preds:
        print("[bulk] 예측 생성 실패(빈 결과) - 저장 생략")
        return

    tracker = PredictionTracker()
    # replace=False + 중복 조합 가드 -> 이미 있는 조합은 스킵, 신규만 누적
    tracker.save_predictions(next_round, preds, replace=False)
    print(f"[bulk] {next_round}회 예측 5세트 생성/저장 시도 완료 (seed={seed})")


if __name__ == '__main__':
    main()
