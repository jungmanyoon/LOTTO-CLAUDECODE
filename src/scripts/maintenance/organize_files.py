"""
파일 정리 자동화 스크립트

프로젝트 파일들을 적절한 위치로 자동 정리합니다.
"""

import os
import shutil
import glob
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProjectOrganizer:
    """프로젝트 파일 정리 클래스"""
    
    def __init__(self, project_root='.'):
        self.project_root = os.path.abspath(project_root)
        self.moves = []  # 이동된 파일 기록
        self.deletions = []  # 삭제된 파일 기록
        
        # 필요한 디렉토리 정의
        self.directories = {
            'scripts': 'src/scripts',
            'tests': 'tests',
            'maintenance': 'src/scripts/maintenance',
            'configs': 'configs',
            'output': 'output',
            'charts': 'output/charts',
            'results': 'results',
            'temp': 'temp'
        }
        
        # 파일 이동 규칙
        self.rules = [
            # 테스트 파일
            {'pattern': 'test_*.py', 'destination': 'tests'},
            {'pattern': '*_test.py', 'destination': 'tests'},
            
            # 스크립트 파일
            {'pattern': 'analyze_*.py', 'destination': 'scripts'},
            {'pattern': 'extract_*.py', 'destination': 'scripts'},
            {'pattern': 'apply_*.py', 'destination': 'scripts'},
            {'pattern': 'optimize_*.py', 'destination': 'scripts'},
            {'pattern': 'sample_*.py', 'destination': 'scripts'},
            {'pattern': '*_optimizer.py', 'destination': 'scripts'},
            {'pattern': '*_integrator.py', 'destination': 'scripts'},
            
            # 유지보수 스크립트
            {'pattern': 'fix_*.py', 'destination': 'maintenance'},
            {'pattern': 'clean_*.py', 'destination': 'maintenance'},
            {'pattern': 'migrate_*.py', 'destination': 'maintenance'},
            
            # 설정 파일
            {'pattern': 'config_*.yaml', 'destination': 'configs'},
            {'pattern': 'config_*.yml', 'destination': 'configs'},
            
            # 출력 파일
            {'pattern': '*.txt', 'destination': 'output'},
            {'pattern': '*.png', 'destination': 'charts'},
            {'pattern': '*.jpg', 'destination': 'charts'},
            {'pattern': '*.jpeg', 'destination': 'charts'},
            
            # 결과 파일
            {'pattern': '*_result.json', 'destination': 'results'},
            {'pattern': '*_results.json', 'destination': 'results'},
            {'pattern': '*_report.json', 'destination': 'results'},
            {'pattern': 'predictions_*.json', 'destination': 'results'},
            {'pattern': 'recommendations_*.json', 'destination': 'results'},
            {'pattern': 'bayesian_beliefs.json', 'destination': 'results'},
            {'pattern': 'fractal_analysis.json', 'destination': 'results'},
            {'pattern': 'filter_performance_report.json', 'destination': 'results'},
            
            # 이미지 파일
            {'pattern': 'bayesian_beliefs.png', 'destination': 'charts'},
            {'pattern': 'fractal_analysis.png', 'destination': 'charts'},
        ]
        
        # 루트에 허용된 파일
        self.allowed_in_root = [
            'main.py',
            'requirements.txt',
            'config.yaml',
            'README.md',
            'CLAUDE.md',
            '.gitignore',
            'LICENSE',
            'setup.py',
            'pyproject.toml'
        ]
        
        # 삭제해야 할 파일들
        self.files_to_delete = [
            '=3.0.0',
            'nul',
            'test_output.txt',
            'test_log_clean_start.py',
            'test_main_log.py'
        ]
        
        # 초창기 MD 파일들 (docs로 이동 또는 삭제)
        self.old_md_files = [
            'INFINITE_LOOP_FIX.md',
            'ML_AI_통합_완료.md',
            'INSTALL_GUIDE.md'
        ]
        
        # 백업 파일 패턴
        self.backup_patterns = [
            'config_backup_*.yaml',
            'config_backup_*.yml',
            '*_backup_*.json',
            'temp_*.json'
        ]
        
    def ensure_directories(self):
        """필요한 디렉토리 생성"""
        for name, path in self.directories.items():
            full_path = os.path.join(self.project_root, path)
            if not os.path.exists(full_path):
                os.makedirs(full_path)
                logger.info(f"디렉토리 생성: {path}")
                
    def move_file(self, source, destination):
        """파일 이동"""
        src_path = os.path.join(self.project_root, source)
        dst_dir = os.path.join(self.project_root, self.directories[destination])
        dst_path = os.path.join(dst_dir, os.path.basename(source))
        
        if os.path.exists(src_path) and not os.path.exists(dst_path):
            shutil.move(src_path, dst_path)
            self.moves.append((source, dst_path))
            logger.info(f"파일 이동: {source} -> {dst_path}")
            return True
        return False
        
    def clean_temp_files(self):
        """임시 파일 삭제"""
        temp_patterns = [
            '*.pyc',
            '__pycache__',
            '.pytest_cache',
            '*.tmp',
            '*.temp',
            '.DS_Store',
            'Thumbs.db'
        ]
        
        for pattern in temp_patterns:
            for file_path in glob.glob(os.path.join(self.project_root, '**', pattern), recursive=True):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    self.deletions.append(file_path)
                    logger.info(f"임시 파일 삭제: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    self.deletions.append(file_path)
                    logger.info(f"임시 디렉토리 삭제: {file_path}")
                    
    def delete_specific_files(self):
        """특정 파일 삭제"""
        for file_name in self.files_to_delete:
            file_path = os.path.join(self.project_root, file_name)
            if os.path.exists(file_path):
                try:
                    # nul 파일은 Windows에서 특수 파일이므로 특별한 처리 필요
                    if file_name == 'nul':
                        # Windows에서 nul 파일 삭제
                        import subprocess
                        subprocess.run(['del', '/f', file_path], shell=True, check=False)
                    else:
                        os.remove(file_path)
                    self.deletions.append(file_path)
                    logger.info(f"파일 삭제: {file_name}")
                except Exception as e:
                    logger.warning(f"파일 삭제 실패 {file_name}: {str(e)}")
                
    def handle_old_md_files(self):
        """초창기 MD 파일 처리"""
        docs_dir = os.path.join(self.project_root, 'docs', 'archive')
        os.makedirs(docs_dir, exist_ok=True)
        
        for md_file in self.old_md_files:
            src_path = os.path.join(self.project_root, md_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(docs_dir, md_file)
                shutil.move(src_path, dst_path)
                self.moves.append((md_file, dst_path))
                logger.info(f"MD 파일 아카이브: {md_file} -> docs/archive/")
                
    def clean_backup_files(self):
        """백업 파일 정리 (30일 이상된 것 삭제)"""
        import time
        current_time = time.time()
        for pattern in self.backup_patterns:
            for file_path in glob.glob(os.path.join(self.project_root, pattern)):
                if os.path.isfile(file_path):
                    # 파일 수정 시간 확인
                    file_mtime = os.path.getmtime(file_path)
                    if current_time - file_mtime > 30 * 24 * 3600:  # 30일 이상
                        os.remove(file_path)
                        self.deletions.append(file_path)
                        logger.info(f"오래된 백업 삭제: {os.path.basename(file_path)}")
                    else:
                        # 30일 이내면 backup 디렉토리로 이동
                        backup_dir = os.path.join(self.project_root, 'configs', 'backup')
                        os.makedirs(backup_dir, exist_ok=True)
                        dst_path = os.path.join(backup_dir, os.path.basename(file_path))
                        if not os.path.exists(dst_path):
                            shutil.move(file_path, dst_path)
                            self.moves.append((file_path, dst_path))
                            logger.info(f"백업 파일 이동: {os.path.basename(file_path)}")
    
    def organize_files(self):
        """파일 정리 실행"""
        logger.info("="*60)
        logger.info("파일 정리 시작...")
        
        # 1. 디렉토리 확인/생성
        self.ensure_directories()
        
        # 2. 특정 파일 삭제
        self.delete_specific_files()
        
        # 3. 초창기 MD 파일 처리
        self.handle_old_md_files()
        
        # 4. 백업 파일 정리
        self.clean_backup_files()
        
        # 5. 루트 디렉토리의 파일 확인
        root_files = [f for f in os.listdir(self.project_root) 
                     if os.path.isfile(os.path.join(self.project_root, f))]
        
        # 6. 규칙에 따라 파일 이동
        for rule in self.rules:
            pattern = rule['pattern']
            destination = rule['destination']
            
            for file_name in root_files:
                if glob.fnmatch.fnmatch(file_name, pattern):
                    if file_name not in self.allowed_in_root:
                        self.move_file(file_name, destination)
                        
        # 7. 임시 파일 정리
        self.clean_temp_files()
        
        # 8. 중복 MD 파일 처리
        self.check_duplicate_md_files()
        
        # 9. 결과 보고
        self.print_report()
        
    def check_duplicate_md_files(self):
        """중복된 MD 파일 확인 및 정리"""
        # 슈퍼클로드 MD 파일 중복 확인
        root_sc = os.path.join(self.project_root, '슈퍼클로드_설치방법_및_주요명령어.md')
        docs_sc = os.path.join(self.project_root, 'docs', '슈퍼클로드_설치방법_및_주요명령어.md')
        
        if os.path.exists(root_sc) and os.path.exists(docs_sc):
            # 루트의 파일 삭제
            os.remove(root_sc)
            self.deletions.append(root_sc)
            logger.info(f"중복 MD 파일 삭제: 슈퍼클로드_설치방법_및_주요명령어.md (루트)")
        
    def print_report(self):
        """정리 결과 보고"""
        logger.info("\n" + "="*60)
        logger.info("파일 정리 완료!")
        logger.info("="*60)
        
        if self.moves:
            logger.info(f"\n이동된 파일: {len(self.moves)}개")
            for src, dst in self.moves[:10]:  # 처음 10개만 표시
                logger.info(f"  - {src} -> {os.path.basename(dst)}")
            if len(self.moves) > 10:
                logger.info(f"  ... 그리고 {len(self.moves) - 10}개 더")
                
        if self.deletions:
            logger.info(f"\n삭제된 파일: {len(self.deletions)}개")
            
        # 현재 루트 상태
        root_files = [f for f in os.listdir(self.project_root) 
                     if os.path.isfile(os.path.join(self.project_root, f))]
        logger.info(f"\n현재 루트 디렉토리 파일 수: {len(root_files)}개")
        
        # 보고서 저장
        report_path = os.path.join(self.project_root, 'temp', 
                                  f'organize_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"파일 정리 보고서\n")
            f.write(f"생성 시간: {datetime.now()}\n\n")
            f.write(f"이동된 파일: {len(self.moves)}개\n")
            f.write(f"삭제된 파일: {len(self.deletions)}개\n\n")
            
            if self.moves:
                f.write("이동 내역:\n")
                for src, dst in self.moves:
                    f.write(f"  {src} -> {dst}\n")
                    
        logger.info(f"\n보고서 저장: {report_path}")
        
    def check_status(self):
        """현재 파일 구조 상태 확인"""
        issues = []
        
        # 루트에 있으면 안 되는 파일 확인
        root_files = [f for f in os.listdir(self.project_root) 
                     if os.path.isfile(os.path.join(self.project_root, f))]
        
        for file_name in root_files:
            if file_name not in self.allowed_in_root:
                # 패턴 확인
                for rule in self.rules:
                    if glob.fnmatch.fnmatch(file_name, rule['pattern']):
                        issues.append(f"{file_name} -> {self.directories[rule['destination']]}")
                        break
                        
        if issues:
            logger.warning(f"\n정리가 필요한 파일: {len(issues)}개")
            for issue in issues[:5]:
                logger.warning(f"  - {issue}")
            if len(issues) > 5:
                logger.warning(f"  ... 그리고 {len(issues) - 5}개 더")
        else:
            logger.info("\n파일 구조가 깨끗합니다!")
            
        return len(issues) == 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='프로젝트 파일 정리 도구')
    parser.add_argument('--check', action='store_true', help='현재 상태만 확인')
    parser.add_argument('--dry-run', action='store_true', help='실제 이동 없이 시뮬레이션')
    args = parser.parse_args()
    
    # 프로젝트 루트 찾기 (CLAUDE.md가 있는 디렉토리)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = current_dir
    
    # 상위 디렉토리로 올라가면서 CLAUDE.md 찾기
    for _ in range(5):  # 최대 5단계까지만
        if os.path.exists(os.path.join(project_root, 'CLAUDE.md')):
            break
        parent = os.path.dirname(project_root)
        if parent == project_root:  # 루트 디렉토리에 도달
            break
        project_root = parent
        
    organizer = ProjectOrganizer(project_root)
    
    if args.check:
        # 상태 확인만
        organizer.check_status()
    else:
        # 파일 정리 실행
        organizer.organize_files()
