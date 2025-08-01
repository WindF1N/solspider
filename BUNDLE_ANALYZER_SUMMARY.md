# Bundle Analyzer - Система анализа бандлеров для A/B тестов

## 🎯 Описание

Bundle Analyzer - это автоматизированная система для анализа количества бандлеров (bundlers) новых токенов, обнаруженных через Jupiter, с последующей отправкой уведомлений в Telegram группу при превышении настраиваемого порога.

## 📁 Файловая структура

```
bundle_analyzer.py                    # Основной модуль анализа бандлеров
bundle_analyzer_integration.py       # Интеграция с источниками токенов
padre_websocket_client.py           # Улучшенный WebSocket клиент для trade.padre.gg
test_bundle_analyzer.py             # Тестовый скрипт для проверки всех компонентов
run_bundle_analyzer.sh              # Bash скрипт для удобного запуска
requirements_bundle.txt             # Зависимости Python
bundle_analyzer_config.env          # Шаблон конфигурации
README_BUNDLE_ANALYZER.md          # Подробная документация
BUNDLE_ANALYZER_SUMMARY.md         # Это резюме
```

## 🚀 Быстрый старт

### 1. Установка зависимостей
```bash
pip install -r requirements_bundle.txt
```

### 2. Настройка конфигурации
```bash
cp bundle_analyzer_config.env .env
# Отредактируйте .env и установите ваш TELEGRAM_TOKEN
```

### 3. Запуск через скрипт
```bash
./run_bundle_analyzer.sh
```
Выберите режим:
- `1` - Тестирование (рекомендуется для начала)
- `2` - Полный режим с Jupiter 
- `3` - Тестовый режим без Jupiter
- `4` - Только WebSocket анализ

### 4. Ручной запуск
```bash
# Тестирование
python3 test_bundle_analyzer.py

# Полный режим
USE_JUPITER=true python3 bundle_analyzer_integration.py

# Тестовый режим
USE_JUPITER=false python3 bundle_analyzer_integration.py
```

## ⚙️ Ключевые настройки

### В файле .env:
```bash
TELEGRAM_TOKEN=your_bot_token_here          # Токен Telegram бота
MIN_BUNDLER_PERCENTAGE=10.0                 # Минимальный % бандлеров (по умолчанию 10%)
USE_JUPITER=false                           # true=Jupiter, false=тестовый режим
TARGET_CHAT_ID=-1002680160752               # ID Telegram группы
TARGET_THREAD_ID=13134                      # ID темы в группе
```

## 🔄 Принцип работы

1. **Получение токенов** → Jupiter WebSocket или тестовые данные
2. **Подключение к padre.gg** → WebSocket соединение с trade.padre.gg
3. **Анализ бандлеров** → Декодирование сообщений и извлечение данных
4. **Расчет процента** → Сравнение с настроенным порогом
5. **Уведомления** → Отправка в Telegram при превышении порога

## 📨 Формат уведомлений

```
🔥 ВЫСОКИЙ ПРОЦЕНТ БАНДЛЕРОВ!

💎 Токен: Token Name (SYMBOL)
📍 Контракт: 26KHEk6Y1F3tY2Lum4fCiTiHC1AtQ6Cneg5yP4TLbonk
👥 Бандлеров: 150
📊 Процент: 15.0%
⚡ Порог: 10.0%

🕐 Время: 14:30:25

[Кнопки: Axiom.trade | DexScreener | trade.padre.gg]
```

## 🧪 Тестирование

Система включает комплексное тестирование:
- Декодер сообщений trade.padre.gg
- Отправка уведомлений в Telegram
- WebSocket соединения
- Полная интеграция компонентов

## 🔧 Компоненты системы

### 1. PadreWebSocketClient (bundle_analyzer.py)
- Подключение к trade.padre.gg WebSocket
- Аутентификация с куки
- Подписка на данные о токенах
- Отправка уведомлений в Telegram

### 2. JupiterTokenListener (bundle_analyzer_integration.py) 
- Подключение к Jupiter WebSocket
- Получение новых токенов
- Парсинг сообщений Jupiter

### 3. PumpFunTokenListener (bundle_analyzer_integration.py)
- Альтернативный источник токенов
- Тестовый режим с имитацией

### 4. PadreMessageDecoder (padre_websocket_client.py)
- Декодирование бинарных сообщений
- Поддержка Base64, MessagePack, JSON
- Мультиплексированные протоколы

### 5. BundlerDataExtractor (padre_websocket_client.py)
- Извлечение данных о бандлерах
- Расчет процентов
- Идентификация контрактов

## 📊 WebSocket протокол trade.padre.gg

Система корректно обрабатывает:
- Аутентификационные сообщения (JWT токены)
- Подписки на данные токенов
- Бинарные сообщения с данными о бандлерах
- MessagePack кодирование
- Мультиплексированные каналы

## 🛠️ Отладка

### Логи
Все события записываются в `bundle_analyzer.log`:
- Подключения WebSocket
- Декодирование сообщений  
- Анализ бандлеров
- Отправка уведомлений
- Ошибки

### Уровни логирования
```bash
export LOG_LEVEL=DEBUG    # Подробная отладка
export LOG_LEVEL=INFO     # Обычная работа (по умолчанию)
export LOG_LEVEL=WARNING  # Только предупреждения
```

## 🔒 Безопасность

- Куки для trade.padre.gg обновляются автоматически
- Telegram токен хранится в переменных окружения
- Не передавайте .env файлы в git
- Используйте отдельные боты для тестирования

## 📈 Мониторинг

Система отслеживает:
- Состояние WebSocket соединений
- Количество обработанных токенов
- Успешность отправки уведомлений
- Ошибки декодирования сообщений

## 🚨 Решение проблем

### WebSocket не подключается
1. Проверьте доступность trade.padre.gg
2. Обновите куки в конфигурации
3. Проверьте User-Agent и заголовки

### Не приходят токены
1. Проверьте Jupiter WebSocket URL
2. Используйте тестовый режим (USE_JUPITER=false)
3. Проверьте логи на ошибки парсинга

### Не отправляются уведомления
1. Проверьте TELEGRAM_TOKEN
2. Убедитесь что бот в группе и имеет права
3. Проверьте TARGET_CHAT_ID и TARGET_THREAD_ID

## 📞 Поддержка

При возникновении проблем:
1. Запустите тестирование: `python3 test_bundle_analyzer.py`
2. Проверьте логи в `bundle_analyzer.log`
3. Используйте режим отладки: `LOG_LEVEL=DEBUG`

---

**Bundle Analyzer** готов к работе! 🎉

Для анализа бандлеров новых токенов с отправкой уведомлений в Telegram группу https://t.me/c/2680160752/13134 при превышении настраиваемого порога (по умолчанию 10%). 