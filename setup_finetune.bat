@echo off
echo Setting up Echo fine-tune environment...
echo.

SET CONDA=C:\Users\jrsrl\miniconda3\Scripts\conda.exe
SET ACTIVATE=C:\Users\jrsrl\miniconda3\Scripts\activate.bat

echo Step 1: Creating conda environment echo_finetune...
call "%ACTIVATE%"
%CONDA% create -n echo_finetune python=3.11 -y
if errorlevel 1 (echo ERROR: conda create failed & pause & exit /b 1)

echo.
echo Step 2: Installing PyTorch CUDA 12.1...
%CONDA% run -n echo_finetune pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (echo ERROR: PyTorch install failed & pause & exit /b 1)

echo.
echo Step 3: Installing Unsloth...
%CONDA% run -n echo_finetune pip install "unsloth[cu121-torch210] @ git+https://github.com/unslothai/unsloth.git"
if errorlevel 1 (echo ERROR: Unsloth install failed & pause & exit /b 1)

echo.
echo Step 4: Installing training dependencies...
%CONDA% run -n echo_finetune pip install --no-deps trl peft accelerate
%CONDA% run -n echo_finetune pip install bitsandbytes datasets transformers
if errorlevel 1 (echo ERROR: Dependency install failed & pause & exit /b 1)

echo.
echo =============================================
echo Setup complete.
echo To train:
echo   conda activate echo_finetune
echo   cd C:\Users\jrsrl\Desktop\Echo2
echo   python finetune_echo.py
echo =============================================
pause
