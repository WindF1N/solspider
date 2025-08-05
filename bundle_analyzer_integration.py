#!/usr/bin/env python3
"""
Bundle Analyzer Integration Module
Интегрируется с pump_bot.py для получения новых токенов и их анализа на количество бандлеров
"""

import asyncio
import json
import logging
import websockets
import ssl
from datetime import datetime
from typing import Dict, Optional, Any
import os

# Импортируем bundle_analyzer
from bundle_analyzer import MultiplePadreManager, TokenMonitor

# Настройка логирования
logger = logging.getLogger(__name__)



class JupiterTokenListener:
    """Слушатель новых токенов из Jupiter WebSocket (как в pump_bot.py)"""
    
    def __init__(self, token_monitor: TokenMonitor):
        self.token_monitor = token_monitor
        self.websocket = None
        self.running = False
        self.token_gotten = False
        
    async def connect_to_jupiter(self):
        """Подключение к Jupiter WebSocket (логика из pump_bot.py)"""
        try:
            # Правильный URL Jupiter WebSocket из pump_bot.py
            jupiter_ws_url = "wss://trench-stream.jup.ag/ws"
            
            # Создаем SSL контекст для Jupiter (как в pump_bot.py)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Дополнительные заголовки для Jupiter WebSocket с CloudFlare куками (из pump_bot.py)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Origin": "https://jup.ag",
                "Cookie": "cf_clearance=m5O0sYyORJM.bb3A3eQGse7P6aa2c9BLgMOt6tm8Mu8-1750902546-1.2.1.1-eRyDtqC_4lkjfCnREIIEQ2LwdV3qMnJqeI4wGFZQpuYfpbLyKuz44QurDH1nnhmPo8.KF9u1vlQRddXKKWdQu7RfJR17j1kgpQeNYY.jUsbLeIYkwgDGlTRWwMeYD0FVitXxJkK6sMtKIXMVdfsdL.M.shrsRtlhuLmZCfVWjhZ89pZrBn5TpZjB98akJAOSGRl3qnsP352Q77oTOsMdnggp5fjO2wlfXqHY.TAjkHKJ0Frk.EtzUKw1sESan_pPne_jbfJRu4CVKkTi52mko5DFlrC5QuAiCntW0a11t2LSqLLkxcXM6jxDKV5IhHpPq79qXtne2PmwiweC_QucapNUyyA_0bFh33Lx4ahcYRc"
            }
            
            # Определяем параметры подключения в зависимости от версии websockets
            import websockets
            websockets_version = websockets.__version__
            
            # Универсальные параметры подключения с улучшенными настройками
            connect_params = {
                "ssl": ssl_context,
                "close_timeout": 15,
                "max_size": 10**7,
                "max_queue": 32,
            }
            
            # Добавляем заголовки в зависимости от версии
            if int(websockets_version.split('.')[0]) >= 12:
                # Новая версия (12.x+) использует additional_headers
                connect_params["additional_headers"] = headers
            else:
                # Старая версия (11.x и ниже) использует extra_headers
                connect_params["extra_headers"] = headers
            
            # Подключаемся к Jupiter
            self.websocket = await websockets.connect(jupiter_ws_url, **connect_params)
            
            # Подписываемся на recent обновления (как в pump_bot.py)
            recent_msg = {"type": "subscribe:recent"}
            await self.websocket.send(json.dumps(recent_msg))
            logger.debug("✅ Подписались на recent обновления")
            
            await asyncio.sleep(1)
            
            # Подписываемся на пулы (первая группа) - из pump_bot.py
            pools_msg_1 = {
                "type": "subscribe:pool",
                "pools": [
                    "7ydCvqmPj42msz3mm2W28a4hXKaukF7XNpRjNXNhbonk",
                    "29F4jaxGYGCP9oqJxWn7BRrXDCXMQYFEirSHQjhhpump"
                ]
            }
            await self.websocket.send(json.dumps(pools_msg_1))
            logger.debug("✅ Подписались на первую группу пулов")
            
            return True
            
        except Exception as e:
            logger.debug(f"❌ Ошибка подключения к Jupiter: {e}")
            if hasattr(self, 'websocket') and self.websocket:
                try:
                    await self.websocket.close()
                except:
                    pass
                self.websocket = None
            return False
    
    async def listen_for_new_tokens(self):
        """Слушаем новые токены из Jupiter"""
        try:
            while self.running and self.websocket:
                try:
                    # Получаем сообщение от Jupiter WebSocket
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                    
                    # Парсим сообщение
                    token_data = await self.parse_jupiter_message(message)
                    
                    if token_data:
                        # Передаем токен для анализа бандлеров
                        await self.token_monitor.add_token_for_analysis(token_data)
                        
                except asyncio.TimeoutError:
                    logger.debug("⏱️ Таймаут ожидания сообщений Jupiter")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("🔌 Jupiter WebSocket соединение закрыто")
                    break
                except websockets.exceptions.InvalidURI:
                    logger.error("❌ Неверный URI Jupiter WebSocket")
                    break
                except websockets.exceptions.InvalidHandshake:
                    logger.error("❌ Ошибка handshake с Jupiter WebSocket")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки сообщения Jupiter: {e}")
                    # При неизвестной ошибке тоже прерываем цикл для переподключения
                    break
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в основном цикле Jupiter: {e}")
        finally:
            # Закрываем соединение при выходе из цикла
            if hasattr(self, 'websocket') and self.websocket:
                try:
                    await self.websocket.close()
                except:
                    pass
                self.websocket = None
    
    async def parse_jupiter_message(self, message: str) -> Optional[dict]:
        """Парсим сообщение от Jupiter (логика из pump_bot.py)"""
        try:
            data = json.loads(message)
            
            # Проверяем, что это сообщение о новом токене
            # Логика должна соответствовать handle_new_jupiter_token из pump_bot.py
            if data.get('type') == 'updates' and 'data' in data:
                updates = data['data']
                
                for update in updates:
                    update_type = update.get('type')
                    pool_data = update.get('pool', {})

                    if pool_data.get('dex') not in ['pump.fun', 'letsbonk.fun']:
                        continue

                    if update_type == 'new' and pool_data:
                        # Извлекаем данные о токене
                        base_asset = pool_data.get('baseAsset', {})
                        
                        token_data = {
                            'mint': base_asset.get('id', pool_data.get('id')),
                            'symbol': base_asset.get('symbol', 'Unknown'),
                            'name': base_asset.get('name', base_asset.get('symbol', 'Unknown')),
                            'dex_source': pool_data.get('dex', 'Jupiter'),
                            'pool_type': pool_data.get('type', 'Unknown'),
                            'market_cap': base_asset.get('marketCap', 0),
                            'created_timestamp': pool_data.get('createdAt'),
                            'address': base_asset.get('id')  # Дублируем для совместимости
                        }

                        logger.info(f"Дата сет токена Jupiter: {update}")
                        
                        # Проверяем, что у токена есть адрес
                        if token_data.get('mint') and len(token_data['mint']) > 30:
                            logger.info(f"🆕 Новый токен из Jupiter: {token_data['symbol']} ({token_data['mint'][:8]}...)")
                            return token_data
            
            return None
            
        except json.JSONDecodeError:
            logger.debug("🔍 Сообщение от Jupiter не является JSON")
            return None
        except Exception as e:
            logger.debug(f"🔍 Ошибка парсинга сообщения Jupiter: {e}")
            return None
    
    async def start(self):
        """Запускаем слушатель Jupiter с автоматическим переподключением"""
        self.running = True
        
        retry_count = 0
        max_retries = float('inf')  # Бесконечные попытки переподключения
        
        while self.running:
            try:
                retry_count += 1
                logger.info(f"🔗 Подключаемся к Jupiter WebSocket (попытка {retry_count})...")
                
                if await self.connect_to_jupiter():
                    logger.info("✅ Успешно подключились к Jupiter")
                    retry_count = 0  # Сбрасываем счетчик при успешном подключении
                    
                    await self.listen_for_new_tokens()
                    
                    # Если мы здесь, значит соединение было разорвано
                    logger.warning("🔌 Jupiter WebSocket соединение разорвано, переподключаемся...")
                    
                else:
                    logger.error("❌ Не удалось подключиться к Jupiter")
                
            except Exception as e:
                logger.error(f"❌ Ошибка подключения к Jupiter: {e}")
            
            if self.running:
                # Фиксированная задержка перед переподключением
                wait_time = 5  # 5 секунд между попытками
                logger.info(f"⏱️ Ждем {wait_time} секунд перед переподключением...")
                await asyncio.sleep(wait_time)
    
    async def stop(self):
        """Останавливаем слушатель Jupiter"""
        logger.info("🛑 Останавливаем Jupiter WebSocket слушатель...")
        self.running = False
        
        if hasattr(self, 'websocket') and self.websocket:
            try:
                await self.websocket.close()
                logger.info("✅ Jupiter WebSocket соединение закрыто")
            except Exception as e:
                logger.debug(f"Ошибка при закрытии WebSocket: {e}")
            finally:
                self.websocket = None

class PumpFunTokenListener:
    """Альтернативный слушатель для pump.fun (если Jupiter недоступен)"""
    
    def __init__(self, token_monitor: TokenMonitor):
        self.token_monitor = token_monitor
        self.running = False
        
    async def simulate_new_tokens(self):
        """Имитация новых токенов для тестирования"""
        try:
            test_tokens = [
                {
                    'mint': '26KHEk6Y1F3tY2Lum4fCiTiHC1AtQ6Cneg5yP4TLbonk',
                    'symbol': 'TEST1',
                    'name': 'Test Token 1',
                    'dex_source': 'pump.fun',
                    'market_cap': 50000,
                    'address': '26KHEk6Y1F3tY2Lum4fCiTiHC1AtQ6Cneg5yP4TLbonk'
                },
                {
                    'mint': '7GuYTEVSsqnRMzsRy2u2Zj9HjduEJRj2mWSBN4D9T3ZA', 
                    'symbol': 'TEST2',
                    'name': 'Test Token 2',
                    'dex_source': 'pump.fun',
                    'market_cap': 75000,
                    'address': '7GuYTEVSsqnRMzsRy2u2Zj9HjduEJRj2mWSBN4D9T3ZA'
                }
            ]
            
            while self.running:
                for token in test_tokens:
                    if not self.running:
                        break
                        
                    logger.info(f"🧪 Тестовый токен: {token['symbol']}")
                    await self.token_monitor.add_token_for_analysis(token)
                    
                    # Ждем 60 секунд перед следующим токеном
                    await asyncio.sleep(60)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка имитации токенов: {e}")
    
    async def start(self):
        """Запускаем имитацию"""
        self.running = True
        await self.simulate_new_tokens()
    
    async def stop(self):
        """Останавливаем имитацию"""
        self.running = False

async def main_integration():
    """Основная функция интеграции"""
    logger.info("🚀 Запускаем интеграцию Bundle Analyzer с источниками токенов...")
    
    # Создаем клиенты
    padre_client = MultiplePadreManager()
    token_monitor = TokenMonitor(padre_client)
    
    # Выбираем источник токенов
    use_jupiter = os.getenv("USE_JUPITER", "true").lower() == "true"
    use_padre = os.getenv("USE_PADRE", "true").lower() == "true"  # По умолчанию отключен
    
    if use_jupiter:
        token_listener = JupiterTokenListener(token_monitor)
        logger.info("📡 Используем Jupiter как источник токенов")
    else:
        token_listener = PumpFunTokenListener(token_monitor)
        logger.info("🧪 Используем тестовый режим для токенов")
    
    try:
        if use_padre:
            # Запускаем оба клиента параллельно
            await asyncio.gather(
                padre_client.start(),  # Слушаем trade.padre.gg для бандлеров
                token_listener.start()  # Слушаем новые токены
            )
        else:
            # Запускаем только Jupiter без padre.gg
            logger.info("⚠️ Trade.padre.gg отключен - используем симуляцию анализа бандлеров")
            await token_listener.start()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки интеграции")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка интеграции: {e}")
    finally:
        # Останавливаем клиенты
        if use_padre:
            await padre_client.stop()
        await token_listener.stop()
        logger.info("✅ Интеграция Bundle Analyzer остановлена")

if __name__ == "__main__":
    # Проверяем зависимости
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if not telegram_token or telegram_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("❌ Не установлен TELEGRAM_TOKEN!")
        exit(1)
    
    # Запускаем интеграцию
    asyncio.run(main_integration()) 