@echo off
setlocal

cd /d "%~dp0"

if not exist ".ems.pid" (
    echo No PID file found. EMS may not be running.
    exit /b 0
)

set /p EMS_PID=<".ems.pid"

if "%EMS_PID%"=="" (
    echo PID file is empty. Cleaning up PID file.
    del /f /q ".ems.pid" >nul 2>&1
    exit /b 0
)

tasklist /FI "PID eq %EMS_PID%" | find "%EMS_PID%" >nul
if %ERRORLEVEL% neq 0 (
    echo Process %EMS_PID% is not running. Cleaning up PID file.
    del /f /q ".ems.pid" >nul 2>&1
    exit /b 0
)

taskkill /PID %EMS_PID% /T /F >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Failed to stop EMS process %EMS_PID%.
    exit /b 1
)

del /f /q ".ems.pid" >nul 2>&1
echo EMS stopped (PID %EMS_PID%).

endlocal
