# 로또 번호 예측 시스템

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-70%25%2B%20coverage-green.svg)](tests/)

ML/AI를 활용한 로또 번호 분석 및 예측 시스템입니다. 확률 기반 필터링으로 8.14M 조합을 ~300K로 축소하여 패턴 제외를 통해 확률을 27배 개선합니다.

## 🚀 Quick Start

```bash
# 전체 시스템 1회 실행 후 종료 (~4분, F5)
python main.py              # 1사이클(데이터/필터/ML/백테스팅/예측) 수행 후 종료. Dashboard: http://127.0.0.1:5001(daemon)

# 상주 모드 (계속 켜두기)
python main.py --24h        # 새 회차 감지 + 예약 예측 + 무한 백그라운드 최적화 (Ctrl+C로 종료)

# 테스트 실행
python -m pytest tests/     # 70%+ 커버리지

# 캐시/모델 오류 해결
python src/scripts/clear_model_cache.py
```

## 🏗️ 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                    Main Application (main.py)                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Data      │  │   Filter    │  │    ML       │              │
│  │ Collection  │→ │   System    │→ │ Prediction  │→ Dashboard   │
│  │  (Auto)     │  │(16 Filters) │  │  (5 Models) │   (5001)     │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
├─────────────────────────────────────────────────────────────────┤
│           Background: ThresholdOptimizer (Optuna TPE)           │
│           Auto-Learning: SmartAutoLearning (24h cycle)          │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 데이터 흐름**: 데이터 수집 → 필터링 (8.14M→300K) → ML 예측 → 최종 선택 → 대시보드

📖 **상세 아키텍처**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 🎯 주요 기능

### 1. 완전 자동화 시스템
- **자동 데이터 수집**: 동행복권에서 최신 당첨번호 수집 (1186+ 회차)
- **새 회차 자동 감지**: 프로그램 실행 중 새 당첨번호 발표 시 자동 업데이트
- **백그라운드 최적화**: Optuna TPE를 이용한 무한 파라미터 최적화 (140개 조합 사이클)
- **자동 롤백**: 성능 저하 시 자동 복구 (>10% 저하 감지)

### 2. 16종 필터링 시스템

| 카테고리 | 필터 | 설명 |
|---------|------|------|
| **필수** | odd_even, consecutive, sum_range, max_gap | 항상 적용 |
| **완화가능** | average, prime_composite, fixed_step, multiple | ML 예측 시 완화 |
| **분석** | ten_section, digit_sum, dispersion, last_digit | 분포 분석 |
| **수열** | arithmetic_sequence, geometric_sequence | 수열 패턴 |
| **구간** | section, match | 구간/일치 패턴 |

### 3. ML/AI 예측 모델

| 모델 | 방식 | 특징 |
|------|------|------|
| **LSTM** | 시계열 | 50회차 시퀀스 학습 |
| **앙상블** | RF + XGBoost + NN | 3개 모델 결합 |
| **Monte Carlo** | 시뮬레이션 | 6,000회, 8 워커 병렬 |
| **베이지안** | 확률 추론 | 사후 확률 계산 |
| **프랙탈** | 카오스 이론 | 비선형 패턴 분석 |

### 4. 웹 대시보드

- **자동 시작**: main.py 실행 시 포트 5001에서 자동 시작
- **실시간 예측**: 예측 결과 실시간 표시
- **온디맨드 생성**: "새 예측 생성" 버튼으로 언제든 5세트 예측 생성

## 📋 요구사항

- **Python**: 3.8+ (3.11.9 테스트 완료)
- **OS**: Windows (권장), Linux/Mac 지원
- **메모리**: 4GB+ 권장 (8GB+ 최적)
- **저장공간**: ~2.5GB (모델 캐시 1.7GB + 데이터베이스 500MB)
- **포트**: 5001 (Flask 대시보드)

### 핵심 패키지

| 패키지 | 용도 |
|-------|------|
| tensorflow>=2.8.0 | LSTM 모델 |
| scikit-learn>=1.0.0 | 앙상블 모델 |
| xgboost>=1.5.0 | 그래디언트 부스팅 |
| optuna>=3.0.0 | 하이퍼파라미터 최적화 |
| flask>=2.0.0 | 웹 대시보드 |
| pytz | 한국 시간대 (KST) |

## 🚀 설치 방법

```bash
# 1. 저장소 클론
git clone https://github.com/jungmanyoon/-_CLAUDE-CODE.git
cd -_CLAUDE-CODE

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 실행 (모든 기능 자동 시작)
python main.py
```

## 💻 사용법

### 기본 실행

```bash
python main.py          # 1사이클 실행 후 종료(~4분) → Dashboard: http://127.0.0.1:5001 (daemon)
python main.py --24h    # 상주 모드: 계속 켜두고 새 회차 감지/예약 예측/무한 최적화
```

> plain `python main.py`는 한 사이클을 수행한 뒤 **자체 종료**합니다. 대시보드와 백그라운드 최적화는
> daemon 스레드라 프로세스 종료와 함께 멈춥니다. 계속 켜두려면 `--24h`를 사용하세요.

실행 시 자동으로(1사이클):
- ✅ 데이터 수집 및 업데이트
- ✅ 16개 필터 적용
- ✅ 5개 ML 모델 예측
- ✅ 백그라운드 최적화 (Optuna, 사이클 동안 / 상주는 --24h)
- ✅ 웹 대시보드 시작 (daemon)

### 명령행 옵션

| 옵션 | 설명 |
|------|------|
| `--skip-fetch` | 데이터 수집 건너뛰기 |
| `--ml-only` | ML/AI 분석만 수행 |
| `--no-parallel` | 병렬 처리 비활성화 |
| `--lstm` | LSTM 모델만 사용 |
| `--no-ensemble` | 앙상블 모델 제외 |
| `--no-monte-carlo` | Monte Carlo 시뮬레이션 제외 |

### 유틸리티 스크립트

```bash
# 테스트
python -m pytest tests/                    # 전체 테스트
python -m pytest tests/ -k "test_name"     # 특정 테스트
python -m pytest --cov=src tests/          # 커버리지 포함

# 유지보수
python src/scripts/clear_model_cache.py    # 모델 캐시 정리
python src/scripts/auto_cache_cleaner.py   # 자동 캐시 정리

# 모니터링
python src/scripts/check_optimization_status.py  # 최적화 상태 확인
python src/scripts/analyze_filters.py            # 필터 효과 분석
```

## 📁 프로젝트 구조

```
├── main.py                      # 메인 실행 파일 (F5 엔트리포인트)
├── config.yaml                  # 시스템 설정 (워커, 배치 크기)
├── configs/
│   └── adaptive_filter_config.yaml  # 필터 설정 (Single Source of Truth)
├── src/
│   ├── core/                    # 핵심 모듈
│   │   ├── db_manager.py        # 데이터베이스 관리 (Singleton)
│   │   ├── filter_manager.py    # 필터 오케스트레이션
│   │   ├── threshold_manager.py # 임계값 관리 (Singleton, Observer)
│   │   ├── performance_metrics.py # 성능 메트릭 (Single Source)
│   │   └── threshold_optimizer.py # Optuna 최적화
│   ├── filters/                 # 16개 필터 구현
│   │   ├── base_filter.py       # 기본 필터 클래스
│   │   └── *_filter.py          # 개별 필터들
│   ├── ml/                      # ML 모델
│   │   ├── lstm_predictor.py    # LSTM 시계열 예측
│   │   └── ensemble_predictor.py # 앙상블 모델
│   ├── probabilistic/           # 확률 모델
│   │   ├── monte_carlo_simulator.py
│   │   └── bayesian_inference.py
│   ├── advanced/                # 고급 분석
│   │   └── fractal_pattern_analyzer.py
│   ├── scripts/                 # 유틸리티 스크립트
│   │   └── enhanced_dashboard_v2.py  # 웹 대시보드
│   └── utils/                   # 유틸리티
├── tests/                       # 테스트 (70%+ 커버리지)
├── data/                        # 데이터베이스 파일
├── cache/                       # 모델 캐시 (~1.7GB)
├── logs/                        # 로그 파일
└── docs/                        # API 문서 (Sphinx)
```

## 🔧 성능 최적화

| 구성요소 | 설정 | 비고 |
|---------|------|------|
| **FilterManager** | 12 워커 | 75% CPU 활용 |
| **배치 크기** | 60,000 조합 | 31GB 메모리 최적화 |
| **Monte Carlo** | 6,000 시뮬레이션, 8 워커 | 병렬 처리 |
| **캐시 전략** | 7일 TTL, 1.7GB+ | LRU 캐시 |

### 성능 지표

- **초기 실행**: 5-10분 (데이터 수집 + 학습 + 필터링)
- **이후 실행**: 2-3분 (캐시 활용)
- **필터 효율**: ~96.3% 감소 (8.14M → 300K)
- **백테스트 정확도**: 0.8-1.5 평균 일치 (허용 범위: 0.6-2.0)

## 📊 분석 결과 예시

```
필터링 결과: 8,145,060 → 298,423 조합 (96.3% 감소)
홀짝 분포: 3:3 비율이 33.93%로 가장 빈번
연속 번호: 2개 연속이 46.45%로 가장 많음
번호 일치: 1개 일치가 42.31%로 가장 빈번
ML 포함률: ~8.5% (목표: 15% with 완화된 임계값)
```

## 🧪 테스트

```bash
# 전체 테스트 실행
python -m pytest tests/

# 커버리지 포함
python -m pytest --cov=src tests/

# 단위/통합 테스트 분리
python -m pytest -m unit          # 단위 테스트만
python -m pytest -m integration   # 통합 테스트만
```

**테스트 커버리지**: 70%+ (pytest.ini에서 강제)

## 📚 API 문서

Sphinx 기반 API 문서 생성:

```bash
cd docs
sphinx-build -b html . _build/html

# 브라우저에서 열기
start _build/html/index.html  # Windows
open _build/html/index.html   # Mac
```

**API 문서 구조**:
- `docs/api/core.rst` - 핵심 모듈 (DatabaseManager, ThresholdManager 등)
- `docs/api/filters.rst` - 16개 필터 모듈
- `docs/api/ml.rst` - ML 모델 (LSTM, Ensemble 등)

## ⚠️ 주의사항

이 프로그램은 통계적 분석과 패턴 인식을 위한 **연구 목적**으로 개발되었습니다.
로또는 확률 게임이며, 이 프로그램이 당첨을 **보장하지 않습니다**.

## 🔧 문제 해결

### 빠른 해결 가이드

| 증상 | 원인 | 해결 |
|------|------|------|
| StandardScaler 에러 | 캐시 손상 | `python src/scripts/clear_model_cache.py` |
| 메모리 >4GB | 캐시/배치 과대 | `auto_cache_cleaner.py` 실행 |
| 실행 >15분 | 병렬화 문제 | config.yaml에서 max_workers 확인 |
| 필터 포함률 <10% | 임계값 과도 | `global_probability_threshold` 조정 |
| 대시보드 연결 실패 | 포트 5001 사용중 | main.py 재시작 또는 포트 확인 |
| `get_all_rounds()` 에러 | 잘못된 API | `get_all_winning_numbers()` 사용 |

### StandardScaler 에러

```bash
# 손상된 캐시 정리
python src/scripts/clear_model_cache.py

# main.py 재실행
python main.py
```

### 성능 문제

- **첫 실행**: 5-10분 (모델 학습)
- **이후 실행**: 2-3분 (캐시 활용)
- **메모리 부족**: `config.yaml`에서 `batch_size` 감소

### 데이터베이스 잠금

```bash
python src/scripts/kill_db_locks.py
```

## 📖 상세 문서

| 문서 | 설명 |
|------|------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 시스템 아키텍처, 다이어그램, 싱글톤 패턴 |
| [CLAUDE.md](CLAUDE.md) | AI 개발 가이드, API 레퍼런스 |
| [ADAPTIVE_FILTER_GUIDE.md](docs/ADAPTIVE_FILTER_GUIDE.md) | 적응형 필터 설정 가이드 |
| [PERFORMANCE_METRICS_QUICK_REF.md](docs/PERFORMANCE_METRICS_QUICK_REF.md) | 성능 메트릭 퀵 레퍼런스 |

## 🔑 핵심 설정 파일

| 파일 | 용도 |
|------|------|
| `config.yaml` | 시스템 설정 (워커, 배치 크기, 메모리) |
| `configs/adaptive_filter_config.yaml` | **필터 설정 (Single Source of Truth)** |

⚠️ **중요**: 필터 기준값 변경은 반드시 `adaptive_filter_config.yaml`에서 하세요!

## 📝 라이선스

MIT License

## 👥 기여

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

## 📧 문의

Issues 탭을 통해 문의해주세요.

---

**버전**: 1.0.0 | **최종 업데이트**: 2025-12-07