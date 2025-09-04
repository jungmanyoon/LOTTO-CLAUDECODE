# 📊 예측 번호 저장 및 당첨 결과 추적 시스템

## 🎯 시스템 목적

매주 생성되는 로또 예측 번호를 체계적으로 저장하고, 실제 당첨 결과와 비교하여 시스템의 성능을 추적하는 통합 관리 시스템입니다.

### 주요 기능
1. **예측 저장**: 매주 5세트 예측 번호를 영구 저장
2. **결과 비교**: 실제 당첨번호와 자동 비교
3. **성과 추적**: 당첨 이력 및 통계 관리
4. **리포팅**: 주간/월간 성과 보고서 생성

## 🗄️ 데이터베이스 구조

### 1. predictions 테이블 (예측 저장)
```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL,                -- 예측 대상 회차
    prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    set_number INTEGER NOT NULL,           -- 세트 번호 (1-5)
    numbers TEXT NOT NULL,                 -- 예측 번호 (콤마 구분)
    confidence REAL,                       -- 신뢰도 (0.0-1.0)
    source TEXT,                          -- 예측 출처
    characteristics TEXT                   -- JSON 형식 특성
);

-- 인덱스
CREATE INDEX idx_predictions_round ON predictions(round);
CREATE INDEX idx_predictions_date ON predictions(prediction_date);
```

### 2. prediction_results 테이블 (결과 비교)
```sql
CREATE TABLE prediction_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL,
    prediction_id INTEGER,
    actual_numbers TEXT NOT NULL,          -- 실제 당첨번호
    bonus_number INTEGER,                  -- 보너스 번호
    match_count INTEGER,                   -- 일치 개수
    bonus_match BOOLEAN DEFAULT 0,         -- 보너스 일치 여부
    rank INTEGER,                          -- 등수 (1-5, 0=미당첨)
    prize_amount INTEGER,                  -- 예상 당첨금
    check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

-- 인덱스
CREATE INDEX idx_results_round ON prediction_results(round);
CREATE INDEX idx_results_rank ON prediction_results(rank);
```

### 3. weekly_performance 테이블 (주간 성과)
```sql
CREATE TABLE weekly_performance (
    round INTEGER PRIMARY KEY,
    prediction_count INTEGER DEFAULT 5,
    checked BOOLEAN DEFAULT 0,
    best_match INTEGER,                    -- 최고 일치 개수
    best_rank INTEGER,                     -- 최고 등수
    rank_1_count INTEGER DEFAULT 0,        -- 1등 당첨 수
    rank_2_count INTEGER DEFAULT 0,        -- 2등 당첨 수
    rank_3_count INTEGER DEFAULT 0,        -- 3등 당첨 수
    rank_4_count INTEGER DEFAULT 0,        -- 4등 당첨 수
    rank_5_count INTEGER DEFAULT 0,        -- 5등 당첨 수
    total_prize INTEGER DEFAULT 0,         -- 총 당첨금
    accuracy_rate REAL,                    -- 정확도 (평균 일치 개수)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 📁 파일 시스템 구조

```
data/
├── predictions/
│   ├── predictions.db              # SQLite 데이터베이스
│   ├── 2025/                      # 연도별 디렉토리
│   │   ├── week_1185.json         # 주차별 예측 파일
│   │   ├── week_1186.json
│   │   └── ...
│   └── results/
│       ├── 2025_summary.json      # 연간 요약
│       ├── monthly/
│       │   ├── 2025_08.json       # 월간 요약
│       │   └── ...
│       └── reports/
│           ├── weekly_report.md    # 주간 보고서
│           └── monthly_report.md   # 월간 보고서
```

## 🔧 클래스 구조

### PredictionTracker 클래스
```python
class PredictionTracker:
    """예측 번호 관리 클래스"""
    
    def __init__(self, db_path='data/predictions/predictions.db'):
        """데이터베이스 초기화"""
        
    def save_predictions(self, round_num: int, predictions: List[Dict]):
        """예측 5세트 저장"""
        
    def get_predictions(self, round_num: int) -> List[Dict]:
        """특정 회차 예측 조회"""
        
    def get_latest_unchecked(self) -> Optional[Dict]:
        """아직 확인하지 않은 최신 예측 조회"""
        
    def update_characteristics(self, prediction_id: int, characteristics: Dict):
        """예측 특성 업데이트"""
```

### ResultChecker 클래스
```python
class ResultChecker:
    """당첨 결과 확인 클래스"""
    
    def __init__(self, db_manager, prediction_tracker):
        """초기화"""
        
    def check_new_results(self) -> Dict:
        """새 당첨번호 확인 및 비교"""
        
    def calculate_rank(self, match_count: int, bonus_match: bool = False) -> int:
        """등수 계산
        - 6개 일치: 1등
        - 5개 + 보너스: 2등
        - 5개 일치: 3등
        - 4개 일치: 4등
        - 3개 일치: 5등
        """
        
    def estimate_prize(self, rank: int) -> int:
        """예상 당첨금 계산"""
        
    def save_results(self, round_num: int, results: Dict):
        """결과 저장"""
        
    def generate_report(self, round_num: int) -> str:
        """결과 보고서 생성"""
```

## 📊 JSON 데이터 형식

### 주간 예측 파일 (week_1185.json)
```json
{
    "round": 1185,
    "prediction_date": "2025-08-19T21:00:00",
    "model_version": "2.0",
    "predictions": [
        {
            "set": 1,
            "numbers": [3, 15, 22, 31, 38, 42],
            "confidence": 0.85,
            "source": "Ensemble",
            "characteristics": {
                "odd_even_ratio": "3:3",
                "sum_total": 151,
                "consecutive_count": 0,
                "section_distribution": [1, 1, 1, 2, 1],
                "hot_numbers": 2,
                "cold_numbers": 1
            }
        },
        {
            "set": 2,
            "numbers": [7, 12, 25, 33, 39, 44],
            "confidence": 0.78,
            "source": "LSTM",
            "characteristics": {
                "odd_even_ratio": "4:2",
                "sum_total": 160,
                "consecutive_count": 0,
                "section_distribution": [1, 1, 1, 2, 1],
                "hot_numbers": 3,
                "cold_numbers": 0
            }
        }
        // ... 3개 세트 더
    ],
    "result": {
        "checked": false,
        "check_date": null,
        "actual_numbers": null,
        "bonus_number": null,
        "matches": [],
        "best_rank": null,
        "total_prize": 0
    }
}
```

### 월간 요약 파일 (2025_08.json)
```json
{
    "year": 2025,
    "month": 8,
    "rounds": [1185, 1186, 1187, 1188],
    "total_predictions": 20,
    "performance": {
        "total_checked": 3,
        "rank_distribution": {
            "1등": 0,
            "2등": 0,
            "3등": 0,
            "4등": 1,
            "5등": 2,
            "미당첨": 12
        },
        "best_rank": 4,
        "total_prize": 55000,
        "accuracy_rate": 1.35,
        "hit_rate": 0.20
    },
    "trends": {
        "improving": true,
        "best_model": "Ensemble",
        "most_frequent_numbers": [7, 15, 22, 33, 38]
    }
}
```

## 🚀 사용 시나리오

### 1. 개발 단계 (현재)
```python
# main.py 실행 시
1. 프로그램 시작
2. 이전 예측 결과 확인
   - DB에서 미확인 예측 조회
   - 새 당첨번호와 비교
   - 결과 출력 및 저장
3. 새로운 예측 생성
4. DB와 JSON 파일에 저장
5. 예측 번호 출력
```

### 2. 서버 운영 단계 (미래)
```python
# 크론잡 또는 스케줄러로 실행
# 매주 토요일 20:45 - 당첨번호 발표 직후

1. 자동 실행 (토요일 20:45)
2. 웹 크롤링으로 당첨번호 수집
3. DB에서 해당 회차 예측 조회
4. 자동 비교 및 등수 계산
5. 결과 저장 및 리포트 생성
6. 사용자 알림 발송
   - 이메일/SMS/푸시 알림
   - "축하합니다! 1185회차 5등 당첨!"
7. 다음 회차 예측 자동 생성
8. 대시보드 업데이트
```

## 📈 리포팅 예시

### 콘솔 출력
```
====================================================
📊 예측 결과 확인 - 1184회차
====================================================
예측일: 2025-08-12 21:00:00
실제 당첨번호: [5, 15, 22, 31, 40, 45] + 보너스 [7]

[예측 1세트] [3, 15, 22, 31, 38, 42]
  ✅ 3개 일치 (15, 22, 31) → 5등 당첨! 💰 5,000원
  신뢰도: 85% | 출처: Ensemble

[예측 2세트] [7, 12, 25, 33, 39, 44]
  ❌ 1개 일치 (7) → 미당첨
  신뢰도: 78% | 출처: LSTM

[예측 3세트] [5, 15, 28, 35, 40, 43]
  ⭐ 4개 일치 (5, 15, 40) → 4등 당첨! 💰 50,000원
  신뢰도: 82% | 출처: Monte Carlo

----------------------------------------------------
📈 이번 회차 성과
- 총 5세트 중 2세트 당첨 (40% 적중률)
- 최고 등수: 4등
- 총 당첨금: 55,000원
- 평균 일치 개수: 1.8개

📊 누적 성과 (최근 10회)
- 총 50세트 중 8세트 당첨 (16% 적중률)
- 최고 등수: 3등 (1회)
- 누적 당첨금: 2,355,000원
====================================================
```

### 주간 보고서 (weekly_report.md)
```markdown
# 주간 로또 예측 성과 보고서

## 📅 기간: 2025년 8월 3주차 (1185회차)

### 🎯 예측 성과
| 세트 | 예측 번호 | 일치 | 등수 | 당첨금 |
|------|-----------|------|------|--------|
| 1 | [3, 15, 22, 31, 38, 42] | 3개 | 5등 | 5,000원 |
| 2 | [7, 12, 25, 33, 39, 44] | 1개 | - | 0원 |
| 3 | [5, 15, 28, 35, 40, 43] | 4개 | 4등 | 50,000원 |
| 4 | [11, 19, 27, 34, 41, 45] | 2개 | - | 0원 |
| 5 | [2, 14, 23, 30, 37, 44] | 2개 | - | 0원 |

### 📊 통계
- **적중률**: 40% (5세트 중 2세트)
- **총 당첨금**: 55,000원
- **평균 일치**: 2.4개
- **최고 성과**: 4등

### 📈 트렌드 분석
- 이번 주 Ensemble 모델 성능 우수
- 홀짝 비율 3:3 예측 적중
- 연속번호 0개 예측 정확

### 💡 개선 사항
- 핫넘버 예측 정확도 향상 필요
- 구간 분포 예측 개선 필요
```

## 🔄 구현 우선순위

### Phase 1: 기본 시스템 (즉시)
1. ✅ 설계 문서 작성
2. 데이터베이스 스키마 생성
3. PredictionTracker 클래스 구현
4. main.py에 저장 로직 통합

### Phase 2: 결과 확인 (1일)
1. ResultChecker 클래스 구현
2. 자동 비교 로직 구현
3. 등수 계산 및 당첨금 추정

### Phase 3: 리포팅 (2일)
1. 콘솔 출력 포맷팅
2. JSON 리포트 생성
3. Markdown 보고서 생성

### Phase 4: 고급 기능 (1주)
1. 웹 대시보드 준비
2. 알림 시스템 구현
3. 통계 분석 강화

## 🎯 기대 효과

1. **투명성**: 모든 예측과 결과를 추적 가능
2. **신뢰성**: 실제 성과를 바탕으로 시스템 개선
3. **사용자 경험**: 당첨 시 즉시 알림
4. **데이터 기반 개선**: 성과 분석을 통한 알고리즘 최적화

---

*이 시스템은 로또 예측의 투명성과 신뢰성을 높이는 핵심 인프라입니다.*
*작성일: 2025-08-19*