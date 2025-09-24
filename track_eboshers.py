#!/usr/bin/env python3
"""
Track Eboshers - WebSocket client for monitoring eboshers activity
Отслеживает активность ебошеров через WebSocket подключение к padre.gg

ИСПОЛЬЗОВАНИЕ:
1. Убедитесь, что файл eboshers_v5.txt содержит список адресов ебошеров
2. Запустите скрипт: python track_eboshers.py
3. Скрипт подключится к Padre WebSocket и начнет отслеживать трейды ебошеров

ФУНКЦИОНАЛЬНОСТЬ:
- Подключение к Padre WebSocket
- Аутентификация с JWT токеном (автоматическое обновление)
- Интерактивный ввод нового токена при истечении
- Подписка на tracked-trades/wallet-groups
- Минимальная обработка данных трейдов (только необходимые поля)
- Логирование трейдов в отдельные файлы по адресам токенов
- Обнаружение скоплений ебошеров
- Параллельное логирование по старым метрикам (4+ кошельков за час)

ОСОБЕННОСТИ:
- При истечении JWT токена система автоматически попытается обновить его
- Если автоматическое обновление невозможно, система запросит новый токен у пользователя
- При вводе токена можно использовать Ctrl+C для отмены и продолжения с текущим токеном
- Обнаружение скоплений по объему ≥ $2000 И количеству кошельков ≥ 4
- Расширенное временное окно в 1 час для накопления объема
- Логирование всех покупок в отдельные файлы по токенам

КОМАНДЫ:
- Ctrl+C для остановки скрипта
"""

import asyncio
import websockets
import json
import base64
import struct
import os
import sys
import logging
import subprocess
import aiohttp
import msgpack
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
import requests
from urllib.parse import quote
import re
import ssl
import time
import traceback
from dotenv import load_dotenv
import numpy as np
from scipy.stats import linregress
import uuid
import random
import threading

# Загружаем переменные окружения из .env файла
load_dotenv()

# Глобальный черный список для токенов, помеченных как "гениальные раги"
GENIUS_RUG_BLACKLIST = set()

# Папка для логов токенов
EBOSHERS_LOGS_DIR = "eboshers_logs"

# Файл для логов по старым метрикам
OLD_METRICS_LOG_FILE = "eboshers_old_metrics_find.log"
BLACKLIST_FILE = "genius_rug_blacklist.txt"

# Файл для хранения отправленных токенов
SENT_TOKENS_FILE = "sent_tokens.json"
MAX_SENT_TOKENS = 300

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

def load_blacklist():
    """Загружает черный список из файла"""
    global GENIUS_RUG_BLACKLIST
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r') as f:
                GENIUS_RUG_BLACKLIST = set(line.strip() for line in f if line.strip())
            print(f"📥 Загружен черный список: {len(GENIUS_RUG_BLACKLIST)} токенов")
    except Exception as e:
        print(f"❌ Ошибка загрузки черного списка: {e}")

def save_blacklist():
    """Сохраняет черный список в файл"""
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            for token in sorted(GENIUS_RUG_BLACKLIST):
                f.write(f"{token}\n")
    except Exception as e:
        print(f"❌ Ошибка сохранения черного списка: {e}")

def load_sent_tokens():
    """Загружает список отправленных токенов из JSON файла"""
    global sent_tokens
    try:
        if os.path.exists(SENT_TOKENS_FILE):
            with open(SENT_TOKENS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Берем последние MAX_SENT_TOKENS токенов (FIFO)
                tokens_list = data.get('tokens', [])
                if len(tokens_list) > MAX_SENT_TOKENS:
                    tokens_list = tokens_list[-MAX_SENT_TOKENS:]
                sent_tokens = set(tokens_list)
            print(f"📥 Загружен список отправленных токенов: {len(sent_tokens)}")
        else:
            print("📝 Файл с отправленными токенами не найден, создаем новый")
            sent_tokens = set()
    except Exception as e:
        print(f"❌ Ошибка загрузки отправленных токенов: {e}")
        sent_tokens = set()

def save_sent_tokens():
    """Сохраняет список отправленных токенов в JSON файл"""
    global sent_tokens
    try:
        # Конвертируем set в list для сохранения в JSON
        tokens_list = list(sent_tokens)

        # Ограничиваем количество токенов до MAX_SENT_TOKENS (FIFO)
        if len(tokens_list) > MAX_SENT_TOKENS:
            tokens_list = tokens_list[-MAX_SENT_TOKENS:]

        data = {
            'tokens': tokens_list,
            'last_updated': datetime.now().isoformat(),
            'max_tokens': MAX_SENT_TOKENS
        }

        with open(SENT_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"💾 Сохранен список отправленных токенов: {len(tokens_list)}")
    except Exception as e:
        print(f"❌ Ошибка сохранения отправленных токенов: {e}")

def add_sent_token(token_address: str):
    """Добавляет токен в список отправленных"""
    global sent_tokens
    if token_address and token_address not in sent_tokens:
        sent_tokens.add(token_address)
        save_sent_tokens()

def is_token_sent(token_address: str) -> bool:
    """Проверяет, был ли токен уже отправлен"""
    return token_address in sent_tokens

# Загружаем черный список при запуске
load_blacklist()

# Загружаем список отправленных токенов при запуске
load_sent_tokens()

# Настройка основного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('track_eboshers.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация системы отслеживания скоплений ебошеров
ebosher_clusters = {}  # {token_address: {'wallets': {wallet: timestamp}, 'first_detection': timestamp, 'cluster_size': int, 'last_market_cap': float}}

# Глобальный словарь для кластеров по старым метрикам (4+ кошельков за час)
old_metrics_clusters = {}  # {token_address: {'wallets': {wallet: timestamp}, 'first_detection': timestamp, 'cluster_size': int}}

# Глобальный набор отправленных токенов
sent_tokens = set()

def create_token_logger(token_address: str) -> logging.Logger:
    """Создает отдельный логгер для токена"""
    try:
        # Создаем папку для логов токенов если она не существует
        tokens_logs_dir = 'tokens_logs'
        if not os.path.exists(tokens_logs_dir):
            os.makedirs(tokens_logs_dir)

        # Создаем имя файла из адреса токена (первые 12 символов для краткости)
        safe_token_name = token_address[:12] if token_address else "unknown"
        log_filename = os.path.join(tokens_logs_dir, f'{safe_token_name}.log')

        # Создаем логгер для этого токена
        token_logger = logging.getLogger(f'token_{token_address}')

        # Проверяем, не создан ли уже логгер для этого токена
        if token_logger.handlers:
            return token_logger

        # Настраиваем уровень логирования
        token_logger.setLevel(logging.INFO)

        # Создаем форматтер
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Создаем файловый обработчик для токена
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(formatter)

        # Добавляем обработчик к логгеру
        token_logger.addHandler(file_handler)

        # Отключаем распространение в родительский логгер чтобы избежать дублирования
        token_logger.propagate = False

        logger.info(f"✅ Создан отдельный логгер для токена {token_address[:8]} -> {log_filename}")

        return token_logger

    except Exception as e:
        logger.error(f"❌ Ошибка создания логгера для токена {token_address[:8]}: {e}")
        # Возвращаем основной логгер в случае ошибки
        return logger

def get_token_logger(token_address: str) -> logging.Logger:
    """Получает логгер для токена (создает если не существует)"""
    if not token_address:
        return logger
    return create_token_logger(token_address)

# Глобальная переменная для хранения mapping токенов к market_id
TOKEN_TO_MARKET_CACHE = {}

# Хранилище для pending запросов market_id
PENDING_MARKET_ID_REQUESTS = {}

# В начале файла, где другие глобальные переменные
# Хранилище для отправленных уведомлений {token_address: {'activity': timestamp, 'pump': timestamp}}
SENT_NOTIFICATIONS = {}

# Список бэкендов Padre для ротации
PADRE_BACKENDS = [
    "wss://backend1.padre.gg/_heavy_multiplex",
    "wss://backend2.padre.gg/_heavy_multiplex",
    "wss://backend3.padre.gg/_heavy_multiplex",
    "wss://backend.padre.gg/_heavy_multiplex"
]

# Счетчик для ротации бэкендов
_backend_counter = 0

def get_next_padre_backend() -> str:
    """Возвращает следующий бэкенд Padre в режиме round-robin"""
    global _backend_counter
    backend = PADRE_BACKENDS[_backend_counter % len(PADRE_BACKENDS)]
    _backend_counter += 1
    return backend

class AuthenticationPolicyViolation(Exception):
    """Исключение при нарушении политики аутентификации (код 1008)"""
    pass

async def request_market_id_via_websocket(websocket, token_address: str) -> bool:
    """Отправляет запрос market_id для токена через WebSocket (не ждет ответ)"""
    try:
        token_logger = get_token_logger(token_address)

        # Проверяем cache
        if token_address in TOKEN_TO_MARKET_CACHE:
            return True

        # Создаем запрос market_id в формате MessagePack
        request_data = [8, token_address]
        message_bytes = msgpack.packb(request_data)

        await websocket.send(message_bytes)
        token_logger.info(f"📤 Отправлен запрос market_id для {token_address[:8]}")

        # Помечаем как pending
        PENDING_MARKET_ID_REQUESTS[token_address] = time.time()

        return True

    except Exception as e:
        token_logger = get_token_logger(token_address)
        token_logger.error(f"❌ Ошибка отправки запроса market_id для {token_address[:8]}: {e}")
        return False

def process_markets_per_token_response(payload: dict):
    """Обрабатывает ответ markets-per-token и обновляет кеш"""
    try:
        if not isinstance(payload, dict):
            return

        if 'markets' in payload and 'SOLANA' in payload['markets']:
            solana_markets = payload['markets']['SOLANA']

            for token_address, markets_list in solana_markets.items():
                if markets_list and isinstance(markets_list, list) and len(markets_list) > 0:
                    market_info = markets_list[0]
                    market_id = market_info.get('marketId')

                    if market_id:
                        TOKEN_TO_MARKET_CACHE[token_address] = market_id
                        logger.info(f"📊 Сохранен market_id для {token_address[:8]}: {market_id}")

                        # Удаляем из pending если был там
                        if token_address in PENDING_MARKET_ID_REQUESTS:
                            del PENDING_MARKET_ID_REQUESTS[token_address]

    except Exception as e:
        logger.error(f"❌ Ошибка обработки markets-per-token ответа: {e}")

async def get_market_id_for_token_cached(token_address: str) -> Optional[str]:
    """Получает market_id для токена с использованием кеша"""
    try:
        # Проверяем кеш
        if token_address in TOKEN_TO_MARKET_CACHE:
            return TOKEN_TO_MARKET_CACHE[token_address]

        # Если нет в кеше и запрос не в процессе, создаем новое подключение для запроса
        if token_address not in PENDING_MARKET_ID_REQUESTS:
            logger.info(f"🔍 Market_id для {token_address[:8]} не найден в кеше, создаем запрос...")

            # Создаем временное подключение для запроса market_id
            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                headers = {
                    'Cookie': 'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel=%7B%22distinct_id%22%3A%20%22tg_7705971216%22%2C%22%24device_id%22%3A%20%2219946bc0c961188-06db4de430e72a8-4c657b58-1fa400-19946bc0c9727d3%22%2C%22%24user_id%22%3A%20%22tg_7705971216%22%2C%22%24initial_referrer%22%3A%20%22%24direct%22%2C%22%24initial_referring_domain%22%3A%20%22%24direct%22%7D',
                    'Origin': 'https://trade.padre.gg',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 OPR/122.0.0.0 (Edition Yx 08)'
                }

                async with websockets.connect(
                    get_next_padre_backend(),
                    extra_headers=headers,
                    ping_interval=None,
                    ping_timeout=None,
                    ssl=ssl_context
                ) as websocket:
                    # Отправляем запрос
                    if await request_market_id_via_websocket(websocket, token_address):
                        # Ждем ответ короткое время
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            # Декодируем и обрабатываем ответ
                            if isinstance(response, bytes):
                                decoded_data = decode_padre_message(response)
                                if decoded_data:
                                    logger.info(f"📨 Получен ответ market_id: {decoded_data}")
                                    process_markets_per_token_response(decoded_data)
                        except asyncio.TimeoutError:
                            logger.warning(f"⏰ Таймаут ожидания ответа market_id для {token_address[:8]}")

            except Exception as e:
                logger.error(f"❌ Ошибка создания временного подключения для market_id: {e}")

        return TOKEN_TO_MARKET_CACHE.get(token_address)

    except Exception as e:
        logger.error(f"❌ Ошибка получения market_id для {token_address}: {e}")
        return None

async def get_token_metadata(token_address: str) -> dict:
    """Получает метаданные токена"""
    try:
        # Используем Axiom API для получения информации о токене
        axiom_api_domains = [
            "https://api.axiom.trade",
            "https://api2.axiom.trade",
            "https://api3.axiom.trade",
            "https://api6.axiom.trade",
            "https://api7.axiom.trade",
            "https://api8.axiom.trade",
            "https://api9.axiom.trade",
            "https://api10.axiom.trade",
        ]

        last_used_api_domain = 0

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{axiom_api_domains[last_used_api_domain]}/token-info?pairAddress={token_address}", headers={
                'accept': '*/*',
                'cookie': 'auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6IjdhN2JhN2E3LWY4NDktNDVlNC05ZDI4LWY2MjRhNjUzY2YyYiIsImlhdCI6MTc1Mzk5MDE5Mn0.m825JgO7TNs6LR1RfmWs2y_O0qSZfQi3Tug04qdVKMw; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiMzVlNjc3YzMtMjY4Zi00YTFmLWI5M2ItN2VkOGJjN2IzYjU0IiwiaWF0IjoxNzU1NTM1MjU2LCJleHAiOjE3NTU1MzYyMTZ9.ruxPC8uhIx_13OrcmlBtigIWWkCU2gl_MK9SIeoU0S8'
            }, timeout=aiohttp.ClientTimeout(total=5)) as response:
                try:
                    data = await response.json(content_type=None)
                    return data
                except Exception as e:
                    logger.error(f"Failed to parse JSON from token-info: {e}")
                    return {}

        last_used_api_domain = (last_used_api_domain + 1) % len(axiom_api_domains)

    except Exception as e:
        logger.error(f"❌ Ошибка получения метаданных токена {token_address[:8]}: {e}")
        return {}

async def get_market_id_for_token(token_address: str) -> Optional[str]:
    """Получает market_id для токена через API"""
    try:
        # Получаем метаданные токена
        metadata = await get_token_metadata(token_address)

        if metadata and 'pairAddress' in metadata:
            market_id = metadata['pairAddress']
            TOKEN_TO_MARKET_CACHE[token_address] = market_id
            logger.info(f"📊 Получен market_id для {token_address[:8]}: {market_id}")
            return market_id

        return None

    except Exception as e:
        logger.error(f"❌ Ошибка получения market_id для {token_address}: {e}")
        return None

async def get_market_address_via_smart_query(websocket, token_address: str) -> Optional[str]:
    """Получает адрес маркета через smart query"""
    try:
        # Создаем smart query запрос
        smart_query = {
            "operationName": "GetMarketByBaseTokenAddress",
            "variables": {
                "address": token_address,
                "chain": "SOLANA"
            },
            "query": """
            query GetMarketByBaseTokenAddress($address: String!, $chain: Chain!) {
                markets(
                    filters: {
                        baseTokenAddress: { equalTo: $address }
                        chain: { equalTo: $chain }
                    }
                    pagination: { limit: 1 }
                ) {
                    id
                    baseTokenAddress
                    quoteTokenAddress
                }
            }
            """
        }

        # Отправляем запрос
        query_bytes = msgpack.packb([7, smart_query])
        await websocket.send(query_bytes)

        # Ждем ответ
        response = await websocket.recv()
        if isinstance(response, bytes):
            decoded_data = decode_padre_message(response)
            if decoded_data and 'data' in decoded_data:
                markets = decoded_data['data'].get('markets', [])
                if markets:
                    market_id = markets[0].get('id')
                    if market_id:
                        TOKEN_TO_MARKET_CACHE[token_address] = market_id
                        logger.info(f"📊 Получен market_id через smart query для {token_address[:8]}: {market_id}")
                        return market_id

        return None

    except Exception as e:
        logger.error(f"❌ Ошибка smart query для {token_address[:8]}: {e}")
        return None

def decode_padre_message(message_bytes: bytes) -> Optional[dict]:
    """
    Декодирует бинарное сообщение от padre.gg WebSocket
    """
    try:
        # Распаковываем MessagePack
        unpacked = msgpack.unpackb(message_bytes, strict_map_key=False)

        # Проверяем, является ли сообщение словарем (новый формат Padre)
        if isinstance(unpacked, dict):
            return unpacked

        # Проверяем, является ли сообщение списком (старый формат)
        elif isinstance(unpacked, list):
            print("✅ Сообщение является списком (старый формат)")

            if len(unpacked) < 3:
                print(f"❌ Список слишком короткий: {len(unpacked)}")
                print(unpacked)
                return None

            message_type = unpacked[0]
            payload = unpacked[1]

            # Разбираем payload в зависимости от типа сообщения
            if message_type == 4:  # tracked-trades subscription responses
                # Для tracked-trades возвращаем полное сообщение
                return {'type': 'tracked_trades', 'raw_data': unpacked}
            elif message_type == 9:  # markets-per-token
                if isinstance(payload, dict):
                    return payload
            elif message_type in [5, 8]:  # fast-stats updates или другие
                # Проверяем, является ли третий элемент списка словарем (часто содержит основные данные)
                if len(unpacked) > 2 and isinstance(unpacked[2], dict):
                    return unpacked[2]
                # Если нет, возвращаемся к проверке payload
                elif isinstance(payload, dict):
                    return payload
            elif message_type in [1, 2, 3]:  # auth responses, subscription confirmations
                return {'type': 'system', 'message_type': message_type, 'payload': payload}
            elif message_type == 6:  # Специальное сообщение для переподключения
                print(f"🚨 ОБНАРУЖЕНО СПЕЦИАЛЬНОЕ СООБЩЕНИЕ: message_type={message_type}, payload={payload}")
                print("🔄 Будет выполнено принудительное переподключение WebSocket")
                return {'type': 'reconnect_required', 'message_type': message_type, 'payload': payload}
            else:
                print(f"📋 message_type: {message_type}")
                print(f"📋 payload: {payload}")
                print(f"📋 payload type: {type(payload)}")
                print(unpacked[2])

            # Для всех остальных типов возвращаем полное сообщение
            return {'type': 'unknown', 'raw_data': unpacked}

        else:
            print(f"❌ Неизвестный тип сообщения: {type(unpacked)}")
            return None

    except Exception as e:
        logger.debug(f"❌ Ошибка декодирования сообщения: {e}")
        return None

# Конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TARGET_CHAT_ID = -1002680160752  # ID группы из https://t.me/c/2680160752/13134
SPECIAL_CHAT_ID = -1002731055130  # Канал для специальных сообщений
SPECIAL_DUPLICATE_CHAT_ID = -1002538268724  # Дополнительный канал для специальных сообщений
NEW_ADDITIONAL_CHANNEL_ID = -1003084764631 # Новый дополнительный канал для специальных сообщений
STANDARD_CHAT_ID = -1002837160729  # Канал для стандартных сообщений
SPECIAL_PATTERN_THREAD_ID = 19879  # ID ветки для специального паттерна https://t.me/c/2680160752/19879
TARGET_THREAD_ID = 13134  # ID темы
MIN_BUNDLER_PERCENTAGE = float(os.getenv("MIN_BUNDLER_PERCENTAGE", "10"))  # Минимальный процент бандлеров

# WebSocket URL для trade.padre.gg
PADRE_WS_URL = get_next_padre_backend()

# Куки для подключения к padre
PADRE_COOKIES = {
    'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel': '%7B%22distinct_id%22%3A%20%22tg_7705971216%22%2C%22%24device_id%22%3A%20%2219946bc0c961188-06db4de430e72a8-4c657b58-1fa400-19946bc0c9727d3%22%2C%22%24user_id%22%3A%20%22tg_7705971216%22%2C%22%24initial_referrer%22%3A%20%22%24direct%22%2C%22%24initial_referring_domain%22%3A%20%22%24direct%22%7D'
}

# Хранилище токенов для анализа
pending_tokens: Dict[str, dict] = {}  # {contract_address: token_data}
bundler_results: Dict[str, dict] = {}  # {contract_address: bundler_data}
sended_tokens: Dict[str, bool] = {}  # {contract_address: bool}

class TokenMetrics:
    """Класс для отслеживания метрик токена"""

    def __init__(self, token_address: str, creation_time: int):
        """Инициализация метрик токена"""
        self.token_address = token_address
        self.creation_time = creation_time
        self.metrics_history = []
        self.last_notification_type = None
        self.last_notification_time = 0
        self.max_dev_percent = 0
        self.dev_exit_time = None
        self.max_bundlers_after_dev_exit = 0

    def can_send_notification(self, notification_type: str) -> bool:
        """Проверяет, можно ли отправить уведомление данного типа"""
        current_time = time.time()
        cooldowns = {
            'activity': 300,  # 5 минут
            'pump': 600,      # 10 минут
            'special_pattern': 1800,  # 30 минут
            'bundler': 900,   # 15 минут
        }

        cooldown = cooldowns.get(notification_type, 300)

        if (self.last_notification_type == notification_type and
            current_time - self.last_notification_time < cooldown):
            return False

        return True

    def add_metrics(self, metrics: dict):
        """Добавляет метрики в историю"""
        timestamp = int(time.time())
        metrics_entry = {
            'timestamp': timestamp,
            'total_holders': metrics.get('total_holders', 0),
            'dev_percent': float(metrics.get('devHoldingPcnt', 0) or 0),
            'bundlers_percent': float(metrics.get('bundlesHoldingPcnt', {}).get('current', 0) or 0),
            'snipers_percent': float(metrics.get('snipersHoldingPcnt', 0) or 0),
            'insiders_percent': float(metrics.get('insidersHoldingPcnt', 0) or 0),
            'liquidity': float(metrics.get('liquidityInUsdUi', 0) or 0),
            'market_cap': float(metrics.get('totalSupply', 0) or 0) / (10 ** 9) * float(metrics.get('basePriceInUsdUi', 0) or 0) * 1000,
        }

        self.metrics_history.append(metrics_entry)

        # Обновляем максимальный процент дева
        if metrics_entry['dev_percent'] > self.max_dev_percent:
            self.max_dev_percent = metrics_entry['dev_percent']

        # Отслеживаем выход дева
        if (self.dev_exit_time is None and
            self.max_dev_percent > 5 and
            metrics_entry['dev_percent'] < 2):
            self.dev_exit_time = timestamp

        # Отслеживаем максимальный процент бандлеров после выхода дева
        if (self.dev_exit_time is not None and
            metrics_entry['bundlers_percent'] > self.max_bundlers_after_dev_exit):
            self.max_bundlers_after_dev_exit = metrics_entry['bundlers_percent']

        # Ограничиваем историю последними 1000 записями
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]

    def get_growth_rates(self) -> dict:
        """Вычисляет скорости роста для различных метрик"""
        if len(self.metrics_history) < 2:
            return {}

        current = self.metrics_history[-1]
        previous = self.metrics_history[-2]

        time_diff = current['timestamp'] - previous['timestamp']
        if time_diff <= 0:
            return {}

        growth_rates = {}

        for metric in ['total_holders', 'dev_percent', 'bundlers_percent', 'snipers_percent',
                      'insiders_percent', 'liquidity', 'market_cap']:
            if metric in current and metric in previous:
                current_value = current[metric] or 0
                previous_value = previous[metric] or 0
                if previous_value != 0:
                    rate_per_second = (current_value - previous_value) / time_diff
                    growth_rates[metric] = rate_per_second

        return growth_rates

    def check_snipers_bundlers_correlation(self) -> bool:
        """Проверяет корреляцию между снайперами и бандлерами"""
        if len(self.metrics_history) < 20:
            return False

        # Берем последние 20 записей
        recent_data = self.metrics_history[-20:]

        snipers_values = [entry['snipers_percent'] for entry in recent_data]
        bundlers_values = [entry['bundlers_percent'] for entry in recent_data]

        # Вычисляем корреляцию
        correlation = self._calculate_correlation(snipers_values, bundlers_values)

        # Если корреляция > 0.7, это подозрительно
        return correlation > 0.7

    def check_snipers_insiders_correlation(self) -> bool:
        """Проверяет корреляцию между снайперами и инсайдерами"""
        if len(self.metrics_history) < 20:
            return False

        recent_data = self.metrics_history[-20:]

        snipers_values = [entry['snipers_percent'] for entry in recent_data]
        insiders_values = [entry['insiders_percent'] for entry in recent_data]

        correlation = self._calculate_correlation(snipers_values, insiders_values)

        return correlation > 0.7

    def check_bundlers_snipers_exit_correlation(self) -> bool:
        """Проверяет корреляцию выхода бандлеров и снайперов"""
        if len(self.metrics_history) < 30:
            return False

        recent_data = self.metrics_history[-30:]

        # Ищем паттерн: бандлеры выходят, затем снайперы
        bundlers_exiting = False
        snipers_exiting = False

        for i in range(1, len(recent_data)):
            bundlers_change = recent_data[i]['bundlers_percent'] - recent_data[i-1]['bundlers_percent']
            snipers_change = recent_data[i]['snipers_percent'] - recent_data[i-1]['snipers_percent']

            if bundlers_change < -1.0:  # Бандлеры выходят
                bundlers_exiting = True
            if snipers_change < -1.0 and bundlers_exiting:  # Снайперы выходят после бандлеров
                snipers_exiting = True

        return bundlers_exiting and snipers_exiting

    async def check_holders_correlation(self) -> bool:
        """Проверяет корреляцию между различными типами холдеров"""
        if len(self.metrics_history) < 20:
            return False

        recent_data = self.metrics_history[-20:]

        dev_values = [entry['dev_percent'] for entry in recent_data]
        insiders_values = [entry['insiders_percent'] for entry in recent_data]
        snipers_values = [entry['snipers_percent'] for entry in recent_data]

        # Проверяем корреляцию между dev и insiders
        dev_insiders_corr = self._calculate_correlation(dev_values, insiders_values)
        # Проверяем корреляцию между dev и snipers
        dev_snipers_corr = self._calculate_correlation(dev_values, snipers_values)

        # Если dev сильно коррелирует с insiders или snipers, это подозрительно
        return dev_insiders_corr > 0.8 or dev_snipers_corr > 0.8

    def _calculate_correlation(self, series1: list, series2: list) -> float:
        """Вычисляет коэффициент корреляции Пирсона между двумя сериями"""
        if len(series1) != len(series2) or len(series1) < 2:
            return 0.0

        try:
            n = len(series1)
            sum1 = sum(series1)
            sum2 = sum(series2)
            sum1_sq = sum(x**2 for x in series1)
            sum2_sq = sum(x**2 for x in series2)
            sum12 = sum(x*y for x, y in zip(series1, series2))

            numerator = n * sum12 - sum1 * sum2
            denominator = ((n * sum1_sq - sum1**2) * (n * sum2_sq - sum2**2)) ** 0.5

            if denominator == 0:
                return 0.0

            return numerator / denominator

        except (ZeroDivisionError, ValueError):
            return 0.0

    def check_rapid_exit(self, metric_name: str, ratio: float = 3.0, max_seconds: int = 120) -> bool:
        """Проверяет быстрый выход для указанной метрики"""
        if len(self.metrics_history) < 3:
            return False

        # Берем последние записи в пределах max_seconds
        current_time = time.time()
        recent_data = [entry for entry in self.metrics_history
                      if current_time - entry['timestamp'] <= max_seconds]

        if len(recent_data) < 3:
            return False

        # Вычисляем среднюю скорость изменения
        values = [entry[metric_name] for entry in recent_data if metric_name in entry]
        if len(values) < 3:
            return False

        # Проверяем резкое падение
        if values[-1] < values[0] * (1 - ratio/100):  # Падение больше чем ratio%
            return True

        return False

    def check_rapid_exit_average_holders(self, metric_name: str, ratio: float = 3.0, max_seconds: int = 120) -> bool:
        """Проверяет быстрый выход для средней доли холдеров"""
        if len(self.metrics_history) < 10:
            return False

        current_time = time.time()
        recent_data = [entry for entry in self.metrics_history
                      if current_time - entry['timestamp'] <= max_seconds]

        if len(recent_data) < 10:
            return False

        # Вычисляем средние значения
        avg_holders = sum(entry.get('total_holders', 0) for entry in recent_data) / len(recent_data)
        current_holders = recent_data[-1].get('total_holders', 0)

        # Если текущее значение сильно ниже среднего, это быстрый выход
        if current_holders < avg_holders * (1 - ratio/100):
            return True

        return False


class EboshersTracker:
    """Класс для отслеживания ебошеров через WebSocket"""

    def __init__(self):
        self.websocket = None
        self.running = False
        self.logger = logger
        self.JWT_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImVmMjQ4ZjQyZjc0YWUwZjk0OTIwYWY5YTlhMDEzMTdlZjJkMzVmZTEiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoid29ya2VyMTAwMHgiLCJoYXV0aCI6dHJ1ZSwiaXNzIjoiaHR0cHM6Ly9zZWN1cmV0b2tlbi5nb29nbGUuY29tL3BhZHJlLTQxNzAyMCIsImF1ZCI6InBhZHJlLTQxNzAyMCIsImF1dGhfdGltZSI6MTc1NTY0ODA3OCwidXNlcl9pZCI6InRnXzc4OTE1MjQyNDQiLCJzdWIiOiJ0Z183ODkxNTI0MjQ0IiwiaWF0IjoxNzU3MDA2NTAwLCJleHAiOjE3NTcwMTAxMDAsImZpcmViYXNlIjp7ImlkZW50aXRpZXMiOnt9LCJzaWduX2luX3Byb3ZpZGVyIjoiY3VzdG9tIn19.Sf8Yvoh-yRpPo6_hohrvVCz5nj15XD_TwJOwUgHUwuJ5R-R-C22Ldqw-VrI6JV6iD1cvhV_T0iQbDLd-tGnGveoPSk7-G7h6xfchq_08H5skEmKFLK8PFBKV_X8V7MJVn7b4hqYdESaMP4TBJ2IdsFCTu-7kwof2qKMDXojdn5PajvqinmtgCFEVlJEdLYnYLdh4KEn9aFdgLRHrV6ORCXreKAbbrh1_KG6ID1TmCARVx6gJnyqhu-1cQLb3NXezaiL_A2SO5RrrWljpxmr2oKOZiVLoOVU6vHtpGmXY_3b5-VzgWsWe6rzZQMWWDWy_av-oPTq-1_3KRoI5gCLTeA"

        # Отслеживание активности tracked trades для автоматического переподключения
        self.last_tracked_trade_time = None
        self.tracked_trade_timeout = 60  # 1 минута таймаут
        self.connection_established_time = None  # Время установления соединения

        # Отслеживание общего времени последнего сообщения (любого типа)
        self.last_message_time = None
        self.message_timeout = 60  # 1 минута таймаут без любых сообщений

        # Глобальный словарь скоплений ебошеров доступен через ebosher_clusters

        # Таймеры для управления соединением
        self.connection_start_time = None
        self.connection_duration = 10 * 60  # 10 минут в секундах
        self.reconnect_delay = 0  # Немедленное переподключение

    async def connect(self):
        """Подключение к WebSocket"""
        try:
            backend_url = get_next_padre_backend()
            self.logger.info(f"🔗 Подключаемся к: {backend_url}")

            # Заголовки как в браузере
            headers = {
                'Cookie': 'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel=' + PADRE_COOKIES['mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel'],
                'Origin': 'https://trade.padre.gg',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
            }

            # Добавляем обработку ошибок SSL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            self.logger.info("🔌 Создаем WebSocket соединение...")
            # Пробуем подключиться
            self.websocket = await websockets.connect(
                backend_url,
                extra_headers=headers,
                ping_interval=None,
                ping_timeout=None,
                ssl=ssl_context
            )
            self.logger.info("✅ WebSocket соединение установлено")

            # Устанавливаем время начала соединения
            self.connection_start_time = time.time()
            self.connection_established_time = time.time()

            self.logger.info("🔐 Отправляем аутентификацию...")
            # Отправляем аутентификационное сообщение
            await self.send_auth_message()
            self.logger.info("✅ Аутентификация прошла успешно")

            self.logger.info("📡 Отправляем подписку...")
            # Отправляем сообщение подписки на tracked-trades
            await self.send_subscription_message()
            self.logger.info("✅ Подписки отправлены успешно")

            # Небольшая пауза после подписки для стабилизации соединения
            await asyncio.sleep(0.5)
            self.logger.info("🔄 Соединение готово к приему сообщений")

            self.logger.info(f"⏰ Соединение активно на {self.connection_duration // 60} минут")

            # Устанавливаем время успешного подключения для защиты от частых переподключений
            if hasattr(self, 'last_connection_time'):
                self.last_connection_time = time.time()

            # Сбрасываем время последнего tracked trade сообщения при новом подключении
            self.last_tracked_trade_time = None

            # Сбрасываем время последнего сообщения при новом подключении
            self.last_message_time = time.time()

            return True

        except AuthenticationPolicyViolation as e:
            # Специальная обработка - токен был обновлен, требуется переподключение
            self.logger.warning(f"🔐 Токен был обновлен, требуется переподключение: {e}")
            return False  # Возвращаем False чтобы вызвать переподключение
        except websockets.exceptions.InvalidURI as e:
            self.logger.error(f"❌ Неверный URI: {e}")
            return False
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.error(f"❌ Ошибка соединения: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к WebSocket: {type(e).__name__}: {e}")
            return False

    async def send_auth_message(self):
        """Отправляем аутентификационное сообщение"""
        try:
            # Формируем auth message в формате [1, JWT_TOKEN, suffix]
            auth_message = [
                1,
                self.JWT_TOKEN,
                j8()[:13]
            ]
            auth_bytes = msgpack.packb(auth_message)

            self.logger.info("🔐 Отправляем аутентификационное сообщение...")
            self.logger.info(f"📨 Auth message: {auth_message}")

            # Отправляем как бинарные данные (Binary Message)
            await self.websocket.send(auth_bytes)
            self.logger.info("✅ Аутентификационное сообщение отправлено")

            # Ждем ответ с таймаутом
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                self.logger.info(f"📨 Получили ответ аутентификации: {len(response)} байт")

                # Декодируем и логируем ответ для отладки
                if isinstance(response, bytes):
                    decoded_response = decode_padre_message(response)
                    self.logger.info(f"📨 Ответ аутентификации декодирован: {decoded_response}")

            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Таймаут ожидания ответа аутентификации, продолжаем...")
                # Не бросаем исключение, позволяем продолжить

        except websockets.exceptions.ConnectionClosedError as e:
            if e.code == 1008:  # Policy violation - часто означает истекший токен
                self.logger.error(f"❌ Критическая ошибка аутентификации (код 1008): {e}")
                self.logger.info("🔄 Попытка обновить JWT токен...")

                # Пробуем получить новый токен через padre_get_access_token.py
                new_token = None
                try:
                    self.logger.info("🔄 Получаем новый токен через padre_get_access_token.py...")
                    new_token = await self.request_new_token_from_user()
                except Exception as token_error:
                    self.logger.error(f"❌ Не удалось получить токен через padre_get_access_token.py: {token_error}")

                # Если не удалось получить токен, пробуем продолжить с текущим
                if not new_token:
                    self.logger.warning("⚠️ Не удалось получить новый токен, продолжаем с текущим...")
                    return

                # Устанавливаем новый токен
                if new_token and new_token.strip():
                    self.JWT_TOKEN = new_token.strip()
                    self.logger.info("✅ Новый JWT токен установлен")

                    # Вместо повторной отправки по закрытому соединению, бросаем исключение
                    # чтобы вызвать переподключение с новым токеном
                    self.logger.info("🔄 Вызываем переподключение с новым токеном...")
                    raise AuthenticationPolicyViolation("Требуется переподключение с новым токеном")

            self.logger.error(f"❌ Ошибка аутентификации: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Ошибка аутентификации: {e}")
            raise

    async def send_subscription_message(self):
        """Отправляем сообщения подписки на tracked-trades (две подписки)"""
        try:
            # Первая подписка на tracked-trades/wallet-groups
            subscription_message_1 = [
                4,
                1,
                '/tracked-trades/wallet-groups/cba0b62d-a37f-4ecf-8672-56f857d56055/subscribe?encodedFilter=%7B%22tradeType%22%3A%5B0%2C1%2C3%2C2%5D%2C%22amountInUsd%22%3A%7B%7D%2C%22mcapInUsd%22%3A%7B%7D%2C%22tokenAgeSeconds%22%3A%7B%7D%7D'
            ]

            subscription_bytes_1 = msgpack.packb(subscription_message_1)

            self.logger.info("📡 Отправляем первое сообщение подписки на tracked-trades...")
            self.logger.info(f"📨 Subscription message 1: {subscription_message_1}")

            # Отправляем первое сообщение
            await self.websocket.send(subscription_bytes_1)
            self.logger.info("✅ Первое сообщение подписки отправлено")

            # Ждем подтверждение первой подписки
            try:
                response1 = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                self.logger.info(f"📨 Подтверждение первой подписки: {len(response1)} байт")
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Таймаут ожидания подтверждения первой подписки")

            # Ждем небольшую задержку между подписками
            await asyncio.sleep(0.2)

            # Вторая подписка на tracked-trades/wallet-groups (другая группа)
            subscription_message_2 = [
                4,
                2,
                '/tracked-trades/wallet-groups/14b924db-1808-475b-8320-362baa22f92b/subscribe?encodedFilter=%7B%22tradeType%22%3A%5B0%2C1%2C3%2C2%5D%2C%22amountInUsd%22%3A%7B%7D%2C%22mcapInUsd%22%3A%7B%7D%2C%22tokenAgeSeconds%22%3A%7B%7D%7D'
            ]

            subscription_bytes_2 = msgpack.packb(subscription_message_2)

            self.logger.info("📡 Отправляем второе сообщение подписки...")
            self.logger.info(f"📨 Subscription message 2: [4, 34, '/tracked-trades/...']")

            # Отправляем второе сообщение
            await self.websocket.send(subscription_bytes_2)
            self.logger.info("✅ Второе сообщение подписки отправлено")

            # Ждем подтверждение второй подписки
            try:
                response2 = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                self.logger.info(f"📨 Подтверждение второй подписки: {len(response2)} байт")
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Таймаут ожидания подтверждения второй подписки")

            # Вторая подписка на tracked-trades/wallet-groups (другая группа)
            subscription_message_3 = [
                4,
                3,
                '/tracked-trades/wallet-groups/c1031d6c-1e8f-4b03-82c5-863df244aaf5/subscribe?encodedFilter=%7B%22tradeType%22%3A%5B0%2C1%2C3%2C2%5D%2C%22amountInUsd%22%3A%7B%7D%2C%22mcapInUsd%22%3A%7B%7D%2C%22tokenAgeSeconds%22%3A%7B%7D%7D'
            ]

            subscription_bytes_3 = msgpack.packb(subscription_message_3)

            self.logger.info("📡 Отправляем второе сообщение подписки...")
            self.logger.info(f"📨 Subscription message 3: [4, 35, '/tracked-trades/...']")

            # Отправляем второе сообщение
            await self.websocket.send(subscription_bytes_3)
            self.logger.info("✅ Третье сообщение подписки отправлено")

            # Ждем подтверждение второй подписки
            try:
                response3 = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                self.logger.info(f"📨 Подтверждение третьей подписки: {len(response3)} байт")
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Таймаут ожидания подтверждения третьей подписки")

        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки сообщений подписки: {e}")
            raise

    async def request_new_token_from_user(self) -> Optional[str]:
        """Автоматически получает новый JWT токен через padre_get_access_token.py"""
        try:
            self.logger.info("🔄 Автоматически получаем новый JWT токен через padre_get_access_token.py...")

            # Используем executor для выполнения синхронного вызова скрипта
            loop = asyncio.get_event_loop()
            token = await loop.run_in_executor(None, self._sync_get_token_from_script)

            if token:
                self.logger.info("✅ Новый токен успешно получен!")
                return token
            else:
                self.logger.error("❌ Не удалось получить токен через скрипт")
                return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении токена: {e}")
            return None

    def _sync_log_trade(self, token_address: str, log_entry: str):
        """Синхронная запись лога трейда в файл токена"""
        try:
            # Создаем папку если её нет
            if not os.path.exists(EBOSHERS_LOGS_DIR):
                os.makedirs(EBOSHERS_LOGS_DIR)

            # Формируем имя файла
            log_filename = f"{EBOSHERS_LOGS_DIR}/{token_address}.log"

            # Записываем в файл
            with open(log_filename, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {log_entry}\n")
                f.flush()

        except Exception as e:
            print(f"❌ Ошибка записи лога для {token_address}: {e}")

    async def log_trade_to_file(self, token_address: str, wallet_address: str, amount_usd: float, timestamp: int, token_name: str, trade_type: int, market_cap: float):
        """Асинхронное логирование трейда в отдельный файл"""
        try:
            # Формируем строку лога с минимальными данными
            log_entry = (
                f"[{wallet_address}] {'-' if trade_type > 1 else ''}${amount_usd:.2f} | "
                f"{token_name} | mc: {round(market_cap, 2)} | "
                f"Time: {datetime.fromtimestamp(timestamp)}"
            )

            # Записываем в файл в отдельном потоке
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_log_trade, token_address, log_entry)

        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования трейда для {token_address}: {e}")

    def _sync_log_old_metrics_cluster(self, token_address: str, token_name: str, cluster_data: dict):
        """Синхронная запись лога кластера по старым метрикам"""
        try:
            # Формируем строку лога
            wallets = cluster_data['wallets']
            wallet_count = len(wallets)
            min_time = min(wallets.values())
            max_time = max(wallets.values())
            time_span = max_time - min_time

            log_entry = (
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"СТАРЫЕ МЕТРИКИ: {token_address} | "
                f"{token_name} | "
                f"Кошельков: {wallet_count} | "
                f"Временной промежуток: {time_span} сек | "
                f"Кошельки: {', '.join([f'{w[:8]}...' for w in wallets.keys()])}"
            )

            # Записываем в файл
            with open(OLD_METRICS_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{log_entry}\n")
                f.flush()

        except Exception as e:
            print(f"❌ Ошибка записи лога старых метрик для {token_address}: {e}")

    async def log_old_metrics_cluster(self, token_address: str, token_name: str, cluster_data: dict):
        """Асинхронное логирование кластера по старым метрикам"""
        try:
            # Записываем в файл в отдельном потоке
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_log_old_metrics_cluster, token_address, token_name, cluster_data)

        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования кластера старых метрик для {token_address}: {e}")

    def _sync_get_token_from_script(self) -> Optional[str]:
        """Синхронный вызов скрипта padre_get_access_token.py"""
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
                print("✅ Скрипт padre_get_access_token.py выполнен успешно")

                # Читаем токен из файла token.txt
                token_file = os.path.join(os.path.dirname(__file__), "token.txt")
                if os.path.exists(token_file):
                    with open(token_file, 'r') as f:
                        token = f.read().strip()

                    if token and token.startswith('eyJ'):
                        return token
                    else:
                        print("❌ Токен в файле имеет неправильный формат")
                        return None
                else:
                    print("❌ Файл token.txt не найден")
                    return None
            else:
                print(f"❌ Ошибка выполнения скрипта: {result.stderr}")
                return None

        except Exception as e:
            print(f"❌ Ошибка при вызове скрипта: {e}")
            return None

    async def listen_for_messages(self):
        """Слушаем входящие сообщения с автоматическим переподключением"""
        self.logger.info("👂 Запуск прослушивания сообщений...")
        messages_processed = 0

        while self.running:
            self.logger.debug(f"🔄 Начало новой итерации цикла, running={self.running}")
            try:
                if not self.websocket:
                    self.logger.warning("⚠️ WebSocket не инициализирован, пытаемся переподключиться...")
                    if self.running:
                        await self.force_reconnect()
                        # После успешного переподключения продолжаем цикл
                        continue
                    else:
                        self.logger.info(f"📊 Выход из цикла из-за running=False (WebSocket не инициализирован)")
                        break

                self.logger.info(f"👂 Начинаем прослушивание сообщений (итерация #{messages_processed})...")
                iteration_start = time.time()

                # Проверяем, что соединение готово (авторизация и подписки отправлены)
                if not hasattr(self, 'connection_start_time') or self.connection_start_time is None or (time.time() - self.connection_start_time) > 600:  # Более 10 минут
                    self.logger.warning("⚠️ Соединение не инициализировано, повторно отправляем авторизацию и подписку...")
                    try:
                        self.logger.info("🔐 Повторная отправка аутентификации...")
                        await self.send_auth_message()
                        self.logger.info("✅ Аутентификация повторно отправлена")

                        self.logger.info("📡 Повторная отправка подписок...")
                        await self.send_subscription_message()
                        self.logger.info("✅ Подписки повторно отправлены")

                        # Устанавливаем время начала соединения
                        self.connection_start_time = time.time()
                        await asyncio.sleep(0.5)  # Пауза для стабилизации

                    except Exception as e:
                        self.logger.error(f"❌ Ошибка при повторной авторизации/подписке: {e}")
                        if self.running:
                            await self.force_reconnect()
                            # После успешного переподключения продолжаем цикл без выхода
                            continue
                        else:
                            self.logger.info(f"📊 Выход из цикла из-за running=False (повторная авторизация)")
                            break

                # Дополнительная проверка состояния соединения
                try:
                    # Проверяем, что соединение не закрылось сразу после подписки
                    await asyncio.sleep(0.1)  # Короткая пауза для проверки
                    if self.websocket.closed:
                        self.logger.warning("⚠️ Соединение закрылось сразу после подписки, повторное переподключение...")
                        if self.running:
                            await self.force_reconnect()
                            # После успешного переподключения продолжаем цикл без выхода
                            continue
                        else:
                            self.logger.info(f"📊 Выход из цикла из-за running=False (проверка соединения)")
                            break
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка проверки состояния соединения: {e}")
                    if self.running:
                        await self.force_reconnect()
                        # После успешного переподключения продолжаем цикл без выхода
                        continue
                    else:
                        self.logger.info(f"📊 Выход из цикла из-за running=False (ошибка проверки соединения)")
                        break

                messages_in_iteration = 0
                async for message in self.websocket:
                    # Проверяем таймаут tracked trades перед обработкой каждого сообщения
                    # Только если прошло минимум 2 минуты после установления соединения
                    current_time = time.time()
                    if (self.connection_established_time is not None and
                        current_time - self.connection_established_time > 120 and  # 2 минуты после подключения
                        self.last_tracked_trade_time is not None and
                        current_time - self.last_tracked_trade_time > self.tracked_trade_timeout):
                        self.logger.warning(f"⏰ Таймаут tracked trades: {self.tracked_trade_timeout} сек без новых данных")
                        self.logger.info("🔄 Выполняем переподключение из-за отсутствия активности tracked trades...")
                        await self.force_reconnect()
                        break  # Выходим из цикла прослушивания для переподключения

                    if isinstance(message, bytes):
                        # Декодируем бинарные данные
                        decoded_data = decode_padre_message(message)

                        if decoded_data:
                            # Обрабатываем сообщение
                            await self.process_message(decoded_data)
                            messages_processed += 1
                            messages_in_iteration += 1
                        else:
                            self.logger.debug(f"📦 Неизвестное бинарное сообщение: {len(message)} байт")

                    elif isinstance(message, str):
                        # Обновляем время последнего полученного сообщения
                        self.last_message_time = time.time()
                        self.logger.info(f"📨 Текстовое сообщение: {message}")

                # Если дошли до сюда, значит соединение закрылось
                iteration_duration = time.time() - iteration_start
                self.logger.info(f"🔚 Итерация завершена: {messages_in_iteration} сообщений за {iteration_duration:.1f} сек")

                # Если итерация была слишком короткой и не обработала сообщений, добавляем задержку
                if iteration_duration < 1.0 and messages_in_iteration == 0:
                    self.logger.warning("⚠️ Соединение закрылось слишком быстро, добавляем задержку 2 сек...")
                    await asyncio.sleep(2)

            except websockets.exceptions.ConnectionClosed:
                iteration_duration = time.time() - iteration_start
                self.logger.warning(f"🔌 WebSocket соединение закрыто после {iteration_duration:.1f} сек")
                if self.running:
                    await self.force_reconnect()
                    # После переподключения продолжаем цикл
                    continue
                else:
                    self.logger.info(f"📊 Выход из цикла из-за running=False (ConnectionClosed)")
                    break

            except websockets.exceptions.ConnectionClosedError as e:
                iteration_duration = time.time() - iteration_start
                self.logger.warning(f"🔌 WebSocket соединение закрыто с ошибкой после {iteration_duration:.1f} сек: {e}")
                if self.running:
                    await self.force_reconnect()
                    # После переподключения продолжаем цикл
                    continue
                else:
                    self.logger.info(f"📊 Выход из цикла из-за running=False (ConnectionClosedError)")
                    break

            except KeyboardInterrupt:
                self.logger.info("🛑 Получен сигнал прерывания в прослушивании")
                self.running = False
                self.logger.info(f"📊 Выход из цикла из-за KeyboardInterrupt")
                break
            except AuthenticationPolicyViolation as e:
                # Специальная обработка ошибки аутентификации - токен истек или требуется новый
                iteration_duration = time.time() - iteration_start
                self.logger.warning(f"🔐 Ошибка аутентификации после {iteration_duration:.1f} сек: {e}")
                if self.running:
                    await self.force_reconnect()
                    # После переподключения продолжаем цикл
                    continue
                else:
                    self.logger.info(f"📊 Выход из цикла из-за running=False (AuthenticationPolicyViolation)")
                    break
            except Exception as e:
                iteration_duration = time.time() - iteration_start
                self.logger.error(f"❌ Ошибка при прослушивании после {iteration_duration:.1f} сек: {e}")
                if self.running:
                    await self.force_reconnect()
                    # После переподключения продолжаем цикл
                    continue
                else:
                    self.logger.info(f"📊 Выход из цикла из-за running=False (Exception)")
                    break

        self.logger.info(f"🛑 Завершение прослушивания сообщений. Всего обработано: {messages_processed} сообщений")
        self.logger.info(f"📊 Состояние системы: running={self.running}")

    async def process_message(self, message_data: dict):
        """Обрабатываем входящее сообщение"""
        try:
            # Обновляем время последнего полученного сообщения (любого типа)
            self.last_message_time = time.time()

            # Обработка нового формата Padre сообщений
            if 'type' in message_data and message_data['type'] == 'msg':
                conn_id = message_data.get('connId', '')
                payload = message_data.get('payload', {})

                if payload.get('type') == 'init' and 'snapshot' in payload:
                    # Обновляем время последнего tracked trade сообщения при получении snapshot
                    self.last_tracked_trade_time = time.time()

                    snapshot = payload['snapshot']

                    # Обрабатываем трейды из snapshot
                    if 'trades' in snapshot:
                        await self.process_tracked_trades(snapshot['trades'])

                elif payload.get('type') == 'update' and 'update' in payload:
                    # Обновляем время последнего tracked trade сообщения
                    self.last_tracked_trade_time = time.time()

                    # Обработка обновлений трейдов
                    update_data = payload['update']
                    if 'newTrades' in update_data:
                        await self.process_tracked_trades(update_data['newTrades'])

                self.logger.info(f"📨 Обработано сообщение connId={conn_id}, тип={payload.get('type', 'unknown')}")

            # Обработка старого формата, который теперь возвращается как прямой словарь (аналогично payload нового формата)
            elif isinstance(message_data, dict) and message_data.get('type') == 'init' and 'snapshot' in message_data:
                self.last_tracked_trade_time = time.time()
                snapshot = message_data['snapshot']
                if 'trades' in snapshot:
                    await self.process_tracked_trades(snapshot['trades'])
                self.logger.info(f"📨 Обработано сообщение старого формата (init snapshot), тип={message_data.get('type', 'unknown')}")

            elif isinstance(message_data, dict) and message_data.get('type') == 'update' and 'update' in message_data:
                self.last_tracked_trade_time = time.time()
                update_data = message_data['update']
                if 'newTrades' in update_data:
                    await self.process_tracked_trades(update_data['newTrades'])
                self.logger.info(f"📨 Обработано сообщение старого формата (update), тип={message_data.get('type', 'unknown')}")

            # Обработка tracked_trades типа сообщений (от decode_padre_message)
            elif 'type' in message_data and message_data['type'] == 'tracked_trades':
                # Обновляем время последнего tracked trade сообщения
                self.last_tracked_trade_time = time.time()

                raw_data = message_data.get('raw_data', [])
                if len(raw_data) >= 2:
                    conn_id = raw_data[1]  # connection id
                    self.logger.info(f"📨 Получено tracked_trades сообщение, connId={conn_id}")

                    # tracked_trades сообщения могут содержать данные о трейдах
                    # Обычно это ответы на подписки или обновления
                    if len(raw_data) >= 3:
                        payload = raw_data[2]
                        if isinstance(payload, dict):
                            # Проверяем, есть ли данные о трейдах
                            if 'trades' in payload:
                                await self.process_tracked_trades(payload['trades'])
                            elif 'snapshot' in payload and 'trades' in payload['snapshot']:
                                await self.process_tracked_trades(payload['snapshot']['trades'])
                            else:
                                self.logger.debug(f"📦 tracked_trades payload без трейдов: {payload}")

                            # Если в payload есть трейды, обновляем время последнего сообщения
                            if 'trades' in payload or ('snapshot' in payload and 'trades' in payload['snapshot']):
                                self.last_tracked_trade_time = time.time()

            # Обработка специального сообщения для переподключения
            elif 'type' in message_data and message_data['type'] == 'reconnect_required':
                message_type = message_data.get('message_type', 0)
                payload = message_data.get('payload', 0)
                self.logger.warning(f"🔄 Получено специальное сообщение для переподключения: message_type={message_type}, payload={payload}")
                self.logger.info("🔄 Выполняем принудительное переподключение WebSocket...")
                await self.force_reconnect()
                return  # Выходим из обработки, так как переподключение уже выполнено

            # Обработка системных сообщений
            elif 'type' in message_data and message_data['type'] == 'system':
                message_type = message_data.get('message_type', 0)
                self.logger.debug(f"📨 Системное сообщение типа {message_type}")

            # Обработка неизвестных типов
            elif 'type' in message_data and message_data['type'] == 'unknown':
                raw_data = message_data.get('raw_data', [])
                if len(raw_data) >= 1:
                    message_type = raw_data[0]
                    self.logger.debug(f"📨 Неизвестное сообщение типа {message_type}: {raw_data}")

            else:
                # Обработка старого формата или других типов сообщений
                self.logger.debug(f"📨 Неизвестный формат сообщения: {message_data}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки сообщения: {e}")
            import traceback
            self.logger.error(f"📋 Traceback: {traceback.format_exc()}")

    async def process_tracked_trades(self, trades_data):
        """Обрабатываем данные о tracked trades"""
        try:
            if not trades_data:
                return

            self.logger.info(f"📊 Обрабатываем tracked trades: {len(trades_data)} записей")

            for trade in trades_data:
                # Новый формат: трейд представлен как список элементов
                if isinstance(trade, list) and len(trade) >= 18:
                    # Извлекаем только необходимые данные
                    timestamp = trade[1]  # Временная метка
                    wallet_address = trade[3]  # Адрес кошелька
                    amount_usd = trade[4]  # Сумма в долларах
                    token_address = trade[12]  # Адрес токена
                    token_name = trade[17] if len(trade) > 17 else 'Unknown'  # Название токена
                    trade_type = trade[7]

                    # Извлекаем market cap (предположительно в миллиардах)
                    market_cap_raw = trade[8] if len(trade) > 8 else 0
                    market_cap = market_cap_raw * 1000000000  # Конвертируем в доллары

                    # Логируем каждый трейд для отладки
                    self.logger.debug(f"📊 Трейд: amount={amount_usd:.2f}, market_cap_raw={market_cap_raw}, market_cap={market_cap:.0f}, token={token_name}")

                    # ФИЛЬТР: учитываем только ПОКУПКИ (положительная сумма)
                    if amount_usd <= 0:
                        self.logger.debug(f"❌ Пропущен трейд: отрицательная сумма {amount_usd}")
                        continue  # Пропускаем продажи и нулевые суммы

                    # ФИЛЬТР: market cap от 50k до 300k
                    if market_cap < 50000 or market_cap > 300000:
                        # Логируем пропущенные трейды для отладки
                        self.logger.debug(f"❌ Пропущен трейд: market_cap {market_cap:.0f} вне диапазона 50k-300k")
                        continue

                    # Обрабатываем трейд с минимальными данными
                    await self.process_trade(wallet_address, token_address, amount_usd, timestamp, token_name, market_cap, trade_type)

                else:
                    # Старый формат или неизвестный
                    self.logger.debug(f"📦 Неизвестный формат трейда: {trade}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки tracked trades: {e}")
            import traceback
            self.logger.error(f"📋 Traceback: {traceback.format_exc()}")

    async def process_trade(self, wallet_address: str, token_address: str, amount_usd: float, timestamp: int, token_name: str, market_cap: float = 0, trade_type: int = 0):
        """Обрабатываем трейд ебошера и проверяем на скопления"""
        try:
            # Обновляем последнюю рыночную капитализацию в кластере
            if token_address in ebosher_clusters:
                ebosher_clusters[token_address]['last_market_cap'] = market_cap

            # Логируем трейд в отдельный файл для токена
            await self.log_trade_to_file(token_address, wallet_address, amount_usd, timestamp, token_name, trade_type, market_cap)

            # Проверяем на скопление ебошеров
            await self.check_ebosher_cluster(wallet_address, token_address, amount_usd, timestamp, token_name)

            # Также проверяем по старым метрикам (4+ кошельков за час)
            await self.check_old_metrics_cluster(wallet_address, token_address, timestamp, token_name)

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки трейда {wallet_address[:8]}: {e}")

    async def check_ebosher_cluster(self, wallet_address: str, token_address: str, amount_usd: float, timestamp: int, token_name: str):
        """Проверяем на скопление ебошеров в токене по объему ПЕРВЫХ ПОКУПОК (только положительные суммы, без повторных покупок от одного кошелька)"""
        try:
            # Параметры для определения скопления
            VOLUME_THRESHOLD_USD = 2000  # Минимум 2000 долларов общий объем
            TIME_WINDOW_SECONDS = 120  # 2 минуты - временное окно
            CLEANUP_TIME_SECONDS = 300  # Очищать старые записи через час

            # Инициализируем кластер для токена если его нет
            if token_address not in ebosher_clusters:
                ebosher_clusters[token_address] = {
                    'wallets': {},  # wallet -> {'amount': usd, 'timestamp': time}
                    'total_volume': 0,
                    'first_detection': timestamp,
                    'last_update': timestamp,
                    'token_name': token_name,
                    'detected': False,
                    'last_market_cap': 0  # Последняя рыночная капитализация
                }

            cluster = ebosher_clusters[token_address]

            # Добавляем кошелек в кластер (ТОЛЬКО ПЕРВАЯ ПОКУПКА)
            if wallet_address not in cluster['wallets']:
                cluster['wallets'][wallet_address] = {
                    'amount': amount_usd,
                    'timestamp': timestamp
                }
                cluster['total_volume'] += amount_usd
            else:
                # Повторная покупка от того же кошелька - игнорируем
                self.logger.debug(f"⚠️ Повторная покупка от кошелька {wallet_address[:8]} игнорируется")
                return  # Выходим из функции, не обновляя кластер

            cluster['last_update'] = timestamp

            # Очищаем старые записи (кошельки, которые давно не торговали)
            current_time = timestamp
            wallets_to_remove = []
            volume_to_remove = 0

            for wallet, wallet_data in cluster['wallets'].items():
                if current_time - wallet_data['timestamp'] > CLEANUP_TIME_SECONDS:
                    wallets_to_remove.append(wallet)
                    volume_to_remove += wallet_data['amount']

            for wallet in wallets_to_remove:
                del cluster['wallets'][wallet]
                cluster['total_volume'] -= volume_to_remove

            # Проверяем, является ли это скоплением по объему И по количеству кошельков
            WALLET_THRESHOLD = 10  # Минимум 10 кошелька
            if (cluster['total_volume'] >= VOLUME_THRESHOLD_USD and len(cluster['wallets']) >= WALLET_THRESHOLD) and not cluster['detected']:
                # СКОПЛЕНИЕ ОБНАРУЖЕНО! (без проверки временного окна)
                cluster['detected'] = True

                # Вычисляем временную статистику для логов
                wallet_timestamps = [data['timestamp'] for data in cluster['wallets'].values()]
                if wallet_timestamps:
                    min_time = min(wallet_timestamps)
                    max_time = max(wallet_timestamps)
                    time_span = max_time - min_time
                else:
                    min_time = timestamp
                    max_time = timestamp
                    time_span = 0

                # Определяем критерий обнаружения
                detection_reason = f"ПЕРВЫЕ ПОКУПКИ: ОБЪЕМ ≥ ${VOLUME_THRESHOLD_USD} + КОШЕЛЬКИ ≥ {WALLET_THRESHOLD}"

                self.logger.info("🚨 " + "="*60)
                self.logger.info("🎯 СКОПЛЕНИЕ ЕБОШЕРОВ ОБНАРУЖЕНО!")
                self.logger.info(f"📊 КРИТЕРИЙ: {detection_reason}")
                self.logger.info("🚨 " + "="*60)
                self.logger.info(f"🪙 ТОКЕН: {token_name}")
                self.logger.info(f"📍 АДРЕС: {token_address}")
                self.logger.info(f"💰 ОБЩИЙ ОБЪЕМ: ${cluster['total_volume']:,.2f}")
                self.logger.info(f"👥 КОШЕЛЬКОВ: {len(cluster['wallets'])}")
                self.logger.info(f"⏱️  ВРЕМЕННОЙ ПРОМЕЖУТОК: {time_span} сек")
                self.logger.info(f"🕒 ПЕРВЫЙ ВХОД: {datetime.fromtimestamp(min_time)}")
                self.logger.info(f"🕒 ПОСЛЕДНИЙ ВХОД: {datetime.fromtimestamp(max_time)}")

                # Выводим список кошельков с суммами
                self.logger.info("📋 КОШЕЛЬКИ:")
                for i, (wallet, wallet_data) in enumerate(sorted(cluster['wallets'].items(), key=lambda x: x[1]['timestamp']), 1):
                    time_diff = wallet_data['timestamp'] - min_time
                    self.logger.info(f"   {i}. {wallet[:12]}... ${wallet_data['amount']:.2f} (вход через {time_diff} сек)")

                self.logger.info("🚨 " + "="*60)

                # Отправляем уведомление в Telegram
                await self.notify_ebosher_cluster(token_address, token_name, cluster)

                # Уведомление о найденном скоплении
                self.logger.info("✅ СКОПЛЕНИЕ ЕБОШЕРОВ НАЙДЕНО!")

        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки скопления для {token_address[:8]}: {e}")

    async def check_old_metrics_cluster(self, wallet_address: str, token_address: str, timestamp: int, token_name: str):
        """Проверяем на скопление ебошеров по старым метрикам (4+ кошельков за час)"""
        try:
            # Параметры для определения скопления по старым метрикам
            OLD_METRICS_WALLET_THRESHOLD = 4  # Минимум 4 кошелька
            OLD_METRICS_TIME_WINDOW = 1800     # полчаса
            OLD_METRICS_CLEANUP_TIME = 3600   # Очистка через 1 час

            # Инициализируем кластер для токена если его нет
            if token_address not in old_metrics_clusters:
                old_metrics_clusters[token_address] = {
                    'wallets': {},
                    'first_detection': timestamp,
                    'cluster_size': 0,
                    'last_update': timestamp,
                    'token_name': token_name,
                    'detected': False
                }

            cluster = old_metrics_clusters[token_address]

            # Добавляем кошелек в кластер
            if wallet_address not in cluster['wallets']:
                cluster['wallets'][wallet_address] = timestamp
                cluster['cluster_size'] += 1
                cluster['last_update'] = timestamp

            # Очищаем старые записи (кошельки, которые давно не торговали)
            current_time = timestamp
            wallets_to_remove = []
            for wallet, wallet_timestamp in cluster['wallets'].items():
                if current_time - wallet_timestamp > OLD_METRICS_CLEANUP_TIME:
                    wallets_to_remove.append(wallet)

            for wallet in wallets_to_remove:
                del cluster['wallets'][wallet]
                cluster['cluster_size'] -= 1

            # Проверяем, является ли это скоплением по старым метрикам
            if cluster['cluster_size'] >= OLD_METRICS_WALLET_THRESHOLD and not cluster['detected']:
                # Проверяем, что все кошельки вошли в часовой промежуток времени
                wallet_timestamps = list(cluster['wallets'].values())
                if wallet_timestamps:
                    min_time = min(wallet_timestamps)
                    max_time = max(wallet_timestamps)
                    time_span = max_time - min_time

                    if time_span <= OLD_METRICS_TIME_WINDOW:
                        # СКОПЛЕНИЕ ПО СТАРЫМ МЕТРИКАМ ОБНАРУЖЕНО!
                        cluster['detected'] = True

                        self.logger.info("📊 " + "="*50)
                        self.logger.info("🎯 СКОПЛЕНИЕ ПО СТАРЫМ МЕТРИКАМ!")
                        self.logger.info("📊 " + "="*50)
                        self.logger.info(f"🪙 ТОКЕН: {token_name}")
                        self.logger.info(f"📍 АДРЕС: {token_address}")
                        self.logger.info(f"👥 КОШЕЛЬКОВ: {cluster['cluster_size']}")
                        self.logger.info(f"⏱️  ВРЕМЕННОЙ ПРОМЕЖУТОК: {time_span} сек")

                        # Логируем в файл (без отправки в Telegram)
                        await self.log_old_metrics_cluster(token_address, token_name, cluster)

                        self.logger.info("✅ СКОПЛЕНИЕ ПО СТАРЫМ МЕТРИКАМ ЗАЛОГИРОВАНО!")

        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки старых метрик для {token_address[:8]}: {e}")

    async def send_telegram_message(self, message: str, keyboard=None, chat_id=None, thread_id=None) -> bool:
        """Отправляет сообщение в Telegram"""
        try:
            # Проверяем, не слишком ли часто отправляем
            current_time = time.time()
            if hasattr(self, 'last_telegram_time'):
                time_since_last = current_time - self.last_telegram_time
                if time_since_last < 3:  # Минимум 3 секунды между сообщениями
                    await asyncio.sleep(3 - time_since_last)

            # Используем переданный chat_id или по умолчанию
            chat_id = chat_id or TARGET_CHAT_ID

            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }

            # Добавляем thread_id только если он указан (для групп с ветками)
            if thread_id is not None:
                data["message_thread_id"] = thread_id

            if keyboard:
                data["reply_markup"] = {"inline_keyboard": keyboard}

            self.logger.info(f"📤 Отправляем в Telegram: chat={chat_id}, thread={thread_id}")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = (await response.json()).get('parameters', {}).get('retry_after', 30)
                        self.logger.warning(f"⚠️ Слишком много запросов к Telegram API. Ждем {retry_after} сек.")
                        await asyncio.sleep(retry_after)
                        # Пробуем отправить еще раз
                        async with session.post(url, json=data) as retry_response:
                            if retry_response.status != 200:
                                self.logger.error(f"❌ Ошибка Telegram API: {retry_response.status} - {await retry_response.text()}")
                                return False
                    elif response.status != 200:
                        self.logger.error(f"❌ Ошибка Telegram API: {response.status} - {await response.text()}")
                        return False

            # Сохраняем время последней отправки
            self.last_telegram_time = time.time()
            self.logger.info("✅ Сообщение успешно отправлено в Telegram")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки в Telegram: {e}")
            return False

    async def notify_ebosher_cluster(self, token_address: str, token_name: str, cluster_data: dict):
        """Отправляет уведомление о скоплении ебошеров в Telegram"""
        try:
            # Проверяем, не отправляли ли уже уведомление для этого токена
            if is_token_sent(token_address):
                self.logger.info(f"⏭️  Токен {token_address[:8]} уже был отправлен ранее, пропускаем")
                return
            wallets = cluster_data['wallets']
            wallet_timestamps = [data['timestamp'] for data in wallets.values()]
            min_time = min(wallet_timestamps)
            max_time = max(wallet_timestamps)
            time_span = max_time - min_time
            total_volume = cluster_data['total_volume']

            # Получаем последнюю рыночную капитализацию
            last_market_cap = cluster_data.get('last_market_cap', 0)

            # Проверяем наличие специальных кошельков для отправки в особую ветку
            special_wallets = {
                "8znHBwV5wSBWDg7ruwYkHeMDNXQ2BPiwBzkTDJeUy1rP",
                "niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS"
            }

            special_wallet_qualified_high_value = False
            qualified_special_wallet_high_value = None
            special_wallet_qualified_low_value = False
            qualified_special_wallet_low_value = None # To log which low value special wallet triggered it

            for wallet, wallet_data in wallets.items():
                if wallet in special_wallets:
                    amount = wallet_data['amount']
                    if amount > 3000:
                        special_wallet_qualified_high_value = True
                        qualified_special_wallet_high_value = wallet
                        self.logger.info(f"🎯 Специальный кошелек {wallet[:8]}... квалифицирован (высокая сумма): ${amount:.2f} > $3000")
                    elif amount > 0 and amount <= 3000:
                        special_wallet_qualified_low_value = True
                        qualified_special_wallet_low_value = wallet
                        self.logger.info(f"🎯 Специальный кошелек {wallet[:8]}... квалифицирован (низкая сумма): ${amount:.2f} <= $3000")


            # Выбираем основной канал для отправки (логика для high_value_special_wallet)
            selected_chat_id = STANDARD_CHAT_ID
            selected_thread_id = None

            if special_wallet_qualified_high_value and len(wallets) == 10 and total_volume >= 3000:
                selected_chat_id = SPECIAL_CHAT_ID  # Канал для специальных сообщений
                selected_thread_id = None  # В каналах нет веток
                self.logger.info(f"🎯 Отправляем в специальный канал {selected_chat_id} (спец. кошелек: {qualified_special_wallet_high_value[:8]}...)")
            else:
                if not special_wallet_qualified_high_value:
                    self.logger.debug(f"📝 Отправляем в стандартный канал (нет квалифицированного спец. кошелька высокой стоимости)")
                elif len(wallets) != 10:
                    self.logger.debug(f"📝 Отправляем в стандартный канал (кошельков: {len(wallets)} != 10)")
                elif total_volume < 3000:
                    self.logger.debug(f"📝 Отправляем в стандартный канал (объем: ${total_volume:.2f} < $3000)")


            # Формируем сообщение в формате Markdown
            message = (
                f"**памп монеты от топов**\n\n"
                f"**{token_name}**\n"
                f"`{token_address}`\n\n"
                f"mc: ${last_market_cap:,.0f}\n\n"
                f"[axiom](https://axiom.trade/t/{token_address}) | "
                f"[padre](https://trade.padre.gg/trade/solana/{token_address}) |"
                f"[gmgn](https://gmgn.ai/sol/token/{token_address})\n\n"
                f"*🚀 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} © **by Wormster***"
            )

            # Создаем клавиатуру с кнопкой быстрой покупки
            keyboard = [[{
                "text": "⚡ QUICK BUY",
                "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{token_address}"
            }]]

            # Отправляем сообщение в выбранный канал
            success_main = await self.send_telegram_message(message, keyboard, selected_chat_id, selected_thread_id)
            duplicate_info_for_log = ""
            success_duplicate_special = True # Assume true if not sent

            # Если это специальное сообщение (по высокой стоимости), дублируем в SPECIAL_DUPLICATE_CHAT_ID
            if special_wallet_qualified_high_value and selected_chat_id == SPECIAL_CHAT_ID:
                success_duplicate_special = await self.send_telegram_message(message, keyboard, SPECIAL_DUPLICATE_CHAT_ID, None)
                if success_duplicate_special:
                    self.logger.info(f"📢 Дубликат отправлен в дополнительный канал {SPECIAL_DUPLICATE_CHAT_ID}")
                    duplicate_info_for_log += " (с дубликатом в SPECIAL_DUPLICATE)"
                else:
                    self.logger.warning(f"⚠️ Не удалось отправить дубликат в дополнительный канал {SPECIAL_DUPLICATE_CHAT_ID}")

            # НОВАЯ ЛОГИКА: Если специальный кошелек зашел на сумму <= $3000, отправляем в NEW_ADDITIONAL_CHANNEL_ID
            success_duplicate_new_additional = True # Assume true if not sent
            if special_wallet_qualified_low_value:
                self.logger.info(f"🎯 Отправляем в новый дополнительный канал {NEW_ADDITIONAL_CHANNEL_ID} (спец. кошелек: {qualified_special_wallet_low_value[:8]}... с низкой суммой)")
                success_duplicate_new_additional = await self.send_telegram_message(message, keyboard, NEW_ADDITIONAL_CHANNEL_ID, None)
                if success_duplicate_new_additional:
                    self.logger.info(f"📢 Дубликат отправлен в новый дополнительный канал {NEW_ADDITIONAL_CHANNEL_ID}")
                    duplicate_info_for_log += " (с дубликатом в NEW_ADDITIONAL_CHANNEL)"
                else:
                    self.logger.warning(f"⚠️ Не удалось отправить дубликат в новый дополнительный канал {NEW_ADDITIONAL_CHANNEL_ID}")


            # Проверяем успешность отправки основного сообщения
            if success_main:
                channel_type = "специальный канал" if selected_chat_id == SPECIAL_CHAT_ID else "стандартный канал"
                self.logger.info(f"📢 Уведомление о скоплении отправлено для {token_address[:8]} в {channel_type}{duplicate_info_for_log}")

                # Добавляем токен в список отправленных только при успешной отправке в основной канал
                add_sent_token(token_address)
            else:
                self.logger.error(f"❌ Не удалось отправить уведомление о скоплении для {token_address[:8]}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки уведомления о скоплении: {e}")

    async def print_eboshers_stats(self):
        """Выводит статистику по ебошерам"""
        try:
            if not self.eboshers_stats:
                self.logger.info("📊 Нет данных о ебошерах")
                return

            self.logger.info("📊 === СТАТИСТИКА ЕБОШЕРОВ ===")

            # Сортируем ебошеров по скорости входа (от самой быстрой к самой медленной)
            sorted_eboshers = sorted(
                self.eboshers_stats.items(),
                key=lambda x: x[1]['entry_speed_seconds'],
                reverse=True
            )

            for wallet, stats in sorted_eboshers:
                entry_speed = stats['entry_speed_seconds']
                trade_count = stats['trade_count']
                total_volume = stats['total_volume_usd']
                tokens_count = len(stats['tokens_traded'])

                # Определяем скорость (быстрый/средний/медленный вход)
                if entry_speed == 0:
                    speed_category = "⚡ НОВЫЙ"
                elif entry_speed < 60:
                    speed_category = "⚡ ОЧЕНЬ БЫСТРЫЙ"
                elif entry_speed < 300:
                    speed_category = "🚀 БЫСТРЫЙ"
                elif entry_speed < 1800:
                    speed_category = "🏃 СРЕДНИЙ"
                else:
                    speed_category = "🐌 МЕДЛЕННЫЙ"

                self.logger.info(f"👨‍💼 {wallet[:8]}...: {speed_category}")
                self.logger.info(f"   ⏱️  Скорость входа: {entry_speed} сек")
                self.logger.info(f"   📊 Трейдов: {trade_count}")
                self.logger.info(f"   💰 Объем: ${total_volume:,.2f}")
                self.logger.info(f"   🪙 Токенов: {tokens_count}")

            self.logger.info("📊 === КОНЕЦ СТАТИСТИКИ ===")

        except Exception as e:
            self.logger.error(f"❌ Ошибка вывода статистики ебошеров: {e}")

    async def stats_monitor_task(self):
        """Задача для периодического вывода статистики"""
        try:
            while self.running:
                await asyncio.sleep(300)  # Каждые 5 минут
                if self.running:  # Проверяем, что еще не остановлены
                    await self.print_eboshers_stats()
        except Exception as e:
            self.logger.error(f"❌ Ошибка в задаче мониторинга статистики: {e}")

    def should_reconnect(self) -> bool:
        """Проверяет, нужно ли переподключиться (истекло время соединения)"""
        if not self.connection_start_time:
            return False

        elapsed = time.time() - self.connection_start_time
        return elapsed >= self.connection_duration

    def get_remaining_connection_time(self) -> float:
        """Возвращает оставшееся время соединения в секундах"""
        if not self.connection_start_time:
            return self.connection_duration

        elapsed = time.time() - self.connection_start_time
        return max(0, self.connection_duration - elapsed)

    async def connection_timer_task(self):
        """Задача для отслеживания времени соединения и автоматического переподключения"""
        try:
            while self.running:
                if self.should_reconnect():
                    self.logger.info("⏰ Время соединения истекло (10 мин), переподключаемся немедленно...")
                    await self.force_reconnect()
                else:
                    # Проверяем каждые 30 секунд
                    await asyncio.sleep(30)
        except Exception as e:
            self.logger.error(f"❌ Ошибка в задаче таймера соединения: {e}")

    async def message_timeout_task(self):
        """Задача для отслеживания таймаута сообщений и автоматического переподключения"""
        try:
            while self.running:
                current_time = time.time()

                # Проверяем, прошло ли более минуты с момента последнего сообщения
                if (self.last_message_time is not None and
                    self.connection_established_time is not None and
                    current_time - self.connection_established_time > 30 and  # Ждем минимум 30 сек после подключения
                    current_time - self.last_message_time > self.message_timeout):

                    self.logger.warning(f"⏰ Таймаут сообщений: {self.message_timeout} сек без данных от сервера")
                    self.logger.info("🔄 Выполняем переподключение для обновления авторизации и подписок...")

                    # Выполняем переподключение для обновления авторизации и подписок
                    await self.force_reconnect()

                # Проверяем каждые 10 секунд
                await asyncio.sleep(10)

        except Exception as e:
            self.logger.error(f"❌ Ошибка в задаче таймаута сообщений: {e}")

    async def force_reconnect(self):
        """Немедленное переподключение с защитой от бесконечного цикла"""
        try:
            # Счетчик попыток переподключения
            if not hasattr(self, 'reconnect_attempts'):
                self.reconnect_attempts = 0
                self.last_connection_time = 0

            self.reconnect_attempts += 1
            current_time = time.time()

            self.logger.info(f"🔄 Начинаем переподключение (попытка #{self.reconnect_attempts})...")

            # Закрываем текущее соединение
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка при закрытии соединения: {e}")
                self.websocket = None

            # Вычисляем задержку на основе времени с момента последнего успешного подключения
            if self.last_connection_time > 0:
                time_since_last_connection = current_time - self.last_connection_time
                if time_since_last_connection < 5:  # Если прошло менее 5 секунд
                    delay = 5 - time_since_last_connection
                    self.logger.warning(f"⚠️ Слишком частые переподключения. Ждем {delay:.1f} сек...")
                    await asyncio.sleep(delay)

            # Защита от бесконечного цикла переподключений
            if self.reconnect_attempts > 5:
                # После 5 неудачных попыток увеличиваем задержку
                delay = min(30, self.reconnect_attempts * 2)  # Максимум 30 секунд
                self.logger.warning(f"⚠️ Много неудачных попыток переподключения. Ждем {delay} сек...")
                await asyncio.sleep(delay)
            elif self.reconnect_attempts > 15:
                # После 15 попыток останавливаем систему
                self.logger.error("🚫 Слишком много неудачных попыток переподключения. Останавливаем систему...")
                self.running = False
                return
            else:
                # Первые 5 попыток - немедленное переподключение
                await asyncio.sleep(0.1)  # Минимальная задержка

            # Пытаемся подключиться заново
            try:
                connect_result = await self.connect()
                if connect_result:
                    self.logger.info("✅ Переподключение успешно! Продолжаем работу...")
                    self.reconnect_attempts = 0  # Сбрасываем счетчик при успехе
                    self.last_connection_time = time.time()  # Запоминаем время успешного подключения
                else:
                    self.logger.warning(f"⚠️ Переподключение #{self.reconnect_attempts} не удалось, пробуем еще раз...")
                    # Небольшая задержка перед следующей попыткой при неудаче
                    await asyncio.sleep(1)
            except AuthenticationPolicyViolation as e:
                # Специальная обработка - токен был обновлен, продолжаем попытки подключения
                self.logger.info(f"🔄 Токен обновлен, повторяем попытку подключения: {e}")
                # Не увеличиваем счетчик попыток для этого случая
                await asyncio.sleep(0.5)  # Короткая задержка
            except Exception as e:
                self.logger.error(f"❌ Ошибка при переподключении #{self.reconnect_attempts}: {e}")
                # Небольшая задержка перед следующей попыткой при ошибке
                await asyncio.sleep(2)

        except Exception as e:
            self.logger.error(f"❌ Ошибка при переподключении: {e}")
            await asyncio.sleep(5)

    async def start(self):
        """Запускает отслеживание"""
        try:
            self.logger.info("🚀 Запуск Eboshers Tracker...")
            self.logger.info("📊 Запуск системы отслеживания скоплений ебошеров")
            self.running = True

            # Пытаемся подключиться (даже если первое подключение не удалось)
            connected = await self.connect()

            # Запускаем задачи параллельно
            timer_task = asyncio.create_task(self.connection_timer_task())
            message_timeout_task = asyncio.create_task(self.message_timeout_task())
            listen_task = asyncio.create_task(self.listen_for_messages())

            # Ждем завершения любой из задач
            done, pending = await asyncio.wait(
                [listen_task, timer_task, message_timeout_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Отменяем оставшиеся задачи
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            self.logger.info("🛑 Получен сигнал прерывания (Ctrl+C)")
            self.running = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка в работе трекера: {e}")
            import traceback
            self.logger.error(f"📋 Traceback: {traceback.format_exc()}")
        finally:
            self.logger.info("🛑 Останавливаем трекер...")
            await self.stop()

    async def stop(self):
        """Останавливает соединение"""
        self.running = False
        if self.websocket:
            try:
                await self.websocket.close()
                self.logger.info("🔌 WebSocket соединение закрыто")
            except Exception as e:
                self.logger.error(f"❌ Ошибка при закрытии соединения: {e}")
            self.websocket = None


async def main():
    """Главная функция для запуска отслеживания ебошеров"""
    try:
        logger.info("🚀 Запуск Eboshers Tracker...")
        logger.info("📡 Подключение к Padre WebSocket для отслеживания скоплений ебошеров")
        logger.info("📊 Система готова к обнаружению скоплений")

        # Создаем и запускаем трекер
        tracker = EboshersTracker()
        await tracker.start()

    except KeyboardInterrupt:
        logger.info("🛑 Программа прервана пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка в main: {e}")
        import traceback
        logger.error(f"📋 Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    # Запускаем основную функцию
    asyncio.run(main())
