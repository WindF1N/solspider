#!/usr/bin/env python3
"""
📱 TELEGRAM VIP MONITOR (TELETHON) 📱
Мониторинг VIP Telegram чатов для мгновенных сигналов

Использует Telethon для более стабильной работы без конфликтов зависимостей.
"""

import os
import asyncio
import logging
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Set

from telethon import TelegramClient, events
from telethon.tl.types import Message, User, Channel, Chat

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
        logging.FileHandler('telegram_vip_telethon.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TelegramVIPTelethon')

class TelegramVipTelethon:
    """VIP мониторинг Telegram чатов через Telethon"""
    
    def __init__(self):
        # Загружаем конфигурацию
        self.telegram_chats = VIP_TELEGRAM_CHATS
        self.monitor_settings = TELEGRAM_MONITOR_SETTINGS
        self.notification_config = TELEGRAM_NOTIFICATION_CONFIG
        
        # Настройки Telegram API
        self.api_credentials = TELEGRAM_API_CREDENTIALS
        
        # Создаем Telethon клиент
        self.client = TelegramClient(
            self.api_credentials['session_name'],
            self.api_credentials['api_id'],
            self.api_credentials['api_hash']
        )
        
        # Настройки уведомлений
        self.notification_bot_token = self.notification_config['bot_token']
        self.notification_chat_id = os.getenv(self.notification_config['chat_id_env_var'])
        
        # Кэш для дедупликации сигналов
        self.signals_cache: Set[str] = set()
        
        # Список активных чатов
        self.active_chats = get_active_telegram_chats()
        self.chat_ids = [config['chat_id'] for config in self.active_chats.values()]
        
        # Инициализируем статистику
        update_telegram_stats('start')
        
        logger.info(f"📱 Telegram VIP Telethon инициализирован")
        logger.info(f"🔄 Активных чатов: {len(self.active_chats)}")
        logger.info(f"💰 Чатов с автопокупкой: {len(get_auto_buy_telegram_chats())}")
        logger.info(f"📋 Мониторим чаты: {self.chat_ids}")
        
        if not self.notification_chat_id:
            logger.error(f"❌ {self.notification_config['chat_id_env_var']} не задан в переменных окружения!")
    
    def extract_contracts_from_text(self, text: str) -> List[str]:
        """Извлекает Solana контракты из текста сообщения"""
        if not text:
            return []
        
        all_contracts = []
        
        # 1. Ищем обычные адреса Solana (32-44 символа, буквы и цифры)
        basic_contracts = re.findall(r'\b[A-Za-z0-9]{32,44}\b', text)
        all_contracts.extend(basic_contracts)
        
        # 2. Ищем контракты в URL pump.fun и других платформах
        pump_contracts = re.findall(r'pump\.fun/coin/([A-Za-z0-9]{32,44})', text, re.IGNORECASE)
        all_contracts.extend(pump_contracts)
        
        # 3. Ищем контракты в dexscreener URL
        dex_contracts = re.findall(r'dexscreener\.com/solana/([A-Za-z0-9]{32,44})', text, re.IGNORECASE)
        all_contracts.extend(dex_contracts)
        
        # 4. Ищем контракты в birdeye URL
        birdeye_contracts = re.findall(r'birdeye\.so/token/([A-Za-z0-9]{32,44})', text, re.IGNORECASE)
        all_contracts.extend(birdeye_contracts)
        
        # 5. Ищем контракты в jupiter URL
        jupiter_contracts = re.findall(r'jup\.ag/swap/[A-Za-z0-9]+-([A-Za-z0-9]{32,44})', text, re.IGNORECASE)
        all_contracts.extend(jupiter_contracts)
        
        # 6. Ищем контракты в raydium URL
        raydium_contracts = re.findall(r'raydium\.io/swap/\?([A-Za-z0-9]{32,44})', text, re.IGNORECASE)
        all_contracts.extend(raydium_contracts)
        
        # 7. Ищем контракты после специальных префиксов
        prefix_patterns = [
            r'(?:contract|контракт|ca|address|адрес)[:=\s]+([A-Za-z0-9]{32,44})(?:\s|$)',
            r'(?:token|токен)[:=\s]+([A-Za-z0-9]{32,44})(?:\s|$)',
            r'\b([A-Za-z0-9]{32,44})(?:\s*(?:pump|пампим|buy|покупаем))(?:\s|$)'
        ]
        
        for pattern in prefix_patterns:
            prefix_contracts = re.findall(pattern, text, re.IGNORECASE)
            all_contracts.extend(prefix_contracts)
        
        # 8. Ищем контракты в Markdown ссылках и коде
        markdown_contracts = re.findall(r'`([A-Za-z0-9]{32,44})`', text)
        all_contracts.extend(markdown_contracts)
        
        # 9. Ищем контракты в квадратных скобках (цитаты)
        quote_contracts = re.findall(r'\[([A-Za-z0-9]{32,44})\]', text)
        all_contracts.extend(quote_contracts)
        
        # Фильтруем и очищаем все найденные контракты
        clean_contracts = []
        for contract in all_contracts:
            if not contract:
                continue
                
            # Убираем "pump" с конца если есть
            if contract.endswith('pump'):
                contract = contract[:-4]
            
            # Проверяем что это похоже на Solana адрес
            if 32 <= len(contract) <= 44 and contract.isalnum():
                # Исключаем явно неправильные адреса
                if not contract.startswith('0000') and not contract.endswith('0000'):
                    # Исключаем общие токены (SOL, USDC и т.д.)
                    excluded_tokens = [
                        'So11111111111111111111111111111111111111112',  # SOL
                        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',  # USDC
                        'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',  # USDT
                    ]
                    
                    if contract not in excluded_tokens:
                        clean_contracts.append(contract)
        
        # Убираем дубликаты сохраняя порядок
        seen = set()
        final_contracts = []
        for contract in clean_contracts:
            if contract not in seen:
                # Проверяем что этот контракт не является началом более длинного контракта
                is_substring = False
                for other_contract in clean_contracts:
                    if other_contract != contract and other_contract.startswith(contract):
                        is_substring = True
                        break
                
                if not is_substring:
                    seen.add(contract)
                    final_contracts.append(contract)
        
        if final_contracts:
            logger.info(f"🔍 Найдено {len(final_contracts)} уникальных контрактов: {final_contracts}")
        
        return final_contracts
    
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
    
    def get_chat_config(self, chat_id: int) -> Optional[Dict]:
        """Получает конфигурацию для чата по ID"""
        for config in self.active_chats.values():
            if config['chat_id'] == chat_id:
                return config
        return None
    
    def get_author_name(self, message: Message) -> str:
        """Получает имя автора сообщения"""
        if not message.sender:
            return "Unknown"
            
        if hasattr(message.sender, 'username') and message.sender.username:
            return f"@{message.sender.username}"
        elif hasattr(message.sender, 'first_name') and message.sender.first_name:
            name = message.sender.first_name
            if hasattr(message.sender, 'last_name') and message.sender.last_name:
                name += f" {message.sender.last_name}"
            return name
        else:
            return f"User_{message.sender.id}" if hasattr(message.sender, 'id') else "Unknown"
    
    def extract_full_text_from_message(self, message: Message) -> str:
        """Извлекает полный текст из сообщения включая форматированные элементы"""
        try:
            all_text_parts = []
            
            # Основной текст сообщения
            if message.text:
                all_text_parts.append(message.text)
            
            # Извлекаем текст из entities (ссылки, моношрифт, жирный текст и т.д.)
            if hasattr(message, 'entities') and message.entities:
                from telethon.tl.types import (
                    MessageEntityUrl, MessageEntityTextUrl, MessageEntityMention, 
                    MessageEntityCode, MessageEntityPre, MessageEntityBold,
                    MessageEntityItalic, MessageEntityUnderline, MessageEntityStrike,
                    MessageEntityCashtag, MessageEntityHashtag, MessageEntityPhone,
                    MessageEntityEmail, MessageEntityBankCard, MessageEntitySpoiler,
                    MessageEntityCustomEmoji, MessageEntityBlockquote
                )
                
                for entity in message.entities:
                    # Получаем текст из entity
                    start = entity.offset
                    end = entity.offset + entity.length
                    entity_text = message.text[start:end] if message.text else ""
                    
                    # 🔍 СПЕЦИАЛЬНАЯ ОБРАБОТКА СКРЫТОГО ТЕКСТА (SPOILER)
                    if isinstance(entity, MessageEntitySpoiler):
                        if entity_text and entity_text not in all_text_parts:
                            all_text_parts.append(entity_text)
                            logger.info(f"👁️ Найден скрытый текст (spoiler): {entity_text[:50]}...")
                    
                    # 📜 ОБРАБОТКА ЦИТАТ/БЛОКОВ
                    elif isinstance(entity, MessageEntityBlockquote):
                        if entity_text and entity_text not in all_text_parts:
                            all_text_parts.append(entity_text)
                            logger.info(f"📜 Найден текст в цитате: {entity_text[:50]}...")
                    
                    # 💻 ОБРАБОТКА КОДА И ПРЕ-БЛОКОВ  
                    elif isinstance(entity, (MessageEntityCode, MessageEntityPre)):
                        if entity_text and entity_text not in all_text_parts:
                            all_text_parts.append(entity_text)
                            logger.info(f"💻 Найден код: {entity_text[:50]}...")
                    
                    # 🔗 ОБРАБОТКА ВСЕХ ОСТАЛЬНЫХ ENTITIES
                    else:
                        if entity_text and entity_text not in all_text_parts:
                            all_text_parts.append(entity_text)
                    
                    # Для URL entities получаем сам URL
                    if isinstance(entity, MessageEntityTextUrl) and hasattr(entity, 'url'):
                        if entity.url not in all_text_parts:
                            all_text_parts.append(entity.url)
                            logger.info(f"🔗 Найден URL: {entity.url[:50]}...")
            
            # Извлекаем текст из кнопок (если есть)
            if hasattr(message, 'reply_markup') and message.reply_markup:
                from telethon.tl.types import ReplyInlineMarkup
                if isinstance(message.reply_markup, ReplyInlineMarkup):
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'text') and button.text:
                                all_text_parts.append(button.text)
                            if hasattr(button, 'url') and button.url:
                                all_text_parts.append(button.url)
            
            # Извлекаем текст из подписи к медиа
            if hasattr(message, 'message') and message.message:
                if message.message not in all_text_parts:
                    all_text_parts.append(message.message)
            
            # 📤 ОБРАБОТКА ПЕРЕСЛАННЫХ СООБЩЕНИЙ
            if hasattr(message, 'forward') and message.forward:
                # Если есть оригинальное сообщение с текстом
                if hasattr(message, 'fwd_from') and message.text:
                    logger.info(f"📤 Обрабатываем пересланное сообщение")
            
            # 🖼️ ОБРАБОТКА МЕДИА-ПОДПИСЕЙ
            if hasattr(message, 'media') and message.media:
                # Проверяем подпись к фото/видео
                if hasattr(message.media, 'caption') and message.media.caption:
                    if message.media.caption not in all_text_parts:
                        all_text_parts.append(message.media.caption)
                        logger.info(f"🖼️ Найдена подпись к медиа: {message.media.caption[:50]}...")
                
                # Проверяем документы (файлы) с подписью
                if hasattr(message.media, 'document') and hasattr(message.media.document, 'attributes'):
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'file_name') and attr.file_name:
                            # Извлекаем контракты даже из имен файлов
                            if attr.file_name not in all_text_parts:
                                all_text_parts.append(attr.file_name)
                                logger.info(f"📁 Найдено имя файла: {attr.file_name}")
            
            # Объединяем весь текст
            full_text = " ".join(all_text_parts)
            
            # Дедупликация и очистка
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            
            logger.debug(f"🔍 Извлечен полный текст ({len(all_text_parts)} частей): {full_text[:100]}...")
            
            return full_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения полного текста: {e}")
            # Возвращаем базовый текст как fallback
            return message.text or message.message or ""
    
    async def process_message_contracts(self, message: Message, chat_config: Dict):
        """Обрабатывает найденные контракты в сообщении"""
        start_time = time.time()
        
        try:
            # Получаем текст сообщения
            message_text = self.extract_full_text_from_message(message)
            
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
            author_name = self.get_author_name(message)
            
            # Обрабатываем каждый найденный контракт
            for contract in contracts:
                # Проверяем дедупликацию
                signal_key = f"tg_{message.chat_id}:{contract}"
                
                if signal_key not in self.signals_cache:
                    self.signals_cache.add(signal_key)
                    update_telegram_stats('contract_found')
                    
                    logger.info(f"🔥 TELEGRAM КОНТРАКТ НАЙДЕН! Чат {message.chat_id}: {contract}")
                    
                    # Автоматическая покупка если включена
                    purchase_result = None
                    if chat_config.get('auto_buy', False):
                        amount_sol = chat_config.get('buy_amount_sol', 0.01)
                        update_telegram_stats('purchase_attempt')
                        
                        purchase_result = await self.execute_automatic_purchase(
                            contract, message.chat_id, message_text, amount_sol, chat_config
                        )
                    
                    # Создаем уведомление
                    await self.send_contract_notification(
                        contract, message_text, author_name, message.chat_id, 
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
    
    async def setup_event_handlers(self):
        """Настраивает обработчики событий Telethon"""
        
        @self.client.on(events.NewMessage(chats=self.chat_ids))
        async def new_message_handler(event):
            """Обработчик новых сообщений"""
            try:
                message = event.message
                chat_id = message.chat_id
                
                # Получаем конфигурацию чата
                chat_config = self.get_chat_config(chat_id)
                if not chat_config:
                    return
                
                # Специальная обработка для ботов
                is_bot_chat = chat_config.get('is_bot', False)
                
                # Упрощенная фильтрация - все VIP чаты обрабатывают сообщения от ботов
                # Проверяем только пересланные сообщения (если отключено в настройках чата)
                if not chat_config.get('monitor_forwards', True) and message.forward:
                    return
                
                # Для ботов пропускаем дополнительные проверки
                # Проверяем возраст сообщения для всех типов чатов
                max_age = self.monitor_settings['max_message_age']
                if message.date:
                    # Приводим к UTC для корректного сравнения
                    from datetime import timezone
                    now_utc = datetime.now(timezone.utc)
                    message_date = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                    if (now_utc - message_date).total_seconds() > max_age:
                        return
                
                # Обрабатываем сообщение
                await self.process_message_contracts(message, chat_config)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике новых сообщений: {e}")
        
        @self.client.on(events.MessageEdited(chats=self.chat_ids))
        async def edited_message_handler(event):
            """Обработчик редактированных сообщений"""
            try:
                message = event.message
                chat_id = message.chat_id
                
                # Получаем конфигурацию чата
                chat_config = self.get_chat_config(chat_id)
                if not chat_config or not chat_config.get('monitor_edits', True):
                    return
                
                # Обрабатываем как новое сообщение
                await self.process_message_contracts(message, chat_config)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике редактированных сообщений: {e}")
        
        logger.info("✅ Обработчики событий Telethon настроены")
    
    async def start_monitoring(self):
        """Запускает мониторинг Telegram чатов"""
        try:
            if not self.notification_chat_id:
                logger.error(f"❌ {self.notification_config['chat_id_env_var']} не настроен")
                return
            
            logger.info("🚀 Подключение к Telegram через Telethon...")
            
            # Запускаем клиент
            await self.client.start()
            logger.info("✅ Успешно подключены к Telegram!")
            
            # Настраиваем обработчики событий
            await self.setup_event_handlers()
            
            # Получаем информацию о себе
            me = await self.client.get_me()
            logger.info(f"👤 Авторизован как: {me.first_name} (@{me.username})")
            
            # Проверяем доступ к чатам
            for chat_id in self.chat_ids:
                try:
                    # Получаем конфигурацию чата для проверки типа
                    chat_config = self.get_chat_config(chat_id)
                    
                    # Специальная обработка для ботов
                    if chat_config and chat_config.get('is_bot', False):
                        try:
                            # Для ботов пробуем получить через username или ID
                            entity = await self.client.get_entity(chat_id)
                            logger.info(f"🤖 Доступ к боту: {chat_id}")
                        except Exception as bot_error:
                            logger.warning(f"⚠️ Не удалось подключиться к боту {chat_id}: {bot_error}")
                            logger.info(f"💡 Попробуйте начать диалог с ботом вручную: @{chat_id}")
                            continue
                    else:
                        # Обычная обработка для групп/каналов
                        entity = await self.client.get_entity(chat_id)
                        if hasattr(entity, 'title'):
                            logger.info(f"✅ Доступ к чату: {entity.title} ({chat_id})")
                        else:
                            logger.info(f"✅ Доступ к чату: {chat_id}")
                            
                except Exception as e:
                    logger.error(f"❌ Нет доступа к чату {chat_id}: {e}")
                    
                    # Для ботов даем дополнительные инструкции
                    chat_config = self.get_chat_config(chat_id)
                    if chat_config and chat_config.get('is_bot', False):
                        logger.info(f"💡 Для работы с ботом {chat_id}:")
                        logger.info(f"   1. Найдите бота в Telegram")
                        logger.info(f"   2. Нажмите /start")
                        logger.info(f"   3. Перезапустите мониторинг")
            
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
            
            logger.info("🔥 Telegram VIP мониторинг запущен! Ожидаем сообщения...")
            
            # Основной цикл - Telethon сам обрабатывает сообщения
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
            await self.client.disconnect()
    
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
    monitor = TelegramVipTelethon()
    await monitor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Telegram VIP Monitor (Telethon) остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка в Telegram VIP мониторе") 

