@echo off
REM Build a portable GitHubManager.exe into dist\.

setlocal
cd /d "%~dp0"

echo Building GitHub Manager...
python build.py --clean || goto :error

echo.
echo Done. The portable executable is in dist\GitHubManager.exe
echo Copy that single file anywhere - it needs no Python installation.
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
