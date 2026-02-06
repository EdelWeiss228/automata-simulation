#!/bin/bash

# 1. Активируем виртуальное окружение (если есть)
if [ -d "./venv" ]; then
    source ./venv/bin/activate
fi

# 2. Детекция ОС и параметров ядра
OS_NAME=$(uname -s)
KERNEL_INFO=$(uname -rvm)
ARCH_NAME=$(uname -m)

echo "Detected OS: $OS_NAME ($ARCH_NAME)"

# 3. Настройка флагов OpenMP и компилятора
OMP_FLAGS=""
EXTRA_LIBS=""

if [[ "$OS_NAME" == "Darwin" ]]; then
    # macOS: Apple Clang требует специальных флагов для OpenMP через libomp
    if [ -d "/opt/homebrew/opt/libomp" ]; then
        OMP_FLAGS="-Xpreprocessor -fopenmp -I/opt/homebrew/opt/libomp/include"
        EXTRA_LIBS="-L/opt/homebrew/opt/libomp/lib -lomp"
    elif [ -d "/usr/local/opt/libomp" ]; then
        OMP_FLAGS="-Xpreprocessor -fopenmp -I/usr/local/opt/libomp/include"
        EXTRA_LIBS="-L/usr/local/opt/libomp/lib -lomp"
    else
        echo "Warning: libomp not found via Homebrew. Compilation might fail or run sequentially."
    fi
    UNDEFINED_LOOKUP="-undefined dynamic_lookup"
elif [[ "$OS_NAME" == "Linux" ]]; then
    OMP_FLAGS="-fopenmp"
    UNDEFINED_LOOKUP=""
else
    # Windows (MinGW/MSYS)
    OMP_FLAGS="-fopenmp"
    UNDEFINED_LOOKUP=""
fi

# 4. Получаем пути к заголовочным файлам Python и pybind11
PY_BIN="python3"
if [ -f "./venv/bin/python3" ]; then
    PY_BIN="./venv/bin/python3"
fi

echo "Using Python: $($PY_BIN --version) from $PY_BIN"
INCLUDES=$($PY_BIN -m pybind11 --includes)

# 5. Получаем правильное расширение для модуля
SUFFIX=$($PY_BIN -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')")

# 6. Компилируем
echo "Compiling C++ engine with OpenMP..."
c++ -O3 -Wall -shared -std=c++17 -fPIC ${OMP_FLAGS} ${INCLUDES} ${UNDEFINED_LOOKUP} \
    core/src/engine.cpp core/src/binding.cpp \
    ${EXTRA_LIBS} \
    -o core/emotion_engine${SUFFIX}

if [ $? -eq 0 ]; then
    echo "Successfully compiled: core/emotion_engine${SUFFIX}"
    # Сохраняем информацию о билде для run.sh
    echo "$OS_NAME | $KERNEL_INFO | $ARCH_NAME" > core/.build_info
else
    echo "Compilation failed!"
    exit 1
fi
