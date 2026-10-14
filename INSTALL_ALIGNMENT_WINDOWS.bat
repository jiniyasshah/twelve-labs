@echo off
setlocal
cd /d "%~dp0"
echo.
echo   Kitten Studio - Sentence alignment engine
 echo   -----------------------------------------
 echo   Installs free faster-whisper into the existing private .venv.
 echo   It will use CPU for alignment to avoid competing with KittenTTS GPU memory.
 echo.
if not exist ".venv\Scripts\python.exe" (
  echo Please run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" -m pip install --prefer-binary "faster-whisper>=1.1,<2"
if errorlevel 1 (
  echo.
  echo Installation failed. Check the error above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "from faster_whisper import WhisperModel; print('Alignment dependency ready.')"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Sentence alignment is installed. The first Detect sentences run
 echo downloads a small multilingual Whisper model, then caches it locally.
pause
