#!/usr/bin/env python3
"""
ML 기반 예측 필터
머신러닝 모델의 예측을 기반으로 번호 조합을 필터링
"""
import logging
from typing import List, Dict, Optional
import numpy as np
from .base_filter import BaseFilter

class MLPredictionFilter(BaseFilter):
    """ML 예측 기반 필터"""
    
    def __init__(self, db_manager, criteria=None, predictor=None):
        """
        Args:
            db_manager: 데이터베이스 매니저
            criteria: 필터 기준값 (ML 필터는 사용하지 않음)
            predictor: ML 예측기 인스턴스
        """
        super().__init__(db_manager, criteria or {})
        self.predictor = predictor
        self.threshold = 0.5  # 기본 확률 임계값
        
    def apply(self, combinations: List[str], round_num: int) -> List[str]:
        """ML 예측 기반 필터링
        
        Args:
            combinations: 필터링할 조합 리스트
            round_num: 회차 번호
            
        Returns:
            List[str]: 필터링된 조합 리스트
        """
        if not self.predictor:
            logging.debug("ML 예측기가 설정되지 않았습니다. 백테스팅 모드에서는 정상입니다.")
            return combinations
            
        try:
            # 과거 당첨번호 데이터 가져오기
            winning_numbers = self.db_manager.get_all_winning_numbers()
            
            if not winning_numbers or len(winning_numbers) < 50:
                logging.warning("ML 예측을 위한 충분한 데이터가 없습니다.")
                return combinations
            
            # 특징 추출 (예측기 타입에 따라)
            if hasattr(self.predictor, 'extract_features'):
                features = self.predictor.extract_features(winning_numbers)
                latest_features = features.iloc[-1:].values
                
                # 스케일링 (필요시)
                if hasattr(self.predictor, 'scalers') and hasattr(self.predictor.scalers.get('features'), 'transform'):
                    latest_features = self.predictor.scalers['features'].transform(latest_features)
                
                # 예측 확률 계산
                try:
                    pred_result = self.predictor.predict_probability(latest_features)
                    # 결과가 스칼라인 경우 배열로 변환
                    if np.isscalar(pred_result) or pred_result.ndim == 0:
                        probabilities = np.ones(45) / 45  # 균등 분포
                    else:
                        probabilities = pred_result[0] if pred_result.ndim > 1 else pred_result
                        # 45개 요소가 없으면 균등 분포 사용
                        if len(probabilities) != 45:
                            probabilities = np.ones(45) / 45
                except Exception as e:
                    logging.debug(f"예측 확률 계산 실패: {e}")
                    probabilities = np.ones(45) / 45  # 균등 분포
            else:
                # 기본 예측 방식
                probabilities = np.ones(45) / 45  # 균등 분포
            
            # numpy 벡터화 필터링
            threshold_normalized = self.threshold / 45

            # 조합을 numpy 배열로 일괄 변환
            combo_arrays = np.array(
                [list(map(int, c.split(','))) if isinstance(c, str) else list(c)
                 for c in combinations],
                dtype=np.int32
            )

            # 벡터화된 평균 확률 계산 (인덱스 -1로 0-based)
            combo_probs = np.mean(probabilities[combo_arrays - 1], axis=1)

            # 임계값 필터링
            valid_mask = combo_probs >= threshold_normalized
            filtered_combinations = [combinations[i] for i in range(len(combinations)) if valid_mask[i]]

            # 결과 로깅
            filtered_count = len(combinations) - len(filtered_combinations)
            if filtered_count > 0:
                logging.info(f"ML 예측 필터: {filtered_count}개 제외 "
                           f"({filtered_count/len(combinations)*100:.1f}%)")

            return filtered_combinations
            
        except Exception as e:
            # [filters-16-7] 필터가 예외로 "비활성화됨"을 상위 통계에서 구분할 수 있도록 신호 설정.
            # 이 플래그가 True면 아래 전체 통과 반환은 "정상 제거 0건"이 아니라 "필터 예외로 무력화"를 의미한다.
            # 안전상 전체 통과 폴백은 유지한다(청크 전체 손실 방지).
            self._apply_failed = True
            logging.error(f"ML 예측 필터 적용 중 오류: {str(e)}")
            logging.warning(
                f"[FILTER-DISABLED] {self.get_filter_name()} 필터가 예외로 비활성화됨 "
                f"(전체 {len(combinations):,}개 통과 폴백): {str(e)}"
            )
            return combinations
    
    def set_predictor(self, predictor):
        """예측기 설정
        
        Args:
            predictor: ML 예측기 인스턴스
        """
        self.predictor = predictor
        
    def set_threshold(self, threshold: float):
        """확률 임계값 설정
        
        Args:
            threshold: 확률 임계값 (0.0 ~ 1.0)
        """
        self.threshold = max(0.0, min(1.0, threshold))
    
    def _validate_criteria(self) -> bool:
        """기준값 유효성 검증
        
        Returns:
            bool: 유효 여부
        """
        # ML 필터는 특별한 기준값 검증이 필요 없음
        return True