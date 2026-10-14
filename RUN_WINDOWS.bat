@echo off
setlocal
cd /d "%~dp0"

echo   Kitten Studio - checking installation...
if not exist ".venv\Scripts\python.exe" goto :repair
".venv\Scripts\python.exe" -X utf8 verify_install.py
if errorlevel 1 goto :repair
goto :launch

:repair
echo.
echo   Some dependencies are missing. Repairing the private environment...
call "%~dp0INSTALL_WINDOWS.bat" --auto
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -X utf8 verify_install.py
if errorlevel 1 goto :fail

:launch
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-windows.ps1"
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo   Kitten Studio could not start. See the error above.
echo   To retry setup manually, run REPAIR_WINDOWS.bat.
pause
exit /b 1
