# 🔄 Инструкция по восстановлению групп дубликатов

## 📋 Описание

Эта инструкция поможет восстановить группы дубликатов из Google Sheets и создать новые сообщения в Telegram с кнопками для просмотра таблиц.

## 🚀 Когда использовать

- Сообщения были отправлены без кнопок Google Sheets
- Бот был перезапущен и потерял информацию о группах
- Нужно восстановить связь между Google Sheets и Telegram сообщениями

## ⚡ Быстрый запуск

```bash
# Убедитесь что установлен TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN="your_bot_token_here"

# Запустите скрипт восстановления
python restore_groups.py
```

## 📊 Что происходит при восстановлении

1. **Поиск таблиц**: Скрипт ищет все существующие таблицы дубликатов в Google Sheets
2. **Загрузка данных**: Загружает данные токенов из таблиц
3. **Восстановление групп**: Создает объекты групп в памяти
4. **Анализ Twitter**: Определяет главные Twitter аккаунты
5. **Поиск анонсов**: Ищет официальные анонсы в Twitter
6. **Создание сообщений**: Создает новые сообщения в Telegram с кнопками

## 📋 Логи восстановления

```
🔄 Начинаем восстановление групп из Google Sheets...
📥 Загружаем все таблицы дубликатов в кэш...
📊 Загружено 15 таблиц в кэш
🔍 Восстанавливаем группу pump_PUMP...
✅ Группа pump_PUMP восстановлена (619 токенов, главный Twitter: @не определен)
🔄 Создаем новые сообщения с кнопками Google Sheets...
✅ Создано новое сообщение для группы PUMP с кнопкой Google Sheets
✅ Восстановление групп завершено успешно!
```

## 🎯 Результат

После восстановления:
- ✅ Все существующие таблицы Google Sheets связаны с группами в памяти
- ✅ Созданы новые сообщения в Telegram с кнопками Google Sheets
- ✅ Бот знает о всех группах и может продолжать работу
- ✅ Пользователи могут просматривать таблицы через кнопки

## 🔧 Настройки

В файле `restore_groups.py` можно изменить:
- `chat_id`: ID чата для отправки сообщений
- `thread_id`: ID темы для дубликатов
- Логирование и фильтры

## ⚠️ Важные моменты

1. **Дубликаты сообщений**: Скрипт создает НОВЫЕ сообщения, старые остаются без изменений
2. **Время выполнения**: Может занять несколько минут в зависимости от количества групп
3. **Ограничения API**: Соблюдает лимиты Google Sheets API и Telegram Bot API
4. **Безопасность**: Не изменяет существующие данные в таблицах

## 🛠️ Альтернативные методы

### Через Python консоль:
```python
import asyncio
from duplicate_groups_manager import get_duplicate_groups_manager, initialize_duplicate_groups_manager

# Инициализация
initialize_duplicate_groups_manager("your_telegram_token")
manager = get_duplicate_groups_manager()

# Восстановление
result = asyncio.run(manager.restore_groups_from_sheets_and_update_messages())
print(f"Восстановлено {len(result)} групп")
```

### Через основной бот:
```python
# Добавьте в main.py вызов восстановления при старте
await manager.restore_groups_from_sheets_and_update_messages()
```

## 📞 Поддержка

При проблемах проверьте:
- Правильность токена Telegram бота
- Доступность Google Sheets API
- Логи выполнения скрипта 