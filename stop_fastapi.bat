@echo off
setlocal

set "ROOT=%~dp0"
set "RUNDIR=%ROOT%run"
set "PIDFILE=%RUNDIR%\fastapi.pid"
if not exist "%RUNDIR%" mkdir "%RUNDIR%" >nul 2>&1

if exist "%PIDFILE%" (
  set /p PID=<"%PIDFILE%"
  if not "%PID%"=="" (
    echo [INFO] Stopping FastAPI PID %PID% ...
    taskkill /PID %PID% /T /F >nul 2>&1
    if %errorlevel%==0 (
      echo [INFO] Process %PID% stopped.
      del "%PIDFILE%" >nul 2>&1
      endlocal
      exit /b 0
    )
    echo [WARN] PID %PID% was not running. Trying fallback...
  )
)

echo [INFO] Fallback: stopping processes running app_fastapi.py ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app_fastapi.py' }; " ^
  "if (-not $procs) { Write-Host '[INFO] No app_fastapi.py process found.'; exit 0 }; " ^
  "$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[INFO] Stopped PID ' + $_.ProcessId) }"

del "%PIDFILE%" >nul 2>&1
endlocal
