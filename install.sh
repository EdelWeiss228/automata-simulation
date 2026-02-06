#!/bin/bash

# install.sh — Скрипт автоматического развертывания окружения

echo "=== Collective Automaton Simulation: Installation ==="

# 1. Проверка наличия Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install it first."
    exit 1
fi

# 2. Детекция ОС
OS_NAME=$(uname -s)
echo "Detected OS: $OS_NAME"

# 3. Настройка системных зависимостей
if [[ "$OS_NAME" == "Darwin" ]]; then
    if ! command -v brew &> /dev/null; then
        echo "Tip: Homebrew not found. It's recommended for installing libomp (OpenMP)."
    else
        if [ ! -d "/opt/homebrew/opt/libomp" ] && [ ! -d "/usr/local/opt/libomp" ]; then
            echo "Installing libomp for OpenMP support..."
            brew install libomp
        else
            echo "libomp (OpenMP) already exists."
        fi
    fi
elif [[ "$OS_NAME" == "Linux" ]]; then
    echo "Checking Linux dependencies..."
    # Проверка g++
    if ! command -v g++ &> /dev/null; then
        echo "Warning: g++ not found. Please install build-essential (Debian/Ubuntu) or gcc-c++ (Fedora/CentOS)."
    fi
    # Проверка OpenMP (libomp или libgomp)
    if ! ldconfig -p | grep -q libgomp; then
        echo "Warning: libgomp (OpenMP) not found. Please install libomp-dev or libgomp1."
    fi
    # Проверка venv модуля
    if ! python3 -m venv --help &> /dev/null; then
        echo "Warning: python3-venv module not found. Please install it (e.g., sudo apt install python3-venv)."
    fi
fi

# 4. Создание виртуального окружения
if [ ! -d "./venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# 5. Установка Python зависимостей
echo "Activating virtual environment and installing dependencies..."
source ./venv/bin/activate

# Апгрейд pip
python3 -m pip install --upgrade pip

# Установка из requirements.txt
if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt
else
    echo "requirements.txt not found! Installing base packages manually..."
    python3 -m pip install numpy pandas pybind11
fi

# 6. Компиляция ядра
echo "Running build.sh to compile the C++ engine..."
chmod +x build.sh
./build.sh

if [ $? -eq 0 ]; then
    echo "=== INSTALLATION SUCCESSFUL ==="
    echo "Entering virtual environment shell. Type 'exit' to leave."
    # Пытаемся запустить оболочку с активированным окружением
    if [[ "$SHELL" == *"zsh"* ]]; then
        ZDOTDIR=$PWD exec zsh -i -c "source ./venv/bin/activate; exec zsh"
    else
        bash --rcfile <(echo "source ~/.bashrc; source ./venv/bin/activate")
    fi
else
    echo "=== INSTALLATION FINISHED WITH WARNINGS ==="
    echo "Environment is set up, but build.sh failed. Check C++ dependencies."
fi
