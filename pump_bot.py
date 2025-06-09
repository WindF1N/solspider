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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# Nitter конфигурация для анализа Twitter
NITTER_COOKIE = "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiMGEyOWM0YzcwZGM0YzYxMjE2NTNkMzQwYTU0YTNmNTFmZmJlNDIwOGM4MWZkZmUxNDA4MTY2MGNmMDc3ZGY2IiwiZXhwIjoxNzQ5NjAyOTA3LCJpYXQiOjE3NDg5OTgxMDcsIm5iZiI6MTc0ODk5ODA0Nywibm9uY2UiOiIxMzI4MSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWEwZjdmMjBjNGQ0MGU5ODIzMWI4MDNmNWZiMGJlMGZjZmZiOGRhOTIzNDUyNDdhZjU1Yjk1MDJlZWE2In0.615N6HT0huTaYXHffqbBWqlpbpUgb7uVCh__TCoIuZLtGzBkdS3K8fGOPkFxHrbIo2OY3bw0igmtgDZKFesjAg"

def send_telegram(message, inline_keyboard=None):
    """Отправка сообщения в Telegram с кнопками"""
    try:
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(TELEGRAM_URL, json=payload)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Ошибка Telegram: {e}")
        return False

def analyze_token_sentiment(mint, symbol):
    """Анализ упоминаний токена в Twitter через Nitter"""
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
        
        # Поиск по символу и адресу контракта
        search_queries = [f'${symbol}', mint]
        total_tweets = 0
        total_engagement = 0
        symbol_tweets = 0
        contract_tweets = 0
        
        for i, query in enumerate(search_queries):
            url = f"https://nitter.tiekoetter.com/search?f=tweets&q=%22{query}%22"
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Находим все твиты
                    tweets = soup.find_all('div', class_='timeline-item')
                    tweet_count = len(tweets)
                    total_tweets += tweet_count
                    
                    # Сохраняем отдельно твиты по символу и контракту
                    if i == 0:  # Символ токена
                        symbol_tweets = tweet_count
                    else:  # Адрес контракта
                        contract_tweets = tweet_count
                    
                    # Анализируем активность в твитах
                    for tweet in tweets:
                        stats = tweet.find_all('span', class_='tweet-stat')
                        for stat in stats:
                            icon_container = stat.find('div', class_='icon-container')
                            if icon_container:
                                text = icon_container.get_text(strip=True)
                                # Извлекаем числа (лайки, ретвиты, комментарии)
                                numbers = re.findall(r'\d+', text)
                                if numbers:
                                    total_engagement += int(numbers[0])
                    
                    logger.info(f"🔍 Nitter анализ '{query}': {tweet_count} твитов, активность: {total_engagement}")
                    
                    # Небольшая задержка между запросами
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Ошибка запроса к Nitter для '{query}': {e}")
                continue
        
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

def format_new_token(data):
    """Форматирование сообщения о новом токене с полной информацией"""
    mint = data.get('mint', 'Unknown')
    name = data.get('name', 'Unknown Token')
    symbol = data.get('symbol', 'UNK')
    description = data.get('description', 'Нет описания')
    creator = data.get('traderPublicKey', 'Unknown')
    
    # Анализируем упоминания в Twitter
    logger.info(f"🔍 Анализируем токен {symbol} в Twitter...")
    twitter_analysis = analyze_token_sentiment(mint, symbol)
    
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
        twitter_analysis['score'] >= 5 or  # Минимальный скор
        twitter_analysis['tweets'] >= 3 or  # Минимум 3 твита
        'высокий' in twitter_analysis['rating'].lower() or  # Высокий интерес
        'средний' in twitter_analysis['rating'].lower()    # Средний интерес
    )
    
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
            msg, keyboard, should_notify = format_new_token(data)
            
            if should_notify:
                logger.info(f"✅ Токен {symbol} прошел фильтрацию - отправляем уведомление")
                send_telegram(msg, keyboard)
            else:
                logger.info(f"❌ Токен {symbol} не прошел фильтрацию - пропускаем")
            
        # Проверяем, это ли торговое событие
        elif 'mint' in data and 'traderPublicKey' in data and 'sol_amount' in data:
            sol_amount = float(data.get('sol_amount', 0))
            is_buy = data.get('is_buy', True)
            mint = data.get('mint', 'Unknown')
            
            # Отправляем уведомления о крупных сделках (больше 5 SOL)
            if sol_amount >= 5.0:
                logger.info(f"💰 Крупная {'покупка' if is_buy else 'продажа'}: {sol_amount:.2f} SOL")
                msg, keyboard = format_trade_alert(data)
                send_telegram(msg, keyboard)
            
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")

async def main():
    """Основная функция с автоматическим реконнектом"""
    uri = "wss://pumpportal.fun/api/data"
    max_retries = 10
    retry_delay = 5
    retry_count = 0
    first_connection = True
    
    while True:
        try:
            # Настройки WebSocket с keepalive
            async with websockets.connect(
                uri,
                ping_interval=20,  # Отправка ping каждые 20 секунд
                ping_timeout=10,   # Таймаут ожидания pong 10 секунд
                close_timeout=10   # Таймаут закрытия соединения
            ) as websocket:
                logger.info("🌐 Подключен к PumpPortal")
                
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
                async for message in websocket:
                    await handle_message(message)
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"⚠️ Соединение закрыто: {e}")
            send_telegram(f"⚠️ <b>Соединение потеряно</b>\nПричина: {e}\n🔄 Попытка переподключения...")
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"❌ Неверный статус код: {e}")
            send_telegram(f"❌ <b>Ошибка подключения</b>\nСтатус: {e}")
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"❌ WebSocket ошибка: {e}")
            send_telegram(f"❌ <b>WebSocket ошибка</b>\n{e}")
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {e}")
            send_telegram(f"❌ <b>Критическая ошибка</b>\n{e}")
        
        # Увеличиваем задержку для следующего подключения
        retry_count = min(retry_count + 1, max_retries)
        delay = retry_delay * retry_count
        
        if retry_count >= max_retries:
            error_msg = "❌ <b>Максимум попыток переподключения достигнут</b>\n⏹️ Бот остановлен"
            logger.error(error_msg)
            send_telegram(error_msg)
            break
        
        logger.info(f"🔄 Переподключение через {delay} секунд... (попытка {retry_count}/{max_retries})")
        await asyncio.sleep(delay)

if __name__ == "__main__":
    asyncio.run(main()) 