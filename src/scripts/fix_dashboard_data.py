"""
대시보드 데이터 문제 수정 스크립트
predictions.db 초기화 및 테스트 데이터 생성
"""

import sqlite3
import os
import json
import random
from datetime import datetime, timedelta

def create_predictions_table():
    """predictions 테이블 생성"""
    db_path = 'data/predictions.db'
    
    print(f"[INFO] predictions.db 초기화 중...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # predictions 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round INTEGER NOT NULL,
            set_number INTEGER NOT NULL,
            numbers TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            source TEXT DEFAULT 'Filtered',
            characteristics TEXT,
            prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 인덱스 생성
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_round ON predictions(round)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(prediction_date)")
    
    conn.commit()
    print(f"[OK] predictions 테이블 생성 완료")
    
    return conn, cursor

def add_sample_predictions(conn, cursor):
    """샘플 예측 데이터 추가"""
    print(f"[INFO] 샘플 예측 데이터 생성 중...")
    
    # 최근 5개 회차에 대한 예측 생성 (1183-1187회차)
    for round_num in range(1183, 1188):
        # 각 회차당 5개 세트 예측
        for set_num in range(1, 6):
            # 랜덤 번호 생성
            numbers = sorted(random.sample(range(1, 46), 6))
            numbers_str = ','.join(map(str, numbers))
            
            # 신뢰도는 0.4 ~ 0.9 사이
            confidence = round(random.uniform(0.4, 0.9), 3)
            
            # 소스 선택
            sources = ['LSTM', 'Ensemble', 'MonteCarlo', 'Bayesian', 'Filtered']
            source = random.choice(sources)
            
            # 특성 정보
            characteristics = {
                'sum': sum(numbers),
                'odd_count': len([n for n in numbers if n % 2 == 1]),
                'even_count': len([n for n in numbers if n % 2 == 0]),
                'consecutive': any(numbers[i+1] - numbers[i] == 1 for i in range(5)),
                'max_gap': max(numbers[i+1] - numbers[i] for i in range(5))
            }
            
            # 예측 날짜 (각 회차마다 다른 날짜)
            base_date = datetime.now() - timedelta(days=(1187-round_num)*7)
            pred_date = base_date.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                INSERT INTO predictions (round, set_number, numbers, confidence, source, characteristics, prediction_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (round_num, set_num, numbers_str, confidence, source, json.dumps(characteristics), pred_date))
    
    conn.commit()
    print(f"[OK] {5*5}개 샘플 예측 데이터 추가 완료")

def create_performance_stats():
    """성능 통계 데이터 생성"""
    db_path = 'data/performance_stats.db'
    
    print(f"[INFO] performance_stats.db 초기화 중...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # performance_stats 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            prediction_count INTEGER DEFAULT 0,
            match_0 INTEGER DEFAULT 0,
            match_1 INTEGER DEFAULT 0,
            match_2 INTEGER DEFAULT 0,
            match_3 INTEGER DEFAULT 0,
            match_4 INTEGER DEFAULT 0,
            match_5 INTEGER DEFAULT 0,
            match_6 INTEGER DEFAULT 0,
            average_confidence REAL DEFAULT 0.0,
            execution_time REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 샘플 통계 데이터 추가
    models = ['LSTM', 'Ensemble', 'MonteCarlo', 'Bayesian', 'Filtered']
    
    for round_num in range(1183, 1188):
        for model in models:
            # 랜덤 통계 생성
            total = 100
            match_dist = [
                random.randint(5, 15),   # match_0
                random.randint(15, 30),  # match_1
                random.randint(25, 40),  # match_2
                random.randint(15, 25),  # match_3
                random.randint(5, 10),   # match_4
                random.randint(0, 3),    # match_5
                random.randint(0, 1)     # match_6
            ]
            
            # 합이 100이 되도록 조정
            current_sum = sum(match_dist)
            if current_sum != total:
                match_dist[1] += (total - current_sum)
            
            cursor.execute("""
                INSERT INTO performance_stats 
                (round, model_name, prediction_count, match_0, match_1, match_2, match_3, match_4, match_5, match_6, average_confidence, execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (round_num, model, total, *match_dist, random.uniform(0.5, 0.8), random.uniform(1.0, 5.0)))
    
    conn.commit()
    conn.close()
    print(f"[OK] 성능 통계 데이터 생성 완료")

def verify_data():
    """데이터 검증"""
    print(f"\n[INFO] 데이터 검증 중...")
    
    # predictions.db 확인
    conn = sqlite3.connect('data/predictions.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM predictions")
    pred_count = cursor.fetchone()[0]
    print(f"[OK] predictions 테이블: {pred_count}개 레코드")
    
    cursor.execute("SELECT DISTINCT round FROM predictions ORDER BY round")
    rounds = [r[0] for r in cursor.fetchall()]
    print(f"[OK] 예측 회차: {rounds}")
    conn.close()
    
    # performance_stats.db 확인
    if os.path.exists('data/performance_stats.db'):
        conn = sqlite3.connect('data/performance_stats.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM performance_stats")
        stats_count = cursor.fetchone()[0]
        print(f"[OK] performance_stats 테이블: {stats_count}개 레코드")
        conn.close()

def main():
    """메인 실행 함수"""
    print("="*60)
    print("대시보드 데이터 문제 수정 스크립트")
    print("="*60)
    
    # 1. predictions 테이블 생성
    conn, cursor = create_predictions_table()
    
    # 2. 기존 데이터 확인
    cursor.execute("SELECT COUNT(*) FROM predictions")
    existing_count = cursor.fetchone()[0]
    
    if existing_count == 0:
        # 3. 샘플 데이터 추가
        add_sample_predictions(conn, cursor)
    else:
        print(f"[INFO] 이미 {existing_count}개의 예측 데이터가 있습니다.")
    
    conn.close()
    
    # 4. performance_stats 생성
    create_performance_stats()
    
    # 5. 검증
    verify_data()
    
    print("\n" + "="*60)
    print("[완료] 대시보드 데이터 수정 완료!")
    print("이제 'python run_dashboard.py'로 대시보드를 실행하세요.")
    print("="*60)

if __name__ == "__main__":
    main()