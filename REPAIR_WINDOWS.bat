@echo off
setlocal
cd /d "%~dp0"
call "%~dp0INSTALL_WINDOWS.bat"
exit /b %errorlevel%
