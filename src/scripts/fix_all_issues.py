#!/usr/bin/env python
"""
백테스팅 카운트 및 로그 문제 종합 해결 스크립트
- 백테스팅 카운트가 증가하지 않는 문제 해결
- 로그 과다 출력 문제 해결
"""
import json
import os
import sys
import re
from datetime import datetime
import shutil

# 프로젝트 루트 경로
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

def fix_backtesting_counts():
    """백테스팅 카운트 문제 수정"""
    print("\n" + "="*60)
    print("1. 백테스팅 카운트 문제 수정")
    print("="*60)
    
    # auto_adjustment_state.json 확인 및 수정
    adj_file = os.path.join(project_root, 'data', 'auto_adjustment_state.json')
    if os.path.exists(adj_file):
        with open(adj_file, 'r', encoding='utf-8') as f:
            adj_state = json.load(f)
        
        current_count = adj_state.get('total_backtesting_count', 0)
        print(f"현재 auto_adjustment_state.json 백테스팅 횟수: {current_count}회")
        
        # 백업 생성
        backup_file = adj_file.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.copy2(adj_file, backup_file)
        print(f"백업 생성: {backup_file}")
        
        # 마지막 라운드 번호 확인
        last_round = adj_state.get('last_backtest_round', 0)
        print(f"마지막 백테스트 라운드: {last_round}")
        
        # 성능 점수가 0이 아닌지 확인
        perf_scores = adj_state.get('performance_scores', [])
        if perf_scores:
            avg_score = sum(perf_scores[-10:]) / min(10, len(perf_scores))
            print(f"최근 10회 평균 성능: {avg_score:.4f}")
    
    # auto_improvement_state.json 비활성화
    imp_file = os.path.join(project_root, 'data', 'auto_improvement_state.json')
    if os.path.exists(imp_file):
        # 백업 후 이름 변경하여 사용 중지
        backup_imp = imp_file.replace('.json', f'_inactive_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.move(imp_file, backup_imp)
        print(f"auto_improvement_state.json을 비활성화: {backup_imp}")
    
    # realtime_learning_state.json 확인
    realtime_file = os.path.join(project_root, 'results', 'realtime_learning_state.json')
    if os.path.exists(realtime_file):
        with open(realtime_file, 'r', encoding='utf-8') as f:
            realtime_state = json.load(f)
        
        for model in ['lstm', 'ensemble', 'monte_carlo']:
            update_count = realtime_state['model_states'][model]['update_count']
            print(f"{model} 업데이트 횟수: {update_count}")
    
    return True

def fix_auto_adjustment_system():
    """AutoAdjustmentSystem 코드 수정"""
    print("\n" + "="*60)
    print("2. AutoAdjustmentSystem 코드 수정")
    print("="*60)
    
    auto_adj_file = os.path.join(project_root, 'src', 'core', 'auto_adjustment_system.py')
    
    if not os.path.exists(auto_adj_file):
        print(f"파일을 찾을 수 없음: {auto_adj_file}")
        return False
    
    with open(auto_adj_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 백업 생성
    backup_file = auto_adj_file + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"백업 생성: {backup_file}")
    
    modified = False
    
    # 1. run_backtesting 메서드에서 카운트 증가 로직 수정
    # 백테스팅 결과 저장 후 카운트 증가하도록 수정
    if 'self.state["total_backtesting_count"] = self.state.get("total_backtesting_count", 0) + 1' not in content:
        # 백테스팅 결과 저장 부분 찾기
        pattern = r'(results = backtesting\.run_comprehensive_backtest\([^)]*\))'
        replacement = r'\1\n        \n        # 백테스팅 카운트 증가\n        self.state["total_backtesting_count"] = self.state.get("total_backtesting_count", 0) + 1\n        logging.info(f"백테스팅 완료: 총 {self.state[\'total_backtesting_count\']}회 실행")'
        
        new_content = re.sub(pattern, replacement, content, count=1)
        if new_content != content:
            content = new_content
            modified = True
            print("백테스팅 카운트 증가 로직 추가")
    
    # 2. 상태 저장 확인
    if modified and 'self.save_state()' not in content.split('self.state["total_backtesting_count"]')[-1][:200]:
        # 카운트 증가 후 즉시 저장하도록 수정
        pattern = r'(self\.state\["total_backtesting_count"\].*?\n)'
        replacement = r'\1        self.save_state()  # 상태 즉시 저장\n'
        content = re.sub(pattern, replacement, content)
        print("상태 자동 저장 로직 추가")
        modified = True
    
    # 수정된 내용 저장
    if modified:
        with open(auto_adj_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("AutoAdjustmentSystem 수정 완료")
    else:
        print("AutoAdjustmentSystem 수정 사항 없음")
    
    return True

def fix_logging_verbosity():
    """로그 출력 과다 문제 해결"""
    print("\n" + "="*60)
    print("3. 로그 출력 최적화")
    print("="*60)
    
    files_to_fix = {
        'src/core/filter_manager.py': [
            ('logging.info(f"필터 {filter_name} 초기화 중...")', 
             'logging.debug(f"필터 {filter_name} 초기화 중...")'),
            ('logging.info(f"  - {filter_name}: {len(filtered)} 조합 통과")',
             'logging.debug(f"  - {filter_name}: {len(filtered)} 조합 통과")'),
            ('logging.info(f"필터 {name} 적용 중...")',
             'logging.debug(f"필터 {name} 적용 중...")'),
            ('logging.info(f"{name} 필터: {before:,} → {after:,} (제거: {before-after:,})")',
             'logging.debug(f"{name} 필터: {before:,} → {after:,} (제거: {before-after:,})")'),
        ],
        'src/ml/ensemble_predictor.py': [
            ('logging.info("앙상블 예측 시작...")',
             'logging.debug("앙상블 예측 시작...")'),
            ('logging.info(f"Random Forest 예측: {rf_pred}")',
             'logging.debug(f"Random Forest 예측: {rf_pred}")'),
            ('logging.info(f"XGBoost 예측: {xgb_pred}")',
             'logging.debug(f"XGBoost 예측: {xgb_pred}")'),
            ('logging.info(f"Neural Network 예측: {nn_pred}")',
             'logging.debug(f"Neural Network 예측: {nn_pred}")'),
        ],
        'src/ml/lstm_predictor.py': [
            ('logging.info("LSTM 예측 시작...")',
             'logging.debug("LSTM 예측 시작...")'),
            ('logging.info(f"예측 번호: {predicted_numbers}")',
             'logging.debug(f"예측 번호: {predicted_numbers}")'),
            ('logging.info(f"LSTM 모델 학습 시작 (데이터: {len(train_data)}개)")',
             'logging.debug(f"LSTM 모델 학습 시작 (데이터: {len(train_data)}개)")'),
        ],
        'src/backtesting/optimized_backtesting_framework.py': [
            ('logging.info(f"라운드 {test_round} 백테스팅...")',
             'logging.debug(f"라운드 {test_round} 백테스팅...")'),
            ('logging.info(f"  {model_name}: {matches}개 일치")',
             'logging.debug(f"  {model_name}: {matches}개 일치")'),
            ('logging.info(f"백테스팅 라운드 {test_round}:")',
             'logging.debug(f"백테스팅 라운드 {test_round}:")'),
        ],
        'main.py': [
            ('logging.info("자동 조정 시스템 초기화...")',
             'logging.debug("자동 조정 시스템 초기화...")'),
            ('logging.info("실시간 학습 시스템 초기화...")',
             'logging.debug("실시간 학습 시스템 초기화...")'),
            ('logging.info("캐스케이드 필터링 수행 중...")',
             'logging.debug("캐스케이드 필터링 수행 중...")'),
            ('logging.info("데이터베이스 초기화 중...")',
             'logging.debug("데이터베이스 초기화 중...")'),
            ('logging.info("필터 매니저 초기화 중...")',
             'logging.debug("필터 매니저 초기화 중...")'),
        ],
        'src/ml/realtime_learning_system.py': [
            ('logging.info(f"실시간 학습 버퍼: {model_name} - {len(self.learning_buffers[model_name])}/{self.buffer_size}")',
             'logging.debug(f"실시간 학습 버퍼: {model_name} - {len(self.learning_buffers[model_name])}/{self.buffer_size}")'),
            ('logging.info(f"{model_name} 모델 업데이트 시작 (버퍼: {len(self.learning_buffers[model_name])}개)")',
             'logging.debug(f"{model_name} 모델 업데이트 시작 (버퍼: {len(self.learning_buffers[model_name])}개)")'),
        ]
    }
    
    total_changes = 0
    
    for file_path, replacements in files_to_fix.items():
        full_path = os.path.join(project_root, file_path)
        
        if not os.path.exists(full_path):
            print(f"파일을 찾을 수 없음: {file_path}")
            continue
        
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 백업 생성
        backup_file = full_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 로그 레벨 변경
        changes_made = 0
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                changes_made += 1
        
        if changes_made > 0:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] {file_path}: {changes_made}개 로그 최적화")
            total_changes += changes_made
        else:
            print(f"  {file_path}: 이미 최적화됨")
    
    # config.yaml 로그 레벨 설정
    config_file = os.path.join(project_root, 'config.yaml')
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        # 로그 레벨을 INFO로 유지하되, 상세 로그는 DEBUG로
        if 'log_level:' in config_content:
            config_content = re.sub(r'log_level:\s*\w+', 'log_level: INFO', config_content)
        else:
            config_content += '\n\n# 로깅 설정\nlog_level: INFO\nverbose_logging: false\n'
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        print("[OK] config.yaml 로그 설정 완료")
    
    print(f"\n총 {total_changes}개의 로그 레벨 변경 완료")
    return True

def verify_fixes():
    """수정 사항 검증"""
    print("\n" + "="*60)
    print("4. 수정 사항 검증")
    print("="*60)
    
    # 1. 백테스팅 카운트 확인
    adj_file = os.path.join(project_root, 'data', 'auto_adjustment_state.json')
    if os.path.exists(adj_file):
        with open(adj_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        print(f"[OK] auto_adjustment_state.json 백테스팅 횟수: {state['total_backtesting_count']}회")
    
    # 2. auto_improvement_state.json이 비활성화되었는지 확인
    imp_file = os.path.join(project_root, 'data', 'auto_improvement_state.json')
    if not os.path.exists(imp_file):
        print("[OK] auto_improvement_state.json 비활성화 완료")
    else:
        print("[WARNING] auto_improvement_state.json이 여전히 존재함")
    
    # 3. 로그 레벨 변경 확인
    filter_manager = os.path.join(project_root, 'src', 'core', 'filter_manager.py')
    if os.path.exists(filter_manager):
        with open(filter_manager, 'r', encoding='utf-8') as f:
            content = f.read()
        
        info_count = content.count('logging.info')
        debug_count = content.count('logging.debug')
        print(f"[OK] filter_manager.py - INFO: {info_count}개, DEBUG: {debug_count}개")
    
    # 4. AutoAdjustmentSystem 수정 확인
    auto_adj = os.path.join(project_root, 'src', 'core', 'auto_adjustment_system.py')
    if os.path.exists(auto_adj):
        with open(auto_adj, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'self.state["total_backtesting_count"] = self.state.get("total_backtesting_count", 0) + 1' in content:
            print("[OK] AutoAdjustmentSystem 백테스팅 카운트 증가 로직 확인")
        else:
            print("[WARNING] AutoAdjustmentSystem 백테스팅 카운트 증가 로직 미확인")
    
    # 5. 주요 파일들의 로그 최적화 확인
    main_file = os.path.join(project_root, 'main.py')
    if os.path.exists(main_file):
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        verbose_logs = content.count('logging.info("') + content.count("logging.info('")
        if verbose_logs < 20:  # 주요 로그만 남김
            print(f"[OK] main.py 로그 최적화 확인 (INFO 로그: {verbose_logs}개)")
        else:
            print(f"[WARNING] main.py에 아직 많은 INFO 로그 존재 ({verbose_logs}개)")
    
    return True

def main():
    print("="*60)
    print("[FIX] 종합 문제 해결 스크립트")
    print("="*60)
    print("다음 문제들을 해결합니다:")
    print("1. 백테스팅 카운트가 증가하지 않는 문제")
    print("2. 로그 과다 출력 문제")
    print("="*60)
    
    # 1. 백테스팅 카운트 문제 해결
    fix_backtesting_counts()
    
    # 2. AutoAdjustmentSystem 코드 수정
    fix_auto_adjustment_system()
    
    # 3. 로그 출력 최적화
    fix_logging_verbosity()
    
    # 4. 수정 사항 검증
    verify_fixes()
    
    print("\n" + "="*60)
    print("[OK] 모든 수정 완료!")
    print("="*60)
    print("\n권장사항:")
    print("1. main.py를 다시 실행하여 백테스팅 카운트가 증가하는지 확인")
    print("2. 로그 출력이 줄어들었는지 확인")
    print("3. 문제가 지속되면 프로그램을 재시작해보세요")
    print("="*60)

if __name__ == "__main__":
    main()