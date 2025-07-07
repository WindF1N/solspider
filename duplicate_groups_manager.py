#!/usr/bin/env python3
"""
Продвинутая система управления группами дубликатов токенов
Интеграция с Google Sheets, умные Telegram сообщения, отслеживание официальных контрактов
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
from dynamic_cookie_rotation import get_next_proxy_cookie_async
from anubis_handler import handle_anubis_challenge_for_session, update_cookies_in_string

logger = logging.getLogger(__name__)

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
    """Менеджер для управления группами дубликатов с умными функциями"""
    
    def __init__(self, telegram_token: str):
        """Инициализация с токеном Telegram бота"""
        self.telegram_token = telegram_token
        
        # Создаем и запускаем очередь сообщений
        self.telegram_queue = TelegramMessageQueue(telegram_token)
        self.telegram_queue.start()
        
        # Группы дубликатов {group_key: GroupData}
        self.groups = {}
        
        # Отслеживание официальных контрактов {group_key: official_contract_info}
        self.official_contracts = {}
        
        # Кэш результатов проверки Twitter аккаунтов (чтобы не проверять недоступные аккаунты повторно)
        self.twitter_check_cache = {}  # key: "account_symbol" -> {"has_mentions": bool, "last_check": timestamp, "error": str}
        self.cache_ttl = 300  # 5 минут кэш для успешных проверок
        self.error_cache_ttl = 3600  # 1 час кэш для ошибок (404, заблокированы и т.д.)
        
        # Настройки
        self.target_chat_id = -1002680160752  # ID группы
        self.message_thread_id = 14  # ID темы для дубликатов
    
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
        logger.info("🛑 Менеджер групп дубликатов остановлен")
    
    def get_queue_stats(self) -> Dict:
        """Возвращает статистику очереди сообщений"""
        return {
            'queue_size': self.telegram_queue.get_queue_size(),
            'min_delay': self.telegram_queue.min_delay,
            'max_delay': self.telegram_queue.max_delay,
            'is_running': self.telegram_queue.running
        }
    
    class GroupData:
        """Данные группы дубликатов"""
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
    
    async def determine_main_twitter(self, tokens: List[Dict]) -> Optional[str]:
        """Определяет главный Twitter аккаунт на основе упоминаний символа в кавычках с проверкой возраста"""
        try:
            if not tokens:
                return None
            
            # Получаем символ из токенов
            symbol = tokens[0].get('symbol', '').strip()
            if not symbol:
                return None
            
            # Собираем все уникальные Twitter аккаунты
            all_twitter_accounts = set()
            for token in tokens:
                twitter_accounts = self.extract_twitter_accounts(token)
                for account in twitter_accounts:
                    all_twitter_accounts.add(account.lower())
            
            if not all_twitter_accounts:
                logger.warning(f"🚫 Нет Twitter аккаунтов для проверки символа {symbol}")
                return None
            
            logger.info(f"🔍 Проверяем {len(all_twitter_accounts)} Twitter аккаунтов на упоминания \"${symbol}\" (с проверкой возраста)")
            
            # Проверяем каждый аккаунт на наличие упоминаний символа в кавычках
            valid_accounts = []
            has_any_fresh_tweets = False
            
            for twitter_account in all_twitter_accounts:
                logger.info(f"🔍 Проверяем аккаунт @{twitter_account} на упоминания \"${symbol}\"")
                
                # 🚫 КРИТИЧЕСКАЯ ПРОВЕРКА: Проверяем наличие контрактов в аккаунте
                has_contracts = await self._check_contracts_in_twitter(twitter_account)
                if has_contracts:
                    logger.warning(f"🚫 Аккаунт @{twitter_account} ИСКЛЮЧЕН: найдены контракты (официальный токен уже запущен)")
                    continue  # Пропускаем аккаунт с контрактами
                
                # Проверяем наличие символа в кавычках (теперь с проверкой возраста)
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
                logger.warning(f"⏰🚫 ГРУППА {symbol} СКИПАЕТСЯ: Все твиты со всех Twitter аккаунтов старше 30 дней! Группа неактуальна.")
                return None
            
            if not valid_accounts:
                logger.warning(f"🚫 Ни один аккаунт не содержит СВЕЖИЕ упоминания \"${symbol}\" - группа будет пропущена")
                return None
            
            # Если найден только один валидный аккаунт - он главный
            if len(valid_accounts) == 1:
                main_twitter = valid_accounts[0]
                logger.info(f"🎯 Главный Twitter определен: @{main_twitter} (единственный со СВЕЖИМИ упоминаниями \"${symbol}\")")
                return main_twitter
            
            # Если несколько валидных аккаунтов - берем первый (или можно добавить доп. логику)
            main_twitter = valid_accounts[0]
            logger.info(f"🎯 Главный Twitter определен: @{main_twitter} (первый из {len(valid_accounts)} валидных со СВЕЖИМИ твитами)")
            return main_twitter
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения главного Twitter: {e}")
            return None
    
    async def _check_symbol_mentions_in_twitter(self, twitter_account: str, symbol: str) -> bool:
        """Проверяет наличие упоминаний символа в кавычках в Twitter аккаунте (с кэшированием и проверкой возраста)"""
        try:
            # Проверяем кэш
            cache_key = f"{twitter_account}_{symbol}"
            current_time = time.time()
            
            if cache_key in self.twitter_check_cache:
                cached_result = self.twitter_check_cache[cache_key]
                
                # Определяем TTL в зависимости от типа результата
                if cached_result.get('error'):
                    # Для ошибок (404, заблокированы) - длинный кэш
                    ttl = self.error_cache_ttl
                    cache_type = "ERROR"
                else:
                    # Для успешных проверок - короткий кэш
                    ttl = self.cache_ttl
                    cache_type = "SUCCESS"
                
                # Проверяем не истек ли кэш
                if current_time - cached_result['last_check'] < ttl:
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
                
                # Настройка соединения
                connector = aiohttp.TCPConnector(ssl=False)
                request_kwargs = {}
                if proxy:
                    request_kwargs['proxy'] = proxy
                
                # URL поиска в конкретном аккаунте
                search_url = f"https://nitter.tiekoetter.com/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                
                async with session.get(search_url, headers=headers, timeout=20, **request_kwargs) as response:
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
                                    # Сохраняем в кэш как успех
                                    self.twitter_check_cache[cache_key] = {
                                        'has_mentions': True,
                                        'last_check': current_time,
                                        'error': None
                                    }
                                    return True
                                else:
                                    logger.warning(f"⏰ Найдено {valid_tweets} твитов с \"${symbol}\" в @{twitter_account}, но все старше 30 дней")
                                    # Сохраняем в кэш как неуспех (старые твиты)
                                    self.twitter_check_cache[cache_key] = {
                                        'has_mentions': False,
                                        'last_check': current_time,
                                        'error': 'Все твиты старше 30 дней'
                                    }
                                    return False
                            else:
                                logger.warning(f"🚫 Найдено {len(tweets)} твитов, но НИ ОДИН не содержит \"${symbol}\" в @{twitter_account}")
                                # Сохраняем в кэш как неуспех
                                self.twitter_check_cache[cache_key] = {
                                    'has_mentions': False,
                                    'last_check': current_time,
                                    'error': 'Твиты найдены, но без символа'
                                }
                                return False
                        else:
                            logger.debug(f"🚫 Упоминания \"${symbol}\" НЕ найдены в @{twitter_account}")
                            # Сохраняем в кэш как неуспех
                            self.twitter_check_cache[cache_key] = {
                                'has_mentions': False,
                                'last_check': current_time,
                                'error': None
                            }
                            return False
                    else:
                        logger.warning(f"❌ Ошибка поиска в @{twitter_account}: HTTP {response.status}")
                        # Сохраняем в кэш как ошибку
                        self.twitter_check_cache[cache_key] = {
                            'has_mentions': False,
                            'last_check': current_time,
                            'error': f'HTTP {response.status}'
                        }
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Ошибка проверки символа в @{twitter_account}: {e}")
            # Сохраняем в кэш как ошибку
            self.twitter_check_cache[cache_key] = {
                'has_mentions': False,
                'last_check': current_time,
                'error': str(e)
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
    
    async def _find_oldest_token_mention(self, twitter_account: str, symbol: str) -> Optional[Dict]:
        """Находит самое старое упоминание символа в кавычках в Twitter аккаунте"""
        try:
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
                
                # Настройка соединения
                connector = aiohttp.TCPConnector(ssl=False)
                request_kwargs = {}
                if proxy:
                    request_kwargs['proxy'] = proxy
                
                # Поиск по страницам (максимум 3)
                all_tweets = []
                current_url = f"https://nitter.tiekoetter.com/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                
                for page in range(3):  # Максимум 3 страницы
                    logger.debug(f"🔍 Страница {page + 1} поиска \"${symbol}\" в @{twitter_account}")
                    
                    async with session.get(current_url, headers=headers, timeout=20, **request_kwargs) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Проверяем на блокировку Nitter
                            title = soup.find('title')
                            if title and 'Making sure you\'re not a bot!' in title.get_text():
                                logger.warning(f"🚫 Nitter заблокирован на странице {page + 1} для поиска старых упоминаний @{twitter_account} - пытаемся восстановить")
                                
                                # 🔄 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ: решаем Anubis challenge
                                retry_soup = await self._handle_nitter_block(session, proxy, cookie, headers, current_url, f"страница {page + 1} поиска старых упоминаний @{twitter_account}", html)
                                
                                if retry_soup:
                                    # Успешно восстановились, используем новый soup
                                    soup = retry_soup
                                    logger.info(f"✅ Восстановление успешно для страницы {page + 1} поиска старых упоминаний @{twitter_account}")
                                else:
                                    # Не удалось восстановиться, прерываем цикл
                                    logger.error(f"❌ Не удалось восстановиться для страницы {page + 1} поиска старых упоминаний @{twitter_account}")
                                    break
                            
                            # Ищем твиты на текущей странице
                            tweets = soup.find_all('div', class_='timeline-item')
                            page_tweets_count = 0
                            symbol_pattern = f"${symbol.upper()}"  # Определяем паттерн символа
                            
                            if tweets:
                                for tweet in tweets:
                                    # Извлекаем данные твита
                                    tweet_text_elem = tweet.find('div', class_='tweet-content')
                                    tweet_date_elem = tweet.find('span', class_='tweet-date')
                                    tweet_link_elem = tweet.find('a', class_='tweet-link')
                                    
                                    if tweet_text_elem and tweet_date_elem:
                                        tweet_text = tweet_text_elem.get_text(strip=True)
                                        
                                        # Получаем дату из атрибута title ссылки, если доступно
                                        tweet_date = ""
                                        date_link = tweet_date_elem.find('a')
                                        if date_link and date_link.get('title'):
                                            # Берем полную дату из title: "Jun 16, 2025 · 6:03 PM UTC"
                                            tweet_date = date_link.get('title')
                                        else:
                                            # Fallback: берем текст элемента
                                            tweet_date = tweet_date_elem.get_text(strip=True)
                                        
                                        tweet_url = ""
                                        
                                        # Получаем ссылку на твит
                                        if tweet_link_elem and 'href' in tweet_link_elem.attrs:
                                            tweet_url = f"https://nitter.tiekoetter.com{tweet_link_elem['href']}"
                                        
                                        # 🔍 КРИТИЧЕСКАЯ ВАЛИДАЦИЯ: проверяем наличие "$SYMBOL" в тексте твита (регистронезависимо)
                                        if symbol_pattern in tweet_text.upper():
                                            # Проверяем возраст твита - для официального анонса берем только свежие твиты
                                            tweet_age = self._get_tweet_age(tweet_date_elem)
                                            one_month_ago = datetime.now() - timedelta(days=30)
                                            
                                            if tweet_age and tweet_age > one_month_ago:
                                                all_tweets.append({
                                                    'text': tweet_text,
                                                    'date': tweet_date,
                                                    'url': tweet_url,
                                                    'page': page + 1,
                                                    'age': tweet_age
                                                })
                                                page_tweets_count += 1
                                                logger.debug(f"✅ Валидный СВЕЖИЙ твит с \"{symbol_pattern}\" ({tweet_age.strftime('%Y-%m-%d')}): {tweet_text[:50]}...")
                                            else:
                                                logger.debug(f"⏰ Пропущен СТАРЫЙ твит с \"{symbol_pattern}\" ({tweet_age.strftime('%Y-%m-%d') if tweet_age else 'неизвестно'}): {tweet_text[:50]}...")
                                        else:
                                            logger.debug(f"❌ Пропущен твит без \"{symbol_pattern}\": {tweet_text[:50]}...")
                                
                                logger.info(f"📄 Страница {page + 1}: найдено {page_tweets_count} ВАЛИДНЫХ твитов с \"{symbol_pattern}\"")
                            else:
                                logger.debug(f"🚫 На странице {page + 1} твиты не найдены")
                            
                            # Ищем ссылку на следующую страницу - правильный поиск в .show-more
                            next_link = None
                            has_more = False
                            
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
                            
                            # Проверяем есть ли следующая страница
                            if next_link and 'href' in next_link.attrs and page < 2:
                                next_url = next_link['href']
                                
                                # Правильно формируем URL для следующей страницы
                                if next_url.startswith('/'):
                                    current_url = f"https://nitter.tiekoetter.com{next_url}"
                                elif next_url.startswith('?'):
                                    # Если это только параметры, заменяем параметры в базовом URL
                                    current_url = f"https://nitter.tiekoetter.com/{twitter_account}/search{next_url}"
                                else:
                                    current_url = next_url
                                
                                logger.debug(f"🔗 Следующая страница: {current_url}")
                                has_more = True
                                
                                # Пауза между страницами
                                await asyncio.sleep(2)
                            else:
                                logger.debug(f"🚫 Следующая страница не найдена или достигнут лимит")
                                has_more = False
                            
                            # Если нет следующей страницы и нет твитов на текущей - прерываем
                            if not has_more and page_tweets_count == 0:
                                logger.debug(f"🚫 Нет больше страниц и твитов")
                                break
                        else:
                            logger.warning(f"❌ Ошибка загрузки страницы {page + 1} для @{twitter_account}: HTTP {response.status}")
                            break
                
                # Возвращаем самый старый валидный СВЕЖИЙ твит (последний в списке, так как Nitter сортирует по убыванию)
                if all_tweets:
                    oldest_tweet = all_tweets[-1]  # Последний твит = самый старый из свежих
                    logger.info(f"🕰️ Найден самый старый СВЕЖИЙ твит с \"${symbol}\" в @{twitter_account}: {oldest_tweet['date']} (возраст: {oldest_tweet['age'].strftime('%Y-%m-%d')})")
                    return oldest_tweet
                else:
                    logger.warning(f"⏰🚫 СВЕЖИЕ твиты с \"${symbol}\" не найдены в @{twitter_account} - все твиты старше 30 дней!")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка поиска старого упоминания в @{twitter_account}: {e}")
            return None
    
    async def _check_contracts_in_twitter(self, twitter_account: str) -> bool:
        """Проверяет наличие контрактов в Twitter аккаунте (3 страницы)"""
        try:
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
                
                # Настройка соединения
                connector = aiohttp.TCPConnector(ssl=False)
                request_kwargs = {}
                if proxy:
                    request_kwargs['proxy'] = proxy
                
                # СНАЧАЛА проверяем основную страницу профиля (био)
                profile_url = f"https://nitter.tiekoetter.com/{twitter_account}"
                
                logger.debug(f"🔍 Проверяем био профиля @{twitter_account}")
                
                async with session.get(profile_url, headers=headers, timeout=20, **request_kwargs) as response:
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
                                # Не удалось восстановиться, но продолжаем проверку твитов
                                logger.warning(f"❌ Не удалось восстановиться для профиля @{twitter_account}, пропускаем био")
                                soup = None
                        
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
                
                # Ищем любые потенциальные контракты через поиск
                search_query = "pump OR raydium OR solana OR token OR contract"
                current_url = f"https://nitter.tiekoetter.com/{twitter_account}/search?f=tweets&q={quote(search_query)}&since=&until=&near="
                
                for page in range(3):  # Максимум 3 страницы
                    logger.debug(f"🔍 Страница {page + 1} поиска контрактов в @{twitter_account}")
                    
                    async with session.get(current_url, headers=headers, timeout=20, **request_kwargs) as response:
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
                                    # Не удалось восстановиться, прерываем цикл
                                    logger.error(f"❌ Не удалось восстановиться для страницы {page + 1} поиска @{twitter_account}")
                                    break
                            
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
                                
                                # Правильно формируем URL для следующей страницы
                                if next_url.startswith('/'):
                                    current_url = f"https://nitter.tiekoetter.com{next_url}"
                                elif next_url.startswith('?'):
                                    # Если это только параметры, заменяем параметры в базовом URL
                                    current_url = f"https://nitter.tiekoetter.com/{twitter_account}/search{next_url}"
                                else:
                                    current_url = next_url
                                
                                logger.debug(f"🔗 Следующая страница контрактов: {current_url}")
                                
                                # Пауза между страницами
                                await asyncio.sleep(2)
                            else:
                                logger.debug(f"🚫 Следующая страница не найдена или достигнут лимит")
                                break
                        else:
                            logger.warning(f"❌ Ошибка загрузки страницы {page + 1} для @{twitter_account}: HTTP {response.status}")
                            break
                
                # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: страница with_replies (максимум 5 страниц)
                logger.debug(f"🔍 Проверяем страницу with_replies @{twitter_account}")
                
                current_url = f"https://nitter.tiekoetter.com/{twitter_account}/with_replies"
                
                for page in range(5):  # Максимум 5 страниц
                    logger.debug(f"🔍 Страница {page + 1} with_replies для @{twitter_account}")
                    
                    async with session.get(current_url, headers=headers, timeout=20, **request_kwargs) as response:
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
                                    # Не удалось восстановиться, прерываем цикл
                                    logger.error(f"❌ Не удалось восстановиться для страницы {page + 1} with_replies @{twitter_account}")
                                    break
                            
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
                            
                            if next_link and 'href' in next_link.attrs and page < 4:
                                next_url = next_link['href']
                                
                                # Правильно формируем URL для следующей страницы
                                if next_url.startswith('/'):
                                    current_url = f"https://nitter.tiekoetter.com{next_url}"
                                elif next_url.startswith('?'):
                                    # Если это только параметры, заменяем параметры в базовом URL
                                    current_url = f"https://nitter.tiekoetter.com/{twitter_account}/with_replies{next_url}"
                                else:
                                    current_url = next_url
                                
                                logger.debug(f"🔗 Следующая страница with_replies: {current_url}")
                                
                                # Пауза между страницами
                                await asyncio.sleep(2)
                            else:
                                logger.debug(f"🚫 Следующая страница with_replies не найдена или достигнут лимит")
                                break
                        else:
                            logger.warning(f"❌ Ошибка загрузки страницы {page + 1} with_replies для @{twitter_account}: HTTP {response.status}")
                            break
                
                logger.info(f"✅ Контракты НЕ найдены в @{twitter_account} (проверено: био + 3 страницы твитов + 5 страниц with_replies)")
                return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка проверки контрактов в @{twitter_account}: {e}")
            return False
    
    async def add_token_to_group(self, token_data: Dict, reason: str = "Обнаружен дубликат") -> bool:
        """Добавляет токен в группу дубликатов"""
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
                
                logger.info(f"🐛✅ WORMSTER ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен {symbol} добавлен в стаю дубликатов (всего жертв: {len(existing_group.tokens)}) 🎯")
                return True
            
            # Если группы нет - проверяем, существует ли группа с точным ключом
            if group_key not in self.groups:
                # Создаем новую группу
                logger.info(f"🆕 Создаем новую группу дубликатов: {symbol}")
                
                # Загружаем все токены этого символа из БД
                db_tokens = self._load_tokens_from_db(symbol)
                
                # Создаем группу
                group = self.GroupData(group_key, symbol, name)
                group.tokens = db_tokens + [token_data] if token_data not in db_tokens else db_tokens
                group.latest_added_token = self._enrich_token_with_date(token_data)  # 🎯 Обогащаем датой из БД!
                
                # Определяем главный Twitter аккаунт (новая логика с проверкой символа в кавычках)
                group.main_twitter = await self.determine_main_twitter(group.tokens)
                
                # ⚠️ СМЯГЧЕННАЯ ПРОВЕРКА: Если главный Twitter не определен, всё равно создаем группу, но с предупреждением
                if not group.main_twitter:
                    logger.warning(f"⚠️ Группа {symbol} создана БЕЗ главного Twitter аккаунта - токены будут отслеживаться, но без проверки анонса")
                    
                    # 🚀 Создаем группу без Twitter аккаунта В ФОНЕ (БЕЗ ОТПРАВКИ СООБЩЕНИЯ)
                    group.official_announcement = None
                    group.sheet_url = None
                    group.message_id = None  # НЕ отправляем сообщение в Telegram
                    
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
                
                # 🔍 Ищем самое старое упоминание токена для официального анонса
                oldest_mention = await self._find_oldest_token_mention(group.main_twitter, symbol)
                if oldest_mention:
                    group.official_announcement = oldest_mention
                    logger.info(f"📅 Найден официальный анонс токена {symbol} от {oldest_mention['date']}")
                else:
                    group.official_announcement = None
                    logger.warning(f"🐛❌ WORMSTER НЕ НАШЁЛ АНОНС В @{group.main_twitter}, но всё равно создаёт группу {symbol}! 🚫")
                
                # 🚀 ПОЛНОСТЬЮ АСИНХРОННАЯ ЛОГИКА: сообщение БЕЗ кнопки, затем таблица в фоне
                logger.info(f"📊 Группа {symbol} создается асинхронно...")
                
                # Сначала отправляем сообщение БЕЗ кнопки (не тормозим поток)
                group.sheet_url = None  # Пока нет таблицы
                group.message_id = await self._send_group_message(group)
                
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
                    
                    # Обновляем сообщение с актуальными данными
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
                        oldest_mention = await self._find_oldest_token_mention(new_main_twitter, symbol)
                        group.official_announcement = oldest_mention
                
                # 🔍 ИСПРАВЛЕНИЕ: Ищем анонс если его нет в существующей группе
                if group.main_twitter and not group.official_announcement:
                    logger.info(f"🐛🔍 WORMSTER НАШЁЛ ГРУППУ {symbol} БЕЗ АНОНСА! Копаем глубже в @{group.main_twitter}...")
                    oldest_mention = await self._find_oldest_token_mention(group.main_twitter, symbol)
                    if oldest_mention:
                        group.official_announcement = oldest_mention
                        logger.info(f"📅 Найден анонс для существующей группы {symbol} от {oldest_mention['date']}")
                
                # 🔧 ИСПРАВЛЕНИЕ: Всегда пересоздаем таблицу с полным списком токенов
                logger.info(f"🔄 Пересоздаем таблицу для группы {symbol} с {len(group.tokens)} токенами...")
                self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                
                logger.info(f"🐛✅ WORMSTER ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен {symbol} добавлен в стаю дубликатов (всего жертв: {len(group.tokens)}) 🎯")
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

    async def _format_group_message(self, group: 'GroupData') -> str:
        """Форматирует текст сообщения для группы дубликатов"""
        try:
            # 🐛 АГРЕССИВНЫЙ ЗАГОЛОВОК WORMSTER'А
            message = f"🐛💰 <b>WORMSTER НАШЁЛ СТАЮ ДУБЛИКАТОВ: ${group.symbol.upper()}!</b>\n"
            message += f"🎯 <b>Цель для ИКСОВ:</b> {group.name}\n"
            message += f"⚡ <b>ВНИМАНИЕ!</b> Обнаружены множественные листинги! Время для хантинга! 🔥\n\n"
            
            # Информация о главном Twitter аккаунте
            if group.main_twitter:
                message += f"🐦 <b>ГЛАВНЫЙ TWITTER:</b> @{group.main_twitter}\n"
                
                # Официальный анонс токена (самый старый твит)
                if group.official_announcement:
                    message += f"📢 <b>ОФИЦИАЛЬНЫЙ АНОНС:</b>\n"
                    message += f"📅 <b>Дата:</b> {group.official_announcement['date']}\n"
                    # Обрезаем текст если слишком длинный
                    announcement_text = group.official_announcement['text']
                    if len(announcement_text) > 200:
                        announcement_text = announcement_text[:200] + "..."
                    message += f"<blockquote>{announcement_text}</blockquote>\n"
                    
                    # Добавляем список дополнительных Twitter аккаунтов
                    additional_accounts = await self._get_additional_twitter_accounts(group)
                    if additional_accounts:
                        message += f"🐦 <b>Дополнительные Twitter аккаунты:</b>\n"
                        for account in additional_accounts:
                            message += f"• @{account}\n"
                    message += "\n"
                else:
                    message += f"📢 <b>АНОНС:</b> Не найден\n\n"
                
                # 🐛 СТАТУС ОХОТЫ WORMSTER'А
                if group.official_contract:
                    message += f"🎉 <b>БИНГО! WORMSTER ПОЙМАЛ ОФИЦИАЛКУ!</b>\n"
                    message += f"💎 <b>Золотой адрес:</b> <code>{group.official_contract['address']}</code>\n"
                    message += f"📅 <b>Момент победы:</b> {group.official_contract['date']}\n"
                    message += f"🚀 <b>ЭТО ОНО! ГОТОВЬ КОШЕЛЁК К ИКСАМ!</b>\n\n"
                else:
                    message += f"🔍 <b>WORMSTER ПРОДОЛЖАЕТ ОХОТУ...</b>\n"
                    message += f"👀 Официальный контракт всё ещё скрывается в Twitter-джунглях!\n"
                    message += f"⚡ Но охота не прекращается! Поиск продолжается! 🐛\n\n"
            else:
                message += f"❓ <b>ГЛАВНЫЙ TWITTER:</b> Не определен\n\n"
            
            # 🐛 БОЕВАЯ СТАТИСТИКА WORMSTER'А
            total_tokens = len(group.tokens)
            tokens_with_links = sum(1 for token in group.tokens if self._has_links(token))
            tokens_without_links = total_tokens - tokens_with_links
            
            message += f"⚔️ <b>БОЕВАЯ СВОДКА WORMSTER'А:</b>\n"
            message += f"🎯 Всего целей в засаде: <b>{total_tokens}</b>\n"
            message += f"🔗 Готовых к памп-атаке: <b>{tokens_with_links}</b>\n"
            message += f"👻 Призрачных (без соцсетей): <b>{tokens_without_links}</b>\n"
            if tokens_with_links > 0:
                success_rate = round((tokens_with_links / total_tokens) * 100)
                if success_rate >= 70:
                    message += f"🚀 <b>ШАНС НА ИКССЫ: {success_rate}% - АГРЕССИВНО ЗАХОДИМ!</b>\n"
                elif success_rate >= 40:
                    message += f"⚠️ <b>ШАНС НА ИКССЫ: {success_rate}% - ОСТОРОЖНО, НО ЗАХОДИМ!</b>\n"
                else:
                    message += f"🐛 <b>ШАНС НА ИКССЫ: {success_rate}% - WORMSTER В РЕЖИМЕ ОХОТЫ!</b>\n"
            message += "\n"
            
            # Последний добавленный токен
            if group.latest_added_token:
                # 🎯 Показываем именно тот токен, который только что пришел из Jupiter
                latest_token = group.latest_added_token
                latest_contract = latest_token.get('id', 'Unknown')
                latest_created = latest_token.get('firstPool', {}).get('createdAt', '')
                
                # 🔧 FALLBACK: Если нет даты создания, используем время обновления группы
                if not latest_created or latest_created == '' or latest_created is None:
                    logger.warning(f"⚠️ Дата создания токена {latest_contract[:8]}... пустая, используем fallback")
                    created_display = f"{group.last_updated.strftime('%d.%m.%Y %H:%M')} (недавно)"
                else:
                    created_display = self._parse_jupiter_date(latest_created)
                
                message += f"🎯 <b>СВЕЖАЯ ДОБЫЧА WORMSTER'А:</b>\n"
                message += f"<code>{latest_contract}</code>\n"
                message += f"⏰ Время рождения: {created_display} UTC\n"
                message += f"🐛 <b>ЧУВСТВУЮ ЗАПАХ ИКСОВ!</b> Это может быть ТОТ САМЫЙ токен! 💎\n\n"
            elif group.tokens:
                # Fallback: если нет latest_added_token, используем первый токен
                fallback_token = group.tokens[0]
                fallback_contract = fallback_token.get('id', 'Unknown')
                message += f"🆕 <b>КОНТРАКТ:</b>\n"
                message += f"<code>{fallback_contract}</code>\n"
                message += f"📅 Создан: Недавно\n\n"
            
            # 🐛 МЕТКА ВРЕМЕНИ WORMSTER'А
            utc_time = datetime.utcnow()
            message += f"🕐 <b>Wormster обновил данные:</b> {utc_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
            message += f"🎯 <b>ПОМНИ:</b> Ранние птицы ловят лучшие иксы! Не проспи альфу! 💰🐛"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования сообщения группы: {e}")
            return f"❌ Ошибка форматирования группы {group.symbol}"
    
    def _create_group_keyboard(self, group: 'GroupData') -> Dict:
        """Создает inline клавиатуру для группы дубликатов"""
        try:
            buttons = []
            
            # Кнопка Google Sheets - проверяем что URL не пустой
            if group.sheet_url and group.sheet_url.strip():
                buttons.append([{
                    "text": "📊 Смотреть в Google Sheets",
                    "url": group.sheet_url
                }])
                logger.debug(f"✅ Кнопка Google Sheets добавлена для группы {group.symbol}")
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
                            
                            # Обновляем сообщение с кнопкой синхронно (из фонового потока)
                            if group.message_id:
                                try:
                                    logger.info(f"📱 DEBUG: Обновляем сообщение {group.message_id} для {group_key}")
                                    self._update_message_with_sheet_button_sync(group)
                                except Exception as e:
                                    logger.error(f"❌ Ошибка синхронного обновления сообщения: {e}")
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
        """Синхронно форматирует текст сообщения для группы дубликатов (для фонового потока)"""
        try:
            # 🐛 АГРЕССИВНЫЙ ЗАГОЛОВОК WORMSTER'А
            message = f"🐛💰 <b>WORMSTER НАШЁЛ СТАЮ ДУБЛИКАТОВ: ${group.symbol.upper()}!</b>\n"
            message += f"🎯 <b>Цель для ИКСОВ:</b> {group.name}\n"
            message += f"⚡ <b>ВНИМАНИЕ!</b> Обнаружены множественные листинги! Время для хантинга! 🔥\n\n"
            
            # Информация о главном Twitter аккаунте
            if group.main_twitter:
                message += f"🐦 <b>ГЛАВНЫЙ TWITTER:</b> @{group.main_twitter}\n"
                
                # Официальный анонс токена (самый старый твит)
                if group.official_announcement:
                    message += f"📢 <b>ОФИЦИАЛЬНЫЙ АНОНС:</b>\n"
                    message += f"📅 <b>Дата:</b> {group.official_announcement['date']}\n"
                    # Обрезаем текст если слишком длинный
                    announcement_text = group.official_announcement['text']
                    if len(announcement_text) > 200:
                        announcement_text = announcement_text[:200] + "..."
                    message += f"<blockquote>{announcement_text}</blockquote>\n"
                    
                    # Пропускаем дополнительные аккаунты в синхронной версии
                    message += "\n"
                else:
                    message += f"📢 <b>АНОНС:</b> Не найден\n\n"
                
                # 🐛 СТАТУС ОХОТЫ WORMSTER'А
                if group.official_contract:
                    message += f"🎉 <b>БИНГО! WORMSTER ПОЙМАЛ ОФИЦИАЛКУ!</b>\n"
                    message += f"💎 <b>Золотой адрес:</b> <code>{group.official_contract['address']}</code>\n"
                    message += f"📅 <b>Момент победы:</b> {group.official_contract['date']}\n"
                    message += f"🚀 <b>ЭТО ОНО! ГОТОВЬ КОШЕЛЁК К ИКСАМ!</b>\n\n"
                else:
                    message += f"🔍 <b>WORMSTER ПРОДОЛЖАЕТ ОХОТУ...</b>\n"
                    message += f"👀 Официальный контракт всё ещё скрывается в Twitter-джунглях!\n"
                    message += f"⚡ Но охота не прекращается! Поиск продолжается! 🐛\n\n"
            else:
                message += f"❓ <b>ГЛАВНЫЙ TWITTER:</b> Не определен\n\n"
            
            # 🐛 БОЕВАЯ СТАТИСТИКА WORMSTER'А
            total_tokens = len(group.tokens)
            tokens_with_links = sum(1 for token in group.tokens if self._has_links(token))
            tokens_without_links = total_tokens - tokens_with_links
            
            message += f"⚔️ <b>БОЕВАЯ СВОДКА WORMSTER'А:</b>\n"
            message += f"🎯 Всего целей в засаде: <b>{total_tokens}</b>\n"
            message += f"🔗 Готовых к памп-атаке: <b>{tokens_with_links}</b>\n"
            message += f"👻 Призрачных (без соцсетей): <b>{tokens_without_links}</b>\n"
            if tokens_with_links > 0:
                success_rate = round((tokens_with_links / total_tokens) * 100)
                if success_rate >= 70:
                    message += f"🚀 <b>ШАНС НА ИКССЫ: {success_rate}% - АГРЕССИВНО ЗАХОДИМ!</b>\n"
                elif success_rate >= 40:
                    message += f"⚠️ <b>ШАНС НА ИКССЫ: {success_rate}% - ОСТОРОЖНО, НО ЗАХОДИМ!</b>\n"
                else:
                    message += f"🐛 <b>ШАНС НА ИКССЫ: {success_rate}% - WORMSTER В РЕЖИМЕ ОХОТЫ!</b>\n"
            message += "\n"
            
            # Последний добавленный токен
            if group.latest_added_token:
                # 🎯 Показываем именно тот токен, который только что пришел из Jupiter
                latest_token = group.latest_added_token
                latest_contract = latest_token.get('id', 'Unknown')
                latest_created = latest_token.get('firstPool', {}).get('createdAt', '')
                
                # 🔧 FALLBACK: Если нет даты создания, используем время обновления группы
                if not latest_created or latest_created == '' or latest_created is None:
                    logger.warning(f"⚠️ Дата создания токена {latest_contract[:8]}... пустая, используем fallback")
                    created_display = f"{group.last_updated.strftime('%d.%m.%Y %H:%M')} (недавно)"
                else:
                    created_display = self._parse_jupiter_date(latest_created)
                
                message += f"🎯 <b>СВЕЖАЯ ДОБЫЧА WORMSTER'А:</b>\n"
                message += f"<code>{latest_contract}</code>\n"
                message += f"⏰ Время рождения: {created_display} UTC\n"
                message += f"🐛 <b>ЧУВСТВУЮ ЗАПАХ ИКСОВ!</b> Это может быть ТОТ САМЫЙ токен! 💎\n\n"
            elif group.tokens:
                # Fallback: если нет latest_added_token, используем первый токен
                fallback_token = group.tokens[0]
                fallback_contract = fallback_token.get('id', 'Unknown')
                message += f"🆕 <b>КОНТРАКТ:</b>\n"
                message += f"<code>{fallback_contract}</code>\n"
                message += f"📅 Создан: Недавно\n\n"
            
            # 🐛 МЕТКА ВРЕМЕНИ WORMSTER'А
            utc_time = datetime.utcnow()
            message += f"🕐 <b>Wormster обновил данные:</b> {utc_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
            message += f"🎯 <b>ПОМНИ:</b> Ранние птицы ловят лучшие иксы! Не проспи альфу! 💰🐛"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка синхронного форматирования сообщения группы: {e}")
            return f"❌ Ошибка форматирования группы {group.symbol}"

    def _update_message_with_sheet_button_sync(self, group: 'GroupData') -> bool:
        """Синхронно обновляет сообщение Telegram с кнопкой Google Sheets (для фонового потока)"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False

            # Синхронное форматирование сообщения (без await)
            message_text = self._format_group_message_sync(group)
            inline_keyboard = self._create_group_keyboard(group)

            payload = {
                "chat_id": self.target_chat_id,
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

            payload = {
                "chat_id": self.target_chat_id,
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
                payload = {
                    "chat_id": self.target_chat_id,
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
                anubis_cookies = await handle_anubis_challenge_for_session(session, url, html_content)
                
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
                    async with session.get(url, headers=headers, timeout=20, **request_kwargs) as anubis_response:
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
            logger.error(f"❌ Ошибка автоматического восстановления для {context_name}: {e}")
            return None
    
    async def _fallback_with_new_proxy(self, session, old_proxy, old_cookie, headers, url, context_name):
        """Fallback функция: пробуем с новым прокси если challenge не решился"""
        try:
            logger.info(f"🔄 Fallback: получаем новый прокси для {context_name}")
            
            # Помечаем старый прокси как заблокированный
            from dynamic_cookie_rotation import mark_proxy_temp_blocked
            mark_proxy_temp_blocked(old_proxy, old_cookie, block_duration_minutes=5)
            
            # Получаем новый прокси и cookie
            from dynamic_cookie_rotation import get_next_proxy_cookie_async
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
                async with session.get(url, headers=headers, timeout=20, **request_kwargs) as retry_response:
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
                                anubis_cookies = await handle_anubis_challenge_for_session(session, url, retry_html)
                                
                                if anubis_cookies:
                                    logger.info(f"✅ Challenge решен с новым прокси для {context_name}")
                                    
                                    # Обновляем куки в заголовках
                                    updated_cookies = update_cookies_in_string(headers.get('Cookie', ''), anubis_cookies)
                                    headers['Cookie'] = updated_cookies
                                    
                                    # Повторяем запрос с решенным challenge
                                    async with session.get(url, headers=headers, timeout=20, **request_kwargs) as final_response:
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
            logger.error(f"❌ Ошибка fallback для {context_name}: {e}")
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

# Глобальный экземпляр для использования в проекте
# Будет инициализирован в main при запуске
_duplicate_groups_manager = None

def get_duplicate_groups_manager():
    """Возвращает текущий экземпляр менеджера групп дубликатов"""
    global _duplicate_groups_manager
    return _duplicate_groups_manager

def initialize_duplicate_groups_manager(telegram_token: str):
    """Инициализирует глобальный менеджер групп дубликатов"""
    global _duplicate_groups_manager
    _duplicate_groups_manager = DuplicateGroupsManager(telegram_token)
    logger.info("✅ Менеджер групп дубликатов инициализирован")

def shutdown_duplicate_groups_manager():
    """Корректно завершает работу менеджера групп дубликатов"""
    global _duplicate_groups_manager
    if _duplicate_groups_manager:
        _duplicate_groups_manager.stop()
        _duplicate_groups_manager = None
        logger.info("🛑 Менеджер групп дубликатов завершен")

# Обратная совместимость - удалена, используйте get_duplicate_groups_manager() 