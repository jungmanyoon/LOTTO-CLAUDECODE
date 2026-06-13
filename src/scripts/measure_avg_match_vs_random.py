# -*- coding: utf-8 -*-
"""
시스템이 실제로 내는 예측 세트의 '티켓당 평균 일치'가 무작위(이론 0.8)보다
체계적으로 낮은지/같은지/높은지를 walk-forward blind로 측정.

배경(2026-06-06): 사용자가 1227회 240세트 평균 일치 0.63(<무작위 0.8), 3개+ 0건을 보고
"무작위보다 낮은 것 아니냐"고 정당하게 의문. 한 회차 운인지 구조적 저성능인지 데이터로 확정한다.

blind: fold 마다 build_pool(train_until=fold직전), holdout 회차로만 평가(미래 미사용).
비교: PROD(극단성 풀 + 다양성 선택) vs RAND(8.14M 완전 무작위). 동일 SETS_PER_DRAW.
지표: 티켓당 평균 일치(이론 무작위 0.8), 티켓당 P(>=3)(이론 0.02386), 회차당 최고일치 평균,
      회차당 'SETS_PER_DRAW개 중 하나라도 3+' 비율.
ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.db_manager import DatabaseManager
from src.core.extremeness_pool_predictor import ExtremenessPoolPredictor


def main():
    folds = int(os.environ.get('AM_FOLDS', '6'))
    window = int(os.environ.get('AM_WINDOW', '30'))
    sets_per_draw = int(os.environ.get('AM_SETS', '20'))
    K = int(os.environ.get('AM_K', '1500000'))

    db = DatabaseManager()
    rows = []
    for r, t in db.get_numbers_with_bonus():
        rows.append((int(r), set(int(x) for x in t[:6])))
    rows.sort(key=lambda x: x[0])
    total = len(rows)
    first = max(1, total - folds * window)
    specs = []
    s = first
    while s + window <= total:
        specs.append((s, s + window))
        s += window
    if not specs:
        print('[측정] 데이터 부족')
        return

    rng = np.random.RandomState(123)
    prod_match = []   # 티켓당 일치(전체)
    rand_match = []
    prod_best = []    # 회차당 최고일치
    prod_has3 = []    # 회차당 (포트폴리오 내 하나라도 3+)
    rand_has3 = []

    n_draw = 0
    for (a, b) in specs:
        train_until = rows[a - 1][0]
        try:
            epp = ExtremenessPoolPredictor(db, target_K=K)
            epp.build_pool(train_until=train_until)
        except Exception as e:
            print('[측정] fold(train<=%d) build 실패: %s' % (train_until, e))
            continue
        # PROD 포트폴리오는 fold 당 1회 생성(=그 시점 풀로 만든 실제 예측)하고,
        # holdout 회차들에 대해 평가한다(production-faithful + 30배 빠름).
        psets = []
        k = 0
        while len(psets) < sets_per_draw:
            out = epp.predict(num_sets=5, seed=1000 + k)
            for s2 in out:
                psets.append(set(int(x) for x in s2['numbers']))
            k += 5
        psets = psets[:sets_per_draw]
        for (_rr, win) in rows[a:b]:
            n_draw += 1
            pm = [len(s2 & win) for s2 in psets]
            prod_match.extend(pm)
            prod_best.append(max(pm))
            prod_has3.append(1 if max(pm) >= 3 else 0)
            # RAND 포트폴리오
            rsets = [set(rng.choice(range(1, 46), 6, replace=False).tolist()) for _ in range(sets_per_draw)]
            rm = [len(s2 & win) for s2 in rsets]
            rand_match.extend(rm)
            rand_has3.append(1 if max(rm) >= 3 else 0)

    pm = np.array(prod_match, dtype=float)
    rm = np.array(rand_match, dtype=float)
    print('=' * 70)
    print('[측정] walk-forward | folds=%d window=%d sets/draw=%d | 회차=%d 티켓=%d'
          % (len(specs), window, sets_per_draw, n_draw, len(pm)))
    print('-' * 70)
    print('PROD  티켓당 평균 일치 = %.4f   P(티켓>=3) = %.4f' % (pm.mean(), (pm >= 3).mean()))
    print('RAND  티켓당 평균 일치 = %.4f   P(티켓>=3) = %.4f  (이론 0.8000 / 0.02386)'
          % (rm.mean(), (rm >= 3).mean()))
    print('-' * 70)
    print('PROD  회차당 최고일치 평균 = %.3f   회차중 (포트폴리오 3+ 적중) = %.1f%%'
          % (np.mean(prod_best), 100.0 * np.mean(prod_has3)))
    print('RAND  회차중 (포트폴리오 3+ 적중) = %.1f%%' % (100.0 * np.mean(rand_has3)))
    print('-' * 70)
    diff = pm.mean() - rm.mean()
    if diff < -0.02:
        verdict = 'PROD < RAND => 체계적으로 무작위보다 낮음 (구조적 결함 - 수정가치 큼)'
    elif diff > 0.02:
        verdict = 'PROD > RAND => 무작위보다 약간 높음 (1227회는 나쁜 운)'
    else:
        verdict = 'PROD ~= RAND => 사실상 동등 (우위 없음, 1227회는 변동)'
    print('[결론] 티켓당 평균 일치 차이 = %+.4f -> %s' % (diff, verdict))
    print('=' * 70)


if __name__ == '__main__':
    main()
