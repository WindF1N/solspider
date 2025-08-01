#!/bin/bash

# Bundle Analyzer Startup Script
# Автоматический запуск системы анализа бандлеров

set -e

echo "🚀 Bundle Analyzer для A/B тестов"
echo "=================================="

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден!"
    exit 1
fi

# Проверяем зависимости
echo "📦 Проверяем зависимости..."
if [ -f "requirements_bundle.txt" ]; then
    pip3 install -r requirements_bundle.txt --quiet
    echo "✅ Зависимости установлены"
else
    echo "⚠️ Файл requirements_bundle.txt не найден"
fi

# Проверяем конфигурацию
if [ -f ".env.bundlers" ]; then
    echo "⚙️ Загружаем конфигурацию из .env.bundlers"
    export $(cat .env.bundlers | grep -v '#' | xargs)
else
    echo "⚠️ Файл .env не найден, используем bundle_analyzer_config.env"
    if [ -f "bundle_analyzer_config.env" ]; then
        export $(cat bundle_analyzer_config.env | grep -v '#' | xargs)
    fi
fi

# Проверяем TELEGRAM_TOKEN
if [ -z "$TELEGRAM_TOKEN" ] || [ "$TELEGRAM_TOKEN" = "YOUR_TELEGRAM_BOT_TOKEN_HERE" ]; then
    echo "❌ TELEGRAM_TOKEN не установлен!"
    echo "📝 Настройте токен в файле .env.bundlers или bundle_analyzer_config.env"
    exit 1
fi

# Выбор режима запуска
echo ""
echo "Выберите режим запуска:"
echo "1) 🧪 Тестирование (рекомендуется для первого запуска)"
echo "2) 🎯 Полный режим с Jupiter"
echo "3) 🔧 Тестовый режим без Jupiter"
echo "4) 🔍 Только WebSocket анализ"

read -p "Введите номер (1-4): " choice

case $choice in
    1)
        echo "🧪 Запускаем тестирование..."
        python3 test_bundle_analyzer.py
        ;;
    2)
        echo "🎯 Запускаем полный режим с Jupiter..."
        export USE_JUPITER=true
        python3 bundle_analyzer_integration.py
        ;;
    3)
        echo "🔧 Запускаем тестовый режим..."
        export USE_JUPITER=false
        python3 bundle_analyzer_integration.py
        ;;
    4)
        echo "🔍 Запускаем только WebSocket анализ..."
        python3 padre_websocket_client.py
        ;;
    *)
        echo "❌ Неверный выбор!"
        exit 1
        ;;
esac 