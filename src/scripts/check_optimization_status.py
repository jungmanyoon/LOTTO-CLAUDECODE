#!/usr/bin/env python3
"""
최적화 스터디 상태 확인 및 관리 스크립트
"""
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.core.threshold_optimizer import ThresholdOptimizer
import argparse

def main():
    parser = argparse.ArgumentParser(description='최적화 스터디 상태 확인 및 관리')
    parser.add_argument('--reset', action='store_true', help='스터디 초기화 (새로 시작)')
    parser.add_argument('--study-name', default='lotto_threshold_v4', help='스터디 이름')

    args = parser.parse_args()

    # [2026-06-13 오도 방지 경고] 이 스크립트가 보는 것은 '옛 threshold 최적화 스터디'다.
    # 현재 실제로 도는 활성 최적화기는 PoolOptimizer(study=pool_optimization_v6,
    # data/pool_optimization.db, 극단성 풀 마할라 가중치 탐색)이며, 이 스크립트의 --reset는
    # 그 활성 스터디를 건드리지 않는다(옛/정지된 threshold 스터디 전용). 게다가 활성 풀
    # 스터디는 '누적 유지가 정상'이라 리셋이 필요 없다. 혼동 방지를 위해 명시한다.
    print("[주의] 활성 최적화 = PoolOptimizer(study=pool_optimization_v6 @ data/pool_optimization.db).")
    print("       아래 상태/--reset는 '옛 threshold 스터디'(2025-03 정지, 최종예측 미사용) 전용입니다.")
    print("       극단성 풀 최적화(실제 레버)는 누적 유지가 정상이며 리셋 불필요.")
    print()

    # ThresholdOptimizer 인스턴스 생성
    optimizer = ThresholdOptimizer()

    if args.reset:
        # 스터디 초기화
        print(f"스터디 '{args.study_name}' 초기화 중...")
        result = optimizer.reset_study(args.study_name)
        if result:
            print("[O] 초기화 완료! 다음 실행부터 0회부터 새로 시작합니다.")
        else:
            print("[X] 초기화 실패 (이미 없을 수 있음)")
    else:
        # 스터디 정보 조회
        print(f"\n=== 최적화 스터디 상태 ===")
        print(f"스터디 이름: {args.study_name}")
        print()

        info = optimizer.get_study_info(args.study_name)

        if info.get('n_trials', 0) == 0:
            print("상태: 아직 최적화를 실행하지 않았습니다.")
            print()
            print("최초 실행 시:")
            print("  - 기존 시도: 0회")
            print("  - 추가 시도: 설정된 n_trials (기본 25회)")
            print("  - 총 목표: 25회")
        else:
            print(f"총 시도: {info['n_trials']}회")
            print(f"  - 완료: {info.get('trials_complete', 0)}회")
            print(f"  - 실패: {info.get('trials_failed', 0)}회")
            print(f"  - 중단: {info.get('trials_pruned', 0)}회")
            print()

            if info.get('best_value'):
                print(f"최적 점수: {info['best_value']:.3f}")
                print()
                print("최적 파라미터:")
                for key, value in info.get('best_params', {}).items():
                    print(f"  - {key}: {value}")

            print()
            print("다음 실행 시:")
            print(f"  - 기존 시도: {info['n_trials']}회")
            print(f"  - 추가 시도: 설정된 n_trials (기본 25회)")
            print(f"  - 총 목표: {info['n_trials'] + 25}회")

        print()
        print("사용법:")
        print("  - 상태 확인: python src/scripts/check_optimization_status.py")
        print("  - 초기화: python src/scripts/check_optimization_status.py --reset")
        print()

if __name__ == "__main__":
    main()
