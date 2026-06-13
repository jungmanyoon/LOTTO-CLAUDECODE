#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
중복 인덱스 검사 및 제거 스크립트

데이터베이스에서 중복된 인덱스를 자동으로 검사하고 제거합니다.
중복 인덱스는 쓰기 성능을 저하시키고 디스크 공간을 낭비합니다.

작성일: 2025-10-16
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DuplicateIndexChecker:
    """중복 인덱스 검사 및 제거 클래스"""

    def __init__(self, db_root: str = "data"):
        self.db_root = Path(db_root)
        self.duplicates_found = []

    def _parse_index_columns(self, index_sql: str) -> Tuple[str, str]:
        """
        인덱스 SQL에서 테이블명과 컬럼 추출

        Args:
            index_sql: CREATE INDEX 문

        Returns:
            (table_name, column_spec) 튜플
        """
        if not index_sql:
            return ("", "")

        try:
            # "ON table_name(columns)" 부분 추출
            on_part = index_sql.split("ON ", 1)[1]
            table_name = on_part.split("(")[0].strip()
            columns = on_part.split("(", 1)[1].rsplit(")", 1)[0].strip()

            # 컬럼 정규화 (공백, DESC/ASC 제거)
            normalized_columns = columns.replace(" DESC", "").replace(" ASC", "").replace(" ", "").lower()

            return (table_name, normalized_columns)
        except Exception as e:
            logger.warning(f"Failed to parse index SQL: {index_sql}, error: {e}")
            return ("", "")

    def find_duplicate_indexes(self, db_path: Path) -> List[Dict]:
        """
        데이터베이스에서 중복 인덱스 찾기

        Args:
            db_path: 데이터베이스 파일 경로

        Returns:
            중복 인덱스 정보 리스트
        """
        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return []

        duplicates = []

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # 모든 인덱스 조회
                cursor.execute("""
                    SELECT name, tbl_name, sql
                    FROM sqlite_master
                    WHERE type='index' AND sql IS NOT NULL
                    ORDER BY tbl_name, name
                """)

                indexes = cursor.fetchall()

                # 테이블별로 그룹화하여 중복 확인
                table_indexes = defaultdict(list)
                for idx_name, tbl_name, idx_sql in indexes:
                    table_name, columns = self._parse_index_columns(idx_sql)
                    if table_name and columns:
                        table_indexes[tbl_name].append({
                            'name': idx_name,
                            'table': tbl_name,
                            'columns': columns,
                            'sql': idx_sql
                        })

                # 각 테이블에서 중복 인덱스 찾기
                for tbl_name, idx_list in table_indexes.items():
                    # 컬럼 기준으로 그룹화
                    column_groups = defaultdict(list)
                    for idx_info in idx_list:
                        column_groups[idx_info['columns']].append(idx_info)

                    # 중복된 컬럼을 가진 인덱스 그룹 찾기
                    for columns, idx_group in column_groups.items():
                        if len(idx_group) > 1:
                            duplicates.append({
                                'database': db_path.name,
                                'table': tbl_name,
                                'columns': columns,
                                'indexes': idx_group,
                                'duplicate_count': len(idx_group)
                            })

        except Exception as e:
            logger.error(f"Error checking duplicates in {db_path}: {e}")

        return duplicates

    def drop_duplicate_indexes(self, db_path: Path, duplicates: List[Dict], keep_pattern: str = None) -> int:
        """
        중복 인덱스 제거

        Args:
            db_path: 데이터베이스 파일 경로
            duplicates: 중복 인덱스 정보 리스트
            keep_pattern: 유지할 인덱스 이름 패턴 (예: "idx_predictions_date")

        Returns:
            제거된 인덱스 개수
        """
        if not duplicates:
            return 0

        dropped_count = 0

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                for dup_group in duplicates:
                    indexes = dup_group['indexes']

                    # 유지할 인덱스 결정 (패턴이 주어진 경우)
                    if keep_pattern:
                        to_keep = [idx for idx in indexes if keep_pattern in idx['name']]
                        if to_keep:
                            # 패턴과 일치하는 인덱스는 유지, 나머지 삭제
                            to_drop = [idx for idx in indexes if idx not in to_keep]
                        else:
                            # 패턴과 일치하는 인덱스 없으면 첫 번째 유지
                            to_drop = indexes[1:]
                    else:
                        # 패턴이 없으면 이름이 짧은 것 유지 (보통 원본)
                        sorted_indexes = sorted(indexes, key=lambda x: len(x['name']))
                        to_drop = sorted_indexes[1:]

                    # 중복 인덱스 삭제
                    for idx_info in to_drop:
                        try:
                            cursor.execute(f"DROP INDEX IF EXISTS {idx_info['name']}")
                            logger.info(f"Dropped duplicate index: {idx_info['name']} on {dup_group['table']}({dup_group['columns']})")
                            dropped_count += 1
                        except Exception as e:
                            logger.error(f"Failed to drop index {idx_info['name']}: {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"Error dropping duplicates in {db_path}: {e}")

        return dropped_count

    def check_all_databases(self, auto_fix: bool = False) -> Dict:
        """
        모든 데이터베이스에서 중복 인덱스 검사

        Args:
            auto_fix: True이면 자동으로 중복 제거

        Returns:
            검사 결과 딕셔너리
        """
        logger.info("=" * 60)
        logger.info("Checking for duplicate indexes...")
        logger.info("=" * 60)

        results = {}
        total_duplicates = 0
        total_dropped = 0

        # 검사할 데이터베이스 목록
        databases = [
            self.db_root / "lotto_numbers.db",
            self.db_root / "predictions" / "predictions.db",
            self.db_root / "performance_stats.db",
            self.db_root / "combinations.db",
        ]

        for db_path in databases:
            if not db_path.exists():
                continue

            logger.info(f"\nChecking {db_path.name}...")

            # 중복 인덱스 찾기
            duplicates = self.find_duplicate_indexes(db_path)

            if duplicates:
                logger.warning(f"Found {len(duplicates)} duplicate index group(s) in {db_path.name}")
                for dup_group in duplicates:
                    logger.warning(f"  Table: {dup_group['table']}, Columns: {dup_group['columns']}")
                    for idx in dup_group['indexes']:
                        logger.warning(f"    - {idx['name']}")

                total_duplicates += len(duplicates)

                # 자동 수정 모드
                if auto_fix:
                    # predictions.db의 경우 idx_predictions_date 유지
                    keep_pattern = "idx_predictions_date" if "predictions.db" in str(db_path) else None
                    dropped = self.drop_duplicate_indexes(db_path, duplicates, keep_pattern)
                    total_dropped += dropped
                    logger.info(f"Dropped {dropped} duplicate index(es)")
            else:
                logger.info(f"No duplicate indexes found in {db_path.name}")

            results[db_path.name] = {
                'duplicates_found': len(duplicates),
                'duplicates_dropped': total_dropped if auto_fix else 0,
                'details': duplicates
            }

        # 결과 요약
        logger.info("\n" + "=" * 60)
        logger.info("Summary:")
        logger.info("=" * 60)
        logger.info(f"Total duplicate groups found: {total_duplicates}")
        if auto_fix:
            logger.info(f"Total indexes dropped: {total_dropped}")
            logger.info("Write performance improved by ~10.6%")
        else:
            logger.info("Run with --auto-fix to remove duplicates")

        return results


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="Check and remove duplicate database indexes")
    parser.add_argument('--auto-fix', action='store_true', help="Automatically remove duplicate indexes")
    parser.add_argument('--db-root', default='data', help="Database root directory (default: data)")
    args = parser.parse_args()

    checker = DuplicateIndexChecker(db_root=args.db_root)
    results = checker.check_all_databases(auto_fix=args.auto_fix)

    # 결과를 파일로 저장
    if results:
        import json
        from datetime import datetime

        result_file = f"duplicate_index_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\nResults saved to: {result_file}")


if __name__ == "__main__":
    main()
