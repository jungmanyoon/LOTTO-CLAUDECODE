# -*- coding: utf-8 -*-
"""
극단성 풀이 '무엇을' 제거해 1.5M을 남기는지 투명하게 진단.

배경(2026-06-06): 사용자가 "지금 방식은 뭘 제거해 150만개를 남겼는지 모르겠다. 이게 가장
기본이고 중요한데 재검토해야겠다"고 함. 마할라노비스 극단성 점수는 불투명하므로, 제거된
6.6M vs 남은 1.5M이 어떤 특성으로 갈리는지 + 가장자리(1,45) 번호가 과잉 제거되는지 + 역대
당첨번호 보존율(가장자리 포함/미포함 비교)을 숫자로 드러낸다.

ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.db_manager import DatabaseManager
from src.core.extremeness_scorer import ExtremenessScorer

K = int(os.environ.get('DIAG_K', '1500000'))


def main():
    db = DatabaseManager()
    scorer = ExtremenessScorer(db)
    scorer.fit_until(None)  # 전체 역사 학습

    combos = ExtremenessScorer.all_combinations()  # (8.14M,6) int8
    M = combos.shape[0]
    print('[진단] 전체 조합=%d, 목표 풀 K=%d (제거 목표 %d, %.1f%%)' % (M, K, M - K, 100.0 * (M - K) / M))

    scores = scorer.score(combos)  # (8.14M,)
    cutoff = ExtremenessScorer.cutoff_for_size(scores, K)
    removed = scores > cutoff
    kept = ~removed
    print('[진단] 극단성 점수 컷오프 = %.2f (이 값 초과면 제거). 제거 %d개 / 유지 %d개'
          % (cutoff, int(removed.sum()), int(kept.sum())))
    print('-' * 72)

    # 1) 점수 성분 분해(샘플): 제거 vs 유지에서 무엇이 점수를 끌어올렸나
    rng = np.random.RandomState(0)
    idx = rng.choice(M, size=min(300000, M), replace=False)
    comp = scorer.score_components(combos[idx])
    s_removed = comp['total'] > cutoff
    s_kept = ~s_removed

    def mean_pair(arr):
        return float(arr[s_removed].mean()), float(arr[s_kept].mean())

    print('[성분별 평균] (제거 / 유지) - 클수록 그 성분이 제거를 유발')
    for name, key in [('마할라노비스거리^2', 'mahalanobis2'),
                      ('최장연속 페널티', 'pen_max_consecutive'),
                      ('홀짝 페널티', 'pen_odd_count'),
                      ('동일끝자리 페널티', 'pen_max_same_last_digit'),
                      ('구간몰림 페널티', 'pen_max_section_occupancy')]:
        r, k = mean_pair(comp[key])
        print('  %-16s 제거=%.3f / 유지=%.3f  (차이 %+.3f)' % (name, r, k, r - k))
    print('-' * 72)

    # 2) 이산 특징값 분포(제거 vs 유지)
    feats = comp['features']
    print('[이산 특징 평균] (제거 / 유지)')
    for name, key in [('최장연속길이', 'max_consecutive'), ('홀수개수', 'odd_count'),
                      ('동일끝자리 최대', 'max_same_last_digit'), ('구간최대점유', 'max_section_occupancy')]:
        r = float(feats[key][s_removed].mean()); k = float(feats[key][s_kept].mean())
        print('  %-14s 제거=%.2f / 유지=%.2f' % (name, r, k))

    # 연속 특징(샘플)
    F = ExtremenessScorer._continuous_features(combos[idx])  # CONTINUOUS_FEATURES 순서
    cnames = ExtremenessScorer.CONTINUOUS_FEATURES
    print('[연속 특징 평균] (제거 / 유지)')
    for i, nm in enumerate(cnames):
        r = float(F[s_removed, i].mean()); k = float(F[s_kept, i].mean())
        print('  %-20s 제거=%.2f / 유지=%.2f' % (nm, r, k))
    print('-' * 72)

    # 3) 가장자리 번호 과잉 제거 점검 (1, 45, 둘다)
    base_rate = float(removed.mean())
    has1 = (combos == 1).any(axis=1)
    has45 = (combos == 45).any(axis=1)
    has_both = has1 & has45
    has_edge = ((combos <= 3) | (combos >= 43)).any(axis=1)
    print('[가장자리 과잉제거 점검] 전체 제거율 = %.1f%%' % (100 * base_rate))
    print('  번호 1 포함 조합의 제거율  = %.1f%%' % (100 * float(removed[has1].mean())))
    print('  번호 45 포함 조합의 제거율 = %.1f%%' % (100 * float(removed[has45].mean())))
    print('  1&45 둘다 포함 제거율      = %.1f%%' % (100 * float(removed[has_both].mean())))
    print('  양끝(1-3 또는 43-45) 포함 제거율 = %.1f%%' % (100 * float(removed[has_edge].mean())))
    mid_only = ~has_edge
    print('  양끝 미포함(중앙만) 제거율 = %.1f%%' % (100 * float(removed[mid_only].mean())))
    print('-' * 72)

    # 4) 역대 당첨번호 보존율(가장자리 포함/미포함)
    rows = [sorted(int(x) for x in t[:6]) for _, t in db.get_numbers_with_bonus()]
    W = np.array(rows, dtype=np.int16)
    wscore = scorer.score(W)
    wkept = wscore <= cutoff
    w_has_edge = ((W <= 3) | (W >= 43)).any(axis=1)
    print('[역대 당첨번호 보존율(풀 포함 비율)]')
    print('  전체 당첨번호 보존율        = %.1f%% (%d/%d)'
          % (100 * float(wkept.mean()), int(wkept.sum()), len(W)))
    if w_has_edge.sum() > 0:
        print('  양끝(1-3/43-45) 포함 당첨 보존 = %.1f%% (%d개 중)'
              % (100 * float(wkept[w_has_edge].mean()), int(w_has_edge.sum())))
    if (~w_has_edge).sum() > 0:
        print('  양끝 미포함 당첨 보존        = %.1f%% (%d개 중)'
              % (100 * float(wkept[~w_has_edge].mean()), int((~w_has_edge).sum())))
    print('-' * 72)

    # 5) 가장 많이 제거된(극단) 조합 예시 + 컷오프 근처
    order = np.argsort(scores)
    print('[가장 극단(=제거 1순위) 조합 5개]')
    for j in order[-5:][::-1]:
        print('  %s  score=%.1f' % (combos[j].tolist(), scores[j]))
    print('[컷오프 바로 위(아슬하게 제거) 5개]')
    near = order[K:K + 5]
    for j in near:
        print('  %s  score=%.2f' % (combos[j].tolist(), scores[j]))
    print('[컷오프 바로 아래(아슬하게 유지) 5개]')
    for j in order[K - 5:K]:
        print('  %s  score=%.2f' % (combos[j].tolist(), scores[j]))
    print('=' * 72)


if __name__ == '__main__':
    main()
