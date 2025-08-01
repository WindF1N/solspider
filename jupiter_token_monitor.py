#!/usr/bin/env python3
"""
Jupiter Token Monitor - Мониторинг новых токенов через Jupiter WebSocket
Интегрирован с Padre WebSocket для получения данных о бандлерах и холдерах
"""

import asyncio
import json
import logging
import websockets
import ssl
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass
from token_behavior_monitor import TokenBehaviorMonitor
from padre_websocket_client import ImprovedPadreClient, BundlerDataExtractor, PadreMessageDecoder
import base64
from datetime import datetime
import random

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('token_behavior_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class TokenBundlerData:
    """Данные о бандлерах токена"""
    mint_address: str
    symbol: str
    bundler_count: int = 0
    total_holders: int = 0
    bundler_percentage: float = 0.0
    market_cap: Optional[float] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    trade_count: Optional[int] = None
    suspicious_patterns: list = None
    
    def __post_init__(self):
        if self.suspicious_patterns is None:
            self.suspicious_patterns = []

class PadreTokenDataCollector:
    """Собирает данные о токенах через Padre WebSocket"""
    
    def __init__(self):
        self.padre_client = None
        self.message_decoder = PadreMessageDecoder()
        self.bundler_extractor = BundlerDataExtractor()
        self.pending_tokens = {}  # mint -> TokenBundlerData
        self.data_callbacks = []  # callbacks для обработки полученных данных
        self.running = False
        
    def add_data_callback(self, callback):
        """Добавляет callback для обработки данных о токенах"""
        self.data_callbacks.append(callback)
        
    async def start(self):
        """Запускает Padre WebSocket клиент"""
        try:
            self.running = True
            self.padre_client = ImprovedPadreClient()
            
            # Переопределяем метод обработки данных бандлеров
            self.padre_client.process_bundler_data = self._process_padre_bundler_data
            
            logger.info("🔗 Запускаем Padre WebSocket клиент для сбора данных...")
            await self.padre_client.start()
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Padre клиента: {e}")
            
    async def stop(self):
        """Останавливает клиент"""
        self.running = False
        if self.padre_client:
            await self.padre_client.stop()
            
    async def request_token_data(self, mint_address: str, symbol: str):
        """Запрашивает данные о токене через Padre"""
        try:
            # Создаем запись для ожидания данных
            token_data = TokenBundlerData(
                mint_address=mint_address,
                symbol=symbol
            )
            self.pending_tokens[mint_address] = token_data
            
            # Отправляем запрос через Padre WebSocket
            await self._send_token_request(mint_address)
            
            logger.info(f"📤 Запросили данные для токена {symbol} ({mint_address[:8]}...)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запроса данных токена {symbol}: {e}")
            
    async def _send_token_request(self, mint_address: str):
        """Отправляет запрос данных токена через Padre WebSocket"""
        try:
            if not self.padre_client or not self.padre_client.websocket:
                logger.warning("⚠️ Padre WebSocket не подключен")
                return
                
            # Формируем запрос для конкретного токена
            # Формат URL аналогичен тому что в браузере
            request_url = f"/trade/solana/{mint_address}"
            encoded_request = base64.b64encode(request_url.encode()).decode()
            
            await self.padre_client.websocket.send(encoded_request.encode())
            logger.debug(f"📤 Отправлен запрос данных для {mint_address[:8]}...")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки запроса для {mint_address}: {e}")
            
    async def _process_padre_bundler_data(self, bundler_info: dict):
        """Обрабатывает данные о бандлерах от Padre"""
        try:
            contract_address = bundler_info.get('contract_address')
            if not contract_address:
                return
                
            # Проверяем есть ли токен в ожидании
            if contract_address not in self.pending_tokens:
                # Возможно данные пришли для неизвестного токена
                logger.debug(f"🔍 Получены данные для неизвестного токена {contract_address[:8]}...")
                return
                
            # Обновляем данные токена
            token_data = self.pending_tokens[contract_address]
            token_data.bundler_count = bundler_info.get('bundler_count', 0)
            token_data.market_cap = bundler_info.get('market_cap')
            token_data.price = bundler_info.get('price')
            token_data.volume = bundler_info.get('volume')
            token_data.trade_count = bundler_info.get('trade_count')
            
            # Рассчитываем процент бандлеров
            if token_data.bundler_count > 0:
                token_data.bundler_percentage = self.bundler_extractor.calculate_bundler_percentage(
                    token_data.bundler_count,
                    token_data.total_holders
                )
            
            # Анализируем подозрительные паттерны
            await self._analyze_suspicious_patterns(token_data)
            
            logger.info(f"📊 Получены данные для {token_data.symbol}: "
                       f"🤖 Бандлеры: {token_data.bundler_count} ({token_data.bundler_percentage:.1f}%)")
            
            # Вызываем callbacks
            for callback in self.data_callbacks:
                try:
                    await callback(token_data)
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback: {e}")
            
            # Удаляем из ожидания
            del self.pending_tokens[contract_address]
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки данных бандлеров: {e}")
            
    async def _analyze_suspicious_patterns(self, token_data: TokenBundlerData):
        """Анализирует подозрительные паттерны"""
        try:
            patterns = []
            
            # Высокий процент бандлеров
            if token_data.bundler_percentage >= 20.0:
                patterns.append(f"🤖 Высокий % бандлеров: {token_data.bundler_percentage:.1f}%")
                
            # Подозрительно низкое количество сделок при высоком количестве держателей
            if (token_data.trade_count and token_data.bundler_count and 
                token_data.trade_count < token_data.bundler_count * 2):
                patterns.append("📉 Мало сделок при многих держателях")
                
            # Странное соотношение объема к капитализации
            if (token_data.volume and token_data.market_cap and 
                token_data.volume > token_data.market_cap * 5):
                patterns.append("💰 Подозрительно высокий объем")
                
            token_data.suspicious_patterns = patterns
            
            if patterns:
                logger.warning(f"🚨 ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ в {token_data.symbol}!")
                for pattern in patterns:
                    logger.warning(f"   {pattern}")
                logger.warning("🎯 Возможно volume bot marketing!")
                
        except Exception as e:
            logger.error(f"❌ Ошибка анализа паттернов: {e}")

class JupiterTokenMonitor:
    """Мониторинг новых токенов через Jupiter WebSocket с интеграцией Padre"""
    
    def __init__(self):
        self.active_monitors = {}  # mint -> task
        self.monitor_instances = {}  # mint -> TokenBehaviorMonitor
        self.successful_monitors = 0
        self.failed_monitors = 0
        self.processed_tokens = 0
        
        # Интеграция с Padre для получения данных о бандлерах
        self.padre_collector = PadreTokenDataCollector()
        self.padre_collector.add_data_callback(self._handle_padre_token_data)
        
    async def start_padre_collector(self):
        """Запускает Padre WebSocket клиент в фоновом режиме"""
        try:
            # Запускаем Padre клиент в отдельной задаче
            padre_task = asyncio.create_task(self.padre_collector.start())
            logger.info("🔗 Padre WebSocket клиент запущен в фоновом режиме")
            
            # Даем время на подключение
            await asyncio.sleep(3)
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Padre клиента: {e}")
    
    async def _handle_padre_token_data(self, token_data: TokenBundlerData):
        """Обрабатывает данные о токене от Padre"""
        try:
            # Логируем полученные данные
            logger.info(f"📊 Данные от Padre для {token_data.symbol}:")
            logger.info(f"   🤖 Бандлеры: {token_data.bundler_count} ({token_data.bundler_percentage:.1f}%)")
            
            if token_data.market_cap:
                logger.info(f"   💰 Market Cap: ${token_data.market_cap:,.0f}")
            if token_data.volume:
                logger.info(f"   📈 Volume: ${token_data.volume:,.0f}")
            if token_data.trade_count:
                logger.info(f"   🔄 Trades: {token_data.trade_count}")
                
            # Если есть подозрительные паттерны - отправляем уведомления
            if token_data.suspicious_patterns:
                await self._send_bundler_alert(token_data)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки данных от Padre: {e}")
    
    async def _send_bundler_alert(self, token_data: TokenBundlerData):
        """Отправляет уведомление о подозрительной активности"""
        try:
            alert_message = f"🚨 ПОДОЗРИТЕЛЬНЫЙ ТОКЕН: {token_data.symbol}\n"
            alert_message += f"📍 Mint: {token_data.mint_address}\n"
            alert_message += f"🤖 Бандлеры: {token_data.bundler_count} ({token_data.bundler_percentage:.1f}%)\n"
            
            if token_data.market_cap:
                alert_message += f"💰 Market Cap: ${token_data.market_cap:,.0f}\n"
            
            alert_message += "⚠️ Подозрительные паттерны:\n"
            for pattern in token_data.suspicious_patterns:
                alert_message += f"   • {pattern}\n"
            
            alert_message += "\n🎯 Возможно volume bot marketing!"
            
            logger.warning(alert_message)
            
            # Здесь можно добавить отправку в Telegram
            # await send_telegram_alert(alert_message)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")

    async def start_token_monitoring(self, mint: str, symbol: str, name: str = ""):
        """Запускает мониторинг токена через Padre WebSocket"""
        try:
            if mint in self.active_monitors:
                logger.debug(f"🔄 Токен {symbol} уже мониторится")
                return True
            
            # Запрашиваем данные через Padre
            await self.padre_collector.request_token_data(mint, symbol)
            
            # Создаем задачу мониторинга на 30 секунд
            task = asyncio.create_task(self._monitor_token_padre(mint, symbol, name))
            self.active_monitors[mint] = task
            
            logger.info(f"🎯 Запущен мониторинг токена {symbol} через Padre")
            self.processed_tokens += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска мониторинга {symbol}: {str(e)}")
            self.failed_monitors += 1
            return False
    
    async def _monitor_token_padre(self, mint: str, symbol: str, name: str):
        """Мониторит токен в течение 30 секунд, ожидая данные от Padre"""
        try:
            # Ждем 30 секунд для получения данных от Padre
            await asyncio.sleep(30)
            
            logger.info(f"🎯 Мониторинг {symbol} завершен после 30 секунд")
            self.successful_monitors += 1
            
        except asyncio.CancelledError:
            logger.debug(f"🛑 Мониторинг {symbol} отменен")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга {symbol}: {str(e)}")
            self.failed_monitors += 1
        finally:
            # Очищаем ссылки
            if mint in self.active_monitors:
                del self.active_monitors[mint]
    
    async def stop_token_monitoring(self, mint: str) -> bool:
        """Останавливает мониторинг конкретного токена"""
        try:
            if mint not in self.active_monitors:
                logger.debug(f"⚠️ Токен {mint[:8]}... не мониторится")
                return False
            
            # Отменяем задачу
            task = self.active_monitors[mint]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Удаляем из словаря
            del self.active_monitors[mint]
            if mint in self.monitor_instances:
                del self.monitor_instances[mint]
            
            logger.info(f"🛑 Остановлен мониторинг токена {mint[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки мониторинга {mint[:8]}...: {str(e)}")
            return False
    
    def get_monitoring_stats(self) -> dict:
        """Возвращает статистику мониторинга"""
        return {
            'active_monitors': len(self.active_monitors),
            'total_processed': self.processed_tokens,
            'successful': self.successful_monitors,
            'failed': self.failed_monitors,
            'padre_pending': len(self.padre_collector.pending_tokens) if self.padre_collector else 0
        }
    
    async def handle_new_jupiter_token(self, token_data: dict):
        """Обрабатывает новый токен от Jupiter"""
        try:
            # Извлекаем данные токена
            mint = token_data.get('mint') or token_data.get('id')
            base_asset = token_data.get('baseAsset', {})
            
            if not mint:
                logger.debug("⚠️ Токен без mint адреса")
                return
            
            symbol = base_asset.get('symbol', 'UNK')
            name = base_asset.get('name', '')
            
            # Проверяем фильтрацию
            if not await self._should_monitor_token(token_data):
                logger.info(f"🚫 Токен {symbol} не прошел фильтрацию")
                return
            
            # Запускаем мониторинг через Padre
            await self.start_token_monitoring(mint, symbol, name)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки нового токена: {e}")
    
    async def _should_monitor_token(self, token_data: dict) -> bool:
        """Проверяет должен ли токен мониториться"""
        try:
            base_asset = token_data.get('baseAsset', {})
            
            # Проверяем наличие Twitter
            twitter = base_asset.get('twitter')
            if not twitter or '/status/' in twitter:
                logger.debug(f"🚫 Нет валидного Twitter")
                return False
            
            # Проверяем Market Cap (если есть)
            market_cap = base_asset.get('marketCap', 0)
            if market_cap > 1000000:  # Больше $1M - скорее всего устоявшийся токен
                logger.debug(f"🚫 Market Cap слишком высокий: ${market_cap:,.0f}")
                return False
            
            # Проверяем длину символа
            symbol = base_asset.get('symbol', '')
            if len(symbol) > 20:
                logger.debug(f"🚫 Слишком длинный символ: {symbol}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка фильтрации токена: {e}")
            return False
    
    async def handle_message(self, message: str):
        """Обрабатывает сообщения от Jupiter WebSocket"""
        try:
            data = json.loads(message)
            
            # Ищем данные о новых токенах
            pools = data.get('pools', [])
            
            for pool_data in pools:
                pool_type = pool_data.get('poolType', '')
                
                # Фокусируемся на pump.fun, letsbonk.fun и других интересных пулах
                if any(pt in pool_type.lower() for pt in ['pump', 'bonk', 'flux']):
                    # Логируем новый токен
                    base_asset = pool_data.get('baseAsset', {})
                    symbol = base_asset.get('symbol', 'UNK')
                    name = base_asset.get('name', 'Unknown')
                    mint = pool_data.get('mint') or pool_data.get('id')
                    
                    # Определяем тип пула
                    if 'pumpfun' in pool_type.lower():
                        pool_source = "pump.fun" if pool_type == "pumpfun" else "swap.pump.fun"
                    elif 'bonk' in pool_type.lower():
                        pool_source = "letsbonk.fun"
                    elif 'flux' in pool_type.lower():
                        pool_source = "FluxBeam"
                    else:
                        pool_source = pool_type
                    
                    logger.info(f"🚀 НОВЫЙ ТОКЕН: {name} ({symbol}) через {pool_source}")
                    logger.info(f"   📊 Mint: {mint}")
                    logger.info(f"   🏷️ Тип пула: {pool_type}")
                    
                    # Обрабатываем токен
                    await self.handle_new_jupiter_token(pool_data)
                    
        except json.JSONDecodeError:
            logger.debug("❌ Не удалось декодировать JSON сообщение")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
    
    async def cleanup(self):
        """Очистка ресурсов"""
        try:
            # Останавливаем все активные мониторы
            for mint in list(self.active_monitors.keys()):
                await self.stop_token_monitoring(mint)
            
            # Останавливаем Padre клиент
            if self.padre_collector:
                await self.padre_collector.stop()
                
            logger.info("🧹 Очистка завершена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")

async def main():
    """Основная функция"""
    try:
        # Создаем экземпляр монитора
        jupiter_monitor = JupiterTokenMonitor()
        
        # Запускаем Padre WebSocket клиент в фоновом режиме
        await jupiter_monitor.start_padre_collector()
        
        # Статистика для логирования
        last_stats_time = asyncio.get_event_loop().time()
        
        # Настройки WebSocket соединения
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': 'cf_clearance=example_clearance_token'
        }
        
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            try:
                logger.info(f"🔗 Подключаемся к Jupiter WebSocket (попытка {retry_count + 1}/{max_retries})...")
                
                async with websockets.connect(
                    "wss://trench-stream.jup.ag/ws",
                    ssl=ssl_context,
                    extra_headers=headers,
                    ping_interval=30,
                    ping_timeout=10
                ) as websocket:
                    
                    logger.info("✅ Успешно подключились к Jupiter!")
                    retry_count = 0  # Сбрасываем счетчик при успешном подключении
                    
                    # Подписываемся на события
                    subscribe_recent = json.dumps({"method": "subscribe", "params": ["recent"]})
                    await websocket.send(subscribe_recent)
                    logger.info("📡 Подписались на recent события")
                    
                    # Дополнительная подписка на пулы
                    subscribe_pools = json.dumps({
                        "method": "subscribe", 
                        "params": ["pool:HZ1znC9XBasm9AMDhGocd9EHSyH8Pyj1EUdiPb4WnZjo"]
                    })
                    await websocket.send(subscribe_pools)
                    logger.info("📡 Подписались на pool события")
                    
                    # Основной цикл получения сообщений
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            await jupiter_monitor.handle_message(message)
                            
                            # Логируем статистику каждые 60 секунд
                            current_time = asyncio.get_event_loop().time()
                            if current_time - last_stats_time >= 60:
                                stats = jupiter_monitor.get_monitoring_stats()
                                logger.info(f"📊 Статистика: Активных мониторов: {stats['active_monitors']}, "
                                          f"Обработано: {stats['total_processed']}, "
                                          f"Успешно: {stats['successful']}, "
                                          f"Ошибок: {stats['failed']}, "
                                          f"Ожидают Padre: {stats['padre_pending']}")
                                last_stats_time = current_time
                                
                        except asyncio.TimeoutError:
                            logger.debug("⏱️ Таймаут получения сообщений")
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("🔌 WebSocket соединение закрыто")
                            break
                            
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ Ошибка подключения (попытка {retry_count}): {e}")
                
                if retry_count < max_retries:
                    wait_time = min(2 ** retry_count, 60)  # Экспоненциальная задержка
                    logger.info(f"⏱️ Ждем {wait_time} секунд перед переподключением...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("💥 Превышено максимальное количество попыток подключения")
                    break
                    
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        if 'jupiter_monitor' in locals():
            await jupiter_monitor.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 