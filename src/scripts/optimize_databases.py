#!/usr/bin/env python3
"""
데이터베이스 최적화 스크립트
- VACUUM으로 파일 크기 최적화
- 인덱스 추가로 쿼리 성능 향상
- 데이터베이스 통계 분석
"""

import sqlite3
import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DatabaseOptimizer:
    """데이터베이스 최적화 관리자"""

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.db_stats = {}

    def find_all_databases(self) -> List[Path]:
        """모든 .db 파일 찾기"""
        db_files = []
        for pattern in ["**/*.db"]:
            db_files.extend(self.base_path.glob(pattern))
        return [db for db in db_files if db.stat().st_size > 0]  # 빈 파일 제외

    def analyze_database(self, db_path: Path) -> Dict:
        """데이터베이스 분석"""
        stats = {
            'path': str(db_path),
            'size_before': db_path.stat().st_size,
            'tables': [],
            'indexes': [],
            'row_counts': {}
        }

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 테이블 목록 가져오기
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            stats['tables'] = [t[0] for t in tables]

            # 각 테이블의 행 수 확인
            for table_name in stats['tables']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    stats['row_counts'][table_name] = count
                except Exception as e:
                    logging.warning(f"테이블 {table_name} 분석 실패: {e}")

            # 인덱스 목록 가져오기
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = cursor.fetchall()
            stats['indexes'] = [i[0] for i in indexes if i[0] not in ['sqlite_autoindex_1']]

            conn.close()

        except Exception as e:
            logging.error(f"데이터베이스 분석 실패 {db_path}: {e}")

        return stats

    def optimize_database(self, db_path: Path) -> Tuple[bool, Dict]:
        """데이터베이스 최적화 수행"""
        result = {
            'path': str(db_path),
            'size_before': db_path.stat().st_size,
            'size_after': 0,
            'reduction': 0,
            'indexes_created': [],
            'vacuum_success': False,
            'error': None
        }

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 1. 분석 수행
            cursor.execute("ANALYZE")

            # 2. 테이블별 인덱스 생성 (필요한 경우)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            for table_name in [t[0] for t in tables]:
                try:
                    # 테이블 구조 확인
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()

                    # 주요 컬럼에 인덱스 생성 (이미 없는 경우)
                    for col in columns:
                        col_name = col[1]
                        # ID, round, numbers 같은 주요 컬럼에 인덱스 생성
                        if col_name in ['round', 'round_number', 'combination', 'pattern']:
                            index_name = f"idx_{table_name}_{col_name}"
                            try:
                                cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({col_name})")
                                result['indexes_created'].append(index_name)
                            except Exception as e:
                                logging.debug(f"인덱스 생성 스킵 {index_name}: {e}")

                except Exception as e:
                    logging.debug(f"테이블 {table_name} 인덱스 처리 스킵: {e}")

            # 3. VACUUM 수행
            conn.execute("VACUUM")
            result['vacuum_success'] = True

            conn.commit()
            conn.close()

            # 4. 최적화 후 크기 확인
            result['size_after'] = db_path.stat().st_size
            result['reduction'] = result['size_before'] - result['size_after']

            return True, result

        except Exception as e:
            result['error'] = str(e)
            logging.error(f"최적화 실패 {db_path}: {e}")
            return False, result

    def run_optimization(self):
        """전체 데이터베이스 최적화 실행"""
        print("\n" + "="*60)
        print("데이터베이스 최적화 시작")
        print("="*60)

        # 1. 모든 데이터베이스 찾기
        db_files = self.find_all_databases()
        print(f"\n발견된 데이터베이스: {len(db_files)}개")

        # 2. 크기 기준으로 정렬 (큰 파일부터)
        db_files.sort(key=lambda x: x.stat().st_size, reverse=True)

        total_size_before = sum(db.stat().st_size for db in db_files)
        total_size_after = 0
        optimized_count = 0
        failed_count = 0

        print(f"총 데이터베이스 크기: {total_size_before / (1024**3):.2f}GB\n")

        # 3. 각 데이터베이스 최적화
        for i, db_path in enumerate(db_files, 1):
            db_name = db_path.name
            db_size_mb = db_path.stat().st_size / (1024**2)

            print(f"[{i}/{len(db_files)}] {db_name} ({db_size_mb:.1f}MB) 최적화 중...", end=" ")

            # 크기가 작은 파일은 스킵 가능
            if db_size_mb < 1:  # 1MB 미만은 스킵
                print("스킵 (1MB 미만)")
                total_size_after += db_path.stat().st_size
                continue

            # 최적화 수행
            success, result = self.optimize_database(db_path)

            if success:
                reduction_mb = result['reduction'] / (1024**2)
                new_size_mb = result['size_after'] / (1024**2)
                reduction_pct = (result['reduction'] / result['size_before']) * 100 if result['size_before'] > 0 else 0

                print(f"완료! ({new_size_mb:.1f}MB, -{reduction_mb:.1f}MB, -{reduction_pct:.1f}%)")

                if result['indexes_created']:
                    print(f"  └─ 생성된 인덱스: {len(result['indexes_created'])}개")

                total_size_after += result['size_after']
                optimized_count += 1
            else:
                print(f"실패: {result.get('error', 'Unknown error')}")
                total_size_after += db_path.stat().st_size
                failed_count += 1

        # 4. 결과 요약
        print("\n" + "="*60)
        print("최적화 완료 요약")
        print("="*60)
        print(f"처리된 데이터베이스: {optimized_count}/{len(db_files)}개")
        print(f"실패: {failed_count}개")
        print(f"이전 총 크기: {total_size_before / (1024**3):.2f}GB")
        print(f"최적화 후 크기: {total_size_after / (1024**3):.2f}GB")

        total_reduction = total_size_before - total_size_after
        reduction_pct = (total_reduction / total_size_before) * 100 if total_size_before > 0 else 0
        print(f"절약된 공간: {total_reduction / (1024**3):.2f}GB ({reduction_pct:.1f}%)")
        print("="*60)

        return {
            'optimized': optimized_count,
            'failed': failed_count,
            'total_reduction': total_reduction,
            'reduction_percentage': reduction_pct
        }

def main():
    """메인 실행 함수"""
    import sys

    # 경로 설정
    if len(sys.argv) > 1:
        base_path = sys.argv[1]
    else:
        base_path = "."

    # 최적화 실행
    optimizer = DatabaseOptimizer(base_path)
    results = optimizer.run_optimization()

    # 결과에 따른 종료 코드
    if results['failed'] == 0:
        sys.exit(0)  # 모두 성공
    elif results['optimized'] > 0:
        sys.exit(1)  # 일부 성공
    else:
        sys.exit(2)  # 모두 실패

if __name__ == "__main__":
    main()
