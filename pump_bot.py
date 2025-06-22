import asyncio
import websockets
import json
import requests
import logging
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re
import time
import random
import ssl
from logging.handlers import RotatingFileHandler
import colorlog
import threading
import aiohttp
from urllib.parse import quote
from database import get_db_manager, TwitterAuthor, Token, Trade, Migration, TweetMention
from logger_config import setup_logging, log_token_analysis, log_trade_activity, log_database_operation, log_daily_stats
from connection_monitor import connection_monitor
from cookie_rotation import proxy_cookie_rotator, background_proxy_cookie_rotator, cookie_rotator
from twitter_profile_parser import TwitterProfileParser


# Загрузка переменных окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv не установлен, используем системные переменные окружения
    pass

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# Инициализация парсера профилей Twitter (будет создан в async функциях)
twitter_parser = None

# Telegram конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# Список чатов для отправки уведомлений
CHAT_IDS = [
    CHAT_ID,  # Основной чат из .env
    "203504880"
]

# WebSocket конфигурация
WEBSOCKET_CONFIG = {
    'ping_interval': 30,     # Ping каждые 30 секунд
    'ping_timeout': 20,      # Ожидание pong 20 секунд 
    'close_timeout': 15,     # Таймаут закрытия
    'max_size': 10**7,       # Максимальный размер сообщения (10MB)
    'max_queue': 32,         # Размер очереди
    'heartbeat_check': 300,  # Проверка соединения если нет сообщений 5 минут
    'health_check_interval': 100  # Проверяем здоровье каждые 100 сообщений
}

# Nitter конфигурация для анализа Twitter
NITTER_COOKIE = "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiMGEyOWM0YzcwZGM0YzYxMjE2NTNkMzQwYTU0YTNmNTFmZmJlNDIwOGM4MWZkZmUxNDA4MTY2MGNmMDc3ZGY2IiwiZXhwIjoxNzQ5NjAyOTA3LCJpYXQiOjE3NDg5OTgxMDcsIm5iZiI6MTc0ODk5ODA0Nywibm9uY2UiOiIxMzI4MSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWEwZjdmMjBjNGQ0MGU5ODIzMWI4MDNmNWZiMGJlMGZjZmZiOGRhOTIzNDUyNDdhZjU1Yjk1MDJlZWE2In0.615N6HT0huTaYXHffqbBWqlpbpUgb7uVCh__TCoIuZLtGzBkdS3K8fGOPkFxHrbIo2OY3bw0igmtgDZKFesjAg"

# Черный список авторов Twitter (исключаем из анализа)
TWITTER_AUTHOR_BLACKLIST = {
    'launchonpump',    # @LaunchOnPump - официальный аккаунт платформы
    'fake_aio',        # Спам-аккаунт
    'cheeznytrashiny', # Спам-аккаунт
    'drvfh54737952',   # @drvfh54737952 - спамер контрактов (много разных токенов)
    'cvxej15391531',   # @cvxej15391531 - спамер контрактов (каждый твит = контракт)
    'cheeze_devs',
    'h1ghlysk1lled',
    'loafzsol',
    'moonminer100x',
    'mmifh46796833',
    'vkhzb26995951',
    'glvgw57181461',
}
# Очередь для асинхронной обработки анализа Twitter
twitter_analysis_queue = asyncio.Queue()
# Словарь для хранения результатов анализа
twitter_analysis_results = {}

def send_telegram(message, inline_keyboard=None):
    """Отправка сообщения в Telegram во все чаты"""
    success_count = 0
    total_chats = 0
    
    for chat_id in CHAT_IDS:
        # Пропускаем пустые или неверные chat_id
        if not chat_id or chat_id in ["YOUR_CHAT_ID", ""]:
            continue
            
        total_chats += 1
        
        try:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            
            if inline_keyboard:
                payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
            
            response = requests.post(TELEGRAM_URL, json=payload)
            if response.status_code == 200:
                logger.info(f"✅ Сообщение отправлено в чат {chat_id}")
                success_count += 1
            else:
                logger.error(f"❌ Ошибка Telegram для чата {chat_id}: {response.text}")
                
        except Exception as e:
            logger.error(f"Ошибка Telegram для чата {chat_id}: {e}")
    
    if success_count > 0:
        logger.info(f"📤 Сообщение отправлено в {success_count}/{total_chats} чатов")
        return True
    else:
        logger.error("❌ Не удалось отправить сообщение ни в один чат")
        return False

def send_telegram_photo(photo_url, caption, inline_keyboard=None):
    """Отправка фото с подписью в Telegram во все чаты"""
    success_count = 0
    total_chats = 0
    
    for chat_id in CHAT_IDS:
        # Пропускаем пустые или неверные chat_id
        if not chat_id or chat_id in ["YOUR_CHAT_ID", ""]:
            continue
            
        total_chats += 1
        
        try:
            # Сначала пробуем отправить фото
            photo_url_to_send = f"https://cf-ipfs.com/ipfs/{photo_url.split('/')[-1]}" if photo_url and not photo_url.startswith('http') else photo_url
            
            payload = {
                "chat_id": chat_id,
                "photo": photo_url_to_send,
                "caption": caption,
                "parse_mode": "HTML"
            }
            
            if inline_keyboard:
                payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
            
            photo_response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", json=payload)
            
            if photo_response.status_code == 200:
                logger.info(f"✅ Фото отправлено в чат {chat_id}")
                success_count += 1
            else:
                # Если фото не удалось отправить, отправляем обычное сообщение
                logger.warning(f"⚠️ Не удалось отправить фото в чат {chat_id}, отправляю текст: {photo_response.text}")
                text_payload = {
                    "chat_id": chat_id,
                    "text": caption,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                
                if inline_keyboard:
                    text_payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
                
                text_response = requests.post(TELEGRAM_URL, json=text_payload)
                if text_response.status_code == 200:
                    logger.info(f"✅ Текстовое сообщение отправлено в чат {chat_id}")
                    success_count += 1
                else:
                    logger.error(f"❌ Ошибка отправки в чат {chat_id}: {text_response.text}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
    
    if success_count > 0:
        logger.info(f"📤 Сообщение отправлено в {success_count}/{total_chats} чатов")
        return True
    else:
        logger.error("❌ Не удалось отправить сообщение ни в один чат")
        return False

async def search_single_query(query, headers, retry_count=0, use_quotes=False, cycle_cookie=None):
    """Выполняет одиночный поисковый запрос к Nitter с повторными попытками при 429 и ротацией cookies"""
    # Добавляем вчерашнюю дату в параметр since (UTC)
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Убираем поиск с кавычками - используем только без кавычек
    url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quote(query)}&since={yesterday}&until=&near="
    
    # Используем переданные прокси+cookie для цикла или получаем новые
    if cycle_cookie:
        # Если передан cycle_cookie, ищем соответствующую связку прокси
        proxy = None
        current_cookie = cycle_cookie
        for pair in proxy_cookie_rotator.proxy_cookie_pairs:
            if pair['cookie'] == cycle_cookie:
                proxy = pair['proxy']
                break
    else:
        proxy, current_cookie = proxy_cookie_rotator.get_next_proxy_cookie()
    
    # Обновляем заголовки с cookie
    headers_with_cookie = headers.copy()
    headers_with_cookie['Cookie'] = current_cookie
    
    try:
        # Используем asyncio совместимую библиотеку
        import aiohttp
        
        # Настройка прокси если требуется
        connector = None
        request_kwargs = {}
        if proxy:
            try:
                # Пробуем новый API (aiohttp 3.8+)
                connector = aiohttp.ProxyConnector.from_url(proxy)
                proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                logger.debug(f"🌐 Используем прокси через ProxyConnector: {proxy_info}")
            except AttributeError:
                # Для aiohttp 3.9.1 - прокси передается напрямую в get()
                connector = aiohttp.TCPConnector()
                request_kwargs['proxy'] = proxy
                proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                logger.debug(f"🌐 Используем прокси напрямую: {proxy_info}")
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers_with_cookie, timeout=20, **request_kwargs) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Проверяем на блокировку Nitter
                    title = soup.find('title')
                    if title and 'Making sure you\'re not a bot!' in title.get_text():
                        logger.error(f"🚫 NITTER ЗАБЛОКИРОВАН! Нужно обновить куки для '{query}' куки '{current_cookie}'")
                        logger.error("🔧 Обновите куки в переменной NITTER_COOKIE")
                        
                        # Отправляем критическое уведомление
                        alert_message = (
                            f"🚫 <b>КРИТИЧЕСКАЯ ОШИБКА!</b>\n\n"
                            f"🤖 <b>Nitter заблокирован</b>\n"
                            f"🔧 <b>Требуется обновление кук</b>\n\n"
                            f"📍 <b>Запрос:</b> {query}\n"
                            f"⚠️ <b>Статус:</b> 'Making sure you're not a bot!'\n\n"
                            f"🛠️ <b>Действия:</b>\n"
                            f"1. Обновите NITTER_COOKIE\n"
                            f"2. Перезапустите бота\n\n"
                            f"❌ <b>Twitter анализ недоступен!</b>"
                        )
                        send_telegram(alert_message)
                        return []
                    
                    # Находим все твиты
                    tweets = soup.find_all('div', class_='timeline-item')
                    tweet_count = len(tweets)
                    
                    # Проверяем, это запрос по контракту (длинная строка)
                    is_contract_query = len(query) > 20
                    
                    # Анализируем активность в твитах
                    engagement = 0
                    for tweet in tweets:
                        stats = tweet.find_all('span', class_='tweet-stat')
                        for stat in stats:
                            icon_container = stat.find('div', class_='icon-container')
                            if icon_container:
                                text = icon_container.get_text(strip=True)
                                # Извлекаем числа (лайки, ретвиты, комментарии)
                                numbers = re.findall(r'\d+', text)
                                if numbers:
                                    engagement += int(numbers[0])
                    
                    quote_status = "с кавычками" if use_quotes else "без кавычек"
                    logger.info(f"🔍 Nitter анализ '{query}' ({quote_status}): {tweet_count} твитов, активность: {engagement}")
                    
                    # Парсим авторов если найдены твиты по контракту
                    authors_data = []
                    if is_contract_query and tweet_count > 0:
                        authors_data = await extract_tweet_authors(soup, query, True)
                        if authors_data:
                            logger.info(f"👥 Найдено {len(authors_data)} авторов для контракта")
                    
                    # Возвращаем твиты с их уникальными идентификаторами
                    tweet_data = []
                    for tweet in tweets:
                        # Извлекаем уникальные данные твита для дедупликации
                        tweet_link = tweet.find('a', class_='tweet-link')
                        tweet_time = tweet.find('span', class_='tweet-date')
                        tweet_text = tweet.find('div', class_='tweet-content')
                        
                        tweet_id = None
                        if tweet_link and 'href' in tweet_link.attrs:
                            tweet_id = tweet_link['href']
                        elif tweet_time and tweet_text:
                            # Создаем уникальный ID на основе времени + текста
                            time_text = tweet_time.get_text(strip=True) if tweet_time else ""
                            content_text = tweet_text.get_text(strip=True)[:50] if tweet_text else ""
                            tweet_id = f"{time_text}_{hash(content_text)}"
                        
                        if tweet_id:
                            tweet_data.append({
                                'id': tweet_id,
                                'engagement': 0,  # будет заполнено ниже
                                'authors': authors_data if is_contract_query else []
                            })
                    
                    # Анализируем активность в твитах
                    for i, tweet in enumerate(tweets):
                        if i < len(tweet_data):
                            stats = tweet.find_all('span', class_='tweet-stat')
                            for stat in stats:
                                icon_container = stat.find('div', class_='icon-container')
                                if icon_container:
                                    text = icon_container.get_text(strip=True)
                                    numbers = re.findall(r'\d+', text)
                                    if numbers:
                                        tweet_data[i]['engagement'] += int(numbers[0])
                    
                    return tweet_data
                elif response.status == 429:
                    # Ошибка 429 - Too Many Requests, увеличиваем паузу
                    if retry_count < 2:  # Максимум 2 попытки с увеличивающимися паузами
                        pause_time = 0.1  # МИНИМАЛЬНАЯ пауза при 429
                        logger.warning(f"⚠️ Nitter 429 (Too Many Requests) для '{query}', ждём {pause_time}с (попытка {retry_count + 1}/2)")
                        await asyncio.sleep(pause_time)
                        return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie)
                    else:
                        # Только после 2 попыток помечаем связку как временно недоступную
                        if not cycle_cookie:  # Помечаем только если НЕ используется cycle_cookie
                            proxy_cookie_rotator.mark_pair_failed(proxy, current_cookie)
                            logger.warning(f"❌ [PUMP_BOT] Связка прокси+cookie помечена как неработающая после 429 ошибок")
                        logger.error(f"❌ Nitter 429 (Too Many Requests) для '{query}' - превышено количество попыток")
                        return []
                else:
                    logger.warning(f"❌ Nitter ответил {response.status} для '{query}'")
                    return []
                    
    except Exception as e:
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБОК
        error_type = type(e).__name__
        error_msg = str(e)
        
        # Определяем тип ошибки для детального логирования
        if "TimeoutError" in error_type or "timeout" in error_msg.lower():
            logger.error(f"⏰ ТАЙМАУТ для '{query}': {error_type} - {error_msg}")
            error_category = "TIMEOUT"
        elif "ConnectionError" in error_type or "connection" in error_msg.lower():
            logger.error(f"🔌 ОШИБКА СОЕДИНЕНИЯ для '{query}': {error_type} - {error_msg}")
            error_category = "CONNECTION"
        elif "429" in error_msg or "too many requests" in error_msg.lower():
            logger.error(f"🚫 ПРЕВЫШЕН ЛИМИТ для '{query}': {error_type} - {error_msg}")
            error_category = "RATE_LIMIT"
        elif "blocked" in error_msg.lower() or "bot" in error_msg.lower():
            logger.error(f"🤖 БЛОКИРОВКА для '{query}': {error_type} - {error_msg}")
            error_category = "BLOCKED"
        else:
            logger.error(f"❓ НЕИЗВЕСТНАЯ ОШИБКА для '{query}': {error_type} - {error_msg}")
            error_category = "UNKNOWN"
        
        # Повторная попытка при любых ошибках (не только 429)
        if retry_count < 3:
            logger.warning(f"⚠️ Повторная попытка для '{query}' после {error_category} (попытка {retry_count + 1}/3)")
            return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie)
        else:
            logger.error(f"❌ Превышено количество попыток для '{query}' после {error_category} - возвращаем пустой результат")
            # Возвращаем информацию об ошибке для анализа
            return {"error": error_category, "message": error_msg, "type": error_type}

async def analyze_token_sentiment(mint, symbol, cycle_cookie=None):
    """Анализ упоминаний токена в Twitter через Nitter (2 запроса без кавычек с дедупликацией)"""
    try:
        # Получаем один cookie для всего анализа токена (2 запроса)
        if not cycle_cookie:
            _, cycle_cookie = proxy_cookie_rotator.get_cycle_proxy_cookie()
            logger.debug(f"🍪 Используем одну связку для анализа токена {symbol}")
            
        # Базовые заголовки без cookie (cookie будет добавлен в search_single_query)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 2 запроса: символ и контракт, только без кавычек
        search_queries = [
            (f'${symbol}', False),  # Символ без кавычек
            (mint, False)           # Контракт без кавычек
        ]
        
        # Выполняем запросы последовательно с паузами для избежания блокировки
        results = []
        error_details = []
        for i, (query, use_quotes) in enumerate(search_queries):
            try:
                result = await search_single_query(query, headers, use_quotes=use_quotes, cycle_cookie=cycle_cookie)
                
                # Проверяем если результат содержит информацию об ошибке
                if isinstance(result, dict) and "error" in result:
                    error_details.append({
                        "query": query,
                        "error_category": result["error"],
                        "error_message": result["message"],
                        "error_type": result["type"]
                    })
                    logger.warning(f"⚠️ Ошибка запроса {i+1} для '{query}': {result['error']} - {result['message']}")
                    results.append([])  # Пустой результат
                else:
                    results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ Неожиданная ошибка запроса {i+1}: {e}")
                error_details.append({
                    "query": query,
                    "error_category": "UNEXPECTED",
                    "error_message": str(e),
                    "error_type": type(e).__name__
                })
                results.append(e)
        
        # Собираем все твиты в один словарь для дедупликации
        all_tweets = {}
        symbol_tweets_count = 0
        contract_tweets_count = 0
        contract_authors = []  # Авторы твитов с контрактами
        
        for i, result in enumerate(results):
            if isinstance(result, Exception) or not result:
                continue
                
            for tweet_data in result:
                tweet_id = tweet_data['id']
                engagement = tweet_data['engagement']
                authors = tweet_data.get('authors', [])
                
                # Если твит уже есть, берем максимальное значение активности
                if tweet_id in all_tweets:
                    all_tweets[tweet_id] = max(all_tweets[tweet_id], engagement)
                else:
                    all_tweets[tweet_id] = engagement
                    
                    # Подсчитываем уникальные твиты по категориям
                    if i == 0:  # Первый запрос - символ
                        symbol_tweets_count += 1
                    else:  # Второй запрос - контракт
                        contract_tweets_count += 1
                        # Добавляем авторов контрактных твитов
                        contract_authors.extend(authors)
        
        # Итоговые подсчеты
        total_tweets = len(all_tweets)
        total_engagement = sum(all_tweets.values())
        
        logger.info(f"📊 Итоговый анализ '{symbol}': {total_tweets} уникальных твитов (символ: {symbol_tweets_count}, контракт: {contract_tweets_count}), активность: {total_engagement}")
        
        # Рассчитываем рейтинг токена
        if total_tweets == 0:
                    return {
            'tweets': 0,
            'symbol_tweets': 0,
            'contract_tweets': 0,
            'engagement': 0,
            'score': 0,
            'rating': '🔴 Мало внимания',
                'contract_found': False,
                'contract_authors': [],
                'error_details': error_details  # Добавляем детали ошибок
        }
        
        # Средняя активность на твит
        avg_engagement = total_engagement / total_tweets if total_tweets > 0 else 0
        
        # Рассчитываем общий скор
        score = (total_tweets * 0.3) + (avg_engagement * 0.7)
        
        # Определяем рейтинг
        if score >= 50:
            rating = '🟢 Высокий интерес'
        elif score >= 20:
            rating = '🟡 Средний интерес'
        elif score >= 5:
            rating = '🟠 Низкий интерес'
        else:
            rating = '🔴 Мало внимания'
        
        return {
            'tweets': total_tweets,
            'symbol_tweets': symbol_tweets_count,
            'contract_tweets': contract_tweets_count,
            'engagement': total_engagement,
            'score': round(score, 1),
            'rating': rating,
            'contract_found': contract_tweets_count > 0,
            'contract_authors': contract_authors,
            'error_details': error_details  # Добавляем детали ошибок
        }
        
    except Exception as e:
        logger.error(f"Ошибка анализа токена: {e}")
        return {
            'tweets': 0,
            'symbol_tweets': 0,
            'contract_tweets': 0,
            'engagement': 0,
            'score': 0,
            'rating': '❓ Ошибка анализа',
            'contract_found': False,
            'contract_authors': [],
            'error_details': [{"query": symbol, "error_category": "SYSTEM_ERROR", "error_message": str(e), "error_type": type(e).__name__}]
        }

async def format_new_token(data):
    """Форматирование сообщения о новом токене с быстрым сохранением и фоновым анализом Twitter"""
    mint = data.get('mint', 'Unknown')
    name = data.get('name', 'Unknown Token')
    symbol = data.get('symbol', 'UNK')
    description = data.get('description', 'Нет описания')
    creator = data.get('traderPublicKey', 'Unknown')
    
    # Создаем базовый анализ Twitter для немедленного сохранения
    twitter_analysis = {
        'tweets': 0,
        'symbol_tweets': 0,
        'contract_tweets': 0,
        'engagement': 0,
        'score': 0,
        'rating': '⏳ Анализируется...',
        'contract_found': False,
        'contract_authors': []
    }
    
    # БЫСТРО сохраняем токен в базу данных БЕЗ ожидания анализа Twitter
    token_id = None
    try:
        db_manager = get_db_manager()
        saved_token = db_manager.save_token(data, twitter_analysis)
        # Просто используем mint как уникальный идентификатор
        if saved_token:
            token_id = mint  # Используем mint как ID для поиска в фоновом анализе
        logger.info(f"⚡ БЫСТРО сохранен токен {symbol} в БД")
        log_database_operation("SAVE_TOKEN", "tokens", "SUCCESS", f"Symbol: {symbol}")
    except Exception as e:
        logger.error(f"❌ Ошибка быстрого сохранения токена в БД: {e}")
        log_database_operation("SAVE_TOKEN", "tokens", "ERROR", str(e))
    
    # Добавляем токен в очередь для фонового анализа Twitter
    try:
        await twitter_analysis_queue.put(data)
        logger.info(f"📋 Токен {symbol} добавлен в очередь фонового анализа Twitter")
    except Exception as e:
        logger.error(f"❌ Ошибка добавления в очередь анализа: {e}")
    
    # Дополнительная информация
    uri = data.get('uri', '')
    initial_buy = data.get('initialBuy', 0)
    market_cap = data.get('marketCap', 0)
    creator_percentage = data.get('creatorPercentage', 0)
    twitter = data.get('twitter', '')
    telegram = data.get('telegram', '')
    website = data.get('website', '')
    
    # Обрезаем описание если слишком длинное
    if len(description) > 200:
        description = description[:200] + "..."
    
    # Получаем bondingCurveKey для кнопок
    bonding_curve_key = data.get('bondingCurveKey', 'Not available')
    
    # Получаем дату создания токена (для новых токенов используем текущее время)
    token_created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    message = (
        f"🚀 <b>НОВЫЙ ТОКЕН НА PUMP.FUN!</b>\n\n"
        f"<b>💎 <a href='https://pump.fun/{mint}'>{name}</a></b>\n"
        f"<b>🏷️ Символ:</b> {symbol}\n"
        f"<b>📍 Mint:</b> <code>{mint}</code>\n"
        f"<b>👤 Создатель:</b> <code>{creator[:8] if len(creator) > 8 else creator}...</code>\n"
        f"<b>📅 Создан:</b> {token_created_at}\n"
        f"<b>💰 Начальная покупка:</b> {initial_buy} SOL\n"
    )
    
    # Добавляем Market Cap только если он больше 0
    if market_cap > 0:
        message += f"<b>📊 Market Cap:</b> ${market_cap:,.0f}\n"
    
    message += (
        f"<b>👨‍💼 Доля создателя:</b> {creator_percentage}%\n"
        f"<b>🐦 Twitter активность:</b> {twitter_analysis['rating']}\n"
        f"<b>📈 Твиты:</b> {twitter_analysis['tweets']} | <b>Активность:</b> {twitter_analysis['engagement']} | <b>Скор:</b> {twitter_analysis['score']}\n"
        f"<b>🔍 Поиск:</b> Символ: {twitter_analysis['symbol_tweets']} | Контракт: {twitter_analysis['contract_tweets']} {'✅' if twitter_analysis['contract_found'] else '❌'}\n"
    )
    
    # Добавляем описание только если оно не пустое и не "Нет описания"
    if description and description.strip() and description.strip() != "Нет описания":
        message += f"<b>📝 Описание:</b> {description}\n"
    
    # Добавляем социальные сети если есть
    if twitter:
        message += f"<b>🐦 Twitter:</b> <a href='{twitter}'>Ссылка</a>\n"
    if telegram:
        message += f"<b>💬 Telegram:</b> <a href='{telegram}'>Ссылка</a>\n"
    if website:
        message += f"<b>🌐 Website:</b> <a href='{website}'>Ссылка</a>\n"
    
    # Добавляем информацию об авторах твитов с контрактом
    if twitter_analysis.get('contract_authors'):
        authors = twitter_analysis['contract_authors']
        total_followers = sum([author.get('followers_count', 0) for author in authors])
        verified_count = sum([1 for author in authors if author.get('is_verified', False)])
        
        message += f"\n\n<b>👥 АВТОРЫ ТВИТОВ С КОНТРАКТОМ ({len(authors)} авторов):</b>\n"
        message += f"   📊 Общий охват: {total_followers:,} подписчиков\n"
        if verified_count > 0:
            message += f"   ✅ Верифицированных: {verified_count}\n"
        message += "\n"
        
        for i, author in enumerate(authors[:3]):  # Показываем максимум 3 авторов
            username = author.get('username', 'Unknown')
            display_name = author.get('display_name', username)
            followers = author.get('followers_count', 0)
            verified = "✅" if author.get('is_verified', False) else ""
            tweet_text = author.get('tweet_text', '')  # Полный текст твита
            tweet_date = author.get('tweet_date', '')  # Дата твита
            
            # Информация о спаме контрактов
            diversity_percent = author.get('contract_diversity', 0)
            spam_percent = author.get('max_contract_spam', 0)
            diversity_recommendation = author.get('diversity_recommendation', 'Нет данных')
            spam_analysis = author.get('spam_analysis', 'Нет данных')
            is_spam_likely = author.get('is_spam_likely', False)
            total_contract_tweets = author.get('total_contract_tweets', 0)
            unique_contracts = author.get('unique_contracts_count', 0)
            
            # Эмодзи для статуса автора (высокая концентрация = хорошо)
            spam_indicator = ""
            if spam_percent >= 80:
                spam_indicator = " 🔥"  # Вспышка активности
            elif spam_percent >= 60:
                spam_indicator = " ⭐"  # Высокая концентрация
            elif spam_percent >= 40:
                spam_indicator = " 🟡"  # Умеренная концентрация
            elif is_spam_likely:
                spam_indicator = " 🚫"  # Много разных контрактов
            
            message += f"{i+1}. <b>@{username}</b> {verified}{spam_indicator}\n"
            if display_name != username:
                message += f"   📝 {display_name}\n"
            
            # Полная информация о профиле
            following_count = author.get('following_count', 0)
            tweets_count = author.get('tweets_count', 0)
            likes_count = author.get('likes_count', 0)
            join_date = author.get('join_date', '')
            
            if followers > 0 or following_count > 0 or tweets_count > 0:
                message += f"   👥 {followers:,} подписчиков | {following_count:,} подписок\n"
                message += f"   📝 {tweets_count:,} твитов | ❤️ {likes_count:,} лайков\n"
                if join_date:
                    message += f"   📅 Создан: {join_date}\n"
            
                            # Добавляем дату публикации если есть
                if tweet_date:
                    message += f"   📅 Опубликован: {tweet_date}\n"
                
                # Добавляем тип твита
                tweet_type = author.get('tweet_type', 'Твит')
                type_emoji = "💬" if tweet_type == "Ответ" else "🐦"
                message += f"   {type_emoji} Тип: {tweet_type}\n"
                
                # Добавляем исторические данные автора
                historical_data = db_manager.get_author_historical_data(author.get('username', ''))
                if historical_data and historical_data.get('total_mentions', 0) > 0:
                    total_mentions = historical_data.get('total_mentions', 0)
                    unique_tokens = historical_data.get('unique_tokens', 0)
                    recent_7d = historical_data.get('recent_mentions_7d', 0)
                    recent_30d = historical_data.get('recent_mentions_30d', 0)
                    
                    message += f"   📊 История: {total_mentions} упоминаний ({unique_tokens} токенов)\n"
                    if recent_7d > 0 or recent_30d > 0:
                        message += f"   📈 Активность: {recent_7d} за 7д, {recent_30d} за 30д\n"
            
            # Показываем анализ концентрации контрактов
            if total_contract_tweets > 0:
                message += f"   📊 Контракты: {unique_contracts} из {total_contract_tweets} твитов (концентрация: {spam_percent:.1f}%)\n"
                message += f"   🎯 Анализ: {spam_analysis}\n"
            
            # Весь текст твита в цитате
            if tweet_text:
                message += f"   💬 <blockquote>{tweet_text}</blockquote>\n"
    
    message += f"\n<b>🕐 Время:</b> {datetime.now().strftime('%H:%M:%S')}"
    
    # Получаем bondingCurveKey для Axiom
    bonding_curve_key = data.get('bondingCurveKey', mint)  # Fallback to mint if no bondingCurveKey
    
    # Создаем кнопки
    keyboard = [
        [
            {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/meme/{bonding_curve_key}"},
            {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{mint}"}
        ],
        [
            {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
        ]
    ]
    
    # НОВАЯ ЛОГИКА: быстрое сохранение, анализ Twitter в фоне
    # Немедленного уведомления нет - Twitter анализ идет в фоне
    immediate_notify = False  # ОТКЛЮЧАЕМ немедленные уведомления - только с анализом Twitter
    
    # Все токены сохраняются в БД и добавляются в фоновый мониторинг
    logger.info(f"⚡ Токен {symbol} - быстро сохранен, Twitter анализ запущен в фоне")
    
    should_notify = immediate_notify
    
    # Логируем анализ токена
    log_token_analysis(data, twitter_analysis, should_notify)
    
    # Получаем URL картинки токена (используем ссылку Axiom)
    token_image_url = f"https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/{mint}.webp"
    
    return message, keyboard, should_notify, token_image_url

def format_trade_alert(data):
    """Форматирование сообщения о крупной сделке"""
    mint = data.get('mint', 'Unknown')
    trader = data.get('traderPublicKey', 'Unknown')
    is_buy = data.get('is_buy', True)
    sol_amount = float(data.get('sol_amount', 0))
    token_amount = data.get('token_amount', 0)
    market_cap = data.get('market_cap', 0)
    
    action = "🟢 ПОКУПКА" if is_buy else "🔴 ПРОДАЖА"
    action_emoji = "📈" if is_buy else "📉"
    
    message = (
        f"{action_emoji} <b>{action}</b>\n\n"
        f"<b>💰 Сумма:</b> {sol_amount:.4f} SOL\n"
        f"<b>🪙 Токенов:</b> {token_amount:,}\n"
        f"<b>📊 Market Cap:</b> ${market_cap:,.0f}\n"
        f"<b>📍 Mint:</b> <code>{mint}</code>\n"
        f"<b>👤 Трейдер:</b> <code>{trader[:8] if len(trader) > 8 else trader}...</code>\n"
        f"<b>🕐 Время:</b> {datetime.now().strftime('%H:%M:%S')}"
    )
    
    # Получаем bondingCurveKey для Axiom
    bonding_curve_key = data.get('bondingCurveKey', mint)  # Fallback to mint if no bondingCurveKey
    
    # Кнопки для торговых уведомлений
    keyboard = [
        [
            {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/meme/{bonding_curve_key}"},
            {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{mint}"}
        ],
        [
            {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
        ]
    ]
    
    return message, keyboard

async def handle_message(message):
    """Обработка сообщений WebSocket"""
    try:
        data = json.loads(message)
        logger.debug(f"Получено: {data}")
        
        # Проверяем, это ли новый токен
        if 'mint' in data and 'name' in data and 'symbol' in data:
            token_name = data.get('name', 'Unknown')
            mint = data.get('mint', 'Unknown')
            symbol = data.get('symbol', 'Unknown')
            logger.info(f"🚀 НОВЫЙ ТОКЕН: {token_name} ({symbol}) - {mint[:8]}...")
            
            # Анализируем токен и получаем сообщение
            msg, keyboard, should_notify, token_image_url = await format_new_token(data)
            
            if should_notify:
                logger.info(f"✅ Токен {symbol} прошел фильтрацию - отправляем уведомление")
                send_telegram_photo(token_image_url, msg, keyboard)
                
                # Обновляем статус уведомления в БД
                try:
                    db_manager = get_db_manager()
                    # Здесь можно обновить поле notification_sent
                    log_database_operation("UPDATE_NOTIFICATION", "tokens", "SUCCESS", f"Symbol: {symbol}")
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления статуса уведомления: {e}")
            else:
                logger.info(f"❌ Токен {symbol} не прошел фильтрацию - пропускаем")
            
        # Проверяем, это ли торговое событие
        elif 'mint' in data and 'traderPublicKey' in data and 'sol_amount' in data:
            sol_amount = float(data.get('sol_amount', 0))
            is_buy = data.get('is_buy', True)
            mint = data.get('mint', 'Unknown')
            
            # Сохраняем торговую операцию в БД
            notification_sent = False
            try:
                db_manager = get_db_manager()
                saved_trade = db_manager.save_trade(data)
                log_database_operation("SAVE_TRADE", "trades", "SUCCESS", 
                                     f"Amount: {sol_amount:.2f} SOL")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения торговой операции в БД: {e}")
                log_database_operation("SAVE_TRADE", "trades", "ERROR", str(e))
            
            # ТОРГОВЫЕ УВЕДОМЛЕНИЯ ОТКЛЮЧЕНЫ - только логируем
            if sol_amount >= 5.0:
                logger.info(f"💰 Крупная {'покупка' if is_buy else 'продажа'}: {sol_amount:.2f} SOL (уведомление отключено)")
                # msg, keyboard = format_trade_alert(data)
                # notification_sent = send_telegram(msg, keyboard)
            
            # Логируем торговую активность
            log_trade_activity(data, notification_sent)
        
        # Проверяем, это ли миграция на Raydium
        elif 'mint' in data and 'bondingCurveKey' in data and 'liquiditySol' in data:
            logger.info(f"🚀 МИГРАЦИЯ НА RAYDIUM: {data.get('mint', 'Unknown')[:8]}...")
            
            # Сохраняем миграцию в БД
            try:
                db_manager = get_db_manager()
                saved_migration = db_manager.save_migration(data)
                log_database_operation("SAVE_MIGRATION", "migrations", "SUCCESS", 
                                     f"Mint: {data.get('mint', 'Unknown')[:8]}...")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения миграции в БД: {e}")
                log_database_operation("SAVE_MIGRATION", "migrations", "ERROR", str(e))
            
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")

async def send_daily_stats():
    """Отправка ежедневной статистики"""
    try:
        db_manager = get_db_manager()
        stats = db_manager.get_token_stats()
        
        if stats:
            # Логируем статистику
            log_daily_stats(stats)
            
            # Формируем сообщение со статистикой
            stats_message = (
                f"📊 <b>ЕЖЕДНЕВНАЯ СТАТИСТИКА SolSpider</b>\n\n"
                f"📈 <b>Всего токенов:</b> {stats['total_tokens']:,}\n"
                f"💰 <b>Всего сделок:</b> {stats['total_trades']:,}\n"
                f"🚀 <b>Миграций на Raydium:</b> {stats['total_migrations']:,}\n"
                f"💎 <b>Крупных сделок за 24ч:</b> {stats['big_trades_24h']:,}\n\n"
            )
            
            # Добавляем топ токены по Twitter скору
            if stats['top_tokens']:
                stats_message += "<b>🏆 ТОП ТОКЕНЫ по Twitter скору:</b>\n"
                for i, token in enumerate(stats['top_tokens'][:5], 1):
                    stats_message += f"{i}. {token['symbol']} - {token['score']:.1f}\n"
            
            stats_message += f"\n<b>🕐 Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Отправляем статистику
            send_telegram(stats_message)
            logger.info("📊 Ежедневная статистика отправлена")
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки ежедневной статистики: {e}")

async def check_connection_health(websocket):
    """Проверка здоровья соединения"""
    try:
        # Отправляем простой ping
        pong_waiter = await websocket.ping()
        await asyncio.wait_for(pong_waiter, timeout=5)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Проблема с соединением: {e}")
        return False

async def extract_tweet_authors(soup, query, contract_found):
    """Извлекает авторов твитов и парсит их профили если найден контракт"""
    authors_data = []
    
    if not contract_found:
        return authors_data  # Парсим авторов только когда найден контракт
    
    try:
        tweets = soup.find_all('div', class_='timeline-item')
        retweets_skipped = 0
        
        for tweet in tweets:
            # Проверяем наличие retweet-header - если есть, то это ретвит
            retweet_header = tweet.find('div', class_='retweet-header')
            if retweet_header:
                retweets_skipped += 1
                continue  # Пропускаем ретвиты
            
            # Извлекаем имя автора
            author_link = tweet.find('a', class_='username')
            if author_link:
                author_username = author_link.get_text(strip=True).replace('@', '')
                
                # Проверяем черный список авторов
                if author_username.lower() in TWITTER_AUTHOR_BLACKLIST:
                    logger.info(f"🚫 Автор @{author_username} в черном списке - пропускаем")
                    continue
                
                # Определяем тип твита (обычный твит или ответ)
                replying_to = tweet.find('div', class_='replying-to')
                tweet_type = "Ответ" if replying_to else "Твит"
                
                # Извлекаем текст твита
                tweet_content = tweet.find('div', class_='tweet-content')
                tweet_text = tweet_content.get_text(strip=True) if tweet_content else ""
                
                # Извлекаем дату твита
                tweet_date = tweet.find('span', class_='tweet-date')
                tweet_date_text = ""
                if tweet_date:
                    # Пытаемся получить полную дату из title атрибута ссылки
                    date_link = tweet_date.find('a')
                    if date_link and date_link.get('title'):
                        tweet_date_text = date_link.get('title')
                    else:
                        # Если title нет, берем текст
                        tweet_date_text = tweet_date.get_text(strip=True)
                
                # Извлекаем статистику твита
                retweets = 0
                likes = 0
                replies = 0
                
                stats = tweet.find_all('span', class_='tweet-stat')
                for stat in stats:
                    icon_container = stat.find('div', class_='icon-container')
                    if icon_container:
                        text = icon_container.get_text(strip=True)
                        numbers = re.findall(r'\d+', text)
                        if numbers:
                            # Определяем тип статистики по порядку
                            if 'reply' in str(stat).lower():
                                replies = int(numbers[0])
                            elif 'retweet' in str(stat).lower():
                                retweets = int(numbers[0])
                            elif 'heart' in str(stat).lower() or 'like' in str(stat).lower():
                                likes = int(numbers[0])
                
                # Добавляем данные автора
                authors_data.append({
                    'username': author_username,
                    'tweet_text': tweet_text,  # Полный текст твита для цитаты
                    'tweet_date': tweet_date_text,
                    'tweet_type': tweet_type,  # Тип твита (Твит или Ответ)
                    'retweets': retweets,
                    'likes': likes,
                    'replies': replies,
                    'query': query
                })
                
                logger.info(f"📝 Найден автор твита: @{author_username} для запроса '{query}'")
        
        if retweets_skipped > 0:
            logger.info(f"🔄 Пропущено {retweets_skipped} ретвитов при парсинге авторов")
        
        # Парсим профили авторов (максимум 5 для производительности)
        unique_authors = list({author['username']: author for author in authors_data}.values())[:5]
        
        if unique_authors:
            logger.info(f"👥 Проверяем профили {len(unique_authors)} авторов...")
            
            # Проверяем существующих авторов в БД
            db_manager = get_db_manager()
            usernames_to_parse = []
            usernames_to_update = []
            existing_authors = {}
            
            for author in unique_authors:
                username = author['username']
                
                # Проверяем в БД
                session = db_manager.Session()
                try:
                    existing_author = session.query(TwitterAuthor).filter_by(username=username).first()
                    if existing_author:
                        # Проверяем возраст данных (обновляем если старше 20 минут)
                        time_since_update = datetime.utcnow() - existing_author.last_updated
                        minutes_since_update = time_since_update.total_seconds() / 60
                        
                        if minutes_since_update >= 20:
                            # Данные устарели - нужно обновить
                            usernames_to_update.append(username)
                            existing_authors[username] = {
                                'username': existing_author.username,
                                'display_name': existing_author.display_name,
                                'followers_count': existing_author.followers_count,
                                'following_count': existing_author.following_count,
                                'tweets_count': existing_author.tweets_count,
                                'likes_count': existing_author.likes_count,
                                'bio': existing_author.bio,
                                'website': existing_author.website,
                                'join_date': existing_author.join_date,
                                'is_verified': existing_author.is_verified,
                                'avatar_url': existing_author.avatar_url
                            }
                            logger.info(f"🔄 Автор @{username} найден в БД, но данные устарели ({minutes_since_update:.1f}мин) - нужно обновление")
                        else:
                            # Данные свежие - используем из БД
                            existing_authors[username] = {
                                'username': existing_author.username,
                                'display_name': existing_author.display_name,
                                'followers_count': existing_author.followers_count,
                                'following_count': existing_author.following_count,
                                'tweets_count': existing_author.tweets_count,
                                'likes_count': existing_author.likes_count,
                                'bio': existing_author.bio,
                                'website': existing_author.website,
                                'join_date': existing_author.join_date,
                                'is_verified': existing_author.is_verified,
                                'avatar_url': existing_author.avatar_url
                            }
                            logger.info(f"📋 Автор @{username} найден в БД ({existing_author.followers_count:,} подписчиков, обновлен {minutes_since_update:.1f}мин назад)")
                    else:
                        # Автор не найден - нужно загрузить профиль
                        usernames_to_parse.append(username)
                        logger.info(f"🔍 Автор @{username} не найден в БД - нужна загрузка")
                finally:
                    session.close()
            
            # Загружаем новых авторов и обновляем устаревшие
            new_profiles = {}
            updated_profiles = {}
            total_to_load = len(usernames_to_parse) + len(usernames_to_update)
            
            if total_to_load > 0:
                logger.info(f"📥 Загружаем {len(usernames_to_parse)} новых и обновляем {len(usernames_to_update)} устаревших профилей...")
                
                # Используем контекстный менеджер для парсера
                async with TwitterProfileParser() as profile_parser:
                    # Загружаем новые профили
                    if usernames_to_parse:
                        new_profiles = await profile_parser.get_multiple_profiles(usernames_to_parse)
                    
                    # Обновляем устаревшие профили
                    if usernames_to_update:
                        updated_profiles = await profile_parser.get_multiple_profiles(usernames_to_update)
            else:
                logger.info(f"✅ Все авторы найдены в БД с актуальными данными - пропускаем загрузку профилей")
            
                                # Обогащаем данные авторов профилями
            for author in unique_authors:
                username = author['username']
                
                # Приоритет: обновленные данные > новые данные > существующие в БД
                profile = updated_profiles.get(username) or new_profiles.get(username) or existing_authors.get(username)
                
                if profile and isinstance(profile, dict):
                    # Получаем исторические данные автора
                    historical_data = db_manager.get_author_historical_data(username)
                    
                    author.update({
                        'display_name': profile.get('display_name', ''),
                        'followers_count': profile.get('followers_count', 0),
                        'following_count': profile.get('following_count', 0),
                        'tweets_count': profile.get('tweets_count', 0),
                        'likes_count': profile.get('likes_count', 0),
                        'bio': profile.get('bio', ''),
                        'website': profile.get('website', ''),
                        'join_date': profile.get('join_date', ''),
                        'is_verified': profile.get('is_verified', False),
                        'avatar_url': profile.get('avatar_url', ''),
                        # Исторические данные
                        'historical_data': historical_data
                    })
                    
                    # Собираем все твиты этого автора с текущей страницы
                    author_tweets_on_page = []
                    for author_data in authors_data:
                        if author_data['username'] == username:
                            author_tweets_on_page.append(author_data['tweet_text'])
                    
                    # ВСЕГДА загружаем полные данные с профиля для точного анализа
                    logger.info(f"🔍 Анализируем контракты автора @{username} (загружаем с профиля)")
                    page_analysis = await analyze_author_page_contracts(username, tweets_on_page=None, load_from_profile=True)
                    
                    # Проверяем что получили достаточно данных
                    total_analyzed_tweets = page_analysis['total_tweets_on_page']
                    
                    # Обрабатываем разные случаи недостатка данных
                    if total_analyzed_tweets < 3:
                        if page_analysis['diversity_category'] == 'Сетевая ошибка':
                            # Сетевая ошибка - НЕ помечаем как подозрительного
                            logger.warning(f"🌐 @{username}: сетевая ошибка при анализе - пропускаем без блокировки")
                            page_analysis['is_spam_likely'] = False
                            page_analysis['recommendation'] = "🌐 Сетевая ошибка - повторить позже"
                        else:
                            # ИСПРАВЛЕННАЯ ЛОГИКА: мало твитов = потенциальный сигнал (новый аккаунт)
                            logger.info(f"🆕 @{username}: новый аккаунт с {total_analyzed_tweets} твитами - потенциальный сигнал!")
                            page_analysis['is_spam_likely'] = False  # НЕ спамер!
                            page_analysis['spam_analysis'] = f"Новый аккаунт: {total_analyzed_tweets} твитов (потенциальный сигнал)"
                            page_analysis['recommendation'] = "🆕 НОВЫЙ АККАУНТ - хороший сигнал"
                    
                    author.update({
                        'contract_diversity': page_analysis['contract_diversity_percent'],
                        'max_contract_spam': page_analysis['max_contract_spam_percent'],
                        'diversity_recommendation': page_analysis['recommendation'],
                        'is_spam_likely': page_analysis['is_spam_likely'],
                        'diversity_category': page_analysis['diversity_category'],
                        'spam_analysis': page_analysis['spam_analysis'],
                        'total_contract_tweets': page_analysis['total_tweets_on_page'],
                        'unique_contracts_count': page_analysis['unique_contracts_on_page']
                    })
                    
                    logger.info(f"📊 @{username}: {page_analysis['total_tweets_on_page']} твитов, концентрация: {page_analysis['max_contract_spam_percent']:.1f}%, разнообразие: {page_analysis['contract_diversity_percent']:.1f}% - {page_analysis['recommendation']}")
                    
                    # Сохраняем в базу данных новые профили
                    if username in usernames_to_parse:
                        try:
                            db_manager.save_twitter_author(profile)
                            db_manager.save_tweet_mention({
                                'mint': query if len(query) > 20 else None,  # Если длинный запрос - это контракт
                                'author_username': username,
                                'tweet_text': author['tweet_text'],
                                'search_query': query,
                                'retweets': author['retweets'],
                                'likes': author['likes'],
                                'replies': author['replies'],
                                'author_followers_at_time': profile.get('followers_count', 0),
                                'author_verified_at_time': profile.get('is_verified', False)
                            })
                            logger.info(f"💾 Сохранен новый профиль @{username} в БД ({profile.get('followers_count', 0):,} подписчиков)")
                        except Exception as e:
                            logger.error(f"❌ Ошибка сохранения профиля @{username}: {e}")
                    
                    # Обновляем существующие профили
                    elif username in usernames_to_update:
                        try:
                            # Обновляем профиль в БД
                            session = db_manager.Session()
                            try:
                                existing_author = session.query(TwitterAuthor).filter_by(username=username).first()
                                if existing_author:
                                    # Отслеживаем изменения для логирования
                                    old_followers = existing_author.followers_count
                                    new_followers = profile.get('followers_count', 0)
                                    followers_change = new_followers - old_followers
                                    
                                    # Обновляем все поля
                                    existing_author.display_name = profile.get('display_name', existing_author.display_name)
                                    existing_author.followers_count = new_followers
                                    existing_author.following_count = profile.get('following_count', existing_author.following_count)
                                    existing_author.tweets_count = profile.get('tweets_count', existing_author.tweets_count)
                                    existing_author.likes_count = profile.get('likes_count', existing_author.likes_count)
                                    existing_author.bio = profile.get('bio', existing_author.bio)
                                    existing_author.website = profile.get('website', existing_author.website)
                                    existing_author.join_date = profile.get('join_date', existing_author.join_date)
                                    existing_author.is_verified = profile.get('is_verified', existing_author.is_verified)
                                    existing_author.avatar_url = profile.get('avatar_url', existing_author.avatar_url)
                                    existing_author.last_updated = datetime.utcnow()
                                    
                                    session.commit()
                                    
                                    change_info = f" ({followers_change:+,} подписчиков)" if followers_change != 0 else ""
                                    logger.info(f"🔄 Обновлен профиль @{username} в БД ({new_followers:,} подписчиков{change_info})")
                            finally:
                                session.close()
                            
                            # Сохраняем твит
                            db_manager.save_tweet_mention({
                                'mint': query if len(query) > 20 else None,
                                'author_username': username,
                                'tweet_text': author['tweet_text'],
                                'search_query': query,
                                'retweets': author['retweets'],
                                'likes': author['likes'],
                                'replies': author['replies'],
                                'author_followers_at_time': profile.get('followers_count', 0),
                                'author_verified_at_time': profile.get('is_verified', False)
                            })
                        except Exception as e:
                            logger.error(f"❌ Ошибка обновления профиля @{username}: {e}")
                    
                    # Для существующих авторов (с актуальными данными) сохраняем только твит
                    else:
                        try:
                            db_manager.save_tweet_mention({
                                'mint': query if len(query) > 20 else None,
                                'author_username': username,
                                'tweet_text': author['tweet_text'],
                                'search_query': query,
                                'retweets': author['retweets'],
                                'likes': author['likes'],
                                'replies': author['replies'],
                                'author_followers_at_time': profile.get('followers_count', 0),
                                'author_verified_at_time': profile.get('is_verified', False)
                            })
                            logger.info(f"📱 Сохранен твит от автора @{username} (актуальные данные)")
                        except Exception as e:
                            logger.error(f"❌ Ошибка сохранения твита @{username}: {e}")
                else:
                    # Если профиль не загрузился, используем базовые данные
                    logger.warning(f"⚠️ Не удалось загрузить/найти профиль @{username}")
                    author.update({
                        'display_name': f'@{username}',
                        'followers_count': 0,
                        'following_count': 0,
                        'tweets_count': 0,
                        'likes_count': 0,
                        'bio': '',
                        'website': '',
                        'join_date': '',
                        'is_verified': False,
                        'avatar_url': '',
                        'contract_diversity': 0,
                        'max_contract_spam': 0,
                        'diversity_recommendation': 'Профиль недоступен',
                        'is_spam_likely': False,
                        'diversity_category': 'Неизвестно',
                        'spam_analysis': 'Профиль недоступен',
                        'total_contract_tweets': 0,
                        'unique_contracts_count': 0
                    })
                    
                    # Все равно сохраняем твит с базовыми данными
                    try:
                        db_manager.save_tweet_mention({
                            'mint': query if len(query) > 20 else None,
                            'author_username': username,
                            'tweet_text': author['tweet_text'],
                            'search_query': query,
                            'retweets': author['retweets'],
                            'likes': author['likes'],
                            'replies': author['replies'],
                            'author_followers_at_time': 0,
                            'author_verified_at_time': False
                        })
                        logger.info(f"📱 Сохранен твит от автора @{username} (без профиля)")
                    except Exception as e:
                        logger.error(f"❌ Ошибка сохранения твита @{username}: {e}")
        
        # НОВАЯ ФИЛЬТРАЦИЯ: исключаем спамеров и аккаунты с подозрительными метриками
        filtered_authors = []
        excluded_count = 0
        
        for author in unique_authors:
            username = author.get('username', 'Unknown')
            
            # ФИЛЬТР 1 ОТКЛЮЧЕН: Проверка метрик лайков/подписчиков отключена
            # if is_account_suspicious_by_metrics(author):
            #     excluded_count += 1
            #     logger.info(f"🚫 Автор @{username} исключен из результатов - подозрительные метрики")
            #     continue
            
            # УПРОЩЕННАЯ ЛОГИКА: исключаем только чистых спамеров (90%+ контрактов)
            diversity_percent = author.get('contract_diversity', 0)
            spam_percent = author.get('max_contract_spam', 0)
            total_tweets = author.get('total_contract_tweets', 0)
            
            # ПРОСТАЯ ПРОВЕРКА: исключаем только если автор пишет контракты в 90%+ сообщений
            if total_tweets >= 3 and (spam_percent >= 90 or diversity_percent >= 90):
                excluded_count += 1
                logger.info(f"🚫 Автор @{username} исключен - ЧИСТЫЙ СПАМЕР (контракты в {max(spam_percent, diversity_percent):.1f}% сообщений)")
                continue
            
            # Автор прошел упрощенную фильтрацию
            filtered_authors.append(author)
            logger.info(f"✅ Автор @{username} включен в результаты (контракты в {max(spam_percent, diversity_percent):.1f}% сообщений)")
        
        if excluded_count > 0:
            logger.info(f"🎯 УПРОЩЕННАЯ ФИЛЬТРАЦИЯ: исключено {excluded_count} чистых спамеров, оставлено {len(filtered_authors)} авторов")
        else:
            logger.info(f"🎯 УПРОЩЕННАЯ ФИЛЬТРАЦИЯ: все {len(filtered_authors)} авторов прошли проверку")
        
        return filtered_authors
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга авторов: {e}")
        return []

async def twitter_analysis_worker():
    """Фоновый обработчик для анализа Twitter (работает параллельно с основным потоком)"""
    logger.info("🔄 Запущен фоновый обработчик анализа Twitter")
    
    # Счетчики для оптимизации
    consecutive_errors = 0
    batch_mode = False
    
    while True:
        try:
            # Получаем токен из очереди
            token_data = await twitter_analysis_queue.get()
            
            # Проверяем размер очереди для пакетной обработки
            queue_size = twitter_analysis_queue.qsize()
            if queue_size > 15:  # Уменьшено с 50 до 15 токенов
                if not batch_mode:
                    batch_mode = True
                    logger.warning(f"⚡ ПАКЕТНЫЙ РЕЖИМ: очередь {queue_size} токенов - ускоряем обработку")
            elif queue_size < 8:  # Уменьшено с 25 до 8 токенов
                if batch_mode:
                    batch_mode = False
                    logger.info(f"✅ Обычный режим: очередь {queue_size} токенов")
            
            if token_data is None:  # Сигнал для завершения
                break
                
            mint = token_data['mint']
            symbol = token_data['symbol']
            
            logger.info(f"🔍 Начинаем фоновый анализ токена {symbol} в Twitter...")
            
            # Выполняем анализ Twitter с быстрым фолбэком при ошибках
            try:
                twitter_analysis = await analyze_token_sentiment(mint, symbol)
                
                # Проверяем если анализ провалился из-за Nitter проблем
                if twitter_analysis['tweets'] == 0 and twitter_analysis['engagement'] == 0:
                    # Анализируем причины фолбэка на основе error_details из результата анализа
                    fallback_reason = "НЕИЗВЕСТНАЯ ПРИЧИНА"
                    error_details = twitter_analysis.get('error_details', [])
                    
                    if error_details:
                        # Определяем основную причину
                        error_categories = [err['error_category'] for err in error_details]
                        if 'TIMEOUT' in error_categories:
                            fallback_reason = "ТАЙМАУТ (медленный ответ сервера)"
                        elif 'RATE_LIMIT' in error_categories:
                            fallback_reason = "429 ОШИБКА (слишком много запросов)"
                        elif 'BLOCKED' in error_categories:
                            fallback_reason = "БЛОКИРОВКА ('Making sure you're not a bot!')"
                        elif 'CONNECTION' in error_categories:
                            fallback_reason = "ОШИБКА СОЕДИНЕНИЯ (сервер недоступен)"
                        elif 'SYSTEM_ERROR' in error_categories:
                            fallback_reason = "СИСТЕМНАЯ ОШИБКА (внутренняя проблема)"
                        elif 'UNEXPECTED' in error_categories:
                            fallback_reason = "НЕОЖИДАННАЯ ОШИБКА (исключение Python)"
                        else:
                            fallback_reason = f"ОШИБКИ: {', '.join(set(error_categories))}"
                        
                        # Детальное логирование
                        logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol}")
                        logger.warning(f"📋 ПРИЧИНА: {fallback_reason}")
                        for err in error_details:
                            logger.warning(f"   🔸 {err['query']}: {err['error_category']} - {err['error_message']}")
                    else:
                        # Если нет error_details и нет данных - возможно Nitter просто не нашел твиты
                        if twitter_analysis['rating'] == '🔴 Мало внимания':
                            logger.info(f"✅ Токен {symbol} проанализирован - твиты не найдены (норма)")
                        else:
                            logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol} - ПРИЧИНА: {fallback_reason}")
                    
                    # Обновляем analysis без error_details для сохранения в БД
                    twitter_analysis = {
                        'tweets': 0,
                        'symbol_tweets': 0, 
                        'contract_tweets': 0,
                        'engagement': 0,
                        'score': 0,
                        'rating': '🔴 Мало внимания',
                        'contract_found': False,
                        'contract_authors': []
                    }
            except Exception as e:
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ИСКЛЮЧЕНИЙ
                error_type = type(e).__name__
                error_msg = str(e)
                
                logger.error(f"❌ ИСКЛЮЧЕНИЕ при анализе {symbol}: {error_type}")
                logger.error(f"📋 ДЕТАЛИ: {error_msg}")
                
                # Определяем причину исключения
                if "TimeoutError" in error_type:
                    fallback_reason = "ГЛОБАЛЬНЫЙ ТАЙМАУТ (превышено время ожидания)"
                elif "ConnectionError" in error_type:
                    fallback_reason = "ОШИБКА ПОДКЛЮЧЕНИЯ (сеть недоступна)"
                elif "HTTPError" in error_type:
                    fallback_reason = "HTTP ОШИБКА (проблема с сервером)"
                else:
                    fallback_reason = f"СИСТЕМНАЯ ОШИБКА ({error_type})"
                
                logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol}")
                logger.warning(f"📋 ПРИЧИНА: {fallback_reason}")
                
                # Быстрый фолбэк при ошибке
                twitter_analysis = {
                    'tweets': 0,
                    'symbol_tweets': 0,
                    'contract_tweets': 0, 
                    'engagement': 0,
                    'score': 0,
                    'rating': '❓ Ошибка анализа',
                    'contract_found': False,
                    'contract_authors': []
                }
            
            # Сохраняем результат
            twitter_analysis_results[mint] = twitter_analysis
            
            # Обновляем данные в БД
            try:
                db_manager = get_db_manager()
                session = db_manager.Session()
                
                # Ищем токен по mint адресу
                db_token = session.query(Token).filter_by(mint=mint).first()
                if db_token:
                    # Обновляем Twitter данные
                    db_token.twitter_score = twitter_analysis['score']
                    db_token.twitter_rating = twitter_analysis['rating']
                    db_token.twitter_tweets = twitter_analysis['tweets']
                    db_token.twitter_engagement = twitter_analysis['engagement']
                    db_token.twitter_symbol_tweets = twitter_analysis['symbol_tweets']
                    db_token.twitter_contract_tweets = twitter_analysis['contract_tweets']
                    db_token.twitter_contract_found = twitter_analysis['contract_found']
                    db_token.updated_at = datetime.utcnow()
                    
                    session.commit()
                    logger.info(f"✅ Обновлены Twitter данные для токена {symbol} в БД")
                    consecutive_errors = 0  # Сбрасываем счетчик ошибок при успехе
                else:
                    logger.warning(f"⚠️ Токен {symbol} ({mint}) не найден в БД для обновления")
                
                session.close()
                
                # Проверяем нужно ли отправить отложенное уведомление
                if should_send_delayed_notification(twitter_analysis, symbol, mint):
                    await send_delayed_twitter_notification(token_data, twitter_analysis)
                    
                    # ПОМЕЧАЕМ ЧТО УВЕДОМЛЕНИЕ ОТПРАВЛЕНО - избегаем дублирования
                    try:
                        if db_token:
                            db_token.notification_sent = True
                            session.commit()
                            logger.info(f"✅ Помечено уведомление как отправленное для {symbol}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления флага уведомления для {symbol}: {e}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обновления Twitter данных для {symbol}: {e}")
                
            # Помечаем задачу как выполненную
            twitter_analysis_queue.task_done()
            
            # Адаптивные паузы в зависимости от загрузки
            if batch_mode:
                # В пакетном режиме - без пауз
                pass  
            else:
                # В обычном режиме - микропауза для стабильности
                await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в фоновом анализе Twitter: {e}")
            consecutive_errors += 1
            
            # Адаптивная пауза при ошибках
            if consecutive_errors > 5:
                logger.warning(f"⚠️ Много ошибок подряд ({consecutive_errors}) - возможно Nitter недоступен")
                await asyncio.sleep(5)  # Длинная пауза при массовых ошибках
            else:
                await asyncio.sleep(0.5)  # Короткая пауза при единичных ошибках


def reset_analyzing_tokens_timeout():
    """Находит старые токены в статусе анализа и добавляет их обратно в очередь (НЕ сбрасывает рейтинг)"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Находим токены в статусе анализа старше 2 часов (увеличено с 1 часа)
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        
        stuck_tokens = session.query(Token).filter(
            Token.twitter_rating == '⏳ Анализируется...',
            Token.created_at < two_hours_ago
        ).all()
        
        if stuck_tokens:
            logger.warning(f"🔄 Найдено {len(stuck_tokens)} токенов в анализе старше 2 часов")
            
            for token in stuck_tokens:
                logger.info(f"🔄 Повторная постановка в очередь: {token.symbol} (возраст: {datetime.utcnow() - token.created_at})")
                
                # НЕ сбрасываем рейтинг! Добавляем в очередь для анализа
                retry_data = {
                    'mint': token.mint,
                    'symbol': token.symbol,
                    'name': token.name
                }
                
                # Добавляем в глобальную очередь для анализа
                import asyncio
                try:
                    # Если есть активный event loop, используем его
                    loop = asyncio.get_running_loop()
                    loop.create_task(twitter_analysis_queue.put(retry_data))
                    logger.info(f"📋 {token.symbol} добавлен в очередь повторного анализа")
                except RuntimeError:
                    # Если нет активного event loop, просто логируем
                    logger.warning(f"⚠️ {token.symbol} требует повторного анализа (будет обработан при следующем запуске)")
                    
            logger.info(f"✅ Поставлено в очередь {len(stuck_tokens)} токенов для повторного анализа")
        else:
            logger.debug("✅ Нет старых токенов в статусе анализа")
        
        session.close()
        
    except Exception as e:
        logger.error(f"❌ Ошибка повторной постановки токенов в очередь: {e}")


async def emergency_clear_overloaded_queue():
    """ОТКЛЮЧЕНА: Мониторинг перегрузки без удаления токенов"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Считаем токены в анализе
        analyzing_count = session.query(Token).filter(
            Token.twitter_rating == '⏳ Анализируется...'
        ).count()
        
        # Размер очереди в памяти
        queue_size = twitter_analysis_queue.qsize()
        
        logger.info(f"📊 МОНИТОРИНГ ОЧЕРЕДИ:")
        logger.info(f"   📋 В БД (анализируется): {analyzing_count} токенов")
        logger.info(f"   ⏳ В очереди (ожидание): {queue_size} токенов")
        logger.info(f"   🎯 ПОЛИТИКА: анализируем ВСЕ токены, никого не удаляем")
        
        # ТОЛЬКО логирование, НЕ удаляем токены!
        if analyzing_count > 1000:
            logger.warning(f"⚠️ ВЫСОКАЯ НАГРУЗКА: {analyzing_count} токенов в анализе")
            logger.warning(f"📝 РЕКОМЕНДАЦИЯ: дождаться завершения анализа или добавить воркеров")
        
        if queue_size > 60:  # Уменьшено с 200 до 60 токенов - просто предупреждение
            logger.warning(f"📊 БОЛЬШАЯ ОЧЕРЕДЬ: {queue_size} токенов - система продолжает работать")
            
        session.close()
    except Exception as e:
        logger.error(f"❌ Ошибка мониторинга очереди: {e}")

async def check_queue_overload():
    """Мониторинг очереди без экстренной очистки"""
    try:
        queue_size = twitter_analysis_queue.qsize()
        
        # Только мониторинг, без удаления
        if queue_size > 60:  # Уменьшено с 200 до 60 токенов - просто предупреждение
            logger.warning(f"📊 БОЛЬШАЯ ОЧЕРЕДЬ: {queue_size} токенов - система продолжает работать")
            await emergency_clear_overloaded_queue()  # Только для логирования статистики
            
    except Exception as e:
        logger.error(f"❌ Ошибка мониторинга очереди: {e}")


async def check_and_retry_failed_analysis():
    """ОТКЛЮЧЕНА: Мониторинг токенов в анализе без повторного добавления в очередь"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Находим токены в статусе анализа старше 30 минут
        thirty_min_ago = datetime.utcnow() - timedelta(minutes=30)
        
        retry_tokens = session.query(Token).filter(
            Token.twitter_rating == '⏳ Анализируется...',
            Token.created_at < thirty_min_ago
        ).all()
        
        if retry_tokens:
            logger.info(f"📊 МОНИТОРИНГ: {len(retry_tokens)} токенов в анализе более 30 минут")
            
            # Группируем по возрасту для статистики
            old_count = len([t for t in retry_tokens if datetime.utcnow() - t.created_at > timedelta(hours=1)])
            very_old_count = len([t for t in retry_tokens if datetime.utcnow() - t.created_at > timedelta(hours=2)])
            
            logger.info(f"   ⏰ >30мин: {len(retry_tokens)} токенов")
            logger.info(f"   ⏰ >1час: {old_count} токенов") 
            logger.info(f"   ⏰ >2часа: {very_old_count} токенов")
            logger.info(f"   🎯 ПОЛИТИКА: ждем завершения анализа, не дублируем в очереди")
        else:
            logger.debug("✅ Нет токенов в длительном анализе")
        
        session.close()
        
    except Exception as e:
        logger.error(f"❌ Ошибка мониторинга анализа: {e}")


def is_account_suspicious_by_metrics(author):
    """ОТКЛЮЧЕНА: Проверка лайков к подписчикам может быть неточной"""
    username = author.get('username', 'Unknown')
    
    # ОТКЛЮЧЕНО: проверка лайков к подписчикам
    # Эта метрика может быть неточной и исключать валидных авторов
    logger.debug(f"✅ @{username}: проверка метрик отключена - автор принимается")
    
    return False  # Всегда принимаем автора

def is_author_spam_by_analysis(author):
    """Проверяет является ли автор спамером по анализу контрактов"""
    username = author.get('username', 'Unknown')
    
    # Получаем анализ разнообразия контрактов
    try:
        analysis = analyze_author_contract_diversity(username)
        diversity_percent = analysis.get('contract_diversity_percent', 0)
        
        # Если автор определен как спамер
        if analysis.get('is_spam_likely', False):
            recommendation = analysis.get('recommendation', '')
            
            logger.warning(f"🚫 @{username}: СПАМЕР ПО АНАЛИЗУ - {recommendation} (разнообразие: {diversity_percent:.1f}%)")
            return True
            
        # Дополнительная проверка: если слишком много разных контрактов
        if diversity_percent >= 50:  # 50%+ разных контрактов = точно спам
            logger.warning(f"🚫 @{username}: ВЫСОКОЕ РАЗНООБРАЗИЕ КОНТРАКТОВ - {diversity_percent:.1f}% разных контрактов")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка анализа спама для @{username}: {e}")
        return False
    
    return False

def should_notify_based_on_authors_quality(authors):
    """
    УПРОЩЕННАЯ ЛОГИКА: Отправляем уведомления только если есть информация об авторах,
    кроме случаев когда автор отправляет каждое сообщение с контрактом (100% спам)
    """
    if not authors:
        logger.info(f"🚫 Нет информации об авторах твитов - пропускаем уведомление")
        return False  # Нет авторов - НЕ отправляем
    
    pure_spammers = 0  # Авторы которые КАЖДОЕ сообщение пишут с контрактом
    total_authors = len(authors)
    
    for author in authors:
        diversity_percent = author.get('contract_diversity', 0)
        spam_percent = author.get('max_contract_spam', 0)
        total_tweets = author.get('total_contract_tweets', 0)
        username = author.get('username', 'Unknown')
        
        # ПРОСТАЯ ПРОВЕРКА: если автор пишет контракты в 90%+ сообщений = чистый спамер
        if total_tweets >= 3 and (spam_percent >= 90 or diversity_percent >= 90):
            pure_spammers += 1
            logger.info(f"🚫 @{username}: ЧИСТЫЙ СПАМЕР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений")
        else:
            logger.info(f"✅ @{username}: НОРМАЛЬНЫЙ АВТОР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений")
    
    # Блокируем ТОЛЬКО если ВСЕ авторы - чистые спамеры
    should_notify = pure_spammers < total_authors
    
    logger.info(f"📊 УПРОЩЕННЫЙ АНАЛИЗ АВТОРОВ:")
    logger.info(f"   👥 Всего авторов: {total_authors}")
    logger.info(f"   🚫 Чистых спамеров (90%+ контрактов): {pure_spammers}")
    logger.info(f"   ✅ Нормальных авторов: {total_authors - pure_spammers}")
    logger.info(f"   🎯 РЕШЕНИЕ: {'ОТПРАВИТЬ' if should_notify else 'ЗАБЛОКИРОВАТЬ'}")
    
    if not should_notify:
        logger.info(f"🚫 Уведомление заблокировано - ВСЕ авторы являются чистыми спамерами")
    else:
        logger.info(f"✅ Уведомление разрешено - есть нормальные авторы или нет данных об авторах")
    
    return should_notify

def should_send_delayed_notification(twitter_analysis, symbol, mint):
    """
    Проверяет нужно ли отправить отложенное уведомление после анализа Twitter
    ОТПРАВЛЯЕМ если найден контракт с подходящими авторами
    """
    # Проверяем что контракт найден в Twitter
    if not twitter_analysis.get('contract_found', False):
        logger.debug(f"🚫 {symbol}: контракт не найден в Twitter - пропускаем уведомление")
        return False
    
    # Получаем авторов твитов с контрактом
    contract_authors = twitter_analysis.get('contract_authors', [])
    
    # Используем упрощенную логику фильтрации авторов
    should_notify = should_notify_based_on_authors_quality(contract_authors)
    
    if should_notify:
        logger.info(f"✅ {symbol}: найден контракт с подходящими авторами - отправляем уведомление")
    else:
        logger.info(f"🚫 {symbol}: контракт найден, но авторы не подходят - пропускаем уведомление")
    
    return should_notify

async def send_delayed_twitter_notification(token_data, twitter_analysis):
    """Отправляет отложенное уведомление после анализа Twitter"""
    try:
        mint = token_data['mint']
        symbol = token_data['symbol']
        name = token_data.get('name', 'Unknown Token')
        description = token_data.get('description', 'Нет описания')
        market_cap = token_data.get('marketCap', 0)
        
        # Получаем дату создания токена из БД
        db_manager = get_db_manager()
        session = db_manager.Session()
        try:
            db_token = session.query(Token).filter_by(mint=mint).first()
            if db_token and db_token.created_at:
                token_created_at = db_token.created_at.strftime('%Y-%m-%d %H:%M:%S')
            else:
                token_created_at = "Неизвестно"
        except Exception as e:
            logger.error(f"❌ Ошибка получения даты создания токена: {e}")
            token_created_at = "Неизвестно"
        finally:
            session.close()
        
        # Обрезаем описание если слишком длинное
        if len(description) > 200:
            description = description[:200] + "..."
        
        message = (
            f"🚀 <b>КОНТРАКТ НАЙДЕН В TWITTER!</b>\n\n"
            f"<b>💎 {name} ({symbol})</b>\n"
            f"<b>📍 Mint:</b> <code>{mint}</code>\n"
            f"<b>📅 Создан:</b> {token_created_at}\n"
        )
        
        # Добавляем Market Cap только если он больше 0
        if market_cap > 0:
            message += f"<b>💰 Market Cap:</b> ${market_cap:,.0f}\n"
        
        # Добавляем описание только если оно не пустое и не "Нет описания"
        if description and description.strip() and description.strip() != "Нет описания":
            message += f"<b>📝 Описание:</b> {description}\n"
        
        message += (
            f"\n<b>🐦 Twitter анализ:</b> {twitter_analysis['rating']}\n"
            f"<b>📈 Твиты:</b> {twitter_analysis['tweets']} | <b>Активность:</b> {twitter_analysis['engagement']} | <b>Скор:</b> {twitter_analysis['score']}\n"
            f"<b>🔍 Поиск:</b> Символ: {twitter_analysis['symbol_tweets']} | Контракт: {twitter_analysis['contract_tweets']} ✅\n"
        )
        
        # Добавляем информацию об авторах твитов с контрактом
        if twitter_analysis.get('contract_authors'):
            authors = twitter_analysis['contract_authors']
            total_followers = sum([author.get('followers_count', 0) for author in authors])
            verified_count = sum([1 for author in authors if author.get('is_verified', False)])
            
            message += f"\n<b>👥 АВТОРЫ ТВИТОВ С КОНТРАКТОМ ({len(authors)} авторов):</b>\n"
            message += f"   📊 Общий охват: {total_followers:,} подписчиков\n"
            if verified_count > 0:
                message += f"   ✅ Верифицированных: {verified_count}\n"
            message += "\n"
            
            for i, author in enumerate(authors[:3]):  # Показываем максимум 3 авторов
                username = author.get('username', 'Unknown')
                display_name = author.get('display_name', username)
                followers = author.get('followers_count', 0)
                verified = "✅" if author.get('is_verified', False) else ""
                tweet_text = author.get('tweet_text', '')
                tweet_date = author.get('tweet_date', '')
                
                # Информация о спаме контрактов
                diversity_percent = author.get('contract_diversity', 0)
                spam_percent = author.get('max_contract_spam', 0)
                diversity_recommendation = author.get('diversity_recommendation', 'Нет данных')
                spam_analysis = author.get('spam_analysis', 'Нет данных')
                is_spam_likely = author.get('is_spam_likely', False)
                total_contract_tweets = author.get('total_contract_tweets', 0)
                unique_contracts = author.get('unique_contracts_count', 0)
                
                # Эмодзи для статуса автора (высокая концентрация = хорошо)
                spam_indicator = ""
                if spam_percent >= 80:
                    spam_indicator = " 🔥"  # Вспышка активности
                elif spam_percent >= 60:
                    spam_indicator = " ⭐"  # Высокая концентрация
                elif spam_percent >= 40:
                    spam_indicator = " 🟡"  # Умеренная концентрация
                elif is_spam_likely:
                    spam_indicator = " 🚫"  # Много разных контрактов
                
                message += f"{i+1}. <b>@{username}</b> {verified}{spam_indicator}\n"
                if display_name != username:
                    message += f"   📝 {display_name}\n"
                
                # Полная информация о профиле
                following_count = author.get('following_count', 0)
                tweets_count = author.get('tweets_count', 0)
                likes_count = author.get('likes_count', 0)
                join_date = author.get('join_date', '')
                
                if followers > 0 or following_count > 0 or tweets_count > 0:
                    message += f"   👥 {followers:,} подписчиков | {following_count:,} подписок\n"
                    message += f"   📝 {tweets_count:,} твитов | ❤️ {likes_count:,} лайков\n"
                    if join_date:
                        message += f"   📅 Создан: {join_date}\n"
                
                            # Добавляем дату публикации если есть
            if tweet_date:
                message += f"   📅 Опубликован: {tweet_date}\n"
            
            # Добавляем тип твита
            tweet_type = author.get('tweet_type', 'Твит')
            type_emoji = "💬" if tweet_type == "Ответ" else "🐦"
            message += f"   {type_emoji} Тип: {tweet_type}\n"
            
            # Добавляем исторические данные автора
            historical_data = author.get('historical_data', {})
            if historical_data and historical_data.get('total_mentions', 0) > 0:
                total_mentions = historical_data.get('total_mentions', 0)
                unique_tokens = historical_data.get('unique_tokens', 0)
                recent_7d = historical_data.get('recent_mentions_7d', 0)
                recent_30d = historical_data.get('recent_mentions_30d', 0)
                
                message += f"   📊 История: {total_mentions} упоминаний ({unique_tokens} токенов)\n"
                if recent_7d > 0 or recent_30d > 0:
                    message += f"   📈 Активность: {recent_7d} за 7д, {recent_30d} за 30д\n"
                
                # Показываем анализ концентрации контрактов
                if total_contract_tweets > 0:
                    message += f"   📊 Контракты: {unique_contracts} из {total_contract_tweets} твитов (концентрация: {spam_percent:.1f}%)\n"
                    message += f"   🎯 Анализ: {spam_analysis}\n"
                
                # Весь текст твита в цитате
                if tweet_text:
                    message += f"   💬 <blockquote>{tweet_text}</blockquote>\n"
            
            message += "\n"
        
        message += f"⚡ <b>Время действовать!</b>\n"
        message += f"<b>🕐 Время:</b> {datetime.now().strftime('%H:%M:%S')}"
        
        # Кнопки
        bonding_curve_key = token_data.get('bondingCurveKey', mint)
        keyboard = [
            [
                {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/meme/{bonding_curve_key}"},
                {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{mint}"}
            ],
            [
                {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
            ]
        ]
        
        # Получаем URL картинки токена
        token_image_url = f"https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/{mint}.webp"
        
        send_telegram_photo(token_image_url, message, keyboard)
        logger.info(f"📤 Отправлено отложенное уведомление для {symbol}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки отложенного уведомления: {e}")

def analyze_author_contract_diversity(author_username, db_manager=None):
    """
    Анализирует качество автора для pump.fun мониторинга
    ХОРОШИЕ = высокая концентрация на одном контракте (вспышка активности)
    ПЛОХИЕ = много разных контрактов (нет фокуса, низкий интерес)
    """
    if not db_manager:
        db_manager = get_db_manager()
    
    session = db_manager.Session()
    try:
        # Получаем все твиты автора с контрактами
        tweet_mentions = session.query(TweetMention).filter_by(
            author_username=author_username
        ).all()
        
        if not tweet_mentions:
            return {
                'total_tweets': 0,
                'unique_contracts': 0,
                'contract_diversity_percent': 0,
                'max_contract_spam_percent': 0,
                'is_spam_likely': False,
                'recommendation': 'Нет данных о твитах',
                'contracts_list': [],
                'diversity_category': 'Нет данных',
                'spam_analysis': 'Нет данных'
            }
        
        # Извлекаем все контракты из твитов
        all_contracts = set()
        contract_mentions = {}  # контракт -> количество упоминаний
        
        for mention in tweet_mentions:
            # Ищем контракты в тексте твита (адреса длиной 32-44 символа)
            contracts_in_tweet = re.findall(r'\b[A-Za-z0-9]{32,44}\b', mention.tweet_text)
            
            # Также добавляем контракт из поля mint если есть
            if mention.mint:
                contracts_in_tweet.append(mention.mint)
            
            # Добавляем найденные контракты
            for contract in contracts_in_tweet:
                # Проверяем что это похоже на Solana адрес
                if len(contract) >= 32 and contract.isalnum():
                    all_contracts.add(contract)
                    contract_mentions[contract] = contract_mentions.get(contract, 0) + 1
        
        total_tweets = len(tweet_mentions)
        unique_contracts = len(all_contracts)
        
        # Вычисляем ПРАВИЛЬНУЮ концентрацию контрактов
        if total_tweets == 0:
            diversity_percent = 0
            concentration_percent = 0
        else:
            # РАЗНООБРАЗИЕ = уникальные контракты / твиты * 100%
            # Чем больше процент, тем больше разных контрактов (плохо)
            diversity_percent = (unique_contracts / total_tweets) * 100
            
            # КОНЦЕНТРАЦИЯ = 100% - разнообразие
            # Чем выше концентрация, тем меньше разных контрактов (хорошо)
            concentration_percent = 100 - diversity_percent
        
        # ЛОГИКА ДЛЯ PUMP.FUN: Ищем вспышки активности (высокая концентрация = хорошо)
        is_spam_likely = False
        recommendation = "✅ Качественный автор"
        spam_analysis = ""
        
        if unique_contracts == 0:
            recommendation = "⚪ Нет контрактов на странице"
            spam_analysis = "Нет контрактов для анализа"
        elif concentration_percent >= 95:  # ≤5% разных контрактов
            recommendation = "🔥 ОТЛИЧНЫЙ - максимальная концентрация!"
            spam_analysis = f"ВСПЫШКА! {concentration_percent:.1f}% концентрация (только {diversity_percent:.1f}% разных контрактов)"
        elif concentration_percent >= 80:  # ≤20% разных контрактов  
            recommendation = "⭐ ХОРОШИЙ - высокая концентрация"
            spam_analysis = f"Хорошая концентрация: {concentration_percent:.1f}% ({diversity_percent:.1f}% разных контрактов)"
        elif concentration_percent >= 60:  # ≤40% разных контрактов
            recommendation = "🟡 СРЕДНИЙ - умеренная концентрация"
            spam_analysis = f"Умеренная концентрация: {concentration_percent:.1f}% ({diversity_percent:.1f}% разных контрактов)"
        elif diversity_percent >= 80:  # ≥80% разных контрактов
            is_spam_likely = True
            recommendation = "🚫 СПАМЕР - каждый твит новый контракт!"
            spam_analysis = f"СПАМ! {diversity_percent:.1f}% разных контрактов - явный спамер"
        elif diversity_percent >= 50:  # ≥50% разных контрактов
            is_spam_likely = True
            recommendation = "🚫 ПЛОХОЙ - слишком много разных контрактов"
            spam_analysis = f"Низкое качество: {diversity_percent:.1f}% разных контрактов - нет фокуса"
        else:
            # ИСПРАВЛЕННАЯ ЛОГИКА: низкое разнообразие = хорошо
            if diversity_percent <= 30:  # ≤30% разных контрактов = хорошо
                is_spam_likely = False
                recommendation = "🟡 ПРИЕМЛЕМЫЙ - низкое разнообразие контрактов"
                spam_analysis = f"Приемлемо: {diversity_percent:.1f}% разнообразия - низкая концентрация но фокус есть"
            else:
                is_spam_likely = True
                recommendation = "⚠️ ПОДОЗРИТЕЛЬНЫЙ - много разных контрактов"
                spam_analysis = f"Подозрительно: {diversity_percent:.1f}% разнообразия - нет концентрации интереса"
        
        # Топ-5 наиболее упоминаемых контрактов
        top_contracts = sorted(contract_mentions.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_tweets_on_page': total_tweets,
            'unique_contracts_on_page': unique_contracts,
            'contract_diversity_percent': round(diversity_percent, 1),
            'max_contract_spam_percent': round(concentration_percent, 1),
            'is_spam_likely': is_spam_likely,
            'recommendation': recommendation,
            'contracts_list': [{'contract': contract, 'mentions': count} for contract, count in top_contracts],
            'diversity_category': get_diversity_category(concentration_percent),
            'spam_analysis': spam_analysis
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа разнообразия контрактов для @{author_username}: {e}")
        return {
            'total_tweets': 0,
            'unique_contracts': 0,
            'contract_diversity_percent': 0,
            'max_contract_spam_percent': 0,
            'is_spam_likely': False,
            'recommendation': f'Ошибка анализа: {e}',
            'contracts_list': [],
            'diversity_category': 'Ошибка',
            'spam_analysis': f'Ошибка: {e}'
        }
    finally:
        session.close()

def get_diversity_category(concentration_percent):
    """Возвращает категорию качества по концентрации на одном контракте"""
    if concentration_percent >= 80:
        return "🔥 Вспышка активности"
    elif concentration_percent >= 60:
        return "⭐ Высокая концентрация"
    elif concentration_percent >= 40:
        return "🟡 Умеренная концентрация"
    elif concentration_percent >= 20:
        return "🟢 Низкая концентрация"
    else:
        return "⚠️ Нет концентрации"

async def analyze_author_page_contracts(author_username, tweets_on_page=None, load_from_profile=True):
    """
    Анализирует контракты автора на основе ТЕКУЩЕЙ СТРАНИЦЫ твитов или загружает с профиля
    tweets_on_page - список твитов с текущей загруженной страницы (опционально)
    load_from_profile - загружать ли твиты с профиля автора для более точного анализа
    """
    
    # Если нужно загрузить твиты с профиля
    if load_from_profile and (not tweets_on_page or len(tweets_on_page) < 5):
        logger.info(f"🔍 Загружаем твиты с профиля @{author_username} для анализа")
        
        profile_load_failed = False
        network_error = False
        
        try:
            from twitter_profile_parser import TwitterProfileParser
            
            async with TwitterProfileParser() as profile_parser:
                profile_data, profile_tweets = await profile_parser.get_profile_with_tweets(author_username)
                
                if profile_tweets:
                    tweets_on_page = profile_tweets
                    logger.info(f"📱 Загружено {len(profile_tweets)} твитов с профиля @{author_username}")
                else:
                    logger.warning(f"⚠️ Не удалось загрузить твиты с профиля @{author_username}")
                    profile_load_failed = True
                    
        except Exception as e:
            # Проверяем на сетевые ошибки
            if ("Cannot connect to host" in str(e) or 
                "Network is unreachable" in str(e) or
                "Connection timeout" in str(e) or
                "TimeoutError" in str(e) or
                "ClientConnectorError" in str(e)):
                logger.warning(f"🌐 Сетевая ошибка при загрузке твитов @{author_username}: {e}")
                network_error = True
            else:
                logger.error(f"❌ Ошибка загрузки твитов с профиля @{author_username}: {e}")
            profile_load_failed = True
    
    # Обрабатываем случай когда не удалось загрузить твиты
    if not tweets_on_page:
        if network_error:
            # Сетевая ошибка - не помечаем как подозрительного, просто пропускаем
            return {
                'total_tweets_on_page': 0,
                'unique_contracts_on_page': 0,
                'contract_diversity_percent': 0,
                'max_contract_spam_percent': 0,
                'is_spam_likely': False,
                'recommendation': '🌐 Сетевая ошибка - повторить позже',
                'contracts_list': [],
                'diversity_category': 'Сетевая ошибка',
                'spam_analysis': 'Не удалось загрузить из-за сетевой ошибки'
            }
        else:
            # Нет твитов или другая ошибка
            return {
                'total_tweets_on_page': 0,
                'unique_contracts_on_page': 0,
                'contract_diversity_percent': 0,
                'max_contract_spam_percent': 0,
                'is_spam_likely': False,
                'recommendation': 'Нет твитов на странице',
                'contracts_list': [],
                'diversity_category': 'Нет данных',
                'spam_analysis': 'Нет твитов на странице'
            }
    
    # Извлекаем контракты из твитов на странице
    all_contracts = set()
    contract_mentions = {}
    
    for tweet_text in tweets_on_page:
        # Ищем контракты в тексте твита (адреса длиной 32-44 символа)
        contracts_in_tweet = re.findall(r'\b[A-Za-z0-9]{32,44}\b', tweet_text)
        
        for contract in contracts_in_tweet:
            # Проверяем что это похоже на Solana адрес
            if len(contract) >= 32 and contract.isalnum():
                all_contracts.add(contract)
                contract_mentions[contract] = contract_mentions.get(contract, 0) + 1
    
    total_tweets = len(tweets_on_page)
    unique_contracts = len(all_contracts)
    
    # Вычисляем процент разнообразия контрактов
    if total_tweets == 0:
        diversity_percent = 0
        max_contract_spam_percent = 0
    else:
        diversity_percent = (unique_contracts / total_tweets) * 100
        
        # Находим контракт с максимальным количеством упоминаний
        if contract_mentions:
            max_mentions = max(contract_mentions.values())
            max_contract_spam_percent = (max_mentions / total_tweets) * 100
        else:
            max_contract_spam_percent = 0
    
    # ЛОГИКА ДЛЯ PUMP.FUN: Ищем вспышки активности (высокая концентрация = хорошо)
    is_spam_likely = False
    recommendation = "✅ Качественный автор"
    spam_analysis = ""
    
    if unique_contracts == 0:
        recommendation = "⚪ Нет контрактов на странице"
        spam_analysis = "Нет контрактов для анализа"
    elif max_contract_spam_percent >= 80:
        recommendation = "🔥 ОТЛИЧНЫЙ - вспышка активности об одном контракте!"
        spam_analysis = f"ВСПЫШКА! {max_contract_spam_percent:.1f}% твитов об одном контракте - сильный сигнал к покупке"
    elif max_contract_spam_percent >= 60:
        recommendation = "⭐ ХОРОШИЙ - высокая концентрация на контракте"
        spam_analysis = f"Хорошая концентрация: {max_contract_spam_percent:.1f}% на одном контракте - интерес растет"
    elif max_contract_spam_percent >= 40:
        recommendation = "🟡 СРЕДНИЙ - умеренная концентрация"
        spam_analysis = f"Умеренная концентрация: {max_contract_spam_percent:.1f}% на топ-контракте"
    elif diversity_percent >= 80:
        is_spam_likely = True
        recommendation = "🚫 СПАМЕР - каждый твит новый контракт!"
        spam_analysis = f"СПАМ! {diversity_percent:.1f}% разных контрактов на странице - явный спамер"
    elif diversity_percent >= 50:
        is_spam_likely = True
        recommendation = "🚫 ПЛОХОЙ - слишком много разных контрактов"
        spam_analysis = f"Низкое качество: {diversity_percent:.1f}% разных контрактов - нет фокуса"
    else:
        # ИСПРАВЛЕННАЯ ЛОГИКА: низкое разнообразие = хорошо
        if diversity_percent <= 30:  # ≤30% разных контрактов = хорошо
            is_spam_likely = False
            recommendation = "🟡 ПРИЕМЛЕМЫЙ - низкое разнообразие контрактов"
            spam_analysis = f"Приемлемо: {diversity_percent:.1f}% разнообразия - низкая концентрация но фокус есть"
        else:
            is_spam_likely = True
            recommendation = "⚠️ ПОДОЗРИТЕЛЬНЫЙ - много разных контрактов"
            spam_analysis = f"Подозрительно: {diversity_percent:.1f}% разнообразия - нет концентрации интереса"
    
    # Топ-5 наиболее упоминаемых контрактов
    top_contracts = sorted(contract_mentions.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'total_tweets_on_page': total_tweets,
        'unique_contracts_on_page': unique_contracts,
        'contract_diversity_percent': round(diversity_percent, 1),
        'max_contract_spam_percent': round(max_contract_spam_percent, 1),
        'is_spam_likely': is_spam_likely,
        'recommendation': recommendation,
        'contracts_list': [{'contract': contract, 'mentions': count} for contract, count in top_contracts],
        'diversity_category': get_diversity_category(max_contract_spam_percent),
        'spam_analysis': spam_analysis
    }

def should_filter_author_by_diversity(author_username, diversity_threshold=30):
    """
    Проверяет, нужно ли фильтровать автора по разнообразию контрактов
    diversity_threshold - порог в процентах разнообразия, выше которого автор фильтруется (много разных контрактов = плохо)
    """
    analysis = analyze_author_contract_diversity(author_username)
    return analysis['contract_diversity_percent'] >= diversity_threshold

async def main():
    """Основная функция с автоматическим реконнектом"""
    uri = "wss://pumpportal.fun/api/data"
    max_retries = 10
    retry_delay = 5
    retry_count = 0
    first_connection = True
    last_stats_day = None
    last_heartbeat = datetime.now()
    
    # Запускаем фоновый обработчик анализа Twitter
    twitter_worker_task = asyncio.create_task(twitter_analysis_worker())
    
    # Сбрасываем старые "Анализируется..." при запуске
    reset_analyzing_tokens_timeout()
    
    # Запускаем задачу повторного анализа каждые 10 минут
    async def retry_analysis_scheduler():
        while True:
            await asyncio.sleep(600)  # 10 минут
            
            # Проверяем перегрузку очереди
            await check_queue_overload()
            
            # Стандартная очистка
            await check_and_retry_failed_analysis()
            reset_analyzing_tokens_timeout()
    
    retry_task = asyncio.create_task(retry_analysis_scheduler())
    logger.info("🔄 Запущен планировщик повторного анализа")
    logger.info("🔄 Запущен фоновый обработчик анализа Twitter")
    
    # Счетчики для оптимизации
    consecutive_errors = 0
    batch_mode = False
    
    while True:
        try:
            # Настройки WebSocket с улучшенным keepalive
            async with websockets.connect(
                uri,
                ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                ping_timeout=WEBSOCKET_CONFIG['ping_timeout'],
                close_timeout=WEBSOCKET_CONFIG['close_timeout'],
                max_size=WEBSOCKET_CONFIG['max_size'],
                max_queue=WEBSOCKET_CONFIG['max_queue'],
                compression=None,   # Отключаем сжатие для стабильности
                user_agent_header="SolSpider/1.0"  # Идентификация клиента
            ) as websocket:
                logger.info("🌐 Подключен к PumpPortal")
                
                # Инициализируем мониторинг соединения
                connection_monitor.connection_established()
                
                # Подписываемся на новые токены
                subscribe_msg = {"method": "subscribeNewToken"}
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("✅ Подписались на новые токены")
                
                # Подписываемся на миграции
                migrate_msg = {"method": "subscribeMigration"}
                await websocket.send(json.dumps(migrate_msg))
                logger.info("✅ Подписались на миграции")
                
                # Уведомляем о запуске только при первом подключении
                if first_connection:
                    start_message = (
                        "🚀 <b>PUMP.FUN БОТ v3.0 ЗАПУЩЕН!</b>\n\n"
                        "✅ Мониторинг новых токенов БЕЗ ПОТЕРЬ\n"
                        "🔄 Асинхронный Twitter анализ в фоне\n"
                        "⚡ НИКАКОЙ блокировки при анализе\n"
                        "✅ Отслеживание крупных сделок (>5 SOL)\n"
                        "✅ Кнопки для быстрой покупки\n\n"
                        "💎 Ни один токен не будет потерян!"
                    )
                    send_telegram(start_message)
                    first_connection = False
                else:
                    # Уведомление о переподключении
                    send_telegram("🔄 <b>Переподключение успешно!</b>\n✅ Продолжаем мониторинг токенов")
                
                # Сброс счетчика ретраев при успешном подключении
                retry_count = 0
                
                # Слушаем сообщения
                message_count = 0
                async for message in websocket:
                    await handle_message(message)
                    message_count += 1
                    
                    # Обновляем мониторинг
                    connection_monitor.message_received()
                    last_heartbeat = datetime.now()
                    
                    # Проверяем, нужно ли отправить ежедневную статистику
                    current_day = datetime.now().strftime('%Y-%m-%d')
                    current_hour = datetime.now().hour
                    
                    # Отправляем статистику раз в день в 12:00
                    if (last_stats_day != current_day and current_hour >= 12):
                        await send_daily_stats()
                        last_stats_day = current_day
                    
                    # Отправляем статистику соединения каждый час
                    if message_count % 3600 == 0 and message_count > 0:  # Примерно каждый час при активности
                        connection_stats = connection_monitor.format_stats_message()
                        logger.info("📊 Отправляем статистику соединения")
                        send_telegram(connection_stats)
                    
                    # Проверяем здоровье соединения периодически
                    if message_count % WEBSOCKET_CONFIG['health_check_interval'] == 0:
                        current_time = datetime.now()
                        time_since_heartbeat = (current_time - last_heartbeat).total_seconds()
                        
                        # Если долго нет сообщений, проверяем соединение
                        if time_since_heartbeat > WEBSOCKET_CONFIG['heartbeat_check']:
                            logger.info(f"🔍 Проверяем соединение (нет сообщений {time_since_heartbeat:.0f}с)")
                            
                            # Выполняем ping тест через монитор
                            ping_time = await connection_monitor.ping_test(websocket)
                            if ping_time == -1:
                                logger.warning("❌ Соединение нездорово, переподключаемся...")
                                break
                            else:
                                logger.info(f"✅ Ping: {ping_time:.0f}ms - соединение в порядке")
                                last_heartbeat = current_time
                    
        except websockets.exceptions.ConnectionClosed as e:
            # Обновляем статистику мониторинга
            connection_monitor.connection_lost()
            
            if e.code == 1011:
                logger.warning(f"⚠️ Keepalive timeout: {e}")
                # Не отправляем уведомление для обычных keepalive ошибок
            else:
                logger.warning(f"⚠️ Соединение закрыто: {e}")
                send_telegram(f"⚠️ <b>Соединение потеряно</b>\nКод: {e.code}\nПричина: {e.reason}\n🔄 Переподключение...")
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"❌ Неверный статус код: {e}")
            send_telegram(f"❌ <b>Ошибка подключения</b>\nСтатус: {e}")
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"❌ WebSocket ошибка: {e}")
            # Не спамим уведомлениями при частых WebSocket ошибках
            if retry_count <= 3:
                send_telegram(f"❌ <b>WebSocket ошибка</b>\n{e}")
        except ConnectionResetError as e:
            logger.warning(f"⚠️ Соединение сброшено сетью: {e}")
            # Обычная сетевая ошибка, не требует уведомления
        except OSError as e:
            logger.error(f"❌ Системная ошибка сети: {e}")
            if retry_count <= 2:
                send_telegram(f"❌ <b>Сетевая ошибка</b>\n{e}")
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {e}")
            if retry_count <= 1:
                send_telegram(f"❌ <b>Критическая ошибка</b>\n{e}")
        
        # Увеличиваем счетчик попыток
        retry_count = min(retry_count + 1, max_retries)
        
        if retry_count >= max_retries:
            error_msg = "❌ <b>Максимум попыток переподключения достигнут</b>\n⏹️ Бот остановлен"
            logger.error(error_msg)
            send_telegram(error_msg)
            break
        
        logger.info(f"🔄 Мгновенное переподключение... (попытка {retry_count}/{max_retries})")
        # Без задержки - сразу переподключаемся

if __name__ == "__main__":
    asyncio.run(main()) 