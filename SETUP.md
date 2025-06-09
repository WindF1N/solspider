# 🛠️ Подробная настройка проекта

## 📋 Предварительные требования

- Python 3.8+ 
- Telegram аккаунт
- Интернет соединение

## 🤖 Создание Telegram бота

### Шаг 1: Создание бота
1. Откройте Telegram и найдите [@BotFather](https://t.me/botfather)
2. Отправьте команду `/newbot`
3. Введите название вашего бота (например: "My Pump Bot")
4. Введите username бота (должен заканчиваться на "bot", например: "my_pump_bot")
5. Скопируйте полученный токен

### Шаг 2: Получение Chat ID
1. Откройте [@userinfobot](https://t.me/userinfobot) 
2. Отправьте любое сообщение
3. Скопируйте ваш ID из ответа

## ⚙️ Настройка проекта

### Шаг 1: Клонирование
```bash
git clone https://github.com/your-username/pump-fun-telegram-bot
cd pump-fun-telegram-bot
```

### Шаг 2: Настройка переменных окружения
```bash
# Скопируйте пример файла
cp .env.example .env

# Отредактируйте файл .env
nano .env
```

Вставьте ваши данные:
```
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVwxyz
CHAT_ID=123456789
```

### Шаг 3: Установка и запуск
```bash
# Сделайте скрипт исполняемым
chmod +x start_bot.sh

# Запустите бота
./start_bot.sh
```

## 🔧 Возможные проблемы

### macOS: externally-managed-environment
Скрипт автоматически создает виртуальное окружение

### Ошибка "Module not found"
```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

### Бот не отвечает
1. Проверьте правильность токена
2. Убедитесь что бот запущен (`/start` в Telegram)
3. Проверьте Chat ID

## 📊 Мониторинг

### Просмотр логов
```bash
tail -f pump_bot.log
```

### Остановка бота
```bash
# Нажмите Ctrl+C в терминале где запущен бот
# Или найдите процесс:
ps aux | grep pump_bot
kill <PID>
```

## 🚀 Автозапуск (Linux/macOS)

### Создание systemd службы (Linux)
```bash
sudo nano /etc/systemd/system/pump-bot.service
```

Содержимое файла:
```ini
[Unit]
Description=Pump.fun Telegram Bot
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/pump-fun-telegram-bot
ExecStart=/path/to/pump-fun-telegram-bot/venv/bin/python pump_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Активация:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pump-bot
sudo systemctl start pump-bot
```

### Использование screen (Linux/macOS)
```bash
# Запуск в фоновом режиме
screen -S pump-bot ./start_bot.sh

# Отключение (Ctrl+A, затем D)
# Подключение обратно
screen -r pump-bot
``` 