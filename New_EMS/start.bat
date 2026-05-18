@echo off
setlocal

cd /d "%~dp0"

if exist ".ems.pid" (
    set /p EXISTING_PID=<".ems.pid"
    if not "%EXISTING_PID%"=="" (
        tasklist /FI "PID eq %EXISTING_PID%" | find "%EXISTING_PID%" >nul
        if %ERRORLEVEL%==0 (
            echo EMS is already running with PID %EXISTING_PID%.
            exit /b 0
        )
    )
)

if not exist "logs" mkdir "logs"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath python -ArgumentList 'app.py' -WorkingDirectory '%cd%' -WindowStyle Hidden -PassThru -RedirectStandardOutput 'logs\ems.out.log' -RedirectStandardError 'logs\ems.err.log'; Set-Content -Path '.ems.pid' -Value $p.Id"

if %ERRORLEVEL% neq 0 (
    echo Failed to start EMS.
    exit /b 1
)

set /p NEW_PID=<".ems.pid"
echo EMS started in background with PID %NEW_PID%.
echo Logs: logs\ems.out.log and logs\ems.err.log

endlocal
