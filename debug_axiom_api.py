#!/usr/bin/env python3
"""
Отладочный скрипт для проверки Axiom API
"""

import aiohttp
import asyncio
import logging
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Куки и заголовки
AXIOM_BASE_URL = "https://api9.axiom.trade"
AXIOM_COOKIES = {
    'auth-refresh-token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWZyZXNoVG9rZW5JZCI6IjExMzA1NzA4LWRkNmYtNDM0Zi05NDg2LTg3NGFlYjI1NjlmNiIsImlhdCI6MTc0OTIzNTE5OX0.Ko8fHYKCWtDBJX_3AWChVsfzyfn6TLToDqLFTxhaXFA',
    'auth-access-token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdXRoZW50aWNhdGVkVXNlcklkIjoiZDAwYWE2NDYtMDQ0My00NmExLWE0N2UtYjMyM2Q3YzJlZGQyIiwiaWF0IjoxNzUyODQ0MzkyLCJleHAiOjE3NTI4NDUzNTJ9.c7S4MQFDZ7rswVjNs99acfzvNqE7hE8HUQzAjK4P-qE'
}

async def debug_axiom_api():
    """Отладка Axiom API"""
    
    # Заголовки как в браузере
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Origin': 'https://axiom.trade',
        'Referer': 'https://axiom.trade/',
        'Priority': 'u=1, i',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }
    
    cookie_string = '; '.join([f'{k}={v}' for k, v in AXIOM_COOKIES.items()])
    headers['Cookie'] = cookie_string
    
    # Тестовый токен из примера
    test_token = "EuU9Vh37eKDdUnZkUfMZLGCcBqwFYpr1E6X3ZwUxhvgm"
    
    async with aiohttp.ClientSession() as session:
        
        # 1. Проверяем swap-info
        logger.info(f"🔍 Тестируем swap-info для токена {test_token[:8]}...")
        swap_url = f"{AXIOM_BASE_URL}/swap-info?tokenAddress={test_token}"
        
        try:
            async with session.get(swap_url, headers=headers) as response:
                logger.info(f"📊 Статус swap-info: {response.status}")
                logger.info(f"📋 Заголовки ответа: {dict(response.headers)}")
                
                # Получаем raw content
                content = await response.read()
                logger.info(f"📦 Размер контента: {len(content)} байт")
                
                # Пытаемся прочитать как текст
                try:
                    text_content = content.decode('utf-8')
                    logger.info(f"📄 Текстовый контент (первые 500 символов): {text_content[:500]}")
                except UnicodeDecodeError:
                    logger.info(f"❌ Не удалось декодировать как UTF-8")
                
                # Проверяем content-type
                content_type = response.headers.get('content-type', 'unknown')
                logger.info(f"🏷️ Content-Type: {content_type}")
                
                # Пытаемся парсить как JSON если возможно
                if response.status == 200:
                    try:
                        # Принудительно парсим как JSON независимо от Content-Type
                        text = await response.text()
                        data = json.loads(text)
                        logger.info(f"✅ JSON успешно спарсен!")
                        logger.info(f"📋 Ключи JSON: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        
                        # Выводим pairAddress если есть
                        if isinstance(data, dict) and 'pairAddress' in data:
                            pair_address = data['pairAddress']
                            logger.info(f"🎯 Найден pairAddress: {pair_address}")
                            
                            # 2. Тестируем token-info
                            logger.info(f"\n🔍 Тестируем token-info для pairAddress {pair_address[:8]}...")
                            token_info_url = f"{AXIOM_BASE_URL}/token-info?pairAddress={pair_address}"
                            
                            async with session.get(token_info_url, headers=headers) as token_response:
                                logger.info(f"📊 Статус token-info: {token_response.status}")
                                
                                if token_response.status == 200:
                                    try:
                                        # Принудительно парсим как JSON
                                        text = await token_response.text()
                                        token_data = json.loads(text)
                                        logger.info(f"✅ Token-info JSON успешно спарсен!")
                                        logger.info(f"📋 Ключи token-info: {list(token_data.keys()) if isinstance(token_data, dict) else type(token_data)}")
                                        
                                        # Выводим основные метрики
                                        if isinstance(token_data, dict):
                                            logger.info(f"👥 numHolders: {token_data.get('numHolders', 'N/A')}")
                                            logger.info(f"🤖 numBotUsers: {token_data.get('numBotUsers', 'N/A')}")
                                            logger.info(f"📦 bundlersHoldPercent: {token_data.get('bundlersHoldPercent', 'N/A')}")
                                            logger.info(f"👨‍💼 insidersHoldPercent: {token_data.get('insidersHoldPercent', 'N/A')}")
                                            logger.info(f"💰 dexPaid: {token_data.get('dexPaid', 'N/A')}")
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка парсинга token-info JSON: {e}")
                                        content = await token_response.read()
                                        logger.info(f"📄 Raw token-info content: {content[:200]}")
                                else:
                                    logger.error(f"❌ Ошибка token-info: {token_response.status}")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка парсинга JSON: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка запроса: {e}")

if __name__ == "__main__":
    asyncio.run(debug_axiom_api()) 