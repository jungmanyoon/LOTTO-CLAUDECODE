# Render.com 무료 플랜 분석 및 로또 예측 시스템 배포 가이드

## 📊 Render.com 무료 플랜 분석 결과

### 1. 무료 플랜 제한사항 ⚠️

#### 1.1 Web Services (무료 플랜)
- **자동 슬립 모드**: 15분간 활동이 없으면 자동으로 슬립 (24/7 운영 불가능)
- **월 750시간 제한**: 한 달 24/7 운영시 720시간 필요 (겨우 가능)
- **RAM 제한**: 512MB
- **CPU 제한**: 0.1 CPU
- **대역폭 제한**: 100GB/월
- **빌드 시간**: 월 400분 제한

#### 1.2 Background Workers
- **무료 플랜에서 사용 불가** ❌
- 최소 $7/월부터 시작 (Starter 플랜)

#### 1.3 Cron Jobs
- **무료 플랜에서 사용 불가** ❌
- 최소 $7/월부터 시작 (Starter 플랜)

#### 1.4 PostgreSQL Database
- **무료 플랜**: 1GB 스토리지
- **30일 후 자동 삭제** (활동이 없을 경우)
- **연결 제한**: 97개

### 2. MCP (Model Context Protocol) 지원 여부

**결론: Render.com은 MCP를 직접 지원하지 않음** ❌

- Render.com은 표준 웹 서비스, 백그라운드 워커, 크론 작업을 제공
- MCP는 Anthropic의 프로토콜로 별도 구현 필요
- API 엔드포인트를 통한 간접 통합은 가능

## 💰 필요한 비용 계산

### 24/7 자동화를 위한 최소 비용
```
- Web Service (Standard): $25/월 (슬립 모드 없음)
- Background Worker: $7/월 (데이터 수집)
- Cron Jobs: $7/월 (주기적 작업)
- Database (Starter): $7/월 (영구 보관)
----------------------------------------
총 최소 비용: $46/월 (약 60,000원)
```

## 🚫 무료 플랜으로 24/7 운영이 불가능한 이유

1. **15분 슬립 모드**: 지속적인 데이터 수집 불가능
2. **Background Workers 없음**: 백그라운드 처리 불가능
3. **Cron Jobs 없음**: 예약 작업 실행 불가능
4. **데이터베이스 30일 삭제**: 장기 데이터 보관 불가능

## 🎯 권장 솔루션

### 옵션 1: 하이브리드 아키텍처 (추천) ⭐
```yaml
구성:
  - GitHub Actions: 데이터 수집 (무료, 매일 실행)
  - Render.com 무료: 웹 대시보드 (필요시만 활성화)
  - GitHub Repository: 데이터 저장 (무료)
  - Local Machine: ML 모델 학습 (주 1회)

장점:
  - 완전 무료 운영 가능
  - 데이터 영구 보관
  - 유연한 스케줄링

단점:
  - 실시간 처리 불가
  - 로컬 머신 의존성
```

### 옵션 2: 최소 비용 운영
```yaml
구성:
  - Render Cron Job ($7/월): 데이터 수집 (매일)
  - Render Web Service (무료): 대시보드
  - External Database: Supabase 무료 플랜
  
월 비용: $7 (약 9,000원)
```

### 옵션 3: 완전 자동화
```yaml
구성:
  - Render Standard Web Service: $25/월
  - Render Background Worker: $7/월
  - Render Cron Jobs: $7/월
  - Render PostgreSQL Starter: $7/월
  
월 비용: $46 (약 60,000원)
```

## 📝 무료 플랜 배포 가이드 (테스트용)

### 1. 프로젝트 준비
```bash
# requirements.txt 최적화
echo "Flask==2.3.0
gunicorn==21.2.0
requests==2.31.0
beautifulsoup4==4.12.2
pandas==2.0.3
numpy==1.24.3" > requirements.txt

# 경량화된 웹 서버 생성
cat > app.py << 'EOF'
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "message": "로또 예측 시스템 (테스트 모드)"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
EOF
```

### 2. render.yaml 설정
```yaml
services:
  - type: web
    name: lotto-prediction
    runtime: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "gunicorn app:app"
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
    
    # 무료 플랜 설정
    plan: free
    
    # 헬스체크 설정 (슬립 지연)
    healthCheckPath: /health
    
  # 무료 플랜에서는 아래 서비스 사용 불가
  # - type: worker  # 유료
  # - type: cron    # 유료
```

### 3. GitHub Actions 통합 (무료 자동화)
```yaml
# .github/workflows/daily-collection.yml
name: Daily Lottery Data Collection

on:
  schedule:
    - cron: '0 13 * * 6'  # 매주 토요일 오후 10시 (KST)
  workflow_dispatch:  # 수동 실행 가능

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4 pandas
      
      - name: Collect lottery data
        run: |
          python src/data_collector.py
      
      - name: Commit and push
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add data/
          git commit -m "Update lottery data $(date +'%Y-%m-%d')"
          git push
```

## 🔧 최적화 전략

### 1. 데이터 수집 최적화
```python
# 주 1회만 실행 (토요일 밤)
# GitHub Actions 또는 로컬 스케줄러 사용
import schedule
import time

def weekly_collection():
    # 데이터 수집
    collect_lottery_data()
    # GitHub에 푸시
    push_to_github()
    # Render 웹서비스 웨이크업
    wake_up_render_service()

schedule.every().saturday.at("22:00").do(weekly_collection)
```

### 2. 모델 학습 최적화
```python
# 월 1회 로컬에서 실행
# 학습된 모델을 GitHub LFS에 저장
def monthly_training():
    # 데이터 로드
    data = load_from_github()
    # 모델 학습
    train_models(data)
    # 모델 저장 (GitHub LFS)
    save_to_github_lfs()
```

### 3. 예측 서비스 최적화
```python
# Render 무료 웹서비스
# 요청시에만 활성화
@app.route('/predict')
def predict():
    # 캐시된 모델 로드
    model = load_cached_model()
    # 예측 수행
    predictions = model.predict()
    return jsonify(predictions)
```

## 🌐 대안 플랫폼 비교

| 플랫폼 | 무료 플랜 | 24/7 지원 | 크론 작업 | 비고 |
|--------|-----------|-----------|-----------|------|
| Render.com | 750시간/월 | ❌ | ❌ | 15분 슬립 |
| Railway.app | $5 크레딧 | ❌ | ✅ | 크레딧 소진시 중단 |
| Fly.io | 3개 앱 | ✅ | ❌ | 리소스 제한 |
| Vercel | 무제한 | ❌ | ✅ | Serverless only |
| Netlify | 300분 빌드 | ❌ | ✅ | 정적 사이트 중심 |
| Heroku | 없음 | ❌ | ❌ | 무료 플랜 종료 |

## 📌 결론 및 권장사항

### 무료로 운영하려면:
1. **GitHub Actions + GitHub Pages** 조합 사용
2. 실시간 처리 포기, 주간 배치 처리로 전환
3. 로컬 머신에서 주요 처리 수행

### 안정적인 24/7 운영을 원한다면:
1. **최소 월 $7-15** 예산 확보 (Railway.app 또는 Fly.io)
2. **월 $46** 예산으로 Render.com 완전 자동화
3. **AWS/GCP 프리티어** 1년 활용 후 마이그레이션

### 현실적인 추천:
**GitHub Actions (무료) + Supabase (무료 DB) + Vercel (무료 웹)** 조합으로 완전 무료 운영 가능. 단, 실시간 처리는 제한됨.

## 📞 추가 지원

질문이나 구현 도움이 필요하시면 GitHub Issues에 문의해주세요!