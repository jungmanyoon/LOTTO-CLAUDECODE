"""
결과 검증 시스템 (스텁 구현)
"""
import logging
from typing import List, Dict, Any, Tuple


class ResultValidator:
    """예측 결과 검증 클래스"""
    
    def __init__(self):
        """결과 검증기 초기화"""
        self.validation_rules = {
            'number_range': (1, 45),
            'combination_size': 6,
            'no_duplicates': True,
            'sorted_order': True
        }
        logging.info("ResultValidator 초기화 (스텁)")
    
    def validate_combination(self, numbers: List[int]) -> Tuple[bool, List[str]]:
        """단일 조합 검증"""
        errors = []
        
        # 개수 체크
        if len(numbers) != self.validation_rules['combination_size']:
            errors.append(f"잘못된 번호 개수: {len(numbers)} (6개여야 함)")
        
        # 범위 체크
        min_num, max_num = self.validation_rules['number_range']
        for num in numbers:
            if not (min_num <= num <= max_num):
                errors.append(f"범위 벗어남: {num} ({min_num}-{max_num} 사이여야 함)")
        
        # 중복 체크
        if self.validation_rules['no_duplicates'] and len(numbers) != len(set(numbers)):
            errors.append("중복된 번호 존재")
        
        # 정렬 체크
        if self.validation_rules['sorted_order'] and numbers != sorted(numbers):
            errors.append("번호가 정렬되지 않음")
        
        return len(errors) == 0, errors
    
    def validate_predictions(self, predictions: List[List[int]]) -> Dict[str, Any]:
        """예측 결과 전체 검증"""
        results = {
            'valid': True,
            'total': len(predictions),
            'valid_count': 0,
            'invalid_count': 0,
            'errors': []
        }
        
        for i, combination in enumerate(predictions):
            is_valid, errors = self.validate_combination(combination)
            if is_valid:
                results['valid_count'] += 1
            else:
                results['invalid_count'] += 1
                results['errors'].append({
                    'index': i,
                    'combination': combination,
                    'errors': errors
                })
        
        results['valid'] = results['invalid_count'] == 0
        return results
    
    def validate_filter_results(self, filtered_combinations: List[str]) -> bool:
        """필터링 결과 검증"""
        if not filtered_combinations:
            logging.warning("필터링 결과가 비어있음")
            return False
        
        # 샘플 검증
        sample_size = min(100, len(filtered_combinations))
        for combo_str in filtered_combinations[:sample_size]:
            try:
                numbers = [int(n) for n in combo_str.split(',')]
                is_valid, _ = self.validate_combination(numbers)
                if not is_valid:
                    return False
            except Exception as e:
                logging.error(f"조합 파싱 오류: {combo_str} - {e}")
                return False
        
        return True