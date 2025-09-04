# 📊 진행률 표시 개선 완료

## 🎯 문제점
- **tqdm 진행률 바가 너무 자주 업데이트되어 로그가 지저분해짐**
- 각 필터마다 개별 진행률 바가 표시되어 화면이 복잡함
- 진행률 바의 잔상이 로그에 남아 읽기 어려움

## ✅ 해결 방법

### 1. **중앙 제어 시스템 구축**
- `src/utils/progress_config.py`: 진행률 표시 설정 중앙 관리
- `src/filters/tqdm_wrapper.py`: tqdm 래퍼로 모든 진행률 표시 제어

### 2. **간단 모드 도입**
- **Simple Mode**: 25%, 50%, 75%, 100% 단위로만 로그 출력
- 진행률 바 대신 깔끔한 텍스트 로그만 표시
- 로그 스팸 대폭 감소

### 3. **config.yaml 설정 추가**
```yaml
# 진행률 표시 설정
progress_display:
  disable_all: false  # true로 설정하면 모든 진행률 바 비활성화
  simple_mode: true   # true로 설정하면 간단한 로그만 표시
```

## 📈 개선 효과

### Before
```
- average 필터 진행률: 100%|███████████| 1/1 [00:00<?] 
- 배수 패턴 필터링 진행률: 100%|██████████| 1/1 [00:00<00:00] 
- ten_section 필터 진행률: 100%|█████████| 1/1 [00:00<?] 
```
(매 필터마다 복잡한 진행률 바)

### After
```
average 필터: 25% 완료
average 필터: 50% 완료  
average 필터: 75% 완료
average 필터: 100% 완료
```
(깔끔한 텍스트 로그)

## ⚙️ 사용법

### 1. 간단 모드 활성화 (기본값)
```yaml
# config.yaml
progress_display:
  simple_mode: true
```

### 2. 진행률 표시 완전 비활성화
```yaml
progress_display:
  disable_all: true
```

### 3. 원래 진행률 바로 복원
```yaml
progress_display:
  simple_mode: false
  disable_all: false
```

## 🔧 추가 설정

### 환경 변수로도 제어 가능
```bash
# 진행률 바 비활성화
export DISABLE_PROGRESS_BARS=true

# 간단 모드 활성화
export PROGRESS_SIMPLE_MODE=true
```

## 💡 장점
1. **로그 가독성 향상**: 불필요한 진행률 바 제거
2. **성능 개선**: 업데이트 빈도 감소로 약간의 성능 향상
3. **유연한 제어**: config.yaml이나 환경 변수로 쉽게 조절
4. **호환성 유지**: 기존 코드 수정 최소화

이제 로그를 확인하기 훨씬 편해졌습니다!