@echo off
setlocal
cd /d "%~dp0"
if not exist output mkdir output

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo Inno Setup 6 compiler was not found.
    exit /b 1
)

"%ISCC%" CRAFT.iss
if errorlevel 1 exit /b 1
echo Installer was created in installer\output.
exit /b 0
