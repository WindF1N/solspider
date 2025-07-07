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
from database import get_db_manager, TwitterAuthor, Token, Trade, Migration, TweetMention, DuplicateToken, DuplicatePair
from logger_config import setup_logging, log_token_analysis, log_token_decision, log_trade_activity, log_database_operation, log_daily_stats
from connection_monitor import connection_monitor
# Старая система cookie_rotation удалена - используем только dynamic_cookie_rotation с anubis_handler
from dynamic_cookie_rotation import get_next_proxy_cookie_async
from twitter_profile_parser import TwitterProfileParser
# Новая система групп дубликатов с Google Sheets интеграцией
from duplicate_groups_manager import get_duplicate_groups_manager, initialize_duplicate_groups_manager, shutdown_duplicate_groups_manager


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
    "203504880",
    "230913172"
]

# WebSocket конфигурация
WEBSOCKET_CONFIG = {
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
    '_soleyes',
    'dhnrp68135133',
    'kingpings_',
    'sfckp23567159',
    'officialmj001',
    'alphamegaups'
}
# Очередь для асинхронной обработки анализа Twitter
twitter_analysis_queue = asyncio.Queue()
duplicate_detection_queue = None  # Будет создана в main()
# Словарь для хранения результатов анализа
twitter_analysis_results = {}

# Система обнаружения дубликатов токенов (через базу данных)
duplicate_detection_enabled = os.getenv("DUPLICATE_DETECTION_ENABLED", "true").lower() == "true"
# Отключение поиска контрактов в Twitter (фокус только на шилинге)
contract_search_disabled = os.getenv("CONTRACT_SEARCH_DISABLED", "true").lower() == "true"
duplicate_message_ids = {}  # Словарь {token_id: message_id} для отслеживания первых сообщений о дубликатах

def send_telegram(message, inline_keyboard=None):
    """Отправка сообщения в Telegram группу в тему"""
    # Отправляем в группу в тему вместо отдельных пользователей
    target_chat_id = -1002680160752  # ID группы из https://t.me/c/2680160752/13
    message_thread_id = 13  # ID темы
    
    try:
        payload = {
            "chat_id": target_chat_id,
            "message_thread_id": message_thread_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(TELEGRAM_URL, json=payload)
        if response.status_code == 200:
            logger.info(f"✅ Сообщение отправлено в группу {target_chat_id} в тему {message_thread_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в группу: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в группу: {e}")
        return False

def send_telegram_general(message, inline_keyboard=None):
    """Отправка сообщения в Telegram группу в ОБЩИЙ ЧАТ (без темы)"""
    # Отправляем в общий чат группы без указания темы
    target_chat_id = -1002680160752  # ID группы
    
    try:
        payload = {
            "chat_id": target_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(TELEGRAM_URL, json=payload)
        if response.status_code == 200:
            logger.info(f"✅ Сообщение отправлено в общий чат группы {target_chat_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в общий чат: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в общий чат: {e}")
        return False

def send_telegram_photo(photo_url, caption, inline_keyboard=None):
    """Отправка фото с подписью в Telegram группу в тему"""
    # Отправляем в группу в тему вместо отдельных пользователей
    target_chat_id = -1002680160752  # ID группы из https://t.me/c/2680160752/13
    message_thread_id = 13  # ID темы
    
    try:
        # Сначала пробуем отправить фото
        photo_url_to_send = f"https://cf-ipfs.com/ipfs/{photo_url.split('/')[-1]}" if photo_url and not photo_url.startswith('http') else photo_url
        
        payload = {
            "chat_id": target_chat_id,
            "message_thread_id": message_thread_id,
            "photo": photo_url_to_send,
            "caption": caption,
            "parse_mode": "HTML"
        }
        
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        photo_response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", json=payload)
        
        if photo_response.status_code == 200:
            logger.info(f"✅ Фото отправлено в группу {target_chat_id} в тему {message_thread_id}")
            return True
        else:
            # Если фото не удалось отправить, отправляем обычное сообщение
            logger.warning(f"⚠️ Не удалось отправить фото в группу, отправляю текст: {photo_response.text}")
            text_payload = {
                "chat_id": target_chat_id,
                "message_thread_id": message_thread_id,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            
            if inline_keyboard:
                text_payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
            
            text_response = requests.post(TELEGRAM_URL, json=text_payload)
            if text_response.status_code == 200:
                logger.info(f"✅ Текстовое сообщение отправлено в группу {target_chat_id} в тему {message_thread_id}")
                return True
            else:
                logger.error(f"❌ Ошибка отправки текста в группу: {text_response.text}")
                return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в группу: {e}")
        return False

# send_vip_telegram_photo функция перенесена в vip_twitter_monitor.py

def send_telegram_to_user(message, user_id=7891524244):
    """Отправка сообщения лично пользователю"""
    try:
        payload = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        response = requests.post(TELEGRAM_URL, json=payload)
        if response.status_code == 200:
            logger.info(f"✅ Личное сообщение отправлено пользователю {user_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки личного сообщения: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки личного сообщения: {e}")
        return False


async def search_single_query(query, headers, retry_count=0, use_quotes=False, cycle_cookie=None, session=None):
    """Выполняет одиночный поисковый запрос к Nitter с повторными попытками при 429 и динамическими cookies"""
    # Добавляем пустые параметры since, until, near как требует Nitter
    url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quote(query)}&since=&until=&near="
    
    # Используем только новую динамическую систему куки с anubis_handler
    if session:
        proxy, current_cookie = await get_next_proxy_cookie_async(session)
    else:
        # Если нет сессии, создаем временную для получения куки
        async with aiohttp.ClientSession() as temp_session:
            proxy, current_cookie = await get_next_proxy_cookie_async(temp_session)
    
    # Обновляем заголовки с cookie
    headers_with_cookie = headers.copy()
    headers_with_cookie['Cookie'] = current_cookie
    
    current_session = None
    session_created_locally = False
    
    try:
        # Настройка прокси если требуется
        connector = None
        request_kwargs = {}
        if proxy:
            try:
                # Пробуем новый API (aiohttp 3.8+)
                connector = aiohttp.ProxyConnector.from_url(proxy)
                proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                logger.debug(f"🌐 [DYNAMIC] Используем прокси через ProxyConnector: {proxy_info}")
            except AttributeError:
                # Для aiohttp 3.9.1 - прокси передается напрямую в get()
                connector = aiohttp.TCPConnector()
                request_kwargs['proxy'] = proxy
                proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                logger.debug(f"🌐 [DYNAMIC] Используем прокси напрямую: {proxy_info}")
        
        # Используем переданную сессию или создаем новую
        if session:
            current_session = session
        else:
            current_session = aiohttp.ClientSession(connector=connector)
            session_created_locally = True
        
        try:
            async with current_session.get(url, headers=headers_with_cookie, timeout=20, **request_kwargs) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Проверяем на блокировку Nitter (современный Anubis challenge)
                    title = soup.find('title')
                    has_challenge_text = title and 'Making sure you\'re not a bot!' in title.get_text()
                    has_anubis_script = 'id="anubis_challenge"' in html
                    
                    if has_challenge_text or has_anubis_script:
                        logger.warning(f"🤖 Обнаружен Anubis challenge для '{query}', пытаемся решить автоматически...")
                        
                        # Попытка автоматического решения challenge
                        try:
                            from anubis_handler import handle_anubis_challenge_for_session
                            
                            new_cookies = await handle_anubis_challenge_for_session(
                                current_session, 
                                str(response.url), 
                                html
                            )
                            
                            if new_cookies:
                                # Обновляем куки в заголовках
                                updated_cookie = "; ".join([f"{name}={value}" for name, value in new_cookies.items()])
                                headers_with_cookie['Cookie'] = updated_cookie
                                
                                logger.info(f"✅ Challenge решен для '{query}', повторяем запрос с новыми куки")
                                
                                # Повторяем запрос с новыми куки
                                async with current_session.get(url, headers=headers_with_cookie, timeout=20, **request_kwargs) as retry_response:
                                    if retry_response.status == 200:
                                        retry_html = await retry_response.text()
                                        retry_soup = BeautifulSoup(retry_html, 'html.parser')
                                        
                                        # Проверяем что challenge больше нет
                                        retry_title = retry_soup.find('title')
                                        retry_has_challenge_text = retry_title and 'Making sure you\'re not a bot!' in retry_title.get_text()
                                        retry_has_anubis_script = 'id="anubis_challenge"' in retry_html
                                        
                                        if retry_has_challenge_text or retry_has_anubis_script:
                                            logger.error(f"❌ Challenge не решен для '{query}' - требует дополнительной настройки")
                                            return []
                                        
                                        logger.info(f"🎉 Поисковая страница доступна для '{query}' после решения challenge")
                                        # Продолжаем с retry_soup вместо soup
                                        soup = retry_soup
                                        html = retry_html
                                    else:
                                        logger.error(f"❌ Ошибка повторного запроса для '{query}': {retry_response.status}")
                                        return []
                            else:
                                logger.error(f"❌ Не удалось решить challenge для '{query}'")
                                
                                # Отправляем уведомление только если автоматическое решение не помогло
                                alert_message = (
                                    f"🚫 <b>ОШИБКА ANUBIS CHALLENGE!</b>\n\n"
                                    f"🤖 <b>Не удалось решить challenge автоматически</b>\n"
                                    f"📍 <b>Запрос:</b> {query}\n"
                                    f"⚠️ <b>Статус:</b> 'Making sure you're not a bot!'\n\n"
                                    f"🛠️ <b>Возможные причины:</b>\n"
                                    f"1. Изменился алгоритм challenge\n"
                                    f"2. Нужны дополнительные куки\n"
                                    f"3. Блокировка IP адреса\n\n"
                                    f"❌ <b>Twitter анализ недоступен!</b>"
                                )
                                send_telegram_to_user(alert_message)
                                return []
                                
                        except Exception as challenge_error:
                            logger.error(f"❌ Ошибка решения challenge для '{query}': {challenge_error}")
                            
                            # Отправляем уведомление об ошибке
                            alert_message = (
                                f"🚫 <b>ОШИБКА РЕШЕНИЯ CHALLENGE!</b>\n\n"
                                f"📍 <b>Запрос:</b> {query}\n"
                                f"❌ <b>Ошибка:</b> {str(challenge_error)}\n\n"
                                f"🛠️ <b>Требуется проверка системы</b>\n"
                                f"❌ <b>Twitter анализ недоступен!</b>"
                            )
                            send_telegram_to_user(alert_message)
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
                                'authors': authors_data if is_contract_query else [],
                                'html': tweet  # Сохраняем HTML для дальнейшего использования
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
                        return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie, session)
                    else:
                        # После 2 попыток помещаем прокси в спячку на минуту вместо полной блокировки
                        from dynamic_cookie_rotation import mark_proxy_temp_blocked
                        mark_proxy_temp_blocked(proxy, current_cookie, 1)
                        logger.warning(f"😴 Прокси помещен в спячку на 1 минуту после 429 ошибок для '{query}'")
                        return []
                else:
                    logger.warning(f"❌ Nitter ответил {response.status} для '{query}'")
                    return []
        except Exception as e:
            # Обрабатываем ошибки HTTP запроса
            logger.error(f"❌ Ошибка HTTP запроса для '{query}': {e}")
            raise  # Поднимаем исключение для обработки во внешнем блоке
                    
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
            return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie, session)
        else:
            logger.error(f"❌ Превышено количество попыток для '{query}' после {error_category} - возвращаем пустой результат")
            # Возвращаем информацию об ошибке для анализа
            return {"error": error_category, "message": error_msg, "type": error_type}
    finally:
        # Закрываем сессию если она была создана локально
        if session_created_locally and current_session:
            await current_session.close()

def extract_next_page_url(soup):
    """Извлекает URL следующей страницы из кнопки 'Load more'"""
    try:
        show_more = soup.find('div', class_='show-more')
        if show_more:
            link = show_more.find('a')
            if link and 'href' in link.attrs:
                return link['href']
        return None
    except Exception as e:
        logger.debug(f"Ошибка извлечения URL следующей страницы: {e}")
        return None

def ensure_nitter_params(url):
    """Гарантирует наличие пустых параметров since, until, near в Nitter URL"""
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Добавляем пустые параметры если их нет
        if 'since' not in query_params:
            query_params['since'] = ['']
        if 'until' not in query_params:
            query_params['until'] = ['']
        if 'near' not in query_params:
            query_params['near'] = ['']
        
        # Пересобираем URL
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
        
    except Exception as e:
        logger.debug(f"Ошибка обработки URL параметров: {e}")
        return url

async def search_with_pagination(query, headers, max_pages=3, cycle_cookie=None, session=None):
    """Выполняет поиск с пагинацией, проходя по всем доступным страницам с динамическими куки"""
    try:
        all_tweets = []
        all_authors = []
        page_count = 0
        current_url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quote(query)}&since=&until=&near="
        
        # Используем только новую динамическую систему куки с anubis_handler
        if session:
            proxy, current_cookie = await get_next_proxy_cookie_async(session)
        else:
            # Если нет сессии, создаем временную для получения куки
            async with aiohttp.ClientSession() as temp_session:
                proxy, current_cookie = await get_next_proxy_cookie_async(temp_session)

        # Обновляем заголовки с cookie
        headers_with_cookie = headers.copy()
        headers_with_cookie['Cookie'] = current_cookie
        
        # Настройка соединения (прокси или без прокси)
        connector = aiohttp.TCPConnector(ssl=False)
        request_kwargs = {}
        if proxy:
            request_kwargs['proxy'] = proxy
            
        logger.info(f"🔄 Начинаем поиск с пагинацией для '{query}' (до {max_pages} страниц)")
        
        # Используем переданную сессию или создаем новую
        if session:
            current_session = session
        else:
            current_session = aiohttp.ClientSession(connector=connector)
        
        try:
            while page_count < max_pages and current_url:
                page_count += 1
                logger.info(f"📄 Загружаем страницу {page_count}/{max_pages} для '{query}'")
                
                try:
                    async with current_session.get(current_url, headers=headers_with_cookie, timeout=20, **request_kwargs) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Проверяем на блокировку Nitter (современный Anubis challenge)
                            title = soup.find('title')
                            has_challenge_text = title and 'Making sure you\'re not a bot!' in title.get_text()
                            has_anubis_script = 'id="anubis_challenge"' in html
                            
                            if has_challenge_text or has_anubis_script:
                                logger.warning(f"🤖 Обнаружен Anubis challenge на странице {page_count} для '{query}', пытаемся решить автоматически...")
                                
                                # Попытка автоматического решения challenge
                                try:
                                    from anubis_handler import handle_anubis_challenge_for_session
                                    
                                    new_cookies = await handle_anubis_challenge_for_session(
                                        current_session, 
                                        str(response.url), 
                                        html
                                    )
                                    
                                    if new_cookies:
                                        # Обновляем куки в заголовках
                                        updated_cookie = "; ".join([f"{name}={value}" for name, value in new_cookies.items()])
                                        headers_with_cookie['Cookie'] = updated_cookie
                                        
                                        logger.info(f"✅ Challenge решен на странице {page_count} для '{query}', повторяем запрос с новыми куки")
                                        
                                        # Повторяем запрос с новыми куки
                                        async with current_session.get(current_url, headers=headers_with_cookie, timeout=20, **request_kwargs) as retry_response:
                                            if retry_response.status == 200:
                                                retry_html = await retry_response.text()
                                                retry_soup = BeautifulSoup(retry_html, 'html.parser')
                                                
                                                # Проверяем что challenge больше нет
                                                retry_title = retry_soup.find('title')
                                                retry_has_challenge_text = retry_title and 'Making sure you\'re not a bot!' in retry_title.get_text()
                                                retry_has_anubis_script = 'id="anubis_challenge"' in retry_html
                                                
                                                if retry_has_challenge_text or retry_has_anubis_script:
                                                    logger.error(f"❌ Challenge не решен на странице {page_count} для '{query}' - прерываем пагинацию")
                                                    break
                                                
                                                logger.info(f"🎉 Страница {page_count} доступна для '{query}' после решения challenge")
                                                # Продолжаем с retry_soup вместо soup
                                                soup = retry_soup
                                                html = retry_html
                                            else:
                                                if retry_response.status == 429:
                                                    # При 429 ошибке помещаем прокси в спячку на минуту
                                                    from dynamic_cookie_rotation import mark_proxy_temp_blocked
                                                    mark_proxy_temp_blocked(proxy, current_cookie, 1)
                                                    logger.warning(f"😴 Прокси помещен в спячку на 1 минуту из-за 429 ошибки при повторном запросе страницы {page_count} для '{query}'")
                                                else:
                                                    logger.error(f"❌ Ошибка повторного запроса страницы {page_count} для '{query}': {retry_response.status}")
                                                break
                                    else:
                                        logger.error(f"❌ Не удалось решить challenge на странице {page_count} для '{query}' - прерываем пагинацию")
                                        break
                                        
                                except Exception as challenge_error:
                                    logger.error(f"❌ Ошибка решения challenge на странице {page_count} для '{query}': {challenge_error}")
                                    # Отправляем уведомление об ошибке
                                    alert_message = (
                                        f"🚫 <b>ОШИБКА РЕШЕНИЯ CHALLENGE!</b>\n\n"
                                        f"📍 <b>Запрос:</b> {query}\n"
                                        f"❌ <b>Ошибка:</b> {str(challenge_error)}\n\n"
                                        f"🛠️ <b>Требуется проверка системы</b>\n"
                                        f"❌ <b>Twitter анализ недоступен!</b>"
                                    )
                                    send_telegram_to_user(alert_message)
                                    return []
                                
                            # Находим все твиты на текущей странице
                            tweets = soup.find_all('div', class_='timeline-item')
                            # Исключаем элементы show-more и top-ref
                            tweets = [t for t in tweets if not t.find('div', class_='show-more') and not t.find('div', class_='top-ref')]
                            
                            page_tweet_count = len(tweets)
                            logger.info(f"📱 Страница {page_count}: найдено {page_tweet_count} твитов")
                            
                            # Проверяем, это запрос по контракту (длинная строка)
                            is_contract_query = len(query) > 20
                            
                            # Парсим авторов если найдены твиты по контракту
                            page_authors = []
                            if is_contract_query and page_tweet_count > 0:
                                page_authors = await extract_tweet_authors(soup, query, True)
                                all_authors.extend(page_authors)
                                logger.info(f"👥 Страница {page_count}: найдено {len(page_authors)} авторов")
                            
                            # Обрабатываем твиты текущей страницы
                            for tweet in tweets:
                                # Извлекаем уникальные данные твита
                                tweet_link = tweet.find('a', class_='tweet-link')
                                tweet_time = tweet.find('span', class_='tweet-date')
                                tweet_text = tweet.find('div', class_='tweet-content')
                                
                                tweet_id = None
                                if tweet_link and 'href' in tweet_link.attrs:
                                    tweet_id = tweet_link['href']
                                elif tweet_time and tweet_text:
                                    time_text = tweet_time.get_text(strip=True) if tweet_time else ""
                                    content_text = tweet_text.get_text(strip=True)[:50] if tweet_text else ""
                                    tweet_id = f"{time_text}_{hash(content_text)}"
                                
                                if tweet_id:
                                    # Анализируем активность твита
                                    engagement = 0
                                    stats = tweet.find_all('span', class_='tweet-stat')
                                    for stat in stats:
                                        icon_container = stat.find('div', class_='icon-container')
                                        if icon_container:
                                            text = icon_container.get_text(strip=True)
                                            numbers = re.findall(r'\d+', text)
                                            if numbers:
                                                engagement += int(numbers[0])
                                    
                                    all_tweets.append({
                                        'id': tweet_id,
                                        'engagement': engagement,
                                        'authors': page_authors if is_contract_query else [],
                                        'page': page_count
                                    })
                            
                            # Ищем ссылку на следующую страницу
                            next_page_url = extract_next_page_url(soup)
                            if next_page_url and page_count < max_pages:
                                # Формируем полный URL
                                if next_page_url.startswith('?'):
                                    current_url = f"https://nitter.tiekoetter.com/search{next_page_url}"
                                elif next_page_url.startswith('/search'):
                                    current_url = f"https://nitter.tiekoetter.com{next_page_url}"
                                else:
                                    current_url = next_page_url
                                
                                # Гарантируем наличие пустых параметров since, until, near
                                current_url = ensure_nitter_params(current_url)
                                
                                logger.debug(f"🔗 Следующая страница: {current_url}")
                                
                                # Пауза между страницами
                                await asyncio.sleep(0.5)
                            else:
                                logger.info(f"📄 Больше страниц нет или достигнут лимит для '{query}'")
                                break
                                
                        elif response.status == 429:
                            # При 429 ошибке помещаем прокси в спячку на минуту
                            from dynamic_cookie_rotation import mark_proxy_temp_blocked
                            mark_proxy_temp_blocked(proxy, current_cookie, 1)
                            logger.warning(f"😴 Прокси помещен в спячку на 1 минуту из-за 429 ошибки на странице {page_count} для '{query}' - останавливаем пагинацию")
                            break
                        else:
                            logger.warning(f"❌ Nitter ответил {response.status} на странице {page_count} для '{query}'")
                            break
                            
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки страницы {page_count} для '{query}': {e}")
                    break
        except Exception as e:
            # Обрабатываем ошибки внутреннего try блока  
            logger.error(f"❌ Ошибка сессии для '{query}': {e}")
            return [], []
        
        # Дедупликация твитов
        unique_tweets = {}
        for tweet in all_tweets:
            tweet_id = tweet['id']
            if tweet_id in unique_tweets:
                # Берем максимальную активность
                unique_tweets[tweet_id]['engagement'] = max(
                    unique_tweets[tweet_id]['engagement'], 
                    tweet['engagement']
                )
            else:
                unique_tweets[tweet_id] = tweet
        
        final_tweets = list(unique_tweets.values())
        logger.info(f"🎯 Пагинация завершена для '{query}': {len(final_tweets)} уникальных твитов с {page_count} страниц")
        
        return final_tweets, all_authors
                
    except Exception as e:
        logger.error(f"❌ Ошибка поиска с пагинацией для '{query}': {e}")
        return [], []

async def analyze_token_sentiment(mint, symbol, cycle_cookie=None, session=None):
    """Анализ упоминаний токена в Twitter через Nitter с динамическими куки (2 запроса без кавычек с дедупликацией)"""
    # Создаем сессию если она не передана
    if not session:
        session = aiohttp.ClientSession()
        session_created_locally = True
    else:
        session_created_locally = False
    
    try:
        # Получаем один cookie для всего анализа токена (2 запроса) - только новая динамическая система
        if not cycle_cookie:
            if session:
                # Используем новую динамическую систему
                _, cycle_cookie = await get_next_proxy_cookie_async(session)
                logger.debug(f"🍪 [DYNAMIC] Получили динамическую связку для анализа токена {symbol}")
            else:
                # Если нет сессии, создаем временную для получения куки
                async with aiohttp.ClientSession() as temp_session:
                    _, cycle_cookie = await get_next_proxy_cookie_async(temp_session)
                    logger.debug(f"🍪 [DYNAMIC] Получили динамическую связку через временную сессию для анализа токена {symbol}")
            
        # Базовые заголовки без cookie (cookie будет добавлен в search_single_query)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 2 запроса: символ (обычный поиск) и контракт (с кавычками и пагинацией)
        search_queries = [
            (f'${symbol}', False, False),  # Символ без кавычек, без пагинации
        ]
        
        # В режиме шилинга (CONTRACT_SEARCH_DISABLED=true) поиск контрактов отключен
        import os
        contract_search_disabled = os.getenv('CONTRACT_SEARCH_DISABLED', 'false').lower() == 'true'
        
        if not contract_search_disabled:
            search_queries.append((f'"{mint}"', False, True))  # Контракт В КАВЫЧКАХ, с пагинацией для точного поиска
            logger.debug(f"🔍 {symbol}: поиск символа + контракта (полный режим)")
        else:
            logger.info(f"🎯 {symbol}: поиск только символа - режим шилинга активен (CONTRACT_SEARCH_DISABLED=true)")
        
        # Выполняем запросы последовательно с паузами для избежания блокировки
        results = []
        all_contract_authors = []
        error_details = []
        for i, (query, use_quotes, use_pagination) in enumerate(search_queries):
            try:
                if use_pagination:
                    # Для контрактов используем пагинацию (до 3 страниц)
                    result, authors = await search_with_pagination(query, headers, max_pages=3, cycle_cookie=cycle_cookie, session=session)
                    all_contract_authors.extend(authors)
                    logger.info(f"📄 Пагинация для '{query}': {len(result)} твитов, {len(authors)} авторов")
                else:
                    # Для символов используем обычный поиск
                    result = await search_single_query(query, headers, use_quotes=use_quotes, cycle_cookie=cycle_cookie, session=session)
                
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
                results.append([])
        
        # Собираем все твиты в один словарь для дедупликации
        all_tweets = {}
        symbol_tweets_count = 0
        contract_tweets_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception) or not result:
                continue
                
            for tweet_data in result:
                tweet_id = tweet_data['id']
                engagement = tweet_data['engagement']
                
                # Если твит уже есть, берем максимальное значение активности
                if tweet_id in all_tweets:
                    all_tweets[tweet_id] = max(all_tweets[tweet_id], engagement)
                else:
                    all_tweets[tweet_id] = engagement
                    
                    # Подсчитываем уникальные твиты по категориям
                    if i == 0:  # Первый запрос - символ
                        symbol_tweets_count += 1
                    elif len(search_queries) > 1 and i == 1:  # Второй запрос - контракт (только если не отключен)
                        contract_tweets_count += 1
        
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
            'contract_authors': all_contract_authors,
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
    finally:
        # Закрываем сессию если она была создана локально
        if session_created_locally and session:
            await session.close()

async def format_new_token(data):
    """Форматирование сообщения о новом токене с быстрым сохранением и фоновым анализом Twitter"""
    mint = data.get('mint', 'Unknown')
    name = data.get('name', 'Unknown Token')
    symbol = data.get('symbol', 'UNK')
    description = data.get('description', 'Нет описания')
    creator = data.get('traderPublicKey', 'Unknown')
    
    # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ НАЧАЛА АНАЛИЗА ТОКЕНА ===
    log_token_decision("🚀 НОВЫЙ_ТОКЕН_ОБНАРУЖЕН", symbol, mint, 
                      f"Название: '{name}' | DEX: {data.get('dex', 'Unknown')} | "
                      f"MC: ${data.get('marketCap', 0):,.0f} | "
                      f"Создатель: {creator[:8]}... | "
                      f"Twitter: {data.get('twitter', 'Отсутствует')}")
    
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
    
    # ОТКЛЮЧЕН: Twitter анализ больше не нужен, используем только дубликаты
    logger.info(f"🚫 Twitter анализ отключен для {symbol} - анализируем только дубликаты")
    
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
    
    # Получаем реальную дату создания токена из Jupiter API
    token_created_at = "N/A"
    first_pool = data.get('firstPool', {})
    if first_pool and first_pool.get('createdAt'):
        try:
            # Парсим дату из Jupiter API (формат: '2025-06-30T01:47:45Z')
            created_at_str = first_pool.get('createdAt')
            if created_at_str.endswith('Z'):
                created_at_str = created_at_str[:-1]
            
            # Используем datetime класс из импорта
            created_datetime = datetime.fromisoformat(created_at_str)
            token_created_at = created_datetime.strftime('%d.%m.%Y %H:%M:%S')
        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга даты создания токена: {e}")
            token_created_at = datetime.now().strftime('%d.%m.%Y %H:%M:%S')  # Fallback
    else:
        # Если нет данных о дате создания - используем текущее время
        token_created_at = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    
    # Определяем источник и заголовок
    dex_source = data.get('dex_source', 'pump.fun')
    pool_type = data.get('pool_type', 'pumpfun')
    
    if dex_source != 'pump.fun':
        header = f"🚀 <b>НОВЫЙ ТОКЕН через {dex_source.upper()}!</b>\n\n"
        token_url = f"https://jup.ag/swap/SOL-{mint}"  # Jupiter URL
    else:
        header = f"🚀 <b>НОВЫЙ ТОКЕН НА PUMP.FUN!</b>\n\n"
        token_url = f"https://pump.fun/{mint}"
    
    message = (
        header +
        f"<b>💎 <a href='{token_url}'>{name}</a></b>\n"
        f"<b>🏷️ Символ:</b> {symbol}\n"
        f"<b>📍 Mint:</b> <code>{mint}</code>\n"
        f"<b>🌐 Источник:</b> {dex_source} ({pool_type})\n"
        f"<b>👤 Создатель:</b> <code>{creator[:8] if len(creator) > 8 else creator}...</code>\n"
        f"<b>📅 Создан:</b> {token_created_at}\n"
    )
    
    # Добавляем начальную покупку только для pump.fun
    if initial_buy > 0:
        message += f"<b>💰 Начальная покупка:</b> {initial_buy} SOL\n"
    
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
            {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/t/{mint}"},
            {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{mint}"}
        ],
        [
            {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
        ]
    ]
    
    # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ФИЛЬТРАЦИИ ===
    log_token_decision("📊 НАЧАЛО_ФИЛЬТРАЦИИ", symbol, mint, 
                      f"MC: ${data.get('marketCap', 0):,.0f} | "
                      f"Pool: {data.get('pool_type', 'Unknown')} | "
                      f"Initial Buy: {data.get('initialBuy', 0)} SOL")
    
    # НОВАЯ ЛОГИКА: только дубликаты, никаких уведомлений
    # Уведомления отправляются только через duplicate_groups_manager
    immediate_notify = False  # ОТКЛЮЧАЕМ все уведомления - используем только дубликаты
    
    log_token_decision("🔍 ТОЛЬКО_ДУБЛИКАТЫ", symbol, mint, 
                      "Токен сохранен в БД, анализируем только дубликаты. "
                      "Уведомления отправляются только через duplicate_groups_manager.")
    
    # Все токены сохраняются в БД и добавляются в систему дубликатов
    logger.info(f"⚡ Токен {symbol} - сохранен, анализ дубликатов запущен")
    
    should_notify = immediate_notify
    
    log_token_decision("🚫 РЕШЕНИЕ_НЕМЕДЛЕННОЕ_УВЕДОМЛЕНИЕ", symbol, mint, 
                      f"should_notify = {should_notify} (ВСЕГДА FALSE - используем только дубликаты)")
    
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
            {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/t/{mint}"},
            {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{mint}"}
        ],
        [
            {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
        ]
    ]
    
    return message, keyboard

async def execute_auto_purchase_new_token(mint, symbol, token_name):
    """Выполняет автоматическую покупку нового токена"""
    try:
        logger.info(f"💰 АВТОПОКУПКА НОВОГО ТОКЕНА: {symbol} ({mint[:8]}...)")
        
        # Импортируем axiom_trader
        from axiom_trader import execute_axiom_purchase
        
        # Параметры автопокупки
        auto_buy_amount = 0.0001  # 0.0001 SOL
        
        # Импортируем функцию газа
        try:
            from vip_config import get_gas_fee, get_gas_description
            gas_fee = get_gas_fee('new_tokens')
            gas_desc = get_gas_description('new_tokens')
            logger.info(f"⚡ Газ для нового токена: {gas_desc}")
        except ImportError:
            gas_fee = 0.001  # Fallback значение
        
        # Выполняем покупку через Axiom
        result = await execute_axiom_purchase(
            contract_address=mint,
            twitter_username="SolSpider_AutoBuy",
            tweet_text=f"Автоматическая покупка нового токена {token_name} ({symbol})",
            sol_amount=auto_buy_amount,
            slippage=15,
            priority_fee=gas_fee  # Оптимизированный газ для новых токенов
        )
        
        if result.get('success', False):
            logger.info(f"✅ Автопокупка {symbol} успешна! TX: {result.get('tx_hash', 'N/A')[:16]}...")
            
            # Отправляем уведомление об успешной покупке
            purchase_msg = (
                f"💰 <b>АВТОПОКУПКА ВЫПОЛНЕНА!</b>\n\n"
                f"🪙 <b>{token_name}</b> ({symbol})\n"
                f"📍 <b>Mint:</b> <code>{mint}</code>\n"
                f"⚡ <b>Сумма:</b> {auto_buy_amount} SOL\n"
                f"🔗 <b>TX:</b> <code>{result.get('tx_hash', 'N/A')}</code>\n"
                f"⏱️ <b>Время:</b> {result.get('execution_time', 0):.2f}с"
            )
            
            # Создаем клавиатуру с ссылками
            keyboard = [
                [
                    {"text": "💎 Axiom.trade", "url": f"https://axiom.trade/t/{mint}"},
                    {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
                ],
                [{"text": "🚀 Pump.fun", "url": f"https://pump.fun/{mint}"}]
            ]
            
            send_telegram(purchase_msg, keyboard)
            
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ Ошибка автопокупки {symbol}: {error_msg}")
            
            # Отправляем уведомление об ошибке
            error_notification = (
                f"❌ <b>ОШИБКА АВТОПОКУПКИ</b>\n\n"
                f"🪙 <b>{token_name}</b> ({symbol})\n"
                f"📍 <b>Mint:</b> <code>{mint}</code>\n"
                f"⚠️ <b>Ошибка:</b> {error_msg[:100]}\n"
                f"⚡ <b>Сумма:</b> {auto_buy_amount} SOL"
            )
            
            send_telegram(error_notification)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка автопокупки {symbol}: {e}")
        
        # Отправляем уведомление о критической ошибке
        critical_error_msg = (
            f"🚫 <b>КРИТИЧЕСКАЯ ОШИБКА АВТОПОКУПКИ</b>\n\n"
            f"🪙 <b>{token_name}</b> ({symbol})\n"
            f"📍 <b>Mint:</b> <code>{mint}</code>\n"
            f"❌ <b>Ошибка:</b> {str(e)[:100]}"
        )
        
        send_telegram(critical_error_msg)
        
        return {
            'success': False,
            'error': f'Critical error: {str(e)}',
            'execution_time': 0
        }

async def handle_message(message):
    """Обработка сообщений Jupiter WebSocket"""
    try:
        data = json.loads(message)
        logger.debug(f"Jupiter получено: {json.dumps(data, indent=2)[:200]}...")
        
        # Jupiter возвращает структуру {"type": "updates", "data": [...]}
        if data.get('type') == 'updates' and 'data' in data:
            updates = data['data']
            
            for update in updates:
                # Проверяем тип обновления
                update_type = update.get('type')
                pool_data = update.get('pool', {})
                
                if update_type == 'new' and pool_data:
                    # Это новый токен/пул
                    await handle_new_jupiter_token(pool_data)
                    
                elif update_type == 'update' and pool_data:
                    # Это обновление существующего пула (возможные торговые операции)
                    await handle_jupiter_pool_update(pool_data)
                    
        # Также проверяем на старый формат pump.fun (для совместимости)
        elif 'mint' in data and 'name' in data and 'symbol' in data:
            # Старый формат pump.fun - обрабатываем как раньше
            await handle_legacy_pumpfun_token(data)
            
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON от Jupiter: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки Jupiter сообщения: {e}")

async def handle_new_jupiter_token(pool_data):
    """Обработка нового токена от Jupiter"""
    try:
        # Извлекаем данные о токене
        pool_id = pool_data.get('id', 'Unknown')
        dex = pool_data.get('dex', 'Unknown')
        pool_type = pool_data.get('type', 'Unknown')
        base_asset = pool_data.get('baseAsset', {})
        
        # Основные данные токена
        mint = base_asset.get('id', pool_id)  # Иногда mint = pool_id
        symbol = base_asset.get('symbol', 'Unknown')
        name = base_asset.get('name', symbol)
        dev_address = base_asset.get('dev', 'Unknown')

        logger.info(base_asset)
        
        # Дополнительная информация
        market_cap = base_asset.get('marketCap', 0)
        created_timestamp = pool_data.get('createdTimestamp')
        
        logger.info(f"🚀 НОВЫЙ ТОКЕН через {dex}: {name} ({symbol}) - {mint[:8]}...")
        logger.info(f"   📊 Тип: {pool_type}, Market Cap: ${market_cap:,.2f}")
        
        # DEBUG: Проверяем наличие Twitter у токена перед фильтрацией
        twitter_url = base_asset.get('twitter', '')
        if twitter_url:
            logger.info(f"   🐦 TWITTER НАЙДЕН: {twitter_url[:50]}... (тип пула: {pool_type})")
        
        # Обрабатываем ВСЕ токены независимо от типа пула
        logger.debug(f"   ✅ Обрабатываем токен из {pool_type}")
        
        # Преобразуем данные Jupiter в формат pump.fun для совместимости
        pumpfun_format = {
            'mint': mint,
            'name': name,
            'symbol': symbol,
            'uri': base_asset.get('uri', ''),
            'description': base_asset.get('description', ''),
            'image_uri': base_asset.get('image', ''),
            'dev': dev_address,
            'market_cap': market_cap,
            'created_timestamp': created_timestamp,
            'dex_source': dex,
            'pool_type': pool_type,
            'pool_id': pool_id
        }
        
        # Анализируем токен и получаем сообщение
        msg, keyboard, should_notify, token_image_url = await format_new_token(pumpfun_format)
        
        # Подготавливаем данные для системы обнаружения дубликатов
        duplicate_detection_data = {
            'id': mint,
            'name': name,
            'symbol': symbol,
            'twitter': base_asset.get('twitter', ''),
            'website': base_asset.get('website', ''),
            'telegram': base_asset.get('telegram', ''),
            'social': base_asset.get('social', ''),
            'links': base_asset.get('links', ''),
            'firstPool': {
                'createdAt': created_timestamp
            },
            'dev': dev_address,
            'dex': dex,
            'pool_type': pool_type
        }
        
        # Добавляем в очередь обнаружения дубликатов (НЕ блокирует основной поток)
        try:
            logger.debug(f"🔍 ДУБЛИКАТ DEBUG {symbol}: Twitter = '{duplicate_detection_data.get('twitter', '')}', Pool Type = '{pool_type}'")
            await duplicate_detection_queue.put(duplicate_detection_data)
            logger.debug(f"📋 Токен {symbol} добавлен в очередь обнаружения дубликатов")
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в очередь дубликатов для {symbol}: {e}")
        
        # Отправляем уведомление
        if should_notify:
            logger.info(f"✅ Токен {symbol} ({dex}) прошел фильтрацию - отправляем уведомление")
            send_telegram_photo(token_image_url, msg, keyboard)
            
            # Сохраняем в БД
            try:
                db_manager = get_db_manager()
                log_database_operation("NEW_TOKEN_JUPITER", "tokens", "SUCCESS", 
                                     f"Symbol: {symbol}, DEX: {dex}")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения токена Jupiter в БД: {e}")
        else:
            logger.info(f"❌ Токен {symbol} ({dex}) не прошел фильтрацию")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки нового токена Jupiter: {e}")

async def handle_jupiter_pool_update(pool_data):
    """Обработка обновления пула Jupiter (торговые операции)"""
    try:
        # Извлекаем данные об обновлении
        pool_id = pool_data.get('id', 'Unknown')
        dex = pool_data.get('dex', 'Unknown')
        base_asset = pool_data.get('baseAsset', {})
        
        # Проверяем изменения в рыночной капитализации или объеме
        market_cap = base_asset.get('marketCap', 0)
        volume_24h = pool_data.get('volume24h', 0)
        
        # Логируем только значительные изменения (ОТКЛЮЧЕНО - слишком много спама)
        # if market_cap > 50000 or volume_24h > 1000:  # $50k market cap или $1k объем
        #     symbol = base_asset.get('symbol', 'Unknown')
        #     logger.info(f"📈 Активность в {dex}: {symbol} - MC: ${market_cap:,.0f}, Vol: ${volume_24h:,.0f}")
        #     
        #     # Можно добавить логику для отслеживания крупных торговых операций
        #     # Пока просто логируем
            
    except Exception as e:
        logger.debug(f"Ошибка обработки обновления пула Jupiter: {e}")

async def handle_legacy_pumpfun_token(data):
    """Обработка токена в старом формате pump.fun (для совместимости)"""
    try:
        token_name = data.get('name', 'Unknown')
        mint = data.get('mint', 'Unknown')
        symbol = data.get('symbol', 'Unknown')
        logger.info(f"🚀 LEGACY ТОКЕН: {token_name} ({symbol}) - {mint[:8]}...")
        
        # Анализируем токен и получаем сообщение
        msg, keyboard, should_notify, token_image_url = await format_new_token(data)
        
        # Подготавливаем данные для системы обнаружения дубликатов
        duplicate_detection_data = {
            'id': mint,
            'name': token_name,
            'symbol': symbol,
            'twitter': data.get('twitter', ''),
            'website': data.get('website', ''),
            'telegram': data.get('telegram', ''),
            'social': data.get('social', ''),
            'links': data.get('links', ''),
            'firstPool': {
                'createdAt': data.get('created_timestamp', data.get('timestamp'))
            },
            'dev': data.get('dev', ''),
            'dex': 'pump.fun',
            'pool_type': 'legacy'
        }
        
        # Добавляем в очередь обнаружения дубликатов (НЕ блокирует основной поток)
        try:
            logger.debug(f"🔍 LEGACY ДУБЛИКАТ DEBUG {symbol}: Twitter = '{duplicate_detection_data.get('twitter', '')}'")
            await duplicate_detection_queue.put(duplicate_detection_data)
            logger.debug(f"📋 Legacy токен {symbol} добавлен в очередь обнаружения дубликатов")
        except Exception as e:
            logger.error(f"❌ Ошибка добавления legacy в очередь дубликатов для {symbol}: {e}")
        
        # Отправляем уведомление
        if should_notify:
            logger.info(f"✅ Legacy токен {symbol} прошел фильтрацию - отправляем уведомление")
            send_telegram_photo(token_image_url, msg, keyboard)
            
            # Сохраняем в БД
            try:
                db_manager = get_db_manager()
                log_database_operation("NEW_TOKEN_LEGACY", "tokens", "SUCCESS", f"Symbol: {symbol}")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения legacy токена в БД: {e}")
        else:
            logger.info(f"❌ Legacy токен {symbol} не прошел фильтрацию")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки legacy токена: {e}")

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
            # send_telegram(stats_message)  # Отключено по запросу пользователя
            logger.info("📊 Ежедневная статистика НЕ отправлена (отключено)")
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки ежедневной статистики: {e}")

async def check_connection_health(websocket):
    """Проверка здоровья соединения без ping - просто проверяем что WebSocket не закрыт"""
    try:
        # Проверяем только состояние соединения без отправки ping
        if websocket.closed:
            return False
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
                                'mint': query.strip('"') if len(query) > 20 else None,  # Убираем кавычки из mint
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
                                'mint': query.strip('"') if len(query) > 20 else None,  # Убираем кавычки из mint
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
                                'mint': query.strip('"') if len(query) > 20 else None,  # Убираем кавычки из mint
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
                            'mint': query.strip('"') if len(query) > 20 else None,  # Убираем кавычки из mint
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
            
            # УПРОЩЕННАЯ ЛОГИКА: исключаем только чистых спамеров (80%+ контрактов)
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
            
            # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ФОНОВОГО АНАЛИЗА ===
            log_token_decision("🔍 СТАРТ_TWITTER_АНАЛИЗА", symbol, mint, 
                              f"Токен извлечен из очереди. Размер очереди: {queue_size}. "
                              f"Режим: {'ПАКЕТНЫЙ' if batch_mode else 'ОБЫЧНЫЙ'}")
            
            logger.info(f"🔍 Начинаем фоновый анализ токена {symbol} в Twitter...")
            
            # Выполняем анализ Twitter с быстрым фолбэком при ошибках
            try:
                log_token_decision("📊 ЗАПУСК_АНАЛИЗА_NITTER", symbol, mint, 
                                  "Начинаем поиск в Twitter через Nitter серверы...")
                
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
            
            # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ РЕЗУЛЬТАТОВ АНАЛИЗА ===
            log_token_decision("✅ АНАЛИЗ_ЗАВЕРШЕН", symbol, mint, 
                              f"Твиты: {twitter_analysis['tweets']} | "
                              f"Символ: {twitter_analysis['symbol_tweets']} | "
                              f"Контракт: {twitter_analysis['contract_tweets']} | "
                              f"Активность: {twitter_analysis['engagement']} | "
                              f"Скор: {twitter_analysis['score']} | "
                              f"Рейтинг: {twitter_analysis['rating']} | "
                              f"Контракт найден: {'ДА' if twitter_analysis['contract_found'] else 'НЕТ'}")
            
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
                # В режиме шилинга (CONTRACT_SEARCH_DISABLED=true) уведомления о контрактах отключены
                contract_search_disabled = os.getenv('CONTRACT_SEARCH_DISABLED', 'false').lower() == 'true'
                
                log_token_decision("⚖️ ПРОВЕРКА_ФИЛЬТРА", symbol, mint, 
                                  f"CONTRACT_SEARCH_DISABLED: {contract_search_disabled}")
                
                notification_decision = should_send_delayed_notification(twitter_analysis, symbol, mint)
                
                log_token_decision("🎯 РЕШЕНИЕ_ФИЛЬТРА", symbol, mint, 
                                  f"should_send_delayed_notification() = {notification_decision} | "
                                  f"Причина: {'Найден контракт в Twitter' if notification_decision else 'Контракт НЕ найден или низкая активность'}")
                
                if notification_decision:
                    if contract_search_disabled:
                        log_token_decision("🚫 БЛОКИРОВКА_РЕЖИМОМ_ШИЛИНГА", symbol, mint, 
                                          "Уведомление заблокировано - включен режим шилинга (CONTRACT_SEARCH_DISABLED=true)")
                        logger.info(f"🎯 {symbol}: уведомление о контракте пропущено - включен режим шилинга (CONTRACT_SEARCH_DISABLED=true)")
                    else:
                        log_token_decision("🚀 ОТПРАВКА_УВЕДОМЛЕНИЯ", symbol, mint, 
                                          f"ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! Отправляем уведомление пользователям. "
                                          f"Контракт найден: {'ДА' if twitter_analysis['contract_found'] else 'НЕТ'} | "
                                          f"Скор: {twitter_analysis['score']}")
                        await send_delayed_twitter_notification(token_data, twitter_analysis)
                else:
                    log_token_decision("❌ ТОКЕН_ОТФИЛЬТРОВАН", symbol, mint, 
                                      f"Токен НЕ прошел фильтрацию. Уведомление НЕ отправляется. "
                                      f"Контракт: {'НЕ найден' if not twitter_analysis['contract_found'] else 'найден'} | "
                                      f"Скор: {twitter_analysis['score']} (возможно недостаточно)")
                    
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


async def duplicate_detection_worker():
    """Фоновый обработчик обнаружения дубликатов"""
    logger.info("🔄 Фоновый обработчик обнаружения дубликатов запущен")
    
    while True:
        try:
            # Получаем токен из очереди
            data = await duplicate_detection_queue.get()
            
            # Обработка токена
            symbol = data.get('symbol', 'Unknown')
            mint = data.get('id', 'Unknown')
            
            logger.debug(f"🔍 Начинаем фоновое обнаружение дубликатов для токена {symbol}...")
            
            # Обработка дубликатов (БЕЗ блокировки основного потока)
            await process_duplicate_detection(data)
            
            # Помечаем задачу как выполненную
            duplicate_detection_queue.task_done()
            
        except asyncio.CancelledError:
            logger.info("🛑 Фоновый обработчик обнаружения дубликатов остановлен")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в фоновом обработчике обнаружения дубликатов: {e}")
            await asyncio.sleep(5)  # Пауза перед повторной попыткой

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

def should_notify_based_on_authors_unified(authors):
    """
    ЕДИНАЯ УНИФИЦИРОВАННАЯ ЛОГИКА для pump_bot.py И background_monitor.py
    Отправляем уведомления только если есть информация об авторах,
    кроме случаев когда автор отправляет каждое сообщение с контрактом (100% спам)
    ВАЖНО: Также проверяем черный список авторов
    НОВОЕ: Также блокируем спам-ботов
    """
    # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ АНАЛИЗА АВТОРОВ ===
    if authors:
        authors_info = []
        for author in authors[:3]:  # Показываем первых 3 авторов
            username = author.get('username', 'Unknown')
            followers = author.get('followers_count', 0)
            diversity = author.get('contract_diversity', 0)
            spam_percent = author.get('max_contract_spam', 0)
            authors_info.append(f"@{username} ({followers:,} подп., {diversity:.1f}% разнообр.)")
        
        # Извлекаем первый mint из авторов если есть
        first_author = authors[0] if authors else {}
        sample_mint = "Unknown"
        if 'tweet_text' in first_author:
            import re
            contracts = re.findall(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b', first_author['tweet_text'])
            if contracts:
                sample_mint = contracts[0]
        
        log_token_decision("👥 АНАЛИЗ_АВТОРОВ_СТАРТ", "MULTIPLE", sample_mint, 
                          f"Найдено {len(authors)} авторов: {', '.join(authors_info[:3])}{'...' if len(authors) > 3 else ''}")
    
    if not authors:
        logger.info(f"🚫 Нет информации об авторах твитов - пропускаем уведомление")
        return False  # Нет авторов - НЕ отправляем
    
    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ЧЕРНОГО СПИСКА
    blacklisted_authors = 0
    for author in authors:
        username = author.get('username', '').lower()
        if username in TWITTER_AUTHOR_BLACKLIST:
            blacklisted_authors += 1
            logger.info(f"🚫 Автор @{username} в черном списке - исключаем из анализа")
    
    # Если ВСЕ авторы в черном списке - блокируем уведомление
    if blacklisted_authors == len(authors):
        logger.info(f"🚫 ВСЕ авторы ({len(authors)}) в черном списке - блокируем уведомление")
        return False
    
    pure_spammers = 0  # Авторы которые КАЖДОЕ сообщение пишут с контрактом
    spam_bots = 0      # Спам-боты по содержанию твитов
    total_authors = len(authors)
    valid_authors = total_authors - blacklisted_authors  # Авторы НЕ из черного списка
    
    # Если нет валидных авторов после фильтрации - блокируем
    if valid_authors <= 0:
        logger.info(f"🚫 Нет валидных авторов после фильтрации черного списка - блокируем уведомление")
        return False
    
    for author in authors:
        diversity_percent = author.get('contract_diversity', 0)
        spam_percent = author.get('max_contract_spam', 0)
        total_tweets = author.get('total_contract_tweets', 0)
        username = author.get('username', 'Unknown')
        tweet_text = author.get('tweet_text', '')
        
        # Пропускаем авторов из черного списка в анализе спама
        if username.lower() in TWITTER_AUTHOR_BLACKLIST:
            logger.info(f"🚫 @{username}: В ЧЕРНОМ СПИСКЕ - пропускаем анализ спама")
            continue
        
        # НОВАЯ ПРОВЕРКА: детекция спам-ботов
        is_spam_bot, spam_bot_reason = is_spam_bot_tweet(tweet_text, username)
        
        if is_spam_bot:
            spam_bots += 1
            pure_spammers += 1  # Считаем как спамера
            logger.info(f"🤖 @{username}: СПАМ-БОТ - {spam_bot_reason}")
            continue  # Пропускаем остальные проверки для спам-ботов
        
        # АДАПТИВНАЯ ПРОВЕРКА: разные пороги в зависимости от количества твитов
        diversity_threshold = 40  # По умолчанию для больших выборок
        
        if total_tweets < 10:
            diversity_threshold = 50  # Мягкий порог для малых выборок
        elif total_tweets < 20:
            diversity_threshold = 30  # Умеренный порог для средних выборок
        else:
            diversity_threshold = 40  # Умеренный порог для больших выборок
        
        if total_tweets >= 3 and (spam_percent >= 80 or diversity_percent >= diversity_threshold):
            pure_spammers += 1
            logger.info(f"🚫 @{username}: ЧИСТЫЙ СПАМЕР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений (порог: {diversity_threshold}% для {total_tweets} твитов)")
        else:
            logger.info(f"✅ @{username}: НОРМАЛЬНЫЙ АВТОР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений (порог: {diversity_threshold}% для {total_tweets} твитов)")
    
    # Блокируем ТОЛЬКО если ВСЕ НЕЗАБЛОКИРОВАННЫЕ авторы - чистые спамеры или спам-боты
    should_notify = pure_spammers < valid_authors
    
    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: если остались только спам-боты после фильтрации
    clean_authors = valid_authors - spam_bots
    if clean_authors <= 0:
        logger.info(f"🚫 Нет чистых авторов для отображения - блокируем уведомление")
        should_notify = False
    
    logger.info(f"📊 УНИФИЦИРОВАННЫЙ АНАЛИЗ АВТОРОВ:")
    logger.info(f"   👥 Всего авторов: {total_authors}")
    logger.info(f"   🚫 В черном списке: {blacklisted_authors}")
    logger.info(f"   ✅ Валидных авторов: {valid_authors}")
    logger.info(f"   🤖 Спам-ботов: {spam_bots}")
    logger.info(f"   🚫 Чистых спамеров (80%+ контрактов): {pure_spammers - spam_bots}")
    logger.info(f"   ✅ Нормальных авторов: {valid_authors - pure_spammers}")
    logger.info(f"   🎯 РЕШЕНИЕ: {'ОТПРАВИТЬ' if should_notify else 'ЗАБЛОКИРОВАТЬ'}")
    
    # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ФИНАЛЬНОГО РЕШЕНИЯ ===
    decision_details = (
        f"Всего: {total_authors} | Валидных: {valid_authors} | "
        f"Спам-ботов: {spam_bots} | Чистых спамеров: {pure_spammers - spam_bots} | "
        f"В черном списке: {blacklisted_authors}"
    )
    
    if not should_notify:
        log_token_decision("🚫 АВТОРЫ_ОТФИЛЬТРОВАНЫ", "MULTIPLE", sample_mint, 
                          f"ВСЕ авторы являются спамерами/спам-ботами. {decision_details}")
        logger.info(f"🚫 Уведомление заблокировано - ВСЕ авторы являются спамерами/спам-ботами")
    else:
        log_token_decision("✅ АВТОРЫ_ПРОШЛИ_ФИЛЬТР", "MULTIPLE", sample_mint, 
                          f"Есть подходящие авторы для уведомления. {decision_details}")
        logger.info(f"✅ Уведомление разрешено - есть нормальные авторы или нет данных об авторах")
    
    return should_notify

def should_notify_based_on_authors_quality(authors):
    """
    УСТАРЕВШАЯ ФУНКЦИЯ - используем унифицированную версию
    Оставлена для обратной совместимости
    """
    return should_notify_based_on_authors_unified(authors)

def should_send_delayed_notification(twitter_analysis, symbol, mint):
    """
    Проверяет нужно ли отправить отложенное уведомление после анализа Twitter
    ОТПРАВЛЯЕМ если найден контракт с подходящими авторами
    """
    # Проверяем что контракт найден в Twitter
    if not twitter_analysis.get('contract_found', False):
        logger.debug(f"🚫 {symbol}: контракт не найден в Twitter - пропускаем уведомление")
        return False
    
    # НОВАЯ ПРОВЕРКА: дедупликация уведомлений
    if was_twitter_notification_sent_recently(mint):
        logger.info(f"🔄 {symbol}: уведомление о Twitter активности уже отправлено недавно - пропускаем дублирование")
        return False
    
    # Получаем авторов твитов с контрактом
    contract_authors = twitter_analysis.get('contract_authors', [])
    
    # Используем унифицированную логику фильтрации авторов
    should_notify = should_notify_based_on_authors_unified(contract_authors)
    
    if should_notify:
        logger.info(f"✅ {symbol}: найден контракт с подходящими авторами - отправляем уведомление")
    else:
        logger.info(f"🚫 {symbol}: контракт найден, но авторы не подходят - пропускаем уведомление")
    
    return should_notify

def was_twitter_notification_sent_recently(mint, time_window_minutes=10):
    """Проверяет, было ли отправлено уведомление о Twitter активности в последние N минут"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Получаем токен из базы
        token = session.query(Token).filter_by(mint=mint).first()
        
        if not token:
            logger.debug(f"🔍 {mint[:8]}...: токен не найден в БД")
            return False
            
        if not token.last_twitter_notification:
            logger.debug(f"🔍 {mint[:8]}...: уведомления еще не отправлялись")
            return False
        
        # Проверяем прошло ли достаточно времени
        from datetime import datetime, timedelta
        current_time = datetime.utcnow()
        time_threshold = current_time - timedelta(minutes=time_window_minutes)
        last_notification = token.last_twitter_notification
        
        # Если последнее уведомление было ПОСЛЕ порога (недавно) - блокируем
        if last_notification > time_threshold:
            minutes_ago = (current_time - last_notification).total_seconds() / 60
            logger.debug(f"📅 {mint[:8]}...: уведомление {minutes_ago:.2f} минут назад (порог {time_window_minutes} мин) - БЛОКИРУЕМ")
            return True
        else:
            minutes_ago = (current_time - last_notification).total_seconds() / 60
            logger.debug(f"📅 {mint[:8]}...: уведомление {minutes_ago:.2f} минут назад (порог {time_window_minutes} мин) - РАЗРЕШАЕМ")
            return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки дедупликации для {mint}: {e}")
        return False
    finally:
        session.close()

def mark_twitter_notification_sent(mint):
    """Отмечает что уведомление о Twitter активности было отправлено"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Обновляем время последнего уведомления
        token = session.query(Token).filter_by(mint=mint).first()
        if token:
            from datetime import datetime
            current_time = datetime.utcnow()
            token.last_twitter_notification = current_time
            session.commit()
            logger.debug(f"✅ Отмечено уведомление для {mint[:8]}... в {current_time}")
        else:
            logger.warning(f"⚠️ Токен {mint[:8]}... не найден в БД для отметки уведомления")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отметки уведомления для {mint}: {e}")
        session.rollback()
    finally:
        session.close()

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
            
            # Используем единую функцию форматирования авторов
            message += format_authors_section(authors, prefix_newline=True)
            

        
        message += f"⚡ <b>Время действовать!</b>\n"
        message += f"<b>🕐 Время:</b> {datetime.now().strftime('%H:%M:%S')}"
        
        # Кнопки
        bonding_curve_key = token_data.get('bondingCurveKey', mint)
        keyboard = [
            [
                {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/t/{mint}"},
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
        
        # Отмечаем что уведомление отправлено
        mark_twitter_notification_sent(mint)
        
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
            # Используем единую функцию для извлечения контрактов
            contracts_in_tweet = extract_contracts_from_text(mention.tweet_text)
            
            # Также добавляем контракт из поля mint если есть
            if mention.mint:
                contracts_in_tweet.append(mention.mint)
            
            # Добавляем найденные контракты
            for contract in contracts_in_tweet:
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
        elif diversity_percent >= 20:  # ≥20% разных контрактов (максимум 10 из 62)
            is_spam_likely = True
            recommendation = "🚫 СПАМЕР - слишком много разных контрактов!"
            spam_analysis = f"СПАМ! {diversity_percent:.1f}% разных контрактов - явный спамер (лимит 16%)"
        else:
            # ИСПРАВЛЕННАЯ ЛОГИКА: низкое разнообразие = хорошо
            if diversity_percent <= 10:  # ≤10% разных контрактов = отлично
                is_spam_likely = False
                recommendation = "✅ ОТЛИЧНЫЙ - очень низкое разнообразие контрактов"
                spam_analysis = f"Отлично: {diversity_percent:.1f}% разнообразия - высокий фокус на конкретных токенах"
            else:
                is_spam_likely = False
                recommendation = "🟡 ПРИЕМЛЕМЫЙ - низкое разнообразие контрактов"
                spam_analysis = f"Приемлемо: {diversity_percent:.1f}% разнообразия (порог {diversity_threshold}% для {total_tweets} твитов)"
        
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
                profile_data, all_tweets, tweets_with_contracts = await profile_parser.get_profile_with_replies_multi_page(author_username, max_pages=3)
                
                if all_tweets:
                    tweets_on_page = all_tweets
                    logger.info(f"📱 Загружено {len(all_tweets)} твитов с профиля @{author_username} (3 страницы)")
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
        # Используем единую функцию для извлечения контрактов
        contracts_in_tweet = extract_contracts_from_text(tweet_text)
        
        for contract in contracts_in_tweet:
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
    else:
        # АДАПТИВНЫЕ ПОРОГИ в зависимости от количества твитов
        diversity_threshold = 40  # По умолчанию для больших выборок
        
        if total_tweets < 10:
            diversity_threshold = 50  # Мягкий порог для малых выборок
        elif total_tweets < 20:
            diversity_threshold = 30  # Умеренный порог для средних выборок
        else:
            diversity_threshold = 40  # Умеренный порог для больших выборок
        
        if diversity_percent >= diversity_threshold:
            is_spam_likely = True
            recommendation = "🚫 СПАМЕР - слишком много разных контрактов!"
            spam_analysis = f"СПАМ! {diversity_percent:.1f}% разных контрактов - превышен порог {diversity_threshold}% для {total_tweets} твитов"
        else:
            # ИСПРАВЛЕННАЯ ЛОГИКА: низкое разнообразие = хорошо
            if diversity_percent <= 10:  # ≤10% разных контрактов = отлично
                is_spam_likely = False
                recommendation = "✅ ОТЛИЧНЫЙ - очень низкое разнообразие контрактов"
                spam_analysis = f"Отлично: {diversity_percent:.1f}% разнообразия - высокий фокус на конкретных токенах"
            else:
                is_spam_likely = False
                recommendation = "🟡 ПРИЕМЛЕМЫЙ - низкое разнообразие контрактов"
                spam_analysis = f"Приемлемо: {diversity_percent:.1f}% разнообразия (порог {diversity_threshold}% для {total_tweets} твитов)"
    
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

def extract_contracts_from_text(text):
    """
    ЕДИНАЯ ФУНКЦИЯ для извлечения Solana контрактов из текста твита
    Возвращает список уникальных контрактов длиной 32-44 символа
    """
    if not text:
        return []
    
    # Используем более гибкое регулярное выражение:
    # 1. Ищем последовательности из 32-48 символов (включая возможное "pump")
    # 2. Не требуем строгих границ слов, но исключаем полностью буквенные строки
    contracts = re.findall(r'[A-Za-z0-9]{32,48}', text)
    
    # Очищаем и фильтруем контракты
    clean_contracts = []
    for contract in contracts:
        # Убираем "pump" с конца если есть
        clean_contract = contract
        if contract.endswith('pump'):
            clean_contract = contract[:-4]
        
        # Проверяем что это похоже на Solana адрес:
        # - 32-44 символа
        # - только буквы и цифры
        # - содержит хотя бы одну цифру (чтобы исключить чисто буквенные строки)
        if (32 <= len(clean_contract) <= 44 and 
            clean_contract.isalnum() and 
            any(c.isdigit() for c in clean_contract)):
            clean_contracts.append(clean_contract)
    
    # Возвращаем уникальные контракты
    return list(set(clean_contracts))

def should_filter_author_by_diversity(author_username, diversity_threshold=30):
    """
    Проверяет, нужно ли фильтровать автора по разнообразию контрактов
    diversity_threshold - порог в процентах разнообразия, выше которого автор фильтруется (много разных контрактов = плохо)
    """
    analysis = analyze_author_contract_diversity(author_username)
    return analysis['contract_diversity_percent'] >= diversity_threshold

def is_spam_bot_tweet(tweet_text, author_username=""):
    """
    Определяет, является ли твит от спам-бота по характерным признакам
    """
    if not tweet_text:
        return False, "Нет текста"
    
    spam_score = 0
    reasons = []
    
    # 1. КИТАЙСКИЕ СИМВОЛЫ (высокий приоритет)
    chinese_patterns = [
        '投资良机', '聪明钱', '查看我主页', '无延迟群组', '跟随', '快人一步', '交易平台',
        '速抢钻石福利', '合约地址', '频道信号', '点击'
    ]
    chinese_count = sum(1 for pattern in chinese_patterns if pattern in tweet_text)
    if chinese_count > 0:
        spam_score += chinese_count * 15  # Очень высокий вес
        reasons.append(f"Китайские паттерны: {chinese_count}")
    
    # 2. СПЕЦИФИЧЕСКИЕ ДОМЕНЫ СПАМ-СЕРВИСОВ
    spam_domains = [
        'ant.fun', 'okai.hk', 'okai.HK', 'gmgn.ai', 'Gmgn.ai', 'axiom.hk', 'Axiom.hk'
    ]
    domain_count = sum(1 for domain in spam_domains if domain.lower() in tweet_text.lower())
    if domain_count > 0:
        spam_score += domain_count * 20  # Очень высокий вес
        reasons.append(f"Спам-домены: {domain_count}")
    
    # 3. СТРУКТУРИРОВАННЫЕ МЕТКИ (CA:, MC:, H:, T:, M:, C:)
    structured_patterns = [
        r'CA:\s*[A-Za-z0-9]{20,}',  # Contract Address
        r'MC:\s*[\d\.\$KM]+',       # Market Cap
        r'H:\s*\d+',                # Holders
        r'T:\s*\d+min',             # Time
        r'M\s*-\s*[\d\.\$KM]+',     # Market cap variant
        r'C\s*-\s*[A-Za-z0-9]{20,}' # Contract variant
    ]
    
    import re
    structured_count = 0
    for pattern in structured_patterns:
        if re.search(pattern, tweet_text):
            structured_count += 1
    
    if structured_count >= 2:  # Если есть 2+ структурированных элемента
        spam_score += structured_count * 10
        reasons.append(f"Структура: {structured_count} меток")
    
    # 4. ТИПИЧНЫЕ СПАМ ФРАЗЫ
    spam_phrases = [
        'AI Alert', 'Quick buy', 'Fast Buy', 'Signal', 'smart traders', 'smart money',
        'Opportunity!', 'Follow ant.fun', 'Track ant.fun', 'bubble map', 'earn points',
        'Quick trade', 'no delay group', 'Launched!', 'Token Alert', 'Quickest fills',
        'Smart buys', 'Anti-Scam', 'Detect red flags', 'Quick buy 👉', 'Signal 👉',
        'Alert 👉', 'Check Analyze', 'Features you want', 'performance you need'
    ]
    
    phrase_count = sum(1 for phrase in spam_phrases if phrase.lower() in tweet_text.lower())
    if phrase_count > 0:
        spam_score += phrase_count * 8
        reasons.append(f"Спам-фразы: {phrase_count}")
    
    # 5. ИЗБЫТОЧНОЕ КОЛИЧЕСТВО ЭМОДЗИ
    emoji_count = len([c for c in tweet_text if ord(c) > 127])  # Примерная оценка эмодзи
    if emoji_count > 15:  # Слишком много эмодзи
        spam_score += (emoji_count - 15) * 2
        reasons.append(f"Избыток эмодзи: {emoji_count}")
    
    # 6. ССЫЛКИ НА СОКРАЩЕННЫЕ АДРЕСА КОНТРАКТОВ
    shortened_contract_patterns = [
        r'[A-Za-z0-9]{8,12}\.{3}',  # Сокращенные адреса типа "HBZ7M8iA..."
        r'[A-Za-z0-9]{8,12}…',      # С символом многоточия
        r'token/[A-Za-z0-9]{8,12}_[A-Za-z]'  # Паттерн gmgn.ai
    ]
    
    shortened_count = 0
    for pattern in shortened_contract_patterns:
        if re.search(pattern, tweet_text):
            shortened_count += 1
    
    if shortened_count > 0:
        spam_score += shortened_count * 12
        reasons.append(f"Сокращенные контракты: {shortened_count}")
    
    # 7. СПЕЦИФИЧЕСКИЕ СПАМ КОНСТРУКЦИИ
    spam_constructions = [
        '🔊 Signal 🌐', '🤖 Quick buy 👉', '💎 AI Alert', '🚀 Fast Buy 👉',
        '- The Quickest fills', '- Great TX speed', '- Anti-Scam –', 
        '- Features you want', '- Resize your instant', '👉👉', '⬅️', '🔃-'
    ]
    
    construction_count = sum(1 for construction in spam_constructions if construction in tweet_text)
    if construction_count > 0:
        spam_score += construction_count * 15
        reasons.append(f"Спам-конструкции: {construction_count}")
    
    # 8. ПРОВЕРКА ИМЕНИ ПОЛЬЗОВАТЕЛЯ НА ПОДОЗРИТЕЛЬНОСТЬ
    suspicious_username_patterns = [
        r'^[a-z]+\d{4,}$',  # Имена типа "user1234"
        r'^bot\w*\d*$',     # Содержит "bot"
        r'^\w*signal\w*$',  # Содержит "signal"
        r'^\w*trade\w*$'    # Содержит "trade"
    ]
    
    username_suspicious = any(re.match(pattern, author_username.lower()) for pattern in suspicious_username_patterns)
    if username_suspicious:
        spam_score += 10
        reasons.append("Подозрительный username")
    
    # ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА
    is_spam = spam_score >= 30  # Порог для определения спама
    
    confidence = min(spam_score / 50 * 100, 100)  # Уверенность в %
    
    result_text = f"Спам: {spam_score} баллов ({confidence:.0f}%)"
    if reasons:
        result_text += f" - {', '.join(reasons)}"
    
    return is_spam, result_text

def filter_authors_for_display(authors):
    """
    ЕДИНАЯ ФУНКЦИЯ ФИЛЬТРАЦИИ АВТОРОВ ДЛЯ ОТОБРАЖЕНИЯ
    Используется в pump_bot.py И background_monitor.py
    Удаляет спамеров, спам-ботов и авторов из черного списка
    """
    filtered_authors = []
    
    for author in authors:
        username = author.get('username', 'Unknown')
        tweet_text = author.get('tweet_text', '')
        
        # Проверяем черный список
        if username.lower() in TWITTER_AUTHOR_BLACKLIST:
            logger.info(f"🚫 Скрываем автора @{username} из уведомления: в черном списке")
            continue
        
        # Проверяем на спам-бота
        is_spam_bot, spam_bot_reason = is_spam_bot_tweet(tweet_text, username)
        if is_spam_bot:
            logger.info(f"🤖 Скрываем спам-бота @{username} из уведомления: {spam_bot_reason}")
            continue
        
        # НОВАЯ ПРОВЕРКА: исключаем авторов с высоким разнообразием контрактов (спамеров)
        is_spam_likely = author.get('is_spam_likely', False)
        if is_spam_likely:
            spam_analysis = author.get('spam_analysis', 'превышен порог разнообразия контрактов')
            logger.info(f"🚫 Скрываем спамера @{username} из уведомления: {spam_analysis}")
            continue
        
        # Автор прошел все проверки - добавляем в отображение
        filtered_authors.append(author)
    
    return filtered_authors

def format_authors_section(authors, prefix_newline=True):
    """
    ЕДИНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ СЕКЦИИ АВТОРОВ
    Используется в pump_bot.py И background_monitor.py
    Обеспечивает идентичное форматирование уведомлений
    """
    if not authors:
        return ""
    
    # Фильтруем авторов для отображения
    filtered_authors = filter_authors_for_display(authors)
    
    if not filtered_authors:
        return ""
    
    # Начинаем секцию
    prefix = "\n" if prefix_newline else ""
    message = f"{prefix}<b>👥 АВТОРЫ ТВИТОВ С КОНТРАКТОМ ({len(filtered_authors)} авторов):</b>\n"
    
    # Статистика
    total_followers = sum([author.get('followers_count', 0) for author in filtered_authors])
    verified_count = sum([1 for author in filtered_authors if author.get('is_verified', False)])
    
    message += f"   📊 Общий охват: {total_followers:,} подписчиков\n"
    if verified_count > 0:
        message += f"   ✅ Верифицированных: {verified_count}\n"
    message += "\n"
    
    # Показываем максимум 3 авторов
    for i, author in enumerate(filtered_authors[:3]):
        username = author.get('username', 'Unknown')
        display_name = author.get('display_name', username)
        followers = author.get('followers_count', 0)
        verified = "✅" if author.get('is_verified', False) else ""
        tweet_text = author.get('tweet_text', '')
        tweet_date = author.get('tweet_date', '')
        
        # Информация о спаме контрактов
        spam_percent = author.get('max_contract_spam', 0)
        is_spam_likely = author.get('is_spam_likely', False)
        total_contract_tweets = author.get('total_contract_tweets', 0)
        unique_contracts = author.get('unique_contracts_count', 0)
        spam_analysis = author.get('spam_analysis', 'Нет данных')
        
        # Эмодзи для статуса автора (спамеры исключены фильтрацией)
        spam_indicator = ""
        if spam_percent >= 80:
            spam_indicator = " 🔥"  # Вспышка активности
        elif spam_percent >= 60:
            spam_indicator = " ⭐"  # Высокая концентрация
        elif spam_percent >= 40:
            spam_indicator = " 🟡"  # Умеренная концентрация
        # Убрали проверку на is_spam_likely, поскольку спамеры теперь исключаются фильтром
        
        message += f"{i+1}. <b>@{username}</b> {verified}{spam_indicator}\n"
        if display_name != username:
            message += f"   📝 {display_name}\n"
        
        # Информация о профиле
        following_count = author.get('following_count', 0)
        tweets_count = author.get('tweets_count', 0)
        likes_count = author.get('likes_count', 0)
        join_date = author.get('join_date', '')
        
        if followers > 0 or following_count > 0 or tweets_count > 0:
            message += f"   👥 {followers:,} подписчиков | {following_count:,} подписок\n"
            message += f"   📝 {tweets_count:,} твитов | ❤️ {likes_count:,} лайков\n"
            if join_date:
                message += f"   📅 Создан: {join_date}\n"
        
        # Дата публикации твита
        if tweet_date:
            message += f"   📅 Опубликован: {tweet_date}\n"
        
        # Тип твита
        tweet_type = author.get('tweet_type', 'Твит')
        type_emoji = "💬" if tweet_type == "Ответ" else "🐦"
        message += f"   {type_emoji} Тип: {tweet_type}\n"
        
        # Исторические данные
        historical_data = author.get('historical_data', {})
        if historical_data and historical_data.get('total_mentions', 0) > 0:
            total_mentions = historical_data.get('total_mentions', 0)
            unique_tokens = historical_data.get('unique_tokens', 0)
            recent_7d = historical_data.get('recent_mentions_7d', 0)
            recent_30d = historical_data.get('recent_mentions_30d', 0)
            
            message += f"   📊 История: {total_mentions} упоминаний ({unique_tokens} токенов)\n"
            if recent_7d > 0 or recent_30d > 0:
                message += f"   📈 Активность: {recent_7d} за 7д, {recent_30d} за 30д\n"
        
        # Анализ концентрации контрактов
        if total_contract_tweets > 0:
            message += f"   📊 Контракты: {unique_contracts} из {total_contract_tweets} твитов (концентрация: {spam_percent:.1f}%)\n"
            message += f"   🎯 Анализ: {spam_analysis}\n"
        
        # Текст твита
        if tweet_text:
            message += f"   💬 <blockquote>{tweet_text}</blockquote>\n"
    
    message += "\n"
    return message

async def main():
    """Основная функция с автоматическим реконнектом - теперь с Jupiter!"""
    uri = "wss://trench-stream.jup.ag/ws"
    max_retries = 10
    retry_delay = 5
    retry_count = 0
    first_connection = True
    last_stats_day = None
    last_heartbeat = datetime.now()
    
    # Инициализируем очередь для дубликатов
    global duplicate_detection_queue
    duplicate_detection_queue = asyncio.Queue()
    
    # ОТКЛЮЧЕН: Twitter анализ больше не нужен
    # twitter_worker_task = asyncio.create_task(twitter_analysis_worker())
    
    # Запускаем фоновый обработчик обнаружения дубликатов
    duplicate_worker_task = asyncio.create_task(duplicate_detection_worker())
    
    # Сбрасываем старые "Анализируется..." при запуске
    reset_analyzing_tokens_timeout()
    
    # ОТКЛЮЧЕН: задачи повторного анализа Twitter больше не нужны
    # async def retry_analysis_scheduler():
    #     while True:
    #         await asyncio.sleep(600)  # 10 минут
    #         
    #         # Проверяем перегрузку очереди
    #         await check_queue_overload()
    #         
    #         # Стандартная очистка
    #         await check_and_retry_failed_analysis()
    #         reset_analyzing_tokens_timeout()
    
    # Запускаем мониторинг официальных контрактов каждую минуту
    async def official_contracts_monitor():
        while True:
            await asyncio.sleep(60)  # 1 минута
            
            # Мониторим официальные контракты для групп дубликатов
            await monitor_official_contracts_for_groups()
    
    # Запускаем VIP мониторинг Twitter аккаунтов
    # VIP мониторинг Twitter аккаунтов перенесен в отдельную систему vip_twitter_monitor.py
    
    # retry_task = asyncio.create_task(retry_analysis_scheduler())
    contracts_monitor_task = asyncio.create_task(official_contracts_monitor())
    
    logger.info("🚫 Планировщик повторного анализа Twitter ОТКЛЮЧЕН")
    logger.info("🚫 Фоновый обработчик Twitter анализа ОТКЛЮЧЕН")
    logger.info("🔍 Запущен мониторинг официальных контрактов (каждую минуту)")
    
    # Инициализируем новую систему групп дубликатов
    initialize_duplicate_groups_manager(TELEGRAM_TOKEN)
    logger.info("✅ Система групп дубликатов с Google Sheets инициализирована")
    
    # Логируем статус системы обнаружения дубликатов
    if duplicate_detection_enabled:
        logger.info("🔍 Система обнаружения дубликатов АКТИВНА")
        logger.info("📍 Уведомления о дубликатах будут отправляться в тему 14")
        logger.info("📊 Google Sheets таблицы будут создаваться автоматически")
        if contract_search_disabled:
            logger.info("🎯 РЕЖИМ: Фокус на шилинге - поиск контрактов ОТКЛЮЧЕН")
            logger.info("⚡ Уведомления при любых упоминаниях токена")
        else:
            logger.info("🔍 РЕЖИМ: Полный анализ - поиск контрактов ВКЛЮЧЕН")
            logger.info("📊 Уведомления только при анонсах БЕЗ контракта")
    else:
        logger.info("🚫 Система обнаружения дубликатов ОТКЛЮЧЕНА")
    
    # Счетчики для оптимизации
    consecutive_errors = 0
    batch_mode = False
    
    while True:
        try:
            # Создаем SSL контекст для Jupiter
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Дополнительные заголовки для Jupiter WebSocket с CloudFlare куками
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Origin": "https://jup.ag",
                "Cookie": "cf_clearance=m5O0sYyORJM.bb3A3eQGse7P6aa2c9BLgMOt6tm8Mu8-1750902546-1.2.1.1-eRyDtqC_4lkjfCnREIIEQ2LwdV3qMnJqeI4wGFZQpuYfpbLyKuz44QurDH1nnhmPo8.KF9u1vlQRddXKKWdQu7RfJR17j1kgpQeNYY.jUsbLeIYkwgDGlTRWwMeYD0FVitXxJkK6sMtKIXMVdfsdL.M.shrsRtlhuLmZCfVWjhZ89pZrBn5TpZjB98akJAOSGRl3qnsP352Q77oTOsMdnggp5fjO2wlfXqHY.TAjkHKJ0Frk.EtzUKw1sESan_pPne_jbfJRu4CVKkTi52mko5DFlrC5QuAiCntW0a11t2LSqLLkxcXM6jxDKV5IhHpPq79qXtne2PmwiweC_QucapNUyyA_0bFh33Lx4ahcYRc"
            }
            
            # Определяем параметры подключения в зависимости от версии websockets
            import websockets
            websockets_version = websockets.__version__
            logger.info(f"🔧 Используется websockets версия: {websockets_version}")
            
            # Универсальные параметры подключения
            connect_params = {
                "ssl": ssl_context,
                "close_timeout": WEBSOCKET_CONFIG['close_timeout'],
                "max_size": WEBSOCKET_CONFIG['max_size'],
                "max_queue": WEBSOCKET_CONFIG['max_queue']
            }
            
            # Добавляем заголовки в зависимости от версии
            if int(websockets_version.split('.')[0]) >= 12:
                # Новая версия (12.x+) использует additional_headers
                connect_params["additional_headers"] = headers
            else:
                # Старая версия (11.x и ниже) использует extra_headers
                connect_params["extra_headers"] = headers
            
            # Настройки WebSocket с улучшенным keepalive для Jupiter
            async with websockets.connect(uri, **connect_params) as websocket:
                logger.info("🌐 Подключен к Jupiter WebSocket")
                
                # Инициализируем мониторинг соединения
                connection_monitor.connection_established()
                
                # Подписываемся на последние обновления Jupiter
                recent_msg = {"type": "subscribe:recent"}
                await websocket.send(json.dumps(recent_msg))
                logger.info("✅ Подписались на recent обновления")
                
                await asyncio.sleep(1)
                
                # Подписываемся на пулы (первая группа)
                pools_msg_1 = {
                    "type": "subscribe:pool",
                    "pools": [
                        "7ydCvqmPj42msz3mm2W28a4hXKaukF7XNpRjNXNhbonk",
                        "29F4jaxGYGCP9oqJxWn7BRrXDCXMQYFEirSHQjhhpump",
                        "B5BQaCLi74zGhftMgJ4sMvB6mLmrX57HxhcUKgGBpump",
                        "9mjmty3G22deMtg1Nm3jTc5CRYTmK6wPPpbLG43Xpump",
                        "2d1STwNUEprrGuTz7DLSYb27K3iRcuSUKGkk2KpKpump",
                        "qy4gzfT8AyEC8YHRDhF8STMhJBi12dQkLFmabRVFSvA",
                        "31Edt1xnFvoRxL1cuaHB4wUGCL3P3xWrVEqpr2Jppump",
                        "AMxueJUmbczaFwB33opka4Noiy9xjkuHtk9wbu8Apump"
                    ]
                }
                await websocket.send(json.dumps(pools_msg_1))
                logger.info("✅ Подписались на первую группу пулов (8 пулов)")
                
                await asyncio.sleep(1)
                
                # Подписываемся на пулы (вторая группа)
                pools_msg_2 = {
                    "type": "subscribe:pool",
                    "pools": [
                        "Gvn6RiUgXe5mhdsfxG99WPaE4tA5B34cSfuKz1bDpump",
                        "XMF7a2yneYzRJYNmrCAyuY5Q4FhHFaq1rVrZyBoGVb6",
                        "9a65Ydi2b7oHq2WQwJtQdnUzaqLb9BVMR4mvm1LSpump",
                        "5YpHeidohua6JU16sM2mfK6xjomvrSzBVvuducY3pump",
                        "CuDeFkJpbpdyyAzyEK61j3rn5GWYxvdbJpi3gKpxpump",
                        "AtfLADJjSqpfaogbnGvYBpmCz3EWX25p671Z5dc3pump",
                        "EvKGsBoF86SundThCauxByMdx1gUgPzCtd3wgYeLpump",
                        "36kHY89q592VNKATeHCdDcV3tJLvQYASu4oe1Zfhpump"
                    ]
                }
                await websocket.send(json.dumps(pools_msg_2))
                logger.info("✅ Подписались на вторую группу пулов (8 пулов)")
                
                await asyncio.sleep(1)
                
                # Подписываемся на пулы (третья группа)
                pools_msg_3 = {
                    "type": "subscribe:pool",
                    "pools": [
                        "fZXyTmDrjtjkXLBsVx2YWw2RU9TjUcnV3T3V4fhrGuv",
                        "8pR8hQRRLYMyxh6mLszMbyQPFNpNFNMTUjx9D7nxnxQh",
                        "DXazegZa2KcHH8ukAnweT8hj1Sa9t2KyDmvUfbXkjxZk",
                        "JECb6Zsw5FwuU6Kf28wTHwfGTaWTu9rAdHGcrcbb7TJD",
                        "7AH7kZiK2sByFUGpy1zgndtDiAaiAMQr66C8Mu8at9yz",
                        "9adfJNSd3sjfvV2kBX7z6erjbD2J3ANqPKpvTaLPnrku",
                        "DC9e6vbsnrooUTKVPbVVwNpxYvd4dcirk3jbTe7T6Hch",
                        "Cp2Yb6vj948VToEVddo6LNm7cDGAQCrDnjwbMYG3LkL5"
                    ]
                }
                await websocket.send(json.dumps(pools_msg_3))
                logger.info("✅ Подписались на третью группу пулов (8 пулов)")
                
                # Уведомляем о запуске только при первом подключении
                if first_connection:
                    start_message = (
                        "🚀 <b>JUPITER БОТ v4.0 ЗАПУЩЕН!</b>\n\n"
                        "✅ Мониторинг ВСЕХ DEX'ов через Jupiter\n"
                        "🚫 Twitter анализ ОТКЛЮЧЕН\n"
                        "🔍 Фокус на обнаружении дубликатов\n"
                        "🌐 Источники: pump.fun, Raydium, Meteora, bags.fun\n"
                        "📊 В 3-5 раз БОЛЬШЕ токенов чем раньше\n"
                        "✅ Кнопки для быстрой покупки\n\n"
                    )
                    
                    # Добавляем информацию о системе дубликатов только если она включена
                    if duplicate_detection_enabled:
                        start_message += (
                            "🔍 <b>СИСТЕМА ОБНАРУЖЕНИЯ ДУБЛИКАТОВ!</b>\n"
                            "🎯 Поиск токенов с одинаковыми данными\n"
                        )
                        if contract_search_disabled:
                            start_message += (
                                "⚡ <b>РЕЖИМ ШИЛИНГА:</b> Любые упоминания токена\n"
                                "🚀 Максимальная скорость обнаружения\n"
                            )
                        else:
                            start_message += (
                                "🐦 Проверка контрактов в Twitter\n"
                                "📊 Уведомления только при анонсах БЕЗ контракта\n"
                            )
                        start_message += "📍 Уведомления в тему 14\n\n"
                    
                    start_message += "💎 Революция в мониторинге токенов!"
                    # send_telegram_general(start_message)  # Отключено по запросу пользователя
                    first_connection = False
                else:
                    # Уведомление о переподключении
                    send_telegram_to_user("🔄 <b>Jupiter переподключение успешно!</b>\n✅ Продолжаем мониторинг всех DEX'ов")
                
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
                        # await send_daily_stats()  # Отключено по запросу пользователя
                        last_stats_day = current_day
                    
                    # Отправляем статистику соединения каждый час
                    if message_count % 3600 == 0 and message_count > 0:  # Примерно каждый час при активности
                        connection_stats = connection_monitor.format_stats_message()
                        logger.info("📊 Отправляем статистику соединения")
                        send_telegram_to_user(connection_stats)
                    
                    # Проверяем здоровье соединения периодически
                    if message_count % WEBSOCKET_CONFIG['health_check_interval'] == 0:
                        current_time = datetime.now()
                        time_since_heartbeat = (current_time - last_heartbeat).total_seconds()
                        
                        # Если долго нет сообщений, просто переподписываемся на пулы
                        if time_since_heartbeat > WEBSOCKET_CONFIG['heartbeat_check']:
                            logger.info(f"🔍 Переподписываемся на пулы (нет сообщений {time_since_heartbeat:.0f}с)")
                            
                            try:
                                # Переподписываемся на recent
                                recent_msg = {"type": "subscribe:recent"}
                                await websocket.send(json.dumps(recent_msg))
                                logger.info("✅ Переподписались на recent")
                                
                                await asyncio.sleep(0.5)
                                
                                # Переподписываемся на первую группу пулов
                                pools_msg_1 = {
                                    "type": "subscribe:pool",
                                    "pools": [
                                        "7ydCvqmPj42msz3mm2W28a4hXKaukF7XNpRjNXNhbonk",
                                        "29F4jaxGYGCP9oqJxWn7BRrXDCXMQYFEirSHQjhhpump",
                                        "B5BQaCLi74zGhftMgJ4sMvB6mLmrX57HxhcUKgGBpump",
                                        "9mjmty3G22deMtg1Nm3jTc5CRYTmK6wPPpbLG43Xpump",
                                        "2d1STwNUEprrGuTz7DLSYb27K3iRcuSUKGkk2KpKpump",
                                        "qy4gzfT8AyEC8YHRDhF8STMhJBi12dQkLFmabRVFSvA",
                                        "31Edt1xnFvoRxL1cuaHB4wUGCL3P3xWrVEqpr2Jppump",
                                        "AMxueJUmbczaFwB33opka4Noiy9xjkuHtk9wbu8Apump"
                                    ]
                                }
                                await websocket.send(json.dumps(pools_msg_1))
                                logger.info("✅ Переподписались на первую группу пулов")
                                
                                await asyncio.sleep(0.5)
                                
                                # Переподписываемся на вторую группу пулов
                                pools_msg_2 = {
                                    "type": "subscribe:pool", 
                                    "pools": [
                                        "Gvn6RiUgXe5mhdsfxG99WPaE4tA5B34cSfuKz1bDpump",
                                        "XMF7a2yneYzRJYNmrCAyuY5Q4FhHFaq1rVrZyBoGVb6",
                                        "9a65Ydi2b7oHq2WQwJtQdnUzaqLb9BVMR4mvm1LSpump",
                                        "5YpHeidohua6JU16sM2mfK6xjomvrSzBVvuducY3pump",
                                        "CuDeFkJpbpdyyAzyEK61j3rn5GWYxvdbJpi3gKpxpump",
                                        "AtfLADJjSqpfaogbnGvYBpmCz3EWX25p671Z5dc3pump",
                                        "EvKGsBoF86SundThCauxByMdx1gUgPzCtd3wgYeLpump",
                                        "36kHY89q592VNKATeHCdDcV3tJLvQYASu4oe1Zfhpump"
                                    ]
                                }
                                await websocket.send(json.dumps(pools_msg_2))
                                logger.info("✅ Переподписались на вторую группу пулов")
                                
                                await asyncio.sleep(0.5)
                                
                                # Переподписываемся на третью группу пулов
                                pools_msg_3 = {
                                    "type": "subscribe:pool",
                                    "pools": [
                                        "fZXyTmDrjtjkXLBsVx2YWw2RU9TjUcnV3T3V4fhrGuv",
                                        "8pR8hQRRLYMyxh6mLszMbyQPFNpNFNMTUjx9D7nxnxQh",
                                        "DXazegZa2KcHH8ukAnweT8hj1Sa9t2KyDmvUfbXkjxZk",
                                        "JECb6Zsw5FwuU6Kf28wTHwfGTaWTu9rAdHGcrcbb7TJD",
                                        "7AH7kZiK2sByFUGpy1zgndtDiAaiAMQr66C8Mu8at9yz",
                                        "9adfJNSd3sjfvV2kBX7z6erjbD2J3ANqPKpvTaLPnrku",
                                        "DC9e6vbsnrooUTKVPbVVwNpxYvd4dcirk3jbTe7T6Hch",
                                        "Cp2Yb6vj948VToEVddo6LNm7cDGAQCrDnjwbMYG3LkL5"
                                    ]
                                }
                                await websocket.send(json.dumps(pools_msg_3))
                                logger.info("✅ Переподписались на третью группу пулов")
                                
                                last_heartbeat = current_time
                                logger.info("✅ Переподписка на все пулы завершена")
                                
                            except Exception as e:
                                logger.warning(f"❌ Ошибка переподписки, переподключаемся: {e}")
                                break
                    
        except websockets.exceptions.ConnectionClosed as e:
            # Обновляем статистику мониторинга
            connection_monitor.connection_lost()
            
            if e.code == 1011:
                logger.warning(f"⚠️ Keepalive timeout: {e}")
                # Не отправляем уведомление для обычных keepalive ошибок
            else:
                logger.warning(f"⚠️ Соединение закрыто: {e}")
                send_telegram_to_user(f"⚠️ <b>Соединение потеряно</b>\nКод: {e.code}\nПричина: {e.reason}\n🔄 Переподключение...")
        except Exception as status_error:
            # Проверяем на ошибки статуса (совместимость с разными версиями websockets)
            if "InvalidStatusCode" in str(type(status_error)) or "InvalidStatus" in str(type(status_error)) or "HTTP 520" in str(status_error):
                logger.error(f"❌ Неверный статус код: {status_error}")
                if retry_count <= 3:
                    send_telegram_to_user(f"❌ <b>Ошибка подключения</b>\nСтатус: {status_error}")
                # Продолжаем к следующей итерации для переподключения
                pass
            elif "WebSocketException" in str(type(status_error)) or "websockets" in str(type(status_error)):
                # WebSocket ошибки
                logger.error(f"❌ WebSocket ошибка: {status_error}")
                # Не спамим уведомлениями при частых WebSocket ошибках
                if retry_count <= 3:
                    send_telegram_to_user(f"❌ <b>WebSocket ошибка</b>\n{status_error}")
            else:
                # Другие неожиданные ошибки
                logger.error(f"❌ Неожиданная ошибка: {status_error}")
                if retry_count <= 1:
                    send_telegram_to_user(f"❌ <b>Критическая ошибка</b>\n{status_error}")
        except ConnectionResetError as e:
            logger.warning(f"⚠️ Соединение сброшено сетью: {e}")
            # Обычная сетевая ошибка, не требует уведомления
        except OSError as e:
            logger.error(f"❌ Системная ошибка сети: {e}")
            if retry_count <= 2:
                send_telegram_to_user(f"❌ <b>Сетевая ошибка</b>\n{e}")
        
        # Увеличиваем счетчик попыток
        retry_count = min(retry_count + 1, max_retries)
        
        if retry_count >= max_retries:
            error_msg = "❌ <b>Максимум попыток переподключения достигнут</b>\n⏹️ Бот остановлен"
            logger.error(error_msg)
            send_telegram_to_user(error_msg)
            break
        
        logger.info(f"🔄 Мгновенное переподключение... (попытка {retry_count}/{max_retries})")
        # Без задержки - сразу переподключаемся

# VIP функции перенесены в отдельную систему vip_twitter_monitor.py

async def get_creator_token_history(creator_address):
    """Получает историю токенов создателя через Axiom API"""
    try:
        url = f"https://api8.axiom.trade/dev-tokens-v2?devAddress={creator_address}"
        
        # Заголовки для имитации браузера iPhone Safari
        import os
        axiom_cookies = os.getenv('AXIOM_COOKIES', '')
        
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
            'cache-control': 'max-age=0',
            'cookie': axiom_cookies,
            'priority': 'u=0, i',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1 Edg/137.0.0.0'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    # Получаем данные как текст и парсим вручную (Axiom API не отправляет Content-Type)
                    try:
                        # Сначала получаем как текст
                        text_data = await response.text()
                        
                        # Парсим JSON вручную
                        import json
                        data = json.loads(text_data)
                        
                        tokens = data.get('tokens', [])
                        counts = data.get('counts', {})
                        
                        total_count = counts.get('totalCount', 0)
                        migrated_count = counts.get('migratedCount', 0)
                    except (json.JSONDecodeError, ValueError) as e:
                        # Это не JSON - анализируем содержимое
                        text_data = await response.text()
                        logger.warning(f"⚠️ Axiom API вернул не-JSON ответ для {creator_address[:8]}...")
                        logger.debug(f"Содержимое ответа: {text_data[:300]}...")
                        
                        # Проверяем на страницу авторизации
                        if 'login' in text_data.lower() or 'sign in' in text_data.lower():
                            logger.error("🔑 Axiom API требует авторизации - обновите AXIOM_COOKIES")
                        elif 'blocked' in text_data.lower() or 'forbidden' in text_data.lower():
                            logger.error("🚫 Axiom API заблокировал запрос - возможно нужны новые заголовки")
                        
                        return {
                            'success': False, 
                            'error': f'JSON decode error: {str(e)}',
                            'total_tokens': 0,
                            'migrated_tokens': 0,
                            'recent_tokens': [],
                            'is_first_time': True,  # По умолчанию считаем первым токеном при ошибке
                            'is_serial_creator': False,
                            'success_rate': 0
                        }
                    
                    # Анализируем токены
                    recent_tokens = []
                    for token in tokens[:5]:  # Берем последние 5 токенов
                        recent_tokens.append({
                            'symbol': token.get('tokenTicker', 'UNK'),
                            'name': token.get('tokenName', 'Unknown'),
                            'created_at': token.get('createdAt', ''),
                            'migrated': token.get('migrated', False),
                            'liquidity_sol': token.get('liquiditySol', 0)
                        })
                    
                    logger.info(f"📊 История создателя {creator_address[:8]}...: {total_count} токенов, {migrated_count} мигрировано")
                    
                    return {
                        'success': True,
                        'total_tokens': total_count,
                        'migrated_tokens': migrated_count,
                        'recent_tokens': recent_tokens,
                        'is_first_time': total_count == 0,  # Будет True для первого токена
                        'is_serial_creator': total_count > 5,  # Много токенов = серийный создатель
                        'success_rate': (migrated_count / total_count * 100) if total_count > 0 else 0
                    }
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ Axiom API вернул статус {response.status} для создателя {creator_address[:8]}...")
                    logger.debug(f"Ответ сервера: {error_text[:200]}...")
                    
                    if response.status == 401:
                        logger.error("🔑 Axiom API: токены авторизации устарели! Обновите AXIOM_COOKIES в .env")
                    elif response.status == 403:
                        logger.error("🚫 Axiom API: доступ запрещен - проверьте куки и заголовки")
                    elif response.status == 500:
                        logger.error("⚙️ Axiom API: внутренняя ошибка сервера - попробуем позже")
                    
                    return {'success': False, 'error': f'HTTP {response.status}'}
                    
    except Exception as e:
        logger.error(f"❌ Ошибка получения истории создателя через Axiom API: {e}")
        return {'success': False, 'error': str(e)}

# *** ФУНКЦИЯ ПЕРЕНЕСЕНА В vip_twitter_monitor.py ***

# *** ФУНКЦИЯ ПЕРЕНЕСЕНА В vip_twitter_monitor.py ***

# *** ФУНКЦИЯ ПЕРЕНЕСЕНА В vip_twitter_monitor.py ***

# *** ФУНКЦИЯ ПЕРЕНЕСЕНА В vip_twitter_monitor.py ***

def format_token_creation_time(created_time):
    """Форматирует время создания токена в читаемый вид"""
    try:
        if not created_time or created_time == 'N/A':
            return "❓ Неизвестно"
        
        # Пробуем разные форматы времени
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%S.%fZ',  # 2025-06-29T04:23:36.123Z
            '%Y-%m-%dT%H:%M:%SZ',     # 2025-06-29T04:23:36Z
            '%Y-%m-%dT%H:%M:%S',      # 2025-06-29T04:23:36
            '%Y-%m-%d %H:%M:%S',      # 2025-06-29 04:23:36
        ]
        
        parsed_time = None
        for format_str in formats_to_try:
            try:
                parsed_time = datetime.strptime(created_time, format_str)
                break
            except ValueError:
                continue
        
        if parsed_time:
            # Форматируем в читаемый вид
            now = datetime.now()
            time_diff = now - parsed_time
            
            # Добавляем относительное время
            if time_diff.days > 0:
                relative_time = f"({time_diff.days} дн. назад)"
            elif time_diff.seconds > 3600:
                hours = time_diff.seconds // 3600
                relative_time = f"({hours} ч. назад)"
            elif time_diff.seconds > 60:
                minutes = time_diff.seconds // 60
                relative_time = f"({minutes} мин. назад)"
            else:
                relative_time = "(только что)"
            
            return f"📅 {parsed_time.strftime('%d.%m.%Y %H:%M:%S')} {relative_time}"
        else:
            return f"📅 {created_time}"
            
    except Exception as e:
        logger.debug(f"❌ Ошибка форматирования времени {created_time}: {e}")
        return f"📅 {created_time}"

def calculate_time_difference(original_time, duplicate_time):
    """Вычисляет и форматирует разницу во времени между созданием токенов"""
    try:
        if not original_time or not duplicate_time or original_time == 'N/A' or duplicate_time == 'N/A':
            return ""
        
        # Пробуем разные форматы времени
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
        ]
        
        original_parsed = None
        duplicate_parsed = None
        
        for format_str in formats_to_try:
            try:
                if not original_parsed:
                    original_parsed = datetime.strptime(original_time, format_str)
                if not duplicate_parsed:
                    duplicate_parsed = datetime.strptime(duplicate_time, format_str)
                if original_parsed and duplicate_parsed:
                    break
            except ValueError:
                continue
        
        if original_parsed and duplicate_parsed:
            time_diff = abs((duplicate_parsed - original_parsed).total_seconds())
            
            if time_diff < 60:
                diff_str = f"{int(time_diff)} сек."
            elif time_diff < 3600:
                minutes = int(time_diff // 60)
                seconds = int(time_diff % 60)
                diff_str = f"{minutes} мин. {seconds} сек."
            elif time_diff < 86400:
                hours = int(time_diff // 3600)
                minutes = int((time_diff % 3600) // 60)
                diff_str = f"{hours} ч. {minutes} мин."
            else:
                days = int(time_diff // 86400)
                hours = int((time_diff % 86400) // 3600)
                diff_str = f"{days} дн. {hours} ч."
            
            return f"⏰ <b>Разница во времени:</b> {diff_str}\n\n"
        
        return ""
        
    except Exception as e:
        logger.debug(f"❌ Ошибка вычисления разницы времени: {e}")
        return ""

# Устаревшие функции удалены - логика перенесена в database.py

def send_duplicate_alert(original_token, duplicate_token, reason, twitter_info=None):
    """Отправляет уведомление о найденном дубликате в тему 14 с улучшенным форматированием"""
    try:
        target_chat_id = -1002680160752  # ID группы
        message_thread_id = 14  # ID темы для дубликатов
        
        token1_id = original_token.get('id')
        token2_id = duplicate_token.get('id')
        
        # Извлекаем Twitter аккаунты для отображения
        token1_twitter = extract_twitter_accounts_from_token(original_token)
        token2_twitter = extract_twitter_accounts_from_token(duplicate_token)
        
        token1_twitter_display = f"@{', @'.join(token1_twitter)}" if token1_twitter else "N/A"
        token2_twitter_display = f"@{', @'.join(token2_twitter)}" if token2_twitter else "N/A"
        
        # Получаем правильно отформатированные даты
        token1_created = original_token.get('firstPool', {}).get('createdAt')
        token2_created = duplicate_token.get('firstPool', {}).get('createdAt')
        
        # Исправляем форматирование дат - убираем лишний префикс
        def format_creation_date(created_time):
            if not created_time or created_time == 'N/A':
                return "❓ Неизвестно"
            
            try:
                # Пробуем стандартный Jupiter формат
                if created_time.endswith('Z'):
                    parsed_time = datetime.fromisoformat(created_time[:-1])
                else:
                    parsed_time = datetime.fromisoformat(created_time)
                
                now = datetime.now()
                time_diff = now - parsed_time
                
                if time_diff.days > 0:
                    relative = f"({time_diff.days} дн. назад)"
                elif time_diff.seconds > 3600:
                    hours = time_diff.seconds // 3600
                    relative = f"({hours} ч. назад)"
                elif time_diff.seconds > 60:
                    minutes = time_diff.seconds // 60
                    relative = f"({minutes} мин. назад)"
                else:
                    relative = "(только что)"
                
                return f"{parsed_time.strftime('%d.%m.%Y %H:%M:%S')} {relative}"
            except Exception as e:
                logger.debug(f"❌ Ошибка парсинга даты {created_time}: {e}")
                return str(created_time)
        
        token1_created_formatted = format_creation_date(token1_created)
        token2_created_formatted = format_creation_date(token2_created)
        
        # Вычисляем разницу во времени
        time_diff_info = calculate_time_difference(token1_created, token2_created)
        
        # Анализируем Twitter информацию
        twitter_analysis = ""
        tweet_quote = ""
        
        if twitter_info:
            token1_announced = twitter_info.get('original_query') is not None
            token2_announced = twitter_info.get('duplicate_query') is not None
            
            token1_has_contract = twitter_info.get('original_has_contract', False)
            token2_has_contract = twitter_info.get('duplicate_has_contract', False)
            
            # Проверяем одинаковые ли твиты
            tweet1 = twitter_info.get('original_tweet', '')
            tweet2 = twitter_info.get('duplicate_tweet', '')
            
            if tweet1 and tweet2 and tweet1.strip() == tweet2.strip():
                # Твиты одинаковые - показываем как одну цитату
                tweet_quote = f"\n\n💬 <b>Найденный твит:</b>\n<blockquote>{tweet1}</blockquote>\n"
            else:
                # Твиты разные - показываем отдельно если есть
                if tweet1:
                    tweet_quote += f"\n💬 <b>Твит токена #1:</b>\n<blockquote>{tweet1}</blockquote>\n"
                if tweet2:
                    tweet_quote += f"\n💬 <b>Твит токена #2:</b>\n<blockquote>{tweet2}</blockquote>\n"
            
            # Формируем анализ статуса
            twitter_analysis = "\n🔍 <b>АНАЛИЗ TWITTER:</b>\n"
            
            # Статус токена #1
            if token1_announced:
                contract_status1 = "📍 КОНТРАКТ ЕСТЬ" if token1_has_contract else "❌ КОНТРАКТ НЕТ"
                twitter_analysis += f"1️⃣ <b>Токен #1:</b> ✅ анонсирован, {contract_status1}\n"
            else:
                twitter_analysis += f"1️⃣ <b>Токен #1:</b> ❌ не анонсирован\n"
            
            # Статус токена #2  
            if token2_announced:
                contract_status2 = "📍 КОНТРАКТ ЕСТЬ" if token2_has_contract else "❌ КОНТРАКТ НЕТ"
                twitter_analysis += f"2️⃣ <b>Токен #2:</b> ✅ анонсирован, {contract_status2}\n"
            else:
                twitter_analysis += f"2️⃣ <b>Токен #2:</b> ❌ не анонсирован\n"
        
        # Формируем основное сообщение
        message = (
            f"🔍 <b>НАЙДЕНЫ ПОХОЖИЕ ТОКЕНЫ!</b>\n\n"
            f"📋 <b>Причина схожести:</b> {reason}\n\n"
            f"1️⃣ <b>ТОКЕН #1:</b>\n"
            f"💎 <b>Название:</b> {original_token.get('name', 'N/A')}\n"
            f"🏷️ <b>Символ:</b> {original_token.get('symbol', 'N/A')}\n"
            f"📍 <b>Адрес:</b> <code>{token1_id}</code>\n"
            f"🐦 <b>Twitter:</b> {token1_twitter_display}\n"
            f"📅 <b>Создан:</b> {token1_created_formatted}\n\n"
            f"2️⃣ <b>ТОКЕН #2:</b>\n"
            f"💎 <b>Название:</b> {duplicate_token.get('name', 'N/A')}\n"
            f"🏷️ <b>Символ:</b> {duplicate_token.get('symbol', 'N/A')}\n"
            f"📍 <b>Адрес:</b> <code>{token2_id}</code>\n"
            f"🐦 <b>Twitter:</b> {token2_twitter_display}\n"
            f"📅 <b>Создан:</b> {token2_created_formatted}\n\n"
            f"{time_diff_info}"
            f"{twitter_analysis}"
            f"{tweet_quote}"
            f"⚠️ <b>Возможный шилинг похожих токенов!</b>\n"
            f"🕐 <b>Время обнаружения:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        

        
        # Отправляем текстовое сообщение
        text_payload = {
            "chat_id": target_chat_id,
            "message_thread_id": message_thread_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        text_response = requests.post(TELEGRAM_URL, json=text_payload)
        
        if text_response.status_code == 200:
            # Помечаем пару как отправленную через БД
            if token1_id and token2_id:
                db_manager = get_db_manager()
                db_manager.mark_duplicate_pair_as_sent(token1_id, token2_id)
            
            logger.info(f"✅ Уведомление о похожих токенах отправлено в тему {message_thread_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки текстового сообщения: {text_response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления о дубликате: {e}")
        return False

async def search_twitter_mentions(twitter_url, token_name, token_symbol, contract_address=None):
    """Ищет упоминания токена в Twitter используя ту же систему что и основной анализ"""
    try:
        if not twitter_url or not token_name:
            return None, None, None
            
        # Извлекаем username из Twitter URL
        import re
        username_match = re.search(r'(?:twitter\.com|x\.com)/([^/]+)', twitter_url)
        if not username_match:
            return None, None, None
            
        username = username_match.group(1)
        
        # Создаем поисковые запросы - символ доллара и контракт
        search_queries = []
        
        # 1. Приоритет 1 - символ с долларом (основной поиск)
        if token_symbol:
            search_queries.append({
                'query': f'"${token_symbol}"',
                'priority': 1,
                'type': 'dollar_symbol'
            })
        
        # 2. Приоритет 2 - контракт в кавычках (если есть)
        if contract_address:
            search_queries.append({
                'query': f'"{contract_address}"',
                'priority': 2,
                'type': 'quoted_contract'
            })
        
        # Используем новую динамическую систему куки с anubis_handler
        async with aiohttp.ClientSession() as temp_session:
            proxy, cookie = await get_next_proxy_cookie_async(temp_session)
        
        # Заголовки как в основной системе
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cookie': cookie
        }
        
        from bs4 import BeautifulSoup
        from urllib.parse import quote
        
        # Ищем по приоритету запросов
        for query_info in search_queries:
            query = query_info['query']
            query_type = query_info['type']
            priority = query_info['priority']
            
            # Формируем URL поиска как в основной системе
            search_url = f"https://nitter.tiekoetter.com/{username}/search?f=tweets&q={quote(query)}&since=&until=&near="
            
            # Retry механизм для каждого запроса (как в основной системе)
            for retry_attempt in range(3):  # до 3 попыток
                # Создаем НОВЫЙ connector для каждой попытки (исправляет Session is closed)
                connector = None
                request_kwargs = {}
                if proxy:
                    try:
                        connector = aiohttp.ProxyConnector.from_url(proxy)
                    except AttributeError:
                        connector = aiohttp.TCPConnector()
                        request_kwargs['proxy'] = proxy
                
                try:
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.get(search_url, headers=headers, timeout=20, **request_kwargs) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Проверяем на блокировку Nitter как в основной системе
                                title = soup.find('title')
                                if title and 'Making sure you\'re not a bot!' in title.get_text():
                                    logger.warning(f"🚫 Nitter заблокирован для поиска '{query}' в @{username} - пытаемся решить challenge")
                                    
                                    # 🔄 РЕШАЕМ ANUBIS CHALLENGE
                                    try:
                                        from anubis_handler import handle_anubis_challenge_for_session
                                        
                                        # Решаем challenge
                                        anubis_cookies = await handle_anubis_challenge_for_session(session, search_url, html)
                                        
                                        if anubis_cookies:
                                            logger.info(f"✅ Anubis challenge решен для поиска '{query}' в @{username}")
                                            
                                            # Обновляем куки и повторяем запрос
                                            from anubis_handler import update_cookies_in_string
                                            new_cookie = update_cookies_in_string(cookie, anubis_cookies)
                                            headers['Cookie'] = new_cookie
                                            
                                            # Повторяем запрос с новыми куками
                                            async with session.get(search_url, headers=headers, timeout=20, **request_kwargs) as retry_response:
                                                if retry_response.status == 200:
                                                    retry_html = await retry_response.text()
                                                    retry_soup = BeautifulSoup(retry_html, 'html.parser')
                                                    
                                                    # Проверяем что challenge исчез
                                                    retry_title = retry_soup.find('title')
                                                    if retry_title and 'Making sure you\'re not a bot!' not in retry_title.get_text():
                                                        logger.info(f"✅ Успешно преодолели блокировку для поиска '{query}' в @{username}")
                                                        soup = retry_soup  # Используем новый soup
                                                    else:
                                                        logger.error(f"❌ Challenge не решен для поиска '{query}' в @{username}")
                                                        break
                                                else:
                                                    logger.error(f"❌ Ошибка после решения challenge для поиска '{query}' в @{username}")
                                                    break
                                        else:
                                            logger.error(f"❌ Не удалось решить challenge для поиска '{query}' в @{username}")
                                            break
                                    except Exception as challenge_error:
                                        logger.error(f"❌ Ошибка при решении challenge для поиска '{query}' в @{username}: {challenge_error}")
                                        break
                                
                                tweets = soup.find_all('div', class_='timeline-item')
                                
                                if tweets and len(tweets) > 0:
                                    # Извлекаем текст первого найденного твита
                                    tweet_text = extract_first_tweet_text(tweets[0])
                                    logger.info(f"✅ Найдено упоминание '{query}' в Twitter @{username} (тип: {query_type}, приоритет: {priority})")
                                    return query, tweet_text, query_type
                                else:
                                    logger.debug(f"🚫 Упоминание '{query}' НЕ найдено в Twitter @{username}")
                                    break  # Нет смысла retry если твиты не найдены
                            elif response.status == 429:
                                if retry_attempt < 2:
                                    logger.warning(f"⚠️ Rate limit для поиска '{query}' в @{username} (попытка {retry_attempt + 1}/3)")
                                    await asyncio.sleep(0.1)  # Мини пауза
                                    continue  # Повторяем попытку
                                else:
                                    logger.warning(f"❌ Rate limit для поиска '{query}' в @{username} - превышены попытки")
                                    break
                            else:
                                logger.warning(f"⚠️ Не удалось проверить '{query}' в Twitter @{username}: {response.status}")
                                break  # Прерываем retry для HTTP ошибок
                                
                except Exception as e:
                    error_type = type(e).__name__
                    if retry_attempt < 2:
                        logger.warning(f"⚠️ Ошибка поиска '{query}' в @{username}: {error_type} (попытка {retry_attempt + 1}/3)")
                        await asyncio.sleep(0.1)  # Мини пауза перед retry
                        continue  # Повторяем попытку
                    else:
                        logger.error(f"❌ Превышены попытки поиска '{query}' в @{username}: {error_type} - {e}")
                        break  # Прерываем retry
                
                # Если дошли сюда - успешный результат или окончательная ошибка
                break
        
        # Ничего не найдено
        logger.debug(f"🚫 Никаких упоминаний токена не найдено в Twitter @{username}")
        return None, None, None
                    
    except Exception as e:
        logger.error(f"❌ Ошибка поиска упоминаний в Twitter: {e}")
        return None, None, None

def extract_first_tweet_text(tweet_element):
    """Извлекает текст из элемента твита"""
    try:
        # Ищем текст твита в различных элементах
        tweet_content = tweet_element.find('div', class_='tweet-content')
        if tweet_content:
            text = tweet_content.get_text().strip()
            # Ограничиваем длину текста
            if len(text) > 280:
                text = text[:280] + "..."
            return text
        
        # Если не нашли tweet-content, пробуем другие варианты
        text_elements = tweet_element.find_all(['p', 'div'], class_=lambda x: x and ('tweet' in x or 'content' in x))
        for element in text_elements:
            text = element.get_text().strip()
            if text and len(text) > 10:  # Минимальная длина для осмысленного текста
                if len(text) > 280:
                    text = text[:280] + "..."
                return text
        
        # Последняя попытка - просто весь текст элемента
        text = tweet_element.get_text().strip()
        if text:
            # Очищаем от лишних пробелов и переносов
            import re
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 280:
                text = text[:280] + "..."
            return text
            
        return "Текст твита не удалось извлечь"
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения текста твита: {e}")
        return "Ошибка извлечения текста"

async def check_twitter_contract_exists(twitter_url, contract_address):
    """Проверяет наличие контракта в Twitter через Nitter (для обратной совместимости)"""
    found_query, tweet_text, query_type = await search_twitter_mentions(twitter_url, "", "", contract_address)
    return found_query is not None

def extract_twitter_accounts_from_token(token_data):
    """Извлекает и нормализует Twitter аккаунты из всех полей токена"""
    twitter_accounts = set()
    
    # Поля где могут быть Twitter ссылки
    twitter_fields = ['twitter', 'website', 'telegram', 'social', 'links']
    
    for field in twitter_fields:
        url = token_data.get(field, '')
        if url and isinstance(url, str):
            account = normalize_twitter_url(url)
            if account:
                twitter_accounts.add(account)
    
    return list(twitter_accounts)

def normalize_twitter_url(url):
    """Нормализует Twitter URL, извлекая чистый аккаунт с сохранением оригинального регистра username"""
    try:
        if not url or not isinstance(url, str):
            return None
            
        original_url = url.strip()
        
        # Приводим к нижнему регистру только для проверки доменов
        url_lower = original_url.lower()
        
        # Проверяем что это Twitter/X ссылка (проверяем в нижнем регистре)
        if not any(domain in url_lower for domain in ['twitter.com', 'x.com']):
            return None
            
        # Пропускаем ссылки на комьюнити (проверяем в нижнем регистре)
        if '/communities/' in url_lower:
            logger.debug(f"🚫 Пропускаем комьюнити ссылку: {original_url}")
            return None
            
        # Пропускаем ссылки на твиты - только аккаунты без ссылок на конкретные посты
        if '/status/' in url_lower:
            logger.debug(f"🚫 Пропускаем ссылку на твит: {original_url}")
            return None
            
        # Извлекаем username из ОРИГИНАЛЬНОГО URL (с сохранением регистра)
        import re
        
        # Паттерн для извлечения username (case-insensitive для доменов)
        # Поддерживает: twitter.com/username, x.com/username, twitter.com/username/status/...
        username_pattern = r'(?i)(?:twitter\.com|x\.com)/([^/\?]+)'
        match = re.search(username_pattern, original_url)
        
        if match:
            username = match.group(1).strip()
            
            # Пропускаем служебные пути (проверяем в нижнем регистре)
            service_paths = ['i', 'home', 'search', 'notifications', 'messages', 'settings', 'intent']
            if username.lower() in service_paths:
                logger.debug(f"🚫 Пропускаем служебную ссылку: {original_url}")
                return None
                
            # Возвращаем username в ОРИГИНАЛЬНОМ регистре
            return username
            
    except Exception as e:
        logger.debug(f"❌ Ошибка нормализации Twitter URL {original_url}: {e}")
        
    return None

def tokens_are_similar(token1, token2, similarity_threshold=0.8):
    """Проверяет похожесть двух токенов по названию, символу и Twitter аккаунтам"""
    try:
        # Сравниваем основные поля
        name1 = token1.get('name', '').lower().strip()
        name2 = token2.get('name', '').lower().strip()
        
        symbol1 = token1.get('symbol', '').lower().strip()
        symbol2 = token2.get('symbol', '').lower().strip()
        
        # Извлекаем Twitter аккаунты из всех полей
        twitter_accounts1 = set(extract_twitter_accounts_from_token(token1))
        twitter_accounts2 = set(extract_twitter_accounts_from_token(token2))
        
        # Проверяем пересечения Twitter аккаунтов
        twitter_intersection = twitter_accounts1.intersection(twitter_accounts2)
        has_common_twitter = len(twitter_intersection) > 0
        
        # Проверяем точные совпадения
        exact_matches = 0
        total_checks = 0
        reasons = []
        
        # Название
        if name1 and name2:
            total_checks += 1
            if name1 == name2:
                exact_matches += 1
                reasons.append("одинаковое название")
        
        # Символ
        if symbol1 and symbol2:
            total_checks += 1
            if symbol1 == symbol2:
                exact_matches += 1
                reasons.append("одинаковый символ")
        
        # Twitter аккаунты
        if twitter_accounts1 and twitter_accounts2:
            total_checks += 1
            if has_common_twitter:
                exact_matches += 1
                common_accounts = ', '.join(twitter_intersection)
                reasons.append(f"общие Twitter аккаунты: @{common_accounts}")
        
        # Вычисляем схожесть
        if total_checks == 0:
            return False, "Недостаточно данных для сравнения"
        
        similarity = exact_matches / total_checks
        
        if similarity >= similarity_threshold:
            return True, f"Схожесть {similarity:.0%}: {', '.join(reasons)}"
        
        return False, f"Схожесть {similarity:.0%} - недостаточно для дубликата"
        
    except Exception as e:
        logger.error(f"❌ Ошибка сравнения токенов: {e}")
        return False, f"Ошибка сравнения: {e}"

async def process_duplicate_detection(new_token):
    """Обрабатывает новый токен для поиска дубликатов через базу данных"""
    try:
        if not duplicate_detection_enabled:
            return
            
        token_id = new_token.get('id')
        if not token_id:
            logger.debug("🚫 Токен пропущен - нет ID")
            return
        
        # Получаем менеджер БД
        db_manager = get_db_manager()
        
        # УБИРАЕМ проверку на обработку - хотим искать дубликаты для всех токенов
        # Каждый токен должен быть проверен на дубликаты хотя бы раз
        logger.debug(f"🔍 Обрабатываем токен {new_token.get('symbol', 'Unknown')} ({token_id[:8]}...) на дубликаты")
            
        # НОВАЯ СТРАТЕГИЯ: обрабатываем ВСЕ токены для определения главного Twitter в группах
        has_links = has_any_links(new_token)
        if has_links:
            logger.debug(f"🔗 Токен {new_token.get('symbol', 'Unknown')} ({token_id[:8]}...) имеет ссылки - добавляем в группы дубликатов для анализа Twitter")
        else:
            logger.info(f"🎯 ЧИСТЫЙ ТОКЕН БЕЗ ССЫЛОК: {new_token.get('symbol', 'Unknown')} ({token_id[:8]}...) - ищем дубликаты")
        
        # Ищем похожие токены в БД
        similar_tokens = db_manager.find_similar_tokens(new_token, similarity_threshold=0.8)
        duplicates_found = 0
        
        # Обрабатываем каждый похожий токен
        for similar_data in similar_tokens:
            stored_token_db = similar_data['token']
            similarity_score = similar_data['similarity'] 
            similarity_reasons = similar_data['reasons']
            
            stored_token_id = stored_token_db.mint
            
            # Проверяем, не отправляли ли мы уже эту пару
            if db_manager.is_duplicate_pair_already_sent(stored_token_id, token_id):
                logger.debug(f"🚫 Пара {stored_token_db.symbol} vs {new_token.get('symbol')} уже отправлена - пропускаем")
                continue
            
            logger.info(f"🔍 Найден возможный дубликат: {new_token.get('symbol')} ({token_id[:8]}...) похож на {stored_token_db.symbol} ({stored_token_id[:8]}...)")
            logger.info(f"🔍 Схожесть {similarity_score:.0%}: {', '.join(similarity_reasons)}")
            
            # Преобразуем объект БД в словарь для совместимости с существующим кодом
            stored_token = {
                'id': stored_token_db.mint,
                'name': getattr(stored_token_db, 'name', None),
                'symbol': getattr(stored_token_db, 'symbol', None),
                'icon': getattr(stored_token_db, 'icon', None),  # Безопасный доступ к icon (может не существовать)
                'twitter': getattr(stored_token_db, 'twitter', None),
                'telegram': getattr(stored_token_db, 'telegram', None),
                'website': getattr(stored_token_db, 'website', None)
            }
            
            # ПРОВЕРКА: у нового токена НЕТ ссылок, но проверяем есть ли ссылки у найденного дубликата
            stored_has_links = has_any_links(stored_token)
            new_has_links = has_any_links(new_token)  # Должно быть False, но проверим
            
            logger.info(f"📋 Сравнение: найденный дубликат {'🔗 ЕСТЬ ссылки' if stored_has_links else '🚫 БЕЗ ссылок'}, новый токен {'🔗 ЕСТЬ ссылки' if new_has_links else '🚫 БЕЗ ссылок'}")
            
            # Получаем Twitter аккаунты для проверки упоминаний (только у тех токенов где есть ссылки)
            stored_twitter_accounts = extract_twitter_accounts_from_token(stored_token) if stored_has_links else []
            new_twitter_accounts = extract_twitter_accounts_from_token(new_token) if new_has_links else []
            
            # Ищем упоминания токенов в Twitter
            original_found_query = None
            original_tweet_text = None
            original_query_type = None
            
            duplicate_found_query = None
            duplicate_tweet_text = None
            duplicate_query_type = None
            
            # Проверяем оригинальный токен
            for account in stored_twitter_accounts:
                twitter_url = f"https://x.com/{account}"
                query, tweet, query_type = await search_twitter_mentions(
                    twitter_url, 
                    stored_token.get('name', ''), 
                    stored_token.get('symbol', ''),
                    stored_token.get('id')
                )
                if query:
                    original_found_query = query
                    original_tweet_text = tweet
                    original_query_type = query_type
                    break
            
            # Проверяем дубликат
            for account in new_twitter_accounts:
                twitter_url = f"https://x.com/{account}"
                query, tweet, query_type = await search_twitter_mentions(
                    twitter_url, 
                    new_token.get('name', ''), 
                    new_token.get('symbol', ''),
                    new_token.get('id')
                )
                if query:
                    duplicate_found_query = query
                    duplicate_tweet_text = tweet
                    duplicate_query_type = query_type
                    break
            
            # НОВАЯ ЛОГИКА: анализ токенов БЕЗ ссылок vs С ссылками
            send_notification = False
            skip_reasons = []
            
            if not stored_has_links and not new_has_links:
                # Оба токена БЕЗ ссылок - возможно несколько команд делают один токен
                send_notification = True
                logger.info(f"🔥 НАЙДЕНЫ ДВА ЧИСТЫХ ТОКЕНА: {new_token.get('symbol')} - оба без ссылок, возможна конкуренция разработчиков!")
                
            elif stored_has_links and not new_has_links:
                # Старый токен СО ссылками, новый БЕЗ ссылок - новый может быть оригинал!
                send_notification = True
                logger.info(f"🎯 ПОТЕНЦИАЛЬНЫЙ ОРИГИНАЛ: {new_token.get('symbol')} БЕЗ ссылок появился после скам-токена СО ссылками!")
                
            elif not stored_has_links and new_has_links:
                # Старый токен БЕЗ ссылок, новый СО ссылками - добавляем в группу
                send_notification = True
                logger.info(f"🎯 ГРУППА ДУБЛИКАТОВ: {new_token.get('symbol')} - токен с ссылками + чистый токен!")
                
            else:
                # Оба со ссылками - тоже добавляем в группу
                send_notification = True
                logger.info(f"🔗 ГРУППА ДУБЛИКАТОВ: {new_token.get('symbol')} - оба токена с ссылками!")
            
            # Дополнительно анализируем Twitter если есть аккаунты
            if send_notification and (stored_twitter_accounts or new_twitter_accounts):
                # Анализируем упоминания токенов
                original_has_priority_mention = (original_query_type in ['hashtag_symbol', 'dollar_symbol', 'quoted_contract'] if original_query_type else False)
                duplicate_has_priority_mention = (duplicate_query_type in ['hashtag_symbol', 'dollar_symbol', 'quoted_contract'] if duplicate_query_type else False)
                
                # Если у токена СО ссылками нет упоминаний - это подозрительно
                if stored_has_links and stored_twitter_accounts and not original_has_priority_mention:
                    logger.info(f"🚨 ПОДОЗРИТЕЛЬНО: у токена со ссылками @{', @'.join(stored_twitter_accounts)} нет упоминаний токена!")
                
            if skip_reasons:
                logger.info(f"🚫 Дубликат {new_token.get('symbol')} пропущен: {', '.join(skip_reasons)}")
                db_manager.mark_duplicate_pair_as_sent(stored_token_id, token_id, similarity_score, similarity_reasons)
            elif send_notification:
                # Уведомление уже одобрено - отправляем
                if True:
                    # Создаем данные для уведомления (включая информацию о Twitter аккаунтах)
                    twitter_info = {
                        'stored_token_name': stored_token.get('name', ''),
                        'stored_token_symbol': stored_token.get('symbol', ''),
                        'stored_has_links': stored_has_links,
                        'new_token_name': new_token.get('name', ''),
                        'new_token_symbol': new_token.get('symbol', ''),
                        'new_has_links': new_has_links,
                        'stored_twitter_accounts': stored_twitter_accounts,
                        'new_twitter_accounts': new_twitter_accounts,
                        'analysis_type': 'mixed_tokens'
                    }
                    
                    # Формируем детальное описание ситуации
                    if stored_has_links and not new_has_links:
                        reason_text = f"🎯 ЧИСТЫЙ ТОКЕН + токен с ссылками. Схожесть {similarity_score:.0%}: {', '.join(similarity_reasons)}"
                    elif not stored_has_links and new_has_links:
                        reason_text = f"🎯 ТОКЕН С ССЫЛКАМИ + чистый токен. Схожесть {similarity_score:.0%}: {', '.join(similarity_reasons)}"
                    elif not stored_has_links and not new_has_links:
                        reason_text = f"🔥 КОНКУРЕНЦИЯ РАЗРАБОТЧИКОВ! Оба БЕЗ ссылок. Схожесть {similarity_score:.0%}: {', '.join(similarity_reasons)}"
                    else:
                        reason_text = f"🔗 ОБА С ССЫЛКАМИ. Схожесть {similarity_score:.0%}: {', '.join(similarity_reasons)}"
                    
                    # НОВАЯ СИСТЕМА: используем улучшенную систему групп дубликатов с Google Sheets
                    manager = get_duplicate_groups_manager()
                    if manager:
                        await manager.add_token_to_group(new_token, reason_text)
                    
                    # Отмечаем пару как отправленную
                    db_manager.mark_duplicate_pair_as_sent(stored_token_id, token_id, similarity_score, similarity_reasons)
                    duplicates_found += 1
                else:
                    logger.info(f"🚫 Дубликат {new_token.get('symbol')} пропущен: неопределенное состояние")
                    db_manager.mark_duplicate_pair_as_sent(stored_token_id, token_id, similarity_score, similarity_reasons)
        
        # Сохраняем новый токен в БД для будущих сравнений
        db_manager.save_duplicate_token(new_token)
        
        if duplicates_found > 0:
            logger.info(f"📊 Для токена {new_token.get('symbol')} найдено {duplicates_found} дубликатов")
        
        # Статистика общего количества токенов в БД
        total_tokens = db_manager.get_duplicate_tokens_count()
        logger.debug(f"📊 Общее количество токенов в БД дубликатов: {total_tokens}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки дубликатов: {e}")

async def check_twitter_account_has_any_contracts(twitter_username):
    """Проверяет наличие любых Solana контрактов в Twitter аккаунте"""
    try:
        # Используем новую динамическую систему куки с anubis_handler
        async with aiohttp.ClientSession() as temp_session:
            proxy, cookie = await get_next_proxy_cookie_async(temp_session)
        
        # Заголовки как в основной системе
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cookie': cookie
        }
        
        from bs4 import BeautifulSoup
        import re
        
        # Настройка прокси как в основной системе
        connector = None
        request_kwargs = {}
        if proxy:
            try:
                connector = aiohttp.ProxyConnector.from_url(proxy)
            except AttributeError:
                connector = aiohttp.TCPConnector()
                request_kwargs['proxy'] = proxy
        
        # Загружаем страницу пользователя
        profile_url = f"https://nitter.tiekoetter.com/{twitter_username}"
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(profile_url, headers=headers, timeout=20, **request_kwargs) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Проверяем на блокировку Nitter
                    title = soup.find('title')
                    if title and 'Making sure you\'re not a bot!' in title.get_text():
                        logger.warning(f"🚫 Nitter заблокирован для @{twitter_username}")
                        return False
                    
                    # Извлекаем весь текст со страницы
                    page_text = soup.get_text()
                    
                    # Ищем паттерны Solana контрактов (base58, 32-44 символа)
                    # Solana адреса обычно 44 символа, но могут быть короче
                    solana_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
                    
                    # Находим все потенциальные адреса
                    potential_addresses = re.findall(solana_pattern, page_text)
                    
                    if potential_addresses:
                        # Фильтруем адреса - исключаем слишком короткие и явно не контракты
                        valid_addresses = []
                        for addr in potential_addresses:
                            # Solana адреса обычно начинаются с определенных символов и имеют определенную длину
                            if len(addr) >= 40 and not addr.isdigit():
                                valid_addresses.append(addr)
                        
                        if valid_addresses:
                            logger.info(f"📍 Аккаунт @{twitter_username} содержит {len(valid_addresses)} контрактов: {valid_addresses[:3]}{'...' if len(valid_addresses) > 3 else ''}")
                            return True
                    
                    logger.debug(f"🔍 Аккаунт @{twitter_username} не содержит контрактов")
                    return False
                elif response.status == 429:
                    logger.warning(f"⚠️ Rate limit для проверки @{twitter_username}")
                    return False
                else:
                    logger.warning(f"⚠️ Не удалось проверить @{twitter_username}: {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Ошибка проверки контрактов в @{twitter_username}: {e}")
        return False

# СИСТЕМА ГРУППИРОВКИ ДУБЛЕЙ - собирает все дубли в одном сообщении
duplicate_groups = {}  # Хранит группы дублей: {group_key: {tokens: [], message_id: int, chat_id: int}}

def create_duplicate_group_key(token_data):
    """Создает ключ группы для токена (название + символ)"""
    name = token_data.get('name', '').strip().lower()
    symbol = token_data.get('symbol', '').strip().upper()
    return f"{name}_{symbol}"

def edit_telegram_message(chat_id, message_id, new_text, inline_keyboard=None):
    """Редактирует существующее сообщение в Telegram"""
    try:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        if inline_keyboard:
            payload["reply_markup"] = inline_keyboard
        
        edit_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
        response = requests.post(edit_url, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Ошибка редактирования сообщения: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")
        return False

def format_grouped_duplicate_message(group_data):
    """Форматирует сообщение для группы дублей с inline кнопками для контрактов"""
    tokens = group_data['tokens']
    
    if not tokens:
        return "❌ Нет токенов в группе", None
    
    # Берем первый токен как основу для названия группы
    first_token_info = tokens[0]
    first_token = first_token_info['token'] 
    token_name = first_token.get('name', 'Unknown')
    token_symbol = first_token.get('symbol', 'Unknown')
    
    # Разделяем токены на группы: с Twitter и без Twitter
    tokens_with_twitter = []
    tokens_without_twitter = []
    
    for token_info in tokens:
        token_data = token_info['token']
        twitter_accounts = extract_twitter_accounts_from_token(token_data)
        
        if twitter_accounts:
            tokens_with_twitter.append(token_info)
        else:
            tokens_without_twitter.append(token_info)
    
    # Сортируем по времени создания (новые сверху), обрабатываем None значения
    tokens_with_twitter.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    tokens_without_twitter.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    
    total_count = len(tokens)
    twitter_count = len(tokens_with_twitter)
    no_twitter_count = len(tokens_without_twitter)
    
    # Основное сообщение (КОРОТКОЕ, без контрактов)
    message = (
        f"🔍 <b>ГРУППА ДУБЛЕЙ: {token_name} ({token_symbol})</b>\n\n"
        f"📊 <b>Всего токенов:</b> {total_count}\n"
        f"🐦 <b>С официальным Twitter:</b> {twitter_count}\n"
        f"❌ <b>Без Twitter:</b> {no_twitter_count}\n\n"
    )
    
    # Анализ ситуации
    if twitter_count > 0 and no_twitter_count > 0:
        message += "⚠️ <b>ВНИМАНИЕ:</b> Есть токены с официальным Twitter и без него!\n"
        message += "🎯 <b>Возможный сценарий:</b> официальный токен запущен без Twitter, дубли добавили фейковые ссылки\n\n"
    elif twitter_count > 1:
        message += "🚨 <b>ПОДОЗРИТЕЛЬНО:</b> Несколько токенов с одинаковым Twitter!\n\n"
    elif no_twitter_count > 1:
        message += "🔍 <b>АНАЛИЗ:</b> Несколько токенов без социальных сетей\n\n"
    
    # Время последнего обновления
    message += f"🕐 <b>Последнее обновление:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    # Создаем inline клавиатуру с контрактами
    inline_keyboard = {"inline_keyboard": []}
    
    # Добавляем кнопки для токенов с Twitter
    if tokens_with_twitter:
        # Заголовок секции
        inline_keyboard["inline_keyboard"].append([{
            "text": f"✅ С TWITTER ({twitter_count})",
            "callback_data": "section_twitter"
        }])
        
        # Кнопки с контрактами (по 1 в ряду)
        for i, token_info in enumerate(tokens_with_twitter, 1):
            token_data = token_info['token']
            contract_full = token_data.get('id', 'Unknown')
            twitter_accounts = extract_twitter_accounts_from_token(token_data)
            created_time = token_info.get('created_at', 'Unknown')
            
            # Сокращаем контракт для отображения в кнопке
            contract_display = f"{contract_full[:8]}...{contract_full[-8:]}" if len(contract_full) > 20 else contract_full
            twitter_display = f"@{twitter_accounts[0]}" if twitter_accounts else ""
            time_display = format_creation_date_short(created_time)
            
            button_text = f"{i}. {contract_display} {twitter_display} ({time_display})"
            
            inline_keyboard["inline_keyboard"].append([{
                "text": button_text,
                "url": f"https://pump.fun/{contract_full}"
            }])
    
    # Добавляем кнопки для токенов без Twitter
    if tokens_without_twitter:
        # Заголовок секции
        inline_keyboard["inline_keyboard"].append([{
            "text": f"❌ БЕЗ TWITTER ({no_twitter_count})",
            "callback_data": "section_no_twitter"
        }])
        
        # Кнопки с контрактами (по 1 в ряду)  
        for i, token_info in enumerate(tokens_without_twitter, 1):
            token_data = token_info['token']
            contract_full = token_data.get('id', 'Unknown')
            created_time = token_info.get('created_at', 'Unknown')
            
            # Сокращаем контракт для отображения в кнопке
            contract_display = f"{contract_full[:8]}...{contract_full[-8:]}" if len(contract_full) > 20 else contract_full
            time_display = format_creation_date_short(created_time)
            
            button_text = f"{i}. {contract_display} ({time_display})"
            
            inline_keyboard["inline_keyboard"].append([{
                "text": button_text,
                "url": f"https://pump.fun/{contract_full}"
            }])
    
    return message, inline_keyboard

def format_creation_date_short(created_time):
    """Краткое форматирование даты создания"""
    if not created_time or created_time == 'Unknown':
        return "❓ Неизвестно"
    
    try:
        # Пробуем стандартный Jupiter формат
        if isinstance(created_time, str):
            if created_time.endswith('Z'):
                parsed_time = datetime.fromisoformat(created_time[:-1])
            else:
                parsed_time = datetime.fromisoformat(created_time)
        else:
            parsed_time = created_time
        
        now = datetime.now()
        time_diff = now - parsed_time
        
        if time_diff.days > 0:
            return f"{time_diff.days}д назад"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            return f"{hours}ч назад"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            return f"{minutes}м назад"
        else:
            return "только что"
    except Exception as e:
        logger.debug(f"❌ Ошибка парсинга даты {created_time}: {e}")
        return str(created_time)[:10]

async def send_or_update_grouped_duplicate_alert(token_data, reason="Обнаружен дубликат"):
    """Отправляет новое или обновляет существующее сообщение о группе дублей"""
    try:
        target_chat_id = -1002680160752  # ID группы
        message_thread_id = 14  # ID темы для дубликатов
        
        # Создаем ключ группы
        group_key = create_duplicate_group_key(token_data)
        
        # Подготавливаем данные токена с временной меткой
        token_info = {
            'token': token_data,
            'created_at': token_data.get('firstPool', {}).get('createdAt'),
            'reason': reason,
            'discovered_at': datetime.now().isoformat()
        }
        
        # Если группа не существует - создаем новую и отправляем ПОЛНУЮ группу из БД
        if group_key not in duplicate_groups:
            symbol = token_data.get('symbol', 'Unknown')
            
            # СНАЧАЛА отправляем полную группу из БД
            logger.info(f"🆕 Обнаружен ПЕРВЫЙ дубль символа {symbol} - отправляем ПОЛНУЮ группу из БД")
            auto_message_id = await send_full_duplicate_group_from_db(symbol)
            
            if auto_message_id:
                logger.info(f"✅ Автоматическая полная группа {symbol} отправлена, message_id: {auto_message_id}")
            else:
                logger.warning(f"⚠️ Не удалось отправить автоматическую полную группу {symbol}")
            
            # Создаем группу для дальнейших real-time обновлений
            duplicate_groups[group_key] = {
                'tokens': [token_info],
                'message_id': None,
                'chat_id': target_chat_id,
                'thread_id': message_thread_id,
                'first_seen': datetime.now().isoformat(),
                'auto_full_sent': True  # Флаг что полная группа уже отправлена
            }
            
            # НЕ отправляем обычное групповое сообщение, т.к. уже отправили полную группу
            logger.info(f"🔄 Группа {group_key} создана для дальнейших real-time обновлений (полная группа уже отправлена)")
            return True
        else:
            # Группа уже существует - добавляем токен и обновляем сообщение
            group = duplicate_groups[group_key]
            
            # Проверяем что токен еще не добавлен
            token_id = token_data.get('id')
            existing_ids = [t['token'].get('id') for t in group['tokens']]
            
            if token_id not in existing_ids:
                group['tokens'].append(token_info)
                
                # Обновляем сообщение с inline клавиатурой
                message_text, inline_keyboard = format_grouped_duplicate_message(group)
                
                if group['message_id']:
                    success = edit_telegram_message(
                        group['chat_id'], 
                        group['message_id'], 
                        message_text,
                        inline_keyboard
                    )
                    
                    if success:
                        logger.info(f"✅ Обновлена группа дублей: {token_data.get('symbol')} (токенов: {len(group['tokens'])})")
                        return True
                    else:
                        logger.error(f"❌ Не удалось обновить группу дублей: {token_data.get('symbol')}")
                        return False
                else:
                    logger.warning(f"⚠️ Группа {group_key} не имеет message_id для редактирования")
                    return False
            else:
                logger.debug(f"🔄 Токен {token_id[:8]}... уже в группе {group_key}")
                return True
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки групповых дублей: {e}")
        return False

async def send_full_duplicate_group_from_db(symbol):
    """🚀 НОВАЯ СИСТЕМА: Создает группу дубликатов через DuplicateGroupsManager с Google Sheets"""
    try:
        logger.info(f"🔍 Создаем НОВУЮ группу дубликатов для символа {symbol} с Google Sheets...")
        
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Получаем все токены этого символа из БД
        tokens = session.query(DuplicateToken).filter(
            DuplicateToken.normalized_symbol == symbol.lower()
        ).order_by(DuplicateToken.first_seen.desc()).all()
        
        session.close()
        
        if len(tokens) < 2:  # Нужно минимум 2 токена для группы
            logger.info(f"📊 Недостаточно токенов {symbol} для группы: {len(tokens)}")
            return None
            
        logger.info(f"📊 Найдено {len(tokens)} токенов {symbol} в БД")
        
        # Проверяем есть ли хотя бы у одного токена ВАЛИДНЫЙ Twitter аккаунт
        twitter_count = 0
        for token in tokens:
            token_data = {
                'twitter': token.twitter,
                'website': token.website,
                'telegram': token.telegram
            }
            
            twitter_accounts = extract_twitter_accounts_from_token(token_data)
            if twitter_accounts:
                twitter_count += 1
        
        logger.info(f"📊 Группа {symbol}: всего токенов {len(tokens)}, с валидными Twitter аккаунтами: {twitter_count}")
        
        if twitter_count == 0:
            logger.info(f"🚫 Группа {symbol} пропущена - нет валидных Twitter аккаунтов")
            return None
            
        # Выбираем первый токен (самый новый) для создания группы
        first_token = tokens[0]
        test_token_data = {
            'id': first_token.mint,
            'name': first_token.name,
            'symbol': first_token.symbol,
            'icon': first_token.icon,
            'twitter': first_token.twitter,
            'telegram': first_token.telegram,
            'website': first_token.website,
            'firstPool': {
                'createdAt': first_token.created_at.isoformat() if first_token.created_at else None
            }
        }
        
        # 🚀 ИСПОЛЬЗУЕМ НОВУЮ СИСТЕМУ ГРУПП ДУБЛИКАТОВ
        manager = get_duplicate_groups_manager()
        if not manager:
            logger.error("❌ DuplicateGroupsManager не инициализирован")
            return None
            
        success = await manager.add_token_to_group(
            test_token_data, 
            f"🧪 ТЕСТОВАЯ ПОЛНАЯ ГРУППА {symbol.upper()} из БД"
        )
        
        if success:
            # Получаем group_key и сообщение ID
            group_key = manager.create_group_key(test_token_data)
            group = manager.groups.get(group_key)
            
            if group:
                logger.info(f"✅ НОВАЯ система: группа {symbol} создана с Google Sheets!")
                logger.info(f"📊 Google Sheets URL: {group.sheet_url}")
                logger.info(f"📩 Telegram message ID: {group.message_id}")
                return group.message_id
            else:
                logger.error(f"❌ Группа {group_key} не найдена после создания")
                return None
        else:
            logger.error(f"❌ Не удалось создать группу через НОВУЮ систему")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания НОВОЙ группы для {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

def has_any_links(token_data):
    """Проверяет есть ли у токена какие-либо ссылки (twitter, website, telegram и т.д.)"""
    link_fields = ['twitter', 'website', 'telegram', 'discord', 'social', 'links']
    
    for field in link_fields:
        value = token_data.get(field)
        if value and isinstance(value, str) and value.strip():
            return True
    
    return False

async def check_official_contract_in_main_twitter(group_key: str, main_twitter: str, contracts_to_check: list) -> bool:
    """Проверяет наличие официального контракта в главном Twitter аккаунте группы дубликатов"""
    try:
        if not main_twitter or not contracts_to_check:
            return False
        
        logger.info(f"🔍 Проверяем официальный контракт в @{main_twitter} для группы {group_key}")
        
        # Используем существующую систему поиска контрактов в Twitter
        twitter_url = f"https://x.com/{main_twitter}"
        
        for contract in contracts_to_check:
            # Проверяем есть ли контракт в Twitter
            found = await check_twitter_contract_exists(twitter_url, contract)
            
            if found:
                # Официальный контракт найден!
                logger.info(f"✅ Официальный контракт {contract[:8]}... найден в @{main_twitter}")
                
                # Отмечаем в системе групп дубликатов
                manager = get_duplicate_groups_manager()
                if manager:
                    await manager.mark_official_contract_found(
                        group_key, 
                        contract,
                        datetime.now().strftime('%d.%m.%Y %H:%M')
                    )
                
                return True
        
        logger.debug(f"❌ Официальные контракты не найдены в @{main_twitter}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки официального контракта в @{main_twitter}: {e}")
        return False

async def monitor_official_contracts_for_groups():
    """Периодический мониторинг официальных контрактов для всех активных групп"""
    try:
        manager = get_duplicate_groups_manager()
        if not manager or not manager.groups:
            logger.debug("🔍 Нет активных групп для мониторинга")
            return
        
        active_groups = [g for g in manager.groups.values() 
                        if not g.official_contract and g.main_twitter]
        
        if not active_groups:
            logger.debug("🔍 Нет групп требующих мониторинга контрактов")
            return
        
        logger.info(f"🔍 Мониторинг контрактов для {len(active_groups)} групп дубликатов")
        
        for group in active_groups:
            # Собираем все контракты из группы
            contracts_to_check = [token.get('id') for token in group.tokens if token.get('id')]
            
            if contracts_to_check:
                await check_official_contract_in_main_twitter(
                    group.group_key, 
                    group.main_twitter, 
                    contracts_to_check
                )
                
                # Пауза между проверками чтобы не перегружать Twitter
                await asyncio.sleep(3)
        
    except Exception as e:
        logger.error(f"❌ Ошибка мониторинга официальных контрактов: {e}")

def handle_telegram_callback(callback_query):
    """Обработчик callback'ов от Telegram кнопок"""
    try:
        callback_data = callback_query.get('data', '')
        
        if callback_data.startswith('delete_group:'):
            # Извлекаем group_key
            group_key = callback_data.replace('delete_group:', '')
            
            # Удаляем группу асинхронно
            manager = get_duplicate_groups_manager()
            if manager:
                asyncio.create_task(manager.delete_group(group_key))
            
            # Отвечаем на callback
            callback_id = callback_query.get('id')
            answer_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
            answer_payload = {
                "callback_query_id": callback_id,
                "text": "✅ Группа дубликатов удалена"
            }
            requests.post(answer_url, json=answer_payload)
            
            logger.info(f"✅ Группа дубликатов {group_key} удалена по запросу пользователя")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки callback: {e}")
        return False
    
    return False

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал завершения работы")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в main: {e}")
    finally:
        # Корректно завершаем работу менеджера групп дубликатов
        shutdown_duplicate_groups_manager()
        logger.info("👋 Программа завершена") 