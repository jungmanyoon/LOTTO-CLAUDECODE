# 다음 세션 인계: 로그/코드 정직성 잔여 정리

작성: 2026-06-14 (세션 마무리). 메모리: honesty-audit-and-dead-machinery-removal-2026-06-14

## 0. 지난 세션 결론 (재발견 금지)
- **제품 핵심(극단성 풀 -> 5세트)은 정직·정상 작동**. 문제는 "최종예측에 영향 없는 레거시/보조 계층이
  '자동조정/최적화 완료/최종 검증/미세조정 완료'로 일하는 척"하는 honesty 결함이었다.
- 울트라코드 전수감사 **108건**(MISLEADING/DEAD_THEATER/NO_OP/VALUE_MISMATCH 등). 전체 where+fix:
  `docs/LOG_CODE_HONESTY_AUDIT_2026-06-14.md` (gitignore, 로컬 전용).
- **처리 완료(push됨)**: HIGH 12건 전부 + 주요 MEDIUM + cosmetic 일부.
  커밋: 0226445, 3797be6, 450e6f5(P1), 735ca7b(P2), f718ac1(메모리경합), e799f1c(P3).
  주요 수정: AutoAdjustmentV2 비활성, 30분 피드백루프 no-op 연산제거, fine_tune 거짓로그 정정,
  CMA-ES->TPE, ML"최종검증"->보조신호검증, 신뢰도->전형성, 가짜 CRITICAL->참고, 대시보드 죽은DB->활성DB,
  PoolOptimizer 메모리경합(백그라운드 최적화를 전경 사이클 후 시작).
- **검증**: 전체 828 passed(1 기존 flaky 타이밍벤치) + main.py --once EXIT0 + ERROR 0 + Unable to allocate 0
  + 최종 5세트 정상(겹침0) + 전형성 라벨.
- **운영 주의**: 옛 상주 프로세스(09:48 시작, 옛 코드, 2.8GB)가 메모리경합·좀비 스폰의 주범이었음 -> 정리함.
  상주로 쓰려면 새 코드로 `python main.py` 재시작.

## 1. 남은 작업 (전부 순수 LOW cosmetic, 동작영향 0)
`docs/LOG_CODE_HONESTY_AUDIT_2026-06-14.md`의 미처리 항목(~50건). 죽은/보조 코드의 로그라벨·docstring 태그:
- db_manager.py 인덱스로그 중복 / optimization_db.py 죽은 테이블(optimization_trials/best_parameters) 주석
- specialized_databases.py 카운트 / integrated_filter_manager.py 2단계 확률필터 '0개제거 보장' 태그
- adaptive_probability_filter.py get_filtered_count / filter_validator.py report 레거시 태그
- hyperparameter_tuner.py / feedback_loop_system.py / improved_auto_improvement_manager.py DEAD 태그
- system_state_manager.py / resource_monitor.py / db_connection_manager.py / dashboard.py / performance_dashboard.py
- auto_threshold_optimizer.py(ml_inclusion 미사용) / lstm_predictor.py / extremeness_scorer.py coverage(미사용)
- main.py SystemHealthChecker._check_database_structure/_check_filter_configuration (no-op 정직화)
- backtesting avg_matches 무작위 기준선 병기

### 구조적(동작 변경 - 사용자 결정 필요)
- main.py 비-fast 경로 16필터 7.7M 연산: 레거시 미사용인데 매 사이클 채점(시간 낭비) -> 스킵 검토.
- AutomatedFilterScheduler 등 죽은 클래스/모듈 '삭제'(현재는 DEAD 주석 태그만).
- `.gitignore`에 `cache/` 추가(현재 cache/가 ?? 로 노출).

## 2. 수행 방식 (중요)
- **대규모 병렬 에이전트 워크플로우는 서버 rate limit으로 반복 실패함**(2025 다회 실측).
  -> 잔여는 **직접 순차** 또는 **소규모(<=5) 배치**로. 파일별 1에이전트 30개 동시 = 실패.
- 모든 수정은 **로그/주석/docstring 텍스트만**(로직/제어흐름 불변). 함수·클래스 삭제 금지(태그만),
  단 위 "구조적" 3건은 별도 결정 후.
- 각 수정 후 `python -c "import ast; ast.parse(...)"` 구문검사. 묶음 단위 커밋+push.
- 마무리 검증: `python -m pytest tests/ --no-cov -q` (828 기준, flaky 타이밍벤치 1 무관) +
  `python main.py --once`(ERROR 0 / 5세트 / 겹침0 확인). **실행 전 잔존 main.py 프로세스 정리**(메모리경합 방지).

## 3. 다음 세션 시작 프롬프트(붙여넣기용)
> docs/NEXT_SESSION_HONESTY_CLEANUP_2026-06-14.md 대로 정직성 잔여(LOW cosmetic) 정리 이어서 해줘.
> docs/LOG_CODE_HONESTY_AUDIT_2026-06-14.md의 미처리 항목을 소규모 배치(직접 순차, 대규모 병렬 금지=rate limit)로
> 로그/docstring 텍스트만 정직화하고(로직 불변), 묶음 커밋+push. 마지막에 pytest + main.py --once(프로세스 정리 후)로 검증.
> 구조적 3건(16필터 7.7M 연산 스킵 / 죽은 클래스 삭제 / .gitignore cache/)은 먼저 물어보고 진행.
