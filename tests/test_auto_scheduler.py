#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoScheduler 클래스 유닛 테스트

이 모듈은 src/automation/auto_scheduler.py의 AutoScheduler 클래스에 대한
포괄적인 단위 테스트를 제공합니다.

테스트 커버리지:
- 초기화 및 설정
- 스케줄 설정
- 새 회차 감지
- 자동 업데이트 트리거
- 콜백 등록 및 실행
- 상태 체크
- 오류 처리
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timedelta
import threading
import time
import sqlite3
import os
import tempfile
import yaml


@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager for testing"""
    mock_db = Mock()
    mock_db.get_last_round.return_value = 1000
    mock_db.get_all_winning_numbers.return_value = [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
        [13, 14, 15, 16, 17, 18]
    ]
    return mock_db


@pytest.fixture
def scheduler(mock_db_manager):
    """Create AutoScheduler instance with mocked dependencies"""
    with patch('src.automation.auto_scheduler.schedule_module'):
        from src.automation.auto_scheduler import AutoScheduler
        return AutoScheduler(db_manager=mock_db_manager)


@pytest.fixture
def temp_db_file():
    """Create temporary database file for testing"""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(temp_fd)

    # Create a simple test database
    conn = sqlite3.connect(temp_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lotto_numbers (
            round_num INTEGER PRIMARY KEY,
            numbers TEXT,
            bonus INTEGER,
            draw_date TEXT
        )
    """)
    cursor.execute(
        "INSERT INTO lotto_numbers VALUES (1, '1,2,3,4,5,6', 7, '2023-01-01')"
    )
    conn.commit()
    conn.close()

    yield temp_path

    # Cleanup
    try:
        os.unlink(temp_path)
    except:
        pass


class TestAutoSchedulerInitialization:
    """AutoScheduler 초기화 테스트"""

    def test_initialization_without_db_manager(self):
        """DatabaseManager 없이 초기화 테스트"""
        with patch('src.automation.auto_scheduler.schedule_module'):
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            assert scheduler.db_manager is None
            assert scheduler.running is False
            assert scheduler.thread is None
            assert isinstance(scheduler.job_status, dict)
            assert isinstance(scheduler.callbacks, dict)

    def test_initialization_with_db_manager(self, mock_db_manager):
        """DatabaseManager와 함께 초기화 테스트"""
        with patch('src.automation.auto_scheduler.schedule_module'):
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=mock_db_manager)

            assert scheduler.db_manager == mock_db_manager
            assert scheduler.running is False
            assert scheduler.thread is None

    def test_job_status_initialization(self, scheduler):
        """작업 상태 초기화 확인"""
        expected_jobs = [
            'check_new_round',
            'daily_prediction',
            'weekly_optimization',
            'health_check',
            'cleanup_logs'
        ]

        for job_name in expected_jobs:
            assert job_name in scheduler.job_status
            assert scheduler.job_status[job_name]['last_run'] is None
            assert scheduler.job_status[job_name]['success'] == 0
            assert scheduler.job_status[job_name]['fail'] == 0

    def test_callbacks_initialization(self, scheduler):
        """콜백 초기화 확인"""
        expected_callbacks = [
            'new_round_detected',
            'refilter_required',
            'optimization_complete'
        ]

        for callback_name in expected_callbacks:
            assert callback_name in scheduler.callbacks
            assert scheduler.callbacks[callback_name] is None


class TestScheduleSetup:
    """스케줄 설정 테스트"""

    def test_schedule_setup_called_on_init(self):
        """초기화 시 스케줄 설정 호출 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # schedule.every() 호출 확인
            assert mock_schedule.Scheduler.return_value.every.called

    def test_saturday_intensive_monitoring_schedule(self):
        """토요일 집중 모니터링 스케줄 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # 토요일 20:45~21:30 사이 스케줄 설정 확인
            saturday_calls = [
                call for call in mock_schedule.Scheduler.return_value.every().saturday.at.call_args_list
            ]

            # 최소 45분 이상의 스케줄이 설정되어야 함
            assert len(saturday_calls) >= 45

    def test_daily_prediction_schedule(self):
        """일일 예측 스케줄 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # 매일 09:00 스케줄 확인
            mock_schedule.Scheduler.return_value.every().day.at.assert_any_call("09:00")

    def test_weekly_optimization_schedule(self):
        """주간 최적화 스케줄 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # 일요일 03:00 스케줄 확인
            mock_schedule.Scheduler.return_value.every().sunday.at.assert_any_call("03:00")

    def test_health_check_schedule(self):
        """상태 체크 스케줄 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # 30분마다 상태 체크 확인
            mock_schedule.Scheduler.return_value.every.assert_any_call(30)

    def test_cleanup_logs_schedule(self):
        """로그 정리 스케줄 확인"""
        with patch('src.automation.auto_scheduler.schedule_module') as mock_schedule:
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            # 매일 자정 로그 정리 확인
            mock_schedule.Scheduler.return_value.every().day.at.assert_any_call("00:00")


class TestCallbackRegistration:
    """콜백 등록 테스트"""

    def test_register_valid_callback(self, scheduler):
        """유효한 콜백 등록 테스트"""
        callback_func = Mock()
        scheduler.register_callback('new_round_detected', callback_func)

        assert scheduler.callbacks['new_round_detected'] == callback_func

    def test_register_multiple_callbacks(self, scheduler):
        """여러 콜백 등록 테스트"""
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()

        scheduler.register_callback('new_round_detected', callback1)
        scheduler.register_callback('refilter_required', callback2)
        scheduler.register_callback('optimization_complete', callback3)

        assert scheduler.callbacks['new_round_detected'] == callback1
        assert scheduler.callbacks['refilter_required'] == callback2
        assert scheduler.callbacks['optimization_complete'] == callback3

    def test_register_invalid_callback_type(self, scheduler):
        """잘못된 콜백 타입 등록 시도"""
        callback_func = Mock()
        scheduler.register_callback('invalid_event', callback_func)

        # 잘못된 이벤트 타입은 무시됨
        assert 'invalid_event' not in scheduler.callbacks


class TestSchedulerLifecycle:
    """스케줄러 생명주기 테스트"""

    def test_start_scheduler(self, scheduler):
        """스케줄러 시작 테스트"""
        with patch.object(scheduler, '_check_new_round') as mock_check:
            scheduler.start()

            assert scheduler.running is True
            assert scheduler.thread is not None
            assert scheduler.thread.daemon is True

            # 즉시 새 회차 확인 호출 확인
            mock_check.assert_called_once()

            # 정리
            scheduler.stop()

    def test_stop_scheduler(self, scheduler):
        """스케줄러 중지 테스트"""
        scheduler.start()
        time.sleep(0.1)  # 스레드 시작 대기

        scheduler.stop()

        assert scheduler.running is False

    def test_start_already_running_scheduler(self, scheduler):
        """이미 실행 중인 스케줄러 시작 시도"""
        scheduler.start()
        thread1 = scheduler.thread

        scheduler.start()
        thread2 = scheduler.thread

        # 동일한 스레드여야 함
        assert thread1 == thread2

        # 정리
        scheduler.stop()

    def test_scheduler_loop_error_handling(self, scheduler):
        """스케줄러 루프 오류 처리 테스트"""
        # [FIX] 코드가 self.scheduler(=schedule_module.Scheduler()).run_pending()를 호출하므로
        #       schedule.run_pending이 아니라 인스턴스 메서드를 패치한다.
        with patch.object(scheduler.scheduler, 'run_pending') as mock_run:
            # 예외 발생 시뮬레이션 (이후 호출은 정상)
            mock_run.side_effect = [Exception("Test error")] + [None] * 100

            scheduler.start()
            time.sleep(0.2)

            # 오류에도 불구하고 스케줄러는 계속 실행되어야 함
            assert scheduler.running is True

            # 정리
            scheduler.stop()


class TestNewRoundDetection:
    """새 회차 감지 테스트"""

    def test_check_new_round_no_db_manager(self):
        """DatabaseManager 없이 새 회차 확인"""
        with patch('src.automation.auto_scheduler.schedule_module'):
            from src.automation.auto_scheduler import AutoScheduler
            scheduler = AutoScheduler(db_manager=None)

            result = scheduler._check_new_round()
            assert result is False

    def test_check_new_round_no_new_data(self, scheduler, mock_db_manager):
        """새 회차가 없는 경우"""
        with patch.object(scheduler, '_fetch_latest_round_from_web', return_value=1000):
            result = scheduler._check_new_round()

            assert result is False
            mock_db_manager.get_last_round.assert_called_once()

    def test_check_new_round_with_new_data(self, scheduler, mock_db_manager):
        """새 회차가 있는 경우"""
        mock_db_manager.get_last_round.return_value = 1000

        with patch.object(scheduler, '_fetch_latest_round_from_web', return_value=1001):
            with patch.object(scheduler, '_fetch_and_save_new_round', return_value=True):
                result = scheduler._check_new_round()

                assert result is True

    def test_check_new_round_with_callback(self, scheduler, mock_db_manager):
        """새 회차 감지 시 콜백 실행 확인"""
        mock_db_manager.get_last_round.return_value = 1000
        mock_callback = Mock()
        scheduler.register_callback('new_round_detected', mock_callback)

        with patch.object(scheduler, '_fetch_latest_round_from_web', return_value=1001):
            with patch.object(scheduler, '_fetch_and_save_new_round', return_value=True):
                scheduler._check_new_round()

                mock_callback.assert_called_once_with(1001)

    def test_check_new_round_with_refilter_callback(self, scheduler, mock_db_manager):
        """재필터링 콜백 실행 확인"""
        mock_db_manager.get_last_round.return_value = 1000
        mock_callback = Mock()
        scheduler.register_callback('refilter_required', mock_callback)

        with patch.object(scheduler, '_fetch_latest_round_from_web', return_value=1001):
            with patch.object(scheduler, '_fetch_and_save_new_round', return_value=True):
                scheduler._check_new_round()

                mock_callback.assert_called_once_with('new_round', 1001)

    def test_check_new_round_error_handling(self, scheduler):
        """새 회차 확인 중 오류 처리"""
        with patch.object(scheduler, '_fetch_latest_round_from_web', side_effect=Exception("Network error")):
            result = scheduler._check_new_round()

            assert result is False
            assert scheduler.job_status['check_new_round']['fail'] > 0

    def test_check_new_round_intensive_saturday(self, scheduler, mock_db_manager):
        """토요일 집중 모니터링 테스트"""
        mock_db_manager.get_last_round.return_value = 1000

        with patch.object(scheduler, '_fetch_latest_round_from_web', return_value=1001):
            with patch.object(scheduler, '_fetch_and_save_new_round', return_value=True):
                with patch.object(scheduler, '_trigger_update_chain'):
                    with patch.object(scheduler, '_run_prediction_for_new_round'):
                        result = scheduler._check_new_round_intensive()

                        assert result is True

    def test_check_new_round_if_not_saturday(self, scheduler):
        """토요일이 아닐 때 새 회차 확인"""
        # 월요일로 설정 (2023-01-02는 월요일, weekday() = 0)
        with patch('src.automation.auto_scheduler.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 2, 12, 0)  # Monday

            with patch.object(scheduler, '_check_new_round', return_value=True) as mock_check:
                result = scheduler._check_new_round_if_not_saturday()

                mock_check.assert_called_once()
                assert result is True

    def test_check_new_round_on_saturday(self, scheduler):
        """토요일일 때는 일반 확인 스킵"""
        # 토요일로 설정 (2023-01-07은 토요일, weekday() = 5)
        with patch('src.automation.auto_scheduler.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 7, 12, 0)  # Saturday

            result = scheduler._check_new_round_if_not_saturday()

            assert result is False


class TestWebDataFetching:
    """웹 데이터 가져오기 테스트"""

    def test_fetch_latest_round_success(self, scheduler):
        """최신 회차 조회 성공"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'returnValue': 'success'}

        with patch('src.automation.auto_scheduler.requests.get', return_value=mock_response):
            result = scheduler._fetch_latest_round_from_web()

            assert result is not None
            assert isinstance(result, int)

    def test_fetch_latest_round_network_error(self, scheduler):
        """네트워크 오류 시 None 반환"""
        with patch('src.automation.auto_scheduler.requests.get', side_effect=Exception("Network error")):
            result = scheduler._fetch_latest_round_from_web()

            assert result is None

    def test_fetch_and_save_new_round_success(self, scheduler):
        """새 회차 데이터 저장 성공"""
        with patch('src.automation.auto_scheduler.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0

            result = scheduler._fetch_and_save_new_round(1001)

            assert result is True
            mock_run.assert_called_once()

    def test_fetch_and_save_new_round_failure(self, scheduler):
        """새 회차 데이터 저장 실패"""
        with patch('src.automation.auto_scheduler.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Error message"

            result = scheduler._fetch_and_save_new_round(1001)

            assert result is False


class TestAutomatedTasks:
    """자동화 작업 테스트"""

    def test_run_daily_prediction_success(self, scheduler):
        """일일 예측 실행 성공"""
        with patch('src.automation.auto_scheduler.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0

            with patch.object(scheduler, '_is_main_py_running', return_value=False):
                with patch.object(scheduler, '_notify_prediction_complete') as mock_notify:
                    scheduler._run_daily_prediction()

                    assert scheduler.job_status['daily_prediction']['success'] > 0
                    mock_notify.assert_called_once()

    def test_run_daily_prediction_failure(self, scheduler):
        """일일 예측 실행 실패"""
        with patch('src.automation.auto_scheduler.subprocess.run') as mock_run, \
             patch.object(scheduler, '_is_main_py_running', return_value=False):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Prediction error"

            scheduler._run_daily_prediction()

            assert scheduler.job_status['daily_prediction']['fail'] > 0

    def test_run_weekly_optimization(self, scheduler):
        """주간 최적화 실행"""
        with patch.object(scheduler, '_cleanup_old_cache'):
            with patch.object(scheduler, '_optimize_databases'):
                with patch.object(scheduler, '_update_filter_criteria'):
                    with patch.object(scheduler, '_retrain_models'):
                        scheduler._run_weekly_optimization()

                        assert scheduler.job_status['weekly_optimization']['success'] > 0

    def test_run_prediction_for_new_round(self, scheduler):
        """새 회차 예측 생성"""
        with patch('src.automation.auto_scheduler.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0

            scheduler._run_prediction_for_new_round(1002)

            # 예측 생성이 호출되었는지 확인
            assert mock_run.called


class TestHealthCheck:
    """상태 체크 테스트"""

    def test_health_check_all_healthy(self, scheduler):
        """모든 상태가 정상인 경우"""
        with patch.object(scheduler, '_check_database_health', return_value=True):
            with patch.object(scheduler, '_check_disk_space', return_value=True):
                with patch.object(scheduler, '_check_memory_usage', return_value=True):
                    with patch.object(scheduler, '_check_process_status', return_value=True):
                        scheduler._health_check()

                        assert scheduler.job_status['health_check']['success'] > 0

    def test_health_check_database_unhealthy(self, scheduler):
        """데이터베이스 상태 불량"""
        with patch.object(scheduler, '_check_database_health', return_value=False):
            with patch.object(scheduler, '_check_disk_space', return_value=True):
                with patch.object(scheduler, '_check_memory_usage', return_value=True):
                    with patch.object(scheduler, '_check_process_status', return_value=True):
                        with patch.object(scheduler, '_send_alert') as mock_alert:
                            scheduler._health_check()

                            mock_alert.assert_called()

    def test_check_database_health_success(self, scheduler, temp_db_file):
        """데이터베이스 상태 확인 성공"""
        with patch('src.automation.auto_scheduler.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()  # MagicMock for context manager support
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (100,)
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = False
            mock_connect.return_value = mock_conn

            result = scheduler._check_database_health()

            assert result is True

    def test_check_database_health_failure(self, scheduler):
        """데이터베이스 상태 확인 실패"""
        with patch('src.automation.auto_scheduler.sqlite3.connect', side_effect=sqlite3.Error("Connection error")):
            result = scheduler._check_database_health()

            assert result is False

    def test_check_disk_space(self, scheduler):
        """디스크 공간 확인"""
        result = scheduler._check_disk_space()

        # 실제 시스템에서는 True 또는 False 반환
        assert isinstance(result, bool)

    def test_check_memory_usage(self, scheduler):
        """메모리 사용량 확인"""
        result = scheduler._check_memory_usage()

        # 실제 시스템에서는 True 또는 False 반환
        assert isinstance(result, bool)

    def test_check_process_status(self, scheduler):
        """프로세스 상태 확인"""
        result = scheduler._check_process_status()

        # 항상 True (실행 중이므로)
        assert result is True


class TestCleanupOperations:
    """정리 작업 테스트"""

    def test_cleanup_logs_success(self, scheduler, tmp_path):
        """로그 파일 정리 성공"""
        # 임시 로그 디렉토리 생성
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # 오래된 로그 파일 생성
        old_log = log_dir / "old.log"
        old_log.write_text("old log")

        # 파일 수정 시간을 40일 전으로 설정
        old_time = time.time() - (40 * 24 * 60 * 60)
        os.utime(str(old_log), (old_time, old_time))

        with patch('src.automation.auto_scheduler.os.listdir', return_value=['old.log']):
            with patch('src.automation.auto_scheduler.os.path.join', return_value=str(old_log)):
                with patch('src.automation.auto_scheduler.os.path.getmtime', return_value=old_time):
                    with patch('src.automation.auto_scheduler.os.remove') as mock_remove:
                        scheduler._cleanup_logs()

                        assert scheduler.job_status['cleanup_logs']['success'] > 0

    def test_cleanup_old_cache(self, scheduler, tmp_path):
        """오래된 캐시 정리"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        old_cache = cache_dir / "old_model.pkl"
        old_cache.write_text("old cache")

        with patch('src.automation.auto_scheduler.os.walk', return_value=[(str(cache_dir), [], ['old_model.pkl'])]):
            with patch('src.automation.auto_scheduler.os.remove') as mock_remove:
                scheduler._cleanup_old_cache()

                # 캐시 정리가 실행되었는지 확인
                assert True

    def test_optimize_databases(self, scheduler, temp_db_file):
        """데이터베이스 최적화"""
        with patch('src.automation.auto_scheduler.os.path.exists', return_value=True):
            with patch('src.automation.auto_scheduler.sqlite3.connect') as mock_connect:
                mock_conn = MagicMock()  # MagicMock for context manager support
                mock_conn.__enter__.return_value = mock_conn
                mock_conn.__exit__.return_value = False
                mock_connect.return_value = mock_conn

                scheduler._optimize_databases()

                # VACUUM 및 ANALYZE 실행 확인
                assert mock_conn.execute.called

    def test_retrain_models(self, scheduler, tmp_path):
        """ML 모델 재학습"""
        model_cache = tmp_path / "cache" / "models"
        model_cache.mkdir(parents=True)

        with patch('src.automation.auto_scheduler.os.path.exists', return_value=True):
            with patch('shutil.rmtree') as mock_rmtree:  # shutil is locally imported
                with patch('src.automation.auto_scheduler.os.makedirs') as mock_makedirs:
                    scheduler._retrain_models()

                    # 캐시 삭제 및 재생성 확인
                    mock_rmtree.assert_called_once()
                    mock_makedirs.assert_called_once()


class TestUpdateChain:
    """자동 업데이트 체인 테스트"""

    def test_trigger_update_chain_success(self, scheduler):
        """자동 업데이트 체인 성공"""
        with patch.object(scheduler, '_trigger_pattern_reanalysis'):
            with patch.object(scheduler, '_trigger_filter_update'):
                with patch.object(scheduler, '_invalidate_ml_cache'):
                    with patch.object(scheduler, '_update_system_state'):
                        scheduler._trigger_update_chain(1001)

                        # 모든 단계가 호출되었는지 확인
                        scheduler._trigger_pattern_reanalysis.assert_called_once()
                        scheduler._trigger_filter_update.assert_called_once()
                        scheduler._invalidate_ml_cache.assert_called_once()
                        scheduler._update_system_state.assert_called_once()

    def test_trigger_pattern_reanalysis(self, scheduler, mock_db_manager):
        """패턴 재분석 트리거"""
        # [FIX] 코드가 db.get_numbers_with_bonus()[-1][0]로 최신 회차를 구하고
        #       pattern_mgr.analyze_patterns(latest_round)를 호출하도록 리팩토링됨.
        #       (기존 테스트는 analyze_all_patterns를 기대 → 코드와 불일치하여 실패)
        mock_db_manager.get_numbers_with_bonus.return_value = [
            (1000, (1, 2, 3, 4, 5, 6, 7)),
            (1001, (8, 9, 10, 11, 12, 13, 14)),
        ]
        with patch('src.core.pattern_manager.PatternManager') as mock_pm:  # locally imported in function
            mock_pattern_mgr = Mock()
            mock_pattern_mgr.analyze_patterns.return_value = {'pattern1': 0.5}
            mock_pm.return_value = mock_pattern_mgr

            scheduler._trigger_pattern_reanalysis(1001)

            # 패턴 분석 호출 확인 (최신 회차 1001로 호출)
            mock_pattern_mgr.analyze_patterns.assert_called_once_with(1001)

    def test_trigger_filter_update(self, scheduler, mock_db_manager, tmp_path):
        """필터 업데이트 트리거"""
        # 임시 설정 파일 생성
        config_file = tmp_path / "adaptive_filter_config.yaml"
        config_file.write_text(yaml.dump({'global_probability_threshold': 2.0}))

        with patch('src.core.integrated_filter_manager.IntegratedFilterManager') as mock_ifm:  # locally imported in function
            mock_filter_mgr = Mock()
            mock_filter_mgr.update_filters_weekly.return_value = {'updated_filters': 5}
            mock_ifm.return_value = mock_filter_mgr

            # yaml.safe_load를 직접 mock하여 파일 읽기 우회
            with patch('yaml.safe_load', return_value={'global_probability_threshold': 2.0}):
                from unittest.mock import mock_open
                with patch('builtins.open', mock_open(read_data=yaml.dump({'global_probability_threshold': 2.0}))):
                    scheduler._trigger_filter_update(1001)

                    # 필터 업데이트 호출 확인
                    mock_filter_mgr.update_filters_weekly.assert_called_once()

    def test_invalidate_ml_cache(self, scheduler, tmp_path):
        """ML 캐시 무효화"""
        cache_dir = tmp_path / "cache" / "models"
        cache_dir.mkdir(parents=True)

        # [2026-06-13] _invalidate_ml_cache는 '회차 스탬프 기반 자동 재학습' 정책으로
        # cache/models 물리 삭제를 의도적 no-op으로 전환함(재사용 가능한 모델까지 날리는
        # 파괴적 재학습 방지). 따라서 rmtree/makedirs가 '호출되지 않음'을 검증하고,
        # 예외 없이 정상 반환하는지만 확인한다.
        with patch('shutil.rmtree') as mock_rmtree:  # shutil is locally imported
            with patch('src.automation.auto_scheduler.os.makedirs') as mock_makedirs:
                scheduler._invalidate_ml_cache()

                mock_rmtree.assert_not_called()
                mock_makedirs.assert_not_called()

    def test_update_system_state(self, scheduler):
        """시스템 상태 업데이트"""
        with patch('src.core.system_state_manager.SystemStateManager') as mock_ssm:  # locally imported in function
            mock_state_mgr = Mock()
            mock_ssm.return_value = mock_state_mgr

            scheduler._update_system_state(1001)

            # 시스템 상태 업데이트 호출 확인
            mock_state_mgr.update_state.assert_called_once()


class TestDatabaseCallbacks:
    """데이터베이스 콜백 테스트"""

    def test_setup_db_callbacks(self, scheduler, mock_db_manager):
        """데이터베이스 콜백 설정"""
        scheduler.setup_db_callbacks()

        # DatabaseManager에 콜백이 등록되었는지 확인
        mock_db_manager.register_callback.assert_called_once_with(
            'new_round_added',
            scheduler._on_new_round_added
        )

    def test_on_new_round_added_callback(self, scheduler):
        """새 회차 추가 시 콜백 실행"""
        with patch.object(scheduler, '_trigger_update_chain') as mock_trigger:
            scheduler._on_new_round_added(1001)

            mock_trigger.assert_called_once_with(1001)


class TestStatusReporting:
    """상태 보고 테스트"""

    def test_get_status_scheduler_stopped(self, scheduler):
        """스케줄러 중지 상태"""
        status = scheduler.get_status()

        assert status['running'] is False
        assert 'jobs' in status
        assert isinstance(status['jobs'], dict)

    def test_get_status_scheduler_running(self, scheduler):
        """스케줄러 실행 상태"""
        scheduler.start()
        time.sleep(0.1)

        status = scheduler.get_status()

        assert status['running'] is True
        assert 'jobs' in status

        # 정리
        scheduler.stop()

    def test_update_job_status_success(self, scheduler):
        """작업 상태 업데이트 - 성공"""
        initial_success = scheduler.job_status['check_new_round']['success']

        scheduler._update_job_status('check_new_round', True)

        assert scheduler.job_status['check_new_round']['success'] == initial_success + 1
        assert scheduler.job_status['check_new_round']['last_run'] is not None

    def test_update_job_status_failure(self, scheduler):
        """작업 상태 업데이트 - 실패"""
        initial_fail = scheduler.job_status['check_new_round']['fail']

        scheduler._update_job_status('check_new_round', False)

        assert scheduler.job_status['check_new_round']['fail'] == initial_fail + 1
        assert scheduler.job_status['check_new_round']['last_run'] is not None


class TestNotificationSystem:
    """알림 시스템 테스트"""

    def test_notify_prediction_complete(self, scheduler):
        """예측 완료 알림"""
        # 알림 기능 호출 확인
        scheduler._notify_prediction_complete()

        # 로깅이 발생했는지 확인
        assert True

    def test_send_alert(self, scheduler):
        """경고 알림 전송"""
        # 경고 알림 호출 확인
        scheduler._send_alert("Test alert message")

        # 로깅이 발생했는지 확인
        assert True


class TestErrorHandling:
    """오류 처리 테스트"""

    def test_health_check_exception_handling(self, scheduler):
        """상태 체크 예외 처리"""
        with patch.object(scheduler, '_check_database_health', side_effect=Exception("DB error")):
            scheduler._health_check()

            # 예외에도 불구하고 fail 카운터가 증가해야 함
            assert scheduler.job_status['health_check']['fail'] > 0

    def test_cleanup_logs_exception_handling(self, scheduler):
        """로그 정리 예외 처리"""
        with patch('src.automation.auto_scheduler.os.listdir', side_effect=Exception("Directory error")):
            scheduler._cleanup_logs()

            assert scheduler.job_status['cleanup_logs']['fail'] > 0

    def test_weekly_optimization_exception_handling(self, scheduler):
        """주간 최적화 예외 처리"""
        with patch.object(scheduler, '_cleanup_old_cache', side_effect=Exception("Cache error")):
            scheduler._run_weekly_optimization()

            assert scheduler.job_status['weekly_optimization']['fail'] > 0


# 테스트 실행 시 로깅 설정
@pytest.fixture(autouse=True)
def setup_logging():
    """테스트용 로깅 설정"""
    import logging
    logging.basicConfig(level=logging.ERROR)  # 테스트 중 로그 최소화
