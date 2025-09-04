#!/usr/bin/env python3
"""
필터 검증 시스템 테스트 스크립트
"""
import sys
import os

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.validators.filter_validator import FilterValidator
from src.logger import setup_logging
import logging

def main():
    """필터 검증 테스트 실행"""
    setup_logging()
    
    logging.info("="*60)
    logging.info("필터 검증 시스템 테스트 시작")
    logging.info("="*60)
    
    # 검증 시스템 초기화
    validator = FilterValidator()
    
    # 최근 100회차 검증 (1083~1182회차)
    logging.info("\n[1단계] 최근 100회차 당첨번호로 필터 검증")
    results = validator.validate_filters_with_historical_data(start_round=1083, end_round=1182)
    
    # 전체 통과율이 낮으면 필터 최적화 제안
    if results['overall_pass_rate'] < 90:
        logging.info("\n[2단계] 필터 최적화 제안")
        optimized = validator.optimize_filter_thresholds(target_pass_rate=0.95)
        
        logging.info("\n[최적화된 필터 설정 제안]")
        for filter_name, criteria in optimized.items():
            logging.info(f"{filter_name}: {criteria}")
        
        # config.yaml에 자동 반영 옵션 제공
        logging.info("\n[config.yaml 자동 업데이트]")
        user_input = input("최적화된 설정을 config.yaml에 자동으로 반영하시겠습니까? (y/n): ")
        
        if user_input.lower() == 'y':
            if validator.apply_optimized_settings_to_config(optimized):
                logging.info("✅ config.yaml이 성공적으로 업데이트되었습니다.")
            else:
                logging.error("❌ config.yaml 업데이트에 실패했습니다.")
        else:
            # 수동 업데이트를 위한 가이드 제공
            logging.info("\n[수동 업데이트 가이드]")
            logging.info("다음 설정을 config.yaml에 수동으로 반영하세요:")
            logging.info("```yaml")
            logging.info("filters:")
            logging.info("  criteria:")
            for filter_name, criteria in optimized.items():
                logging.info(f"    {filter_name}:")
                for key, value in criteria.items():
                    logging.info(f"      {key}: {value}")
            logging.info("```")
    else:
        logging.info(f"\n✅ 현재 필터 설정이 적절합니다. (통과율: {results['overall_pass_rate']:.2f}%)")
    
    logging.info("\n테스트 완료!")


if __name__ == "__main__":
    main()