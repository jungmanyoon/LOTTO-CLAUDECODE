#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터베이스 스키마 수정 스크립트
round_num 컬럼을 round로 통일
"""

import sqlite3
import os
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def fix_database_schema():
    """데이터베이스 스키마 수정"""
    
    # 데이터베이스 파일 경로
    db_paths = [
        'data/combinations.db',
        'data/filters/match_filter.db',
        'data/filters/odd_even_filter.db',
        'data/filters/consecutive_filter.db',
        'data/filters/sum_range_filter.db',
        'data/filters/fixed_step_filter.db',
        'data/filters/last_digit_filter.db',
        'data/filters/max_gap_filter.db',
        'data/filters/section_filter.db',
        'data/filters/average_filter.db',
        'data/filters/multiple_filter.db',
        'data/filters/ten_section_filter.db',
        'data/filters/arithmetic_sequence_filter.db',
        'data/filters/geometric_sequence_filter.db',
        'data/filters/prime_composite_filter.db',
        'data/filters/digit_sum_filter.db',
        'data/filters/dispersion_filter.db'
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            logging.info(f"데이터베이스 확인: {db_path}")
            
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # 테이블 존재 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filtered_combinations'")
                if cursor.fetchone():
                    logging.info(f"  - filtered_combinations 테이블 발견")
                    
                    # 현재 스키마 확인
                    cursor.execute("PRAGMA table_info(filtered_combinations)")
                    columns = cursor.fetchall()
                    column_names = [col[1] for col in columns]
                    
                    if 'round_num' in column_names and 'round' not in column_names:
                        logging.info(f"  - round_num 컬럼을 round로 변경 필요")
                        
                        # 새 테이블 생성
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS filtered_combinations_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                round INTEGER NOT NULL,
                                combination TEXT NOT NULL,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(round, combination)
                            )
                        """)
                        
                        # 데이터 복사
                        cursor.execute("""
                            INSERT OR IGNORE INTO filtered_combinations_new (round, combination, created_at)
                            SELECT round_num, combination, created_at FROM filtered_combinations
                        """)
                        
                        # 기존 테이블 삭제
                        cursor.execute("DROP TABLE filtered_combinations")
                        
                        # 새 테이블 이름 변경
                        cursor.execute("ALTER TABLE filtered_combinations_new RENAME TO filtered_combinations")
                        
                        logging.info(f"  - 스키마 변경 완료")
                    else:
                        logging.info(f"  - 이미 올바른 스키마 사용 중")
                
                # excluded_combinations 테이블도 확인
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='excluded_combinations'")
                if cursor.fetchone():
                    logging.info(f"  - excluded_combinations 테이블 발견")
                    
                    # 현재 스키마 확인
                    cursor.execute("PRAGMA table_info(excluded_combinations)")
                    columns = cursor.fetchall()
                    column_names = [col[1] for col in columns]
                    
                    if 'round_num' in column_names and 'round' not in column_names:
                        logging.info(f"  - round_num 컬럼을 round로 변경 필요")
                        
                        # 새 테이블 생성
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS excluded_combinations_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                round INTEGER NOT NULL,
                                combination TEXT NOT NULL,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(round, combination)
                            )
                        """)
                        
                        # 데이터 복사
                        cursor.execute("""
                            INSERT OR IGNORE INTO excluded_combinations_new (round, combination, created_at)
                            SELECT round_num, combination, created_at FROM excluded_combinations
                        """)
                        
                        # 기존 테이블 삭제
                        cursor.execute("DROP TABLE excluded_combinations")
                        
                        # 새 테이블 이름 변경
                        cursor.execute("ALTER TABLE excluded_combinations_new RENAME TO excluded_combinations")
                        
                        logging.info(f"  - 스키마 변경 완료")
                
                conn.commit()
                conn.close()
                
            except Exception as e:
                logging.error(f"  - 오류 발생: {str(e)}")
    
    logging.info("\n스키마 수정 완료!")
    logging.info("프로그램을 다시 실행해주세요.")

if __name__ == "__main__":
    fix_database_schema()