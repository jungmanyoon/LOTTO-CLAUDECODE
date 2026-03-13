#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조합 저장 방식 통합 마이그레이션 스크립트

Phase 3.10: 중복 조합 저장 통합
- TEXT vs BLOB 저장 분석
- 단일 형식(BLOB)으로 통합
- 마이그레이션 스크립트
- 데이터 무결성 검증

TEXT 형식: "1,2,3,4,5,6" - 약 17-20 바이트
BLOB 형식: 비트맵 정수 - 고정 8 바이트 (45비트 사용)
예상 절약: 약 60% 저장 공간 절약
"""

import sys
import logging
import sqlite3
import struct
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.validators import LottoValidator


class CombinationStorageMigrator:
    """조합 저장 방식 마이그레이션 관리자"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.logger = logging.getLogger(__name__)

        # 마이그레이션 대상 DB 목록
        self.db_paths = self._find_combination_databases()

    def _find_combination_databases(self) -> List[Path]:
        """조합을 저장하는 데이터베이스 찾기"""
        dbs = []

        # 주요 DB 경로
        data_dir = self.project_root / 'data'
        filters_dir = self.project_root / 'filters'
        results_dir = self.project_root / 'results'

        # combinations.db
        combinations_db = data_dir / 'combinations.db'
        if combinations_db.exists():
            dbs.append(combinations_db)

        # 필터 DB들
        if filters_dir.exists():
            for db_file in filters_dir.glob('*.db'):
                dbs.append(db_file)

        # results DB
        if results_dir.exists():
            for db_file in results_dir.glob('*.db'):
                dbs.append(db_file)

        return dbs

    def analyze_storage(self) -> Dict:
        """현재 저장 방식 분석

        Returns:
            Dict: 분석 결과 (DB별 TEXT/BLOB 테이블 수, 레코드 수, 크기)
        """
        analysis = {
            'databases': {},
            'total_text_records': 0,
            'total_blob_records': 0,
            'total_text_size_mb': 0.0,
            'total_blob_size_mb': 0.0,
            'estimated_savings_mb': 0.0
        }

        for db_path in self.db_paths:
            db_info = self._analyze_database(db_path)
            if db_info:
                analysis['databases'][str(db_path)] = db_info
                analysis['total_text_records'] += db_info.get('text_records', 0)
                analysis['total_blob_records'] += db_info.get('blob_records', 0)
                analysis['total_text_size_mb'] += db_info.get('text_size_mb', 0)
                analysis['total_blob_size_mb'] += db_info.get('blob_size_mb', 0)

        # 예상 절약량 계산 (TEXT 60% -> BLOB)
        if analysis['total_text_records'] > 0:
            # TEXT 평균 18바이트, BLOB 8바이트 -> 약 55% 절약
            estimated_savings = analysis['total_text_size_mb'] * 0.55
            analysis['estimated_savings_mb'] = round(estimated_savings, 2)

        return analysis

    def _analyze_database(self, db_path: Path) -> Optional[Dict]:
        """단일 데이터베이스 분석"""
        if not db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            db_info = {
                'path': str(db_path),
                'size_mb': round(db_path.stat().st_size / (1024 * 1024), 2),
                'text_tables': [],
                'blob_tables': [],
                'text_records': 0,
                'blob_records': 0,
                'text_size_mb': 0.0,
                'blob_size_mb': 0.0
            }

            # 테이블 목록 조회
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                # combination 컬럼 확인
                cursor.execute(f"PRAGMA table_info({table})")
                columns = {col[1]: col[2] for col in cursor.fetchall()}

                has_text = 'combination' in columns and columns['combination'].upper() == 'TEXT'
                has_blob = 'combination_blob' in columns and columns['combination_blob'].upper() == 'BLOB'

                if has_text:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    db_info['text_tables'].append({'name': table, 'records': count})
                    db_info['text_records'] += count
                    # 추정 크기 (평균 18바이트 * 레코드 수)
                    db_info['text_size_mb'] += (count * 18) / (1024 * 1024)

                if has_blob:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    db_info['blob_tables'].append({'name': table, 'records': count})
                    db_info['blob_records'] += count
                    # 추정 크기 (8바이트 * 레코드 수)
                    db_info['blob_size_mb'] += (count * 8) / (1024 * 1024)

            db_info['text_size_mb'] = round(db_info['text_size_mb'], 2)
            db_info['blob_size_mb'] = round(db_info['blob_size_mb'], 2)

            conn.close()
            return db_info

        except Exception as e:
            self.logger.error(f"DB 분석 실패 {db_path}: {str(e)}")
            return None

    def migrate_to_blob(self, db_path: Path, table_name: str,
                       batch_size: int = 10000) -> Dict:
        """TEXT 테이블을 BLOB으로 마이그레이션

        Args:
            db_path: 데이터베이스 경로
            table_name: 마이그레이션 대상 테이블
            batch_size: 배치 크기

        Returns:
            Dict: 마이그레이션 결과
        """
        result = {
            'success': False,
            'table': table_name,
            'records_migrated': 0,
            'errors': [],
            'elapsed_seconds': 0
        }

        start_time = datetime.now()

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 원본 테이블 정보 확인
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = {col[1]: col[2] for col in cursor.fetchall()}

            if 'combination' not in columns:
                result['errors'].append("combination 컬럼이 없습니다")
                conn.close()
                return result

            # 임시 테이블 생성
            new_table = f"{table_name}_blob"

            # 기존 컬럼 목록 구성
            other_columns = [col for col in columns.keys() if col != 'combination']

            # 새 테이블 스키마 구성
            column_defs = ['combination_blob BLOB NOT NULL']
            for col in other_columns:
                column_defs.append(f"{col} {columns[col]}")

            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {new_table} (
                    {", ".join(column_defs)}
                )
            ''')

            # 데이터 마이그레이션
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_records = cursor.fetchone()[0]

            offset = 0
            while offset < total_records:
                # 배치 조회
                select_cols = ['combination'] + other_columns
                cursor.execute(f'''
                    SELECT {", ".join(select_cols)}
                    FROM {table_name}
                    LIMIT ? OFFSET ?
                ''', (batch_size, offset))

                batch = cursor.fetchall()

                # 변환 및 삽입
                insert_data = []
                for row in batch:
                    combination_text = row[0]
                    other_values = row[1:]

                    try:
                        # TEXT -> BLOB 변환
                        numbers = [int(n) for n in combination_text.split(',')]
                        bitmap = LottoValidator.encode_combination(numbers)
                        blob_data = struct.pack('<Q', bitmap)  # 8바이트 리틀 엔디안

                        insert_data.append((blob_data,) + other_values)
                        result['records_migrated'] += 1

                    except Exception as e:
                        result['errors'].append(f"변환 실패: {combination_text} - {str(e)}")

                # 배치 삽입
                if insert_data:
                    placeholders = ', '.join(['?'] * len(insert_data[0]))
                    cursor.executemany(f'''
                        INSERT INTO {new_table} VALUES ({placeholders})
                    ''', insert_data)
                    conn.commit()

                offset += batch_size
                self.logger.info(f"마이그레이션 진행: {min(offset, total_records)}/{total_records}")

            # 인덱스 생성
            cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{new_table}_blob ON {new_table}(combination_blob)')
            conn.commit()

            result['success'] = True

        except Exception as e:
            result['errors'].append(f"마이그레이션 실패: {str(e)}")

        finally:
            conn.close()
            result['elapsed_seconds'] = (datetime.now() - start_time).total_seconds()

        return result

    def verify_migration(self, db_path: Path, old_table: str,
                        new_table: str, sample_size: int = 1000) -> Dict:
        """마이그레이션 검증

        Args:
            db_path: 데이터베이스 경로
            old_table: 원본 테이블
            new_table: 마이그레이션된 테이블
            sample_size: 검증 샘플 크기

        Returns:
            Dict: 검증 결과
        """
        result = {
            'verified': False,
            'samples_checked': 0,
            'mismatches': 0,
            'errors': []
        }

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 샘플 조회 (원본)
            cursor.execute(f"SELECT combination FROM {old_table} LIMIT ?", (sample_size,))
            old_samples = [row[0] for row in cursor.fetchall()]

            # 새 테이블에서 조회 및 비교
            cursor.execute(f"SELECT combination_blob FROM {new_table} LIMIT ?", (sample_size,))
            new_samples = cursor.fetchall()

            for i, (old_combo, new_row) in enumerate(zip(old_samples, new_samples)):
                result['samples_checked'] += 1

                # BLOB -> 숫자 복원
                blob_data = new_row[0]
                bitmap = struct.unpack('<Q', blob_data)[0]
                decoded = LottoValidator.decode_combination(bitmap)
                decoded_text = ','.join(map(str, decoded))

                if decoded_text != old_combo:
                    result['mismatches'] += 1
                    result['errors'].append(f"불일치: {old_combo} vs {decoded_text}")

            result['verified'] = (result['mismatches'] == 0)

            conn.close()

        except Exception as e:
            result['errors'].append(f"검증 실패: {str(e)}")

        return result

    def estimate_size_reduction(self) -> Dict:
        """크기 절약량 예측

        Returns:
            Dict: 절약량 예측 정보
        """
        analysis = self.analyze_storage()

        # TEXT: 평균 18바이트 ("1,12,23,34,40,45" 형식)
        # BLOB: 고정 8바이트 (45비트 비트맵)

        text_size = analysis['total_text_size_mb']
        estimated_blob_size = text_size * (8 / 18)  # 비율로 계산

        return {
            'current_text_size_mb': round(text_size, 2),
            'estimated_blob_size_mb': round(estimated_blob_size, 2),
            'estimated_savings_mb': round(text_size - estimated_blob_size, 2),
            'savings_percent': round((1 - 8/18) * 100, 1),
            'total_text_records': analysis['total_text_records']
        }


class CombinationStorageUnifier:
    """조합 저장 통합 API

    TEXT와 BLOB 형식을 자동으로 처리하는 통합 인터페이스
    """

    @staticmethod
    def encode_to_blob(combination: str) -> bytes:
        """문자열 조합을 BLOB으로 변환

        Args:
            combination: "1,2,3,4,5,6" 형식의 문자열

        Returns:
            bytes: 8바이트 BLOB 데이터
        """
        numbers = [int(n) for n in combination.split(',')]
        bitmap = LottoValidator.encode_combination(numbers)
        return struct.pack('<Q', bitmap)

    @staticmethod
    def decode_from_blob(blob: bytes) -> str:
        """BLOB에서 문자열 조합으로 변환

        Args:
            blob: 8바이트 BLOB 데이터

        Returns:
            str: "1,2,3,4,5,6" 형식의 문자열
        """
        bitmap = struct.unpack('<Q', blob)[0]
        numbers = LottoValidator.decode_combination(bitmap)
        return ','.join(map(str, numbers))

    @staticmethod
    def encode_batch(combinations: List[str]) -> List[bytes]:
        """배치 인코딩"""
        return [CombinationStorageUnifier.encode_to_blob(c) for c in combinations]

    @staticmethod
    def decode_batch(blobs: List[bytes]) -> List[str]:
        """배치 디코딩"""
        return [CombinationStorageUnifier.decode_from_blob(b) for b in blobs]


def print_analysis_report(analysis: Dict):
    """분석 결과 출력"""
    print("\n" + "=" * 60)
    print("조합 저장 방식 분석 보고서")
    print("=" * 60)

    print(f"\n총 TEXT 레코드: {analysis['total_text_records']:,}")
    print(f"총 BLOB 레코드: {analysis['total_blob_records']:,}")
    print(f"총 TEXT 크기 (추정): {analysis['total_text_size_mb']:.2f} MB")
    print(f"총 BLOB 크기 (추정): {analysis['total_blob_size_mb']:.2f} MB")
    print(f"예상 절약량: {analysis['estimated_savings_mb']:.2f} MB")

    print("\n데이터베이스별 상세:")
    print("-" * 60)

    for db_path, db_info in analysis['databases'].items():
        print(f"\n{Path(db_path).name}:")
        print(f"  파일 크기: {db_info['size_mb']:.2f} MB")

        if db_info['text_tables']:
            print("  TEXT 테이블:")
            for table in db_info['text_tables']:
                print(f"    - {table['name']}: {table['records']:,} 레코드")

        if db_info['blob_tables']:
            print("  BLOB 테이블:")
            for table in db_info['blob_tables']:
                print(f"    - {table['name']}: {table['records']:,} 레코드")


def main():
    """CLI 실행"""
    import argparse

    parser = argparse.ArgumentParser(description='조합 저장 방식 마이그레이션')
    parser.add_argument('--analyze', action='store_true', help='현재 저장 방식 분석')
    parser.add_argument('--estimate', action='store_true', help='크기 절약량 예측')
    parser.add_argument('--migrate', type=str, help='마이그레이션 실행 (DB:테이블)')
    parser.add_argument('--verify', type=str, help='마이그레이션 검증 (DB:원본:새테이블)')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    migrator = CombinationStorageMigrator()

    if args.analyze:
        analysis = migrator.analyze_storage()
        print_analysis_report(analysis)

    elif args.estimate:
        estimate = migrator.estimate_size_reduction()
        print("\n크기 절약량 예측:")
        print(f"  현재 TEXT 크기: {estimate['current_text_size_mb']:.2f} MB")
        print(f"  예상 BLOB 크기: {estimate['estimated_blob_size_mb']:.2f} MB")
        print(f"  예상 절약량: {estimate['estimated_savings_mb']:.2f} MB ({estimate['savings_percent']}%)")
        print(f"  총 TEXT 레코드: {estimate['total_text_records']:,}")

    elif args.migrate:
        db_table = args.migrate.split(':')
        if len(db_table) != 2:
            print("형식: --migrate DB경로:테이블명")
            return
        db_path, table = db_table
        result = migrator.migrate_to_blob(Path(db_path), table)
        print(f"\n마이그레이션 결과:")
        print(f"  성공: {result['success']}")
        print(f"  마이그레이션된 레코드: {result['records_migrated']:,}")
        print(f"  소요 시간: {result['elapsed_seconds']:.2f}초")
        if result['errors']:
            print(f"  오류: {len(result['errors'])}건")

    elif args.verify:
        parts = args.verify.split(':')
        if len(parts) != 3:
            print("형식: --verify DB경로:원본테이블:새테이블")
            return
        db_path, old_table, new_table = parts
        result = migrator.verify_migration(Path(db_path), old_table, new_table)
        print(f"\n검증 결과:")
        print(f"  검증됨: {result['verified']}")
        print(f"  확인된 샘플: {result['samples_checked']}")
        print(f"  불일치: {result['mismatches']}")

    else:
        # 기본: 분석 실행
        analysis = migrator.analyze_storage()
        print_analysis_report(analysis)


if __name__ == '__main__':
    main()
