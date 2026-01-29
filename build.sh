#!/bin/bash

# 1. Активируем виртуальное окружение (если есть)
source ./venv/bin/activate

# 2. Получаем пути к заголовочным файлам Python и pybind11
INCLUDES=$(python3 -m pybind11 --includes)

# 3. Получаем правильное расширение для модуля (.so или .dylib)
SUFFIX=$(python3 -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')")

# 4. Компилируем
echo "Compiling C++ engine..."
c++ -O3 -Wall -shared -std=c++17 -fPIC ${INCLUDES} -undefined dynamic_lookup core/src/engine.cpp core/src/binding.cpp -o core/emotion_engine${SUFFIX}

if [ $? -eq 0 ]; then
    echo "Successfully compiled: core/emotion_engine${SUFFIX}"
else
    echo "Compilation failed!"
    exit 1
fi
