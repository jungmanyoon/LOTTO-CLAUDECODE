# -*- coding: utf-8 -*-
"""
통합 상태 초기화 도구 (2026-06-13 신설) - "코드/전략 변경, 새 회차, 학습, 백테스트" 4트리거별로
'무엇을 무효화/재계산해야 하는가'를 한 곳에서 처리한다.

배경(상태 무효화 감사 2026-06-13): 이 시스템은 '새 회차'는 캐시 키(train_until)로 잘 무효화하지만
'코드/전략 변경'을 감지하는 메커니즘이 거의 없었다(on_code_change=missing). 코드를 바꿔도 회차가
같으면 옛 캐시/모델을 재사용 -> 사용자가 우려한 '뒤죽박죽'. 이 스크립트로 코드변경 시 안전하게
관련 캐시만 선별 무효화한다.

설계 원칙:
  - 안전: DB는 삭제하지 않고 data/_archive/ 로 이동(되돌리기 가능). 재생성 가능한 캐시(npz/모델)만 삭제.
  - 정직: 무엇을 건드리고 무엇을 '의도적으로 안 건드리는지'(예: Optuna 누적 스터디=의미 일관이라 유지)
    를 명확히 출력한다.
  - 기본 dry-run: 실제 실행은 --execute 필요(실수 방지).

사용:
  python src/scripts/reset_state.py --on code-change            # 무엇이 지워질지 미리보기(dry-run)
  python src/scripts/reset_state.py --on code-change --execute  # 실제 실행
  python src/scripts/reset_state.py --on all --execute
  트리거: code-change | new-round | training | backtest | all

ASCII 출력, UTF-8, 이모지 금지.
"""
import os
import sys
import glob
import shutil
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _human(n):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _size_of(paths):
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            for dp, _dn, fn in os.walk(p):
                for f in fn:
                    try:
                        total += os.path.getsize(os.path.join(dp, f))
                    except OSError:
                        pass
    return total


def _glob(*patterns):
    out = []
    for pat in patterns:
        out.extend(glob.glob(os.path.join(ROOT, pat)))
    return [p for p in out if os.path.exists(p)]


def plan_for(trigger):
    """트리거별 (삭제 대상 경로 리스트, 아카이브 대상 경로 리스트, 안내문) 반환."""
    delete, archive, notes = [], [], []

    if trigger in ('code-change', 'all'):
        # 극단성 풀 npz 캐시: 스코어러 로직(extremeness_scorer.py / tail_*)을 고치면 옛 풀이 재사용될
        # 수 있어 강제 무효화(재생성 가능, ~15s). (캐시키 mtime 보강으로 대부분 자동이나, 확실히 비움)
        delete += _glob('cache/extremeness_pool_*.npz')
        # ML 모델 캐시: 모델 구조/특징 코드 변경 시 옛 모델 재사용 방지(회차스탬프만으론 코드변경 미감지).
        delete += _glob('cache/models')
        notes.append("코드변경: 극단풀 npz + ML 모델캐시 무효화(재생성됨). 다음 main.py 실행에 새 코드로 재계산.")
        notes.append("[의도적 미변경] Optuna 풀 스터디(pool_optimization_v6)는 목적함수/탐색공간이 그대로면")
        notes.append("  '의미 일관'이라 누적 유지가 옳다. 목적함수 자체를 바꿨다면 pool_optimizer.py의")
        notes.append("  study_name을 v7로 올려라(옛 trial이 sampler를 오염시키지 않도록).")
        notes.append("[참고] target_K 정책(extremeness_pool_policy.json)은 회차 기반 재탐색이라, 선택")
        notes.append("  로직 코드를 바꿨고 회차가 그대로면 자동 재탐색되지 않는다. 강제하려면 --on new-round")
        notes.append("  병행 또는 정책 파일 round를 낮춰 재탐색을 유도.")

    if trigger in ('training', 'all'):
        delete += _glob('cache/models')
        notes.append("학습: ML 모델 캐시 무효화 -> 다음 실행에 재학습.")

    if trigger in ('backtest', 'all'):
        # 백테스트 상태/캐시: 코드/전략 변경 후 옛 백테스트 결과 재사용 방지.
        delete += _glob('backtest_state.json', 'data/backtest_state.json', 'cache/backtest_*')
        notes.append("백테스트: backtest_state.json 무효화 -> 새 전략으로 재백테스트.")

    if trigger in ('new-round', 'all'):
        notes.append("새 회차: 대부분 자동(캐시 키에 train_until/회차 포함). 별도 삭제 불필요.")
        notes.append("  main.py 실행 시 SystemStateManager가 새 회차를 감지해 패턴/필터/풀/ML을 재계산한다.")
        notes.append("  (수동 강제: python main.py 로 한 사이클 실행)")

    # 중복 제거
    delete = sorted(set(delete))
    archive = sorted(set(archive))
    return delete, archive, notes


def main():
    ap = argparse.ArgumentParser(description='통합 상태 초기화(코드변경/새회차/학습/백테스트 트리거별 무효화)')
    ap.add_argument('--on', required=True,
                    choices=['code-change', 'new-round', 'training', 'backtest', 'all'],
                    help='무효화 트리거')
    ap.add_argument('--execute', action='store_true', help='실제 실행(미지정 시 dry-run 미리보기)')
    args = ap.parse_args()

    delete, archive, notes = plan_for(args.on)
    mode = 'EXECUTE' if args.execute else 'DRY-RUN(미리보기)'

    print("=" * 72)
    print(f"[상태 초기화] 트리거={args.on} | 모드={mode}")
    print("=" * 72)
    for n in notes:
        print("  - " + n)
    print("-" * 72)

    del_size = _size_of(delete)
    print(f"[삭제 대상] {len(delete)}개 ({_human(del_size)}) - 재생성 가능")
    for p in delete[:30]:
        print("   X " + os.path.relpath(p, ROOT))
    if len(delete) > 30:
        print(f"   ... 외 {len(delete) - 30}개")
    if archive:
        print(f"[아카이브 대상] {len(archive)}개 -> data/_archive/ (되돌리기 가능)")
        for p in archive:
            print("   > " + os.path.relpath(p, ROOT))

    if not args.execute:
        print("-" * 72)
        print("미리보기입니다. 실제로 지우려면 --execute 를 붙여 다시 실행하세요.")
        return

    # 실제 실행
    print("-" * 72)
    arch_dir = os.path.join(ROOT, 'data', '_archive')
    os.makedirs(arch_dir, exist_ok=True)
    done_del = 0
    for p in delete:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            done_del += 1
        except OSError as e:
            print(f"   [경고] 삭제 실패 {os.path.relpath(p, ROOT)}: {e}")
    for p in archive:
        try:
            shutil.move(p, os.path.join(arch_dir, os.path.basename(p)))
        except OSError as e:
            print(f"   [경고] 아카이브 실패 {os.path.relpath(p, ROOT)}: {e}")
    print(f"[완료] 삭제 {done_del}개({_human(del_size)} 회수), 아카이브 {len(archive)}개.")
    print("다음 'python main.py' 실행 시 무효화된 항목이 새 코드/회차 기준으로 재생성됩니다.")


if __name__ == '__main__':
    main()
