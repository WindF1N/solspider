#!/usr/bin/env python3
"""
Продвинутая система управления группами токенов (включая одиночные токены)
Интеграция с Google Sheets, умные Telegram сообщения, отслеживание официальных контрактов

🌍 НОВАЯ ФУНКЦИОНАЛЬНОСТЬ - ГЛОБАЛЬНЫЙ ПОИСК:
=====================================

Система теперь обрабатывает токены БЕЗ Twitter ссылок через глобальный поиск:

1. 🔍 Если токены в группе НЕ имеют Twitter ссылок, система автоматически:
   - Выполняет глобальный поиск по символу токена на Nitter (с автоматической ротацией доменов)
   - Ищет все аккаунты, которые упоминали символ токена с $ (например "$MORI")
   - Проверяет каждый найденный аккаунт на наличие контрактов и свежесть твитов
   - Выбирает главный Twitter аккаунт из найденных (без контрактов, со свежими твитами)

2. 🎯 Те же проверки что и для обычных токенов:
   - Проверка на наличие контрактов в Twitter (исключает аккаунты с контрактами)
   - Проверка свежести твитов (только твиты младше 30 дней)
   - Поиск официального анонса токена (самый старый твит с символом)

3. 💬 Отправка сообщений:
   - Группы найденные через глобальный поиск отправляются в ЛИЧНЫЙ ЧАТ (ID: 7891524244)
   - Обычные группы отправляются в групповой чат как и раньше
   - Флаг is_global_search_group помечает такие группы

4. 🔄 Автоматическое решение Anubis Challenge:
   - Если Nitter заблокирован, система автоматически решает challenge
   - Используется та же логика что и для обычных запросов к аккаунтам
   - Поддержка смены прокси при необходимости

5. 📊 Google Sheets:
   - Создаются те же таблицы что и для обычных токенов
   - Главный Twitter помечается как найденный через глобальный поиск
   - Полная интеграция с существующей системой

ИСПОЛЬЗОВАНИЕ:
=============
Система автоматически активируется при обработке токенов без Twitter ссылок.
Никаких дополнительных действий не требуется - все работает через existing
процесс обработки дубликатов в pump_bot.py.
"""
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import Counter
import json
import re
import time
import random
from queue import Queue
from threading import Thread
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote

# Импорты проекта
from google_sheets_manager import sheets_manager
from database import get_db_manager, DuplicateToken, Token
from dynamic_cookie_rotation import get_next_proxy_cookie_async, mark_proxy_temp_blocked
from anubis_handler import handle_anubis_challenge_for_session, update_cookies_in_string
from twitter_profile_parser import TwitterProfileParser
from nitter_domain_rotator import get_next_nitter_domain, record_nitter_request_result

logger = logging.getLogger(__name__)

# Список проблемных доменов Nitter, которые часто дают ошибки
PROBLEMATIC_NITTER_DOMAINS = {
    # Домены с частыми 503/502 ошибками можно добавить здесь
}

def get_nitter_base_url():
    """Получает базовый URL для Nitter с использованием ротации доменов"""
    domain = get_next_nitter_domain()
    
    # Для обычных доменов используем HTTPS
    if domain.startswith("nitter."):
        return f"https://{domain}"
    # Для IP-адресов используем HTTP
    else:
        return f"http://{domain}"

def get_nitter_domain_and_url():
    """Получает домен и URL для Nitter с использованием ротации доменов"""
    domain = get_next_nitter_domain()
    
    # Для обычных доменов используем HTTPS
    if domain.startswith("nitter."):
        url = f"https://{domain}"
    # Для IP-адресов используем HTTP
    else:
        url = f"http://{domain}"
    
    return domain, url

def format_nitter_url(domain: str) -> str:
    """Форматирует URL для конкретного домена"""
    # Для обычных доменов используем HTTPS
    if domain.startswith("nitter."):
        return f"https://{domain}"
    # Для IP-адресов используем HTTP
    else:
        return f"http://{domain}"

def add_host_header_if_needed(headers: Dict, domain: str) -> None:
    """Добавляет заголовок Host для специальных IP-адресов"""
    # Специальный заголовок Host для IP nitter.space
    if domain == "89.252.140.174":
        headers['Host'] = 'nitter.space'
        logger.debug(f"🌐 Добавлен заголовок Host: nitter.space для {domain}")

# 🛡️ УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ВСЕХ СЕТЕВЫХ ОШИБОК
async def network_retry_wrapper(session, method, url, max_retries=20, **kwargs):
    """
    Универсальная функция для агрессивных повторных попыток при ЛЮБЫХ сетевых ошибках
    С интеграцией доменной ротации и записью статистики
    
    Обрабатывает:
    - Server disconnected
    - Connection reset by peer  
    - Cannot connect to host
    - Timeout errors
    - SSL errors
    - DNS errors
    - Любые другие сетевые ошибки
    """
    import time
    from urllib.parse import urlparse
    
    start_time = time.time()
    NETWORK_ERRORS = [
        "Server disconnected",
        "Connection reset by peer", 
        "Cannot connect to host",
        "Connection timed out",
        "Timeout",
        "SSL", 
        "Name resolution failed",
        "Network is unreachable",
        "Connection refused",
        "Connection aborted",
        "Broken pipe",
        "No route to host",
        "Host is unreachable",
        "Connection closed",
        "Connection lost",
        "Socket error",
        "ClientConnectorError",
        "ClientError",
        "ServerDisconnectedError",
        "ClientOSError",
        "TooManyRedirects",
        "Can not decode content-encoding: brotli"
    ]
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Выполняем HTTP запрос
            if method.lower() == 'get':
                async with session.get(url, **kwargs) as response:
                    # Читаем содержимое чтобы избежать проблем с connection pooling
                    await response.read()
                    
                    # Записываем результат в статистику доменной ротации
                    response_time = time.time() - start_time
                    parsed_url = urlparse(url)
                    if 'nitter' in parsed_url.netloc:
                        domain = parsed_url.netloc
                        success = response.status == 200
                        record_nitter_request_result(domain, success, response_time, response.status)
                        
                    return response
            elif method.lower() == 'post':
                async with session.post(url, **kwargs) as response:
                    await response.read()
                    
                    # Записываем результат в статистику доменной ротации
                    response_time = time.time() - start_time
                    parsed_url = urlparse(url)
                    if 'nitter' in parsed_url.netloc:
                        domain = parsed_url.netloc
                        success = response.status == 200
                        record_nitter_request_result(domain, success, response_time, response.status)
                        
                    return response
            else:
                raise ValueError(f"Unsupported method: {method}")
                
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Записываем ошибку в статистику доменной ротации
            response_time = time.time() - start_time
            parsed_url = urlparse(url)
            if 'nitter' in parsed_url.netloc:
                domain = parsed_url.netloc
                # Определяем тип ошибки для статистики
                if '429' in error_str:
                    status_code = 429
                elif '502' in error_str or 'bad gateway' in error_str:
                    status_code = 502
                else:
                    status_code = None
                record_nitter_request_result(domain, False, response_time, status_code)
            
            # Проверяем является ли это сетевой ошибкой (включая 502, 429, 500, 403, 503)
            is_network_error = any(net_err.lower() in error_str for net_err in NETWORK_ERRORS) or \
                             '502' in error_str or 'bad gateway' in error_str or \
                             '429' in error_str or '500' in error_str or '403' in error_str or '503' in error_str
            
            if is_network_error:
                # Уменьшаем задержку для быстрых HTTP ошибок (403, 429, 500, 503)
                if any(err in error_str for err in ['429', '500', '403', '503', 'toomanyredirects', 'brotli']):
                    backoff_time = min(15, (attempt + 1) * 1 + random.uniform(0.5, 2))  # Быстрое восстановление
                else:
                    backoff_time = min(60, (attempt + 1) * 2 + random.uniform(1, 5))  # Обычная задержка
                    
                logger.warning(f"🔥 СЕТЕВАЯ ОШИБКА (попытка {attempt + 1}/{max_retries}): {e}")
                logger.warning(f"⏳ Ждем {backoff_time:.1f}с перед повтором...")
                
                # При TooManyRedirects, 429, 500, 403, 503, Brotli переключаем ДОМЕН быстро
                if any(err in error_str for err in ['toomanyredirects', '429', '500', '403', '503', 'brotli']):
                    error_type = "TooManyRedirects" if 'toomanyredirects' in error_str else f"HTTP {error_str}"
                    logger.warning(f"🔄 {error_type} - быстро переключаем домен Nitter")
                    try:
                        # Агрессивно пропускаем проблемные домены
                        for _ in range(10):  # Увеличиваем попытки поиска хорошего домена
                            new_domain = get_next_nitter_domain()
                            if new_domain and new_domain not in PROBLEMATIC_NITTER_DOMAINS:
                                break
                        else:
                            logger.warning(f"⚠️ Не удалось найти непроблемный домен, используем любой")
                            new_domain = get_next_nitter_domain()
                            
                        if new_domain and 'nitter' in parsed_url.netloc:
                            # Заменяем домен в URL
                            new_base_url = format_nitter_url(new_domain)
                            url = f"{new_base_url}{parsed_url.path}"
                            if parsed_url.query:
                                url += f"?{parsed_url.query}"
                            logger.info(f"🌐 Переключились на новый домен: {new_domain}")
                    except Exception as domain_error:
                        logger.warning(f"⚠️ Ошибка переключения домена: {domain_error}")
                else:
                    # Получаем новый прокси при других сетевых ошибках
                    if 'proxy' in kwargs:
                        try:
                            proxy, cookie = await get_next_proxy_cookie_async(session)
                            if proxy:
                                kwargs['proxy'] = proxy
                            if 'headers' in kwargs and cookie:
                                kwargs['headers']['Cookie'] = cookie
                            logger.info(f"🔄 Переключились на новый прокси для повтора")
                        except:
                            pass
                
                await asyncio.sleep(backoff_time)
                continue
            else:
                # Не сетевая ошибка - пробрасываем дальше
                raise e
    
    # Если все попытки исчерпаны
    logger.error(f"💀 ВСЕ {max_retries} ПОПЫТОК ИСЧЕРПАНЫ. Последняя ошибка: {last_error}")
    raise last_error

class TelegramMessageQueue:
    """Очередь для сообщений Telegram с rate limiting"""
    
    def __init__(self, telegram_token: str):
        self.telegram_token = telegram_token
        self.telegram_url = f"https://api.telegram.org/bot{telegram_token}"
        self.queue = Queue()
        self.running = True
        self.worker_thread = None
        self.min_delay = 2.0  # минимальная задержка в секундах
        self.max_delay = 4.0  # максимальная задержка в секундах
        self.last_request_time = 0
        
    def start(self):
        """Запускает обработчик очереди"""
        if self.worker_thread is None:
            self.worker_thread = Thread(target=self._process_queue, daemon=True)
            self.worker_thread.start()
            logger.info("✅ Очередь Telegram сообщений запущена")
    
    def stop(self):
        """Останавливает обработчик очереди"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
            logger.info("⏹️ Очередь Telegram сообщений остановлена")
    
    def _process_queue(self):
        """Обрабатывает очередь сообщений с задержкой"""
        while self.running:
            try:
                if not self.queue.empty():
                    # Получаем задачу из очереди
                    task = self.queue.get(timeout=1)
                    
                    # Рассчитываем задержку
                    current_time = time.time()
                    time_since_last = current_time - self.last_request_time
                    
                    # Случайная задержка между min_delay и max_delay
                    delay = random.uniform(self.min_delay, self.max_delay)
                    
                    # Если прошло меньше задержки, ждем
                    if time_since_last < delay:
                        sleep_time = delay - time_since_last
                        time.sleep(sleep_time)
                    
                    # Выполняем запрос
                    self._execute_request(task)
                    self.last_request_time = time.time()
                    
                    # Помечаем задачу как выполненную
                    self.queue.task_done()
                else:
                    # Если очередь пуста, ждем немного
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике очереди Telegram: {e}")
                time.sleep(1)
    
    def _execute_request(self, task: Dict):
        """Выполняет HTTP запрос к Telegram API"""
        try:
            method = task['method']
            payload = task['payload']
            callback = task.get('callback')
            
            response = requests.post(f"{self.telegram_url}/{method}", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                if callback:
                    callback(True, result)
                logger.debug(f"✅ Telegram API {method} успешно выполнен")
            else:
                error_text = response.text
                if callback:
                    callback(False, error_text)
                logger.error(f"❌ Ошибка Telegram API {method}: {error_text}")
                
        except Exception as e:
            if task.get('callback'):
                task['callback'](False, str(e))
            logger.error(f"❌ Ошибка выполнения Telegram запроса: {e}")
    
    def send_message(self, payload: Dict, callback=None):
        """Добавляет сообщение в очередь"""
        task = {
            'method': 'sendMessage',
            'payload': payload,
            'callback': callback
        }
        self.queue.put(task)
        logger.debug(f"📤 Сообщение добавлено в очередь (размер: {self.queue.qsize()})")
    
    def edit_message(self, payload: Dict, callback=None):
        """Добавляет редактирование сообщения в очередь"""
        task = {
            'method': 'editMessageText',
            'payload': payload,
            'callback': callback
        }
        self.queue.put(task)
        logger.debug(f"✏️ Редактирование сообщения добавлено в очередь (размер: {self.queue.qsize()})")
    
    def delete_message(self, payload: Dict, callback=None):
        """Добавляет удаление сообщения в очередь"""
        task = {
            'method': 'deleteMessage',
            'payload': payload,
            'callback': callback
        }
        self.queue.put(task)
        logger.debug(f"🗑️ Удаление сообщения добавлено в очередь (размер: {self.queue.qsize()})")
    
    def get_queue_size(self) -> int:
        """Возвращает размер очереди"""
        return self.queue.qsize()

class DuplicateGroupsManager:
    """Менеджер для управления группами токенов (включая одиночные) с умными функциями"""
    
    def __init__(self, telegram_token: str):
        """Инициализация с токеном Telegram бота"""
        self.telegram_token = telegram_token
        
        # Создаем и запускаем очередь сообщений
        self.telegram_queue = TelegramMessageQueue(telegram_token)
        self.telegram_queue.start()
        
        # Группы токенов {group_key: GroupData}
        self.groups = {}
        
        # Отслеживание официальных контрактов {group_key: official_contract_info}
        self.official_contracts = {}
        
        # Кэш результатов проверки Twitter аккаунтов (чтобы не проверять недоступные аккаунты повторно)
        self.twitter_check_cache = {}  # key: "account_symbol" -> {"has_mentions": bool, "last_check": timestamp, "error": str}
        self.cache_ttl = 300  # 5 минут кэш для успешных проверок
        self.error_cache_ttl = 3600  # 1 час кэш для ошибок (404, заблокированы и т.д.)
        
        # Глобальный rate limiting
        self.last_request_time = 0
        self.min_request_interval = 3.0  # Минимум 3 секунды между любыми запросами
        self.recent_429_count = 0  # Счетчик недавних 429 ошибок
        self.last_429_time = 0  # Время последней 429 ошибки
        
        # Настройки
        self.target_chat_id = -1002680160752  # ID группы
        self.message_thread_id = 14  # ID темы для групп токенов
        self.private_chat_id = 7891524244  # ID пользователя для токенов без Twitter
    
    def __del__(self):
        """Деструктор - останавливает очередь сообщений"""
        try:
            if hasattr(self, 'telegram_queue'):
                self.telegram_queue.stop()
        except:
            pass
    
    def stop(self):
        """Останавливает очередь сообщений"""
        self.telegram_queue.stop()
        logger.info("🛑 Менеджер групп токенов остановлен")
    
    def get_queue_stats(self) -> Dict:
        """Возвращает статистику очереди сообщений"""
        return {
            'queue_size': self.telegram_queue.get_queue_size(),
            'min_delay': self.telegram_queue.min_delay,
            'max_delay': self.telegram_queue.max_delay,
            'is_running': self.telegram_queue.running
        }
    
    class GroupData:
        """Данные группы токенов"""
        def __init__(self, group_key: str, symbol: str, name: str):
            self.group_key = group_key
            self.symbol = symbol
            self.name = name
            self.tokens = []  # Список всех токенов в группе
            self.message_id = None  # ID сообщения в Telegram
            self.sheet_url = None  # URL Google Sheets таблицы
            self.main_twitter = None  # Главный Twitter аккаунт
            self.official_contract = None  # Официальный контракт если найден
            self.official_announcement = None  # Самый старый твит с анонсом токена
            self.created_at = datetime.now()
            self.last_updated = datetime.now()
            self.latest_added_token = None  # Последний добавленный токен из Jupiter потока
            self.is_global_search_group = False  # Флаг для групп найденных через глобальный поиск (без Twitter ссылок)
    
    async def _apply_global_rate_limit(self):
        """Rate limiting отключен - используется 60-сек система в dynamic_cookie_rotation.py"""
        # Никаких задержек - полагаемся на систему прокси с 60-секундными интервалами
        pass
    
    def _track_429_error(self):
        """Отслеживает 429 ошибки для статистики"""
        current_time = time.time()
        
        # Если прошло больше 30 минут с последней 429 ошибки, сбрасываем счетчик
        if current_time - self.last_429_time > 1800:  # 30 минут
            self.recent_429_count = 0
        
        self.recent_429_count += 1
        self.last_429_time = current_time
        
        logger.warning(f"🔥 Отслеживание 429: {self.recent_429_count} ошибок за 30мин - используется 60-сек система в dynamic_cookie_rotation.py")
    
    def create_group_key(self, token_data: Dict) -> str:
        """Создает ключ группы для токена"""
        name = token_data.get('name', '').strip().lower()
        symbol = token_data.get('symbol', '').strip().upper()
        return f"{name}_{symbol}"
    
    def extract_twitter_accounts(self, token_data: Dict) -> List[str]:
        """Извлекает все Twitter аккаунты из данных токена"""
        twitter_accounts = set()
        
        # Поля где могут быть Twitter ссылки
        twitter_fields = ['twitter', 'website', 'telegram', 'social', 'links']
        
        for field in twitter_fields:
            url = token_data.get(field, '')
            if url and isinstance(url, str):
                account = self._normalize_twitter_url(url)
                if account:
                    twitter_accounts.add(account)
        
        return list(twitter_accounts)
    
    def _normalize_twitter_url(self, url: str) -> Optional[str]:
        """Нормализует Twitter URL, извлекая username"""
        try:
            if not url or not isinstance(url, str):
                return None
                
            url_lower = url.lower()
            
            # Проверяем что это Twitter/X ссылка
            if not any(domain in url_lower for domain in ['twitter.com', 'x.com']):
                return None
            
            # Извлекаем username
            username_pattern = r'(?i)(?:twitter\.com|x\.com)/([^/\?]+)'
            match = re.search(username_pattern, url)
            
            if match:
                username = match.group(1).strip()
                
                # Пропускаем служебные пути
                service_paths = ['i', 'home', 'search', 'notifications', 'messages', 'settings', 'intent']
                if username.lower() in service_paths:
                    return None
                    
                return username
                
        except Exception as e:
            logger.debug(f"❌ Ошибка нормализации Twitter URL {url}: {e}")
            
        return None
    
    def _is_twitter_username_similar_to_token(self, username: str, token_name: str, token_symbol: str) -> bool:
        """
        Проверяет схожесть никнейма Twitter аккаунта с названием или символом токена
        
        Примеры совпадений:
        - @AniAnichat +-= 'Jew Ani' / 'JANI'
        - @jewcoinonbonk +-= 'Jewbacca' / 'JEWBACCA'  
        - @CegeCoin +-= 'Cege' / 'CegeCoin'
        - @spltokenbonk +-= 'Standard Pointless Token' / 'SPL'
        - @suit_xero +-= 'SUITXERO' / 'XERO'
        """
        try:
            if not username or not (token_name or token_symbol):
                return False
            
            # Нормализуем строки - убираем пробелы, переводим в нижний регистр
            username_clean = username.lower().strip()
            token_name_clean = token_name.lower().strip() if token_name else ""
            token_symbol_clean = token_symbol.lower().strip() if token_symbol else ""
            
            # Убираем распространенные префиксы/суффиксы из username
            common_prefixes = ['the', 'official', 'real', 'true']
            common_suffixes = ['coin', 'token', 'crypto', 'sol', 'onsolana', 'onbonk', 'bonk', 'fun', 'official']
            
            username_parts = username_clean.replace('_', '').replace('-', '')
            
            # Убираем префиксы
            for prefix in common_prefixes:
                if username_parts.startswith(prefix):
                    username_parts = username_parts[len(prefix):]
                    break
            
            # Убираем суффиксы  
            for suffix in common_suffixes:
                if username_parts.endswith(suffix):
                    username_parts = username_parts[:-len(suffix)]
                    break
            
            # Проверяем прямые совпадения
            if username_parts == token_symbol_clean:
                logger.debug(f"✅ Прямое совпадение username '{username_parts}' с символом '{token_symbol_clean}'")
                return True
            
            if username_parts == token_name_clean.replace(' ', ''):
                logger.debug(f"✅ Прямое совпадение username '{username_parts}' с названием '{token_name_clean}'")
                return True
            
            # Проверяем содержание символа в username
            if token_symbol_clean and len(token_symbol_clean) >= 3:
                if token_symbol_clean in username_parts:
                    logger.debug(f"✅ Символ '{token_symbol_clean}' содержится в username '{username_parts}'")
                    return True
            
            # Проверяем содержание username в символе (для коротких username)
            if len(username_parts) >= 3:
                if username_parts in token_symbol_clean:
                    logger.debug(f"✅ Username '{username_parts}' содержится в символе '{token_symbol_clean}'")
                    return True
            
            # Проверяем схожесть с названием токена (по словам)
            if token_name_clean:
                token_name_words = token_name_clean.split()
                
                # Проверяем, содержит ли username части названия
                for word in token_name_words:
                    if len(word) >= 3 and word in username_parts:
                        logger.debug(f"✅ Слово '{word}' из названия найдено в username '{username_parts}'")
                        return True
                
                # Проверяем обратное - содержит ли название части username
                if len(username_parts) >= 3:
                    for word in token_name_words:
                        if username_parts in word:
                            logger.debug(f"✅ Username '{username_parts}' найден в слове '{word}' названия")
                            return True
                
                # Дополнительная проверка для частичных совпадений (например jewcoin содержит jew)
                for word in token_name_words:
                    if len(word) >= 3:
                        # Проверяем начало слова из названия в username
                        word_start = word[:max(3, len(word)//2)]  # Берем начало слова (мин 3 символа)
                        if word_start in username_parts:
                            logger.debug(f"✅ Начало слова '{word_start}' из '{word}' найдено в username '{username_parts}'")
                            return True
                        
                        # Проверяем начало username в слове названия
                        if len(username_parts) >= 3:
                            username_start = username_parts[:max(3, len(username_parts)//2)]
                            if username_start in word:
                                logger.debug(f"✅ Начало username '{username_start}' найдено в слове '{word}' названия")
                                return True
            
            # Проверяем по первым буквам название (аббревиатуры)
            if token_name_clean and len(token_name_clean.split()) > 1:
                initials = ''.join([word[0] for word in token_name_clean.split() if word])
                if initials == username_parts:
                    logger.debug(f"✅ Username '{username_parts}' совпадает с инициалами названия '{initials}'")
                    return True
            
            logger.debug(f"❌ Никакого сходства между username '{username_parts}' и токеном '{token_name_clean}'/'{token_symbol_clean}'")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сходства username {username} с токеном: {e}")
            return False
    
    async def _check_recent_tweets(self, twitter_account: str) -> bool:
        """
        Проверяет наличие свежих твитов (младше 30 дней) в Twitter аккаунте
        Используется для определения активности аккаунта
        """
        try:
            logger.debug(f"🔍 Проверяем наличие свежих твитов в @{twitter_account}")
            
            # Используем существующую функцию, но без проверки символа
            # Просто проверяем что в аккаунте есть твиты младше 30 дней
            async with TwitterProfileParser() as parser:
                result = await parser.get_profile_with_replies_multi_page(twitter_account, max_pages=2)
                
                if result and len(result) >= 2:
                    profile_data, all_tweets = result[0], result[1]
                else:
                    logger.debug(f"❌ Не удалось получить твиты от @{twitter_account}")
                    return False
                
                if not all_tweets:
                    logger.debug(f"❌ Нет твитов в @{twitter_account}")
                    return False
                
                # Проверяем возраст твитов
                fresh_tweets_count = 0
                current_time = datetime.now()
                
                for tweet in all_tweets:
                    try:
                        tweet_date_elem = tweet.get('date')
                        if not tweet_date_elem:
                            continue
                            
                        tweet_date = self._get_tweet_age(tweet_date_elem)
                        if tweet_date:
                            age_days = (current_time - tweet_date).days
                            if age_days <= 30:  # Твит младше 30 дней
                                fresh_tweets_count += 1
                    except Exception as e:
                        logger.debug(f"❌ Ошибка обработки твита: {e}")
                        continue
                
                if fresh_tweets_count > 0:
                    logger.debug(f"✅ Найдено {fresh_tweets_count} свежих твитов (< 30 дней) в @{twitter_account}")
                    return True
                else:
                    logger.debug(f"⏰ Все твиты в @{twitter_account} старше 30 дней")
                    return False
                    
        except Exception as e:
            logger.debug(f"❌ Ошибка проверки свежих твитов в @{twitter_account}: {e}")
            return False
    
    async def determine_main_twitter(self, tokens: List[Dict]) -> Optional[str]:
        """
        НОВАЯ ЛОГИКА: Определяет главный Twitter аккаунт на основе сходства никнейма с названием/символом токена
        
        Критерии отбора:
        1. Никнейм Twitter аккаунта должен быть похож на название или символ токена  
        2. Аккаунт НЕ должен содержать контракты (исключает аккаунты с уже запущенными токенами)
        3. Приоритет отдается аккаунтам со свежими твитами (< 30 дней)
        """
        try:
            if not tokens:
                return None
            
            # Получаем название и символ из токенов
            first_token = tokens[0]
            token_name = first_token.get('name', '').strip()
            token_symbol = first_token.get('symbol', '').strip()
            
            if not token_symbol:
                logger.warning(f"🚫 Нет символа токена для определения главного Twitter")
                return None
            
            logger.info(f"🔍 НОВАЯ ЛОГИКА: Ищем Twitter аккаунт похожий на '{token_name}' / '{token_symbol}'")
            
            # Собираем все уникальные Twitter аккаунты
            all_twitter_accounts = set()
            for token in tokens:
                twitter_accounts = self.extract_twitter_accounts(token)
                for account in twitter_accounts:
                    all_twitter_accounts.add(account.lower())
            
            if not all_twitter_accounts:
                logger.warning(f"🚫 Нет Twitter аккаунтов для проверки токена {token_symbol}")
                return None
            
            logger.info(f"🔍 Проверяем {len(all_twitter_accounts)} Twitter аккаунтов на сходство с токеном {token_symbol}")
            
            # Фильтруем аккаунты по сходству никнейма с токеном
            similar_accounts = []
            for twitter_account in all_twitter_accounts:
                is_similar = self._is_twitter_username_similar_to_token(twitter_account, token_name, token_symbol)
                if is_similar:
                    logger.info(f"✅ Аккаунт @{twitter_account} ПОХОЖ на токен '{token_name}'/'{token_symbol}'")
                    similar_accounts.append(twitter_account)
                else:
                    logger.debug(f"❌ Аккаунт @{twitter_account} НЕ похож на токен '{token_name}'/'{token_symbol}'")
            
            if not similar_accounts:
                logger.warning(f"🚫 Ни один Twitter аккаунт не похож на токен {token_symbol} - группа будет без главного аккаунта")
                return None
            
            logger.info(f"🎯 Найдено {len(similar_accounts)} похожих аккаунтов: {', '.join('@' + acc for acc in similar_accounts)}")
            
            # Проверяем каждый похожий аккаунт на наличие контрактов и свежесть твитов
            valid_accounts = []
            
            for i, twitter_account in enumerate(similar_accounts):
                logger.info(f"🔍 Проверяем похожий аккаунт @{twitter_account} ({i+1}/{len(similar_accounts)})")
                
                # Задержка между проверками для избежания rate limiting
                if i > 0:
                    delay = random.uniform(3, 7)
                    logger.debug(f"⏳ Пауза {delay:.1f}с перед проверкой @{twitter_account}")
                    await asyncio.sleep(delay)
                
                # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Проверяем наличие контрактов в аккаунте
                has_contracts = await self._check_contracts_in_twitter(twitter_account)
                if has_contracts:
                    logger.warning(f"🚫 Аккаунт @{twitter_account} ИСКЛЮЧЕН: найдены контракты (официальный токен уже запущен)")
                    continue  # Пропускаем аккаунт с контрактами
                
                # Проверяем наличие свежих твитов (любых, не обязательно с символом)
                has_fresh_tweets = await self._check_recent_tweets(twitter_account)
                
                if has_fresh_tweets:
                    logger.info(f"✅ Аккаунт @{twitter_account}: похож на токен + БЕЗ контрактов + есть свежие твиты")
                    valid_accounts.append(twitter_account)
                else:
                    logger.info(f"⏰ Аккаунт @{twitter_account}: похож на токен + БЕЗ контрактов, но НЕТ свежих твитов")
                    # Всё равно добавляем в valid_accounts как резервный вариант
                    valid_accounts.append(twitter_account)
            
            if not valid_accounts:
                logger.warning(f"🚫 Ни один похожий аккаунт не прошел проверки для токена {token_symbol}")
                return None
            
            # Если найден только один валидный аккаунт - он главный
            if len(valid_accounts) == 1:
                main_twitter = valid_accounts[0]
                logger.info(f"🎯 Главный Twitter определен: @{main_twitter} (единственный похожий и валидный)")
                return main_twitter
            
            # Если несколько валидных аккаунтов - берем первый
            main_twitter = valid_accounts[0]
            logger.info(f"🎯 Главный Twitter определен: @{main_twitter} (первый из {len(valid_accounts)} похожих и валидных)")
            return main_twitter
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения главного Twitter: {e}")
            return None

    async def determine_main_twitter_from_global_search(self, symbol: str) -> Optional[str]:
        """Определяет главный Twitter аккаунт через глобальный поиск для токенов без Twitter ссылок"""
        try:
            logger.info(f"🌍 Поиск главного Twitter для токена {symbol} через ГЛОБАЛЬНЫЙ поиск...")
            
            # Выполняем глобальный поиск
            found_accounts = await self._global_search_for_symbol(symbol)
            
            if not found_accounts:
                # Проверяем причину неудачи в кэше
                cache_key = f"global_search_{symbol}"
                cached_result = self.twitter_check_cache.get(cache_key, {})
                error_reason = cached_result.get('error', 'Нет данных в кэше')
                
                if error_reason and 'TimeoutError' in str(error_reason):
                    logger.error(f"🚫💥 КРИТИЧЕСКАЯ ОШИБКА: Глобальный поиск для {symbol} упал с TimeoutError!")
                    logger.error(f"🔧 Это означает, что БОТ ПРОПУСКАЕТ ТОКЕНЫ из-за проблем с доменами!")
                else:
                    logger.warning(f"🚫 Глобальный поиск не нашел аккаунтов для символа {symbol} (причина: {error_reason})")
                return None
            
            logger.info(f"🔍 Проверяем {len(found_accounts)} найденных аккаунтов на пригодность...")
            
            # Проверяем каждый найденный аккаунт
            valid_accounts = []
            has_any_fresh_tweets = False
            
            for i, twitter_account in enumerate(found_accounts):
                logger.info(f"🔍 Проверяем аккаунт @{twitter_account} из глобального поиска ({i+1}/{len(found_accounts)})...")
                
                # Задержка между проверками аккаунтов для избежания rate limiting
                if i > 0:  # Не ждем перед первым аккаунтом
                    delay = random.uniform(8, 15)
                    logger.debug(f"⏳ Пауза {delay:.1f}с перед проверкой @{twitter_account}")
                    await asyncio.sleep(delay)
                
                # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Проверяем наличие контрактов в аккаунте
                has_contracts = await self._check_contracts_in_twitter(twitter_account)
                if has_contracts:
                    logger.warning(f"🚫 Аккаунт @{twitter_account} ИСКЛЮЧЕН: найдены контракты (официальный токен уже запущен)")
                    continue  # Пропускаем аккаунт с контрактами
                
                # Проверяем наличие символа в кавычках (с проверкой возраста)
                has_symbol_mentions = await self._check_symbol_mentions_in_twitter(twitter_account, symbol)
                
                if has_symbol_mentions:
                    logger.info(f"✅ Аккаунт @{twitter_account} содержит СВЕЖИЕ упоминания \"${symbol}\" (< 30 дней) БЕЗ контрактов")
                    valid_accounts.append(twitter_account)
                    has_any_fresh_tweets = True
                else:
                    # Проверяем кэш для понимания причины отказа
                    cache_key = f"{twitter_account}_{symbol}"
                    cached_result = self.twitter_check_cache.get(cache_key, {})
                    error_reason = cached_result.get('error', 'Неизвестная причина')
                    
                    if error_reason == 'Все твиты старше 30 дней':
                        logger.info(f"⏰ Аккаунт @{twitter_account} содержит упоминания \"${symbol}\", но все твиты СТАРШЕ 30 дней")
                    else:
                        logger.info(f"❌ Аккаунт @{twitter_account} НЕ содержит упоминания \"${symbol}\" ({error_reason})")
            
            # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Если НИ ОДИН аккаунт не содержит свежих твитов - скипаем группу
            if not has_any_fresh_tweets:
                logger.warning(f"⏰🚫 ГРУППА {symbol} СКИПАЕТСЯ: Все твиты со всех найденных аккаунтов старше 30 дней! Группа неактуальна.")
                return None
            
            if not valid_accounts:
                logger.warning(f"🚫 Ни один найденный аккаунт не содержит СВЕЖИЕ упоминания \"${symbol}\" - группа будет пропущена")
                return None
            
            # Если найден только один валидный аккаунт - он главный
            if len(valid_accounts) == 1:
                main_twitter = valid_accounts[0]
                logger.info(f"🎯 Главный Twitter определен через ГЛОБАЛЬНЫЙ ПОИСК: @{main_twitter} (единственный со СВЕЖИМИ упоминаниями \"${symbol}\")")
                return main_twitter
            
            # Если несколько валидных аккаунтов - берем первый (или можно добавить доп. логику)
            main_twitter = valid_accounts[0]
            logger.info(f"🎯 Главный Twitter определен через ГЛОБАЛЬНЫЙ ПОИСК: @{main_twitter} (первый из {len(valid_accounts)} валидных со СВЕЖИМИ твитами)")
            return main_twitter
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения главного Twitter через глобальный поиск: {e}")
            return None
    
    async def _check_symbol_mentions_in_twitter(self, twitter_account: str, symbol: str) -> bool:
        """Проверяет наличие упоминаний символа в кавычках в Twitter аккаунте с перебором всех доменов Nitter (БЕЗ блокировки прокси)"""
        from dynamic_cookie_rotation import get_next_proxy_cookie_async
        from nitter_domain_rotator import get_all_nitter_domains, get_domain_count, record_nitter_request_result, get_next_nitter_domain
        
        # Используем количество попыток равное количеству доменов Nitter
        max_attempts = get_domain_count()  # Столько попыток, сколько доменов
        
        # Инициализируем переменные вне цикла
        current_time = time.time()
        cache_key = f"{twitter_account}_{symbol}"
        
        # Получаем все домены для перебора
        all_domains = get_all_nitter_domains()
        
        for attempt in range(max_attempts):
            try:
                # 🛡️ НИКОГДА НЕ ПРОПУСКАЕМ - ВСЕГДА ДОБИВАЕМСЯ УСПЕХА!
                # Используем домен по номеру попытки (циклически)
                current_domain = all_domains[attempt % len(all_domains)]
                
                # Проверяем кэш только на первой попытке
                if attempt == 0 and cache_key in self.twitter_check_cache:
                    cached_result = self.twitter_check_cache[cache_key]
                    
                    # Определяем TTL в зависимости от типа результата
                    if cached_result.get('error'):
                        # Для истощенных попыток - средний кэш (меньше чем раньше)
                        if 'All retries exhausted' in cached_result.get('error', ''):
                            ttl = self.error_cache_ttl // 2  # Вдвое меньше чем обычные ошибки
                            cache_type = "EXHAUSTED"
                        else:
                            # Для обычных ошибок (404, заблокированы) - длинный кэш
                            ttl = self.error_cache_ttl
                            cache_type = "ERROR"
                    else:
                        # Для успешных проверок - короткий кэш
                        ttl = self.cache_ttl
                        cache_type = "SUCCESS"
                    
                    # Проверяем не истек ли кэш
                    if current_time - cached_result['last_check'] < ttl:
                        if cache_type == "EXHAUSTED":
                            remaining_time = int((ttl - (current_time - cached_result['last_check']))/60)
                            logger.warning(f"💀 Кэш [{cache_type}]: @{twitter_account} недавно исчерпал попытки, ждем восстановления (осталось {remaining_time}мин)")
                        else:
                            logger.info(f"📋 Кэш [{cache_type}]: @{twitter_account} - {cached_result.get('error', 'проверено')} (TTL: {int(ttl/60)}мин)")
                        return cached_result['has_mentions']
                    else:
                        logger.debug(f"⏰ Кэш истек для @{twitter_account} (прошло {int((current_time - cached_result['last_check'])/60)}мин)")
                
                # Формируем поисковый запрос: "${СИМВОЛ}"
                search_query = f'"${symbol}"'
                
                # Получаем cookie для поиска
                async with aiohttp.ClientSession() as session:
                    proxy, cookie = await get_next_proxy_cookie_async(session)
                    
                    # Заголовки
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cookie': cookie
                    }
                    
                    # Добавляем заголовок Host для специальных IP-адресов
                    add_host_header_if_needed(headers, current_domain)
                    
                    # Настройка соединения
                    connector = aiohttp.TCPConnector(ssl=False)
                    request_kwargs = {}
                    if proxy:
                        request_kwargs['proxy'] = proxy
                    
                    # URL поиска в конкретном аккаунте (перебираем домены)
                    nitter_base = format_nitter_url(current_domain)
                    search_url = f"{nitter_base}/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                    
                    logger.info(f"🔍 Попытка {attempt + 1}/{max_attempts}: ищем \"${symbol}\" в @{twitter_account} на домене {current_domain}")
                    
                    # Применяем глобальный rate limiting
                    await self._apply_global_rate_limit()
                    
                    # Засекаем время запроса для статистики
                    start_time = time.time()
                    
                    # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС
                    response = await network_retry_wrapper(session, 'get', search_url, 
                                                        headers=headers, timeout=15, **request_kwargs)
                    
                    # Вычисляем время выполнения запроса
                    response_time = time.time() - start_time
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Проверяем на блокировку Nitter
                        title = soup.find('title')
                        if title and 'Making sure you\'re not a bot!' in title.get_text():
                            logger.warning(f"🚫 Nitter заблокирован для поиска \"${symbol}\" в @{twitter_account} - пытаемся восстановить")
                            
                            # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                            retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, search_url, f"поиск \"${symbol}\" в @{twitter_account}", html)
                            
                            if retry_soup:
                                # Успешно восстановились, используем новый soup
                                soup = retry_soup
                                logger.info(f"✅ Восстановление успешно для поиска \"${symbol}\" в @{twitter_account}")
                            else:
                                # Не удалось восстановиться
                                logger.error(f"❌ Не удалось восстановиться после блокировки для поиска \"${symbol}\" в @{twitter_account}")
                                # Сохраняем в кэш как ошибку
                                self.twitter_check_cache[cache_key] = {
                                    'has_mentions': False,
                                    'last_check': current_time,
                                    'error': 'Nitter заблокирован (не удалось восстановить)'
                                }
                                return False
                        
                        # Ищем твиты
                        tweets = soup.find_all('div', class_='timeline-item')
                        if tweets and len(tweets) > 0:
                            # 🔍 КРИТИЧЕСКАЯ ВАЛИДАЦИЯ: проверяем каждый твит на наличие "$SYMBOL" и возраст
                            valid_tweets = 0
                            fresh_tweets = 0
                            one_month_ago = datetime.now() - timedelta(days=30)
                            
                            for tweet in tweets:
                                tweet_content = tweet.find('div', class_='tweet-content')
                                tweet_date_elem = tweet.find('span', class_='tweet-date')
                                
                                if tweet_content and tweet_date_elem:
                                    tweet_text = tweet_content.get_text()
                                    # Проверяем наличие символа с $ в тексте (регистронезависимо)
                                    symbol_pattern = f"${symbol.upper()}"
                                    if symbol_pattern in tweet_text.upper():
                                        valid_tweets += 1
                                        
                                        # Проверяем возраст твита
                                        tweet_age = self._get_tweet_age(tweet_date_elem)
                                        if tweet_age and tweet_age > one_month_ago:
                                            fresh_tweets += 1
                                            logger.debug(f"✅ Свежий твит с \"{symbol_pattern}\" ({tweet_age.strftime('%Y-%m-%d')}): {tweet_text[:50]}...")
                                        else:
                                            logger.debug(f"⏰ Старый твит с \"{symbol_pattern}\" ({tweet_age.strftime('%Y-%m-%d') if tweet_age else 'неизвестно'}): {tweet_text[:50]}...")
                                    else:
                                        logger.debug(f"❌ Невалидный твит (нет \"{symbol_pattern}\"): {tweet_text[:50]}...")
                            
                            if valid_tweets > 0:
                                if fresh_tweets > 0:
                                    logger.info(f"✅ Найдено {valid_tweets} ВАЛИДНЫХ твитов с \"${symbol}\" в @{twitter_account}, из них {fresh_tweets} свежих (< 30 дней)")
                                    # Записываем успешную статистику для домена
                                    record_nitter_request_result(current_domain, True, response_time, 200)
                                    # Сохраняем в кэш как успех
                                    self.twitter_check_cache[cache_key] = {
                                        'has_mentions': True,
                                        'last_check': current_time,
                                        'error': None
                                    }
                                    return True
                                else:
                                    logger.warning(f"⏰ Найдено {valid_tweets} твитов с \"${symbol}\" в @{twitter_account}, но все старше 30 дней")
                                    # Записываем статистику (технически успешный запрос, но результат не подходит)
                                    record_nitter_request_result(current_domain, True, response_time, 200)
                                    # Сохраняем в кэш как неуспех (старые твиты)
                                    self.twitter_check_cache[cache_key] = {
                                        'has_mentions': False,
                                        'last_check': current_time,
                                        'error': 'Все твиты старше 30 дней'
                                    }
                                    return False
                            else:
                                logger.warning(f"🚫 Найдено {len(tweets)} твитов, но НИ ОДИН не содержит \"${symbol}\" в @{twitter_account}")
                                # Записываем статистику (технически успешный запрос, но результат не подходит)
                                record_nitter_request_result(current_domain, True, response_time, 200)
                                # Сохраняем в кэш как неуспех
                                self.twitter_check_cache[cache_key] = {
                                    'has_mentions': False,
                                    'last_check': current_time,
                                    'error': 'Твиты найдены, но без символа'
                                }
                                return False
                        else:
                            logger.debug(f"🚫 Упоминания \"${symbol}\" НЕ найдены в @{twitter_account}")
                            # Записываем статистику (технически успешный запрос, но результат не подходит)
                            record_nitter_request_result(current_domain, True, response_time, 200)
                            # Сохраняем в кэш как неуспех
                            self.twitter_check_cache[cache_key] = {
                                'has_mentions': False,
                                'last_check': current_time,
                                'error': None
                            }
                            return False
                    elif response.status == 429:
                        # HTTP 429 - это проблема домена, а не прокси
                        self._track_429_error()
                        # Записываем статистику 429 ошибки для домена
                        record_nitter_request_result(current_domain, False, response_time, 429)
                        
                        logger.warning(f"🌐 HTTP 429 для @{twitter_account} на домене {current_domain} - пробуем следующий домен!")
                        
                        # Короткая пауза перед попыткой со следующим доменом
                        await asyncio.sleep(2)
                        continue  # Пробуем следующий домен в цикле
                    else:
                        # Записываем статистику ошибки для домена
                        record_nitter_request_result(current_domain, False, response_time, response.status)
                        
                        logger.warning(f"❌ Ошибка поиска в @{twitter_account} на домене {current_domain}: HTTP {response.status}")
                        # Пробуем следующий домен
                        continue
                            
            except Exception as e:
                error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
                
                # Проверяем на таймаут или сетевые ошибки
                is_timeout_error = any(keyword in error_msg.lower() for keyword in [
                    'timeout', 'timed out', 'connection', 'network', 'disconnected', 
                    'unreachable', 'refused', 'reset', 'aborted'
                ])
                
                if is_timeout_error and attempt < max_attempts - 1:
                    # Записываем статистику timeout для домена
                    record_nitter_request_result(current_domain, False, response_time if 'response_time' in locals() else 30.0, None)
                    
                    delay = min(30, (attempt + 1) * 3)  # 3, 6, 9, 12, 15 секунд
                    logger.warning(f"⏰ Таймаут при проверке символа @{twitter_account} на домене {current_domain} (попытка {attempt + 1}/{max_attempts}). Повтор через {delay}с...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Записываем статистику ошибки для домена
                    record_nitter_request_result(current_domain, False, response_time if 'response_time' in locals() else 30.0, None)
                    
                    logger.error(f"❌ Ошибка проверки символа в @{twitter_account} на домене {current_domain}: {error_msg}")
                    # Сохраняем в кэш как ошибку
                    self.twitter_check_cache[cache_key] = {
                        'has_mentions': False,
                        'last_check': current_time,
                        'error': error_msg
                    }
                    return False
        
        logger.error(f"💀 Все {max_attempts} попыток исчерпаны для проверки символа @{twitter_account}")
        # Сохраняем в кэш как ошибку
        self.twitter_check_cache[cache_key] = {
            'has_mentions': False,
            'last_check': time.time(),
            'error': f"Все {max_attempts} попыток исчерпаны"
        }
        return False
    
    def _get_tweet_age(self, tweet_date_elem) -> Optional[datetime]:
        """Парсит возраст твита из элемента даты"""
        try:
            if not tweet_date_elem:
                return None
                
            # Получаем дату из атрибута title ссылки, если доступно
            date_link = tweet_date_elem.find('a')
            if date_link and date_link.get('title'):
                # Берем полную дату из title: "Jun 16, 2025 · 6:03 PM UTC"
                date_str = date_link.get('title')
                
                # Парсим дату в формате "Jun 16, 2025 · 6:03 PM UTC"
                try:
                    # Убираем часовой пояс и разделители
                    date_str = date_str.replace(' UTC', '').replace(' · ', ' ')
                    tweet_date = datetime.strptime(date_str, '%b %d, %Y %I:%M %p')
                    return tweet_date
                except:
                    pass
                    
            # Fallback: берем текст элемента
            date_text = tweet_date_elem.get_text(strip=True)
            if date_text:
                # Обрабатываем относительные даты типа "1h", "2d", "3w"
                if 'h' in date_text:  # часы
                    hours = int(re.search(r'(\d+)h', date_text).group(1))
                    return datetime.now() - timedelta(hours=hours)
                elif 'd' in date_text:  # дни
                    days = int(re.search(r'(\d+)d', date_text).group(1))
                    return datetime.now() - timedelta(days=days)
                elif 'w' in date_text:  # недели
                    weeks = int(re.search(r'(\d+)w', date_text).group(1))
                    return datetime.now() - timedelta(weeks=weeks)
                elif 'm' in date_text:  # месяцы (примерно)
                    months = int(re.search(r'(\d+)m', date_text).group(1))
                    return datetime.now() - timedelta(days=months * 30)
                elif 'y' in date_text:  # годы
                    years = int(re.search(r'(\d+)y', date_text).group(1))
                    return datetime.now() - timedelta(days=years * 365)
            
            return None
            
        except Exception as e:
            logger.debug(f"❌ Ошибка парсинга возраста твита: {e}")
            return None
    
    async def _find_oldest_announcement(self, twitter_account: str, symbol: str) -> Optional[Dict]:
        """
        НОВАЯ ЛОГИКА: Находит самый старый твит в Twitter аккаунте как анонс (не обязательно с символом)
        
        Логика:
        1. Получает все твиты из аккаунта
        2. Возвращает самый старый твит как анонс
        3. Если твитов нет - возвращает None (бот отправит сообщение без анонса)
        """
        try:
            logger.info(f"🔍 НОВАЯ ЛОГИКА: Ищем самый старый твит в @{twitter_account} как анонс (не ищем ${symbol})")
            
            async with TwitterProfileParser() as parser:
                # Получаем профиль с твитами (больше страниц для поиска старых твитов)
                result = await parser.get_profile_with_replies_multi_page(twitter_account, max_pages=5)
                
                if result and len(result) >= 2:
                    profile_data, all_tweets = result[0], result[1]
                else:
                    logger.warning(f"❌ Не удалось получить твиты от @{twitter_account}")
                    return None
                
                if not all_tweets:
                    logger.warning(f"❌ Нет твитов в @{twitter_account} - отправим без анонса")
                    return None
                
                logger.info(f"📄 Получено {len(all_tweets)} твитов от @{twitter_account}")
                
                # Ищем самый старый твит
                oldest_tweet = None
                oldest_date = None
                
                for tweet in all_tweets:
                    try:
                        tweet_text = tweet.get('text', '').strip()
                        tweet_date_elem = tweet.get('date')
                        tweet_url = tweet.get('url', '')
                        
                        if not tweet_text or not tweet_date_elem:
                            continue
                        
                        # Парсим дату твита
                        tweet_date = self._get_tweet_age(tweet_date_elem)
                        if not tweet_date:
                            continue
                        
                        # Ищем самый старый твит
                        if oldest_date is None or tweet_date < oldest_date:
                            oldest_date = tweet_date
                            oldest_tweet = {
                                'text': tweet_text,
                                'date': tweet_date.strftime('%Y-%m-%d'),
                                'url': tweet_url
                            }
                            
                    except Exception as e:
                        logger.debug(f"❌ Ошибка обработки твита: {e}")
                        continue
                
                if oldest_tweet:
                    logger.info(f"✅ АНОНС НАЙДЕН: Самый старый твит от {oldest_tweet['date']} в @{twitter_account}")
                    logger.info(f"📄 Текст анонса: {oldest_tweet['text'][:100]}...")
                    return oldest_tweet
                else:
                    logger.warning(f"❌ Не удалось найти подходящие твиты в @{twitter_account}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка поиска анонса в @{twitter_account}: {e}")
            return None
    
    async def _find_oldest_token_mention(self, twitter_account: str, symbol: str) -> Optional[Dict]:
        """Находит самое старое упоминание токена в Twitter аккаунте с агрессивными повторными попытками"""
        max_attempts = 15  # Максимум 15 попыток для поиска анонса
        attempt = 0
        
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"🔍 Попытка {attempt}/{max_attempts} найти анонс токена ${symbol} в @{twitter_account}")
                
                # 🔄 СОЗДАЕМ НОВЫЙ ПАРСЕР ДЛЯ КАЖДОЙ ПОПЫТКИ (свежие прокси!)
                async with TwitterProfileParser() as parser:
                    # Получаем профиль с твитами
                    result = await parser.get_profile_with_replies_multi_page(twitter_account, max_pages=3)
                    
                    # Проверяем что получили правильное количество значений
                    if result and len(result) == 3:
                        profile_data, all_tweets, tweets_with_contracts = result
                    elif result and len(result) == 2:
                        profile_data, all_tweets = result
                        tweets_with_contracts = []
                    else:
                        logger.warning(f"⚠️ Неожиданный результат от парсера для @{twitter_account}: {result}")
                        all_tweets = []
                    
                    if not all_tweets:
                        logger.warning(f"⚠️ Попытка {attempt}: Нет твитов от @{twitter_account}")
                        if attempt < max_attempts:
                            delay = min(30, 3 * attempt)
                            logger.info(f"⏳ Ждем {delay}с перед попыткой {attempt + 1} (новый прокси)...")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            break
                    
                    logger.info(f"📄 Получено {len(all_tweets)} твитов от @{twitter_account}")
                    
                    # Ищем упоминания символа в твитах
                    mentions = []
                    symbol_patterns = [
                        f"${symbol}",
                        f"#{symbol}",
                        f"{symbol}",
                        f"${symbol.upper()}",
                        f"#{symbol.upper()}",
                        f"{symbol.upper()}"
                    ]
                    
                    for tweet in all_tweets:
                        try:
                            # Проверяем что tweet это словарь, а не строка
                            if not isinstance(tweet, dict):
                                logger.debug(f"⚠️ Пропущен твит неправильного типа: {type(tweet)}")
                                continue
                                
                            tweet_text = tweet.get('text', '').upper()
                            
                            # Проверяем все варианты символа
                            for pattern in symbol_patterns:
                                if pattern.upper() in tweet_text:
                                    # Получаем дату твита
                                    tweet_date_elem = tweet.get('date')
                                    tweet_date = self._get_tweet_age(tweet_date_elem)
                                    
                                    if tweet_date:
                                        mentions.append({
                                            'text': tweet.get('text', ''),
                                            'date': tweet_date,
                                            'url': tweet.get('url', ''),
                                            'pattern_matched': pattern
                                        })
                                        logger.debug(f"✅ Найдено упоминание {pattern} в твите от {tweet_date}")
                                    break
                        except Exception as e:
                            logger.error(f"❌ Ошибка обработки твита: {e} (тип: {type(tweet)})")
                            continue
                    
                    if mentions:
                        # Сортируем по дате (самые старые первыми)
                        mentions.sort(key=lambda x: x['date'])
                        oldest_mention = mentions[0]
                        
                        logger.info(f"✅ УСПЕХ! Найден анонс ${symbol} в @{twitter_account} от {oldest_mention['date']}")
                        return oldest_mention
                    else:
                        logger.warning(f"⚠️ Попытка {attempt}: Упоминания ${symbol} не найдены в @{twitter_account}")
                        
            except Exception as e:
                logger.error(f"❌ Попытка {attempt}: Ошибка поиска анонса ${symbol} в @{twitter_account}: {e}")
            
            # Если не последняя попытка - ждем перед повтором
            if attempt < max_attempts:
                # Задержка: 5, 10, 15, 20, 25, 30, 30, 30...
                delay = min(30, 5 * attempt)
                logger.info(f"⏳ Ждем {delay}с перед попыткой {attempt + 1} (новый прокси)...")
                await asyncio.sleep(delay)
        
        logger.warning(f"💀 ВСЕ {max_attempts} ПОПЫТОК ИСЧЕРПАНЫ для поиска анонса ${symbol} в @{twitter_account}! Анонс не найден")
        
        # 🔄 FALLBACK: Пробуем через обычный Nitter поиск (тот же метод что работает!)
        logger.info(f"🔄 FALLBACK: Пробуем найти анонс ${symbol} через обычный Nitter поиск...")
        return await self._find_oldest_token_mention_via_nitter(twitter_account, symbol)
    
    async def _find_oldest_token_mention_via_nitter(self, twitter_account: str, symbol: str) -> Optional[Dict]:
        """Находит самое старое упоминание токена через обычный Nitter поиск (как fallback для TwitterProfileParser)"""
        from dynamic_cookie_rotation import get_next_proxy_cookie_async
        from nitter_domain_rotator import get_next_nitter_domain, record_nitter_request_result
        
        max_attempts = 5  # Меньше попыток для fallback
        attempt = 0
        
        logger.info(f"🔍 Fallback поиск анонса ${symbol} в @{twitter_account} через Nitter")
        
        while attempt < max_attempts:
            try:
                attempt += 1
                
                # Получаем текущий домен Nitter
                current_domain = get_next_nitter_domain()
                
                async with aiohttp.ClientSession() as session:
                    # Получаем прокси и куки
                    proxy, cookie = await get_next_proxy_cookie_async(session)
                    
                    search_query = f'"{symbol}"'  # Поиск в кавычках
                    search_pattern = f"${symbol}"  # Что ищем в твитах
                    
                    # Заголовки запроса
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cookie': cookie
                    }
                    
                    # Добавляем заголовок Host для специальных IP-адресов
                    add_host_header_if_needed(headers, current_domain)
                    
                    # Настройка соединения
                    connector = aiohttp.TCPConnector(ssl=False)
                    request_kwargs = {}
                    if proxy:
                        request_kwargs['proxy'] = proxy
                    
                    # URL поиска в конкретном аккаунте
                    nitter_base = format_nitter_url(current_domain)
                    search_url = f"{nitter_base}/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                    
                    logger.info(f"🔍 Nitter fallback попытка {attempt}/{max_attempts}: {search_url}")
                    
                    # Применяем глобальный rate limiting
                    await self._apply_global_rate_limit()
                    
                    start_time = time.time()
                    
                    # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС
                    response = await network_retry_wrapper(session, 'get', search_url, 
                                                        headers=headers, timeout=15, **request_kwargs)
                    
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Проверяем на блокировку Nitter
                        title = soup.find('title')
                        if title and 'Making sure you\'re not a bot!' in title.get_text():
                            logger.warning(f"🚫 Nitter заблокирован для fallback поиска ${symbol} в @{twitter_account} - пытаемся восстановить")
                            
                            retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, search_url, f"fallback поиск ${symbol} в @{twitter_account}", html)
                            
                            if retry_soup:
                                soup = retry_soup
                                logger.info(f"✅ Восстановление успешно для fallback поиска ${symbol} в @{twitter_account}")
                            else:
                                # Пробуем следующий домен
                                continue
                        
                        # Извлекаем твиты
                        tweets = soup.find_all('div', class_='timeline-item')
                        mentions = []
                        
                        if tweets:
                            logger.info(f"📄 Fallback нашел {len(tweets)} твитов в @{twitter_account}")
                            
                            for tweet in tweets:
                                try:
                                    # Извлекаем содержимое твита
                                    tweet_content = tweet.find('div', class_='tweet-content')
                                    if not tweet_content:
                                        continue
                                    
                                    tweet_text = tweet_content.get_text().upper()
                                    
                                    # Проверяем наличие символа
                                    if search_pattern.upper() in tweet_text:
                                        # Извлекаем дату
                                        tweet_date_elem = tweet.find('span', class_='tweet-date')
                                        tweet_date = self._get_tweet_age(tweet_date_elem)
                                        
                                        if tweet_date:
                                            # Извлекаем URL твита
                                            tweet_link = tweet.find('a', class_='tweet-link')
                                            tweet_url = tweet_link.get('href', '') if tweet_link else ''
                                            
                                            mentions.append({
                                                'text': tweet_content.get_text(),
                                                'date': tweet_date,
                                                'url': tweet_url,
                                                'pattern_matched': search_pattern
                                            })
                                            
                                            logger.debug(f"✅ Fallback нашел упоминание {search_pattern} от {tweet_date}")
                                        
                                except Exception as e:
                                    logger.error(f"❌ Ошибка обработки твита в fallback: {e}")
                                    continue
                            
                            if mentions:
                                # Сортируем по дате (самые старые первыми)
                                mentions.sort(key=lambda x: x['date'])
                                oldest_mention = mentions[0]
                                
                                logger.info(f"✅ FALLBACK УСПЕХ! Найден анонс ${symbol} в @{twitter_account} от {oldest_mention['date']}")
                                record_nitter_request_result(current_domain, True, response_time, 200)
                                return oldest_mention
                            else:
                                logger.warning(f"⚠️ Fallback: твиты найдены, но без упоминаний ${symbol} в @{twitter_account}")
                                record_nitter_request_result(current_domain, True, response_time, 200)
                        else:
                            logger.warning(f"⚠️ Fallback: нет твитов для ${symbol} в @{twitter_account}")
                            record_nitter_request_result(current_domain, True, response_time, 200)
                    
                    elif response.status == 429:
                        # HTTP 429 - пробуем следующий домен
                        record_nitter_request_result(current_domain, False, response_time, 429)
                        logger.warning(f"🌐 HTTP 429 для fallback поиска ${symbol} - пробуем следующий домен!")
                        await asyncio.sleep(2)
                        continue
                    
                    else:
                        record_nitter_request_result(current_domain, False, response_time, response.status)
                        logger.warning(f"❌ Fallback ошибка HTTP {response.status} для ${symbol} в @{twitter_account}")
                        
            except Exception as e:
                error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
                logger.error(f"❌ Fallback попытка {attempt}: Ошибка поиска ${symbol} в @{twitter_account}: {error_msg}")
                
                if attempt < max_attempts:
                    delay = min(10, 2 * attempt)
                    logger.info(f"⏳ Fallback ждем {delay}с перед попыткой {attempt + 1}...")
                    await asyncio.sleep(delay)
        
        logger.warning(f"💀 Fallback исчерпан для ${symbol} в @{twitter_account}! Анонс НЕ найден")
        return None
    
    async def _global_search_for_symbol(self, symbol: str) -> List[str]:
        """Выполняет глобальный поиск символа токена и возвращает найденные Twitter аккаунты"""
        from dynamic_cookie_rotation import get_next_proxy_cookie_async, mark_proxy_temp_blocked
        
        try:
            # 🛡️ НИКОГДА НЕ ПРОПУСКАЕМ - ВСЕГДА ДОБИВАЕМСЯ УСПЕХА!
            
            # 🗂️ КЕШИРОВАНИЕ ГЛОБАЛЬНОГО ПОИСКА для избежания дублирующих запросов
            cache_key = f"global_search_{symbol}"
            current_time = time.time()
            
            if cache_key in self.twitter_check_cache:
                cached_result = self.twitter_check_cache[cache_key]
                ttl = self.cache_ttl  # Используем стандартный TTL для глобального поиска
                
                if current_time - cached_result['last_check'] < ttl:
                    remaining_time = int((ttl - (current_time - cached_result['last_check']))/60)
                    logger.info(f"🗂️ Кеш ГЛОБАЛЬНОГО ПОИСКА: символ \"{symbol}\" уже искался недавно (осталось {remaining_time}мин)")
                    return cached_result.get('found_accounts', [])
                else:
                    logger.debug(f"⏰ Кеш глобального поиска истек для \"{symbol}\"")
            
            found_accounts = set()
            search_query = f'"${symbol}"'
            symbol_pattern = f"${symbol.upper()}"  # Определяем паттерн символа заранее
            
            logger.info(f"🌍 Начинаем ГЛОБАЛЬНЫЙ поиск символа \"{search_query}\"...")
            
            # Получаем cookie для поиска
            async with aiohttp.ClientSession() as session:
                proxy, cookie = await get_next_proxy_cookie_async(session)
                
                # URL глобального поиска (с ротацией доменов)
                current_domain, nitter_base = get_nitter_domain_and_url()
                search_url = f"{nitter_base}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                
                # Заголовки
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cookie': cookie
                }
                
                # Добавляем заголовок Host для специальных IP-адресов
                add_host_header_if_needed(headers, current_domain)
                
                # Настройка соединения
                connector = aiohttp.TCPConnector(ssl=False)
                request_kwargs = {}
                if proxy:
                    request_kwargs['proxy'] = proxy
                
                # Поиск по страницам (без ограничений - до конца результатов)
                current_url = search_url
                page = 0
                
                while current_url:  # Просматриваем ВСЕ страницы до конца результатов
                    page += 1
                    logger.info(f"🌍 Глобальный поиск \"{search_query}\" - страница {page}")
                    
                    # Применяем глобальный rate limiting
                    await self._apply_global_rate_limit()
                    
                    # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС с дополнительной обработкой TimeoutError
                    try:
                        response = await network_retry_wrapper(session, 'get', current_url, 
                                                             headers=headers, timeout=15, **request_kwargs)
                    except asyncio.TimeoutError:
                        logger.warning(f"⏰ {current_domain}: timeout ошибка на странице {page} глобального поиска - переключаемся на следующий домен!")
                        
                        # Переключаемся на следующий домен Nitter
                        from nitter_domain_rotator import get_next_nitter_domain
                        new_domain = get_next_nitter_domain()
                        logger.warning(f"🌐 Переключились на новый домен: {new_domain}")
                        
                        # Обновляем URL с новым доменом
                        from urllib.parse import urlparse, urlunparse
                        parsed_url = urlparse(current_url)
                        new_base_url = format_nitter_url(new_domain)
                        current_url = f"{new_base_url}{parsed_url.path}"
                        if parsed_url.query:
                            current_url += f"?{parsed_url.query}"
                        
                        # Обновляем домен для заголовков
                        current_domain = new_domain
                        add_host_header_if_needed(headers, current_domain)
                        
                        # Повторяем запрос с новым доменом
                        await asyncio.sleep(2)
                        page -= 1  # Повторяем ту же страницу
                        continue
                    
                    logger.info(f"URL запроса: {current_url}")

                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Проверяем на блокировку Nitter
                        title = soup.find('title')
                        if title and 'Making sure you\'re not a bot!' in title.get_text():
                            logger.warning(f"🚫 Nitter заблокирован на странице {page + 1} глобального поиска - пытаемся восстановить")
                            
                            # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                            retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, current_url, f"глобальный поиск страница {page + 1}", html)
                            
                            if retry_soup:
                                # Успешно восстановились, используем новый soup
                                soup = retry_soup
                                logger.info(f"✅ Восстановление успешно для страницы {page + 1} глобального поиска")
                            else:
                                # НИКОГДА НЕ СДАЕМСЯ! Получаем новый прокси и пробуем снова
                                logger.warning(f"❌ Не удалось восстановиться для страницы {page + 1} глобального поиска - пробуем новый прокси!")
                                
                                # Блокируем текущий прокси и получаем новый
                                mark_proxy_temp_blocked(proxy, cookie, 120)
                                
                                # Получаем новый прокси и куки
                                proxy, cookie = await get_next_proxy_cookie_async(session)
                                
                                # Обновляем request_kwargs и headers
                                request_kwargs = {}
                                if proxy:
                                    request_kwargs['proxy'] = proxy
                                
                                headers['Cookie'] = cookie
                                
                                # Откатываемся на одну страницу назад чтобы повторить
                                page -= 1
                                await asyncio.sleep(2)
                                continue
                        
                        # Ищем твиты на текущей странице
                        tweets = soup.find_all('div', class_='timeline-item')
                        page_accounts_count = 0
                        
                        if tweets:
                            for tweet in tweets:
                                # Извлекаем автора твита
                                author_elem = tweet.find('a', class_='username')
                                tweet_content = tweet.find('div', class_='tweet-content')
                                tweet_date_elem = tweet.find('span', class_='tweet-date')
                                
                                if author_elem and tweet_content and tweet_date_elem:
                                    author = author_elem.get_text(strip=True).replace('@', '')
                                    tweet_text = tweet_content.get_text(strip=True)
                                    
                                    # Проверяем наличие символа с $ в тексте твита (регистронезависимо)
                                    if symbol_pattern in tweet_text.upper():
                                        # Проверяем возраст твита - только свежие (< 30 дней)
                                        tweet_age = self._get_tweet_age(tweet_date_elem)
                                        one_month_ago = datetime.now() - timedelta(days=30)
                                        
                                        if tweet_age and tweet_age > one_month_ago:
                                            if author not in found_accounts:
                                                # 🆕 НОВЫЙ ФИЛЬТР: Проверяем сходство никнейма с токеном
                                                # Для глобального поиска берем только название из символа
                                                token_name = symbol  # В глобальном поиске name недоступно
                                                is_similar = self._is_twitter_username_similar_to_token(author, token_name, symbol)
                                                
                                                if is_similar:
                                                    found_accounts.add(author)
                                                    page_accounts_count += 1
                                                    logger.info(f"✅ Найден ПОХОЖИЙ аккаунт @{author} с \"{symbol_pattern}\" ({tweet_age.strftime('%Y-%m-%d')})")
                                                else:
                                                    logger.debug(f"🚫 Аккаунт @{author} НЕ похож на токен {symbol} - пропускаем")
                                        else:
                                            logger.debug(f"⏰ Пропущен старый твит от @{author} с \"{symbol_pattern}\"")
                            
                            logger.info(f"📄 Глобальный поиск страница {page + 1}: найдено {page_accounts_count} новых аккаунтов с \"{symbol_pattern}\"")
                        else:
                            logger.debug(f"🚫 На странице {page + 1} глобального поиска твиты не найдены")
                        
                        # Ищем ссылку на следующую страницу
                        next_link = None
                        
                        # Вариант 1: ищем элемент div.show-more с ссылкой внутри
                        show_more = soup.find('div', class_='show-more')
                        if show_more:
                            next_link = show_more.find('a')
                            if next_link and next_link.get('href'):
                                logger.debug(f"🔗 Найдена ссылка в .show-more: {next_link['href']}")
                                
                        # Вариант 2: ищем ссылку "Load more" по тексту
                        if not next_link:
                            next_link = soup.find('a', string=lambda text: text and ('load more' in text.lower() or 'more' in text.lower()))
                            if next_link:
                                logger.debug(f"🔗 Найдена ссылка по тексту 'Load more': {next_link['href']}")
                        
                        # Вариант 3: ищем любую ссылку содержащую 'cursor=' или 'max_position='
                        if not next_link:
                            all_links = soup.find_all('a', href=True)
                            for link in all_links:
                                if 'cursor=' in link['href'] or 'max_position=' in link['href']:
                                    next_link = link
                                    logger.debug(f"🔗 Найдена ссылка с cursor: {next_link['href']}")
                                    break
                        
                        # Проверяем есть ли следующая страница (без ограничений)
                        if next_link and 'href' in next_link.attrs:
                            next_url = next_link['href']
                            
                            # Правильно формируем URL для следующей страницы (с ротацией доменов)
                            if next_url.startswith('/'):
                                current_url = f"{nitter_base}{next_url}"
                            elif next_url.startswith('?'):
                                # Если это только параметры, заменяем параметры в базовом URL
                                current_url = f"{nitter_base}/search{next_url}"
                            else:
                                current_url = next_url
                            
                            logger.debug(f"🔗 Следующая страница глобального поиска: {current_url}")
                            
                            # Максимальная пауза между страницами (увеличена из-за rate limiting)
                            await asyncio.sleep(random.uniform(15, 30))
                        else:
                            logger.debug(f"🚫 Следующая страница не найдена - завершаем глобальный поиск")
                            current_url = None  # Завершаем while цикл
                    elif response.status == 429:
                        # HTTP 429 - это проблема домена, а не прокси
                        self._track_429_error()
                        
                        logger.warning(f"🌐 HTTP 429 на странице {page + 1} глобального поиска - переключаемся на следующий домен!")
                        
                        # Переключаемся на следующий домен Nitter
                        from nitter_domain_rotator import get_next_nitter_domain
                        new_domain = get_next_nitter_domain()
                        logger.warning(f"🌐 Переключились на новый домен: {new_domain}")
                        
                        # Обновляем URL с новым доменом
                        from urllib.parse import urlparse, urlunparse
                        parsed_url = urlparse(current_url)
                        new_base_url = format_nitter_url(new_domain)
                        current_url = f"{new_base_url}{parsed_url.path}"
                        if parsed_url.query:
                            current_url += f"?{parsed_url.query}"
                        
                        # Короткая пауза и повтор той же страницы с новым доменом
                        await asyncio.sleep(2)
                        page -= 1  # Повторяем ту же страницу
                        continue
                    else:
                        logger.warning(f"❌ Ошибка загрузки страницы {page} глобального поиска: HTTP {response.status}")
                        current_url = None  # Завершаем поиск при серьезных ошибках
                
                found_accounts_list = list(found_accounts)
                logger.info(f"🌍 Глобальный поиск завершен: найдено {len(found_accounts_list)} уникальных аккаунтов с \"{symbol_pattern}\"")
                
                # 🗂️ СОХРАНЯЕМ РЕЗУЛЬТАТ В КЕШ для избежания повторных запросов
                self.twitter_check_cache[cache_key] = {
                    'found_accounts': found_accounts_list,
                    'last_check': current_time,
                    'error': None
                }
                
                return found_accounts_list
                    
        except Exception as e:
            import traceback
            logger.error(f"❌ Ошибка глобального поиска символа {symbol}: {e}")
            logger.error(f"📋 Полный traceback: {traceback.format_exc()}")
            
            # 🔄 ДОПОЛНИТЕЛЬНАЯ ПОПЫТКА: Если это TimeoutError, попробуем еще раз с другим доменом
            if isinstance(e, asyncio.TimeoutError):
                logger.warning(f"⏰ Последняя попытка глобального поиска для {symbol} через другой домен...")
                
                try:
                    # Получаем новый домен и прокси
                    from nitter_domain_rotator import get_next_nitter_domain
                    from dynamic_cookie_rotation import get_next_proxy_cookie_async
                    
                    backup_domain = get_next_nitter_domain()
                    backup_proxy, backup_cookie = await get_next_proxy_cookie_async(session)
                    
                    logger.warning(f"🔄 Резервная попытка с доменом {backup_domain}")
                    
                    # Формируем резервный URL
                    backup_base_url = format_nitter_url(backup_domain)
                    backup_search_url = f"{backup_base_url}/search?f=tweets&q=\"{symbol_pattern}\"&since=&until=&near="
                    
                    # Обновляем заголовки
                    headers['Cookie'] = backup_cookie
                    add_host_header_if_needed(headers, backup_domain)
                    
                    # Обновляем прокси
                    backup_kwargs = {}
                    if backup_proxy:
                        backup_kwargs['proxy'] = backup_proxy
                    
                    # Делаем резервный запрос с коротким таймаутом
                    backup_response = await network_retry_wrapper(session, 'get', backup_search_url, 
                                                                headers=headers, timeout=15, **backup_kwargs)
                    
                    if backup_response.status == 200:
                        logger.info(f"✅ Резервная попытка успешна! Обрабатываем результаты...")
                        
                        html = await backup_response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Быстрая обработка только первой страницы
                        tweets = soup.find_all('div', class_='timeline-item')
                        backup_accounts = set()
                        
                        if tweets:
                            for tweet in tweets:
                                author_elem = tweet.find('a', class_='username')
                                tweet_content = tweet.find('div', class_='tweet-content')
                                tweet_date_elem = tweet.find('span', class_='tweet-date')
                                
                                if author_elem and tweet_content and tweet_date_elem:
                                    author = author_elem.get_text(strip=True).replace('@', '')
                                    tweet_text = tweet_content.get_text(strip=True)
                                    
                                    if symbol_pattern in tweet_text.upper():
                                        tweet_age = self._get_tweet_age(tweet_date_elem)
                                        one_month_ago = datetime.now() - timedelta(days=30)
                                        
                                        if tweet_age and tweet_age > one_month_ago:
                                            backup_accounts.add(author)
                                            logger.info(f"✅ Резервный поиск: найден @{author} с \"{symbol_pattern}\"")
                        
                        backup_accounts_list = list(backup_accounts)
                        if backup_accounts_list:
                            logger.info(f"🔄 Резервный поиск успешен: найдено {len(backup_accounts_list)} аккаунтов")
                            
                            # Сохраняем результат в кэш
                            self.twitter_check_cache[cache_key] = {
                                'found_accounts': backup_accounts_list,
                                'last_check': current_time,
                                'error': None
                            }
                            
                            return backup_accounts_list
                        else:
                            logger.warning(f"🔄 Резервный поиск не дал результатов")
                    else:
                        logger.warning(f"🔄 Резервный поиск неуспешен: HTTP {backup_response.status}")
                        
                except Exception as backup_error:
                    logger.error(f"❌ Ошибка резервного поиска: {backup_error}")
            
            # 🗂️ СОХРАНЯЕМ ОШИБКУ В КЕШ для избежания повторных попыток
            self.twitter_check_cache[cache_key] = {
                'found_accounts': [],
                'last_check': current_time,
                'error': str(e)
            }
            
            return []

    async def _check_contracts_in_twitter(self, twitter_account: str) -> bool:
        """Проверяет наличие контрактов в Twitter аккаунте (3 страницы) с повторными попытками при таймауте"""
        from dynamic_cookie_rotation import get_next_proxy_cookie_async, mark_proxy_temp_blocked
        
        max_attempts = 5  # Максимум 5 попыток при таймауте
        
        for attempt in range(max_attempts):
            try:
                # Получаем cookie для поиска
                async with aiohttp.ClientSession() as session:
                    proxy, cookie = await get_next_proxy_cookie_async(session)
                    
                    # СНАЧАЛА проверяем основную страницу профиля (био) (с ротацией доменов)
                    current_domain, nitter_base = get_nitter_domain_and_url()
                    profile_url = f"{nitter_base}/{twitter_account}"
                    
                    # Заголовки
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cookie': cookie
                    }
                    
                    # Добавляем заголовок Host для специальных IP-адресов
                    add_host_header_if_needed(headers, current_domain)
                    
                    # Настройка соединения
                    connector = aiohttp.TCPConnector(ssl=False)
                    request_kwargs = {}
                    if proxy:
                        request_kwargs['proxy'] = proxy
                    
                    logger.debug(f"🔍 Проверяем био профиля @{twitter_account}")
                    
                    # Применяем глобальный rate limiting
                    await self._apply_global_rate_limit()
                    
                    # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ПРОФИЛЯ
                    response = await network_retry_wrapper(session, 'get', profile_url, 
                                                        headers=headers, timeout=15, **request_kwargs)
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Проверяем на блокировку Nitter
                        title = soup.find('title')
                        if title and 'Making sure you\'re not a bot!' in title.get_text():
                            logger.warning(f"🚫 Nitter заблокирован для профиля @{twitter_account} - пытаемся восстановить")
                            
                            # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                            retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, profile_url, f"профиль @{twitter_account}", html)
                            
                            if retry_soup:
                                # Успешно восстановились, используем новый soup
                                soup = retry_soup
                                logger.info(f"✅ Восстановление успешно для профиля @{twitter_account}")
                            else:
                                # НИКОГДА НЕ СДАЕМСЯ! Повторяем попытки с новым прокси
                                logger.warning(f"❌ Первая попытка восстановления не удалась для @{twitter_account} - пробуем с новым прокси!")
                                
                                # Блокируем текущий прокси и получаем новый
                                mark_proxy_temp_blocked(proxy, cookie)
                                
                                # Получаем новый прокси и куки
                                proxy, cookie = await get_next_proxy_cookie_async(session)
                                
                                # Обновляем request_kwargs с новым прокси
                                request_kwargs = {}
                                if proxy:
                                    request_kwargs['proxy'] = proxy
                                
                                # Делаем новую попытку загрузки профиля
                                logger.info(f"🔄 Повторная попытка загрузки профиля @{twitter_account} с новым прокси")
                                await asyncio.sleep(2)
                                
                                # Рекурсивно вызываем функцию для повторной попытки
                                return await self._check_contracts_in_twitter(twitter_account)
                        
                        # Проверяем био только если soup доступен
                        if soup:
                            # Ищем био профиля
                            bio_element = soup.find('div', class_='profile-bio')
                            if bio_element:
                                bio_text = bio_element.get_text()
                                logger.debug(f"📋 Био @{twitter_account}: {bio_text[:100]}...")
                                
                                # Ищем паттерны Solana контрактов в био
                                solana_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
                                potential_contracts = re.findall(solana_pattern, bio_text)
                                
                                if potential_contracts:
                                    logger.warning(f"🚫 Найдены контракты в БИО @{twitter_account}: {len(potential_contracts)} шт.")
                                    for contract in potential_contracts:
                                        logger.warning(f"   📋 Контракт в био: {contract}")
                                    return True
                                else:
                                    logger.debug(f"✅ Контракты в био @{twitter_account} НЕ найдены")
                            else:
                                logger.debug(f"⚠️ Био не найдено для @{twitter_account}")
                    else:
                        logger.warning(f"❌ Ошибка загрузки профиля @{twitter_account}: HTTP {response.status}")
                    
                    # ЗАТЕМ проверяем твиты через поиск (максимум 3 страницы)
                    logger.debug(f"🔍 Проверяем твиты @{twitter_account}")
                    
                    # Ищем любые потенциальные контракты через поиск (с ротацией доменов)
                    search_query = "pump OR raydium OR solana OR token OR contract"
                    current_url = f"{nitter_base}/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                    
                    for page in range(3):  # Максимум 3 страницы
                        logger.debug(f"🔍 Страница {page + 1} поиска контрактов в @{twitter_account}")
                        
                        # Применяем глобальный rate limiting
                        await self._apply_global_rate_limit()
                        
                        # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ПОИСКА КОНТРАКТОВ
                        response = await network_retry_wrapper(session, 'get', current_url, 
                                                            headers=headers, timeout=15, **request_kwargs)
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Проверяем на блокировку Nitter
                            title = soup.find('title')
                            if title and 'Making sure you\'re not a bot!' in title.get_text():
                                logger.warning(f"🚫 Nitter заблокирован на странице {page + 1} для @{twitter_account} - пытаемся восстановить")
                                
                                # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                                retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, current_url, f"страница {page + 1} поиска @{twitter_account}", html)
                                
                                if retry_soup:
                                    # Успешно восстановились, используем новый soup
                                    soup = retry_soup
                                    logger.info(f"✅ Восстановление успешно для страницы {page + 1} поиска @{twitter_account}")
                                else:
                                    # НИКОГДА НЕ СДАЕМСЯ! Получаем новый прокси и пробуем снова
                                    logger.warning(f"❌ Не удалось восстановиться для страницы {page + 1} поиска @{twitter_account} - пробуем новый прокси!")
                                    
                                    # Блокируем текущий прокси и получаем новый
                                    mark_proxy_temp_blocked(proxy, cookie)
                                    
                                    # Получаем новый прокси и куки
                                    proxy, cookie = await get_next_proxy_cookie_async(session)
                                    
                                    # Обновляем request_kwargs и headers
                                    request_kwargs = {}
                                    if proxy:
                                        request_kwargs['proxy'] = proxy
                                    
                                    headers['Cookie'] = cookie
                                    
                                    # Откатываемся на одну страницу назад чтобы повторить
                                    page -= 1
                                    await asyncio.sleep(2)
                                    continue
                            
                            # Извлекаем весь текст со страницы
                            page_text = soup.get_text()
                            
                            # Ищем паттерны Solana контрактов (base58, 32-44 символа)
                            solana_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
                            potential_contracts = re.findall(solana_pattern, page_text)
                            
                            if potential_contracts:
                                logger.warning(f"🚫 Найдены контракты в @{twitter_account} на странице {page + 1}: {len(potential_contracts)} шт.")
                                return True
                            
                            # Ищем ссылку на следующую страницу - правильный поиск в .show-more
                            next_link = None
                            
                            # Вариант 1: ищем элемент div.show-more с ссылкой внутри
                            show_more = soup.find('div', class_='show-more')
                            if show_more:
                                next_link = show_more.find('a')
                                if next_link and next_link.get('href'):
                                    logger.debug(f"🔗 Найдена ссылка в .show-more: {next_link['href']}")
                                    
                            # Вариант 2: ищем ссылку "Load more" по тексту
                            if not next_link:
                                next_link = soup.find('a', string=lambda text: text and ('load more' in text.lower() or 'more' in text.lower()))
                                if next_link:
                                    logger.debug(f"🔗 Найдена ссылка по тексту 'Load more': {next_link['href']}")
                            
                            # Вариант 3: ищем любую ссылку содержащую 'cursor=' или 'max_position='
                            if not next_link:
                                all_links = soup.find_all('a', href=True)
                                for link in all_links:
                                    if 'cursor=' in link['href'] or 'max_position=' in link['href']:
                                        next_link = link
                                        logger.debug(f"🔗 Найдена ссылка с cursor: {next_link['href']}")
                                        break
                            
                            if next_link and 'href' in next_link.attrs and page < 2:
                                next_url = next_link['href']
                                
                                # Правильно формируем URL для следующей страницы (с ротацией доменов)
                                if next_url.startswith('/'):
                                    current_url = f"{nitter_base}{next_url}"
                                elif next_url.startswith('?'):
                                    # Если это только параметры, заменяем параметры в базовом URL
                                    current_url = f"{nitter_base}/{twitter_account}/search{next_url}"
                                else:
                                    current_url = next_url
                                
                                logger.debug(f"🔗 Следующая страница контрактов: {current_url}")
                                
                                # Увеличенная пауза между страницами
                                await asyncio.sleep(random.uniform(10, 20))
                            else:
                                logger.debug(f"🚫 Следующая страница не найдена или достигнут лимит")
                                break
                        else:
                            logger.warning(f"❌ Ошибка загрузки страницы {page + 1} для @{twitter_account}: HTTP {response.status}")
                            break
                    
                    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: страница with_replies (максимум 5 страниц) (с ротацией доменов)
                    logger.debug(f"🔍 Проверяем страницу with_replies @{twitter_account}")
                    
                    current_url = f"{nitter_base}/{twitter_account}/with_replies"
                    
                    for page in range(5):  # Максимум 5 страниц
                        logger.debug(f"🔍 Страница {page + 1} with_replies для @{twitter_account}")
                        
                        # Применяем глобальный rate limiting
                        await self._apply_global_rate_limit()
                        
                        # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ WITH_REPLIES
                        response = await network_retry_wrapper(session, 'get', current_url, 
                                                            headers=headers, timeout=15, **request_kwargs)
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Проверяем на блокировку Nitter
                            title = soup.find('title')
                            if title and 'Making sure you\'re not a bot!' in title.get_text():
                                logger.warning(f"🚫 Nitter заблокирован на странице {page + 1} with_replies для @{twitter_account} - пытаемся восстановить")
                                
                                # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                                retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, current_url, f"страница {page + 1} with_replies @{twitter_account}", html)
                                
                                if retry_soup:
                                    # Успешно восстановились, используем новый soup
                                    soup = retry_soup
                                    logger.info(f"✅ Восстановление успешно для страницы {page + 1} with_replies @{twitter_account}")
                                else:
                                    # НИКОГДА НЕ СДАЕМСЯ! Получаем новый прокси и пробуем снова
                                    logger.warning(f"❌ Не удалось восстановиться для страницы {page + 1} with_replies @{twitter_account} - пробуем новый прокси!")
                                    
                                    # Блокируем текущий прокси и получаем новый
                                    mark_proxy_temp_blocked(proxy, cookie)
                                    
                                    # Получаем новый прокси и куки
                                    proxy, cookie = await get_next_proxy_cookie_async(session)
                                    
                                    # Обновляем request_kwargs и headers
                                    request_kwargs = {}
                                    if proxy:
                                        request_kwargs['proxy'] = proxy
                                    
                                    headers['Cookie'] = cookie
                                    
                                    # Откатываемся на одну страницу назад чтобы повторить
                                    page -= 1
                                    await asyncio.sleep(2)
                                    continue
                            
                            # Извлекаем весь текст со страницы
                            page_text = soup.get_text()
                            
                            # Ищем паттерны Solana контрактов (base58, 32-44 символа)
                            solana_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
                            potential_contracts = re.findall(solana_pattern, page_text)
                            
                            if potential_contracts:
                                logger.warning(f"🚫 Найдены контракты в @{twitter_account} на странице {page + 1} with_replies: {len(potential_contracts)} шт.")
                                for contract in potential_contracts:
                                    logger.warning(f"   💰 Контракт в with_replies: {contract}")
                                return True
                            
                            # Ищем ссылку на следующую страницу - правильный поиск в .show-more
                            next_link = None
                            
                            # Вариант 1: ищем элемент div.show-more с ссылкой внутри
                            show_more = soup.find('div', class_='show-more')
                            if show_more:
                                next_link = show_more.find('a')
                                if next_link and next_link.get('href'):
                                    logger.debug(f"🔗 Найдена ссылка в .show-more: {next_link['href']}")
                                    
                            # Вариант 2: ищем ссылку "Load more" по тексту
                            if not next_link:
                                next_link = soup.find('a', string=lambda text: text and ('load more' in text.lower() or 'more' in text.lower()))
                                if next_link:
                                    logger.debug(f"🔗 Найдена ссылка по тексту 'Load more': {next_link['href']}")
                            
                            # Вариант 3: ищем любую ссылку содержащую 'cursor=' или 'max_position='
                            if not next_link:
                                all_links = soup.find_all('a', href=True)
                                for link in all_links:
                                    if 'cursor=' in link['href'] or 'max_position=' in link['href']:
                                        next_link = link
                                        logger.debug(f"🔗 Найдена ссылка с cursor: {next_link['href']}")
                                        break
                            
                            if next_link and 'href' in next_link.attrs:
                                next_url = next_link['href']
                                
                                # Правильно формируем URL для следующей страницы (с ротацией доменов)
                                if next_url.startswith('/'):
                                    current_url = f"{nitter_base}{next_url}"
                                elif next_url.startswith('?'):
                                    # Если это только параметры, заменяем параметры в базовом URL
                                    current_url = f"{nitter_base}/{twitter_account}/with_replies{next_url}"
                                else:
                                    current_url = next_url
                                
                                logger.debug(f"🔗 Следующая страница with_replies: {current_url}")
                                
                                # Увеличенная пауза между страницами
                                await asyncio.sleep(random.uniform(10, 20))
                            else:
                                logger.debug(f"🚫 Следующая страница with_replies не найдена или достигнут лимит")
                                break
                        else:
                            logger.warning(f"❌ Ошибка загрузки страницы {page + 1} with_replies для @{twitter_account}: HTTP {response.status}")
                            break
                    
                    logger.info(f"✅ Контракты НЕ найдены в @{twitter_account} (проверено: био + 3 страницы твитов + 5 страниц with_replies)")
                    return False
                    
            except Exception as e:
                error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
                
                # Проверяем на таймаут или сетевые ошибки
                is_timeout_error = any(keyword in error_msg.lower() for keyword in [
                    'timeout', 'timed out', 'connection', 'network', 'disconnected', 
                    'unreachable', 'refused', 'reset', 'aborted'
                ])
                
                if is_timeout_error and attempt < max_attempts - 1:
                    delay = min(30, (attempt + 1) * 3)  # 3, 6, 9, 12, 15 секунд
                    logger.warning(f"⏰ Таймаут при проверке контрактов @{twitter_account} (попытка {attempt + 1}/{max_attempts}). Повтор через {delay}с...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ Ошибка проверки контрактов в @{twitter_account}: {error_msg}")
                    return False
        
        logger.error(f"💀 Все {max_attempts} попыток исчерпаны для проверки контрактов @{twitter_account}")
        return False
    
    async def add_token_to_group(self, token_data: Dict, reason: str = "Обнаружен токен") -> bool:
        """Добавляет токен в группу (создает группу даже для одного токена)"""
        try:
            group_key = self.create_group_key(token_data)
            token_id = token_data.get('id')
            symbol = token_data.get('symbol', 'Unknown')
            name = token_data.get('name', 'Unknown')
            
            # 🔍 НОВАЯ ЛОГИКА: Сначала ищем существующую группу с таким же символом
            existing_group = None
            existing_group_key = None
            
            for key, group in self.groups.items():
                if group.symbol.upper() == symbol.upper():
                    existing_group = group
                    existing_group_key = key
                    logger.info(f"🔍 Найдена существующая группа для символа {symbol}: {key}")
                    break
            
            # Если найдена существующая группа с таким символом - добавляем токен туда
            if existing_group:
                logger.info(f"➡️ Добавляем токен {symbol} в существующую группу {existing_group_key}")
                
                # 🚫 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Если в главном аккаунте есть контракты, скипаем добавление
                if existing_group.main_twitter:
                    has_contracts = await self._check_contracts_in_twitter(existing_group.main_twitter)
                    if has_contracts:
                        logger.warning(f"🐛🚫 WORMSTER ЗАБЛОКИРОВАЛ ТОКЕН {symbol}: Главный Twitter @{existing_group.main_twitter} светит контракты! Не любим спойлеры! 🤬")
                        return False
                
                # Проверяем, не добавлен ли уже этот токен
                existing_ids = [t.get('id') for t in existing_group.tokens]
                if token_id in existing_ids:
                    logger.debug(f"🔄 Токен {token_id[:8]}... уже в группе {existing_group_key}")
                    # 🎯 ИСПРАВЛЕНИЕ: Обновляем latest_added_token даже если токен уже есть
                    existing_group.latest_added_token = self._enrich_token_with_date(token_data)
                    existing_group.last_updated = datetime.now()
                    
                    # Обновляем сообщение с актуальными данными
                    # 🌍 ПРОВЕРКА: Если группа найдена через глобальный поиск - обновляем в личном чате
                    if existing_group.is_global_search_group:
                        await self._update_private_group_message(existing_group)
                    else:
                        await self._update_group_message(existing_group)
                    return True
                
                # Добавляем новый токен в существующую группу
                existing_group.tokens.append(token_data)
                existing_group.latest_added_token = self._enrich_token_with_date(token_data)
                existing_group.last_updated = datetime.now()
                
                # НЕ пересчитываем главный Twitter - используем существующий
                logger.info(f"🐛✅ WORMSTER ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен {symbol} добавлен в существующую группу (главный Twitter: @{existing_group.main_twitter or 'не определен'})")
                
                # 🔧 ИСПРАВЛЕНИЕ: Всегда пересоздаем таблицу с полным списком токенов
                logger.info(f"🔄 Пересоздаем таблицу для группы {symbol} с {len(existing_group.tokens)} токенами...")
                self._create_sheet_and_update_message_async(existing_group_key, existing_group.tokens, existing_group.main_twitter)
                
                logger.info(f"🐛✅ WORMSTER ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен {symbol} добавлен в группу (всего токенов: {len(existing_group.tokens)}) 🎯")
                return True
            
            # Если группы нет - проверяем, существует ли группа с точным ключом
            if group_key not in self.groups:
                # Создаем новую группу токенов
                logger.info(f"🆕 Создаем новую группу токенов: {symbol}")
                
                # Загружаем все токены этого символа из БД
                db_tokens = self._load_tokens_from_db(symbol)
                
                # Создаем группу
                group = self.GroupData(group_key, symbol, name)
                group.tokens = db_tokens + [token_data] if token_data not in db_tokens else db_tokens
                group.latest_added_token = self._enrich_token_with_date(token_data)  # 🎯 Обогащаем датой из БД!
                
                # Определяем главный Twitter аккаунт (новая логика с проверкой символа в кавычках)
                group.main_twitter = await self.determine_main_twitter(group.tokens)
                
                # # 🌍 НОВАЯ ЛОГИКА: Если главный Twitter не определен, пробуем глобальный поиск
                # if not group.main_twitter:
                #     logger.info(f"🌍 Токены {symbol} НЕ имеют Twitter ссылок - пробуем ГЛОБАЛЬНЫЙ ПОИСК...")
                    
                #     # Проверяем, есть ли у токенов в группе Twitter ссылки
                #     has_any_twitter_links = any(
                #         self.extract_twitter_accounts(token) for token in group.tokens
                #     )
                    
                #     if not has_any_twitter_links:
                #         # Токены вообще не имеют Twitter ссылок - используем глобальный поиск
                #         logger.info(f"🌍 Группа {symbol} БЕЗ Twitter ссылок - ищем через глобальный поиск...")
                #         global_main_twitter = await self.determine_main_twitter_from_global_search(symbol)
                        
                #         if global_main_twitter:
                #             group.main_twitter = global_main_twitter
                #             group.is_global_search_group = True  # Помечаем как группу найденную через глобальный поиск
                #             logger.info(f"🌍✅ Найден главный Twitter через ГЛОБАЛЬНЫЙ ПОИСК: @{global_main_twitter}")
                #         else:
                #             # Проверяем причину неудачи глобального поиска
                #             cache_key = f"global_search_{symbol}"
                #             cached_result = self.twitter_check_cache.get(cache_key, {})
                #             error_reason = cached_result.get('error', 'Неизвестная причина')
                            
                #             if error_reason and 'TimeoutError' in str(error_reason):
                #                 logger.error(f"🌍💥 КРИТИЧЕСКАЯ ОШИБКА: Глобальный поиск для {symbol} упал с TimeoutError - БОТ ПРОПУСКАЕТ ТОКЕНЫ!")
                #                 logger.error(f"🔧 Требуется проверка доменов Nitter и прокси!")
                #             else:
                #                 logger.warning(f"🌍🚫 Глобальный поиск НЕ нашел подходящий Twitter для {symbol} (причина: {error_reason})")
                
                # ⚠️ СМЯГЧЕННАЯ ПРОВЕРКА: Если главный Twitter не определен, всё равно создаем группу, но с предупреждением
                if not group.main_twitter:
                    logger.warning(f"⚠️ Группа {symbol} создана БЕЗ главного Twitter аккаунта - токены будут отслеживаться, но без проверки анонса")
                    
                    # 🚀 Создаем группу без Twitter аккаунта В ФОНЕ (БЕЗ ОТПРАВКИ СООБЩЕНИЯ)
                    group.official_announcement = None
                    group.sheet_url = None
                    group.message_id = None  # НЕ отправляем сообщение в Telegram без анонса
                    
                    # Сохраняем группу
                    self.groups[group_key] = group
                    
                    # Запускаем создание таблицы асинхронно (даже без Twitter)
                    self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                    
                    logger.info(f"🐛📊 WORMSTER СОЗДАЛ СКРЫТУЮ ГРУППУ {symbol} БЕЗ TELEGRAM СООБЩЕНИЯ! Копает таблицы в фоне! 📊")
                    return True
                
                # 🚫 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Если в главном аккаунте есть контракты, скипаем группу
                has_contracts = await self._check_contracts_in_twitter(group.main_twitter)
                if has_contracts:
                    logger.warning(f"🚫 Группа {symbol} НЕ создана: в главном Twitter @{group.main_twitter} найдены контракты")
                    return False
                
                # 🔍 НОВАЯ ЛОГИКА: Ищем самый старый твит как анонс (не обязательно с символом)
                oldest_mention = await self._find_oldest_announcement(group.main_twitter, symbol)
                if oldest_mention:
                    group.official_announcement = oldest_mention
                    logger.info(f"📅 Найден официальный анонс токена {symbol} от {oldest_mention['date']}")
                else:
                    group.official_announcement = None
                    logger.warning(f"🐛❌ WORMSTER НЕ НАШЁЛ АНОНС В @{group.main_twitter}! НЕ отправляем сообщение без анонса! 🚫")
                
                # 🚀 ПОЛНОСТЬЮ АСИНХРОННАЯ ЛОГИКА: сообщение БЕЗ кнопки, затем таблица в фоне
                logger.info(f"📊 Группа {symbol} создается асинхронно...")
                
                # 🚫 СТРОГАЯ ПРОВЕРКА: Отправляем сообщение ТОЛЬКО если есть официальный анонс
                group.sheet_url = None  # Пока нет таблицы
                if group.official_announcement:
                    # 🚫 ОТКЛЮЧЕНЫ ЛИЧНЫЕ СООБЩЕНИЯ: Отправляем только в основной чат
                    group.message_id = await self._send_group_message(group)
                    if group.message_id:
                        logger.info(f"✅ Сообщение о группе {symbol} отправлено в Telegram (есть анонс)")
                    else:
                        logger.warning(f"🚫 Сообщение о группе {symbol} НЕ отправлено - недостаточно информации о Twitter")
                else:
                    group.message_id = None  # НЕ отправляем сообщение без анонса
                    logger.info(f"🚫 Сообщение о группе {symbol} НЕ отправлено (нет анонса)")
                
                # Сохраняем группу
                self.groups[group_key] = group
                
                # Запускаем создание таблицы асинхронно (в фоновом потоке)
                self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                
                logger.info(f"🐛🎉 WORMSTER СОЗДАЛ НОВУЮ ОХОТНИЧЬЮ СТАЮ {symbol}! Теперь копает таблицы в фоне! 📊")
                return True
                
            else:
                # Обновляем существующую группу с точным ключом
                group = self.groups[group_key]
                
                # 🚫 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Если в главном аккаунте есть контракты, скипаем добавление
                if group.main_twitter:
                    has_contracts = await self._check_contracts_in_twitter(group.main_twitter)
                    if has_contracts:
                        logger.warning(f"🐛🚫 WORMSTER ЗАБЛОКИРОВАЛ ТОКЕН {symbol}: Главный Twitter @{group.main_twitter} светит контракты! Не любим спойлеры! 🤬")
                        return False
                
                # Проверяем, не добавлен ли уже этот токен
                existing_ids = [t.get('id') for t in group.tokens]
                if token_id in existing_ids:
                    logger.debug(f"🔄 Токен {token_id[:8]}... уже в группе {group_key}")
                    # 🎯 ИСПРАВЛЕНИЕ: Обновляем latest_added_token даже если токен уже есть
                    group.latest_added_token = self._enrich_token_with_date(token_data)  # Обогащаем датой из БД!
                    group.last_updated = datetime.now()
                    
                    # Обновляем сообщение с актуальными данными (только если есть анонс)
                    if group.official_announcement and group.message_id:
                        await self._update_group_message(group)
                    return True
                
                # Добавляем новый токен
                group.tokens.append(token_data)
                group.latest_added_token = self._enrich_token_with_date(token_data)  # 🎯 Обогащаем датой из БД!
                group.last_updated = datetime.now()
                
                # Пересчитываем главный Twitter аккаунт
                new_main_twitter = await self.determine_main_twitter(group.tokens)
                if new_main_twitter != group.main_twitter:
                    # Если главный Twitter изменился, проверяем новый аккаунт на контракты
                    if new_main_twitter:
                        has_contracts = await self._check_contracts_in_twitter(new_main_twitter)
                        if has_contracts:
                            logger.warning(f"🚫 Группа {symbol} скипается: новый главный Twitter @{new_main_twitter} содержит контракты")
                            return False
                    
                    group.main_twitter = new_main_twitter
                    # Обновляем статусы в Google Sheets асинхронно с приоритетом
                    priority = 0 if group.message_id else 1  # Высокий приоритет для отправленных групп
                    sheets_manager.update_main_twitter_async(group_key, new_main_twitter, priority=priority)
                    
                    # Обновляем официальный анонс если изменился главный аккаунт
                    if new_main_twitter:
                        oldest_mention = await self._find_oldest_announcement(new_main_twitter, symbol)
                        group.official_announcement = oldest_mention
                        
                        # 🚀 НОВАЯ ЛОГИКА: Если анонс найден впервые, отправляем сообщение
                        if oldest_mention and not group.message_id:
                            # 🚫 ОТКЛЮЧЕНЫ ЛИЧНЫЕ СООБЩЕНИЯ: Отправляем только в основной чат
                            group.message_id = await self._send_group_message(group)
                            if group.message_id:
                                logger.info(f"✅ Впервые отправлено сообщение для группы {symbol} (новый Twitter с анонсом)")
                            else:
                                logger.warning(f"🚫 Сообщение для группы {symbol} НЕ отправлено - недостаточно информации о Twitter")
                
                # 🔍 ИСПРАВЛЕНИЕ: Ищем анонс если его нет в существующей группе
                if group.main_twitter and not group.official_announcement:
                    logger.info(f"🐛🔍 WORMSTER НАШЁЛ ГРУППУ {symbol} БЕЗ АНОНСА! Копаем глубже в @{group.main_twitter}...")
                    oldest_mention = await self._find_oldest_announcement(group.main_twitter, symbol)
                    if oldest_mention:
                        group.official_announcement = oldest_mention
                        logger.info(f"📅 Найден анонс для существующей группы {symbol} от {oldest_mention['date']}")
                        
                        # 🚀 НОВАЯ ЛОГИКА: Если анонс найден впервые, отправляем сообщение
                        if not group.message_id:
                            # 🚫 ОТКЛЮЧЕНЫ ЛИЧНЫЕ СООБЩЕНИЯ: Отправляем только в основной чат
                            group.message_id = await self._send_group_message(group)
                            if group.message_id:
                                logger.info(f"✅ Впервые отправлено сообщение для группы {symbol} (найден анонс)")
                            else:
                                logger.warning(f"🚫 Сообщение для группы {symbol} НЕ отправлено - недостаточно информации о Twitter")
                
                # 🔧 ИСПРАВЛЕНИЕ: Всегда пересоздаем таблицу с полным списком токенов
                logger.info(f"🔄 Пересоздаем таблицу для группы {symbol} с {len(group.tokens)} токенами...")
                # Обновляем сообщение только если есть анонс и message_id
                if group.official_announcement and group.message_id:
                    self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                else:
                    # Создаем только таблицу без обновления сообщения
                    if group.main_twitter:
                        sheets_manager.add_tokens_batch(group_key, group.tokens, group.main_twitter)
                        if group.is_global_search_group:
                            logger.info(f"📊 Таблица для группы {symbol} обновлена БЕЗ уведомления в личный чат (нет анонса)")
                        else:
                            logger.info(f"📊 Таблица для группы {symbol} обновлена БЕЗ уведомления (нет анонса)")
                
                logger.info(f"🐛✅ WORMSTER ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен {symbol} добавлен в группу (всего токенов: {len(group.tokens)}) 🎯")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления токена в группу: {e}")
            return False
    
    def _enrich_token_with_date(self, token_data: Dict) -> Dict:
        """Обогащает данные токена датой создания и временем обнаружения из БД"""
        try:
            db_manager = get_db_manager()
            session = db_manager.Session()
            
            # Получаем токен из основной таблицы и таблицы дубликатов
            from database import Token
            main_token = session.query(Token).filter_by(mint=token_data.get('id')).first()
            dup_token = session.query(DuplicateToken).filter_by(mint=token_data.get('id')).first()
            
            session.close()
            
            # Создаем копию token_data для изменения
            enriched_token = token_data.copy()
            
            # Если нашли токен в БД и у него есть дата создания
            if main_token and main_token.created_at:
                # Преобразуем в ISO формат с Z суффиксом
                created_at_str = main_token.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                # Обогащаем firstPool данными
                if 'firstPool' not in enriched_token:
                    enriched_token['firstPool'] = {}
                
                enriched_token['firstPool']['createdAt'] = created_at_str
                
                logger.debug(f"✅ Токен {token_data.get('id', '')[:8]}... обогащен датой создания: {created_at_str}")
            else:
                logger.debug(f"⚠️ Дата создания токена {token_data.get('id', '')[:8]}... не найдена в БД")
            
            # Обогащаем временем обнаружения из таблицы дубликатов
            if dup_token and dup_token.first_seen:
                # Преобразуем в ISO формат с Z суффиксом
                first_seen_str = dup_token.first_seen.strftime('%Y-%m-%dT%H:%M:%SZ')
                enriched_token['first_seen'] = first_seen_str
                
                logger.debug(f"✅ Токен {token_data.get('id', '')[:8]}... обогащен временем обнаружения: {first_seen_str}")
            else:
                logger.debug(f"⚠️ Время обнаружения токена {token_data.get('id', '')[:8]}... не найдено в БД")
            
            return enriched_token
            
        except Exception as e:
            logger.error(f"❌ Ошибка обогащения токена датой: {e}")
            return token_data  # Возвращаем оригинальные данные в случае ошибки

    def _load_tokens_from_db(self, symbol: str) -> List[Dict]:
        """Загружает ВСЕ токены символа из основной таблицы tokens с временем обнаружения"""
        try:
            db_manager = get_db_manager()
            session = db_manager.Session()
            
            # ИСПРАВЛЕНИЕ: Загружаем ВСЕ токены из основной таблицы tokens с JOIN к duplicate_tokens для времени обнаружения
            tokens = session.query(Token, DuplicateToken).outerjoin(
                DuplicateToken, Token.mint == DuplicateToken.mint
            ).filter(
                Token.symbol == symbol.upper()  # Символы в основной таблице в верхнем регистре
            ).order_by(Token.created_at.desc()).all()  # Сортируем по дате создания
            
            session.close()
            
            # Конвертируем в словари в формате Jupiter API
            token_list = []
            for token, dup_token in tokens:
                # Форматируем дату создания для Jupiter API формата
                created_at_str = None
                if token.created_at:
                    # Преобразуем в ISO формат с Z суффиксом
                    created_at_str = token.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                # Форматируем время обнаружения
                first_seen_str = None
                if dup_token and dup_token.first_seen:
                    first_seen_str = dup_token.first_seen.strftime('%Y-%m-%dT%H:%M:%SZ')
                
                token_dict = {
                    'id': token.mint,
                    'name': token.name or 'Unknown',
                    'symbol': token.symbol,
                    'icon': getattr(token, 'icon', None),
                    'twitter': getattr(token, 'twitter', None),
                    'telegram': getattr(token, 'telegram', None),
                    'website': getattr(token, 'website', None),
                    'decimals': getattr(token, 'decimals', 6),
                    'firstPool': {
                        'createdAt': created_at_str
                    },
                    'first_seen': first_seen_str  # Добавляем время обнаружения
                }
                token_list.append(token_dict)
            
            logger.info(f"📊 Загружено {len(token_list)} токенов {symbol} из ОСНОВНОЙ таблицы tokens с временем обнаружения")
            return token_list
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки токенов из БД: {e}")
            return []
    
    async def _send_group_message(self, group: 'GroupData') -> Optional[int]:
        """Отправляет новое сообщение группы в Telegram через очередь"""
        try:
            message_text = await self._format_group_message(group)
            
            # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Если сообщение не сформировано (нет информации о Twitter) - НЕ отправляем
            if not message_text:
                logger.warning(f"🚫 Сообщение для группы {group.symbol} НЕ отправлено - недостаточно информации о Twitter")
                return None
            
            inline_keyboard = self._create_group_keyboard(group)
            
            payload = {
                "chat_id": self.target_chat_id,
                "message_thread_id": self.message_thread_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }
            
            # Создаем Future для получения результата
            future = asyncio.Future()
            
            def callback(success: bool, result):
                if success:
                    message_id = result['result']['message_id']
                    logger.info(f"✅ Сообщение группы {group.symbol} отправлено через очередь (ID: {message_id})")
                    future.set_result(message_id)
                else:
                    logger.error(f"❌ Ошибка отправки сообщения группы через очередь: {result}")
                    future.set_result(None)
            
            # Добавляем в очередь
            self.telegram_queue.send_message(payload, callback)
            
            # Ждем результат с таймаутом
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут отправки сообщения группы {group.symbol}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки группового сообщения: {e}")
            return None
    
    async def _send_private_group_message(self, group: 'GroupData') -> Optional[int]:
        """Отправляет сообщение группы в личный чат пользователя (для токенов без Twitter)"""
        try:
            message_text = await self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)
            
            payload = {
                "chat_id": self.private_chat_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }
            
            # Создаем Future для получения результата
            future = asyncio.Future()
            
            def callback(success: bool, result):
                if success:
                    message_id = result['result']['message_id']
                    logger.info(f"✅ Сообщение группы {group.symbol} отправлено в ЛИЧНЫЙ ЧАТ через очередь (ID: {message_id})")
                    future.set_result(message_id)
                else:
                    logger.error(f"❌ Ошибка отправки сообщения группы в личный чат через очередь: {result}")
                    future.set_result(None)
            
            # Добавляем в очередь
            self.telegram_queue.send_message(payload, callback)
            
            # Ждем результат с таймаутом
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут отправки сообщения группы {group.symbol} в личный чат")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения в личный чат: {e}")
            return None
    
    async def _update_private_group_message(self, group: 'GroupData') -> bool:
        """Обновляет существующее сообщение группы в личном чате"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления в личном чате")
                return False

            message_text = await self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)

            payload = {
                "chat_id": self.private_chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }

            # Создаем Future для получения результата
            future = asyncio.Future()

            def callback(success: bool, result):
                if success:
                    logger.info(f"✅ Сообщение группы {group.symbol} обновлено в ЛИЧНОМ ЧАТЕ через очередь")
                    future.set_result(True)
                else:
                    logger.error(f"❌ Ошибка обновления сообщения группы в личном чате через очередь: {result}")
                    future.set_result(False)

            # Добавляем в очередь
            self.telegram_queue.edit_message(payload, callback)

            # Ждем результат с таймаутом
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут обновления сообщения группы {group.symbol} в личном чате")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщения в личном чате: {e}")
            return False
    
    async def _update_group_message(self, group: 'GroupData') -> bool:
        """Обновляет существующее сообщение группы через очередь"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False

            message_text = await self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)

            payload = {
                "chat_id": self.target_chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }

            # Создаем Future для получения результата
            future = asyncio.Future()

            def callback(success: bool, result):
                if success:
                    logger.info(f"✅ Сообщение группы {group.symbol} обновлено через очередь")
                    future.set_result(True)
                else:
                    logger.error(f"❌ Ошибка обновления сообщения группы через очередь: {result}")
                    future.set_result(False)

            # Добавляем в очередь
            self.telegram_queue.edit_message(payload, callback)

            # Ждем результат с таймаутом
            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут обновления сообщения группы {group.symbol}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления группового сообщения: {e}")
            return False
    
    def _parse_jupiter_date(self, date_string: str) -> str:
        """Парсинг даты из Jupiter API формата '2025-07-05T16:03:59Z' в читаемый формат"""
        if not date_string:
            return "Неизвестно"
            
        try:
            # Улучшенный парсинг UTC даты с Z-суффиксом
            if date_string.endswith('Z'):
                # Заменяем Z на +00:00 для явного указания UTC
                date_string = date_string.replace('Z', '+00:00')
            
            # Парсим дату в формате ISO с таймзоной
            created_date = datetime.fromisoformat(date_string)
            
            # Возвращаем в читаемом формате
            return created_date.strftime('%d.%m.%Y %H:%M')
            
        except Exception as e:
            logger.debug(f"⚠️ Ошибка парсинга Jupiter даты '{date_string}': {e}")
            return str(date_string)  # Возвращаем оригинальную строку

    async def _format_group_message(self, group: 'GroupData') -> Optional[str]:
        """Форматирует простое сообщение как обычный анонс токена. Возвращает None если информация недоступна"""
        try:
            # ПРОСТОЙ ЗАГОЛОВОК
            message = f"🐛💰 <b>НОВЫЙ ЗАПУСК МОНЕТЫ: ${group.symbol.upper()}!</b>\n\n"
            
            # Детальная информация о главном Twitter аккаунте
            if group.main_twitter:
                # Получаем детальную информацию о главном Twitter
                main_twitter_info = await self._format_twitter_profile_info(group.main_twitter, is_main=True)
                
                # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Если информация о главном Twitter недоступна - НЕ отправляем уведомление
                if not main_twitter_info:
                    logger.warning(f"🚫 Информация о главном Twitter @{group.main_twitter} недоступна - НЕ отправляем уведомление для {group.symbol}")
                    return None
                
                message += main_twitter_info
                
                # Официальный анонс токена (самый старый твит)
                if group.official_announcement:
                    message += f"📢 <b>ОФИЦИАЛЬНЫЙ АНОНС:</b>\n"
                    message += f"📅 <b>Дата:</b> {group.official_announcement['date']}\n"
                    # Обрезаем текст если слишком длинный
                    announcement_text = group.official_announcement['text']
                    if len(announcement_text) > 150:
                        announcement_text = announcement_text[:150] + "..."
                    # Экранируем HTML символы в тексте анонса
                    import html
                    announcement_text = html.escape(announcement_text)
                    message += f"<blockquote>{announcement_text}</blockquote>\n"
                
                # Добавляем список дополнительных Twitter аккаунтов с краткой информацией
                additional_accounts = await self._get_additional_twitter_accounts(group)
                if additional_accounts:
                    message += f"\n🔗 <b>ДОПОЛНИТЕЛЬНЫЕ TWITTER АККАУНТЫ:</b>\n"
                    
                    # Ограничиваем количество дополнительных аккаунтов
                    max_additional = 3
                    for i, account in enumerate(additional_accounts[:max_additional]):
                        additional_info = await self._format_twitter_profile_info(account, is_main=False)
                        if additional_info:  # Добавляем только если информация доступна
                            message += f"• {additional_info}\n"
                    
                    if len(additional_accounts) > max_additional:
                        remaining = len(additional_accounts) - max_additional
                        message += f"• и еще {remaining} аккаунт(ов)\n"
                    
                    message += "\n"
                else:
                    message += "\n"
            else:
                message += f"🐦 <b>TWITTER ОСНОВАТЕЛЯ:</b> Поиск...\n\n"
            
            # СТАТУС ОХОТЫ
            if group.official_contract:
                message += f"✅ <b>ОФИЦИАЛЬНЫЙ КОНТРАКТ НАЙДЕН!</b>\n"
                message += f"💎 <b>Адрес:</b> <code>{group.official_contract['address']}</code>\n"
                message += f"📅 <b>Дата:</b> {group.official_contract['date']}\n\n"
            else:
                message += f"🔍 <b>WORMSTER ПРОДОЛЖАЕТ ОХОТУ...</b>\n"
                message += f"👀 Официальный контракт всё ещё не вышел. Время охоты!\n\n"
            
            # МЕТКА ВРЕМЕНИ
            utc_time = datetime.utcnow()
            message += f"🕐 <b>Wormster обновил данные:</b> {utc_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
            message += f"🎯 <b>ПОМНИ:</b> Ранние птицы ловят лучшие иксы! Не проспи альфу! 💰🐛"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования сообщения группы: {e}")
            return None
    
    def _create_group_keyboard(self, group: 'GroupData') -> Dict:
        """Создает inline клавиатуру для группы с кнопкой Google Sheets"""
        try:
            buttons = []
            
            # 📊 КНОПКА GOOGLE SHEETS - всегда добавляем когда URL готов
            if group.sheet_url and group.sheet_url.strip():
                buttons.append([{
                    "text": "📊 Смотреть в Google Sheets",
                    "url": group.sheet_url
                }])
                logger.debug(f"✅ Кнопка Google Sheets добавлена для группы {group.symbol}: {group.sheet_url}")
            else:
                logger.debug(f"📊 Кнопка Google Sheets пока не готова для группы {group.symbol} (таблица создается)")
            
            # Кнопка "Окей" появляется только когда найден официальный контракт
            if group.official_contract:
                buttons.append([{
                    "text": "✅ Окей",
                    "callback_data": f"delete_group:{group.group_key}"
                }])
            
            return {"inline_keyboard": buttons}
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры группы: {e}")
            return {"inline_keyboard": []}
    
    def _has_links(self, token_data: Dict) -> bool:
        """Проверяет наличие ссылок у токена"""
        link_fields = ['twitter', 'telegram', 'website']
        return any(token_data.get(field) for field in link_fields)
    
    async def _get_additional_twitter_accounts(self, group: 'GroupData') -> List[str]:
        """Получает список дополнительных Twitter аккаунтов, которые упоминают символ токена (исключая главный)"""
        try:
            additional_accounts = set()
            
            # Собираем все Twitter аккаунты из токенов в группе
            for token in group.tokens:
                accounts = self.extract_twitter_accounts(token)
                for account in accounts:
                    # Исключаем главный Twitter аккаунт
                    if account and account != group.main_twitter:
                        additional_accounts.add(account)
            
            # Фильтруем только те аккаунты, которые упоминают символ токена
            filtered_accounts = []
            for account in additional_accounts:
                try:
                    # Проверяем, упоминает ли аккаунт символ токена
                    mentions_symbol = await self._check_symbol_mentions_in_twitter(account, group.symbol)
                    if mentions_symbol:
                        filtered_accounts.append(account)
                        logger.debug(f"✅ Аккаунт @{account} упоминает {group.symbol} - добавляем в список")
                    else:
                        logger.debug(f"❌ Аккаунт @{account} НЕ упоминает {group.symbol} - исключаем")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка проверки упоминания {group.symbol} в @{account}: {e}")
                    # В случае ошибки НЕ добавляем аккаунт (безопасный подход)
            
            # Возвращаем отсортированный список
            return sorted(filtered_accounts)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения дополнительных Twitter аккаунтов: {e}")
            return []
    
    def _get_additional_twitter_accounts_sync(self, group: 'GroupData') -> List[str]:
        """Получает список дополнительных Twitter аккаунтов (синхронная версия - без проверки упоминаний)"""
        try:
            additional_accounts = set()
            
            # Собираем все Twitter аккаунты из токенов в группе
            for token in group.tokens:
                accounts = self.extract_twitter_accounts(token)
                for account in accounts:
                    # Исключаем главный Twitter аккаунт
                    if account and account != group.main_twitter:
                        additional_accounts.add(account)
            
            # Возвращаем отсортированный список без проверки упоминаний
            return sorted(list(additional_accounts))
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения дополнительных Twitter аккаунтов (синхронно): {e}")
            return []
    
    def _create_sheet_and_update_message_async(self, group_key: str, tokens: List[Dict], main_twitter: str):
        """🔥 СУПЕР БЫСТРОЕ асинхронное создание Google Sheets таблицы батчем с приоритизацией"""
        def create_sheet_task():
            try:
                logger.info(f"🔥 Создаем Google Sheets таблицу для группы {group_key} БАТЧЕМ ({len(tokens)} токенов)...")
                logger.info(f"🔍 DEBUG: main_twitter = {main_twitter}, group_key = {group_key}")
                
                # 🔥 СУПЕР БЫСТРО: Добавляем ВСЕ токены одним батчем
                if tokens:
                    logger.info(f"📋 DEBUG: Вызываем add_tokens_batch для {group_key} с {len(tokens)} токенами")
                    table_created = sheets_manager.add_tokens_batch(group_key, tokens, main_twitter)
                    logger.info(f"📊 DEBUG: add_tokens_batch для {group_key} вернул: {table_created}")
                    
                    if table_created:
                        # Получаем URL таблицы
                        logger.info(f"🔗 DEBUG: Получаем URL таблицы для {group_key}")
                        sheet_url = sheets_manager.get_sheet_url(group_key)
                        logger.info(f"🔗 DEBUG: get_sheet_url для {group_key} вернул: {sheet_url}")
                        
                        if sheet_url and group_key in self.groups:
                            # Обновляем группу
                            group = self.groups[group_key]
                            group.sheet_url = sheet_url
                            
                            logger.info(f"🔥 БАТЧЕВАЯ таблица создана для {group_key}, URL: {sheet_url}")
                            
                            # Обновляем сообщение с кнопкой асинхронно (из фонового потока)
                            if group.message_id:
                                try:
                                    logger.info(f"📱 DEBUG: Обновляем сообщение {group.message_id} для {group_key}")
                                    # Создаем задачу для async обновления сообщения с полной информацией о Twitter
                                    self._schedule_async_message_update(group)
                                except Exception as e:
                                    logger.error(f"❌ Ошибка планирования обновления сообщения: {e}")
                            else:
                                logger.debug(f"📊 Сообщение для группы {group_key} не отправлено (тест режим)")
                            
                            logger.info(f"✅ БАТЧЕВАЯ обработка таблицы для группы {group_key} завершена за 1 запрос!")
                        else:
                            if not sheet_url:
                                logger.error(f"❌ get_sheet_url вернул пустой URL для {group_key}")
                            if group_key not in self.groups:
                                logger.error(f"❌ Группа {group_key} НЕ найдена в self.groups!")
                                logger.info(f"🔍 DEBUG: Доступные группы: {list(self.groups.keys())}")
                    else:
                        logger.error(f"❌ add_tokens_batch вернул False для группы {group_key}")
                else:
                    logger.error(f"❌ Нет токенов для создания таблицы {group_key}")
                        
            except Exception as e:
                logger.error(f"❌ Ошибка создания таблицы в фоне для {group_key}: {e}")
                import traceback
                logger.error(f"❌ Трассировка: {traceback.format_exc()}")
        
        # 🔥 ОПРЕДЕЛЯЕМ ПРИОРИТЕТ: Высокий для отправленных уведомлений, обычный для тестовых
        group = self.groups.get(group_key)
        if group and group.message_id:
            # Высокий приоритет для отправленных уведомлений
            priority = 0
            priority_msg = "🔥 ВЫСОКИЙ (отправленное уведомление)"
        else:
            # Обычный приоритет для тестовых/необработанных групп
            priority = 1
            priority_msg = "⏳ ОБЫЧНЫЙ (тестовая группа)"
        
        # Запускаем в фоновом потоке Google Sheets с приоритетом
        logger.info(f"📤 DEBUG: Добавляем задачу create_sheet_task для {group_key} в очередь с приоритетом {priority_msg}")
        sheets_manager._queue_task(create_sheet_task, priority=priority)
    
    def _format_group_message_sync(self, group: 'GroupData') -> str:
        """Синхронно форматирует простое сообщение как обычный анонс токена (для фонового потока)"""
        try:
            # ПРОСТОЙ ЗАГОЛОВОК
            message = f"🐛💰 <b>НОВЫЙ ЗАПУСК МОНЕТЫ: ${group.symbol.upper()}!</b>\n\n"
            
            # Информация о главном Twitter аккаунте
            if group.main_twitter:
                message += f"🐦 <b>TWITTER ОСНОВАТЕЛЯ:</b> @{group.main_twitter}\n"
                
                # Официальный анонс токена (самый старый твит)
                if group.official_announcement:
                    message += f"📢 <b>ОФИЦИАЛЬНЫЙ АНОНС:</b>\n"
                    message += f"📅 <b>Дата:</b> {group.official_announcement['date']}\n"
                    # Обрезаем текст если слишком длинный
                    announcement_text = group.official_announcement['text']
                    if len(announcement_text) > 150:
                        announcement_text = announcement_text[:150] + "..."
                    # Экранируем HTML символы в тексте анонса
                    import html
                    announcement_text = html.escape(announcement_text)
                    message += f"<blockquote>{announcement_text}</blockquote>\n"
                    
                # Добавляем список дополнительных Twitter аккаунтов (упрощенная синхронная версия)
                additional_accounts = self._get_additional_twitter_accounts_sync(group)
                if additional_accounts:
                    if len(additional_accounts) <= 3:
                        accounts_str = ", ".join([f"@{account}" for account in additional_accounts])
                        message += f"🔗 <b>ДОПОЛНИТЕЛЬНЫЕ TWITTER:</b> {accounts_str}\n\n"
                    else:
                        first_three = ", ".join([f"@{account}" for account in additional_accounts[:3]])
                        remaining = len(additional_accounts) - 3
                        message += f"🔗 <b>ДОПОЛНИТЕЛЬНЫЕ TWITTER:</b> {first_three} и еще {remaining}\n\n"
                else:
                    message += "\n"
            else:
                message += f"🐦 <b>TWITTER ОСНОВАТЕЛЯ:</b> Поиск...\n\n"
            
            # СТАТУС ОХОТЫ
            if group.official_contract:
                message += f"✅ <b>ОФИЦИАЛЬНЫЙ КОНТРАКТ НАЙДЕН!</b>\n"
                message += f"💎 <b>Адрес:</b> <code>{group.official_contract['address']}</code>\n"
                message += f"📅 <b>Дата:</b> {group.official_contract['date']}\n\n"
            else:
                message += f"🔍 <b>WORMSTER ПРОДОЛЖАЕТ ОХОТУ...</b>\n"
                message += f"👀 Официальный контракт всё ещё не вышел. Время охоты!\n\n"
            
            # МЕТКА ВРЕМЕНИ
            utc_time = datetime.utcnow()
            message += f"🕐 <b>Wormster обновил данные:</b> {utc_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
            message += f"🎯 <b>ПОМНИ:</b> Ранние птицы ловят лучшие иксы! Не проспи альфу! 💰🐛"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка синхронного форматирования сообщения группы: {e}")
            return f"❌ Ошибка форматирования группы {group.symbol}"

    def _schedule_async_message_update(self, group: 'GroupData') -> bool:
        """Планирует async обновление сообщения с полной информацией о Twitter (для фонового потока)"""
        try:
            import asyncio
            import threading
            
            def run_async_update():
                """Запускает async обновление в отдельном потоке"""
                try:
                    # Создаем новый event loop для этого потока
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Выполняем async обновление
                    result = loop.run_until_complete(self._update_message_with_sheet_button(group))
                    
                    if result:
                        logger.info(f"✅ Async обновление сообщения {group.symbol} с детальной Twitter информацией завершено")
                    else:
                        logger.error(f"❌ Async обновление сообщения {group.symbol} не удалось")
                    
                    loop.close()
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка async обновления сообщения {group.symbol}: {e}")
            
            # Запускаем в отдельном потоке
            update_thread = threading.Thread(target=run_async_update, daemon=True)
            update_thread.start()
            
            logger.info(f"📤 Async обновление сообщения группы {group.symbol} запланировано")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка планирования async обновления сообщения: {e}")
            return False

    def _update_message_with_sheet_button_sync(self, group: 'GroupData') -> bool:
        """Синхронно обновляет сообщение Telegram с кнопкой Google Sheets (для фонового потока)"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False

            # Синхронное форматирование сообщения (без await)
            message_text = self._format_group_message_sync(group)
            inline_keyboard = self._create_group_keyboard(group)

            # 🌍 ПРОВЕРКА: Если группа найдена через глобальный поиск - используем личный чат
            chat_id = self.private_chat_id if group.is_global_search_group else self.target_chat_id
            
            payload = {
                "chat_id": chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }

            def callback(success: bool, result):
                if success:
                    logger.info(f"✅ Сообщение группы {group.symbol} обновлено с кнопкой Google Sheets через очередь")
                else:
                    logger.error(f"❌ Ошибка обновления сообщения с кнопкой через очередь: {result}")

            # Добавляем в очередь
            self.telegram_queue.edit_message(payload, callback)
            
            logger.info(f"📤 Обновление сообщения группы {group.symbol} с кнопкой добавлено в очередь")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка синхронного обновления сообщения с кнопкой: {e}")
            return False

    async def _update_message_with_sheet_button(self, group: 'GroupData') -> bool:
        """Асинхронно обновляет сообщение Telegram с кнопкой Google Sheets через очередь"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False

            message_text = await self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)

            # 🌍 ПРОВЕРКА: Если группа найдена через глобальный поиск - используем личный чат
            chat_id = self.private_chat_id if group.is_global_search_group else self.target_chat_id

            payload = {
                "chat_id": chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }

            # Создаем переменную для результата
            result_container = {'success': False}

            def callback(success: bool, result):
                if success:
                    logger.info(f"✅ Сообщение группы {group.symbol} обновлено с кнопкой Google Sheets через очередь")
                    result_container['success'] = True
                else:
                    logger.error(f"❌ Ошибка обновления сообщения с кнопкой через очередь: {result}")
                    result_container['success'] = False

            # Добавляем в очередь
            self.telegram_queue.edit_message(payload, callback)
            
            # Поскольку это синхронный метод, возвращаем True (задача добавлена в очередь)
            logger.info(f"📤 Обновление сообщения группы {group.symbol} с кнопкой добавлено в очередь")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщения с кнопкой: {e}")
            return False
    
    async def check_official_contract(self, group_key: str) -> bool:
        """Проверяет наличие официального контракта в Twitter главного аккаунта"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            if not group.main_twitter:
                return False
            
            # Здесь будет логика поиска контракта в Twitter
            # Пока что заглушка - вернет False
            # TODO: Интегрировать с системой поиска в Twitter из pump_bot.py
            
            logger.debug(f"🔍 Проверка официального контракта для @{group.main_twitter} - пока не реализовано")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки официального контракта: {e}")
            return False
    
    async def mark_official_contract_found(self, group_key: str, contract_address: str, found_date: str = None) -> bool:
        """Отмечает что официальный контракт найден"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            
            # Сохраняем информацию об официальном контракте
            group.official_contract = {
                'address': contract_address,
                'date': found_date or datetime.now().strftime('%d.%m.%Y %H:%M'),
                'found_at': datetime.now()
            }
            
            # Обновляем Google Sheets
            if group.main_twitter:
                sheets_manager.check_official_contract_in_twitter(
                    group_key, group.main_twitter, contract_address
                )
            
            # Обновляем Telegram сообщение
            await self._update_group_message(group)
            
            logger.info(f"✅ Официальный контракт {contract_address[:8]}... отмечен для группы {group.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отметки официального контракта: {e}")
            return False
    
    async def delete_group(self, group_key: str) -> bool:
        """Удаляет группу дубликатов (удаляет сообщение в Telegram)"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            
            # Удаляем сообщение в Telegram через очередь
            if group.message_id:
                # 🌍 ПРОВЕРКА: Если группа найдена через глобальный поиск - удаляем из личного чата
                chat_id = self.private_chat_id if group.is_global_search_group else self.target_chat_id
                
                payload = {
                    "chat_id": chat_id,
                    "message_id": group.message_id
                }
                
                # Создаем Future для получения результата
                future = asyncio.Future()
                
                def callback(success: bool, result):
                    if success:
                        logger.info(f"✅ Сообщение группы {group.symbol} удалено через очередь")
                        future.set_result(True)
                    else:
                        logger.warning(f"⚠️ Не удалось удалить сообщение группы {group.symbol} через очередь: {result}")
                        future.set_result(False)
                
                # Добавляем в очередь
                self.telegram_queue.delete_message(payload, callback)
                
                # Ждем результат с таймаутом
                try:
                    await asyncio.wait_for(future, timeout=30.0)
                except asyncio.TimeoutError:
                    logger.error(f"⏰ Таймаут удаления сообщения группы {group.symbol}")
            
            # Удаляем группу из памяти
            del self.groups[group_key]
            
            logger.info(f"🐛💥 WORMSTER УНИЧТОЖИЛ ГРУППУ {group.symbol}! Охота завершена! 🎯")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления группы: {e}")
            return False
    
    def get_group_stats(self) -> Dict:
        """Возвращает статистику по всем группам"""
        try:
            total_groups = len(self.groups)
            total_tokens = sum(len(group.tokens) for group in self.groups.values())
            groups_with_official = sum(1 for group in self.groups.values() if group.official_contract)
            
            return {
                'total_groups': total_groups,
                'total_tokens': total_tokens,
                'groups_with_official_contracts': groups_with_official,
                'active_groups': [
                    {
                        'symbol': group.symbol,
                        'tokens_count': len(group.tokens),
                        'main_twitter': group.main_twitter,
                        'has_official': bool(group.official_contract),
                        'sheet_url': group.sheet_url
                    }
                    for group in self.groups.values()
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики групп: {e}")
            return {}
    
    async def _handle_nitter_block(self, session, proxy, cookie, headers, url, context_name, html_content):
        """🔄 Правильная функция для автоматического восстановления при блокировке Nitter с Anubis challenge"""
        try:
            logger.warning(f"🚫 Nitter заблокирован для {context_name} - пытаемся восстановить")
            
            # СНАЧАЛА пытаемся решить Anubis challenge с текущими прокси (правильная логика!)
            logger.warning(f"🤖 Обнаружен Anubis challenge для {context_name}, пытаемся решить автоматически...")
            
            try:
                # Создаем простой объект для переключения доменов
                class SimpleDomainRotator:
                    def get_next_domain(self):
                        return get_next_nitter_domain()
                
                domain_rotator = SimpleDomainRotator()
                anubis_cookies = await handle_anubis_challenge_for_session(session, url, html_content, nitter_domain_rotator=domain_rotator)
                
                if anubis_cookies:
                    logger.info(f"✅ Challenge решен для {context_name}, повторяем запрос с новыми куки")
                    
                    # Обновляем куки в заголовках
                    updated_cookies = update_cookies_in_string(headers.get('Cookie', ''), anubis_cookies)
                    headers['Cookie'] = updated_cookies
                    
                    # Настройка запроса с текущим прокси
                    request_kwargs = {}
                    if proxy:
                        request_kwargs['proxy'] = proxy
                    
                    # Повторяем запрос с решенным challenge
                    # Применяем глобальный rate limiting
                    await self._apply_global_rate_limit()
                    
                    # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ANUBIS
                    anubis_response = await network_retry_wrapper(session, 'get', url, 
                                                                headers=headers, timeout=15, **request_kwargs)
                    if anubis_response.status == 200:
                        anubis_html = await anubis_response.text()
                        anubis_soup = BeautifulSoup(anubis_html, 'html.parser')
                        
                        # Проверяем что challenge больше нет
                        anubis_title = anubis_soup.find('title')
                        anubis_has_challenge_text = anubis_title and 'Making sure you\'re not a bot!' in anubis_title.get_text()
                        anubis_has_anubis_script = 'id="anubis_challenge"' in anubis_html
                        
                        if anubis_has_challenge_text or anubis_has_anubis_script:
                            logger.warning(f"⚠️ Challenge не решен с текущим прокси для {context_name}, пробуем новый прокси")
                            # Fallback: пробуем с новым прокси
                            return await self._fallback_with_new_proxy(session, proxy, cookie, headers, url, context_name)
                        
                        logger.info(f"🎉 {context_name} доступен после решения challenge")
                        return anubis_soup
                    elif anubis_response.status == 429:
                        # При 429 ошибке переключаемся на следующий домен, а не прокси
                        logger.warning(f"🔥 HTTP 429 после решения challenge для {context_name} - переключаемся на следующий домен")
                        return await self._fallback_with_new_domain(session, proxy, cookie, headers, url, context_name)
                    else:
                        logger.error(f"❌ Ошибка после решения challenge для {context_name}: HTTP {anubis_response.status}")
                        # Fallback: пробуем с новым прокси
                        return await self._fallback_with_new_proxy(session, proxy, cookie, headers, url, context_name)
                else:
                    logger.warning(f"❌ Не удалось решить challenge с текущим прокси для {context_name}, пробуем новый прокси")
                    # Fallback: пробуем с новым прокси
                    return await self._fallback_with_new_proxy(session, proxy, cookie, headers, url, context_name)
                    
            except Exception as anubis_error:
                logger.error(f"❌ Ошибка решения challenge для {context_name}: {anubis_error}")
                # Fallback: пробуем с новым прокси
                return await self._fallback_with_new_proxy(session, proxy, cookie, headers, url, context_name)
                
        except Exception as e:
            error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
            logger.error(f"❌ Ошибка автоматического восстановления для {context_name}: {error_msg}")
            return None
    
    async def _fallback_with_new_domain(self, session, proxy, cookie, headers, url, context_name):
        """Fallback функция: пробуем с новым доменом Nitter при 429 ошибке"""
        try:
            logger.info(f"🌐 Fallback: переключаемся на новый домен Nitter для {context_name}")
            
            # Получаем новый домен из ротации
            from nitter_domain_rotator import get_next_nitter_domain
            new_domain = get_next_nitter_domain()
            
            if not new_domain:
                logger.error(f"❌ Не удалось получить новый домен для {context_name}")
                return None
            
            # Формируем новый URL с новым доменом
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            new_base_url = format_nitter_url(new_domain)
            new_url = f"{new_base_url}{parsed_url.path}"
            if parsed_url.query:
                new_url += f"?{parsed_url.query}"
            
            logger.info(f"🔄 Повторяем запрос с новым доменом: {new_domain}")
            
            # Настройка запроса с текущим прокси (НЕ меняем прокси!)
            request_kwargs = {}
            if proxy:
                request_kwargs['proxy'] = proxy
            
            # Повторяем запрос с новым доменом
            # Применяем глобальный rate limiting
            await self._apply_global_rate_limit()
            
            # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС С НОВЫМ ДОМЕНОМ (уменьшенный timeout)
            retry_response = await network_retry_wrapper(session, 'get', new_url, 
                                                    headers=headers, timeout=15, **request_kwargs)
            if retry_response.status == 200:
                retry_html = await retry_response.text()
                retry_soup = BeautifulSoup(retry_html, 'html.parser')
                
                # Проверяем на блокировку
                retry_title = retry_soup.find('title')
                has_challenge_text = retry_title and 'Making sure you\'re not a bot!' in retry_title.get_text()
                has_anubis_script = 'id="anubis_challenge"' in retry_html
                
                if has_challenge_text or has_anubis_script:
                    logger.warning(f"🤖 Новый домен тоже показывает challenge для {context_name}, решаем...")
                    
                    # Решаем challenge с новым доменом
                    try:
                        # Создаем простой объект для переключения доменов
                        class SimpleDomainRotator:
                            def get_next_domain(self):
                                return get_next_nitter_domain()
                        
                        domain_rotator = SimpleDomainRotator()
                        anubis_cookies = await handle_anubis_challenge_for_session(session, new_url, retry_html, nitter_domain_rotator=domain_rotator)
                        
                        if anubis_cookies:
                            logger.info(f"✅ Challenge решен с новым доменом для {context_name}")
                            
                            # Обновляем куки в заголовках
                            updated_cookies = update_cookies_in_string(headers.get('Cookie', ''), anubis_cookies)
                            headers['Cookie'] = updated_cookies
                            
                            # Повторяем запрос с решенным challenge
                            # Применяем глобальный rate limiting
                            await self._apply_global_rate_limit()
                            
                            # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ФИНАЛЬНОЙ ПОПЫТКИ
                            final_response = await network_retry_wrapper(session, 'get', new_url, 
                                                                    headers=headers, timeout=15, **request_kwargs)
                            if final_response.status == 200:
                                final_html = await final_response.text()
                                final_soup = BeautifulSoup(final_html, 'html.parser')
                                
                                # Финальная проверка
                                final_title = final_soup.find('title')
                                final_has_challenge = final_title and 'Making sure you\'re not a bot!' in final_title.get_text()
                                final_has_anubis = 'id="anubis_challenge"' in final_html
                                
                                if final_has_challenge or final_has_anubis:
                                    logger.error(f"❌ Challenge всё ещё не решен с новым доменом для {context_name}")
                                    return None
                                
                                logger.info(f"🎉 {context_name} доступен после смены домена и решения challenge")
                                return final_soup
                            elif final_response.status == 429:
                                logger.warning(f"🔥 HTTP 429 даже с новым доменом для {context_name} - пробуем ещё один домен")
                                # Рекурсивно пробуем следующий домен
                                return await self._fallback_with_new_domain(session, proxy, cookie, headers, url, context_name)
                            else:
                                logger.error(f"❌ Ошибка финального запроса с новым доменом для {context_name}: HTTP {final_response.status}")
                                return None
                        else:
                            logger.error(f"❌ Не удалось решить challenge с новым доменом для {context_name}")
                            return None
                            
                    except Exception as anubis_error:
                        logger.error(f"❌ Ошибка решения challenge с новым доменом для {context_name}: {anubis_error}")
                        return None
                else:
                    logger.info(f"✅ Новый домен работает для {context_name}")
                    return retry_soup
            elif retry_response.status == 429:
                logger.warning(f"🔥 HTTP 429 даже с новым доменом для {context_name} - пробуем ещё один домен")
                # Рекурсивно пробуем следующий домен
                return await self._fallback_with_new_domain(session, proxy, cookie, headers, url, context_name)
            else:
                logger.warning(f"❌ Ошибка запроса с новым доменом для {context_name}: HTTP {retry_response.status}")
                return None
                
        except Exception as e:
            error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
            logger.error(f"❌ Ошибка смены домена для {context_name}: {error_msg}")
            return None
    
    async def _fallback_with_new_proxy(self, session, old_proxy, old_cookie, headers, url, context_name):
        """Fallback функция: пробуем с новым прокси если challenge не решился"""
        try:
            logger.info(f"🔄 Fallback: получаем новый прокси для {context_name}")
            
            # Помечаем старый прокси как заблокированный
            from dynamic_cookie_rotation import mark_proxy_temp_blocked
            mark_proxy_temp_blocked(old_proxy, old_cookie)
            
            # Получаем новый прокси и cookie
            new_proxy, new_cookie = await get_next_proxy_cookie_async(session)
            
            if new_proxy != old_proxy or new_cookie != old_cookie:
                logger.info(f"🔄 Повторяем запрос с новым прокси для {context_name}")
                
                # Обновляем заголовки с новым cookie
                headers['Cookie'] = new_cookie
                
                # Обновляем настройки запроса с новым прокси
                request_kwargs = {}
                if new_proxy:
                    request_kwargs['proxy'] = new_proxy
                
                # Повторяем запрос с новыми данными
                # Применяем глобальный rate limiting
                await self._apply_global_rate_limit()
                
                # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ FALLBACK
                retry_response = await network_retry_wrapper(session, 'get', url, 
                                                        headers=headers, timeout=15, **request_kwargs)
                    
                if retry_response.status == 200:
                    retry_html = await retry_response.text()
                    retry_soup = BeautifulSoup(retry_html, 'html.parser')
                    
                    # Проверяем снова на блокировку
                    retry_title = retry_soup.find('title')
                    has_challenge_text = retry_title and 'Making sure you\'re not a bot!' in retry_title.get_text()
                    has_anubis_script = 'id="anubis_challenge"' in retry_html
                    
                    if has_challenge_text or has_anubis_script:
                        logger.warning(f"🤖 Новый прокси тоже показывает challenge для {context_name}, решаем...")
                        
                        # Решаем challenge с новым прокси
                        try:
                            # Создаем простой объект для переключения доменов
                            class SimpleDomainRotator:
                                def get_next_domain(self):
                                    return get_next_nitter_domain()
                            
                            domain_rotator = SimpleDomainRotator()
                            anubis_cookies = await handle_anubis_challenge_for_session(session, url, retry_html, nitter_domain_rotator=domain_rotator)
                            
                            if anubis_cookies:
                                logger.info(f"✅ Challenge решен с новым прокси для {context_name}")
                                
                                # Обновляем куки в заголовках
                                updated_cookies = update_cookies_in_string(headers.get('Cookie', ''), anubis_cookies)
                                headers['Cookie'] = updated_cookies
                                
                                # Повторяем запрос с решенным challenge
                                # Применяем глобальный rate limiting
                                await self._apply_global_rate_limit()
                                
                                # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ФИНАЛЬНОЙ ПОПЫТКИ
                                final_response = await network_retry_wrapper(session, 'get', url, 
                                                                        headers=headers, timeout=15, **request_kwargs)
                                    
                                if final_response.status == 200:
                                    final_html = await final_response.text()
                                    final_soup = BeautifulSoup(final_html, 'html.parser')
                                    
                                    # Финальная проверка
                                    final_title = final_soup.find('title')
                                    final_has_challenge = final_title and 'Making sure you\'re not a bot!' in final_title.get_text()
                                    final_has_anubis = 'id="anubis_challenge"' in final_html
                                    
                                    if final_has_challenge or final_has_anubis:
                                        logger.error(f"❌ Challenge всё ещё не решен для {context_name}")
                                        return None
                                    
                                    logger.info(f"🎉 {context_name} доступен после fallback решения challenge")
                                    return final_soup
                                else:
                                    logger.error(f"❌ Ошибка финального запроса для {context_name}: HTTP {final_response.status}")
                                    return None
                            else:
                                logger.error(f"❌ Не удалось решить challenge с новым прокси для {context_name}")
                                return None
                                
                        except Exception as anubis_error:
                            logger.error(f"❌ Ошибка решения challenge с новым прокси для {context_name}: {anubis_error}")
                            return None
                    else:
                        logger.info(f"✅ Новый прокси работает для {context_name}")
                        return retry_soup
                else:
                    logger.warning(f"❌ Ошибка запроса с новым прокси для {context_name}: HTTP {retry_response.status}")
                    return None
            else:
                logger.warning(f"🚫 Не удалось получить новый прокси для {context_name}")
                return None
                
        except Exception as e:
            error_msg = str(e) if str(e).strip() else f"{type(e).__name__} (пустое сообщение)"
            logger.error(f"❌ Ошибка fallback для {context_name}: {error_msg}")
            return None

    async def cleanup_groups_with_contracts(self) -> Dict[str, bool]:
        """Проверяет все существующие группы и удаляет те, где главный Twitter содержит контракты"""
        results = {}
        groups_to_delete = []
        
        try:
            logger.info("🔍 Проверяем все существующие группы на наличие контрактов...")
            
            for group_key, group in self.groups.items():
                if group.main_twitter:
                    logger.info(f"🔍 Проверяем группу {group.symbol} (@{group.main_twitter})")
                    
                    # Проверяем контракты в главном Twitter
                    has_contracts = await self._check_contracts_in_twitter(group.main_twitter)
                    
                    if has_contracts:
                        logger.warning(f"🚫 Группа {group.symbol} помечена для удаления: контракты найдены в @{group.main_twitter}")
                        groups_to_delete.append(group_key)
                        results[group.symbol] = True
                    else:
                        logger.info(f"✅ Группа {group.symbol} чистая: контракты не найдены в @{group.main_twitter}")
                        results[group.symbol] = False
                else:
                    logger.warning(f"⚠️ Группа {group.symbol} без главного Twitter - пропускаем")
                    results[group.symbol] = False
            
            # Удаляем группы с контрактами
            for group_key in groups_to_delete:
                group = self.groups[group_key]
                logger.warning(f"🗑️ Удаляем группу {group.symbol} с контрактами...")
                await self.delete_group(group_key)
            
            logger.info(f"✅ Проверка завершена. Удалено групп: {len(groups_to_delete)}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки групп: {e}")
            return results

    async def restore_groups_from_sheets_and_update_messages(self) -> Dict[str, bool]:
        """Восстанавливает группы из Google Sheets и обновляет существующие сообщения с кнопками"""
        try:
            logger.info("🔄 Начинаем восстановление групп из Google Sheets...")
            
            # Получаем все существующие таблицы
            from google_sheets_manager import sheets_manager
            if not sheets_manager:
                logger.error("❌ Google Sheets manager не инициализирован")
                return {}
            
            # Сначала загружаем все существующие таблицы в кэш
            logger.info("📥 Загружаем все таблицы токенов в кэш...")
            loaded_sheets = sheets_manager.load_all_duplicate_sheets()
            
            if not loaded_sheets:
                logger.warning("⚠️ Не удалось загрузить таблицы дубликатов")
                return {}
            
            logger.info(f"📊 Загружено {len(loaded_sheets)} таблиц в кэш")
            
            # Получаем список всех таблиц
            existing_sheets = sheets_manager.spreadsheets
            if not existing_sheets:
                logger.warning("⚠️ Нет существующих таблиц для восстановления")
                return {}
            
            results = {}
            
            for group_key, spreadsheet in existing_sheets.items():
                try:
                    logger.info(f"🔍 Восстанавливаем группу {group_key}...")
                    
                    # Получаем данные из таблицы
                    worksheet = spreadsheet.sheet1
                    all_data = worksheet.get_all_values()
                    
                    if len(all_data) <= 1:
                        logger.warning(f"⚠️ Таблица {group_key} пуста")
                        continue
                    
                    # Парсим данные токенов из таблицы
                    tokens = []
                    symbol = None
                    name = None
                    main_twitter = None
                    
                    for row in all_data[1:]:  # Пропускаем заголовок
                        if len(row) >= 4:
                            if not symbol:
                                symbol = row[0]  # Символ
                            if not name:
                                name = row[1]  # Название
                            
                            # Ищем главный Twitter (статус "🎯 ГЛАВНЫЙ")
                            if len(row) >= 8 and row[7] == "🎯 ГЛАВНЫЙ":
                                twitter_cell = row[2]
                                # Извлекаем Twitter аккаунт
                                if twitter_cell and twitter_cell.startswith('@'):
                                    main_twitter = twitter_cell[1:]  # Убираем @
                            
                            # Создаем данные токена
                            token_data = {
                                'symbol': row[0],
                                'name': row[1],
                                'id': row[3],  # Контракт
                                'twitter': row[2] if len(row) > 2 else None,
                                'firstPool': {
                                    'createdAt': row[4] if len(row) > 4 else None
                                }
                            }
                            tokens.append(token_data)
                    
                    if not tokens or not symbol:
                        logger.warning(f"⚠️ Не удалось восстановить данные для группы {group_key}")
                        continue
                    
                    # Создаем группу
                    group = self.GroupData(group_key, symbol, name or symbol)
                    group.tokens = tokens
                    group.main_twitter = main_twitter
                    group.sheet_url = spreadsheet.url
                    group.latest_added_token = tokens[-1] if tokens else None
                    
                    # Ищем официальный анонс если есть главный Twitter
                    if main_twitter:
                        oldest_mention = await self._find_oldest_announcement(main_twitter, symbol)
                        group.official_announcement = oldest_mention
                    
                    # Сохраняем группу
                    self.groups[group_key] = group
                    
                    logger.info(f"✅ Группа {group_key} восстановлена ({len(tokens)} токенов, главный Twitter: @{main_twitter or 'не определен'})")
                    results[group_key] = True
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка восстановления группы {group_key}: {e}")
                    results[group_key] = False
            
            logger.info(f"🔄 Восстановление завершено: {len(results)} групп обработано")
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления групп: {e}")
            return {}

    async def update_existing_messages_with_buttons(self, chat_id: int, thread_id: int = None) -> Dict[str, bool]:
        """Обновляет существующие сообщения в чате с кнопками Google Sheets"""
        try:
            logger.info("🔄 Начинаем поиск и обновление существующих сообщений...")
            
            # Сначала восстанавливаем группы
            restored_groups = await self.restore_groups_from_sheets_and_update_messages()
            if not restored_groups:
                logger.warning("⚠️ Нет восстановленных групп для обновления")
                return {}
            
            results = {}
            
            # Пытаемся найти сообщения для каждой группы
            for group_key, group in self.groups.items():
                try:
                    if not group.sheet_url:
                        logger.warning(f"⚠️ Группа {group_key} не имеет URL таблицы")
                        continue
                    
                    # Попытка найти сообщение по содержимому
                    # Это сложная задача, так как нужно сканировать историю чата
                    # Для простоты создадим новое сообщение
                    
                    logger.info(f"🔍 Пытаемся найти сообщение для группы {group.symbol}...")
                    
                    # Отправляем новое сообщение с кнопкой
                    group.message_id = await self._send_group_message(group)
                    
                    if group.message_id:
                        logger.info(f"✅ Создано новое сообщение для группы {group.symbol} с кнопкой Google Sheets")
                        results[group_key] = True
                    else:
                        logger.error(f"❌ Не удалось создать сообщение для группы {group.symbol}")
                        results[group_key] = False
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления сообщения для группы {group_key}: {e}")
                    results[group_key] = False
            
            logger.info(f"🔄 Обновление сообщений завершено: {len(results)} групп обработано")
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщений: {e}")
            return {}

    async def _get_twitter_profile_info(self, twitter_account: str) -> Optional[Dict]:
        """Получает детальную информацию о Twitter профиле с агрессивными повторными попытками"""
        max_attempts = 20  # Максимум 20 попыток
        attempt = 0
        
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"🔍 Попытка {attempt}/{max_attempts} получить профиль @{twitter_account}")
                
                # 🔄 СОЗДАЕМ НОВЫЙ ПАРСЕР ДЛЯ КАЖДОЙ ПОПЫТКИ (свежие прокси!)
                async with TwitterProfileParser() as parser:
                    # Получаем профиль
                    result = await parser.get_profile_with_replies_multi_page(twitter_account, max_pages=1)
                    
                    # Проверяем что получили правильное количество значений
                    if result and len(result) == 3:
                        profile_data, all_tweets, tweets_with_contracts = result
                    elif result and len(result) == 2:
                        profile_data, all_tweets = result
                        tweets_with_contracts = []
                    else:
                        logger.warning(f"⚠️ Неожиданный результат от парсера для @{twitter_account}: {result}")
                        profile_data = None
                    
                    if profile_data and profile_data.get('followers_count') is not None:
                        logger.info(f"✅ УСПЕХ! Получены данные профиля @{twitter_account}: {profile_data.get('followers_count', 0)} подписчиков")
                        return profile_data
                    else:
                        logger.warning(f"⚠️ Попытка {attempt}: Неполные данные профиля @{twitter_account}")
                        
            except Exception as e:
                logger.error(f"❌ Попытка {attempt}: Ошибка получения профиля @{twitter_account}: {e}")
            
            # Если не последняя попытка - ждем перед повтором
            if attempt < max_attempts:
                # Экспоненциальная задержка: 5, 10, 20, 40, 60, 60, 60...
                delay = min(60, 5 * (2 ** (attempt - 1)))
                logger.info(f"⏳ Ждем {delay}с перед попыткой {attempt + 1} (новый прокси)...")
                await asyncio.sleep(delay)
        
        logger.error(f"💀 ВСЕ {max_attempts} ПОПЫТОК ИСЧЕРПАНЫ для @{twitter_account}! Возвращаем None")
        return None

    def _format_number(self, number: int) -> str:
        """Форматирует число в читаемый вид (1.2K, 15M и т.д.)"""
        if number >= 1_000_000:
            return f"{number / 1_000_000:.1f}M"
        elif number >= 1_000:
            return f"{number / 1_000:.1f}K"
        else:
            return str(number)

    async def _format_twitter_profile_info(self, twitter_account: str, is_main: bool = False) -> Optional[str]:
        """Форматирует информацию о Twitter профиле для сообщения. Возвращает None если информация недоступна"""
        try:
            profile_info = await self._get_twitter_profile_info(twitter_account)
            
            if not profile_info:
                logger.warning(f"⚠️ Информация о профиле @{twitter_account} недоступна")
                return None
            
            if is_main:
                # Полная информация для главного аккаунта
                display_name = profile_info.get('display_name', twitter_account)
                bio = profile_info.get('bio', 'Нет описания')
                join_date = profile_info.get('join_date', 'Неизвестно')
                is_verified = profile_info.get('is_verified', False)
                
                # Статистика
                tweets = self._format_number(profile_info.get('tweets_count', 0))
                followers = self._format_number(profile_info.get('followers_count', 0))
                following = self._format_number(profile_info.get('following_count', 0))
                likes = self._format_number(profile_info.get('likes_count', 0))
                
                # Формируем информацию
                verified_badge = "✅" if is_verified else ""
                
                info = f"🐦 <b>ГЛАВНЫЙ TWITTER:</b> <code>{twitter_account}</code> {verified_badge}\n"
                info += f"📋 <b>Имя:</b> {display_name}\n"
                
                if bio and bio != 'Нет описания':
                    # Bio в виде цитаты, обрезаем если слишком длинное
                    bio_short = bio[:200] + "..." if len(bio) > 200 else bio
                    # Экранируем HTML символы в bio
                    import html
                    bio_short = html.escape(bio_short)
                    info += f"📝 <b>Описание:</b>\n<blockquote>{bio_short}</blockquote>\n"
                
                info += f"📅 <b>Регистрация:</b> {join_date}\n"
                info += f"📊 <b>Статистика:</b> {tweets} твитов • {followers} подписчиков • {following} подписок • {likes} лайков\n"
                
                return info
            else:
                # Краткая информация для дополнительных аккаунтов
                display_name = profile_info.get('display_name', twitter_account)
                followers = self._format_number(profile_info.get('followers_count', 0))
                is_verified = profile_info.get('is_verified', False)
                
                verified_badge = "✅" if is_verified else ""
                return f"@{twitter_account} {verified_badge} ({display_name}, {followers} подписчиков)"
                
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования профиля @{twitter_account}: {e}")
            return None

# Глобальный экземпляр для использования в проекте
# Будет инициализирован в main при запуске
_duplicate_groups_manager = None

def get_duplicate_groups_manager():
    """Возвращает текущий экземпляр менеджера групп токенов"""
    global _duplicate_groups_manager
    return _duplicate_groups_manager

def initialize_duplicate_groups_manager(telegram_token: str):
    """Инициализирует глобальный менеджер групп токенов"""
    global _duplicate_groups_manager
    _duplicate_groups_manager = DuplicateGroupsManager(telegram_token)
    logger.info("✅ Менеджер групп токенов инициализирован")

def shutdown_duplicate_groups_manager():
    """Корректно завершает работу менеджера групп токенов"""
    global _duplicate_groups_manager
    if _duplicate_groups_manager:
        _duplicate_groups_manager.stop()
        _duplicate_groups_manager = None
        logger.info("🛑 Менеджер групп токенов завершен")

# Обратная совместимость - удалена, используйте get_duplicate_groups_manager() 