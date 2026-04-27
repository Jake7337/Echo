@echo off
:: ============================================================
:: Run Echo Webcam Intelligence Module
:: Always uses the Python 3.11 venv — never system Python 3.14
:: ============================================================

set VENV_PYTHON=C:\EchoEnv\Scripts\python.exe
set ECHO_DIR=C:\Users\jrsrl\Desktop\Echo2

if not exist "%VENV_PYTHON%" (
    echo.
    echo  ERROR: EchoEnv venv not found.
    echo  Run setup_echo_venv.bat first.
    echo.
    pause
    exit /b 1
)

echo  Starting Echo Webcam Intel (Python 3.11)...
echo  Open Chrome: http://localhost:5051
echo.

cd /d "%ECHO_DIR%"
"%VENV_PYTHON%" -m webcam_intel.main

pause
