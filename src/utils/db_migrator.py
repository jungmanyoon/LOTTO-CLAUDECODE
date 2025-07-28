import os
import logging
import shutil
from typing import Optional, Dict, Any, Tuple
import datetime

from src.core.db_structure import DatabasePaths
from src.meta_data_manager import MetaDataManager


class DatabaseMigrator:
    """데이터베이스 마이그레이션 관리 클래스"""
    
    # 현재 코드베이스가 요구하는 DB 버전
    CURRENT_REQUIRED_VERSION = "2.0"
    
    # 스토리지 모드 변경이 필요할 때 초기화가 필요한지 여부
    STORAGE_MODE_REQUIRES_RESET = {
        ("legacy", "optimized"): True,   # legacy에서 optimized로 변경 시 초기화 필요
        ("optimized", "legacy"): True,   # optimized에서 legacy로 변경 시 초기화 필요
        ("legacy", "legacy"): False,     # 동일한 모드는 초기화 불필요
        ("optimized", "optimized"): False # 동일한 모드는 초기화 불필요
    }
    
    def __init__(self, meta_manager: Optional[MetaDataManager] = None):
        """DatabaseMigrator 초기화
        
        Args:
            meta_manager: 메타데이터 관리자 인스턴스 (기본값: None, 자동 생성)
        """
        self.meta_manager = meta_manager or MetaDataManager()
        self.db_paths = DatabasePaths()
        
    def check_compatibility(self) -> Tuple[bool, str]:
        """데이터베이스 호환성 검사
        
        Returns:
            Tuple[bool, str]: (호환 여부, 메시지)
        """
        try:
            # 현재 저장된 DB 버전 확인
            current_version = self.meta_manager.get_db_version()
            
            # 필요한 DB 버전과 호환되는지 확인
            if self.meta_manager.is_db_version_compatible(self.CURRENT_REQUIRED_VERSION):
                return True, f"데이터베이스 버전 {current_version}이(가) 호환됩니다."
            else:
                return False, f"데이터베이스 버전 {current_version}이(가) 필요한 버전 {self.CURRENT_REQUIRED_VERSION}과(와) 호환되지 않습니다."
        except Exception as e:
            # 오류 발생 시 호환되지 않는 것으로 간주
            logging.error(f"버전 호환성 검사 중 오류 발생: {str(e)}")
            return False, f"버전 호환성 검사 중 오류 발생: {str(e)}"
            
    def check_storage_mode_compatibility(self, target_mode: str) -> Tuple[bool, str]:
        """저장 모드 호환성 검사
        
        Args:
            target_mode: 대상 저장 모드 ('legacy' 또는 'optimized')
            
        Returns:
            Tuple[bool, str]: (호환 여부, 메시지)
        """
        try:
            current_mode = self.meta_manager.get_db_storage_mode()
            
            # 저장 모드가 변경되었는지, 그리고 초기화가 필요한지 확인
            mode_pair = (current_mode, target_mode)
            if mode_pair in self.STORAGE_MODE_REQUIRES_RESET:
                requires_reset = self.STORAGE_MODE_REQUIRES_RESET[mode_pair]
                
                if requires_reset:
                    return False, f"저장 모드를 {current_mode}에서 {target_mode}(으)로 변경하려면 데이터베이스 초기화가 필요합니다."
                else:
                    return True, f"저장 모드 {target_mode}이(가) 호환됩니다."
            else:
                # 알 수 없는 모드 조합은 초기화가 필요하다고 간주
                # 기본값 사용
                if current_mode == "legacy" and target_mode is None:
                    return True, "기본 저장 모드(legacy)를 사용합니다."
                return False, f"알 수 없는 저장 모드 조합 ({current_mode} -> {target_mode})입니다. 데이터베이스 초기화가 필요합니다."
        except Exception as e:
            # 오류 발생 시 호환되지 않는 것으로 간주
            logging.error(f"저장 모드 호환성 검사 중 오류 발생: {str(e)}")
            return False, f"저장 모드 호환성 검사 중 오류 발생: {str(e)}"
            
    def backup_database(self) -> bool:
        """데이터베이스 백업
        
        Returns:
            bool: 백업 성공 여부
        """
        try:
            # 백업 디렉토리 확인 및 생성
            backup_dir = os.path.join("data", "backup")
            try:
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir, exist_ok=True)
                    logging.info(f"백업 디렉토리 '{backup_dir}'를 생성했습니다.")
            except Exception as dir_err:
                logging.error(f"백업 디렉토리 생성 실패: {str(dir_err)}")
                # 백업 실패는 치명적이지 않으므로 계속 진행
                return False
                
            # 조합 DB 파일 백업
            combinations_path = self.db_paths.combinations
            if os.path.exists(combinations_path):
                try:
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = os.path.join(backup_dir, 
                                               f"combinations_backup_{self.meta_manager.get_db_version()}_{timestamp}.db")
                    shutil.copy2(combinations_path, backup_path)
                    logging.info(f"데이터베이스 백업 완료: {backup_path}")
                except Exception as copy_err:
                    logging.error(f"데이터베이스 파일 복사 실패: {str(copy_err)}")
                    # 백업 실패는 치명적이지 않으므로 계속 진행
            else:
                logging.warning(f"조합 DB 파일 '{combinations_path}'이 존재하지 않아 백업하지 않습니다.")
                
            # 메타데이터 백업
            meta_path = self.meta_manager.meta_file
            if os.path.exists(meta_path):
                try:
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_meta_path = os.path.join(backup_dir, 
                                                   f"meta_backup_{self.meta_manager.get_db_version()}_{timestamp}.json")
                    shutil.copy2(meta_path, backup_meta_path)
                    logging.info(f"메타데이터 백업 완료: {backup_meta_path}")
                except Exception as copy_err:
                    logging.error(f"메타데이터 파일 복사 실패: {str(copy_err)}")
                    # 백업 실패는 치명적이지 않으므로 계속 진행
            else:
                logging.warning(f"메타데이터 파일 '{meta_path}'이 존재하지 않아 백업하지 않습니다.")
                
            return True
            
        except Exception as e:
            logging.error(f"데이터베이스 백업 중 오류 발생: {str(e)}")
            # 백업 실패는 치명적이지 않으므로 계속 진행
            return False
            
    def reset_database(self) -> bool:
        """데이터베이스 초기화
        
        Returns:
            bool: 초기화 성공 여부
        """
        try:
            # 백업 먼저 수행
            backup_result = self.backup_database()
            if not backup_result:
                logging.warning("데이터베이스 백업에 실패했지만 초기화를 계속 진행합니다.")
            
            # 조합 DB 파일 삭제
            combinations_path = self.db_paths.combinations
            try:
                if os.path.exists(combinations_path):
                    # 파일이 사용 중인지 확인하는 방법은 없으므로 직접 삭제 시도
                    try:
                        os.remove(combinations_path)
                        logging.warning(f"조합 DB 파일 '{combinations_path}'을 삭제했습니다.")
                    except PermissionError:
                        logging.error(f"권한 오류: '{combinations_path}' 파일에 접근할 수 없습니다. 파일이 다른 프로세스에서 사용 중일 수 있습니다.")
                        return False
                    except FileNotFoundError:
                        logging.warning(f"파일을 찾을 수 없습니다: '{combinations_path}'")
                        # 파일이 없는 것은 오류가 아니므로 계속 진행
                    except Exception as e:
                        logging.error(f"파일 삭제 중 오류 발생: {str(e)}")
                        return False
                else:
                    logging.info(f"조합 DB 파일 '{combinations_path}'이 존재하지 않습니다.")
            except Exception as file_err:
                logging.error(f"파일 접근 중 오류 발생: {str(file_err)}")
                return False
                
            # 기본 조합 플래그 초기화
            try:
                delete_result = self.meta_manager.delete_meta('base_combinations_exist')
                if delete_result:
                    logging.info("기본 조합 생성 메타데이터를 초기화했습니다.")
                else:
                    logging.warning("기본 조합 생성 메타데이터 초기화가 불필요하거나 실패했습니다.")
                    # 메타데이터 초기화 실패는 치명적이지 않으므로 계속 진행
            except Exception as meta_err:
                logging.error(f"메타데이터 초기화 중 오류 발생: {str(meta_err)}")
                # 메타데이터 초기화 실패는 치명적이지 않으므로 계속 진행
                
            # DB 파일을 새로 생성하는 대신, 목록만 지우고 DB 매니저가 나중에 생성하도록 함
            return True
            
        except Exception as e:
            import traceback
            error_tb = traceback.format_exc()
            logging.error(f"데이터베이스 초기화 중 예상치 못한 오류 발생: {str(e)}")
            logging.error(f"상세 오류 정보: {error_tb}")
            return False
            
    def migrate_if_needed(self, target_storage_mode: Optional[str] = None) -> Tuple[bool, str]:
        """필요한 경우 데이터베이스 마이그레이션 수행
        
        Args:
            target_storage_mode: 원하는 저장 모드 (기본값: 현재 모드 유지)
            
        Returns:
            Tuple[bool, str]: (성공 여부, 메시지)
        """
        try:
            # 1. 버전 호환성 확인
            version_compatible, version_msg = self.check_compatibility()
            logging.debug(f"데이터베이스 버전 호환성 확인 결과: {version_compatible}, {version_msg}")
            
            # 2. 저장 모드 호환성 확인
            storage_mode = target_storage_mode or self.meta_manager.get_db_storage_mode()
            mode_compatible, mode_msg = self.check_storage_mode_compatibility(storage_mode)
            logging.debug(f"저장 모드 호환성 확인 결과: {mode_compatible}, {mode_msg}")
            
            # 초기화가 필요한지 여부 결정
            needs_reset = not version_compatible or not mode_compatible
            
            if needs_reset:
                # 메시지 생성
                message = ""
                if not version_compatible:
                    message += version_msg + " "
                if not mode_compatible:
                    message += mode_msg + " "
                    
                # 사용자에게 초기화가 필요함을 알림
                logging.warning(message.strip())
                logging.warning("데이터베이스 호환성 문제로 초기화가 필요합니다.")
                
                # 데이터베이스 초기화 수행
                if self.reset_database():
                    # 성공적으로 초기화된 경우 메타데이터 업데이트
                    update_result = self.meta_manager.update_db_info(
                        version=self.CURRENT_REQUIRED_VERSION,
                        storage_mode=storage_mode
                    )
                    
                    if not update_result:
                        logging.error("메타데이터 업데이트 실패")
                        return False, "데이터베이스는 초기화되었으나 메타데이터 업데이트에 실패했습니다."
                        
                    return True, "데이터베이스가 성공적으로 초기화되고 업데이트되었습니다."
                else:
                    return False, "데이터베이스 초기화 중 오류가 발생했습니다."
            else:
                # 저장 모드만 업데이트가 필요한 경우
                if target_storage_mode and target_storage_mode != self.meta_manager.get_db_storage_mode():
                    update_result = self.meta_manager.update_db_info(storage_mode=target_storage_mode)
                    if not update_result:
                        logging.error("저장 모드 업데이트 실패")
                        return False, f"저장 모드를 {target_storage_mode}(으)로 업데이트하는 데 실패했습니다."
                    return True, f"저장 모드가 {target_storage_mode}(으)로 업데이트되었습니다."
                
                # 이미 호환되는 경우
                return True, "데이터베이스가 이미 호환됩니다. 마이그레이션이 필요하지 않습니다."
        except Exception as e:
            import traceback
            error_tb = traceback.format_exc()
            logging.error(f"마이그레이션 과정에서 예외 발생: {str(e)}")
            logging.error(f"상세 오류: {error_tb}")
            return False, f"마이그레이션 과정에서 예외 발생: {str(e)}" 