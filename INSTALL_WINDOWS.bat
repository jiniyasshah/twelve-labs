@echo off
setlocal
cd /d "%~dp0"
set "QUIET=0"
if /i "%~1"=="--auto" set "QUIET=1"
echo.
echo   Kitten Studio - Windows setup and repair
echo   -----------------------------------------
echo.
if exist ".venv\Scripts\python.exe" goto :install

echo   Creating a standalone Python environment in:
echo   %CD%\.venv
echo.
py -3.12 -m venv ".venv"
if not errorlevel 1 goto :install
py -3.11 -m venv ".venv"
if not errorlevel 1 goto :install
py -3.10 -m venv ".venv"
if errorlevel 1 (
  echo   Unable to find Python 3.10, 3.11 or 3.12.
  echo   Install Python and rerun this installer.
  goto :fail
)

:install
if not exist ".venv\Scripts\python.exe" goto :fail
set "PYTHONUTF8=1"
set "PIP_DEFAULT_TIMEOUT=120"
set "PIP_RETRIES=5"
echo   Installing required libraries into the private environment...
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo   Checking all required imports...
".venv\Scripts\python.exe" -X utf8 verify_install.py
if errorlevel 1 goto :fail

echo.
echo   SUCCESS: Kitten Studio is installed in its own .venv.
echo   Run RUN_WINDOWS.bat to start.
if "%QUIET%"=="0" pause
exit /b 0

:fail
echo.
echo   ERROR: Installation did not finish. The server will not be started.
echo   See the error above, then rerun INSTALL_WINDOWS.bat.
if "%QUIET%"=="0" pause
exit /b 1
