@echo off
setlocal

set "ROOT=%~dp0"
set "RUNDIR=%ROOT%run"
set "PIDFILE=%RUNDIR%\fastapi.pid"
if not exist "%RUNDIR%" mkdir "%RUNDIR%" >nul 2>&1
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%VIRTUAL_ENV%\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
if "%PY%"=="py" (
  where py >nul 2>&1
  if errorlevel 1 set "PY=python"
)

if "%PY%"=="python" (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python interpreter not found.
    echo [HINT] Create venv in project: python -m venv .venv
    echo [HINT] Then install deps: .venv\Scripts\python.exe -m pip install fastapi uvicorn
    exit /b 1
  )
)

if not "%PY%"=="py" if not "%PY%"=="python" if not exist "%PY%" (
  echo [ERROR] Python not found in virtual environment.
  echo Checked local path: %ROOT%.venv\Scripts\python.exe
  echo Checked active venv: %VIRTUAL_ENV%\Scripts\python.exe
  exit /b 1
)

echo [INFO] Starting FastAPI using:
echo        %PY%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath '%PY%' -ArgumentList 'app_fastapi.py' -WorkingDirectory '%ROOT%' -PassThru; " ^
  "Set-Content -Path '%PIDFILE%' -Value $p.Id; " ^
  "Write-Host ('[INFO] FastAPI started. PID=' + $p.Id)"

endlocal
