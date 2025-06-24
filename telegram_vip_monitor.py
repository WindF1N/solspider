#!/usr/bin/env python3
"""
📱 TELEGRAM VIP MONITOR 📱
Мониторинг VIP Telegram чатов для мгновенных сигналов

Функциональность:
- Мониторинг VIP Telegram чатов в реальном времени
- Поиск контрактов Solana в сообщениях
- Автоматическая покупка с ULTRA приоритетом газа ($5)
- Отправка VIP уведомлений в Telegram бота
- Работает параллельно с Twitter VIP системой
"""

import os
import asyncio
import logging
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from pyrogram import Client, filters
from pyrogram.types import Message

# Загружаем переменные окружения из .env файла
def load_env_file():
    """Загружает переменные окружения из .env файла"""
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print(f"✅ Загружены переменные окружения из {env_file}")
    else:
        print(f"⚠️ Файл {env_file} не найден")

# Загружаем .env при импорте модуля
load_env_file()

# Импортируем конфигурации
try:
    from telegram_vip_config import (
        TELEGRAM_API_CREDENTIALS, VIP_TELEGRAM_CHATS, TELEGRAM_MONITOR_SETTINGS,
        TELEGRAM_NOTIFICATION_CONFIG, MESSAGE_FILTERS, format_telegram_message,
        get_active_telegram_chats, get_auto_buy_telegram_chats, should_process_message,
        update_telegram_stats, get_telegram_stats_summary
    )
    from vip_config import get_gas_fee, get_gas_description, create_keyboard
except ImportError as e:
    print(f"❌ Не удалось импортировать конфигурацию: {e}")
    print("Убедитесь что файлы telegram_vip_config.py и vip_config.py находятся в той же папке")
    exit(1)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, TELEGRAM_MONITOR_SETTINGS.get('log_level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_vip_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TelegramVIPMonitor')

class TelegramVipMonitor:
    """VIP мониторинг Telegram чатов"""
    
    def __init__(self):
        # Загружаем конфигурацию
        self.telegram_chats = VIP_TELEGRAM_CHATS
        self.monitor_settings = TELEGRAM_MONITOR_SETTINGS
        self.notification_config = TELEGRAM_NOTIFICATION_CONFIG
        
        # Настройки Telegram API
        self.api_credentials = TELEGRAM_API_CREDENTIALS
        
        # Настройки уведомлений
        self.notification_bot_token = self.notification_config['bot_token']
        self.notification_chat_id = os.getenv(self.notification_config['chat_id_env_var'])
        
        # Кэш для дедупликации сигналов
        self.signals_cache: Set[str] = set()
        
        # Инициализируем статистику
        update_telegram_stats('start')
        
        # Pyrogram клиент
        self.client = None
        
        active_chats = get_active_telegram_chats()
        auto_buy_chats = get_auto_buy_telegram_chats()
        
        logger.info(f"📱 Telegram VIP Monitor инициализирован")
        logger.info(f"🔄 Активных чатов: {len(active_chats)}")
        logger.info(f"🔄 Чатов с автопокупкой: {len(auto_buy_chats)}")
        
        if not self.notification_chat_id:
            logger.error(f"❌ {self.notification_config['chat_id_env_var']} не задан в переменных окружения!")
    
    def extract_contracts_from_text(self, text: str) -> List[str]:
        """Извлекает Solana контракты из текста сообщения"""
        if not text:
            return []
        
        # Ищем адреса Solana (32-44 символа, буквы и цифры)
        contracts = re.findall(r'\b[A-Za-z0-9]{32,44}\b', text)
        
        # Фильтруем и очищаем
        clean_contracts = []
        for contract in contracts:
            # Убираем "pump" с конца если есть
            if contract.endswith('pump'):
                contract = contract[:-4]
            
            # Проверяем что это похоже на Solana адрес
            if 32 <= len(contract) <= 44 and contract.isalnum():
                # Исключаем явно неправильные адреса
                if not contract.startswith('0000') and not contract.endswith('0000'):
                    clean_contracts.append(contract)
        
        return list(set(clean_contracts))  # Убираем дубликаты
    
    async def send_telegram_notification(self, message: str, keyboard: Optional[List] = None) -> bool:
        """Отправляет уведомление в Telegram"""
        try:
            import requests
            
            payload = {
                "chat_id": self.notification_chat_id,
                "text": message,
                "parse_mode": self.notification_config['parse_mode'],
                "disable_web_page_preview": self.notification_config['disable_web_page_preview']
            }
            
            if keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            
            url = f"https://api.telegram.org/bot{self.notification_bot_token}/sendMessage"
            response = requests.post(url, json=payload, timeout=self.notification_config['timeout'])
            
            if response.status_code == 200:
                logger.info("✅ Telegram уведомление отправлено")
                return True
            else:
                logger.error(f"❌ Ошибка отправки Telegram уведомления: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка отправки уведомления: {e}")
            return False
    
    async def send_telegram_photo_notification(self, photo_url: str, caption: str, keyboard: Optional[List] = None) -> bool:
        """Отправляет уведомление с фото в Telegram"""
        try:
            import requests
            
            payload = {
                "chat_id": self.notification_chat_id,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": self.notification_config['parse_mode']
            }
            
            if keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            
            url = f"https://api.telegram.org/bot{self.notification_bot_token}/sendPhoto"
            response = requests.post(url, json=payload, timeout=self.notification_config['timeout'])
            
            if response.status_code == 200:
                logger.info("✅ Telegram фото уведомление отправлено")
                return True
            else:
                # Если фото не получилось, отправляем текст
                logger.warning(f"⚠️ Не удалось отправить фото, отправляю текст: {response.text}")
                return await self.send_telegram_notification(caption, keyboard)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram фото: {e}")
            return await self.send_telegram_notification(caption, keyboard)
    
    async def execute_automatic_purchase(self, contract: str, chat_id: int, message_text: str, 
                                       amount_sol: float, chat_config: Dict) -> Dict:
        """Выполняет автоматическую покупку токена с ULTRA приоритетом"""
        logger.info(f"🚀 TELEGRAM АВТОПОКУПКА: {contract} на {amount_sol} SOL из чата {chat_id}")
        
        start_time = time.time()
        
        try:
            # Импортируем Axiom трейдер
            from axiom_trader import execute_axiom_purchase
            
            # 🔥 Определяем тип газа на основе приоритета чата
            chat_priority = chat_config.get('priority', 'HIGH')
            if chat_priority == 'ULTRA':
                gas_type = 'ultra_vip'  # $5 газ для ULTRA приоритета
            else:
                gas_type = 'vip_signals'  # $2 газ для HIGH приоритета
            
            vip_gas_fee = get_gas_fee(gas_type)
            gas_description = get_gas_description(gas_type)
            gas_usd = vip_gas_fee * 140  # Приблизительная стоимость в USD
            
            logger.info(f"🔥 Используем {gas_description}")
            logger.info(f"⚡ Telegram VIP Gas fee: {vip_gas_fee} SOL (~${gas_usd:.2f})")
            
            # Выполняем реальную покупку через Axiom.trade
            result = await execute_axiom_purchase(
                contract_address=contract,
                twitter_username=f"TelegramVIP_Chat_{abs(chat_id)}",
                tweet_text=f"Автопокупка из Telegram чата: {message_text[:100]}...",
                sol_amount=amount_sol,
                slippage=15,
                priority_fee=vip_gas_fee  # 🔥 ULTRA VIP газ для мгновенного подтверждения
            )
            
            execution_time = time.time() - start_time
            
            if result.get('success', False):
                logger.info(f"✅ Telegram автопокупка успешна! TX: {result.get('tx_hash', 'N/A')}")
                update_telegram_stats('purchase_success')
                
                return {
                    'success': True,
                    'tx_hash': result.get('tx_hash', 'N/A'),
                    'sol_amount': amount_sol,
                    'execution_time': execution_time,
                    'status': f'Axiom.trade - покупка {amount_sol:.6f} SOL',
                    'platform': 'Axiom.trade',
                    'gas_fee': vip_gas_fee,
                    'gas_usd': gas_usd
                }
            else:
                error_msg = result.get('error', 'Unknown error from Axiom')
                logger.error(f"❌ Ошибка Telegram автопокупки: {error_msg}")
                update_telegram_stats('purchase_failed')
                
                return {
                    'success': False,
                    'error': error_msg,
                    'execution_time': execution_time,
                    'gas_fee': vip_gas_fee,
                    'gas_usd': gas_usd
                }
                
        except ImportError:
            logger.error("❌ axiom_trader модуль не найден! Установите Axiom интеграцию")
            update_telegram_stats('purchase_failed')
            return {
                'success': False,
                'error': 'axiom_trader module not found',
                'execution_time': time.time() - start_time
            }
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Критическая ошибка Telegram автопокупки: {e}")
            update_telegram_stats('purchase_failed')
            return {
                'success': False,
                'error': f'Critical error: {str(e)}',
                'execution_time': execution_time
            }
    
    async def process_message_contracts(self, message: Message, chat_config: Dict):
        """Обрабатывает найденные контракты в сообщении"""
        start_time = time.time()
        
        try:
            # Получаем текст сообщения
            message_text = message.text or message.caption or ""
            
            # Проверяем, нужно ли обрабатывать сообщение
            if not should_process_message(message_text, chat_config):
                return
            
            # Обновляем статистику
            update_telegram_stats('message_processed')
            
            # Ищем контракты
            contracts = self.extract_contracts_from_text(message_text)
            
            if not contracts:
                return
            
            # Получаем информацию об авторе
            author_name = "Unknown"
            if message.from_user:
                if message.from_user.username:
                    author_name = f"@{message.from_user.username}"
                elif message.from_user.first_name:
                    author_name = message.from_user.first_name
                    if message.from_user.last_name:
                        author_name += f" {message.from_user.last_name}"
                else:
                    author_name = f"User_{message.from_user.id}"
            
            # Обрабатываем каждый найденный контракт
            for contract in contracts:
                # Проверяем дедупликацию
                signal_key = f"tg_{message.chat.id}:{contract}"
                
                if signal_key not in self.signals_cache:
                    self.signals_cache.add(signal_key)
                    update_telegram_stats('contract_found')
                    
                    logger.info(f"🔥 TELEGRAM КОНТРАКТ НАЙДЕН! Чат {message.chat.id}: {contract}")
                    
                    # Автоматическая покупка если включена
                    purchase_result = None
                    if chat_config.get('auto_buy', False):
                        amount_sol = chat_config.get('buy_amount_sol', 0.01)
                        update_telegram_stats('purchase_attempt')
                        
                        purchase_result = await self.execute_automatic_purchase(
                            contract, message.chat.id, message_text, amount_sol, chat_config
                        )
                    
                    # Создаем уведомление
                    await self.send_contract_notification(
                        contract, message_text, author_name, message.chat.id, 
                        chat_config, purchase_result
                    )
            
            processing_time = time.time() - start_time
            logger.info(f"📨 Сообщение обработано за {processing_time:.2f}с, найдено {len(contracts)} контрактов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
    
    async def send_contract_notification(self, contract: str, message_text: str, author_name: str,
                                       chat_id: int, chat_config: Dict, purchase_result: Optional[Dict] = None):
        """Отправляет уведомление о найденном контракте"""
        try:
            # Обрезаем сообщение если слишком длинное
            if len(message_text) > 200:
                message_text = message_text[:200] + "..."
            
            # Базовое сообщение
            notification = format_telegram_message(
                'contract_found',
                description=chat_config['description'],
                chat_id=chat_id,
                author_name=author_name,
                contract=contract,
                message_text=message_text,
                priority=chat_config['priority'],
                timestamp=datetime.now().strftime('%H:%M:%S')
            )
            
            # Добавляем информацию об автоматической покупке
            if purchase_result:
                if purchase_result['success']:
                    notification += format_telegram_message(
                        'auto_buy_success',
                        status=purchase_result['status'],
                        sol_amount=purchase_result['sol_amount'],
                        execution_time=purchase_result['execution_time'],
                        tx_hash=purchase_result['tx_hash'],
                        gas_fee=purchase_result.get('gas_fee', 0),
                        gas_usd=purchase_result.get('gas_usd', 0)
                    )
                else:
                    notification += format_telegram_message(
                        'auto_buy_error',
                        error=purchase_result['error'][:100]
                    )
            
            # Создаем клавиатуру
            keyboard = create_keyboard(contract)
            
            # Отправляем уведомление (с попыткой отправить фото)
            photo_url = f"https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/{contract}.webp"
            success = await self.send_telegram_photo_notification(photo_url, notification, keyboard)
            
            if success:
                logger.info(f"📤 Telegram VIP сигнал отправлен для {contract}")
            else:
                logger.error(f"❌ Не удалось отправить Telegram VIP сигнал для {contract}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")
    
    async def setup_client(self):
        """Настраивает Telegram клиент"""
        try:
            # Создаем клиент
            self.client = Client(
                self.api_credentials['session_name'],
                api_id=self.api_credentials['api_id'],
                api_hash=self.api_credentials['api_hash'],
                workdir="."
            )
            
            # Получаем ID чатов для фильтрации
            active_chats = get_active_telegram_chats()
            chat_ids = [config['chat_id'] for config in active_chats.values()]
            
            logger.info(f"📱 Настраиваем мониторинг для чатов: {chat_ids}")
            
            # Создаем фильтр для конкретных чатов
            chat_filter = filters.chat(chat_ids)
            
            # Регистрируем обработчик сообщений
            @self.client.on_message(chat_filter)
            async def handle_message(client, message: Message):
                try:
                    # Найдем конфигурацию для этого чата
                    chat_config = None
                    for config in active_chats.values():
                        if config['chat_id'] == message.chat.id:
                            chat_config = config
                            break
                    
                    if not chat_config:
                        return
                    
                    # Фильтрация сообщений
                    if MESSAGE_FILTERS['ignore_bots'] and message.from_user and message.from_user.is_bot:
                        return
                    
                    if MESSAGE_FILTERS['ignore_forwards'] and message.forward_date:
                        return
                    
                    # Проверяем возраст сообщения
                    max_age = self.monitor_settings['max_message_age']
                    if message.date and (datetime.now() - message.date).total_seconds() > max_age:
                        return
                    
                    # Обрабатываем сообщение
                    await self.process_message_contracts(message, chat_config)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в обработчике сообщений: {e}")
            
            logger.info("✅ Telegram клиент настроен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки Telegram клиента: {e}")
            return False
    
    async def start_monitoring(self):
        """Запускает мониторинг Telegram чатов"""
        try:
            if not self.notification_chat_id:
                logger.error(f"❌ {self.notification_config['chat_id_env_var']} не настроен")
                return
            
            # Настраиваем клиент
            if not await self.setup_client():
                logger.error("❌ Не удалось настроить Telegram клиент")
                return
            
            # Отправляем уведомление о запуске
            if self.monitor_settings.get('send_startup_notification', True):
                active_chats = get_active_telegram_chats()
                auto_buy_chats = get_auto_buy_telegram_chats()
                
                start_message = format_telegram_message(
                    'startup',
                    active_chats=len(active_chats),
                    auto_buy_chats=', '.join([f"Chat_{abs(config['chat_id'])}" for config in auto_buy_chats.values()]),
                    timestamp=datetime.now().strftime('%H:%M:%S %d.%m.%Y')
                )
                
                await self.send_telegram_notification(start_message)
            
            logger.info("🚀 Запуск Telegram VIP мониторинга...")
            
            # Запускаем клиент
            await self.client.start()
            logger.info("✅ Telegram VIP Monitor запущен и готов к работе!")
            
            # Основной цикл (Pyrogram сам обрабатывает сообщения)
            while True:
                await asyncio.sleep(60)  # Проверяем статус каждую минуту
                
                # Очищаем кэш при превышении лимита
                cleanup_threshold = self.monitor_settings['cache_cleanup_threshold']
                if len(self.signals_cache) > cleanup_threshold:
                    logger.info("🧹 Очистка кэша Telegram сигналов")
                    self.signals_cache.clear()
                
        except KeyboardInterrupt:
            logger.info("🛑 Остановка Telegram VIP мониторинга по запросу пользователя")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка Telegram мониторинга: {e}")
            
            # Отправляем уведомление об ошибке
            if self.monitor_settings.get('send_error_notifications', True):
                error_message = format_telegram_message(
                    'connection_error',
                    error=str(e)[:200],
                    delay=self.monitor_settings['reconnect_delay']
                )
                await self.send_telegram_notification(error_message)
            
            # Ждем перед переподключением
            await asyncio.sleep(self.monitor_settings['reconnect_delay'])
        finally:
            if self.client:
                await self.client.stop()
    
    async def start(self):
        """Запуск мониторинга с автоматическим переподключением"""
        while True:
            try:
                await self.start_monitoring()
            except Exception as e:
                logger.error(f"❌ Критическая ошибка: {e}")
                await asyncio.sleep(self.monitor_settings['reconnect_delay'])
                logger.info("🔄 Попытка переподключения...")


async def main():
    """Главная функция"""
    monitor = TelegramVipMonitor()
    await monitor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Telegram VIP Monitor остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка в Telegram VIP мониторе")
