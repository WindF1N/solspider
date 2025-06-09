# 🔧 Устранение проблем SolSpider

## 🌐 Проблемы с WebSocket соединением

### Ошибка "keepalive ping timeout"

**Симптомы:**
```
[20:49:05] WARNING: ⚠️ Соединение закрыто: sent 1011 (unexpected error) keepalive ping timeout; no close frame received
```

**✅ ИСПРАВЛЕНО** - начиная с версии с новым фильтром, эта ошибка обрабатывается автоматически с быстрым переподключением (5 секунд вместо 10).

**Причины:**
- Нестабильное интернет-соединение
- Проблемы с сетью провайдера  
- Высокая загруженность сервера pump.fun
- Проблемы с NAT/firewall

**Решения:**

#### 1. Проверка сетевого соединения
```bash
# Проверить ping до внешних серверов
ping google.com
ping pump.fun

# Проверить качество соединения
traceroute pump.fun
```

#### 2. Настройка сетевых параметров (Linux)
```bash
# Увеличить таймауты TCP
echo 'net.ipv4.tcp_keepalive_time = 120' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_keepalive_intvl = 30' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_keepalive_probes = 3' >> /etc/sysctl.conf
sysctl -p
```

#### 3. Использование VPN или прокси
```bash
# Если проблема с провайдером, попробуйте VPN
# Например, через OpenVPN или WireGuard
```

#### 4. Настройки брандмауэра
```bash
# Ubuntu/Debian - разрешить исходящие WebSocket соединения
sudo ufw allow out 443/tcp
sudo ufw allow out 80/tcp

# CentOS/RHEL
sudo firewall-cmd --zone=public --add-service=https --permanent
sudo firewall-cmd --reload
```

### Ошибка "Connection reset by peer"

**Решения:**
- Проверить стабильность интернета
- Попробовать запуск с другого сервера/локации
- Использовать тунель через стабильный сервер

### Частые переподключения

**Проверка логов:**
```bash
# Смотрим статистику соединений
tail -f logs/solspider.log | grep "Соединение"

# Анализируем ошибки
grep -i "error\|warning" logs/errors.log | tail -20
```

**Настройка WebSocket таймаутов:**
Отредактируйте `pump_bot.py`, изменив `WEBSOCKET_CONFIG`:
```python
WEBSOCKET_CONFIG = {
    'ping_interval': 60,     # Увеличить до 60 секунд
    'ping_timeout': 30,      # Увеличить до 30 секунд
    'close_timeout': 20,     # Увеличить таймаут закрытия
    'heartbeat_check': 600,  # Проверять реже (10 минут)
}
```

## 🗃️ Проблемы с базой данных

### Ошибка подключения к MySQL

**Проверка статуса MySQL:**
```bash
# Проверить запущен ли MySQL
sudo systemctl status mysql
# или
sudo systemctl status mariadb

# Запустить если остановлен
sudo systemctl start mysql
```

**Проверка подключения:**
```bash
# Проверить подключение к базе
mysql -u solspider -p solspider

# Проверить права пользователя
mysql -u root -p
> SHOW GRANTS FOR 'solspider'@'localhost';
```

**Решение проблем с правами:**
```sql
-- В MySQL консоли от имени root
GRANT ALL PRIVILEGES ON solspider.* TO 'solspider'@'localhost';
FLUSH PRIVILEGES;
```

### Ошибки с таблицами

**Пересоздание таблиц:**
```bash
# Сделать резервную копию
mysqldump -u solspider -p solspider > backup_$(date +%Y%m%d).sql

# Пересоздать таблицы
python -c "from database import get_db_manager; get_db_manager()"
```

## 📝 Проблемы с логированием

### Папка logs не создается

```bash
# Создать папку вручную
mkdir -p logs
chmod 755 logs

# Проверить права
ls -la logs/
```

### Логи не ротируются

**Проверка размера логов:**
```bash
du -sh logs/*
```

**Ручная очистка:**
```bash
# Архивировать старые логи
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
# Удалить старые файлы
find logs/ -name "*.log" -mtime +7 -delete
```

## 🔄 Проблемы с автозапуском

### Systemd служба не запускается

**Проверка статуса:**
```bash
sudo systemctl status pump-bot
sudo journalctl -u pump-bot -f
```

**Типичные проблемы:**
1. Неправильный путь в ExecStart
2. Отсутствие .env файла
3. Нет прав на запись в logs/

**Исправление службы:**
```ini
[Unit]
Description=SolSpider Pump.fun Bot
After=network.target mysql.service

[Service]
Type=simple
User=yourusername
WorkingDirectory=/full/path/to/solspider
ExecStart=/full/path/to/solspider/venv/bin/python pump_bot.py
Restart=always
RestartSec=10
Environment=PATH=/full/path/to/solspider/venv/bin

[Install]
WantedBy=multi-user.target
```

## 📊 Мониторинг и диагностика

### Команды для диагностики

```bash
# Статистика базы данных
python analyze_data.py

# Просмотр активных соединений
netstat -an | grep ESTABLISHED

# Мониторинг использования ресурсов
top -p $(pgrep -f pump_bot.py)

# Проверка свободного места
df -h
```

### Автоматический мониторинг

**Cron задачи для проверки:**
```bash
# Добавить в crontab
crontab -e

# Проверять каждые 5 минут
*/5 * * * * /path/to/check_bot.sh

# Ежедневная очистка логов
0 2 * * * find /path/to/logs -name "*.log" -mtime +30 -delete
```

**Скрипт check_bot.sh:**
```bash
#!/bin/bash
if ! pgrep -f "pump_bot.py" > /dev/null; then
    echo "$(date): Bot not running, restarting..." >> /var/log/solspider_monitor.log
    cd /path/to/solspider
    ./start_bot.sh &
fi
```

## 🆘 Экстренные действия

### Полная переустановка

```bash
# Остановить бота
pkill -f pump_bot.py

# Сохранить данные
mysqldump -u solspider -p solspider > emergency_backup.sql
cp -r logs logs_backup

# Обновить код
git pull

# Переустановить зависимости
pip install -r requirements.txt --upgrade

# Запустить
./start_bot.sh
```

### Откат к предыдущей версии

```bash
# Посмотреть коммиты
git log --oneline -10

# Откатиться к рабочей версии
git checkout <commit_hash>

# Запустить
./start_bot.sh
```

## 📞 Получение помощи

1. **Проверьте логи:** `tail -f logs/errors.log`
2. **Статистика соединения:** Бот отправляет автоматически
3. **Анализ данных:** `python analyze_data.py`
4. **Системные ресурсы:** `htop`, `df -h`, `free -h`

При сохранении проблем:
- Сохраните логи: `tar -czf debug_logs.tar.gz logs/`
- Опишите конфигурацию системы
- Укажите время возникновения проблемы 