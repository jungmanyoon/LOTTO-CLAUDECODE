#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
패턴 저장소 마이그레이션 스크립트

Phase 3.7: JSON 패턴 저장 → 컬럼 마이그레이션
- JSON 필드에서 요약 컬럼 추출
- 인덱스 추가로 쿼리 성능 개선
- 기존 JSON 데이터 보존 (하위 호환성)
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent


class PatternStorageMigrator:
    """패턴 저장소 마이그레이션 관리자"""

    # 추가할 요약 컬럼 정의
    SUMMARY_COLUMNS = {
        # 패턴별 최소/최대 확률
        'min_probability': {'type': 'REAL', 'default': None},
        'max_probability': {'type': 'REAL', 'default': None},
        # 패턴 카운트
        'total_pattern_count': {'type': 'INTEGER', 'default': 0},
        # 중요 패턴 플래그
        'has_low_prob_patterns': {'type': 'INTEGER', 'default': 0},  # boolean as int
        # 분석 버전 (마이그레이션 추적용)
        'schema_version': {'type': 'INTEGER', 'default': 2},
    }

    # 생성할 인덱스 정의
    INDEXES = [
        ('idx_pattern_round', 'pattern_analysis', ['round']),
        ('idx_pattern_analyzed_at', 'pattern_analysis', ['analyzed_at']),
        ('idx_pattern_min_prob', 'pattern_analysis', ['min_probability']),
        ('idx_pattern_max_prob', 'pattern_analysis', ['max_probability']),
        ('idx_pattern_has_low_prob', 'pattern_analysis', ['has_low_prob_patterns']),
        ('idx_pattern_round_analyzed', 'pattern_analysis', ['round', 'analyzed_at']),
    ]

    def __init__(self, db_path: Optional[Path] = None):
        """초기화

        Args:
            db_path: 데이터베이스 경로 (None이면 기본 경로 사용)
        """
        if db_path is None:
            db_path = PROJECT_ROOT / 'data' / 'patterns.db'
        self.db_path = Path(db_path)

    def analyze_current_schema(self) -> Dict[str, Any]:
        """현재 스키마 분석

        Returns:
            Dict: 스키마 분석 결과
        """
        result = {
            'db_exists': self.db_path.exists(),
            'table_exists': False,
            'columns': [],
            'indexes': [],
            'row_count': 0,
            'json_columns': [],
            'summary_columns_exist': [],
            'missing_summary_columns': [],
        }

        if not self.db_path.exists():
            return result

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 테이블 존재 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='pattern_analysis'
            """)
            result['table_exists'] = cursor.fetchone() is not None

            if not result['table_exists']:
                conn.close()
                return result

            # 컬럼 정보
            cursor.execute("PRAGMA table_info(pattern_analysis)")
            columns = cursor.fetchall()
            result['columns'] = [col[1] for col in columns]

            # JSON 컬럼 식별 (TEXT 타입이고 _patterns로 끝나는 것)
            for col in columns:
                col_name, col_type = col[1], col[2]
                if col_type == 'TEXT' and col_name.endswith('_patterns'):
                    result['json_columns'].append(col_name)

            # 요약 컬럼 존재 여부 확인
            for col_name in self.SUMMARY_COLUMNS:
                if col_name in result['columns']:
                    result['summary_columns_exist'].append(col_name)
                else:
                    result['missing_summary_columns'].append(col_name)

            # 인덱스 정보
            cursor.execute("""
                SELECT name, sql FROM sqlite_master
                WHERE type='index' AND tbl_name='pattern_analysis'
            """)
            result['indexes'] = [(row[0], row[1]) for row in cursor.fetchall()]

            # 행 수
            cursor.execute("SELECT COUNT(*) FROM pattern_analysis")
            result['row_count'] = cursor.fetchone()[0]

            conn.close()

        except Exception as e:
            logging.error(f"스키마 분석 중 오류: {str(e)}")

        return result

    def add_summary_columns(self) -> Dict[str, Any]:
        """요약 컬럼 추가

        Returns:
            Dict: 작업 결과
        """
        result = {
            'success': False,
            'columns_added': [],
            'columns_skipped': [],
            'error': None
        }

        if not self.db_path.exists():
            result['error'] = "데이터베이스 파일이 존재하지 않습니다."
            return result

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 기존 컬럼 확인
            cursor.execute("PRAGMA table_info(pattern_analysis)")
            existing_columns = {col[1] for col in cursor.fetchall()}

            # 요약 컬럼 추가
            for col_name, col_info in self.SUMMARY_COLUMNS.items():
                if col_name in existing_columns:
                    result['columns_skipped'].append(col_name)
                    continue

                col_type = col_info['type']
                default = col_info['default']

                if default is not None:
                    sql = f"ALTER TABLE pattern_analysis ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                else:
                    sql = f"ALTER TABLE pattern_analysis ADD COLUMN {col_name} {col_type}"

                cursor.execute(sql)
                result['columns_added'].append(col_name)
                logging.info(f"컬럼 추가: {col_name}")

            conn.commit()
            conn.close()

            result['success'] = True

        except Exception as e:
            result['error'] = str(e)
            logging.error(f"컬럼 추가 중 오류: {str(e)}")

        return result

    def create_indexes(self) -> Dict[str, Any]:
        """인덱스 생성

        Returns:
            Dict: 작업 결과
        """
        result = {
            'success': False,
            'indexes_created': [],
            'indexes_skipped': [],
            'error': None
        }

        if not self.db_path.exists():
            result['error'] = "데이터베이스 파일이 존재하지 않습니다."
            return result

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 기존 인덱스 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='pattern_analysis'
            """)
            existing_indexes = {row[0] for row in cursor.fetchall()}

            # 인덱스 생성
            for idx_name, table_name, columns in self.INDEXES:
                if idx_name in existing_indexes:
                    result['indexes_skipped'].append(idx_name)
                    continue

                # 컬럼 존재 여부 확인
                cursor.execute(f"PRAGMA table_info({table_name})")
                table_columns = {col[1] for col in cursor.fetchall()}

                missing_cols = [c for c in columns if c not in table_columns]
                if missing_cols:
                    logging.warning(f"인덱스 {idx_name} 생성 스킵: 컬럼 없음 - {missing_cols}")
                    result['indexes_skipped'].append(f"{idx_name} (missing: {missing_cols})")
                    continue

                cols_str = ', '.join(columns)
                sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({cols_str})"

                cursor.execute(sql)
                result['indexes_created'].append(idx_name)
                logging.info(f"인덱스 생성: {idx_name}")

            conn.commit()
            conn.close()

            result['success'] = True

        except Exception as e:
            result['error'] = str(e)
            logging.error(f"인덱스 생성 중 오류: {str(e)}")

        return result

    def extract_summary_from_json(self, json_data: str) -> Dict[str, Any]:
        """JSON 데이터에서 요약 정보 추출

        Args:
            json_data: JSON 문자열

        Returns:
            Dict: 요약 정보
        """
        summary = {
            'min_probability': None,
            'max_probability': None,
            'pattern_count': 0,
            'has_low_prob': False
        }

        if not json_data:
            return summary

        try:
            data = json.loads(json_data)

            if not isinstance(data, dict):
                return summary

            probabilities = []

            # 중첩 구조 처리
            def extract_probabilities(obj, depth=0):
                if depth > 3:  # 무한 재귀 방지
                    return

                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, (int, float)) and 0 <= value <= 100:
                            probabilities.append(float(value))
                        elif isinstance(value, dict):
                            extract_probabilities(value, depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (int, float)) and 0 <= value <= 100:
                            probabilities.append(float(item))
                        elif isinstance(item, dict):
                            extract_probabilities(item, depth + 1)

            extract_probabilities(data)

            if probabilities:
                summary['min_probability'] = min(probabilities)
                summary['max_probability'] = max(probabilities)
                summary['pattern_count'] = len(probabilities)
                # 1.0% 미만을 낮은 확률로 간주
                summary['has_low_prob'] = any(p < 1.0 for p in probabilities)

        except (json.JSONDecodeError, TypeError) as e:
            logging.debug(f"JSON 파싱 오류 (무시됨): {str(e)}")

        return summary

    def populate_summary_columns(self, batch_size: int = 100) -> Dict[str, Any]:
        """요약 컬럼 데이터 채우기

        Args:
            batch_size: 배치 크기

        Returns:
            Dict: 작업 결과
        """
        result = {
            'success': False,
            'rows_updated': 0,
            'rows_skipped': 0,
            'error': None
        }

        if not self.db_path.exists():
            result['error'] = "데이터베이스 파일이 존재하지 않습니다."
            return result

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # JSON 컬럼 목록 가져오기
            cursor.execute("PRAGMA table_info(pattern_analysis)")
            columns = cursor.fetchall()
            json_columns = [col[1] for col in columns
                           if col[2] == 'TEXT' and col[1].endswith('_patterns')]

            if not json_columns:
                result['error'] = "JSON 컬럼이 없습니다."
                conn.close()
                return result

            # 모든 행 가져오기
            cols_str = ', '.join(['round'] + json_columns)
            cursor.execute(f"SELECT {cols_str} FROM pattern_analysis")
            rows = cursor.fetchall()

            for row in rows:
                round_num = row[0]
                json_values = row[1:]

                # 모든 JSON 컬럼에서 요약 정보 수집
                all_min_probs = []
                all_max_probs = []
                total_count = 0
                has_any_low_prob = False

                for json_data in json_values:
                    if json_data:
                        summary = self.extract_summary_from_json(json_data)
                        if summary['min_probability'] is not None:
                            all_min_probs.append(summary['min_probability'])
                        if summary['max_probability'] is not None:
                            all_max_probs.append(summary['max_probability'])
                        total_count += summary['pattern_count']
                        if summary['has_low_prob']:
                            has_any_low_prob = True

                # 요약 컬럼 업데이트
                min_prob = min(all_min_probs) if all_min_probs else None
                max_prob = max(all_max_probs) if all_max_probs else None

                cursor.execute("""
                    UPDATE pattern_analysis
                    SET min_probability = ?,
                        max_probability = ?,
                        total_pattern_count = ?,
                        has_low_prob_patterns = ?,
                        schema_version = 2
                    WHERE round = ?
                """, (min_prob, max_prob, total_count,
                      1 if has_any_low_prob else 0, round_num))

                result['rows_updated'] += 1

            conn.commit()
            conn.close()

            result['success'] = True
            logging.info(f"요약 컬럼 데이터 채우기 완료: {result['rows_updated']}개 행 업데이트")

        except Exception as e:
            result['error'] = str(e)
            logging.error(f"요약 컬럼 채우기 중 오류: {str(e)}")

        return result

    def run_full_migration(self, dry_run: bool = False) -> Dict[str, Any]:
        """전체 마이그레이션 실행

        Args:
            dry_run: True면 실제 변경 없이 분석만 수행

        Returns:
            Dict: 마이그레이션 결과
        """
        result = {
            'dry_run': dry_run,
            'schema_analysis': None,
            'columns_result': None,
            'indexes_result': None,
            'populate_result': None,
            'success': False,
            'timestamp': datetime.now().isoformat()
        }

        logging.info("=" * 60)
        logging.info("패턴 저장소 마이그레이션 시작")
        logging.info("=" * 60)

        # 1. 스키마 분석
        result['schema_analysis'] = self.analyze_current_schema()
        logging.info(f"현재 스키마: {len(result['schema_analysis']['columns'])}개 컬럼, "
                    f"{result['schema_analysis']['row_count']}개 행")
        logging.info(f"JSON 컬럼: {result['schema_analysis']['json_columns']}")
        logging.info(f"누락된 요약 컬럼: {result['schema_analysis']['missing_summary_columns']}")

        if dry_run:
            logging.info("Dry run 모드 - 실제 변경 없음")
            result['success'] = True
            return result

        # 2. 요약 컬럼 추가
        result['columns_result'] = self.add_summary_columns()
        if not result['columns_result']['success']:
            logging.error(f"컬럼 추가 실패: {result['columns_result']['error']}")
            return result

        # 3. 인덱스 생성
        result['indexes_result'] = self.create_indexes()
        if not result['indexes_result']['success']:
            logging.error(f"인덱스 생성 실패: {result['indexes_result']['error']}")
            return result

        # 4. 요약 데이터 채우기
        result['populate_result'] = self.populate_summary_columns()
        if not result['populate_result']['success']:
            logging.error(f"요약 데이터 채우기 실패: {result['populate_result']['error']}")
            return result

        result['success'] = True
        logging.info("=" * 60)
        logging.info("패턴 저장소 마이그레이션 완료")
        logging.info("=" * 60)

        return result


class PatternQueryOptimizer:
    """패턴 쿼리 최적화 유틸리티"""

    @staticmethod
    def get_patterns_with_low_probability(
        db_path: Path,
        threshold: float = 1.0
    ) -> List[Tuple[int, float]]:
        """낮은 확률의 패턴이 있는 회차 조회 (최적화된 쿼리)

        Args:
            db_path: 데이터베이스 경로
            threshold: 확률 임계값

        Returns:
            List[Tuple[int, float]]: (회차, 최소확률) 목록
        """
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 요약 컬럼을 사용한 최적화된 쿼리
        cursor.execute("""
            SELECT round, min_probability
            FROM pattern_analysis
            WHERE has_low_prob_patterns = 1
              AND min_probability < ?
            ORDER BY round DESC
        """, (threshold,))

        results = cursor.fetchall()
        conn.close()

        return results

    @staticmethod
    def get_pattern_statistics_summary(db_path: Path) -> Dict[str, Any]:
        """패턴 통계 요약 조회 (최적화된 쿼리)

        Args:
            db_path: 데이터베이스 경로

        Returns:
            Dict: 통계 요약
        """
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_rounds,
                AVG(min_probability) as avg_min_prob,
                AVG(max_probability) as avg_max_prob,
                AVG(total_pattern_count) as avg_pattern_count,
                SUM(has_low_prob_patterns) as rounds_with_low_prob
            FROM pattern_analysis
            WHERE schema_version >= 2
        """)

        row = cursor.fetchone()
        conn.close()

        return {
            'total_rounds': row[0] or 0,
            'avg_min_probability': row[1],
            'avg_max_probability': row[2],
            'avg_pattern_count': row[3],
            'rounds_with_low_prob': row[4] or 0
        }


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='패턴 저장소 마이그레이션')
    parser.add_argument('--dry-run', action='store_true',
                       help='실제 변경 없이 분석만 수행')
    parser.add_argument('--db-path', type=str, default=None,
                       help='데이터베이스 경로')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    db_path = Path(args.db_path) if args.db_path else None
    migrator = PatternStorageMigrator(db_path)
    result = migrator.run_full_migration(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("마이그레이션 결과 요약")
    print("=" * 60)
    print(f"성공: {result['success']}")
    print(f"Dry Run: {result['dry_run']}")

    if result['schema_analysis']:
        print(f"\n스키마 분석:")
        print(f"  - 전체 행 수: {result['schema_analysis']['row_count']}")
        print(f"  - JSON 컬럼 수: {len(result['schema_analysis']['json_columns'])}")
        print(f"  - 기존 인덱스 수: {len(result['schema_analysis']['indexes'])}")

    if result['columns_result'] and not result['dry_run']:
        print(f"\n컬럼 추가:")
        print(f"  - 추가됨: {result['columns_result']['columns_added']}")
        print(f"  - 스킵됨: {result['columns_result']['columns_skipped']}")

    if result['indexes_result'] and not result['dry_run']:
        print(f"\n인덱스 생성:")
        print(f"  - 생성됨: {result['indexes_result']['indexes_created']}")
        print(f"  - 스킵됨: {result['indexes_result']['indexes_skipped']}")

    if result['populate_result'] and not result['dry_run']:
        print(f"\n요약 데이터:")
        print(f"  - 업데이트된 행: {result['populate_result']['rows_updated']}")


if __name__ == '__main__':
    main()
