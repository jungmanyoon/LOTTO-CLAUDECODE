"""
예측 번호 저장 및 관리 시스템

매주 생성되는 로또 예측 번호를 체계적으로 저장하고 관리합니다.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import pytz  # 한국 시간대(KST) 처리 - 절대 제거하지 말 것!
from src.utils.json_encoder import NumpyJSONEncoder, convert_numpy_to_python

class PredictionTracker:
    """예측 번호 관리 클래스"""
    
    def __init__(self, db_path: str = None):
        """
        데이터베이스 초기화
        
        Args:
            db_path: 데이터베이스 경로 (기본값: data/predictions/predictions.db)
        """
        if db_path is None:
            base_path = Path(__file__).parent.parent.parent
            db_path = base_path / "data" / "predictions" / "predictions.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self._init_database()
    
    def _init_database(self):
        """데이터베이스 테이블 생성"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # predictions 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    prediction_date TIMESTAMP DEFAULT (datetime('now', 'localtime')),  -- KST 기준
                    set_number INTEGER NOT NULL,
                    numbers TEXT NOT NULL,
                    confidence REAL,
                    source TEXT,
                    characteristics TEXT
                )
            """)
            
            # prediction_results 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prediction_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round INTEGER NOT NULL,
                    prediction_id INTEGER,
                    actual_numbers TEXT NOT NULL,
                    bonus_number INTEGER,
                    match_count INTEGER,
                    bonus_match BOOLEAN DEFAULT 0,
                    rank INTEGER,
                    prize_amount INTEGER,
                    check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
                )
            """)
            
            # weekly_performance 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weekly_performance (
                    round INTEGER PRIMARY KEY,
                    prediction_count INTEGER DEFAULT 5,
                    checked BOOLEAN DEFAULT 0,
                    best_match INTEGER,
                    best_rank INTEGER,
                    rank_1_count INTEGER DEFAULT 0,
                    rank_2_count INTEGER DEFAULT 0,
                    rank_3_count INTEGER DEFAULT 0,
                    rank_4_count INTEGER DEFAULT 0,
                    rank_5_count INTEGER DEFAULT 0,
                    total_prize INTEGER DEFAULT 0,
                    accuracy_rate REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 생성
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_round ON predictions(round)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(prediction_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_round ON prediction_results(round)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_rank ON prediction_results(rank)")
            
            conn.commit()
            self.logger.info(f"데이터베이스 초기화 완료: {self.db_path}")
    
    def save_predictions(self, round_num: int, predictions: List[Dict], replace: bool = False) -> bool:
        """
        예측 5세트 저장
        
        Args:
            round_num: 회차 번호
            predictions: 예측 번호 리스트 (5세트)
                [
                    {
                        'numbers': [1, 2, 3, 4, 5, 6],
                        'confidence': 0.85,
                        'source': 'Ensemble',
                        'characteristics': {...}
                    },
                    ...
                ]
            replace: True면 기존 예측 삭제 후 저장, False면 누적 저장
        
        Returns:
            성공 여부
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # replace=True이면 기존 예측 삭제
                if replace:
                    cursor.execute("DELETE FROM predictions WHERE round = ?", (round_num,))
                    self.logger.info(f"{round_num}회차 기존 예측 {cursor.rowcount}개 삭제")
                    start_set_number = 1
                else:
                    # 누적 저장인 경우 기존 로직
                    cursor.execute("SELECT MAX(set_number) FROM predictions WHERE round = ?", (round_num,))
                    result = cursor.fetchone()
                    start_set_number = (result[0] + 1) if result[0] else 1
                
                # 예측 저장
                for idx, pred in enumerate(predictions):
                    set_number = start_set_number + idx
                    # numpy int32를 일반 int로 변환
                    numbers = [int(n) for n in pred['numbers']]
                    numbers_str = ','.join(map(str, numbers))
                    # NumPy 타입을 Python 기본 타입으로 변환
                    characteristics = convert_numpy_to_python(pred.get('characteristics', {}))
                    characteristics_json = json.dumps(
                        characteristics,
                        cls=NumpyJSONEncoder,
                        ensure_ascii=False
                    )
                    
                    cursor.execute("""
                        INSERT INTO predictions 
                        (round, set_number, numbers, confidence, source, characteristics)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        round_num,
                        set_number,
                        numbers_str,
                        float(pred.get('confidence', 0.5)),
                        pred.get('source', 'Unknown'),
                        characteristics_json
                    ))
                
                # weekly_performance 초기 레코드 생성
                cursor.execute("""
                    INSERT OR IGNORE INTO weekly_performance (round, prediction_count)
                    VALUES (?, ?)
                """, (round_num, len(predictions)))
                
                conn.commit()
                
                # JSON 백업 저장
                self._save_json_backup(round_num, predictions, replace=replace)
                
                self.logger.info(f"{round_num}회차 예측 {len(predictions)}세트 저장 완료")
                return True
                
        except Exception as e:
            self.logger.error(f"예측 저장 실패: {e}")
            return False
    
    def _convert_to_json_serializable(self, obj):
        """numpy 타입을 JSON 직렬화 가능한 타입으로 변환"""
        import numpy as np
        
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_json_serializable(item) for item in obj]
        else:
            return obj
    
    def _save_json_backup(self, round_num: int, predictions: List[Dict], replace: bool = False):
        """JSON 형식으로 백업 저장
        
        Args:
            round_num: 회차 번호
            predictions: 예측 리스트
            replace: True면 기존 파일 덮어쓰기, False면 누적
        """
        try:
            # 연도별 디렉토리 생성
            # IMPORTANT: 한국 시간대(KST) 사용 - 절대 변경하지 말 것!
            kst = pytz.timezone('Asia/Seoul')
            year = datetime.now(kst).year
            json_dir = self.db_path.parent / str(year)
            json_dir.mkdir(exist_ok=True)
            
            # 파일 경로
            json_path = json_dir / f"week_{round_num}.json"
            
            if replace or not json_path.exists():
                # 새로운 JSON 데이터 구성 (덮어쓰기)
                json_data = {
                    "round": round_num,
                    "prediction_date": datetime.now(pytz.timezone('Asia/Seoul')).isoformat(),  # KST 시간
                    "model_version": "2.0",
                    "predictions": []
                }
                existing_count = 0
            else:
                # 기존 파일에 누적
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                existing_count = len(json_data.get("predictions", []))
            
            # 예측 추가
            for i, pred in enumerate(predictions, existing_count + 1 if not replace else 1):
                # numpy 타입을 일반 타입으로 변환
                numbers = [int(self._convert_to_json_serializable(n)) for n in pred['numbers']]
                characteristics = self._convert_to_json_serializable(pred.get('characteristics', {}))
                
                json_data["predictions"].append({
                    "set": i,
                    "numbers": numbers,
                    "confidence": float(pred.get('confidence', 0.5)),
                    "source": pred.get('source', 'Unknown'),
                    "characteristics": characteristics
                })
            
            # 결과 섹션 초기화 (기존 결과가 없을 때만)
            if "result" not in json_data:
                json_data["result"] = {
                    "checked": False,
                    "check_date": None,
                    "actual_numbers": None,
                    "bonus_number": None,
                    "matches": [],
                    "best_rank": None,
                    "total_prize": 0
                }
            
            # 파일 저장
            json_path = json_dir / f"week_{round_num}.json"
            # NumPy 타입을 안전하게 변환하여 저장
            json_data_converted = convert_numpy_to_python(json_data)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data_converted, f, cls=NumpyJSONEncoder, ensure_ascii=False, indent=2)
            
            self.logger.info(f"JSON 백업 저장: {json_path}")
            
        except Exception as e:
            self.logger.error(f"JSON 백업 저장 실패: {e}")
    
    def get_predictions(self, round_num: int) -> List[Dict]:
        """
        특정 회차 예측 조회
        
        Args:
            round_num: 회차 번호
        
        Returns:
            예측 리스트
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, set_number, numbers, confidence, source, characteristics
                    FROM predictions
                    WHERE round = ?
                    ORDER BY set_number
                """, (round_num,))
                
                predictions = []
                for row in cursor.fetchall():
                    predictions.append({
                        'id': row[0],
                        'set_number': row[1],
                        'numbers': list(map(int, row[2].split(','))),
                        'confidence': row[3],
                        'source': row[4],
                        'characteristics': json.loads(row[5]) if row[5] else {}
                    })
                
                return predictions
                
        except Exception as e:
            self.logger.error(f"예측 조회 실패: {e}")
            return []
    
    def get_latest_unchecked(self) -> Optional[Dict]:
        """
        아직 확인하지 않은 최신 예측 조회
        
        Returns:
            미확인 예측 정보 또는 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT p.round, COUNT(p.id) as pred_count
                    FROM predictions p
                    LEFT JOIN weekly_performance wp ON p.round = wp.round
                    WHERE wp.checked = 0 OR wp.checked IS NULL
                    GROUP BY p.round
                    ORDER BY p.round DESC
                    LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    return {
                        'round': row[0],
                        'prediction_count': row[1],
                        'predictions': self.get_predictions(row[0])
                    }
                
                return None
                
        except Exception as e:
            self.logger.error(f"미확인 예측 조회 실패: {e}")
            return None
    
    def update_characteristics(self, prediction_id: int, characteristics: Dict):
        """
        예측 특성 업데이트
        
        Args:
            prediction_id: 예측 ID
            characteristics: 특성 정보
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # NumPy 타입을 Python 기본 타입으로 변환
                characteristics_converted = convert_numpy_to_python(characteristics)
                characteristics_json = json.dumps(characteristics_converted, cls=NumpyJSONEncoder, ensure_ascii=False)
                cursor.execute("""
                    UPDATE predictions
                    SET characteristics = ?
                    WHERE id = ?
                """, (characteristics_json, prediction_id))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"특성 업데이트 실패: {e}")
    
    def get_performance_summary(self, recent_rounds: int = 10) -> Dict:
        """
        최근 성과 요약 조회
        
        Args:
            recent_rounds: 조회할 최근 회차 수
        
        Returns:
            성과 요약 정보
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 최근 성과 조회
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT round) as total_rounds,
                        SUM(rank_1_count) as total_rank_1,
                        SUM(rank_2_count) as total_rank_2,
                        SUM(rank_3_count) as total_rank_3,
                        SUM(rank_4_count) as total_rank_4,
                        SUM(rank_5_count) as total_rank_5,
                        SUM(total_prize) as total_prize,
                        AVG(accuracy_rate) as avg_accuracy
                    FROM weekly_performance
                    WHERE checked = 1
                    ORDER BY round DESC
                    LIMIT ?
                """, (recent_rounds,))
                
                row = cursor.fetchone()
                if row:
                    total_wins = row[1] + row[2] + row[3] + row[4] + row[5]
                    total_predictions = row[0] * 5  # 회차당 5세트
                    
                    return {
                        'total_rounds': row[0],
                        'total_predictions': total_predictions,
                        'total_wins': total_wins,
                        'win_rate': total_wins / total_predictions if total_predictions > 0 else 0,
                        'rank_distribution': {
                            '1등': row[1] or 0,
                            '2등': row[2] or 0,
                            '3등': row[3] or 0,
                            '4등': row[4] or 0,
                            '5등': row[5] or 0
                        },
                        'total_prize': row[6] or 0,
                        'avg_accuracy': row[7] or 0
                    }
                
                return {
                    'total_rounds': 0,
                    'total_predictions': 0,
                    'total_wins': 0,
                    'win_rate': 0,
                    'rank_distribution': {},
                    'total_prize': 0,
                    'avg_accuracy': 0
                }
                
        except Exception as e:
            self.logger.error(f"성과 요약 조회 실패: {e}")
            return {}