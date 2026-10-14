@echo off
setlocal
cd /d "%~dp0"
echo.
echo   Kitten Studio - optional NVIDIA GPU support
 echo   ----------------------------------------------
echo   This replaces CPU-only torch/torchaudio in THIS app's private venv.
echo   NVIDIA GPU and a compatible current driver are required.
echo   CPU mode works without doing this.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat before installing optional GPU support.
  pause
  exit /b 1
)
where nvidia-smi >nul 2>nul
if errorlevel 1 (
  echo ERROR: NVIDIA driver utility not found. Check your GPU and NVIDIA driver.
  pause
  exit /b 1
)
nvidia-smi
 echo.
choice /m "Replace PyTorch packages with the CUDA 12.8 build"
if errorlevel 2 exit /b 1
set "PYTHONUTF8=1"
set "PIP_DEFAULT_TIMEOUT=120"
".venv\Scripts\python.exe" -m pip install --upgrade --force-reinstall torch==2.10.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -c "import torch; print('PyTorch:',torch.__version__,'CUDA build:',torch.version.cuda,'usable:',torch.cuda.is_available()); assert torch.cuda.is_available(), 'CUDA GPU unavailable: check driver and NVIDIA compatibility'"
if errorlevel 1 goto :fail
 echo.
echo   CUDA setup succeeded. Close and restart Kitten Studio.
pause
exit /b 0
:fail
echo.
echo   ERROR: CUDA setup not confirmed. CPU mode can be restored using REPAIR_WINDOWS.bat.
pause
exit /b 1
