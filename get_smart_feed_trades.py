import asyncio
import websockets
import json
import msgpack
import ssl
import uuid
import random
from typing import Optional, Any

import os
import subprocess
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smart_feed_trades.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Функции, скопированные из track_eboshers.py (упрощенные) ---

def j8(e=None, t=None, n=None):
    # Если доступен встроенный randomUUID и не переданы t и e
    if hasattr(uuid, 'uuid4') and t is None and (e is None or e == {}):
        return str(uuid.uuid4())

    # Генерация 16 случайных байт (аналог O8())
    if e is None:
        e = {}

    if 'random' in e:
        r = e['random']
    elif 'rng' in e:
        r = e['rng']()
    else:
        # Генерация 16 случайных байт (0-255)
        r = [random.randint(0, 255) for _ in range(16)]

    # Установка версии и варианта (как в оригинальной функции)
    r[6] = (15 & r[6]) | 64  # Устанавливаем версию 4
    r[8] = (63 & r[8]) | 128 # Устанавливаем вариант 10 (RFC 4122)

    if t is not None:
        # Если передан буфер t - записываем байты
        n = n or 0
        for i in range(16):
            t[n + i] = r[i]
        return t

    # Форматирование в строку UUID
    def format_bytes(bytes_arr, offset=0):
        hex_chars = "0123456789abcdef"
        result = []

        for i in range(16):
            if i in [4, 6, 8, 10]:
                result.append('-')
            byte_val = bytes_arr[offset + i]
            result.append(hex_chars[byte_val >> 4])
            result.append(hex_chars[byte_val & 0x0F])

        return ''.join(result)

    return format_bytes(r)

def decode_padre_message(message_bytes: bytes) -> Optional[Any]:
    """
    Декодирует бинарное сообщение от padre.gg WebSocket.
    Попытка универсального декодирования.
    """
    try:
        unpacked = msgpack.unpackb(message_bytes, raw=False)

        # Padre часто отправляет объекты JSON внутри MessagePack,
        # или просто вложенные структуры.
        # Попытаемся обработать разные варианты.
        if isinstance(unpacked, dict):
            # Если это новый формат с 'type': 'msg' и payload - JSON строка
            if unpacked.get('type') == 'msg' and isinstance(unpacked.get('payload'), str):
                try:
                    return json.loads(unpacked['payload'])
                except json.JSONDecodeError:
                    return unpacked['payload'] # Если не JSON, возвращаем как есть
            return unpacked
        elif isinstance(unpacked, list):
            # Если список, и один из элементов - словарь, возможно, это данные
            for item in unpacked:
                if isinstance(item, dict):
                    return item
                elif isinstance(item, str): # Попробуем декодировать строку как JSON
                    try:
                        return json.loads(item)
                    except json.JSONDecodeError:
                        pass
            return unpacked
        else:
            return unpacked # Возвращаем как есть (например, число или булево)

    except Exception as e:
        logger.error(f"❌ Ошибка декодирования сообщения: {e}")
        return None

async def get_token_from_script() -> Optional[str]:
    """
    Асинхронный вызов скрипта padre_get_access_token.py для получения JWT токена.
    """
    try:
        logger.info("🔄 Автоматически получаем новый JWT токен через padre_get_access_token.py...")

        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, _sync_get_token_from_script)

        if token:
            logger.info("✅ Новый токен успешно получен!")
            return token
        else:
            logger.error("❌ Не удалось получить токен через скрипт")
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка при получении токена: {e}")
        return None

def _sync_get_token_from_script() -> Optional[str]:
    """
    Синхронный вызов скрипта padre_get_access_token.py
    """
    try:
        # Запускаем скрипт padre_get_access_token.py
        script_path = os.path.join(os.path.dirname(__file__), "padre_get_access_token.py")
        result = subprocess.run(
            ["python", script_path],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__)
        )

        if result.returncode == 0:
            logger.info("✅ Скрипт padre_get_access_token.py выполнен успешно")

            # Читаем токен из файла token.txt
            token_file = os.path.join(os.path.dirname(__file__), "token.txt")
            if os.path.exists(token_file):
                with open(token_file, 'r') as f:
                    token = f.read().strip()

                if token and token.startswith('eyJ'):
                    return token
                else:
                    logger.error("❌ Токен в файле имеет неправильный формат")
                    return None
            else:
                logger.error("❌ Файл token.txt не найден")
                return None
        else:
            logger.error(f"❌ Ошибка выполнения скрипта: {result.stderr}")
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка при вызове скрипта: {e}")
        return None

# --- Основная логика скрипта ---

# !!! ВАЖНО: Замените этот PADRE_COOKIES на актуальный из вашего браузера !!!
# Его можно найти в Developer Tools -> Network -> любой запрос к padre.gg -> Headers -> Cookie
PADRE_COOKIES = {
    'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel': 'YOUR_ACTUAL_MIXAPANEL_COOKIE_VALUE'
}

PADRE_WS_URL = "wss://backend.padre.gg/_heavy_multiplex"

async def connect_and_subscribe():
    logger.info(f"🔗 Подключаемся к: {PADRE_WS_URL}")

    # Получаем JWT токен
    jwt_token = await get_token_from_script()
    if not jwt_token:
        logger.error("❌ Не удалось получить JWT токен. Отмена подключения.")
        return

    headers = {
        'Cookie': 'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel=' + PADRE_COOKIES['mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel'],
        'Origin': 'https://trade.padre.gg',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        async with websockets.connect(
            PADRE_WS_URL,
            extra_headers=headers,
            ping_interval=None,
            ping_timeout=None,
            ssl=ssl_context
        ) as websocket:
            logger.info("✅ WebSocket соединение установлено")

            # Отправляем аутентификационное сообщение
            auth_message = [
                1,
                jwt_token,  # Используем полученный токен
                j8()[:13]
            ]
            auth_bytes = msgpack.packb(auth_message)
            await websocket.send(auth_bytes)
            logger.info("🔐 Аутентификационное сообщение отправлено")
            await asyncio.sleep(1) # Небольшая пауза для обработки ответа

            # Отправляем сообщение подписки
            # [4, 37, '/trades/recent/solana-HLKzXdsg3q2WwgJHiUUCXgonnvXrvvPSqkpnrju94yjR/smart-feed']
            subscription_message = [
                4,
                37,
                '/trades/recent/solana-HLKzXdsg3q2WwgJHiUUCXgonnvXrvvPSqkpnrju94yjR/smart-feed'
            ]
            subscription_bytes = msgpack.packb(subscription_message)
            await websocket.send(subscription_bytes)
            logger.info("📡 Сообщение подписки отправлено")
            await asyncio.sleep(1) # Небольшая пауза для обработки ответа

            logger.info("👂 Начинаем прослушивание сообщений...")
            async for message in websocket:
                if isinstance(message, bytes):
                    decoded_data = decode_padre_message(message)
                    if decoded_data:
                        logger.info(f"📨 Получено сообщение: {json.dumps(decoded_data, indent=2, ensure_ascii=False)}")
                    else:
                        logger.warning(f"📦 Получено бинарное сообщение (не декодировано): {message[:50]}...")
                elif isinstance(message, str):
                    logger.info(f"📨 Получено текстовое сообщение: {message}")

    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"❌ Соединение WebSocket закрыто: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def main():
    try:
        await connect_and_subscribe()
    except KeyboardInterrupt:
        logger.info("🛑 Программа прервана пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка в main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
