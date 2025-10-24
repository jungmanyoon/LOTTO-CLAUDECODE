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
        self.computation_cost = 1.5  # 통계 계산으로 인한 중간 비용

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
        """필터 적용 - 각 조합 내부의 IQR 기반 이상치 탐지

        Args:
            combinations: 필터링할 조합 목록
            round_num: 회차 번호

        Returns:
            List[str]: 필터링된 조합 목록
        """
        if not combinations:
            return []

        max_outliers = self.criteria['max_outliers']
        multiplier = self.criteria['iqr_multiplier']
        filtered = []
        excluded_count = 0

        total = len(combinations)
        log_interval = max(1, total // 10)  # 10% 단위 로깅

        for idx, combo_str in enumerate(combinations):
            # 진행률 로깅 (10% 단위)
            if idx > 0 and idx % log_interval == 0:
                progress = (idx / total) * 100
                exclusion_rate = (excluded_count / idx) * 100
                logging.debug(
                    f"[OutlierDetectionFilter] 진행률: {progress:.0f}% | "
                    f"제외율: {exclusion_rate:.1f}%"
                )

            # 조합을 숫자 리스트로 변환
            numbers = list(map(int, combo_str.split(',')))

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
            if outlier_count <= max_outliers:
                filtered.append(combo_str)
            else:
                excluded_count += 1
                logging.debug(
                    f"[OutlierDetectionFilter] 제외: {combo_str} - "
                    f"이상치 {outlier_count}개 (> {max_outliers}), "
                    f"Q1={q1:.1f}, Q3={q3:.1f}, IQR={iqr:.1f}"
                )

        # 최종 결과 로깅 (조건부)
        remaining = len(filtered)
        excluded = total - remaining
        exclusion_rate = (excluded / total * 100) if total > 0 else 0

        # 실제로 제외된 조합이 있을 때만 INFO 레벨로 로깅
        if excluded > 0:
            logging.info(
                f"[OutlierDetectionFilter] 완료 - "
                f"{remaining:,}/{total:,}개 남음 ({excluded:,}개 제외, {exclusion_rate:.2f}%)"
            )
        else:
            logging.debug(
                f"[OutlierDetectionFilter] 완료 - "
                f"{remaining:,}/{total:,}개 남음 (제외 없음)"
            )

        return filtered

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
