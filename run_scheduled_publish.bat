@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "D:\99_MyPJT\GoogleAI_PJT\Instagram_TrailLog"
if not exist "logs" mkdir "logs"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
set "LOG_FILE=logs\schedule_%TODAY%.log"
set "GIT_EXE=C:\Users\gjyu\AppData\Local\Atlassian\SourceTree\git_local\cmd\git.exe"
if not exist "%GIT_EXE%" set "GIT_EXE=git"
set "GIT_TERMINAL_PROMPT=0"

echo ==================================================>> "%LOG_FILE%"
echo [%DATE% %TIME%] TrailLog 예약 업로드 시작>> "%LOG_FILE%"

"%GIT_EXE%" pull --rebase origin main >> "%LOG_FILE%" 2>&1

".\.venv\Scripts\python.exe" main.py --brd 걷기 --style auto --skip-published --round-robin --max-daily 5 --count 1 --publish >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% equ 0 (
    "%GIT_EXE%" diff --quiet published_history.json
    if errorlevel 1 (
        "%GIT_EXE%" add published_history.json >> "%LOG_FILE%" 2>&1
        "%GIT_EXE%" commit -m "chore: update published_history.json [skip ci]" >> "%LOG_FILE%" 2>&1
        "%GIT_EXE%" push origin main >> "%LOG_FILE%" 2>&1
    )
)

echo [%DATE% %TIME%] 종료 코드: %EXIT_CODE%>> "%LOG_FILE%"
exit /b %EXIT_CODE%
