# 로또 번호 예측 시스템

ML/AI를 활용한 로또 번호 분석 및 예측 시스템입니다.

## 🎯 주요 기능

### 1. 데이터 수집 및 분석
- 동행복권 공식 사이트에서 최신 당첨번호 자동 수집
- 1182회차까지의 모든 당첨 데이터 분석
- 13가지 패턴 분석 (홀짝, 연속번호, 구간별 분포 등)

### 2. 필터링 시스템 (16종)
- **match_filter**: 이전 당첨번호와 일치 개수
- **odd_even_filter**: 홀짝 비율
- **consecutive_filter**: 연속 번호
- **sum_range_filter**: 합계 범위
- **fixed_step_filter**: 고정 간격
- **last_digit_filter**: 끝자리
- **max_gap_filter**: 최대 간격
- **section_filter**: 구간별 분포
- **average_filter**: 평균값
- **multiple_filter**: 배수 패턴
- **ten_section_filter**: 10구간 분석
- **arithmetic_sequence_filter**: 등차수열
- **geometric_sequence_filter**: 등비수열
- **prime_composite_filter**: 소수/합성수
- **digit_sum_filter**: 자릿수 합
- **dispersion_filter**: 분산도

### 3. ML/AI 예측 모델
- **LSTM**: 시계열 예측 (과거 50회차 데이터 학습)
- **앙상블 모델**: Random Forest + XGBoost + Neural Network
- **Monte Carlo**: 10,000회 시뮬레이션
- **베이지안 추론**: 확률적 예측
- **프랙탈 분석**: 카오스 이론 적용

## 📋 요구사항

```bash
Python 3.8+
TensorFlow 2.x
scikit-learn
xgboost
numpy
pandas
tqdm
psutil
requests
beautifulsoup4
pyyaml
```

## 🚀 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/jungmanyoon/-_CLAUDE-CODE.git
cd -_CLAUDE-CODE
```

2. 의존성 설치
```bash
pip install -r requirements.txt
```

## 💻 사용법

### 기본 실행
```bash
python main.py
```

### 주요 옵션
```bash
# 데이터 수집 건너뛰기
python main.py --skip-fetch

# ML/AI 분석만 수행
python main.py --ml-only

# 병렬 처리 비활성화
python main.py --no-parallel

# 특정 ML 모델만 사용
python main.py --lstm --no-ensemble --no-monte-carlo
```

## 📁 프로젝트 구조

```
├── main.py                 # 메인 실행 파일
├── src/
│   ├── core/              # 핵심 모듈
│   ├── filters/           # 필터 구현
│   ├── ml/                # ML 모델
│   ├── probabilistic/     # 확률 모델
│   └── advanced/          # 고급 분석
├── data/                  # 데이터베이스 파일
├── models/                # 학습된 모델
├── logs/                  # 로그 파일
└── docs/                  # 문서
```

## 🔧 성능 최적화

- **병렬 처리**: ProcessPoolExecutor를 통한 멀티코어 활용
- **배치 처리**: 최적화된 배치 크기로 메모리 효율성 향상
- **조기 종료**: Early Termination 전략으로 불필요한 연산 감소
- **캐싱**: LRU 캐시로 반복 연산 최소화

## 📊 분석 결과 예시

```
홀짝 분포: 3:3 비율이 33.93%로 가장 빈번
연속 번호: 2개 연속이 46.45%로 가장 많음
번호 일치: 1개 일치가 42.31%로 가장 빈번
```

## ⚠️ 주의사항

이 프로그램은 통계적 분석과 패턴 인식을 위한 연구 목적으로 개발되었습니다. 
로또는 확률 게임이며, 이 프로그램이 당첨을 보장하지 않습니다.

## 📝 라이선스

MIT License

## 👥 기여

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

## 📧 문의

Issues 탭을 통해 문의해주세요.