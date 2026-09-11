@echo off
REM Rebuilds the standalone packaged app into dist\SunoMastering.
REM Run from anywhere; paths are resolved relative to this script.
setlocal

set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo pyinstaller is not installed in .venv -- run:
    echo   .venv\Scripts\python.exe -m pip install pyinstaller
    exit /b 1
)

echo Building... this takes 2-3 minutes.
".venv\Scripts\pyinstaller.exe" "packaging\suno_mastering.spec"

if errorlevel 1 (
    echo Build failed -- see output above.
    exit /b 1
)

echo.
echo Build complete: dist\SunoMastering\
echo Zip that whole folder to distribute it. The user runs SunoMastering.exe
echo inside it -- no Python install needed.
pause
