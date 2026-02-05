#!/bin/bash

# 1. Проверка совместимости билда (авто-ребилд при смене ядра/ОС)
OS_NAME=$(uname -s)
KERNEL_INFO=$(uname -rvm)
ARCH_NAME=$(uname -m)
CURRENT_INFO="$OS_NAME | $KERNEL_INFO | $ARCH_NAME"

BUILD_INFO_FILE="core/.build_info"
# Ищем бинарный файл (с любым расширением .so, .dylib, .pyd)
EXT_SUFFIX=$(python3 -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')")
BINARY_FILE="core/emotion_engine${EXT_SUFFIX}"

REBUILD_NEEDED=false

if [ ! -f "$BINARY_FILE" ]; then
    echo "Engine binary not found. Rebuilding..."
    REBUILD_NEEDED=true
elif [ ! -f "$BUILD_INFO_FILE" ]; then
    echo "Build info missing. Rebuilding for safety..."
    REBUILD_NEEDED=true
else
    LAST_BUILD_INFO=$(cat "$BUILD_INFO_FILE")
    if [[ "$CURRENT_INFO" != "$LAST_BUILD_INFO" ]]; then
        echo "Kernel or OS change detected!"
        echo "Current: $CURRENT_INFO"
        echo "Built:   $LAST_BUILD_INFO"
        REBUILD_NEEDED=true
    fi
fi

if [ "$REBUILD_NEEDED" = true ]; then
    chmod +x build.sh
    ./build.sh
    if [ $? -ne 0 ]; then
        echo "Auto-rebuild failed! Please check build.sh manually."
        exit 1
    fi
fi

# 2. Активируем виртуальное окружение
if [ -d "./venv" ]; then
    source ./venv/bin/activate
fi

# 3. Запускаем симуляцию
python3 main.py
