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
from cookie_rotation import cookie_rotator, background_cookie_rotator
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
    "5542434203",  # Дополнительный чат 1
    "1424887871"   # Дополнительный чат 2
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
    # Добавьте других нежелательных авторов здесь
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

async def search_single_query(query, headers, retry_count=0, use_quotes=True, cycle_cookie=None):
    """Выполняет одиночный поисковый запрос к Nitter с повторными попытками при 429 и ротацией cookies"""
    if use_quotes:
        url = f"https://nitter.tiekoetter.com/search?f=tweets&q=%22{query}%22&since=&until=&near="
    else:
        url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quote(query)}&since=&until=&near="
    
    # Используем переданный cookie для цикла или получаем новый
    if cycle_cookie:
        current_cookie = cycle_cookie
    else:
        current_cookie = cookie_rotator.get_next_cookie()
    
    # Обновляем заголовки с cookie
    headers_with_cookie = headers.copy()
    headers_with_cookie['Cookie'] = current_cookie
    
    try:
        # Используем asyncio совместимую библиотеку
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers_with_cookie, timeout=20) as response:
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
                        pause_time = 1  # МИНИМАЛЬНАЯ пауза при 429
                        logger.warning(f"⚠️ Nitter 429 (Too Many Requests) для '{query}', ждём {pause_time}с (попытка {retry_count + 1}/2)")
                        await asyncio.sleep(pause_time)
                        return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie)
                    else:
                        # Только после 2 попыток помечаем cookie как временно недоступный
                        if not cycle_cookie:  # Помечаем только если НЕ используется cycle_cookie
                            cookie_rotator.mark_cookie_failed(current_cookie)
                            logger.warning(f"❌ [PUMP_BOT] Cookie помечен как неработающий после 429 ошибок")
                        logger.error(f"❌ Nitter 429 (Too Many Requests) для '{query}' - превышено количество попыток")
                        return []
                else:
                    logger.warning(f"❌ Nitter ответил {response.status} для '{query}'")
                    return []
                    
    except Exception as e:
        logger.error(f"Ошибка запроса к Nitter для '{query}': {type(e).__name__}: {e}")
        
        # Повторная попытка при любых ошибках (не только 429)
        if retry_count < 3:
            logger.warning(f"⚠️ Повторная попытка для '{query}' после ошибки {type(e).__name__} (попытка {retry_count + 1}/3)")
            # await asyncio.sleep(1)  # УБИРАЕМ ПАУЗЫ
            return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie)
        else:
            logger.error(f"❌ Превышено количество попыток для '{query}' - возвращаем пустой результат")
            return []

async def analyze_token_sentiment(mint, symbol, cycle_cookie=None):
    """Анализ упоминаний токена в Twitter через Nitter (4 запроса с дедупликацией)"""
    try:
        # Получаем один cookie для всего анализа токена (4 запроса)
        if not cycle_cookie:
            cycle_cookie = cookie_rotator.get_cycle_cookie()
            logger.debug(f"🍪 Используем один cookie для анализа токена {symbol}")
            
        # Базовые заголовки без cookie (cookie будет добавлен в search_single_query)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 4 запроса: символ и контракт, каждый с кавычками и без
        search_queries = [
            (f'${symbol}', True),   # Символ с кавычками
            (f'${symbol}', False),  # Символ без кавычек
            (mint, True),           # Контракт с кавычками
            (mint, False)           # Контракт без кавычек
        ]
        
        # Выполняем запросы последовательно с паузами для избежания блокировки
        results = []
        for i, (query, use_quotes) in enumerate(search_queries):
            try:
                result = await search_single_query(query, headers, use_quotes=use_quotes, cycle_cookie=cycle_cookie)
                results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка запроса {i+1}: {e}")
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
                    if i < 2:  # Первые 2 запроса - символ
                        symbol_tweets_count += 1
                    else:  # Последние 2 запроса - контракт
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
            'contract_authors': []
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
            'contract_authors': contract_authors
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
            'contract_authors': []
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
    
    # Получаем bondingCurveKey
    bonding_curve_key = data.get('bondingCurveKey', 'Not available')
    
    message = (
        f"🚀 <b>НОВЫЙ ТОКЕН НА PUMP.FUN!</b>\n\n"
        f"<b>💎 <a href='https://pump.fun/{mint}'>{name}</a></b>\n"
        f"<b>🏷️ Символ:</b> {symbol}\n"
        f"<b>📍 Mint:</b> <code>{mint}</code>\n"
        f"<b>🔗 Bonding Curve:</b> <code>{bonding_curve_key}</code>\n"
        f"<b>👤 Создатель:</b> <code>{creator[:8] if len(creator) > 8 else creator}...</code>\n"
        f"<b>💰 Начальная покупка:</b> {initial_buy} SOL\n"
        f"<b>📊 Market Cap:</b> ${market_cap:,.0f}\n"
        f"<b>👨‍💼 Доля создателя:</b> {creator_percentage}%\n"
        f"<b>🐦 Twitter активность:</b> {twitter_analysis['rating']}\n"
        f"<b>📈 Твиты:</b> {twitter_analysis['tweets']} | <b>Активность:</b> {twitter_analysis['engagement']} | <b>Скор:</b> {twitter_analysis['score']}\n"
        f"<b>🔍 Поиск:</b> Символ: {twitter_analysis['symbol_tweets']} | Контракт: {twitter_analysis['contract_tweets']} {'✅' if twitter_analysis['contract_found'] else '❌'}\n"
        f"<b>📝 Описание:</b> {description}\n"
    )
    
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
        message += f"\n\n<b>👥 АВТОРЫ ТВИТОВ С КОНТРАКТОМ:</b>\n"
        for i, author in enumerate(authors[:3]):  # Показываем максимум 3 авторов
            username = author.get('username', 'Unknown')
            display_name = author.get('display_name', username)
            followers = author.get('followers_count', 0)
            verified = "✅" if author.get('is_verified', False) else ""
            tweet_text = author.get('tweet_text', '')[:100] + "..." if len(author.get('tweet_text', '')) > 100 else author.get('tweet_text', '')
            
            message += f"{i+1}. <b>@{username}</b> {verified}\n"
            if display_name != username:
                message += f"   📝 {display_name}\n"
            message += f"   👥 {followers:,} подписчиков\n"
            message += f"   💬 \"{tweet_text}\"\n"
    
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
    
    return message, keyboard, should_notify

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
            msg, keyboard, should_notify = await format_new_token(data)
            
            if should_notify:
                logger.info(f"✅ Токен {symbol} прошел фильтрацию - отправляем уведомление")
                send_telegram(msg, keyboard)
                
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
        await asyncio.wait_for(pong_waiter, timeout=10)
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
        
        for tweet in tweets:
            # Извлекаем имя автора
            author_link = tweet.find('a', class_='username')
            if author_link:
                author_username = author_link.get_text(strip=True).replace('@', '')
                
                # Проверяем черный список авторов
                if author_username.lower() in TWITTER_AUTHOR_BLACKLIST:
                    logger.info(f"🚫 Автор @{author_username} в черном списке - пропускаем")
                    continue
                
                # Извлекаем текст твита
                tweet_content = tweet.find('div', class_='tweet-content')
                tweet_text = tweet_content.get_text(strip=True) if tweet_content else ""
                
                # Извлекаем дату твита
                tweet_date = tweet.find('span', class_='tweet-date')
                tweet_date_text = tweet_date.get_text(strip=True) if tweet_date else ""
                
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
                    'tweet_text': tweet_text[:200],  # Ограничиваем длину
                    'tweet_date': tweet_date_text,
                    'retweets': retweets,
                    'likes': likes,
                    'replies': replies,
                    'query': query
                })
                
                logger.info(f"📝 Найден автор твита: @{author_username} для запроса '{query}'")
        
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
                        # Проверяем возраст данных (обновляем если старше 24 часов)
                        time_since_update = datetime.utcnow() - existing_author.last_updated
                        hours_since_update = time_since_update.total_seconds() / 3600
                        
                        if hours_since_update >= 24:
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
                            logger.info(f"🔄 Автор @{username} найден в БД, но данные устарели ({hours_since_update:.1f}ч) - нужно обновление")
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
                            logger.info(f"📋 Автор @{username} найден в БД ({existing_author.followers_count:,} подписчиков, обновлен {hours_since_update:.1f}ч назад)")
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
                        'avatar_url': profile.get('avatar_url', '')
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
                    if total_analyzed_tweets < 3:
                        logger.warning(f"⚠️ @{username}: недостаточно твитов для анализа ({total_analyzed_tweets}) - помечаем как подозрительного")
                        page_analysis['is_spam_likely'] = True
                        page_analysis['spam_analysis'] = f"Недостаточно данных: только {total_analyzed_tweets} твитов"
                        page_analysis['recommendation'] = "⚠️ ПОДОЗРИТЕЛЬНЫЙ - мало твитов"
                    
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
                    
                    logger.info(f"📊 @{username}: {page_analysis['total_tweets_on_page']} твитов, {page_analysis['max_contract_spam_percent']:.1f}% концентрация - {page_analysis['recommendation']}")
                    
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
        
        return unique_authors
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга авторов: {e}")
        return []

async def twitter_analysis_worker():
    """Фоновый обработчик для анализа Twitter (работает параллельно с основным потоком)"""
    logger.info("🔄 Запущен фоновый обработчик анализа Twitter")
    
    while True:
        try:
            # Получаем токен из очереди
            token_data = await twitter_analysis_queue.get()
            
            if token_data is None:  # Сигнал для завершения
                break
                
            mint = token_data['mint']
            symbol = token_data['symbol']
            
            logger.info(f"🔍 Начинаем фоновый анализ токена {symbol} в Twitter...")
            
            # Выполняем анализ Twitter
            twitter_analysis = await analyze_token_sentiment(mint, symbol)
            
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
            
            # УБИРАЕМ ПАУЗЫ - максимальная скорость
            # await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в фоновом анализе Twitter: {e}")
            await asyncio.sleep(1)  # Минимальная пауза только при ошибке

def should_notify_based_on_authors_quality(authors):
    """
    Проверяет качество авторов для отложенных уведомлений
    ИСПРАВЛЕННАЯ ЛОГИКА: фокус на одном контракте = хорошо, много разных = плохо
    """
    if not authors:
        return False  # Нет авторов - не отправляем
    
    excellent_authors = 0  # Вспышки активности (≥80%)
    good_authors = 0       # Хорошие авторы (≥40%)
    new_accounts = 0       # Новые аккаунты (≤2 твитов)
    spam_authors = 0       # Спамеры разных контрактов
    
    for author in authors:
        diversity_percent = author.get('contract_diversity', 0)
        spam_percent = author.get('max_contract_spam', 0)
        total_tweets = author.get('total_contract_tweets', 0)
        username = author.get('username', 'Unknown')
        
        # ПРОВЕРКА НА ОТСУТСТВИЕ ДАННЫХ АНАЛИЗА
        if total_tweets == 0 and spam_percent == 0 and diversity_percent == 0:
            logger.warning(f"⚠️ @{username}: недостаточно данных для анализа ({total_tweets} твитов) - пропускаем")
            continue
        
        # НОВАЯ ЛОГИКА: малое количество твитов = потенциально хороший сигнал
        if total_tweets <= 2:
            new_accounts += 1
            logger.info(f"🆕 @{username}: новый аккаунт ({total_tweets} твитов) - потенциальный сигнал")
            continue
        
        # Анализируем концентрацию на одном контракте
        if spam_percent >= 80:
            excellent_authors += 1
            logger.info(f"🔥 @{username}: ВСПЫШКА! ({spam_percent:.1f}% концентрация на одном контракте)")
        elif spam_percent >= 40:
            good_authors += 1
            logger.info(f"⭐ @{username}: ХОРОШИЙ ({spam_percent:.1f}% концентрация на одном контракте)")
        elif diversity_percent >= 30:
            # Много РАЗНЫХ контрактов = плохо
            spam_authors += 1
            logger.info(f"🚫 @{username}: СПАМЕР РАЗНЫХ ТОКЕНОВ ({diversity_percent:.1f}% разных контрактов)")
        elif spam_percent >= 20:
            # Умеренная концентрация - принимаем
            good_authors += 1
            logger.info(f"🟡 @{username}: умеренная концентрация ({spam_percent:.1f}%) - принимаем")
        else:
            # НИЗКАЯ концентрация И низкое разнообразие = подозрительно
            spam_authors += 1
            logger.info(f"🚫 @{username}: НИЗКОЕ КАЧЕСТВО ({spam_percent:.1f}% концентрация, {diversity_percent:.1f}% разнообразие) - отклоняем")
    
    # СМЯГЧЕННЫЕ КРИТЕРИИ: отправляем если есть хорошие сигналы
    should_notify = excellent_authors > 0 or good_authors > 0 or new_accounts > 0
    
    logger.info(f"📊 ИСПРАВЛЕННЫЙ АНАЛИЗ АВТОРОВ (отложенные уведомления):")
    logger.info(f"   🔥 Вспышки (≥80%): {excellent_authors}")
    logger.info(f"   ⭐ Хорошие (≥40%): {good_authors}")
    logger.info(f"   🆕 Новые аккаунты (≤2 твитов): {new_accounts}")
    logger.info(f"   🚫 Спамеры разных токенов: {spam_authors}")
    logger.info(f"   🎯 РЕШЕНИЕ: {'ОТПРАВИТЬ' if should_notify else 'ЗАБЛОКИРОВАТЬ'}")
    
    if not should_notify:
        logger.info(f"🚫 Отложенное уведомление заблокировано - только спамеры разных токенов")
    
    return should_notify

def should_send_delayed_notification(twitter_analysis, symbol, mint):
    """Проверяет нужно ли отправить отложенное уведомление после анализа Twitter"""
    if not twitter_analysis['contract_found']:
        return False
    
    # ПРОВЕРЯЕМ НА ДУБЛИРОВАНИЕ - уже отправлялось ли уведомление
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Ищем токен в БД
        db_token = session.query(Token).filter_by(mint=mint).first()
        if db_token and db_token.notification_sent:
            logger.info(f"🚫 Отложенное уведомление для {symbol} уже отправлялось ранее - пропускаем дублирование")
            session.close()
            return False
        
        session.close()
    except Exception as e:
        logger.error(f"❌ Ошибка проверки дублирования уведомления для {symbol}: {e}")
    
    # Проверяем качество авторов
    authors = twitter_analysis.get('contract_authors', [])
    if not should_notify_based_on_authors_quality(authors):
        logger.info(f"🚫 Отложенное уведомление для {symbol} заблокировано - все авторы являются спамерами")
        return False
        
    # Критерии для отложенного уведомления
    high_activity = (
        twitter_analysis['score'] >= 10 or
        twitter_analysis['tweets'] >= 5 or
        'высокий' in twitter_analysis['rating'].lower()
    )
    
    if high_activity:
        logger.info(f"📢 Токен {symbol} показал высокую активность в Twitter - отправляем отложенное уведомление")
        return True
        
    return False

async def send_delayed_twitter_notification(token_data, twitter_analysis):
    """Отправляет отложенное уведомление после анализа Twitter"""
    try:
        mint = token_data['mint']
        symbol = token_data['symbol']
        name = token_data.get('name', 'Unknown Token')
        
        message = (
            f"🔥 <b>ВЫСОКАЯ АКТИВНОСТЬ В TWITTER!</b>\n\n"
            f"<b>💎 {name} ({symbol})</b>\n"
            f"<b>📍 Mint:</b> <code>{mint}</code>\n\n"
            f"<b>🐦 Twitter анализ:</b> {twitter_analysis['rating']}\n"
            f"<b>📈 Твиты:</b> {twitter_analysis['tweets']} | <b>Активность:</b> {twitter_analysis['engagement']} | <b>Скор:</b> {twitter_analysis['score']}\n"
            f"<b>🔍 Поиск:</b> Символ: {twitter_analysis['symbol_tweets']} | Контракт: {twitter_analysis['contract_tweets']} ✅\n\n"
            f"⚡ <b>Обнаружена повышенная активность после анализа!</b>\n"
            f"<b>🕐 Время:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        
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
        
        send_telegram(message, keyboard)
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
            recommendation = "⚪ Нет контрактов в твитах"
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
        elif diversity_percent >= 50:
            is_spam_likely = True
            recommendation = "🚫 ПЛОХОЙ - слишком много разных контрактов"
            spam_analysis = f"Низкое качество: {diversity_percent:.1f}% разных контрактов - нет фокуса"
        else:
            is_spam_likely = True
            recommendation = "⚠️ ПОДОЗРИТЕЛЬНЫЙ - много разных контрактов"
            spam_analysis = f"Подозрительно: {diversity_percent:.1f}% разнообразия - нет концентрации интереса"
        
        # Топ-5 наиболее упоминаемых контрактов
        top_contracts = sorted(contract_mentions.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_tweets': total_tweets,
            'unique_contracts': unique_contracts,
            'contract_diversity_percent': round(diversity_percent, 1),
            'max_contract_spam_percent': round(max_contract_spam_percent, 1),
            'is_spam_likely': is_spam_likely,
            'recommendation': recommendation,
            'contracts_list': [{'contract': contract, 'mentions': count} for contract, count in top_contracts],
            'diversity_category': get_diversity_category(max_contract_spam_percent),
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
        
        try:
            from twitter_profile_parser import TwitterProfileParser
            
            async with TwitterProfileParser() as profile_parser:
                profile_data, profile_tweets = await profile_parser.get_profile_with_tweets(author_username)
                
                if profile_tweets:
                    tweets_on_page = profile_tweets
                    logger.info(f"📱 Загружено {len(profile_tweets)} твитов с профиля @{author_username}")
                else:
                    logger.warning(f"⚠️ Не удалось загрузить твиты с профиля @{author_username}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки твитов с профиля @{author_username}: {e}")
    
    if not tweets_on_page:
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
    logger.info("🔄 Запущен фоновый обработчик анализа Twitter")
    
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