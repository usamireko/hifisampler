@echo off
setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set "LOG_FILE=%CD%\logs\server.log"

set "PYTHON_EXE=%CD%\runtime\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%CD%\runtime\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python runtime not found. Use the full portable package or install Python 3.10.
        echo Python runtime not found. Use the full portable package or install Python 3.10.>> "%LOG_FILE%"
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

set "SERVER_SCRIPT=%CD%\hifiserver.py"
if not exist "%SERVER_SCRIPT%" set "SERVER_SCRIPT=%CD%\..\hifiserver.py"
if not exist "%SERVER_SCRIPT%" (
    echo ERROR: hifiserver.py was not found.
    echo Expected it in this portable folder or the parent folder.
    echo ERROR: hifiserver.py was not found.>> "%LOG_FILE%"
    pause
    exit /b 1
)

set "HIFISAMPLER_CONFIG=%CD%\config.yaml"
set "HIFISAMPLER_DEFAULT_CONFIG=%CD%\config.default.yaml"

if exist "manager\prepare_portable.py" (
    "%PYTHON_EXE%" "manager\prepare_portable.py"
    if errorlevel 1 (
        echo ERROR: portable preparation failed. See messages above.
        pause
        exit /b 1
    )
)

echo.
echo Hifisampler server started.
echo Logs: %LOG_FILE%
echo Press Ctrl+C to stop the server.
echo.
echo ===== Hifisampler server start %DATE% %TIME% =====>> "%LOG_FILE%"
"%PYTHON_EXE%" "%SERVER_SCRIPT%" >> "%LOG_FILE%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo ERROR: Hifisampler server stopped with exit code %SERVER_EXIT%.
    echo See logs\server.log for details.
    pause
    exit /b %SERVER_EXIT%
)

echo.
echo Hifisampler server stopped.
pause
exit /b 0
