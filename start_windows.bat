@echo off
setlocal
cd /d "%~dp0"
echo =========================================
echo  PyBot Network Explorer / Windows
echo  Python standard library - no venv
echo =========================================
where py >nul 2>&1
if not errorlevel 1 (
  py -3 launch.py
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python 3.8+ is required: https://www.python.org/downloads/
    pause
    exit /b 1
  )
  python launch.py
)
if errorlevel 1 (
  echo Startup failed. See error above.
  pause
  exit /b 1
)
endlocal
exit /b 0
