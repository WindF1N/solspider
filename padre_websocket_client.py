#!/usr/bin/env python3
"""
Improved WebSocket client for trade.padre.gg
Правильно декодирует бинарные сообщения и извлекает данные о бандлерах
"""

import asyncio
import websockets
import json
import base64
import struct
import logging
import msgpack
from typing import Dict, List, Optional, Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

class PadreMessageDecoder:
    """Декодер сообщений от trade.padre.gg"""
    
    @staticmethod
    def decode_base64_message(message: bytes) -> Optional[str]:
        """Декодируем base64 сообщение"""
        try:
            decoded = base64.b64decode(message).decode('utf-8', errors='ignore')
            return decoded
        except:
            return None
    
    @staticmethod
    def decode_msgpack_message(message: bytes) -> Optional[dict]:
        """Декодируем MessagePack сообщение"""
        try:
            data = msgpack.unpackb(message, raw=False, strict_map_key=False)
            return data
        except:
            return None
    
    @staticmethod
    def decode_multiplexed_message(message: bytes) -> Optional[dict]:
        """Декодируем мультиплексированное сообщение"""
        try:
            # Формат может быть: [длина][тип][данные]
            if len(message) < 4:
                return None
            
            # Читаем первые 4 байта как длину
            length = struct.unpack('>I', message[:4])[0]
            
            if len(message) < 4 + length:
                return None
            
            # Извлекаем данные
            data_bytes = message[4:4+length]
            
            # Пытаемся декодировать как JSON
            try:
                text = data_bytes.decode('utf-8')
                return json.loads(text)
            except:
                pass
            
            # Пытаемся декодировать как MessagePack
            try:
                return msgpack.unpackb(data_bytes, raw=False)
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.debug(f"Ошибка декодирования мультиплексированного сообщения: {e}")
            return None
    
    @classmethod
    def decode_message(cls, message: bytes) -> Optional[dict]:
        """Основной метод декодирования"""
        if not message:
            return None
        
        # Логируем первые байты для анализа
        logger.debug(f"Сообщение ({len(message)} байт): {message[:20].hex() if len(message) >= 20 else message.hex()}")
        
        # Пытаемся различные методы декодирования
        
        # 1. Прямой JSON
        try:
            text = message.decode('utf-8')
            return json.loads(text)
        except:
            pass
        
        # 2. Base64 + JSON
        decoded_b64 = cls.decode_base64_message(message)
        if decoded_b64:
            try:
                return json.loads(decoded_b64)
            except:
                if 'bundler' in decoded_b64.lower() or 'holder' in decoded_b64.lower():
                    return {'raw_text': decoded_b64}
        
        # 3. MessagePack
        msgpack_data = cls.decode_msgpack_message(message)
        if msgpack_data:
            return msgpack_data
        
        # 4. Мультиплексированный формат
        multiplexed_data = cls.decode_multiplexed_message(message)
        if multiplexed_data:
            return multiplexed_data
        
        # 5. Анализ по байтам
        if len(message) >= 2:
            # Проверяем первые байты на известные паттерны
            first_byte = message[0]
            second_byte = message[1] if len(message) > 1 else 0
            
            logger.debug(f"Первые байты: 0x{first_byte:02x} 0x{second_byte:02x}")
            
            # Возможные паттерны протокола padre.gg
            if first_byte == 0x8c or first_byte == 0x84:  # Возможно MessagePack array/map
                try:
                    return msgpack.unpackb(message[1:], raw=False)
                except:
                    pass
        
        return None

class BundlerDataExtractor:
    """Извлечение данных о бандлерах из декодированных сообщений"""
    
    @staticmethod
    def extract_bundler_info(data: Any) -> Optional[dict]:
        """Извлекаем информацию о бандлерах"""
        if not data:
            return None
        
        result = {}
        
        # Если это строка, ищем ключевые слова
        if isinstance(data, str):
            if any(keyword in data.lower() for keyword in ['bundler', 'holder', 'bundle']):
                # Пытаемся извлечь числа
                import re
                numbers = re.findall(r'\d+', data)
                if numbers:
                    result['bundler_count'] = int(numbers[0])
                    result['raw_text'] = data
                return result
        
        # Если это словарь, ищем релевантные поля
        elif isinstance(data, dict):
            result = BundlerDataExtractor._extract_from_dict(data)
            if result:
                return result
        
        # Если это список, проверяем элементы
        elif isinstance(data, list):
            for item in data:
                sub_result = BundlerDataExtractor.extract_bundler_info(item)
                if sub_result:
                    return sub_result
        
        return None
    
    @staticmethod
    def _extract_from_dict(data: dict) -> Optional[dict]:
        """Извлекаем данные из словаря"""
        result = {}
        
        # Прямые поля бандлеров
        bundler_fields = [
            'bundlers', 'bundler_count', 'bundlerCount',
            'holders', 'holder_count', 'holderCount',
            'totalHolders', 'total_holders',
            'uniqueHolders', 'unique_holders'
        ]
        
        for field in bundler_fields:
            if field in data and isinstance(data[field], (int, float)):
                result['bundler_count'] = int(data[field])
                result['source_field'] = field
                break
        
        # Ищем адрес контракта
        contract_fields = [
            'contract', 'address', 'mint', 'token', 'asset',
            'contractAddress', 'tokenAddress', 'mintAddress',
            'baseAsset', 'quoteAsset', 'id'
        ]
        
        for field in contract_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str) and len(value) >= 32:
                    result['contract_address'] = value
                    break
                elif isinstance(value, dict) and 'address' in value:
                    result['contract_address'] = value['address']
                    break
        
        # Ищем другие полезные данные
        if 'marketCap' in data:
            result['market_cap'] = data['marketCap']
        if 'price' in data:
            result['price'] = data['price']
        if 'volume' in data:
            result['volume'] = data['volume']
        
        # Ищем метрики торговли
        trading_fields = [
            'trades', 'tradeCount', 'transactions', 'txCount'
        ]
        
        for field in trading_fields:
            if field in data and isinstance(data[field], (int, float)):
                result['trade_count'] = int(data[field])
                break
        
        # Рекурсивно ищем в вложенных объектах
        for key, value in data.items():
            if isinstance(value, dict):
                sub_result = BundlerDataExtractor._extract_from_dict(value)
                if sub_result and 'bundler_count' in sub_result:
                    result.update(sub_result)
                    break
        
        # Возвращаем результат только если найдены бандлеры
        if 'bundler_count' in result:
            result['raw_data'] = data
            return result
        
        return None
    
    @staticmethod
    def calculate_bundler_percentage(bundler_count: int, total_supply: Optional[int] = None) -> float:
        """Рассчитываем процент бандлеров"""
        if total_supply and total_supply > 0:
            return (bundler_count / total_supply) * 100
        
        # Если нет данных о total_supply, используем эвристику
        # Предполагаем, что 1000 держателей = 100%
        max_holders = 1000
        return (bundler_count / max_holders) * 100

class ImprovedPadreClient:
    """Улучшенный клиент для trade.padre.gg"""
    
    def __init__(self):
        self.websocket = None
        self.running = False
        self.message_decoder = PadreMessageDecoder()
        self.bundler_extractor = BundlerDataExtractor()
        self.pending_tokens = {}
        
    async def connect(self):
        """Подключение к WebSocket"""
        try:
            # URL и заголовки
            ws_url = "wss://backend2.padre.gg/_multiplex?desc=%2Ftrade%2Fsolana%2F26KHEk6Y1F3tY2Lum4fCiTiHC1AtQ6Cneg5yP4TLbonk"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
                'Origin': 'https://trade.padre.gg',
                'Cookie': 'mp_f259317776e8d4d722cf5f6de613d9b5_mixpanel=%7B%22distinct_id%22%3A%20%22h9OxQuVq9IY2Tvr4c4iAkdq6zsr1%22%2C%22%24device_id%22%3A%20%2219815b2e836edc-0d96b9e7fde936-4c657b58-1fa400-19815b2e8371af5%22%2C%22%24user_id%22%3A%20%22h9OxQuVq9IY2Tvr4c4iAkdq6zsr1%22%2C%22%24initial_referrer%22%3A%20%22%24direct%22%2C%22%24initial_referring_domain%22%3A%20%22%24direct%22%2C%22referralCode%22%3A%20%22soldeggen%22%7D'
            }
            
            logger.info("🔗 Подключаемся к улучшенному trade.padre.gg WebSocket...")
            
            self.websocket = await websockets.connect(
                ws_url,
                extra_headers=headers,
                ping_interval=30,
                ping_timeout=10,
                max_size=10**7
            )
            
            logger.info("✅ Успешно подключились к trade.padre.gg")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к trade.padre.gg: {e}")
            return False
    
    async def send_initial_messages(self):
        """Отправляем начальные сообщения как в браузере"""
        try:
            # Список сообщений из анализа браузера
            initial_messages = [
                "kwHaBLFleUpoYkdjaU9pSlNVekkxTmlJc0ltdHBaQ0k2SW1FNFpHWTJNbVF6WVRCaE5EUmxNMlJtWTJSallXWmpObVJoTVRNNE16YzNORFU1WmpsaU1ERWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKdVlXMWxJam9pMEpyUXNOR0MwWThnMEpqUXN0Q3cwTDNRdnRDeTBMQWlMQ0p3YVdOMGRYSmxJam9pYUhSMGNITTZMeTlzYURNdVoyOXZaMnhsZFhObGNtTnZiblJsYm5RdVkyOXRMMkV2UVVObk9FOWpTVVJZUmtoWVVsaFpSa3h3WVhjMGJFMU5ZbHBuUzNoTFNFUkJUR2xvWVRkRGFYcHRibFprZGpFeGJXNUJNMlJyY3oxek9UWXRZeUlzSW1oaGRYUm9JanAwY25WbExDSnBjM01pT2lKb2RIUndjem92TDNObFkzVnlaWFJ2YTJWdUxtZHZiMmRzWlM1amIyMHZjR0ZrY21VdE5ERTNNREl3SWl3aVlYVmtJam9pY0dGa2NtVXROREUzTURJd0lpd2lZWFYwYUY5MGFXMWxJam94TnpRNU5qWXpOekkzTENKMWMyVnlYMmxrSWpvaWFEbFBlRkYxVm5FNVNWa3lWSFp5TkdNMGFVRnJaSEUyZW5OeU1TSXNJbk4xWWlJNkltZzVUM2hSZFZaeE9VbFpNbFIyY2pSak5HbEJhMlJ4Tm5wemNqRWlMQ0pwWVhRaU9qRTNOVEkzTVRFNE5ERXNJbVY0Y0NJNk1UYzFNamN4TlRRME1Td2laVzFoYVd3aU9pSmhaMkZtYjI1dmRpNWxaMjl5ZFhOb2EyRkFaMjFoYVd3dVkyOXRJaXdpWlcxaGFXeGZkbVZ5YVdacFpXUWlPblJ5ZFdVc0ltWnBjbVZpWVhObElqcDdJbWxrWlc1MGFYUnBaWE1pT25zaVoyOXZaMnhsTG1OdmJTSTZXeUl4TURrM01qYzNOell3TVRreU5EWTNOelEyTXpFaVhTd2laVzFoYVd3aU9sc2lZV2RoWm05dWIzWXVaV2R2Y25WemFHdGhRR2R0WVdsc0xtTnZiU0pkZlN3aWMybG5ibDlwYmw5d2NtOTJhV1JsY2lJNkltZHZiMmRzWlM1amIyMGlmWDAuUHhYS3M5LUk4R1JKSGFVOEs0UGhteVRuUDZORXZpQXBuS2RjNDEzTGZyUmpFTzZSRFN3V3BSdFEyNWRyWlVzb1p4aVpkRkNBZDF4LXJJWGNjVEczcW5CdjYwVFJUd3IxN25GWEtPUTltcUFOTWg1S0owclNGbElTcXRkdFBsb2F1dWowYkNBX1pmLWtDUnNrMEpsc3ppN1djZC15ZFdqZFh5TmMwMElQRHVBZDRtU1U4Znk3Snd3SVR3VzVQSjRiQlAzemRENlE1N084NDVYZzNvZDFVY2I0WVhKXzJheEVuSEUxXzNwVDQzVk9kMWRsMGc2LU85WjlSbEhCSUN6YzVIRWdzNGROeC1sOHBIWlMtOUZvVUVvd2NlSm5jN2Fyc1plUjRjY2pmTzRodUFlN1EzS3ZaOENlUlZzbnFOd0tNOE1VdDZnSWJUVWVlb1N5aU5CV3JRrWNlYTAwNWJmLTA2YjQ=",
                "lAgT2VwvcHJpY2VzL3F1ZXJ5L3NvbGFuYS0yNktIRWs2WTFGM3RZMkx1bTRmQ2lUaUhDMUF0UTZDbmVnNXlQNFRMYm9uay9nZXQtbWFya2V0LXNtYXJ0LXdpdGgtd2FybdkkNWI1YTg4NzAtOThhOS00OTJiLWIyMTItN2VkMmQ5ZWM2NWM5",
                "lAgZ2TwvdXNlcnMvdXNlcnMvaDlPeFF1VnE5SVkyVHZyNGM0aUFrZHE2enNyMS9lYXJseS1hY2Nlc3Mtc2NvcGXA"
            ]
            
            for i, msg_b64 in enumerate(initial_messages):
                msg_bytes = base64.b64decode(msg_b64)
                await self.websocket.send(msg_bytes)
                logger.info(f"📤 Отправлено начальное сообщение {i+1}")
                
                # Небольшая пауза между сообщениями
                await asyncio.sleep(0.1)
            
            logger.info("✅ Все начальные сообщения отправлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки начальных сообщений: {e}")
    
    async def listen_for_messages(self):
        """Слушаем сообщения от WebSocket"""
        try:
            while self.running:
                try:
                    # Получаем сообщение
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                    
                    # Декодируем сообщение
                    decoded_data = self.message_decoder.decode_message(message)
                    
                    if decoded_data:
                        logger.info(f"📨 Декодированное сообщение: {str(decoded_data)[:200]}...")
                        
                        # Извлекаем данные о бандлерах
                        bundler_info = self.bundler_extractor.extract_bundler_info(decoded_data)
                        
                        if bundler_info:
                            await self.process_bundler_data(bundler_info)
                    else:
                        logger.debug(f"🔍 Не удалось декодировать сообщение ({len(message)} байт)")
                        
                except asyncio.TimeoutError:
                    logger.debug("⏱️ Таймаут ожидания сообщений")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("🔌 WebSocket соединение закрыто")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки сообщения: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле прослушивания: {e}")
    
    async def process_bundler_data(self, bundler_info: dict):
        """Обрабатываем данные о бандлерах"""
        try:
            bundler_count = bundler_info.get('bundler_count', 0)
            contract_address = bundler_info.get('contract_address')
            
            logger.info(f"💎 Найдены данные о бандлерах: {bundler_count} для контракта {contract_address}")
            
            if contract_address:
                # Рассчитываем процент
                percentage = self.bundler_extractor.calculate_bundler_percentage(bundler_count)
                
                logger.info(f"📊 Контракт {contract_address[:8]}: {bundler_count} бандлеров ({percentage:.1f}%)")
                
                # Здесь можно добавить логику уведомлений
                if percentage >= 10.0:  # Минимальный порог
                    await self.send_bundler_alert(bundler_info, percentage)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки данных бандлеров: {e}")
    
    async def send_bundler_alert(self, bundler_info: dict, percentage: float):
        """Отправляем уведомление о высоком проценте бандлеров"""
        logger.info(f"🚨 ВЫСОКИЙ ПРОЦЕНТ БАНДЛЕРОВ: {percentage:.1f}%")
        logger.info(f"📊 Данные: {bundler_info}")
        
        # Здесь будет отправка в Telegram
        # await send_telegram_bundler_alert(bundler_info, percentage)
    
    async def start(self):
        """Запускаем клиент"""
        self.running = True
        
        if await self.connect():
            await self.send_initial_messages()
            await self.listen_for_messages()
    
    async def stop(self):
        """Останавливаем клиент"""
        self.running = False
        if self.websocket:
            await self.websocket.close()

async def test_padre_client():
    """Тестирование клиента"""
    logging.basicConfig(level=logging.INFO)
    
    client = ImprovedPadreClient()
    
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(test_padre_client()) 