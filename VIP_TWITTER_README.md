# 🌟 VIP TWITTER MONITOR 🌟

Независимый парсер VIP аккаунтов Twitter для мгновенных сигналов о Solana токенах.

## 📋 Описание

VIP Twitter Monitor - это автономная система мониторинга избранных Twitter аккаунтов для обнаружения упоминаний контрактов Solana токенов. Система работает независимо от основной SolSpider архитектуры и предназначена для получения мгновенных VIP сигналов.

## ⭐ Основные возможности

- 🔍 **Мониторинг VIP аккаунтов** в реальном времени
- 🎯 **Поиск контрактов Solana** в твитах
- 💰 **Автоматическая покупка** для указанных аккаунтов  
- 📱 **VIP уведомления** в отдельного Telegram бота
- 🔄 **Ротация cookies** для обхода ограничений Nitter
- 🛡️ **Дедупликация сигналов** для избежания дублирования
- ⚙️ **Гибкая конфигурация** через отдельный файл настроек

## 📁 Структура файлов

```
solspider/
├── vip_twitter_monitor.py    # Основной модуль VIP мониторинга
├── vip_config.py            # Конфигурация VIP аккаунтов
└── VIP_TWITTER_README.md     # Документация (этот файл)
```

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install aiohttp requests beautifulsoup4 asyncio
```

### 2. Настройка переменных окружения

Добавьте в `.env` файл:

```bash
VIP_CHAT_ID=your_vip_telegram_chat_id
```

### 3. Настройка VIP аккаунтов

Отредактируйте `vip_config.py`:

```python
VIP_TWITTER_ACCOUNTS = {
    'your_vip_account': {
        'enabled': True,
        'description': 'Описание аккаунта',
        'priority': 'HIGH',
        'auto_buy': True,  # Включить автопокупку
        'buy_amount_usd': 1000.0,
        'check_interval': 30
    }
}
```

### 4. Запуск мониторинга

```bash
python vip_twitter_monitor.py
```

## ⚙️ Конфигурация

### VIP аккаунты (`VIP_TWITTER_ACCOUNTS`)

```python
{
    'username': {
        'enabled': bool,              # Включен ли аккаунт
        'description': str,           # Описание для уведомлений
        'priority': str,              # HIGH, ULTRA, MEDIUM
        'auto_buy': bool,            # Автоматическая покупка
        'buy_amount_usd': float,     # Сумма для автопокупки
        'check_interval': int,       # Интервал проверки (сек)
        'notify_unknown_contracts': bool,  # Уведомлять о неизвестных
        'bypass_filters': bool       # Обходить фильтры
    }
}
```

### Настройки мониторинга (`VIP_MONITOR_SETTINGS`)

- `default_check_interval`: Базовый интервал проверки (30 сек)
- `max_retries`: Максимум попыток при ошибках (3)
- `cache_cleanup_threshold`: Очистка кэша при превышении (1000)
- `request_timeout`: Таймаут запросов к Nitter (15 сек)
- `log_level`: Уровень логирования ('INFO')

### Автопокупка (`AUTO_BUY_CONFIG`)

- `enabled_accounts`: Список аккаунтов с автопокупкой
- `default_amount_usd`: Сумма по умолчанию (100 USD)
- `max_amount_usd`: Максимальная сумма (2000 USD)
- `simulate_only`: Только симуляция (True для тестирования)

## 📱 Telegram настройки

### VIP бот конфигурация

```python
VIP_TELEGRAM_CONFIG = {
    'bot_token': "your_vip_bot_token",
    'chat_id_env_var': 'VIP_CHAT_ID',
    'parse_mode': 'HTML',
    'timeout': 10
}
```

### Пример уведомления

```
🌟 VIP TWITTER СИГНАЛ! 🌟

🔥 Сильный инфлюенсер - мгновенные сигналы
👤 От: @MoriCoinCrypto

📍 Контракт: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
📱 Твит: New token launch! Check out this amazing project...

⚡ МГНОВЕННЫЙ VIP СИГНАЛ!
🎯 Приоритет: HIGH
🚀 Время действовать СЕЙЧАС!
🕐 Время: 15:42:33

💰 АВТОМАТИЧЕСКАЯ ПОКУПКА ВЫПОЛНЕНА!
✅ Статус: Симуляция - успешно выполнено
💵 Сумма: $1062.5
⚡ Время: 2.00с
🔗 TX: mock_tx_1736435753
```

## 🔧 Независимость от основной системы

VIP Twitter Monitor полностью независим от SolSpider:

- ✅ **Собственные cookies** - не влияет на основной бот
- ✅ **Отдельный Telegram бот** - VIP уведомления изолированы
- ✅ **Независимая конфигурация** - настройки в отдельном файле
- ✅ **Собственное логирование** - файл `vip_monitor.log`
- ✅ **Отдельные зависимости** - минимальный набор библиотек

## 📊 Мониторинг и логи

### Файлы логов

- `vip_monitor.log` - основные логи VIP мониторинга
- Консольный вывод с цветным форматированием

### Статистика работы

```
🔄 VIP мониторинг завершен за 2.45с. Следующая проверка через 30с
📱 Найдено 15 твитов у @MoriCoinCrypto
🔥 VIP КОНТРАКТ НАЙДЕН! @MoriCoinCrypto: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
```

## 🛠️ Расширение функциональности

### Добавление нового VIP аккаунта

1. Откройте `vip_config.py`
2. Добавьте новый аккаунт в `VIP_TWITTER_ACCOUNTS`:

```python
'new_vip_account': {
    'enabled': True,
    'description': 'Новый VIP аккаунт',
    'priority': 'HIGH',
    'auto_buy': False,
    'buy_amount_usd': 500.0,
    'check_interval': 60
}
```

### Интеграция реальной автопокупки

1. Установите `simulate_only: False` в `AUTO_BUY_CONFIG`
2. Реализуйте функцию `execute_automatic_purchase()` с интеграцией DEX API
3. Настройте приватные ключи и кошельки для торговли

### Добавление новых шаблонов сообщений

Отредактируйте `VIP_MESSAGE_TEMPLATES` в `vip_config.py`:

```python
'new_template': """🎯 НОВЫЙ ТИП СИГНАЛА!

📊 {custom_field}
💎 {another_field}"""
```

## 🔒 Безопасность

- 🛡️ **Изолированная среда** - не влияет на основной бот
- 🔐 **Раздельные токены** - отдельный VIP Telegram бот
- 🍪 **Собственные cookies** - независимая ротация
- 📝 **Отдельные логи** - изолированное логирование

## 🚨 Устранение неполадок

### Ошибка импорта конфигурации

```
❌ Не удалось импортировать vip_config.py
```

**Решение:** Убедитесь что `vip_config.py` находится в той же папке что и `vip_twitter_monitor.py`

### Блокировка Nitter

```
🚫 VIP мониторинг заблокирован для @username
```

**Решение:** Обновите cookies в `VIP_NITTER_COOKIES` в файле `vip_config.py`

### Ошибка Telegram

```
❌ VIP_CHAT_ID не задан в переменных окружения!
```

**Решение:** Добавьте `VIP_CHAT_ID=your_chat_id` в `.env` файл

## 📈 Производительность

- ⚡ **Параллельная проверка** всех VIP аккаунтов
- 🔄 **Эффективная ротация cookies** 
- 💾 **Умное кэширование** с автоочисткой
- ⏱️ **Настраиваемые интервалы** для каждого аккаунта

## 🎯 Примеры использования

### Только мониторинг без автопокупки

```python
'monitoring_only_account': {
    'enabled': True,
    'description': 'Только мониторинг',
    'priority': 'MEDIUM',
    'auto_buy': False,  # Отключить автопокупку
    'check_interval': 60
}
```

### VIP аккаунт с автопокупкой

```python
'auto_buy_account': {
    'enabled': True,
    'description': 'Автопокупка активна',
    'priority': 'HIGH',
    'auto_buy': True,  # Включить автопокупку
    'buy_amount_usd': 1500.0,
    'check_interval': 15  # Частая проверка
}
```

## 📞 Поддержка

Для получения помощи:

1. Проверьте логи в `vip_monitor.log`
2. Убедитесь что все зависимости установлены
3. Проверьте корректность конфигурации в `vip_config.py`
4. Убедитесь что `VIP_CHAT_ID` настроен в переменных окружения

---

🌟 **VIP Twitter Monitor** - мощный инструмент для получения мгновенных сигналов от избранных Twitter аккаунтов! 