@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%CD%\runtime\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%CD%\runtime\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python runtime not found. Use the full portable package or install Python 3.10.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "manager\install_openutau.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXIT_CODE%
