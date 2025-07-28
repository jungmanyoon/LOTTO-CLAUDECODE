# 로또 예측 프로그램 설치 가이드

## 필수 패키지 설치

### 기본 패키지
```bash
pip install numpy pandas matplotlib seaborn
pip install scikit-learn xgboost
pip install tensorflow keras
```

### 추가 패키지 (고급 기능)

#### 1. PyWavelets (프랙탈 분석용)
```bash
pip install PyWavelets
```

PyWavelets는 프랙탈 패턴 분석 기능을 위해 필요합니다. 설치하지 않아도 기본 기능은 정상 작동하지만, 프랙탈 분석 기능은 사용할 수 없습니다.

#### 2. 전체 패키지 한 번에 설치
```bash
pip install -r requirements.txt
```

## requirements.txt 내용
```
numpy>=1.20.0
pandas>=1.3.0
matplotlib>=3.4.0
seaborn>=0.11.0
scikit-learn>=1.0.0
xgboost>=1.5.0
tensorflow>=2.8.0
keras>=2.8.0
PyWavelets>=1.1.0
```

## 선택적 설치

ML/AI 기능을 사용하지 않을 경우:
```bash
# 기본 필터링 기능만 사용
pip install numpy pandas
```

## 문제 해결

### 1. TensorFlow 설치 오류
- Python 3.7-3.10 버전 권장
- 64비트 Python 필요

### 2. XGBoost 설치 오류
Windows의 경우:
```bash
pip install xgboost --no-binary xgboost
```

### 3. PyWavelets 설치 오류
C++ 컴파일러가 필요할 수 있습니다:
- Windows: Visual Studio Build Tools 설치
- Linux: `sudo apt-get install build-essential`
- macOS: Xcode Command Line Tools 설치

## 실행 방법

### 기본 실행
```bash
python main.py
```

### ML/AI 기능 비활성화
```bash
python main.py --skip-ml
```

### 특정 ML 기능만 사용
```bash
# LSTM만 사용
python main.py --no-ensemble --no-monte-carlo --no-bayesian --no-fractal

# 프랙탈 분석 제외
python main.py --no-fractal
```

## 권장 사양

- CPU: 4코어 이상
- RAM: 8GB 이상 (ML 기능 사용시 16GB 권장)
- 저장공간: 2GB 이상
- Python: 3.7-3.10