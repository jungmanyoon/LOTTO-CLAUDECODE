# Ralph Loop - 로또 시스템 반복 개선 프롬프트

## 목표
로또 예측 시스템의 모든 에러를 반복적으로 발견하고 수정한다.
새로운 에러가 2회 연속 없고 테스트 통과율 80% 이상이면 완료.

## 매 이터레이션 실행 순서

### STEP 1: 상태 파일 확인
`.claude/ralph_state.json` 읽기 (없으면 초기화)
```json
{"iteration": 0, "consecutive_clean": 0, "errors_fixed": [], "last_errors": []}
```

### STEP 2: 임시 파일 정리
루트에서 삭제: test_*.py, check_*.py, verify_*.py, *_FIX.md, *_SUMMARY.md, *_REPORT.md

### STEP 3: 구문 검증
```bash
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('[OK] main.py')"
python -c "import sys; sys.path.insert(0,'src'); from filters.sum_range_filter import SumRangeFilter; print('[OK] filters')"
```

### STEP 4: pytest 실행
```bash
python -m pytest tests/ -x --timeout=60 -q --tb=short 2>&1 | head -150
```
알려진 무시 이슈: test_auto_scheduler(타임아웃), test_backtesting_fix(_check_prediction 반환), test_filter_pass_rate(0.0)

### STEP 5: 로그 분석
```bash
findstr /I "ERROR CRITICAL" logs/lotto_app.log 2>/dev/null | tail -30
```

### STEP 6: 에러 수정
각 새 에러를 하나씩 Read→분석→Edit으로 수정. 수정 후 개별 테스트 재실행.

### STEP 7: 종료 판정
- 새 에러 0건: consecutive_clean += 1
- consecutive_clean >= 2 AND 통과율 >= 80%: `<promise>IMPROVEMENT COMPLETE</promise>` 출력

## 완료 신호
반드시 이 태그를 출력해야 루프 종료:
`<promise>IMPROVEMENT COMPLETE</promise>`
