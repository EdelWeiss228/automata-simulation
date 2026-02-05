@echo off
setlocal

:: 1. Check for engine binary
for /f "tokens=*" %%i in ('python -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.pyd')"') do set SUFFIX=%%i
set BINARY_FILE=core\emotion_engine%SUFFIX%

if not exist "%BINARY_FILE%" (
    echo Engine binary not found. Running build.bat...
    call build.bat
    if %ERRORLEVEL% neq 0 exit /b 1
)

:: 2. Activate Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 3. Launch Simulation
echo Starting Simulation...
python main.py
