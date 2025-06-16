#!/usr/bin/env python3
"""
Конфигурация собственного Nitter для SolSpider
"""

import random
import os
from typing import List

class NitterConfig:
    """Конфигурация множественных Nitter инстансов"""
    
    def __init__(self):
        # Список ваших Nitter серверов (пока публичные для тестирования)
        self.nitter_instances = [
            "http://localhost:8080",  # Ваш локальный Nitter (когда настроите)
            "https://nitter.tiekoetter.com",  # Fallback на текущий
            "https://nitter.net",
            "https://nitter.it", 
            "https://nitter.unixfox.eu",
        ]
        
        # Индекс текущего сервера
        self.current_index = 0
        
        # Проверяем переменную окружения для локального Nitter
        local_nitter = os.getenv('LOCAL_NITTER_URL', '')
        if local_nitter:
            # Добавляем локальный Nitter в начало списка
            self.nitter_instances.insert(0, local_nitter)
        
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
        return "localhost" in url or "127.0.0.1" in url
        
    def get_primary_nitter(self) -> str:
        """Получает основной Nitter (первый в списке)"""
        return self.nitter_instances[0]

# Глобальный экземпляр
nitter_config = NitterConfig()

def get_nitter_search_url(query, yesterday, use_local=True):
    """Генерирует URL для поиска в Nitter с предпочтением локального"""
    if use_local and nitter_config.is_local_nitter(nitter_config.get_primary_nitter()):
        base_url = nitter_config.get_primary_nitter()
    else:
        base_url = nitter_config.get_nitter_url()
    
    from urllib.parse import quote
    return f"{base_url}/search?f=tweets&q={quote(query)}&since={yesterday}&until=&near="

def get_nitter_profile_url(username, use_local=True):
    """Генерирует URL для профиля в Nitter"""
    if use_local and nitter_config.is_local_nitter(nitter_config.get_primary_nitter()):
        base_url = nitter_config.get_primary_nitter()
    else:
        base_url = nitter_config.get_nitter_url()
    
    return f"{base_url}/{username}" 