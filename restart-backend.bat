@echo off
rem Double-click: RESTART the video-tool backend (kill whatever holds :8911, start fresh).
rem Do NOT run this while a render is in progress - it kills the running task.
rem Backend: http://127.0.0.1:8911/docs    H5: http://127.0.0.1:8920
chcp 65001 >nul
setlocal
set ROOT=C:\tmp\video-tool
set PY=D:\venvs\video-tool\Scripts\python.exe
cd /d "%ROOT%\backend"

echo [backend] stopping anything listening on 8911...
set KILLED=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8911" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
    set KILLED=1
)
if "%KILLED%"=="0" echo [backend] was not running.
ping -n 3 127.0.0.1 >nul

echo [backend] starting...
start "video-tool backend" /min cmd /c "set VT_CLONE_WORKERS=4&& "%PY%" scripts\with_user_env.py "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8911 --log-level info >> "%ROOT%\logs\clone-8911.log" 2>&1"
ping -n 6 127.0.0.1 >nul

netstat -ano | findstr ":8911" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [backend] FAILED to start - check %ROOT%\logs\clone-8911.log
) else (
    echo [backend] OK - http://127.0.0.1:8911/docs
)

echo [backend] opening live log window (close it anytime; backend keeps running)
start "" powershell -NoExit -Command "Get-Content -Path '%ROOT%\logs\clone-8911.log' -Wait -Tail 60"
endlocal
ping -n 4 127.0.0.1 >nul
