@echo off
setlocal enabledelayedexpansion

echo === Compiling C++ engine (Windows) ===

:: 1. Check for Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 2. Get Python and pybind11 info
for /f "tokens=*" %%i in ('python -m pybind11 --includes') do set INCLUDES=%%i
for /f "tokens=*" %%i in ('python -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.pyd')"') do set SUFFIX=%%i

:: 3. Compilation with g++ (MinGW/MSYS2)
echo Using g++ to build core\emotion_engine%SUFFIX%...
g++ -O3 -Wall -shared -std=c++17 -fopenmp %INCLUDES% ^
    core\src\engine.cpp core\src\logger.cpp core\src\binding.cpp ^
    -o core\emotion_engine%SUFFIX%

if %ERRORLEVEL% equ 0 (
    echo Successfully compiled: core\emotion_engine%SUFFIX%
    echo Windows | %DATE% %TIME% | %PROCESSOR_ARCHITECTURE% > core\.build_info
) else (
    echo Compilation failed! Make sure g++ (MinGW-w64) is in your PATH.
    exit /b 1
)
