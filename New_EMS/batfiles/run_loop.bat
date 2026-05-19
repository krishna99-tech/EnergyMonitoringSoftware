@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs

:loop
REM Generate timestamp for log file
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set mydate=%%d-%%b-%%c
for /f "tokens=1-2 delims=:." %%a in ("%time%") do set mytime=%%a-%%b
set logfile=logs\app_%mydate%_%mytime%.log

REM Start app.py with pythonw (no console window) and redirect output to log
start "" /b pythonw app.py >> "%logfile%" 2>&1

REM Wait a moment, then loop forever (restarts immediately if app.py exits)
timeout /t 2 /nobreak >nul
goto loop