"""
휠링(covering design) vs 1-cover 5장 vs 누적 다양성 hold-out 실측 비교

설계 합의 (2026-06-01, Codex gpt-5.5 + Gemini 3.1-pro + Claude):
  - 사용자 전략: 역사적 극단 패턴 최대 제거(K=1.5M 풀) -> 남은 풀에서 다양성 N장 추천.
    실사용 = 그때그때 돌려 N세트 추천 -> 본인+공유자가 골라 구매(누적).
  - 두 모델 만장일치: "세션 간 누적 다양성"이 휠보다 큰 레버(검증된 1cover의 스케일업).
    휠은 보조 실험(좁은 N개 안에 당첨이 몰린 회차의 "다중 당첨 폭발" 가능성 확인).

세 가지 비교(모두 동일 train/pool/weight, hold-out 최근 H회):
  A. 동일 5장 예산 : 1-cover 5장  vs  상위 8번호 greedy covering 5장
  B. 휠 예산 확대   : 8->6장(8-6-3) / 9->9장(9-6-3) / 10->14장(10-6-3) / 12->22장(12-6-3)
  C. 누적 다양성    : 1cover 5장 / 독립 5장x4=20장(중복허용) / 누적다양성 20장 / 무작위 20장

지표(1차=3+회수, 보조=4+회수/평균 best-match/유니크 커버):
  - 각 전략의 "구매 티켓 집합" 기준, 당첨번호와의 best-match(=한 티켓 최대 일치수).
  - 3+회수 = best-match>=3 인 hold-out 회차 수 (하위 등수=많은 번호 맞추기 목표 정합).
  - "총 3+티켓수" = 누적 모델에서 한 회차에 3+를 맞춘 티켓 개수 합(다중 당첨 폭발 측정).

주의: 풀 1회 채점(train_until=latest-H 고정) 방식은 generate_diverse_predictions --evaluate와
동일(8.14M x H회 재채점은 비현실적). 엄밀 walk-forward 아님을 정직히 명시. 기존 1cover 11.33
결과와 직접 비교 가능.

사용법:
  python src/scripts/evaluate_wheel_vs_cover.py --holdout 100
  python src/scripts/evaluate_wheel_vs_cover.py --holdout 100 --seeds 3 --K 1500000
"""
import os
import sys
import time
import json
import argparse
from itertools import combinations

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np


def best_match(ticket, winning_set):
    return len(set(ticket) & winning_set)


def wheel_index_pattern(n, guarantee, max_combos):
    """1..n 번호로 만든 n-k-g 휠을 0-based 인덱스 패턴으로 반환(번호 독립, 1회 계산 후 재사용).

    주의: WheelingSystem.generate_wheel은 STANDARD_WHEELS 표준패턴이 있으면 max_combinations를
    무시한다(예: 8-6-3=6장 고정). 동일 예산(정확한 장수) 비교를 위해 greedy covering을 직접
    호출해 max_combos로 절단한다(완전커버를 더 일찍 달성하면 그보다 적게 나올 수 있음=정상).
    """
    from src.optimization.wheeling_system import WheelingSystem
    ws = WheelingSystem()
    combos = ws._greedy_covering(list(range(1, n + 1)), guarantee, max_combos)
    return [tuple(x - 1 for x in combo) for combo in combos]


def apply_wheel(top_numbers, index_pattern):
    """상위 번호 배열(길이>=n)에 인덱스 패턴을 적용해 실제 6번호 티켓 리스트 생성."""
    tickets = []
    for idx in index_pattern:
        tickets.append(tuple(sorted(int(top_numbers[i]) for i in idx)))
    return tickets


def round_stats(tickets, winning_set):
    """한 회차의 티켓 집합 통계: 최고 일치수, 3+티켓수, 4+티켓수."""
    matches = [best_match(t, winning_set) for t in tickets]
    bm = max(matches) if matches else 0
    n3 = sum(1 for m in matches if m >= 3)
    n4 = sum(1 for m in matches if m >= 4)
    return bm, n3, n4


class Accum:
    """전략별 hold-out 누적 집계기."""
    def __init__(self, name, n_tickets):
        self.name = name
        self.n_tickets = n_tickets
        self.best = []          # 회차별 best-match
        self.rounds_3plus = 0   # best-match>=3 인 회차 수
        self.rounds_4plus = 0   # best-match>=4 인 회차 수
        self.total_3plus_tickets = 0  # 모든 회차 3+ 티켓 개수 합(다중당첨 폭발)
        self.total_4plus_tickets = 0
        self.uniq_cover = []    # 회차별 티켓 집합 유니크 번호 수

    def add(self, tickets, winning_set):
        bm, n3, n4 = round_stats(tickets, winning_set)
        self.best.append(bm)
        if bm >= 3:
            self.rounds_3plus += 1
        if bm >= 4:
            self.rounds_4plus += 1
        self.total_3plus_tickets += n3
        self.total_4plus_tickets += n4
        uniq = len(set(n for t in tickets for n in t))
        self.uniq_cover.append(uniq)

    def summary(self, total_rounds):
        best = np.array(self.best) if self.best else np.array([0])
        return {
            'name': self.name,
            'tickets_per_round': self.n_tickets,
            'avg_best_match': round(float(best.mean()), 4),
            'rounds_3plus': self.rounds_3plus,
            'rounds_4plus': self.rounds_4plus,
            'rounds_3plus_pct': round(self.rounds_3plus / total_rounds * 100, 1),
            'total_3plus_tickets': self.total_3plus_tickets,
            'total_4plus_tickets': self.total_4plus_tickets,
            'avg_unique_cover': round(float(np.mean(self.uniq_cover)), 1) if self.uniq_cover else 0,
            'best_match_dist': [int(x) for x in np.bincount(best, minlength=7)[:7]],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=1_500_000, help='목표 풀 크기 (기본 1.5M)')
    ap.add_argument('--holdout', type=int, default=100)
    ap.add_argument('--seeds', type=int, default=1, help='회차당 시드 반복수(안정성). 기본 1(=회차번호 시드)')
    ap.add_argument('--candidate-sample', type=int, default=20000)
    ap.add_argument('--spread', type=float, default=0.5)
    ap.add_argument('--weights', type=str, default='configs/extremeness_weights.json')
    ap.add_argument('--out', type=str, default='results/wheel_eval.json')
    args = ap.parse_args()

    from src.core.db_manager import DatabaseManager
    from src.core.extremeness_scorer import ExtremenessScorer, TOTAL_COMBINATIONS
    from src.core.diversity_selector import FrequencyAnalyzer, DiversitySelector

    db = DatabaseManager()
    all_rows = [(r, s) for r, s, _ in db.get_all_numbers()]
    latest_round = max(r for r, _ in all_rows)
    train_until = latest_round - args.holdout
    holdout_rounds = [(r, s) for r, s in all_rows if r > train_until]
    win_train = np.array([sorted(int(x) for x in s.split(','))
                          for r, s in all_rows if r <= train_until], dtype=np.int16)

    print("=" * 96)
    print(f"휠 vs 1cover vs 누적다양성  |  최신 {latest_round}  |  train<= {train_until}  |  "
          f"hold-out {len(holdout_rounds)}회  |  K={args.K:,}")
    print("=" * 96)

    # ---- 극단성 풀 1회 채점 ----
    t0 = time.time()
    wpath = os.path.join(PROJECT_ROOT, args.weights)
    if os.path.exists(wpath):
        with open(wpath, 'r', encoding='utf-8') as f:
            wj = json.load(f)
        bp = wj.get('best_params', {})
        pw = {d: bp.get(f"pw_{d}", 1.0) for d in ExtremenessScorer.PENALTY_DIMS}
        scorer = ExtremenessScorer(db, alpha=bp.get('alpha', 0.5), penalty_weights=pw)
        scorer._feature_scale = np.array(
            [bp.get(f"fw_{f}", 1.0) for f in ExtremenessScorer.CONTINUOUS_FEATURES], dtype=np.float32)
        scorer.fit(win_train)
        S = np.diag(scorer._feature_scale).astype(np.float32)
        scorer.cov_inv = (S @ scorer.cov_inv @ S).astype(np.float32)
        wlabel = f"최적화(AUC={wj.get('metrics', {}).get('auc_separation', 0):.3f})"
    else:
        scorer = ExtremenessScorer(db)
        scorer.fit(win_train)
        wlabel = "균등(기본)"

    combos = ExtremenessScorer.all_combinations()
    scores = scorer.score(combos)
    pool_idx = ExtremenessScorer.select_pool(scores, args.K)
    pool_combos = combos[pool_idx]
    pool_list = [tuple(int(x) for x in row) for row in pool_combos]
    print(f"  채점/풀형성 {time.time()-t0:.1f}s  |  풀 {len(pool_list):,}개 "
          f"({(1-len(pool_list)/TOTAL_COMBINATIONS)*100:.1f}% 제거)  |  가중치 {wlabel}")

    # ---- 번호 가중치 -> 상위 N개 순서 ----
    fa = FrequencyAnalyzer(db)
    weights = fa.compute_weights(until_round=train_until, spread=args.spread)
    order = (np.argsort(-weights) + 1).astype(int)  # 가중치 내림차순 번호(1..45)
    print(f"  상위 12 번호(가중치순): {[int(x) for x in order[:12]]}")

    # ---- 휠 인덱스 패턴(번호 독립, 1회 계산) ----
    # (키, n개 번호, guarantee, 목표 장수, 태그). 실제 장수는 greedy 결과 len(완전커버 조기달성 시 더 적음).
    wheel_specs = [
        ('wheel8_5', 8, 3, 5, '동일예산'),   # A: 동일 5장 예산 비교용
        ('wheel8_6', 8, 3, 6, ''),
        ('wheel9_9', 9, 3, 9, ''),
        ('wheel10_14', 10, 3, 14, ''),
        ('wheel12_22', 12, 3, 22, ''),
    ]
    wheel_patterns = {}   # key -> 인덱스 패턴
    wheel_labels = {}     # key -> 라벨(실제 장수 반영)
    for key, n, g, mx, tag in wheel_specs:
        pat = wheel_index_pattern(n, g, mx)
        wheel_patterns[key] = pat
        L = len(pat)
        wheel_labels[key] = f"상위{n}번호 {L}장 휠(g{g}{',' + tag if tag else ''})"
        print(f"  휠 {key}: n={n}, g={g}, 목표{mx}장 -> 실제 {L}장")

    selector = DiversitySelector(number_weights=weights)
    rng = np.random.RandomState(0)

    # ---- 집계기 ----
    acc = {'cover5': Accum('1cover 5장', 5)}
    for key, n, g, mx, tag in wheel_specs:
        acc[key] = Accum(wheel_labels[key], len(wheel_patterns[key]))
    acc['cum_indep20'] = Accum('독립 5장x4=20장(중복허용)', 20)
    acc['cum_div20'] = Accum('누적다양성 20장', 20)
    acc['rand20'] = Accum('무작위 20장', 20)

    print("-" * 96)
    print(f"  hold-out 평가 시작 (seeds={args.seeds}, candidate_sample={args.candidate_sample}) ...")
    t0 = time.time()
    for ri, (r, s) in enumerate(holdout_rounds, 1):
        wn = set(int(x) for x in s.split(','))

        # --- 1cover 5장 (시드 평균을 위해 첫 시드 사용, 누적은 4시드 활용) ---
        cover5 = selector.select(pool_list, num_tickets=5, quality=-scores[pool_idx],
                                 candidate_sample=args.candidate_sample, seed=r, local_search_iters=50)
        acc['cover5'].add(cover5, wn)

        # --- 휠들(상위 번호 매핑) ---
        topn = order  # 길이 45, 앞에서부터 사용
        for key, n, g, mx, tag in wheel_specs:
            acc[key].add(apply_wheel(topn, wheel_patterns[key]), wn)

        # --- 누적: 독립 5장 x 4 (중복 허용) ---
        indep = []
        for k in range(4):
            indep.extend(selector.select(pool_list, num_tickets=5, quality=-scores[pool_idx],
                                         candidate_sample=args.candidate_sample,
                                         seed=r * 10 + k, local_search_iters=30))
        acc['cum_indep20'].add(indep, wn)

        # --- 누적 다양성 20장 (한 번에 num_tickets=20, 제약이 글로벌 커버 극대화) ---
        div20 = selector.select(pool_list, num_tickets=20, quality=-scores[pool_idx],
                                candidate_sample=args.candidate_sample, seed=r, local_search_iters=60)
        acc['cum_div20'].add(div20, wn)

        # --- 무작위 20장 ---
        ridx = rng.choice(len(pool_list), 20, replace=False)
        acc['rand20'].add([pool_list[i] for i in ridx], wn)

        if ri % 20 == 0:
            print(f"    {ri}/{len(holdout_rounds)} 진행 ({time.time()-t0:.0f}s)")

    print(f"  평가 완료 {time.time()-t0:.0f}s")
    print("=" * 96)

    # ---- 결과 출력 ----
    H = len(holdout_rounds)
    summaries = {k: a.summary(H) for k, a in acc.items()}

    def line(key):
        d = summaries[key]
        return (f"  {d['name']:<28} | {d['tickets_per_round']:>3}장 | "
                f"avg={d['avg_best_match']:.3f} | 3+회차={d['rounds_3plus']:>3}/{H} "
                f"({d['rounds_3plus_pct']:>4.1f}%) | 4+회차={d['rounds_4plus']:>2} | "
                f"3+티켓합={d['total_3plus_tickets']:>3} | 4+티켓합={d['total_4plus_tickets']:>2} | "
                f"유니크={d['avg_unique_cover']:.0f}")

    print("[A] 동일 5장 예산 비교")
    print(line('cover5'))
    print(line('wheel8_5'))
    print("-" * 96)
    print("[B] 휠 예산 확대 (3개 보장)")
    print(line('cover5'))
    print(line('wheel8_6'))
    print(line('wheel9_9'))
    print(line('wheel10_14'))
    print(line('wheel12_22'))
    print("-" * 96)
    print("[C] 누적 다양성 (20장)")
    print(line('cover5'))
    print(line('cum_indep20'))
    print(line('cum_div20'))
    print(line('rand20'))
    print("=" * 96)

    out = {
        'meta': {
            'latest_round': latest_round, 'train_until': train_until,
            'holdout': H, 'K': args.K, 'weights': wlabel,
            'candidate_sample': args.candidate_sample, 'spread': args.spread,
            'top12_numbers': [int(x) for x in order[:12]],
            'note': 'pool 1회 채점(train 고정) 방식; 엄밀 walk-forward 아님',
        },
        'results': summaries,
    }
    outpath = os.path.join(PROJECT_ROOT, args.out)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: {args.out}")


if __name__ == '__main__':
    main()
