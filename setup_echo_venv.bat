@echo off
setlocal

:: ============================================================
:: Echo Virtual Environment Setup
:: Uses Python 3.11.9 (already installed)
:: Creates: C:\EchoEnv\
:: ============================================================

set PYTHON311=C:\Users\jrsrl\AppData\Local\Programs\Python\Python311\python.exe
set VENV_DIR=C:\EchoEnv

echo.
echo  Echo Venv Setup
echo  ===============
echo.

:: Verify Python 3.11 is available
if not exist "%PYTHON311%" (
    echo  ERROR: Python 3.11 not found at %PYTHON311%
    echo  Download from: https://www.python.org/downloads/release/python-3119/
    echo  Install to default location, do NOT add to PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('"%PYTHON311%" --version') do echo  Found: %%v

:: Create the venv
echo.
echo  Creating venv at %VENV_DIR% ...
"%PYTHON311%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo  ERROR: Failed to create venv.
    pause
    exit /b 1
)
echo  Venv created.

:: Upgrade pip inside venv
echo.
echo  Upgrading pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip

:: Install all requirements
echo.
echo  Installing packages (this may take a few minutes)...
echo  dlib and face_recognition take the longest.
echo.
"%VENV_DIR%\Scripts\pip.exe" install -r "%~dp0requirements_echo_venv.txt"

if errorlevel 1 (
    echo.
    echo  Some packages failed. See errors above.
    echo  Common fix: install Visual C++ Build Tools for dlib.
    echo  Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   All packages installed successfully.
echo   Run test_echo_env.py to verify:
echo     C:\EchoEnv\Scripts\python.exe test_echo_env.py
echo  ============================================================
echo.
pause
