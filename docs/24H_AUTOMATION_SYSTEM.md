# 24시간 자동 실행 시스템 가이드

## 🚀 개요

`main.py` 단일 파일로 24시간 자동 운영이 가능한 통합 자동화 시스템입니다.
설정 변경 감지, 새 회차 처리, 자동 재필터링 등 모든 작업을 자동으로 수행합니다.

## 📋 주요 기능

### 1. 자동 설정 변경 감지
- `global_probability_threshold` 변경 시 자동 재필터링
- 필터 설정 변경 시 즉시 반영
- 30초마다 설정 파일 모니터링

### 2. 새 회차 자동 처리
- 매시 정각 새 회차 확인
- 자동 데이터 수집 및 저장
- 새 데이터로 자동 재필터링

### 3. 스케줄 기반 작업
- **매시 정각**: 새 회차 확인
- **매일 오전 9시**: 일일 예측 생성
- **매주 일요일 오전 3시**: 시스템 최적화
- **30분마다**: 시스템 상태 체크
- **매일 자정**: 로그 파일 정리

### 4. 자동 복구 시스템
- 오류 발생 시 자동 재시도
- 캐시 자동 정리
- 데이터베이스 재연결

## 🛠️ 시스템 구성

### 핵심 컴포넌트

#### 1. ConfigWatcher
```python
src/automation/config_watcher.py
```
- 설정 파일 변경 실시간 감지
- MD5 해시 기반 변경 추적
- 콜백 기반 이벤트 처리

#### 2. AutoScheduler  
```python
src/automation/auto_scheduler.py
```
- schedule 라이브러리 기반 작업 스케줄링
- 새 회차 감지 및 데이터 수집
- 정기 작업 자동 실행

#### 3. AutomationCoordinator
```python
src/automation/automation_coordinator.py
```
- 모든 자동화 컴포넌트 통합 관리
- 재필터링 트리거 (30분 쿨다운)
- 시스템 상태 모니터링

## 📦 설치 및 실행

### 1. 필수 패키지 설치
```bash
pip install schedule psutil
```

### 2. 24시간 자동 실행 (main.py만 사용)
```bash
# 24시간 자동 실행 모드 시작
python main.py --24h

# 테스트 모드 (5분 후 자동 종료)
python main.py --automation-test
```

### 3. 자동화 관련 옵션
```bash
# 데이터 수집만 수행 (자동화 시스템에서 사용)
python main.py --fetch-only

# 예측만 수행 (필터링 건너뛰기, 자동화 시스템에서 사용)
python main.py --predict-only

# 전체 재필터링 강제 실행
python main.py --full-filter --skip-fetch

# 일반 실행 (자동화 없이)
python main.py
```

## 🔄 자동화 워크플로우

### 설정 변경 시
```
1. ConfigWatcher가 설정 파일 변경 감지 (30초마다)
2. 변경 유형 분석 (threshold, filter, criteria)
3. AutomationCoordinator에 콜백 전달
4. 30분 쿨다운 확인
5. main.py --full-filter --skip-fetch 실행
6. 예측 재생성
```

### 새 회차 감지 시
```
1. AutoScheduler가 매시 정각 확인
2. 동행복권 API 조회
3. 새 회차 발견 시 데이터 수집
4. main.py --fetch-only 실행
5. 재필터링 트리거
6. 새 예측 생성
```

## 📊 모니터링

### 상태 확인
시스템은 10분마다 자동으로 상태를 출력합니다:

```
============================================================
📊 시스템 상태 보고서
⏰ 현재 시각: 2025-09-02 20:30:00
⏱️ 가동 시간: 2시간 15분
🔄 전체 상태: running
📁 설정 감시: 실행중=True, 변경감지=3회
⏰ 스케줄러: 실행중=True, 작업=5개, 실행=12회
💾 캐시: 히트율=85.3%, 메모리=125.4MB
📝 최근 활동:
  - threshold 변경: 2.0 → 1.5
  - 재필터링 완료 (소요: 4.2분)
  - 예측 생성 완료
============================================================
```

### 로그 파일
```
logs/
├── automation_20250902.log  # 자동화 시스템 로그
├── lotto_app.log            # 메인 프로그램 로그
└── filtering/               # 필터링 성능 로그
```

## ⚠️ 주의사항

### 1. 단일 실행 파일
- **모든 기능은 `main.py` 하나로 통합됨**
- 별도의 실행 파일 없이 main.py만 사용
- 24시간 모드와 일반 모드 모두 지원

### 2. 재필터링 쿨다운
- 최소 30분 간격으로만 재필터링 실행
- 연속된 설정 변경 시 마지막 변경만 처리

### 3. 메모리 관리
- 재필터링 시 약 2-4GB 메모리 사용
- 시스템 메모리 70% 초과 시 자동 대기

### 4. 데이터베이스 동시성
- 여러 프로세스 동시 접근 방지
- 트랜잭션 기반 안전한 업데이트

## 🔧 트러블슈팅

### 1. 24시간 모드가 시작되지 않음
```bash
# --24h 옵션 확인
python main.py --24h

# 테스트 모드로 확인
python main.py --automation-test
```

### 2. 재필터링이 실행되지 않음
- 30분 쿨다운 확인
- logs/lotto_app.log 확인
- subprocess 권한 확인

### 3. 메모리 부족
```yaml
# config.yaml에서 조정
filtering:
  batch_size: 5000  # 기본: 10000
  max_workers: 7    # 기본: 14
```

## 📈 성능 최적화

### 1. 증분 모드 활용
- 기본적으로 증분 모드로 실행 (30초-1분)
- 전체 모드는 필요시만 (3-5분)

### 2. 병렬 처리
```bash
python main.py --parallel --workers 14
```

### 3. 캐시 활용
- 7일간 ML 모델 캐시
- 필터 결과 캐시

## 🔄 시스템 업데이트

### 새 필터 추가 시
1. 필터 파일 추가
2. FilterManager 자동 인식
3. 자동화 시스템이 자동으로 적용

### 스케줄 변경
```python
# src/automation/auto_scheduler.py
schedule.every().day.at("09:00").do(self._run_daily_prediction)
# 원하는 시간으로 변경
```

## 📝 설정 예시

### adaptive_filter_config.yaml
```yaml
# 자동 재필터링 트리거 값
global_probability_threshold: 2.0  # 변경 시 자동 재필터링

# 필터 활성화 (변경 시 자동 적용)
filters:
  sum_range: true
  odd_even: true
  consecutive: true
  # ...
```

## 🎯 핵심 장점

1. **완전 자동화**: 사람의 개입 없이 24시간 운영
2. **실시간 반응**: 설정 변경 즉시 반영
3. **자가 복구**: 오류 발생 시 자동 복구
4. **효율적 운영**: 증분 업데이트로 리소스 절약
5. **투명한 운영**: 상세한 로깅과 상태 보고

## 📞 문제 발생 시

1. 로그 확인: `logs/automation_*.log`
2. 상태 확인: 10분마다 출력되는 상태 보고서
3. 테스트 실행: `python test_automation_system.py`
4. 수동 실행: `python main.py` (자동화 없이)