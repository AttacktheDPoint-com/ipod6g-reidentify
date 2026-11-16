@echo off
rem Guided iPod Classic 6G re-identify (see README.md). Extra arguments are passed through,
rem e.g.  run_guide.bat --serial AB1234CD9ZU   or   run_guide.bat --bootloader syscfgtool
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python 3 is not installed or not on PATH.
    pause
    exit /b 1
)
python tools\ipod6g_guide.py %*
echo.
pause
