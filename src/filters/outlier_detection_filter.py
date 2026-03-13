"""
Outlier Detection Filter - 조합 내 이상치 탐지 필터

각 조합 내부의 번호 분포를 분석하여 극단적인 값을 가진 조합 제외:
- **조합 내부** Q1, Q3 계산 (각 조합의 6개 번호 기준)
- IQR = Q3 - Q1
- 이상치 범위: [Q1 - multiplier×IQR, Q3 + multiplier×IQR] 밖의 값
- 이상치가 max_outliers개 이상인 조합 제외

이론적 근거:
1. 통계학의 표준 이상치 탐지 방법 (Tukey's fences)
2. 과거 당첨번호 분석: 극단값(1-5, 41-45)이 2개 이상 나오는 경우 드물음
3. 조합 내 번호 분포의 균형성 검증
4. 편향된 분포(몰림 현상) 제외로 다양성 확보
"""

from typing import List, Dict, Any
import logging
import numpy as np
from .base_filter import BaseFilter
from ..filter_optimizer import FilterOptimizer


class OutlierDetectionFilter(BaseFilter):
    """IQR 기반 이상치 탐지 필터

    조합 내 번호들의 통계적 이상치를 탐지하여 극단적인 분포 제외
    """

    def __init__(self, db_manager, criteria: Dict[str, Any] = None):
        """OutlierDetectionFilter 초기화

        Args:
            db_manager: 데이터베이스 관리자 인스턴스
            criteria: 필터링 기준값
                - max_outliers: 허용 가능한 최대 이상치 개수 (기본값: 1)
                - iqr_multiplier: IQR 승수 (기본값: 1.0, balanced)
        """
        super().__init__(db_manager, criteria)
        self.computation_cost = 1.5
        self.optimizer = FilterOptimizer(self._process_chunk_wrapper)

        # 과거 당첨번호 통계 분석 (참고용)
        self._analyze_historical_outliers()

    def _validate_criteria(self) -> None:
        """필터링 기준값 유효성 검사"""
        # 기본값 설정
        if 'max_outliers' not in self.criteria:
            self.criteria['max_outliers'] = 1  # 최대 1개 이상치 허용

        if 'iqr_multiplier' not in self.criteria:
            self.criteria['iqr_multiplier'] = 1.0  # 균형잡힌 승수

        # 유효성 검사
        max_outliers = self.criteria['max_outliers']
        if not isinstance(max_outliers, int) or max_outliers < 0 or max_outliers > 6:
            raise ValueError("'max_outliers'는 0에서 6 사이의 정수여야 합니다.")

        iqr_multiplier = self.criteria['iqr_multiplier']
        if not isinstance(iqr_multiplier, (int, float)) or iqr_multiplier <= 0:
            raise ValueError("'iqr_multiplier'는 양수여야 합니다.")

        logging.info(
            f"[OutlierDetectionFilter] 초기화 완료 - "
            f"max_outliers: {max_outliers}, iqr_multiplier: {iqr_multiplier}"
        )

    def _analyze_historical_outliers(self) -> None:
        """과거 당첨번호의 이상치 패턴 분석 (참고용)

        각 당첨 조합 내부의 이상치 개수를 분석하여 통계 산출
        """
        try:
            # 과거 당첨번호 가져오기
            winning_numbers = self.db_manager.get_all_winning_numbers()

            if not winning_numbers:
                logging.warning("[OutlierDetectionFilter] 당첨번호 데이터 없음")
                self.avg_outliers_per_combo = 0.5  # 기본값
                return

            # 각 조합의 이상치 개수 계산
            outlier_counts = []
            multiplier = self.criteria.get('iqr_multiplier', 0.75)

            for nums in winning_numbers:
                if isinstance(nums, str):
                    numbers = list(map(int, nums.split(',')))
                else:
                    numbers = list(nums[:6])  # 보너스 제외

                # 조합 내부 IQR 계산
                q1 = np.percentile(numbers, 25)
                q3 = np.percentile(numbers, 75)
                iqr = q3 - q1

                # 이상치 범위
                lower_bound = q1 - multiplier * iqr
                upper_bound = q3 + multiplier * iqr

                # 이상치 개수
                outlier_count = sum(
                    1 for num in numbers
                    if num < lower_bound or num > upper_bound
                )
                outlier_counts.append(outlier_count)

            # 통계 계산
            self.avg_outliers_per_combo = np.mean(outlier_counts)
            self.max_outliers_historical = max(outlier_counts)

            # 이상치 분포 계산
            unique, counts = np.unique(outlier_counts, return_counts=True)
            distribution = dict(zip(unique, counts))

            logging.info(
                f"[OutlierDetectionFilter] 과거 당첨번호 분석 완료 - "
                f"평균 이상치: {self.avg_outliers_per_combo:.2f}개, "
                f"최대: {self.max_outliers_historical}개"
            )
            logging.debug(f"  이상치 분포: {distribution}")

        except Exception as e:
            logging.error(f"[OutlierDetectionFilter] 통계 분석 실패: {e}")
            self.avg_outliers_per_combo = 0.5
            self.max_outliers_historical = 2

    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """필터 적용 - numpy 벡터화된 IQR 기반 이상치 탐지

        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호

        Returns:
            List[str]: 필터링된 조합 목록
        """
        if not combinations:
            return []

        return self.optimizer.optimize_filter(
            combinations=combinations,
            desc="outlier_detection 필터 진행률",
            max_outliers=self.criteria['max_outliers'],
            iqr_multiplier=self.criteria['iqr_multiplier']
        )

    @staticmethod
    def _process_chunk_wrapper(combinations_chunk: List[str], **kwargs) -> List[str]:
        """FilterOptimizer용 래퍼 함수"""
        return OutlierDetectionFilter._process_chunk(
            combinations_chunk,
            kwargs.get('max_outliers', 1),
            kwargs.get('iqr_multiplier', 1.0)
        )

    @staticmethod
    def _process_chunk(combinations_chunk: List[str],
                      max_outliers: int,
                      iqr_multiplier: float) -> List[str]:
        """청크 단위 벡터화 필터링

        n=6 고정이므로 Q1/Q3를 정렬 인덱스에서 직접 계산 (np.percentile 호출 제거)
        """
        try:
            chunk_arrays = np.array(
                [list(map(int, c.split(','))) for c in combinations_chunk],
                dtype=np.float32
            )

            # n=6 정렬 후 Q1/Q3 직접 계산 (percentile(25)=sorted[1]+0.25*(sorted[2]-sorted[1]))
            sorted_arr = np.sort(chunk_arrays, axis=1)
            q1 = sorted_arr[:, 1] + 0.25 * (sorted_arr[:, 2] - sorted_arr[:, 1])
            q3 = sorted_arr[:, 3] + 0.75 * (sorted_arr[:, 4] - sorted_arr[:, 3])
            iqr = q3 - q1

            lower = q1 - iqr_multiplier * iqr
            upper = q3 + iqr_multiplier * iqr

            # 이상치 개수 계산 (벡터화)
            outlier_mask = (chunk_arrays < lower[:, np.newaxis]) | (chunk_arrays > upper[:, np.newaxis])
            outlier_counts = np.sum(outlier_mask, axis=1)
            valid = outlier_counts <= max_outliers

            return [combinations_chunk[i] for i in range(len(combinations_chunk)) if valid[i]]

        except Exception as e:
            logging.error(f"[OutlierDetectionFilter] 청크 처리 오류: {e}")
            return combinations_chunk

    def check_combination(self, combination: str, round_num: int) -> bool:
        """단일 조합이 필터 조건을 만족하는지 확인

        Args:
            combination: 검사할 조합
            round_num: 회차 번호

        Returns:
            bool: 조건 만족 여부 (True = 통과)
        """
        max_outliers = self.criteria['max_outliers']
        multiplier = self.criteria['iqr_multiplier']

        # 조합을 숫자 리스트로 변환
        numbers = list(map(int, combination.split(',')))

        # 조합 내부 IQR 계산
        q1 = np.percentile(numbers, 25)
        q3 = np.percentile(numbers, 75)
        iqr = q3 - q1

        # 이상치 범위 계산
        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        # 이상치 개수 계산
        outlier_count = sum(
            1 for num in numbers
            if num < lower_bound or num > upper_bound
        )

        # 이상치가 허용 범위 내면 통과
        return outlier_count <= max_outliers

    def supports_early_termination(self) -> bool:
        """조기 종료 전략 지원 여부

        Returns:
            bool: 지원 여부 (True)
        """
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """필터 통계 정보 반환

        Returns:
            Dict[str, Any]: 통계 정보
        """
        return {
            'max_outliers': self.criteria['max_outliers'],
            'iqr_multiplier': self.criteria['iqr_multiplier'],
            'avg_outliers_per_combo': getattr(self, 'avg_outliers_per_combo', 0.0),
            'max_outliers_historical': getattr(self, 'max_outliers_historical', 2),
            'method': 'per_combination_iqr'
        }
