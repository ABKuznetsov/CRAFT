@echo off
setlocal
set "APP_ROOT=%~dp0"
set "SCI_PYTHON=%PROGRAMDATA%\Sci\env\Scripts\pythonw.exe"
set "CRISTMA_VERSION="
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "cristma==" "%APP_ROOT%toolkit\requirements-windows.txt"') do set "CRISTMA_VERSION=%%B"
if not defined CRISTMA_VERSION (
    echo CRAFT has no exact CRiStMa dependency pin.
    exit /b 1
)

if not exist "%SCI_PYTHON%" (
    call "%APP_ROOT%toolkit\setup_sci_env.bat"
    if errorlevel 1 exit /b 1
)

"%SCI_PYTHON%" -c "import cristma, sys, docx; raise SystemExit(0 if cristma.__version__ == sys.argv[1] else 1)" "%CRISTMA_VERSION%" >nul 2>&1
if errorlevel 1 (
    call "%APP_ROOT%toolkit\setup_sci_env.bat"
    if errorlevel 1 exit /b 1
    "%SCI_PYTHON%" -c "import cristma, sys, docx; raise SystemExit(0 if cristma.__version__ == sys.argv[1] else 1)" "%CRISTMA_VERSION%" >nul 2>&1
    if errorlevel 1 (
        echo CRiStMa %CRISTMA_VERSION% is missing from the shared Python environment.
        exit /b 1
    )
)

set "PYTHONPATH=%APP_ROOT%;%PYTHONPATH%"
set "QT_API=pyside6"
start "" /b "%SCI_PYTHON%" -m craft.app %*
