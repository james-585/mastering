@echo off
REM Drag a WAV file onto this .bat file, or double-click and enter a path when prompted.
setlocal

set "INPUT=%~1"
if "%INPUT%"=="" (
    set /p INPUT=Enter full path to your WAV file:
)

set "REPO_ROOT=%~dp0"
set "IMPLEMENTATION_DIR=%REPO_ROOT%stories\STORY-001\implementation"
set "PYTHONPATH=%IMPLEMENTATION_DIR%;%PYTHONPATH%"

cd /d "%IMPLEMENTATION_DIR%"

echo Input file: %INPUT%
echo.
echo Activating environment...
call "%REPO_ROOT%venv\Scripts\activate.bat"

echo Environment ready. Starting mastering — this can take a minute or two
echo per track with no output in between, that is normal, please wait...
echo.
REM The Python CLI itself prints the live stage-progress banner below --
REM do not echo it here too, it would just be printed twice.
REM Use the stem-aware pre-master flow so repairs are triggered only after
REM explicit stem-level issue identification in Stage 2. Stem separation
REM always runs the 6-stem HTDemucs model (piano/guitar isolation); the
REM four-stem models remain available via --stem-model overrides.
python -m suno_mastering "%INPUT%" --split-stems --stem-model htdemucs_6s --no-repair-whistles --no-shape-transients --no-collapse-swish

if errorlevel 2 (
    echo.
    echo REJECTED - quality review rejected this master; see report for details.
) else if errorlevel 1 (
    echo.
    echo FAILED - see error message above.
) else (
    echo.
    echo SUCCESS - mastered file and report written next to the input file.
)

echo.
echo Press any key to close this window.
pause >nul
