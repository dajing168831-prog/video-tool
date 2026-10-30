@echo off
rem Foreground backend start - logs scroll in this window. Ctrl+C to stop.
rem Used by .vscode/tasks.json; double-click also works.
rem Credentials come from HKCU via scripts\with_user_env.py (never on the command line).
rem NOTE: keep this file pure ASCII - chcp 65001 would make cmd re-read the
rem       file with the wrong offsets and garble any non-ASCII bytes.
chcp 65001 >nul
setlocal
set ROOT=C:\tmp\video-tool
set PY=D:\venvs\video-tool\Scripts\python.exe
cd /d "%ROOT%\backend"
set VT_CLONE_WORKERS=4

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8911" ^| findstr "LISTENING"') do (
    echo [backend] killing old pid %%a
    taskkill /f /pid %%a >nul 2>&1
)

echo [backend] http://127.0.0.1:8911/docs   (Ctrl+C to stop)
echo ----------------------------------------------------------------------
"%PY%" scripts\with_user_env.py "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8911 --log-level info
echo ----------------------------------------------------------------------
echo [backend] stopped. Exit code %errorlevel%
endlocal
