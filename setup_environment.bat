@echo off
echo ================================
echo Python 환경 설정 스크립트
echo ================================

echo.
echo [1/3] Python 버전 확인...
python --version
if %errorlevel% neq 0 (
    echo [X] Python이 설치되지 않았습니다!
    echo     https://www.python.org/downloads/ 에서 설치하세요.
    pause
    exit /b 1
)

echo.
echo [2/3] 필수 패키지 설치...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [X] 패키지 설치 실패!
    pause
    exit /b 1
)

echo.
echo [3/3] 환경 테스트...
python test_main_execution.py
if %errorlevel% neq 0 (
    echo [X] 테스트 실패!
    pause
    exit /b 1
)

echo.
echo ================================
echo [O] 환경 설정 완료!
echo ================================
echo.
echo 이제 다음 명령으로 프로그램을 실행할 수 있습니다:
echo python main.py
echo.
pause