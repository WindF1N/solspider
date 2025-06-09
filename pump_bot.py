import asyncio
import websockets
import json
import requests
import logging
import os
from datetime import datetime
from bs4 import BeautifulSoup
import re
import time

# Загрузка переменных окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv не установлен, используем системные переменные окружения
    pass

# Импорт модулей проекта
from logger_config import setup_logging, log_token_analysis, log_trade_activity, log_database_operation, log_daily_stats
from database import get_db_manager
from connection_monitor import connection_monitor

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

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

async def search_single_query(query, headers):
    """Выполняет одиночный поисковый запрос к Nitter"""
    url = f"https://nitter.tiekoetter.com/search?f=tweets&q=%22{query}%22"
    
    try:
        # Используем asyncio совместимую библиотеку
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Находим все твиты
                    tweets = soup.find_all('div', class_='timeline-item')
                    tweet_count = len(tweets)
                    
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
                    
                    logger.info(f"🔍 Nitter анализ '{query}': {tweet_count} твитов, активность: {engagement}")
                    return tweet_count, engagement
                else:
                    logger.warning(f"❌ Nitter ответил {response.status} для '{query}'")
                    return 0, 0
                    
    except Exception as e:
        logger.error(f"Ошибка запроса к Nitter для '{query}': {e}")
        return 0, 0

async def analyze_token_sentiment(mint, symbol):
    """Анализ упоминаний токена в Twitter через Nitter (параллельно)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Cookie': NITTER_COOKIE,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Параллельные запросы по символу и адресу контракта
        search_queries = [f'${symbol}', mint]
        
        # Выполняем оба запроса параллельно
        results = await asyncio.gather(
            search_single_query(search_queries[0], headers),  # Символ токена
            search_single_query(search_queries[1], headers),  # Адрес контракта
            return_exceptions=True
        )
        
        # Обрабатываем результаты
        symbol_tweets, symbol_engagement = results[0] if not isinstance(results[0], Exception) else (0, 0)
        contract_tweets, contract_engagement = results[1] if not isinstance(results[1], Exception) else (0, 0)
        
        total_tweets = symbol_tweets + contract_tweets
        total_engagement = symbol_engagement + contract_engagement
        
        # Рассчитываем рейтинг токена
        if total_tweets == 0:
                    return {
            'tweets': 0,
            'symbol_tweets': 0,
            'contract_tweets': 0,
            'engagement': 0,
            'score': 0,
            'rating': '🔴 Мало внимания',
            'contract_found': False
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
            'symbol_tweets': symbol_tweets,
            'contract_tweets': contract_tweets,
            'engagement': total_engagement,
            'score': round(score, 1),
            'rating': rating,
            'contract_found': contract_tweets > 0
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
            'contract_found': False
        }

async def format_new_token(data):
    """Форматирование сообщения о новом токене с полной информацией"""
    mint = data.get('mint', 'Unknown')
    name = data.get('name', 'Unknown Token')
    symbol = data.get('symbol', 'UNK')
    description = data.get('description', 'Нет описания')
    creator = data.get('traderPublicKey', 'Unknown')
    
    # Анализируем упоминания в Twitter
    logger.info(f"🔍 Анализируем токен {symbol} в Twitter...")
    twitter_analysis = await analyze_token_sentiment(mint, symbol)
    
    # Сохраняем токен в базу данных
    try:
        db_manager = get_db_manager()
        saved_token = db_manager.save_token(data, twitter_analysis)
        log_database_operation("SAVE_TOKEN", "tokens", "SUCCESS", f"Symbol: {symbol}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения токена в БД: {e}")
        log_database_operation("SAVE_TOKEN", "tokens", "ERROR", str(e))
    
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
    
    # Проверяем, стоит ли отправлять уведомление на основе Twitter активности
    should_notify = (
        twitter_analysis['contract_found'] and (  # НОВЫЙ ФИЛЬТР: адрес контракта найден в Twitter
            twitter_analysis['score'] >= 5 or  # Минимальный скор
            twitter_analysis['tweets'] >= 3 or  # Минимум 3 твита
            'высокий' in twitter_analysis['rating'].lower() or  # Высокий интерес
            'средний' in twitter_analysis['rating'].lower()    # Средний интерес
        )
    )
    
    # Дополнительное логирование фильтрации
    if not twitter_analysis['contract_found']:
        logger.info(f"🚫 Токен {symbol} отфильтрован: адрес контракта НЕ найден в Twitter")
    elif not should_notify:
        logger.info(f"🚫 Токен {symbol} отфильтрован: низкие показатели Twitter активности")
    
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
            
            # Отправляем уведомления о крупных сделках (больше 5 SOL)
            if sol_amount >= 5.0:
                logger.info(f"💰 Крупная {'покупка' if is_buy else 'продажа'}: {sol_amount:.2f} SOL")
                msg, keyboard = format_trade_alert(data)
                notification_sent = send_telegram(msg, keyboard)
            
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

async def main():
    """Основная функция с автоматическим реконнектом"""
    uri = "wss://pumpportal.fun/api/data"
    max_retries = 10
    retry_delay = 5
    retry_count = 0
    first_connection = True
    last_stats_day = None
    last_heartbeat = datetime.now()
    
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
                        "🚀 <b>PUMP.FUN БОТ ЗАПУЩЕН!</b>\n\n"
                        "✅ Мониторинг новых токенов с Twitter анализом\n"
                        "✅ Умная фильтрация мусорных токенов\n"
                        "✅ Отслеживание крупных сделок (>5 SOL)\n"
                        "✅ Кнопки для быстрой покупки\n\n"
                        "💎 Готов ловить качественные токены!"
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