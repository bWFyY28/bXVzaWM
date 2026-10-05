@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run python install.py with Python 3.13 first; see README.md.
    exit /b 1
)
set "PYTHONPATH=%~dp0src"
set "PYTHONDONTWRITEBYTECODE=1"
"%~dp0.venv\Scripts\python.exe" -m bxvzm %*
exit /b %errorlevel%
