#!/usr/bin/env python3
"""
Bundle Analyzer for A/B Testing
Анализирует количество бандлеров для новых токенов и отправляет уведомления в Telegram
"""

import asyncio
import websockets
import json
import base64
import struct
import os
import sys
import logging
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

# Загружаем переменные окружения из .env файла
load_dotenv()

# Добавляем путь к pump_bot для импорта функций
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bundle_analyzer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения mapping токенов к market_id
TOKEN_TO_MARKET_CACHE = {}

# Хранилище для pending запросов market_id
PENDING_MARKET_ID_REQUESTS = {}

# В начале файла, где другие глобальные переменные
# Хранилище для отправленных уведомлений {token_address: {'activity': timestamp, 'pump': timestamp}}
SENT_NOTIFICATIONS = {}

# Список бэкендов Padre для ротации
PADRE_BACKENDS = [
    "wss://backend1.padre.gg/_multiplex",
    "wss://backend2.padre.gg/_multiplex",
    "wss://backend3.padre.gg/_multiplex",
    "wss://backend.padre.gg/_multiplex"
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
        # Проверяем cache
        if token_address in TOKEN_TO_MARKET_CACHE:
            return True
        
        # Проверяем, не отправлен ли уже запрос
        if token_address in PENDING_MARKET_ID_REQUESTS:
            logger.debug(f"📋 Запрос market_id для {token_address[:8]}... уже отправлен")
            return False
        
        logger.info(f"🔍 Запрашиваем market_id для токена {token_address[:8]}... через WebSocket")
        
        # Создаем уникальный ID для запроса
        import uuid
        request_id = str(uuid.uuid4())
        
        # Формируем запрос markets-per-token как в браузере
        markets_request_path = "/prices/prices/markets-per-token"
        markets_payload = {
            'tokens': [{'chain': 'SOLANA', 'tokenAddress': token_address}]
        }
        
        # Создаём MessagePack структуру [8, 45, path, request_id, payload]
        message_data = [8, 45, markets_request_path, request_id, markets_payload]
        message_bytes = msgpack.packb(message_data)
        
        logger.info(f"📡 Отправляем запрос markets-per-token для {token_address[:8]}...")
        logger.info(f"📦 MessagePack: [8, 45, path, uuid, payload] -> {len(message_bytes)} байт")
        
        # Отправляем запрос
        await websocket.send(message_bytes)
        
        # Добавляем в pending запросы
        PENDING_MARKET_ID_REQUESTS[token_address] = {
            'request_id': request_id,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки запроса market_id для {token_address[:8]}...: {e}")
        return False

def process_markets_per_token_response(payload: dict):
    """Обрабатывает ответ markets-per-token и обновляет cache"""
    try:
        if 'markets' in payload and 'SOLANA' in payload['markets']:
            solana_markets = payload['markets']['SOLANA']
            
            for token_address, markets_list in solana_markets.items():
                if markets_list and isinstance(markets_list, list) and len(markets_list) > 0:
                    # Берем первый market (обычно самый ликвидный)
                    market_info = markets_list[0]
                    market_id = market_info.get('marketId')
                    
                    if market_id:
                        # Убираем префикс "solana-" если есть
                        if market_id.startswith('solana-'):
                            market_id = market_id[7:]
                        
                            # Сохраняем в cache
                            TOKEN_TO_MARKET_CACHE[token_address] = market_id
                            logger.info(f"✅ Сохранен market_id для {token_address[:8]}...: {market_id[:8]}...")
                            logger.info(f"📋 ✅ Контракт С market_id (markets-per-token): {token_address} -> {market_id}")
                        
                        # Удаляем из pending запросов
                        if token_address in PENDING_MARKET_ID_REQUESTS:
                            del PENDING_MARKET_ID_REQUESTS[token_address]
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки markets-per-token ответа: {e}")

async def get_market_id_for_token_cached(token_address: str) -> Optional[str]:
    """Получает market_id из cache или возвращает None"""
    return TOKEN_TO_MARKET_CACHE.get(token_address)

async def get_token_metadata(token_address: str) -> dict:
    """Получает метаданные токена через API DexScreener или Jupiter"""
    try:
        logger.info(f"🔍 Запрашиваем метаданные для токена {token_address[:8]}...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        # Пробуем DexScreener API
        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(dex_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'pairs' in data and data['pairs']:
                        # Берем первую пару (обычно самая ликвидная)
                        pair = data['pairs'][0]
                        base_token = pair.get('baseToken', {})
                        
                        symbol = base_token.get('symbol', 'UNK')
                        name = base_token.get('name', symbol)
                        
                        if symbol != 'UNK':
                            logger.info(f"✅ Найдены метаданные через DexScreener: {name} ({symbol})")
                            return {
                                'symbol': symbol,
                                'name': name,
                                'market_cap': float(pair.get('fdv', 0)),
                                'dex_source': pair.get('dexId', 'Unknown'),
                                'source': 'DexScreener'
                            }
                
                # Пробуем Jupiter API как fallback
                logger.info(f"🔄 Пробуем Jupiter API для {token_address[:8]}...")
                jupiter_url = f"https://price.jup.ag/v6/price?ids={token_address}"
                
                async with session.get(jupiter_url, headers=headers, timeout=10) as jup_response:
                    if jup_response.status == 200:
                        jup_data = await jup_response.json()
                        
                        if 'data' in jup_data and token_address in jup_data['data']:
                            token_data = jup_data['data'][token_address]
                            return {
                                'symbol': 'UNK',  # Jupiter price API не содержит symbol
                                'name': 'Unknown Token',
                                'market_cap': 0,
                                'dex_source': 'Jupiter',
                                'source': 'Jupiter',
                                'price': float(token_data.get('price', 0))
                            }
                
        logger.warning(f"⚠️ Не удалось найти метаданные для токена {token_address[:8]}...")
        return {
            'symbol': 'UNK',
            'name': 'Unknown Token',
            'market_cap': 0,
            'dex_source': 'Unknown',
            'source': 'None'
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения метаданных для {token_address[:8]}...: {e}")
        return {
            'symbol': 'UNK',
            'name': 'Unknown Token',
            'market_cap': 0,
            'dex_source': 'Unknown',
            'source': 'Error'
        }

async def get_market_id_for_token(token_address: str) -> Optional[str]:
    """Получает market_id для токена через cache или альтернативные API"""
    try:
        # Проверяем cache
        if token_address in TOKEN_TO_MARKET_CACHE:
            cached_market_id = TOKEN_TO_MARKET_CACHE[token_address]
            logger.debug(f"📋 Найден market_id в cache для {token_address[:8]}...: {cached_market_id[:8]}...")
            return cached_market_id
        
        # Альтернативный метод: используем DexScreener API как fallback
        logger.info(f"🔄 Пробуем DexScreener API для {token_address[:8]}...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(dex_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'pairs' in data and data['pairs']:
                        # Берем первую пару (обычно самая ликвидная)
                        pair = data['pairs'][0]
                        market_id = pair.get('pairAddress')
                        
                        if market_id:
                            # Сохраняем в cache
                            TOKEN_TO_MARKET_CACHE[token_address] = market_id
                            logger.info(f"✅ Найден market_id через DexScreener для {token_address[:8]}...: {market_id[:8]}...")
                            return market_id
                
                        logger.warning(f"❌ Не удалось найти market_id для токена {token_address[:8]}...")
                logger.info(f"📋 Полный адрес контракта без market_id (DexScreener): {token_address}")
                return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения market_id для {token_address[:8]}...: {e}")
        return None

async def get_market_address_via_smart_query(websocket, token_address: str) -> Optional[str]:
    """Получает marketAddress для токена через get-market-smart-with-warm endpoint"""
    try:
        # Проверяем cache
        if token_address in TOKEN_TO_MARKET_CACHE:
            cached_market_id = TOKEN_TO_MARKET_CACHE[token_address]
            logger.debug(f"📋 Найден marketAddress в cache для {token_address[:8]}...: {cached_market_id[:8]}...")
            return cached_market_id
        
        logger.info(f"🔍 Запрашиваем marketAddress для токена {token_address[:8]}... через get-market-smart-with-warm")
        
        # Создаем уникальный ID для запроса
        import uuid
        request_id = str(uuid.uuid4())
        
        # Формируем правильный путь как в браузере
        smart_query_path = f"/prices/query/solana-{token_address}/get-market-smart-with-warm"
        
        # Упаковываем сообщение в MessagePack формат [8, 19, path, id]
        smart_query_request = [8, 19, smart_query_path, request_id]
        smart_query_request_bytes = msgpack.packb(smart_query_request)
        
        logger.debug(f"📤 Отправляем get-market-smart-with-warm запрос для {token_address[:8]}...")
        await websocket.send(smart_query_request_bytes)
        
        # Ждем ответ с marketAddress
        for _ in range(10):  # Максимум 10 попыток
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                if isinstance(response, bytes):
                    try:
                        decoded_response = msgpack.unpackb(response, raw=False)
                        logger.debug(f"📨 Получили ответ: {str(decoded_response)[:300]}...")
                        
                        # Проверяем формат ответа [9, 19, 200, payload]
                        if (isinstance(decoded_response, list) and len(decoded_response) >= 4 and 
                            decoded_response[0] == 9 and decoded_response[1] == 19 and 
                            decoded_response[2] == 200):
                            
                            response_payload = decoded_response[3]
                            if isinstance(response_payload, dict) and 'marketAddress' in response_payload:
                                market_address = response_payload['marketAddress']
                                logger.info(f"✅ Найден marketAddress для {token_address[:8]}...: {market_address}")
                                
                                # Сохраняем в cache
                                TOKEN_TO_MARKET_CACHE[token_address] = market_address
                                logger.info(f"📋 ✅ Контракт С marketAddress: {token_address} -> {market_address}")
                                return market_address
                            else:
                                logger.warning(f"⚠️ marketAddress не найден в ответе для {token_address[:8]}...")
                                logger.debug(f"📊 Полная структура ответа: {str(response_payload)[:500]}...")
                        elif (isinstance(decoded_response, list) and len(decoded_response) >= 4 and 
                              decoded_response[0] == 9 and decoded_response[1] == 19 and 
                              decoded_response[2] != 200):
                            # Ошибка в запросе
                            logger.warning(f"⚠️ Ошибка в get-market-smart-with-warm запросе: код {decoded_response[2]}")
                        else:
                            logger.debug(f"📡 Получено сообщение другого типа: {decoded_response[:3] if isinstance(decoded_response, list) else type(decoded_response)}")
                            
                    except Exception as decode_error:
                        logger.debug(f"🔍 Ошибка декодирования ответа: {decode_error}")
                        continue
                else:
                    logger.debug(f"📡 Получено не-binary сообщение: {type(response)}")
                    
            except asyncio.TimeoutError:
                logger.debug(f"⏰ Таймаут ожидания ответа для {token_address[:8]}...")
                break
            except Exception as e:
                logger.debug(f"🔍 Ошибка получения ответа: {e}")
                break
        
        logger.warning(f"⚠️ Не удалось получить marketAddress для {token_address[:8]}... через get-market-smart-with-warm")
        logger.info(f"📋 Полный адрес контракта без marketAddress: {token_address}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения marketAddress через get-market-smart-with-warm для {token_address[:8]}...: {e}")
        logger.info(f"📋 Полный адрес контракта с ошибкой: {token_address}")
        return None

# Конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TARGET_CHAT_ID = -1002680160752  # ID группы из https://t.me/c/2680160752/13134
TARGET_THREAD_ID = 13134  # ID темы
MIN_BUNDLER_PERCENTAGE = float(os.getenv("MIN_BUNDLER_PERCENTAGE", "10"))  # Минимальный процент бандлеров

# WebSocket URL для trade.padre.gg
PADRE_WS_URL = get_next_padre_backend()

# Куки для подключения к padre
PADRE_COOKIES = {
    'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel': '%7B%22distinct_id%22%3A%20%22tg_453500861%22%2C%22%24device_id%22%3A%20%22198553678cdad5-07cb4ed93902208-4c657b58-1fa400-198553678ce2283%22%2C%22%24user_id%22%3A%20%22tg_453500861%22%2C%22%24initial_referrer%22%3A%20%22%24direct%22%2C%22%24initial_referring_domain%22%3A%20%22%24direct%22%7D'
}

# Хранилище токенов для анализа
pending_tokens: Dict[str, dict] = {}  # {contract_address: token_data}
bundler_results: Dict[str, dict] = {}  # {contract_address: bundler_data}
sended_tokens: Dict[str, bool] = {}  # {contract_address: bool}

def decode_padre_message(message_bytes: bytes) -> Optional[dict]:
    """
    Декодирует сообщение от trade.padre.gg WebSocket
    Пытается различные форматы: MessagePack, JSON, base64
    """
    try:
        logger.debug(f"🔍 Декодируем сообщение: {len(message_bytes)} байт")
        
        # Вариант 1: Прямой MessagePack
        try:
            data = msgpack.unpackb(message_bytes, raw=False)
            logger.debug(f"✅ Успешно декодировано как MessagePack: {type(data)}")
            
            # Если это fast-stats update, логируем подробнее
            if isinstance(data, dict) and any(key in str(data).lower() for key in ['bundler', 'holder', 'volume', 'stats']):
                logger.info(f"🚀 Fast-stats данные обнаружены: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            
            return data if isinstance(data, dict) else {'raw_data': data, 'type': 'msgpack'}
        except Exception as e:
            logger.debug(f"❌ Не MessagePack: {e}")
        
        # Вариант 2: JSON
        try:
            text = message_bytes.decode('utf-8', errors='ignore')
            if text.strip().startswith('{'):
                data = json.loads(text)
                logger.debug(f"✅ Успешно декодировано как JSON")
                return data
        except Exception as e:
            logger.debug(f"❌ Не JSON: {e}")
        
        # Вариант 3: Base64 encoded data
        try:
            if len(message_bytes) % 4 == 0:  # base64 должен быть кратен 4
                decoded_b64 = base64.b64decode(message_bytes)
                
                # Пытаемся декодировать результат как MessagePack
                try:
                    data = msgpack.unpackb(decoded_b64, raw=False)
                    logger.debug(f"✅ Декодировано как base64->MessagePack")
                    return data if isinstance(data, dict) else {'raw_data': data, 'type': 'base64_msgpack'}
                except:
                    pass
                
                # Пытаемся как JSON
                try:
                    text = decoded_b64.decode('utf-8', errors='ignore')
                    if text.strip().startswith('{'):
                        data = json.loads(text)
                        logger.debug(f"✅ Декодировано как base64->JSON")
                        return data
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"❌ Ошибка base64: {e}")
        
        # Вариант 4: Множественные части (может быть multiplex format)
        try:
            # Если сообщение начинается с определенных байтов, это может быть мультиплексированный формат
            if len(message_bytes) > 10:
                # Попробуем найти JSON части в сообщении
                text = message_bytes.decode('utf-8', errors='ignore')
                
                # Ищем JSON блоки
                import re
                json_matches = re.findall(r'\{[^{}]*\}', text)
                for match in json_matches:
                    try:
                        data = json.loads(match)
                        logger.debug(f"✅ Найден JSON в мультиплексе")
                        return data
                    except:
                        continue
                        
                # Ищем признаки fast-stats
                if any(keyword in text.lower() for keyword in ['bundler', 'holder', 'volume', 'stats', 'trades']):
                    logger.info(f"📊 Обнаружен потенциальный fast-stats контент: {text[:100]}...")
                    return {'type': 'fast_stats_text', 'content': text}
                    
        except Exception as e:
            logger.debug(f"❌ Ошибка мультиплекс анализа: {e}")
        
        # Вариант 5: Простое ping/pong сообщение
        try:
            text = message_bytes.decode('utf-8', errors='ignore').strip()
            if text.lower() in ['ping', 'pong'] or len(text) < 10:
                return {'type': 'ping', 'message': text}
        except:
            pass
        
        # Если ничего не сработало, возвращаем raw данные для анализа
        logger.debug(f"🤔 Неизвестный формат сообщения, возвращаем raw данные")
        return {
            'type': 'unknown',
            'raw_bytes': message_bytes.hex() if len(message_bytes) < 200 else f"{message_bytes[:100].hex()}...",
            'length': len(message_bytes),
            'ascii_preview': message_bytes.decode('utf-8', errors='ignore')[:100]
        }
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка декодирования: {e}")
        return None

class TokenMetrics:
    """Класс для отслеживания метрик токена"""
    def __init__(self, token_address: str, creation_time: int):
        self.token_address = token_address
        self.creation_time = creation_time
        self.metrics_history = []
        self.max_dev_percent = 0
        self.max_bundlers_after_dev_exit = 0
        self.max_bundlers_before_dev_exit = 0  # Максимальный процент бандлеров до выхода дева
        self.max_holders = 0  # Максимальное количество холдеров
        self.dev_exit_time = None
        self.last_notification_time = 0
        self.last_notification_type = None  # Тип последнего уведомления
        
    def can_send_notification(self, notification_type: str) -> bool:
        """
        Проверяет, можно ли отправить уведомление данного типа
        Args:
            notification_type: Тип уведомления ('active', 'pump', etc)
        Returns:
            bool: True если можно отправить уведомление
        """
        current_time = time.time()
        
        # Минимальный интервал между уведомлениями
        MIN_NOTIFICATION_INTERVAL = 900  # 15 минут
        
        # Проверяем время последнего уведомления
        if current_time - self.last_notification_time < MIN_NOTIFICATION_INTERVAL:
            return False
        
        # Если тип уведомления изменился, разрешаем отправку
        if self.last_notification_type != notification_type:
            return True
            
        # Обновляем время и тип последнего уведомления
        self.last_notification_time = current_time
        self.last_notification_type = notification_type
        return True
    
    def add_metrics(self, metrics: dict):
        """Добавляет новые метрики и рассчитывает динамику"""
        # Используем время из метрик если есть, иначе текущее
        if 'timestamp' not in metrics:
            metrics['timestamp'] = int(time.time())

        # Получаем процент дева и бандлеров
        dev_holding = metrics.get('devHoldingPcnt')
        dev_percent = float(dev_holding) if dev_holding is not None else 0
        
        bundles_percent = metrics.get('bundlesHoldingPcnt')
        bundles_percent = float(bundles_percent.get('current', 0) if isinstance(bundles_percent, dict) else (bundles_percent if bundles_percent is not None else 0))

        # Обновляем максимальный процент дева
        if dev_percent > self.max_dev_percent:
            self.max_dev_percent = dev_percent
            logger.info(f"📈 Новый максимум доли дева: {dev_percent:.1f}%")

        # Проверяем выход дева
        if self.dev_exit_time is None and dev_percent == 0 and self.metrics_history:
            last_dev_percent = float(self.metrics_history[-1].get('devHoldingPcnt', 0) or 0)
            if last_dev_percent > 0:
                self.dev_exit_time = metrics['timestamp']
                logger.info(f"🚪 Дев полностью вышел из токена в {datetime.fromtimestamp(self.dev_exit_time)}")

        # Обновляем максимальный процент бандлеров в зависимости от статуса дева
        if self.dev_exit_time is None:
            # До выхода дева
            if bundles_percent > self.max_bundlers_before_dev_exit:
                self.max_bundlers_before_dev_exit = bundles_percent
                logger.info(f"📈 Новый максимум доли бандлеров до выхода дева: {bundles_percent:.1f}%")
        else:
            # После выхода дева
            if bundles_percent > self.max_bundlers_after_dev_exit:
                self.max_bundlers_after_dev_exit = bundles_percent
                logger.info(f"📈 Новый максимум доли бандлеров после выхода дева: {bundles_percent:.1f}%")
        
        # Обновляем максимальное количество холдеров
        total_holders = int(metrics.get('total_holders', 0) or 0)
        if total_holders > self.max_holders:
            self.max_holders = total_holders
            logger.info(f"📈 Новый максимум холдеров: {total_holders}")
        
        # Добавляем новые метрики
        self.metrics_history.append(metrics.copy())  # Используем copy() чтобы избежать ссылок
        
        # Оставляем только последние 5 минут метрик
        current_time = int(time.time())
        self.metrics_history = [m for m in self.metrics_history 
                              if current_time - m['timestamp'] <= 300]
    
    def get_growth_rates(self) -> dict:
        """Рассчитывает скорость роста различных метрик"""
        if len(self.metrics_history) < 2:
            return {
                'holders_growth': 0,
                'bundlers_growth': 0,
                'price_growth': 0
            }
        
        # Берем самые старые и новые метрики
        old = self.metrics_history[0]
        new = self.metrics_history[-1]
        time_diff_sec = new['timestamp'] - old['timestamp']  # разница в секундах

        logger.info(f"📊 time_diff_sec: {time_diff_sec}")
        logger.info(f"📊 old: {old}")
        logger.info(f"📊 new: {new}")
        
        if time_diff_sec == 0:
            return {
                'holders_growth': 0,
                'bundlers_growth': 0,
                'price_growth': 0
            }

        # Получаем значения, убеждаясь что они числа
        old_holders = int(old.get('total_holders', 0) or 0)
        new_holders = int(new.get('total_holders', 0) or 0)
        old_bundlers = int(old.get('totalBundlesCount', 0) or 0)
        new_bundlers = int(new.get('totalBundlesCount', 0) or 0)
        old_price = float(old.get('basePriceInUsdUi', 0) or 0)
        new_price = float(new.get('basePriceInUsdUi', 0) or 0)
        
        # Рассчитываем абсолютный прирост
        holders_diff = new_holders - old_holders
        bundlers_diff = new_bundlers - old_bundlers
        price_diff = new_price - old_price

        # Если прирост есть, считаем его как моментальный рост
        holders_growth = holders_diff * 60 if holders_diff > 0 else 0  # конвертируем в /мин для совместимости
        bundlers_growth = bundlers_diff * 60 if bundlers_diff > 0 else 0
        price_growth = price_diff * 60 if price_diff > 0 else 0
        
        logger.info(f"📊 Расчет роста для {self.token_address[:8]}:")
        logger.info(f"⏰ Интервал: {time_diff_sec} сек")
        logger.info(f"👥 Холдеры: {old_holders} → {new_holders} (Δ{holders_diff}) = {holders_growth:.2f}/мин")
        logger.info(f"📦 Бандлеры: {old_bundlers} → {new_bundlers} (Δ{bundlers_diff}) = {bundlers_growth:.2f}/мин")
        logger.info(f"💰 Цена: ${old_price:.8f} → ${new_price:.8f} (Δ${price_diff:.8f}) = ${price_growth:.8f}/мин")
        
        return {
            'holders_growth': holders_growth,
            'bundlers_growth': bundlers_growth,
            'price_growth': price_growth
        }
    
    def check_snipers_bundlers_correlation(self) -> bool:
        """
        Проверяет, не являются ли снайперы бандлерами, анализируя корреляцию их изменений
        Returns:
            bool: True если корреляция в норме (снайперы не являются бандлерами),
                 False если есть подозрение что снайперы это бандлеры
        """
        if not hasattr(self, 'metrics_history'):
            return True

        # Нужно минимум 3 точки данных для анализа
        if len(self.metrics_history) < 3:
            return True

        bundlers_changes = []
        snipers_changes = []
        
        # Анализируем изменения процентов
        for i in range(1, len(self.metrics_history)):
            prev = self.metrics_history[i-1]
            curr = self.metrics_history[i]
            
            # Получаем процент бандлеров
            prev_bundles = prev.get('bundlesHoldingPcnt', 0)
            curr_bundles = curr.get('bundlesHoldingPcnt', 0)
            
            # Обрабатываем случай когда значение может быть как словарем, так и числом
            if isinstance(prev_bundles, dict):
                prev_bundlers_pct = float(prev_bundles.get('current', 0) if prev_bundles is not None else 0)
            else:
                prev_bundlers_pct = float(prev_bundles if prev_bundles is not None else 0)
                
            if isinstance(curr_bundles, dict):
                curr_bundlers_pct = float(curr_bundles.get('current', 0) if curr_bundles is not None else 0)
            else:
                curr_bundlers_pct = float(curr_bundles if curr_bundles is not None else 0)
            
            # Получаем процент снайперов
            prev_snipers = prev.get('snipersHoldingPcnt', 0)
            curr_snipers = curr.get('snipersHoldingPcnt', 0)
            
            # Аналогичная обработка для снайперов
            if isinstance(prev_snipers, dict):
                prev_snipers_pct = float(prev_snipers.get('current', 0) if prev_snipers is not None else 0)
            else:
                prev_snipers_pct = float(prev_snipers if prev_snipers is not None else 0)
                
            if isinstance(curr_snipers, dict):
                curr_snipers_pct = float(curr_snipers.get('current', 0) if curr_snipers is not None else 0)
            else:
                curr_snipers_pct = float(curr_snipers if curr_snipers is not None else 0)
            
            # Если снайперы вышли, а бандлеры остались - это хороший признак
            if curr_snipers_pct <= 3.5 and curr_bundlers_pct > 0:
                logger.info("✅ Снайперы вышли, но бандлеры остались - бандлеры не являются снайперами")
                return True
            
            bundlers_change = curr_bundlers_pct - prev_bundlers_pct
            snipers_change = curr_snipers_pct - prev_snipers_pct
            
            # Если есть значительное изменение
            if abs(bundlers_change) > 0.1:  # Изменение более 0.1%
                bundlers_changes.append(bundlers_change)
                snipers_changes.append(snipers_change)
                
                logger.info(f"📊 bundlers_change: {bundlers_change}")
                logger.info(f"📊 snipers_change: {snipers_change}")
                
                # Логируем подозрительные изменения
                if (bundlers_change * snipers_change > 0 and 
                    abs(bundlers_change - snipers_change) / max(abs(bundlers_change), abs(snipers_change)) < 0.3):
                    logger.info(f"🚨 Подозрительная корреляция снайперов и бандлеров:")
                    logger.info(f"📊 Изменение бандлеров: {bundlers_change:.2f}%")
                    logger.info(f"🎯 Изменение снайперов: {snipers_change:.2f}%")

        # Если недостаточно значительных изменений
        if len(bundlers_changes) < 2:
            return True

        # Проверяем корреляцию
        suspicious = 0
        for i in range(len(bundlers_changes)):
            # Если изменения происходят в одном направлении и близки по масштабу
            if (bundlers_changes[i] * snipers_changes[i] > 0 and 
                abs(bundlers_changes[i] - snipers_changes[i]) / max(abs(bundlers_changes[i]), abs(snipers_changes[i])) < 0.3):
                suspicious += 1

        # Если более 50% изменений коррелируют, считаем это подозрительным
        is_suspicious = suspicious >= len(bundlers_changes) * 0.5
        if is_suspicious:
            logger.warning(f"⚠️ Обнаружена сильная корреляция между снайперами и бандлерами!")
            logger.warning(f"📊 {suspicious} из {len(bundlers_changes)} изменений показывают корреляцию")
        
        return not is_suspicious

    def check_snipers_insiders_correlation(self) -> bool:
        """
        Проверяет корреляцию между снайперами и инсайдерами (если инсайдеры = снайперы — плохо)
        """
        if not hasattr(self, 'metrics_history'):
            return True
        if len(self.metrics_history) < 3:
            return True
        snipers_changes = []
        insiders_changes = []
        for i in range(1, len(self.metrics_history)):
            prev = self.metrics_history[i-1]
            curr = self.metrics_history[i]
            prev_snipers = float(prev.get('snipersHoldingPcnt', 0) or 0)
            curr_snipers = float(curr.get('snipersHoldingPcnt', 0) or 0)
            prev_insiders = float(prev.get('insidersHoldingPcnt', 0) or 0)
            curr_insiders = float(curr.get('insidersHoldingPcnt', 0) or 0)
            snipers_change = curr_snipers - prev_snipers
            insiders_change = curr_insiders - prev_insiders
            if abs(snipers_change) > 0.1:
                snipers_changes.append(snipers_change)
                insiders_changes.append(insiders_change)
        if len(snipers_changes) < 2:
            return True
        # # Если снайперы вышли, а инсайдеры остались - это хороший признак
        # if curr_snipers <= 3.5 and curr_insiders > 0:
        #     logger.info("✅ Снайперы вышли, но инсайдеры остались - инсайдеры не являются снайперами")
        #     return True
        suspicious = 0
        for i in range(len(snipers_changes)):
            if (snipers_changes[i] * insiders_changes[i] > 0 and
                abs(snipers_changes[i] - insiders_changes[i]) / max(abs(snipers_changes[i]), abs(insiders_changes[i])) < 0.3):
                suspicious += 1
        is_suspicious = suspicious >= len(snipers_changes) * 0.5
        if is_suspicious:
            logger.warning("⚠️ Обнаружена сильная корреляция между снайперами и инсайдерами!")
        return not is_suspicious

    def check_bundlers_snipers_exit_correlation(self) -> bool:
        """
        Проверяет, не выходят ли бандлеры и снайперы равномерно (это плохо)
        """
        if not hasattr(self, 'metrics_history'):
            return True
        if len(self.metrics_history) < 3:
            return True
        bundlers_changes = []
        snipers_changes = []
        for i in range(1, len(self.metrics_history)):
            prev = self.metrics_history[i-1]
            curr = self.metrics_history[i]
            prev_bundlers = prev.get('bundlesHoldingPcnt', 0)
            curr_bundlers = curr.get('bundlesHoldingPcnt', 0)
            prev_snipers = float(prev.get('snipersHoldingPcnt', 0) or 0)
            curr_snipers = float(curr.get('snipersHoldingPcnt', 0) or 0)
            if isinstance(prev_bundlers, dict):
                prev_bundlers = float(prev_bundlers.get('current', 0) if prev_bundlers is not None else 0)
            else:
                prev_bundlers = float(prev_bundlers if prev_bundlers is not None else 0)
            if isinstance(curr_bundlers, dict):
                curr_bundlers = float(curr_bundlers.get('current', 0) if curr_bundlers is not None else 0)
            else:
                curr_bundlers = float(curr_bundlers if curr_bundlers is not None else 0)
            bundlers_change = curr_bundlers - prev_bundlers
            snipers_change = curr_snipers - prev_snipers
            # Интересует только одновременное падение
            if bundlers_change < 0 and snipers_change < 0:
                bundlers_changes.append(bundlers_change)
                snipers_changes.append(snipers_change)
        if len(bundlers_changes) < 2:
            return True
        # Если снайперы вышли, а бандлеры остались - это хороший признак
        if curr_snipers <= 3.5 and curr_bundlers > 0:
            logger.info("✅ Снайперы вышли, но бандлеры остались - бандлеры не являются снайперами")
            return True
        suspicious = 0
        for i in range(len(bundlers_changes)):
            if abs(bundlers_changes[i] - snipers_changes[i]) / max(abs(bundlers_changes[i]), abs(snipers_changes[i])) < 0.3:
                suspicious += 1
        is_suspicious = suspicious >= len(bundlers_changes) * 0.5
        if is_suspicious:
            logger.warning("⚠️ Обнаружена равномерная корреляция выхода бандлеров и снайперов!")
        return not is_suspicious

    def check_rapid_exit(self, metric_name: str, ratio: float = 3.0, max_seconds: int = 120) -> bool:
        """
        Проверяет стремительный выход (снайперов или инсайдеров)
        Args:
            metric_name: 'snipersHoldingPcnt' или 'insidersHoldingPcnt'
            ratio: во сколько раз должен уменьшиться процент
            max_seconds: за сколько секунд должен произойти выход
        Returns:
            bool: True если был стремительный выход
        """
        if not self.metrics_history or len(self.metrics_history) < 2:
            return False
        first_value = None
        first_time = None
        for m in self.metrics_history:
            value = float(m.get(metric_name, 0) or 0)
            if value > 0:
                first_value = value
                first_time = m['timestamp']
                break
        if not first_value:
            return False
        current_value = float(self.metrics_history[-1].get(metric_name, 0) or 0)
        current_time = self.metrics_history[-1]['timestamp']
        time_diff = current_time - first_time
        if time_diff <= max_seconds and current_value <= first_value / ratio:
            logger.info(f"📉 Стремительный выход обнаружен для {metric_name}: {first_value:.1f}% → {current_value:.1f}% за {time_diff} сек")
            return True
        return False

class PadreWebSocketClient:
    """Клиент для подключения к trade.padre.gg WebSocket"""
    
    def __init__(self, token_address: str, connection_id: str = "default"):
        """Инициализация клиента"""
        self.token_address = token_address  # Адрес токена для этого соединения
        self.connection_id = f"{connection_id}_{token_address[:8]}"  # Уникальный ID соединения с адресом токена
        self.websocket = None
        self.running = False
        self.start_time = None  # Время начала соединения
        self.max_duration = 10 * 60  # 10 минут в секундах
        self.token_data_cache = {}  # Кеш данных для этого токена
        self.current_update_data = None  # Текущие данные обновления
        self.current_pump_gaze = None  # Текущие данные pump_fun_gaze
        self.last_used_api_domain = 0
        self.axiom_api_domains = [
            "https://api.axiom.trade",
            "https://api2.axiom.trade",
            "https://api3.axiom.trade",
            "https://api6.axiom.trade",
            "https://api7.axiom.trade",
            "https://api8.axiom.trade",
            "https://api9.axiom.trade",
            "https://api10.axiom.trade",
        ]
        self.token_metrics = TokenMetrics(token_address, int(time.time()))
        self.last_notification_type = None  # Тип последнего уведомления
        self.last_notification_time = 0  # Время последнего уведомления
        self.max_dev_percent = 0  # Максимальный процент дева за всю историю
        self.dev_exit_time = None  # Время когда дев полностью вышел из токена
        self.max_bundlers_after_dev_exit = 0  # Максимальный процент бандлеров после выхода дева
        self.padre_backend = get_next_padre_backend()  # Выбираем бэкенд при создании клиента
        
    async def connect(self):
        """Подключение к WebSocket"""
        try:
            logger.info(f"🔗 Padre backend: {self.padre_backend.split('/')[-2]}")
            # Заголовки как в браузере
            headers = {
                'Cookie': 'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel=' + PADRE_COOKIES['mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel'],
                'Origin': 'https://trade.padre.gg',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
            }
            
            logger.info(f"🔗 Подключаемся к {self.padre_backend} для токена {self.token_address[:8]}...")
            
            # Добавляем обработку ошибок SSL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Пробуем подключиться несколько раз
            for attempt in range(3):
                try:
                    self.websocket = await websockets.connect(
                        self.padre_backend,
                        extra_headers=headers,
                        ping_interval=None,
                        ping_timeout=None,
                        ssl=ssl_context
                    )
                    logger.info(f"✅ Успешно подключились к {self.padre_backend} для токена {self.token_address[:8]}")
                    
                    # Отправляем аутентификационное сообщение
                    await self.send_auth_message()
                    
                    return True
                    
                except AuthenticationPolicyViolation as e:
                    logger.critical(f"🚫 {e}")
                    # Завершаем работу скрипта при ошибке аутентификации
                    sys.exit(1)
                except Exception as e:
                    if attempt < 2:  # На последней попытке не логируем
                        logger.warning(f"⚠️ Попытка {attempt + 1}/3 подключения не удалась: {e}")
                        # Пробуем другой бэкенд при следующей попытке
                        self.padre_backend = get_next_padre_backend()
                        logger.info(f"🔄 Переключаемся на бэкенд {self.padre_backend}")
                        await asyncio.sleep(1)  # Ждем секунду перед следующей попыткой
            
            logger.error(f"❌ Не удалось подключиться после 3 попыток для токена {self.token_address[:8]}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к {self.padre_backend} для токена {self.token_address[:8]}: {e}")
            return False

    async def send_bundler_notification(self, contract_address: str, token_data: dict, bundler_count: int, bundler_percentage: float, simulated: bool = False):
        """Отправляем уведомление о токене с высоким процентом бандлеров"""
        try:
            market_id = await get_market_id_for_token_cached(contract_address)
            if sended_tokens.get(market_id):
                logger.info(f"⚠️ Уведомление для {contract_address[:8]} уже было отправлено")
                return
            
            symbol = token_data.get('symbol', 'UNK')
            name = token_data.get('name', symbol)
            dex_source = token_data.get('dex_source', 'Unknown')
            market_cap = token_data.get('market_cap', 0)
            total_holders = token_data.get('total_holders', 0)
            sol_spent_in_bundles = token_data.get('sol_spent_in_bundles', 0)
            bundler_percentage_ath = token_data.get('bundler_percentage_ath', 0)
            sim_tag = " 🎲 [СИМУЛЯЦИЯ]" if simulated else ""
            
            logger.info(f"📤 Подготовка уведомления для {contract_address[:8]}")
            logger.info(f"📊 Проверка условий: holders={total_holders}, bundlers={bundler_count}, market_id={market_id}")
            
            # Получаем deployer процент (может быть числом или объектом)
            deployer_pcnt = token_data.get('deployerHoldingPcnt')
            if isinstance(deployer_pcnt, dict):
                deployer_pcnt = deployer_pcnt.get('current', 0)
            
            message = (
                f"🚨 <b>X X X XX X иксыыыыы!!!</b>\n\n"
                f"🪙 <b>{name}</b> ({symbol})\n"
                f"📍 <b>Контракт:</b> <code>{contract_address}</code>\n"
                f"📊 <b>Бандлеры:</b> {bundler_count} ({self.safe_format(bundler_percentage, '.1f')}%)\n"
                f"🏆 <b>ATH бандлеры:</b> {self.safe_format(bundler_percentage_ath, '.1f')}%\n"
                f"👤 <b>Холдеры:</b> {total_holders}\n"
                f"💰 <b>SOL на бандлеры:</b> {self.safe_format(sol_spent_in_bundles, ',.2f')}\n"
                f"💰 <b>Market Cap:</b> ${self.safe_format(market_cap, ',.0f')}\n"
                f"🏪 <b>DEX:</b> {dex_source}\n\n"
                
                f"💵 <b>Цена:</b> ${self.safe_format(token_data.get('basePriceInUsdUi'), ',.8f')}\n"
                f"💱 <b>Цена в Quote:</b> {self.safe_format(token_data.get('basePriceInQuoteUi'), ',.8f')}\n"
                f"💧 <b>Ликвидность:</b> ${self.safe_format(token_data.get('liquidityInUsdUi'), ',.2f')}\n\n"
                
                f"📊 <b>АНАЛИЗ ТОКЕНА:</b>\n"
                f"👨‍💼 <b>Dev %:</b> {self.safe_format(token_data.get('devHoldingPcnt'), '.1f')}%\n"
                f"👨‍💼 <b>Deployer %:</b> {self.safe_format(deployer_pcnt, '.1f')}%\n"
                f"👥 <b>Инсайдеры:</b> {self.safe_format(token_data.get('insidersHoldingPcnt'), '.1f')}%\n"
                f"🎯 <b>Снайперы:</b> {token_data.get('totalSnipers') or 0} ({self.safe_format(token_data.get('snipersHoldingPcnt'), '.1f')}%)\n"
                f"🤖 <b>Trading App:</b> {token_data.get('tradingAppTxns') or 0} транзакций\n\n"
                
                f"📦 <b>БАНДЛЫ:</b>\n"
                f"💼 <b>Количество:</b> {token_data.get('totalBundlesCount') or 0}\n"
                f"📈 <b>Текущий %:</b> {self.safe_format((token_data.get('bundlesHoldingPcnt', {}) or {}).get('current'), '.1f')}%\n"
                f"🏆 <b>ATH %:</b> {self.safe_format((token_data.get('bundlesHoldingPcnt', {}) or {}).get('ath'), '.1f')}%\n"
                f"💰 <b>SOL в бандлах:</b> {self.safe_format(token_data.get('totalSolSpentInBundles'), ',.2f')}\n"
                f"🔢 <b>Токенов в бандлах:</b> {self.safe_format(token_data.get('totalTokenBoughtInBundles'), ',.0f')}\n\n"
                
                f"🆕 <b>FRESH WALLETS:</b>\n"
                f"👥 <b>Количество:</b> {(token_data.get('freshWalletBuys', {}) or {}).get('count', 0)}\n"
                f"💰 <b>SOL потрачено:</b> {self.safe_format((token_data.get('freshWalletBuys', {}) or {}).get('sol'), ',.2f')}\n"
                f"💸 <b>Комиссии:</b> {self.safe_format(token_data.get('totalSolFees'), ',.4f')} SOL\n\n"
                
                f"📊 <b>SUPPLY:</b>\n"
                f"🔢 <b>Total Supply:</b> {self.safe_format(token_data.get('totalSupply'), ',')}"
            )
            
            # Создаем кнопки для быстрых действий
            keyboard = [
                [
                    {"text": "🚀 Axiom", "url": f"https://axiom.trade/t/{contract_address}"},
                    {"text": "🚀 DexScreener", "url": f"https://dexscreener.com/solana/{contract_address}"}
                ],
            ]
            
            success = await self.send_telegram_message(message, keyboard)
            
            if success:
                logger.info(f"✅ Отправлено уведомление о токене {symbol} с {bundler_percentage:.1f}% бандлеров")
                if market_id:
                    sended_tokens[market_id] = True
                logger.warning(f"⚠️ Не удалось отправить уведомление о токене {symbol}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления о бандлерах: {e}")
            logger.exception(e)
    
    async def send_auth_message(self):
        """Отправляем аутентификационное сообщение"""
        try:
            # Декодируем первое сообщение от клиента для аутентификации
            auth_message_b64 = "kwHaAyZleUpoYkdjaU9pSlNVekkxTmlJc0ltdHBaQ0k2SWprMU1XUmtaVGt6TW1WaVlXTmtPRGhoWm1Jd01ETTNZbVpsWkRobU5qSmlNRGRtTURnMk5tSWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKdVlXMWxJam9pZDI5eWEyVnlNVEF3TUhnaUxDSm9ZWFYwYUNJNmRISjFaU3dpYVhOeklqb2lhSFIwY0hNNkx5OXpaV04xY21WMGIydGxiaTVuYjI5bmJHVXVZMjl0TDNCaFpISmxMVFF4TnpBeU1DSXNJbUYxWkNJNkluQmhaSEpsTFRReE56QXlNQ0lzSW1GMWRHaGZkR2x0WlNJNk1UYzFNems1TkRNNU1Dd2lkWE5sY2w5cFpDSTZJblJuWHpjNE9URTFNalF5TkRRaUxDSnpkV0lpT2lKMFoxODNPRGt4TlRJME1qUTBJaXdpYVdGMElqb3hOelUwTURBMU1UZ3hMQ0psZUhBaU9qRTNOVFF3TURnM09ERXNJbVpwY21WaVlYTmxJanA3SW1sa1pXNTBhWFJwWlhNaU9udDlMQ0p6YVdkdVgybHVYM0J5YjNacFpHVnlJam9pWTNWemRHOXRJbjE5LldNREVyaFJya3c1SUZjWVhoVnJtR1FxbTZlTjZXSTNTeThPUVRoUHhvbFdwUUl3bnJacGtaVkpHRlZ5em8xRnkxdDNsSXVGSUJudG1QY1ZTWnYyNnlURURUNW9tbi1IYm1sN0t4ZERqSklnNlJpMWpVbW9JZmoxOXpocWFHaDM0aG9UZTlfMHJKRlEySkRuUHIzWUUzaXNLcmduMHR1SWdocXFIUUZqUEhGZk9LWWpYbXg4cTZtdFdNRE1DdWtvbGNWS2NWSGdUWXVsVkEyMG1WZU5aemg2LVdFV2owNTBBSmh0eG9Db0U0c2VDY2NNX2sxbzNHak5LSWJBU0VOdUxhR2drR2lYNWsxdEtjSmRQNjZqdml0VWhtNGlQeU1rcW1qUlpmMC1GR1hMdlV5Z3lyV2NYMFo0V3dpU2ZtalAyellnN0VicTRrSVZOSklqc1BzcHUwUa00NDRjNGI0NC1hOTI3"
            auth_bytes = base64.b64decode(auth_message_b64)
            
            # Отправляем как бинарные данные (Binary Message)
            await self.websocket.send(auth_bytes)
            logger.info("🔐 Отправили аутентификационное сообщение")
            
            # Ждем ответ
            response = await self.websocket.recv()
            logger.info(f"📨 Получили ответ от сервера: {len(response)} байт")
            
        except websockets.exceptions.ConnectionClosedError as e:
            if e.code == 1008:  # Policy violation
                logger.error(f"❌ Критическая ошибка аутентификации (код 1008): {e}")
                raise AuthenticationPolicyViolation("Требуется смена ключа авторизации")
            logger.error(f"❌ Ошибка аутентификации: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка аутентификации: {e}")
            raise
    
    async def subscribe_to_token_data(self, token_address: str):
        """Подписываемся на данные токена для анализа бандлеров"""
        try:
            # Проверяем, что это наш токен
            if token_address != self.token_address:
                logger.warning(f"⚠️ Попытка подписаться на другой токен {token_address[:8]} в соединении для {self.token_address[:8]}")
                return False
            
            # Проверяем, что соединение установлено
            if not self.websocket:
                logger.error(f"❌ WebSocket не подключен для токена {token_address[:8]}")
                return False
            
            logger.info(f"🔍 Получаем marketAddress для токена {token_address[:8]}...")
            
            # Используем правильный endpoint для получения marketAddress
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.axiom_api_domains[self.last_used_api_domain]}/swap-info?tokenAddress={token_address}", headers={
                    'accept': '*/*',
                    'cookie': 'auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6IjdhN2JhN2E3LWY4NDktNDVlNC05ZDI4LWY2MjRhNjUzY2YyYiIsImlhdCI6MTc1Mzk5MDE5Mn0.m825JgO7TNs6LR1RfmWs2y_O0qSZfQi3Tug04qdVKMw; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiMzVlNjc3YzMtMjY4Zi00YTFmLWI5M2ItN2VkOGJjN2IzYjU0IiwiaWF0IjoxNzUzOTk1MDM1LCJleHAiOjE3NTM5OTU5OTV9.pej0JiJAHSFVS_rvbKpYjK4slqJCxNDQqvUHdheH9L4'
                }, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    try:
                        data = await response.json(content_type=None)
                        market_id = data.get('pairAddress', None)
                    except Exception as e:
                        logger.error(f"Failed to parse JSON from swap-info: {e}")
                        market_id = None
                    self.last_used_api_domain = (self.last_used_api_domain + 1) % len(self.axiom_api_domains)

            # Если есть market_id, подписываемся на market stats и холдеров
            if market_id:
                logger.info(f"✅ Получили market_id {market_id} для токена {token_address[:8]}")
                # Подписываемся только на token stats
                token_subscribe_path = f"/fast-stats/encoded-tokens/solana-{market_id}/on-fast-stats-update"
                token_message_data = [4, 1, token_subscribe_path]
                token_message_bytes = msgpack.packb(token_message_data)
                
                logger.info(f"📊 Подписка на token fast-stats для {token_address[:8]}...")
                await self.websocket.send(token_message_bytes)

                # Подписка на market stats
                market_subscribe_path = f"/fast-stats/encoded-markets/solana-{market_id}/on-auto-migrating-market-stats-update"
                market_message_data = [4, 43, market_subscribe_path]
                market_message_bytes = msgpack.packb(market_message_data)
                
                logger.info(f"🔔 Подписываемся на market stats для токена {token_address[:8]}... (market: {market_id[:8]})")
                logger.info(f"📡 Market путь: {market_subscribe_path}")
                logger.info(f"📦 MessagePack структура: [4, 43, path] -> {len(market_message_bytes)} байт")
                await self.websocket.send(market_message_bytes)

                # # Подписка на холдеров (recent holders)
                # holders_subscribe_path = f"/holders/chains/SOLANA/tokenAddress/{token_address}/subscribe-recent-holders"
                # holders_message_data = [4, 37, holders_subscribe_path]
                # holders_message_bytes = msgpack.packb(holders_message_data)

                # logger.info(f"👥 Подписываемся на recent holders для токена {token_address[:8]}...")
                # logger.info(f"📡 Holders путь: {holders_subscribe_path}")
                # logger.info(f"📦 MessagePack структура: [4, 37, path] -> {len(holders_message_bytes)} байт")
                # await self.websocket.send(holders_message_bytes)

                # Новая подписка на top holders v3
                top_holders_subscribe_path = f"/holders/chains/SOLANA/tokenAddress/{token_address}/subscribe-top-holders-v3"
                top_holders_message_data = [4, 38, top_holders_subscribe_path]
                top_holders_message_bytes = msgpack.packb(top_holders_message_data)

                logger.info(f"🏆 Подписываемся на top holders v3 для токена {token_address[:8]}...")
                logger.info(f"📡 Top holders путь: {top_holders_subscribe_path}")
                logger.info(f"📦 MessagePack структура: [4, 38, path] -> {len(top_holders_message_bytes)} байт")
                await self.websocket.send(top_holders_message_bytes)

            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подписки на токен {token_address}: {e}")
            return False

    async def track_token_info(self, market_id: str, token_address: str):
        """Отслеживает изменения в token-info для заданного market_id"""
        last_data = None
        unchanged_time = 0
        start_time = time.time()

        while time.time() - start_time < 300:  # 5 минут
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.axiom_api_domains[self.last_used_api_domain]}/token-info?pairAddress={market_id}", headers={
                        'accept': '*/*',
                        'cookie': 'auth-refresh-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6ImU2YTQ3NmNlLWVlYzUtNDk0Yy05NzMyLWJmMTg2ODg5ODQyZiIsImlhdCI6MTc1MzM1MTk0Nn0.HxLwKo8UHnoAonBgcg01ZyPzBosdiNopHHu-HxIf8Yo; auth-access-token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiMjI2MGI0YzEtOWUxYy00YTlkLTkyZmQtYWE3ZGM2MWY1YTQzIiwiaWF0IjoxNzUzMzU4NTY4LCJleHAiOjE3NTMzNTk1Mjh9.231BR16KSiCQeRGI11kstS-pXLpNfYdJkIW0io3qv9I'
                    }, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        response_text = await response.text()
                        logger.info(f"123213s25ы1: {str(response.url)} {response_text}")
                        
                        current_data = response_text
                        
                        if current_data == last_data:
                            unchanged_time += 1
                            if unchanged_time >= 300:  # 5 минут без изменений
                                logger.info(f"Токен {token_address[:8]} перестал отслеживаться - нет изменений 5 минут")
                                return
                        else:
                            unchanged_time = 0
                            last_data = current_data
                            
                self.last_used_api_domain = (self.last_used_api_domain + 1) % len(self.axiom_api_domains)
                await asyncio.sleep(1)  # Пауза 1 секунда между запросами
                
            except Exception as e:
                logger.error(f"Ошибка при отслеживании token-info: {e}")
                await asyncio.sleep(1)

    
    async def listen_for_bundler_data(self):
        """Слушаем данные о бандлерах из WebSocket"""
        try:
            async for message in self.websocket:
                if isinstance(message, bytes):
                    # Декодируем бинарные данные
                    decoded_data = decode_padre_message(message)
                    
                    if decoded_data:
                        logger.info(f"🔍 Получили данные о бандлерах: {decoded_data}")
                        
                        # Проверяем, это ли ответ markets-per-token
                        if self.is_markets_per_token_response(decoded_data):
                            await self.process_markets_per_token_response(decoded_data)
                        # Проверяем, содержит ли сообщение данные о fast-stats
                        elif self.is_fast_stats_update(decoded_data):
                            await self.process_fast_stats_data(decoded_data)
                        elif self.is_top10holders_update(decoded_data):
                            await self.process_top10holders_data(decoded_data)
                        elif decoded_data.get('type') == 'ping':
                            # Это ping сообщение, отвечаем pong если нужно
                            logger.debug("📡 Получен ping от сервера")
                        else:
                            logger.debug(f"🔍 Неизвестный тип данных: {decoded_data}")
                            
                elif isinstance(message, str):
                    logger.info(f"📨 Текстовое сообщение: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("🔌 WebSocket соединение закрыто")
        except Exception as e:
            logger.error(f"❌ Ошибка при получении данных: {e}")
    
    def is_markets_per_token_response(self, data: dict) -> bool:
        """Проверяет, является ли сообщение ответом markets-per-token"""
        if not isinstance(data, dict):
            return False
        
        if 'raw_data' in data and isinstance(data['raw_data'], list):
            raw_data = data['raw_data']
            if len(raw_data) >= 4:
                # Проверяем markets-per-token responses [9, 45, 200, payload]
                if raw_data[0] == 9 and raw_data[1] == 45 and raw_data[2] == 200:
                    return True
        
        return False
    
    async def process_markets_per_token_response(self, data: dict):
        """Обрабатывает ответ markets-per-token и подписывается на найденные маркеты"""
        try:
            if 'raw_data' in data and isinstance(data['raw_data'], list):
                raw_data = data['raw_data']
                if len(raw_data) >= 4 and isinstance(raw_data[3], dict):
                    payload = raw_data[3]
                    
                    logger.info(f"📨 Обрабатываем ответ markets-per-token: {str(payload)[:200]}...")
                    
                    # Обрабатываем ответ и обновляем cache
                    process_markets_per_token_response(payload)
                    
                    # Теперь подписываемся на найденные маркеты
                    if 'markets' in payload and 'SOLANA' in payload['markets']:
                        solana_markets = payload['markets']['SOLANA']
                        
                        for token_address, markets_list in solana_markets.items():
                            if markets_list and isinstance(markets_list, list) and len(markets_list) > 0:
                                market_info = markets_list[0]
                                market_id = market_info.get('marketId')
                                
                                if market_id and market_id.startswith('solana-'):
                                    clean_market_id = market_id[7:]  # Убираем префикс "solana-"
                                    
                                    # Подписываемся на market stats
                                    await self.subscribe_to_market_stats(token_address, clean_market_id)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки markets-per-token ответа: {e}")
    
    async def subscribe_to_market_stats(self, token_address: str, market_id: str):
        """Подписывается на market stats для конкретного маркета"""
        try:
            market_subscribe_path = f"/fast-stats/encoded-markets/solana-{market_id}/on-auto-migrating-market-stats-update"
            
            # Создаём правильную MessagePack структуру: [4, 43, path] для market stats
            market_message_data = [4, 43, market_subscribe_path]
            market_message_bytes = msgpack.packb(market_message_data)
            
            logger.info(f"🔔 Подписываемся на market stats для токена {token_address[:8]}... (market: {market_id[:8]})")
            logger.info(f"📡 Market путь: {market_subscribe_path}")
            logger.info(f"📦 MessagePack структура: [4, 43, path] -> {len(market_message_bytes)} байт")
            
            # Отправляем сообщение подписки на market stats
            await self.websocket.send(market_message_bytes)
            
        except Exception as e:
            logger.error(f"❌ Ошибка подписки на market stats для {token_address[:8]}...: {e}")

    def is_fast_stats_update(self, data: dict) -> bool:
        """Проверяет, является ли сообщение обновлением fast-stats"""
        if not isinstance(data, dict):
            return False
        
        # Новая структура: ищем raw_data с различными типами сообщений
        if 'raw_data' in data and isinstance(data['raw_data'], list):
            raw_data = data['raw_data']
            if len(raw_data) >= 3:
                # Проверяем market stats responses [5, 43, payload]
                if raw_data[0] == 5 and raw_data[1] == 43:
                    return True
                # Проверяем token stats responses [5, 1, payload]
                elif raw_data[0] == 5 and raw_data[1] == 1:
                    return True
                # НЕ обрабатываем markets-per-token как fast-stats
                elif raw_data[0] == 9 and raw_data[1] == 45:
                    return False
        
        # Старые признаки fast-stats данных
        stats_indicators = ['bundlers', 'holders', 'volume', 'market_cap', 'trades', 'snapshot', 'tokenAddress', 'pumpFunGaze']
        return any(indicator in str(data).lower() for indicator in stats_indicators)

    def is_top10holders_update(self, data: dict) -> bool:
        """Проверяет, является ли сообщение обновлением top10holders"""
        if not isinstance(data, dict):
            return False
        
        # Новая структура: ищем raw_data с различными типами сообщений
        if 'raw_data' in data and isinstance(data['raw_data'], list):
            raw_data = data['raw_data']
            if len(raw_data) >= 3:
                # Проверяем market stats responses [5, 43, payload]
                if raw_data[0] == 5 and raw_data[1] == 38:
                    return True
                else:
                    return False
    
    def safe_format(self, value, format_spec: str, default=0):
        """Безопасное форматирование значения с обработкой None"""
        try:
            if value is None:
                value = default
            return f"{value:{format_spec}}"
        except (ValueError, TypeError):
            return f"{default:{format_spec}}"
    
    async def process_fast_stats_data(self, data: dict):
        """Обрабатываем данные fast-stats для извлечения информации о бандлерах"""
        try:
            logger.info(f"📊 Обрабатываем fast-stats данные: {str(data)}...")
            
            if not self.websocket:
                logger.warning(f"⚠️ WebSocket не подключен для {self.token_address[:8]}")
                return
            
            # Извлекаем данные из новой структуры [5, 1, payload]
            if 'raw_data' not in data or not isinstance(data['raw_data'], list):
                logger.warning("⚠️ Неверный формат данных")
                return
            
            raw_data = data['raw_data']
            if len(raw_data) < 3 or not isinstance(raw_data[2], dict):
                logger.warning("⚠️ Недостаточно данных в raw_data")
                return
            
            payload = raw_data[2]
            message_type_code = raw_data[1] if len(raw_data) > 1 else 0
            msg_type = payload.get('type', 'unknown')
            
            logger.info(f"📋 Тип сообщения fast-stats: {msg_type} (код: {message_type_code})")
            
            if message_type_code == 43:
                logger.info(f"🎯 ПОЛУЧИЛИ MARKET STATS (код 43) - ищем bundler данные!")
                
                if msg_type == 'init' and 'snapshot' in payload:
                    snapshot = payload['snapshot']
                    token_address = snapshot.get('baseTokenAddress')
                    market_id = snapshot.get('marketId')
                    
                    if token_address:
                        self.current_token_address = token_address
                        logger.info(f"🔍 ПОЛНЫЙ MARKET INIT SNAPSHOT для {token_address[:8]}:")
                        logger.info(f"📦 INIT SNAPSHOT: {snapshot}")
                        
                        if token_address in self.token_data_cache:
                            logger.warning(f"⭐️ Токен {token_address[:8]} прошёл миграцию")
                            return

                        # Сохраняем базовые данные из snapshot
                        self.token_data_cache[token_address] = {
                            'timestamp': int(time.time()),  # Добавляем timestamp
                            'basePriceInUsdUi': snapshot.get('basePriceInUsdUi'),
                            'basePriceInQuoteUi': snapshot.get('basePriceInQuoteUi'),
                            'liquidityInUsdUi': snapshot.get('liquidityInUsdUi'),
                            'totalSupply': snapshot.get('baseTokenTotalSupply'),
                            'symbol': snapshot.get('baseTokenSymbol'),
                            'name': snapshot.get('baseTokenName'),
                            'marketCreatedAt': snapshot.get('marketCreatedAt'),
                            'total_holders': snapshot.get('totalHolders', 0),
                            'devHoldingPcnt': 0,
                            'tradingAppTxns': 0,
                            'freshWalletBuys': {'count': 0, 'sol': 0},
                            'insidersHoldingPcnt': 0,
                            'totalSnipers': 0,
                            'bundlesHoldingPcnt': {'current': 0, 'ath': 0},
                            'totalBundlesCount': 0,
                            'totalSolSpentInBundles': 0,
                            'totalTokenBoughtInBundles': 0,
                            'totalSolFees': 0,
                            'snipersHoldingPcnt': 0,
                            'baseTokenAudit': snapshot.get('baseTokenAudit', {})  # Сохраняем аудит токена
                        }
                        
                        # Если есть baseTokenAudit в snapshot, обновляем его
                        if 'baseTokenAudit' in snapshot:
                            self.token_data_cache[token_address]['baseTokenAudit'] = snapshot['baseTokenAudit']
                            logger.info(f"📊 Сохранен аудит токена: {snapshot['baseTokenAudit']}")
                        
                        # Обрабатываем метрики для раннего обнаружения
                        await self.process_token_metrics(self.token_data_cache[token_address])
                
                elif msg_type == 'update':
                    logger.info(f"🚀 MARKET UPDATE - ищем bundler данные!")
                    
                    if 'update' in payload:
                        update_data = payload['update']
                        
                        # Добавляем timestamp в update данные
                        update_data['timestamp'] = int(time.time())
                        
                        # Если есть baseTokenAudit в update, обновляем его
                        if 'baseTokenAudit' in update_data:
                            if self.current_token_address in self.token_data_cache:
                                self.token_data_cache[self.current_token_address]['baseTokenAudit'] = update_data['baseTokenAudit']
                                logger.info(f"📊 Обновлен аудит токена: {update_data['baseTokenAudit']}")
                        
                        if self.current_token_address in self.token_data_cache:
                            # Обновляем существующие данные
                            self.token_data_cache[self.current_token_address].update(update_data)
                            # Обновляем timestamp
                            self.token_data_cache[self.current_token_address]['timestamp'] = update_data['timestamp']
                            # Обрабатываем обновленные метрики
                            await self.process_token_metrics(self.token_data_cache[self.current_token_address])
            
            if 'update' not in payload:
                logger.warning("⚠️ Нет 'update' поля в payload")
                return
            
            update_data = payload['update']
            logger.info(f"📦 ПОЛНЫЙ MARKET UPDATE: {update_data}")
            
            if not self.current_token_address:
                logger.warning("⚠️ Не установлен текущий токен")
                return
            
            # Получаем или создаем кеш для текущего токена
            current_cache = self.token_data_cache.get(self.current_token_address, {})
            if not current_cache:
                current_cache = {
                    'basePriceInUsdUi': 0,
                    'basePriceInQuoteUi': 0,
                    'liquidityInUsdUi': 0,
                    'total_holders': 0,
                    'devHoldingPcnt': 0,
                    'tradingAppTxns': 0,
                    'freshWalletBuys': {'count': 0, 'sol': 0},
                    'insidersHoldingPcnt': 0,
                    'totalSnipers': 0,
                    'bundlesHoldingPcnt': {'current': 0, 'ath': 0},
                    'totalBundlesCount': 0,
                    'totalSolSpentInBundles': 0,
                    'totalTokenBoughtInBundles': 0,
                    'totalSolFees': 0,
                    'snipersHoldingPcnt': 0,
                    'baseTokenAudit': {
                        'chain': 'SOLANA',
                        'tokenAddress': self.current_token_address,
                        'deployerAddress': None,
                        'isFreezeAuthorityEnabled': None,
                        'isMintAuthorityEnabled': None,
                        'top10HoldersPcnt': None
                    }
                }
            
            # Обновляем базовые данные
            if 'basePriceInUsdUi' in update_data:
                current_cache['basePriceInUsdUi'] = update_data['basePriceInUsdUi']
            if 'basePriceInQuoteUi' in update_data:
                current_cache['basePriceInQuoteUi'] = update_data['basePriceInQuoteUi']
            if 'liquidityInUsdUi' in update_data:
                current_cache['liquidityInUsdUi'] = update_data['liquidityInUsdUi']
            if 'totalHolders' in update_data:
                current_cache['total_holders'] = update_data['totalHolders']
            
            # Обрабатываем pumpFunGaze данные
            if 'pumpFunGaze' in update_data:
                pump_gaze = update_data['pumpFunGaze']
                for key in ['devHoldingPcnt', 'tradingAppTxns', 'freshWalletBuys',
                          'insidersHoldingPcnt', 'totalSupply', 'totalSnipers',
                          'bundlesHoldingPcnt', 'totalBundlesCount', 'totalSolSpentInBundles',
                          'totalTokenBoughtInBundles', 'totalSolFees', 'snipersHoldingPcnt']:
                    if key in pump_gaze:
                        current_cache[key] = pump_gaze[key]
            
            # Сохраняем обновленный кеш
            self.token_data_cache[self.current_token_address] = current_cache
            
            # Подробное логирование
            logger.info("📊 ОБНОВЛЕННЫЕ ДАННЫЕ:")
            logger.info(f"💵 Цена USD: ${self.safe_format(current_cache.get('basePriceInUsdUi', 0), ',.8f')}")
            logger.info(f"💧 Ликвидность: ${self.safe_format(current_cache.get('liquidityInUsdUi', 0), ',.2f')}")
            logger.info(f"👥 Холдеры: {current_cache.get('total_holders', 0)}")
            logger.info(f"📦 Бандлеры: {current_cache.get('totalBundlesCount', 0)}")
            logger.info(f"🆕 Fresh Wallets: {(current_cache.get('freshWalletBuys', {}) or {}).get('count', 0)}")
            
            # Обрабатываем метрики для обнаружения
            await self.process_token_metrics(current_cache)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки fast-stats данных: {e}")
            logger.error(traceback.format_exc())

    async def process_top10holders_data(self, data: dict):
        """Обрабатываем данные top10holders для извлечения информации о ТОП-10 холдерах"""
        try:
            logger.info(f"📊 Обрабатываем top10holders данные: {str(data)}...")
            
            if not self.websocket:
                logger.warning(f"⚠️ WebSocket не подключен для {self.token_address[:8]}")
                return
            
            # Извлекаем данные из новой структуры [5, 1, payload]
            if 'raw_data' not in data or not isinstance(data['raw_data'], list):
                logger.warning("⚠️ Неверный формат данных")
                return
            
            raw_data = data['raw_data']
            if len(raw_data) < 3 or not isinstance(raw_data[2], dict):
                logger.warning("⚠️ Недостаточно данных в raw_data")
                return
            
            payload = raw_data[2]
            message_type_code = raw_data[1] if len(raw_data) > 1 else 0
            msg_type = payload.get('type', 'unknown')
            
            logger.info(f"📋 Тип сообщения top10holders: {msg_type} (код: {message_type_code})")
            
            if message_type_code == 38:
                logger.info(f"🎯 ПОЛУЧИЛИ top10holders (код 38) - ищем данные о холдерах!")
                
                if msg_type == 'update':
                    logger.info(f"🚀 top10holders UPDATE - ищем данные о холдерах!")
                    
                    if 'update' in payload:
                        update_data = payload['update']
                        
                        # Добавляем timestamp в update данные
                        update_data['timestamp'] = int(time.time())

                        if 'totalSupply' in self.token_data_cache[self.current_token_address]:
                            totalSupply = self.token_data_cache[self.current_token_address]['totalSupply']
                            if not totalSupply:
                                logger.warning("⚠️ Нет 'totalSupply' поля в self.token_data_cache[self.current_token_address]")
                                return
                        else:
                            logger.warning("⚠️ Нет 'totalSupply' поля в self.token_data_cache[self.current_token_address]")
                            return

                        if 'deleted' in update_data:
                            if self.current_token_address in self.token_data_cache:
                                if 'top10holders' in self.token_data_cache[self.current_token_address]:
                                    top10holders_pcnt = self.token_data_cache[self.current_token_address]['top10holders']
                                else:
                                    top10holders_pcnt = {}
                                for delete in update_data['deleted']:
                                    del top10holders_pcnt[delete[1]]
                                if 'top10holders' in self.token_data_cache[self.current_token_address]:
                                    self.token_data_cache[self.current_token_address]['top10holders'].update(top10holders_pcnt)
                                    logger.info(f"📊 Удалены top10holders токена: {update_data['deleted']}")
                                else:
                                    self.token_data_cache[self.current_token_address]['top10holders'] = top10holders_pcnt
                                    logger.info(f"📊 Удалены top10holders токена: {update_data['deleted']}")

                        if 'updated' in update_data:
                            if self.current_token_address in self.token_data_cache:
                                if len(update_data['updated']) == 1 and update_data['updated'][0][4]:
                                    liquidityPoolAddress = update_data['updated'][0][1]
                                    if not self.token_data_cache[self.current_token_address].get('liquidityPoolAddress'):
                                        logger.info(f"Найден пул ликвидности: {update_data['updated'][0][1]}")
                                        self.token_data_cache[self.current_token_address]['liquidityPoolAddress'] = liquidityPoolAddress
                                        self.token_data_cache[self.current_token_address]['liquidityPoolPcnt'] = int(update_data['updated'][0][2]) / int(totalSupply) * 100
                                    else:
                                        if self.token_data_cache[self.current_token_address].get('liquidityPoolAddress') == liquidityPoolAddress:
                                            self.token_data_cache[self.current_token_address]['liquidityPoolPcnt'] = int(update_data['updated'][0][2]) / int(totalSupply) * 100
                                    
                                for update in update_data['updated']:
                                    if update[2]:
                                        top10holders_pcnt[update[1]] = {
                                            'pcnt': int(update[2]) / int(totalSupply) * 100,
                                            'insider': update[4],
                                            'isBundler': update[15],
                                            'isPool': self.token_data_cache[self.current_token_address].get('liquidityPoolAddress') == update[1]
                                        }
                                    else:
                                        top10holders_pcnt[update[1]] = {
                                            'pcnt': 0,
                                            'insider': update[4],
                                            'isBundler': update[15],
                                            'isPool': self.token_data_cache[self.current_token_address].get('liquidityPoolAddress') == update[1]
                                        }
                                self.token_data_cache[self.current_token_address]['top10holders'] = top10holders_pcnt
                                logger.info(f"📊 Обновлен top10holders токена: {update_data['updated']}")
                        
                        if self.current_token_address in self.token_data_cache:
                            # Обновляем существующие данные
                            self.token_data_cache[self.current_token_address].update(update_data)
                            # Обновляем timestamp
                            self.token_data_cache[self.current_token_address]['timestamp'] = update_data['timestamp']
                            # Обрабатываем обновленные метрики
                            await self.process_token_metrics(self.token_data_cache[self.current_token_address])
                
                elif msg_type == 'init':
                    snapshot_data = payload["snapshot"]

                    # Добавляем timestamp в snapshot данные
                    snapshot_data['timestamp'] = int(time.time())

                    if 'totalSupply' in self.token_data_cache[self.current_token_address]:
                        totalSupply = self.token_data_cache[self.current_token_address]['totalSupply']
                    else:
                        logger.warning("⚠️ Нет 'totalSupply' поля в self.token_data_cache[self.current_token_address]")
                        return

                    # Если есть allEntries в snapshot, обновляем его
                    if 'allEntries' in snapshot_data:
                        if self.current_token_address in self.token_data_cache:
                            if 'top10holders' in self.token_data_cache[self.current_token_address]:
                                top10holders_pcnt = self.token_data_cache[self.current_token_address]['top10holders']
                            else:
                                top10holders_pcnt = {}
                            logger.info(f"Найден пул ликвидности: {snapshot_data['allEntries'][0][1]}")
                            liquidityPoolAddress = snapshot_data['allEntries'][0][1]
                            self.token_data_cache[self.current_token_address]['liquidityPoolAddress'] = liquidityPoolAddress
                            for entry in snapshot_data['allEntries']:
                                if entry[2]:
                                    top10holders_pcnt[entry[1]] = {
                                        'pcnt': int(entry[2]) / int(totalSupply) * 100,
                                        'insider': entry[4],
                                        'isBundler': entry[15],
                                        'isPool': liquidityPoolAddress == entry[1]
                                    }
                                else:
                                    top10holders_pcnt[entry[1]] = {
                                        'pcnt': 0,
                                        'insider': entry[4],
                                        'isBundler': entry[15],
                                        'isPool': liquidityPoolAddress == entry[1]
                                    }
                            self.token_data_cache[self.current_token_address]['top10holders'] = top10holders_pcnt
                            logger.info(f"📊 Создан top10holders токена: {snapshot_data['allEntries']}")
                    
                    if self.current_token_address in self.token_data_cache:
                        # Обновляем существующие данные
                        self.token_data_cache[self.current_token_address].update(snapshot_data)
                        # Обновляем timestamp
                        self.token_data_cache[self.current_token_address]['timestamp'] = snapshot_data['timestamp']
                        # Обрабатываем обновленные метрики
                        await self.process_token_metrics(self.token_data_cache[self.current_token_address])

            
            if 'update' not in payload:
                logger.warning("⚠️ Нет 'update' поля в payload")
                return
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки top10holders данных: {e}")
            logger.error(traceback.format_exc())
    
    def extract_bundler_data(self, data: dict) -> dict:
        """Извлекает данные о бандлерах из fast-stats ответа"""
        try:
            # Попробуем различные структуры данных
            bundler_info = {}
            
            # Вариант 1: прямые поля
            if 'bundlers' in data:
                bundler_info['bundler_count'] = data['bundlers']
            elif 'bundler_count' in data:
                bundler_info['bundler_count'] = data['bundler_count']
                
            # Вариант 2: поля в stats объекте
            if 'stats' in data:
                stats = data['stats']
                if 'bundlers' in stats:
                    bundler_info['bundler_count'] = stats['bundlers']
                if 'holders' in stats:
                    bundler_info['total_holders'] = stats['holders']
                    
            # Вариант 3: множественные токены в массиве
            if 'tokens' in data:
                # Обрабатываем каждый токен отдельно
                for token_data in data['tokens']:
                    token_address = token_data.get('address') or token_data.get('contract')
                    if token_address:
                        bundler_info['token_address'] = token_address
                        bundler_info['bundler_count'] = token_data.get('bundlers', 0)
                        bundler_info['total_holders'] = token_data.get('holders', 0)
                        break
                        
            # Поиск токена по адресу
            if not bundler_info.get('token_address'):
                # Ищем адрес токена в различных полях
                for key, value in data.items():
                    if isinstance(value, str) and len(value) > 30:  # Похоже на адрес токена
                        bundler_info['token_address'] = value
                        break
                        
            return bundler_info if bundler_info else None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных о бандлерах: {e}")
            return None
    
    def extract_bundler_data_from_init_snapshot(self, snapshot: dict, token_address: str) -> dict:
        """Извлекает данные о бандлерах из init snapshot"""
        try:
            bundler_info = {'token_address': token_address}
            
            # ВАЖНО: Извлекаем и сохраняем метаданные токена из snapshot
            symbol = snapshot.get('baseTokenSymbol') or snapshot.get('symbol', 'UNK')
            name = snapshot.get('baseTokenName') or snapshot.get('name', symbol)
            market_cap = snapshot.get('marketCapInUsd', snapshot.get('fdvInUsdUi', 0))
            
            # Сохраняем метаданные токена в кеш
            if symbol != 'UNK' or name != symbol:
                self.token_data_cache[token_address] = {
                    'symbol': symbol,
                    'name': name,
                    'market_cap': market_cap,
                    'dex_source': 'Pump.fun',
                    'chain': snapshot.get('chain', 'SOLANA'),
                    'source': 'market_init_snapshot'
                }
                logger.info(f"✅ Сохранили метаданные токена {name} ({symbol}) в кеш из market snapshot")
            
            # Ищем в pumpFunGaze (основной источник bundler данных)
            logger.info(f"🔍 Проверяем наличие pumpFunGaze в snapshot...")
            logger.info(f"📋 Ключи в snapshot: {list(snapshot.keys())}")
            
            if 'pumpFunGaze' in snapshot and snapshot['pumpFunGaze'] is not None:
                pump_gaze = snapshot['pumpFunGaze']
                logger.info(f"🎯 Найдены pumpFunGaze данные в init:")
                logger.info(f"📦 ПОЛНЫЕ pumpFunGaze данные: {pump_gaze}")
                
                # Извлекаем количество бандлеров и холдеров
                if 'totalBundlesCount' in pump_gaze:
                    bundler_info['bundler_count'] = pump_gaze['totalBundlesCount']
                
                # Извлекаем процент бандлеров
                if 'bundlesHoldingPcnt' in pump_gaze:
                    bundles_pcnt = pump_gaze['bundlesHoldingPcnt']
                    if isinstance(bundles_pcnt, dict) and 'current' in bundles_pcnt:
                        bundler_info['bundler_percentage'] = bundles_pcnt['current']
                        bundler_info['bundler_percentage_ath'] = bundles_pcnt.get('ath', 0)
                
                # Дополнительная информация
                if 'totalSolSpentInBundles' in pump_gaze:
                    bundler_info['sol_spent_in_bundles'] = pump_gaze['totalSolSpentInBundles']
            
            # Извлекаем общее количество холдеров
            if 'totalHolders' in snapshot:
                bundler_info['total_holders'] = snapshot['totalHolders']
            
            # Проверяем, есть ли достаточно данных для анализа
            if bundler_info.get('bundler_count') and bundler_info.get('total_holders'):
                return bundler_info
            elif bundler_info.get('bundler_percentage') and bundler_info.get('total_holders'):
                return bundler_info
            else:
                logger.debug(f"⚠️ Недостаточно bundler данных в init snapshot для {token_address[:8]}...")
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения bundler данных из init snapshot: {e}")
            return None

    def extract_bundler_data_from_update(self, update_payload: dict) -> dict:
        """Извлекает данные о бандлерах из update сообщения"""
        try:
            bundler_info = {}
            
            # НОВЫЙ ФОРМАТ: pumpFunGaze данные
            logger.info(f"🔍 Проверяем наличие pumpFunGaze в update...")
            logger.info(f"📋 Ключи в update_payload: {list(update_payload.keys())}")
            
            if 'pumpFunGaze' in update_payload and update_payload['pumpFunGaze'] is not None:
                pump_gaze = update_payload['pumpFunGaze']
                logger.info(f"🎯 Найдены pumpFunGaze данные в update:")
                logger.info(f"📦 ПОЛНЫЕ pumpFunGaze данные: {pump_gaze}")
                
                # Ищем ключи bundler данных
                logger.info(f"🔍 Ключи в pumpFunGaze: {list(pump_gaze.keys())}")
                
                # Извлекаем количество бандлеров
                if 'totalBundlesCount' in pump_gaze and pump_gaze['totalBundlesCount'] is not None:
                    bundler_info['bundler_count'] = pump_gaze['totalBundlesCount']
                    logger.info(f"✅ Найден totalBundlesCount: {pump_gaze['totalBundlesCount']}")
                else:
                    logger.info(f"❌ totalBundlesCount не найден или None")
                
                # Извлекаем процент бандлеров (уже рассчитанный)
                if 'bundlesHoldingPcnt' in pump_gaze and pump_gaze['bundlesHoldingPcnt'] is not None:
                    bundles_pcnt = pump_gaze['bundlesHoldingPcnt']
                    logger.info(f"✅ Найден bundlesHoldingPcnt: {bundles_pcnt}")
                    if isinstance(bundles_pcnt, dict) and 'current' in bundles_pcnt:
                        bundler_info['bundler_percentage'] = bundles_pcnt['current']
                        bundler_info['bundler_percentage_ath'] = bundles_pcnt.get('ath', 0)
                        logger.info(f"✅ Извлечен bundler процент: {bundles_pcnt['current']}%")
                    else:
                        logger.info(f"❌ bundlesHoldingPcnt неправильного формата")
                else:
                    logger.info(f"❌ bundlesHoldingPcnt не найден или None")
                
                # Дополнительная информация
                if 'totalSolSpentInBundles' in pump_gaze and pump_gaze['totalSolSpentInBundles'] is not None:
                    bundler_info['sol_spent_in_bundles'] = pump_gaze['totalSolSpentInBundles']
            
            # Извлекаем общее количество холдеров
            if 'totalHolders' in update_payload:
                bundler_info['total_holders'] = update_payload['totalHolders']
                
            # Также проверяем bundler данные на уровне update_payload
            if 'bundlesHoldingPcnt' in update_payload and update_payload['bundlesHoldingPcnt'] is not None:
                bundles_pcnt = update_payload['bundlesHoldingPcnt']
                if isinstance(bundles_pcnt, dict) and 'current' in bundles_pcnt:
                    bundler_info['bundler_percentage'] = bundles_pcnt['current']
                    bundler_info['bundler_percentage_ath'] = bundles_pcnt.get('ath', 0)
                    logger.info(f"🎯 Найден bundler percentage в update_payload: {bundles_pcnt['current']}%")
                    
            if 'totalBundlesCount' in update_payload and update_payload['totalBundlesCount'] is not None:
                bundler_info['bundler_count'] = update_payload['totalBundlesCount']
                logger.info(f"🎯 Найден bundler count в update_payload: {update_payload['totalBundlesCount']}")
                
            if 'totalSolSpentInBundles' in update_payload and update_payload['totalSolSpentInBundles'] is not None:
                bundler_info['sol_spent_in_bundles'] = update_payload['totalSolSpentInBundles']
            
            # Старые форматы (оставляем для совместимости)
            if 'bundlers' in update_payload:
                bundler_info['bundler_count'] = update_payload['bundlers']
            if 'holders' in update_payload:
                bundler_info['total_holders'] = update_payload['holders']
            if 'tokenAddress' in update_payload:
                bundler_info['token_address'] = update_payload['tokenAddress']
                
            # Ищем в дельтах (изменения)
            if 'delta' in update_payload:
                delta = update_payload['delta']
                if 'bundlers' in delta:
                    bundler_info['bundler_count'] = delta['bundlers']
                if 'holders' in delta:
                    bundler_info['total_holders'] = delta['holders']
                    
            # Ищем в stats
            if 'stats' in update_payload:
                stats = update_payload['stats']
                if 'bundlers' in stats:
                    bundler_info['bundler_count'] = stats['bundlers']
                if 'holders' in stats:
                    bundler_info['total_holders'] = stats['holders']
                    
            # Проверяем, есть ли достаточно данных для анализа
            logger.info(f"🔍 Проверяем извлеченные bundler данные: {bundler_info}")
            
            bundler_count = bundler_info.get('bundler_count')
            bundler_percentage = bundler_info.get('bundler_percentage') 
            total_holders = bundler_info.get('total_holders')
            
            logger.info(f"📊 bundler_count: {bundler_count}")
            logger.info(f"📊 bundler_percentage: {bundler_percentage}")
            logger.info(f"📊 total_holders: {total_holders}")
            
            # Проверяем, есть ли основные bundler данные
            has_bundler_data = bundler_count is not None or bundler_percentage is not None
            
            if has_bundler_data:
                logger.info(f"✅ Bundler данные найдены! Возвращаем: {bundler_info}")
                return bundler_info
            else:
                logger.info(f"❌ Нет bundler данных (ни count, ни percentage)")
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения bundler данных из update: {e}")
            return None

    async def process_bundler_detection(self, bundler_info: dict):
        """Обрабатывает обнаруженные данные о бандлерах"""
        try:
            token_address = bundler_info.get('token_address')
            bundler_count = bundler_info.get('bundler_count', 0)
            total_holders = bundler_info.get('total_holders', 0)
            
            # Используем уже рассчитанный процент если доступен
            bundler_percentage = bundler_info.get('bundler_percentage')
            if bundler_percentage is None and bundler_count > 0 and total_holders > 0:
                bundler_percentage = (bundler_count / total_holders) * 100
            
            if bundler_count > 0 and bundler_percentage is not None:
                # Используем сохраненный адрес токена если не передан
                if not token_address and hasattr(self, 'current_token_address'):
                    token_address = self.current_token_address
                
                bundler_percentage_ath = bundler_info.get('bundler_percentage_ath', bundler_percentage)
                sol_spent = bundler_info.get('sol_spent_in_bundles', 0)
                
                logger.info(f"🎯 БАНДЛЕР ДАННЫЕ ОБНАРУЖЕНЫ!")
                logger.info(f"📊 Токен {token_address if token_address else 'N/A'}: {bundler_count} бандлеров")
                logger.info(f"👥 Холдеры: {total_holders}")
                logger.info(f"📈 Текущий %: {bundler_percentage:.2f}%")
                logger.info(f"🔥 ATH %: {bundler_percentage_ath:.2f}%")
                logger.info(f"💰 SOL потрачено в бандлах: {sol_spent:.2f}")
                
                if bundler_percentage > 0:
                    logger.info(f"Токен имеет {bundler_percentage:.2f}% бандлеров")
                    
                    # Получаем данные токена из кеша
                    cached_data = self.token_data_cache.get(token_address, {})
                    
                    # Формируем данные токена для уведомления
                    token_data = {
                        'address': token_address or "Unknown",
                        'symbol': cached_data.get('symbol', 'UNK'),
                        'name': cached_data.get('name', 'Unknown Token'),
                        'market_cap': cached_data.get('market_cap', 0),
                        'dex_source': cached_data.get('dex_source', 'Unknown'),
                        'total_holders': total_holders,
                        'bundler_percentage_ath': bundler_percentage_ath,
                        'sol_spent_in_bundles': sol_spent,
                        'bundler_count': bundler_count,
                        # Базовые поля
                        'basePriceInUsdUi': cached_data.get('basePriceInUsdUi', 0),
                        'basePriceInQuoteUi': cached_data.get('basePriceInQuoteUi', 0),
                        'liquidityInUsdUi': cached_data.get('liquidityInUsdUi', 0),
                        'deployerHoldingPcnt': cached_data.get('deployerHoldingPcnt', 0),
                        
                        # PumpFunGaze данные
                        'devHoldingPcnt': cached_data.get('devHoldingPcnt', 0),
                        'tradingAppTxns': cached_data.get('tradingAppTxns', 0),
                        'freshWalletBuys': cached_data.get('freshWalletBuys', {'count': 0, 'sol': 0}),
                        'insidersHoldingPcnt': cached_data.get('insidersHoldingPcnt', 0),
                        'totalSupply': cached_data.get('totalSupply', 0),
                        'totalSnipers': cached_data.get('totalSnipers', 0),
                        'bundlesHoldingPcnt': cached_data.get('bundlesHoldingPcnt', {'current': 0, 'ath': 0}),
                        'totalBundlesCount': cached_data.get('totalBundlesCount', 0),
                        'totalSolSpentInBundles': cached_data.get('totalSolSpentInBundles', 0),
                        'totalTokenBoughtInBundles': cached_data.get('totalTokenBoughtInBundles', 0),
                        'totalSolFees': cached_data.get('totalSolFees', 0),
                        'snipersHoldingPcnt': cached_data.get('snipersHoldingPcnt', 0),
                    }

                    # Получаем deployer процент (может быть числом или объектом)
                    deployer_pcnt = token_data.get('deployerHoldingPcnt')
                    if isinstance(deployer_pcnt, dict):
                        deployer_pcnt = deployer_pcnt.get('current', 0)

                    if total_holders > 18 and bundler_count > 0 and bundler_count < 6:
                        logger.info(f"🎯 Найдены подходящие условия для уведомления! Holders: {total_holders}, Bundlers: {bundler_count}")
                        
                        # Формируем bundler_info для отправки
                        bundler_info = {
                            'token_address': self.token_address,
                            'bundler_count': bundler_count,
                            'total_holders': total_holders,
                            'bundler_percentage': bundles_pcnt.get('current', 0),
                            'bundler_percentage_ath': bundles_pcnt.get('ath', 0),
                            'sol_spent_in_bundles': pump_gaze.get('totalSolSpentInBundles', 0)
                        }
                        
                        # Добавляем все данные из кеша
                        bundler_info.update(self.token_data_cache.get(self.token_address, {}))
                        
                        # Отправляем уведомление
                        await self.send_bundler_notification(
                            contract_address=self.token_address,
                            token_data=bundler_info,
                            bundler_count=bundler_count,
                            bundler_percentage=bundles_pcnt.get('current', 0),
                            simulated=False
                        )
                    else:
                        logger.info(f"⚠️ Токен {self.token_address[:8]} не соответствует условиям: holders={total_holders}, bundlers={bundler_count}")
                    
                else:
                    logger.info(f"✅ Ниже порога: {bundler_percentage:.2f}%")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки bundler detection: {e}")
    
    async def analyze_token_bundlers(self, contract_address: str):
        """Анализируем бандлеров токена и отправляем уведомление при необходимости"""
        try:
            token_data = pending_tokens.get(contract_address)
            bundler_data = bundler_results.get(contract_address)
            
            if not token_data or not bundler_data:
                return
            
            bundler_count = bundler_data['bundler_count']
            
            # Рассчитываем процент бандлеров (условная формула, нужно адаптировать)
            # Предполагаем, что 100% = 1000 держателей (это нужно настроить)
            max_holders = 1000
            bundler_percentage = (bundler_count / max_holders) * 100
            
            logger.info(f"📈 Токен {contract_address[:8]}: {bundler_count} бандлеров ({bundler_percentage:.1f}%)")
            
            # Проверяем, достигается ли минимальный порог
            if bundler_percentage >= MIN_BUNDLER_PERCENTAGE:
                await self.send_bundler_alert(token_data, bundler_count, bundler_percentage)
            else:
                logger.info(f"⚪ Токен {contract_address[:8]}: процент бандлеров {bundler_percentage:.1f}% ниже порога {MIN_BUNDLER_PERCENTAGE}%")
            
            # Удаляем токен из очереди
            del pending_tokens[contract_address]
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа бандлеров для {contract_address[:8]}: {e}")
    
    async def send_bundler_alert(self, token_data: dict, bundler_count: int, bundler_percentage: float):
        """Отправляем уведомление о токене с высоким процентом бандлеров"""
        try:
            contract_address = token_data.get('mint', token_data.get('address', 'Unknown'))
            symbol = token_data.get('symbol', 'UNK')
            name = token_data.get('name', 'Unknown Token')
            
            # Формируем сообщение
            message = (
                f"🔥 <b>ВЫСОКИЙ ПРОЦЕНТ БАНДЛЕРОВ!</b>\n\n"
                f"💎 <b>Токен:</b> {name} ({symbol})\n"
                f"📍 <b>Контракт:</b> <code>{contract_address}</code>\n"
                f"👥 <b>Бандлеров:</b> {bundler_count}\n"
                f"📊 <b>Процент:</b> {bundler_percentage:.1f}%\n"
                f"⚡ <b>Порог:</b> {MIN_BUNDLER_PERCENTAGE}%\n\n"
                f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # Создаем кнопки
            keyboard = [
                [
                    {"text": "💎 Axiom.trade", "url": f"https://axiom.trade/t/{contract_address}"},
                    {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{contract_address}"}
                ],
                [
                    {"text": "🔍 trade.padre.gg", "url": f"https://trade.padre.gg/trade/solana/{contract_address}"}
                ]
            ]
            
            # Отправляем в указанную группу и тему
            success = await self.send_telegram_message(message, keyboard)
            
            if success:
                logger.info(f"✅ Отправлено уведомление о токене {symbol} с {bundler_percentage:.1f}% бандлеров")
            else:
                logger.error(f"❌ Не удалось отправить уведомление о токене {symbol}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")
    
    async def send_telegram_message(self, message: str, keyboard: List[List[Dict[str, str]]] = None) -> bool:
        """Отправляет сообщение в Telegram с задержкой при необходимости"""
        try:
            # Проверяем, не слишком ли часто отправляем
            current_time = time.time()
            if hasattr(self, 'last_telegram_time'):
                time_since_last = current_time - self.last_telegram_time
                if time_since_last < 3:  # Минимум 3 секунды между сообщениями
                    await asyncio.sleep(3 - time_since_last)
            
            # Отправляем сообщение
            chat_id = "-1002680160752"  # ID чата
            thread_id = "13134"  # ID треда
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"  # Используем глобальную константу
            
            data = {
                "chat_id": chat_id,
                "message_thread_id": thread_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            if keyboard:
                data["reply_markup"] = {"inline_keyboard": keyboard}
            
            logger.info(f"📤 Отправляем в Telegram: chat={chat_id}, thread={thread_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = (await response.json()).get('parameters', {}).get('retry_after', 30)
                        logger.warning(f"⚠️ Слишком много запросов к Telegram API. Ждем {retry_after} сек.")
                        await asyncio.sleep(retry_after)
                        # Пробуем отправить еще раз
                        async with session.post(url, json=data) as retry_response:
                            if retry_response.status != 200:
                                logger.error(f"❌ Ошибка Telegram API: {response.status} - {await response.text()}")
                                return False
                    elif response.status != 200:
                        logger.error(f"❌ Ошибка Telegram API: {response.status} - {await response.text()}")
                        return False
                        
            # Сохраняем время последней отправки
            self.last_telegram_time = time.time()
            logger.info("✅ Сообщение успешно отправлено в Telegram")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в Telegram: {e}")
            return False
    
    async def start(self):
        """Запускает клиент"""
        self.running = True
        self.start_time = asyncio.get_event_loop().time()  # Записываем время начала
        
        logger.info(f"🔗 Запускаем Padre соединение {self.connection_id} для токена {self.token_address[:8]} (макс. {self.max_duration // 60} мин)")
        
        try:
            if await self.connect():
                # Подписываемся на данные токена сразу после аутентификации
                await self.subscribe_to_token_data(self.token_address)
                # Начинаем слушать данные
                await self.listen_for_bundler_data()
            else:
                logger.error(f"❌ Не удалось подключиться для токена {self.token_address[:8]}")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска клиента для {self.token_address[:8]}: {e}")
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
        """Проверяет истекло ли время соединения"""
        if not self.start_time:
            return False
        
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.start_time
        return elapsed >= self.max_duration
    
    def get_remaining_time(self) -> float:
        """Возвращает оставшееся время соединения в секундах"""
        if not self.start_time:
            return self.max_duration
        
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.start_time
        return max(0, self.max_duration - elapsed)
    
    def is_connection_expired(self) -> bool:
        """Проверяет истекло ли время соединения"""
        if not self.start_time:
            return False
        
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.start_time
        return elapsed >= self.max_duration
    
    async def stop(self):
        """Останавливает все соединения и менеджер"""
        self.running = False
        
        # Отменяем задачу очистки
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Закрываем все активные соединения
        for token_address in list(self.active_connections.keys()):
            await self._remove_connection(token_address, reason="остановка менеджера")
        
        logger.info("✅ MultiplePadreManager остановлен")

    async def process_token_metrics(self, metrics: dict):
        """Обрабатывает метрики токена и проверяет условия для уведомлений"""
        try:
            if not self.websocket:
                logger.info(f"⏳ Ожидаем подключения WebSocket для {self.token_address[:8]}")
                return
            
            if not metrics:
                logger.warning(f"⚠️ Пустые метрики для {self.token_address[:8]}")
                return
            
            # Инициализируем метрики при первом получении
            if not hasattr(self, 'token_metrics') or not self.token_metrics:
                # Пробуем получить время создания из разных источников
                creation_time = int(metrics.get('marketCreatedAt', 0) or 0)
                if not creation_time and 'firstPool' in metrics:
                    try:
                        created_at_str = metrics['firstPool']['createdAt']
                        creation_time = int(datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").timestamp())
                    except (KeyError, ValueError) as e:
                        logger.warning(f"⚠️ Не удалось распарсить время создания: {e}")
                
                if not creation_time:
                    creation_time = int(time.time())
                    logger.warning(f"⚠️ Используем текущее время для {self.token_address[:8]}")
                
                self.token_metrics = TokenMetrics(self.token_address, creation_time)
                logger.info(f"✨ Инициализированы метрики для {self.token_address[:8]} (создан: {datetime.fromtimestamp(creation_time)})")
            
            # Добавляем метрики в историю
            self.token_metrics.add_metrics(metrics)
            
            # Получаем рост
            growth = self.token_metrics.get_growth_rates()
            
            # Безопасно получаем значения
            total_holders = int(metrics.get('total_holders', 0) or 0)
            total_bundlers = int(metrics.get('totalBundlesCount', 0) or 0)
            liquidity = float(metrics.get('liquidityInUsdUi', 0) or 0)
            market_cap = float(metrics.get('marketCapUsdUi', 0) or 0)
            
            # Получаем проценты владения
            dev_percent = float(metrics.get('devHoldingPcnt', 0) or 0)
            
            bundles_percent = metrics.get('bundlesHoldingPcnt', 0)
            if isinstance(bundles_percent, dict):
                bundles_percent = float(bundles_percent.get('current', 0) or 0)
            else:
                bundles_percent = float(bundles_percent or 0)
            
            snipers_percent = float(metrics.get('snipersHoldingPcnt', 0) or 0)
            insiders_percent = float(metrics.get('insidersHoldingPcnt', 0) or 0)
            
            snipers_count = int(metrics.get('totalSnipers', 0) or 0)
            
            # Получаем данные о новых кошельках
            fresh_wallets_data = metrics.get('freshWalletBuys', {}) or {}
            fresh_wallets = int(fresh_wallets_data.get('count', 0) or 0)
            fresh_wallets_sol = float(fresh_wallets_data.get('sol', 0) or 0)

            top10holders = metrics.get("top10holders", {})
            top10HoldersPcnt = 0
            top10Holders = ""
            available_liquidity = 0

            sorted_holders = sorted(
                top10holders.items(),
                key=lambda item: item[1]['pcnt'],
                reverse=True  # Сортировка по убыванию (от большего % к меньшему)
            )

            total_pcnt_holders = 0
            max_holders_pcnt = 0
            top_10_holders = ""
            top_10_holders_total_pcnt = 0
            index = 0

            average_holders_pcnt = 0
            average_top_10_holders_pcnt = 0

            for wallet, value in sorted_holders:
                if value['isPool']:
                    logger.info(f"🔎 Обнаружена незаполненная ликвидность {wallet} на {value['pcnt']}%")
                    available_liquidity = value['pcnt']
                    continue
                total_pcnt_holders += value['pcnt']
                if value['isBundler']:
                    logger.info(f"⚠️ Обнаружен бандлер {wallet} среди холдлеров имеющий {value['pcnt']}%")
                    continue
                if value['insider']:
                    logger.info(f"⚠️ Обнаружен инсайдер {wallet} среди холдлеров имеющий {value['pcnt']}%")
                    continue
                if value['pcnt'] > max_holders_pcnt:
                    max_holders_pcnt = value['pcnt']
                top10HoldersPcnt += value['pcnt'] or 0
                top10Holders += f"{round(value['pcnt'] or 0, 2)}% "
                average_holders_pcnt += value['pcnt'] or 0
                if index < 10:
                    top_10_holders += f"{round(value['pcnt'] or 0, 2)}% "
                    top_10_holders_total_pcnt += value['pcnt'] or 0
                    average_top_10_holders_pcnt += value['pcnt'] or 0
                    index += 1

            average_holders_pcnt = average_holders_pcnt / len(sorted_holders)
            average_top_10_holders_pcnt = average_top_10_holders_pcnt / 10

            # Логируем текущие значения
            logger.info(f"\n📊 АНАЛИЗ МЕТРИК для {self.token_address[:8]}:")
            logger.info(f"⏰ Возраст: {(int(time.time()) - metrics.get('marketCreatedAt', 0))} сек")
            logger.info(f"🔎 Незаполненная ликвидность: {round(available_liquidity, 2)}%")
            logger.info(f"👥 Холдеры: {total_holders}")
            logger.info(f"🏆 Холдеры держат: {top10HoldersPcnt:.1f}% ({total_pcnt_holders:.1f}%)")
            logger.info(f"🏆 Проценты держателей: {top10Holders}")
            logger.info(f"🏆 Средний процент держателей: {average_holders_pcnt:.1f}%")
            logger.info(f"🏆 ТОП-10: {top_10_holders_total_pcnt:.1f}% ({top_10_holders})")
            logger.info(f"🏆 Средний процент ТОП-10: {average_top_10_holders_pcnt:.1f}%")
            logger.info(f"📦 Бандлеры: {total_bundlers} ({bundles_percent:.1f}%)")
            logger.info(f"👨‍💼 Dev %: {dev_percent:.1f}%")
            logger.info(f"💧 Ликвидность: ${liquidity:,.2f}")
            logger.info(f"💰 Market Cap: ${market_cap:,.2f}")
            logger.info(f"🆕 Fresh Wallets: {fresh_wallets} ({fresh_wallets_sol:.2f} SOL)")
            logger.info(f"🎯 Снайперы: {snipers_percent:.1f}% ({snipers_count})")
            logger.info(f"👨‍💼 Инсайдеры: {insiders_percent:.1f}%")
            
            logger.info(f"📈 ДИНАМИКА РОСТА:")
            logger.info(f"👥 Холдеры: +{growth['holders_growth']:.2f}/мин")
            logger.info(f"📦 Бандлеры: +{growth['bundlers_growth']:.2f}/мин")
            logger.info(f"💰 Цена: +${growth['price_growth']:.8f}/мин")
            
            activity_conditions = {
                'time_ok': (int(time.time()) - metrics.get('marketCreatedAt', 0)) < 120,
                # Базовые условия по холдерам
                'holders_min': total_holders >= 30,  # Минимум 30 холдеров
                'holders_max': total_holders <= 100,  # Максимум 100 холдеров
                'available_liquidity': available_liquidity < 70,
                # 'max_top_10_holders_pcnt': top10HoldersPcnt < 35,
                'holders_never_dumped': (
                    self.token_metrics.max_holders <= 140  # Никогда не было больше 140 холдеров
                ),
                'max_holders_pcnt': 0 < max_holders_pcnt <= 7,
                # Условия по бандлерам
                'bundlers_ok': (
                    self.token_metrics.max_bundlers_after_dev_exit >= 5 and  # Процент бандлеров после выхода дева >= 5%
                    self.token_metrics.max_bundlers_after_dev_exit <= 50  # Но не больше 50% (избегаем слишком высокой концентрации)
                ),
                'bundlers_before_dev_ok': (
                    self.token_metrics.max_bundlers_before_dev_exit <= 50  # Максимум 50% бандлеров до выхода дева
                ),
                # Условия по деву
                'dev_percent_ok': (
                    dev_percent <= 2 and  # Текущий процент дева <= 2%
                    self.token_metrics.max_dev_percent <= 30  # Максимальный процент тоже <= 30%
                ),
                
                # Условия по снайперам
                'snipers_ok': (
                    snipers_count <= 20 and  # Не более 20 снайперов
                    (
                        snipers_percent <= 3.5 or  # Либо текущий процент <= 3.5%
                        (
                            any(float(m.get('snipersHoldingPcnt', 0) or 0) > 0 for m in self.token_metrics.metrics_history) and
                            max(float(m.get('snipersHoldingPcnt', 0) or 0) 
                                for m in self.token_metrics.metrics_history 
                                if float(m.get('snipersHoldingPcnt', 0) or 0) > 0) > snipers_percent and
                            snipers_percent <= 8.0 and  # Но не больше 8% в текущий момент
                            self.token_metrics.check_rapid_exit('snipersHoldingPcnt', ratio=2.5, max_seconds=120)  # Более строгий rapid exit
                        )
                    )
                ),
                'snipers_not_bundlers': self.token_metrics.check_snipers_bundlers_correlation(),  # Проверка что снайперы не являются бандлерами

                # Условия по инсайдерам
                'insiders_ok': (
                    insiders_percent <= 15 or  # Либо текущий процент <= 15%
                    (
                        any(float(m.get('insidersHoldingPcnt', 0) or 0) > 0 for m in self.token_metrics.metrics_history) and
                        max(float(m.get('insidersHoldingPcnt', 0) or 0) 
                            for m in self.token_metrics.metrics_history 
                            if float(m.get('insidersHoldingPcnt', 0) or 0) > 0) > insiders_percent and
                        insiders_percent <= 22.0 and  # Но не больше 22% в текущий момент
                        self.token_metrics.check_rapid_exit('insidersHoldingPcnt', ratio=2.5, max_seconds=120)  # Более строгий rapid exit
                    )
                ),

                # Условия по ликвидности и росту
                'min_liquidity': liquidity >= 10000,
                'holders_growth': growth['holders_growth'] >= 2900,  # Рост холдеров ≥2900/мин

                # Проверка возможности уведомления
                'can_notify': self.token_metrics.can_send_notification('active'),

                'snipers_not_insiders': self.token_metrics.check_snipers_insiders_correlation(),
                'bundlers_snipers_exit_not_correlated': self.token_metrics.check_bundlers_snipers_exit_correlation(),
            }

            if all(activity_conditions.values()):
                logger.info(f"🚀 АКТИВНОСТЬ ТОКЕНА НАЙДЕНА: {self.token_address[:8]}")
                logger.info("✅ Все условия выполнены:")
                for condition, value in activity_conditions.items():
                    logger.info(f"  • {condition}: {value}")
                await self.send_activity_notification(metrics, growth)
            else:
                logger.info("❌ Не соответствует условиям активности:")
                for condition, value in activity_conditions.items():
                    if not value:
                        logger.info(f"  • {condition}: {value}")
            
            # 2. Сигнал помпа (быстрый рост)
            pump_conditions = {
                'holders_growth': growth['holders_growth'] > 0.5,
                'price_growth': growth['price_growth'] > 0,
                'activity_ok': (
                    total_bundlers > 0 or           # Есть бандлеры
                    fresh_wallets >= 5 or           # Много новых кошельков
                    fresh_wallets_sol >= 2.0        # Большие покупки от новых
                ),
                'min_liquidity': liquidity >= 20000,
                'min_mcap': market_cap >= 50000,
                'can_notify': self.token_metrics.can_send_notification('pump')
            }
            
            if all(pump_conditions.values()):
                logger.info(f"🔥 БЫСТРЫЙ РОСТ НАЙДЕН: {self.token_address[:8]}")
                logger.info("✅ Все условия выполнены:")
                for condition, value in pump_conditions.items():
                    logger.info(f"  • {condition}: {value}")
                await self.send_pump_notification(metrics, growth)
            else:
                logger.info("❌ Не соответствует условиям помпа:")
                for condition, value in pump_conditions.items():
                    if not value:
                        logger.info(f"  • {condition}: {value}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки метрик для {self.token_address[:8]}: {e}")
            logger.error(traceback.format_exc())
    

    async def send_activity_notification(self, metrics: dict, growth: dict):
        """Отправляет уведомление о начале активности"""
        # Проверяем, не отправляли ли мы уже уведомление для этого токена
        if self.token_address in SENT_NOTIFICATIONS:
            last_activity = SENT_NOTIFICATIONS[self.token_address].get('activity', 0)
            if time.time() - last_activity < 900:  # 15 минут между повторными уведомлениями
                logger.info(f"⏳ Пропускаем уведомление об активности для {self.token_address[:8]} (слишком рано)")
                return

        message = (
            f"🚀 <b>НАЧАЛО АКТИВНОСТИ!</b>\n\n"
            f"🪙 <b>{metrics.get('name', 'Unknown')}</b> ({metrics.get('symbol', 'UNK')})\n"
            f"📍 <b>Контракт:</b> <code>{self.token_address}</code>\n\n"
            
            f"📊 <b>МЕТРИКИ:</b>\n"
            f"👥 <b>Холдеры:</b> {metrics.get('total_holders', 0)}\n"
            f"📈 <b>Рост холдеров:</b> {self.safe_format(growth.get('holders_growth'), '.1f')}/мин\n"
            f"📦 <b>Бандлеры:</b> {metrics.get('totalBundlesCount', 0)} ({self.safe_format(metrics.get('bundlesHoldingPcnt', {}).get('current', 0), '.1f')}%)\n"
            f"💰 <b>SOL в бандлах:</b> {self.safe_format(metrics.get('totalSolSpentInBundles'), '.2f')}\n"
            f"🆕 <b>Fresh Wallets:</b> {(metrics.get('freshWalletBuys', {}) or {}).get('count', 0)}\n"
            f"💵 <b>Цена:</b> ${self.safe_format(metrics.get('basePriceInUsdUi'), ',.8f')}\n\n"
            
            f"⚡ <b>СИГНАЛЫ:</b>\n"
            f"✅ Первые бандлеры\n"
            f"✅ Покупки с новых кошельков\n"
            f"✅ Активный рост холдеров"
        )
        
        keyboard = [
            [
                {"text": "🚀 Axiom", "url": f"https://axiom.trade/t/{self.token_address}"},
                {"text": "🚀 DexScreener", "url": f"https://dexscreener.com/solana/{self.token_address}"}
            ],
            [
                {"text": "QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{self.token_address}"}
            ]
        ]
        
        if await self.send_telegram_message(message, keyboard):
            # Сохраняем время отправки
            if self.token_address not in SENT_NOTIFICATIONS:
                SENT_NOTIFICATIONS[self.token_address] = {}
            SENT_NOTIFICATIONS[self.token_address]['activity'] = time.time()
            logger.info(f"📢 Отправлено уведомление о начале активности для {self.token_address[:8]}")
    
    async def send_pump_notification(self, metrics: dict, growth: dict):
        """Отправляет уведомление о начале помпа"""
        # Проверяем, не отправляли ли мы уже уведомление для этого токена
        if self.token_address in SENT_NOTIFICATIONS:
            last_pump = SENT_NOTIFICATIONS[self.token_address].get('pump', 0)
            if time.time() - last_pump < 300:  # 5 минут между повторными уведомлениями
                logger.info(f"⏳ Пропускаем уведомление о помпе для {self.token_address[:8]} (слишком рано)")
                return

        message = (
            f"🔥 <b>СИЛЬНЫЙ РОСТ!</b>\n\n"
            f"🪙 <b>{metrics.get('name', 'Unknown')}</b> ({metrics.get('symbol', 'UNK')})\n"
            f"📍 <b>Контракт:</b> <code>{self.token_address}</code>\n\n"
            
            f"📊 <b>МЕТРИКИ РОСТА:</b>\n"
            f"👥 <b>Холдеры:</b> +{self.safe_format(growth.get('holders_growth'), '.1f')}/мин\n"
            f"📦 <b>Бандлеры:</b> +{self.safe_format(growth.get('bundlers_growth'), '.1f')}/мин\n"
            f"💰 <b>Цена:</b> +${self.safe_format(growth.get('price_growth'), ',.8f')}/мин\n\n"
            
            f"📈 <b>ТЕКУЩИЕ ДАННЫЕ:</b>\n"
            f"👥 <b>Всего холдеров:</b> {metrics.get('total_holders', 0)}\n"
            f"📦 <b>Всего бандлеров:</b> {metrics.get('totalBundlesCount', 0)}\n"
            f"💵 <b>Текущая цена:</b> ${self.safe_format(metrics.get('basePriceInUsdUi'), ',.8f')}\n"
            f"💰 <b>SOL в бандлах:</b> {self.safe_format(metrics.get('totalSolSpentInBundles'), '.2f')}\n"
            f"🆕 <b>Fresh Wallets:</b> {(metrics.get('freshWalletBuys', {}) or {}).get('count', 0)}"
        )
        
        keyboard = [
            [
                {"text": "🚀 Axiom", "url": f"https://axiom.trade/t/{self.token_address}"},
                {"text": "🚀 Padre GG", "url": f"https://trade.padre.gg/trade/solana/{self.token_address}"}
            ],
        ]
        
        if await self.send_telegram_message(message, keyboard):
            # Сохраняем время отправки
            if self.token_address not in SENT_NOTIFICATIONS:
                SENT_NOTIFICATIONS[self.token_address] = {}
            SENT_NOTIFICATIONS[self.token_address]['pump'] = time.time()
            logger.info(f"📢 Отправлено уведомление о сильном росте для {self.token_address[:8]}")
    
    async def process_jupiter_token(self, token_data: dict):
        """Обрабатывает новый токен из Jupiter"""
        try:
            if token_data.get('type') != 'new':
                return
            
            pool = token_data.get('pool', {})
            base_asset = pool.get('baseAsset', {})
            token_address = base_asset.get('id')
            
            if not token_address:
                logger.warning("⚠️ Нет адреса токена в данных Jupiter")
                return
            
            # Получаем время создания
            created_at = None
            try:
                if 'createdAt' in pool:
                    created_at = int(datetime.strptime(pool['createdAt'], "%Y-%m-%dT%H:%M:%SZ").timestamp())
                elif 'firstPool' in base_asset and 'createdAt' in base_asset['firstPool']:
                    created_at = int(datetime.strptime(base_asset['firstPool']['createdAt'], "%Y-%m-%dT%H:%M:%SZ").timestamp())
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка парсинга времени создания: {e}")
            
            symbol = base_asset.get('symbol', 'UNK')
            name = base_asset.get('name', 'Unknown Token')
            
            logger.info(f"🆕 Новый токен из Jupiter: {name} ({token_address[:8]}...)")
            
            # Сохраняем базовую информацию в кеш
            if token_address not in self.token_data_cache:
                self.token_data_cache[token_address] = {
                    'symbol': symbol,
                    'name': name,
                    'marketCreatedAt': created_at,
                    'total_holders': 0,
                    'devHoldingPcnt': 0,
                    'tradingAppTxns': 0,
                    'freshWalletBuys': {'count': 0, 'sol': 0},
                    'insidersHoldingPcnt': 0,
                    'totalSnipers': 0,
                    'bundlesHoldingPcnt': {'current': 0, 'ath': 0},
                    'totalBundlesCount': 0,
                    'totalSolSpentInBundles': 0,
                    'totalTokenBoughtInBundles': 0,
                    'totalSolFees': 0,
                    'snipersHoldingPcnt': 0
                }
            
            logger.info(f"🔍 Добавляем токен {name} ({token_address[:8]}) для анализа бандлеров")
            
            # Создаем новое соединение для токена
            await self.padre_manager.add_token(token_address)
            logger.info(f"📡 Используем Padre соединение default_{token_address[:8]} для токена {name}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Jupiter токена: {e}")
            logger.error(traceback.format_exc())

class MultiplePadreManager:
    """Менеджер для управления множеством Padre WebSocket соединений"""
    
    def __init__(self, connection_interval: float = 30.0):
        self.connection_interval = connection_interval
        self.active_connections: Dict[str, PadreWebSocketClient] = {}  # {token_address: client}
        self.connection_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self.next_connection_time = 0
        self.cleanup_task = None
        
        logger.info(f"🔗 Инициализирован MultiplePadreManager: без лимита соединений, тайм-аут 10 минут")
    
    async def start(self):
        """Запускает менеджер соединений"""
        self.running = True
        # Запускаем задачу очистки истекших соединений
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ MultiplePadreManager запущен")
    
    async def stop(self):
        """Останавливает все соединения и менеджер"""
        self.running = False
        
        # Отменяем задачу очистки
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Закрываем все активные соединения
        for token_address in list(self.active_connections.keys()):
            await self._remove_connection(token_address, reason="остановка менеджера")
        
        logger.info("✅ MultiplePadreManager остановлен")
    
    async def _cleanup_loop(self):
        """Периодически проверяет и закрывает истекшие соединения"""
        try:
            while self.running:
                current_time = asyncio.get_event_loop().time()
                
                # Проверяем все соединения
                for token_address, client in list(self.active_connections.items()):
                    if client.is_connection_expired():
                        logger.info(f"⏰ Обнаружено истекшее соединение для {token_address[:8]}")
                        await self._remove_connection(token_address, reason="тайм-аут 10 минут")
                
                # Логируем статистику каждые 30 секунд
                if int(current_time) % 30 == 0:
                    active_count = len(self.active_connections)
                    if active_count > 0:
                        logger.info(f"📊 Активных соединений: {active_count}")
                        # Показываем оставшееся время для каждого соединения
                        for token_address, client in self.active_connections.items():
                            remaining = client.get_remaining_time()
                            logger.info(f"⏳ {token_address[:8]}: {remaining/60:.1f}м осталось")
                
                await asyncio.sleep(10)  # Проверяем каждые 10 секунд
                
        except asyncio.CancelledError:
            logger.info("🛑 Задача очистки соединений остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка в задаче очистки соединений: {e}")
    
    async def add_token(self, token_address: str) -> Optional[PadreWebSocketClient]:
        """Добавляет новый токен для отслеживания"""
        try:
            # Проверяем, нет ли уже соединения для этого токена
            if token_address in self.active_connections:
                logger.info(f"✅ Соединение для токена {token_address[:8]} уже существует")
                return self.active_connections[token_address]
            
            # Создаем новое соединение
            client = PadreWebSocketClient(token_address=token_address)
            
            # Запускаем клиент в отдельной задаче
            task = asyncio.create_task(client.start())
            
            # Сохраняем ссылки
            self.active_connections[token_address] = client
            self.connection_tasks[token_address] = task
            
            logger.info(f"➕ Создано новое Padre соединение для токена {token_address[:8]}")
            logger.info(f"📊 Активных соединений: {len(self.active_connections)}")
            
            return client
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания соединения для токена {token_address[:8]}: {e}")
            return None

    async def _remove_connection(self, token_address: str, reason: str):
        """Удаляет соединение для данного токена"""
        try:
            logger.info(f"🔌 Удаляем соединение для {token_address[:8]} из-за {reason}")
            del self.active_connections[token_address]
            del self.connection_tasks[token_address]
        except Exception as e:
            logger.error(f"❌ Ошибка удаления соединения для {token_address[:8]}: {e}")

class TokenMonitor:
    """Монитор новых токенов из pump_bot.py"""
    
    def __init__(self, padre_manager: MultiplePadreManager):
        self.padre_manager = padre_manager
        
    async def add_token_for_analysis(self, token_data: dict):
        """Добавляем токен для анализа бандлеров"""
        try:
            contract_address = token_data.get('mint', token_data.get('address'))
            
            if not contract_address:
                logger.warning("⚠️ Токен без адреса контракта")
                return
            
            symbol = token_data.get('symbol', 'UNK')
            logger.info(f"🔍 Добавляем токен {symbol} ({contract_address[:8]}) для анализа бандлеров")
            
            # Создаем новое соединение для токена
            client = await self.padre_manager.add_token(contract_address)
            
            if client:
                # Подписываемся на данные токена
                logger.info(f"📡 Используем Padre соединение {client.connection_id} для токена {symbol}")
                # await client.subscribe_to_token_data(contract_address)
            else:
                # Симулируем анализ бандлеров без активного padre соединения
                logger.info(f"🎲 Не удалось создать Padre соединение, симулируем анализ для {symbol}")
                await self.simulate_bundler_analysis(contract_address, token_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления токена для анализа: {e}")
    
    async def simulate_bundler_analysis(self, contract_address: str, token_data: dict):
        """Симулируем анализ бандлеров с рандомными данными"""
        try:
            import random
            
            # Генерируем случайные данные о бандлерах
            bundler_count = random.randint(50, 300)
            bundler_percentage = (bundler_count / 1000) * 100  # Предполагаем 1000 общих холдеров
            
            symbol = token_data.get('symbol', 'UNK')
            logger.info(f"🎯 Симуляция: {symbol} имеет {bundler_count} бандлеров ({bundler_percentage:.1f}%)")
            
            # Если процент выше минимального, отправляем уведомление
            if bundler_percentage >= MIN_BUNDLER_PERCENTAGE:
                await self.send_bundler_notification(contract_address, token_data, bundler_count, bundler_percentage, simulated=True)
                
            # Убираем из очереди ожидания
            if contract_address in pending_tokens:
                del pending_tokens[contract_address]
                
        except Exception as e:
            logger.error(f"❌ Ошибка симуляции анализа бандлеров: {e}")
    
    async def send_bundler_notification(self, contract_address: str, token_data: dict, bundler_count: int, bundler_percentage: float, simulated: bool = False):
        """Отправляем уведомление о токене с высоким процентом бандлеров"""
        try:
            symbol = token_data.get('symbol', 'UNK')
            name = token_data.get('name', symbol)
            dex_source = token_data.get('dex_source', 'Unknown')
            market_cap = token_data.get('market_cap', 0)
            
            sim_tag = " 🎲 [СИМУЛЯЦИЯ]" if simulated else ""
            
            message = (
                f"🚨 <b>ВЫСОКИЙ ПРОЦЕНТ БАНДЛЕРОВ!{sim_tag}</b>\n\n"
                f"🪙 <b>{name}</b> ({symbol})\n"
                f"📍 <b>Контракт:</b> <code>{contract_address}</code>\n"
                f"📊 <b>Бандлеры:</b> {bundler_count} ({bundler_percentage:.1f}%)\n"
                f"💰 <b>Market Cap:</b> ${market_cap:,.0f}\n"
                f"🏪 <b>DEX:</b> {dex_source}\n\n"
                f"⚡ <b>Мин. порог:</b> {MIN_BUNDLER_PERCENTAGE}%\n"
                f"🎯 <b>Результат:</b> Превышен на {bundler_percentage - MIN_BUNDLER_PERCENTAGE:.1f}%"
            )
            
            # Создаем кнопки для быстрых действий
            keyboard = [
                [
                    {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{contract_address}"},
                    {"text": "🚀 Pump.fun", "url": f"https://pump.fun/{contract_address}"}
                ],
                [{"text": "💎 Jupiter", "url": f"https://jup.ag/swap/SOL-{contract_address}"}]
            ]
            
            success = await self.send_telegram_message(message, keyboard)
            
            if success:
                logger.info(f"✅ Отправлено уведомление о токене {symbol} с {bundler_percentage:.1f}% бандлеров")
            else:
                logger.warning(f"⚠️ Не удалось отправить уведомление о токене {symbol}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления о бандлерах: {e}")
    
    async def send_telegram_message(self, message: str, keyboard: List[List[Dict[str, str]]] = None) -> bool:
        """Отправляем сообщение в Telegram с задержкой при необходимости"""
        try:
            # Проверяем, не слишком ли часто отправляем
            current_time = time.time()
            if hasattr(self, 'last_telegram_time'):
                time_since_last = current_time - self.last_telegram_time
                if time_since_last < 3:  # Минимум 3 секунды между сообщениями
                    await asyncio.sleep(3 - time_since_last)
            
            # Отправляем сообщение
            chat_id = "-1002680160752"  # ID чата
            thread_id = "13134"  # ID треда
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"  # Используем глобальную константу
            
            data = {
                "chat_id": chat_id,
                "message_thread_id": thread_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            if keyboard:
                data["reply_markup"] = {"inline_keyboard": keyboard}
            
            logger.info(f"📤 Отправляем в Telegram: chat={chat_id}, thread={thread_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = (await response.json()).get('parameters', {}).get('retry_after', 30)
                        logger.warning(f"⚠️ Слишком много запросов к Telegram API. Ждем {retry_after} сек.")
                        await asyncio.sleep(retry_after)
                        # Пробуем отправить еще раз
                        async with session.post(url, json=data) as retry_response:
                            if retry_response.status != 200:
                                logger.error(f"❌ Ошибка Telegram API: {response.status} - {await response.text()}")
                                return False
                    elif response.status != 200:
                        logger.error(f"❌ Ошибка Telegram API: {response.status} - {await response.text()}")
                        return False
                        
            # Сохраняем время последней отправки
            self.last_telegram_time = time.time()
            logger.info("✅ Сообщение успешно отправлено в Telegram")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в Telegram: {e}")
            return False

async def main():
    """Основная функция"""
    logger.info("🚀 Запускаем Bundle Analyzer для A/B тестов...")
    logger.info(f"⚙️ Минимальный процент бандлеров: {MIN_BUNDLER_PERCENTAGE}%")
    
    # Создаем менеджер соединений (интервал 30 секунд между новыми соединениями)
    padre_manager = MultiplePadreManager(connection_interval=30.0)
    token_monitor = TokenMonitor(padre_manager)
    
    try:
        # Запускаем менеджер соединений
        logger.info("🔗 Запускаем менеджер Padre соединений...")
        await padre_manager.start()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        # Останавливаем все соединения
        await padre_manager.stop()
        logger.info("✅ Bundle Analyzer остановлен")

if __name__ == "__main__":
    # Проверяем переменные окружения
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("❌ Не установлен TELEGRAM_TOKEN!")
        sys.exit(1)
    
    # Запускаем
    asyncio.run(main()) 