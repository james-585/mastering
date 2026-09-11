@echo off
REM Double-click to launch the local settings UI in your browser.
setlocal

set "REPO_ROOT=%~dp0"
set "IMPLEMENTATION_DIR=%REPO_ROOT%stories\STORY-001\implementation"
set "PYTHONPATH=%IMPLEMENTATION_DIR%;%PYTHONPATH%"

cd /d "%IMPLEMENTATION_DIR%"

REM Load HF_TOKEN from .env if present (stem separation needs it for Demucs).
if exist "%REPO_ROOT%.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%REPO_ROOT%.env") do (
        if /i "%%A"=="HF_TOKEN" set "HF_TOKEN=%%B"
    )
)

echo Activating environment...
call "%REPO_ROOT%.venv\Scripts\activate.bat"

echo Starting the settings UI. Your browser will open automatically.
echo Leave this window open while you use it; close it to stop the server.
echo.
python -m suno_mastering.webui

echo.
echo Server stopped. Press any key to close this window.
pause >nul
