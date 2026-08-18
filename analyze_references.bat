@echo off
REM Drag a FOLDER of reference tracks onto this .bat file, or double-click
REM and enter a folder path when prompted. Optionally also compare a Suno
REM export against the set.
setlocal

set "REFDIR=%~1"
if "%REFDIR%"=="" (
    set /p REFDIR=Enter full path to your reference-tracks folder:
)

set "SUNOEXPORT="
set /p SUNOEXPORT=Optional: path to a Suno export WAV to compare (leave blank to skip):

echo.
echo Reference folder: %REFDIR%
if not "%SUNOEXPORT%"=="" echo Suno export:       %SUNOEXPORT%
echo.
echo Activating environment...
call "%~dp0venv\Scripts\activate.bat"

echo Environment ready. Starting analysis — this can take several minutes
echo for a full reference set with no output in between, that is normal,
echo please wait...
echo.

if "%SUNOEXPORT%"=="" (
    python -m suno_mastering.reference_analysis "%REFDIR%"
) else (
    python -m suno_mastering.reference_analysis "%REFDIR%" --suno-export "%SUNOEXPORT%"
)

if errorlevel 1 (
    echo.
    echo FAILED - see error message above.
) else (
    echo.
    echo SUCCESS - report (markdown + JSON) written into the reference folder.
)

echo.
echo Press any key to close this window.
pause >nul
