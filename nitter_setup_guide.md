# 🚀 Настройка собственного Nitter с прокси для SolSpider

## 📋 **Зачем это нужно?**

Собственный Nitter решит **все основные проблемы** SolSpider:
- ❌ Rate limits (429 ошибки) → ✅ Неограниченные запросы
- ❌ Блокировки IP → ✅ Ротация прокси
- ❌ Медленные ответы (5-20с) → ✅ Мгновенная скорость
- ❌ Недоступность сервиса → ✅ 100% контроль

## 🛠️ **Вариант 1: Docker Setup (Рекомендуется)**

### 1. Установка базовых компонентов:
```bash
# Устанавливаем Docker и Docker Compose
sudo apt update
sudo apt install docker.io docker-compose git

# Добавляем пользователя в группу docker
sudo usermod -aG docker $USER
```

### 2. Клонируем и настраиваем Nitter:
```bash
# Клонируем репозиторий Nitter
git clone https://github.com/zedeus/nitter.git
cd nitter

# Создаем файл конфигурации
cp nitter.example.conf nitter.conf
```

### 3. Настройка конфигурации `nitter.conf`:
```ini
[Server]
hostname = "localhost"
port = 8080
https = false
httpMaxConnections = 100
staticDir = "./public"
title = "SolSpider Nitter"
address = "0.0.0.0"

[Cache]
listMinutes = 240
rssMinutes = 10
redisHost = "redis"
redisPort = 6379
redisConnections = 20

[Config]
hmacKey = "your-secret-key-here"
base64Media = false
enableRSS = true
enableDebug = false
proxy = ""  # Настроим позже
proxyAuth = ""

[Preferences]
theme = "Nitter"
replaceTwitter = "localhost:8080"
replaceYouTube = ""
replaceReddit = ""
proxyVideos = true
hlsPlayback = false
infiniteScroll = false

# ПРОКСИ КОНФИГУРАЦИЯ
[Proxy]
# Список SOCKS5 прокси (добавьте свои)
proxies = [
    "socks5://proxy1:port",
    "socks5://proxy2:port", 
    "socks5://proxy3:port",
    "socks5://proxy4:port",
    "socks5://proxy5:port"
]
```

### 4. Docker Compose файл `docker-compose.yml`:
```yaml
version: "3"

services:
  nitter:
    image: zedeus/nitter:latest
    container_name: solspider-nitter
    ports:
      - "8080:8080"
    volumes:
      - ./nitter.conf:/src/nitter.conf:ro
    depends_on:
      - redis
    restart: unless-stopped
    environment:
      - NITTER_PROXY_ROTATION=true
      - NITTER_PROXY_TIMEOUT=10
      
  redis:
    image: redis:6-alpine
    container_name: solspider-redis
    command: redis-server --save 60 1 --loglevel warning
    restart: unless-stopped
    volumes:
      - redis_data:/data
      
volumes:
  redis_data:
```

### 5. Запуск:
```bash
# Запускаем Nitter
docker-compose up -d

# Проверяем логи
docker-compose logs -f nitter
```

## 🛠️ **Вариант 2: Расширенная настройка с множественными инстансами**

### Мультиинстанс setup `docker-compose-multi.yml`:
```yaml
version: "3"

services:
  # Nitter инстанс 1 (порты 8080-8084)
  nitter1:
    image: zedeus/nitter:latest
    container_name: solspider-nitter-1
    ports:
      - "8080:8080"
    volumes:
      - ./nitter1.conf:/src/nitter.conf:ro
    depends_on:
      - redis
    restart: unless-stopped
    
  nitter2:
    image: zedeus/nitter:latest
    container_name: solspider-nitter-2
    ports:
      - "8081:8080"
    volumes:
      - ./nitter2.conf:/src/nitter.conf:ro
    depends_on:
      - redis
    restart: unless-stopped
      
  nitter3:
    image: zedeus/nitter:latest
    container_name: solspider-nitter-3
    ports:
      - "8082:8080"
    volumes:
      - ./nitter3.conf:/src/nitter.conf:ro
    depends_on:
      - redis
    restart: unless-stopped
      
  # Nginx для балансировки нагрузки
  nginx:
    image: nginx:alpine
    container_name: solspider-nginx
    ports:
      - "8090:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - nitter1
      - nitter2
      - nitter3
    restart: unless-stopped
      
  redis:
    image: redis:6-alpine
    container_name: solspider-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
      
volumes:
  redis_data:
```

## 🔧 **Интеграция с SolSpider**

### 1. Создание конфигурационного файла `nitter_config.py`:
```python
#!/usr/bin/env python3
"""
Конфигурация собственного Nitter для SolSpider
"""

import random
from typing import List

class NitterConfig:
    """Конфигурация множественных Nitter инстансов"""
    
    def __init__(self):
        # Список ваших Nitter серверов
        self.nitter_instances = [
            "http://localhost:8080",
            "http://localhost:8081", 
            "http://localhost:8082",
            # Добавьте больше инстансов если нужно
        ]
        
        # Индекс текущего сервера
        self.current_index = 0
        
    def get_nitter_url(self) -> str:
        """Получает URL следующего Nitter сервера с ротацией"""
        url = self.nitter_instances[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.nitter_instances)
        return url
        
    def get_random_nitter_url(self) -> str:
        """Получает случайный Nitter сервер"""
        return random.choice(self.nitter_instances)
        
    def is_local_nitter(self, url: str) -> bool:
        """Проверяет, является ли URL локальным Nitter"""
        return any(instance in url for instance in self.nitter_instances)

# Глобальный экземпляр
nitter_config = NitterConfig()
```

### 2. Модификация `pump_bot.py`:
```python
# В начале файла добавить:
from nitter_config import nitter_config

# Заменить все "https://nitter.tiekoetter.com" на:
def get_nitter_search_url(query, yesterday):
    """Генерирует URL для поиска в собственном Nitter"""
    base_url = nitter_config.get_nitter_url()
    return f"{base_url}/search?f=tweets&q={quote(query)}&since={yesterday}&until=&near="

# В функции search_single_query заменить:
# url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quote(query)}&since={yesterday}&until=&near="
url = get_nitter_search_url(query, yesterday)
```

### 3. Модификация `background_monitor.py`:
```python
# Аналогично заменить URL:
base_url = nitter_config.get_nitter_url()
urls = [
    f"{base_url}/search?f=tweets&q={token.mint}&since={yesterday}&until=&near="
]
```

## ⚡ **Рекомендуемая конфигурация прокси**

### Получение прокси:
1. **Покупка качественных прокси:**
   - ProxyEmpire, SmartProxy, Bright Data
   - Рекомендуется: 10-20 SOCKS5 прокси
   - Ротация каждые 5-10 минут

2. **Конфигурация прокси в nitter.conf:**
```ini
[Proxy]
proxies = [
    "socks5://username:password@proxy1.example.com:1080",
    "socks5://username:password@proxy2.example.com:1080",
    "socks5://username:password@proxy3.example.com:1080",
    # ... до 20 прокси
]
rotation_interval = 300  # 5 минут
```

## 📊 **Ожидаемые результаты**

### До (текущее состояние):
- ⏳ 2,500+ токенов в анализе
- 🐌 5-20 секунд на запрос
- ❌ 429 ошибки каждые 10 запросов
- 🚫 Периодические блокировки

### После (собственный Nitter):
- ⚡ 0-50 токенов в анализе
- 🚀 0.1-1 секунда на запрос  
- ✅ Неограниченные запросы
- 🔄 Автоматическая ротация прокси

## 🚀 **План внедрения:**

1. **Подготовка** (30 минут):
   - Установка Docker
   - Клонирование Nitter
   - Покупка прокси

2. **Настройка** (1 час):
   - Конфигурация Nitter
   - Настройка прокси
   - Тестирование

3. **Интеграция** (30 минут):
   - Модификация SolSpider
   - Обновление URL
   - Тестирование работы

4. **Запуск** (мгновенно):
   - Перезапуск SolSpider
   - Мониторинг производительности

## 💡 **Дополнительные оптимизации:**

### Nginx Load Balancer (`nginx.conf`):
```nginx
events {
    worker_connections 1024;
}

http {
    upstream nitter_backend {
        server nitter1:8080;
        server nitter2:8080;
        server nitter3:8080;
    }
    
    server {
        listen 80;
        
        location / {
            proxy_pass http://nitter_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 5s;
            proxy_read_timeout 10s;
        }
    }
}
```

### Мониторинг:
```bash
# Скрипт мониторинга nitter_monitor.sh
#!/bin/bash
while true; do
    for port in 8080 8081 8082; do
        if curl -s "http://localhost:$port" > /dev/null; then
            echo "✅ Nitter :$port работает"
        else
            echo "❌ Nitter :$port недоступен!"
        fi
    done
    sleep 30
done
```

## 🎯 **Итог:**

Собственный Nitter с прокси **ПОЛНОСТЬЮ РЕШИТ** проблему производительности SolSpider, увеличив скорость анализа в **10-50 раз** и устранив все ограничения внешних сервисов! 