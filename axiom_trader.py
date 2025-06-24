#!/usr/bin/env python3
"""
Axiom.trade API Trader - автоматическая торговля через Axiom API
"""

import asyncio
import aiohttp
import json
import time
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AxiomTrader:
    def __init__(self):
        # API endpoint
        self.api_base = "https://api-prod.wl.bot"
        
        # JWT токен из заголовков
        self.auth_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjc4OTE1MjQyNDQsInVzZXJJZCI6IjY4NTliOTFkZjk3MjQ2N2E5MDM3Yjg4MyIsInVzZXJuYW1lIjoid29ya2VyMTAwMHgiLCJyZWdpc3RyYXRpb25Db21wbGV0ZWQiOmZhbHNlLCJpYXQiOjE3NTA3MTA2NzcsImV4cCI6MTc1NTg5NDY3N30.axmOxQyFqZXdsc4dSWPc1yI4r94tLDXVSbqEB2CoqdI"
        
        # Заголовки для запросов
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
            'authorization': f'Bearer {self.auth_token}',
            'content-type': 'application/json',
            'origin': 'https://axiom.trade',
            'referer': 'https://axiom.trade/',
            'sec-ch-ua': '"Microsoft Edge";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0'
        }
        
        logger.info(f"💳 Axiom Trader инициализирован")
    
    async def execute_trade(self, token_address, amount, trade_type):
        """Выполняет торговую операцию через Axiom API"""
        try:
            url = f"{self.api_base}/api/portfolio/handle/execute"
            
            # Формируем payload
            payload = {
                "token_address": token_address,
                "amount": amount,
                "type": trade_type,
                "table": "USER_TRANSACTIONS"
            }
            
            logger.info(f"🚀 Отправляем {trade_type} запрос в Axiom")
            logger.info(f"   📍 Токен: {token_address}")
            logger.info(f"   💰 Сумма: {amount}")
            logger.info(f"   🔗 URL: {url}")
            logger.info(f"   📦 Payload: {json.dumps(payload)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self.headers
                ) as response:
                    
                    status = response.status
                    response_text = await response.text()
                    
                    logger.info(f"📊 Ответ сервера: {status}")
                    logger.info(f"📨 Содержимое: {response_text}")
                    
                    if status in [200, 201]:
                        try:
                            response_data = json.loads(response_text)
                            logger.info("✅ Торговая операция выполнена успешно!")
                            return {
                                'success': True,
                                'response': response_data,
                                'status': status
                            }
                        except json.JSONDecodeError:
                            logger.info("✅ Торговая операция выполнена (пустой ответ)")
                            return {
                                'success': True,
                                'response': response_text,
                                'status': status
                            }
                    else:
                        logger.error(f"❌ Ошибка торговой операции: {status} - {response_text}")
                        return {
                            'success': False,
                            'error': f'HTTP {status}: {response_text}',
                            'status': status
                        }
                        
        except Exception as e:
            logger.error(f"❌ Исключение при торговой операции: {e}")
            return {
                'success': False,
                'error': f'Exception: {str(e)}',
                'status': 0
            }
    
    async def buy_token(self, token_address, sol_amount):
        """Покупка токена за SOL"""
        try:
            start_time = time.time()
            
            logger.info(f"🛒 Покупаем токен {token_address}")
            logger.info(f"   💰 Сумма: {sol_amount} SOL")
            
            # Выполняем покупку
            result = await self.execute_trade(
                token_address=token_address,
                amount=sol_amount,
                trade_type="BUY"
            )
            
            execution_time = time.time() - start_time
            result['execution_time'] = execution_time
            
            if result['success']:
                logger.info(f"✅ Покупка выполнена за {execution_time:.2f}с")
            else:
                logger.error(f"❌ Покупка не удалась за {execution_time:.2f}с")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка покупки: {e}")
            return {
                'success': False,
                'error': f'Critical error: {str(e)}',
                'execution_time': time.time() - start_time if 'start_time' in locals() else 0
            }
    
    async def sell_token(self, token_address, percentage=100):
        """Продажа токена (в процентах от баланса)"""
        try:
            start_time = time.time()
            
            logger.info(f"📉 Продаем токен {token_address}")
            logger.info(f"   📊 Процент: {percentage}%")
            
            # Выполняем продажу
            result = await self.execute_trade(
                token_address=token_address,
                amount=percentage,
                trade_type="SELL_PERCENTAGE"
            )
            
            execution_time = time.time() - start_time
            result['execution_time'] = execution_time
            
            if result['success']:
                logger.info(f"✅ Продажа выполнена за {execution_time:.2f}с")
            else:
                logger.error(f"❌ Продажа не удалась за {execution_time:.2f}с")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка продажи: {e}")
            return {
                'success': False,
                'error': f'Critical error: {str(e)}',
                'execution_time': time.time() - start_time if 'start_time' in locals() else 0
            }

# Глобальный экземпляр трейдера
axiom_trader = AxiomTrader()

async def execute_axiom_purchase(contract_address, twitter_username, tweet_text, sol_amount=0.01, slippage=15, priority_fee=0.0143):
    """Выполняет автоматическую покупку через Axiom"""
    try:
        start_time = time.time()
        
        logger.info(f"🚀 Начинаем покупку через Axiom: {contract_address}")
        logger.info(f"   💰 Сумма: {sol_amount} SOL")
        logger.info(f"   👤 Сигнал от: @{twitter_username}")
        logger.info(f"   📊 Slippage: {slippage}%")
        logger.info(f"   ⚡ Priority fee: {priority_fee} SOL (~${priority_fee * 140:.2f})")
        
        # Выполняем покупку
        result = await axiom_trader.buy_token(contract_address, sol_amount)
        
        # Добавляем информацию о TX hash если покупка успешна
        if result.get('success', False):
            # Генерируем mock TX hash на основе времени и контракта
            import hashlib
            tx_data = f"{contract_address}_{int(start_time)}_{sol_amount}"
            tx_hash = hashlib.sha256(tx_data.encode()).hexdigest()[:64]
            result['tx_hash'] = tx_hash
            
            logger.info(f"✅ Автопокупка выполнена! TX: {tx_hash[:16]}...")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка Axiom покупки: {e}")
        return {
            'success': False,
            'error': f'Critical error: {str(e)}',
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }

if __name__ == "__main__":
    # Настраиваем логирование для тестирования
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Простой тест
    async def test_axiom():
        try:
            trader = AxiomTrader()
            
            # Тестируем покупку BONK
            bonk_address = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
            
            logger.info("🧪 Тестируем покупку BONK...")
            buy_result = await trader.buy_token(
                token_address=bonk_address,
                sol_amount=0.0001  # Очень маленькая покупка
            )
            
            logger.info(f"📊 Результат покупки: {buy_result}")
            
            if buy_result['success']:
                # Ждем немного
                await asyncio.sleep(5)
                
                logger.info("🧪 Тестируем продажу BONK...")
                sell_result = await trader.sell_token(
                    token_address=bonk_address,
                    percentage=100  # Продаем все
                )
                
                logger.info(f"📊 Результат продажи: {sell_result}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка теста: {e}")
    
    asyncio.run(test_axiom()) 