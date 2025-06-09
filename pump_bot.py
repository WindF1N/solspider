import asyncio
import websockets
import json
import requests
import logging
import os
from datetime import datetime

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

def format_new_token(data):
    """Форматирование сообщения о новом токене с полной информацией"""
    mint = data.get('mint', 'Unknown')
    name = data.get('name', 'Unknown Token')
    symbol = data.get('symbol', 'UNK')
    description = data.get('description', 'Нет описания')
    creator = data.get('traderPublicKey', 'Unknown')
    
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
    
    return message, keyboard

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
            logger.info(f"🚀 НОВЫЙ ТОКЕН: {token_name} ({mint[:8]}...)")
            
            # Отправляем в Telegram с кнопками
            msg, keyboard = format_new_token(data)
            send_telegram(msg, keyboard)
            
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
    """Основная функция"""
    uri = "wss://pumpportal.fun/api/data"
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("🌐 Подключен к PumpPortal")
            
            # Подписываемся на новые токены
            subscribe_msg = {"method": "subscribeNewToken"}
            await websocket.send(json.dumps(subscribe_msg))
            logger.info("✅ Подписались на новые токены")
            
            # Подписываемся на миграции
            migrate_msg = {"method": "subscribeMigration"}
            await websocket.send(json.dumps(migrate_msg))
            logger.info("✅ Подписались на миграции")
            
            # Уведомляем о запуске
            start_message = (
                "🚀 <b>PUMP.FUN БОТ ЗАПУЩЕН!</b>\n\n"
                "✅ Мониторинг новых токенов\n"
                "✅ Отслеживание крупных сделок (>5 SOL)\n"
                "✅ Кнопки для быстрой покупки\n\n"
                "💎 Готов ловить новые токены!"
            )
            send_telegram(start_message)
            
            # Слушаем сообщения
            async for message in websocket:
                await handle_message(message)
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        send_telegram(f"❌ Ошибка бота: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 