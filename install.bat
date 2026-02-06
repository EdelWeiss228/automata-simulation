@echo off
setlocal

echo === Collective Automaton Simulation: Installation (Windows) ===

:: 1. Check for Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: python is not installed or not in PATH.
    exit /b 1
)

:: 2. Create Virtual Environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists.
)

:: 3. Install Dependencies
echo Activating virtual environment and installing dependencies...
call venv\Scripts\activate.bat

python -m pip install --upgrade pip

if exist "requirements.txt" (
    pip install -r requirements.txt
) else (
    echo requirements.txt not found! Installing base packages manually...
    pip install numpy pandas pybind11
)

:: 4. Build Engine
echo Running build.bat to compile the C++ engine...
call build.bat

if %ERRORLEVEL% equ 0 (
    echo === INSTALLATION SUCCESSFUL ===
    echo Entering virtual environment shell...
    cmd /k venv\Scripts\activate.bat
) else (
    echo === INSTALLATION FINISHED WITH WARNINGS ===
    echo Environment is set up, but build.bat failed. Check C++ compiler (g++).
)

pause
