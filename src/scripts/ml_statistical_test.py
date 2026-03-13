"""
ML 모델 랜덤 대비 통계 검정

목적: 각 ML 모델이 순수 랜덤보다 통계적으로 유의미한 성능을 보이는지 검정
- one-sample t-test: H0: mu = 0.8 (랜덤 기대값)
- 랜덤 baseline과의 비교 (two-sample t-test)
- p-value < 0.05인 모델만 유의미

수학적 배경:
- 로또 6/45에서 랜덤 6개 선택 시 당첨번호 일치 기대값 = 6 * 6/45 = 0.8
- 분산 = 6 * (6/45) * (39/45) * (39/44) = ~0.608
- 표준편차 ~= 0.78

사용법:
    python src/scripts/ml_statistical_test.py [--rounds 200] [--quick]
"""

import sys
import os
import json
import argparse
import logging
import random
import warnings
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# TensorFlow 로그 억제
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['ABSL_LOGGING_VERBOSITY'] = '1'
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

import numpy as np
from scipy import stats
from tqdm import tqdm

from src.core.db_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_matches(predicted: List[int], actual: List[int]) -> int:
    """예측번호와 실제 당첨번호의 일치 개수 계산"""
    return len(set(predicted) & set(actual))


def random_prediction() -> List[int]:
    """1~45에서 랜덤 6개 선택"""
    return sorted(random.sample(range(1, 46), 6))


def test_random_baseline(
    all_data: List[Tuple[int, Tuple]],
    test_rounds: List[int],
    n_predictions_per_round: int = 10,
    n_repeat: int = 5
) -> List[float]:
    """랜덤 baseline 테스트

    각 회차마다 랜덤 예측 n_predictions_per_round개 생성,
    가장 좋은 match_count 기록. n_repeat번 반복하여 평균.
    """
    round_dict = {r: tuple(nums[:6]) for r, nums in all_data}
    all_matches = []

    for round_num in test_rounds:
        actual = list(round_dict.get(round_num, ()))
        if not actual:
            continue

        round_best_matches = []
        for _ in range(n_repeat):
            best = 0
            for _ in range(n_predictions_per_round):
                pred = random_prediction()
                m = calculate_matches(pred, actual)
                best = max(best, m)
            round_best_matches.append(best)

        all_matches.append(np.mean(round_best_matches))

    return all_matches


def test_model_predictions(
    model_name: str,
    model_instance: Any,
    all_data: List[Tuple[int, Tuple]],
    test_rounds: List[int],
    winning_numbers_list: List[str],
    n_predictions: int = 10
) -> Optional[List[float]]:
    """특정 ML 모델의 백테스트

    Returns:
        각 회차별 최고 match_count 리스트 또는 None (실패 시)
    """
    round_dict = {r: tuple(nums[:6]) for r, nums in all_data}
    matches_list = []

    for round_num in tqdm(test_rounds, desc=f"{model_name} 테스트", file=sys.stdout):
        actual = list(round_dict.get(round_num, ()))
        if not actual:
            continue

        # 해당 회차 이전 데이터로 예측
        # 회차 인덱스 찾기
        round_idx = None
        for i, (r, _) in enumerate(all_data):
            if r == round_num:
                round_idx = i
                break

        if round_idx is None or round_idx < 50:
            continue

        # 이전 데이터 추출
        previous_data = all_data[:round_idx]
        previous_numbers = [
            ','.join(str(n) for n in sorted(nums[:6]))
            for _, nums in previous_data
        ]

        try:
            predictions = []

            if model_name == 'lstm':
                # LSTM: 최근 50회차 데이터 사용
                recent = previous_numbers[-50:]
                preds = model_instance.predict_next_numbers(recent, n_predictions)
                predictions = [p.get('numbers', []) for p in preds if 'numbers' in p]

            elif model_name == 'ensemble':
                preds = model_instance.predict_next_numbers(previous_numbers, n_predictions)
                predictions = [p.get('numbers', []) for p in preds if 'numbers' in p]

            elif model_name == 'monte_carlo':
                # Monte Carlo는 내부에서 데이터 로드
                preds = model_instance.get_best_combinations(n_combinations=n_predictions)
                predictions = [p.get('numbers', []) for p in preds if 'numbers' in p]

            # 최고 match_count 기록
            if predictions:
                best_match = max(
                    calculate_matches(pred, actual)
                    for pred in predictions
                    if len(pred) == 6
                )
                matches_list.append(best_match)
            else:
                # 예측 생성 실패 시 0 기록
                matches_list.append(0)

        except Exception as e:
            logger.debug(f"{model_name} 회차 {round_num} 예측 실패: {e}")
            matches_list.append(0)

    return matches_list if matches_list else None


def run_statistical_test(
    n_test_rounds: int = 200,
    quick_mode: bool = False
) -> Dict[str, Any]:
    """ML 모델 랜덤 대비 통계 검정 실행"""

    if quick_mode:
        n_test_rounds = min(n_test_rounds, 50)
        logger.info(f"[Quick 모드] 테스트 회차: {n_test_rounds}개")

    # DB 로드
    db = DatabaseManager()
    all_data = db.get_numbers_with_bonus()
    winning_numbers = db.get_all_winning_numbers()

    if not all_data:
        logger.error("당첨번호 데이터 없음")
        return {}

    total_rounds = len(all_data)
    # 테스트할 회차 범위 (최근 n_test_rounds개)
    test_start_idx = max(50, total_rounds - n_test_rounds)  # 최소 50회차 학습 데이터 필요
    test_rounds = [r for r, _ in all_data[test_start_idx:]]

    logger.info(f"전체 데이터: {total_rounds}개, 테스트 회차: {len(test_rounds)}개")
    logger.info(f"테스트 범위: {test_rounds[0]}~{test_rounds[-1]}")

    results = {
        'test_info': {
            'total_data': total_rounds,
            'test_rounds': len(test_rounds),
            'test_range': f"{test_rounds[0]}~{test_rounds[-1]}",
            'quick_mode': quick_mode,
            'timestamp': datetime.now().isoformat(),
            'random_expectation': 0.8,
            'random_std': 0.78
        },
        'models': {}
    }

    # 1. 랜덤 baseline 테스트
    logger.info("랜덤 baseline 테스트 중...")
    random_matches = test_random_baseline(all_data, test_rounds)
    if random_matches:
        avg = np.mean(random_matches)
        std = np.std(random_matches)
        t_stat, p_value = stats.ttest_1samp(random_matches, 0.8)
        results['models']['random_baseline'] = {
            'avg_matches': float(avg),
            'std': float(std),
            'n_rounds': len(random_matches),
            't_stat': float(t_stat),
            'p_value': float(p_value),
            'conclusion': '기준 확인'
        }

    # 2. 각 모델 테스트
    models_to_test = {}

    # LSTM
    try:
        from src.ml.lstm_predictor import LSTMPredictor
        models_to_test['lstm'] = LSTMPredictor(db)
        logger.info("LSTM 모델 로드 성공")
    except Exception as e:
        logger.warning(f"LSTM 모델 로드 실패: {e}")

    # Ensemble
    try:
        from src.ml.ensemble_predictor import EnsemblePredictor
        models_to_test['ensemble'] = EnsemblePredictor(db)
        logger.info("Ensemble 모델 로드 성공")
    except Exception as e:
        logger.warning(f"Ensemble 모델 로드 실패: {e}")

    # Monte Carlo
    try:
        from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
        models_to_test['monte_carlo'] = MonteCarloSimulator(db)
        logger.info("Monte Carlo 모델 로드 성공")
    except Exception as e:
        logger.warning(f"Monte Carlo 모델 로드 실패: {e}")

    # 각 모델 백테스트
    for model_name, model_instance in models_to_test.items():
        logger.info(f"\n--- {model_name} 모델 백테스트 시작 ---")
        try:
            matches = test_model_predictions(
                model_name, model_instance,
                all_data, test_rounds, winning_numbers,
                n_predictions=10
            )

            if matches and len(matches) >= 10:
                avg = np.mean(matches)
                std = np.std(matches)

                # H0: mu = 0.8 (랜덤과 동일)
                t_stat, p_value = stats.ttest_1samp(matches, 0.8)

                # 결론 판정
                if p_value < 0.05 and avg > 0.8:
                    conclusion = "랜덤보다 우수 (유의미)"
                elif p_value < 0.05 and avg < 0.8:
                    conclusion = "랜덤보다 열등 (유의미)"
                else:
                    conclusion = "랜덤과 동일 (유의미하지 않음)"

                # 랜덤 baseline과 two-sample t-test
                if random_matches:
                    t2, p2 = stats.ttest_ind(matches, random_matches)
                else:
                    t2, p2 = None, None

                results['models'][model_name] = {
                    'avg_matches': float(avg),
                    'std': float(std),
                    'n_rounds': len(matches),
                    't_stat': float(t_stat),
                    'p_value': float(p_value),
                    'vs_random_t': float(t2) if t2 is not None else None,
                    'vs_random_p': float(p2) if p2 is not None else None,
                    'conclusion': conclusion,
                    'match_distribution': {
                        str(i): int(np.sum(np.array(matches) == i))
                        for i in range(7)
                    }
                }
                logger.info(f"{model_name}: avg={avg:.3f}, std={std:.3f}, t={t_stat:.3f}, p={p_value:.4f} -> {conclusion}")
            else:
                results['models'][model_name] = {
                    'error': '충분한 테스트 데이터 없음',
                    'n_rounds': len(matches) if matches else 0
                }
        except Exception as e:
            results['models'][model_name] = {
                'error': str(e)
            }
            logger.error(f"{model_name} 백테스트 실패: {e}")

    return results


def print_results(results: Dict[str, Any]):
    """결과를 표 형태로 출력"""
    if not results:
        print("결과 없음")
        return

    test_info = results['test_info']
    models = results['models']

    print("\n" + "=" * 100)
    print("  ML 모델 랜덤 대비 통계 검정 결과")
    print("=" * 100)
    print(f"  테스트 범위: {test_info['test_range']}")
    print(f"  테스트 회차: {test_info['test_rounds']}개")
    print(f"  랜덤 기대값: E[X] = {test_info['random_expectation']} (6*6/45)")
    print(f"  Quick 모드: {'예' if test_info['quick_mode'] else '아니오'}")
    print("-" * 100)

    # 결과 테이블
    header = f"  {'모델':<18} | {'테스트':>6} | {'avg_matches':>11} | {'std':>6} | {'t-stat':>8} | {'p-value':>8} | {'결론'}"
    print(header)
    print("-" * 100)

    # 이론적 랜덤 기대값
    print(f"  {'이론 (랜덤)':<18} | {'(이론)':>6} | {'0.800':>11} | {'0.78':>6} | {'-':>8} | {'-':>8} | 기준")

    for model_name, data in models.items():
        if 'error' in data:
            print(f"  {model_name:<18} | {'-':>6} | {'-':>11} | {'-':>6} | {'-':>8} | {'-':>8} | 오류: {data['error'][:30]}")
            continue

        avg = data.get('avg_matches', 0)
        std = data.get('std', 0)
        n = data.get('n_rounds', 0)
        t = data.get('t_stat', 0)
        p = data.get('p_value', 1)
        conclusion = data.get('conclusion', '')

        # p-value 표시 (유의미한 경우 강조)
        p_str = f"{p:.4f}" if p >= 0.001 else f"{p:.2e}"

        print(f"  {model_name:<18} | {n:>6} | {avg:>11.3f} | {std:>6.3f} | {t:>8.3f} | {p_str:>8} | {conclusion}")

    print("=" * 100)

    # 해석 가이드
    print("\n  [해석 가이드]")
    print("  - p-value < 0.05: 통계적으로 유의미 (랜덤과 다름)")
    print("  - p-value >= 0.05: 랜덤과 차이 없음")
    print("  - avg_matches ~= 0.8: 순수 랜덤 수준")
    print("  - 로또는 독립 사건: 과거 데이터로 미래 예측은 이론적으로 불가능")

    # 각 모델 match 분포
    print("\n  [모델별 Match 분포]")
    for model_name, data in models.items():
        if 'match_distribution' in data:
            dist = data['match_distribution']
            total = sum(int(v) for v in dist.values())
            if total > 0:
                print(f"\n  {model_name}:")
                for i in range(7):
                    count = int(dist.get(str(i), 0))
                    pct = count / total * 100
                    bar = '#' * int(pct / 2)
                    print(f"    {i}개 일치: {count:>4} ({pct:>5.1f}%) {bar}")

    print("\n" + "=" * 100)


def save_results(results: Dict[str, Any]):
    """결과를 JSON 파일로 저장"""
    results_dir = os.path.join(project_root, 'results')
    os.makedirs(results_dir, exist_ok=True)

    output_path = os.path.join(results_dir, 'ml_statistical_test_report.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"결과 저장: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='ML 모델 랜덤 대비 통계 검정')
    parser.add_argument('--rounds', type=int, default=200, help='테스트 회차 수 (기본 200)')
    parser.add_argument('--quick', action='store_true', help='Quick 모드 (50회차만)')
    args = parser.parse_args()

    logger.info("ML 통계 검정 시작...")

    results = run_statistical_test(
        n_test_rounds=args.rounds,
        quick_mode=args.quick
    )

    if results:
        print_results(results)
        save_results(results)
    else:
        logger.error("검정 실패")


if __name__ == '__main__':
    main()
