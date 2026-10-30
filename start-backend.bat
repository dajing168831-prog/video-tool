@echo off
rem Double-click: start the video-tool backend (if not running) and open a live log window.
rem Backend: http://127.0.0.1:8911/docs    H5: http://127.0.0.1:8920
chcp 65001 >nul
setlocal
set ROOT=C:\tmp\video-tool
set PY=D:\venvs\video-tool\Scripts\python.exe
cd /d "%ROOT%\backend"

netstat -ano | findstr ":8911" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [backend] not running, starting...
    start "video-tool backend" /min cmd /c "set VT_CLONE_WORKERS=4&& "%PY%" scripts\with_user_env.py "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8911 --log-level info >> "%ROOT%\logs\clone-8911.log" 2>&1"
    timeout /t 5 >nul
) else (
    echo [backend] already running on port 8911
)

echo [backend] opening live log window (close it anytime; backend keeps running)
start "" powershell -NoExit -Command "Get-Content -Path '%ROOT%\logs\clone-8911.log' -Wait -Tail 60"
endlocal
